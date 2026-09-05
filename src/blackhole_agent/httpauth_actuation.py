"""Drive a first-class HTTP Authentication tool through RFC 2617 AUTH/DIGEST.

Tool routing already fails missions that require ``httpauth``: hosted
httpauth endpoints stay on the unsupported MCP provider, and no first-party
httpauth provider is executable. Unbound therefore cannot speak a AUTH,
lockstep a DIGEST nonceid handshake over HTTP Digest NONCEID,
independently poll the stored authdigest, or seal a authdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``httpauth`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2617 daemon
- keep a missing-nonceid client so the httpauth-nonceid hole stays falsifiable
- refuse DIGEST until a AUTH lands with a non-empty nonceid
- independently poll the stored authdigest on a later client socket
- persist a sealed authdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 2817 Upgrading to TLS Within HTTP/1.1
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
    HTTPAUTH_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    httpauth_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTPAUTH_ACTUATION_ID = "capability.httpauth-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-AUTH-OK"
POLL_TOKEN = "BH-AUTH-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_NONCEID = 0
EMPTY_AUTHDIGEST = 0
AUTH_FIRST = 0x41  # RFC 2617 HTTP Authentication (ASCII 'A')
NONCEID_SIZE = 4
AUTHDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DIGEST = 0x02  # RFC 2617 digest confirmation
FRAME_AUTH = 0x01  # RFC 2617 AUTH
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTPAUTH_LEFTOVER = (
    "Later genesis can take RFC 2617 HTTP Authentication AUTH/DIGEST over a "
    "nonceid-gated authdigest."
)
HTTPAUTH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPAUTH_ACTUATION_ID};"
    f"capability_proved:{HTTPAUTH_ACTUATION_ID};"
    "no_skill_route"
)
HTTPAUTH_ACTUATION_GOAL = (
    "Repair rfc2617 httpauth auth/digest cycle cannot land over http "
    "httpauth nonceid: hosted httpauth endpoints remain unsupported so a AUTH then "
    "DIGEST nonceid handshake cannot land and a sealed authdigest "
    "cannot be produced. A missing httpauth nonceid stays forbidden; fail-closed "
    "routing never opts the httpauth provider in. An independent later poll of the "
    "stored authdigest keeps the hole falsifiable."
)


class HttpauthActuationError(RuntimeError):
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
# RFC 2617 sections 5.1 and 5.2: AUTH / DIGEST.
RFC_AUTH_FIELD = "AUTH"
RFC_DIGEST_FIELD = "DIGEST"
RFC_HTTPAUTH_DIGEST = RFC_DIGEST_FIELD
RFC_AUTH_DIRECTIVE = "scheme=Digest"
RFC_DIGEST_DIRECTIVE = "qop=auth"
DEFAULT_AUTH = "AUTH"
DIGEST_POLICY = "DIGEST"
AUTH_HEADER = "WWW-Authenticate"
DIGEST_HEADER = "Authorization"
HTTPAUTH_DIGEST_HEADER = DIGEST_HEADER
RFC_AUTH_PATH = "/auth/"
RFC_AUTH_EMPTY = ""


def httpauth_directive_pair(*, digest: bool = False) -> tuple[str, str]:
    """RFC 2617 AUTH scheme / DIGEST qop pair."""

    if digest:
        return "qop", "auth"
    return "scheme", "Digest"


def ascii_serialize_httpauth_directive(*, digest: bool = False) -> str:
    """RFC 2617 token "=" auth-or-digest."""

    name, value = httpauth_directive_pair(digest=digest)
    if not is_token(name):
        raise HttpauthActuationError("illegal_directive")
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
            raise HttpauthActuationError("short_httpauth")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 2617 DAV token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_httpauth(policy: str | Sequence[str]) -> str:
    """Serialize RFC 2617 AUTH / DIGEST token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise HttpauthActuationError("illegal_httpauth")
    upper = text.upper().replace("_", "-")
    if upper in {"AUTH", "SCHEME", "HTTPAUTH"}:
        return "AUTH"
    if upper in {"DIGEST", "QOP", "DIGEST"}:
        return "DIGEST"
    if upper.startswith("SCHEME="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpauthActuationError("illegal_httpauth")
        return "AUTH"
    if upper.startswith("QOP="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpauthActuationError("illegal_httpauth")
        return "DIGEST"
    raise HttpauthActuationError("illegal_httpauth")


def parse_httpauth(text: str) -> str:
    """Parse RFC 2617 DAV auth extensions into AUTH or DIGEST."""

    raw = str(text or "").strip()
    if not raw:
        raise HttpauthActuationError("illegal_httpauth")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"AUTH", "SCHEME", "HTTPAUTH"}:
        return "AUTH"
    if upper in {"DIGEST", "QOP", "DIGEST"}:
        return "DIGEST"
    if upper.startswith("SCHEME="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpauthActuationError("illegal_httpauth")
        return "AUTH"
    if upper.startswith("QOP="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpauthActuationError("illegal_httpauth")
        return "DIGEST"
    raise HttpauthActuationError("illegal_httpauth")


def encode_httpauth_header(policy: str | Sequence[str]) -> bytes:
    """RFC 2617 DAV field as bytes."""

    return serialize_httpauth(policy).encode("ascii")


def parse_httpauth_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_httpauth(field_value) if field_value else DEFAULT_AUTH
    return {
        "field_value": field_value,
        "policy": policy,
        "header": AUTH_HEADER,
        "directive": str(policy),
        "auth": str(policy) == "AUTH",
        "digest": str(policy) == "DIGEST",
    }


def canonical_auth(identity: str, nonceid: int) -> str:
    """RFC 2617 AUTH advertisement bound to identity and nonceid."""

    return (
        f"{serialize_httpauth(DEFAULT_AUTH)}, "
        f"auth={ascii_serialize_httpauth_directive()}, "
        f"identity={identity}, nonceid={int(nonceid) & 0xFFFFFFFF}"
    )


def canonical_digest(identity: str, nonceid: int, authdigest: int | None = None) -> str:
    """RFC 2617 DIGEST confirmation of the stored digest policy."""

    digest = ""
    if authdigest is not None:
        digest = f", authdigest={int(authdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_httpauth(DIGEST_POLICY)}, "
        f"digest={ascii_serialize_httpauth_directive(digest=True)}, "
        f"identity={identity}, nonceid={int(nonceid) & 0xFFFFFFFF}{digest}"
    )


def representation_digest(identity: str, nonceid: int, authdigest: int) -> str:
    return canonical_digest(identity, nonceid, authdigest)


def httpauth_matches(left: str, right: str) -> bool:
    return parse_httpauth(left) == parse_httpauth(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HttpauthActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HttpauthActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HttpauthActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HttpauthActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def auth_request(identity: str, nonceid: int) -> bytes:
    """HTTP AUTH that elicits RFC 2617 origin AUTH."""

    keyid = f"{int(nonceid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"AUTH /auth/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Nonce-Id: {int(nonceid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def digest_request(identity: str, nonceid: int, authdigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 2617 DIGEST confirmation of the stored digest policy."""

    keyid = f"{int(nonceid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if authdigest is not None:
        extra = f"Auth-Digest: {int(authdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"DIGEST /auth/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Nonce-Id: {int(nonceid) & 0xFFFFFFFF}\r\n"
        "Digest-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    httpauth_kind = "digest" if fields.get("digest-confirm") == "1" else "auth"
    upgrade_field = fields.get("www-authenticate") or fields.get("authorization") or fields.get("httpauth") or ""
    policy = parse_httpauth(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "httpauth_kind": httpauth_kind,
        "policy": policy,
        "nonceid": int(fields["nonce-id"]) if fields.get("nonce-id") else EMPTY_NONCEID,
        "authdigest": int(fields["auth-digest"]) if fields.get("auth-digest") else EMPTY_AUTHDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def auth_response(identity: str, nonceid: int, authdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 2617 origin AUTH, carrying the stored authdigest."""

    advertised = serialize_httpauth(DEFAULT_AUTH)
    payload = bytes(body or canonical_auth(identity, nonceid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"WWW-Authenticate: {advertised}\r\n"
        f"Nonce-Id: {int(nonceid) & 0xFFFFFFFF}\r\n"
        f"Auth-Digest: {int(authdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def digest_response(identity: str, nonceid: int, authdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 2617 DIGEST, carrying the stored DIGEST policy."""

    advertised = serialize_httpauth(DIGEST_POLICY)
    payload = bytes(body or representation_digest(identity, nonceid, authdigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"WWW-Authenticate: {advertised}\r\n"
        f"Nonce-Id: {int(nonceid) & 0xFFFFFFFF}\r\n"
        f"Auth-Digest: {int(authdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/http-digest\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise HttpauthActuationError("illegal_content_length") from error
    field_value = fields.get("www-authenticate") or fields.get("authorization") or fields.get("httpauth") or ""
    policy = parse_httpauth(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/http-digest" or policy == DIGEST_POLICY:
        status = 200
        httpauth_kind = "digest"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        httpauth_kind = "auth"
    else:
        status = 0
        httpauth_kind = "auth"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "httpauth_kind": httpauth_kind,
        "policy": policy,
        "nonceid": int(fields["nonce-id"]) if fields.get("nonce-id") else EMPTY_NONCEID,
        "authdigest": int(fields["auth-digest"]) if fields.get("auth-digest") else EMPTY_AUTHDIGEST,
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
        raise HttpauthActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise HttpauthActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise HttpauthActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HttpauthActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_nonceid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"nonceid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_nonceid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-nonceid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_authdigest(nonceid: int = EMPTY_NONCEID, token: str = SENTINEL) -> int:
    material = canonical_auth(token or SENTINEL, int(nonceid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_NONCEID = request_nonceid(SENTINEL)
DEFAULT_AUTHDIGEST = request_authdigest(DEFAULT_NONCEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    nonceid: int,
    authdigest: int,
    include_nonceid: bool = True,
) -> bytes:
    live_nonceid = int(nonceid) & 0xFFFFFFFF if include_nonceid else EMPTY_NONCEID
    live_digest = int(authdigest) & 0xFFFFFFFF if include_nonceid and live_nonceid else EMPTY_AUTHDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_nonceid) if live_nonceid else b""
    header = bytearray()
    header.append(AUTH_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_auth(
    *,
    identity: str,
    nonceid: int,
    authdigest: int | None = None,
    include_nonceid: bool = True,
) -> bytes:
    live_nonceid = int(nonceid) & 0xFFFFFFFF if include_nonceid else EMPTY_NONCEID
    live_digest = int(authdigest) if authdigest is not None else request_authdigest(live_nonceid, identity)
    return encode_packet(
        FRAME_AUTH,
        identity=identity,
        nonceid=live_nonceid,
        authdigest=live_digest,
        include_nonceid=include_nonceid,
    )


def encode_digest(
    *,
    identity: str,
    nonceid: int,
    authdigest: int | None = None,
    include_nonceid: bool = True,
) -> bytes:
    live_nonceid = int(nonceid) & 0xFFFFFFFF if include_nonceid else EMPTY_NONCEID
    live_digest = int(authdigest) if authdigest is not None else request_authdigest(live_nonceid, identity)
    return encode_packet(
        FRAME_DIGEST,
        identity=identity,
        nonceid=live_nonceid,
        authdigest=live_digest,
        include_nonceid=include_nonceid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HttpauthActuationError("short_packet")
    first = raw[0]
    if first != AUTH_FIRST:
        raise HttpauthActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise HttpauthActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == NONCEID_SIZE:
        live_nonceid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_nonceid = EMPTY_NONCEID
    else:
        raise HttpauthActuationError("illegal_nonceid")
    if offset >= len(raw):
        raise HttpauthActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_AUTH, FRAME_DIGEST}:
        raise HttpauthActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HttpauthActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HttpauthActuationError("checksum_failed")
    if len(payload) < 5:
        raise HttpauthActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HttpauthActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_nonceid = int(live_nonceid) != EMPTY_NONCEID
    has_authdigest = has_nonceid and int(live_digest) != EMPTY_AUTHDIGEST
    is_auth = frame_type == FRAME_AUTH
    is_digest = frame_type == FRAME_DIGEST
    return {
        "type": int(frame_type),
        "is_auth": is_auth,
        "is_digest": is_digest,
        "is_response": is_digest,
        "nonceid": int(live_nonceid),
        "has_nonceid": has_nonceid,
        "authdigest": int(live_digest),
        "has_authdigest": has_authdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC2617",
        "serialize_field": canonical_auth(identity, live_nonceid) if has_nonceid else "",
        "tls_field": canonical_digest(identity, live_nonceid, live_digest) if has_authdigest else "",
    }


class HttpauthClient:
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
            raise HttpauthActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_digest"] or not packet["is_response"]:
            raise HttpauthActuationError("authdigest_required")
        if not packet["has_nonceid"]:
            raise HttpauthActuationError("nonceid_required")
        if not packet["has_authdigest"]:
            raise HttpauthActuationError("authdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_authdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_authdigest:
            raise HttpauthActuationError("authdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "nonceid": int(reply.get("nonceid") or EMPTY_NONCEID),
            "identity": str(reply.get("identity") or ""),
            "authdigest": int(reply.get("authdigest") or EMPTY_AUTHDIGEST),
        }

    def report(
        self,
        identity: str,
        nonceid: int,
        authdigest: int = EMPTY_AUTHDIGEST,
        *,
        wait_authdigest: bool = True,
        include_nonceid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_digest(
            identity=identity,
            nonceid=nonceid,
            authdigest=authdigest or request_authdigest(nonceid, identity),
            include_nonceid=include_nonceid,
        )
        return self.exchange(packet, wait_authdigest=wait_authdigest)


class HttpauthSession:
    """NONCEID-gated loopback RFC 2617 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        nonceid_gate: int = DEFAULT_NONCEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.nonceid_gate = int(nonceid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.nonceid = EMPTY_NONCEID
        self.authdigest = EMPTY_AUTHDIGEST
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

    def store_nonceid_once(self, identity: str, nonceid: int, authdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(nonceid or EMPTY_NONCEID)
            live_digest = int(authdigest or EMPTY_AUTHDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.nonceid = live
                self.authdigest = live_digest or request_authdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.nonceid), int(self.authdigest)

    def read_nonceid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.nonceid), int(self.authdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "nonceid": EMPTY_NONCEID,
            "authdigest": EMPTY_AUTHDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _nonceid_missing(self) -> bool:
        return not int(self.nonceid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, nonceid: int, authdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_digest(
            identity=identity,
            nonceid=nonceid,
            authdigest=authdigest,
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
            except HttpauthActuationError:
                continue
            if not packet.get("is_auth") and not packet.get("is_digest"):
                continue
            if not packet.get("has_nonceid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_nonceid, stored_digest = self.store_nonceid_once(
                identity,
                int(packet.get("nonceid") or EMPTY_NONCEID),
                int(packet.get("authdigest") or EMPTY_AUTHDIGEST),
            )
            if not stored_name or not stored_nonceid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_auth"):
                    self.opened = True
                if packet.get("is_digest"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_nonceid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._nonceid_missing():
            return self._forbidden("missing_nonceid")
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
        do_auth: bool = True,
        do_digest: bool = True,
        do_authdigest: bool = True,
        replay: bool = True,
        use_nonceid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._nonceid_missing():
            return self._forbidden("missing_nonceid")
        live_token = str(token or SENTINEL)
        origin_nonceid = request_nonceid(live_token)
        origin_digest = request_authdigest(origin_nonceid, live_token)
        client: HttpauthClient | None = None
        independent: HttpauthClient | None = None
        try:
            client = HttpauthClient(self.host, int(self.port))
            if not do_auth:
                return self._conflict("auth_required")
            bind_packet = encode_auth(
                identity=live_token,
                nonceid=origin_nonceid,
                authdigest=origin_digest,
                include_nonceid=use_nonceid,
            )
            if not use_nonceid:
                try:
                    client.exchange(bind_packet, wait_authdigest=True)
                except HttpauthActuationError:
                    return self._conflict("nonceid_required")
                return self._conflict("nonceid_required")
            client.send(bind_packet)
            if not do_digest:
                return self._conflict("digest_required")
            proxy_packet = encode_digest(
                identity=live_token,
                nonceid=origin_nonceid,
                authdigest=origin_digest,
                include_nonceid=True,
            )
            if not do_authdigest:
                try:
                    client.exchange(proxy_packet, wait_authdigest=False)
                except HttpauthActuationError as error:
                    if str(error) == "authdigest_required":
                        return self._conflict("authdigest_required")
                    return self._conflict("authdigest_required")
                return self._conflict("authdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_authdigest=True)
            except HttpauthActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("nonceid_required")
                if reason == "authdigest_required":
                    return self._conflict("authdigest_required")
                return self._conflict("auth_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("auth_required")
            if int(reply.get("nonceid") or EMPTY_NONCEID) != origin_nonceid:
                return self._conflict("authdigest_required")
            if int(reply.get("authdigest") or EMPTY_AUTHDIGEST) != origin_digest:
                return self._conflict("authdigest_required")
            self.retrieved = True
            if replay:
                independent = HttpauthClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_nonceid(live_token),
                        request_authdigest(poll_nonceid(live_token), POLL_TOKEN),
                        wait_authdigest=True,
                    )
                except HttpauthActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_nonceid, stored_digest = self.read_nonceid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_nonceid != origin_nonceid
                    or stored_digest != origin_digest
                    or int(poll.get("nonceid") or EMPTY_NONCEID) != origin_nonceid
                    or int(poll.get("authdigest") or EMPTY_AUTHDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_nonceid}:{origin_digest}:{live_token}:{canonical_auth(live_token, origin_nonceid)}:{canonical_digest(live_token, origin_nonceid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "nonceid": origin_nonceid,
                "authdigest": origin_digest,
                "auth_frame": True,
                "digest_frame": True,
                "authdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "nonceid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_httpauth_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "nonceid": origin_nonceid,
                "authdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "auth_frame": True,
                "digest_frame": True,
                "authdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "nonceid_bound": True,
            }
        except (OSError, HttpauthActuationError) as error:
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
        live = independent_httpauth_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "nonceid": int(live.get("nonceid") or EMPTY_NONCEID),
            "authdigest": int(live.get("authdigest") or EMPTY_AUTHDIGEST),
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


def call_httpauth_tool(session: HttpauthSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one auth tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_auth = True if arguments.get("auth") is None else bool(arguments.get("auth"))
    do_digest = True if arguments.get("digest") is None else bool(arguments.get("digest"))
    do_authdigest = True if arguments.get("authdigest") is None else bool(arguments.get("authdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_nonceid = True if arguments.get("use_nonceid") is None else bool(arguments.get("use_nonceid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_auth=do_auth,
            do_digest=do_digest,
            do_authdigest=do_authdigest,
            replay=replay,
            use_nonceid=use_nonceid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HttpauthActuationError(f"unsupported httpauth action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_httpauth_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed auth authdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "nonceid": EMPTY_NONCEID,
        "authdigest": EMPTY_AUTHDIGEST,
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
            "auth_frame",
            "digest_frame",
            "authdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "nonceid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    nonceid = int(payload.get("nonceid") or EMPTY_NONCEID)
    authdigest = int(payload.get("authdigest") or EMPTY_AUTHDIGEST)
    dual = port > 0 and bool(nonceid) and bool(authdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "nonceid": nonceid,
        "authdigest": authdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "auth_frame": payload.get("auth_frame") is True,
        "digest_frame": payload.get("digest_frame") is True,
        "authdigest_response": payload.get("authdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "nonceid_bound": payload.get("nonceid_bound") is True,
    }


def run_httpauth_workflow(
    *,
    with_nonceid: bool = True,
    skip_bind: bool = False,
    do_auth: bool = True,
    do_digest: bool = True,
    do_authdigest: bool = True,
    replay: bool = True,
    use_nonceid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2617 AUTH/DIGEST nonceid cycle workflow."""

    descriptor = httpauth_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPAUTH_TOOL_PROVIDER),
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
        raise HttpauthActuationError(f"httpauth tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="httpauth-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HttpauthSession(out, nonceid_gate=DEFAULT_NONCEID if with_nonceid else EMPTY_NONCEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "auth": do_auth,
            "digest": do_digest,
            "authdigest": do_authdigest,
            "replay": replay,
            "use_nonceid": use_nonceid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_httpauth_tool(session, arguments))
            except HttpauthActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_httpauth_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_nonceid
        and not skip_bind
        and do_auth
        and do_digest
        and do_authdigest
        and replay
        and use_nonceid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "httpauth_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_nonceid": with_nonceid,
        "skip_bind": skip_bind,
        "auth_frame": do_auth,
        "digest": do_digest,
        "authdigest": do_authdigest,
        "replay": replay,
        "use_nonceid": use_nonceid,
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
        "nonceid_value": int(publish_result.get("nonceid") or independent.get("nonceid") or EMPTY_NONCEID),
        "authdigest_value": int(publish_result.get("authdigest") or independent.get("authdigest") or EMPTY_AUTHDIGEST),
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
        "nonceid": int(trace_body["nonceid_value"] or EMPTY_NONCEID),
        "authdigest": int(trace_body["authdigest_value"] or EMPTY_AUTHDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_nonceid": with_nonceid,
        "skip_bind": skip_bind,
        "auth_cycle": do_auth,
        "digest_cycle": do_digest,
        "authdigest_cycle": do_authdigest,
        "replay": replay,
        "use_nonceid": use_nonceid,
    }


def verify_httpauth_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_httpauth_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    nonceid = int(trace.get("nonceid_value") or independent.get("nonceid") or EMPTY_NONCEID)
    authdigest = int(trace.get("authdigest_value") or independent.get("authdigest") or EMPTY_AUTHDIGEST)
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
        "auth_frame": independent.get("auth_frame") is True,
        "digest_frame": independent.get("digest_frame") is True,
        "authdigest_response": independent.get("authdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "nonceid_bound": independent.get("nonceid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "authdigest_recorded": (
            port > 0
            and nonceid == DEFAULT_NONCEID
            and authdigest == DEFAULT_AUTHDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def httpauth_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.httpauth_actuation import "
        "builtin_httpauth_actuation_proof; r=builtin_httpauth_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='httpauth_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_httpauth_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTPAUTH_ACTUATION_ID,
        name="First-class RFC 2617 HTTP Authentication AUTH/DIGEST actuation",
        description=(
            "Missions that require a httpauth tool can opt the httpauth provider in, "
            "bind a loopback RFC 2617 HTTP Authentication endpoint, complete a AUTH "
            "with a non-empty nonceid, lockstep a DIGEST that carries the "
            "stored authdigest, independently poll the stored authdigest "
            "on a later socket, and seal a digest-chained authdigest. Default "
            "routing stays fail-closed; a missing nonceid keeps the hole "
            "falsifiable, and skip-AUTH/DIGEST/AUTHDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.httpauth_actuation:builtin_httpauth_actuation_proof",
        proof_command=httpauth_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.httptls-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/httpauth_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/httptls_actuation.py",
            "src/blackhole_agent/tcn_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required httpauth tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 2617 daemon, speaks a "
            "AUTH then DIGEST over HTTP Authentication with a non-empty nonceid and "
            "authdigest, independently polls the stored authdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 2817 Upgrading to TLS Within HTTP/1.1 lockstep is proved. "
            "Missing nonceids, skip-AUTH, skip-DIGEST, skip-authdigest, skip-REPLAY, "
            "and a AUTH aimed without a nonceid stay fail-closed. "
            "Later genesis can take RFC 2295 Transparent Content Negotiation ALTERNATES/CHOICE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("httpauth", "rfc2617", "http", "nonceid", "authdigest", "auth", "digest", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T003509Z-774dcbb7",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_httpauth_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2617 auth lockstep actuation seals a authdigest."""

    from blackhole_agent.httptls_actuation import (
        HTTPTLS_ACTUATION_GOAL,
        HTTPTLS_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
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
    checks["denylists_self"] = HTTPAUTH_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTPAUTH_ACTUATION_GOAL) == (
        HTTPAUTH_ACTUATION_ID,
    )
    checks["leftover_text_binds_httpauth"] = leftover_marker_ids(HTTPAUTH_LEFTOVER) == (
        HTTPAUTH_ACTUATION_ID,
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
        (HTTPTLS_ACTUATION_GOAL, HTTPTLS_ACTUATION_ID, "httptls"),
        (TCN_ACTUATION_GOAL, TCN_ACTUATION_ID, "tcn"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_httpauth"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"httpauth_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTPAUTH_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTPAUTH_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_httpauth(DEFAULT_AUTH)
    rebuilt = serialize_httpauth(parse_httpauth(advertised))
    preloaded = parse_httpauth(RFC_HTTPAUTH_DIGEST)
    header = encode_httpauth_header(DEFAULT_AUTH)
    parsed_header = parse_httpauth_header(header)
    asked = parse_http_request(auth_request(SENTINEL, DEFAULT_NONCEID))
    preload_req = parse_http_request(digest_request(SENTINEL, DEFAULT_NONCEID, DEFAULT_AUTHDIGEST))
    got = parse_http_response(auth_response(SENTINEL, DEFAULT_NONCEID, DEFAULT_AUTHDIGEST))
    preload_reply = parse_http_response(
        digest_response(SENTINEL, DEFAULT_NONCEID, DEFAULT_AUTHDIGEST)
    )
    checks["httpauth_roundtrip"] = (
        parse_httpauth(advertised) == DEFAULT_AUTH
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_AUTH_FIELD
        and is_token("AUTH") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_AUTH_FIELD
        and parsed_header["policy"] == DEFAULT_AUTH
        and parsed_header["header"] == AUTH_HEADER
        and parsed_header["auth"] is True
        and parsed_header["digest"] is False
        and preloaded == DIGEST_POLICY
        and ascii_serialize_httpauth_directive() == RFC_AUTH_DIRECTIVE
        and httpauth_directive_pair() == ("scheme", "Digest")
        and RFC_AUTH_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_httpauth(DIGEST_POLICY) == RFC_HTTPAUTH_DIGEST
        and DEFAULT_AUTHDIGEST == request_authdigest(DEFAULT_NONCEID, SENTINEL)
        and "authdigest=" in canonical_digest(SENTINEL, DEFAULT_NONCEID, DEFAULT_AUTHDIGEST)
        and canonical_auth(SENTINEL, DEFAULT_NONCEID).startswith("AUTH")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "AUTH"
        and asked["httpauth_kind"] == "auth"
        and asked["nonceid"] == DEFAULT_NONCEID
        and preload_req["httpauth_kind"] == "digest"
        and preload_req["authdigest"] == DEFAULT_AUTHDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["httpauth_kind"] == "auth"
        and preload_reply["httpauth_kind"] == "digest"
        and got["policy"] == DEFAULT_AUTH
        and preload_reply["policy"] == DIGEST_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["authdigest"] == DEFAULT_AUTHDIGEST
        and preload_reply["authdigest"] == DEFAULT_AUTHDIGEST
        and httpauth_matches(serialize_httpauth(got["policy"]), advertised)
    )

    checks["catalog_names_httpauth"] = (
        len(catalog) > 96
        and catalog[96]["id"] == HTTPAUTH_ACTUATION_ID
        and catalog[95]["id"] == HTTPTLS_ACTUATION_ID
        and catalog[96]["source"] == "genesis_bind_httpauth"
    )
    checks["catalog_names_tcn"] = (
        len(catalog) > 97
        and catalog[97]["id"] == TCN_ACTUATION_ID
        and catalog[97]["source"] == "genesis_bind_tcn"
    )
    family = capability_family(HTTPAUTH_ACTUATION_GOAL)
    checks["family_is_httpauth"] = "httpauth" in family
    checks["family_is_httpauth_surface"] = "httpauth" in family
    checks["family_is_nonceid"] = "nonceid" in family
    checks["family_is_rfc2617"] = "rfc2617" in family
    checks["family_is_authdigest"] = "authdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_tcn"] = (
        "tcn" not in family
        and "rfc2295" not in family
        and "variantid" not in family
        and "choicedigest" not in family
    )
    checks["family_is_not_httptls"] = (
        "httptls" not in family
        and "httptl" not in family
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
    packed = encode_auth(identity=SENTINEL, nonceid=DEFAULT_NONCEID, authdigest=DEFAULT_AUTHDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_auth"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_nonceid"] is True
        and parsed["nonceid"] == DEFAULT_NONCEID
        and parsed["authdigest"] == DEFAULT_AUTHDIGEST
        and parsed["is_response"] is False
        and parsed["is_digest"] is False
        and parsed["type"] == FRAME_AUTH
        and parsed["first_byte"] == AUTH_FIRST
    )
    shook = encode_digest(
        identity=SENTINEL,
        nonceid=DEFAULT_NONCEID,
        authdigest=DEFAULT_AUTHDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_digest"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_auth"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["nonceid"] == DEFAULT_NONCEID
        and answer_parsed["authdigest"] == DEFAULT_AUTHDIGEST
        and answer_parsed["has_authdigest"] is True
        and answer_parsed["type"] == FRAME_DIGEST
        and answer_parsed["first_byte"] == AUTH_FIRST
    )
    bare = encode_auth(identity=SENTINEL, nonceid=DEFAULT_NONCEID, include_nonceid=False)
    checks["missing_nonceid_is_unauthed"] = parse_message(bare)["has_nonceid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    httpauth_signature = semantic_signature(HTTPAUTH_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(httpauth_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_httpauth = ToolDescriptor(name="remote_httpauth", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_httpauth)
    checks["naive_mcp_httpauth_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = httpauth_tool_descriptor()
    default_httpauth = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPAUTH_TOOL_PROVIDER),
    )
    checks["default_httpauth_provider_is_unsupported"] = (
        default_httpauth.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTPAUTH_TOOL_PROVIDER}" in default_httpauth.reasons
    )
    checks["opted_in_httpauth_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_httpauth],
        required_tool_names=("local_memory", "httpauth"),
    )
    checks["naive_preflight_missing_httpauth"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["httpauth"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "httpauth"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPAUTH_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "httpauth" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="httpauth-actuation-") as tmp:
        root = Path(tmp)
        missing = run_httpauth_workflow(with_nonceid=False, output_dir=root / "missing")
        skip_bind = run_httpauth_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_auth = run_httpauth_workflow(do_auth=False, output_dir=root / "skip-upgrade")
        skip_digest = run_httpauth_workflow(do_digest=False, output_dir=root / "skip-tls")
        skip_authdigest = run_httpauth_workflow(do_authdigest=False, output_dir=root / "skip-authdigest")
        skip_replay = run_httpauth_workflow(replay=False, output_dir=root / "skip-replay")
        skip_nonceid = run_httpauth_workflow(use_nonceid=False, output_dir=root / "skip-nonceid")
        live = run_httpauth_workflow(output_dir=root / "live")
        verify = verify_httpauth_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_httpauth_trace(clone)
        checks["naive_without_nonceid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_nonceid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_auth_stays_empty"] = (
            skip_auth["ok"] is False
            and skip_auth["error"] == "auth_required"
            and skip_auth["final_status"] == 409
            and skip_auth["payload_exists"] is False
        )
        checks["skip_digest_stays_empty"] = (
            skip_digest["ok"] is False
            and skip_digest["error"] == "digest_required"
            and skip_digest["final_status"] == 409
            and skip_digest["payload_exists"] is False
        )
        checks["skip_authdigest_stays_empty"] = (
            skip_authdigest["ok"] is False
            and skip_authdigest["error"] == "authdigest_required"
            and skip_authdigest["final_status"] == 409
            and skip_authdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_nonceid_stays_empty"] = (
            skip_nonceid["ok"] is False
            and skip_nonceid["error"] == "nonceid_required"
            and skip_nonceid["final_status"] == 409
            and skip_nonceid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_authdigest"] = (
            int(live.get("nonceid") or 0) == DEFAULT_NONCEID
            and int(live.get("authdigest") or 0) == DEFAULT_AUTHDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_nonceid_encode_digest_authdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_auth["ok"] is False
            and skip_digest["ok"] is False
            and skip_authdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_nonceid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="httpauth-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTPAUTH_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_httpauth"] = (
        live_goal == HTTPAUTH_ACTUATION_GOAL
        and HTTPAUTH_ACTUATION_ID in live_done
        and live_source == "genesis_bind_httpauth"
    )

    with tempfile.TemporaryDirectory(prefix="httpauth-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTPAUTH_LEFTOVER, root)
        register_catalog_proved(root, HTTPAUTH_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTPAUTH_LEFTOVER, root)
        after = leftover_is_open(HTTPAUTH_LEFTOVER, root)
    checks["httpauth_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_httpauth_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTPAUTH_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_httpauth_actuation_capability()
    return {
        "ok": ok,
        "action": "httpauth_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTPAUTH_ACTUATION_GOAL,
        "done_when": HTTPAUTH_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
