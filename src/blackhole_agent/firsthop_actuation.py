"""Drive a first-class First-Hop Router Selection by Hosts in a Multi-Prefix Network tool through RFC 8028 FIRST/HOP.

Tool routing already fails missions that require ``firsthop``: hosted
firsthop endpoints stay on the unsupported MCP provider, and no first-party
firsthop provider is executable. Unbound therefore cannot speak a FIRST,
lockstep a HOP hopid handshake over HTTP/1.0 HOPID,
independently poll the stored hopdigest, or seal a hopdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``firsthop`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 8028 daemon
- keep a missing-hopid client so the firsthop-hopid hole stays falsifiable
- refuse HOP until a FIRST lands with a non-empty hopid
- independently poll the stored hopdigest on a later client socket
- persist a sealed hopdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 7078 Distributing Address Selection Policy using DHCPv6
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
    FIRSTHOP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    firsthop_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
FIRSTHOP_ACTUATION_ID = "capability.firsthop-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-FIRSTHOP-OK"
POLL_TOKEN = "BH-FIRSTHOP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_HOPID = 0
EMPTY_HOPDIGEST = 0
FIRSTHOP_FIRST = 0x86  # RFC 8028 ICMPv6 Router Advertisement type 134
HOPID_SIZE = 4
HOPDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DEST = 0x02  # RFC 8028 hop index
FRAME_SOURCE = 0x01  # RFC 8028 first type
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
FIRSTHOP_LEFTOVER = (
    "Later genesis can take RFC 8028 First-Hop Router Selection by Hosts in a Multi-Prefix Network FIRST/HOP over a "
    "hopid-gated hopdigest."
)
FIRSTHOP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{FIRSTHOP_ACTUATION_ID};"
    f"capability_proved:{FIRSTHOP_ACTUATION_ID};"
    "no_skill_route"
)
FIRSTHOP_ACTUATION_GOAL = (
    "Repair rfc8028 firsthop first/hop cycle cannot land over http "
    "firsthop hopid: hosted firsthop endpoints remain unsupported so a FIRST then "
    "HOP hopid handshake cannot land and a sealed hopdigest "
    "cannot be produced. A missing firsthop hopid stays forbidden; fail-closed "
    "routing never opts the firsthop provider in. An independent later poll of the "
    "stored hopdigest keeps the hole falsifiable."
)


class FirsthopActuationError(RuntimeError):
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
# RFC 8028 sections 3.1 and 3.2: FIRST / HOP.
RFC_SOURCE_FIELD = "FIRST"
RFC_DEST_FIELD = "HOP"
RFC_FIRSTHOP_DEST = RFC_DEST_FIELD
RFC_SOURCE_DIRECTIVE = "first=message"
RFC_DEST_DIRECTIVE = "hop=message"
DEFAULT_SOURCE = "FIRST"
DEST_HOP = "HOP"
SOURCE_HEADER = "First"
DEST_HEADER = "Hop"
FIRSTHOP_DEST_HEADER = DEST_HEADER
RFC_SOURCE_PATH = "/firsthop/"
RFC_SOURCE_EMPTY = ""


def firsthop_directive_pair(*, local: bool = False) -> tuple[str, str]:
    """RFC 8028 First / Hop directive pair."""

    if local:
        return "hop", "message"
    return "first", "message"


def ascii_serialize_firsthop_directive(*, local: bool = False) -> str:
    """RFC 8028 token "=" body-or-local."""

    name, value = firsthop_directive_pair(local=local)
    if not is_token(name):
        raise FirsthopActuationError("illegal_directive")
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
            raise FirsthopActuationError("short_firsthop")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 8028 body-unique token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_firsthop(policy: str | Sequence[str]) -> str:
    """Serialize RFC 8028 FIRST / HOP opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise FirsthopActuationError("illegal_firsthop")
    upper = text.upper().replace("_", "-")
    if upper in {"FIRST", "FIRSTHOP", "FIRSTHOP-FIRST"}:
        return "FIRST"
    if upper in {"HOP", "ROUTER", "FIRSTHOP-HOP"}:
        return "HOP"
    if upper.startswith("FIRST="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise FirsthopActuationError("illegal_firsthop")
        return "FIRST"
    if upper.startswith("HOP="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise FirsthopActuationError("illegal_firsthop")
        return "HOP"
    raise FirsthopActuationError("illegal_firsthop")


def parse_firsthop(text: str) -> str:
    """Parse RFC 8028 FIRSTHOP opcode header extensions into FIRST or HOP."""

    raw = str(text or "").strip()
    if not raw:
        raise FirsthopActuationError("illegal_firsthop")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"FIRST", "FIRSTHOP", "FIRSTHOP-FIRST"}:
        return "FIRST"
    if upper in {"HOP", "ROUTER", "FIRSTHOP-HOP"}:
        return "HOP"
    if upper.startswith("FIRST="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise FirsthopActuationError("illegal_firsthop")
        return "FIRST"
    if upper.startswith("HOP="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise FirsthopActuationError("illegal_firsthop")
        return "HOP"
    raise FirsthopActuationError("illegal_firsthop")


def encode_firsthop_header(policy: str | Sequence[str]) -> bytes:
    """RFC 8028 HTTP/1.0 field as bytes."""

    return serialize_firsthop(policy).encode("ascii")


def parse_firsthop_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_firsthop(field_value) if field_value else DEFAULT_SOURCE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": SOURCE_HEADER,
        "directive": str(policy),
        "is_first": str(policy) == "FIRST",
        "table": str(policy) == "HOP",
    }


def canonical_temporary(identity: str, hopid: int) -> str:
    """RFC 8028 body-unique advertisement bound to identity and hopid."""

    return (
        f"{serialize_firsthop(DEFAULT_SOURCE)}, "
        f"first={ascii_serialize_firsthop_directive()}, "
        f"identity={identity}, hopid={int(hopid) & 0xFFFFFFFF}"
    )


def canonical_public(identity: str, hopid: int, hopdigest: int | None = None) -> str:
    """RFC 8028 local-message confirmation of the stored identifier-digest."""

    digest = ""
    if hopdigest is not None:
        digest = f", hopdigest={int(hopdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_firsthop(DEST_HOP)}, "
        f"hop={ascii_serialize_firsthop_directive(local=True)}, "
        f"identity={identity}, hopid={int(hopid) & 0xFFFFFFFF}{digest}"
    )


def representation_public(identity: str, hopid: int, hopdigest: int) -> str:
    return canonical_public(identity, hopid, hopdigest)


def firsthop_matches(left: str, right: str) -> bool:
    return parse_firsthop(left) == parse_firsthop(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise FirsthopActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise FirsthopActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise FirsthopActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise FirsthopActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def temporary_request(identity: str, hopid: int) -> bytes:
    """HTTP FIRST that elicits RFC 8028 origin HTTP/1.0."""

    keyid = f"{int(hopid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"FIRST /firsthop/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Hop-Id: {int(hopid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def public_request(identity: str, hopid: int, hopdigest: int | None = None) -> bytes:
    """HTTP HOP carrying RFC 8028 local-message confirmation of the stored identifier-digest."""

    keyid = f"{int(hopid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if hopdigest is not None:
        extra = f"Hop-Digest: {int(hopdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"HOP /firsthop/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Hop-Id: {int(hopid) & 0xFFFFFFFF}\r\n"
        "Hop-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    firsthop_kind = "hop" if fields.get("hop-confirm") == "1" else "first"
    upgrade_field = fields.get("first") or fields.get("firsthop") or ""
    policy = parse_firsthop(upgrade_field) if upgrade_field else ()
    return {
        "kind": "first",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "firsthop_kind": firsthop_kind,
        "policy": policy,
        "hopid": int(fields["hop-id"]) if fields.get("hop-id") else EMPTY_HOPID,
        "hopdigest": int(fields["hop-digest"]) if fields.get("hop-digest") else EMPTY_HOPDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def temporary_response(identity: str, hopid: int, hopdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 8028 origin HTTP/1.0, carrying the stored hopdigest."""

    publicised = serialize_firsthop(DEFAULT_SOURCE)
    payload = bytes(body or canonical_temporary(identity, hopid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"First: {publicised}\r\n"
        f"Hop-Id: {int(hopid) & 0xFFFFFFFF}\r\n"
        f"Hop-Digest: {int(hopdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def public_response(identity: str, hopid: int, hopdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 8028 HOP, carrying the stored identifier-digest."""

    publicised = serialize_firsthop(DEST_HOP)
    payload = bytes(body or representation_public(identity, hopid, hopdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"First: {publicised}\r\n"
        f"Hop-Id: {int(hopid) & 0xFFFFFFFF}\r\n"
        f"Hop-Digest: {int(hopdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/firsthop-hop\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise FirsthopActuationError("illegal_content_length") from error
    field_value = fields.get("first") or fields.get("firsthop") or ""
    policy = parse_firsthop(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/firsthop-hop" or policy == DEST_HOP:
        status = 200
        firsthop_kind = "hop"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        firsthop_kind = "first"
    else:
        status = 0
        firsthop_kind = "first"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "firsthop_kind": firsthop_kind,
        "policy": policy,
        "hopid": int(fields["hop-id"]) if fields.get("hop-id") else EMPTY_HOPID,
        "hopdigest": int(fields["hop-digest"]) if fields.get("hop-digest") else EMPTY_HOPDIGEST,
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
        raise FirsthopActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise FirsthopActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise FirsthopActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise FirsthopActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc8028_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    ula: str,
) -> str:
    """RFC 8028 identifier digest over method, router-IP, identity, and hopid."""

    payload = f"{method}:{ula}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def temporary_hopid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"hopid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_hopid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-hopid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def temporary_hopdigest(hopid: int = EMPTY_HOPID, token: str = SENTINEL) -> int:
    nonce = f"{int(hopid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc8028_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="HOP",
        ula=f"/firsthop/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_HOPID = temporary_hopid(SENTINEL)
DEFAULT_HOPDIGEST = temporary_hopdigest(DEFAULT_HOPID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    hopid: int,
    hopdigest: int,
    include_hopid: bool = True,
) -> bytes:
    live_hopid = int(hopid) & 0xFFFFFFFF if include_hopid else EMPTY_HOPID
    live_digest = int(hopdigest) & 0xFFFFFFFF if include_hopid and live_hopid else EMPTY_HOPDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_hopid) if live_hopid else b""
    header = bytearray()
    header.append(FIRSTHOP_FIRST)
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
    hopid: int,
    hopdigest: int | None = None,
    include_hopid: bool = True,
) -> bytes:
    live_hopid = int(hopid) & 0xFFFFFFFF if include_hopid else EMPTY_HOPID
    live_digest = int(hopdigest) if hopdigest is not None else temporary_hopdigest(live_hopid, identity)
    return encode_packet(
        FRAME_SOURCE,
        identity=identity,
        hopid=live_hopid,
        hopdigest=live_digest,
        include_hopid=include_hopid,
    )


def encode_public(
    *,
    identity: str,
    hopid: int,
    hopdigest: int | None = None,
    include_hopid: bool = True,
) -> bytes:
    live_hopid = int(hopid) & 0xFFFFFFFF if include_hopid else EMPTY_HOPID
    live_digest = int(hopdigest) if hopdigest is not None else temporary_hopdigest(live_hopid, identity)
    return encode_packet(
        FRAME_DEST,
        identity=identity,
        hopid=live_hopid,
        hopdigest=live_digest,
        include_hopid=include_hopid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise FirsthopActuationError("short_packet")
    first = raw[0]
    if first != FIRSTHOP_FIRST:
        raise FirsthopActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise FirsthopActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == HOPID_SIZE:
        live_hopid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_hopid = EMPTY_HOPID
    else:
        raise FirsthopActuationError("illegal_hopid")
    if offset >= len(raw):
        raise FirsthopActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SOURCE, FRAME_DEST}:
        raise FirsthopActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise FirsthopActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise FirsthopActuationError("checksum_failed")
    if len(payload) < 5:
        raise FirsthopActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise FirsthopActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_hopid = int(live_hopid) != EMPTY_HOPID
    has_hopdigest = has_hopid and int(live_digest) != EMPTY_HOPDIGEST
    is_temporary = frame_type == FRAME_SOURCE
    is_public = frame_type == FRAME_DEST
    return {
        "type": int(frame_type),
        "is_temporary": is_temporary,
        "is_public": is_public,
        "hopid": int(live_hopid),
        "has_hopid": has_hopid,
        "hopdigest": int(live_digest),
        "has_hopdigest": has_hopdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC8028",
        "serialize_field": canonical_temporary(identity, live_hopid) if has_hopid else "",
        "tls_field": canonical_public(identity, live_hopid, live_digest) if has_hopdigest else "",
    }


class FirsthopClient:
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
            raise FirsthopActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_public"] or not packet["is_public"]:
            raise FirsthopActuationError("hopdigest_required")
        if not packet["has_hopid"]:
            raise FirsthopActuationError("hopid_required")
        if not packet["has_hopdigest"]:
            raise FirsthopActuationError("hopdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_hopdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_hopdigest:
            raise FirsthopActuationError("hopdigest_required")
        prefix = self._recv()
        return {
            "session": prefix,
            "hopid": int(prefix.get("hopid") or EMPTY_HOPID),
            "identity": str(prefix.get("identity") or ""),
            "hopdigest": int(prefix.get("hopdigest") or EMPTY_HOPDIGEST),
        }

    def local(
        self,
        identity: str,
        hopid: int,
        hopdigest: int = EMPTY_HOPDIGEST,
        *,
        wait_hopdigest: bool = True,
        include_hopid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_public(
            identity=identity,
            hopid=hopid,
            hopdigest=hopdigest or temporary_hopdigest(hopid, identity),
            include_hopid=include_hopid,
        )
        return self.exchange(packet, wait_hopdigest=wait_hopdigest)


class FirsthopSession:
    """HOPID-gated loopback RFC 8028 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        hopid_gate: int = DEFAULT_HOPID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.hopid_gate = int(hopid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.hopid = EMPTY_HOPID
        self.hopdigest = EMPTY_HOPDIGEST
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

    def store_hopid_once(self, identity: str, hopid: int, hopdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(hopid or EMPTY_HOPID)
            live_digest = int(hopdigest or EMPTY_HOPDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.hopid = live
                self.hopdigest = live_digest or temporary_hopdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.hopid), int(self.hopdigest)

    def read_hopid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.hopid), int(self.hopdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "hopid": EMPTY_HOPID,
            "hopdigest": EMPTY_HOPDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _hopid_missing(self) -> bool:
        return not int(self.hopid_gate or 0)

    def _public_tuple(self, peer: tuple[str, int], identity: str, hopid: int, hopdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_public(
            identity=identity,
            hopid=hopid,
            hopdigest=hopdigest,
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
            except FirsthopActuationError:
                continue
            if not packet.get("is_temporary") and not packet.get("is_public"):
                continue
            if not packet.get("has_hopid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_hopid, stored_digest = self.store_hopid_once(
                identity,
                int(packet.get("hopid") or EMPTY_HOPID),
                int(packet.get("hopdigest") or EMPTY_HOPDIGEST),
            )
            if not stored_name or not stored_hopid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_temporary"):
                    self.opened = True
                if packet.get("is_public"):
                    self.handshook = True
                self.retrieved = True
            self._public_tuple(peer, stored_name, stored_hopid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._hopid_missing():
            return self._forbidden("missing_hopid")
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
        do_hopdigest: bool = True,
        replay: bool = True,
        use_hopid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._hopid_missing():
            return self._forbidden("missing_hopid")
        live_token = str(token or SENTINEL)
        origin_hopid = temporary_hopid(live_token)
        origin_digest = temporary_hopdigest(origin_hopid, live_token)
        client: FirsthopClient | None = None
        independent: FirsthopClient | None = None
        try:
            client = FirsthopClient(self.host, int(self.port))
            if not do_temporary:
                return self._conflict("temporary_required")
            bind_packet = encode_temporary(
                identity=live_token,
                hopid=origin_hopid,
                hopdigest=origin_digest,
                include_hopid=use_hopid,
            )
            if not use_hopid:
                try:
                    client.exchange(bind_packet, wait_hopdigest=True)
                except FirsthopActuationError:
                    return self._conflict("hopid_required")
                return self._conflict("hopid_required")
            client.send(bind_packet)
            if not do_public:
                return self._conflict("public_required")
            proxy_packet = encode_public(
                identity=live_token,
                hopid=origin_hopid,
                hopdigest=origin_digest,
                include_hopid=True,
            )
            if not do_hopdigest:
                try:
                    client.exchange(proxy_packet, wait_hopdigest=False)
                except FirsthopActuationError as error:
                    if str(error) == "hopdigest_required":
                        return self._conflict("hopdigest_required")
                    return self._conflict("hopdigest_required")
                return self._conflict("hopdigest_required")
            try:
                prefix = client.exchange(proxy_packet, wait_hopdigest=True)
            except FirsthopActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("hopid_required")
                if reason == "hopdigest_required":
                    return self._conflict("hopdigest_required")
                return self._conflict("temporary_required")
            if str(prefix.get("identity") or "") != live_token:
                return self._conflict("temporary_required")
            if int(prefix.get("hopid") or EMPTY_HOPID) != origin_hopid:
                return self._conflict("hopdigest_required")
            if int(prefix.get("hopdigest") or EMPTY_HOPDIGEST) != origin_digest:
                return self._conflict("hopdigest_required")
            self.retrieved = True
            if replay:
                independent = FirsthopClient(self.host, int(self.port))
                try:
                    poll = independent.local(
                        POLL_TOKEN,
                        poll_hopid(live_token),
                        temporary_hopdigest(poll_hopid(live_token), POLL_TOKEN),
                        wait_hopdigest=True,
                    )
                except FirsthopActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_hopid, stored_digest = self.read_hopid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_hopid != origin_hopid
                    or stored_digest != origin_digest
                    or int(poll.get("hopid") or EMPTY_HOPID) != origin_hopid
                    or int(poll.get("hopdigest") or EMPTY_HOPDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_hopid}:{origin_digest}:{live_token}:{canonical_temporary(live_token, origin_hopid)}:{canonical_public(live_token, origin_hopid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "hopid": origin_hopid,
                "hopdigest": origin_digest,
                "temporary_frame": True,
                "public_frame": True,
                "hopdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "hopid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_hopdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "hopid": origin_hopid,
                "hopdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "temporary_frame": True,
                "public_frame": True,
                "hopdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "hopid_bound": True,
            }
        except (OSError, FirsthopActuationError) as error:
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
        live = independent_hopdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "hopid": int(live.get("hopid") or EMPTY_HOPID),
            "hopdigest": int(live.get("hopdigest") or EMPTY_HOPDIGEST),
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


def call_firsthop_tool(session: FirsthopSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one firsthop tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_temporary = True if arguments.get("first") is None else bool(arguments.get("first"))
    do_public = True if arguments.get("hop") is None else bool(arguments.get("hop"))
    do_hopdigest = True if arguments.get("hopdigest") is None else bool(arguments.get("hopdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_hopid = True if arguments.get("use_hopid") is None else bool(arguments.get("use_hopid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_temporary=do_temporary,
            do_public=do_public,
            do_hopdigest=do_hopdigest,
            replay=replay,
            use_hopid=use_hopid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise FirsthopActuationError(f"unsupported firsthop action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_hopdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage hopdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "hopid": EMPTY_HOPID,
        "hopdigest": EMPTY_HOPDIGEST,
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
            "hopdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "hopid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    hopid = int(payload.get("hopid") or EMPTY_HOPID)
    hopdigest = int(payload.get("hopdigest") or EMPTY_HOPDIGEST)
    dual = port > 0 and bool(hopid) and bool(hopdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "hopid": hopid,
        "hopdigest": hopdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "temporary_frame": payload.get("temporary_frame") is True,
        "public_frame": payload.get("public_frame") is True,
        "hopdigest_locate": payload.get("hopdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "hopid_bound": payload.get("hopid_bound") is True,
    }


def run_firsthop_workflow(
    *,
    with_hopid: bool = True,
    skip_bind: bool = False,
    do_temporary: bool = True,
    do_public: bool = True,
    do_hopdigest: bool = True,
    replay: bool = True,
    use_hopid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 8028 FIRST/HOP hopid cycle workflow."""

    descriptor = firsthop_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FIRSTHOP_TOOL_PROVIDER),
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
        raise FirsthopActuationError(f"firsthop tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="firsthop-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = FirsthopSession(out, hopid_gate=DEFAULT_HOPID if with_hopid else EMPTY_HOPID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "first": do_temporary,
            "hop": do_public,
            "hopdigest": do_hopdigest,
            "replay": replay,
            "use_hopid": use_hopid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_firsthop_tool(session, arguments))
            except FirsthopActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_hopdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_hopid
        and not skip_bind
        and do_temporary
        and do_public
        and do_hopdigest
        and replay
        and use_hopid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "firsthop_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_hopid": with_hopid,
        "skip_bind": skip_bind,
        "temporary_frame": do_temporary,
        "public_frame": do_public,
        "hopdigest": do_hopdigest,
        "replay": replay,
        "use_hopid": use_hopid,
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
        "hopid_value": int(publish_result.get("hopid") or independent.get("hopid") or EMPTY_HOPID),
        "hopdigest_value": int(publish_result.get("hopdigest") or independent.get("hopdigest") or EMPTY_HOPDIGEST),
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
        "hopid": int(trace_body["hopid_value"] or EMPTY_HOPID),
        "hopdigest": int(trace_body["hopdigest_value"] or EMPTY_HOPDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_hopid": with_hopid,
        "skip_bind": skip_bind,
        "temporary_cycle": do_temporary,
        "public_cycle": do_public,
        "hopdigest_cycle": do_hopdigest,
        "replay": replay,
        "use_hopid": use_hopid,
    }


def verify_firsthop_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_hopdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    hopid = int(trace.get("hopid_value") or independent.get("hopid") or EMPTY_HOPID)
    hopdigest = int(trace.get("hopdigest_value") or independent.get("hopdigest") or EMPTY_HOPDIGEST)
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
        "hopdigest_locate": independent.get("hopdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "hopid_bound": independent.get("hopid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "hopdigest_recorded": (
            port > 0
            and hopid == DEFAULT_HOPID
            and hopdigest == DEFAULT_HOPDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def firsthop_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.firsthop_actuation import "
        "builtin_firsthop_actuation_proof; r=builtin_firsthop_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='firsthop_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_firsthop_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=FIRSTHOP_ACTUATION_ID,
        name="First-class RFC 8028 First-Hop Router Selection by Hosts in a Multi-Prefix Network FIRST/HOP actuation",
        description=(
            "Missions that require a firsthop tool can opt the firsthop provider in, "
            "bind a loopback RFC 8028 First-Hop Router Selection by Hosts in a Multi-Prefix Network endpoint, complete a FIRST "
            "with a non-empty hopid, lockstep a HOP that carries the "
            "stored hopdigest, independently poll the stored hopdigest "
            "on a later socket, and seal a digest-chained hopdigest. Default "
            "routing stays fail-closed; a missing hopid keeps the hole "
            "falsifiable, and skip-FIRST/HOP/HOPDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.firsthop_actuation:builtin_firsthop_actuation_proof",
        proof_command=firsthop_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.addrpolicy-actuation",
        ),
        behavior_paths=(
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
            "src/blackhole_agent/rdnss_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required firsthop tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 8028 daemon, speaks a "
            "FIRST then HOP over First-Hop Router Selection by Hosts in a Multi-Prefix Network with a non-empty hopid and "
            "hopdigest, independently polls the stored hopdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 7078 Distributing Address Selection Policy using DHCPv6 lockstep is proved. "
            "Missing hopids, skip-FIRST, skip-HOP, skip-hopdigest, skip-REPLAY, "
            "and a FIRST aimed without a hopid stay fail-closed. "
            "Later genesis can take RFC 8106 IPv6 Router Advertisement Options for DNS Configuration RDNSS/DNSSL as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("firsthop", "rfc8028", "http", "hopid", "hopdigest", "first", "hop", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260907T004403Z-ec5f8a8b",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_firsthop_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 8028 first/hop lockstep actuation seals a hopdigest."""

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
    from blackhole_agent.rdnss_actuation import (
        RDNSS_ACTUATION_GOAL,
        RDNSS_ACTUATION_ID,
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
    checks["denylists_self"] = FIRSTHOP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(FIRSTHOP_ACTUATION_GOAL) == (
        FIRSTHOP_ACTUATION_ID,
    )
    checks["leftover_text_binds_firsthop"] = leftover_marker_ids(FIRSTHOP_LEFTOVER) == (
        FIRSTHOP_ACTUATION_ID,
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
        (RDNSS_ACTUATION_GOAL, RDNSS_ACTUATION_ID, "rdnss"),
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
        checks[f"{name}_goal_is_not_firsthop"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"firsthop_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            FIRSTHOP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = FIRSTHOP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    publicised = serialize_firsthop(DEFAULT_SOURCE)
    rebuilt = serialize_firsthop(parse_firsthop(publicised))
    preloaded = parse_firsthop(RFC_FIRSTHOP_DEST)
    header = encode_firsthop_header(DEFAULT_SOURCE)
    parsed_header = parse_firsthop_header(header)
    asked = parse_http_request(temporary_request(SENTINEL, DEFAULT_HOPID))
    preload_req = parse_http_request(public_request(SENTINEL, DEFAULT_HOPID, DEFAULT_HOPDIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_HOPID, DEFAULT_HOPDIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_HOPID, DEFAULT_HOPDIGEST)
    )
    checks["firsthop_roundtrip"] = (
        parse_firsthop(publicised) == DEFAULT_SOURCE
        and hmac.compare_digest(rebuilt, publicised)
        and publicised == RFC_SOURCE_FIELD
        and is_token("FIRST") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_SOURCE_FIELD
        and parsed_header["policy"] == DEFAULT_SOURCE
        and parsed_header["header"] == SOURCE_HEADER
        and parsed_header["is_first"] is True
        and parsed_header["table"] is False
        and preloaded == DEST_HOP
        and ascii_serialize_firsthop_directive() == RFC_SOURCE_DIRECTIVE
        and firsthop_directive_pair() == ("first", "message")
        and RFC_SOURCE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_firsthop(DEST_HOP) == RFC_FIRSTHOP_DEST
        and DEFAULT_HOPDIGEST == temporary_hopdigest(DEFAULT_HOPID, SENTINEL)
        and "hopdigest=" in canonical_public(SENTINEL, DEFAULT_HOPID, DEFAULT_HOPDIGEST)
        and canonical_temporary(SENTINEL, DEFAULT_HOPID).startswith("FIRST")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "FIRST"
        and asked["firsthop_kind"] == "first"
        and asked["hopid"] == DEFAULT_HOPID
        and preload_req["firsthop_kind"] == "hop"
        and preload_req["hopdigest"] == DEFAULT_HOPDIGEST
        and got["status"] == 200
        and preload_public["status"] == 200
        and got["firsthop_kind"] == "first"
        and preload_public["firsthop_kind"] == "hop"
        and got["policy"] == DEFAULT_SOURCE
        and preload_public["policy"] == DEST_HOP
        and got["content_length_matches_body"] is True
        and preload_public["content_length_matches_body"] is True
        and got["hopdigest"] == DEFAULT_HOPDIGEST
        and preload_public["hopdigest"] == DEFAULT_HOPDIGEST
        and firsthop_matches(serialize_firsthop(got["policy"]), publicised)
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
    family = capability_family(FIRSTHOP_ACTUATION_GOAL)
    checks["family_is_firsthop"] = "firsthop" in family.split("/")
    checks["family_is_firsthop_surface"] = "hopid" in family
    checks["family_is_hopid"] = "hopid" in family
    checks["family_is_rfc8028"] = "rfc8028" in family
    checks["family_is_hopdigest"] = "hopdigest" in family
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
    checks["family_is_not_rdnss"] = (
        "rdnss" not in family.split("/")
        and "rfc8106" not in family
        and "rdnssid" not in family
        and "rdnssdigest" not in family
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
    packed = encode_temporary(identity=SENTINEL, hopid=DEFAULT_HOPID, hopdigest=DEFAULT_HOPDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_temporary"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_hopid"] is True
        and parsed["hopid"] == DEFAULT_HOPID
        and parsed["hopdigest"] == DEFAULT_HOPDIGEST
        and parsed["is_public"] is False
        and parsed["is_public"] is False
        and parsed["type"] == FRAME_SOURCE
        and parsed["first_byte"] == FIRSTHOP_FIRST
    )
    shook = encode_public(
        identity=SENTINEL,
        hopid=DEFAULT_HOPID,
        hopdigest=DEFAULT_HOPDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_public"] is True
        and answer_parsed["is_public"] is True
        and answer_parsed["is_temporary"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["hopid"] == DEFAULT_HOPID
        and answer_parsed["hopdigest"] == DEFAULT_HOPDIGEST
        and answer_parsed["has_hopdigest"] is True
        and answer_parsed["type"] == FRAME_DEST
        and answer_parsed["first_byte"] == FIRSTHOP_FIRST
    )
    bare = encode_temporary(identity=SENTINEL, hopid=DEFAULT_HOPID, include_hopid=False)
    checks["missing_hopid_is_unauthed"] = parse_message(bare)["has_hopid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(FIRSTHOP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_firsthop = ToolDescriptor(name="remote_firsthop", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_firsthop)
    checks["naive_mcp_firsthop_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = firsthop_tool_descriptor()
    default_firsthop = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FIRSTHOP_TOOL_PROVIDER),
    )
    checks["default_firsthop_provider_is_unsupported"] = (
        default_firsthop.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{FIRSTHOP_TOOL_PROVIDER}" in default_firsthop.reasons
    )
    checks["opted_in_firsthop_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_firsthop],
        required_tool_names=("local_memory", "firsthop"),
    )
    checks["naive_preflight_missing_firsthop"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["firsthop"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "firsthop"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FIRSTHOP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "firsthop" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="firsthop-actuation-") as tmp:
        root = Path(tmp)
        missing = run_firsthop_workflow(with_hopid=False, output_dir=root / "missing")
        skip_bind = run_firsthop_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_temporary = run_firsthop_workflow(do_temporary=False, output_dir=root / "skip-first")
        skip_public = run_firsthop_workflow(do_public=False, output_dir=root / "skip-hop")
        skip_hopdigest = run_firsthop_workflow(do_hopdigest=False, output_dir=root / "skip-hopdigest")
        skip_replay = run_firsthop_workflow(replay=False, output_dir=root / "skip-replay")
        skip_hopid = run_firsthop_workflow(use_hopid=False, output_dir=root / "skip-hopid")
        live = run_firsthop_workflow(output_dir=root / "live")
        sealed = verify_firsthop_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_firsthop_trace(clone)
        checks["naive_without_hopid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_hopid"
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
        checks["skip_hopdigest_stays_empty"] = (
            skip_hopdigest["ok"] is False
            and skip_hopdigest["error"] == "hopdigest_required"
            and skip_hopdigest["final_status"] == 409
            and skip_hopdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_hopid_stays_empty"] = (
            skip_hopid["ok"] is False
            and skip_hopid["error"] == "hopid_required"
            and skip_hopid["final_status"] == 409
            and skip_hopid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_hopdigest"] = (
            int(live.get("hopid") or 0) == DEFAULT_HOPID
            and int(live.get("hopdigest") or 0) == DEFAULT_HOPDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_hopid_encode_public_hopdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_temporary["ok"] is False
            and skip_public["ok"] is False
            and skip_hopdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_hopid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = sealed["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="firsthop-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != FIRSTHOP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, FIRSTHOP_ACTUATION_GOAL, FIRSTHOP_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_firsthop"] = (
        not gate.accepted
        and live_goal != FIRSTHOP_ACTUATION_GOAL
        and FIRSTHOP_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_firsthop"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="firsthop-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(FIRSTHOP_LEFTOVER, root)
        register_catalog_proved(root, FIRSTHOP_ACTUATION_ID)
        reason = leftover_satisfied_by(FIRSTHOP_LEFTOVER, root)
        after = leftover_is_open(FIRSTHOP_LEFTOVER, root)
    checks["firsthop_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_firsthop_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{FIRSTHOP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_firsthop_actuation_capability()
    return {
        "ok": ok,
        "action": "firsthop_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": FIRSTHOP_ACTUATION_GOAL,
        "done_when": FIRSTHOP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
