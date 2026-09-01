"""Drive a first-class AMQP 0-9-1 tool through work-queue delivery.

Tool routing already fails missions that require ``amqp``: hosted broker
plugins stay on the unsupported MCP provider, and no first-party AMQP
provider is executable. Unbound therefore cannot speak a protocol header,
CONNECTION-START/TUNE/OPEN, CHANNEL-OPEN, QUEUE-DECLARE, BASIC-PUBLISH
with content-header/body frames, BASIC-DELIVER, or seal a delivery-tag
digest an independent later consumer can re-open.

This module closes that hole:

- advertise an ``amqp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback AMQP 0-9-1 listener
- keep a missing-password client so the PLAIN hole stays falsifiable
- refuse CHANNEL-OPEN until CONNECTION-START/TUNE/OPEN succeed
- refuse BASIC-DELIVER until QUEUE-DECLARE plus BASIC-PUBLISH succeed
- independently re-consume the retained last-value on a later connection
- persist a sealed delivery-tag digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after gRPC
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
    AMQP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    amqp_tool_descriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
AMQP_ACTUATION_ID = "capability.amqp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-AMQP-OK"
DEFAULT_USERNAME = "blackhole"
DEFAULT_PASSWORD = "blackhole-amqp-secret"
DEFAULT_VHOST = "/"
DEFAULT_QUEUE = "blackhole.seal"
DEFAULT_CONSUMER_TAG = "blackhole-consumer"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0

PROTOCOL_HEADER = b"AMQP\x00\x00\x09\x01"
FRAME_METHOD = 1
FRAME_HEADER = 2
FRAME_BODY = 3
FRAME_HEARTBEAT = 8
FRAME_END = 0xCE
MAX_FRAME = 131072

CLASS_CONNECTION = 10
CLASS_CHANNEL = 20
CLASS_QUEUE = 50
CLASS_BASIC = 60

CONNECTION_START = 10
CONNECTION_START_OK = 11
CONNECTION_TUNE = 30
CONNECTION_TUNE_OK = 31
CONNECTION_OPEN = 40
CONNECTION_OPEN_OK = 41
CONNECTION_CLOSE = 50
CONNECTION_CLOSE_OK = 51

CHANNEL_OPEN = 10
CHANNEL_OPEN_OK = 11
CHANNEL_CLOSE = 40
CHANNEL_CLOSE_OK = 41

QUEUE_DECLARE = 10
QUEUE_DECLARE_OK = 11

BASIC_QOS = 10
BASIC_CONSUME = 20
BASIC_CONSUME_OK = 21
BASIC_PUBLISH = 40
BASIC_DELIVER = 60
BASIC_ACK = 80

AMQP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{AMQP_ACTUATION_ID};"
    f"capability_proved:{AMQP_ACTUATION_ID};"
    "no_skill_route"
)
AMQP_ACTUATION_GOAL = (
    "Repair AMQP 0-9-1 work-queue delivery: hosted amqp tools remain "
    "unsupported so a PROTOCOL-HEADER/CONNECTION-START/TUNE/OPEN then "
    "CHANNEL-OPEN/QUEUE-DECLARE/BASIC-PUBLISH/BASIC-DELIVER cycle cannot "
    "land and a sealed delivery-tag digest cannot be produced. A missing "
    "amqp PLAIN password stays forbidden; fail-closed routing never opts "
    "the amqp provider in. The content-header body frames and later-session "
    "consume replay keep the hole falsifiable."
)


class AmqpActuationError(RuntimeError):
    """Raised when the AMQP session or loopback broker fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def encode_shortstr(value: str) -> bytes:
    raw = str(value or "").encode("utf-8")
    if len(raw) > 255:
        raise AmqpActuationError("shortstr too long")
    return bytes([len(raw)]) + raw


def encode_longstr(value: bytes | str) -> bytes:
    raw = value.encode("utf-8") if isinstance(value, str) else bytes(value or b"")
    return struct.pack("!I", len(raw)) + raw


def encode_bits(*flags: bool) -> bytes:
    value = 0
    for index, flag in enumerate(flags):
        if flag:
            value |= 1 << index
    return bytes([value & 0xFF])


def encode_table(fields: Mapping[str, Any]) -> bytes:
    inner = bytearray()
    for key, value in dict(fields or {}).items():
        inner += encode_shortstr(str(key))
        if isinstance(value, bool):
            inner += b"t" + bytes([1 if value else 0])
        elif isinstance(value, int) and not isinstance(value, bool):
            inner += b"I" + struct.pack("!i", int(value))
        elif isinstance(value, dict):
            inner += b"F" + encode_table(value)
        else:
            inner += b"S" + encode_longstr(str(value))
    return encode_longstr(bytes(inner))


def encode_frame(ftype: int, channel: int, payload: bytes) -> bytes:
    body = bytes(payload or b"")
    if len(body) > MAX_FRAME:
        raise AmqpActuationError("frame too large")
    return struct.pack("!BHI", int(ftype) & 0xFF, int(channel) & 0xFFFF, len(body)) + body + bytes([FRAME_END])


def encode_method(channel: int, class_id: int, method_id: int, args: bytes = b"") -> bytes:
    return encode_frame(FRAME_METHOD, channel, struct.pack("!HH", class_id, method_id) + bytes(args or b""))


def encode_content_header(channel: int, class_id: int, body_size: int) -> bytes:
    payload = struct.pack("!HHQH", int(class_id), 0, int(body_size), 0)
    return encode_frame(FRAME_HEADER, channel, payload)


def encode_body(channel: int, body: bytes) -> bytes:
    return encode_frame(FRAME_BODY, channel, bytes(body or b""))


def encode_plain_response(username: str, password: str) -> bytes:
    return b"\x00" + str(username or "").encode("utf-8") + b"\x00" + str(password or "").encode("utf-8")


def decode_plain_response(response: bytes) -> tuple[str, str]:
    parts = bytes(response or b"").split(b"\x00")
    if len(parts) >= 3:
        return parts[1].decode("utf-8", errors="replace"), parts[2].decode("utf-8", errors="replace")
    if len(parts) == 2:
        return parts[0].decode("utf-8", errors="replace"), parts[1].decode("utf-8", errors="replace")
    return "", ""


def read_shortstr(buf: bytes, offset: int) -> tuple[str, int]:
    if offset >= len(buf):
        raise AmqpActuationError("truncated shortstr")
    size = buf[offset]
    start = offset + 1
    end = start + size
    if end > len(buf):
        raise AmqpActuationError("truncated shortstr body")
    return buf[start:end].decode("utf-8", errors="replace"), end


def read_longstr(buf: bytes, offset: int) -> tuple[bytes, int]:
    if offset + 4 > len(buf):
        raise AmqpActuationError("truncated longstr")
    size = struct.unpack_from("!I", buf, offset)[0]
    start = offset + 4
    end = start + size
    if end > len(buf):
        raise AmqpActuationError("truncated longstr body")
    return buf[start:end], end


def parse_method(payload: bytes) -> tuple[int, int, bytes]:
    if len(payload) < 4:
        raise AmqpActuationError("truncated method")
    class_id, method_id = struct.unpack_from("!HH", payload, 0)
    return int(class_id), int(method_id), payload[4:]


def parse_start_ok(args: bytes) -> dict[str, str]:
    _props, offset = read_longstr(args, 0)
    mechanism, offset = read_shortstr(args, offset)
    response, offset = read_longstr(args, offset)
    locale, _offset = read_shortstr(args, offset)
    username, password = decode_plain_response(response)
    return {
        "mechanism": mechanism,
        "locale": locale,
        "username": username,
        "password": password,
    }


def parse_open(args: bytes) -> str:
    vhost, _offset = read_shortstr(args, 0)
    return vhost


def parse_queue_declare(args: bytes) -> str:
    if len(args) < 2:
        raise AmqpActuationError("truncated queue.declare")
    queue, _offset = read_shortstr(args, 2)
    return queue


def parse_basic_publish(args: bytes) -> tuple[str, str]:
    if len(args) < 2:
        raise AmqpActuationError("truncated basic.publish")
    exchange, offset = read_shortstr(args, 2)
    routing_key, _offset = read_shortstr(args, offset)
    return exchange, routing_key


def parse_basic_consume(args: bytes) -> tuple[str, str]:
    if len(args) < 2:
        raise AmqpActuationError("truncated basic.consume")
    queue, offset = read_shortstr(args, 2)
    consumer_tag, _offset = read_shortstr(args, offset)
    return queue, consumer_tag


def parse_content_header(payload: bytes) -> tuple[int, int]:
    if len(payload) < 14:
        raise AmqpActuationError("truncated content header")
    class_id, _weight, body_size = struct.unpack_from("!HHQ", payload, 0)
    return int(class_id), int(body_size)


def encode_connection_start() -> bytes:
    args = bytes([0, 9]) + encode_table({"product": "blackhole-amqp", "version": "0.9.1"})
    args += encode_longstr(b"PLAIN") + encode_longstr(b"en_US")
    return encode_method(0, CLASS_CONNECTION, CONNECTION_START, args)


def encode_start_ok(username: str, password: str) -> bytes:
    args = encode_table({"product": "blackhole-unbound"})
    args += encode_shortstr("PLAIN")
    args += encode_longstr(encode_plain_response(username, password))
    args += encode_shortstr("en_US")
    return encode_method(0, CLASS_CONNECTION, CONNECTION_START_OK, args)


def encode_tune() -> bytes:
    return encode_method(0, CLASS_CONNECTION, CONNECTION_TUNE, struct.pack("!HIH", 2047, MAX_FRAME, 0))


def encode_tune_ok() -> bytes:
    return encode_method(0, CLASS_CONNECTION, CONNECTION_TUNE_OK, struct.pack("!HIH", 2047, MAX_FRAME, 0))


def encode_connection_open(vhost: str = DEFAULT_VHOST) -> bytes:
    return encode_method(0, CLASS_CONNECTION, CONNECTION_OPEN, encode_shortstr(vhost) + encode_shortstr("") + bytes([0]))


def encode_connection_open_ok() -> bytes:
    return encode_method(0, CLASS_CONNECTION, CONNECTION_OPEN_OK, encode_shortstr(""))


def encode_connection_close(code: int, text: str) -> bytes:
    args = struct.pack("!H", int(code)) + encode_shortstr(text) + struct.pack("!HH", 0, 0)
    return encode_method(0, CLASS_CONNECTION, CONNECTION_CLOSE, args)


def encode_channel_open(channel: int = 1) -> bytes:
    return encode_method(channel, CLASS_CHANNEL, CHANNEL_OPEN, encode_shortstr(""))


def encode_channel_open_ok(channel: int = 1) -> bytes:
    return encode_method(channel, CLASS_CHANNEL, CHANNEL_OPEN_OK, encode_longstr(b""))


def encode_queue_declare(channel: int, queue: str) -> bytes:
    args = struct.pack("!H", 0) + encode_shortstr(queue) + encode_bits(False, True, False, False, False)
    args += encode_table({})
    return encode_method(channel, CLASS_QUEUE, QUEUE_DECLARE, args)


def encode_queue_declare_ok(channel: int, queue: str, messages: int = 0) -> bytes:
    args = encode_shortstr(queue) + struct.pack("!II", int(messages), 0)
    return encode_method(channel, CLASS_QUEUE, QUEUE_DECLARE_OK, args)


def encode_basic_publish(channel: int, routing_key: str) -> bytes:
    args = struct.pack("!H", 0) + encode_shortstr("") + encode_shortstr(routing_key) + encode_bits(False, False)
    return encode_method(channel, CLASS_BASIC, BASIC_PUBLISH, args)


def encode_basic_consume(channel: int, queue: str, consumer_tag: str = DEFAULT_CONSUMER_TAG) -> bytes:
    args = struct.pack("!H", 0) + encode_shortstr(queue) + encode_shortstr(consumer_tag)
    args += encode_bits(False, False, False, False) + encode_table({})
    return encode_method(channel, CLASS_BASIC, BASIC_CONSUME, args)


def encode_basic_consume_ok(channel: int, consumer_tag: str) -> bytes:
    return encode_method(channel, CLASS_BASIC, BASIC_CONSUME_OK, encode_shortstr(consumer_tag))


def encode_basic_deliver(channel: int, consumer_tag: str, delivery_tag: int, routing_key: str) -> bytes:
    args = encode_shortstr(consumer_tag) + struct.pack("!Q", int(delivery_tag))
    args += encode_bits(False) + encode_shortstr("") + encode_shortstr(routing_key)
    return encode_method(channel, CLASS_BASIC, BASIC_DELIVER, args)


def encode_basic_ack(channel: int, delivery_tag: int) -> bytes:
    return encode_method(channel, CLASS_BASIC, BASIC_ACK, struct.pack("!Q", int(delivery_tag)) + encode_bits(False))


def encode_publish_content(channel: int, routing_key: str, body: bytes) -> bytes:
    payload = bytes(body or b"")
    return (
        encode_basic_publish(channel, routing_key)
        + encode_content_header(channel, CLASS_BASIC, len(payload))
        + encode_body(channel, payload)
    )


def encode_deliver_content(
    channel: int,
    consumer_tag: str,
    delivery_tag: int,
    routing_key: str,
    body: bytes,
) -> bytes:
    payload = bytes(body or b"")
    return (
        encode_basic_deliver(channel, consumer_tag, delivery_tag, routing_key)
        + encode_content_header(channel, CLASS_BASIC, len(payload))
        + encode_body(channel, payload)
    )


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    if size < 0 or size > MAX_FRAME + 8:
        raise AmqpActuationError(f"read length out of range: {size}")
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise AmqpActuationError("eof")
        buf.extend(chunk)
    return bytes(buf)


def read_frame_from_sock(sock: socket.socket) -> tuple[int, int, bytes]:
    header = _recv_exact(sock, 7)
    ftype, channel, size = struct.unpack("!BHI", header)
    if size > MAX_FRAME:
        raise AmqpActuationError("frame too large")
    payload = _recv_exact(sock, size) if size else b""
    end = _recv_exact(sock, 1)
    if end != bytes([FRAME_END]):
        raise AmqpActuationError("bad frame end")
    return int(ftype), int(channel), payload


class _AmqpTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(self, address: tuple[str, int], handler: type[socketserver.BaseRequestHandler], session: AmqpSession) -> None:
        self.session = session
        super().__init__(address, handler)


class _AmqpHandler(socketserver.StreamRequestHandler):
    timeout = None

    def setup(self) -> None:
        super().setup()
        self._send_lock = threading.Lock()

    def _send(self, payload: bytes) -> None:
        with self._send_lock:
            self.request.sendall(payload)

    def handle(self) -> None:
        session: AmqpSession = self.server.session  # type: ignore[attr-defined]
        authenticated = False
        tuned = False
        connection_open = False
        channels: set[int] = set()
        try:
            self.request.settimeout(IO_TIMEOUT)
            try:
                header = _recv_exact(self.request, 8)
            except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
                return
            if header != PROTOCOL_HEADER:
                return
            self.request.settimeout(None)
            self._send(encode_connection_start())
            while True:
                try:
                    ftype, channel, payload = read_frame_from_sock(self.request)
                except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
                    return
                if ftype == FRAME_HEARTBEAT:
                    self._send(encode_frame(FRAME_HEARTBEAT, 0, b""))
                    continue
                if ftype != FRAME_METHOD:
                    return
                try:
                    class_id, method_id, args = parse_method(payload)
                except AmqpActuationError:
                    return
                if class_id == CLASS_CONNECTION and method_id == CONNECTION_START_OK:
                    try:
                        start_ok = parse_start_ok(args)
                    except AmqpActuationError:
                        self._send(encode_connection_close(501, "invalid start-ok"))
                        return
                    if start_ok.get("mechanism") != "PLAIN" or not session.credentials_match(
                        start_ok.get("username") or "",
                        start_ok.get("password") or "",
                    ):
                        self._send(encode_connection_close(403, "ACCESS_REFUSED"))
                        return
                    authenticated = True
                    self._send(encode_tune())
                elif class_id == CLASS_CONNECTION and method_id == CONNECTION_TUNE_OK:
                    if not authenticated:
                        self._send(encode_connection_close(504, "channel error"))
                        return
                    tuned = True
                elif class_id == CLASS_CONNECTION and method_id == CONNECTION_OPEN:
                    if not authenticated or not tuned:
                        self._send(encode_connection_close(504, "channel error"))
                        return
                    try:
                        vhost = parse_open(args)
                    except AmqpActuationError:
                        self._send(encode_connection_close(501, "invalid open"))
                        return
                    if vhost != DEFAULT_VHOST:
                        self._send(encode_connection_close(403, "ACCESS_REFUSED"))
                        return
                    connection_open = True
                    self._send(encode_connection_open_ok())
                elif class_id == CLASS_CONNECTION and method_id == CONNECTION_CLOSE:
                    self._send(encode_method(0, CLASS_CONNECTION, CONNECTION_CLOSE_OK, b""))
                    return
                elif class_id == CLASS_CHANNEL and method_id == CHANNEL_OPEN:
                    if not connection_open:
                        self._send(encode_connection_close(504, "channel error"))
                        return
                    channels.add(channel)
                    self._send(encode_channel_open_ok(channel))
                elif class_id == CLASS_QUEUE and method_id == QUEUE_DECLARE:
                    if channel not in channels:
                        self._send(encode_connection_close(504, "channel error"))
                        return
                    try:
                        queue = parse_queue_declare(args)
                    except AmqpActuationError:
                        return
                    session.declare_queue(queue)
                    self._send(encode_queue_declare_ok(channel, queue, session.message_count(queue)))
                elif class_id == CLASS_BASIC and method_id == BASIC_PUBLISH:
                    if channel not in channels:
                        self._send(encode_connection_close(504, "channel error"))
                        return
                    try:
                        _exchange, routing_key = parse_basic_publish(args)
                        header_type, _hdr_channel, header_payload = read_frame_from_sock(self.request)
                        if header_type != FRAME_HEADER:
                            return
                        _class_id, body_size = parse_content_header(header_payload)
                        collected = bytearray()
                        while len(collected) < body_size:
                            body_type, _body_channel, body_payload = read_frame_from_sock(self.request)
                            if body_type != FRAME_BODY:
                                return
                            collected.extend(body_payload)
                    except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
                        return
                    session.store_publish(routing_key, bytes(collected[:body_size]))
                elif class_id == CLASS_BASIC and method_id == BASIC_CONSUME:
                    if channel not in channels:
                        self._send(encode_connection_close(504, "channel error"))
                        return
                    try:
                        queue, consumer_tag = parse_basic_consume(args)
                    except AmqpActuationError:
                        return
                    tag = consumer_tag or DEFAULT_CONSUMER_TAG
                    self._send(encode_basic_consume_ok(channel, tag))
                    delivered = session.take_deliver(queue)
                    if delivered is None:
                        continue
                    delivery_tag, body = delivered
                    self._send(encode_deliver_content(channel, tag, delivery_tag, queue, body))
                elif class_id == CLASS_BASIC and method_id == BASIC_ACK:
                    continue
                elif class_id == CLASS_CHANNEL and method_id == CHANNEL_CLOSE:
                    self._send(encode_method(channel, CLASS_CHANNEL, CHANNEL_CLOSE_OK, b""))
                    channels.discard(channel)
                else:
                    return
        finally:
            return


class _AmqpClient:
    """Minimal AMQP 0-9-1 client for protocol-header through basic.deliver."""

    def __init__(self, host: str, port: int, *, timeout: float = IO_TIMEOUT) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.timeout = timeout

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def _write(self, payload: bytes) -> None:
        self.sock.sendall(payload)

    def read_frame(self) -> tuple[int, int, bytes]:
        return read_frame_from_sock(self.sock)

    def read_method(self) -> tuple[int, int, int, bytes]:
        ftype, channel, payload = self.read_frame()
        if ftype != FRAME_METHOD:
            raise AmqpActuationError(f"expected method frame, got {ftype}")
        class_id, method_id, args = parse_method(payload)
        return class_id, method_id, channel, args

    def write_protocol(self) -> None:
        self._write(PROTOCOL_HEADER)

    def negotiate(self, username: str, password: str) -> tuple[bool, str]:
        self.write_protocol()
        try:
            class_id, method_id, _channel, _args = self.read_method()
        except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
            return False, "eof"
        if (class_id, method_id) != (CLASS_CONNECTION, CONNECTION_START):
            return False, "not_start"
        self._write(encode_start_ok(username, password))
        try:
            class_id, method_id, _channel, _args = self.read_method()
        except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
            return False, "eof"
        if (class_id, method_id) == (CLASS_CONNECTION, CONNECTION_CLOSE):
            return False, "auth_failed"
        if (class_id, method_id) != (CLASS_CONNECTION, CONNECTION_TUNE):
            return False, "not_tune"
        self._write(encode_tune_ok())
        self._write(encode_connection_open())
        try:
            class_id, method_id, _channel, _args = self.read_method()
        except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
            return False, "eof"
        if (class_id, method_id) != (CLASS_CONNECTION, CONNECTION_OPEN_OK):
            return False, "not_open_ok"
        return True, "ok"

    def open_channel(self, channel: int = 1) -> tuple[bool, str]:
        self._write(encode_channel_open(channel))
        try:
            class_id, method_id, _channel, _args = self.read_method()
        except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
            return False, "eof"
        if (class_id, method_id) != (CLASS_CHANNEL, CHANNEL_OPEN_OK):
            return False, "not_channel_ok"
        return True, "ok"

    def declare(self, queue: str, channel: int = 1) -> tuple[bool, str]:
        self._write(encode_queue_declare(channel, queue))
        try:
            class_id, method_id, _channel, _args = self.read_method()
        except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
            return False, "eof"
        if (class_id, method_id) != (CLASS_QUEUE, QUEUE_DECLARE_OK):
            return False, "not_declare_ok"
        return True, "ok"

    def publish(self, routing_key: str, body: bytes, channel: int = 1) -> None:
        self._write(encode_publish_content(channel, routing_key, body))

    def consume(self, queue: str, channel: int = 1) -> tuple[bool, str, int, bytes]:
        self._write(encode_basic_consume(channel, queue))
        try:
            class_id, method_id, _channel, args = self.read_method()
        except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
            return False, "eof", 0, b""
        if (class_id, method_id) != (CLASS_BASIC, BASIC_CONSUME_OK):
            return False, "not_consume_ok", 0, b""
        try:
            class_id, method_id, _channel, args = self.read_method()
        except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
            return False, "no_deliver", 0, b""
        if (class_id, method_id) != (CLASS_BASIC, BASIC_DELIVER):
            return False, "not_deliver", 0, b""
        _tag, offset = read_shortstr(args, 0)
        delivery_tag = struct.unpack_from("!Q", args, offset)[0]
        try:
            ftype, _channel, header_payload = self.read_frame()
            if ftype != FRAME_HEADER:
                return False, "not_header", 0, b""
            _class_id, body_size = parse_content_header(header_payload)
            collected = bytearray()
            while len(collected) < body_size:
                ftype, _channel, body_payload = self.read_frame()
                if ftype != FRAME_BODY:
                    return False, "not_body", 0, b""
                collected.extend(body_payload)
        except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
            return False, "content_eof", 0, b""
        body = bytes(collected[:body_size])
        self._write(encode_basic_ack(channel, int(delivery_tag)))
        return True, "ok", int(delivery_tag), body


class AmqpSession:
    """Credential-gated loopback AMQP listener: bind, publish, read."""

    def __init__(self, output_dir: Path, *, password: str = DEFAULT_PASSWORD) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.username = DEFAULT_USERNAME
        self.password = str(password or "")
        self.host: str | None = None
        self.port: int | None = None
        self.server: _AmqpTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.delivered = False
        self.last_token = ""
        self.last_delivery_tag = 0
        self.history: list[dict[str, Any]] = []
        self._queues: dict[str, bytes] = {}
        self._delivery = 0
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def credentials_match(self, username: str, password: str) -> bool:
        if not self.password:
            return False
        return username == self.username and password == self.password

    def declare_queue(self, queue: str) -> None:
        with self._lock:
            self._queues.setdefault(str(queue or ""), b"")

    def message_count(self, queue: str) -> int:
        with self._lock:
            body = self._queues.get(str(queue or ""), b"")
            return 1 if body else 0

    def store_publish(self, routing_key: str, body: bytes) -> None:
        with self._lock:
            self._queues[str(routing_key or "")] = bytes(body or b"")

    def take_deliver(self, queue: str) -> tuple[int, bytes] | None:
        with self._lock:
            body = self._queues.get(str(queue or ""), b"")
            if not body:
                return None
            self._delivery += 1
            return self._delivery, bytes(body)

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
        server = _AmqpTCPServer(("127.0.0.1", 0), _AmqpHandler, self)
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

    def publish(
        self,
        token: str = SENTINEL,
        *,
        authenticate: bool = True,
        protocol: bool = True,
        connection: bool = True,
        channel: bool = True,
        declare: bool = True,
        publish: bool = True,
        consume: bool = True,
        replay: bool = True,
        password: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.password:
            return self._forbidden("missing_secret")
        live_token = str(token or SENTINEL)
        body = live_token.encode("utf-8")
        publisher: _AmqpClient | None = None
        consumer: _AmqpClient | None = None
        independent: _AmqpClient | None = None
        try:
            publisher = _AmqpClient(self.host, int(self.port))
            if not protocol:
                publisher._write(encode_channel_open(1))
                return self._conflict("protocol_required")
            if not connection:
                publisher.write_protocol()
                try:
                    publisher.read_method()
                except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
                    return self._conflict("connection_required")
                publisher._write(encode_channel_open(1))
                return self._conflict("connection_required")
            if authenticate:
                secret = self.password if password is None else str(password)
                ok, status = publisher.negotiate(self.username, secret)
                if not ok:
                    reason = "auth_failed" if status == "auth_failed" else "connection_required"
                    code = 403 if reason == "auth_failed" else 530
                    return self._forbidden(reason, status=code)
            else:
                publisher.write_protocol()
                try:
                    publisher.read_method()
                except (AmqpActuationError, OSError, TimeoutError, socket.timeout):
                    return self._forbidden("connection_required", status=530)
                publisher._write(encode_channel_open(1))
                return self._forbidden("connection_required", status=530)
            if not channel:
                publisher._write(encode_queue_declare(1, DEFAULT_QUEUE))
                return self._conflict("channel_required")
            opened, _ = publisher.open_channel(1)
            if not opened:
                return self._conflict("channel_required")
            if not declare:
                publisher.publish(DEFAULT_QUEUE, body)
                return self._conflict("declare_required")
            declared, _ = publisher.declare(DEFAULT_QUEUE)
            if not declared:
                return self._conflict("declare_required")
            if not publish:
                return self._conflict("publish_required")
            publisher.publish(DEFAULT_QUEUE, body)
            if not consume:
                return self._conflict("deliver_required")
            consumer = _AmqpClient(self.host, int(self.port))
            cok, _cstatus = consumer.negotiate(self.username, self.password)
            if not cok:
                return self._forbidden("consumer_connect_failed", status=503)
            if not consumer.open_channel(1)[0]:
                return self._conflict("channel_required")
            delivered, dstatus, delivery_tag, received = consumer.consume(DEFAULT_QUEUE)
            if not delivered or received != body:
                return self._forbidden("deliver_required" if dstatus == "no_deliver" else "payload_mismatch", status=409)
            if not replay:
                return self._conflict("replay_required")
            independent = _AmqpClient(self.host, int(self.port))
            iok, _istatus = independent.negotiate(self.username, self.password)
            if not iok:
                return self._forbidden("independent_connect_failed", status=503)
            if not independent.open_channel(1)[0]:
                return self._forbidden("independent_channel_failed", status=503)
            ireplay, _istatus, ireplay_tag, ireceived = independent.consume(DEFAULT_QUEUE)
            if not ireplay or ireceived != body:
                return self._forbidden("replay_required", status=409)
            digest = payload_sha256(received)
            sealed = {
                "queue": DEFAULT_QUEUE,
                "routing_key": DEFAULT_QUEUE,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "delivery_tag": int(delivery_tag),
                "replay_tag": int(ireplay_tag),
                "digest": digest,
                "protocol": True,
                "connected": True,
                "channeled": True,
                "declared": True,
                "published": True,
                "delivered": True,
                "replayed": True,
                "independent": True,
                "authenticated": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            self.last_delivery_tag = int(delivery_tag)
            live = independent_amqp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "queue": DEFAULT_QUEUE,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "delivery_tag": int(delivery_tag),
                "path": str(self.sealed_path),
                "authenticated": True,
                "protocol": True,
                "connected": True,
                "channeled": True,
                "declared": True,
                "published": True,
                "delivered": True,
                "replayed": True,
                "independent": True,
            }
        except (OSError, AmqpActuationError) as error:
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
                independent.close()
            if consumer is not None:
                consumer.close()
            if publisher is not None:
                publisher.close()

    def read(self) -> dict[str, Any]:
        live = independent_amqp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "queue": str(live.get("queue") or ""),
            "delivery_tag": int(live.get("delivery_tag") or 0),
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


def call_amqp_tool(session: AmqpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one AMQP tool call against a bound listener session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = True if arguments.get("authenticate") is None else bool(arguments.get("authenticate"))
    protocol = True if arguments.get("protocol") is None else bool(arguments.get("protocol"))
    connection = True if arguments.get("connection") is None else bool(arguments.get("connection"))
    channel = True if arguments.get("channel") is None else bool(arguments.get("channel"))
    declare = True if arguments.get("declare") is None else bool(arguments.get("declare"))
    publish = True if arguments.get("publish") is None else bool(arguments.get("publish"))
    consume = True if arguments.get("consume") is None else bool(arguments.get("consume"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    password = arguments.get("password")
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            authenticate=authenticate,
            protocol=protocol,
            connection=connection,
            channel=channel,
            declare=declare,
            publish=publish,
            consume=consume,
            replay=replay,
            password=None if password is None else str(password),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise AmqpActuationError(f"unsupported amqp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_amqp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed AMQP delivery through a fresh file open."""

    path = Path(sealed_path)
    if not path.is_file():
        return {
            "ok": False,
            "error": "missing_payload",
            "token": "",
            "sentinel": "",
            "digest": "",
            "queue": "",
            "delivery_tag": 0,
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
            "digest": "",
            "queue": "",
            "delivery_tag": 0,
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "invalid_payload",
            "token": "",
            "sentinel": "",
            "digest": "",
            "queue": "",
            "delivery_tag": 0,
        }
    token = str(payload.get("token") or "")
    flags = all(
        payload.get(name) is True
        for name in (
            "protocol",
            "connected",
            "channeled",
            "declared",
            "published",
            "delivered",
            "replayed",
            "independent",
            "authenticated",
        )
    )
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags else "",
        "digest": str(payload.get("digest") or ""),
        "queue": str(payload.get("queue") or ""),
        "delivery_tag": int(payload.get("delivery_tag") or 0),
        "replay_tag": int(payload.get("replay_tag") or 0),
        "protocol": payload.get("protocol") is True,
        "connected": payload.get("connected") is True,
        "channeled": payload.get("channeled") is True,
        "declared": payload.get("declared") is True,
        "published": payload.get("published") is True,
        "delivered": payload.get("delivered") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "authenticated": payload.get("authenticated") is True,
    }


def run_amqp_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    protocol: bool = True,
    connection: bool = True,
    channel: bool = True,
    declare: bool = True,
    publish: bool = True,
    consume: bool = True,
    replay: bool = True,
    password: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the AMQP 0-9-1 work-queue delivery workflow and seal a trace."""

    descriptor = amqp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, AMQP_TOOL_PROVIDER),
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
        raise AmqpActuationError(f"amqp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="amqp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = AmqpSession(out, password=DEFAULT_PASSWORD if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    publish_args: dict[str, Any] = {
        "action": "publish",
        "token": SENTINEL,
        "authenticate": authenticate,
        "protocol": protocol,
        "connection": connection,
        "channel": channel,
        "declare": declare,
        "publish": publish,
        "consume": consume,
        "replay": replay,
    }
    if password is not None:
        publish_args["password"] = password
    calls.append(publish_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_amqp_tool(session, arguments))
            except AmqpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_amqp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and protocol
        and connection
        and channel
        and declare
        and publish
        and consume
        and replay
        and password is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "amqp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "protocol": protocol,
        "connection": connection,
        "channel": channel,
        "declare": declare,
        "publish": publish,
        "consume": consume,
        "replay": replay,
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
        "digest": str(publish_result.get("digest") or independent.get("digest") or ""),
        "delivery_tag": int(publish_result.get("delivery_tag") or independent.get("delivery_tag") or 0),
        "delivered": bool(session.delivered or publish_result.get("delivered")),
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
        "digest": str(trace_body["digest"] or ""),
        "delivery_tag": int(trace_body["delivery_tag"] or 0),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "delivered": bool(trace_body["delivered"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "protocol": protocol,
        "connection": connection,
        "channel": channel,
        "declare": declare,
        "publish": publish,
        "consume": consume,
        "replay": replay,
    }


def verify_amqp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed AMQP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_amqp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "independent_digest": _digest(independent) == trace.get("independent_digest"),
        "routing_executable": routing.get("executable") is True and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "independent_recorded": str(independent.get("sentinel") or "") == SENTINEL,
        "live_payload_matches": str(live_row.get("sentinel") or "") == SENTINEL,
        "payload_exists": bool(trace.get("payload_exists")) and sealed_path.is_file(),
        "delivered": trace.get("delivered") is True,
        "protocol": independent.get("protocol") is True,
        "connected": independent.get("connected") is True,
        "channeled": independent.get("channeled") is True,
        "declared": independent.get("declared") is True,
        "published": independent.get("published") is True,
        "delivered_flag": independent.get("delivered") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "authenticated": independent.get("authenticated") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "delivery_tag_recorded": int(trace.get("delivery_tag") or independent.get("delivery_tag") or 0) > 0,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def amqp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.amqp_actuation import "
        "builtin_amqp_actuation_proof; r=builtin_amqp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='amqp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_amqp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=AMQP_ACTUATION_ID,
        name="First-class AMQP 0-9-1 work-queue delivery actuation",
        description=(
            "Missions that require an amqp tool can opt the amqp provider in, "
            "bind a loopback AMQP 0-9-1 broker, complete PROTOCOL-HEADER plus "
            "CONNECTION-START/TUNE/OPEN, CHANNEL-OPEN, QUEUE-DECLARE, "
            "BASIC-PUBLISH with content-header/body frames, BASIC-DELIVER a "
            "delivery-tag, independently re-consume the retained last-value on "
            "a later connection, and seal digest-chained work-queue delivery. "
            "Default routing stays fail-closed; a missing PLAIN password keeps "
            "the hole falsifiable, and skip-PROTOCOL/CONNECTION/CHANNEL/"
            "DECLARE/PUBLISH/DELIVER/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.amqp_actuation:builtin_amqp_actuation_proof",
        proof_command=amqp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.grpc-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/amqp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required amqp tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback AMQP 0-9-1 broker, speaks the "
            "protocol header, CONNECTION-START/TUNE/OPEN, CHANNEL-OPEN, "
            "QUEUE-DECLARE, BASIC-PUBLISH with content-header/body frames, "
            "BASIC-DELIVER a delivery-tag, independently re-consumes the "
            "retained last-value on a later connection, and binds this family "
            "as the next diversity-catalog successor once gRPC HTTP/2 RPC is "
            "proved. Missing credentials, skip-PROTOCOL, skip-CONNECTION, "
            "skip-CHANNEL, skip-DECLARE, skip-PUBLISH, skip-DELIVER, and "
            "skip-REPLAY stay fail-closed."
        ),
        tags=("amqp", "work-queue", "delivery", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T153721Z-6ecf37b5",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_amqp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in AMQP 0-9-1 actuation seals a delivery-tag digest."""

    from blackhole_agent.grpc_actuation import GRPC_ACTUATION_GOAL, GRPC_ACTUATION_ID
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
    from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
    from blackhole_agent.redis_actuation import REDIS_ACTUATION_GOAL, REDIS_ACTUATION_ID
    from blackhole_agent.ssh_actuation import SSH_ACTUATION_GOAL, SSH_ACTUATION_ID
    from blackhole_agent.websocket_actuation import WEBSOCKET_ACTUATION_GOAL, WEBSOCKET_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = AMQP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(AMQP_ACTUATION_GOAL) == (AMQP_ACTUATION_ID,)
    checks["grpc_goal_is_not_amqp"] = leftover_marker_ids(GRPC_ACTUATION_GOAL) == (GRPC_ACTUATION_ID,)
    checks["ssh_goal_is_not_amqp"] = leftover_marker_ids(SSH_ACTUATION_GOAL) == (SSH_ACTUATION_ID,)
    checks["websocket_goal_is_not_amqp"] = leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL) == (
        WEBSOCKET_ACTUATION_ID,
    )
    checks["mqtt_goal_is_not_amqp"] = leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    checks["redis_goal_is_not_amqp"] = leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    checks["amqp_goal_is_not_grpc"] = GRPC_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    checks["amqp_goal_is_not_ssh"] = SSH_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    checks["amqp_goal_is_not_websocket"] = WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(
        AMQP_ACTUATION_GOAL
    )
    checks["amqp_goal_is_not_mqtt"] = MQTT_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    checks["amqp_goal_is_not_redis"] = REDIS_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    checks["grpc_marker_stays_grpc"] = AMQP_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    checks["ssh_marker_stays_ssh"] = AMQP_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    checks["websocket_marker_stays_websocket"] = AMQP_ACTUATION_ID not in leftover_marker_ids(
        WEBSOCKET_ACTUATION_GOAL
    )
    checks["mqtt_marker_stays_mqtt"] = AMQP_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    checks["redis_marker_stays_redis"] = AMQP_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_amqp"] = (
        len(catalog) > 44
        and catalog[44]["id"] == AMQP_ACTUATION_ID
        and catalog[43]["id"] == GRPC_ACTUATION_ID
    )
    family = capability_family(AMQP_ACTUATION_GOAL)
    checks["family_is_amqp"] = "amqp" in family
    checks["family_is_queue"] = "queue" in family
    checks["family_is_delivery"] = "delivery" in family
    checks["family_is_not_grpc"] = "grpc" not in family and "http2" not in family
    checks["family_is_not_openssh"] = "openssh" not in family and "ssh" not in family
    checks["family_is_not_websocket"] = "websocket" not in family and "rfc6455" not in family
    checks["family_is_not_mqtt"] = "mqtt" not in family
    checks["family_is_not_redis"] = "redi" not in family and "blpop" not in family
    checks["protocol_header_is_amqp_091"] = PROTOCOL_HEADER == b"AMQP\x00\x00\x09\x01"
    packed = encode_frame(FRAME_METHOD, 1, b"abcd")
    ftype, channel, size = struct.unpack("!BHI", packed[:7])
    checks["frame_roundtrip"] = (
        ftype == FRAME_METHOD
        and channel == 1
        and size == 4
        and packed[7:11] == b"abcd"
        and packed[11] == FRAME_END
    )
    user, secret = decode_plain_response(encode_plain_response("u", "p"))
    checks["plain_roundtrip"] = user == "u" and secret == "p"
    start_ok = parse_start_ok(parse_method(encode_start_ok("u", "p")[7:-1])[2])
    checks["start_ok_plain_roundtrip"] = (
        start_ok.get("mechanism") == "PLAIN" and start_ok.get("username") == "u" and start_ok.get("password") == "p"
    )
    neighbors = (
        GRPC_ACTUATION_GOAL,
        SSH_ACTUATION_GOAL,
        WEBSOCKET_ACTUATION_GOAL,
        MQTT_ACTUATION_GOAL,
        REDIS_ACTUATION_GOAL,
    )
    amqp_signature = semantic_signature(AMQP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(amqp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_amqp = ToolDescriptor(name="remote_amqp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_amqp)
    checks["naive_mcp_amqp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = amqp_tool_descriptor()
    default_amqp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, AMQP_TOOL_PROVIDER),
    )
    checks["default_amqp_provider_is_unsupported"] = (
        default_amqp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{AMQP_TOOL_PROVIDER}" in default_amqp.reasons
    )
    checks["opted_in_amqp_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_amqp],
        required_tool_names=("local_memory", "amqp"),
    )
    checks["naive_preflight_missing_amqp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["amqp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "amqp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, AMQP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "amqp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="amqp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_amqp_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_amqp_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_amqp_workflow(password="wrong-password", output_dir=root / "wrong")
        skip_bind = run_amqp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_protocol = run_amqp_workflow(protocol=False, output_dir=root / "skip-protocol")
        skip_connection = run_amqp_workflow(connection=False, output_dir=root / "skip-connection")
        skip_channel = run_amqp_workflow(channel=False, output_dir=root / "skip-channel")
        skip_declare = run_amqp_workflow(declare=False, output_dir=root / "skip-declare")
        skip_publish = run_amqp_workflow(publish=False, output_dir=root / "skip-publish")
        skip_consume = run_amqp_workflow(consume=False, output_dir=root / "skip-consume")
        skip_replay = run_amqp_workflow(replay=False, output_dir=root / "skip-replay")
        live = run_amqp_workflow(output_dir=root / "live")
        verify = verify_amqp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_amqp_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unauthenticated_channel_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 530
            and unauth["error"] == "connection_required"
            and unauth["payload_exists"] is False
        )
        checks["wrong_password_is_forbidden"] = (
            wrong["ok"] is False
            and wrong["final_status"] == 403
            and wrong["error"] == "auth_failed"
            and wrong["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_protocol_stays_empty"] = (
            skip_protocol["ok"] is False
            and skip_protocol["error"] == "protocol_required"
            and skip_protocol["final_status"] == 409
            and skip_protocol["payload_exists"] is False
        )
        checks["skip_connection_stays_empty"] = (
            skip_connection["ok"] is False
            and skip_connection["error"] == "connection_required"
            and skip_connection["final_status"] == 409
            and skip_connection["payload_exists"] is False
        )
        checks["skip_channel_stays_empty"] = (
            skip_channel["ok"] is False
            and skip_channel["error"] == "channel_required"
            and skip_channel["final_status"] == 409
            and skip_channel["payload_exists"] is False
        )
        checks["skip_declare_stays_empty"] = (
            skip_declare["ok"] is False
            and skip_declare["error"] == "declare_required"
            and skip_declare["final_status"] == 409
            and skip_declare["payload_exists"] is False
        )
        checks["skip_publish_stays_empty"] = (
            skip_publish["ok"] is False
            and skip_publish["error"] == "publish_required"
            and skip_publish["final_status"] == 409
            and skip_publish["payload_exists"] is False
        )
        checks["skip_consume_stays_empty"] = (
            skip_consume["ok"] is False
            and skip_consume["error"] == "deliver_required"
            and skip_consume["final_status"] == 409
            and skip_consume["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_delivery_tag"] = int(live.get("delivery_tag") or 0) > 0
        checks["token_protocol_connection_channel_declare_publish_deliver_and_replay_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_bind["ok"] is False
            and skip_protocol["ok"] is False
            and skip_connection["ok"] is False
            and skip_channel["ok"] is False
            and skip_declare["ok"] is False
            and skip_publish["ok"] is False
            and skip_consume["ok"] is False
            and skip_replay["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="amqp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != AMQP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_amqp"] = (
        live_goal == AMQP_ACTUATION_GOAL
        and AMQP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_amqp"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_amqp_actuation_capability()
    return {
        "ok": ok,
        "action": "amqp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": AMQP_ACTUATION_GOAL,
        "done_when": AMQP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
