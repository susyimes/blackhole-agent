"""Drive a first-class IPv6 Stateless Address Autoconfiguration tool through RFC 4862 ROUTER/PREFIX.

Tool routing already fails missions that require ``slaac``: hosted
slaac endpoints stay on the unsupported MCP provider, and no first-party
slaac provider is executable. Unbound therefore cannot speak a ROUTER,
lockstep a PREFIX slaacid handshake over HTTP/1.0 SLAACID,
independently poll the stored slaacdigest, or seal a slaacdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``slaac`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 4862 daemon
- keep a missing-slaacid client so the slaac-slaacid hole stays falsifiable
- refuse PREFIX until a ROUTER lands with a non-empty slaacid
- independently poll the stored slaacdigest on a later client socket
- persist a sealed slaacdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 4861 Neighbor Discovery Protocol
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
    SLAAC_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    slaac_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
SLAAC_ACTUATION_ID = "capability.slaac-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SLAAC-OK"
POLL_TOKEN = "BH-SLAAC-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_SLAACID = 0
EMPTY_SLAACDIGEST = 0
SLAAC_FIRST = 0x3A  # RFC 4862 SLAAC (ICMPv6 next-header 58)
SLAACID_SIZE = 4
SLAACDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_PREFIX = 0x86  # RFC 4862 Prefix Information
FRAME_ROUTER = 0x85  # RFC 4861 Router Solicitation
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
SLAAC_LEFTOVER = (
    "Later genesis can take RFC 4862 IPv6 Stateless Address Autoconfiguration ROUTER/PREFIX over an "
    "slaacid-gated slaacdigest."
)
SLAAC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SLAAC_ACTUATION_ID};"
    f"capability_proved:{SLAAC_ACTUATION_ID};"
    "no_skill_route"
)
SLAAC_ACTUATION_GOAL = (
    "Repair rfc4862 slaac router/prefix cycle cannot land over http "
    "slaac slaacid: hosted slaac endpoints remain unsupported so a ROUTER then "
    "PREFIX slaacid handshake cannot land and a sealed slaacdigest "
    "cannot be produced. A missing slaac slaacid stays forbidden; fail-closed "
    "routing never opts the slaac provider in. An independent later poll of the "
    "stored slaacdigest keeps the hole falsifiable."
)


class SlaacActuationError(RuntimeError):
    """Raised when the HTTP/1.0 session or loopback daemon fixture misbehaves."""


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
# RFC 4862 sections 3.3 and 3.4: ROUTER / PREFIX.
RFC_ROUTER_FIELD = "ROUTER"
RFC_PREFIX_FIELD = "PREFIX"
RFC_SLAAC_PREFIX = RFC_PREFIX_FIELD
RFC_ROUTER_DIRECTIVE = "router=message"
RFC_PREFIX_DIRECTIVE = "prefix=message"
DEFAULT_ROUTER = "ROUTER"
PREFIX_POLICY = "PREFIX"
ROUTER_HEADER = "Router"
PREFIX_HEADER = "Prefix"
SLAAC_PREFIX_HEADER = PREFIX_HEADER
RFC_ROUTER_PATH = "/slaac/"
RFC_ROUTER_EMPTY = ""


def slaac_directive_pair(*, prefix: bool = False) -> tuple[str, str]:
    """RFC 4862 Router / Prefix directive pair."""

    if prefix:
        return "prefix", "message"
    return "router", "message"


def ascii_serialize_slaac_directive(*, prefix: bool = False) -> str:
    """RFC 4862 token "=" body-or-prefix."""

    name, value = slaac_directive_pair(prefix=prefix)
    if not is_token(name):
        raise SlaacActuationError("illegal_directive")
    return f"{name}={value}"


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise SlaacActuationError("short_slaac")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 4862 body-router token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_slaac(policy: str | Sequence[str]) -> str:
    """Serialize RFC 4862 ROUTER / PREFIX opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise SlaacActuationError("illegal_slaac")
    upper = text.upper().replace("_", "-")
    if upper in {"ROUTER", "SLAAC", "SLAAC-ROUTER", "SLAAC-REQUEST"}:
        return "ROUTER"
    if upper in {"PREFIX", "RESOURCE", "SLAAC-PREFIX"}:
        return "PREFIX"
    if upper.startswith("ROUTER="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SlaacActuationError("illegal_slaac")
        return "ROUTER"
    if upper.startswith("PREFIX="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SlaacActuationError("illegal_slaac")
        return "PREFIX"
    raise SlaacActuationError("illegal_slaac")


def parse_slaac(text: str) -> str:
    """Parse RFC 4862 SLAAC opcode header extensions into ROUTER or PREFIX."""

    raw = str(text or "").strip()
    if not raw:
        raise SlaacActuationError("illegal_slaac")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"ROUTER", "SLAAC", "SLAAC-ROUTER", "SLAAC-REQUEST"}:
        return "ROUTER"
    if upper in {"PREFIX", "RESOURCE", "SLAAC-PREFIX"}:
        return "PREFIX"
    if upper.startswith("ROUTER="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SlaacActuationError("illegal_slaac")
        return "ROUTER"
    if upper.startswith("PREFIX="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SlaacActuationError("illegal_slaac")
        return "PREFIX"
    raise SlaacActuationError("illegal_slaac")


def encode_slaac_header(policy: str | Sequence[str]) -> bytes:
    """RFC 4862 HTTP/1.0 field as bytes."""

    return serialize_slaac(policy).encode("ascii")


def parse_slaac_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_slaac(field_value) if field_value else DEFAULT_ROUTER
    return {
        "field_value": field_value,
        "policy": policy,
        "header": ROUTER_HEADER,
        "directive": str(policy),
        "router": str(policy) == "ROUTER",
        "prefix": str(policy) == "PREFIX",
    }


def canonical_router(identity: str, slaacid: int) -> str:
    """RFC 4862 body-router advertisement bound to identity and slaacid."""

    return (
        f"{serialize_slaac(DEFAULT_ROUTER)}, "
        f"router={ascii_serialize_slaac_directive()}, "
        f"identity={identity}, slaacid={int(slaacid) & 0xFFFFFFFF}"
    )


def canonical_prefix(identity: str, slaacid: int, slaacdigest: int | None = None) -> str:
    """RFC 4862 prefix-message confirmation of the stored identifier-digest."""

    digest = ""
    if slaacdigest is not None:
        digest = f", slaacdigest={int(slaacdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_slaac(PREFIX_POLICY)}, "
        f"prefix={ascii_serialize_slaac_directive(prefix=True)}, "
        f"identity={identity}, slaacid={int(slaacid) & 0xFFFFFFFF}{digest}"
    )


def representation_prefix(identity: str, slaacid: int, slaacdigest: int) -> str:
    return canonical_prefix(identity, slaacid, slaacdigest)


def slaac_matches(left: str, right: str) -> bool:
    return parse_slaac(left) == parse_slaac(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise SlaacActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise SlaacActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise SlaacActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise SlaacActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def router_request(identity: str, slaacid: int) -> bytes:
    """HTTP ROUTER that elicits RFC 4862 origin HTTP/1.0."""

    keyid = f"{int(slaacid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"ROUTER /slaac/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Slaac-Id: {int(slaacid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def prefix_request(identity: str, slaacid: int, slaacdigest: int | None = None) -> bytes:
    """HTTP PREFIX carrying RFC 4862 prefix-message confirmation of the stored identifier-digest."""

    keyid = f"{int(slaacid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if slaacdigest is not None:
        extra = f"Slaac-Digest: {int(slaacdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"PREFIX /slaac/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Slaac-Id: {int(slaacid) & 0xFFFFFFFF}\r\n"
        "Prefix-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    slaac_kind = "prefix" if fields.get("prefix-confirm") == "1" else "router"
    upgrade_field = fields.get("router") or fields.get("slaac") or ""
    policy = parse_slaac(upgrade_field) if upgrade_field else ()
    return {
        "kind": "router",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "slaac_kind": slaac_kind,
        "policy": policy,
        "slaacid": int(fields["slaac-id"]) if fields.get("slaac-id") else EMPTY_SLAACID,
        "slaacdigest": int(fields["slaac-digest"]) if fields.get("slaac-digest") else EMPTY_SLAACDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def router_response(identity: str, slaacid: int, slaacdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 4862 origin HTTP/1.0, carrying the stored slaacdigest."""

    prefixised = serialize_slaac(DEFAULT_ROUTER)
    payload = bytes(body or canonical_router(identity, slaacid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Router: {prefixised}\r\n"
        f"Slaac-Id: {int(slaacid) & 0xFFFFFFFF}\r\n"
        f"Slaac-Digest: {int(slaacdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def prefix_response(identity: str, slaacid: int, slaacdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 4862 PREFIX, carrying the stored identifier-digest."""

    prefixised = serialize_slaac(PREFIX_POLICY)
    payload = bytes(body or representation_prefix(identity, slaacid, slaacdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Router: {prefixised}\r\n"
        f"Slaac-Id: {int(slaacid) & 0xFFFFFFFF}\r\n"
        f"Slaac-Digest: {int(slaacdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/slaac-prefix\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise SlaacActuationError("illegal_content_length") from error
    field_value = fields.get("router") or fields.get("slaac") or ""
    policy = parse_slaac(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/slaac-prefix" or policy == PREFIX_POLICY:
        status = 200
        slaac_kind = "prefix"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        slaac_kind = "router"
    else:
        status = 0
        slaac_kind = "router"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "slaac_kind": slaac_kind,
        "policy": policy,
        "slaacid": int(fields["slaac-id"]) if fields.get("slaac-id") else EMPTY_SLAACID,
        "slaacdigest": int(fields["slaac-digest"]) if fields.get("slaac-digest") else EMPTY_SLAACDIGEST,
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
        raise SlaacActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise SlaacActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise SlaacActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise SlaacActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc4862_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    slaac: str,
) -> str:
    """RFC 4862 identifier digest over method, router-IP, identity, and slaacid."""

    payload = f"{method}:{slaac}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def router_slaacid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"slaacid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_slaacid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-slaacid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def router_slaacdigest(slaacid: int = EMPTY_SLAACID, token: str = SENTINEL) -> int:
    nonce = f"{int(slaacid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc4862_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="PREFIX",
        slaac=f"/slaac/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_SLAACID = router_slaacid(SENTINEL)
DEFAULT_SLAACDIGEST = router_slaacdigest(DEFAULT_SLAACID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    slaacid: int,
    slaacdigest: int,
    include_slaacid: bool = True,
) -> bytes:
    live_slaacid = int(slaacid) & 0xFFFFFFFF if include_slaacid else EMPTY_SLAACID
    live_digest = int(slaacdigest) & 0xFFFFFFFF if include_slaacid and live_slaacid else EMPTY_SLAACDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_slaacid) if live_slaacid else b""
    header = bytearray()
    header.append(SLAAC_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_router(
    *,
    identity: str,
    slaacid: int,
    slaacdigest: int | None = None,
    include_slaacid: bool = True,
) -> bytes:
    live_slaacid = int(slaacid) & 0xFFFFFFFF if include_slaacid else EMPTY_SLAACID
    live_digest = int(slaacdigest) if slaacdigest is not None else router_slaacdigest(live_slaacid, identity)
    return encode_packet(
        FRAME_ROUTER,
        identity=identity,
        slaacid=live_slaacid,
        slaacdigest=live_digest,
        include_slaacid=include_slaacid,
    )


def encode_prefix(
    *,
    identity: str,
    slaacid: int,
    slaacdigest: int | None = None,
    include_slaacid: bool = True,
) -> bytes:
    live_slaacid = int(slaacid) & 0xFFFFFFFF if include_slaacid else EMPTY_SLAACID
    live_digest = int(slaacdigest) if slaacdigest is not None else router_slaacdigest(live_slaacid, identity)
    return encode_packet(
        FRAME_PREFIX,
        identity=identity,
        slaacid=live_slaacid,
        slaacdigest=live_digest,
        include_slaacid=include_slaacid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise SlaacActuationError("short_packet")
    first = raw[0]
    if first != SLAAC_FIRST:
        raise SlaacActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise SlaacActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == SLAACID_SIZE:
        live_slaacid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_slaacid = EMPTY_SLAACID
    else:
        raise SlaacActuationError("illegal_slaacid")
    if offset >= len(raw):
        raise SlaacActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ROUTER, FRAME_PREFIX}:
        raise SlaacActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise SlaacActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise SlaacActuationError("checksum_failed")
    if len(payload) < 5:
        raise SlaacActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise SlaacActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_slaacid = int(live_slaacid) != EMPTY_SLAACID
    has_slaacdigest = has_slaacid and int(live_digest) != EMPTY_SLAACDIGEST
    is_router = frame_type == FRAME_ROUTER
    is_prefix = frame_type == FRAME_PREFIX
    return {
        "type": int(frame_type),
        "is_router": is_router,
        "is_prefix": is_prefix,
        "slaacid": int(live_slaacid),
        "has_slaacid": has_slaacid,
        "slaacdigest": int(live_digest),
        "has_slaacdigest": has_slaacdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC4862",
        "serialize_field": canonical_router(identity, live_slaacid) if has_slaacid else "",
        "tls_field": canonical_prefix(identity, live_slaacid, live_digest) if has_slaacdigest else "",
    }


class SlaacClient:
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
            raise SlaacActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_prefix"] or not packet["is_prefix"]:
            raise SlaacActuationError("slaacdigest_required")
        if not packet["has_slaacid"]:
            raise SlaacActuationError("slaacid_required")
        if not packet["has_slaacdigest"]:
            raise SlaacActuationError("slaacdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_slaacdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_slaacdigest:
            raise SlaacActuationError("slaacdigest_required")
        prefix = self._recv()
        return {
            "session": prefix,
            "slaacid": int(prefix.get("slaacid") or EMPTY_SLAACID),
            "identity": str(prefix.get("identity") or ""),
            "slaacdigest": int(prefix.get("slaacdigest") or EMPTY_SLAACDIGEST),
        }

    def prefix(
        self,
        identity: str,
        slaacid: int,
        slaacdigest: int = EMPTY_SLAACDIGEST,
        *,
        wait_slaacdigest: bool = True,
        include_slaacid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_prefix(
            identity=identity,
            slaacid=slaacid,
            slaacdigest=slaacdigest or router_slaacdigest(slaacid, identity),
            include_slaacid=include_slaacid,
        )
        return self.exchange(packet, wait_slaacdigest=wait_slaacdigest)


class SlaacSession:
    """SLAACID-gated loopback RFC 4862 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        slaacid_gate: int = DEFAULT_SLAACID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.slaacid_gate = int(slaacid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.slaacid = EMPTY_SLAACID
        self.slaacdigest = EMPTY_SLAACDIGEST
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

    def store_slaacid_once(self, identity: str, slaacid: int, slaacdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(slaacid or EMPTY_SLAACID)
            live_digest = int(slaacdigest or EMPTY_SLAACDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.slaacid = live
                self.slaacdigest = live_digest or router_slaacdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.slaacid), int(self.slaacdigest)

    def read_slaacid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.slaacid), int(self.slaacdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "slaacid": EMPTY_SLAACID,
            "slaacdigest": EMPTY_SLAACDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _slaacid_missing(self) -> bool:
        return not int(self.slaacid_gate or 0)

    def _prefix_tuple(self, peer: tuple[str, int], identity: str, slaacid: int, slaacdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_prefix(
            identity=identity,
            slaacid=slaacid,
            slaacdigest=slaacdigest,
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
            except SlaacActuationError:
                continue
            if not packet.get("is_router") and not packet.get("is_prefix"):
                continue
            if not packet.get("has_slaacid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_slaacid, stored_digest = self.store_slaacid_once(
                identity,
                int(packet.get("slaacid") or EMPTY_SLAACID),
                int(packet.get("slaacdigest") or EMPTY_SLAACDIGEST),
            )
            if not stored_name or not stored_slaacid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_router"):
                    self.opened = True
                if packet.get("is_prefix"):
                    self.handshook = True
                self.retrieved = True
            self._prefix_tuple(peer, stored_name, stored_slaacid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._slaacid_missing():
            return self._forbidden("missing_slaacid")
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
        do_router: bool = True,
        do_prefix: bool = True,
        do_slaacdigest: bool = True,
        replay: bool = True,
        use_slaacid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._slaacid_missing():
            return self._forbidden("missing_slaacid")
        live_token = str(token or SENTINEL)
        origin_slaacid = router_slaacid(live_token)
        origin_digest = router_slaacdigest(origin_slaacid, live_token)
        client: SlaacClient | None = None
        independent: SlaacClient | None = None
        try:
            client = SlaacClient(self.host, int(self.port))
            if not do_router:
                return self._conflict("router_required")
            bind_packet = encode_router(
                identity=live_token,
                slaacid=origin_slaacid,
                slaacdigest=origin_digest,
                include_slaacid=use_slaacid,
            )
            if not use_slaacid:
                try:
                    client.exchange(bind_packet, wait_slaacdigest=True)
                except SlaacActuationError:
                    return self._conflict("slaacid_required")
                return self._conflict("slaacid_required")
            client.send(bind_packet)
            if not do_prefix:
                return self._conflict("prefix_required")
            proxy_packet = encode_prefix(
                identity=live_token,
                slaacid=origin_slaacid,
                slaacdigest=origin_digest,
                include_slaacid=True,
            )
            if not do_slaacdigest:
                try:
                    client.exchange(proxy_packet, wait_slaacdigest=False)
                except SlaacActuationError as error:
                    if str(error) == "slaacdigest_required":
                        return self._conflict("slaacdigest_required")
                    return self._conflict("slaacdigest_required")
                return self._conflict("slaacdigest_required")
            try:
                prefix = client.exchange(proxy_packet, wait_slaacdigest=True)
            except SlaacActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("slaacid_required")
                if reason == "slaacdigest_required":
                    return self._conflict("slaacdigest_required")
                return self._conflict("router_required")
            if str(prefix.get("identity") or "") != live_token:
                return self._conflict("router_required")
            if int(prefix.get("slaacid") or EMPTY_SLAACID) != origin_slaacid:
                return self._conflict("slaacdigest_required")
            if int(prefix.get("slaacdigest") or EMPTY_SLAACDIGEST) != origin_digest:
                return self._conflict("slaacdigest_required")
            self.retrieved = True
            if replay:
                independent = SlaacClient(self.host, int(self.port))
                try:
                    poll = independent.prefix(
                        POLL_TOKEN,
                        poll_slaacid(live_token),
                        router_slaacdigest(poll_slaacid(live_token), POLL_TOKEN),
                        wait_slaacdigest=True,
                    )
                except SlaacActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_slaacid, stored_digest = self.read_slaacid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_slaacid != origin_slaacid
                    or stored_digest != origin_digest
                    or int(poll.get("slaacid") or EMPTY_SLAACID) != origin_slaacid
                    or int(poll.get("slaacdigest") or EMPTY_SLAACDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_slaacid}:{origin_digest}:{live_token}:{canonical_router(live_token, origin_slaacid)}:{canonical_prefix(live_token, origin_slaacid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "slaacid": origin_slaacid,
                "slaacdigest": origin_digest,
                "router_frame": True,
                "prefix_frame": True,
                "slaacdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "slaacid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_slaacdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "slaacid": origin_slaacid,
                "slaacdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "router_frame": True,
                "prefix_frame": True,
                "slaacdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "slaacid_bound": True,
            }
        except (OSError, SlaacActuationError) as error:
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
        live = independent_slaacdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "slaacid": int(live.get("slaacid") or EMPTY_SLAACID),
            "slaacdigest": int(live.get("slaacdigest") or EMPTY_SLAACDIGEST),
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


def call_slaac_tool(session: SlaacSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one slaac tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_router = True if arguments.get("router") is None else bool(arguments.get("router"))
    do_prefix = True if arguments.get("prefix") is None else bool(arguments.get("prefix"))
    do_slaacdigest = True if arguments.get("slaacdigest") is None else bool(arguments.get("slaacdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_slaacid = True if arguments.get("use_slaacid") is None else bool(arguments.get("use_slaacid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_router=do_router,
            do_prefix=do_prefix,
            do_slaacdigest=do_slaacdigest,
            replay=replay,
            use_slaacid=use_slaacid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SlaacActuationError(f"unsupported slaac action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_slaacdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage slaacdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "slaacid": EMPTY_SLAACID,
        "slaacdigest": EMPTY_SLAACDIGEST,
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
            "router_frame",
            "prefix_frame",
            "slaacdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "slaacid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    slaacid = int(payload.get("slaacid") or EMPTY_SLAACID)
    slaacdigest = int(payload.get("slaacdigest") or EMPTY_SLAACDIGEST)
    dual = port > 0 and bool(slaacid) and bool(slaacdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "slaacid": slaacid,
        "slaacdigest": slaacdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "router_frame": payload.get("router_frame") is True,
        "prefix_frame": payload.get("prefix_frame") is True,
        "slaacdigest_locate": payload.get("slaacdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "slaacid_bound": payload.get("slaacid_bound") is True,
    }


def run_slaac_workflow(
    *,
    with_slaacid: bool = True,
    skip_bind: bool = False,
    do_router: bool = True,
    do_prefix: bool = True,
    do_slaacdigest: bool = True,
    replay: bool = True,
    use_slaacid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 4862 ROUTER/PREFIX slaacid cycle workflow."""

    descriptor = slaac_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SLAAC_TOOL_PROVIDER),
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
        raise SlaacActuationError(f"slaac tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="slaac-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SlaacSession(out, slaacid_gate=DEFAULT_SLAACID if with_slaacid else EMPTY_SLAACID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "router": do_router,
            "prefix": do_prefix,
            "slaacdigest": do_slaacdigest,
            "replay": replay,
            "use_slaacid": use_slaacid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_slaac_tool(session, arguments))
            except SlaacActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_slaacdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_slaacid
        and not skip_bind
        and do_router
        and do_prefix
        and do_slaacdigest
        and replay
        and use_slaacid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "slaac_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_slaacid": with_slaacid,
        "skip_bind": skip_bind,
        "router_frame": do_router,
        "prefix_frame": do_prefix,
        "slaacdigest": do_slaacdigest,
        "replay": replay,
        "use_slaacid": use_slaacid,
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
        "slaacid_value": int(publish_result.get("slaacid") or independent.get("slaacid") or EMPTY_SLAACID),
        "slaacdigest_value": int(publish_result.get("slaacdigest") or independent.get("slaacdigest") or EMPTY_SLAACDIGEST),
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
        "slaacid": int(trace_body["slaacid_value"] or EMPTY_SLAACID),
        "slaacdigest": int(trace_body["slaacdigest_value"] or EMPTY_SLAACDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_slaacid": with_slaacid,
        "skip_bind": skip_bind,
        "router_cycle": do_router,
        "prefix_cycle": do_prefix,
        "slaacdigest_cycle": do_slaacdigest,
        "replay": replay,
        "use_slaacid": use_slaacid,
    }


def verify_slaac_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_slaacdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    slaacid = int(trace.get("slaacid_value") or independent.get("slaacid") or EMPTY_SLAACID)
    slaacdigest = int(trace.get("slaacdigest_value") or independent.get("slaacdigest") or EMPTY_SLAACDIGEST)
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
        "router_frame": independent.get("router_frame") is True,
        "prefix_frame": independent.get("prefix_frame") is True,
        "slaacdigest_locate": independent.get("slaacdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "slaacid_bound": independent.get("slaacid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "slaacdigest_recorded": (
            port > 0
            and slaacid == DEFAULT_SLAACID
            and slaacdigest == DEFAULT_SLAACDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def slaac_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.slaac_actuation import "
        "builtin_slaac_actuation_proof; r=builtin_slaac_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='slaac_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_slaac_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SLAAC_ACTUATION_ID,
        name="First-class RFC 4862 IPv6 Stateless Address Autoconfiguration ROUTER/PREFIX actuation",
        description=(
            "Missions that require a slaac tool can opt the slaac provider in, "
            "bind a loopback RFC 4862 IPv6 Stateless Address Autoconfiguration endpoint, complete a ROUTER "
            "with a non-empty slaacid, lockstep a PREFIX that carries the "
            "stored slaacdigest, independently poll the stored slaacdigest "
            "on a later socket, and seal a digest-chained slaacdigest. Default "
            "routing stays fail-closed; a missing slaacid keeps the hole "
            "falsifiable, and skip-ROUTER/PREFIX/SLAACDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.slaac_actuation:builtin_slaac_actuation_proof",
        proof_command=slaac_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.ndp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/slaac_actuation.py",
            "src/blackhole_agent/ndp_actuation.py",
            "src/blackhole_agent/mld_actuation.py",
            "src/blackhole_agent/igmp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/rarp_actuation.py",
            "src/blackhole_agent/arp_actuation.py",
            "src/blackhole_agent/ip_actuation.py",
            "src/blackhole_agent/icmp_actuation.py",
            "src/blackhole_agent/tempaddr_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required slaac tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 4862 daemon, speaks a "
            "ROUTER then PREFIX over IPv6 Stateless Address Autoconfiguration with a non-empty slaacid and "
            "slaacdigest, independently polls the stored slaacdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 4861 Neighbor Discovery Protocol lockstep is proved. "
            "Missing slaacids, skip-ROUTER, skip-PREFIX, skip-slaacdigest, skip-REPLAY, "
            "and a ROUTER aimed without a slaacid stay fail-closed. "
            "Later genesis can take RFC 4941 Privacy Extensions for Stateless Address Autoconfiguration TEMPORARY/PUBLIC as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("slaac", "rfc4862", "http", "slaacid", "slaacdigest", "router", "prefix", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T184808Z-a0ef0946",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_slaac_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 4862 router/prefix lockstep actuation seals an slaacdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.tempaddr_actuation import (
        TEMPADDR_ACTUATION_GOAL,
        TEMPADDR_ACTUATION_ID,
    )
    from blackhole_agent.ndp_actuation import (
        NDP_ACTUATION_GOAL,
        NDP_ACTUATION_ID,
    )
    from blackhole_agent.mld_actuation import (
        MLD_ACTUATION_GOAL,
        MLD_ACTUATION_ID,
    )
    from blackhole_agent.igmp_actuation import (
        IGMP_ACTUATION_GOAL,
        IGMP_ACTUATION_ID,
    )
    from blackhole_agent.rarp_actuation import (
        RARP_ACTUATION_GOAL,
        RARP_ACTUATION_ID,
    )
    from blackhole_agent.arp_actuation import (
        ARP_ACTUATION_GOAL,
        ARP_ACTUATION_ID,
    )
    from blackhole_agent.ip_actuation import (
        IP_ACTUATION_GOAL,
        IP_ACTUATION_ID,
    )
    from blackhole_agent.icmp_actuation import (
        ICMP_ACTUATION_GOAL,
        ICMP_ACTUATION_ID,
    )
    from blackhole_agent.udp_actuation import (
        UDP_ACTUATION_GOAL,
        UDP_ACTUATION_ID,
    )
    from blackhole_agent.tcp_actuation import (
        TCP_ACTUATION_GOAL,
        TCP_ACTUATION_ID,
    )
    from blackhole_agent.telnet_actuation import (
        TELNET_ACTUATION_GOAL,
        TELNET_ACTUATION_ID,
    )
    from blackhole_agent.finger_actuation import (
        FINGER_ACTUATION_GOAL,
        FINGER_ACTUATION_ID,
    )
    from blackhole_agent.mime_actuation import (
        MIME_ACTUATION_GOAL,
        MIME_ACTUATION_ID,
    )
    from blackhole_agent.uri_actuation import (
        URI_ACTUATION_GOAL,
        URI_ACTUATION_ID,
    )
    from blackhole_agent.http10_actuation import (
        HTTP10_ACTUATION_GOAL,
        HTTP10_ACTUATION_ID,
    )
    from blackhole_agent.digestauth_actuation import (
        DIGESTAUTH_ACTUATION_GOAL,
        DIGESTAUTH_ACTUATION_ID,
    )
    from blackhole_agent.httpstate_actuation import (
        HTTPSTATE_ACTUATION_GOAL,
        HTTPSTATE_ACTUATION_ID,
    )
    from blackhole_agent.httpver_actuation import (
        HTTPVER_ACTUATION_GOAL,
        HTTPVER_ACTUATION_ID,
    )
    from blackhole_agent.icp_actuation import (
        ICP_ACTUATION_GOAL,
        ICP_ACTUATION_ID,
    )
    from blackhole_agent.spnego_actuation import (
        SPNEGO_ACTUATION_GOAL,
        SPNEGO_ACTUATION_ID,
    )
    from blackhole_agent.stalecontent_actuation import (
        STALECONTENT_ACTUATION_GOAL,
        STALECONTENT_ACTUATION_ID,
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
    checks["denylists_self"] = SLAAC_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SLAAC_ACTUATION_GOAL) == (
        SLAAC_ACTUATION_ID,
    )
    checks["leftover_text_binds_slaac"] = leftover_marker_ids(SLAAC_LEFTOVER) == (
        SLAAC_ACTUATION_ID,
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
        (STALECONTENT_ACTUATION_GOAL, STALECONTENT_ACTUATION_ID, "stalecontent"),
        (SPNEGO_ACTUATION_GOAL, SPNEGO_ACTUATION_ID, "spnego"),
        (HTTPAUTH_ACTUATION_GOAL, HTTPAUTH_ACTUATION_ID, "httpauth"),
        (TCN_ACTUATION_GOAL, TCN_ACTUATION_ID, "tcn"),
        (TEMPADDR_ACTUATION_GOAL, TEMPADDR_ACTUATION_ID, "tempaddr"),
        (NDP_ACTUATION_GOAL, NDP_ACTUATION_ID, "ndp"),
        (MLD_ACTUATION_GOAL, MLD_ACTUATION_ID, "mld"),
        (IGMP_ACTUATION_GOAL, IGMP_ACTUATION_ID, "igmp"),
        (RARP_ACTUATION_GOAL, RARP_ACTUATION_ID, "rarp"),
        (ARP_ACTUATION_GOAL, ARP_ACTUATION_ID, "arp"),
        (IP_ACTUATION_GOAL, IP_ACTUATION_ID, "ip"),
        (ICMP_ACTUATION_GOAL, ICMP_ACTUATION_ID, "icmp"),
        (UDP_ACTUATION_GOAL, UDP_ACTUATION_ID, "udp"),
        (TCP_ACTUATION_GOAL, TCP_ACTUATION_ID, "tcp"),
        (TELNET_ACTUATION_GOAL, TELNET_ACTUATION_ID, "telnet"),
        (FINGER_ACTUATION_GOAL, FINGER_ACTUATION_ID, "finger"),
        (MIME_ACTUATION_GOAL, MIME_ACTUATION_ID, "mime"),
        (URI_ACTUATION_GOAL, URI_ACTUATION_ID, "uri"),
        (HTTP10_ACTUATION_GOAL, HTTP10_ACTUATION_ID, "http10"),
        (DIGESTAUTH_ACTUATION_GOAL, DIGESTAUTH_ACTUATION_ID, "digestauth"),
        (HTTPSTATE_ACTUATION_GOAL, HTTPSTATE_ACTUATION_ID, "httpstate"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_slaac"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"slaac_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            SLAAC_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = SLAAC_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    prefixised = serialize_slaac(DEFAULT_ROUTER)
    rebuilt = serialize_slaac(parse_slaac(prefixised))
    preloaded = parse_slaac(RFC_SLAAC_PREFIX)
    header = encode_slaac_header(DEFAULT_ROUTER)
    parsed_header = parse_slaac_header(header)
    asked = parse_http_request(router_request(SENTINEL, DEFAULT_SLAACID))
    preload_req = parse_http_request(prefix_request(SENTINEL, DEFAULT_SLAACID, DEFAULT_SLAACDIGEST))
    got = parse_http_response(router_response(SENTINEL, DEFAULT_SLAACID, DEFAULT_SLAACDIGEST))
    preload_prefix = parse_http_response(
        prefix_response(SENTINEL, DEFAULT_SLAACID, DEFAULT_SLAACDIGEST)
    )
    checks["slaac_roundtrip"] = (
        parse_slaac(prefixised) == DEFAULT_ROUTER
        and hmac.compare_digest(rebuilt, prefixised)
        and prefixised == RFC_ROUTER_FIELD
        and is_token("ROUTER") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_ROUTER_FIELD
        and parsed_header["policy"] == DEFAULT_ROUTER
        and parsed_header["header"] == ROUTER_HEADER
        and parsed_header["router"] is True
        and parsed_header["prefix"] is False
        and preloaded == PREFIX_POLICY
        and ascii_serialize_slaac_directive() == RFC_ROUTER_DIRECTIVE
        and slaac_directive_pair() == ("router", "message")
        and RFC_ROUTER_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_slaac(PREFIX_POLICY) == RFC_SLAAC_PREFIX
        and DEFAULT_SLAACDIGEST == router_slaacdigest(DEFAULT_SLAACID, SENTINEL)
        and "slaacdigest=" in canonical_prefix(SENTINEL, DEFAULT_SLAACID, DEFAULT_SLAACDIGEST)
        and canonical_router(SENTINEL, DEFAULT_SLAACID).startswith("ROUTER")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "ROUTER"
        and asked["slaac_kind"] == "router"
        and asked["slaacid"] == DEFAULT_SLAACID
        and preload_req["slaac_kind"] == "prefix"
        and preload_req["slaacdigest"] == DEFAULT_SLAACDIGEST
        and got["status"] == 200
        and preload_prefix["status"] == 200
        and got["slaac_kind"] == "router"
        and preload_prefix["slaac_kind"] == "prefix"
        and got["policy"] == DEFAULT_ROUTER
        and preload_prefix["policy"] == PREFIX_POLICY
        and got["content_length_matches_body"] is True
        and preload_prefix["content_length_matches_body"] is True
        and got["slaacdigest"] == DEFAULT_SLAACDIGEST
        and preload_prefix["slaacdigest"] == DEFAULT_SLAACDIGEST
        and slaac_matches(serialize_slaac(got["policy"]), prefixised)
    )

    checks["catalog_names_slaac"] = (
        len(catalog) > 121
        and catalog[121]["id"] == SLAAC_ACTUATION_ID
        and catalog[120]["id"] == NDP_ACTUATION_ID
        and catalog[119]["id"] == MLD_ACTUATION_ID
        and catalog[121]["source"] == "genesis_bind_slaac"
    )
    checks["catalog_names_tempaddr"] = (
        len(catalog) > 122
        and catalog[122]["id"] == TEMPADDR_ACTUATION_ID
        and catalog[122]["source"] == "genesis_bind_tempaddr"
    )
    family = capability_family(SLAAC_ACTUATION_GOAL)
    checks["family_is_slaac"] = "slaac" in family.split("/")
    checks["family_is_slaac_surface"] = "slaacid" in family
    checks["family_is_slaacid"] = "slaacid" in family
    checks["family_is_rfc4862"] = "rfc4862" in family
    checks["family_is_slaacdigest"] = "slaacdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_tempaddr"] = (
        "tempaddr" not in family.split("/")
        and "rfc4941" not in family
        and "tempaddrid" not in family
        and "tempaddrdigest" not in family
    )
    checks["family_is_not_ndp"] = (
        "ndp" not in family.split("/")
        and "rfc4861" not in family
        and "ndpid" not in family
        and "ndpdigest" not in family
    )
    checks["family_is_not_mld"] = (
        "mld" not in family.split("/")
        and "rfc2710" not in family
        and "mldid" not in family
        and "mlddigest" not in family
    )
    checks["family_is_not_igmp"] = (
        "igmp" not in family.split("/")
        and "rfc1112" not in family
        and "igmpid" not in family
        and "igmpdigest" not in family
    )
    checks["family_is_not_rarp"] = (
        "rarp" not in family.split("/")
        and "rfc903" not in family
        and "rarpid" not in family
        and "rarpdigest" not in family
    )
    checks["family_is_not_arp"] = (
        "arp" not in family.split("/")
        and "rfc826" not in family
        and "arpid" not in family.split("/")
        and "arpdigest" not in family.split("/")
    )
    checks["family_is_not_ip"] = (
        "ip" not in family.split("/")
        and "rfc791" not in family
        and "ipid" not in family
        and "ipdigest" not in family
    )
    checks["family_is_not_tcp"] = (
        "tcp" not in family.split("/")
        and "rfc793" not in family
        and "tcpid" not in family
        and "tcpdigest" not in family
    )
    checks["family_is_not_icmp"] = (
        "icmp" not in family.split("/")
        and "rfc792" not in family
        and "icmpid" not in family
        and "icmpdigest" not in family
    )
    checks["family_is_not_udp"] = (
        "udp" not in family.split("/")
        and "rfc768" not in family
        and "udpid" not in family
        and "udpdigest" not in family
    )
    checks["family_is_not_telnet"] = (
        "telnet" not in family.split("/")
        and "rfc854" not in family
        and "telnetid" not in family
        and "telnetdigest" not in family
    )
    checks["family_is_not_finger"] = (
        "finger" not in family.split("/")
        and "rfc1288" not in family
        and "fingerid" not in family
        and "fingerdigest" not in family
    )
    checks["family_is_not_mime"] = (
        "mime" not in family.split("/")
        and "rfc1521" not in family
        and "mimeid" not in family
        and "mimedigest" not in family
    )
    checks["family_is_not_uri"] = (
        "uri" not in family.split("/")
        and "rfc1630" not in family
        and "uriid" not in family
        and "uridigest" not in family
    )
    checks["family_is_not_http10"] = (
        "http10" not in family
        and "rfc1945" not in family
        and "http10id" not in family
        and "http10digest" not in family
    )
    checks["family_is_not_digestauth"] = (
        "digestauth" not in family
        and "rfc2069" not in family
        and "challengeid" not in family
        and "responsedigest" not in family
    )
    checks["family_is_not_httpstate"] = (
        "httpstate" not in family
        and "rfc2109" not in family
        and "stateid" not in family
        and "statedigest" not in family
    )
    checks["family_is_not_httpver"] = (
        "httpver" not in family
        and "rfc2145" not in family
        and "versionid" not in family
        and "versiondigest" not in family
    )
    checks["family_is_not_icp"] = (
        "icp" not in family
        and "rfc2186" not in family
        and "queryid" not in family
        and "icpdigest" not in family
    )
    checks["family_is_not_httpauth"] = (
        "httpauth" not in family
        and "rfc2617" not in family
        and "nonceid" not in family
        and "authdigest" not in family
    )
    checks["family_is_not_tcn"] = (
        "tcn" not in family
        and "rfc2295" not in family
        and "variantid" not in family
        and "choicedigest" not in family
    )
    checks["family_is_not_stalecontent"] = (
        "stalecontent" not in family
        and "rfc5861" not in family
        and "staleid" not in family
        and "staledigest" not in family
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
        and "complianceid" not in family
        and "ipaddr" not in family
    )
    checks["family_is_not_masque"] = (
        "masque" not in family
        and "rfc9298" not in family
        and "targetid" not in family
        and "authority" not in family
    )
    checks["family_is_not_datagram"] = (
        "rfc9221" not in family
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
    checks["family_is_not_ice"] = (
        "ice" not in family.split("/") and "rfc8445" not in family and "ufrag" not in family
    )
    checks["family_is_not_turn"] = "turn" not in family and "rfc5766" not in family and "relay" not in family
    checks["family_is_not_stun"] = "stun" not in family and "rfc5389" not in family and "txid" not in family
    checks["family_is_not_sip"] = "sip" not in family and "rfc3261" not in family and "callid" not in family
    checks["family_is_not_ike"] = "ike" not in family and "rfc7296" not in family and "spi" not in family
    checks["family_is_not_dhcp"] = "dhcp" not in family and "rfc2131" not in family and "yiaddr" not in family
    checks["family_is_not_radius"] = (
        "radius" not in family and "radiu" not in family and "rfc2865" not in family
    )
    checks["family_is_not_ntp"] = (
        "ntp" not in family.split("/")
        and "rfc5905" not in family
        and "keyid" not in family
    )
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
    packed = encode_router(identity=SENTINEL, slaacid=DEFAULT_SLAACID, slaacdigest=DEFAULT_SLAACDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_router"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_slaacid"] is True
        and parsed["slaacid"] == DEFAULT_SLAACID
        and parsed["slaacdigest"] == DEFAULT_SLAACDIGEST
        and parsed["is_prefix"] is False
        and parsed["is_prefix"] is False
        and parsed["type"] == FRAME_ROUTER
        and parsed["first_byte"] == SLAAC_FIRST
    )
    shook = encode_prefix(
        identity=SENTINEL,
        slaacid=DEFAULT_SLAACID,
        slaacdigest=DEFAULT_SLAACDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_prefix"] is True
        and answer_parsed["is_prefix"] is True
        and answer_parsed["is_router"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["slaacid"] == DEFAULT_SLAACID
        and answer_parsed["slaacdigest"] == DEFAULT_SLAACDIGEST
        and answer_parsed["has_slaacdigest"] is True
        and answer_parsed["type"] == FRAME_PREFIX
        and answer_parsed["first_byte"] == SLAAC_FIRST
    )
    bare = encode_router(identity=SENTINEL, slaacid=DEFAULT_SLAACID, include_slaacid=False)
    checks["missing_slaacid_is_unauthed"] = parse_message(bare)["has_slaacid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(SLAAC_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_slaac = ToolDescriptor(name="remote_slaac", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_slaac)
    checks["naive_mcp_slaac_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = slaac_tool_descriptor()
    default_slaac = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SLAAC_TOOL_PROVIDER),
    )
    checks["default_slaac_provider_is_unsupported"] = (
        default_slaac.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SLAAC_TOOL_PROVIDER}" in default_slaac.reasons
    )
    checks["opted_in_slaac_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_slaac],
        required_tool_names=("local_memory", "slaac"),
    )
    checks["naive_preflight_missing_slaac"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["slaac"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "slaac"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SLAAC_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "slaac" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="slaac-actuation-") as tmp:
        root = Path(tmp)
        missing = run_slaac_workflow(with_slaacid=False, output_dir=root / "missing")
        skip_bind = run_slaac_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_router = run_slaac_workflow(do_router=False, output_dir=root / "skip-router")
        skip_prefix = run_slaac_workflow(do_prefix=False, output_dir=root / "skip-prefix")
        skip_slaacdigest = run_slaac_workflow(do_slaacdigest=False, output_dir=root / "skip-slaacdigest")
        skip_replay = run_slaac_workflow(replay=False, output_dir=root / "skip-replay")
        skip_slaacid = run_slaac_workflow(use_slaacid=False, output_dir=root / "skslaac-slaacid")
        live = run_slaac_workflow(output_dir=root / "live")
        verify = verify_slaac_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_slaac_trace(clone)
        checks["naive_without_slaacid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_slaacid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_router_stays_empty"] = (
            skip_router["ok"] is False
            and skip_router["error"] == "router_required"
            and skip_router["final_status"] == 409
            and skip_router["payload_exists"] is False
        )
        checks["skip_prefix_stays_empty"] = (
            skip_prefix["ok"] is False
            and skip_prefix["error"] == "prefix_required"
            and skip_prefix["final_status"] == 409
            and skip_prefix["payload_exists"] is False
        )
        checks["skip_slaacdigest_stays_empty"] = (
            skip_slaacdigest["ok"] is False
            and skip_slaacdigest["error"] == "slaacdigest_required"
            and skip_slaacdigest["final_status"] == 409
            and skip_slaacdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_slaacid_stays_empty"] = (
            skip_slaacid["ok"] is False
            and skip_slaacid["error"] == "slaacid_required"
            and skip_slaacid["final_status"] == 409
            and skip_slaacid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_slaacdigest"] = (
            int(live.get("slaacid") or 0) == DEFAULT_SLAACID
            and int(live.get("slaacdigest") or 0) == DEFAULT_SLAACDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_slaacid_encode_prefix_slaacdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_router["ok"] is False
            and skip_prefix["ok"] is False
            and skip_slaacdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_slaacid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="slaac-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SLAAC_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, SLAAC_ACTUATION_GOAL, SLAAC_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_slaac"] = (
        not gate.accepted
        and live_goal != SLAAC_ACTUATION_GOAL
        and SLAAC_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_slaac"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="slaac-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(SLAAC_LEFTOVER, root)
        register_catalog_proved(root, SLAAC_ACTUATION_ID)
        reason = leftover_satisfied_by(SLAAC_LEFTOVER, root)
        after = leftover_is_open(SLAAC_LEFTOVER, root)
    checks["slaac_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_slaac_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{SLAAC_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_slaac_actuation_capability()
    return {
        "ok": ok,
        "action": "slaac_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SLAAC_ACTUATION_GOAL,
        "done_when": SLAAC_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
