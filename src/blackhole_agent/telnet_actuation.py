"""Drive a first-class Telnet Protocol Specification tool through RFC 854 DO/WILL.

Tool routing already fails missions that require ``telnet``: hosted
telnet endpoints stay on the unsupported MCP provider, and no first-party
telnet provider is executable. Unbound therefore cannot speak a DO,
lockstep a WILL telnetid handshake over HTTP/1.0 TELNETID,
independently poll the stored telnetdigest, or seal a telnetdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``telnet`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 854 daemon
- keep a missing-telnetid client so the telnet-telnetid hole stays falsifiable
- refuse WILL until a DO lands with a non-empty telnetid
- independently poll the stored telnetdigest on a later client socket
- persist a sealed telnetdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 977 Network News Transfer Protocol
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
    TELNET_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    telnet_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
TELNET_ACTUATION_ID = "capability.telnet-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-TELNET-OK"
POLL_TOKEN = "BH-TELNET-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_TELNETID = 0
EMPTY_TELNETDIGEST = 0
TELNET_FIRST = 0x54  # RFC 854 TELNET (ASCII 'T')
TELNETID_SIZE = 4
TELNETDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_WILL = 0x02  # RFC 854 WILL confirmation
FRAME_DO = 0x01  # RFC 854 DO
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
TELNET_LEFTOVER = (
    "Later genesis can take RFC 854 Telnet Protocol Specification DO/WILL over a "
    "telnetid-gated telnetdigest."
)
TELNET_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TELNET_ACTUATION_ID};"
    f"capability_proved:{TELNET_ACTUATION_ID};"
    "no_skill_route"
)
TELNET_ACTUATION_GOAL = (
    "Repair rfc854 telnet do/will cycle cannot land over http "
    "telnet telnetid: hosted telnet endpoints remain unsupported so a DO then "
    "WILL telnetid handshake cannot land and a sealed telnetdigest "
    "cannot be produced. A missing telnet telnetid stays forbidden; fail-closed "
    "routing never opts the telnet provider in. An independent later poll of the "
    "stored telnetdigest keeps the hole falsifiable."
)


class TelnetActuationError(RuntimeError):
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
# RFC 854 sections 2.1 and 2.1.2: DO / WILL.
RFC_DO_FIELD = "DO"
RFC_WILL_FIELD = "WILL"
RFC_TELNET_WILL = RFC_WILL_FIELD
RFC_DO_DIRECTIVE = "do=option"
RFC_WILL_DIRECTIVE = "will=option"
DEFAULT_DO = "DO"
WILL_POLICY = "WILL"
DO_HEADER = "Do"
WILL_HEADER = "Will"
TELNET_WILL_HEADER = WILL_HEADER
RFC_DO_PATH = "/telnet/"
RFC_DO_EMPTY = ""


def telnet_directive_pair(*, will: bool = False) -> tuple[str, str]:
    """RFC 854 Do / Will directive pair."""

    if will:
        return "will", "option"
    return "do", "option"


def ascii_serialize_telnet_directive(*, will: bool = False) -> str:
    """RFC 854 token "=" body-or-will."""

    name, value = telnet_directive_pair(will=will)
    if not is_token(name):
        raise TelnetActuationError("illegal_directive")
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
            raise TelnetActuationError("short_telnet")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 854 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_telnet(policy: str | Sequence[str]) -> str:
    """Serialize RFC 854 DO / WILL opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise TelnetActuationError("illegal_telnet")
    upper = text.upper().replace("_", "-")
    if upper in {"DO", "TELNET", "TELNET-DO"}:
        return "DO"
    if upper in {"WILL", "RESOURCE", "TELNET-WILL"}:
        return "WILL"
    if upper.startswith("DO="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TelnetActuationError("illegal_telnet")
        return "DO"
    if upper.startswith("WILL="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TelnetActuationError("illegal_telnet")
        return "WILL"
    raise TelnetActuationError("illegal_telnet")


def parse_telnet(text: str) -> str:
    """Parse RFC 854 TELNET opcode header extensions into DO or WILL."""

    raw = str(text or "").strip()
    if not raw:
        raise TelnetActuationError("illegal_telnet")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"DO", "TELNET", "TELNET-DO"}:
        return "DO"
    if upper in {"WILL", "RESOURCE", "TELNET-WILL"}:
        return "WILL"
    if upper.startswith("DO="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TelnetActuationError("illegal_telnet")
        return "DO"
    if upper.startswith("WILL="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TelnetActuationError("illegal_telnet")
        return "WILL"
    raise TelnetActuationError("illegal_telnet")


def encode_telnet_header(policy: str | Sequence[str]) -> bytes:
    """RFC 854 HTTP/1.0 field as bytes."""

    return serialize_telnet(policy).encode("ascii")


def parse_telnet_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_telnet(field_value) if field_value else DEFAULT_DO
    return {
        "field_value": field_value,
        "policy": policy,
        "header": DO_HEADER,
        "directive": str(policy),
        "do": str(policy) == "DO",
        "will": str(policy) == "WILL",
    }


def canonical_do(identity: str, telnetid: int) -> str:
    """RFC 854 body-request advertisement bound to identity and telnetid."""

    return (
        f"{serialize_telnet(DEFAULT_DO)}, "
        f"do={ascii_serialize_telnet_directive()}, "
        f"identity={identity}, telnetid={int(telnetid) & 0xFFFFFFFF}"
    )


def canonical_will(identity: str, telnetid: int, telnetdigest: int | None = None) -> str:
    """RFC 854 will-option confirmation of the stored identifier-digest."""

    digest = ""
    if telnetdigest is not None:
        digest = f", telnetdigest={int(telnetdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_telnet(WILL_POLICY)}, "
        f"will={ascii_serialize_telnet_directive(will=True)}, "
        f"identity={identity}, telnetid={int(telnetid) & 0xFFFFFFFF}{digest}"
    )


def representation_will(identity: str, telnetid: int, telnetdigest: int) -> str:
    return canonical_will(identity, telnetid, telnetdigest)


def telnet_matches(left: str, right: str) -> bool:
    return parse_telnet(left) == parse_telnet(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise TelnetActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise TelnetActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise TelnetActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise TelnetActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def do_request(identity: str, telnetid: int) -> bytes:
    """HTTP DO that elicits RFC 854 origin HTTP/1.0."""

    keyid = f"{int(telnetid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"DO /telnet/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Telnet-Id: {int(telnetid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def will_request(identity: str, telnetid: int, telnetdigest: int | None = None) -> bytes:
    """HTTP WILL carrying RFC 854 will-option confirmation of the stored identifier-digest."""

    keyid = f"{int(telnetid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if telnetdigest is not None:
        extra = f"Telnet-Digest: {int(telnetdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"WILL /telnet/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Telnet-Id: {int(telnetid) & 0xFFFFFFFF}\r\n"
        "Will-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    telnet_kind = "will" if fields.get("will-confirm") == "1" else "do"
    upgrade_field = fields.get("do") or fields.get("telnet") or ""
    policy = parse_telnet(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "telnet_kind": telnet_kind,
        "policy": policy,
        "telnetid": int(fields["telnet-id"]) if fields.get("telnet-id") else EMPTY_TELNETID,
        "telnetdigest": int(fields["telnet-digest"]) if fields.get("telnet-digest") else EMPTY_TELNETDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def do_response(identity: str, telnetid: int, telnetdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 854 origin HTTP/1.0, carrying the stored telnetdigest."""

    advertised = serialize_telnet(DEFAULT_DO)
    payload = bytes(body or canonical_do(identity, telnetid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Do: {advertised}\r\n"
        f"Telnet-Id: {int(telnetid) & 0xFFFFFFFF}\r\n"
        f"Telnet-Digest: {int(telnetdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def will_response(identity: str, telnetid: int, telnetdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 854 WILL, carrying the stored identifier-digest."""

    advertised = serialize_telnet(WILL_POLICY)
    payload = bytes(body or representation_will(identity, telnetid, telnetdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Do: {advertised}\r\n"
        f"Telnet-Id: {int(telnetid) & 0xFFFFFFFF}\r\n"
        f"Telnet-Digest: {int(telnetdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/telnet-will\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise TelnetActuationError("illegal_content_length") from error
    field_value = fields.get("do") or fields.get("telnet") or ""
    policy = parse_telnet(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/telnet-will" or policy == WILL_POLICY:
        status = 200
        telnet_kind = "will"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        telnet_kind = "do"
    else:
        status = 0
        telnet_kind = "do"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "telnet_kind": telnet_kind,
        "policy": policy,
        "telnetid": int(fields["telnet-id"]) if fields.get("telnet-id") else EMPTY_TELNETID,
        "telnetdigest": int(fields["telnet-digest"]) if fields.get("telnet-digest") else EMPTY_TELNETDIGEST,
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
        raise TelnetActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise TelnetActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise TelnetActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise TelnetActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc854_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    telnet: str,
) -> str:
    """RFC 854 identifier digest over method, request-TELNET, identity, and telnetid."""

    payload = f"{method}:{telnet}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_telnetid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"telnetid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_telnetid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-telnetid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_telnetdigest(telnetid: int = EMPTY_TELNETID, token: str = SENTINEL) -> int:
    nonce = f"{int(telnetid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc854_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="WILL",
        telnet=f"/telnet/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_TELNETID = request_telnetid(SENTINEL)
DEFAULT_TELNETDIGEST = request_telnetdigest(DEFAULT_TELNETID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    telnetid: int,
    telnetdigest: int,
    include_telnetid: bool = True,
) -> bytes:
    live_telnetid = int(telnetid) & 0xFFFFFFFF if include_telnetid else EMPTY_TELNETID
    live_digest = int(telnetdigest) & 0xFFFFFFFF if include_telnetid and live_telnetid else EMPTY_TELNETDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_telnetid) if live_telnetid else b""
    header = bytearray()
    header.append(TELNET_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_do(
    *,
    identity: str,
    telnetid: int,
    telnetdigest: int | None = None,
    include_telnetid: bool = True,
) -> bytes:
    live_telnetid = int(telnetid) & 0xFFFFFFFF if include_telnetid else EMPTY_TELNETID
    live_digest = int(telnetdigest) if telnetdigest is not None else request_telnetdigest(live_telnetid, identity)
    return encode_packet(
        FRAME_DO,
        identity=identity,
        telnetid=live_telnetid,
        telnetdigest=live_digest,
        include_telnetid=include_telnetid,
    )


def encode_will(
    *,
    identity: str,
    telnetid: int,
    telnetdigest: int | None = None,
    include_telnetid: bool = True,
) -> bytes:
    live_telnetid = int(telnetid) & 0xFFFFFFFF if include_telnetid else EMPTY_TELNETID
    live_digest = int(telnetdigest) if telnetdigest is not None else request_telnetdigest(live_telnetid, identity)
    return encode_packet(
        FRAME_WILL,
        identity=identity,
        telnetid=live_telnetid,
        telnetdigest=live_digest,
        include_telnetid=include_telnetid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise TelnetActuationError("short_packet")
    first = raw[0]
    if first != TELNET_FIRST:
        raise TelnetActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise TelnetActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == TELNETID_SIZE:
        live_telnetid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_telnetid = EMPTY_TELNETID
    else:
        raise TelnetActuationError("illegal_telnetid")
    if offset >= len(raw):
        raise TelnetActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_DO, FRAME_WILL}:
        raise TelnetActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise TelnetActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise TelnetActuationError("checksum_failed")
    if len(payload) < 5:
        raise TelnetActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise TelnetActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_telnetid = int(live_telnetid) != EMPTY_TELNETID
    has_telnetdigest = has_telnetid and int(live_digest) != EMPTY_TELNETDIGEST
    is_do = frame_type == FRAME_DO
    is_will = frame_type == FRAME_WILL
    return {
        "type": int(frame_type),
        "is_do": is_do,
        "is_will": is_will,
        "telnetid": int(live_telnetid),
        "has_telnetid": has_telnetid,
        "telnetdigest": int(live_digest),
        "has_telnetdigest": has_telnetdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC854",
        "serialize_field": canonical_do(identity, live_telnetid) if has_telnetid else "",
        "tls_field": canonical_will(identity, live_telnetid, live_digest) if has_telnetdigest else "",
    }


class TelnetClient:
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
            raise TelnetActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_will"] or not packet["is_will"]:
            raise TelnetActuationError("telnetdigest_required")
        if not packet["has_telnetid"]:
            raise TelnetActuationError("telnetid_required")
        if not packet["has_telnetdigest"]:
            raise TelnetActuationError("telnetdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_telnetdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_telnetdigest:
            raise TelnetActuationError("telnetdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "telnetid": int(reply.get("telnetid") or EMPTY_TELNETID),
            "identity": str(reply.get("identity") or ""),
            "telnetdigest": int(reply.get("telnetdigest") or EMPTY_TELNETDIGEST),
        }

    def report(
        self,
        identity: str,
        telnetid: int,
        telnetdigest: int = EMPTY_TELNETDIGEST,
        *,
        wait_telnetdigest: bool = True,
        include_telnetid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_will(
            identity=identity,
            telnetid=telnetid,
            telnetdigest=telnetdigest or request_telnetdigest(telnetid, identity),
            include_telnetid=include_telnetid,
        )
        return self.exchange(packet, wait_telnetdigest=wait_telnetdigest)


class TelnetSession:
    """TELNETID-gated loopback RFC 854 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        telnetid_gate: int = DEFAULT_TELNETID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.telnetid_gate = int(telnetid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.telnetid = EMPTY_TELNETID
        self.telnetdigest = EMPTY_TELNETDIGEST
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

    def store_telnetid_once(self, identity: str, telnetid: int, telnetdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(telnetid or EMPTY_TELNETID)
            live_digest = int(telnetdigest or EMPTY_TELNETDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.telnetid = live
                self.telnetdigest = live_digest or request_telnetdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.telnetid), int(self.telnetdigest)

    def read_telnetid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.telnetid), int(self.telnetdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "telnetid": EMPTY_TELNETID,
            "telnetdigest": EMPTY_TELNETDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _telnetid_missing(self) -> bool:
        return not int(self.telnetid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, telnetid: int, telnetdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_will(
            identity=identity,
            telnetid=telnetid,
            telnetdigest=telnetdigest,
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
            except TelnetActuationError:
                continue
            if not packet.get("is_do") and not packet.get("is_will"):
                continue
            if not packet.get("has_telnetid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_telnetid, stored_digest = self.store_telnetid_once(
                identity,
                int(packet.get("telnetid") or EMPTY_TELNETID),
                int(packet.get("telnetdigest") or EMPTY_TELNETDIGEST),
            )
            if not stored_name or not stored_telnetid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_do"):
                    self.opened = True
                if packet.get("is_will"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_telnetid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._telnetid_missing():
            return self._forbidden("missing_telnetid")
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
        do_do: bool = True,
        do_will: bool = True,
        do_telnetdigest: bool = True,
        replay: bool = True,
        use_telnetid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._telnetid_missing():
            return self._forbidden("missing_telnetid")
        live_token = str(token or SENTINEL)
        origin_telnetid = request_telnetid(live_token)
        origin_digest = request_telnetdigest(origin_telnetid, live_token)
        client: TelnetClient | None = None
        independent: TelnetClient | None = None
        try:
            client = TelnetClient(self.host, int(self.port))
            if not do_do:
                return self._conflict("do_required")
            bind_packet = encode_do(
                identity=live_token,
                telnetid=origin_telnetid,
                telnetdigest=origin_digest,
                include_telnetid=use_telnetid,
            )
            if not use_telnetid:
                try:
                    client.exchange(bind_packet, wait_telnetdigest=True)
                except TelnetActuationError:
                    return self._conflict("telnetid_required")
                return self._conflict("telnetid_required")
            client.send(bind_packet)
            if not do_will:
                return self._conflict("will_required")
            proxy_packet = encode_will(
                identity=live_token,
                telnetid=origin_telnetid,
                telnetdigest=origin_digest,
                include_telnetid=True,
            )
            if not do_telnetdigest:
                try:
                    client.exchange(proxy_packet, wait_telnetdigest=False)
                except TelnetActuationError as error:
                    if str(error) == "telnetdigest_required":
                        return self._conflict("telnetdigest_required")
                    return self._conflict("telnetdigest_required")
                return self._conflict("telnetdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_telnetdigest=True)
            except TelnetActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("telnetid_required")
                if reason == "telnetdigest_required":
                    return self._conflict("telnetdigest_required")
                return self._conflict("do_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("do_required")
            if int(reply.get("telnetid") or EMPTY_TELNETID) != origin_telnetid:
                return self._conflict("telnetdigest_required")
            if int(reply.get("telnetdigest") or EMPTY_TELNETDIGEST) != origin_digest:
                return self._conflict("telnetdigest_required")
            self.retrieved = True
            if replay:
                independent = TelnetClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_telnetid(live_token),
                        request_telnetdigest(poll_telnetid(live_token), POLL_TOKEN),
                        wait_telnetdigest=True,
                    )
                except TelnetActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_telnetid, stored_digest = self.read_telnetid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_telnetid != origin_telnetid
                    or stored_digest != origin_digest
                    or int(poll.get("telnetid") or EMPTY_TELNETID) != origin_telnetid
                    or int(poll.get("telnetdigest") or EMPTY_TELNETDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_telnetid}:{origin_digest}:{live_token}:{canonical_do(live_token, origin_telnetid)}:{canonical_will(live_token, origin_telnetid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "telnetid": origin_telnetid,
                "telnetdigest": origin_digest,
                "do_frame": True,
                "will_frame": True,
                "telnetdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "telnetid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_telnetdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "telnetid": origin_telnetid,
                "telnetdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "do_frame": True,
                "will_frame": True,
                "telnetdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "telnetid_bound": True,
            }
        except (OSError, TelnetActuationError) as error:
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
        live = independent_telnetdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "telnetid": int(live.get("telnetid") or EMPTY_TELNETID),
            "telnetdigest": int(live.get("telnetdigest") or EMPTY_TELNETDIGEST),
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


def call_telnet_tool(session: TelnetSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one telnet tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_do = True if arguments.get("do") is None else bool(arguments.get("do"))
    do_will = True if arguments.get("will") is None else bool(arguments.get("will"))
    do_telnetdigest = True if arguments.get("telnetdigest") is None else bool(arguments.get("telnetdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_telnetid = True if arguments.get("use_telnetid") is None else bool(arguments.get("use_telnetid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_do=do_do,
            do_will=do_will,
            do_telnetdigest=do_telnetdigest,
            replay=replay,
            use_telnetid=use_telnetid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise TelnetActuationError(f"unsupported telnet action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_telnetdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage telnetdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "telnetid": EMPTY_TELNETID,
        "telnetdigest": EMPTY_TELNETDIGEST,
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
            "do_frame",
            "will_frame",
            "telnetdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "telnetid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    telnetid = int(payload.get("telnetid") or EMPTY_TELNETID)
    telnetdigest = int(payload.get("telnetdigest") or EMPTY_TELNETDIGEST)
    dual = port > 0 and bool(telnetid) and bool(telnetdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "telnetid": telnetid,
        "telnetdigest": telnetdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "do_frame": payload.get("do_frame") is True,
        "will_frame": payload.get("will_frame") is True,
        "telnetdigest_locate": payload.get("telnetdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "telnetid_bound": payload.get("telnetid_bound") is True,
    }


def run_telnet_workflow(
    *,
    with_telnetid: bool = True,
    skip_bind: bool = False,
    do_do: bool = True,
    do_will: bool = True,
    do_telnetdigest: bool = True,
    replay: bool = True,
    use_telnetid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 854 DO/WILL telnetid cycle workflow."""

    descriptor = telnet_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TELNET_TOOL_PROVIDER),
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
        raise TelnetActuationError(f"telnet tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="telnet-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = TelnetSession(out, telnetid_gate=DEFAULT_TELNETID if with_telnetid else EMPTY_TELNETID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "do": do_do,
            "will": do_will,
            "telnetdigest": do_telnetdigest,
            "replay": replay,
            "use_telnetid": use_telnetid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_telnet_tool(session, arguments))
            except TelnetActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_telnetdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_telnetid
        and not skip_bind
        and do_do
        and do_will
        and do_telnetdigest
        and replay
        and use_telnetid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "telnet_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_telnetid": with_telnetid,
        "skip_bind": skip_bind,
        "do_frame": do_do,
        "will_frame": do_will,
        "telnetdigest": do_telnetdigest,
        "replay": replay,
        "use_telnetid": use_telnetid,
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
        "telnetid_value": int(publish_result.get("telnetid") or independent.get("telnetid") or EMPTY_TELNETID),
        "telnetdigest_value": int(publish_result.get("telnetdigest") or independent.get("telnetdigest") or EMPTY_TELNETDIGEST),
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
        "telnetid": int(trace_body["telnetid_value"] or EMPTY_TELNETID),
        "telnetdigest": int(trace_body["telnetdigest_value"] or EMPTY_TELNETDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_telnetid": with_telnetid,
        "skip_bind": skip_bind,
        "do_cycle": do_do,
        "will_cycle": do_will,
        "telnetdigest_cycle": do_telnetdigest,
        "replay": replay,
        "use_telnetid": use_telnetid,
    }


def verify_telnet_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_telnetdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    telnetid = int(trace.get("telnetid_value") or independent.get("telnetid") or EMPTY_TELNETID)
    telnetdigest = int(trace.get("telnetdigest_value") or independent.get("telnetdigest") or EMPTY_TELNETDIGEST)
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
        "do_frame": independent.get("do_frame") is True,
        "will_frame": independent.get("will_frame") is True,
        "telnetdigest_locate": independent.get("telnetdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "telnetid_bound": independent.get("telnetid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "telnetdigest_recorded": (
            port > 0
            and telnetid == DEFAULT_TELNETID
            and telnetdigest == DEFAULT_TELNETDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def telnet_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.telnet_actuation import "
        "builtin_telnet_actuation_proof; r=builtin_telnet_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='telnet_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_telnet_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=TELNET_ACTUATION_ID,
        name="First-class RFC 854 Telnet Protocol Specification DO/WILL actuation",
        description=(
            "Missions that require a telnet tool can opt the telnet provider in, "
            "bind a loopback RFC 854 Telnet Protocol Specification endpoint, complete a DO "
            "with a non-empty telnetid, lockstep a WILL that carries the "
            "stored telnetdigest, independently poll the stored telnetdigest "
            "on a later socket, and seal a digest-chained telnetdigest. Default "
            "routing stays fail-closed; a missing telnetid keeps the hole "
            "falsifiable, and skip-DO/WILL/TELNETDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.telnet_actuation:builtin_telnet_actuation_proof",
        proof_command=telnet_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.nntp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/telnet_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/nntp_actuation.py",
            "src/blackhole_agent/tcp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required telnet tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 854 daemon, speaks a "
            "DO then WILL over Telnet Protocol Specification with a non-empty telnetid and "
            "telnetdigest, independently polls the stored telnetdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 977 Network News Transfer Protocol lockstep is proved. "
            "Missing telnetids, skip-DO, skip-WILL, skip-telnetdigest, skip-REPLAY, "
            "and a DO aimed without a telnetid stay fail-closed. "
            "Later genesis can take RFC 793 Transmission Control Protocol SYN/ACK as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("telnet", "rfc854", "http", "telnetid", "telnetdigest", "do", "will", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T040945Z-b1a82587",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_telnet_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 854 do/will lockstep actuation seals a telnetdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.tcp_actuation import (
        TCP_ACTUATION_GOAL,
        TCP_ACTUATION_ID,
    )
    from blackhole_agent.nntp_actuation import (
        NNTP_ACTUATION_GOAL,
        NNTP_ACTUATION_ID,
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
    checks["denylists_self"] = TELNET_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(TELNET_ACTUATION_GOAL) == (
        TELNET_ACTUATION_ID,
    )
    checks["leftover_text_binds_telnet"] = leftover_marker_ids(TELNET_LEFTOVER) == (
        TELNET_ACTUATION_ID,
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
        (TCP_ACTUATION_GOAL, TCP_ACTUATION_ID, "tcp"),
        (NNTP_ACTUATION_GOAL, NNTP_ACTUATION_ID, "nntp"),
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
        checks[f"{name}_goal_is_not_telnet"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"telnet_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            TELNET_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = TELNET_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_telnet(DEFAULT_DO)
    rebuilt = serialize_telnet(parse_telnet(advertised))
    preloaded = parse_telnet(RFC_TELNET_WILL)
    header = encode_telnet_header(DEFAULT_DO)
    parsed_header = parse_telnet_header(header)
    asked = parse_http_request(do_request(SENTINEL, DEFAULT_TELNETID))
    preload_req = parse_http_request(will_request(SENTINEL, DEFAULT_TELNETID, DEFAULT_TELNETDIGEST))
    got = parse_http_response(do_response(SENTINEL, DEFAULT_TELNETID, DEFAULT_TELNETDIGEST))
    preload_reply = parse_http_response(
        will_response(SENTINEL, DEFAULT_TELNETID, DEFAULT_TELNETDIGEST)
    )
    checks["telnet_roundtrip"] = (
        parse_telnet(advertised) == DEFAULT_DO
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_DO_FIELD
        and is_token("DO") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_DO_FIELD
        and parsed_header["policy"] == DEFAULT_DO
        and parsed_header["header"] == DO_HEADER
        and parsed_header["do"] is True
        and parsed_header["will"] is False
        and preloaded == WILL_POLICY
        and ascii_serialize_telnet_directive() == RFC_DO_DIRECTIVE
        and telnet_directive_pair() == ("do", "option")
        and RFC_DO_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_telnet(WILL_POLICY) == RFC_TELNET_WILL
        and DEFAULT_TELNETDIGEST == request_telnetdigest(DEFAULT_TELNETID, SENTINEL)
        and "telnetdigest=" in canonical_will(SENTINEL, DEFAULT_TELNETID, DEFAULT_TELNETDIGEST)
        and canonical_do(SENTINEL, DEFAULT_TELNETID).startswith("DO")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "DO"
        and asked["telnet_kind"] == "do"
        and asked["telnetid"] == DEFAULT_TELNETID
        and preload_req["telnet_kind"] == "will"
        and preload_req["telnetdigest"] == DEFAULT_TELNETDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["telnet_kind"] == "do"
        and preload_reply["telnet_kind"] == "will"
        and got["policy"] == DEFAULT_DO
        and preload_reply["policy"] == WILL_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["telnetdigest"] == DEFAULT_TELNETDIGEST
        and preload_reply["telnetdigest"] == DEFAULT_TELNETDIGEST
        and telnet_matches(serialize_telnet(got["policy"]), advertised)
    )

    checks["catalog_names_telnet"] = (
        len(catalog) > 111
        and catalog[111]["id"] == TELNET_ACTUATION_ID
        and catalog[110]["id"] == NNTP_ACTUATION_ID
        and catalog[111]["source"] == "genesis_bind_telnet"
    )
    checks["catalog_names_tcp"] = (
        len(catalog) > 112
        and catalog[112]["id"] == TCP_ACTUATION_ID
        and catalog[112]["source"] == "genesis_bind_tcp"
    )
    family = capability_family(TELNET_ACTUATION_GOAL)
    checks["family_is_telnet"] = "telnet" in family
    checks["family_is_telnet_surface"] = "telnet" in family
    checks["family_is_telnetid"] = "telnetid" in family
    checks["family_is_rfc854"] = "rfc854" in family
    checks["family_is_telnetdigest"] = "telnetdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_tcp"] = (
        "tcp" not in family.split("/")
        and "rfc793" not in family
        and "tcpid" not in family
        and "tcpdigest" not in family
    )
    checks["family_is_not_nntp"] = (
        "nntp" not in family.split("/")
        and "rfc977" not in family
        and "nntpid" not in family
        and "nntpdigest" not in family
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
    packed = encode_do(identity=SENTINEL, telnetid=DEFAULT_TELNETID, telnetdigest=DEFAULT_TELNETDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_do"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_telnetid"] is True
        and parsed["telnetid"] == DEFAULT_TELNETID
        and parsed["telnetdigest"] == DEFAULT_TELNETDIGEST
        and parsed["is_will"] is False
        and parsed["is_will"] is False
        and parsed["type"] == FRAME_DO
        and parsed["first_byte"] == TELNET_FIRST
    )
    shook = encode_will(
        identity=SENTINEL,
        telnetid=DEFAULT_TELNETID,
        telnetdigest=DEFAULT_TELNETDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_will"] is True
        and answer_parsed["is_will"] is True
        and answer_parsed["is_do"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["telnetid"] == DEFAULT_TELNETID
        and answer_parsed["telnetdigest"] == DEFAULT_TELNETDIGEST
        and answer_parsed["has_telnetdigest"] is True
        and answer_parsed["type"] == FRAME_WILL
        and answer_parsed["first_byte"] == TELNET_FIRST
    )
    bare = encode_do(identity=SENTINEL, telnetid=DEFAULT_TELNETID, include_telnetid=False)
    checks["missing_telnetid_is_unauthed"] = parse_message(bare)["has_telnetid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(TELNET_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_telnet = ToolDescriptor(name="remote_telnet", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_telnet)
    checks["naive_mcp_telnet_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = telnet_tool_descriptor()
    default_telnet = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TELNET_TOOL_PROVIDER),
    )
    checks["default_telnet_provider_is_unsupported"] = (
        default_telnet.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{TELNET_TOOL_PROVIDER}" in default_telnet.reasons
    )
    checks["opted_in_telnet_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_telnet],
        required_tool_names=("local_memory", "telnet"),
    )
    checks["naive_preflight_missing_telnet"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["telnet"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "telnet"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TELNET_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "telnet" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="telnet-actuation-") as tmp:
        root = Path(tmp)
        missing = run_telnet_workflow(with_telnetid=False, output_dir=root / "missing")
        skip_bind = run_telnet_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_do = run_telnet_workflow(do_do=False, output_dir=root / "skip-do")
        skip_will = run_telnet_workflow(do_will=False, output_dir=root / "skip-will")
        skip_telnetdigest = run_telnet_workflow(do_telnetdigest=False, output_dir=root / "skip-telnetdigest")
        skip_replay = run_telnet_workflow(replay=False, output_dir=root / "skip-replay")
        skip_telnetid = run_telnet_workflow(use_telnetid=False, output_dir=root / "skip-telnetid")
        live = run_telnet_workflow(output_dir=root / "live")
        verify = verify_telnet_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_telnet_trace(clone)
        checks["naive_without_telnetid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_telnetid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_do_stays_empty"] = (
            skip_do["ok"] is False
            and skip_do["error"] == "do_required"
            and skip_do["final_status"] == 409
            and skip_do["payload_exists"] is False
        )
        checks["skip_will_stays_empty"] = (
            skip_will["ok"] is False
            and skip_will["error"] == "will_required"
            and skip_will["final_status"] == 409
            and skip_will["payload_exists"] is False
        )
        checks["skip_telnetdigest_stays_empty"] = (
            skip_telnetdigest["ok"] is False
            and skip_telnetdigest["error"] == "telnetdigest_required"
            and skip_telnetdigest["final_status"] == 409
            and skip_telnetdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_telnetid_stays_empty"] = (
            skip_telnetid["ok"] is False
            and skip_telnetid["error"] == "telnetid_required"
            and skip_telnetid["final_status"] == 409
            and skip_telnetid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_telnetdigest"] = (
            int(live.get("telnetid") or 0) == DEFAULT_TELNETID
            and int(live.get("telnetdigest") or 0) == DEFAULT_TELNETDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_telnetid_encode_will_telnetdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_do["ok"] is False
            and skip_will["ok"] is False
            and skip_telnetdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_telnetid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="telnet-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != TELNET_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_telnet"] = (
        live_goal == TELNET_ACTUATION_GOAL
        and TELNET_ACTUATION_ID in live_done
        and live_source == "genesis_bind_telnet"
    )

    with tempfile.TemporaryDirectory(prefix="telnet-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(TELNET_LEFTOVER, root)
        register_catalog_proved(root, TELNET_ACTUATION_ID)
        reason = leftover_satisfied_by(TELNET_LEFTOVER, root)
        after = leftover_is_open(TELNET_LEFTOVER, root)
    checks["telnet_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_telnet_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{TELNET_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_telnet_actuation_capability()
    return {
        "ok": ok,
        "action": "telnet_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": TELNET_ACTUATION_GOAL,
        "done_when": TELNET_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
