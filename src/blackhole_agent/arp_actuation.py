"""Drive a first-class Address Resolution Protocol tool through RFC 826 REQUEST/REPLY.

Tool routing already fails missions that require ``arp``: hosted
arp endpoints stay on the unsupported MCP provider, and no first-party
arp provider is executable. Unbound therefore cannot speak a REQUEST,
lockstep a REPLY arpid handshake over HTTP/1.0 ARPID,
independently poll the stored arpdigest, or seal an arpdigest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``arp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 826 daemon
- keep a missing-arpid client so the arp-arpid hole stays falsifiable
- refuse REPLY until a REQUEST lands with a non-empty arpid
- independently poll the stored arpdigest on a later client socket
- persist a sealed arpdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 791 Internet Protocol
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
    ARP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    arp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
ARP_ACTUATION_ID = "capability.arp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-ARP-OK"
POLL_TOKEN = "BH-ARP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_ARPID = 0
EMPTY_ARPDIGEST = 0
ARP_FIRST = 0x08  # RFC 826 ARP (EtherType 0x0806)
ARPID_SIZE = 4
ARPDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_REPLY = 0x02  # RFC 826 REPLY confirmation
FRAME_REQUEST = 0x01  # RFC 826 REQUEST
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
ARP_LEFTOVER = (
    "Later genesis can take RFC 826 Address Resolution Protocol REQUEST/REPLY over an "
    "arpid-gated arpdigest."
)
ARP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ARP_ACTUATION_ID};"
    f"capability_proved:{ARP_ACTUATION_ID};"
    "no_skill_route"
)
ARP_ACTUATION_GOAL = (
    "Repair rfc826 arp request/reply cycle cannot land over http "
    "arp arpid: hosted arp endpoints remain unsupported so a REQUEST then "
    "REPLY arpid handshake cannot land and a sealed arpdigest "
    "cannot be produced. A missing arp arpid stays forbidden; fail-closed "
    "routing never opts the arp provider in. An independent later poll of the "
    "stored arpdigest keeps the hole falsifiable."
)


class ArpActuationError(RuntimeError):
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
# RFC 826 sections 3.3 and 3.4: REQUEST / REPLY.
RFC_REQUEST_FIELD = "REQUEST"
RFC_REPLY_FIELD = "REPLY"
RFC_ARP_REPLY = RFC_REPLY_FIELD
RFC_REQUEST_DIRECTIVE = "request=message"
RFC_REPLY_DIRECTIVE = "reply=message"
DEFAULT_REQUEST = "REQUEST"
REPLY_POLICY = "REPLY"
REQUEST_HEADER = "Request"
REPLY_HEADER = "Reply"
ARP_REPLY_HEADER = REPLY_HEADER
RFC_REQUEST_PATH = "/arp/"
RFC_REQUEST_EMPTY = ""


def arp_directive_pair(*, reply: bool = False) -> tuple[str, str]:
    """RFC 826 Request / Reply directive pair."""

    if reply:
        return "reply", "message"
    return "request", "message"


def ascii_serialize_arp_directive(*, reply: bool = False) -> str:
    """RFC 826 token "=" body-or-reply."""

    name, value = arp_directive_pair(reply=reply)
    if not is_token(name):
        raise ArpActuationError("illegal_directive")
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
            raise ArpActuationError("short_arp")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 826 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_arp(policy: str | Sequence[str]) -> str:
    """Serialize RFC 826 REQUEST / REPLY opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise ArpActuationError("illegal_arp")
    upper = text.upper().replace("_", "-")
    if upper in {"REQUEST", "ARP", "ARP-REQUEST"}:
        return "REQUEST"
    if upper in {"REPLY", "RESOURCE", "ARP-REPLY"}:
        return "REPLY"
    if upper.startswith("REQUEST="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise ArpActuationError("illegal_arp")
        return "REQUEST"
    if upper.startswith("REPLY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise ArpActuationError("illegal_arp")
        return "REPLY"
    raise ArpActuationError("illegal_arp")


def parse_arp(text: str) -> str:
    """Parse RFC 826 ARP opcode header extensions into REQUEST or REPLY."""

    raw = str(text or "").strip()
    if not raw:
        raise ArpActuationError("illegal_arp")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"REQUEST", "ARP", "ARP-REQUEST"}:
        return "REQUEST"
    if upper in {"REPLY", "RESOURCE", "ARP-REPLY"}:
        return "REPLY"
    if upper.startswith("REQUEST="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise ArpActuationError("illegal_arp")
        return "REQUEST"
    if upper.startswith("REPLY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise ArpActuationError("illegal_arp")
        return "REPLY"
    raise ArpActuationError("illegal_arp")


def encode_arp_header(policy: str | Sequence[str]) -> bytes:
    """RFC 826 HTTP/1.0 field as bytes."""

    return serialize_arp(policy).encode("ascii")


def parse_arp_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_arp(field_value) if field_value else DEFAULT_REQUEST
    return {
        "field_value": field_value,
        "policy": policy,
        "header": REQUEST_HEADER,
        "directive": str(policy),
        "request": str(policy) == "REQUEST",
        "reply": str(policy) == "REPLY",
    }


def canonical_request(identity: str, arpid: int) -> str:
    """RFC 826 body-request advertisement bound to identity and arpid."""

    return (
        f"{serialize_arp(DEFAULT_REQUEST)}, "
        f"request={ascii_serialize_arp_directive()}, "
        f"identity={identity}, arpid={int(arpid) & 0xFFFFFFFF}"
    )


def canonical_reply(identity: str, arpid: int, arpdigest: int | None = None) -> str:
    """RFC 826 reply-message confirmation of the stored identifier-digest."""

    digest = ""
    if arpdigest is not None:
        digest = f", arpdigest={int(arpdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_arp(REPLY_POLICY)}, "
        f"reply={ascii_serialize_arp_directive(reply=True)}, "
        f"identity={identity}, arpid={int(arpid) & 0xFFFFFFFF}{digest}"
    )


def representation_reply(identity: str, arpid: int, arpdigest: int) -> str:
    return canonical_reply(identity, arpid, arpdigest)


def arp_matches(left: str, right: str) -> bool:
    return parse_arp(left) == parse_arp(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise ArpActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise ArpActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise ArpActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise ArpActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def request_request(identity: str, arpid: int) -> bytes:
    """HTTP REQUEST that elicits RFC 826 origin HTTP/1.0."""

    keyid = f"{int(arpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"REQUEST /arp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Arp-Id: {int(arpid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def reply_request(identity: str, arpid: int, arpdigest: int | None = None) -> bytes:
    """HTTP REPLY carrying RFC 826 reply-message confirmation of the stored identifier-digest."""

    keyid = f"{int(arpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if arpdigest is not None:
        extra = f"Arp-Digest: {int(arpdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"REPLY /arp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Arp-Id: {int(arpid) & 0xFFFFFFFF}\r\n"
        "Reply-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    arp_kind = "reply" if fields.get("reply-confirm") == "1" else "request"
    upgrade_field = fields.get("request") or fields.get("arp") or ""
    policy = parse_arp(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "arp_kind": arp_kind,
        "policy": policy,
        "arpid": int(fields["arp-id"]) if fields.get("arp-id") else EMPTY_ARPID,
        "arpdigest": int(fields["arp-digest"]) if fields.get("arp-digest") else EMPTY_ARPDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def request_response(identity: str, arpid: int, arpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 826 origin HTTP/1.0, carrying the stored arpdigest."""

    advertised = serialize_arp(DEFAULT_REQUEST)
    payload = bytes(body or canonical_request(identity, arpid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Request: {advertised}\r\n"
        f"Arp-Id: {int(arpid) & 0xFFFFFFFF}\r\n"
        f"Arp-Digest: {int(arpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def reply_response(identity: str, arpid: int, arpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 826 REPLY, carrying the stored identifier-digest."""

    advertised = serialize_arp(REPLY_POLICY)
    payload = bytes(body or representation_reply(identity, arpid, arpdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Request: {advertised}\r\n"
        f"Arp-Id: {int(arpid) & 0xFFFFFFFF}\r\n"
        f"Arp-Digest: {int(arpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/arp-reply\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise ArpActuationError("illegal_content_length") from error
    field_value = fields.get("request") or fields.get("arp") or ""
    policy = parse_arp(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/arp-reply" or policy == REPLY_POLICY:
        status = 200
        arp_kind = "reply"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        arp_kind = "request"
    else:
        status = 0
        arp_kind = "request"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "arp_kind": arp_kind,
        "policy": policy,
        "arpid": int(fields["arp-id"]) if fields.get("arp-id") else EMPTY_ARPID,
        "arpdigest": int(fields["arp-digest"]) if fields.get("arp-digest") else EMPTY_ARPDIGEST,
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
        raise ArpActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise ArpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise ArpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise ArpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc826_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    arp: str,
) -> str:
    """RFC 826 identifier digest over method, request-IP, identity, and arpid."""

    payload = f"{method}:{arp}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_arpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"arpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_arpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-arpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_arpdigest(arpid: int = EMPTY_ARPID, token: str = SENTINEL) -> int:
    nonce = f"{int(arpid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc826_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="REPLY",
        arp=f"/arp/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_ARPID = request_arpid(SENTINEL)
DEFAULT_ARPDIGEST = request_arpdigest(DEFAULT_ARPID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    arpid: int,
    arpdigest: int,
    include_arpid: bool = True,
) -> bytes:
    live_arpid = int(arpid) & 0xFFFFFFFF if include_arpid else EMPTY_ARPID
    live_digest = int(arpdigest) & 0xFFFFFFFF if include_arpid and live_arpid else EMPTY_ARPDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_arpid) if live_arpid else b""
    header = bytearray()
    header.append(ARP_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_request(
    *,
    identity: str,
    arpid: int,
    arpdigest: int | None = None,
    include_arpid: bool = True,
) -> bytes:
    live_arpid = int(arpid) & 0xFFFFFFFF if include_arpid else EMPTY_ARPID
    live_digest = int(arpdigest) if arpdigest is not None else request_arpdigest(live_arpid, identity)
    return encode_packet(
        FRAME_REQUEST,
        identity=identity,
        arpid=live_arpid,
        arpdigest=live_digest,
        include_arpid=include_arpid,
    )


def encode_reply(
    *,
    identity: str,
    arpid: int,
    arpdigest: int | None = None,
    include_arpid: bool = True,
) -> bytes:
    live_arpid = int(arpid) & 0xFFFFFFFF if include_arpid else EMPTY_ARPID
    live_digest = int(arpdigest) if arpdigest is not None else request_arpdigest(live_arpid, identity)
    return encode_packet(
        FRAME_REPLY,
        identity=identity,
        arpid=live_arpid,
        arpdigest=live_digest,
        include_arpid=include_arpid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise ArpActuationError("short_packet")
    first = raw[0]
    if first != ARP_FIRST:
        raise ArpActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise ArpActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == ARPID_SIZE:
        live_arpid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_arpid = EMPTY_ARPID
    else:
        raise ArpActuationError("illegal_arpid")
    if offset >= len(raw):
        raise ArpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_REQUEST, FRAME_REPLY}:
        raise ArpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise ArpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise ArpActuationError("checksum_failed")
    if len(payload) < 5:
        raise ArpActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise ArpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_arpid = int(live_arpid) != EMPTY_ARPID
    has_arpdigest = has_arpid and int(live_digest) != EMPTY_ARPDIGEST
    is_request = frame_type == FRAME_REQUEST
    is_reply = frame_type == FRAME_REPLY
    return {
        "type": int(frame_type),
        "is_request": is_request,
        "is_reply": is_reply,
        "arpid": int(live_arpid),
        "has_arpid": has_arpid,
        "arpdigest": int(live_digest),
        "has_arpdigest": has_arpdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC826",
        "serialize_field": canonical_request(identity, live_arpid) if has_arpid else "",
        "tls_field": canonical_reply(identity, live_arpid, live_digest) if has_arpdigest else "",
    }


class ArpClient:
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
            raise ArpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_reply"] or not packet["is_reply"]:
            raise ArpActuationError("arpdigest_required")
        if not packet["has_arpid"]:
            raise ArpActuationError("arpid_required")
        if not packet["has_arpdigest"]:
            raise ArpActuationError("arpdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_arpdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_arpdigest:
            raise ArpActuationError("arpdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "arpid": int(reply.get("arpid") or EMPTY_ARPID),
            "identity": str(reply.get("identity") or ""),
            "arpdigest": int(reply.get("arpdigest") or EMPTY_ARPDIGEST),
        }

    def report(
        self,
        identity: str,
        arpid: int,
        arpdigest: int = EMPTY_ARPDIGEST,
        *,
        wait_arpdigest: bool = True,
        include_arpid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_reply(
            identity=identity,
            arpid=arpid,
            arpdigest=arpdigest or request_arpdigest(arpid, identity),
            include_arpid=include_arpid,
        )
        return self.exchange(packet, wait_arpdigest=wait_arpdigest)


class ArpSession:
    """ARPID-gated loopback RFC 826 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        arpid_gate: int = DEFAULT_ARPID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.arpid_gate = int(arpid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.arpid = EMPTY_ARPID
        self.arpdigest = EMPTY_ARPDIGEST
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

    def store_arpid_once(self, identity: str, arpid: int, arpdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(arpid or EMPTY_ARPID)
            live_digest = int(arpdigest or EMPTY_ARPDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.arpid = live
                self.arpdigest = live_digest or request_arpdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.arpid), int(self.arpdigest)

    def read_arpid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.arpid), int(self.arpdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "arpid": EMPTY_ARPID,
            "arpdigest": EMPTY_ARPDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _arpid_missing(self) -> bool:
        return not int(self.arpid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, arpid: int, arpdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_reply(
            identity=identity,
            arpid=arpid,
            arpdigest=arpdigest,
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
            except ArpActuationError:
                continue
            if not packet.get("is_request") and not packet.get("is_reply"):
                continue
            if not packet.get("has_arpid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_arpid, stored_digest = self.store_arpid_once(
                identity,
                int(packet.get("arpid") or EMPTY_ARPID),
                int(packet.get("arpdigest") or EMPTY_ARPDIGEST),
            )
            if not stored_name or not stored_arpid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_request"):
                    self.opened = True
                if packet.get("is_reply"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_arpid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._arpid_missing():
            return self._forbidden("missing_arpid")
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
        do_request: bool = True,
        do_reply: bool = True,
        do_arpdigest: bool = True,
        replay: bool = True,
        use_arpid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._arpid_missing():
            return self._forbidden("missing_arpid")
        live_token = str(token or SENTINEL)
        origin_arpid = request_arpid(live_token)
        origin_digest = request_arpdigest(origin_arpid, live_token)
        client: ArpClient | None = None
        independent: ArpClient | None = None
        try:
            client = ArpClient(self.host, int(self.port))
            if not do_request:
                return self._conflict("request_required")
            bind_packet = encode_request(
                identity=live_token,
                arpid=origin_arpid,
                arpdigest=origin_digest,
                include_arpid=use_arpid,
            )
            if not use_arpid:
                try:
                    client.exchange(bind_packet, wait_arpdigest=True)
                except ArpActuationError:
                    return self._conflict("arpid_required")
                return self._conflict("arpid_required")
            client.send(bind_packet)
            if not do_reply:
                return self._conflict("reply_required")
            proxy_packet = encode_reply(
                identity=live_token,
                arpid=origin_arpid,
                arpdigest=origin_digest,
                include_arpid=True,
            )
            if not do_arpdigest:
                try:
                    client.exchange(proxy_packet, wait_arpdigest=False)
                except ArpActuationError as error:
                    if str(error) == "arpdigest_required":
                        return self._conflict("arpdigest_required")
                    return self._conflict("arpdigest_required")
                return self._conflict("arpdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_arpdigest=True)
            except ArpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("arpid_required")
                if reason == "arpdigest_required":
                    return self._conflict("arpdigest_required")
                return self._conflict("request_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("request_required")
            if int(reply.get("arpid") or EMPTY_ARPID) != origin_arpid:
                return self._conflict("arpdigest_required")
            if int(reply.get("arpdigest") or EMPTY_ARPDIGEST) != origin_digest:
                return self._conflict("arpdigest_required")
            self.retrieved = True
            if replay:
                independent = ArpClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_arpid(live_token),
                        request_arpdigest(poll_arpid(live_token), POLL_TOKEN),
                        wait_arpdigest=True,
                    )
                except ArpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_arpid, stored_digest = self.read_arpid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_arpid != origin_arpid
                    or stored_digest != origin_digest
                    or int(poll.get("arpid") or EMPTY_ARPID) != origin_arpid
                    or int(poll.get("arpdigest") or EMPTY_ARPDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_arpid}:{origin_digest}:{live_token}:{canonical_request(live_token, origin_arpid)}:{canonical_reply(live_token, origin_arpid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "arpid": origin_arpid,
                "arpdigest": origin_digest,
                "request_frame": True,
                "reply_frame": True,
                "arpdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "arpid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_arpdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "arpid": origin_arpid,
                "arpdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "request_frame": True,
                "reply_frame": True,
                "arpdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "arpid_bound": True,
            }
        except (OSError, ArpActuationError) as error:
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
        live = independent_arpdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "arpid": int(live.get("arpid") or EMPTY_ARPID),
            "arpdigest": int(live.get("arpdigest") or EMPTY_ARPDIGEST),
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


def call_arp_tool(session: ArpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one arp tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_request = True if arguments.get("request") is None else bool(arguments.get("request"))
    do_reply = True if arguments.get("reply") is None else bool(arguments.get("reply"))
    do_arpdigest = True if arguments.get("arpdigest") is None else bool(arguments.get("arpdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_arpid = True if arguments.get("use_arpid") is None else bool(arguments.get("use_arpid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_request=do_request,
            do_reply=do_reply,
            do_arpdigest=do_arpdigest,
            replay=replay,
            use_arpid=use_arpid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise ArpActuationError(f"unsupported arp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_arpdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage arpdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "arpid": EMPTY_ARPID,
        "arpdigest": EMPTY_ARPDIGEST,
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
            "request_frame",
            "reply_frame",
            "arpdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "arpid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    arpid = int(payload.get("arpid") or EMPTY_ARPID)
    arpdigest = int(payload.get("arpdigest") or EMPTY_ARPDIGEST)
    dual = port > 0 and bool(arpid) and bool(arpdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "arpid": arpid,
        "arpdigest": arpdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "request_frame": payload.get("request_frame") is True,
        "reply_frame": payload.get("reply_frame") is True,
        "arpdigest_locate": payload.get("arpdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "arpid_bound": payload.get("arpid_bound") is True,
    }


def run_arp_workflow(
    *,
    with_arpid: bool = True,
    skip_bind: bool = False,
    do_request: bool = True,
    do_reply: bool = True,
    do_arpdigest: bool = True,
    replay: bool = True,
    use_arpid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 826 REQUEST/REPLY arpid cycle workflow."""

    descriptor = arp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ARP_TOOL_PROVIDER),
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
        raise ArpActuationError(f"arp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="arp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = ArpSession(out, arpid_gate=DEFAULT_ARPID if with_arpid else EMPTY_ARPID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "request": do_request,
            "reply": do_reply,
            "arpdigest": do_arpdigest,
            "replay": replay,
            "use_arpid": use_arpid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_arp_tool(session, arguments))
            except ArpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_arpdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_arpid
        and not skip_bind
        and do_request
        and do_reply
        and do_arpdigest
        and replay
        and use_arpid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "arp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_arpid": with_arpid,
        "skip_bind": skip_bind,
        "request_frame": do_request,
        "reply_frame": do_reply,
        "arpdigest": do_arpdigest,
        "replay": replay,
        "use_arpid": use_arpid,
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
        "arpid_value": int(publish_result.get("arpid") or independent.get("arpid") or EMPTY_ARPID),
        "arpdigest_value": int(publish_result.get("arpdigest") or independent.get("arpdigest") or EMPTY_ARPDIGEST),
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
        "arpid": int(trace_body["arpid_value"] or EMPTY_ARPID),
        "arpdigest": int(trace_body["arpdigest_value"] or EMPTY_ARPDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_arpid": with_arpid,
        "skip_bind": skip_bind,
        "request_cycle": do_request,
        "reply_cycle": do_reply,
        "arpdigest_cycle": do_arpdigest,
        "replay": replay,
        "use_arpid": use_arpid,
    }


def verify_arp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_arpdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    arpid = int(trace.get("arpid_value") or independent.get("arpid") or EMPTY_ARPID)
    arpdigest = int(trace.get("arpdigest_value") or independent.get("arpdigest") or EMPTY_ARPDIGEST)
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
        "request_frame": independent.get("request_frame") is True,
        "reply_frame": independent.get("reply_frame") is True,
        "arpdigest_locate": independent.get("arpdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "arpid_bound": independent.get("arpid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "arpdigest_recorded": (
            port > 0
            and arpid == DEFAULT_ARPID
            and arpdigest == DEFAULT_ARPDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def arp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.arp_actuation import "
        "builtin_arp_actuation_proof; r=builtin_arp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='arp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_arp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ARP_ACTUATION_ID,
        name="First-class RFC 826 Address Resolution Protocol REQUEST/REPLY actuation",
        description=(
            "Missions that require an arp tool can opt the arp provider in, "
            "bind a loopback RFC 826 Address Resolution Protocol endpoint, complete a REQUEST "
            "with a non-empty arpid, lockstep a REPLY that carries the "
            "stored arpdigest, independently poll the stored arpdigest "
            "on a later socket, and seal a digest-chained arpdigest. Default "
            "routing stays fail-closed; a missing arpid keeps the hole "
            "falsifiable, and skip-REQUEST/REPLY/ARPDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.arp_actuation:builtin_arp_actuation_proof",
        proof_command=arp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.ip-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/arp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/ip_actuation.py",
            "src/blackhole_agent/icmp_actuation.py",
            "src/blackhole_agent/udp_actuation.py",
            "src/blackhole_agent/tcp_actuation.py",
            "src/blackhole_agent/rarp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required arp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 826 daemon, speaks a "
            "REQUEST then REPLY over Address Resolution Protocol with a non-empty arpid and "
            "arpdigest, independently polls the stored arpdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 791 Internet Protocol lockstep is proved. "
            "Missing arpids, skip-REQUEST, skip-REPLY, skip-arpdigest, skip-REPLAY, "
            "and a REQUEST aimed without an arpid stay fail-closed. "
            "Later genesis can take RFC 903 Reverse Address Resolution Protocol REVERSE/REPLY as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("arp", "rfc826", "http", "arpid", "arpdigest", "request", "reply", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T143628Z-39303da5",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_arp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 826 request/reply lockstep actuation seals an arpdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.rarp_actuation import (
        RARP_ACTUATION_GOAL,
        RARP_ACTUATION_ID,
    )
    from blackhole_agent.ip_actuation import (
        IP_ACTUATION_GOAL,
        IP_ACTUATION_ID,
    )
    from blackhole_agent.icmp_actuation import (
        ICMP_ACTUATION_GOAL,
        ICMP_ACTUATION_ID,
    )
    from blackhole_agent.udp_actuation import (
        UDP_ACTUATION_GOAL,
        UDP_ACTUATION_ID,
    )
    from blackhole_agent.tcp_actuation import (
        TCP_ACTUATION_GOAL,
        TCP_ACTUATION_ID,
    )
    from blackhole_agent.telnet_actuation import (
        TELNET_ACTUATION_GOAL,
        TELNET_ACTUATION_ID,
    )
    from blackhole_agent.finger_actuation import (
        FINGER_ACTUATION_GOAL,
        FINGER_ACTUATION_ID,
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
    checks["denylists_self"] = ARP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(ARP_ACTUATION_GOAL) == (
        ARP_ACTUATION_ID,
    )
    checks["leftover_text_binds_arp"] = leftover_marker_ids(ARP_LEFTOVER) == (
        ARP_ACTUATION_ID,
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
        (RARP_ACTUATION_GOAL, RARP_ACTUATION_ID, "rarp"),
        (IP_ACTUATION_GOAL, IP_ACTUATION_ID, "ip"),
        (ICMP_ACTUATION_GOAL, ICMP_ACTUATION_ID, "icmp"),
        (UDP_ACTUATION_GOAL, UDP_ACTUATION_ID, "udp"),
        (TCP_ACTUATION_GOAL, TCP_ACTUATION_ID, "tcp"),
        (TELNET_ACTUATION_GOAL, TELNET_ACTUATION_ID, "telnet"),
        (FINGER_ACTUATION_GOAL, FINGER_ACTUATION_ID, "finger"),
        (MIME_ACTUATION_GOAL, MIME_ACTUATION_ID, "mime"),
        (URI_ACTUATION_GOAL, URI_ACTUATION_ID, "uri"),
        (HTTP10_ACTUATION_GOAL, HTTP10_ACTUATION_ID, "http10"),
        (DIGESTAUTH_ACTUATION_GOAL, DIGESTAUTH_ACTUATION_ID, "digestauth"),
        (HTTPSTATE_ACTUATION_GOAL, HTTPSTATE_ACTUATION_ID, "httpstate"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_arp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"arp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            ARP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = ARP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_arp(DEFAULT_REQUEST)
    rebuilt = serialize_arp(parse_arp(advertised))
    preloaded = parse_arp(RFC_ARP_REPLY)
    header = encode_arp_header(DEFAULT_REQUEST)
    parsed_header = parse_arp_header(header)
    asked = parse_http_request(request_request(SENTINEL, DEFAULT_ARPID))
    preload_req = parse_http_request(reply_request(SENTINEL, DEFAULT_ARPID, DEFAULT_ARPDIGEST))
    got = parse_http_response(request_response(SENTINEL, DEFAULT_ARPID, DEFAULT_ARPDIGEST))
    preload_reply = parse_http_response(
        reply_response(SENTINEL, DEFAULT_ARPID, DEFAULT_ARPDIGEST)
    )
    checks["arp_roundtrip"] = (
        parse_arp(advertised) == DEFAULT_REQUEST
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_REQUEST_FIELD
        and is_token("REQUEST") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_REQUEST_FIELD
        and parsed_header["policy"] == DEFAULT_REQUEST
        and parsed_header["header"] == REQUEST_HEADER
        and parsed_header["request"] is True
        and parsed_header["reply"] is False
        and preloaded == REPLY_POLICY
        and ascii_serialize_arp_directive() == RFC_REQUEST_DIRECTIVE
        and arp_directive_pair() == ("request", "message")
        and RFC_REQUEST_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_arp(REPLY_POLICY) == RFC_ARP_REPLY
        and DEFAULT_ARPDIGEST == request_arpdigest(DEFAULT_ARPID, SENTINEL)
        and "arpdigest=" in canonical_reply(SENTINEL, DEFAULT_ARPID, DEFAULT_ARPDIGEST)
        and canonical_request(SENTINEL, DEFAULT_ARPID).startswith("REQUEST")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "REQUEST"
        and asked["arp_kind"] == "request"
        and asked["arpid"] == DEFAULT_ARPID
        and preload_req["arp_kind"] == "reply"
        and preload_req["arpdigest"] == DEFAULT_ARPDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["arp_kind"] == "request"
        and preload_reply["arp_kind"] == "reply"
        and got["policy"] == DEFAULT_REQUEST
        and preload_reply["policy"] == REPLY_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["arpdigest"] == DEFAULT_ARPDIGEST
        and preload_reply["arpdigest"] == DEFAULT_ARPDIGEST
        and arp_matches(serialize_arp(got["policy"]), advertised)
    )

    checks["catalog_names_arp"] = (
        len(catalog) > 116
        and catalog[116]["id"] == ARP_ACTUATION_ID
        and catalog[115]["id"] == IP_ACTUATION_ID
        and catalog[116]["source"] == "genesis_bind_arp"
    )
    checks["catalog_names_rarp"] = (
        len(catalog) > 117
        and catalog[117]["id"] == RARP_ACTUATION_ID
        and catalog[117]["source"] == "genesis_bind_rarp"
    )
    family = capability_family(ARP_ACTUATION_GOAL)
    checks["family_is_arp"] = "arp" in family.split("/")
    checks["family_is_arp_surface"] = "arpid" in family
    checks["family_is_arpid"] = "arpid" in family
    checks["family_is_rfc826"] = "rfc826" in family
    checks["family_is_arpdigest"] = "arpdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_rarp"] = (
        "rarp" not in family.split("/")
        and "rfc903" not in family
        and "rarpid" not in family
        and "rarpdigest" not in family
    )
    checks["family_is_not_ip"] = (
        "ip" not in family.split("/")
        and "rfc791" not in family
        and "ipid" not in family
        and "ipdigest" not in family
    )
    checks["family_is_not_tcp"] = (
        "tcp" not in family.split("/")
        and "rfc793" not in family
        and "tcpid" not in family
        and "tcpdigest" not in family
    )
    checks["family_is_not_icmp"] = (
        "icmp" not in family.split("/")
        and "rfc792" not in family
        and "icmpid" not in family
        and "icmpdigest" not in family
    )
    checks["family_is_not_udp"] = (
        "udp" not in family.split("/")
        and "rfc768" not in family
        and "udpid" not in family
        and "udpdigest" not in family
    )
    checks["family_is_not_telnet"] = (
        "telnet" not in family.split("/")
        and "rfc854" not in family
        and "telnetid" not in family
        and "telnetdigest" not in family
    )
    checks["family_is_not_finger"] = (
        "finger" not in family.split("/")
        and "rfc1288" not in family
        and "fingerid" not in family
        and "fingerdigest" not in family
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
        "rfc9221" not in family
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
    checks["family_is_not_ntp"] = (
        "ntp" not in family.split("/")
        and "rfc5905" not in family
        and "keyid" not in family
    )
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
    packed = encode_request(identity=SENTINEL, arpid=DEFAULT_ARPID, arpdigest=DEFAULT_ARPDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_request"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_arpid"] is True
        and parsed["arpid"] == DEFAULT_ARPID
        and parsed["arpdigest"] == DEFAULT_ARPDIGEST
        and parsed["is_reply"] is False
        and parsed["is_reply"] is False
        and parsed["type"] == FRAME_REQUEST
        and parsed["first_byte"] == ARP_FIRST
    )
    shook = encode_reply(
        identity=SENTINEL,
        arpid=DEFAULT_ARPID,
        arpdigest=DEFAULT_ARPDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_reply"] is True
        and answer_parsed["is_reply"] is True
        and answer_parsed["is_request"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["arpid"] == DEFAULT_ARPID
        and answer_parsed["arpdigest"] == DEFAULT_ARPDIGEST
        and answer_parsed["has_arpdigest"] is True
        and answer_parsed["type"] == FRAME_REPLY
        and answer_parsed["first_byte"] == ARP_FIRST
    )
    bare = encode_request(identity=SENTINEL, arpid=DEFAULT_ARPID, include_arpid=False)
    checks["missing_arpid_is_unauthed"] = parse_message(bare)["has_arpid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(ARP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_arp = ToolDescriptor(name="remote_arp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_arp)
    checks["naive_mcp_arp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = arp_tool_descriptor()
    default_arp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ARP_TOOL_PROVIDER),
    )
    checks["default_arp_provider_is_unsupported"] = (
        default_arp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{ARP_TOOL_PROVIDER}" in default_arp.reasons
    )
    checks["opted_in_arp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_arp],
        required_tool_names=("local_memory", "arp"),
    )
    checks["naive_preflight_missing_arp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["arp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "arp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ARP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "arp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="arp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_arp_workflow(with_arpid=False, output_dir=root / "missing")
        skip_bind = run_arp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_request = run_arp_workflow(do_request=False, output_dir=root / "skip-request")
        skip_reply = run_arp_workflow(do_reply=False, output_dir=root / "skip-reply")
        skip_arpdigest = run_arp_workflow(do_arpdigest=False, output_dir=root / "skip-arpdigest")
        skip_replay = run_arp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_arpid = run_arp_workflow(use_arpid=False, output_dir=root / "skarp-arpid")
        live = run_arp_workflow(output_dir=root / "live")
        verify = verify_arp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_arp_trace(clone)
        checks["naive_without_arpid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_arpid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_request_stays_empty"] = (
            skip_request["ok"] is False
            and skip_request["error"] == "request_required"
            and skip_request["final_status"] == 409
            and skip_request["payload_exists"] is False
        )
        checks["skip_reply_stays_empty"] = (
            skip_reply["ok"] is False
            and skip_reply["error"] == "reply_required"
            and skip_reply["final_status"] == 409
            and skip_reply["payload_exists"] is False
        )
        checks["skip_arpdigest_stays_empty"] = (
            skip_arpdigest["ok"] is False
            and skip_arpdigest["error"] == "arpdigest_required"
            and skip_arpdigest["final_status"] == 409
            and skip_arpdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_arpid_stays_empty"] = (
            skip_arpid["ok"] is False
            and skip_arpid["error"] == "arpid_required"
            and skip_arpid["final_status"] == 409
            and skip_arpid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_arpdigest"] = (
            int(live.get("arpid") or 0) == DEFAULT_ARPID
            and int(live.get("arpdigest") or 0) == DEFAULT_ARPDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_arpid_encode_reply_arpdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_request["ok"] is False
            and skip_reply["ok"] is False
            and skip_arpdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_arpid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="arp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != ARP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_arp"] = (
        live_goal == ARP_ACTUATION_GOAL
        and ARP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_arp"
    )

    with tempfile.TemporaryDirectory(prefix="arp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(ARP_LEFTOVER, root)
        register_catalog_proved(root, ARP_ACTUATION_ID)
        reason = leftover_satisfied_by(ARP_LEFTOVER, root)
        after = leftover_is_open(ARP_LEFTOVER, root)
    checks["arp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_arp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{ARP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_arp_actuation_capability()
    return {
        "ok": ok,
        "action": "arp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": ARP_ACTUATION_GOAL,
        "done_when": ARP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
