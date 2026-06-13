"""synthetic mqtt payload builders mirroring pilot's wire shapes."""

import json

GATEWAY_SN = "5YSZK1400B00A1"
AIRCRAFT_SN = "1ZNBJ7R0010078"

STATUS_TOPIC = f"sys/product/{GATEWAY_SN}/status"
REQUESTS_TOPIC = f"thing/product/{GATEWAY_SN}/requests"


def make_envelope(method: str, data: dict, tid: str = "tid-1", bid: str = "bid-1") -> bytes:
    """request envelope bytes as a device publishes them."""
    return json.dumps(
        {"tid": tid, "bid": bid, "timestamp": 1733700000000, "method": method, "data": data}
    ).encode()


def make_topo(with_aircraft: bool = True, aircraft_sn: str = AIRCRAFT_SN) -> dict:
    """update_topo payload: rc plus gateway, optionally with an m350 sub-device."""
    data: dict = {"domain": 2, "type": 119, "sub_type": 0, "sub_devices": []}
    if with_aircraft:
        data["sub_devices"].append(
            {"sn": aircraft_sn, "domain": 0, "type": 89, "sub_type": 0, "index": "A"}
        )
    return data
