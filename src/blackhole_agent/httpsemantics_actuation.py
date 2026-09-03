"""Drive a first-class HTTP Semantics tool through RFC 9110 GET/HEAD.

Tool routing already fails missions that require ``httpsemantics``: hosted
httpsemantics endpoints stay on the unsupported MCP provider, and no first-party
httpsemantics provider is executable. Unbound therefore cannot speak a GET,
lockstep a HEAD methodid handshake over HTTP HTTP Semantics METHODID,
independently poll the stored field section, or seal a fieldsection digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``httpsemantics`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9110 daemon
- keep a missing-methodid client so the httpsemantics-methodid hole stays falsifiable
- refuse HEAD until a GET lands with a non-empty methodid
- independently poll the stored field section on a later client socket
- persist a sealed fieldsection digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9111 HTTP Caching
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
    HTTPSMANTICS_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    httpsemantics_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTPSMANTICS_ACTUATION_ID = "capability.httpsemantics-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-HS-OK"
POLL_TOKEN = "BH-HS-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_METHODID = 0
EMPTY_FIELDSECTION = 0
HS_FIRST = 0x53  # RFC 9110 HTTP Semantics (ASCII 'S')
METHODID_SIZE = 4
FIELDSECTION_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_HEAD = 0x02  # RFC 9110 HEAD (field section, no content)
FRAME_GET = 0x01  # RFC 9110 GET (representation + field section)
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
TCHAR = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "!#$%&'*+-.^_`|~"
)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS", "TRACE"})
HTTPSMANTICS_LEFTOVER = (
    "Later genesis can take RFC 9110 HTTP Semantics GET/HEAD over a "
    "methodid-gated fieldsection digest."
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


HTTPSMANTICS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPSMANTICS_ACTUATION_ID};"
    f"capability_proved:{HTTPSMANTICS_ACTUATION_ID};"
    "no_skill_route"
)
HTTPSMANTICS_ACTUATION_GOAL = (
    "Repair rfc9110 httpsemantics get/head cycle cannot land over http "
    "httpsemantics methodid: hosted httpsemantics endpoints remain unsupported so a GET then "
    "HEAD methodid handshake cannot land and a sealed fieldsection digest "
    "cannot be produced. A missing httpsemantics methodid stays forbidden; fail-closed "
    "routing never opts the httpsemantics provider in. An independent later poll of the "
    "stored fieldsection keeps the hole falsifiable."
)


class HttpsemanticsActuationError(RuntimeError):
    """Raised when the HTTP Semantics session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def is_token(value: str) -> bool:
    """RFC 9110 section 5.6.2 token (1*tchar)."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def parse_field_name(value: str) -> str:
    """RFC 9110 section 5.1 field-name: case-insensitive token."""

    raw = str(value or "").strip()
    if not is_token(raw):
        raise HttpsemanticsActuationError("illegal_field_name")
    return raw.lower()


def parse_field_value(value: str) -> str:
    """RFC 9110 section 5.5 field-value: VCHAR / SP / HTAB, no CR or LF."""

    raw = str(value or "")
    if "\r" in raw or "\n" in raw:
        raise HttpsemanticsActuationError("illegal_field_value")
    for char in raw:
        code = ord(char)
        if code != 0x09 and (code < 0x20 or code > 0x7E):
            raise HttpsemanticsActuationError("illegal_field_value")
    return raw.strip()


def parse_field_section(headers: Sequence[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """RFC 9110 section 5: ordered field section with case-insensitive names."""

    fields: list[tuple[str, str]] = []
    for name, value in headers:
        fields.append((parse_field_name(name), parse_field_value(value)))
    return tuple(fields)


def format_field_section(fields: Sequence[tuple[str, str]]) -> str:
    """Serialize a field section as HTTP header lines without the blank terminator."""

    lines: list[str] = []
    for name, value in parse_field_section(fields):
        lines.append(f"{name}: {value}")
    return "\r\n".join(lines)


def method_is_safe(method: str) -> bool:
    """RFC 9110 section 9.2.1 safe methods."""

    return str(method or "").upper() in SAFE_METHODS


def method_is_idempotent(method: str) -> bool:
    """RFC 9110 section 9.2.2 idempotent methods."""

    return str(method or "").upper() in IDEMPOTENT_METHODS


def method_allows_request_content(method: str) -> bool:
    """RFC 9110 sections 9.3.1 and 9.3.2: GET/HEAD content has no defined semantics."""

    return str(method or "").upper() not in {"GET", "HEAD", "TRACE"}


def representation_body(identity: str, methodid: int) -> bytes:
    keyid = f"{int(methodid) & 0xFFFFFFFF:08x}"
    return f"{identity}:{keyid}".encode("ascii")


def representation_fields(identity: str, methodid: int) -> tuple[tuple[str, str], ...]:
    """RFC 9110 representation metadata bound to methodid (header field section)."""

    body = representation_body(identity, methodid)
    keyid = f"{int(methodid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return parse_field_section(
        (
            ("Content-Type", "application/octet-stream"),
            ("Content-Length", str(len(body))),
            ("ETag", f'"{keyid}"'),
            ("X-Method-Id", keyid),
            ("X-Identity", host),
        )
    )


def canonical_field_section(identity: str, methodid: int) -> str:
    return format_field_section(representation_fields(identity, methodid))


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HttpsemanticsActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HttpsemanticsActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HttpsemanticsActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HttpsemanticsActuationError("illegal_field")
        headers.append((parse_field_name(name), parse_field_value(value)))
    return lines[0], headers, body


def get_request(identity: str, methodid: int) -> bytes:
    """RFC 9110 section 9.3.1 GET for the methodid-gated target resource."""

    keyid = f"{int(methodid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /httpsemantics/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "\r\n"
    ).encode("ascii")


def head_request(identity: str, methodid: int) -> bytes:
    """RFC 9110 section 9.3.2 HEAD: same as GET, no representation content."""

    keyid = f"{int(methodid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"HEAD /httpsemantics/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "field_section": parse_field_section(headers),
        "body": body,
        "host": fields.get("host", ""),
        "safe": method_is_safe(method),
        "idempotent": method_is_idempotent(method),
        "allows_content": method_allows_request_content(method),
    }


def get_response(identity: str, methodid: int) -> bytes:
    """RFC 9110 GET response: field section plus representation content."""

    fields = format_field_section(representation_fields(identity, methodid))
    body = representation_body(identity, methodid)
    return f"HTTP/1.1 200 OK\r\n{fields}\r\n\r\n".encode("ascii") + body


def head_response(identity: str, methodid: int) -> bytes:
    """RFC 9110 HEAD response: same field section as GET, no content."""

    fields = format_field_section(representation_fields(identity, methodid))
    return f"HTTP/1.1 200 OK\r\n{fields}\r\n\r\n".encode("ascii")


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = parse_field_section(headers)
    mapped = dict(fields)
    try:
        content_length = int(mapped.get("content-length") or "0")
    except ValueError as error:
        raise HttpsemanticsActuationError("illegal_content_length") from error
    return {
        "kind": "response",
        "start_line": start,
        "status": 200 if start.startswith("HTTP/1.1 200") else 0,
        "headers": headers,
        "field_section": fields,
        "body": body,
        "content_length": content_length,
        "etag": mapped.get("etag", ""),
        "content_omitted": len(body) == 0,
        "content_length_matches_body": content_length == len(body),
    }


def field_section_matches(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """RFC 9110 9.3.2: HEAD SHOULD send the same header fields as GET."""

    return tuple(left.get("field_section") or ()) == tuple(right.get("field_section") or ())


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
        raise HttpsemanticsActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise HttpsemanticsActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise HttpsemanticsActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HttpsemanticsActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_methodid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"methodid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_methodid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-methodid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_fieldsection(methodid: int = EMPTY_METHODID, token: str = SENTINEL) -> int:
    material = canonical_field_section(token or SENTINEL, int(methodid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_METHODID = request_methodid(SENTINEL)
DEFAULT_FIELDSECTION = request_fieldsection(DEFAULT_METHODID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    methodid: int,
    fieldsection: int,
    include_methodid: bool = True,
) -> bytes:
    live_methodid = int(methodid) & 0xFFFFFFFF if include_methodid else EMPTY_METHODID
    live_fieldsection = int(fieldsection) & 0xFFFFFFFF if include_methodid and live_methodid else EMPTY_FIELDSECTION
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_fieldsection, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_methodid) if live_methodid else b""
    header = bytearray()
    header.append(HS_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_get(
    *,
    identity: str,
    methodid: int,
    fieldsection: int | None = None,
    include_methodid: bool = True,
) -> bytes:
    live_methodid = int(methodid) & 0xFFFFFFFF if include_methodid else EMPTY_METHODID
    live_fieldsection = int(fieldsection) if fieldsection is not None else request_fieldsection(live_methodid, identity)
    return encode_packet(
        FRAME_GET,
        identity=identity,
        methodid=live_methodid,
        fieldsection=live_fieldsection,
        include_methodid=include_methodid,
    )


def encode_head(
    *,
    identity: str,
    methodid: int,
    fieldsection: int | None = None,
    include_methodid: bool = True,
) -> bytes:
    live_methodid = int(methodid) & 0xFFFFFFFF if include_methodid else EMPTY_METHODID
    live_fieldsection = int(fieldsection) if fieldsection is not None else request_fieldsection(live_methodid, identity)
    return encode_packet(
        FRAME_HEAD,
        identity=identity,
        methodid=live_methodid,
        fieldsection=live_fieldsection,
        include_methodid=include_methodid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HttpsemanticsActuationError("short_packet")
    first = raw[0]
    if first != HS_FIRST:
        raise HttpsemanticsActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise HttpsemanticsActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == METHODID_SIZE:
        live_methodid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_methodid = EMPTY_METHODID
    else:
        raise HttpsemanticsActuationError("illegal_methodid")
    if offset >= len(raw):
        raise HttpsemanticsActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_GET, FRAME_HEAD}:
        raise HttpsemanticsActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HttpsemanticsActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HttpsemanticsActuationError("checksum_failed")
    if len(payload) < 5:
        raise HttpsemanticsActuationError("short_packet")
    live_fieldsection, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HttpsemanticsActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_methodid = int(live_methodid) != EMPTY_METHODID
    has_fieldsection = has_methodid and int(live_fieldsection) != EMPTY_FIELDSECTION
    is_get = frame_type == FRAME_GET
    is_head = frame_type == FRAME_HEAD
    return {
        "type": int(frame_type),
        "is_get": is_get,
        "is_head": is_head,
        "is_response": is_head,
        "methodid": int(live_methodid),
        "has_methodid": has_methodid,
        "fieldsection": int(live_fieldsection),
        "has_fieldsection": has_fieldsection,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http_semantics": "RFC9110",
    }


class HttpsemanticsClient:
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
            raise HttpsemanticsActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_head"] or not packet["is_response"]:
            raise HttpsemanticsActuationError("fieldsection_required")
        if not packet["has_methodid"]:
            raise HttpsemanticsActuationError("methodid_required")
        if not packet["has_fieldsection"]:
            raise HttpsemanticsActuationError("fieldsection_required")
        return packet

    def exchange(self, packet: bytes, *, wait_fieldsection: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_fieldsection:
            raise HttpsemanticsActuationError("fieldsection_required")
        reply = self._recv()
        return {
            "session": reply,
            "methodid": int(reply.get("methodid") or EMPTY_METHODID),
            "identity": str(reply.get("identity") or ""),
            "fieldsection": int(reply.get("fieldsection") or EMPTY_FIELDSECTION),
        }

    def head(
        self,
        identity: str,
        methodid: int,
        fieldsection: int = EMPTY_FIELDSECTION,
        *,
        wait_fieldsection: bool = True,
        include_methodid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_head(
            identity=identity,
            methodid=methodid,
            fieldsection=fieldsection or request_fieldsection(methodid, identity),
            include_methodid=include_methodid,
        )
        return self.exchange(packet, wait_fieldsection=wait_fieldsection)


class HttpsemanticsSession:
    """METHODID-gated loopback RFC 9110 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        methodid_gate: int = DEFAULT_METHODID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.methodid_gate = int(methodid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.methodid = EMPTY_METHODID
        self.fieldsection = EMPTY_FIELDSECTION
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

    def store_methodid_once(self, identity: str, methodid: int, fieldsection: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(methodid or EMPTY_METHODID)
            live_fieldsection = int(fieldsection or EMPTY_FIELDSECTION)
            if not self.identity and name and live:
                self.identity = name
                self.methodid = live
                self.fieldsection = live_fieldsection or request_fieldsection(live, name)
                self.stored = True
            return str(self.identity), int(self.methodid), int(self.fieldsection)

    def read_methodid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.methodid), int(self.fieldsection)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "methodid": EMPTY_METHODID,
            "fieldsection": EMPTY_FIELDSECTION,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _methodid_missing(self) -> bool:
        return not int(self.methodid_gate or 0)

    def _reply_head(self, peer: tuple[str, int], identity: str, methodid: int, fieldsection: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_head(
            identity=identity,
            methodid=methodid,
            fieldsection=fieldsection,
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
            except HttpsemanticsActuationError:
                continue
            if not packet.get("is_get") and not packet.get("is_head"):
                continue
            if not packet.get("has_methodid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_methodid, stored_fieldsection = self.store_methodid_once(
                identity,
                int(packet.get("methodid") or EMPTY_METHODID),
                int(packet.get("fieldsection") or EMPTY_FIELDSECTION),
            )
            if not stored_name or not stored_methodid or not stored_fieldsection:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_get"):
                    self.opened = True
                if packet.get("is_head"):
                    self.handshook = True
                self.retrieved = True
            self._reply_head(peer, stored_name, stored_methodid, stored_fieldsection)

    def bind(self) -> dict[str, Any]:
        if self._methodid_missing():
            return self._forbidden("missing_methodid")
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
        do_get_cycle: bool = True,
        do_head: bool = True,
        do_fieldsection: bool = True,
        replay: bool = True,
        use_methodid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._methodid_missing():
            return self._forbidden("missing_methodid")
        live_token = str(token or SENTINEL)
        origin_methodid = request_methodid(live_token)
        origin_fieldsection = request_fieldsection(origin_methodid, live_token)
        client: HttpsemanticsClient | None = None
        independent: HttpsemanticsClient | None = None
        try:
            client = HttpsemanticsClient(self.host, int(self.port))
            if not do_get_cycle:
                return self._conflict("get_required")
            bind_packet = encode_get(
                identity=live_token,
                methodid=origin_methodid,
                fieldsection=origin_fieldsection,
                include_methodid=use_methodid,
            )
            if not use_methodid:
                try:
                    client.exchange(bind_packet, wait_fieldsection=True)
                except HttpsemanticsActuationError:
                    return self._conflict("methodid_required")
                return self._conflict("methodid_required")
            client.send(bind_packet)
            if not do_head:
                return self._conflict("head_required")
            proxy_packet = encode_head(
                identity=live_token,
                methodid=origin_methodid,
                fieldsection=origin_fieldsection,
                include_methodid=True,
            )
            if not do_fieldsection:
                try:
                    client.exchange(proxy_packet, wait_fieldsection=False)
                except HttpsemanticsActuationError as error:
                    if str(error) == "fieldsection_required":
                        return self._conflict("fieldsection_required")
                    return self._conflict("fieldsection_required")
                return self._conflict("fieldsection_required")
            try:
                reply = client.exchange(proxy_packet, wait_fieldsection=True)
            except HttpsemanticsActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("methodid_required")
                if reason == "fieldsection_required":
                    return self._conflict("fieldsection_required")
                return self._conflict("get_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("get_required")
            if int(reply.get("methodid") or EMPTY_METHODID) != origin_methodid:
                return self._conflict("fieldsection_required")
            if int(reply.get("fieldsection") or EMPTY_FIELDSECTION) != origin_fieldsection:
                return self._conflict("fieldsection_required")
            self.retrieved = True
            if replay:
                independent = HttpsemanticsClient(self.host, int(self.port))
                try:
                    poll = independent.head(
                        POLL_TOKEN,
                        poll_methodid(live_token),
                        request_fieldsection(poll_methodid(live_token), POLL_TOKEN),
                        wait_fieldsection=True,
                    )
                except HttpsemanticsActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_methodid, stored_fieldsection = self.read_methodid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_methodid != origin_methodid
                    or stored_fieldsection != origin_fieldsection
                    or int(poll.get("methodid") or EMPTY_METHODID) != origin_methodid
                    or int(poll.get("fieldsection") or EMPTY_FIELDSECTION) != origin_fieldsection
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_methodid}:{origin_fieldsection}:{live_token}:{canonical_field_section(live_token, origin_methodid)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "methodid": origin_methodid,
                "fieldsection": origin_fieldsection,
                "get_frame": True,
                "head": True,
                "fieldsection_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "methodid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_httpsemantics_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "methodid": origin_methodid,
                "fieldsection": origin_fieldsection,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "get_frame": True,
                "head": True,
                "fieldsection_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "methodid_bound": True,
            }
        except (OSError, HttpsemanticsActuationError) as error:
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
        live = independent_httpsemantics_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "methodid": int(live.get("methodid") or EMPTY_METHODID),
            "fieldsection": int(live.get("fieldsection") or EMPTY_FIELDSECTION),
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


def call_httpsemantics_tool(session: HttpsemanticsSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one HTTP Semantics tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_get_cycle = True if arguments.get("get_cycle") is None else bool(arguments.get("get_cycle"))
    do_head = True if arguments.get("head") is None else bool(arguments.get("head"))
    do_fieldsection = True if arguments.get("fieldsection") is None else bool(arguments.get("fieldsection"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_methodid = True if arguments.get("use_methodid") is None else bool(arguments.get("use_methodid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_get_cycle=do_get_cycle,
            do_head=do_head,
            do_fieldsection=do_fieldsection,
            replay=replay,
            use_methodid=use_methodid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HttpsemanticsActuationError(f"unsupported httpsemantics action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_httpsemantics_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed HTTP Semantics fieldsection digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "methodid": EMPTY_METHODID,
        "fieldsection": EMPTY_FIELDSECTION,
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
            "get_frame",
            "head",
            "fieldsection_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "methodid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    methodid = int(payload.get("methodid") or EMPTY_METHODID)
    fieldsection = int(payload.get("fieldsection") or EMPTY_FIELDSECTION)
    dual = port > 0 and bool(methodid) and bool(fieldsection)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "methodid": methodid,
        "fieldsection": fieldsection,
        "size": int(payload.get("size") or 0),
        "port": port,
        "get_frame": payload.get("get_frame") is True,
        "head": payload.get("head") is True,
        "fieldsection_response": payload.get("fieldsection_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "methodid_bound": payload.get("methodid_bound") is True,
    }


def run_httpsemantics_workflow(
    *,
    with_methodid: bool = True,
    skip_bind: bool = False,
    do_get_cycle: bool = True,
    do_head: bool = True,
    do_fieldsection: bool = True,
    replay: bool = True,
    use_methodid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9110 GET/HEAD methodid cycle workflow."""

    descriptor = httpsemantics_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPSMANTICS_TOOL_PROVIDER),
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
        raise HttpsemanticsActuationError(f"httpsemantics tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="httpsemantics-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HttpsemanticsSession(out, methodid_gate=DEFAULT_METHODID if with_methodid else EMPTY_METHODID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "get_cycle": do_get_cycle,
            "head": do_head,
            "fieldsection": do_fieldsection,
            "replay": replay,
            "use_methodid": use_methodid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_httpsemantics_tool(session, arguments))
            except HttpsemanticsActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_httpsemantics_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_methodid
        and not skip_bind
        and do_get_cycle
        and do_head
        and do_fieldsection
        and replay
        and use_methodid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "httpsemantics_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_methodid": with_methodid,
        "skip_bind": skip_bind,
        "get_frame": do_get_cycle,
        "head": do_head,
        "fieldsection": do_fieldsection,
        "replay": replay,
        "use_methodid": use_methodid,
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
        "methodid_value": int(publish_result.get("methodid") or independent.get("methodid") or EMPTY_METHODID),
        "fieldsection_value": int(
            publish_result.get("fieldsection") or independent.get("fieldsection") or EMPTY_FIELDSECTION
        ),
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
        "methodid": int(trace_body["methodid_value"] or EMPTY_METHODID),
        "fieldsection": int(trace_body["fieldsection_value"] or EMPTY_FIELDSECTION),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_methodid": with_methodid,
        "skip_bind": skip_bind,
        "get_cycle": do_get_cycle,
        "head_cycle": do_head,
        "fieldsection_cycle": do_fieldsection,
        "replay": replay,
        "use_methodid": use_methodid,
    }


def verify_httpsemantics_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed HTTP Semantics trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_httpsemantics_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    methodid = int(trace.get("methodid_value") or independent.get("methodid") or EMPTY_METHODID)
    fieldsection = int(trace.get("fieldsection_value") or independent.get("fieldsection") or EMPTY_FIELDSECTION)
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
        "get_frame": independent.get("get_frame") is True,
        "head": independent.get("head") is True,
        "fieldsection_response": independent.get("fieldsection_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "methodid_bound": independent.get("methodid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "fieldsection_recorded": (
            port > 0
            and methodid == DEFAULT_METHODID
            and fieldsection == DEFAULT_FIELDSECTION
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def httpsemantics_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.httpsemantics_actuation import "
        "builtin_httpsemantics_actuation_proof; r=builtin_httpsemantics_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='httpsemantics_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_httpsemantics_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTPSMANTICS_ACTUATION_ID,
        name="First-class RFC 9110 HTTP Semantics GET/HEAD actuation",
        description=(
            "Missions that require a httpsemantics tool can opt the httpsemantics provider in, "
            "bind a loopback RFC 9110 HTTP Semantics origin, complete a GET "
            "with a non-empty methodid, lockstep a HEAD that carries the "
            "stored fieldsection, independently poll the stored field section "
            "on a later socket, and seal a digest-chained fieldsection. Default "
            "routing stays fail-closed; a missing methodid keeps the hole "
            "falsifiable, and skip-GET/HEAD/FIELDSECTION/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.httpsemantics_actuation:builtin_httpsemantics_actuation_proof",
        proof_command=httpsemantics_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.httpcache-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/httpsemantics_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/structuredfields_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required httpsemantics tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9110 daemon, speaks a "
            "GET then HEAD over HTTP Semantics with a non-empty methodid and "
            "fieldsection, independently polls the stored field section on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9111 HTTP Caching lockstep is proved. "
            "Missing methodids, skip-GET, skip-HEAD, skip-fieldsection, skip-REPLAY, "
            "and a GET aimed without a methodid stay fail-closed. "
            "Later genesis can take RFC 8941 Structured Fields DICT/LIST as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("httpsemantics", "rfc9110", "http", "methodid", "fieldsection", "get", "head", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T110121Z-66f15500",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_httpsemantics_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9110 HTTP Semantics lockstep actuation seals a fieldsection digest."""

    from blackhole_agent.structuredfields_actuation import (
        STRUCTUREDFIELDS_ACTUATION_GOAL,
        STRUCTUREDFIELDS_ACTUATION_ID,
    )
    from blackhole_agent.httpcache_actuation import HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID
    from blackhole_agent.http2_actuation import HTTP2_ACTUATION_GOAL, HTTP2_ACTUATION_ID
    from blackhole_agent.http11_actuation import HTTP11_ACTUATION_GOAL, HTTP11_ACTUATION_ID
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
    checks["denylists_self"] = HTTPSMANTICS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTPSMANTICS_ACTUATION_GOAL) == (
        HTTPSMANTICS_ACTUATION_ID,
    )
    checks["leftover_text_binds_httpsemantics"] = leftover_marker_ids(HTTPSMANTICS_LEFTOVER) == (
        HTTPSMANTICS_ACTUATION_ID,
    )
    neighbor_goals = (
        (HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID, "httpcache"),
        (HTTP2_ACTUATION_GOAL, HTTP2_ACTUATION_ID, "http2"),
        (HTTP11_ACTUATION_GOAL, HTTP11_ACTUATION_ID, "http11"),
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
        (STRUCTUREDFIELDS_ACTUATION_GOAL, STRUCTUREDFIELDS_ACTUATION_ID, "structuredfields"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_httpsemantics"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"httpsemantics_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTPSMANTICS_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTPSMANTICS_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    fields = representation_fields(SENTINEL, DEFAULT_METHODID)
    rebuilt = format_field_section(fields)
    asked = parse_http_request(get_request(SENTINEL, DEFAULT_METHODID))
    headed = parse_http_request(head_request(SENTINEL, DEFAULT_METHODID))
    got = parse_http_response(get_response(SENTINEL, DEFAULT_METHODID))
    head_reply = parse_http_response(head_response(SENTINEL, DEFAULT_METHODID))
    checks["field_section_roundtrip"] = (
        fields[0] == ("content-type", "application/octet-stream")
        and fields[1][0] == "content-length"
        and fields[2] == ("etag", f'"{DEFAULT_METHODID:08x}"')
        and fields[3] == ("x-method-id", f"{DEFAULT_METHODID:08x}")
        and hmac.compare_digest(rebuilt, canonical_field_section(SENTINEL, DEFAULT_METHODID))
        and is_token("x-method-id") is True
        and parse_field_name("Content-Type") == "content-type"
    )
    checks["get_head_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["safe"] is True
        and asked["idempotent"] is True
        and asked["allows_content"] is False
        and headed["method"] == "HEAD"
        and headed["safe"] is True
        and headed["idempotent"] is True
        and headed["allows_content"] is False
        and got["status"] == 200
        and head_reply["status"] == 200
        and got["content_omitted"] is False
        and head_reply["content_omitted"] is True
        and got["content_length_matches_body"] is True
        and head_reply["content_length"] == got["content_length"]
        and field_section_matches(got, head_reply) is True
        and method_is_safe("GET") is True
        and method_is_idempotent("HEAD") is True
        and DEFAULT_FIELDSECTION == request_fieldsection(DEFAULT_METHODID, SENTINEL)
    )
    checks["catalog_names_httpsemantics"] = (
        len(catalog) > 75
        and catalog[75]["id"] == HTTPSMANTICS_ACTUATION_ID
        and catalog[74]["id"] == HTTPCACHE_ACTUATION_ID
        and catalog[75]["source"] == "genesis_bind_httpsemantics"
    )
    checks["catalog_names_structuredfields"] = (
        len(catalog) > 76
        and catalog[76]["id"] == STRUCTUREDFIELDS_ACTUATION_ID
        and catalog[76]["source"] == "genesis_bind_structuredfields"
    )
    family = capability_family(HTTPSMANTICS_ACTUATION_GOAL)
    checks["family_is_httpsemantics"] = "httpsemantic" in family
    checks["family_is_rfc9110"] = "rfc9110" in family
    checks["family_is_methodid"] = "methodid" in family
    checks["family_is_fieldsection"] = "fieldsection" in family
    checks["family_is_not_structuredfields"] = (
        "structuredfield" not in family
        and "rfc8941" not in family
        and "dictid" not in family
        and "sfv" not in family
    )
    checks["family_is_not_httpcache"] = (
        "httpcache" not in family
        and "rfc9111" not in family
        and "cacheid" not in family
        and "freshness" not in family
        and "validator" not in family
    )
    checks["family_is_not_http2"] = (
        "http2" not in family
        and "rfc9113" not in family
        and "settingsid" not in family
        and "hpack" not in family
        and "preface" not in family
    )
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
    checks["family_is_not_http11"] = (
        "http11" not in family
        and "rfc9112" not in family
        and "requestid" not in family
        and "startline" not in family
        and "httpmessage" not in family
    )
    packed = encode_get(identity=SENTINEL, methodid=DEFAULT_METHODID, fieldsection=DEFAULT_FIELDSECTION)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_get"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_methodid"] is True
        and parsed["methodid"] == DEFAULT_METHODID
        and parsed["fieldsection"] == DEFAULT_FIELDSECTION
        and parsed["is_response"] is False
        and parsed["is_head"] is False
        and parsed["type"] == FRAME_GET
        and parsed["first_byte"] == HS_FIRST
    )
    shook = encode_head(
        identity=SENTINEL,
        methodid=DEFAULT_METHODID,
        fieldsection=DEFAULT_FIELDSECTION,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_head"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_get"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["methodid"] == DEFAULT_METHODID
        and answer_parsed["fieldsection"] == DEFAULT_FIELDSECTION
        and answer_parsed["has_fieldsection"] is True
        and answer_parsed["type"] == FRAME_HEAD
        and answer_parsed["first_byte"] == HS_FIRST
    )
    bare = encode_get(identity=SENTINEL, methodid=DEFAULT_METHODID, include_methodid=False)
    checks["missing_methodid_is_unauthenticated"] = parse_message(bare)["has_methodid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    httpsemantics_signature = semantic_signature(HTTPSMANTICS_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(httpsemantics_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_httpsemantics = ToolDescriptor(name="remote_httpsemantics", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_httpsemantics)
    checks["naive_mcp_httpsemantics_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = httpsemantics_tool_descriptor()
    default_httpsemantics = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPSMANTICS_TOOL_PROVIDER),
    )
    checks["default_httpsemantics_provider_is_unsupported"] = (
        default_httpsemantics.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTPSMANTICS_TOOL_PROVIDER}" in default_httpsemantics.reasons
    )
    checks["opted_in_httpsemantics_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_httpsemantics],
        required_tool_names=("local_memory", "httpsemantics"),
    )
    checks["naive_preflight_missing_httpsemantics"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["httpsemantics"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "httpsemantics"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPSMANTICS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "httpsemantics" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="httpsemantics-actuation-") as tmp:
        root = Path(tmp)
        missing = run_httpsemantics_workflow(with_methodid=False, output_dir=root / "missing")
        skip_bind = run_httpsemantics_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_get_cycle = run_httpsemantics_workflow(do_get_cycle=False, output_dir=root / "skip-get-cycle")
        skip_head = run_httpsemantics_workflow(do_head=False, output_dir=root / "skip-head")
        skip_fieldsection = run_httpsemantics_workflow(do_fieldsection=False, output_dir=root / "skip-fieldsection")
        skip_replay = run_httpsemantics_workflow(replay=False, output_dir=root / "skip-replay")
        skip_methodid = run_httpsemantics_workflow(use_methodid=False, output_dir=root / "skip-methodid")
        live = run_httpsemantics_workflow(output_dir=root / "live")
        verify = verify_httpsemantics_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_httpsemantics_trace(clone)
        checks["naive_without_methodid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_methodid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_get_cycle_stays_empty"] = (
            skip_get_cycle["ok"] is False
            and skip_get_cycle["error"] == "get_required"
            and skip_get_cycle["final_status"] == 409
            and skip_get_cycle["payload_exists"] is False
        )
        checks["skip_head_stays_empty"] = (
            skip_head["ok"] is False
            and skip_head["error"] == "head_required"
            and skip_head["final_status"] == 409
            and skip_head["payload_exists"] is False
        )
        checks["skip_fieldsection_stays_empty"] = (
            skip_fieldsection["ok"] is False
            and skip_fieldsection["error"] == "fieldsection_required"
            and skip_fieldsection["final_status"] == 409
            and skip_fieldsection["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_methodid_stays_empty"] = (
            skip_methodid["ok"] is False
            and skip_methodid["error"] == "methodid_required"
            and skip_methodid["final_status"] == 409
            and skip_methodid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_fieldsection"] = (
            int(live.get("methodid") or 0) == DEFAULT_METHODID
            and int(live.get("fieldsection") or 0) == DEFAULT_FIELDSECTION
            and int(live.get("port") or 0) > 0
        )
        checks["token_methodid_encode_head_fieldsection_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_get_cycle["ok"] is False
            and skip_head["ok"] is False
            and skip_fieldsection["ok"] is False
            and skip_replay["ok"] is False
            and skip_methodid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="httpsemantics-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTPSMANTICS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_httpsemantics"] = (
        live_goal == HTTPSMANTICS_ACTUATION_GOAL
        and HTTPSMANTICS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_httpsemantics"
    )

    with tempfile.TemporaryDirectory(prefix="httpsemantics-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTPSMANTICS_LEFTOVER, root)
        register_catalog_proved(root, HTTPSMANTICS_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTPSMANTICS_LEFTOVER, root)
        after = leftover_is_open(HTTPSMANTICS_LEFTOVER, root)
    checks["httpsemantics_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_httpsemantics_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTPSMANTICS_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_httpsemantics_actuation_capability()
    return {
        "ok": ok,
        "action": "httpsemantics_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTPSMANTICS_ACTUATION_GOAL,
        "done_when": HTTPSMANTICS_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
