# DJI Cloud API Reference — fieldhub implementation contract

The protocol surface the `fieldhub` service implements so DJI Pilot 2 can use
TarmacView as its "third-party cloud platform" over the local network. This is
the **single protocol source of truth for implementation work** — pipeline
agents have no web access; everything needed for the field-hub issues is
inline here.

**Provenance.** Extracted from the DJI Cloud API Demo v1.10 source (the
reference implementation Pilot 2 ships against; archived locally in the
`field-hub-spike/` workspace on the field laptop) and cross-checked against
the public Cloud-API-Doc. A live demo stack validated the platform side; a
2026-06-13 **BlueStacks spike** then drove real DJI Pilot 2 against it,
confirming the connect chain and the full wayline dispatch round-trip in
emulation (§9). **Hardware verdicts are still pending** — items marked
⚠ UNVERIFIED get confirmed or corrected on the real RC Plus 2 / RC Plus;
deltas are folded back into this doc.

Companion docs: architecture `FIELD-HUB.md` · KMZ/WPML payload format
`dji-wpml-reference.md`.

## 1. Connection bootstrap (Pilot 2 → platform)

1. Operator opens DJI Pilot 2 → *Cloud Service* → enters the platform URL
   (e.g. `https://192.168.8.100:8443`). Pilot loads that page in its
   embedded webview.
2. The page (served by the hub) drives Pilot through `window.djiBridge`
   (JSBridge): it verifies the **app credentials** (`appId`, `appKey`,
   `appLicense` — the DJI developer app bound to the platform; license
   verification requires internet at least once ⚠ UNVERIFIED how long the
   verification caches offline).
3. The page calls the platform's **login** endpoint with operator
   credentials; the response carries everything Pilot needs to attach:
   workspace, JWT for HTTP, and MQTT address + per-user MQTT credentials.
4. The page loads JSBridge modules (`api` with the host + token, `thing`
   with the MQTT params) — Pilot's *thing* module connects to the broker
   and publishes its device topology (`update_topo`). The platform replies;
   the RC and (when powered) the aircraft are now online.
5. All subsequent traffic: HTTPS calls Pilot-initiated (wayline lists, media
   negotiation) + MQTT both ways (status, OSD, events, requests).

## 2. HTTP conventions

- Every response uses the demo's envelope (`HttpResultResponse`):

  ```json
  {"code": 0, "message": "success", "data": { ... }}
  ```

  `code: 0` = success; non-zero = failure with `message`. Pilot checks the
  envelope, not HTTP status alone.
- After login, Pilot sends the JWT on every request in the
  **`x-auth-token`** header.
- Module prefixes (all under `/{prefix}/api/v1`):

  | module | prefix | used by fieldhub for |
  |---|---|---|
  | manage | `/manage/api/v1` | login, workspace, devices/binding |
  | wayline | `/wayline/api/v1` | route library sync + dispatch |
  | media | `/media/api/v1` | fast-upload negotiation + callbacks |
  | storage | `/storage/api/v1` | temporary object-store credentials (STS) |
  | tsa | `/manage/api/v1` (impl) | device topology for situational awareness |
  | map, control | `/map`, `/control` | **out of scope** for fieldhub v1 |

- Paging convention on list endpoints: `page` (1-based), `page_size`;
  list payloads come wrapped as `{"list": [...], "pagination": {"page": n,
  "page_size": n, "total": n}}`.

## 3. Endpoints the hub must serve

### 3.1 manage — login & devices

| method + path | purpose |
|---|---|
| `POST /manage/api/v1/login` | operator/Pilot login. Body `{username, password, flag}` (`flag` distinguishes web vs Pilot client). |
| `POST /manage/api/v1/token/refresh` | JWT refresh. |
| `GET /manage/api/v1/workspaces/current` | workspace of the authenticated user (id, name). |
| `GET /manage/api/v1/devices/{workspace_id}/devices` | all devices in the workspace. |
| `GET /manage/api/v1/devices/{workspace_id}/devices/{device_sn}` | one device. |
| `GET /manage/api/v1/devices/{workspace_id}/devices/bound` | bound devices (paged). |
| `POST /manage/api/v1/devices/{device_sn}/binding` | bind a device to the workspace. |
| `DELETE /manage/api/v1/devices/{device_sn}/unbinding` | unbind. |
| `PUT /manage/api/v1/devices/{workspace_id}/devices/{device_sn}` | rename etc. |

Login response `data` (demo `UserDTO`) — the contract that attaches Pilot:

```json
{
  "user_id": "...", "username": "...", "user_type": 2,
  "workspace_id": "...",
  "access_token": "<jwt for x-auth-token>",
  "mqtt_addr": "tcp://192.168.8.100:1883",
  "mqtt_username": "...", "mqtt_password": "..."
}
```

Notes:
- `mqtt_addr` format is `<scheme>://<host>:<port>`. The demo uses `tcp://`;
  for the fieldhub the broker is MQTTS — scheme/port for TLS
  (`ssl://host:8883`) ⚠ UNVERIFIED on hardware, confirm Pilot accepts it
  with the locally-installed CA.
- The address must be reachable **from the RC on the WiFi** (LAN IP, never
  a compose hostname). If the hub itself also connects to the broker, it
  must use the compose-internal address — never reuse the device-facing one
  (Docker Desktop does not hairpin container→host-LAN-IP traffic; found
  empirically during the spike).

### 3.2 wayline — route library (dispatch leg)

| method + path | purpose |
|---|---|
| `GET /wayline/api/v1/workspaces/{workspace_id}/waylines` | paged route list Pilot syncs from. Query: `page`, `page_size`, `order_by`, `favorited`, `template_type`, `action_type`, `drone_model_keys`, `payload_model_key`, `key` (name search). |
| `GET /wayline/api/v1/workspaces/{workspace_id}/waylines/{wayline_id}/url` | download of the KMZ — the demo answers with a redirect to a presigned object-store URL; the presigned host must be the LAN-reachable MinIO address. |
| `GET /wayline/api/v1/workspaces/{workspace_id}/waylines/duplicate-names` | name-collision check (`name` query param, returns colliding names). |
| `POST /wayline/api/v1/workspaces/{workspace_id}/upload-callback` | Pilot reports a wayline *it* uploaded to object storage (RC→cloud direction; lets operators push routes from Pilot). |
| `POST /wayline/api/v1/workspaces/{workspace_id}/waylines/file/upload` | direct multipart upload (web UI path; TarmacView dispatch can reuse it server-side). |
| `POST /wayline/api/v1/workspaces/{workspace_id}/favorites` + `DELETE` | mark/unmark favorites (ids in body). |
| `DELETE /wayline/api/v1/workspaces/{workspace_id}/waylines/{wayline_id}` | delete a wayline. |

Wayline list item (demo `GetWaylineListResponse`) — what Pilot renders in
its route library:

```json
{
  "id": "<uuid>", "name": "RWY22 PAPI inspection",
  "drone_model_key": "0-89-0",
  "payload_model_keys": ["1-53-0"],
  "template_types": [0],
  "object_key": "wayline/<file>.kmz",
  "sign": "<md5 of the kmz>",
  "favorited": false, "username": "...",
  "create_time": 1733700000000, "update_time": 1733700000000
}
```

- `drone_model_key` / `payload_model_keys` are `domain-type-subtype` strings
  (see §6) — Pilot **filters the list by the connected aircraft**, so a
  wayline whose `drone_model_key` doesn't match the connected drone may not
  appear. Populate from the mission's drone profile.
- `template_types`: 0 = waypoint. `sign` is the file checksum (md5) ⚠
  UNVERIFIED whether Pilot enforces it; the demo computes it on upload.
- The KMZ itself must contain `wpmz/template.kml` (+ `waylines.wpml`) — the
  TarmacView exporter already emits both (`dji-wpml-reference.md`).
- **Import is strict** — `template.kml` must declare uppercase
  `encoding="UTF-8"`, drone/payload enums must be in the device dictionary
  (§6), and the wayline name (derived from the filename) must avoid
  `_ . / \ < > : " | ? *`. See §9 for the concrete failures the spike hit.
- The hub defensively sanitizes the wayline name on register (the single
  dispatch chokepoint): forbidden chars collapse to a space, an all-forbidden
  name falls back to `wayline`, and `duplicate-names` normalizes its query the
  same way so the collision check matches the stored form. The exporter still
  emitting a clean filename (the monorepo half) stays the primary fix.
- Pilot triggers the sync itself (pull). Refresh cadence / manual
  pull-to-refresh behavior in the route list UI ⚠ UNVERIFIED (V2).

### 3.3 storage + media — media return leg

| method + path | purpose |
|---|---|
| `POST /storage/api/v1/workspaces/{workspace_id}/sts` | temporary object-store credentials for direct upload. |
| `POST /media/api/v1/workspaces/{workspace_id}/fast-upload` | fingerprint pre-check: Pilot asks "do you already have this file?" before uploading. |
| `POST /media/api/v1/workspaces/{workspace_id}/files/tiny-fingerprints` | batch variant — Pilot sends the tiny-fingerprint list, platform answers which already exist. |
| `POST /media/api/v1/workspaces/{workspace_id}/upload-callback` | Pilot reports a completed upload with full file metadata — **this is the hub→backend media-event trigger**. |
| `POST /media/api/v1/workspaces/{workspace_id}/group-upload-callback` | folder/group variant of the callback. |
| `GET /media/api/v1/files/{workspace_id}/files` | uploaded-files list (paged; web UI). |
| `GET /media/api/v1/files/{workspace_id}/file/{file_id}/url` | presigned download URL for a stored file. |

STS response `data` (demo `StsCredentialsResponse`):

```json
{
  "bucket": "cloud-bucket",
  "endpoint": "http://192.168.8.100:9000",
  "provider": "minio",
  "region": "us-east-1",
  "object_key_prefix": "media",
  "credentials": {
    "access_key_id": "...", "access_key_secret": "...",
    "security_token": "...", "expire": 3600
  }
}
```

- `provider` ∈ `minio | aws | ali` (`OssTypeEnum`) — Pilot picks its S3
  client accordingly. MinIO works via its AssumeRole STS API (validated
  against the demo; on-hardware confirmation is V4).
- `endpoint` must be the **LAN-reachable** MinIO address — Pilot uploads
  directly to it with the temporary credentials.
- Devices may also request the same config over MQTT (`storage_config_get`
  on the requests topic, §4) — implement both paths against one source.

Upload callback body (demo `MediaUploadCallbackRequest`): `{fingerprint,
name, path, object_key, sub_file_type, metadata, ext}` where `metadata`
(demo `MediaFileMetadata`) is the matching input for TarmacView:

```json
{
  "absolute_altitude": 423.6,
  "relative_altitude": 38.2,
  "gimbal_yaw_degree": -87.5,
  "created_time": "2026-06-09T14:21:33+02:00",
  "shoot_position": {"lat": 48.17, "lng": 17.21}
}
```

`ext` (`MediaFileExtension`) carries drone SN / payload info and the
`fileGroupId`/`flightId` linkage when present. Persist the callback payload
verbatim alongside the derived `drone_media_file` row — capture time and
shoot position drive mission matching; never substitute server receive time.

### 3.4 tsa — topology (situational awareness)

`GET /manage/api/v1/workspaces/{workspace_id}/devices/topologies` — Pilot's
TSA module fetches the device tree (gateways + aircraft) to render what's
online. Serve it from the hub's device registry; it is also a convenient
backing source for TarmacView's field-link status endpoint.

## 4. MQTT contract

Topic families (from the SDK's `TopicConst`; `{sn}` = device serial,
gateway = the RC):

| topic | direction | purpose |
|---|---|---|
| `sys/product/{gateway_sn}/status` | device → cloud | lifecycle: `update_topo` on connect/topology change (aircraft attached/detached, going offline) |
| `sys/product/{gateway_sn}/status_reply` | cloud → device | ack: `{"method": "update_topo", "data": {"result": 0}}` |
| `thing/product/{sn}/osd` | device → cloud | periodic telemetry (position, battery, attitude) |
| `thing/product/{sn}/state` | device → cloud | sparse state changes (firmware, payload, live-capacity) |
| `thing/product/{sn}/services` + `_reply` | cloud → device | commands the cloud invokes on the device |
| `thing/product/{sn}/events` + `_reply` | device → cloud | device-initiated notifications (file upload progress, HMS); some demand a reply with `result` |
| `thing/product/{sn}/requests` + `_reply` | device → cloud | device asks the cloud for data — incl. `airport_organization_get`/`airport_organization_bind` (binding) and **`storage_config_get`** (STS for media/logs) |
| `thing/product/{sn}/property/set` | cloud → device | property writes |
| `thing/product/{sn}/drc/up` / `/down` | both | DRC live-control link — **out of scope** for fieldhub v1 |

Message envelope, both directions (SDK `CommonTopicRequest/Response`):

```json
{"tid": "<uuid per transaction>", "bid": "<uuid per business flow>",
 "timestamp": 1733700000000, "method": "update_topo", "data": { ... }}
```

Replies echo `tid`/`bid` and return `{"result": 0}` inside `data` (0 = ok).
`method` appears on methodful topics (status/services/events/requests).

Behavioral notes:
- The hub subscribes at minimum to `sys/product/+/status` and
  `thing/product/+/requests` at startup (the demo's bootstrap set), plus
  `thing/product/+/osd|state|events` for devices it knows.
- **Online/offline**: a gateway is online after `update_topo`; the aircraft
  appears as a sub-device in the topology payload. Offline = MQTT
  disconnect (track broker client events and/or MQTT last-will) or an
  `update_topo` without the sub-device. Demo keeps device state in Redis
  with a TTL refreshed by OSD traffic — the fieldhub equivalent must expire
  stale devices.
- Per-user MQTT credentials come from login (§3.1); the broker currently
  accepts TLS-anonymous clients (skeleton); per-device credentials land
  with the binding slice.

## 5. Pilot webview / JSBridge (connect page)

Implemented: the hub serves its own connect page at `GET /` (plain HTML +
vanilla JS under `fieldhub/app/static/`, no build step, all assets local —
the field network has no internet). `GET /pilot/config` supplies the page's
bootstrap as an envelope — the DJI app credentials from hub settings
(`FIELDHUB_DJI_APP_ID` / `_DJI_APP_KEY` / `_DJI_APP_LICENSE`; never
hardcoded in the page), the device-facing `mqtt_addr`, and the
platform/workspace identity:

```json
{"app_id": "...", "app_key": "...", "app_license": "...",
 "mqtt_addr": "ssl://192.168.8.100:8883",
 "platform_name": "TarmacView Field Hub",
 "workspace_name": "TarmacView Field", "workspace_desc": ""}
```

Unconfigured credentials → non-zero envelope code and the page stops at the
license step with the message. The endpoint is unauthenticated by design —
the page needs it before login; LAN-only surface, same posture as login.

Call sequence (`pilot-connect.js`; each step gates the next, the first
failure stops the flow and renders the error in plain text on the status
panel):

1. `GET /pilot/config` → bootstrap above.
2. `platformVerifyLicense(appId, appKey, appLicense)`, then
   `platformIsVerified()`.
3. Login - **resume or prompt**. The page caches `access_token` in
   `localStorage`; on load, when a token is cached it tries `POST
   /manage/api/v1/token/refresh` (`x-auth-token`: cached) first, gets a fresh
   one, and skips the form ("resuming session"). A stale or expired token is
   dropped and the operator login form shows as before → `POST
   /manage/api/v1/login` `{username, password, flag: 2}`. Either path yields
   `access_token`, `mqtt_*`, `workspace_id` (§3.1) and the page re-caches the
   token. Refresh both validates and extends, so a webview reload (returning
   from the route library) no longer forces a re-login.
4. `platformLoadComponent("api", {host: <page origin>, token})`.
5. `window.thingConnectCallback` registered (callbacks are global function
   *names* Pilot invokes), then `platformLoadComponent("thing", {host:
   mqtt_addr, username, password, connectCallback:
   "thingConnectCallback"})`.
6. `platformSetWorkspaceId(workspace_id)` +
   `platformSetInformation(platform_name, workspace_name, workspace_desc)`.
7. One-shot `thingGetConnectState()` to catch an already-attached link;
   afterwards the callback drives the MQTT row on the status panel.
8. `platformLoadComponent("media", {autoUploadPhoto: true,
   autoUploadPhotoType: 0, autoUploadVideo: true})` — originals (not
   thumbnails) + video auto-upload on, per the media-return design
   (`mediaSetAutoUploadVideo` is covered by the load param).
9. `platformLoadComponent("mission", {})` — the wayline/route-library cloud
   sync. Empty params; the HTTP host + token come from the `api` module.
   **Required** — without it Pilot never queries `/wayline/...` and no cloud
   routes appear (see below).

The form button reads **Connect**; after connect the page shows "Connected as
&lt;username&gt;" next to a **Disconnect** button. Disconnect is a real
teardown: the page unloads the loaded JSBridge components
(`mission`/`media`/`thing`/`api`, reverse load order via
`platformUnloadComponent`) so Pilot drops the cloud-platform link, then clears
the cached token and returns to the connect form.

Bridge return parsing (`parseBridgeReturn`): string returns are JSON
`{code, message, data}` envelopes — `code: 0` = ok, `data` is sometimes a
JSON-encoded string itself (`"true"`/`"false"`); plain `true`/`false` and
void returns also occur (void = success, no error signal). An envelope with
`code: 0` but `data: false` counts as failure.

Without `window.djiBridge` (plain browser) the page degrades to an "open
this page in DJI Pilot 2" banner — also how the node-driven tests exercise
the flow (`fieldhub/tests/test_pilot_page.py`).

The `mission` component is **required and confirmed** (2026-06-14 BlueStacks
run against `fieldhub`, §9): with only `api`/`thing`/`media` loaded Pilot's
Flight Route Library stayed empty and never called `/wayline/...`; adding
`platformLoadComponent("mission", {})` made the routes appear under a **Cloud**
tab and Pilot then synced + downloaded over HTTP. It works **ungated by MQTT**
(synced with the `thing` link disconnected) — the demo loads it inside the
MQTT connect callback, but the wayline sync itself is pure HTTP via the `api`
module. The demo's wayline list call carries `file_type=5` and
`order_by=update_time desc` (the hub ignores `file_type` and still returns the
route); `GET .../waylines/{id}/url` answers a **307** redirect the native
`okhttp` client follows.

Still not loaded: `tsa`, `ws`. Parameter dictionary for the unused modules:
demo `front_page/src/api/pilot-bridge.ts` (archived in the spike workspace).

## 6. Device enums (product dictionary)

`domain-type-subtype`; domain: 0 = aircraft, 1 = payload, 2 = RC, 3 = dock.

| device | key | status |
|---|---|---|
| Matrice 300 RTK | `0-60-0` | from demo SQL |
| Matrice 350 RTK | `0-89-0` | from demo SQL |
| Mavic 3 Enterprise (M3E) | `0-77-0` | from demo SQL |
| Mavic 3T | `0-77-1` | from demo SQL |
| Matrice 30 / 30T | `0-67-0` / `0-67-1` | from demo SQL |
| DJI RC Plus | `2-119-0` | from demo SQL |
| DJI RC Pro Enterprise | `2-144-0` | Cloud-API-Doc |
| **Matrice 4T** | `0-99-1` | WPML `droneEnumValue` 99 sub 1 **confirmed** from a TarmacView export (spike). Note: demo v1.10's dictionary predates the M4 series and *rejects* enum 99 — the hub must seed this key itself. RC-topology key still ⚠ pending hardware |
| **DJI RC Plus 2** | ⚠ UNKNOWN | capture from the live `update_topo` payload when the hardware arrives (V1/V2) |

These keys appear in `update_topo` payloads, wayline `drone_model_key`
filtering, and OSD routing — the hub must hold a device dictionary keyed by
them (seed from this table; unknown devices must degrade gracefully, not
crash binding).

## 7. Provisioning & field constraints

- **TLS**: Pilot requires the platform URL over HTTPS and the broker over
  MQTTS in production posture; the local CA from `gen-certs.sh` must be
  installed on each RC once (Android CA store or Pilot cert import — exact
  path is V5 ⚠). Cert SANs must include the laptop's LAN IP.
- **One-time online**: DJI app-license verification needs internet at least
  once per RC (V1 ⚠ — exact recheck cadence unknown). Field operation after
  provisioning must be fully offline.
- **NTP**: the demo configures an NTP server hint for devices
  (`ntp.server.host`); offline deployments should point it at the field
  laptop or omit it — flag for V1 testing.
- **Addressing**: every URL/address handed to Pilot (platform URL,
  `mqtt_addr`, STS `endpoint`, presigned URLs) must use the laptop's static
  LAN IP on the travel router; compose-internal hostnames must never leak
  into device-facing payloads. The hub single-sources this off
  `FIELDHUB_PUBLIC_HOST` (the laptop's LAN IP) - `mqtt_addr`, the STS
  `endpoint`, and presigned URLs all derive from it, with per-service
  overrides kept for a reverse proxy. The startup log echoes the resolved
  device-facing addresses and warns when one still resolves to a
  compose/loopback host (`localhost`/`minio`/`emqx`/…).

## 8. Scope map for the implementation issues

| issue | implements from this doc |
|---|---|
| binding + link status | §1, §3.1, §3.4, §4 (status/update_topo, online/offline), §5, §6 |
| mission dispatch | §3.2 (list, url, duplicate-names, favorites), KMZ contract via `dji-wpml-reference.md` |
| media return | §3.3 (sts, fast-upload, tiny-fingerprints, upload-callback), §4 `storage_config_get` |
| explicitly out of scope v1 | livestream, DRC live control, HMS, firmware/OTA, log upload, map elements, dock-only flight-task execution |

## 9. Phase 0 emulator validation (BlueStacks spike, 2026-06-13)

DJI Pilot 2 running in BlueStacks (Android `SM-G998B`) was pointed at a live
DJI Cloud API Demo v1.10 stack on the field laptop — a hardware-less precursor
to the RC verdicts. This **confirms the protocol/connectivity chain and the
full V2 dispatch round-trip**; it does *not* replace the on-hardware V1–V5
verdicts (MQTT device-online, media upload, STS, TLS, and native JSBridge all
still need the real RC).

### Confirmed
- **Connection chain (V1, partial).** Pilot 2 → platform login → workspace →
  authenticated `/manage` API, end to end over the local network.
- **Mission dispatch (V2), full round-trip.** A TarmacView mission KMZ →
  uploaded to the wayline library → stored in MinIO → listed in Pilot 2's
  Flight Route Library (M350 RTK / H20T) → **downloaded by Pilot** (`GET
  .../url` → 302 → object `HTTP 200`, valid `wpmz/template.kml` +
  `waylines.wpml`).

### Confirmed — 2026-06-14, against `fieldhub` (not the demo)

A second BlueStacks run pointed real Pilot 2 at the **`fieldhub` service** over
plain HTTP (`emulator/` run-kit). This is the first time our own implementation
met Pilot 2; the demo proved the protocol, this proves the code.

- **Connect chain** end to end against fieldhub: license verify, login
  (`flag` honored), `api`, `media` (issued STS to Pilot's media module), and
  `mission`.
- **Wayline sync (V2)** via the `mission` module (the missing piece, §5) — the
  route appeared in Pilot's **Cloud** tab and synced over HTTP.
- **KMZ download** — `GET .../url` → **307** → presigned `…/{id}.kmz` through
  the nginx proxy → `HTTP 200`, validating the OSS split-horizon + SigV4-through-
  proxy path with a real `okhttp` client.
- **M4T end to end** — a real TarmacView **M4T** export (`droneEnumValue=99`,
  `encoding='UTF-8'`) registered, synced, downloaded (3817 B), and **opened in
  Pilot with waypoints**. Real Pilot 2 accepts the M4-series enum the demo
  v1.10 dictionary rejected.

Still hardware-only (RC Plus 2): MQTT device-online/topology (the `thing` link
stayed disconnected in emulation and wayline sync did not need it), media
upload (V3), STS via Pilot's real S3 upload (V4), TLS acceptance (V5), and the
RC Plus 2 topology key (§6).

### Protocol constraints the implementation must honor
1. **KMZ import is strict** (demo `WaylineFileServiceImpl.validKmzFile`; real
   DJI tooling is at least as strict):
   - `template.kml` XML declaration must be **uppercase** `encoding="UTF-8"`.
     lxml emits lowercase `utf-8` → rejected ("file encoding format is
     incorrect"). The TarmacView exporter must emit uppercase.
   - `wpml:droneEnumValue` / `payloadEnumValue` must be in the platform's
     device dictionary (§6). A TarmacView M4-series export wrote
     `droneEnumValue=99`, which demo v1.10 doesn't know → rejected; the hub's
     dictionary must include every fleet model (M4T = `0-99-1`).
   - The wayline **name** (derived from the KMZ filename) cannot contain
     `_ . / \ < > : " | ? *` — an underscore broke the *list* endpoint for
     every wayline. Sanitize dispatched filenames.
2. **OSS split-horizon (the §3.1 / §3.3 / §7 addressing rule, made concrete).**
   The server reaches MinIO over the compose network (`minio:9000`); the
   device reaches it only over the LAN — no single literal address serves
   both. The hub must (a) issue presigned URLs / the STS `endpoint` with the
   **device-reachable** host, and (b) reach MinIO for its own put/stat over
   the **internal** address. Generating a presigned URL is pure local
   computation (no MinIO round-trip), so the device-facing host is set
   independently of where the server connects. SigV4 is computed over the
   signed `Host` header, so a reverse proxy in front of MinIO works only if it
   forwards that header **verbatim**.
3. **Pilot webview refuses non-`http(s)` schemes.** The demo web console's
   "Download" button fetches the file as a blob then triggers a `blob:`
   object-URL save, which Pilot rejects ("Only URL starting with http or https
   supported"). Anything the hub's own connect page hands Pilot for
   navigation/download must be a plain `http(s)` URL, never `blob:`/`data:`.

### Emulator-specific (testing only — not a hardware truth)
- **BlueStacks reaches the host only via the emulator alias `10.0.2.2`**
  (→ host loopback), never the host LAN IP — TCP to the LAN IP hairpins even
  though ICMP pings. A real RC on WiFi hits the laptop's LAN IP as a normal
  external client, so this is a BlueStacks artifact. For emulator testing,
  wire every device-facing address to `10.0.2.2` and route the API **and**
  MinIO through one reachable port (e.g. an nginx reverse proxy on `:8080`).
- **The demo web login form sends `flag=1`** (Web account) because BlueStacks'
  Pilot doesn't expose the native `window.djiBridge`; use the Web-type account
  there. On a real RC the native bridge runs and the connect page's operator
  login uses `flag=2` (§5 step 3) — an emulator login note, not a contract
  change.
- The demo runs on Apple Silicon with the **arm64 EMQX image** (amd64
  segfaults under emulation); MinIO is the object store.

Full run log: monorepo issue #812.

## 10. Sources

- DJI Cloud API Demo v1.10 source (sample + cloud-sdk modules) — archived
  in the spike workspace on the field laptop; the structures named above
  (`UserDTO`, `GetWaylineListResponse`, `StsCredentialsResponse`,
  `MediaUploadCallbackRequest`, `MediaFileMetadata`, `CommonTopicRequest`,
  `TopicConst`, `HttpResultResponse`) carry the exact field sets.
- Public Cloud-API-Doc (github.com/dji-sdk/Cloud-API-Doc) for the Pilot
  feature-set narrative and product-support matrix.
- Live validation against the demo stack on the field laptop (login, MQTT
  broker, MinIO bucket + STS path) — 2026-06-09/10.
