"""minio access for the wayline library - store kmz objects, presign downloads.

module functions are the seam the wayline routes/services call; tests
monkeypatch them so the suite never needs a live object store.
"""

from datetime import timedelta
from io import BytesIO
from urllib.parse import urlparse

from minio import Minio

from app.core.config import settings


def _client_for(endpoint: str) -> Minio:
    """minio client for an endpoint url like http://minio:9000."""
    parsed = urlparse(endpoint)
    return Minio(
        parsed.netloc,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=parsed.scheme == "https",
    )


def _internal_client() -> Minio:
    """client against the compose-internal endpoint - uploads and bucket admin."""
    return _client_for(settings.minio_endpoint)


def _public_client() -> Minio:
    """client against the lan-reachable endpoint - presigning only, no requests.

    presigned urls embed the host in the signature, so they must be signed
    against the address pilot will actually dial (ref doc section 7).
    """
    return _client_for(settings.minio_public_endpoint or settings.minio_endpoint)


def put_object(object_key: str, data: bytes, content_type: str) -> None:
    """store an object in the wayline bucket, creating the bucket on first use."""
    client = _internal_client()
    bucket = settings.minio_wayline_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    client.put_object(bucket, object_key, BytesIO(data), len(data), content_type=content_type)


def presigned_get_url(object_key: str) -> str:
    """lan-reachable presigned download url for a stored object."""
    return _public_client().presigned_get_object(
        settings.minio_wayline_bucket,
        object_key,
        expires=timedelta(seconds=settings.presigned_url_expiry_s),
    )


def remove_object(object_key: str) -> None:
    """delete an object from the wayline bucket."""
    _internal_client().remove_object(settings.minio_wayline_bucket, object_key)
