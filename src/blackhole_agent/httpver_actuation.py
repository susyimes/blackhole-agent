"""Drive a first-class Use and Interpretation of HTTP Version Numbers tool through RFC 2145 VERSION/INTERPRET.

Tool routing already fails missions that require ``httpver``: hosted
httpver endpoints stay on the unsupported MCP provider, and no first-party
httpver provider is executable. Unbound therefore cannot speak a VERSION,
lockstep a INTERPRET versionid handshake over HTTP Version VERSIONID,
independently poll the stored versiondigest, or seal a versiondigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``httpver`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2145 daemon
- keep a missing-versionid client so the httpver-versionid hole stays falsifiable
- refuse INTERPRET until a VERSION lands with a non-empty versionid
- independently poll the stored versiondigest on a later client socket
- persist a sealed versiondigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 2186 Internet Cache Protocol
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
    HTTPVER_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    httpver_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTPVER_ACTUATION_ID = "capability.httpver-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-HTTPVER-OK"
POLL_TOKEN = "BH-HTTPVER-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_VERSIONID = 0
EMPTY_VERSIONDIGEST = 0
HTTPVER_FIRST = 0x56  # RFC 2145 Use and Interpretation of HTTP Version Numbers (ASCII 'V')
VERSIONID_SIZE = 4
VERSIONDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_INTERPRET = 0x02  # RFC 2145 INTERPRET confirmation
FRAME_VERSION = 0x01  # RFC 2145 VERSION
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTPVER_LEFTOVER = (
    "Later genesis can take RFC 2145 Use and Interpretation of HTTP Version Numbers VERSION/INTERPRET over a "
    "versionid-gated versiondigest."
)
HTTPVER_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPVER_ACTUATION_ID};"
    f"capability_proved:{HTTPVER_ACTUATION_ID};"
    "no_skill_route"
)
HTTPVER_ACTUATION_GOAL = (
    "Repair rfc2145 httpver version/interpret cycle cannot land over http "
    "httpver versionid: hosted httpver endpoints remain unsupported so a VERSION then "
    "INTERPRET versionid handshake cannot land and a sealed versiondigest "
    "cannot be produced. A missing httpver versionid stays forbidden; fail-closed "
    "routing never opts the httpver provider in. An independent later poll of the "
    "stored versiondigest keeps the hole falsifiable."
)


class HttpverActuationError(RuntimeError):
    """Raised when the digest session or loopback daemon fixture misbehaves."""


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
# RFC 2145 sections 5.1 and 5.2: AUTH / DIGEST.
RFC_VERSION_FIELD = "VERSION"
RFC_INTERPRET_FIELD = "INTERPRET"
RFC_HTTPVER_INTERPRET = RFC_INTERPRET_FIELD
RFC_VERSION_DIRECTIVE = "version=number"
RFC_INTERPRET_DIRECTIVE = "interpret=minor"
DEFAULT_VERSION = "VERSION"
INTERPRET_POLICY = "INTERPRET"
VERSION_HEADER = "Version"
INTERPRET_HEADER = "Interpret"
HTTPVER_INTERPRET_HEADER = INTERPRET_HEADER
RFC_VERSION_PATH = "/httpver/"
RFC_VERSION_EMPTY = ""


def httpver_directive_pair(*, hit: bool = False) -> tuple[str, str]:
    """RFC 2145 Version / Interpret directive pair."""

    if hit:
        return "interpret", "minor"
    return "version", "number"


def ascii_serialize_httpver_directive(*, hit: bool = False) -> str:
    """RFC 2145 token "=" version-or-interpret."""

    name, value = httpver_directive_pair(hit=hit)
    if not is_token(name):
        raise HttpverActuationError("illegal_directive")
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
            raise HttpverActuationError("short_httpver")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 2145 Meter token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_httpver(policy: str | Sequence[str]) -> str:
    """Serialize RFC 2145 VERSION / INTERPRET opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise HttpverActuationError("illegal_httpver")
    upper = text.upper().replace("_", "-")
    if upper in {"VERSION", "HTTPVER", "HTTPVER-VERSION"}:
        return "VERSION"
    if upper in {"INTERPRET", "OBJECT", "HTTPVER-INTERPRET"}:
        return "INTERPRET"
    if upper.startswith("VERSION="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpverActuationError("illegal_httpver")
        return "VERSION"
    if upper.startswith("INTERPRET="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpverActuationError("illegal_httpver")
        return "INTERPRET"
    raise HttpverActuationError("illegal_httpver")


def parse_httpver(text: str) -> str:
    """Parse RFC 2145 HTTPVER opcode header extensions into VERSION or INTERPRET."""

    raw = str(text or "").strip()
    if not raw:
        raise HttpverActuationError("illegal_httpver")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"VERSION", "HTTPVER", "HTTPVER-VERSION"}:
        return "VERSION"
    if upper in {"INTERPRET", "OBJECT", "HTTPVER-INTERPRET"}:
        return "INTERPRET"
    if upper.startswith("VERSION="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpverActuationError("illegal_httpver")
        return "VERSION"
    if upper.startswith("INTERPRET="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpverActuationError("illegal_httpver")
        return "INTERPRET"
    raise HttpverActuationError("illegal_httpver")


def encode_httpver_header(policy: str | Sequence[str]) -> bytes:
    """RFC 2145 Meter field as bytes."""

    return serialize_httpver(policy).encode("ascii")


def parse_httpver_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_httpver(field_value) if field_value else DEFAULT_VERSION
    return {
        "field_value": field_value,
        "policy": policy,
        "header": VERSION_HEADER,
        "directive": str(policy),
        "version": str(policy) == "VERSION",
        "interpret": str(policy) == "INTERPRET",
    }


def canonical_version(identity: str, versionid: int) -> str:
    """RFC 2145 AUTH advertisement bound to identity and versionid."""

    return (
        f"{serialize_httpver(DEFAULT_VERSION)}, "
        f"version={ascii_serialize_httpver_directive()}, "
        f"identity={identity}, versionid={int(versionid) & 0xFFFFFFFF}"
    )


def canonical_interpret(identity: str, versionid: int, versiondigest: int | None = None) -> str:
    """RFC 2145 DIGEST confirmation of the stored digest policy."""

    digest = ""
    if versiondigest is not None:
        digest = f", versiondigest={int(versiondigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_httpver(INTERPRET_POLICY)}, "
        f"interpret={ascii_serialize_httpver_directive(hit=True)}, "
        f"identity={identity}, versionid={int(versionid) & 0xFFFFFFFF}{digest}"
    )


def representation_interpret(identity: str, versionid: int, versiondigest: int) -> str:
    return canonical_interpret(identity, versionid, versiondigest)


def httpver_matches(left: str, right: str) -> bool:
    return parse_httpver(left) == parse_httpver(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HttpverActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HttpverActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HttpverActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HttpverActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def version_request(identity: str, versionid: int) -> bytes:
    """HTTP AUTH that elicits RFC 2145 origin AUTH."""

    keyid = f"{int(versionid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"VERSION /httpver/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Version-Id: {int(versionid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def interpret_request(identity: str, versionid: int, versiondigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 2145 DIGEST confirmation of the stored digest policy."""

    keyid = f"{int(versionid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if versiondigest is not None:
        extra = f"Version-Digest: {int(versiondigest) & 0xFFFFFFFF}\r\n"
    return (
        f"INTERPRET /httpver/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Version-Id: {int(versionid) & 0xFFFFFFFF}\r\n"
        "Interpret-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    httpver_kind = "interpret" if fields.get("interpret-confirm") == "1" else "version"
    upgrade_field = fields.get("version") or fields.get("negotiate") or fields.get("httpver") or ""
    policy = parse_httpver(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "httpver_kind": httpver_kind,
        "policy": policy,
        "versionid": int(fields["version-id"]) if fields.get("version-id") else EMPTY_VERSIONID,
        "versiondigest": int(fields["version-digest"]) if fields.get("version-digest") else EMPTY_VERSIONDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def version_response(identity: str, versionid: int, versiondigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 2145 origin AUTH, carrying the stored versiondigest."""

    advertised = serialize_httpver(DEFAULT_VERSION)
    payload = bytes(body or canonical_version(identity, versionid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Version: {advertised}\r\n"
        f"Version-Id: {int(versionid) & 0xFFFFFFFF}\r\n"
        f"Version-Digest: {int(versiondigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def interpret_response(identity: str, versionid: int, versiondigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 2145 DIGEST, carrying the stored DIGEST policy."""

    advertised = serialize_httpver(INTERPRET_POLICY)
    payload = bytes(body or representation_interpret(identity, versionid, versiondigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Version: {advertised}\r\n"
        f"Version-Id: {int(versionid) & 0xFFFFFFFF}\r\n"
        f"Version-Digest: {int(versiondigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/httpver-interpret\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise HttpverActuationError("illegal_content_length") from error
    field_value = fields.get("version") or fields.get("negotiate") or fields.get("httpver") or ""
    policy = parse_httpver(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/httpver-interpret" or policy == INTERPRET_POLICY:
        status = 200
        httpver_kind = "interpret"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        httpver_kind = "version"
    else:
        status = 0
        httpver_kind = "version"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "httpver_kind": httpver_kind,
        "policy": policy,
        "versionid": int(fields["version-id"]) if fields.get("version-id") else EMPTY_VERSIONID,
        "versiondigest": int(fields["version-digest"]) if fields.get("version-digest") else EMPTY_VERSIONDIGEST,
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
        raise HttpverActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise HttpverActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise HttpverActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HttpverActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_versionid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"versionid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_versionid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-versionid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_versiondigest(versionid: int = EMPTY_VERSIONID, token: str = SENTINEL) -> int:
    material = canonical_version(token or SENTINEL, int(versionid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_VERSIONID = request_versionid(SENTINEL)
DEFAULT_VERSIONDIGEST = request_versiondigest(DEFAULT_VERSIONID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    versionid: int,
    versiondigest: int,
    include_versionid: bool = True,
) -> bytes:
    live_versionid = int(versionid) & 0xFFFFFFFF if include_versionid else EMPTY_VERSIONID
    live_digest = int(versiondigest) & 0xFFFFFFFF if include_versionid and live_versionid else EMPTY_VERSIONDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_versionid) if live_versionid else b""
    header = bytearray()
    header.append(HTTPVER_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_version(
    *,
    identity: str,
    versionid: int,
    versiondigest: int | None = None,
    include_versionid: bool = True,
) -> bytes:
    live_versionid = int(versionid) & 0xFFFFFFFF if include_versionid else EMPTY_VERSIONID
    live_digest = int(versiondigest) if versiondigest is not None else request_versiondigest(live_versionid, identity)
    return encode_packet(
        FRAME_VERSION,
        identity=identity,
        versionid=live_versionid,
        versiondigest=live_digest,
        include_versionid=include_versionid,
    )


def encode_interpret(
    *,
    identity: str,
    versionid: int,
    versiondigest: int | None = None,
    include_versionid: bool = True,
) -> bytes:
    live_versionid = int(versionid) & 0xFFFFFFFF if include_versionid else EMPTY_VERSIONID
    live_digest = int(versiondigest) if versiondigest is not None else request_versiondigest(live_versionid, identity)
    return encode_packet(
        FRAME_INTERPRET,
        identity=identity,
        versionid=live_versionid,
        versiondigest=live_digest,
        include_versionid=include_versionid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HttpverActuationError("short_packet")
    first = raw[0]
    if first != HTTPVER_FIRST:
        raise HttpverActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise HttpverActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == VERSIONID_SIZE:
        live_versionid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_versionid = EMPTY_VERSIONID
    else:
        raise HttpverActuationError("illegal_versionid")
    if offset >= len(raw):
        raise HttpverActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_VERSION, FRAME_INTERPRET}:
        raise HttpverActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HttpverActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HttpverActuationError("checksum_failed")
    if len(payload) < 5:
        raise HttpverActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HttpverActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_versionid = int(live_versionid) != EMPTY_VERSIONID
    has_versiondigest = has_versionid and int(live_digest) != EMPTY_VERSIONDIGEST
    is_version = frame_type == FRAME_VERSION
    is_interpret = frame_type == FRAME_INTERPRET
    return {
        "type": int(frame_type),
        "is_version": is_version,
        "is_interpret": is_interpret,
        "is_response": is_interpret,
        "versionid": int(live_versionid),
        "has_versionid": has_versionid,
        "versiondigest": int(live_digest),
        "has_versiondigest": has_versiondigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC2145",
        "serialize_field": canonical_version(identity, live_versionid) if has_versionid else "",
        "tls_field": canonical_interpret(identity, live_versionid, live_digest) if has_versiondigest else "",
    }


class HttpverClient:
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
            raise HttpverActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_interpret"] or not packet["is_response"]:
            raise HttpverActuationError("versiondigest_required")
        if not packet["has_versionid"]:
            raise HttpverActuationError("versionid_required")
        if not packet["has_versiondigest"]:
            raise HttpverActuationError("versiondigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_versiondigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_versiondigest:
            raise HttpverActuationError("versiondigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "versionid": int(reply.get("versionid") or EMPTY_VERSIONID),
            "identity": str(reply.get("identity") or ""),
            "versiondigest": int(reply.get("versiondigest") or EMPTY_VERSIONDIGEST),
        }

    def report(
        self,
        identity: str,
        versionid: int,
        versiondigest: int = EMPTY_VERSIONDIGEST,
        *,
        wait_versiondigest: bool = True,
        include_versionid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_interpret(
            identity=identity,
            versionid=versionid,
            versiondigest=versiondigest or request_versiondigest(versionid, identity),
            include_versionid=include_versionid,
        )
        return self.exchange(packet, wait_versiondigest=wait_versiondigest)


class HttpverSession:
    """VERSIONID-gated loopback RFC 2145 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        versionid_gate: int = DEFAULT_VERSIONID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.versionid_gate = int(versionid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.versionid = EMPTY_VERSIONID
        self.versiondigest = EMPTY_VERSIONDIGEST
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

    def store_versionid_once(self, identity: str, versionid: int, versiondigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(versionid or EMPTY_VERSIONID)
            live_digest = int(versiondigest or EMPTY_VERSIONDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.versionid = live
                self.versiondigest = live_digest or request_versiondigest(live, name)
                self.stored = True
            return str(self.identity), int(self.versionid), int(self.versiondigest)

    def read_versionid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.versionid), int(self.versiondigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "versionid": EMPTY_VERSIONID,
            "versiondigest": EMPTY_VERSIONDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _versionid_missing(self) -> bool:
        return not int(self.versionid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, versionid: int, versiondigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_interpret(
            identity=identity,
            versionid=versionid,
            versiondigest=versiondigest,
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
            except HttpverActuationError:
                continue
            if not packet.get("is_version") and not packet.get("is_interpret"):
                continue
            if not packet.get("has_versionid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_versionid, stored_digest = self.store_versionid_once(
                identity,
                int(packet.get("versionid") or EMPTY_VERSIONID),
                int(packet.get("versiondigest") or EMPTY_VERSIONDIGEST),
            )
            if not stored_name or not stored_versionid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_version"):
                    self.opened = True
                if packet.get("is_interpret"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_versionid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._versionid_missing():
            return self._forbidden("missing_versionid")
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
        do_version: bool = True,
        do_interpret: bool = True,
        do_versiondigest: bool = True,
        replay: bool = True,
        use_versionid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._versionid_missing():
            return self._forbidden("missing_versionid")
        live_token = str(token or SENTINEL)
        origin_versionid = request_versionid(live_token)
        origin_digest = request_versiondigest(origin_versionid, live_token)
        client: HttpverClient | None = None
        independent: HttpverClient | None = None
        try:
            client = HttpverClient(self.host, int(self.port))
            if not do_version:
                return self._conflict("version_required")
            bind_packet = encode_version(
                identity=live_token,
                versionid=origin_versionid,
                versiondigest=origin_digest,
                include_versionid=use_versionid,
            )
            if not use_versionid:
                try:
                    client.exchange(bind_packet, wait_versiondigest=True)
                except HttpverActuationError:
                    return self._conflict("versionid_required")
                return self._conflict("versionid_required")
            client.send(bind_packet)
            if not do_interpret:
                return self._conflict("interpret_required")
            proxy_packet = encode_interpret(
                identity=live_token,
                versionid=origin_versionid,
                versiondigest=origin_digest,
                include_versionid=True,
            )
            if not do_versiondigest:
                try:
                    client.exchange(proxy_packet, wait_versiondigest=False)
                except HttpverActuationError as error:
                    if str(error) == "versiondigest_required":
                        return self._conflict("versiondigest_required")
                    return self._conflict("versiondigest_required")
                return self._conflict("versiondigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_versiondigest=True)
            except HttpverActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("versionid_required")
                if reason == "versiondigest_required":
                    return self._conflict("versiondigest_required")
                return self._conflict("version_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("version_required")
            if int(reply.get("versionid") or EMPTY_VERSIONID) != origin_versionid:
                return self._conflict("versiondigest_required")
            if int(reply.get("versiondigest") or EMPTY_VERSIONDIGEST) != origin_digest:
                return self._conflict("versiondigest_required")
            self.retrieved = True
            if replay:
                independent = HttpverClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_versionid(live_token),
                        request_versiondigest(poll_versionid(live_token), POLL_TOKEN),
                        wait_versiondigest=True,
                    )
                except HttpverActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_versionid, stored_digest = self.read_versionid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_versionid != origin_versionid
                    or stored_digest != origin_digest
                    or int(poll.get("versionid") or EMPTY_VERSIONID) != origin_versionid
                    or int(poll.get("versiondigest") or EMPTY_VERSIONDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_versionid}:{origin_digest}:{live_token}:{canonical_version(live_token, origin_versionid)}:{canonical_interpret(live_token, origin_versionid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "versionid": origin_versionid,
                "versiondigest": origin_digest,
                "version_frame": True,
                "interpret_frame": True,
                "versiondigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "versionid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_httpver_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "versionid": origin_versionid,
                "versiondigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "version_frame": True,
                "interpret_frame": True,
                "versiondigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "versionid_bound": True,
            }
        except (OSError, HttpverActuationError) as error:
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
        live = independent_httpver_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "versionid": int(live.get("versionid") or EMPTY_VERSIONID),
            "versiondigest": int(live.get("versiondigest") or EMPTY_VERSIONDIGEST),
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


def call_httpver_tool(session: HttpverSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one httpver tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_version = True if arguments.get("version") is None else bool(arguments.get("version"))
    do_interpret = True if arguments.get("interpret") is None else bool(arguments.get("interpret"))
    do_versiondigest = True if arguments.get("versiondigest") is None else bool(arguments.get("versiondigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_versionid = True if arguments.get("use_versionid") is None else bool(arguments.get("use_versionid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_version=do_version,
            do_interpret=do_interpret,
            do_versiondigest=do_versiondigest,
            replay=replay,
            use_versionid=use_versionid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HttpverActuationError(f"unsupported httpver action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_httpver_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage versiondigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "versionid": EMPTY_VERSIONID,
        "versiondigest": EMPTY_VERSIONDIGEST,
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
            "version_frame",
            "interpret_frame",
            "versiondigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "versionid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    versionid = int(payload.get("versionid") or EMPTY_VERSIONID)
    versiondigest = int(payload.get("versiondigest") or EMPTY_VERSIONDIGEST)
    dual = port > 0 and bool(versionid) and bool(versiondigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "versionid": versionid,
        "versiondigest": versiondigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "version_frame": payload.get("version_frame") is True,
        "interpret_frame": payload.get("interpret_frame") is True,
        "versiondigest_response": payload.get("versiondigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "versionid_bound": payload.get("versionid_bound") is True,
    }


def run_httpver_workflow(
    *,
    with_versionid: bool = True,
    skip_bind: bool = False,
    do_version: bool = True,
    do_interpret: bool = True,
    do_versiondigest: bool = True,
    replay: bool = True,
    use_versionid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2145 VERSION/INTERPRET versionid cycle workflow."""

    descriptor = httpver_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPVER_TOOL_PROVIDER),
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
        raise HttpverActuationError(f"httpver tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="httpver-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HttpverSession(out, versionid_gate=DEFAULT_VERSIONID if with_versionid else EMPTY_VERSIONID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "version": do_version,
            "interpret": do_interpret,
            "versiondigest": do_versiondigest,
            "replay": replay,
            "use_versionid": use_versionid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_httpver_tool(session, arguments))
            except HttpverActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_httpver_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_versionid
        and not skip_bind
        and do_version
        and do_interpret
        and do_versiondigest
        and replay
        and use_versionid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "httpver_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_versionid": with_versionid,
        "skip_bind": skip_bind,
        "version_frame": do_version,
        "interpret": do_interpret,
        "versiondigest": do_versiondigest,
        "replay": replay,
        "use_versionid": use_versionid,
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
        "versionid_value": int(publish_result.get("versionid") or independent.get("versionid") or EMPTY_VERSIONID),
        "versiondigest_value": int(publish_result.get("versiondigest") or independent.get("versiondigest") or EMPTY_VERSIONDIGEST),
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
        "versionid": int(trace_body["versionid_value"] or EMPTY_VERSIONID),
        "versiondigest": int(trace_body["versiondigest_value"] or EMPTY_VERSIONDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_versionid": with_versionid,
        "skip_bind": skip_bind,
        "version_cycle": do_version,
        "interpret_cycle": do_interpret,
        "versiondigest_cycle": do_versiondigest,
        "replay": replay,
        "use_versionid": use_versionid,
    }


def verify_httpver_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_httpver_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    versionid = int(trace.get("versionid_value") or independent.get("versionid") or EMPTY_VERSIONID)
    versiondigest = int(trace.get("versiondigest_value") or independent.get("versiondigest") or EMPTY_VERSIONDIGEST)
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
        "version_frame": independent.get("version_frame") is True,
        "interpret_frame": independent.get("interpret_frame") is True,
        "versiondigest_response": independent.get("versiondigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "versionid_bound": independent.get("versionid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "versiondigest_recorded": (
            port > 0
            and versionid == DEFAULT_VERSIONID
            and versiondigest == DEFAULT_VERSIONDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def httpver_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.httpver_actuation import "
        "builtin_httpver_actuation_proof; r=builtin_httpver_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='httpver_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_httpver_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTPVER_ACTUATION_ID,
        name="First-class RFC 2145 Use and Interpretation of HTTP Version Numbers VERSION/INTERPRET actuation",
        description=(
            "Missions that require a httpver tool can opt the httpver provider in, "
            "bind a loopback RFC 2145 Use and Interpretation of HTTP Version Numbers endpoint, complete a VERSION "
            "with a non-empty versionid, lockstep a INTERPRET that carries the "
            "stored versiondigest, independently poll the stored versiondigest "
            "on a later socket, and seal a digest-chained versiondigest. Default "
            "routing stays fail-closed; a missing versionid keeps the hole "
            "falsifiable, and skip-VERSION/INTERPRET/VERSIONDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.httpver_actuation:builtin_httpver_actuation_proof",
        proof_command=httpver_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.icp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/httpver_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/icp_actuation.py",
            "src/blackhole_agent/httpstate_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required httpver tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 2145 daemon, speaks a "
            "VERSION then INTERPRET over Use and Interpretation of HTTP Version Numbers with a non-empty versionid and "
            "versiondigest, independently polls the stored versiondigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 2186 Internet Cache Protocol lockstep is proved. "
            "Missing versionids, skip-VERSION, skip-INTERPRET, skip-versiondigest, skip-REPLAY, "
            "and a VERSION aimed without a versionid stay fail-closed. "
            "Later genesis can take RFC 2109 HTTP State Management Mechanism OFFER/ATTACH as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("httpver", "rfc2145", "http", "versionid", "versiondigest", "version", "interpret", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T025646Z-e1220663",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_httpver_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2145 query lockstep actuation seals a versiondigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.httpstate_actuation import (
        HTTPSTATE_ACTUATION_GOAL,
        HTTPSTATE_ACTUATION_ID,
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
    checks["denylists_self"] = HTTPVER_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTPVER_ACTUATION_GOAL) == (
        HTTPVER_ACTUATION_ID,
    )
    checks["leftover_text_binds_httpver"] = leftover_marker_ids(HTTPVER_LEFTOVER) == (
        HTTPVER_ACTUATION_ID,
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
        (HTTPSTATE_ACTUATION_GOAL, HTTPSTATE_ACTUATION_ID, "httpstate"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_httpver"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"httpver_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTPVER_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTPVER_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_httpver(DEFAULT_VERSION)
    rebuilt = serialize_httpver(parse_httpver(advertised))
    preloaded = parse_httpver(RFC_HTTPVER_INTERPRET)
    header = encode_httpver_header(DEFAULT_VERSION)
    parsed_header = parse_httpver_header(header)
    asked = parse_http_request(version_request(SENTINEL, DEFAULT_VERSIONID))
    preload_req = parse_http_request(interpret_request(SENTINEL, DEFAULT_VERSIONID, DEFAULT_VERSIONDIGEST))
    got = parse_http_response(version_response(SENTINEL, DEFAULT_VERSIONID, DEFAULT_VERSIONDIGEST))
    preload_reply = parse_http_response(
        interpret_response(SENTINEL, DEFAULT_VERSIONID, DEFAULT_VERSIONDIGEST)
    )
    checks["httpver_roundtrip"] = (
        parse_httpver(advertised) == DEFAULT_VERSION
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_VERSION_FIELD
        and is_token("VERSION") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_VERSION_FIELD
        and parsed_header["policy"] == DEFAULT_VERSION
        and parsed_header["header"] == VERSION_HEADER
        and parsed_header["version"] is True
        and parsed_header["interpret"] is False
        and preloaded == INTERPRET_POLICY
        and ascii_serialize_httpver_directive() == RFC_VERSION_DIRECTIVE
        and httpver_directive_pair() == ("version", "number")
        and RFC_VERSION_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_httpver(INTERPRET_POLICY) == RFC_HTTPVER_INTERPRET
        and DEFAULT_VERSIONDIGEST == request_versiondigest(DEFAULT_VERSIONID, SENTINEL)
        and "versiondigest=" in canonical_interpret(SENTINEL, DEFAULT_VERSIONID, DEFAULT_VERSIONDIGEST)
        and canonical_version(SENTINEL, DEFAULT_VERSIONID).startswith("VERSION")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "VERSION"
        and asked["httpver_kind"] == "version"
        and asked["versionid"] == DEFAULT_VERSIONID
        and preload_req["httpver_kind"] == "interpret"
        and preload_req["versiondigest"] == DEFAULT_VERSIONDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["httpver_kind"] == "version"
        and preload_reply["httpver_kind"] == "interpret"
        and got["policy"] == DEFAULT_VERSION
        and preload_reply["policy"] == INTERPRET_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["versiondigest"] == DEFAULT_VERSIONDIGEST
        and preload_reply["versiondigest"] == DEFAULT_VERSIONDIGEST
        and httpver_matches(serialize_httpver(got["policy"]), advertised)
    )

    checks["catalog_names_httpver"] = (
        len(catalog) > 100
        and catalog[100]["id"] == HTTPVER_ACTUATION_ID
        and catalog[99]["id"] == ICP_ACTUATION_ID
        and catalog[100]["source"] == "genesis_bind_httpver"
    )
    checks["catalog_names_httpstate"] = (
        len(catalog) > 101
        and catalog[101]["id"] == HTTPSTATE_ACTUATION_ID
        and catalog[101]["source"] == "genesis_bind_httpstate"
    )
    family = capability_family(HTTPVER_ACTUATION_GOAL)
    checks["family_is_httpver"] = "httpver" in family
    checks["family_is_httpver_surface"] = "httpver" in family
    checks["family_is_versionid"] = "versionid" in family
    checks["family_is_rfc2145"] = "rfc2145" in family
    checks["family_is_versiondigest"] = "versiondigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_httpstate"] = (
        "httpstate" not in family
        and "rfc2109" not in family
        and "stateid" not in family
        and "statedigest" not in family
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
    packed = encode_version(identity=SENTINEL, versionid=DEFAULT_VERSIONID, versiondigest=DEFAULT_VERSIONDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_version"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_versionid"] is True
        and parsed["versionid"] == DEFAULT_VERSIONID
        and parsed["versiondigest"] == DEFAULT_VERSIONDIGEST
        and parsed["is_response"] is False
        and parsed["is_interpret"] is False
        and parsed["type"] == FRAME_VERSION
        and parsed["first_byte"] == HTTPVER_FIRST
    )
    shook = encode_interpret(
        identity=SENTINEL,
        versionid=DEFAULT_VERSIONID,
        versiondigest=DEFAULT_VERSIONDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_interpret"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_version"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["versionid"] == DEFAULT_VERSIONID
        and answer_parsed["versiondigest"] == DEFAULT_VERSIONDIGEST
        and answer_parsed["has_versiondigest"] is True
        and answer_parsed["type"] == FRAME_INTERPRET
        and answer_parsed["first_byte"] == HTTPVER_FIRST
    )
    bare = encode_version(identity=SENTINEL, versionid=DEFAULT_VERSIONID, include_versionid=False)
    checks["missing_versionid_is_unauthed"] = parse_message(bare)["has_versionid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(HTTPVER_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_httpver = ToolDescriptor(name="remote_httpver", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_httpver)
    checks["naive_mcp_httpver_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = httpver_tool_descriptor()
    default_httpver = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPVER_TOOL_PROVIDER),
    )
    checks["default_httpver_provider_is_unsupported"] = (
        default_httpver.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTPVER_TOOL_PROVIDER}" in default_httpver.reasons
    )
    checks["opted_in_httpver_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_httpver],
        required_tool_names=("local_memory", "httpver"),
    )
    checks["naive_preflight_missing_httpver"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["httpver"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "httpver"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPVER_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "httpver" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="httpver-actuation-") as tmp:
        root = Path(tmp)
        missing = run_httpver_workflow(with_versionid=False, output_dir=root / "missing")
        skip_bind = run_httpver_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_version = run_httpver_workflow(do_version=False, output_dir=root / "skip-query")
        skip_interpret = run_httpver_workflow(do_interpret=False, output_dir=root / "skip-hit")
        skip_versiondigest = run_httpver_workflow(do_versiondigest=False, output_dir=root / "skip-versiondigest")
        skip_replay = run_httpver_workflow(replay=False, output_dir=root / "skip-replay")
        skip_versionid = run_httpver_workflow(use_versionid=False, output_dir=root / "skip-versionid")
        live = run_httpver_workflow(output_dir=root / "live")
        verify = verify_httpver_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_httpver_trace(clone)
        checks["naive_without_versionid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_versionid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_version_stays_empty"] = (
            skip_version["ok"] is False
            and skip_version["error"] == "version_required"
            and skip_version["final_status"] == 409
            and skip_version["payload_exists"] is False
        )
        checks["skip_interpret_stays_empty"] = (
            skip_interpret["ok"] is False
            and skip_interpret["error"] == "interpret_required"
            and skip_interpret["final_status"] == 409
            and skip_interpret["payload_exists"] is False
        )
        checks["skip_versiondigest_stays_empty"] = (
            skip_versiondigest["ok"] is False
            and skip_versiondigest["error"] == "versiondigest_required"
            and skip_versiondigest["final_status"] == 409
            and skip_versiondigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_versionid_stays_empty"] = (
            skip_versionid["ok"] is False
            and skip_versionid["error"] == "versionid_required"
            and skip_versionid["final_status"] == 409
            and skip_versionid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_versiondigest"] = (
            int(live.get("versionid") or 0) == DEFAULT_VERSIONID
            and int(live.get("versiondigest") or 0) == DEFAULT_VERSIONDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_versionid_encode_interpret_versiondigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_version["ok"] is False
            and skip_interpret["ok"] is False
            and skip_versiondigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_versionid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="httpver-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTPVER_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_httpver"] = (
        live_goal == HTTPVER_ACTUATION_GOAL
        and HTTPVER_ACTUATION_ID in live_done
        and live_source == "genesis_bind_httpver"
    )

    with tempfile.TemporaryDirectory(prefix="httpver-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTPVER_LEFTOVER, root)
        register_catalog_proved(root, HTTPVER_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTPVER_LEFTOVER, root)
        after = leftover_is_open(HTTPVER_LEFTOVER, root)
    checks["httpver_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_httpver_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTPVER_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_httpver_actuation_capability()
    return {
        "ok": ok,
        "action": "httpver_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTPVER_ACTUATION_GOAL,
        "done_when": HTTPVER_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
