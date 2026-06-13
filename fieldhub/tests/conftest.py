"""shared pytest fixtures for the field hub test suite."""

import os

# hermetic test env - in-memory registry shared across sessions, no broker
# connection, fixed pilot credentials. set before any app import reads Settings().
os.environ["FIELDHUB_DATABASE_URL"] = "sqlite://"
os.environ["FIELDHUB_MQTT_ENABLED"] = "false"
os.environ["FIELDHUB_PILOT_USERNAME"] = "pilot"
os.environ["FIELDHUB_PILOT_PASSWORD"] = "field-test-password"
os.environ["FIELDHUB_MQTT_DEVICE_ADDR"] = "ssl://192.168.8.100:8883"
os.environ["FIELDHUB_DJI_APP_ID"] = "test-dji-app-id"
os.environ["FIELDHUB_DJI_APP_KEY"] = "test-dji-app-key"
os.environ["FIELDHUB_DJI_APP_LICENSE"] = "test-dji-app-license"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.media_file import MediaFile  # noqa: E402
from app.services import device_registry  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    """create registry tables once for the suite."""
    init_db()


@pytest.fixture(autouse=True)
def _clean_registry():
    """wipe device/media rows and online state between tests."""
    yield
    db = SessionLocal()
    try:
        db.query(Device).delete()
        db.query(MediaFile).delete()
        db.commit()
    finally:
        db.close()
    device_registry.tracker.clear()


@pytest.fixture
def client():
    """test client against the field hub app."""
    return TestClient(app)


@pytest.fixture
def pilot_headers(client):
    """headers carrying a fresh x-auth-token from the test pilot login."""
    response = client.post(
        "/manage/api/v1/login",
        json={"username": "pilot", "password": "field-test-password", "flag": 2},
    )
    body = response.json()
    assert body["code"] == 0
    return {"x-auth-token": body["data"]["access_token"]}


@pytest.fixture
def db_session():
    """db session for direct registry access."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
