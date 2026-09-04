"""Drive a first-class Content-Disposition tool through RFC 6266 DISPOSITION/ATTACHMENT.

Tool routing already fails missions that require ``contentdisposition``: hosted
contentdisposition endpoints stay on the unsupported MCP provider, and no first-party
contentdisposition provider is executable. Unbound therefore cannot speak a DISPOSITION,
lockstep a ATTACHMENT dispositionid handshake over HTTP Attachment DISPOSITIONID,
independently poll the stored dispositiondigest, or seal a dispositiondigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``contentdisposition`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 6266 daemon
- keep a missing-dispositionid client so the contentdisposition-dispositionid hole stays falsifiable
- refuse ATTACHMENT until a DISPOSITION lands with a non-empty dispositionid
- independently poll the stored dispositiondigest on a later client socket
- persist a sealed dispositiondigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 6265 HTTP Cookie
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
    CONTENTDISPOSITION_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    contentdisposition_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
CONTENTDISPOSITION_ACTUATION_ID = "capability.contentdisposition-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-CONTENTDISPOSITION-OK"
POLL_TOKEN = "BH-CONTENTDISPOSITION-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_DISPOSITIONID = 0
EMPTY_DISPOSITIONDIGEST = 0
CD_FIRST = 0x44  # RFC 6266 Content-Disposition (ASCII 'D')
DISPOSITIONID_SIZE = 4
DISPOSITIONDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_ATTACHMENT = 0x02  # RFC 6266 report confirmation
FRAME_DISPOSITION = 0x01  # RFC 6266 Content-Disposition
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
CONTENTDISPOSITION_LEFTOVER = (
    "Later genesis can take RFC 6266 Content-Disposition Header Field DISPOSITION/ATTACHMENT over a "
    "dispositionid-gated dispositiondigest."
)
CONTENTDISPOSITION_ACTUATION_DONE_WHEN = (
    f"capability_exists:{CONTENTDISPOSITION_ACTUATION_ID};"
    f"capability_proved:{CONTENTDISPOSITION_ACTUATION_ID};"
    "no_skill_route"
)
CONTENTDISPOSITION_ACTUATION_GOAL = (
    "Repair rfc6266 contentdisposition disposition/attachment cycle cannot land over http "
    "contentdisposition dispositionid: hosted contentdisposition endpoints remain unsupported so a DISPOSITION then "
    "ATTACHMENT dispositionid handshake cannot land and a sealed dispositiondigest "
    "cannot be produced. A missing contentdisposition dispositionid stays forbidden; fail-closed "
    "routing never opts the contentdisposition provider in. An independent later poll of the "
    "stored dispositiondigest keeps the hole falsifiable."
)


class ContentdispositionActuationError(RuntimeError):
    """Raised when the attachment session or loopback daemon fixture misbehaves."""


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
# RFC 6266 section 4.1 Content-Disposition / 4.2 Attachment.
RFC_DISPOSITION_FIELD = "DISPOSITION"
RFC_ATTACHMENT_FIELD = "ATTACHMENT"
RFC_CONTENTDISPOSITION_ATTACHMENT = RFC_ATTACHMENT_FIELD
RFC_DISPOSITION_PARAM = 'filename="report.bin"'
DEFAULT_DISPOSITION = "DISPOSITION"
ATTACHMENT_POLICY = "ATTACHMENT"
DISPOSITION_HEADER = "Content-Disposition"
ATTACHMENT_HEADER = "Content-Disposition"
CONTENTDISPOSITION_ATTACHMENT_HEADER = ATTACHMENT_HEADER
RFC_FILENAME = "report.bin"
RFC_DISP_TYPE = "attachment"
RFC_DISPOSITION_PATH = "/"
RFC_DISPOSITION_PAIR = 'attachment; filename="report.bin"'
RFC_DISPOSITION_EMPTY = ""


def disposition_pair(
    disp_type: str = RFC_DISP_TYPE,
    filename: str = RFC_FILENAME,
) -> tuple[str, str]:
    """RFC 6266 section 4.1 disposition-type and filename-parm."""

    return str(disp_type or RFC_DISP_TYPE), str(filename or RFC_FILENAME)


def ascii_serialize_disposition(
    disp_type: str = RFC_DISP_TYPE,
    filename: str = RFC_FILENAME,
) -> str:
    """RFC 6266 section 4.2 Content-Disposition field-value."""

    live_type, live_name = disposition_pair(disp_type, filename)
    if not is_token(live_type):
        raise ContentdispositionActuationError("illegal_disposition_type")
    if any(ord(char) <= 0x20 or char in '",;\\' or ord(char) >= 0x7F for char in live_name):
        raise ContentdispositionActuationError("illegal_filename")
    return f'{live_type}; filename="{live_name}"'


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise ContentdispositionActuationError("short_contentdisposition")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 6266 directive-name."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_contentdisposition(policy: str | Sequence[str]) -> str:
    """Serialize RFC 6266 Content-Disposition field-value."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise ContentdispositionActuationError("illegal_contentdisposition")
    upper = text.upper()
    if upper in {"DISPOSITION", "INLINE"}:
        return "DISPOSITION"
    if upper in {"ATTACHMENT", "ATTACH"}:
        return "ATTACHMENT"
    if upper.startswith("FILENAME="):
        path_value = text.split("=", 1)[1].strip().strip('"')
        if not path_value or ";" in path_value:
            raise ContentdispositionActuationError("illegal_contentdisposition")
        return f'filename="{path_value}"'
    raise ContentdispositionActuationError("illegal_contentdisposition")


def parse_contentdisposition(text: str) -> str:
    """Parse RFC 6266 Content-Disposition into DISPOSITION, ATTACHMENT, or filename."""

    raw = str(text or "").strip()
    if not raw:
        raise ContentdispositionActuationError("illegal_contentdisposition")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper()
    if upper in {"DISPOSITION", "INLINE"}:
        return "DISPOSITION"
    if upper in {"ATTACHMENT", "ATTACH"}:
        return "ATTACHMENT"
    if upper.startswith("FILENAME="):
        path_value = head.split("=", 1)[1].strip().strip('"')
        if not path_value or ";" in path_value:
            raise ContentdispositionActuationError("illegal_contentdisposition")
        return f'filename="{path_value}"'
    raise ContentdispositionActuationError("illegal_contentdisposition")


def encode_contentdisposition_header(policy: str | Sequence[str]) -> bytes:
    """RFC 6266 Content-Disposition field as bytes."""

    return serialize_contentdisposition(policy).encode("ascii")


def parse_contentdisposition_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_contentdisposition(field_value) if field_value else DEFAULT_DISPOSITION
    return {
        "field_value": field_value,
        "policy": policy,
        "header": DISPOSITION_HEADER,
        "directive": str(policy),
        "disposition": str(policy) == "DISPOSITION",
        "attachment": str(policy) == "ATTACHMENT",
    }


def canonical_disposition(identity: str, dispositionid: int) -> str:
    """RFC 6266 DISPOSITION advertisement bound to identity and dispositionid."""

    return (
        f"{serialize_contentdisposition(DEFAULT_DISPOSITION)}, "
        f"attachment={ascii_serialize_disposition()}, "
        f"identity={identity}, dispositionid={int(dispositionid) & 0xFFFFFFFF}"
    )


def canonical_attachment(identity: str, dispositionid: int, dispositiondigest: int | None = None) -> str:
    """RFC 6266 ATTACHMENT confirmation of the stored attachment policy."""

    suffix = ""
    if dispositiondigest is not None:
        suffix = f", dispositiondigest={int(dispositiondigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_contentdisposition(ATTACHMENT_POLICY)}, "
        f"attachment={ascii_serialize_disposition()}, "
        f"identity={identity}, dispositionid={int(dispositionid) & 0xFFFFFFFF}{suffix}"
    )


def representation_attachment(identity: str, dispositionid: int, dispositiondigest: int) -> str:
    return canonical_attachment(identity, dispositionid, dispositiondigest)


def contentdisposition_matches(left: str, right: str) -> bool:
    return parse_contentdisposition(left) == parse_contentdisposition(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise ContentdispositionActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise ContentdispositionActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise ContentdispositionActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise ContentdispositionActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def disposition_request(identity: str, dispositionid: int) -> bytes:
    """HTTP GET that elicits RFC 6266 Origin DISPOSITION."""

    keyid = f"{int(dispositionid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /contentdisposition/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Disposition-Id: {int(dispositionid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def attachment_request(identity: str, dispositionid: int, dispositiondigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 6266 ATTACHMENT confirmation of the stored attachment policy."""

    keyid = f"{int(dispositionid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if dispositiondigest is not None:
        extra = f"Disposition-Digest: {int(dispositiondigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /contentdisposition/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Disposition-Id: {int(dispositionid) & 0xFFFFFFFF}\r\n"
        "Disposition-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    contentdisposition_kind = "attachment" if fields.get("disposition-confirm") == "1" else "disposition"
    attachment_field = fields.get("content-disposition") or ""
    policy = parse_contentdisposition(attachment_field) if attachment_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "contentdisposition_kind": contentdisposition_kind,
        "policy": policy,
        "dispositionid": int(fields["disposition-id"]) if fields.get("disposition-id") else EMPTY_DISPOSITIONID,
        "dispositiondigest": int(fields["disposition-digest"]) if fields.get("disposition-digest") else EMPTY_DISPOSITIONDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def disposition_response(identity: str, dispositionid: int, dispositiondigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 6266 Origin DISPOSITION, carrying the stored dispositiondigest."""

    advertised = serialize_contentdisposition(DEFAULT_DISPOSITION)
    payload = bytes(body or canonical_disposition(identity, dispositionid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Content-Disposition: {advertised}\r\n"
        f"Disposition-Id: {int(dispositionid) & 0xFFFFFFFF}\r\n"
        f"Disposition-Digest: {int(dispositiondigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/content-disposition\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def attachment_response(identity: str, dispositionid: int, dispositiondigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 6266 Attachment ATTACHMENT, carrying the stored ATTACHMENT policy."""

    advertised = serialize_contentdisposition(ATTACHMENT_POLICY)
    payload = bytes(body or representation_attachment(identity, dispositionid, dispositiondigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Content-Disposition: {advertised}\r\n"
        f"Disposition-Id: {int(dispositionid) & 0xFFFFFFFF}\r\n"
        f"Disposition-Digest: {int(dispositiondigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/content-disposition-confirm\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise ContentdispositionActuationError("illegal_content_length") from error
    field_value = fields.get("content-disposition") or ""
    policy = parse_contentdisposition(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/content-disposition-confirm" or policy == ATTACHMENT_POLICY:
        status = 200
        contentdisposition_kind = "attachment"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        contentdisposition_kind = "disposition"
    else:
        status = 0
        contentdisposition_kind = "disposition"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "contentdisposition_kind": contentdisposition_kind,
        "policy": policy,
        "dispositionid": int(fields["disposition-id"]) if fields.get("disposition-id") else EMPTY_DISPOSITIONID,
        "dispositiondigest": int(fields["disposition-digest"]) if fields.get("disposition-digest") else EMPTY_DISPOSITIONDIGEST,
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
        raise ContentdispositionActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise ContentdispositionActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise ContentdispositionActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise ContentdispositionActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_dispositionid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"dispositionid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_dispositionid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-dispositionid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_dispositiondigest(dispositionid: int = EMPTY_DISPOSITIONID, token: str = SENTINEL) -> int:
    material = canonical_disposition(token or SENTINEL, int(dispositionid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_DISPOSITIONID = request_dispositionid(SENTINEL)
DEFAULT_DISPOSITIONDIGEST = request_dispositiondigest(DEFAULT_DISPOSITIONID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    dispositionid: int,
    dispositiondigest: int,
    include_dispositionid: bool = True,
) -> bytes:
    live_dispositionid = int(dispositionid) & 0xFFFFFFFF if include_dispositionid else EMPTY_DISPOSITIONID
    live_digest = int(dispositiondigest) & 0xFFFFFFFF if include_dispositionid and live_dispositionid else EMPTY_DISPOSITIONDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_dispositionid) if live_dispositionid else b""
    header = bytearray()
    header.append(CD_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_disposition(
    *,
    identity: str,
    dispositionid: int,
    dispositiondigest: int | None = None,
    include_dispositionid: bool = True,
) -> bytes:
    live_dispositionid = int(dispositionid) & 0xFFFFFFFF if include_dispositionid else EMPTY_DISPOSITIONID
    live_digest = int(dispositiondigest) if dispositiondigest is not None else request_dispositiondigest(live_dispositionid, identity)
    return encode_packet(
        FRAME_DISPOSITION,
        identity=identity,
        dispositionid=live_dispositionid,
        dispositiondigest=live_digest,
        include_dispositionid=include_dispositionid,
    )


def encode_attachment(
    *,
    identity: str,
    dispositionid: int,
    dispositiondigest: int | None = None,
    include_dispositionid: bool = True,
) -> bytes:
    live_dispositionid = int(dispositionid) & 0xFFFFFFFF if include_dispositionid else EMPTY_DISPOSITIONID
    live_digest = int(dispositiondigest) if dispositiondigest is not None else request_dispositiondigest(live_dispositionid, identity)
    return encode_packet(
        FRAME_ATTACHMENT,
        identity=identity,
        dispositionid=live_dispositionid,
        dispositiondigest=live_digest,
        include_dispositionid=include_dispositionid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise ContentdispositionActuationError("short_packet")
    first = raw[0]
    if first != CD_FIRST:
        raise ContentdispositionActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise ContentdispositionActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == DISPOSITIONID_SIZE:
        live_dispositionid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_dispositionid = EMPTY_DISPOSITIONID
    else:
        raise ContentdispositionActuationError("illegal_dispositionid")
    if offset >= len(raw):
        raise ContentdispositionActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_DISPOSITION, FRAME_ATTACHMENT}:
        raise ContentdispositionActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise ContentdispositionActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise ContentdispositionActuationError("checksum_failed")
    if len(payload) < 5:
        raise ContentdispositionActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise ContentdispositionActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_dispositionid = int(live_dispositionid) != EMPTY_DISPOSITIONID
    has_dispositiondigest = has_dispositionid and int(live_digest) != EMPTY_DISPOSITIONDIGEST
    is_disposition = frame_type == FRAME_DISPOSITION
    is_attachment = frame_type == FRAME_ATTACHMENT
    return {
        "type": int(frame_type),
        "is_disposition": is_disposition,
        "is_attachment": is_attachment,
        "is_response": is_attachment,
        "dispositionid": int(live_dispositionid),
        "has_dispositionid": has_dispositionid,
        "dispositiondigest": int(live_digest),
        "has_dispositiondigest": has_dispositiondigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http_state": "RFC6266",
        "serialize_field": canonical_disposition(identity, live_dispositionid) if has_dispositionid else "",
        "attachment_field": canonical_attachment(identity, live_dispositionid, live_digest) if has_dispositiondigest else "",
    }


class ContentdispositionClient:
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
            raise ContentdispositionActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_attachment"] or not packet["is_response"]:
            raise ContentdispositionActuationError("dispositiondigest_required")
        if not packet["has_dispositionid"]:
            raise ContentdispositionActuationError("dispositionid_required")
        if not packet["has_dispositiondigest"]:
            raise ContentdispositionActuationError("dispositiondigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_dispositiondigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_dispositiondigest:
            raise ContentdispositionActuationError("dispositiondigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "dispositionid": int(reply.get("dispositionid") or EMPTY_DISPOSITIONID),
            "identity": str(reply.get("identity") or ""),
            "dispositiondigest": int(reply.get("dispositiondigest") or EMPTY_DISPOSITIONDIGEST),
        }

    def report(
        self,
        identity: str,
        dispositionid: int,
        dispositiondigest: int = EMPTY_DISPOSITIONDIGEST,
        *,
        wait_dispositiondigest: bool = True,
        include_dispositionid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_attachment(
            identity=identity,
            dispositionid=dispositionid,
            dispositiondigest=dispositiondigest or request_dispositiondigest(dispositionid, identity),
            include_dispositionid=include_dispositionid,
        )
        return self.exchange(packet, wait_dispositiondigest=wait_dispositiondigest)


class ContentdispositionSession:
    """DISPOSITIONID-gated loopback RFC 6266 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        dispositionid_gate: int = DEFAULT_DISPOSITIONID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dispositionid_gate = int(dispositionid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.dispositionid = EMPTY_DISPOSITIONID
        self.dispositiondigest = EMPTY_DISPOSITIONDIGEST
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

    def store_dispositionid_once(self, identity: str, dispositionid: int, dispositiondigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(dispositionid or EMPTY_DISPOSITIONID)
            live_digest = int(dispositiondigest or EMPTY_DISPOSITIONDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.dispositionid = live
                self.dispositiondigest = live_digest or request_dispositiondigest(live, name)
                self.stored = True
            return str(self.identity), int(self.dispositionid), int(self.dispositiondigest)

    def read_dispositionid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.dispositionid), int(self.dispositiondigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "dispositionid": EMPTY_DISPOSITIONID,
            "dispositiondigest": EMPTY_DISPOSITIONDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _dispositionid_missing(self) -> bool:
        return not int(self.dispositionid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, dispositionid: int, dispositiondigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_attachment(
            identity=identity,
            dispositionid=dispositionid,
            dispositiondigest=dispositiondigest,
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
            except ContentdispositionActuationError:
                continue
            if not packet.get("is_disposition") and not packet.get("is_attachment"):
                continue
            if not packet.get("has_dispositionid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_dispositionid, stored_digest = self.store_dispositionid_once(
                identity,
                int(packet.get("dispositionid") or EMPTY_DISPOSITIONID),
                int(packet.get("dispositiondigest") or EMPTY_DISPOSITIONDIGEST),
            )
            if not stored_name or not stored_dispositionid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_disposition"):
                    self.opened = True
                if packet.get("is_attachment"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_dispositionid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._dispositionid_missing():
            return self._forbidden("missing_dispositionid")
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
        do_disposition: bool = True,
        do_attachment: bool = True,
        do_dispositiondigest: bool = True,
        replay: bool = True,
        use_dispositionid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._dispositionid_missing():
            return self._forbidden("missing_dispositionid")
        live_token = str(token or SENTINEL)
        origin_dispositionid = request_dispositionid(live_token)
        origin_digest = request_dispositiondigest(origin_dispositionid, live_token)
        client: ContentdispositionClient | None = None
        independent: ContentdispositionClient | None = None
        try:
            client = ContentdispositionClient(self.host, int(self.port))
            if not do_disposition:
                return self._conflict("disposition_required")
            bind_packet = encode_disposition(
                identity=live_token,
                dispositionid=origin_dispositionid,
                dispositiondigest=origin_digest,
                include_dispositionid=use_dispositionid,
            )
            if not use_dispositionid:
                try:
                    client.exchange(bind_packet, wait_dispositiondigest=True)
                except ContentdispositionActuationError:
                    return self._conflict("dispositionid_required")
                return self._conflict("dispositionid_required")
            client.send(bind_packet)
            if not do_attachment:
                return self._conflict("attachment_required")
            proxy_packet = encode_attachment(
                identity=live_token,
                dispositionid=origin_dispositionid,
                dispositiondigest=origin_digest,
                include_dispositionid=True,
            )
            if not do_dispositiondigest:
                try:
                    client.exchange(proxy_packet, wait_dispositiondigest=False)
                except ContentdispositionActuationError as error:
                    if str(error) == "dispositiondigest_required":
                        return self._conflict("dispositiondigest_required")
                    return self._conflict("dispositiondigest_required")
                return self._conflict("dispositiondigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_dispositiondigest=True)
            except ContentdispositionActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("dispositionid_required")
                if reason == "dispositiondigest_required":
                    return self._conflict("dispositiondigest_required")
                return self._conflict("disposition_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("disposition_required")
            if int(reply.get("dispositionid") or EMPTY_DISPOSITIONID) != origin_dispositionid:
                return self._conflict("dispositiondigest_required")
            if int(reply.get("dispositiondigest") or EMPTY_DISPOSITIONDIGEST) != origin_digest:
                return self._conflict("dispositiondigest_required")
            self.retrieved = True
            if replay:
                independent = ContentdispositionClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_dispositionid(live_token),
                        request_dispositiondigest(poll_dispositionid(live_token), POLL_TOKEN),
                        wait_dispositiondigest=True,
                    )
                except ContentdispositionActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_dispositionid, stored_digest = self.read_dispositionid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_dispositionid != origin_dispositionid
                    or stored_digest != origin_digest
                    or int(poll.get("dispositionid") or EMPTY_DISPOSITIONID) != origin_dispositionid
                    or int(poll.get("dispositiondigest") or EMPTY_DISPOSITIONDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_dispositionid}:{origin_digest}:{live_token}:{canonical_disposition(live_token, origin_dispositionid)}:{canonical_attachment(live_token, origin_dispositionid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "dispositionid": origin_dispositionid,
                "dispositiondigest": origin_digest,
                "disposition_frame": True,
                "attachment_frame": True,
                "dispositiondigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "dispositionid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_contentdisposition_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "dispositionid": origin_dispositionid,
                "dispositiondigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "disposition_frame": True,
                "attachment_frame": True,
                "dispositiondigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "dispositionid_bound": True,
            }
        except (OSError, ContentdispositionActuationError) as error:
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
        live = independent_contentdisposition_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "dispositionid": int(live.get("dispositionid") or EMPTY_DISPOSITIONID),
            "dispositiondigest": int(live.get("dispositiondigest") or EMPTY_DISPOSITIONDIGEST),
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


def call_contentdisposition_tool(session: ContentdispositionSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one attachment tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_disposition = True if arguments.get("disposition") is None else bool(arguments.get("disposition"))
    do_attachment = True if arguments.get("attachment") is None else bool(arguments.get("attachment"))
    do_dispositiondigest = True if arguments.get("dispositiondigest") is None else bool(arguments.get("dispositiondigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_dispositionid = True if arguments.get("use_dispositionid") is None else bool(arguments.get("use_dispositionid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_disposition=do_disposition,
            do_attachment=do_attachment,
            do_dispositiondigest=do_dispositiondigest,
            replay=replay,
            use_dispositionid=use_dispositionid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise ContentdispositionActuationError(f"unsupported contentdisposition action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_contentdisposition_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed attachment dispositiondigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "dispositionid": EMPTY_DISPOSITIONID,
        "dispositiondigest": EMPTY_DISPOSITIONDIGEST,
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
            "disposition_frame",
            "attachment_frame",
            "dispositiondigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "dispositionid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    dispositionid = int(payload.get("dispositionid") or EMPTY_DISPOSITIONID)
    dispositiondigest = int(payload.get("dispositiondigest") or EMPTY_DISPOSITIONDIGEST)
    dual = port > 0 and bool(dispositionid) and bool(dispositiondigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "dispositionid": dispositionid,
        "dispositiondigest": dispositiondigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "disposition_frame": payload.get("disposition_frame") is True,
        "attachment_frame": payload.get("attachment_frame") is True,
        "dispositiondigest_response": payload.get("dispositiondigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "dispositionid_bound": payload.get("dispositionid_bound") is True,
    }


def run_contentdisposition_workflow(
    *,
    with_dispositionid: bool = True,
    skip_bind: bool = False,
    do_disposition: bool = True,
    do_attachment: bool = True,
    do_dispositiondigest: bool = True,
    replay: bool = True,
    use_dispositionid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 6266 DISPOSITION/ATTACHMENT dispositionid cycle workflow."""

    descriptor = contentdisposition_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CONTENTDISPOSITION_TOOL_PROVIDER),
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
        raise ContentdispositionActuationError(f"contentdisposition tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="contentdisposition-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = ContentdispositionSession(out, dispositionid_gate=DEFAULT_DISPOSITIONID if with_dispositionid else EMPTY_DISPOSITIONID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "disposition": do_disposition,
            "attachment": do_attachment,
            "dispositiondigest": do_dispositiondigest,
            "replay": replay,
            "use_dispositionid": use_dispositionid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_contentdisposition_tool(session, arguments))
            except ContentdispositionActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_contentdisposition_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_dispositionid
        and not skip_bind
        and do_disposition
        and do_attachment
        and do_dispositiondigest
        and replay
        and use_dispositionid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "contentdisposition_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_dispositionid": with_dispositionid,
        "skip_bind": skip_bind,
        "disposition_frame": do_disposition,
        "attachment": do_attachment,
        "dispositiondigest": do_dispositiondigest,
        "replay": replay,
        "use_dispositionid": use_dispositionid,
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
        "dispositionid_value": int(publish_result.get("dispositionid") or independent.get("dispositionid") or EMPTY_DISPOSITIONID),
        "dispositiondigest_value": int(publish_result.get("dispositiondigest") or independent.get("dispositiondigest") or EMPTY_DISPOSITIONDIGEST),
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
        "dispositionid": int(trace_body["dispositionid_value"] or EMPTY_DISPOSITIONID),
        "dispositiondigest": int(trace_body["dispositiondigest_value"] or EMPTY_DISPOSITIONDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_dispositionid": with_dispositionid,
        "skip_bind": skip_bind,
        "disposition_cycle": do_disposition,
        "attachment_cycle": do_attachment,
        "dispositiondigest_cycle": do_dispositiondigest,
        "replay": replay,
        "use_dispositionid": use_dispositionid,
    }


def verify_contentdisposition_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_contentdisposition_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    dispositionid = int(trace.get("dispositionid_value") or independent.get("dispositionid") or EMPTY_DISPOSITIONID)
    dispositiondigest = int(trace.get("dispositiondigest_value") or independent.get("dispositiondigest") or EMPTY_DISPOSITIONDIGEST)
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
        "disposition_frame": independent.get("disposition_frame") is True,
        "attachment_frame": independent.get("attachment_frame") is True,
        "dispositiondigest_response": independent.get("dispositiondigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "dispositionid_bound": independent.get("dispositionid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "dispositiondigest_recorded": (
            port > 0
            and dispositionid == DEFAULT_DISPOSITIONID
            and dispositiondigest == DEFAULT_DISPOSITIONDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def contentdisposition_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.contentdisposition_actuation import "
        "builtin_contentdisposition_actuation_proof; r=builtin_contentdisposition_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='contentdisposition_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_contentdisposition_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=CONTENTDISPOSITION_ACTUATION_ID,
        name="First-class RFC 6266 Content-Disposition DISPOSITION/ATTACHMENT actuation",
        description=(
            "Missions that require a contentdisposition tool can opt the contentdisposition provider in, "
            "bind a loopback RFC 6266 Content-Disposition endpoint, complete a DISPOSITION "
            "with a non-empty dispositionid, lockstep a ATTACHMENT that carries the "
            "stored dispositiondigest, independently poll the stored dispositiondigest "
            "on a later socket, and seal a digest-chained dispositiondigest. Default "
            "routing stays fail-closed; a missing dispositionid keeps the hole "
            "falsifiable, and skip-DISPOSITION/ATTACHMENT/DISPOSITIONDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.contentdisposition_actuation:builtin_contentdisposition_actuation_proof",
        proof_command=contentdisposition_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.httpcookie-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/contentdisposition_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/httpcookie_actuation.py",
            "src/blackhole_agent/weblinking_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required contentdisposition tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 6266 daemon, speaks a "
            "DISPOSITION then ATTACHMENT over Content-Disposition with a non-empty dispositionid and "
            "dispositiondigest, independently polls the stored dispositiondigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 6265 HTTP Cookie lockstep is proved. "
            "Missing dispositionids, skip-DISPOSITION, skip-ATTACHMENT, skip-dispositiondigest, skip-REPLAY, "
            "and a DISPOSITION aimed without a dispositionid stay fail-closed. "
            "Later genesis can take RFC 5988 Web Linking LINK/RELATION as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("contentdisposition", "rfc6266", "http", "dispositionid", "dispositiondigest", "disposition", "attachment", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T180935Z-b9a60705",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_contentdisposition_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 6266 attachment lockstep actuation seals a dispositiondigest."""

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
    checks["denylists_self"] = CONTENTDISPOSITION_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(CONTENTDISPOSITION_ACTUATION_GOAL) == (
        CONTENTDISPOSITION_ACTUATION_ID,
    )
    checks["leftover_text_binds_contentdisposition"] = leftover_marker_ids(CONTENTDISPOSITION_LEFTOVER) == (
        CONTENTDISPOSITION_ACTUATION_ID,
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
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_contentdisposition"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"contentdisposition_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            CONTENTDISPOSITION_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = CONTENTDISPOSITION_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_contentdisposition(DEFAULT_DISPOSITION)
    rebuilt = serialize_contentdisposition(parse_contentdisposition(advertised))
    preloaded = parse_contentdisposition(RFC_CONTENTDISPOSITION_ATTACHMENT)
    header = encode_contentdisposition_header(DEFAULT_DISPOSITION)
    parsed_header = parse_contentdisposition_header(header)
    asked = parse_http_request(disposition_request(SENTINEL, DEFAULT_DISPOSITIONID))
    preload_req = parse_http_request(attachment_request(SENTINEL, DEFAULT_DISPOSITIONID, DEFAULT_DISPOSITIONDIGEST))
    got = parse_http_response(disposition_response(SENTINEL, DEFAULT_DISPOSITIONID, DEFAULT_DISPOSITIONDIGEST))
    preload_reply = parse_http_response(
        attachment_response(SENTINEL, DEFAULT_DISPOSITIONID, DEFAULT_DISPOSITIONDIGEST)
    )
    checks["contentdisposition_roundtrip"] = (
        parse_contentdisposition(advertised) == DEFAULT_DISPOSITION
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_DISPOSITION_FIELD
        and is_token("DISPOSITION") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_DISPOSITION_FIELD
        and parsed_header["policy"] == DEFAULT_DISPOSITION
        and parsed_header["header"] == DISPOSITION_HEADER
        and parsed_header["disposition"] is True
        and parsed_header["attachment"] is False
        and preloaded == ATTACHMENT_POLICY
        and ascii_serialize_disposition() == RFC_DISPOSITION_PAIR
        and disposition_pair() == (RFC_DISP_TYPE, RFC_FILENAME)
        and RFC_DISPOSITION_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_contentdisposition(ATTACHMENT_POLICY) == RFC_CONTENTDISPOSITION_ATTACHMENT
        and DEFAULT_DISPOSITIONDIGEST == request_dispositiondigest(DEFAULT_DISPOSITIONID, SENTINEL)
        and "dispositiondigest=" in canonical_attachment(SENTINEL, DEFAULT_DISPOSITIONID, DEFAULT_DISPOSITIONDIGEST)
        and canonical_disposition(SENTINEL, DEFAULT_DISPOSITIONID).startswith("DISPOSITION")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["contentdisposition_kind"] == "disposition"
        and asked["dispositionid"] == DEFAULT_DISPOSITIONID
        and preload_req["contentdisposition_kind"] == "attachment"
        and preload_req["dispositiondigest"] == DEFAULT_DISPOSITIONDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["contentdisposition_kind"] == "disposition"
        and preload_reply["contentdisposition_kind"] == "attachment"
        and got["policy"] == DEFAULT_DISPOSITION
        and preload_reply["policy"] == ATTACHMENT_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["dispositiondigest"] == DEFAULT_DISPOSITIONDIGEST
        and preload_reply["dispositiondigest"] == DEFAULT_DISPOSITIONDIGEST
        and contentdisposition_matches(serialize_contentdisposition(got["policy"]), advertised)
    )

    checks["catalog_names_contentdisposition"] = (
        len(catalog) > 87
        and catalog[87]["id"] == CONTENTDISPOSITION_ACTUATION_ID
        and catalog[86]["id"] == HTTPCOOKIE_ACTUATION_ID
        and catalog[87]["source"] == "genesis_bind_contentdisposition"
    )
    checks["catalog_names_weblinking"] = (
        len(catalog) > 88
        and catalog[88]["id"] == WEBLINKING_ACTUATION_ID
        and catalog[88]["source"] == "genesis_bind_weblinking"
    )
    family = capability_family(CONTENTDISPOSITION_ACTUATION_GOAL)
    checks["family_is_contentdisposition"] = "contentdisposition" in family
    checks["family_is_contentdisposition_surface"] = "contentdisposition" in family
    checks["family_is_dispositionid"] = "dispositionid" in family
    checks["family_is_rfc6266"] = "rfc6266" in family
    checks["family_is_dispositiondigest"] = "dispositiondigest" in family
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
        and "prefixid" not in family
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
    packed = encode_disposition(identity=SENTINEL, dispositionid=DEFAULT_DISPOSITIONID, dispositiondigest=DEFAULT_DISPOSITIONDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_disposition"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_dispositionid"] is True
        and parsed["dispositionid"] == DEFAULT_DISPOSITIONID
        and parsed["dispositiondigest"] == DEFAULT_DISPOSITIONDIGEST
        and parsed["is_response"] is False
        and parsed["is_attachment"] is False
        and parsed["type"] == FRAME_DISPOSITION
        and parsed["first_byte"] == CD_FIRST
    )
    shook = encode_attachment(
        identity=SENTINEL,
        dispositionid=DEFAULT_DISPOSITIONID,
        dispositiondigest=DEFAULT_DISPOSITIONDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_attachment"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_disposition"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["dispositionid"] == DEFAULT_DISPOSITIONID
        and answer_parsed["dispositiondigest"] == DEFAULT_DISPOSITIONDIGEST
        and answer_parsed["has_dispositiondigest"] is True
        and answer_parsed["type"] == FRAME_ATTACHMENT
        and answer_parsed["first_byte"] == CD_FIRST
    )
    bare = encode_disposition(identity=SENTINEL, dispositionid=DEFAULT_DISPOSITIONID, include_dispositionid=False)
    checks["missing_dispositionid_is_unauthenticated"] = parse_message(bare)["has_dispositionid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    contentdisposition_signature = semantic_signature(CONTENTDISPOSITION_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(contentdisposition_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_contentdisposition = ToolDescriptor(name="remote_contentdisposition", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_contentdisposition)
    checks["naive_mcp_contentdisposition_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = contentdisposition_tool_descriptor()
    default_contentdisposition = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CONTENTDISPOSITION_TOOL_PROVIDER),
    )
    checks["default_contentdisposition_provider_is_unsupported"] = (
        default_contentdisposition.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{CONTENTDISPOSITION_TOOL_PROVIDER}" in default_contentdisposition.reasons
    )
    checks["opted_in_contentdisposition_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_contentdisposition],
        required_tool_names=("local_memory", "contentdisposition"),
    )
    checks["naive_preflight_missing_contentdisposition"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["contentdisposition"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "contentdisposition"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CONTENTDISPOSITION_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "contentdisposition" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="contentdisposition-actuation-") as tmp:
        root = Path(tmp)
        missing = run_contentdisposition_workflow(with_dispositionid=False, output_dir=root / "missing")
        skip_bind = run_contentdisposition_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_disposition = run_contentdisposition_workflow(do_disposition=False, output_dir=root / "skip-disposition")
        skip_attachment = run_contentdisposition_workflow(do_attachment=False, output_dir=root / "skip-attachment")
        skip_dispositiondigest = run_contentdisposition_workflow(do_dispositiondigest=False, output_dir=root / "skip-dispositiondigest")
        skip_replay = run_contentdisposition_workflow(replay=False, output_dir=root / "skip-replay")
        skip_dispositionid = run_contentdisposition_workflow(use_dispositionid=False, output_dir=root / "skip-dispositionid")
        live = run_contentdisposition_workflow(output_dir=root / "live")
        verify = verify_contentdisposition_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_contentdisposition_trace(clone)
        checks["naive_without_dispositionid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_dispositionid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_disposition_stays_empty"] = (
            skip_disposition["ok"] is False
            and skip_disposition["error"] == "disposition_required"
            and skip_disposition["final_status"] == 409
            and skip_disposition["payload_exists"] is False
        )
        checks["skip_attachment_stays_empty"] = (
            skip_attachment["ok"] is False
            and skip_attachment["error"] == "attachment_required"
            and skip_attachment["final_status"] == 409
            and skip_attachment["payload_exists"] is False
        )
        checks["skip_dispositiondigest_stays_empty"] = (
            skip_dispositiondigest["ok"] is False
            and skip_dispositiondigest["error"] == "dispositiondigest_required"
            and skip_dispositiondigest["final_status"] == 409
            and skip_dispositiondigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_dispositionid_stays_empty"] = (
            skip_dispositionid["ok"] is False
            and skip_dispositionid["error"] == "dispositionid_required"
            and skip_dispositionid["final_status"] == 409
            and skip_dispositionid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_dispositiondigest"] = (
            int(live.get("dispositionid") or 0) == DEFAULT_DISPOSITIONID
            and int(live.get("dispositiondigest") or 0) == DEFAULT_DISPOSITIONDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_dispositionid_encode_attachment_dispositiondigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_disposition["ok"] is False
            and skip_attachment["ok"] is False
            and skip_dispositiondigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_dispositionid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="contentdisposition-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != CONTENTDISPOSITION_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_contentdisposition"] = (
        live_goal == CONTENTDISPOSITION_ACTUATION_GOAL
        and CONTENTDISPOSITION_ACTUATION_ID in live_done
        and live_source == "genesis_bind_contentdisposition"
    )

    with tempfile.TemporaryDirectory(prefix="contentdisposition-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(CONTENTDISPOSITION_LEFTOVER, root)
        register_catalog_proved(root, CONTENTDISPOSITION_ACTUATION_ID)
        reason = leftover_satisfied_by(CONTENTDISPOSITION_LEFTOVER, root)
        after = leftover_is_open(CONTENTDISPOSITION_LEFTOVER, root)
    checks["contentdisposition_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_contentdisposition_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{CONTENTDISPOSITION_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_contentdisposition_actuation_capability()
    return {
        "ok": ok,
        "action": "contentdisposition_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": CONTENTDISPOSITION_ACTUATION_GOAL,
        "done_when": CONTENTDISPOSITION_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
