"""media return e2e - fake pilot against the compose minio, sts to media event.

auto-skips when no minio is reachable (ci); runs on a dev machine with
`docker compose --profile field up -d minio`.
"""

import hashlib
import io
import json
import os
import uuid
from urllib.parse import urlsplit

import httpx
import pytest

from app.core.config import settings
from tests.data.media_payloads import make_upload_callback
from tests.data.mqtt_messages import AIRCRAFT_SN

MINIO_ENDPOINT = os.environ.get("FIELDHUB_MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ROOT_USER", "tarmacview")
MINIO_SECRET_KEY = os.environ.get("MINIO_ROOT_PASSWORD", "tarmacview-minio")
E2E_BUCKET = "tarmacview-media-e2e"


def _minio_reachable() -> bool:
    """probe the compose minio health endpoint."""
    try:
        response = httpx.get(f"{MINIO_ENDPOINT}/minio/health/live", timeout=2.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _minio_reachable(), reason="compose minio not reachable")


@pytest.fixture
def storage_settings(monkeypatch):
    """point the hub at the compose minio with an isolated e2e bucket."""
    monkeypatch.setattr(settings, "minio_endpoint", MINIO_ENDPOINT)
    monkeypatch.setattr(settings, "minio_access_key", MINIO_ACCESS_KEY)
    monkeypatch.setattr(settings, "minio_secret_key", MINIO_SECRET_KEY)
    monkeypatch.setattr(settings, "minio_bucket", E2E_BUCKET)
    monkeypatch.setattr(settings, "backend_url", "http://backend:8000")
    monkeypatch.setattr(settings, "shared_secret", "e2e-secret")
    yield

    # best-effort bucket cleanup so reruns start clean
    from app.services import storage_service

    try:
        client = storage_service._root_client()
        for obj in client.list_objects(E2E_BUCKET, recursive=True):
            client.remove_object(E2E_BUCKET, obj.object_name)
        client.remove_bucket(E2E_BUCKET)
    except Exception:
        pass


def test_fake_pilot_media_return_flow(
    client, db_session, storage_settings, pilot_headers, monkeypatch
):
    """sts -> direct upload with temp creds -> callback -> media event."""
    from minio import Minio

    from app.models.media_file import MediaFile
    from app.services import media_service, storage_service

    # 1. fake pilot obtains temporary credentials from the hub
    response = client.post(
        f"/storage/api/v1/workspaces/{settings.workspace_id}/sts", headers=pilot_headers
    )
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["provider"] == "minio"
    creds = data["credentials"]
    assert creds["access_key_id"] != MINIO_ACCESS_KEY
    assert creds["security_token"]

    # 2. uploads an original using only the temporary credentials
    payload_bytes = b"fake-jpeg-original-" + uuid.uuid4().bytes
    object_key = f"{data['object_key_prefix']}/DJI_20260609142133_0001.JPG"
    endpoint = urlsplit(data["endpoint"])
    pilot_client = Minio(
        endpoint.netloc,
        access_key=creds["access_key_id"],
        secret_key=creds["access_key_secret"],
        session_token=creds["security_token"],
        secure=endpoint.scheme == "https",
        region=data["region"],
    )
    pilot_client.put_object(
        data["bucket"], object_key, io.BytesIO(payload_bytes), len(payload_bytes)
    )

    # 3. the stored object is byte-identical - never transcoded or modified
    stored = storage_service._root_client().get_object(data["bucket"], object_key)
    try:
        assert stored.read() == payload_bytes
    finally:
        stored.close()
        stored.release_conn()

    # 4. posts the upload callback; the hub reports the media event
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        """fake backend media-events endpoint."""
        seen["path"] = request.url.path
        seen["secret"] = request.headers.get("X-Hub-Secret")
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"status": "RECEIVED"})

    monkeypatch.setattr(media_service, "transport", httpx.MockTransport(handler))

    fingerprint = hashlib.md5(payload_bytes).hexdigest()
    callback = make_upload_callback(fingerprint=fingerprint, object_key=object_key)
    response = client.post(
        f"/media/api/v1/workspaces/{settings.workspace_id}/upload-callback",
        headers=pilot_headers,
        json=callback,
    )
    assert response.json()["code"] == 0

    # media event carries the matching inputs verbatim
    assert seen["path"] == "/api/v1/field-link/media-events"
    assert seen["secret"] == "e2e-secret"
    assert seen["body"]["fingerprint"] == fingerprint
    assert seen["body"]["object_key"] == object_key
    assert seen["body"]["captured_at"] == "2026-06-09T14:21:33+02:00"
    assert seen["body"]["position"]["coordinates"] == [17.21, 48.17, 423.6]
    assert seen["body"]["device_sn"] == AIRCRAFT_SN

    row = db_session.query(MediaFile).filter(MediaFile.fingerprint == fingerprint).first()
    assert row is not None
    assert row.reported_at is not None
