"""health endpoint dto."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """aggregate health snapshot for the hub and its dependencies."""

    status: str
    service: str
    broker: bool
    object_store: bool
