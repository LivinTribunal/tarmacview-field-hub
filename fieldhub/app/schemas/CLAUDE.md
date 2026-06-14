# schemas

## Purpose

Pydantic v2 DTOs for device-facing requests and responses, mirroring the DJI
Cloud API demo payload shapes, plus the response-envelope helpers every
device-facing route wraps its output in.

## Public API surface

- `envelope` → `HttpResultResponse`, `ok()`, `error()`, `CODE_OK` / `CODE_ERROR` - the wrapper every device-facing response uses.
- `health.HealthResponse` → status / service / version / broker / object_store snapshot.
- `manage` → Login, Workspace, Device, Topology DTOs plus `PaginationData`, `PLATFORM_NAME`, `USER_TYPE_PILOT`.
- `media` → `MediaFastUploadRequest`, `TinyFingerprintsRequest/Data`, `MediaUploadCallbackRequest`, and its nested metadata/extension models.
- `storage` → `StsCredentialsData`, `StsCredentialBlock`, `PROVIDER_MINIO`.
- `wayline` → `WaylineListData`, `WaylineListItem`, `FavoritesRequest`, `WaylineRegisterData`.
- `pilot.PilotConfigData`; `internal.InternalDeviceStatus` / `InternalStatusResponse`.

## Invariants

- Device-facing responses must follow the envelope shapes in `docs/specs/dji-cloud-api-reference.md`.
- Wire field names mirror the demo even when misspelled: `tinny_fingerprint` is accepted via `AliasChoices` alongside `tiny_fingerprint` - don't "fix" the wire name.
- Pure DTOs only: no business logic, no db access, no I/O.

## Cross-package dependencies

- Imports: `pydantic` only; internally `schemas/wayline` reuses `PaginationData` from `schemas/manage`.
- Imported by: `app.api.routes.*` (request/response models + envelope), `app.services` (media_service, storage_service), and `app.main` (envelope).

## Gotchas

- Pydantic v2 - use `validation_alias` / `AliasChoices` for demo wire-name quirks.
- Constants live next to their DTOs (`PLATFORM_NAME`, `USER_TYPE_PILOT`, `PROVIDER_MINIO`) - reuse them, don't redefine.
- `HealthResponse` and the dict `health_service.get_health()` returns must stay in lockstep; the `version` field was added in #2 and is sourced from `app.__version__`.
