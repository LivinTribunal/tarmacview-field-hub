"""wayline library model - dispatched routes pilot 2 syncs into its route list."""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, String

from app.core.db import FIELDHUB_SCHEMA, Base

# wpml template type for waypoint routes (demo enum)
TEMPLATE_TYPE_WAYPOINT = 0


def _utcnow() -> datetime:
    """timezone-aware now for create/update stamps."""
    return datetime.now(UTC)


class Wayline(Base):
    """one route in the library, anchored to the tarmacview mission it came from."""

    __tablename__ = "waylines"
    __table_args__ = {"schema": FIELDHUB_SCHEMA}

    # uuid string assigned by the backend at first dispatch - stable across re-dispatch
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    # mission uuid on the tarmacview side - the wayline <-> mission mapping anchor
    mission_id = Column(String, nullable=False, unique=True, index=True)
    drone_model_key = Column(String, nullable=True)
    payload_model_keys = Column(JSON, nullable=False, default=list)
    template_types = Column(JSON, nullable=False, default=lambda: [TEMPLATE_TYPE_WAYPOINT])
    object_key = Column(String, nullable=False)
    # md5 of the kmz - pilot's file checksum field
    sign = Column(String, nullable=True)
    favorited = Column(Boolean, nullable=False, default=False)
    username = Column(String, nullable=True)
    create_time = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    update_time = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
