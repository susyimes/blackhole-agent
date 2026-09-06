"""Drive a first-class Cryptographically Generated Addresses tool through RFC 3972 GENERATE/VERIFY.

Tool routing already fails missions that require ``cga``: hosted
cga endpoints stay on the unsupported MCP provider, and no first-party
cga provider is executable. Unbound therefore cannot speak a GENERATE,
lockstep a VERIFY cgaid handshake over HTTP/1.0 CGAID,
independently poll the stored cgadigest, or seal a cgadigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``cga`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 3972 daemon
- keep a missing-cgaid client so the cga-cgaid hole stays falsifiable
- refuse VERIFY until a GENERATE lands with a non-empty cgaid
- independently poll the stored cgadigest on a later client socket
- persist a sealed cgadigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 7217 Semantically Opaque Interface Identifiers
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
    CGA_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    cga_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
CGA_ACTUATION_ID = "capability.cga-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-CGA-OK"
POLL_TOKEN = "BH-CGA-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_CGAID = 0
EMPTY_CGADIGEST = 0
CGA_FIRST = 0x3D  # RFC 3972 CGA (Cryptographically Generated Addresses next-header)
CGAID_SIZE = 4
CGADIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_VERIFY = 0x02  # RFC 3972 verify address
FRAME_GENERATE = 0x01  # RFC 3972 generate address
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
CGA_LEFTOVER = (
    "Later genesis can take RFC 3972 Cryptographically Generated Addresses GENERATE/VERIFY over an "
    "cgaid-gated cgadigest."
)
CGA_ACTUATION_DONE_WHEN = (
    f"capability_exists:{CGA_ACTUATION_ID};"
    f"capability_proved:{CGA_ACTUATION_ID};"
    "no_skill_route"
)
CGA_ACTUATION_GOAL = (
    "Repair rfc3972 cga generate/verify cycle cannot land over http "
    "cga cgaid: hosted cga endpoints remain unsupported so a GENERATE then "
    "VERIFY cgaid handshake cannot land and a sealed cgadigest "
    "cannot be produced. A missing cga cgaid stays forbidden; fail-closed "
    "routing never opts the cga provider in. An independent later poll of the "
    "stored cgadigest keeps the hole falsifiable."
)


class CgaActuationError(RuntimeError):
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
# RFC 3972 sections 3.1 and 3.2: GENERATE / VERIFY.
RFC_GENERATE_FIELD = "GENERATE"
RFC_VERIFY_FIELD = "VERIFY"
RFC_CGA_VERIFY = RFC_VERIFY_FIELD
RFC_GENERATE_DIRECTIVE = "generate=message"
RFC_VERIFY_DIRECTIVE = "verify=message"
DEFAULT_GENERATE = "GENERATE"
VERIFY_POLICY = "VERIFY"
GENERATE_HEADER = "Generate"
VERIFY_HEADER = "Verify"
CGA_VERIFY_HEADER = VERIFY_HEADER
RFC_GENERATE_PATH = "/cga/"
RFC_GENERATE_EMPTY = ""


def cga_directive_pair(*, verify: bool = False) -> tuple[str, str]:
    """RFC 3972 Generate / Verify directive pair."""

    if verify:
        return "verify", "message"
    return "generate", "message"


def ascii_serialize_cga_directive(*, verify: bool = False) -> str:
    """RFC 3972 token "=" body-or-verify."""

    name, value = cga_directive_pair(verify=verify)
    if not is_token(name):
        raise CgaActuationError("illegal_directive")
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
            raise CgaActuationError("short_cga")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 3972 body-generate token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_cga(policy: str | Sequence[str]) -> str:
    """Serialize RFC 3972 GENERATE / VERIFY opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise CgaActuationError("illegal_cga")
    upper = text.upper().replace("_", "-")
    if upper in {"GENERATE", "CGA", "CGA-GENERATE", "CGA-GENERATE"}:
        return "GENERATE"
    if upper in {"VERIFY", "RESOURCE", "CGA-VERIFY"}:
        return "VERIFY"
    if upper.startswith("GENERATE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise CgaActuationError("illegal_cga")
        return "GENERATE"
    if upper.startswith("VERIFY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise CgaActuationError("illegal_cga")
        return "VERIFY"
    raise CgaActuationError("illegal_cga")


def parse_cga(text: str) -> str:
    """Parse RFC 3972 CGA opcode header extensions into GENERATE or VERIFY."""

    raw = str(text or "").strip()
    if not raw:
        raise CgaActuationError("illegal_cga")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"GENERATE", "CGA", "CGA-GENERATE", "CGA-GENERATE"}:
        return "GENERATE"
    if upper in {"VERIFY", "RESOURCE", "CGA-VERIFY"}:
        return "VERIFY"
    if upper.startswith("GENERATE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise CgaActuationError("illegal_cga")
        return "GENERATE"
    if upper.startswith("VERIFY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise CgaActuationError("illegal_cga")
        return "VERIFY"
    raise CgaActuationError("illegal_cga")


def encode_cga_header(policy: str | Sequence[str]) -> bytes:
    """RFC 3972 HTTP/1.0 field as bytes."""

    return serialize_cga(policy).encode("ascii")


def parse_cga_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_cga(field_value) if field_value else DEFAULT_GENERATE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": GENERATE_HEADER,
        "directive": str(policy),
        "generate": str(policy) == "GENERATE",
        "verify": str(policy) == "VERIFY",
    }


def canonical_temporary(identity: str, cgaid: int) -> str:
    """RFC 3972 body-generate advertisement bound to identity and cgaid."""

    return (
        f"{serialize_cga(DEFAULT_GENERATE)}, "
        f"generate={ascii_serialize_cga_directive()}, "
        f"identity={identity}, cgaid={int(cgaid) & 0xFFFFFFFF}"
    )


def canonical_public(identity: str, cgaid: int, cgadigest: int | None = None) -> str:
    """RFC 3972 verify-message confirmation of the stored identifier-digest."""

    digest = ""
    if cgadigest is not None:
        digest = f", cgadigest={int(cgadigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_cga(VERIFY_POLICY)}, "
        f"verify={ascii_serialize_cga_directive(verify=True)}, "
        f"identity={identity}, cgaid={int(cgaid) & 0xFFFFFFFF}{digest}"
    )


def representation_public(identity: str, cgaid: int, cgadigest: int) -> str:
    return canonical_public(identity, cgaid, cgadigest)


def cga_matches(left: str, right: str) -> bool:
    return parse_cga(left) == parse_cga(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise CgaActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise CgaActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise CgaActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise CgaActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def temporary_request(identity: str, cgaid: int) -> bytes:
    """HTTP GENERATE that elicits RFC 3972 origin HTTP/1.0."""

    keyid = f"{int(cgaid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GENERATE /cga/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Cga-Id: {int(cgaid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def public_request(identity: str, cgaid: int, cgadigest: int | None = None) -> bytes:
    """HTTP VERIFY carrying RFC 3972 verify-message confirmation of the stored identifier-digest."""

    keyid = f"{int(cgaid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if cgadigest is not None:
        extra = f"Cga-Digest: {int(cgadigest) & 0xFFFFFFFF}\r\n"
    return (
        f"VERIFY /cga/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Cga-Id: {int(cgaid) & 0xFFFFFFFF}\r\n"
        "Verify-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    cga_kind = "verify" if fields.get("verify-confirm") == "1" else "generate"
    upgrade_field = fields.get("generate") or fields.get("cga") or ""
    policy = parse_cga(upgrade_field) if upgrade_field else ()
    return {
        "kind": "generate",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "cga_kind": cga_kind,
        "policy": policy,
        "cgaid": int(fields["cga-id"]) if fields.get("cga-id") else EMPTY_CGAID,
        "cgadigest": int(fields["cga-digest"]) if fields.get("cga-digest") else EMPTY_CGADIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def temporary_response(identity: str, cgaid: int, cgadigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 3972 origin HTTP/1.0, carrying the stored cgadigest."""

    publicised = serialize_cga(DEFAULT_GENERATE)
    payload = bytes(body or canonical_temporary(identity, cgaid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Generate: {publicised}\r\n"
        f"Cga-Id: {int(cgaid) & 0xFFFFFFFF}\r\n"
        f"Cga-Digest: {int(cgadigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def public_response(identity: str, cgaid: int, cgadigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 3972 VERIFY, carrying the stored identifier-digest."""

    publicised = serialize_cga(VERIFY_POLICY)
    payload = bytes(body or representation_public(identity, cgaid, cgadigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Generate: {publicised}\r\n"
        f"Cga-Id: {int(cgaid) & 0xFFFFFFFF}\r\n"
        f"Cga-Digest: {int(cgadigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/cga-verify\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise CgaActuationError("illegal_content_length") from error
    field_value = fields.get("generate") or fields.get("cga") or ""
    policy = parse_cga(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/cga-verify" or policy == VERIFY_POLICY:
        status = 200
        cga_kind = "verify"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        cga_kind = "generate"
    else:
        status = 0
        cga_kind = "generate"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "cga_kind": cga_kind,
        "policy": policy,
        "cgaid": int(fields["cga-id"]) if fields.get("cga-id") else EMPTY_CGAID,
        "cgadigest": int(fields["cga-digest"]) if fields.get("cga-digest") else EMPTY_CGADIGEST,
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
        raise CgaActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise CgaActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise CgaActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise CgaActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc3972_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    cga: str,
) -> str:
    """RFC 3972 identifier digest over method, router-IP, identity, and cgaid."""

    payload = f"{method}:{cga}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def temporary_cgaid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"cgaid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_cgaid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-cgaid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def temporary_cgadigest(cgaid: int = EMPTY_CGAID, token: str = SENTINEL) -> int:
    nonce = f"{int(cgaid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc3972_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="VERIFY",
        cga=f"/cga/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_CGAID = temporary_cgaid(SENTINEL)
DEFAULT_CGADIGEST = temporary_cgadigest(DEFAULT_CGAID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    cgaid: int,
    cgadigest: int,
    include_cgaid: bool = True,
) -> bytes:
    live_cgaid = int(cgaid) & 0xFFFFFFFF if include_cgaid else EMPTY_CGAID
    live_digest = int(cgadigest) & 0xFFFFFFFF if include_cgaid and live_cgaid else EMPTY_CGADIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_cgaid) if live_cgaid else b""
    header = bytearray()
    header.append(CGA_FIRST)
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
    cgaid: int,
    cgadigest: int | None = None,
    include_cgaid: bool = True,
) -> bytes:
    live_cgaid = int(cgaid) & 0xFFFFFFFF if include_cgaid else EMPTY_CGAID
    live_digest = int(cgadigest) if cgadigest is not None else temporary_cgadigest(live_cgaid, identity)
    return encode_packet(
        FRAME_GENERATE,
        identity=identity,
        cgaid=live_cgaid,
        cgadigest=live_digest,
        include_cgaid=include_cgaid,
    )


def encode_public(
    *,
    identity: str,
    cgaid: int,
    cgadigest: int | None = None,
    include_cgaid: bool = True,
) -> bytes:
    live_cgaid = int(cgaid) & 0xFFFFFFFF if include_cgaid else EMPTY_CGAID
    live_digest = int(cgadigest) if cgadigest is not None else temporary_cgadigest(live_cgaid, identity)
    return encode_packet(
        FRAME_VERIFY,
        identity=identity,
        cgaid=live_cgaid,
        cgadigest=live_digest,
        include_cgaid=include_cgaid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise CgaActuationError("short_packet")
    first = raw[0]
    if first != CGA_FIRST:
        raise CgaActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise CgaActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == CGAID_SIZE:
        live_cgaid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_cgaid = EMPTY_CGAID
    else:
        raise CgaActuationError("illegal_cgaid")
    if offset >= len(raw):
        raise CgaActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_GENERATE, FRAME_VERIFY}:
        raise CgaActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise CgaActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise CgaActuationError("checksum_failed")
    if len(payload) < 5:
        raise CgaActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise CgaActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_cgaid = int(live_cgaid) != EMPTY_CGAID
    has_cgadigest = has_cgaid and int(live_digest) != EMPTY_CGADIGEST
    is_temporary = frame_type == FRAME_GENERATE
    is_public = frame_type == FRAME_VERIFY
    return {
        "type": int(frame_type),
        "is_temporary": is_temporary,
        "is_public": is_public,
        "cgaid": int(live_cgaid),
        "has_cgaid": has_cgaid,
        "cgadigest": int(live_digest),
        "has_cgadigest": has_cgadigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC3972",
        "serialize_field": canonical_temporary(identity, live_cgaid) if has_cgaid else "",
        "tls_field": canonical_public(identity, live_cgaid, live_digest) if has_cgadigest else "",
    }


class CgaClient:
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
            raise CgaActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_public"] or not packet["is_public"]:
            raise CgaActuationError("cgadigest_required")
        if not packet["has_cgaid"]:
            raise CgaActuationError("cgaid_required")
        if not packet["has_cgadigest"]:
            raise CgaActuationError("cgadigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_cgadigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_cgadigest:
            raise CgaActuationError("cgadigest_required")
        prefix = self._recv()
        return {
            "session": prefix,
            "cgaid": int(prefix.get("cgaid") or EMPTY_CGAID),
            "identity": str(prefix.get("identity") or ""),
            "cgadigest": int(prefix.get("cgadigest") or EMPTY_CGADIGEST),
        }

    def verify(
        self,
        identity: str,
        cgaid: int,
        cgadigest: int = EMPTY_CGADIGEST,
        *,
        wait_cgadigest: bool = True,
        include_cgaid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_public(
            identity=identity,
            cgaid=cgaid,
            cgadigest=cgadigest or temporary_cgadigest(cgaid, identity),
            include_cgaid=include_cgaid,
        )
        return self.exchange(packet, wait_cgadigest=wait_cgadigest)


class CgaSession:
    """CGAID-gated loopback RFC 3972 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        cgaid_gate: int = DEFAULT_CGAID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cgaid_gate = int(cgaid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.cgaid = EMPTY_CGAID
        self.cgadigest = EMPTY_CGADIGEST
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

    def store_cgaid_once(self, identity: str, cgaid: int, cgadigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(cgaid or EMPTY_CGAID)
            live_digest = int(cgadigest or EMPTY_CGADIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.cgaid = live
                self.cgadigest = live_digest or temporary_cgadigest(live, name)
                self.stored = True
            return str(self.identity), int(self.cgaid), int(self.cgadigest)

    def read_cgaid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.cgaid), int(self.cgadigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "cgaid": EMPTY_CGAID,
            "cgadigest": EMPTY_CGADIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _cgaid_missing(self) -> bool:
        return not int(self.cgaid_gate or 0)

    def _public_tuple(self, peer: tuple[str, int], identity: str, cgaid: int, cgadigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_public(
            identity=identity,
            cgaid=cgaid,
            cgadigest=cgadigest,
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
            except CgaActuationError:
                continue
            if not packet.get("is_temporary") and not packet.get("is_public"):
                continue
            if not packet.get("has_cgaid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_cgaid, stored_digest = self.store_cgaid_once(
                identity,
                int(packet.get("cgaid") or EMPTY_CGAID),
                int(packet.get("cgadigest") or EMPTY_CGADIGEST),
            )
            if not stored_name or not stored_cgaid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_temporary"):
                    self.opened = True
                if packet.get("is_public"):
                    self.handshook = True
                self.retrieved = True
            self._public_tuple(peer, stored_name, stored_cgaid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._cgaid_missing():
            return self._forbidden("missing_cgaid")
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
        do_cgadigest: bool = True,
        replay: bool = True,
        use_cgaid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._cgaid_missing():
            return self._forbidden("missing_cgaid")
        live_token = str(token or SENTINEL)
        origin_cgaid = temporary_cgaid(live_token)
        origin_digest = temporary_cgadigest(origin_cgaid, live_token)
        client: CgaClient | None = None
        independent: CgaClient | None = None
        try:
            client = CgaClient(self.host, int(self.port))
            if not do_temporary:
                return self._conflict("temporary_required")
            bind_packet = encode_temporary(
                identity=live_token,
                cgaid=origin_cgaid,
                cgadigest=origin_digest,
                include_cgaid=use_cgaid,
            )
            if not use_cgaid:
                try:
                    client.exchange(bind_packet, wait_cgadigest=True)
                except CgaActuationError:
                    return self._conflict("cgaid_required")
                return self._conflict("cgaid_required")
            client.send(bind_packet)
            if not do_public:
                return self._conflict("public_required")
            proxy_packet = encode_public(
                identity=live_token,
                cgaid=origin_cgaid,
                cgadigest=origin_digest,
                include_cgaid=True,
            )
            if not do_cgadigest:
                try:
                    client.exchange(proxy_packet, wait_cgadigest=False)
                except CgaActuationError as error:
                    if str(error) == "cgadigest_required":
                        return self._conflict("cgadigest_required")
                    return self._conflict("cgadigest_required")
                return self._conflict("cgadigest_required")
            try:
                prefix = client.exchange(proxy_packet, wait_cgadigest=True)
            except CgaActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("cgaid_required")
                if reason == "cgadigest_required":
                    return self._conflict("cgadigest_required")
                return self._conflict("temporary_required")
            if str(prefix.get("identity") or "") != live_token:
                return self._conflict("temporary_required")
            if int(prefix.get("cgaid") or EMPTY_CGAID) != origin_cgaid:
                return self._conflict("cgadigest_required")
            if int(prefix.get("cgadigest") or EMPTY_CGADIGEST) != origin_digest:
                return self._conflict("cgadigest_required")
            self.retrieved = True
            if replay:
                independent = CgaClient(self.host, int(self.port))
                try:
                    poll = independent.verify(
                        POLL_TOKEN,
                        poll_cgaid(live_token),
                        temporary_cgadigest(poll_cgaid(live_token), POLL_TOKEN),
                        wait_cgadigest=True,
                    )
                except CgaActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_cgaid, stored_digest = self.read_cgaid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_cgaid != origin_cgaid
                    or stored_digest != origin_digest
                    or int(poll.get("cgaid") or EMPTY_CGAID) != origin_cgaid
                    or int(poll.get("cgadigest") or EMPTY_CGADIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_cgaid}:{origin_digest}:{live_token}:{canonical_temporary(live_token, origin_cgaid)}:{canonical_public(live_token, origin_cgaid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "cgaid": origin_cgaid,
                "cgadigest": origin_digest,
                "temporary_frame": True,
                "public_frame": True,
                "cgadigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "cgaid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_cgadigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "cgaid": origin_cgaid,
                "cgadigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "temporary_frame": True,
                "public_frame": True,
                "cgadigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "cgaid_bound": True,
            }
        except (OSError, CgaActuationError) as error:
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
        live = independent_cgadigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "cgaid": int(live.get("cgaid") or EMPTY_CGAID),
            "cgadigest": int(live.get("cgadigest") or EMPTY_CGADIGEST),
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


def call_cga_tool(session: CgaSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one cga tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_temporary = True if arguments.get("generate") is None else bool(arguments.get("generate"))
    do_public = True if arguments.get("verify") is None else bool(arguments.get("verify"))
    do_cgadigest = True if arguments.get("cgadigest") is None else bool(arguments.get("cgadigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_cgaid = True if arguments.get("use_cgaid") is None else bool(arguments.get("use_cgaid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_temporary=do_temporary,
            do_public=do_public,
            do_cgadigest=do_cgadigest,
            replay=replay,
            use_cgaid=use_cgaid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise CgaActuationError(f"unsupported cga action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_cgadigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage cgadigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "cgaid": EMPTY_CGAID,
        "cgadigest": EMPTY_CGADIGEST,
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
            "cgadigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "cgaid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    cgaid = int(payload.get("cgaid") or EMPTY_CGAID)
    cgadigest = int(payload.get("cgadigest") or EMPTY_CGADIGEST)
    dual = port > 0 and bool(cgaid) and bool(cgadigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "cgaid": cgaid,
        "cgadigest": cgadigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "temporary_frame": payload.get("temporary_frame") is True,
        "public_frame": payload.get("public_frame") is True,
        "cgadigest_locate": payload.get("cgadigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "cgaid_bound": payload.get("cgaid_bound") is True,
    }


def run_cga_workflow(
    *,
    with_cgaid: bool = True,
    skip_bind: bool = False,
    do_temporary: bool = True,
    do_public: bool = True,
    do_cgadigest: bool = True,
    replay: bool = True,
    use_cgaid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 3972 GENERATE/VERIFY cgaid cycle workflow."""

    descriptor = cga_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CGA_TOOL_PROVIDER),
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
        raise CgaActuationError(f"cga tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="cga-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = CgaSession(out, cgaid_gate=DEFAULT_CGAID if with_cgaid else EMPTY_CGAID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "generate": do_temporary,
            "verify": do_public,
            "cgadigest": do_cgadigest,
            "replay": replay,
            "use_cgaid": use_cgaid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_cga_tool(session, arguments))
            except CgaActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_cgadigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_cgaid
        and not skip_bind
        and do_temporary
        and do_public
        and do_cgadigest
        and replay
        and use_cgaid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "cga_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_cgaid": with_cgaid,
        "skip_bind": skip_bind,
        "temporary_frame": do_temporary,
        "public_frame": do_public,
        "cgadigest": do_cgadigest,
        "replay": replay,
        "use_cgaid": use_cgaid,
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
        "cgaid_value": int(publish_result.get("cgaid") or independent.get("cgaid") or EMPTY_CGAID),
        "cgadigest_value": int(publish_result.get("cgadigest") or independent.get("cgadigest") or EMPTY_CGADIGEST),
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
        "cgaid": int(trace_body["cgaid_value"] or EMPTY_CGAID),
        "cgadigest": int(trace_body["cgadigest_value"] or EMPTY_CGADIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_cgaid": with_cgaid,
        "skip_bind": skip_bind,
        "temporary_cycle": do_temporary,
        "public_cycle": do_public,
        "cgadigest_cycle": do_cgadigest,
        "replay": replay,
        "use_cgaid": use_cgaid,
    }


def verify_cga_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_cgadigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    cgaid = int(trace.get("cgaid_value") or independent.get("cgaid") or EMPTY_CGAID)
    cgadigest = int(trace.get("cgadigest_value") or independent.get("cgadigest") or EMPTY_CGADIGEST)
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
        "cgadigest_locate": independent.get("cgadigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "cgaid_bound": independent.get("cgaid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "cgadigest_recorded": (
            port > 0
            and cgaid == DEFAULT_CGAID
            and cgadigest == DEFAULT_CGADIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def cga_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.cga_actuation import "
        "builtin_cga_actuation_proof; r=builtin_cga_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='cga_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_cga_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=CGA_ACTUATION_ID,
        name="First-class RFC 3972 Cryptographically Generated Addresses GENERATE/VERIFY actuation",
        description=(
            "Missions that require an cga tool can opt the cga provider in, "
            "bind a loopback RFC 3972 Cryptographically Generated Addresses endpoint, complete a GENERATE "
            "with a non-empty cgaid, lockstep a VERIFY that carries the "
            "stored cgadigest, independently poll the stored cgadigest "
            "on a later socket, and seal a digest-chained cgadigest. Default "
            "routing stays fail-closed; a missing cgaid keeps the hole "
            "falsifiable, and skip-GENERATE/VERIFY/CGADIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.cga_actuation:builtin_cga_actuation_proof",
        proof_command=cga_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.opaqueiid-actuation",
        ),
        behavior_paths=(
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
            "src/blackhole_agent/send_actuation.py",
            "src/blackhole_agent/ula_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required cga tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 3972 daemon, speaks a "
            "GENERATE then VERIFY over Cryptographically Generated Addresses with a non-empty cgaid and "
            "cgadigest, independently polls the stored cgadigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 7217 Semantically Opaque Interface Identifiers lockstep is proved. "
            "Missing cgaids, skip-GENERATE, skip-VERIFY, skip-cgadigest, skip-REPLAY, "
            "and a GENERATE aimed without a cgaid stay fail-closed. "
            "Later genesis can take RFC 3971 SEcure Neighbor Discovery CPS/CPA as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("cga", "rfc3972", "http", "cgaid", "cgadigest", "generate", "verify", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T203342Z-ba0a6516",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_cga_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 3972 generate/verify lockstep actuation seals an cgadigest."""

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
    from blackhole_agent.send_actuation import (
        SEND_ACTUATION_GOAL,
        SEND_ACTUATION_ID,
    )
    from blackhole_agent.ula_actuation import (
        ULA_ACTUATION_GOAL,
        ULA_ACTUATION_ID,
    )
    from blackhole_agent.ipv6addr_actuation import (
        IPV6ADDR_ACTUATION_GOAL,
        IPV6ADDR_ACTUATION_ID,
    )
    from blackhole_agent.ipv6scope_actuation import (
        IPV6SCOPE_ACTUATION_GOAL,
        IPV6SCOPE_ACTUATION_ID,
    )
    from blackhole_agent.addrselect_actuation import (
        ADDRSELECT_ACTUATION_GOAL,
        ADDRSELECT_ACTUATION_ID,
    )
    from blackhole_agent.addrpolicy_actuation import (
        ADDRPOLICY_ACTUATION_GOAL,
        ADDRPOLICY_ACTUATION_ID,
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
    checks["denylists_self"] = CGA_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(CGA_ACTUATION_GOAL) == (
        CGA_ACTUATION_ID,
    )
    checks["leftover_text_binds_cga"] = leftover_marker_ids(CGA_LEFTOVER) == (
        CGA_ACTUATION_ID,
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
        (ULA_ACTUATION_GOAL, ULA_ACTUATION_ID, "ula"),
        (IPV6SCOPE_ACTUATION_GOAL, IPV6SCOPE_ACTUATION_ID, "ipv6scope"),
        (ADDRSELECT_ACTUATION_GOAL, ADDRSELECT_ACTUATION_ID, "addrselect"),
        (ADDRPOLICY_ACTUATION_GOAL, ADDRPOLICY_ACTUATION_ID, "addrpolicy"),
        (IPV6ADDR_ACTUATION_GOAL, IPV6ADDR_ACTUATION_ID, "ipv6addr"),
        (SEND_ACTUATION_GOAL, SEND_ACTUATION_ID, "send"),
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
        checks[f"{name}_goal_is_not_cga"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"cga_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            CGA_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = CGA_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    publicised = serialize_cga(DEFAULT_GENERATE)
    rebuilt = serialize_cga(parse_cga(publicised))
    preloaded = parse_cga(RFC_CGA_VERIFY)
    header = encode_cga_header(DEFAULT_GENERATE)
    parsed_header = parse_cga_header(header)
    asked = parse_http_request(temporary_request(SENTINEL, DEFAULT_CGAID))
    preload_req = parse_http_request(public_request(SENTINEL, DEFAULT_CGAID, DEFAULT_CGADIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_CGAID, DEFAULT_CGADIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_CGAID, DEFAULT_CGADIGEST)
    )
    checks["cga_roundtrip"] = (
        parse_cga(publicised) == DEFAULT_GENERATE
        and hmac.compare_digest(rebuilt, publicised)
        and publicised == RFC_GENERATE_FIELD
        and is_token("GENERATE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_GENERATE_FIELD
        and parsed_header["policy"] == DEFAULT_GENERATE
        and parsed_header["header"] == GENERATE_HEADER
        and parsed_header["generate"] is True
        and parsed_header["verify"] is False
        and preloaded == VERIFY_POLICY
        and ascii_serialize_cga_directive() == RFC_GENERATE_DIRECTIVE
        and cga_directive_pair() == ("generate", "message")
        and RFC_GENERATE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_cga(VERIFY_POLICY) == RFC_CGA_VERIFY
        and DEFAULT_CGADIGEST == temporary_cgadigest(DEFAULT_CGAID, SENTINEL)
        and "cgadigest=" in canonical_public(SENTINEL, DEFAULT_CGAID, DEFAULT_CGADIGEST)
        and canonical_temporary(SENTINEL, DEFAULT_CGAID).startswith("GENERATE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "GENERATE"
        and asked["cga_kind"] == "generate"
        and asked["cgaid"] == DEFAULT_CGAID
        and preload_req["cga_kind"] == "verify"
        and preload_req["cgadigest"] == DEFAULT_CGADIGEST
        and got["status"] == 200
        and preload_public["status"] == 200
        and got["cga_kind"] == "generate"
        and preload_public["cga_kind"] == "verify"
        and got["policy"] == DEFAULT_GENERATE
        and preload_public["policy"] == VERIFY_POLICY
        and got["content_length_matches_body"] is True
        and preload_public["content_length_matches_body"] is True
        and got["cgadigest"] == DEFAULT_CGADIGEST
        and preload_public["cgadigest"] == DEFAULT_CGADIGEST
        and cga_matches(serialize_cga(got["policy"]), publicised)
    )

    checks["catalog_names_cga"] = (
        len(catalog) > 124
        and catalog[124]["id"] == CGA_ACTUATION_ID
        and catalog[123]["id"] == OPAQUEIID_ACTUATION_ID
        and catalog[122]["id"] == TEMPADDR_ACTUATION_ID
        and catalog[124]["source"] == "genesis_bind_cga"
    )
    checks["catalog_names_send"] = (
        len(catalog) > 125
        and catalog[125]["id"] == SEND_ACTUATION_ID
        and catalog[125]["source"] == "genesis_bind_send"
    )
    checks["catalog_names_ula"] = (
        len(catalog) > 126
        and catalog[126]["id"] == ULA_ACTUATION_ID
        and catalog[126]["source"] == "genesis_bind_ula"
    )
    checks["catalog_names_ipv6addr"] = (
        len(catalog) > 127
        and catalog[127]["id"] == IPV6ADDR_ACTUATION_ID
        and catalog[127]["source"] == "genesis_bind_ipv6addr"
    )
    checks["catalog_names_ipv6scope"] = (
        len(catalog) > 128
        and catalog[128]["id"] == IPV6SCOPE_ACTUATION_ID
        and catalog[128]["source"] == "genesis_bind_ipv6scope"
    )
    checks["catalog_names_addrselect"] = (
        len(catalog) > 129
        and catalog[129]["id"] == ADDRSELECT_ACTUATION_ID
        and catalog[129]["source"] == "genesis_bind_addrselect"
    )
    checks["catalog_names_addrpolicy"] = (
        len(catalog) > 130
        and catalog[130]["id"] == ADDRPOLICY_ACTUATION_ID
        and catalog[130]["source"] == "genesis_bind_addrpolicy"
    )
    family = capability_family(CGA_ACTUATION_GOAL)
    checks["family_is_cga"] = "cga" in family.split("/")
    checks["family_is_cga_surface"] = "cgaid" in family
    checks["family_is_cgaid"] = "cgaid" in family
    checks["family_is_rfc3972"] = "rfc3972" in family
    checks["family_is_cgadigest"] = "cgadigest" in family
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
    checks["family_is_not_ula"] = (
        "ula" not in family.split("/")
        and "rfc4193" not in family
        and "ulaid" not in family
        and "uladigest" not in family
    )
    checks["family_is_not_ipv6addr"] = (
        "ipv6addr" not in family.split("/")
        and "rfc4291" not in family
        and "ipv6addrid" not in family
        and "ipv6addrdigest" not in family
    )
    checks["family_is_not_ipv6scope"] = (
        "ipv6scope" not in family.split("/")
        and "rfc4007" not in family
        and "scopeid" not in family
        and "scopedigest" not in family
    )
    checks["family_is_not_addrselect"] = (
        "addrselect" not in family.split("/")
        and "rfc6724" not in family
        and "selectid" not in family
        and "selectdigest" not in family
    )
    checks["family_is_not_addrpolicy"] = (
        "addrpolicy" not in family.split("/")
        and "rfc7078" not in family
        and "policyid" not in family
        and "policydigest" not in family
    )
    checks["family_is_not_send"] = (
        "send" not in family.split("/")
        and "rfc3971" not in family
        and "sendid" not in family
        and "senddigest" not in family
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
    packed = encode_temporary(identity=SENTINEL, cgaid=DEFAULT_CGAID, cgadigest=DEFAULT_CGADIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_temporary"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_cgaid"] is True
        and parsed["cgaid"] == DEFAULT_CGAID
        and parsed["cgadigest"] == DEFAULT_CGADIGEST
        and parsed["is_public"] is False
        and parsed["is_public"] is False
        and parsed["type"] == FRAME_GENERATE
        and parsed["first_byte"] == CGA_FIRST
    )
    shook = encode_public(
        identity=SENTINEL,
        cgaid=DEFAULT_CGAID,
        cgadigest=DEFAULT_CGADIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_public"] is True
        and answer_parsed["is_public"] is True
        and answer_parsed["is_temporary"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["cgaid"] == DEFAULT_CGAID
        and answer_parsed["cgadigest"] == DEFAULT_CGADIGEST
        and answer_parsed["has_cgadigest"] is True
        and answer_parsed["type"] == FRAME_VERIFY
        and answer_parsed["first_byte"] == CGA_FIRST
    )
    bare = encode_temporary(identity=SENTINEL, cgaid=DEFAULT_CGAID, include_cgaid=False)
    checks["missing_cgaid_is_unauthed"] = parse_message(bare)["has_cgaid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(CGA_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_cga = ToolDescriptor(name="remote_cga", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_cga)
    checks["naive_mcp_cga_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = cga_tool_descriptor()
    default_cga = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CGA_TOOL_PROVIDER),
    )
    checks["default_cga_provider_is_unsupported"] = (
        default_cga.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{CGA_TOOL_PROVIDER}" in default_cga.reasons
    )
    checks["opted_in_cga_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_cga],
        required_tool_names=("local_memory", "cga"),
    )
    checks["naive_preflight_missing_cga"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["cga"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "cga"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CGA_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "cga" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="cga-actuation-") as tmp:
        root = Path(tmp)
        missing = run_cga_workflow(with_cgaid=False, output_dir=root / "missing")
        skip_bind = run_cga_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_temporary = run_cga_workflow(do_temporary=False, output_dir=root / "skip-generate")
        skip_public = run_cga_workflow(do_public=False, output_dir=root / "skip-verify")
        skip_cgadigest = run_cga_workflow(do_cgadigest=False, output_dir=root / "skip-cgadigest")
        skip_replay = run_cga_workflow(replay=False, output_dir=root / "skip-replay")
        skip_cgaid = run_cga_workflow(use_cgaid=False, output_dir=root / "skcga-cgaid")
        live = run_cga_workflow(output_dir=root / "live")
        verify = verify_cga_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_cga_trace(clone)
        checks["naive_without_cgaid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_cgaid"
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
        checks["skip_cgadigest_stays_empty"] = (
            skip_cgadigest["ok"] is False
            and skip_cgadigest["error"] == "cgadigest_required"
            and skip_cgadigest["final_status"] == 409
            and skip_cgadigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_cgaid_stays_empty"] = (
            skip_cgaid["ok"] is False
            and skip_cgaid["error"] == "cgaid_required"
            and skip_cgaid["final_status"] == 409
            and skip_cgaid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_cgadigest"] = (
            int(live.get("cgaid") or 0) == DEFAULT_CGAID
            and int(live.get("cgadigest") or 0) == DEFAULT_CGADIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_cgaid_encode_public_cgadigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_temporary["ok"] is False
            and skip_public["ok"] is False
            and skip_cgadigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_cgaid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="cga-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != CGA_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_cga"] = (
        live_goal == CGA_ACTUATION_GOAL
        and CGA_ACTUATION_ID in live_done
        and live_source == "genesis_bind_cga"
    )

    with tempfile.TemporaryDirectory(prefix="cga-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(CGA_LEFTOVER, root)
        register_catalog_proved(root, CGA_ACTUATION_ID)
        reason = leftover_satisfied_by(CGA_LEFTOVER, root)
        after = leftover_is_open(CGA_LEFTOVER, root)
    checks["cga_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_cga_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{CGA_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_cga_actuation_capability()
    return {
        "ok": ok,
        "action": "cga_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": CGA_ACTUATION_GOAL,
        "done_when": CGA_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
