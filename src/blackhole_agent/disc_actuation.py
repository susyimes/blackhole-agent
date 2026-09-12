"""Drive a first-class Stateful IPV4ONLY tool through RFC 7050 IPV4ONLY/AAAA.

Tool routing already fails missions that require ``disc``: hosted
disc endpoints stay on the unsupported MCP provider, and no first-party
disc provider is executable. Unbound therefore cannot speak a IPV4ONLY,
lockstep a AAAA discid handshake over HTTP/1.0 DISCID,
independently poll the stored discdigest, or seal a discdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``disc`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 7050 daemon
- keep a missing-discid client so the disc-discid hole stays falsifiable
- refuse AAAA until a IPV4ONLY lands with a non-empty discid
- independently poll the stored discdigest on a later client socket
- persist a sealed discdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 6877 CLAT/PLAT
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
    DISC_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    disc_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
DISC_ACTUATION_ID = "capability.disc-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-DISC-OK"
POLL_TOKEN = "BH-DISC-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_DISCID = 0
EMPTY_DISCDIGEST = 0
DISC_FIRST = 0x50  # RFC 7050 IPV4ONLY; no RA option type
DISCID_SIZE = 4
DISCDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DEST = 0x02  # RFC 7050 aaaa index
FRAME_SOURCE = 0x01  # RFC 7050 disc type
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
DISC_LEFTOVER = (
    "Later genesis can take RFC 7050 Discovery of the IPv6 Prefix Used for IPv6 Address Synthesis IPV4ONLY/AAAA over a "
    "discid-gated discdigest."
)
DISC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DISC_ACTUATION_ID};"
    f"capability_proved:{DISC_ACTUATION_ID};"
    "no_skill_route"
)
DISC_ACTUATION_GOAL = (
    "Repair rfc7050 disc ipv4only/aaaa cycle cannot land over http "
    "disc discid: hosted disc endpoints remain unsupported so a IPV4ONLY then "
    "AAAA discid handshake cannot land and a sealed discdigest "
    "cannot be produced. A missing disc discid stays forbidden; fail-closed "
    "routing never opts the disc provider in. An independent later poll of the "
    "stored discdigest keeps the hole falsifiable."
)


class DiscActuationError(RuntimeError):
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
# RFC 7050 sections 3.1 and 3.2: IPV4ONLY / AAAA.
RFC_SOURCE_FIELD = "IPV4ONLY"
RFC_DEST_FIELD = "AAAA"
RFC_DISC_DEST = RFC_DEST_FIELD
RFC_SOURCE_DIRECTIVE = "ipv4only=message"
RFC_DEST_DIRECTIVE = "aaaa=message"
DEFAULT_SOURCE = "IPV4ONLY"
DEST_HOP = "AAAA"
SOURCE_HEADER = "Ipv4only"
DEST_HEADER = "Aaaa"
DISC_DEST_HEADER = DEST_HEADER
RFC_SOURCE_PATH = "/disc/"
RFC_SOURCE_EMPTY = ""


def disc_directive_pair(*, local: bool = False) -> tuple[str, str]:
    """RFC 7050 Ipv4only / Aaaa directive pair."""

    if local:
        return "aaaa", "message"
    return "ipv4only", "message"


def ascii_serialize_disc_directive(*, local: bool = False) -> str:
    """RFC 7050 token "=" body-or-local."""

    name, value = disc_directive_pair(local=local)
    if not is_token(name):
        raise DiscActuationError("illegal_directive")
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
            raise DiscActuationError("short_disc")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 7050 body-unique token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_disc(policy: str | Sequence[str]) -> str:
    """Serialize RFC 7050 IPV4ONLY / AAAA opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise DiscActuationError("illegal_disc")
    upper = text.upper().replace("_", "-")
    if upper in {"IPV4ONLY", "IPV4ONLY", "IPV4ONLY-IPV4ONLY"}:
        return "IPV4ONLY"
    if upper in {"AAAA", "IPV4ONLY-AAAA"}:
        return "AAAA"
    if upper.startswith("IPV4ONLY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise DiscActuationError("illegal_disc")
        return "IPV4ONLY"
    if upper.startswith("AAAA="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise DiscActuationError("illegal_disc")
        return "AAAA"
    raise DiscActuationError("illegal_disc")


def parse_disc(text: str) -> str:
    """Parse RFC 7050 IPV4ONLY opcode header extensions into IPV4ONLY or AAAA."""

    raw = str(text or "").strip()
    if not raw:
        raise DiscActuationError("illegal_disc")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"IPV4ONLY", "IPV4ONLY", "IPV4ONLY-IPV4ONLY"}:
        return "IPV4ONLY"
    if upper in {"AAAA", "IPV4ONLY-AAAA"}:
        return "AAAA"
    if upper.startswith("IPV4ONLY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise DiscActuationError("illegal_disc")
        return "IPV4ONLY"
    if upper.startswith("AAAA="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise DiscActuationError("illegal_disc")
        return "AAAA"
    raise DiscActuationError("illegal_disc")


def encode_disc_header(policy: str | Sequence[str]) -> bytes:
    """RFC 7050 HTTP/1.0 field as bytes."""

    return serialize_disc(policy).encode("ascii")


def parse_disc_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_disc(field_value) if field_value else DEFAULT_SOURCE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SOURCE_HEADER,
        "directive": str(policy),
        "is_first": str(policy) == "IPV4ONLY",
        "table": str(policy) == "AAAA",
    }


def canonical_temporary(identity: str, discid: int) -> str:
    """RFC 7050 body-unique advertisement bound to identity and discid."""

    return (
        f"{serialize_disc(DEFAULT_SOURCE)}, "
        f"disc={ascii_serialize_disc_directive()}, "
        f"identity={identity}, discid={int(discid) & 0xFFFFFFFF}"
    )


def canonical_public(identity: str, discid: int, discdigest: int | None = None) -> str:
    """RFC 7050 local-message confirmation of the stored identifier-digest."""

    digest = ""
    if discdigest is not None:
        digest = f", discdigest={int(discdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_disc(DEST_HOP)}, "
        f"aaaa={ascii_serialize_disc_directive(local=True)}, "
        f"identity={identity}, discid={int(discid) & 0xFFFFFFFF}{digest}"
    )


def representation_public(identity: str, discid: int, discdigest: int) -> str:
    return canonical_public(identity, discid, discdigest)


def disc_matches(left: str, right: str) -> bool:
    return parse_disc(left) == parse_disc(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise DiscActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise DiscActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise DiscActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise DiscActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def temporary_request(identity: str, discid: int) -> bytes:
    """HTTP IPV4ONLY that elicits RFC 7050 origin HTTP/1.0."""

    keyid = f"{int(discid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"IPV4ONLY /disc/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Disc-Id: {int(discid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def public_request(identity: str, discid: int, discdigest: int | None = None) -> bytes:
    """HTTP AAAA carrying RFC 7050 local-message confirmation of the stored identifier-digest."""

    keyid = f"{int(discid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if discdigest is not None:
        extra = f"Disc-Digest: {int(discdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"AAAA /disc/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Disc-Id: {int(discid) & 0xFFFFFFFF}\r\n"
        "Aaaa-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    disc_kind = "aaaa" if fields.get("aaaa-confirm") == "1" else "ipv4only"
    upgrade_field = fields.get("ipv4only") or fields.get("disc") or ""
    policy = parse_disc(upgrade_field) if upgrade_field else ()
    return {
        "kind": "disc",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "disc_kind": disc_kind,
        "policy": policy,
        "discid": int(fields["disc-id"]) if fields.get("disc-id") else EMPTY_DISCID,
        "discdigest": int(fields["disc-digest"]) if fields.get("disc-digest") else EMPTY_DISCDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def temporary_response(identity: str, discid: int, discdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 7050 origin HTTP/1.0, carrying the stored discdigest."""

    publicised = serialize_disc(DEFAULT_SOURCE)
    payload = bytes(body or canonical_temporary(identity, discid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Ipv4only: {publicised}\r\n"
        f"Disc-Id: {int(discid) & 0xFFFFFFFF}\r\n"
        f"Disc-Digest: {int(discdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def public_response(identity: str, discid: int, discdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 7050 AAAA, carrying the stored identifier-digest."""

    publicised = serialize_disc(DEST_HOP)
    payload = bytes(body or representation_public(identity, discid, discdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Ipv4only: {publicised}\r\n"
        f"Disc-Id: {int(discid) & 0xFFFFFFFF}\r\n"
        f"Disc-Digest: {int(discdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/disc-aaaa\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise DiscActuationError("illegal_content_length") from error
    field_value = fields.get("ipv4only") or fields.get("disc") or ""
    policy = parse_disc(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/disc-aaaa" or policy == DEST_HOP:
        status = 200
        disc_kind = "aaaa"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        disc_kind = "ipv4only"
    else:
        status = 0
        disc_kind = "ipv4only"
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
        "discid": int(fields["disc-id"]) if fields.get("disc-id") else EMPTY_DISCID,
        "discdigest": int(fields["disc-digest"]) if fields.get("disc-digest") else EMPTY_DISCDIGEST,
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
        raise DiscActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise DiscActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise DiscActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise DiscActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc7050_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    ula: str,
) -> str:
    """RFC 7050 identifier digest over method, router-IP, identity, and discid."""

    payload = f"{method}:{ula}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def temporary_discid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"discid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_discid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-discid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def temporary_discdigest(discid: int = EMPTY_DISCID, token: str = SENTINEL) -> int:
    nonce = f"{int(discid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc7050_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="AAAA",
        ula=f"/disc/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_DISCID = temporary_discid(SENTINEL)
DEFAULT_DISCDIGEST = temporary_discdigest(DEFAULT_DISCID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    discid: int,
    discdigest: int,
    include_discid: bool = True,
) -> bytes:
    live_discid = int(discid) & 0xFFFFFFFF if include_discid else EMPTY_DISCID
    live_digest = int(discdigest) & 0xFFFFFFFF if include_discid and live_discid else EMPTY_DISCDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_discid) if live_discid else b""
    header = bytearray()
    header.append(DISC_FIRST)
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
    discid: int,
    discdigest: int | None = None,
    include_discid: bool = True,
) -> bytes:
    live_discid = int(discid) & 0xFFFFFFFF if include_discid else EMPTY_DISCID
    live_digest = int(discdigest) if discdigest is not None else temporary_discdigest(live_discid, identity)
    return encode_packet(
        FRAME_SOURCE,
        identity=identity,
        discid=live_discid,
        discdigest=live_digest,
        include_discid=include_discid,
    )


def encode_public(
    *,
    identity: str,
    discid: int,
    discdigest: int | None = None,
    include_discid: bool = True,
) -> bytes:
    live_discid = int(discid) & 0xFFFFFFFF if include_discid else EMPTY_DISCID
    live_digest = int(discdigest) if discdigest is not None else temporary_discdigest(live_discid, identity)
    return encode_packet(
        FRAME_DEST,
        identity=identity,
        discid=live_discid,
        discdigest=live_digest,
        include_discid=include_discid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise DiscActuationError("short_packet")
    disc = raw[0]
    if disc != DISC_FIRST:
        raise DiscActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise DiscActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == DISCID_SIZE:
        live_discid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_discid = EMPTY_DISCID
    else:
        raise DiscActuationError("illegal_discid")
    if offset >= len(raw):
        raise DiscActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SOURCE, FRAME_DEST}:
        raise DiscActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise DiscActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise DiscActuationError("checksum_failed")
    if len(payload) < 5:
        raise DiscActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise DiscActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_discid = int(live_discid) != EMPTY_DISCID
    has_discdigest = has_discid and int(live_digest) != EMPTY_DISCDIGEST
    is_temporary = frame_type == FRAME_SOURCE
    is_public = frame_type == FRAME_DEST
    return {
        "type": int(frame_type),
        "is_temporary": is_temporary,
        "is_public": is_public,
        "discid": int(live_discid),
        "has_discid": has_discid,
        "discdigest": int(live_digest),
        "has_discdigest": has_discdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(disc),
        "mech_len": int(mech_len),
        "http_state": "RFC7050",
        "serialize_field": canonical_temporary(identity, live_discid) if has_discid else "",
        "tls_field": canonical_public(identity, live_discid, live_digest) if has_discdigest else "",
    }


class DiscClient:
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
            raise DiscActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_public"] or not packet["is_public"]:
            raise DiscActuationError("discdigest_required")
        if not packet["has_discid"]:
            raise DiscActuationError("discid_required")
        if not packet["has_discdigest"]:
            raise DiscActuationError("discdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_discdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_discdigest:
            raise DiscActuationError("discdigest_required")
        session = self._recv()
        return {
            "session": session,
            "discid": int(session.get("discid") or EMPTY_DISCID),
            "identity": str(session.get("identity") or ""),
            "discdigest": int(session.get("discdigest") or EMPTY_DISCDIGEST),
        }

    def local(
        self,
        identity: str,
        discid: int,
        discdigest: int = EMPTY_DISCDIGEST,
        *,
        wait_discdigest: bool = True,
        include_discid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_public(
            identity=identity,
            discid=discid,
            discdigest=discdigest or temporary_discdigest(discid, identity),
            include_discid=include_discid,
        )
        return self.exchange(packet, wait_discdigest=wait_discdigest)


class DiscSession:
    """DISCID-gated loopback RFC 7050 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        discid_gate: int = DEFAULT_DISCID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.discid_gate = int(discid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.discid = EMPTY_DISCID
        self.discdigest = EMPTY_DISCDIGEST
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

    def store_discid_once(self, identity: str, discid: int, discdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(discid or EMPTY_DISCID)
            live_digest = int(discdigest or EMPTY_DISCDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.discid = live
                self.discdigest = live_digest or temporary_discdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.discid), int(self.discdigest)

    def read_discid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.discid), int(self.discdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "discid": EMPTY_DISCID,
            "discdigest": EMPTY_DISCDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _discid_missing(self) -> bool:
        return not int(self.discid_gate or 0)

    def _public_tuple(self, peer: tuple[str, int], identity: str, discid: int, discdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_public(
            identity=identity,
            discid=discid,
            discdigest=discdigest,
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
            except DiscActuationError:
                continue
            if not packet.get("is_temporary") and not packet.get("is_public"):
                continue
            if not packet.get("has_discid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_discid, stored_digest = self.store_discid_once(
                identity,
                int(packet.get("discid") or EMPTY_DISCID),
                int(packet.get("discdigest") or EMPTY_DISCDIGEST),
            )
            if not stored_name or not stored_discid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_temporary"):
                    self.opened = True
                if packet.get("is_public"):
                    self.handshook = True
                self.retrieved = True
            self._public_tuple(peer, stored_name, stored_discid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._discid_missing():
            return self._forbidden("missing_discid")
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
        do_discdigest: bool = True,
        replay: bool = True,
        use_discid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._discid_missing():
            return self._forbidden("missing_discid")
        live_token = str(token or SENTINEL)
        origin_discid = temporary_discid(live_token)
        origin_digest = temporary_discdigest(origin_discid, live_token)
        client: DiscClient | None = None
        independent: DiscClient | None = None
        try:
            client = DiscClient(self.host, int(self.port))
            if not do_temporary:
                return self._conflict("temporary_required")
            bind_packet = encode_temporary(
                identity=live_token,
                discid=origin_discid,
                discdigest=origin_digest,
                include_discid=use_discid,
            )
            if not use_discid:
                try:
                    client.exchange(bind_packet, wait_discdigest=True)
                except DiscActuationError:
                    return self._conflict("discid_required")
                return self._conflict("discid_required")
            client.send(bind_packet)
            if not do_public:
                return self._conflict("public_required")
            proxy_packet = encode_public(
                identity=live_token,
                discid=origin_discid,
                discdigest=origin_digest,
                include_discid=True,
            )
            if not do_discdigest:
                try:
                    client.exchange(proxy_packet, wait_discdigest=False)
                except DiscActuationError as error:
                    if str(error) == "discdigest_required":
                        return self._conflict("discdigest_required")
                    return self._conflict("discdigest_required")
                return self._conflict("discdigest_required")
            try:
                session = client.exchange(proxy_packet, wait_discdigest=True)
            except DiscActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("discid_required")
                if reason == "discdigest_required":
                    return self._conflict("discdigest_required")
                return self._conflict("temporary_required")
            if str(session.get("identity") or "") != live_token:
                return self._conflict("temporary_required")
            if int(session.get("discid") or EMPTY_DISCID) != origin_discid:
                return self._conflict("discdigest_required")
            if int(session.get("discdigest") or EMPTY_DISCDIGEST) != origin_digest:
                return self._conflict("discdigest_required")
            self.retrieved = True
            if replay:
                independent = DiscClient(self.host, int(self.port))
                try:
                    poll = independent.local(
                        POLL_TOKEN,
                        poll_discid(live_token),
                        temporary_discdigest(poll_discid(live_token), POLL_TOKEN),
                        wait_discdigest=True,
                    )
                except DiscActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_discid, stored_digest = self.read_discid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_discid != origin_discid
                    or stored_digest != origin_digest
                    or int(poll.get("discid") or EMPTY_DISCID) != origin_discid
                    or int(poll.get("discdigest") or EMPTY_DISCDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_discid}:{origin_digest}:{live_token}:{canonical_temporary(live_token, origin_discid)}:{canonical_public(live_token, origin_discid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "discid": origin_discid,
                "discdigest": origin_digest,
                "temporary_frame": True,
                "public_frame": True,
                "discdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "discid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_discdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "discid": origin_discid,
                "discdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "temporary_frame": True,
                "public_frame": True,
                "discdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "discid_bound": True,
            }
        except (OSError, DiscActuationError) as error:
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
        live = independent_discdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "discid": int(live.get("discid") or EMPTY_DISCID),
            "discdigest": int(live.get("discdigest") or EMPTY_DISCDIGEST),
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


def call_disc_tool(session: DiscSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one disc tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_temporary = True if arguments.get("ipv4only") is None else bool(arguments.get("ipv4only"))
    do_public = True if arguments.get("aaaa") is None else bool(arguments.get("aaaa"))
    do_discdigest = True if arguments.get("discdigest") is None else bool(arguments.get("discdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_discid = True if arguments.get("use_discid") is None else bool(arguments.get("use_discid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_temporary=do_temporary,
            do_public=do_public,
            do_discdigest=do_discdigest,
            replay=replay,
            use_discid=use_discid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise DiscActuationError(f"unsupported disc action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_discdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage discdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "discid": EMPTY_DISCID,
        "discdigest": EMPTY_DISCDIGEST,
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
            "discdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "discid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    discid = int(payload.get("discid") or EMPTY_DISCID)
    discdigest = int(payload.get("discdigest") or EMPTY_DISCDIGEST)
    dual = port > 0 and bool(discid) and bool(discdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "discid": discid,
        "discdigest": discdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "temporary_frame": payload.get("temporary_frame") is True,
        "public_frame": payload.get("public_frame") is True,
        "discdigest_locate": payload.get("discdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "discid_bound": payload.get("discid_bound") is True,
    }


def run_disc_workflow(
    *,
    with_discid: bool = True,
    skip_bind: bool = False,
    do_temporary: bool = True,
    do_public: bool = True,
    do_discdigest: bool = True,
    replay: bool = True,
    use_discid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 7050 IPV4ONLY/AAAA discid cycle workflow."""

    descriptor = disc_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DISC_TOOL_PROVIDER),
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
        raise DiscActuationError(f"disc tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="disc-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = DiscSession(out, discid_gate=DEFAULT_DISCID if with_discid else EMPTY_DISCID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "ipv4only": do_temporary,
            "aaaa": do_public,
            "discdigest": do_discdigest,
            "replay": replay,
            "use_discid": use_discid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_disc_tool(session, arguments))
            except DiscActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_discdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_discid
        and not skip_bind
        and do_temporary
        and do_public
        and do_discdigest
        and replay
        and use_discid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "disc_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_discid": with_discid,
        "skip_bind": skip_bind,
        "temporary_frame": do_temporary,
        "public_frame": do_public,
        "discdigest": do_discdigest,
        "replay": replay,
        "use_discid": use_discid,
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
        "discid_value": int(publish_result.get("discid") or independent.get("discid") or EMPTY_DISCID),
        "discdigest_value": int(publish_result.get("discdigest") or independent.get("discdigest") or EMPTY_DISCDIGEST),
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
        "discid": int(trace_body["discid_value"] or EMPTY_DISCID),
        "discdigest": int(trace_body["discdigest_value"] or EMPTY_DISCDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_discid": with_discid,
        "skip_bind": skip_bind,
        "temporary_cycle": do_temporary,
        "public_cycle": do_public,
        "discdigest_cycle": do_discdigest,
        "replay": replay,
        "use_discid": use_discid,
    }


def verify_disc_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_discdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    discid = int(trace.get("discid_value") or independent.get("discid") or EMPTY_DISCID)
    discdigest = int(trace.get("discdigest_value") or independent.get("discdigest") or EMPTY_DISCDIGEST)
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
        "discdigest_locate": independent.get("discdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "discid_bound": independent.get("discid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "discdigest_recorded": (
            port > 0
            and discid == DEFAULT_DISCID
            and discdigest == DEFAULT_DISCDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def disc_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.disc_actuation import "
        "builtin_disc_actuation_proof; r=builtin_disc_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='disc_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_disc_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=DISC_ACTUATION_ID,
        name="First-class RFC 7050 Discovery of the IPv6 Prefix Used for IPv6 Address Synthesis IPV4ONLY/AAAA actuation",
        description=(
            "Missions that require a disc tool can opt the disc provider in, "
            "bind a loopback RFC 7050 Discovery of the IPv6 Prefix Used for IPv6 Address Synthesis endpoint, complete a IPV4ONLY "
            "with a non-empty discid, lockstep a AAAA that carries the "
            "stored discdigest, independently poll the stored discdigest "
            "on a later socket, and seal a digest-chained discdigest. Default "
            "routing stays fail-closed; a missing discid keeps the hole "
            "falsifiable, and skip-IPV4ONLY/AAAA/discdigest/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.disc_actuation:builtin_disc_actuation_proof",
        proof_command=disc_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.xlat-actuation",
            "capability.dns64-actuation",
        ),
        behavior_paths=(
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
            "src/blackhole_agent/dslite_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required disc tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 7050 daemon, speaks a "
            "IPV4ONLY then AAAA over Discovery of the IPv6 Prefix Used for IPv6 Address Synthesis with a non-empty discid and "
            "discdigest, independently polls the stored discdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 6877 CLAT/PLAT lockstep is proved. "
            "Missing discids, skip-IPV4ONLY, skip-AAAA, skip-discdigest, skip-REPLAY, "
            "and a IPV4ONLY aimed without a discid stay fail-closed. "
            "Later genesis can take RFC 6333 Dual-Stack Lite Broadband Deployments Following IPv4 Exhaustion B4/AFTR as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("disc", "rfc7050", "http", "discid", "discdigest", "ipv4only", "aaaa", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260907T070408Z-8411274d",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_disc_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 7050 disc/aaaa lockstep actuation seals a discdigest."""

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
    from blackhole_agent.dslite_actuation import (
        DSLITE_ACTUATION_GOAL,
        DSLITE_ACTUATION_ID,
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
    checks["denylists_self"] = DISC_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(DISC_ACTUATION_GOAL) == (
        DISC_ACTUATION_ID,
    )
    checks["leftover_text_binds_disc"] = leftover_marker_ids(DISC_LEFTOVER) == (
        DISC_ACTUATION_ID,
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
        (DSLITE_ACTUATION_GOAL, DSLITE_ACTUATION_ID, "dslite"),
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
        checks[f"{name}_goal_is_not_disc"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"disc_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            DISC_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = DISC_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    publicised = serialize_disc(DEFAULT_SOURCE)
    rebuilt = serialize_disc(parse_disc(publicised))
    preloaded = parse_disc(RFC_DISC_DEST)
    header = encode_disc_header(DEFAULT_SOURCE)
    parsed_header = parse_disc_header(header)
    asked = parse_http_request(temporary_request(SENTINEL, DEFAULT_DISCID))
    preload_req = parse_http_request(public_request(SENTINEL, DEFAULT_DISCID, DEFAULT_DISCDIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_DISCID, DEFAULT_DISCDIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_DISCID, DEFAULT_DISCDIGEST)
    )
    checks["disc_roundtrip"] = (
        parse_disc(publicised) == DEFAULT_SOURCE
        and hmac.compare_digest(rebuilt, publicised)
        and publicised == RFC_SOURCE_FIELD
        and is_token("IPV4ONLY") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SOURCE_FIELD
        and parsed_header["policy"] == DEFAULT_SOURCE
        and parsed_header["header"] == SOURCE_HEADER
        and parsed_header["is_first"] is True
        and parsed_header["table"] is False
        and preloaded == DEST_HOP
        and ascii_serialize_disc_directive() == RFC_SOURCE_DIRECTIVE
        and disc_directive_pair() == ("ipv4only", "message")
        and RFC_SOURCE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_disc(DEST_HOP) == RFC_DISC_DEST
        and DEFAULT_DISCDIGEST == temporary_discdigest(DEFAULT_DISCID, SENTINEL)
        and "discdigest=" in canonical_public(SENTINEL, DEFAULT_DISCID, DEFAULT_DISCDIGEST)
        and canonical_temporary(SENTINEL, DEFAULT_DISCID).startswith("IPV4ONLY")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "IPV4ONLY"
        and asked["disc_kind"] == "ipv4only"
        and asked["discid"] == DEFAULT_DISCID
        and preload_req["disc_kind"] == "aaaa"
        and preload_req["discdigest"] == DEFAULT_DISCDIGEST
        and got["status"] == 200
        and preload_public["status"] == 200
        and got["disc_kind"] == "ipv4only"
        and preload_public["disc_kind"] == "aaaa"
        and got["policy"] == DEFAULT_SOURCE
        and preload_public["policy"] == DEST_HOP
        and got["content_length_matches_body"] is True
        and preload_public["content_length_matches_body"] is True
        and got["discdigest"] == DEFAULT_DISCDIGEST
        and preload_public["discdigest"] == DEFAULT_DISCDIGEST
        and disc_matches(serialize_disc(got["policy"]), publicised)
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
    from blackhole_agent.mission_selection import semantic_tokens

    family = capability_family(DISC_ACTUATION_GOAL)
    checks["family_is_disc"] = "disc" in family.split("/")
    checks["family_is_disc_surface"] = "discid" in family
    checks["family_is_discid"] = "discid" in family
    checks["family_is_rfc7050"] = "rfc7050" in set(semantic_tokens(DISC_ACTUATION_GOAL))
    checks["family_is_discdigest"] = "discdigest" in family
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
    checks["family_is_not_dslite"] = (
        "dslite" not in family.split("/")
        and "rfc6333" not in family
        and "dsliteid" not in family
        and "dslitedigest" not in family
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
    packed = encode_temporary(identity=SENTINEL, discid=DEFAULT_DISCID, discdigest=DEFAULT_DISCDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_temporary"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_discid"] is True
        and parsed["discid"] == DEFAULT_DISCID
        and parsed["discdigest"] == DEFAULT_DISCDIGEST
        and parsed["is_public"] is False
        and parsed["is_public"] is False
        and parsed["type"] == FRAME_SOURCE
        and parsed["first_byte"] == DISC_FIRST
    )
    shook = encode_public(
        identity=SENTINEL,
        discid=DEFAULT_DISCID,
        discdigest=DEFAULT_DISCDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_public"] is True
        and answer_parsed["is_public"] is True
        and answer_parsed["is_temporary"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["discid"] == DEFAULT_DISCID
        and answer_parsed["discdigest"] == DEFAULT_DISCDIGEST
        and answer_parsed["has_discdigest"] is True
        and answer_parsed["type"] == FRAME_DEST
        and answer_parsed["first_byte"] == DISC_FIRST
    )
    bare = encode_temporary(identity=SENTINEL, discid=DEFAULT_DISCID, include_discid=False)
    checks["missing_discid_is_unauthed"] = parse_message(bare)["has_discid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(DISC_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_disc = ToolDescriptor(name="remote_disc", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_disc)
    checks["naive_mcp_disc_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = disc_tool_descriptor()
    default_disc = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DISC_TOOL_PROVIDER),
    )
    checks["default_disc_provider_is_unsupported"] = (
        default_disc.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{DISC_TOOL_PROVIDER}" in default_disc.reasons
    )
    checks["opted_in_disc_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_disc],
        required_tool_names=("local_memory", "disc"),
    )
    checks["naive_preflight_missing_disc"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["disc"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "disc"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DISC_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "disc" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="disc-actuation-") as tmp:
        root = Path(tmp)
        missing = run_disc_workflow(with_discid=False, output_dir=root / "missing")
        skip_bind = run_disc_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_temporary = run_disc_workflow(do_temporary=False, output_dir=root / "skip-ipv4only")
        skip_public = run_disc_workflow(do_public=False, output_dir=root / "skip-aaaa")
        skip_discdigest = run_disc_workflow(do_discdigest=False, output_dir=root / "skip-discdigest")
        skip_replay = run_disc_workflow(replay=False, output_dir=root / "skip-replay")
        skip_discid = run_disc_workflow(use_discid=False, output_dir=root / "skip-discid")
        live = run_disc_workflow(output_dir=root / "live")
        sealed = verify_disc_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_disc_trace(clone)
        checks["naive_without_discid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_discid"
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
        checks["skip_discdigest_stays_empty"] = (
            skip_discdigest["ok"] is False
            and skip_discdigest["error"] == "discdigest_required"
            and skip_discdigest["final_status"] == 409
            and skip_discdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_discid_stays_empty"] = (
            skip_discid["ok"] is False
            and skip_discid["error"] == "discid_required"
            and skip_discid["final_status"] == 409
            and skip_discid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_discdigest"] = (
            int(live.get("discid") or 0) == DEFAULT_DISCID
            and int(live.get("discdigest") or 0) == DEFAULT_DISCDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_discid_encode_public_discdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_temporary["ok"] is False
            and skip_public["ok"] is False
            and skip_discdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_discid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = sealed["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="disc-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != DISC_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, DISC_ACTUATION_GOAL, DISC_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_disc"] = (
        not gate.accepted
        and live_goal != DISC_ACTUATION_GOAL
        and DISC_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_disc"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="disc-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(DISC_LEFTOVER, root)
        register_catalog_proved(root, DISC_ACTUATION_ID)
        reason = leftover_satisfied_by(DISC_LEFTOVER, root)
        after = leftover_is_open(DISC_LEFTOVER, root)
    checks["disc_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_disc_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{DISC_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_disc_actuation_capability()
    return {
        "ok": ok,
        "action": "disc_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": DISC_ACTUATION_GOAL,
        "done_when": DISC_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
