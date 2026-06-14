"""pilot connect page - static serving, bootstrap config, and the js flow."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.config import settings

DRIVER = Path(__file__).parent / "data" / "pilot_connect_driver.js"

requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

# full happy-path order: license verify -> login -> api -> thing -> media -> mission
HAPPY_EVENTS = [
    "fetch:GET:/pilot/config",
    "bridge:platformVerifyLicense",
    "bridge:platformIsVerified",
    "credentials",
    "fetch:POST:/manage/api/v1/login",
    "bridge:platformLoadComponent:api",
    "bridge:platformLoadComponent:thing",
    "bridge:platformSetWorkspaceId",
    "bridge:platformSetInformation",
    "bridge:thingGetConnectState",
    "bridge:platformLoadComponent:media",
    "bridge:platformLoadComponent:mission",
]


def _run_flow(scenario: str) -> dict:
    """run the node flow driver for one scenario and parse its json report."""
    process = subprocess.run(
        ["node", str(DRIVER), scenario], capture_output=True, text=True, timeout=60
    )
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


# page + config endpoint


def test_connect_page_served(client):
    """root serves the html page with the degraded-mode marker + flow script."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Open this page in DJI Pilot 2" in response.text
    assert "/static/pilot-connect.js" in response.text


def test_flow_script_served(client):
    """the dom-free flow module is served from the static mount."""
    response = client.get("/static/pilot-connect.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "runConnectFlow" in response.text


def test_pilot_config_returns_credentials(client):
    """config envelope carries the dji app credentials and attach addresses."""
    body = client.get("/pilot/config").json()

    assert body["code"] == 0
    data = body["data"]
    assert data["app_id"] == "test-dji-app-id"
    assert data["app_key"] == "test-dji-app-key"
    assert data["app_license"] == "test-dji-app-license"
    assert data["mqtt_addr"] == "ssl://192.168.8.100:8883"
    assert data["platform_name"] == "TarmacView Field Hub"
    assert data["workspace_name"] == settings.workspace_name


def test_pilot_config_unconfigured(client, monkeypatch):
    """missing dji credentials -> non-zero envelope instead of empty strings."""
    monkeypatch.setattr(settings, "dji_app_license", "")

    body = client.get("/pilot/config").json()

    assert body["code"] != 0
    assert "not configured" in body["message"]


# js flow via the node driver


@requires_node
def test_flow_happy_path_order():
    """license -> login -> api -> thing -> media -> mission, each step gating the next."""
    report = _run_flow("happy")

    assert report["result"]["completed"] is True
    assert report["result"]["failedStep"] is None
    assert report["events"] == HAPPY_EVENTS


@requires_node
def test_flow_module_params():
    """api/thing/media component params match the jsbridge contract."""
    report = _run_flow("happy")

    components = {
        call["args"][0]: json.loads(call["args"][1])
        for call in report["calls"]
        if call["method"] == "platformLoadComponent"
    }
    assert components["api"] == {"host": "https://192.168.8.100:8443", "token": "token-1"}
    assert components["thing"] == {
        "host": "ssl://192.168.8.100:8883",
        "username": "mqtt-user",
        "password": "mqtt-pass",
        "connectCallback": "thingConnectCallback",
    }

    # originals (type 0) + video on, per the media-return design
    assert components["media"] == {
        "autoUploadPhoto": True,
        "autoUploadPhotoType": 0,
        "autoUploadVideo": True,
    }

    # mission module enables the cloud route-library sync; empty params, host +
    # token come from the api module (confirmed against real pilot 2)
    assert components["mission"] == {}


@requires_node
def test_flow_workspace_and_platform_info():
    """workspace id from login + platform identity from config reach the bridge."""
    report = _run_flow("happy")

    calls = {call["method"]: call["args"] for call in report["calls"]}
    assert calls["platformSetWorkspaceId"] == ["workspace-1"]
    assert calls["platformSetInformation"] == ["TarmacView Field Hub", "TarmacView Field", ""]


@requires_node
def test_flow_login_request_shape():
    """login posts the pilot client flag with the entered credentials."""
    report = _run_flow("happy")

    login = next(f for f in report["fetches"] if f["url"].endswith("/login"))
    assert login["method"] == "POST"
    assert login["body"] == {"username": "pilot", "password": "field-test-password", "flag": 2}


@requires_node
def test_flow_caches_token_on_login():
    """a successful login caches the access token for later resume."""
    report = _run_flow("happy")

    assert report["tokenOps"] == [{"op": "persist", "token": "token-1"}]
    assert report["cachedToken"] == "token-1"


@requires_node
def test_flow_resume_skips_login():
    """a cached token is refreshed and the login form is skipped."""
    report = _run_flow("resume")

    assert report["result"]["completed"] is True
    assert "credentials" not in report["events"]
    refresh = next(f for f in report["fetches"] if f["url"].endswith("/token/refresh"))
    assert refresh["method"] == "POST"
    assert refresh["headers"]["x-auth-token"] == "cached-token"
    assert not any(f["url"].endswith("/login") for f in report["fetches"])

    # the refreshed token replaces the cached one and is what the api module gets
    components = {
        call["args"][0]: json.loads(call["args"][1])
        for call in report["calls"]
        if call["method"] == "platformLoadComponent"
    }
    assert components["api"]["token"] == "token-refreshed"
    assert report["cachedToken"] == "token-refreshed"


@requires_node
def test_flow_resume_falls_back_when_token_stale():
    """a token that fails to refresh is dropped and the form is used instead."""
    report = _run_flow("resume-expired")

    assert report["result"]["completed"] is True
    assert report["tokenOps"][0] == {"op": "clear"}
    assert "credentials" in report["events"]
    assert any(f["url"].endswith("/login") for f in report["fetches"])
    assert report["cachedToken"] == "token-1"


@requires_node
def test_disconnect_unloads_modules_and_clears_token():
    """disconnect unloads the loaded components (reverse order) and drops the token."""
    report = _run_flow("disconnect")

    unloaded = [c["args"][0] for c in report["calls"] if c["method"] == "platformUnloadComponent"]
    assert unloaded == ["mission", "media", "thing", "api"]
    assert report["tokenOps"] == [{"op": "clear"}]
    assert report["cachedToken"] is None


@requires_node
def test_flow_mqtt_callback_updates_state():
    """the registered thing callback drives the mqtt row in both directions."""
    report = _run_flow("happy")

    assert report["registeredCallbacks"] == ["thingConnectCallback"]
    assert report["mqttAfterDisconnect"]["state"] == "waiting"
    assert report["mqttAfterConnect"]["state"] == "ok"


@requires_node
def test_flow_stops_when_config_fails():
    """unconfigured hub -> visible error before any bridge call."""
    report = _run_flow("config-fail")

    assert report["result"]["failedStep"] == "license"
    assert report["events"] == ["fetch:GET:/pilot/config"]
    assert "not configured" in report["result"]["message"]


@requires_node
def test_flow_stops_when_license_rejected():
    """failed verify -> no login request, no component loads."""
    report = _run_flow("verify-fail")

    assert report["result"]["failedStep"] == "license"
    assert report["events"] == ["fetch:GET:/pilot/config", "bridge:platformVerifyLicense"]


@requires_node
def test_flow_stops_when_login_rejected():
    """failed login -> no component loads."""
    report = _run_flow("login-fail")

    assert report["result"]["failedStep"] == "login"
    assert not any(e.startswith("bridge:platformLoadComponent") for e in report["events"])
    assert "invalid username or password" in report["result"]["message"]


@requires_node
def test_flow_stops_when_thing_fails():
    """thing module failure -> media never loads, raw bridge error surfaced."""
    report = _run_flow("thing-fail")

    assert report["result"]["failedStep"] == "mqtt"
    assert "bridge:platformLoadComponent:media" not in report["events"]
    last = report["statuses"][-1]
    assert last["step"] == "mqtt"
    assert last["state"] == "error"
    assert "broker unreachable" in last["detail"]


@requires_node
def test_flow_browser_mode():
    """no djiBridge -> browser-mode result, no requests, no crash."""
    report = _run_flow("no-bridge")

    assert report["result"]["mode"] == "browser"
    assert report["result"]["completed"] is False
    assert report["events"] == []
    assert "DJI Pilot 2" in report["result"]["message"]
