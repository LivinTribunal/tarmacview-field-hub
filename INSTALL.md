# Install & Connect — TarmacView Field Hub

How to bring the field stack up and get TarmacView's **Send to drone** panel off
*"not connected"*. For architecture and flows see `docs/specs/FIELD-HUB.md`; for
the deployment topology see
`docs/adr/2026-06-14-tarmacview-fieldhub-integration-topology.md`.

## What "not connected" means

The Send-to-drone panel reads its state from the backend's
`GET /api/v1/field-link/status`, which proxies the hub's
`GET /internal/api/v1/status` — authenticated with the `X-Hub-Secret` shared
secret and reaching the hub at `FIELDHUB_URL`. The panel shows **not connected**
whenever any link in that chain is missing:

1. `FIELDHUB_URL` / `FIELDHUB_SHARED_SECRET` are empty (the default) — the backend
   reports "no hub" with no network call.
2. They are set, but the hub container isn't running (or has no TLS certs).
3. The hub is up, but no DJI device (RC) has bound / is online yet — the hub is
   connected, but there is no drone to talk to.

Layers 1–2 are this install. Layer 3 is RC provisioning (last section).

## Which repo to run from

- **Full stack** (backend + frontend + hub + EMQX + MinIO) builds from the
  **[monorepo](https://github.com/LivinTribunal/drone-mission-planning-module)**.
  The TarmacView UI you're looking at runs from there, so the connected setup is
  driven from the monorepo's `docker-compose.yml` with the `field` profile.
- **This repo** builds only the `fieldhub` container (`./fieldhub` context); its
  `docker-compose.yml` lists `backend`/`frontend` as references whose build
  contexts are intentionally absent. Use this repo to run/develop the hub on its
  own (hub + EMQX + MinIO over postgres) — handy for testing the hub against DJI
  Pilot 2 directly, but it does not start the TarmacView UI.

The cert tool (`scripts/field-hub/gen-certs.sh`) lives here and is canonical —
the monorepo launcher reuses it.

## Prerequisites

- Docker + Docker Compose.
- `openssl` on PATH (for `gen-certs.sh`).
- The laptop's **static LAN IP** on the field/travel router (e.g.
  `192.168.8.100`) — DJI Pilot 2 on the RC connects to that IP, and every
  device-facing address derives from it.
- A DJI developer **Cloud API application** (App ID / Key / License) from
  developer.dji.com, bound to the platform.

## Steps

Run these from the repo root that owns the full stack (the **monorepo** for the
connected UI; **this repo** for hub-only). The commands are identical; only the
`.env.docker` wiring of `FIELDHUB_URL`/`FIELDHUB_CA` differs (see step 2).

### 1. Generate TLS material (once per LAN IP)

The hub serves HTTPS and EMQX serves MQTTS — DJI Pilot 2 requires both. Pass the
laptop's LAN IP so the certs carry it as a SAN (RCs verify against it):

```bash
scripts/field-hub/gen-certs.sh 192.168.8.100
```

Writes a git-ignored `certs/` tree: `certs/ca/ca.crt` (the local CA — install
this on each RC), plus per-service certs under `certs/fieldhub/`, `certs/emqx/`,
`certs/minio/`. The CA is created once and reused; rerun the script after the
LAN IP changes to refresh the service certs (it keeps the existing CA).

### 2. Configure `.env.docker`

Copy the example and fill in the field values:

```bash
cp .env.docker.example .env.docker
```

The keys that take the panel from *not connected* to *connected* — backend↔hub
wiring (set these to the **same** values the backend and hub both read):

```ini
# backend -> hub proxy (compose DNS name + the CA mounted into the backend)
FIELDHUB_URL=https://fieldhub:8443
FIELDHUB_CA=/certs/fieldhub/ca.crt

# shared secret authenticating backend <-> hub calls (X-Hub-Secret).
# empty disables the integration on BOTH sides. generate one:
#   openssl rand -hex 32
FIELDHUB_SHARED_SECRET=<random-hex>

# the laptop's LAN IP - the single host every device-facing address
# (mqtt addr, STS endpoint, presigned wayline URLs) derives from
FIELDHUB_PUBLIC_HOST=192.168.8.100
```

For a usable session you also want (see `.env.docker.example` /
`fieldhub/README.md` for the full table):

```ini
# pilot login - login is rejected while this is empty
FIELDHUB_PILOT_USERNAME=pilot
FIELDHUB_PILOT_PASSWORD=<pilot-password>

# DJI Cloud API app the Pilot connect page verifies via JSBridge
FIELDHUB_DJI_APP_ID=<app-id>
FIELDHUB_DJI_APP_KEY=<app-key>
FIELDHUB_DJI_APP_LICENSE=<app-license>

# object store (LAN defaults are fine; override for the field)
MINIO_ROOT_USER=tarmacview
MINIO_ROOT_PASSWORD=<minio-password>

# override the dev defaults in the field
JWT_SECRET=<random-hex>           # backend JWT signing (required by compose)
FIELDHUB_JWT_SECRET=<random-hex>  # hub x-auth-token signing
```

> Hub-only (this repo): leave `FIELDHUB_URL`/`FIELDHUB_CA` empty — there is no
> backend here to proxy. Everything else above still applies.

### 3. Bring up the stack

```bash
docker compose --profile field up -d --build
```

`--profile field` adds `fieldhub`, `emqx`, and `minio`. Without it those three
stay down and the panel reports no hub. If the certs are missing, fieldhub exits
with a clear error and EMQX fails its SSL listener — run step 1, then retry.

### 4. Verify

Hub health (CA-signed cert, so verify against the local CA):

```bash
curl --cacert certs/ca/ca.crt https://localhost:8443/healthz
# {"status": "ok", "service": "fieldhub", "broker": true, "object_store": true}
```

`status: degraded` (still HTTP 200) means EMQX or MinIO is unreachable — the
`broker` / `object_store` flags say which.

The exact snapshot the backend consumes (needs the shared secret):

```bash
curl --cacert certs/ca/ca.crt \
  -H "X-Hub-Secret: $FIELDHUB_SHARED_SECRET" \
  https://localhost:8443/internal/api/v1/status
# {"broker_connected": ..., "devices": [...]}
```

Then reload the TarmacView UI — Send-to-drone should report connected. (It still
shows no *devices* until an RC is provisioned and online.)

## Provision DJI Pilot 2 / the RC (gets a drone online)

Once the panel is connected, bind the controller so a drone actually appears:

1. **Install the CA on the RC.** Copy `certs/ca/ca.crt` to the controller and
   install it as a trusted certificate (Pilot needs it to verify the hub's HTTPS
   and EMQX's MQTTS). Regenerating the CA invalidates already-provisioned RCs.
2. **Connect the RC to the field WiFi** (same LAN as the laptop's
   `FIELDHUB_PUBLIC_HOST`).
3. **Open the connect page in DJI Pilot 2:** browse to
   `https://192.168.8.100:8443/` (the hub's `GET /`). The page verifies the DJI
   app credentials via JSBridge, then prompts for the pilot login
   (`FIELDHUB_PILOT_USERNAME` / `FIELDHUB_PILOT_PASSWORD`) and loads the
   `api` / `thing` / `media` / `mission` modules. In a normal browser it
   degrades to an "open in DJI Pilot 2" note.
4. The device binds and appears in the field-link devices list; dispatched
   missions show up in Pilot's Cloud route library, and media auto-uploads after
   landing.

## Troubleshooting "not connected"

- **Empty `FIELDHUB_URL` or `FIELDHUB_SHARED_SECRET`** → backend reports no hub
  with no network call. Most common cause. Set both in `.env.docker` and restart
  the backend.
- **Secret mismatch** → the hub's internal endpoints reject the call. The backend
  and hub must read the *same* `FIELDHUB_SHARED_SECRET` (both come from
  `.env.docker`).
- **Forgot `--profile field`** → hub/EMQX/MinIO never start. Re-run step 3.
- **Certs missing / LAN IP changed** → fieldhub won't start, or the RC fails TLS.
  Re-run `gen-certs.sh <ip>`, then `up -d` again.
- **`/healthz` returns `degraded`** → broker or object store down; check the
  `broker` / `object_store` flags and the `emqx` / `minio` containers.
- **Connected but no devices** → that's RC provisioning, not the hub link. See
  the section above.
- Inspect: `docker compose --profile field logs -f fieldhub`. The hub's startup
  log echoes the resolved device-facing addresses and warns if any still points
  at a compose/loopback host instead of `FIELDHUB_PUBLIC_HOST`.

Teardown / reset: `scripts/field-hub/stop-field.sh` (`--wipe` also drops the
`emqx-data` / `minio-data` / shared `pgdata` volumes).
