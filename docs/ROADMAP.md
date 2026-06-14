# Field Hub Roadmap

Prioritized next steps for the field hub, written so an agent can pick up any
item with enough context to act. For each item: **where** it lives, **why**,
**what to do**, **done-when**, and the spec refs.

## Context (read first)

The field hub is a local DJI Cloud API gateway: DJI Pilot 2 (on a DJI RC) talks
to it as a "third-party cloud platform" over the LAN, fully offline. It does two
jobs — **mission out** (TarmacView mission → Pilot's route library over WiFi)
and **media back** (full-quality photos/videos → laptop after landing). Design:
`docs/specs/FIELD-HUB.md`. Protocol contract (the implementation source of
truth): `docs/specs/dji-cloud-api-reference.md`. KMZ/WPML: `dji-wpml-reference.md`.

**Status:** Phases 1–3 + the Pilot connect page are merged. A 2026-06-13
BlueStacks spike confirmed the connect chain (V1 partial) and the full mission
dispatch round-trip (V2) in emulation; the interop constraints it surfaced are
in `dji-cloud-api-reference.md` §9. V3/V4/V5 + native-JSBridge + MQTT
device-online are hardware-only (RC Plus 2, ~next week, monorepo issue #812).

### Cross-repo seam — where to work

This repo is the **dev home for the `fieldhub/` service**. The **integration
surface** lives in the TarmacView monorepo (`drone-mission-planning-module`):
the dispatch endpoint `POST /api/v1/missions/{id}/dispatch`, the
`/api/v1/field-link/*` + `/api/v1/drone-media` backend APIs, the KMZ exporter
(`backend/app/services/export/`), and the ExportPanel / Upload-drone-media UI.
Each item below is tagged **[hub]** (here), **[monorepo]**, or **[hardware]**.
A change that spans both repos says so in its PR.

---

## P1 — before the RC arrives (do now, no hardware needed)

### 1. OSS split-horizon: device-facing vs internal endpoint  **[hub]** · T3
**Why.** The spike proved the server and the device cannot share one MinIO
address: the server reaches MinIO over the compose network (`minio:9000`); the
RC reaches it only over the LAN. Presigned URLs / STS `endpoint` handed to Pilot
must use the **device-reachable** host, while the hub's own put/stat use the
**internal** host. (`dji-cloud-api-reference.md` §9.2, §3.3, §7.)
**Do.** In `fieldhub/app/services/storage_service.py` (+ `core/config.py`),
split the MinIO endpoint into two settings: an internal endpoint for the hub's
own client (put/stat/bucket-ensure) and a device-facing endpoint used when
building STS responses and presigned URLs. Presigning is pure local computation
(no MinIO round-trip), so the device-facing host is set independently. If a
reverse proxy ever fronts MinIO, it must forward the signed `Host` header
verbatim (SigV4).
**Done-when.** STS `endpoint` + presigned wayline/media URLs carry the
device-facing host; the hub still reads/writes MinIO over the internal host;
tests cover both. The media e2e test still self-skips without MinIO.

### 2. Single-source device-facing addressing  **[hub]** · T2
**Why.** The spike's #1 time-sink: a stale IP in *one* of {MQTT host, STS
endpoint, connect-page `mqtt_addr`} silently breaks the chain with a generic
"network abnormal" and no hint which leg. (`dji-cloud-api-reference.md` §7.)
**Do.** Drive every device-facing address off one configured LAN IP/host
setting (`FIELDHUB_PUBLIC_HOST` or similar), so `mqtt_addr`, the STS/presign
endpoint (#1), and `/pilot/config` all derive from it. Add a startup log line
echoing the resolved device-facing addresses. Document a one-command re-point
for when the laptop's LAN IP changes.
**Done-when.** Changing one setting re-points all device-facing payloads;
startup logs show them; a test asserts they agree.

### 3. Device dictionary completeness  **[hub]** · T2
**Why.** The spike confirmed `wpml:droneEnumValue=99` for the M4 series; demo
v1.10's dictionary predates it and *rejects* it. The hub must seed every fleet
model and degrade gracefully (never crash binding) on an unknown device.
(`dji-cloud-api-reference.md` §6.)
**Do.** Ensure the hub's device dictionary seeds at least M300 `0-60-0`, M350
`0-89-0`, M3E/M3T `0-77-0/1`, M30/M30T `0-67-0/1`, **M4T `0-99-1`**, RC Plus
`2-119-0`. Unknown `domain-type-subtype` → log + treat as generic, don't 500.
**Done-when.** Binding/`update_topo` with M4T and with an unknown key both
succeed; tests cover the unknown-device path. (RC Plus 2 key is captured on
hardware — item 6.)

### 4. Dispatched-filename / wayline-name sanitization  **[hub]** + **[monorepo]** · T2
**Why.** The spike: a wayline name with an underscore broke the *list* endpoint
for every wayline (DJI name rule forbids `_ . / \ < > : " | ? *`), and lxml's
lowercase `encoding='utf-8'` got the KMZ rejected (must be uppercase `UTF-8`).
(`dji-cloud-api-reference.md` §3.2, §9.1.)
**Do.** **[hub]** defensively sanitize the wayline name in the register/upload
path. **[monorepo]** the KMZ exporter must emit uppercase `encoding="UTF-8"` and
sanitize the mission-derived filename before dispatch.
**Done-when.** A mission whose name contains forbidden chars dispatches and
lists cleanly; the exported `template.kml` declares uppercase UTF-8.

## P1 — hardware day (RC Plus 2 + RC Plus, ~next week)  **[hardware]**

### 5. Run V1–V5 + verify the connect page on real hardware  · #812
**Do.** Provision one RC (DJI login, install the local CA from `gen-certs.sh`,
point Cloud Service at the hub URL), then work `FIELD-HUB.md` §9: **V1** offline
binding across reboots, **V2** native route-list refresh UX, **V3** 4K video
auto-upload + resume on WiFi drop, **V4** MinIO STS from Pilot's S3 client,
**V5** TLS/MQTTS acceptance of the local CA. Confirm the #831 connect page's
JSBridge flow on real hardware (license verify → login `flag:2` → `thing`/`media`
load → `update_topo`), and capture the **RC Plus 2 topology key** (§6).
**Done-when.** §9 verdicts posted, deltas filed as small follow-up issues,
`dji-cloud-api-reference.md` `⚠ UNVERIFIED` markers resolved, #812 closed.

## P2 — finish Phase 3

### 6. Wire confirm-ingest → processing pipeline  **[monorepo]** · T2
**Why.** Media return is built end-to-end *except* the hand-off: confirm-ingest
marks rows `INGESTED` but the pipeline hand-off behind it is a **stub**
(`FIELD-HUB.md` §6, §8 Phase 3).
**Do.** In the monorepo, replace the stub in
`backend/app/services/drone_media_service.py` (confirm-ingest path) with a real
hand-off into the existing processing pipeline.
**Done-when.** Confirming a mission's media actually enqueues it for processing;
tested.

### 7. Connect-page JSBridge hardening  **[hub]** · T2 (verify needs hardware)
**Why.** `§5` flags the `mission` module as ⚠ UNVERIFIED — the route library may
need it loaded beyond `api`/`thing`/`media`; bridge-return parsing has edge
cases (`code:0` + `data:false` = failure).
**Do.** After item 5's hardware findings, add the `mission` module to the
connect sequence if required, and tighten `parseBridgeReturn` edge handling.
**Done-when.** Route sync + media upload both work from the native bridge on
hardware.

## P3 — polish (optional, post-hardware)  **[hub]** + **[monorepo]**

Phase 4 from `FIELD-HUB.md` §8: results-page pull flow, multi-RC sessions,
upload-progress UI, retry/resume on WiFi drop, and JSBridge webview embedding of
TarmacView inside Pilot. Pull these in as the field workflow demands.

---

## Handing a task to the harnext pipeline

File it as an issue in this repo (or the monorepo for **[monorepo]** items),
include acceptance criteria, then add the `harnext:start` label. The pipeline
(tagger → triage → plan → implement → gap → review → human merge) runs on
GitHub-hosted runners; `harnext-verify` is disabled here. Gates are
`cd fieldhub && ruff check . && ruff format --check . && pytest` (see
`harness.config.json` for risk tiers — T3 = `core/security*`, `storage_service*`,
`*media*`, `scripts/field-hub/**`).
