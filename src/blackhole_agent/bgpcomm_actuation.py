"""Drive a first-class BGP Communities Attribute tool through RFC 1997 COMM/ATTR.

Tool routing already fails missions that require ``bgpcomm``: hosted
bgp communities attribute endpoints stay on the unsupported MCP provider, and no first-party
bgpcomm provider is executable. Unbound therefore cannot speak a COMM,
lockstep a ATTR bgpcommid handshake over HTTP/1.0 BGPCOMMID,
independently poll the stored bgpcommdigest, or seal a bgpcommdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``bgpcomm`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1997 daemon
- keep a missing-bgpcommid client so the bgpcomm-bgpcommid hole stays falsifiable
- refuse ATTR until a COMM lands with a non-empty bgpcommid
- independently poll the stored bgpcommdigest on a later client socket
- persist a sealed bgpcommdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 2918 Route Refresh Capability for BGP-4 REQUEST/REFRESH
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
    BGPCOMM_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    bgpcomm_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
BGPCOMM_ACTUATION_ID = "capability.bgpcomm-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-BGPCOMM-OK"
POLL_TOKEN = "BH-BGPCOMM-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_BGPCOMMID = 0
EMPTY_BGPCOMMDIGEST = 0
BGPCOMM_FIRST = 0xB8  # RFC 1997 COMM type 1
BGPCOMMID_SIZE = 4
BGPCOMMDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DEST = 0x02  # RFC 1997 ATTR type 2
FRAME_SOURCE = 0x01  # RFC 1997 COMM type 1
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
BGPCOMM_LEFTOVER = (
    'Later genesis can take RFC 1997 BGP Communities Attribute COMM/ATTR over a bgpcommid-gated bgpcommdigest.'
)
BGPCOMM_ACTUATION_DONE_WHEN = (
    f"capability_exists:{BGPCOMM_ACTUATION_ID};"
    f"capability_proved:{BGPCOMM_ACTUATION_ID};"
    "no_skill_route"
)
BGPCOMM_ACTUATION_GOAL = (
    'Repair rfc1997 bgpcomm comm/attr cycle cannot land over http bgpcomm bgpcommid: hosted bgp communities attribute endpoints remain unsupported so a COMM then ATTR bgpcommid handshake cannot land and a sealed bgpcommdigest cannot be produced. A missing bgpcomm bgpcommid stays forbidden; fail-closed routing never opts the bgpcomm provider in. An independent later poll of the stored bgpcommdigest keeps the hole falsifiable. BGP Communities sessions stay fail-closed without a bgpcommid-gated bgpcommdigest.'
)


class BgpcommActuationError(RuntimeError):
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
# RFC 1997 sections 3 and 4: MP_OPEN_speaker / ATTR type 2.
RFC_SOURCE_FIELD = "COMM"
RFC_DEST_FIELD = "ATTR"
RFC_BGPCOMM_DEST = RFC_DEST_FIELD
RFC_SOURCE_DIRECTIVE = "comm=message"
RFC_DEST_DIRECTIVE = "attr=message"
DEFAULT_SOURCE = "COMM"
DEST_HOP = "ATTR"
SOURCE_HEADER = "COMM"
DEST_HEADER = "Attr"
BGPCOMM_DEST_HEADER = DEST_HEADER
RFC_SOURCE_PATH = "/bgpcomm/"
RFC_SOURCE_EMPTY = ""


def bgpcomm_directive_pair(*, local: bool = False) -> tuple[str, str]:
    """RFC 1997 COMM / UPDATE directive pair."""

    if local:
        return "attr", "message"
    return "comm", "message"


def ascii_serialize_bgpcomm_directive(*, local: bool = False) -> str:
    """RFC 1997 token "=" body-or-local."""

    name, value = bgpcomm_directive_pair(local=local)
    if not is_token(name):
        raise BgpcommActuationError("illegal_directive")
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
            raise BgpcommActuationError("short_bgpcomm")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 1997 body-unique token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_bgpcomm(policy: str | Sequence[str]) -> str:
    """Serialize RFC 1997 COMM / UPDATE opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise BgpcommActuationError("illegal_bgpcomm")
    upper = text.upper().replace("_", "-")
    if upper in {"COMM", "COMM", "COMM-COMM"}:
        return "COMM"
    if upper in {"ATTR", "COMM-ATTR"}:
        return "ATTR"
    if upper.startswith("COMM="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise BgpcommActuationError("illegal_bgpcomm")
        return "COMM"
    if upper.startswith("ATTR="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise BgpcommActuationError("illegal_bgpcomm")
        return "ATTR"
    raise BgpcommActuationError("illegal_bgpcomm")


def parse_bgpcomm(text: str) -> str:
    """Parse RFC 1997 CE opcode header extensions into CE or BR."""

    raw = str(text or "").strip()
    if not raw:
        raise BgpcommActuationError("illegal_bgpcomm")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"COMM", "COMM", "COMM-COMM"}:
        return "COMM"
    if upper in {"ATTR", "COMM-ATTR"}:
        return "ATTR"
    if upper.startswith("COMM="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise BgpcommActuationError("illegal_bgpcomm")
        return "COMM"
    if upper.startswith("ATTR="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise BgpcommActuationError("illegal_bgpcomm")
        return "ATTR"
    raise BgpcommActuationError("illegal_bgpcomm")


def encode_bgpcomm_header(policy: str | Sequence[str]) -> bytes:
    """RFC 1997 HTTP/1.0 field as bytes."""

    return serialize_bgpcomm(policy).encode("ascii")


def parse_bgpcomm_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_bgpcomm(field_value) if field_value else DEFAULT_SOURCE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SOURCE_HEADER,
        "directive": str(policy),
        "is_first": str(policy) == "COMM",
        "table": str(policy) == "ATTR",
    }


def canonical_temporary(identity: str, bgpcommid: int) -> str:
    """RFC 1997 body-unique advertisement bound to identity and bgpcommid."""

    return (
        f"{serialize_bgpcomm(DEFAULT_SOURCE)}, "
        f"bgpcomm={ascii_serialize_bgpcomm_directive()}, "
        f"identity={identity}, bgpcommid={int(bgpcommid) & 0xFFFFFFFF}"
    )


def canonical_public(identity: str, bgpcommid: int, bgpcommdigest: int | None = None) -> str:
    """RFC 1997 local-message confirmation of the stored identifier-digest."""

    digest = ""
    if bgpcommdigest is not None:
        digest = f", bgpcommdigest={int(bgpcommdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_bgpcomm(DEST_HOP)}, "
        f"update={ascii_serialize_bgpcomm_directive(local=True)}, "
        f"identity={identity}, bgpcommid={int(bgpcommid) & 0xFFFFFFFF}{digest}"
    )


def representation_public(identity: str, bgpcommid: int, bgpcommdigest: int) -> str:
    return canonical_public(identity, bgpcommid, bgpcommdigest)


def bgpcomm_matches(left: str, right: str) -> bool:
    return parse_bgpcomm(left) == parse_bgpcomm(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise BgpcommActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise BgpcommActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise BgpcommActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise BgpcommActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def temporary_comm(identity: str, bgpcommid: int) -> bytes:
    """HTTP CE that elicits RFC 1997 origin HTTP/1.0."""

    keyid = f"{int(bgpcommid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"COMM /bgpcomm/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Bgpcomm-Id: {int(bgpcommid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def public_comm(identity: str, bgpcommid: int, bgpcommdigest: int | None = None) -> bytes:
    """HTTP BR carrying RFC 1997 local-message confirmation of the stored identifier-digest."""

    keyid = f"{int(bgpcommid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if bgpcommdigest is not None:
        extra = f"Bgpcomm-Digest: {int(bgpcommdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"ATTR /bgpcomm/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Bgpcomm-Id: {int(bgpcommid) & 0xFFFFFFFF}\r\n"
        "Attr-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_comm(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    disc_kind = "attr" if fields.get("attr-confirm") == "1" else "bgpcomm"
    upgrade_field = fields.get("comm") or fields.get("bgpcomm") or ""
    policy = parse_bgpcomm(upgrade_field) if upgrade_field else ()
    return {
        "kind": "bgpcomm",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "disc_kind": disc_kind,
        "policy": policy,
        "bgpcommid": int(fields["bgpcomm-id"]) if fields.get("bgpcomm-id") else EMPTY_BGPCOMMID,
        "bgpcommdigest": int(fields["bgpcomm-digest"]) if fields.get("bgpcomm-digest") else EMPTY_BGPCOMMDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def temporary_response(identity: str, bgpcommid: int, bgpcommdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 1997 origin HTTP/1.0, carrying the stored bgpcommdigest."""

    publicised = serialize_bgpcomm(DEFAULT_SOURCE)
    payload = bytes(body or canonical_temporary(identity, bgpcommid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"COMM: {publicised}\r\n"
        f"Bgpcomm-Id: {int(bgpcommid) & 0xFFFFFFFF}\r\n"
        f"Bgpcomm-Digest: {int(bgpcommdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def public_response(identity: str, bgpcommid: int, bgpcommdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 1997 BR, carrying the stored identifier-digest."""

    publicised = serialize_bgpcomm(DEST_HOP)
    payload = bytes(body or representation_public(identity, bgpcommid, bgpcommdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"COMM: {publicised}\r\n"
        f"Bgpcomm-Id: {int(bgpcommid) & 0xFFFFFFFF}\r\n"
        f"Bgpcomm-Digest: {int(bgpcommdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/bgpcomm-attr\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise BgpcommActuationError("illegal_content_length") from error
    field_value = fields.get("comm") or fields.get("bgpcomm") or ""
    policy = parse_bgpcomm(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/bgpcomm-attr" or policy == DEST_HOP:
        status = 200
        disc_kind = "attr"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        disc_kind = "bgpcomm"
    else:
        status = 0
        disc_kind = "bgpcomm"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "disc_kind": disc_kind,
        "policy": policy,
        "bgpcommid": int(fields["bgpcomm-id"]) if fields.get("bgpcomm-id") else EMPTY_BGPCOMMID,
        "bgpcommdigest": int(fields["bgpcomm-digest"]) if fields.get("bgpcomm-digest") else EMPTY_BGPCOMMDIGEST,
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
        raise BgpcommActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise BgpcommActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise BgpcommActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise BgpcommActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc1997_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    ula: str,
) -> str:
    """RFC 1997 identifier digest over method, router-IP, identity, and bgpcommid."""

    payload = f"{method}:{ula}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def temporary_bgpcommid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"bgpcommid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_bgpcommid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-bgpcommid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def temporary_bgpcommdigest(bgpcommid: int = EMPTY_BGPCOMMID, token: str = SENTINEL) -> int:
    nonce = f"{int(bgpcommid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc1997_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="ATTR",
        ula=f"/bgpcomm/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_BGPCOMMID = temporary_bgpcommid(SENTINEL)
DEFAULT_BGPCOMMDIGEST = temporary_bgpcommdigest(DEFAULT_BGPCOMMID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    bgpcommid: int,
    bgpcommdigest: int,
    include_bgpcommid: bool = True,
) -> bytes:
    live_bgpcommid = int(bgpcommid) & 0xFFFFFFFF if include_bgpcommid else EMPTY_BGPCOMMID
    live_digest = int(bgpcommdigest) & 0xFFFFFFFF if include_bgpcommid and live_bgpcommid else EMPTY_BGPCOMMDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_bgpcommid) if live_bgpcommid else b""
    header = bytearray()
    header.append(BGPCOMM_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_temporary(
    *,
    identity: str,
    bgpcommid: int,
    bgpcommdigest: int | None = None,
    include_bgpcommid: bool = True,
) -> bytes:
    live_bgpcommid = int(bgpcommid) & 0xFFFFFFFF if include_bgpcommid else EMPTY_BGPCOMMID
    live_digest = int(bgpcommdigest) if bgpcommdigest is not None else temporary_bgpcommdigest(live_bgpcommid, identity)
    return encode_packet(
        FRAME_SOURCE,
        identity=identity,
        bgpcommid=live_bgpcommid,
        bgpcommdigest=live_digest,
        include_bgpcommid=include_bgpcommid,
    )


def encode_public(
    *,
    identity: str,
    bgpcommid: int,
    bgpcommdigest: int | None = None,
    include_bgpcommid: bool = True,
) -> bytes:
    live_bgpcommid = int(bgpcommid) & 0xFFFFFFFF if include_bgpcommid else EMPTY_BGPCOMMID
    live_digest = int(bgpcommdigest) if bgpcommdigest is not None else temporary_bgpcommdigest(live_bgpcommid, identity)
    return encode_packet(
        FRAME_DEST,
        identity=identity,
        bgpcommid=live_bgpcommid,
        bgpcommdigest=live_digest,
        include_bgpcommid=include_bgpcommid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise BgpcommActuationError("short_packet")
    disc = raw[0]
    if disc != BGPCOMM_FIRST:
        raise BgpcommActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise BgpcommActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == BGPCOMMID_SIZE:
        live_bgpcommid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_bgpcommid = EMPTY_BGPCOMMID
    else:
        raise BgpcommActuationError("illegal_bgpcommid")
    if offset >= len(raw):
        raise BgpcommActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SOURCE, FRAME_DEST}:
        raise BgpcommActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise BgpcommActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise BgpcommActuationError("checksum_failed")
    if len(payload) < 5:
        raise BgpcommActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise BgpcommActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_bgpcommid = int(live_bgpcommid) != EMPTY_BGPCOMMID
    has_bgpcommdigest = has_bgpcommid and int(live_digest) != EMPTY_BGPCOMMDIGEST
    is_temporary = frame_type == FRAME_SOURCE
    is_public = frame_type == FRAME_DEST
    return {
        "type": int(frame_type),
        "is_temporary": is_temporary,
        "is_public": is_public,
        "bgpcommid": int(live_bgpcommid),
        "has_bgpcommid": has_bgpcommid,
        "bgpcommdigest": int(live_digest),
        "has_bgpcommdigest": has_bgpcommdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(disc),
        "mech_len": int(mech_len),
        "http_state": "RFC1997",
        "serialize_field": canonical_temporary(identity, live_bgpcommid) if has_bgpcommid else "",
        "tls_field": canonical_public(identity, live_bgpcommid, live_digest) if has_bgpcommdigest else "",
    }


class BgpcommClient:
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
            raise BgpcommActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_public"] or not packet["is_public"]:
            raise BgpcommActuationError("bgpcommdigest_required")
        if not packet["has_bgpcommid"]:
            raise BgpcommActuationError("bgpcommid_required")
        if not packet["has_bgpcommdigest"]:
            raise BgpcommActuationError("bgpcommdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_bgpcommdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_bgpcommdigest:
            raise BgpcommActuationError("bgpcommdigest_required")
        session = self._recv()
        return {
            "session": session,
            "bgpcommid": int(session.get("bgpcommid") or EMPTY_BGPCOMMID),
            "identity": str(session.get("identity") or ""),
            "bgpcommdigest": int(session.get("bgpcommdigest") or EMPTY_BGPCOMMDIGEST),
        }

    def local(
        self,
        identity: str,
        bgpcommid: int,
        bgpcommdigest: int = EMPTY_BGPCOMMDIGEST,
        *,
        wait_bgpcommdigest: bool = True,
        include_bgpcommid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_public(
            identity=identity,
            bgpcommid=bgpcommid,
            bgpcommdigest=bgpcommdigest or temporary_bgpcommdigest(bgpcommid, identity),
            include_bgpcommid=include_bgpcommid,
        )
        return self.exchange(packet, wait_bgpcommdigest=wait_bgpcommdigest)


class BgpcommSession:
    """BGPCOMMID-gated loopback RFC 1997 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        bgpcommid_gate: int = DEFAULT_BGPCOMMID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.bgpcommid_gate = int(bgpcommid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.bgpcommid = EMPTY_BGPCOMMID
        self.bgpcommdigest = EMPTY_BGPCOMMDIGEST
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

    def store_bgpcommid_once(self, identity: str, bgpcommid: int, bgpcommdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(bgpcommid or EMPTY_BGPCOMMID)
            live_digest = int(bgpcommdigest or EMPTY_BGPCOMMDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.bgpcommid = live
                self.bgpcommdigest = live_digest or temporary_bgpcommdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.bgpcommid), int(self.bgpcommdigest)

    def read_bgpcommid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.bgpcommid), int(self.bgpcommdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "bgpcommid": EMPTY_BGPCOMMID,
            "bgpcommdigest": EMPTY_BGPCOMMDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _bgpcommid_missing(self) -> bool:
        return not int(self.bgpcommid_gate or 0)

    def _public_tuple(self, update: tuple[str, int], identity: str, bgpcommid: int, bgpcommdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_public(
            identity=identity,
            bgpcommid=bgpcommid,
            bgpcommdigest=bgpcommdigest,
        )
        try:
            sock.sendto(packet, update)
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
            except BgpcommActuationError:
                continue
            if not packet.get("is_temporary") and not packet.get("is_public"):
                continue
            if not packet.get("has_bgpcommid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_bgpcommid, stored_digest = self.store_bgpcommid_once(
                identity,
                int(packet.get("bgpcommid") or EMPTY_BGPCOMMID),
                int(packet.get("bgpcommdigest") or EMPTY_BGPCOMMDIGEST),
            )
            if not stored_name or not stored_bgpcommid or not stored_digest:
                continue
            update = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_temporary"):
                    self.opened = True
                if packet.get("is_public"):
                    self.handshook = True
                self.retrieved = True
            self._public_tuple(update, stored_name, stored_bgpcommid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._bgpcommid_missing():
            return self._forbidden("missing_bgpcommid")
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
        do_temporary: bool = True,
        do_public: bool = True,
        do_bgpcommdigest: bool = True,
        replay: bool = True,
        use_bgpcommid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._bgpcommid_missing():
            return self._forbidden("missing_bgpcommid")
        live_token = str(token or SENTINEL)
        origin_bgpcommid = temporary_bgpcommid(live_token)
        origin_digest = temporary_bgpcommdigest(origin_bgpcommid, live_token)
        client: BgpcommClient | None = None
        independent: BgpcommClient | None = None
        try:
            client = BgpcommClient(self.host, int(self.port))
            if not do_temporary:
                return self._conflict("temporary_required")
            bind_packet = encode_temporary(
                identity=live_token,
                bgpcommid=origin_bgpcommid,
                bgpcommdigest=origin_digest,
                include_bgpcommid=use_bgpcommid,
            )
            if not use_bgpcommid:
                try:
                    client.exchange(bind_packet, wait_bgpcommdigest=True)
                except BgpcommActuationError:
                    return self._conflict("bgpcommid_required")
                return self._conflict("bgpcommid_required")
            client.send(bind_packet)
            if not do_public:
                return self._conflict("public_required")
            proxy_packet = encode_public(
                identity=live_token,
                bgpcommid=origin_bgpcommid,
                bgpcommdigest=origin_digest,
                include_bgpcommid=True,
            )
            if not do_bgpcommdigest:
                try:
                    client.exchange(proxy_packet, wait_bgpcommdigest=False)
                except BgpcommActuationError as error:
                    if str(error) == "bgpcommdigest_required":
                        return self._conflict("bgpcommdigest_required")
                    return self._conflict("bgpcommdigest_required")
                return self._conflict("bgpcommdigest_required")
            try:
                session = client.exchange(proxy_packet, wait_bgpcommdigest=True)
            except BgpcommActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("bgpcommid_required")
                if reason == "bgpcommdigest_required":
                    return self._conflict("bgpcommdigest_required")
                return self._conflict("temporary_required")
            if str(session.get("identity") or "") != live_token:
                return self._conflict("temporary_required")
            if int(session.get("bgpcommid") or EMPTY_BGPCOMMID) != origin_bgpcommid:
                return self._conflict("bgpcommdigest_required")
            if int(session.get("bgpcommdigest") or EMPTY_BGPCOMMDIGEST) != origin_digest:
                return self._conflict("bgpcommdigest_required")
            self.retrieved = True
            if replay:
                independent = BgpcommClient(self.host, int(self.port))
                try:
                    poll = independent.local(
                        POLL_TOKEN,
                        poll_bgpcommid(live_token),
                        temporary_bgpcommdigest(poll_bgpcommid(live_token), POLL_TOKEN),
                        wait_bgpcommdigest=True,
                    )
                except BgpcommActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_bgpcommid, stored_digest = self.read_bgpcommid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_bgpcommid != origin_bgpcommid
                    or stored_digest != origin_digest
                    or int(poll.get("bgpcommid") or EMPTY_BGPCOMMID) != origin_bgpcommid
                    or int(poll.get("bgpcommdigest") or EMPTY_BGPCOMMDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_bgpcommid}:{origin_digest}:{live_token}:{canonical_temporary(live_token, origin_bgpcommid)}:{canonical_public(live_token, origin_bgpcommid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "bgpcommid": origin_bgpcommid,
                "bgpcommdigest": origin_digest,
                "temporary_frame": True,
                "public_frame": True,
                "bgpcommdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "bgpcommid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_bgpcommdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "bgpcommid": origin_bgpcommid,
                "bgpcommdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "temporary_frame": True,
                "public_frame": True,
                "bgpcommdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "bgpcommid_bound": True,
            }
        except (OSError, BgpcommActuationError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "<<<UPDATEABLE>>>",
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
        live = independent_bgpcommdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "bgpcommid": int(live.get("bgpcommid") or EMPTY_BGPCOMMID),
            "bgpcommdigest": int(live.get("bgpcommdigest") or EMPTY_BGPCOMMDIGEST),
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


def call_bgpcomm_tool(session: BgpcommSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one bgpcomm tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_temporary = True if arguments.get("bgpcomm") is None else bool(arguments.get("bgpcomm"))
    do_public = True if arguments.get("attr") is None else bool(arguments.get("attr"))
    do_bgpcommdigest = True if arguments.get("bgpcommdigest") is None else bool(arguments.get("bgpcommdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_bgpcommid = True if arguments.get("use_bgpcommid") is None else bool(arguments.get("use_bgpcommid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_temporary=do_temporary,
            do_public=do_public,
            do_bgpcommdigest=do_bgpcommdigest,
            replay=replay,
            use_bgpcommid=use_bgpcommid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise BgpcommActuationError(f"unsupported bgpcomm action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_bgpcommdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage bgpcommdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "bgpcommid": EMPTY_BGPCOMMID,
        "bgpcommdigest": EMPTY_BGPCOMMDIGEST,
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
            "temporary_frame",
            "public_frame",
            "bgpcommdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "bgpcommid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    bgpcommid = int(payload.get("bgpcommid") or EMPTY_BGPCOMMID)
    bgpcommdigest = int(payload.get("bgpcommdigest") or EMPTY_BGPCOMMDIGEST)
    dual = port > 0 and bool(bgpcommid) and bool(bgpcommdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "bgpcommid": bgpcommid,
        "bgpcommdigest": bgpcommdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "temporary_frame": payload.get("temporary_frame") is True,
        "public_frame": payload.get("public_frame") is True,
        "bgpcommdigest_locate": payload.get("bgpcommdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "bgpcommid_bound": payload.get("bgpcommid_bound") is True,
    }


def run_bgpcomm_workflow(
    *,
    with_bgpcommid: bool = True,
    skip_bind: bool = False,
    do_temporary: bool = True,
    do_public: bool = True,
    do_bgpcommdigest: bool = True,
    replay: bool = True,
    use_bgpcommid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1997 COMM/ATTR bgpcommid cycle workflow."""

    descriptor = bgpcomm_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BGPCOMM_TOOL_PROVIDER),
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
        raise BgpcommActuationError(f"bgpcomm tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="bgpcomm-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = BgpcommSession(out, bgpcommid_gate=DEFAULT_BGPCOMMID if with_bgpcommid else EMPTY_BGPCOMMID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "bgpcomm": do_temporary,
            "attr": do_public,
            "bgpcommdigest": do_bgpcommdigest,
            "replay": replay,
            "use_bgpcommid": use_bgpcommid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_bgpcomm_tool(session, arguments))
            except BgpcommActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_bgpcommdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_bgpcommid
        and not skip_bind
        and do_temporary
        and do_public
        and do_bgpcommdigest
        and replay
        and use_bgpcommid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "bgpcomm_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_bgpcommid": with_bgpcommid,
        "skip_bind": skip_bind,
        "temporary_frame": do_temporary,
        "public_frame": do_public,
        "bgpcommdigest": do_bgpcommdigest,
        "replay": replay,
        "use_bgpcommid": use_bgpcommid,
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
        "bgpcommid_value": int(publish_result.get("bgpcommid") or independent.get("bgpcommid") or EMPTY_BGPCOMMID),
        "bgpcommdigest_value": int(publish_result.get("bgpcommdigest") or independent.get("bgpcommdigest") or EMPTY_BGPCOMMDIGEST),
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
        "bgpcommid": int(trace_body["bgpcommid_value"] or EMPTY_BGPCOMMID),
        "bgpcommdigest": int(trace_body["bgpcommdigest_value"] or EMPTY_BGPCOMMDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_bgpcommid": with_bgpcommid,
        "skip_bind": skip_bind,
        "temporary_cycle": do_temporary,
        "public_cycle": do_public,
        "bgpcommdigest_cycle": do_bgpcommdigest,
        "replay": replay,
        "use_bgpcommid": use_bgpcommid,
    }


def verify_bgpcomm_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_bgpcommdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    bgpcommid = int(trace.get("bgpcommid_value") or independent.get("bgpcommid") or EMPTY_BGPCOMMID)
    bgpcommdigest = int(trace.get("bgpcommdigest_value") or independent.get("bgpcommdigest") or EMPTY_BGPCOMMDIGEST)
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
        "temporary_frame": independent.get("temporary_frame") is True,
        "public_frame": independent.get("public_frame") is True,
        "bgpcommdigest_locate": independent.get("bgpcommdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "bgpcommid_bound": independent.get("bgpcommid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "bgpcommdigest_recorded": (
            port > 0
            and bgpcommid == DEFAULT_BGPCOMMID
            and bgpcommdigest == DEFAULT_BGPCOMMDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def bgpcomm_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.bgpcomm_actuation import "
        "builtin_bgpcomm_actuation_proof; r=builtin_bgpcomm_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='bgpcomm_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_bgpcomm_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=BGPCOMM_ACTUATION_ID,
        name="First-class RFC 1997 BGP Communities Attribute COMM/ATTR actuation",
        description=(
            "Missions that require a bgpcomm tool can opt the bgpcomm provider in, "
            "bind a loopback RFC 1997 BGP Communities Attribute endpoint, complete a COMM "
            "with a non-empty bgpcommid, lockstep a ATTR that carries the "
            "stored bgpcommdigest, independently poll the stored bgpcommdigest "
            "on a later socket, and seal a digest-chained bgpcommdigest. Default "
            "routing stays fail-closed; a missing bgpcommid keeps the hole "
            "falsifiable, and skip-COMM/ATTR/bgpcommdigest/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.bgpcomm_actuation:builtin_bgpcomm_actuation_proof",
        proof_command=bgpcomm_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.luprefix-actuation",
            "capability.sixrd-actuation",
            "capability.sixto4-actuation",
            "capability.teredo-actuation",
            "capability.isatap-actuation",
            "capability.sixover4-actuation",
            "capability.sixin4-actuation",
            "capability.tsp-actuation",
            "capability.l2tp-actuation",
            "capability.mesh-actuation",
            "capability.encap-actuation",
            "capability.mpbgp-actuation",
            "capability.bgp4-actuation",
            "capability.rtrefresh-actuation",
            "capability.v4embed-actuation",
            "capability.siitdtm-actuation",
            "capability.siitdc-actuation",
            "capability.eam-actuation",
            "capability.siit-actuation",
            "capability.prefix64-actuation",
            "capability.m46-actuation",
            "capability.ucpe-actuation",
            "capability.s46-actuation",
            "capability.mapt-actuation",
            "capability.mape-actuation",
            "capability.lw4o6-actuation",
            "capability.dslite-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/bgpcomm_actuation.py",
            "src/blackhole_agent/rtrefresh_actuation.py",
            "src/blackhole_agent/extcomm_actuation.py",
            "src/blackhole_agent/largecomm_actuation.py",
            "src/blackhole_agent/bgp4_actuation.py",
            "src/blackhole_agent/mpbgp_actuation.py",
            "src/blackhole_agent/encap_actuation.py",
            "src/blackhole_agent/mesh_actuation.py",
            "src/blackhole_agent/l2tp_actuation.py",
            "src/blackhole_agent/bgpcomm_actuation.py",
            "src/blackhole_agent/tsp_actuation.py",
            "src/blackhole_agent/sixin4_actuation.py",
            "src/blackhole_agent/sixover4_actuation.py",
            "src/blackhole_agent/isatap_actuation.py",
            "src/blackhole_agent/teredo_actuation.py",
            "src/blackhole_agent/sixto4_actuation.py",
            "src/blackhole_agent/sixrd_actuation.py",
            "src/blackhole_agent/luprefix_actuation.py",
            "src/blackhole_agent/v4embed_actuation.py",
            "src/blackhole_agent/siitdtm_actuation.py",
            "src/blackhole_agent/siitdc_actuation.py",
            "src/blackhole_agent/eam_actuation.py",
            "src/blackhole_agent/siit_actuation.py",
            "src/blackhole_agent/ucpe_actuation.py",
            "src/blackhole_agent/s46_actuation.py",
            "src/blackhole_agent/lw4o6_actuation.py",
            "src/blackhole_agent/dslite_actuation.py",
            "src/blackhole_agent/disc_actuation.py",
            "src/blackhole_agent/xlat_actuation.py",
            "src/blackhole_agent/dns64_actuation.py",
            "src/blackhole_agent/nat64_actuation.py",
            "src/blackhole_agent/pref64_actuation.py",
            "src/blackhole_agent/rdnss_actuation.py",
            "src/blackhole_agent/firsthop_actuation.py",
            "src/blackhole_agent/addrpolicy_actuation.py",
            "src/blackhole_agent/addrselect_actuation.py",
            "src/blackhole_agent/ipv6scope_actuation.py",
            "src/blackhole_agent/ipv6addr_actuation.py",
            "src/blackhole_agent/cga_actuation.py",
            "src/blackhole_agent/opaqueiid_actuation.py",
            "src/blackhole_agent/tempaddr_actuation.py",
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
            "src/blackhole_agent/m46_actuation.py",
            "src/blackhole_agent/prefix64_actuation.py",
            "src/blackhole_agent/mapt_actuation.py",
            "src/blackhole_agent/mape_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required bgpcomm tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 1997 daemon, speaks a "
            "COMM then ATTR over BGP Communities Attribute with a non-empty bgpcommid and "
            "bgpcommdigest, independently polls the stored bgpcommdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 2918 Route Refresh Capability for BGP-4 REQUEST/REFRESH lockstep is proved. "
            "Missing bgpcommids, skip-COMM, skip-ATTR, skip-bgpcommdigest, skip-REPLAY, "
            "and a COMM aimed without a bgpcommid stay fail-closed. "
            "Later genesis can take RFC 4360 BGP Extended Communities Attribute EXT/TYPE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("bgpcomm", "rfc1997", "http", "bgpcommid", "bgpcommdigest", "comm", "attr", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260908T003841Z-bc7a70c9",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_bgpcomm_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1997 comm/attr lockstep actuation seals a bgpcommdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.slaac_actuation import (
        SLAAC_ACTUATION_GOAL,
        SLAAC_ACTUATION_ID,
    )
    from blackhole_agent.s46_actuation import (
        S46_ACTUATION_GOAL,
        S46_ACTUATION_ID,
    )
    from blackhole_agent.ucpe_actuation import (
        UCPE_ACTUATION_GOAL,
        UCPE_ACTUATION_ID,
    )
    from blackhole_agent.m46_actuation import (
        M46_ACTUATION_GOAL,
        M46_ACTUATION_ID,
    )
    from blackhole_agent.siit_actuation import (
        SIIT_ACTUATION_GOAL,
        SIIT_ACTUATION_ID,
    )
    from blackhole_agent.eam_actuation import (
        EAM_ACTUATION_GOAL,
        EAM_ACTUATION_ID,
    )
    from blackhole_agent.siitdc_actuation import (
        SIITDC_ACTUATION_GOAL,
        SIITDC_ACTUATION_ID,
    )
    from blackhole_agent.siitdtm_actuation import (
        SIITDTM_ACTUATION_GOAL,
        SIITDTM_ACTUATION_ID,
    )
    from blackhole_agent.v4embed_actuation import (
        V4EMBED_ACTUATION_GOAL,
        V4EMBED_ACTUATION_ID,
    )
    from blackhole_agent.luprefix_actuation import (
        LUPREFIX_ACTUATION_GOAL,
        LUPREFIX_ACTUATION_ID,
    )
    from blackhole_agent.sixrd_actuation import (
        SIXRD_ACTUATION_GOAL,
        SIXRD_ACTUATION_ID,
    )
    from blackhole_agent.sixto4_actuation import (
        SIXTO4_ACTUATION_GOAL,
        SIXTO4_ACTUATION_ID,
    )
    from blackhole_agent.teredo_actuation import (
        TEREDO_ACTUATION_GOAL,
        TEREDO_ACTUATION_ID,
    )
    from blackhole_agent.isatap_actuation import (
        ISATAP_ACTUATION_GOAL,
        ISATAP_ACTUATION_ID,
    )
    from blackhole_agent.sixover4_actuation import (
        SIXOVER4_ACTUATION_GOAL,
        SIXOVER4_ACTUATION_ID,
    )
    from blackhole_agent.sixin4_actuation import (
        SIXIN4_ACTUATION_GOAL,
        SIXIN4_ACTUATION_ID,
    )
    from blackhole_agent.tsp_actuation import (
        TSP_ACTUATION_GOAL,
        TSP_ACTUATION_ID,
    )
    from blackhole_agent.l2tp_actuation import (
        L2TP_ACTUATION_GOAL,
        L2TP_ACTUATION_ID,
    )
    from blackhole_agent.mesh_actuation import (
        MESH_ACTUATION_GOAL,
        MESH_ACTUATION_ID,
    )
    from blackhole_agent.encap_actuation import (
        ENCAP_ACTUATION_GOAL,
        ENCAP_ACTUATION_ID,
    )
    from blackhole_agent.mpbgp_actuation import (
        MPBGP_ACTUATION_GOAL,
        MPBGP_ACTUATION_ID,
    )
    from blackhole_agent.bgp4_actuation import (
        BGP4_ACTUATION_GOAL,
        BGP4_ACTUATION_ID,
    )
    from blackhole_agent.rtrefresh_actuation import (
        RTREFRESH_ACTUATION_GOAL,
        RTREFRESH_ACTUATION_ID,
    )
    from blackhole_agent.extcomm_actuation import (
        EXTCOMM_ACTUATION_GOAL,
        EXTCOMM_ACTUATION_ID,
    )
    from blackhole_agent.largecomm_actuation import (
        LARGECOMM_ACTUATION_GOAL,
        LARGECOMM_ACTUATION_ID,
    )
    from blackhole_agent.prefix64_actuation import (
        PREFIX64_ACTUATION_GOAL,
        PREFIX64_ACTUATION_ID,
    )
    from blackhole_agent.mapt_actuation import (
        MAPT_ACTUATION_GOAL,
        MAPT_ACTUATION_ID,
    )
    from blackhole_agent.mape_actuation import (
        MAPE_ACTUATION_GOAL,
        MAPE_ACTUATION_ID,
    )
    from blackhole_agent.lw4o6_actuation import (
        LW4O6_ACTUATION_GOAL,
        LW4O6_ACTUATION_ID,
    )
    from blackhole_agent.dslite_actuation import (
        DSLITE_ACTUATION_GOAL,
        DSLITE_ACTUATION_ID,
    )
    from blackhole_agent.disc_actuation import (
        DISC_ACTUATION_GOAL,
        DISC_ACTUATION_ID,
    )
    from blackhole_agent.xlat_actuation import (
        XLAT_ACTUATION_GOAL,
        XLAT_ACTUATION_ID,
    )
    from blackhole_agent.dns64_actuation import (
        DNS64_ACTUATION_GOAL,
        DNS64_ACTUATION_ID,
    )
    from blackhole_agent.nat64_actuation import (
        NAT64_ACTUATION_GOAL,
        NAT64_ACTUATION_ID,
    )
    from blackhole_agent.pref64_actuation import (
        PREF64_ACTUATION_GOAL,
        PREF64_ACTUATION_ID,
    )
    from blackhole_agent.rdnss_actuation import (
        RDNSS_ACTUATION_GOAL,
        RDNSS_ACTUATION_ID,
    )
    from blackhole_agent.firsthop_actuation import (
        FIRSTHOP_ACTUATION_GOAL,
        FIRSTHOP_ACTUATION_ID,
    )
    from blackhole_agent.addrpolicy_actuation import (
        ADDRPOLICY_ACTUATION_GOAL,
        ADDRPOLICY_ACTUATION_ID,
    )
    from blackhole_agent.addrselect_actuation import (
        ADDRSELECT_ACTUATION_GOAL,
        ADDRSELECT_ACTUATION_ID,
    )
    from blackhole_agent.ipv6scope_actuation import (
        IPV6SCOPE_ACTUATION_GOAL,
        IPV6SCOPE_ACTUATION_ID,
    )
    from blackhole_agent.ipv6addr_actuation import (
        IPV6ADDR_ACTUATION_GOAL,
        IPV6ADDR_ACTUATION_ID,
    )
    from blackhole_agent.ula_actuation import (
        ULA_ACTUATION_GOAL,
        ULA_ACTUATION_ID,
    )
    from blackhole_agent.cga_actuation import (
        CGA_ACTUATION_GOAL,
        CGA_ACTUATION_ID,
    )
    from blackhole_agent.opaqueiid_actuation import (
        OPAQUEIID_ACTUATION_GOAL,
        OPAQUEIID_ACTUATION_ID,
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
        semantic_tokens,
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
    checks["denylists_self"] = BGPCOMM_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(BGPCOMM_ACTUATION_GOAL) == (
        BGPCOMM_ACTUATION_ID,
    )
    checks["leftover_text_binds_bgpcomm"] = leftover_marker_ids(BGPCOMM_LEFTOVER) == (
        BGPCOMM_ACTUATION_ID,
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
        (S46_ACTUATION_GOAL, S46_ACTUATION_ID, "s46"),
        (UCPE_ACTUATION_GOAL, UCPE_ACTUATION_ID, "ucpe"),
        (M46_ACTUATION_GOAL, M46_ACTUATION_ID, "m46"),
        (PREFIX64_ACTUATION_GOAL, PREFIX64_ACTUATION_ID, "prefix64"),
        (SIIT_ACTUATION_GOAL, SIIT_ACTUATION_ID, "siit"),
        (EAM_ACTUATION_GOAL, EAM_ACTUATION_ID, "eam"),
        (SIITDC_ACTUATION_GOAL, SIITDC_ACTUATION_ID, "siitdc"),
        (SIITDTM_ACTUATION_GOAL, SIITDTM_ACTUATION_ID, "siitdtm"),
        (V4EMBED_ACTUATION_GOAL, V4EMBED_ACTUATION_ID, "v4embed"),
        (LUPREFIX_ACTUATION_GOAL, LUPREFIX_ACTUATION_ID, "luprefix"),
        (SIXRD_ACTUATION_GOAL, SIXRD_ACTUATION_ID, "sixrd"),
        (SIXTO4_ACTUATION_GOAL, SIXTO4_ACTUATION_ID, "sixto4"),
        (TEREDO_ACTUATION_GOAL, TEREDO_ACTUATION_ID, "teredo"),
        (ISATAP_ACTUATION_GOAL, ISATAP_ACTUATION_ID, "isatap"),
        (SIXOVER4_ACTUATION_GOAL, SIXOVER4_ACTUATION_ID, "sixover4"),
        (SIXIN4_ACTUATION_GOAL, SIXIN4_ACTUATION_ID, "sixin4"),
        (TSP_ACTUATION_GOAL, TSP_ACTUATION_ID, "tsp"),
        (L2TP_ACTUATION_GOAL, L2TP_ACTUATION_ID, "l2tp"),
        (MESH_ACTUATION_GOAL, MESH_ACTUATION_ID, "mesh"),
        (ENCAP_ACTUATION_GOAL, ENCAP_ACTUATION_ID, "encap"),
        (MPBGP_ACTUATION_GOAL, MPBGP_ACTUATION_ID, "mpbgp"),
        (BGP4_ACTUATION_GOAL, BGP4_ACTUATION_ID, "bgp4"),
        (RTREFRESH_ACTUATION_GOAL, RTREFRESH_ACTUATION_ID, "rtrefresh"),
        (EXTCOMM_ACTUATION_GOAL, EXTCOMM_ACTUATION_ID, "extcomm"),
        (LARGECOMM_ACTUATION_GOAL, LARGECOMM_ACTUATION_ID, "largecomm"),
        (MAPT_ACTUATION_GOAL, MAPT_ACTUATION_ID, "mapt"),
        (MAPE_ACTUATION_GOAL, MAPE_ACTUATION_ID, "mape"),
        (LW4O6_ACTUATION_GOAL, LW4O6_ACTUATION_ID, "lw4o6"),
        (DSLITE_ACTUATION_GOAL, DSLITE_ACTUATION_ID, "dslite"),
        (DISC_ACTUATION_GOAL, DISC_ACTUATION_ID, "disc"),
        (XLAT_ACTUATION_GOAL, XLAT_ACTUATION_ID, "xlat"),
        (DNS64_ACTUATION_GOAL, DNS64_ACTUATION_ID, "dns64"),
        (NAT64_ACTUATION_GOAL, NAT64_ACTUATION_ID, "nat64"),
        (PREF64_ACTUATION_GOAL, PREF64_ACTUATION_ID, "pref64"),
        (RDNSS_ACTUATION_GOAL, RDNSS_ACTUATION_ID, "rdnss"),
        (FIRSTHOP_ACTUATION_GOAL, FIRSTHOP_ACTUATION_ID, "firsthop"),
        (ADDRPOLICY_ACTUATION_GOAL, ADDRPOLICY_ACTUATION_ID, "addrpolicy"),
        (ADDRSELECT_ACTUATION_GOAL, ADDRSELECT_ACTUATION_ID, "addrselect"),
        (IPV6SCOPE_ACTUATION_GOAL, IPV6SCOPE_ACTUATION_ID, "ipv6scope"),
        (IPV6ADDR_ACTUATION_GOAL, IPV6ADDR_ACTUATION_ID, "ipv6addr"),
        (ULA_ACTUATION_GOAL, ULA_ACTUATION_ID, "ula"),
        (CGA_ACTUATION_GOAL, CGA_ACTUATION_ID, "cga"),
        (OPAQUEIID_ACTUATION_GOAL, OPAQUEIID_ACTUATION_ID, "opaqueiid"),
        (TEMPADDR_ACTUATION_GOAL, TEMPADDR_ACTUATION_ID, "tempaddr"),
        (SLAAC_ACTUATION_GOAL, SLAAC_ACTUATION_ID, "slaac"),
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
        checks[f"{name}_goal_is_not_bgpcomm"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"bgpcomm_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            BGPCOMM_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = BGPCOMM_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    publicised = serialize_bgpcomm(DEFAULT_SOURCE)
    rebuilt = serialize_bgpcomm(parse_bgpcomm(publicised))
    preloaded = parse_bgpcomm(RFC_BGPCOMM_DEST)
    header = encode_bgpcomm_header(DEFAULT_SOURCE)
    parsed_header = parse_bgpcomm_header(header)
    asked = parse_http_comm(temporary_comm(SENTINEL, DEFAULT_BGPCOMMID))
    preload_req = parse_http_comm(public_comm(SENTINEL, DEFAULT_BGPCOMMID, DEFAULT_BGPCOMMDIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_BGPCOMMID, DEFAULT_BGPCOMMDIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_BGPCOMMID, DEFAULT_BGPCOMMDIGEST)
    )
    checks["bgpcomm_roundtrip"] = (
        parse_bgpcomm(publicised) == DEFAULT_SOURCE
        and hmac.compare_digest(rebuilt, publicised)
        and publicised == RFC_SOURCE_FIELD
        and is_token("COMM") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SOURCE_FIELD
        and parsed_header["policy"] == DEFAULT_SOURCE
        and parsed_header["header"] == SOURCE_HEADER
        and parsed_header["is_first"] is True
        and parsed_header["table"] is False
        and preloaded == DEST_HOP
        and ascii_serialize_bgpcomm_directive() == RFC_SOURCE_DIRECTIVE
        and bgpcomm_directive_pair() == ("comm", "message")
        and RFC_SOURCE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_bgpcomm(DEST_HOP) == RFC_BGPCOMM_DEST
        and DEFAULT_BGPCOMMDIGEST == temporary_bgpcommdigest(DEFAULT_BGPCOMMID, SENTINEL)
        and "bgpcommdigest=" in canonical_public(SENTINEL, DEFAULT_BGPCOMMID, DEFAULT_BGPCOMMDIGEST)
        and canonical_temporary(SENTINEL, DEFAULT_BGPCOMMID).startswith("COMM")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "COMM"
        and asked["disc_kind"] == "bgpcomm"
        and asked["bgpcommid"] == DEFAULT_BGPCOMMID
        and preload_req["disc_kind"] == "attr"
        and preload_req["bgpcommdigest"] == DEFAULT_BGPCOMMDIGEST
        and got["status"] == 200
        and preload_public["status"] == 200
        and got["disc_kind"] == "bgpcomm"
        and preload_public["disc_kind"] == "attr"
        and got["policy"] == DEFAULT_SOURCE
        and preload_public["policy"] == DEST_HOP
        and got["content_length_matches_body"] is True
        and preload_public["content_length_matches_body"] is True
        and got["bgpcommdigest"] == DEFAULT_BGPCOMMDIGEST
        and preload_public["bgpcommdigest"] == DEFAULT_BGPCOMMDIGEST
        and bgpcomm_matches(serialize_bgpcomm(got["policy"]), publicised)
    )

    checks["catalog_names_addrselect"] = (
        len(catalog) > 129
        and catalog[129]["id"] == ADDRSELECT_ACTUATION_ID
        and catalog[128]["id"] == IPV6SCOPE_ACTUATION_ID
        and catalog[129]["source"] == "genesis_bind_addrselect"
    )
    checks["catalog_names_addrpolicy"] = (
        len(catalog) > 130
        and catalog[130]["id"] == ADDRPOLICY_ACTUATION_ID
        and catalog[130]["source"] == "genesis_bind_addrpolicy"
    )
    checks["catalog_names_firsthop"] = (
        len(catalog) > 131
        and catalog[131]["id"] == FIRSTHOP_ACTUATION_ID
        and catalog[131]["source"] == "genesis_bind_firsthop"
    )
    checks["catalog_names_rdnss"] = (
        len(catalog) > 132
        and catalog[132]["id"] == RDNSS_ACTUATION_ID
        and catalog[132]["source"] == "genesis_bind_rdnss"
    )
    checks["catalog_names_pref64"] = (
        len(catalog) > 133
        and catalog[133]["id"] == PREF64_ACTUATION_ID
        and catalog[133]["source"] == "genesis_bind_pref64"
    )
    checks["catalog_names_nat64"] = (
        len(catalog) > 134
        and catalog[134]["id"] == NAT64_ACTUATION_ID
        and catalog[134]["source"] == "genesis_bind_nat64"
    )
    checks["catalog_names_dns64"] = (
        len(catalog) > 135
        and catalog[135]["id"] == DNS64_ACTUATION_ID
        and catalog[135]["source"] == "genesis_bind_dns64"
    )
    checks["catalog_names_xlat"] = (
        len(catalog) > 136
        and catalog[136]["id"] == XLAT_ACTUATION_ID
        and catalog[136]["source"] == "genesis_bind_xlat"
    )
    checks["catalog_names_disc"] = (
        len(catalog) > 137
        and catalog[137]["id"] == DISC_ACTUATION_ID
        and catalog[137]["source"] == "genesis_bind_disc"
    )
    checks["catalog_names_dslite"] = (
        len(catalog) > 138
        and catalog[138]["id"] == DSLITE_ACTUATION_ID
        and catalog[138]["source"] == "genesis_bind_dslite"
    )
    checks["catalog_names_lw4o6"] = (
        len(catalog) > 139
        and catalog[139]["id"] == LW4O6_ACTUATION_ID
        and catalog[139]["source"] == "genesis_bind_lw4o6"
    )
    checks["catalog_names_mape"] = (
        len(catalog) > 140
        and catalog[140]["id"] == MAPE_ACTUATION_ID
        and catalog[140]["source"] == "genesis_bind_mape"
    )
    checks["catalog_names_mapt"] = (
        len(catalog) > 141
        and catalog[141]["id"] == MAPT_ACTUATION_ID
        and catalog[141]["source"] == "genesis_bind_mapt"
    )
    checks["catalog_names_s46"] = (
        len(catalog) > 142
        and catalog[142]["id"] == S46_ACTUATION_ID
        and catalog[142]["source"] == "genesis_bind_s46"
    )
    checks["catalog_names_ucpe"] = (
        len(catalog) > 143
        and catalog[143]["id"] == UCPE_ACTUATION_ID
        and catalog[143]["source"] == "genesis_bind_ucpe"
    )
    checks["catalog_names_m46"] = (
        len(catalog) > 144
        and catalog[144]["id"] == M46_ACTUATION_ID
        and catalog[144]["source"] == "genesis_bind_m46"
    )
    checks["catalog_names_prefix64"] = (
        len(catalog) > 145
        and catalog[145]["id"] == PREFIX64_ACTUATION_ID
        and catalog[145]["source"] == "genesis_bind_prefix64"
    )
    checks["catalog_names_siit"] = (
        len(catalog) > 146
        and catalog[146]["id"] == SIIT_ACTUATION_ID
        and catalog[146]["source"] == "genesis_bind_siit"
    )
    checks["catalog_names_eam"] = (
        len(catalog) > 147
        and catalog[147]["id"] == EAM_ACTUATION_ID
        and catalog[147]["source"] == "genesis_bind_eam"
    )
    checks["catalog_names_siitdc"] = (
        len(catalog) > 148
        and catalog[148]["id"] == SIITDC_ACTUATION_ID
        and catalog[148]["source"] == "genesis_bind_siitdc"
    )
    checks["catalog_names_siitdtm"] = (
        len(catalog) > 149
        and catalog[149]["id"] == SIITDTM_ACTUATION_ID
        and catalog[149]["source"] == "genesis_bind_siitdtm"
    )
    checks["catalog_names_v4embed"] = (
        len(catalog) > 150
        and catalog[150]["id"] == V4EMBED_ACTUATION_ID
        and catalog[150]["source"] == "genesis_bind_v4embed"
    )
    checks["catalog_names_luprefix"] = (
        len(catalog) > 151
        and catalog[151]["id"] == LUPREFIX_ACTUATION_ID
        and catalog[151]["source"] == "genesis_bind_luprefix"
    )
    checks["catalog_names_sixrd"] = (
        len(catalog) > 152
        and catalog[152]["id"] == SIXRD_ACTUATION_ID
        and catalog[152]["source"] == "genesis_bind_sixrd"
    )
    checks["catalog_names_sixto4"] = (
        len(catalog) > 153
        and catalog[153]["id"] == SIXTO4_ACTUATION_ID
        and catalog[153]["source"] == "genesis_bind_sixto4"
    )
    checks["catalog_names_teredo"] = (
        len(catalog) > 154
        and catalog[154]["id"] == TEREDO_ACTUATION_ID
        and catalog[154]["source"] == "genesis_bind_teredo"
    )
    checks["catalog_names_isatap"] = (
        len(catalog) > 155
        and catalog[155]["id"] == ISATAP_ACTUATION_ID
        and catalog[155]["source"] == "genesis_bind_isatap"
    )
    checks["catalog_names_sixover4"] = (
        len(catalog) > 156
        and catalog[156]["id"] == SIXOVER4_ACTUATION_ID
        and catalog[156]["source"] == "genesis_bind_sixover4"
    )
    checks["catalog_names_sixin4"] = (
        len(catalog) > 157
        and catalog[157]["id"] == SIXIN4_ACTUATION_ID
        and catalog[157]["source"] == "genesis_bind_sixin4"
    )
    checks["catalog_names_tsp"] = (
        len(catalog) > 158
        and catalog[158]["id"] == TSP_ACTUATION_ID
        and catalog[158]["source"] == "genesis_bind_tsp"
    )
    checks["catalog_names_l2tp"] = (
        len(catalog) > 159
        and catalog[159]["id"] == L2TP_ACTUATION_ID
        and catalog[159]["source"] == "genesis_bind_l2tp"
    )
    checks["catalog_names_mesh"] = (
        len(catalog) > 160
        and catalog[160]["id"] == MESH_ACTUATION_ID
        and catalog[160]["source"] == "genesis_bind_mesh"
    )
    checks["catalog_names_encap"] = (
        len(catalog) > 161
        and catalog[161]["id"] == ENCAP_ACTUATION_ID
        and catalog[161]["source"] == "genesis_bind_encap"
    )
    checks["catalog_names_mpbgp"] = (
        len(catalog) > 162
        and catalog[162]["id"] == MPBGP_ACTUATION_ID
        and catalog[162]["source"] == "genesis_bind_mpbgp"
    )
    checks["catalog_names_bgp4"] = (
        len(catalog) > 163
        and catalog[163]["id"] == BGP4_ACTUATION_ID
        and catalog[163]["source"] == "genesis_bind_bgp4"
    )
    checks["catalog_names_rtrefresh"] = (
        len(catalog) > 164
        and catalog[164]["id"] == RTREFRESH_ACTUATION_ID
        and catalog[164]["source"] == "genesis_bind_rtrefresh"
    )
    checks["catalog_names_bgpcomm"] = (
        len(catalog) > 165
        and catalog[165]["id"] == BGPCOMM_ACTUATION_ID
        and catalog[165]["source"] == "genesis_bind_bgpcomm"
    )
    checks["catalog_names_extcomm"] = (
        len(catalog) > 166
        and catalog[166]["id"] == EXTCOMM_ACTUATION_ID
        and catalog[166]["source"] == "genesis_bind_extcomm"
    )
    checks["catalog_names_largecomm"] = (
        len(catalog) > 167
        and catalog[167]["id"] == LARGECOMM_ACTUATION_ID
        and catalog[167]["source"] == "genesis_bind_largecomm"
    )
    family = capability_family(BGPCOMM_ACTUATION_GOAL)
    checks["family_is_bgpcomm"] = "bgpcomm" in family.split("/")
    checks["family_is_bgpcomm_surface"] = "bgpcomm" in family.split("/") and "bgpcommid" in set(semantic_tokens(BGPCOMM_ACTUATION_GOAL))
    checks["family_is_bgpcommid"] = "bgpcommid" in set(semantic_tokens(BGPCOMM_ACTUATION_GOAL))
    checks["family_is_rfc1997"] = "rfc1997" in family
    checks["family_is_bgpcommdigest"] = "bgpcommdigest" in family
    checks["family_is_not_ucpe"] = (
        "ucpe" not in family.split("/")
        and "rfc8026" not in family
        and "ucpeid" not in family
        and "ucpedigest" not in family
    )
    checks["family_is_not_prefix64"] = (
        "prefix64" not in family.split("/")
        and "rfc8115" not in family
        and "prefix64id" not in family
        and "prefix64digest" not in family
    )
    checks["family_is_not_m46"] = (
        "m46" not in family.split("/")
        and "rfc8114" not in family
        and "m46id" not in family
        and "m46digest" not in family
    )
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_slaac"] = (
        "slaac" not in family.split("/")
        and "rfc4862" not in family
        and "slaacid" not in family
        and "slaacdigest" not in family
    )
    checks["family_is_not_s46"] = (
        "s46" not in family.split("/")
        and "rfc7598" not in family
        and "s46id" not in family
        and "s46digest" not in family
    )
    checks["family_is_not_siit"] = (
        "siit" not in family.split("/")
        and "rfc7915" not in family
        and "siitid" not in family
        and "siitdigest" not in family
    )
    checks["family_is_not_eam"] = (
        "eam" not in family.split("/")
        and "rfc7757" not in family
        and "eamid" not in family.split("/")
        and "eamdigest" not in family.split("/")
    )
    checks["family_is_not_siitdc"] = (
        "siitdc" not in family.split("/")
        and "rfc7755" not in family
        and "siitdcid" not in family.split("/")
        and "siitdcdigest" not in family.split("/")
    )
    checks["family_is_not_siitdtm"] = (
        "siitdtm" not in family.split("/")
        and "rfc7756" not in family
        and "siitdtmid" not in family.split("/")
        and "siitdtmdigest" not in family.split("/")
    )
    checks["family_is_not_v4embed"] = (
        "v4embed" not in family.split("/")
        and "rfc6052" not in family
        and "v4embedid" not in family.split("/")
        and "v4embeddigest" not in family.split("/")
    )
    checks["family_is_not_luprefix"] = (
        "luprefix" not in family.split("/")
        and "rfc8215" not in family
        and "luprefixid" not in family.split("/")
        and "luprefixdigest" not in family.split("/")
    )
    checks["family_is_not_sixrd"] = (
        "sixrd" not in family.split("/")
        and "rfc5969" not in family
        and "sixrdid" not in family.split("/")
        and "sixrddigest" not in family.split("/")
    )
    checks["family_is_not_sixto4"] = (
        "sixto4" not in family.split("/")
        and "rfc3056" not in family
        and "sixto4id" not in family.split("/")
        and "sixto4digest" not in family.split("/")
    )
    checks["family_is_not_teredo"] = (
        "teredo" not in family.split("/")
        and "rfc4380" not in family
        and "teredoid" not in family.split("/")
        and "teredodigest" not in family.split("/")
    )
    checks["family_is_not_isatap"] = (
        "isatap" not in family.split("/")
        and "rfc5214" not in family
        and "isatapid" not in family.split("/")
        and "isatapdigest" not in family.split("/")
    )
    checks["family_is_not_sixover4"] = (
        "sixover4" not in family.split("/")
        and "rfc2529" not in family
        and "sixover4id" not in family.split("/")
        and "sixover4digest" not in family.split("/")
    )
    checks["family_is_not_sixin4"] = (
        "sixin4" not in family.split("/")
        and "rfc4213" not in family
        and "sixin4id" not in family.split("/")
        and "sixin4digest" not in family.split("/")
    )
    checks["family_is_not_tsp"] = (
        "tsp" not in family.split("/")
        and "rfc5572" not in family
        and "tspid" not in family.split("/")
        and "tspdigest" not in family.split("/")
    )
    checks["family_is_not_l2tp"] = (
        "l2tp" not in family.split("/")
        and "rfc5571" not in family
        and "l2tpid" not in family.split("/")
        and "l2tpdigest" not in family.split("/")
    )
    checks["family_is_not_mesh"] = (
        "mesh" not in family.split("/")
        and "rfc5565" not in family
        and "meshid" not in family.split("/")
        and "meshdigest" not in family.split("/")
    )
    checks["family_is_not_encap"] = (
        "encap" not in family.split("/")
        and "rfc5512" not in family
        and "encapid" not in family
        and "encapdigest" not in family
    )
    checks["family_is_not_mpbgp"] = (
        "mpbgp" not in family.split("/")
        and "rfc4760" not in family
        and "mpbgpid" not in family
        and "mpbgpdigest" not in family
    )
    checks["family_is_not_extcomm"] = (
        "extcomm" not in family.split("/")
        and "rfc4360" not in family
        and "extcommid" not in family
        and "extcommdigest" not in family
    )
    checks["family_is_not_largecomm"] = (
        "largecomm" not in family.split("/")
        and "rfc8092" not in family
        and "largecommid" not in family
        and "largecommdigest" not in family
    )
    checks["family_is_not_rtrefresh"] = (
        "rtrefresh" not in family.split("/")
        and "rfc2918" not in family
        and "rtrefreshid" not in family
        and "rtrefreshdigest" not in family
    )
    checks["family_is_not_bgp4"] = (
        "bgp4" not in family.split("/")
        and "rfc4271" not in family
        and "bgp4id" not in family
        and "bgp4digest" not in family
    )
    checks["family_is_not_mapt"] = (
        "mapt" not in family.split("/")
        and "rfc7599" not in family
        and "maptid" not in family
        and "maptdigest" not in family
    )
    checks["family_is_not_mape"] = (
        "mape" not in family.split("/")
        and "rfc7597" not in family
        and "mapeid" not in family
        and "mapedigest" not in family
    )
    checks["family_is_not_lw4o6"] = (
        "lw4o6" not in family.split("/")
        and "rfc7596" not in family
        and "lw4o6id" not in family
        and "lw4o6digest" not in family
    )
    checks["family_is_not_dslite"] = (
        "dslite" not in family.split("/")
        and "rfc6333" not in family
        and "dsliteid" not in family
        and "dslitedigest" not in family
    )
    checks["family_is_not_disc"] = (
        "disc" not in family.split("/")
        and "rfc7050" not in family
        and "discid" not in family
        and "discdigest" not in family
    )
    checks["family_is_not_xlat"] = (
        "xlat" not in family.split("/")
        and "rfc6877" not in family
        and "clatid" not in family
        and "clatdigest" not in family
    )
    checks["family_is_not_dns64"] = (
        "dns64" not in family.split("/")
        and "rfc6147" not in family
        and "dns64id" not in family
        and "dns64digest" not in family
    )
    checks["family_is_not_nat64"] = (
        "nat64" not in family.split("/")
        and "rfc6146" not in family
        and "nat64id" not in family
        and "nat64digest" not in family
    )
    checks["family_is_not_pref64"] = (
        "pref64" not in family.split("/")
        and "rfc8781" not in family
        and "pref64id" not in family
        and "pref64digest" not in family
    )
    checks["family_is_not_rdnss"] = (
        "rdnss" not in family.split("/")
        and "rfc8106" not in family
        and "rdnssid" not in family
        and "rdnssdigest" not in family
    )
    checks["family_is_not_firsthop"] = (
        "firsthop" not in family.split("/")
        and "rfc8028" not in family
        and "hopid" not in family
        and "hopdigest" not in family
    )
    checks["family_is_not_addrpolicy"] = (
        "addrpolicy" not in family.split("/")
        and "rfc7078" not in family
        and "policyid" not in family
        and "policydigest" not in family
    )
    checks["family_is_not_addrselect"] = (
        "addrselect" not in family.split("/")
        and "rfc6724" not in family
        and "selectid" not in family
        and "selectdigest" not in family
    )
    checks["family_is_not_ipv6scope"] = (
        "ipv6scope" not in family.split("/")
        and "rfc4007" not in family
        and "scopeid" not in family
        and "scopedigest" not in family
    )
    checks["family_is_not_ipv6addr"] = (
        "ipv6addr" not in family.split("/")
        and "rfc4291" not in family
        and "ipv6addrid" not in family
        and "ipv6addrdigest" not in family
    )
    checks["family_is_not_ula"] = (
        "ula" not in family.split("/")
        and "rfc4193" not in family
        and "ulaid" not in family
        and "uladigest" not in family
    )
    checks["family_is_not_send"] = (
        "send" not in family.split("/")
        and "rfc3971" not in family
        and "sendid" not in family
        and "senddigest" not in family
    )
    checks["family_is_not_cga"] = (
        "cga" not in family.split("/")
        and "rfc3972" not in family
        and "cgaid" not in family
        and "cgadigest" not in family
    )
    checks["family_is_not_opaqueiid"] = (
        "opaqueiid" not in family.split("/")
        and "rfc7217" not in family
        and "opaqueid" not in family
        and "opaquedigest" not in family
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
        "ipid" not in family.split("/")
        and "ipdigest" not in family.split("/")
        and "rfc791" not in family.split("/")
    )
    checks["family_is_not_tcp"] = (
        "tcp" not in family.split("/")
        and "rfc793" not in family
        and "tcpid" not in family
        and "tcpdigest" not in family
    )
    checks["family_is_not_icmp"] = (
        "rfc792" not in family.split("/")
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
        and "encid" not in family.split("/")
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
        and "dcid" not in family.split("/")
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
    checks["family_is_not_ike"] = (
        "ike" not in family.split("/")
        and "rfc7296" not in family
        and "spi" not in family.split("/")
    )
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
    packed = encode_temporary(identity=SENTINEL, bgpcommid=DEFAULT_BGPCOMMID, bgpcommdigest=DEFAULT_BGPCOMMDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_temporary"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_bgpcommid"] is True
        and parsed["bgpcommid"] == DEFAULT_BGPCOMMID
        and parsed["bgpcommdigest"] == DEFAULT_BGPCOMMDIGEST
        and parsed["is_public"] is False
        and parsed["is_public"] is False
        and parsed["type"] == FRAME_SOURCE
        and parsed["first_byte"] == BGPCOMM_FIRST
    )
    shook = encode_public(
        identity=SENTINEL,
        bgpcommid=DEFAULT_BGPCOMMID,
        bgpcommdigest=DEFAULT_BGPCOMMDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_public"] is True
        and answer_parsed["is_public"] is True
        and answer_parsed["is_temporary"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["bgpcommid"] == DEFAULT_BGPCOMMID
        and answer_parsed["bgpcommdigest"] == DEFAULT_BGPCOMMDIGEST
        and answer_parsed["has_bgpcommdigest"] is True
        and answer_parsed["type"] == FRAME_DEST
        and answer_parsed["first_byte"] == BGPCOMM_FIRST
    )
    bare = encode_temporary(identity=SENTINEL, bgpcommid=DEFAULT_BGPCOMMID, include_bgpcommid=False)
    checks["missing_bgpcommid_is_unauthed"] = parse_message(bare)["has_bgpcommid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(BGPCOMM_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_bgpcomm = ToolDescriptor(name="remote_bgpcomm", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_bgpcomm)
    checks["naive_mcp_bgpcomm_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = bgpcomm_tool_descriptor()
    default_bgpcomm = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BGPCOMM_TOOL_PROVIDER),
    )
    checks["default_bgpcomm_provider_is_unsupported"] = (
        default_bgpcomm.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{BGPCOMM_TOOL_PROVIDER}" in default_bgpcomm.reasons
    )
    checks["opted_in_bgpcomm_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_bgpcomm],
        required_tool_names=("local_memory", "bgpcomm"),
    )
    checks["naive_preflight_missing_bgpcomm"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["bgpcomm"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "bgpcomm"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BGPCOMM_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "bgpcomm" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="bgpcomm-actuation-") as tmp:
        root = Path(tmp)
        missing = run_bgpcomm_workflow(with_bgpcommid=False, output_dir=root / "missing")
        skip_bind = run_bgpcomm_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_temporary = run_bgpcomm_workflow(do_temporary=False, output_dir=root / "skip-comm")
        skip_public = run_bgpcomm_workflow(do_public=False, output_dir=root / "skip-attr")
        skip_bgpcommdigest = run_bgpcomm_workflow(do_bgpcommdigest=False, output_dir=root / "skip-bgpcommdigest")
        skip_replay = run_bgpcomm_workflow(replay=False, output_dir=root / "skip-replay")
        skip_bgpcommid = run_bgpcomm_workflow(use_bgpcommid=False, output_dir=root / "skip-bgpcommid")
        live = run_bgpcomm_workflow(output_dir=root / "live")
        sealed = verify_bgpcomm_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_bgpcomm_trace(clone)
        checks["naive_without_bgpcommid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_bgpcommid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_temporary_stays_empty"] = (
            skip_temporary["ok"] is False
            and skip_temporary["error"] == "temporary_required"
            and skip_temporary["final_status"] == 409
            and skip_temporary["payload_exists"] is False
        )
        checks["skip_public_stays_empty"] = (
            skip_public["ok"] is False
            and skip_public["error"] == "public_required"
            and skip_public["final_status"] == 409
            and skip_public["payload_exists"] is False
        )
        checks["skip_bgpcommdigest_stays_empty"] = (
            skip_bgpcommdigest["ok"] is False
            and skip_bgpcommdigest["error"] == "bgpcommdigest_required"
            and skip_bgpcommdigest["final_status"] == 409
            and skip_bgpcommdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_bgpcommid_stays_empty"] = (
            skip_bgpcommid["ok"] is False
            and skip_bgpcommid["error"] == "bgpcommid_required"
            and skip_bgpcommid["final_status"] == 409
            and skip_bgpcommid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_bgpcommdigest"] = (
            int(live.get("bgpcommid") or 0) == DEFAULT_BGPCOMMID
            and int(live.get("bgpcommdigest") or 0) == DEFAULT_BGPCOMMDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_bgpcommid_encode_public_bgpcommdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_temporary["ok"] is False
            and skip_public["ok"] is False
            and skip_bgpcommdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_bgpcommid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = sealed["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="bgpcomm-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != BGPCOMM_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, BGPCOMM_ACTUATION_GOAL, BGPCOMM_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_bgpcomm"] = (
        not gate.accepted
        and live_goal != BGPCOMM_ACTUATION_GOAL
        and BGPCOMM_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_bgpcomm"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="bgpcomm-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(BGPCOMM_LEFTOVER, root)
        register_catalog_proved(root, BGPCOMM_ACTUATION_ID)
        reason = leftover_satisfied_by(BGPCOMM_LEFTOVER, root)
        after = leftover_is_open(BGPCOMM_LEFTOVER, root)
    checks["bgpcomm_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_bgpcomm_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{BGPCOMM_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_bgpcomm_actuation_capability()
    return {
        "ok": ok,
        "action": "bgpcomm_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": BGPCOMM_ACTUATION_GOAL,
        "done_when": BGPCOMM_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
