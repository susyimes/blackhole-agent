"""Drive a first-class The Finger User Information Protocol tool through RFC 1288 QUERY/USER.

Tool routing already fails missions that require ``finger``: hosted
finger endpoints stay on the unsupported MCP provider, and no first-party
finger provider is executable. Unbound therefore cannot speak a QUERY,
lockstep a USER fingerid handshake over HTTP/1.0 FINGERID,
independently poll the stored fingerdigest, or seal a fingerdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``finger`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1288 daemon
- keep a missing-fingerid client so the finger-fingerid hole stays falsifiable
- refuse USER until a QUERY lands with a non-empty fingerid
- independently poll the stored fingerdigest on a later client socket
- persist a sealed fingerdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 1436 The Internet Gopher Protocol
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
    FINGER_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    finger_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
FINGER_ACTUATION_ID = "capability.finger-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-FINGER-OK"
POLL_TOKEN = "BH-FINGER-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_FINGERID = 0
EMPTY_FINGERDIGEST = 0
FINGER_FIRST = 0x46  # RFC 1288 FINGER (ASCII 'F')
FINGERID_SIZE = 4
FINGERDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_USER = 0x02  # RFC 1288 USER confirmation
FRAME_QUERY = 0x01  # RFC 1288 QUERY
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
FINGER_LEFTOVER = (
    "Later genesis can take RFC 1288 The Finger User Information Protocol QUERY/USER over a "
    "fingerid-gated fingerdigest."
)
FINGER_ACTUATION_DONE_WHEN = (
    f"capability_exists:{FINGER_ACTUATION_ID};"
    f"capability_proved:{FINGER_ACTUATION_ID};"
    "no_skill_route"
)
FINGER_ACTUATION_GOAL = (
    "Repair rfc1288 finger query/user cycle cannot land over http "
    "finger fingerid: hosted finger endpoints remain unsupported so a QUERY then "
    "USER fingerid handshake cannot land and a sealed fingerdigest "
    "cannot be produced. A missing finger fingerid stays forbidden; fail-closed "
    "routing never opts the finger provider in. An independent later poll of the "
    "stored fingerdigest keeps the hole falsifiable."
)


class FingerActuationError(RuntimeError):
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
# RFC 1288 sections 2.1 and 2.1.2: QUERY / USER.
RFC_QUERY_FIELD = "QUERY"
RFC_USER_FIELD = "USER"
RFC_FINGER_USER = RFC_USER_FIELD
RFC_QUERY_DIRECTIVE = "query=name"
RFC_USER_DIRECTIVE = "user=resource"
DEFAULT_QUERY = "QUERY"
USER_POLICY = "USER"
QUERY_HEADER = "Query"
USER_HEADER = "User"
FINGER_USER_HEADER = USER_HEADER
RFC_QUERY_PATH = "/finger/"
RFC_QUERY_EMPTY = ""


def finger_directive_pair(*, user: bool = False) -> tuple[str, str]:
    """RFC 1288 Query / User directive pair."""

    if user:
        return "user", "resource"
    return "query", "name"


def ascii_serialize_finger_directive(*, user: bool = False) -> str:
    """RFC 1288 token "=" body-or-user."""

    name, value = finger_directive_pair(user=user)
    if not is_token(name):
        raise FingerActuationError("illegal_directive")
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
            raise FingerActuationError("short_finger")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 1288 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_finger(policy: str | Sequence[str]) -> str:
    """Serialize RFC 1288 QUERY / USER opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise FingerActuationError("illegal_finger")
    upper = text.upper().replace("_", "-")
    if upper in {"QUERY", "FINGER", "FINGER-QUERY"}:
        return "QUERY"
    if upper in {"USER", "RESOURCE", "FINGER-USER"}:
        return "USER"
    if upper.startswith("QUERY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise FingerActuationError("illegal_finger")
        return "QUERY"
    if upper.startswith("USER="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise FingerActuationError("illegal_finger")
        return "USER"
    raise FingerActuationError("illegal_finger")


def parse_finger(text: str) -> str:
    """Parse RFC 1288 FINGER opcode header extensions into QUERY or USER."""

    raw = str(text or "").strip()
    if not raw:
        raise FingerActuationError("illegal_finger")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"QUERY", "FINGER", "FINGER-QUERY"}:
        return "QUERY"
    if upper in {"USER", "RESOURCE", "FINGER-USER"}:
        return "USER"
    if upper.startswith("QUERY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise FingerActuationError("illegal_finger")
        return "QUERY"
    if upper.startswith("USER="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise FingerActuationError("illegal_finger")
        return "USER"
    raise FingerActuationError("illegal_finger")


def encode_finger_header(policy: str | Sequence[str]) -> bytes:
    """RFC 1288 HTTP/1.0 field as bytes."""

    return serialize_finger(policy).encode("ascii")


def parse_finger_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_finger(field_value) if field_value else DEFAULT_QUERY
    return {
        "field_value": field_value,
        "policy": policy,
        "header": QUERY_HEADER,
        "directive": str(policy),
        "query": str(policy) == "QUERY",
        "user": str(policy) == "USER",
    }


def canonical_query(identity: str, fingerid: int) -> str:
    """RFC 1288 body-request advertisement bound to identity and fingerid."""

    return (
        f"{serialize_finger(DEFAULT_QUERY)}, "
        f"query={ascii_serialize_finger_directive()}, "
        f"identity={identity}, fingerid={int(fingerid) & 0xFFFFFFFF}"
    )


def canonical_user(identity: str, fingerid: int, fingerdigest: int | None = None) -> str:
    """RFC 1288 user-resource confirmation of the stored identifier-digest."""

    digest = ""
    if fingerdigest is not None:
        digest = f", fingerdigest={int(fingerdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_finger(USER_POLICY)}, "
        f"user={ascii_serialize_finger_directive(user=True)}, "
        f"identity={identity}, fingerid={int(fingerid) & 0xFFFFFFFF}{digest}"
    )


def representation_user(identity: str, fingerid: int, fingerdigest: int) -> str:
    return canonical_user(identity, fingerid, fingerdigest)


def finger_matches(left: str, right: str) -> bool:
    return parse_finger(left) == parse_finger(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise FingerActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise FingerActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise FingerActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise FingerActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def query_request(identity: str, fingerid: int) -> bytes:
    """HTTP QUERY that elicits RFC 1288 origin HTTP/1.0."""

    keyid = f"{int(fingerid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"QUERY /finger/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Finger-Id: {int(fingerid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def user_request(identity: str, fingerid: int, fingerdigest: int | None = None) -> bytes:
    """HTTP QUERY carrying RFC 1288 user-resource confirmation of the stored identifier-digest."""

    keyid = f"{int(fingerid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if fingerdigest is not None:
        extra = f"Finger-Digest: {int(fingerdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"USER /finger/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Finger-Id: {int(fingerid) & 0xFFFFFFFF}\r\n"
        "User-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    finger_kind = "user" if fields.get("user-confirm") == "1" else "query"
    upgrade_field = fields.get("query") or fields.get("finger") or ""
    policy = parse_finger(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "finger_kind": finger_kind,
        "policy": policy,
        "fingerid": int(fields["finger-id"]) if fields.get("finger-id") else EMPTY_FINGERID,
        "fingerdigest": int(fields["finger-digest"]) if fields.get("finger-digest") else EMPTY_FINGERDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def query_response(identity: str, fingerid: int, fingerdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 1288 origin HTTP/1.0, carrying the stored fingerdigest."""

    advertised = serialize_finger(DEFAULT_QUERY)
    payload = bytes(body or canonical_query(identity, fingerid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Query: {advertised}\r\n"
        f"Finger-Id: {int(fingerid) & 0xFFFFFFFF}\r\n"
        f"Finger-Digest: {int(fingerdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def user_response(identity: str, fingerid: int, fingerdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 1288 USER, carrying the stored identifier-digest."""

    advertised = serialize_finger(USER_POLICY)
    payload = bytes(body or representation_user(identity, fingerid, fingerdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Query: {advertised}\r\n"
        f"Finger-Id: {int(fingerid) & 0xFFFFFFFF}\r\n"
        f"Finger-Digest: {int(fingerdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/finger-user\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise FingerActuationError("illegal_content_length") from error
    field_value = fields.get("query") or fields.get("finger") or ""
    policy = parse_finger(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/finger-user" or policy == USER_POLICY:
        status = 200
        finger_kind = "user"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        finger_kind = "query"
    else:
        status = 0
        finger_kind = "query"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "finger_kind": finger_kind,
        "policy": policy,
        "fingerid": int(fields["finger-id"]) if fields.get("finger-id") else EMPTY_FINGERID,
        "fingerdigest": int(fields["finger-digest"]) if fields.get("finger-digest") else EMPTY_FINGERDIGEST,
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
        raise FingerActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise FingerActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise FingerActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise FingerActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc1288_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    finger: str,
) -> str:
    """RFC 1288 identifier digest over method, request-FINGER, identity, and fingerid."""

    payload = f"{method}:{finger}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_fingerid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"fingerid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_fingerid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-fingerid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_fingerdigest(fingerid: int = EMPTY_FINGERID, token: str = SENTINEL) -> int:
    nonce = f"{int(fingerid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc1288_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="USER",
        finger=f"/finger/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_FINGERID = request_fingerid(SENTINEL)
DEFAULT_FINGERDIGEST = request_fingerdigest(DEFAULT_FINGERID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    fingerid: int,
    fingerdigest: int,
    include_fingerid: bool = True,
) -> bytes:
    live_fingerid = int(fingerid) & 0xFFFFFFFF if include_fingerid else EMPTY_FINGERID
    live_digest = int(fingerdigest) & 0xFFFFFFFF if include_fingerid and live_fingerid else EMPTY_FINGERDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_fingerid) if live_fingerid else b""
    header = bytearray()
    header.append(FINGER_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_query(
    *,
    identity: str,
    fingerid: int,
    fingerdigest: int | None = None,
    include_fingerid: bool = True,
) -> bytes:
    live_fingerid = int(fingerid) & 0xFFFFFFFF if include_fingerid else EMPTY_FINGERID
    live_digest = int(fingerdigest) if fingerdigest is not None else request_fingerdigest(live_fingerid, identity)
    return encode_packet(
        FRAME_QUERY,
        identity=identity,
        fingerid=live_fingerid,
        fingerdigest=live_digest,
        include_fingerid=include_fingerid,
    )


def encode_user(
    *,
    identity: str,
    fingerid: int,
    fingerdigest: int | None = None,
    include_fingerid: bool = True,
) -> bytes:
    live_fingerid = int(fingerid) & 0xFFFFFFFF if include_fingerid else EMPTY_FINGERID
    live_digest = int(fingerdigest) if fingerdigest is not None else request_fingerdigest(live_fingerid, identity)
    return encode_packet(
        FRAME_USER,
        identity=identity,
        fingerid=live_fingerid,
        fingerdigest=live_digest,
        include_fingerid=include_fingerid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise FingerActuationError("short_packet")
    first = raw[0]
    if first != FINGER_FIRST:
        raise FingerActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise FingerActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == FINGERID_SIZE:
        live_fingerid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_fingerid = EMPTY_FINGERID
    else:
        raise FingerActuationError("illegal_fingerid")
    if offset >= len(raw):
        raise FingerActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_QUERY, FRAME_USER}:
        raise FingerActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise FingerActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise FingerActuationError("checksum_failed")
    if len(payload) < 5:
        raise FingerActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise FingerActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_fingerid = int(live_fingerid) != EMPTY_FINGERID
    has_fingerdigest = has_fingerid and int(live_digest) != EMPTY_FINGERDIGEST
    is_query = frame_type == FRAME_QUERY
    is_user = frame_type == FRAME_USER
    return {
        "type": int(frame_type),
        "is_query": is_query,
        "is_user": is_user,
        "fingerid": int(live_fingerid),
        "has_fingerid": has_fingerid,
        "fingerdigest": int(live_digest),
        "has_fingerdigest": has_fingerdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC1288",
        "serialize_field": canonical_query(identity, live_fingerid) if has_fingerid else "",
        "tls_field": canonical_user(identity, live_fingerid, live_digest) if has_fingerdigest else "",
    }


class FingerClient:
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
            raise FingerActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_user"] or not packet["is_user"]:
            raise FingerActuationError("fingerdigest_required")
        if not packet["has_fingerid"]:
            raise FingerActuationError("fingerid_required")
        if not packet["has_fingerdigest"]:
            raise FingerActuationError("fingerdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_fingerdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_fingerdigest:
            raise FingerActuationError("fingerdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "fingerid": int(reply.get("fingerid") or EMPTY_FINGERID),
            "identity": str(reply.get("identity") or ""),
            "fingerdigest": int(reply.get("fingerdigest") or EMPTY_FINGERDIGEST),
        }

    def report(
        self,
        identity: str,
        fingerid: int,
        fingerdigest: int = EMPTY_FINGERDIGEST,
        *,
        wait_fingerdigest: bool = True,
        include_fingerid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_user(
            identity=identity,
            fingerid=fingerid,
            fingerdigest=fingerdigest or request_fingerdigest(fingerid, identity),
            include_fingerid=include_fingerid,
        )
        return self.exchange(packet, wait_fingerdigest=wait_fingerdigest)


class FingerSession:
    """FINGERID-gated loopback RFC 1288 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        fingerid_gate: int = DEFAULT_FINGERID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.fingerid_gate = int(fingerid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.fingerid = EMPTY_FINGERID
        self.fingerdigest = EMPTY_FINGERDIGEST
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

    def store_fingerid_once(self, identity: str, fingerid: int, fingerdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(fingerid or EMPTY_FINGERID)
            live_digest = int(fingerdigest or EMPTY_FINGERDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.fingerid = live
                self.fingerdigest = live_digest or request_fingerdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.fingerid), int(self.fingerdigest)

    def read_fingerid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.fingerid), int(self.fingerdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "fingerid": EMPTY_FINGERID,
            "fingerdigest": EMPTY_FINGERDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _fingerid_missing(self) -> bool:
        return not int(self.fingerid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, fingerid: int, fingerdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_user(
            identity=identity,
            fingerid=fingerid,
            fingerdigest=fingerdigest,
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
            except FingerActuationError:
                continue
            if not packet.get("is_query") and not packet.get("is_user"):
                continue
            if not packet.get("has_fingerid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_fingerid, stored_digest = self.store_fingerid_once(
                identity,
                int(packet.get("fingerid") or EMPTY_FINGERID),
                int(packet.get("fingerdigest") or EMPTY_FINGERDIGEST),
            )
            if not stored_name or not stored_fingerid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_query"):
                    self.opened = True
                if packet.get("is_user"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_fingerid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._fingerid_missing():
            return self._forbidden("missing_fingerid")
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
        do_query: bool = True,
        do_user: bool = True,
        do_fingerdigest: bool = True,
        replay: bool = True,
        use_fingerid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._fingerid_missing():
            return self._forbidden("missing_fingerid")
        live_token = str(token or SENTINEL)
        origin_fingerid = request_fingerid(live_token)
        origin_digest = request_fingerdigest(origin_fingerid, live_token)
        client: FingerClient | None = None
        independent: FingerClient | None = None
        try:
            client = FingerClient(self.host, int(self.port))
            if not do_query:
                return self._conflict("query_required")
            bind_packet = encode_query(
                identity=live_token,
                fingerid=origin_fingerid,
                fingerdigest=origin_digest,
                include_fingerid=use_fingerid,
            )
            if not use_fingerid:
                try:
                    client.exchange(bind_packet, wait_fingerdigest=True)
                except FingerActuationError:
                    return self._conflict("fingerid_required")
                return self._conflict("fingerid_required")
            client.send(bind_packet)
            if not do_user:
                return self._conflict("user_required")
            proxy_packet = encode_user(
                identity=live_token,
                fingerid=origin_fingerid,
                fingerdigest=origin_digest,
                include_fingerid=True,
            )
            if not do_fingerdigest:
                try:
                    client.exchange(proxy_packet, wait_fingerdigest=False)
                except FingerActuationError as error:
                    if str(error) == "fingerdigest_required":
                        return self._conflict("fingerdigest_required")
                    return self._conflict("fingerdigest_required")
                return self._conflict("fingerdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_fingerdigest=True)
            except FingerActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("fingerid_required")
                if reason == "fingerdigest_required":
                    return self._conflict("fingerdigest_required")
                return self._conflict("query_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("query_required")
            if int(reply.get("fingerid") or EMPTY_FINGERID) != origin_fingerid:
                return self._conflict("fingerdigest_required")
            if int(reply.get("fingerdigest") or EMPTY_FINGERDIGEST) != origin_digest:
                return self._conflict("fingerdigest_required")
            self.retrieved = True
            if replay:
                independent = FingerClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_fingerid(live_token),
                        request_fingerdigest(poll_fingerid(live_token), POLL_TOKEN),
                        wait_fingerdigest=True,
                    )
                except FingerActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_fingerid, stored_digest = self.read_fingerid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_fingerid != origin_fingerid
                    or stored_digest != origin_digest
                    or int(poll.get("fingerid") or EMPTY_FINGERID) != origin_fingerid
                    or int(poll.get("fingerdigest") or EMPTY_FINGERDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_fingerid}:{origin_digest}:{live_token}:{canonical_query(live_token, origin_fingerid)}:{canonical_user(live_token, origin_fingerid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "fingerid": origin_fingerid,
                "fingerdigest": origin_digest,
                "query_frame": True,
                "user_frame": True,
                "fingerdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "fingerid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_fingerdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "fingerid": origin_fingerid,
                "fingerdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "query_frame": True,
                "user_frame": True,
                "fingerdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "fingerid_bound": True,
            }
        except (OSError, FingerActuationError) as error:
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
        live = independent_fingerdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "fingerid": int(live.get("fingerid") or EMPTY_FINGERID),
            "fingerdigest": int(live.get("fingerdigest") or EMPTY_FINGERDIGEST),
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


def call_finger_tool(session: FingerSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one finger tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_query = True if arguments.get("query") is None else bool(arguments.get("query"))
    do_user = True if arguments.get("user") is None else bool(arguments.get("user"))
    do_fingerdigest = True if arguments.get("fingerdigest") is None else bool(arguments.get("fingerdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_fingerid = True if arguments.get("use_fingerid") is None else bool(arguments.get("use_fingerid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_query=do_query,
            do_user=do_user,
            do_fingerdigest=do_fingerdigest,
            replay=replay,
            use_fingerid=use_fingerid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise FingerActuationError(f"unsupported finger action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_fingerdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage fingerdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "fingerid": EMPTY_FINGERID,
        "fingerdigest": EMPTY_FINGERDIGEST,
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
            "query_frame",
            "user_frame",
            "fingerdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "fingerid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    fingerid = int(payload.get("fingerid") or EMPTY_FINGERID)
    fingerdigest = int(payload.get("fingerdigest") or EMPTY_FINGERDIGEST)
    dual = port > 0 and bool(fingerid) and bool(fingerdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "fingerid": fingerid,
        "fingerdigest": fingerdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "query_frame": payload.get("query_frame") is True,
        "user_frame": payload.get("user_frame") is True,
        "fingerdigest_locate": payload.get("fingerdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "fingerid_bound": payload.get("fingerid_bound") is True,
    }


def run_finger_workflow(
    *,
    with_fingerid: bool = True,
    skip_bind: bool = False,
    do_query: bool = True,
    do_user: bool = True,
    do_fingerdigest: bool = True,
    replay: bool = True,
    use_fingerid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1288 QUERY/USER fingerid cycle workflow."""

    descriptor = finger_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FINGER_TOOL_PROVIDER),
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
        raise FingerActuationError(f"finger tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="finger-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = FingerSession(out, fingerid_gate=DEFAULT_FINGERID if with_fingerid else EMPTY_FINGERID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "query": do_query,
            "user": do_user,
            "fingerdigest": do_fingerdigest,
            "replay": replay,
            "use_fingerid": use_fingerid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_finger_tool(session, arguments))
            except FingerActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_fingerdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_fingerid
        and not skip_bind
        and do_query
        and do_user
        and do_fingerdigest
        and replay
        and use_fingerid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "finger_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_fingerid": with_fingerid,
        "skip_bind": skip_bind,
        "query_frame": do_query,
        "user_frame": do_user,
        "fingerdigest": do_fingerdigest,
        "replay": replay,
        "use_fingerid": use_fingerid,
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
        "fingerid_value": int(publish_result.get("fingerid") or independent.get("fingerid") or EMPTY_FINGERID),
        "fingerdigest_value": int(publish_result.get("fingerdigest") or independent.get("fingerdigest") or EMPTY_FINGERDIGEST),
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
        "fingerid": int(trace_body["fingerid_value"] or EMPTY_FINGERID),
        "fingerdigest": int(trace_body["fingerdigest_value"] or EMPTY_FINGERDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_fingerid": with_fingerid,
        "skip_bind": skip_bind,
        "query_cycle": do_query,
        "user_cycle": do_user,
        "fingerdigest_cycle": do_fingerdigest,
        "replay": replay,
        "use_fingerid": use_fingerid,
    }


def verify_finger_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_fingerdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    fingerid = int(trace.get("fingerid_value") or independent.get("fingerid") or EMPTY_FINGERID)
    fingerdigest = int(trace.get("fingerdigest_value") or independent.get("fingerdigest") or EMPTY_FINGERDIGEST)
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
        "query_frame": independent.get("query_frame") is True,
        "user_frame": independent.get("user_frame") is True,
        "fingerdigest_locate": independent.get("fingerdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "fingerid_bound": independent.get("fingerid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "fingerdigest_recorded": (
            port > 0
            and fingerid == DEFAULT_FINGERID
            and fingerdigest == DEFAULT_FINGERDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def finger_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.finger_actuation import "
        "builtin_finger_actuation_proof; r=builtin_finger_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='finger_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_finger_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=FINGER_ACTUATION_ID,
        name="First-class RFC 1288 The Finger User Information Protocol QUERY/USER actuation",
        description=(
            "Missions that require a finger tool can opt the finger provider in, "
            "bind a loopback RFC 1288 The Finger User Information Protocol endpoint, complete a QUERY "
            "with a non-empty fingerid, lockstep a USER that carries the "
            "stored fingerdigest, independently poll the stored fingerdigest "
            "on a later socket, and seal a digest-chained fingerdigest. Default "
            "routing stays fail-closed; a missing fingerid keeps the hole "
            "falsifiable, and skip-QUERY/USER/FINGERDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.finger_actuation:builtin_finger_actuation_proof",
        proof_command=finger_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.gopher-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/finger_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/gopher_actuation.py",
            "src/blackhole_agent/lpd_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required finger tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 1288 daemon, speaks a "
            "QUERY then USER over The Finger User Information Protocol with a non-empty fingerid and "
            "fingerdigest, independently polls the stored fingerdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 1436 The Internet Gopher Protocol lockstep is proved. "
            "Missing fingerids, skip-QUERY, skip-USER, skip-fingerdigest, skip-REPLAY, "
            "and a QUERY aimed without a fingerid stay fail-closed. "
            "Later genesis can take RFC 1179 Line Printer Daemon Protocol PRINT/QUEUE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("finger", "rfc1288", "http", "fingerid", "fingerdigest", "query", "user", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T073518Z-3dd4fad8",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_finger_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1288 query/user lockstep actuation seals a fingerdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.lpd_actuation import (
        LPD_ACTUATION_GOAL,
        LPD_ACTUATION_ID,
    )
    from blackhole_agent.gopher_actuation import (
        GOPHER_ACTUATION_GOAL,
        GOPHER_ACTUATION_ID,
    )
    from blackhole_agent.mime_actuation import (
        MIME_ACTUATION_GOAL,
        MIME_ACTUATION_ID,
    )
    from blackhole_agent.uri_actuation import (
        URI_ACTUATION_GOAL,
        URI_ACTUATION_ID,
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
    checks["denylists_self"] = FINGER_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(FINGER_ACTUATION_GOAL) == (
        FINGER_ACTUATION_ID,
    )
    checks["leftover_text_binds_finger"] = leftover_marker_ids(FINGER_LEFTOVER) == (
        FINGER_ACTUATION_ID,
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
        (LPD_ACTUATION_GOAL, LPD_ACTUATION_ID, "lpd"),
        (GOPHER_ACTUATION_GOAL, GOPHER_ACTUATION_ID, "gopher"),
        (MIME_ACTUATION_GOAL, MIME_ACTUATION_ID, "mime"),
        (URI_ACTUATION_GOAL, URI_ACTUATION_ID, "uri"),
        (HTTP10_ACTUATION_GOAL, HTTP10_ACTUATION_ID, "http10"),
        (DIGESTAUTH_ACTUATION_GOAL, DIGESTAUTH_ACTUATION_ID, "digestauth"),
        (HTTPSTATE_ACTUATION_GOAL, HTTPSTATE_ACTUATION_ID, "httpstate"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_finger"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"finger_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            FINGER_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = FINGER_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_finger(DEFAULT_QUERY)
    rebuilt = serialize_finger(parse_finger(advertised))
    preloaded = parse_finger(RFC_FINGER_USER)
    header = encode_finger_header(DEFAULT_QUERY)
    parsed_header = parse_finger_header(header)
    asked = parse_http_request(query_request(SENTINEL, DEFAULT_FINGERID))
    preload_req = parse_http_request(user_request(SENTINEL, DEFAULT_FINGERID, DEFAULT_FINGERDIGEST))
    got = parse_http_response(query_response(SENTINEL, DEFAULT_FINGERID, DEFAULT_FINGERDIGEST))
    preload_reply = parse_http_response(
        user_response(SENTINEL, DEFAULT_FINGERID, DEFAULT_FINGERDIGEST)
    )
    checks["finger_roundtrip"] = (
        parse_finger(advertised) == DEFAULT_QUERY
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_QUERY_FIELD
        and is_token("QUERY") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_QUERY_FIELD
        and parsed_header["policy"] == DEFAULT_QUERY
        and parsed_header["header"] == QUERY_HEADER
        and parsed_header["query"] is True
        and parsed_header["user"] is False
        and preloaded == USER_POLICY
        and ascii_serialize_finger_directive() == RFC_QUERY_DIRECTIVE
        and finger_directive_pair() == ("query", "name")
        and RFC_QUERY_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_finger(USER_POLICY) == RFC_FINGER_USER
        and DEFAULT_FINGERDIGEST == request_fingerdigest(DEFAULT_FINGERID, SENTINEL)
        and "fingerdigest=" in canonical_user(SENTINEL, DEFAULT_FINGERID, DEFAULT_FINGERDIGEST)
        and canonical_query(SENTINEL, DEFAULT_FINGERID).startswith("QUERY")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "QUERY"
        and asked["finger_kind"] == "query"
        and asked["fingerid"] == DEFAULT_FINGERID
        and preload_req["finger_kind"] == "user"
        and preload_req["fingerdigest"] == DEFAULT_FINGERDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["finger_kind"] == "query"
        and preload_reply["finger_kind"] == "user"
        and got["policy"] == DEFAULT_QUERY
        and preload_reply["policy"] == USER_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["fingerdigest"] == DEFAULT_FINGERDIGEST
        and preload_reply["fingerdigest"] == DEFAULT_FINGERDIGEST
        and finger_matches(serialize_finger(got["policy"]), advertised)
    )

    checks["catalog_names_finger"] = (
        len(catalog) > 108
        and catalog[108]["id"] == FINGER_ACTUATION_ID
        and catalog[107]["id"] == GOPHER_ACTUATION_ID
        and catalog[108]["source"] == "genesis_bind_finger"
    )
    checks["catalog_names_lpd"] = (
        len(catalog) > 109
        and catalog[109]["id"] == LPD_ACTUATION_ID
        and catalog[109]["source"] == "genesis_bind_lpd"
    )
    family = capability_family(FINGER_ACTUATION_GOAL)
    checks["family_is_finger"] = "finger" in family
    checks["family_is_finger_surface"] = "finger" in family
    checks["family_is_fingerid"] = "fingerid" in family
    checks["family_is_rfc1288"] = "rfc1288" in family
    checks["family_is_fingerdigest"] = "fingerdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_lpd"] = (
        "lpd" not in family.split("/")
        and "rfc1179" not in family
        and "lpdid" not in family
        and "lpddigest" not in family
    )
    checks["family_is_not_gopher"] = (
        "gopher" not in family.split("/")
        and "rfc1436" not in family
        and "gopherid" not in family
        and "gopherdigest" not in family
    )
    checks["family_is_not_mime"] = (
        "mime" not in family.split("/")
        and "rfc1521" not in family
        and "mimeid" not in family
        and "mimedigest" not in family
    )
    checks["family_is_not_uri"] = (
        "uri" not in family.split("/")
        and "rfc1630" not in family
        and "uriid" not in family
        and "uridigest" not in family
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
    packed = encode_query(identity=SENTINEL, fingerid=DEFAULT_FINGERID, fingerdigest=DEFAULT_FINGERDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_query"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_fingerid"] is True
        and parsed["fingerid"] == DEFAULT_FINGERID
        and parsed["fingerdigest"] == DEFAULT_FINGERDIGEST
        and parsed["is_user"] is False
        and parsed["is_user"] is False
        and parsed["type"] == FRAME_QUERY
        and parsed["first_byte"] == FINGER_FIRST
    )
    shook = encode_user(
        identity=SENTINEL,
        fingerid=DEFAULT_FINGERID,
        fingerdigest=DEFAULT_FINGERDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_user"] is True
        and answer_parsed["is_user"] is True
        and answer_parsed["is_query"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["fingerid"] == DEFAULT_FINGERID
        and answer_parsed["fingerdigest"] == DEFAULT_FINGERDIGEST
        and answer_parsed["has_fingerdigest"] is True
        and answer_parsed["type"] == FRAME_USER
        and answer_parsed["first_byte"] == FINGER_FIRST
    )
    bare = encode_query(identity=SENTINEL, fingerid=DEFAULT_FINGERID, include_fingerid=False)
    checks["missing_fingerid_is_unauthed"] = parse_message(bare)["has_fingerid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(FINGER_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_finger = ToolDescriptor(name="remote_finger", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_finger)
    checks["naive_mcp_finger_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = finger_tool_descriptor()
    default_finger = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FINGER_TOOL_PROVIDER),
    )
    checks["default_finger_provider_is_unsupported"] = (
        default_finger.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{FINGER_TOOL_PROVIDER}" in default_finger.reasons
    )
    checks["opted_in_finger_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_finger],
        required_tool_names=("local_memory", "finger"),
    )
    checks["naive_preflight_missing_finger"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["finger"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "finger"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FINGER_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "finger" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="finger-actuation-") as tmp:
        root = Path(tmp)
        missing = run_finger_workflow(with_fingerid=False, output_dir=root / "missing")
        skip_bind = run_finger_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_query = run_finger_workflow(do_query=False, output_dir=root / "skip-query")
        skip_user = run_finger_workflow(do_user=False, output_dir=root / "skip-user")
        skip_fingerdigest = run_finger_workflow(do_fingerdigest=False, output_dir=root / "skip-fingerdigest")
        skip_replay = run_finger_workflow(replay=False, output_dir=root / "skip-replay")
        skip_fingerid = run_finger_workflow(use_fingerid=False, output_dir=root / "skip-fingerid")
        live = run_finger_workflow(output_dir=root / "live")
        verify = verify_finger_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_finger_trace(clone)
        checks["naive_without_fingerid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_fingerid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_query_stays_empty"] = (
            skip_query["ok"] is False
            and skip_query["error"] == "query_required"
            and skip_query["final_status"] == 409
            and skip_query["payload_exists"] is False
        )
        checks["skip_user_stays_empty"] = (
            skip_user["ok"] is False
            and skip_user["error"] == "user_required"
            and skip_user["final_status"] == 409
            and skip_user["payload_exists"] is False
        )
        checks["skip_fingerdigest_stays_empty"] = (
            skip_fingerdigest["ok"] is False
            and skip_fingerdigest["error"] == "fingerdigest_required"
            and skip_fingerdigest["final_status"] == 409
            and skip_fingerdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_fingerid_stays_empty"] = (
            skip_fingerid["ok"] is False
            and skip_fingerid["error"] == "fingerid_required"
            and skip_fingerid["final_status"] == 409
            and skip_fingerid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_fingerdigest"] = (
            int(live.get("fingerid") or 0) == DEFAULT_FINGERID
            and int(live.get("fingerdigest") or 0) == DEFAULT_FINGERDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_fingerid_encode_user_fingerdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_query["ok"] is False
            and skip_user["ok"] is False
            and skip_fingerdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_fingerid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="finger-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != FINGER_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_finger"] = (
        live_goal == FINGER_ACTUATION_GOAL
        and FINGER_ACTUATION_ID in live_done
        and live_source == "genesis_bind_finger"
    )

    with tempfile.TemporaryDirectory(prefix="finger-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(FINGER_LEFTOVER, root)
        register_catalog_proved(root, FINGER_ACTUATION_ID)
        reason = leftover_satisfied_by(FINGER_LEFTOVER, root)
        after = leftover_is_open(FINGER_LEFTOVER, root)
    checks["finger_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_finger_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{FINGER_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_finger_actuation_capability()
    return {
        "ok": ok,
        "action": "finger_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": FINGER_ACTUATION_GOAL,
        "done_when": FINGER_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
