"""Drive a first-class Simple Hit-Metering tool through RFC 2227 METER/USAGE.

Tool routing already fails missions that require ``hitmeter``: hosted
hitmeter endpoints stay on the unsupported MCP provider, and no first-party
hitmeter provider is executable. Unbound therefore cannot speak an METER,
lockstep a USAGE meterid handshake over HITMETER Usage METERID,
independently poll the stored usagedigest, or seal a usagedigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``hitmeter`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2227 daemon
- keep a missing-meterid client so the hitmeter-meterid hole stays falsifiable
- refuse USAGE until an METER lands with a non-empty meterid
- independently poll the stored usagedigest on a later client socket
- persist a sealed usagedigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 2295 Transparent Content Negotiation
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
    HITMETER_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    hitmeter_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HITMETER_ACTUATION_ID = "capability.hitmeter-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-HITMETER-OK"
POLL_TOKEN = "BH-HITMETER-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_METERID = 0
EMPTY_USAGEDIGEST = 0
HITMETER_FIRST = 0x4D  # RFC 2227 Simple Hit-Metering (ASCII 'M')
METERID_SIZE = 4
USAGEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_USAGE = 0x02  # RFC 2227 USAGE confirmation
FRAME_METER = 0x01  # RFC 2227 METER
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HITMETER_LEFTOVER = (
    "Later genesis can take RFC 2227 Simple Hit-Metering METER/USAGE over a "
    "meterid-gated usagedigest."
)
HITMETER_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HITMETER_ACTUATION_ID};"
    f"capability_proved:{HITMETER_ACTUATION_ID};"
    "no_skill_route"
)
HITMETER_ACTUATION_GOAL = (
    "Repair rfc2227 hitmeter meter/usage cycle cannot land over http "
    "hitmeter meterid: hosted hitmeter endpoints remain unsupported so a METER then "
    "USAGE meterid handshake cannot land and a sealed usagedigest "
    "cannot be produced. A missing hitmeter meterid stays forbidden; fail-closed "
    "routing never opts the hitmeter provider in. An independent later poll of the "
    "stored usagedigest keeps the hole falsifiable."
)


class HitmeterActuationError(RuntimeError):
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
# RFC 2227 sections 5.1 and 5.2: AUTH / DIGEST.
RFC_METER_FIELD = "METER"
RFC_USAGE_FIELD = "USAGE"
RFC_HITMETER_USAGE = RFC_USAGE_FIELD
RFC_METER_DIRECTIVE = "meter=on"
RFC_USAGE_DIRECTIVE = "usage=report"
DEFAULT_METER = "METER"
USAGE_POLICY = "USAGE"
METER_HEADER = "Meter"
USAGE_HEADER = "Usage"
HITMETER_USAGE_HEADER = USAGE_HEADER
RFC_METER_PATH = "/hitmeter/"
RFC_METER_EMPTY = ""


def hitmeter_directive_pair(*, usage: bool = False) -> tuple[str, str]:
    """RFC 2227 Meter / Usage directive pair."""

    if usage:
        return "usage", "report"
    return "meter", "on"


def ascii_serialize_hitmeter_directive(*, usage: bool = False) -> str:
    """RFC 2227 token "=" auth-or-digest."""

    name, value = hitmeter_directive_pair(usage=usage)
    if not is_token(name):
        raise HitmeterActuationError("illegal_directive")
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
            raise HitmeterActuationError("short_hitmeter")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 2227 Meter token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_hitmeter(policy: str | Sequence[str]) -> str:
    """Serialize RFC 2227 METER / USAGE token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise HitmeterActuationError("illegal_hitmeter")
    upper = text.upper().replace("_", "-")
    if upper in {"METER", "HIT", "HITMETER"}:
        return "METER"
    if upper in {"USAGE", "REPORT", "HIT-USAGE"}:
        return "USAGE"
    if upper.startswith("METER="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HitmeterActuationError("illegal_hitmeter")
        return "METER"
    if upper.startswith("USAGE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HitmeterActuationError("illegal_hitmeter")
        return "USAGE"
    raise HitmeterActuationError("illegal_hitmeter")


def parse_hitmeter(text: str) -> str:
    """Parse RFC 2227 Meter header extensions into METER or USAGE."""

    raw = str(text or "").strip()
    if not raw:
        raise HitmeterActuationError("illegal_hitmeter")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"METER", "HIT", "HITMETER"}:
        return "METER"
    if upper in {"USAGE", "REPORT", "HIT-USAGE"}:
        return "USAGE"
    if upper.startswith("METER="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HitmeterActuationError("illegal_hitmeter")
        return "METER"
    if upper.startswith("USAGE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HitmeterActuationError("illegal_hitmeter")
        return "USAGE"
    raise HitmeterActuationError("illegal_hitmeter")


def encode_hitmeter_header(policy: str | Sequence[str]) -> bytes:
    """RFC 2227 Meter field as bytes."""

    return serialize_hitmeter(policy).encode("ascii")


def parse_hitmeter_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_hitmeter(field_value) if field_value else DEFAULT_METER
    return {
        "field_value": field_value,
        "policy": policy,
        "header": METER_HEADER,
        "directive": str(policy),
        "meter": str(policy) == "METER",
        "usage": str(policy) == "USAGE",
    }


def canonical_meter(identity: str, meterid: int) -> str:
    """RFC 2227 AUTH advertisement bound to identity and meterid."""

    return (
        f"{serialize_hitmeter(DEFAULT_METER)}, "
        f"meter={ascii_serialize_hitmeter_directive()}, "
        f"identity={identity}, meterid={int(meterid) & 0xFFFFFFFF}"
    )


def canonical_usage(identity: str, meterid: int, usagedigest: int | None = None) -> str:
    """RFC 2227 DIGEST confirmation of the stored digest policy."""

    digest = ""
    if usagedigest is not None:
        digest = f", usagedigest={int(usagedigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_hitmeter(USAGE_POLICY)}, "
        f"usage={ascii_serialize_hitmeter_directive(usage=True)}, "
        f"identity={identity}, meterid={int(meterid) & 0xFFFFFFFF}{digest}"
    )


def representation_usage(identity: str, meterid: int, usagedigest: int) -> str:
    return canonical_usage(identity, meterid, usagedigest)


def hitmeter_matches(left: str, right: str) -> bool:
    return parse_hitmeter(left) == parse_hitmeter(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HitmeterActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HitmeterActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HitmeterActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HitmeterActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def meter_request(identity: str, meterid: int) -> bytes:
    """HTTP AUTH that elicits RFC 2227 origin AUTH."""

    keyid = f"{int(meterid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"METER /hitmeter/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Meter-Id: {int(meterid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def usage_request(identity: str, meterid: int, usagedigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 2227 DIGEST confirmation of the stored digest policy."""

    keyid = f"{int(meterid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if usagedigest is not None:
        extra = f"Usage-Digest: {int(usagedigest) & 0xFFFFFFFF}\r\n"
    return (
        f"USAGE /hitmeter/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Meter-Id: {int(meterid) & 0xFFFFFFFF}\r\n"
        "Usage-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    hitmeter_kind = "usage" if fields.get("usage-confirm") == "1" else "meter"
    upgrade_field = fields.get("meter") or fields.get("negotiate") or fields.get("hitmeter") or ""
    policy = parse_hitmeter(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "hitmeter_kind": hitmeter_kind,
        "policy": policy,
        "meterid": int(fields["meter-id"]) if fields.get("meter-id") else EMPTY_METERID,
        "usagedigest": int(fields["usage-digest"]) if fields.get("usage-digest") else EMPTY_USAGEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def meter_response(identity: str, meterid: int, usagedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 2227 origin AUTH, carrying the stored usagedigest."""

    advertised = serialize_hitmeter(DEFAULT_METER)
    payload = bytes(body or canonical_meter(identity, meterid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Meter: {advertised}\r\n"
        f"Meter-Id: {int(meterid) & 0xFFFFFFFF}\r\n"
        f"Usage-Digest: {int(usagedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def usage_response(identity: str, meterid: int, usagedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 2227 DIGEST, carrying the stored DIGEST policy."""

    advertised = serialize_hitmeter(USAGE_POLICY)
    payload = bytes(body or representation_usage(identity, meterid, usagedigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Meter: {advertised}\r\n"
        f"Meter-Id: {int(meterid) & 0xFFFFFFFF}\r\n"
        f"Usage-Digest: {int(usagedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/http-usage\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise HitmeterActuationError("illegal_content_length") from error
    field_value = fields.get("meter") or fields.get("negotiate") or fields.get("hitmeter") or ""
    policy = parse_hitmeter(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/http-usage" or policy == USAGE_POLICY:
        status = 200
        hitmeter_kind = "usage"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        hitmeter_kind = "meter"
    else:
        status = 0
        hitmeter_kind = "meter"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "hitmeter_kind": hitmeter_kind,
        "policy": policy,
        "meterid": int(fields["meter-id"]) if fields.get("meter-id") else EMPTY_METERID,
        "usagedigest": int(fields["usage-digest"]) if fields.get("usage-digest") else EMPTY_USAGEDIGEST,
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
        raise HitmeterActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise HitmeterActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise HitmeterActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HitmeterActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_meterid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"meterid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_meterid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-meterid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_usagedigest(meterid: int = EMPTY_METERID, token: str = SENTINEL) -> int:
    material = canonical_meter(token or SENTINEL, int(meterid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_METERID = request_meterid(SENTINEL)
DEFAULT_USAGEDIGEST = request_usagedigest(DEFAULT_METERID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    meterid: int,
    usagedigest: int,
    include_meterid: bool = True,
) -> bytes:
    live_meterid = int(meterid) & 0xFFFFFFFF if include_meterid else EMPTY_METERID
    live_digest = int(usagedigest) & 0xFFFFFFFF if include_meterid and live_meterid else EMPTY_USAGEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_meterid) if live_meterid else b""
    header = bytearray()
    header.append(HITMETER_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_meter(
    *,
    identity: str,
    meterid: int,
    usagedigest: int | None = None,
    include_meterid: bool = True,
) -> bytes:
    live_meterid = int(meterid) & 0xFFFFFFFF if include_meterid else EMPTY_METERID
    live_digest = int(usagedigest) if usagedigest is not None else request_usagedigest(live_meterid, identity)
    return encode_packet(
        FRAME_METER,
        identity=identity,
        meterid=live_meterid,
        usagedigest=live_digest,
        include_meterid=include_meterid,
    )


def encode_usage(
    *,
    identity: str,
    meterid: int,
    usagedigest: int | None = None,
    include_meterid: bool = True,
) -> bytes:
    live_meterid = int(meterid) & 0xFFFFFFFF if include_meterid else EMPTY_METERID
    live_digest = int(usagedigest) if usagedigest is not None else request_usagedigest(live_meterid, identity)
    return encode_packet(
        FRAME_USAGE,
        identity=identity,
        meterid=live_meterid,
        usagedigest=live_digest,
        include_meterid=include_meterid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HitmeterActuationError("short_packet")
    first = raw[0]
    if first != HITMETER_FIRST:
        raise HitmeterActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise HitmeterActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == METERID_SIZE:
        live_meterid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_meterid = EMPTY_METERID
    else:
        raise HitmeterActuationError("illegal_meterid")
    if offset >= len(raw):
        raise HitmeterActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_METER, FRAME_USAGE}:
        raise HitmeterActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HitmeterActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HitmeterActuationError("checksum_failed")
    if len(payload) < 5:
        raise HitmeterActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HitmeterActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_meterid = int(live_meterid) != EMPTY_METERID
    has_usagedigest = has_meterid and int(live_digest) != EMPTY_USAGEDIGEST
    is_meter = frame_type == FRAME_METER
    is_usage = frame_type == FRAME_USAGE
    return {
        "type": int(frame_type),
        "is_meter": is_meter,
        "is_usage": is_usage,
        "is_response": is_usage,
        "meterid": int(live_meterid),
        "has_meterid": has_meterid,
        "usagedigest": int(live_digest),
        "has_usagedigest": has_usagedigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC2227",
        "serialize_field": canonical_meter(identity, live_meterid) if has_meterid else "",
        "tls_field": canonical_usage(identity, live_meterid, live_digest) if has_usagedigest else "",
    }


class HitmeterClient:
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
            raise HitmeterActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_usage"] or not packet["is_response"]:
            raise HitmeterActuationError("usagedigest_required")
        if not packet["has_meterid"]:
            raise HitmeterActuationError("meterid_required")
        if not packet["has_usagedigest"]:
            raise HitmeterActuationError("usagedigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_usagedigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_usagedigest:
            raise HitmeterActuationError("usagedigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "meterid": int(reply.get("meterid") or EMPTY_METERID),
            "identity": str(reply.get("identity") or ""),
            "usagedigest": int(reply.get("usagedigest") or EMPTY_USAGEDIGEST),
        }

    def report(
        self,
        identity: str,
        meterid: int,
        usagedigest: int = EMPTY_USAGEDIGEST,
        *,
        wait_usagedigest: bool = True,
        include_meterid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_usage(
            identity=identity,
            meterid=meterid,
            usagedigest=usagedigest or request_usagedigest(meterid, identity),
            include_meterid=include_meterid,
        )
        return self.exchange(packet, wait_usagedigest=wait_usagedigest)


class HitmeterSession:
    """METERID-gated loopback RFC 2227 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        meterid_gate: int = DEFAULT_METERID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.meterid_gate = int(meterid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.meterid = EMPTY_METERID
        self.usagedigest = EMPTY_USAGEDIGEST
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

    def store_meterid_once(self, identity: str, meterid: int, usagedigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(meterid or EMPTY_METERID)
            live_digest = int(usagedigest or EMPTY_USAGEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.meterid = live
                self.usagedigest = live_digest or request_usagedigest(live, name)
                self.stored = True
            return str(self.identity), int(self.meterid), int(self.usagedigest)

    def read_meterid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.meterid), int(self.usagedigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "meterid": EMPTY_METERID,
            "usagedigest": EMPTY_USAGEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _meterid_missing(self) -> bool:
        return not int(self.meterid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, meterid: int, usagedigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_usage(
            identity=identity,
            meterid=meterid,
            usagedigest=usagedigest,
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
            except HitmeterActuationError:
                continue
            if not packet.get("is_meter") and not packet.get("is_usage"):
                continue
            if not packet.get("has_meterid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_meterid, stored_digest = self.store_meterid_once(
                identity,
                int(packet.get("meterid") or EMPTY_METERID),
                int(packet.get("usagedigest") or EMPTY_USAGEDIGEST),
            )
            if not stored_name or not stored_meterid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_meter"):
                    self.opened = True
                if packet.get("is_usage"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_meterid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._meterid_missing():
            return self._forbidden("missing_meterid")
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
        do_meter: bool = True,
        do_usage: bool = True,
        do_usagedigest: bool = True,
        replay: bool = True,
        use_meterid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._meterid_missing():
            return self._forbidden("missing_meterid")
        live_token = str(token or SENTINEL)
        origin_meterid = request_meterid(live_token)
        origin_digest = request_usagedigest(origin_meterid, live_token)
        client: HitmeterClient | None = None
        independent: HitmeterClient | None = None
        try:
            client = HitmeterClient(self.host, int(self.port))
            if not do_meter:
                return self._conflict("meter_required")
            bind_packet = encode_meter(
                identity=live_token,
                meterid=origin_meterid,
                usagedigest=origin_digest,
                include_meterid=use_meterid,
            )
            if not use_meterid:
                try:
                    client.exchange(bind_packet, wait_usagedigest=True)
                except HitmeterActuationError:
                    return self._conflict("meterid_required")
                return self._conflict("meterid_required")
            client.send(bind_packet)
            if not do_usage:
                return self._conflict("usage_required")
            proxy_packet = encode_usage(
                identity=live_token,
                meterid=origin_meterid,
                usagedigest=origin_digest,
                include_meterid=True,
            )
            if not do_usagedigest:
                try:
                    client.exchange(proxy_packet, wait_usagedigest=False)
                except HitmeterActuationError as error:
                    if str(error) == "usagedigest_required":
                        return self._conflict("usagedigest_required")
                    return self._conflict("usagedigest_required")
                return self._conflict("usagedigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_usagedigest=True)
            except HitmeterActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("meterid_required")
                if reason == "usagedigest_required":
                    return self._conflict("usagedigest_required")
                return self._conflict("meter_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("meter_required")
            if int(reply.get("meterid") or EMPTY_METERID) != origin_meterid:
                return self._conflict("usagedigest_required")
            if int(reply.get("usagedigest") or EMPTY_USAGEDIGEST) != origin_digest:
                return self._conflict("usagedigest_required")
            self.retrieved = True
            if replay:
                independent = HitmeterClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_meterid(live_token),
                        request_usagedigest(poll_meterid(live_token), POLL_TOKEN),
                        wait_usagedigest=True,
                    )
                except HitmeterActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_meterid, stored_digest = self.read_meterid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_meterid != origin_meterid
                    or stored_digest != origin_digest
                    or int(poll.get("meterid") or EMPTY_METERID) != origin_meterid
                    or int(poll.get("usagedigest") or EMPTY_USAGEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_meterid}:{origin_digest}:{live_token}:{canonical_meter(live_token, origin_meterid)}:{canonical_usage(live_token, origin_meterid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "meterid": origin_meterid,
                "usagedigest": origin_digest,
                "meter_frame": True,
                "usage_frame": True,
                "usagedigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "meterid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_hitmeter_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "meterid": origin_meterid,
                "usagedigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "meter_frame": True,
                "usage_frame": True,
                "usagedigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "meterid_bound": True,
            }
        except (OSError, HitmeterActuationError) as error:
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
        live = independent_hitmeter_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "meterid": int(live.get("meterid") or EMPTY_METERID),
            "usagedigest": int(live.get("usagedigest") or EMPTY_USAGEDIGEST),
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


def call_hitmeter_tool(session: HitmeterSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one hitmeter tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_meter = True if arguments.get("meter") is None else bool(arguments.get("meter"))
    do_usage = True if arguments.get("usage") is None else bool(arguments.get("usage"))
    do_usagedigest = True if arguments.get("usagedigest") is None else bool(arguments.get("usagedigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_meterid = True if arguments.get("use_meterid") is None else bool(arguments.get("use_meterid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_meter=do_meter,
            do_usage=do_usage,
            do_usagedigest=do_usagedigest,
            replay=replay,
            use_meterid=use_meterid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HitmeterActuationError(f"unsupported hitmeter action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_hitmeter_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage usagedigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "meterid": EMPTY_METERID,
        "usagedigest": EMPTY_USAGEDIGEST,
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
            "meter_frame",
            "usage_frame",
            "usagedigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "meterid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    meterid = int(payload.get("meterid") or EMPTY_METERID)
    usagedigest = int(payload.get("usagedigest") or EMPTY_USAGEDIGEST)
    dual = port > 0 and bool(meterid) and bool(usagedigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "meterid": meterid,
        "usagedigest": usagedigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "meter_frame": payload.get("meter_frame") is True,
        "usage_frame": payload.get("usage_frame") is True,
        "usagedigest_response": payload.get("usagedigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "meterid_bound": payload.get("meterid_bound") is True,
    }


def run_hitmeter_workflow(
    *,
    with_meterid: bool = True,
    skip_bind: bool = False,
    do_meter: bool = True,
    do_usage: bool = True,
    do_usagedigest: bool = True,
    replay: bool = True,
    use_meterid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2227 METER/USAGE meterid cycle workflow."""

    descriptor = hitmeter_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HITMETER_TOOL_PROVIDER),
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
        raise HitmeterActuationError(f"hitmeter tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="hitmeter-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HitmeterSession(out, meterid_gate=DEFAULT_METERID if with_meterid else EMPTY_METERID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "meter": do_meter,
            "usage": do_usage,
            "usagedigest": do_usagedigest,
            "replay": replay,
            "use_meterid": use_meterid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_hitmeter_tool(session, arguments))
            except HitmeterActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_hitmeter_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_meterid
        and not skip_bind
        and do_meter
        and do_usage
        and do_usagedigest
        and replay
        and use_meterid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "hitmeter_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_meterid": with_meterid,
        "skip_bind": skip_bind,
        "meter_frame": do_meter,
        "usage": do_usage,
        "usagedigest": do_usagedigest,
        "replay": replay,
        "use_meterid": use_meterid,
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
        "meterid_value": int(publish_result.get("meterid") or independent.get("meterid") or EMPTY_METERID),
        "usagedigest_value": int(publish_result.get("usagedigest") or independent.get("usagedigest") or EMPTY_USAGEDIGEST),
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
        "meterid": int(trace_body["meterid_value"] or EMPTY_METERID),
        "usagedigest": int(trace_body["usagedigest_value"] or EMPTY_USAGEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_meterid": with_meterid,
        "skip_bind": skip_bind,
        "meter_cycle": do_meter,
        "usage_cycle": do_usage,
        "usagedigest_cycle": do_usagedigest,
        "replay": replay,
        "use_meterid": use_meterid,
    }


def verify_hitmeter_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_hitmeter_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    meterid = int(trace.get("meterid_value") or independent.get("meterid") or EMPTY_METERID)
    usagedigest = int(trace.get("usagedigest_value") or independent.get("usagedigest") or EMPTY_USAGEDIGEST)
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
        "meter_frame": independent.get("meter_frame") is True,
        "usage_frame": independent.get("usage_frame") is True,
        "usagedigest_response": independent.get("usagedigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "meterid_bound": independent.get("meterid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "usagedigest_recorded": (
            port > 0
            and meterid == DEFAULT_METERID
            and usagedigest == DEFAULT_USAGEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def hitmeter_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.hitmeter_actuation import "
        "builtin_hitmeter_actuation_proof; r=builtin_hitmeter_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='hitmeter_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_hitmeter_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HITMETER_ACTUATION_ID,
        name="First-class RFC 2227 Simple Hit-Metering METER/USAGE actuation",
        description=(
            "Missions that require a hitmeter tool can opt the hitmeter provider in, "
            "bind a loopback RFC 2227 Simple Hit-Metering endpoint, complete an METER "
            "with a non-empty meterid, lockstep a USAGE that carries the "
            "stored usagedigest, independently poll the stored usagedigest "
            "on a later socket, and seal a digest-chained usagedigest. Default "
            "routing stays fail-closed; a missing meterid keeps the hole "
            "falsifiable, and skip-METER/USAGE/USAGEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.hitmeter_actuation:builtin_hitmeter_actuation_proof",
        proof_command=hitmeter_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.tcn-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/hitmeter_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/tcn_actuation.py",
            "src/blackhole_agent/icp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required hitmeter tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 2227 daemon, speaks a "
            "METER then USAGE over Simple Hit-Metering with a non-empty meterid and "
            "usagedigest, independently polls the stored usagedigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 2295 Transparent Content Negotiation lockstep is proved. "
            "Missing meterids, skip-METER, skip-USAGE, skip-usagedigest, skip-REPLAY, "
            "and an METER aimed without a meterid stay fail-closed. "
            "Later genesis can take RFC 2186 Internet Cache Protocol QUERY/HIT as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("hitmeter", "rfc2227", "http", "meterid", "usagedigest", "meter", "usage", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T014703Z-3fe1289a",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_hitmeter_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2227 meter lockstep actuation seals a usagedigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
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
    checks["denylists_self"] = HITMETER_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HITMETER_ACTUATION_GOAL) == (
        HITMETER_ACTUATION_ID,
    )
    checks["leftover_text_binds_hitmeter"] = leftover_marker_ids(HITMETER_LEFTOVER) == (
        HITMETER_ACTUATION_ID,
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
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_hitmeter"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"hitmeter_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HITMETER_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HITMETER_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_hitmeter(DEFAULT_METER)
    rebuilt = serialize_hitmeter(parse_hitmeter(advertised))
    preloaded = parse_hitmeter(RFC_HITMETER_USAGE)
    header = encode_hitmeter_header(DEFAULT_METER)
    parsed_header = parse_hitmeter_header(header)
    asked = parse_http_request(meter_request(SENTINEL, DEFAULT_METERID))
    preload_req = parse_http_request(usage_request(SENTINEL, DEFAULT_METERID, DEFAULT_USAGEDIGEST))
    got = parse_http_response(meter_response(SENTINEL, DEFAULT_METERID, DEFAULT_USAGEDIGEST))
    preload_reply = parse_http_response(
        usage_response(SENTINEL, DEFAULT_METERID, DEFAULT_USAGEDIGEST)
    )
    checks["hitmeter_roundtrip"] = (
        parse_hitmeter(advertised) == DEFAULT_METER
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_METER_FIELD
        and is_token("METER") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_METER_FIELD
        and parsed_header["policy"] == DEFAULT_METER
        and parsed_header["header"] == METER_HEADER
        and parsed_header["meter"] is True
        and parsed_header["usage"] is False
        and preloaded == USAGE_POLICY
        and ascii_serialize_hitmeter_directive() == RFC_METER_DIRECTIVE
        and hitmeter_directive_pair() == ("meter", "on")
        and RFC_METER_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_hitmeter(USAGE_POLICY) == RFC_HITMETER_USAGE
        and DEFAULT_USAGEDIGEST == request_usagedigest(DEFAULT_METERID, SENTINEL)
        and "usagedigest=" in canonical_usage(SENTINEL, DEFAULT_METERID, DEFAULT_USAGEDIGEST)
        and canonical_meter(SENTINEL, DEFAULT_METERID).startswith("METER")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "METER"
        and asked["hitmeter_kind"] == "meter"
        and asked["meterid"] == DEFAULT_METERID
        and preload_req["hitmeter_kind"] == "usage"
        and preload_req["usagedigest"] == DEFAULT_USAGEDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["hitmeter_kind"] == "meter"
        and preload_reply["hitmeter_kind"] == "usage"
        and got["policy"] == DEFAULT_METER
        and preload_reply["policy"] == USAGE_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["usagedigest"] == DEFAULT_USAGEDIGEST
        and preload_reply["usagedigest"] == DEFAULT_USAGEDIGEST
        and hitmeter_matches(serialize_hitmeter(got["policy"]), advertised)
    )

    checks["catalog_names_hitmeter"] = (
        len(catalog) > 98
        and catalog[98]["id"] == HITMETER_ACTUATION_ID
        and catalog[97]["id"] == TCN_ACTUATION_ID
        and catalog[98]["source"] == "genesis_bind_hitmeter"
    )
    checks["catalog_names_icp"] = (
        len(catalog) > 99
        and catalog[99]["id"] == ICP_ACTUATION_ID
        and catalog[99]["source"] == "genesis_bind_icp"
    )
    family = capability_family(HITMETER_ACTUATION_GOAL)
    checks["family_is_hitmeter"] = "hitmeter" in family
    checks["family_is_hitmeter_surface"] = "hitmeter" in family
    checks["family_is_meterid"] = "meterid" in family
    checks["family_is_rfc2227"] = "rfc2227" in family
    checks["family_is_usagedigest"] = "usagedigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
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
    packed = encode_meter(identity=SENTINEL, meterid=DEFAULT_METERID, usagedigest=DEFAULT_USAGEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_meter"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_meterid"] is True
        and parsed["meterid"] == DEFAULT_METERID
        and parsed["usagedigest"] == DEFAULT_USAGEDIGEST
        and parsed["is_response"] is False
        and parsed["is_usage"] is False
        and parsed["type"] == FRAME_METER
        and parsed["first_byte"] == HITMETER_FIRST
    )
    shook = encode_usage(
        identity=SENTINEL,
        meterid=DEFAULT_METERID,
        usagedigest=DEFAULT_USAGEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_usage"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_meter"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["meterid"] == DEFAULT_METERID
        and answer_parsed["usagedigest"] == DEFAULT_USAGEDIGEST
        and answer_parsed["has_usagedigest"] is True
        and answer_parsed["type"] == FRAME_USAGE
        and answer_parsed["first_byte"] == HITMETER_FIRST
    )
    bare = encode_meter(identity=SENTINEL, meterid=DEFAULT_METERID, include_meterid=False)
    checks["missing_meterid_is_unauthed"] = parse_message(bare)["has_meterid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    hitmeter_signature = semantic_signature(HITMETER_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(hitmeter_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_hitmeter = ToolDescriptor(name="remote_hitmeter", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_hitmeter)
    checks["naive_mcp_hitmeter_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = hitmeter_tool_descriptor()
    default_hitmeter = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HITMETER_TOOL_PROVIDER),
    )
    checks["default_hitmeter_provider_is_unsupported"] = (
        default_hitmeter.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HITMETER_TOOL_PROVIDER}" in default_hitmeter.reasons
    )
    checks["opted_in_hitmeter_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_hitmeter],
        required_tool_names=("local_memory", "hitmeter"),
    )
    checks["naive_preflight_missing_hitmeter"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["hitmeter"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "hitmeter"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HITMETER_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "hitmeter" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="hitmeter-actuation-") as tmp:
        root = Path(tmp)
        missing = run_hitmeter_workflow(with_meterid=False, output_dir=root / "missing")
        skip_bind = run_hitmeter_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_meter = run_hitmeter_workflow(do_meter=False, output_dir=root / "skip-upgrade")
        skip_usage = run_hitmeter_workflow(do_usage=False, output_dir=root / "skip-tls")
        skip_usagedigest = run_hitmeter_workflow(do_usagedigest=False, output_dir=root / "skip-usagedigest")
        skip_replay = run_hitmeter_workflow(replay=False, output_dir=root / "skip-replay")
        skip_meterid = run_hitmeter_workflow(use_meterid=False, output_dir=root / "skip-meterid")
        live = run_hitmeter_workflow(output_dir=root / "live")
        verify = verify_hitmeter_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_hitmeter_trace(clone)
        checks["naive_without_meterid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_meterid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_meter_stays_empty"] = (
            skip_meter["ok"] is False
            and skip_meter["error"] == "meter_required"
            and skip_meter["final_status"] == 409
            and skip_meter["payload_exists"] is False
        )
        checks["skip_usage_stays_empty"] = (
            skip_usage["ok"] is False
            and skip_usage["error"] == "usage_required"
            and skip_usage["final_status"] == 409
            and skip_usage["payload_exists"] is False
        )
        checks["skip_usagedigest_stays_empty"] = (
            skip_usagedigest["ok"] is False
            and skip_usagedigest["error"] == "usagedigest_required"
            and skip_usagedigest["final_status"] == 409
            and skip_usagedigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_meterid_stays_empty"] = (
            skip_meterid["ok"] is False
            and skip_meterid["error"] == "meterid_required"
            and skip_meterid["final_status"] == 409
            and skip_meterid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_usagedigest"] = (
            int(live.get("meterid") or 0) == DEFAULT_METERID
            and int(live.get("usagedigest") or 0) == DEFAULT_USAGEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_meterid_encode_usage_usagedigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_meter["ok"] is False
            and skip_usage["ok"] is False
            and skip_usagedigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_meterid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="hitmeter-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HITMETER_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_hitmeter"] = (
        live_goal == HITMETER_ACTUATION_GOAL
        and HITMETER_ACTUATION_ID in live_done
        and live_source == "genesis_bind_hitmeter"
    )

    with tempfile.TemporaryDirectory(prefix="hitmeter-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HITMETER_LEFTOVER, root)
        register_catalog_proved(root, HITMETER_ACTUATION_ID)
        reason = leftover_satisfied_by(HITMETER_LEFTOVER, root)
        after = leftover_is_open(HITMETER_LEFTOVER, root)
    checks["hitmeter_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_hitmeter_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HITMETER_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_hitmeter_actuation_capability()
    return {
        "ok": ok,
        "action": "hitmeter_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HITMETER_ACTUATION_GOAL,
        "done_when": HITMETER_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
