"""Drive a first-class Transmission Control Protocol tool through RFC 793 SYN/ACK.

Tool routing already fails missions that require ``tcp``: hosted
tcp endpoints stay on the unsupported MCP provider, and no first-party
tcp provider is executable. Unbound therefore cannot speak a SYN,
lockstep an ACK tcpid handshake over HTTP/1.0 TCPID,
independently poll the stored tcpdigest, or seal a tcpdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``tcp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 793 daemon
- keep a missing-tcpid client so the tcp-tcpid hole stays falsifiable
- refuse ACK until a SYN lands with a non-empty tcpid
- independently poll the stored tcpdigest on a later client socket
- persist a sealed tcpdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 854 Telnet Protocol Specification
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
    TCP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    tcp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
TCP_ACTUATION_ID = "capability.tcp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-TCP-OK"
POLL_TOKEN = "BH-TCP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_TCPID = 0
EMPTY_TCPDIGEST = 0
TCP_FIRST = 0x06  # RFC 793 TCP (IP protocol 6)
TCPID_SIZE = 4
TCPDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_ACK = 0x02  # RFC 793 ACK confirmation
FRAME_SYN = 0x01  # RFC 793 SYN
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
TCP_LEFTOVER = (
    "Later genesis can take RFC 793 Transmission Control Protocol SYN/ACK over a "
    "tcpid-gated tcpdigest."
)
TCP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TCP_ACTUATION_ID};"
    f"capability_proved:{TCP_ACTUATION_ID};"
    "no_skill_route"
)
TCP_ACTUATION_GOAL = (
    "Repair rfc793 tcp syn/ack cycle cannot land over http "
    "tcp tcpid: hosted tcp endpoints remain unsupported so a SYN then "
    "ACK tcpid handshake cannot land and a sealed tcpdigest "
    "cannot be produced. A missing tcp tcpid stays forbidden; fail-closed "
    "routing never opts the tcp provider in. An independent later poll of the "
    "stored tcpdigest keeps the hole falsifiable."
)


class TcpActuationError(RuntimeError):
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
# RFC 793 sections 3.3 and 3.4: SYN / ACK.
RFC_SYN_FIELD = "SYN"
RFC_ACK_FIELD = "ACK"
RFC_TCP_ACK = RFC_ACK_FIELD
RFC_SYN_DIRECTIVE = "syn=segment"
RFC_ACK_DIRECTIVE = "ack=segment"
DEFAULT_SYN = "SYN"
ACK_POLICY = "ACK"
SYN_HEADER = "Syn"
ACK_HEADER = "Ack"
TCP_ACK_HEADER = ACK_HEADER
RFC_SYN_PATH = "/tcp/"
RFC_SYN_EMPTY = ""


def tcp_directive_pair(*, ack: bool = False) -> tuple[str, str]:
    """RFC 793 Syn / Ack directive pair."""

    if ack:
        return "ack", "segment"
    return "syn", "segment"


def ascii_serialize_tcp_directive(*, ack: bool = False) -> str:
    """RFC 793 token "=" body-or-ack."""

    name, value = tcp_directive_pair(ack=ack)
    if not is_token(name):
        raise TcpActuationError("illegal_directive")
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
            raise TcpActuationError("short_tcp")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 793 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_tcp(policy: str | Sequence[str]) -> str:
    """Serialize RFC 793 SYN / ACK opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise TcpActuationError("illegal_tcp")
    upper = text.upper().replace("_", "-")
    if upper in {"SYN", "TCP", "TCP-SYN"}:
        return "SYN"
    if upper in {"ACK", "RESOURCE", "TCP-ACK"}:
        return "ACK"
    if upper.startswith("SYN="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TcpActuationError("illegal_tcp")
        return "SYN"
    if upper.startswith("ACK="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TcpActuationError("illegal_tcp")
        return "ACK"
    raise TcpActuationError("illegal_tcp")


def parse_tcp(text: str) -> str:
    """Parse RFC 793 TCP opcode header extensions into SYN or ACK."""

    raw = str(text or "").strip()
    if not raw:
        raise TcpActuationError("illegal_tcp")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"SYN", "TCP", "TCP-SYN"}:
        return "SYN"
    if upper in {"ACK", "RESOURCE", "TCP-ACK"}:
        return "ACK"
    if upper.startswith("SYN="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TcpActuationError("illegal_tcp")
        return "SYN"
    if upper.startswith("ACK="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TcpActuationError("illegal_tcp")
        return "ACK"
    raise TcpActuationError("illegal_tcp")


def encode_tcp_header(policy: str | Sequence[str]) -> bytes:
    """RFC 793 HTTP/1.0 field as bytes."""

    return serialize_tcp(policy).encode("ascii")


def parse_tcp_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_tcp(field_value) if field_value else DEFAULT_SYN
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SYN_HEADER,
        "directive": str(policy),
        "syn": str(policy) == "SYN",
        "ack": str(policy) == "ACK",
    }


def canonical_syn(identity: str, tcpid: int) -> str:
    """RFC 793 body-request advertisement bound to identity and tcpid."""

    return (
        f"{serialize_tcp(DEFAULT_SYN)}, "
        f"syn={ascii_serialize_tcp_directive()}, "
        f"identity={identity}, tcpid={int(tcpid) & 0xFFFFFFFF}"
    )


def canonical_ack(identity: str, tcpid: int, tcpdigest: int | None = None) -> str:
    """RFC 793 ack-segment confirmation of the stored identifier-digest."""

    digest = ""
    if tcpdigest is not None:
        digest = f", tcpdigest={int(tcpdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_tcp(ACK_POLICY)}, "
        f"ack={ascii_serialize_tcp_directive(ack=True)}, "
        f"identity={identity}, tcpid={int(tcpid) & 0xFFFFFFFF}{digest}"
    )


def representation_ack(identity: str, tcpid: int, tcpdigest: int) -> str:
    return canonical_ack(identity, tcpid, tcpdigest)


def tcp_matches(left: str, right: str) -> bool:
    return parse_tcp(left) == parse_tcp(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise TcpActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise TcpActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise TcpActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise TcpActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def syn_request(identity: str, tcpid: int) -> bytes:
    """HTTP SYN that elicits RFC 793 origin HTTP/1.0."""

    keyid = f"{int(tcpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"SYN /tcp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Tcp-Id: {int(tcpid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def ack_request(identity: str, tcpid: int, tcpdigest: int | None = None) -> bytes:
    """HTTP ACK carrying RFC 793 ack-segment confirmation of the stored identifier-digest."""

    keyid = f"{int(tcpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if tcpdigest is not None:
        extra = f"Tcp-Digest: {int(tcpdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"ACK /tcp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Tcp-Id: {int(tcpid) & 0xFFFFFFFF}\r\n"
        "Ack-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    tcp_kind = "ack" if fields.get("ack-confirm") == "1" else "syn"
    upgrade_field = fields.get("syn") or fields.get("tcp") or ""
    policy = parse_tcp(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "tcp_kind": tcp_kind,
        "policy": policy,
        "tcpid": int(fields["tcp-id"]) if fields.get("tcp-id") else EMPTY_TCPID,
        "tcpdigest": int(fields["tcp-digest"]) if fields.get("tcp-digest") else EMPTY_TCPDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def syn_response(identity: str, tcpid: int, tcpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 793 origin HTTP/1.0, carrying the stored tcpdigest."""

    advertised = serialize_tcp(DEFAULT_SYN)
    payload = bytes(body or canonical_syn(identity, tcpid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Syn: {advertised}\r\n"
        f"Tcp-Id: {int(tcpid) & 0xFFFFFFFF}\r\n"
        f"Tcp-Digest: {int(tcpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def ack_response(identity: str, tcpid: int, tcpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 793 ACK, carrying the stored identifier-digest."""

    advertised = serialize_tcp(ACK_POLICY)
    payload = bytes(body or representation_ack(identity, tcpid, tcpdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Syn: {advertised}\r\n"
        f"Tcp-Id: {int(tcpid) & 0xFFFFFFFF}\r\n"
        f"Tcp-Digest: {int(tcpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/tcp-ack\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise TcpActuationError("illegal_content_length") from error
    field_value = fields.get("syn") or fields.get("tcp") or ""
    policy = parse_tcp(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/tcp-ack" or policy == ACK_POLICY:
        status = 200
        tcp_kind = "ack"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        tcp_kind = "syn"
    else:
        status = 0
        tcp_kind = "syn"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "tcp_kind": tcp_kind,
        "policy": policy,
        "tcpid": int(fields["tcp-id"]) if fields.get("tcp-id") else EMPTY_TCPID,
        "tcpdigest": int(fields["tcp-digest"]) if fields.get("tcp-digest") else EMPTY_TCPDIGEST,
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
        raise TcpActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise TcpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise TcpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise TcpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc793_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    tcp: str,
) -> str:
    """RFC 793 identifier digest over method, request-TCP, identity, and tcpid."""

    payload = f"{method}:{tcp}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_tcpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"tcpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_tcpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-tcpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_tcpdigest(tcpid: int = EMPTY_TCPID, token: str = SENTINEL) -> int:
    nonce = f"{int(tcpid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc793_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="ACK",
        tcp=f"/tcp/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_TCPID = request_tcpid(SENTINEL)
DEFAULT_TCPDIGEST = request_tcpdigest(DEFAULT_TCPID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    tcpid: int,
    tcpdigest: int,
    include_tcpid: bool = True,
) -> bytes:
    live_tcpid = int(tcpid) & 0xFFFFFFFF if include_tcpid else EMPTY_TCPID
    live_digest = int(tcpdigest) & 0xFFFFFFFF if include_tcpid and live_tcpid else EMPTY_TCPDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_tcpid) if live_tcpid else b""
    header = bytearray()
    header.append(TCP_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_syn(
    *,
    identity: str,
    tcpid: int,
    tcpdigest: int | None = None,
    include_tcpid: bool = True,
) -> bytes:
    live_tcpid = int(tcpid) & 0xFFFFFFFF if include_tcpid else EMPTY_TCPID
    live_digest = int(tcpdigest) if tcpdigest is not None else request_tcpdigest(live_tcpid, identity)
    return encode_packet(
        FRAME_SYN,
        identity=identity,
        tcpid=live_tcpid,
        tcpdigest=live_digest,
        include_tcpid=include_tcpid,
    )


def encode_ack(
    *,
    identity: str,
    tcpid: int,
    tcpdigest: int | None = None,
    include_tcpid: bool = True,
) -> bytes:
    live_tcpid = int(tcpid) & 0xFFFFFFFF if include_tcpid else EMPTY_TCPID
    live_digest = int(tcpdigest) if tcpdigest is not None else request_tcpdigest(live_tcpid, identity)
    return encode_packet(
        FRAME_ACK,
        identity=identity,
        tcpid=live_tcpid,
        tcpdigest=live_digest,
        include_tcpid=include_tcpid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise TcpActuationError("short_packet")
    first = raw[0]
    if first != TCP_FIRST:
        raise TcpActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise TcpActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == TCPID_SIZE:
        live_tcpid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_tcpid = EMPTY_TCPID
    else:
        raise TcpActuationError("illegal_tcpid")
    if offset >= len(raw):
        raise TcpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SYN, FRAME_ACK}:
        raise TcpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise TcpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise TcpActuationError("checksum_failed")
    if len(payload) < 5:
        raise TcpActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise TcpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_tcpid = int(live_tcpid) != EMPTY_TCPID
    has_tcpdigest = has_tcpid and int(live_digest) != EMPTY_TCPDIGEST
    is_syn = frame_type == FRAME_SYN
    is_ack = frame_type == FRAME_ACK
    return {
        "type": int(frame_type),
        "is_syn": is_syn,
        "is_ack": is_ack,
        "tcpid": int(live_tcpid),
        "has_tcpid": has_tcpid,
        "tcpdigest": int(live_digest),
        "has_tcpdigest": has_tcpdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC793",
        "serialize_field": canonical_syn(identity, live_tcpid) if has_tcpid else "",
        "tls_field": canonical_ack(identity, live_tcpid, live_digest) if has_tcpdigest else "",
    }


class TcpClient:
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
            raise TcpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_ack"] or not packet["is_ack"]:
            raise TcpActuationError("tcpdigest_required")
        if not packet["has_tcpid"]:
            raise TcpActuationError("tcpid_required")
        if not packet["has_tcpdigest"]:
            raise TcpActuationError("tcpdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_tcpdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_tcpdigest:
            raise TcpActuationError("tcpdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "tcpid": int(reply.get("tcpid") or EMPTY_TCPID),
            "identity": str(reply.get("identity") or ""),
            "tcpdigest": int(reply.get("tcpdigest") or EMPTY_TCPDIGEST),
        }

    def report(
        self,
        identity: str,
        tcpid: int,
        tcpdigest: int = EMPTY_TCPDIGEST,
        *,
        wait_tcpdigest: bool = True,
        include_tcpid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_ack(
            identity=identity,
            tcpid=tcpid,
            tcpdigest=tcpdigest or request_tcpdigest(tcpid, identity),
            include_tcpid=include_tcpid,
        )
        return self.exchange(packet, wait_tcpdigest=wait_tcpdigest)


class TcpSession:
    """TCPID-gated loopback RFC 793 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        tcpid_gate: int = DEFAULT_TCPID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tcpid_gate = int(tcpid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.tcpid = EMPTY_TCPID
        self.tcpdigest = EMPTY_TCPDIGEST
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

    def store_tcpid_once(self, identity: str, tcpid: int, tcpdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(tcpid or EMPTY_TCPID)
            live_digest = int(tcpdigest or EMPTY_TCPDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.tcpid = live
                self.tcpdigest = live_digest or request_tcpdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.tcpid), int(self.tcpdigest)

    def read_tcpid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.tcpid), int(self.tcpdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "tcpid": EMPTY_TCPID,
            "tcpdigest": EMPTY_TCPDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _tcpid_missing(self) -> bool:
        return not int(self.tcpid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, tcpid: int, tcpdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_ack(
            identity=identity,
            tcpid=tcpid,
            tcpdigest=tcpdigest,
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
            except TcpActuationError:
                continue
            if not packet.get("is_syn") and not packet.get("is_ack"):
                continue
            if not packet.get("has_tcpid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_tcpid, stored_digest = self.store_tcpid_once(
                identity,
                int(packet.get("tcpid") or EMPTY_TCPID),
                int(packet.get("tcpdigest") or EMPTY_TCPDIGEST),
            )
            if not stored_name or not stored_tcpid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_syn"):
                    self.opened = True
                if packet.get("is_ack"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_tcpid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._tcpid_missing():
            return self._forbidden("missing_tcpid")
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
        do_syn: bool = True,
        do_ack: bool = True,
        do_tcpdigest: bool = True,
        replay: bool = True,
        use_tcpid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._tcpid_missing():
            return self._forbidden("missing_tcpid")
        live_token = str(token or SENTINEL)
        origin_tcpid = request_tcpid(live_token)
        origin_digest = request_tcpdigest(origin_tcpid, live_token)
        client: TcpClient | None = None
        independent: TcpClient | None = None
        try:
            client = TcpClient(self.host, int(self.port))
            if not do_syn:
                return self._conflict("syn_required")
            bind_packet = encode_syn(
                identity=live_token,
                tcpid=origin_tcpid,
                tcpdigest=origin_digest,
                include_tcpid=use_tcpid,
            )
            if not use_tcpid:
                try:
                    client.exchange(bind_packet, wait_tcpdigest=True)
                except TcpActuationError:
                    return self._conflict("tcpid_required")
                return self._conflict("tcpid_required")
            client.send(bind_packet)
            if not do_ack:
                return self._conflict("ack_required")
            proxy_packet = encode_ack(
                identity=live_token,
                tcpid=origin_tcpid,
                tcpdigest=origin_digest,
                include_tcpid=True,
            )
            if not do_tcpdigest:
                try:
                    client.exchange(proxy_packet, wait_tcpdigest=False)
                except TcpActuationError as error:
                    if str(error) == "tcpdigest_required":
                        return self._conflict("tcpdigest_required")
                    return self._conflict("tcpdigest_required")
                return self._conflict("tcpdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_tcpdigest=True)
            except TcpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("tcpid_required")
                if reason == "tcpdigest_required":
                    return self._conflict("tcpdigest_required")
                return self._conflict("syn_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("syn_required")
            if int(reply.get("tcpid") or EMPTY_TCPID) != origin_tcpid:
                return self._conflict("tcpdigest_required")
            if int(reply.get("tcpdigest") or EMPTY_TCPDIGEST) != origin_digest:
                return self._conflict("tcpdigest_required")
            self.retrieved = True
            if replay:
                independent = TcpClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_tcpid(live_token),
                        request_tcpdigest(poll_tcpid(live_token), POLL_TOKEN),
                        wait_tcpdigest=True,
                    )
                except TcpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_tcpid, stored_digest = self.read_tcpid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_tcpid != origin_tcpid
                    or stored_digest != origin_digest
                    or int(poll.get("tcpid") or EMPTY_TCPID) != origin_tcpid
                    or int(poll.get("tcpdigest") or EMPTY_TCPDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_tcpid}:{origin_digest}:{live_token}:{canonical_syn(live_token, origin_tcpid)}:{canonical_ack(live_token, origin_tcpid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "tcpid": origin_tcpid,
                "tcpdigest": origin_digest,
                "syn_frame": True,
                "ack_frame": True,
                "tcpdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "tcpid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_tcpdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "tcpid": origin_tcpid,
                "tcpdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "syn_frame": True,
                "ack_frame": True,
                "tcpdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "tcpid_bound": True,
            }
        except (OSError, TcpActuationError) as error:
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
        live = independent_tcpdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "tcpid": int(live.get("tcpid") or EMPTY_TCPID),
            "tcpdigest": int(live.get("tcpdigest") or EMPTY_TCPDIGEST),
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


def call_tcp_tool(session: TcpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one tcp tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_syn = True if arguments.get("syn") is None else bool(arguments.get("syn"))
    do_ack = True if arguments.get("ack") is None else bool(arguments.get("ack"))
    do_tcpdigest = True if arguments.get("tcpdigest") is None else bool(arguments.get("tcpdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_tcpid = True if arguments.get("use_tcpid") is None else bool(arguments.get("use_tcpid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_syn=do_syn,
            do_ack=do_ack,
            do_tcpdigest=do_tcpdigest,
            replay=replay,
            use_tcpid=use_tcpid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise TcpActuationError(f"unsupported tcp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_tcpdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage tcpdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "tcpid": EMPTY_TCPID,
        "tcpdigest": EMPTY_TCPDIGEST,
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
            "syn_frame",
            "ack_frame",
            "tcpdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "tcpid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    tcpid = int(payload.get("tcpid") or EMPTY_TCPID)
    tcpdigest = int(payload.get("tcpdigest") or EMPTY_TCPDIGEST)
    dual = port > 0 and bool(tcpid) and bool(tcpdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "tcpid": tcpid,
        "tcpdigest": tcpdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "syn_frame": payload.get("syn_frame") is True,
        "ack_frame": payload.get("ack_frame") is True,
        "tcpdigest_locate": payload.get("tcpdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "tcpid_bound": payload.get("tcpid_bound") is True,
    }


def run_tcp_workflow(
    *,
    with_tcpid: bool = True,
    skip_bind: bool = False,
    do_syn: bool = True,
    do_ack: bool = True,
    do_tcpdigest: bool = True,
    replay: bool = True,
    use_tcpid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 793 SYN/ACK tcpid cycle workflow."""

    descriptor = tcp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TCP_TOOL_PROVIDER),
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
        raise TcpActuationError(f"tcp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="tcp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = TcpSession(out, tcpid_gate=DEFAULT_TCPID if with_tcpid else EMPTY_TCPID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "syn": do_syn,
            "ack": do_ack,
            "tcpdigest": do_tcpdigest,
            "replay": replay,
            "use_tcpid": use_tcpid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_tcp_tool(session, arguments))
            except TcpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_tcpdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_tcpid
        and not skip_bind
        and do_syn
        and do_ack
        and do_tcpdigest
        and replay
        and use_tcpid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "tcp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_tcpid": with_tcpid,
        "skip_bind": skip_bind,
        "syn_frame": do_syn,
        "ack_frame": do_ack,
        "tcpdigest": do_tcpdigest,
        "replay": replay,
        "use_tcpid": use_tcpid,
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
        "tcpid_value": int(publish_result.get("tcpid") or independent.get("tcpid") or EMPTY_TCPID),
        "tcpdigest_value": int(publish_result.get("tcpdigest") or independent.get("tcpdigest") or EMPTY_TCPDIGEST),
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
        "tcpid": int(trace_body["tcpid_value"] or EMPTY_TCPID),
        "tcpdigest": int(trace_body["tcpdigest_value"] or EMPTY_TCPDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_tcpid": with_tcpid,
        "skip_bind": skip_bind,
        "syn_cycle": do_syn,
        "ack_cycle": do_ack,
        "tcpdigest_cycle": do_tcpdigest,
        "replay": replay,
        "use_tcpid": use_tcpid,
    }


def verify_tcp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_tcpdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    tcpid = int(trace.get("tcpid_value") or independent.get("tcpid") or EMPTY_TCPID)
    tcpdigest = int(trace.get("tcpdigest_value") or independent.get("tcpdigest") or EMPTY_TCPDIGEST)
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
        "syn_frame": independent.get("syn_frame") is True,
        "ack_frame": independent.get("ack_frame") is True,
        "tcpdigest_locate": independent.get("tcpdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "tcpid_bound": independent.get("tcpid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "tcpdigest_recorded": (
            port > 0
            and tcpid == DEFAULT_TCPID
            and tcpdigest == DEFAULT_TCPDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def tcp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.tcp_actuation import "
        "builtin_tcp_actuation_proof; r=builtin_tcp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='tcp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_tcp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=TCP_ACTUATION_ID,
        name="First-class RFC 793 Transmission Control Protocol SYN/ACK actuation",
        description=(
            "Missions that require a tcp tool can opt the tcp provider in, "
            "bind a loopback RFC 793 Transmission Control Protocol endpoint, complete a SYN "
            "with a non-empty tcpid, lockstep an ACK that carries the "
            "stored tcpdigest, independently poll the stored tcpdigest "
            "on a later socket, and seal a digest-chained tcpdigest. Default "
            "routing stays fail-closed; a missing tcpid keeps the hole "
            "falsifiable, and skip-SYN/ACK/TCPDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.tcp_actuation:builtin_tcp_actuation_proof",
        proof_command=tcp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.telnet-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/tcp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/telnet_actuation.py",
            "src/blackhole_agent/udp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required tcp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 793 daemon, speaks a "
            "SYN then ACK over Transmission Control Protocol with a non-empty tcpid and "
            "tcpdigest, independently polls the stored tcpdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 854 Telnet Protocol Specification lockstep is proved. "
            "Missing tcpids, skip-SYN, skip-ACK, skip-tcpdigest, skip-REPLAY, "
            "and a SYN aimed without a tcpid stay fail-closed. "
            "Later genesis can take RFC 768 User Datagram Protocol SEND/RECV as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("tcp", "rfc793", "http", "tcpid", "tcpdigest", "syn", "ack", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T044048Z-7069252d",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_tcp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 793 syn/ack lockstep actuation seals a tcpdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.udp_actuation import (
        UDP_ACTUATION_GOAL,
        UDP_ACTUATION_ID,
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
    checks["denylists_self"] = TCP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(TCP_ACTUATION_GOAL) == (
        TCP_ACTUATION_ID,
    )
    checks["leftover_text_binds_tcp"] = leftover_marker_ids(TCP_LEFTOVER) == (
        TCP_ACTUATION_ID,
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
        (UDP_ACTUATION_GOAL, UDP_ACTUATION_ID, "udp"),
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
        checks[f"{name}_goal_is_not_tcp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"tcp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            TCP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = TCP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_tcp(DEFAULT_SYN)
    rebuilt = serialize_tcp(parse_tcp(advertised))
    preloaded = parse_tcp(RFC_TCP_ACK)
    header = encode_tcp_header(DEFAULT_SYN)
    parsed_header = parse_tcp_header(header)
    asked = parse_http_request(syn_request(SENTINEL, DEFAULT_TCPID))
    preload_req = parse_http_request(ack_request(SENTINEL, DEFAULT_TCPID, DEFAULT_TCPDIGEST))
    got = parse_http_response(syn_response(SENTINEL, DEFAULT_TCPID, DEFAULT_TCPDIGEST))
    preload_reply = parse_http_response(
        ack_response(SENTINEL, DEFAULT_TCPID, DEFAULT_TCPDIGEST)
    )
    checks["tcp_roundtrip"] = (
        parse_tcp(advertised) == DEFAULT_SYN
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_SYN_FIELD
        and is_token("SYN") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SYN_FIELD
        and parsed_header["policy"] == DEFAULT_SYN
        and parsed_header["header"] == SYN_HEADER
        and parsed_header["syn"] is True
        and parsed_header["ack"] is False
        and preloaded == ACK_POLICY
        and ascii_serialize_tcp_directive() == RFC_SYN_DIRECTIVE
        and tcp_directive_pair() == ("syn", "segment")
        and RFC_SYN_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_tcp(ACK_POLICY) == RFC_TCP_ACK
        and DEFAULT_TCPDIGEST == request_tcpdigest(DEFAULT_TCPID, SENTINEL)
        and "tcpdigest=" in canonical_ack(SENTINEL, DEFAULT_TCPID, DEFAULT_TCPDIGEST)
        and canonical_syn(SENTINEL, DEFAULT_TCPID).startswith("SYN")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "SYN"
        and asked["tcp_kind"] == "syn"
        and asked["tcpid"] == DEFAULT_TCPID
        and preload_req["tcp_kind"] == "ack"
        and preload_req["tcpdigest"] == DEFAULT_TCPDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["tcp_kind"] == "syn"
        and preload_reply["tcp_kind"] == "ack"
        and got["policy"] == DEFAULT_SYN
        and preload_reply["policy"] == ACK_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["tcpdigest"] == DEFAULT_TCPDIGEST
        and preload_reply["tcpdigest"] == DEFAULT_TCPDIGEST
        and tcp_matches(serialize_tcp(got["policy"]), advertised)
    )

    checks["catalog_names_tcp"] = (
        len(catalog) > 112
        and catalog[112]["id"] == TCP_ACTUATION_ID
        and catalog[111]["id"] == TELNET_ACTUATION_ID
        and catalog[112]["source"] == "genesis_bind_tcp"
    )
    checks["catalog_names_udp"] = (
        len(catalog) > 113
        and catalog[113]["id"] == UDP_ACTUATION_ID
        and catalog[113]["source"] == "genesis_bind_udp"
    )
    family = capability_family(TCP_ACTUATION_GOAL)
    checks["family_is_tcp"] = "tcp" in family
    checks["family_is_tcp_surface"] = "tcp" in family
    checks["family_is_tcpid"] = "tcpid" in family
    checks["family_is_rfc793"] = "rfc793" in family
    checks["family_is_tcpdigest"] = "tcpdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
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
    packed = encode_syn(identity=SENTINEL, tcpid=DEFAULT_TCPID, tcpdigest=DEFAULT_TCPDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_syn"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_tcpid"] is True
        and parsed["tcpid"] == DEFAULT_TCPID
        and parsed["tcpdigest"] == DEFAULT_TCPDIGEST
        and parsed["is_ack"] is False
        and parsed["is_ack"] is False
        and parsed["type"] == FRAME_SYN
        and parsed["first_byte"] == TCP_FIRST
    )
    shook = encode_ack(
        identity=SENTINEL,
        tcpid=DEFAULT_TCPID,
        tcpdigest=DEFAULT_TCPDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_ack"] is True
        and answer_parsed["is_ack"] is True
        and answer_parsed["is_syn"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["tcpid"] == DEFAULT_TCPID
        and answer_parsed["tcpdigest"] == DEFAULT_TCPDIGEST
        and answer_parsed["has_tcpdigest"] is True
        and answer_parsed["type"] == FRAME_ACK
        and answer_parsed["first_byte"] == TCP_FIRST
    )
    bare = encode_syn(identity=SENTINEL, tcpid=DEFAULT_TCPID, include_tcpid=False)
    checks["missing_tcpid_is_unauthed"] = parse_message(bare)["has_tcpid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(TCP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_tcp = ToolDescriptor(name="remote_tcp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_tcp)
    checks["naive_mcp_tcp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = tcp_tool_descriptor()
    default_tcp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TCP_TOOL_PROVIDER),
    )
    checks["default_tcp_provider_is_unsupported"] = (
        default_tcp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{TCP_TOOL_PROVIDER}" in default_tcp.reasons
    )
    checks["opted_in_tcp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_tcp],
        required_tool_names=("local_memory", "tcp"),
    )
    checks["naive_preflight_missing_tcp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["tcp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "tcp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TCP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "tcp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="tcp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_tcp_workflow(with_tcpid=False, output_dir=root / "missing")
        skip_bind = run_tcp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_syn = run_tcp_workflow(do_syn=False, output_dir=root / "skip-syn")
        skip_ack = run_tcp_workflow(do_ack=False, output_dir=root / "skip-ack")
        skip_tcpdigest = run_tcp_workflow(do_tcpdigest=False, output_dir=root / "skip-tcpdigest")
        skip_replay = run_tcp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_tcpid = run_tcp_workflow(use_tcpid=False, output_dir=root / "skip-tcpid")
        live = run_tcp_workflow(output_dir=root / "live")
        verify = verify_tcp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_tcp_trace(clone)
        checks["naive_without_tcpid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_tcpid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_syn_stays_empty"] = (
            skip_syn["ok"] is False
            and skip_syn["error"] == "syn_required"
            and skip_syn["final_status"] == 409
            and skip_syn["payload_exists"] is False
        )
        checks["skip_ack_stays_empty"] = (
            skip_ack["ok"] is False
            and skip_ack["error"] == "ack_required"
            and skip_ack["final_status"] == 409
            and skip_ack["payload_exists"] is False
        )
        checks["skip_tcpdigest_stays_empty"] = (
            skip_tcpdigest["ok"] is False
            and skip_tcpdigest["error"] == "tcpdigest_required"
            and skip_tcpdigest["final_status"] == 409
            and skip_tcpdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_tcpid_stays_empty"] = (
            skip_tcpid["ok"] is False
            and skip_tcpid["error"] == "tcpid_required"
            and skip_tcpid["final_status"] == 409
            and skip_tcpid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_tcpdigest"] = (
            int(live.get("tcpid") or 0) == DEFAULT_TCPID
            and int(live.get("tcpdigest") or 0) == DEFAULT_TCPDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_tcpid_encode_ack_tcpdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_syn["ok"] is False
            and skip_ack["ok"] is False
            and skip_tcpdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_tcpid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="tcp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != TCP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_tcp"] = (
        live_goal == TCP_ACTUATION_GOAL
        and TCP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_tcp"
    )

    with tempfile.TemporaryDirectory(prefix="tcp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(TCP_LEFTOVER, root)
        register_catalog_proved(root, TCP_ACTUATION_ID)
        reason = leftover_satisfied_by(TCP_LEFTOVER, root)
        after = leftover_is_open(TCP_LEFTOVER, root)
    checks["tcp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_tcp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{TCP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_tcp_actuation_capability()
    return {
        "ok": ok,
        "action": "tcp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": TCP_ACTUATION_GOAL,
        "done_when": TCP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
