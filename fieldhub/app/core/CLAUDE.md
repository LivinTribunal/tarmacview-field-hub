# core

## Purpose

Cross-cutting foundations every other package builds on: settings, the registry
db engine/session, x-auth-token JWT auth plus the backend shared-secret gate,
and the envelope error type. No business logic lives here.

## Public API surface

- `config.settings` → the process-wide `Settings` singleton (all `FIELDHUB_*` env vars). Address resolvers: `device_mqtt_addr()`, `device_minio_endpoint()`, `device_address_report()`; constants `DEFAULT_JWT_SECRET`, `UNREACHABLE_HOSTS`.
- `db` → `Base`, `engine`, `SessionLocal`, `init_db()`, `get_db()` (request-scoped session dependency), `FIELDHUB_SCHEMA`.
- `security` → `create_access_token`, `require_pilot_token` (FastAPI dep), `require_hub_secret` (FastAPI dep), `constant_time_equals`.
- `exceptions.HubApiError` → raise anywhere; rendered as a non-zero DJI envelope (code/message + an http status, default 200).

## Invariants

- Every device-facing address resolves through `settings.device_mqtt_addr()` / `device_minio_endpoint()` - never read the raw `mqtt_device_addr` / `minio_device_endpoint` fields. Precedence: explicit per-service override → `public_host` → the internal probe/endpoint. This is the single source, so re-pointing the LAN IP is one env var (`FIELDHUB_PUBLIC_HOST`).
- The JWT signing key is never empty: a field validator falls back to `DEFAULT_JWT_SECRET` so an unset env var can't silently produce an empty key.
- `require_hub_secret` 503s when no shared secret is configured and 403s on mismatch - it never waves a call through while unconfigured.
- Tokens are secrets: never log them (see root `CLAUDE.md` security constraints).

## Cross-package dependencies

- Imports: stdlib + pydantic-settings, sqlalchemy, python-jose, fastapi. `init_db()` imports `app.models` lazily so tables are registered before `create_all`.
- Imported by: nearly everything - `app.models` (`Base` / `FIELDHUB_SCHEMA`), `app.services.*` (settings, `SessionLocal`), `app.api.routes.*` (settings, `get_db`, the auth deps), and `app.main` (`init_db`, settings, `HubApiError`).

## Gotchas

- Tier 3 critical path: `security*` (JWT issue/verify) needs thorough tests + human review - see `harness.config.json`.
- `settings` is instantiated at import time; tests build `Settings(_env_file=None)` to skip reading a stray `.env`.
- sqlite (dev/tests) has no schemas, so the `fieldhub` schema is translated away; in-memory sqlite shares one connection (`StaticPool`) so every session sees the same db. No alembic - `init_db()` is create-if-missing and idempotent.
- `device_address_report()` returns `(summary, warnings)`; `main` logs the warning when an address still resolves to an `UNREACHABLE_HOSTS` member (compose/loopback host) Pilot on the LAN can't reach.
