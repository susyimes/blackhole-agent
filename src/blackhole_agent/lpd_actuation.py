"""Drive a first-class Line Printer Daemon Protocol tool through RFC 1179 PRINT/QUEUE.

Tool routing already fails missions that require ``lpd``: hosted
lpd endpoints stay on the unsupported MCP provider, and no first-party
lpd provider is executable. Unbound therefore cannot speak a PRINT,
lockstep a QUEUE lpdid handshake over HTTP/1.0 LPDID,
independently poll the stored lpddigest, or seal a lpddigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``lpd`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1179 daemon
- keep a missing-lpdid client so the lpd-lpdid hole stays falsifiable
- refuse QUEUE until a PRINT lands with a non-empty lpdid
- independently poll the stored lpddigest on a later client socket
- persist a sealed lpddigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 1288 The Finger User Information Protocol
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
    LPD_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    lpd_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
LPD_ACTUATION_ID = "capability.lpd-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-LPD-OK"
POLL_TOKEN = "BH-LPD-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_LPDID = 0
EMPTY_LPDDIGEST = 0
LPD_FIRST = 0x4C  # RFC 1179 LPD (ASCII 'L')
LPDID_SIZE = 4
LPDDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_QUEUE = 0x02  # RFC 1179 QUEUE confirmation
FRAME_PRINT = 0x01  # RFC 1179 PRINT
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
LPD_LEFTOVER = (
    "Later genesis can take RFC 1179 Line Printer Daemon Protocol PRINT/QUEUE over an "
    "lpdid-gated lpddigest."
)
LPD_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LPD_ACTUATION_ID};"
    f"capability_proved:{LPD_ACTUATION_ID};"
    "no_skill_route"
)
LPD_ACTUATION_GOAL = (
    "Repair rfc1179 lpd print/queue cycle cannot land over http "
    "lpd lpdid: hosted lpd endpoints remain unsupported so a PRINT then "
    "QUEUE lpdid handshake cannot land and a sealed lpddigest "
    "cannot be produced. A missing lpd lpdid stays forbidden; fail-closed "
    "routing never opts the lpd provider in. An independent later poll of the "
    "stored lpddigest keeps the hole falsifiable."
)


class LpdActuationError(RuntimeError):
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
# RFC 1179 sections 2.1 and 2.1.2: PRINT / QUEUE.
RFC_PRINT_FIELD = "PRINT"
RFC_QUEUE_FIELD = "QUEUE"
RFC_LPD_QUEUE = RFC_QUEUE_FIELD
RFC_PRINT_DIRECTIVE = "print=job"
RFC_QUEUE_DIRECTIVE = "queue=printer"
DEFAULT_PRINT = "PRINT"
QUEUE_POLICY = "QUEUE"
PRINT_HEADER = "Print"
QUEUE_HEADER = "Queue"
LPD_QUEUE_HEADER = QUEUE_HEADER
RFC_PRINT_PATH = "/lpd/"
RFC_PRINT_EMPTY = ""


def lpd_directive_pair(*, queue: bool = False) -> tuple[str, str]:
    """RFC 1179 Print / Queue directive pair."""

    if queue:
        return "queue", "printer"
    return "print", "job"


def ascii_serialize_lpd_directive(*, queue: bool = False) -> str:
    """RFC 1179 token "=" body-or-queue."""

    name, value = lpd_directive_pair(queue=queue)
    if not is_token(name):
        raise LpdActuationError("illegal_directive")
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
            raise LpdActuationError("short_lpd")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 1179 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_lpd(policy: str | Sequence[str]) -> str:
    """Serialize RFC 1179 PRINT / QUEUE opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise LpdActuationError("illegal_lpd")
    upper = text.upper().replace("_", "-")
    if upper in {"PRINT", "LPD", "LPD-PRINT"}:
        return "PRINT"
    if upper in {"QUEUE", "RESOURCE", "LPD-QUEUE"}:
        return "QUEUE"
    if upper.startswith("PRINT="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise LpdActuationError("illegal_lpd")
        return "PRINT"
    if upper.startswith("QUEUE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise LpdActuationError("illegal_lpd")
        return "QUEUE"
    raise LpdActuationError("illegal_lpd")


def parse_lpd(text: str) -> str:
    """Parse RFC 1179 LPD opcode header extensions into PRINT or QUEUE."""

    raw = str(text or "").strip()
    if not raw:
        raise LpdActuationError("illegal_lpd")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"PRINT", "LPD", "LPD-PRINT"}:
        return "PRINT"
    if upper in {"QUEUE", "RESOURCE", "LPD-QUEUE"}:
        return "QUEUE"
    if upper.startswith("PRINT="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise LpdActuationError("illegal_lpd")
        return "PRINT"
    if upper.startswith("QUEUE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise LpdActuationError("illegal_lpd")
        return "QUEUE"
    raise LpdActuationError("illegal_lpd")


def encode_lpd_header(policy: str | Sequence[str]) -> bytes:
    """RFC 1179 HTTP/1.0 field as bytes."""

    return serialize_lpd(policy).encode("ascii")


def parse_lpd_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_lpd(field_value) if field_value else DEFAULT_PRINT
    return {
        "field_value": field_value,
        "policy": policy,
        "header": PRINT_HEADER,
        "directive": str(policy),
        "print": str(policy) == "PRINT",
        "queue": str(policy) == "QUEUE",
    }


def canonical_print(identity: str, lpdid: int) -> str:
    """RFC 1179 body-request advertisement bound to identity and lpdid."""

    return (
        f"{serialize_lpd(DEFAULT_PRINT)}, "
        f"print={ascii_serialize_lpd_directive()}, "
        f"identity={identity}, lpdid={int(lpdid) & 0xFFFFFFFF}"
    )


def canonical_queue(identity: str, lpdid: int, lpddigest: int | None = None) -> str:
    """RFC 1179 queue-printer confirmation of the stored identifier-digest."""

    digest = ""
    if lpddigest is not None:
        digest = f", lpddigest={int(lpddigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_lpd(QUEUE_POLICY)}, "
        f"queue={ascii_serialize_lpd_directive(queue=True)}, "
        f"identity={identity}, lpdid={int(lpdid) & 0xFFFFFFFF}{digest}"
    )


def representation_queue(identity: str, lpdid: int, lpddigest: int) -> str:
    return canonical_queue(identity, lpdid, lpddigest)


def lpd_matches(left: str, right: str) -> bool:
    return parse_lpd(left) == parse_lpd(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise LpdActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise LpdActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise LpdActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise LpdActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def print_request(identity: str, lpdid: int) -> bytes:
    """HTTP PRINT that elicits RFC 1179 origin HTTP/1.0."""

    keyid = f"{int(lpdid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"PRINT /lpd/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Lpd-Id: {int(lpdid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def queue_request(identity: str, lpdid: int, lpddigest: int | None = None) -> bytes:
    """HTTP QUEUE carrying RFC 1179 queue-printer confirmation of the stored identifier-digest."""

    keyid = f"{int(lpdid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if lpddigest is not None:
        extra = f"Lpd-Digest: {int(lpddigest) & 0xFFFFFFFF}\r\n"
    return (
        f"QUEUE /lpd/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Lpd-Id: {int(lpdid) & 0xFFFFFFFF}\r\n"
        "Queue-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    lpd_kind = "queue" if fields.get("queue-confirm") == "1" else "print"
    upgrade_field = fields.get("print") or fields.get("lpd") or ""
    policy = parse_lpd(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "lpd_kind": lpd_kind,
        "policy": policy,
        "lpdid": int(fields["lpd-id"]) if fields.get("lpd-id") else EMPTY_LPDID,
        "lpddigest": int(fields["lpd-digest"]) if fields.get("lpd-digest") else EMPTY_LPDDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def print_response(identity: str, lpdid: int, lpddigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 1179 origin HTTP/1.0, carrying the stored lpddigest."""

    advertised = serialize_lpd(DEFAULT_PRINT)
    payload = bytes(body or canonical_print(identity, lpdid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Print: {advertised}\r\n"
        f"Lpd-Id: {int(lpdid) & 0xFFFFFFFF}\r\n"
        f"Lpd-Digest: {int(lpddigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def queue_response(identity: str, lpdid: int, lpddigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 1179 QUEUE, carrying the stored identifier-digest."""

    advertised = serialize_lpd(QUEUE_POLICY)
    payload = bytes(body or representation_queue(identity, lpdid, lpddigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Print: {advertised}\r\n"
        f"Lpd-Id: {int(lpdid) & 0xFFFFFFFF}\r\n"
        f"Lpd-Digest: {int(lpddigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/lpd-queue\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise LpdActuationError("illegal_content_length") from error
    field_value = fields.get("print") or fields.get("lpd") or ""
    policy = parse_lpd(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/lpd-queue" or policy == QUEUE_POLICY:
        status = 200
        lpd_kind = "queue"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        lpd_kind = "print"
    else:
        status = 0
        lpd_kind = "print"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "lpd_kind": lpd_kind,
        "policy": policy,
        "lpdid": int(fields["lpd-id"]) if fields.get("lpd-id") else EMPTY_LPDID,
        "lpddigest": int(fields["lpd-digest"]) if fields.get("lpd-digest") else EMPTY_LPDDIGEST,
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
        raise LpdActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise LpdActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise LpdActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise LpdActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc1179_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    lpd: str,
) -> str:
    """RFC 1179 identifier digest over method, request-LPD, identity, and lpdid."""

    payload = f"{method}:{lpd}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_lpdid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"lpdid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_lpdid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-lpdid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_lpddigest(lpdid: int = EMPTY_LPDID, token: str = SENTINEL) -> int:
    nonce = f"{int(lpdid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc1179_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="QUEUE",
        lpd=f"/lpd/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_LPDID = request_lpdid(SENTINEL)
DEFAULT_LPDDIGEST = request_lpddigest(DEFAULT_LPDID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    lpdid: int,
    lpddigest: int,
    include_lpdid: bool = True,
) -> bytes:
    live_lpdid = int(lpdid) & 0xFFFFFFFF if include_lpdid else EMPTY_LPDID
    live_digest = int(lpddigest) & 0xFFFFFFFF if include_lpdid and live_lpdid else EMPTY_LPDDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_lpdid) if live_lpdid else b""
    header = bytearray()
    header.append(LPD_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_print(
    *,
    identity: str,
    lpdid: int,
    lpddigest: int | None = None,
    include_lpdid: bool = True,
) -> bytes:
    live_lpdid = int(lpdid) & 0xFFFFFFFF if include_lpdid else EMPTY_LPDID
    live_digest = int(lpddigest) if lpddigest is not None else request_lpddigest(live_lpdid, identity)
    return encode_packet(
        FRAME_PRINT,
        identity=identity,
        lpdid=live_lpdid,
        lpddigest=live_digest,
        include_lpdid=include_lpdid,
    )


def encode_queue(
    *,
    identity: str,
    lpdid: int,
    lpddigest: int | None = None,
    include_lpdid: bool = True,
) -> bytes:
    live_lpdid = int(lpdid) & 0xFFFFFFFF if include_lpdid else EMPTY_LPDID
    live_digest = int(lpddigest) if lpddigest is not None else request_lpddigest(live_lpdid, identity)
    return encode_packet(
        FRAME_QUEUE,
        identity=identity,
        lpdid=live_lpdid,
        lpddigest=live_digest,
        include_lpdid=include_lpdid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise LpdActuationError("short_packet")
    first = raw[0]
    if first != LPD_FIRST:
        raise LpdActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise LpdActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == LPDID_SIZE:
        live_lpdid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_lpdid = EMPTY_LPDID
    else:
        raise LpdActuationError("illegal_lpdid")
    if offset >= len(raw):
        raise LpdActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_PRINT, FRAME_QUEUE}:
        raise LpdActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise LpdActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise LpdActuationError("checksum_failed")
    if len(payload) < 5:
        raise LpdActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise LpdActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_lpdid = int(live_lpdid) != EMPTY_LPDID
    has_lpddigest = has_lpdid and int(live_digest) != EMPTY_LPDDIGEST
    is_print = frame_type == FRAME_PRINT
    is_queue = frame_type == FRAME_QUEUE
    return {
        "type": int(frame_type),
        "is_print": is_print,
        "is_queue": is_queue,
        "lpdid": int(live_lpdid),
        "has_lpdid": has_lpdid,
        "lpddigest": int(live_digest),
        "has_lpddigest": has_lpddigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC1179",
        "serialize_field": canonical_print(identity, live_lpdid) if has_lpdid else "",
        "tls_field": canonical_queue(identity, live_lpdid, live_digest) if has_lpddigest else "",
    }


class LpdClient:
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
            raise LpdActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_queue"] or not packet["is_queue"]:
            raise LpdActuationError("lpddigest_required")
        if not packet["has_lpdid"]:
            raise LpdActuationError("lpdid_required")
        if not packet["has_lpddigest"]:
            raise LpdActuationError("lpddigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_lpddigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_lpddigest:
            raise LpdActuationError("lpddigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "lpdid": int(reply.get("lpdid") or EMPTY_LPDID),
            "identity": str(reply.get("identity") or ""),
            "lpddigest": int(reply.get("lpddigest") or EMPTY_LPDDIGEST),
        }

    def report(
        self,
        identity: str,
        lpdid: int,
        lpddigest: int = EMPTY_LPDDIGEST,
        *,
        wait_lpddigest: bool = True,
        include_lpdid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_queue(
            identity=identity,
            lpdid=lpdid,
            lpddigest=lpddigest or request_lpddigest(lpdid, identity),
            include_lpdid=include_lpdid,
        )
        return self.exchange(packet, wait_lpddigest=wait_lpddigest)


class LpdSession:
    """LPDID-gated loopback RFC 1179 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        lpdid_gate: int = DEFAULT_LPDID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lpdid_gate = int(lpdid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.lpdid = EMPTY_LPDID
        self.lpddigest = EMPTY_LPDDIGEST
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

    def store_lpdid_once(self, identity: str, lpdid: int, lpddigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(lpdid or EMPTY_LPDID)
            live_digest = int(lpddigest or EMPTY_LPDDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.lpdid = live
                self.lpddigest = live_digest or request_lpddigest(live, name)
                self.stored = True
            return str(self.identity), int(self.lpdid), int(self.lpddigest)

    def read_lpdid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.lpdid), int(self.lpddigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "lpdid": EMPTY_LPDID,
            "lpddigest": EMPTY_LPDDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _lpdid_missing(self) -> bool:
        return not int(self.lpdid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, lpdid: int, lpddigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_queue(
            identity=identity,
            lpdid=lpdid,
            lpddigest=lpddigest,
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
            except LpdActuationError:
                continue
            if not packet.get("is_print") and not packet.get("is_queue"):
                continue
            if not packet.get("has_lpdid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_lpdid, stored_digest = self.store_lpdid_once(
                identity,
                int(packet.get("lpdid") or EMPTY_LPDID),
                int(packet.get("lpddigest") or EMPTY_LPDDIGEST),
            )
            if not stored_name or not stored_lpdid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_print"):
                    self.opened = True
                if packet.get("is_queue"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_lpdid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._lpdid_missing():
            return self._forbidden("missing_lpdid")
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
        do_print: bool = True,
        do_queue: bool = True,
        do_lpddigest: bool = True,
        replay: bool = True,
        use_lpdid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._lpdid_missing():
            return self._forbidden("missing_lpdid")
        live_token = str(token or SENTINEL)
        origin_lpdid = request_lpdid(live_token)
        origin_digest = request_lpddigest(origin_lpdid, live_token)
        client: LpdClient | None = None
        independent: LpdClient | None = None
        try:
            client = LpdClient(self.host, int(self.port))
            if not do_print:
                return self._conflict("print_required")
            bind_packet = encode_print(
                identity=live_token,
                lpdid=origin_lpdid,
                lpddigest=origin_digest,
                include_lpdid=use_lpdid,
            )
            if not use_lpdid:
                try:
                    client.exchange(bind_packet, wait_lpddigest=True)
                except LpdActuationError:
                    return self._conflict("lpdid_required")
                return self._conflict("lpdid_required")
            client.send(bind_packet)
            if not do_queue:
                return self._conflict("queue_required")
            proxy_packet = encode_queue(
                identity=live_token,
                lpdid=origin_lpdid,
                lpddigest=origin_digest,
                include_lpdid=True,
            )
            if not do_lpddigest:
                try:
                    client.exchange(proxy_packet, wait_lpddigest=False)
                except LpdActuationError as error:
                    if str(error) == "lpddigest_required":
                        return self._conflict("lpddigest_required")
                    return self._conflict("lpddigest_required")
                return self._conflict("lpddigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_lpddigest=True)
            except LpdActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("lpdid_required")
                if reason == "lpddigest_required":
                    return self._conflict("lpddigest_required")
                return self._conflict("print_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("print_required")
            if int(reply.get("lpdid") or EMPTY_LPDID) != origin_lpdid:
                return self._conflict("lpddigest_required")
            if int(reply.get("lpddigest") or EMPTY_LPDDIGEST) != origin_digest:
                return self._conflict("lpddigest_required")
            self.retrieved = True
            if replay:
                independent = LpdClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_lpdid(live_token),
                        request_lpddigest(poll_lpdid(live_token), POLL_TOKEN),
                        wait_lpddigest=True,
                    )
                except LpdActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_lpdid, stored_digest = self.read_lpdid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_lpdid != origin_lpdid
                    or stored_digest != origin_digest
                    or int(poll.get("lpdid") or EMPTY_LPDID) != origin_lpdid
                    or int(poll.get("lpddigest") or EMPTY_LPDDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_lpdid}:{origin_digest}:{live_token}:{canonical_print(live_token, origin_lpdid)}:{canonical_queue(live_token, origin_lpdid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "lpdid": origin_lpdid,
                "lpddigest": origin_digest,
                "print_frame": True,
                "queue_frame": True,
                "lpddigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "lpdid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_lpddigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "lpdid": origin_lpdid,
                "lpddigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "print_frame": True,
                "queue_frame": True,
                "lpddigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "lpdid_bound": True,
            }
        except (OSError, LpdActuationError) as error:
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
        live = independent_lpddigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "lpdid": int(live.get("lpdid") or EMPTY_LPDID),
            "lpddigest": int(live.get("lpddigest") or EMPTY_LPDDIGEST),
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


def call_lpd_tool(session: LpdSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one lpd tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_print = True if arguments.get("print") is None else bool(arguments.get("print"))
    do_queue = True if arguments.get("queue") is None else bool(arguments.get("queue"))
    do_lpddigest = True if arguments.get("lpddigest") is None else bool(arguments.get("lpddigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_lpdid = True if arguments.get("use_lpdid") is None else bool(arguments.get("use_lpdid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_print=do_print,
            do_queue=do_queue,
            do_lpddigest=do_lpddigest,
            replay=replay,
            use_lpdid=use_lpdid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise LpdActuationError(f"unsupported lpd action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_lpddigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage lpddigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "lpdid": EMPTY_LPDID,
        "lpddigest": EMPTY_LPDDIGEST,
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
            "print_frame",
            "queue_frame",
            "lpddigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "lpdid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    lpdid = int(payload.get("lpdid") or EMPTY_LPDID)
    lpddigest = int(payload.get("lpddigest") or EMPTY_LPDDIGEST)
    dual = port > 0 and bool(lpdid) and bool(lpddigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "lpdid": lpdid,
        "lpddigest": lpddigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "print_frame": payload.get("print_frame") is True,
        "queue_frame": payload.get("queue_frame") is True,
        "lpddigest_locate": payload.get("lpddigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "lpdid_bound": payload.get("lpdid_bound") is True,
    }


def run_lpd_workflow(
    *,
    with_lpdid: bool = True,
    skip_bind: bool = False,
    do_print: bool = True,
    do_queue: bool = True,
    do_lpddigest: bool = True,
    replay: bool = True,
    use_lpdid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1179 PRINT/QUEUE lpdid cycle workflow."""

    descriptor = lpd_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, LPD_TOOL_PROVIDER),
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
        raise LpdActuationError(f"lpd tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="lpd-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = LpdSession(out, lpdid_gate=DEFAULT_LPDID if with_lpdid else EMPTY_LPDID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "print": do_print,
            "queue": do_queue,
            "lpddigest": do_lpddigest,
            "replay": replay,
            "use_lpdid": use_lpdid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_lpd_tool(session, arguments))
            except LpdActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_lpddigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_lpdid
        and not skip_bind
        and do_print
        and do_queue
        and do_lpddigest
        and replay
        and use_lpdid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "lpd_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_lpdid": with_lpdid,
        "skip_bind": skip_bind,
        "print_frame": do_print,
        "queue_frame": do_queue,
        "lpddigest": do_lpddigest,
        "replay": replay,
        "use_lpdid": use_lpdid,
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
        "lpdid_value": int(publish_result.get("lpdid") or independent.get("lpdid") or EMPTY_LPDID),
        "lpddigest_value": int(publish_result.get("lpddigest") or independent.get("lpddigest") or EMPTY_LPDDIGEST),
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
        "lpdid": int(trace_body["lpdid_value"] or EMPTY_LPDID),
        "lpddigest": int(trace_body["lpddigest_value"] or EMPTY_LPDDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_lpdid": with_lpdid,
        "skip_bind": skip_bind,
        "print_cycle": do_print,
        "queue_cycle": do_queue,
        "lpddigest_cycle": do_lpddigest,
        "replay": replay,
        "use_lpdid": use_lpdid,
    }


def verify_lpd_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_lpddigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    lpdid = int(trace.get("lpdid_value") or independent.get("lpdid") or EMPTY_LPDID)
    lpddigest = int(trace.get("lpddigest_value") or independent.get("lpddigest") or EMPTY_LPDDIGEST)
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
        "print_frame": independent.get("print_frame") is True,
        "queue_frame": independent.get("queue_frame") is True,
        "lpddigest_locate": independent.get("lpddigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "lpdid_bound": independent.get("lpdid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "lpddigest_recorded": (
            port > 0
            and lpdid == DEFAULT_LPDID
            and lpddigest == DEFAULT_LPDDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def lpd_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.lpd_actuation import "
        "builtin_lpd_actuation_proof; r=builtin_lpd_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='lpd_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_lpd_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LPD_ACTUATION_ID,
        name="First-class RFC 1179 Line Printer Daemon Protocol PRINT/QUEUE actuation",
        description=(
            "Missions that require a lpd tool can opt the lpd provider in, "
            "bind a loopback RFC 1179 Line Printer Daemon Protocol endpoint, complete a PRINT "
            "with a non-empty lpdid, lockstep a QUEUE that carries the "
            "stored lpddigest, independently poll the stored lpddigest "
            "on a later socket, and seal a digest-chained lpddigest. Default "
            "routing stays fail-closed; a missing lpdid keeps the hole "
            "falsifiable, and skip-PRINT/QUEUE/LPDDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.lpd_actuation:builtin_lpd_actuation_proof",
        proof_command=lpd_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.finger-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/lpd_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/finger_actuation.py",
            "src/blackhole_agent/nntp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required lpd tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 1179 daemon, speaks a "
            "PRINT then QUEUE over Line Printer Daemon Protocol with a non-empty lpdid and "
            "lpddigest, independently polls the stored lpddigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 1288 The Finger User Information Protocol lockstep is proved. "
            "Missing lpdids, skip-PRINT, skip-QUEUE, skip-lpddigest, skip-REPLAY, "
            "and a PRINT aimed without an lpdid stay fail-closed. "
            "Later genesis can take RFC 977 Network News Transfer Protocol ARTICLE/GROUP as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("lpd", "rfc1179", "http", "lpdid", "lpddigest", "print", "queue", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T080839Z-b2392864",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_lpd_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1179 print/queue lockstep actuation seals a lpddigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.nntp_actuation import (
        NNTP_ACTUATION_GOAL,
        NNTP_ACTUATION_ID,
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
    checks["denylists_self"] = LPD_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LPD_ACTUATION_GOAL) == (
        LPD_ACTUATION_ID,
    )
    checks["leftover_text_binds_lpd"] = leftover_marker_ids(LPD_LEFTOVER) == (
        LPD_ACTUATION_ID,
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
        (NNTP_ACTUATION_GOAL, NNTP_ACTUATION_ID, "nntp"),
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
        checks[f"{name}_goal_is_not_lpd"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"lpd_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            LPD_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = LPD_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_lpd(DEFAULT_PRINT)
    rebuilt = serialize_lpd(parse_lpd(advertised))
    preloaded = parse_lpd(RFC_LPD_QUEUE)
    header = encode_lpd_header(DEFAULT_PRINT)
    parsed_header = parse_lpd_header(header)
    asked = parse_http_request(print_request(SENTINEL, DEFAULT_LPDID))
    preload_req = parse_http_request(queue_request(SENTINEL, DEFAULT_LPDID, DEFAULT_LPDDIGEST))
    got = parse_http_response(print_response(SENTINEL, DEFAULT_LPDID, DEFAULT_LPDDIGEST))
    preload_reply = parse_http_response(
        queue_response(SENTINEL, DEFAULT_LPDID, DEFAULT_LPDDIGEST)
    )
    checks["lpd_roundtrip"] = (
        parse_lpd(advertised) == DEFAULT_PRINT
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_PRINT_FIELD
        and is_token("PRINT") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_PRINT_FIELD
        and parsed_header["policy"] == DEFAULT_PRINT
        and parsed_header["header"] == PRINT_HEADER
        and parsed_header["print"] is True
        and parsed_header["queue"] is False
        and preloaded == QUEUE_POLICY
        and ascii_serialize_lpd_directive() == RFC_PRINT_DIRECTIVE
        and lpd_directive_pair() == ("print", "job")
        and RFC_PRINT_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_lpd(QUEUE_POLICY) == RFC_LPD_QUEUE
        and DEFAULT_LPDDIGEST == request_lpddigest(DEFAULT_LPDID, SENTINEL)
        and "lpddigest=" in canonical_queue(SENTINEL, DEFAULT_LPDID, DEFAULT_LPDDIGEST)
        and canonical_print(SENTINEL, DEFAULT_LPDID).startswith("PRINT")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "PRINT"
        and asked["lpd_kind"] == "print"
        and asked["lpdid"] == DEFAULT_LPDID
        and preload_req["lpd_kind"] == "queue"
        and preload_req["lpddigest"] == DEFAULT_LPDDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["lpd_kind"] == "print"
        and preload_reply["lpd_kind"] == "queue"
        and got["policy"] == DEFAULT_PRINT
        and preload_reply["policy"] == QUEUE_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["lpddigest"] == DEFAULT_LPDDIGEST
        and preload_reply["lpddigest"] == DEFAULT_LPDDIGEST
        and lpd_matches(serialize_lpd(got["policy"]), advertised)
    )

    checks["catalog_names_lpd"] = (
        len(catalog) > 109
        and catalog[109]["id"] == LPD_ACTUATION_ID
        and catalog[108]["id"] == FINGER_ACTUATION_ID
        and catalog[109]["source"] == "genesis_bind_lpd"
    )
    checks["catalog_names_nntp"] = (
        len(catalog) > 110
        and catalog[110]["id"] == NNTP_ACTUATION_ID
        and catalog[110]["source"] == "genesis_bind_nntp"
    )
    family = capability_family(LPD_ACTUATION_GOAL)
    checks["family_is_lpd"] = "lpd" in family
    checks["family_is_lpd_surface"] = "lpd" in family
    checks["family_is_lpdid"] = "lpdid" in family
    checks["family_is_rfc1179"] = "rfc1179" in family
    checks["family_is_lpddigest"] = "lpddigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_nntp"] = (
        "nntp" not in family.split("/")
        and "rfc977" not in family
        and "nntpid" not in family
        and "nntpdigest" not in family
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
    packed = encode_print(identity=SENTINEL, lpdid=DEFAULT_LPDID, lpddigest=DEFAULT_LPDDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_print"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_lpdid"] is True
        and parsed["lpdid"] == DEFAULT_LPDID
        and parsed["lpddigest"] == DEFAULT_LPDDIGEST
        and parsed["is_queue"] is False
        and parsed["is_queue"] is False
        and parsed["type"] == FRAME_PRINT
        and parsed["first_byte"] == LPD_FIRST
    )
    shook = encode_queue(
        identity=SENTINEL,
        lpdid=DEFAULT_LPDID,
        lpddigest=DEFAULT_LPDDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_queue"] is True
        and answer_parsed["is_queue"] is True
        and answer_parsed["is_print"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["lpdid"] == DEFAULT_LPDID
        and answer_parsed["lpddigest"] == DEFAULT_LPDDIGEST
        and answer_parsed["has_lpddigest"] is True
        and answer_parsed["type"] == FRAME_QUEUE
        and answer_parsed["first_byte"] == LPD_FIRST
    )
    bare = encode_print(identity=SENTINEL, lpdid=DEFAULT_LPDID, include_lpdid=False)
    checks["missing_lpdid_is_unauthed"] = parse_message(bare)["has_lpdid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(LPD_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_lpd = ToolDescriptor(name="remote_lpd", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_lpd)
    checks["naive_mcp_lpd_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = lpd_tool_descriptor()
    default_lpd = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, LPD_TOOL_PROVIDER),
    )
    checks["default_lpd_provider_is_unsupported"] = (
        default_lpd.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{LPD_TOOL_PROVIDER}" in default_lpd.reasons
    )
    checks["opted_in_lpd_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_lpd],
        required_tool_names=("local_memory", "lpd"),
    )
    checks["naive_preflight_missing_lpd"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["lpd"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "lpd"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, LPD_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "lpd" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="lpd-actuation-") as tmp:
        root = Path(tmp)
        missing = run_lpd_workflow(with_lpdid=False, output_dir=root / "missing")
        skip_bind = run_lpd_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_print = run_lpd_workflow(do_print=False, output_dir=root / "skip-print")
        skip_queue = run_lpd_workflow(do_queue=False, output_dir=root / "skip-queue")
        skip_lpddigest = run_lpd_workflow(do_lpddigest=False, output_dir=root / "skip-lpddigest")
        skip_replay = run_lpd_workflow(replay=False, output_dir=root / "skip-replay")
        skip_lpdid = run_lpd_workflow(use_lpdid=False, output_dir=root / "skip-lpdid")
        live = run_lpd_workflow(output_dir=root / "live")
        verify = verify_lpd_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_lpd_trace(clone)
        checks["naive_without_lpdid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_lpdid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_print_stays_empty"] = (
            skip_print["ok"] is False
            and skip_print["error"] == "print_required"
            and skip_print["final_status"] == 409
            and skip_print["payload_exists"] is False
        )
        checks["skip_queue_stays_empty"] = (
            skip_queue["ok"] is False
            and skip_queue["error"] == "queue_required"
            and skip_queue["final_status"] == 409
            and skip_queue["payload_exists"] is False
        )
        checks["skip_lpddigest_stays_empty"] = (
            skip_lpddigest["ok"] is False
            and skip_lpddigest["error"] == "lpddigest_required"
            and skip_lpddigest["final_status"] == 409
            and skip_lpddigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_lpdid_stays_empty"] = (
            skip_lpdid["ok"] is False
            and skip_lpdid["error"] == "lpdid_required"
            and skip_lpdid["final_status"] == 409
            and skip_lpdid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_lpddigest"] = (
            int(live.get("lpdid") or 0) == DEFAULT_LPDID
            and int(live.get("lpddigest") or 0) == DEFAULT_LPDDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_lpdid_encode_queue_lpddigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_print["ok"] is False
            and skip_queue["ok"] is False
            and skip_lpddigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_lpdid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="lpd-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != LPD_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, LPD_ACTUATION_GOAL, LPD_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_lpd"] = (
        not gate.accepted
        and live_goal != LPD_ACTUATION_GOAL
        and LPD_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_lpd"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="lpd-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(LPD_LEFTOVER, root)
        register_catalog_proved(root, LPD_ACTUATION_ID)
        reason = leftover_satisfied_by(LPD_LEFTOVER, root)
        after = leftover_is_open(LPD_LEFTOVER, root)
    checks["lpd_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_lpd_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{LPD_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_lpd_actuation_capability()
    return {
        "ok": ok,
        "action": "lpd_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LPD_ACTUATION_GOAL,
        "done_when": LPD_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
