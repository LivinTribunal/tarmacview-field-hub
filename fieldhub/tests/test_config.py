"""settings defaults and FIELDHUB_* env override behavior."""

from pathlib import Path

from app.core.config import DEFAULT_JWT_SECRET, Settings


def test_defaults_are_sane():
    """fresh settings carry local dev defaults."""
    s = Settings(_env_file=None)

    assert s.mqtt_host == "localhost"
    assert s.mqtt_port == 8883
    assert s.minio_endpoint == "http://localhost:9000"
    assert s.tls_cert == Path("/certs/server.crt")
    assert s.tls_key == Path("/certs/server.key")
    assert s.shared_secret == ""
    assert s.probe_timeout > 0


def test_env_overrides_applied(monkeypatch):
    """FIELDHUB_* env vars override the defaults."""
    monkeypatch.setenv("FIELDHUB_MQTT_HOST", "emqx")
    monkeypatch.setenv("FIELDHUB_MQTT_PORT", "18883")
    monkeypatch.setenv("FIELDHUB_MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("FIELDHUB_SHARED_SECRET", "field-secret")
    monkeypatch.setenv("FIELDHUB_PROBE_TIMEOUT", "0.5")

    s = Settings(_env_file=None)

    assert s.mqtt_host == "emqx"
    assert s.mqtt_port == 18883
    assert s.minio_endpoint == "http://minio:9000"
    assert s.shared_secret == "field-secret"
    assert s.probe_timeout == 0.5


def test_tls_paths_wired_from_env(monkeypatch):
    """tls cert/key paths land in settings from env."""
    monkeypatch.setenv("FIELDHUB_TLS_CERT", "/tmp/field-certs/server.crt")
    monkeypatch.setenv("FIELDHUB_TLS_KEY", "/tmp/field-certs/server.key")

    s = Settings(_env_file=None)

    assert s.tls_cert == Path("/tmp/field-certs/server.crt")
    assert s.tls_key == Path("/tmp/field-certs/server.key")


def test_unprefixed_env_ignored(monkeypatch):
    """env vars without the FIELDHUB_ prefix don't leak into settings."""
    monkeypatch.setenv("MQTT_HOST", "evil-broker")

    s = Settings(_env_file=None)

    assert s.mqtt_host == "localhost"


def test_empty_jwt_secret_falls_back_to_default(monkeypatch):
    """an empty FIELDHUB_JWT_SECRET never becomes an empty signing key."""
    monkeypatch.setenv("FIELDHUB_JWT_SECRET", "")

    s = Settings(_env_file=None)

    assert s.jwt_secret == DEFAULT_JWT_SECRET


def test_device_mqtt_addr_override_and_fallback(monkeypatch):
    """device-facing broker addr - configured value wins, probe target otherwise."""
    monkeypatch.delenv("FIELDHUB_MQTT_DEVICE_ADDR", raising=False)
    assert Settings(_env_file=None).device_mqtt_addr() == "ssl://localhost:8883"

    monkeypatch.setenv("FIELDHUB_MQTT_DEVICE_ADDR", "ssl://192.168.8.50:8883")
    assert Settings(_env_file=None).device_mqtt_addr() == "ssl://192.168.8.50:8883"
