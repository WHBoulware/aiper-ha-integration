"""AWS IoT MQTT layer for Aiper devices.

The app talks to robots over AWS IoT Core using an MQTT-over-WebSocket
connection authenticated with temporary AWS credentials obtained from
Amazon Cognito (the ``users/getOpenIdToken`` response carries the IoT
endpoint and the Cognito identity id).

It then:
  * subscribes to ``$aws/things/{sn}/shadow/update/accepted`` and the Aiper
    custom report topics for live state, and
  * publishes commands to ``aiper/things/{sn}/cloud/app/downChan`` and/or the
    device shadow ``$aws/things/{sn}/shadow/update``.

What is confirmed from the binary: the endpoint/identity provisioning flow,
the topic names, and that commands are routed BLE-first / IoT-fallback by
``AiperTransportService``.

What is NOT confirmed from the binary and needs ONE capture to finish: the
exact *byte layout* of a command payload (it is protobuf / a small binary
frame, not plain JSON). ``build_command`` below is a clearly-marked
placeholder. Until it is filled in from a capture, this module can still
read live state; it just won't send control commands.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .const import (
    TOPIC_CLOUD_APP_DOWN,
    TOPIC_SHADOW_REPORT,
    TOPIC_SHADOW_UPDATE,
    TOPIC_SHADOW_UPDATE_ACCEPTED,
    TOPIC_APP_REPORT,
)

_LOGGER = logging.getLogger(__name__)


class AiperMqtt:
    """Thin wrapper around awsiotsdk's MQTT-over-WebSocket client.

    Kept optional: if awsiotsdk / credentials are unavailable, the
    integration degrades to REST polling only.
    """

    def __init__(self, iot_model: dict[str, Any]) -> None:
        self._iot_model = iot_model
        self._connection = None
        self._listeners: dict[str, Callable[[str, dict], None]] = {}

    @property
    def endpoint(self) -> str | None:
        return (
            self._iot_model.get("iotEndpoint")
            or self._iot_model.get("endpoint")
            or self._iot_model.get("host")
        )

    async def async_connect(self) -> bool:
        """Open the Cognito-signed WebSocket.

        Returns False (instead of raising) so the coordinator can continue in
        poll-only mode if MQTT can't be established.
        """
        try:
            from awscrt import auth, mqtt
            from awsiot import mqtt_connection_builder
        except ImportError:
            _LOGGER.warning("awsiotsdk not installed; MQTT disabled (poll-only)")
            return False

        endpoint = self.endpoint
        creds = _extract_credentials(self._iot_model)
        if not endpoint or not creds:
            _LOGGER.warning(
                "IoT model missing endpoint/credentials; MQTT disabled. keys=%s",
                list(self._iot_model.keys()),
            )
            return False

        try:
            provider = auth.AwsCredentialsProvider.new_static(
                access_key_id=creds["access_key_id"],
                secret_access_key=creds["secret_access_key"],
                session_token=creds.get("session_token"),
            )
            self._connection = mqtt_connection_builder.websockets_with_default_aws_signing(
                endpoint=endpoint,
                region=creds["region"],
                credentials_provider=provider,
                client_id=creds.get("client_id") or creds["identity_id"],
                keep_alive_secs=30,
            )
            future = self._connection.connect()
            future.result(timeout=15)
            _LOGGER.info("Connected to AWS IoT endpoint %s", endpoint)
            return True
        except Exception as err:  # noqa: BLE001 - degrade gracefully
            _LOGGER.warning("AWS IoT connect failed (%s); poll-only mode", err)
            self._connection = None
            return False

    def subscribe_device(self, sn: str, on_state: Callable[[str, dict], None]) -> None:
        """Subscribe to all state topics for one device serial."""
        if not self._connection:
            return
        from awscrt import mqtt

        self._listeners[sn] = on_state
        for topic in (
            TOPIC_SHADOW_UPDATE_ACCEPTED.format(sn=sn),
            TOPIC_SHADOW_REPORT.format(sn=sn),
            TOPIC_APP_REPORT.format(sn=sn),
        ):
            self._connection.subscribe(
                topic=topic, qos=mqtt.QoS.AT_LEAST_ONCE, callback=self._make_cb(sn)
            )

    def _make_cb(self, sn: str):
        def _cb(topic: str, payload: bytes, **_: Any) -> None:
            state = _decode_state(topic, payload)
            if state and (listener := self._listeners.get(sn)):
                listener(topic, state)

        return _cb

    def publish_command(self, sn: str, command: str, params: dict[str, Any] | None = None) -> bool:
        """Publish a control command to a device.

        Returns False if the command layer is not yet calibrated (see
        build_command) or MQTT is unavailable.
        """
        if not self._connection:
            return False
        from awscrt import mqtt

        frame = build_command(command, params or {})
        if frame is None:
            _LOGGER.warning(
                "Command '%s' not calibrated yet. Run one capture (tools/"
                "capture_guide.md) and fill in build_command().",
                command,
            )
            return False

        topic = TOPIC_CLOUD_APP_DOWN.format(sn=sn)
        self._connection.publish(topic=topic, payload=frame, qos=mqtt.QoS.AT_LEAST_ONCE)
        return True

    async def async_disconnect(self) -> None:
        if self._connection:
            try:
                self._connection.disconnect().result(timeout=5)
            except Exception:  # noqa: BLE001
                pass
            self._connection = None


# --------------------------------------------------------------------------
# Payload codecs.  decode is best-effort (JSON or shadow); encode is the
# part that needs a capture.
# --------------------------------------------------------------------------
def _decode_state(topic: str, payload: bytes) -> dict[str, Any]:
    """Best-effort decode of an inbound state message.

    Shadow messages are JSON. The Aiper custom report topics may be binary
    (protobuf); those are returned raw for the parser once calibrated.
    """
    try:
        doc = json.loads(payload.decode())
    except (ValueError, UnicodeDecodeError):
        return {"_binary": payload.hex()}
    # Shadow docs look like {"state": {"reported": {...}}}
    if isinstance(doc, dict) and "state" in doc:
        return doc["state"].get("reported", doc["state"])
    return doc


def build_command(command: str, params: dict[str, Any]) -> bytes | None:
    """Encode a control command into the on-wire frame.

    NEEDS CAPTURE. The app frames commands as a small binary/protobuf packet
    (``acceptPacket(index:payload:)`` / ``__swift5_proto``), not plain JSON,
    so this cannot be reconstructed from the binary's strings alone.

    To calibrate: run tools/capture_guide.md, press Start / Stop / Recall in
    the real app once each, copy the bytes published to
    ``aiper/things/{sn}/cloud/app/downChan`` and map them here, e.g.::

        TABLE = {
            "start":  bytes.fromhex("...."),
            "stop":   bytes.fromhex("...."),
            "recall": bytes.fromhex("...."),
        }
        return TABLE.get(command)

    Some models also accept a desired-shadow command; if your capture shows a
    JSON shadow write instead, return::

        return json.dumps({"state": {"desired": {"workStatus": 1}}}).encode()
    """
    return None


def _extract_credentials(iot_model: dict[str, Any]) -> dict[str, Any] | None:
    """Pull AWS creds out of the getOpenIdToken response.

    The response shape varies by build. We accept either (a) ready-made
    temporary credentials, or (b) a Cognito identity id + OpenID token that
    must be exchanged via cognito-identity GetCredentialsForIdentity.
    """
    cred = iot_model.get("credentials") or iot_model
    access = cred.get("accessKeyId") or cred.get("AccessKeyId")
    secret = cred.get("secretKey") or cred.get("secretAccessKey") or cred.get("SecretKey")
    region = (
        iot_model.get("region")
        or _region_from_endpoint(iot_model.get("iotEndpoint") or iot_model.get("endpoint", ""))
    )
    if access and secret:
        return {
            "access_key_id": access,
            "secret_access_key": secret,
            "session_token": cred.get("sessionToken") or cred.get("SessionToken"),
            "identity_id": iot_model.get("identityId"),
            "client_id": iot_model.get("clientId"),
            "region": region,
        }
    # Case (b): only identity id + token present. Exchanging these for AWS
    # creds requires the Cognito identity pool id, which is read at runtime
    # from the getOpenIdToken response if present.
    _LOGGER.debug(
        "IoT model has no ready credentials; Cognito exchange needed. keys=%s",
        list(iot_model.keys()),
    )
    return None


def _region_from_endpoint(endpoint: str) -> str:
    # e.g. xxxx-ats.iot.us-east-1.amazonaws.com
    parts = endpoint.split(".")
    for i, p in enumerate(parts):
        if p == "iot" and i + 1 < len(parts):
            return parts[i + 1]
    return "us-east-1"
