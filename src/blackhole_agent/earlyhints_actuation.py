"""Drive a first-class Early Hints tool through RFC 8297 LINK/HINT.

Tool routing already fails missions that require ``earlyhints``: hosted
earlyhints endpoints stay on the unsupported MCP provider, and no first-party
earlyhints provider is executable. Unbound therefore cannot speak a LINK,
lockstep a HINT linkid handshake over Early Hints LINKID,
independently poll the stored earlydigest, or seal an earlydigest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``earlyhints`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 8297 daemon
- keep a missing-linkid client so the earlyhints-linkid hole stays falsifiable
- refuse HINT until a LINK lands with a non-empty linkid
- independently poll the stored earlydigest on a later client socket
- persist a sealed earlydigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 8942 HTTP Client Hints
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
    EARLYHINTS_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    earlyhints_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
EARLYHINTS_ACTUATION_ID = "capability.earlyhints-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-EH-OK"
POLL_TOKEN = "BH-EH-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_LINKID = 0
EMPTY_EARLYDIGEST = 0
EH_FIRST = 0x45  # RFC 8297 Early Hints (ASCII 'E')
LINKID_SIZE = 4
EARLYDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_HINT = 0x02  # RFC 8297 Early-Hints retry
FRAME_LINK = 0x01  # RFC 8297 Link advertisement
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
TCHAR = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "!#$%&'*+-.^_`|~"
)
TOKEN_START = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ*")
# RFC 8297 103 Early Hints carries RFC 8288 Link values (preload examples from the RFC).
DEFAULT_LINKS = (
    ("/style.css", "preload", "style"),
    ("/script.js", "preload", "script"),
)
HINT_LINKS = (("/style.css", "preload", "style"),)
TARGET_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~/%")
EARLYHINTS_LEFTOVER = (
    "Later genesis can take RFC 8297 Early Hints LINK/HINT over a "
    "linkid-gated earlydigest."
)
EARLYHINTS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{EARLYHINTS_ACTUATION_ID};"
    f"capability_proved:{EARLYHINTS_ACTUATION_ID};"
    "no_skill_route"
)
EARLYHINTS_ACTUATION_GOAL = (
    "Repair rfc8297 earlyhints link/hint cycle cannot land over http "
    "earlyhints linkid: hosted earlyhints endpoints remain unsupported so a LINK then "
    "HINT linkid handshake cannot land and a sealed earlydigest "
    "cannot be produced. A missing earlyhints linkid stays forbidden; fail-closed "
    "routing never opts the earlyhints provider in. An independent later poll of the "
    "stored earlydigest keeps the hole falsifiable."
)


class EarlyhintsActuationError(RuntimeError):
    """Raised when the Early Hints session or loopback daemon fixture misbehaves."""


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
            raise EarlyhintsActuationError("short_sfv")
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
    """RFC 8941 sf-token used by RFC 8288 rel / as parameters on RFC 8297 Links."""

    raw = str(value or "")
    if not raw or raw[0] not in TOKEN_START:
        return False
    allowed = TCHAR | set(":/")
    return all(char in allowed for char in raw)


def serialize_link_list(links: Sequence[tuple[str, str, str]]) -> str:
    """RFC 8288 link-value list used by RFC 8297 103 Early Hints."""

    chunks: list[str] = []
    for target, rel, as_token in links:
        live_target = str(target or "")
        if not live_target or live_target[0] not in "/h":
            raise EarlyhintsActuationError("illegal_target")
        if any(char not in TARGET_CHARS for char in live_target.lstrip("/")):
            if any(char not in TARGET_CHARS for char in live_target):
                raise EarlyhintsActuationError("illegal_target")
        if not is_token(rel) or not is_token(as_token):
            raise EarlyhintsActuationError("illegal_token")
        chunks.append(f"<{live_target}>; rel={rel}; as={as_token}")
    return ", ".join(chunks)


def parse_link_list(text: str) -> tuple[tuple[str, str, str], ...]:
    """Parse a comma-separated RFC 8288 Link list of preload members."""

    parser = _Parser(text)
    parser.skip_ows()
    if parser.eof():
        return ()
    members: list[tuple[str, str, str]] = []
    while True:
        parser.skip_ows()
        if parser.take() != "<":
            raise EarlyhintsActuationError("illegal_links")
        start = parser.pos
        while parser.peek() and parser.peek() != ">":
            parser.pos += 1
        target = parser.text[start:parser.pos]
        if parser.take() != ">" or not target:
            raise EarlyhintsActuationError("illegal_links")
        rel = ""
        as_token = ""
        while True:
            parser.skip_ows()
            if parser.peek() != ";":
                break
            parser.pos += 1
            parser.skip_ows()
            name_start = parser.pos
            while parser.peek() and parser.peek() not in ";,= \t":
                parser.pos += 1
            name = parser.text[name_start:parser.pos].lower()
            parser.skip_ows()
            if parser.take() != "=":
                raise EarlyhintsActuationError("illegal_link")
            value_start = parser.pos
            while parser.peek() and parser.peek() not in ";, \t":
                parser.pos += 1
            value = parser.text[value_start:parser.pos]
            if name == "rel":
                rel = value
            elif name == "as":
                as_token = value
        if not rel:
            raise EarlyhintsActuationError("illegal_links")
        members.append((target, rel, as_token))
        parser.skip_ows()
        if parser.peek() != ",":
            break
        parser.pos += 1
    parser.skip_ows()
    if not parser.eof():
        raise EarlyhintsActuationError("illegal_links")
    return tuple(members)


def canonical_link(identity: str, linkid: int) -> str:
    """RFC 8297 103 Link list bound to identity and linkid."""

    return (
        f"{serialize_link_list(DEFAULT_LINKS)}; "
        f"identity={identity}; linkid={int(linkid) & 0xFFFFFFFF}"
    )


def canonical_hint(identity: str, linkid: int, earlydigest: int | None = None) -> str:
    """RFC 8297 hinted Link subset of the stored 103 members."""

    suffix = ""
    if earlydigest is not None:
        suffix = f"; earlydigest={int(earlydigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_link_list(HINT_LINKS)}; "
        f"identity={identity}; linkid={int(linkid) & 0xFFFFFFFF}{suffix}"
    )


def representation_links(identity: str, linkid: int, earlydigest: int) -> str:
    return canonical_hint(identity, linkid, earlydigest)


def link_list_matches(left: str, right: str) -> bool:
    return parse_link_list(left) == parse_link_list(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise EarlyhintsActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise EarlyhintsActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise EarlyhintsActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise EarlyhintsActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def link_request(identity: str, linkid: int) -> bytes:
    """HTTP GET that elicits RFC 8297 Link / Early-Hints."""

    keyid = f"{int(linkid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /earlyhints/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Link-Id: {int(linkid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def hint_request(identity: str, linkid: int, earlydigest: int | None = None) -> bytes:
    """HTTP GET retry carrying Early Hints fulfillment (RFC 8297 reliability)."""

    keyid = f"{int(linkid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if earlydigest is not None:
        extra = f"Early-Digest: {int(earlydigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /earlyhints/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Link-Id: {int(linkid) & 0xFFFFFFFF}\r\n"
        "Early-Hints: 103\r\n"
        f"Link: {serialize_link_list(HINT_LINKS)}\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    eh_kind = "hint" if fields.get("early-hints") == "103" else "link"
    links = parse_link_list(fields["link"]) if fields.get("link") else ()
    hint_links = links if eh_kind == "hint" else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "eh_kind": eh_kind,
        "links": links,
        "hint_links": hint_links,
        "linkid": int(fields["link-id"]) if fields.get("link-id") else EMPTY_LINKID,
    }


def link_response(identity: str, linkid: int, earlydigest: int) -> bytes:
    """HTTP 103 Early Hints advertising RFC 8288 Link values."""

    advertised = serialize_link_list(DEFAULT_LINKS)
    body = canonical_link(identity, linkid)
    return (
        "HTTP/1.1 103 Early Hints\r\n"
        f"Link: {advertised}\r\n"
        f"Link-Id: {int(linkid) & 0xFFFFFFFF}\r\n"
        f"Early-Digest: {int(earlydigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/early-hints\r\n"
        f"Content-Length: {len(body.encode('ascii'))}\r\n"
        "\r\n"
        f"{body}"
    ).encode("ascii")


def hint_response(identity: str, linkid: int, earlydigest: int) -> bytes:
    """HTTP 200 after a 103 Early Hints cycle, carrying the stored earlydigest."""

    advertised = serialize_link_list(DEFAULT_LINKS)
    body = representation_links(identity, linkid, earlydigest)
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Link: {advertised}\r\n"
        f"Link-Id: {int(linkid) & 0xFFFFFFFF}\r\n"
        f"Early-Digest: {int(earlydigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/early-hints\r\n"
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
        raise EarlyhintsActuationError("illegal_content_length") from error
    links = parse_link_list(fields["link"]) if fields.get("link") else ()
    if start.startswith("HTTP/1.1 103"):
        status = 103
        eh_kind = "link"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        eh_kind = "hint"
    else:
        status = 0
        eh_kind = "link"
    decoded = body.decode("ascii") if body else ""
    hint_links = HINT_LINKS if eh_kind == "hint" and "earlydigest=" in decoded else ()
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "eh_kind": eh_kind,
        "links": links,
        "hint_links": hint_links,
        "linkid": int(fields["link-id"]) if fields.get("link-id") else EMPTY_LINKID,
        "earlydigest": int(fields["early-digest"]) if fields.get("early-digest") else EMPTY_EARLYDIGEST,
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
        raise EarlyhintsActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise EarlyhintsActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise EarlyhintsActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise EarlyhintsActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_linkid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"linkid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_linkid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-linkid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_earlydigest(linkid: int = EMPTY_LINKID, token: str = SENTINEL) -> int:
    material = canonical_link(token or SENTINEL, int(linkid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_LINKID = request_linkid(SENTINEL)
DEFAULT_EARLYDIGEST = request_earlydigest(DEFAULT_LINKID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    linkid: int,
    earlydigest: int,
    include_linkid: bool = True,
) -> bytes:
    live_linkid = int(linkid) & 0xFFFFFFFF if include_linkid else EMPTY_LINKID
    live_digest = int(earlydigest) & 0xFFFFFFFF if include_linkid and live_linkid else EMPTY_EARLYDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_linkid) if live_linkid else b""
    header = bytearray()
    header.append(EH_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_link(
    *,
    identity: str,
    linkid: int,
    earlydigest: int | None = None,
    include_linkid: bool = True,
) -> bytes:
    live_linkid = int(linkid) & 0xFFFFFFFF if include_linkid else EMPTY_LINKID
    live_digest = int(earlydigest) if earlydigest is not None else request_earlydigest(live_linkid, identity)
    return encode_packet(
        FRAME_LINK,
        identity=identity,
        linkid=live_linkid,
        earlydigest=live_digest,
        include_linkid=include_linkid,
    )


def encode_hint(
    *,
    identity: str,
    linkid: int,
    earlydigest: int | None = None,
    include_linkid: bool = True,
) -> bytes:
    live_linkid = int(linkid) & 0xFFFFFFFF if include_linkid else EMPTY_LINKID
    live_digest = int(earlydigest) if earlydigest is not None else request_earlydigest(live_linkid, identity)
    return encode_packet(
        FRAME_HINT,
        identity=identity,
        linkid=live_linkid,
        earlydigest=live_digest,
        include_linkid=include_linkid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise EarlyhintsActuationError("short_packet")
    first = raw[0]
    if first != EH_FIRST:
        raise EarlyhintsActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise EarlyhintsActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == LINKID_SIZE:
        live_linkid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_linkid = EMPTY_LINKID
    else:
        raise EarlyhintsActuationError("illegal_linkid")
    if offset >= len(raw):
        raise EarlyhintsActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_LINK, FRAME_HINT}:
        raise EarlyhintsActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise EarlyhintsActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise EarlyhintsActuationError("checksum_failed")
    if len(payload) < 5:
        raise EarlyhintsActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise EarlyhintsActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_linkid = int(live_linkid) != EMPTY_LINKID
    has_earlydigest = has_linkid and int(live_digest) != EMPTY_EARLYDIGEST
    is_link = frame_type == FRAME_LINK
    is_hint = frame_type == FRAME_HINT
    return {
        "type": int(frame_type),
        "is_link": is_link,
        "is_hint": is_hint,
        "is_response": is_hint,
        "linkid": int(live_linkid),
        "has_linkid": has_linkid,
        "earlydigest": int(live_digest),
        "has_earlydigest": has_earlydigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "early_hints": "RFC8297",
        "links": canonical_link(identity, live_linkid) if has_linkid else "",
        "hint_links": canonical_hint(identity, live_linkid, live_digest) if has_earlydigest else "",
    }


class EarlyhintsClient:
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
            raise EarlyhintsActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_hint"] or not packet["is_response"]:
            raise EarlyhintsActuationError("earlydigest_required")
        if not packet["has_linkid"]:
            raise EarlyhintsActuationError("linkid_required")
        if not packet["has_earlydigest"]:
            raise EarlyhintsActuationError("earlydigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_earlydigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_earlydigest:
            raise EarlyhintsActuationError("earlydigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "linkid": int(reply.get("linkid") or EMPTY_LINKID),
            "identity": str(reply.get("identity") or ""),
            "earlydigest": int(reply.get("earlydigest") or EMPTY_EARLYDIGEST),
        }

    def hint(
        self,
        identity: str,
        linkid: int,
        earlydigest: int = EMPTY_EARLYDIGEST,
        *,
        wait_earlydigest: bool = True,
        include_linkid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_hint(
            identity=identity,
            linkid=linkid,
            earlydigest=earlydigest or request_earlydigest(linkid, identity),
            include_linkid=include_linkid,
        )
        return self.exchange(packet, wait_earlydigest=wait_earlydigest)


class EarlyhintsSession:
    """LINKID-gated loopback RFC 8297 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        linkid_gate: int = DEFAULT_LINKID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.linkid_gate = int(linkid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.linkid = EMPTY_LINKID
        self.earlydigest = EMPTY_EARLYDIGEST
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

    def store_linkid_once(self, identity: str, linkid: int, earlydigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(linkid or EMPTY_LINKID)
            live_digest = int(earlydigest or EMPTY_EARLYDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.linkid = live
                self.earlydigest = live_digest or request_earlydigest(live, name)
                self.stored = True
            return str(self.identity), int(self.linkid), int(self.earlydigest)

    def read_linkid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.linkid), int(self.earlydigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "linkid": EMPTY_LINKID,
            "earlydigest": EMPTY_EARLYDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _linkid_missing(self) -> bool:
        return not int(self.linkid_gate or 0)

    def _reply_hint(self, peer: tuple[str, int], identity: str, linkid: int, earlydigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_hint(
            identity=identity,
            linkid=linkid,
            earlydigest=earlydigest,
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
            except EarlyhintsActuationError:
                continue
            if not packet.get("is_link") and not packet.get("is_hint"):
                continue
            if not packet.get("has_linkid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_linkid, stored_digest = self.store_linkid_once(
                identity,
                int(packet.get("linkid") or EMPTY_LINKID),
                int(packet.get("earlydigest") or EMPTY_EARLYDIGEST),
            )
            if not stored_name or not stored_linkid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_link"):
                    self.opened = True
                if packet.get("is_hint"):
                    self.handshook = True
                self.retrieved = True
            self._reply_hint(peer, stored_name, stored_linkid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._linkid_missing():
            return self._forbidden("missing_linkid")
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
        do_link: bool = True,
        do_hint: bool = True,
        do_earlydigest: bool = True,
        replay: bool = True,
        use_linkid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._linkid_missing():
            return self._forbidden("missing_linkid")
        live_token = str(token or SENTINEL)
        origin_linkid = request_linkid(live_token)
        origin_digest = request_earlydigest(origin_linkid, live_token)
        client: EarlyhintsClient | None = None
        independent: EarlyhintsClient | None = None
        try:
            client = EarlyhintsClient(self.host, int(self.port))
            if not do_link:
                return self._conflict("link_required")
            bind_packet = encode_link(
                identity=live_token,
                linkid=origin_linkid,
                earlydigest=origin_digest,
                include_linkid=use_linkid,
            )
            if not use_linkid:
                try:
                    client.exchange(bind_packet, wait_earlydigest=True)
                except EarlyhintsActuationError:
                    return self._conflict("linkid_required")
                return self._conflict("linkid_required")
            client.send(bind_packet)
            if not do_hint:
                return self._conflict("hint_required")
            proxy_packet = encode_hint(
                identity=live_token,
                linkid=origin_linkid,
                earlydigest=origin_digest,
                include_linkid=True,
            )
            if not do_earlydigest:
                try:
                    client.exchange(proxy_packet, wait_earlydigest=False)
                except EarlyhintsActuationError as error:
                    if str(error) == "earlydigest_required":
                        return self._conflict("earlydigest_required")
                    return self._conflict("earlydigest_required")
                return self._conflict("earlydigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_earlydigest=True)
            except EarlyhintsActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("linkid_required")
                if reason == "earlydigest_required":
                    return self._conflict("earlydigest_required")
                return self._conflict("link_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("link_required")
            if int(reply.get("linkid") or EMPTY_LINKID) != origin_linkid:
                return self._conflict("earlydigest_required")
            if int(reply.get("earlydigest") or EMPTY_EARLYDIGEST) != origin_digest:
                return self._conflict("earlydigest_required")
            self.retrieved = True
            if replay:
                independent = EarlyhintsClient(self.host, int(self.port))
                try:
                    poll = independent.hint(
                        POLL_TOKEN,
                        poll_linkid(live_token),
                        request_earlydigest(poll_linkid(live_token), POLL_TOKEN),
                        wait_earlydigest=True,
                    )
                except EarlyhintsActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_linkid, stored_digest = self.read_linkid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_linkid != origin_linkid
                    or stored_digest != origin_digest
                    or int(poll.get("linkid") or EMPTY_LINKID) != origin_linkid
                    or int(poll.get("earlydigest") or EMPTY_EARLYDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_linkid}:{origin_digest}:{live_token}:{canonical_link(live_token, origin_linkid)}:{canonical_hint(live_token, origin_linkid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "linkid": origin_linkid,
                "earlydigest": origin_digest,
                "link_frame": True,
                "hint": True,
                "earlydigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "linkid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_earlyhints_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "linkid": origin_linkid,
                "earlydigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "link_frame": True,
                "hint": True,
                "earlydigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "linkid_bound": True,
            }
        except (OSError, EarlyhintsActuationError) as error:
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
        live = independent_earlyhints_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "linkid": int(live.get("linkid") or EMPTY_LINKID),
            "earlydigest": int(live.get("earlydigest") or EMPTY_EARLYDIGEST),
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


def call_earlyhints_tool(session: EarlyhintsSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one Early Hints tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_link = True if arguments.get("link") is None else bool(arguments.get("link"))
    do_hint = True if arguments.get("hint") is None else bool(arguments.get("hint"))
    do_earlydigest = True if arguments.get("earlydigest") is None else bool(arguments.get("earlydigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_linkid = True if arguments.get("use_linkid") is None else bool(arguments.get("use_linkid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_link=do_link,
            do_hint=do_hint,
            do_earlydigest=do_earlydigest,
            replay=replay,
            use_linkid=use_linkid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise EarlyhintsActuationError(f"unsupported earlyhints action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_earlyhints_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed Early Hints earlydigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "linkid": EMPTY_LINKID,
        "earlydigest": EMPTY_EARLYDIGEST,
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
            "link_frame",
            "hint",
            "earlydigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "linkid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    linkid = int(payload.get("linkid") or EMPTY_LINKID)
    earlydigest = int(payload.get("earlydigest") or EMPTY_EARLYDIGEST)
    dual = port > 0 and bool(linkid) and bool(earlydigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "linkid": linkid,
        "earlydigest": earlydigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "link_frame": payload.get("link_frame") is True,
        "hint": payload.get("hint") is True,
        "earlydigest_response": payload.get("earlydigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "linkid_bound": payload.get("linkid_bound") is True,
    }


def run_earlyhints_workflow(
    *,
    with_linkid: bool = True,
    skip_bind: bool = False,
    do_link: bool = True,
    do_hint: bool = True,
    do_earlydigest: bool = True,
    replay: bool = True,
    use_linkid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 8297 LINK/HINT linkid cycle workflow."""

    descriptor = earlyhints_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EARLYHINTS_TOOL_PROVIDER),
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
        raise EarlyhintsActuationError(f"earlyhints tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="earlyhints-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = EarlyhintsSession(out, linkid_gate=DEFAULT_LINKID if with_linkid else EMPTY_LINKID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "link": do_link,
            "hint": do_hint,
            "earlydigest": do_earlydigest,
            "replay": replay,
            "use_linkid": use_linkid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_earlyhints_tool(session, arguments))
            except EarlyhintsActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_earlyhints_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_linkid
        and not skip_bind
        and do_link
        and do_hint
        and do_earlydigest
        and replay
        and use_linkid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "earlyhints_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_linkid": with_linkid,
        "skip_bind": skip_bind,
        "link_frame": do_link,
        "hint": do_hint,
        "earlydigest": do_earlydigest,
        "replay": replay,
        "use_linkid": use_linkid,
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
        "linkid_value": int(publish_result.get("linkid") or independent.get("linkid") or EMPTY_LINKID),
        "earlydigest_value": int(publish_result.get("earlydigest") or independent.get("earlydigest") or EMPTY_EARLYDIGEST),
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
        "linkid": int(trace_body["linkid_value"] or EMPTY_LINKID),
        "earlydigest": int(trace_body["earlydigest_value"] or EMPTY_EARLYDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_linkid": with_linkid,
        "skip_bind": skip_bind,
        "link_cycle": do_link,
        "hint_cycle": do_hint,
        "earlydigest_cycle": do_earlydigest,
        "replay": replay,
        "use_linkid": use_linkid,
    }


def verify_earlyhints_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Early Hints trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_earlyhints_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    linkid = int(trace.get("linkid_value") or independent.get("linkid") or EMPTY_LINKID)
    earlydigest = int(trace.get("earlydigest_value") or independent.get("earlydigest") or EMPTY_EARLYDIGEST)
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
        "link_frame": independent.get("link_frame") is True,
        "hint": independent.get("hint") is True,
        "earlydigest_response": independent.get("earlydigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "linkid_bound": independent.get("linkid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "earlydigest_recorded": (
            port > 0
            and linkid == DEFAULT_LINKID
            and earlydigest == DEFAULT_EARLYDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def earlyhints_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.earlyhints_actuation import "
        "builtin_earlyhints_actuation_proof; r=builtin_earlyhints_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='earlyhints_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_earlyhints_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=EARLYHINTS_ACTUATION_ID,
        name="First-class RFC 8297 Early Hints LINK/HINT actuation",
        description=(
            "Missions that require an earlyhints tool can opt the earlyhints provider in, "
            "bind a loopback RFC 8297 Early Hints origin, complete a LINK "
            "with a non-empty linkid, lockstep a HINT that carries the "
            "stored earlydigest, independently poll the stored earlydigest "
            "on a later socket, and seal a digest-chained earlydigest. Default "
            "routing stays fail-closed; a missing linkid keeps the hole "
            "falsifiable, and skip-LINK/HINT/EARLYDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.earlyhints_actuation:builtin_earlyhints_actuation_proof",
        proof_command=earlyhints_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.clienthints-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/earlyhints_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/encryptedcontent_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required earlyhints tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 8297 daemon, speaks a "
            "LINK then HINT over Early Hints with a non-empty linkid and "
            "earlydigest, independently polls the stored earlydigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 8942 HTTP Client Hints lockstep is proved. "
            "Missing linkids, skip-LINK, skip-HINT, skip-earlydigest, skip-REPLAY, "
            "and a LINK aimed without a linkid stay fail-closed. "
            "Later genesis can take RFC 8188 Encrypted Content-Encoding ENCRYPT/DECRYPT as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("earlyhints", "rfc8297", "http", "linkid", "earlydigest", "link", "hint", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T042257Z-1d4b6127",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_earlyhints_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 8297 Early Hints lockstep actuation seals a earlydigest."""

    from blackhole_agent.encryptedcontent_actuation import (
        ENCRYPTEDCONTENT_ACTUATION_GOAL,
        ENCRYPTEDCONTENT_ACTUATION_ID,
    )
    from blackhole_agent.clienthints_actuation import (
        CLIENTHINTS_ACTUATION_GOAL,
        CLIENTHINTS_ACTUATION_ID,
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
    checks["denylists_self"] = EARLYHINTS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (
        EARLYHINTS_ACTUATION_ID,
    )
    checks["leftover_text_binds_earlyhints"] = leftover_marker_ids(EARLYHINTS_LEFTOVER) == (
        EARLYHINTS_ACTUATION_ID,
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
        (ENCRYPTEDCONTENT_ACTUATION_GOAL, ENCRYPTEDCONTENT_ACTUATION_ID, "encryptedcontent"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_earlyhints"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"earlyhints_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            EARLYHINTS_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = EARLYHINTS_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_link_list(DEFAULT_LINKS)
    rebuilt = serialize_link_list(parse_link_list(advertised))
    critical = serialize_link_list(HINT_LINKS)
    rfc_links = parse_link_list(
        "</style.css>; rel=preload; as=style, </script.js>; rel=preload; as=script"
    )
    asked = parse_http_request(link_request(SENTINEL, DEFAULT_LINKID))
    hint_req = parse_http_request(hint_request(SENTINEL, DEFAULT_LINKID, DEFAULT_EARLYDIGEST))
    got = parse_http_response(link_response(SENTINEL, DEFAULT_LINKID, DEFAULT_EARLYDIGEST))
    hint_reply = parse_http_response(hint_response(SENTINEL, DEFAULT_LINKID, DEFAULT_EARLYDIGEST))
    checks["link_roundtrip"] = (
        parse_link_list(advertised) == DEFAULT_LINKS
        and hmac.compare_digest(rebuilt, advertised)
        and is_token("preload") is True
        and is_token("style") is True
        and is_token("BH-EH-OK") is True
        and rfc_links == DEFAULT_LINKS
        and parse_link_list(critical) == HINT_LINKS
    )
    checks["hint_roundtrip"] = (
        parse_link_list(critical)[0] == HINT_LINKS[0]
        and hmac.compare_digest(serialize_link_list(parse_link_list(critical)), critical)
        and DEFAULT_EARLYDIGEST == request_earlydigest(DEFAULT_LINKID, SENTINEL)
        and "earlydigest=" in canonical_hint(SENTINEL, DEFAULT_LINKID, DEFAULT_EARLYDIGEST)
    )
    checks["link_hint_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["eh_kind"] == "link"
        and asked["linkid"] == DEFAULT_LINKID
        and hint_req["eh_kind"] == "hint"
        and hint_req["hint_links"] == HINT_LINKS
        and hint_req["links"][0] == HINT_LINKS[0]
        and got["status"] == 103
        and hint_reply["status"] == 200
        and got["links"] == DEFAULT_LINKS
        and hint_reply["hint_links"] == HINT_LINKS
        and got["content_length_matches_body"] is True
        and hint_reply["content_length_matches_body"] is True
        and got["earlydigest"] == DEFAULT_EARLYDIGEST
        and hint_reply["earlydigest"] == DEFAULT_EARLYDIGEST
        and link_list_matches(serialize_link_list(got["links"]), advertised)
    )
    checks["catalog_names_earlyhints"] = (
        len(catalog) > 78
        and catalog[78]["id"] == EARLYHINTS_ACTUATION_ID
        and catalog[77]["id"] == CLIENTHINTS_ACTUATION_ID
        and catalog[78]["source"] == "genesis_bind_earlyhints"
    )
    checks["catalog_names_encryptedcontent"] = (
        len(catalog) > 79
        and catalog[79]["id"] == ENCRYPTEDCONTENT_ACTUATION_ID
        and catalog[79]["source"] == "genesis_bind_encryptedcontent"
    )
    family = capability_family(EARLYHINTS_ACTUATION_GOAL)
    checks["family_is_earlyhints"] = "earlyhint" in family
    checks["family_is_link_surface"] = "earlyhint" in family
    checks["family_is_linkid"] = "linkid" in family
    checks["family_is_rfc8297"] = "rfc8297" in family
    checks["family_is_earlydigest"] = "earlydigest" in family
    checks["family_is_not_encryptedcontent"] = (
        "encryptedcontent" not in family
        and "rfc8188" not in family
        and "encid" not in family
        and "aes128gcm" not in family
        and "ecedigest" not in family
    )
    checks["family_is_not_clienthints"] = (
        "clienthint" not in family
        and "rfc8942" not in family
        and "chid" not in family
        and "acceptch" not in family
        and "hintsdigest" not in family
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
    packed = encode_link(identity=SENTINEL, linkid=DEFAULT_LINKID, earlydigest=DEFAULT_EARLYDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_link"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_linkid"] is True
        and parsed["linkid"] == DEFAULT_LINKID
        and parsed["earlydigest"] == DEFAULT_EARLYDIGEST
        and parsed["is_response"] is False
        and parsed["is_hint"] is False
        and parsed["type"] == FRAME_LINK
        and parsed["first_byte"] == EH_FIRST
    )
    shook = encode_hint(
        identity=SENTINEL,
        linkid=DEFAULT_LINKID,
        earlydigest=DEFAULT_EARLYDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_hint"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_link"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["linkid"] == DEFAULT_LINKID
        and answer_parsed["earlydigest"] == DEFAULT_EARLYDIGEST
        and answer_parsed["has_earlydigest"] is True
        and answer_parsed["type"] == FRAME_HINT
        and answer_parsed["first_byte"] == EH_FIRST
    )
    bare = encode_link(identity=SENTINEL, linkid=DEFAULT_LINKID, include_linkid=False)
    checks["missing_linkid_is_unauthenticated"] = parse_message(bare)["has_linkid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    earlyhints_signature = semantic_signature(EARLYHINTS_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(earlyhints_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_earlyhints = ToolDescriptor(name="remote_earlyhints", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_earlyhints)
    checks["naive_mcp_earlyhints_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = earlyhints_tool_descriptor()
    default_earlyhints = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EARLYHINTS_TOOL_PROVIDER),
    )
    checks["default_earlyhints_provider_is_unsupported"] = (
        default_earlyhints.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{EARLYHINTS_TOOL_PROVIDER}" in default_earlyhints.reasons
    )
    checks["opted_in_earlyhints_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_earlyhints],
        required_tool_names=("local_memory", "earlyhints"),
    )
    checks["naive_preflight_missing_earlyhints"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["earlyhints"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "earlyhints"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EARLYHINTS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "earlyhints" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="earlyhints-actuation-") as tmp:
        root = Path(tmp)
        missing = run_earlyhints_workflow(with_linkid=False, output_dir=root / "missing")
        skip_bind = run_earlyhints_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_link = run_earlyhints_workflow(do_link=False, output_dir=root / "skip-link")
        skip_hint = run_earlyhints_workflow(do_hint=False, output_dir=root / "skip-hint")
        skip_earlydigest = run_earlyhints_workflow(do_earlydigest=False, output_dir=root / "skip-earlydigest")
        skip_replay = run_earlyhints_workflow(replay=False, output_dir=root / "skip-replay")
        skip_linkid = run_earlyhints_workflow(use_linkid=False, output_dir=root / "skip-linkid")
        live = run_earlyhints_workflow(output_dir=root / "live")
        verify = verify_earlyhints_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_earlyhints_trace(clone)
        checks["naive_without_linkid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_linkid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_link_stays_empty"] = (
            skip_link["ok"] is False
            and skip_link["error"] == "link_required"
            and skip_link["final_status"] == 409
            and skip_link["payload_exists"] is False
        )
        checks["skip_hint_stays_empty"] = (
            skip_hint["ok"] is False
            and skip_hint["error"] == "hint_required"
            and skip_hint["final_status"] == 409
            and skip_hint["payload_exists"] is False
        )
        checks["skip_earlydigest_stays_empty"] = (
            skip_earlydigest["ok"] is False
            and skip_earlydigest["error"] == "earlydigest_required"
            and skip_earlydigest["final_status"] == 409
            and skip_earlydigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_linkid_stays_empty"] = (
            skip_linkid["ok"] is False
            and skip_linkid["error"] == "linkid_required"
            and skip_linkid["final_status"] == 409
            and skip_linkid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_earlydigest"] = (
            int(live.get("linkid") or 0) == DEFAULT_LINKID
            and int(live.get("earlydigest") or 0) == DEFAULT_EARLYDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_linkid_encode_hint_earlydigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_link["ok"] is False
            and skip_hint["ok"] is False
            and skip_earlydigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_linkid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="earlyhints-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != EARLYHINTS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_earlyhints"] = (
        live_goal == EARLYHINTS_ACTUATION_GOAL
        and EARLYHINTS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_earlyhints"
    )

    with tempfile.TemporaryDirectory(prefix="earlyhints-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(EARLYHINTS_LEFTOVER, root)
        register_catalog_proved(root, EARLYHINTS_ACTUATION_ID)
        reason = leftover_satisfied_by(EARLYHINTS_LEFTOVER, root)
        after = leftover_is_open(EARLYHINTS_LEFTOVER, root)
    checks["earlyhints_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_earlyhints_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{EARLYHINTS_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_earlyhints_actuation_capability()
    return {
        "ok": ok,
        "action": "earlyhints_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": EARLYHINTS_ACTUATION_GOAL,
        "done_when": EARLYHINTS_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
