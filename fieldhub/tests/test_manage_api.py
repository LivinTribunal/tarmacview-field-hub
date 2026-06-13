"""manage api - login envelope, token gate, binding persistence, topologies."""

from app.core.config import settings
from app.core.db import SessionLocal
from app.services import device_registry
from app.services.mqtt_listener import handle_message
from tests.data.mqtt_messages import (
    AIRCRAFT_SN,
    GATEWAY_SN,
    STATUS_TOPIC,
    make_envelope,
    make_topo,
)

LOGIN_PATH = "/manage/api/v1/login"


def _login_data(client) -> dict:
    """login with the test credentials, returning the envelope data."""
    response = client.post(
        LOGIN_PATH, json={"username": "pilot", "password": "field-test-password", "flag": 2}
    )
    body = response.json()
    assert body["code"] == 0
    return body["data"]


def _auth(client) -> dict:
    """headers carrying a fresh x-auth-token."""
    return {"x-auth-token": _login_data(client)["access_token"]}


def _seed_topology(db_session) -> None:
    """register gateway + aircraft through the mqtt handler."""
    handle_message(db_session, STATUS_TOPIC, make_envelope("update_topo", make_topo()))
    db_session.commit()


def test_login_returns_userdto_envelope(client):
    """login data carries the full pilot attach contract."""
    data = _login_data(client)

    assert data["username"] == "pilot"
    assert data["user_type"] == 2
    assert data["workspace_id"] == settings.workspace_id
    assert data["access_token"]
    assert data["mqtt_addr"] == "ssl://192.168.8.100:8883"
    assert "mqtt_username" in data
    assert "mqtt_password" in data


def test_login_rejects_bad_credentials(client):
    """wrong password -> non-zero envelope code, http 200 (pilot reads the code)."""
    response = client.post(LOGIN_PATH, json={"username": "pilot", "password": "wrong"})

    assert response.status_code == 200
    assert response.json()["code"] != 0


def test_login_disabled_without_configured_password(client, monkeypatch):
    """empty pilot password rejects every login instead of matching empty."""
    monkeypatch.setattr(settings, "pilot_password", "")
    response = client.post(LOGIN_PATH, json={"username": "pilot", "password": ""})

    assert response.json()["code"] != 0


def test_token_refresh_issues_fresh_token(client):
    """refresh exchanges a valid token for a new userdto payload."""
    response = client.post("/manage/api/v1/token/refresh", headers=_auth(client))

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["access_token"]


def test_manage_requires_token(client):
    """missing or garbage x-auth-token -> non-zero envelope code."""
    missing = client.get("/manage/api/v1/workspaces/current")
    assert missing.status_code == 401
    assert missing.json()["code"] != 0

    garbage = client.get("/manage/api/v1/workspaces/current", headers={"x-auth-token": "garbage"})
    assert garbage.status_code == 401
    assert garbage.json()["code"] != 0


def test_current_workspace(client):
    """workspace endpoint reflects hub config."""
    response = client.get("/manage/api/v1/workspaces/current", headers=_auth(client))

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["workspace_id"] == settings.workspace_id
    assert body["data"]["workspace_name"] == settings.workspace_name


def test_bind_persists_across_sessions(client):
    """binding survives a fresh db session - the restart-persistence contract."""
    headers = _auth(client)
    response = client.post(f"/manage/api/v1/devices/{AIRCRAFT_SN}/binding", headers=headers)
    assert response.json()["code"] == 0

    # fresh session, nothing shared with the request that wrote the row
    db = SessionLocal()
    try:
        device = device_registry.get_device(db, AIRCRAFT_SN)
        assert device is not None
        assert device.is_bound
    finally:
        db.close()


def test_bound_list_and_unbind_flow(client):
    """bound list pages the registry; unbinding empties it again."""
    headers = _auth(client)
    client.post(f"/manage/api/v1/devices/{AIRCRAFT_SN}/binding", headers=headers)

    workspace = settings.workspace_id
    listed = client.get(f"/manage/api/v1/devices/{workspace}/devices/bound", headers=headers).json()
    assert listed["code"] == 0
    assert listed["data"]["pagination"] == {"page": 1, "page_size": 10, "total": 1}
    assert listed["data"]["list"][0]["device_sn"] == AIRCRAFT_SN
    assert listed["data"]["list"][0]["bound_status"] is True

    unbound = client.delete(
        f"/manage/api/v1/devices/{AIRCRAFT_SN}/unbinding", headers=headers
    ).json()
    assert unbound["code"] == 0

    relisted = client.get(
        f"/manage/api/v1/devices/{workspace}/devices/bound", headers=headers
    ).json()
    assert relisted["data"]["pagination"]["total"] == 0


def test_unbind_unknown_device_reports_error(client):
    """unbinding a serial the hub never saw -> non-zero code."""
    response = client.delete("/manage/api/v1/devices/NOPE/unbinding", headers=_auth(client))

    assert response.json()["code"] != 0


def test_device_detail_and_rename(client, db_session):
    """device detail reflects topology identity; rename sets the nickname."""
    _seed_topology(db_session)
    headers = _auth(client)
    workspace = settings.workspace_id

    detail = client.get(
        f"/manage/api/v1/devices/{workspace}/devices/{AIRCRAFT_SN}", headers=headers
    ).json()
    assert detail["code"] == 0
    assert detail["data"]["device_model"]["key"] == "0-89-0"
    assert detail["data"]["device_name"] == "Matrice 350 RTK"
    assert detail["data"]["status"] is True

    renamed = client.put(
        f"/manage/api/v1/devices/{workspace}/devices/{AIRCRAFT_SN}",
        headers=headers,
        json={"nickname": "Inspection Bird"},
    ).json()
    assert renamed["code"] == 0

    detail = client.get(
        f"/manage/api/v1/devices/{workspace}/devices/{AIRCRAFT_SN}", headers=headers
    ).json()
    assert detail["data"]["nickname"] == "Inspection Bird"


def test_device_list_includes_topology_devices(client, db_session):
    """workspace device list serves everything the registry knows."""
    _seed_topology(db_session)
    response = client.get(
        f"/manage/api/v1/devices/{settings.workspace_id}/devices", headers=_auth(client)
    ).json()

    assert response["code"] == 0
    sns = {d["device_sn"] for d in response["data"]}
    assert sns == {GATEWAY_SN, AIRCRAFT_SN}


def test_topologies_groups_aircraft_under_gateway(client, db_session):
    """tsa topology tree: gateway in parents, attached aircraft in hosts."""
    _seed_topology(db_session)
    response = client.get(
        f"/manage/api/v1/workspaces/{settings.workspace_id}/devices/topologies",
        headers=_auth(client),
    ).json()

    assert response["code"] == 0
    topologies = response["data"]["list"]
    assert len(topologies) == 1
    parent = topologies[0]["parents"][0]
    host = topologies[0]["hosts"][0]
    assert parent["sn"] == GATEWAY_SN
    assert parent["online_status"] is True
    assert parent["device_model"]["key"] == "2-119-0"
    assert host["sn"] == AIRCRAFT_SN
    assert host["gateway_sn"] == GATEWAY_SN
