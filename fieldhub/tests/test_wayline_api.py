"""wayline api - register upsert, list contract vs recorded samples, url, favorites."""

import pytest

from app.core.db import SessionLocal
from app.models.wayline import Wayline
from app.services import object_store
from tests.data.wayline_samples import (
    RECORDED_ITEM_FIELDS,
    RECORDED_LIST_ITEM,
    RECORDED_PAGINATION_FIELDS,
    SAMPLE_KMZ_BYTES,
    SAMPLE_REGISTER_FORM,
)

WORKSPACE = "8f2b3e64-7c1a-4f5e-9d3b-2a6c8e0f4d71"
LIST_PATH = f"/wayline/api/v1/workspaces/{WORKSPACE}/waylines"
REGISTER_PATH = "/internal/api/v1/waylines"
LAN_PRESIGNED_URL = "http://192.168.8.100:9000/tarmacview-waylines/wayline/x.kmz?sig=abc"


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    """configure the backend shared secret for register calls."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "shared_secret", "hub-secret")


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    """record object-store calls instead of dialing minio."""
    store = {"objects": {}, "removed": []}

    def put_object(object_key, data, content_type):
        """capture the stored object."""
        store["objects"][object_key] = {"data": data, "content_type": content_type}

    def presigned_get_url(object_key):
        """lan-reachable presigned url stand-in."""
        store["presigned_for"] = object_key
        return LAN_PRESIGNED_URL

    def remove_object(object_key):
        """capture deletions."""
        store["removed"].append(object_key)

    monkeypatch.setattr(object_store, "put_object", put_object)
    monkeypatch.setattr(object_store, "presigned_get_url", presigned_get_url)
    monkeypatch.setattr(object_store, "remove_object", remove_object)
    return store


@pytest.fixture(autouse=True)
def _clean_waylines():
    """wipe wayline rows between tests."""
    yield
    db = SessionLocal()
    try:
        db.query(Wayline).delete()
        db.commit()
    finally:
        db.close()


def _auth(client) -> dict:
    """headers carrying a fresh pilot x-auth-token."""
    response = client.post(
        "/manage/api/v1/login",
        json={"username": "pilot", "password": "field-test-password", "flag": 2},
    )
    return {"x-auth-token": response.json()["data"]["access_token"]}


def _register(client, **overrides):
    """register a wayline through the internal endpoint."""
    form = {**SAMPLE_REGISTER_FORM, **overrides}
    filename = form["object_key"].rsplit("/", 1)[-1]
    return client.post(
        REGISTER_PATH,
        data=form,
        files={"file": (filename, SAMPLE_KMZ_BYTES, "application/vnd.google-earth.kmz")},
        headers={"X-Hub-Secret": "hub-secret"},
    )


# internal register


def test_register_stores_object_and_row(client, fake_store, db_session):
    """register stores the kmz under object_key and persists the library row."""
    response = _register(client)

    assert response.status_code == 200
    body = response.json()
    assert body["wayline_id"] == SAMPLE_REGISTER_FORM["wayline_id"]
    assert body["mission_id"] == SAMPLE_REGISTER_FORM["mission_id"]
    assert body["object_key"] == SAMPLE_REGISTER_FORM["object_key"]

    stored = fake_store["objects"][SAMPLE_REGISTER_FORM["object_key"]]
    assert stored["data"] == SAMPLE_KMZ_BYTES
    assert stored["content_type"] == "application/vnd.google-earth.kmz"

    wayline = db_session.get(Wayline, SAMPLE_REGISTER_FORM["wayline_id"])
    assert wayline is not None
    assert wayline.mission_id == SAMPLE_REGISTER_FORM["mission_id"]
    assert wayline.payload_model_keys == RECORDED_LIST_ITEM["payload_model_keys"]


def test_register_is_idempotent_per_wayline_id(client, db_session):
    """re-dispatch updates the existing row in place - no duplicate library entries."""
    _register(client)
    response = _register(client, name="RWY22 PAPI inspection v2", sign="ffff")

    assert response.status_code == 200
    rows = db_session.query(Wayline).all()
    assert len(rows) == 1
    assert rows[0].name == "RWY22 PAPI inspection v2"
    assert rows[0].sign == "ffff"


def test_register_requires_hub_secret(client):
    """missing or wrong secret never reaches the store."""
    response = client.post(
        REGISTER_PATH,
        data=SAMPLE_REGISTER_FORM,
        files={"file": ("x.kmz", SAMPLE_KMZ_BYTES, "application/vnd.google-earth.kmz")},
        headers={"X-Hub-Secret": "wrong"},
    )
    assert response.status_code == 403


# wayline list - contract against the recorded demo sample


def test_list_item_matches_recorded_field_set(client):
    """every field of the demo GetWaylineListResponse item is served, none renamed."""
    _register(client)

    response = client.get(LIST_PATH, headers=_auth(client))
    body = response.json()

    assert body["code"] == 0
    data = body["data"]
    assert set(data) == {"list", "pagination"}
    assert set(data["pagination"]) == RECORDED_PAGINATION_FIELDS

    item = data["list"][0]
    assert set(item) == RECORDED_ITEM_FIELDS
    assert item["id"] == RECORDED_LIST_ITEM["id"]
    assert item["name"] == RECORDED_LIST_ITEM["name"]
    assert item["drone_model_key"] == RECORDED_LIST_ITEM["drone_model_key"]
    assert item["payload_model_keys"] == RECORDED_LIST_ITEM["payload_model_keys"]
    assert item["template_types"] == RECORDED_LIST_ITEM["template_types"]
    assert item["object_key"] == RECORDED_LIST_ITEM["object_key"]
    assert item["sign"] == RECORDED_LIST_ITEM["sign"]
    assert item["favorited"] is False
    # epoch milliseconds like the recorded sample
    assert isinstance(item["create_time"], int)
    assert item["create_time"] > 10**12
    assert isinstance(item["update_time"], int)


def test_list_paginates(client):
    """pagination block carries page/page_size/total across pages."""
    for i in range(3):
        _register(
            client,
            wayline_id=f"00000000-0000-0000-0000-00000000000{i}",
            mission_id=f"10000000-0000-0000-0000-00000000000{i}",
            name=f"Mission {i}",
            object_key=f"wayline/{i}.kmz",
        )

    response = client.get(LIST_PATH, params={"page": 2, "page_size": 2}, headers=_auth(client))
    data = response.json()["data"]

    assert data["pagination"] == {"page": 2, "page_size": 2, "total": 3}
    assert len(data["list"]) == 1


def test_list_filters_by_name_key(client):
    """key query searches the wayline name."""
    _register(client)
    _register(
        client,
        wayline_id="20000000-0000-0000-0000-000000000001",
        mission_id="30000000-0000-0000-0000-000000000001",
        name="Taxiway edge sweep",
        object_key="wayline/other.kmz",
    )

    response = client.get(LIST_PATH, params={"key": "papi"}, headers=_auth(client))
    items = response.json()["data"]["list"]

    assert [i["name"] for i in items] == ["RWY22 PAPI inspection"]


def test_list_filters_by_drone_model_keys(client):
    """pilot's connected-aircraft filter narrows by drone_model_key, comma form too."""
    _register(client)  # 0-89-0 (M350)
    _register(
        client,
        wayline_id="20000000-0000-0000-0000-000000000002",
        mission_id="30000000-0000-0000-0000-000000000002",
        name="M4T mission",
        object_key="wayline/m4t.kmz",
        drone_model_key="0-99-1",
    )
    headers = _auth(client)

    response = client.get(LIST_PATH, params={"drone_model_keys": "0-99-1"}, headers=headers)
    assert [i["name"] for i in response.json()["data"]["list"]] == ["M4T mission"]

    response = client.get(LIST_PATH, params={"drone_model_keys": "0-99-1,0-89-0"}, headers=headers)
    assert response.json()["data"]["pagination"]["total"] == 2


def test_list_requires_pilot_token(client):
    """wayline endpoints are pilot-token gated."""
    assert client.get(LIST_PATH).status_code == 401


# download url


def test_wayline_url_redirects_to_lan_presigned_url(client, fake_store):
    """url endpoint answers a redirect whose target is the lan-reachable store."""
    _register(client)

    response = client.get(
        f"{LIST_PATH}/{SAMPLE_REGISTER_FORM['wayline_id']}/url",
        headers=_auth(client),
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == LAN_PRESIGNED_URL
    assert fake_store["presigned_for"] == SAMPLE_REGISTER_FORM["object_key"]


def test_wayline_url_unknown_id_is_envelope_error(client):
    """unknown wayline -> non-zero envelope code, not a bare 404."""
    response = client.get(
        f"{LIST_PATH}/ffffffff-0000-0000-0000-000000000000/url", headers=_auth(client)
    )

    assert response.status_code == 200
    assert response.json()["code"] != 0


# duplicate names


def test_duplicate_names_returns_collisions(client):
    """only names already present come back."""
    _register(client)

    response = client.get(
        f"{LIST_PATH}/duplicate-names",
        params=[("name", "RWY22 PAPI inspection"), ("name", "Unused name")],
        headers=_auth(client),
    )

    body = response.json()
    assert body["code"] == 0
    assert body["data"] == ["RWY22 PAPI inspection"]


# favorites


def test_favorites_mark_and_unmark(client):
    """favorites POST sets the flag, DELETE clears it, list filter follows."""
    _register(client)
    headers = _auth(client)
    wayline_id = SAMPLE_REGISTER_FORM["wayline_id"]
    favorites_path = f"/wayline/api/v1/workspaces/{WORKSPACE}/favorites"

    assert (
        client.post(favorites_path, json={"ids": [wayline_id]}, headers=headers).json()["code"] == 0
    )
    favorited = client.get(LIST_PATH, params={"favorited": True}, headers=headers)
    assert favorited.json()["data"]["pagination"]["total"] == 1

    request = client.request("DELETE", favorites_path, json={"ids": [wayline_id]}, headers=headers)
    assert request.json()["code"] == 0
    favorited = client.get(LIST_PATH, params={"favorited": True}, headers=headers)
    assert favorited.json()["data"]["pagination"]["total"] == 0


# delete


def test_delete_wayline_removes_row_and_object(client, fake_store, db_session):
    """delete drops the library row and cleans the stored kmz."""
    _register(client)
    wayline_id = SAMPLE_REGISTER_FORM["wayline_id"]

    response = client.delete(f"{LIST_PATH}/{wayline_id}", headers=_auth(client))

    assert response.json()["code"] == 0
    assert db_session.get(Wayline, wayline_id) is None
    assert fake_store["removed"] == [SAMPLE_REGISTER_FORM["object_key"]]
