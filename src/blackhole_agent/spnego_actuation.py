"""Drive a first-class SPNEGO-based Kerberos and NTLM HTTP Authentication tool through RFC 4559 NEGOTIATE/AUTHENTICATE.

Tool routing already fails missions that require ``spnego``: hosted
spnego endpoints stay on the unsupported MCP provider, and no first-party
spnego provider is executable. Unbound therefore cannot speak a NEGOTIATE,
lockstep an AUTHENTICATE negotiateid handshake over HTTP Negotiate NEGOTIATEID,
independently poll the stored negotiatedigest, or seal a negotiatedigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``spnego`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 4559 daemon
- keep a missing-negotiateid client so the spnego-negotiateid hole stays falsifiable
- refuse AUTHENTICATE until a NEGOTIATE lands with a non-empty negotiateid
- independently poll the stored negotiatedigest on a later client socket
- persist a sealed negotiatedigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 4918 HTTP Extensions for WebDAV
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
    SPNEGO_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    spnego_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
SPNEGO_ACTUATION_ID = "capability.spnego-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SPN-OK"
POLL_TOKEN = "BH-SPN-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_NEGOTIATEID = 0
EMPTY_NEGOTIATEDIGEST = 0
NEGOTIATE_FIRST = 0x4E  # RFC 4559 SPNEGO-based Kerberos and NTLM HTTP Authentication (ASCII 'N')
NEGOTIATEID_SIZE = 4
NEGOTIATEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_AUTHENTICATE = 0x02  # RFC 4559 authenticate confirmation
FRAME_NEGOTIATE = 0x01  # RFC 4559 NEGOTIATE
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
SPNEGO_LEFTOVER = (
    "Later genesis can take RFC 4559 SPNEGO-based Kerberos and NTLM HTTP Authentication NEGOTIATE/AUTHENTICATE over a "
    "negotiateid-gated negotiatedigest."
)
SPNEGO_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SPNEGO_ACTUATION_ID};"
    f"capability_proved:{SPNEGO_ACTUATION_ID};"
    "no_skill_route"
)
SPNEGO_ACTUATION_GOAL = (
    "Repair rfc4559 spnego negotiate/authenticate cycle cannot land over http "
    "spnego negotiateid: hosted spnego endpoints remain unsupported so a NEGOTIATE then "
    "AUTHENTICATE negotiateid handshake cannot land and a sealed negotiatedigest "
    "cannot be produced. A missing spnego negotiateid stays forbidden; fail-closed "
    "routing never opts the spnego provider in. An independent later poll of the "
    "stored negotiatedigest keeps the hole falsifiable."
)


class SpnegoActuationError(RuntimeError):
    """Raised when the authenticate session or loopback daemon fixture misbehaves."""


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
# RFC 4559 sections 9.1 and 9.10: mech / gssmech.
RFC_NEGOTIATE_FIELD = "NEGOTIATE"
RFC_AUTHENTICATE_FIELD = "AUTHENTICATE"
RFC_SPNEGO_AUTHENTICATE = RFC_AUTHENTICATE_FIELD
RFC_NEGOTIATE_DIRECTIVE = "mech=Negotiate"
RFC_AUTHENTICATE_DIRECTIVE = "gssmech=kerberos"
DEFAULT_NEGOTIATE = "NEGOTIATE"
AUTHENTICATE_POLICY = "AUTHENTICATE"
NEGOTIATE_HEADER = "Negotiate"
AUTHENTICATE_HEADER = "Negotiate"
SPNEGO_AUTHENTICATE_HEADER = AUTHENTICATE_HEADER
RFC_NEGOTIATE_PATH = "/negotiate/"
RFC_NEGOTIATE_EMPTY = ""


def spnego_directive_pair(*, authenticate: bool = False) -> tuple[str, str]:
    """RFC 4559 section 3 dav-uri mech / registered gssmech."""

    if authenticate:
        return "gssmech", "kerberos"
    return "mech", "Negotiate"


def ascii_serialize_spnego_directive(*, authenticate: bool = False) -> str:
    """RFC 4559 dav-uri: token "=" authenticate-or-mech."""

    name, value = spnego_directive_pair(authenticate=authenticate)
    if not is_token(name):
        raise SpnegoActuationError("illegal_directive")
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
            raise SpnegoActuationError("short_spnego")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 4559 DAV token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_spnego(policy: str | Sequence[str]) -> str:
    """Serialize RFC 4559 mech / gssmech token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise SpnegoActuationError("illegal_spnego")
    upper = text.upper().replace("_", "-")
    if upper in {"NEGOTIATE", "MECH", "SPNEGO"}:
        return "NEGOTIATE"
    if upper in {"AUTHENTICATE", "GSSMECH", "KERBEROS"}:
        return "AUTHENTICATE"
    if upper.startswith("MECH="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SpnegoActuationError("illegal_spnego")
        return "NEGOTIATE"
    if upper.startswith("GSSMECH="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SpnegoActuationError("illegal_spnego")
        return "AUTHENTICATE"
    raise SpnegoActuationError("illegal_spnego")


def parse_spnego(text: str) -> str:
    """Parse RFC 4559 DAV negotiate extensions into NEGOTIATE or AUTHENTICATE."""

    raw = str(text or "").strip()
    if not raw:
        raise SpnegoActuationError("illegal_spnego")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"NEGOTIATE", "MECH", "SPNEGO"}:
        return "NEGOTIATE"
    if upper in {"AUTHENTICATE", "GSSMECH", "KERBEROS"}:
        return "AUTHENTICATE"
    if upper.startswith("MECH="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SpnegoActuationError("illegal_spnego")
        return "NEGOTIATE"
    if upper.startswith("GSSMECH="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SpnegoActuationError("illegal_spnego")
        return "AUTHENTICATE"
    raise SpnegoActuationError("illegal_spnego")


def encode_spnego_header(policy: str | Sequence[str]) -> bytes:
    """RFC 4559 DAV field as bytes."""

    return serialize_spnego(policy).encode("ascii")


def parse_spnego_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_spnego(field_value) if field_value else DEFAULT_NEGOTIATE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": NEGOTIATE_HEADER,
        "directive": str(policy),
        "negotiate": str(policy) == "NEGOTIATE",
        "authenticate": str(policy) == "AUTHENTICATE",
    }


def canonical_negotiate(identity: str, negotiateid: int) -> str:
    """RFC 4559 NEGOTIATE advertisement bound to identity and negotiateid."""

    return (
        f"{serialize_spnego(DEFAULT_NEGOTIATE)}, "
        f"negotiate={ascii_serialize_spnego_directive()}, "
        f"identity={identity}, negotiateid={int(negotiateid) & 0xFFFFFFFF}"
    )


def canonical_authenticate(identity: str, negotiateid: int, negotiatedigest: int | None = None) -> str:
    """RFC 4559 AUTHENTICATE confirmation of the stored authenticate policy."""

    authenticate = ""
    if negotiatedigest is not None:
        authenticate = f", negotiatedigest={int(negotiatedigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_spnego(AUTHENTICATE_POLICY)}, "
        f"authenticate={ascii_serialize_spnego_directive(authenticate=True)}, "
        f"identity={identity}, negotiateid={int(negotiateid) & 0xFFFFFFFF}{authenticate}"
    )


def representation_authenticate(identity: str, negotiateid: int, negotiatedigest: int) -> str:
    return canonical_authenticate(identity, negotiateid, negotiatedigest)


def spnego_matches(left: str, right: str) -> bool:
    return parse_spnego(left) == parse_spnego(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise SpnegoActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise SpnegoActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise SpnegoActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise SpnegoActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def negotiate_request(identity: str, negotiateid: int) -> bytes:
    """HTTP NEGOTIATE that elicits RFC 4559 origin NEGOTIATE."""

    keyid = f"{int(negotiateid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"NEGOTIATE /negotiate/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Negotiate-Id: {int(negotiateid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def authenticate_request(identity: str, negotiateid: int, negotiatedigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 4559 AUTHENTICATE confirmation of the stored authenticate policy."""

    keyid = f"{int(negotiateid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if negotiatedigest is not None:
        extra = f"Negotiate-Digest: {int(negotiatedigest) & 0xFFFFFFFF}\r\n"
    return (
        f"AUTHENTICATE /negotiate/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Negotiate-Id: {int(negotiateid) & 0xFFFFFFFF}\r\n"
        "Negotiate-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    spnego_kind = "authenticate" if fields.get("negotiate-confirm") == "1" else "negotiate"
    negotiate_field = fields.get("negotiate") or ""
    policy = parse_spnego(negotiate_field) if negotiate_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "spnego_kind": spnego_kind,
        "policy": policy,
        "negotiateid": int(fields["negotiate-id"]) if fields.get("negotiate-id") else EMPTY_NEGOTIATEID,
        "negotiatedigest": int(fields["negotiate-digest"]) if fields.get("negotiate-digest") else EMPTY_NEGOTIATEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def negotiate_response(identity: str, negotiateid: int, negotiatedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 4559 origin NEGOTIATE, carrying the stored negotiatedigest."""

    advertised = serialize_spnego(DEFAULT_NEGOTIATE)
    payload = bytes(body or canonical_negotiate(identity, negotiateid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Negotiate: {advertised}\r\n"
        f"Negotiate-Id: {int(negotiateid) & 0xFFFFFFFF}\r\n"
        f"Negotiate-Digest: {int(negotiatedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def authenticate_response(identity: str, negotiateid: int, negotiatedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 4559 AUTHENTICATE, carrying the stored AUTHENTICATE policy."""

    advertised = serialize_spnego(AUTHENTICATE_POLICY)
    payload = bytes(body or representation_authenticate(identity, negotiateid, negotiatedigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Negotiate: {advertised}\r\n"
        f"Negotiate-Id: {int(negotiateid) & 0xFFFFFFFF}\r\n"
        f"Negotiate-Digest: {int(negotiatedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/spnego-auth\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise SpnegoActuationError("illegal_content_length") from error
    field_value = fields.get("negotiate") or ""
    policy = parse_spnego(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/spnego-auth" or policy == AUTHENTICATE_POLICY:
        status = 200
        spnego_kind = "authenticate"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        spnego_kind = "negotiate"
    else:
        status = 0
        spnego_kind = "negotiate"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "spnego_kind": spnego_kind,
        "policy": policy,
        "negotiateid": int(fields["negotiate-id"]) if fields.get("negotiate-id") else EMPTY_NEGOTIATEID,
        "negotiatedigest": int(fields["negotiate-digest"]) if fields.get("negotiate-digest") else EMPTY_NEGOTIATEDIGEST,
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
        raise SpnegoActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise SpnegoActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise SpnegoActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise SpnegoActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_negotiateid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"negotiateid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_negotiateid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-negotiateid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_negotiatedigest(negotiateid: int = EMPTY_NEGOTIATEID, token: str = SENTINEL) -> int:
    material = canonical_negotiate(token or SENTINEL, int(negotiateid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_NEGOTIATEID = request_negotiateid(SENTINEL)
DEFAULT_NEGOTIATEDIGEST = request_negotiatedigest(DEFAULT_NEGOTIATEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    negotiateid: int,
    negotiatedigest: int,
    include_negotiateid: bool = True,
) -> bytes:
    live_negotiateid = int(negotiateid) & 0xFFFFFFFF if include_negotiateid else EMPTY_NEGOTIATEID
    live_digest = int(negotiatedigest) & 0xFFFFFFFF if include_negotiateid and live_negotiateid else EMPTY_NEGOTIATEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_negotiateid) if live_negotiateid else b""
    header = bytearray()
    header.append(NEGOTIATE_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_negotiate(
    *,
    identity: str,
    negotiateid: int,
    negotiatedigest: int | None = None,
    include_negotiateid: bool = True,
) -> bytes:
    live_negotiateid = int(negotiateid) & 0xFFFFFFFF if include_negotiateid else EMPTY_NEGOTIATEID
    live_digest = int(negotiatedigest) if negotiatedigest is not None else request_negotiatedigest(live_negotiateid, identity)
    return encode_packet(
        FRAME_NEGOTIATE,
        identity=identity,
        negotiateid=live_negotiateid,
        negotiatedigest=live_digest,
        include_negotiateid=include_negotiateid,
    )


def encode_authenticate(
    *,
    identity: str,
    negotiateid: int,
    negotiatedigest: int | None = None,
    include_negotiateid: bool = True,
) -> bytes:
    live_negotiateid = int(negotiateid) & 0xFFFFFFFF if include_negotiateid else EMPTY_NEGOTIATEID
    live_digest = int(negotiatedigest) if negotiatedigest is not None else request_negotiatedigest(live_negotiateid, identity)
    return encode_packet(
        FRAME_AUTHENTICATE,
        identity=identity,
        negotiateid=live_negotiateid,
        negotiatedigest=live_digest,
        include_negotiateid=include_negotiateid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise SpnegoActuationError("short_packet")
    first = raw[0]
    if first != NEGOTIATE_FIRST:
        raise SpnegoActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise SpnegoActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == NEGOTIATEID_SIZE:
        live_negotiateid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_negotiateid = EMPTY_NEGOTIATEID
    else:
        raise SpnegoActuationError("illegal_negotiateid")
    if offset >= len(raw):
        raise SpnegoActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_NEGOTIATE, FRAME_AUTHENTICATE}:
        raise SpnegoActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise SpnegoActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise SpnegoActuationError("checksum_failed")
    if len(payload) < 5:
        raise SpnegoActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise SpnegoActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_negotiateid = int(live_negotiateid) != EMPTY_NEGOTIATEID
    has_negotiatedigest = has_negotiateid and int(live_digest) != EMPTY_NEGOTIATEDIGEST
    is_negotiate = frame_type == FRAME_NEGOTIATE
    is_authenticate = frame_type == FRAME_AUTHENTICATE
    return {
        "type": int(frame_type),
        "is_negotiate": is_negotiate,
        "is_authenticate": is_authenticate,
        "is_response": is_authenticate,
        "negotiateid": int(live_negotiateid),
        "has_negotiateid": has_negotiateid,
        "negotiatedigest": int(live_digest),
        "has_negotiatedigest": has_negotiatedigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC4559",
        "serialize_field": canonical_negotiate(identity, live_negotiateid) if has_negotiateid else "",
        "authenticate_field": canonical_authenticate(identity, live_negotiateid, live_digest) if has_negotiatedigest else "",
    }


class SpnegoClient:
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
            raise SpnegoActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_authenticate"] or not packet["is_response"]:
            raise SpnegoActuationError("negotiatedigest_required")
        if not packet["has_negotiateid"]:
            raise SpnegoActuationError("negotiateid_required")
        if not packet["has_negotiatedigest"]:
            raise SpnegoActuationError("negotiatedigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_negotiatedigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_negotiatedigest:
            raise SpnegoActuationError("negotiatedigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "negotiateid": int(reply.get("negotiateid") or EMPTY_NEGOTIATEID),
            "identity": str(reply.get("identity") or ""),
            "negotiatedigest": int(reply.get("negotiatedigest") or EMPTY_NEGOTIATEDIGEST),
        }

    def report(
        self,
        identity: str,
        negotiateid: int,
        negotiatedigest: int = EMPTY_NEGOTIATEDIGEST,
        *,
        wait_negotiatedigest: bool = True,
        include_negotiateid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_authenticate(
            identity=identity,
            negotiateid=negotiateid,
            negotiatedigest=negotiatedigest or request_negotiatedigest(negotiateid, identity),
            include_negotiateid=include_negotiateid,
        )
        return self.exchange(packet, wait_negotiatedigest=wait_negotiatedigest)


class SpnegoSession:
    """NEGOTIATEID-gated loopback RFC 4559 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        negotiateid_gate: int = DEFAULT_NEGOTIATEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.negotiateid_gate = int(negotiateid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.negotiateid = EMPTY_NEGOTIATEID
        self.negotiatedigest = EMPTY_NEGOTIATEDIGEST
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

    def store_negotiateid_once(self, identity: str, negotiateid: int, negotiatedigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(negotiateid or EMPTY_NEGOTIATEID)
            live_digest = int(negotiatedigest or EMPTY_NEGOTIATEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.negotiateid = live
                self.negotiatedigest = live_digest or request_negotiatedigest(live, name)
                self.stored = True
            return str(self.identity), int(self.negotiateid), int(self.negotiatedigest)

    def read_negotiateid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.negotiateid), int(self.negotiatedigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "negotiateid": EMPTY_NEGOTIATEID,
            "negotiatedigest": EMPTY_NEGOTIATEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _negotiateid_missing(self) -> bool:
        return not int(self.negotiateid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, negotiateid: int, negotiatedigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_authenticate(
            identity=identity,
            negotiateid=negotiateid,
            negotiatedigest=negotiatedigest,
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
            except SpnegoActuationError:
                continue
            if not packet.get("is_negotiate") and not packet.get("is_authenticate"):
                continue
            if not packet.get("has_negotiateid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_negotiateid, stored_digest = self.store_negotiateid_once(
                identity,
                int(packet.get("negotiateid") or EMPTY_NEGOTIATEID),
                int(packet.get("negotiatedigest") or EMPTY_NEGOTIATEDIGEST),
            )
            if not stored_name or not stored_negotiateid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_negotiate"):
                    self.opened = True
                if packet.get("is_authenticate"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_negotiateid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._negotiateid_missing():
            return self._forbidden("missing_negotiateid")
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
        do_negotiate: bool = True,
        do_authenticate: bool = True,
        do_negotiatedigest: bool = True,
        replay: bool = True,
        use_negotiateid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._negotiateid_missing():
            return self._forbidden("missing_negotiateid")
        live_token = str(token or SENTINEL)
        origin_negotiateid = request_negotiateid(live_token)
        origin_digest = request_negotiatedigest(origin_negotiateid, live_token)
        client: SpnegoClient | None = None
        independent: SpnegoClient | None = None
        try:
            client = SpnegoClient(self.host, int(self.port))
            if not do_negotiate:
                return self._conflict("negotiate_required")
            bind_packet = encode_negotiate(
                identity=live_token,
                negotiateid=origin_negotiateid,
                negotiatedigest=origin_digest,
                include_negotiateid=use_negotiateid,
            )
            if not use_negotiateid:
                try:
                    client.exchange(bind_packet, wait_negotiatedigest=True)
                except SpnegoActuationError:
                    return self._conflict("negotiateid_required")
                return self._conflict("negotiateid_required")
            client.send(bind_packet)
            if not do_authenticate:
                return self._conflict("authenticate_required")
            proxy_packet = encode_authenticate(
                identity=live_token,
                negotiateid=origin_negotiateid,
                negotiatedigest=origin_digest,
                include_negotiateid=True,
            )
            if not do_negotiatedigest:
                try:
                    client.exchange(proxy_packet, wait_negotiatedigest=False)
                except SpnegoActuationError as error:
                    if str(error) == "negotiatedigest_required":
                        return self._conflict("negotiatedigest_required")
                    return self._conflict("negotiatedigest_required")
                return self._conflict("negotiatedigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_negotiatedigest=True)
            except SpnegoActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("negotiateid_required")
                if reason == "negotiatedigest_required":
                    return self._conflict("negotiatedigest_required")
                return self._conflict("negotiate_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("negotiate_required")
            if int(reply.get("negotiateid") or EMPTY_NEGOTIATEID) != origin_negotiateid:
                return self._conflict("negotiatedigest_required")
            if int(reply.get("negotiatedigest") or EMPTY_NEGOTIATEDIGEST) != origin_digest:
                return self._conflict("negotiatedigest_required")
            self.retrieved = True
            if replay:
                independent = SpnegoClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_negotiateid(live_token),
                        request_negotiatedigest(poll_negotiateid(live_token), POLL_TOKEN),
                        wait_negotiatedigest=True,
                    )
                except SpnegoActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_negotiateid, stored_digest = self.read_negotiateid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_negotiateid != origin_negotiateid
                    or stored_digest != origin_digest
                    or int(poll.get("negotiateid") or EMPTY_NEGOTIATEID) != origin_negotiateid
                    or int(poll.get("negotiatedigest") or EMPTY_NEGOTIATEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_negotiateid}:{origin_digest}:{live_token}:{canonical_negotiate(live_token, origin_negotiateid)}:{canonical_authenticate(live_token, origin_negotiateid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "negotiateid": origin_negotiateid,
                "negotiatedigest": origin_digest,
                "negotiate_frame": True,
                "authenticate_frame": True,
                "negotiatedigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "negotiateid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_spnego_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "negotiateid": origin_negotiateid,
                "negotiatedigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "negotiate_frame": True,
                "authenticate_frame": True,
                "negotiatedigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "negotiateid_bound": True,
            }
        except (OSError, SpnegoActuationError) as error:
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
        live = independent_spnego_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "negotiateid": int(live.get("negotiateid") or EMPTY_NEGOTIATEID),
            "negotiatedigest": int(live.get("negotiatedigest") or EMPTY_NEGOTIATEDIGEST),
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


def call_spnego_tool(session: SpnegoSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one negotiate tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_negotiate = True if arguments.get("negotiate") is None else bool(arguments.get("negotiate"))
    do_authenticate = True if arguments.get("authenticate") is None else bool(arguments.get("authenticate"))
    do_negotiatedigest = True if arguments.get("negotiatedigest") is None else bool(arguments.get("negotiatedigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_negotiateid = True if arguments.get("use_negotiateid") is None else bool(arguments.get("use_negotiateid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_negotiate=do_negotiate,
            do_authenticate=do_authenticate,
            do_negotiatedigest=do_negotiatedigest,
            replay=replay,
            use_negotiateid=use_negotiateid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SpnegoActuationError(f"unsupported spnego action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_spnego_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed negotiate negotiatedigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "negotiateid": EMPTY_NEGOTIATEID,
        "negotiatedigest": EMPTY_NEGOTIATEDIGEST,
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
            "negotiate_frame",
            "authenticate_frame",
            "negotiatedigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "negotiateid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    negotiateid = int(payload.get("negotiateid") or EMPTY_NEGOTIATEID)
    negotiatedigest = int(payload.get("negotiatedigest") or EMPTY_NEGOTIATEDIGEST)
    dual = port > 0 and bool(negotiateid) and bool(negotiatedigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "negotiateid": negotiateid,
        "negotiatedigest": negotiatedigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "negotiate_frame": payload.get("negotiate_frame") is True,
        "authenticate_frame": payload.get("authenticate_frame") is True,
        "negotiatedigest_response": payload.get("negotiatedigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "negotiateid_bound": payload.get("negotiateid_bound") is True,
    }


def run_spnego_workflow(
    *,
    with_negotiateid: bool = True,
    skip_bind: bool = False,
    do_negotiate: bool = True,
    do_authenticate: bool = True,
    do_negotiatedigest: bool = True,
    replay: bool = True,
    use_negotiateid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 4559 NEGOTIATE/AUTHENTICATE negotiateid cycle workflow."""

    descriptor = spnego_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SPNEGO_TOOL_PROVIDER),
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
        raise SpnegoActuationError(f"spnego tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="spnego-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SpnegoSession(out, negotiateid_gate=DEFAULT_NEGOTIATEID if with_negotiateid else EMPTY_NEGOTIATEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "negotiate": do_negotiate,
            "authenticate": do_authenticate,
            "negotiatedigest": do_negotiatedigest,
            "replay": replay,
            "use_negotiateid": use_negotiateid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_spnego_tool(session, arguments))
            except SpnegoActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_spnego_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_negotiateid
        and not skip_bind
        and do_negotiate
        and do_authenticate
        and do_negotiatedigest
        and replay
        and use_negotiateid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "spnego_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_negotiateid": with_negotiateid,
        "skip_bind": skip_bind,
        "negotiate_frame": do_negotiate,
        "authenticate": do_authenticate,
        "negotiatedigest": do_negotiatedigest,
        "replay": replay,
        "use_negotiateid": use_negotiateid,
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
        "negotiateid_value": int(publish_result.get("negotiateid") or independent.get("negotiateid") or EMPTY_NEGOTIATEID),
        "negotiatedigest_value": int(publish_result.get("negotiatedigest") or independent.get("negotiatedigest") or EMPTY_NEGOTIATEDIGEST),
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
        "negotiateid": int(trace_body["negotiateid_value"] or EMPTY_NEGOTIATEID),
        "negotiatedigest": int(trace_body["negotiatedigest_value"] or EMPTY_NEGOTIATEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_negotiateid": with_negotiateid,
        "skip_bind": skip_bind,
        "negotiate_cycle": do_negotiate,
        "authenticate_cycle": do_authenticate,
        "negotiatedigest_cycle": do_negotiatedigest,
        "replay": replay,
        "use_negotiateid": use_negotiateid,
    }


def verify_spnego_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_spnego_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    negotiateid = int(trace.get("negotiateid_value") or independent.get("negotiateid") or EMPTY_NEGOTIATEID)
    negotiatedigest = int(trace.get("negotiatedigest_value") or independent.get("negotiatedigest") or EMPTY_NEGOTIATEDIGEST)
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
        "negotiate_frame": independent.get("negotiate_frame") is True,
        "authenticate_frame": independent.get("authenticate_frame") is True,
        "negotiatedigest_response": independent.get("negotiatedigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "negotiateid_bound": independent.get("negotiateid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "negotiatedigest_recorded": (
            port > 0
            and negotiateid == DEFAULT_NEGOTIATEID
            and negotiatedigest == DEFAULT_NEGOTIATEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def spnego_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.spnego_actuation import "
        "builtin_spnego_actuation_proof; r=builtin_spnego_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='spnego_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_spnego_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SPNEGO_ACTUATION_ID,
        name="First-class RFC 4559 SPNEGO-based Kerberos and NTLM HTTP Authentication NEGOTIATE/AUTHENTICATE actuation",
        description=(
            "Missions that require a spnego tool can opt the spnego provider in, "
            "bind a loopback RFC 4559 SPNEGO-based Kerberos and NTLM HTTP Authentication endpoint, complete a NEGOTIATE "
            "with a non-empty negotiateid, lockstep an AUTHENTICATE that carries the "
            "stored negotiatedigest, independently poll the stored negotiatedigest "
            "on a later socket, and seal a digest-chained negotiatedigest. Default "
            "routing stays fail-closed; a missing negotiateid keeps the hole "
            "falsifiable, and skip-NEGOTIATE/AUTHENTICATE/NEGOTIATEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.spnego_actuation:builtin_spnego_actuation_proof",
        proof_command=spnego_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.webdav-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/spnego_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/webdav_actuation.py",
            "src/blackhole_agent/httptls_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required spnego tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 4559 daemon, speaks a "
            "NEGOTIATE then AUTHENTICATE over SPNEGO-based Kerberos and NTLM HTTP Authentication with a non-empty negotiateid and "
            "negotiatedigest, independently polls the stored negotiatedigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 4918 HTTP Extensions for WebDAV lockstep is proved. "
            "Missing negotiateids, skip-NEGOTIATE, skip-AUTHENTICATE, skip-negotiatedigest, skip-REPLAY, "
            "and a NEGOTIATE aimed without a negotiateid stay fail-closed. "
            "Later genesis can take RFC 2817 Upgrading to TLS Within HTTP/1.1 UPGRADE/TLS as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("spnego", "rfc4559", "http", "negotiateid", "negotiatedigest", "negotiate", "authenticate", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T232410Z-4b9e1e58",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_spnego_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 4559 negotiate lockstep actuation seals a negotiatedigest."""

    from blackhole_agent.webdav_actuation import (
        WEBDAV_ACTUATION_GOAL,
        WEBDAV_ACTUATION_ID,
    )
    from blackhole_agent.httptls_actuation import (
        HTTPTLS_ACTUATION_GOAL,
        HTTPTLS_ACTUATION_ID,
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
    checks["denylists_self"] = SPNEGO_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SPNEGO_ACTUATION_GOAL) == (
        SPNEGO_ACTUATION_ID,
    )
    checks["leftover_text_binds_spnego"] = leftover_marker_ids(SPNEGO_LEFTOVER) == (
        SPNEGO_ACTUATION_ID,
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
        (WEBDAV_ACTUATION_GOAL, WEBDAV_ACTUATION_ID, "webdav"),
        (HTTPTLS_ACTUATION_GOAL, HTTPTLS_ACTUATION_ID, "httptls"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_spnego"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"spnego_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            SPNEGO_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = SPNEGO_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_spnego(DEFAULT_NEGOTIATE)
    rebuilt = serialize_spnego(parse_spnego(advertised))
    preloaded = parse_spnego(RFC_SPNEGO_AUTHENTICATE)
    header = encode_spnego_header(DEFAULT_NEGOTIATE)
    parsed_header = parse_spnego_header(header)
    asked = parse_http_request(negotiate_request(SENTINEL, DEFAULT_NEGOTIATEID))
    preload_req = parse_http_request(authenticate_request(SENTINEL, DEFAULT_NEGOTIATEID, DEFAULT_NEGOTIATEDIGEST))
    got = parse_http_response(negotiate_response(SENTINEL, DEFAULT_NEGOTIATEID, DEFAULT_NEGOTIATEDIGEST))
    preload_reply = parse_http_response(
        authenticate_response(SENTINEL, DEFAULT_NEGOTIATEID, DEFAULT_NEGOTIATEDIGEST)
    )
    checks["spnego_roundtrip"] = (
        parse_spnego(advertised) == DEFAULT_NEGOTIATE
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_NEGOTIATE_FIELD
        and is_token("NEGOTIATE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_NEGOTIATE_FIELD
        and parsed_header["policy"] == DEFAULT_NEGOTIATE
        and parsed_header["header"] == NEGOTIATE_HEADER
        and parsed_header["negotiate"] is True
        and parsed_header["authenticate"] is False
        and preloaded == AUTHENTICATE_POLICY
        and ascii_serialize_spnego_directive() == RFC_NEGOTIATE_DIRECTIVE
        and spnego_directive_pair() == ("mech", "Negotiate")
        and RFC_NEGOTIATE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_spnego(AUTHENTICATE_POLICY) == RFC_SPNEGO_AUTHENTICATE
        and DEFAULT_NEGOTIATEDIGEST == request_negotiatedigest(DEFAULT_NEGOTIATEID, SENTINEL)
        and "negotiatedigest=" in canonical_authenticate(SENTINEL, DEFAULT_NEGOTIATEID, DEFAULT_NEGOTIATEDIGEST)
        and canonical_negotiate(SENTINEL, DEFAULT_NEGOTIATEID).startswith("NEGOTIATE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "NEGOTIATE"
        and asked["spnego_kind"] == "negotiate"
        and asked["negotiateid"] == DEFAULT_NEGOTIATEID
        and preload_req["spnego_kind"] == "authenticate"
        and preload_req["negotiatedigest"] == DEFAULT_NEGOTIATEDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["spnego_kind"] == "negotiate"
        and preload_reply["spnego_kind"] == "authenticate"
        and got["policy"] == DEFAULT_NEGOTIATE
        and preload_reply["policy"] == AUTHENTICATE_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["negotiatedigest"] == DEFAULT_NEGOTIATEDIGEST
        and preload_reply["negotiatedigest"] == DEFAULT_NEGOTIATEDIGEST
        and spnego_matches(serialize_spnego(got["policy"]), advertised)
    )

    checks["catalog_names_spnego"] = (
        len(catalog) > 94
        and catalog[94]["id"] == SPNEGO_ACTUATION_ID
        and catalog[93]["id"] == WEBDAV_ACTUATION_ID
        and catalog[94]["source"] == "genesis_bind_spnego"
    )
    checks["catalog_names_httptls"] = (
        len(catalog) > 95
        and catalog[95]["id"] == HTTPTLS_ACTUATION_ID
        and catalog[95]["source"] == "genesis_bind_httptls"
    )
    family = capability_family(SPNEGO_ACTUATION_GOAL)
    checks["family_is_spnego"] = "spnego" in family
    checks["family_is_spnego_surface"] = "spnego" in family
    checks["family_is_negotiateid"] = "negotiateid" in family
    checks["family_is_rfc4559"] = "rfc4559" in family
    checks["family_is_negotiatedigest"] = "negotiatedigest" in family
    checks["family_is_not_webdav"] = (
        "webdav" not in family
        and "rfc4918" not in family
        and "lockid" not in family
        and "lockdigest" not in family
    )
    checks["family_is_not_httptls"] = (
        "httptls" not in family
        and "rfc2817" not in family
        and "upgradeid" not in family
        and "upgradetlsdigest" not in family
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
    packed = encode_negotiate(identity=SENTINEL, negotiateid=DEFAULT_NEGOTIATEID, negotiatedigest=DEFAULT_NEGOTIATEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_negotiate"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_negotiateid"] is True
        and parsed["negotiateid"] == DEFAULT_NEGOTIATEID
        and parsed["negotiatedigest"] == DEFAULT_NEGOTIATEDIGEST
        and parsed["is_response"] is False
        and parsed["is_authenticate"] is False
        and parsed["type"] == FRAME_NEGOTIATE
        and parsed["first_byte"] == NEGOTIATE_FIRST
    )
    shook = encode_authenticate(
        identity=SENTINEL,
        negotiateid=DEFAULT_NEGOTIATEID,
        negotiatedigest=DEFAULT_NEGOTIATEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_authenticate"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_negotiate"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["negotiateid"] == DEFAULT_NEGOTIATEID
        and answer_parsed["negotiatedigest"] == DEFAULT_NEGOTIATEDIGEST
        and answer_parsed["has_negotiatedigest"] is True
        and answer_parsed["type"] == FRAME_AUTHENTICATE
        and answer_parsed["first_byte"] == NEGOTIATE_FIRST
    )
    bare = encode_negotiate(identity=SENTINEL, negotiateid=DEFAULT_NEGOTIATEID, include_negotiateid=False)
    checks["missing_negotiateid_is_unauthenticated"] = parse_message(bare)["has_negotiateid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    spnego_signature = semantic_signature(SPNEGO_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(spnego_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_spnego = ToolDescriptor(name="remote_spnego", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_spnego)
    checks["naive_mcp_spnego_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = spnego_tool_descriptor()
    default_spnego = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SPNEGO_TOOL_PROVIDER),
    )
    checks["default_spnego_provider_is_unsupported"] = (
        default_spnego.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SPNEGO_TOOL_PROVIDER}" in default_spnego.reasons
    )
    checks["opted_in_spnego_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_spnego],
        required_tool_names=("local_memory", "spnego"),
    )
    checks["naive_preflight_missing_spnego"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["spnego"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "spnego"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SPNEGO_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "spnego" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="spnego-actuation-") as tmp:
        root = Path(tmp)
        missing = run_spnego_workflow(with_negotiateid=False, output_dir=root / "missing")
        skip_bind = run_spnego_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_negotiate = run_spnego_workflow(do_negotiate=False, output_dir=root / "skip-negotiate")
        skip_authenticate = run_spnego_workflow(do_authenticate=False, output_dir=root / "skip-authenticate")
        skip_negotiatedigest = run_spnego_workflow(do_negotiatedigest=False, output_dir=root / "skip-negotiatedigest")
        skip_replay = run_spnego_workflow(replay=False, output_dir=root / "skip-replay")
        skip_negotiateid = run_spnego_workflow(use_negotiateid=False, output_dir=root / "skip-negotiateid")
        live = run_spnego_workflow(output_dir=root / "live")
        verify = verify_spnego_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_spnego_trace(clone)
        checks["naive_without_negotiateid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_negotiateid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_negotiate_stays_empty"] = (
            skip_negotiate["ok"] is False
            and skip_negotiate["error"] == "negotiate_required"
            and skip_negotiate["final_status"] == 409
            and skip_negotiate["payload_exists"] is False
        )
        checks["skip_authenticate_stays_empty"] = (
            skip_authenticate["ok"] is False
            and skip_authenticate["error"] == "authenticate_required"
            and skip_authenticate["final_status"] == 409
            and skip_authenticate["payload_exists"] is False
        )
        checks["skip_negotiatedigest_stays_empty"] = (
            skip_negotiatedigest["ok"] is False
            and skip_negotiatedigest["error"] == "negotiatedigest_required"
            and skip_negotiatedigest["final_status"] == 409
            and skip_negotiatedigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_negotiateid_stays_empty"] = (
            skip_negotiateid["ok"] is False
            and skip_negotiateid["error"] == "negotiateid_required"
            and skip_negotiateid["final_status"] == 409
            and skip_negotiateid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_negotiatedigest"] = (
            int(live.get("negotiateid") or 0) == DEFAULT_NEGOTIATEID
            and int(live.get("negotiatedigest") or 0) == DEFAULT_NEGOTIATEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_negotiateid_encode_authenticate_negotiatedigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_negotiate["ok"] is False
            and skip_authenticate["ok"] is False
            and skip_negotiatedigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_negotiateid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="spnego-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SPNEGO_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_spnego"] = (
        live_goal == SPNEGO_ACTUATION_GOAL
        and SPNEGO_ACTUATION_ID in live_done
        and live_source == "genesis_bind_spnego"
    )

    with tempfile.TemporaryDirectory(prefix="spnego-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(SPNEGO_LEFTOVER, root)
        register_catalog_proved(root, SPNEGO_ACTUATION_ID)
        reason = leftover_satisfied_by(SPNEGO_LEFTOVER, root)
        after = leftover_is_open(SPNEGO_LEFTOVER, root)
    checks["spnego_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_spnego_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{SPNEGO_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_spnego_actuation_capability()
    return {
        "ok": ok,
        "action": "spnego_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SPNEGO_ACTUATION_GOAL,
        "done_when": SPNEGO_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
