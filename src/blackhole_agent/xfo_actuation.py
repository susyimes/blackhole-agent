"""Drive a first-class X-Frame-Options tool through RFC 7034 DENY/SAMEORIGIN.

Tool routing already fails missions that require ``xfo``: hosted
xfo endpoints stay on the unsupported MCP provider, and no first-party
xfo provider is executable. Unbound therefore cannot speak a DENY,
lockstep a SAMEORIGIN frameid handshake over HTTP X-Frame-Options FRAMEID,
independently poll the stored framedigest, or seal a framedigest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``xfo`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 7034 daemon
- keep a missing-frameid client so the xfo-frameid hole stays falsifiable
- refuse SAMEORIGIN until a DENY lands with a non-empty frameid
- independently poll the stored framedigest on a later client socket
- persist a sealed framedigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9163 Expect-CT
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
    XFO_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    xfo_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
XFO_ACTUATION_ID = "capability.xfo-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-XFO-OK"
POLL_TOKEN = "BH-XFO-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_FRAMEID = 0
EMPTY_FRAMEDIGEST = 0
XF_FIRST = 0x58  # RFC 7034 X-Frame-Options (ASCII 'X')
FRAMEID_SIZE = 4
FRAMEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_SAMEORIGIN = 0x02  # RFC 7034 report confirmation
FRAME_DENY = 0x01  # RFC 7034 X-Frame-Options
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
XFO_LEFTOVER = (
    "Later genesis can take RFC 7034 X-Frame-Options DENY/SAMEORIGIN over a "
    "frameid-gated framedigest."
)
XFO_ACTUATION_DONE_WHEN = (
    f"capability_exists:{XFO_ACTUATION_ID};"
    f"capability_proved:{XFO_ACTUATION_ID};"
    "no_skill_route"
)
XFO_ACTUATION_GOAL = (
    "Repair rfc7034 xfo deny/sameorigin cycle cannot land over http "
    "xfo frameid: hosted xfo endpoints remain unsupported so a DENY then "
    "SAMEORIGIN frameid handshake cannot land and a sealed framedigest "
    "cannot be produced. A missing xfo frameid stays forbidden; fail-closed "
    "routing never opts the xfo provider in. An independent later poll of the "
    "stored framedigest keeps the hole falsifiable."
)


class XfoActuationError(RuntimeError):
    """Raised when the X-Frame-Options session or loopback daemon fixture misbehaves."""


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
# RFC 7034 section 2.1 X-Frame-Options directives (DENY / SAMEORIGIN / ALLOW-FROM).
RFC_XFO_ALLOW_FROM_ORIGIN = "https://example.com"
RFC_XFO_FIELD = "DENY"
RFC_XFO_SAMEORIGIN = "SAMEORIGIN"
RFC_XFO_ALLOW_FROM = f"ALLOW-FROM {RFC_XFO_ALLOW_FROM_ORIGIN}"
DEFAULT_XFO = "DENY"
SAMEORIGIN_XFO = "SAMEORIGIN"
XFO_HEADER = "X-Frame-Options"
XFO_SAMEORIGIN_HEADER = "X-Frame-Options"


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise XfoActuationError("short_xfo")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 7034 directive-name."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_xfo(policy: str | Sequence[str]) -> str:
    """Serialize RFC 7034 X-Frame-Options field-value."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise XfoActuationError("illegal_xfo")
    upper = text.upper()
    if upper == "DENY":
        return "DENY"
    if upper == "SAMEORIGIN":
        return "SAMEORIGIN"
    if upper.startswith("ALLOW-FROM"):
        parts = text.split(None, 1)
        if len(parts) != 2 or not parts[1].strip():
            raise XfoActuationError("illegal_xfo")
        return f"ALLOW-FROM {parts[1].strip()}"
    raise XfoActuationError("illegal_xfo")


def parse_xfo(text: str) -> str:
    """Parse RFC 7034 X-Frame-Options into DENY, SAMEORIGIN, or ALLOW-FROM."""

    raw = str(text or "").strip()
    if not raw:
        raise XfoActuationError("illegal_xfo")
    head = raw.split(",", 1)[0].strip()
    upper = head.upper()
    if upper == "DENY":
        return "DENY"
    if upper == "SAMEORIGIN":
        return "SAMEORIGIN"
    if upper.startswith("ALLOW-FROM"):
        parts = head.split(None, 1)
        if len(parts) != 2 or not parts[1].strip():
            raise XfoActuationError("illegal_xfo")
        return f"ALLOW-FROM {parts[1].strip()}"
    raise XfoActuationError("illegal_xfo")


def encode_xfo_header(policy: str | Sequence[str]) -> bytes:
    """RFC 7034 X-Frame-Options field as bytes."""

    return serialize_xfo(policy).encode("ascii")


def parse_xfo_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_xfo(field_value) if field_value else DEFAULT_XFO
    return {
        "field_value": field_value,
        "policy": policy,
        "header": XFO_HEADER,
        "directive": str(policy),
        "deny": str(policy) == "DENY",
        "sameorigin": str(policy) == "SAMEORIGIN",
    }


def canonical_deny(identity: str, frameid: int) -> str:
    """RFC 7034 DENY advertisement bound to identity and frameid."""

    return (
        f"{serialize_xfo(DEFAULT_XFO)}, "
        f"identity={identity}, frameid={int(frameid) & 0xFFFFFFFF}"
    )


def canonical_sameorigin(identity: str, frameid: int, framedigest: int | None = None) -> str:
    """RFC 7034 SAMEORIGIN confirmation of the stored X-Frame-Options policy."""

    suffix = ""
    if framedigest is not None:
        suffix = f", framedigest={int(framedigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_xfo(SAMEORIGIN_XFO)}, "
        f"identity={identity}, frameid={int(frameid) & 0xFFFFFFFF}{suffix}"
    )


def representation_sameorigin(identity: str, frameid: int, framedigest: int) -> str:
    return canonical_sameorigin(identity, frameid, framedigest)


def xfo_matches(left: str, right: str) -> bool:
    return parse_xfo(left) == parse_xfo(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise XfoActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise XfoActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise XfoActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise XfoActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def deny_request(identity: str, frameid: int) -> bytes:
    """HTTP GET that elicits RFC 7034 X-Frame-Options DENY."""

    keyid = f"{int(frameid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /xfo/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Frame-Id: {int(frameid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def sameorigin_request(identity: str, frameid: int, framedigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 7034 SAMEORIGIN confirmation of the stored X-Frame-Options policy."""

    keyid = f"{int(frameid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if framedigest is not None:
        extra = f"Frame-Digest: {int(framedigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /xfo/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Frame-Id: {int(frameid) & 0xFFFFFFFF}\r\n"
        "Sameorigin: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    xfo_kind = "sameorigin" if fields.get("sameorigin") == "1" else "deny"
    policy = parse_xfo(fields["x-frame-options"]) if fields.get("x-frame-options") else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "xfo_kind": xfo_kind,
        "policy": policy,
        "frameid": int(fields["frame-id"]) if fields.get("frame-id") else EMPTY_FRAMEID,
        "framedigest": int(fields["frame-digest"]) if fields.get("frame-digest") else EMPTY_FRAMEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def deny_response(identity: str, frameid: int, framedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 7034 X-Frame-Options DENY, carrying the stored framedigest."""

    advertised = serialize_xfo(DEFAULT_XFO)
    payload = bytes(body or canonical_deny(identity, frameid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"X-Frame-Options: {advertised}\r\n"
        f"Frame-Id: {int(frameid) & 0xFFFFFFFF}\r\n"
        f"Frame-Digest: {int(framedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/x-frame-options\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def sameorigin_response(identity: str, frameid: int, framedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 7034 X-Frame-Options SAMEORIGIN, carrying the stored SAMEORIGIN policy."""

    advertised = serialize_xfo(SAMEORIGIN_XFO)
    payload = bytes(body or representation_sameorigin(identity, frameid, framedigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"X-Frame-Options: {advertised}\r\n"
        f"Frame-Id: {int(frameid) & 0xFFFFFFFF}\r\n"
        f"Frame-Digest: {int(framedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/x-frame-options-sameorigin\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise XfoActuationError("illegal_content_length") from error
    field_value = fields.get("x-frame-options") or ""
    policy = parse_xfo(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/x-frame-options-sameorigin" or policy == SAMEORIGIN_XFO:
        status = 200
        xfo_kind = "sameorigin"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        xfo_kind = "deny"
    else:
        status = 0
        xfo_kind = "deny"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "xfo_kind": xfo_kind,
        "policy": policy,
        "frameid": int(fields["frame-id"]) if fields.get("frame-id") else EMPTY_FRAMEID,
        "framedigest": int(fields["frame-digest"]) if fields.get("frame-digest") else EMPTY_FRAMEDIGEST,
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
        raise XfoActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise XfoActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise XfoActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise XfoActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_frameid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"frameid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_frameid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-frameid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_framedigest(frameid: int = EMPTY_FRAMEID, token: str = SENTINEL) -> int:
    material = canonical_deny(token or SENTINEL, int(frameid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_FRAMEID = request_frameid(SENTINEL)
DEFAULT_FRAMEDIGEST = request_framedigest(DEFAULT_FRAMEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    frameid: int,
    framedigest: int,
    include_frameid: bool = True,
) -> bytes:
    live_frameid = int(frameid) & 0xFFFFFFFF if include_frameid else EMPTY_FRAMEID
    live_digest = int(framedigest) & 0xFFFFFFFF if include_frameid and live_frameid else EMPTY_FRAMEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_frameid) if live_frameid else b""
    header = bytearray()
    header.append(XF_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_deny(
    *,
    identity: str,
    frameid: int,
    framedigest: int | None = None,
    include_frameid: bool = True,
) -> bytes:
    live_frameid = int(frameid) & 0xFFFFFFFF if include_frameid else EMPTY_FRAMEID
    live_digest = int(framedigest) if framedigest is not None else request_framedigest(live_frameid, identity)
    return encode_packet(
        FRAME_DENY,
        identity=identity,
        frameid=live_frameid,
        framedigest=live_digest,
        include_frameid=include_frameid,
    )


def encode_sameorigin(
    *,
    identity: str,
    frameid: int,
    framedigest: int | None = None,
    include_frameid: bool = True,
) -> bytes:
    live_frameid = int(frameid) & 0xFFFFFFFF if include_frameid else EMPTY_FRAMEID
    live_digest = int(framedigest) if framedigest is not None else request_framedigest(live_frameid, identity)
    return encode_packet(
        FRAME_SAMEORIGIN,
        identity=identity,
        frameid=live_frameid,
        framedigest=live_digest,
        include_frameid=include_frameid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise XfoActuationError("short_packet")
    first = raw[0]
    if first != XF_FIRST:
        raise XfoActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise XfoActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == FRAMEID_SIZE:
        live_frameid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_frameid = EMPTY_FRAMEID
    else:
        raise XfoActuationError("illegal_frameid")
    if offset >= len(raw):
        raise XfoActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_DENY, FRAME_SAMEORIGIN}:
        raise XfoActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise XfoActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise XfoActuationError("checksum_failed")
    if len(payload) < 5:
        raise XfoActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise XfoActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_frameid = int(live_frameid) != EMPTY_FRAMEID
    has_framedigest = has_frameid and int(live_digest) != EMPTY_FRAMEDIGEST
    is_deny = frame_type == FRAME_DENY
    is_sameorigin = frame_type == FRAME_SAMEORIGIN
    return {
        "type": int(frame_type),
        "is_deny": is_deny,
        "is_sameorigin": is_sameorigin,
        "is_response": is_sameorigin,
        "frameid": int(live_frameid),
        "has_frameid": has_frameid,
        "framedigest": int(live_digest),
        "has_framedigest": has_framedigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "x_frame_options": "RFC7034",
        "deny_field": canonical_deny(identity, live_frameid) if has_frameid else "",
        "sameorigin_field": canonical_sameorigin(identity, live_frameid, live_digest) if has_framedigest else "",
    }


class XfoClient:
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
            raise XfoActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_sameorigin"] or not packet["is_response"]:
            raise XfoActuationError("framedigest_required")
        if not packet["has_frameid"]:
            raise XfoActuationError("frameid_required")
        if not packet["has_framedigest"]:
            raise XfoActuationError("framedigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_framedigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_framedigest:
            raise XfoActuationError("framedigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "frameid": int(reply.get("frameid") or EMPTY_FRAMEID),
            "identity": str(reply.get("identity") or ""),
            "framedigest": int(reply.get("framedigest") or EMPTY_FRAMEDIGEST),
        }

    def report(
        self,
        identity: str,
        frameid: int,
        framedigest: int = EMPTY_FRAMEDIGEST,
        *,
        wait_framedigest: bool = True,
        include_frameid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_sameorigin(
            identity=identity,
            frameid=frameid,
            framedigest=framedigest or request_framedigest(frameid, identity),
            include_frameid=include_frameid,
        )
        return self.exchange(packet, wait_framedigest=wait_framedigest)


class XfoSession:
    """FRAMEID-gated loopback RFC 7034 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        frameid_gate: int = DEFAULT_FRAMEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frameid_gate = int(frameid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.frameid = EMPTY_FRAMEID
        self.framedigest = EMPTY_FRAMEDIGEST
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

    def store_frameid_once(self, identity: str, frameid: int, framedigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(frameid or EMPTY_FRAMEID)
            live_digest = int(framedigest or EMPTY_FRAMEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.frameid = live
                self.framedigest = live_digest or request_framedigest(live, name)
                self.stored = True
            return str(self.identity), int(self.frameid), int(self.framedigest)

    def read_frameid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.frameid), int(self.framedigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "frameid": EMPTY_FRAMEID,
            "framedigest": EMPTY_FRAMEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _frameid_missing(self) -> bool:
        return not int(self.frameid_gate or 0)

    def _reply_sameorigin(self, peer: tuple[str, int], identity: str, frameid: int, framedigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_sameorigin(
            identity=identity,
            frameid=frameid,
            framedigest=framedigest,
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
            except XfoActuationError:
                continue
            if not packet.get("is_deny") and not packet.get("is_sameorigin"):
                continue
            if not packet.get("has_frameid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_frameid, stored_digest = self.store_frameid_once(
                identity,
                int(packet.get("frameid") or EMPTY_FRAMEID),
                int(packet.get("framedigest") or EMPTY_FRAMEDIGEST),
            )
            if not stored_name or not stored_frameid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_deny"):
                    self.opened = True
                if packet.get("is_sameorigin"):
                    self.handshook = True
                self.retrieved = True
            self._reply_sameorigin(peer, stored_name, stored_frameid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._frameid_missing():
            return self._forbidden("missing_frameid")
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
        do_deny: bool = True,
        do_sameorigin: bool = True,
        do_framedigest: bool = True,
        replay: bool = True,
        use_frameid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._frameid_missing():
            return self._forbidden("missing_frameid")
        live_token = str(token or SENTINEL)
        origin_frameid = request_frameid(live_token)
        origin_digest = request_framedigest(origin_frameid, live_token)
        client: XfoClient | None = None
        independent: XfoClient | None = None
        try:
            client = XfoClient(self.host, int(self.port))
            if not do_deny:
                return self._conflict("deny_required")
            bind_packet = encode_deny(
                identity=live_token,
                frameid=origin_frameid,
                framedigest=origin_digest,
                include_frameid=use_frameid,
            )
            if not use_frameid:
                try:
                    client.exchange(bind_packet, wait_framedigest=True)
                except XfoActuationError:
                    return self._conflict("frameid_required")
                return self._conflict("frameid_required")
            client.send(bind_packet)
            if not do_sameorigin:
                return self._conflict("sameorigin_required")
            proxy_packet = encode_sameorigin(
                identity=live_token,
                frameid=origin_frameid,
                framedigest=origin_digest,
                include_frameid=True,
            )
            if not do_framedigest:
                try:
                    client.exchange(proxy_packet, wait_framedigest=False)
                except XfoActuationError as error:
                    if str(error) == "framedigest_required":
                        return self._conflict("framedigest_required")
                    return self._conflict("framedigest_required")
                return self._conflict("framedigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_framedigest=True)
            except XfoActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("frameid_required")
                if reason == "framedigest_required":
                    return self._conflict("framedigest_required")
                return self._conflict("deny_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("deny_required")
            if int(reply.get("frameid") or EMPTY_FRAMEID) != origin_frameid:
                return self._conflict("framedigest_required")
            if int(reply.get("framedigest") or EMPTY_FRAMEDIGEST) != origin_digest:
                return self._conflict("framedigest_required")
            self.retrieved = True
            if replay:
                independent = XfoClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_frameid(live_token),
                        request_framedigest(poll_frameid(live_token), POLL_TOKEN),
                        wait_framedigest=True,
                    )
                except XfoActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_frameid, stored_digest = self.read_frameid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_frameid != origin_frameid
                    or stored_digest != origin_digest
                    or int(poll.get("frameid") or EMPTY_FRAMEID) != origin_frameid
                    or int(poll.get("framedigest") or EMPTY_FRAMEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_frameid}:{origin_digest}:{live_token}:{canonical_deny(live_token, origin_frameid)}:{canonical_sameorigin(live_token, origin_frameid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "frameid": origin_frameid,
                "framedigest": origin_digest,
                "deny_frame": True,
                "sameorigin_frame": True,
                "framedigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "frameid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_xfo_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "frameid": origin_frameid,
                "framedigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "deny_frame": True,
                "sameorigin_frame": True,
                "framedigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "frameid_bound": True,
            }
        except (OSError, XfoActuationError) as error:
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
        live = independent_xfo_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "frameid": int(live.get("frameid") or EMPTY_FRAMEID),
            "framedigest": int(live.get("framedigest") or EMPTY_FRAMEDIGEST),
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


def call_xfo_tool(session: XfoSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one X-Frame-Options tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_deny = True if arguments.get("deny") is None else bool(arguments.get("deny"))
    do_sameorigin = True if arguments.get("sameorigin") is None else bool(arguments.get("sameorigin"))
    do_framedigest = True if arguments.get("framedigest") is None else bool(arguments.get("framedigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_frameid = True if arguments.get("use_frameid") is None else bool(arguments.get("use_frameid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_deny=do_deny,
            do_sameorigin=do_sameorigin,
            do_framedigest=do_framedigest,
            replay=replay,
            use_frameid=use_frameid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise XfoActuationError(f"unsupported xfo action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_xfo_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed X-Frame-Options framedigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "frameid": EMPTY_FRAMEID,
        "framedigest": EMPTY_FRAMEDIGEST,
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
            "deny_frame",
            "sameorigin_frame",
            "framedigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "frameid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    frameid = int(payload.get("frameid") or EMPTY_FRAMEID)
    framedigest = int(payload.get("framedigest") or EMPTY_FRAMEDIGEST)
    dual = port > 0 and bool(frameid) and bool(framedigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "frameid": frameid,
        "framedigest": framedigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "deny_frame": payload.get("deny_frame") is True,
        "sameorigin_frame": payload.get("sameorigin_frame") is True,
        "framedigest_response": payload.get("framedigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "frameid_bound": payload.get("frameid_bound") is True,
    }


def run_xfo_workflow(
    *,
    with_frameid: bool = True,
    skip_bind: bool = False,
    do_deny: bool = True,
    do_sameorigin: bool = True,
    do_framedigest: bool = True,
    replay: bool = True,
    use_frameid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 7034 DENY/SAMEORIGIN frameid cycle workflow."""

    descriptor = xfo_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, XFO_TOOL_PROVIDER),
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
        raise XfoActuationError(f"xfo tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="xfo-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = XfoSession(out, frameid_gate=DEFAULT_FRAMEID if with_frameid else EMPTY_FRAMEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "deny": do_deny,
            "sameorigin": do_sameorigin,
            "framedigest": do_framedigest,
            "replay": replay,
            "use_frameid": use_frameid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_xfo_tool(session, arguments))
            except XfoActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_xfo_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_frameid
        and not skip_bind
        and do_deny
        and do_sameorigin
        and do_framedigest
        and replay
        and use_frameid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "xfo_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_frameid": with_frameid,
        "skip_bind": skip_bind,
        "deny_frame": do_deny,
        "sameorigin": do_sameorigin,
        "framedigest": do_framedigest,
        "replay": replay,
        "use_frameid": use_frameid,
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
        "frameid_value": int(publish_result.get("frameid") or independent.get("frameid") or EMPTY_FRAMEID),
        "framedigest_value": int(publish_result.get("framedigest") or independent.get("framedigest") or EMPTY_FRAMEDIGEST),
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
        "frameid": int(trace_body["frameid_value"] or EMPTY_FRAMEID),
        "framedigest": int(trace_body["framedigest_value"] or EMPTY_FRAMEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_frameid": with_frameid,
        "skip_bind": skip_bind,
        "deny_cycle": do_deny,
        "sameorigin_cycle": do_sameorigin,
        "framedigest_cycle": do_framedigest,
        "replay": replay,
        "use_frameid": use_frameid,
    }


def verify_xfo_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed X-Frame-Options trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_xfo_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    frameid = int(trace.get("frameid_value") or independent.get("frameid") or EMPTY_FRAMEID)
    framedigest = int(trace.get("framedigest_value") or independent.get("framedigest") or EMPTY_FRAMEDIGEST)
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
        "deny_frame": independent.get("deny_frame") is True,
        "sameorigin_frame": independent.get("sameorigin_frame") is True,
        "framedigest_response": independent.get("framedigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "frameid_bound": independent.get("frameid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "framedigest_recorded": (
            port > 0
            and frameid == DEFAULT_FRAMEID
            and framedigest == DEFAULT_FRAMEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def xfo_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.xfo_actuation import "
        "builtin_xfo_actuation_proof; r=builtin_xfo_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='xfo_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_xfo_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=XFO_ACTUATION_ID,
        name="First-class RFC 7034 X-Frame-Options DENY/SAMEORIGIN actuation",
        description=(
            "Missions that require an xfo tool can opt the xfo provider in, "
            "bind a loopback RFC 7034 X-Frame-Options origin, complete a DENY "
            "with a non-empty frameid, lockstep a SAMEORIGIN that carries the "
            "stored framedigest, independently poll the stored framedigest "
            "on a later socket, and seal a digest-chained framedigest. Default "
            "routing stays fail-closed; a missing frameid keeps the hole "
            "falsifiable, and skip-DENY/SAMEORIGIN/FRAMEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.xfo_actuation:builtin_xfo_actuation_proof",
        proof_command=xfo_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.expectct-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/xfo_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/expectct_actuation.py",
            "src/blackhole_agent/weborigin_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required xfo tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 7034 daemon, speaks a "
            "DENY then SAMEORIGIN over X-Frame-Options with a non-empty frameid and "
            "framedigest, independently polls the stored framedigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9163 Expect-CT lockstep is proved. "
            "Missing frameids, skip-DENY, skip-SAMEORIGIN, skip-framedigest, skip-REPLAY, "
            "and a DENY aimed without a frameid stay fail-closed. "
            "Later genesis can take RFC 6454 The Web Origin Concept SERIALIZE/TUPLE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("xfo", "rfc7034", "http", "frameid", "framedigest", "deny", "sameorigin", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T162450Z-a21828a1",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_xfo_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 7034 X-Frame-Options lockstep actuation seals a framedigest."""

    from blackhole_agent.weborigin_actuation import (
        WEBORIGIN_ACTUATION_GOAL,
        WEBORIGIN_ACTUATION_ID,
    )
    from blackhole_agent.expectct_actuation import (
        EXPECTCT_ACTUATION_GOAL,
        EXPECTCT_ACTUATION_ID,
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
    checks["denylists_self"] = XFO_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(XFO_ACTUATION_GOAL) == (
        XFO_ACTUATION_ID,
    )
    checks["leftover_text_binds_xfo"] = leftover_marker_ids(XFO_LEFTOVER) == (
        XFO_ACTUATION_ID,
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
        (EXPECTCT_ACTUATION_GOAL, EXPECTCT_ACTUATION_ID, "expectct"),
        (WEBORIGIN_ACTUATION_GOAL, WEBORIGIN_ACTUATION_ID, "weborigin"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_xfo"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"xfo_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            XFO_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = XFO_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_xfo(DEFAULT_XFO)
    rebuilt = serialize_xfo(parse_xfo(advertised))
    preloaded = parse_xfo(RFC_XFO_SAMEORIGIN)
    header = encode_xfo_header(DEFAULT_XFO)
    parsed_header = parse_xfo_header(header)
    asked = parse_http_request(deny_request(SENTINEL, DEFAULT_FRAMEID))
    preload_req = parse_http_request(sameorigin_request(SENTINEL, DEFAULT_FRAMEID, DEFAULT_FRAMEDIGEST))
    got = parse_http_response(deny_response(SENTINEL, DEFAULT_FRAMEID, DEFAULT_FRAMEDIGEST))
    preload_reply = parse_http_response(
        sameorigin_response(SENTINEL, DEFAULT_FRAMEID, DEFAULT_FRAMEDIGEST)
    )
    checks["xfo_roundtrip"] = (
        parse_xfo(advertised) == DEFAULT_XFO
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_XFO_FIELD
        and is_token("DENY") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_XFO_FIELD
        and parsed_header["policy"] == DEFAULT_XFO
        and parsed_header["header"] == XFO_HEADER
        and parsed_header["deny"] is True
        and parsed_header["sameorigin"] is False
        and preloaded == SAMEORIGIN_XFO
    )
    checks["sameorigin_roundtrip"] = (
        serialize_xfo(SAMEORIGIN_XFO) == RFC_XFO_SAMEORIGIN
        and DEFAULT_FRAMEDIGEST == request_framedigest(DEFAULT_FRAMEID, SENTINEL)
        and "framedigest=" in canonical_sameorigin(SENTINEL, DEFAULT_FRAMEID, DEFAULT_FRAMEDIGEST)
        and canonical_deny(SENTINEL, DEFAULT_FRAMEID).startswith("DENY")
    )
    checks["deny_sameorigin_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["xfo_kind"] == "deny"
        and asked["frameid"] == DEFAULT_FRAMEID
        and preload_req["xfo_kind"] == "sameorigin"
        and preload_req["framedigest"] == DEFAULT_FRAMEDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["xfo_kind"] == "deny"
        and preload_reply["xfo_kind"] == "sameorigin"
        and got["policy"] == DEFAULT_XFO
        and preload_reply["policy"] == SAMEORIGIN_XFO
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["framedigest"] == DEFAULT_FRAMEDIGEST
        and preload_reply["framedigest"] == DEFAULT_FRAMEDIGEST
        and xfo_matches(serialize_xfo(got["policy"]), advertised)
    )

    checks["catalog_names_xfo"] = (
        len(catalog) > 84
        and catalog[84]["id"] == XFO_ACTUATION_ID
        and catalog[83]["id"] == EXPECTCT_ACTUATION_ID
        and catalog[84]["source"] == "genesis_bind_xfo"
    )
    checks["catalog_names_weborigin"] = (
        len(catalog) > 85
        and catalog[85]["id"] == WEBORIGIN_ACTUATION_ID
        and catalog[85]["source"] == "genesis_bind_weborigin"
    )
    family = capability_family(XFO_ACTUATION_GOAL)
    checks["family_is_xfo"] = "xfo" in family
    checks["family_is_xfo_surface"] = "xfo" in family
    checks["family_is_frameid"] = "frameid" in family
    checks["family_is_rfc7034"] = "rfc7034" in family
    checks["family_is_framedigest"] = "framedigest" in family
    checks["family_is_not_weborigin"] = (
        "weborigin" not in family
        and "rfc6454" not in family
        and "tupleid" not in family
        and "tupledigest" not in family
    )
    checks["family_is_not_expectct"] = (
        "expectct" not in family
        and "rfc9163" not in family
        and "ctid" not in family
        and "ctdigest" not in family
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
    packed = encode_deny(identity=SENTINEL, frameid=DEFAULT_FRAMEID, framedigest=DEFAULT_FRAMEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_deny"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_frameid"] is True
        and parsed["frameid"] == DEFAULT_FRAMEID
        and parsed["framedigest"] == DEFAULT_FRAMEDIGEST
        and parsed["is_response"] is False
        and parsed["is_sameorigin"] is False
        and parsed["type"] == FRAME_DENY
        and parsed["first_byte"] == XF_FIRST
    )
    shook = encode_sameorigin(
        identity=SENTINEL,
        frameid=DEFAULT_FRAMEID,
        framedigest=DEFAULT_FRAMEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_sameorigin"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_deny"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["frameid"] == DEFAULT_FRAMEID
        and answer_parsed["framedigest"] == DEFAULT_FRAMEDIGEST
        and answer_parsed["has_framedigest"] is True
        and answer_parsed["type"] == FRAME_SAMEORIGIN
        and answer_parsed["first_byte"] == XF_FIRST
    )
    bare = encode_deny(identity=SENTINEL, frameid=DEFAULT_FRAMEID, include_frameid=False)
    checks["missing_frameid_is_unauthenticated"] = parse_message(bare)["has_frameid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    xfo_signature = semantic_signature(XFO_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(xfo_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_xfo = ToolDescriptor(name="remote_xfo", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_xfo)
    checks["naive_mcp_xfo_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = xfo_tool_descriptor()
    default_xfo = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, XFO_TOOL_PROVIDER),
    )
    checks["default_xfo_provider_is_unsupported"] = (
        default_xfo.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{XFO_TOOL_PROVIDER}" in default_xfo.reasons
    )
    checks["opted_in_xfo_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_xfo],
        required_tool_names=("local_memory", "xfo"),
    )
    checks["naive_preflight_missing_xfo"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["xfo"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "xfo"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, XFO_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "xfo" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="xfo-actuation-") as tmp:
        root = Path(tmp)
        missing = run_xfo_workflow(with_frameid=False, output_dir=root / "missing")
        skip_bind = run_xfo_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_deny = run_xfo_workflow(do_deny=False, output_dir=root / "skip-deny")
        skip_preload = run_xfo_workflow(do_sameorigin=False, output_dir=root / "skip-sameorigin")
        skip_framedigest = run_xfo_workflow(do_framedigest=False, output_dir=root / "skip-framedigest")
        skip_replay = run_xfo_workflow(replay=False, output_dir=root / "skip-replay")
        skip_frameid = run_xfo_workflow(use_frameid=False, output_dir=root / "skip-frameid")
        live = run_xfo_workflow(output_dir=root / "live")
        verify = verify_xfo_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_xfo_trace(clone)
        checks["naive_without_frameid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_frameid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_deny_stays_empty"] = (
            skip_deny["ok"] is False
            and skip_deny["error"] == "deny_required"
            and skip_deny["final_status"] == 409
            and skip_deny["payload_exists"] is False
        )
        checks["skip_sameorigin_stays_empty"] = (
            skip_preload["ok"] is False
            and skip_preload["error"] == "sameorigin_required"
            and skip_preload["final_status"] == 409
            and skip_preload["payload_exists"] is False
        )
        checks["skip_framedigest_stays_empty"] = (
            skip_framedigest["ok"] is False
            and skip_framedigest["error"] == "framedigest_required"
            and skip_framedigest["final_status"] == 409
            and skip_framedigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_frameid_stays_empty"] = (
            skip_frameid["ok"] is False
            and skip_frameid["error"] == "frameid_required"
            and skip_frameid["final_status"] == 409
            and skip_frameid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_framedigest"] = (
            int(live.get("frameid") or 0) == DEFAULT_FRAMEID
            and int(live.get("framedigest") or 0) == DEFAULT_FRAMEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_frameid_encode_sameorigin_framedigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_deny["ok"] is False
            and skip_preload["ok"] is False
            and skip_framedigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_frameid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="xfo-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != XFO_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_xfo"] = (
        live_goal == XFO_ACTUATION_GOAL
        and XFO_ACTUATION_ID in live_done
        and live_source == "genesis_bind_xfo"
    )

    with tempfile.TemporaryDirectory(prefix="xfo-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(XFO_LEFTOVER, root)
        register_catalog_proved(root, XFO_ACTUATION_ID)
        reason = leftover_satisfied_by(XFO_LEFTOVER, root)
        after = leftover_is_open(XFO_LEFTOVER, root)
    checks["xfo_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_xfo_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{XFO_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_xfo_actuation_capability()
    return {
        "ok": ok,
        "action": "xfo_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": XFO_ACTUATION_GOAL,
        "done_when": XFO_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
