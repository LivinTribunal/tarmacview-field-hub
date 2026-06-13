# Field Hub

Local DJI Cloud API gateway for TarmacView. Runs on the field laptop as part
of the docker compose `field` profile, alongside EMQX (MQTT broker) and MinIO
(S3-compatible object store). DJI Pilot 2 on the remote controller connects to
this stack over the local WiFi for wireless mission dispatch and media return.

Architecture and flows: `docs/specs/FIELD-HUB.md`; protocol contract:
`docs/specs/dji-cloud-api-reference.md`. Implemented so far:

- `GET /healthz` — broker + object-store reachability probe.
- Cloud API access/binding surface (`/manage/api/v1/...`): login (`x-auth-token`
  JWTs, `HttpResultResponse` envelope), token refresh, current workspace,
  device list/detail/bound-list, bind/unbind/rename, and the TSA device
  topology tree.
- MQTT listener on `sys/product/+/status`, `thing/product/+/requests`, and
  `thing/product/+/osd|state`: `update_topo` keeps the device registry and
  online state current (acked on `status_reply`),
  `airport_organization_get`/`airport_organization_bind` answer the binding
  flow, and telemetry traffic refreshes the online TTL for known devices.
- Device registry persisted in the shared postgres under the `fieldhub`
  schema (created on startup, not Alembic-managed).
- `GET /internal/api/v1/status` — backend-facing snapshot (hub/broker/devices),
  gated by the `X-Hub-Secret` shared secret.
- Media return (`/storage/api/v1/...` + `/media/api/v1/...`): STS endpoint
  issuing temporary upload-scoped MinIO credentials (AssumeRole), fast-upload
  fingerprint pre-check + tiny-fingerprints batch, and the upload callbacks.
  Each arrival is persisted (`media_files`) and reported to the backend as
  `POST /api/v1/field-link/media-events` (shared-secret auth); a backend
  outage never blocks the Pilot ack — the file is already safe in MinIO and
  the report retries on the next callback repost. `storage_config_get` on the
  MQTT requests topic answers from the same payload source. Originals are
  never transcoded or modified.
- Wayline library (`/wayline/api/v1/...`, pilot-token gated): the paged route
  list Pilot 2 syncs from, presigned KMZ downloads, duplicate-names,
  favorites, delete — fed by the backend's mission dispatch through the
  shared-secret internal register endpoint, KMZ objects in MinIO.
- Pilot 2 connect page at `GET /` (plain HTML + vanilla JS under
  `app/static/`, no build step, no CDN assets): JSBridge license verify →
  operator login → `api`/`thing`/`media` module loads (auto-upload originals
  incl. video) with workspace id + platform info, rendered as a large-text
  status panel with live MQTT connection state. `GET /pilot/config` hands
  the page the DJI app credentials and the device-facing mqtt address; in a
  normal browser the page degrades to an "open this page in DJI Pilot 2"
  note. Call sequence: `docs/specs/dji-cloud-api-reference.md` §5.

## Run the field profile

TLS material must exist before the first start (fieldhub serves HTTPS, EMQX
serves MQTTS — DJI Pilot 2 requires both):

```bash
# 1. generate local CA + per-service certs (repeatable; pass the laptop's
#    static LAN IP on the travel router so RCs can verify the certs)
scripts/field-hub/gen-certs.sh 192.168.8.100

# 2. start the full stack incl. the field services
docker compose --profile field up -d --build

# 3. check the hub (CA-signed cert, so verify against the local CA)
curl --cacert certs/ca/ca.crt https://localhost:8443/healthz
```

Expected response:

```json
{"status": "ok", "service": "fieldhub", "broker": true, "object_store": true}
```

`status` is `degraded` (still HTTP 200) when EMQX or MinIO is unreachable;
the `broker` / `object_store` flags say which.

Plain `docker compose up` is unaffected — the `fieldhub`, `emqx`, and `minio`
services only start when the `field` profile is active.

### Certificates

`scripts/field-hub/gen-certs.sh` writes a git-ignored `certs/` tree at the
repo root: a local CA (`certs/ca/`) plus per-service server certs for
`fieldhub`, `emqx`, and `minio` (MinIO cert uses its expected
`public.crt`/`private.key` naming; the compose service still runs plain HTTP
for now and switches to TLS in a later slice). The CA is created once and
reused on later runs — it gets installed on each RC during provisioning, so
regenerating it would invalidate them. Service certs are regenerated on every
run, e.g. after the laptop's LAN IP changes.

If the field profile is started without certs, fieldhub exits with a clear
error and EMQX fails to load its SSL listener — run the script, then
`docker compose --profile field up -d` again.

## Configuration

All settings come from `FIELDHUB_*` env vars (see `app/core/config.py`):

| Variable | Default | Purpose |
|---|---|---|
| `FIELDHUB_MQTT_HOST` | `localhost` | EMQX host (healthz probe + hub-side listener) |
| `FIELDHUB_MQTT_PORT` | `8883` | EMQX MQTTS port |
| `FIELDHUB_MINIO_ENDPOINT` | `http://localhost:9000` | MinIO base URL (hub-side) |
| `FIELDHUB_MINIO_ACCESS_KEY` / `FIELDHUB_MINIO_SECRET_KEY` | empty | MinIO root credentials for STS AssumeRole + bucket ensure; STS answers an envelope error while unset |
| `FIELDHUB_MINIO_BUCKET` | `tarmacview-media` | media bucket, created on first STS issue |
| `FIELDHUB_MINIO_REGION` | `us-east-1` | region echoed in STS payloads |
| `FIELDHUB_MINIO_OBJECT_KEY_PREFIX` | `media` | object key prefix Pilot uploads under |
| `FIELDHUB_MINIO_STS_EXPIRY_S` | `3600` | temporary credential lifetime (MinIO floors AssumeRole at 1 h) |
| `FIELDHUB_MINIO_DEVICE_ENDPOINT` | empty | MinIO endpoint handed to Pilot in STS payloads — the laptop's LAN IP (`http://192.168.x.x:9000`), never a compose hostname; falls back to `FIELDHUB_MINIO_ENDPOINT` |
| `FIELDHUB_BACKEND_URL` | empty | TarmacView backend base URL for media-event reporting; empty disables reporting |
| `FIELDHUB_BACKEND_TIMEOUT` | `5.0` | media-event report timeout (seconds) |
| `FIELDHUB_TLS_CERT` | `/certs/server.crt` | HTTPS cert served by uvicorn |
| `FIELDHUB_TLS_KEY` | `/certs/server.key` | HTTPS key served by uvicorn |
| `FIELDHUB_SHARED_SECRET` | empty | hub↔backend auth; internal endpoints answer 503 while unset |
| `FIELDHUB_PROBE_TIMEOUT` | `2.0` | dependency probe timeout (seconds) |
| `FIELDHUB_DATABASE_URL` | `sqlite:///./fieldhub.db` | device registry storage; compose points it at the shared postgres |
| `FIELDHUB_MQTT_ENABLED` | `true` | hub-side MQTT listener on/off (tests run with it off) |
| `FIELDHUB_MQTT_TLS` / `FIELDHUB_MQTT_TLS_CA` | `true` / `/certs/ca.crt` | listener TLS toward EMQX |
| `FIELDHUB_MQTT_DEVICE_ADDR` | empty | `mqtt_addr` handed to Pilot at login — the laptop's LAN IP (`ssl://192.168.x.x:8883`), never a compose hostname |
| `FIELDHUB_PILOT_USERNAME` / `FIELDHUB_PILOT_PASSWORD` | `pilot` / empty | Pilot login account; login is rejected while the password is empty |
| `FIELDHUB_DJI_APP_ID` / `FIELDHUB_DJI_APP_KEY` / `FIELDHUB_DJI_APP_LICENSE` | empty | DJI developer app the connect page verifies via JSBridge; `GET /pilot/config` answers an envelope error while unset |
| `FIELDHUB_WORKSPACE_ID` / `FIELDHUB_WORKSPACE_NAME` | fixed UUID / `TarmacView Field` | workspace presented to Pilot |
| `FIELDHUB_JWT_SECRET` | dev default | signing key for `x-auth-token` JWTs — override in the field |
| `FIELDHUB_DEVICE_OFFLINE_TTL_S` | `120` | seconds without status traffic before a device reads offline |

`FIELDHUB_SHARED_SECRET`, `FIELDHUB_PILOT_PASSWORD`, `FIELDHUB_JWT_SECRET`,
the `FIELDHUB_DJI_*` app credentials, and the MinIO root credentials are
plumbed through `.env.docker` (see `.env.docker.example`) — never commit
real values.

## Local development

```bash
cd fieldhub
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run tests (no docker, network, or hardware needed; the media-return
# e2e test auto-skips unless the compose MinIO is reachable)
pytest

# lint + format
ruff check . && ruff format --check .

# dev server without TLS
uvicorn app.main:app --reload --port 8443
```
