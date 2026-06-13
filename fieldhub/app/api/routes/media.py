"""media module - fast-upload negotiation and upload-result callbacks."""

import logging

from fastapi import APIRouter, Depends
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_pilot_token
from app.schemas.envelope import HttpResultResponse, error, ok
from app.schemas.media import (
    MediaFastUploadRequest,
    MediaUploadCallbackRequest,
    TinyFingerprintsData,
    TinyFingerprintsRequest,
)
from app.services import media_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media/api/v1", tags=["media"])


@router.post("/workspaces/{workspace_id}/fast-upload")
def fast_upload(
    workspace_id: str,
    body: MediaFastUploadRequest,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """fingerprint pre-check - code 0 means already here, pilot skips the upload."""
    if media_service.fingerprint_known(db, body.fingerprint):
        return ok()
    return error("file not found")


@router.post("/workspaces/{workspace_id}/files/tiny-fingerprints")
def tiny_fingerprints(
    workspace_id: str,
    body: TinyFingerprintsRequest,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """batch pre-check - answers which tiny fingerprints already exist."""
    known = media_service.known_tiny_fingerprints(db, body.tiny_fingerprints)
    return ok(TinyFingerprintsData(tiny_fingerprints=known))


@router.post("/workspaces/{workspace_id}/upload-callback")
def upload_callback(
    workspace_id: str,
    body: dict,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """pilot reports a completed upload - persist it and notify the backend.

    the raw dict is kept verbatim alongside the parsed shape; a failed
    backend report still acks pilot (the file is safe in the object store)
    and leaves reported_at null for a retry on the next repost.
    """
    try:
        parsed = MediaUploadCallbackRequest.model_validate(body)
    except ValidationError:
        logger.warning("malformed upload callback payload")
        return error("invalid upload callback payload")

    media_file = media_service.record_upload_callback(db, parsed, body)
    if not media_file.is_reported:
        payload = media_service.media_event_payload(parsed, body)
        if media_service.report_media_event(payload):
            media_file.mark_reported()
    db.commit()
    return ok()


@router.post("/workspaces/{workspace_id}/group-upload-callback")
def group_upload_callback(
    workspace_id: str,
    body: dict,
    _: dict = Depends(require_pilot_token),
) -> HttpResultResponse:
    """folder/group upload progress - acked only, per-file callbacks carry the data."""
    logger.debug("group upload callback: %s", body)
    return ok()
