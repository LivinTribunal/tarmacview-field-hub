"""object-store credentials - minio assume-role sts plus the storage config payload."""

import json
import logging
from urllib.parse import urlsplit

from minio import Minio
from minio.credentials import AssumeRoleProvider, Credentials

from app.core.config import settings
from app.schemas.storage import StsCredentialBlock, StsCredentialsData

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """object store not configured or not reachable."""


def _split_endpoint(url: str) -> tuple[str, bool]:
    """minio sdk address parts (netloc, secure) from a base url."""
    parts = urlsplit(url)
    if not parts.netloc:
        raise StorageError(f"invalid object store endpoint: {url!r}")
    return parts.netloc, parts.scheme == "https"


def _require_root_credentials() -> None:
    """fail early when the media-return surface is not configured."""
    if not settings.minio_access_key or not settings.minio_secret_key:
        raise StorageError("object store credentials not configured")


def _root_client() -> Minio:
    """minio client with root credentials - hub-side address, never device-facing."""
    _require_root_credentials()
    netloc, secure = _split_endpoint(settings.minio_endpoint)
    return Minio(
        netloc,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
        region=settings.minio_region,
    )


def _upload_policy(bucket: str) -> str:
    """session policy scoping temporary credentials to uploads into the bucket."""
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:PutObject",
                        "s3:GetObject",
                        "s3:AbortMultipartUpload",
                        "s3:ListMultipartUploadParts",
                    ],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetBucketLocation",
                        "s3:ListBucket",
                        "s3:ListBucketMultipartUploads",
                    ],
                    "Resource": [f"arn:aws:s3:::{bucket}"],
                },
            ],
        }
    )


def ensure_bucket() -> None:
    """create the media bucket when missing - originals are never touched."""
    client = _root_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def assume_role() -> Credentials:
    """temporary upload-scoped credentials via minio's assume-role sts api."""
    _require_root_credentials()
    provider = AssumeRoleProvider(
        sts_endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        duration_seconds=settings.minio_sts_expiry_s,
        policy=_upload_policy(settings.minio_bucket),
        region=settings.minio_region,
    )
    return provider.retrieve()


def device_endpoint() -> str:
    """device-facing object-store address for sts payloads."""
    return settings.device_minio_endpoint()


def storage_config_payload() -> StsCredentialsData:
    """the single storage-config source for the http sts endpoint and mqtt.

    every address in the payload is device-facing; the assume-role call
    itself goes to the hub-side endpoint.
    """
    ensure_bucket()
    creds = assume_role()
    return StsCredentialsData(
        bucket=settings.minio_bucket,
        endpoint=device_endpoint(),
        region=settings.minio_region,
        object_key_prefix=settings.minio_object_key_prefix,
        credentials=StsCredentialBlock(
            access_key_id=creds.access_key,
            access_key_secret=creds.secret_key,
            security_token=creds.session_token or "",
            expire=settings.minio_sts_expiry_s,
        ),
    )
