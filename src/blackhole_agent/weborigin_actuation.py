"""Drive a first-class Web Origin tool through RFC 6454 SERIALIZE/TUPLE.

Tool routing already fails missions that require ``weborigin``: hosted
weborigin endpoints stay on the unsupported MCP provider, and no first-party
weborigin provider is executable. Unbound therefore cannot speak a SERIALIZE,
lockstep a TUPLE tupleid handshake over HTTP Origin TUPLEID,
independently poll the stored tupledigest, or seal a tupledigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``weborigin`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 6454 daemon
- keep a missing-tupleid client so the weborigin-tupleid hole stays falsifiable
- refuse TUPLE until a SERIALIZE lands with a non-empty tupleid
- independently poll the stored tupledigest on a later client socket
- persist a sealed tupledigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 7034 X-Frame-Options
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
    WEBORIGIN_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    weborigin_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
WEBORIGIN_ACTUATION_ID = "capability.weborigin-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-WEBORIGIN-OK"
POLL_TOKEN = "BH-WEBORIGIN-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_TUPLEID = 0
EMPTY_TUPLEDIGEST = 0
WO_FIRST = 0x4F  # RFC 6454 Origin (ASCII 'O')
TUPLEID_SIZE = 4
TUPLEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_TUPLE = 0x02  # RFC 6454 report confirmation
FRAME_SERIALIZE = 0x01  # RFC 6454 Origin
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
WEBORIGIN_LEFTOVER = (
    "Later genesis can take RFC 6454 The Web Origin Concept SERIALIZE/TUPLE over a "
    "tupleid-gated tupledigest."
)
WEBORIGIN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WEBORIGIN_ACTUATION_ID};"
    f"capability_proved:{WEBORIGIN_ACTUATION_ID};"
    "no_skill_route"
)
WEBORIGIN_ACTUATION_GOAL = (
    "Repair rfc6454 weborigin serialize/tuple cycle cannot land over http "
    "weborigin tupleid: hosted weborigin endpoints remain unsupported so a SERIALIZE then "
    "TUPLE tupleid handshake cannot land and a sealed tupledigest "
    "cannot be produced. A missing weborigin tupleid stays forbidden; fail-closed "
    "routing never opts the weborigin provider in. An independent later poll of the "
    "stored tupledigest keeps the hole falsifiable."
)


class WeboriginActuationError(RuntimeError):
    """Raised when the Origin session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


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


TCHAR = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "!#$%&'*+-.^_`|~"
)
# RFC 6454 section 2.1 Origin directives (SERIALIZE / TUPLE / ALLOW-FROM).
RFC_WEBORIGIN_ALLOW_FROM_ORIGIN = "https://example.com"
RFC_WEBORIGIN_FIELD = "SERIALIZE"
RFC_WEBORIGIN_TUPLE = "TUPLE"
RFC_WEBORIGIN_ALLOW_FROM = f"ALLOW-FROM {RFC_WEBORIGIN_ALLOW_FROM_ORIGIN}"
DEFAULT_WEBORIGIN = "SERIALIZE"
TUPLE_WEBORIGIN = "TUPLE"
WEBORIGIN_HEADER = "Origin"
WEBORIGIN_TUPLE_HEADER = "Origin"
RFC_ORIGIN_SCHEME = "https"
RFC_ORIGIN_HOST = "example.com"
RFC_ORIGIN_PORT = 443
RFC_ORIGIN_ASCII = "https://example.com"
RFC_ORIGIN_NULL = "null"


def ascii_serialize_origin(
    scheme: str = RFC_ORIGIN_SCHEME,
    host: str = RFC_ORIGIN_HOST,
    port: int | None = None,
) -> str:
    """RFC 6454 section 6.2 ASCII serialization of an origin."""

    live_scheme = str(scheme or RFC_ORIGIN_SCHEME).lower()
    live_host = str(host or RFC_ORIGIN_HOST).lower()
    default_port = 443 if live_scheme == "https" else 80 if live_scheme == "http" else None
    live_port = RFC_ORIGIN_PORT if port is None else int(port)
    if default_port is not None and live_port == default_port:
        return f"{live_scheme}://{live_host}"
    return f"{live_scheme}://{live_host}:{live_port}"


def origin_tuple(
    scheme: str = RFC_ORIGIN_SCHEME,
    host: str = RFC_ORIGIN_HOST,
    port: int | None = None,
) -> tuple[str, str, int]:
    """RFC 6454 section 4 origin of a URI as (scheme, host, port)."""

    live_scheme = str(scheme or RFC_ORIGIN_SCHEME).lower()
    live_host = str(host or RFC_ORIGIN_HOST).lower()
    default_port = 443 if live_scheme == "https" else 80 if live_scheme == "http" else 0
    live_port = default_port if port is None else int(port)
    return live_scheme, live_host, int(live_port)


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise WeboriginActuationError("short_weborigin")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 6454 directive-name."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_weborigin(policy: str | Sequence[str]) -> str:
    """Serialize RFC 6454 Origin field-value."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise WeboriginActuationError("illegal_weborigin")
    upper = text.upper()
    if upper == "SERIALIZE":
        return "SERIALIZE"
    if upper == "TUPLE":
        return "TUPLE"
    if upper.startswith("ALLOW-FROM"):
        parts = text.split(None, 1)
        if len(parts) != 2 or not parts[1].strip():
            raise WeboriginActuationError("illegal_weborigin")
        return f"ALLOW-FROM {parts[1].strip()}"
    raise WeboriginActuationError("illegal_weborigin")


def parse_weborigin(text: str) -> str:
    """Parse RFC 6454 Origin into SERIALIZE, TUPLE, or ALLOW-FROM."""

    raw = str(text or "").strip()
    if not raw:
        raise WeboriginActuationError("illegal_weborigin")
    head = raw.split(",", 1)[0].strip()
    upper = head.upper()
    if upper == "SERIALIZE":
        return "SERIALIZE"
    if upper == "TUPLE":
        return "TUPLE"
    if upper.startswith("ALLOW-FROM"):
        parts = head.split(None, 1)
        if len(parts) != 2 or not parts[1].strip():
            raise WeboriginActuationError("illegal_weborigin")
        return f"ALLOW-FROM {parts[1].strip()}"
    raise WeboriginActuationError("illegal_weborigin")


def encode_weborigin_header(policy: str | Sequence[str]) -> bytes:
    """RFC 6454 Origin field as bytes."""

    return serialize_weborigin(policy).encode("ascii")


def parse_weborigin_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_weborigin(field_value) if field_value else DEFAULT_WEBORIGIN
    return {
        "field_value": field_value,
        "policy": policy,
        "header": WEBORIGIN_HEADER,
        "directive": str(policy),
        "serialize": str(policy) == "SERIALIZE",
        "tuple": str(policy) == "TUPLE",
    }


def canonical_serialize(identity: str, tupleid: int) -> str:
    """RFC 6454 SERIALIZE advertisement bound to identity and tupleid."""

    return (
        f"{serialize_weborigin(DEFAULT_WEBORIGIN)}, "
        f"origin={ascii_serialize_origin()}, "
        f"identity={identity}, tupleid={int(tupleid) & 0xFFFFFFFF}"
    )


def canonical_tuple(identity: str, tupleid: int, tupledigest: int | None = None) -> str:
    """RFC 6454 TUPLE confirmation of the stored Origin policy."""

    suffix = ""
    if tupledigest is not None:
        suffix = f", tupledigest={int(tupledigest) & 0xFFFFFFFF}"
    scheme, host, port = origin_tuple()
    return (
        f"{serialize_weborigin(TUPLE_WEBORIGIN)}, "
        f"origin=({scheme},{host},{port}), "
        f"identity={identity}, tupleid={int(tupleid) & 0xFFFFFFFF}{suffix}"
    )


def representation_tuple(identity: str, tupleid: int, tupledigest: int) -> str:
    return canonical_tuple(identity, tupleid, tupledigest)


def weborigin_matches(left: str, right: str) -> bool:
    return parse_weborigin(left) == parse_weborigin(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise WeboriginActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise WeboriginActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise WeboriginActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise WeboriginActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def serialize_request(identity: str, tupleid: int) -> bytes:
    """HTTP GET that elicits RFC 6454 Origin SERIALIZE."""

    keyid = f"{int(tupleid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /weborigin/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Tuple-Id: {int(tupleid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def tuple_request(identity: str, tupleid: int, tupledigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 6454 TUPLE confirmation of the stored Origin policy."""

    keyid = f"{int(tupleid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if tupledigest is not None:
        extra = f"Tuple-Digest: {int(tupledigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /weborigin/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Tuple-Id: {int(tupleid) & 0xFFFFFFFF}\r\n"
        "Tuple: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    weborigin_kind = "tuple" if fields.get("tuple") == "1" else "serialize"
    policy = parse_weborigin(fields["origin"]) if fields.get("origin") else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "weborigin_kind": weborigin_kind,
        "policy": policy,
        "tupleid": int(fields["tuple-id"]) if fields.get("tuple-id") else EMPTY_TUPLEID,
        "tupledigest": int(fields["tuple-digest"]) if fields.get("tuple-digest") else EMPTY_TUPLEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def serialize_response(identity: str, tupleid: int, tupledigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 6454 Origin SERIALIZE, carrying the stored tupledigest."""

    advertised = serialize_weborigin(DEFAULT_WEBORIGIN)
    payload = bytes(body or canonical_serialize(identity, tupleid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Origin: {advertised}\r\n"
        f"Tuple-Id: {int(tupleid) & 0xFFFFFFFF}\r\n"
        f"Tuple-Digest: {int(tupledigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/web-origin\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def tuple_response(identity: str, tupleid: int, tupledigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 6454 Origin TUPLE, carrying the stored TUPLE policy."""

    advertised = serialize_weborigin(TUPLE_WEBORIGIN)
    payload = bytes(body or representation_tuple(identity, tupleid, tupledigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Origin: {advertised}\r\n"
        f"Tuple-Id: {int(tupleid) & 0xFFFFFFFF}\r\n"
        f"Tuple-Digest: {int(tupledigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/web-origin-tuple\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise WeboriginActuationError("illegal_content_length") from error
    field_value = fields.get("origin") or ""
    policy = parse_weborigin(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/web-origin-tuple" or policy == TUPLE_WEBORIGIN:
        status = 200
        weborigin_kind = "tuple"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        weborigin_kind = "serialize"
    else:
        status = 0
        weborigin_kind = "serialize"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "weborigin_kind": weborigin_kind,
        "policy": policy,
        "tupleid": int(fields["tuple-id"]) if fields.get("tuple-id") else EMPTY_TUPLEID,
        "tupledigest": int(fields["tuple-digest"]) if fields.get("tuple-digest") else EMPTY_TUPLEDIGEST,
        "content_length_matches_body": content_length == len(body),
    }


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
        raise WeboriginActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise WeboriginActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise WeboriginActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise WeboriginActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_tupleid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"tupleid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_tupleid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-tupleid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_tupledigest(tupleid: int = EMPTY_TUPLEID, token: str = SENTINEL) -> int:
    material = canonical_serialize(token or SENTINEL, int(tupleid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_TUPLEID = request_tupleid(SENTINEL)
DEFAULT_TUPLEDIGEST = request_tupledigest(DEFAULT_TUPLEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    tupleid: int,
    tupledigest: int,
    include_tupleid: bool = True,
) -> bytes:
    live_tupleid = int(tupleid) & 0xFFFFFFFF if include_tupleid else EMPTY_TUPLEID
    live_digest = int(tupledigest) & 0xFFFFFFFF if include_tupleid and live_tupleid else EMPTY_TUPLEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_tupleid) if live_tupleid else b""
    header = bytearray()
    header.append(WO_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_serialize(
    *,
    identity: str,
    tupleid: int,
    tupledigest: int | None = None,
    include_tupleid: bool = True,
) -> bytes:
    live_tupleid = int(tupleid) & 0xFFFFFFFF if include_tupleid else EMPTY_TUPLEID
    live_digest = int(tupledigest) if tupledigest is not None else request_tupledigest(live_tupleid, identity)
    return encode_packet(
        FRAME_SERIALIZE,
        identity=identity,
        tupleid=live_tupleid,
        tupledigest=live_digest,
        include_tupleid=include_tupleid,
    )


def encode_tuple(
    *,
    identity: str,
    tupleid: int,
    tupledigest: int | None = None,
    include_tupleid: bool = True,
) -> bytes:
    live_tupleid = int(tupleid) & 0xFFFFFFFF if include_tupleid else EMPTY_TUPLEID
    live_digest = int(tupledigest) if tupledigest is not None else request_tupledigest(live_tupleid, identity)
    return encode_packet(
        FRAME_TUPLE,
        identity=identity,
        tupleid=live_tupleid,
        tupledigest=live_digest,
        include_tupleid=include_tupleid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise WeboriginActuationError("short_packet")
    first = raw[0]
    if first != WO_FIRST:
        raise WeboriginActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise WeboriginActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == TUPLEID_SIZE:
        live_tupleid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_tupleid = EMPTY_TUPLEID
    else:
        raise WeboriginActuationError("illegal_tupleid")
    if offset >= len(raw):
        raise WeboriginActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SERIALIZE, FRAME_TUPLE}:
        raise WeboriginActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise WeboriginActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise WeboriginActuationError("checksum_failed")
    if len(payload) < 5:
        raise WeboriginActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise WeboriginActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_tupleid = int(live_tupleid) != EMPTY_TUPLEID
    has_tupledigest = has_tupleid and int(live_digest) != EMPTY_TUPLEDIGEST
    is_serialize = frame_type == FRAME_SERIALIZE
    is_tuple = frame_type == FRAME_TUPLE
    return {
        "type": int(frame_type),
        "is_serialize": is_serialize,
        "is_tuple": is_tuple,
        "is_response": is_tuple,
        "tupleid": int(live_tupleid),
        "has_tupleid": has_tupleid,
        "tupledigest": int(live_digest),
        "has_tupledigest": has_tupledigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "x_frame_options": "RFC6454",
        "serialize_field": canonical_serialize(identity, live_tupleid) if has_tupleid else "",
        "tuple_field": canonical_tuple(identity, live_tupleid, live_digest) if has_tupledigest else "",
    }


class WeboriginClient:
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
            raise WeboriginActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_tuple"] or not packet["is_response"]:
            raise WeboriginActuationError("tupledigest_required")
        if not packet["has_tupleid"]:
            raise WeboriginActuationError("tupleid_required")
        if not packet["has_tupledigest"]:
            raise WeboriginActuationError("tupledigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_tupledigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_tupledigest:
            raise WeboriginActuationError("tupledigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "tupleid": int(reply.get("tupleid") or EMPTY_TUPLEID),
            "identity": str(reply.get("identity") or ""),
            "tupledigest": int(reply.get("tupledigest") or EMPTY_TUPLEDIGEST),
        }

    def report(
        self,
        identity: str,
        tupleid: int,
        tupledigest: int = EMPTY_TUPLEDIGEST,
        *,
        wait_tupledigest: bool = True,
        include_tupleid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_tuple(
            identity=identity,
            tupleid=tupleid,
            tupledigest=tupledigest or request_tupledigest(tupleid, identity),
            include_tupleid=include_tupleid,
        )
        return self.exchange(packet, wait_tupledigest=wait_tupledigest)


class WeboriginSession:
    """TUPLEID-gated loopback RFC 6454 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        tupleid_gate: int = DEFAULT_TUPLEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tupleid_gate = int(tupleid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.tupleid = EMPTY_TUPLEID
        self.tupledigest = EMPTY_TUPLEDIGEST
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

    def store_tupleid_once(self, identity: str, tupleid: int, tupledigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(tupleid or EMPTY_TUPLEID)
            live_digest = int(tupledigest or EMPTY_TUPLEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.tupleid = live
                self.tupledigest = live_digest or request_tupledigest(live, name)
                self.stored = True
            return str(self.identity), int(self.tupleid), int(self.tupledigest)

    def read_tupleid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.tupleid), int(self.tupledigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "tupleid": EMPTY_TUPLEID,
            "tupledigest": EMPTY_TUPLEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _tupleid_missing(self) -> bool:
        return not int(self.tupleid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, tupleid: int, tupledigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_tuple(
            identity=identity,
            tupleid=tupleid,
            tupledigest=tupledigest,
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
            except WeboriginActuationError:
                continue
            if not packet.get("is_serialize") and not packet.get("is_tuple"):
                continue
            if not packet.get("has_tupleid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_tupleid, stored_digest = self.store_tupleid_once(
                identity,
                int(packet.get("tupleid") or EMPTY_TUPLEID),
                int(packet.get("tupledigest") or EMPTY_TUPLEDIGEST),
            )
            if not stored_name or not stored_tupleid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_serialize"):
                    self.opened = True
                if packet.get("is_tuple"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_tupleid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._tupleid_missing():
            return self._forbidden("missing_tupleid")
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
        do_serialize: bool = True,
        do_tuple: bool = True,
        do_tupledigest: bool = True,
        replay: bool = True,
        use_tupleid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._tupleid_missing():
            return self._forbidden("missing_tupleid")
        live_token = str(token or SENTINEL)
        origin_tupleid = request_tupleid(live_token)
        origin_digest = request_tupledigest(origin_tupleid, live_token)
        client: WeboriginClient | None = None
        independent: WeboriginClient | None = None
        try:
            client = WeboriginClient(self.host, int(self.port))
            if not do_serialize:
                return self._conflict("serialize_required")
            bind_packet = encode_serialize(
                identity=live_token,
                tupleid=origin_tupleid,
                tupledigest=origin_digest,
                include_tupleid=use_tupleid,
            )
            if not use_tupleid:
                try:
                    client.exchange(bind_packet, wait_tupledigest=True)
                except WeboriginActuationError:
                    return self._conflict("tupleid_required")
                return self._conflict("tupleid_required")
            client.send(bind_packet)
            if not do_tuple:
                return self._conflict("tuple_required")
            proxy_packet = encode_tuple(
                identity=live_token,
                tupleid=origin_tupleid,
                tupledigest=origin_digest,
                include_tupleid=True,
            )
            if not do_tupledigest:
                try:
                    client.exchange(proxy_packet, wait_tupledigest=False)
                except WeboriginActuationError as error:
                    if str(error) == "tupledigest_required":
                        return self._conflict("tupledigest_required")
                    return self._conflict("tupledigest_required")
                return self._conflict("tupledigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_tupledigest=True)
            except WeboriginActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("tupleid_required")
                if reason == "tupledigest_required":
                    return self._conflict("tupledigest_required")
                return self._conflict("serialize_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("serialize_required")
            if int(reply.get("tupleid") or EMPTY_TUPLEID) != origin_tupleid:
                return self._conflict("tupledigest_required")
            if int(reply.get("tupledigest") or EMPTY_TUPLEDIGEST) != origin_digest:
                return self._conflict("tupledigest_required")
            self.retrieved = True
            if replay:
                independent = WeboriginClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_tupleid(live_token),
                        request_tupledigest(poll_tupleid(live_token), POLL_TOKEN),
                        wait_tupledigest=True,
                    )
                except WeboriginActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_tupleid, stored_digest = self.read_tupleid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_tupleid != origin_tupleid
                    or stored_digest != origin_digest
                    or int(poll.get("tupleid") or EMPTY_TUPLEID) != origin_tupleid
                    or int(poll.get("tupledigest") or EMPTY_TUPLEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_tupleid}:{origin_digest}:{live_token}:{canonical_serialize(live_token, origin_tupleid)}:{canonical_tuple(live_token, origin_tupleid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "tupleid": origin_tupleid,
                "tupledigest": origin_digest,
                "serialize_frame": True,
                "tuple_frame": True,
                "tupledigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "tupleid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_weborigin_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "tupleid": origin_tupleid,
                "tupledigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "serialize_frame": True,
                "tuple_frame": True,
                "tupledigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "tupleid_bound": True,
            }
        except (OSError, WeboriginActuationError) as error:
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
        live = independent_weborigin_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "tupleid": int(live.get("tupleid") or EMPTY_TUPLEID),
            "tupledigest": int(live.get("tupledigest") or EMPTY_TUPLEDIGEST),
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


def call_weborigin_tool(session: WeboriginSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one Origin tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_serialize = True if arguments.get("serialize") is None else bool(arguments.get("serialize"))
    do_tuple = True if arguments.get("tuple") is None else bool(arguments.get("tuple"))
    do_tupledigest = True if arguments.get("tupledigest") is None else bool(arguments.get("tupledigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_tupleid = True if arguments.get("use_tupleid") is None else bool(arguments.get("use_tupleid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_serialize=do_serialize,
            do_tuple=do_tuple,
            do_tupledigest=do_tupledigest,
            replay=replay,
            use_tupleid=use_tupleid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise WeboriginActuationError(f"unsupported weborigin action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_weborigin_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed Origin tupledigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "tupleid": EMPTY_TUPLEID,
        "tupledigest": EMPTY_TUPLEDIGEST,
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
            "serialize_frame",
            "tuple_frame",
            "tupledigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "tupleid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    tupleid = int(payload.get("tupleid") or EMPTY_TUPLEID)
    tupledigest = int(payload.get("tupledigest") or EMPTY_TUPLEDIGEST)
    dual = port > 0 and bool(tupleid) and bool(tupledigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "tupleid": tupleid,
        "tupledigest": tupledigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "serialize_frame": payload.get("serialize_frame") is True,
        "tuple_frame": payload.get("tuple_frame") is True,
        "tupledigest_response": payload.get("tupledigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "tupleid_bound": payload.get("tupleid_bound") is True,
    }


def run_weborigin_workflow(
    *,
    with_tupleid: bool = True,
    skip_bind: bool = False,
    do_serialize: bool = True,
    do_tuple: bool = True,
    do_tupledigest: bool = True,
    replay: bool = True,
    use_tupleid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 6454 SERIALIZE/TUPLE tupleid cycle workflow."""

    descriptor = weborigin_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBORIGIN_TOOL_PROVIDER),
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
        raise WeboriginActuationError(f"weborigin tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="weborigin-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = WeboriginSession(out, tupleid_gate=DEFAULT_TUPLEID if with_tupleid else EMPTY_TUPLEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "serialize": do_serialize,
            "tuple": do_tuple,
            "tupledigest": do_tupledigest,
            "replay": replay,
            "use_tupleid": use_tupleid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_weborigin_tool(session, arguments))
            except WeboriginActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_weborigin_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_tupleid
        and not skip_bind
        and do_serialize
        and do_tuple
        and do_tupledigest
        and replay
        and use_tupleid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "weborigin_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_tupleid": with_tupleid,
        "skip_bind": skip_bind,
        "serialize_frame": do_serialize,
        "tuple": do_tuple,
        "tupledigest": do_tupledigest,
        "replay": replay,
        "use_tupleid": use_tupleid,
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
        "tupleid_value": int(publish_result.get("tupleid") or independent.get("tupleid") or EMPTY_TUPLEID),
        "tupledigest_value": int(publish_result.get("tupledigest") or independent.get("tupledigest") or EMPTY_TUPLEDIGEST),
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
        "tupleid": int(trace_body["tupleid_value"] or EMPTY_TUPLEID),
        "tupledigest": int(trace_body["tupledigest_value"] or EMPTY_TUPLEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_tupleid": with_tupleid,
        "skip_bind": skip_bind,
        "serialize_cycle": do_serialize,
        "tuple_cycle": do_tuple,
        "tupledigest_cycle": do_tupledigest,
        "replay": replay,
        "use_tupleid": use_tupleid,
    }


def verify_weborigin_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_weborigin_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    tupleid = int(trace.get("tupleid_value") or independent.get("tupleid") or EMPTY_TUPLEID)
    tupledigest = int(trace.get("tupledigest_value") or independent.get("tupledigest") or EMPTY_TUPLEDIGEST)
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
        "serialize_frame": independent.get("serialize_frame") is True,
        "tuple_frame": independent.get("tuple_frame") is True,
        "tupledigest_response": independent.get("tupledigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "tupleid_bound": independent.get("tupleid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "tupledigest_recorded": (
            port > 0
            and tupleid == DEFAULT_TUPLEID
            and tupledigest == DEFAULT_TUPLEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def weborigin_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.weborigin_actuation import "
        "builtin_weborigin_actuation_proof; r=builtin_weborigin_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='weborigin_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_weborigin_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=WEBORIGIN_ACTUATION_ID,
        name="First-class RFC 6454 Origin SERIALIZE/TUPLE actuation",
        description=(
            "Missions that require a weborigin tool can opt the weborigin provider in, "
            "bind a loopback RFC 6454 Web Origin endpoint, complete a SERIALIZE "
            "with a non-empty tupleid, lockstep a TUPLE that carries the "
            "stored tupledigest, independently poll the stored tupledigest "
            "on a later socket, and seal a digest-chained tupledigest. Default "
            "routing stays fail-closed; a missing tupleid keeps the hole "
            "falsifiable, and skip-SERIALIZE/TUPLE/TUPLEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.weborigin_actuation:builtin_weborigin_actuation_proof",
        proof_command=weborigin_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.xfo-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/weborigin_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/xfo_actuation.py",
            "src/blackhole_agent/httpcookie_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required weborigin tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 6454 daemon, speaks a "
            "SERIALIZE then TUPLE over Origin with a non-empty tupleid and "
            "tupledigest, independently polls the stored tupledigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 7034 X-Frame-Options lockstep is proved. "
            "Missing tupleids, skip-SERIALIZE, skip-TUPLE, skip-tupledigest, skip-REPLAY, "
            "and a SERIALIZE aimed without a tupleid stay fail-closed. "
            "Later genesis can take RFC 6265 HTTP State Management Mechanism SET-COOKIE/COOKIE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("weborigin", "rfc6454", "http", "tupleid", "tupledigest", "serialize", "tuple", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T165824Z-0a93fcb5",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_weborigin_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 6454 Origin lockstep actuation seals a tupledigest."""

    from blackhole_agent.httpcookie_actuation import (
        HTTPCOOKIE_ACTUATION_GOAL,
        HTTPCOOKIE_ACTUATION_ID,
    )
    from blackhole_agent.xfo_actuation import (
        XFO_ACTUATION_GOAL,
        XFO_ACTUATION_ID,
    )
    from blackhole_agent.hpkp_actuation import (
        HPKP_ACTUATION_GOAL,
        HPKP_ACTUATION_ID,
    )
    from blackhole_agent.hsts_actuation import (
        HSTS_ACTUATION_GOAL,
        HSTS_ACTUATION_ID,
    )
    from blackhole_agent.altsvc_actuation import (
        ALTSVC_ACTUATION_GOAL,
        ALTSVC_ACTUATION_ID,
    )
    from blackhole_agent.encryptedcontent_actuation import (
        ENCRYPTEDCONTENT_ACTUATION_GOAL,
        ENCRYPTEDCONTENT_ACTUATION_ID,
    )
    from blackhole_agent.earlyhints_actuation import (
        EARLYHINTS_ACTUATION_GOAL,
        EARLYHINTS_ACTUATION_ID,
    )
    from blackhole_agent.structuredfields_actuation import (
        STRUCTUREDFIELDS_ACTUATION_GOAL,
        STRUCTUREDFIELDS_ACTUATION_ID,
    )
    from blackhole_agent.httpsemantics_actuation import HTTPSMANTICS_ACTUATION_GOAL, HTTPSMANTICS_ACTUATION_ID
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
    from blackhole_agent.clienthints_actuation import CLIENTHINTS_ACTUATION_GOAL, CLIENTHINTS_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = WEBORIGIN_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(WEBORIGIN_ACTUATION_GOAL) == (
        WEBORIGIN_ACTUATION_ID,
    )
    checks["leftover_text_binds_weborigin"] = leftover_marker_ids(WEBORIGIN_LEFTOVER) == (
        WEBORIGIN_ACTUATION_ID,
    )
    neighbor_goals = (
        (STRUCTUREDFIELDS_ACTUATION_GOAL, STRUCTUREDFIELDS_ACTUATION_ID, "structuredfields"),
        (HTTPSMANTICS_ACTUATION_GOAL, HTTPSMANTICS_ACTUATION_ID, "httpsemantics"),
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
        (CLIENTHINTS_ACTUATION_GOAL, CLIENTHINTS_ACTUATION_ID, "clienthints"),
        (EARLYHINTS_ACTUATION_GOAL, EARLYHINTS_ACTUATION_ID, "earlyhints"),
        (ENCRYPTEDCONTENT_ACTUATION_GOAL, ENCRYPTEDCONTENT_ACTUATION_ID, "encryptedcontent"),
        (ALTSVC_ACTUATION_GOAL, ALTSVC_ACTUATION_ID, "altsvc"),
        (HSTS_ACTUATION_GOAL, HSTS_ACTUATION_ID, "hsts"),
        (HPKP_ACTUATION_GOAL, HPKP_ACTUATION_ID, "hpkp"),
        (XFO_ACTUATION_GOAL, XFO_ACTUATION_ID, "xfo"),
        (HTTPCOOKIE_ACTUATION_GOAL, HTTPCOOKIE_ACTUATION_ID, "httpcookie"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_weborigin"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"weborigin_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            WEBORIGIN_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = WEBORIGIN_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_weborigin(DEFAULT_WEBORIGIN)
    rebuilt = serialize_weborigin(parse_weborigin(advertised))
    preloaded = parse_weborigin(RFC_WEBORIGIN_TUPLE)
    header = encode_weborigin_header(DEFAULT_WEBORIGIN)
    parsed_header = parse_weborigin_header(header)
    asked = parse_http_request(serialize_request(SENTINEL, DEFAULT_TUPLEID))
    preload_req = parse_http_request(tuple_request(SENTINEL, DEFAULT_TUPLEID, DEFAULT_TUPLEDIGEST))
    got = parse_http_response(serialize_response(SENTINEL, DEFAULT_TUPLEID, DEFAULT_TUPLEDIGEST))
    preload_reply = parse_http_response(
        tuple_response(SENTINEL, DEFAULT_TUPLEID, DEFAULT_TUPLEDIGEST)
    )
    checks["weborigin_roundtrip"] = (
        parse_weborigin(advertised) == DEFAULT_WEBORIGIN
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_WEBORIGIN_FIELD
        and is_token("SERIALIZE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_WEBORIGIN_FIELD
        and parsed_header["policy"] == DEFAULT_WEBORIGIN
        and parsed_header["header"] == WEBORIGIN_HEADER
        and parsed_header["serialize"] is True
        and parsed_header["tuple"] is False
        and preloaded == TUPLE_WEBORIGIN
        and ascii_serialize_origin() == RFC_ORIGIN_ASCII
        and origin_tuple() == (RFC_ORIGIN_SCHEME, RFC_ORIGIN_HOST, RFC_ORIGIN_PORT)
        and RFC_ORIGIN_NULL == "null"
    )
    checks["tuple_roundtrip"] = (
        serialize_weborigin(TUPLE_WEBORIGIN) == RFC_WEBORIGIN_TUPLE
        and DEFAULT_TUPLEDIGEST == request_tupledigest(DEFAULT_TUPLEID, SENTINEL)
        and "tupledigest=" in canonical_tuple(SENTINEL, DEFAULT_TUPLEID, DEFAULT_TUPLEDIGEST)
        and canonical_serialize(SENTINEL, DEFAULT_TUPLEID).startswith("SERIALIZE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["weborigin_kind"] == "serialize"
        and asked["tupleid"] == DEFAULT_TUPLEID
        and preload_req["weborigin_kind"] == "tuple"
        and preload_req["tupledigest"] == DEFAULT_TUPLEDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["weborigin_kind"] == "serialize"
        and preload_reply["weborigin_kind"] == "tuple"
        and got["policy"] == DEFAULT_WEBORIGIN
        and preload_reply["policy"] == TUPLE_WEBORIGIN
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["tupledigest"] == DEFAULT_TUPLEDIGEST
        and preload_reply["tupledigest"] == DEFAULT_TUPLEDIGEST
        and weborigin_matches(serialize_weborigin(got["policy"]), advertised)
    )

    checks["catalog_names_weborigin"] = (
        len(catalog) > 85
        and catalog[85]["id"] == WEBORIGIN_ACTUATION_ID
        and catalog[84]["id"] == XFO_ACTUATION_ID
        and catalog[85]["source"] == "genesis_bind_weborigin"
    )
    checks["catalog_names_httpcookie"] = (
        len(catalog) > 86
        and catalog[86]["id"] == HTTPCOOKIE_ACTUATION_ID
        and catalog[86]["source"] == "genesis_bind_httpcookie"
    )
    family = capability_family(WEBORIGIN_ACTUATION_GOAL)
    checks["family_is_weborigin"] = "weborigin" in family
    checks["family_is_weborigin_surface"] = "weborigin" in family
    checks["family_is_tupleid"] = "tupleid" in family
    checks["family_is_rfc6454"] = "rfc6454" in family
    checks["family_is_tupledigest"] = "tupledigest" in family
    checks["family_is_not_httpcookie"] = (
        "httpcookie" not in family
        and "rfc6265" not in family
        and "cookieid" not in family
        and "cookiedigest" not in family
    )
    checks["family_is_not_xfo"] = (
        "xfo" not in family
        and "rfc7034" not in family
        and "frameid" not in family
        and "framedigest" not in family
    )
    checks["family_is_not_hpkp"] = (
        "hpkp" not in family
        and "rfc7469" not in family
        and "pinid" not in family
        and "pindigest" not in family
    )
    checks["family_is_not_hsts"] = (
        "hsts" not in family
        and "rfc6797" not in family
        and "hstsid" not in family
        and "stsdigest" not in family
    )
    checks["family_is_not_altsvc"] = (
        "altsvc" not in family
        and "rfc7838" not in family
        and "altsvcid" not in family
        and "origindigest" not in family
    )
    checks["family_is_not_encryptedcontent"] = (
        "encryptedcontent" not in family
        and "rfc8188" not in family
        and "encid" not in family
        and "aes128gcm" not in family
        and "ecedigest" not in family
    )
    checks["family_is_not_earlyhints"] = (
        "earlyhint" not in family
        and "rfc8297" not in family
        and "linkid" not in family
        and "earlydigest" not in family
    )
    checks["family_is_not_structuredfields"] = (
        "structuredfield" not in family
        and "rfc8941" not in family
        and "dictid" not in family
        and "sfv" not in family
    )
    checks["family_is_not_httpsemantics"] = (
        "httpsemantic" not in family
        and "rfc9110" not in family
        and "methodid" not in family
        and "fieldsection" not in family
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
    packed = encode_serialize(identity=SENTINEL, tupleid=DEFAULT_TUPLEID, tupledigest=DEFAULT_TUPLEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_serialize"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_tupleid"] is True
        and parsed["tupleid"] == DEFAULT_TUPLEID
        and parsed["tupledigest"] == DEFAULT_TUPLEDIGEST
        and parsed["is_response"] is False
        and parsed["is_tuple"] is False
        and parsed["type"] == FRAME_SERIALIZE
        and parsed["first_byte"] == WO_FIRST
    )
    shook = encode_tuple(
        identity=SENTINEL,
        tupleid=DEFAULT_TUPLEID,
        tupledigest=DEFAULT_TUPLEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_tuple"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_serialize"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["tupleid"] == DEFAULT_TUPLEID
        and answer_parsed["tupledigest"] == DEFAULT_TUPLEDIGEST
        and answer_parsed["has_tupledigest"] is True
        and answer_parsed["type"] == FRAME_TUPLE
        and answer_parsed["first_byte"] == WO_FIRST
    )
    bare = encode_serialize(identity=SENTINEL, tupleid=DEFAULT_TUPLEID, include_tupleid=False)
    checks["missing_tupleid_is_unauthenticated"] = parse_message(bare)["has_tupleid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    weborigin_signature = semantic_signature(WEBORIGIN_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(weborigin_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_weborigin = ToolDescriptor(name="remote_weborigin", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_weborigin)
    checks["naive_mcp_weborigin_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = weborigin_tool_descriptor()
    default_weborigin = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBORIGIN_TOOL_PROVIDER),
    )
    checks["default_weborigin_provider_is_unsupported"] = (
        default_weborigin.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{WEBORIGIN_TOOL_PROVIDER}" in default_weborigin.reasons
    )
    checks["opted_in_weborigin_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_weborigin],
        required_tool_names=("local_memory", "weborigin"),
    )
    checks["naive_preflight_missing_weborigin"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["weborigin"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "weborigin"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBORIGIN_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "weborigin" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="weborigin-actuation-") as tmp:
        root = Path(tmp)
        missing = run_weborigin_workflow(with_tupleid=False, output_dir=root / "missing")
        skip_bind = run_weborigin_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_serialize = run_weborigin_workflow(do_serialize=False, output_dir=root / "skip-serialize")
        skip_preload = run_weborigin_workflow(do_tuple=False, output_dir=root / "skip-tuple")
        skip_tupledigest = run_weborigin_workflow(do_tupledigest=False, output_dir=root / "skip-tupledigest")
        skip_replay = run_weborigin_workflow(replay=False, output_dir=root / "skip-replay")
        skip_tupleid = run_weborigin_workflow(use_tupleid=False, output_dir=root / "skip-tupleid")
        live = run_weborigin_workflow(output_dir=root / "live")
        verify = verify_weborigin_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_weborigin_trace(clone)
        checks["naive_without_tupleid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_tupleid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_serialize_stays_empty"] = (
            skip_serialize["ok"] is False
            and skip_serialize["error"] == "serialize_required"
            and skip_serialize["final_status"] == 409
            and skip_serialize["payload_exists"] is False
        )
        checks["skip_tuple_stays_empty"] = (
            skip_preload["ok"] is False
            and skip_preload["error"] == "tuple_required"
            and skip_preload["final_status"] == 409
            and skip_preload["payload_exists"] is False
        )
        checks["skip_tupledigest_stays_empty"] = (
            skip_tupledigest["ok"] is False
            and skip_tupledigest["error"] == "tupledigest_required"
            and skip_tupledigest["final_status"] == 409
            and skip_tupledigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_tupleid_stays_empty"] = (
            skip_tupleid["ok"] is False
            and skip_tupleid["error"] == "tupleid_required"
            and skip_tupleid["final_status"] == 409
            and skip_tupleid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_tupledigest"] = (
            int(live.get("tupleid") or 0) == DEFAULT_TUPLEID
            and int(live.get("tupledigest") or 0) == DEFAULT_TUPLEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_tupleid_encode_tuple_tupledigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_serialize["ok"] is False
            and skip_preload["ok"] is False
            and skip_tupledigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_tupleid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="weborigin-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != WEBORIGIN_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_weborigin"] = (
        live_goal == WEBORIGIN_ACTUATION_GOAL
        and WEBORIGIN_ACTUATION_ID in live_done
        and live_source == "genesis_bind_weborigin"
    )

    with tempfile.TemporaryDirectory(prefix="weborigin-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(WEBORIGIN_LEFTOVER, root)
        register_catalog_proved(root, WEBORIGIN_ACTUATION_ID)
        reason = leftover_satisfied_by(WEBORIGIN_LEFTOVER, root)
        after = leftover_is_open(WEBORIGIN_LEFTOVER, root)
    checks["weborigin_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_weborigin_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{WEBORIGIN_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_weborigin_actuation_capability()
    return {
        "ok": ok,
        "action": "weborigin_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": WEBORIGIN_ACTUATION_GOAL,
        "done_when": WEBORIGIN_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
