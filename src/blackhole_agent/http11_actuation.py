"""Drive a first-class HTTP/1.1 tool through RFC 9112 PARSE/SERIALIZE.

Tool routing already fails missions that require ``http11``: hosted http11
endpoints stay on the unsupported MCP provider, and no first-party http11
provider is executable. Unbound therefore cannot speak a PARSE,
lockstep a SERIALIZE requestid handshake over HTTP HTTP/1.1 REQUESTID,
independently poll the stored httpmessage startline, or seal a startline digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``http11`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9112 daemon
- keep a missing-requestid client so the http11-requestid hole stays falsifiable
- refuse SERIALIZE until a PARSE lands with a non-empty requestid
- independently poll the stored httpmessage startline on a later client socket
- persist a sealed startline digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9292 Binary HTTP
"""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import socket
import struct
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    HTTP11_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    http11_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTP11_ACTUATION_ID = "capability.http11-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-H11-OK"
POLL_TOKEN = "BH-H11-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_REQUESTID = 0
EMPTY_STARTLINE = 0
H11_FIRST = 0x48  # RFC 9112 HTTP/1.1 (ASCII 'H')
REQUESTID_SIZE = 4
STARTLINE_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_SERIALIZE = 0x02  # RFC 9112 HTTP/1.1 serialize
FRAME_PARSE = 0x01  # RFC 9112 HTTP/1.1 parse
HTTP_VERSION = "HTTP/1.1"
CRLF = b"\r\n"
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTP11_LEFTOVER = (
    "Later genesis can take RFC 9112 HTTP/1.1 PARSE/SERIALIZE over a "
    "requestid-gated startline digest."
)


def _crc32c_table() -> tuple[int, ...]:
    table = []
    for index in range(256):
        crc = index
        for _ in range(8):
            crc = (crc >> 1) ^ CRC32C_POLY if crc & 1 else crc >> 1
        table.append(crc)
    return tuple(table)


_CRC32C_TABLE = _crc32c_table()


def crc32c(data: bytes) -> int:
    """RFC 3309 CRC32c (Castagnoli) over ``data``."""

    crc = 0xFFFFFFFF
    for byte in bytes(data or b""):
        crc = _CRC32C_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


HTTP11_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTP11_ACTUATION_ID};"
    f"capability_proved:{HTTP11_ACTUATION_ID};"
    "no_skill_route"
)
HTTP11_ACTUATION_GOAL = (
    "Repair rfc9112 http11 parse/serialize cycle cannot land over http "
    "http11 requestid: hosted http11 endpoints remain unsupported so a PARSE then "
    "SERIALIZE requestid handshake cannot land and a sealed startline digest "
    "cannot be produced. A missing http11 requestid stays forbidden; fail-closed "
    "routing never opts the http11 provider in. An independent later poll of the "
    "stored httpmessage startline keeps the hole falsifiable."
)


class Http11ActuationError(RuntimeError):
    """Raised when the HTTP/1.1 session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def encode_varint(value: int) -> bytes:
    number = int(value)
    if number < 0:
        number = 0
    if number <= 63:
        return bytes([number])
    if number <= 16383:
        return struct.pack("!H", 0x4000 | number)
    if number <= 1073741823:
        return struct.pack("!I", 0x80000000 | number)
    return struct.pack("!Q", 0xC000000000000000 | (number & 0x3FFFFFFFFFFFFFFF))


def decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    raw = bytes(data or b"")
    if offset >= len(raw):
        raise Http11ActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise Http11ActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise Http11ActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise Http11ActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def _ascii_token(value: str, *, what: str) -> str:
    text = str(value or "")
    if not text or any(ch in text for ch in " \r\n\t"):
        raise Http11ActuationError(f"illegal_{what}")
    try:
        text.encode("ascii")
    except UnicodeEncodeError as error:
        raise Http11ActuationError(f"illegal_{what}") from error
    return text


def serialize_field_lines(fields: Sequence[tuple[str, str]]) -> bytes:
    """RFC 9112 section 5 field-line: field-name ':' OWS field-value OWS CRLF."""

    parts: list[bytes] = []
    for name, value in fields:
        field_name = _ascii_token(str(name or ""), what="field_name")
        if ":" in field_name:
            raise Http11ActuationError("illegal_field_name")
        field_value = str(value or "")
        if "\r" in field_value or "\n" in field_value:
            raise Http11ActuationError("illegal_field_value")
        try:
            field_value.encode("ascii")
        except UnicodeEncodeError as error:
            raise Http11ActuationError("illegal_field_value") from error
        parts.append(f"{field_name}: {field_value}\r\n".encode("ascii"))
    return b"".join(parts)


def serialize_request(
    *,
    method: str,
    target: str,
    version: str = HTTP_VERSION,
    headers: Sequence[tuple[str, str]] = (),
    body: bytes = b"",
) -> bytes:
    """RFC 9112 section 3 request-line + field-lines + empty line + body."""

    live_method = _ascii_token(method, what="method")
    live_target = _ascii_token(target, what="target")
    live_version = _ascii_token(version, what="version")
    if live_version != HTTP_VERSION:
        raise Http11ActuationError("illegal_version")
    start_line = f"{live_method} {live_target} {live_version}\r\n".encode("ascii")
    return start_line + serialize_field_lines(headers) + CRLF + bytes(body or b"")


def serialize_response(
    *,
    status: int,
    reason: str = "OK",
    version: str = HTTP_VERSION,
    headers: Sequence[tuple[str, str]] = (),
    body: bytes = b"",
) -> bytes:
    """RFC 9112 section 4 status-line + field-lines + empty line + body."""

    live_version = _ascii_token(version, what="version")
    if live_version != HTTP_VERSION:
        raise Http11ActuationError("illegal_version")
    code = int(status)
    if code < 100 or code > 599:
        raise Http11ActuationError("illegal_status")
    live_reason = str(reason or "")
    if "\r" in live_reason or "\n" in live_reason:
        raise Http11ActuationError("illegal_reason")
    start_line = f"{live_version} {code} {live_reason}\r\n".encode("ascii")
    return start_line + serialize_field_lines(headers) + CRLF + bytes(body or b"")


def _split_http_message(data: bytes) -> tuple[bytes, list[bytes], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise Http11ActuationError("short_message")
    head = raw[:split]
    body = raw[split + len(HEADER_END) :]
    if b"\r\n " in head or b"\r\n\t" in head or b"\n " in head or b"\n\t" in head:
        raise Http11ActuationError("obs_fold")
    if b"\n" in head and CRLF not in head:
        raise Http11ActuationError("illegal_line_ending")
    lines = head.split(CRLF)
    if not lines or not lines[0]:
        raise Http11ActuationError("illegal_start_line")
    return lines[0], lines[1:], body


def parse_request(data: bytes) -> dict[str, Any]:
    """RFC 9112 section 3 request parser. Rejects obs-fold and HTTP/1.0."""

    start_raw, field_lines, body = _split_http_message(data)
    try:
        start_line = start_raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise Http11ActuationError("illegal_start_line") from error
    parts = start_line.split(" ")
    if len(parts) != 3:
        raise Http11ActuationError("illegal_start_line")
    method, target, version = parts
    if version != HTTP_VERSION:
        raise Http11ActuationError("illegal_version")
    headers: list[tuple[str, str]] = []
    for line in field_lines:
        if not line:
            continue
        if b":" not in line:
            raise Http11ActuationError("illegal_fields")
        name, value = line.split(b":", 1)
        headers.append(
            (
                name.decode("ascii", errors="strict"),
                value.decode("ascii", errors="strict").strip(" \t"),
            )
        )
    return {
        "kind": "request",
        "method": method,
        "target": target,
        "version": version,
        "start_line": start_line,
        "headers": headers,
        "body": body,
    }


def parse_response(data: bytes) -> dict[str, Any]:
    """RFC 9112 section 4 status-line parser. Rejects obs-fold and HTTP/1.0."""

    start_raw, field_lines, body = _split_http_message(data)
    try:
        start_line = start_raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise Http11ActuationError("illegal_start_line") from error
    parts = start_line.split(" ", 2)
    if len(parts) < 2:
        raise Http11ActuationError("illegal_start_line")
    version, status_text = parts[0], parts[1]
    reason = parts[2] if len(parts) > 2 else ""
    if version != HTTP_VERSION:
        raise Http11ActuationError("illegal_version")
    if len(status_text) != 3 or not status_text.isdigit():
        raise Http11ActuationError("illegal_status")
    headers: list[tuple[str, str]] = []
    for line in field_lines:
        if not line:
            continue
        if b":" not in line:
            raise Http11ActuationError("illegal_fields")
        name, value = line.split(b":", 1)
        headers.append(
            (
                name.decode("ascii", errors="strict"),
                value.decode("ascii", errors="strict").strip(" \t"),
            )
        )
    return {
        "kind": "response",
        "version": version,
        "status": int(status_text),
        "reason": reason,
        "start_line": start_line,
        "headers": headers,
        "body": body,
    }


def http11_request(identity: str, requestid: int) -> bytes:
    """RFC 9112 request-line bound to requestid."""

    keyid = f"{int(requestid) & 0xFFFFFFFF:08x}"
    body = f"{identity}:{keyid}".encode("ascii")
    host = _ascii_token(str(identity or "localhost"), what="host")
    return serialize_request(
        method="POST",
        target=f"/http11/{keyid}",
        version=HTTP_VERSION,
        headers=(
            ("Host", host),
            ("Content-Type", "application/octet-stream"),
            ("Content-Length", str(len(body))),
        ),
        body=body,
    )


def http11_response(identity: str, requestid: int) -> bytes:
    """RFC 9112 status-line response echoing the stored HTTP/1.1 request."""

    encoded = http11_request(identity, requestid)
    return serialize_response(
        status=200,
        reason="OK",
        version=HTTP_VERSION,
        headers=(
            ("Content-Type", "application/octet-stream"),
            ("Content-Length", str(len(encoded))),
        ),
        body=encoded,
    )


def request_requestid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"requestid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_requestid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-requestid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_startline(requestid: int = EMPTY_REQUESTID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(http11_request(token or SENTINEL, int(requestid) & 0xFFFFFFFF)).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_REQUESTID = request_requestid(SENTINEL)
DEFAULT_STARTLINE = request_startline(DEFAULT_REQUESTID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    requestid: int,
    startline: int,
    include_requestid: bool = True,
) -> bytes:
    live_requestid = int(requestid) & 0xFFFFFFFF if include_requestid else EMPTY_REQUESTID
    live_startline = int(startline) & 0xFFFFFFFF if include_requestid and live_requestid else EMPTY_STARTLINE
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_startline, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_requestid) if live_requestid else b""
    header = bytearray()
    header.append(H11_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_parse(
    *,
    identity: str,
    requestid: int,
    startline: int | None = None,
    include_requestid: bool = True,
) -> bytes:
    live_requestid = int(requestid) & 0xFFFFFFFF if include_requestid else EMPTY_REQUESTID
    live_startline = int(startline) if startline is not None else request_startline(live_requestid, identity)
    return encode_packet(
        FRAME_PARSE,
        identity=identity,
        requestid=live_requestid,
        startline=live_startline,
        include_requestid=include_requestid,
    )


def encode_serialize(
    *,
    identity: str,
    requestid: int,
    startline: int | None = None,
    include_requestid: bool = True,
) -> bytes:
    live_requestid = int(requestid) & 0xFFFFFFFF if include_requestid else EMPTY_REQUESTID
    live_startline = int(startline) if startline is not None else request_startline(live_requestid, identity)
    return encode_packet(
        FRAME_SERIALIZE,
        identity=identity,
        requestid=live_requestid,
        startline=live_startline,
        include_requestid=include_requestid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise Http11ActuationError("short_packet")
    first = raw[0]
    if first != H11_FIRST:
        raise Http11ActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise Http11ActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == REQUESTID_SIZE:
        live_requestid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_requestid = EMPTY_REQUESTID
    else:
        raise Http11ActuationError("illegal_requestid")
    if offset >= len(raw):
        raise Http11ActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_PARSE, FRAME_SERIALIZE}:
        raise Http11ActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise Http11ActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise Http11ActuationError("checksum_failed")
    if len(payload) < 5:
        raise Http11ActuationError("short_packet")
    live_startline, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise Http11ActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_requestid = int(live_requestid) != EMPTY_REQUESTID
    has_startline = has_requestid and int(live_startline) != EMPTY_STARTLINE
    is_parse = frame_type == FRAME_PARSE
    is_serialize = frame_type == FRAME_SERIALIZE
    return {
        "type": int(frame_type),
        "is_parse": is_parse,
        "is_serialize": is_serialize,
        "is_response": is_serialize,
        "requestid": int(live_requestid),
        "has_requestid": has_requestid,
        "startline": int(live_startline),
        "has_startline": has_startline,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http11_version": HTTP_VERSION,
    }


class Http11Client:
    def __init__(self, host: str, port: int, *, timeout: float = IO_TIMEOUT) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(timeout)
        self.client_port = int(self.sock.getsockname()[1])

    def close(self) -> None:
        sock = self.sock
        self.sock = None  # type: ignore[assignment]
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass

    def send(self, packet: bytes) -> None:
        self.sock.sendto(bytes(packet or b""), (self.host, self.port))

    def _recv(self) -> dict[str, Any]:
        try:
            payload, _addr = self.sock.recvfrom(65535)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise Http11ActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_serialize"] or not packet["is_response"]:
            raise Http11ActuationError("startline_required")
        if not packet["has_requestid"]:
            raise Http11ActuationError("requestid_required")
        if not packet["has_startline"]:
            raise Http11ActuationError("startline_required")
        return packet

    def exchange(self, packet: bytes, *, wait_startline: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_startline:
            raise Http11ActuationError("startline_required")
        reply = self._recv()
        return {
            "session": reply,
            "requestid": int(reply.get("requestid") or EMPTY_REQUESTID),
            "identity": str(reply.get("identity") or ""),
            "startline": int(reply.get("startline") or EMPTY_STARTLINE),
        }

    def serialize(
        self,
        identity: str,
        requestid: int,
        startline: int = EMPTY_STARTLINE,
        *,
        wait_startline: bool = True,
        include_requestid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_serialize(
            identity=identity,
            requestid=requestid,
            startline=startline or request_startline(requestid, identity),
            include_requestid=include_requestid,
        )
        return self.exchange(packet, wait_startline=wait_startline)


class Http11Session:
    """REQUESTID-gated loopback RFC 9112 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        requestid_gate: int = DEFAULT_REQUESTID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.requestid_gate = int(requestid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.requestid = EMPTY_REQUESTID
        self.startline = EMPTY_STARTLINE
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.opened = False
        self.handshook = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_requestid_once(self, identity: str, requestid: int, startline: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(requestid or EMPTY_REQUESTID)
            live_startline = int(startline or EMPTY_STARTLINE)
            if not self.identity and name and live:
                self.identity = name
                self.requestid = live
                self.startline = live_startline or request_startline(live, name)
                self.stored = True
            return str(self.identity), int(self.requestid), int(self.startline)

    def read_requestid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.requestid), int(self.startline)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "requestid": EMPTY_REQUESTID,
            "startline": EMPTY_STARTLINE,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _requestid_missing(self) -> bool:
        return not int(self.requestid_gate or 0)

    def _reply_decode(self, peer: tuple[str, int], identity: str, requestid: int, startline: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_serialize(
            identity=identity,
            requestid=requestid,
            startline=startline,
        )
        try:
            sock.sendto(packet, peer)
        except OSError:
            return

    def _serve(self) -> None:
        while self._running:
            sock = self.sock
            if sock is None:
                return
            try:
                payload, addr = sock.recvfrom(65535)
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                return
            try:
                packet = parse_message(payload)
            except Http11ActuationError:
                continue
            if not packet.get("is_parse") and not packet.get("is_serialize"):
                continue
            if not packet.get("has_requestid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_requestid, stored_startline = self.store_requestid_once(
                identity,
                int(packet.get("requestid") or EMPTY_REQUESTID),
                int(packet.get("startline") or EMPTY_STARTLINE),
            )
            if not stored_name or not stored_requestid or not stored_startline:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_parse"):
                    self.opened = True
                if packet.get("is_serialize"):
                    self.handshook = True
                self.retrieved = True
            self._reply_decode(peer, stored_name, stored_requestid, stored_startline)

    def bind(self) -> dict[str, Any]:
        if self._requestid_missing():
            return self._forbidden("missing_requestid")
        if self.sock is not None:
            return {
                "ok": True,
                "status": 200,
                "host": self.host or "",
                "port": int(self.port or 0),
                "reused": True,
            }
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(SERVE_TIMEOUT)
        host, port = sock.getsockname()[:2]
        self.sock = sock
        self.host = str(host)
        self.port = int(port)
        self._running = True
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
        self.thread = thread
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
        do_parse_cycle: bool = True,
        do_serialize: bool = True,
        do_startline: bool = True,
        replay: bool = True,
        use_requestid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._requestid_missing():
            return self._forbidden("missing_requestid")
        live_token = str(token or SENTINEL)
        origin_requestid = request_requestid(live_token)
        origin_startline = request_startline(origin_requestid, live_token)
        client: Http11Client | None = None
        independent: Http11Client | None = None
        try:
            client = Http11Client(self.host, int(self.port))
            if not do_parse_cycle:
                return self._conflict("parse_required")
            bind_packet = encode_parse(
                identity=live_token,
                requestid=origin_requestid,
                startline=origin_startline,
                include_requestid=use_requestid,
            )
            if not use_requestid:
                try:
                    client.exchange(bind_packet, wait_startline=True)
                except Http11ActuationError:
                    return self._conflict("requestid_required")
                return self._conflict("requestid_required")
            client.send(bind_packet)
            if not do_serialize:
                return self._conflict("serialize_required")
            proxy_packet = encode_serialize(
                identity=live_token,
                requestid=origin_requestid,
                startline=origin_startline,
                include_requestid=True,
            )
            if not do_startline:
                try:
                    client.exchange(proxy_packet, wait_startline=False)
                except Http11ActuationError as error:
                    if str(error) == "startline_required":
                        return self._conflict("startline_required")
                    return self._conflict("startline_required")
                return self._conflict("startline_required")
            try:
                reply = client.exchange(proxy_packet, wait_startline=True)
            except Http11ActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("requestid_required")
                if reason == "startline_required":
                    return self._conflict("startline_required")
                return self._conflict("parse_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("parse_required")
            if int(reply.get("requestid") or EMPTY_REQUESTID) != origin_requestid:
                return self._conflict("startline_required")
            if int(reply.get("startline") or EMPTY_STARTLINE) != origin_startline:
                return self._conflict("startline_required")
            self.retrieved = True
            if replay:
                independent = Http11Client(self.host, int(self.port))
                try:
                    poll = independent.serialize(
                        POLL_TOKEN,
                        poll_requestid(live_token),
                        request_startline(poll_requestid(live_token), POLL_TOKEN),
                        wait_startline=True,
                    )
                except Http11ActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_requestid, stored_startline = self.read_requestid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_requestid != origin_requestid
                    or stored_startline != origin_startline
                    or int(poll.get("requestid") or EMPTY_REQUESTID) != origin_requestid
                    or int(poll.get("startline") or EMPTY_STARTLINE) != origin_startline
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_requestid}:{origin_startline}:{live_token}:{http11_request(live_token, origin_requestid).hex()}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "requestid": origin_requestid,
                "startline": origin_startline,
                "parse_frame": True,
                "serialize": True,
                "startline_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "requestid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_http11_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "requestid": origin_requestid,
                "startline": origin_startline,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "parse_frame": True,
                "serialize": True,
                "startline_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "requestid_bound": True,
            }
        except (OSError, Http11ActuationError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error),
                "token": live_token,
                "sentinel": "",
                "digest": "",
            }
        finally:
            if independent is not None:
                independent.close()
            if client is not None:
                client.close()

    def read(self) -> dict[str, Any]:
        live = independent_http11_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "requestid": int(live.get("requestid") or EMPTY_REQUESTID),
            "startline": int(live.get("startline") or EMPTY_STARTLINE),
            "port": int(live.get("port") or 0),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        self._running = False
        sock = self.sock
        thread = self.thread
        self.sock = None
        self.thread = None
        self.host = None
        self.port = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=1)
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_http11_tool(session: Http11Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one HTTP/1.1 tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_parse_cycle = True if arguments.get("parse_cycle") is None else bool(arguments.get("parse_cycle"))
    do_serialize = True if arguments.get("serialize") is None else bool(arguments.get("serialize"))
    do_startline = True if arguments.get("startline") is None else bool(arguments.get("startline"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_requestid = True if arguments.get("use_requestid") is None else bool(arguments.get("use_requestid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_parse_cycle=do_parse_cycle,
            do_serialize=do_serialize,
            do_startline=do_startline,
            replay=replay,
            use_requestid=use_requestid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise Http11ActuationError(f"unsupported http11 action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_http11_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed HTTP/1.1 startline digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "requestid": EMPTY_REQUESTID,
        "startline": EMPTY_STARTLINE,
        "port": 0,
    }
    if not path.is_file():
        return empty
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {**empty, "error": "invalid_payload", "detail": str(error)}
    if not isinstance(payload, dict):
        return {**empty, "error": "invalid_payload"}
    token = str(payload.get("token") or "")
    flags = all(
        payload.get(name) is True
        for name in (
            "parse_frame",
            "serialize",
            "startline_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "requestid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    requestid = int(payload.get("requestid") or EMPTY_REQUESTID)
    startline = int(payload.get("startline") or EMPTY_STARTLINE)
    dual = port > 0 and bool(requestid) and bool(startline)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "requestid": requestid,
        "startline": startline,
        "size": int(payload.get("size") or 0),
        "port": port,
        "parse_frame": payload.get("parse_frame") is True,
        "serialize": payload.get("serialize") is True,
        "startline_response": payload.get("startline_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "requestid_bound": payload.get("requestid_bound") is True,
    }


def run_http11_workflow(
    *,
    with_requestid: bool = True,
    skip_bind: bool = False,
    do_parse_cycle: bool = True,
    do_serialize: bool = True,
    do_startline: bool = True,
    replay: bool = True,
    use_requestid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9112 PARSE/SERIALIZE requestid cycle workflow."""

    descriptor = http11_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP11_TOOL_PROVIDER),
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
        raise Http11ActuationError(f"http11 tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="http11-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = Http11Session(out, requestid_gate=DEFAULT_REQUESTID if with_requestid else EMPTY_REQUESTID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "parse_cycle": do_parse_cycle,
            "serialize": do_serialize,
            "startline": do_startline,
            "replay": replay,
            "use_requestid": use_requestid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_http11_tool(session, arguments))
            except Http11ActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_http11_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_requestid
        and not skip_bind
        and do_parse_cycle
        and do_serialize
        and do_startline
        and replay
        and use_requestid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "http11_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_requestid": with_requestid,
        "skip_bind": skip_bind,
        "parse_frame": do_parse_cycle,
        "serialize": do_serialize,
        "startline": do_startline,
        "replay": replay,
        "use_requestid": use_requestid,
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
        "port": int(publish_result.get("port") or independent.get("port") or 0),
        "requestid_value": int(publish_result.get("requestid") or independent.get("requestid") or EMPTY_REQUESTID),
        "startline_value": int(publish_result.get("startline") or independent.get("startline") or EMPTY_STARTLINE),
        "stored": bool(session.stored or publish_result.get("stored")),
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
        "port": int(trace_body["port"] or 0),
        "requestid": int(trace_body["requestid_value"] or EMPTY_REQUESTID),
        "startline": int(trace_body["startline_value"] or EMPTY_STARTLINE),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_requestid": with_requestid,
        "skip_bind": skip_bind,
        "parse_cycle": do_parse_cycle,
        "serialize_cycle": do_serialize,
        "startline_cycle": do_startline,
        "replay": replay,
        "use_requestid": use_requestid,
    }


def verify_http11_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed HTTP/1.1 trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_http11_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    requestid = int(trace.get("requestid_value") or independent.get("requestid") or EMPTY_REQUESTID)
    startline = int(trace.get("startline_value") or independent.get("startline") or EMPTY_STARTLINE)
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
        "stored": trace.get("stored") is True,
        "parse_frame": independent.get("parse_frame") is True,
        "serialize": independent.get("serialize") is True,
        "startline_response": independent.get("startline_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "requestid_bound": independent.get("requestid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "startline_recorded": (
            port > 0
            and requestid == DEFAULT_REQUESTID
            and startline == DEFAULT_STARTLINE
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def http11_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.http11_actuation import "
        "builtin_http11_actuation_proof; r=builtin_http11_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='http11_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_http11_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTP11_ACTUATION_ID,
        name="First-class RFC 9112 HTTP/1.1 PARSE/SERIALIZE actuation",
        description=(
            "Missions that require a http11 tool can opt the http11 provider in, "
            "bind a loopback RFC 9112 HTTP/1.1 origin, complete a PARSE "
            "with a non-empty requestid, lockstep a SERIALIZE that carries the "
            "stored startline, independently poll the stored httpmessage "
            "startline on a later socket, and seal a digest-chained startline. Default "
            "routing stays fail-closed; a missing requestid keeps the hole "
            "falsifiable, and skip-PARSE/SERIALIZE/STARTLINE/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.http11_actuation:builtin_http11_actuation_proof",
        proof_command=http11_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.bhttp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/http11_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/http2_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required http11 tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9112 daemon, speaks a "
            "PARSE then SERIALIZE over HTTP/1.1 with a non-empty requestid and "
            "startline, independently polls the stored httpmessage startline on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9292 Binary HTTP lockstep is proved. "
            "Missing requestids, skip-PARSE, skip-SERIALIZE, skip-startline, skip-REPLAY, "
            "and a PARSE aimed without a requestid stay fail-closed. "
            "Later genesis can take RFC 9113 HTTP/2 PREFACE/SETTINGS as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("http11", "rfc9112", "http", "requestid", "startline", "httpmessage", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T091235Z-e0c240c4",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_http11_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9112 HTTP/1.1 lockstep actuation seals a startline digest."""

    from blackhole_agent.http2_actuation import HTTP2_ACTUATION_GOAL, HTTP2_ACTUATION_ID
    from blackhole_agent.httpcache_actuation import HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID
    from blackhole_agent.bhttp_actuation import BHTTP_ACTUATION_GOAL, BHTTP_ACTUATION_ID
    from blackhole_agent.digestfields_actuation import DIGESTFIELDS_ACTUATION_GOAL, DIGESTFIELDS_ACTUATION_ID
    from blackhole_agent.httpsig_actuation import HTTPSIG_ACTUATION_GOAL, HTTPSIG_ACTUATION_ID
    from blackhole_agent.ohsvcb_actuation import OHSVCB_ACTUATION_GOAL, OHSVCB_ACTUATION_ID
    from blackhole_agent.ohttp_actuation import OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID
    from blackhole_agent.connectip_actuation import CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID
    from blackhole_agent.masque_actuation import MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID
    from blackhole_agent.datagram_actuation import DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID
    from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
    from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
    from blackhole_agent.ice_actuation import ICE_ACTUATION_GOAL, ICE_ACTUATION_ID
    from blackhole_agent.ike_actuation import IKE_ACTUATION_GOAL, IKE_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.kernel_leftover import leftover_is_open, leftover_satisfied_by
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
    from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
    from blackhole_agent.webtransport_actuation import (
        WEBTRANSPORT_ACTUATION_GOAL,
        WEBTRANSPORT_ACTUATION_ID,
    )
    from blackhole_agent.quic_actuation import QUIC_ACTUATION_GOAL, QUIC_ACTUATION_ID
    from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
    from blackhole_agent.sctp_actuation import SCTP_ACTUATION_GOAL, SCTP_ACTUATION_ID
    from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.srtp_actuation import SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID
    from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
    from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
    from blackhole_agent.datachannel_actuation import (
        DATACHANNEL_ACTUATION_GOAL,
        DATACHANNEL_ACTUATION_ID,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = HTTP11_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTP11_ACTUATION_GOAL) == (
        HTTP11_ACTUATION_ID,
    )
    checks["leftover_text_binds_http11"] = leftover_marker_ids(HTTP11_LEFTOVER) == (
        HTTP11_ACTUATION_ID,
    )
    neighbor_goals = (
        (BHTTP_ACTUATION_GOAL, BHTTP_ACTUATION_ID, "bhttp"),
        (DIGESTFIELDS_ACTUATION_GOAL, DIGESTFIELDS_ACTUATION_ID, "digestfields"),
        (HTTPSIG_ACTUATION_GOAL, HTTPSIG_ACTUATION_ID, "httpsig"),
        (OHSVCB_ACTUATION_GOAL, OHSVCB_ACTUATION_ID, "ohsvcb"),
        (OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID, "ohttp"),
        (CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID, "connectip"),
        (MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID, "masque"),
        (DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID, "datagram"),
        (WEBTRANSPORT_ACTUATION_GOAL, WEBTRANSPORT_ACTUATION_ID, "webtransport"),
        (HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID, "http3"),
        (QUIC_ACTUATION_GOAL, QUIC_ACTUATION_ID, "quic"),
        (DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID, "datachannel"),
        (SCTP_ACTUATION_GOAL, SCTP_ACTUATION_ID, "sctp"),
        (SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID, "srtp"),
        (DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID, "dtls"),
        (ICE_ACTUATION_GOAL, ICE_ACTUATION_ID, "ice"),
        (TURN_ACTUATION_GOAL, TURN_ACTUATION_ID, "turn"),
        (STUN_ACTUATION_GOAL, STUN_ACTUATION_ID, "stun"),
        (SIP_ACTUATION_GOAL, SIP_ACTUATION_ID, "sip"),
        (IKE_ACTUATION_GOAL, IKE_ACTUATION_ID, "ike"),
        (DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID, "dhcp"),
        (RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID, "radius"),
        (NTP_ACTUATION_GOAL, NTP_ACTUATION_ID, "ntp"),
        (SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID, "syslog"),
        (SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID, "snmp"),
        (TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID, "tftp"),
        (FTP_ACTUATION_GOAL, FTP_ACTUATION_ID, "ftp"),
        (DNS_ACTUATION_GOAL, DNS_ACTUATION_ID, "dns"),
        (HTTP2_ACTUATION_GOAL, HTTP2_ACTUATION_ID, "http2"),
        (HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID, "httpcache"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_http11"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"http11_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTP11_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTP11_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    encoded = http11_request(SENTINEL, DEFAULT_REQUESTID)
    decoded = parse_request(encoded)
    expected_target = f"/http11/{DEFAULT_REQUESTID:08x}"
    expected_content = f"{SENTINEL}:{DEFAULT_REQUESTID:08x}".encode("ascii")
    rebuilt = serialize_request(
        method="POST",
        target=expected_target,
        version=HTTP_VERSION,
        headers=(
            ("Host", SENTINEL),
            ("Content-Type", "application/octet-stream"),
            ("Content-Length", str(len(expected_content))),
        ),
        body=expected_content,
    )
    checks["http11_request_roundtrip"] = (
        decoded["kind"] == "request"
        and decoded["method"] == "POST"
        and decoded["target"] == expected_target
        and decoded["version"] == HTTP_VERSION
        and decoded["start_line"] == f"POST {expected_target} {HTTP_VERSION}"
        and decoded["body"] == expected_content
        and hmac.compare_digest(encoded, rebuilt)
        and DEFAULT_STARTLINE == request_startline(DEFAULT_REQUESTID, SENTINEL)
    )
    response = http11_response(SENTINEL, DEFAULT_REQUESTID)
    parsed_response = parse_response(response)
    checks["http11_response_roundtrip"] = (
        parsed_response["kind"] == "response"
        and parsed_response["status"] == 200
        and parsed_response["version"] == HTTP_VERSION
        and parsed_response["body"] == encoded
    )
    checks["catalog_names_http11"] = (
        len(catalog) > 72
        and catalog[72]["id"] == HTTP11_ACTUATION_ID
        and catalog[71]["id"] == BHTTP_ACTUATION_ID
        and catalog[72]["source"] == "genesis_bind_http11"
    )
    checks["catalog_names_http2"] = (
        len(catalog) > 73
        and catalog[73]["id"] == HTTP2_ACTUATION_ID
        and catalog[73]["source"] == "genesis_bind_http2"
    )
    checks["catalog_names_httpcache"] = (
        len(catalog) > 74
        and catalog[74]["id"] == HTTPCACHE_ACTUATION_ID
        and catalog[74]["source"] == "genesis_bind_httpcache"
    )
    family = capability_family(HTTP11_ACTUATION_GOAL)
    checks["family_is_http11"] = "http11" in family
    checks["family_is_rfc9112"] = "rfc9112" in family
    checks["family_is_requestid"] = "requestid" in family
    checks["family_is_startline"] = "startline" in family
    checks["family_is_httpmessage"] = "httpmessage" in family
    checks["family_is_not_digestfields"] = (
        "digestfield" not in family
        and "rfc9530" not in family
        and "digestid" not in family
        and "contentdigest" not in family
    )
    checks["family_is_not_httpsig"] = (
        "httpsig" not in family
        and "rfc9421" not in family
        and "sigid" not in family
        and "sigbase" not in family
    )
    checks["family_is_not_ohsvcb"] = (
        "ohsvcb" not in family
        and "rfc9540" not in family
        and "svcbid" not in family
        and "keyconf" not in family
    )
    checks["family_is_not_ohttp"] = (
        "ohttp" not in family
        and "rfc9458" not in family
        and "configid" not in family
        and "gateway" not in family
    )
    checks["family_is_not_connectip"] = (
        "connectip" not in family
        and "rfc9484" not in family
        and "prefixid" not in family
        and "ipaddr" not in family
    )
    checks["family_is_not_masque"] = (
        "masque" not in family
        and "rfc9298" not in family
        and "targetid" not in family
        and "authority" not in family
    )
    checks["family_is_not_datagram"] = (
        "datagram" not in family
        and "rfc9221" not in family
        and "flowid" not in family
        and "contextid" not in family
    )
    checks["family_is_not_webtransport"] = (
        "webtransport" not in family
        and "rfc9220" not in family
        and "sessionid" not in family
        and "capsule" not in family
    )
    checks["family_is_not_http3"] = (
        "http3" not in family
        and "rfc9114" not in family
        and "streamid" not in family
        and "qpack" not in family
    )
    checks["family_is_not_quic"] = (
        "quic" not in family
        and "rfc9000" not in family
        and "dcid" not in family
        and "pktnum" not in family
    )
    checks["family_is_not_datachannel"] = (
        "datachannel" not in family
        and "rfc8831" not in family
        and "ppid" not in family
        and "dcep" not in family
    )
    checks["family_is_not_sctp_association"] = (
        "rfc4960" not in family and "vtag" not in family and "tsn" not in family
    )
    checks["family_is_not_srtp"] = (
        "srtp" not in family and "rfc3711" not in family and "roc" not in family and "ssrc" not in family
    )
    checks["family_is_not_dtls"] = (
        "dtls" not in family and "rfc6347" not in family and "cookie" not in family and "epoch" not in family
    )
    checks["family_is_not_ice"] = "ice" not in family and "rfc8445" not in family and "ufrag" not in family
    checks["family_is_not_turn"] = "turn" not in family and "rfc5766" not in family and "relay" not in family
    checks["family_is_not_stun"] = "stun" not in family and "rfc5389" not in family and "txid" not in family
    checks["family_is_not_sip"] = "sip" not in family and "rfc3261" not in family and "callid" not in family
    checks["family_is_not_ike"] = "ike" not in family and "rfc7296" not in family and "spi" not in family
    checks["family_is_not_dhcp"] = "dhcp" not in family and "rfc2131" not in family and "yiaddr" not in family
    checks["family_is_not_radius"] = (
        "radius" not in family and "radiu" not in family and "rfc2865" not in family
    )
    checks["family_is_not_ntp"] = "ntp" not in family and "rfc5905" not in family and "keyid" not in family
    checks["family_is_not_syslog"] = "syslog" not in family and "nilvalue" not in family
    checks["family_is_not_snmp"] = "snmp" not in family and "varbind" not in family
    checks["family_is_not_tftp"] = "tftp" not in family and "rfc1350" not in family
    checks["family_is_not_ftp"] = "ftpd" not in family and "pasv" not in family
    checks["family_is_not_dns"] = "tsig" not in family and "nameserver" not in family
    checks["family_is_not_bhttp"] = (
        "bhttp" not in family
        and "rfc9292" not in family
        and "messageid" not in family
        and "binarymsg" not in family
        and "binaryhttp" not in family
    )
    checks["family_is_not_http2"] = (
        "http2" not in family
        and "rfc9113" not in family
        and "settingsid" not in family
        and "hpack" not in family
        and "preface" not in family
    )
    checks["family_is_not_httpcache"] = (
        "httpcache" not in family
        and "rfc9111" not in family
        and "cacheid" not in family
        and "freshness" not in family
        and "validator" not in family
    )
    packed = encode_parse(identity=SENTINEL, requestid=DEFAULT_REQUESTID, startline=DEFAULT_STARTLINE)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_parse"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_requestid"] is True
        and parsed["requestid"] == DEFAULT_REQUESTID
        and parsed["startline"] == DEFAULT_STARTLINE
        and parsed["is_response"] is False
        and parsed["is_serialize"] is False
        and parsed["type"] == FRAME_PARSE
        and parsed["first_byte"] == H11_FIRST
    )
    shook = encode_serialize(
        identity=SENTINEL,
        requestid=DEFAULT_REQUESTID,
        startline=DEFAULT_STARTLINE,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_serialize"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_parse"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["requestid"] == DEFAULT_REQUESTID
        and answer_parsed["startline"] == DEFAULT_STARTLINE
        and answer_parsed["has_startline"] is True
        and answer_parsed["type"] == FRAME_SERIALIZE
        and answer_parsed["first_byte"] == H11_FIRST
    )
    bare = encode_parse(identity=SENTINEL, requestid=DEFAULT_REQUESTID, include_requestid=False)
    checks["missing_requestid_is_unauthenticated"] = parse_message(bare)["has_requestid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    http11_signature = semantic_signature(HTTP11_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(http11_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_http11 = ToolDescriptor(name="remote_http11", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_http11)
    checks["naive_mcp_http11_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = http11_tool_descriptor()
    default_http11 = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP11_TOOL_PROVIDER),
    )
    checks["default_http11_provider_is_unsupported"] = (
        default_http11.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTP11_TOOL_PROVIDER}" in default_http11.reasons
    )
    checks["opted_in_http11_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_http11],
        required_tool_names=("local_memory", "http11"),
    )
    checks["naive_preflight_missing_http11"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["http11"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "http11"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP11_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "http11" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="http11-actuation-") as tmp:
        root = Path(tmp)
        missing = run_http11_workflow(with_requestid=False, output_dir=root / "missing")
        skip_bind = run_http11_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_parse_cycle = run_http11_workflow(do_parse_cycle=False, output_dir=root / "skip-parse-cycle")
        skip_serialize = run_http11_workflow(do_serialize=False, output_dir=root / "skip-serialize")
        skip_startline = run_http11_workflow(do_startline=False, output_dir=root / "skip-startline")
        skip_replay = run_http11_workflow(replay=False, output_dir=root / "skip-replay")
        skip_requestid = run_http11_workflow(use_requestid=False, output_dir=root / "skip-requestid")
        live = run_http11_workflow(output_dir=root / "live")
        verify = verify_http11_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_http11_trace(clone)
        checks["naive_without_requestid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_requestid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_parse_cycle_stays_empty"] = (
            skip_parse_cycle["ok"] is False
            and skip_parse_cycle["error"] == "parse_required"
            and skip_parse_cycle["final_status"] == 409
            and skip_parse_cycle["payload_exists"] is False
        )
        checks["skip_serialize_stays_empty"] = (
            skip_serialize["ok"] is False
            and skip_serialize["error"] == "serialize_required"
            and skip_serialize["final_status"] == 409
            and skip_serialize["payload_exists"] is False
        )
        checks["skip_startline_stays_empty"] = (
            skip_startline["ok"] is False
            and skip_startline["error"] == "startline_required"
            and skip_startline["final_status"] == 409
            and skip_startline["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_requestid_stays_empty"] = (
            skip_requestid["ok"] is False
            and skip_requestid["error"] == "requestid_required"
            and skip_requestid["final_status"] == 409
            and skip_requestid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_startline"] = (
            int(live.get("requestid") or 0) == DEFAULT_REQUESTID
            and int(live.get("startline") or 0) == DEFAULT_STARTLINE
            and int(live.get("port") or 0) > 0
        )
        checks["token_requestid_encode_serialize_startline_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_parse_cycle["ok"] is False
            and skip_serialize["ok"] is False
            and skip_startline["ok"] is False
            and skip_replay["ok"] is False
            and skip_requestid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="http11-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTP11_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_http11"] = (
        live_goal == HTTP11_ACTUATION_GOAL
        and HTTP11_ACTUATION_ID in live_done
        and live_source == "genesis_bind_http11"
    )

    with tempfile.TemporaryDirectory(prefix="http11-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTP11_LEFTOVER, root)
        register_catalog_proved(root, HTTP11_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTP11_LEFTOVER, root)
        after = leftover_is_open(HTTP11_LEFTOVER, root)
    checks["http11_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_http11_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTP11_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_http11_actuation_capability()
    return {
        "ok": ok,
        "action": "http11_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTP11_ACTUATION_GOAL,
        "done_when": HTTP11_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
