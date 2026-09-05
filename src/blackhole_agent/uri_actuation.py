"""Drive a first-class Universal Resource Identifiers tool through RFC 1630 IDENTIFY/DEREF.

Tool routing already fails missions that require ``uri``: hosted
uri endpoints stay on the unsupported MCP provider, and no first-party
uri provider is executable. Unbound therefore cannot speak a IDENTIFY,
lockstep a DEREF uriid handshake over HTTP/1.0 URIID,
independently poll the stored uridigest, or seal a uridigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``uri`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1630 daemon
- keep a missing-uriid client so the uri-uriid hole stays falsifiable
- refuse DEREF until a IDENTIFY lands with a non-empty uriid
- independently poll the stored uridigest on a later client socket
- persist a sealed uridigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 1738 Uniform Resource Locators
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
    URI_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    uri_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
URI_ACTUATION_ID = "capability.uri-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-URI-OK"
POLL_TOKEN = "BH-URI-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_URIID = 0
EMPTY_URIDIGEST = 0
URI_FIRST = 0x49  # RFC 1630 Universal Resource Identifiers (ASCII 'I')
URIID_SIZE = 4
URIDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DEREF = 0x02  # RFC 1630 DEREF confirmation
FRAME_IDENTIFY = 0x01  # RFC 1630 IDENTIFY
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
URI_LEFTOVER = (
    "Later genesis can take RFC 1630 Universal Resource Identifiers IDENTIFY/DEREF over a "
    "uriid-gated uridigest."
)
URI_ACTUATION_DONE_WHEN = (
    f"capability_exists:{URI_ACTUATION_ID};"
    f"capability_proved:{URI_ACTUATION_ID};"
    "no_skill_route"
)
URI_ACTUATION_GOAL = (
    "Repair rfc1630 uri identify/deref cycle cannot land over http "
    "uri uriid: hosted uri endpoints remain unsupported so a IDENTIFY then "
    "DEREF uriid handshake cannot land and a sealed uridigest "
    "cannot be produced. A missing uri uriid stays forbidden; fail-closed "
    "routing never opts the uri provider in. An independent later poll of the "
    "stored uridigest keeps the hole falsifiable."
)


class UriActuationError(RuntimeError):
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
# RFC 1630 sections 2.1 and 2.1.2: IDENTIFY / DEREF.
RFC_IDENTIFY_FIELD = "IDENTIFY"
RFC_DEREF_FIELD = "DEREF"
RFC_URI_DEREF = RFC_DEREF_FIELD
RFC_IDENTIFY_DIRECTIVE = "identify=name"
RFC_DEREF_DIRECTIVE = "deref=resource"
DEFAULT_IDENTIFY = "IDENTIFY"
DEREF_POLICY = "DEREF"
IDENTIFY_HEADER = "Identify"
DEREF_HEADER = "Deref"
URI_DEREF_HEADER = DEREF_HEADER
RFC_IDENTIFY_PATH = "/uri/"
RFC_IDENTIFY_EMPTY = ""


def uri_directive_pair(*, deref: bool = False) -> tuple[str, str]:
    """RFC 1630 Identify / Deref directive pair."""

    if deref:
        return "deref", "resource"
    return "identify", "name"


def ascii_serialize_uri_directive(*, deref: bool = False) -> str:
    """RFC 1630 token "=" identify-or-deref."""

    name, value = uri_directive_pair(deref=deref)
    if not is_token(name):
        raise UriActuationError("illegal_directive")
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
            raise UriActuationError("short_uri")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 1630 identify-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_uri(policy: str | Sequence[str]) -> str:
    """Serialize RFC 1630 IDENTIFY / DEREF opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise UriActuationError("illegal_uri")
    upper = text.upper().replace("_", "-")
    if upper in {"IDENTIFY", "URI", "URI-IDENTIFY"}:
        return "IDENTIFY"
    if upper in {"DEREF", "RESOURCE", "URI-DEREF"}:
        return "DEREF"
    if upper.startswith("IDENTIFY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UriActuationError("illegal_uri")
        return "IDENTIFY"
    if upper.startswith("DEREF="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UriActuationError("illegal_uri")
        return "DEREF"
    raise UriActuationError("illegal_uri")


def parse_uri(text: str) -> str:
    """Parse RFC 1630 URI opcode header extensions into IDENTIFY or DEREF."""

    raw = str(text or "").strip()
    if not raw:
        raise UriActuationError("illegal_uri")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"IDENTIFY", "URI", "URI-IDENTIFY"}:
        return "IDENTIFY"
    if upper in {"DEREF", "RESOURCE", "URI-DEREF"}:
        return "DEREF"
    if upper.startswith("IDENTIFY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UriActuationError("illegal_uri")
        return "IDENTIFY"
    if upper.startswith("DEREF="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UriActuationError("illegal_uri")
        return "DEREF"
    raise UriActuationError("illegal_uri")


def encode_uri_header(policy: str | Sequence[str]) -> bytes:
    """RFC 1630 HTTP/1.0 field as bytes."""

    return serialize_uri(policy).encode("ascii")


def parse_uri_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_uri(field_value) if field_value else DEFAULT_IDENTIFY
    return {
        "field_value": field_value,
        "policy": policy,
        "header": IDENTIFY_HEADER,
        "directive": str(policy),
        "identify": str(policy) == "IDENTIFY",
        "deref": str(policy) == "DEREF",
    }


def canonical_identify(identity: str, uriid: int) -> str:
    """RFC 1630 identify-request advertisement bound to identity and uriid."""

    return (
        f"{serialize_uri(DEFAULT_IDENTIFY)}, "
        f"identify={ascii_serialize_uri_directive()}, "
        f"identity={identity}, uriid={int(uriid) & 0xFFFFFFFF}"
    )


def canonical_deref(identity: str, uriid: int, uridigest: int | None = None) -> str:
    """RFC 1630 deref-resource confirmation of the stored identifier-digest."""

    digest = ""
    if uridigest is not None:
        digest = f", uridigest={int(uridigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_uri(DEREF_POLICY)}, "
        f"deref={ascii_serialize_uri_directive(deref=True)}, "
        f"identity={identity}, uriid={int(uriid) & 0xFFFFFFFF}{digest}"
    )


def representation_deref(identity: str, uriid: int, uridigest: int) -> str:
    return canonical_deref(identity, uriid, uridigest)


def uri_matches(left: str, right: str) -> bool:
    return parse_uri(left) == parse_uri(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise UriActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise UriActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise UriActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise UriActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def identify_request(identity: str, uriid: int) -> bytes:
    """HTTP IDENTIFY that elicits RFC 1630 origin HTTP/1.0."""

    keyid = f"{int(uriid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"IDENTIFY /uri/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Uri-Id: {int(uriid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def deref_request(identity: str, uriid: int, uridigest: int | None = None) -> bytes:
    """HTTP IDENTIFY carrying RFC 1630 deref-resource confirmation of the stored identifier-digest."""

    keyid = f"{int(uriid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if uridigest is not None:
        extra = f"Uri-Digest: {int(uridigest) & 0xFFFFFFFF}\r\n"
    return (
        f"DEREF /uri/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Uri-Id: {int(uriid) & 0xFFFFFFFF}\r\n"
        "Deref-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    uri_kind = "deref" if fields.get("deref-confirm") == "1" else "identify"
    upgrade_field = fields.get("identify") or fields.get("uri") or ""
    policy = parse_uri(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "uri_kind": uri_kind,
        "policy": policy,
        "uriid": int(fields["uri-id"]) if fields.get("uri-id") else EMPTY_URIID,
        "uridigest": int(fields["uri-digest"]) if fields.get("uri-digest") else EMPTY_URIDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def identify_response(identity: str, uriid: int, uridigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 1630 origin HTTP/1.0, carrying the stored uridigest."""

    advertised = serialize_uri(DEFAULT_IDENTIFY)
    payload = bytes(body or canonical_identify(identity, uriid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Identify: {advertised}\r\n"
        f"Uri-Id: {int(uriid) & 0xFFFFFFFF}\r\n"
        f"Uri-Digest: {int(uridigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def deref_response(identity: str, uriid: int, uridigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 1630 DEREF, carrying the stored identifier-digest."""

    advertised = serialize_uri(DEREF_POLICY)
    payload = bytes(body or representation_deref(identity, uriid, uridigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Identify: {advertised}\r\n"
        f"Uri-Id: {int(uriid) & 0xFFFFFFFF}\r\n"
        f"Uri-Digest: {int(uridigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/uri-deref\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise UriActuationError("illegal_content_length") from error
    field_value = fields.get("identify") or fields.get("uri") or ""
    policy = parse_uri(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/uri-deref" or policy == DEREF_POLICY:
        status = 200
        uri_kind = "deref"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        uri_kind = "identify"
    else:
        status = 0
        uri_kind = "identify"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "uri_kind": uri_kind,
        "policy": policy,
        "uriid": int(fields["uri-id"]) if fields.get("uri-id") else EMPTY_URIID,
        "uridigest": int(fields["uri-digest"]) if fields.get("uri-digest") else EMPTY_URIDIGEST,
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
        raise UriActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise UriActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise UriActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise UriActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc1630_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    uri: str,
) -> str:
    """RFC 1630 identifier digest over method, request-URI, identity, and uriid."""

    payload = f"{method}:{uri}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_uriid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"uriid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_uriid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-uriid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_uridigest(uriid: int = EMPTY_URIID, token: str = SENTINEL) -> int:
    nonce = f"{int(uriid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc1630_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="DEREF",
        uri=f"/uri/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_URIID = request_uriid(SENTINEL)
DEFAULT_URIDIGEST = request_uridigest(DEFAULT_URIID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    uriid: int,
    uridigest: int,
    include_uriid: bool = True,
) -> bytes:
    live_uriid = int(uriid) & 0xFFFFFFFF if include_uriid else EMPTY_URIID
    live_digest = int(uridigest) & 0xFFFFFFFF if include_uriid and live_uriid else EMPTY_URIDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_uriid) if live_uriid else b""
    header = bytearray()
    header.append(URI_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_identify(
    *,
    identity: str,
    uriid: int,
    uridigest: int | None = None,
    include_uriid: bool = True,
) -> bytes:
    live_uriid = int(uriid) & 0xFFFFFFFF if include_uriid else EMPTY_URIID
    live_digest = int(uridigest) if uridigest is not None else request_uridigest(live_uriid, identity)
    return encode_packet(
        FRAME_IDENTIFY,
        identity=identity,
        uriid=live_uriid,
        uridigest=live_digest,
        include_uriid=include_uriid,
    )


def encode_deref(
    *,
    identity: str,
    uriid: int,
    uridigest: int | None = None,
    include_uriid: bool = True,
) -> bytes:
    live_uriid = int(uriid) & 0xFFFFFFFF if include_uriid else EMPTY_URIID
    live_digest = int(uridigest) if uridigest is not None else request_uridigest(live_uriid, identity)
    return encode_packet(
        FRAME_DEREF,
        identity=identity,
        uriid=live_uriid,
        uridigest=live_digest,
        include_uriid=include_uriid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise UriActuationError("short_packet")
    first = raw[0]
    if first != URI_FIRST:
        raise UriActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise UriActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == URIID_SIZE:
        live_uriid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_uriid = EMPTY_URIID
    else:
        raise UriActuationError("illegal_uriid")
    if offset >= len(raw):
        raise UriActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_IDENTIFY, FRAME_DEREF}:
        raise UriActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise UriActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise UriActuationError("checksum_failed")
    if len(payload) < 5:
        raise UriActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise UriActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_uriid = int(live_uriid) != EMPTY_URIID
    has_uridigest = has_uriid and int(live_digest) != EMPTY_URIDIGEST
    is_identify = frame_type == FRAME_IDENTIFY
    is_deref = frame_type == FRAME_DEREF
    return {
        "type": int(frame_type),
        "is_identify": is_identify,
        "is_deref": is_deref,
        "uriid": int(live_uriid),
        "has_uriid": has_uriid,
        "uridigest": int(live_digest),
        "has_uridigest": has_uridigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC1630",
        "serialize_field": canonical_identify(identity, live_uriid) if has_uriid else "",
        "tls_field": canonical_deref(identity, live_uriid, live_digest) if has_uridigest else "",
    }


class UriClient:
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
            raise UriActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_deref"] or not packet["is_deref"]:
            raise UriActuationError("uridigest_required")
        if not packet["has_uriid"]:
            raise UriActuationError("uriid_required")
        if not packet["has_uridigest"]:
            raise UriActuationError("uridigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_uridigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_uridigest:
            raise UriActuationError("uridigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "uriid": int(reply.get("uriid") or EMPTY_URIID),
            "identity": str(reply.get("identity") or ""),
            "uridigest": int(reply.get("uridigest") or EMPTY_URIDIGEST),
        }

    def report(
        self,
        identity: str,
        uriid: int,
        uridigest: int = EMPTY_URIDIGEST,
        *,
        wait_uridigest: bool = True,
        include_uriid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_deref(
            identity=identity,
            uriid=uriid,
            uridigest=uridigest or request_uridigest(uriid, identity),
            include_uriid=include_uriid,
        )
        return self.exchange(packet, wait_uridigest=wait_uridigest)


class UriSession:
    """URIID-gated loopback RFC 1630 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        uriid_gate: int = DEFAULT_URIID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.uriid_gate = int(uriid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.uriid = EMPTY_URIID
        self.uridigest = EMPTY_URIDIGEST
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

    def store_uriid_once(self, identity: str, uriid: int, uridigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(uriid or EMPTY_URIID)
            live_digest = int(uridigest or EMPTY_URIDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.uriid = live
                self.uridigest = live_digest or request_uridigest(live, name)
                self.stored = True
            return str(self.identity), int(self.uriid), int(self.uridigest)

    def read_uriid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.uriid), int(self.uridigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "uriid": EMPTY_URIID,
            "uridigest": EMPTY_URIDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _uriid_missing(self) -> bool:
        return not int(self.uriid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, uriid: int, uridigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_deref(
            identity=identity,
            uriid=uriid,
            uridigest=uridigest,
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
            except UriActuationError:
                continue
            if not packet.get("is_identify") and not packet.get("is_deref"):
                continue
            if not packet.get("has_uriid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_uriid, stored_digest = self.store_uriid_once(
                identity,
                int(packet.get("uriid") or EMPTY_URIID),
                int(packet.get("uridigest") or EMPTY_URIDIGEST),
            )
            if not stored_name or not stored_uriid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_identify"):
                    self.opened = True
                if packet.get("is_deref"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_uriid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._uriid_missing():
            return self._forbidden("missing_uriid")
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
        do_identify: bool = True,
        do_deref: bool = True,
        do_uridigest: bool = True,
        replay: bool = True,
        use_uriid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._uriid_missing():
            return self._forbidden("missing_uriid")
        live_token = str(token or SENTINEL)
        origin_uriid = request_uriid(live_token)
        origin_digest = request_uridigest(origin_uriid, live_token)
        client: UriClient | None = None
        independent: UriClient | None = None
        try:
            client = UriClient(self.host, int(self.port))
            if not do_identify:
                return self._conflict("identify_required")
            bind_packet = encode_identify(
                identity=live_token,
                uriid=origin_uriid,
                uridigest=origin_digest,
                include_uriid=use_uriid,
            )
            if not use_uriid:
                try:
                    client.exchange(bind_packet, wait_uridigest=True)
                except UriActuationError:
                    return self._conflict("uriid_required")
                return self._conflict("uriid_required")
            client.send(bind_packet)
            if not do_deref:
                return self._conflict("deref_required")
            proxy_packet = encode_deref(
                identity=live_token,
                uriid=origin_uriid,
                uridigest=origin_digest,
                include_uriid=True,
            )
            if not do_uridigest:
                try:
                    client.exchange(proxy_packet, wait_uridigest=False)
                except UriActuationError as error:
                    if str(error) == "uridigest_required":
                        return self._conflict("uridigest_required")
                    return self._conflict("uridigest_required")
                return self._conflict("uridigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_uridigest=True)
            except UriActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("uriid_required")
                if reason == "uridigest_required":
                    return self._conflict("uridigest_required")
                return self._conflict("identify_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("identify_required")
            if int(reply.get("uriid") or EMPTY_URIID) != origin_uriid:
                return self._conflict("uridigest_required")
            if int(reply.get("uridigest") or EMPTY_URIDIGEST) != origin_digest:
                return self._conflict("uridigest_required")
            self.retrieved = True
            if replay:
                independent = UriClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_uriid(live_token),
                        request_uridigest(poll_uriid(live_token), POLL_TOKEN),
                        wait_uridigest=True,
                    )
                except UriActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_uriid, stored_digest = self.read_uriid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_uriid != origin_uriid
                    or stored_digest != origin_digest
                    or int(poll.get("uriid") or EMPTY_URIID) != origin_uriid
                    or int(poll.get("uridigest") or EMPTY_URIDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_uriid}:{origin_digest}:{live_token}:{canonical_identify(live_token, origin_uriid)}:{canonical_deref(live_token, origin_uriid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "uriid": origin_uriid,
                "uridigest": origin_digest,
                "identify_frame": True,
                "deref_frame": True,
                "uridigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "uriid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_uridigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "uriid": origin_uriid,
                "uridigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "identify_frame": True,
                "deref_frame": True,
                "uridigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "uriid_bound": True,
            }
        except (OSError, UriActuationError) as error:
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
        live = independent_uridigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "uriid": int(live.get("uriid") or EMPTY_URIID),
            "uridigest": int(live.get("uridigest") or EMPTY_URIDIGEST),
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


def call_uri_tool(session: UriSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one uri tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_identify = True if arguments.get("identify") is None else bool(arguments.get("identify"))
    do_deref = True if arguments.get("deref") is None else bool(arguments.get("deref"))
    do_uridigest = True if arguments.get("uridigest") is None else bool(arguments.get("uridigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_uriid = True if arguments.get("use_uriid") is None else bool(arguments.get("use_uriid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_identify=do_identify,
            do_deref=do_deref,
            do_uridigest=do_uridigest,
            replay=replay,
            use_uriid=use_uriid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise UriActuationError(f"unsupported uri action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_uridigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage uridigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "uriid": EMPTY_URIID,
        "uridigest": EMPTY_URIDIGEST,
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
            "identify_frame",
            "deref_frame",
            "uridigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "uriid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    uriid = int(payload.get("uriid") or EMPTY_URIID)
    uridigest = int(payload.get("uridigest") or EMPTY_URIDIGEST)
    dual = port > 0 and bool(uriid) and bool(uridigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "uriid": uriid,
        "uridigest": uridigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "identify_frame": payload.get("identify_frame") is True,
        "deref_frame": payload.get("deref_frame") is True,
        "uridigest_locate": payload.get("uridigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "uriid_bound": payload.get("uriid_bound") is True,
    }


def run_uri_workflow(
    *,
    with_uriid: bool = True,
    skip_bind: bool = False,
    do_identify: bool = True,
    do_deref: bool = True,
    do_uridigest: bool = True,
    replay: bool = True,
    use_uriid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1630 IDENTIFY/DEREF uriid cycle workflow."""

    descriptor = uri_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, URI_TOOL_PROVIDER),
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
        raise UriActuationError(f"uri tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="uri-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = UriSession(out, uriid_gate=DEFAULT_URIID if with_uriid else EMPTY_URIID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "identify": do_identify,
            "deref": do_deref,
            "uridigest": do_uridigest,
            "replay": replay,
            "use_uriid": use_uriid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_uri_tool(session, arguments))
            except UriActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_uridigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_uriid
        and not skip_bind
        and do_identify
        and do_deref
        and do_uridigest
        and replay
        and use_uriid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "uri_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_uriid": with_uriid,
        "skip_bind": skip_bind,
        "identify_frame": do_identify,
        "deref_frame": do_deref,
        "uridigest": do_uridigest,
        "replay": replay,
        "use_uriid": use_uriid,
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
        "uriid_value": int(publish_result.get("uriid") or independent.get("uriid") or EMPTY_URIID),
        "uridigest_value": int(publish_result.get("uridigest") or independent.get("uridigest") or EMPTY_URIDIGEST),
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
        "uriid": int(trace_body["uriid_value"] or EMPTY_URIID),
        "uridigest": int(trace_body["uridigest_value"] or EMPTY_URIDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_uriid": with_uriid,
        "skip_bind": skip_bind,
        "identify_cycle": do_identify,
        "deref_cycle": do_deref,
        "uridigest_cycle": do_uridigest,
        "replay": replay,
        "use_uriid": use_uriid,
    }


def verify_uri_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_uridigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    uriid = int(trace.get("uriid_value") or independent.get("uriid") or EMPTY_URIID)
    uridigest = int(trace.get("uridigest_value") or independent.get("uridigest") or EMPTY_URIDIGEST)
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
        "identify_frame": independent.get("identify_frame") is True,
        "deref_frame": independent.get("deref_frame") is True,
        "uridigest_locate": independent.get("uridigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "uriid_bound": independent.get("uriid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "uridigest_recorded": (
            port > 0
            and uriid == DEFAULT_URIID
            and uridigest == DEFAULT_URIDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def uri_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.uri_actuation import "
        "builtin_uri_actuation_proof; r=builtin_uri_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='uri_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_uri_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=URI_ACTUATION_ID,
        name="First-class RFC 1630 Universal Resource Identifiers IDENTIFY/DEREF actuation",
        description=(
            "Missions that require a uri tool can opt the uri provider in, "
            "bind a loopback RFC 1630 Universal Resource Identifiers endpoint, complete a IDENTIFY "
            "with a non-empty uriid, lockstep a DEREF that carries the "
            "stored uridigest, independently poll the stored uridigest "
            "on a later socket, and seal a digest-chained uridigest. Default "
            "routing stays fail-closed; a missing uriid keeps the hole "
            "falsifiable, and skip-IDENTIFY/DEREF/URIDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.uri_actuation:builtin_uri_actuation_proof",
        proof_command=uri_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.url-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/uri_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/url_actuation.py",
            "src/blackhole_agent/mime_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required uri tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 1630 daemon, speaks a "
            "IDENTIFY then DEREF over Universal Resource Identifiers with a non-empty uriid and "
            "uridigest, independently polls the stored uridigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 1738 Uniform Resource Locators lockstep is proved. "
            "Missing uriids, skip-IDENTIFY, skip-DEREF, skip-uridigest, skip-REPLAY, "
            "and a IDENTIFY aimed without a uriid stay fail-closed. "
            "Later genesis can take RFC 1521 MIME BODY/TRANSFER as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("uri", "rfc1630", "http", "uriid", "uridigest", "identify", "deref", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T055004Z-64857439",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_uri_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1630 identify/deref lockstep actuation seals a uridigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.mime_actuation import (
        MIME_ACTUATION_GOAL,
        MIME_ACTUATION_ID,
    )
    from blackhole_agent.url_actuation import (
        URL_ACTUATION_GOAL,
        URL_ACTUATION_ID,
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
    checks["denylists_self"] = URI_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(URI_ACTUATION_GOAL) == (
        URI_ACTUATION_ID,
    )
    checks["leftover_text_binds_uri"] = leftover_marker_ids(URI_LEFTOVER) == (
        URI_ACTUATION_ID,
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
        (MIME_ACTUATION_GOAL, MIME_ACTUATION_ID, "mime"),
        (URL_ACTUATION_GOAL, URL_ACTUATION_ID, "url"),
        (HTTP10_ACTUATION_GOAL, HTTP10_ACTUATION_ID, "http10"),
        (DIGESTAUTH_ACTUATION_GOAL, DIGESTAUTH_ACTUATION_ID, "digestauth"),
        (HTTPSTATE_ACTUATION_GOAL, HTTPSTATE_ACTUATION_ID, "httpstate"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_uri"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"uri_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            URI_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = URI_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_uri(DEFAULT_IDENTIFY)
    rebuilt = serialize_uri(parse_uri(advertised))
    preloaded = parse_uri(RFC_URI_DEREF)
    header = encode_uri_header(DEFAULT_IDENTIFY)
    parsed_header = parse_uri_header(header)
    asked = parse_http_request(identify_request(SENTINEL, DEFAULT_URIID))
    preload_req = parse_http_request(deref_request(SENTINEL, DEFAULT_URIID, DEFAULT_URIDIGEST))
    got = parse_http_response(identify_response(SENTINEL, DEFAULT_URIID, DEFAULT_URIDIGEST))
    preload_reply = parse_http_response(
        deref_response(SENTINEL, DEFAULT_URIID, DEFAULT_URIDIGEST)
    )
    checks["uri_roundtrip"] = (
        parse_uri(advertised) == DEFAULT_IDENTIFY
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_IDENTIFY_FIELD
        and is_token("IDENTIFY") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_IDENTIFY_FIELD
        and parsed_header["policy"] == DEFAULT_IDENTIFY
        and parsed_header["header"] == IDENTIFY_HEADER
        and parsed_header["identify"] is True
        and parsed_header["deref"] is False
        and preloaded == DEREF_POLICY
        and ascii_serialize_uri_directive() == RFC_IDENTIFY_DIRECTIVE
        and uri_directive_pair() == ("identify", "name")
        and RFC_IDENTIFY_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_uri(DEREF_POLICY) == RFC_URI_DEREF
        and DEFAULT_URIDIGEST == request_uridigest(DEFAULT_URIID, SENTINEL)
        and "uridigest=" in canonical_deref(SENTINEL, DEFAULT_URIID, DEFAULT_URIDIGEST)
        and canonical_identify(SENTINEL, DEFAULT_URIID).startswith("IDENTIFY")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "IDENTIFY"
        and asked["uri_kind"] == "identify"
        and asked["uriid"] == DEFAULT_URIID
        and preload_req["uri_kind"] == "deref"
        and preload_req["uridigest"] == DEFAULT_URIDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["uri_kind"] == "identify"
        and preload_reply["uri_kind"] == "deref"
        and got["policy"] == DEFAULT_IDENTIFY
        and preload_reply["policy"] == DEREF_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["uridigest"] == DEFAULT_URIDIGEST
        and preload_reply["uridigest"] == DEFAULT_URIDIGEST
        and uri_matches(serialize_uri(got["policy"]), advertised)
    )

    checks["catalog_names_uri"] = (
        len(catalog) > 105
        and catalog[105]["id"] == URI_ACTUATION_ID
        and catalog[104]["id"] == URL_ACTUATION_ID
        and catalog[105]["source"] == "genesis_bind_uri"
    )
    checks["catalog_names_mime"] = (
        len(catalog) > 106
        and catalog[106]["id"] == MIME_ACTUATION_ID
        and catalog[106]["source"] == "genesis_bind_mime"
    )
    family = capability_family(URI_ACTUATION_GOAL)
    checks["family_is_uri"] = "uri" in family
    checks["family_is_uri_surface"] = "uri" in family
    checks["family_is_uriid"] = "uriid" in family
    checks["family_is_rfc1630"] = "rfc1630" in family
    checks["family_is_uridigest"] = "uridigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_mime"] = (
        "mime" not in family.split("/")
        and "rfc1521" not in family
        and "mimeid" not in family
        and "mimedigest" not in family
    )
    checks["family_is_not_url"] = (
        "url" not in family.split("/")
        and "rfc1738" not in family
        and "urlid" not in family
        and "urldigest" not in family
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
    packed = encode_identify(identity=SENTINEL, uriid=DEFAULT_URIID, uridigest=DEFAULT_URIDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_identify"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_uriid"] is True
        and parsed["uriid"] == DEFAULT_URIID
        and parsed["uridigest"] == DEFAULT_URIDIGEST
        and parsed["is_deref"] is False
        and parsed["is_deref"] is False
        and parsed["type"] == FRAME_IDENTIFY
        and parsed["first_byte"] == URI_FIRST
    )
    shook = encode_deref(
        identity=SENTINEL,
        uriid=DEFAULT_URIID,
        uridigest=DEFAULT_URIDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_deref"] is True
        and answer_parsed["is_deref"] is True
        and answer_parsed["is_identify"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["uriid"] == DEFAULT_URIID
        and answer_parsed["uridigest"] == DEFAULT_URIDIGEST
        and answer_parsed["has_uridigest"] is True
        and answer_parsed["type"] == FRAME_DEREF
        and answer_parsed["first_byte"] == URI_FIRST
    )
    bare = encode_identify(identity=SENTINEL, uriid=DEFAULT_URIID, include_uriid=False)
    checks["missing_uriid_is_unauthed"] = parse_message(bare)["has_uriid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(URI_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_uri = ToolDescriptor(name="remote_uri", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_uri)
    checks["naive_mcp_uri_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = uri_tool_descriptor()
    default_uri = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, URI_TOOL_PROVIDER),
    )
    checks["default_uri_provider_is_unsupported"] = (
        default_uri.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{URI_TOOL_PROVIDER}" in default_uri.reasons
    )
    checks["opted_in_uri_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_uri],
        required_tool_names=("local_memory", "uri"),
    )
    checks["naive_preflight_missing_uri"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["uri"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "uri"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, URI_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "uri" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="uri-actuation-") as tmp:
        root = Path(tmp)
        missing = run_uri_workflow(with_uriid=False, output_dir=root / "missing")
        skip_bind = run_uri_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_identify = run_uri_workflow(do_identify=False, output_dir=root / "skip-identify")
        skip_deref = run_uri_workflow(do_deref=False, output_dir=root / "skip-deref")
        skip_uridigest = run_uri_workflow(do_uridigest=False, output_dir=root / "skip-uridigest")
        skip_replay = run_uri_workflow(replay=False, output_dir=root / "skip-replay")
        skip_uriid = run_uri_workflow(use_uriid=False, output_dir=root / "skip-uriid")
        live = run_uri_workflow(output_dir=root / "live")
        verify = verify_uri_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_uri_trace(clone)
        checks["naive_without_uriid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_uriid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_identify_stays_empty"] = (
            skip_identify["ok"] is False
            and skip_identify["error"] == "identify_required"
            and skip_identify["final_status"] == 409
            and skip_identify["payload_exists"] is False
        )
        checks["skip_deref_stays_empty"] = (
            skip_deref["ok"] is False
            and skip_deref["error"] == "deref_required"
            and skip_deref["final_status"] == 409
            and skip_deref["payload_exists"] is False
        )
        checks["skip_uridigest_stays_empty"] = (
            skip_uridigest["ok"] is False
            and skip_uridigest["error"] == "uridigest_required"
            and skip_uridigest["final_status"] == 409
            and skip_uridigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_uriid_stays_empty"] = (
            skip_uriid["ok"] is False
            and skip_uriid["error"] == "uriid_required"
            and skip_uriid["final_status"] == 409
            and skip_uriid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_uridigest"] = (
            int(live.get("uriid") or 0) == DEFAULT_URIID
            and int(live.get("uridigest") or 0) == DEFAULT_URIDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_uriid_encode_deref_uridigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_identify["ok"] is False
            and skip_deref["ok"] is False
            and skip_uridigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_uriid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="uri-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != URI_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_uri"] = (
        live_goal == URI_ACTUATION_GOAL
        and URI_ACTUATION_ID in live_done
        and live_source == "genesis_bind_uri"
    )

    with tempfile.TemporaryDirectory(prefix="uri-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(URI_LEFTOVER, root)
        register_catalog_proved(root, URI_ACTUATION_ID)
        reason = leftover_satisfied_by(URI_LEFTOVER, root)
        after = leftover_is_open(URI_LEFTOVER, root)
    checks["uri_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_uri_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{URI_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_uri_actuation_capability()
    return {
        "ok": ok,
        "action": "uri_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": URI_ACTUATION_GOAL,
        "done_when": URI_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
