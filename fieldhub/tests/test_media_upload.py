"""media module - fast-upload dedupe, tiny-fingerprint batch, upload callbacks."""

import json

import httpx
import pytest

from app.core.config import settings
from app.models.media_file import MediaFile
from app.services import media_service
from tests.data.media_payloads import (
    ABSOLUTE_ALTITUDE,
    CREATED_TIME,
    FINGERPRINT,
    OBJECT_KEY,
    SHOOT_LAT,
    SHOOT_LNG,
    TINY_FINGERPRINT,
    make_upload_callback,
)
from tests.data.mqtt_messages import AIRCRAFT_SN

WORKSPACE = settings.workspace_id
FAST_UPLOAD_PATH = f"/media/api/v1/workspaces/{WORKSPACE}/fast-upload"
TINY_FINGERPRINTS_PATH = f"/media/api/v1/workspaces/{WORKSPACE}/files/tiny-fingerprints"
CALLBACK_PATH = f"/media/api/v1/workspaces/{WORKSPACE}/upload-callback"
GROUP_CALLBACK_PATH = f"/media/api/v1/workspaces/{WORKSPACE}/group-upload-callback"


@pytest.fixture
def backend_configured(monkeypatch):
    """backend reporting target plus the shared secret."""
    monkeypatch.setattr(settings, "backend_url", "http://backend:8000")
    monkeypatch.setattr(settings, "shared_secret", "hub-secret")


@pytest.fixture
def captured_reports(monkeypatch, backend_configured):
    """record outbound media-event posts, answering 201."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        """fake backend media-events endpoint."""
        seen.append(
            {
                "path": request.url.path,
                "secret": request.headers.get("X-Hub-Secret"),
                "body": json.loads(request.content),
            }
        )
        return httpx.Response(201, json={"status": "RECEIVED"})

    monkeypatch.setattr(media_service, "transport", httpx.MockTransport(handler))
    return seen


def _media_row(db_session, fingerprint: str) -> MediaFile | None:
    """hub media row by fingerprint."""
    return db_session.query(MediaFile).filter(MediaFile.fingerprint == fingerprint).first()


def test_media_endpoints_require_token(client):
    """missing x-auth-token -> 401 on every media endpoint."""
    for path in (FAST_UPLOAD_PATH, TINY_FINGERPRINTS_PATH, CALLBACK_PATH, GROUP_CALLBACK_PATH):
        response = client.post(path, json={})
        assert response.status_code == 401, path


def test_fast_upload_unknown_fingerprint_asks_for_upload(client, pilot_headers):
    """unknown fingerprint -> non-zero code, pilot proceeds with the real upload."""
    response = client.post(
        FAST_UPLOAD_PATH, headers=pilot_headers, json={"fingerprint": FINGERPRINT}
    )

    assert response.status_code == 200
    assert response.json()["code"] != 0


def test_fast_upload_known_fingerprint_dedupes(client, pilot_headers, captured_reports):
    """fingerprint already received -> code 0, pilot skips the upload."""
    client.post(CALLBACK_PATH, headers=pilot_headers, json=make_upload_callback())

    response = client.post(
        FAST_UPLOAD_PATH, headers=pilot_headers, json={"fingerprint": FINGERPRINT}
    )

    assert response.json()["code"] == 0


def test_tiny_fingerprints_answers_known_subset(client, pilot_headers, captured_reports):
    """batch pre-check returns only the tiny fingerprints the hub has."""
    client.post(CALLBACK_PATH, headers=pilot_headers, json=make_upload_callback())

    response = client.post(
        TINY_FINGERPRINTS_PATH,
        headers=pilot_headers,
        json={"tiny_fingerprints": [TINY_FINGERPRINT, "tiny-unknown"]},
    )

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["tiny_fingerprints"] == [TINY_FINGERPRINT]


def test_upload_callback_persists_and_reports(client, pilot_headers, captured_reports, db_session):
    """callback persists the hub row verbatim and posts the media event."""
    callback = make_upload_callback()

    response = client.post(CALLBACK_PATH, headers=pilot_headers, json=callback)

    assert response.json()["code"] == 0

    row = _media_row(db_session, FINGERPRINT)
    assert row is not None
    assert row.object_key == OBJECT_KEY
    assert row.device_sn == AIRCRAFT_SN
    assert row.tiny_fingerprint == TINY_FINGERPRINT
    assert row.raw_callback == callback
    assert row.reported_at is not None

    assert len(captured_reports) == 1
    report = captured_reports[0]
    assert report["path"] == "/api/v1/field-link/media-events"
    assert report["secret"] == "hub-secret"
    assert report["body"]["fingerprint"] == FINGERPRINT
    assert report["body"]["object_key"] == OBJECT_KEY
    assert report["body"]["captured_at"] == CREATED_TIME
    assert report["body"]["position"]["coordinates"] == [SHOOT_LNG, SHOOT_LAT, ABSOLUTE_ALTITUDE]
    assert report["body"]["device_sn"] == AIRCRAFT_SN
    assert report["body"]["raw_callback"] == callback


def test_upload_callback_acks_pilot_when_backend_down(
    client, pilot_headers, backend_configured, db_session, monkeypatch
):
    """backend unreachable -> still code 0; row kept with reported_at null."""

    def refuse(request: httpx.Request) -> httpx.Response:
        """simulate a refused connection."""
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(media_service, "transport", httpx.MockTransport(refuse))

    response = client.post(CALLBACK_PATH, headers=pilot_headers, json=make_upload_callback())

    assert response.json()["code"] == 0
    row = _media_row(db_session, FINGERPRINT)
    assert row is not None
    assert row.reported_at is None


def test_upload_callback_skips_report_when_backend_unset(
    client, pilot_headers, db_session, monkeypatch
):
    """no backend url configured -> code 0, no network attempt."""
    monkeypatch.setattr(settings, "backend_url", "")

    def fail(request: httpx.Request) -> httpx.Response:
        """fail the test if any request goes out."""
        raise AssertionError("no request expected when backend_url is unset")

    monkeypatch.setattr(media_service, "transport", httpx.MockTransport(fail))

    response = client.post(CALLBACK_PATH, headers=pilot_headers, json=make_upload_callback())

    assert response.json()["code"] == 0
    assert _media_row(db_session, FINGERPRINT).reported_at is None


def test_upload_callback_repost_is_idempotent_and_retries_report(
    client, pilot_headers, backend_configured, db_session, monkeypatch
):
    """a repost never duplicates the row and retries an unreported event."""

    def refuse(request: httpx.Request) -> httpx.Response:
        """simulate a refused connection."""
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(media_service, "transport", httpx.MockTransport(refuse))
    client.post(CALLBACK_PATH, headers=pilot_headers, json=make_upload_callback())

    seen = []

    def accept(request: httpx.Request) -> httpx.Response:
        """fake backend accepting the retried report."""
        seen.append(json.loads(request.content))
        return httpx.Response(201, json={})

    monkeypatch.setattr(media_service, "transport", httpx.MockTransport(accept))
    response = client.post(CALLBACK_PATH, headers=pilot_headers, json=make_upload_callback())

    assert response.json()["code"] == 0
    rows = db_session.query(MediaFile).filter(MediaFile.fingerprint == FINGERPRINT).all()
    assert len(rows) == 1
    assert rows[0].reported_at is not None
    assert len(seen) == 1


def test_upload_callback_reported_row_not_reposted(
    client, pilot_headers, captured_reports, db_session
):
    """an already-reported fingerprint never produces a second media event."""
    client.post(CALLBACK_PATH, headers=pilot_headers, json=make_upload_callback())
    client.post(CALLBACK_PATH, headers=pilot_headers, json=make_upload_callback())

    assert len(captured_reports) == 1


def test_upload_callback_rejects_malformed_payload(client, pilot_headers, db_session):
    """payload without a fingerprint -> envelope error, nothing persisted."""
    bad = make_upload_callback()
    del bad["fingerprint"]

    response = client.post(CALLBACK_PATH, headers=pilot_headers, json=bad)

    assert response.status_code == 200
    assert response.json()["code"] != 0
    assert db_session.query(MediaFile).count() == 0


def test_group_upload_callback_acked(client, pilot_headers):
    """group variant is acked - per-file callbacks carry the data."""
    response = client.post(
        GROUP_CALLBACK_PATH,
        headers=pilot_headers,
        json={"file_group_id": "9a8b", "file_count": 4, "file_uploaded_count": 4},
    )

    assert response.json()["code"] == 0
