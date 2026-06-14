# TarmacView ⇄ Field Hub — Integration Roadmap

How the TarmacView app connects to the field hub across deployments, and the
phased plan to build it. Companion to `docs/ROADMAP.md` (hardware/field
validation). Topology decision record:
`docs/adr/2026-06-14-tarmacview-fieldhub-integration-topology.md`.

## Committed decision

Offline co-located **Docker is the primary field path**; the hosted web app
drives a local hub via a **browser-bridge** in a later phase (only useful where
the field has internet). A cloud backend never reaches a LAN-only hub directly —
the operator's browser/laptop is the only shared point.

Three scenarios, not "cloud vs docker":

| Scenario | Internet | How the hub is reached |
|---|---|---|
| **Offline field** (core) | none | whole stack local in Docker; backend→hub over the compose network |
| **Connected field** | yes | hosted web app; browser talks to the local hub directly over the LAN |
| **Office planning** | yes | cloud web app, no hub present — graceful "no hub" |

**Repo legend:** `[hub]` = this repo · `[mono]` =
drone-mission-planning-module · `[both]` = cross-repo seam.

## Current state (baseline)

- Backend → hub: `X-Hub-Secret` REST — `POST /internal/api/v1/waylines`
  (dispatch) + `GET /internal/api/v1/status`, reaching `https://fieldhub:8443`
  over the compose network.
- Frontend → backend only (axios `baseURL: /api/v1`, relative); never the hub.
- Deploy modes: Lambda (cloud, no hub, degrades to "no hub") and docker-compose
  `field` profile (backend+frontend+hub co-located on the laptop).
- No cloud→LAN bridge. Field setup is manual (hand-edited `.env.docker` for
  `FIELDHUB_URL`/secret/CA; `start.sh` doesn't touch them).

---

## Phase 0 — Settle the architecture (ADR) · `[hub]` ✅ Done

- **0.1 Topology ADR.** ✅ Landed —
  `docs/adr/2026-06-14-tarmacview-fieldhub-integration-topology.md`. Records the
  three scenarios, local-docker-first, browser-bridge as Phase 3, the deferred
  pre-trip sync, and *why not* a cloud↔LAN tunnel. Supersedes the 2026-06-09
  ADR's deployment notes.

## Phase 1 — One-command offline field setup · `[both]` (hardware-day enabler)

- **1.1 `start-field.sh` / `.bat`** `[mono]`: detect LAN IP → `gen-certs.sh
  <ip>` → generate shared secret + `FIELDHUB_PUBLIC_HOST` → wire
  `FIELDHUB_URL`/`FIELDHUB_SHARED_SECRET`/`FIELDHUB_CA` into `.env.docker` →
  prompt/carry DJI app creds + pilot password + MinIO creds → `compose
  --profile field up --build` → print the hub URL to type in Pilot + the
  CA-install reminder.
- **1.2 Auto-wire backend↔hub in the field profile** `[mono]`: compose sets
  `FIELDHUB_URL` + CA + the generated secret so there is **zero hand-editing**.
- **1.3 Teardown + keep cert tooling in sync** `[hub]`: a stop/reset script;
  keep this repo's `gen-certs.sh` + the compose `field` reference aligned with
  the monorepo's. ✅ `scripts/field-hub/stop-field.sh` (`down` by default,
  `--wipe` drops the `emqx-data`/`minio-data`/`pgdata` volumes — note `pgdata`
  is the *shared* postgres volume). **Stack alignment / intentional drift:** this
  repo ships only the `fieldhub` build context; the `backend`/`frontend` contexts
  in `docker-compose.yml` are monorepo-only references, so the `field` profile
  here is fieldhub + EMQX + MinIO over the base postgres. `gen-certs.sh` is the
  canonical cert tooling the monorepo launcher reuses.
- *Done-when:* from a clean laptop, **one command** brings up the full offline
  stack with the backend reaching the hub and the hub ready for Pilot.

## Phase 2 — Field Hub operator panel (TarmacView UI) · `[mono]`

- **2.1 Status/devices panel:** hub health (broker/object-store), bound devices
  (model + online), from `/field-link/status` (extend if needed).
- **2.2 Setup/connect wizard:** the Pilot URL, CA-install steps, DJI-app-cred
  check — guides the one-time RC provisioning.
- **2.3 Session view:** dispatched routes (hub library) + media inventory in one
  place (reuses dispatch + drone-media APIs).
- *Done-when:* an operator provisions an RC, dispatches, and tracks media from
  one cockpit.

## Phase 3 — Browser-bridge: hosted web app ⇄ local hub · `[both]` (later)

- **3.1 Hub browser surface** `[hub]`: CORS + a short-lived hub-issued **browser
  token** (distinct from the Pilot JWT and the `X-Hub-Secret`), scoped to the
  field-link/dispatch/media actions the browser needs.
- **3.2 Frontend hub discovery** `[mono]`: configured hub URL (e.g.
  `https://hub.tarmacview.local:8443`); call the hub directly when not
  co-located, fall back to the backend proxy when local-docker.
- **3.3 CA trust UX + security review** `[both]`: install the local CA in the
  browser; review the new browser-reachable surface.
- *Done-when:* the hosted web app on a connected field site shows live hub
  status + dispatches to the local hub directly.

## Deferred — Planning → field mission sync · `[mono]`

**Decided (ADR):** supported now are **both-local** (plan + fly in the local
stack) and **both-online** (cloud app + a reachable hub). The mixed case — cloud
app while only the hub is offline — needs **pre-trip pull sync** (the local stack
pulls selected missions while still online). **Deferred** until office-planning-
then-offline-flying is a real workflow; for offline work now, plan locally.

---

**Order:** 0 ✅ → 1 → 2 → 3; pre-trip sync deferred. Phase 1 directly smooths
hardware day. Native/desktop-wrapper packaging is out of scope (stay Docker;
revisit a thin launcher only if operators need it).
