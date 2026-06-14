"""reachability probes for the hub's broker and object-store dependencies."""

import socket

import httpx

from app import __version__
from app.core.config import settings


def check_broker() -> bool:
    """true when a tcp connection to the mqtt broker's mqtts port succeeds."""
    try:
        with socket.create_connection(
            (settings.mqtt_host, settings.mqtt_port), timeout=settings.probe_timeout
        ):
            return True
    except OSError:
        return False


def check_object_store() -> bool:
    """true when the minio liveness endpoint answers 200."""
    url = f"{settings.minio_endpoint.rstrip('/')}/minio/health/live"
    try:
        response = httpx.get(url, timeout=settings.probe_timeout)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def get_health() -> dict:
    """aggregate health snapshot - ok only when both dependencies are reachable."""
    broker = check_broker()
    object_store = check_object_store()
    status = "ok" if broker and object_store else "degraded"

    return {
        "status": status,
        "service": "fieldhub",
        "version": __version__,
        "broker": broker,
        "object_store": object_store,
    }
