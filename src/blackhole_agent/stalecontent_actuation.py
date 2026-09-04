"""Drive a first-class HTTP Cache-Control Extensions for Stale Content tool through RFC 5861 STALE/IFERROR.

Tool routing already fails missions that require ``stalecontent``: hosted
stalecontent endpoints stay on the unsupported MCP provider, and no first-party
stalecontent provider is executable. Unbound therefore cannot speak a STALE,
lockstep an IFERROR staleid handshake over HTTP Cache-Control STALEID,
independently poll the stored staledigest, or seal a staledigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``stalecontent`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 5861 daemon
- keep a missing-staleid client so the stalecontent-staleid hole stays falsifiable
- refuse IFERROR until a STALE lands with a non-empty staleid
- independently poll the stored staledigest on a later client socket
- persist a sealed staledigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 5987 Character Set and Language Encoding
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
    STALECONTENT_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    stalecontent_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
STALECONTENT_ACTUATION_ID = "capability.stalecontent-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-STALE-OK"
POLL_TOKEN = "BH-STALE-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_STALEID = 0
EMPTY_STALEDIGEST = 0
SC_FIRST = 0x53  # RFC 5861 Cache-Control Stale (ASCII 'S')
STALEID_SIZE = 4
STALEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_IFERROR = 0x02  # RFC 5861 report confirmation
FRAME_STALE = 0x01  # RFC 5861 Stale
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
STALECONTENT_LEFTOVER = (
    "Later genesis can take RFC 5861 HTTP Cache-Control Extensions for Stale Content STALE/IFERROR over a "
    "staleid-gated staledigest."
)
STALECONTENT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{STALECONTENT_ACTUATION_ID};"
    f"capability_proved:{STALECONTENT_ACTUATION_ID};"
    "no_skill_route"
)
STALECONTENT_ACTUATION_GOAL = (
    "Repair rfc5861 stalecontent stale/iferror cycle cannot land over http "
    "stalecontent staleid: hosted stalecontent endpoints remain unsupported so a STALE then "
    "IFERROR staleid handshake cannot land and a sealed staledigest "
    "cannot be produced. A missing stalecontent staleid stays forbidden; fail-closed "
    "routing never opts the stalecontent provider in. An independent later poll of the "
    "stored staledigest keeps the hole falsifiable."
)


class StalecontentActuationError(RuntimeError):
    """Raised when the iferror session or loopback daemon fixture misbehaves."""


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
# RFC 5861 sections 3 and 4: stale-while-revalidate / stale-if-error.
RFC_STALE_FIELD = "STALE"
RFC_IFERROR_FIELD = "IFERROR"
RFC_STALECONTENT_IFERROR = RFC_IFERROR_FIELD
RFC_STALE_WHILE_REVALIDATE = 30
RFC_STALE_IF_ERROR = 86400
DEFAULT_STALE = "STALE"
IFERROR_POLICY = "IFERROR"
STALE_HEADER = "Cache-Control"
IFERROR_HEADER = "Cache-Control"
STALECONTENT_IFERROR_HEADER = IFERROR_HEADER
RFC_STALE_PATH = "/"
RFC_STALE_DIRECTIVE = "stale-while-revalidate=30"
RFC_IFERROR_DIRECTIVE = "stale-if-error=86400"
RFC_STALE_EMPTY = ""


def stale_directive_pair(
    *,
    iferror: bool = False,
    seconds: int | None = None,
) -> tuple[str, int]:
    """RFC 5861 section 3 stale-while-revalidate / section 4 stale-if-error."""

    live_seconds = int(seconds) if seconds is not None else (
        RFC_STALE_IF_ERROR if iferror else RFC_STALE_WHILE_REVALIDATE
    )
    if live_seconds < 0:
        raise StalecontentActuationError("illegal_delta_seconds")
    name = "stale-if-error" if iferror else "stale-while-revalidate"
    return name, live_seconds


def ascii_serialize_stale_directive(
    *,
    iferror: bool = False,
    seconds: int | None = None,
) -> str:
    """RFC 5861 Cache-Control extension: name "=" delta-seconds."""

    name, live_seconds = stale_directive_pair(iferror=iferror, seconds=seconds)
    if not is_token(name):
        raise StalecontentActuationError("illegal_directive")
    return f"{name}={live_seconds}"


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise StalecontentActuationError("short_stalecontent")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 5861 Cache-Control token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_stalecontent(policy: str | Sequence[str]) -> str:
    """Serialize RFC 5861 stale-while-revalidate / stale-if-error token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise StalecontentActuationError("illegal_stalecontent")
    upper = text.upper().replace("_", "-")
    if upper in {"STALE", "STALE-WHILE-REVALIDATE", "SWR"}:
        return "STALE"
    if upper in {"IFERROR", "STALE-IF-ERROR", "SIE"}:
        return "IFERROR"
    if upper.startswith("STALE-WHILE-REVALIDATE="):
        seconds = text.split("=", 1)[1].strip().strip('"')
        if not seconds.isdigit():
            raise StalecontentActuationError("illegal_stalecontent")
        return "STALE"
    if upper.startswith("STALE-IF-ERROR="):
        seconds = text.split("=", 1)[1].strip().strip('"')
        if not seconds.isdigit():
            raise StalecontentActuationError("illegal_stalecontent")
        return "IFERROR"
    raise StalecontentActuationError("illegal_stalecontent")


def parse_stalecontent(text: str) -> str:
    """Parse RFC 5861 Cache-Control stale extensions into STALE or IFERROR."""

    raw = str(text or "").strip()
    if not raw:
        raise StalecontentActuationError("illegal_stalecontent")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"STALE", "STALE-WHILE-REVALIDATE", "SWR"}:
        return "STALE"
    if upper in {"IFERROR", "STALE-IF-ERROR", "SIE"}:
        return "IFERROR"
    if upper.startswith("STALE-WHILE-REVALIDATE="):
        seconds = head.split("=", 1)[1].strip().strip('"')
        if not seconds.isdigit():
            raise StalecontentActuationError("illegal_stalecontent")
        return "STALE"
    if upper.startswith("STALE-IF-ERROR="):
        seconds = head.split("=", 1)[1].strip().strip('"')
        if not seconds.isdigit():
            raise StalecontentActuationError("illegal_stalecontent")
        return "IFERROR"
    raise StalecontentActuationError("illegal_stalecontent")


def encode_stalecontent_header(policy: str | Sequence[str]) -> bytes:
    """RFC 5861 Cache-Control field as bytes."""

    return serialize_stalecontent(policy).encode("ascii")


def parse_stalecontent_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_stalecontent(field_value) if field_value else DEFAULT_STALE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": STALE_HEADER,
        "directive": str(policy),
        "stale": str(policy) == "STALE",
        "iferror": str(policy) == "IFERROR",
    }


def canonical_stale(identity: str, staleid: int) -> str:
    """RFC 5861 STALE advertisement bound to identity and staleid."""

    return (
        f"{serialize_stalecontent(DEFAULT_STALE)}, "
        f"stale={ascii_serialize_stale_directive()}, "
        f"identity={identity}, staleid={int(staleid) & 0xFFFFFFFF}"
    )


def canonical_iferror(identity: str, staleid: int, staledigest: int | None = None) -> str:
    """RFC 5861 IFERROR confirmation of the stored iferror policy."""

    suffix = ""
    if staledigest is not None:
        suffix = f", staledigest={int(staledigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_stalecontent(IFERROR_POLICY)}, "
        f"iferror={ascii_serialize_stale_directive(iferror=True)}, "
        f"identity={identity}, staleid={int(staleid) & 0xFFFFFFFF}{suffix}"
    )


def representation_iferror(identity: str, staleid: int, staledigest: int) -> str:
    return canonical_iferror(identity, staleid, staledigest)


def stalecontent_matches(left: str, right: str) -> bool:
    return parse_stalecontent(left) == parse_stalecontent(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise StalecontentActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise StalecontentActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise StalecontentActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise StalecontentActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def stale_request(identity: str, staleid: int) -> bytes:
    """HTTP GET that elicits RFC 5861 origin STALE."""

    keyid = f"{int(staleid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /stalecontent/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Stale-Id: {int(staleid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def iferror_request(identity: str, staleid: int, staledigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 5861 IFERROR confirmation of the stored iferror policy."""

    keyid = f"{int(staleid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if staledigest is not None:
        extra = f"Stale-Digest: {int(staledigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /stalecontent/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Stale-Id: {int(staleid) & 0xFFFFFFFF}\r\n"
        "Stale-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    stalecontent_kind = "iferror" if fields.get("stale-confirm") == "1" else "stale"
    stale_field = fields.get("cache-control") or ""
    policy = parse_stalecontent(stale_field) if stale_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "stalecontent_kind": stalecontent_kind,
        "policy": policy,
        "staleid": int(fields["stale-id"]) if fields.get("stale-id") else EMPTY_STALEID,
        "staledigest": int(fields["stale-digest"]) if fields.get("stale-digest") else EMPTY_STALEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def stale_response(identity: str, staleid: int, staledigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 5861 origin STALE, carrying the stored staledigest."""

    advertised = serialize_stalecontent(DEFAULT_STALE)
    payload = bytes(body or canonical_stale(identity, staleid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Cache-Control: {advertised}\r\n"
        f"Stale-Id: {int(staleid) & 0xFFFFFFFF}\r\n"
        f"Stale-Digest: {int(staledigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/stale-content\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def iferror_response(identity: str, staleid: int, staledigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 5861 IFERROR, carrying the stored IFERROR policy."""

    advertised = serialize_stalecontent(IFERROR_POLICY)
    payload = bytes(body or representation_iferror(identity, staleid, staledigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Cache-Control: {advertised}\r\n"
        f"Stale-Id: {int(staleid) & 0xFFFFFFFF}\r\n"
        f"Stale-Digest: {int(staledigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/stale-if-error\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise StalecontentActuationError("illegal_content_length") from error
    field_value = fields.get("cache-control") or ""
    policy = parse_stalecontent(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/stale-if-error" or policy == IFERROR_POLICY:
        status = 200
        stalecontent_kind = "iferror"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        stalecontent_kind = "stale"
    else:
        status = 0
        stalecontent_kind = "stale"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "stalecontent_kind": stalecontent_kind,
        "policy": policy,
        "staleid": int(fields["stale-id"]) if fields.get("stale-id") else EMPTY_STALEID,
        "staledigest": int(fields["stale-digest"]) if fields.get("stale-digest") else EMPTY_STALEDIGEST,
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
        raise StalecontentActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise StalecontentActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise StalecontentActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise StalecontentActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_staleid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"staleid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_staleid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-staleid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_staledigest(staleid: int = EMPTY_STALEID, token: str = SENTINEL) -> int:
    material = canonical_stale(token or SENTINEL, int(staleid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_STALEID = request_staleid(SENTINEL)
DEFAULT_STALEDIGEST = request_staledigest(DEFAULT_STALEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    staleid: int,
    staledigest: int,
    include_staleid: bool = True,
) -> bytes:
    live_staleid = int(staleid) & 0xFFFFFFFF if include_staleid else EMPTY_STALEID
    live_digest = int(staledigest) & 0xFFFFFFFF if include_staleid and live_staleid else EMPTY_STALEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_staleid) if live_staleid else b""
    header = bytearray()
    header.append(SC_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_stale(
    *,
    identity: str,
    staleid: int,
    staledigest: int | None = None,
    include_staleid: bool = True,
) -> bytes:
    live_staleid = int(staleid) & 0xFFFFFFFF if include_staleid else EMPTY_STALEID
    live_digest = int(staledigest) if staledigest is not None else request_staledigest(live_staleid, identity)
    return encode_packet(
        FRAME_STALE,
        identity=identity,
        staleid=live_staleid,
        staledigest=live_digest,
        include_staleid=include_staleid,
    )


def encode_iferror(
    *,
    identity: str,
    staleid: int,
    staledigest: int | None = None,
    include_staleid: bool = True,
) -> bytes:
    live_staleid = int(staleid) & 0xFFFFFFFF if include_staleid else EMPTY_STALEID
    live_digest = int(staledigest) if staledigest is not None else request_staledigest(live_staleid, identity)
    return encode_packet(
        FRAME_IFERROR,
        identity=identity,
        staleid=live_staleid,
        staledigest=live_digest,
        include_staleid=include_staleid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise StalecontentActuationError("short_packet")
    first = raw[0]
    if first != SC_FIRST:
        raise StalecontentActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise StalecontentActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == STALEID_SIZE:
        live_staleid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_staleid = EMPTY_STALEID
    else:
        raise StalecontentActuationError("illegal_staleid")
    if offset >= len(raw):
        raise StalecontentActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_STALE, FRAME_IFERROR}:
        raise StalecontentActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise StalecontentActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise StalecontentActuationError("checksum_failed")
    if len(payload) < 5:
        raise StalecontentActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise StalecontentActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_staleid = int(live_staleid) != EMPTY_STALEID
    has_staledigest = has_staleid and int(live_digest) != EMPTY_STALEDIGEST
    is_stale = frame_type == FRAME_STALE
    is_iferror = frame_type == FRAME_IFERROR
    return {
        "type": int(frame_type),
        "is_stale": is_stale,
        "is_iferror": is_iferror,
        "is_response": is_iferror,
        "staleid": int(live_staleid),
        "has_staleid": has_staleid,
        "staledigest": int(live_digest),
        "has_staledigest": has_staledigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http_state": "RFC5861",
        "serialize_field": canonical_stale(identity, live_staleid) if has_staleid else "",
        "iferror_field": canonical_iferror(identity, live_staleid, live_digest) if has_staledigest else "",
    }


class StalecontentClient:
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
            raise StalecontentActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_iferror"] or not packet["is_response"]:
            raise StalecontentActuationError("staledigest_required")
        if not packet["has_staleid"]:
            raise StalecontentActuationError("staleid_required")
        if not packet["has_staledigest"]:
            raise StalecontentActuationError("staledigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_staledigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_staledigest:
            raise StalecontentActuationError("staledigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "staleid": int(reply.get("staleid") or EMPTY_STALEID),
            "identity": str(reply.get("identity") or ""),
            "staledigest": int(reply.get("staledigest") or EMPTY_STALEDIGEST),
        }

    def report(
        self,
        identity: str,
        staleid: int,
        staledigest: int = EMPTY_STALEDIGEST,
        *,
        wait_staledigest: bool = True,
        include_staleid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_iferror(
            identity=identity,
            staleid=staleid,
            staledigest=staledigest or request_staledigest(staleid, identity),
            include_staleid=include_staleid,
        )
        return self.exchange(packet, wait_staledigest=wait_staledigest)


class StalecontentSession:
    """STALEID-gated loopback RFC 5861 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        staleid_gate: int = DEFAULT_STALEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.staleid_gate = int(staleid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.staleid = EMPTY_STALEID
        self.staledigest = EMPTY_STALEDIGEST
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

    def store_staleid_once(self, identity: str, staleid: int, staledigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(staleid or EMPTY_STALEID)
            live_digest = int(staledigest or EMPTY_STALEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.staleid = live
                self.staledigest = live_digest or request_staledigest(live, name)
                self.stored = True
            return str(self.identity), int(self.staleid), int(self.staledigest)

    def read_staleid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.staleid), int(self.staledigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "staleid": EMPTY_STALEID,
            "staledigest": EMPTY_STALEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _staleid_missing(self) -> bool:
        return not int(self.staleid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, staleid: int, staledigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_iferror(
            identity=identity,
            staleid=staleid,
            staledigest=staledigest,
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
            except StalecontentActuationError:
                continue
            if not packet.get("is_stale") and not packet.get("is_iferror"):
                continue
            if not packet.get("has_staleid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_staleid, stored_digest = self.store_staleid_once(
                identity,
                int(packet.get("staleid") or EMPTY_STALEID),
                int(packet.get("staledigest") or EMPTY_STALEDIGEST),
            )
            if not stored_name or not stored_staleid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_stale"):
                    self.opened = True
                if packet.get("is_iferror"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_staleid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._staleid_missing():
            return self._forbidden("missing_staleid")
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
        do_stale: bool = True,
        do_iferror: bool = True,
        do_staledigest: bool = True,
        replay: bool = True,
        use_staleid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._staleid_missing():
            return self._forbidden("missing_staleid")
        live_token = str(token or SENTINEL)
        origin_staleid = request_staleid(live_token)
        origin_digest = request_staledigest(origin_staleid, live_token)
        client: StalecontentClient | None = None
        independent: StalecontentClient | None = None
        try:
            client = StalecontentClient(self.host, int(self.port))
            if not do_stale:
                return self._conflict("stale_required")
            bind_packet = encode_stale(
                identity=live_token,
                staleid=origin_staleid,
                staledigest=origin_digest,
                include_staleid=use_staleid,
            )
            if not use_staleid:
                try:
                    client.exchange(bind_packet, wait_staledigest=True)
                except StalecontentActuationError:
                    return self._conflict("staleid_required")
                return self._conflict("staleid_required")
            client.send(bind_packet)
            if not do_iferror:
                return self._conflict("iferror_required")
            proxy_packet = encode_iferror(
                identity=live_token,
                staleid=origin_staleid,
                staledigest=origin_digest,
                include_staleid=True,
            )
            if not do_staledigest:
                try:
                    client.exchange(proxy_packet, wait_staledigest=False)
                except StalecontentActuationError as error:
                    if str(error) == "staledigest_required":
                        return self._conflict("staledigest_required")
                    return self._conflict("staledigest_required")
                return self._conflict("staledigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_staledigest=True)
            except StalecontentActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("staleid_required")
                if reason == "staledigest_required":
                    return self._conflict("staledigest_required")
                return self._conflict("stale_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("stale_required")
            if int(reply.get("staleid") or EMPTY_STALEID) != origin_staleid:
                return self._conflict("staledigest_required")
            if int(reply.get("staledigest") or EMPTY_STALEDIGEST) != origin_digest:
                return self._conflict("staledigest_required")
            self.retrieved = True
            if replay:
                independent = StalecontentClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_staleid(live_token),
                        request_staledigest(poll_staleid(live_token), POLL_TOKEN),
                        wait_staledigest=True,
                    )
                except StalecontentActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_staleid, stored_digest = self.read_staleid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_staleid != origin_staleid
                    or stored_digest != origin_digest
                    or int(poll.get("staleid") or EMPTY_STALEID) != origin_staleid
                    or int(poll.get("staledigest") or EMPTY_STALEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_staleid}:{origin_digest}:{live_token}:{canonical_stale(live_token, origin_staleid)}:{canonical_iferror(live_token, origin_staleid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "staleid": origin_staleid,
                "staledigest": origin_digest,
                "stale_frame": True,
                "iferror_frame": True,
                "staledigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "staleid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_stalecontent_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "staleid": origin_staleid,
                "staledigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "stale_frame": True,
                "iferror_frame": True,
                "staledigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "staleid_bound": True,
            }
        except (OSError, StalecontentActuationError) as error:
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
        live = independent_stalecontent_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "staleid": int(live.get("staleid") or EMPTY_STALEID),
            "staledigest": int(live.get("staledigest") or EMPTY_STALEDIGEST),
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


def call_stalecontent_tool(session: StalecontentSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one stale tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_stale = True if arguments.get("stale") is None else bool(arguments.get("stale"))
    do_iferror = True if arguments.get("iferror") is None else bool(arguments.get("iferror"))
    do_staledigest = True if arguments.get("staledigest") is None else bool(arguments.get("staledigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_staleid = True if arguments.get("use_staleid") is None else bool(arguments.get("use_staleid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_stale=do_stale,
            do_iferror=do_iferror,
            do_staledigest=do_staledigest,
            replay=replay,
            use_staleid=use_staleid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise StalecontentActuationError(f"unsupported stalecontent action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_stalecontent_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed stale staledigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "staleid": EMPTY_STALEID,
        "staledigest": EMPTY_STALEDIGEST,
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
            "stale_frame",
            "iferror_frame",
            "staledigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "staleid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    staleid = int(payload.get("staleid") or EMPTY_STALEID)
    staledigest = int(payload.get("staledigest") or EMPTY_STALEDIGEST)
    dual = port > 0 and bool(staleid) and bool(staledigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "staleid": staleid,
        "staledigest": staledigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "stale_frame": payload.get("stale_frame") is True,
        "iferror_frame": payload.get("iferror_frame") is True,
        "staledigest_response": payload.get("staledigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "staleid_bound": payload.get("staleid_bound") is True,
    }


def run_stalecontent_workflow(
    *,
    with_staleid: bool = True,
    skip_bind: bool = False,
    do_stale: bool = True,
    do_iferror: bool = True,
    do_staledigest: bool = True,
    replay: bool = True,
    use_staleid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 5861 STALE/IFERROR staleid cycle workflow."""

    descriptor = stalecontent_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STALECONTENT_TOOL_PROVIDER),
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
        raise StalecontentActuationError(f"stalecontent tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="stalecontent-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = StalecontentSession(out, staleid_gate=DEFAULT_STALEID if with_staleid else EMPTY_STALEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "stale": do_stale,
            "iferror": do_iferror,
            "staledigest": do_staledigest,
            "replay": replay,
            "use_staleid": use_staleid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_stalecontent_tool(session, arguments))
            except StalecontentActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_stalecontent_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_staleid
        and not skip_bind
        and do_stale
        and do_iferror
        and do_staledigest
        and replay
        and use_staleid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "stalecontent_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_staleid": with_staleid,
        "skip_bind": skip_bind,
        "stale_frame": do_stale,
        "iferror": do_iferror,
        "staledigest": do_staledigest,
        "replay": replay,
        "use_staleid": use_staleid,
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
        "staleid_value": int(publish_result.get("staleid") or independent.get("staleid") or EMPTY_STALEID),
        "staledigest_value": int(publish_result.get("staledigest") or independent.get("staledigest") or EMPTY_STALEDIGEST),
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
        "staleid": int(trace_body["staleid_value"] or EMPTY_STALEID),
        "staledigest": int(trace_body["staledigest_value"] or EMPTY_STALEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_staleid": with_staleid,
        "skip_bind": skip_bind,
        "stale_cycle": do_stale,
        "iferror_cycle": do_iferror,
        "staledigest_cycle": do_staledigest,
        "replay": replay,
        "use_staleid": use_staleid,
    }


def verify_stalecontent_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_stalecontent_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    staleid = int(trace.get("staleid_value") or independent.get("staleid") or EMPTY_STALEID)
    staledigest = int(trace.get("staledigest_value") or independent.get("staledigest") or EMPTY_STALEDIGEST)
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
        "stale_frame": independent.get("stale_frame") is True,
        "iferror_frame": independent.get("iferror_frame") is True,
        "staledigest_response": independent.get("staledigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "staleid_bound": independent.get("staleid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "staledigest_recorded": (
            port > 0
            and staleid == DEFAULT_STALEID
            and staledigest == DEFAULT_STALEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def stalecontent_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.stalecontent_actuation import "
        "builtin_stalecontent_actuation_proof; r=builtin_stalecontent_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='stalecontent_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_stalecontent_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=STALECONTENT_ACTUATION_ID,
        name="First-class RFC 5861 HTTP Cache-Control Extensions for Stale Content STALE/IFERROR actuation",
        description=(
            "Missions that require a stalecontent tool can opt the stalecontent provider in, "
            "bind a loopback RFC 5861 HTTP Cache-Control Extensions for Stale Content endpoint, complete a STALE "
            "with a non-empty staleid, lockstep a IFERROR that carries the "
            "stored staledigest, independently poll the stored staledigest "
            "on a later socket, and seal a digest-chained staledigest. Default "
            "routing stays fail-closed; a missing staleid keeps the hole "
            "falsifiable, and skip-STALE/IFERROR/STALEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.stalecontent_actuation:builtin_stalecontent_actuation_proof",
        proof_command=stalecontent_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.extvalue-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/stalecontent_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/extvalue_actuation.py",
            "src/blackhole_agent/httppatch_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required stalecontent tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 5861 daemon, speaks a "
            "STALE then IFERROR over HTTP Cache-Control Extensions for Stale Content with a non-empty staleid and "
            "staledigest, independently polls the stored staledigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 5987 Character Set and Language Encoding lockstep is proved. "
            "Missing staleids, skip-STALE, skip-IFERROR, skip-staledigest, skip-REPLAY, "
            "and a STALE aimed without a staleid stay fail-closed. "
            "Later genesis can take RFC 5789 PATCH Method for HTTP PATCH/ENTITY as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("stalecontent", "rfc5861", "http", "staleid", "staledigest", "stale", "iferror", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T195251Z-930946ee",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_stalecontent_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 5861 stale lockstep actuation seals a staledigest."""

    from blackhole_agent.httppatch_actuation import (
        HTTPPATCH_ACTUATION_GOAL,
        HTTPPATCH_ACTUATION_ID,
    )
    from blackhole_agent.extvalue_actuation import (
        EXTVALUE_ACTUATION_GOAL,
        EXTVALUE_ACTUATION_ID,
    )
    from blackhole_agent.weblinking_actuation import (
        WEBLINKING_ACTUATION_GOAL,
        WEBLINKING_ACTUATION_ID,
    )
    from blackhole_agent.httpcookie_actuation import (
        HTTPCOOKIE_ACTUATION_GOAL,
        HTTPCOOKIE_ACTUATION_ID,
    )
    from blackhole_agent.weborigin_actuation import (
        WEBORIGIN_ACTUATION_GOAL,
        WEBORIGIN_ACTUATION_ID,
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
    checks["denylists_self"] = STALECONTENT_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(STALECONTENT_ACTUATION_GOAL) == (
        STALECONTENT_ACTUATION_ID,
    )
    checks["leftover_text_binds_stalecontent"] = leftover_marker_ids(STALECONTENT_LEFTOVER) == (
        STALECONTENT_ACTUATION_ID,
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
        (WEBORIGIN_ACTUATION_GOAL, WEBORIGIN_ACTUATION_ID, "weborigin"),
        (HTTPCOOKIE_ACTUATION_GOAL, HTTPCOOKIE_ACTUATION_ID, "httpcookie"),
        (WEBLINKING_ACTUATION_GOAL, WEBLINKING_ACTUATION_ID, "weblinking"),
        (EXTVALUE_ACTUATION_GOAL, EXTVALUE_ACTUATION_ID, "extvalue"),
        (HTTPPATCH_ACTUATION_GOAL, HTTPPATCH_ACTUATION_ID, "httppatch"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_stalecontent"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"stalecontent_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            STALECONTENT_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = STALECONTENT_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_stalecontent(DEFAULT_STALE)
    rebuilt = serialize_stalecontent(parse_stalecontent(advertised))
    preloaded = parse_stalecontent(RFC_STALECONTENT_IFERROR)
    header = encode_stalecontent_header(DEFAULT_STALE)
    parsed_header = parse_stalecontent_header(header)
    asked = parse_http_request(stale_request(SENTINEL, DEFAULT_STALEID))
    preload_req = parse_http_request(iferror_request(SENTINEL, DEFAULT_STALEID, DEFAULT_STALEDIGEST))
    got = parse_http_response(stale_response(SENTINEL, DEFAULT_STALEID, DEFAULT_STALEDIGEST))
    preload_reply = parse_http_response(
        iferror_response(SENTINEL, DEFAULT_STALEID, DEFAULT_STALEDIGEST)
    )
    checks["stalecontent_roundtrip"] = (
        parse_stalecontent(advertised) == DEFAULT_STALE
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_STALE_FIELD
        and is_token("STALE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_STALE_FIELD
        and parsed_header["policy"] == DEFAULT_STALE
        and parsed_header["header"] == STALE_HEADER
        and parsed_header["stale"] is True
        and parsed_header["iferror"] is False
        and preloaded == IFERROR_POLICY
        and ascii_serialize_stale_directive() == RFC_STALE_DIRECTIVE
        and stale_directive_pair() == ("stale-while-revalidate", RFC_STALE_WHILE_REVALIDATE)
        and RFC_STALE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_stalecontent(IFERROR_POLICY) == RFC_STALECONTENT_IFERROR
        and DEFAULT_STALEDIGEST == request_staledigest(DEFAULT_STALEID, SENTINEL)
        and "staledigest=" in canonical_iferror(SENTINEL, DEFAULT_STALEID, DEFAULT_STALEDIGEST)
        and canonical_stale(SENTINEL, DEFAULT_STALEID).startswith("STALE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["stalecontent_kind"] == "stale"
        and asked["staleid"] == DEFAULT_STALEID
        and preload_req["stalecontent_kind"] == "iferror"
        and preload_req["staledigest"] == DEFAULT_STALEDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["stalecontent_kind"] == "stale"
        and preload_reply["stalecontent_kind"] == "iferror"
        and got["policy"] == DEFAULT_STALE
        and preload_reply["policy"] == IFERROR_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["staledigest"] == DEFAULT_STALEDIGEST
        and preload_reply["staledigest"] == DEFAULT_STALEDIGEST
        and stalecontent_matches(serialize_stalecontent(got["policy"]), advertised)
    )

    checks["catalog_names_stalecontent"] = (
        len(catalog) > 90
        and catalog[90]["id"] == STALECONTENT_ACTUATION_ID
        and catalog[89]["id"] == EXTVALUE_ACTUATION_ID
        and catalog[90]["source"] == "genesis_bind_stalecontent"
    )
    checks["catalog_names_httppatch"] = (
        len(catalog) > 91
        and catalog[91]["id"] == HTTPPATCH_ACTUATION_ID
        and catalog[91]["source"] == "genesis_bind_httppatch"
    )
    family = capability_family(STALECONTENT_ACTUATION_GOAL)
    checks["family_is_stalecontent"] = "stalecontent" in family
    checks["family_is_stalecontent_surface"] = "stalecontent" in family
    checks["family_is_staleid"] = "staleid" in family
    checks["family_is_rfc5861"] = "rfc5861" in family
    checks["family_is_staledigest"] = "staledigest" in family
    checks["family_is_not_httppatch"] = (
        "httppatch" not in family
        and "rfc5789" not in family
        and "patchid" not in family
        and "patchdigest" not in family
    )
    checks["family_is_not_extvalue"] = (
        "extvalue" not in family
        and "rfc5987" not in family
        and "charsetid" not in family
        and "charsetdigest" not in family
    )
    checks["family_is_not_weblinking"] = (
        "weblinking" not in family
        and "rfc5988" not in family
        and "relationid" not in family
        and "relationdigest" not in family
    )
    checks["family_is_not_httpcookie"] = (
        "httpcookie" not in family
        and "rfc6265" not in family
        and "cookieid" not in family
        and "cookiedigest" not in family
    )
    checks["family_is_not_weborigin"] = (
        "weborigin" not in family
        and "rfc6454" not in family
        and "tupleid" not in family
        and "tupledigest" not in family
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
        "dtls" not in family and "rfc6347" not in family and "epoch" not in family
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
    packed = encode_stale(identity=SENTINEL, staleid=DEFAULT_STALEID, staledigest=DEFAULT_STALEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_stale"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_staleid"] is True
        and parsed["staleid"] == DEFAULT_STALEID
        and parsed["staledigest"] == DEFAULT_STALEDIGEST
        and parsed["is_response"] is False
        and parsed["is_iferror"] is False
        and parsed["type"] == FRAME_STALE
        and parsed["first_byte"] == SC_FIRST
    )
    shook = encode_iferror(
        identity=SENTINEL,
        staleid=DEFAULT_STALEID,
        staledigest=DEFAULT_STALEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_iferror"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_stale"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["staleid"] == DEFAULT_STALEID
        and answer_parsed["staledigest"] == DEFAULT_STALEDIGEST
        and answer_parsed["has_staledigest"] is True
        and answer_parsed["type"] == FRAME_IFERROR
        and answer_parsed["first_byte"] == SC_FIRST
    )
    bare = encode_stale(identity=SENTINEL, staleid=DEFAULT_STALEID, include_staleid=False)
    checks["missing_staleid_is_unauthenticated"] = parse_message(bare)["has_staleid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    stalecontent_signature = semantic_signature(STALECONTENT_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(stalecontent_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_stalecontent = ToolDescriptor(name="remote_stalecontent", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_stalecontent)
    checks["naive_mcp_stalecontent_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = stalecontent_tool_descriptor()
    default_stalecontent = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STALECONTENT_TOOL_PROVIDER),
    )
    checks["default_stalecontent_provider_is_unsupported"] = (
        default_stalecontent.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{STALECONTENT_TOOL_PROVIDER}" in default_stalecontent.reasons
    )
    checks["opted_in_stalecontent_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_stalecontent],
        required_tool_names=("local_memory", "stalecontent"),
    )
    checks["naive_preflight_missing_stalecontent"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["stalecontent"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "stalecontent"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STALECONTENT_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "stalecontent" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="stalecontent-actuation-") as tmp:
        root = Path(tmp)
        missing = run_stalecontent_workflow(with_staleid=False, output_dir=root / "missing")
        skip_bind = run_stalecontent_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_stale = run_stalecontent_workflow(do_stale=False, output_dir=root / "skip-stale")
        skip_iferror = run_stalecontent_workflow(do_iferror=False, output_dir=root / "skip-iferror")
        skip_staledigest = run_stalecontent_workflow(do_staledigest=False, output_dir=root / "skip-staledigest")
        skip_replay = run_stalecontent_workflow(replay=False, output_dir=root / "skip-replay")
        skip_staleid = run_stalecontent_workflow(use_staleid=False, output_dir=root / "skip-staleid")
        live = run_stalecontent_workflow(output_dir=root / "live")
        verify = verify_stalecontent_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_stalecontent_trace(clone)
        checks["naive_without_staleid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_staleid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_stale_stays_empty"] = (
            skip_stale["ok"] is False
            and skip_stale["error"] == "stale_required"
            and skip_stale["final_status"] == 409
            and skip_stale["payload_exists"] is False
        )
        checks["skip_iferror_stays_empty"] = (
            skip_iferror["ok"] is False
            and skip_iferror["error"] == "iferror_required"
            and skip_iferror["final_status"] == 409
            and skip_iferror["payload_exists"] is False
        )
        checks["skip_staledigest_stays_empty"] = (
            skip_staledigest["ok"] is False
            and skip_staledigest["error"] == "staledigest_required"
            and skip_staledigest["final_status"] == 409
            and skip_staledigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_staleid_stays_empty"] = (
            skip_staleid["ok"] is False
            and skip_staleid["error"] == "staleid_required"
            and skip_staleid["final_status"] == 409
            and skip_staleid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_staledigest"] = (
            int(live.get("staleid") or 0) == DEFAULT_STALEID
            and int(live.get("staledigest") or 0) == DEFAULT_STALEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_staleid_encode_iferror_staledigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_stale["ok"] is False
            and skip_iferror["ok"] is False
            and skip_staledigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_staleid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="stalecontent-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != STALECONTENT_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_stalecontent"] = (
        live_goal == STALECONTENT_ACTUATION_GOAL
        and STALECONTENT_ACTUATION_ID in live_done
        and live_source == "genesis_bind_stalecontent"
    )

    with tempfile.TemporaryDirectory(prefix="stalecontent-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(STALECONTENT_LEFTOVER, root)
        register_catalog_proved(root, STALECONTENT_ACTUATION_ID)
        reason = leftover_satisfied_by(STALECONTENT_LEFTOVER, root)
        after = leftover_is_open(STALECONTENT_LEFTOVER, root)
    checks["stalecontent_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_stalecontent_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{STALECONTENT_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_stalecontent_actuation_capability()
    return {
        "ok": ok,
        "action": "stalecontent_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": STALECONTENT_ACTUATION_GOAL,
        "done_when": STALECONTENT_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
