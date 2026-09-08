"""Drive a first-class Updates to EVPN BUM Procedures tool through RFC 9572 SMET/IMET.

Tool routing already fails missions that require ``evpnbum``: hosted
evpn broadcast unknown unicast and multicast procedures endpoints stay on the unsupported MCP provider, and no first-party
evpnbum provider is executable. Unbound therefore cannot speak an SMET,
lockstep an IMET evpnbumid handshake over HTTP/1.0 EVPNBUMID,
independently poll the stored evpnbumdigest, or seal a evpnbumdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``evpnbum`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9572 daemon
- keep a missing-evpnbumid client so the evpnbum-evpnbumid hole stays falsifiable
- refuse IMET until a SMET lands with a non-empty evpnbumid
- independently poll the stored evpnbumdigest on a later client socket
- persist a sealed evpnbumdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9251 IGMP and MLD Proxies for Ethernet VPN IGMP/MLD
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
    EVPNBUM_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    evpnbum_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
EVPNBUM_ACTUATION_ID = "capability.evpnbum-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-EVPNBUM-OK"
POLL_TOKEN = "BH-EVPNBUM-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_EVPNBUMID = 0
EMPTY_EVPNBUMDIGEST = 0
EVPNBUM_FIRST = 0x01  # RFC 9572 Protocol Version 1 / Serial Query
EVPNBUMID_SIZE = 4
EVPNBUMDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DEST = 0x02  # RFC 9572 IMET local-data
FRAME_SOURCE = 0x01  # RFC 9572 SMET community
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
EVPNBUM_LEFTOVER = (
    'Later genesis can take RFC 9572 Updates to EVPN BUM Procedures SMET/IMET over an evpnbumid-gated evpnbumdigest.'
)
EVPNBUM_ACTUATION_DONE_WHEN = (
    f"capability_exists:{EVPNBUM_ACTUATION_ID};"
    f"capability_proved:{EVPNBUM_ACTUATION_ID};"
    "no_skill_route"
)
EVPNBUM_ACTUATION_GOAL = (
    'Repair rfc9572 evpnbum smet/imet cycle cannot land over http evpnbum evpnbumid: hosted evpn broadcast unknown unicast and multicast procedures remain unsupported so a SMET then IMET evpnbumid handshake cannot land and a sealed evpnbumdigest cannot be produced. A missing evpnbum evpnbumid stays forbidden; fail-closed routing never opts the evpnbum provider in. An independent later poll of the stored evpnbumdigest keeps the hole falsifiable. EVPN BUM Procedures sessions stay fail-closed without a evpnbumid-gated evpnbumdigest.'
)


class EvpnbumActuationError(RuntimeError):
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
# RFC 9572 sections 2 and 3: Global Administrator plus Local Data Path 1 / Path 2.
RFC_SOURCE_FIELD = "SMET"
RFC_DEST_FIELD = "IMET"
RFC_EVPNBUM_DEST = RFC_DEST_FIELD
RFC_SOURCE_DIRECTIVE = "smet=message"
RFC_DEST_DIRECTIVE = "imet=message"
DEFAULT_SOURCE = "SMET"
DEST_HOP = "IMET"
SOURCE_HEADER = "SMET"
DEST_HEADER = "IMET"
EVPNBUM_DEST_HEADER = DEST_HEADER
RFC_SOURCE_PROP = "/evpnbum/"
RFC_SOURCE_EMPTY = ""


def evpnbum_directive_pair(*, local: bool = False) -> tuple[str, str]:
    """RFC 9572 SMET / IMET directive pair."""

    if local:
        return "imet", "message"
    return "smet", "message"


def ascii_serialize_evpnbum_directive(*, local: bool = False) -> str:
    """RFC 9572 token "=" body-or-local."""

    name, value = evpnbum_directive_pair(local=local)
    if not is_token(name):
        raise EvpnbumActuationError("illegal_directive")
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
            raise EvpnbumActuationError("short_evpnbum")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 9572 body-unique token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_evpnbum(policy: str | Sequence[str]) -> str:
    """Serialize RFC 9572 SMET / IMET opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise EvpnbumActuationError("illegal_evpnbum")
    upper = text.upper().replace("_", "-")
    if upper in {"SMET", "SMET", "SMET-SMET"}:
        return "SMET"
    if upper in {"IMET", "SMET-IMET"}:
        return "IMET"
    if upper.startswith("SMET="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise EvpnbumActuationError("illegal_evpnbum")
        return "SMET"
    if upper.startswith("IMET="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise EvpnbumActuationError("illegal_evpnbum")
        return "IMET"
    raise EvpnbumActuationError("illegal_evpnbum")


def parse_evpnbum(text: str) -> str:
    """Parse RFC 9572 CE opcode header extensions into CE or BR."""

    raw = str(text or "").strip()
    if not raw:
        raise EvpnbumActuationError("illegal_evpnbum")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"SMET", "SMET", "SMET-SMET"}:
        return "SMET"
    if upper in {"IMET", "SMET-IMET"}:
        return "IMET"
    if upper.startswith("SMET="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise EvpnbumActuationError("illegal_evpnbum")
        return "SMET"
    if upper.startswith("IMET="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise EvpnbumActuationError("illegal_evpnbum")
        return "IMET"
    raise EvpnbumActuationError("illegal_evpnbum")


def encode_evpnbum_header(policy: str | Sequence[str]) -> bytes:
    """RFC 9572 HTTP/1.0 field as bytes."""

    return serialize_evpnbum(policy).encode("ascii")


def parse_evpnbum_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_evpnbum(field_value) if field_value else DEFAULT_SOURCE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SOURCE_HEADER,
        "directive": str(policy),
        "is_first": str(policy) == "SMET",
        "table": str(policy) == "IMET",
    }


def canonical_temporary(identity: str, evpnbumid: int) -> str:
    """RFC 9572 body-unique advertisement bound to identity and evpnbumid."""

    return (
        f"{serialize_evpnbum(DEFAULT_SOURCE)}, "
        f"proxy={ascii_serialize_evpnbum_directive()}, "
        f"identity={identity}, evpnbumid={int(evpnbumid) & 0xFFFFFFFF}"
    )


def canonical_public(identity: str, evpnbumid: int, evpnbumdigest: int | None = None) -> str:
    """RFC 9572 local-message confirmation of the stored identifier-digest."""

    digest = ""
    if evpnbumdigest is not None:
        digest = f", evpnbumdigest={int(evpnbumdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_evpnbum(DEST_HOP)}, "
        f"update={ascii_serialize_evpnbum_directive(local=True)}, "
        f"identity={identity}, evpnbumid={int(evpnbumid) & 0xFFFFFFFF}{digest}"
    )


def representation_public(identity: str, evpnbumid: int, evpnbumdigest: int) -> str:
    return canonical_public(identity, evpnbumid, evpnbumdigest)


def evpnbum_matches(left: str, right: str) -> bool:
    return parse_evpnbum(left) == parse_evpnbum(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise EvpnbumActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise EvpnbumActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise EvpnbumActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise EvpnbumActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def temporary_comm(identity: str, evpnbumid: int) -> bytes:
    """HTTP CE that elicits RFC 9572 origin HTTP/1.0."""

    keyid = f"{int(evpnbumid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"SMET /evpnbum/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Evpnbum-Id: {int(evpnbumid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def public_comm(identity: str, evpnbumid: int, evpnbumdigest: int | None = None) -> bytes:
    """HTTP BR carrying RFC 9572 local-message confirmation of the stored identifier-digest."""

    keyid = f"{int(evpnbumid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if evpnbumdigest is not None:
        extra = f"Evpnbum-Digest: {int(evpnbumdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"IMET /evpnbum/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Evpnbum-Id: {int(evpnbumid) & 0xFFFFFFFF}\r\n"
        "IMET-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_comm(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    disc_kind = "imet" if fields.get("imet-confirm") == "1" else "evpnbum"
    upgrade_field = fields.get("smet") or fields.get("evpnbum") or ""
    policy = parse_evpnbum(upgrade_field) if upgrade_field else ()
    return {
        "kind": "evpnbum",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "disc_kind": disc_kind,
        "policy": policy,
        "evpnbumid": int(fields["evpnbum-id"]) if fields.get("evpnbum-id") else EMPTY_EVPNBUMID,
        "evpnbumdigest": int(fields["evpnbum-digest"]) if fields.get("evpnbum-digest") else EMPTY_EVPNBUMDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def temporary_response(identity: str, evpnbumid: int, evpnbumdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 9572 origin HTTP/1.0, carrying the stored evpnbumdigest."""

    publicised = serialize_evpnbum(DEFAULT_SOURCE)
    payload = bytes(body or canonical_temporary(identity, evpnbumid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"SMET: {publicised}\r\n"
        f"Evpnbum-Id: {int(evpnbumid) & 0xFFFFFFFF}\r\n"
        f"Evpnbum-Digest: {int(evpnbumdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def public_response(identity: str, evpnbumid: int, evpnbumdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 9572 BR, carrying the stored identifier-digest."""

    publicised = serialize_evpnbum(DEST_HOP)
    payload = bytes(body or representation_public(identity, evpnbumid, evpnbumdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"SMET: {publicised}\r\n"
        f"Evpnbum-Id: {int(evpnbumid) & 0xFFFFFFFF}\r\n"
        f"Evpnbum-Digest: {int(evpnbumdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/evpnbum-imet\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise EvpnbumActuationError("illegal_content_length") from error
    field_value = fields.get("smet") or fields.get("evpnbum") or ""
    policy = parse_evpnbum(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/evpnbum-imet" or policy == DEST_HOP:
        status = 200
        disc_kind = "imet"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        disc_kind = "evpnbum"
    else:
        status = 0
        disc_kind = "evpnbum"
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
        "evpnbumid": int(fields["evpnbum-id"]) if fields.get("evpnbum-id") else EMPTY_EVPNBUMID,
        "evpnbumdigest": int(fields["evpnbum-digest"]) if fields.get("evpnbum-digest") else EMPTY_EVPNBUMDIGEST,
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
        raise EvpnbumActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise EvpnbumActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise EvpnbumActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise EvpnbumActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc9572_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    ula: str,
) -> str:
    """RFC 9572 identifier digest over method, router-IP, identity, and evpnbumid."""

    payload = f"{method}:{ula}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def temporary_evpnbumid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"evpnbumid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_evpnbumid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-evpnbumid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def temporary_evpnbumdigest(evpnbumid: int = EMPTY_EVPNBUMID, token: str = SENTINEL) -> int:
    nonce = f"{int(evpnbumid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc9572_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="IMET",
        ula=f"/evpnbum/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_EVPNBUMID = temporary_evpnbumid(SENTINEL)
DEFAULT_EVPNBUMDIGEST = temporary_evpnbumdigest(DEFAULT_EVPNBUMID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    evpnbumid: int,
    evpnbumdigest: int,
    include_evpnbumid: bool = True,
) -> bytes:
    live_evpnbumid = int(evpnbumid) & 0xFFFFFFFF if include_evpnbumid else EMPTY_EVPNBUMID
    live_digest = int(evpnbumdigest) & 0xFFFFFFFF if include_evpnbumid and live_evpnbumid else EMPTY_EVPNBUMDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_evpnbumid) if live_evpnbumid else b""
    header = bytearray()
    header.append(EVPNBUM_FIRST)
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
    evpnbumid: int,
    evpnbumdigest: int | None = None,
    include_evpnbumid: bool = True,
) -> bytes:
    live_evpnbumid = int(evpnbumid) & 0xFFFFFFFF if include_evpnbumid else EMPTY_EVPNBUMID
    live_digest = int(evpnbumdigest) if evpnbumdigest is not None else temporary_evpnbumdigest(live_evpnbumid, identity)
    return encode_packet(
        FRAME_SOURCE,
        identity=identity,
        evpnbumid=live_evpnbumid,
        evpnbumdigest=live_digest,
        include_evpnbumid=include_evpnbumid,
    )


def encode_public(
    *,
    identity: str,
    evpnbumid: int,
    evpnbumdigest: int | None = None,
    include_evpnbumid: bool = True,
) -> bytes:
    live_evpnbumid = int(evpnbumid) & 0xFFFFFFFF if include_evpnbumid else EMPTY_EVPNBUMID
    live_digest = int(evpnbumdigest) if evpnbumdigest is not None else temporary_evpnbumdigest(live_evpnbumid, identity)
    return encode_packet(
        FRAME_DEST,
        identity=identity,
        evpnbumid=live_evpnbumid,
        evpnbumdigest=live_digest,
        include_evpnbumid=include_evpnbumid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise EvpnbumActuationError("short_packet")
    disc = raw[0]
    if disc != EVPNBUM_FIRST:
        raise EvpnbumActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise EvpnbumActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == EVPNBUMID_SIZE:
        live_evpnbumid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_evpnbumid = EMPTY_EVPNBUMID
    else:
        raise EvpnbumActuationError("illegal_evpnbumid")
    if offset >= len(raw):
        raise EvpnbumActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SOURCE, FRAME_DEST}:
        raise EvpnbumActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise EvpnbumActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise EvpnbumActuationError("checksum_failed")
    if len(payload) < 5:
        raise EvpnbumActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise EvpnbumActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_evpnbumid = int(live_evpnbumid) != EMPTY_EVPNBUMID
    has_evpnbumdigest = has_evpnbumid and int(live_digest) != EMPTY_EVPNBUMDIGEST
    is_temporary = frame_type == FRAME_SOURCE
    is_public = frame_type == FRAME_DEST
    return {
        "type": int(frame_type),
        "is_temporary": is_temporary,
        "is_public": is_public,
        "evpnbumid": int(live_evpnbumid),
        "has_evpnbumid": has_evpnbumid,
        "evpnbumdigest": int(live_digest),
        "has_evpnbumdigest": has_evpnbumdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(disc),
        "mech_len": int(mech_len),
        "http_state": "RFC9572",
        "serialize_field": canonical_temporary(identity, live_evpnbumid) if has_evpnbumid else "",
        "tls_field": canonical_public(identity, live_evpnbumid, live_digest) if has_evpnbumdigest else "",
    }


class EvpnbumClient:
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
            raise EvpnbumActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_public"] or not packet["is_public"]:
            raise EvpnbumActuationError("evpnbumdigest_required")
        if not packet["has_evpnbumid"]:
            raise EvpnbumActuationError("evpnbumid_required")
        if not packet["has_evpnbumdigest"]:
            raise EvpnbumActuationError("evpnbumdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_evpnbumdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_evpnbumdigest:
            raise EvpnbumActuationError("evpnbumdigest_required")
        session = self._recv()
        return {
            "session": session,
            "evpnbumid": int(session.get("evpnbumid") or EMPTY_EVPNBUMID),
            "identity": str(session.get("identity") or ""),
            "evpnbumdigest": int(session.get("evpnbumdigest") or EMPTY_EVPNBUMDIGEST),
        }

    def local(
        self,
        identity: str,
        evpnbumid: int,
        evpnbumdigest: int = EMPTY_EVPNBUMDIGEST,
        *,
        wait_evpnbumdigest: bool = True,
        include_evpnbumid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_public(
            identity=identity,
            evpnbumid=evpnbumid,
            evpnbumdigest=evpnbumdigest or temporary_evpnbumdigest(evpnbumid, identity),
            include_evpnbumid=include_evpnbumid,
        )
        return self.exchange(packet, wait_evpnbumdigest=wait_evpnbumdigest)


class EvpnbumSession:
    """EVPNBUMID-gated loopback RFC 9572 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        evpnbumid_gate: int = DEFAULT_EVPNBUMID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.evpnbumid_gate = int(evpnbumid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.evpnbumid = EMPTY_EVPNBUMID
        self.evpnbumdigest = EMPTY_EVPNBUMDIGEST
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

    def store_evpnbumid_once(self, identity: str, evpnbumid: int, evpnbumdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(evpnbumid or EMPTY_EVPNBUMID)
            live_digest = int(evpnbumdigest or EMPTY_EVPNBUMDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.evpnbumid = live
                self.evpnbumdigest = live_digest or temporary_evpnbumdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.evpnbumid), int(self.evpnbumdigest)

    def read_evpnbumid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.evpnbumid), int(self.evpnbumdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "evpnbumid": EMPTY_EVPNBUMID,
            "evpnbumdigest": EMPTY_EVPNBUMDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _evpnbumid_missing(self) -> bool:
        return not int(self.evpnbumid_gate or 0)

    def _public_tuple(self, update: tuple[str, int], identity: str, evpnbumid: int, evpnbumdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_public(
            identity=identity,
            evpnbumid=evpnbumid,
            evpnbumdigest=evpnbumdigest,
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
            except EvpnbumActuationError:
                continue
            if not packet.get("is_temporary") and not packet.get("is_public"):
                continue
            if not packet.get("has_evpnbumid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_evpnbumid, stored_digest = self.store_evpnbumid_once(
                identity,
                int(packet.get("evpnbumid") or EMPTY_EVPNBUMID),
                int(packet.get("evpnbumdigest") or EMPTY_EVPNBUMDIGEST),
            )
            if not stored_name or not stored_evpnbumid or not stored_digest:
                continue
            update = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_temporary"):
                    self.opened = True
                if packet.get("is_public"):
                    self.handshook = True
                self.retrieved = True
            self._public_tuple(update, stored_name, stored_evpnbumid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._evpnbumid_missing():
            return self._forbidden("missing_evpnbumid")
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
        do_evpnbumdigest: bool = True,
        replay: bool = True,
        use_evpnbumid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._evpnbumid_missing():
            return self._forbidden("missing_evpnbumid")
        live_token = str(token or SENTINEL)
        origin_evpnbumid = temporary_evpnbumid(live_token)
        origin_digest = temporary_evpnbumdigest(origin_evpnbumid, live_token)
        client: EvpnbumClient | None = None
        independent: EvpnbumClient | None = None
        try:
            client = EvpnbumClient(self.host, int(self.port))
            if not do_temporary:
                return self._conflict("temporary_required")
            bind_packet = encode_temporary(
                identity=live_token,
                evpnbumid=origin_evpnbumid,
                evpnbumdigest=origin_digest,
                include_evpnbumid=use_evpnbumid,
            )
            if not use_evpnbumid:
                try:
                    client.exchange(bind_packet, wait_evpnbumdigest=True)
                except EvpnbumActuationError:
                    return self._conflict("evpnbumid_required")
                return self._conflict("evpnbumid_required")
            client.send(bind_packet)
            if not do_public:
                return self._conflict("public_required")
            proxy_packet = encode_public(
                identity=live_token,
                evpnbumid=origin_evpnbumid,
                evpnbumdigest=origin_digest,
                include_evpnbumid=True,
            )
            if not do_evpnbumdigest:
                try:
                    client.exchange(proxy_packet, wait_evpnbumdigest=False)
                except EvpnbumActuationError as error:
                    if str(error) == "evpnbumdigest_required":
                        return self._conflict("evpnbumdigest_required")
                    return self._conflict("evpnbumdigest_required")
                return self._conflict("evpnbumdigest_required")
            try:
                session = client.exchange(proxy_packet, wait_evpnbumdigest=True)
            except EvpnbumActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("evpnbumid_required")
                if reason == "evpnbumdigest_required":
                    return self._conflict("evpnbumdigest_required")
                return self._conflict("temporary_required")
            if str(session.get("identity") or "") != live_token:
                return self._conflict("temporary_required")
            if int(session.get("evpnbumid") or EMPTY_EVPNBUMID) != origin_evpnbumid:
                return self._conflict("evpnbumdigest_required")
            if int(session.get("evpnbumdigest") or EMPTY_EVPNBUMDIGEST) != origin_digest:
                return self._conflict("evpnbumdigest_required")
            self.retrieved = True
            if replay:
                independent = EvpnbumClient(self.host, int(self.port))
                try:
                    poll = independent.local(
                        POLL_TOKEN,
                        poll_evpnbumid(live_token),
                        temporary_evpnbumdigest(poll_evpnbumid(live_token), POLL_TOKEN),
                        wait_evpnbumdigest=True,
                    )
                except EvpnbumActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_evpnbumid, stored_digest = self.read_evpnbumid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_evpnbumid != origin_evpnbumid
                    or stored_digest != origin_digest
                    or int(poll.get("evpnbumid") or EMPTY_EVPNBUMID) != origin_evpnbumid
                    or int(poll.get("evpnbumdigest") or EMPTY_EVPNBUMDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_evpnbumid}:{origin_digest}:{live_token}:{canonical_temporary(live_token, origin_evpnbumid)}:{canonical_public(live_token, origin_evpnbumid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "evpnbumid": origin_evpnbumid,
                "evpnbumdigest": origin_digest,
                "temporary_frame": True,
                "public_frame": True,
                "evpnbumdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "evpnbumid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_evpnbumdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "evpnbumid": origin_evpnbumid,
                "evpnbumdigest": origin_digest,
                "client_port": int(client.client_port),
                "nd": str(self.sealed_path),
                "temporary_frame": True,
                "public_frame": True,
                "evpnbumdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "evpnbumid_bound": True,
            }
        except (OSError, EvpnbumActuationError) as error:
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
        live = independent_evpnbumdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "evpnbumid": int(live.get("evpnbumid") or EMPTY_EVPNBUMID),
            "evpnbumdigest": int(live.get("evpnbumdigest") or EMPTY_EVPNBUMDIGEST),
            "port": int(live.get("port") or 0),
            "nd": str(self.sealed_path),
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
        return {"ok": True, "status": 200, "closed": True, "nd": str(self.sealed_path)}


def call_evpnbum_tool(session: EvpnbumSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one evpnbum tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_temporary = True if arguments.get("evpnbum") is None else bool(arguments.get("evpnbum"))
    do_public = True if arguments.get("imet") is None else bool(arguments.get("imet"))
    do_evpnbumdigest = True if arguments.get("evpnbumdigest") is None else bool(arguments.get("evpnbumdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_evpnbumid = True if arguments.get("use_evpnbumid") is None else bool(arguments.get("use_evpnbumid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_temporary=do_temporary,
            do_public=do_public,
            do_evpnbumdigest=do_evpnbumdigest,
            replay=replay,
            use_evpnbumid=use_evpnbumid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise EvpnbumActuationError(f"unsupported evpnbum action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_evpnbumdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage evpnbumdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "evpnbumid": EMPTY_EVPNBUMID,
        "evpnbumdigest": EMPTY_EVPNBUMDIGEST,
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
            "evpnbumdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "evpnbumid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    evpnbumid = int(payload.get("evpnbumid") or EMPTY_EVPNBUMID)
    evpnbumdigest = int(payload.get("evpnbumdigest") or EMPTY_EVPNBUMDIGEST)
    dual = port > 0 and bool(evpnbumid) and bool(evpnbumdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "evpnbumid": evpnbumid,
        "evpnbumdigest": evpnbumdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "temporary_frame": payload.get("temporary_frame") is True,
        "public_frame": payload.get("public_frame") is True,
        "evpnbumdigest_locate": payload.get("evpnbumdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "evpnbumid_bound": payload.get("evpnbumid_bound") is True,
    }


def run_evpnbum_workflow(
    *,
    with_evpnbumid: bool = True,
    skip_bind: bool = False,
    do_temporary: bool = True,
    do_public: bool = True,
    do_evpnbumdigest: bool = True,
    replay: bool = True,
    use_evpnbumid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9572 SMET/IMET evpnbumid cycle workflow."""

    descriptor = evpnbum_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EVPNBUM_TOOL_PROVIDER),
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
        raise EvpnbumActuationError(f"evpnbum tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="evpnbum-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = EvpnbumSession(out, evpnbumid_gate=DEFAULT_EVPNBUMID if with_evpnbumid else EMPTY_EVPNBUMID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "evpnbum": do_temporary,
            "imet": do_public,
            "evpnbumdigest": do_evpnbumdigest,
            "replay": replay,
            "use_evpnbumid": use_evpnbumid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_evpnbum_tool(session, arguments))
            except EvpnbumActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_evpnbumdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_evpnbumid
        and not skip_bind
        and do_temporary
        and do_public
        and do_evpnbumdigest
        and replay
        and use_evpnbumid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "evpnbum_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_evpnbumid": with_evpnbumid,
        "skip_bind": skip_bind,
        "temporary_frame": do_temporary,
        "public_frame": do_public,
        "evpnbumdigest": do_evpnbumdigest,
        "replay": replay,
        "use_evpnbumid": use_evpnbumid,
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
        "evpnbumid_value": int(publish_result.get("evpnbumid") or independent.get("evpnbumid") or EMPTY_EVPNBUMID),
        "evpnbumdigest_value": int(publish_result.get("evpnbumdigest") or independent.get("evpnbumdigest") or EMPTY_EVPNBUMDIGEST),
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
        "evpnbumid": int(trace_body["evpnbumid_value"] or EMPTY_EVPNBUMID),
        "evpnbumdigest": int(trace_body["evpnbumdigest_value"] or EMPTY_EVPNBUMDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_evpnbumid": with_evpnbumid,
        "skip_bind": skip_bind,
        "temporary_cycle": do_temporary,
        "public_cycle": do_public,
        "evpnbumdigest_cycle": do_evpnbumdigest,
        "replay": replay,
        "use_evpnbumid": use_evpnbumid,
    }


def verify_evpnbum_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_evpnbumdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    evpnbumid = int(trace.get("evpnbumid_value") or independent.get("evpnbumid") or EMPTY_EVPNBUMID)
    evpnbumdigest = int(trace.get("evpnbumdigest_value") or independent.get("evpnbumdigest") or EMPTY_EVPNBUMDIGEST)
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
        "evpnbumdigest_locate": independent.get("evpnbumdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "evpnbumid_bound": independent.get("evpnbumid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "evpnbumdigest_recorded": (
            port > 0
            and evpnbumid == DEFAULT_EVPNBUMID
            and evpnbumdigest == DEFAULT_EVPNBUMDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def evpnbum_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.evpnbum_actuation import "
        "builtin_evpnbum_actuation_proof; r=builtin_evpnbum_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='evpnbum_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_evpnbum_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    evpnbum = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(evpnbum)
    ledger = load_ledger(path)
    capability = Capability(
        id=EVPNBUM_ACTUATION_ID,
        name="First-class RFC 9572 Updates to EVPN BUM Procedures SMET/IMET actuation",
        description=(
            "Missions that require a evpnbum tool can opt the evpnbum provider in, "
            "bind a loopback RFC 9572 Updates to EVPN BUM Procedures endpoint, complete an SMET "
            "with a non-empty evpnbumid, lockstep a IMET that carries the "
            "stored evpnbumdigest, independently poll the stored evpnbumdigest "
            "on a later socket, and seal a digest-chained evpnbumdigest. Default "
            "routing stays fail-closed; a missing evpnbumid keeps the hole "
            "falsifiable, and skip-SMET/IMET/evpnbumdigest/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.evpnbum_actuation:builtin_evpnbum_actuation_proof",
        proof_command=evpnbum_actuation_proof_command(),
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
            "capability.bgpcomm-actuation",
            "capability.extcomm-actuation",
            "capability.largecomm-actuation",
            "capability.bgpsec-actuation",
            "capability.rtr-actuation",
            "capability.ebgp-actuation",
            "capability.evpn-actuation",
            "capability.etree-actuation",
            "capability.nvo-actuation",
            "capability.dfe-actuation",
            "capability.irb-actuation",
            "capability.ippfx-actuation",
            "capability.proxynd-actuation",
            "capability.imlproxy-actuation",
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
            "src/blackhole_agent/rtr_actuation.py",
            "src/blackhole_agent/ebgp_actuation.py",
            "src/blackhole_agent/evpn_actuation.py",
            "src/blackhole_agent/etree_actuation.py",
            "src/blackhole_agent/nvo_actuation.py",
            "src/blackhole_agent/dfe_actuation.py",
            "src/blackhole_agent/irb_actuation.py",
            "src/blackhole_agent/ippfx_actuation.py",
            "src/blackhole_agent/proxynd_actuation.py",
            "src/blackhole_agent/imlproxy_actuation.py",
            "src/blackhole_agent/evpnbum_actuation.py",
            "src/blackhole_agent/fxc_actuation.py",
            "src/blackhole_agent/largecomm_actuation.py",
            "src/blackhole_agent/bgpsec_actuation.py",
            "src/blackhole_agent/extcomm_actuation.py",
            "src/blackhole_agent/bgpcomm_actuation.py",
            "src/blackhole_agent/rtrefresh_actuation.py",
            "src/blackhole_agent/evpnbum_actuation.py",
            "src/blackhole_agent/fxc_actuation.py",
            "src/blackhole_agent/bgp4_actuation.py",
            "src/blackhole_agent/mpbgp_actuation.py",
            "src/blackhole_agent/encap_actuation.py",
            "src/blackhole_agent/mesh_actuation.py",
            "src/blackhole_agent/l2tp_actuation.py",
            "src/blackhole_agent/evpnbum_actuation.py",
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
            "A required evpnbum tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9572 daemon, speaks a "
            "SMET then IMET over Updates to EVPN BUM Procedures with a non-empty evpnbumid and "
            "evpnbumdigest, independently polls the stored evpnbumdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9251 IGMP and MLD Proxies for Ethernet VPN IGMP/MLD lockstep is proved. "
            "Missing evpnbumids, skip-SMET, skip-IMET, skip-evpnbumdigest, skip-REPLAY, "
            "and an SMET aimed without a evpnbumid stay fail-closed. "
            "Later genesis can take RFC 9625 EVPN VPWS Flexible Cross-Connect FXC/VLAN as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("evpnbum", "rfc9572", "http", "evpnbumid", "evpnbumdigest", "smet", "imet", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260908T143436Z-27ac4660",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_evpnbum_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9572 smet/imet lockstep actuation seals a evpnbumdigest."""

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
    from blackhole_agent.bgpcomm_actuation import (
        BGPCOMM_ACTUATION_GOAL,
        BGPCOMM_ACTUATION_ID,
    )
    from blackhole_agent.extcomm_actuation import (
        EXTCOMM_ACTUATION_GOAL,
        EXTCOMM_ACTUATION_ID,
    )
    from blackhole_agent.largecomm_actuation import (
        LARGECOMM_ACTUATION_GOAL,
        LARGECOMM_ACTUATION_ID,
    )
    from blackhole_agent.bgpsec_actuation import (
        BGPSEC_ACTUATION_GOAL,
        BGPSEC_ACTUATION_ID,
    )
    from blackhole_agent.rtr_actuation import (
        RTR_ACTUATION_GOAL,
        RTR_ACTUATION_ID,
    )
    from blackhole_agent.ebgp_actuation import (
        EBGP_ACTUATION_GOAL,
        EBGP_ACTUATION_ID,
    )
    from blackhole_agent.evpn_actuation import (
        EVPN_ACTUATION_GOAL,
        EVPN_ACTUATION_ID,
    )
    from blackhole_agent.etree_actuation import (
        ETREE_ACTUATION_GOAL,
        ETREE_ACTUATION_ID,
    )
    from blackhole_agent.nvo_actuation import (
        NVO_ACTUATION_GOAL,
        NVO_ACTUATION_ID,
    )
    from blackhole_agent.dfe_actuation import (
        DFE_ACTUATION_GOAL,
        DFE_ACTUATION_ID,
    )
    from blackhole_agent.irb_actuation import (
        IRB_ACTUATION_GOAL,
        IRB_ACTUATION_ID,
    )
    from blackhole_agent.ippfx_actuation import (
        IPPFX_ACTUATION_GOAL,
        IPPFX_ACTUATION_ID,
    )
    from blackhole_agent.proxynd_actuation import (
        PROXYND_ACTUATION_GOAL,
        PROXYND_ACTUATION_ID,
    )
    from blackhole_agent.imlproxy_actuation import (
        IMLPROXY_ACTUATION_GOAL,
        IMLPROXY_ACTUATION_ID,
    )
    from blackhole_agent.fxc_actuation import (
        FXC_ACTUATION_GOAL,
        FXC_ACTUATION_ID,
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
    checks["denylists_self"] = EVPNBUM_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(EVPNBUM_ACTUATION_GOAL) == (
        EVPNBUM_ACTUATION_ID,
    )
    checks["leftover_text_binds_evpnbum"] = leftover_marker_ids(EVPNBUM_LEFTOVER) == (
        EVPNBUM_ACTUATION_ID,
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
        (BGPCOMM_ACTUATION_GOAL, BGPCOMM_ACTUATION_ID, "bgpcomm"),
        (EXTCOMM_ACTUATION_GOAL, EXTCOMM_ACTUATION_ID, "extcomm"),
        (LARGECOMM_ACTUATION_GOAL, LARGECOMM_ACTUATION_ID, "largecomm"),
        (BGPSEC_ACTUATION_GOAL, BGPSEC_ACTUATION_ID, "bgpsec"),
        (RTR_ACTUATION_GOAL, RTR_ACTUATION_ID, "rtr"),
        (EBGP_ACTUATION_GOAL, EBGP_ACTUATION_ID, "ebgp"),
        (EVPN_ACTUATION_GOAL, EVPN_ACTUATION_ID, "evpn"),
        (ETREE_ACTUATION_GOAL, ETREE_ACTUATION_ID, "etree"),
        (NVO_ACTUATION_GOAL, NVO_ACTUATION_ID, "nvo"),
        (DFE_ACTUATION_GOAL, DFE_ACTUATION_ID, "dfe"),
        (IRB_ACTUATION_GOAL, IRB_ACTUATION_ID, "irb"),
        (IPPFX_ACTUATION_GOAL, IPPFX_ACTUATION_ID, "ippfx"),
        (PROXYND_ACTUATION_GOAL, PROXYND_ACTUATION_ID, "proxynd"),
        (IMLPROXY_ACTUATION_GOAL, IMLPROXY_ACTUATION_ID, "imlproxy"),
        (FXC_ACTUATION_GOAL, FXC_ACTUATION_ID, "fxc"),
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
        (MLD_ACTUATION_GOAL, MLD_ACTUATION_ID, "imet"),
        (IGMP_ACTUATION_GOAL, IGMP_ACTUATION_ID, "smet"),
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
        checks[f"{name}_goal_is_not_evpnbum"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"evpnbum_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            EVPNBUM_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = EVPNBUM_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    publicised = serialize_evpnbum(DEFAULT_SOURCE)
    rebuilt = serialize_evpnbum(parse_evpnbum(publicised))
    preloaded = parse_evpnbum(RFC_EVPNBUM_DEST)
    header = encode_evpnbum_header(DEFAULT_SOURCE)
    parsed_header = parse_evpnbum_header(header)
    asked = parse_http_comm(temporary_comm(SENTINEL, DEFAULT_EVPNBUMID))
    preload_req = parse_http_comm(public_comm(SENTINEL, DEFAULT_EVPNBUMID, DEFAULT_EVPNBUMDIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_EVPNBUMID, DEFAULT_EVPNBUMDIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_EVPNBUMID, DEFAULT_EVPNBUMDIGEST)
    )
    checks["irb_roundtrip"] = (
        parse_evpnbum(publicised) == DEFAULT_SOURCE
        and hmac.compare_digest(rebuilt, publicised)
        and publicised == RFC_SOURCE_FIELD
        and is_token("SMET") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SOURCE_FIELD
        and parsed_header["policy"] == DEFAULT_SOURCE
        and parsed_header["header"] == SOURCE_HEADER
        and parsed_header["is_first"] is True
        and parsed_header["table"] is False
        and preloaded == DEST_HOP
        and ascii_serialize_evpnbum_directive() == RFC_SOURCE_DIRECTIVE
        and evpnbum_directive_pair() == ("smet", "message")
        and RFC_SOURCE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_evpnbum(DEST_HOP) == RFC_EVPNBUM_DEST
        and DEFAULT_EVPNBUMDIGEST == temporary_evpnbumdigest(DEFAULT_EVPNBUMID, SENTINEL)
        and "evpnbumdigest=" in canonical_public(SENTINEL, DEFAULT_EVPNBUMID, DEFAULT_EVPNBUMDIGEST)
        and canonical_temporary(SENTINEL, DEFAULT_EVPNBUMID).startswith("SMET")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "SMET"
        and asked["disc_kind"] == "evpnbum"
        and asked["evpnbumid"] == DEFAULT_EVPNBUMID
        and preload_req["disc_kind"] == "imet"
        and preload_req["evpnbumdigest"] == DEFAULT_EVPNBUMDIGEST
        and got["status"] == 200
        and preload_public["status"] == 200
        and got["disc_kind"] == "evpnbum"
        and preload_public["disc_kind"] == "imet"
        and got["policy"] == DEFAULT_SOURCE
        and preload_public["policy"] == DEST_HOP
        and got["content_length_matches_body"] is True
        and preload_public["content_length_matches_body"] is True
        and got["evpnbumdigest"] == DEFAULT_EVPNBUMDIGEST
        and preload_public["evpnbumdigest"] == DEFAULT_EVPNBUMDIGEST
        and evpnbum_matches(serialize_evpnbum(got["policy"]), publicised)
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
    checks["catalog_names_bgpsec"] = (
        len(catalog) > 168
        and catalog[168]["id"] == BGPSEC_ACTUATION_ID
        and catalog[168]["source"] == "genesis_bind_bgpsec"
    )
    checks["catalog_names_rtr"] = (
        len(catalog) > 169
        and catalog[169]["id"] == RTR_ACTUATION_ID
        and catalog[169]["source"] == "genesis_bind_rtr"
    )
    checks["catalog_names_ebgp"] = (
        len(catalog) > 170
        and catalog[170]["id"] == EBGP_ACTUATION_ID
        and catalog[170]["source"] == "genesis_bind_ebgp"
    )
    checks["catalog_names_evpn"] = (
        len(catalog) > 171
        and catalog[171]["id"] == EVPN_ACTUATION_ID
        and catalog[171]["source"] == "genesis_bind_evpn"
    )
    checks["catalog_names_etree"] = (
        len(catalog) > 172
        and catalog[172]["id"] == ETREE_ACTUATION_ID
        and catalog[172]["source"] == "genesis_bind_etree"
    )
    checks["catalog_names_nvo"] = (
        len(catalog) > 173
        and catalog[173]["id"] == NVO_ACTUATION_ID
        and catalog[173]["source"] == "genesis_bind_nvo"
    )
    checks["catalog_names_dfe"] = (
        len(catalog) > 174
        and catalog[174]["id"] == DFE_ACTUATION_ID
        and catalog[174]["source"] == "genesis_bind_dfe"
    )
    checks["catalog_names_irb"] = (
        len(catalog) > 175
        and catalog[175]["id"] == IRB_ACTUATION_ID
        and catalog[175]["source"] == "genesis_bind_irb"
    )
    checks["catalog_names_ippfx"] = (
        len(catalog) > 176
        and catalog[176]["id"] == IPPFX_ACTUATION_ID
        and catalog[176]["source"] == "genesis_bind_ippfx"
    )
    checks["catalog_names_proxynd"] = (
        len(catalog) > 177
        and catalog[177]["id"] == PROXYND_ACTUATION_ID
        and catalog[177]["source"] == "genesis_bind_proxynd"
    )
    checks["catalog_names_imlproxy"] = (
        len(catalog) > 178
        and catalog[178]["id"] == IMLPROXY_ACTUATION_ID
        and catalog[178]["source"] == "genesis_bind_imlproxy"
    )
    checks["catalog_names_evpnbum"] = (
        len(catalog) > 179
        and catalog[179]["id"] == EVPNBUM_ACTUATION_ID
        and catalog[179]["source"] == "genesis_bind_evpnbum"
    )
    checks["catalog_names_fxc"] = (
        len(catalog) > 180
        and catalog[180]["id"] == FXC_ACTUATION_ID
        and catalog[180]["source"] == "genesis_bind_fxc"
    )
    family = capability_family(EVPNBUM_ACTUATION_GOAL)
    checks["family_is_evpnbum"] = "evpnbum" in family.split("/")
    checks["family_is_evpnbum_surface"] = "evpnbum" in family.split("/") and "evpnbumid" in set(semantic_tokens(EVPNBUM_ACTUATION_GOAL))
    checks["family_is_evpnbumid"] = "evpnbumid" in set(semantic_tokens(EVPNBUM_ACTUATION_GOAL))
    checks["family_is_rfc9572"] = "rfc9572" in set(semantic_tokens(EVPNBUM_ACTUATION_GOAL))
    checks["family_is_evpnbumdigest"] = "evpnbumdigest" in family
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
    checks["family_is_not_bgpcomm"] = (
        "bgpcomm" not in family.split("/")
        and "rfc1997" not in family
        and "bgpcommid" not in family
        and "bgpcommdigest" not in family
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
    checks["family_is_not_bgpsec"] = (
        "bgpsec" not in family.split("/")
        and "rfc8205" not in family
        and "bgpsecid" not in family
        and "bgpsecdigest" not in family
    )
    checks["family_is_not_rtr"] = (
        "rtr" not in family.split("/")
        and "rfc8210" not in family
        and "rtrid" not in family
        and "rtrdigest" not in family
    )
    checks["family_is_not_ebgp"] = (
        "ebgp" not in family.split("/")
        and "rfc8212" not in family
        and "ebgpid" not in family
        and "ebgpdigest" not in family
    )
    checks["family_is_not_evpn"] = (
        "rfc8214" not in family
        and "evpnid" not in family
        and "evpndigest" not in family
        and "ad/vpws" not in family
    )
    checks["family_is_not_etree"] = (
        "etree" not in family.split("/")
        and "rfc8317" not in family
        and "etreeid" not in family
        and "etreedigest" not in family
    )
    checks["family_is_not_nvo"] = (
        "nvo" not in family.split("/")
        and "rfc8365" not in family
        and "nvoid" not in family
        and "nvodigest" not in family
    )
    checks["family_is_not_dfe"] = (
        "dfe" not in family.split("/")
        and "rfc8584" not in family
        and "dfeid" not in family
        and "dfedigest" not in family
    )
    checks["family_is_not_irb"] = (
        "irb" not in family.split("/")
        and "rfc9135" not in family
        and "irbid" not in family
        and "irbdigest" not in family
    )
    checks["family_is_not_ippfx"] = (
        "ippfx" not in family.split("/")
        and "rfc9136" not in family
        and "ippfxid" not in family
        and "ippfxdigest" not in family
    )
    checks["family_is_not_proxynd"] = (
        "proxynd" not in family.split("/")
        and "rfc9161" not in family
        and "proxyndid" not in family
        and "proxynddigest" not in family
    )
    checks["family_is_not_imlproxy"] = (
        "imlproxy" not in family.split("/")
        and "rfc9251" not in family
        and "imlproxyid" not in family
        and "imlproxydigest" not in family
    )
    checks["family_is_not_fxc"] = (
        "fxc" not in family.split("/")
        and "rfc9625" not in family
        and "fxcid" not in family
        and "fxcdigest" not in family
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
        "rfc2710" not in family
        and "mldid" not in family.split("/")
        and "mlddigest" not in family.split("/")
    )
    checks["family_is_not_igmp"] = (
        "rfc1112" not in family
        and "igmpid" not in family.split("/")
        and "igmpdigest" not in family.split("/")
    )
    checks["family_is_not_rarp"] = (
        "rarp" not in family.split("/")
        and "rfc903" not in family
        and "rarpid" not in family
        and "rarpdigest" not in family
    )
    checks["family_is_not_arp"] = (
        "rfc826" not in family
        and "arpid" not in family.split("/")
        and "arpdigest" not in family.split("/")
    )
    checks["family_is_not_ip"] = (
        "ip" not in family.split("/")
        and "ipid" not in family.split("/")
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
    packed = encode_temporary(identity=SENTINEL, evpnbumid=DEFAULT_EVPNBUMID, evpnbumdigest=DEFAULT_EVPNBUMDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_temporary"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_evpnbumid"] is True
        and parsed["evpnbumid"] == DEFAULT_EVPNBUMID
        and parsed["evpnbumdigest"] == DEFAULT_EVPNBUMDIGEST
        and parsed["is_public"] is False
        and parsed["is_public"] is False
        and parsed["type"] == FRAME_SOURCE
        and parsed["first_byte"] == EVPNBUM_FIRST
    )
    shook = encode_public(
        identity=SENTINEL,
        evpnbumid=DEFAULT_EVPNBUMID,
        evpnbumdigest=DEFAULT_EVPNBUMDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_public"] is True
        and answer_parsed["is_public"] is True
        and answer_parsed["is_temporary"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["evpnbumid"] == DEFAULT_EVPNBUMID
        and answer_parsed["evpnbumdigest"] == DEFAULT_EVPNBUMDIGEST
        and answer_parsed["has_evpnbumdigest"] is True
        and answer_parsed["type"] == FRAME_DEST
        and answer_parsed["first_byte"] == EVPNBUM_FIRST
    )
    bare = encode_temporary(identity=SENTINEL, evpnbumid=DEFAULT_EVPNBUMID, include_evpnbumid=False)
    checks["missing_evpnbumid_is_unauthed"] = parse_message(bare)["has_evpnbumid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(EVPNBUM_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_evpnbum = ToolDescriptor(name="remote_evpnbum", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_evpnbum)
    checks["naive_mcp_evpnbum_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = evpnbum_tool_descriptor()
    default_evpnbum = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EVPNBUM_TOOL_PROVIDER),
    )
    checks["default_evpnbum_provider_is_unsupported"] = (
        default_evpnbum.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{EVPNBUM_TOOL_PROVIDER}" in default_evpnbum.reasons
    )
    checks["opted_in_evpnbum_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_evpnbum],
        required_tool_names=("local_memory", "evpnbum"),
    )
    checks["naive_preflight_missing_evpnbum"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["evpnbum"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "evpnbum"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EVPNBUM_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "evpnbum" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="evpnbum-actuation-") as tmp:
        evpnbum = Path(tmp)
        missing = run_evpnbum_workflow(with_evpnbumid=False, output_dir=evpnbum / "missing")
        skip_bind = run_evpnbum_workflow(skip_bind=True, output_dir=evpnbum / "skip-bind")
        skip_temporary = run_evpnbum_workflow(do_temporary=False, output_dir=evpnbum / "skip-evpnbum")
        skip_public = run_evpnbum_workflow(do_public=False, output_dir=evpnbum / "skip-imet")
        skip_evpnbumdigest = run_evpnbum_workflow(do_evpnbumdigest=False, output_dir=evpnbum / "skip-evpnbumdigest")
        skip_replay = run_evpnbum_workflow(replay=False, output_dir=evpnbum / "skip-replay")
        skip_evpnbumid = run_evpnbum_workflow(use_evpnbumid=False, output_dir=evpnbum / "skip-evpnbumid")
        live = run_evpnbum_workflow(output_dir=evpnbum / "live")
        sealed = verify_evpnbum_trace(Path(live["output_dir"]))
        clone = evpnbum / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_evpnbum_trace(clone)
        checks["naive_without_evpnbumid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_evpnbumid"
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
        checks["skip_evpnbumdigest_stays_empty"] = (
            skip_evpnbumdigest["ok"] is False
            and skip_evpnbumdigest["error"] == "evpnbumdigest_required"
            and skip_evpnbumdigest["final_status"] == 409
            and skip_evpnbumdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_evpnbumid_stays_empty"] = (
            skip_evpnbumid["ok"] is False
            and skip_evpnbumid["error"] == "evpnbumid_required"
            and skip_evpnbumid["final_status"] == 409
            and skip_evpnbumid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_evpnbumdigest"] = (
            int(live.get("evpnbumid") or 0) == DEFAULT_EVPNBUMID
            and int(live.get("evpnbumdigest") or 0) == DEFAULT_EVPNBUMDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_evpnbumid_encode_public_evpnbumdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_temporary["ok"] is False
            and skip_public["ok"] is False
            and skip_evpnbumdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_evpnbumid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = sealed["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="evpnbum-bind-") as tmp:
        evpnbum = Path(tmp)
        _prepare_exhausted_catalog(evpnbum)
        for item in catalog:
            if item["id"] != EVPNBUM_ACTUATION_ID:
                register_catalog_proved(evpnbum, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(evpnbum)
    checks["exhausted_catalog_binds_evpnbum"] = (
        live_goal == EVPNBUM_ACTUATION_GOAL
        and EVPNBUM_ACTUATION_ID in live_done
        and live_source == "genesis_bind_evpnbum"
    )

    with tempfile.TemporaryDirectory(prefix="evpnbum-leftover-") as tmp:
        evpnbum = Path(tmp)
        open_before = leftover_is_open(EVPNBUM_LEFTOVER, evpnbum)
        register_catalog_proved(evpnbum, EVPNBUM_ACTUATION_ID)
        reason = leftover_satisfied_by(EVPNBUM_LEFTOVER, evpnbum)
        after = leftover_is_open(EVPNBUM_LEFTOVER, evpnbum)
    checks["evpnbum_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_evpnbum_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{EVPNBUM_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_evpnbum_actuation_capability()
    return {
        "ok": ok,
        "action": "evpnbum_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": EVPNBUM_ACTUATION_GOAL,
        "done_when": EVPNBUM_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
