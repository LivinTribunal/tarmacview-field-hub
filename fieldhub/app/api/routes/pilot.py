"""pilot webview - the static connect page and its bootstrap config."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.envelope import HttpResultResponse, error, ok
from app.schemas.manage import PLATFORM_NAME
from app.schemas.pilot import PilotConfigData

# static assets shipped inside the app package - index.html + pilot-connect.js
STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

router = APIRouter(tags=["pilot"])


@router.get("/", include_in_schema=False)
def connect_page() -> FileResponse:
    """serve the connect page pilot 2 loads in its cloud-service webview."""
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/pilot/config")
def pilot_config() -> HttpResultResponse:
    """app credentials + attach addresses for the connect page.

    unauthenticated by design - the page needs the credentials before login;
    the hub is a lan-only surface, same posture as the login endpoint.
    """
    if not (settings.dji_app_id and settings.dji_app_key and settings.dji_app_license):
        return error("dji app credentials not configured - set FIELDHUB_DJI_APP_ID/KEY/LICENSE")
    return ok(
        PilotConfigData(
            app_id=settings.dji_app_id,
            app_key=settings.dji_app_key,
            app_license=settings.dji_app_license,
            mqtt_addr=settings.device_mqtt_addr(),
            platform_name=PLATFORM_NAME,
            workspace_name=settings.workspace_name,
        )
    )
