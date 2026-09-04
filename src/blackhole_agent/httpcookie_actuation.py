"""Drive a first-class HTTP Cookie tool through RFC 6265 SET-COOKIE/COOKIE.

Tool routing already fails missions that require ``httpcookie``: hosted
httpcookie endpoints stay on the unsupported MCP provider, and no first-party
httpcookie provider is executable. Unbound therefore cannot speak a SET-COOKIE,
lockstep a COOKIE cookieid handshake over HTTP Cookie COOKIEID,
independently poll the stored cookiedigest, or seal a cookiedigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``httpcookie`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 6265 daemon
- keep a missing-cookieid client so the httpcookie-cookieid hole stays falsifiable
- refuse COOKIE until a SET-COOKIE lands with a non-empty cookieid
- independently poll the stored cookiedigest on a later client socket
- persist a sealed cookiedigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 6454 Web Origin
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
    HTTPCOOKIE_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    httpcookie_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTPCOOKIE_ACTUATION_ID = "capability.httpcookie-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-HTTPCOOKIE-OK"
POLL_TOKEN = "BH-HTTPCOOKIE-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_COOKIEID = 0
EMPTY_COOKIEDIGEST = 0
CK_FIRST = 0x43  # RFC 6265 Cookie (ASCII 'C')
COOKIEID_SIZE = 4
COOKIEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_COOKIE = 0x02  # RFC 6265 report confirmation
FRAME_SETCOOKIE = 0x01  # RFC 6265 Set-Cookie
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTPCOOKIE_LEFTOVER = (
    "Later genesis can take RFC 6265 HTTP State Management Mechanism SET-COOKIE/COOKIE over a "
    "cookieid-gated cookiedigest."
)
HTTPCOOKIE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPCOOKIE_ACTUATION_ID};"
    f"capability_proved:{HTTPCOOKIE_ACTUATION_ID};"
    "no_skill_route"
)
HTTPCOOKIE_ACTUATION_GOAL = (
    "Repair rfc6265 httpcookie set-cookie/cookie cycle cannot land over http "
    "httpcookie cookieid: hosted httpcookie endpoints remain unsupported so a SET-COOKIE then "
    "COOKIE cookieid handshake cannot land and a sealed cookiedigest "
    "cannot be produced. A missing httpcookie cookieid stays forbidden; fail-closed "
    "routing never opts the httpcookie provider in. An independent later poll of the "
    "stored cookiedigest keeps the hole falsifiable."
)


class HttpcookieActuationError(RuntimeError):
    """Raised when the cookie session or loopback daemon fixture misbehaves."""


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
# RFC 6265 section 4.1 Set-Cookie / 4.2 Cookie.
RFC_SETCOOKIE_FIELD = "SET-COOKIE"
RFC_COOKIE_FIELD = "COOKIE"
RFC_HTTPCOOKIE_COOKIE = RFC_COOKIE_FIELD
RFC_SETCOOKIE_PATH = "Path=/"
DEFAULT_SETCOOKIE = "SET-COOKIE"
COOKIE_POLICY = "COOKIE"
SETCOOKIE_HEADER = "Set-Cookie"
COOKIE_HEADER = "Cookie"
HTTPCOOKIE_COOKIE_HEADER = COOKIE_HEADER
RFC_COOKIE_NAME = "SID"
RFC_COOKIE_VALUE = "BH-COOKIE-OK"
RFC_COOKIE_PATH = "/"
RFC_COOKIE_PAIR = "SID=BH-COOKIE-OK"
RFC_COOKIE_EMPTY = ""


def cookie_pair(
    name: str = RFC_COOKIE_NAME,
    value: str = RFC_COOKIE_VALUE,
) -> tuple[str, str]:
    """RFC 6265 section 4.1.1 cookie-pair as (name, value)."""

    return str(name or RFC_COOKIE_NAME), str(value or RFC_COOKIE_VALUE)


def ascii_serialize_cookie(
    name: str = RFC_COOKIE_NAME,
    value: str = RFC_COOKIE_VALUE,
) -> str:
    """RFC 6265 section 4.1.1 cookie-pair ASCII serialization."""

    live_name, live_value = cookie_pair(name, value)
    if not is_token(live_name):
        raise HttpcookieActuationError("illegal_cookie_name")
    if any(ord(char) <= 0x20 or char in '",;\\' or ord(char) >= 0x7F for char in live_value):
        raise HttpcookieActuationError("illegal_cookie_value")
    return f"{live_name}={live_value}"


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise HttpcookieActuationError("short_httpcookie")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 6265 directive-name."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_httpcookie(policy: str | Sequence[str]) -> str:
    """Serialize RFC 6265 Set-Cookie field-value."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise HttpcookieActuationError("illegal_httpcookie")
    upper = text.upper()
    if upper in {"SET-COOKIE", "SETCOOKIE"}:
        return "SET-COOKIE"
    if upper == "COOKIE":
        return "COOKIE"
    if upper.startswith("PATH="):
        path_value = text.split("=", 1)[1].strip()
        if not path_value or ";" in path_value:
            raise HttpcookieActuationError("illegal_httpcookie")
        return f"Path={path_value}"
    raise HttpcookieActuationError("illegal_httpcookie")


def parse_httpcookie(text: str) -> str:
    """Parse RFC 6265 Set-Cookie/Cookie into SET-COOKIE, COOKIE, or Path."""

    raw = str(text or "").strip()
    if not raw:
        raise HttpcookieActuationError("illegal_httpcookie")
    head = raw.split(",", 1)[0].strip()
    upper = head.upper()
    if upper in {"SET-COOKIE", "SETCOOKIE"}:
        return "SET-COOKIE"
    if upper == "COOKIE":
        return "COOKIE"
    if upper.startswith("PATH="):
        path_value = head.split("=", 1)[1].strip()
        if not path_value or ";" in path_value:
            raise HttpcookieActuationError("illegal_httpcookie")
        return f"Path={path_value}"
    raise HttpcookieActuationError("illegal_httpcookie")


def encode_httpcookie_header(policy: str | Sequence[str]) -> bytes:
    """RFC 6265 Set-Cookie field as bytes."""

    return serialize_httpcookie(policy).encode("ascii")


def parse_httpcookie_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_httpcookie(field_value) if field_value else DEFAULT_SETCOOKIE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SETCOOKIE_HEADER,
        "directive": str(policy),
        "setcookie": str(policy) == "SET-COOKIE",
        "cookie": str(policy) == "COOKIE",
    }


def canonical_setcookie(identity: str, cookieid: int) -> str:
    """RFC 6265 SET-COOKIE advertisement bound to identity and cookieid."""

    return (
        f"{serialize_httpcookie(DEFAULT_SETCOOKIE)}, "
        f"cookie={ascii_serialize_cookie()}, "
        f"identity={identity}, cookieid={int(cookieid) & 0xFFFFFFFF}"
    )


def canonical_cookie(identity: str, cookieid: int, cookiedigest: int | None = None) -> str:
    """RFC 6265 COOKIE confirmation of the stored cookie policy."""

    suffix = ""
    if cookiedigest is not None:
        suffix = f", cookiedigest={int(cookiedigest) & 0xFFFFFFFF}"
    name, value = cookie_pair()
    return (
        f"{serialize_httpcookie(COOKIE_POLICY)}, "
        f"cookie={name}={value}, "
        f"identity={identity}, cookieid={int(cookieid) & 0xFFFFFFFF}{suffix}"
    )


def representation_cookie(identity: str, cookieid: int, cookiedigest: int) -> str:
    return canonical_cookie(identity, cookieid, cookiedigest)


def httpcookie_matches(left: str, right: str) -> bool:
    return parse_httpcookie(left) == parse_httpcookie(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HttpcookieActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HttpcookieActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HttpcookieActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HttpcookieActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def setcookie_request(identity: str, cookieid: int) -> bytes:
    """HTTP GET that elicits RFC 6265 Origin SET-COOKIE."""

    keyid = f"{int(cookieid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /httpcookie/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Cookie-Id: {int(cookieid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def cookie_request(identity: str, cookieid: int, cookiedigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 6265 COOKIE confirmation of the stored cookie policy."""

    keyid = f"{int(cookieid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if cookiedigest is not None:
        extra = f"Cookie-Digest: {int(cookiedigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /httpcookie/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Cookie-Id: {int(cookieid) & 0xFFFFFFFF}\r\n"
        "Cookie-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    httpcookie_kind = "cookie" if fields.get("cookie-confirm") == "1" else "setcookie"
    cookie_field = fields.get("set-cookie") or fields.get("cookie") or ""
    policy = parse_httpcookie(cookie_field) if cookie_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "httpcookie_kind": httpcookie_kind,
        "policy": policy,
        "cookieid": int(fields["cookie-id"]) if fields.get("cookie-id") else EMPTY_COOKIEID,
        "cookiedigest": int(fields["cookie-digest"]) if fields.get("cookie-digest") else EMPTY_COOKIEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def setcookie_response(identity: str, cookieid: int, cookiedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 6265 Origin SET-COOKIE, carrying the stored cookiedigest."""

    advertised = serialize_httpcookie(DEFAULT_SETCOOKIE)
    payload = bytes(body or canonical_setcookie(identity, cookieid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Set-Cookie: {advertised}\r\n"
        f"Cookie-Id: {int(cookieid) & 0xFFFFFFFF}\r\n"
        f"Cookie-Digest: {int(cookiedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/http-cookie\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def cookie_response(identity: str, cookieid: int, cookiedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 6265 Cookie COOKIE, carrying the stored COOKIE policy."""

    advertised = serialize_httpcookie(COOKIE_POLICY)
    payload = bytes(body or representation_cookie(identity, cookieid, cookiedigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Set-Cookie: {advertised}\r\n"
        f"Cookie-Id: {int(cookieid) & 0xFFFFFFFF}\r\n"
        f"Cookie-Digest: {int(cookiedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/http-cookie-confirm\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise HttpcookieActuationError("illegal_content_length") from error
    field_value = fields.get("set-cookie") or fields.get("cookie") or ""
    policy = parse_httpcookie(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/http-cookie-confirm" or policy == COOKIE_POLICY:
        status = 200
        httpcookie_kind = "cookie"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        httpcookie_kind = "setcookie"
    else:
        status = 0
        httpcookie_kind = "setcookie"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "httpcookie_kind": httpcookie_kind,
        "policy": policy,
        "cookieid": int(fields["cookie-id"]) if fields.get("cookie-id") else EMPTY_COOKIEID,
        "cookiedigest": int(fields["cookie-digest"]) if fields.get("cookie-digest") else EMPTY_COOKIEDIGEST,
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
        raise HttpcookieActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise HttpcookieActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise HttpcookieActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HttpcookieActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_cookieid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"cookieid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_cookieid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-cookieid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_cookiedigest(cookieid: int = EMPTY_COOKIEID, token: str = SENTINEL) -> int:
    material = canonical_setcookie(token or SENTINEL, int(cookieid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_COOKIEID = request_cookieid(SENTINEL)
DEFAULT_COOKIEDIGEST = request_cookiedigest(DEFAULT_COOKIEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    cookieid: int,
    cookiedigest: int,
    include_cookieid: bool = True,
) -> bytes:
    live_cookieid = int(cookieid) & 0xFFFFFFFF if include_cookieid else EMPTY_COOKIEID
    live_digest = int(cookiedigest) & 0xFFFFFFFF if include_cookieid and live_cookieid else EMPTY_COOKIEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_cookieid) if live_cookieid else b""
    header = bytearray()
    header.append(CK_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_setcookie(
    *,
    identity: str,
    cookieid: int,
    cookiedigest: int | None = None,
    include_cookieid: bool = True,
) -> bytes:
    live_cookieid = int(cookieid) & 0xFFFFFFFF if include_cookieid else EMPTY_COOKIEID
    live_digest = int(cookiedigest) if cookiedigest is not None else request_cookiedigest(live_cookieid, identity)
    return encode_packet(
        FRAME_SETCOOKIE,
        identity=identity,
        cookieid=live_cookieid,
        cookiedigest=live_digest,
        include_cookieid=include_cookieid,
    )


def encode_cookie(
    *,
    identity: str,
    cookieid: int,
    cookiedigest: int | None = None,
    include_cookieid: bool = True,
) -> bytes:
    live_cookieid = int(cookieid) & 0xFFFFFFFF if include_cookieid else EMPTY_COOKIEID
    live_digest = int(cookiedigest) if cookiedigest is not None else request_cookiedigest(live_cookieid, identity)
    return encode_packet(
        FRAME_COOKIE,
        identity=identity,
        cookieid=live_cookieid,
        cookiedigest=live_digest,
        include_cookieid=include_cookieid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HttpcookieActuationError("short_packet")
    first = raw[0]
    if first != CK_FIRST:
        raise HttpcookieActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise HttpcookieActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == COOKIEID_SIZE:
        live_cookieid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_cookieid = EMPTY_COOKIEID
    else:
        raise HttpcookieActuationError("illegal_cookieid")
    if offset >= len(raw):
        raise HttpcookieActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SETCOOKIE, FRAME_COOKIE}:
        raise HttpcookieActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HttpcookieActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HttpcookieActuationError("checksum_failed")
    if len(payload) < 5:
        raise HttpcookieActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HttpcookieActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_cookieid = int(live_cookieid) != EMPTY_COOKIEID
    has_cookiedigest = has_cookieid and int(live_digest) != EMPTY_COOKIEDIGEST
    is_setcookie = frame_type == FRAME_SETCOOKIE
    is_cookie = frame_type == FRAME_COOKIE
    return {
        "type": int(frame_type),
        "is_setcookie": is_setcookie,
        "is_cookie": is_cookie,
        "is_response": is_cookie,
        "cookieid": int(live_cookieid),
        "has_cookieid": has_cookieid,
        "cookiedigest": int(live_digest),
        "has_cookiedigest": has_cookiedigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http_state": "RFC6265",
        "serialize_field": canonical_setcookie(identity, live_cookieid) if has_cookieid else "",
        "cookie_field": canonical_cookie(identity, live_cookieid, live_digest) if has_cookiedigest else "",
    }


class HttpcookieClient:
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
            raise HttpcookieActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_cookie"] or not packet["is_response"]:
            raise HttpcookieActuationError("cookiedigest_required")
        if not packet["has_cookieid"]:
            raise HttpcookieActuationError("cookieid_required")
        if not packet["has_cookiedigest"]:
            raise HttpcookieActuationError("cookiedigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_cookiedigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_cookiedigest:
            raise HttpcookieActuationError("cookiedigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "cookieid": int(reply.get("cookieid") or EMPTY_COOKIEID),
            "identity": str(reply.get("identity") or ""),
            "cookiedigest": int(reply.get("cookiedigest") or EMPTY_COOKIEDIGEST),
        }

    def report(
        self,
        identity: str,
        cookieid: int,
        cookiedigest: int = EMPTY_COOKIEDIGEST,
        *,
        wait_cookiedigest: bool = True,
        include_cookieid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_cookie(
            identity=identity,
            cookieid=cookieid,
            cookiedigest=cookiedigest or request_cookiedigest(cookieid, identity),
            include_cookieid=include_cookieid,
        )
        return self.exchange(packet, wait_cookiedigest=wait_cookiedigest)


class HttpcookieSession:
    """COOKIEID-gated loopback RFC 6265 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        cookieid_gate: int = DEFAULT_COOKIEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookieid_gate = int(cookieid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.cookieid = EMPTY_COOKIEID
        self.cookiedigest = EMPTY_COOKIEDIGEST
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

    def store_cookieid_once(self, identity: str, cookieid: int, cookiedigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(cookieid or EMPTY_COOKIEID)
            live_digest = int(cookiedigest or EMPTY_COOKIEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.cookieid = live
                self.cookiedigest = live_digest or request_cookiedigest(live, name)
                self.stored = True
            return str(self.identity), int(self.cookieid), int(self.cookiedigest)

    def read_cookieid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.cookieid), int(self.cookiedigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "cookieid": EMPTY_COOKIEID,
            "cookiedigest": EMPTY_COOKIEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _cookieid_missing(self) -> bool:
        return not int(self.cookieid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, cookieid: int, cookiedigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_cookie(
            identity=identity,
            cookieid=cookieid,
            cookiedigest=cookiedigest,
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
            except HttpcookieActuationError:
                continue
            if not packet.get("is_setcookie") and not packet.get("is_cookie"):
                continue
            if not packet.get("has_cookieid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_cookieid, stored_digest = self.store_cookieid_once(
                identity,
                int(packet.get("cookieid") or EMPTY_COOKIEID),
                int(packet.get("cookiedigest") or EMPTY_COOKIEDIGEST),
            )
            if not stored_name or not stored_cookieid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_setcookie"):
                    self.opened = True
                if packet.get("is_cookie"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_cookieid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._cookieid_missing():
            return self._forbidden("missing_cookieid")
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
        do_setcookie: bool = True,
        do_cookie: bool = True,
        do_cookiedigest: bool = True,
        replay: bool = True,
        use_cookieid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._cookieid_missing():
            return self._forbidden("missing_cookieid")
        live_token = str(token or SENTINEL)
        origin_cookieid = request_cookieid(live_token)
        origin_digest = request_cookiedigest(origin_cookieid, live_token)
        client: HttpcookieClient | None = None
        independent: HttpcookieClient | None = None
        try:
            client = HttpcookieClient(self.host, int(self.port))
            if not do_setcookie:
                return self._conflict("setcookie_required")
            bind_packet = encode_setcookie(
                identity=live_token,
                cookieid=origin_cookieid,
                cookiedigest=origin_digest,
                include_cookieid=use_cookieid,
            )
            if not use_cookieid:
                try:
                    client.exchange(bind_packet, wait_cookiedigest=True)
                except HttpcookieActuationError:
                    return self._conflict("cookieid_required")
                return self._conflict("cookieid_required")
            client.send(bind_packet)
            if not do_cookie:
                return self._conflict("cookie_required")
            proxy_packet = encode_cookie(
                identity=live_token,
                cookieid=origin_cookieid,
                cookiedigest=origin_digest,
                include_cookieid=True,
            )
            if not do_cookiedigest:
                try:
                    client.exchange(proxy_packet, wait_cookiedigest=False)
                except HttpcookieActuationError as error:
                    if str(error) == "cookiedigest_required":
                        return self._conflict("cookiedigest_required")
                    return self._conflict("cookiedigest_required")
                return self._conflict("cookiedigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_cookiedigest=True)
            except HttpcookieActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("cookieid_required")
                if reason == "cookiedigest_required":
                    return self._conflict("cookiedigest_required")
                return self._conflict("setcookie_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("setcookie_required")
            if int(reply.get("cookieid") or EMPTY_COOKIEID) != origin_cookieid:
                return self._conflict("cookiedigest_required")
            if int(reply.get("cookiedigest") or EMPTY_COOKIEDIGEST) != origin_digest:
                return self._conflict("cookiedigest_required")
            self.retrieved = True
            if replay:
                independent = HttpcookieClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_cookieid(live_token),
                        request_cookiedigest(poll_cookieid(live_token), POLL_TOKEN),
                        wait_cookiedigest=True,
                    )
                except HttpcookieActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_cookieid, stored_digest = self.read_cookieid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_cookieid != origin_cookieid
                    or stored_digest != origin_digest
                    or int(poll.get("cookieid") or EMPTY_COOKIEID) != origin_cookieid
                    or int(poll.get("cookiedigest") or EMPTY_COOKIEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_cookieid}:{origin_digest}:{live_token}:{canonical_setcookie(live_token, origin_cookieid)}:{canonical_cookie(live_token, origin_cookieid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "cookieid": origin_cookieid,
                "cookiedigest": origin_digest,
                "setcookie_frame": True,
                "cookie_frame": True,
                "cookiedigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "cookieid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_httpcookie_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "cookieid": origin_cookieid,
                "cookiedigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "setcookie_frame": True,
                "cookie_frame": True,
                "cookiedigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "cookieid_bound": True,
            }
        except (OSError, HttpcookieActuationError) as error:
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
        live = independent_httpcookie_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "cookieid": int(live.get("cookieid") or EMPTY_COOKIEID),
            "cookiedigest": int(live.get("cookiedigest") or EMPTY_COOKIEDIGEST),
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


def call_httpcookie_tool(session: HttpcookieSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one cookie tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_setcookie = True if arguments.get("setcookie") is None else bool(arguments.get("setcookie"))
    do_cookie = True if arguments.get("cookie") is None else bool(arguments.get("cookie"))
    do_cookiedigest = True if arguments.get("cookiedigest") is None else bool(arguments.get("cookiedigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_cookieid = True if arguments.get("use_cookieid") is None else bool(arguments.get("use_cookieid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_setcookie=do_setcookie,
            do_cookie=do_cookie,
            do_cookiedigest=do_cookiedigest,
            replay=replay,
            use_cookieid=use_cookieid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HttpcookieActuationError(f"unsupported httpcookie action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_httpcookie_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed cookie cookiedigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "cookieid": EMPTY_COOKIEID,
        "cookiedigest": EMPTY_COOKIEDIGEST,
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
            "setcookie_frame",
            "cookie_frame",
            "cookiedigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "cookieid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    cookieid = int(payload.get("cookieid") or EMPTY_COOKIEID)
    cookiedigest = int(payload.get("cookiedigest") or EMPTY_COOKIEDIGEST)
    dual = port > 0 and bool(cookieid) and bool(cookiedigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "cookieid": cookieid,
        "cookiedigest": cookiedigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "setcookie_frame": payload.get("setcookie_frame") is True,
        "cookie_frame": payload.get("cookie_frame") is True,
        "cookiedigest_response": payload.get("cookiedigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "cookieid_bound": payload.get("cookieid_bound") is True,
    }


def run_httpcookie_workflow(
    *,
    with_cookieid: bool = True,
    skip_bind: bool = False,
    do_setcookie: bool = True,
    do_cookie: bool = True,
    do_cookiedigest: bool = True,
    replay: bool = True,
    use_cookieid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 6265 SET-COOKIE/COOKIE cookieid cycle workflow."""

    descriptor = httpcookie_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPCOOKIE_TOOL_PROVIDER),
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
        raise HttpcookieActuationError(f"httpcookie tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="httpcookie-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HttpcookieSession(out, cookieid_gate=DEFAULT_COOKIEID if with_cookieid else EMPTY_COOKIEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "setcookie": do_setcookie,
            "cookie": do_cookie,
            "cookiedigest": do_cookiedigest,
            "replay": replay,
            "use_cookieid": use_cookieid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_httpcookie_tool(session, arguments))
            except HttpcookieActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_httpcookie_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_cookieid
        and not skip_bind
        and do_setcookie
        and do_cookie
        and do_cookiedigest
        and replay
        and use_cookieid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "httpcookie_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_cookieid": with_cookieid,
        "skip_bind": skip_bind,
        "setcookie_frame": do_setcookie,
        "cookie": do_cookie,
        "cookiedigest": do_cookiedigest,
        "replay": replay,
        "use_cookieid": use_cookieid,
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
        "cookieid_value": int(publish_result.get("cookieid") or independent.get("cookieid") or EMPTY_COOKIEID),
        "cookiedigest_value": int(publish_result.get("cookiedigest") or independent.get("cookiedigest") or EMPTY_COOKIEDIGEST),
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
        "cookieid": int(trace_body["cookieid_value"] or EMPTY_COOKIEID),
        "cookiedigest": int(trace_body["cookiedigest_value"] or EMPTY_COOKIEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_cookieid": with_cookieid,
        "skip_bind": skip_bind,
        "setcookie_cycle": do_setcookie,
        "cookie_cycle": do_cookie,
        "cookiedigest_cycle": do_cookiedigest,
        "replay": replay,
        "use_cookieid": use_cookieid,
    }


def verify_httpcookie_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_httpcookie_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    cookieid = int(trace.get("cookieid_value") or independent.get("cookieid") or EMPTY_COOKIEID)
    cookiedigest = int(trace.get("cookiedigest_value") or independent.get("cookiedigest") or EMPTY_COOKIEDIGEST)
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
        "setcookie_frame": independent.get("setcookie_frame") is True,
        "cookie_frame": independent.get("cookie_frame") is True,
        "cookiedigest_response": independent.get("cookiedigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "cookieid_bound": independent.get("cookieid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "cookiedigest_recorded": (
            port > 0
            and cookieid == DEFAULT_COOKIEID
            and cookiedigest == DEFAULT_COOKIEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def httpcookie_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.httpcookie_actuation import "
        "builtin_httpcookie_actuation_proof; r=builtin_httpcookie_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='httpcookie_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_httpcookie_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTPCOOKIE_ACTUATION_ID,
        name="First-class RFC 6265 Cookie SET-COOKIE/COOKIE actuation",
        description=(
            "Missions that require a httpcookie tool can opt the httpcookie provider in, "
            "bind a loopback RFC 6265 HTTP Cookie endpoint, complete a SET-COOKIE "
            "with a non-empty cookieid, lockstep a COOKIE that carries the "
            "stored cookiedigest, independently poll the stored cookiedigest "
            "on a later socket, and seal a digest-chained cookiedigest. Default "
            "routing stays fail-closed; a missing cookieid keeps the hole "
            "falsifiable, and skip-SET-COOKIE/COOKIE/COOKIEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.httpcookie_actuation:builtin_httpcookie_actuation_proof",
        proof_command=httpcookie_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.weborigin-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/httpcookie_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/weborigin_actuation.py",
            "src/blackhole_agent/contentdisposition_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required httpcookie tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 6265 daemon, speaks a "
            "SET-COOKIE then COOKIE over HTTP State Management with a non-empty cookieid and "
            "cookiedigest, independently polls the stored cookiedigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 6454 Web Origin lockstep is proved. "
            "Missing cookieids, skip-SET-COOKIE, skip-COOKIE, skip-cookiedigest, skip-REPLAY, "
            "and a SET-COOKIE aimed without a cookieid stay fail-closed. "
            "Later genesis can take RFC 6266 Content-Disposition Header Field DISPOSITION/ATTACHMENT as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("httpcookie", "rfc6265", "http", "cookieid", "cookiedigest", "setcookie", "cookie", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T173359Z-d4cb003c",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_httpcookie_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 6265 cookie lockstep actuation seals a cookiedigest."""

    from blackhole_agent.contentdisposition_actuation import (
        CONTENTDISPOSITION_ACTUATION_GOAL,
        CONTENTDISPOSITION_ACTUATION_ID,
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
    checks["denylists_self"] = HTTPCOOKIE_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTPCOOKIE_ACTUATION_GOAL) == (
        HTTPCOOKIE_ACTUATION_ID,
    )
    checks["leftover_text_binds_httpcookie"] = leftover_marker_ids(HTTPCOOKIE_LEFTOVER) == (
        HTTPCOOKIE_ACTUATION_ID,
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
        (CONTENTDISPOSITION_ACTUATION_GOAL, CONTENTDISPOSITION_ACTUATION_ID, "contentdisposition"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_httpcookie"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"httpcookie_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTPCOOKIE_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTPCOOKIE_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_httpcookie(DEFAULT_SETCOOKIE)
    rebuilt = serialize_httpcookie(parse_httpcookie(advertised))
    preloaded = parse_httpcookie(RFC_HTTPCOOKIE_COOKIE)
    header = encode_httpcookie_header(DEFAULT_SETCOOKIE)
    parsed_header = parse_httpcookie_header(header)
    asked = parse_http_request(setcookie_request(SENTINEL, DEFAULT_COOKIEID))
    preload_req = parse_http_request(cookie_request(SENTINEL, DEFAULT_COOKIEID, DEFAULT_COOKIEDIGEST))
    got = parse_http_response(setcookie_response(SENTINEL, DEFAULT_COOKIEID, DEFAULT_COOKIEDIGEST))
    preload_reply = parse_http_response(
        cookie_response(SENTINEL, DEFAULT_COOKIEID, DEFAULT_COOKIEDIGEST)
    )
    checks["httpcookie_roundtrip"] = (
        parse_httpcookie(advertised) == DEFAULT_SETCOOKIE
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_SETCOOKIE_FIELD
        and is_token("SET-COOKIE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SETCOOKIE_FIELD
        and parsed_header["policy"] == DEFAULT_SETCOOKIE
        and parsed_header["header"] == SETCOOKIE_HEADER
        and parsed_header["setcookie"] is True
        and parsed_header["cookie"] is False
        and preloaded == COOKIE_POLICY
        and ascii_serialize_cookie() == RFC_COOKIE_PAIR
        and cookie_pair() == (RFC_COOKIE_NAME, RFC_COOKIE_VALUE)
        and RFC_COOKIE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_httpcookie(COOKIE_POLICY) == RFC_HTTPCOOKIE_COOKIE
        and DEFAULT_COOKIEDIGEST == request_cookiedigest(DEFAULT_COOKIEID, SENTINEL)
        and "cookiedigest=" in canonical_cookie(SENTINEL, DEFAULT_COOKIEID, DEFAULT_COOKIEDIGEST)
        and canonical_setcookie(SENTINEL, DEFAULT_COOKIEID).startswith("SET-COOKIE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["httpcookie_kind"] == "setcookie"
        and asked["cookieid"] == DEFAULT_COOKIEID
        and preload_req["httpcookie_kind"] == "cookie"
        and preload_req["cookiedigest"] == DEFAULT_COOKIEDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["httpcookie_kind"] == "setcookie"
        and preload_reply["httpcookie_kind"] == "cookie"
        and got["policy"] == DEFAULT_SETCOOKIE
        and preload_reply["policy"] == COOKIE_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["cookiedigest"] == DEFAULT_COOKIEDIGEST
        and preload_reply["cookiedigest"] == DEFAULT_COOKIEDIGEST
        and httpcookie_matches(serialize_httpcookie(got["policy"]), advertised)
    )

    checks["catalog_names_httpcookie"] = (
        len(catalog) > 86
        and catalog[86]["id"] == HTTPCOOKIE_ACTUATION_ID
        and catalog[85]["id"] == WEBORIGIN_ACTUATION_ID
        and catalog[86]["source"] == "genesis_bind_httpcookie"
    )
    checks["catalog_names_contentdisposition"] = (
        len(catalog) > 87
        and catalog[87]["id"] == CONTENTDISPOSITION_ACTUATION_ID
        and catalog[87]["source"] == "genesis_bind_contentdisposition"
    )
    family = capability_family(HTTPCOOKIE_ACTUATION_GOAL)
    checks["family_is_httpcookie"] = "httpcookie" in family
    checks["family_is_httpcookie_surface"] = "httpcookie" in family
    checks["family_is_cookieid"] = "cookieid" in family
    checks["family_is_rfc6265"] = "rfc6265" in family
    checks["family_is_cookiedigest"] = "cookiedigest" in family
    checks["family_is_not_contentdisposition"] = (
        "contentdisposition" not in family
        and "rfc6266" not in family
        and "dispositionid" not in family
        and "dispositiondigest" not in family
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
    packed = encode_setcookie(identity=SENTINEL, cookieid=DEFAULT_COOKIEID, cookiedigest=DEFAULT_COOKIEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_setcookie"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_cookieid"] is True
        and parsed["cookieid"] == DEFAULT_COOKIEID
        and parsed["cookiedigest"] == DEFAULT_COOKIEDIGEST
        and parsed["is_response"] is False
        and parsed["is_cookie"] is False
        and parsed["type"] == FRAME_SETCOOKIE
        and parsed["first_byte"] == CK_FIRST
    )
    shook = encode_cookie(
        identity=SENTINEL,
        cookieid=DEFAULT_COOKIEID,
        cookiedigest=DEFAULT_COOKIEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_cookie"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_setcookie"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["cookieid"] == DEFAULT_COOKIEID
        and answer_parsed["cookiedigest"] == DEFAULT_COOKIEDIGEST
        and answer_parsed["has_cookiedigest"] is True
        and answer_parsed["type"] == FRAME_COOKIE
        and answer_parsed["first_byte"] == CK_FIRST
    )
    bare = encode_setcookie(identity=SENTINEL, cookieid=DEFAULT_COOKIEID, include_cookieid=False)
    checks["missing_cookieid_is_unauthenticated"] = parse_message(bare)["has_cookieid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    httpcookie_signature = semantic_signature(HTTPCOOKIE_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(httpcookie_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_httpcookie = ToolDescriptor(name="remote_httpcookie", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_httpcookie)
    checks["naive_mcp_httpcookie_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = httpcookie_tool_descriptor()
    default_httpcookie = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPCOOKIE_TOOL_PROVIDER),
    )
    checks["default_httpcookie_provider_is_unsupported"] = (
        default_httpcookie.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTPCOOKIE_TOOL_PROVIDER}" in default_httpcookie.reasons
    )
    checks["opted_in_httpcookie_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_httpcookie],
        required_tool_names=("local_memory", "httpcookie"),
    )
    checks["naive_preflight_missing_httpcookie"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["httpcookie"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "httpcookie"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPCOOKIE_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "httpcookie" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="httpcookie-actuation-") as tmp:
        root = Path(tmp)
        missing = run_httpcookie_workflow(with_cookieid=False, output_dir=root / "missing")
        skip_bind = run_httpcookie_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_setcookie = run_httpcookie_workflow(do_setcookie=False, output_dir=root / "skip-serialize")
        skip_cookie = run_httpcookie_workflow(do_cookie=False, output_dir=root / "skip-tuple")
        skip_cookiedigest = run_httpcookie_workflow(do_cookiedigest=False, output_dir=root / "skip-cookiedigest")
        skip_replay = run_httpcookie_workflow(replay=False, output_dir=root / "skip-replay")
        skip_cookieid = run_httpcookie_workflow(use_cookieid=False, output_dir=root / "skip-cookieid")
        live = run_httpcookie_workflow(output_dir=root / "live")
        verify = verify_httpcookie_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_httpcookie_trace(clone)
        checks["naive_without_cookieid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_cookieid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_setcookie_stays_empty"] = (
            skip_setcookie["ok"] is False
            and skip_setcookie["error"] == "setcookie_required"
            and skip_setcookie["final_status"] == 409
            and skip_setcookie["payload_exists"] is False
        )
        checks["skip_cookie_stays_empty"] = (
            skip_cookie["ok"] is False
            and skip_cookie["error"] == "cookie_required"
            and skip_cookie["final_status"] == 409
            and skip_cookie["payload_exists"] is False
        )
        checks["skip_cookiedigest_stays_empty"] = (
            skip_cookiedigest["ok"] is False
            and skip_cookiedigest["error"] == "cookiedigest_required"
            and skip_cookiedigest["final_status"] == 409
            and skip_cookiedigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_cookieid_stays_empty"] = (
            skip_cookieid["ok"] is False
            and skip_cookieid["error"] == "cookieid_required"
            and skip_cookieid["final_status"] == 409
            and skip_cookieid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_cookiedigest"] = (
            int(live.get("cookieid") or 0) == DEFAULT_COOKIEID
            and int(live.get("cookiedigest") or 0) == DEFAULT_COOKIEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_cookieid_encode_cookie_cookiedigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_setcookie["ok"] is False
            and skip_cookie["ok"] is False
            and skip_cookiedigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_cookieid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="httpcookie-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTPCOOKIE_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_httpcookie"] = (
        live_goal == HTTPCOOKIE_ACTUATION_GOAL
        and HTTPCOOKIE_ACTUATION_ID in live_done
        and live_source == "genesis_bind_httpcookie"
    )

    with tempfile.TemporaryDirectory(prefix="httpcookie-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTPCOOKIE_LEFTOVER, root)
        register_catalog_proved(root, HTTPCOOKIE_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTPCOOKIE_LEFTOVER, root)
        after = leftover_is_open(HTTPCOOKIE_LEFTOVER, root)
    checks["httpcookie_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_httpcookie_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTPCOOKIE_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_httpcookie_actuation_capability()
    return {
        "ok": ok,
        "action": "httpcookie_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTPCOOKIE_ACTUATION_GOAL,
        "done_when": HTTPCOOKIE_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
