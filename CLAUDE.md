# CLAUDE.md

## Project Overview

TarmacView Field Hub — a local DJI Cloud API gateway for the TarmacView drone
mission-planning system. It runs on the field laptop and gives DJI Pilot 2 (on
DJI RC controllers) a "third-party cloud platform" to talk to over MQTT + HTTPS,
fully offline-capable: wireless mission dispatch to the controller's route
library, and automatic full-quality media return after landing.

Python 3.12 + FastAPI. Device registry persists in its own `fieldhub` schema in
the shared PostgreSQL instance. Runs as the `fieldhub` service in the docker
compose `field` profile alongside EMQX (MQTT broker) and MinIO (S3 object store).

This repo is a focused extract of the field-hub component; the backend/frontend
integration surface (dispatch endpoint, drone-media APIs, ExportPanel UI) lives
in the [drone-mission-planning-module](https://github.com/LivinTribunal/drone-mission-planning-module)
monorepo.

## Build & Run Commands

```bash
# install deps
cd fieldhub && pip install -r requirements.txt

# run the field profile (fieldhub + EMQX + MinIO)
docker compose --profile field up -d --build

# run dev server directly
cd fieldhub && uvicorn app.main:app --reload

# run all tests (sqlite-backed, no services needed)
cd fieldhub && pytest

# run a single test file
cd fieldhub && pytest tests/test_manage_api.py -v

# lint + format check
cd fieldhub && ruff check . && ruff format --check .

# regenerate local CA + per-service TLS certs (after the laptop LAN IP changes)
bash scripts/field-hub/gen-certs.sh
```

## Code Style Rules

- **Python imports**: stdlib → third-party → local (enforced by Ruff `I` rule)
- **Python naming**: `snake_case` files and functions, `PascalCase` classes
- **Python line length**: 100 characters max (`fieldhub/pyproject.toml`)
- **Schemas**: Pydantic v2 DTOs; device-facing responses follow the envelope
  shapes in `docs/specs/dji-cloud-api-reference.md`
- **Routes**: device-facing modules are mounted under their DJI Cloud API
  prefixes (`/manage/api/v1`, `/wayline/api/v1`, `/media/api/v1`,
  `/storage/api/v1`); the Pilot connect page is `GET /` + `GET /pilot/config`
- **Error handling**: `HTTPException` in routes, custom exceptions in services
- **Docstrings**: every `def` function and `class` must have a `"""..."""`
  docstring - short, lowercase, one line when possible
- **Comments**: sparse, lowercase, casual. Never comment what the code obviously
  does. Use short section labels above logical groups. Dashes (`-`) not
  em-dashes. No thesis references, no tracker/issue/PR/commit IDs.
- **UUIDs**: `Column(UUID, primary_key=True, default=uuid4)` for primary keys
- **Geometry**: capture positions stored as WKT strings (`POINT Z (lon lat alt)`)
  in `Column(String)`

## Project Structure

```
tarmacview-field-hub/
├── fieldhub/
│   ├── app/
│   │   ├── api/routes/     # device-facing Cloud API HTTP layer (manage, wayline, media, storage, pilot, health, internal)
│   │   ├── core/           # config, db, security (x-auth-token JWTs), exceptions
│   │   ├── models/         # SQLAlchemy ORM (device registry, wayline, media_file)
│   │   ├── schemas/        # Pydantic v2 request/response DTOs + envelope helpers
│   │   ├── services/       # business logic (storage/STS, media, wayline, mqtt listener)
│   │   ├── static/         # the Pilot connect page (plain HTML + vanilla JS, no build step)
│   │   └── main.py         # FastAPI app
│   ├── tests/              # pytest (sqlite via FIELDHUB_DATABASE_URL=sqlite://)
│   ├── requirements.txt    # pinned deps (PROTECTED)
│   └── pyproject.toml      # ruff + pytest config
├── docs/specs/             # FIELD-HUB.md, dji-cloud-api-reference.md, dji-wpml-reference.md
├── docs/adr/               # decision records
├── scripts/field-hub/      # gen-certs.sh (local CA + TLS)
├── .github/workflows/      # CI + harnext pipeline
├── harness.config.json     # risk tier definitions
└── docker-compose.yml      # field profile reference (build contexts live in the monorepo)
```

## Architecture Overview

```
DJI Pilot 2 (RC) ── MQTT + HTTPS ──► fieldhub (FastAPI) ── internal REST ──► backend (monorepo)
                                         │         │
                                      EMQX      MinIO
                                     (MQTTS)    (S3 / presigned URLs)
```

- `fieldhub/app/api/routes/` — HTTP layer only, no business logic
- `fieldhub/app/services/` — all business logic (storage/STS, media matching, wayline library, MQTT topology)
- Routes never import models directly; routes → services → models/schemas.

## Critical Paths — Extra Care Required (Tier 3)

- `fieldhub/app/core/security*` — x-auth-token JWT issuing/verification
- `fieldhub/app/services/storage_service*` — STS credential issuing, presigned URLs
- `fieldhub/app/services/*media*` — media fast-upload negotiation, callbacks, matching
- `scripts/field-hub/**` — TLS cert tooling

Changes here require thorough test coverage and human review (see `harness.config.json`).

## Testing

- pytest + httpx; async tests use `asyncio_mode = "auto"` (in `fieldhub/pyproject.toml`)
- Tests run against in-memory **sqlite** (`FIELDHUB_DATABASE_URL=sqlite://`, set in `conftest.py`) — no Postgres/MQTT/MinIO needed
- The media-return e2e test self-skips when no MinIO is reachable on `localhost:9000`

## Security Constraints

- Field mode has zero internet egress; all endpoints bind to the LAN
- Validate all external input at boundaries (Pydantic handles this)
- Use SQLAlchemy ORM only, never raw SQL strings
- `x-auth-token` JWTs via `python-jose` — never expose tokens in logs
- Per-device credentials issued at binding; backend↔fieldhub calls use a shared secret
- Never commit secrets, certs, or `.env` files (`certs/` is git-ignored)

## Specification Documents — READ BEFORE IMPLEMENTING

- `docs/specs/FIELD-HUB.md` — **READ FIRST.** Architecture, flows (mission
  dispatch, media return), build plan, and the V1–V5 validation checklist.
- `docs/specs/dji-cloud-api-reference.md` — protocol contract: endpoints, MQTT
  topic families, payload shapes, STS/storage flow, device enums. The
  implementation reference.
- `docs/specs/dji-wpml-reference.md` — WPML/KMZ wayline structure.

## Harnext Automation

This repo uses harnext for automated issue lifecycle. Gate an issue with the
`harnext:start` label to opt it into the pipeline (tagger → triage → plan →
implement → gap → review → doc-gardening → human merge). `harnext-verify` is
disabled on this repo (no self-hosted runner). Pipeline workflows are under
`.github/workflows/harnext-*.yml`.

## PR Conventions

- **Branch naming**: `<type>/<short-description>` (e.g., `feat/wayline-favorites`)
- **Commit messages**: conventional prefixes required (`feat:`, `fix:`, `chore:`,
  `refactor:`, `docs:`, `test:`, `build:`, `ci:`); short, lowercase, casual after
  the prefix. No AI attribution, ever.
- **Git identity**: commits must use `Štefan Moravík <stevko.moravik@gmail.com>`
- All PRs must pass CI before merge

## Protected Files

Agents must never modify:
- `.github/workflows/**` — pipeline definitions
- `harness.config.json` — risk tier configuration
- `fieldhub/requirements.txt` — Python dependencies

`CLAUDE.md` is editable by agents only when the user explicitly requests it.
