"""media file registry - uploads pilot reported via the upload callback."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, String

from app.core.db import FIELDHUB_SCHEMA, Base


class MediaFile(Base):
    """one uploaded original known to the hub, keyed by its dji fingerprint."""

    __tablename__ = "media_files"
    __table_args__ = {"schema": FIELDHUB_SCHEMA}

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    fingerprint = Column(String, nullable=False, unique=True)
    tiny_fingerprint = Column(String, nullable=True, index=True)
    object_key = Column(String, nullable=False)
    name = Column(String, nullable=True)
    device_sn = Column(String, nullable=True)
    # callback payload persisted verbatim - capture time and shoot position
    # drive mission matching on the backend side
    raw_callback = Column(JSON, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    reported_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def is_reported(self) -> bool:
        """true once the backend acked the media event."""
        return self.reported_at is not None

    def mark_reported(self) -> None:
        """record a successful media-event report to the backend."""
        self.reported_at = datetime.now(UTC)
