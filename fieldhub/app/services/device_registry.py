"""device registry - binding, topology upserts, and online-state snapshots."""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.device import DOMAIN_RC, Device, OnlineTracker

# shared online state for the process - ttl-expired like the demo's redis
tracker = OnlineTracker(ttl_seconds=settings.device_offline_ttl_s)


def get_device(db: Session, sn: str) -> Device | None:
    """device by serial."""
    return db.get(Device, sn)


def list_devices(db: Session) -> list[Device]:
    """all known devices, stable order."""
    return db.query(Device).order_by(Device.sn).all()


def list_bound(db: Session, page: int, page_size: int) -> tuple[list[Device], int]:
    """one page of bound devices plus the total bound count."""
    query = db.query(Device).filter(Device.bound_at.isnot(None)).order_by(Device.sn)
    total = query.count()
    devices = query.offset((page - 1) * page_size).limit(page_size).all()
    return devices, total


def _get_or_create(db: Session, sn: str) -> Device:
    """fetch a device row, creating a bare one for unknown serials."""
    device = db.get(Device, sn)
    if device is None:
        device = Device(sn=sn)
        db.add(device)
        db.flush()
    return device


def bind_device(db: Session, sn: str, nickname: str | None = None) -> Device:
    """bind a device to the workspace, creating the row when unknown."""
    device = _get_or_create(db, sn)
    device.bind(nickname=nickname)
    db.flush()
    return device


def unbind_device(db: Session, sn: str) -> Device | None:
    """release a device's binding, none when the serial is unknown."""
    device = db.get(Device, sn)
    if device is None:
        return None
    device.unbind()
    db.flush()
    return device


def rename_device(db: Session, sn: str, nickname: str) -> Device | None:
    """set a device nickname, none when the serial is unknown."""
    device = db.get(Device, sn)
    if device is None:
        return None
    device.nickname = nickname
    db.flush()
    return device


def refresh_online(db: Session, sn: str) -> None:
    """ttl-refresh from telemetry traffic - known devices only."""
    if db.get(Device, sn) is not None:
        tracker.mark_online(sn)


def apply_update_topo(db: Session, gateway_sn: str, data: dict) -> None:
    """upsert the gateway and its sub-devices from an update_topo payload.

    the gateway is online after the message; sub-devices present in the
    topology are online, and previously-attached aircraft missing from it
    go offline (aircraft powered down or detached).
    """
    gateway = _get_or_create(db, gateway_sn)
    gateway.update_hardware(data.get("domain", DOMAIN_RC), data.get("type"), data.get("sub_type"))
    tracker.mark_online(gateway_sn)

    present: set[str] = set()
    for sub in data.get("sub_devices") or []:
        sn = sub.get("sn")
        if not sn:
            continue
        device = _get_or_create(db, sn)
        device.update_hardware(sub.get("domain"), sub.get("type"), sub.get("sub_type"))
        device.gateway_sn = gateway_sn
        tracker.mark_online(sn)
        present.add(sn)

    detached = (
        db.query(Device)
        .filter(Device.gateway_sn == gateway_sn, Device.sn.notin_(present | {gateway_sn}))
        .all()
    )
    for device in detached:
        tracker.mark_offline(device.sn)

    db.flush()


def snapshot(db: Session) -> list[dict]:
    """registry rows with live online state, for internal status and topologies."""
    return [
        {
            "sn": device.sn,
            "domain": device.domain,
            "type": device.type,
            "sub_type": device.sub_type,
            "model_key": device.model_key,
            "model_name": device.model_name,
            "nickname": device.nickname,
            "gateway_sn": device.gateway_sn,
            "online": tracker.is_online(device.sn),
            "bound": device.is_bound,
            "bound_at": device.bound_at.isoformat() if device.bound_at else None,
        }
        for device in list_devices(db)
    ]
