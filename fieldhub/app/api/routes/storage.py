"""storage module - temporary object-store credentials for direct upload."""

import logging

from fastapi import APIRouter, Depends

from app.core.security import require_pilot_token
from app.schemas.envelope import HttpResultResponse, error, ok
from app.services import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage/api/v1", tags=["storage"])


@router.post("/workspaces/{workspace_id}/sts")
def issue_sts(
    workspace_id: str,
    _: dict = Depends(require_pilot_token),
) -> HttpResultResponse:
    """temporary minio credentials - pilot uploads originals directly with them."""

    # an unreachable or unconfigured object store must answer as an envelope
    # error - pilot reads the code, not the http status
    try:
        return ok(storage_service.storage_config_payload())
    except Exception:
        logger.warning("sts credential issue failed", exc_info=True)
        return error("storage credentials unavailable")
