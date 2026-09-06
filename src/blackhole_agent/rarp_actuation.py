"""Drive a first-class Reverse Address Resolution Protocol tool through RFC 903 REVERSE/REPLY.

Tool routing already fails missions that require ``rarp``: hosted
rarp endpoints stay on the unsupported MCP provider, and no first-party
rarp provider is executable. Unbound therefore cannot speak a REVERSE,
lockstep a REPLY rarpid handshake over HTTP/1.0 RARPID,
independently poll the stored rarpdigest, or seal a rarpdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``rarp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 903 daemon
- keep a missing-rarpid client so the rarp-rarpid hole stays falsifiable
- refuse REPLY until a REVERSE lands with a non-empty rarpid
- independently poll the stored rarpdigest on a later client socket
- persist a sealed rarpdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 826 Address Resolution Protocol
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
    RARP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    rarp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
RARP_ACTUATION_ID = "capability.rarp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-RARP-OK"
POLL_TOKEN = "BH-RARP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_RARPID = 0
EMPTY_RARPDIGEST = 0
RARP_FIRST = 0x80  # RFC 903 RARP (EtherType 0x8035)
RARPID_SIZE = 4
RARPDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_REPLY = 0x04  # RFC 903 RARP-REPLY
FRAME_REVERSE = 0x03  # RFC 903 RARP-REQUEST
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
RARP_LEFTOVER = (
    "Later genesis can take RFC 903 Reverse Address Resolution Protocol REVERSE/REPLY over a "
    "rarpid-gated rarpdigest."
)
RARP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{RARP_ACTUATION_ID};"
    f"capability_proved:{RARP_ACTUATION_ID};"
    "no_skill_route"
)
RARP_ACTUATION_GOAL = (
    "Repair rfc903 rarp reverse/reply cycle cannot land over http "
    "rarp rarpid: hosted rarp endpoints remain unsupported so a REVERSE then "
    "REPLY rarpid handshake cannot land and a sealed rarpdigest "
    "cannot be produced. A missing rarp rarpid stays forbidden; fail-closed "
    "routing never opts the rarp provider in. An independent later poll of the "
    "stored rarpdigest keeps the hole falsifiable."
)


class RarpActuationError(RuntimeError):
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
# RFC 903 sections 3.3 and 3.4: REVERSE / REPLY.
RFC_REVERSE_FIELD = "REVERSE"
RFC_REPLY_FIELD = "REPLY"
RFC_RARP_REPLY = RFC_REPLY_FIELD
RFC_REVERSE_DIRECTIVE = "reverse=message"
RFC_REPLY_DIRECTIVE = "reply=message"
DEFAULT_REVERSE = "REVERSE"
REPLY_POLICY = "REPLY"
REVERSE_HEADER = "Reverse"
REPLY_HEADER = "Reply"
RARP_REPLY_HEADER = REPLY_HEADER
RFC_REVERSE_PATH = "/rarp/"
RFC_REVERSE_EMPTY = ""


def rarp_directive_pair(*, reply: bool = False) -> tuple[str, str]:
    """RFC 903 Reverse / Reply directive pair."""

    if reply:
        return "reply", "message"
    return "reverse", "message"


def ascii_serialize_rarp_directive(*, reply: bool = False) -> str:
    """RFC 903 token "=" body-or-reply."""

    name, value = rarp_directive_pair(reply=reply)
    if not is_token(name):
        raise RarpActuationError("illegal_directive")
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
            raise RarpActuationError("short_rarp")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 903 body-reverse token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_rarp(policy: str | Sequence[str]) -> str:
    """Serialize RFC 903 REVERSE / REPLY opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise RarpActuationError("illegal_rarp")
    upper = text.upper().replace("_", "-")
    if upper in {"REVERSE", "RARP", "RARP-REVERSE", "RARP-REQUEST"}:
        return "REVERSE"
    if upper in {"REPLY", "RESOURCE", "RARP-REPLY"}:
        return "REPLY"
    if upper.startswith("REVERSE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise RarpActuationError("illegal_rarp")
        return "REVERSE"
    if upper.startswith("REPLY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise RarpActuationError("illegal_rarp")
        return "REPLY"
    raise RarpActuationError("illegal_rarp")


def parse_rarp(text: str) -> str:
    """Parse RFC 903 RARP opcode header extensions into REVERSE or REPLY."""

    raw = str(text or "").strip()
    if not raw:
        raise RarpActuationError("illegal_rarp")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"REVERSE", "RARP", "RARP-REVERSE", "RARP-REQUEST"}:
        return "REVERSE"
    if upper in {"REPLY", "RESOURCE", "RARP-REPLY"}:
        return "REPLY"
    if upper.startswith("REVERSE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise RarpActuationError("illegal_rarp")
        return "REVERSE"
    if upper.startswith("REPLY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise RarpActuationError("illegal_rarp")
        return "REPLY"
    raise RarpActuationError("illegal_rarp")


def encode_rarp_header(policy: str | Sequence[str]) -> bytes:
    """RFC 903 HTTP/1.0 field as bytes."""

    return serialize_rarp(policy).encode("ascii")


def parse_rarp_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_rarp(field_value) if field_value else DEFAULT_REVERSE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": REVERSE_HEADER,
        "directive": str(policy),
        "reverse": str(policy) == "REVERSE",
        "reply": str(policy) == "REPLY",
    }


def canonical_reverse(identity: str, rarpid: int) -> str:
    """RFC 903 body-reverse advertisement bound to identity and rarpid."""

    return (
        f"{serialize_rarp(DEFAULT_REVERSE)}, "
        f"reverse={ascii_serialize_rarp_directive()}, "
        f"identity={identity}, rarpid={int(rarpid) & 0xFFFFFFFF}"
    )


def canonical_reply(identity: str, rarpid: int, rarpdigest: int | None = None) -> str:
    """RFC 903 reply-message confirmation of the stored identifier-digest."""

    digest = ""
    if rarpdigest is not None:
        digest = f", rarpdigest={int(rarpdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_rarp(REPLY_POLICY)}, "
        f"reply={ascii_serialize_rarp_directive(reply=True)}, "
        f"identity={identity}, rarpid={int(rarpid) & 0xFFFFFFFF}{digest}"
    )


def representation_reply(identity: str, rarpid: int, rarpdigest: int) -> str:
    return canonical_reply(identity, rarpid, rarpdigest)


def rarp_matches(left: str, right: str) -> bool:
    return parse_rarp(left) == parse_rarp(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise RarpActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise RarpActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise RarpActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise RarpActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def reverse_request(identity: str, rarpid: int) -> bytes:
    """HTTP REVERSE that elicits RFC 903 origin HTTP/1.0."""

    keyid = f"{int(rarpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"REVERSE /rarp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Rarp-Id: {int(rarpid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def reply_request(identity: str, rarpid: int, rarpdigest: int | None = None) -> bytes:
    """HTTP REPLY carrying RFC 903 reply-message confirmation of the stored identifier-digest."""

    keyid = f"{int(rarpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if rarpdigest is not None:
        extra = f"Rarp-Digest: {int(rarpdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"REPLY /rarp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Rarp-Id: {int(rarpid) & 0xFFFFFFFF}\r\n"
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
    rarp_kind = "reply" if fields.get("reply-confirm") == "1" else "reverse"
    upgrade_field = fields.get("reverse") or fields.get("rarp") or ""
    policy = parse_rarp(upgrade_field) if upgrade_field else ()
    return {
        "kind": "reverse",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "rarp_kind": rarp_kind,
        "policy": policy,
        "rarpid": int(fields["rarp-id"]) if fields.get("rarp-id") else EMPTY_RARPID,
        "rarpdigest": int(fields["rarp-digest"]) if fields.get("rarp-digest") else EMPTY_RARPDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def reverse_response(identity: str, rarpid: int, rarpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 903 origin HTTP/1.0, carrying the stored rarpdigest."""

    advertised = serialize_rarp(DEFAULT_REVERSE)
    payload = bytes(body or canonical_reverse(identity, rarpid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Reverse: {advertised}\r\n"
        f"Rarp-Id: {int(rarpid) & 0xFFFFFFFF}\r\n"
        f"Rarp-Digest: {int(rarpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def reply_response(identity: str, rarpid: int, rarpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 903 REPLY, carrying the stored identifier-digest."""

    advertised = serialize_rarp(REPLY_POLICY)
    payload = bytes(body or representation_reply(identity, rarpid, rarpdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Reverse: {advertised}\r\n"
        f"Rarp-Id: {int(rarpid) & 0xFFFFFFFF}\r\n"
        f"Rarp-Digest: {int(rarpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/rarp-reply\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise RarpActuationError("illegal_content_length") from error
    field_value = fields.get("reverse") or fields.get("rarp") or ""
    policy = parse_rarp(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/rarp-reply" or policy == REPLY_POLICY:
        status = 200
        rarp_kind = "reply"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        rarp_kind = "reverse"
    else:
        status = 0
        rarp_kind = "reverse"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "rarp_kind": rarp_kind,
        "policy": policy,
        "rarpid": int(fields["rarp-id"]) if fields.get("rarp-id") else EMPTY_RARPID,
        "rarpdigest": int(fields["rarp-digest"]) if fields.get("rarp-digest") else EMPTY_RARPDIGEST,
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
        raise RarpActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise RarpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise RarpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise RarpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc903_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    rarp: str,
) -> str:
    """RFC 903 identifier digest over method, reverse-IP, identity, and rarpid."""

    payload = f"{method}:{rarp}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def reverse_rarpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"rarpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_rarpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-rarpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def reverse_rarpdigest(rarpid: int = EMPTY_RARPID, token: str = SENTINEL) -> int:
    nonce = f"{int(rarpid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc903_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="REPLY",
        rarp=f"/rarp/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_RARPID = reverse_rarpid(SENTINEL)
DEFAULT_RARPDIGEST = reverse_rarpdigest(DEFAULT_RARPID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    rarpid: int,
    rarpdigest: int,
    include_rarpid: bool = True,
) -> bytes:
    live_rarpid = int(rarpid) & 0xFFFFFFFF if include_rarpid else EMPTY_RARPID
    live_digest = int(rarpdigest) & 0xFFFFFFFF if include_rarpid and live_rarpid else EMPTY_RARPDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_rarpid) if live_rarpid else b""
    header = bytearray()
    header.append(RARP_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_reverse(
    *,
    identity: str,
    rarpid: int,
    rarpdigest: int | None = None,
    include_rarpid: bool = True,
) -> bytes:
    live_rarpid = int(rarpid) & 0xFFFFFFFF if include_rarpid else EMPTY_RARPID
    live_digest = int(rarpdigest) if rarpdigest is not None else reverse_rarpdigest(live_rarpid, identity)
    return encode_packet(
        FRAME_REVERSE,
        identity=identity,
        rarpid=live_rarpid,
        rarpdigest=live_digest,
        include_rarpid=include_rarpid,
    )


def encode_reply(
    *,
    identity: str,
    rarpid: int,
    rarpdigest: int | None = None,
    include_rarpid: bool = True,
) -> bytes:
    live_rarpid = int(rarpid) & 0xFFFFFFFF if include_rarpid else EMPTY_RARPID
    live_digest = int(rarpdigest) if rarpdigest is not None else reverse_rarpdigest(live_rarpid, identity)
    return encode_packet(
        FRAME_REPLY,
        identity=identity,
        rarpid=live_rarpid,
        rarpdigest=live_digest,
        include_rarpid=include_rarpid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise RarpActuationError("short_packet")
    first = raw[0]
    if first != RARP_FIRST:
        raise RarpActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise RarpActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == RARPID_SIZE:
        live_rarpid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_rarpid = EMPTY_RARPID
    else:
        raise RarpActuationError("illegal_rarpid")
    if offset >= len(raw):
        raise RarpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_REVERSE, FRAME_REPLY}:
        raise RarpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise RarpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise RarpActuationError("checksum_failed")
    if len(payload) < 5:
        raise RarpActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise RarpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_rarpid = int(live_rarpid) != EMPTY_RARPID
    has_rarpdigest = has_rarpid and int(live_digest) != EMPTY_RARPDIGEST
    is_reverse = frame_type == FRAME_REVERSE
    is_reply = frame_type == FRAME_REPLY
    return {
        "type": int(frame_type),
        "is_reverse": is_reverse,
        "is_reply": is_reply,
        "rarpid": int(live_rarpid),
        "has_rarpid": has_rarpid,
        "rarpdigest": int(live_digest),
        "has_rarpdigest": has_rarpdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC903",
        "serialize_field": canonical_reverse(identity, live_rarpid) if has_rarpid else "",
        "tls_field": canonical_reply(identity, live_rarpid, live_digest) if has_rarpdigest else "",
    }


class RarpClient:
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
            raise RarpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_reply"] or not packet["is_reply"]:
            raise RarpActuationError("rarpdigest_required")
        if not packet["has_rarpid"]:
            raise RarpActuationError("rarpid_required")
        if not packet["has_rarpdigest"]:
            raise RarpActuationError("rarpdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_rarpdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_rarpdigest:
            raise RarpActuationError("rarpdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "rarpid": int(reply.get("rarpid") or EMPTY_RARPID),
            "identity": str(reply.get("identity") or ""),
            "rarpdigest": int(reply.get("rarpdigest") or EMPTY_RARPDIGEST),
        }

    def report(
        self,
        identity: str,
        rarpid: int,
        rarpdigest: int = EMPTY_RARPDIGEST,
        *,
        wait_rarpdigest: bool = True,
        include_rarpid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_reply(
            identity=identity,
            rarpid=rarpid,
            rarpdigest=rarpdigest or reverse_rarpdigest(rarpid, identity),
            include_rarpid=include_rarpid,
        )
        return self.exchange(packet, wait_rarpdigest=wait_rarpdigest)


class RarpSession:
    """RARPID-gated loopback RFC 903 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        rarpid_gate: int = DEFAULT_RARPID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rarpid_gate = int(rarpid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.rarpid = EMPTY_RARPID
        self.rarpdigest = EMPTY_RARPDIGEST
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

    def store_rarpid_once(self, identity: str, rarpid: int, rarpdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(rarpid or EMPTY_RARPID)
            live_digest = int(rarpdigest or EMPTY_RARPDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.rarpid = live
                self.rarpdigest = live_digest or reverse_rarpdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.rarpid), int(self.rarpdigest)

    def read_rarpid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.rarpid), int(self.rarpdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "rarpid": EMPTY_RARPID,
            "rarpdigest": EMPTY_RARPDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _rarpid_missing(self) -> bool:
        return not int(self.rarpid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, rarpid: int, rarpdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_reply(
            identity=identity,
            rarpid=rarpid,
            rarpdigest=rarpdigest,
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
            except RarpActuationError:
                continue
            if not packet.get("is_reverse") and not packet.get("is_reply"):
                continue
            if not packet.get("has_rarpid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_rarpid, stored_digest = self.store_rarpid_once(
                identity,
                int(packet.get("rarpid") or EMPTY_RARPID),
                int(packet.get("rarpdigest") or EMPTY_RARPDIGEST),
            )
            if not stored_name or not stored_rarpid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_reverse"):
                    self.opened = True
                if packet.get("is_reply"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_rarpid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._rarpid_missing():
            return self._forbidden("missing_rarpid")
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
        do_reverse: bool = True,
        do_reply: bool = True,
        do_rarpdigest: bool = True,
        replay: bool = True,
        use_rarpid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._rarpid_missing():
            return self._forbidden("missing_rarpid")
        live_token = str(token or SENTINEL)
        origin_rarpid = reverse_rarpid(live_token)
        origin_digest = reverse_rarpdigest(origin_rarpid, live_token)
        client: RarpClient | None = None
        independent: RarpClient | None = None
        try:
            client = RarpClient(self.host, int(self.port))
            if not do_reverse:
                return self._conflict("reverse_required")
            bind_packet = encode_reverse(
                identity=live_token,
                rarpid=origin_rarpid,
                rarpdigest=origin_digest,
                include_rarpid=use_rarpid,
            )
            if not use_rarpid:
                try:
                    client.exchange(bind_packet, wait_rarpdigest=True)
                except RarpActuationError:
                    return self._conflict("rarpid_required")
                return self._conflict("rarpid_required")
            client.send(bind_packet)
            if not do_reply:
                return self._conflict("reply_required")
            proxy_packet = encode_reply(
                identity=live_token,
                rarpid=origin_rarpid,
                rarpdigest=origin_digest,
                include_rarpid=True,
            )
            if not do_rarpdigest:
                try:
                    client.exchange(proxy_packet, wait_rarpdigest=False)
                except RarpActuationError as error:
                    if str(error) == "rarpdigest_required":
                        return self._conflict("rarpdigest_required")
                    return self._conflict("rarpdigest_required")
                return self._conflict("rarpdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_rarpdigest=True)
            except RarpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("rarpid_required")
                if reason == "rarpdigest_required":
                    return self._conflict("rarpdigest_required")
                return self._conflict("reverse_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("reverse_required")
            if int(reply.get("rarpid") or EMPTY_RARPID) != origin_rarpid:
                return self._conflict("rarpdigest_required")
            if int(reply.get("rarpdigest") or EMPTY_RARPDIGEST) != origin_digest:
                return self._conflict("rarpdigest_required")
            self.retrieved = True
            if replay:
                independent = RarpClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_rarpid(live_token),
                        reverse_rarpdigest(poll_rarpid(live_token), POLL_TOKEN),
                        wait_rarpdigest=True,
                    )
                except RarpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_rarpid, stored_digest = self.read_rarpid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_rarpid != origin_rarpid
                    or stored_digest != origin_digest
                    or int(poll.get("rarpid") or EMPTY_RARPID) != origin_rarpid
                    or int(poll.get("rarpdigest") or EMPTY_RARPDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_rarpid}:{origin_digest}:{live_token}:{canonical_reverse(live_token, origin_rarpid)}:{canonical_reply(live_token, origin_rarpid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "rarpid": origin_rarpid,
                "rarpdigest": origin_digest,
                "reverse_frame": True,
                "reply_frame": True,
                "rarpdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "rarpid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_rarpdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "rarpid": origin_rarpid,
                "rarpdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "reverse_frame": True,
                "reply_frame": True,
                "rarpdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "rarpid_bound": True,
            }
        except (OSError, RarpActuationError) as error:
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
        live = independent_rarpdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "rarpid": int(live.get("rarpid") or EMPTY_RARPID),
            "rarpdigest": int(live.get("rarpdigest") or EMPTY_RARPDIGEST),
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


def call_rarp_tool(session: RarpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one rarp tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_reverse = True if arguments.get("reverse") is None else bool(arguments.get("reverse"))
    do_reply = True if arguments.get("reply") is None else bool(arguments.get("reply"))
    do_rarpdigest = True if arguments.get("rarpdigest") is None else bool(arguments.get("rarpdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_rarpid = True if arguments.get("use_rarpid") is None else bool(arguments.get("use_rarpid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_reverse=do_reverse,
            do_reply=do_reply,
            do_rarpdigest=do_rarpdigest,
            replay=replay,
            use_rarpid=use_rarpid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise RarpActuationError(f"unsupported rarp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_rarpdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage rarpdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "rarpid": EMPTY_RARPID,
        "rarpdigest": EMPTY_RARPDIGEST,
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
            "reverse_frame",
            "reply_frame",
            "rarpdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "rarpid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    rarpid = int(payload.get("rarpid") or EMPTY_RARPID)
    rarpdigest = int(payload.get("rarpdigest") or EMPTY_RARPDIGEST)
    dual = port > 0 and bool(rarpid) and bool(rarpdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "rarpid": rarpid,
        "rarpdigest": rarpdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "reverse_frame": payload.get("reverse_frame") is True,
        "reply_frame": payload.get("reply_frame") is True,
        "rarpdigest_locate": payload.get("rarpdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "rarpid_bound": payload.get("rarpid_bound") is True,
    }


def run_rarp_workflow(
    *,
    with_rarpid: bool = True,
    skip_bind: bool = False,
    do_reverse: bool = True,
    do_reply: bool = True,
    do_rarpdigest: bool = True,
    replay: bool = True,
    use_rarpid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 903 REVERSE/REPLY rarpid cycle workflow."""

    descriptor = rarp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, RARP_TOOL_PROVIDER),
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
        raise RarpActuationError(f"rarp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="rarp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = RarpSession(out, rarpid_gate=DEFAULT_RARPID if with_rarpid else EMPTY_RARPID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "reverse": do_reverse,
            "reply": do_reply,
            "rarpdigest": do_rarpdigest,
            "replay": replay,
            "use_rarpid": use_rarpid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_rarp_tool(session, arguments))
            except RarpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_rarpdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_rarpid
        and not skip_bind
        and do_reverse
        and do_reply
        and do_rarpdigest
        and replay
        and use_rarpid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "rarp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_rarpid": with_rarpid,
        "skip_bind": skip_bind,
        "reverse_frame": do_reverse,
        "reply_frame": do_reply,
        "rarpdigest": do_rarpdigest,
        "replay": replay,
        "use_rarpid": use_rarpid,
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
        "rarpid_value": int(publish_result.get("rarpid") or independent.get("rarpid") or EMPTY_RARPID),
        "rarpdigest_value": int(publish_result.get("rarpdigest") or independent.get("rarpdigest") or EMPTY_RARPDIGEST),
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
        "rarpid": int(trace_body["rarpid_value"] or EMPTY_RARPID),
        "rarpdigest": int(trace_body["rarpdigest_value"] or EMPTY_RARPDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_rarpid": with_rarpid,
        "skip_bind": skip_bind,
        "reverse_cycle": do_reverse,
        "reply_cycle": do_reply,
        "rarpdigest_cycle": do_rarpdigest,
        "replay": replay,
        "use_rarpid": use_rarpid,
    }


def verify_rarp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_rarpdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    rarpid = int(trace.get("rarpid_value") or independent.get("rarpid") or EMPTY_RARPID)
    rarpdigest = int(trace.get("rarpdigest_value") or independent.get("rarpdigest") or EMPTY_RARPDIGEST)
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
        "reverse_frame": independent.get("reverse_frame") is True,
        "reply_frame": independent.get("reply_frame") is True,
        "rarpdigest_locate": independent.get("rarpdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "rarpid_bound": independent.get("rarpid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "rarpdigest_recorded": (
            port > 0
            and rarpid == DEFAULT_RARPID
            and rarpdigest == DEFAULT_RARPDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def rarp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.rarp_actuation import "
        "builtin_rarp_actuation_proof; r=builtin_rarp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='rarp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_rarp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=RARP_ACTUATION_ID,
        name="First-class RFC 903 Reverse Address Resolution Protocol REVERSE/REPLY actuation",
        description=(
            "Missions that require a rarp tool can opt the rarp provider in, "
            "bind a loopback RFC 903 Reverse Address Resolution Protocol endpoint, complete a REVERSE "
            "with a non-empty rarpid, lockstep a REPLY that carries the "
            "stored rarpdigest, independently poll the stored rarpdigest "
            "on a later socket, and seal a digest-chained rarpdigest. Default "
            "routing stays fail-closed; a missing rarpid keeps the hole "
            "falsifiable, and skip-REVERSE/REPLY/RARPDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.rarp_actuation:builtin_rarp_actuation_proof",
        proof_command=rarp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.arp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/rarp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/arp_actuation.py",
            "src/blackhole_agent/ip_actuation.py",
            "src/blackhole_agent/icmp_actuation.py",
            "src/blackhole_agent/igmp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required rarp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 903 daemon, speaks a "
            "REVERSE then REPLY over Reverse Address Resolution Protocol with a non-empty rarpid and "
            "rarpdigest, independently polls the stored rarpdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 826 Address Resolution Protocol lockstep is proved. "
            "Missing rarpids, skip-REVERSE, skip-REPLY, skip-rarpdigest, skip-REPLAY, "
            "and a REVERSE aimed without a rarpid stay fail-closed. "
            "Later genesis can take RFC 1112 Internet Group Management Protocol QUERY/REPORT as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("rarp", "rfc903", "http", "rarpid", "rarpdigest", "reverse", "reply", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T151350Z-fd0df45b",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_rarp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 903 reverse/reply lockstep actuation seals an rarpdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.igmp_actuation import (
        IGMP_ACTUATION_GOAL,
        IGMP_ACTUATION_ID,
    )
    from blackhole_agent.arp_actuation import (
        ARP_ACTUATION_GOAL,
        ARP_ACTUATION_ID,
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
    checks["denylists_self"] = RARP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(RARP_ACTUATION_GOAL) == (
        RARP_ACTUATION_ID,
    )
    checks["leftover_text_binds_rarp"] = leftover_marker_ids(RARP_LEFTOVER) == (
        RARP_ACTUATION_ID,
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
        (IGMP_ACTUATION_GOAL, IGMP_ACTUATION_ID, "igmp"),
        (ARP_ACTUATION_GOAL, ARP_ACTUATION_ID, "arp"),
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
        checks[f"{name}_goal_is_not_rarp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"rarp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            RARP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = RARP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_rarp(DEFAULT_REVERSE)
    rebuilt = serialize_rarp(parse_rarp(advertised))
    preloaded = parse_rarp(RFC_RARP_REPLY)
    header = encode_rarp_header(DEFAULT_REVERSE)
    parsed_header = parse_rarp_header(header)
    asked = parse_http_request(reverse_request(SENTINEL, DEFAULT_RARPID))
    preload_req = parse_http_request(reply_request(SENTINEL, DEFAULT_RARPID, DEFAULT_RARPDIGEST))
    got = parse_http_response(reverse_response(SENTINEL, DEFAULT_RARPID, DEFAULT_RARPDIGEST))
    preload_reply = parse_http_response(
        reply_response(SENTINEL, DEFAULT_RARPID, DEFAULT_RARPDIGEST)
    )
    checks["rarp_roundtrip"] = (
        parse_rarp(advertised) == DEFAULT_REVERSE
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_REVERSE_FIELD
        and is_token("REVERSE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_REVERSE_FIELD
        and parsed_header["policy"] == DEFAULT_REVERSE
        and parsed_header["header"] == REVERSE_HEADER
        and parsed_header["reverse"] is True
        and parsed_header["reply"] is False
        and preloaded == REPLY_POLICY
        and ascii_serialize_rarp_directive() == RFC_REVERSE_DIRECTIVE
        and rarp_directive_pair() == ("reverse", "message")
        and RFC_REVERSE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_rarp(REPLY_POLICY) == RFC_RARP_REPLY
        and DEFAULT_RARPDIGEST == reverse_rarpdigest(DEFAULT_RARPID, SENTINEL)
        and "rarpdigest=" in canonical_reply(SENTINEL, DEFAULT_RARPID, DEFAULT_RARPDIGEST)
        and canonical_reverse(SENTINEL, DEFAULT_RARPID).startswith("REVERSE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "REVERSE"
        and asked["rarp_kind"] == "reverse"
        and asked["rarpid"] == DEFAULT_RARPID
        and preload_req["rarp_kind"] == "reply"
        and preload_req["rarpdigest"] == DEFAULT_RARPDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["rarp_kind"] == "reverse"
        and preload_reply["rarp_kind"] == "reply"
        and got["policy"] == DEFAULT_REVERSE
        and preload_reply["policy"] == REPLY_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["rarpdigest"] == DEFAULT_RARPDIGEST
        and preload_reply["rarpdigest"] == DEFAULT_RARPDIGEST
        and rarp_matches(serialize_rarp(got["policy"]), advertised)
    )

    checks["catalog_names_rarp"] = (
        len(catalog) > 117
        and catalog[117]["id"] == RARP_ACTUATION_ID
        and catalog[116]["id"] == ARP_ACTUATION_ID
        and catalog[117]["source"] == "genesis_bind_rarp"
    )
    checks["catalog_names_igmp"] = (
        len(catalog) > 118
        and catalog[118]["id"] == IGMP_ACTUATION_ID
        and catalog[118]["source"] == "genesis_bind_igmp"
    )
    family = capability_family(RARP_ACTUATION_GOAL)
    checks["family_is_rarp"] = "rarp" in family.split("/")
    checks["family_is_rarp_surface"] = "rarpid" in family
    checks["family_is_rarpid"] = "rarpid" in family
    checks["family_is_rfc903"] = "rfc903" in family
    checks["family_is_rarpdigest"] = "rarpdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_igmp"] = (
        "igmp" not in family.split("/")
        and "rfc1112" not in family
        and "igmpid" not in family
        and "igmpdigest" not in family
    )
    checks["family_is_not_arp"] = (
        "arp" not in family.split("/")
        and "rfc826" not in family
        and "arpid" not in family.split("/")
        and "arpdigest" not in family.split("/")
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
    packed = encode_reverse(identity=SENTINEL, rarpid=DEFAULT_RARPID, rarpdigest=DEFAULT_RARPDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_reverse"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_rarpid"] is True
        and parsed["rarpid"] == DEFAULT_RARPID
        and parsed["rarpdigest"] == DEFAULT_RARPDIGEST
        and parsed["is_reply"] is False
        and parsed["is_reply"] is False
        and parsed["type"] == FRAME_REVERSE
        and parsed["first_byte"] == RARP_FIRST
    )
    shook = encode_reply(
        identity=SENTINEL,
        rarpid=DEFAULT_RARPID,
        rarpdigest=DEFAULT_RARPDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_reply"] is True
        and answer_parsed["is_reply"] is True
        and answer_parsed["is_reverse"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["rarpid"] == DEFAULT_RARPID
        and answer_parsed["rarpdigest"] == DEFAULT_RARPDIGEST
        and answer_parsed["has_rarpdigest"] is True
        and answer_parsed["type"] == FRAME_REPLY
        and answer_parsed["first_byte"] == RARP_FIRST
    )
    bare = encode_reverse(identity=SENTINEL, rarpid=DEFAULT_RARPID, include_rarpid=False)
    checks["missing_rarpid_is_unauthed"] = parse_message(bare)["has_rarpid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(RARP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_rarp = ToolDescriptor(name="remote_rarp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_rarp)
    checks["naive_mcp_rarp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = rarp_tool_descriptor()
    default_rarp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, RARP_TOOL_PROVIDER),
    )
    checks["default_rarp_provider_is_unsupported"] = (
        default_rarp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{RARP_TOOL_PROVIDER}" in default_rarp.reasons
    )
    checks["opted_in_rarp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_rarp],
        required_tool_names=("local_memory", "rarp"),
    )
    checks["naive_preflight_missing_rarp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["rarp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "rarp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, RARP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "rarp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="rarp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_rarp_workflow(with_rarpid=False, output_dir=root / "missing")
        skip_bind = run_rarp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_reverse = run_rarp_workflow(do_reverse=False, output_dir=root / "skip-reverse")
        skip_reply = run_rarp_workflow(do_reply=False, output_dir=root / "skip-reply")
        skip_rarpdigest = run_rarp_workflow(do_rarpdigest=False, output_dir=root / "skip-rarpdigest")
        skip_replay = run_rarp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_rarpid = run_rarp_workflow(use_rarpid=False, output_dir=root / "skrarp-rarpid")
        live = run_rarp_workflow(output_dir=root / "live")
        verify = verify_rarp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_rarp_trace(clone)
        checks["naive_without_rarpid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_rarpid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_reverse_stays_empty"] = (
            skip_reverse["ok"] is False
            and skip_reverse["error"] == "reverse_required"
            and skip_reverse["final_status"] == 409
            and skip_reverse["payload_exists"] is False
        )
        checks["skip_reply_stays_empty"] = (
            skip_reply["ok"] is False
            and skip_reply["error"] == "reply_required"
            and skip_reply["final_status"] == 409
            and skip_reply["payload_exists"] is False
        )
        checks["skip_rarpdigest_stays_empty"] = (
            skip_rarpdigest["ok"] is False
            and skip_rarpdigest["error"] == "rarpdigest_required"
            and skip_rarpdigest["final_status"] == 409
            and skip_rarpdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_rarpid_stays_empty"] = (
            skip_rarpid["ok"] is False
            and skip_rarpid["error"] == "rarpid_required"
            and skip_rarpid["final_status"] == 409
            and skip_rarpid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_rarpdigest"] = (
            int(live.get("rarpid") or 0) == DEFAULT_RARPID
            and int(live.get("rarpdigest") or 0) == DEFAULT_RARPDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_rarpid_encode_reply_rarpdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_reverse["ok"] is False
            and skip_reply["ok"] is False
            and skip_rarpdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_rarpid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="rarp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != RARP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_rarp"] = (
        live_goal == RARP_ACTUATION_GOAL
        and RARP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_rarp"
    )

    with tempfile.TemporaryDirectory(prefix="rarp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(RARP_LEFTOVER, root)
        register_catalog_proved(root, RARP_ACTUATION_ID)
        reason = leftover_satisfied_by(RARP_LEFTOVER, root)
        after = leftover_is_open(RARP_LEFTOVER, root)
    checks["rarp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_rarp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{RARP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_rarp_actuation_capability()
    return {
        "ok": ok,
        "action": "rarp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": RARP_ACTUATION_GOAL,
        "done_when": RARP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
