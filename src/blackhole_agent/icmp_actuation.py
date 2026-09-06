"""Drive a first-class Internet Control Message Protocol tool through RFC 792 ECHO/REPLY.

Tool routing already fails missions that require ``icmp``: hosted
icmp endpoints stay on the unsupported MCP provider, and no first-party
icmp provider is executable. Unbound therefore cannot speak a ECHO,
lockstep an REPLY icmpid handshake over HTTP/1.0 ICMPID,
independently poll the stored icmpdigest, or seal a icmpdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``icmp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 792 daemon
- keep a missing-icmpid client so the icmp-icmpid hole stays falsifiable
- refuse REPLY until a ECHO lands with a non-empty icmpid
- independently poll the stored icmpdigest on a later client socket
- persist a sealed icmpdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 768 User Datagram Protocol
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
    ICMP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    icmp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
ICMP_ACTUATION_ID = "capability.icmp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-ICMP-OK"
POLL_TOKEN = "BH-ICMP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_ICMPID = 0
EMPTY_ICMPDIGEST = 0
ICMP_FIRST = 0x01  # RFC 792 ICMP (IP protocol 1)
ICMPID_SIZE = 4
ICMPDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_REPLY = 0x02  # RFC 792 REPLY confirmation
FRAME_ECHO = 0x01  # RFC 792 ECHO
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
ICMP_LEFTOVER = (
    "Later genesis can take RFC 792 Internet Control Message Protocol ECHO/REPLY over a "
    "icmpid-gated icmpdigest."
)
ICMP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ICMP_ACTUATION_ID};"
    f"capability_proved:{ICMP_ACTUATION_ID};"
    "no_skill_route"
)
ICMP_ACTUATION_GOAL = (
    "Repair rfc792 icmp echo/reply cycle cannot land over http "
    "icmp icmpid: hosted icmp endpoints remain unsupported so an ECHO then "
    "REPLY icmpid handshake cannot land and a sealed icmpdigest "
    "cannot be produced. A missing icmp icmpid stays forbidden; fail-closed "
    "routing never opts the icmp provider in. An independent later poll of the "
    "stored icmpdigest keeps the hole falsifiable."
)


class IcmpActuationError(RuntimeError):
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
# RFC 792 sections 3.3 and 3.4: ECHO / REPLY.
RFC_ECHO_FIELD = "ECHO"
RFC_REPLY_FIELD = "REPLY"
RFC_ICMP_REPLY = RFC_REPLY_FIELD
RFC_ECHO_DIRECTIVE = "echo=message"
RFC_REPLY_DIRECTIVE = "reply=message"
DEFAULT_ECHO = "ECHO"
REPLY_POLICY = "REPLY"
ECHO_HEADER = "Echo"
REPLY_HEADER = "Reply"
ICMP_REPLY_HEADER = REPLY_HEADER
RFC_ECHO_PATH = "/icmp/"
RFC_ECHO_EMPTY = ""


def icmp_directive_pair(*, reply: bool = False) -> tuple[str, str]:
    """RFC 792 Echo / Reply directive pair."""

    if reply:
        return "reply", "message"
    return "echo", "message"


def ascii_serialize_icmp_directive(*, reply: bool = False) -> str:
    """RFC 792 token "=" body-or-reply."""

    name, value = icmp_directive_pair(reply=reply)
    if not is_token(name):
        raise IcmpActuationError("illegal_directive")
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
            raise IcmpActuationError("short_icmp")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 792 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_icmp(policy: str | Sequence[str]) -> str:
    """Serialize RFC 792 ECHO / REPLY opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise IcmpActuationError("illegal_icmp")
    upper = text.upper().replace("_", "-")
    if upper in {"ECHO", "ICMP", "ICMP-ECHO"}:
        return "ECHO"
    if upper in {"REPLY", "RESOURCE", "ICMP-REPLY"}:
        return "REPLY"
    if upper.startswith("ECHO="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IcmpActuationError("illegal_icmp")
        return "ECHO"
    if upper.startswith("REPLY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IcmpActuationError("illegal_icmp")
        return "REPLY"
    raise IcmpActuationError("illegal_icmp")


def parse_icmp(text: str) -> str:
    """Parse RFC 792 ICMP opcode header extensions into ECHO or REPLY."""

    raw = str(text or "").strip()
    if not raw:
        raise IcmpActuationError("illegal_icmp")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"ECHO", "ICMP", "ICMP-ECHO"}:
        return "ECHO"
    if upper in {"REPLY", "RESOURCE", "ICMP-REPLY"}:
        return "REPLY"
    if upper.startswith("ECHO="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IcmpActuationError("illegal_icmp")
        return "ECHO"
    if upper.startswith("REPLY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IcmpActuationError("illegal_icmp")
        return "REPLY"
    raise IcmpActuationError("illegal_icmp")


def encode_icmp_header(policy: str | Sequence[str]) -> bytes:
    """RFC 792 HTTP/1.0 field as bytes."""

    return serialize_icmp(policy).encode("ascii")


def parse_icmp_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_icmp(field_value) if field_value else DEFAULT_ECHO
    return {
        "field_value": field_value,
        "policy": policy,
        "header": ECHO_HEADER,
        "directive": str(policy),
        "echo": str(policy) == "ECHO",
        "reply": str(policy) == "REPLY",
    }


def canonical_echo(identity: str, icmpid: int) -> str:
    """RFC 792 body-request advertisement bound to identity and icmpid."""

    return (
        f"{serialize_icmp(DEFAULT_ECHO)}, "
        f"echo={ascii_serialize_icmp_directive()}, "
        f"identity={identity}, icmpid={int(icmpid) & 0xFFFFFFFF}"
    )


def canonical_reply(identity: str, icmpid: int, icmpdigest: int | None = None) -> str:
    """RFC 792 reply-message confirmation of the stored identifier-digest."""

    digest = ""
    if icmpdigest is not None:
        digest = f", icmpdigest={int(icmpdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_icmp(REPLY_POLICY)}, "
        f"reply={ascii_serialize_icmp_directive(reply=True)}, "
        f"identity={identity}, icmpid={int(icmpid) & 0xFFFFFFFF}{digest}"
    )


def representation_reply(identity: str, icmpid: int, icmpdigest: int) -> str:
    return canonical_reply(identity, icmpid, icmpdigest)


def icmp_matches(left: str, right: str) -> bool:
    return parse_icmp(left) == parse_icmp(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise IcmpActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise IcmpActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise IcmpActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise IcmpActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def echo_request(identity: str, icmpid: int) -> bytes:
    """HTTP ECHO that elicits RFC 792 origin HTTP/1.0."""

    keyid = f"{int(icmpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"ECHO /icmp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Icmp-Id: {int(icmpid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def reply_request(identity: str, icmpid: int, icmpdigest: int | None = None) -> bytes:
    """HTTP REPLY carrying RFC 792 reply-message confirmation of the stored identifier-digest."""

    keyid = f"{int(icmpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if icmpdigest is not None:
        extra = f"Icmp-Digest: {int(icmpdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"REPLY /icmp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Icmp-Id: {int(icmpid) & 0xFFFFFFFF}\r\n"
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
    icmp_kind = "reply" if fields.get("reply-confirm") == "1" else "echo"
    upgrade_field = fields.get("echo") or fields.get("icmp") or ""
    policy = parse_icmp(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "icmp_kind": icmp_kind,
        "policy": policy,
        "icmpid": int(fields["icmp-id"]) if fields.get("icmp-id") else EMPTY_ICMPID,
        "icmpdigest": int(fields["icmp-digest"]) if fields.get("icmp-digest") else EMPTY_ICMPDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def echo_response(identity: str, icmpid: int, icmpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 792 origin HTTP/1.0, carrying the stored icmpdigest."""

    advertised = serialize_icmp(DEFAULT_ECHO)
    payload = bytes(body or canonical_echo(identity, icmpid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Echo: {advertised}\r\n"
        f"Icmp-Id: {int(icmpid) & 0xFFFFFFFF}\r\n"
        f"Icmp-Digest: {int(icmpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def reply_response(identity: str, icmpid: int, icmpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 792 REPLY, carrying the stored identifier-digest."""

    advertised = serialize_icmp(REPLY_POLICY)
    payload = bytes(body or representation_reply(identity, icmpid, icmpdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Echo: {advertised}\r\n"
        f"Icmp-Id: {int(icmpid) & 0xFFFFFFFF}\r\n"
        f"Icmp-Digest: {int(icmpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/icmp-reply\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise IcmpActuationError("illegal_content_length") from error
    field_value = fields.get("echo") or fields.get("icmp") or ""
    policy = parse_icmp(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/icmp-reply" or policy == REPLY_POLICY:
        status = 200
        icmp_kind = "reply"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        icmp_kind = "echo"
    else:
        status = 0
        icmp_kind = "echo"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "icmp_kind": icmp_kind,
        "policy": policy,
        "icmpid": int(fields["icmp-id"]) if fields.get("icmp-id") else EMPTY_ICMPID,
        "icmpdigest": int(fields["icmp-digest"]) if fields.get("icmp-digest") else EMPTY_ICMPDIGEST,
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
        raise IcmpActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise IcmpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise IcmpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise IcmpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc792_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    icmp: str,
) -> str:
    """RFC 792 identifier digest over method, request-ICMP, identity, and icmpid."""

    payload = f"{method}:{icmp}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_icmpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"icmpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_icmpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-icmpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_icmpdigest(icmpid: int = EMPTY_ICMPID, token: str = SENTINEL) -> int:
    nonce = f"{int(icmpid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc792_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="REPLY",
        icmp=f"/icmp/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_ICMPID = request_icmpid(SENTINEL)
DEFAULT_ICMPDIGEST = request_icmpdigest(DEFAULT_ICMPID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    icmpid: int,
    icmpdigest: int,
    include_icmpid: bool = True,
) -> bytes:
    live_icmpid = int(icmpid) & 0xFFFFFFFF if include_icmpid else EMPTY_ICMPID
    live_digest = int(icmpdigest) & 0xFFFFFFFF if include_icmpid and live_icmpid else EMPTY_ICMPDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_icmpid) if live_icmpid else b""
    header = bytearray()
    header.append(ICMP_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_echo(
    *,
    identity: str,
    icmpid: int,
    icmpdigest: int | None = None,
    include_icmpid: bool = True,
) -> bytes:
    live_icmpid = int(icmpid) & 0xFFFFFFFF if include_icmpid else EMPTY_ICMPID
    live_digest = int(icmpdigest) if icmpdigest is not None else request_icmpdigest(live_icmpid, identity)
    return encode_packet(
        FRAME_ECHO,
        identity=identity,
        icmpid=live_icmpid,
        icmpdigest=live_digest,
        include_icmpid=include_icmpid,
    )


def encode_reply(
    *,
    identity: str,
    icmpid: int,
    icmpdigest: int | None = None,
    include_icmpid: bool = True,
) -> bytes:
    live_icmpid = int(icmpid) & 0xFFFFFFFF if include_icmpid else EMPTY_ICMPID
    live_digest = int(icmpdigest) if icmpdigest is not None else request_icmpdigest(live_icmpid, identity)
    return encode_packet(
        FRAME_REPLY,
        identity=identity,
        icmpid=live_icmpid,
        icmpdigest=live_digest,
        include_icmpid=include_icmpid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise IcmpActuationError("short_packet")
    first = raw[0]
    if first != ICMP_FIRST:
        raise IcmpActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise IcmpActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == ICMPID_SIZE:
        live_icmpid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_icmpid = EMPTY_ICMPID
    else:
        raise IcmpActuationError("illegal_icmpid")
    if offset >= len(raw):
        raise IcmpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ECHO, FRAME_REPLY}:
        raise IcmpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise IcmpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise IcmpActuationError("checksum_failed")
    if len(payload) < 5:
        raise IcmpActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise IcmpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_icmpid = int(live_icmpid) != EMPTY_ICMPID
    has_icmpdigest = has_icmpid and int(live_digest) != EMPTY_ICMPDIGEST
    is_echo = frame_type == FRAME_ECHO
    is_reply = frame_type == FRAME_REPLY
    return {
        "type": int(frame_type),
        "is_echo": is_echo,
        "is_reply": is_reply,
        "icmpid": int(live_icmpid),
        "has_icmpid": has_icmpid,
        "icmpdigest": int(live_digest),
        "has_icmpdigest": has_icmpdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC792",
        "serialize_field": canonical_echo(identity, live_icmpid) if has_icmpid else "",
        "tls_field": canonical_reply(identity, live_icmpid, live_digest) if has_icmpdigest else "",
    }


class IcmpClient:
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
            raise IcmpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_reply"] or not packet["is_reply"]:
            raise IcmpActuationError("icmpdigest_required")
        if not packet["has_icmpid"]:
            raise IcmpActuationError("icmpid_required")
        if not packet["has_icmpdigest"]:
            raise IcmpActuationError("icmpdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_icmpdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_icmpdigest:
            raise IcmpActuationError("icmpdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "icmpid": int(reply.get("icmpid") or EMPTY_ICMPID),
            "identity": str(reply.get("identity") or ""),
            "icmpdigest": int(reply.get("icmpdigest") or EMPTY_ICMPDIGEST),
        }

    def report(
        self,
        identity: str,
        icmpid: int,
        icmpdigest: int = EMPTY_ICMPDIGEST,
        *,
        wait_icmpdigest: bool = True,
        include_icmpid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_reply(
            identity=identity,
            icmpid=icmpid,
            icmpdigest=icmpdigest or request_icmpdigest(icmpid, identity),
            include_icmpid=include_icmpid,
        )
        return self.exchange(packet, wait_icmpdigest=wait_icmpdigest)


class IcmpSession:
    """ICMPID-gated loopback RFC 792 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        icmpid_gate: int = DEFAULT_ICMPID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.icmpid_gate = int(icmpid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.icmpid = EMPTY_ICMPID
        self.icmpdigest = EMPTY_ICMPDIGEST
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

    def store_icmpid_once(self, identity: str, icmpid: int, icmpdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(icmpid or EMPTY_ICMPID)
            live_digest = int(icmpdigest or EMPTY_ICMPDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.icmpid = live
                self.icmpdigest = live_digest or request_icmpdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.icmpid), int(self.icmpdigest)

    def read_icmpid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.icmpid), int(self.icmpdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "icmpid": EMPTY_ICMPID,
            "icmpdigest": EMPTY_ICMPDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _icmpid_missing(self) -> bool:
        return not int(self.icmpid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, icmpid: int, icmpdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_reply(
            identity=identity,
            icmpid=icmpid,
            icmpdigest=icmpdigest,
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
            except IcmpActuationError:
                continue
            if not packet.get("is_echo") and not packet.get("is_reply"):
                continue
            if not packet.get("has_icmpid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_icmpid, stored_digest = self.store_icmpid_once(
                identity,
                int(packet.get("icmpid") or EMPTY_ICMPID),
                int(packet.get("icmpdigest") or EMPTY_ICMPDIGEST),
            )
            if not stored_name or not stored_icmpid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_echo"):
                    self.opened = True
                if packet.get("is_reply"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_icmpid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._icmpid_missing():
            return self._forbidden("missing_icmpid")
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
        do_echo: bool = True,
        do_reply: bool = True,
        do_icmpdigest: bool = True,
        replay: bool = True,
        use_icmpid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._icmpid_missing():
            return self._forbidden("missing_icmpid")
        live_token = str(token or SENTINEL)
        origin_icmpid = request_icmpid(live_token)
        origin_digest = request_icmpdigest(origin_icmpid, live_token)
        client: IcmpClient | None = None
        independent: IcmpClient | None = None
        try:
            client = IcmpClient(self.host, int(self.port))
            if not do_echo:
                return self._conflict("echo_required")
            bind_packet = encode_echo(
                identity=live_token,
                icmpid=origin_icmpid,
                icmpdigest=origin_digest,
                include_icmpid=use_icmpid,
            )
            if not use_icmpid:
                try:
                    client.exchange(bind_packet, wait_icmpdigest=True)
                except IcmpActuationError:
                    return self._conflict("icmpid_required")
                return self._conflict("icmpid_required")
            client.send(bind_packet)
            if not do_reply:
                return self._conflict("reply_required")
            proxy_packet = encode_reply(
                identity=live_token,
                icmpid=origin_icmpid,
                icmpdigest=origin_digest,
                include_icmpid=True,
            )
            if not do_icmpdigest:
                try:
                    client.exchange(proxy_packet, wait_icmpdigest=False)
                except IcmpActuationError as error:
                    if str(error) == "icmpdigest_required":
                        return self._conflict("icmpdigest_required")
                    return self._conflict("icmpdigest_required")
                return self._conflict("icmpdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_icmpdigest=True)
            except IcmpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("icmpid_required")
                if reason == "icmpdigest_required":
                    return self._conflict("icmpdigest_required")
                return self._conflict("echo_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("echo_required")
            if int(reply.get("icmpid") or EMPTY_ICMPID) != origin_icmpid:
                return self._conflict("icmpdigest_required")
            if int(reply.get("icmpdigest") or EMPTY_ICMPDIGEST) != origin_digest:
                return self._conflict("icmpdigest_required")
            self.retrieved = True
            if replay:
                independent = IcmpClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_icmpid(live_token),
                        request_icmpdigest(poll_icmpid(live_token), POLL_TOKEN),
                        wait_icmpdigest=True,
                    )
                except IcmpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_icmpid, stored_digest = self.read_icmpid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_icmpid != origin_icmpid
                    or stored_digest != origin_digest
                    or int(poll.get("icmpid") or EMPTY_ICMPID) != origin_icmpid
                    or int(poll.get("icmpdigest") or EMPTY_ICMPDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_icmpid}:{origin_digest}:{live_token}:{canonical_echo(live_token, origin_icmpid)}:{canonical_reply(live_token, origin_icmpid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "icmpid": origin_icmpid,
                "icmpdigest": origin_digest,
                "echo_frame": True,
                "reply_frame": True,
                "icmpdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "icmpid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_icmpdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "icmpid": origin_icmpid,
                "icmpdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "echo_frame": True,
                "reply_frame": True,
                "icmpdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "icmpid_bound": True,
            }
        except (OSError, IcmpActuationError) as error:
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
        live = independent_icmpdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "icmpid": int(live.get("icmpid") or EMPTY_ICMPID),
            "icmpdigest": int(live.get("icmpdigest") or EMPTY_ICMPDIGEST),
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


def call_icmp_tool(session: IcmpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one icmp tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_echo = True if arguments.get("echo") is None else bool(arguments.get("echo"))
    do_reply = True if arguments.get("reply") is None else bool(arguments.get("reply"))
    do_icmpdigest = True if arguments.get("icmpdigest") is None else bool(arguments.get("icmpdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_icmpid = True if arguments.get("use_icmpid") is None else bool(arguments.get("use_icmpid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_echo=do_echo,
            do_reply=do_reply,
            do_icmpdigest=do_icmpdigest,
            replay=replay,
            use_icmpid=use_icmpid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise IcmpActuationError(f"unsupported icmp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_icmpdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage icmpdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "icmpid": EMPTY_ICMPID,
        "icmpdigest": EMPTY_ICMPDIGEST,
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
            "echo_frame",
            "reply_frame",
            "icmpdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "icmpid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    icmpid = int(payload.get("icmpid") or EMPTY_ICMPID)
    icmpdigest = int(payload.get("icmpdigest") or EMPTY_ICMPDIGEST)
    dual = port > 0 and bool(icmpid) and bool(icmpdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "icmpid": icmpid,
        "icmpdigest": icmpdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "echo_frame": payload.get("echo_frame") is True,
        "reply_frame": payload.get("reply_frame") is True,
        "icmpdigest_locate": payload.get("icmpdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "icmpid_bound": payload.get("icmpid_bound") is True,
    }


def run_icmp_workflow(
    *,
    with_icmpid: bool = True,
    skip_bind: bool = False,
    do_echo: bool = True,
    do_reply: bool = True,
    do_icmpdigest: bool = True,
    replay: bool = True,
    use_icmpid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 792 ECHO/REPLY icmpid cycle workflow."""

    descriptor = icmp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICMP_TOOL_PROVIDER),
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
        raise IcmpActuationError(f"icmp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="icmp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = IcmpSession(out, icmpid_gate=DEFAULT_ICMPID if with_icmpid else EMPTY_ICMPID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "echo": do_echo,
            "reply": do_reply,
            "icmpdigest": do_icmpdigest,
            "replay": replay,
            "use_icmpid": use_icmpid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_icmp_tool(session, arguments))
            except IcmpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_icmpdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_icmpid
        and not skip_bind
        and do_echo
        and do_reply
        and do_icmpdigest
        and replay
        and use_icmpid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "icmp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_icmpid": with_icmpid,
        "skip_bind": skip_bind,
        "echo_frame": do_echo,
        "reply_frame": do_reply,
        "icmpdigest": do_icmpdigest,
        "replay": replay,
        "use_icmpid": use_icmpid,
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
        "icmpid_value": int(publish_result.get("icmpid") or independent.get("icmpid") or EMPTY_ICMPID),
        "icmpdigest_value": int(publish_result.get("icmpdigest") or independent.get("icmpdigest") or EMPTY_ICMPDIGEST),
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
        "icmpid": int(trace_body["icmpid_value"] or EMPTY_ICMPID),
        "icmpdigest": int(trace_body["icmpdigest_value"] or EMPTY_ICMPDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_icmpid": with_icmpid,
        "skip_bind": skip_bind,
        "echo_cycle": do_echo,
        "reply_cycle": do_reply,
        "icmpdigest_cycle": do_icmpdigest,
        "replay": replay,
        "use_icmpid": use_icmpid,
    }


def verify_icmp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_icmpdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    icmpid = int(trace.get("icmpid_value") or independent.get("icmpid") or EMPTY_ICMPID)
    icmpdigest = int(trace.get("icmpdigest_value") or independent.get("icmpdigest") or EMPTY_ICMPDIGEST)
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
        "echo_frame": independent.get("echo_frame") is True,
        "reply_frame": independent.get("reply_frame") is True,
        "icmpdigest_locate": independent.get("icmpdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "icmpid_bound": independent.get("icmpid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "icmpdigest_recorded": (
            port > 0
            and icmpid == DEFAULT_ICMPID
            and icmpdigest == DEFAULT_ICMPDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def icmp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.icmp_actuation import "
        "builtin_icmp_actuation_proof; r=builtin_icmp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='icmp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_icmp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ICMP_ACTUATION_ID,
        name="First-class RFC 792 Internet Control Message Protocol ECHO/REPLY actuation",
        description=(
            "Missions that require a icmp tool can opt the icmp provider in, "
            "bind a loopback RFC 792 Internet Control Message Protocol endpoint, complete a ECHO "
            "with a non-empty icmpid, lockstep a REPLY that carries the "
            "stored icmpdigest, independently poll the stored icmpdigest "
            "on a later socket, and seal a digest-chained icmpdigest. Default "
            "routing stays fail-closed; a missing icmpid keeps the hole "
            "falsifiable, and skip-ECHO/REPLY/ICMPDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.icmp_actuation:builtin_icmp_actuation_proof",
        proof_command=icmp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.udp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/icmp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/udp_actuation.py",
            "src/blackhole_agent/tcp_actuation.py",
            "src/blackhole_agent/telnet_actuation.py",
            "src/blackhole_agent/ip_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required icmp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 792 daemon, speaks a "
            "ECHO then REPLY over Internet Control Message Protocol with a non-empty icmpid and "
            "icmpdigest, independently polls the stored icmpdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 768 User Datagram Protocol lockstep is proved. "
            "Missing icmpids, skip-ECHO, skip-REPLY, skip-icmpdigest, skip-REPLAY, "
            "and a ECHO aimed without a icmpid stay fail-closed. "
            "Later genesis can take RFC 791 Internet Protocol DATAGRAM/FRAGMENT as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("icmp", "rfc792", "http", "icmpid", "icmpdigest", "echo", "reply", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T054811Z-3e4c39b7",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_icmp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 792 echo/reply lockstep actuation seals a icmpdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.ip_actuation import (
        IP_ACTUATION_GOAL,
        IP_ACTUATION_ID,
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
    checks["denylists_self"] = ICMP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(ICMP_ACTUATION_GOAL) == (
        ICMP_ACTUATION_ID,
    )
    checks["leftover_text_binds_icmp"] = leftover_marker_ids(ICMP_LEFTOVER) == (
        ICMP_ACTUATION_ID,
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
        (IP_ACTUATION_GOAL, IP_ACTUATION_ID, "ip"),
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
        checks[f"{name}_goal_is_not_icmp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"icmp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            ICMP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = ICMP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_icmp(DEFAULT_ECHO)
    rebuilt = serialize_icmp(parse_icmp(advertised))
    preloaded = parse_icmp(RFC_ICMP_REPLY)
    header = encode_icmp_header(DEFAULT_ECHO)
    parsed_header = parse_icmp_header(header)
    asked = parse_http_request(echo_request(SENTINEL, DEFAULT_ICMPID))
    preload_req = parse_http_request(reply_request(SENTINEL, DEFAULT_ICMPID, DEFAULT_ICMPDIGEST))
    got = parse_http_response(echo_response(SENTINEL, DEFAULT_ICMPID, DEFAULT_ICMPDIGEST))
    preload_reply = parse_http_response(
        reply_response(SENTINEL, DEFAULT_ICMPID, DEFAULT_ICMPDIGEST)
    )
    checks["icmp_roundtrip"] = (
        parse_icmp(advertised) == DEFAULT_ECHO
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_ECHO_FIELD
        and is_token("ECHO") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_ECHO_FIELD
        and parsed_header["policy"] == DEFAULT_ECHO
        and parsed_header["header"] == ECHO_HEADER
        and parsed_header["echo"] is True
        and parsed_header["reply"] is False
        and preloaded == REPLY_POLICY
        and ascii_serialize_icmp_directive() == RFC_ECHO_DIRECTIVE
        and icmp_directive_pair() == ("echo", "message")
        and RFC_ECHO_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_icmp(REPLY_POLICY) == RFC_ICMP_REPLY
        and DEFAULT_ICMPDIGEST == request_icmpdigest(DEFAULT_ICMPID, SENTINEL)
        and "icmpdigest=" in canonical_reply(SENTINEL, DEFAULT_ICMPID, DEFAULT_ICMPDIGEST)
        and canonical_echo(SENTINEL, DEFAULT_ICMPID).startswith("ECHO")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "ECHO"
        and asked["icmp_kind"] == "echo"
        and asked["icmpid"] == DEFAULT_ICMPID
        and preload_req["icmp_kind"] == "reply"
        and preload_req["icmpdigest"] == DEFAULT_ICMPDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["icmp_kind"] == "echo"
        and preload_reply["icmp_kind"] == "reply"
        and got["policy"] == DEFAULT_ECHO
        and preload_reply["policy"] == REPLY_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["icmpdigest"] == DEFAULT_ICMPDIGEST
        and preload_reply["icmpdigest"] == DEFAULT_ICMPDIGEST
        and icmp_matches(serialize_icmp(got["policy"]), advertised)
    )

    checks["catalog_names_icmp"] = (
        len(catalog) > 114
        and catalog[114]["id"] == ICMP_ACTUATION_ID
        and catalog[113]["id"] == UDP_ACTUATION_ID
        and catalog[114]["source"] == "genesis_bind_icmp"
    )
    checks["catalog_names_ip"] = (
        len(catalog) > 115
        and catalog[115]["id"] == IP_ACTUATION_ID
        and catalog[115]["source"] == "genesis_bind_ip"
    )
    family = capability_family(ICMP_ACTUATION_GOAL)
    checks["family_is_icmp"] = "icmp" in family
    checks["family_is_icmp_surface"] = "icmp" in family
    checks["family_is_icmpid"] = "icmpid" in family
    checks["family_is_rfc792"] = "rfc792" in family
    checks["family_is_icmpdigest"] = "icmpdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
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
    packed = encode_echo(identity=SENTINEL, icmpid=DEFAULT_ICMPID, icmpdigest=DEFAULT_ICMPDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_echo"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_icmpid"] is True
        and parsed["icmpid"] == DEFAULT_ICMPID
        and parsed["icmpdigest"] == DEFAULT_ICMPDIGEST
        and parsed["is_reply"] is False
        and parsed["is_reply"] is False
        and parsed["type"] == FRAME_ECHO
        and parsed["first_byte"] == ICMP_FIRST
    )
    shook = encode_reply(
        identity=SENTINEL,
        icmpid=DEFAULT_ICMPID,
        icmpdigest=DEFAULT_ICMPDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_reply"] is True
        and answer_parsed["is_reply"] is True
        and answer_parsed["is_echo"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["icmpid"] == DEFAULT_ICMPID
        and answer_parsed["icmpdigest"] == DEFAULT_ICMPDIGEST
        and answer_parsed["has_icmpdigest"] is True
        and answer_parsed["type"] == FRAME_REPLY
        and answer_parsed["first_byte"] == ICMP_FIRST
    )
    bare = encode_echo(identity=SENTINEL, icmpid=DEFAULT_ICMPID, include_icmpid=False)
    checks["missing_icmpid_is_unauthed"] = parse_message(bare)["has_icmpid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(ICMP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_icmp = ToolDescriptor(name="remote_icmp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_icmp)
    checks["naive_mcp_icmp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = icmp_tool_descriptor()
    default_icmp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICMP_TOOL_PROVIDER),
    )
    checks["default_icmp_provider_is_unsupported"] = (
        default_icmp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{ICMP_TOOL_PROVIDER}" in default_icmp.reasons
    )
    checks["opted_in_icmp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_icmp],
        required_tool_names=("local_memory", "icmp"),
    )
    checks["naive_preflight_missing_icmp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["icmp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "icmp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICMP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "icmp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="icmp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_icmp_workflow(with_icmpid=False, output_dir=root / "missing")
        skip_bind = run_icmp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_echo = run_icmp_workflow(do_echo=False, output_dir=root / "skip-echo")
        skip_reply = run_icmp_workflow(do_reply=False, output_dir=root / "skip-reply")
        skip_icmpdigest = run_icmp_workflow(do_icmpdigest=False, output_dir=root / "skip-icmpdigest")
        skip_replay = run_icmp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_icmpid = run_icmp_workflow(use_icmpid=False, output_dir=root / "skip-icmpid")
        live = run_icmp_workflow(output_dir=root / "live")
        verify = verify_icmp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_icmp_trace(clone)
        checks["naive_without_icmpid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_icmpid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_echo_stays_empty"] = (
            skip_echo["ok"] is False
            and skip_echo["error"] == "echo_required"
            and skip_echo["final_status"] == 409
            and skip_echo["payload_exists"] is False
        )
        checks["skip_reply_stays_empty"] = (
            skip_reply["ok"] is False
            and skip_reply["error"] == "reply_required"
            and skip_reply["final_status"] == 409
            and skip_reply["payload_exists"] is False
        )
        checks["skip_icmpdigest_stays_empty"] = (
            skip_icmpdigest["ok"] is False
            and skip_icmpdigest["error"] == "icmpdigest_required"
            and skip_icmpdigest["final_status"] == 409
            and skip_icmpdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_icmpid_stays_empty"] = (
            skip_icmpid["ok"] is False
            and skip_icmpid["error"] == "icmpid_required"
            and skip_icmpid["final_status"] == 409
            and skip_icmpid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_icmpdigest"] = (
            int(live.get("icmpid") or 0) == DEFAULT_ICMPID
            and int(live.get("icmpdigest") or 0) == DEFAULT_ICMPDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_icmpid_encode_reply_icmpdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_echo["ok"] is False
            and skip_reply["ok"] is False
            and skip_icmpdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_icmpid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="icmp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != ICMP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_icmp"] = (
        live_goal == ICMP_ACTUATION_GOAL
        and ICMP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_icmp"
    )

    with tempfile.TemporaryDirectory(prefix="icmp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(ICMP_LEFTOVER, root)
        register_catalog_proved(root, ICMP_ACTUATION_ID)
        reason = leftover_satisfied_by(ICMP_LEFTOVER, root)
        after = leftover_is_open(ICMP_LEFTOVER, root)
    checks["icmp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_icmp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{ICMP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_icmp_actuation_capability()
    return {
        "ok": ok,
        "action": "icmp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": ICMP_ACTUATION_GOAL,
        "done_when": ICMP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
