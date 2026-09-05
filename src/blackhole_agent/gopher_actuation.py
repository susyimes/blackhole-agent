"""Drive a first-class The Internet Gopher Protocol tool through RFC 1436 SELECTOR/MENU.

Tool routing already fails missions that require ``gopher``: hosted
gopher endpoints stay on the unsupported MCP provider, and no first-party
gopher provider is executable. Unbound therefore cannot speak a SELECTOR,
lockstep a MENU gopherid handshake over HTTP/1.0 GOPHERID,
independently poll the stored gopherdigest, or seal a gopherdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``gopher`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1436 daemon
- keep a missing-gopherid client so the gopher-gopherid hole stays falsifiable
- refuse MENU until a SELECTOR lands with a non-empty gopherid
- independently poll the stored gopherdigest on a later client socket
- persist a sealed gopherdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 1521 MIME
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
    GOPHER_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    gopher_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
GOPHER_ACTUATION_ID = "capability.gopher-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-GOPHER-OK"
POLL_TOKEN = "BH-GOPHER-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_GOPHERID = 0
EMPTY_GOPHERDIGEST = 0
GOPHER_FIRST = 0x47  # RFC 1436 GOPHER (ASCII 'G')
GOPHERID_SIZE = 4
GOPHERDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_MENU = 0x02  # RFC 1436 MENU confirmation
FRAME_SELECTOR = 0x01  # RFC 1436 SELECTOR
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
GOPHER_LEFTOVER = (
    "Later genesis can take RFC 1436 The Internet Gopher Protocol SELECTOR/MENU over a "
    "gopherid-gated gopherdigest."
)
GOPHER_ACTUATION_DONE_WHEN = (
    f"capability_exists:{GOPHER_ACTUATION_ID};"
    f"capability_proved:{GOPHER_ACTUATION_ID};"
    "no_skill_route"
)
GOPHER_ACTUATION_GOAL = (
    "Repair rfc1436 gopher selector/menu cycle cannot land over http "
    "gopher gopherid: hosted gopher endpoints remain unsupported so a SELECTOR then "
    "MENU gopherid handshake cannot land and a sealed gopherdigest "
    "cannot be produced. A missing gopher gopherid stays forbidden; fail-closed "
    "routing never opts the gopher provider in. An independent later poll of the "
    "stored gopherdigest keeps the hole falsifiable."
)


class GopherActuationError(RuntimeError):
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
# RFC 1436 sections 2.1 and 2.1.2: SELECTOR / MENU.
RFC_SELECTOR_FIELD = "SELECTOR"
RFC_MENU_FIELD = "MENU"
RFC_GOPHER_MENU = RFC_MENU_FIELD
RFC_SELECTOR_DIRECTIVE = "selector=name"
RFC_MENU_DIRECTIVE = "menu=resource"
DEFAULT_SELECTOR = "SELECTOR"
MENU_POLICY = "MENU"
SELECTOR_HEADER = "Selector"
MENU_HEADER = "Menu"
GOPHER_MENU_HEADER = MENU_HEADER
RFC_SELECTOR_PATH = "/gopher/"
RFC_SELECTOR_EMPTY = ""


def gopher_directive_pair(*, menu: bool = False) -> tuple[str, str]:
    """RFC 1436 Selector / Menu directive pair."""

    if menu:
        return "menu", "resource"
    return "selector", "name"


def ascii_serialize_gopher_directive(*, menu: bool = False) -> str:
    """RFC 1436 token "=" body-or-menu."""

    name, value = gopher_directive_pair(menu=menu)
    if not is_token(name):
        raise GopherActuationError("illegal_directive")
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
            raise GopherActuationError("short_gopher")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 1436 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_gopher(policy: str | Sequence[str]) -> str:
    """Serialize RFC 1436 SELECTOR / MENU opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise GopherActuationError("illegal_gopher")
    upper = text.upper().replace("_", "-")
    if upper in {"SELECTOR", "GOPHER", "GOPHER-SELECTOR"}:
        return "SELECTOR"
    if upper in {"MENU", "RESOURCE", "GOPHER-MENU"}:
        return "MENU"
    if upper.startswith("SELECTOR="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise GopherActuationError("illegal_gopher")
        return "SELECTOR"
    if upper.startswith("MENU="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise GopherActuationError("illegal_gopher")
        return "MENU"
    raise GopherActuationError("illegal_gopher")


def parse_gopher(text: str) -> str:
    """Parse RFC 1436 GOPHER opcode header extensions into SELECTOR or MENU."""

    raw = str(text or "").strip()
    if not raw:
        raise GopherActuationError("illegal_gopher")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"SELECTOR", "GOPHER", "GOPHER-SELECTOR"}:
        return "SELECTOR"
    if upper in {"MENU", "RESOURCE", "GOPHER-MENU"}:
        return "MENU"
    if upper.startswith("SELECTOR="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise GopherActuationError("illegal_gopher")
        return "SELECTOR"
    if upper.startswith("MENU="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise GopherActuationError("illegal_gopher")
        return "MENU"
    raise GopherActuationError("illegal_gopher")


def encode_gopher_header(policy: str | Sequence[str]) -> bytes:
    """RFC 1436 HTTP/1.0 field as bytes."""

    return serialize_gopher(policy).encode("ascii")


def parse_gopher_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_gopher(field_value) if field_value else DEFAULT_SELECTOR
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SELECTOR_HEADER,
        "directive": str(policy),
        "selector": str(policy) == "SELECTOR",
        "menu": str(policy) == "MENU",
    }


def canonical_selector(identity: str, gopherid: int) -> str:
    """RFC 1436 body-request advertisement bound to identity and gopherid."""

    return (
        f"{serialize_gopher(DEFAULT_SELECTOR)}, "
        f"selector={ascii_serialize_gopher_directive()}, "
        f"identity={identity}, gopherid={int(gopherid) & 0xFFFFFFFF}"
    )


def canonical_menu(identity: str, gopherid: int, gopherdigest: int | None = None) -> str:
    """RFC 1436 menu-resource confirmation of the stored identifier-digest."""

    digest = ""
    if gopherdigest is not None:
        digest = f", gopherdigest={int(gopherdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_gopher(MENU_POLICY)}, "
        f"menu={ascii_serialize_gopher_directive(menu=True)}, "
        f"identity={identity}, gopherid={int(gopherid) & 0xFFFFFFFF}{digest}"
    )


def representation_menu(identity: str, gopherid: int, gopherdigest: int) -> str:
    return canonical_menu(identity, gopherid, gopherdigest)


def gopher_matches(left: str, right: str) -> bool:
    return parse_gopher(left) == parse_gopher(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise GopherActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise GopherActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise GopherActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise GopherActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def selector_request(identity: str, gopherid: int) -> bytes:
    """HTTP SELECTOR that elicits RFC 1436 origin HTTP/1.0."""

    keyid = f"{int(gopherid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"SELECTOR /gopher/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Gopher-Id: {int(gopherid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def menu_request(identity: str, gopherid: int, gopherdigest: int | None = None) -> bytes:
    """HTTP SELECTOR carrying RFC 1436 menu-resource confirmation of the stored identifier-digest."""

    keyid = f"{int(gopherid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if gopherdigest is not None:
        extra = f"Gopher-Digest: {int(gopherdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"MENU /gopher/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Gopher-Id: {int(gopherid) & 0xFFFFFFFF}\r\n"
        "Menu-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    gopher_kind = "menu" if fields.get("menu-confirm") == "1" else "selector"
    upgrade_field = fields.get("selector") or fields.get("gopher") or ""
    policy = parse_gopher(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "gopher_kind": gopher_kind,
        "policy": policy,
        "gopherid": int(fields["gopher-id"]) if fields.get("gopher-id") else EMPTY_GOPHERID,
        "gopherdigest": int(fields["gopher-digest"]) if fields.get("gopher-digest") else EMPTY_GOPHERDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def selector_response(identity: str, gopherid: int, gopherdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 1436 origin HTTP/1.0, carrying the stored gopherdigest."""

    advertised = serialize_gopher(DEFAULT_SELECTOR)
    payload = bytes(body or canonical_selector(identity, gopherid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Selector: {advertised}\r\n"
        f"Gopher-Id: {int(gopherid) & 0xFFFFFFFF}\r\n"
        f"Gopher-Digest: {int(gopherdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def menu_response(identity: str, gopherid: int, gopherdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 1436 MENU, carrying the stored identifier-digest."""

    advertised = serialize_gopher(MENU_POLICY)
    payload = bytes(body or representation_menu(identity, gopherid, gopherdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Selector: {advertised}\r\n"
        f"Gopher-Id: {int(gopherid) & 0xFFFFFFFF}\r\n"
        f"Gopher-Digest: {int(gopherdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/gopher-menu\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise GopherActuationError("illegal_content_length") from error
    field_value = fields.get("selector") or fields.get("gopher") or ""
    policy = parse_gopher(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/gopher-menu" or policy == MENU_POLICY:
        status = 200
        gopher_kind = "menu"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        gopher_kind = "selector"
    else:
        status = 0
        gopher_kind = "selector"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "gopher_kind": gopher_kind,
        "policy": policy,
        "gopherid": int(fields["gopher-id"]) if fields.get("gopher-id") else EMPTY_GOPHERID,
        "gopherdigest": int(fields["gopher-digest"]) if fields.get("gopher-digest") else EMPTY_GOPHERDIGEST,
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
        raise GopherActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise GopherActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise GopherActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise GopherActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc1436_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    gopher: str,
) -> str:
    """RFC 1436 identifier digest over method, request-GOPHER, identity, and gopherid."""

    payload = f"{method}:{gopher}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_gopherid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"gopherid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_gopherid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-gopherid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_gopherdigest(gopherid: int = EMPTY_GOPHERID, token: str = SENTINEL) -> int:
    nonce = f"{int(gopherid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc1436_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="MENU",
        gopher=f"/gopher/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_GOPHERID = request_gopherid(SENTINEL)
DEFAULT_GOPHERDIGEST = request_gopherdigest(DEFAULT_GOPHERID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    gopherid: int,
    gopherdigest: int,
    include_gopherid: bool = True,
) -> bytes:
    live_gopherid = int(gopherid) & 0xFFFFFFFF if include_gopherid else EMPTY_GOPHERID
    live_digest = int(gopherdigest) & 0xFFFFFFFF if include_gopherid and live_gopherid else EMPTY_GOPHERDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_gopherid) if live_gopherid else b""
    header = bytearray()
    header.append(GOPHER_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_selector(
    *,
    identity: str,
    gopherid: int,
    gopherdigest: int | None = None,
    include_gopherid: bool = True,
) -> bytes:
    live_gopherid = int(gopherid) & 0xFFFFFFFF if include_gopherid else EMPTY_GOPHERID
    live_digest = int(gopherdigest) if gopherdigest is not None else request_gopherdigest(live_gopherid, identity)
    return encode_packet(
        FRAME_SELECTOR,
        identity=identity,
        gopherid=live_gopherid,
        gopherdigest=live_digest,
        include_gopherid=include_gopherid,
    )


def encode_menu(
    *,
    identity: str,
    gopherid: int,
    gopherdigest: int | None = None,
    include_gopherid: bool = True,
) -> bytes:
    live_gopherid = int(gopherid) & 0xFFFFFFFF if include_gopherid else EMPTY_GOPHERID
    live_digest = int(gopherdigest) if gopherdigest is not None else request_gopherdigest(live_gopherid, identity)
    return encode_packet(
        FRAME_MENU,
        identity=identity,
        gopherid=live_gopherid,
        gopherdigest=live_digest,
        include_gopherid=include_gopherid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise GopherActuationError("short_packet")
    first = raw[0]
    if first != GOPHER_FIRST:
        raise GopherActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise GopherActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == GOPHERID_SIZE:
        live_gopherid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_gopherid = EMPTY_GOPHERID
    else:
        raise GopherActuationError("illegal_gopherid")
    if offset >= len(raw):
        raise GopherActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SELECTOR, FRAME_MENU}:
        raise GopherActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise GopherActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise GopherActuationError("checksum_failed")
    if len(payload) < 5:
        raise GopherActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise GopherActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_gopherid = int(live_gopherid) != EMPTY_GOPHERID
    has_gopherdigest = has_gopherid and int(live_digest) != EMPTY_GOPHERDIGEST
    is_selector = frame_type == FRAME_SELECTOR
    is_menu = frame_type == FRAME_MENU
    return {
        "type": int(frame_type),
        "is_selector": is_selector,
        "is_menu": is_menu,
        "gopherid": int(live_gopherid),
        "has_gopherid": has_gopherid,
        "gopherdigest": int(live_digest),
        "has_gopherdigest": has_gopherdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC1436",
        "serialize_field": canonical_selector(identity, live_gopherid) if has_gopherid else "",
        "tls_field": canonical_menu(identity, live_gopherid, live_digest) if has_gopherdigest else "",
    }


class GopherClient:
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
            raise GopherActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_menu"] or not packet["is_menu"]:
            raise GopherActuationError("gopherdigest_required")
        if not packet["has_gopherid"]:
            raise GopherActuationError("gopherid_required")
        if not packet["has_gopherdigest"]:
            raise GopherActuationError("gopherdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_gopherdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_gopherdigest:
            raise GopherActuationError("gopherdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "gopherid": int(reply.get("gopherid") or EMPTY_GOPHERID),
            "identity": str(reply.get("identity") or ""),
            "gopherdigest": int(reply.get("gopherdigest") or EMPTY_GOPHERDIGEST),
        }

    def report(
        self,
        identity: str,
        gopherid: int,
        gopherdigest: int = EMPTY_GOPHERDIGEST,
        *,
        wait_gopherdigest: bool = True,
        include_gopherid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_menu(
            identity=identity,
            gopherid=gopherid,
            gopherdigest=gopherdigest or request_gopherdigest(gopherid, identity),
            include_gopherid=include_gopherid,
        )
        return self.exchange(packet, wait_gopherdigest=wait_gopherdigest)


class GopherSession:
    """GOPHERID-gated loopback RFC 1436 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        gopherid_gate: int = DEFAULT_GOPHERID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.gopherid_gate = int(gopherid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.gopherid = EMPTY_GOPHERID
        self.gopherdigest = EMPTY_GOPHERDIGEST
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

    def store_gopherid_once(self, identity: str, gopherid: int, gopherdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(gopherid or EMPTY_GOPHERID)
            live_digest = int(gopherdigest or EMPTY_GOPHERDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.gopherid = live
                self.gopherdigest = live_digest or request_gopherdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.gopherid), int(self.gopherdigest)

    def read_gopherid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.gopherid), int(self.gopherdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "gopherid": EMPTY_GOPHERID,
            "gopherdigest": EMPTY_GOPHERDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _gopherid_missing(self) -> bool:
        return not int(self.gopherid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, gopherid: int, gopherdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_menu(
            identity=identity,
            gopherid=gopherid,
            gopherdigest=gopherdigest,
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
            except GopherActuationError:
                continue
            if not packet.get("is_selector") and not packet.get("is_menu"):
                continue
            if not packet.get("has_gopherid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_gopherid, stored_digest = self.store_gopherid_once(
                identity,
                int(packet.get("gopherid") or EMPTY_GOPHERID),
                int(packet.get("gopherdigest") or EMPTY_GOPHERDIGEST),
            )
            if not stored_name or not stored_gopherid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_selector"):
                    self.opened = True
                if packet.get("is_menu"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_gopherid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._gopherid_missing():
            return self._forbidden("missing_gopherid")
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
        do_selector: bool = True,
        do_menu: bool = True,
        do_gopherdigest: bool = True,
        replay: bool = True,
        use_gopherid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._gopherid_missing():
            return self._forbidden("missing_gopherid")
        live_token = str(token or SENTINEL)
        origin_gopherid = request_gopherid(live_token)
        origin_digest = request_gopherdigest(origin_gopherid, live_token)
        client: GopherClient | None = None
        independent: GopherClient | None = None
        try:
            client = GopherClient(self.host, int(self.port))
            if not do_selector:
                return self._conflict("selector_required")
            bind_packet = encode_selector(
                identity=live_token,
                gopherid=origin_gopherid,
                gopherdigest=origin_digest,
                include_gopherid=use_gopherid,
            )
            if not use_gopherid:
                try:
                    client.exchange(bind_packet, wait_gopherdigest=True)
                except GopherActuationError:
                    return self._conflict("gopherid_required")
                return self._conflict("gopherid_required")
            client.send(bind_packet)
            if not do_menu:
                return self._conflict("menu_required")
            proxy_packet = encode_menu(
                identity=live_token,
                gopherid=origin_gopherid,
                gopherdigest=origin_digest,
                include_gopherid=True,
            )
            if not do_gopherdigest:
                try:
                    client.exchange(proxy_packet, wait_gopherdigest=False)
                except GopherActuationError as error:
                    if str(error) == "gopherdigest_required":
                        return self._conflict("gopherdigest_required")
                    return self._conflict("gopherdigest_required")
                return self._conflict("gopherdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_gopherdigest=True)
            except GopherActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("gopherid_required")
                if reason == "gopherdigest_required":
                    return self._conflict("gopherdigest_required")
                return self._conflict("selector_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("selector_required")
            if int(reply.get("gopherid") or EMPTY_GOPHERID) != origin_gopherid:
                return self._conflict("gopherdigest_required")
            if int(reply.get("gopherdigest") or EMPTY_GOPHERDIGEST) != origin_digest:
                return self._conflict("gopherdigest_required")
            self.retrieved = True
            if replay:
                independent = GopherClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_gopherid(live_token),
                        request_gopherdigest(poll_gopherid(live_token), POLL_TOKEN),
                        wait_gopherdigest=True,
                    )
                except GopherActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_gopherid, stored_digest = self.read_gopherid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_gopherid != origin_gopherid
                    or stored_digest != origin_digest
                    or int(poll.get("gopherid") or EMPTY_GOPHERID) != origin_gopherid
                    or int(poll.get("gopherdigest") or EMPTY_GOPHERDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_gopherid}:{origin_digest}:{live_token}:{canonical_selector(live_token, origin_gopherid)}:{canonical_menu(live_token, origin_gopherid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "gopherid": origin_gopherid,
                "gopherdigest": origin_digest,
                "selector_frame": True,
                "menu_frame": True,
                "gopherdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "gopherid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_gopherdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "gopherid": origin_gopherid,
                "gopherdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "selector_frame": True,
                "menu_frame": True,
                "gopherdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "gopherid_bound": True,
            }
        except (OSError, GopherActuationError) as error:
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
        live = independent_gopherdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "gopherid": int(live.get("gopherid") or EMPTY_GOPHERID),
            "gopherdigest": int(live.get("gopherdigest") or EMPTY_GOPHERDIGEST),
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


def call_gopher_tool(session: GopherSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one gopher tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_selector = True if arguments.get("selector") is None else bool(arguments.get("selector"))
    do_menu = True if arguments.get("menu") is None else bool(arguments.get("menu"))
    do_gopherdigest = True if arguments.get("gopherdigest") is None else bool(arguments.get("gopherdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_gopherid = True if arguments.get("use_gopherid") is None else bool(arguments.get("use_gopherid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_selector=do_selector,
            do_menu=do_menu,
            do_gopherdigest=do_gopherdigest,
            replay=replay,
            use_gopherid=use_gopherid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise GopherActuationError(f"unsupported gopher action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_gopherdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage gopherdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "gopherid": EMPTY_GOPHERID,
        "gopherdigest": EMPTY_GOPHERDIGEST,
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
            "selector_frame",
            "menu_frame",
            "gopherdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "gopherid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    gopherid = int(payload.get("gopherid") or EMPTY_GOPHERID)
    gopherdigest = int(payload.get("gopherdigest") or EMPTY_GOPHERDIGEST)
    dual = port > 0 and bool(gopherid) and bool(gopherdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "gopherid": gopherid,
        "gopherdigest": gopherdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "selector_frame": payload.get("selector_frame") is True,
        "menu_frame": payload.get("menu_frame") is True,
        "gopherdigest_locate": payload.get("gopherdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "gopherid_bound": payload.get("gopherid_bound") is True,
    }


def run_gopher_workflow(
    *,
    with_gopherid: bool = True,
    skip_bind: bool = False,
    do_selector: bool = True,
    do_menu: bool = True,
    do_gopherdigest: bool = True,
    replay: bool = True,
    use_gopherid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1436 SELECTOR/MENU gopherid cycle workflow."""

    descriptor = gopher_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GOPHER_TOOL_PROVIDER),
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
        raise GopherActuationError(f"gopher tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="gopher-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = GopherSession(out, gopherid_gate=DEFAULT_GOPHERID if with_gopherid else EMPTY_GOPHERID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "selector": do_selector,
            "menu": do_menu,
            "gopherdigest": do_gopherdigest,
            "replay": replay,
            "use_gopherid": use_gopherid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_gopher_tool(session, arguments))
            except GopherActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_gopherdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_gopherid
        and not skip_bind
        and do_selector
        and do_menu
        and do_gopherdigest
        and replay
        and use_gopherid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "gopher_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_gopherid": with_gopherid,
        "skip_bind": skip_bind,
        "selector_frame": do_selector,
        "menu_frame": do_menu,
        "gopherdigest": do_gopherdigest,
        "replay": replay,
        "use_gopherid": use_gopherid,
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
        "gopherid_value": int(publish_result.get("gopherid") or independent.get("gopherid") or EMPTY_GOPHERID),
        "gopherdigest_value": int(publish_result.get("gopherdigest") or independent.get("gopherdigest") or EMPTY_GOPHERDIGEST),
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
        "gopherid": int(trace_body["gopherid_value"] or EMPTY_GOPHERID),
        "gopherdigest": int(trace_body["gopherdigest_value"] or EMPTY_GOPHERDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_gopherid": with_gopherid,
        "skip_bind": skip_bind,
        "selector_cycle": do_selector,
        "menu_cycle": do_menu,
        "gopherdigest_cycle": do_gopherdigest,
        "replay": replay,
        "use_gopherid": use_gopherid,
    }


def verify_gopher_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_gopherdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    gopherid = int(trace.get("gopherid_value") or independent.get("gopherid") or EMPTY_GOPHERID)
    gopherdigest = int(trace.get("gopherdigest_value") or independent.get("gopherdigest") or EMPTY_GOPHERDIGEST)
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
        "selector_frame": independent.get("selector_frame") is True,
        "menu_frame": independent.get("menu_frame") is True,
        "gopherdigest_locate": independent.get("gopherdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "gopherid_bound": independent.get("gopherid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "gopherdigest_recorded": (
            port > 0
            and gopherid == DEFAULT_GOPHERID
            and gopherdigest == DEFAULT_GOPHERDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def gopher_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.gopher_actuation import "
        "builtin_gopher_actuation_proof; r=builtin_gopher_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='gopher_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_gopher_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=GOPHER_ACTUATION_ID,
        name="First-class RFC 1436 The Internet Gopher Protocol SELECTOR/MENU actuation",
        description=(
            "Missions that require a gopher tool can opt the gopher provider in, "
            "bind a loopback RFC 1436 The Internet Gopher Protocol endpoint, complete a SELECTOR "
            "with a non-empty gopherid, lockstep a MENU that carries the "
            "stored gopherdigest, independently poll the stored gopherdigest "
            "on a later socket, and seal a digest-chained gopherdigest. Default "
            "routing stays fail-closed; a missing gopherid keeps the hole "
            "falsifiable, and skip-SELECTOR/MENU/GOPHERDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.gopher_actuation:builtin_gopher_actuation_proof",
        proof_command=gopher_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mime-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/gopher_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/mime_actuation.py",
            "src/blackhole_agent/finger_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required gopher tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 1436 daemon, speaks a "
            "SELECTOR then MENU over The Internet Gopher Protocol with a non-empty gopherid and "
            "gopherdigest, independently polls the stored gopherdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 1521 MIME lockstep is proved. "
            "Missing gopherids, skip-SELECTOR, skip-MENU, skip-gopherdigest, skip-REPLAY, "
            "and a SELECTOR aimed without a gopherid stay fail-closed. "
            "Later genesis can take RFC 1288 The Finger User Information Protocol QUERY/USER as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("gopher", "rfc1436", "http", "gopherid", "gopherdigest", "selector", "menu", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T070029Z-905df7d4",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_gopher_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1436 selector/menu lockstep actuation seals a gopherdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
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
    checks["denylists_self"] = GOPHER_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(GOPHER_ACTUATION_GOAL) == (
        GOPHER_ACTUATION_ID,
    )
    checks["leftover_text_binds_gopher"] = leftover_marker_ids(GOPHER_LEFTOVER) == (
        GOPHER_ACTUATION_ID,
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
        checks[f"{name}_goal_is_not_gopher"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"gopher_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            GOPHER_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = GOPHER_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_gopher(DEFAULT_SELECTOR)
    rebuilt = serialize_gopher(parse_gopher(advertised))
    preloaded = parse_gopher(RFC_GOPHER_MENU)
    header = encode_gopher_header(DEFAULT_SELECTOR)
    parsed_header = parse_gopher_header(header)
    asked = parse_http_request(selector_request(SENTINEL, DEFAULT_GOPHERID))
    preload_req = parse_http_request(menu_request(SENTINEL, DEFAULT_GOPHERID, DEFAULT_GOPHERDIGEST))
    got = parse_http_response(selector_response(SENTINEL, DEFAULT_GOPHERID, DEFAULT_GOPHERDIGEST))
    preload_reply = parse_http_response(
        menu_response(SENTINEL, DEFAULT_GOPHERID, DEFAULT_GOPHERDIGEST)
    )
    checks["gopher_roundtrip"] = (
        parse_gopher(advertised) == DEFAULT_SELECTOR
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_SELECTOR_FIELD
        and is_token("SELECTOR") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SELECTOR_FIELD
        and parsed_header["policy"] == DEFAULT_SELECTOR
        and parsed_header["header"] == SELECTOR_HEADER
        and parsed_header["selector"] is True
        and parsed_header["menu"] is False
        and preloaded == MENU_POLICY
        and ascii_serialize_gopher_directive() == RFC_SELECTOR_DIRECTIVE
        and gopher_directive_pair() == ("selector", "name")
        and RFC_SELECTOR_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_gopher(MENU_POLICY) == RFC_GOPHER_MENU
        and DEFAULT_GOPHERDIGEST == request_gopherdigest(DEFAULT_GOPHERID, SENTINEL)
        and "gopherdigest=" in canonical_menu(SENTINEL, DEFAULT_GOPHERID, DEFAULT_GOPHERDIGEST)
        and canonical_selector(SENTINEL, DEFAULT_GOPHERID).startswith("SELECTOR")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "SELECTOR"
        and asked["gopher_kind"] == "selector"
        and asked["gopherid"] == DEFAULT_GOPHERID
        and preload_req["gopher_kind"] == "menu"
        and preload_req["gopherdigest"] == DEFAULT_GOPHERDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["gopher_kind"] == "selector"
        and preload_reply["gopher_kind"] == "menu"
        and got["policy"] == DEFAULT_SELECTOR
        and preload_reply["policy"] == MENU_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["gopherdigest"] == DEFAULT_GOPHERDIGEST
        and preload_reply["gopherdigest"] == DEFAULT_GOPHERDIGEST
        and gopher_matches(serialize_gopher(got["policy"]), advertised)
    )

    checks["catalog_names_gopher"] = (
        len(catalog) > 107
        and catalog[107]["id"] == GOPHER_ACTUATION_ID
        and catalog[106]["id"] == MIME_ACTUATION_ID
        and catalog[107]["source"] == "genesis_bind_gopher"
    )
    checks["catalog_names_finger"] = (
        len(catalog) > 108
        and catalog[108]["id"] == FINGER_ACTUATION_ID
        and catalog[108]["source"] == "genesis_bind_finger"
    )
    family = capability_family(GOPHER_ACTUATION_GOAL)
    checks["family_is_gopher"] = "gopher" in family
    checks["family_is_gopher_surface"] = "gopher" in family
    checks["family_is_gopherid"] = "gopherid" in family
    checks["family_is_rfc1436"] = "rfc1436" in family
    checks["family_is_gopherdigest"] = "gopherdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
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
    packed = encode_selector(identity=SENTINEL, gopherid=DEFAULT_GOPHERID, gopherdigest=DEFAULT_GOPHERDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_selector"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_gopherid"] is True
        and parsed["gopherid"] == DEFAULT_GOPHERID
        and parsed["gopherdigest"] == DEFAULT_GOPHERDIGEST
        and parsed["is_menu"] is False
        and parsed["is_menu"] is False
        and parsed["type"] == FRAME_SELECTOR
        and parsed["first_byte"] == GOPHER_FIRST
    )
    shook = encode_menu(
        identity=SENTINEL,
        gopherid=DEFAULT_GOPHERID,
        gopherdigest=DEFAULT_GOPHERDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_menu"] is True
        and answer_parsed["is_menu"] is True
        and answer_parsed["is_selector"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["gopherid"] == DEFAULT_GOPHERID
        and answer_parsed["gopherdigest"] == DEFAULT_GOPHERDIGEST
        and answer_parsed["has_gopherdigest"] is True
        and answer_parsed["type"] == FRAME_MENU
        and answer_parsed["first_byte"] == GOPHER_FIRST
    )
    bare = encode_selector(identity=SENTINEL, gopherid=DEFAULT_GOPHERID, include_gopherid=False)
    checks["missing_gopherid_is_unauthed"] = parse_message(bare)["has_gopherid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(GOPHER_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_gopher = ToolDescriptor(name="remote_gopher", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_gopher)
    checks["naive_mcp_gopher_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = gopher_tool_descriptor()
    default_gopher = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GOPHER_TOOL_PROVIDER),
    )
    checks["default_gopher_provider_is_unsupported"] = (
        default_gopher.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{GOPHER_TOOL_PROVIDER}" in default_gopher.reasons
    )
    checks["opted_in_gopher_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_gopher],
        required_tool_names=("local_memory", "gopher"),
    )
    checks["naive_preflight_missing_gopher"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["gopher"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "gopher"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GOPHER_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "gopher" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="gopher-actuation-") as tmp:
        root = Path(tmp)
        missing = run_gopher_workflow(with_gopherid=False, output_dir=root / "missing")
        skip_bind = run_gopher_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_selector = run_gopher_workflow(do_selector=False, output_dir=root / "skip-selector")
        skip_menu = run_gopher_workflow(do_menu=False, output_dir=root / "skip-menu")
        skip_gopherdigest = run_gopher_workflow(do_gopherdigest=False, output_dir=root / "skip-gopherdigest")
        skip_replay = run_gopher_workflow(replay=False, output_dir=root / "skip-replay")
        skip_gopherid = run_gopher_workflow(use_gopherid=False, output_dir=root / "skip-gopherid")
        live = run_gopher_workflow(output_dir=root / "live")
        verify = verify_gopher_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_gopher_trace(clone)
        checks["naive_without_gopherid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_gopherid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_selector_stays_empty"] = (
            skip_selector["ok"] is False
            and skip_selector["error"] == "selector_required"
            and skip_selector["final_status"] == 409
            and skip_selector["payload_exists"] is False
        )
        checks["skip_menu_stays_empty"] = (
            skip_menu["ok"] is False
            and skip_menu["error"] == "menu_required"
            and skip_menu["final_status"] == 409
            and skip_menu["payload_exists"] is False
        )
        checks["skip_gopherdigest_stays_empty"] = (
            skip_gopherdigest["ok"] is False
            and skip_gopherdigest["error"] == "gopherdigest_required"
            and skip_gopherdigest["final_status"] == 409
            and skip_gopherdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_gopherid_stays_empty"] = (
            skip_gopherid["ok"] is False
            and skip_gopherid["error"] == "gopherid_required"
            and skip_gopherid["final_status"] == 409
            and skip_gopherid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_gopherdigest"] = (
            int(live.get("gopherid") or 0) == DEFAULT_GOPHERID
            and int(live.get("gopherdigest") or 0) == DEFAULT_GOPHERDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_gopherid_encode_menu_gopherdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_selector["ok"] is False
            and skip_menu["ok"] is False
            and skip_gopherdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_gopherid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="gopher-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != GOPHER_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_gopher"] = (
        live_goal == GOPHER_ACTUATION_GOAL
        and GOPHER_ACTUATION_ID in live_done
        and live_source == "genesis_bind_gopher"
    )

    with tempfile.TemporaryDirectory(prefix="gopher-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(GOPHER_LEFTOVER, root)
        register_catalog_proved(root, GOPHER_ACTUATION_ID)
        reason = leftover_satisfied_by(GOPHER_LEFTOVER, root)
        after = leftover_is_open(GOPHER_LEFTOVER, root)
    checks["gopher_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_gopher_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{GOPHER_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_gopher_actuation_capability()
    return {
        "ok": ok,
        "action": "gopher_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": GOPHER_ACTUATION_GOAL,
        "done_when": GOPHER_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
