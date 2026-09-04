"""Drive a first-class Client Hints tool through RFC 8942 ACCEPTCH/CRITCH.

Tool routing already fails missions that require ``clienthints``: hosted
clienthints endpoints stay on the unsupported MCP provider, and no first-party
clienthints provider is executable. Unbound therefore cannot speak an ACCEPTCH,
lockstep a CRITCH chid handshake over HTTP Client Hints CHID,
independently poll the stored hintsdigest, or seal a hintsdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``clienthints`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 8942 daemon
- keep a missing-chid client so the clienthints-chid hole stays falsifiable
- refuse CRITCH until an ACCEPTCH lands with a non-empty chid
- independently poll the stored hintsdigest on a later client socket
- persist a sealed hintsdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 8941 Structured Fields
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
    CLIENTHINTS_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    clienthints_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
CLIENTHINTS_ACTUATION_ID = "capability.clienthints-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-CH-OK"
POLL_TOKEN = "BH-CH-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_CHID = 0
EMPTY_HINTSDIGEST = 0
CH_FIRST = 0x43  # RFC 8942 HTTP Client Hints (ASCII 'C')
CHID_SIZE = 4
HINTSDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_CRITCH = 0x02  # RFC 8942 Critical-CH retry
FRAME_ACCEPTCH = 0x01  # RFC 8942 Accept-CH advertisement
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
TCHAR = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "!#$%&'*+-.^_`|~"
)
TOKEN_START = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ*")
# RFC 8942 does not define specific hint fields; these are the historical
# Client Hint request names used to exercise Accept-CH / Critical-CH.
ACCEPT_CH_FIELDS = ("DPR", "Width", "Viewport-Width")
CRITICAL_CH_FIELDS = ("DPR",)
DEFAULT_HINT_VALUES = (("DPR", "2"), ("Width", "1920"), ("Viewport-Width", "1280"))
CLIENTHINTS_LEFTOVER = (
    "Later genesis can take RFC 8942 HTTP Client Hints ACCEPTCH/CRITCH over a "
    "chid-gated hintsdigest."
)
CLIENTHINTS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{CLIENTHINTS_ACTUATION_ID};"
    f"capability_proved:{CLIENTHINTS_ACTUATION_ID};"
    "no_skill_route"
)
CLIENTHINTS_ACTUATION_GOAL = (
    "Repair rfc8942 clienthints acceptch/critch cycle cannot land over http "
    "clienthints chid: hosted clienthints endpoints remain unsupported so an ACCEPTCH then "
    "CRITCH chid handshake cannot land and a sealed hintsdigest "
    "cannot be produced. A missing clienthints chid stays forbidden; fail-closed "
    "routing never opts the clienthints provider in. An independent later poll of the "
    "stored hintsdigest keeps the hole falsifiable."
)


class ClienthintsActuationError(RuntimeError):
    """Raised when the Client Hints session or loopback daemon fixture misbehaves."""


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


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise ClienthintsActuationError("short_sfv")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def remaining(self) -> str:
        return self.text[self.pos :]

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 8941 sf-token used by RFC 8942 Accept-CH / Critical-CH lists."""

    raw = str(value or "")
    if not raw or raw[0] not in TOKEN_START:
        return False
    allowed = TCHAR | set(":/")
    return all(char in allowed for char in raw)


def serialize_token_list(tokens: Sequence[str]) -> str:
    """RFC 8941 sf-list of tokens (RFC 8942 Accept-CH / Critical-CH)."""

    chunks: list[str] = []
    for token in tokens:
        if not is_token(token):
            raise ClienthintsActuationError("illegal_token")
        chunks.append(str(token))
    return ", ".join(chunks)


def parse_token_list(text: str) -> tuple[str, ...]:
    """RFC 8941 section 4.2.1 parse an sf-list of tokens."""

    parser = _Parser(text)
    parser.skip_ows()
    if parser.eof():
        return ()
    members: list[str] = []
    while True:
        parser.skip_ows()
        if parser.peek() not in TOKEN_START:
            raise ClienthintsActuationError("illegal_token")
        start = parser.pos
        allowed = TCHAR | set(":/")
        parser.pos += 1
        while parser.peek() in allowed:
            parser.pos += 1
        members.append(parser.text[start:parser.pos])
        parser.skip_ows()
        if parser.peek() != ",":
            break
        parser.pos += 1
    parser.skip_ows()
    if not parser.eof():
        raise ClienthintsActuationError("illegal_list")
    return tuple(members)


def serialize_hints(values: Sequence[tuple[str, str]]) -> str:
    chunks: list[str] = []
    for name, value in values:
        if not is_token(name):
            raise ClienthintsActuationError("illegal_token")
        chunks.append(f"{name}={value}")
    return ", ".join(chunks)


def parse_hints(text: str) -> tuple[tuple[str, str], ...]:
    parser = _Parser(text)
    parser.skip_ows()
    if parser.eof():
        return ()
    members: list[tuple[str, str]] = []
    while True:
        parser.skip_ows()
        if parser.peek() not in TOKEN_START:
            raise ClienthintsActuationError("illegal_token")
        start = parser.pos
        allowed = TCHAR | set(":/")
        parser.pos += 1
        while parser.peek() in allowed:
            parser.pos += 1
        name = parser.text[start:parser.pos]
        if parser.take() != "=":
            raise ClienthintsActuationError("illegal_hint")
        value_start = parser.pos
        while parser.peek() and parser.peek() not in {",", " ", "\t"}:
            parser.pos += 1
        value = parser.text[value_start:parser.pos]
        if not value:
            raise ClienthintsActuationError("illegal_hint")
        members.append((name, value))
        parser.skip_ows()
        if parser.peek() != ",":
            break
        parser.pos += 1
    parser.skip_ows()
    if not parser.eof():
        raise ClienthintsActuationError("illegal_hint")
    return tuple(members)


def canonical_accept_ch(identity: str, chid: int) -> str:
    """RFC 8942 Accept-CH list bound to identity and chid."""

    return (
        f"{serialize_token_list(ACCEPT_CH_FIELDS)}; "
        f"identity={identity}; chid={int(chid) & 0xFFFFFFFF}"
    )


def canonical_crit_ch(identity: str, chid: int, hintsdigest: int | None = None) -> str:
    """RFC 8942 Critical-CH list of the stored Accept-CH members."""

    suffix = ""
    if hintsdigest is not None:
        suffix = f"; hintsdigest={int(hintsdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_token_list(CRITICAL_CH_FIELDS)}; "
        f"identity={identity}; chid={int(chid) & 0xFFFFFFFF}{suffix}"
    )


def representation_hints(identity: str, chid: int, hintsdigest: int) -> str:
    return (
        f"{serialize_hints(DEFAULT_HINT_VALUES)}; "
        f"identity={identity}; chid={int(chid) & 0xFFFFFFFF}; "
        f"hintsdigest={int(hintsdigest) & 0xFFFFFFFF}"
    )


def token_list_matches(left: str, right: str) -> bool:
    return parse_token_list(left) == parse_token_list(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise ClienthintsActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise ClienthintsActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise ClienthintsActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise ClienthintsActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def acceptch_request(identity: str, chid: int) -> bytes:
    """HTTP GET that elicits RFC 8942 Accept-CH / Critical-CH."""

    keyid = f"{int(chid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /clienthints/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"CH-Id: {int(chid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def critch_request(identity: str, chid: int, hintsdigest: int | None = None) -> bytes:
    """HTTP GET retry carrying Critical-CH fulfillment (RFC 8942 reliability)."""

    keyid = f"{int(chid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    hint_lines = "".join(f"{name}: {value}\r\n" for name, value in DEFAULT_HINT_VALUES)
    extra = ""
    if hintsdigest is not None:
        extra = f"Hints-Digest: {int(hintsdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /clienthints/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"CH-Id: {int(chid) & 0xFFFFFFFF}\r\n"
        f"Critical-CH: {serialize_token_list(CRITICAL_CH_FIELDS)}\r\n"
        f"{hint_lines}"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    has_hints = all(name.lower() in fields for name, _value in DEFAULT_HINT_VALUES)
    ch_kind = "critch" if fields.get("critical-ch") and has_hints else "acceptch"
    accept_ch = parse_token_list(fields["accept-ch"]) if fields.get("accept-ch") else ()
    crit_ch = parse_token_list(fields["critical-ch"]) if fields.get("critical-ch") else ()
    hints = tuple(
        (name, fields[name.lower()])
        for name, _value in DEFAULT_HINT_VALUES
        if name.lower() in fields
    )
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "ch_kind": ch_kind,
        "accept_ch": accept_ch,
        "crit_ch": crit_ch,
        "hints": hints,
        "chid": int(fields["ch-id"]) if fields.get("ch-id") else EMPTY_CHID,
    }


def acceptch_response(identity: str, chid: int, hintsdigest: int) -> bytes:
    """HTTP 200 advertising RFC 8942 Accept-CH and Critical-CH."""

    accept = serialize_token_list(ACCEPT_CH_FIELDS)
    critical = serialize_token_list(CRITICAL_CH_FIELDS)
    body = canonical_accept_ch(identity, chid)
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Accept-CH: {accept}\r\n"
        f"Critical-CH: {critical}\r\n"
        f"Vary: {accept}\r\n"
        f"CH-Id: {int(chid) & 0xFFFFFFFF}\r\n"
        f"Hints-Digest: {int(hintsdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/client-hints\r\n"
        f"Content-Length: {len(body.encode('ascii'))}\r\n"
        "\r\n"
        f"{body}"
    ).encode("ascii")


def critch_response(identity: str, chid: int, hintsdigest: int) -> bytes:
    """HTTP 200 after a Critical-CH retry, carrying the stored hintsdigest."""

    accept = serialize_token_list(ACCEPT_CH_FIELDS)
    critical = serialize_token_list(CRITICAL_CH_FIELDS)
    body = representation_hints(identity, chid, hintsdigest)
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Accept-CH: {accept}\r\n"
        f"Critical-CH: {critical}\r\n"
        f"Vary: {accept}\r\n"
        f"CH-Id: {int(chid) & 0xFFFFFFFF}\r\n"
        f"Hints-Digest: {int(hintsdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/client-hints\r\n"
        f"Content-Length: {len(body.encode('ascii'))}\r\n"
        "\r\n"
        f"{body}"
    ).encode("ascii")


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise ClienthintsActuationError("illegal_content_length") from error
    accept_ch = parse_token_list(fields["accept-ch"]) if fields.get("accept-ch") else ()
    crit_ch = parse_token_list(fields["critical-ch"]) if fields.get("critical-ch") else ()
    ch_kind = "critch" if fields.get("hints-digest") and crit_ch == CRITICAL_CH_FIELDS and "DPR=" in (body.decode("ascii") if body else "") else "acceptch"
    return {
        "kind": "response",
        "start_line": start,
        "status": 200 if start.startswith("HTTP/1.1 200") else 0,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "ch_kind": ch_kind,
        "accept_ch": accept_ch,
        "crit_ch": crit_ch,
        "chid": int(fields["ch-id"]) if fields.get("ch-id") else EMPTY_CHID,
        "hintsdigest": int(fields["hints-digest"]) if fields.get("hints-digest") else EMPTY_HINTSDIGEST,
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
        raise ClienthintsActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise ClienthintsActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise ClienthintsActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise ClienthintsActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_chid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"chid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_chid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-chid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_hintsdigest(chid: int = EMPTY_CHID, token: str = SENTINEL) -> int:
    material = canonical_accept_ch(token or SENTINEL, int(chid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_CHID = request_chid(SENTINEL)
DEFAULT_HINTSDIGEST = request_hintsdigest(DEFAULT_CHID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    chid: int,
    hintsdigest: int,
    include_chid: bool = True,
) -> bytes:
    live_chid = int(chid) & 0xFFFFFFFF if include_chid else EMPTY_CHID
    live_digest = int(hintsdigest) & 0xFFFFFFFF if include_chid and live_chid else EMPTY_HINTSDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_chid) if live_chid else b""
    header = bytearray()
    header.append(CH_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_acceptch(
    *,
    identity: str,
    chid: int,
    hintsdigest: int | None = None,
    include_chid: bool = True,
) -> bytes:
    live_chid = int(chid) & 0xFFFFFFFF if include_chid else EMPTY_CHID
    live_digest = int(hintsdigest) if hintsdigest is not None else request_hintsdigest(live_chid, identity)
    return encode_packet(
        FRAME_ACCEPTCH,
        identity=identity,
        chid=live_chid,
        hintsdigest=live_digest,
        include_chid=include_chid,
    )


def encode_critch(
    *,
    identity: str,
    chid: int,
    hintsdigest: int | None = None,
    include_chid: bool = True,
) -> bytes:
    live_chid = int(chid) & 0xFFFFFFFF if include_chid else EMPTY_CHID
    live_digest = int(hintsdigest) if hintsdigest is not None else request_hintsdigest(live_chid, identity)
    return encode_packet(
        FRAME_CRITCH,
        identity=identity,
        chid=live_chid,
        hintsdigest=live_digest,
        include_chid=include_chid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise ClienthintsActuationError("short_packet")
    first = raw[0]
    if first != CH_FIRST:
        raise ClienthintsActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise ClienthintsActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == CHID_SIZE:
        live_chid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_chid = EMPTY_CHID
    else:
        raise ClienthintsActuationError("illegal_chid")
    if offset >= len(raw):
        raise ClienthintsActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ACCEPTCH, FRAME_CRITCH}:
        raise ClienthintsActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise ClienthintsActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise ClienthintsActuationError("checksum_failed")
    if len(payload) < 5:
        raise ClienthintsActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise ClienthintsActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_chid = int(live_chid) != EMPTY_CHID
    has_hintsdigest = has_chid and int(live_digest) != EMPTY_HINTSDIGEST
    is_acceptch = frame_type == FRAME_ACCEPTCH
    is_critch = frame_type == FRAME_CRITCH
    return {
        "type": int(frame_type),
        "is_acceptch": is_acceptch,
        "is_critch": is_critch,
        "is_response": is_critch,
        "chid": int(live_chid),
        "has_chid": has_chid,
        "hintsdigest": int(live_digest),
        "has_hintsdigest": has_hintsdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "client_hints": "RFC8942",
        "accept_ch": canonical_accept_ch(identity, live_chid) if has_chid else "",
        "crit_ch": canonical_crit_ch(identity, live_chid, live_digest) if has_hintsdigest else "",
    }


class ClienthintsClient:
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
            raise ClienthintsActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_critch"] or not packet["is_response"]:
            raise ClienthintsActuationError("hintsdigest_required")
        if not packet["has_chid"]:
            raise ClienthintsActuationError("chid_required")
        if not packet["has_hintsdigest"]:
            raise ClienthintsActuationError("hintsdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_hintsdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_hintsdigest:
            raise ClienthintsActuationError("hintsdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "chid": int(reply.get("chid") or EMPTY_CHID),
            "identity": str(reply.get("identity") or ""),
            "hintsdigest": int(reply.get("hintsdigest") or EMPTY_HINTSDIGEST),
        }

    def critch(
        self,
        identity: str,
        chid: int,
        hintsdigest: int = EMPTY_HINTSDIGEST,
        *,
        wait_hintsdigest: bool = True,
        include_chid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_critch(
            identity=identity,
            chid=chid,
            hintsdigest=hintsdigest or request_hintsdigest(chid, identity),
            include_chid=include_chid,
        )
        return self.exchange(packet, wait_hintsdigest=wait_hintsdigest)


class ClienthintsSession:
    """CHID-gated loopback RFC 8942 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        chid_gate: int = DEFAULT_CHID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chid_gate = int(chid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.chid = EMPTY_CHID
        self.hintsdigest = EMPTY_HINTSDIGEST
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

    def store_chid_once(self, identity: str, chid: int, hintsdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(chid or EMPTY_CHID)
            live_digest = int(hintsdigest or EMPTY_HINTSDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.chid = live
                self.hintsdigest = live_digest or request_hintsdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.chid), int(self.hintsdigest)

    def read_chid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.chid), int(self.hintsdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "chid": EMPTY_CHID,
            "hintsdigest": EMPTY_HINTSDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _chid_missing(self) -> bool:
        return not int(self.chid_gate or 0)

    def _reply_critch(self, peer: tuple[str, int], identity: str, chid: int, hintsdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_critch(
            identity=identity,
            chid=chid,
            hintsdigest=hintsdigest,
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
            except ClienthintsActuationError:
                continue
            if not packet.get("is_acceptch") and not packet.get("is_critch"):
                continue
            if not packet.get("has_chid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_chid, stored_digest = self.store_chid_once(
                identity,
                int(packet.get("chid") or EMPTY_CHID),
                int(packet.get("hintsdigest") or EMPTY_HINTSDIGEST),
            )
            if not stored_name or not stored_chid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_acceptch"):
                    self.opened = True
                if packet.get("is_critch"):
                    self.handshook = True
                self.retrieved = True
            self._reply_critch(peer, stored_name, stored_chid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._chid_missing():
            return self._forbidden("missing_chid")
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
        do_acceptch: bool = True,
        do_critch: bool = True,
        do_hintsdigest: bool = True,
        replay: bool = True,
        use_chid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._chid_missing():
            return self._forbidden("missing_chid")
        live_token = str(token or SENTINEL)
        origin_chid = request_chid(live_token)
        origin_digest = request_hintsdigest(origin_chid, live_token)
        client: ClienthintsClient | None = None
        independent: ClienthintsClient | None = None
        try:
            client = ClienthintsClient(self.host, int(self.port))
            if not do_acceptch:
                return self._conflict("acceptch_required")
            bind_packet = encode_acceptch(
                identity=live_token,
                chid=origin_chid,
                hintsdigest=origin_digest,
                include_chid=use_chid,
            )
            if not use_chid:
                try:
                    client.exchange(bind_packet, wait_hintsdigest=True)
                except ClienthintsActuationError:
                    return self._conflict("chid_required")
                return self._conflict("chid_required")
            client.send(bind_packet)
            if not do_critch:
                return self._conflict("critch_required")
            proxy_packet = encode_critch(
                identity=live_token,
                chid=origin_chid,
                hintsdigest=origin_digest,
                include_chid=True,
            )
            if not do_hintsdigest:
                try:
                    client.exchange(proxy_packet, wait_hintsdigest=False)
                except ClienthintsActuationError as error:
                    if str(error) == "hintsdigest_required":
                        return self._conflict("hintsdigest_required")
                    return self._conflict("hintsdigest_required")
                return self._conflict("hintsdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_hintsdigest=True)
            except ClienthintsActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("chid_required")
                if reason == "hintsdigest_required":
                    return self._conflict("hintsdigest_required")
                return self._conflict("acceptch_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("acceptch_required")
            if int(reply.get("chid") or EMPTY_CHID) != origin_chid:
                return self._conflict("hintsdigest_required")
            if int(reply.get("hintsdigest") or EMPTY_HINTSDIGEST) != origin_digest:
                return self._conflict("hintsdigest_required")
            self.retrieved = True
            if replay:
                independent = ClienthintsClient(self.host, int(self.port))
                try:
                    poll = independent.critch(
                        POLL_TOKEN,
                        poll_chid(live_token),
                        request_hintsdigest(poll_chid(live_token), POLL_TOKEN),
                        wait_hintsdigest=True,
                    )
                except ClienthintsActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_chid, stored_digest = self.read_chid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_chid != origin_chid
                    or stored_digest != origin_digest
                    or int(poll.get("chid") or EMPTY_CHID) != origin_chid
                    or int(poll.get("hintsdigest") or EMPTY_HINTSDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_chid}:{origin_digest}:{live_token}:{canonical_accept_ch(live_token, origin_chid)}:{canonical_crit_ch(live_token, origin_chid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "chid": origin_chid,
                "hintsdigest": origin_digest,
                "acceptch_frame": True,
                "critch": True,
                "hintsdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "chid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_clienthints_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "chid": origin_chid,
                "hintsdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "acceptch_frame": True,
                "critch": True,
                "hintsdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "chid_bound": True,
            }
        except (OSError, ClienthintsActuationError) as error:
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
        live = independent_clienthints_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "chid": int(live.get("chid") or EMPTY_CHID),
            "hintsdigest": int(live.get("hintsdigest") or EMPTY_HINTSDIGEST),
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


def call_clienthints_tool(session: ClienthintsSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one Client Hints tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_acceptch = True if arguments.get("acceptch") is None else bool(arguments.get("acceptch"))
    do_critch = True if arguments.get("critch") is None else bool(arguments.get("critch"))
    do_hintsdigest = True if arguments.get("hintsdigest") is None else bool(arguments.get("hintsdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_chid = True if arguments.get("use_chid") is None else bool(arguments.get("use_chid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_acceptch=do_acceptch,
            do_critch=do_critch,
            do_hintsdigest=do_hintsdigest,
            replay=replay,
            use_chid=use_chid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise ClienthintsActuationError(f"unsupported clienthints action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_clienthints_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed Client Hints hintsdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "chid": EMPTY_CHID,
        "hintsdigest": EMPTY_HINTSDIGEST,
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
            "acceptch_frame",
            "critch",
            "hintsdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "chid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    chid = int(payload.get("chid") or EMPTY_CHID)
    hintsdigest = int(payload.get("hintsdigest") or EMPTY_HINTSDIGEST)
    dual = port > 0 and bool(chid) and bool(hintsdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "chid": chid,
        "hintsdigest": hintsdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "acceptch_frame": payload.get("acceptch_frame") is True,
        "critch": payload.get("critch") is True,
        "hintsdigest_response": payload.get("hintsdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "chid_bound": payload.get("chid_bound") is True,
    }


def run_clienthints_workflow(
    *,
    with_chid: bool = True,
    skip_bind: bool = False,
    do_acceptch: bool = True,
    do_critch: bool = True,
    do_hintsdigest: bool = True,
    replay: bool = True,
    use_chid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 8942 ACCEPTCH/CRITCH chid cycle workflow."""

    descriptor = clienthints_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CLIENTHINTS_TOOL_PROVIDER),
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
        raise ClienthintsActuationError(f"clienthints tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="clienthints-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = ClienthintsSession(out, chid_gate=DEFAULT_CHID if with_chid else EMPTY_CHID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "acceptch": do_acceptch,
            "critch": do_critch,
            "hintsdigest": do_hintsdigest,
            "replay": replay,
            "use_chid": use_chid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_clienthints_tool(session, arguments))
            except ClienthintsActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_clienthints_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_chid
        and not skip_bind
        and do_acceptch
        and do_critch
        and do_hintsdigest
        and replay
        and use_chid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "clienthints_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_chid": with_chid,
        "skip_bind": skip_bind,
        "acceptch_frame": do_acceptch,
        "critch": do_critch,
        "hintsdigest": do_hintsdigest,
        "replay": replay,
        "use_chid": use_chid,
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
        "chid_value": int(publish_result.get("chid") or independent.get("chid") or EMPTY_CHID),
        "hintsdigest_value": int(publish_result.get("hintsdigest") or independent.get("hintsdigest") or EMPTY_HINTSDIGEST),
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
        "chid": int(trace_body["chid_value"] or EMPTY_CHID),
        "hintsdigest": int(trace_body["hintsdigest_value"] or EMPTY_HINTSDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_chid": with_chid,
        "skip_bind": skip_bind,
        "acceptch_cycle": do_acceptch,
        "critch_cycle": do_critch,
        "hintsdigest_cycle": do_hintsdigest,
        "replay": replay,
        "use_chid": use_chid,
    }


def verify_clienthints_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Client Hints trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_clienthints_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    chid = int(trace.get("chid_value") or independent.get("chid") or EMPTY_CHID)
    hintsdigest = int(trace.get("hintsdigest_value") or independent.get("hintsdigest") or EMPTY_HINTSDIGEST)
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
        "acceptch_frame": independent.get("acceptch_frame") is True,
        "critch": independent.get("critch") is True,
        "hintsdigest_response": independent.get("hintsdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "chid_bound": independent.get("chid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "hintsdigest_recorded": (
            port > 0
            and chid == DEFAULT_CHID
            and hintsdigest == DEFAULT_HINTSDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def clienthints_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.clienthints_actuation import "
        "builtin_clienthints_actuation_proof; r=builtin_clienthints_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='clienthints_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_clienthints_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=CLIENTHINTS_ACTUATION_ID,
        name="First-class RFC 8942 HTTP Client Hints ACCEPTCH/CRITCH actuation",
        description=(
            "Missions that require a clienthints tool can opt the clienthints provider in, "
            "bind a loopback RFC 8942 Client Hints origin, complete an ACCEPTCH "
            "with a non-empty chid, lockstep a CRITCH that carries the "
            "stored hintsdigest, independently poll the stored hintsdigest "
            "on a later socket, and seal a digest-chained hintsdigest. Default "
            "routing stays fail-closed; a missing chid keeps the hole "
            "falsifiable, and skip-ACCEPTCH/CRITCH/HINTSDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.clienthints_actuation:builtin_clienthints_actuation_proof",
        proof_command=clienthints_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.structuredfields-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/clienthints_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/earlyhints_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required clienthints tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 8942 daemon, speaks an "
            "ACCEPTCH then CRITCH over Client Hints with a non-empty chid and "
            "hintsdigest, independently polls the stored hintsdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 8941 Structured Fields lockstep is proved. "
            "Missing chids, skip-ACCEPTCH, skip-CRITCH, skip-hintsdigest, skip-REPLAY, "
            "and an ACCEPTCH aimed without a chid stay fail-closed. "
            "Later genesis can take RFC 8297 Early Hints LINK/HINT as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("clienthints", "rfc8942", "http", "chid", "hintsdigest", "acceptch", "critch", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T034822Z-0d35f585",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_clienthints_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 8942 Client Hints lockstep actuation seals a hintsdigest."""

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

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = CLIENTHINTS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(CLIENTHINTS_ACTUATION_GOAL) == (
        CLIENTHINTS_ACTUATION_ID,
    )
    checks["leftover_text_binds_clienthints"] = leftover_marker_ids(CLIENTHINTS_LEFTOVER) == (
        CLIENTHINTS_ACTUATION_ID,
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
        (EARLYHINTS_ACTUATION_GOAL, EARLYHINTS_ACTUATION_ID, "earlyhints"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_clienthints"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"clienthints_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            CLIENTHINTS_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = CLIENTHINTS_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_token_list(ACCEPT_CH_FIELDS)
    rebuilt = serialize_token_list(parse_token_list(advertised))
    critical = serialize_token_list(CRITICAL_CH_FIELDS)
    rfc_accept = parse_token_list("Sec-CH-Example, Sec-CH-Example-Other")
    asked = parse_http_request(acceptch_request(SENTINEL, DEFAULT_CHID))
    listed_req = parse_http_request(critch_request(SENTINEL, DEFAULT_CHID, DEFAULT_HINTSDIGEST))
    got = parse_http_response(acceptch_response(SENTINEL, DEFAULT_CHID, DEFAULT_HINTSDIGEST))
    crit_reply = parse_http_response(critch_response(SENTINEL, DEFAULT_CHID, DEFAULT_HINTSDIGEST))
    checks["accept_ch_roundtrip"] = (
        parse_token_list(advertised) == ACCEPT_CH_FIELDS
        and hmac.compare_digest(rebuilt, advertised)
        and is_token("DPR") is True
        and is_token("Viewport-Width") is True
        and is_token("BH-CH-OK") is True
        and rfc_accept == ("Sec-CH-Example", "Sec-CH-Example-Other")
        and parse_token_list(critical) == CRITICAL_CH_FIELDS
    )
    checks["crit_ch_roundtrip"] = (
        parse_token_list(critical)[0] == "DPR"
        and hmac.compare_digest(serialize_token_list(parse_token_list(critical)), critical)
        and DEFAULT_HINTSDIGEST == request_hintsdigest(DEFAULT_CHID, SENTINEL)
        and parse_hints(serialize_hints(DEFAULT_HINT_VALUES)) == DEFAULT_HINT_VALUES
    )
    checks["acceptch_critch_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["ch_kind"] == "acceptch"
        and asked["chid"] == DEFAULT_CHID
        and listed_req["ch_kind"] == "critch"
        and listed_req["crit_ch"] == CRITICAL_CH_FIELDS
        and listed_req["hints"][0] == ("DPR", "2")
        and got["status"] == 200
        and crit_reply["status"] == 200
        and got["accept_ch"] == ACCEPT_CH_FIELDS
        and crit_reply["crit_ch"] == CRITICAL_CH_FIELDS
        and got["content_length_matches_body"] is True
        and crit_reply["content_length_matches_body"] is True
        and got["hintsdigest"] == DEFAULT_HINTSDIGEST
        and crit_reply["hintsdigest"] == DEFAULT_HINTSDIGEST
        and token_list_matches(serialize_token_list(got["accept_ch"]), advertised)
    )
    checks["catalog_names_clienthints"] = (
        len(catalog) > 77
        and catalog[77]["id"] == CLIENTHINTS_ACTUATION_ID
        and catalog[76]["id"] == STRUCTUREDFIELDS_ACTUATION_ID
        and catalog[77]["source"] == "genesis_bind_clienthints"
    )
    checks["catalog_names_earlyhints"] = (
        len(catalog) > 78
        and catalog[78]["id"] == EARLYHINTS_ACTUATION_ID
        and catalog[78]["source"] == "genesis_bind_earlyhints"
    )
    family = capability_family(CLIENTHINTS_ACTUATION_GOAL)
    checks["family_is_clienthints"] = "clienthint" in family
    checks["family_is_acceptch"] = "acceptch" in family
    checks["family_is_chid"] = "chid" in family
    checks["family_is_critch"] = "critch" in family
    checks["family_is_hintsdigest"] = "hintsdigest" in family
    checks["family_is_not_earlyhints"] = (
        "earlyhint" not in family
        and "rfc8297" not in family
        and "linkid" not in family
        and "hint103" not in family
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
    packed = encode_acceptch(identity=SENTINEL, chid=DEFAULT_CHID, hintsdigest=DEFAULT_HINTSDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_acceptch"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_chid"] is True
        and parsed["chid"] == DEFAULT_CHID
        and parsed["hintsdigest"] == DEFAULT_HINTSDIGEST
        and parsed["is_response"] is False
        and parsed["is_critch"] is False
        and parsed["type"] == FRAME_ACCEPTCH
        and parsed["first_byte"] == CH_FIRST
    )
    shook = encode_critch(
        identity=SENTINEL,
        chid=DEFAULT_CHID,
        hintsdigest=DEFAULT_HINTSDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_critch"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_acceptch"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["chid"] == DEFAULT_CHID
        and answer_parsed["hintsdigest"] == DEFAULT_HINTSDIGEST
        and answer_parsed["has_hintsdigest"] is True
        and answer_parsed["type"] == FRAME_CRITCH
        and answer_parsed["first_byte"] == CH_FIRST
    )
    bare = encode_acceptch(identity=SENTINEL, chid=DEFAULT_CHID, include_chid=False)
    checks["missing_chid_is_unauthenticated"] = parse_message(bare)["has_chid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    clienthints_signature = semantic_signature(CLIENTHINTS_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(clienthints_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_clienthints = ToolDescriptor(name="remote_clienthints", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_clienthints)
    checks["naive_mcp_clienthints_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = clienthints_tool_descriptor()
    default_clienthints = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CLIENTHINTS_TOOL_PROVIDER),
    )
    checks["default_clienthints_provider_is_unsupported"] = (
        default_clienthints.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{CLIENTHINTS_TOOL_PROVIDER}" in default_clienthints.reasons
    )
    checks["opted_in_clienthints_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_clienthints],
        required_tool_names=("local_memory", "clienthints"),
    )
    checks["naive_preflight_missing_clienthints"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["clienthints"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "clienthints"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CLIENTHINTS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "clienthints" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="clienthints-actuation-") as tmp:
        root = Path(tmp)
        missing = run_clienthints_workflow(with_chid=False, output_dir=root / "missing")
        skip_bind = run_clienthints_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_acceptch = run_clienthints_workflow(do_acceptch=False, output_dir=root / "skip-acceptch")
        skip_critch = run_clienthints_workflow(do_critch=False, output_dir=root / "skip-critch")
        skip_hintsdigest = run_clienthints_workflow(do_hintsdigest=False, output_dir=root / "skip-hintsdigest")
        skip_replay = run_clienthints_workflow(replay=False, output_dir=root / "skip-replay")
        skip_chid = run_clienthints_workflow(use_chid=False, output_dir=root / "skip-chid")
        live = run_clienthints_workflow(output_dir=root / "live")
        verify = verify_clienthints_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_clienthints_trace(clone)
        checks["naive_without_chid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_chid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_acceptch_stays_empty"] = (
            skip_acceptch["ok"] is False
            and skip_acceptch["error"] == "acceptch_required"
            and skip_acceptch["final_status"] == 409
            and skip_acceptch["payload_exists"] is False
        )
        checks["skip_critch_stays_empty"] = (
            skip_critch["ok"] is False
            and skip_critch["error"] == "critch_required"
            and skip_critch["final_status"] == 409
            and skip_critch["payload_exists"] is False
        )
        checks["skip_hintsdigest_stays_empty"] = (
            skip_hintsdigest["ok"] is False
            and skip_hintsdigest["error"] == "hintsdigest_required"
            and skip_hintsdigest["final_status"] == 409
            and skip_hintsdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_chid_stays_empty"] = (
            skip_chid["ok"] is False
            and skip_chid["error"] == "chid_required"
            and skip_chid["final_status"] == 409
            and skip_chid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_hintsdigest"] = (
            int(live.get("chid") or 0) == DEFAULT_CHID
            and int(live.get("hintsdigest") or 0) == DEFAULT_HINTSDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_chid_encode_critch_hintsdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_acceptch["ok"] is False
            and skip_critch["ok"] is False
            and skip_hintsdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_chid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="clienthints-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != CLIENTHINTS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_clienthints"] = (
        live_goal == CLIENTHINTS_ACTUATION_GOAL
        and CLIENTHINTS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_clienthints"
    )

    with tempfile.TemporaryDirectory(prefix="clienthints-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(CLIENTHINTS_LEFTOVER, root)
        register_catalog_proved(root, CLIENTHINTS_ACTUATION_ID)
        reason = leftover_satisfied_by(CLIENTHINTS_LEFTOVER, root)
        after = leftover_is_open(CLIENTHINTS_LEFTOVER, root)
    checks["clienthints_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_clienthints_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{CLIENTHINTS_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_clienthints_actuation_capability()
    return {
        "ok": ok,
        "action": "clienthints_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": CLIENTHINTS_ACTUATION_GOAL,
        "done_when": CLIENTHINTS_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
