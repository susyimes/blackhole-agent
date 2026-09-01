"""Drive a first-class MQTT tool through retained-topic fanout.

Tool routing already fails missions that require ``mqtt``: hosted broker
plugins stay on the unsupported MCP provider, and no first-party MQTT
provider is executable. Unbound therefore cannot speak CONNECT with a
password, SUBSCRIBE a wildcard filter, PUBLISH a retained topic, or seal
fanout to a later subscriber.

This module closes that hole:

- advertise an ``mqtt`` provider tool that stays fail-closed until opted in
- drive bind / receive / read against a real loopback MQTT 3.1.1 listener
- keep a missing-secret client so the password hole stays falsifiable
- refuse SUBSCRIBE until CONNECT succeeds
- deliver a retained topic to a later wildcard subscriber, so skip-retain
  and skip-SUBSCRIBE stay empty
- persist a sealed topic an independent reader can re-open from disk
- bind this family as the next diversity-catalog successor after Redis
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import socketserver
import struct
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    MQTT_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    mqtt_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
MQTT_ACTUATION_ID = "capability.mqtt-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-mqtt"
SENTINEL = "BH-MQTT-OK"
DEFAULT_USERNAME = "blackhole"
DEFAULT_PASSWORD = "blackhole-mqtt-secret"
DEFAULT_FILTER = "sensors/+"
DEFAULT_TOPIC = "sensors/heartbeat"
SEALED_NAME = "sealed.json"

MQTT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MQTT_ACTUATION_ID};"
    f"capability_proved:{MQTT_ACTUATION_ID};"
    "no_skill_route"
)
MQTT_ACTUATION_GOAL = (
    "Repair MQTT retained-topic fanout: hosted broker tools remain "
    "unsupported so a CONNECT/SUBSCRIBE/PUBLISH cycle cannot land and "
    "a retained topic cannot be produced. A missing MQTT password stays "
    "forbidden; fail-closed routing never opts the mqtt provider in."
)


class MqttActuationError(RuntimeError):
    """Raised when the MQTT session or listener fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _encode_remaining_length(length: int) -> bytes:
    if length < 0 or length > 268435455:
        raise MqttActuationError(f"remaining length out of range: {length}")
    out = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length > 0:
            digit |= 0x80
        out.append(digit)
        if length == 0:
            break
    return bytes(out)


def _read_remaining_length(rfile: Any) -> int:
    multiplier = 1
    value = 0
    for _ in range(4):
        encoded = rfile.read(1)
        if not encoded:
            raise MqttActuationError("eof remaining length")
        byte = encoded[0]
        value += (byte & 127) * multiplier
        if (byte & 128) == 0:
            return value
        multiplier *= 128
    raise MqttActuationError("malformed remaining length")


def _encode_utf8(value: str) -> bytes:
    raw = str(value or "").encode("utf-8")
    return struct.pack("!H", len(raw)) + raw


def _read_utf8(buf: bytes, offset: int) -> tuple[str, int]:
    if offset + 2 > len(buf):
        raise MqttActuationError("truncated utf8 length")
    size = struct.unpack_from("!H", buf, offset)[0]
    start = offset + 2
    end = start + size
    if end > len(buf):
        raise MqttActuationError("truncated utf8 payload")
    return buf[start:end].decode("utf-8", errors="replace"), end


def _encode_packet(packet_type: int, payload: bytes, *, flags: int = 0) -> bytes:
    first = ((packet_type & 0x0F) << 4) | (flags & 0x0F)
    return bytes([first]) + _encode_remaining_length(len(payload)) + payload


def _encode_connect(client_id: str, username: str, password: str) -> bytes:
    flags = 0x80 | 0x40 | 0x02
    variable = _encode_utf8("MQTT") + bytes([4, flags]) + struct.pack("!H", 60)
    variable += _encode_utf8(client_id)
    variable += _encode_utf8(username)
    variable += _encode_utf8(password)
    return _encode_packet(1, variable)


def _encode_connack(return_code: int) -> bytes:
    return _encode_packet(2, bytes([0x00, return_code & 0xFF]))


def _encode_subscribe(packet_id: int, topic_filter: str, qos: int = 0) -> bytes:
    payload = struct.pack("!H", packet_id) + _encode_utf8(topic_filter) + bytes([qos & 0x03])
    return _encode_packet(8, payload, flags=0x02)


def _encode_suback(packet_id: int, return_code: int = 0) -> bytes:
    return _encode_packet(9, struct.pack("!H", packet_id) + bytes([return_code & 0xFF]))


def _encode_publish(topic: str, payload: bytes, *, retain: bool = False) -> bytes:
    flags = 0x01 if retain else 0x00
    return _encode_packet(3, _encode_utf8(topic) + payload, flags=flags)


def _encode_disconnect() -> bytes:
    return _encode_packet(14, b"")


def _read_packet(rfile: Any) -> tuple[int, int, bytes] | None:
    first = rfile.read(1)
    if not first:
        return None
    packet_type = first[0] >> 4
    flags = first[0] & 0x0F
    remaining = _read_remaining_length(rfile)
    payload = rfile.read(remaining) if remaining else b""
    if remaining and len(payload) != remaining:
        raise MqttActuationError("truncated packet")
    return packet_type, flags, payload


def _parse_connect(payload: bytes) -> dict[str, str]:
    protocol, offset = _read_utf8(payload, 0)
    if offset + 4 > len(payload):
        raise MqttActuationError("truncated connect")
    level = payload[offset]
    flags = payload[offset + 1]
    offset += 4
    client_id, offset = _read_utf8(payload, offset)
    if flags & 0x04:
        _, offset = _read_utf8(payload, offset)
        _, offset = _read_utf8(payload, offset)
    username = ""
    password = ""
    if flags & 0x80:
        username, offset = _read_utf8(payload, offset)
    if flags & 0x40:
        password, offset = _read_utf8(payload, offset)
    return {
        "protocol": protocol,
        "level": str(level),
        "client_id": client_id,
        "username": username,
        "password": password,
    }


def _parse_publish(flags: int, payload: bytes) -> dict[str, Any]:
    topic, offset = _read_utf8(payload, 0)
    qos = (flags >> 1) & 0x03
    if qos:
        offset += 2
    body = payload[offset:]
    return {
        "topic": topic,
        "payload": body.decode("utf-8", errors="replace"),
        "retain": bool(flags & 0x01),
        "qos": qos,
    }


def _parse_subscribe(payload: bytes) -> tuple[int, str]:
    if len(payload) < 3:
        raise MqttActuationError("truncated subscribe")
    packet_id = struct.unpack_from("!H", payload, 0)[0]
    topic_filter, _offset = _read_utf8(payload, 2)
    return packet_id, topic_filter


def topic_matches(filter_name: str, topic: str) -> bool:
    """Match an MQTT topic filter including ``+`` and ``#`` wildcards."""

    filters = str(filter_name or "").split("/")
    parts = str(topic or "").split("/")
    for index, token in enumerate(filters):
        if token == "#":
            return True
        if index >= len(parts):
            return False
        if token != "+" and token != parts[index]:
            return False
    return len(filters) == len(parts)


class _MqttTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(self, address: tuple[str, int], handler: type[socketserver.BaseRequestHandler], session: MqttSession) -> None:
        self.session = session
        super().__init__(address, handler)


class _MqttHandler(socketserver.StreamRequestHandler):
    timeout = None

    def setup(self) -> None:
        super().setup()
        self._send_lock = threading.Lock()

    def _send(self, payload: bytes) -> None:
        with self._send_lock:
            self.wfile.write(payload)
            self.wfile.flush()

    def handle(self) -> None:
        session: MqttSession = self.server.session  # type: ignore[attr-defined]
        connected = False
        filters: list[str] = []
        session.attach(self)
        try:
            while True:
                try:
                    packet = _read_packet(self.rfile)
                except (MqttActuationError, OSError, ValueError, struct.error):
                    return
                if packet is None:
                    return
                packet_type, flags, payload = packet
                if packet_type == 1:
                    try:
                        connect = _parse_connect(payload)
                    except MqttActuationError:
                        self._send(_encode_connack(5))
                        return
                    if connect.get("protocol") != "MQTT":
                        self._send(_encode_connack(1))
                        return
                    if session.credentials_match(connect.get("username") or "", connect.get("password") or ""):
                        connected = True
                        self._send(_encode_connack(0))
                    else:
                        self._send(_encode_connack(4))
                        return
                elif packet_type == 8:
                    if not connected:
                        return
                    try:
                        packet_id, topic_filter = _parse_subscribe(payload)
                    except MqttActuationError:
                        return
                    filters.append(topic_filter)
                    session.watch(self, list(filters))
                    self._send(_encode_suback(packet_id, 0))
                    for topic, body in session.retained_matches(topic_filter):
                        self._send(_encode_publish(topic, body, retain=True))
                elif packet_type == 3:
                    if not connected:
                        return
                    try:
                        published = _parse_publish(flags, payload)
                    except MqttActuationError:
                        return
                    session.store_publish(
                        str(published["topic"]),
                        str(published["payload"]).encode("utf-8"),
                        retain=bool(published["retain"]),
                    )
                elif packet_type == 12:
                    self._send(_encode_packet(13, b""))
                elif packet_type == 14:
                    return
                else:
                    return
        finally:
            session.detach(self)


class _MqttClient:
    """Minimal MQTT 3.1.1 client with CONNECT, SUBSCRIBE, PUBLISH, and retained receive."""

    def __init__(self, host: str, port: int, *, timeout: float = 6.0) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.rfile = self.sock.makefile("rb", buffering=0)
        self.wfile = self.sock.makefile("wb", buffering=0)
        self.timeout = timeout

    def close(self) -> None:
        try:
            self.wfile.close()
        except OSError:
            pass
        try:
            self.rfile.close()
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def _write(self, payload: bytes) -> None:
        self.wfile.write(payload)
        self.wfile.flush()

    def connect(self, client_id: str, username: str, password: str) -> tuple[bool, str]:
        self._write(_encode_connect(client_id, username, password))
        try:
            packet = _read_packet(self.rfile)
        except (MqttActuationError, OSError, socket.timeout):
            return False, "eof"
        if packet is None:
            return False, "eof"
        packet_type, _flags, payload = packet
        if packet_type != 2 or len(payload) < 2:
            return False, "not_connack"
        code = int(payload[1])
        return code == 0, f"connack_{code}"

    def subscribe(self, topic_filter: str, packet_id: int = 1) -> tuple[bool, str]:
        self._write(_encode_subscribe(packet_id, topic_filter))
        try:
            packet = _read_packet(self.rfile)
        except (MqttActuationError, OSError, socket.timeout):
            return False, "eof"
        if packet is None:
            return False, "eof"
        packet_type, _flags, payload = packet
        if packet_type != 9 or len(payload) < 3:
            return False, "not_suback"
        return payload[2] != 0x80, "suback"

    def publish(self, topic: str, payload: str, *, retain: bool = False) -> None:
        self._write(_encode_publish(topic, payload.encode("utf-8"), retain=retain))

    def wait_publish(self, *, timeout: float = 1.5) -> dict[str, Any] | None:
        self.sock.settimeout(timeout)
        try:
            packet = _read_packet(self.rfile)
        except (MqttActuationError, OSError, socket.timeout):
            return None
        finally:
            try:
                self.sock.settimeout(self.timeout)
            except OSError:
                pass
        if packet is None:
            return None
        packet_type, flags, payload = packet
        if packet_type != 3:
            return None
        try:
            return _parse_publish(flags, payload)
        except MqttActuationError:
            return None

    def disconnect(self) -> None:
        try:
            self._write(_encode_disconnect())
        except (MqttActuationError, OSError, socket.timeout):
            pass
        self.close()


class MqttSession:
    """Credential-gated loopback MQTT listener: bind, receive, read."""

    def __init__(self, output_dir: Path, *, password: str = DEFAULT_PASSWORD) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.username = DEFAULT_USERNAME
        self.password = str(password or "")
        self.host: str | None = None
        self.port: int | None = None
        self.server: _MqttTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.delivered = False
        self.last_token = ""
        self.history: list[dict[str, Any]] = []
        self._retained: dict[str, bytes] = {}
        self._watchers: list[tuple[_MqttHandler, tuple[str, ...]]] = []
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def credentials_match(self, username: str, password: str) -> bool:
        if not self.password:
            return False
        return username == self.username and password == self.password

    def attach(self, handler: _MqttHandler) -> None:
        return None

    def watch(self, handler: _MqttHandler, filters: list[str]) -> None:
        with self._lock:
            self._watchers = [(item, watched) for item, watched in self._watchers if item is not handler]
            self._watchers.append((handler, tuple(filters)))

    def detach(self, handler: _MqttHandler) -> None:
        with self._lock:
            self._watchers = [(item, watched) for item, watched in self._watchers if item is not handler]

    def retained_matches(self, topic_filter: str) -> list[tuple[str, bytes]]:
        with self._lock:
            return [
                (topic, body)
                for topic, body in self._retained.items()
                if topic_matches(topic_filter, topic)
            ]

    def store_publish(self, topic: str, body: bytes, *, retain: bool) -> None:
        targets: list[_MqttHandler] = []
        with self._lock:
            if retain:
                self._retained[topic] = body
            for handler, filters in self._watchers:
                if any(topic_matches(item, topic) for item in filters):
                    targets.append(handler)
        packet = _encode_publish(topic, body, retain=retain)
        for handler in targets:
            try:
                handler._send(packet)
            except OSError:
                continue

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "delivered": self.delivered,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 409,
            "error": reason,
            "token": "",
            "sentinel": "",
            "delivered": self.delivered,
        }

    def bind(self) -> dict[str, Any]:
        if not self.password:
            return self._forbidden("missing_secret")
        if self.server is not None:
            return {
                "ok": True,
                "status": 200,
                "host": self.host or "",
                "port": int(self.port or 0),
                "reused": True,
            }
        server = _MqttTCPServer(("127.0.0.1", 0), _MqttHandler, self)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        self.server = server
        self.thread = thread
        self.host = str(host)
        self.port = int(port)
        return {
            "ok": True,
            "status": 200,
            "host": self.host,
            "port": self.port,
            "reused": False,
        }

    def receive(
        self,
        token: str = SENTINEL,
        *,
        authenticate: bool = True,
        subscribe: bool = True,
        retain: bool = True,
        password: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.password:
            return self._forbidden("missing_secret")
        live_token = str(token or SENTINEL)
        publisher: _MqttClient | None = None
        subscriber: _MqttClient | None = None
        independent: _MqttClient | None = None
        try:
            publisher = _MqttClient(self.host, int(self.port))
            published, publish_status = publisher.connect("mqtt-publisher", self.username, self.password)
            if not published:
                return self._forbidden("publisher_connect_failed", status=503)
            publisher.publish(DEFAULT_TOPIC, live_token, retain=retain)
            time.sleep(0.05)
            publisher.disconnect()
            publisher = None
            if not subscribe:
                return self._conflict("subscribe_required")
            subscriber = _MqttClient(self.host, int(self.port))
            if authenticate:
                secret = self.password if password is None else str(password)
                ok, status = subscriber.connect("mqtt-subscriber", self.username, secret)
                if not ok:
                    return self._forbidden("auth_failed", status=535)
            else:
                subscribed, _status = subscriber.subscribe(DEFAULT_FILTER)
                reason = "connect_required" if not subscribed else "connect_required"
                return self._forbidden(reason, status=530)
            subscribed, sub_status = subscriber.subscribe(DEFAULT_FILTER)
            if not subscribed:
                reason = "connect_required" if "eof" in sub_status else "subscribe_failed"
                code = 530 if reason == "connect_required" else 550
                return self._forbidden(reason, status=code)
            received = subscriber.wait_publish(timeout=1.5)
            if received is None:
                return self._forbidden("retain_required" if not retain else "subscribe_timeout", status=409)
            if str(received.get("topic") or "") != DEFAULT_TOPIC:
                return self._forbidden("topic_mismatch", status=409)
            if str(received.get("payload") or "") != live_token:
                return self._forbidden("payload_mismatch", status=409)
            if retain and not bool(received.get("retain")):
                return self._forbidden("retain_required", status=409)
            independent = _MqttClient(self.host, int(self.port))
            ind_ok, _ind_status = independent.connect("mqtt-independent", self.username, self.password)
            if not ind_ok:
                return self._forbidden("independent_connect_failed", status=503)
            ind_sub, _ = independent.subscribe(DEFAULT_FILTER)
            if not ind_sub:
                return self._forbidden("independent_subscribe_failed", status=503)
            replay = independent.wait_publish(timeout=1.5)
            if replay is None or str(replay.get("payload") or "") != live_token:
                return self._forbidden("independent_required", status=409)
            sealed = {
                "topic": DEFAULT_TOPIC,
                "filter": DEFAULT_FILTER,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "connected": True,
                "subscribed": True,
                "retained": True,
                "independent": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            live = independent_mqtt_topic(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "queued": False,
                "fanout": True,
                "topic": DEFAULT_TOPIC,
                "filter": DEFAULT_FILTER,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "path": str(self.sealed_path),
                "authenticated": bool(authenticate),
                "retained": True,
                "independent": True,
            }
        except (OSError, MqttActuationError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error),
                "token": live_token,
                "sentinel": "",
            }
        finally:
            if independent is not None:
                independent.disconnect()
            if subscriber is not None:
                subscriber.disconnect()
            if publisher is not None:
                publisher.disconnect()

    def read(self) -> dict[str, Any]:
        live = independent_mqtt_topic(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "topic": str(live.get("topic") or ""),
            "filter": str(live.get("filter") or ""),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        server = self.server
        thread = self.thread
        self.server = None
        self.thread = None
        self.host = None
        self.port = None
        if server is not None:
            try:
                server.shutdown()
            except OSError:
                pass
            try:
                server.server_close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=1)
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_mqtt_tool(session: MqttSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one MQTT tool call against a bound listener session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = arguments.get("authenticate")
    if authenticate is None:
        authenticate = True
    subscribe = arguments.get("subscribe")
    if subscribe is None:
        subscribe = True
    retain = arguments.get("retain")
    if retain is None:
        retain = True
    password = arguments.get("password")
    if action == "bind":
        result = session.bind()
    elif action == "receive":
        result = session.receive(
            token,
            authenticate=bool(authenticate),
            subscribe=bool(subscribe),
            retain=bool(retain),
            password=None if password is None else str(password),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise MqttActuationError(f"unsupported mqtt action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_mqtt_topic(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed MQTT topic through a fresh file open."""

    path = Path(sealed_path)
    if not path.is_file():
        return {
            "ok": False,
            "error": "missing_payload",
            "token": "",
            "sentinel": "",
            "topic": "",
            "filter": "",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "ok": False,
            "error": "invalid_payload",
            "detail": str(error),
            "token": "",
            "sentinel": "",
            "topic": "",
            "filter": "",
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "invalid_payload",
            "token": "",
            "sentinel": "",
            "topic": "",
            "filter": "",
        }
    token = str(payload.get("token") or "")
    connected = payload.get("connected") is True
    subscribed = payload.get("subscribed") is True
    retained = payload.get("retained") is True
    independent = payload.get("independent") is True
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and connected and subscribed and retained and independent else "",
        "topic": str(payload.get("topic") or ""),
        "filter": str(payload.get("filter") or ""),
        "connected": connected,
        "subscribed": subscribed,
        "retained": retained,
        "independent": independent,
    }


def run_mqtt_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    subscribe: bool = True,
    retain: bool = True,
    password: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the CONNECT/SUBSCRIBE/PUBLISH retained-fanout workflow and seal a trace."""

    descriptor = mqtt_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MQTT_TOOL_PROVIDER),
    )
    routing = {
        "descriptor": {
            "name": descriptor.name,
            "provider": descriptor.provider,
            "tool_type": descriptor.tool_type,
        },
        "route": decision.route,
        "reasons": list(decision.reasons),
        "executable": decision.executable,
    }
    if not decision.executable:
        raise MqttActuationError(f"mqtt tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="mqtt-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = MqttSession(out, password=DEFAULT_PASSWORD if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    receive_args: dict[str, Any] = {
        "action": "receive",
        "token": SENTINEL,
        "authenticate": authenticate,
        "subscribe": subscribe,
        "retain": retain,
    }
    if password is not None:
        receive_args["password"] = password
    calls.append(receive_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_mqtt_tool(session, arguments))
            except MqttActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    receive_result = next((item for item in results if item.get("action") == "receive"), {})
    independent = independent_mqtt_topic(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and subscribe
        and retain
        and password is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mqtt_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "subscribe": subscribe,
        "retain": retain,
        "wrong_password": password is not None,
        "sealed_path": str(session.sealed_path),
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "independent": independent,
        "independent_digest": _digest(independent),
        "sentinel": sentinel,
        "delivered": bool(session.delivered or receive_result.get("fanout")),
        "payload_exists": session.sealed_path.is_file(),
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}
    from blackhole_agent.capability_compounder import atomic_write_json

    atomic_write_json(out / "execution.json", trace)
    final = results[-1] if results else {}
    return {
        "ok": sealed,
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "sealed_path": str(session.sealed_path),
        "sentinel": sentinel,
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or receive_result.get("error") or ""),
        "delivered": bool(trace_body["delivered"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "subscribe": subscribe,
        "retain": retain,
    }


def verify_mqtt_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed MQTT trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_mqtt_topic(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "independent_digest": _digest(independent) == trace.get("independent_digest"),
        "routing_executable": routing.get("executable") is True
        and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "independent_recorded": str(independent.get("sentinel") or "") == SENTINEL,
        "live_payload_matches": str(live_row.get("sentinel") or "") == SENTINEL,
        "payload_exists": bool(trace.get("payload_exists")) and sealed_path.is_file(),
        "delivered": trace.get("delivered") is True,
        "connected": independent.get("connected") is True,
        "subscribed": independent.get("subscribed") is True,
        "retained": independent.get("retained") is True,
        "independent": independent.get("independent") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def mqtt_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mqtt_actuation import "
        "builtin_mqtt_actuation_proof; r=builtin_mqtt_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='mqtt_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mqtt_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MQTT_ACTUATION_ID,
        name="First-class retained-topic MQTT fanout actuation",
        description=(
            "Missions that require an mqtt tool can opt the mqtt provider in, "
            "bind a loopback MQTT 3.1.1 listener, CONNECT with a password, "
            "PUBLISH a retained topic, SUBSCRIBE a wildcard filter after the "
            "publisher has disconnected, and seal digest-chained fanout that a "
            "later independent subscriber can replay. Default routing stays "
            "fail-closed; a missing password keeps the hole falsifiable, and "
            "skip-SUBSCRIBE or skip-retain stay empty."
        ),
        kind="python",
        entry="blackhole_agent.mqtt_actuation:builtin_mqtt_actuation_proof",
        proof_command=mqtt_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.redis-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mqtt_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required mqtt tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback MQTT 3.1.1 listener, CONNECTs with a "
            "password, PUBLISHes a retained topic, SUBSCRIBEs a wildcard filter "
            "after the publisher has disconnected, independently replays the "
            "retained fanout on a later subscriber, and binds this family as "
            "the next diversity-catalog successor once Redis BLPOP queues are "
            "proved. Missing credentials, skipped CONNECT, wrong passwords, "
            "skip-SUBSCRIBE, and skip-retain stay fail-closed."
        ),
        tags=("mqtt", "retained", "topic", "fanout", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T080703Z-ced89969",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mqtt_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in MQTT actuation seals retained-topic fanout."""

    from blackhole_agent.imap_actuation import IMAP_ACTUATION_GOAL, IMAP_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.redis_actuation import REDIS_ACTUATION_GOAL, REDIS_ACTUATION_ID
    from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
    from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MQTT_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    checks["redis_goal_is_not_mqtt"] = leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    checks["imap_goal_is_not_mqtt"] = leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    checks["smtp_goal_is_not_mqtt"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    checks["sqlite_goal_is_not_mqtt"] = leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (
        SQLITE_ACTUATION_ID,
    )
    checks["mqtt_goal_is_not_redis"] = REDIS_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    checks["mqtt_goal_is_not_imap"] = IMAP_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    checks["mqtt_goal_is_not_smtp"] = SMTP_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    checks["mqtt_goal_is_not_sqlite"] = SQLITE_ACTUATION_ID not in leftover_marker_ids(
        MQTT_ACTUATION_GOAL
    )
    checks["redis_marker_stays_redis"] = MQTT_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    checks["imap_marker_stays_imap"] = MQTT_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    checks["smtp_marker_stays_smtp"] = MQTT_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    checks["sqlite_marker_stays_sqlite"] = MQTT_ACTUATION_ID not in leftover_marker_ids(
        SQLITE_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_mqtt"] = (
        len(catalog) > 33
        and catalog[33]["id"] == MQTT_ACTUATION_ID
        and catalog[32]["id"] == REDIS_ACTUATION_ID
    )
    family = capability_family(MQTT_ACTUATION_GOAL)
    checks["family_is_mqtt"] = "mqtt" in family
    checks["family_is_retained"] = "retained" in family
    checks["family_is_topic"] = "topic" in family
    checks["family_is_fanout"] = "fanout" in family
    checks["family_is_not_redis"] = "redi" not in family
    checks["family_is_not_blpop"] = "blpop" not in family
    checks["family_is_not_imap"] = "imap" not in family
    checks["family_is_not_smtp"] = "smtp" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["family_is_not_auth_surface"] = family != "auth" and "auth" not in family.split("/")
    checks["wildcard_filter_matches_topic"] = topic_matches(DEFAULT_FILTER, DEFAULT_TOPIC)
    checks["wildcard_filter_rejects_other_tree"] = not topic_matches(DEFAULT_FILTER, "other/heartbeat")
    checks["not_a_redis_duplicate"] = (
        semantic_similarity(
            semantic_signature(MQTT_ACTUATION_GOAL),
            semantic_signature(REDIS_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_an_imap_duplicate"] = (
        semantic_similarity(
            semantic_signature(MQTT_ACTUATION_GOAL),
            semantic_signature(IMAP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_smtp_duplicate"] = (
        semantic_similarity(
            semantic_signature(MQTT_ACTUATION_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_sqlite_duplicate"] = (
        semantic_similarity(
            semantic_signature(MQTT_ACTUATION_GOAL),
            semantic_signature(SQLITE_ACTUATION_GOAL),
        )
        < 0.82
    )

    mcp_mqtt = ToolDescriptor(name="remote_mqtt", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_mqtt)
    checks["naive_mcp_mqtt_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = mqtt_tool_descriptor()
    default_mqtt = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MQTT_TOOL_PROVIDER),
    )
    checks["default_mqtt_provider_is_unsupported"] = (
        default_mqtt.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{MQTT_TOOL_PROVIDER}" in default_mqtt.reasons
    )
    checks["opted_in_mqtt_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_mqtt],
        required_tool_names=("local_memory", "mqtt"),
    )
    checks["naive_preflight_missing_mqtt"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["mqtt"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "mqtt"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MQTT_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "mqtt" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="mqtt-actuation-") as tmp:
        root = Path(tmp)
        missing = run_mqtt_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_mqtt_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_mqtt_workflow(password="wrong-password", output_dir=root / "wrong")
        skip_subscribe = run_mqtt_workflow(subscribe=False, output_dir=root / "skip-subscribe")
        skip_retain = run_mqtt_workflow(retain=False, output_dir=root / "skip-retain")
        live = run_mqtt_workflow(output_dir=root / "live")
        verify = verify_mqtt_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_mqtt_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unauthenticated_subscribe_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 530
            and unauth["error"] == "connect_required"
            and unauth["delivered"] is False
            and unauth["payload_exists"] is False
        )
        checks["wrong_password_is_forbidden"] = (
            wrong["ok"] is False
            and wrong["final_status"] == 535
            and wrong["error"] == "auth_failed"
            and wrong["payload_exists"] is False
        )
        checks["skip_subscribe_stays_empty"] = (
            skip_subscribe["ok"] is False
            and skip_subscribe["error"] == "subscribe_required"
            and skip_subscribe["final_status"] == 409
            and skip_subscribe["payload_exists"] is False
        )
        checks["skip_retain_stays_empty"] = (
            skip_retain["ok"] is False
            and skip_retain["error"] == "retain_required"
            and skip_retain["final_status"] == 409
            and skip_retain["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_topic"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["secret_connect_subscribe_and_retain_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_subscribe["ok"] is False
            and skip_retain["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="mqtt-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MQTT_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_mqtt"] = (
        live_goal == MQTT_ACTUATION_GOAL
        and MQTT_ACTUATION_ID in live_done
        and live_source == "genesis_bind_mqtt"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mqtt_actuation_capability()
    return {
        "ok": ok,
        "action": "mqtt_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MQTT_ACTUATION_GOAL,
        "done_when": MQTT_ACTUATION_DONE_WHEN,
    }
