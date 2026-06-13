"""device registry model, product dictionary, and the in-memory online tracker."""

import time
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.core.db import FIELDHUB_SCHEMA, Base

# domain segment of the device key
DOMAIN_AIRCRAFT = 0
DOMAIN_PAYLOAD = 1
DOMAIN_RC = 2
DOMAIN_DOCK = 3

# product dictionary keyed by domain-type-subtype. unknown keys must degrade
# to "online, unknown model" - never block binding on a missing entry.
DEVICE_DICTIONARY = {
    "0-60-0": "Matrice 300 RTK",
    "0-89-0": "Matrice 350 RTK",
    "0-77-0": "Mavic 3 Enterprise",
    "0-77-1": "Mavic 3T",
    "0-67-0": "Matrice 30",
    "0-67-1": "Matrice 30T",
    "0-99-1": "Matrice 4T",  # wpml-derived, unverified on hardware
    "2-119-0": "DJI RC Plus",
    "2-144-0": "DJI RC Pro Enterprise",
}


class Device(Base):
    """a dji device known to the hub - gateway (rc) or aircraft."""

    __tablename__ = "devices"
    __table_args__ = {"schema": FIELDHUB_SCHEMA}

    sn = Column(String, primary_key=True)
    domain = Column(Integer, nullable=True)
    type = Column(Integer, nullable=True)
    sub_type = Column(Integer, nullable=True)
    gateway_sn = Column(String, nullable=True)
    nickname = Column(String, nullable=True)
    bound_at = Column(DateTime(timezone=True), nullable=True)
    first_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    @property
    def model_key(self) -> str | None:
        """domain-type-subtype key, none until hardware identity is known."""
        if self.domain is None or self.type is None or self.sub_type is None:
            return None
        return f"{self.domain}-{self.type}-{self.sub_type}"

    @property
    def model_name(self) -> str | None:
        """dictionary name for the model key, none for unknown devices."""
        key = self.model_key
        return DEVICE_DICTIONARY.get(key) if key else None

    @property
    def is_bound(self) -> bool:
        """true when the device is bound to the workspace."""
        return self.bound_at is not None

    def bind(self, nickname: str | None = None) -> None:
        """bind to the workspace, keeping the original bound time on rebind."""
        if self.bound_at is None:
            self.bound_at = datetime.now(UTC)
        if nickname:
            self.nickname = nickname

    def unbind(self) -> None:
        """release the workspace binding."""
        self.bound_at = None

    def update_hardware(self, domain: int | None, type_: int | None, sub_type: int | None) -> None:
        """refresh hardware identity from a topology payload."""
        if domain is not None:
            self.domain = domain
        if type_ is not None:
            self.type = type_
        if sub_type is not None:
            self.sub_type = sub_type


class OnlineTracker:
    """in-memory online state keyed by sn, expired by a ttl like the demo's redis."""

    def __init__(self, ttl_seconds: float, clock=time.monotonic):
        """track online deadlines using the given ttl and clock."""
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._deadlines: dict[str, float] = {}

    def mark_online(self, sn: str) -> None:
        """refresh the device's online deadline."""
        self._deadlines[sn] = self._clock() + self.ttl_seconds

    def mark_offline(self, sn: str) -> None:
        """drop the device's online state immediately."""
        self._deadlines.pop(sn, None)

    def is_online(self, sn: str) -> bool:
        """true while the device's deadline has not expired."""
        deadline = self._deadlines.get(sn)
        return deadline is not None and self._clock() < deadline

    def clear(self) -> None:
        """forget all online state."""
        self._deadlines.clear()
