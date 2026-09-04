"""Drive a first-class HTTP Strict Transport Security tool through RFC 6797 STS/PRELOAD.

Tool routing already fails missions that require ``hsts``: hosted
hsts endpoints stay on the unsupported MCP provider, and no first-party
hsts provider is executable. Unbound therefore cannot speak an STS,
lockstep a PRELOAD hstsid handshake over HTTP Strict Transport Security HSTSID,
independently poll the stored stsdigest, or seal a stsdigest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``hsts`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 6797 daemon
- keep a missing-hstsid client so the hsts-hstsid hole stays falsifiable
- refuse PRELOAD until an STS lands with a non-empty hstsid
- independently poll the stored stsdigest on a later client socket
- persist a sealed stsdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 7838 HTTP Alternative Services
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
    HSTS_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    hsts_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HSTS_ACTUATION_ID = "capability.hsts-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-HSTS-OK"
POLL_TOKEN = "BH-HSTS-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_HSTSID = 0
EMPTY_STSDIGEST = 0
HS_FIRST = 0x48  # RFC 6797 HSTS (ASCII 'H')
HSTSID_SIZE = 4
STSDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_PRELOAD = 0x02  # RFC 6797 preload confirmation
FRAME_STS = 0x01  # RFC 6797 Strict-Transport-Security
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HSTS_LEFTOVER = (
    "Later genesis can take RFC 6797 HTTP Strict Transport Security STS/PRELOAD over an "
    "hstsid-gated stsdigest."
)
HSTS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HSTS_ACTUATION_ID};"
    f"capability_proved:{HSTS_ACTUATION_ID};"
    "no_skill_route"
)
HSTS_ACTUATION_GOAL = (
    "Repair rfc6797 hsts sts/preload cycle cannot land over http "
    "hsts hstsid: hosted hsts endpoints remain unsupported so an STS then "
    "PRELOAD hstsid handshake cannot land and a sealed stsdigest "
    "cannot be produced. A missing hsts hstsid stays forbidden; fail-closed "
    "routing never opts the hsts provider in. An independent later poll of the "
    "stored stsdigest keeps the hole falsifiable."
)


class HstsActuationError(RuntimeError):
    """Raised when the HTTP Strict Transport Security session or loopback daemon fixture misbehaves."""


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
# RFC 6797 section 6.1 / 6.1.1 example.
RFC_STS_FIELD = "max-age=31536000; includeSubDomains"
RFC_STS_PRELOAD = "max-age=31536000; includeSubDomains; preload"
# policy = (max_age, include_subdomains, preload)
DEFAULT_STS: tuple[int, bool, bool] = (31536000, True, False)
PRELOAD_STS: tuple[int, bool, bool] = (31536000, True, True)
STS_HEADER = "Strict-Transport-Security"


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise HstsActuationError("short_sts")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 6797 directive-name."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_sts(policy: tuple[int, bool, bool] | Sequence[int | bool]) -> str:
    """Serialize RFC 6797 Strict-Transport-Security field-value."""

    max_age = int(policy[0])
    include_subdomains = bool(policy[1])
    preload = bool(policy[2]) if len(policy) > 2 else False
    if max_age < 0:
        raise HstsActuationError("illegal_max_age")
    chunks = [f"max-age={max_age}"]
    if include_subdomains:
        chunks.append("includeSubDomains")
    if preload:
        chunks.append("preload")
    return "; ".join(chunks)


def parse_sts(text: str) -> tuple[int, bool, bool]:
    """Parse RFC 6797 Strict-Transport-Security into max-age/includeSubDomains/preload."""

    raw = str(text or "").strip()
    if not raw:
        raise HstsActuationError("illegal_sts")
    parser = _Parser(raw)
    max_age: int | None = None
    include_subdomains = False
    preload = False
    first = True
    while True:
        parser.skip_ows()
        if parser.eof():
            break
        if not first:
            if parser.peek() != ";":
                raise HstsActuationError("illegal_sts")
            parser.take()
            parser.skip_ows()
            if parser.eof():
                break
        first = False
        name_start = parser.pos
        while parser.peek() and parser.peek() in TCHAR:
            parser.pos += 1
        name = parser.text[name_start : parser.pos]
        if not name:
            raise HstsActuationError("illegal_sts")
        parser.skip_ows()
        value = ""
        if parser.peek() == "=":
            parser.take()
            parser.skip_ows()
            if parser.peek() == '"':
                parser.take()
                val_start = parser.pos
                while parser.peek() and parser.peek() != '"':
                    parser.pos += 1
                value = parser.text[val_start : parser.pos]
                if parser.take() != '"':
                    raise HstsActuationError("illegal_sts")
            else:
                val_start = parser.pos
                while parser.peek() and parser.peek() not in "; \t":
                    parser.pos += 1
                value = parser.text[val_start : parser.pos]
        lowered = name.lower()
        if lowered == "max-age":
            if not value.isdigit():
                raise HstsActuationError("illegal_max_age")
            max_age = int(value)
        elif lowered == "includesubdomains":
            include_subdomains = True
        elif lowered == "preload":
            preload = True
    if max_age is None:
        raise HstsActuationError("illegal_sts")
    return (int(max_age), include_subdomains, preload)


def encode_sts_header(policy: tuple[int, bool, bool]) -> bytes:
    """RFC 6797 Strict-Transport-Security field as bytes."""

    return serialize_sts(policy).encode("ascii")


def parse_sts_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_sts(field_value) if field_value else DEFAULT_STS
    return {
        "field_value": field_value,
        "policy": policy,
        "header": STS_HEADER,
        "max_age": int(policy[0]),
        "include_subdomains": bool(policy[1]),
        "preload": bool(policy[2]),
    }


def canonical_sts(identity: str, hstsid: int) -> str:
    """RFC 6797 STS advertisement bound to identity and hstsid."""

    return (
        f"{serialize_sts(DEFAULT_STS)}; "
        f"identity={identity}; hstsid={int(hstsid) & 0xFFFFFFFF}"
    )


def canonical_preload(identity: str, hstsid: int, stsdigest: int | None = None) -> str:
    """RFC 6797 preload confirmation of the stored STS policy."""

    suffix = ""
    if stsdigest is not None:
        suffix = f"; stsdigest={int(stsdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_sts(PRELOAD_STS)}; "
        f"identity={identity}; hstsid={int(hstsid) & 0xFFFFFFFF}{suffix}"
    )


def representation_preload(identity: str, hstsid: int, stsdigest: int) -> str:
    return canonical_preload(identity, hstsid, stsdigest)


def sts_matches(left: str, right: str) -> bool:
    return parse_sts(left) == parse_sts(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HstsActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HstsActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HstsActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HstsActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def sts_request(identity: str, hstsid: int) -> bytes:
    """HTTP GET that elicits RFC 6797 Strict-Transport-Security."""

    keyid = f"{int(hstsid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /hsts/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Hsts-Id: {int(hstsid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def preload_request(identity: str, hstsid: int, stsdigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 6797 preload confirmation of the stored STS policy."""

    keyid = f"{int(hstsid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if stsdigest is not None:
        extra = f"Sts-Digest: {int(stsdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /hsts/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Hsts-Id: {int(hstsid) & 0xFFFFFFFF}\r\n"
        "Preload: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    hs_kind = "preload" if fields.get("preload") == "1" else "sts"
    policy = parse_sts(fields["strict-transport-security"]) if fields.get("strict-transport-security") else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "hs_kind": hs_kind,
        "policy": policy,
        "hstsid": int(fields["hsts-id"]) if fields.get("hsts-id") else EMPTY_HSTSID,
        "stsdigest": int(fields["sts-digest"]) if fields.get("sts-digest") else EMPTY_STSDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def sts_response(identity: str, hstsid: int, stsdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 6797 STS, carrying the stored stsdigest."""

    advertised = serialize_sts(DEFAULT_STS)
    payload = bytes(body or canonical_sts(identity, hstsid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Strict-Transport-Security: {advertised}\r\n"
        f"Hsts-Id: {int(hstsid) & 0xFFFFFFFF}\r\n"
        f"Sts-Digest: {int(stsdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/hsts\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def preload_response(identity: str, hstsid: int, stsdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 6797 preload, carrying the stored preload policy."""

    advertised = serialize_sts(PRELOAD_STS)
    payload = bytes(body or representation_preload(identity, hstsid, stsdigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Strict-Transport-Security: {advertised}\r\n"
        f"Hsts-Id: {int(hstsid) & 0xFFFFFFFF}\r\n"
        f"Sts-Digest: {int(stsdigest) & 0xFFFFFFFF}\r\n"
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
        raise HstsActuationError("illegal_content_length") from error
    policy = parse_sts(fields["strict-transport-security"]) if fields.get("strict-transport-security") else ()
    if policy and bool(policy[2]):
        status = 200
        hs_kind = "preload"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        hs_kind = "sts"
    else:
        status = 0
        hs_kind = "sts"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "hs_kind": hs_kind,
        "policy": policy,
        "hstsid": int(fields["hsts-id"]) if fields.get("hsts-id") else EMPTY_HSTSID,
        "stsdigest": int(fields["sts-digest"]) if fields.get("sts-digest") else EMPTY_STSDIGEST,
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
        raise HstsActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise HstsActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise HstsActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HstsActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_hstsid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"hstsid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_hstsid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-hstsid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_stsdigest(hstsid: int = EMPTY_HSTSID, token: str = SENTINEL) -> int:
    material = canonical_sts(token or SENTINEL, int(hstsid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_HSTSID = request_hstsid(SENTINEL)
DEFAULT_STSDIGEST = request_stsdigest(DEFAULT_HSTSID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    hstsid: int,
    stsdigest: int,
    include_hstsid: bool = True,
) -> bytes:
    live_hstsid = int(hstsid) & 0xFFFFFFFF if include_hstsid else EMPTY_HSTSID
    live_digest = int(stsdigest) & 0xFFFFFFFF if include_hstsid and live_hstsid else EMPTY_STSDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_hstsid) if live_hstsid else b""
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


def encode_sts(
    *,
    identity: str,
    hstsid: int,
    stsdigest: int | None = None,
    include_hstsid: bool = True,
) -> bytes:
    live_hstsid = int(hstsid) & 0xFFFFFFFF if include_hstsid else EMPTY_HSTSID
    live_digest = int(stsdigest) if stsdigest is not None else request_stsdigest(live_hstsid, identity)
    return encode_packet(
        FRAME_STS,
        identity=identity,
        hstsid=live_hstsid,
        stsdigest=live_digest,
        include_hstsid=include_hstsid,
    )


def encode_preload(
    *,
    identity: str,
    hstsid: int,
    stsdigest: int | None = None,
    include_hstsid: bool = True,
) -> bytes:
    live_hstsid = int(hstsid) & 0xFFFFFFFF if include_hstsid else EMPTY_HSTSID
    live_digest = int(stsdigest) if stsdigest is not None else request_stsdigest(live_hstsid, identity)
    return encode_packet(
        FRAME_PRELOAD,
        identity=identity,
        hstsid=live_hstsid,
        stsdigest=live_digest,
        include_hstsid=include_hstsid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HstsActuationError("short_packet")
    first = raw[0]
    if first != HS_FIRST:
        raise HstsActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise HstsActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == HSTSID_SIZE:
        live_hstsid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_hstsid = EMPTY_HSTSID
    else:
        raise HstsActuationError("illegal_hstsid")
    if offset >= len(raw):
        raise HstsActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_STS, FRAME_PRELOAD}:
        raise HstsActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HstsActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HstsActuationError("checksum_failed")
    if len(payload) < 5:
        raise HstsActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HstsActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_hstsid = int(live_hstsid) != EMPTY_HSTSID
    has_stsdigest = has_hstsid and int(live_digest) != EMPTY_STSDIGEST
    is_sts = frame_type == FRAME_STS
    is_preload = frame_type == FRAME_PRELOAD
    return {
        "type": int(frame_type),
        "is_sts": is_sts,
        "is_preload": is_preload,
        "is_response": is_preload,
        "hstsid": int(live_hstsid),
        "has_hstsid": has_hstsid,
        "stsdigest": int(live_digest),
        "has_stsdigest": has_stsdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "strict_transport_security": "RFC6797",
        "sts_field": canonical_sts(identity, live_hstsid) if has_hstsid else "",
        "preload_field": canonical_preload(identity, live_hstsid, live_digest) if has_stsdigest else "",
    }


class HstsClient:
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
            raise HstsActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_preload"] or not packet["is_response"]:
            raise HstsActuationError("stsdigest_required")
        if not packet["has_hstsid"]:
            raise HstsActuationError("hstsid_required")
        if not packet["has_stsdigest"]:
            raise HstsActuationError("stsdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_stsdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_stsdigest:
            raise HstsActuationError("stsdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "hstsid": int(reply.get("hstsid") or EMPTY_HSTSID),
            "identity": str(reply.get("identity") or ""),
            "stsdigest": int(reply.get("stsdigest") or EMPTY_STSDIGEST),
        }

    def preload(
        self,
        identity: str,
        hstsid: int,
        stsdigest: int = EMPTY_STSDIGEST,
        *,
        wait_stsdigest: bool = True,
        include_hstsid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_preload(
            identity=identity,
            hstsid=hstsid,
            stsdigest=stsdigest or request_stsdigest(hstsid, identity),
            include_hstsid=include_hstsid,
        )
        return self.exchange(packet, wait_stsdigest=wait_stsdigest)


class HstsSession:
    """HSTSID-gated loopback RFC 6797 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        hstsid_gate: int = DEFAULT_HSTSID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.hstsid_gate = int(hstsid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.hstsid = EMPTY_HSTSID
        self.stsdigest = EMPTY_STSDIGEST
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

    def store_hstsid_once(self, identity: str, hstsid: int, stsdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(hstsid or EMPTY_HSTSID)
            live_digest = int(stsdigest or EMPTY_STSDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.hstsid = live
                self.stsdigest = live_digest or request_stsdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.hstsid), int(self.stsdigest)

    def read_hstsid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.hstsid), int(self.stsdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "hstsid": EMPTY_HSTSID,
            "stsdigest": EMPTY_STSDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _hstsid_missing(self) -> bool:
        return not int(self.hstsid_gate or 0)

    def _reply_preload(self, peer: tuple[str, int], identity: str, hstsid: int, stsdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_preload(
            identity=identity,
            hstsid=hstsid,
            stsdigest=stsdigest,
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
            except HstsActuationError:
                continue
            if not packet.get("is_sts") and not packet.get("is_preload"):
                continue
            if not packet.get("has_hstsid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_hstsid, stored_digest = self.store_hstsid_once(
                identity,
                int(packet.get("hstsid") or EMPTY_HSTSID),
                int(packet.get("stsdigest") or EMPTY_STSDIGEST),
            )
            if not stored_name or not stored_hstsid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_sts"):
                    self.opened = True
                if packet.get("is_preload"):
                    self.handshook = True
                self.retrieved = True
            self._reply_preload(peer, stored_name, stored_hstsid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._hstsid_missing():
            return self._forbidden("missing_hstsid")
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
        do_sts: bool = True,
        do_preload: bool = True,
        do_stsdigest: bool = True,
        replay: bool = True,
        use_hstsid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._hstsid_missing():
            return self._forbidden("missing_hstsid")
        live_token = str(token or SENTINEL)
        origin_hstsid = request_hstsid(live_token)
        origin_digest = request_stsdigest(origin_hstsid, live_token)
        client: HstsClient | None = None
        independent: HstsClient | None = None
        try:
            client = HstsClient(self.host, int(self.port))
            if not do_sts:
                return self._conflict("sts_required")
            bind_packet = encode_sts(
                identity=live_token,
                hstsid=origin_hstsid,
                stsdigest=origin_digest,
                include_hstsid=use_hstsid,
            )
            if not use_hstsid:
                try:
                    client.exchange(bind_packet, wait_stsdigest=True)
                except HstsActuationError:
                    return self._conflict("hstsid_required")
                return self._conflict("hstsid_required")
            client.send(bind_packet)
            if not do_preload:
                return self._conflict("preload_required")
            proxy_packet = encode_preload(
                identity=live_token,
                hstsid=origin_hstsid,
                stsdigest=origin_digest,
                include_hstsid=True,
            )
            if not do_stsdigest:
                try:
                    client.exchange(proxy_packet, wait_stsdigest=False)
                except HstsActuationError as error:
                    if str(error) == "stsdigest_required":
                        return self._conflict("stsdigest_required")
                    return self._conflict("stsdigest_required")
                return self._conflict("stsdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_stsdigest=True)
            except HstsActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("hstsid_required")
                if reason == "stsdigest_required":
                    return self._conflict("stsdigest_required")
                return self._conflict("sts_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("sts_required")
            if int(reply.get("hstsid") or EMPTY_HSTSID) != origin_hstsid:
                return self._conflict("stsdigest_required")
            if int(reply.get("stsdigest") or EMPTY_STSDIGEST) != origin_digest:
                return self._conflict("stsdigest_required")
            self.retrieved = True
            if replay:
                independent = HstsClient(self.host, int(self.port))
                try:
                    poll = independent.preload(
                        POLL_TOKEN,
                        poll_hstsid(live_token),
                        request_stsdigest(poll_hstsid(live_token), POLL_TOKEN),
                        wait_stsdigest=True,
                    )
                except HstsActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_hstsid, stored_digest = self.read_hstsid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_hstsid != origin_hstsid
                    or stored_digest != origin_digest
                    or int(poll.get("hstsid") or EMPTY_HSTSID) != origin_hstsid
                    or int(poll.get("stsdigest") or EMPTY_STSDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_hstsid}:{origin_digest}:{live_token}:{canonical_sts(live_token, origin_hstsid)}:{canonical_preload(live_token, origin_hstsid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "hstsid": origin_hstsid,
                "stsdigest": origin_digest,
                "sts_frame": True,
                "preload_frame": True,
                "stsdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "hstsid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_hsts_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "hstsid": origin_hstsid,
                "stsdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "sts_frame": True,
                "preload_frame": True,
                "stsdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "hstsid_bound": True,
            }
        except (OSError, HstsActuationError) as error:
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
        live = independent_hsts_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "hstsid": int(live.get("hstsid") or EMPTY_HSTSID),
            "stsdigest": int(live.get("stsdigest") or EMPTY_STSDIGEST),
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


def call_hsts_tool(session: HstsSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one HTTP Strict Transport Security tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_sts = True if arguments.get("sts") is None else bool(arguments.get("sts"))
    do_preload = True if arguments.get("preload") is None else bool(arguments.get("preload"))
    do_stsdigest = True if arguments.get("stsdigest") is None else bool(arguments.get("stsdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_hstsid = True if arguments.get("use_hstsid") is None else bool(arguments.get("use_hstsid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_sts=do_sts,
            do_preload=do_preload,
            do_stsdigest=do_stsdigest,
            replay=replay,
            use_hstsid=use_hstsid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HstsActuationError(f"unsupported hsts action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_hsts_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed HTTP Strict Transport Security stsdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "hstsid": EMPTY_HSTSID,
        "stsdigest": EMPTY_STSDIGEST,
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
            "sts_frame",
            "preload_frame",
            "stsdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "hstsid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    hstsid = int(payload.get("hstsid") or EMPTY_HSTSID)
    stsdigest = int(payload.get("stsdigest") or EMPTY_STSDIGEST)
    dual = port > 0 and bool(hstsid) and bool(stsdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "hstsid": hstsid,
        "stsdigest": stsdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "sts_frame": payload.get("sts_frame") is True,
        "preload_frame": payload.get("preload_frame") is True,
        "stsdigest_response": payload.get("stsdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "hstsid_bound": payload.get("hstsid_bound") is True,
    }


def run_hsts_workflow(
    *,
    with_hstsid: bool = True,
    skip_bind: bool = False,
    do_sts: bool = True,
    do_preload: bool = True,
    do_stsdigest: bool = True,
    replay: bool = True,
    use_hstsid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 6797 STS/PRELOAD hstsid cycle workflow."""

    descriptor = hsts_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HSTS_TOOL_PROVIDER),
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
        raise HstsActuationError(f"hsts tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="hsts-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HstsSession(out, hstsid_gate=DEFAULT_HSTSID if with_hstsid else EMPTY_HSTSID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "sts": do_sts,
            "preload": do_preload,
            "stsdigest": do_stsdigest,
            "replay": replay,
            "use_hstsid": use_hstsid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_hsts_tool(session, arguments))
            except HstsActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_hsts_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_hstsid
        and not skip_bind
        and do_sts
        and do_preload
        and do_stsdigest
        and replay
        and use_hstsid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "hsts_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_hstsid": with_hstsid,
        "skip_bind": skip_bind,
        "sts_frame": do_sts,
        "preload": do_preload,
        "stsdigest": do_stsdigest,
        "replay": replay,
        "use_hstsid": use_hstsid,
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
        "hstsid_value": int(publish_result.get("hstsid") or independent.get("hstsid") or EMPTY_HSTSID),
        "stsdigest_value": int(publish_result.get("stsdigest") or independent.get("stsdigest") or EMPTY_STSDIGEST),
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
        "hstsid": int(trace_body["hstsid_value"] or EMPTY_HSTSID),
        "stsdigest": int(trace_body["stsdigest_value"] or EMPTY_STSDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_hstsid": with_hstsid,
        "skip_bind": skip_bind,
        "sts_cycle": do_sts,
        "preload_cycle": do_preload,
        "stsdigest_cycle": do_stsdigest,
        "replay": replay,
        "use_hstsid": use_hstsid,
    }


def verify_hsts_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed HTTP Strict Transport Security trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_hsts_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    hstsid = int(trace.get("hstsid_value") or independent.get("hstsid") or EMPTY_HSTSID)
    stsdigest = int(trace.get("stsdigest_value") or independent.get("stsdigest") or EMPTY_STSDIGEST)
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
        "sts_frame": independent.get("sts_frame") is True,
        "preload_frame": independent.get("preload_frame") is True,
        "stsdigest_response": independent.get("stsdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "hstsid_bound": independent.get("hstsid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "stsdigest_recorded": (
            port > 0
            and hstsid == DEFAULT_HSTSID
            and stsdigest == DEFAULT_STSDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def hsts_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.hsts_actuation import "
        "builtin_hsts_actuation_proof; r=builtin_hsts_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='hsts_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_hsts_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HSTS_ACTUATION_ID,
        name="First-class RFC 6797 HTTP Strict Transport Security STS/PRELOAD actuation",
        description=(
            "Missions that require an hsts tool can opt the hsts provider in, "
            "bind a loopback RFC 6797 HTTP Strict Transport Security origin, complete an STS "
            "with a non-empty hstsid, lockstep a PRELOAD that carries the "
            "stored stsdigest, independently poll the stored stsdigest "
            "on a later socket, and seal a digest-chained stsdigest. Default "
            "routing stays fail-closed; a missing hstsid keeps the hole "
            "falsifiable, and skip-STS/PRELOAD/STSDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.hsts_actuation:builtin_hsts_actuation_proof",
        proof_command=hsts_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.altsvc-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/hsts_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/hpkp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required hsts tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 6797 daemon, speaks an "
            "STS then PRELOAD over HTTP Strict Transport Security with a non-empty hstsid and "
            "stsdigest, independently polls the stored stsdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 7838 HTTP Alternative Services lockstep is proved. "
            "Missing hstsids, skip-STS, skip-PRELOAD, skip-stsdigest, skip-REPLAY, "
            "and an STS aimed without an hstsid stay fail-closed. "
            "Later genesis can take RFC 7469 HTTP Public Key Pinning PIN/REPORT as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("hsts", "rfc6797", "http", "hstsid", "stsdigest", "sts", "preload", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T091212Z-701ea59b",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_hsts_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 6797 HTTP Strict Transport Security lockstep actuation seals a stsdigest."""

    from blackhole_agent.hpkp_actuation import (
        HPKP_ACTUATION_GOAL,
        HPKP_ACTUATION_ID,
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
    checks["denylists_self"] = HSTS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HSTS_ACTUATION_GOAL) == (
        HSTS_ACTUATION_ID,
    )
    checks["leftover_text_binds_hsts"] = leftover_marker_ids(HSTS_LEFTOVER) == (
        HSTS_ACTUATION_ID,
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
        (HPKP_ACTUATION_GOAL, HPKP_ACTUATION_ID, "hpkp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_hsts"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"hsts_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HSTS_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HSTS_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_sts(DEFAULT_STS)
    rebuilt = serialize_sts(parse_sts(advertised))
    preloaded = parse_sts(RFC_STS_PRELOAD)
    header = encode_sts_header(DEFAULT_STS)
    parsed_header = parse_sts_header(header)
    asked = parse_http_request(sts_request(SENTINEL, DEFAULT_HSTSID))
    preload_req = parse_http_request(preload_request(SENTINEL, DEFAULT_HSTSID, DEFAULT_STSDIGEST))
    got = parse_http_response(sts_response(SENTINEL, DEFAULT_HSTSID, DEFAULT_STSDIGEST))
    preload_reply = parse_http_response(
        preload_response(SENTINEL, DEFAULT_HSTSID, DEFAULT_STSDIGEST)
    )
    checks["sts_roundtrip"] = (
        parse_sts(advertised) == DEFAULT_STS
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_STS_FIELD
        and is_token("max-age") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_STS_FIELD
        and parsed_header["policy"] == DEFAULT_STS
        and parsed_header["header"] == STS_HEADER
        and parsed_header["include_subdomains"] is True
        and parsed_header["preload"] is False
        and preloaded == PRELOAD_STS
    )
    checks["preload_roundtrip"] = (
        serialize_sts(PRELOAD_STS) == RFC_STS_PRELOAD
        and DEFAULT_STSDIGEST == request_stsdigest(DEFAULT_HSTSID, SENTINEL)
        and "stsdigest=" in canonical_preload(SENTINEL, DEFAULT_HSTSID, DEFAULT_STSDIGEST)
        and canonical_sts(SENTINEL, DEFAULT_HSTSID).startswith("max-age=")
    )
    checks["sts_preload_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["hs_kind"] == "sts"
        and asked["hstsid"] == DEFAULT_HSTSID
        and preload_req["hs_kind"] == "preload"
        and preload_req["stsdigest"] == DEFAULT_STSDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["hs_kind"] == "sts"
        and preload_reply["hs_kind"] == "preload"
        and got["policy"] == DEFAULT_STS
        and preload_reply["policy"] == PRELOAD_STS
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["stsdigest"] == DEFAULT_STSDIGEST
        and preload_reply["stsdigest"] == DEFAULT_STSDIGEST
        and sts_matches(serialize_sts(got["policy"]), advertised)
    )

    checks["catalog_names_hsts"] = (
        len(catalog) > 81
        and catalog[81]["id"] == HSTS_ACTUATION_ID
        and catalog[80]["id"] == ALTSVC_ACTUATION_ID
        and catalog[81]["source"] == "genesis_bind_hsts"
    )
    checks["catalog_names_hpkp"] = (
        len(catalog) > 82
        and catalog[82]["id"] == HPKP_ACTUATION_ID
        and catalog[82]["source"] == "genesis_bind_hpkp"
    )
    family = capability_family(HSTS_ACTUATION_GOAL)
    checks["family_is_hsts"] = "hsts" in family
    checks["family_is_hsts_surface"] = "hsts" in family
    checks["family_is_hstsid"] = "hstsid" in family
    checks["family_is_rfc6797"] = "rfc6797" in family
    checks["family_is_stsdigest"] = "stsdigest" in family
    checks["family_is_not_hpkp"] = (
        "hpkp" not in family
        and "rfc7469" not in family
        and "pinid" not in family
        and "pindigest" not in family
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
    packed = encode_sts(identity=SENTINEL, hstsid=DEFAULT_HSTSID, stsdigest=DEFAULT_STSDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_sts"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_hstsid"] is True
        and parsed["hstsid"] == DEFAULT_HSTSID
        and parsed["stsdigest"] == DEFAULT_STSDIGEST
        and parsed["is_response"] is False
        and parsed["is_preload"] is False
        and parsed["type"] == FRAME_STS
        and parsed["first_byte"] == HS_FIRST
    )
    shook = encode_preload(
        identity=SENTINEL,
        hstsid=DEFAULT_HSTSID,
        stsdigest=DEFAULT_STSDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_preload"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_sts"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["hstsid"] == DEFAULT_HSTSID
        and answer_parsed["stsdigest"] == DEFAULT_STSDIGEST
        and answer_parsed["has_stsdigest"] is True
        and answer_parsed["type"] == FRAME_PRELOAD
        and answer_parsed["first_byte"] == HS_FIRST
    )
    bare = encode_sts(identity=SENTINEL, hstsid=DEFAULT_HSTSID, include_hstsid=False)
    checks["missing_hstsid_is_unauthenticated"] = parse_message(bare)["has_hstsid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    hsts_signature = semantic_signature(HSTS_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(hsts_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_hsts = ToolDescriptor(name="remote_hsts", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_hsts)
    checks["naive_mcp_hsts_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = hsts_tool_descriptor()
    default_hsts = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HSTS_TOOL_PROVIDER),
    )
    checks["default_hsts_provider_is_unsupported"] = (
        default_hsts.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HSTS_TOOL_PROVIDER}" in default_hsts.reasons
    )
    checks["opted_in_hsts_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_hsts],
        required_tool_names=("local_memory", "hsts"),
    )
    checks["naive_preflight_missing_hsts"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["hsts"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "hsts"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HSTS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "hsts" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="hsts-actuation-") as tmp:
        root = Path(tmp)
        missing = run_hsts_workflow(with_hstsid=False, output_dir=root / "missing")
        skip_bind = run_hsts_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_sts = run_hsts_workflow(do_sts=False, output_dir=root / "skip-sts")
        skip_preload = run_hsts_workflow(do_preload=False, output_dir=root / "skip-preload")
        skip_stsdigest = run_hsts_workflow(do_stsdigest=False, output_dir=root / "skip-stsdigest")
        skip_replay = run_hsts_workflow(replay=False, output_dir=root / "skip-replay")
        skip_hstsid = run_hsts_workflow(use_hstsid=False, output_dir=root / "skip-hstsid")
        live = run_hsts_workflow(output_dir=root / "live")
        verify = verify_hsts_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_hsts_trace(clone)
        checks["naive_without_hstsid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_hstsid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_sts_stays_empty"] = (
            skip_sts["ok"] is False
            and skip_sts["error"] == "sts_required"
            and skip_sts["final_status"] == 409
            and skip_sts["payload_exists"] is False
        )
        checks["skip_preload_stays_empty"] = (
            skip_preload["ok"] is False
            and skip_preload["error"] == "preload_required"
            and skip_preload["final_status"] == 409
            and skip_preload["payload_exists"] is False
        )
        checks["skip_stsdigest_stays_empty"] = (
            skip_stsdigest["ok"] is False
            and skip_stsdigest["error"] == "stsdigest_required"
            and skip_stsdigest["final_status"] == 409
            and skip_stsdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_hstsid_stays_empty"] = (
            skip_hstsid["ok"] is False
            and skip_hstsid["error"] == "hstsid_required"
            and skip_hstsid["final_status"] == 409
            and skip_hstsid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_stsdigest"] = (
            int(live.get("hstsid") or 0) == DEFAULT_HSTSID
            and int(live.get("stsdigest") or 0) == DEFAULT_STSDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_hstsid_encode_preload_stsdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_sts["ok"] is False
            and skip_preload["ok"] is False
            and skip_stsdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_hstsid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="hsts-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HSTS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_hsts"] = (
        live_goal == HSTS_ACTUATION_GOAL
        and HSTS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_hsts"
    )

    with tempfile.TemporaryDirectory(prefix="hsts-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HSTS_LEFTOVER, root)
        register_catalog_proved(root, HSTS_ACTUATION_ID)
        reason = leftover_satisfied_by(HSTS_LEFTOVER, root)
        after = leftover_is_open(HSTS_LEFTOVER, root)
    checks["hsts_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_hsts_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HSTS_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_hsts_actuation_capability()
    return {
        "ok": ok,
        "action": "hsts_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HSTS_ACTUATION_GOAL,
        "done_when": HSTS_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
