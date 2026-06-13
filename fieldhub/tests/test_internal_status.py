"""internal status endpoint - shared-secret gate and registry snapshot."""

from app.core.config import settings
from app.services.mqtt_listener import handle_message
from tests.data.mqtt_messages import (
    AIRCRAFT_SN,
    GATEWAY_SN,
    STATUS_TOPIC,
    make_envelope,
    make_topo,
)

STATUS_PATH = "/internal/api/v1/status"


def test_unconfigured_secret_returns_503(client):
    """no shared secret configured -> 503, never an open endpoint."""
    response = client.get(STATUS_PATH, headers={"X-Hub-Secret": "anything"})

    assert response.status_code == 503


def test_wrong_secret_returns_403(client, monkeypatch):
    """mismatched secret -> 403."""
    monkeypatch.setattr(settings, "shared_secret", "s3cret")

    assert client.get(STATUS_PATH, headers={"X-Hub-Secret": "nope"}).status_code == 403


def test_missing_secret_header_returns_403(client, monkeypatch):
    """absent header -> 403."""
    monkeypatch.setattr(settings, "shared_secret", "s3cret")

    assert client.get(STATUS_PATH).status_code == 403


def test_status_snapshot_with_correct_secret(client, db_session, monkeypatch):
    """correct secret -> broker flag plus per-device online/bound state."""
    monkeypatch.setattr(settings, "shared_secret", "s3cret")
    handle_message(db_session, STATUS_TOPIC, make_envelope("update_topo", make_topo()))
    db_session.commit()

    response = client.get(STATUS_PATH, headers={"X-Hub-Secret": "s3cret"})

    assert response.status_code == 200
    body = response.json()
    assert body["broker_connected"] is False
    devices = {d["sn"]: d for d in body["devices"]}
    assert devices[GATEWAY_SN]["online"] is True
    assert devices[GATEWAY_SN]["model_name"] == "DJI RC Plus"
    assert devices[AIRCRAFT_SN]["online"] is True
    assert devices[AIRCRAFT_SN]["model_name"] == "Matrice 350 RTK"
    assert devices[AIRCRAFT_SN]["bound"] is False
    assert devices[AIRCRAFT_SN]["gateway_sn"] == GATEWAY_SN


def test_empty_registry_snapshot(client, monkeypatch):
    """no devices yet -> empty list, not an error."""
    monkeypatch.setattr(settings, "shared_secret", "s3cret")

    response = client.get(STATUS_PATH, headers={"X-Hub-Secret": "s3cret"})

    assert response.status_code == 200
    assert response.json()["devices"] == []
