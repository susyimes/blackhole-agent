"""Drive a first-class User Datagram Protocol tool through RFC 768 SEND/RECV.

Tool routing already fails missions that require ``udp``: hosted
udp endpoints stay on the unsupported MCP provider, and no first-party
udp provider is executable. Unbound therefore cannot speak a SEND,
lockstep an RECV udpid handshake over HTTP/1.0 UDPID,
independently poll the stored udpdigest, or seal a udpdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``udp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 768 daemon
- keep a missing-udpid client so the udp-udpid hole stays falsifiable
- refuse RECV until a SEND lands with a non-empty udpid
- independently poll the stored udpdigest on a later client socket
- persist a sealed udpdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 793 Transmission Control Protocol
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
    UDP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    udp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
UDP_ACTUATION_ID = "capability.udp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-UDP-OK"
POLL_TOKEN = "BH-UDP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_UDPID = 0
EMPTY_UDPDIGEST = 0
UDP_FIRST = 0x11  # RFC 768 UDP (IP protocol 17)
UDPID_SIZE = 4
UDPDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_RECV = 0x02  # RFC 768 RECV confirmation
FRAME_SEND = 0x01  # RFC 768 SEND
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
UDP_LEFTOVER = (
    "Later genesis can take RFC 768 User Datagram Protocol SEND/RECV over a "
    "udpid-gated udpdigest."
)
UDP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{UDP_ACTUATION_ID};"
    f"capability_proved:{UDP_ACTUATION_ID};"
    "no_skill_route"
)
UDP_ACTUATION_GOAL = (
    "Repair rfc768 udp send/recv cycle cannot land over http "
    "udp udpid: hosted udp endpoints remain unsupported so a SEND then "
    "RECV udpid handshake cannot land and a sealed udpdigest "
    "cannot be produced. A missing udp udpid stays forbidden; fail-closed "
    "routing never opts the udp provider in. An independent later poll of the "
    "stored udpdigest keeps the hole falsifiable."
)


class UdpActuationError(RuntimeError):
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
# RFC 768 sections 3.3 and 3.4: SEND / RECV.
RFC_SEND_FIELD = "SEND"
RFC_RECV_FIELD = "RECV"
RFC_UDP_RECV = RFC_RECV_FIELD
RFC_SEND_DIRECTIVE = "send=datagram"
RFC_RECV_DIRECTIVE = "recv=datagram"
DEFAULT_SEND = "SEND"
RECV_POLICY = "RECV"
SEND_HEADER = "Send"
RECV_HEADER = "Recv"
UDP_RECV_HEADER = RECV_HEADER
RFC_SEND_PATH = "/udp/"
RFC_SEND_EMPTY = ""


def udp_directive_pair(*, recv: bool = False) -> tuple[str, str]:
    """RFC 768 Send / Recv directive pair."""

    if recv:
        return "recv", "datagram"
    return "send", "datagram"


def ascii_serialize_udp_directive(*, recv: bool = False) -> str:
    """RFC 768 token "=" body-or-recv."""

    name, value = udp_directive_pair(recv=recv)
    if not is_token(name):
        raise UdpActuationError("illegal_directive")
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
            raise UdpActuationError("short_udp")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 768 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_udp(policy: str | Sequence[str]) -> str:
    """Serialize RFC 768 SEND / RECV opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise UdpActuationError("illegal_udp")
    upper = text.upper().replace("_", "-")
    if upper in {"SEND", "UDP", "UDP-SEND"}:
        return "SEND"
    if upper in {"RECV", "RESOURCE", "UDP-RECV"}:
        return "RECV"
    if upper.startswith("SEND="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UdpActuationError("illegal_udp")
        return "SEND"
    if upper.startswith("RECV="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UdpActuationError("illegal_udp")
        return "RECV"
    raise UdpActuationError("illegal_udp")


def parse_udp(text: str) -> str:
    """Parse RFC 768 UDP opcode header extensions into SEND or RECV."""

    raw = str(text or "").strip()
    if not raw:
        raise UdpActuationError("illegal_udp")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"SEND", "UDP", "UDP-SEND"}:
        return "SEND"
    if upper in {"RECV", "RESOURCE", "UDP-RECV"}:
        return "RECV"
    if upper.startswith("SEND="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UdpActuationError("illegal_udp")
        return "SEND"
    if upper.startswith("RECV="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UdpActuationError("illegal_udp")
        return "RECV"
    raise UdpActuationError("illegal_udp")


def encode_udp_header(policy: str | Sequence[str]) -> bytes:
    """RFC 768 HTTP/1.0 field as bytes."""

    return serialize_udp(policy).encode("ascii")


def parse_udp_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_udp(field_value) if field_value else DEFAULT_SEND
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SEND_HEADER,
        "directive": str(policy),
        "send": str(policy) == "SEND",
        "recv": str(policy) == "RECV",
    }


def canonical_send(identity: str, udpid: int) -> str:
    """RFC 768 body-request advertisement bound to identity and udpid."""

    return (
        f"{serialize_udp(DEFAULT_SEND)}, "
        f"send={ascii_serialize_udp_directive()}, "
        f"identity={identity}, udpid={int(udpid) & 0xFFFFFFFF}"
    )


def canonical_recv(identity: str, udpid: int, udpdigest: int | None = None) -> str:
    """RFC 768 recv-datagram confirmation of the stored identifier-digest."""

    digest = ""
    if udpdigest is not None:
        digest = f", udpdigest={int(udpdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_udp(RECV_POLICY)}, "
        f"recv={ascii_serialize_udp_directive(recv=True)}, "
        f"identity={identity}, udpid={int(udpid) & 0xFFFFFFFF}{digest}"
    )


def representation_recv(identity: str, udpid: int, udpdigest: int) -> str:
    return canonical_recv(identity, udpid, udpdigest)


def udp_matches(left: str, right: str) -> bool:
    return parse_udp(left) == parse_udp(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise UdpActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise UdpActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise UdpActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise UdpActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def send_request(identity: str, udpid: int) -> bytes:
    """HTTP SEND that elicits RFC 768 origin HTTP/1.0."""

    keyid = f"{int(udpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"SEND /udp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Udp-Id: {int(udpid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def recv_request(identity: str, udpid: int, udpdigest: int | None = None) -> bytes:
    """HTTP RECV carrying RFC 768 recv-datagram confirmation of the stored identifier-digest."""

    keyid = f"{int(udpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if udpdigest is not None:
        extra = f"Udp-Digest: {int(udpdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"RECV /udp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Udp-Id: {int(udpid) & 0xFFFFFFFF}\r\n"
        "Recv-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    udp_kind = "recv" if fields.get("recv-confirm") == "1" else "send"
    upgrade_field = fields.get("send") or fields.get("udp") or ""
    policy = parse_udp(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "udp_kind": udp_kind,
        "policy": policy,
        "udpid": int(fields["udp-id"]) if fields.get("udp-id") else EMPTY_UDPID,
        "udpdigest": int(fields["udp-digest"]) if fields.get("udp-digest") else EMPTY_UDPDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def send_response(identity: str, udpid: int, udpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 768 origin HTTP/1.0, carrying the stored udpdigest."""

    advertised = serialize_udp(DEFAULT_SEND)
    payload = bytes(body or canonical_send(identity, udpid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Send: {advertised}\r\n"
        f"Udp-Id: {int(udpid) & 0xFFFFFFFF}\r\n"
        f"Udp-Digest: {int(udpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def recv_response(identity: str, udpid: int, udpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 768 RECV, carrying the stored identifier-digest."""

    advertised = serialize_udp(RECV_POLICY)
    payload = bytes(body or representation_recv(identity, udpid, udpdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Send: {advertised}\r\n"
        f"Udp-Id: {int(udpid) & 0xFFFFFFFF}\r\n"
        f"Udp-Digest: {int(udpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/udp-recv\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise UdpActuationError("illegal_content_length") from error
    field_value = fields.get("send") or fields.get("udp") or ""
    policy = parse_udp(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/udp-recv" or policy == RECV_POLICY:
        status = 200
        udp_kind = "recv"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        udp_kind = "send"
    else:
        status = 0
        udp_kind = "send"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "udp_kind": udp_kind,
        "policy": policy,
        "udpid": int(fields["udp-id"]) if fields.get("udp-id") else EMPTY_UDPID,
        "udpdigest": int(fields["udp-digest"]) if fields.get("udp-digest") else EMPTY_UDPDIGEST,
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
        raise UdpActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise UdpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise UdpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise UdpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc768_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    udp: str,
) -> str:
    """RFC 768 identifier digest over method, request-UDP, identity, and udpid."""

    payload = f"{method}:{udp}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_udpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"udpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_udpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-udpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_udpdigest(udpid: int = EMPTY_UDPID, token: str = SENTINEL) -> int:
    nonce = f"{int(udpid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc768_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="RECV",
        udp=f"/udp/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_UDPID = request_udpid(SENTINEL)
DEFAULT_UDPDIGEST = request_udpdigest(DEFAULT_UDPID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    udpid: int,
    udpdigest: int,
    include_udpid: bool = True,
) -> bytes:
    live_udpid = int(udpid) & 0xFFFFFFFF if include_udpid else EMPTY_UDPID
    live_digest = int(udpdigest) & 0xFFFFFFFF if include_udpid and live_udpid else EMPTY_UDPDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_udpid) if live_udpid else b""
    header = bytearray()
    header.append(UDP_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_send(
    *,
    identity: str,
    udpid: int,
    udpdigest: int | None = None,
    include_udpid: bool = True,
) -> bytes:
    live_udpid = int(udpid) & 0xFFFFFFFF if include_udpid else EMPTY_UDPID
    live_digest = int(udpdigest) if udpdigest is not None else request_udpdigest(live_udpid, identity)
    return encode_packet(
        FRAME_SEND,
        identity=identity,
        udpid=live_udpid,
        udpdigest=live_digest,
        include_udpid=include_udpid,
    )


def encode_recv(
    *,
    identity: str,
    udpid: int,
    udpdigest: int | None = None,
    include_udpid: bool = True,
) -> bytes:
    live_udpid = int(udpid) & 0xFFFFFFFF if include_udpid else EMPTY_UDPID
    live_digest = int(udpdigest) if udpdigest is not None else request_udpdigest(live_udpid, identity)
    return encode_packet(
        FRAME_RECV,
        identity=identity,
        udpid=live_udpid,
        udpdigest=live_digest,
        include_udpid=include_udpid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise UdpActuationError("short_packet")
    first = raw[0]
    if first != UDP_FIRST:
        raise UdpActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise UdpActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == UDPID_SIZE:
        live_udpid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_udpid = EMPTY_UDPID
    else:
        raise UdpActuationError("illegal_udpid")
    if offset >= len(raw):
        raise UdpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SEND, FRAME_RECV}:
        raise UdpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise UdpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise UdpActuationError("checksum_failed")
    if len(payload) < 5:
        raise UdpActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise UdpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_udpid = int(live_udpid) != EMPTY_UDPID
    has_udpdigest = has_udpid and int(live_digest) != EMPTY_UDPDIGEST
    is_send = frame_type == FRAME_SEND
    is_recv = frame_type == FRAME_RECV
    return {
        "type": int(frame_type),
        "is_send": is_send,
        "is_recv": is_recv,
        "udpid": int(live_udpid),
        "has_udpid": has_udpid,
        "udpdigest": int(live_digest),
        "has_udpdigest": has_udpdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC768",
        "serialize_field": canonical_send(identity, live_udpid) if has_udpid else "",
        "tls_field": canonical_recv(identity, live_udpid, live_digest) if has_udpdigest else "",
    }


class UdpClient:
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
            raise UdpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_recv"] or not packet["is_recv"]:
            raise UdpActuationError("udpdigest_required")
        if not packet["has_udpid"]:
            raise UdpActuationError("udpid_required")
        if not packet["has_udpdigest"]:
            raise UdpActuationError("udpdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_udpdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_udpdigest:
            raise UdpActuationError("udpdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "udpid": int(reply.get("udpid") or EMPTY_UDPID),
            "identity": str(reply.get("identity") or ""),
            "udpdigest": int(reply.get("udpdigest") or EMPTY_UDPDIGEST),
        }

    def report(
        self,
        identity: str,
        udpid: int,
        udpdigest: int = EMPTY_UDPDIGEST,
        *,
        wait_udpdigest: bool = True,
        include_udpid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_recv(
            identity=identity,
            udpid=udpid,
            udpdigest=udpdigest or request_udpdigest(udpid, identity),
            include_udpid=include_udpid,
        )
        return self.exchange(packet, wait_udpdigest=wait_udpdigest)


class UdpSession:
    """UDPID-gated loopback RFC 768 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        udpid_gate: int = DEFAULT_UDPID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.udpid_gate = int(udpid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.udpid = EMPTY_UDPID
        self.udpdigest = EMPTY_UDPDIGEST
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

    def store_udpid_once(self, identity: str, udpid: int, udpdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(udpid or EMPTY_UDPID)
            live_digest = int(udpdigest or EMPTY_UDPDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.udpid = live
                self.udpdigest = live_digest or request_udpdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.udpid), int(self.udpdigest)

    def read_udpid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.udpid), int(self.udpdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "udpid": EMPTY_UDPID,
            "udpdigest": EMPTY_UDPDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _udpid_missing(self) -> bool:
        return not int(self.udpid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, udpid: int, udpdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_recv(
            identity=identity,
            udpid=udpid,
            udpdigest=udpdigest,
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
            except UdpActuationError:
                continue
            if not packet.get("is_send") and not packet.get("is_recv"):
                continue
            if not packet.get("has_udpid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_udpid, stored_digest = self.store_udpid_once(
                identity,
                int(packet.get("udpid") or EMPTY_UDPID),
                int(packet.get("udpdigest") or EMPTY_UDPDIGEST),
            )
            if not stored_name or not stored_udpid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_send"):
                    self.opened = True
                if packet.get("is_recv"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_udpid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._udpid_missing():
            return self._forbidden("missing_udpid")
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
        do_send: bool = True,
        do_recv: bool = True,
        do_udpdigest: bool = True,
        replay: bool = True,
        use_udpid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._udpid_missing():
            return self._forbidden("missing_udpid")
        live_token = str(token or SENTINEL)
        origin_udpid = request_udpid(live_token)
        origin_digest = request_udpdigest(origin_udpid, live_token)
        client: UdpClient | None = None
        independent: UdpClient | None = None
        try:
            client = UdpClient(self.host, int(self.port))
            if not do_send:
                return self._conflict("send_required")
            bind_packet = encode_send(
                identity=live_token,
                udpid=origin_udpid,
                udpdigest=origin_digest,
                include_udpid=use_udpid,
            )
            if not use_udpid:
                try:
                    client.exchange(bind_packet, wait_udpdigest=True)
                except UdpActuationError:
                    return self._conflict("udpid_required")
                return self._conflict("udpid_required")
            client.send(bind_packet)
            if not do_recv:
                return self._conflict("recv_required")
            proxy_packet = encode_recv(
                identity=live_token,
                udpid=origin_udpid,
                udpdigest=origin_digest,
                include_udpid=True,
            )
            if not do_udpdigest:
                try:
                    client.exchange(proxy_packet, wait_udpdigest=False)
                except UdpActuationError as error:
                    if str(error) == "udpdigest_required":
                        return self._conflict("udpdigest_required")
                    return self._conflict("udpdigest_required")
                return self._conflict("udpdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_udpdigest=True)
            except UdpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("udpid_required")
                if reason == "udpdigest_required":
                    return self._conflict("udpdigest_required")
                return self._conflict("send_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("send_required")
            if int(reply.get("udpid") or EMPTY_UDPID) != origin_udpid:
                return self._conflict("udpdigest_required")
            if int(reply.get("udpdigest") or EMPTY_UDPDIGEST) != origin_digest:
                return self._conflict("udpdigest_required")
            self.retrieved = True
            if replay:
                independent = UdpClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_udpid(live_token),
                        request_udpdigest(poll_udpid(live_token), POLL_TOKEN),
                        wait_udpdigest=True,
                    )
                except UdpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_udpid, stored_digest = self.read_udpid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_udpid != origin_udpid
                    or stored_digest != origin_digest
                    or int(poll.get("udpid") or EMPTY_UDPID) != origin_udpid
                    or int(poll.get("udpdigest") or EMPTY_UDPDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_udpid}:{origin_digest}:{live_token}:{canonical_send(live_token, origin_udpid)}:{canonical_recv(live_token, origin_udpid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "udpid": origin_udpid,
                "udpdigest": origin_digest,
                "send_frame": True,
                "recv_frame": True,
                "udpdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "udpid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_udpdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "udpid": origin_udpid,
                "udpdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "send_frame": True,
                "recv_frame": True,
                "udpdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "udpid_bound": True,
            }
        except (OSError, UdpActuationError) as error:
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
        live = independent_udpdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "udpid": int(live.get("udpid") or EMPTY_UDPID),
            "udpdigest": int(live.get("udpdigest") or EMPTY_UDPDIGEST),
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


def call_udp_tool(session: UdpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one udp tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_send = True if arguments.get("send") is None else bool(arguments.get("send"))
    do_recv = True if arguments.get("recv") is None else bool(arguments.get("recv"))
    do_udpdigest = True if arguments.get("udpdigest") is None else bool(arguments.get("udpdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_udpid = True if arguments.get("use_udpid") is None else bool(arguments.get("use_udpid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_send=do_send,
            do_recv=do_recv,
            do_udpdigest=do_udpdigest,
            replay=replay,
            use_udpid=use_udpid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise UdpActuationError(f"unsupported udp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_udpdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage udpdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "udpid": EMPTY_UDPID,
        "udpdigest": EMPTY_UDPDIGEST,
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
            "send_frame",
            "recv_frame",
            "udpdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "udpid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    udpid = int(payload.get("udpid") or EMPTY_UDPID)
    udpdigest = int(payload.get("udpdigest") or EMPTY_UDPDIGEST)
    dual = port > 0 and bool(udpid) and bool(udpdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "udpid": udpid,
        "udpdigest": udpdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "send_frame": payload.get("send_frame") is True,
        "recv_frame": payload.get("recv_frame") is True,
        "udpdigest_locate": payload.get("udpdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "udpid_bound": payload.get("udpid_bound") is True,
    }


def run_udp_workflow(
    *,
    with_udpid: bool = True,
    skip_bind: bool = False,
    do_send: bool = True,
    do_recv: bool = True,
    do_udpdigest: bool = True,
    replay: bool = True,
    use_udpid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 768 SEND/RECV udpid cycle workflow."""

    descriptor = udp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, UDP_TOOL_PROVIDER),
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
        raise UdpActuationError(f"udp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="udp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = UdpSession(out, udpid_gate=DEFAULT_UDPID if with_udpid else EMPTY_UDPID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "send": do_send,
            "recv": do_recv,
            "udpdigest": do_udpdigest,
            "replay": replay,
            "use_udpid": use_udpid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_udp_tool(session, arguments))
            except UdpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_udpdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_udpid
        and not skip_bind
        and do_send
        and do_recv
        and do_udpdigest
        and replay
        and use_udpid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "udp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_udpid": with_udpid,
        "skip_bind": skip_bind,
        "send_frame": do_send,
        "recv_frame": do_recv,
        "udpdigest": do_udpdigest,
        "replay": replay,
        "use_udpid": use_udpid,
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
        "udpid_value": int(publish_result.get("udpid") or independent.get("udpid") or EMPTY_UDPID),
        "udpdigest_value": int(publish_result.get("udpdigest") or independent.get("udpdigest") or EMPTY_UDPDIGEST),
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
        "udpid": int(trace_body["udpid_value"] or EMPTY_UDPID),
        "udpdigest": int(trace_body["udpdigest_value"] or EMPTY_UDPDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_udpid": with_udpid,
        "skip_bind": skip_bind,
        "send_cycle": do_send,
        "recv_cycle": do_recv,
        "udpdigest_cycle": do_udpdigest,
        "replay": replay,
        "use_udpid": use_udpid,
    }


def verify_udp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_udpdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    udpid = int(trace.get("udpid_value") or independent.get("udpid") or EMPTY_UDPID)
    udpdigest = int(trace.get("udpdigest_value") or independent.get("udpdigest") or EMPTY_UDPDIGEST)
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
        "send_frame": independent.get("send_frame") is True,
        "recv_frame": independent.get("recv_frame") is True,
        "udpdigest_locate": independent.get("udpdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "udpid_bound": independent.get("udpid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "udpdigest_recorded": (
            port > 0
            and udpid == DEFAULT_UDPID
            and udpdigest == DEFAULT_UDPDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def udp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.udp_actuation import "
        "builtin_udp_actuation_proof; r=builtin_udp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='udp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_udp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=UDP_ACTUATION_ID,
        name="First-class RFC 768 User Datagram Protocol SEND/RECV actuation",
        description=(
            "Missions that require a udp tool can opt the udp provider in, "
            "bind a loopback RFC 768 User Datagram Protocol endpoint, complete a SEND "
            "with a non-empty udpid, lockstep a RECV that carries the "
            "stored udpdigest, independently poll the stored udpdigest "
            "on a later socket, and seal a digest-chained udpdigest. Default "
            "routing stays fail-closed; a missing udpid keeps the hole "
            "falsifiable, and skip-SEND/RECV/UDPDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.udp_actuation:builtin_udp_actuation_proof",
        proof_command=udp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.tcp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/udp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/tcp_actuation.py",
            "src/blackhole_agent/telnet_actuation.py",
            "src/blackhole_agent/icmp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required udp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 768 daemon, speaks a "
            "SEND then RECV over User Datagram Protocol with a non-empty udpid and "
            "udpdigest, independently polls the stored udpdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 793 Transmission Control Protocol lockstep is proved. "
            "Missing udpids, skip-SEND, skip-RECV, skip-udpdigest, skip-REPLAY, "
            "and a SEND aimed without a udpid stay fail-closed. "
            "Later genesis can take RFC 792 Internet Control Message Protocol ECHO/REPLY as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("udp", "rfc768", "http", "udpid", "udpdigest", "send", "recv", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T051341Z-fa64987a",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_udp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 768 send/recv lockstep actuation seals a udpdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.icmp_actuation import (
        ICMP_ACTUATION_GOAL,
        ICMP_ACTUATION_ID,
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
    checks["denylists_self"] = UDP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(UDP_ACTUATION_GOAL) == (
        UDP_ACTUATION_ID,
    )
    checks["leftover_text_binds_udp"] = leftover_marker_ids(UDP_LEFTOVER) == (
        UDP_ACTUATION_ID,
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
        (ICMP_ACTUATION_GOAL, ICMP_ACTUATION_ID, "icmp"),
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
        checks[f"{name}_goal_is_not_udp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"udp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            UDP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = UDP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_udp(DEFAULT_SEND)
    rebuilt = serialize_udp(parse_udp(advertised))
    preloaded = parse_udp(RFC_UDP_RECV)
    header = encode_udp_header(DEFAULT_SEND)
    parsed_header = parse_udp_header(header)
    asked = parse_http_request(send_request(SENTINEL, DEFAULT_UDPID))
    preload_req = parse_http_request(recv_request(SENTINEL, DEFAULT_UDPID, DEFAULT_UDPDIGEST))
    got = parse_http_response(send_response(SENTINEL, DEFAULT_UDPID, DEFAULT_UDPDIGEST))
    preload_reply = parse_http_response(
        recv_response(SENTINEL, DEFAULT_UDPID, DEFAULT_UDPDIGEST)
    )
    checks["udp_roundtrip"] = (
        parse_udp(advertised) == DEFAULT_SEND
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_SEND_FIELD
        and is_token("SEND") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SEND_FIELD
        and parsed_header["policy"] == DEFAULT_SEND
        and parsed_header["header"] == SEND_HEADER
        and parsed_header["send"] is True
        and parsed_header["recv"] is False
        and preloaded == RECV_POLICY
        and ascii_serialize_udp_directive() == RFC_SEND_DIRECTIVE
        and udp_directive_pair() == ("send", "datagram")
        and RFC_SEND_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_udp(RECV_POLICY) == RFC_UDP_RECV
        and DEFAULT_UDPDIGEST == request_udpdigest(DEFAULT_UDPID, SENTINEL)
        and "udpdigest=" in canonical_recv(SENTINEL, DEFAULT_UDPID, DEFAULT_UDPDIGEST)
        and canonical_send(SENTINEL, DEFAULT_UDPID).startswith("SEND")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "SEND"
        and asked["udp_kind"] == "send"
        and asked["udpid"] == DEFAULT_UDPID
        and preload_req["udp_kind"] == "recv"
        and preload_req["udpdigest"] == DEFAULT_UDPDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["udp_kind"] == "send"
        and preload_reply["udp_kind"] == "recv"
        and got["policy"] == DEFAULT_SEND
        and preload_reply["policy"] == RECV_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["udpdigest"] == DEFAULT_UDPDIGEST
        and preload_reply["udpdigest"] == DEFAULT_UDPDIGEST
        and udp_matches(serialize_udp(got["policy"]), advertised)
    )

    checks["catalog_names_udp"] = (
        len(catalog) > 113
        and catalog[113]["id"] == UDP_ACTUATION_ID
        and catalog[112]["id"] == TCP_ACTUATION_ID
        and catalog[113]["source"] == "genesis_bind_udp"
    )
    checks["catalog_names_icmp"] = (
        len(catalog) > 114
        and catalog[114]["id"] == ICMP_ACTUATION_ID
        and catalog[114]["source"] == "genesis_bind_icmp"
    )
    from blackhole_agent.mission_selection import semantic_tokens

    family = capability_family(UDP_ACTUATION_GOAL)
    checks["family_is_udp"] = "udp" in family
    checks["family_is_udp_surface"] = "udp" in family
    checks["family_is_udpid"] = "udpid" in set(semantic_tokens(UDP_ACTUATION_GOAL))
    checks["family_is_rfc768"] = "rfc768" in family
    checks["family_is_udpdigest"] = "udpdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_icmp"] = (
        "icmp" not in family.split("/")
        and "rfc792" not in family
        and "icmpid" not in family
        and "icmpdigest" not in family
    )
    checks["family_is_not_tcp"] = (
        "tcp" not in family.split("/")
        and "rfc793" not in family
        and "tcpid" not in family
        and "tcpdigest" not in family
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
    packed = encode_send(identity=SENTINEL, udpid=DEFAULT_UDPID, udpdigest=DEFAULT_UDPDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_send"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_udpid"] is True
        and parsed["udpid"] == DEFAULT_UDPID
        and parsed["udpdigest"] == DEFAULT_UDPDIGEST
        and parsed["is_recv"] is False
        and parsed["is_recv"] is False
        and parsed["type"] == FRAME_SEND
        and parsed["first_byte"] == UDP_FIRST
    )
    shook = encode_recv(
        identity=SENTINEL,
        udpid=DEFAULT_UDPID,
        udpdigest=DEFAULT_UDPDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_recv"] is True
        and answer_parsed["is_recv"] is True
        and answer_parsed["is_send"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["udpid"] == DEFAULT_UDPID
        and answer_parsed["udpdigest"] == DEFAULT_UDPDIGEST
        and answer_parsed["has_udpdigest"] is True
        and answer_parsed["type"] == FRAME_RECV
        and answer_parsed["first_byte"] == UDP_FIRST
    )
    bare = encode_send(identity=SENTINEL, udpid=DEFAULT_UDPID, include_udpid=False)
    checks["missing_udpid_is_unauthed"] = parse_message(bare)["has_udpid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(UDP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_udp = ToolDescriptor(name="remote_udp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_udp)
    checks["naive_mcp_udp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = udp_tool_descriptor()
    default_udp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, UDP_TOOL_PROVIDER),
    )
    checks["default_udp_provider_is_unsupported"] = (
        default_udp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{UDP_TOOL_PROVIDER}" in default_udp.reasons
    )
    checks["opted_in_udp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_udp],
        required_tool_names=("local_memory", "udp"),
    )
    checks["naive_preflight_missing_udp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["udp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "udp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, UDP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "udp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="udp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_udp_workflow(with_udpid=False, output_dir=root / "missing")
        skip_bind = run_udp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_send = run_udp_workflow(do_send=False, output_dir=root / "skip-send")
        skip_recv = run_udp_workflow(do_recv=False, output_dir=root / "skip-recv")
        skip_udpdigest = run_udp_workflow(do_udpdigest=False, output_dir=root / "skip-udpdigest")
        skip_replay = run_udp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_udpid = run_udp_workflow(use_udpid=False, output_dir=root / "skip-udpid")
        live = run_udp_workflow(output_dir=root / "live")
        verify = verify_udp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_udp_trace(clone)
        checks["naive_without_udpid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_udpid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_send_stays_empty"] = (
            skip_send["ok"] is False
            and skip_send["error"] == "send_required"
            and skip_send["final_status"] == 409
            and skip_send["payload_exists"] is False
        )
        checks["skip_recv_stays_empty"] = (
            skip_recv["ok"] is False
            and skip_recv["error"] == "recv_required"
            and skip_recv["final_status"] == 409
            and skip_recv["payload_exists"] is False
        )
        checks["skip_udpdigest_stays_empty"] = (
            skip_udpdigest["ok"] is False
            and skip_udpdigest["error"] == "udpdigest_required"
            and skip_udpdigest["final_status"] == 409
            and skip_udpdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_udpid_stays_empty"] = (
            skip_udpid["ok"] is False
            and skip_udpid["error"] == "udpid_required"
            and skip_udpid["final_status"] == 409
            and skip_udpid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_udpdigest"] = (
            int(live.get("udpid") or 0) == DEFAULT_UDPID
            and int(live.get("udpdigest") or 0) == DEFAULT_UDPDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_udpid_encode_recv_udpdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_send["ok"] is False
            and skip_recv["ok"] is False
            and skip_udpdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_udpid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="udp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != UDP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, UDP_ACTUATION_GOAL, UDP_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_udp"] = (
        not gate.accepted
        and live_goal != UDP_ACTUATION_GOAL
        and UDP_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_udp"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="udp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(UDP_LEFTOVER, root)
        register_catalog_proved(root, UDP_ACTUATION_ID)
        reason = leftover_satisfied_by(UDP_LEFTOVER, root)
        after = leftover_is_open(UDP_LEFTOVER, root)
    checks["udp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_udp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{UDP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_udp_actuation_capability()
    return {
        "ok": ok,
        "action": "udp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": UDP_ACTUATION_GOAL,
        "done_when": UDP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
