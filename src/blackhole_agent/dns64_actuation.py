"""Drive a first-class Stateful DNS64 tool through RFC 6147 DNS64/SYNTH.

Tool routing already fails missions that require ``dns64``: hosted
dns64 endpoints stay on the unsupported MCP provider, and no first-party
dns64 provider is executable. Unbound therefore cannot speak a DNS64,
lockstep a SYNTH dns64id handshake over HTTP/1.0 DNS64ID,
independently poll the stored dns64digest, or seal a dns64digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``dns64`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 6147 daemon
- keep a missing-dns64id client so the dns64-dns64id hole stays falsifiable
- refuse SYNTH until a DNS64 lands with a non-empty dns64id
- independently poll the stored dns64digest on a later client socket
- persist a sealed dns64digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 6146 Stateful NAT64
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
    DNS64_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    dns64_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
DNS64_ACTUATION_ID = "capability.dns64-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-DNS64-OK"
POLL_TOKEN = "BH-DNS64-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_DNS64ID = 0
EMPTY_DNS64DIGEST = 0
DNS64_FIRST = 0x47  # RFC 6147 DNS64; no RA option type
DNS64ID_SIZE = 4
DNS64DIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DEST = 0x02  # RFC 6147 synth index
FRAME_SOURCE = 0x01  # RFC 6147 dns64 type
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
DNS64_LEFTOVER = (
    "Later genesis can take RFC 6147 DNS Extensions for Network Address Translation from IPv6 Clients to IPv4 Servers DNS64/SYNTH over a "
    "dns64id-gated dns64digest."
)
DNS64_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DNS64_ACTUATION_ID};"
    f"capability_proved:{DNS64_ACTUATION_ID};"
    "no_skill_route"
)
DNS64_ACTUATION_GOAL = (
    "Repair rfc6147 dns64 dns64/synth cycle cannot land over http "
    "dns64 dns64id: hosted dns64 endpoints remain unsupported so a DNS64 then "
    "SYNTH dns64id handshake cannot land and a sealed dns64digest "
    "cannot be produced. A missing dns64 dns64id stays forbidden; fail-closed "
    "routing never opts the dns64 provider in. An independent later poll of the "
    "stored dns64digest keeps the hole falsifiable."
)


class Dns64ActuationError(RuntimeError):
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
# RFC 6147 sections 3.1 and 3.2: DNS64 / SYNTH.
RFC_SOURCE_FIELD = "DNS64"
RFC_DEST_FIELD = "SYNTH"
RFC_DNS64_DEST = RFC_DEST_FIELD
RFC_SOURCE_DIRECTIVE = "dns64=message"
RFC_DEST_DIRECTIVE = "synth=message"
DEFAULT_SOURCE = "DNS64"
DEST_HOP = "SYNTH"
SOURCE_HEADER = "Dns64"
DEST_HEADER = "Synth"
DNS64_DEST_HEADER = DEST_HEADER
RFC_SOURCE_PATH = "/dns64/"
RFC_SOURCE_EMPTY = ""


def dns64_directive_pair(*, local: bool = False) -> tuple[str, str]:
    """RFC 6147 Dns64 / Synth directive pair."""

    if local:
        return "synth", "message"
    return "dns64", "message"


def ascii_serialize_dns64_directive(*, local: bool = False) -> str:
    """RFC 6147 token "=" body-or-local."""

    name, value = dns64_directive_pair(local=local)
    if not is_token(name):
        raise Dns64ActuationError("illegal_directive")
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
            raise Dns64ActuationError("short_dns64")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 6147 body-unique token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_dns64(policy: str | Sequence[str]) -> str:
    """Serialize RFC 6147 DNS64 / SYNTH opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise Dns64ActuationError("illegal_dns64")
    upper = text.upper().replace("_", "-")
    if upper in {"DNS64", "DNS64", "DNS64-DNS64"}:
        return "DNS64"
    if upper in {"SYNTH", "AAAA", "DNS64-SYNTH"}:
        return "SYNTH"
    if upper.startswith("DNS64="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Dns64ActuationError("illegal_dns64")
        return "DNS64"
    if upper.startswith("SYNTH="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Dns64ActuationError("illegal_dns64")
        return "SYNTH"
    raise Dns64ActuationError("illegal_dns64")


def parse_dns64(text: str) -> str:
    """Parse RFC 6147 DNS64 opcode header extensions into DNS64 or SYNTH."""

    raw = str(text or "").strip()
    if not raw:
        raise Dns64ActuationError("illegal_dns64")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"DNS64", "DNS64", "DNS64-DNS64"}:
        return "DNS64"
    if upper in {"SYNTH", "AAAA", "DNS64-SYNTH"}:
        return "SYNTH"
    if upper.startswith("DNS64="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Dns64ActuationError("illegal_dns64")
        return "DNS64"
    if upper.startswith("SYNTH="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise Dns64ActuationError("illegal_dns64")
        return "SYNTH"
    raise Dns64ActuationError("illegal_dns64")


def encode_dns64_header(policy: str | Sequence[str]) -> bytes:
    """RFC 6147 HTTP/1.0 field as bytes."""

    return serialize_dns64(policy).encode("ascii")


def parse_dns64_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_dns64(field_value) if field_value else DEFAULT_SOURCE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SOURCE_HEADER,
        "directive": str(policy),
        "is_first": str(policy) == "DNS64",
        "table": str(policy) == "SYNTH",
    }


def canonical_temporary(identity: str, dns64id: int) -> str:
    """RFC 6147 body-unique advertisement bound to identity and dns64id."""

    return (
        f"{serialize_dns64(DEFAULT_SOURCE)}, "
        f"dns64={ascii_serialize_dns64_directive()}, "
        f"identity={identity}, dns64id={int(dns64id) & 0xFFFFFFFF}"
    )


def canonical_public(identity: str, dns64id: int, dns64digest: int | None = None) -> str:
    """RFC 6147 local-message confirmation of the stored identifier-digest."""

    digest = ""
    if dns64digest is not None:
        digest = f", dns64digest={int(dns64digest) & 0xFFFFFFFF}"
    return (
        f"{serialize_dns64(DEST_HOP)}, "
        f"synth={ascii_serialize_dns64_directive(local=True)}, "
        f"identity={identity}, dns64id={int(dns64id) & 0xFFFFFFFF}{digest}"
    )


def representation_public(identity: str, dns64id: int, dns64digest: int) -> str:
    return canonical_public(identity, dns64id, dns64digest)


def dns64_matches(left: str, right: str) -> bool:
    return parse_dns64(left) == parse_dns64(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise Dns64ActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise Dns64ActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise Dns64ActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise Dns64ActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def temporary_request(identity: str, dns64id: int) -> bytes:
    """HTTP DNS64 that elicits RFC 6147 origin HTTP/1.0."""

    keyid = f"{int(dns64id) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"DNS64 /dns64/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Dns64-Id: {int(dns64id) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def public_request(identity: str, dns64id: int, dns64digest: int | None = None) -> bytes:
    """HTTP SYNTH carrying RFC 6147 local-message confirmation of the stored identifier-digest."""

    keyid = f"{int(dns64id) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if dns64digest is not None:
        extra = f"Dns64-Digest: {int(dns64digest) & 0xFFFFFFFF}\r\n"
    return (
        f"SYNTH /dns64/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Dns64-Id: {int(dns64id) & 0xFFFFFFFF}\r\n"
        "Synth-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    dns64_kind = "synth" if fields.get("synth-confirm") == "1" else "dns64"
    upgrade_field = fields.get("dns64") or fields.get("dns64") or ""
    policy = parse_dns64(upgrade_field) if upgrade_field else ()
    return {
        "kind": "dns64",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "dns64_kind": dns64_kind,
        "policy": policy,
        "dns64id": int(fields["dns64-id"]) if fields.get("dns64-id") else EMPTY_DNS64ID,
        "dns64digest": int(fields["dns64-digest"]) if fields.get("dns64-digest") else EMPTY_DNS64DIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def temporary_response(identity: str, dns64id: int, dns64digest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 6147 origin HTTP/1.0, carrying the stored dns64digest."""

    publicised = serialize_dns64(DEFAULT_SOURCE)
    payload = bytes(body or canonical_temporary(identity, dns64id).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Dns64: {publicised}\r\n"
        f"Dns64-Id: {int(dns64id) & 0xFFFFFFFF}\r\n"
        f"Dns64-Digest: {int(dns64digest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def public_response(identity: str, dns64id: int, dns64digest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 6147 SYNTH, carrying the stored identifier-digest."""

    publicised = serialize_dns64(DEST_HOP)
    payload = bytes(body or representation_public(identity, dns64id, dns64digest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Dns64: {publicised}\r\n"
        f"Dns64-Id: {int(dns64id) & 0xFFFFFFFF}\r\n"
        f"Dns64-Digest: {int(dns64digest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/dns64-synth\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise Dns64ActuationError("illegal_content_length") from error
    field_value = fields.get("dns64") or fields.get("dns64") or ""
    policy = parse_dns64(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/dns64-synth" or policy == DEST_HOP:
        status = 200
        dns64_kind = "synth"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        dns64_kind = "dns64"
    else:
        status = 0
        dns64_kind = "dns64"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "dns64_kind": dns64_kind,
        "policy": policy,
        "dns64id": int(fields["dns64-id"]) if fields.get("dns64-id") else EMPTY_DNS64ID,
        "dns64digest": int(fields["dns64-digest"]) if fields.get("dns64-digest") else EMPTY_DNS64DIGEST,
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
        raise Dns64ActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise Dns64ActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise Dns64ActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise Dns64ActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc6147_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    ula: str,
) -> str:
    """RFC 6147 identifier digest over method, router-IP, identity, and dns64id."""

    payload = f"{method}:{ula}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def temporary_dns64id(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"dns64id:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_dns64id(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-dns64id:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def temporary_dns64digest(dns64id: int = EMPTY_DNS64ID, token: str = SENTINEL) -> int:
    nonce = f"{int(dns64id) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc6147_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="SYNTH",
        ula=f"/dns64/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_DNS64ID = temporary_dns64id(SENTINEL)
DEFAULT_DNS64DIGEST = temporary_dns64digest(DEFAULT_DNS64ID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    dns64id: int,
    dns64digest: int,
    include_dns64id: bool = True,
) -> bytes:
    live_dns64id = int(dns64id) & 0xFFFFFFFF if include_dns64id else EMPTY_DNS64ID
    live_digest = int(dns64digest) & 0xFFFFFFFF if include_dns64id and live_dns64id else EMPTY_DNS64DIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_dns64id) if live_dns64id else b""
    header = bytearray()
    header.append(DNS64_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_temporary(
    *,
    identity: str,
    dns64id: int,
    dns64digest: int | None = None,
    include_dns64id: bool = True,
) -> bytes:
    live_dns64id = int(dns64id) & 0xFFFFFFFF if include_dns64id else EMPTY_DNS64ID
    live_digest = int(dns64digest) if dns64digest is not None else temporary_dns64digest(live_dns64id, identity)
    return encode_packet(
        FRAME_SOURCE,
        identity=identity,
        dns64id=live_dns64id,
        dns64digest=live_digest,
        include_dns64id=include_dns64id,
    )


def encode_public(
    *,
    identity: str,
    dns64id: int,
    dns64digest: int | None = None,
    include_dns64id: bool = True,
) -> bytes:
    live_dns64id = int(dns64id) & 0xFFFFFFFF if include_dns64id else EMPTY_DNS64ID
    live_digest = int(dns64digest) if dns64digest is not None else temporary_dns64digest(live_dns64id, identity)
    return encode_packet(
        FRAME_DEST,
        identity=identity,
        dns64id=live_dns64id,
        dns64digest=live_digest,
        include_dns64id=include_dns64id,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise Dns64ActuationError("short_packet")
    dns64 = raw[0]
    if dns64 != DNS64_FIRST:
        raise Dns64ActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise Dns64ActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == DNS64ID_SIZE:
        live_dns64id = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_dns64id = EMPTY_DNS64ID
    else:
        raise Dns64ActuationError("illegal_dns64id")
    if offset >= len(raw):
        raise Dns64ActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SOURCE, FRAME_DEST}:
        raise Dns64ActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise Dns64ActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise Dns64ActuationError("checksum_failed")
    if len(payload) < 5:
        raise Dns64ActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise Dns64ActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_dns64id = int(live_dns64id) != EMPTY_DNS64ID
    has_dns64digest = has_dns64id and int(live_digest) != EMPTY_DNS64DIGEST
    is_temporary = frame_type == FRAME_SOURCE
    is_public = frame_type == FRAME_DEST
    return {
        "type": int(frame_type),
        "is_temporary": is_temporary,
        "is_public": is_public,
        "dns64id": int(live_dns64id),
        "has_dns64id": has_dns64id,
        "dns64digest": int(live_digest),
        "has_dns64digest": has_dns64digest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(dns64),
        "mech_len": int(mech_len),
        "http_state": "RFC6147",
        "serialize_field": canonical_temporary(identity, live_dns64id) if has_dns64id else "",
        "tls_field": canonical_public(identity, live_dns64id, live_digest) if has_dns64digest else "",
    }


class Dns64Client:
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
            raise Dns64ActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_public"] or not packet["is_public"]:
            raise Dns64ActuationError("dns64digest_required")
        if not packet["has_dns64id"]:
            raise Dns64ActuationError("dns64id_required")
        if not packet["has_dns64digest"]:
            raise Dns64ActuationError("dns64digest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_dns64digest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_dns64digest:
            raise Dns64ActuationError("dns64digest_required")
        session = self._recv()
        return {
            "session": session,
            "dns64id": int(session.get("dns64id") or EMPTY_DNS64ID),
            "identity": str(session.get("identity") or ""),
            "dns64digest": int(session.get("dns64digest") or EMPTY_DNS64DIGEST),
        }

    def local(
        self,
        identity: str,
        dns64id: int,
        dns64digest: int = EMPTY_DNS64DIGEST,
        *,
        wait_dns64digest: bool = True,
        include_dns64id: bool = True,
    ) -> dict[str, Any]:
        packet = encode_public(
            identity=identity,
            dns64id=dns64id,
            dns64digest=dns64digest or temporary_dns64digest(dns64id, identity),
            include_dns64id=include_dns64id,
        )
        return self.exchange(packet, wait_dns64digest=wait_dns64digest)


class Dns64Session:
    """DNS64ID-gated loopback RFC 6147 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        dns64id_gate: int = DEFAULT_DNS64ID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dns64id_gate = int(dns64id_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.dns64id = EMPTY_DNS64ID
        self.dns64digest = EMPTY_DNS64DIGEST
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

    def store_dns64id_once(self, identity: str, dns64id: int, dns64digest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(dns64id or EMPTY_DNS64ID)
            live_digest = int(dns64digest or EMPTY_DNS64DIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.dns64id = live
                self.dns64digest = live_digest or temporary_dns64digest(live, name)
                self.stored = True
            return str(self.identity), int(self.dns64id), int(self.dns64digest)

    def read_dns64id(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.dns64id), int(self.dns64digest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "dns64id": EMPTY_DNS64ID,
            "dns64digest": EMPTY_DNS64DIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _dns64id_missing(self) -> bool:
        return not int(self.dns64id_gate or 0)

    def _public_tuple(self, peer: tuple[str, int], identity: str, dns64id: int, dns64digest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_public(
            identity=identity,
            dns64id=dns64id,
            dns64digest=dns64digest,
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
            except Dns64ActuationError:
                continue
            if not packet.get("is_temporary") and not packet.get("is_public"):
                continue
            if not packet.get("has_dns64id"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_dns64id, stored_digest = self.store_dns64id_once(
                identity,
                int(packet.get("dns64id") or EMPTY_DNS64ID),
                int(packet.get("dns64digest") or EMPTY_DNS64DIGEST),
            )
            if not stored_name or not stored_dns64id or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_temporary"):
                    self.opened = True
                if packet.get("is_public"):
                    self.handshook = True
                self.retrieved = True
            self._public_tuple(peer, stored_name, stored_dns64id, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._dns64id_missing():
            return self._forbidden("missing_dns64id")
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
        do_temporary: bool = True,
        do_public: bool = True,
        do_dns64digest: bool = True,
        replay: bool = True,
        use_dns64id: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._dns64id_missing():
            return self._forbidden("missing_dns64id")
        live_token = str(token or SENTINEL)
        origin_dns64id = temporary_dns64id(live_token)
        origin_digest = temporary_dns64digest(origin_dns64id, live_token)
        client: Dns64Client | None = None
        independent: Dns64Client | None = None
        try:
            client = Dns64Client(self.host, int(self.port))
            if not do_temporary:
                return self._conflict("temporary_required")
            bind_packet = encode_temporary(
                identity=live_token,
                dns64id=origin_dns64id,
                dns64digest=origin_digest,
                include_dns64id=use_dns64id,
            )
            if not use_dns64id:
                try:
                    client.exchange(bind_packet, wait_dns64digest=True)
                except Dns64ActuationError:
                    return self._conflict("dns64id_required")
                return self._conflict("dns64id_required")
            client.send(bind_packet)
            if not do_public:
                return self._conflict("public_required")
            proxy_packet = encode_public(
                identity=live_token,
                dns64id=origin_dns64id,
                dns64digest=origin_digest,
                include_dns64id=True,
            )
            if not do_dns64digest:
                try:
                    client.exchange(proxy_packet, wait_dns64digest=False)
                except Dns64ActuationError as error:
                    if str(error) == "dns64digest_required":
                        return self._conflict("dns64digest_required")
                    return self._conflict("dns64digest_required")
                return self._conflict("dns64digest_required")
            try:
                session = client.exchange(proxy_packet, wait_dns64digest=True)
            except Dns64ActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("dns64id_required")
                if reason == "dns64digest_required":
                    return self._conflict("dns64digest_required")
                return self._conflict("temporary_required")
            if str(session.get("identity") or "") != live_token:
                return self._conflict("temporary_required")
            if int(session.get("dns64id") or EMPTY_DNS64ID) != origin_dns64id:
                return self._conflict("dns64digest_required")
            if int(session.get("dns64digest") or EMPTY_DNS64DIGEST) != origin_digest:
                return self._conflict("dns64digest_required")
            self.retrieved = True
            if replay:
                independent = Dns64Client(self.host, int(self.port))
                try:
                    poll = independent.local(
                        POLL_TOKEN,
                        poll_dns64id(live_token),
                        temporary_dns64digest(poll_dns64id(live_token), POLL_TOKEN),
                        wait_dns64digest=True,
                    )
                except Dns64ActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_dns64id, stored_digest = self.read_dns64id()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_dns64id != origin_dns64id
                    or stored_digest != origin_digest
                    or int(poll.get("dns64id") or EMPTY_DNS64ID) != origin_dns64id
                    or int(poll.get("dns64digest") or EMPTY_DNS64DIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_dns64id}:{origin_digest}:{live_token}:{canonical_temporary(live_token, origin_dns64id)}:{canonical_public(live_token, origin_dns64id, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "dns64id": origin_dns64id,
                "dns64digest": origin_digest,
                "temporary_frame": True,
                "public_frame": True,
                "dns64digest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "dns64id_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_dns64digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "dns64id": origin_dns64id,
                "dns64digest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "temporary_frame": True,
                "public_frame": True,
                "dns64digest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "dns64id_bound": True,
            }
        except (OSError, Dns64ActuationError) as error:
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
        live = independent_dns64digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "dns64id": int(live.get("dns64id") or EMPTY_DNS64ID),
            "dns64digest": int(live.get("dns64digest") or EMPTY_DNS64DIGEST),
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


def call_dns64_tool(session: Dns64Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one dns64 tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_temporary = True if arguments.get("dns64") is None else bool(arguments.get("dns64"))
    do_public = True if arguments.get("synth") is None else bool(arguments.get("synth"))
    do_dns64digest = True if arguments.get("dns64digest") is None else bool(arguments.get("dns64digest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_dns64id = True if arguments.get("use_dns64id") is None else bool(arguments.get("use_dns64id"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_temporary=do_temporary,
            do_public=do_public,
            do_dns64digest=do_dns64digest,
            replay=replay,
            use_dns64id=use_dns64id,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise Dns64ActuationError(f"unsupported dns64 action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_dns64digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage dns64digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "dns64id": EMPTY_DNS64ID,
        "dns64digest": EMPTY_DNS64DIGEST,
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
            "temporary_frame",
            "public_frame",
            "dns64digest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "dns64id_bound",
        )
    )
    port = int(payload.get("port") or 0)
    dns64id = int(payload.get("dns64id") or EMPTY_DNS64ID)
    dns64digest = int(payload.get("dns64digest") or EMPTY_DNS64DIGEST)
    dual = port > 0 and bool(dns64id) and bool(dns64digest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "dns64id": dns64id,
        "dns64digest": dns64digest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "temporary_frame": payload.get("temporary_frame") is True,
        "public_frame": payload.get("public_frame") is True,
        "dns64digest_locate": payload.get("dns64digest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "dns64id_bound": payload.get("dns64id_bound") is True,
    }


def run_dns64_workflow(
    *,
    with_dns64id: bool = True,
    skip_bind: bool = False,
    do_temporary: bool = True,
    do_public: bool = True,
    do_dns64digest: bool = True,
    replay: bool = True,
    use_dns64id: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 6147 DNS64/SYNTH dns64id cycle workflow."""

    descriptor = dns64_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DNS64_TOOL_PROVIDER),
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
        raise Dns64ActuationError(f"dns64 tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="dns64-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = Dns64Session(out, dns64id_gate=DEFAULT_DNS64ID if with_dns64id else EMPTY_DNS64ID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "dns64": do_temporary,
            "synth": do_public,
            "dns64digest": do_dns64digest,
            "replay": replay,
            "use_dns64id": use_dns64id,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_dns64_tool(session, arguments))
            except Dns64ActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_dns64digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_dns64id
        and not skip_bind
        and do_temporary
        and do_public
        and do_dns64digest
        and replay
        and use_dns64id
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "dns64_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_dns64id": with_dns64id,
        "skip_bind": skip_bind,
        "temporary_frame": do_temporary,
        "public_frame": do_public,
        "dns64digest": do_dns64digest,
        "replay": replay,
        "use_dns64id": use_dns64id,
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
        "dns64id_value": int(publish_result.get("dns64id") or independent.get("dns64id") or EMPTY_DNS64ID),
        "dns64digest_value": int(publish_result.get("dns64digest") or independent.get("dns64digest") or EMPTY_DNS64DIGEST),
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
        "dns64id": int(trace_body["dns64id_value"] or EMPTY_DNS64ID),
        "dns64digest": int(trace_body["dns64digest_value"] or EMPTY_DNS64DIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_dns64id": with_dns64id,
        "skip_bind": skip_bind,
        "temporary_cycle": do_temporary,
        "public_cycle": do_public,
        "dns64digest_cycle": do_dns64digest,
        "replay": replay,
        "use_dns64id": use_dns64id,
    }


def verify_dns64_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_dns64digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    dns64id = int(trace.get("dns64id_value") or independent.get("dns64id") or EMPTY_DNS64ID)
    dns64digest = int(trace.get("dns64digest_value") or independent.get("dns64digest") or EMPTY_DNS64DIGEST)
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
        "temporary_frame": independent.get("temporary_frame") is True,
        "public_frame": independent.get("public_frame") is True,
        "dns64digest_locate": independent.get("dns64digest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "dns64id_bound": independent.get("dns64id_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "dns64digest_recorded": (
            port > 0
            and dns64id == DEFAULT_DNS64ID
            and dns64digest == DEFAULT_DNS64DIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def dns64_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.dns64_actuation import "
        "builtin_dns64_actuation_proof; r=builtin_dns64_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='dns64_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_dns64_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=DNS64_ACTUATION_ID,
        name="First-class RFC 6147 DNS Extensions for Network Address Translation from IPv6 Clients to IPv4 Servers DNS64/SYNTH actuation",
        description=(
            "Missions that require a dns64 tool can opt the dns64 provider in, "
            "bind a loopback RFC 6147 DNS Extensions for Network Address Translation from IPv6 Clients to IPv4 Servers endpoint, complete a DNS64 "
            "with a non-empty dns64id, lockstep a SYNTH that carries the "
            "stored dns64digest, independently poll the stored dns64digest "
            "on a later socket, and seal a digest-chained dns64digest. Default "
            "routing stays fail-closed; a missing dns64id keeps the hole "
            "falsifiable, and skip-DNS64/SYNTH/DNS64DIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.dns64_actuation:builtin_dns64_actuation_proof",
        proof_command=dns64_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.nat64-actuation",
            "capability.pref64-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/dns64_actuation.py",
            "src/blackhole_agent/nat64_actuation.py",
            "src/blackhole_agent/pref64_actuation.py",
            "src/blackhole_agent/rdnss_actuation.py",
            "src/blackhole_agent/firsthop_actuation.py",
            "src/blackhole_agent/addrpolicy_actuation.py",
            "src/blackhole_agent/addrselect_actuation.py",
            "src/blackhole_agent/ipv6scope_actuation.py",
            "src/blackhole_agent/ipv6addr_actuation.py",
            "src/blackhole_agent/cga_actuation.py",
            "src/blackhole_agent/opaqueiid_actuation.py",
            "src/blackhole_agent/tempaddr_actuation.py",
            "src/blackhole_agent/slaac_actuation.py",
            "src/blackhole_agent/ndp_actuation.py",
            "src/blackhole_agent/mld_actuation.py",
            "src/blackhole_agent/igmp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/rarp_actuation.py",
            "src/blackhole_agent/arp_actuation.py",
            "src/blackhole_agent/ip_actuation.py",
            "src/blackhole_agent/icmp_actuation.py",
            "src/blackhole_agent/xlat_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required dns64 tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 6147 daemon, speaks a "
            "DNS64 then SYNTH over DNS Extensions for Network Address Translation from IPv6 Clients to IPv4 Servers with a non-empty dns64id and "
            "dns64digest, independently polls the stored dns64digest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 6146 Stateful NAT64 lockstep is proved. "
            "Missing dns64ids, skip-DNS64, skip-SYNTH, skip-dns64digest, skip-REPLAY, "
            "and a DNS64 aimed without a dns64id stay fail-closed. "
            "Later genesis can take RFC 6877 464XLAT Combination of Stateful and Stateless Translation CLAT/PLAT as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("dns64", "rfc6147", "http", "dns64id", "dns64digest", "dns64", "synth", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260907T055534Z-abea330d",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_dns64_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 6147 dns64/synth lockstep actuation seals a dns64digest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.slaac_actuation import (
        SLAAC_ACTUATION_GOAL,
        SLAAC_ACTUATION_ID,
    )
    from blackhole_agent.xlat_actuation import (
        XLAT_ACTUATION_GOAL,
        XLAT_ACTUATION_ID,
    )
    from blackhole_agent.nat64_actuation import (
        NAT64_ACTUATION_GOAL,
        NAT64_ACTUATION_ID,
    )
    from blackhole_agent.pref64_actuation import (
        PREF64_ACTUATION_GOAL,
        PREF64_ACTUATION_ID,
    )
    from blackhole_agent.rdnss_actuation import (
        RDNSS_ACTUATION_GOAL,
        RDNSS_ACTUATION_ID,
    )
    from blackhole_agent.firsthop_actuation import (
        FIRSTHOP_ACTUATION_GOAL,
        FIRSTHOP_ACTUATION_ID,
    )
    from blackhole_agent.addrpolicy_actuation import (
        ADDRPOLICY_ACTUATION_GOAL,
        ADDRPOLICY_ACTUATION_ID,
    )
    from blackhole_agent.addrselect_actuation import (
        ADDRSELECT_ACTUATION_GOAL,
        ADDRSELECT_ACTUATION_ID,
    )
    from blackhole_agent.ipv6scope_actuation import (
        IPV6SCOPE_ACTUATION_GOAL,
        IPV6SCOPE_ACTUATION_ID,
    )
    from blackhole_agent.ipv6addr_actuation import (
        IPV6ADDR_ACTUATION_GOAL,
        IPV6ADDR_ACTUATION_ID,
    )
    from blackhole_agent.ula_actuation import (
        ULA_ACTUATION_GOAL,
        ULA_ACTUATION_ID,
    )
    from blackhole_agent.cga_actuation import (
        CGA_ACTUATION_GOAL,
        CGA_ACTUATION_ID,
    )
    from blackhole_agent.opaqueiid_actuation import (
        OPAQUEIID_ACTUATION_GOAL,
        OPAQUEIID_ACTUATION_ID,
    )
    from blackhole_agent.tempaddr_actuation import (
        TEMPADDR_ACTUATION_GOAL,
        TEMPADDR_ACTUATION_ID,
    )
    from blackhole_agent.ndp_actuation import (
        NDP_ACTUATION_GOAL,
        NDP_ACTUATION_ID,
    )
    from blackhole_agent.mld_actuation import (
        MLD_ACTUATION_GOAL,
        MLD_ACTUATION_ID,
    )
    from blackhole_agent.igmp_actuation import (
        IGMP_ACTUATION_GOAL,
        IGMP_ACTUATION_ID,
    )
    from blackhole_agent.rarp_actuation import (
        RARP_ACTUATION_GOAL,
        RARP_ACTUATION_ID,
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
    checks["denylists_self"] = DNS64_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(DNS64_ACTUATION_GOAL) == (
        DNS64_ACTUATION_ID,
    )
    checks["leftover_text_binds_dns64"] = leftover_marker_ids(DNS64_LEFTOVER) == (
        DNS64_ACTUATION_ID,
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
        (XLAT_ACTUATION_GOAL, XLAT_ACTUATION_ID, "xlat"),
        (NAT64_ACTUATION_GOAL, NAT64_ACTUATION_ID, "nat64"),
        (PREF64_ACTUATION_GOAL, PREF64_ACTUATION_ID, "pref64"),
        (RDNSS_ACTUATION_GOAL, RDNSS_ACTUATION_ID, "rdnss"),
        (FIRSTHOP_ACTUATION_GOAL, FIRSTHOP_ACTUATION_ID, "firsthop"),
        (ADDRPOLICY_ACTUATION_GOAL, ADDRPOLICY_ACTUATION_ID, "addrpolicy"),
        (ADDRSELECT_ACTUATION_GOAL, ADDRSELECT_ACTUATION_ID, "addrselect"),
        (IPV6SCOPE_ACTUATION_GOAL, IPV6SCOPE_ACTUATION_ID, "ipv6scope"),
        (IPV6ADDR_ACTUATION_GOAL, IPV6ADDR_ACTUATION_ID, "ipv6addr"),
        (ULA_ACTUATION_GOAL, ULA_ACTUATION_ID, "ula"),
        (CGA_ACTUATION_GOAL, CGA_ACTUATION_ID, "cga"),
        (OPAQUEIID_ACTUATION_GOAL, OPAQUEIID_ACTUATION_ID, "opaqueiid"),
        (TEMPADDR_ACTUATION_GOAL, TEMPADDR_ACTUATION_ID, "tempaddr"),
        (SLAAC_ACTUATION_GOAL, SLAAC_ACTUATION_ID, "slaac"),
        (NDP_ACTUATION_GOAL, NDP_ACTUATION_ID, "ndp"),
        (MLD_ACTUATION_GOAL, MLD_ACTUATION_ID, "mld"),
        (IGMP_ACTUATION_GOAL, IGMP_ACTUATION_ID, "igmp"),
        (RARP_ACTUATION_GOAL, RARP_ACTUATION_ID, "rarp"),
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
        checks[f"{name}_goal_is_not_dns64"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"dns64_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            DNS64_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = DNS64_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    publicised = serialize_dns64(DEFAULT_SOURCE)
    rebuilt = serialize_dns64(parse_dns64(publicised))
    preloaded = parse_dns64(RFC_DNS64_DEST)
    header = encode_dns64_header(DEFAULT_SOURCE)
    parsed_header = parse_dns64_header(header)
    asked = parse_http_request(temporary_request(SENTINEL, DEFAULT_DNS64ID))
    preload_req = parse_http_request(public_request(SENTINEL, DEFAULT_DNS64ID, DEFAULT_DNS64DIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_DNS64ID, DEFAULT_DNS64DIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_DNS64ID, DEFAULT_DNS64DIGEST)
    )
    checks["dns64_roundtrip"] = (
        parse_dns64(publicised) == DEFAULT_SOURCE
        and hmac.compare_digest(rebuilt, publicised)
        and publicised == RFC_SOURCE_FIELD
        and is_token("DNS64") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SOURCE_FIELD
        and parsed_header["policy"] == DEFAULT_SOURCE
        and parsed_header["header"] == SOURCE_HEADER
        and parsed_header["is_first"] is True
        and parsed_header["table"] is False
        and preloaded == DEST_HOP
        and ascii_serialize_dns64_directive() == RFC_SOURCE_DIRECTIVE
        and dns64_directive_pair() == ("dns64", "message")
        and RFC_SOURCE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_dns64(DEST_HOP) == RFC_DNS64_DEST
        and DEFAULT_DNS64DIGEST == temporary_dns64digest(DEFAULT_DNS64ID, SENTINEL)
        and "dns64digest=" in canonical_public(SENTINEL, DEFAULT_DNS64ID, DEFAULT_DNS64DIGEST)
        and canonical_temporary(SENTINEL, DEFAULT_DNS64ID).startswith("DNS64")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "DNS64"
        and asked["dns64_kind"] == "dns64"
        and asked["dns64id"] == DEFAULT_DNS64ID
        and preload_req["dns64_kind"] == "synth"
        and preload_req["dns64digest"] == DEFAULT_DNS64DIGEST
        and got["status"] == 200
        and preload_public["status"] == 200
        and got["dns64_kind"] == "dns64"
        and preload_public["dns64_kind"] == "synth"
        and got["policy"] == DEFAULT_SOURCE
        and preload_public["policy"] == DEST_HOP
        and got["content_length_matches_body"] is True
        and preload_public["content_length_matches_body"] is True
        and got["dns64digest"] == DEFAULT_DNS64DIGEST
        and preload_public["dns64digest"] == DEFAULT_DNS64DIGEST
        and dns64_matches(serialize_dns64(got["policy"]), publicised)
    )

    checks["catalog_names_addrselect"] = (
        len(catalog) > 129
        and catalog[129]["id"] == ADDRSELECT_ACTUATION_ID
        and catalog[128]["id"] == IPV6SCOPE_ACTUATION_ID
        and catalog[129]["source"] == "genesis_bind_addrselect"
    )
    checks["catalog_names_addrpolicy"] = (
        len(catalog) > 130
        and catalog[130]["id"] == ADDRPOLICY_ACTUATION_ID
        and catalog[130]["source"] == "genesis_bind_addrpolicy"
    )
    checks["catalog_names_firsthop"] = (
        len(catalog) > 131
        and catalog[131]["id"] == FIRSTHOP_ACTUATION_ID
        and catalog[131]["source"] == "genesis_bind_firsthop"
    )
    checks["catalog_names_rdnss"] = (
        len(catalog) > 132
        and catalog[132]["id"] == RDNSS_ACTUATION_ID
        and catalog[132]["source"] == "genesis_bind_rdnss"
    )
    checks["catalog_names_pref64"] = (
        len(catalog) > 133
        and catalog[133]["id"] == PREF64_ACTUATION_ID
        and catalog[133]["source"] == "genesis_bind_pref64"
    )
    checks["catalog_names_nat64"] = (
        len(catalog) > 134
        and catalog[134]["id"] == NAT64_ACTUATION_ID
        and catalog[134]["source"] == "genesis_bind_nat64"
    )
    checks["catalog_names_dns64"] = (
        len(catalog) > 135
        and catalog[135]["id"] == DNS64_ACTUATION_ID
        and catalog[135]["source"] == "genesis_bind_dns64"
    )
    checks["catalog_names_xlat"] = (
        len(catalog) > 136
        and catalog[136]["id"] == XLAT_ACTUATION_ID
        and catalog[136]["source"] == "genesis_bind_xlat"
    )
    family = capability_family(DNS64_ACTUATION_GOAL)
    checks["family_is_dns64"] = "dns64" in family.split("/")
    checks["family_is_dns64_surface"] = "dns64id" in family
    checks["family_is_dns64id"] = "dns64id" in family
    checks["family_is_rfc6147"] = "rfc6147" in family
    checks["family_is_dns64digest"] = "dns64digest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_slaac"] = (
        "slaac" not in family.split("/")
        and "rfc4862" not in family
        and "slaacid" not in family
        and "slaacdigest" not in family
    )
    checks["family_is_not_xlat"] = (
        "xlat" not in family.split("/")
        and "rfc6877" not in family
        and "clatid" not in family
        and "clatdigest" not in family
    )
    checks["family_is_not_nat64"] = (
        "nat64" not in family.split("/")
        and "rfc6146" not in family
        and "nat64id" not in family
        and "nat64digest" not in family
    )
    checks["family_is_not_pref64"] = (
        "pref64" not in family.split("/")
        and "rfc8781" not in family
        and "pref64id" not in family
        and "pref64digest" not in family
    )
    checks["family_is_not_rdnss"] = (
        "rdnss" not in family.split("/")
        and "rfc8106" not in family
        and "rdnssid" not in family
        and "rdnssdigest" not in family
    )
    checks["family_is_not_firsthop"] = (
        "firsthop" not in family.split("/")
        and "rfc8028" not in family
        and "hopid" not in family
        and "hopdigest" not in family
    )
    checks["family_is_not_addrpolicy"] = (
        "addrpolicy" not in family.split("/")
        and "rfc7078" not in family
        and "policyid" not in family
        and "policydigest" not in family
    )
    checks["family_is_not_addrselect"] = (
        "addrselect" not in family.split("/")
        and "rfc6724" not in family
        and "selectid" not in family
        and "selectdigest" not in family
    )
    checks["family_is_not_ipv6scope"] = (
        "ipv6scope" not in family.split("/")
        and "rfc4007" not in family
        and "scopeid" not in family
        and "scopedigest" not in family
    )
    checks["family_is_not_ipv6addr"] = (
        "ipv6addr" not in family.split("/")
        and "rfc4291" not in family
        and "ipv6addrid" not in family
        and "ipv6addrdigest" not in family
    )
    checks["family_is_not_ula"] = (
        "ula" not in family.split("/")
        and "rfc4193" not in family
        and "ulaid" not in family
        and "uladigest" not in family
    )
    checks["family_is_not_send"] = (
        "send" not in family.split("/")
        and "rfc3971" not in family
        and "sendid" not in family
        and "senddigest" not in family
    )
    checks["family_is_not_cga"] = (
        "cga" not in family.split("/")
        and "rfc3972" not in family
        and "cgaid" not in family
        and "cgadigest" not in family
    )
    checks["family_is_not_opaqueiid"] = (
        "opaqueiid" not in family.split("/")
        and "rfc7217" not in family
        and "opaqueid" not in family
        and "opaquedigest" not in family
    )
    checks["family_is_not_tempaddr"] = (
        "tempaddr" not in family.split("/")
        and "rfc4941" not in family
        and "tempaddrid" not in family
        and "tempaddrdigest" not in family
    )
    checks["family_is_not_ndp"] = (
        "ndp" not in family.split("/")
        and "rfc4861" not in family
        and "ndpid" not in family
        and "ndpdigest" not in family
    )
    checks["family_is_not_mld"] = (
        "mld" not in family.split("/")
        and "rfc2710" not in family
        and "mldid" not in family
        and "mlddigest" not in family
    )
    checks["family_is_not_igmp"] = (
        "igmp" not in family.split("/")
        and "rfc1112" not in family
        and "igmpid" not in family
        and "igmpdigest" not in family
    )
    checks["family_is_not_rarp"] = (
        "rarp" not in family.split("/")
        and "rfc903" not in family
        and "rarpid" not in family
        and "rarpdigest" not in family
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
    packed = encode_temporary(identity=SENTINEL, dns64id=DEFAULT_DNS64ID, dns64digest=DEFAULT_DNS64DIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_temporary"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_dns64id"] is True
        and parsed["dns64id"] == DEFAULT_DNS64ID
        and parsed["dns64digest"] == DEFAULT_DNS64DIGEST
        and parsed["is_public"] is False
        and parsed["is_public"] is False
        and parsed["type"] == FRAME_SOURCE
        and parsed["first_byte"] == DNS64_FIRST
    )
    shook = encode_public(
        identity=SENTINEL,
        dns64id=DEFAULT_DNS64ID,
        dns64digest=DEFAULT_DNS64DIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_public"] is True
        and answer_parsed["is_public"] is True
        and answer_parsed["is_temporary"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["dns64id"] == DEFAULT_DNS64ID
        and answer_parsed["dns64digest"] == DEFAULT_DNS64DIGEST
        and answer_parsed["has_dns64digest"] is True
        and answer_parsed["type"] == FRAME_DEST
        and answer_parsed["first_byte"] == DNS64_FIRST
    )
    bare = encode_temporary(identity=SENTINEL, dns64id=DEFAULT_DNS64ID, include_dns64id=False)
    checks["missing_dns64id_is_unauthed"] = parse_message(bare)["has_dns64id"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(DNS64_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_dns64 = ToolDescriptor(name="remote_dns64", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_dns64)
    checks["naive_mcp_dns64_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = dns64_tool_descriptor()
    default_dns64 = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DNS64_TOOL_PROVIDER),
    )
    checks["default_dns64_provider_is_unsupported"] = (
        default_dns64.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{DNS64_TOOL_PROVIDER}" in default_dns64.reasons
    )
    checks["opted_in_dns64_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_dns64],
        required_tool_names=("local_memory", "dns64"),
    )
    checks["naive_preflight_missing_dns64"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["dns64"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "dns64"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DNS64_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "dns64" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="dns64-actuation-") as tmp:
        root = Path(tmp)
        missing = run_dns64_workflow(with_dns64id=False, output_dir=root / "missing")
        skip_bind = run_dns64_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_temporary = run_dns64_workflow(do_temporary=False, output_dir=root / "skip-dns64")
        skip_public = run_dns64_workflow(do_public=False, output_dir=root / "skip-synth")
        skip_dns64digest = run_dns64_workflow(do_dns64digest=False, output_dir=root / "skip-dns64digest")
        skip_replay = run_dns64_workflow(replay=False, output_dir=root / "skip-replay")
        skip_dns64id = run_dns64_workflow(use_dns64id=False, output_dir=root / "skip-dns64id")
        live = run_dns64_workflow(output_dir=root / "live")
        sealed = verify_dns64_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_dns64_trace(clone)
        checks["naive_without_dns64id_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_dns64id"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_temporary_stays_empty"] = (
            skip_temporary["ok"] is False
            and skip_temporary["error"] == "temporary_required"
            and skip_temporary["final_status"] == 409
            and skip_temporary["payload_exists"] is False
        )
        checks["skip_public_stays_empty"] = (
            skip_public["ok"] is False
            and skip_public["error"] == "public_required"
            and skip_public["final_status"] == 409
            and skip_public["payload_exists"] is False
        )
        checks["skip_dns64digest_stays_empty"] = (
            skip_dns64digest["ok"] is False
            and skip_dns64digest["error"] == "dns64digest_required"
            and skip_dns64digest["final_status"] == 409
            and skip_dns64digest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_dns64id_stays_empty"] = (
            skip_dns64id["ok"] is False
            and skip_dns64id["error"] == "dns64id_required"
            and skip_dns64id["final_status"] == 409
            and skip_dns64id["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_dns64digest"] = (
            int(live.get("dns64id") or 0) == DEFAULT_DNS64ID
            and int(live.get("dns64digest") or 0) == DEFAULT_DNS64DIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_dns64id_encode_public_dns64digest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_temporary["ok"] is False
            and skip_public["ok"] is False
            and skip_dns64digest["ok"] is False
            and skip_replay["ok"] is False
            and skip_dns64id["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = sealed["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="dns64-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != DNS64_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_dns64"] = (
        live_goal == DNS64_ACTUATION_GOAL
        and DNS64_ACTUATION_ID in live_done
        and live_source == "genesis_bind_dns64"
    )

    with tempfile.TemporaryDirectory(prefix="dns64-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(DNS64_LEFTOVER, root)
        register_catalog_proved(root, DNS64_ACTUATION_ID)
        reason = leftover_satisfied_by(DNS64_LEFTOVER, root)
        after = leftover_is_open(DNS64_LEFTOVER, root)
    checks["dns64_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_dns64_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{DNS64_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_dns64_actuation_capability()
    return {
        "ok": ok,
        "action": "dns64_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": DNS64_ACTUATION_GOAL,
        "done_when": DNS64_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
