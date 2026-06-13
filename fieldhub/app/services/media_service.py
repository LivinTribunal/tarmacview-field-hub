"""media return - fingerprint dedupe, callback persistence, backend reporting."""

import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.media_file import MediaFile
from app.schemas.media import MediaUploadCallbackRequest

logger = logging.getLogger(__name__)

MEDIA_EVENTS_PATH = "/api/v1/field-link/media-events"

# test seam - swapped for httpx.MockTransport in the suite
transport: httpx.BaseTransport | None = None


def fingerprint_known(db: Session, fingerprint: str) -> bool:
    """true when a file with this fingerprint already arrived."""
    return db.query(MediaFile.id).filter(MediaFile.fingerprint == fingerprint).first() is not None


def known_tiny_fingerprints(db: Session, candidates: list[str]) -> list[str]:
    """subset of the candidate tiny fingerprints the hub already has."""
    if not candidates:
        return []
    rows = (
        db.query(MediaFile.tiny_fingerprint)
        .filter(MediaFile.tiny_fingerprint.in_(candidates))
        .all()
    )
    known = {row[0] for row in rows}
    return [c for c in candidates if c in known]


def record_upload_callback(db: Session, parsed: MediaUploadCallbackRequest, raw: dict) -> MediaFile:
    """persist one upload callback, idempotent on fingerprint - first write wins."""
    existing = db.query(MediaFile).filter(MediaFile.fingerprint == parsed.fingerprint).first()
    if existing is not None:
        return existing

    media_file = MediaFile(
        fingerprint=parsed.fingerprint,
        tiny_fingerprint=parsed.ext.tiny_fingerprint if parsed.ext else None,
        object_key=parsed.object_key,
        name=parsed.name,
        device_sn=parsed.ext.sn if parsed.ext else None,
        raw_callback=raw,
    )
    db.add(media_file)
    db.flush()
    return media_file


def media_event_payload(parsed: MediaUploadCallbackRequest, raw: dict) -> dict:
    """backend media-event body - device-reported capture time and position."""
    meta = parsed.metadata
    position = None
    if meta and meta.shoot_position:
        position = {
            "type": "Point",
            "coordinates": [
                meta.shoot_position.lng,
                meta.shoot_position.lat,
                meta.absolute_altitude if meta.absolute_altitude is not None else 0.0,
            ],
        }
    return {
        "object_key": parsed.object_key,
        "fingerprint": parsed.fingerprint,
        "captured_at": meta.created_time if meta else None,
        "position": position,
        "device_sn": parsed.ext.sn if parsed.ext else None,
        "raw_callback": raw,
    }


def report_media_event(payload: dict) -> bool:
    """post one media event to the backend, false when it can't be delivered.

    a failed report never blocks the pilot ack - the file is already safe in
    the object store and the row keeps reported_at null for a later retry.
    """
    if not settings.backend_url:
        logger.info("backend url not configured - media event not reported")
        return False
    try:
        with httpx.Client(
            base_url=settings.backend_url,
            timeout=settings.backend_timeout,
            transport=transport,
        ) as client:
            response = client.post(
                MEDIA_EVENTS_PATH,
                json=payload,
                headers={"X-Hub-Secret": settings.shared_secret},
            )
            response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.warning("media event report to backend failed", exc_info=True)
        return False
