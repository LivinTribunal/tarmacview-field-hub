"""mqtt status/requests handling - synthetic device messages, no broker needed."""

from app.models.device import OnlineTracker
from app.services import device_registry
from app.services.mqtt_listener import handle_message
from tests.data.mqtt_messages import (
    AIRCRAFT_SN,
    GATEWAY_SN,
    REQUESTS_TOPIC,
    STATUS_TOPIC,
    make_envelope,
    make_topo,
)


def test_update_topo_marks_gateway_and_aircraft_online(db_session):
    """simulated device publishes update_topo -> both devices flip online."""
    replies = handle_message(db_session, STATUS_TOPIC, make_envelope("update_topo", make_topo()))
    db_session.commit()

    assert device_registry.tracker.is_online(GATEWAY_SN)
    assert device_registry.tracker.is_online(AIRCRAFT_SN)

    # ack on status_reply echoing tid/bid with result 0
    assert len(replies) == 1
    topic, payload = replies[0]
    assert topic == f"sys/product/{GATEWAY_SN}/status_reply"
    assert payload["tid"] == "tid-1"
    assert payload["bid"] == "bid-1"
    assert payload["method"] == "update_topo"
    assert payload["data"] == {"result": 0}


def test_update_topo_persists_devices_with_model_identity(db_session):
    """topology upsert stores domain-type-subtype and resolves dictionary names."""
    handle_message(db_session, STATUS_TOPIC, make_envelope("update_topo", make_topo()))
    db_session.commit()

    gateway = device_registry.get_device(db_session, GATEWAY_SN)
    aircraft = device_registry.get_device(db_session, AIRCRAFT_SN)
    assert gateway.model_key == "2-119-0"
    assert gateway.model_name == "DJI RC Plus"
    assert aircraft.model_key == "0-89-0"
    assert aircraft.model_name == "Matrice 350 RTK"
    assert aircraft.gateway_sn == GATEWAY_SN


def test_topo_without_sub_device_marks_aircraft_offline(db_session):
    """a topology without the aircraft means it detached or powered down."""
    handle_message(db_session, STATUS_TOPIC, make_envelope("update_topo", make_topo()))
    handle_message(
        db_session, STATUS_TOPIC, make_envelope("update_topo", make_topo(with_aircraft=False))
    )
    db_session.commit()

    assert device_registry.tracker.is_online(GATEWAY_SN)
    assert not device_registry.tracker.is_online(AIRCRAFT_SN)


def test_online_state_expires_after_ttl(db_session, monkeypatch):
    """device goes silent -> ttl expiry flips it offline without any message."""
    now = [0.0]
    test_tracker = OnlineTracker(ttl_seconds=120.0, clock=lambda: now[0])
    monkeypatch.setattr(device_registry, "tracker", test_tracker)

    handle_message(db_session, STATUS_TOPIC, make_envelope("update_topo", make_topo()))
    db_session.commit()
    assert test_tracker.is_online(AIRCRAFT_SN)

    now[0] = 119.0
    assert test_tracker.is_online(AIRCRAFT_SN)

    now[0] = 121.0
    assert not test_tracker.is_online(AIRCRAFT_SN)
    assert not test_tracker.is_online(GATEWAY_SN)


def test_fresh_status_refreshes_the_ttl(db_session, monkeypatch):
    """status traffic inside the window pushes the offline deadline out."""
    now = [0.0]
    test_tracker = OnlineTracker(ttl_seconds=120.0, clock=lambda: now[0])
    monkeypatch.setattr(device_registry, "tracker", test_tracker)

    handle_message(db_session, STATUS_TOPIC, make_envelope("update_topo", make_topo()))
    now[0] = 100.0
    handle_message(db_session, STATUS_TOPIC, make_envelope("update_topo", make_topo()))
    db_session.commit()

    now[0] = 180.0
    assert test_tracker.is_online(AIRCRAFT_SN)


def test_osd_traffic_refreshes_ttl_for_known_devices(db_session, monkeypatch):
    """telemetry keeps a quiet-but-connected device online past the topo ttl."""
    now = [0.0]
    test_tracker = OnlineTracker(ttl_seconds=120.0, clock=lambda: now[0])
    monkeypatch.setattr(device_registry, "tracker", test_tracker)

    handle_message(db_session, STATUS_TOPIC, make_envelope("update_topo", make_topo()))
    db_session.commit()

    now[0] = 100.0
    assert handle_message(db_session, f"thing/product/{AIRCRAFT_SN}/osd", b"{}") == []

    now[0] = 180.0
    assert test_tracker.is_online(AIRCRAFT_SN)
    assert not test_tracker.is_online(GATEWAY_SN)


def test_telemetry_from_unknown_sn_is_ignored(db_session):
    """osd from a serial the registry never saw creates no row and no state."""
    handle_message(db_session, "thing/product/UNSEEN/osd", b"{}")
    db_session.commit()

    assert device_registry.get_device(db_session, "UNSEEN") is None
    assert not device_registry.tracker.is_online("UNSEEN")


def test_unknown_model_key_degrades_gracefully(db_session):
    """unknown hardware identity persists with no name instead of crashing."""
    data = {"domain": 2, "type": 999, "sub_type": 7, "sub_devices": []}
    handle_message(db_session, STATUS_TOPIC, make_envelope("update_topo", data))
    db_session.commit()

    gateway = device_registry.get_device(db_session, GATEWAY_SN)
    assert gateway.model_key == "2-999-7"
    assert gateway.model_name is None
    assert device_registry.tracker.is_online(GATEWAY_SN)


def test_malformed_payload_is_ignored(db_session):
    """garbage on the wire never raises and never produces replies."""
    assert handle_message(db_session, STATUS_TOPIC, b"not json") == []
    assert handle_message(db_session, STATUS_TOPIC, b'"just a string"') == []


def test_unhandled_methods_get_no_reply(db_session):
    """non-topo status methods and unknown request methods are ignored."""
    assert handle_message(db_session, STATUS_TOPIC, make_envelope("other_method", {})) == []
    unknown = make_envelope("flighttask_resource_get", {})
    assert handle_message(db_session, REQUESTS_TOPIC, unknown) == []


def test_organization_get_replies_with_workspace(db_session):
    """binding flow: organization lookup answered from hub config."""
    replies = handle_message(
        db_session,
        REQUESTS_TOPIC,
        make_envelope("airport_organization_get", {"device_binding_code": "code"}),
    )

    assert len(replies) == 1
    topic, payload = replies[0]
    assert topic == f"thing/product/{GATEWAY_SN}/requests_reply"
    assert payload["tid"] == "tid-1"
    assert payload["data"]["result"] == 0
    assert payload["data"]["output"]["organization_name"]


def test_organization_bind_binds_devices(db_session):
    """binding flow over mqtt persists the binding and reports per-sn results."""
    data = {"bind_devices": [{"sn": GATEWAY_SN, "device_binding_code": "code"}]}
    replies = handle_message(
        db_session, REQUESTS_TOPIC, make_envelope("airport_organization_bind", data)
    )
    db_session.commit()

    _, payload = replies[0]
    assert payload["data"]["output"]["err_infos"] == [{"sn": GATEWAY_SN, "err_code": 0}]
    assert device_registry.get_device(db_session, GATEWAY_SN).is_bound
