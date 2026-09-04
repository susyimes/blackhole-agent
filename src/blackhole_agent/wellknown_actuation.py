"""Drive a first-class Defining Well-Known Uniform Resource Identifiers tool through RFC 5785 DISCOVERY/SUFFIX.

Tool routing already fails missions that require ``wellknown``: hosted
wellknown endpoints stay on the unsupported MCP provider, and no first-party
wellknown provider is executable. Unbound therefore cannot speak a DISCOVERY,
lockstep a SUFFIX suffixid handshake over HTTP Well-Known SUFFIXID,
independently poll the stored suffixdigest, or seal a suffixdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``wellknown`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 5785 daemon
- keep a missing-suffixid client so the wellknown-suffixid hole stays falsifiable
- refuse SUFFIX until a DISCOVERY lands with a non-empty suffixid
- independently poll the stored suffixdigest on a later client socket
- persist a sealed suffixdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 5789 PATCH Method for HTTP
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
    WELLKNOWN_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    wellknown_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
WELLKNOWN_ACTUATION_ID = "capability.wellknown-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-WK-OK"
POLL_TOKEN = "BH-WK-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_SUFFIXID = 0
EMPTY_SUFFIXDIGEST = 0
WK_FIRST = 0x57  # RFC 5785 Defining Well-Known Uniform Resource Identifiers (ASCII 'W')
SUFFIXID_SIZE = 4
SUFFIXDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_SUFFIX = 0x02  # RFC 5785 suffix confirmation
FRAME_DISCOVERY = 0x01  # RFC 5785 DISCOVERY
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
WELLKNOWN_LEFTOVER = (
    "Later genesis can take RFC 5785 Defining Well-Known Uniform Resource Identifiers DISCOVERY/SUFFIX over a "
    "suffixid-gated suffixdigest."
)
WELLKNOWN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WELLKNOWN_ACTUATION_ID};"
    f"capability_proved:{WELLKNOWN_ACTUATION_ID};"
    "no_skill_route"
)
WELLKNOWN_ACTUATION_GOAL = (
    "Repair rfc5785 wellknown discovery/suffix cycle cannot land over http "
    "wellknown suffixid: hosted wellknown endpoints remain unsupported so a DISCOVERY then "
    "SUFFIX suffixid handshake cannot land and a sealed suffixdigest "
    "cannot be produced. A missing wellknown suffixid stays forbidden; fail-closed "
    "routing never opts the wellknown provider in. An independent later poll of the "
    "stored suffixdigest keeps the hole falsifiable."
)


class WellknownActuationError(RuntimeError):
    """Raised when the suffix session or loopback daemon fixture misbehaves."""


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
# RFC 5785 sections 3 and 4: prefix / uri-suffix.
RFC_DISCOVERY_FIELD = "DISCOVERY"
RFC_SUFFIX_FIELD = "SUFFIX"
RFC_WELLKNOWN_SUFFIX = RFC_SUFFIX_FIELD
RFC_DISCOVERY_DIRECTIVE = "prefix=.well-known"
RFC_SUFFIX_DIRECTIVE = "uri-suffix=host-meta"
DEFAULT_DISCOVERY = "DISCOVERY"
SUFFIX_POLICY = "SUFFIX"
DISCOVERY_HEADER = "Well-Known"
SUFFIX_HEADER = "Well-Known"
WELLKNOWN_SUFFIX_HEADER = SUFFIX_HEADER
RFC_DISCOVERY_PATH = "/.well-known/"
RFC_DISCOVERY_EMPTY = ""


def wellknown_directive_pair(*, suffix: bool = False) -> tuple[str, str]:
    """RFC 5785 section 3 well-known-uri prefix / registered uri-suffix."""

    if suffix:
        return "uri-suffix", "host-meta"
    return "prefix", ".well-known"


def ascii_serialize_wellknown_directive(*, suffix: bool = False) -> str:
    """RFC 5785 well-known-uri: token "=" suffix-or-prefix."""

    name, value = wellknown_directive_pair(suffix=suffix)
    if not is_token(name):
        raise WellknownActuationError("illegal_directive")
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
            raise WellknownActuationError("short_wellknown")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 5785 Well-Known token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_wellknown(policy: str | Sequence[str]) -> str:
    """Serialize RFC 5785 prefix / uri-suffix token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise WellknownActuationError("illegal_wellknown")
    upper = text.upper().replace("_", "-")
    if upper in {"DISCOVERY", "PREFIX", "WK"}:
        return "DISCOVERY"
    if upper in {"SUFFIX", "URI-SUFFIX", "HM"}:
        return "SUFFIX"
    if upper.startswith("PREFIX="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise WellknownActuationError("illegal_wellknown")
        return "DISCOVERY"
    if upper.startswith("URI-SUFFIX="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise WellknownActuationError("illegal_wellknown")
        return "SUFFIX"
    raise WellknownActuationError("illegal_wellknown")


def parse_wellknown(text: str) -> str:
    """Parse RFC 5785 Well-Known discovery extensions into DISCOVERY or SUFFIX."""

    raw = str(text or "").strip()
    if not raw:
        raise WellknownActuationError("illegal_wellknown")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"DISCOVERY", "PREFIX", "WK"}:
        return "DISCOVERY"
    if upper in {"SUFFIX", "URI-SUFFIX", "HM"}:
        return "SUFFIX"
    if upper.startswith("PREFIX="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise WellknownActuationError("illegal_wellknown")
        return "DISCOVERY"
    if upper.startswith("URI-SUFFIX="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise WellknownActuationError("illegal_wellknown")
        return "SUFFIX"
    raise WellknownActuationError("illegal_wellknown")


def encode_wellknown_header(policy: str | Sequence[str]) -> bytes:
    """RFC 5785 Well-Known field as bytes."""

    return serialize_wellknown(policy).encode("ascii")


def parse_wellknown_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_wellknown(field_value) if field_value else DEFAULT_DISCOVERY
    return {
        "field_value": field_value,
        "policy": policy,
        "header": DISCOVERY_HEADER,
        "directive": str(policy),
        "discovery": str(policy) == "DISCOVERY",
        "suffix": str(policy) == "SUFFIX",
    }


def canonical_discovery(identity: str, suffixid: int) -> str:
    """RFC 5785 DISCOVERY advertisement bound to identity and suffixid."""

    return (
        f"{serialize_wellknown(DEFAULT_DISCOVERY)}, "
        f"discovery={ascii_serialize_wellknown_directive()}, "
        f"identity={identity}, suffixid={int(suffixid) & 0xFFFFFFFF}"
    )


def canonical_suffix(identity: str, suffixid: int, suffixdigest: int | None = None) -> str:
    """RFC 5785 SUFFIX confirmation of the stored suffix policy."""

    suffix = ""
    if suffixdigest is not None:
        suffix = f", suffixdigest={int(suffixdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_wellknown(SUFFIX_POLICY)}, "
        f"suffix={ascii_serialize_wellknown_directive(suffix=True)}, "
        f"identity={identity}, suffixid={int(suffixid) & 0xFFFFFFFF}{suffix}"
    )


def representation_suffix(identity: str, suffixid: int, suffixdigest: int) -> str:
    return canonical_suffix(identity, suffixid, suffixdigest)


def wellknown_matches(left: str, right: str) -> bool:
    return parse_wellknown(left) == parse_wellknown(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise WellknownActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise WellknownActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise WellknownActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise WellknownActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def discovery_request(identity: str, suffixid: int) -> bytes:
    """HTTP DISCOVERY that elicits RFC 5785 origin DISCOVERY."""

    keyid = f"{int(suffixid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"DISCOVERY /.well-known/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Suffix-Id: {int(suffixid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def suffix_request(identity: str, suffixid: int, suffixdigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 5785 SUFFIX confirmation of the stored suffix policy."""

    keyid = f"{int(suffixid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if suffixdigest is not None:
        extra = f"Suffix-Digest: {int(suffixdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /.well-known/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Suffix-Id: {int(suffixid) & 0xFFFFFFFF}\r\n"
        "Suffix-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    wellknown_kind = "suffix" if fields.get("suffix-confirm") == "1" else "discovery"
    discovery_field = fields.get("well-known") or ""
    policy = parse_wellknown(discovery_field) if discovery_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "wellknown_kind": wellknown_kind,
        "policy": policy,
        "suffixid": int(fields["suffix-id"]) if fields.get("suffix-id") else EMPTY_SUFFIXID,
        "suffixdigest": int(fields["suffix-digest"]) if fields.get("suffix-digest") else EMPTY_SUFFIXDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def discovery_response(identity: str, suffixid: int, suffixdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 5785 origin DISCOVERY, carrying the stored suffixdigest."""

    advertised = serialize_wellknown(DEFAULT_DISCOVERY)
    payload = bytes(body or canonical_discovery(identity, suffixid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Well-Known: {advertised}\r\n"
        f"Suffix-Id: {int(suffixid) & 0xFFFFFFFF}\r\n"
        f"Suffix-Digest: {int(suffixdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def suffix_response(identity: str, suffixid: int, suffixdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 5785 SUFFIX, carrying the stored SUFFIX policy."""

    advertised = serialize_wellknown(SUFFIX_POLICY)
    payload = bytes(body or representation_suffix(identity, suffixid, suffixdigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Well-Known: {advertised}\r\n"
        f"Suffix-Id: {int(suffixid) & 0xFFFFFFFF}\r\n"
        f"Suffix-Digest: {int(suffixdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/resource+json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise WellknownActuationError("illegal_content_length") from error
    field_value = fields.get("well-known") or ""
    policy = parse_wellknown(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/resource+json" or policy == SUFFIX_POLICY:
        status = 200
        wellknown_kind = "suffix"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        wellknown_kind = "discovery"
    else:
        status = 0
        wellknown_kind = "discovery"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "wellknown_kind": wellknown_kind,
        "policy": policy,
        "suffixid": int(fields["suffix-id"]) if fields.get("suffix-id") else EMPTY_SUFFIXID,
        "suffixdigest": int(fields["suffix-digest"]) if fields.get("suffix-digest") else EMPTY_SUFFIXDIGEST,
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
        raise WellknownActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise WellknownActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise WellknownActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise WellknownActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_suffixid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"suffixid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_suffixid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-suffixid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_suffixdigest(suffixid: int = EMPTY_SUFFIXID, token: str = SENTINEL) -> int:
    material = canonical_discovery(token or SENTINEL, int(suffixid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_SUFFIXID = request_suffixid(SENTINEL)
DEFAULT_SUFFIXDIGEST = request_suffixdigest(DEFAULT_SUFFIXID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    suffixid: int,
    suffixdigest: int,
    include_suffixid: bool = True,
) -> bytes:
    live_suffixid = int(suffixid) & 0xFFFFFFFF if include_suffixid else EMPTY_SUFFIXID
    live_digest = int(suffixdigest) & 0xFFFFFFFF if include_suffixid and live_suffixid else EMPTY_SUFFIXDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_suffixid) if live_suffixid else b""
    header = bytearray()
    header.append(WK_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_discovery(
    *,
    identity: str,
    suffixid: int,
    suffixdigest: int | None = None,
    include_suffixid: bool = True,
) -> bytes:
    live_suffixid = int(suffixid) & 0xFFFFFFFF if include_suffixid else EMPTY_SUFFIXID
    live_digest = int(suffixdigest) if suffixdigest is not None else request_suffixdigest(live_suffixid, identity)
    return encode_packet(
        FRAME_DISCOVERY,
        identity=identity,
        suffixid=live_suffixid,
        suffixdigest=live_digest,
        include_suffixid=include_suffixid,
    )


def encode_suffix(
    *,
    identity: str,
    suffixid: int,
    suffixdigest: int | None = None,
    include_suffixid: bool = True,
) -> bytes:
    live_suffixid = int(suffixid) & 0xFFFFFFFF if include_suffixid else EMPTY_SUFFIXID
    live_digest = int(suffixdigest) if suffixdigest is not None else request_suffixdigest(live_suffixid, identity)
    return encode_packet(
        FRAME_SUFFIX,
        identity=identity,
        suffixid=live_suffixid,
        suffixdigest=live_digest,
        include_suffixid=include_suffixid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise WellknownActuationError("short_packet")
    first = raw[0]
    if first != WK_FIRST:
        raise WellknownActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise WellknownActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == SUFFIXID_SIZE:
        live_suffixid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_suffixid = EMPTY_SUFFIXID
    else:
        raise WellknownActuationError("illegal_suffixid")
    if offset >= len(raw):
        raise WellknownActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_DISCOVERY, FRAME_SUFFIX}:
        raise WellknownActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise WellknownActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise WellknownActuationError("checksum_failed")
    if len(payload) < 5:
        raise WellknownActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise WellknownActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_suffixid = int(live_suffixid) != EMPTY_SUFFIXID
    has_suffixdigest = has_suffixid and int(live_digest) != EMPTY_SUFFIXDIGEST
    is_discovery = frame_type == FRAME_DISCOVERY
    is_suffix = frame_type == FRAME_SUFFIX
    return {
        "type": int(frame_type),
        "is_discovery": is_discovery,
        "is_suffix": is_suffix,
        "is_response": is_suffix,
        "suffixid": int(live_suffixid),
        "has_suffixid": has_suffixid,
        "suffixdigest": int(live_digest),
        "has_suffixdigest": has_suffixdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http_state": "RFC5785",
        "serialize_field": canonical_discovery(identity, live_suffixid) if has_suffixid else "",
        "suffix_field": canonical_suffix(identity, live_suffixid, live_digest) if has_suffixdigest else "",
    }


class WellknownClient:
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
            raise WellknownActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_suffix"] or not packet["is_response"]:
            raise WellknownActuationError("suffixdigest_required")
        if not packet["has_suffixid"]:
            raise WellknownActuationError("suffixid_required")
        if not packet["has_suffixdigest"]:
            raise WellknownActuationError("suffixdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_suffixdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_suffixdigest:
            raise WellknownActuationError("suffixdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "suffixid": int(reply.get("suffixid") or EMPTY_SUFFIXID),
            "identity": str(reply.get("identity") or ""),
            "suffixdigest": int(reply.get("suffixdigest") or EMPTY_SUFFIXDIGEST),
        }

    def report(
        self,
        identity: str,
        suffixid: int,
        suffixdigest: int = EMPTY_SUFFIXDIGEST,
        *,
        wait_suffixdigest: bool = True,
        include_suffixid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_suffix(
            identity=identity,
            suffixid=suffixid,
            suffixdigest=suffixdigest or request_suffixdigest(suffixid, identity),
            include_suffixid=include_suffixid,
        )
        return self.exchange(packet, wait_suffixdigest=wait_suffixdigest)


class WellknownSession:
    """SUFFIXID-gated loopback RFC 5785 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        suffixid_gate: int = DEFAULT_SUFFIXID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.suffixid_gate = int(suffixid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.suffixid = EMPTY_SUFFIXID
        self.suffixdigest = EMPTY_SUFFIXDIGEST
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

    def store_suffixid_once(self, identity: str, suffixid: int, suffixdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(suffixid or EMPTY_SUFFIXID)
            live_digest = int(suffixdigest or EMPTY_SUFFIXDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.suffixid = live
                self.suffixdigest = live_digest or request_suffixdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.suffixid), int(self.suffixdigest)

    def read_suffixid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.suffixid), int(self.suffixdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "suffixid": EMPTY_SUFFIXID,
            "suffixdigest": EMPTY_SUFFIXDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _suffixid_missing(self) -> bool:
        return not int(self.suffixid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, suffixid: int, suffixdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_suffix(
            identity=identity,
            suffixid=suffixid,
            suffixdigest=suffixdigest,
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
            except WellknownActuationError:
                continue
            if not packet.get("is_discovery") and not packet.get("is_suffix"):
                continue
            if not packet.get("has_suffixid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_suffixid, stored_digest = self.store_suffixid_once(
                identity,
                int(packet.get("suffixid") or EMPTY_SUFFIXID),
                int(packet.get("suffixdigest") or EMPTY_SUFFIXDIGEST),
            )
            if not stored_name or not stored_suffixid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_discovery"):
                    self.opened = True
                if packet.get("is_suffix"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_suffixid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._suffixid_missing():
            return self._forbidden("missing_suffixid")
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
        do_discovery: bool = True,
        do_suffix: bool = True,
        do_suffixdigest: bool = True,
        replay: bool = True,
        use_suffixid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._suffixid_missing():
            return self._forbidden("missing_suffixid")
        live_token = str(token or SENTINEL)
        origin_suffixid = request_suffixid(live_token)
        origin_digest = request_suffixdigest(origin_suffixid, live_token)
        client: WellknownClient | None = None
        independent: WellknownClient | None = None
        try:
            client = WellknownClient(self.host, int(self.port))
            if not do_discovery:
                return self._conflict("discovery_required")
            bind_packet = encode_discovery(
                identity=live_token,
                suffixid=origin_suffixid,
                suffixdigest=origin_digest,
                include_suffixid=use_suffixid,
            )
            if not use_suffixid:
                try:
                    client.exchange(bind_packet, wait_suffixdigest=True)
                except WellknownActuationError:
                    return self._conflict("suffixid_required")
                return self._conflict("suffixid_required")
            client.send(bind_packet)
            if not do_suffix:
                return self._conflict("suffix_required")
            proxy_packet = encode_suffix(
                identity=live_token,
                suffixid=origin_suffixid,
                suffixdigest=origin_digest,
                include_suffixid=True,
            )
            if not do_suffixdigest:
                try:
                    client.exchange(proxy_packet, wait_suffixdigest=False)
                except WellknownActuationError as error:
                    if str(error) == "suffixdigest_required":
                        return self._conflict("suffixdigest_required")
                    return self._conflict("suffixdigest_required")
                return self._conflict("suffixdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_suffixdigest=True)
            except WellknownActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("suffixid_required")
                if reason == "suffixdigest_required":
                    return self._conflict("suffixdigest_required")
                return self._conflict("discovery_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("discovery_required")
            if int(reply.get("suffixid") or EMPTY_SUFFIXID) != origin_suffixid:
                return self._conflict("suffixdigest_required")
            if int(reply.get("suffixdigest") or EMPTY_SUFFIXDIGEST) != origin_digest:
                return self._conflict("suffixdigest_required")
            self.retrieved = True
            if replay:
                independent = WellknownClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_suffixid(live_token),
                        request_suffixdigest(poll_suffixid(live_token), POLL_TOKEN),
                        wait_suffixdigest=True,
                    )
                except WellknownActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_suffixid, stored_digest = self.read_suffixid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_suffixid != origin_suffixid
                    or stored_digest != origin_digest
                    or int(poll.get("suffixid") or EMPTY_SUFFIXID) != origin_suffixid
                    or int(poll.get("suffixdigest") or EMPTY_SUFFIXDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_suffixid}:{origin_digest}:{live_token}:{canonical_discovery(live_token, origin_suffixid)}:{canonical_suffix(live_token, origin_suffixid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "suffixid": origin_suffixid,
                "suffixdigest": origin_digest,
                "discovery_frame": True,
                "suffix_frame": True,
                "suffixdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "suffixid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_wellknown_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "suffixid": origin_suffixid,
                "suffixdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "discovery_frame": True,
                "suffix_frame": True,
                "suffixdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "suffixid_bound": True,
            }
        except (OSError, WellknownActuationError) as error:
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
        live = independent_wellknown_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "suffixid": int(live.get("suffixid") or EMPTY_SUFFIXID),
            "suffixdigest": int(live.get("suffixdigest") or EMPTY_SUFFIXDIGEST),
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


def call_wellknown_tool(session: WellknownSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Disdiscovery one discovery tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_discovery = True if arguments.get("discovery") is None else bool(arguments.get("discovery"))
    do_suffix = True if arguments.get("suffix") is None else bool(arguments.get("suffix"))
    do_suffixdigest = True if arguments.get("suffixdigest") is None else bool(arguments.get("suffixdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_suffixid = True if arguments.get("use_suffixid") is None else bool(arguments.get("use_suffixid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_discovery=do_discovery,
            do_suffix=do_suffix,
            do_suffixdigest=do_suffixdigest,
            replay=replay,
            use_suffixid=use_suffixid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise WellknownActuationError(f"unsupported wellknown action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_wellknown_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed discovery suffixdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "suffixid": EMPTY_SUFFIXID,
        "suffixdigest": EMPTY_SUFFIXDIGEST,
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
            "discovery_frame",
            "suffix_frame",
            "suffixdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "suffixid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    suffixid = int(payload.get("suffixid") or EMPTY_SUFFIXID)
    suffixdigest = int(payload.get("suffixdigest") or EMPTY_SUFFIXDIGEST)
    dual = port > 0 and bool(suffixid) and bool(suffixdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "suffixid": suffixid,
        "suffixdigest": suffixdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "discovery_frame": payload.get("discovery_frame") is True,
        "suffix_frame": payload.get("suffix_frame") is True,
        "suffixdigest_response": payload.get("suffixdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "suffixid_bound": payload.get("suffixid_bound") is True,
    }


def run_wellknown_workflow(
    *,
    with_suffixid: bool = True,
    skip_bind: bool = False,
    do_discovery: bool = True,
    do_suffix: bool = True,
    do_suffixdigest: bool = True,
    replay: bool = True,
    use_suffixid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 5785 DISCOVERY/SUFFIX suffixid cycle workflow."""

    descriptor = wellknown_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WELLKNOWN_TOOL_PROVIDER),
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
        raise WellknownActuationError(f"wellknown tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="wellknown-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = WellknownSession(out, suffixid_gate=DEFAULT_SUFFIXID if with_suffixid else EMPTY_SUFFIXID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "discovery": do_discovery,
            "suffix": do_suffix,
            "suffixdigest": do_suffixdigest,
            "replay": replay,
            "use_suffixid": use_suffixid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_wellknown_tool(session, arguments))
            except WellknownActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_wellknown_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_suffixid
        and not skip_bind
        and do_discovery
        and do_suffix
        and do_suffixdigest
        and replay
        and use_suffixid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "wellknown_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_suffixid": with_suffixid,
        "skip_bind": skip_bind,
        "discovery_frame": do_discovery,
        "suffix": do_suffix,
        "suffixdigest": do_suffixdigest,
        "replay": replay,
        "use_suffixid": use_suffixid,
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
        "suffixid_value": int(publish_result.get("suffixid") or independent.get("suffixid") or EMPTY_SUFFIXID),
        "suffixdigest_value": int(publish_result.get("suffixdigest") or independent.get("suffixdigest") or EMPTY_SUFFIXDIGEST),
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
        "suffixid": int(trace_body["suffixid_value"] or EMPTY_SUFFIXID),
        "suffixdigest": int(trace_body["suffixdigest_value"] or EMPTY_SUFFIXDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_suffixid": with_suffixid,
        "skip_bind": skip_bind,
        "discovery_cycle": do_discovery,
        "suffix_cycle": do_suffix,
        "suffixdigest_cycle": do_suffixdigest,
        "replay": replay,
        "use_suffixid": use_suffixid,
    }


def verify_wellknown_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_wellknown_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    suffixid = int(trace.get("suffixid_value") or independent.get("suffixid") or EMPTY_SUFFIXID)
    suffixdigest = int(trace.get("suffixdigest_value") or independent.get("suffixdigest") or EMPTY_SUFFIXDIGEST)
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
        "discovery_frame": independent.get("discovery_frame") is True,
        "suffix_frame": independent.get("suffix_frame") is True,
        "suffixdigest_response": independent.get("suffixdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "suffixid_bound": independent.get("suffixid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "suffixdigest_recorded": (
            port > 0
            and suffixid == DEFAULT_SUFFIXID
            and suffixdigest == DEFAULT_SUFFIXDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def wellknown_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.wellknown_actuation import "
        "builtin_wellknown_actuation_proof; r=builtin_wellknown_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='wellknown_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_wellknown_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=WELLKNOWN_ACTUATION_ID,
        name="First-class RFC 5785 Defining Well-Known Uniform Resource Identifiers DISCOVERY/SUFFIX actuation",
        description=(
            "Missions that require a wellknown tool can opt the wellknown provider in, "
            "bind a loopback RFC 5785 Defining Well-Known Uniform Resource Identifiers endpoint, complete a DISCOVERY "
            "with a non-empty suffixid, lockstep an SUFFIX that carries the "
            "stored suffixdigest, independently poll the stored suffixdigest "
            "on a later socket, and seal a digest-chained suffixdigest. Default "
            "routing stays fail-closed; a missing suffixid keeps the hole "
            "falsifiable, and skip-DISCOVERY/SUFFIX/SUFFIXDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.wellknown_actuation:builtin_wellknown_actuation_proof",
        proof_command=wellknown_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.httppatch-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/wellknown_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/httppatch_actuation.py",
            "src/blackhole_agent/webdav_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required wellknown tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 5785 daemon, speaks a "
            "DISCOVERY then SUFFIX over Defining Well-Known Uniform Resource Identifiers with a non-empty suffixid and "
            "suffixdigest, independently polls the stored suffixdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 5789 PATCH Method for HTTP lockstep is proved. "
            "Missing suffixids, skip-DISCOVERY, skip-SUFFIX, skip-suffixdigest, skip-REPLAY, "
            "and a DISCOVERY aimed without a suffixid stay fail-closed. "
            "Later genesis can take RFC 4918 HTTP Extensions for WebDAV PROPFIND/LOCK as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("wellknown", "rfc5785", "http", "suffixid", "suffixdigest", "discovery", "suffix", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T221543Z-6922c11c",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_wellknown_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 5785 discovery lockstep actuation seals a suffixdigest."""

    from blackhole_agent.httppatch_actuation import (
        HTTPPATCH_ACTUATION_GOAL,
        HTTPPATCH_ACTUATION_ID,
    )
    from blackhole_agent.webdav_actuation import (
        WEBDAV_ACTUATION_GOAL,
        WEBDAV_ACTUATION_ID,
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
    checks["denylists_self"] = WELLKNOWN_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(WELLKNOWN_ACTUATION_GOAL) == (
        WELLKNOWN_ACTUATION_ID,
    )
    checks["leftover_text_binds_wellknown"] = leftover_marker_ids(WELLKNOWN_LEFTOVER) == (
        WELLKNOWN_ACTUATION_ID,
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
        (HTTPPATCH_ACTUATION_GOAL, HTTPPATCH_ACTUATION_ID, "httppatch"),
        (WEBDAV_ACTUATION_GOAL, WEBDAV_ACTUATION_ID, "webdav"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_wellknown"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"wellknown_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            WELLKNOWN_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = WELLKNOWN_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_wellknown(DEFAULT_DISCOVERY)
    rebuilt = serialize_wellknown(parse_wellknown(advertised))
    preloaded = parse_wellknown(RFC_WELLKNOWN_SUFFIX)
    header = encode_wellknown_header(DEFAULT_DISCOVERY)
    parsed_header = parse_wellknown_header(header)
    asked = parse_http_request(discovery_request(SENTINEL, DEFAULT_SUFFIXID))
    preload_req = parse_http_request(suffix_request(SENTINEL, DEFAULT_SUFFIXID, DEFAULT_SUFFIXDIGEST))
    got = parse_http_response(discovery_response(SENTINEL, DEFAULT_SUFFIXID, DEFAULT_SUFFIXDIGEST))
    preload_reply = parse_http_response(
        suffix_response(SENTINEL, DEFAULT_SUFFIXID, DEFAULT_SUFFIXDIGEST)
    )
    checks["wellknown_roundtrip"] = (
        parse_wellknown(advertised) == DEFAULT_DISCOVERY
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_DISCOVERY_FIELD
        and is_token("DISCOVERY") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_DISCOVERY_FIELD
        and parsed_header["policy"] == DEFAULT_DISCOVERY
        and parsed_header["header"] == DISCOVERY_HEADER
        and parsed_header["discovery"] is True
        and parsed_header["suffix"] is False
        and preloaded == SUFFIX_POLICY
        and ascii_serialize_wellknown_directive() == RFC_DISCOVERY_DIRECTIVE
        and wellknown_directive_pair() == ("prefix", ".well-known")
        and RFC_DISCOVERY_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_wellknown(SUFFIX_POLICY) == RFC_WELLKNOWN_SUFFIX
        and DEFAULT_SUFFIXDIGEST == request_suffixdigest(DEFAULT_SUFFIXID, SENTINEL)
        and "suffixdigest=" in canonical_suffix(SENTINEL, DEFAULT_SUFFIXID, DEFAULT_SUFFIXDIGEST)
        and canonical_discovery(SENTINEL, DEFAULT_SUFFIXID).startswith("DISCOVERY")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "DISCOVERY"
        and asked["wellknown_kind"] == "discovery"
        and asked["suffixid"] == DEFAULT_SUFFIXID
        and preload_req["wellknown_kind"] == "suffix"
        and preload_req["suffixdigest"] == DEFAULT_SUFFIXDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["wellknown_kind"] == "discovery"
        and preload_reply["wellknown_kind"] == "suffix"
        and got["policy"] == DEFAULT_DISCOVERY
        and preload_reply["policy"] == SUFFIX_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["suffixdigest"] == DEFAULT_SUFFIXDIGEST
        and preload_reply["suffixdigest"] == DEFAULT_SUFFIXDIGEST
        and wellknown_matches(serialize_wellknown(got["policy"]), advertised)
    )

    checks["catalog_names_wellknown"] = (
        len(catalog) > 92
        and catalog[92]["id"] == WELLKNOWN_ACTUATION_ID
        and catalog[91]["id"] == HTTPPATCH_ACTUATION_ID
        and catalog[92]["source"] == "genesis_bind_wellknown"
    )
    checks["catalog_names_webdav"] = (
        len(catalog) > 93
        and catalog[93]["id"] == WEBDAV_ACTUATION_ID
        and catalog[93]["source"] == "genesis_bind_webdav"
    )
    family = capability_family(WELLKNOWN_ACTUATION_GOAL)
    checks["family_is_wellknown"] = "wellknown" in family
    checks["family_is_wellknown_surface"] = "wellknown" in family
    checks["family_is_suffixid"] = "suffixid" in family
    checks["family_is_rfc5785"] = "rfc5785" in family
    checks["family_is_suffixdigest"] = "suffixdigest" in family
    checks["family_is_not_httppatch"] = (
        "httppatch" not in family
        and "rfc5789" not in family
        and "patchid" not in family
        and "patchdigest" not in family
    )
    checks["family_is_not_webdav"] = (
        "webdav" not in family
        and "rfc4918" not in family
        and "lockid" not in family
        and "lockdigest" not in family
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
    packed = encode_discovery(identity=SENTINEL, suffixid=DEFAULT_SUFFIXID, suffixdigest=DEFAULT_SUFFIXDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_discovery"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_suffixid"] is True
        and parsed["suffixid"] == DEFAULT_SUFFIXID
        and parsed["suffixdigest"] == DEFAULT_SUFFIXDIGEST
        and parsed["is_response"] is False
        and parsed["is_suffix"] is False
        and parsed["type"] == FRAME_DISCOVERY
        and parsed["first_byte"] == WK_FIRST
    )
    shook = encode_suffix(
        identity=SENTINEL,
        suffixid=DEFAULT_SUFFIXID,
        suffixdigest=DEFAULT_SUFFIXDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_suffix"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_discovery"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["suffixid"] == DEFAULT_SUFFIXID
        and answer_parsed["suffixdigest"] == DEFAULT_SUFFIXDIGEST
        and answer_parsed["has_suffixdigest"] is True
        and answer_parsed["type"] == FRAME_SUFFIX
        and answer_parsed["first_byte"] == WK_FIRST
    )
    bare = encode_discovery(identity=SENTINEL, suffixid=DEFAULT_SUFFIXID, include_suffixid=False)
    checks["missing_suffixid_is_unauthenticated"] = parse_message(bare)["has_suffixid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    wellknown_signature = semantic_signature(WELLKNOWN_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(wellknown_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_wellknown = ToolDescriptor(name="remote_wellknown", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_wellknown)
    checks["naive_mcp_wellknown_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = wellknown_tool_descriptor()
    default_wellknown = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WELLKNOWN_TOOL_PROVIDER),
    )
    checks["default_wellknown_provider_is_unsupported"] = (
        default_wellknown.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{WELLKNOWN_TOOL_PROVIDER}" in default_wellknown.reasons
    )
    checks["opted_in_wellknown_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_wellknown],
        required_tool_names=("local_memory", "wellknown"),
    )
    checks["naive_preflight_missing_wellknown"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["wellknown"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "wellknown"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WELLKNOWN_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "wellknown" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="wellknown-actuation-") as tmp:
        root = Path(tmp)
        missing = run_wellknown_workflow(with_suffixid=False, output_dir=root / "missing")
        skip_bind = run_wellknown_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_discovery = run_wellknown_workflow(do_discovery=False, output_dir=root / "skip-discovery")
        skip_suffix = run_wellknown_workflow(do_suffix=False, output_dir=root / "skip-suffix")
        skip_suffixdigest = run_wellknown_workflow(do_suffixdigest=False, output_dir=root / "skip-suffixdigest")
        skip_replay = run_wellknown_workflow(replay=False, output_dir=root / "skip-replay")
        skip_suffixid = run_wellknown_workflow(use_suffixid=False, output_dir=root / "skip-suffixid")
        live = run_wellknown_workflow(output_dir=root / "live")
        verify = verify_wellknown_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_wellknown_trace(clone)
        checks["naive_without_suffixid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_suffixid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_discovery_stays_empty"] = (
            skip_discovery["ok"] is False
            and skip_discovery["error"] == "discovery_required"
            and skip_discovery["final_status"] == 409
            and skip_discovery["payload_exists"] is False
        )
        checks["skip_suffix_stays_empty"] = (
            skip_suffix["ok"] is False
            and skip_suffix["error"] == "suffix_required"
            and skip_suffix["final_status"] == 409
            and skip_suffix["payload_exists"] is False
        )
        checks["skip_suffixdigest_stays_empty"] = (
            skip_suffixdigest["ok"] is False
            and skip_suffixdigest["error"] == "suffixdigest_required"
            and skip_suffixdigest["final_status"] == 409
            and skip_suffixdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_suffixid_stays_empty"] = (
            skip_suffixid["ok"] is False
            and skip_suffixid["error"] == "suffixid_required"
            and skip_suffixid["final_status"] == 409
            and skip_suffixid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_suffixdigest"] = (
            int(live.get("suffixid") or 0) == DEFAULT_SUFFIXID
            and int(live.get("suffixdigest") or 0) == DEFAULT_SUFFIXDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_suffixid_encode_suffix_suffixdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_discovery["ok"] is False
            and skip_suffix["ok"] is False
            and skip_suffixdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_suffixid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="wellknown-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != WELLKNOWN_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_wellknown"] = (
        live_goal == WELLKNOWN_ACTUATION_GOAL
        and WELLKNOWN_ACTUATION_ID in live_done
        and live_source == "genesis_bind_wellknown"
    )

    with tempfile.TemporaryDirectory(prefix="wellknown-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(WELLKNOWN_LEFTOVER, root)
        register_catalog_proved(root, WELLKNOWN_ACTUATION_ID)
        reason = leftover_satisfied_by(WELLKNOWN_LEFTOVER, root)
        after = leftover_is_open(WELLKNOWN_LEFTOVER, root)
    checks["wellknown_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_wellknown_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{WELLKNOWN_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_wellknown_actuation_capability()
    return {
        "ok": ok,
        "action": "wellknown_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": WELLKNOWN_ACTUATION_GOAL,
        "done_when": WELLKNOWN_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
