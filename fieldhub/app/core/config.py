"""field hub settings loaded from FIELDHUB_* environment variables."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "fieldhub-dev-secret-change-me"


class Settings(BaseSettings):
    """field hub settings, all overridable via FIELDHUB_* env vars."""

    # mqtt broker (emqx) probe target - mqtts listener
    mqtt_host: str = "localhost"
    mqtt_port: int = 8883

    # s3-compatible object store (minio) base url
    minio_endpoint: str = "http://localhost:9000"

    # minio bucket for the wayline library
    minio_wayline_bucket: str = "tarmacview-waylines"

    # lan-reachable minio url for presigned download links handed to pilot -
    # must be the laptop's lan ip, never a compose hostname. falls back to
    # minio_endpoint when unset (bare-metal dev where both are the same).
    minio_public_endpoint: str = ""

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

    # device-facing object-store endpoint handed to pilot in sts payloads -
    # must be the laptop's lan ip, never a compose hostname. empty falls back
    # to minio_endpoint (bare-metal dev, where both are the same address).
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

    # device-facing mqtt address handed to pilot at login - must be the
    # laptop's lan ip, never a compose hostname. empty until provisioned.
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
        """device-facing broker address - configured value or the probe target."""
        if self.mqtt_device_addr:
            return self.mqtt_device_addr
        return f"ssl://{self.mqtt_host}:{self.mqtt_port}"


settings = Settings()
