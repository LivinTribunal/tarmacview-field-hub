"""hub health endpoint."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services import health_service

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz():
    """report hub status incl. mqtt broker and object-store reachability."""
    return health_service.get_health()
