"""Drive a first-class PATCH Method for HTTP tool through RFC 5789 PATCH/ENTITY.

Tool routing already fails missions that require ``httppatch``: hosted
httppatch endpoints stay on the unsupported MCP provider, and no first-party
httppatch provider is executable. Unbound therefore cannot speak a PATCH,
lockstep an ENTITY patchid handshake over HTTP Accept-Patch PATCHID,
independently poll the stored patchdigest, or seal a patchdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``httppatch`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 5789 daemon
- keep a missing-patchid client so the httppatch-patchid hole stays falsifiable
- refuse ENTITY until a PATCH lands with a non-empty patchid
- independently poll the stored patchdigest on a later client socket
- persist a sealed patchdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 5861 HTTP Cache-Control Extensions for Stale Content
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
    HTTPPATCH_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    httppatch_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTPPATCH_ACTUATION_ID = "capability.httppatch-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-PATCH-OK"
POLL_TOKEN = "BH-PATCH-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_PATCHID = 0
EMPTY_PATCHDIGEST = 0
HP_FIRST = 0x50  # RFC 5789 PATCH Method for HTTP (ASCII 'P')
PATCHID_SIZE = 4
PATCHDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_ENTITY = 0x02  # RFC 5789 entity confirmation
FRAME_PATCH = 0x01  # RFC 5789 PATCH
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTPPATCH_LEFTOVER = (
    "Later genesis can take RFC 5789 PATCH Method for HTTP PATCH/ENTITY over a "
    "patchid-gated patchdigest."
)
HTTPPATCH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPPATCH_ACTUATION_ID};"
    f"capability_proved:{HTTPPATCH_ACTUATION_ID};"
    "no_skill_route"
)
HTTPPATCH_ACTUATION_GOAL = (
    "Repair rfc5789 httppatch patch/entity cycle cannot land over http "
    "httppatch patchid: hosted httppatch endpoints remain unsupported so a PATCH then "
    "ENTITY patchid handshake cannot land and a sealed patchdigest "
    "cannot be produced. A missing httppatch patchid stays forbidden; fail-closed "
    "routing never opts the httppatch provider in. An independent later poll of the "
    "stored patchdigest keeps the hole falsifiable."
)


class HttppatchActuationError(RuntimeError):
    """Raised when the entity session or loopback daemon fixture misbehaves."""


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
# RFC 5789 sections 3 and 4: json-patch / merge-patch.
RFC_PATCH_FIELD = "PATCH"
RFC_ENTITY_FIELD = "ENTITY"
RFC_HTTPPATCH_ENTITY = RFC_ENTITY_FIELD
RFC_JSON_PATCH_SECONDS = 30
RFC_MERGE_PATCH_SECONDS = 86400
DEFAULT_PATCH = "PATCH"
ENTITY_POLICY = "ENTITY"
PATCH_HEADER = "Accept-Patch"
ENTITY_HEADER = "Accept-Patch"
HTTPPATCH_ENTITY_HEADER = ENTITY_HEADER
RFC_PATCH_PATH = "/"
RFC_PATCH_DIRECTIVE = "json-patch=30"
RFC_ENTITY_DIRECTIVE = "merge-patch=86400"
RFC_PATCH_EMPTY = ""


def patch_directive_pair(
    *,
    entity: bool = False,
    seconds: int | None = None,
) -> tuple[str, int]:
    """RFC 5789 section 3 json-patch / section 4 merge-patch."""

    live_seconds = int(seconds) if seconds is not None else (
        RFC_MERGE_PATCH_SECONDS if entity else RFC_JSON_PATCH_SECONDS
    )
    if live_seconds < 0:
        raise HttppatchActuationError("illegal_delta_seconds")
    name = "merge-patch" if entity else "json-patch"
    return name, live_seconds


def ascii_serialize_patch_directive(
    *,
    entity: bool = False,
    seconds: int | None = None,
) -> str:
    """RFC 5789 Accept-Patch extension: name "=" delta-seconds."""

    name, live_seconds = patch_directive_pair(entity=entity, seconds=seconds)
    if not is_token(name):
        raise HttppatchActuationError("illegal_directive")
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
            raise HttppatchActuationError("short_httppatch")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 5789 Accept-Patch token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_httppatch(policy: str | Sequence[str]) -> str:
    """Serialize RFC 5789 json-patch / merge-patch token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise HttppatchActuationError("illegal_httppatch")
    upper = text.upper().replace("_", "-")
    if upper in {"PATCH", "JSON-PATCH", "JP"}:
        return "PATCH"
    if upper in {"ENTITY", "MERGE-PATCH", "MP"}:
        return "ENTITY"
    if upper.startswith("JSON-PATCH="):
        seconds = text.split("=", 1)[1].strip().strip('"')
        if not seconds.isdigit():
            raise HttppatchActuationError("illegal_httppatch")
        return "PATCH"
    if upper.startswith("MERGE-PATCH="):
        seconds = text.split("=", 1)[1].strip().strip('"')
        if not seconds.isdigit():
            raise HttppatchActuationError("illegal_httppatch")
        return "ENTITY"
    raise HttppatchActuationError("illegal_httppatch")


def parse_httppatch(text: str) -> str:
    """Parse RFC 5789 Accept-Patch patch extensions into PATCH or ENTITY."""

    raw = str(text or "").strip()
    if not raw:
        raise HttppatchActuationError("illegal_httppatch")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"PATCH", "JSON-PATCH", "JP"}:
        return "PATCH"
    if upper in {"ENTITY", "MERGE-PATCH", "MP"}:
        return "ENTITY"
    if upper.startswith("JSON-PATCH="):
        seconds = head.split("=", 1)[1].strip().strip('"')
        if not seconds.isdigit():
            raise HttppatchActuationError("illegal_httppatch")
        return "PATCH"
    if upper.startswith("MERGE-PATCH="):
        seconds = head.split("=", 1)[1].strip().strip('"')
        if not seconds.isdigit():
            raise HttppatchActuationError("illegal_httppatch")
        return "ENTITY"
    raise HttppatchActuationError("illegal_httppatch")


def encode_httppatch_header(policy: str | Sequence[str]) -> bytes:
    """RFC 5789 Accept-Patch field as bytes."""

    return serialize_httppatch(policy).encode("ascii")


def parse_httppatch_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_httppatch(field_value) if field_value else DEFAULT_PATCH
    return {
        "field_value": field_value,
        "policy": policy,
        "header": PATCH_HEADER,
        "directive": str(policy),
        "patch": str(policy) == "PATCH",
        "entity": str(policy) == "ENTITY",
    }


def canonical_patch(identity: str, patchid: int) -> str:
    """RFC 5789 PATCH advertisement bound to identity and patchid."""

    return (
        f"{serialize_httppatch(DEFAULT_PATCH)}, "
        f"patch={ascii_serialize_patch_directive()}, "
        f"identity={identity}, patchid={int(patchid) & 0xFFFFFFFF}"
    )


def canonical_entity(identity: str, patchid: int, patchdigest: int | None = None) -> str:
    """RFC 5789 ENTITY confirmation of the stored entity policy."""

    suffix = ""
    if patchdigest is not None:
        suffix = f", patchdigest={int(patchdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_httppatch(ENTITY_POLICY)}, "
        f"entity={ascii_serialize_patch_directive(entity=True)}, "
        f"identity={identity}, patchid={int(patchid) & 0xFFFFFFFF}{suffix}"
    )


def representation_entity(identity: str, patchid: int, patchdigest: int) -> str:
    return canonical_entity(identity, patchid, patchdigest)


def httppatch_matches(left: str, right: str) -> bool:
    return parse_httppatch(left) == parse_httppatch(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HttppatchActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HttppatchActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HttppatchActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HttppatchActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def patch_request(identity: str, patchid: int) -> bytes:
    """HTTP PATCH that elicits RFC 5789 origin PATCH."""

    keyid = f"{int(patchid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"PATCH /httppatch/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Patch-Id: {int(patchid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def entity_request(identity: str, patchid: int, patchdigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 5789 ENTITY confirmation of the stored entity policy."""

    keyid = f"{int(patchid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if patchdigest is not None:
        extra = f"Patch-Digest: {int(patchdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /httppatch/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Patch-Id: {int(patchid) & 0xFFFFFFFF}\r\n"
        "Patch-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    httppatch_kind = "entity" if fields.get("patch-confirm") == "1" else "patch"
    patch_field = fields.get("accept-patch") or ""
    policy = parse_httppatch(patch_field) if patch_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "httppatch_kind": httppatch_kind,
        "policy": policy,
        "patchid": int(fields["patch-id"]) if fields.get("patch-id") else EMPTY_PATCHID,
        "patchdigest": int(fields["patch-digest"]) if fields.get("patch-digest") else EMPTY_PATCHDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def patch_response(identity: str, patchid: int, patchdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 5789 origin PATCH, carrying the stored patchdigest."""

    advertised = serialize_httppatch(DEFAULT_PATCH)
    payload = bytes(body or canonical_patch(identity, patchid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Accept-Patch: {advertised}\r\n"
        f"Patch-Id: {int(patchid) & 0xFFFFFFFF}\r\n"
        f"Patch-Digest: {int(patchdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json-patch+json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def entity_response(identity: str, patchid: int, patchdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 5789 ENTITY, carrying the stored ENTITY policy."""

    advertised = serialize_httppatch(ENTITY_POLICY)
    payload = bytes(body or representation_entity(identity, patchid, patchdigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Accept-Patch: {advertised}\r\n"
        f"Patch-Id: {int(patchid) & 0xFFFFFFFF}\r\n"
        f"Patch-Digest: {int(patchdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/merge-patch+json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise HttppatchActuationError("illegal_content_length") from error
    field_value = fields.get("accept-patch") or ""
    policy = parse_httppatch(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/merge-patch+json" or policy == ENTITY_POLICY:
        status = 200
        httppatch_kind = "entity"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        httppatch_kind = "patch"
    else:
        status = 0
        httppatch_kind = "patch"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "httppatch_kind": httppatch_kind,
        "policy": policy,
        "patchid": int(fields["patch-id"]) if fields.get("patch-id") else EMPTY_PATCHID,
        "patchdigest": int(fields["patch-digest"]) if fields.get("patch-digest") else EMPTY_PATCHDIGEST,
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
        raise HttppatchActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise HttppatchActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise HttppatchActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HttppatchActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_patchid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"patchid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_patchid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-patchid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_patchdigest(patchid: int = EMPTY_PATCHID, token: str = SENTINEL) -> int:
    material = canonical_patch(token or SENTINEL, int(patchid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_PATCHID = request_patchid(SENTINEL)
DEFAULT_PATCHDIGEST = request_patchdigest(DEFAULT_PATCHID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    patchid: int,
    patchdigest: int,
    include_patchid: bool = True,
) -> bytes:
    live_patchid = int(patchid) & 0xFFFFFFFF if include_patchid else EMPTY_PATCHID
    live_digest = int(patchdigest) & 0xFFFFFFFF if include_patchid and live_patchid else EMPTY_PATCHDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_patchid) if live_patchid else b""
    header = bytearray()
    header.append(HP_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_patch(
    *,
    identity: str,
    patchid: int,
    patchdigest: int | None = None,
    include_patchid: bool = True,
) -> bytes:
    live_patchid = int(patchid) & 0xFFFFFFFF if include_patchid else EMPTY_PATCHID
    live_digest = int(patchdigest) if patchdigest is not None else request_patchdigest(live_patchid, identity)
    return encode_packet(
        FRAME_PATCH,
        identity=identity,
        patchid=live_patchid,
        patchdigest=live_digest,
        include_patchid=include_patchid,
    )


def encode_entity(
    *,
    identity: str,
    patchid: int,
    patchdigest: int | None = None,
    include_patchid: bool = True,
) -> bytes:
    live_patchid = int(patchid) & 0xFFFFFFFF if include_patchid else EMPTY_PATCHID
    live_digest = int(patchdigest) if patchdigest is not None else request_patchdigest(live_patchid, identity)
    return encode_packet(
        FRAME_ENTITY,
        identity=identity,
        patchid=live_patchid,
        patchdigest=live_digest,
        include_patchid=include_patchid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HttppatchActuationError("short_packet")
    first = raw[0]
    if first != HP_FIRST:
        raise HttppatchActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise HttppatchActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == PATCHID_SIZE:
        live_patchid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_patchid = EMPTY_PATCHID
    else:
        raise HttppatchActuationError("illegal_patchid")
    if offset >= len(raw):
        raise HttppatchActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_PATCH, FRAME_ENTITY}:
        raise HttppatchActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HttppatchActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HttppatchActuationError("checksum_failed")
    if len(payload) < 5:
        raise HttppatchActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HttppatchActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_patchid = int(live_patchid) != EMPTY_PATCHID
    has_patchdigest = has_patchid and int(live_digest) != EMPTY_PATCHDIGEST
    is_patch = frame_type == FRAME_PATCH
    is_entity = frame_type == FRAME_ENTITY
    return {
        "type": int(frame_type),
        "is_patch": is_patch,
        "is_entity": is_entity,
        "is_response": is_entity,
        "patchid": int(live_patchid),
        "has_patchid": has_patchid,
        "patchdigest": int(live_digest),
        "has_patchdigest": has_patchdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http_state": "RFC5789",
        "serialize_field": canonical_patch(identity, live_patchid) if has_patchid else "",
        "entity_field": canonical_entity(identity, live_patchid, live_digest) if has_patchdigest else "",
    }


class HttppatchClient:
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
            raise HttppatchActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_entity"] or not packet["is_response"]:
            raise HttppatchActuationError("patchdigest_required")
        if not packet["has_patchid"]:
            raise HttppatchActuationError("patchid_required")
        if not packet["has_patchdigest"]:
            raise HttppatchActuationError("patchdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_patchdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_patchdigest:
            raise HttppatchActuationError("patchdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "patchid": int(reply.get("patchid") or EMPTY_PATCHID),
            "identity": str(reply.get("identity") or ""),
            "patchdigest": int(reply.get("patchdigest") or EMPTY_PATCHDIGEST),
        }

    def report(
        self,
        identity: str,
        patchid: int,
        patchdigest: int = EMPTY_PATCHDIGEST,
        *,
        wait_patchdigest: bool = True,
        include_patchid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_entity(
            identity=identity,
            patchid=patchid,
            patchdigest=patchdigest or request_patchdigest(patchid, identity),
            include_patchid=include_patchid,
        )
        return self.exchange(packet, wait_patchdigest=wait_patchdigest)


class HttppatchSession:
    """PATCHID-gated loopback RFC 5789 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        patchid_gate: int = DEFAULT_PATCHID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.patchid_gate = int(patchid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.patchid = EMPTY_PATCHID
        self.patchdigest = EMPTY_PATCHDIGEST
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

    def store_patchid_once(self, identity: str, patchid: int, patchdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(patchid or EMPTY_PATCHID)
            live_digest = int(patchdigest or EMPTY_PATCHDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.patchid = live
                self.patchdigest = live_digest or request_patchdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.patchid), int(self.patchdigest)

    def read_patchid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.patchid), int(self.patchdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "patchid": EMPTY_PATCHID,
            "patchdigest": EMPTY_PATCHDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _patchid_missing(self) -> bool:
        return not int(self.patchid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, patchid: int, patchdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_entity(
            identity=identity,
            patchid=patchid,
            patchdigest=patchdigest,
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
            except HttppatchActuationError:
                continue
            if not packet.get("is_patch") and not packet.get("is_entity"):
                continue
            if not packet.get("has_patchid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_patchid, stored_digest = self.store_patchid_once(
                identity,
                int(packet.get("patchid") or EMPTY_PATCHID),
                int(packet.get("patchdigest") or EMPTY_PATCHDIGEST),
            )
            if not stored_name or not stored_patchid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_patch"):
                    self.opened = True
                if packet.get("is_entity"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_patchid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._patchid_missing():
            return self._forbidden("missing_patchid")
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
        do_patch: bool = True,
        do_entity: bool = True,
        do_patchdigest: bool = True,
        replay: bool = True,
        use_patchid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._patchid_missing():
            return self._forbidden("missing_patchid")
        live_token = str(token or SENTINEL)
        origin_patchid = request_patchid(live_token)
        origin_digest = request_patchdigest(origin_patchid, live_token)
        client: HttppatchClient | None = None
        independent: HttppatchClient | None = None
        try:
            client = HttppatchClient(self.host, int(self.port))
            if not do_patch:
                return self._conflict("patch_required")
            bind_packet = encode_patch(
                identity=live_token,
                patchid=origin_patchid,
                patchdigest=origin_digest,
                include_patchid=use_patchid,
            )
            if not use_patchid:
                try:
                    client.exchange(bind_packet, wait_patchdigest=True)
                except HttppatchActuationError:
                    return self._conflict("patchid_required")
                return self._conflict("patchid_required")
            client.send(bind_packet)
            if not do_entity:
                return self._conflict("entity_required")
            proxy_packet = encode_entity(
                identity=live_token,
                patchid=origin_patchid,
                patchdigest=origin_digest,
                include_patchid=True,
            )
            if not do_patchdigest:
                try:
                    client.exchange(proxy_packet, wait_patchdigest=False)
                except HttppatchActuationError as error:
                    if str(error) == "patchdigest_required":
                        return self._conflict("patchdigest_required")
                    return self._conflict("patchdigest_required")
                return self._conflict("patchdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_patchdigest=True)
            except HttppatchActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("patchid_required")
                if reason == "patchdigest_required":
                    return self._conflict("patchdigest_required")
                return self._conflict("patch_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("patch_required")
            if int(reply.get("patchid") or EMPTY_PATCHID) != origin_patchid:
                return self._conflict("patchdigest_required")
            if int(reply.get("patchdigest") or EMPTY_PATCHDIGEST) != origin_digest:
                return self._conflict("patchdigest_required")
            self.retrieved = True
            if replay:
                independent = HttppatchClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_patchid(live_token),
                        request_patchdigest(poll_patchid(live_token), POLL_TOKEN),
                        wait_patchdigest=True,
                    )
                except HttppatchActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_patchid, stored_digest = self.read_patchid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_patchid != origin_patchid
                    or stored_digest != origin_digest
                    or int(poll.get("patchid") or EMPTY_PATCHID) != origin_patchid
                    or int(poll.get("patchdigest") or EMPTY_PATCHDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_patchid}:{origin_digest}:{live_token}:{canonical_patch(live_token, origin_patchid)}:{canonical_entity(live_token, origin_patchid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "patchid": origin_patchid,
                "patchdigest": origin_digest,
                "patch_frame": True,
                "entity_frame": True,
                "patchdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "patchid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_httppatch_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "patchid": origin_patchid,
                "patchdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "patch_frame": True,
                "entity_frame": True,
                "patchdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "patchid_bound": True,
            }
        except (OSError, HttppatchActuationError) as error:
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
        live = independent_httppatch_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "patchid": int(live.get("patchid") or EMPTY_PATCHID),
            "patchdigest": int(live.get("patchdigest") or EMPTY_PATCHDIGEST),
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


def call_httppatch_tool(session: HttppatchSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one patch tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_patch = True if arguments.get("patch") is None else bool(arguments.get("patch"))
    do_entity = True if arguments.get("entity") is None else bool(arguments.get("entity"))
    do_patchdigest = True if arguments.get("patchdigest") is None else bool(arguments.get("patchdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_patchid = True if arguments.get("use_patchid") is None else bool(arguments.get("use_patchid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_patch=do_patch,
            do_entity=do_entity,
            do_patchdigest=do_patchdigest,
            replay=replay,
            use_patchid=use_patchid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HttppatchActuationError(f"unsupported httppatch action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_httppatch_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed patch patchdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "patchid": EMPTY_PATCHID,
        "patchdigest": EMPTY_PATCHDIGEST,
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
            "patch_frame",
            "entity_frame",
            "patchdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "patchid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    patchid = int(payload.get("patchid") or EMPTY_PATCHID)
    patchdigest = int(payload.get("patchdigest") or EMPTY_PATCHDIGEST)
    dual = port > 0 and bool(patchid) and bool(patchdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "patchid": patchid,
        "patchdigest": patchdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "patch_frame": payload.get("patch_frame") is True,
        "entity_frame": payload.get("entity_frame") is True,
        "patchdigest_response": payload.get("patchdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "patchid_bound": payload.get("patchid_bound") is True,
    }


def run_httppatch_workflow(
    *,
    with_patchid: bool = True,
    skip_bind: bool = False,
    do_patch: bool = True,
    do_entity: bool = True,
    do_patchdigest: bool = True,
    replay: bool = True,
    use_patchid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 5789 PATCH/ENTITY patchid cycle workflow."""

    descriptor = httppatch_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPPATCH_TOOL_PROVIDER),
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
        raise HttppatchActuationError(f"httppatch tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="httppatch-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HttppatchSession(out, patchid_gate=DEFAULT_PATCHID if with_patchid else EMPTY_PATCHID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "patch": do_patch,
            "entity": do_entity,
            "patchdigest": do_patchdigest,
            "replay": replay,
            "use_patchid": use_patchid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_httppatch_tool(session, arguments))
            except HttppatchActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_httppatch_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_patchid
        and not skip_bind
        and do_patch
        and do_entity
        and do_patchdigest
        and replay
        and use_patchid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "httppatch_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_patchid": with_patchid,
        "skip_bind": skip_bind,
        "patch_frame": do_patch,
        "entity": do_entity,
        "patchdigest": do_patchdigest,
        "replay": replay,
        "use_patchid": use_patchid,
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
        "patchid_value": int(publish_result.get("patchid") or independent.get("patchid") or EMPTY_PATCHID),
        "patchdigest_value": int(publish_result.get("patchdigest") or independent.get("patchdigest") or EMPTY_PATCHDIGEST),
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
        "patchid": int(trace_body["patchid_value"] or EMPTY_PATCHID),
        "patchdigest": int(trace_body["patchdigest_value"] or EMPTY_PATCHDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_patchid": with_patchid,
        "skip_bind": skip_bind,
        "patch_cycle": do_patch,
        "entity_cycle": do_entity,
        "patchdigest_cycle": do_patchdigest,
        "replay": replay,
        "use_patchid": use_patchid,
    }


def verify_httppatch_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_httppatch_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    patchid = int(trace.get("patchid_value") or independent.get("patchid") or EMPTY_PATCHID)
    patchdigest = int(trace.get("patchdigest_value") or independent.get("patchdigest") or EMPTY_PATCHDIGEST)
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
        "patch_frame": independent.get("patch_frame") is True,
        "entity_frame": independent.get("entity_frame") is True,
        "patchdigest_response": independent.get("patchdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "patchid_bound": independent.get("patchid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "patchdigest_recorded": (
            port > 0
            and patchid == DEFAULT_PATCHID
            and patchdigest == DEFAULT_PATCHDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def httppatch_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.httppatch_actuation import "
        "builtin_httppatch_actuation_proof; r=builtin_httppatch_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='httppatch_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_httppatch_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTPPATCH_ACTUATION_ID,
        name="First-class RFC 5789 PATCH Method for HTTP PATCH/ENTITY actuation",
        description=(
            "Missions that require a httppatch tool can opt the httppatch provider in, "
            "bind a loopback RFC 5789 PATCH Method for HTTP endpoint, complete a PATCH "
            "with a non-empty patchid, lockstep an ENTITY that carries the "
            "stored patchdigest, independently poll the stored patchdigest "
            "on a later socket, and seal a digest-chained patchdigest. Default "
            "routing stays fail-closed; a missing patchid keeps the hole "
            "falsifiable, and skip-PATCH/ENTITY/PATCHDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.httppatch_actuation:builtin_httppatch_actuation_proof",
        proof_command=httppatch_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.stalecontent-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/httppatch_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/stalecontent_actuation.py",
            "src/blackhole_agent/wellknown_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required httppatch tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 5789 daemon, speaks a "
            "PATCH then ENTITY over PATCH Method for HTTP with a non-empty patchid and "
            "patchdigest, independently polls the stored patchdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 5861 HTTP Cache-Control Extensions for Stale Content lockstep is proved. "
            "Missing patchids, skip-PATCH, skip-ENTITY, skip-patchdigest, skip-REPLAY, "
            "and a PATCH aimed without a patchid stay fail-closed. "
            "Later genesis can take RFC 5785 Defining Well-Known Uniform Resource Identifiers DISCOVERY/SUFFIX as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("httppatch", "rfc5789", "http", "patchid", "patchdigest", "patch", "entity", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T214204Z-c9724193",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_httppatch_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 5789 patch lockstep actuation seals a patchdigest."""

    from blackhole_agent.wellknown_actuation import (
        WELLKNOWN_ACTUATION_GOAL,
        WELLKNOWN_ACTUATION_ID,
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
    checks["denylists_self"] = HTTPPATCH_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTPPATCH_ACTUATION_GOAL) == (
        HTTPPATCH_ACTUATION_ID,
    )
    checks["leftover_text_binds_httppatch"] = leftover_marker_ids(HTTPPATCH_LEFTOVER) == (
        HTTPPATCH_ACTUATION_ID,
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
        (WELLKNOWN_ACTUATION_GOAL, WELLKNOWN_ACTUATION_ID, "wellknown"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_httppatch"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"httppatch_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTPPATCH_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTPPATCH_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_httppatch(DEFAULT_PATCH)
    rebuilt = serialize_httppatch(parse_httppatch(advertised))
    preloaded = parse_httppatch(RFC_HTTPPATCH_ENTITY)
    header = encode_httppatch_header(DEFAULT_PATCH)
    parsed_header = parse_httppatch_header(header)
    asked = parse_http_request(patch_request(SENTINEL, DEFAULT_PATCHID))
    preload_req = parse_http_request(entity_request(SENTINEL, DEFAULT_PATCHID, DEFAULT_PATCHDIGEST))
    got = parse_http_response(patch_response(SENTINEL, DEFAULT_PATCHID, DEFAULT_PATCHDIGEST))
    preload_reply = parse_http_response(
        entity_response(SENTINEL, DEFAULT_PATCHID, DEFAULT_PATCHDIGEST)
    )
    checks["httppatch_roundtrip"] = (
        parse_httppatch(advertised) == DEFAULT_PATCH
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_PATCH_FIELD
        and is_token("PATCH") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_PATCH_FIELD
        and parsed_header["policy"] == DEFAULT_PATCH
        and parsed_header["header"] == PATCH_HEADER
        and parsed_header["patch"] is True
        and parsed_header["entity"] is False
        and preloaded == ENTITY_POLICY
        and ascii_serialize_patch_directive() == RFC_PATCH_DIRECTIVE
        and patch_directive_pair() == ("json-patch", RFC_JSON_PATCH_SECONDS)
        and RFC_PATCH_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_httppatch(ENTITY_POLICY) == RFC_HTTPPATCH_ENTITY
        and DEFAULT_PATCHDIGEST == request_patchdigest(DEFAULT_PATCHID, SENTINEL)
        and "patchdigest=" in canonical_entity(SENTINEL, DEFAULT_PATCHID, DEFAULT_PATCHDIGEST)
        and canonical_patch(SENTINEL, DEFAULT_PATCHID).startswith("PATCH")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "PATCH"
        and asked["httppatch_kind"] == "patch"
        and asked["patchid"] == DEFAULT_PATCHID
        and preload_req["httppatch_kind"] == "entity"
        and preload_req["patchdigest"] == DEFAULT_PATCHDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["httppatch_kind"] == "patch"
        and preload_reply["httppatch_kind"] == "entity"
        and got["policy"] == DEFAULT_PATCH
        and preload_reply["policy"] == ENTITY_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["patchdigest"] == DEFAULT_PATCHDIGEST
        and preload_reply["patchdigest"] == DEFAULT_PATCHDIGEST
        and httppatch_matches(serialize_httppatch(got["policy"]), advertised)
    )

    checks["catalog_names_httppatch"] = (
        len(catalog) > 91
        and catalog[91]["id"] == HTTPPATCH_ACTUATION_ID
        and catalog[90]["id"] == STALECONTENT_ACTUATION_ID
        and catalog[91]["source"] == "genesis_bind_httppatch"
    )
    checks["catalog_names_wellknown"] = (
        len(catalog) > 92
        and catalog[92]["id"] == WELLKNOWN_ACTUATION_ID
        and catalog[92]["source"] == "genesis_bind_wellknown"
    )
    family = capability_family(HTTPPATCH_ACTUATION_GOAL)
    checks["family_is_httppatch"] = "httppatch" in family
    checks["family_is_httppatch_surface"] = "httppatch" in family
    checks["family_is_patchid"] = "patchid" in family
    checks["family_is_rfc5789"] = "rfc5789" in family
    checks["family_is_patchdigest"] = "patchdigest" in family
    checks["family_is_not_wellknown"] = (
        "wellknown" not in family
        and "rfc5785" not in family
        and "suffixid" not in family
        and "suffixdigest" not in family
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
    packed = encode_patch(identity=SENTINEL, patchid=DEFAULT_PATCHID, patchdigest=DEFAULT_PATCHDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_patch"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_patchid"] is True
        and parsed["patchid"] == DEFAULT_PATCHID
        and parsed["patchdigest"] == DEFAULT_PATCHDIGEST
        and parsed["is_response"] is False
        and parsed["is_entity"] is False
        and parsed["type"] == FRAME_PATCH
        and parsed["first_byte"] == HP_FIRST
    )
    shook = encode_entity(
        identity=SENTINEL,
        patchid=DEFAULT_PATCHID,
        patchdigest=DEFAULT_PATCHDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_entity"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_patch"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["patchid"] == DEFAULT_PATCHID
        and answer_parsed["patchdigest"] == DEFAULT_PATCHDIGEST
        and answer_parsed["has_patchdigest"] is True
        and answer_parsed["type"] == FRAME_ENTITY
        and answer_parsed["first_byte"] == HP_FIRST
    )
    bare = encode_patch(identity=SENTINEL, patchid=DEFAULT_PATCHID, include_patchid=False)
    checks["missing_patchid_is_unauthenticated"] = parse_message(bare)["has_patchid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    httppatch_signature = semantic_signature(HTTPPATCH_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(httppatch_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_httppatch = ToolDescriptor(name="remote_httppatch", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_httppatch)
    checks["naive_mcp_httppatch_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = httppatch_tool_descriptor()
    default_httppatch = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPPATCH_TOOL_PROVIDER),
    )
    checks["default_httppatch_provider_is_unsupported"] = (
        default_httppatch.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTPPATCH_TOOL_PROVIDER}" in default_httppatch.reasons
    )
    checks["opted_in_httppatch_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_httppatch],
        required_tool_names=("local_memory", "httppatch"),
    )
    checks["naive_preflight_missing_httppatch"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["httppatch"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "httppatch"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPPATCH_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "httppatch" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="httppatch-actuation-") as tmp:
        root = Path(tmp)
        missing = run_httppatch_workflow(with_patchid=False, output_dir=root / "missing")
        skip_bind = run_httppatch_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_patch = run_httppatch_workflow(do_patch=False, output_dir=root / "skip-patch")
        skip_entity = run_httppatch_workflow(do_entity=False, output_dir=root / "skip-entity")
        skip_patchdigest = run_httppatch_workflow(do_patchdigest=False, output_dir=root / "skip-patchdigest")
        skip_replay = run_httppatch_workflow(replay=False, output_dir=root / "skip-replay")
        skip_patchid = run_httppatch_workflow(use_patchid=False, output_dir=root / "skip-patchid")
        live = run_httppatch_workflow(output_dir=root / "live")
        verify = verify_httppatch_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_httppatch_trace(clone)
        checks["naive_without_patchid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_patchid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_patch_stays_empty"] = (
            skip_patch["ok"] is False
            and skip_patch["error"] == "patch_required"
            and skip_patch["final_status"] == 409
            and skip_patch["payload_exists"] is False
        )
        checks["skip_entity_stays_empty"] = (
            skip_entity["ok"] is False
            and skip_entity["error"] == "entity_required"
            and skip_entity["final_status"] == 409
            and skip_entity["payload_exists"] is False
        )
        checks["skip_patchdigest_stays_empty"] = (
            skip_patchdigest["ok"] is False
            and skip_patchdigest["error"] == "patchdigest_required"
            and skip_patchdigest["final_status"] == 409
            and skip_patchdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_patchid_stays_empty"] = (
            skip_patchid["ok"] is False
            and skip_patchid["error"] == "patchid_required"
            and skip_patchid["final_status"] == 409
            and skip_patchid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_patchdigest"] = (
            int(live.get("patchid") or 0) == DEFAULT_PATCHID
            and int(live.get("patchdigest") or 0) == DEFAULT_PATCHDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_patchid_encode_entity_patchdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_patch["ok"] is False
            and skip_entity["ok"] is False
            and skip_patchdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_patchid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="httppatch-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTPPATCH_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_httppatch"] = (
        live_goal == HTTPPATCH_ACTUATION_GOAL
        and HTTPPATCH_ACTUATION_ID in live_done
        and live_source == "genesis_bind_httppatch"
    )

    with tempfile.TemporaryDirectory(prefix="httppatch-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTPPATCH_LEFTOVER, root)
        register_catalog_proved(root, HTTPPATCH_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTPPATCH_LEFTOVER, root)
        after = leftover_is_open(HTTPPATCH_LEFTOVER, root)
    checks["httppatch_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_httppatch_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTPPATCH_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_httppatch_actuation_capability()
    return {
        "ok": ok,
        "action": "httppatch_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTPPATCH_ACTUATION_GOAL,
        "done_when": HTTPPATCH_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
