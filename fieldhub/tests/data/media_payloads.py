"""synthetic media payloads mirroring pilot's wire shapes."""

from tests.data.mqtt_messages import AIRCRAFT_SN

FINGERPRINT = "d8e1a2c3b4f5061728394a5b6c7d8e9f"
TINY_FINGERPRINT = "tiny-1a2b3c4d"
OBJECT_KEY = "media/DJI_20260609142133_0001.JPG"
CREATED_TIME = "2026-06-09T14:21:33+02:00"
SHOOT_LAT = 48.17
SHOOT_LNG = 17.21
ABSOLUTE_ALTITUDE = 423.6


def make_upload_callback(
    fingerprint: str = FINGERPRINT,
    object_key: str = OBJECT_KEY,
    sn: str = AIRCRAFT_SN,
    **overrides,
) -> dict:
    """upload-callback body as pilot posts it after a completed upload."""
    payload = {
        "fingerprint": fingerprint,
        "name": "DJI_20260609142133_0001.JPG",
        "path": "DJI_202606091421_001/DJI_20260609142133_0001.JPG",
        "object_key": object_key,
        "sub_file_type": 0,
        "metadata": {
            "absolute_altitude": ABSOLUTE_ALTITUDE,
            "relative_altitude": 38.2,
            "gimbal_yaw_degree": -87.5,
            "created_time": CREATED_TIME,
            "shoot_position": {"lat": SHOOT_LAT, "lng": SHOOT_LNG},
        },
        "ext": {
            "sn": sn,
            "drone_model_key": "0-89-0",
            "payload_model_key": "1-53-0",
            "is_original": True,
            "file_group_id": "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
            "flight_id": "3f2e1d0c-9b8a-4756-8493-21f0e9d8c7b6",
            "tinny_fingerprint": TINY_FINGERPRINT,
        },
    }
    payload.update(overrides)
    return payload
