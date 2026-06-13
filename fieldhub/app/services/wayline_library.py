"""wayline library - register/upsert, filtered listing, favorites, deletion."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.wayline import Wayline


def register_wayline(
    db: Session,
    *,
    wayline_id: str,
    mission_id: str,
    name: str,
    object_key: str,
    drone_model_key: str | None = None,
    payload_model_keys: list[str] | None = None,
    sign: str | None = None,
    username: str | None = None,
) -> Wayline:
    """upsert a wayline by id - a re-dispatch updates the row, never duplicates.

    a stale row holding the same mission under a different wayline id (backend
    re-provisioned while the hub kept state) is replaced, keeping one route
    per mission.
    """
    wayline = db.get(Wayline, wayline_id)
    if wayline is None:
        stale = db.query(Wayline).filter(Wayline.mission_id == mission_id).first()
        if stale is not None:
            db.delete(stale)
            db.flush()
        wayline = Wayline(id=wayline_id, mission_id=mission_id, name=name, object_key=object_key)
        db.add(wayline)
    wayline.mission_id = mission_id
    wayline.name = name
    wayline.object_key = object_key
    wayline.drone_model_key = drone_model_key
    wayline.payload_model_keys = payload_model_keys or []
    wayline.sign = sign
    wayline.username = username
    wayline.update_time = datetime.now(UTC)
    db.flush()
    return wayline


def list_waylines(
    db: Session,
    *,
    page: int,
    page_size: int,
    key: str | None = None,
    drone_model_keys: list[str] | None = None,
    favorited: bool | None = None,
) -> tuple[list[Wayline], int]:
    """one page of waylines (newest first) plus the total filtered count."""
    query = db.query(Wayline)
    if key:
        query = query.filter(Wayline.name.ilike(f"%{key}%"))
    if drone_model_keys:
        query = query.filter(Wayline.drone_model_key.in_(drone_model_keys))
    if favorited is not None:
        query = query.filter(Wayline.favorited.is_(favorited))
    query = query.order_by(Wayline.update_time.desc(), Wayline.id)
    total = query.count()
    waylines = query.offset((page - 1) * page_size).limit(page_size).all()
    return waylines, total


def get_wayline(db: Session, wayline_id: str) -> Wayline | None:
    """wayline by id."""
    return db.get(Wayline, wayline_id)


def duplicate_names(db: Session, names: list[str]) -> list[str]:
    """subset of the given names already present in the library."""
    if not names:
        return []
    rows = db.query(Wayline.name).filter(Wayline.name.in_(names)).all()
    return [row[0] for row in rows]


def set_favorited(db: Session, wayline_ids: list[str], favorited: bool) -> int:
    """mark/unmark favorites, returning how many rows matched."""
    count = 0
    for wayline_id in wayline_ids:
        wayline = db.get(Wayline, wayline_id)
        if wayline is not None:
            wayline.favorited = favorited
            count += 1
    db.flush()
    return count


def delete_wayline(db: Session, wayline_id: str) -> Wayline | None:
    """remove a wayline row, returning it (for object cleanup) or none."""
    wayline = db.get(Wayline, wayline_id)
    if wayline is None:
        return None
    db.delete(wayline)
    db.flush()
    return wayline
