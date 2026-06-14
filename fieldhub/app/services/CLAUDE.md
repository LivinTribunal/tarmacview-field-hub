# services

## Purpose

All field-hub business logic - device registry, dependency health probes, media
return, MQTT topic handling, object-store/STS credentials, and the wayline
library. Routes call into here; this layer never imports route code.

## Public API surface

Routes import whole modules (`from app.services import <module>`) and call their
module-level functions; `main.py` imports the listener singleton.

- `device_registry` → `bind_device` / `unbind_device` / `rename_device`, `list_bound`, `apply_update_topo`, `refresh_online`, `snapshot`, plus the process-wide `tracker`.
- `health_service.get_health()` → aggregate snapshot dict (status/service/version/broker/object_store); `check_broker` / `check_object_store`.
- `media_service` → `fingerprint_known`, `known_tiny_fingerprints`, `record_upload_callback`, `media_event_payload`, `report_media_event`.
- `storage_service` → `storage_config_payload`, `assume_role`, `ensure_bucket`, `device_endpoint`; raises `StorageError`.
- `object_store` → `put_object`, `presigned_get_url`, `remove_object`.
- `wayline_library` → `register_wayline`, `list_waylines`, `get_wayline`, `duplicate_names`, `set_favorited`, `delete_wayline`.
- `mqtt_listener` → `listener` singleton, `MqttListener`, `handle_message`.

## Invariants

- Media callback ingest is idempotent on `fingerprint` - first write wins, never insert a duplicate row (`record_upload_callback`).
- Wayline register is an upsert by id and keeps one route per mission: a re-dispatch updates the row, and a stale row holding the same mission under a different id is replaced, never duplicated.
- `register_wayline` is the single chokepoint that sanitizes the name (`sanitize_wayline_name` strips DJI-forbidden `_ . / \ < > : " | ? *`, collapses to spaces, falls back to `wayline` when all-forbidden) so a bad name can't break Pilot's route list; `duplicate_names` normalizes its query the same way so the collision check matches the stored form.
- Online state lives only in the in-process ttl `tracker`, not the db; telemetry traffic (`/osd`, `/state`) refreshes the ttl, `update_topo` rebuilds topology.
- A failed backend media report never blocks the pilot ack - the file is already in the object store and the row stays unreported for a later retry.
- Every address in the storage-config payload is device-facing and resolves through `settings.device_minio_endpoint()` (the single source off `FIELDHUB_PUBLIC_HOST`) - `storage_service.device_endpoint()` for STS and `object_store._public_client()` for presigning both call it; the assume-role and the hub's own put/stat go to the internal endpoint.

## Cross-package dependencies

- Imports from: `app.core` (config settings, db `SessionLocal`), `app.models` (Device, MediaFile, Wayline, OnlineTracker), `app.schemas` (media, storage), `app` (`__version__`).
- Imported by: `app.api.routes.*` (each route → its service) and `app.main` (the mqtt listener).

## Gotchas

- Tier 3 critical paths: `storage_service*` and `*media*` (alongside `core/security*`) need thorough tests and human review - see `harness.config.json`.
- Test seams keep the suite offline: `media_service.transport` accepts an httpx mock transport, and `object_store`'s module functions are monkeypatched, so no live MinIO/MQTT is needed.
- The mqtt listener swallows per-message errors (rollback + continue) so one bad payload never kills the loop; `storage_config_get` answers `result 1` when the object store is unreachable instead of crashing.
- `__version__` is read from `app/__init__.py` (single source of truth) - don't hardcode the build version here.
