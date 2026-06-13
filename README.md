# TarmacView Field Hub

Local DJI Cloud API gateway for the TarmacView drone mission-planning system —
wireless mission dispatch to DJI Pilot 2 controllers and automatic full-quality
media return, fully offline-capable.

This repository is a **focused extract** of the field-hub component from the
TarmacView monorepo
([drone-mission-planning-module](https://github.com/LivinTribunal/drone-mission-planning-module)),
kept here for tracking. The backend/frontend integration surface (the dispatch
endpoint, drone-media APIs, and the ExportPanel UI) lives in the monorepo.

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
- `.github/workflows/` — the harnext automation pipeline + CI, mirrored from the
  monorepo (they reference the monorepo's harnext configuration).
- `docker-compose.yml` — the monorepo compose (profile `field`: fieldhub + EMQX +
  MinIO). Reference only here — the backend/frontend build contexts live in the
  monorepo.

## Run the hub

See [`fieldhub/README.md`](fieldhub/README.md).
