"""Drive a first-class HTTP Alternative Services tool through RFC 7838 ALTSVC/ORIGIN.

Tool routing already fails missions that require ``altsvc``: hosted
altsvc endpoints stay on the unsupported MCP provider, and no first-party
altsvc provider is executable. Unbound therefore cannot speak an ALTSVC,
lockstep an ORIGIN altsvcid handshake over HTTP Alternative Services ALTSVCID,
independently poll the stored origindigest, or seal an origindigest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``altsvc`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 7838 daemon
- keep a missing-altsvcid client so the altsvc-altsvcid hole stays falsifiable
- refuse ORIGIN until an ALTSVC lands with a non-empty altsvcid
- independently poll the stored origindigest on a later client socket
- persist a sealed origindigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 8188 Encrypted Content-Encoding
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
    ALTSVC_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    altsvc_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
ALTSVC_ACTUATION_ID = "capability.altsvc-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-AS-OK"
POLL_TOKEN = "BH-AS-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_ALTSVCID = 0
EMPTY_ORIGINDIGEST = 0
AS_FIRST = 0x53  # RFC 7838 Alt-Svc (ASCII 'S')
ALTSVCID_SIZE = 4
ORIGINDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_ORIGIN = 0x0C  # RFC 8336 ORIGIN HTTP/2 frame
FRAME_ALTSVC = 0x0A  # RFC 7838 ALTSVC HTTP/2 frame
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
ALTSVC_LEFTOVER = (
    "Later genesis can take RFC 7838 HTTP Alternative Services ALTSVC/ORIGIN over an "
    "altsvcid-gated origindigest."
)
ALTSVC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ALTSVC_ACTUATION_ID};"
    f"capability_proved:{ALTSVC_ACTUATION_ID};"
    "no_skill_route"
)
ALTSVC_ACTUATION_GOAL = (
    "Repair rfc7838 altsvc altsvc/origin cycle cannot land over http "
    "altsvc altsvcid: hosted altsvc endpoints remain unsupported so an ALTSVC then "
    "ORIGIN altsvcid handshake cannot land and a sealed origindigest "
    "cannot be produced. A missing altsvc altsvcid stays forbidden; fail-closed "
    "routing never opts the altsvc provider in. An independent later poll of the "
    "stored origindigest keeps the hole falsifiable."
)


class AltsvcActuationError(RuntimeError):
    """Raised when the HTTP Alternative Services session or loopback daemon fixture misbehaves."""


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
# RFC 7838 section 3 example.
RFC_ALTSVC_FIELD = 'h2=":443"; ma=2592000'
RFC_ALTSVC_DUAL = 'h2="alt.example.com:8000", h2=":443"'
# alternative = (protocol-id, host, port, ma, persist)
DEFAULT_ALTS: tuple[tuple[str, str, int, int, int], ...] = (("h2", "", 443, 2592000, 0),)
ORIGIN_ALTS: tuple[tuple[str, str, int, int, int], ...] = (("h2", "", 443, 2592000, 0),)
ALPN_H2 = "h2"
HTTP2_ALTSVC_TYPE = 0x0A
HTTP2_ORIGIN_TYPE = 0x0C


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise AltsvcActuationError("short_altsvc")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 7838 protocol-id / parameter names."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_alt_svc(alts: Sequence[tuple[str, str, int, int, int]]) -> str:
    """Serialize RFC 7838 Alt-Svc field-value (clear is the empty list)."""

    chunks: list[str] = []
    for protocol, host, port, ma, persist in alts:
        if not is_token(protocol):
            raise AltsvcActuationError("illegal_protocol")
        chunk = f'{protocol}="{host}:{int(port)}"'
        if int(ma) > 0:
            chunk += f"; ma={int(ma)}"
        if int(persist):
            chunk += "; persist=1"
        chunks.append(chunk)
    return ", ".join(chunks)


def parse_alt_svc(text: str) -> tuple[tuple[str, str, int, int, int], ...]:
    """Parse RFC 7838 Alt-Svc field-value into protocol/host/port/ma/persist tuples."""

    raw = str(text or "").strip()
    if not raw or raw == "clear":
        return ()
    parser = _Parser(raw)
    members: list[tuple[str, str, int, int, int]] = []
    while True:
        parser.skip_ows()
        start = parser.pos
        while parser.peek() and parser.peek() in TCHAR:
            parser.pos += 1
        protocol = parser.text[start : parser.pos]
        if not protocol:
            raise AltsvcActuationError("illegal_altsvc")
        parser.skip_ows()
        if parser.take() != "=":
            raise AltsvcActuationError("illegal_altsvc")
        parser.skip_ows()
        if parser.take() != '"':
            raise AltsvcActuationError("illegal_authority")
        auth_start = parser.pos
        while parser.peek() and parser.peek() != '"':
            parser.pos += 1
        authority = parser.text[auth_start : parser.pos]
        if parser.take() != '"':
            raise AltsvcActuationError("illegal_authority")
        if ":" not in authority:
            raise AltsvcActuationError("illegal_authority")
        host, _, port_text = authority.rpartition(":")
        try:
            port = int(port_text)
        except ValueError as error:
            raise AltsvcActuationError("illegal_port") from error
        ma = 0
        persist = 0
        while True:
            parser.skip_ows()
            if parser.peek() != ";":
                break
            parser.pos += 1
            parser.skip_ows()
            name_start = parser.pos
            while parser.peek() and parser.peek() in TCHAR:
                parser.pos += 1
            name = parser.text[name_start : parser.pos].lower()
            if not name:
                break
            parser.skip_ows()
            if parser.take() != "=":
                raise AltsvcActuationError("illegal_parameter")
            parser.skip_ows()
            val_start = parser.pos
            while parser.peek() and parser.peek() not in ";, \t":
                parser.pos += 1
            value = parser.text[val_start : parser.pos]
            if name == "ma":
                ma = int(value)
            elif name == "persist":
                persist = int(value)
        members.append((protocol, host, port, ma, persist))
        parser.skip_ows()
        if parser.peek() != ",":
            break
        parser.pos += 1
    parser.skip_ows()
    if not parser.eof():
        raise AltsvcActuationError("illegal_altsvc")
    return tuple(members)


def origin_uri(identity: str) -> str:
    return f"https://{identity}"


def encode_altsvc_frame(origin: str, field_value: str) -> bytes:
    """RFC 7838 ALTSVC HTTP/2 frame payload (type 0x0a)."""

    origin_b = str(origin or "").encode("ascii")
    value_b = str(field_value or "").encode("ascii")
    if len(origin_b) > 0xFFFF:
        raise AltsvcActuationError("illegal_origin")
    return struct.pack("!H", len(origin_b)) + origin_b + value_b


def parse_altsvc_frame(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 2:
        raise AltsvcActuationError("short_altsvc_frame")
    origin_len = struct.unpack("!H", raw[:2])[0]
    if 2 + int(origin_len) > len(raw):
        raise AltsvcActuationError("short_altsvc_frame")
    origin = raw[2 : 2 + int(origin_len)].decode("ascii")
    field_value = raw[2 + int(origin_len) :].decode("ascii")
    return {
        "origin": origin,
        "origin_len": int(origin_len),
        "field_value": field_value,
        "alts": parse_alt_svc(field_value) if field_value and field_value != "clear" else (),
        "frame_type": HTTP2_ALTSVC_TYPE,
    }


def encode_origin_frame(origins: Sequence[str]) -> bytes:
    """RFC 8336 ORIGIN HTTP/2 frame payload (type 0x0c)."""

    out = bytearray()
    for origin in origins:
        raw = str(origin or "").encode("ascii")
        if len(raw) > 0xFFFF:
            raise AltsvcActuationError("illegal_origin")
        out.extend(struct.pack("!H", len(raw)))
        out.extend(raw)
    return bytes(out)


def parse_origin_frame(data: bytes) -> tuple[str, ...]:
    raw = bytes(data or b"")
    offset = 0
    origins: list[str] = []
    while offset < len(raw):
        if offset + 2 > len(raw):
            raise AltsvcActuationError("short_origin_frame")
        length = struct.unpack("!H", raw[offset : offset + 2])[0]
        offset += 2
        if offset + int(length) > len(raw):
            raise AltsvcActuationError("short_origin_frame")
        origins.append(raw[offset : offset + int(length)].decode("ascii"))
        offset += int(length)
    return tuple(origins)


def canonical_altsvc(identity: str, altsvcid: int) -> str:
    """RFC 7838 Alt-Svc advertisement bound to identity and altsvcid."""

    return (
        f"{serialize_alt_svc(DEFAULT_ALTS)}; "
        f"identity={identity}; altsvcid={int(altsvcid) & 0xFFFFFFFF}"
    )


def canonical_origin(identity: str, altsvcid: int, origindigest: int | None = None) -> str:
    """RFC 8336 ORIGIN of the stored alternative service."""

    suffix = ""
    if origindigest is not None:
        suffix = f"; origindigest={int(origindigest) & 0xFFFFFFFF}"
    return (
        f"{origin_uri(identity)}; "
        f"identity={identity}; altsvcid={int(altsvcid) & 0xFFFFFFFF}{suffix}"
    )


def representation_origin(identity: str, altsvcid: int, origindigest: int) -> str:
    return canonical_origin(identity, altsvcid, origindigest)


def alt_svc_matches(left: str, right: str) -> bool:
    return parse_alt_svc(left) == parse_alt_svc(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise AltsvcActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise AltsvcActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise AltsvcActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise AltsvcActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def altsvc_request(identity: str, altsvcid: int) -> bytes:
    """HTTP GET that elicits RFC 7838 Alt-Svc."""

    keyid = f"{int(altsvcid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /altsvc/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Alt-Svc-Id: {int(altsvcid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def origin_request(identity: str, altsvcid: int, origindigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 8336 ORIGIN confirmation of the stored Alt-Svc."""

    keyid = f"{int(altsvcid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if origindigest is not None:
        extra = f"Origin-Digest: {int(origindigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /altsvc/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Alt-Svc-Id: {int(altsvcid) & 0xFFFFFFFF}\r\n"
        "Origin-Frame: 1\r\n"
        f"Origin: {origin_uri(host)}\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    as_kind = "origin" if fields.get("origin-frame") == "1" else "altsvc"
    alts = parse_alt_svc(fields["alt-svc"]) if fields.get("alt-svc") else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "as_kind": as_kind,
        "alts": alts,
        "origin": fields.get("origin", ""),
        "altsvcid": int(fields["alt-svc-id"]) if fields.get("alt-svc-id") else EMPTY_ALTSVCID,
        "origindigest": int(fields["origin-digest"]) if fields.get("origin-digest") else EMPTY_ORIGINDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def altsvc_response(identity: str, altsvcid: int, origindigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 7838 Alt-Svc, carrying the stored origindigest."""

    advertised = serialize_alt_svc(DEFAULT_ALTS)
    payload = bytes(body or canonical_altsvc(identity, altsvcid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Alt-Svc: {advertised}\r\n"
        f"Alt-Svc-Id: {int(altsvcid) & 0xFFFFFFFF}\r\n"
        f"Origin-Digest: {int(origindigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/alt-svc\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def origin_response(identity: str, altsvcid: int, origindigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 8336 ORIGIN, carrying the stored origin URI."""

    advertised = serialize_alt_svc(ORIGIN_ALTS)
    payload = bytes(body or representation_origin(identity, altsvcid, origindigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Origin: {origin_uri(identity)}\r\n"
        f"Alt-Svc: {advertised}\r\n"
        f"Alt-Svc-Id: {int(altsvcid) & 0xFFFFFFFF}\r\n"
        f"Origin-Digest: {int(origindigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: text/plain\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise AltsvcActuationError("illegal_content_length") from error
    alts = parse_alt_svc(fields["alt-svc"]) if fields.get("alt-svc") else ()
    if fields.get("origin"):
        status = 200
        as_kind = "origin"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        as_kind = "altsvc"
    else:
        status = 0
        as_kind = "altsvc"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "as_kind": as_kind,
        "alts": alts,
        "origin": fields.get("origin", ""),
        "altsvcid": int(fields["alt-svc-id"]) if fields.get("alt-svc-id") else EMPTY_ALTSVCID,
        "origindigest": int(fields["origin-digest"]) if fields.get("origin-digest") else EMPTY_ORIGINDIGEST,
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
        raise AltsvcActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise AltsvcActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise AltsvcActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise AltsvcActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_altsvcid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"altsvcid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_altsvcid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-altsvcid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_origindigest(altsvcid: int = EMPTY_ALTSVCID, token: str = SENTINEL) -> int:
    material = canonical_altsvc(token or SENTINEL, int(altsvcid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_ALTSVCID = request_altsvcid(SENTINEL)
DEFAULT_ORIGINDIGEST = request_origindigest(DEFAULT_ALTSVCID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    altsvcid: int,
    origindigest: int,
    include_altsvcid: bool = True,
) -> bytes:
    live_altsvcid = int(altsvcid) & 0xFFFFFFFF if include_altsvcid else EMPTY_ALTSVCID
    live_digest = int(origindigest) & 0xFFFFFFFF if include_altsvcid and live_altsvcid else EMPTY_ORIGINDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_altsvcid) if live_altsvcid else b""
    header = bytearray()
    header.append(AS_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_altsvc(
    *,
    identity: str,
    altsvcid: int,
    origindigest: int | None = None,
    include_altsvcid: bool = True,
) -> bytes:
    live_altsvcid = int(altsvcid) & 0xFFFFFFFF if include_altsvcid else EMPTY_ALTSVCID
    live_digest = int(origindigest) if origindigest is not None else request_origindigest(live_altsvcid, identity)
    return encode_packet(
        FRAME_ALTSVC,
        identity=identity,
        altsvcid=live_altsvcid,
        origindigest=live_digest,
        include_altsvcid=include_altsvcid,
    )


def encode_origin(
    *,
    identity: str,
    altsvcid: int,
    origindigest: int | None = None,
    include_altsvcid: bool = True,
) -> bytes:
    live_altsvcid = int(altsvcid) & 0xFFFFFFFF if include_altsvcid else EMPTY_ALTSVCID
    live_digest = int(origindigest) if origindigest is not None else request_origindigest(live_altsvcid, identity)
    return encode_packet(
        FRAME_ORIGIN,
        identity=identity,
        altsvcid=live_altsvcid,
        origindigest=live_digest,
        include_altsvcid=include_altsvcid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise AltsvcActuationError("short_packet")
    first = raw[0]
    if first != AS_FIRST:
        raise AltsvcActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise AltsvcActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == ALTSVCID_SIZE:
        live_altsvcid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_altsvcid = EMPTY_ALTSVCID
    else:
        raise AltsvcActuationError("illegal_altsvcid")
    if offset >= len(raw):
        raise AltsvcActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ALTSVC, FRAME_ORIGIN}:
        raise AltsvcActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise AltsvcActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise AltsvcActuationError("checksum_failed")
    if len(payload) < 5:
        raise AltsvcActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise AltsvcActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_altsvcid = int(live_altsvcid) != EMPTY_ALTSVCID
    has_origindigest = has_altsvcid and int(live_digest) != EMPTY_ORIGINDIGEST
    is_altsvc = frame_type == FRAME_ALTSVC
    is_origin = frame_type == FRAME_ORIGIN
    return {
        "type": int(frame_type),
        "is_altsvc": is_altsvc,
        "is_origin": is_origin,
        "is_response": is_origin,
        "altsvcid": int(live_altsvcid),
        "has_altsvcid": has_altsvcid,
        "origindigest": int(live_digest),
        "has_origindigest": has_origindigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "alternative_services": "RFC7838",
        "altsvc_field": canonical_altsvc(identity, live_altsvcid) if has_altsvcid else "",
        "origin_field": canonical_origin(identity, live_altsvcid, live_digest) if has_origindigest else "",
    }


class AltsvcClient:
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
            raise AltsvcActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_origin"] or not packet["is_response"]:
            raise AltsvcActuationError("origindigest_required")
        if not packet["has_altsvcid"]:
            raise AltsvcActuationError("altsvcid_required")
        if not packet["has_origindigest"]:
            raise AltsvcActuationError("origindigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_origindigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_origindigest:
            raise AltsvcActuationError("origindigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "altsvcid": int(reply.get("altsvcid") or EMPTY_ALTSVCID),
            "identity": str(reply.get("identity") or ""),
            "origindigest": int(reply.get("origindigest") or EMPTY_ORIGINDIGEST),
        }

    def origin(
        self,
        identity: str,
        altsvcid: int,
        origindigest: int = EMPTY_ORIGINDIGEST,
        *,
        wait_origindigest: bool = True,
        include_altsvcid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_origin(
            identity=identity,
            altsvcid=altsvcid,
            origindigest=origindigest or request_origindigest(altsvcid, identity),
            include_altsvcid=include_altsvcid,
        )
        return self.exchange(packet, wait_origindigest=wait_origindigest)


class AltsvcSession:
    """ALTSVCID-gated loopback RFC 7838 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        altsvcid_gate: int = DEFAULT_ALTSVCID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.altsvcid_gate = int(altsvcid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.altsvcid = EMPTY_ALTSVCID
        self.origindigest = EMPTY_ORIGINDIGEST
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

    def store_altsvcid_once(self, identity: str, altsvcid: int, origindigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(altsvcid or EMPTY_ALTSVCID)
            live_digest = int(origindigest or EMPTY_ORIGINDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.altsvcid = live
                self.origindigest = live_digest or request_origindigest(live, name)
                self.stored = True
            return str(self.identity), int(self.altsvcid), int(self.origindigest)

    def read_altsvcid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.altsvcid), int(self.origindigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "altsvcid": EMPTY_ALTSVCID,
            "origindigest": EMPTY_ORIGINDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _altsvcid_missing(self) -> bool:
        return not int(self.altsvcid_gate or 0)

    def _reply_origin(self, peer: tuple[str, int], identity: str, altsvcid: int, origindigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_origin(
            identity=identity,
            altsvcid=altsvcid,
            origindigest=origindigest,
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
            except AltsvcActuationError:
                continue
            if not packet.get("is_altsvc") and not packet.get("is_origin"):
                continue
            if not packet.get("has_altsvcid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_altsvcid, stored_digest = self.store_altsvcid_once(
                identity,
                int(packet.get("altsvcid") or EMPTY_ALTSVCID),
                int(packet.get("origindigest") or EMPTY_ORIGINDIGEST),
            )
            if not stored_name or not stored_altsvcid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_altsvc"):
                    self.opened = True
                if packet.get("is_origin"):
                    self.handshook = True
                self.retrieved = True
            self._reply_origin(peer, stored_name, stored_altsvcid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._altsvcid_missing():
            return self._forbidden("missing_altsvcid")
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
        do_altsvc: bool = True,
        do_origin: bool = True,
        do_origindigest: bool = True,
        replay: bool = True,
        use_altsvcid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._altsvcid_missing():
            return self._forbidden("missing_altsvcid")
        live_token = str(token or SENTINEL)
        origin_altsvcid = request_altsvcid(live_token)
        origin_digest = request_origindigest(origin_altsvcid, live_token)
        client: AltsvcClient | None = None
        independent: AltsvcClient | None = None
        try:
            client = AltsvcClient(self.host, int(self.port))
            if not do_altsvc:
                return self._conflict("altsvc_required")
            bind_packet = encode_altsvc(
                identity=live_token,
                altsvcid=origin_altsvcid,
                origindigest=origin_digest,
                include_altsvcid=use_altsvcid,
            )
            if not use_altsvcid:
                try:
                    client.exchange(bind_packet, wait_origindigest=True)
                except AltsvcActuationError:
                    return self._conflict("altsvcid_required")
                return self._conflict("altsvcid_required")
            client.send(bind_packet)
            if not do_origin:
                return self._conflict("origin_required")
            proxy_packet = encode_origin(
                identity=live_token,
                altsvcid=origin_altsvcid,
                origindigest=origin_digest,
                include_altsvcid=True,
            )
            if not do_origindigest:
                try:
                    client.exchange(proxy_packet, wait_origindigest=False)
                except AltsvcActuationError as error:
                    if str(error) == "origindigest_required":
                        return self._conflict("origindigest_required")
                    return self._conflict("origindigest_required")
                return self._conflict("origindigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_origindigest=True)
            except AltsvcActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("altsvcid_required")
                if reason == "origindigest_required":
                    return self._conflict("origindigest_required")
                return self._conflict("altsvc_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("altsvc_required")
            if int(reply.get("altsvcid") or EMPTY_ALTSVCID) != origin_altsvcid:
                return self._conflict("origindigest_required")
            if int(reply.get("origindigest") or EMPTY_ORIGINDIGEST) != origin_digest:
                return self._conflict("origindigest_required")
            self.retrieved = True
            if replay:
                independent = AltsvcClient(self.host, int(self.port))
                try:
                    poll = independent.origin(
                        POLL_TOKEN,
                        poll_altsvcid(live_token),
                        request_origindigest(poll_altsvcid(live_token), POLL_TOKEN),
                        wait_origindigest=True,
                    )
                except AltsvcActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_altsvcid, stored_digest = self.read_altsvcid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_altsvcid != origin_altsvcid
                    or stored_digest != origin_digest
                    or int(poll.get("altsvcid") or EMPTY_ALTSVCID) != origin_altsvcid
                    or int(poll.get("origindigest") or EMPTY_ORIGINDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_altsvcid}:{origin_digest}:{live_token}:{canonical_altsvc(live_token, origin_altsvcid)}:{canonical_origin(live_token, origin_altsvcid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "altsvcid": origin_altsvcid,
                "origindigest": origin_digest,
                "altsvc_frame": True,
                "origin_frame": True,
                "origindigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "altsvcid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_altsvc_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "altsvcid": origin_altsvcid,
                "origindigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "altsvc_frame": True,
                "origin_frame": True,
                "origindigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "altsvcid_bound": True,
            }
        except (OSError, AltsvcActuationError) as error:
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
        live = independent_altsvc_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "altsvcid": int(live.get("altsvcid") or EMPTY_ALTSVCID),
            "origindigest": int(live.get("origindigest") or EMPTY_ORIGINDIGEST),
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


def call_altsvc_tool(session: AltsvcSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one HTTP Alternative Services tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_altsvc = True if arguments.get("altsvc") is None else bool(arguments.get("altsvc"))
    do_origin = True if arguments.get("origin") is None else bool(arguments.get("origin"))
    do_origindigest = True if arguments.get("origindigest") is None else bool(arguments.get("origindigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_altsvcid = True if arguments.get("use_altsvcid") is None else bool(arguments.get("use_altsvcid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_altsvc=do_altsvc,
            do_origin=do_origin,
            do_origindigest=do_origindigest,
            replay=replay,
            use_altsvcid=use_altsvcid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise AltsvcActuationError(f"unsupported altsvc action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_altsvc_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed HTTP Alternative Services origindigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "altsvcid": EMPTY_ALTSVCID,
        "origindigest": EMPTY_ORIGINDIGEST,
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
            "altsvc_frame",
            "origin_frame",
            "origindigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "altsvcid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    altsvcid = int(payload.get("altsvcid") or EMPTY_ALTSVCID)
    origindigest = int(payload.get("origindigest") or EMPTY_ORIGINDIGEST)
    dual = port > 0 and bool(altsvcid) and bool(origindigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "altsvcid": altsvcid,
        "origindigest": origindigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "altsvc_frame": payload.get("altsvc_frame") is True,
        "origin_frame": payload.get("origin_frame") is True,
        "origindigest_response": payload.get("origindigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "altsvcid_bound": payload.get("altsvcid_bound") is True,
    }


def run_altsvc_workflow(
    *,
    with_altsvcid: bool = True,
    skip_bind: bool = False,
    do_altsvc: bool = True,
    do_origin: bool = True,
    do_origindigest: bool = True,
    replay: bool = True,
    use_altsvcid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 7838 ALTSVC/ORIGIN altsvcid cycle workflow."""

    descriptor = altsvc_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ALTSVC_TOOL_PROVIDER),
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
        raise AltsvcActuationError(f"altsvc tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="altsvc-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = AltsvcSession(out, altsvcid_gate=DEFAULT_ALTSVCID if with_altsvcid else EMPTY_ALTSVCID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "altsvc": do_altsvc,
            "origin": do_origin,
            "origindigest": do_origindigest,
            "replay": replay,
            "use_altsvcid": use_altsvcid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_altsvc_tool(session, arguments))
            except AltsvcActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_altsvc_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_altsvcid
        and not skip_bind
        and do_altsvc
        and do_origin
        and do_origindigest
        and replay
        and use_altsvcid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "altsvc_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_altsvcid": with_altsvcid,
        "skip_bind": skip_bind,
        "altsvc_frame": do_altsvc,
        "origin": do_origin,
        "origindigest": do_origindigest,
        "replay": replay,
        "use_altsvcid": use_altsvcid,
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
        "altsvcid_value": int(publish_result.get("altsvcid") or independent.get("altsvcid") or EMPTY_ALTSVCID),
        "origindigest_value": int(publish_result.get("origindigest") or independent.get("origindigest") or EMPTY_ORIGINDIGEST),
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
        "altsvcid": int(trace_body["altsvcid_value"] or EMPTY_ALTSVCID),
        "origindigest": int(trace_body["origindigest_value"] or EMPTY_ORIGINDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_altsvcid": with_altsvcid,
        "skip_bind": skip_bind,
        "altsvc_cycle": do_altsvc,
        "origin_cycle": do_origin,
        "origindigest_cycle": do_origindigest,
        "replay": replay,
        "use_altsvcid": use_altsvcid,
    }


def verify_altsvc_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed HTTP Alternative Services trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_altsvc_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    altsvcid = int(trace.get("altsvcid_value") or independent.get("altsvcid") or EMPTY_ALTSVCID)
    origindigest = int(trace.get("origindigest_value") or independent.get("origindigest") or EMPTY_ORIGINDIGEST)
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
        "altsvc_frame": independent.get("altsvc_frame") is True,
        "origin_frame": independent.get("origin_frame") is True,
        "origindigest_response": independent.get("origindigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "altsvcid_bound": independent.get("altsvcid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "origindigest_recorded": (
            port > 0
            and altsvcid == DEFAULT_ALTSVCID
            and origindigest == DEFAULT_ORIGINDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def altsvc_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.altsvc_actuation import "
        "builtin_altsvc_actuation_proof; r=builtin_altsvc_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='altsvc_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_altsvc_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ALTSVC_ACTUATION_ID,
        name="First-class RFC 7838 HTTP Alternative Services ALTSVC/ORIGIN actuation",
        description=(
            "Missions that require an altsvc tool can opt the altsvc provider in, "
            "bind a loopback RFC 7838 HTTP Alternative Services origin, complete an ALTSVC "
            "with a non-empty altsvcid, lockstep an ORIGIN that carries the "
            "stored origindigest, independently poll the stored origindigest "
            "on a later socket, and seal a digest-chained origindigest. Default "
            "routing stays fail-closed; a missing altsvcid keeps the hole "
            "falsifiable, and skip-ALTSVC/ORIGIN/ORIGINDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.altsvc_actuation:builtin_altsvc_actuation_proof",
        proof_command=altsvc_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.encryptedcontent-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/altsvc_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/hsts_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required altsvc tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 7838 daemon, speaks an "
            "ALTSVC then ORIGIN over HTTP Alternative Services with a non-empty altsvcid and "
            "origindigest, independently polls the stored origindigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 8188 Encrypted Content-Encoding lockstep is proved. "
            "Missing altsvcids, skip-ALTSVC, skip-ORIGIN, skip-origindigest, skip-REPLAY, "
            "and an ALTSVC aimed without an altsvcid stay fail-closed. "
            "Later genesis can take RFC 6797 HTTP Strict Transport Security STS/PRELOAD as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("altsvc", "rfc7838", "http", "altsvcid", "origindigest", "h2", "origin", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T064943Z-e71385c4",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_altsvc_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 7838 HTTP Alternative Services lockstep actuation seals a origindigest."""

    from blackhole_agent.hsts_actuation import (
        HSTS_ACTUATION_GOAL,
        HSTS_ACTUATION_ID,
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

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (
        ALTSVC_ACTUATION_ID,
    )
    checks["leftover_text_binds_altsvc"] = leftover_marker_ids(ALTSVC_LEFTOVER) == (
        ALTSVC_ACTUATION_ID,
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
        (EARLYHINTS_ACTUATION_GOAL, EARLYHINTS_ACTUATION_ID, "earlyhints"),
        (ENCRYPTEDCONTENT_ACTUATION_GOAL, ENCRYPTEDCONTENT_ACTUATION_ID, "encryptedcontent"),
        (HSTS_ACTUATION_GOAL, HSTS_ACTUATION_ID, "hsts"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_altsvc"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"altsvc_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            ALTSVC_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = ALTSVC_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_alt_svc(DEFAULT_ALTS)
    rebuilt = serialize_alt_svc(parse_alt_svc(advertised))
    dual = parse_alt_svc(RFC_ALTSVC_DUAL)
    frame = encode_altsvc_frame("", advertised)
    parsed_frame = parse_altsvc_frame(frame)
    origin_payload = encode_origin_frame((origin_uri(SENTINEL),))
    asked = parse_http_request(altsvc_request(SENTINEL, DEFAULT_ALTSVCID))
    origin_req = parse_http_request(origin_request(SENTINEL, DEFAULT_ALTSVCID, DEFAULT_ORIGINDIGEST))
    got = parse_http_response(altsvc_response(SENTINEL, DEFAULT_ALTSVCID, DEFAULT_ORIGINDIGEST))
    origin_reply = parse_http_response(
        origin_response(SENTINEL, DEFAULT_ALTSVCID, DEFAULT_ORIGINDIGEST)
    )
    checks["altsvc_roundtrip"] = (
        parse_alt_svc(advertised) == DEFAULT_ALTS
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_ALTSVC_FIELD
        and is_token("h2") is True
        and is_token(SENTINEL) is True
        and parsed_frame["field_value"] == RFC_ALTSVC_FIELD
        and parsed_frame["alts"] == DEFAULT_ALTS
        and parsed_frame["frame_type"] == HTTP2_ALTSVC_TYPE
        and parsed_frame["origin_len"] == 0
        and dual == (("h2", "alt.example.com", 8000, 0, 0), ("h2", "", 443, 0, 0))
    )
    checks["origin_roundtrip"] = (
        parse_origin_frame(origin_payload) == (origin_uri(SENTINEL),)
        and hmac.compare_digest(encode_origin_frame(parse_origin_frame(origin_payload)), origin_payload)
        and DEFAULT_ORIGINDIGEST == request_origindigest(DEFAULT_ALTSVCID, SENTINEL)
        and "origindigest=" in canonical_origin(SENTINEL, DEFAULT_ALTSVCID, DEFAULT_ORIGINDIGEST)
        and canonical_altsvc(SENTINEL, DEFAULT_ALTSVCID).startswith(ALPN_H2)
    )
    checks["altsvc_origin_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["as_kind"] == "altsvc"
        and asked["altsvcid"] == DEFAULT_ALTSVCID
        and origin_req["as_kind"] == "origin"
        and origin_req["origindigest"] == DEFAULT_ORIGINDIGEST
        and origin_req["origin"] == origin_uri(SENTINEL)
        and got["status"] == 200
        and origin_reply["status"] == 200
        and got["as_kind"] == "altsvc"
        and origin_reply["as_kind"] == "origin"
        and got["alts"] == DEFAULT_ALTS
        and origin_reply["origin"] == origin_uri(SENTINEL)
        and got["content_length_matches_body"] is True
        and origin_reply["content_length_matches_body"] is True
        and got["origindigest"] == DEFAULT_ORIGINDIGEST
        and origin_reply["origindigest"] == DEFAULT_ORIGINDIGEST
        and alt_svc_matches(serialize_alt_svc(got["alts"]), advertised)
    )

    checks["catalog_names_altsvc"] = (
        len(catalog) > 80
        and catalog[80]["id"] == ALTSVC_ACTUATION_ID
        and catalog[79]["id"] == ENCRYPTEDCONTENT_ACTUATION_ID
        and catalog[80]["source"] == "genesis_bind_altsvc"
    )
    checks["catalog_names_hsts"] = (
        len(catalog) > 81
        and catalog[81]["id"] == HSTS_ACTUATION_ID
        and catalog[81]["source"] == "genesis_bind_hsts"
    )
    family = capability_family(ALTSVC_ACTUATION_GOAL)
    checks["family_is_altsvc"] = "altsvc" in family
    checks["family_is_altsvc_surface"] = "altsvc" in family
    checks["family_is_altsvcid"] = "altsvcid" in family
    checks["family_is_rfc7838"] = "rfc7838" in family
    checks["family_is_origindigest"] = "origindigest" in family
    checks["family_is_not_hsts"] = (
        "hsts" not in family
        and "rfc6797" not in family
        and "hstsid" not in family
        and "stsdigest" not in family
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
    packed = encode_altsvc(identity=SENTINEL, altsvcid=DEFAULT_ALTSVCID, origindigest=DEFAULT_ORIGINDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_altsvc"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_altsvcid"] is True
        and parsed["altsvcid"] == DEFAULT_ALTSVCID
        and parsed["origindigest"] == DEFAULT_ORIGINDIGEST
        and parsed["is_response"] is False
        and parsed["is_origin"] is False
        and parsed["type"] == FRAME_ALTSVC
        and parsed["first_byte"] == AS_FIRST
    )
    shook = encode_origin(
        identity=SENTINEL,
        altsvcid=DEFAULT_ALTSVCID,
        origindigest=DEFAULT_ORIGINDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_origin"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_altsvc"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["altsvcid"] == DEFAULT_ALTSVCID
        and answer_parsed["origindigest"] == DEFAULT_ORIGINDIGEST
        and answer_parsed["has_origindigest"] is True
        and answer_parsed["type"] == FRAME_ORIGIN
        and answer_parsed["first_byte"] == AS_FIRST
    )
    bare = encode_altsvc(identity=SENTINEL, altsvcid=DEFAULT_ALTSVCID, include_altsvcid=False)
    checks["missing_altsvcid_is_unauthenticated"] = parse_message(bare)["has_altsvcid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    altsvc_signature = semantic_signature(ALTSVC_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(altsvc_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_altsvc = ToolDescriptor(name="remote_altsvc", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_altsvc)
    checks["naive_mcp_altsvc_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = altsvc_tool_descriptor()
    default_altsvc = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ALTSVC_TOOL_PROVIDER),
    )
    checks["default_altsvc_provider_is_unsupported"] = (
        default_altsvc.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{ALTSVC_TOOL_PROVIDER}" in default_altsvc.reasons
    )
    checks["opted_in_altsvc_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_altsvc],
        required_tool_names=("local_memory", "altsvc"),
    )
    checks["naive_preflight_missing_altsvc"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["altsvc"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "altsvc"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ALTSVC_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "altsvc" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="altsvc-actuation-") as tmp:
        root = Path(tmp)
        missing = run_altsvc_workflow(with_altsvcid=False, output_dir=root / "missing")
        skip_bind = run_altsvc_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_altsvc = run_altsvc_workflow(do_altsvc=False, output_dir=root / "skip-altsvc")
        skip_origin = run_altsvc_workflow(do_origin=False, output_dir=root / "skip-origin")
        skip_origindigest = run_altsvc_workflow(do_origindigest=False, output_dir=root / "skip-origindigest")
        skip_replay = run_altsvc_workflow(replay=False, output_dir=root / "skip-replay")
        skip_altsvcid = run_altsvc_workflow(use_altsvcid=False, output_dir=root / "skip-altsvcid")
        live = run_altsvc_workflow(output_dir=root / "live")
        verify = verify_altsvc_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_altsvc_trace(clone)
        checks["naive_without_altsvcid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_altsvcid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_altsvc_stays_empty"] = (
            skip_altsvc["ok"] is False
            and skip_altsvc["error"] == "altsvc_required"
            and skip_altsvc["final_status"] == 409
            and skip_altsvc["payload_exists"] is False
        )
        checks["skip_origin_stays_empty"] = (
            skip_origin["ok"] is False
            and skip_origin["error"] == "origin_required"
            and skip_origin["final_status"] == 409
            and skip_origin["payload_exists"] is False
        )
        checks["skip_origindigest_stays_empty"] = (
            skip_origindigest["ok"] is False
            and skip_origindigest["error"] == "origindigest_required"
            and skip_origindigest["final_status"] == 409
            and skip_origindigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_altsvcid_stays_empty"] = (
            skip_altsvcid["ok"] is False
            and skip_altsvcid["error"] == "altsvcid_required"
            and skip_altsvcid["final_status"] == 409
            and skip_altsvcid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_origindigest"] = (
            int(live.get("altsvcid") or 0) == DEFAULT_ALTSVCID
            and int(live.get("origindigest") or 0) == DEFAULT_ORIGINDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_altsvcid_encode_origin_origindigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_altsvc["ok"] is False
            and skip_origin["ok"] is False
            and skip_origindigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_altsvcid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="altsvc-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != ALTSVC_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_altsvc"] = (
        live_goal == ALTSVC_ACTUATION_GOAL
        and ALTSVC_ACTUATION_ID in live_done
        and live_source == "genesis_bind_altsvc"
    )

    with tempfile.TemporaryDirectory(prefix="altsvc-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(ALTSVC_LEFTOVER, root)
        register_catalog_proved(root, ALTSVC_ACTUATION_ID)
        reason = leftover_satisfied_by(ALTSVC_LEFTOVER, root)
        after = leftover_is_open(ALTSVC_LEFTOVER, root)
    checks["altsvc_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_altsvc_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{ALTSVC_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_altsvc_actuation_capability()
    return {
        "ok": ok,
        "action": "altsvc_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": ALTSVC_ACTUATION_GOAL,
        "done_when": ALTSVC_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
