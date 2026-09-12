"""Drive a first-class Network News Transfer Protocol tool through RFC 977 ARTICLE/GROUP.

Tool routing already fails missions that require ``nntp``: hosted
nntp endpoints stay on the unsupported MCP provider, and no first-party
nntp provider is executable. Unbound therefore cannot speak an ARTICLE,
lockstep a GROUP nntpid handshake over HTTP/1.0 NNTPID,
independently poll the stored nntpdigest, or seal a nntpdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``nntp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 977 daemon
- keep a missing-nntpid client so the nntp-nntpid hole stays falsifiable
- refuse GROUP until an ARTICLE lands with a non-empty nntpid
- independently poll the stored nntpdigest on a later client socket
- persist a sealed nntpdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 1179 Line Printer Daemon Protocol
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
    NNTP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    nntp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
NNTP_ACTUATION_ID = "capability.nntp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-NNTP-OK"
POLL_TOKEN = "BH-NNTP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_NNTPID = 0
EMPTY_NNTPDIGEST = 0
NNTP_FIRST = 0x4E  # RFC 977 NNTP (ASCII 'N')
NNTPID_SIZE = 4
NNTPDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_GROUP = 0x02  # RFC 977 GROUP confirmation
FRAME_ARTICLE = 0x01  # RFC 977 ARTICLE
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
NNTP_LEFTOVER = (
    "Later genesis can take RFC 977 Network News Transfer Protocol ARTICLE/GROUP over an "
    "nntpid-gated nntpdigest."
)
NNTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{NNTP_ACTUATION_ID};"
    f"capability_proved:{NNTP_ACTUATION_ID};"
    "no_skill_route"
)
NNTP_ACTUATION_GOAL = (
    "Repair rfc977 nntp article/group cycle cannot land over http "
    "nntp nntpid: hosted nntp endpoints remain unsupported so an ARTICLE then "
    "GROUP nntpid handshake cannot land and a sealed nntpdigest "
    "cannot be produced. A missing nntp nntpid stays forbidden; fail-closed "
    "routing never opts the nntp provider in. An independent later poll of the "
    "stored nntpdigest keeps the hole falsifiable."
)


class NntpActuationError(RuntimeError):
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
# RFC 977 sections 2.1 and 2.1.2: ARTICLE / GROUP.
RFC_ARTICLE_FIELD = "ARTICLE"
RFC_GROUP_FIELD = "GROUP"
RFC_NNTP_GROUP = RFC_GROUP_FIELD
RFC_ARTICLE_DIRECTIVE = "article=message"
RFC_GROUP_DIRECTIVE = "group=newsgroup"
DEFAULT_ARTICLE = "ARTICLE"
GROUP_POLICY = "GROUP"
ARTICLE_HEADER = "Article"
GROUP_HEADER = "Group"
NNTP_GROUP_HEADER = GROUP_HEADER
RFC_ARTICLE_PATH = "/nntp/"
RFC_ARTICLE_EMPTY = ""


def nntp_directive_pair(*, group: bool = False) -> tuple[str, str]:
    """RFC 977 Article / Group directive pair."""

    if group:
        return "group", "newsgroup"
    return "article", "message"


def ascii_serialize_nntp_directive(*, group: bool = False) -> str:
    """RFC 977 token "=" body-or-group."""

    name, value = nntp_directive_pair(group=group)
    if not is_token(name):
        raise NntpActuationError("illegal_directive")
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
            raise NntpActuationError("short_nntp")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 977 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_nntp(policy: str | Sequence[str]) -> str:
    """Serialize RFC 977 ARTICLE / GROUP opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise NntpActuationError("illegal_nntp")
    upper = text.upper().replace("_", "-")
    if upper in {"ARTICLE", "NNTP", "NNTP-ARTICLE"}:
        return "ARTICLE"
    if upper in {"GROUP", "RESOURCE", "NNTP-GROUP"}:
        return "GROUP"
    if upper.startswith("ARTICLE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise NntpActuationError("illegal_nntp")
        return "ARTICLE"
    if upper.startswith("GROUP="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise NntpActuationError("illegal_nntp")
        return "GROUP"
    raise NntpActuationError("illegal_nntp")


def parse_nntp(text: str) -> str:
    """Parse RFC 977 NNTP opcode header extensions into ARTICLE or GROUP."""

    raw = str(text or "").strip()
    if not raw:
        raise NntpActuationError("illegal_nntp")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"ARTICLE", "NNTP", "NNTP-ARTICLE"}:
        return "ARTICLE"
    if upper in {"GROUP", "RESOURCE", "NNTP-GROUP"}:
        return "GROUP"
    if upper.startswith("ARTICLE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise NntpActuationError("illegal_nntp")
        return "ARTICLE"
    if upper.startswith("GROUP="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise NntpActuationError("illegal_nntp")
        return "GROUP"
    raise NntpActuationError("illegal_nntp")


def encode_nntp_header(policy: str | Sequence[str]) -> bytes:
    """RFC 977 HTTP/1.0 field as bytes."""

    return serialize_nntp(policy).encode("ascii")


def parse_nntp_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_nntp(field_value) if field_value else DEFAULT_ARTICLE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": ARTICLE_HEADER,
        "directive": str(policy),
        "article": str(policy) == "ARTICLE",
        "group": str(policy) == "GROUP",
    }


def canonical_article(identity: str, nntpid: int) -> str:
    """RFC 977 body-request advertisement bound to identity and nntpid."""

    return (
        f"{serialize_nntp(DEFAULT_ARTICLE)}, "
        f"article={ascii_serialize_nntp_directive()}, "
        f"identity={identity}, nntpid={int(nntpid) & 0xFFFFFFFF}"
    )


def canonical_group(identity: str, nntpid: int, nntpdigest: int | None = None) -> str:
    """RFC 977 group-newsgroup confirmation of the stored identifier-digest."""

    digest = ""
    if nntpdigest is not None:
        digest = f", nntpdigest={int(nntpdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_nntp(GROUP_POLICY)}, "
        f"group={ascii_serialize_nntp_directive(group=True)}, "
        f"identity={identity}, nntpid={int(nntpid) & 0xFFFFFFFF}{digest}"
    )


def representation_group(identity: str, nntpid: int, nntpdigest: int) -> str:
    return canonical_group(identity, nntpid, nntpdigest)


def nntp_matches(left: str, right: str) -> bool:
    return parse_nntp(left) == parse_nntp(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise NntpActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise NntpActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise NntpActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise NntpActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def article_request(identity: str, nntpid: int) -> bytes:
    """HTTP ARTICLE that elicits RFC 977 origin HTTP/1.0."""

    keyid = f"{int(nntpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"ARTICLE /nntp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Nntp-Id: {int(nntpid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def group_request(identity: str, nntpid: int, nntpdigest: int | None = None) -> bytes:
    """HTTP GROUP carrying RFC 977 group-newsgroup confirmation of the stored identifier-digest."""

    keyid = f"{int(nntpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if nntpdigest is not None:
        extra = f"Nntp-Digest: {int(nntpdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GROUP /nntp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Nntp-Id: {int(nntpid) & 0xFFFFFFFF}\r\n"
        "Group-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    nntp_kind = "group" if fields.get("group-confirm") == "1" else "article"
    upgrade_field = fields.get("article") or fields.get("nntp") or ""
    policy = parse_nntp(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "nntp_kind": nntp_kind,
        "policy": policy,
        "nntpid": int(fields["nntp-id"]) if fields.get("nntp-id") else EMPTY_NNTPID,
        "nntpdigest": int(fields["nntp-digest"]) if fields.get("nntp-digest") else EMPTY_NNTPDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def article_response(identity: str, nntpid: int, nntpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 977 origin HTTP/1.0, carrying the stored nntpdigest."""

    advertised = serialize_nntp(DEFAULT_ARTICLE)
    payload = bytes(body or canonical_article(identity, nntpid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Article: {advertised}\r\n"
        f"Nntp-Id: {int(nntpid) & 0xFFFFFFFF}\r\n"
        f"Nntp-Digest: {int(nntpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def group_response(identity: str, nntpid: int, nntpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 977 GROUP, carrying the stored identifier-digest."""

    advertised = serialize_nntp(GROUP_POLICY)
    payload = bytes(body or representation_group(identity, nntpid, nntpdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Article: {advertised}\r\n"
        f"Nntp-Id: {int(nntpid) & 0xFFFFFFFF}\r\n"
        f"Nntp-Digest: {int(nntpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/nntp-group\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise NntpActuationError("illegal_content_length") from error
    field_value = fields.get("article") or fields.get("nntp") or ""
    policy = parse_nntp(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/nntp-group" or policy == GROUP_POLICY:
        status = 200
        nntp_kind = "group"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        nntp_kind = "article"
    else:
        status = 0
        nntp_kind = "article"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "nntp_kind": nntp_kind,
        "policy": policy,
        "nntpid": int(fields["nntp-id"]) if fields.get("nntp-id") else EMPTY_NNTPID,
        "nntpdigest": int(fields["nntp-digest"]) if fields.get("nntp-digest") else EMPTY_NNTPDIGEST,
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
        raise NntpActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise NntpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise NntpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise NntpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc977_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    nntp: str,
) -> str:
    """RFC 977 identifier digest over method, request-NNTP, identity, and nntpid."""

    payload = f"{method}:{nntp}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_nntpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"nntpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_nntpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-nntpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_nntpdigest(nntpid: int = EMPTY_NNTPID, token: str = SENTINEL) -> int:
    nonce = f"{int(nntpid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc977_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="GROUP",
        nntp=f"/nntp/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_NNTPID = request_nntpid(SENTINEL)
DEFAULT_NNTPDIGEST = request_nntpdigest(DEFAULT_NNTPID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    nntpid: int,
    nntpdigest: int,
    include_nntpid: bool = True,
) -> bytes:
    live_nntpid = int(nntpid) & 0xFFFFFFFF if include_nntpid else EMPTY_NNTPID
    live_digest = int(nntpdigest) & 0xFFFFFFFF if include_nntpid and live_nntpid else EMPTY_NNTPDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_nntpid) if live_nntpid else b""
    header = bytearray()
    header.append(NNTP_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_article(
    *,
    identity: str,
    nntpid: int,
    nntpdigest: int | None = None,
    include_nntpid: bool = True,
) -> bytes:
    live_nntpid = int(nntpid) & 0xFFFFFFFF if include_nntpid else EMPTY_NNTPID
    live_digest = int(nntpdigest) if nntpdigest is not None else request_nntpdigest(live_nntpid, identity)
    return encode_packet(
        FRAME_ARTICLE,
        identity=identity,
        nntpid=live_nntpid,
        nntpdigest=live_digest,
        include_nntpid=include_nntpid,
    )


def encode_group(
    *,
    identity: str,
    nntpid: int,
    nntpdigest: int | None = None,
    include_nntpid: bool = True,
) -> bytes:
    live_nntpid = int(nntpid) & 0xFFFFFFFF if include_nntpid else EMPTY_NNTPID
    live_digest = int(nntpdigest) if nntpdigest is not None else request_nntpdigest(live_nntpid, identity)
    return encode_packet(
        FRAME_GROUP,
        identity=identity,
        nntpid=live_nntpid,
        nntpdigest=live_digest,
        include_nntpid=include_nntpid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise NntpActuationError("short_packet")
    first = raw[0]
    if first != NNTP_FIRST:
        raise NntpActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise NntpActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == NNTPID_SIZE:
        live_nntpid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_nntpid = EMPTY_NNTPID
    else:
        raise NntpActuationError("illegal_nntpid")
    if offset >= len(raw):
        raise NntpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ARTICLE, FRAME_GROUP}:
        raise NntpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise NntpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise NntpActuationError("checksum_failed")
    if len(payload) < 5:
        raise NntpActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise NntpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_nntpid = int(live_nntpid) != EMPTY_NNTPID
    has_nntpdigest = has_nntpid and int(live_digest) != EMPTY_NNTPDIGEST
    is_article = frame_type == FRAME_ARTICLE
    is_group = frame_type == FRAME_GROUP
    return {
        "type": int(frame_type),
        "is_article": is_article,
        "is_group": is_group,
        "nntpid": int(live_nntpid),
        "has_nntpid": has_nntpid,
        "nntpdigest": int(live_digest),
        "has_nntpdigest": has_nntpdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC977",
        "serialize_field": canonical_article(identity, live_nntpid) if has_nntpid else "",
        "tls_field": canonical_group(identity, live_nntpid, live_digest) if has_nntpdigest else "",
    }


class NntpClient:
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
            raise NntpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_group"] or not packet["is_group"]:
            raise NntpActuationError("nntpdigest_required")
        if not packet["has_nntpid"]:
            raise NntpActuationError("nntpid_required")
        if not packet["has_nntpdigest"]:
            raise NntpActuationError("nntpdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_nntpdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_nntpdigest:
            raise NntpActuationError("nntpdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "nntpid": int(reply.get("nntpid") or EMPTY_NNTPID),
            "identity": str(reply.get("identity") or ""),
            "nntpdigest": int(reply.get("nntpdigest") or EMPTY_NNTPDIGEST),
        }

    def report(
        self,
        identity: str,
        nntpid: int,
        nntpdigest: int = EMPTY_NNTPDIGEST,
        *,
        wait_nntpdigest: bool = True,
        include_nntpid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_group(
            identity=identity,
            nntpid=nntpid,
            nntpdigest=nntpdigest or request_nntpdigest(nntpid, identity),
            include_nntpid=include_nntpid,
        )
        return self.exchange(packet, wait_nntpdigest=wait_nntpdigest)


class NntpSession:
    """NNTPID-gated loopback RFC 977 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        nntpid_gate: int = DEFAULT_NNTPID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.nntpid_gate = int(nntpid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.nntpid = EMPTY_NNTPID
        self.nntpdigest = EMPTY_NNTPDIGEST
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

    def store_nntpid_once(self, identity: str, nntpid: int, nntpdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(nntpid or EMPTY_NNTPID)
            live_digest = int(nntpdigest or EMPTY_NNTPDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.nntpid = live
                self.nntpdigest = live_digest or request_nntpdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.nntpid), int(self.nntpdigest)

    def read_nntpid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.nntpid), int(self.nntpdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "nntpid": EMPTY_NNTPID,
            "nntpdigest": EMPTY_NNTPDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _nntpid_missing(self) -> bool:
        return not int(self.nntpid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, nntpid: int, nntpdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_group(
            identity=identity,
            nntpid=nntpid,
            nntpdigest=nntpdigest,
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
            except NntpActuationError:
                continue
            if not packet.get("is_article") and not packet.get("is_group"):
                continue
            if not packet.get("has_nntpid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_nntpid, stored_digest = self.store_nntpid_once(
                identity,
                int(packet.get("nntpid") or EMPTY_NNTPID),
                int(packet.get("nntpdigest") or EMPTY_NNTPDIGEST),
            )
            if not stored_name or not stored_nntpid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_article"):
                    self.opened = True
                if packet.get("is_group"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_nntpid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._nntpid_missing():
            return self._forbidden("missing_nntpid")
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
        do_article: bool = True,
        do_group: bool = True,
        do_nntpdigest: bool = True,
        replay: bool = True,
        use_nntpid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._nntpid_missing():
            return self._forbidden("missing_nntpid")
        live_token = str(token or SENTINEL)
        origin_nntpid = request_nntpid(live_token)
        origin_digest = request_nntpdigest(origin_nntpid, live_token)
        client: NntpClient | None = None
        independent: NntpClient | None = None
        try:
            client = NntpClient(self.host, int(self.port))
            if not do_article:
                return self._conflict("article_required")
            bind_packet = encode_article(
                identity=live_token,
                nntpid=origin_nntpid,
                nntpdigest=origin_digest,
                include_nntpid=use_nntpid,
            )
            if not use_nntpid:
                try:
                    client.exchange(bind_packet, wait_nntpdigest=True)
                except NntpActuationError:
                    return self._conflict("nntpid_required")
                return self._conflict("nntpid_required")
            client.send(bind_packet)
            if not do_group:
                return self._conflict("group_required")
            proxy_packet = encode_group(
                identity=live_token,
                nntpid=origin_nntpid,
                nntpdigest=origin_digest,
                include_nntpid=True,
            )
            if not do_nntpdigest:
                try:
                    client.exchange(proxy_packet, wait_nntpdigest=False)
                except NntpActuationError as error:
                    if str(error) == "nntpdigest_required":
                        return self._conflict("nntpdigest_required")
                    return self._conflict("nntpdigest_required")
                return self._conflict("nntpdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_nntpdigest=True)
            except NntpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("nntpid_required")
                if reason == "nntpdigest_required":
                    return self._conflict("nntpdigest_required")
                return self._conflict("article_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("article_required")
            if int(reply.get("nntpid") or EMPTY_NNTPID) != origin_nntpid:
                return self._conflict("nntpdigest_required")
            if int(reply.get("nntpdigest") or EMPTY_NNTPDIGEST) != origin_digest:
                return self._conflict("nntpdigest_required")
            self.retrieved = True
            if replay:
                independent = NntpClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_nntpid(live_token),
                        request_nntpdigest(poll_nntpid(live_token), POLL_TOKEN),
                        wait_nntpdigest=True,
                    )
                except NntpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_nntpid, stored_digest = self.read_nntpid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_nntpid != origin_nntpid
                    or stored_digest != origin_digest
                    or int(poll.get("nntpid") or EMPTY_NNTPID) != origin_nntpid
                    or int(poll.get("nntpdigest") or EMPTY_NNTPDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_nntpid}:{origin_digest}:{live_token}:{canonical_article(live_token, origin_nntpid)}:{canonical_group(live_token, origin_nntpid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "nntpid": origin_nntpid,
                "nntpdigest": origin_digest,
                "article_frame": True,
                "group_frame": True,
                "nntpdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "nntpid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_nntpdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "nntpid": origin_nntpid,
                "nntpdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "article_frame": True,
                "group_frame": True,
                "nntpdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "nntpid_bound": True,
            }
        except (OSError, NntpActuationError) as error:
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
        live = independent_nntpdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "nntpid": int(live.get("nntpid") or EMPTY_NNTPID),
            "nntpdigest": int(live.get("nntpdigest") or EMPTY_NNTPDIGEST),
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


def call_nntp_tool(session: NntpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one nntp tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_article = True if arguments.get("article") is None else bool(arguments.get("article"))
    do_group = True if arguments.get("group") is None else bool(arguments.get("group"))
    do_nntpdigest = True if arguments.get("nntpdigest") is None else bool(arguments.get("nntpdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_nntpid = True if arguments.get("use_nntpid") is None else bool(arguments.get("use_nntpid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_article=do_article,
            do_group=do_group,
            do_nntpdigest=do_nntpdigest,
            replay=replay,
            use_nntpid=use_nntpid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise NntpActuationError(f"unsupported nntp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_nntpdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage nntpdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "nntpid": EMPTY_NNTPID,
        "nntpdigest": EMPTY_NNTPDIGEST,
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
            "article_frame",
            "group_frame",
            "nntpdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "nntpid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    nntpid = int(payload.get("nntpid") or EMPTY_NNTPID)
    nntpdigest = int(payload.get("nntpdigest") or EMPTY_NNTPDIGEST)
    dual = port > 0 and bool(nntpid) and bool(nntpdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "nntpid": nntpid,
        "nntpdigest": nntpdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "article_frame": payload.get("article_frame") is True,
        "group_frame": payload.get("group_frame") is True,
        "nntpdigest_locate": payload.get("nntpdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "nntpid_bound": payload.get("nntpid_bound") is True,
    }


def run_nntp_workflow(
    *,
    with_nntpid: bool = True,
    skip_bind: bool = False,
    do_article: bool = True,
    do_group: bool = True,
    do_nntpdigest: bool = True,
    replay: bool = True,
    use_nntpid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 977 ARTICLE/GROUP nntpid cycle workflow."""

    descriptor = nntp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, NNTP_TOOL_PROVIDER),
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
        raise NntpActuationError(f"nntp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="nntp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = NntpSession(out, nntpid_gate=DEFAULT_NNTPID if with_nntpid else EMPTY_NNTPID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "article": do_article,
            "group": do_group,
            "nntpdigest": do_nntpdigest,
            "replay": replay,
            "use_nntpid": use_nntpid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_nntp_tool(session, arguments))
            except NntpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_nntpdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_nntpid
        and not skip_bind
        and do_article
        and do_group
        and do_nntpdigest
        and replay
        and use_nntpid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "nntp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_nntpid": with_nntpid,
        "skip_bind": skip_bind,
        "article_frame": do_article,
        "group_frame": do_group,
        "nntpdigest": do_nntpdigest,
        "replay": replay,
        "use_nntpid": use_nntpid,
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
        "nntpid_value": int(publish_result.get("nntpid") or independent.get("nntpid") or EMPTY_NNTPID),
        "nntpdigest_value": int(publish_result.get("nntpdigest") or independent.get("nntpdigest") or EMPTY_NNTPDIGEST),
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
        "nntpid": int(trace_body["nntpid_value"] or EMPTY_NNTPID),
        "nntpdigest": int(trace_body["nntpdigest_value"] or EMPTY_NNTPDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_nntpid": with_nntpid,
        "skip_bind": skip_bind,
        "article_cycle": do_article,
        "group_cycle": do_group,
        "nntpdigest_cycle": do_nntpdigest,
        "replay": replay,
        "use_nntpid": use_nntpid,
    }


def verify_nntp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_nntpdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    nntpid = int(trace.get("nntpid_value") or independent.get("nntpid") or EMPTY_NNTPID)
    nntpdigest = int(trace.get("nntpdigest_value") or independent.get("nntpdigest") or EMPTY_NNTPDIGEST)
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
        "article_frame": independent.get("article_frame") is True,
        "group_frame": independent.get("group_frame") is True,
        "nntpdigest_locate": independent.get("nntpdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "nntpid_bound": independent.get("nntpid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "nntpdigest_recorded": (
            port > 0
            and nntpid == DEFAULT_NNTPID
            and nntpdigest == DEFAULT_NNTPDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def nntp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.nntp_actuation import "
        "builtin_nntp_actuation_proof; r=builtin_nntp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='nntp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_nntp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=NNTP_ACTUATION_ID,
        name="First-class RFC 977 Network News Transfer Protocol ARTICLE/GROUP actuation",
        description=(
            "Missions that require an nntp tool can opt the nntp provider in, "
            "bind a loopback RFC 977 Network News Transfer Protocol endpoint, complete an ARTICLE "
            "with a non-empty nntpid, lockstep a GROUP that carries the "
            "stored nntpdigest, independently poll the stored nntpdigest "
            "on a later socket, and seal a digest-chained nntpdigest. Default "
            "routing stays fail-closed; a missing nntpid keeps the hole "
            "falsifiable, and skip-ARTICLE/GROUP/NNTPDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.nntp_actuation:builtin_nntp_actuation_proof",
        proof_command=nntp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.lpd-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/nntp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/lpd_actuation.py",
            "src/blackhole_agent/telnet_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required nntp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 977 daemon, speaks an "
            "ARTICLE then GROUP over Network News Transfer Protocol with a non-empty nntpid and "
            "nntpdigest, independently polls the stored nntpdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 1179 Line Printer Daemon Protocol lockstep is proved. "
            "Missing nntpids, skip-ARTICLE, skip-GROUP, skip-nntpdigest, skip-REPLAY, "
            "and an ARTICLE aimed without an nntpid stay fail-closed. "
            "Later genesis can take RFC 854 Telnet Protocol Specification DO/WILL as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("nntp", "rfc977", "http", "nntpid", "nntpdigest", "article", "group", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T033647Z-6717fe30",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_nntp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 977 article/group lockstep actuation seals a nntpdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.telnet_actuation import (
        TELNET_ACTUATION_GOAL,
        TELNET_ACTUATION_ID,
    )
    from blackhole_agent.lpd_actuation import (
        LPD_ACTUATION_GOAL,
        LPD_ACTUATION_ID,
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
    checks["denylists_self"] = NNTP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(NNTP_ACTUATION_GOAL) == (
        NNTP_ACTUATION_ID,
    )
    checks["leftover_text_binds_nntp"] = leftover_marker_ids(NNTP_LEFTOVER) == (
        NNTP_ACTUATION_ID,
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
        (TELNET_ACTUATION_GOAL, TELNET_ACTUATION_ID, "telnet"),
        (LPD_ACTUATION_GOAL, LPD_ACTUATION_ID, "lpd"),
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
        checks[f"{name}_goal_is_not_nntp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"nntp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            NNTP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = NNTP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_nntp(DEFAULT_ARTICLE)
    rebuilt = serialize_nntp(parse_nntp(advertised))
    preloaded = parse_nntp(RFC_NNTP_GROUP)
    header = encode_nntp_header(DEFAULT_ARTICLE)
    parsed_header = parse_nntp_header(header)
    asked = parse_http_request(article_request(SENTINEL, DEFAULT_NNTPID))
    preload_req = parse_http_request(group_request(SENTINEL, DEFAULT_NNTPID, DEFAULT_NNTPDIGEST))
    got = parse_http_response(article_response(SENTINEL, DEFAULT_NNTPID, DEFAULT_NNTPDIGEST))
    preload_reply = parse_http_response(
        group_response(SENTINEL, DEFAULT_NNTPID, DEFAULT_NNTPDIGEST)
    )
    checks["nntp_roundtrip"] = (
        parse_nntp(advertised) == DEFAULT_ARTICLE
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_ARTICLE_FIELD
        and is_token("ARTICLE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_ARTICLE_FIELD
        and parsed_header["policy"] == DEFAULT_ARTICLE
        and parsed_header["header"] == ARTICLE_HEADER
        and parsed_header["article"] is True
        and parsed_header["group"] is False
        and preloaded == GROUP_POLICY
        and ascii_serialize_nntp_directive() == RFC_ARTICLE_DIRECTIVE
        and nntp_directive_pair() == ("article", "message")
        and RFC_ARTICLE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_nntp(GROUP_POLICY) == RFC_NNTP_GROUP
        and DEFAULT_NNTPDIGEST == request_nntpdigest(DEFAULT_NNTPID, SENTINEL)
        and "nntpdigest=" in canonical_group(SENTINEL, DEFAULT_NNTPID, DEFAULT_NNTPDIGEST)
        and canonical_article(SENTINEL, DEFAULT_NNTPID).startswith("ARTICLE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "ARTICLE"
        and asked["nntp_kind"] == "article"
        and asked["nntpid"] == DEFAULT_NNTPID
        and preload_req["nntp_kind"] == "group"
        and preload_req["nntpdigest"] == DEFAULT_NNTPDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["nntp_kind"] == "article"
        and preload_reply["nntp_kind"] == "group"
        and got["policy"] == DEFAULT_ARTICLE
        and preload_reply["policy"] == GROUP_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["nntpdigest"] == DEFAULT_NNTPDIGEST
        and preload_reply["nntpdigest"] == DEFAULT_NNTPDIGEST
        and nntp_matches(serialize_nntp(got["policy"]), advertised)
    )

    checks["catalog_names_nntp"] = (
        len(catalog) > 110
        and catalog[110]["id"] == NNTP_ACTUATION_ID
        and catalog[109]["id"] == LPD_ACTUATION_ID
        and catalog[110]["source"] == "genesis_bind_nntp"
    )
    checks["catalog_names_telnet"] = (
        len(catalog) > 111
        and catalog[111]["id"] == TELNET_ACTUATION_ID
        and catalog[111]["source"] == "genesis_bind_telnet"
    )
    family = capability_family(NNTP_ACTUATION_GOAL)
    checks["family_is_nntp"] = "nntp" in family
    checks["family_is_nntp_surface"] = "nntp" in family
    checks["family_is_nntpid"] = "nntpid" in family
    checks["family_is_rfc977"] = "rfc977" in family
    checks["family_is_nntpdigest"] = "nntpdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_telnet"] = (
        "telnet" not in family.split("/")
        and "rfc854" not in family
        and "telnetid" not in family
        and "telnetdigest" not in family
    )
    checks["family_is_not_lpd"] = (
        "lpd" not in family.split("/")
        and "rfc1179" not in family
        and "lpdid" not in family
        and "lpddigest" not in family
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
    packed = encode_article(identity=SENTINEL, nntpid=DEFAULT_NNTPID, nntpdigest=DEFAULT_NNTPDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_article"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_nntpid"] is True
        and parsed["nntpid"] == DEFAULT_NNTPID
        and parsed["nntpdigest"] == DEFAULT_NNTPDIGEST
        and parsed["is_group"] is False
        and parsed["is_group"] is False
        and parsed["type"] == FRAME_ARTICLE
        and parsed["first_byte"] == NNTP_FIRST
    )
    shook = encode_group(
        identity=SENTINEL,
        nntpid=DEFAULT_NNTPID,
        nntpdigest=DEFAULT_NNTPDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_group"] is True
        and answer_parsed["is_group"] is True
        and answer_parsed["is_article"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["nntpid"] == DEFAULT_NNTPID
        and answer_parsed["nntpdigest"] == DEFAULT_NNTPDIGEST
        and answer_parsed["has_nntpdigest"] is True
        and answer_parsed["type"] == FRAME_GROUP
        and answer_parsed["first_byte"] == NNTP_FIRST
    )
    bare = encode_article(identity=SENTINEL, nntpid=DEFAULT_NNTPID, include_nntpid=False)
    checks["missing_nntpid_is_unauthed"] = parse_message(bare)["has_nntpid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(NNTP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_nntp = ToolDescriptor(name="remote_nntp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_nntp)
    checks["naive_mcp_nntp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = nntp_tool_descriptor()
    default_nntp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, NNTP_TOOL_PROVIDER),
    )
    checks["default_nntp_provider_is_unsupported"] = (
        default_nntp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{NNTP_TOOL_PROVIDER}" in default_nntp.reasons
    )
    checks["opted_in_nntp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_nntp],
        required_tool_names=("local_memory", "nntp"),
    )
    checks["naive_preflight_missing_nntp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["nntp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "nntp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, NNTP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "nntp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="nntp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_nntp_workflow(with_nntpid=False, output_dir=root / "missing")
        skip_bind = run_nntp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_article = run_nntp_workflow(do_article=False, output_dir=root / "skip-article")
        skip_group = run_nntp_workflow(do_group=False, output_dir=root / "skip-group")
        skip_nntpdigest = run_nntp_workflow(do_nntpdigest=False, output_dir=root / "skip-nntpdigest")
        skip_replay = run_nntp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_nntpid = run_nntp_workflow(use_nntpid=False, output_dir=root / "skip-nntpid")
        live = run_nntp_workflow(output_dir=root / "live")
        verify = verify_nntp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_nntp_trace(clone)
        checks["naive_without_nntpid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_nntpid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_article_stays_empty"] = (
            skip_article["ok"] is False
            and skip_article["error"] == "article_required"
            and skip_article["final_status"] == 409
            and skip_article["payload_exists"] is False
        )
        checks["skip_group_stays_empty"] = (
            skip_group["ok"] is False
            and skip_group["error"] == "group_required"
            and skip_group["final_status"] == 409
            and skip_group["payload_exists"] is False
        )
        checks["skip_nntpdigest_stays_empty"] = (
            skip_nntpdigest["ok"] is False
            and skip_nntpdigest["error"] == "nntpdigest_required"
            and skip_nntpdigest["final_status"] == 409
            and skip_nntpdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_nntpid_stays_empty"] = (
            skip_nntpid["ok"] is False
            and skip_nntpid["error"] == "nntpid_required"
            and skip_nntpid["final_status"] == 409
            and skip_nntpid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_nntpdigest"] = (
            int(live.get("nntpid") or 0) == DEFAULT_NNTPID
            and int(live.get("nntpdigest") or 0) == DEFAULT_NNTPDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_nntpid_encode_group_nntpdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_article["ok"] is False
            and skip_group["ok"] is False
            and skip_nntpdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_nntpid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="nntp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != NNTP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, NNTP_ACTUATION_GOAL, NNTP_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_nntp"] = (
        not gate.accepted
        and live_goal != NNTP_ACTUATION_GOAL
        and NNTP_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_nntp"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="nntp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(NNTP_LEFTOVER, root)
        register_catalog_proved(root, NNTP_ACTUATION_ID)
        reason = leftover_satisfied_by(NNTP_LEFTOVER, root)
        after = leftover_is_open(NNTP_LEFTOVER, root)
    checks["nntp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_nntp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{NNTP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_nntp_actuation_capability()
    return {
        "ok": ok,
        "action": "nntp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": NNTP_ACTUATION_GOAL,
        "done_when": NNTP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
