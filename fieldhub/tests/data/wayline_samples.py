"""recorded wayline payloads from the dji cloud api demo v1.10.

the list item is the GetWaylineListResponse sample documented in
docs/specs/dji-cloud-api-reference.md section 3.2 - the contract oracle the
wayline endpoints are tested against.
"""

# demo GetWaylineListResponse item - field set pilot 2 renders in its route library
RECORDED_LIST_ITEM = {
    "id": "5f8b9c1e-2d3a-4b5c-8e7f-1a2b3c4d5e6f",
    "name": "RWY22 PAPI inspection",
    "drone_model_key": "0-89-0",
    "payload_model_keys": ["1-53-0"],
    "template_types": [0],
    "object_key": "wayline/5f8b9c1e-2d3a-4b5c-8e7f-1a2b3c4d5e6f.kmz",
    "sign": "0a1b2c3d4e5f60718293a4b5c6d7e8f9",
    "favorited": False,
    "username": "pilot",
    "create_time": 1733700000000,
    "update_time": 1733700000000,
}

# the exact key set of the recorded item - the list endpoint must not drop or rename
RECORDED_ITEM_FIELDS = set(RECORDED_LIST_ITEM)

# demo paging envelope keys on every list payload
RECORDED_PAGINATION_FIELDS = {"page", "page_size", "total"}

# minimal valid kmz stand-in for register uploads (content is opaque to the hub)
SAMPLE_KMZ_BYTES = b"PK\x03\x04wpmz-sample"

# register form the tarmacview backend posts on dispatch
SAMPLE_REGISTER_FORM = {
    "wayline_id": RECORDED_LIST_ITEM["id"],
    "mission_id": "0e3df1c6-7a88-4ce2-9b6e-2f1d4c5b6a70",
    "name": RECORDED_LIST_ITEM["name"],
    "object_key": RECORDED_LIST_ITEM["object_key"],
    "drone_model_key": RECORDED_LIST_ITEM["drone_model_key"],
    "payload_model_keys": ",".join(RECORDED_LIST_ITEM["payload_model_keys"]),
    "sign": RECORDED_LIST_ITEM["sign"],
}
