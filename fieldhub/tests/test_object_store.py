"""object-store client wiring - presigning must stay network-free."""

from app.core.config import settings
from app.services import object_store


def test_clients_carry_region_so_presigning_makes_no_network_call():
    """region is set on the client, so minio-py never does a live GetBucketLocation.

    an unset region makes presigning fetch the region over the network, which
    hangs against the device-facing host (unreachable from the hub by design).
    """
    internal = object_store._client_for(settings.minio_endpoint)
    public = object_store._client_for("http://192.168.8.100:8080")

    assert internal._base_url.region == settings.minio_region
    assert public._base_url.region == settings.minio_region
