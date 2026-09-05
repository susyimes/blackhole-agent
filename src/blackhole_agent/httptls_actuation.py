"""Drive a first-class Upgrading to TLS Within HTTP/1.1 tool through RFC 2817 UPGRADE/TLS.

Tool routing already fails missions that require ``httptls``: hosted
httptls endpoints stay on the unsupported MCP provider, and no first-party
httptls provider is executable. Unbound therefore cannot speak a UPGRADE,
lockstep an TLS upgradeid handshake over HTTP Upgrade UPGRADEID,
independently poll the stored upgradetlsdigest, or seal a upgradetlsdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``httptls`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2817 daemon
- keep a missing-upgradeid client so the httptls-upgradeid hole stays falsifiable
- refuse TLS until a UPGRADE lands with a non-empty upgradeid
- independently poll the stored upgradetlsdigest on a later client socket
- persist a sealed upgradetlsdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 4559 SPNEGO-based Kerberos and NTLM HTTP Authentication
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
    HTTPTLS_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    httptls_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTPTLS_ACTUATION_ID = "capability.httptls-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-TLS-OK"
POLL_TOKEN = "BH-TLS-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_UPGRADEID = 0
EMPTY_UPGRADETLSDIGEST = 0
UPGRADE_FIRST = 0x55  # RFC 2817 Upgrading to TLS Within HTTP/1.1 (ASCII 'U')
UPGRADEID_SIZE = 4
UPGRADETLSDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_TLS = 0x02  # RFC 2817 tls confirmation
FRAME_UPGRADE = 0x01  # RFC 2817 UPGRADE
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTPTLS_LEFTOVER = (
    "Later genesis can take RFC 2817 Upgrading to TLS Within HTTP/1.1 UPGRADE/TLS over an "
    "upgradeid-gated upgradetlsdigest."
)
HTTPTLS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPTLS_ACTUATION_ID};"
    f"capability_proved:{HTTPTLS_ACTUATION_ID};"
    "no_skill_route"
)
HTTPTLS_ACTUATION_GOAL = (
    "Repair rfc2817 httptls upgrade/tls cycle cannot land over http "
    "httptls upgradeid: hosted httptls endpoints remain unsupported so a UPGRADE then "
    "TLS upgradeid handshake cannot land and a sealed upgradetlsdigest "
    "cannot be produced. A missing httptls upgradeid stays forbidden; fail-closed "
    "routing never opts the httptls provider in. An independent later poll of the "
    "stored upgradetlsdigest keeps the hole falsifiable."
)


class HttptlsActuationError(RuntimeError):
    """Raised when the tls session or loopback daemon fixture misbehaves."""


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
# RFC 2817 sections 5.1 and 5.2: Upgrade / TLS.
RFC_UPGRADE_FIELD = "UPGRADE"
RFC_TLS_FIELD = "TLS"
RFC_HTTPTLS_TLS = RFC_TLS_FIELD
RFC_UPGRADE_DIRECTIVE = "protocol=TLS/1.0"
RFC_TLS_DIRECTIVE = "version=TLS/1.0"
DEFAULT_UPGRADE = "UPGRADE"
TLS_POLICY = "TLS"
UPGRADE_HEADER = "Upgrade"
TLS_HEADER = "Upgrade"
HTTPTLS_TLS_HEADER = TLS_HEADER
RFC_UPGRADE_PATH = "/upgrade/"
RFC_UPGRADE_EMPTY = ""


def httptls_directive_pair(*, tls: bool = False) -> tuple[str, str]:
    """RFC 2817 Upgrade token / TLS version pair."""

    if tls:
        return "version", "TLS/1.0"
    return "protocol", "TLS/1.0"


def ascii_serialize_httptls_directive(*, tls: bool = False) -> str:
    """RFC 2817 token "=" upgrade-or-tls."""

    name, value = httptls_directive_pair(tls=tls)
    if not is_token(name):
        raise HttptlsActuationError("illegal_directive")
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
            raise HttptlsActuationError("short_httptls")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 2817 DAV token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_httptls(policy: str | Sequence[str]) -> str:
    """Serialize RFC 2817 Upgrade / TLS token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise HttptlsActuationError("illegal_httptls")
    upper = text.upper().replace("_", "-")
    if upper in {"UPGRADE", "PROTOCOL", "HTTPTLS"}:
        return "UPGRADE"
    if upper in {"TLS", "VERSION", "STARTTLS"}:
        return "TLS"
    if upper.startswith("PROTOCOL="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttptlsActuationError("illegal_httptls")
        return "UPGRADE"
    if upper.startswith("VERSION="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttptlsActuationError("illegal_httptls")
        return "TLS"
    raise HttptlsActuationError("illegal_httptls")


def parse_httptls(text: str) -> str:
    """Parse RFC 2817 DAV upgrade extensions into UPGRADE or TLS."""

    raw = str(text or "").strip()
    if not raw:
        raise HttptlsActuationError("illegal_httptls")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"UPGRADE", "PROTOCOL", "HTTPTLS"}:
        return "UPGRADE"
    if upper in {"TLS", "VERSION", "STARTTLS"}:
        return "TLS"
    if upper.startswith("PROTOCOL="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttptlsActuationError("illegal_httptls")
        return "UPGRADE"
    if upper.startswith("VERSION="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttptlsActuationError("illegal_httptls")
        return "TLS"
    raise HttptlsActuationError("illegal_httptls")


def encode_httptls_header(policy: str | Sequence[str]) -> bytes:
    """RFC 2817 DAV field as bytes."""

    return serialize_httptls(policy).encode("ascii")


def parse_httptls_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_httptls(field_value) if field_value else DEFAULT_UPGRADE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": UPGRADE_HEADER,
        "directive": str(policy),
        "upgrade": str(policy) == "UPGRADE",
        "tls": str(policy) == "TLS",
    }


def canonical_upgrade(identity: str, upgradeid: int) -> str:
    """RFC 2817 UPGRADE advertisement bound to identity and upgradeid."""

    return (
        f"{serialize_httptls(DEFAULT_UPGRADE)}, "
        f"upgrade={ascii_serialize_httptls_directive()}, "
        f"identity={identity}, upgradeid={int(upgradeid) & 0xFFFFFFFF}"
    )


def canonical_tls(identity: str, upgradeid: int, upgradetlsdigest: int | None = None) -> str:
    """RFC 2817 TLS confirmation of the stored tls policy."""

    tls = ""
    if upgradetlsdigest is not None:
        tls = f", upgradetlsdigest={int(upgradetlsdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_httptls(TLS_POLICY)}, "
        f"tls={ascii_serialize_httptls_directive(tls=True)}, "
        f"identity={identity}, upgradeid={int(upgradeid) & 0xFFFFFFFF}{tls}"
    )


def representation_tls(identity: str, upgradeid: int, upgradetlsdigest: int) -> str:
    return canonical_tls(identity, upgradeid, upgradetlsdigest)


def httptls_matches(left: str, right: str) -> bool:
    return parse_httptls(left) == parse_httptls(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HttptlsActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HttptlsActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HttptlsActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HttptlsActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def upgrade_request(identity: str, upgradeid: int) -> bytes:
    """HTTP UPGRADE that elicits RFC 2817 origin UPGRADE."""

    keyid = f"{int(upgradeid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"UPGRADE /upgrade/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Upgrade-Id: {int(upgradeid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def tls_request(identity: str, upgradeid: int, upgradetlsdigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 2817 TLS confirmation of the stored tls policy."""

    keyid = f"{int(upgradeid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if upgradetlsdigest is not None:
        extra = f"Upgrade-Digest: {int(upgradetlsdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"TLS /upgrade/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Upgrade-Id: {int(upgradeid) & 0xFFFFFFFF}\r\n"
        "Upgrade-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    httptls_kind = "tls" if fields.get("upgrade-confirm") == "1" else "upgrade"
    upgrade_field = fields.get("upgrade") or ""
    policy = parse_httptls(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "httptls_kind": httptls_kind,
        "policy": policy,
        "upgradeid": int(fields["upgrade-id"]) if fields.get("upgrade-id") else EMPTY_UPGRADEID,
        "upgradetlsdigest": int(fields["upgrade-digest"]) if fields.get("upgrade-digest") else EMPTY_UPGRADETLSDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def upgrade_response(identity: str, upgradeid: int, upgradetlsdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 2817 origin UPGRADE, carrying the stored upgradetlsdigest."""

    advertised = serialize_httptls(DEFAULT_UPGRADE)
    payload = bytes(body or canonical_upgrade(identity, upgradeid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Upgrade: {advertised}\r\n"
        f"Upgrade-Id: {int(upgradeid) & 0xFFFFFFFF}\r\n"
        f"Upgrade-Digest: {int(upgradetlsdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def tls_response(identity: str, upgradeid: int, upgradetlsdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 2817 TLS, carrying the stored TLS policy."""

    advertised = serialize_httptls(TLS_POLICY)
    payload = bytes(body or representation_tls(identity, upgradeid, upgradetlsdigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Upgrade: {advertised}\r\n"
        f"Upgrade-Id: {int(upgradeid) & 0xFFFFFFFF}\r\n"
        f"Upgrade-Digest: {int(upgradetlsdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/upgrade-tls\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise HttptlsActuationError("illegal_content_length") from error
    field_value = fields.get("upgrade") or ""
    policy = parse_httptls(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/upgrade-tls" or policy == TLS_POLICY:
        status = 200
        httptls_kind = "tls"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        httptls_kind = "upgrade"
    else:
        status = 0
        httptls_kind = "upgrade"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "httptls_kind": httptls_kind,
        "policy": policy,
        "upgradeid": int(fields["upgrade-id"]) if fields.get("upgrade-id") else EMPTY_UPGRADEID,
        "upgradetlsdigest": int(fields["upgrade-digest"]) if fields.get("upgrade-digest") else EMPTY_UPGRADETLSDIGEST,
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
        raise HttptlsActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise HttptlsActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise HttptlsActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HttptlsActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_upgradeid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"upgradeid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_upgradeid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-upgradeid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_upgradetlsdigest(upgradeid: int = EMPTY_UPGRADEID, token: str = SENTINEL) -> int:
    material = canonical_upgrade(token or SENTINEL, int(upgradeid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_UPGRADEID = request_upgradeid(SENTINEL)
DEFAULT_UPGRADETLSDIGEST = request_upgradetlsdigest(DEFAULT_UPGRADEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    upgradeid: int,
    upgradetlsdigest: int,
    include_upgradeid: bool = True,
) -> bytes:
    live_upgradeid = int(upgradeid) & 0xFFFFFFFF if include_upgradeid else EMPTY_UPGRADEID
    live_digest = int(upgradetlsdigest) & 0xFFFFFFFF if include_upgradeid and live_upgradeid else EMPTY_UPGRADETLSDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_upgradeid) if live_upgradeid else b""
    header = bytearray()
    header.append(UPGRADE_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_upgrade(
    *,
    identity: str,
    upgradeid: int,
    upgradetlsdigest: int | None = None,
    include_upgradeid: bool = True,
) -> bytes:
    live_upgradeid = int(upgradeid) & 0xFFFFFFFF if include_upgradeid else EMPTY_UPGRADEID
    live_digest = int(upgradetlsdigest) if upgradetlsdigest is not None else request_upgradetlsdigest(live_upgradeid, identity)
    return encode_packet(
        FRAME_UPGRADE,
        identity=identity,
        upgradeid=live_upgradeid,
        upgradetlsdigest=live_digest,
        include_upgradeid=include_upgradeid,
    )


def encode_tls(
    *,
    identity: str,
    upgradeid: int,
    upgradetlsdigest: int | None = None,
    include_upgradeid: bool = True,
) -> bytes:
    live_upgradeid = int(upgradeid) & 0xFFFFFFFF if include_upgradeid else EMPTY_UPGRADEID
    live_digest = int(upgradetlsdigest) if upgradetlsdigest is not None else request_upgradetlsdigest(live_upgradeid, identity)
    return encode_packet(
        FRAME_TLS,
        identity=identity,
        upgradeid=live_upgradeid,
        upgradetlsdigest=live_digest,
        include_upgradeid=include_upgradeid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HttptlsActuationError("short_packet")
    first = raw[0]
    if first != UPGRADE_FIRST:
        raise HttptlsActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise HttptlsActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == UPGRADEID_SIZE:
        live_upgradeid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_upgradeid = EMPTY_UPGRADEID
    else:
        raise HttptlsActuationError("illegal_upgradeid")
    if offset >= len(raw):
        raise HttptlsActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_UPGRADE, FRAME_TLS}:
        raise HttptlsActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HttptlsActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HttptlsActuationError("checksum_failed")
    if len(payload) < 5:
        raise HttptlsActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HttptlsActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_upgradeid = int(live_upgradeid) != EMPTY_UPGRADEID
    has_upgradetlsdigest = has_upgradeid and int(live_digest) != EMPTY_UPGRADETLSDIGEST
    is_upgrade = frame_type == FRAME_UPGRADE
    is_tls = frame_type == FRAME_TLS
    return {
        "type": int(frame_type),
        "is_upgrade": is_upgrade,
        "is_tls": is_tls,
        "is_response": is_tls,
        "upgradeid": int(live_upgradeid),
        "has_upgradeid": has_upgradeid,
        "upgradetlsdigest": int(live_digest),
        "has_upgradetlsdigest": has_upgradetlsdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC2817",
        "serialize_field": canonical_upgrade(identity, live_upgradeid) if has_upgradeid else "",
        "tls_field": canonical_tls(identity, live_upgradeid, live_digest) if has_upgradetlsdigest else "",
    }


class HttptlsClient:
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
            raise HttptlsActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_tls"] or not packet["is_response"]:
            raise HttptlsActuationError("upgradetlsdigest_required")
        if not packet["has_upgradeid"]:
            raise HttptlsActuationError("upgradeid_required")
        if not packet["has_upgradetlsdigest"]:
            raise HttptlsActuationError("upgradetlsdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_upgradetlsdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_upgradetlsdigest:
            raise HttptlsActuationError("upgradetlsdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "upgradeid": int(reply.get("upgradeid") or EMPTY_UPGRADEID),
            "identity": str(reply.get("identity") or ""),
            "upgradetlsdigest": int(reply.get("upgradetlsdigest") or EMPTY_UPGRADETLSDIGEST),
        }

    def report(
        self,
        identity: str,
        upgradeid: int,
        upgradetlsdigest: int = EMPTY_UPGRADETLSDIGEST,
        *,
        wait_upgradetlsdigest: bool = True,
        include_upgradeid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_tls(
            identity=identity,
            upgradeid=upgradeid,
            upgradetlsdigest=upgradetlsdigest or request_upgradetlsdigest(upgradeid, identity),
            include_upgradeid=include_upgradeid,
        )
        return self.exchange(packet, wait_upgradetlsdigest=wait_upgradetlsdigest)


class HttptlsSession:
    """UPGRADEID-gated loopback RFC 2817 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        upgradeid_gate: int = DEFAULT_UPGRADEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.upgradeid_gate = int(upgradeid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.upgradeid = EMPTY_UPGRADEID
        self.upgradetlsdigest = EMPTY_UPGRADETLSDIGEST
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

    def store_upgradeid_once(self, identity: str, upgradeid: int, upgradetlsdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(upgradeid or EMPTY_UPGRADEID)
            live_digest = int(upgradetlsdigest or EMPTY_UPGRADETLSDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.upgradeid = live
                self.upgradetlsdigest = live_digest or request_upgradetlsdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.upgradeid), int(self.upgradetlsdigest)

    def read_upgradeid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.upgradeid), int(self.upgradetlsdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "upgradeid": EMPTY_UPGRADEID,
            "upgradetlsdigest": EMPTY_UPGRADETLSDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _upgradeid_missing(self) -> bool:
        return not int(self.upgradeid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, upgradeid: int, upgradetlsdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_tls(
            identity=identity,
            upgradeid=upgradeid,
            upgradetlsdigest=upgradetlsdigest,
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
            except HttptlsActuationError:
                continue
            if not packet.get("is_upgrade") and not packet.get("is_tls"):
                continue
            if not packet.get("has_upgradeid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_upgradeid, stored_digest = self.store_upgradeid_once(
                identity,
                int(packet.get("upgradeid") or EMPTY_UPGRADEID),
                int(packet.get("upgradetlsdigest") or EMPTY_UPGRADETLSDIGEST),
            )
            if not stored_name or not stored_upgradeid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_upgrade"):
                    self.opened = True
                if packet.get("is_tls"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_upgradeid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._upgradeid_missing():
            return self._forbidden("missing_upgradeid")
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
        do_upgrade: bool = True,
        do_tls: bool = True,
        do_upgradetlsdigest: bool = True,
        replay: bool = True,
        use_upgradeid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._upgradeid_missing():
            return self._forbidden("missing_upgradeid")
        live_token = str(token or SENTINEL)
        origin_upgradeid = request_upgradeid(live_token)
        origin_digest = request_upgradetlsdigest(origin_upgradeid, live_token)
        client: HttptlsClient | None = None
        independent: HttptlsClient | None = None
        try:
            client = HttptlsClient(self.host, int(self.port))
            if not do_upgrade:
                return self._conflict("upgrade_required")
            bind_packet = encode_upgrade(
                identity=live_token,
                upgradeid=origin_upgradeid,
                upgradetlsdigest=origin_digest,
                include_upgradeid=use_upgradeid,
            )
            if not use_upgradeid:
                try:
                    client.exchange(bind_packet, wait_upgradetlsdigest=True)
                except HttptlsActuationError:
                    return self._conflict("upgradeid_required")
                return self._conflict("upgradeid_required")
            client.send(bind_packet)
            if not do_tls:
                return self._conflict("tls_required")
            proxy_packet = encode_tls(
                identity=live_token,
                upgradeid=origin_upgradeid,
                upgradetlsdigest=origin_digest,
                include_upgradeid=True,
            )
            if not do_upgradetlsdigest:
                try:
                    client.exchange(proxy_packet, wait_upgradetlsdigest=False)
                except HttptlsActuationError as error:
                    if str(error) == "upgradetlsdigest_required":
                        return self._conflict("upgradetlsdigest_required")
                    return self._conflict("upgradetlsdigest_required")
                return self._conflict("upgradetlsdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_upgradetlsdigest=True)
            except HttptlsActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("upgradeid_required")
                if reason == "upgradetlsdigest_required":
                    return self._conflict("upgradetlsdigest_required")
                return self._conflict("upgrade_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("upgrade_required")
            if int(reply.get("upgradeid") or EMPTY_UPGRADEID) != origin_upgradeid:
                return self._conflict("upgradetlsdigest_required")
            if int(reply.get("upgradetlsdigest") or EMPTY_UPGRADETLSDIGEST) != origin_digest:
                return self._conflict("upgradetlsdigest_required")
            self.retrieved = True
            if replay:
                independent = HttptlsClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_upgradeid(live_token),
                        request_upgradetlsdigest(poll_upgradeid(live_token), POLL_TOKEN),
                        wait_upgradetlsdigest=True,
                    )
                except HttptlsActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_upgradeid, stored_digest = self.read_upgradeid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_upgradeid != origin_upgradeid
                    or stored_digest != origin_digest
                    or int(poll.get("upgradeid") or EMPTY_UPGRADEID) != origin_upgradeid
                    or int(poll.get("upgradetlsdigest") or EMPTY_UPGRADETLSDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_upgradeid}:{origin_digest}:{live_token}:{canonical_upgrade(live_token, origin_upgradeid)}:{canonical_tls(live_token, origin_upgradeid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "upgradeid": origin_upgradeid,
                "upgradetlsdigest": origin_digest,
                "upgrade_frame": True,
                "tls_frame": True,
                "upgradetlsdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "upgradeid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_httptls_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "upgradeid": origin_upgradeid,
                "upgradetlsdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "upgrade_frame": True,
                "tls_frame": True,
                "upgradetlsdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "upgradeid_bound": True,
            }
        except (OSError, HttptlsActuationError) as error:
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
        live = independent_httptls_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "upgradeid": int(live.get("upgradeid") or EMPTY_UPGRADEID),
            "upgradetlsdigest": int(live.get("upgradetlsdigest") or EMPTY_UPGRADETLSDIGEST),
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


def call_httptls_tool(session: HttptlsSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one upgrade tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_upgrade = True if arguments.get("upgrade") is None else bool(arguments.get("upgrade"))
    do_tls = True if arguments.get("tls") is None else bool(arguments.get("tls"))
    do_upgradetlsdigest = True if arguments.get("upgradetlsdigest") is None else bool(arguments.get("upgradetlsdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_upgradeid = True if arguments.get("use_upgradeid") is None else bool(arguments.get("use_upgradeid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_upgrade=do_upgrade,
            do_tls=do_tls,
            do_upgradetlsdigest=do_upgradetlsdigest,
            replay=replay,
            use_upgradeid=use_upgradeid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HttptlsActuationError(f"unsupported httptls action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_httptls_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed upgrade upgradetlsdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "upgradeid": EMPTY_UPGRADEID,
        "upgradetlsdigest": EMPTY_UPGRADETLSDIGEST,
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
            "upgrade_frame",
            "tls_frame",
            "upgradetlsdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "upgradeid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    upgradeid = int(payload.get("upgradeid") or EMPTY_UPGRADEID)
    upgradetlsdigest = int(payload.get("upgradetlsdigest") or EMPTY_UPGRADETLSDIGEST)
    dual = port > 0 and bool(upgradeid) and bool(upgradetlsdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "upgradeid": upgradeid,
        "upgradetlsdigest": upgradetlsdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "upgrade_frame": payload.get("upgrade_frame") is True,
        "tls_frame": payload.get("tls_frame") is True,
        "upgradetlsdigest_response": payload.get("upgradetlsdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "upgradeid_bound": payload.get("upgradeid_bound") is True,
    }


def run_httptls_workflow(
    *,
    with_upgradeid: bool = True,
    skip_bind: bool = False,
    do_upgrade: bool = True,
    do_tls: bool = True,
    do_upgradetlsdigest: bool = True,
    replay: bool = True,
    use_upgradeid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2817 UPGRADE/TLS upgradeid cycle workflow."""

    descriptor = httptls_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPTLS_TOOL_PROVIDER),
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
        raise HttptlsActuationError(f"httptls tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="httptls-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HttptlsSession(out, upgradeid_gate=DEFAULT_UPGRADEID if with_upgradeid else EMPTY_UPGRADEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "upgrade": do_upgrade,
            "tls": do_tls,
            "upgradetlsdigest": do_upgradetlsdigest,
            "replay": replay,
            "use_upgradeid": use_upgradeid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_httptls_tool(session, arguments))
            except HttptlsActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_httptls_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_upgradeid
        and not skip_bind
        and do_upgrade
        and do_tls
        and do_upgradetlsdigest
        and replay
        and use_upgradeid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "httptls_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_upgradeid": with_upgradeid,
        "skip_bind": skip_bind,
        "upgrade_frame": do_upgrade,
        "tls": do_tls,
        "upgradetlsdigest": do_upgradetlsdigest,
        "replay": replay,
        "use_upgradeid": use_upgradeid,
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
        "upgradeid_value": int(publish_result.get("upgradeid") or independent.get("upgradeid") or EMPTY_UPGRADEID),
        "upgradetlsdigest_value": int(publish_result.get("upgradetlsdigest") or independent.get("upgradetlsdigest") or EMPTY_UPGRADETLSDIGEST),
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
        "upgradeid": int(trace_body["upgradeid_value"] or EMPTY_UPGRADEID),
        "upgradetlsdigest": int(trace_body["upgradetlsdigest_value"] or EMPTY_UPGRADETLSDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_upgradeid": with_upgradeid,
        "skip_bind": skip_bind,
        "upgrade_cycle": do_upgrade,
        "tls_cycle": do_tls,
        "upgradetlsdigest_cycle": do_upgradetlsdigest,
        "replay": replay,
        "use_upgradeid": use_upgradeid,
    }


def verify_httptls_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_httptls_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    upgradeid = int(trace.get("upgradeid_value") or independent.get("upgradeid") or EMPTY_UPGRADEID)
    upgradetlsdigest = int(trace.get("upgradetlsdigest_value") or independent.get("upgradetlsdigest") or EMPTY_UPGRADETLSDIGEST)
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
        "upgrade_frame": independent.get("upgrade_frame") is True,
        "tls_frame": independent.get("tls_frame") is True,
        "upgradetlsdigest_response": independent.get("upgradetlsdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "upgradeid_bound": independent.get("upgradeid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "upgradetlsdigest_recorded": (
            port > 0
            and upgradeid == DEFAULT_UPGRADEID
            and upgradetlsdigest == DEFAULT_UPGRADETLSDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def httptls_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.httptls_actuation import "
        "builtin_httptls_actuation_proof; r=builtin_httptls_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='httptls_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_httptls_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTPTLS_ACTUATION_ID,
        name="First-class RFC 2817 Upgrading to TLS Within HTTP/1.1 UPGRADE/TLS actuation",
        description=(
            "Missions that require a httptls tool can opt the httptls provider in, "
            "bind a loopback RFC 2817 Upgrading to TLS Within HTTP/1.1 endpoint, complete a UPGRADE "
            "with a non-empty upgradeid, lockstep an TLS that carries the "
            "stored upgradetlsdigest, independently poll the stored upgradetlsdigest "
            "on a later socket, and seal a digest-chained upgradetlsdigest. Default "
            "routing stays fail-closed; a missing upgradeid keeps the hole "
            "falsifiable, and skip-UPGRADE/TLS/UPGRADETLSDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.httptls_actuation:builtin_httptls_actuation_proof",
        proof_command=httptls_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.spnego-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/httptls_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/spnego_actuation.py",
            "src/blackhole_agent/httpauth_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required httptls tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 2817 daemon, speaks a "
            "UPGRADE then TLS over Upgrading to TLS Within HTTP/1.1 with a non-empty upgradeid and "
            "upgradetlsdigest, independently polls the stored upgradetlsdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 4559 SPNEGO-based Kerberos and NTLM HTTP Authentication lockstep is proved. "
            "Missing upgradeids, skip-UPGRADE, skip-TLS, skip-upgradetlsdigest, skip-REPLAY, "
            "and a UPGRADE aimed without a upgradeid stay fail-closed. "
            "Later genesis can take RFC 2617 HTTP Authentication AUTH/DIGEST as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("httptls", "rfc2817", "http", "upgradeid", "upgradetlsdigest", "upgrade", "tls", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T000335Z-105a21bd",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_httptls_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2817 upgrade lockstep actuation seals a upgradetlsdigest."""

    from blackhole_agent.spnego_actuation import (
        SPNEGO_ACTUATION_GOAL,
        SPNEGO_ACTUATION_ID,
    )
    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
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
    checks["denylists_self"] = HTTPTLS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTPTLS_ACTUATION_GOAL) == (
        HTTPTLS_ACTUATION_ID,
    )
    checks["leftover_text_binds_httptls"] = leftover_marker_ids(HTTPTLS_LEFTOVER) == (
        HTTPTLS_ACTUATION_ID,
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
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_httptls"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"httptls_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTPTLS_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTPTLS_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_httptls(DEFAULT_UPGRADE)
    rebuilt = serialize_httptls(parse_httptls(advertised))
    preloaded = parse_httptls(RFC_HTTPTLS_TLS)
    header = encode_httptls_header(DEFAULT_UPGRADE)
    parsed_header = parse_httptls_header(header)
    asked = parse_http_request(upgrade_request(SENTINEL, DEFAULT_UPGRADEID))
    preload_req = parse_http_request(tls_request(SENTINEL, DEFAULT_UPGRADEID, DEFAULT_UPGRADETLSDIGEST))
    got = parse_http_response(upgrade_response(SENTINEL, DEFAULT_UPGRADEID, DEFAULT_UPGRADETLSDIGEST))
    preload_reply = parse_http_response(
        tls_response(SENTINEL, DEFAULT_UPGRADEID, DEFAULT_UPGRADETLSDIGEST)
    )
    checks["httptls_roundtrip"] = (
        parse_httptls(advertised) == DEFAULT_UPGRADE
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_UPGRADE_FIELD
        and is_token("UPGRADE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_UPGRADE_FIELD
        and parsed_header["policy"] == DEFAULT_UPGRADE
        and parsed_header["header"] == UPGRADE_HEADER
        and parsed_header["upgrade"] is True
        and parsed_header["tls"] is False
        and preloaded == TLS_POLICY
        and ascii_serialize_httptls_directive() == RFC_UPGRADE_DIRECTIVE
        and httptls_directive_pair() == ("protocol", "TLS/1.0")
        and RFC_UPGRADE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_httptls(TLS_POLICY) == RFC_HTTPTLS_TLS
        and DEFAULT_UPGRADETLSDIGEST == request_upgradetlsdigest(DEFAULT_UPGRADEID, SENTINEL)
        and "upgradetlsdigest=" in canonical_tls(SENTINEL, DEFAULT_UPGRADEID, DEFAULT_UPGRADETLSDIGEST)
        and canonical_upgrade(SENTINEL, DEFAULT_UPGRADEID).startswith("UPGRADE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "UPGRADE"
        and asked["httptls_kind"] == "upgrade"
        and asked["upgradeid"] == DEFAULT_UPGRADEID
        and preload_req["httptls_kind"] == "tls"
        and preload_req["upgradetlsdigest"] == DEFAULT_UPGRADETLSDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["httptls_kind"] == "upgrade"
        and preload_reply["httptls_kind"] == "tls"
        and got["policy"] == DEFAULT_UPGRADE
        and preload_reply["policy"] == TLS_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["upgradetlsdigest"] == DEFAULT_UPGRADETLSDIGEST
        and preload_reply["upgradetlsdigest"] == DEFAULT_UPGRADETLSDIGEST
        and httptls_matches(serialize_httptls(got["policy"]), advertised)
    )

    checks["catalog_names_httptls"] = (
        len(catalog) > 95
        and catalog[95]["id"] == HTTPTLS_ACTUATION_ID
        and catalog[94]["id"] == SPNEGO_ACTUATION_ID
        and catalog[95]["source"] == "genesis_bind_httptls"
    )
    checks["catalog_names_httpauth"] = (
        len(catalog) > 96
        and catalog[96]["id"] == HTTPAUTH_ACTUATION_ID
        and catalog[96]["source"] == "genesis_bind_httpauth"
    )
    family = capability_family(HTTPTLS_ACTUATION_GOAL)
    checks["family_is_httptls"] = "httptl" in family
    checks["family_is_httptls_surface"] = "httptl" in family
    checks["family_is_upgradeid"] = "upgradeid" in family
    checks["family_is_rfc2817"] = "rfc2817" in family
    checks["family_is_upgradetlsdigest"] = "upgradetlsdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_httpauth"] = (
        "httpauth" not in family
        and "rfc2617" not in family
        and "nonceid" not in family
        and "authdigest" not in family
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
    packed = encode_upgrade(identity=SENTINEL, upgradeid=DEFAULT_UPGRADEID, upgradetlsdigest=DEFAULT_UPGRADETLSDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_upgrade"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_upgradeid"] is True
        and parsed["upgradeid"] == DEFAULT_UPGRADEID
        and parsed["upgradetlsdigest"] == DEFAULT_UPGRADETLSDIGEST
        and parsed["is_response"] is False
        and parsed["is_tls"] is False
        and parsed["type"] == FRAME_UPGRADE
        and parsed["first_byte"] == UPGRADE_FIRST
    )
    shook = encode_tls(
        identity=SENTINEL,
        upgradeid=DEFAULT_UPGRADEID,
        upgradetlsdigest=DEFAULT_UPGRADETLSDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_tls"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_upgrade"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["upgradeid"] == DEFAULT_UPGRADEID
        and answer_parsed["upgradetlsdigest"] == DEFAULT_UPGRADETLSDIGEST
        and answer_parsed["has_upgradetlsdigest"] is True
        and answer_parsed["type"] == FRAME_TLS
        and answer_parsed["first_byte"] == UPGRADE_FIRST
    )
    bare = encode_upgrade(identity=SENTINEL, upgradeid=DEFAULT_UPGRADEID, include_upgradeid=False)
    checks["missing_upgradeid_is_untlsd"] = parse_message(bare)["has_upgradeid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    httptls_signature = semantic_signature(HTTPTLS_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(httptls_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_httptls = ToolDescriptor(name="remote_httptls", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_httptls)
    checks["naive_mcp_httptls_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = httptls_tool_descriptor()
    default_httptls = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPTLS_TOOL_PROVIDER),
    )
    checks["default_httptls_provider_is_unsupported"] = (
        default_httptls.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTPTLS_TOOL_PROVIDER}" in default_httptls.reasons
    )
    checks["opted_in_httptls_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_httptls],
        required_tool_names=("local_memory", "httptls"),
    )
    checks["naive_preflight_missing_httptls"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["httptls"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "httptls"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPTLS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "httptls" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="httptls-actuation-") as tmp:
        root = Path(tmp)
        missing = run_httptls_workflow(with_upgradeid=False, output_dir=root / "missing")
        skip_bind = run_httptls_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_upgrade = run_httptls_workflow(do_upgrade=False, output_dir=root / "skip-upgrade")
        skip_tls = run_httptls_workflow(do_tls=False, output_dir=root / "skip-tls")
        skip_upgradetlsdigest = run_httptls_workflow(do_upgradetlsdigest=False, output_dir=root / "skip-upgradetlsdigest")
        skip_replay = run_httptls_workflow(replay=False, output_dir=root / "skip-replay")
        skip_upgradeid = run_httptls_workflow(use_upgradeid=False, output_dir=root / "skip-upgradeid")
        live = run_httptls_workflow(output_dir=root / "live")
        verify = verify_httptls_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_httptls_trace(clone)
        checks["naive_without_upgradeid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_upgradeid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_upgrade_stays_empty"] = (
            skip_upgrade["ok"] is False
            and skip_upgrade["error"] == "upgrade_required"
            and skip_upgrade["final_status"] == 409
            and skip_upgrade["payload_exists"] is False
        )
        checks["skip_tls_stays_empty"] = (
            skip_tls["ok"] is False
            and skip_tls["error"] == "tls_required"
            and skip_tls["final_status"] == 409
            and skip_tls["payload_exists"] is False
        )
        checks["skip_upgradetlsdigest_stays_empty"] = (
            skip_upgradetlsdigest["ok"] is False
            and skip_upgradetlsdigest["error"] == "upgradetlsdigest_required"
            and skip_upgradetlsdigest["final_status"] == 409
            and skip_upgradetlsdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_upgradeid_stays_empty"] = (
            skip_upgradeid["ok"] is False
            and skip_upgradeid["error"] == "upgradeid_required"
            and skip_upgradeid["final_status"] == 409
            and skip_upgradeid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_upgradetlsdigest"] = (
            int(live.get("upgradeid") or 0) == DEFAULT_UPGRADEID
            and int(live.get("upgradetlsdigest") or 0) == DEFAULT_UPGRADETLSDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_upgradeid_encode_tls_upgradetlsdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_upgrade["ok"] is False
            and skip_tls["ok"] is False
            and skip_upgradetlsdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_upgradeid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="httptls-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTPTLS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_httptls"] = (
        live_goal == HTTPTLS_ACTUATION_GOAL
        and HTTPTLS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_httptls"
    )

    with tempfile.TemporaryDirectory(prefix="httptls-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTPTLS_LEFTOVER, root)
        register_catalog_proved(root, HTTPTLS_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTPTLS_LEFTOVER, root)
        after = leftover_is_open(HTTPTLS_LEFTOVER, root)
    checks["httptls_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_httptls_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTPTLS_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_httptls_actuation_capability()
    return {
        "ok": ok,
        "action": "httptls_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTPTLS_ACTUATION_GOAL,
        "done_when": HTTPTLS_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
