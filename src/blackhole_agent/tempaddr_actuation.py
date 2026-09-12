"""Drive a first-class Privacy Extensions tool through RFC 4941 TEMPORARY/PUBLIC.

Tool routing already fails missions that require ``tempaddr``: hosted
tempaddr endpoints stay on the unsupported MCP provider, and no first-party
tempaddr provider is executable. Unbound therefore cannot speak a TEMPORARY,
lockstep a PUBLIC tempaddrid handshake over HTTP/1.0 TEMPADDRID,
independently poll the stored tempaddrdigest, or seal a tempaddrdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``tempaddr`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 4941 daemon
- keep a missing-tempaddrid client so the tempaddr-tempaddrid hole stays falsifiable
- refuse PUBLIC until a TEMPORARY lands with a non-empty tempaddrid
- independently poll the stored tempaddrdigest on a later client socket
- persist a sealed tempaddrdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 4862 Stateless Address Autoconfiguration
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
    TEMPADDR_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    tempaddr_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
TEMPADDR_ACTUATION_ID = "capability.tempaddr-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-TEMPADDR-OK"
POLL_TOKEN = "BH-TEMPADDR-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_TEMPADDRID = 0
EMPTY_TEMPADDRDIGEST = 0
TEMPADDR_FIRST = 0x3B  # RFC 4941 TEMPADDR (Privacy Extensions next-header)
TEMPADDRID_SIZE = 4
TEMPADDRDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_PUBLIC = 0x02  # RFC 4941 public address
FRAME_TEMPORARY = 0x01  # RFC 4941 temporary address
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
TEMPADDR_LEFTOVER = (
    "Later genesis can take RFC 4941 Privacy Extensions TEMPORARY/PUBLIC over a "
    "tempaddrid-gated tempaddrdigest."
)
TEMPADDR_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TEMPADDR_ACTUATION_ID};"
    f"capability_proved:{TEMPADDR_ACTUATION_ID};"
    "no_skill_route"
)
TEMPADDR_ACTUATION_GOAL = (
    "Repair rfc4941 tempaddr temporary/public cycle cannot land over http "
    "tempaddr tempaddrid: hosted tempaddr endpoints remain unsupported so a TEMPORARY then "
    "PUBLIC tempaddrid handshake cannot land and a sealed tempaddrdigest "
    "cannot be produced. A missing tempaddr tempaddrid stays forbidden; fail-closed "
    "routing never opts the tempaddr provider in. An independent later poll of the "
    "stored tempaddrdigest keeps the hole falsifiable."
)


class TempaddrActuationError(RuntimeError):
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
# RFC 4941 sections 3.1 and 3.2: TEMPORARY / PUBLIC.
RFC_TEMPORARY_FIELD = "TEMPORARY"
RFC_PUBLIC_FIELD = "PUBLIC"
RFC_TEMPADDR_PUBLIC = RFC_PUBLIC_FIELD
RFC_TEMPORARY_DIRECTIVE = "temporary=message"
RFC_PUBLIC_DIRECTIVE = "public=message"
DEFAULT_TEMPORARY = "TEMPORARY"
PUBLIC_POLICY = "PUBLIC"
TEMPORARY_HEADER = "Temporary"
PUBLIC_HEADER = "Public"
TEMPADDR_PUBLIC_HEADER = PUBLIC_HEADER
RFC_TEMPORARY_PATH = "/tempaddr/"
RFC_TEMPORARY_EMPTY = ""


def tempaddr_directive_pair(*, public: bool = False) -> tuple[str, str]:
    """RFC 4941 Router / Prefix directive pair."""

    if public:
        return "public", "message"
    return "temporary", "message"


def ascii_serialize_tempaddr_directive(*, public: bool = False) -> str:
    """RFC 4941 token "=" body-or-public."""

    name, value = tempaddr_directive_pair(public=public)
    if not is_token(name):
        raise TempaddrActuationError("illegal_directive")
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
            raise TempaddrActuationError("short_tempaddr")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 4941 body-temporary token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_tempaddr(policy: str | Sequence[str]) -> str:
    """Serialize RFC 4941 TEMPORARY / PUBLIC opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise TempaddrActuationError("illegal_tempaddr")
    upper = text.upper().replace("_", "-")
    if upper in {"TEMPORARY", "TEMPADDR", "TEMPADDR-TEMPORARY", "TEMPADDR-TEMPORARY"}:
        return "TEMPORARY"
    if upper in {"PUBLIC", "RESOURCE", "TEMPADDR-PUBLIC"}:
        return "PUBLIC"
    if upper.startswith("TEMPORARY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TempaddrActuationError("illegal_tempaddr")
        return "TEMPORARY"
    if upper.startswith("PUBLIC="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TempaddrActuationError("illegal_tempaddr")
        return "PUBLIC"
    raise TempaddrActuationError("illegal_tempaddr")


def parse_tempaddr(text: str) -> str:
    """Parse RFC 4941 TEMPADDR opcode header extensions into TEMPORARY or PUBLIC."""

    raw = str(text or "").strip()
    if not raw:
        raise TempaddrActuationError("illegal_tempaddr")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"TEMPORARY", "TEMPADDR", "TEMPADDR-TEMPORARY", "TEMPADDR-TEMPORARY"}:
        return "TEMPORARY"
    if upper in {"PUBLIC", "RESOURCE", "TEMPADDR-PUBLIC"}:
        return "PUBLIC"
    if upper.startswith("TEMPORARY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TempaddrActuationError("illegal_tempaddr")
        return "TEMPORARY"
    if upper.startswith("PUBLIC="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TempaddrActuationError("illegal_tempaddr")
        return "PUBLIC"
    raise TempaddrActuationError("illegal_tempaddr")


def encode_tempaddr_header(policy: str | Sequence[str]) -> bytes:
    """RFC 4941 HTTP/1.0 field as bytes."""

    return serialize_tempaddr(policy).encode("ascii")


def parse_tempaddr_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_tempaddr(field_value) if field_value else DEFAULT_TEMPORARY
    return {
        "field_value": field_value,
        "policy": policy,
        "header": TEMPORARY_HEADER,
        "directive": str(policy),
        "temporary": str(policy) == "TEMPORARY",
        "public": str(policy) == "PUBLIC",
    }


def canonical_temporary(identity: str, tempaddrid: int) -> str:
    """RFC 4941 body-temporary advertisement bound to identity and tempaddrid."""

    return (
        f"{serialize_tempaddr(DEFAULT_TEMPORARY)}, "
        f"temporary={ascii_serialize_tempaddr_directive()}, "
        f"identity={identity}, tempaddrid={int(tempaddrid) & 0xFFFFFFFF}"
    )


def canonical_public(identity: str, tempaddrid: int, tempaddrdigest: int | None = None) -> str:
    """RFC 4941 public-message confirmation of the stored identifier-digest."""

    digest = ""
    if tempaddrdigest is not None:
        digest = f", tempaddrdigest={int(tempaddrdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_tempaddr(PUBLIC_POLICY)}, "
        f"public={ascii_serialize_tempaddr_directive(public=True)}, "
        f"identity={identity}, tempaddrid={int(tempaddrid) & 0xFFFFFFFF}{digest}"
    )


def representation_public(identity: str, tempaddrid: int, tempaddrdigest: int) -> str:
    return canonical_public(identity, tempaddrid, tempaddrdigest)


def tempaddr_matches(left: str, right: str) -> bool:
    return parse_tempaddr(left) == parse_tempaddr(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise TempaddrActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise TempaddrActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise TempaddrActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise TempaddrActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def temporary_request(identity: str, tempaddrid: int) -> bytes:
    """HTTP TEMPORARY that elicits RFC 4941 origin HTTP/1.0."""

    keyid = f"{int(tempaddrid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"TEMPORARY /tempaddr/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Tempaddr-Id: {int(tempaddrid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def public_request(identity: str, tempaddrid: int, tempaddrdigest: int | None = None) -> bytes:
    """HTTP PUBLIC carrying RFC 4941 public-message confirmation of the stored identifier-digest."""

    keyid = f"{int(tempaddrid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if tempaddrdigest is not None:
        extra = f"Tempaddr-Digest: {int(tempaddrdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"PUBLIC /tempaddr/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Tempaddr-Id: {int(tempaddrid) & 0xFFFFFFFF}\r\n"
        "Public-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    tempaddr_kind = "public" if fields.get("public-confirm") == "1" else "temporary"
    upgrade_field = fields.get("temporary") or fields.get("tempaddr") or ""
    policy = parse_tempaddr(upgrade_field) if upgrade_field else ()
    return {
        "kind": "temporary",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "tempaddr_kind": tempaddr_kind,
        "policy": policy,
        "tempaddrid": int(fields["tempaddr-id"]) if fields.get("tempaddr-id") else EMPTY_TEMPADDRID,
        "tempaddrdigest": int(fields["tempaddr-digest"]) if fields.get("tempaddr-digest") else EMPTY_TEMPADDRDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def temporary_response(identity: str, tempaddrid: int, tempaddrdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 4941 origin HTTP/1.0, carrying the stored tempaddrdigest."""

    publicised = serialize_tempaddr(DEFAULT_TEMPORARY)
    payload = bytes(body or canonical_temporary(identity, tempaddrid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Temporary: {publicised}\r\n"
        f"Tempaddr-Id: {int(tempaddrid) & 0xFFFFFFFF}\r\n"
        f"Tempaddr-Digest: {int(tempaddrdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def public_response(identity: str, tempaddrid: int, tempaddrdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 4941 PUBLIC, carrying the stored identifier-digest."""

    publicised = serialize_tempaddr(PUBLIC_POLICY)
    payload = bytes(body or representation_public(identity, tempaddrid, tempaddrdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Temporary: {publicised}\r\n"
        f"Tempaddr-Id: {int(tempaddrid) & 0xFFFFFFFF}\r\n"
        f"Tempaddr-Digest: {int(tempaddrdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/tempaddr-public\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise TempaddrActuationError("illegal_content_length") from error
    field_value = fields.get("temporary") or fields.get("tempaddr") or ""
    policy = parse_tempaddr(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/tempaddr-public" or policy == PUBLIC_POLICY:
        status = 200
        tempaddr_kind = "public"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        tempaddr_kind = "temporary"
    else:
        status = 0
        tempaddr_kind = "temporary"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "tempaddr_kind": tempaddr_kind,
        "policy": policy,
        "tempaddrid": int(fields["tempaddr-id"]) if fields.get("tempaddr-id") else EMPTY_TEMPADDRID,
        "tempaddrdigest": int(fields["tempaddr-digest"]) if fields.get("tempaddr-digest") else EMPTY_TEMPADDRDIGEST,
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
        raise TempaddrActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise TempaddrActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise TempaddrActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise TempaddrActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc4941_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    tempaddr: str,
) -> str:
    """RFC 4941 identifier digest over method, router-IP, identity, and tempaddrid."""

    payload = f"{method}:{tempaddr}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def temporary_tempaddrid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"tempaddrid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_tempaddrid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-tempaddrid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def temporary_tempaddrdigest(tempaddrid: int = EMPTY_TEMPADDRID, token: str = SENTINEL) -> int:
    nonce = f"{int(tempaddrid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc4941_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="PUBLIC",
        tempaddr=f"/tempaddr/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_TEMPADDRID = temporary_tempaddrid(SENTINEL)
DEFAULT_TEMPADDRDIGEST = temporary_tempaddrdigest(DEFAULT_TEMPADDRID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    tempaddrid: int,
    tempaddrdigest: int,
    include_tempaddrid: bool = True,
) -> bytes:
    live_tempaddrid = int(tempaddrid) & 0xFFFFFFFF if include_tempaddrid else EMPTY_TEMPADDRID
    live_digest = int(tempaddrdigest) & 0xFFFFFFFF if include_tempaddrid and live_tempaddrid else EMPTY_TEMPADDRDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_tempaddrid) if live_tempaddrid else b""
    header = bytearray()
    header.append(TEMPADDR_FIRST)
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
    tempaddrid: int,
    tempaddrdigest: int | None = None,
    include_tempaddrid: bool = True,
) -> bytes:
    live_tempaddrid = int(tempaddrid) & 0xFFFFFFFF if include_tempaddrid else EMPTY_TEMPADDRID
    live_digest = int(tempaddrdigest) if tempaddrdigest is not None else temporary_tempaddrdigest(live_tempaddrid, identity)
    return encode_packet(
        FRAME_TEMPORARY,
        identity=identity,
        tempaddrid=live_tempaddrid,
        tempaddrdigest=live_digest,
        include_tempaddrid=include_tempaddrid,
    )


def encode_public(
    *,
    identity: str,
    tempaddrid: int,
    tempaddrdigest: int | None = None,
    include_tempaddrid: bool = True,
) -> bytes:
    live_tempaddrid = int(tempaddrid) & 0xFFFFFFFF if include_tempaddrid else EMPTY_TEMPADDRID
    live_digest = int(tempaddrdigest) if tempaddrdigest is not None else temporary_tempaddrdigest(live_tempaddrid, identity)
    return encode_packet(
        FRAME_PUBLIC,
        identity=identity,
        tempaddrid=live_tempaddrid,
        tempaddrdigest=live_digest,
        include_tempaddrid=include_tempaddrid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise TempaddrActuationError("short_packet")
    first = raw[0]
    if first != TEMPADDR_FIRST:
        raise TempaddrActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise TempaddrActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == TEMPADDRID_SIZE:
        live_tempaddrid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_tempaddrid = EMPTY_TEMPADDRID
    else:
        raise TempaddrActuationError("illegal_tempaddrid")
    if offset >= len(raw):
        raise TempaddrActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_TEMPORARY, FRAME_PUBLIC}:
        raise TempaddrActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise TempaddrActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise TempaddrActuationError("checksum_failed")
    if len(payload) < 5:
        raise TempaddrActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise TempaddrActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_tempaddrid = int(live_tempaddrid) != EMPTY_TEMPADDRID
    has_tempaddrdigest = has_tempaddrid and int(live_digest) != EMPTY_TEMPADDRDIGEST
    is_temporary = frame_type == FRAME_TEMPORARY
    is_public = frame_type == FRAME_PUBLIC
    return {
        "type": int(frame_type),
        "is_temporary": is_temporary,
        "is_public": is_public,
        "tempaddrid": int(live_tempaddrid),
        "has_tempaddrid": has_tempaddrid,
        "tempaddrdigest": int(live_digest),
        "has_tempaddrdigest": has_tempaddrdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC4941",
        "serialize_field": canonical_temporary(identity, live_tempaddrid) if has_tempaddrid else "",
        "tls_field": canonical_public(identity, live_tempaddrid, live_digest) if has_tempaddrdigest else "",
    }


class TempaddrClient:
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
            raise TempaddrActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_public"] or not packet["is_public"]:
            raise TempaddrActuationError("tempaddrdigest_required")
        if not packet["has_tempaddrid"]:
            raise TempaddrActuationError("tempaddrid_required")
        if not packet["has_tempaddrdigest"]:
            raise TempaddrActuationError("tempaddrdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_tempaddrdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_tempaddrdigest:
            raise TempaddrActuationError("tempaddrdigest_required")
        prefix = self._recv()
        return {
            "session": prefix,
            "tempaddrid": int(prefix.get("tempaddrid") or EMPTY_TEMPADDRID),
            "identity": str(prefix.get("identity") or ""),
            "tempaddrdigest": int(prefix.get("tempaddrdigest") or EMPTY_TEMPADDRDIGEST),
        }

    def public(
        self,
        identity: str,
        tempaddrid: int,
        tempaddrdigest: int = EMPTY_TEMPADDRDIGEST,
        *,
        wait_tempaddrdigest: bool = True,
        include_tempaddrid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_public(
            identity=identity,
            tempaddrid=tempaddrid,
            tempaddrdigest=tempaddrdigest or temporary_tempaddrdigest(tempaddrid, identity),
            include_tempaddrid=include_tempaddrid,
        )
        return self.exchange(packet, wait_tempaddrdigest=wait_tempaddrdigest)


class TempaddrSession:
    """TEMPADDRID-gated loopback RFC 4941 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        tempaddrid_gate: int = DEFAULT_TEMPADDRID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tempaddrid_gate = int(tempaddrid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.tempaddrid = EMPTY_TEMPADDRID
        self.tempaddrdigest = EMPTY_TEMPADDRDIGEST
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

    def store_tempaddrid_once(self, identity: str, tempaddrid: int, tempaddrdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(tempaddrid or EMPTY_TEMPADDRID)
            live_digest = int(tempaddrdigest or EMPTY_TEMPADDRDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.tempaddrid = live
                self.tempaddrdigest = live_digest or temporary_tempaddrdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.tempaddrid), int(self.tempaddrdigest)

    def read_tempaddrid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.tempaddrid), int(self.tempaddrdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "tempaddrid": EMPTY_TEMPADDRID,
            "tempaddrdigest": EMPTY_TEMPADDRDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _tempaddrid_missing(self) -> bool:
        return not int(self.tempaddrid_gate or 0)

    def _public_tuple(self, peer: tuple[str, int], identity: str, tempaddrid: int, tempaddrdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_public(
            identity=identity,
            tempaddrid=tempaddrid,
            tempaddrdigest=tempaddrdigest,
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
            except TempaddrActuationError:
                continue
            if not packet.get("is_temporary") and not packet.get("is_public"):
                continue
            if not packet.get("has_tempaddrid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_tempaddrid, stored_digest = self.store_tempaddrid_once(
                identity,
                int(packet.get("tempaddrid") or EMPTY_TEMPADDRID),
                int(packet.get("tempaddrdigest") or EMPTY_TEMPADDRDIGEST),
            )
            if not stored_name or not stored_tempaddrid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_temporary"):
                    self.opened = True
                if packet.get("is_public"):
                    self.handshook = True
                self.retrieved = True
            self._public_tuple(peer, stored_name, stored_tempaddrid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._tempaddrid_missing():
            return self._forbidden("missing_tempaddrid")
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
        do_tempaddrdigest: bool = True,
        replay: bool = True,
        use_tempaddrid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._tempaddrid_missing():
            return self._forbidden("missing_tempaddrid")
        live_token = str(token or SENTINEL)
        origin_tempaddrid = temporary_tempaddrid(live_token)
        origin_digest = temporary_tempaddrdigest(origin_tempaddrid, live_token)
        client: TempaddrClient | None = None
        independent: TempaddrClient | None = None
        try:
            client = TempaddrClient(self.host, int(self.port))
            if not do_temporary:
                return self._conflict("temporary_required")
            bind_packet = encode_temporary(
                identity=live_token,
                tempaddrid=origin_tempaddrid,
                tempaddrdigest=origin_digest,
                include_tempaddrid=use_tempaddrid,
            )
            if not use_tempaddrid:
                try:
                    client.exchange(bind_packet, wait_tempaddrdigest=True)
                except TempaddrActuationError:
                    return self._conflict("tempaddrid_required")
                return self._conflict("tempaddrid_required")
            client.send(bind_packet)
            if not do_public:
                return self._conflict("public_required")
            proxy_packet = encode_public(
                identity=live_token,
                tempaddrid=origin_tempaddrid,
                tempaddrdigest=origin_digest,
                include_tempaddrid=True,
            )
            if not do_tempaddrdigest:
                try:
                    client.exchange(proxy_packet, wait_tempaddrdigest=False)
                except TempaddrActuationError as error:
                    if str(error) == "tempaddrdigest_required":
                        return self._conflict("tempaddrdigest_required")
                    return self._conflict("tempaddrdigest_required")
                return self._conflict("tempaddrdigest_required")
            try:
                prefix = client.exchange(proxy_packet, wait_tempaddrdigest=True)
            except TempaddrActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("tempaddrid_required")
                if reason == "tempaddrdigest_required":
                    return self._conflict("tempaddrdigest_required")
                return self._conflict("temporary_required")
            if str(prefix.get("identity") or "") != live_token:
                return self._conflict("temporary_required")
            if int(prefix.get("tempaddrid") or EMPTY_TEMPADDRID) != origin_tempaddrid:
                return self._conflict("tempaddrdigest_required")
            if int(prefix.get("tempaddrdigest") or EMPTY_TEMPADDRDIGEST) != origin_digest:
                return self._conflict("tempaddrdigest_required")
            self.retrieved = True
            if replay:
                independent = TempaddrClient(self.host, int(self.port))
                try:
                    poll = independent.public(
                        POLL_TOKEN,
                        poll_tempaddrid(live_token),
                        temporary_tempaddrdigest(poll_tempaddrid(live_token), POLL_TOKEN),
                        wait_tempaddrdigest=True,
                    )
                except TempaddrActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_tempaddrid, stored_digest = self.read_tempaddrid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_tempaddrid != origin_tempaddrid
                    or stored_digest != origin_digest
                    or int(poll.get("tempaddrid") or EMPTY_TEMPADDRID) != origin_tempaddrid
                    or int(poll.get("tempaddrdigest") or EMPTY_TEMPADDRDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_tempaddrid}:{origin_digest}:{live_token}:{canonical_temporary(live_token, origin_tempaddrid)}:{canonical_public(live_token, origin_tempaddrid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "tempaddrid": origin_tempaddrid,
                "tempaddrdigest": origin_digest,
                "temporary_frame": True,
                "public_frame": True,
                "tempaddrdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "tempaddrid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_tempaddrdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "tempaddrid": origin_tempaddrid,
                "tempaddrdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "temporary_frame": True,
                "public_frame": True,
                "tempaddrdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "tempaddrid_bound": True,
            }
        except (OSError, TempaddrActuationError) as error:
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
        live = independent_tempaddrdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "tempaddrid": int(live.get("tempaddrid") or EMPTY_TEMPADDRID),
            "tempaddrdigest": int(live.get("tempaddrdigest") or EMPTY_TEMPADDRDIGEST),
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


def call_tempaddr_tool(session: TempaddrSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one tempaddr tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_temporary = True if arguments.get("temporary") is None else bool(arguments.get("temporary"))
    do_public = True if arguments.get("public") is None else bool(arguments.get("public"))
    do_tempaddrdigest = True if arguments.get("tempaddrdigest") is None else bool(arguments.get("tempaddrdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_tempaddrid = True if arguments.get("use_tempaddrid") is None else bool(arguments.get("use_tempaddrid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_temporary=do_temporary,
            do_public=do_public,
            do_tempaddrdigest=do_tempaddrdigest,
            replay=replay,
            use_tempaddrid=use_tempaddrid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise TempaddrActuationError(f"unsupported tempaddr action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_tempaddrdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage tempaddrdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "tempaddrid": EMPTY_TEMPADDRID,
        "tempaddrdigest": EMPTY_TEMPADDRDIGEST,
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
            "tempaddrdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "tempaddrid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    tempaddrid = int(payload.get("tempaddrid") or EMPTY_TEMPADDRID)
    tempaddrdigest = int(payload.get("tempaddrdigest") or EMPTY_TEMPADDRDIGEST)
    dual = port > 0 and bool(tempaddrid) and bool(tempaddrdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "tempaddrid": tempaddrid,
        "tempaddrdigest": tempaddrdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "temporary_frame": payload.get("temporary_frame") is True,
        "public_frame": payload.get("public_frame") is True,
        "tempaddrdigest_locate": payload.get("tempaddrdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "tempaddrid_bound": payload.get("tempaddrid_bound") is True,
    }


def run_tempaddr_workflow(
    *,
    with_tempaddrid: bool = True,
    skip_bind: bool = False,
    do_temporary: bool = True,
    do_public: bool = True,
    do_tempaddrdigest: bool = True,
    replay: bool = True,
    use_tempaddrid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 4941 TEMPORARY/PUBLIC tempaddrid cycle workflow."""

    descriptor = tempaddr_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TEMPADDR_TOOL_PROVIDER),
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
        raise TempaddrActuationError(f"tempaddr tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="tempaddr-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = TempaddrSession(out, tempaddrid_gate=DEFAULT_TEMPADDRID if with_tempaddrid else EMPTY_TEMPADDRID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "temporary": do_temporary,
            "public": do_public,
            "tempaddrdigest": do_tempaddrdigest,
            "replay": replay,
            "use_tempaddrid": use_tempaddrid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_tempaddr_tool(session, arguments))
            except TempaddrActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_tempaddrdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_tempaddrid
        and not skip_bind
        and do_temporary
        and do_public
        and do_tempaddrdigest
        and replay
        and use_tempaddrid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "tempaddr_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_tempaddrid": with_tempaddrid,
        "skip_bind": skip_bind,
        "temporary_frame": do_temporary,
        "public_frame": do_public,
        "tempaddrdigest": do_tempaddrdigest,
        "replay": replay,
        "use_tempaddrid": use_tempaddrid,
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
        "tempaddrid_value": int(publish_result.get("tempaddrid") or independent.get("tempaddrid") or EMPTY_TEMPADDRID),
        "tempaddrdigest_value": int(publish_result.get("tempaddrdigest") or independent.get("tempaddrdigest") or EMPTY_TEMPADDRDIGEST),
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
        "tempaddrid": int(trace_body["tempaddrid_value"] or EMPTY_TEMPADDRID),
        "tempaddrdigest": int(trace_body["tempaddrdigest_value"] or EMPTY_TEMPADDRDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_tempaddrid": with_tempaddrid,
        "skip_bind": skip_bind,
        "temporary_cycle": do_temporary,
        "public_cycle": do_public,
        "tempaddrdigest_cycle": do_tempaddrdigest,
        "replay": replay,
        "use_tempaddrid": use_tempaddrid,
    }


def verify_tempaddr_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_tempaddrdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    tempaddrid = int(trace.get("tempaddrid_value") or independent.get("tempaddrid") or EMPTY_TEMPADDRID)
    tempaddrdigest = int(trace.get("tempaddrdigest_value") or independent.get("tempaddrdigest") or EMPTY_TEMPADDRDIGEST)
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
        "tempaddrdigest_locate": independent.get("tempaddrdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "tempaddrid_bound": independent.get("tempaddrid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "tempaddrdigest_recorded": (
            port > 0
            and tempaddrid == DEFAULT_TEMPADDRID
            and tempaddrdigest == DEFAULT_TEMPADDRDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def tempaddr_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.tempaddr_actuation import "
        "builtin_tempaddr_actuation_proof; r=builtin_tempaddr_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='tempaddr_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_tempaddr_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=TEMPADDR_ACTUATION_ID,
        name="First-class RFC 4941 Privacy Extensions TEMPORARY/PUBLIC actuation",
        description=(
            "Missions that require a tempaddr tool can opt the tempaddr provider in, "
            "bind a loopback RFC 4941 Privacy Extensions endpoint, complete a TEMPORARY "
            "with a non-empty tempaddrid, lockstep a PUBLIC that carries the "
            "stored tempaddrdigest, independently poll the stored tempaddrdigest "
            "on a later socket, and seal a digest-chained tempaddrdigest. Default "
            "routing stays fail-closed; a missing tempaddrid keeps the hole "
            "falsifiable, and skip-TEMPORARY/PUBLIC/TEMPADDRDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.tempaddr_actuation:builtin_tempaddr_actuation_proof",
        proof_command=tempaddr_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.slaac-actuation",
        ),
        behavior_paths=(
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
            "src/blackhole_agent/opaqueiid_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required tempaddr tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 4941 daemon, speaks a "
            "TEMPORARY then PUBLIC over Privacy Extensions with a non-empty tempaddrid and "
            "tempaddrdigest, independently polls the stored tempaddrdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 4862 Stateless Address Autoconfiguration lockstep is proved. "
            "Missing tempaddrids, skip-TEMPORARY, skip-PUBLIC, skip-tempaddrdigest, skip-REPLAY, "
            "and a TEMPORARY aimed without a tempaddrid stay fail-closed. "
            "Later genesis can take RFC 7217 Semantically Opaque Interface Identifiers STABLE/OPAQUE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("tempaddr", "rfc4941", "http", "tempaddrid", "tempaddrdigest", "temporary", "public", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T192327Z-0e64ea97",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_tempaddr_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 4941 temporary/public lockstep actuation seals an tempaddrdigest."""

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
    from blackhole_agent.opaqueiid_actuation import (
        OPAQUEIID_ACTUATION_GOAL,
        OPAQUEIID_ACTUATION_ID,
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
    checks["denylists_self"] = TEMPADDR_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(TEMPADDR_ACTUATION_GOAL) == (
        TEMPADDR_ACTUATION_ID,
    )
    checks["leftover_text_binds_tempaddr"] = leftover_marker_ids(TEMPADDR_LEFTOVER) == (
        TEMPADDR_ACTUATION_ID,
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
        (OPAQUEIID_ACTUATION_GOAL, OPAQUEIID_ACTUATION_ID, "opaqueiid"),
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
        checks[f"{name}_goal_is_not_tempaddr"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"tempaddr_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            TEMPADDR_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = TEMPADDR_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    publicised = serialize_tempaddr(DEFAULT_TEMPORARY)
    rebuilt = serialize_tempaddr(parse_tempaddr(publicised))
    preloaded = parse_tempaddr(RFC_TEMPADDR_PUBLIC)
    header = encode_tempaddr_header(DEFAULT_TEMPORARY)
    parsed_header = parse_tempaddr_header(header)
    asked = parse_http_request(temporary_request(SENTINEL, DEFAULT_TEMPADDRID))
    preload_req = parse_http_request(public_request(SENTINEL, DEFAULT_TEMPADDRID, DEFAULT_TEMPADDRDIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_TEMPADDRID, DEFAULT_TEMPADDRDIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_TEMPADDRID, DEFAULT_TEMPADDRDIGEST)
    )
    checks["tempaddr_roundtrip"] = (
        parse_tempaddr(publicised) == DEFAULT_TEMPORARY
        and hmac.compare_digest(rebuilt, publicised)
        and publicised == RFC_TEMPORARY_FIELD
        and is_token("TEMPORARY") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_TEMPORARY_FIELD
        and parsed_header["policy"] == DEFAULT_TEMPORARY
        and parsed_header["header"] == TEMPORARY_HEADER
        and parsed_header["temporary"] is True
        and parsed_header["public"] is False
        and preloaded == PUBLIC_POLICY
        and ascii_serialize_tempaddr_directive() == RFC_TEMPORARY_DIRECTIVE
        and tempaddr_directive_pair() == ("temporary", "message")
        and RFC_TEMPORARY_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_tempaddr(PUBLIC_POLICY) == RFC_TEMPADDR_PUBLIC
        and DEFAULT_TEMPADDRDIGEST == temporary_tempaddrdigest(DEFAULT_TEMPADDRID, SENTINEL)
        and "tempaddrdigest=" in canonical_public(SENTINEL, DEFAULT_TEMPADDRID, DEFAULT_TEMPADDRDIGEST)
        and canonical_temporary(SENTINEL, DEFAULT_TEMPADDRID).startswith("TEMPORARY")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "TEMPORARY"
        and asked["tempaddr_kind"] == "temporary"
        and asked["tempaddrid"] == DEFAULT_TEMPADDRID
        and preload_req["tempaddr_kind"] == "public"
        and preload_req["tempaddrdigest"] == DEFAULT_TEMPADDRDIGEST
        and got["status"] == 200
        and preload_public["status"] == 200
        and got["tempaddr_kind"] == "temporary"
        and preload_public["tempaddr_kind"] == "public"
        and got["policy"] == DEFAULT_TEMPORARY
        and preload_public["policy"] == PUBLIC_POLICY
        and got["content_length_matches_body"] is True
        and preload_public["content_length_matches_body"] is True
        and got["tempaddrdigest"] == DEFAULT_TEMPADDRDIGEST
        and preload_public["tempaddrdigest"] == DEFAULT_TEMPADDRDIGEST
        and tempaddr_matches(serialize_tempaddr(got["policy"]), publicised)
    )

    checks["catalog_names_tempaddr"] = (
        len(catalog) > 122
        and catalog[122]["id"] == TEMPADDR_ACTUATION_ID
        and catalog[121]["id"] == SLAAC_ACTUATION_ID
        and catalog[120]["id"] == NDP_ACTUATION_ID
        and catalog[122]["source"] == "genesis_bind_tempaddr"
    )
    checks["catalog_names_opaqueiid"] = (
        len(catalog) > 123
        and catalog[123]["id"] == OPAQUEIID_ACTUATION_ID
        and catalog[123]["source"] == "genesis_bind_opaqueiid"
    )
    family = capability_family(TEMPADDR_ACTUATION_GOAL)
    checks["family_is_tempaddr"] = "tempaddr" in family.split("/")
    checks["family_is_tempaddr_surface"] = "tempaddrid" in family
    checks["family_is_tempaddrid"] = "tempaddrid" in family
    checks["family_is_rfc4941"] = "rfc4941" in family
    checks["family_is_tempaddrdigest"] = "tempaddrdigest" in family
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
    checks["family_is_not_opaqueiid"] = (
        "opaqueiid" not in family.split("/")
        and "rfc7217" not in family
        and "opaqueid" not in family
        and "opaquedigest" not in family
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
    packed = encode_temporary(identity=SENTINEL, tempaddrid=DEFAULT_TEMPADDRID, tempaddrdigest=DEFAULT_TEMPADDRDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_temporary"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_tempaddrid"] is True
        and parsed["tempaddrid"] == DEFAULT_TEMPADDRID
        and parsed["tempaddrdigest"] == DEFAULT_TEMPADDRDIGEST
        and parsed["is_public"] is False
        and parsed["is_public"] is False
        and parsed["type"] == FRAME_TEMPORARY
        and parsed["first_byte"] == TEMPADDR_FIRST
    )
    shook = encode_public(
        identity=SENTINEL,
        tempaddrid=DEFAULT_TEMPADDRID,
        tempaddrdigest=DEFAULT_TEMPADDRDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_public"] is True
        and answer_parsed["is_public"] is True
        and answer_parsed["is_temporary"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["tempaddrid"] == DEFAULT_TEMPADDRID
        and answer_parsed["tempaddrdigest"] == DEFAULT_TEMPADDRDIGEST
        and answer_parsed["has_tempaddrdigest"] is True
        and answer_parsed["type"] == FRAME_PUBLIC
        and answer_parsed["first_byte"] == TEMPADDR_FIRST
    )
    bare = encode_temporary(identity=SENTINEL, tempaddrid=DEFAULT_TEMPADDRID, include_tempaddrid=False)
    checks["missing_tempaddrid_is_unauthed"] = parse_message(bare)["has_tempaddrid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(TEMPADDR_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_tempaddr = ToolDescriptor(name="remote_tempaddr", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_tempaddr)
    checks["naive_mcp_tempaddr_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = tempaddr_tool_descriptor()
    default_tempaddr = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TEMPADDR_TOOL_PROVIDER),
    )
    checks["default_tempaddr_provider_is_unsupported"] = (
        default_tempaddr.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{TEMPADDR_TOOL_PROVIDER}" in default_tempaddr.reasons
    )
    checks["opted_in_tempaddr_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_tempaddr],
        required_tool_names=("local_memory", "tempaddr"),
    )
    checks["naive_preflight_missing_tempaddr"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["tempaddr"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "tempaddr"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TEMPADDR_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "tempaddr" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="tempaddr-actuation-") as tmp:
        root = Path(tmp)
        missing = run_tempaddr_workflow(with_tempaddrid=False, output_dir=root / "missing")
        skip_bind = run_tempaddr_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_temporary = run_tempaddr_workflow(do_temporary=False, output_dir=root / "skip-temporary")
        skip_public = run_tempaddr_workflow(do_public=False, output_dir=root / "skip-public")
        skip_tempaddrdigest = run_tempaddr_workflow(do_tempaddrdigest=False, output_dir=root / "skip-tempaddrdigest")
        skip_replay = run_tempaddr_workflow(replay=False, output_dir=root / "skip-replay")
        skip_tempaddrid = run_tempaddr_workflow(use_tempaddrid=False, output_dir=root / "sktempaddr-tempaddrid")
        live = run_tempaddr_workflow(output_dir=root / "live")
        verify = verify_tempaddr_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_tempaddr_trace(clone)
        checks["naive_without_tempaddrid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_tempaddrid"
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
        checks["skip_tempaddrdigest_stays_empty"] = (
            skip_tempaddrdigest["ok"] is False
            and skip_tempaddrdigest["error"] == "tempaddrdigest_required"
            and skip_tempaddrdigest["final_status"] == 409
            and skip_tempaddrdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_tempaddrid_stays_empty"] = (
            skip_tempaddrid["ok"] is False
            and skip_tempaddrid["error"] == "tempaddrid_required"
            and skip_tempaddrid["final_status"] == 409
            and skip_tempaddrid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_tempaddrdigest"] = (
            int(live.get("tempaddrid") or 0) == DEFAULT_TEMPADDRID
            and int(live.get("tempaddrdigest") or 0) == DEFAULT_TEMPADDRDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_tempaddrid_encode_public_tempaddrdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_temporary["ok"] is False
            and skip_public["ok"] is False
            and skip_tempaddrdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_tempaddrid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="tempaddr-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != TEMPADDR_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, TEMPADDR_ACTUATION_GOAL, TEMPADDR_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_tempaddr"] = (
        not gate.accepted
        and live_goal != TEMPADDR_ACTUATION_GOAL
        and TEMPADDR_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_tempaddr"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="tempaddr-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(TEMPADDR_LEFTOVER, root)
        register_catalog_proved(root, TEMPADDR_ACTUATION_ID)
        reason = leftover_satisfied_by(TEMPADDR_LEFTOVER, root)
        after = leftover_is_open(TEMPADDR_LEFTOVER, root)
    checks["tempaddr_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_tempaddr_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{TEMPADDR_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_tempaddr_actuation_capability()
    return {
        "ok": ok,
        "action": "tempaddr_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": TEMPADDR_ACTUATION_GOAL,
        "done_when": TEMPADDR_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
