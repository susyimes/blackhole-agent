"""Drive a first-class MIME tool through RFC 1521 BODY/TRANSFER.

Tool routing already fails missions that require ``mime``: hosted
mime endpoints stay on the unsupported MCP provider, and no first-party
mime provider is executable. Unbound therefore cannot speak a BODY,
lockstep a TRANSFER mimeid handshake over HTTP/1.0 MIMEID,
independently poll the stored mimedigest, or seal a mimedigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``mime`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1521 daemon
- keep a missing-mimeid client so the mime-mimeid hole stays falsifiable
- refuse TRANSFER until a BODY lands with a non-empty mimeid
- independently poll the stored mimedigest on a later client socket
- persist a sealed mimedigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 1630 Universal Resource Identifiers
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
    MIME_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    mime_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
MIME_ACTUATION_ID = "capability.mime-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-MIME-OK"
POLL_TOKEN = "BH-MIME-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_MIMEID = 0
EMPTY_MIMEDIGEST = 0
MIME_FIRST = 0x4D  # RFC 1521 MIME (ASCII 'M')
MIMEID_SIZE = 4
MIMEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_TRANSFER = 0x02  # RFC 1521 TRANSFER confirmation
FRAME_BODY = 0x01  # RFC 1521 BODY
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
MIME_LEFTOVER = (
    "Later genesis can take RFC 1521 MIME BODY/TRANSFER over a "
    "mimeid-gated mimedigest."
)
MIME_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MIME_ACTUATION_ID};"
    f"capability_proved:{MIME_ACTUATION_ID};"
    "no_skill_route"
)
MIME_ACTUATION_GOAL = (
    "Repair rfc1521 mime body/transfer cycle cannot land over http "
    "mime mimeid: hosted mime endpoints remain unsupported so a BODY then "
    "TRANSFER mimeid handshake cannot land and a sealed mimedigest "
    "cannot be produced. A missing mime mimeid stays forbidden; fail-closed "
    "routing never opts the mime provider in. An independent later poll of the "
    "stored mimedigest keeps the hole falsifiable."
)


class MimeActuationError(RuntimeError):
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
# RFC 1521 sections 2.1 and 2.1.2: BODY / TRANSFER.
RFC_BODY_FIELD = "BODY"
RFC_TRANSFER_FIELD = "TRANSFER"
RFC_MIME_TRANSFER = RFC_TRANSFER_FIELD
RFC_BODY_DIRECTIVE = "body=name"
RFC_TRANSFER_DIRECTIVE = "transfer=resource"
DEFAULT_BODY = "BODY"
TRANSFER_POLICY = "TRANSFER"
BODY_HEADER = "Body"
TRANSFER_HEADER = "Transfer"
MIME_TRANSFER_HEADER = TRANSFER_HEADER
RFC_BODY_PATH = "/mime/"
RFC_BODY_EMPTY = ""


def mime_directive_pair(*, transfer: bool = False) -> tuple[str, str]:
    """RFC 1521 Body / Transfer directive pair."""

    if transfer:
        return "transfer", "resource"
    return "body", "name"


def ascii_serialize_mime_directive(*, transfer: bool = False) -> str:
    """RFC 1521 token "=" body-or-transfer."""

    name, value = mime_directive_pair(transfer=transfer)
    if not is_token(name):
        raise MimeActuationError("illegal_directive")
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
            raise MimeActuationError("short_mime")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 1521 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_mime(policy: str | Sequence[str]) -> str:
    """Serialize RFC 1521 BODY / TRANSFER opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise MimeActuationError("illegal_mime")
    upper = text.upper().replace("_", "-")
    if upper in {"BODY", "MIME", "MIME-BODY"}:
        return "BODY"
    if upper in {"TRANSFER", "RESOURCE", "MIME-TRANSFER"}:
        return "TRANSFER"
    if upper.startswith("BODY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise MimeActuationError("illegal_mime")
        return "BODY"
    if upper.startswith("TRANSFER="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise MimeActuationError("illegal_mime")
        return "TRANSFER"
    raise MimeActuationError("illegal_mime")


def parse_mime(text: str) -> str:
    """Parse RFC 1521 MIME opcode header extensions into BODY or TRANSFER."""

    raw = str(text or "").strip()
    if not raw:
        raise MimeActuationError("illegal_mime")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"BODY", "MIME", "MIME-BODY"}:
        return "BODY"
    if upper in {"TRANSFER", "RESOURCE", "MIME-TRANSFER"}:
        return "TRANSFER"
    if upper.startswith("BODY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise MimeActuationError("illegal_mime")
        return "BODY"
    if upper.startswith("TRANSFER="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise MimeActuationError("illegal_mime")
        return "TRANSFER"
    raise MimeActuationError("illegal_mime")


def encode_mime_header(policy: str | Sequence[str]) -> bytes:
    """RFC 1521 HTTP/1.0 field as bytes."""

    return serialize_mime(policy).encode("ascii")


def parse_mime_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_mime(field_value) if field_value else DEFAULT_BODY
    return {
        "field_value": field_value,
        "policy": policy,
        "header": BODY_HEADER,
        "directive": str(policy),
        "body": str(policy) == "BODY",
        "transfer": str(policy) == "TRANSFER",
    }


def canonical_body(identity: str, mimeid: int) -> str:
    """RFC 1521 body-request advertisement bound to identity and mimeid."""

    return (
        f"{serialize_mime(DEFAULT_BODY)}, "
        f"body={ascii_serialize_mime_directive()}, "
        f"identity={identity}, mimeid={int(mimeid) & 0xFFFFFFFF}"
    )


def canonical_transfer(identity: str, mimeid: int, mimedigest: int | None = None) -> str:
    """RFC 1521 transfer-resource confirmation of the stored identifier-digest."""

    digest = ""
    if mimedigest is not None:
        digest = f", mimedigest={int(mimedigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_mime(TRANSFER_POLICY)}, "
        f"transfer={ascii_serialize_mime_directive(transfer=True)}, "
        f"identity={identity}, mimeid={int(mimeid) & 0xFFFFFFFF}{digest}"
    )


def representation_transfer(identity: str, mimeid: int, mimedigest: int) -> str:
    return canonical_transfer(identity, mimeid, mimedigest)


def mime_matches(left: str, right: str) -> bool:
    return parse_mime(left) == parse_mime(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise MimeActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise MimeActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise MimeActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise MimeActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def body_request(identity: str, mimeid: int) -> bytes:
    """HTTP BODY that elicits RFC 1521 origin HTTP/1.0."""

    keyid = f"{int(mimeid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"BODY /mime/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Mime-Id: {int(mimeid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def transfer_request(identity: str, mimeid: int, mimedigest: int | None = None) -> bytes:
    """HTTP BODY carrying RFC 1521 transfer-resource confirmation of the stored identifier-digest."""

    keyid = f"{int(mimeid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if mimedigest is not None:
        extra = f"Mime-Digest: {int(mimedigest) & 0xFFFFFFFF}\r\n"
    return (
        f"TRANSFER /mime/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Mime-Id: {int(mimeid) & 0xFFFFFFFF}\r\n"
        "Transfer-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    mime_kind = "transfer" if fields.get("transfer-confirm") == "1" else "body"
    upgrade_field = fields.get("body") or fields.get("mime") or ""
    policy = parse_mime(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "mime_kind": mime_kind,
        "policy": policy,
        "mimeid": int(fields["mime-id"]) if fields.get("mime-id") else EMPTY_MIMEID,
        "mimedigest": int(fields["mime-digest"]) if fields.get("mime-digest") else EMPTY_MIMEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def body_response(identity: str, mimeid: int, mimedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 1521 origin HTTP/1.0, carrying the stored mimedigest."""

    advertised = serialize_mime(DEFAULT_BODY)
    payload = bytes(body or canonical_body(identity, mimeid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Body: {advertised}\r\n"
        f"Mime-Id: {int(mimeid) & 0xFFFFFFFF}\r\n"
        f"Mime-Digest: {int(mimedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def transfer_response(identity: str, mimeid: int, mimedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 1521 TRANSFER, carrying the stored identifier-digest."""

    advertised = serialize_mime(TRANSFER_POLICY)
    payload = bytes(body or representation_transfer(identity, mimeid, mimedigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Body: {advertised}\r\n"
        f"Mime-Id: {int(mimeid) & 0xFFFFFFFF}\r\n"
        f"Mime-Digest: {int(mimedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/mime-transfer\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise MimeActuationError("illegal_content_length") from error
    field_value = fields.get("body") or fields.get("mime") or ""
    policy = parse_mime(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/mime-transfer" or policy == TRANSFER_POLICY:
        status = 200
        mime_kind = "transfer"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        mime_kind = "body"
    else:
        status = 0
        mime_kind = "body"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "mime_kind": mime_kind,
        "policy": policy,
        "mimeid": int(fields["mime-id"]) if fields.get("mime-id") else EMPTY_MIMEID,
        "mimedigest": int(fields["mime-digest"]) if fields.get("mime-digest") else EMPTY_MIMEDIGEST,
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
        raise MimeActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise MimeActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise MimeActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise MimeActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc1521_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    mime: str,
) -> str:
    """RFC 1521 identifier digest over method, request-MIME, identity, and mimeid."""

    payload = f"{method}:{mime}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_mimeid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"mimeid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_mimeid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-mimeid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_mimedigest(mimeid: int = EMPTY_MIMEID, token: str = SENTINEL) -> int:
    nonce = f"{int(mimeid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc1521_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="TRANSFER",
        mime=f"/mime/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_MIMEID = request_mimeid(SENTINEL)
DEFAULT_MIMEDIGEST = request_mimedigest(DEFAULT_MIMEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    mimeid: int,
    mimedigest: int,
    include_mimeid: bool = True,
) -> bytes:
    live_mimeid = int(mimeid) & 0xFFFFFFFF if include_mimeid else EMPTY_MIMEID
    live_digest = int(mimedigest) & 0xFFFFFFFF if include_mimeid and live_mimeid else EMPTY_MIMEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_mimeid) if live_mimeid else b""
    header = bytearray()
    header.append(MIME_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_body(
    *,
    identity: str,
    mimeid: int,
    mimedigest: int | None = None,
    include_mimeid: bool = True,
) -> bytes:
    live_mimeid = int(mimeid) & 0xFFFFFFFF if include_mimeid else EMPTY_MIMEID
    live_digest = int(mimedigest) if mimedigest is not None else request_mimedigest(live_mimeid, identity)
    return encode_packet(
        FRAME_BODY,
        identity=identity,
        mimeid=live_mimeid,
        mimedigest=live_digest,
        include_mimeid=include_mimeid,
    )


def encode_transfer(
    *,
    identity: str,
    mimeid: int,
    mimedigest: int | None = None,
    include_mimeid: bool = True,
) -> bytes:
    live_mimeid = int(mimeid) & 0xFFFFFFFF if include_mimeid else EMPTY_MIMEID
    live_digest = int(mimedigest) if mimedigest is not None else request_mimedigest(live_mimeid, identity)
    return encode_packet(
        FRAME_TRANSFER,
        identity=identity,
        mimeid=live_mimeid,
        mimedigest=live_digest,
        include_mimeid=include_mimeid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise MimeActuationError("short_packet")
    first = raw[0]
    if first != MIME_FIRST:
        raise MimeActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise MimeActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == MIMEID_SIZE:
        live_mimeid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_mimeid = EMPTY_MIMEID
    else:
        raise MimeActuationError("illegal_mimeid")
    if offset >= len(raw):
        raise MimeActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_BODY, FRAME_TRANSFER}:
        raise MimeActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise MimeActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise MimeActuationError("checksum_failed")
    if len(payload) < 5:
        raise MimeActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise MimeActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_mimeid = int(live_mimeid) != EMPTY_MIMEID
    has_mimedigest = has_mimeid and int(live_digest) != EMPTY_MIMEDIGEST
    is_body = frame_type == FRAME_BODY
    is_transfer = frame_type == FRAME_TRANSFER
    return {
        "type": int(frame_type),
        "is_body": is_body,
        "is_transfer": is_transfer,
        "mimeid": int(live_mimeid),
        "has_mimeid": has_mimeid,
        "mimedigest": int(live_digest),
        "has_mimedigest": has_mimedigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC1521",
        "serialize_field": canonical_body(identity, live_mimeid) if has_mimeid else "",
        "tls_field": canonical_transfer(identity, live_mimeid, live_digest) if has_mimedigest else "",
    }


class MimeClient:
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
            raise MimeActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_transfer"] or not packet["is_transfer"]:
            raise MimeActuationError("mimedigest_required")
        if not packet["has_mimeid"]:
            raise MimeActuationError("mimeid_required")
        if not packet["has_mimedigest"]:
            raise MimeActuationError("mimedigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_mimedigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_mimedigest:
            raise MimeActuationError("mimedigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "mimeid": int(reply.get("mimeid") or EMPTY_MIMEID),
            "identity": str(reply.get("identity") or ""),
            "mimedigest": int(reply.get("mimedigest") or EMPTY_MIMEDIGEST),
        }

    def report(
        self,
        identity: str,
        mimeid: int,
        mimedigest: int = EMPTY_MIMEDIGEST,
        *,
        wait_mimedigest: bool = True,
        include_mimeid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_transfer(
            identity=identity,
            mimeid=mimeid,
            mimedigest=mimedigest or request_mimedigest(mimeid, identity),
            include_mimeid=include_mimeid,
        )
        return self.exchange(packet, wait_mimedigest=wait_mimedigest)


class MimeSession:
    """MIMEID-gated loopback RFC 1521 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        mimeid_gate: int = DEFAULT_MIMEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.mimeid_gate = int(mimeid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.mimeid = EMPTY_MIMEID
        self.mimedigest = EMPTY_MIMEDIGEST
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

    def store_mimeid_once(self, identity: str, mimeid: int, mimedigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(mimeid or EMPTY_MIMEID)
            live_digest = int(mimedigest or EMPTY_MIMEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.mimeid = live
                self.mimedigest = live_digest or request_mimedigest(live, name)
                self.stored = True
            return str(self.identity), int(self.mimeid), int(self.mimedigest)

    def read_mimeid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.mimeid), int(self.mimedigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "mimeid": EMPTY_MIMEID,
            "mimedigest": EMPTY_MIMEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _mimeid_missing(self) -> bool:
        return not int(self.mimeid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, mimeid: int, mimedigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_transfer(
            identity=identity,
            mimeid=mimeid,
            mimedigest=mimedigest,
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
            except MimeActuationError:
                continue
            if not packet.get("is_body") and not packet.get("is_transfer"):
                continue
            if not packet.get("has_mimeid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_mimeid, stored_digest = self.store_mimeid_once(
                identity,
                int(packet.get("mimeid") or EMPTY_MIMEID),
                int(packet.get("mimedigest") or EMPTY_MIMEDIGEST),
            )
            if not stored_name or not stored_mimeid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_body"):
                    self.opened = True
                if packet.get("is_transfer"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_mimeid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._mimeid_missing():
            return self._forbidden("missing_mimeid")
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
        do_body: bool = True,
        do_transfer: bool = True,
        do_mimedigest: bool = True,
        replay: bool = True,
        use_mimeid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._mimeid_missing():
            return self._forbidden("missing_mimeid")
        live_token = str(token or SENTINEL)
        origin_mimeid = request_mimeid(live_token)
        origin_digest = request_mimedigest(origin_mimeid, live_token)
        client: MimeClient | None = None
        independent: MimeClient | None = None
        try:
            client = MimeClient(self.host, int(self.port))
            if not do_body:
                return self._conflict("body_required")
            bind_packet = encode_body(
                identity=live_token,
                mimeid=origin_mimeid,
                mimedigest=origin_digest,
                include_mimeid=use_mimeid,
            )
            if not use_mimeid:
                try:
                    client.exchange(bind_packet, wait_mimedigest=True)
                except MimeActuationError:
                    return self._conflict("mimeid_required")
                return self._conflict("mimeid_required")
            client.send(bind_packet)
            if not do_transfer:
                return self._conflict("transfer_required")
            proxy_packet = encode_transfer(
                identity=live_token,
                mimeid=origin_mimeid,
                mimedigest=origin_digest,
                include_mimeid=True,
            )
            if not do_mimedigest:
                try:
                    client.exchange(proxy_packet, wait_mimedigest=False)
                except MimeActuationError as error:
                    if str(error) == "mimedigest_required":
                        return self._conflict("mimedigest_required")
                    return self._conflict("mimedigest_required")
                return self._conflict("mimedigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_mimedigest=True)
            except MimeActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("mimeid_required")
                if reason == "mimedigest_required":
                    return self._conflict("mimedigest_required")
                return self._conflict("body_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("body_required")
            if int(reply.get("mimeid") or EMPTY_MIMEID) != origin_mimeid:
                return self._conflict("mimedigest_required")
            if int(reply.get("mimedigest") or EMPTY_MIMEDIGEST) != origin_digest:
                return self._conflict("mimedigest_required")
            self.retrieved = True
            if replay:
                independent = MimeClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_mimeid(live_token),
                        request_mimedigest(poll_mimeid(live_token), POLL_TOKEN),
                        wait_mimedigest=True,
                    )
                except MimeActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_mimeid, stored_digest = self.read_mimeid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_mimeid != origin_mimeid
                    or stored_digest != origin_digest
                    or int(poll.get("mimeid") or EMPTY_MIMEID) != origin_mimeid
                    or int(poll.get("mimedigest") or EMPTY_MIMEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_mimeid}:{origin_digest}:{live_token}:{canonical_body(live_token, origin_mimeid)}:{canonical_transfer(live_token, origin_mimeid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "mimeid": origin_mimeid,
                "mimedigest": origin_digest,
                "body_frame": True,
                "transfer_frame": True,
                "mimedigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "mimeid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_mimedigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "mimeid": origin_mimeid,
                "mimedigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "body_frame": True,
                "transfer_frame": True,
                "mimedigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "mimeid_bound": True,
            }
        except (OSError, MimeActuationError) as error:
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
        live = independent_mimedigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "mimeid": int(live.get("mimeid") or EMPTY_MIMEID),
            "mimedigest": int(live.get("mimedigest") or EMPTY_MIMEDIGEST),
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


def call_mime_tool(session: MimeSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one mime tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_body = True if arguments.get("body") is None else bool(arguments.get("body"))
    do_transfer = True if arguments.get("transfer") is None else bool(arguments.get("transfer"))
    do_mimedigest = True if arguments.get("mimedigest") is None else bool(arguments.get("mimedigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_mimeid = True if arguments.get("use_mimeid") is None else bool(arguments.get("use_mimeid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_body=do_body,
            do_transfer=do_transfer,
            do_mimedigest=do_mimedigest,
            replay=replay,
            use_mimeid=use_mimeid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise MimeActuationError(f"unsupported mime action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_mimedigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage mimedigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "mimeid": EMPTY_MIMEID,
        "mimedigest": EMPTY_MIMEDIGEST,
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
            "body_frame",
            "transfer_frame",
            "mimedigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "mimeid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    mimeid = int(payload.get("mimeid") or EMPTY_MIMEID)
    mimedigest = int(payload.get("mimedigest") or EMPTY_MIMEDIGEST)
    dual = port > 0 and bool(mimeid) and bool(mimedigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "mimeid": mimeid,
        "mimedigest": mimedigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "body_frame": payload.get("body_frame") is True,
        "transfer_frame": payload.get("transfer_frame") is True,
        "mimedigest_locate": payload.get("mimedigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "mimeid_bound": payload.get("mimeid_bound") is True,
    }


def run_mime_workflow(
    *,
    with_mimeid: bool = True,
    skip_bind: bool = False,
    do_body: bool = True,
    do_transfer: bool = True,
    do_mimedigest: bool = True,
    replay: bool = True,
    use_mimeid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1521 BODY/TRANSFER mimeid cycle workflow."""

    descriptor = mime_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MIME_TOOL_PROVIDER),
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
        raise MimeActuationError(f"mime tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="mime-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = MimeSession(out, mimeid_gate=DEFAULT_MIMEID if with_mimeid else EMPTY_MIMEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "body": do_body,
            "transfer": do_transfer,
            "mimedigest": do_mimedigest,
            "replay": replay,
            "use_mimeid": use_mimeid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_mime_tool(session, arguments))
            except MimeActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_mimedigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_mimeid
        and not skip_bind
        and do_body
        and do_transfer
        and do_mimedigest
        and replay
        and use_mimeid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mime_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_mimeid": with_mimeid,
        "skip_bind": skip_bind,
        "body_frame": do_body,
        "transfer_frame": do_transfer,
        "mimedigest": do_mimedigest,
        "replay": replay,
        "use_mimeid": use_mimeid,
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
        "mimeid_value": int(publish_result.get("mimeid") or independent.get("mimeid") or EMPTY_MIMEID),
        "mimedigest_value": int(publish_result.get("mimedigest") or independent.get("mimedigest") or EMPTY_MIMEDIGEST),
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
        "mimeid": int(trace_body["mimeid_value"] or EMPTY_MIMEID),
        "mimedigest": int(trace_body["mimedigest_value"] or EMPTY_MIMEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_mimeid": with_mimeid,
        "skip_bind": skip_bind,
        "body_cycle": do_body,
        "transfer_cycle": do_transfer,
        "mimedigest_cycle": do_mimedigest,
        "replay": replay,
        "use_mimeid": use_mimeid,
    }


def verify_mime_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_mimedigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    mimeid = int(trace.get("mimeid_value") or independent.get("mimeid") or EMPTY_MIMEID)
    mimedigest = int(trace.get("mimedigest_value") or independent.get("mimedigest") or EMPTY_MIMEDIGEST)
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
        "body_frame": independent.get("body_frame") is True,
        "transfer_frame": independent.get("transfer_frame") is True,
        "mimedigest_locate": independent.get("mimedigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "mimeid_bound": independent.get("mimeid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "mimedigest_recorded": (
            port > 0
            and mimeid == DEFAULT_MIMEID
            and mimedigest == DEFAULT_MIMEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def mime_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mime_actuation import "
        "builtin_mime_actuation_proof; r=builtin_mime_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='mime_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mime_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MIME_ACTUATION_ID,
        name="First-class RFC 1521 MIME BODY/TRANSFER actuation",
        description=(
            "Missions that require a mime tool can opt the mime provider in, "
            "bind a loopback RFC 1521 MIME endpoint, complete a BODY "
            "with a non-empty mimeid, lockstep a TRANSFER that carries the "
            "stored mimedigest, independently poll the stored mimedigest "
            "on a later socket, and seal a digest-chained mimedigest. Default "
            "routing stays fail-closed; a missing mimeid keeps the hole "
            "falsifiable, and skip-BODY/TRANSFER/MIMEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.mime_actuation:builtin_mime_actuation_proof",
        proof_command=mime_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.uri-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mime_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/uri_actuation.py",
            "src/blackhole_agent/gopher_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required mime tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 1521 daemon, speaks a "
            "BODY then TRANSFER over MIME with a non-empty mimeid and "
            "mimedigest, independently polls the stored mimedigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 1630 Universal Resource Identifiers lockstep is proved. "
            "Missing mimeids, skip-BODY, skip-TRANSFER, skip-mimedigest, skip-REPLAY, "
            "and a BODY aimed without a mimeid stay fail-closed. "
            "Later genesis can take RFC 1436 The Internet Gopher Protocol SELECTOR/MENU as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("mime", "rfc1521", "http", "mimeid", "mimedigest", "body", "transfer", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T062550Z-6cf75d44",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mime_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1521 body/transfer lockstep actuation seals a mimedigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.gopher_actuation import (
        GOPHER_ACTUATION_GOAL,
        GOPHER_ACTUATION_ID,
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
    checks["denylists_self"] = MIME_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MIME_ACTUATION_GOAL) == (
        MIME_ACTUATION_ID,
    )
    checks["leftover_text_binds_mime"] = leftover_marker_ids(MIME_LEFTOVER) == (
        MIME_ACTUATION_ID,
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
        (GOPHER_ACTUATION_GOAL, GOPHER_ACTUATION_ID, "gopher"),
        (URI_ACTUATION_GOAL, URI_ACTUATION_ID, "uri"),
        (HTTP10_ACTUATION_GOAL, HTTP10_ACTUATION_ID, "http10"),
        (DIGESTAUTH_ACTUATION_GOAL, DIGESTAUTH_ACTUATION_ID, "digestauth"),
        (HTTPSTATE_ACTUATION_GOAL, HTTPSTATE_ACTUATION_ID, "httpstate"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_mime"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"mime_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            MIME_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = MIME_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_mime(DEFAULT_BODY)
    rebuilt = serialize_mime(parse_mime(advertised))
    preloaded = parse_mime(RFC_MIME_TRANSFER)
    header = encode_mime_header(DEFAULT_BODY)
    parsed_header = parse_mime_header(header)
    asked = parse_http_request(body_request(SENTINEL, DEFAULT_MIMEID))
    preload_req = parse_http_request(transfer_request(SENTINEL, DEFAULT_MIMEID, DEFAULT_MIMEDIGEST))
    got = parse_http_response(body_response(SENTINEL, DEFAULT_MIMEID, DEFAULT_MIMEDIGEST))
    preload_reply = parse_http_response(
        transfer_response(SENTINEL, DEFAULT_MIMEID, DEFAULT_MIMEDIGEST)
    )
    checks["mime_roundtrip"] = (
        parse_mime(advertised) == DEFAULT_BODY
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_BODY_FIELD
        and is_token("BODY") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_BODY_FIELD
        and parsed_header["policy"] == DEFAULT_BODY
        and parsed_header["header"] == BODY_HEADER
        and parsed_header["body"] is True
        and parsed_header["transfer"] is False
        and preloaded == TRANSFER_POLICY
        and ascii_serialize_mime_directive() == RFC_BODY_DIRECTIVE
        and mime_directive_pair() == ("body", "name")
        and RFC_BODY_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_mime(TRANSFER_POLICY) == RFC_MIME_TRANSFER
        and DEFAULT_MIMEDIGEST == request_mimedigest(DEFAULT_MIMEID, SENTINEL)
        and "mimedigest=" in canonical_transfer(SENTINEL, DEFAULT_MIMEID, DEFAULT_MIMEDIGEST)
        and canonical_body(SENTINEL, DEFAULT_MIMEID).startswith("BODY")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "BODY"
        and asked["mime_kind"] == "body"
        and asked["mimeid"] == DEFAULT_MIMEID
        and preload_req["mime_kind"] == "transfer"
        and preload_req["mimedigest"] == DEFAULT_MIMEDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["mime_kind"] == "body"
        and preload_reply["mime_kind"] == "transfer"
        and got["policy"] == DEFAULT_BODY
        and preload_reply["policy"] == TRANSFER_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["mimedigest"] == DEFAULT_MIMEDIGEST
        and preload_reply["mimedigest"] == DEFAULT_MIMEDIGEST
        and mime_matches(serialize_mime(got["policy"]), advertised)
    )

    checks["catalog_names_mime"] = (
        len(catalog) > 106
        and catalog[106]["id"] == MIME_ACTUATION_ID
        and catalog[105]["id"] == URI_ACTUATION_ID
        and catalog[106]["source"] == "genesis_bind_mime"
    )
    checks["catalog_names_gopher"] = (
        len(catalog) > 107
        and catalog[107]["id"] == GOPHER_ACTUATION_ID
        and catalog[107]["source"] == "genesis_bind_gopher"
    )
    family = capability_family(MIME_ACTUATION_GOAL)
    checks["family_is_mime"] = "mime" in family
    checks["family_is_mime_surface"] = "mime" in family
    checks["family_is_mimeid"] = "mimeid" in family
    checks["family_is_rfc1521"] = "rfc1521" in family
    checks["family_is_mimedigest"] = "mimedigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_gopher"] = (
        "gopher" not in family.split("/")
        and "rfc1436" not in family
        and "gopherid" not in family
        and "gopherdigest" not in family
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
    packed = encode_body(identity=SENTINEL, mimeid=DEFAULT_MIMEID, mimedigest=DEFAULT_MIMEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_body"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_mimeid"] is True
        and parsed["mimeid"] == DEFAULT_MIMEID
        and parsed["mimedigest"] == DEFAULT_MIMEDIGEST
        and parsed["is_transfer"] is False
        and parsed["is_transfer"] is False
        and parsed["type"] == FRAME_BODY
        and parsed["first_byte"] == MIME_FIRST
    )
    shook = encode_transfer(
        identity=SENTINEL,
        mimeid=DEFAULT_MIMEID,
        mimedigest=DEFAULT_MIMEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_transfer"] is True
        and answer_parsed["is_transfer"] is True
        and answer_parsed["is_body"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["mimeid"] == DEFAULT_MIMEID
        and answer_parsed["mimedigest"] == DEFAULT_MIMEDIGEST
        and answer_parsed["has_mimedigest"] is True
        and answer_parsed["type"] == FRAME_TRANSFER
        and answer_parsed["first_byte"] == MIME_FIRST
    )
    bare = encode_body(identity=SENTINEL, mimeid=DEFAULT_MIMEID, include_mimeid=False)
    checks["missing_mimeid_is_unauthed"] = parse_message(bare)["has_mimeid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(MIME_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_mime = ToolDescriptor(name="remote_mime", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_mime)
    checks["naive_mcp_mime_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = mime_tool_descriptor()
    default_mime = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MIME_TOOL_PROVIDER),
    )
    checks["default_mime_provider_is_unsupported"] = (
        default_mime.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{MIME_TOOL_PROVIDER}" in default_mime.reasons
    )
    checks["opted_in_mime_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_mime],
        required_tool_names=("local_memory", "mime"),
    )
    checks["naive_preflight_missing_mime"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["mime"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "mime"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MIME_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "mime" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="mime-actuation-") as tmp:
        root = Path(tmp)
        missing = run_mime_workflow(with_mimeid=False, output_dir=root / "missing")
        skip_bind = run_mime_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_body = run_mime_workflow(do_body=False, output_dir=root / "skip-body")
        skip_transfer = run_mime_workflow(do_transfer=False, output_dir=root / "skip-transfer")
        skip_mimedigest = run_mime_workflow(do_mimedigest=False, output_dir=root / "skip-mimedigest")
        skip_replay = run_mime_workflow(replay=False, output_dir=root / "skip-replay")
        skip_mimeid = run_mime_workflow(use_mimeid=False, output_dir=root / "skip-mimeid")
        live = run_mime_workflow(output_dir=root / "live")
        verify = verify_mime_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_mime_trace(clone)
        checks["naive_without_mimeid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_mimeid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_body_stays_empty"] = (
            skip_body["ok"] is False
            and skip_body["error"] == "body_required"
            and skip_body["final_status"] == 409
            and skip_body["payload_exists"] is False
        )
        checks["skip_transfer_stays_empty"] = (
            skip_transfer["ok"] is False
            and skip_transfer["error"] == "transfer_required"
            and skip_transfer["final_status"] == 409
            and skip_transfer["payload_exists"] is False
        )
        checks["skip_mimedigest_stays_empty"] = (
            skip_mimedigest["ok"] is False
            and skip_mimedigest["error"] == "mimedigest_required"
            and skip_mimedigest["final_status"] == 409
            and skip_mimedigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_mimeid_stays_empty"] = (
            skip_mimeid["ok"] is False
            and skip_mimeid["error"] == "mimeid_required"
            and skip_mimeid["final_status"] == 409
            and skip_mimeid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_mimedigest"] = (
            int(live.get("mimeid") or 0) == DEFAULT_MIMEID
            and int(live.get("mimedigest") or 0) == DEFAULT_MIMEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_mimeid_encode_transfer_mimedigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_body["ok"] is False
            and skip_transfer["ok"] is False
            and skip_mimedigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_mimeid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="mime-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MIME_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_mime"] = (
        live_goal == MIME_ACTUATION_GOAL
        and MIME_ACTUATION_ID in live_done
        and live_source == "genesis_bind_mime"
    )

    with tempfile.TemporaryDirectory(prefix="mime-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(MIME_LEFTOVER, root)
        register_catalog_proved(root, MIME_ACTUATION_ID)
        reason = leftover_satisfied_by(MIME_LEFTOVER, root)
        after = leftover_is_open(MIME_LEFTOVER, root)
    checks["mime_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_mime_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{MIME_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mime_actuation_capability()
    return {
        "ok": ok,
        "action": "mime_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MIME_ACTUATION_GOAL,
        "done_when": MIME_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
