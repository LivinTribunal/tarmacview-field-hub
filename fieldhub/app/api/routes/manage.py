"""manage module - login, workspace, devices/binding, and tsa topologies."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.security import constant_time_equals, create_access_token, require_pilot_token
from app.models.device import DOMAIN_RC
from app.schemas.envelope import HttpResultResponse, error, ok
from app.schemas.manage import (
    BindRequest,
    BoundDeviceListData,
    DeviceData,
    DeviceModelData,
    LoginData,
    LoginRequest,
    PaginationData,
    RenameRequest,
    TopologyData,
    TopologyListData,
    TopologyNodeData,
    WorkspaceData,
)
from app.services import device_registry

router = APIRouter(prefix="/manage/api/v1", tags=["manage"])

DEFAULT_PAGE_SIZE = 10


def _login_data(username: str) -> LoginData:
    """userdto payload with a fresh token and the mqtt attach params."""
    return LoginData(
        user_id=settings.pilot_user_id,
        username=username,
        workspace_id=settings.workspace_id,
        access_token=create_access_token(username),
        mqtt_addr=settings.device_mqtt_addr(),
        mqtt_username=settings.mqtt_device_username,
        mqtt_password=settings.mqtt_device_password,
    )


def _device_data(entry: dict) -> DeviceData:
    """device payload from a registry snapshot entry."""
    return DeviceData(
        device_sn=entry["sn"],
        device_name=entry["model_name"] or entry["sn"],
        nickname=entry["nickname"],
        workspace_id=settings.workspace_id,
        device_model=DeviceModelData(
            key=entry["model_key"],
            domain=entry["domain"],
            type=entry["type"],
            sub_type=entry["sub_type"],
            name=entry["model_name"],
        ),
        status=entry["online"],
        bound_status=entry["bound"],
        bound_time=entry["bound_at"],
        gateway_sn=entry["gateway_sn"],
        domain=entry["domain"],
    )


def _topology_node(entry: dict) -> TopologyNodeData:
    """topology node payload from a registry snapshot entry."""
    return TopologyNodeData(
        sn=entry["sn"],
        online_status=entry["online"],
        device_callsign=entry["nickname"] or entry["model_name"],
        device_model=DeviceModelData(
            key=entry["model_key"],
            domain=entry["domain"],
            type=entry["type"],
            sub_type=entry["sub_type"],
            name=entry["model_name"],
        ),
        gateway_sn=entry["gateway_sn"],
    )


@router.post("/login")
def login(body: LoginRequest) -> HttpResultResponse:
    """pilot/operator login - rejected while no pilot password is configured."""
    if not settings.pilot_password:
        return error("login disabled - pilot password not configured")
    if body.username != settings.pilot_username or not constant_time_equals(
        body.password, settings.pilot_password
    ):
        return error("invalid username or password")
    return ok(_login_data(body.username))


@router.post("/token/refresh")
def refresh_token(claims: dict = Depends(require_pilot_token)) -> HttpResultResponse:
    """exchange a valid token for a fresh one."""
    return ok(_login_data(claims.get("sub", settings.pilot_username)))


@router.get("/workspaces/current")
def current_workspace(_: dict = Depends(require_pilot_token)) -> HttpResultResponse:
    """workspace of the authenticated user."""
    return ok(
        WorkspaceData(workspace_id=settings.workspace_id, workspace_name=settings.workspace_name)
    )


@router.get("/devices/{workspace_id}/devices")
def list_devices(
    workspace_id: str,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """all devices in the workspace."""
    return ok([_device_data(e) for e in device_registry.snapshot(db)])


@router.get("/devices/{workspace_id}/devices/bound")
def list_bound_devices(
    workspace_id: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """bound devices, paged."""
    devices, total = device_registry.list_bound(db, page, page_size)
    snapshot_by_sn = {e["sn"]: e for e in device_registry.snapshot(db)}
    return ok(
        BoundDeviceListData(
            list=[_device_data(snapshot_by_sn[d.sn]) for d in devices],
            pagination=PaginationData(page=page, page_size=page_size, total=total),
        )
    )


@router.get("/devices/{workspace_id}/devices/{device_sn}")
def get_device(
    workspace_id: str,
    device_sn: str,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """one device by serial."""
    entry = next((e for e in device_registry.snapshot(db) if e["sn"] == device_sn), None)
    if entry is None:
        return error("device not found")
    return ok(_device_data(entry))


@router.post("/devices/{device_sn}/binding")
def bind_device(
    device_sn: str,
    body: BindRequest | None = None,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """bind a device to the workspace."""
    device_registry.bind_device(db, device_sn, nickname=body.nickname if body else None)
    db.commit()
    return ok()


@router.delete("/devices/{device_sn}/unbinding")
def unbind_device(
    device_sn: str,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """unbind a device."""
    device = device_registry.unbind_device(db, device_sn)
    if device is None:
        return error("device not found")
    db.commit()
    return ok()


@router.put("/devices/{workspace_id}/devices/{device_sn}")
def rename_device(
    workspace_id: str,
    device_sn: str,
    body: RenameRequest,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """rename a device."""
    nickname = body.nickname or body.device_name
    if not nickname:
        return error("nickname required")
    device = device_registry.rename_device(db, device_sn, nickname)
    if device is None:
        return error("device not found")
    db.commit()
    return ok()


@router.get("/workspaces/{workspace_id}/devices/topologies")
def device_topologies(
    workspace_id: str,
    _: dict = Depends(require_pilot_token),
    db: Session = Depends(get_db),
) -> HttpResultResponse:
    """device tree for pilot's tsa module - gateways with their aircraft."""
    entries = device_registry.snapshot(db)
    gateways = [e for e in entries if e["domain"] == DOMAIN_RC]
    topologies = [
        TopologyData(
            hosts=[_topology_node(e) for e in entries if e["gateway_sn"] == gateway["sn"]],
            parents=[_topology_node(gateway)],
        )
        for gateway in gateways
    ]
    return ok(TopologyListData(list=topologies))
