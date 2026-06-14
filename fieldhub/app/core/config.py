"""field hub settings loaded from FIELDHUB_* environment variables."""

from pathlib import Path
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "fieldhub-dev-secret-change-me"

# hosts that pilot on the lan can never reach - a device-facing address resolving
# to one of these means public_host (or a per-service override) is still unset
UNREACHABLE_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "minio", "emqx"})


class Settings(BaseSettings):
    """field hub settings, all overridable via FIELDHUB_* env vars."""

    # the laptop's lan ip/hostname on the travel router - no scheme, no port,
    # e.g. "192.168.8.100". the single host every device-facing address (mqtt
    # addr, sts endpoint, presigned urls) derives from. empty falls back to the
    # per-service settings below (bare-metal dev where internal == device-facing).
    public_host: str = ""

    # mqtt broker (emqx) probe target - mqtts listener
    mqtt_host: str = "localhost"
    mqtt_port: int = 8883

    # s3-compatible object store (minio) base url
    minio_endpoint: str = "http://localhost:9000"

    # minio bucket for the wayline library
    minio_wayline_bucket: str = "tarmacview-waylines"

    # presigned download url lifetime in seconds
    presigned_url_expiry_s: int = 3600
    # minio root credentials for sts assume-role + bucket ensure - empty means
    # the media-return surface is not configured
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "tarmacview-media"
    minio_region: str = "us-east-1"
    minio_object_key_prefix: str = "media"
    minio_sts_expiry_s: int = 3600

    # explicit per-service override for the device-facing object-store endpoint
    # (sts payloads + presigned download urls) - a full url like
    # http://192.168.8.100:9000. prefer public_host; set this only when minio is
    # reached on a different host/port than the api (e.g. a reverse proxy).
    minio_device_endpoint: str = ""

    # tarmacview backend base url for media-event reporting - empty disables
    backend_url: str = ""
    backend_timeout: float = 5.0

    # tls material uvicorn serves https with (paths inside the container)
    tls_cert: Path = Path("/certs/server.crt")
    tls_key: Path = Path("/certs/server.key")

    # shared secret for hub<->backend calls - empty means not configured
    shared_secret: str = ""

    # dependency probe timeout in seconds
    probe_timeout: float = 2.0

    # device registry persistence - postgres in compose (own fieldhub schema,
    # created on startup), sqlite file as the bare-metal dev default
    database_url: str = "sqlite:///./fieldhub.db"

    # hub-side mqtt listener connection - compose-internal broker address.
    # disabled in tests so the suite never needs a live broker.
    mqtt_enabled: bool = True
    mqtt_tls: bool = True
    mqtt_tls_ca: Path = Path("/certs/ca.crt")
    mqtt_reconnect_delay_s: float = 5.0

    # explicit per-service override for the device-facing broker address handed
    # to pilot at login - a full url like ssl://192.168.8.100:8883. prefer
    # public_host; set this only when the broker is reached on a different
    # host/port than the derived one.
    mqtt_device_addr: str = ""
    mqtt_device_username: str = ""
    mqtt_device_password: str = ""

    # pilot operator account - login is rejected while the password is empty
    pilot_username: str = "pilot"
    pilot_password: str = ""
    pilot_user_id: str = "3c9d2f81-6b4e-4a7c-8e5f-1d0b9a382c64"

    # dji developer app bound to the platform - the connect page verifies these
    # via jsbridge before login. empty means not provisioned yet.
    dji_app_id: str = ""
    dji_app_key: str = ""
    dji_app_license: str = ""

    # workspace presented to pilot
    workspace_id: str = "8f2b3e64-7c1a-4f5e-9d3b-2a6c8e0f4d71"
    workspace_name: str = "TarmacView Field"

    # x-auth-token jwts for the manage api
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    token_expiration_minutes: int = 720

    # online state ttl - a device with no fresh status traffic expires to offline
    device_offline_ttl_s: float = 120.0

    model_config = SettingsConfigDict(env_prefix="FIELDHUB_", env_file=".env", extra="ignore")

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_never_empty(cls, value: str) -> str:
        """an empty env var must not become an empty signing key."""
        return value or DEFAULT_JWT_SECRET

    def device_mqtt_addr(self) -> str:
        """device-facing broker address pilot dials.

        precedence: explicit override, then public_host, then the probe target.
        """
        if self.mqtt_device_addr:
            return self.mqtt_device_addr
        host = self.public_host or self.mqtt_host
        return f"ssl://{host}:{self.mqtt_port}"

    def device_minio_endpoint(self) -> str:
        """device-facing object-store url pilot dials - sts payloads + presigning.

        precedence: explicit override, then public_host (scheme/port inherited
        from minio_endpoint), then the internal endpoint.
        """
        if self.minio_device_endpoint:
            return self.minio_device_endpoint
        if self.public_host:
            parts = urlsplit(self.minio_endpoint)
            return f"{parts.scheme}://{self.public_host}:{parts.port or 9000}"
        return self.minio_endpoint

    def device_address_report(self) -> tuple[list[str], list[str]]:
        """resolved device-facing addresses plus warnings for unreachable hosts.

        returns (summary_lines, warnings) for the startup log - a warning means
        the address resolves to a compose/loopback host pilot on the lan cannot
        reach, so public_host (or an override) is still unset.
        """
        mqtt_addr = self.device_mqtt_addr()
        minio_endpoint = self.device_minio_endpoint()
        summary = [
            f"public_host={self.public_host or '(unset)'}",
            f"device mqtt_addr={mqtt_addr}",
            f"device minio endpoint={minio_endpoint}",
        ]
        warnings = []
        for label, addr in (("mqtt_addr", mqtt_addr), ("minio endpoint", minio_endpoint)):
            if (urlsplit(addr).hostname or "") in UNREACHABLE_HOSTS:
                warnings.append(
                    f"device-facing {label} resolves to {addr!r} - pilot on the lan "
                    "cannot reach this; set FIELDHUB_PUBLIC_HOST to the laptop's lan ip"
                )
        return summary, warnings


settings = Settings()
