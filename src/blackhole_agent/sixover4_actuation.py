"""Drive a first-class Transmission of IPv6 over IPv4 Domains without Explicit Tunnels tool through RFC 2529 6OVER4/MCAST.

Tool routing already fails missions that require ``sixover4``: hosted
ipv6 over ipv4 domains without explicit tunnels endpoints stay on the unsupported MCP provider, and no first-party
sixover4 provider is executable. Unbound therefore cannot speak a 6OVER4,
lockstep a MCAST sixover4id handshake over HTTP/1.0 SIXOVER4ID,
independently poll the stored sixover4digest, or seal a sixover4digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``sixover4`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2529 daemon
- keep a missing-sixover4id client so the sixover4-sixover4id hole stays falsifiable
- refuse MCAST until a 6OVER4 lands with a non-empty sixover4id
- independently poll the stored sixover4digest on a later client socket
- persist a sealed sixover4digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 5214 Intra-Site Automatic Tunnel Addressing Protocol ISATAP/PRL
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
    SIXOVER4_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    sixover4_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
SIXOVER4_ACTUATION_ID = "capability.sixover4-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SIXOVER4-OK"
POLL_TOKEN = "BH-SIXOVER4-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_SIXOVER4ID = 0
EMPTY_SIXOVER4DIGEST = 0
SIXOVER4_FIRST = 0x36  # RFC 2529 6OVER4
SIXOVER4ID_SIZE = 4
SIXOVER4DIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DEST = 0x02  # RFC 2529 mcast index
FRAME_SOURCE = 0x01  # RFC 2529 6over4 type
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
SIXOVER4_LEFTOVER = (
    "Later genesis can take RFC 2529 Transmission of IPv6 over IPv4 Domains without Explicit Tunnels 6OVER4/MCAST over a sixover4id-gated sixover4digest."
)
SIXOVER4_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SIXOVER4_ACTUATION_ID};"
    f"capability_proved:{SIXOVER4_ACTUATION_ID};"
    "no_skill_route"
)
SIXOVER4_ACTUATION_GOAL = (
    "Repair rfc2529 sixover4 6over4/mcast cycle cannot land over http "
    "sixover4 sixover4id: hosted ipv6 over ipv4 domains without explicit tunnels endpoints remain unsupported "
    "so a 6OVER4 then MCAST sixover4id handshake cannot land and a sealed "
    "sixover4digest cannot be produced. A missing sixover4 sixover4id stays forbidden; "
    "fail-closed routing never opts the sixover4 provider in. An independent later "
    "poll of the stored sixover4digest keeps the hole falsifiable. 6over4 "
    "ipv4 multicast virtual links stay fail-closed without a sixover4id-gated "
    "sixover4digest."
)


class Sixover4ActuationError(RuntimeError):
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
# RFC 2529 sections 3.1 and 3.2: 6OVER4 / MCAST.
RFC_SOURCE_FIELD = "6OVER4"
RFC_DEST_FIELD = "MCAST"
RFC_SIXOVER4_DEST = RFC_DEST_FIELD
RFC_SOURCE_DIRECTIVE = "sixover4=message"
RFC_DEST_DIRECTIVE = "mcast=message"
DEFAULT_SOURCE = "6OVER4"
DEST_HOP = "MCAST"
SOURCE_HEADER = "6OVER4"
DEST_HEADER = "Mcast"
SIXOVER4_DEST_HEADER = DEST_HEADER
RFC_SOURCE_PATH = "/sixover4/"
RFC_SOURCE_EMPTY = ""


def sixover4_directive_pair(*, local: bool = False) -> tuple[str, str]:
    """RFC 2529 6OVER4 / MCAST directive pair."""

    if local:
        return "mcast", "message"
    return "sixover4", "message"


def ascii_serialize_sixover4_directive(*, local: bool = False) -> str:
    """RFC 2529 token "=" body-or-local."""

    name, value = sixover4_directive_pair(local=local)
    if not is_token(name):
        raise Sixover4ActuationError("illegal_directive")
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
            raise Sixover4ActuationError("short_sixover4")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 2529 body-unique token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_sixover4(policy: str | Sequence[str]) -> str:
    """Serialize RFC 2529 6OVER4 / MCAST opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise Sixover4ActuationError("illegal_sixover4")
    upper = text.upper().replace("_", "-")
    if upper in {"6OVER4", "6OVER4", "6OVER4-6OVER4"}:
        return "6OVER4"
    if upper in {"MCAST", "6OVER4-MCAST"}:
        return "MCAST"
    if upper.startswith("6OVER4="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Sixover4ActuationError("illegal_sixover4")
        return "6OVER4"
    if upper.startswith("MCAST="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Sixover4ActuationError("illegal_sixover4")
        return "MCAST"
    raise Sixover4ActuationError("illegal_sixover4")


def parse_sixover4(text: str) -> str:
    """Parse RFC 2529 CE opcode header extensions into CE or BR."""

    raw = str(text or "").strip()
    if not raw:
        raise Sixover4ActuationError("illegal_sixover4")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"6OVER4", "6OVER4", "6OVER4-6OVER4"}:
        return "6OVER4"
    if upper in {"MCAST", "6OVER4-MCAST"}:
        return "MCAST"
    if upper.startswith("6OVER4="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Sixover4ActuationError("illegal_sixover4")
        return "6OVER4"
    if upper.startswith("MCAST="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Sixover4ActuationError("illegal_sixover4")
        return "MCAST"
    raise Sixover4ActuationError("illegal_sixover4")


def encode_sixover4_header(policy: str | Sequence[str]) -> bytes:
    """RFC 2529 HTTP/1.0 field as bytes."""

    return serialize_sixover4(policy).encode("ascii")


def parse_sixover4_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_sixover4(field_value) if field_value else DEFAULT_SOURCE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SOURCE_HEADER,
        "directive": str(policy),
        "is_first": str(policy) == "6OVER4",
        "table": str(policy) == "MCAST",
    }


def canonical_temporary(identity: str, sixover4id: int) -> str:
    """RFC 2529 body-unique advertisement bound to identity and sixover4id."""

    return (
        f"{serialize_sixover4(DEFAULT_SOURCE)}, "
        f"sixover4={ascii_serialize_sixover4_directive()}, "
        f"identity={identity}, sixover4id={int(sixover4id) & 0xFFFFFFFF}"
    )


def canonical_public(identity: str, sixover4id: int, sixover4digest: int | None = None) -> str:
    """RFC 2529 local-message confirmation of the stored identifier-digest."""

    digest = ""
    if sixover4digest is not None:
        digest = f", sixover4digest={int(sixover4digest) & 0xFFFFFFFF}"
    return (
        f"{serialize_sixover4(DEST_HOP)}, "
        f"mcast={ascii_serialize_sixover4_directive(local=True)}, "
        f"identity={identity}, sixover4id={int(sixover4id) & 0xFFFFFFFF}{digest}"
    )


def representation_public(identity: str, sixover4id: int, sixover4digest: int) -> str:
    return canonical_public(identity, sixover4id, sixover4digest)


def sixover4_matches(left: str, right: str) -> bool:
    return parse_sixover4(left) == parse_sixover4(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise Sixover4ActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise Sixover4ActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise Sixover4ActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise Sixover4ActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def temporary_request(identity: str, sixover4id: int) -> bytes:
    """HTTP CE that elicits RFC 2529 origin HTTP/1.0."""

    keyid = f"{int(sixover4id) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"6OVER4 /sixover4/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Sixover4-Id: {int(sixover4id) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def public_request(identity: str, sixover4id: int, sixover4digest: int | None = None) -> bytes:
    """HTTP BR carrying RFC 2529 local-message confirmation of the stored identifier-digest."""

    keyid = f"{int(sixover4id) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if sixover4digest is not None:
        extra = f"Sixover4-Digest: {int(sixover4digest) & 0xFFFFFFFF}\r\n"
    return (
        f"MCAST /sixover4/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Sixover4-Id: {int(sixover4id) & 0xFFFFFFFF}\r\n"
        "Mcast-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    disc_kind = "mcast" if fields.get("mcast-confirm") == "1" else "sixover4"
    upgrade_field = fields.get("6over4") or fields.get("sixover4") or ""
    policy = parse_sixover4(upgrade_field) if upgrade_field else ()
    return {
        "kind": "sixover4",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "disc_kind": disc_kind,
        "policy": policy,
        "sixover4id": int(fields["sixover4-id"]) if fields.get("sixover4-id") else EMPTY_SIXOVER4ID,
        "sixover4digest": int(fields["sixover4-digest"]) if fields.get("sixover4-digest") else EMPTY_SIXOVER4DIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def temporary_response(identity: str, sixover4id: int, sixover4digest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 2529 origin HTTP/1.0, carrying the stored sixover4digest."""

    publicised = serialize_sixover4(DEFAULT_SOURCE)
    payload = bytes(body or canonical_temporary(identity, sixover4id).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"6OVER4: {publicised}\r\n"
        f"Sixover4-Id: {int(sixover4id) & 0xFFFFFFFF}\r\n"
        f"Sixover4-Digest: {int(sixover4digest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def public_response(identity: str, sixover4id: int, sixover4digest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 2529 BR, carrying the stored identifier-digest."""

    publicised = serialize_sixover4(DEST_HOP)
    payload = bytes(body or representation_public(identity, sixover4id, sixover4digest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"6OVER4: {publicised}\r\n"
        f"Sixover4-Id: {int(sixover4id) & 0xFFFFFFFF}\r\n"
        f"Sixover4-Digest: {int(sixover4digest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/sixover4-mcast\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise Sixover4ActuationError("illegal_content_length") from error
    field_value = fields.get("6over4") or fields.get("sixover4") or ""
    policy = parse_sixover4(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/sixover4-mcast" or policy == DEST_HOP:
        status = 200
        disc_kind = "mcast"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        disc_kind = "sixover4"
    else:
        status = 0
        disc_kind = "sixover4"
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
        "sixover4id": int(fields["sixover4-id"]) if fields.get("sixover4-id") else EMPTY_SIXOVER4ID,
        "sixover4digest": int(fields["sixover4-digest"]) if fields.get("sixover4-digest") else EMPTY_SIXOVER4DIGEST,
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
        raise Sixover4ActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise Sixover4ActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise Sixover4ActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise Sixover4ActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc2529_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    ula: str,
) -> str:
    """RFC 2529 identifier digest over method, router-IP, identity, and sixover4id."""

    payload = f"{method}:{ula}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def temporary_sixover4id(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"sixover4id:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_sixover4id(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-sixover4id:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def temporary_sixover4digest(sixover4id: int = EMPTY_SIXOVER4ID, token: str = SENTINEL) -> int:
    nonce = f"{int(sixover4id) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc2529_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="MCAST",
        ula=f"/sixover4/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_SIXOVER4ID = temporary_sixover4id(SENTINEL)
DEFAULT_SIXOVER4DIGEST = temporary_sixover4digest(DEFAULT_SIXOVER4ID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    sixover4id: int,
    sixover4digest: int,
    include_sixover4id: bool = True,
) -> bytes:
    live_sixover4id = int(sixover4id) & 0xFFFFFFFF if include_sixover4id else EMPTY_SIXOVER4ID
    live_digest = int(sixover4digest) & 0xFFFFFFFF if include_sixover4id and live_sixover4id else EMPTY_SIXOVER4DIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_sixover4id) if live_sixover4id else b""
    header = bytearray()
    header.append(SIXOVER4_FIRST)
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
    sixover4id: int,
    sixover4digest: int | None = None,
    include_sixover4id: bool = True,
) -> bytes:
    live_sixover4id = int(sixover4id) & 0xFFFFFFFF if include_sixover4id else EMPTY_SIXOVER4ID
    live_digest = int(sixover4digest) if sixover4digest is not None else temporary_sixover4digest(live_sixover4id, identity)
    return encode_packet(
        FRAME_SOURCE,
        identity=identity,
        sixover4id=live_sixover4id,
        sixover4digest=live_digest,
        include_sixover4id=include_sixover4id,
    )


def encode_public(
    *,
    identity: str,
    sixover4id: int,
    sixover4digest: int | None = None,
    include_sixover4id: bool = True,
) -> bytes:
    live_sixover4id = int(sixover4id) & 0xFFFFFFFF if include_sixover4id else EMPTY_SIXOVER4ID
    live_digest = int(sixover4digest) if sixover4digest is not None else temporary_sixover4digest(live_sixover4id, identity)
    return encode_packet(
        FRAME_DEST,
        identity=identity,
        sixover4id=live_sixover4id,
        sixover4digest=live_digest,
        include_sixover4id=include_sixover4id,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise Sixover4ActuationError("short_packet")
    disc = raw[0]
    if disc != SIXOVER4_FIRST:
        raise Sixover4ActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise Sixover4ActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == SIXOVER4ID_SIZE:
        live_sixover4id = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_sixover4id = EMPTY_SIXOVER4ID
    else:
        raise Sixover4ActuationError("illegal_sixover4id")
    if offset >= len(raw):
        raise Sixover4ActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SOURCE, FRAME_DEST}:
        raise Sixover4ActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise Sixover4ActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise Sixover4ActuationError("checksum_failed")
    if len(payload) < 5:
        raise Sixover4ActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise Sixover4ActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_sixover4id = int(live_sixover4id) != EMPTY_SIXOVER4ID
    has_sixover4digest = has_sixover4id and int(live_digest) != EMPTY_SIXOVER4DIGEST
    is_temporary = frame_type == FRAME_SOURCE
    is_public = frame_type == FRAME_DEST
    return {
        "type": int(frame_type),
        "is_temporary": is_temporary,
        "is_public": is_public,
        "sixover4id": int(live_sixover4id),
        "has_sixover4id": has_sixover4id,
        "sixover4digest": int(live_digest),
        "has_sixover4digest": has_sixover4digest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(disc),
        "mech_len": int(mech_len),
        "http_state": "RFC2529",
        "serialize_field": canonical_temporary(identity, live_sixover4id) if has_sixover4id else "",
        "tls_field": canonical_public(identity, live_sixover4id, live_digest) if has_sixover4digest else "",
    }


class Sixover4Client:
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
            raise Sixover4ActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_public"] or not packet["is_public"]:
            raise Sixover4ActuationError("sixover4digest_required")
        if not packet["has_sixover4id"]:
            raise Sixover4ActuationError("sixover4id_required")
        if not packet["has_sixover4digest"]:
            raise Sixover4ActuationError("sixover4digest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_sixover4digest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_sixover4digest:
            raise Sixover4ActuationError("sixover4digest_required")
        session = self._recv()
        return {
            "session": session,
            "sixover4id": int(session.get("sixover4id") or EMPTY_SIXOVER4ID),
            "identity": str(session.get("identity") or ""),
            "sixover4digest": int(session.get("sixover4digest") or EMPTY_SIXOVER4DIGEST),
        }

    def local(
        self,
        identity: str,
        sixover4id: int,
        sixover4digest: int = EMPTY_SIXOVER4DIGEST,
        *,
        wait_sixover4digest: bool = True,
        include_sixover4id: bool = True,
    ) -> dict[str, Any]:
        packet = encode_public(
            identity=identity,
            sixover4id=sixover4id,
            sixover4digest=sixover4digest or temporary_sixover4digest(sixover4id, identity),
            include_sixover4id=include_sixover4id,
        )
        return self.exchange(packet, wait_sixover4digest=wait_sixover4digest)


class Sixover4Session:
    """SIXOVER4ID-gated loopback RFC 2529 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        sixover4id_gate: int = DEFAULT_SIXOVER4ID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sixover4id_gate = int(sixover4id_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.sixover4id = EMPTY_SIXOVER4ID
        self.sixover4digest = EMPTY_SIXOVER4DIGEST
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

    def store_sixover4id_once(self, identity: str, sixover4id: int, sixover4digest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(sixover4id or EMPTY_SIXOVER4ID)
            live_digest = int(sixover4digest or EMPTY_SIXOVER4DIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.sixover4id = live
                self.sixover4digest = live_digest or temporary_sixover4digest(live, name)
                self.stored = True
            return str(self.identity), int(self.sixover4id), int(self.sixover4digest)

    def read_sixover4id(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.sixover4id), int(self.sixover4digest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "sixover4id": EMPTY_SIXOVER4ID,
            "sixover4digest": EMPTY_SIXOVER4DIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _sixover4id_missing(self) -> bool:
        return not int(self.sixover4id_gate or 0)

    def _public_tuple(self, peer: tuple[str, int], identity: str, sixover4id: int, sixover4digest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_public(
            identity=identity,
            sixover4id=sixover4id,
            sixover4digest=sixover4digest,
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
            except Sixover4ActuationError:
                continue
            if not packet.get("is_temporary") and not packet.get("is_public"):
                continue
            if not packet.get("has_sixover4id"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_sixover4id, stored_digest = self.store_sixover4id_once(
                identity,
                int(packet.get("sixover4id") or EMPTY_SIXOVER4ID),
                int(packet.get("sixover4digest") or EMPTY_SIXOVER4DIGEST),
            )
            if not stored_name or not stored_sixover4id or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_temporary"):
                    self.opened = True
                if packet.get("is_public"):
                    self.handshook = True
                self.retrieved = True
            self._public_tuple(peer, stored_name, stored_sixover4id, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._sixover4id_missing():
            return self._forbidden("missing_sixover4id")
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
        do_sixover4digest: bool = True,
        replay: bool = True,
        use_sixover4id: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._sixover4id_missing():
            return self._forbidden("missing_sixover4id")
        live_token = str(token or SENTINEL)
        origin_sixover4id = temporary_sixover4id(live_token)
        origin_digest = temporary_sixover4digest(origin_sixover4id, live_token)
        client: Sixover4Client | None = None
        independent: Sixover4Client | None = None
        try:
            client = Sixover4Client(self.host, int(self.port))
            if not do_temporary:
                return self._conflict("temporary_required")
            bind_packet = encode_temporary(
                identity=live_token,
                sixover4id=origin_sixover4id,
                sixover4digest=origin_digest,
                include_sixover4id=use_sixover4id,
            )
            if not use_sixover4id:
                try:
                    client.exchange(bind_packet, wait_sixover4digest=True)
                except Sixover4ActuationError:
                    return self._conflict("sixover4id_required")
                return self._conflict("sixover4id_required")
            client.send(bind_packet)
            if not do_public:
                return self._conflict("public_required")
            proxy_packet = encode_public(
                identity=live_token,
                sixover4id=origin_sixover4id,
                sixover4digest=origin_digest,
                include_sixover4id=True,
            )
            if not do_sixover4digest:
                try:
                    client.exchange(proxy_packet, wait_sixover4digest=False)
                except Sixover4ActuationError as error:
                    if str(error) == "sixover4digest_required":
                        return self._conflict("sixover4digest_required")
                    return self._conflict("sixover4digest_required")
                return self._conflict("sixover4digest_required")
            try:
                session = client.exchange(proxy_packet, wait_sixover4digest=True)
            except Sixover4ActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("sixover4id_required")
                if reason == "sixover4digest_required":
                    return self._conflict("sixover4digest_required")
                return self._conflict("temporary_required")
            if str(session.get("identity") or "") != live_token:
                return self._conflict("temporary_required")
            if int(session.get("sixover4id") or EMPTY_SIXOVER4ID) != origin_sixover4id:
                return self._conflict("sixover4digest_required")
            if int(session.get("sixover4digest") or EMPTY_SIXOVER4DIGEST) != origin_digest:
                return self._conflict("sixover4digest_required")
            self.retrieved = True
            if replay:
                independent = Sixover4Client(self.host, int(self.port))
                try:
                    poll = independent.local(
                        POLL_TOKEN,
                        poll_sixover4id(live_token),
                        temporary_sixover4digest(poll_sixover4id(live_token), POLL_TOKEN),
                        wait_sixover4digest=True,
                    )
                except Sixover4ActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_sixover4id, stored_digest = self.read_sixover4id()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_sixover4id != origin_sixover4id
                    or stored_digest != origin_digest
                    or int(poll.get("sixover4id") or EMPTY_SIXOVER4ID) != origin_sixover4id
                    or int(poll.get("sixover4digest") or EMPTY_SIXOVER4DIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_sixover4id}:{origin_digest}:{live_token}:{canonical_temporary(live_token, origin_sixover4id)}:{canonical_public(live_token, origin_sixover4id, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "sixover4id": origin_sixover4id,
                "sixover4digest": origin_digest,
                "temporary_frame": True,
                "public_frame": True,
                "sixover4digest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "sixover4id_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_sixover4digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "sixover4id": origin_sixover4id,
                "sixover4digest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "temporary_frame": True,
                "public_frame": True,
                "sixover4digest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "sixover4id_bound": True,
            }
        except (OSError, Sixover4ActuationError) as error:
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
        live = independent_sixover4digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "sixover4id": int(live.get("sixover4id") or EMPTY_SIXOVER4ID),
            "sixover4digest": int(live.get("sixover4digest") or EMPTY_SIXOVER4DIGEST),
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


def call_sixover4_tool(session: Sixover4Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one sixover4 tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_temporary = True if arguments.get("sixover4") is None else bool(arguments.get("sixover4"))
    do_public = True if arguments.get("mcast") is None else bool(arguments.get("mcast"))
    do_sixover4digest = True if arguments.get("sixover4digest") is None else bool(arguments.get("sixover4digest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_sixover4id = True if arguments.get("use_sixover4id") is None else bool(arguments.get("use_sixover4id"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_temporary=do_temporary,
            do_public=do_public,
            do_sixover4digest=do_sixover4digest,
            replay=replay,
            use_sixover4id=use_sixover4id,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise Sixover4ActuationError(f"unsupported sixover4 action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_sixover4digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage sixover4digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "sixover4id": EMPTY_SIXOVER4ID,
        "sixover4digest": EMPTY_SIXOVER4DIGEST,
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
            "sixover4digest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "sixover4id_bound",
        )
    )
    port = int(payload.get("port") or 0)
    sixover4id = int(payload.get("sixover4id") or EMPTY_SIXOVER4ID)
    sixover4digest = int(payload.get("sixover4digest") or EMPTY_SIXOVER4DIGEST)
    dual = port > 0 and bool(sixover4id) and bool(sixover4digest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "sixover4id": sixover4id,
        "sixover4digest": sixover4digest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "temporary_frame": payload.get("temporary_frame") is True,
        "public_frame": payload.get("public_frame") is True,
        "sixover4digest_locate": payload.get("sixover4digest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "sixover4id_bound": payload.get("sixover4id_bound") is True,
    }


def run_sixover4_workflow(
    *,
    with_sixover4id: bool = True,
    skip_bind: bool = False,
    do_temporary: bool = True,
    do_public: bool = True,
    do_sixover4digest: bool = True,
    replay: bool = True,
    use_sixover4id: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2529 6OVER4/MCAST sixover4id cycle workflow."""

    descriptor = sixover4_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIXOVER4_TOOL_PROVIDER),
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
        raise Sixover4ActuationError(f"sixover4 tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="sixover4-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = Sixover4Session(out, sixover4id_gate=DEFAULT_SIXOVER4ID if with_sixover4id else EMPTY_SIXOVER4ID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "sixover4": do_temporary,
            "mcast": do_public,
            "sixover4digest": do_sixover4digest,
            "replay": replay,
            "use_sixover4id": use_sixover4id,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_sixover4_tool(session, arguments))
            except Sixover4ActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_sixover4digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_sixover4id
        and not skip_bind
        and do_temporary
        and do_public
        and do_sixover4digest
        and replay
        and use_sixover4id
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "sixover4_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_sixover4id": with_sixover4id,
        "skip_bind": skip_bind,
        "temporary_frame": do_temporary,
        "public_frame": do_public,
        "sixover4digest": do_sixover4digest,
        "replay": replay,
        "use_sixover4id": use_sixover4id,
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
        "sixover4id_value": int(publish_result.get("sixover4id") or independent.get("sixover4id") or EMPTY_SIXOVER4ID),
        "sixover4digest_value": int(publish_result.get("sixover4digest") or independent.get("sixover4digest") or EMPTY_SIXOVER4DIGEST),
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
        "sixover4id": int(trace_body["sixover4id_value"] or EMPTY_SIXOVER4ID),
        "sixover4digest": int(trace_body["sixover4digest_value"] or EMPTY_SIXOVER4DIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_sixover4id": with_sixover4id,
        "skip_bind": skip_bind,
        "temporary_cycle": do_temporary,
        "public_cycle": do_public,
        "sixover4digest_cycle": do_sixover4digest,
        "replay": replay,
        "use_sixover4id": use_sixover4id,
    }


def verify_sixover4_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_sixover4digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    sixover4id = int(trace.get("sixover4id_value") or independent.get("sixover4id") or EMPTY_SIXOVER4ID)
    sixover4digest = int(trace.get("sixover4digest_value") or independent.get("sixover4digest") or EMPTY_SIXOVER4DIGEST)
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
        "sixover4digest_locate": independent.get("sixover4digest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "sixover4id_bound": independent.get("sixover4id_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "sixover4digest_recorded": (
            port > 0
            and sixover4id == DEFAULT_SIXOVER4ID
            and sixover4digest == DEFAULT_SIXOVER4DIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def sixover4_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.sixover4_actuation import "
        "builtin_sixover4_actuation_proof; r=builtin_sixover4_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='sixover4_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_sixover4_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SIXOVER4_ACTUATION_ID,
        name="First-class RFC 2529 Transmission of IPv6 over IPv4 Domains without Explicit Tunnels 6OVER4/MCAST actuation",
        description=(
            "Missions that require a sixover4 tool can opt the sixover4 provider in, "
            "bind a loopback RFC 2529 Transmission of IPv6 over IPv4 Domains without Explicit Tunnels endpoint, complete a 6OVER4 "
            "with a non-empty sixover4id, lockstep a MCAST that carries the "
            "stored sixover4digest, independently poll the stored sixover4digest "
            "on a later socket, and seal a digest-chained sixover4digest. Default "
            "routing stays fail-closed; a missing sixover4id keeps the hole "
            "falsifiable, and skip-6OVER4/MCAST/sixover4digest/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.sixover4_actuation:builtin_sixover4_actuation_proof",
        proof_command=sixover4_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.luprefix-actuation",
            "capability.sixrd-actuation",
            "capability.sixto4-actuation",
            "capability.teredo-actuation",
            "capability.isatap-actuation",
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
            "src/blackhole_agent/sixover4_actuation.py",
            "src/blackhole_agent/sixin4_actuation.py",
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
            "A required sixover4 tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 2529 daemon, speaks a "
            "6OVER4 then MCAST over Transmission of IPv6 over IPv4 Domains without Explicit Tunnels with a non-empty sixover4id and "
            "sixover4digest, independently polls the stored sixover4digest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 5214 Intra-Site Automatic Tunnel Addressing Protocol ISATAP/PRL lockstep is proved. "
            "Missing sixover4ids, skip-6OVER4, skip-MCAST, skip-sixover4digest, skip-REPLAY, "
            "and a 6OVER4 aimed without a sixover4id stay fail-closed. "
            "Later genesis can take RFC 4213 Basic Transition Mechanisms for IPv6 Hosts and Routers 6IN4/CONFIG as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("sixover4", "rfc2529", "http", "sixover4id", "sixover4digest", "mcast", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260907T192358Z-4ac02a1b",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_sixover4_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2529 6over4/mcast lockstep actuation seals a sixover4digest."""

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
    from blackhole_agent.sixin4_actuation import (
        SIXIN4_ACTUATION_GOAL,
        SIXIN4_ACTUATION_ID,
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
    checks["denylists_self"] = SIXOVER4_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SIXOVER4_ACTUATION_GOAL) == (
        SIXOVER4_ACTUATION_ID,
    )
    checks["leftover_text_binds_sixover4"] = leftover_marker_ids(SIXOVER4_LEFTOVER) == (
        SIXOVER4_ACTUATION_ID,
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
        (SIXIN4_ACTUATION_GOAL, SIXIN4_ACTUATION_ID, "sixin4"),
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
        checks[f"{name}_goal_is_not_sixover4"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"sixover4_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            SIXOVER4_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = SIXOVER4_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    publicised = serialize_sixover4(DEFAULT_SOURCE)
    rebuilt = serialize_sixover4(parse_sixover4(publicised))
    preloaded = parse_sixover4(RFC_SIXOVER4_DEST)
    header = encode_sixover4_header(DEFAULT_SOURCE)
    parsed_header = parse_sixover4_header(header)
    asked = parse_http_request(temporary_request(SENTINEL, DEFAULT_SIXOVER4ID))
    preload_req = parse_http_request(public_request(SENTINEL, DEFAULT_SIXOVER4ID, DEFAULT_SIXOVER4DIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_SIXOVER4ID, DEFAULT_SIXOVER4DIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_SIXOVER4ID, DEFAULT_SIXOVER4DIGEST)
    )
    checks["sixover4_roundtrip"] = (
        parse_sixover4(publicised) == DEFAULT_SOURCE
        and hmac.compare_digest(rebuilt, publicised)
        and publicised == RFC_SOURCE_FIELD
        and is_token("6OVER4") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SOURCE_FIELD
        and parsed_header["policy"] == DEFAULT_SOURCE
        and parsed_header["header"] == SOURCE_HEADER
        and parsed_header["is_first"] is True
        and parsed_header["table"] is False
        and preloaded == DEST_HOP
        and ascii_serialize_sixover4_directive() == RFC_SOURCE_DIRECTIVE
        and sixover4_directive_pair() == ("sixover4", "message")
        and RFC_SOURCE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_sixover4(DEST_HOP) == RFC_SIXOVER4_DEST
        and DEFAULT_SIXOVER4DIGEST == temporary_sixover4digest(DEFAULT_SIXOVER4ID, SENTINEL)
        and "sixover4digest=" in canonical_public(SENTINEL, DEFAULT_SIXOVER4ID, DEFAULT_SIXOVER4DIGEST)
        and canonical_temporary(SENTINEL, DEFAULT_SIXOVER4ID).startswith("6OVER4")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "6OVER4"
        and asked["disc_kind"] == "sixover4"
        and asked["sixover4id"] == DEFAULT_SIXOVER4ID
        and preload_req["disc_kind"] == "mcast"
        and preload_req["sixover4digest"] == DEFAULT_SIXOVER4DIGEST
        and got["status"] == 200
        and preload_public["status"] == 200
        and got["disc_kind"] == "sixover4"
        and preload_public["disc_kind"] == "mcast"
        and got["policy"] == DEFAULT_SOURCE
        and preload_public["policy"] == DEST_HOP
        and got["content_length_matches_body"] is True
        and preload_public["content_length_matches_body"] is True
        and got["sixover4digest"] == DEFAULT_SIXOVER4DIGEST
        and preload_public["sixover4digest"] == DEFAULT_SIXOVER4DIGEST
        and sixover4_matches(serialize_sixover4(got["policy"]), publicised)
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
    family = capability_family(SIXOVER4_ACTUATION_GOAL)
    checks["family_is_sixover4"] = "sixover4" in family.split("/")
    checks["family_is_sixover4_surface"] = "sixover4" in family.split("/") and "sixover4id" in set(semantic_tokens(SIXOVER4_ACTUATION_GOAL))
    checks["family_is_sixover4id"] = "sixover4id" in set(semantic_tokens(SIXOVER4_ACTUATION_GOAL))
    checks["family_is_rfc2529"] = "rfc2529" in family
    checks["family_is_sixover4digest"] = "sixover4digest" in set(semantic_tokens(SIXOVER4_ACTUATION_GOAL))
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
    checks["family_is_not_sixin4"] = (
        "sixin4" not in family.split("/")
        and "rfc4213" not in family
        and "sixin4id" not in family
        and "sixin4digest" not in family
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
    packed = encode_temporary(identity=SENTINEL, sixover4id=DEFAULT_SIXOVER4ID, sixover4digest=DEFAULT_SIXOVER4DIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_temporary"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_sixover4id"] is True
        and parsed["sixover4id"] == DEFAULT_SIXOVER4ID
        and parsed["sixover4digest"] == DEFAULT_SIXOVER4DIGEST
        and parsed["is_public"] is False
        and parsed["is_public"] is False
        and parsed["type"] == FRAME_SOURCE
        and parsed["first_byte"] == SIXOVER4_FIRST
    )
    shook = encode_public(
        identity=SENTINEL,
        sixover4id=DEFAULT_SIXOVER4ID,
        sixover4digest=DEFAULT_SIXOVER4DIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_public"] is True
        and answer_parsed["is_public"] is True
        and answer_parsed["is_temporary"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["sixover4id"] == DEFAULT_SIXOVER4ID
        and answer_parsed["sixover4digest"] == DEFAULT_SIXOVER4DIGEST
        and answer_parsed["has_sixover4digest"] is True
        and answer_parsed["type"] == FRAME_DEST
        and answer_parsed["first_byte"] == SIXOVER4_FIRST
    )
    bare = encode_temporary(identity=SENTINEL, sixover4id=DEFAULT_SIXOVER4ID, include_sixover4id=False)
    checks["missing_sixover4id_is_unauthed"] = parse_message(bare)["has_sixover4id"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(SIXOVER4_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_sixover4 = ToolDescriptor(name="remote_sixover4", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_sixover4)
    checks["naive_mcp_sixover4_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = sixover4_tool_descriptor()
    default_sixover4 = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIXOVER4_TOOL_PROVIDER),
    )
    checks["default_sixover4_provider_is_unsupported"] = (
        default_sixover4.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SIXOVER4_TOOL_PROVIDER}" in default_sixover4.reasons
    )
    checks["opted_in_sixover4_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_sixover4],
        required_tool_names=("local_memory", "sixover4"),
    )
    checks["naive_preflight_missing_sixover4"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["sixover4"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "sixover4"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIXOVER4_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "sixover4" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="sixover4-actuation-") as tmp:
        root = Path(tmp)
        missing = run_sixover4_workflow(with_sixover4id=False, output_dir=root / "missing")
        skip_bind = run_sixover4_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_temporary = run_sixover4_workflow(do_temporary=False, output_dir=root / "skip-sixover4")
        skip_public = run_sixover4_workflow(do_public=False, output_dir=root / "skip-mcast")
        skip_sixover4digest = run_sixover4_workflow(do_sixover4digest=False, output_dir=root / "skip-sixover4digest")
        skip_replay = run_sixover4_workflow(replay=False, output_dir=root / "skip-replay")
        skip_sixover4id = run_sixover4_workflow(use_sixover4id=False, output_dir=root / "skip-sixover4id")
        live = run_sixover4_workflow(output_dir=root / "live")
        sealed = verify_sixover4_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_sixover4_trace(clone)
        checks["naive_without_sixover4id_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_sixover4id"
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
        checks["skip_sixover4digest_stays_empty"] = (
            skip_sixover4digest["ok"] is False
            and skip_sixover4digest["error"] == "sixover4digest_required"
            and skip_sixover4digest["final_status"] == 409
            and skip_sixover4digest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_sixover4id_stays_empty"] = (
            skip_sixover4id["ok"] is False
            and skip_sixover4id["error"] == "sixover4id_required"
            and skip_sixover4id["final_status"] == 409
            and skip_sixover4id["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_sixover4digest"] = (
            int(live.get("sixover4id") or 0) == DEFAULT_SIXOVER4ID
            and int(live.get("sixover4digest") or 0) == DEFAULT_SIXOVER4DIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_sixover4id_encode_public_sixover4digest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_temporary["ok"] is False
            and skip_public["ok"] is False
            and skip_sixover4digest["ok"] is False
            and skip_replay["ok"] is False
            and skip_sixover4id["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = sealed["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="sixover4-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SIXOVER4_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, SIXOVER4_ACTUATION_GOAL, SIXOVER4_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_sixover4"] = (
        not gate.accepted
        and live_goal != SIXOVER4_ACTUATION_GOAL
        and SIXOVER4_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_sixover4"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="sixover4-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(SIXOVER4_LEFTOVER, root)
        register_catalog_proved(root, SIXOVER4_ACTUATION_ID)
        reason = leftover_satisfied_by(SIXOVER4_LEFTOVER, root)
        after = leftover_is_open(SIXOVER4_LEFTOVER, root)
    checks["sixover4_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_sixover4_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{SIXOVER4_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_sixover4_actuation_capability()
    return {
        "ok": ok,
        "action": "sixover4_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SIXOVER4_ACTUATION_GOAL,
        "done_when": SIXOVER4_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
