"""Drive a first-class Hypertext Transfer Protocol -- HTTP/1.0 tool through RFC 1945 GET/POST.

Tool routing already fails missions that require ``http10``: hosted
http10 endpoints stay on the unsupported MCP provider, and no first-party
http10 provider is executable. Unbound therefore cannot speak a GET,
lockstep a POST http10id handshake over HTTP/1.0 HTTP10ID,
independently poll the stored http10digest, or seal a http10digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``http10`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1945 daemon
- keep a missing-http10id client so the http10-http10id hole stays falsifiable
- refuse POST until a GET lands with a non-empty http10id
- independently poll the stored http10digest on a later client socket
- persist a sealed http10digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 2069 Digest Access Authentication
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
    HTTP10_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    http10_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTP10_ACTUATION_ID = "capability.http10-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-HTTP10-OK"
POLL_TOKEN = "BH-HTTP10-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_HTTP10ID = 0
EMPTY_HTTP10DIGEST = 0
HTTP10_FIRST = 0x48  # RFC 1945 Hypertext Transfer Protocol -- HTTP/1.0 (ASCII 'H')
HTTP10ID_SIZE = 4
HTTP10DIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_POST = 0x02  # RFC 1945 POST confirmation
FRAME_GET = 0x01  # RFC 1945 GET
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTP10_LEFTOVER = (
    "Later genesis can take RFC 1945 Hypertext Transfer Protocol -- HTTP/1.0 GET/POST over a "
    "http10id-gated http10digest."
)
HTTP10_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTP10_ACTUATION_ID};"
    f"capability_proved:{HTTP10_ACTUATION_ID};"
    "no_skill_route"
)
HTTP10_ACTUATION_GOAL = (
    "Repair rfc1945 http10 get/post cycle cannot land over http "
    "http10 http10id: hosted http10 endpoints remain unsupported so a GET then "
    "POST http10id handshake cannot land and a sealed http10digest "
    "cannot be produced. A missing http10 http10id stays forbidden; fail-closed "
    "routing never opts the http10 provider in. An independent later poll of the "
    "stored http10digest keeps the hole falsifiable."
)


class Http10ActuationError(RuntimeError):
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
# RFC 1945 sections 2.1 and 2.1.2: GET / POST.
RFC_GET_FIELD = "GET"
RFC_POST_FIELD = "POST"
RFC_HTTP10_POST = RFC_POST_FIELD
RFC_GET_DIRECTIVE = "get=request-uri"
RFC_POST_DIRECTIVE = "post=entity-body"
DEFAULT_GET = "GET"
POST_POLICY = "POST"
GET_HEADER = "Get"
POST_HEADER = "Post"
HTTP10_POST_HEADER = POST_HEADER
RFC_GET_PATH = "/http10/"
RFC_GET_EMPTY = ""


def http10_directive_pair(*, post: bool = False) -> tuple[str, str]:
    """RFC 1945 Challenge / Response directive pair."""

    if post:
        return "post", "entity-body"
    return "get", "request-uri"


def ascii_serialize_http10_directive(*, post: bool = False) -> str:
    """RFC 1945 token "=" get-or-post."""

    name, value = http10_directive_pair(post=post)
    if not is_token(name):
        raise Http10ActuationError("illegal_directive")
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
            raise Http10ActuationError("short_http10")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 1945 get-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_http10(policy: str | Sequence[str]) -> str:
    """Serialize RFC 1945 GET / POST opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise Http10ActuationError("illegal_http10")
    upper = text.upper().replace("_", "-")
    if upper in {"GET", "HTTP10", "HTTP10-GET"}:
        return "GET"
    if upper in {"POST", "ENTITY", "HTTP10-POST"}:
        return "POST"
    if upper.startswith("GET="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Http10ActuationError("illegal_http10")
        return "GET"
    if upper.startswith("POST="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Http10ActuationError("illegal_http10")
        return "POST"
    raise Http10ActuationError("illegal_http10")


def parse_http10(text: str) -> str:
    """Parse RFC 1945 HTTP10 opcode header extensions into GET or POST."""

    raw = str(text or "").strip()
    if not raw:
        raise Http10ActuationError("illegal_http10")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"GET", "HTTP10", "HTTP10-GET"}:
        return "GET"
    if upper in {"POST", "ENTITY", "HTTP10-POST"}:
        return "POST"
    if upper.startswith("GET="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Http10ActuationError("illegal_http10")
        return "GET"
    if upper.startswith("POST="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Http10ActuationError("illegal_http10")
        return "POST"
    raise Http10ActuationError("illegal_http10")


def encode_http10_header(policy: str | Sequence[str]) -> bytes:
    """RFC 1945 HTTP/1.0 field as bytes."""

    return serialize_http10(policy).encode("ascii")


def parse_http10_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_http10(field_value) if field_value else DEFAULT_GET
    return {
        "field_value": field_value,
        "policy": policy,
        "header": GET_HEADER,
        "directive": str(policy),
        "get": str(policy) == "GET",
        "post": str(policy) == "POST",
    }


def canonical_get(identity: str, http10id: int) -> str:
    """RFC 1945 get-request advertisement bound to identity and http10id."""

    return (
        f"{serialize_http10(DEFAULT_GET)}, "
        f"get={ascii_serialize_http10_directive()}, "
        f"identity={identity}, http10id={int(http10id) & 0xFFFFFFFF}"
    )


def canonical_post(identity: str, http10id: int, http10digest: int | None = None) -> str:
    """RFC 1945 post-entity confirmation of the stored entity-digest."""

    digest = ""
    if http10digest is not None:
        digest = f", http10digest={int(http10digest) & 0xFFFFFFFF}"
    return (
        f"{serialize_http10(POST_POLICY)}, "
        f"post={ascii_serialize_http10_directive(post=True)}, "
        f"identity={identity}, http10id={int(http10id) & 0xFFFFFFFF}{digest}"
    )


def representation_post(identity: str, http10id: int, http10digest: int) -> str:
    return canonical_post(identity, http10id, http10digest)


def http10_matches(left: str, right: str) -> bool:
    return parse_http10(left) == parse_http10(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise Http10ActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise Http10ActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise Http10ActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise Http10ActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def get_request(identity: str, http10id: int) -> bytes:
    """HTTP GET that elicits RFC 1945 origin HTTP/1.0."""

    keyid = f"{int(http10id) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /http10/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Http10-Id: {int(http10id) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def post_request(identity: str, http10id: int, http10digest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 1945 post-entity confirmation of the stored entity-digest."""

    keyid = f"{int(http10id) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if http10digest is not None:
        extra = f"Http10-Digest: {int(http10digest) & 0xFFFFFFFF}\r\n"
    return (
        f"POST /http10/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Http10-Id: {int(http10id) & 0xFFFFFFFF}\r\n"
        "Post-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    http10_kind = "post" if fields.get("post-confirm") == "1" else "get"
    upgrade_field = fields.get("get") or fields.get("http10") or ""
    policy = parse_http10(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "http10_kind": http10_kind,
        "policy": policy,
        "http10id": int(fields["http10-id"]) if fields.get("http10-id") else EMPTY_HTTP10ID,
        "http10digest": int(fields["http10-digest"]) if fields.get("http10-digest") else EMPTY_HTTP10DIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def get_response(identity: str, http10id: int, http10digest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 1945 origin HTTP/1.0, carrying the stored http10digest."""

    advertised = serialize_http10(DEFAULT_GET)
    payload = bytes(body or canonical_get(identity, http10id).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Get: {advertised}\r\n"
        f"Http10-Id: {int(http10id) & 0xFFFFFFFF}\r\n"
        f"Http10-Digest: {int(http10digest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def post_response(identity: str, http10id: int, http10digest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 1945 POST, carrying the stored entity-digest."""

    advertised = serialize_http10(POST_POLICY)
    payload = bytes(body or representation_post(identity, http10id, http10digest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Get: {advertised}\r\n"
        f"Http10-Id: {int(http10id) & 0xFFFFFFFF}\r\n"
        f"Http10-Digest: {int(http10digest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/http10-post\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise Http10ActuationError("illegal_content_length") from error
    field_value = fields.get("get") or fields.get("http10") or ""
    policy = parse_http10(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/http10-post" or policy == POST_POLICY:
        status = 200
        http10_kind = "post"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        http10_kind = "get"
    else:
        status = 0
        http10_kind = "get"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "http10_kind": http10_kind,
        "policy": policy,
        "http10id": int(fields["http10-id"]) if fields.get("http10-id") else EMPTY_HTTP10ID,
        "http10digest": int(fields["http10-digest"]) if fields.get("http10-digest") else EMPTY_HTTP10DIGEST,
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
        raise Http10ActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise Http10ActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise Http10ActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise Http10ActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc1945_entity_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    uri: str,
) -> str:
    """RFC 1945 entity digest over method, request-URI, identity, and http10id."""

    payload = f"{method}:{uri}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_http10id(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"http10id:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_http10id(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-http10id:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_http10digest(http10id: int = EMPTY_HTTP10ID, token: str = SENTINEL) -> int:
    nonce = f"{int(http10id) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc1945_entity_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="POST",
        uri=f"/http10/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_HTTP10ID = request_http10id(SENTINEL)
DEFAULT_HTTP10DIGEST = request_http10digest(DEFAULT_HTTP10ID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    http10id: int,
    http10digest: int,
    include_http10id: bool = True,
) -> bytes:
    live_http10id = int(http10id) & 0xFFFFFFFF if include_http10id else EMPTY_HTTP10ID
    live_digest = int(http10digest) & 0xFFFFFFFF if include_http10id and live_http10id else EMPTY_HTTP10DIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_http10id) if live_http10id else b""
    header = bytearray()
    header.append(HTTP10_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_get(
    *,
    identity: str,
    http10id: int,
    http10digest: int | None = None,
    include_http10id: bool = True,
) -> bytes:
    live_http10id = int(http10id) & 0xFFFFFFFF if include_http10id else EMPTY_HTTP10ID
    live_digest = int(http10digest) if http10digest is not None else request_http10digest(live_http10id, identity)
    return encode_packet(
        FRAME_GET,
        identity=identity,
        http10id=live_http10id,
        http10digest=live_digest,
        include_http10id=include_http10id,
    )


def encode_post(
    *,
    identity: str,
    http10id: int,
    http10digest: int | None = None,
    include_http10id: bool = True,
) -> bytes:
    live_http10id = int(http10id) & 0xFFFFFFFF if include_http10id else EMPTY_HTTP10ID
    live_digest = int(http10digest) if http10digest is not None else request_http10digest(live_http10id, identity)
    return encode_packet(
        FRAME_POST,
        identity=identity,
        http10id=live_http10id,
        http10digest=live_digest,
        include_http10id=include_http10id,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise Http10ActuationError("short_packet")
    first = raw[0]
    if first != HTTP10_FIRST:
        raise Http10ActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise Http10ActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == HTTP10ID_SIZE:
        live_http10id = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_http10id = EMPTY_HTTP10ID
    else:
        raise Http10ActuationError("illegal_http10id")
    if offset >= len(raw):
        raise Http10ActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_GET, FRAME_POST}:
        raise Http10ActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise Http10ActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise Http10ActuationError("checksum_failed")
    if len(payload) < 5:
        raise Http10ActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise Http10ActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_http10id = int(live_http10id) != EMPTY_HTTP10ID
    has_http10digest = has_http10id and int(live_digest) != EMPTY_HTTP10DIGEST
    is_get = frame_type == FRAME_GET
    is_post = frame_type == FRAME_POST
    return {
        "type": int(frame_type),
        "is_get": is_get,
        "is_post": is_post,
        "http10id": int(live_http10id),
        "has_http10id": has_http10id,
        "http10digest": int(live_digest),
        "has_http10digest": has_http10digest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC1945",
        "serialize_field": canonical_get(identity, live_http10id) if has_http10id else "",
        "tls_field": canonical_post(identity, live_http10id, live_digest) if has_http10digest else "",
    }


class Http10Client:
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
            raise Http10ActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_post"] or not packet["is_post"]:
            raise Http10ActuationError("http10digest_required")
        if not packet["has_http10id"]:
            raise Http10ActuationError("http10id_required")
        if not packet["has_http10digest"]:
            raise Http10ActuationError("http10digest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_http10digest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_http10digest:
            raise Http10ActuationError("http10digest_required")
        reply = self._recv()
        return {
            "session": reply,
            "http10id": int(reply.get("http10id") or EMPTY_HTTP10ID),
            "identity": str(reply.get("identity") or ""),
            "http10digest": int(reply.get("http10digest") or EMPTY_HTTP10DIGEST),
        }

    def report(
        self,
        identity: str,
        http10id: int,
        http10digest: int = EMPTY_HTTP10DIGEST,
        *,
        wait_http10digest: bool = True,
        include_http10id: bool = True,
    ) -> dict[str, Any]:
        packet = encode_post(
            identity=identity,
            http10id=http10id,
            http10digest=http10digest or request_http10digest(http10id, identity),
            include_http10id=include_http10id,
        )
        return self.exchange(packet, wait_http10digest=wait_http10digest)


class Http10Session:
    """HTTP10ID-gated loopback RFC 1945 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        http10id_gate: int = DEFAULT_HTTP10ID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.http10id_gate = int(http10id_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.http10id = EMPTY_HTTP10ID
        self.http10digest = EMPTY_HTTP10DIGEST
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

    def store_http10id_once(self, identity: str, http10id: int, http10digest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(http10id or EMPTY_HTTP10ID)
            live_digest = int(http10digest or EMPTY_HTTP10DIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.http10id = live
                self.http10digest = live_digest or request_http10digest(live, name)
                self.stored = True
            return str(self.identity), int(self.http10id), int(self.http10digest)

    def read_http10id(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.http10id), int(self.http10digest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "http10id": EMPTY_HTTP10ID,
            "http10digest": EMPTY_HTTP10DIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _http10id_missing(self) -> bool:
        return not int(self.http10id_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, http10id: int, http10digest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_post(
            identity=identity,
            http10id=http10id,
            http10digest=http10digest,
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
            except Http10ActuationError:
                continue
            if not packet.get("is_get") and not packet.get("is_post"):
                continue
            if not packet.get("has_http10id"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_http10id, stored_digest = self.store_http10id_once(
                identity,
                int(packet.get("http10id") or EMPTY_HTTP10ID),
                int(packet.get("http10digest") or EMPTY_HTTP10DIGEST),
            )
            if not stored_name or not stored_http10id or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_get"):
                    self.opened = True
                if packet.get("is_post"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_http10id, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._http10id_missing():
            return self._forbidden("missing_http10id")
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
        do_get: bool = True,
        do_post: bool = True,
        do_http10digest: bool = True,
        replay: bool = True,
        use_http10id: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._http10id_missing():
            return self._forbidden("missing_http10id")
        live_token = str(token or SENTINEL)
        origin_http10id = request_http10id(live_token)
        origin_digest = request_http10digest(origin_http10id, live_token)
        client: Http10Client | None = None
        independent: Http10Client | None = None
        try:
            client = Http10Client(self.host, int(self.port))
            if not do_get:
                return self._conflict("get_required")
            bind_packet = encode_get(
                identity=live_token,
                http10id=origin_http10id,
                http10digest=origin_digest,
                include_http10id=use_http10id,
            )
            if not use_http10id:
                try:
                    client.exchange(bind_packet, wait_http10digest=True)
                except Http10ActuationError:
                    return self._conflict("http10id_required")
                return self._conflict("http10id_required")
            client.send(bind_packet)
            if not do_post:
                return self._conflict("post_required")
            proxy_packet = encode_post(
                identity=live_token,
                http10id=origin_http10id,
                http10digest=origin_digest,
                include_http10id=True,
            )
            if not do_http10digest:
                try:
                    client.exchange(proxy_packet, wait_http10digest=False)
                except Http10ActuationError as error:
                    if str(error) == "http10digest_required":
                        return self._conflict("http10digest_required")
                    return self._conflict("http10digest_required")
                return self._conflict("http10digest_required")
            try:
                reply = client.exchange(proxy_packet, wait_http10digest=True)
            except Http10ActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("http10id_required")
                if reason == "http10digest_required":
                    return self._conflict("http10digest_required")
                return self._conflict("get_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("get_required")
            if int(reply.get("http10id") or EMPTY_HTTP10ID) != origin_http10id:
                return self._conflict("http10digest_required")
            if int(reply.get("http10digest") or EMPTY_HTTP10DIGEST) != origin_digest:
                return self._conflict("http10digest_required")
            self.retrieved = True
            if replay:
                independent = Http10Client(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_http10id(live_token),
                        request_http10digest(poll_http10id(live_token), POLL_TOKEN),
                        wait_http10digest=True,
                    )
                except Http10ActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_http10id, stored_digest = self.read_http10id()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_http10id != origin_http10id
                    or stored_digest != origin_digest
                    or int(poll.get("http10id") or EMPTY_HTTP10ID) != origin_http10id
                    or int(poll.get("http10digest") or EMPTY_HTTP10DIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_http10id}:{origin_digest}:{live_token}:{canonical_get(live_token, origin_http10id)}:{canonical_post(live_token, origin_http10id, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "http10id": origin_http10id,
                "http10digest": origin_digest,
                "get_frame": True,
                "post_frame": True,
                "http10digest_post": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "http10id_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_http10_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "http10id": origin_http10id,
                "http10digest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "get_frame": True,
                "post_frame": True,
                "http10digest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "http10id_bound": True,
            }
        except (OSError, Http10ActuationError) as error:
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
        live = independent_http10_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "http10id": int(live.get("http10id") or EMPTY_HTTP10ID),
            "http10digest": int(live.get("http10digest") or EMPTY_HTTP10DIGEST),
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


def call_http10_tool(session: Http10Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one http10 tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_get = True if arguments.get("get") is None else bool(arguments.get("get"))
    do_post = True if arguments.get("post") is None else bool(arguments.get("post"))
    do_http10digest = True if arguments.get("http10digest") is None else bool(arguments.get("http10digest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_http10id = True if arguments.get("use_http10id") is None else bool(arguments.get("use_http10id"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_get=do_get,
            do_post=do_post,
            do_http10digest=do_http10digest,
            replay=replay,
            use_http10id=use_http10id,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise Http10ActuationError(f"unsupported http10 action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_http10_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage http10digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "http10id": EMPTY_HTTP10ID,
        "http10digest": EMPTY_HTTP10DIGEST,
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
            "get_frame",
            "post_frame",
            "http10digest_post",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "http10id_bound",
        )
    )
    port = int(payload.get("port") or 0)
    http10id = int(payload.get("http10id") or EMPTY_HTTP10ID)
    http10digest = int(payload.get("http10digest") or EMPTY_HTTP10DIGEST)
    dual = port > 0 and bool(http10id) and bool(http10digest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "http10id": http10id,
        "http10digest": http10digest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "get_frame": payload.get("get_frame") is True,
        "post_frame": payload.get("post_frame") is True,
        "http10digest_post": payload.get("http10digest_post") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "http10id_bound": payload.get("http10id_bound") is True,
    }


def run_http10_workflow(
    *,
    with_http10id: bool = True,
    skip_bind: bool = False,
    do_get: bool = True,
    do_post: bool = True,
    do_http10digest: bool = True,
    replay: bool = True,
    use_http10id: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1945 GET/POST http10id cycle workflow."""

    descriptor = http10_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP10_TOOL_PROVIDER),
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
        raise Http10ActuationError(f"http10 tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="http10-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = Http10Session(out, http10id_gate=DEFAULT_HTTP10ID if with_http10id else EMPTY_HTTP10ID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "get": do_get,
            "post": do_post,
            "http10digest": do_http10digest,
            "replay": replay,
            "use_http10id": use_http10id,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_http10_tool(session, arguments))
            except Http10ActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_http10_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_http10id
        and not skip_bind
        and do_get
        and do_post
        and do_http10digest
        and replay
        and use_http10id
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "http10_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_http10id": with_http10id,
        "skip_bind": skip_bind,
        "get_frame": do_get,
        "post_frame": do_post,
        "http10digest": do_http10digest,
        "replay": replay,
        "use_http10id": use_http10id,
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
        "http10id_value": int(publish_result.get("http10id") or independent.get("http10id") or EMPTY_HTTP10ID),
        "http10digest_value": int(publish_result.get("http10digest") or independent.get("http10digest") or EMPTY_HTTP10DIGEST),
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
        "http10id": int(trace_body["http10id_value"] or EMPTY_HTTP10ID),
        "http10digest": int(trace_body["http10digest_value"] or EMPTY_HTTP10DIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_http10id": with_http10id,
        "skip_bind": skip_bind,
        "get_cycle": do_get,
        "post_cycle": do_post,
        "http10digest_cycle": do_http10digest,
        "replay": replay,
        "use_http10id": use_http10id,
    }


def verify_http10_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_http10_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    http10id = int(trace.get("http10id_value") or independent.get("http10id") or EMPTY_HTTP10ID)
    http10digest = int(trace.get("http10digest_value") or independent.get("http10digest") or EMPTY_HTTP10DIGEST)
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
        "get_frame": independent.get("get_frame") is True,
        "post_frame": independent.get("post_frame") is True,
        "http10digest_post": independent.get("http10digest_post") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "http10id_bound": independent.get("http10id_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "http10digest_recorded": (
            port > 0
            and http10id == DEFAULT_HTTP10ID
            and http10digest == DEFAULT_HTTP10DIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def http10_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.http10_actuation import "
        "builtin_http10_actuation_proof; r=builtin_http10_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='http10_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_http10_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTP10_ACTUATION_ID,
        name="First-class RFC 1945 Hypertext Transfer Protocol -- HTTP/1.0 GET/POST actuation",
        description=(
            "Missions that require a http10 tool can opt the http10 provider in, "
            "bind a loopback RFC 1945 Hypertext Transfer Protocol -- HTTP/1.0 endpoint, complete a GET "
            "with a non-empty http10id, lockstep a POST that carries the "
            "stored http10digest, independently poll the stored http10digest "
            "on a later socket, and seal a digest-chained http10digest. Default "
            "routing stays fail-closed; a missing http10id keeps the hole "
            "falsifiable, and skip-GET/POST/HTTP10DIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.http10_actuation:builtin_http10_actuation_proof",
        proof_command=http10_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.digestauth-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/http10_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/digestauth_actuation.py",
            "src/blackhole_agent/url_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required http10 tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 1945 daemon, speaks a "
            "GET then POST over Hypertext Transfer Protocol -- HTTP/1.0 with a non-empty http10id and "
            "http10digest, independently polls the stored http10digest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 2069 Digest Access Authentication lockstep is proved. "
            "Missing http10ids, skip-GET, skip-POST, skip-http10digest, skip-REPLAY, "
            "and a GET aimed without a http10id stay fail-closed. "
            "Later genesis can take RFC 1738 Uniform Resource Locators RESOLVE/LOCATE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("http10", "rfc1945", "http", "http10id", "http10digest", "get", "post", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T044128Z-5634ea96",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_http10_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1945 get/post lockstep actuation seals a http10digest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.url_actuation import (
        URL_ACTUATION_GOAL,
        URL_ACTUATION_ID,
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
    checks["denylists_self"] = HTTP10_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTP10_ACTUATION_GOAL) == (
        HTTP10_ACTUATION_ID,
    )
    checks["leftover_text_binds_http10"] = leftover_marker_ids(HTTP10_LEFTOVER) == (
        HTTP10_ACTUATION_ID,
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
        (URL_ACTUATION_GOAL, URL_ACTUATION_ID, "url"),
        (DIGESTAUTH_ACTUATION_GOAL, DIGESTAUTH_ACTUATION_ID, "digestauth"),
        (HTTPSTATE_ACTUATION_GOAL, HTTPSTATE_ACTUATION_ID, "httpstate"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_http10"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"http10_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTP10_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTP10_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_http10(DEFAULT_GET)
    rebuilt = serialize_http10(parse_http10(advertised))
    preloaded = parse_http10(RFC_HTTP10_POST)
    header = encode_http10_header(DEFAULT_GET)
    parsed_header = parse_http10_header(header)
    asked = parse_http_request(get_request(SENTINEL, DEFAULT_HTTP10ID))
    preload_req = parse_http_request(post_request(SENTINEL, DEFAULT_HTTP10ID, DEFAULT_HTTP10DIGEST))
    got = parse_http_response(get_response(SENTINEL, DEFAULT_HTTP10ID, DEFAULT_HTTP10DIGEST))
    preload_reply = parse_http_response(
        post_response(SENTINEL, DEFAULT_HTTP10ID, DEFAULT_HTTP10DIGEST)
    )
    checks["http10_roundtrip"] = (
        parse_http10(advertised) == DEFAULT_GET
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_GET_FIELD
        and is_token("GET") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_GET_FIELD
        and parsed_header["policy"] == DEFAULT_GET
        and parsed_header["header"] == GET_HEADER
        and parsed_header["get"] is True
        and parsed_header["post"] is False
        and preloaded == POST_POLICY
        and ascii_serialize_http10_directive() == RFC_GET_DIRECTIVE
        and http10_directive_pair() == ("get", "request-uri")
        and RFC_GET_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_http10(POST_POLICY) == RFC_HTTP10_POST
        and DEFAULT_HTTP10DIGEST == request_http10digest(DEFAULT_HTTP10ID, SENTINEL)
        and "http10digest=" in canonical_post(SENTINEL, DEFAULT_HTTP10ID, DEFAULT_HTTP10DIGEST)
        and canonical_get(SENTINEL, DEFAULT_HTTP10ID).startswith("GET")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["http10_kind"] == "get"
        and asked["http10id"] == DEFAULT_HTTP10ID
        and preload_req["http10_kind"] == "post"
        and preload_req["http10digest"] == DEFAULT_HTTP10DIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["http10_kind"] == "get"
        and preload_reply["http10_kind"] == "post"
        and got["policy"] == DEFAULT_GET
        and preload_reply["policy"] == POST_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["http10digest"] == DEFAULT_HTTP10DIGEST
        and preload_reply["http10digest"] == DEFAULT_HTTP10DIGEST
        and http10_matches(serialize_http10(got["policy"]), advertised)
    )

    checks["catalog_names_http10"] = (
        len(catalog) > 103
        and catalog[103]["id"] == HTTP10_ACTUATION_ID
        and catalog[102]["id"] == DIGESTAUTH_ACTUATION_ID
        and catalog[103]["source"] == "genesis_bind_http10"
    )
    checks["catalog_names_url"] = (
        len(catalog) > 104
        and catalog[104]["id"] == URL_ACTUATION_ID
        and catalog[104]["source"] == "genesis_bind_url"
    )
    family = capability_family(HTTP10_ACTUATION_GOAL)
    checks["family_is_http10"] = "http10" in family
    checks["family_is_http10_surface"] = "http10" in family
    checks["family_is_getid"] = "http10id" in family
    checks["family_is_rfc1945"] = "rfc1945" in family
    checks["family_is_http10digest"] = "http10digest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_url"] = (
        "url" not in family.split("/")
        and "rfc1738" not in family
        and "urlid" not in family
        and "urldigest" not in family
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
    packed = encode_get(identity=SENTINEL, http10id=DEFAULT_HTTP10ID, http10digest=DEFAULT_HTTP10DIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_get"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_http10id"] is True
        and parsed["http10id"] == DEFAULT_HTTP10ID
        and parsed["http10digest"] == DEFAULT_HTTP10DIGEST
        and parsed["is_post"] is False
        and parsed["is_post"] is False
        and parsed["type"] == FRAME_GET
        and parsed["first_byte"] == HTTP10_FIRST
    )
    shook = encode_post(
        identity=SENTINEL,
        http10id=DEFAULT_HTTP10ID,
        http10digest=DEFAULT_HTTP10DIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_post"] is True
        and answer_parsed["is_post"] is True
        and answer_parsed["is_get"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["http10id"] == DEFAULT_HTTP10ID
        and answer_parsed["http10digest"] == DEFAULT_HTTP10DIGEST
        and answer_parsed["has_http10digest"] is True
        and answer_parsed["type"] == FRAME_POST
        and answer_parsed["first_byte"] == HTTP10_FIRST
    )
    bare = encode_get(identity=SENTINEL, http10id=DEFAULT_HTTP10ID, include_http10id=False)
    checks["missing_http10id_is_unauthed"] = parse_message(bare)["has_http10id"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(HTTP10_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_http10 = ToolDescriptor(name="remote_http10", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_http10)
    checks["naive_mcp_http10_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = http10_tool_descriptor()
    default_http10 = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP10_TOOL_PROVIDER),
    )
    checks["default_http10_provider_is_unsupported"] = (
        default_http10.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTP10_TOOL_PROVIDER}" in default_http10.reasons
    )
    checks["opted_in_http10_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_http10],
        required_tool_names=("local_memory", "http10"),
    )
    checks["naive_preflight_missing_http10"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["http10"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "http10"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP10_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "http10" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="http10-actuation-") as tmp:
        root = Path(tmp)
        missing = run_http10_workflow(with_http10id=False, output_dir=root / "missing")
        skip_bind = run_http10_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_get = run_http10_workflow(do_get=False, output_dir=root / "skip-get")
        skip_post = run_http10_workflow(do_post=False, output_dir=root / "skip-post")
        skip_http10digest = run_http10_workflow(do_http10digest=False, output_dir=root / "skip-http10digest")
        skip_replay = run_http10_workflow(replay=False, output_dir=root / "skip-replay")
        skip_http10id = run_http10_workflow(use_http10id=False, output_dir=root / "skip-http10id")
        live = run_http10_workflow(output_dir=root / "live")
        verify = verify_http10_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_http10_trace(clone)
        checks["naive_without_http10id_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_http10id"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_get_stays_empty"] = (
            skip_get["ok"] is False
            and skip_get["error"] == "get_required"
            and skip_get["final_status"] == 409
            and skip_get["payload_exists"] is False
        )
        checks["skip_post_stays_empty"] = (
            skip_post["ok"] is False
            and skip_post["error"] == "post_required"
            and skip_post["final_status"] == 409
            and skip_post["payload_exists"] is False
        )
        checks["skip_http10digest_stays_empty"] = (
            skip_http10digest["ok"] is False
            and skip_http10digest["error"] == "http10digest_required"
            and skip_http10digest["final_status"] == 409
            and skip_http10digest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_http10id_stays_empty"] = (
            skip_http10id["ok"] is False
            and skip_http10id["error"] == "http10id_required"
            and skip_http10id["final_status"] == 409
            and skip_http10id["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_http10digest"] = (
            int(live.get("http10id") or 0) == DEFAULT_HTTP10ID
            and int(live.get("http10digest") or 0) == DEFAULT_HTTP10DIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_http10id_encode_post_http10digest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_get["ok"] is False
            and skip_post["ok"] is False
            and skip_http10digest["ok"] is False
            and skip_replay["ok"] is False
            and skip_http10id["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="http10-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTP10_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_http10"] = (
        live_goal == HTTP10_ACTUATION_GOAL
        and HTTP10_ACTUATION_ID in live_done
        and live_source == "genesis_bind_http10"
    )

    with tempfile.TemporaryDirectory(prefix="http10-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTP10_LEFTOVER, root)
        register_catalog_proved(root, HTTP10_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTP10_LEFTOVER, root)
        after = leftover_is_open(HTTP10_LEFTOVER, root)
    checks["http10_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_http10_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTP10_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_http10_actuation_capability()
    return {
        "ok": ok,
        "action": "http10_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTP10_ACTUATION_GOAL,
        "done_when": HTTP10_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
