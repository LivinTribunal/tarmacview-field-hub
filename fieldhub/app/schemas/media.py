"""media module dtos mirroring the demo's fast-upload and callback payloads."""

from pydantic import AliasChoices, BaseModel, Field


class MediaFastUploadRequest(BaseModel):
    """fingerprint pre-check body - do you already have this file?"""

    fingerprint: str
    name: str | None = None
    path: str | None = None


class TinyFingerprintsRequest(BaseModel):
    """batch pre-check body."""

    tiny_fingerprints: list[str] = []


class TinyFingerprintsData(BaseModel):
    """batch pre-check answer - the subset the hub already has."""

    tiny_fingerprints: list[str]


class ShootPosition(BaseModel):
    """capture coordinates as pilot reports them."""

    lat: float
    lng: float


class MediaFileMetadata(BaseModel):
    """demo MediaFileMetadata - the matching input for tarmacview."""

    absolute_altitude: float | None = None
    relative_altitude: float | None = None
    gimbal_yaw_degree: float | None = None
    created_time: str | None = None
    shoot_position: ShootPosition | None = None


class MediaFileExtension(BaseModel):
    """demo MediaFileExtension - drone sn / payload / flight linkage."""

    sn: str | None = None
    drone_model_key: str | None = None
    payload_model_key: str | None = None
    is_original: bool | None = None
    file_group_id: str | None = None
    flight_id: str | None = None
    # demo wire name is the misspelled "tinny_fingerprint" - accept both
    tiny_fingerprint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tinny_fingerprint", "tiny_fingerprint"),
    )


class MediaUploadCallbackRequest(BaseModel):
    """demo MediaUploadCallbackRequest - pilot reports a completed upload."""

    fingerprint: str
    object_key: str
    name: str | None = None
    path: str | None = None
    sub_file_type: int | None = None
    metadata: MediaFileMetadata | None = None
    ext: MediaFileExtension | None = None
