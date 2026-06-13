"""internal endpoints for the tarmacview backend - shared-secret gated."""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_hub_secret
from app.schemas.internal import InternalDeviceStatus, InternalStatusResponse
from app.schemas.wayline import WaylineRegisterData
from app.services import device_registry, mqtt_listener, object_store, wayline_library

router = APIRouter(prefix="/internal/api/v1", tags=["internal"])

KMZ_CONTENT_TYPE = "application/vnd.google-earth.kmz"


@router.get("/status", response_model=InternalStatusResponse)
def status(
    _: None = Depends(require_hub_secret),
    db: Session = Depends(get_db),
) -> InternalStatusResponse:
    """broker attachment plus the device registry with live online state."""
    return InternalStatusResponse(
        broker_connected=mqtt_listener.listener.connected,
        devices=[InternalDeviceStatus(**e) for e in device_registry.snapshot(db)],
    )


@router.post("/waylines", response_model=WaylineRegisterData)
async def register_wayline(
    wayline_id: str = Form(...),
    mission_id: str = Form(...),
    name: str = Form(...),
    object_key: str = Form(...),
    drone_model_key: str | None = Form(default=None),
    payload_model_keys: str = Form(default=""),
    sign: str | None = Form(default=None),
    file: UploadFile = File(...),
    _: None = Depends(require_hub_secret),
    db: Session = Depends(get_db),
) -> WaylineRegisterData:
    """store a dispatched mission KMZ and upsert its wayline library entry.

    keyed on wayline_id so a re-dispatch overwrites the object and updates
    the row instead of duplicating. payload_model_keys is comma-separated.
    """
    data = await file.read()
    object_store.put_object(object_key, data, KMZ_CONTENT_TYPE)
    wayline = wayline_library.register_wayline(
        db,
        wayline_id=wayline_id,
        mission_id=mission_id,
        name=name,
        object_key=object_key,
        drone_model_key=drone_model_key,
        payload_model_keys=[k.strip() for k in payload_model_keys.split(",") if k.strip()],
        sign=sign,
        username="tarmacview",
    )
    db.commit()
    return WaylineRegisterData(
        wayline_id=wayline.id, mission_id=wayline.mission_id, object_key=wayline.object_key
    )
