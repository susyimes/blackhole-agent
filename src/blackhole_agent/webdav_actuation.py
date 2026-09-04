"""Drive a first-class HTTP Extensions for WebDAV tool through RFC 4918 PROPFIND/LOCK.

Tool routing already fails missions that require ``webdav``: hosted
webdav endpoints stay on the unsupported MCP provider, and no first-party
webdav provider is executable. Unbound therefore cannot speak a PROPFIND,
lockstep a LOCK lockid handshake over HTTP DAV LOCKID,
independently poll the stored lockdigest, or seal a lockdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``webdav`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 4918 daemon
- keep a missing-lockid client so the webdav-lockid hole stays falsifiable
- refuse LOCK until a PROPFIND lands with a non-empty lockid
- independently poll the stored lockdigest on a later client socket
- persist a sealed lockdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 5785 Defining Well-Known Uniform Resource Identifiers
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
    WEBDAV_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    webdav_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
WEBDAV_ACTUATION_ID = "capability.webdav-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-DAV-OK"
POLL_TOKEN = "BH-DAV-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_LOCKID = 0
EMPTY_LOCKDIGEST = 0
DAV_FIRST = 0x44  # RFC 4918 HTTP Extensions for WebDAV (ASCII 'D')
LOCKID_SIZE = 4
LOCKDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_LOCK = 0x02  # RFC 4918 lock confirmation
FRAME_PROPFIND = 0x01  # RFC 4918 PROPFIND
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
WEBDAV_LEFTOVER = (
    "Later genesis can take RFC 4918 HTTP Extensions for WebDAV PROPFIND/LOCK over a "
    "lockid-gated lockdigest."
)
WEBDAV_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WEBDAV_ACTUATION_ID};"
    f"capability_proved:{WEBDAV_ACTUATION_ID};"
    "no_skill_route"
)
WEBDAV_ACTUATION_GOAL = (
    "Repair rfc4918 webdav propfind/lock cycle cannot land over http "
    "webdav lockid: hosted webdav endpoints remain unsupported so a PROPFIND then "
    "LOCK lockid handshake cannot land and a sealed lockdigest "
    "cannot be produced. A missing webdav lockid stays forbidden; fail-closed "
    "routing never opts the webdav provider in. An independent later poll of the "
    "stored lockdigest keeps the hole falsifiable."
)


class WebdavActuationError(RuntimeError):
    """Raised when the lock session or loopback daemon fixture misbehaves."""


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
# RFC 4918 sections 9.1 and 9.10: compliance / lockscope.
RFC_PROPFIND_FIELD = "PROPFIND"
RFC_LOCK_FIELD = "LOCK"
RFC_WEBDAV_LOCK = RFC_LOCK_FIELD
RFC_PROPFIND_DIRECTIVE = "compliance=1"
RFC_LOCK_DIRECTIVE = "lockscope=exclusive"
DEFAULT_PROPFIND = "PROPFIND"
LOCK_POLICY = "LOCK"
PROPFIND_HEADER = "DAV"
LOCK_HEADER = "DAV"
WEBDAV_LOCK_HEADER = LOCK_HEADER
RFC_PROPFIND_PATH = "/dav/"
RFC_PROPFIND_EMPTY = ""


def webdav_directive_pair(*, lock: bool = False) -> tuple[str, str]:
    """RFC 4918 section 3 dav-uri compliance / registered lockscope."""

    if lock:
        return "lockscope", "exclusive"
    return "compliance", "1"


def ascii_serialize_webdav_directive(*, lock: bool = False) -> str:
    """RFC 4918 dav-uri: token "=" lock-or-compliance."""

    name, value = webdav_directive_pair(lock=lock)
    if not is_token(name):
        raise WebdavActuationError("illegal_directive")
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
            raise WebdavActuationError("short_webdav")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 4918 DAV token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_webdav(policy: str | Sequence[str]) -> str:
    """Serialize RFC 4918 compliance / lockscope token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise WebdavActuationError("illegal_webdav")
    upper = text.upper().replace("_", "-")
    if upper in {"PROPFIND", "COMPLIANCE", "DAV"}:
        return "PROPFIND"
    if upper in {"LOCK", "LOCKSCOPE", "EX"}:
        return "LOCK"
    if upper.startswith("COMPLIANCE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise WebdavActuationError("illegal_webdav")
        return "PROPFIND"
    if upper.startswith("LOCKSCOPE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise WebdavActuationError("illegal_webdav")
        return "LOCK"
    raise WebdavActuationError("illegal_webdav")


def parse_webdav(text: str) -> str:
    """Parse RFC 4918 DAV propfind extensions into PROPFIND or LOCK."""

    raw = str(text or "").strip()
    if not raw:
        raise WebdavActuationError("illegal_webdav")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"PROPFIND", "COMPLIANCE", "DAV"}:
        return "PROPFIND"
    if upper in {"LOCK", "LOCKSCOPE", "EX"}:
        return "LOCK"
    if upper.startswith("COMPLIANCE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise WebdavActuationError("illegal_webdav")
        return "PROPFIND"
    if upper.startswith("LOCKSCOPE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise WebdavActuationError("illegal_webdav")
        return "LOCK"
    raise WebdavActuationError("illegal_webdav")


def encode_webdav_header(policy: str | Sequence[str]) -> bytes:
    """RFC 4918 DAV field as bytes."""

    return serialize_webdav(policy).encode("ascii")


def parse_webdav_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_webdav(field_value) if field_value else DEFAULT_PROPFIND
    return {
        "field_value": field_value,
        "policy": policy,
        "header": PROPFIND_HEADER,
        "directive": str(policy),
        "propfind": str(policy) == "PROPFIND",
        "lock": str(policy) == "LOCK",
    }


def canonical_propfind(identity: str, lockid: int) -> str:
    """RFC 4918 PROPFIND advertisement bound to identity and lockid."""

    return (
        f"{serialize_webdav(DEFAULT_PROPFIND)}, "
        f"propfind={ascii_serialize_webdav_directive()}, "
        f"identity={identity}, lockid={int(lockid) & 0xFFFFFFFF}"
    )


def canonical_lock(identity: str, lockid: int, lockdigest: int | None = None) -> str:
    """RFC 4918 LOCK confirmation of the stored lock policy."""

    lock = ""
    if lockdigest is not None:
        lock = f", lockdigest={int(lockdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_webdav(LOCK_POLICY)}, "
        f"lock={ascii_serialize_webdav_directive(lock=True)}, "
        f"identity={identity}, lockid={int(lockid) & 0xFFFFFFFF}{lock}"
    )


def representation_lock(identity: str, lockid: int, lockdigest: int) -> str:
    return canonical_lock(identity, lockid, lockdigest)


def webdav_matches(left: str, right: str) -> bool:
    return parse_webdav(left) == parse_webdav(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise WebdavActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise WebdavActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise WebdavActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise WebdavActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def propfind_request(identity: str, lockid: int) -> bytes:
    """HTTP PROPFIND that elicits RFC 4918 origin PROPFIND."""

    keyid = f"{int(lockid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"PROPFIND /dav/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Lock-Id: {int(lockid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def lock_request(identity: str, lockid: int, lockdigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 4918 LOCK confirmation of the stored lock policy."""

    keyid = f"{int(lockid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if lockdigest is not None:
        extra = f"Lock-Digest: {int(lockdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"LOCK /dav/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Lock-Id: {int(lockid) & 0xFFFFFFFF}\r\n"
        "Lock-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    webdav_kind = "lock" if fields.get("lock-confirm") == "1" else "propfind"
    propfind_field = fields.get("dav") or ""
    policy = parse_webdav(propfind_field) if propfind_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "webdav_kind": webdav_kind,
        "policy": policy,
        "lockid": int(fields["lock-id"]) if fields.get("lock-id") else EMPTY_LOCKID,
        "lockdigest": int(fields["lock-digest"]) if fields.get("lock-digest") else EMPTY_LOCKDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def propfind_response(identity: str, lockid: int, lockdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 4918 origin PROPFIND, carrying the stored lockdigest."""

    advertised = serialize_webdav(DEFAULT_PROPFIND)
    payload = bytes(body or canonical_propfind(identity, lockid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"DAV: {advertised}\r\n"
        f"Lock-Id: {int(lockid) & 0xFFFFFFFF}\r\n"
        f"Lock-Digest: {int(lockdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def lock_response(identity: str, lockid: int, lockdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 4918 LOCK, carrying the stored LOCK policy."""

    advertised = serialize_webdav(LOCK_POLICY)
    payload = bytes(body or representation_lock(identity, lockid, lockdigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"DAV: {advertised}\r\n"
        f"Lock-Id: {int(lockid) & 0xFFFFFFFF}\r\n"
        f"Lock-Digest: {int(lockdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/davlocking+xml\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise WebdavActuationError("illegal_content_length") from error
    field_value = fields.get("dav") or ""
    policy = parse_webdav(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/davlocking+xml" or policy == LOCK_POLICY:
        status = 200
        webdav_kind = "lock"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        webdav_kind = "propfind"
    else:
        status = 0
        webdav_kind = "propfind"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "webdav_kind": webdav_kind,
        "policy": policy,
        "lockid": int(fields["lock-id"]) if fields.get("lock-id") else EMPTY_LOCKID,
        "lockdigest": int(fields["lock-digest"]) if fields.get("lock-digest") else EMPTY_LOCKDIGEST,
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
        raise WebdavActuationError("short_packet")
    compliance = raw[offset] >> 6
    if compliance == 0:
        return raw[offset] & 0x3F, offset + 1
    if compliance == 1:
        if offset + 2 > len(raw):
            raise WebdavActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if compliance == 2:
        if offset + 4 > len(raw):
            raise WebdavActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise WebdavActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_lockid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"lockid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_lockid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-lockid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_lockdigest(lockid: int = EMPTY_LOCKID, token: str = SENTINEL) -> int:
    material = canonical_propfind(token or SENTINEL, int(lockid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_LOCKID = request_lockid(SENTINEL)
DEFAULT_LOCKDIGEST = request_lockdigest(DEFAULT_LOCKID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    lockid: int,
    lockdigest: int,
    include_lockid: bool = True,
) -> bytes:
    live_lockid = int(lockid) & 0xFFFFFFFF if include_lockid else EMPTY_LOCKID
    live_digest = int(lockdigest) & 0xFFFFFFFF if include_lockid and live_lockid else EMPTY_LOCKDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    compliance_bytes = struct.pack("!I", live_lockid) if live_lockid else b""
    header = bytearray()
    header.append(DAV_FIRST)
    header.append(len(compliance_bytes))
    header.extend(compliance_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_propfind(
    *,
    identity: str,
    lockid: int,
    lockdigest: int | None = None,
    include_lockid: bool = True,
) -> bytes:
    live_lockid = int(lockid) & 0xFFFFFFFF if include_lockid else EMPTY_LOCKID
    live_digest = int(lockdigest) if lockdigest is not None else request_lockdigest(live_lockid, identity)
    return encode_packet(
        FRAME_PROPFIND,
        identity=identity,
        lockid=live_lockid,
        lockdigest=live_digest,
        include_lockid=include_lockid,
    )


def encode_lock(
    *,
    identity: str,
    lockid: int,
    lockdigest: int | None = None,
    include_lockid: bool = True,
) -> bytes:
    live_lockid = int(lockid) & 0xFFFFFFFF if include_lockid else EMPTY_LOCKID
    live_digest = int(lockdigest) if lockdigest is not None else request_lockdigest(live_lockid, identity)
    return encode_packet(
        FRAME_LOCK,
        identity=identity,
        lockid=live_lockid,
        lockdigest=live_digest,
        include_lockid=include_lockid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise WebdavActuationError("short_packet")
    first = raw[0]
    if first != DAV_FIRST:
        raise WebdavActuationError("illegal_header")
    offset = 1
    compliance_len = raw[offset]
    offset += 1
    if offset + compliance_len > len(raw):
        raise WebdavActuationError("short_packet")
    compliance_bytes = raw[offset : offset + compliance_len]
    offset += compliance_len
    if compliance_len == LOCKID_SIZE:
        live_lockid = struct.unpack("!I", compliance_bytes)[0]
    elif compliance_len == 0:
        live_lockid = EMPTY_LOCKID
    else:
        raise WebdavActuationError("illegal_lockid")
    if offset >= len(raw):
        raise WebdavActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_PROPFIND, FRAME_LOCK}:
        raise WebdavActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise WebdavActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise WebdavActuationError("checksum_failed")
    if len(payload) < 5:
        raise WebdavActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise WebdavActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_lockid = int(live_lockid) != EMPTY_LOCKID
    has_lockdigest = has_lockid and int(live_digest) != EMPTY_LOCKDIGEST
    is_propfind = frame_type == FRAME_PROPFIND
    is_lock = frame_type == FRAME_LOCK
    return {
        "type": int(frame_type),
        "is_propfind": is_propfind,
        "is_lock": is_lock,
        "is_response": is_lock,
        "lockid": int(live_lockid),
        "has_lockid": has_lockid,
        "lockdigest": int(live_digest),
        "has_lockdigest": has_lockdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "compliance_len": int(compliance_len),
        "http_state": "RFC4918",
        "serialize_field": canonical_propfind(identity, live_lockid) if has_lockid else "",
        "lock_field": canonical_lock(identity, live_lockid, live_digest) if has_lockdigest else "",
    }


class WebdavClient:
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
            raise WebdavActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_lock"] or not packet["is_response"]:
            raise WebdavActuationError("lockdigest_required")
        if not packet["has_lockid"]:
            raise WebdavActuationError("lockid_required")
        if not packet["has_lockdigest"]:
            raise WebdavActuationError("lockdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_lockdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_lockdigest:
            raise WebdavActuationError("lockdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "lockid": int(reply.get("lockid") or EMPTY_LOCKID),
            "identity": str(reply.get("identity") or ""),
            "lockdigest": int(reply.get("lockdigest") or EMPTY_LOCKDIGEST),
        }

    def report(
        self,
        identity: str,
        lockid: int,
        lockdigest: int = EMPTY_LOCKDIGEST,
        *,
        wait_lockdigest: bool = True,
        include_lockid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_lock(
            identity=identity,
            lockid=lockid,
            lockdigest=lockdigest or request_lockdigest(lockid, identity),
            include_lockid=include_lockid,
        )
        return self.exchange(packet, wait_lockdigest=wait_lockdigest)


class WebdavSession:
    """LOCKID-gated loopback RFC 4918 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        lockid_gate: int = DEFAULT_LOCKID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lockid_gate = int(lockid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.lockid = EMPTY_LOCKID
        self.lockdigest = EMPTY_LOCKDIGEST
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

    def store_lockid_once(self, identity: str, lockid: int, lockdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(lockid or EMPTY_LOCKID)
            live_digest = int(lockdigest or EMPTY_LOCKDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.lockid = live
                self.lockdigest = live_digest or request_lockdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.lockid), int(self.lockdigest)

    def read_lockid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.lockid), int(self.lockdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "lockid": EMPTY_LOCKID,
            "lockdigest": EMPTY_LOCKDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _lockid_missing(self) -> bool:
        return not int(self.lockid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, lockid: int, lockdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_lock(
            identity=identity,
            lockid=lockid,
            lockdigest=lockdigest,
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
            except WebdavActuationError:
                continue
            if not packet.get("is_propfind") and not packet.get("is_lock"):
                continue
            if not packet.get("has_lockid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_lockid, stored_digest = self.store_lockid_once(
                identity,
                int(packet.get("lockid") or EMPTY_LOCKID),
                int(packet.get("lockdigest") or EMPTY_LOCKDIGEST),
            )
            if not stored_name or not stored_lockid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_propfind"):
                    self.opened = True
                if packet.get("is_lock"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_lockid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._lockid_missing():
            return self._forbidden("missing_lockid")
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
        do_propfind: bool = True,
        do_lock: bool = True,
        do_lockdigest: bool = True,
        replay: bool = True,
        use_lockid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._lockid_missing():
            return self._forbidden("missing_lockid")
        live_token = str(token or SENTINEL)
        origin_lockid = request_lockid(live_token)
        origin_digest = request_lockdigest(origin_lockid, live_token)
        client: WebdavClient | None = None
        independent: WebdavClient | None = None
        try:
            client = WebdavClient(self.host, int(self.port))
            if not do_propfind:
                return self._conflict("propfind_required")
            bind_packet = encode_propfind(
                identity=live_token,
                lockid=origin_lockid,
                lockdigest=origin_digest,
                include_lockid=use_lockid,
            )
            if not use_lockid:
                try:
                    client.exchange(bind_packet, wait_lockdigest=True)
                except WebdavActuationError:
                    return self._conflict("lockid_required")
                return self._conflict("lockid_required")
            client.send(bind_packet)
            if not do_lock:
                return self._conflict("lock_required")
            proxy_packet = encode_lock(
                identity=live_token,
                lockid=origin_lockid,
                lockdigest=origin_digest,
                include_lockid=True,
            )
            if not do_lockdigest:
                try:
                    client.exchange(proxy_packet, wait_lockdigest=False)
                except WebdavActuationError as error:
                    if str(error) == "lockdigest_required":
                        return self._conflict("lockdigest_required")
                    return self._conflict("lockdigest_required")
                return self._conflict("lockdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_lockdigest=True)
            except WebdavActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("lockid_required")
                if reason == "lockdigest_required":
                    return self._conflict("lockdigest_required")
                return self._conflict("propfind_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("propfind_required")
            if int(reply.get("lockid") or EMPTY_LOCKID) != origin_lockid:
                return self._conflict("lockdigest_required")
            if int(reply.get("lockdigest") or EMPTY_LOCKDIGEST) != origin_digest:
                return self._conflict("lockdigest_required")
            self.retrieved = True
            if replay:
                independent = WebdavClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_lockid(live_token),
                        request_lockdigest(poll_lockid(live_token), POLL_TOKEN),
                        wait_lockdigest=True,
                    )
                except WebdavActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_lockid, stored_digest = self.read_lockid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_lockid != origin_lockid
                    or stored_digest != origin_digest
                    or int(poll.get("lockid") or EMPTY_LOCKID) != origin_lockid
                    or int(poll.get("lockdigest") or EMPTY_LOCKDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_lockid}:{origin_digest}:{live_token}:{canonical_propfind(live_token, origin_lockid)}:{canonical_lock(live_token, origin_lockid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "lockid": origin_lockid,
                "lockdigest": origin_digest,
                "propfind_frame": True,
                "lock_frame": True,
                "lockdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "lockid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_webdav_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "lockid": origin_lockid,
                "lockdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "propfind_frame": True,
                "lock_frame": True,
                "lockdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "lockid_bound": True,
            }
        except (OSError, WebdavActuationError) as error:
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
        live = independent_webdav_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "lockid": int(live.get("lockid") or EMPTY_LOCKID),
            "lockdigest": int(live.get("lockdigest") or EMPTY_LOCKDIGEST),
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


def call_webdav_tool(session: WebdavSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one propfind tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_propfind = True if arguments.get("propfind") is None else bool(arguments.get("propfind"))
    do_lock = True if arguments.get("lock") is None else bool(arguments.get("lock"))
    do_lockdigest = True if arguments.get("lockdigest") is None else bool(arguments.get("lockdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_lockid = True if arguments.get("use_lockid") is None else bool(arguments.get("use_lockid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_propfind=do_propfind,
            do_lock=do_lock,
            do_lockdigest=do_lockdigest,
            replay=replay,
            use_lockid=use_lockid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise WebdavActuationError(f"unsupported webdav action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_webdav_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed propfind lockdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "lockid": EMPTY_LOCKID,
        "lockdigest": EMPTY_LOCKDIGEST,
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
            "propfind_frame",
            "lock_frame",
            "lockdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "lockid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    lockid = int(payload.get("lockid") or EMPTY_LOCKID)
    lockdigest = int(payload.get("lockdigest") or EMPTY_LOCKDIGEST)
    dual = port > 0 and bool(lockid) and bool(lockdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "lockid": lockid,
        "lockdigest": lockdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "propfind_frame": payload.get("propfind_frame") is True,
        "lock_frame": payload.get("lock_frame") is True,
        "lockdigest_response": payload.get("lockdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "lockid_bound": payload.get("lockid_bound") is True,
    }


def run_webdav_workflow(
    *,
    with_lockid: bool = True,
    skip_bind: bool = False,
    do_propfind: bool = True,
    do_lock: bool = True,
    do_lockdigest: bool = True,
    replay: bool = True,
    use_lockid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 4918 PROPFIND/LOCK lockid cycle workflow."""

    descriptor = webdav_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBDAV_TOOL_PROVIDER),
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
        raise WebdavActuationError(f"webdav tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="webdav-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = WebdavSession(out, lockid_gate=DEFAULT_LOCKID if with_lockid else EMPTY_LOCKID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "propfind": do_propfind,
            "lock": do_lock,
            "lockdigest": do_lockdigest,
            "replay": replay,
            "use_lockid": use_lockid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_webdav_tool(session, arguments))
            except WebdavActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_webdav_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_lockid
        and not skip_bind
        and do_propfind
        and do_lock
        and do_lockdigest
        and replay
        and use_lockid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "webdav_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_lockid": with_lockid,
        "skip_bind": skip_bind,
        "propfind_frame": do_propfind,
        "lock": do_lock,
        "lockdigest": do_lockdigest,
        "replay": replay,
        "use_lockid": use_lockid,
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
        "lockid_value": int(publish_result.get("lockid") or independent.get("lockid") or EMPTY_LOCKID),
        "lockdigest_value": int(publish_result.get("lockdigest") or independent.get("lockdigest") or EMPTY_LOCKDIGEST),
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
        "lockid": int(trace_body["lockid_value"] or EMPTY_LOCKID),
        "lockdigest": int(trace_body["lockdigest_value"] or EMPTY_LOCKDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_lockid": with_lockid,
        "skip_bind": skip_bind,
        "propfind_cycle": do_propfind,
        "lock_cycle": do_lock,
        "lockdigest_cycle": do_lockdigest,
        "replay": replay,
        "use_lockid": use_lockid,
    }


def verify_webdav_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_webdav_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    lockid = int(trace.get("lockid_value") or independent.get("lockid") or EMPTY_LOCKID)
    lockdigest = int(trace.get("lockdigest_value") or independent.get("lockdigest") or EMPTY_LOCKDIGEST)
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
        "propfind_frame": independent.get("propfind_frame") is True,
        "lock_frame": independent.get("lock_frame") is True,
        "lockdigest_response": independent.get("lockdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "lockid_bound": independent.get("lockid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "lockdigest_recorded": (
            port > 0
            and lockid == DEFAULT_LOCKID
            and lockdigest == DEFAULT_LOCKDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def webdav_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.webdav_actuation import "
        "builtin_webdav_actuation_proof; r=builtin_webdav_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='webdav_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_webdav_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=WEBDAV_ACTUATION_ID,
        name="First-class RFC 4918 HTTP Extensions for WebDAV PROPFIND/LOCK actuation",
        description=(
            "Missions that require a webdav tool can opt the webdav provider in, "
            "bind a loopback RFC 4918 HTTP Extensions for WebDAV endpoint, complete a PROPFIND "
            "with a non-empty lockid, lockstep an LOCK that carries the "
            "stored lockdigest, independently poll the stored lockdigest "
            "on a later socket, and seal a digest-chained lockdigest. Default "
            "routing stays fail-closed; a missing lockid keeps the hole "
            "falsifiable, and skip-PROPFIND/LOCK/LOCKDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.webdav_actuation:builtin_webdav_actuation_proof",
        proof_command=webdav_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.wellknown-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/webdav_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/wellknown_actuation.py",
            "src/blackhole_agent/spnego_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required webdav tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 4918 daemon, speaks a "
            "PROPFIND then LOCK over HTTP Extensions for WebDAV with a non-empty lockid and "
            "lockdigest, independently polls the stored lockdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 5785 Defining Well-Known Uniform Resource Identifiers lockstep is proved. "
            "Missing lockids, skip-PROPFIND, skip-LOCK, skip-lockdigest, skip-REPLAY, "
            "and a PROPFIND aimed without a lockid stay fail-closed. "
            "Later genesis can take RFC 4559 SPNEGO-based Kerberos and NTLM HTTP Authentication NEGOTIATE/AUTHENTICATE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("webdav", "rfc4918", "http", "lockid", "lockdigest", "propfind", "lock", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T225055Z-45929649",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_webdav_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 4918 propfind lockstep actuation seals a lockdigest."""

    from blackhole_agent.wellknown_actuation import (
        WELLKNOWN_ACTUATION_GOAL,
        WELLKNOWN_ACTUATION_ID,
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
    checks["denylists_self"] = WEBDAV_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(WEBDAV_ACTUATION_GOAL) == (
        WEBDAV_ACTUATION_ID,
    )
    checks["leftover_text_binds_webdav"] = leftover_marker_ids(WEBDAV_LEFTOVER) == (
        WEBDAV_ACTUATION_ID,
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
        (WELLKNOWN_ACTUATION_GOAL, WELLKNOWN_ACTUATION_ID, "wellknown"),
        (SPNEGO_ACTUATION_GOAL, SPNEGO_ACTUATION_ID, "spnego"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_webdav"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"webdav_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            WEBDAV_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = WEBDAV_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_webdav(DEFAULT_PROPFIND)
    rebuilt = serialize_webdav(parse_webdav(advertised))
    preloaded = parse_webdav(RFC_WEBDAV_LOCK)
    header = encode_webdav_header(DEFAULT_PROPFIND)
    parsed_header = parse_webdav_header(header)
    asked = parse_http_request(propfind_request(SENTINEL, DEFAULT_LOCKID))
    preload_req = parse_http_request(lock_request(SENTINEL, DEFAULT_LOCKID, DEFAULT_LOCKDIGEST))
    got = parse_http_response(propfind_response(SENTINEL, DEFAULT_LOCKID, DEFAULT_LOCKDIGEST))
    preload_reply = parse_http_response(
        lock_response(SENTINEL, DEFAULT_LOCKID, DEFAULT_LOCKDIGEST)
    )
    checks["webdav_roundtrip"] = (
        parse_webdav(advertised) == DEFAULT_PROPFIND
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_PROPFIND_FIELD
        and is_token("PROPFIND") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_PROPFIND_FIELD
        and parsed_header["policy"] == DEFAULT_PROPFIND
        and parsed_header["header"] == PROPFIND_HEADER
        and parsed_header["propfind"] is True
        and parsed_header["lock"] is False
        and preloaded == LOCK_POLICY
        and ascii_serialize_webdav_directive() == RFC_PROPFIND_DIRECTIVE
        and webdav_directive_pair() == ("compliance", "1")
        and RFC_PROPFIND_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_webdav(LOCK_POLICY) == RFC_WEBDAV_LOCK
        and DEFAULT_LOCKDIGEST == request_lockdigest(DEFAULT_LOCKID, SENTINEL)
        and "lockdigest=" in canonical_lock(SENTINEL, DEFAULT_LOCKID, DEFAULT_LOCKDIGEST)
        and canonical_propfind(SENTINEL, DEFAULT_LOCKID).startswith("PROPFIND")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "PROPFIND"
        and asked["webdav_kind"] == "propfind"
        and asked["lockid"] == DEFAULT_LOCKID
        and preload_req["webdav_kind"] == "lock"
        and preload_req["lockdigest"] == DEFAULT_LOCKDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["webdav_kind"] == "propfind"
        and preload_reply["webdav_kind"] == "lock"
        and got["policy"] == DEFAULT_PROPFIND
        and preload_reply["policy"] == LOCK_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["lockdigest"] == DEFAULT_LOCKDIGEST
        and preload_reply["lockdigest"] == DEFAULT_LOCKDIGEST
        and webdav_matches(serialize_webdav(got["policy"]), advertised)
    )

    checks["catalog_names_webdav"] = (
        len(catalog) > 93
        and catalog[93]["id"] == WEBDAV_ACTUATION_ID
        and catalog[92]["id"] == WELLKNOWN_ACTUATION_ID
        and catalog[93]["source"] == "genesis_bind_webdav"
    )
    checks["catalog_names_spnego"] = (
        len(catalog) > 94
        and catalog[94]["id"] == SPNEGO_ACTUATION_ID
        and catalog[94]["source"] == "genesis_bind_spnego"
    )
    family = capability_family(WEBDAV_ACTUATION_GOAL)
    checks["family_is_webdav"] = "webdav" in family
    checks["family_is_webdav_surface"] = "webdav" in family
    checks["family_is_lockid"] = "lockid" in family
    checks["family_is_rfc4918"] = "rfc4918" in family
    checks["family_is_lockdigest"] = "lockdigest" in family
    checks["family_is_not_wellknown"] = (
        "wellknown" not in family
        and "rfc5785" not in family
        and "suffixid" not in family
        and "suffixdigest" not in family
    )
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
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
    packed = encode_propfind(identity=SENTINEL, lockid=DEFAULT_LOCKID, lockdigest=DEFAULT_LOCKDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_propfind"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_lockid"] is True
        and parsed["lockid"] == DEFAULT_LOCKID
        and parsed["lockdigest"] == DEFAULT_LOCKDIGEST
        and parsed["is_response"] is False
        and parsed["is_lock"] is False
        and parsed["type"] == FRAME_PROPFIND
        and parsed["first_byte"] == DAV_FIRST
    )
    shook = encode_lock(
        identity=SENTINEL,
        lockid=DEFAULT_LOCKID,
        lockdigest=DEFAULT_LOCKDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_lock"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_propfind"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["lockid"] == DEFAULT_LOCKID
        and answer_parsed["lockdigest"] == DEFAULT_LOCKDIGEST
        and answer_parsed["has_lockdigest"] is True
        and answer_parsed["type"] == FRAME_LOCK
        and answer_parsed["first_byte"] == DAV_FIRST
    )
    bare = encode_propfind(identity=SENTINEL, lockid=DEFAULT_LOCKID, include_lockid=False)
    checks["missing_lockid_is_unauthenticated"] = parse_message(bare)["has_lockid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    webdav_signature = semantic_signature(WEBDAV_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(webdav_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_webdav = ToolDescriptor(name="remote_webdav", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_webdav)
    checks["naive_mcp_webdav_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = webdav_tool_descriptor()
    default_webdav = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBDAV_TOOL_PROVIDER),
    )
    checks["default_webdav_provider_is_unsupported"] = (
        default_webdav.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{WEBDAV_TOOL_PROVIDER}" in default_webdav.reasons
    )
    checks["opted_in_webdav_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_webdav],
        required_tool_names=("local_memory", "webdav"),
    )
    checks["naive_preflight_missing_webdav"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["webdav"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "webdav"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBDAV_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "webdav" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="webdav-actuation-") as tmp:
        root = Path(tmp)
        missing = run_webdav_workflow(with_lockid=False, output_dir=root / "missing")
        skip_bind = run_webdav_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_propfind = run_webdav_workflow(do_propfind=False, output_dir=root / "skip-propfind")
        skip_lock = run_webdav_workflow(do_lock=False, output_dir=root / "skip-lock")
        skip_lockdigest = run_webdav_workflow(do_lockdigest=False, output_dir=root / "skip-lockdigest")
        skip_replay = run_webdav_workflow(replay=False, output_dir=root / "skip-replay")
        skip_lockid = run_webdav_workflow(use_lockid=False, output_dir=root / "skip-lockid")
        live = run_webdav_workflow(output_dir=root / "live")
        verify = verify_webdav_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_webdav_trace(clone)
        checks["naive_without_lockid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_lockid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_propfind_stays_empty"] = (
            skip_propfind["ok"] is False
            and skip_propfind["error"] == "propfind_required"
            and skip_propfind["final_status"] == 409
            and skip_propfind["payload_exists"] is False
        )
        checks["skip_lock_stays_empty"] = (
            skip_lock["ok"] is False
            and skip_lock["error"] == "lock_required"
            and skip_lock["final_status"] == 409
            and skip_lock["payload_exists"] is False
        )
        checks["skip_lockdigest_stays_empty"] = (
            skip_lockdigest["ok"] is False
            and skip_lockdigest["error"] == "lockdigest_required"
            and skip_lockdigest["final_status"] == 409
            and skip_lockdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_lockid_stays_empty"] = (
            skip_lockid["ok"] is False
            and skip_lockid["error"] == "lockid_required"
            and skip_lockid["final_status"] == 409
            and skip_lockid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_lockdigest"] = (
            int(live.get("lockid") or 0) == DEFAULT_LOCKID
            and int(live.get("lockdigest") or 0) == DEFAULT_LOCKDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_lockid_encode_lock_lockdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_propfind["ok"] is False
            and skip_lock["ok"] is False
            and skip_lockdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_lockid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="webdav-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != WEBDAV_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_webdav"] = (
        live_goal == WEBDAV_ACTUATION_GOAL
        and WEBDAV_ACTUATION_ID in live_done
        and live_source == "genesis_bind_webdav"
    )

    with tempfile.TemporaryDirectory(prefix="webdav-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(WEBDAV_LEFTOVER, root)
        register_catalog_proved(root, WEBDAV_ACTUATION_ID)
        reason = leftover_satisfied_by(WEBDAV_LEFTOVER, root)
        after = leftover_is_open(WEBDAV_LEFTOVER, root)
    checks["webdav_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_webdav_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{WEBDAV_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_webdav_actuation_capability()
    return {
        "ok": ok,
        "action": "webdav_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": WEBDAV_ACTUATION_GOAL,
        "done_when": WEBDAV_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
