# TarmacView Field Hub

Local DJI Cloud API gateway for the TarmacView drone mission-planning system —
wireless mission dispatch to DJI Pilot 2 controllers and automatic full-quality
media return, fully offline-capable.

This repository is the **development home** for the field hub. The service
itself — the `fieldhub/` FastAPI gateway — is built and evolved here; this is
its canonical source. The backend/frontend **integration surface** (the
`POST /api/v1/missions/{id}/dispatch` endpoint, the `/api/v1/field-link/*` and
`/api/v1/drone-media` APIs, and the ExportPanel / Upload-drone-media UI) lives
in the TarmacView monorepo
([drone-mission-planning-module](https://github.com/LivinTribunal/drone-mission-planning-module)) —
that's the cross-repo seam to keep in sync (see `docs/ROADMAP.md`).

## What's here

- `fieldhub/` — the device-facing FastAPI service (Cloud API: device binding,
  wayline library, media STS/callbacks, the Pilot connect page). See
  `fieldhub/README.md` to run it.
- `docs/specs/FIELD-HUB.md` — architecture, flows, build plan, validation checklist.
- `docs/specs/dji-cloud-api-reference.md` — protocol contract (endpoints, MQTT
  topic families, payload shapes, device enums); the implementation reference.
- `docs/specs/dji-wpml-reference.md` — WPML/KMZ structure.
- `docs/adr/2026-06-09-field-hub-local-cloud-api.md` — decision record.
- `scripts/field-hub/gen-certs.sh` — local CA + per-service TLS cert tooling.
- `scripts/field-hub/stop-field.sh` — stop/reset the compose `field` profile
  (`--wipe` also drops the data volumes, including the shared `pgdata`).
- `docs/ROADMAP.md` — prioritized next steps + the cross-repo seam, written so
  agents can pick up handed-off tasks with the right context.
- `.github/workflows/` — the harnext automation pipeline + CI, **adapted for
  this repo** (fieldhub lint/test gates, fieldhub risk tiers). `harnext-verify`
  is disabled (no self-hosted runner here).
- `docker-compose.yml` — the compose `field` profile (fieldhub + EMQX + MinIO).
  Reference here — the backend/frontend build contexts live in the monorepo.

## Run the hub

See [`fieldhub/README.md`](fieldhub/README.md).
