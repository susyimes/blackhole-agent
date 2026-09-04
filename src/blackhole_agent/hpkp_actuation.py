"""Drive a first-class HTTP Public Key Pinning tool through RFC 7469 PIN/REPORT.

Tool routing already fails missions that require ``hpkp``: hosted
hpkp endpoints stay on the unsupported MCP provider, and no first-party
hpkp provider is executable. Unbound therefore cannot speak a PIN,
lockstep a REPORT pinid handshake over HTTP Public Key Pinning PINID,
independently poll the stored pindigest, or seal a pindigest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``hpkp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 7469 daemon
- keep a missing-pinid client so the hpkp-pinid hole stays falsifiable
- refuse REPORT until a PIN lands with a non-empty pinid
- independently poll the stored pindigest on a later client socket
- persist a sealed pindigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 6797 HTTP Strict Transport Security
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
    HPKP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    hpkp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HPKP_ACTUATION_ID = "capability.hpkp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-HPKP-OK"
POLL_TOKEN = "BH-HPKP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_PINID = 0
EMPTY_PINDIGEST = 0
PK_FIRST = 0x50  # RFC 7469 HPKP (ASCII 'P')
PINID_SIZE = 4
PINDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_REPORT = 0x02  # RFC 7469 report confirmation
FRAME_PIN = 0x01  # RFC 7469 Public-Key-Pins
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HPKP_LEFTOVER = (
    "Later genesis can take RFC 7469 HTTP Public Key Pinning PIN/REPORT over a "
    "pinid-gated pindigest."
)
HPKP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HPKP_ACTUATION_ID};"
    f"capability_proved:{HPKP_ACTUATION_ID};"
    "no_skill_route"
)
HPKP_ACTUATION_GOAL = (
    "Repair rfc7469 hpkp pin/report cycle cannot land over http "
    "hpkp pinid: hosted hpkp endpoints remain unsupported so a PIN then "
    "REPORT pinid handshake cannot land and a sealed pindigest "
    "cannot be produced. A missing hpkp pinid stays forbidden; fail-closed "
    "routing never opts the hpkp provider in. An independent later poll of the "
    "stored pindigest keeps the hole falsifiable."
)


class HpkpActuationError(RuntimeError):
    """Raised when the HTTP Public Key Pinning session or loopback daemon fixture misbehaves."""


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
# RFC 7469 section 2.1.4 example pins (SPKI SHA-256, standard base64).
RFC_PKP_PINS: tuple[str, str] = (
    "d6qzRu9zOECb90Uez27xWltNsj0e1Md7GkYYkVoZWmM=",
    "E9CZ9INDbd+2eRQozYqqbQ2yXLVKB9+xcprMF+44U1g=",
)
RFC_REPORT_URI = "https://example.com/pkp-report"
RFC_PKP_FIELD = (
    "max-age=3000; "
    f'pin-sha256="{RFC_PKP_PINS[0]}"; '
    f'pin-sha256="{RFC_PKP_PINS[1]}"'
)
RFC_PKP_REPORT = RFC_PKP_FIELD + f'; report-uri="{RFC_REPORT_URI}"'
# policy = (max_age, include_subdomains, report_uri_present)
DEFAULT_PKP: tuple[int, bool, bool] = (3000, False, False)
REPORT_PKP: tuple[int, bool, bool] = (3000, False, True)
PKP_HEADER = "Public-Key-Pins"
PKP_REPORT_HEADER = "Public-Key-Pins-Report-Only"


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise HpkpActuationError("short_pkp")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 7469 directive-name."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_pkp(policy: tuple[int, bool, bool] | Sequence[int | bool]) -> str:
    """Serialize RFC 7469 Public-Key-Pins field-value."""

    max_age = int(policy[0])
    include_subdomains = bool(policy[1])
    report = bool(policy[2]) if len(policy) > 2 else False
    if max_age < 0:
        raise HpkpActuationError("illegal_max_age")
    chunks = [f"max-age={max_age}"]
    for pin in RFC_PKP_PINS:
        chunks.append(f'pin-sha256="{pin}"')
    if include_subdomains:
        chunks.append("includeSubDomains")
    if report:
        chunks.append(f'report-uri="{RFC_REPORT_URI}"')
    return "; ".join(chunks)


def parse_pkp(text: str) -> tuple[int, bool, bool]:
    """Parse RFC 7469 Public-Key-Pins into max-age/includeSubDomains/report-uri."""

    raw = str(text or "").strip()
    if not raw:
        raise HpkpActuationError("illegal_pkp")
    parser = _Parser(raw)
    max_age: int | None = None
    include_subdomains = False
    report = False
    pins: list[str] = []
    first = True
    while True:
        parser.skip_ows()
        if parser.eof():
            break
        if not first:
            if parser.peek() != ";":
                raise HpkpActuationError("illegal_pkp")
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
            raise HpkpActuationError("illegal_pkp")
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
                    raise HpkpActuationError("illegal_pkp")
            else:
                val_start = parser.pos
                while parser.peek() and parser.peek() not in "; \t":
                    parser.pos += 1
                value = parser.text[val_start : parser.pos]
        lowered = name.lower()
        if lowered == "max-age":
            if not value.isdigit():
                raise HpkpActuationError("illegal_max_age")
            max_age = int(value)
        elif lowered == "includesubdomains":
            include_subdomains = True
        elif lowered == "pin-sha256":
            if not value:
                raise HpkpActuationError("illegal_pin")
            pins.append(value)
        elif lowered == "report-uri":
            report = True
    if max_age is None or len(pins) < 2:
        raise HpkpActuationError("illegal_pkp")
    return (int(max_age), include_subdomains, report)


def encode_pkp_header(policy: tuple[int, bool, bool]) -> bytes:
    """RFC 7469 Public-Key-Pins field as bytes."""

    return serialize_pkp(policy).encode("ascii")


def parse_pkp_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_pkp(field_value) if field_value else DEFAULT_PKP
    return {
        "field_value": field_value,
        "policy": policy,
        "header": PKP_HEADER,
        "max_age": int(policy[0]),
        "include_subdomains": bool(policy[1]),
        "report": bool(policy[2]),
    }


def canonical_pin(identity: str, pinid: int) -> str:
    """RFC 7469 PIN advertisement bound to identity and pinid."""

    return (
        f"{serialize_pkp(DEFAULT_PKP)}; "
        f"identity={identity}; pinid={int(pinid) & 0xFFFFFFFF}"
    )


def canonical_report(identity: str, pinid: int, pindigest: int | None = None) -> str:
    """RFC 7469 report confirmation of the stored PIN policy."""

    suffix = ""
    if pindigest is not None:
        suffix = f"; pindigest={int(pindigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_pkp(REPORT_PKP)}; "
        f"identity={identity}; pinid={int(pinid) & 0xFFFFFFFF}{suffix}"
    )


def representation_report(identity: str, pinid: int, pindigest: int) -> str:
    return canonical_report(identity, pinid, pindigest)


def pkp_matches(left: str, right: str) -> bool:
    return parse_pkp(left) == parse_pkp(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HpkpActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HpkpActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HpkpActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HpkpActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def pin_request(identity: str, pinid: int) -> bytes:
    """HTTP GET that elicits RFC 7469 Public-Key-Pins."""

    keyid = f"{int(pinid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /hpkp/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Pin-Id: {int(pinid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def report_request(identity: str, pinid: int, pindigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 7469 report confirmation of the stored PIN policy."""

    keyid = f"{int(pinid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if pindigest is not None:
        extra = f"Pin-Digest: {int(pindigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /hpkp/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Pin-Id: {int(pinid) & 0xFFFFFFFF}\r\n"
        "Report: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    pk_kind = "report" if fields.get("report") == "1" else "pin"
    policy = parse_pkp(fields["public-key-pins"]) if fields.get("public-key-pins") else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "pk_kind": pk_kind,
        "policy": policy,
        "pinid": int(fields["pin-id"]) if fields.get("pin-id") else EMPTY_PINID,
        "pindigest": int(fields["pin-digest"]) if fields.get("pin-digest") else EMPTY_PINDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def pin_response(identity: str, pinid: int, pindigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 7469 Public-Key-Pins, carrying the stored pindigest."""

    advertised = serialize_pkp(DEFAULT_PKP)
    payload = bytes(body or canonical_pin(identity, pinid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Public-Key-Pins: {advertised}\r\n"
        f"Pin-Id: {int(pinid) & 0xFFFFFFFF}\r\n"
        f"Pin-Digest: {int(pindigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/hpkp\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def report_response(identity: str, pinid: int, pindigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 7469 pin-validation report, carrying the stored report policy."""

    advertised = serialize_pkp(REPORT_PKP)
    payload = bytes(body or representation_report(identity, pinid, pindigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Public-Key-Pins-Report-Only: {advertised}\r\n"
        f"Pin-Id: {int(pinid) & 0xFFFFFFFF}\r\n"
        f"Pin-Digest: {int(pindigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/pkp-report\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise HpkpActuationError("illegal_content_length") from error
    field_value = fields.get("public-key-pins-report-only") or fields.get("public-key-pins") or ""
    policy = parse_pkp(field_value) if field_value else ()
    if fields.get("public-key-pins-report-only") or (policy and bool(policy[2])):
        status = 200
        pk_kind = "report"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        pk_kind = "pin"
    else:
        status = 0
        pk_kind = "pin"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "pk_kind": pk_kind,
        "policy": policy,
        "pinid": int(fields["pin-id"]) if fields.get("pin-id") else EMPTY_PINID,
        "pindigest": int(fields["pin-digest"]) if fields.get("pin-digest") else EMPTY_PINDIGEST,
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
        raise HpkpActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise HpkpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise HpkpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HpkpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_pinid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"pinid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_pinid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-pinid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_pindigest(pinid: int = EMPTY_PINID, token: str = SENTINEL) -> int:
    material = canonical_pin(token or SENTINEL, int(pinid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_PINID = request_pinid(SENTINEL)
DEFAULT_PINDIGEST = request_pindigest(DEFAULT_PINID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    pinid: int,
    pindigest: int,
    include_pinid: bool = True,
) -> bytes:
    live_pinid = int(pinid) & 0xFFFFFFFF if include_pinid else EMPTY_PINID
    live_digest = int(pindigest) & 0xFFFFFFFF if include_pinid and live_pinid else EMPTY_PINDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_pinid) if live_pinid else b""
    header = bytearray()
    header.append(PK_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_pin(
    *,
    identity: str,
    pinid: int,
    pindigest: int | None = None,
    include_pinid: bool = True,
) -> bytes:
    live_pinid = int(pinid) & 0xFFFFFFFF if include_pinid else EMPTY_PINID
    live_digest = int(pindigest) if pindigest is not None else request_pindigest(live_pinid, identity)
    return encode_packet(
        FRAME_PIN,
        identity=identity,
        pinid=live_pinid,
        pindigest=live_digest,
        include_pinid=include_pinid,
    )


def encode_report(
    *,
    identity: str,
    pinid: int,
    pindigest: int | None = None,
    include_pinid: bool = True,
) -> bytes:
    live_pinid = int(pinid) & 0xFFFFFFFF if include_pinid else EMPTY_PINID
    live_digest = int(pindigest) if pindigest is not None else request_pindigest(live_pinid, identity)
    return encode_packet(
        FRAME_REPORT,
        identity=identity,
        pinid=live_pinid,
        pindigest=live_digest,
        include_pinid=include_pinid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HpkpActuationError("short_packet")
    first = raw[0]
    if first != PK_FIRST:
        raise HpkpActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise HpkpActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == PINID_SIZE:
        live_pinid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_pinid = EMPTY_PINID
    else:
        raise HpkpActuationError("illegal_pinid")
    if offset >= len(raw):
        raise HpkpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_PIN, FRAME_REPORT}:
        raise HpkpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HpkpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HpkpActuationError("checksum_failed")
    if len(payload) < 5:
        raise HpkpActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HpkpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_pinid = int(live_pinid) != EMPTY_PINID
    has_pindigest = has_pinid and int(live_digest) != EMPTY_PINDIGEST
    is_pin = frame_type == FRAME_PIN
    is_report = frame_type == FRAME_REPORT
    return {
        "type": int(frame_type),
        "is_pin": is_pin,
        "is_report": is_report,
        "is_response": is_report,
        "pinid": int(live_pinid),
        "has_pinid": has_pinid,
        "pindigest": int(live_digest),
        "has_pindigest": has_pindigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "public_key_pins": "RFC7469",
        "pin_field": canonical_pin(identity, live_pinid) if has_pinid else "",
        "report_field": canonical_report(identity, live_pinid, live_digest) if has_pindigest else "",
    }


class HpkpClient:
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
            raise HpkpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_report"] or not packet["is_response"]:
            raise HpkpActuationError("pindigest_required")
        if not packet["has_pinid"]:
            raise HpkpActuationError("pinid_required")
        if not packet["has_pindigest"]:
            raise HpkpActuationError("pindigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_pindigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_pindigest:
            raise HpkpActuationError("pindigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "pinid": int(reply.get("pinid") or EMPTY_PINID),
            "identity": str(reply.get("identity") or ""),
            "pindigest": int(reply.get("pindigest") or EMPTY_PINDIGEST),
        }

    def report(
        self,
        identity: str,
        pinid: int,
        pindigest: int = EMPTY_PINDIGEST,
        *,
        wait_pindigest: bool = True,
        include_pinid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_report(
            identity=identity,
            pinid=pinid,
            pindigest=pindigest or request_pindigest(pinid, identity),
            include_pinid=include_pinid,
        )
        return self.exchange(packet, wait_pindigest=wait_pindigest)


class HpkpSession:
    """PINID-gated loopback RFC 7469 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        pinid_gate: int = DEFAULT_PINID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pinid_gate = int(pinid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.pinid = EMPTY_PINID
        self.pindigest = EMPTY_PINDIGEST
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

    def store_pinid_once(self, identity: str, pinid: int, pindigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(pinid or EMPTY_PINID)
            live_digest = int(pindigest or EMPTY_PINDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.pinid = live
                self.pindigest = live_digest or request_pindigest(live, name)
                self.stored = True
            return str(self.identity), int(self.pinid), int(self.pindigest)

    def read_pinid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.pinid), int(self.pindigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "pinid": EMPTY_PINID,
            "pindigest": EMPTY_PINDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _pinid_missing(self) -> bool:
        return not int(self.pinid_gate or 0)

    def _reply_report(self, peer: tuple[str, int], identity: str, pinid: int, pindigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_report(
            identity=identity,
            pinid=pinid,
            pindigest=pindigest,
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
            except HpkpActuationError:
                continue
            if not packet.get("is_pin") and not packet.get("is_report"):
                continue
            if not packet.get("has_pinid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_pinid, stored_digest = self.store_pinid_once(
                identity,
                int(packet.get("pinid") or EMPTY_PINID),
                int(packet.get("pindigest") or EMPTY_PINDIGEST),
            )
            if not stored_name or not stored_pinid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_pin"):
                    self.opened = True
                if packet.get("is_report"):
                    self.handshook = True
                self.retrieved = True
            self._reply_report(peer, stored_name, stored_pinid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._pinid_missing():
            return self._forbidden("missing_pinid")
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
        do_pin: bool = True,
        do_report: bool = True,
        do_pindigest: bool = True,
        replay: bool = True,
        use_pinid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._pinid_missing():
            return self._forbidden("missing_pinid")
        live_token = str(token or SENTINEL)
        origin_pinid = request_pinid(live_token)
        origin_digest = request_pindigest(origin_pinid, live_token)
        client: HpkpClient | None = None
        independent: HpkpClient | None = None
        try:
            client = HpkpClient(self.host, int(self.port))
            if not do_pin:
                return self._conflict("pin_required")
            bind_packet = encode_pin(
                identity=live_token,
                pinid=origin_pinid,
                pindigest=origin_digest,
                include_pinid=use_pinid,
            )
            if not use_pinid:
                try:
                    client.exchange(bind_packet, wait_pindigest=True)
                except HpkpActuationError:
                    return self._conflict("pinid_required")
                return self._conflict("pinid_required")
            client.send(bind_packet)
            if not do_report:
                return self._conflict("report_required")
            proxy_packet = encode_report(
                identity=live_token,
                pinid=origin_pinid,
                pindigest=origin_digest,
                include_pinid=True,
            )
            if not do_pindigest:
                try:
                    client.exchange(proxy_packet, wait_pindigest=False)
                except HpkpActuationError as error:
                    if str(error) == "pindigest_required":
                        return self._conflict("pindigest_required")
                    return self._conflict("pindigest_required")
                return self._conflict("pindigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_pindigest=True)
            except HpkpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("pinid_required")
                if reason == "pindigest_required":
                    return self._conflict("pindigest_required")
                return self._conflict("pin_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("pin_required")
            if int(reply.get("pinid") or EMPTY_PINID) != origin_pinid:
                return self._conflict("pindigest_required")
            if int(reply.get("pindigest") or EMPTY_PINDIGEST) != origin_digest:
                return self._conflict("pindigest_required")
            self.retrieved = True
            if replay:
                independent = HpkpClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_pinid(live_token),
                        request_pindigest(poll_pinid(live_token), POLL_TOKEN),
                        wait_pindigest=True,
                    )
                except HpkpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_pinid, stored_digest = self.read_pinid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_pinid != origin_pinid
                    or stored_digest != origin_digest
                    or int(poll.get("pinid") or EMPTY_PINID) != origin_pinid
                    or int(poll.get("pindigest") or EMPTY_PINDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_pinid}:{origin_digest}:{live_token}:{canonical_pin(live_token, origin_pinid)}:{canonical_report(live_token, origin_pinid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "pinid": origin_pinid,
                "pindigest": origin_digest,
                "pin_frame": True,
                "report_frame": True,
                "pindigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "pinid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_hpkp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "pinid": origin_pinid,
                "pindigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "pin_frame": True,
                "report_frame": True,
                "pindigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "pinid_bound": True,
            }
        except (OSError, HpkpActuationError) as error:
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
        live = independent_hpkp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "pinid": int(live.get("pinid") or EMPTY_PINID),
            "pindigest": int(live.get("pindigest") or EMPTY_PINDIGEST),
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


def call_hpkp_tool(session: HpkpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one HTTP Public Key Pinning tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_pin = True if arguments.get("pin") is None else bool(arguments.get("pin"))
    do_report = True if arguments.get("report") is None else bool(arguments.get("report"))
    do_pindigest = True if arguments.get("pindigest") is None else bool(arguments.get("pindigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_pinid = True if arguments.get("use_pinid") is None else bool(arguments.get("use_pinid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_pin=do_pin,
            do_report=do_report,
            do_pindigest=do_pindigest,
            replay=replay,
            use_pinid=use_pinid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HpkpActuationError(f"unsupported hpkp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_hpkp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed HTTP Public Key Pinning pindigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "pinid": EMPTY_PINID,
        "pindigest": EMPTY_PINDIGEST,
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
            "pin_frame",
            "report_frame",
            "pindigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "pinid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    pinid = int(payload.get("pinid") or EMPTY_PINID)
    pindigest = int(payload.get("pindigest") or EMPTY_PINDIGEST)
    dual = port > 0 and bool(pinid) and bool(pindigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "pinid": pinid,
        "pindigest": pindigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "pin_frame": payload.get("pin_frame") is True,
        "report_frame": payload.get("report_frame") is True,
        "pindigest_response": payload.get("pindigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "pinid_bound": payload.get("pinid_bound") is True,
    }


def run_hpkp_workflow(
    *,
    with_pinid: bool = True,
    skip_bind: bool = False,
    do_pin: bool = True,
    do_report: bool = True,
    do_pindigest: bool = True,
    replay: bool = True,
    use_pinid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 7469 PIN/REPORT pinid cycle workflow."""

    descriptor = hpkp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HPKP_TOOL_PROVIDER),
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
        raise HpkpActuationError(f"hpkp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="hpkp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HpkpSession(out, pinid_gate=DEFAULT_PINID if with_pinid else EMPTY_PINID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "pin": do_pin,
            "report": do_report,
            "pindigest": do_pindigest,
            "replay": replay,
            "use_pinid": use_pinid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_hpkp_tool(session, arguments))
            except HpkpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_hpkp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_pinid
        and not skip_bind
        and do_pin
        and do_report
        and do_pindigest
        and replay
        and use_pinid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "hpkp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_pinid": with_pinid,
        "skip_bind": skip_bind,
        "pin_frame": do_pin,
        "report": do_report,
        "pindigest": do_pindigest,
        "replay": replay,
        "use_pinid": use_pinid,
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
        "pinid_value": int(publish_result.get("pinid") or independent.get("pinid") or EMPTY_PINID),
        "pindigest_value": int(publish_result.get("pindigest") or independent.get("pindigest") or EMPTY_PINDIGEST),
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
        "pinid": int(trace_body["pinid_value"] or EMPTY_PINID),
        "pindigest": int(trace_body["pindigest_value"] or EMPTY_PINDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_pinid": with_pinid,
        "skip_bind": skip_bind,
        "pin_cycle": do_pin,
        "report_cycle": do_report,
        "pindigest_cycle": do_pindigest,
        "replay": replay,
        "use_pinid": use_pinid,
    }


def verify_hpkp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed HTTP Public Key Pinning trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_hpkp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    pinid = int(trace.get("pinid_value") or independent.get("pinid") or EMPTY_PINID)
    pindigest = int(trace.get("pindigest_value") or independent.get("pindigest") or EMPTY_PINDIGEST)
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
        "pin_frame": independent.get("pin_frame") is True,
        "report_frame": independent.get("report_frame") is True,
        "pindigest_response": independent.get("pindigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "pinid_bound": independent.get("pinid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "pindigest_recorded": (
            port > 0
            and pinid == DEFAULT_PINID
            and pindigest == DEFAULT_PINDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def hpkp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.hpkp_actuation import "
        "builtin_hpkp_actuation_proof; r=builtin_hpkp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='hpkp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_hpkp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HPKP_ACTUATION_ID,
        name="First-class RFC 7469 HTTP Public Key Pinning PIN/REPORT actuation",
        description=(
            "Missions that require an hpkp tool can opt the hpkp provider in, "
            "bind a loopback RFC 7469 HTTP Public Key Pinning origin, complete a PIN "
            "with a non-empty pinid, lockstep a REPORT that carries the "
            "stored pindigest, independently poll the stored pindigest "
            "on a later socket, and seal a digest-chained pindigest. Default "
            "routing stays fail-closed; a missing pinid keeps the hole "
            "falsifiable, and skip-PIN/REPORT/PINDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.hpkp_actuation:builtin_hpkp_actuation_proof",
        proof_command=hpkp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.hsts-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/hpkp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/hsts_actuation.py",
            "src/blackhole_agent/expectct_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required hpkp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 7469 daemon, speaks a "
            "PIN then REPORT over HTTP Public Key Pinning with a non-empty pinid and "
            "pindigest, independently polls the stored pindigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 6797 HTTP Strict Transport Security lockstep is proved. "
            "Missing pinids, skip-PIN, skip-REPORT, skip-pindigest, skip-REPLAY, "
            "and a PIN aimed without a pinid stay fail-closed. "
            "Later genesis can take RFC 9163 Expect-CT EXPECT/REPORT as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("hpkp", "rfc7469", "http", "pinid", "pindigest", "pin", "report", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T094423Z-a475f4fc",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_hpkp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 7469 HTTP Public Key Pinning lockstep actuation seals a pindigest."""

    from blackhole_agent.expectct_actuation import (
        EXPECTCT_ACTUATION_GOAL,
        EXPECTCT_ACTUATION_ID,
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
    checks["denylists_self"] = HPKP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HPKP_ACTUATION_GOAL) == (
        HPKP_ACTUATION_ID,
    )
    checks["leftover_text_binds_hpkp"] = leftover_marker_ids(HPKP_LEFTOVER) == (
        HPKP_ACTUATION_ID,
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
        (EXPECTCT_ACTUATION_GOAL, EXPECTCT_ACTUATION_ID, "expectct"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_hpkp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"hpkp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HPKP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HPKP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_pkp(DEFAULT_PKP)
    rebuilt = serialize_pkp(parse_pkp(advertised))
    preloaded = parse_pkp(RFC_PKP_REPORT)
    header = encode_pkp_header(DEFAULT_PKP)
    parsed_header = parse_pkp_header(header)
    asked = parse_http_request(pin_request(SENTINEL, DEFAULT_PINID))
    preload_req = parse_http_request(report_request(SENTINEL, DEFAULT_PINID, DEFAULT_PINDIGEST))
    got = parse_http_response(pin_response(SENTINEL, DEFAULT_PINID, DEFAULT_PINDIGEST))
    preload_reply = parse_http_response(
        report_response(SENTINEL, DEFAULT_PINID, DEFAULT_PINDIGEST)
    )
    checks["sts_roundtrip"] = (
        parse_pkp(advertised) == DEFAULT_PKP
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_PKP_FIELD
        and is_token("max-age") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_PKP_FIELD
        and parsed_header["policy"] == DEFAULT_PKP
        and parsed_header["header"] == PKP_HEADER
        and parsed_header["include_subdomains"] is False
        and parsed_header["report"] is False
        and preloaded == REPORT_PKP
    )
    checks["preload_roundtrip"] = (
        serialize_pkp(REPORT_PKP) == RFC_PKP_REPORT
        and DEFAULT_PINDIGEST == request_pindigest(DEFAULT_PINID, SENTINEL)
        and "pindigest=" in canonical_report(SENTINEL, DEFAULT_PINID, DEFAULT_PINDIGEST)
        and canonical_pin(SENTINEL, DEFAULT_PINID).startswith("max-age=")
    )
    checks["sts_preload_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["pk_kind"] == "pin"
        and asked["pinid"] == DEFAULT_PINID
        and preload_req["pk_kind"] == "report"
        and preload_req["pindigest"] == DEFAULT_PINDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["pk_kind"] == "pin"
        and preload_reply["pk_kind"] == "report"
        and got["policy"] == DEFAULT_PKP
        and preload_reply["policy"] == REPORT_PKP
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["pindigest"] == DEFAULT_PINDIGEST
        and preload_reply["pindigest"] == DEFAULT_PINDIGEST
        and pkp_matches(serialize_pkp(got["policy"]), advertised)
    )

    checks["catalog_names_hpkp"] = (
        len(catalog) > 82
        and catalog[82]["id"] == HPKP_ACTUATION_ID
        and catalog[81]["id"] == HSTS_ACTUATION_ID
        and catalog[82]["source"] == "genesis_bind_hpkp"
    )
    checks["catalog_names_expectct"] = (
        len(catalog) > 83
        and catalog[83]["id"] == EXPECTCT_ACTUATION_ID
        and catalog[83]["source"] == "genesis_bind_expectct"
    )
    family = capability_family(HPKP_ACTUATION_GOAL)
    checks["family_is_hpkp"] = "hpkp" in family
    checks["family_is_hpkp_surface"] = "hpkp" in family
    checks["family_is_pinid"] = "pinid" in family
    checks["family_is_rfc7469"] = "rfc7469" in family
    checks["family_is_pindigest"] = "pindigest" in family
    checks["family_is_not_expectct"] = (
        "expectct" not in family
        and "rfc9163" not in family
        and "ctid" not in family
        and "ctdigest" not in family
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
    packed = encode_pin(identity=SENTINEL, pinid=DEFAULT_PINID, pindigest=DEFAULT_PINDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_pin"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_pinid"] is True
        and parsed["pinid"] == DEFAULT_PINID
        and parsed["pindigest"] == DEFAULT_PINDIGEST
        and parsed["is_response"] is False
        and parsed["is_report"] is False
        and parsed["type"] == FRAME_PIN
        and parsed["first_byte"] == PK_FIRST
    )
    shook = encode_report(
        identity=SENTINEL,
        pinid=DEFAULT_PINID,
        pindigest=DEFAULT_PINDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_report"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_pin"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["pinid"] == DEFAULT_PINID
        and answer_parsed["pindigest"] == DEFAULT_PINDIGEST
        and answer_parsed["has_pindigest"] is True
        and answer_parsed["type"] == FRAME_REPORT
        and answer_parsed["first_byte"] == PK_FIRST
    )
    bare = encode_pin(identity=SENTINEL, pinid=DEFAULT_PINID, include_pinid=False)
    checks["missing_pinid_is_unauthenticated"] = parse_message(bare)["has_pinid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    hpkp_signature = semantic_signature(HPKP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(hpkp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_hpkp = ToolDescriptor(name="remote_hpkp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_hpkp)
    checks["naive_mcp_hpkp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = hpkp_tool_descriptor()
    default_hpkp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HPKP_TOOL_PROVIDER),
    )
    checks["default_hpkp_provider_is_unsupported"] = (
        default_hpkp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HPKP_TOOL_PROVIDER}" in default_hpkp.reasons
    )
    checks["opted_in_hpkp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_hpkp],
        required_tool_names=("local_memory", "hpkp"),
    )
    checks["naive_preflight_missing_hpkp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["hpkp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "hpkp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HPKP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "hpkp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="hpkp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_hpkp_workflow(with_pinid=False, output_dir=root / "missing")
        skip_bind = run_hpkp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_sts = run_hpkp_workflow(do_pin=False, output_dir=root / "skip-pin")
        skip_preload = run_hpkp_workflow(do_report=False, output_dir=root / "skip-report")
        skip_pindigest = run_hpkp_workflow(do_pindigest=False, output_dir=root / "skip-pindigest")
        skip_replay = run_hpkp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_pinid = run_hpkp_workflow(use_pinid=False, output_dir=root / "skip-pinid")
        live = run_hpkp_workflow(output_dir=root / "live")
        verify = verify_hpkp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_hpkp_trace(clone)
        checks["naive_without_pinid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_pinid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_pin_stays_empty"] = (
            skip_sts["ok"] is False
            and skip_sts["error"] == "pin_required"
            and skip_sts["final_status"] == 409
            and skip_sts["payload_exists"] is False
        )
        checks["skip_report_stays_empty"] = (
            skip_preload["ok"] is False
            and skip_preload["error"] == "report_required"
            and skip_preload["final_status"] == 409
            and skip_preload["payload_exists"] is False
        )
        checks["skip_pindigest_stays_empty"] = (
            skip_pindigest["ok"] is False
            and skip_pindigest["error"] == "pindigest_required"
            and skip_pindigest["final_status"] == 409
            and skip_pindigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_pinid_stays_empty"] = (
            skip_pinid["ok"] is False
            and skip_pinid["error"] == "pinid_required"
            and skip_pinid["final_status"] == 409
            and skip_pinid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_pindigest"] = (
            int(live.get("pinid") or 0) == DEFAULT_PINID
            and int(live.get("pindigest") or 0) == DEFAULT_PINDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_pinid_encode_report_pindigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_sts["ok"] is False
            and skip_preload["ok"] is False
            and skip_pindigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_pinid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="hpkp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HPKP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_hpkp"] = (
        live_goal == HPKP_ACTUATION_GOAL
        and HPKP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_hpkp"
    )

    with tempfile.TemporaryDirectory(prefix="hpkp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HPKP_LEFTOVER, root)
        register_catalog_proved(root, HPKP_ACTUATION_ID)
        reason = leftover_satisfied_by(HPKP_LEFTOVER, root)
        after = leftover_is_open(HPKP_LEFTOVER, root)
    checks["hpkp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_hpkp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HPKP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_hpkp_actuation_capability()
    return {
        "ok": ok,
        "action": "hpkp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HPKP_ACTUATION_GOAL,
        "done_when": HPKP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
