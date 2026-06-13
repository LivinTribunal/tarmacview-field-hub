"""storage sts - token gate, payload shape, device endpoint, mqtt config path."""

import json
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services import storage_service
from app.services.mqtt_listener import handle_message
from app.services.storage_service import StorageError
from tests.data.mqtt_messages import GATEWAY_SN, REQUESTS_TOPIC, make_envelope

STS_PATH = f"/storage/api/v1/workspaces/{settings.workspace_id}/sts"

FAKE_CREDS = SimpleNamespace(
    access_key="tmp-access",
    secret_key="tmp-secret",
    session_token="tmp-session-token",
)


@pytest.fixture
def storage_configured(monkeypatch):
    """root credentials set, network calls stubbed out."""
    monkeypatch.setattr(settings, "minio_access_key", "root-access")
    monkeypatch.setattr(settings, "minio_secret_key", "root-secret")
    monkeypatch.setattr(storage_service, "ensure_bucket", lambda: None)
    monkeypatch.setattr(storage_service, "assume_role", lambda: FAKE_CREDS)


def test_sts_requires_token(client):
    """missing x-auth-token -> 401 with a non-zero envelope code."""
    response = client.post(STS_PATH)

    assert response.status_code == 401
    assert response.json()["code"] != 0


def test_sts_payload_matches_reference_shape(client, storage_configured, pilot_headers):
    """sts data carries the demo StsCredentialsResponse contract."""
    response = client.post(STS_PATH, headers=pilot_headers)

    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["bucket"] == settings.minio_bucket
    assert data["endpoint"] == settings.minio_endpoint
    assert data["provider"] == "minio"
    assert data["region"] == settings.minio_region
    assert data["object_key_prefix"] == settings.minio_object_key_prefix
    creds = data["credentials"]
    assert creds["access_key_id"] == "tmp-access"
    assert creds["access_key_secret"] == "tmp-secret"
    assert creds["security_token"] == "tmp-session-token"
    assert creds["expire"] == settings.minio_sts_expiry_s


def test_sts_endpoint_is_device_facing(client, storage_configured, pilot_headers, monkeypatch):
    """configured lan address wins over the hub-side compose endpoint."""
    monkeypatch.setattr(settings, "minio_device_endpoint", "http://192.168.8.100:9000")

    response = client.post(STS_PATH, headers=pilot_headers)

    assert response.json()["data"]["endpoint"] == "http://192.168.8.100:9000"


def test_sts_unconfigured_returns_envelope_error(client, pilot_headers, monkeypatch):
    """missing root credentials -> envelope error, not a 500."""
    monkeypatch.setattr(settings, "minio_access_key", "")

    response = client.post(STS_PATH, headers=pilot_headers)

    assert response.status_code == 200
    assert response.json()["code"] != 0


def test_sts_object_store_down_returns_envelope_error(client, pilot_headers, monkeypatch):
    """unreachable object store -> envelope error - pilot reads the code."""
    monkeypatch.setattr(settings, "minio_access_key", "root-access")
    monkeypatch.setattr(settings, "minio_secret_key", "root-secret")

    def boom():
        """simulate minio down."""
        raise StorageError("connection refused")

    monkeypatch.setattr(storage_service, "ensure_bucket", boom)

    response = client.post(STS_PATH, headers=pilot_headers)

    assert response.json()["code"] != 0


def test_upload_policy_scopes_to_bucket():
    """session policy targets only the media bucket resources."""
    policy = json.loads(storage_service._upload_policy("tarmacview-media"))

    resources = [r for s in policy["Statement"] for r in s["Resource"]]
    assert resources == [
        "arn:aws:s3:::tarmacview-media/*",
        "arn:aws:s3:::tarmacview-media",
    ]
    actions = {a for s in policy["Statement"] for a in s["Action"]}
    assert "s3:PutObject" in actions
    assert "s3:DeleteObject" not in actions


def test_storage_config_get_answered_from_same_source(db_session, storage_configured):
    """mqtt storage_config_get replies with the sts payload, tid/bid echoed."""
    message = make_envelope("storage_config_get", {"module": 0}, tid="tid-9", bid="bid-9")

    replies = handle_message(db_session, REQUESTS_TOPIC, message)

    assert len(replies) == 1
    topic, payload = replies[0]
    assert topic == f"thing/product/{GATEWAY_SN}/requests_reply"
    assert payload["tid"] == "tid-9"
    assert payload["bid"] == "bid-9"
    assert payload["method"] == "storage_config_get"
    assert payload["data"]["result"] == 0
    output = payload["data"]["output"]
    assert output["provider"] == "minio"
    assert output["bucket"] == settings.minio_bucket
    assert output["credentials"]["access_key_id"] == "tmp-access"


def test_storage_config_get_failure_replies_error(db_session, monkeypatch):
    """object store down -> result 1 reply instead of a listener crash."""

    def boom():
        """simulate minio down."""
        raise StorageError("connection refused")

    monkeypatch.setattr(storage_service, "storage_config_payload", boom)
    message = make_envelope("storage_config_get", {"module": 0})

    replies = handle_message(db_session, REQUESTS_TOPIC, message)

    assert len(replies) == 1
    _, payload = replies[0]
    assert payload["data"]["result"] == 1
    assert "output" not in payload["data"]
