"""mqtt listener - status/requests topic handling per the cloud api contract."""

import asyncio
import json
import logging
import ssl
import time

import aiomqtt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.services import device_registry, storage_service

logger = logging.getLogger(__name__)

STATUS_TOPIC_PREFIX = "sys/product/"
STATUS_TOPIC_SUFFIX = "/status"
THING_TOPIC_PREFIX = "thing/product/"
REQUESTS_TOPIC_SUFFIX = "/requests"

# telemetry topics refresh the online ttl - pilot sends update_topo only on
# connect/topology change, so a quiet-but-connected device stays online
# through its osd/state traffic (the demo's redis-ttl behavior)
TELEMETRY_TOPIC_SUFFIXES = ("/osd", "/state")

METHOD_UPDATE_TOPO = "update_topo"
METHOD_ORGANIZATION_GET = "airport_organization_get"
METHOD_ORGANIZATION_BIND = "airport_organization_bind"
METHOD_STORAGE_CONFIG_GET = "storage_config_get"

RESULT_OK = 0
RESULT_ERROR = 1

# (topic, payload) pairs the listener publishes back
Reply = tuple[str, dict]


def _now_ms() -> int:
    """current epoch milliseconds for reply timestamps."""
    return int(time.time() * 1000)


def _reply_envelope(request: dict, method: str, data: dict) -> dict:
    """reply envelope echoing the request's tid/bid."""
    return {
        "tid": request.get("tid"),
        "bid": request.get("bid"),
        "timestamp": _now_ms(),
        "method": method,
        "data": data,
    }


def _topic_sn(topic: str, prefix: str, suffix: str) -> str:
    """serial segment of a device topic."""
    return topic[len(prefix) : -len(suffix)]


def _handle_status(db: Session, sn: str, message: dict) -> list[Reply]:
    """lifecycle topic: update_topo refreshes the registry and gets acked."""
    if message.get("method") != METHOD_UPDATE_TOPO:
        return []
    device_registry.apply_update_topo(db, sn, message.get("data") or {})
    ack = _reply_envelope(message, METHOD_UPDATE_TOPO, {"result": RESULT_OK})
    return [(f"{STATUS_TOPIC_PREFIX}{sn}{STATUS_TOPIC_SUFFIX}_reply", ack)]


def _handle_requests(db: Session, sn: str, message: dict) -> list[Reply]:
    """requests topic: binding-flow methods answered from hub config/registry."""
    method = message.get("method")
    data = message.get("data") or {}

    if method == METHOD_ORGANIZATION_GET:
        output = {
            "organization_id": settings.workspace_id,
            "organization_name": settings.workspace_name,
        }
    elif method == METHOD_STORAGE_CONFIG_GET:
        # same payload source as the http sts endpoint; an unreachable object
        # store answers result 1 instead of crashing the listener
        try:
            output = storage_service.storage_config_payload().model_dump()
        except Exception:
            logger.warning("storage config unavailable for %s", sn, exc_info=True)
            reply = _reply_envelope(message, method, {"result": RESULT_ERROR})
            return [(f"{THING_TOPIC_PREFIX}{sn}{REQUESTS_TOPIC_SUFFIX}_reply", reply)]
    elif method == METHOD_ORGANIZATION_BIND:
        err_infos = []
        for entry in data.get("bind_devices") or []:
            bind_sn = entry.get("sn")
            if not bind_sn:
                continue
            device_registry.bind_device(db, bind_sn)
            err_infos.append({"sn": bind_sn, "err_code": RESULT_OK})
        output = {"err_infos": err_infos}
    else:
        logger.debug("ignoring requests method %s from %s", method, sn)
        return []

    reply = _reply_envelope(message, method, {"result": RESULT_OK, "output": output})
    return [(f"{THING_TOPIC_PREFIX}{sn}{REQUESTS_TOPIC_SUFFIX}_reply", reply)]


def handle_message(db: Session, topic: str, payload: bytes) -> list[Reply]:
    """route one inbound mqtt message, returning the replies to publish."""

    # telemetry only refreshes the ttl - payload content is not needed
    if topic.startswith(THING_TOPIC_PREFIX):
        for suffix in TELEMETRY_TOPIC_SUFFIXES:
            if topic.endswith(suffix):
                device_registry.refresh_online(db, _topic_sn(topic, THING_TOPIC_PREFIX, suffix))
                return []

    try:
        message = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        logger.warning("unparseable payload on %s", topic)
        return []
    if not isinstance(message, dict):
        logger.warning("non-object payload on %s", topic)
        return []

    if topic.startswith(STATUS_TOPIC_PREFIX) and topic.endswith(STATUS_TOPIC_SUFFIX):
        sn = _topic_sn(topic, STATUS_TOPIC_PREFIX, STATUS_TOPIC_SUFFIX)
        return _handle_status(db, sn, message)
    if topic.startswith(THING_TOPIC_PREFIX) and topic.endswith(REQUESTS_TOPIC_SUFFIX):
        sn = _topic_sn(topic, THING_TOPIC_PREFIX, REQUESTS_TOPIC_SUFFIX)
        return _handle_requests(db, sn, message)

    logger.debug("ignoring topic %s", topic)
    return []


class MqttListener:
    """broker connection that dispatches device messages for the app's lifetime."""

    def __init__(self):
        """start disconnected; run() flips the flag while attached."""
        self.connected = False

    def _tls_context(self) -> ssl.SSLContext | None:
        """ssl context trusting the local ca, none for plain tcp."""
        if not settings.mqtt_tls:
            return None
        return ssl.create_default_context(cafile=str(settings.mqtt_tls_ca))

    async def _consume(self, client: aiomqtt.Client) -> None:
        """subscribe the bootstrap set and dispatch messages until disconnect."""
        await client.subscribe(f"{STATUS_TOPIC_PREFIX}+{STATUS_TOPIC_SUFFIX}")
        await client.subscribe(f"{THING_TOPIC_PREFIX}+{REQUESTS_TOPIC_SUFFIX}")
        for suffix in TELEMETRY_TOPIC_SUFFIXES:
            await client.subscribe(f"{THING_TOPIC_PREFIX}+{suffix}")
        async for message in client.messages:
            db = SessionLocal()
            try:
                replies = handle_message(db, str(message.topic), bytes(message.payload))
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("failed handling %s", message.topic)
                continue
            finally:
                db.close()
            for topic, payload in replies:
                await client.publish(topic, json.dumps(payload))

    async def run(self) -> None:
        """connect-and-consume loop with reconnect backoff."""
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=settings.mqtt_host,
                    port=settings.mqtt_port,
                    tls_context=self._tls_context(),
                    identifier="tarmacview-fieldhub",
                ) as client:
                    self.connected = True
                    logger.info("mqtt listener attached to %s", settings.mqtt_host)
                    await self._consume(client)
            except asyncio.CancelledError:
                self.connected = False
                raise
            except aiomqtt.MqttError as exc:
                self.connected = False
                logger.warning("mqtt connection lost (%s), retrying", exc)
                await asyncio.sleep(settings.mqtt_reconnect_delay_s)
            except Exception:
                self.connected = False
                logger.exception("mqtt listener crashed, retrying")
                await asyncio.sleep(settings.mqtt_reconnect_delay_s)


# process-wide listener - started by the app lifespan when mqtt is enabled
listener = MqttListener()
