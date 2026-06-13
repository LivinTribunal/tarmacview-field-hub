"""healthz endpoint and dependency probes - no network, docker, or hardware needed."""

import http.server
import socket
import threading

from app.services import health_service


def test_healthz_ok_when_dependencies_up(client, monkeypatch):
    """both probes true -> overall ok."""
    monkeypatch.setattr(health_service, "check_broker", lambda: True)
    monkeypatch.setattr(health_service, "check_object_store", lambda: True)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "fieldhub",
        "broker": True,
        "object_store": True,
    }


def test_healthz_degraded_when_broker_down(client, monkeypatch):
    """broker probe false -> degraded with broker flagged."""
    monkeypatch.setattr(health_service, "check_broker", lambda: False)
    monkeypatch.setattr(health_service, "check_object_store", lambda: True)

    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["broker"] is False
    assert body["object_store"] is True


def test_healthz_degraded_when_object_store_down(client, monkeypatch):
    """object-store probe false -> degraded with object_store flagged."""
    monkeypatch.setattr(health_service, "check_broker", lambda: True)
    monkeypatch.setattr(health_service, "check_object_store", lambda: False)

    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["broker"] is True
    assert body["object_store"] is False


def test_check_broker_true_against_listening_socket(monkeypatch):
    """tcp probe succeeds against a live local listener."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    try:
        monkeypatch.setattr(health_service.settings, "mqtt_host", host)
        monkeypatch.setattr(health_service.settings, "mqtt_port", port)
        assert health_service.check_broker() is True
    finally:
        server.close()


def test_check_broker_false_when_port_closed(monkeypatch):
    """tcp probe fails against a closed port."""

    # bind then release to get a port that is very likely free
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    _, port = probe.getsockname()
    probe.close()

    monkeypatch.setattr(health_service.settings, "mqtt_host", "127.0.0.1")
    monkeypatch.setattr(health_service.settings, "mqtt_port", port)
    monkeypatch.setattr(health_service.settings, "probe_timeout", 0.2)

    assert health_service.check_broker() is False


class _LivenessHandler(http.server.BaseHTTPRequestHandler):
    """stands in for minio - 200 only on the liveness path."""

    def do_GET(self):
        """answer 200 on /minio/health/live, 404 otherwise."""
        self.send_response(200 if self.path == "/minio/health/live" else 404)
        self.end_headers()

    def log_message(self, *args):
        """silence request logging."""


def test_check_object_store_true_against_local_http(monkeypatch):
    """http probe hits the minio liveness path and accepts a 200."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _LivenessHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        monkeypatch.setattr(health_service.settings, "minio_endpoint", f"http://{host}:{port}")
        assert health_service.check_object_store() is True
    finally:
        server.shutdown()


def test_check_object_store_false_when_unreachable(monkeypatch):
    """http probe returns false when the endpoint refuses connections."""

    # bind then release to get a port that is very likely free
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    _, port = probe.getsockname()
    probe.close()

    monkeypatch.setattr(health_service.settings, "minio_endpoint", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(health_service.settings, "probe_timeout", 0.2)

    assert health_service.check_object_store() is False
