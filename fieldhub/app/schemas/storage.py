"""storage module dtos mirroring the demo's sts credentials payload."""

from pydantic import BaseModel

# OssTypeEnum value pilot uses to pick its s3 client
PROVIDER_MINIO = "minio"


class StsCredentialBlock(BaseModel):
    """temporary credential set inside the sts payload."""

    access_key_id: str
    access_key_secret: str
    security_token: str = ""
    expire: int


class StsCredentialsData(BaseModel):
    """demo StsCredentialsResponse - object-store config for direct upload."""

    bucket: str
    endpoint: str
    provider: str = PROVIDER_MINIO
    region: str
    object_key_prefix: str
    credentials: StsCredentialBlock
