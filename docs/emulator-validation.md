# Emulator validation — DJI Pilot 2 (BlueStacks) → fieldhub

Drive **real DJI Pilot 2** (running in BlueStacks) against the **real fieldhub
service**, not DJI's reference demo. The 2026-06-13 spike (`dji-cloud-api-reference.md`
§9) validated the protocol against the *demo*; fieldhub was written to match but
has never met Pilot 2. This run closes that gap before the RC Plus 2 arrives, so
hardware day is pure validation, not debugging.

The run-kit lives in `emulator/`. It is throwaway test tooling — **cert-free,
plain HTTP, no postgres** — separate from the production `field` compose profile.

## What this can and cannot validate

BlueStacks runs Pilot 2 on emulated Android with **no aircraft and no OcuSync
radio**, and (per the spike) **does not expose the native `window.djiBridge`**.
So:

| Leg | Here? | Why |
|---|---|---|
| V1 — login → workspace → authenticated `/manage` API (HTTP) | ✅ | pure HTTP, against *our* envelopes/JWTs |
| V2 — wayline list render + filter + KMZ download | ✅ (see step 6 caveat) | HTTP wayline library + Pilot's route library |
| KMZ import matrix across fleet models | ✅ | exporter × our device dictionary × Pilot import |
| Native JSBridge connect chain (license/`thing`/`media`) | ❌ | no `window.djiBridge` in BlueStacks |
| MQTT device-online, V3 media upload, V4 STS via Pilot's S3 client, V5 TLS | ❌ | need a real RC + aircraft |

Server-side V4/V5 (STS→S3, MQTTS/HTTPS-with-CA) are validated separately against
the production `field` profile, not here.

## Architecture

```
  BlueStacks (Android)                 host (docker)
  ┌────────────────────┐               ┌──────────────────────────────┐
  │ DJI Pilot 2        │               │  nginx :8080                 │
  │ Cloud Service URL: │── 10.0.2.2 ──►│   /tarmacview-* ─► minio:9000 │
  │ http://10.0.2.2:8080              │   /*           ─► fieldhub:8000│
  └────────────────────┘   (host       └──────────────────────────────┘
                            loopback)
```

BlueStacks reaches the host **only** via the emulator alias `10.0.2.2` (→ host
loopback); the host LAN IP hairpins (§9). Everything device-facing is funnelled
through the single nginx port `8080`, including the object store — so presigned
SigV4 URLs are signed for `10.0.2.2:8080` and nginx forwards that `Host` verbatim
to MinIO (a rewritten Host breaks the signature).

## Prerequisites

- Docker Desktop running.
- BlueStacks with the **DJI Pilot 2** APK installed and a DJI account logged in.
- A DJI **Cloud API application** (app id / key / license from developer.dji.com).
- At least one **TarmacView KMZ export** per fleet model you want to test
  (export from the monorepo app). For a plumbing-only dry run any `.kmz` works.

## Step A — rebuild the stack from scratch

```bash
cd emulator
cp .env.emulator.example .env.emulator      # then fill in DJI app creds
# wipe any previous run, rebuild fieldhub, start cert-free.
# --env-file is required: compose interpolates ${VAR} from it (environment:
# overrides env_file:, so --env-file is the one predictable path).
docker compose --env-file .env.emulator -f docker-compose.emulator.yml down -v
docker compose --env-file .env.emulator -f docker-compose.emulator.yml up -d --build
```

Confirm the hub is up through the proxy:

```bash
curl -s http://localhost:8080/healthz
# {"status":"degraded",...,"broker":false,"object_store":true}  - broker false is expected (MQTT off)
curl -s http://localhost:8080/pilot/config
# envelope with app_id/app_key/app_license + mqtt_addr; code!=0 means DJI creds unset
```

Watch what Pilot requests (the key observability tool):

```bash
docker compose --env-file .env.emulator -f docker-compose.emulator.yml logs -f nginx
```

## Step B — host-side smoke test (no BlueStacks)

Proves the plumbing — including the hard part, presigned-URL-through-nginx
SigV4 — before spending emulator time. Run it with the device endpoint signed
for `localhost` (set `FIELDHUB_MINIO_DEVICE_ENDPOINT=http://localhost:8080` in
`.env.emulator`, then `up -d` again), then:

```bash
# 1. login -> token
TOKEN=$(curl -s -X POST http://localhost:8080/manage/api/v1/login \
  -H 'content-type: application/json' \
  -d '{"username":"pilot","password":"pilot-emulator","flag":2}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["access_token"])')

# 2. seed a wayline (any .kmz for plumbing)
./seed-wayline.sh /path/to/any.kmz "Smoke RWY22" 0-89-0 1-53-0

# 3. list it
WS=8f2b3e64-7c1a-4f5e-9d3b-2a6c8e0f4d71
curl -s -H "x-auth-token: $TOKEN" \
  "http://localhost:8080/wayline/api/v1/workspaces/$WS/waylines" | python3 -m json.tool

# 4. download via the presigned redirect - 302 -> object 200 (the SigV4 test)
WID=<id from step 3>
curl -sL -o /tmp/out.kmz -w '%{http_code}\n' -H "x-auth-token: $TOKEN" \
  "http://localhost:8080/wayline/api/v1/workspaces/$WS/waylines/$WID/url"
```

A `200` with bytes matching the seeded KMZ means the device-facing object path
works end to end. **Reset `FIELDHUB_MINIO_DEVICE_ENDPOINT` to the 10.0.2.2
default before the real run.**

## Step C — seed the fleet matrix

Register one wayline per model so you can confirm Pilot filters/renders each.
Keys are `domain-type-subtype` (`dji-cloud-api-reference.md` §6):

```bash
./seed-wayline.sh exports/m300.kmz "M300 inspection"  0-60-0 1-53-0
./seed-wayline.sh exports/m350.kmz "M350 inspection"  0-89-0 1-53-0
./seed-wayline.sh exports/m3e.kmz  "M3E inspection"   0-77-0
./seed-wayline.sh exports/m4t.kmz  "M4T inspection"   0-99-1   # the enum the demo rejected
```

## Step D — point BlueStacks at fieldhub

1. In BlueStacks, open **DJI Pilot 2 → Cloud Service** (third-party platform).
2. Enter the platform URL: `http://10.0.2.2:8080`.
3. Confirm `10.0.2.2:8080` is reachable from inside BlueStacks first (a browser
   in the emulator should load the connect page).

## Step E — run V1 / V2 and record findings

Work down the connect page and the route library, watching the nginx log. For
each, record the verdict in the issue tracker (monorepo #812).

**Result (2026-06-14): the native Cloud Service flow DID inject `window.djiBridge`
and the full connect chain ran against fieldhub.** The earlier "no bridge in
BlueStacks" worry applied to loading the demo's web console in a webview, not to
this native flow. The connect page (UA `dji-open-platform`) loaded, license
verified, login succeeded, and `api`/`media`/`mission` loaded. The one gap was
`mission` — the connect page didn't load it, so Pilot never queried `/wayline`;
adding `platformLoadComponent("mission", {})` fixed it and routes appeared under
a **Cloud** tab. (Hence the broker in the stack — the demo gates `mission`
behind MQTT, though our ungated load syncs over HTTP regardless.)

Validate (all confirmed 2026-06-14):

- [ ] Each seeded wayline appears in Pilot's Flight Route Library.
- [ ] Pilot filters by connected/selected aircraft model — does the M4T
      (`0-99-1`) wayline show, given our dictionary seeds it (vs the demo that
      rejected enum 99)?
- [ ] Name search, favorites, pagination behave.
- [ ] Selecting a wayline downloads it: nginx log shows
      `GET /wayline/.../url` → `307` → `GET /tarmacview-waylines/...` → `200`.
- [ ] Pilot **opens** the downloaded KMZ (valid `wpmz/template.kml` +
      `waylines.wpml`) for each fleet model — catches exporter × dictionary ×
      import bugs (uppercase `UTF-8`, unknown enums, forbidden name chars).

### Capture list (fold deltas back into `dji-cloud-api-reference.md`)

- Does `window.djiBridge` exist in BlueStacks Pilot 2? (settles the §5 / §9 note)
- Every endpoint+status Pilot hits, in order (from the nginx log).
- Any envelope our hub returns that Pilot rejects (shape/field mismatch vs demo).
- Whether `http://` is accepted as the platform URL, or Pilot demands `https`
  (if so, switch to the TLS variant — see below).
- Route-list refresh UX (auto vs manual pull-to-refresh) — open V2 question.

## Decision points / fallbacks

- **Pilot refuses `http://`** → run a TLS variant: `gen-certs.sh 10.0.2.2`
  (cert with a `10.0.2.2` SAN), have nginx terminate TLS on 8080 with it, and
  install the local CA inside BlueStacks. Adds the V5 trust step early.
- **nginx single-port is fussy** → BlueStacks can also reach individual host
  ports as `10.0.2.2:<port>`; as a fallback publish fieldhub `:8000` and MinIO
  `:9000` directly and set `FIELDHUB_MINIO_DEVICE_ENDPOINT=http://10.0.2.2:9000`,
  platform URL `http://10.0.2.2:8000`. The single nginx port is the spike-proven
  default; this is the escape hatch.
- **Bucket-name mismatch** → `nginx.conf` hardcodes `tarmacview-waylines` /
  `tarmacview-media`; keep the MinIO bucket settings at their defaults or update
  both.

## Teardown

```bash
docker compose --env-file .env.emulator -f docker-compose.emulator.yml down -v
```
