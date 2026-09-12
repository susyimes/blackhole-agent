"""Drive a first-class Stateful TRANSLATE tool through RFC 7915 TRANSLATE/ICMP.

Tool routing already fails missions that require ``siit``: hosted
siit endpoints stay on the unsupported MCP provider, and no first-party
siit provider is executable. Unbound therefore cannot speak a TRANSLATE,
lockstep an ICMP siitid handshake over HTTP/1.0 SIITID,
independently poll the stored siitdigest, or seal a siitdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``siit`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 7915 daemon
- keep a missing-siitid client so the siit-siitid hole stays falsifiable
- refuse ICMP until a TRANSLATE lands with a non-empty siitid
- independently poll the stored siitdigest on a later client socket
- persist a sealed siitdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 8115 DHCPv6 Option for IPv4-Embedded Multicast and Unicast IPv6 Prefixes PREFIX/EMBED
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
    SIIT_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    siit_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
SIIT_ACTUATION_ID = "capability.siit-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SIIT-OK"
POLL_TOKEN = "BH-SIIT-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_SIITID = 0
EMPTY_SIITDIGEST = 0
SIIT_FIRST = 0x72  # RFC 7915 SIIT TRANSLATE
SIITID_SIZE = 4
SIITDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DEST = 0x02  # RFC 7915 icmp index
FRAME_SOURCE = 0x01  # RFC 7915 siit type
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
SIIT_LEFTOVER = (
    "Later genesis can take RFC 7915 IP/ICMP Translation Algorithm TRANSLATE/ICMP over a siitid-gated siitdigest."
)
SIIT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SIIT_ACTUATION_ID};"
    f"capability_proved:{SIIT_ACTUATION_ID};"
    "no_skill_route"
)
SIIT_ACTUATION_GOAL = (
    "Repair rfc7915 siit translate/icmp cycle cannot land over http "
    "siit siitid: hosted ip/icmp translation endpoints remain unsupported "
    "so a TRANSLATE then ICMP siitid handshake cannot land and a sealed "
    "siitdigest cannot be produced. A missing siit siitid stays forbidden; "
    "fail-closed routing never opts the siit provider in. An independent later "
    "poll of the stored siitdigest keeps the hole falsifiable. Stateless IP/ICMP "
    "translation stays fail-closed without a siitid-gated siitdigest."
)


class SiitActuationError(RuntimeError):
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
# RFC 7915 sections 3.1 and 3.2: TRANSLATE / ICMP.
RFC_SOURCE_FIELD = "TRANSLATE"
RFC_DEST_FIELD = "ICMP"
RFC_SIIT_DEST = RFC_DEST_FIELD
RFC_SOURCE_DIRECTIVE = "translate=message"
RFC_DEST_DIRECTIVE = "icmp=message"
DEFAULT_SOURCE = "TRANSLATE"
DEST_HOP = "ICMP"
SOURCE_HEADER = "TRANSLATE"
DEST_HEADER = "Icmp"
SIIT_DEST_HEADER = DEST_HEADER
RFC_SOURCE_PATH = "/siit/"
RFC_SOURCE_EMPTY = ""


def siit_directive_pair(*, local: bool = False) -> tuple[str, str]:
    """RFC 7915 TRANSLATE / ICMP directive pair."""

    if local:
        return "icmp", "message"
    return "translate", "message"


def ascii_serialize_siit_directive(*, local: bool = False) -> str:
    """RFC 7915 token "=" body-or-local."""

    name, value = siit_directive_pair(local=local)
    if not is_token(name):
        raise SiitActuationError("illegal_directive")
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
            raise SiitActuationError("short_siit")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 7915 body-unique token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_siit(policy: str | Sequence[str]) -> str:
    """Serialize RFC 7915 TRANSLATE / ICMP opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise SiitActuationError("illegal_siit")
    upper = text.upper().replace("_", "-")
    if upper in {"TRANSLATE", "TRANSLATE", "TRANSLATE-TRANSLATE"}:
        return "TRANSLATE"
    if upper in {"ICMP", "TRANSLATE-ICMP"}:
        return "ICMP"
    if upper.startswith("TRANSLATE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SiitActuationError("illegal_siit")
        return "TRANSLATE"
    if upper.startswith("ICMP="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SiitActuationError("illegal_siit")
        return "ICMP"
    raise SiitActuationError("illegal_siit")


def parse_siit(text: str) -> str:
    """Parse RFC 7915 CE opcode header extensions into CE or BR."""

    raw = str(text or "").strip()
    if not raw:
        raise SiitActuationError("illegal_siit")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"TRANSLATE", "TRANSLATE", "TRANSLATE-TRANSLATE"}:
        return "TRANSLATE"
    if upper in {"ICMP", "TRANSLATE-ICMP"}:
        return "ICMP"
    if upper.startswith("TRANSLATE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SiitActuationError("illegal_siit")
        return "TRANSLATE"
    if upper.startswith("ICMP="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SiitActuationError("illegal_siit")
        return "ICMP"
    raise SiitActuationError("illegal_siit")


def encode_siit_header(policy: str | Sequence[str]) -> bytes:
    """RFC 7915 HTTP/1.0 field as bytes."""

    return serialize_siit(policy).encode("ascii")


def parse_siit_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_siit(field_value) if field_value else DEFAULT_SOURCE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SOURCE_HEADER,
        "directive": str(policy),
        "is_first": str(policy) == "TRANSLATE",
        "table": str(policy) == "ICMP",
    }


def canonical_temporary(identity: str, siitid: int) -> str:
    """RFC 7915 body-unique advertisement bound to identity and siitid."""

    return (
        f"{serialize_siit(DEFAULT_SOURCE)}, "
        f"siit={ascii_serialize_siit_directive()}, "
        f"identity={identity}, siitid={int(siitid) & 0xFFFFFFFF}"
    )


def canonical_public(identity: str, siitid: int, siitdigest: int | None = None) -> str:
    """RFC 7915 local-message confirmation of the stored identifier-digest."""

    digest = ""
    if siitdigest is not None:
        digest = f", siitdigest={int(siitdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_siit(DEST_HOP)}, "
        f"icmp={ascii_serialize_siit_directive(local=True)}, "
        f"identity={identity}, siitid={int(siitid) & 0xFFFFFFFF}{digest}"
    )


def representation_public(identity: str, siitid: int, siitdigest: int) -> str:
    return canonical_public(identity, siitid, siitdigest)


def siit_matches(left: str, right: str) -> bool:
    return parse_siit(left) == parse_siit(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise SiitActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise SiitActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise SiitActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise SiitActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def temporary_request(identity: str, siitid: int) -> bytes:
    """HTTP CE that elicits RFC 7915 origin HTTP/1.0."""

    keyid = f"{int(siitid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"TRANSLATE /siit/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Siit-Id: {int(siitid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def public_request(identity: str, siitid: int, siitdigest: int | None = None) -> bytes:
    """HTTP BR carrying RFC 7915 local-message confirmation of the stored identifier-digest."""

    keyid = f"{int(siitid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if siitdigest is not None:
        extra = f"Siit-Digest: {int(siitdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"ICMP /siit/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Siit-Id: {int(siitid) & 0xFFFFFFFF}\r\n"
        "Icmp-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    disc_kind = "icmp" if fields.get("icmp-confirm") == "1" else "translate"
    upgrade_field = fields.get("translate") or fields.get("siit") or ""
    policy = parse_siit(upgrade_field) if upgrade_field else ()
    return {
        "kind": "siit",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "disc_kind": disc_kind,
        "policy": policy,
        "siitid": int(fields["siit-id"]) if fields.get("siit-id") else EMPTY_SIITID,
        "siitdigest": int(fields["siit-digest"]) if fields.get("siit-digest") else EMPTY_SIITDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def temporary_response(identity: str, siitid: int, siitdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 7915 origin HTTP/1.0, carrying the stored siitdigest."""

    publicised = serialize_siit(DEFAULT_SOURCE)
    payload = bytes(body or canonical_temporary(identity, siitid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"TRANSLATE: {publicised}\r\n"
        f"Siit-Id: {int(siitid) & 0xFFFFFFFF}\r\n"
        f"Siit-Digest: {int(siitdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def public_response(identity: str, siitid: int, siitdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 7915 BR, carrying the stored identifier-digest."""

    publicised = serialize_siit(DEST_HOP)
    payload = bytes(body or representation_public(identity, siitid, siitdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"TRANSLATE: {publicised}\r\n"
        f"Siit-Id: {int(siitid) & 0xFFFFFFFF}\r\n"
        f"Siit-Digest: {int(siitdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/siit-icmp\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise SiitActuationError("illegal_content_length") from error
    field_value = fields.get("translate") or fields.get("siit") or ""
    policy = parse_siit(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/siit-icmp" or policy == DEST_HOP:
        status = 200
        disc_kind = "icmp"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        disc_kind = "translate"
    else:
        status = 0
        disc_kind = "translate"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "disc_kind": disc_kind,
        "policy": policy,
        "siitid": int(fields["siit-id"]) if fields.get("siit-id") else EMPTY_SIITID,
        "siitdigest": int(fields["siit-digest"]) if fields.get("siit-digest") else EMPTY_SIITDIGEST,
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
        raise SiitActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise SiitActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise SiitActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise SiitActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc7915_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    ula: str,
) -> str:
    """RFC 7915 identifier digest over method, router-IP, identity, and siitid."""

    payload = f"{method}:{ula}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def temporary_siitid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"siitid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_siitid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-siitid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def temporary_siitdigest(siitid: int = EMPTY_SIITID, token: str = SENTINEL) -> int:
    nonce = f"{int(siitid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc7915_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="ICMP",
        ula=f"/siit/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_SIITID = temporary_siitid(SENTINEL)
DEFAULT_SIITDIGEST = temporary_siitdigest(DEFAULT_SIITID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    siitid: int,
    siitdigest: int,
    include_siitid: bool = True,
) -> bytes:
    live_siitid = int(siitid) & 0xFFFFFFFF if include_siitid else EMPTY_SIITID
    live_digest = int(siitdigest) & 0xFFFFFFFF if include_siitid and live_siitid else EMPTY_SIITDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_siitid) if live_siitid else b""
    header = bytearray()
    header.append(SIIT_FIRST)
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
    siitid: int,
    siitdigest: int | None = None,
    include_siitid: bool = True,
) -> bytes:
    live_siitid = int(siitid) & 0xFFFFFFFF if include_siitid else EMPTY_SIITID
    live_digest = int(siitdigest) if siitdigest is not None else temporary_siitdigest(live_siitid, identity)
    return encode_packet(
        FRAME_SOURCE,
        identity=identity,
        siitid=live_siitid,
        siitdigest=live_digest,
        include_siitid=include_siitid,
    )


def encode_public(
    *,
    identity: str,
    siitid: int,
    siitdigest: int | None = None,
    include_siitid: bool = True,
) -> bytes:
    live_siitid = int(siitid) & 0xFFFFFFFF if include_siitid else EMPTY_SIITID
    live_digest = int(siitdigest) if siitdigest is not None else temporary_siitdigest(live_siitid, identity)
    return encode_packet(
        FRAME_DEST,
        identity=identity,
        siitid=live_siitid,
        siitdigest=live_digest,
        include_siitid=include_siitid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise SiitActuationError("short_packet")
    disc = raw[0]
    if disc != SIIT_FIRST:
        raise SiitActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise SiitActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == SIITID_SIZE:
        live_siitid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_siitid = EMPTY_SIITID
    else:
        raise SiitActuationError("illegal_siitid")
    if offset >= len(raw):
        raise SiitActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SOURCE, FRAME_DEST}:
        raise SiitActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise SiitActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise SiitActuationError("checksum_failed")
    if len(payload) < 5:
        raise SiitActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise SiitActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_siitid = int(live_siitid) != EMPTY_SIITID
    has_siitdigest = has_siitid and int(live_digest) != EMPTY_SIITDIGEST
    is_temporary = frame_type == FRAME_SOURCE
    is_public = frame_type == FRAME_DEST
    return {
        "type": int(frame_type),
        "is_temporary": is_temporary,
        "is_public": is_public,
        "siitid": int(live_siitid),
        "has_siitid": has_siitid,
        "siitdigest": int(live_digest),
        "has_siitdigest": has_siitdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(disc),
        "mech_len": int(mech_len),
        "http_state": "RFC7915",
        "serialize_field": canonical_temporary(identity, live_siitid) if has_siitid else "",
        "tls_field": canonical_public(identity, live_siitid, live_digest) if has_siitdigest else "",
    }


class SiitClient:
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
            raise SiitActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_public"] or not packet["is_public"]:
            raise SiitActuationError("siitdigest_required")
        if not packet["has_siitid"]:
            raise SiitActuationError("siitid_required")
        if not packet["has_siitdigest"]:
            raise SiitActuationError("siitdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_siitdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_siitdigest:
            raise SiitActuationError("siitdigest_required")
        session = self._recv()
        return {
            "session": session,
            "siitid": int(session.get("siitid") or EMPTY_SIITID),
            "identity": str(session.get("identity") or ""),
            "siitdigest": int(session.get("siitdigest") or EMPTY_SIITDIGEST),
        }

    def local(
        self,
        identity: str,
        siitid: int,
        siitdigest: int = EMPTY_SIITDIGEST,
        *,
        wait_siitdigest: bool = True,
        include_siitid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_public(
            identity=identity,
            siitid=siitid,
            siitdigest=siitdigest or temporary_siitdigest(siitid, identity),
            include_siitid=include_siitid,
        )
        return self.exchange(packet, wait_siitdigest=wait_siitdigest)


class SiitSession:
    """SIITID-gated loopback RFC 7915 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        siitid_gate: int = DEFAULT_SIITID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.siitid_gate = int(siitid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.siitid = EMPTY_SIITID
        self.siitdigest = EMPTY_SIITDIGEST
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

    def store_siitid_once(self, identity: str, siitid: int, siitdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(siitid or EMPTY_SIITID)
            live_digest = int(siitdigest or EMPTY_SIITDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.siitid = live
                self.siitdigest = live_digest or temporary_siitdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.siitid), int(self.siitdigest)

    def read_siitid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.siitid), int(self.siitdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "siitid": EMPTY_SIITID,
            "siitdigest": EMPTY_SIITDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _siitid_missing(self) -> bool:
        return not int(self.siitid_gate or 0)

    def _public_tuple(self, peer: tuple[str, int], identity: str, siitid: int, siitdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_public(
            identity=identity,
            siitid=siitid,
            siitdigest=siitdigest,
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
            except SiitActuationError:
                continue
            if not packet.get("is_temporary") and not packet.get("is_public"):
                continue
            if not packet.get("has_siitid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_siitid, stored_digest = self.store_siitid_once(
                identity,
                int(packet.get("siitid") or EMPTY_SIITID),
                int(packet.get("siitdigest") or EMPTY_SIITDIGEST),
            )
            if not stored_name or not stored_siitid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_temporary"):
                    self.opened = True
                if packet.get("is_public"):
                    self.handshook = True
                self.retrieved = True
            self._public_tuple(peer, stored_name, stored_siitid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._siitid_missing():
            return self._forbidden("missing_siitid")
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
        do_siitdigest: bool = True,
        replay: bool = True,
        use_siitid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._siitid_missing():
            return self._forbidden("missing_siitid")
        live_token = str(token or SENTINEL)
        origin_siitid = temporary_siitid(live_token)
        origin_digest = temporary_siitdigest(origin_siitid, live_token)
        client: SiitClient | None = None
        independent: SiitClient | None = None
        try:
            client = SiitClient(self.host, int(self.port))
            if not do_temporary:
                return self._conflict("temporary_required")
            bind_packet = encode_temporary(
                identity=live_token,
                siitid=origin_siitid,
                siitdigest=origin_digest,
                include_siitid=use_siitid,
            )
            if not use_siitid:
                try:
                    client.exchange(bind_packet, wait_siitdigest=True)
                except SiitActuationError:
                    return self._conflict("siitid_required")
                return self._conflict("siitid_required")
            client.send(bind_packet)
            if not do_public:
                return self._conflict("public_required")
            proxy_packet = encode_public(
                identity=live_token,
                siitid=origin_siitid,
                siitdigest=origin_digest,
                include_siitid=True,
            )
            if not do_siitdigest:
                try:
                    client.exchange(proxy_packet, wait_siitdigest=False)
                except SiitActuationError as error:
                    if str(error) == "siitdigest_required":
                        return self._conflict("siitdigest_required")
                    return self._conflict("siitdigest_required")
                return self._conflict("siitdigest_required")
            try:
                session = client.exchange(proxy_packet, wait_siitdigest=True)
            except SiitActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("siitid_required")
                if reason == "siitdigest_required":
                    return self._conflict("siitdigest_required")
                return self._conflict("temporary_required")
            if str(session.get("identity") or "") != live_token:
                return self._conflict("temporary_required")
            if int(session.get("siitid") or EMPTY_SIITID) != origin_siitid:
                return self._conflict("siitdigest_required")
            if int(session.get("siitdigest") or EMPTY_SIITDIGEST) != origin_digest:
                return self._conflict("siitdigest_required")
            self.retrieved = True
            if replay:
                independent = SiitClient(self.host, int(self.port))
                try:
                    poll = independent.local(
                        POLL_TOKEN,
                        poll_siitid(live_token),
                        temporary_siitdigest(poll_siitid(live_token), POLL_TOKEN),
                        wait_siitdigest=True,
                    )
                except SiitActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_siitid, stored_digest = self.read_siitid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_siitid != origin_siitid
                    or stored_digest != origin_digest
                    or int(poll.get("siitid") or EMPTY_SIITID) != origin_siitid
                    or int(poll.get("siitdigest") or EMPTY_SIITDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_siitid}:{origin_digest}:{live_token}:{canonical_temporary(live_token, origin_siitid)}:{canonical_public(live_token, origin_siitid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "siitid": origin_siitid,
                "siitdigest": origin_digest,
                "temporary_frame": True,
                "public_frame": True,
                "siitdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "siitid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_siitdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "siitid": origin_siitid,
                "siitdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "temporary_frame": True,
                "public_frame": True,
                "siitdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "siitid_bound": True,
            }
        except (OSError, SiitActuationError) as error:
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
        live = independent_siitdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "siitid": int(live.get("siitid") or EMPTY_SIITID),
            "siitdigest": int(live.get("siitdigest") or EMPTY_SIITDIGEST),
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


def call_siit_tool(session: SiitSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one siit tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_temporary = True if arguments.get("translate") is None else bool(arguments.get("translate"))
    do_public = True if arguments.get("icmp") is None else bool(arguments.get("icmp"))
    do_siitdigest = True if arguments.get("siitdigest") is None else bool(arguments.get("siitdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_siitid = True if arguments.get("use_siitid") is None else bool(arguments.get("use_siitid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_temporary=do_temporary,
            do_public=do_public,
            do_siitdigest=do_siitdigest,
            replay=replay,
            use_siitid=use_siitid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SiitActuationError(f"unsupported siit action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_siitdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage siitdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "siitid": EMPTY_SIITID,
        "siitdigest": EMPTY_SIITDIGEST,
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
            "siitdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "siitid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    siitid = int(payload.get("siitid") or EMPTY_SIITID)
    siitdigest = int(payload.get("siitdigest") or EMPTY_SIITDIGEST)
    dual = port > 0 and bool(siitid) and bool(siitdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "siitid": siitid,
        "siitdigest": siitdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "temporary_frame": payload.get("temporary_frame") is True,
        "public_frame": payload.get("public_frame") is True,
        "siitdigest_locate": payload.get("siitdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "siitid_bound": payload.get("siitid_bound") is True,
    }


def run_siit_workflow(
    *,
    with_siitid: bool = True,
    skip_bind: bool = False,
    do_temporary: bool = True,
    do_public: bool = True,
    do_siitdigest: bool = True,
    replay: bool = True,
    use_siitid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 7915 TRANSLATE/ICMP siitid cycle workflow."""

    descriptor = siit_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIIT_TOOL_PROVIDER),
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
        raise SiitActuationError(f"siit tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="siit-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SiitSession(out, siitid_gate=DEFAULT_SIITID if with_siitid else EMPTY_SIITID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "translate": do_temporary,
            "icmp": do_public,
            "siitdigest": do_siitdigest,
            "replay": replay,
            "use_siitid": use_siitid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_siit_tool(session, arguments))
            except SiitActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_siitdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_siitid
        and not skip_bind
        and do_temporary
        and do_public
        and do_siitdigest
        and replay
        and use_siitid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "siit_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_siitid": with_siitid,
        "skip_bind": skip_bind,
        "temporary_frame": do_temporary,
        "public_frame": do_public,
        "siitdigest": do_siitdigest,
        "replay": replay,
        "use_siitid": use_siitid,
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
        "siitid_value": int(publish_result.get("siitid") or independent.get("siitid") or EMPTY_SIITID),
        "siitdigest_value": int(publish_result.get("siitdigest") or independent.get("siitdigest") or EMPTY_SIITDIGEST),
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
        "siitid": int(trace_body["siitid_value"] or EMPTY_SIITID),
        "siitdigest": int(trace_body["siitdigest_value"] or EMPTY_SIITDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_siitid": with_siitid,
        "skip_bind": skip_bind,
        "temporary_cycle": do_temporary,
        "public_cycle": do_public,
        "siitdigest_cycle": do_siitdigest,
        "replay": replay,
        "use_siitid": use_siitid,
    }


def verify_siit_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_siitdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    siitid = int(trace.get("siitid_value") or independent.get("siitid") or EMPTY_SIITID)
    siitdigest = int(trace.get("siitdigest_value") or independent.get("siitdigest") or EMPTY_SIITDIGEST)
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
        "siitdigest_locate": independent.get("siitdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "siitid_bound": independent.get("siitid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "siitdigest_recorded": (
            port > 0
            and siitid == DEFAULT_SIITID
            and siitdigest == DEFAULT_SIITDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def siit_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.siit_actuation import "
        "builtin_siit_actuation_proof; r=builtin_siit_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='siit_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_siit_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SIIT_ACTUATION_ID,
        name="First-class RFC 7915 IP/ICMP Translation Algorithm TRANSLATE/ICMP actuation",
        description=(
            "Missions that require a siit tool can opt the siit provider in, "
            "bind a loopback RFC 7915 IP/ICMP Translation Algorithm endpoint, complete a TRANSLATE "
            "with a non-empty siitid, lockstep an ICMP that carries the "
            "stored siitdigest, independently poll the stored siitdigest "
            "on a later socket, and seal a digest-chained siitdigest. Default "
            "routing stays fail-closed; a missing siitid keeps the hole "
            "falsifiable, and skip-TRANSLATE/ICMP/siitdigest/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.siit_actuation:builtin_siit_actuation_proof",
        proof_command=siit_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.prefix64-actuation",
            "capability.m46-actuation",
            "capability.ucpe-actuation",
            "capability.s46-actuation",
            "capability.mapt-actuation",
            "capability.mape-actuation",
            "capability.lw4o6-actuation",
            "capability.dslite-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/siit_actuation.py",
            "src/blackhole_agent/ucpe_actuation.py",
            "src/blackhole_agent/s46_actuation.py",
            "src/blackhole_agent/lw4o6_actuation.py",
            "src/blackhole_agent/dslite_actuation.py",
            "src/blackhole_agent/disc_actuation.py",
            "src/blackhole_agent/xlat_actuation.py",
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
            "src/blackhole_agent/m46_actuation.py",
            "src/blackhole_agent/prefix64_actuation.py",
            "src/blackhole_agent/eam_actuation.py",
            "src/blackhole_agent/mapt_actuation.py",
            "src/blackhole_agent/mape_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required siit tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 7915 daemon, speaks a "
            "TRANSLATE then ICMP over IP/ICMP Translation Algorithm with a non-empty siitid and "
            "siitdigest, independently polls the stored siitdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 8115 DHCPv6 Option for IPv4-Embedded Multicast and Unicast IPv6 Prefixes PREFIX/EMBED lockstep is proved. "
            "Missing siitids, skip-TRANSLATE, skip-ICMP, skip-siitdigest, skip-REPLAY, "
            "and a TRANSLATE aimed without a siitid stay fail-closed. "
            "Later genesis can take RFC 7757 Explicit Address Mappings for Stateless IP/ICMP Translation EXPLICIT/MAPPING as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("siit", "rfc7915", "http", "siitid", "siitdigest", "translate", "icmp", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260907T134117Z-4cfd9f6c",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_siit_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 7915 translate/icmp lockstep actuation seals a siitdigest."""

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
    from blackhole_agent.s46_actuation import (
        S46_ACTUATION_GOAL,
        S46_ACTUATION_ID,
    )
    from blackhole_agent.ucpe_actuation import (
        UCPE_ACTUATION_GOAL,
        UCPE_ACTUATION_ID,
    )
    from blackhole_agent.m46_actuation import (
        M46_ACTUATION_GOAL,
        M46_ACTUATION_ID,
    )
    from blackhole_agent.eam_actuation import (
        EAM_ACTUATION_GOAL,
        EAM_ACTUATION_ID,
    )
    from blackhole_agent.prefix64_actuation import (
        PREFIX64_ACTUATION_GOAL,
        PREFIX64_ACTUATION_ID,
    )
    from blackhole_agent.mapt_actuation import (
        MAPT_ACTUATION_GOAL,
        MAPT_ACTUATION_ID,
    )
    from blackhole_agent.mape_actuation import (
        MAPE_ACTUATION_GOAL,
        MAPE_ACTUATION_ID,
    )
    from blackhole_agent.lw4o6_actuation import (
        LW4O6_ACTUATION_GOAL,
        LW4O6_ACTUATION_ID,
    )
    from blackhole_agent.dslite_actuation import (
        DSLITE_ACTUATION_GOAL,
        DSLITE_ACTUATION_ID,
    )
    from blackhole_agent.disc_actuation import (
        DISC_ACTUATION_GOAL,
        DISC_ACTUATION_ID,
    )
    from blackhole_agent.xlat_actuation import (
        XLAT_ACTUATION_GOAL,
        XLAT_ACTUATION_ID,
    )
    from blackhole_agent.dns64_actuation import (
        DNS64_ACTUATION_GOAL,
        DNS64_ACTUATION_ID,
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
        semantic_tokens,
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
    checks["denylists_self"] = SIIT_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SIIT_ACTUATION_GOAL) == (
        SIIT_ACTUATION_ID,
    )
    checks["leftover_text_binds_siit"] = leftover_marker_ids(SIIT_LEFTOVER) == (
        SIIT_ACTUATION_ID,
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
        (S46_ACTUATION_GOAL, S46_ACTUATION_ID, "s46"),
        (UCPE_ACTUATION_GOAL, UCPE_ACTUATION_ID, "ucpe"),
        (M46_ACTUATION_GOAL, M46_ACTUATION_ID, "m46"),
        (PREFIX64_ACTUATION_GOAL, PREFIX64_ACTUATION_ID, "prefix64"),
        (EAM_ACTUATION_GOAL, EAM_ACTUATION_ID, "eam"),
        (MAPT_ACTUATION_GOAL, MAPT_ACTUATION_ID, "mapt"),
        (MAPE_ACTUATION_GOAL, MAPE_ACTUATION_ID, "mape"),
        (LW4O6_ACTUATION_GOAL, LW4O6_ACTUATION_ID, "lw4o6"),
        (DSLITE_ACTUATION_GOAL, DSLITE_ACTUATION_ID, "dslite"),
        (DISC_ACTUATION_GOAL, DISC_ACTUATION_ID, "disc"),
        (XLAT_ACTUATION_GOAL, XLAT_ACTUATION_ID, "xlat"),
        (DNS64_ACTUATION_GOAL, DNS64_ACTUATION_ID, "dns64"),
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
        checks[f"{name}_goal_is_not_siit"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"siit_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            SIIT_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = SIIT_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    publicised = serialize_siit(DEFAULT_SOURCE)
    rebuilt = serialize_siit(parse_siit(publicised))
    preloaded = parse_siit(RFC_SIIT_DEST)
    header = encode_siit_header(DEFAULT_SOURCE)
    parsed_header = parse_siit_header(header)
    asked = parse_http_request(temporary_request(SENTINEL, DEFAULT_SIITID))
    preload_req = parse_http_request(public_request(SENTINEL, DEFAULT_SIITID, DEFAULT_SIITDIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_SIITID, DEFAULT_SIITDIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_SIITID, DEFAULT_SIITDIGEST)
    )
    checks["siit_roundtrip"] = (
        parse_siit(publicised) == DEFAULT_SOURCE
        and hmac.compare_digest(rebuilt, publicised)
        and publicised == RFC_SOURCE_FIELD
        and is_token("TRANSLATE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SOURCE_FIELD
        and parsed_header["policy"] == DEFAULT_SOURCE
        and parsed_header["header"] == SOURCE_HEADER
        and parsed_header["is_first"] is True
        and parsed_header["table"] is False
        and preloaded == DEST_HOP
        and ascii_serialize_siit_directive() == RFC_SOURCE_DIRECTIVE
        and siit_directive_pair() == ("translate", "message")
        and RFC_SOURCE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_siit(DEST_HOP) == RFC_SIIT_DEST
        and DEFAULT_SIITDIGEST == temporary_siitdigest(DEFAULT_SIITID, SENTINEL)
        and "siitdigest=" in canonical_public(SENTINEL, DEFAULT_SIITID, DEFAULT_SIITDIGEST)
        and canonical_temporary(SENTINEL, DEFAULT_SIITID).startswith("TRANSLATE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "TRANSLATE"
        and asked["disc_kind"] == "translate"
        and asked["siitid"] == DEFAULT_SIITID
        and preload_req["disc_kind"] == "icmp"
        and preload_req["siitdigest"] == DEFAULT_SIITDIGEST
        and got["status"] == 200
        and preload_public["status"] == 200
        and got["disc_kind"] == "translate"
        and preload_public["disc_kind"] == "icmp"
        and got["policy"] == DEFAULT_SOURCE
        and preload_public["policy"] == DEST_HOP
        and got["content_length_matches_body"] is True
        and preload_public["content_length_matches_body"] is True
        and got["siitdigest"] == DEFAULT_SIITDIGEST
        and preload_public["siitdigest"] == DEFAULT_SIITDIGEST
        and siit_matches(serialize_siit(got["policy"]), publicised)
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
    checks["catalog_names_disc"] = (
        len(catalog) > 137
        and catalog[137]["id"] == DISC_ACTUATION_ID
        and catalog[137]["source"] == "genesis_bind_disc"
    )
    checks["catalog_names_dslite"] = (
        len(catalog) > 138
        and catalog[138]["id"] == DSLITE_ACTUATION_ID
        and catalog[138]["source"] == "genesis_bind_dslite"
    )
    checks["catalog_names_lw4o6"] = (
        len(catalog) > 139
        and catalog[139]["id"] == LW4O6_ACTUATION_ID
        and catalog[139]["source"] == "genesis_bind_lw4o6"
    )
    checks["catalog_names_mape"] = (
        len(catalog) > 140
        and catalog[140]["id"] == MAPE_ACTUATION_ID
        and catalog[140]["source"] == "genesis_bind_mape"
    )
    checks["catalog_names_mapt"] = (
        len(catalog) > 141
        and catalog[141]["id"] == MAPT_ACTUATION_ID
        and catalog[141]["source"] == "genesis_bind_mapt"
    )
    checks["catalog_names_s46"] = (
        len(catalog) > 142
        and catalog[142]["id"] == S46_ACTUATION_ID
        and catalog[142]["source"] == "genesis_bind_s46"
    )
    checks["catalog_names_ucpe"] = (
        len(catalog) > 143
        and catalog[143]["id"] == UCPE_ACTUATION_ID
        and catalog[143]["source"] == "genesis_bind_ucpe"
    )
    checks["catalog_names_m46"] = (
        len(catalog) > 144
        and catalog[144]["id"] == M46_ACTUATION_ID
        and catalog[144]["source"] == "genesis_bind_m46"
    )
    checks["catalog_names_prefix64"] = (
        len(catalog) > 145
        and catalog[145]["id"] == PREFIX64_ACTUATION_ID
        and catalog[145]["source"] == "genesis_bind_prefix64"
    )
    checks["catalog_names_siit"] = (
        len(catalog) > 146
        and catalog[146]["id"] == SIIT_ACTUATION_ID
        and catalog[146]["source"] == "genesis_bind_siit"
    )
    checks["catalog_names_eam"] = (
        len(catalog) > 147
        and catalog[147]["id"] == EAM_ACTUATION_ID
        and catalog[147]["source"] == "genesis_bind_eam"
    )
    family = capability_family(SIIT_ACTUATION_GOAL)
    checks["family_is_siit"] = "siit" in family.split("/")
    checks["family_is_siit_surface"] = "siit" in family.split("/") and "siitid" in set(semantic_tokens(SIIT_ACTUATION_GOAL))
    checks["family_is_siitid"] = "siitid" in set(semantic_tokens(SIIT_ACTUATION_GOAL))
    checks["family_is_rfc7915"] = "rfc7915" in family
    checks["family_is_siitdigest"] = "siitdigest" in set(semantic_tokens(SIIT_ACTUATION_GOAL))
    checks["family_is_not_ucpe"] = (
        "ucpe" not in family.split("/")
        and "rfc8026" not in family
        and "ucpeid" not in family
        and "ucpedigest" not in family
    )
    checks["family_is_not_prefix64"] = (
        "prefix64" not in family.split("/")
        and "rfc8115" not in family
        and "prefix64id" not in family
        and "prefix64digest" not in family
    )
    checks["family_is_not_m46"] = (
        "m46" not in family.split("/")
        and "rfc8114" not in family
        and "m46id" not in family
        and "m46digest" not in family
    )
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
    checks["family_is_not_s46"] = (
        "s46" not in family.split("/")
        and "rfc7598" not in family
        and "s46id" not in family
        and "s46digest" not in family
    )
    checks["family_is_not_eam"] = (
        "eam" not in family.split("/")
        and "rfc7757" not in family
        and "eamid" not in family
        and "eamdigest" not in family
    )
    checks["family_is_not_mapt"] = (
        "mapt" not in family.split("/")
        and "rfc7599" not in family
        and "maptid" not in family
        and "maptdigest" not in family
    )
    checks["family_is_not_mape"] = (
        "mape" not in family.split("/")
        and "rfc7597" not in family
        and "mapeid" not in family
        and "mapedigest" not in family
    )
    checks["family_is_not_lw4o6"] = (
        "lw4o6" not in family.split("/")
        and "rfc7596" not in family
        and "lw4o6id" not in family
        and "lw4o6digest" not in family
    )
    checks["family_is_not_dslite"] = (
        "dslite" not in family.split("/")
        and "rfc6333" not in family
        and "dsliteid" not in family
        and "dslitedigest" not in family
    )
    checks["family_is_not_disc"] = (
        "disc" not in family.split("/")
        and "rfc7050" not in family
        and "discid" not in family
        and "discdigest" not in family
    )
    checks["family_is_not_xlat"] = (
        "xlat" not in family.split("/")
        and "rfc6877" not in family
        and "clatid" not in family
        and "clatdigest" not in family
    )
    checks["family_is_not_dns64"] = (
        "dns64" not in family.split("/")
        and "rfc6147" not in family
        and "dns64id" not in family
        and "dns64digest" not in family
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
        "ipid" not in family.split("/")
        and "ipdigest" not in family.split("/")
        and "rfc791" not in family.split("/")
    )
    checks["family_is_not_tcp"] = (
        "tcp" not in family.split("/")
        and "rfc793" not in family
        and "tcpid" not in family
        and "tcpdigest" not in family
    )
    checks["family_is_not_icmp"] = (
        "rfc792" not in family.split("/")
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
    packed = encode_temporary(identity=SENTINEL, siitid=DEFAULT_SIITID, siitdigest=DEFAULT_SIITDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_temporary"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_siitid"] is True
        and parsed["siitid"] == DEFAULT_SIITID
        and parsed["siitdigest"] == DEFAULT_SIITDIGEST
        and parsed["is_public"] is False
        and parsed["is_public"] is False
        and parsed["type"] == FRAME_SOURCE
        and parsed["first_byte"] == SIIT_FIRST
    )
    shook = encode_public(
        identity=SENTINEL,
        siitid=DEFAULT_SIITID,
        siitdigest=DEFAULT_SIITDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_public"] is True
        and answer_parsed["is_public"] is True
        and answer_parsed["is_temporary"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["siitid"] == DEFAULT_SIITID
        and answer_parsed["siitdigest"] == DEFAULT_SIITDIGEST
        and answer_parsed["has_siitdigest"] is True
        and answer_parsed["type"] == FRAME_DEST
        and answer_parsed["first_byte"] == SIIT_FIRST
    )
    bare = encode_temporary(identity=SENTINEL, siitid=DEFAULT_SIITID, include_siitid=False)
    checks["missing_siitid_is_unauthed"] = parse_message(bare)["has_siitid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(SIIT_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_siit = ToolDescriptor(name="remote_siit", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_siit)
    checks["naive_mcp_siit_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = siit_tool_descriptor()
    default_siit = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIIT_TOOL_PROVIDER),
    )
    checks["default_siit_provider_is_unsupported"] = (
        default_siit.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SIIT_TOOL_PROVIDER}" in default_siit.reasons
    )
    checks["opted_in_siit_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_siit],
        required_tool_names=("local_memory", "siit"),
    )
    checks["naive_preflight_missing_siit"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["siit"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "siit"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIIT_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "siit" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="siit-actuation-") as tmp:
        root = Path(tmp)
        missing = run_siit_workflow(with_siitid=False, output_dir=root / "missing")
        skip_bind = run_siit_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_temporary = run_siit_workflow(do_temporary=False, output_dir=root / "skip-translate")
        skip_public = run_siit_workflow(do_public=False, output_dir=root / "skip-icmp")
        skip_siitdigest = run_siit_workflow(do_siitdigest=False, output_dir=root / "skip-siitdigest")
        skip_replay = run_siit_workflow(replay=False, output_dir=root / "skip-replay")
        skip_siitid = run_siit_workflow(use_siitid=False, output_dir=root / "skip-siitid")
        live = run_siit_workflow(output_dir=root / "live")
        sealed = verify_siit_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_siit_trace(clone)
        checks["naive_without_siitid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_siitid"
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
        checks["skip_siitdigest_stays_empty"] = (
            skip_siitdigest["ok"] is False
            and skip_siitdigest["error"] == "siitdigest_required"
            and skip_siitdigest["final_status"] == 409
            and skip_siitdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_siitid_stays_empty"] = (
            skip_siitid["ok"] is False
            and skip_siitid["error"] == "siitid_required"
            and skip_siitid["final_status"] == 409
            and skip_siitid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_siitdigest"] = (
            int(live.get("siitid") or 0) == DEFAULT_SIITID
            and int(live.get("siitdigest") or 0) == DEFAULT_SIITDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_siitid_encode_public_siitdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_temporary["ok"] is False
            and skip_public["ok"] is False
            and skip_siitdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_siitid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = sealed["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="siit-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SIIT_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, SIIT_ACTUATION_GOAL, SIIT_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_siit"] = (
        not gate.accepted
        and live_goal != SIIT_ACTUATION_GOAL
        and SIIT_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_siit"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="siit-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(SIIT_LEFTOVER, root)
        register_catalog_proved(root, SIIT_ACTUATION_ID)
        reason = leftover_satisfied_by(SIIT_LEFTOVER, root)
        after = leftover_is_open(SIIT_LEFTOVER, root)
    checks["siit_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_siit_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{SIIT_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_siit_actuation_capability()
    return {
        "ok": ok,
        "action": "siit_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SIIT_ACTUATION_GOAL,
        "done_when": SIIT_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
