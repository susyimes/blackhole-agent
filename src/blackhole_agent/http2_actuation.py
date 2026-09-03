"""Drive a first-class HTTP/2 tool through RFC 9113 PREFACE/SETTINGS.

Tool routing already fails missions that require ``http2``: hosted http2
endpoints stay on the unsupported MCP provider, and no first-party http2
provider is executable. Unbound therefore cannot speak a PREFACE,
lockstep a SETTINGS settingsid handshake over HTTP HTTP/2 SETTINGSID,
independently poll the stored connection preface, or seal a hpack digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``http2`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9113 daemon
- keep a missing-settingsid client so the http2-settingsid hole stays falsifiable
- refuse SETTINGS until a PREFACE lands with a non-empty settingsid
- independently poll the stored connection preface on a later client socket
- persist a sealed hpack digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9112 HTTP/1.1
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
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    HTTP2_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    http2_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTP2_ACTUATION_ID = "capability.http2-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-H2-OK"
POLL_TOKEN = "BH-H2-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_SETTINGSID = 0
EMPTY_HPACK = 0
H2_FIRST = 0x50  # RFC 9113 connection preface (ASCII 'P')
SETTINGSID_SIZE = 4
HPACK_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_SETTINGS = 0x04  # RFC 9113 SETTINGS
FRAME_PREFACE = 0xFF  # connection preface is not a numbered HTTP/2 frame
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTP2_LEFTOVER = (
    "Later genesis can take RFC 9113 HTTP/2 PREFACE/SETTINGS over a "
    "settingsid-gated hpack digest."
)


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


HTTP2_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTP2_ACTUATION_ID};"
    f"capability_proved:{HTTP2_ACTUATION_ID};"
    "no_skill_route"
)
HTTP2_ACTUATION_GOAL = (
    "Repair rfc9113 http2 preface/settings cycle cannot land over http "
    "http2 settingsid: hosted http2 endpoints remain unsupported so a PREFACE then "
    "SETTINGS settingsid handshake cannot land and a sealed hpack digest "
    "cannot be produced. A missing http2 settingsid stays forbidden; fail-closed "
    "routing never opts the http2 provider in. An independent later poll of the "
    "stored connection preface keeps the hole falsifiable."
)


class Http2ActuationError(RuntimeError):
    """Raised when the HTTP/2 session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


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
        raise Http2ActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise Http2ActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise Http2ActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise Http2ActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


CONNECTION_PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
FLAG_ACK = 0x1
SETTING_HEADER_TABLE_SIZE = 0x1
SETTING_ENABLE_PUSH = 0x2
SETTING_MAX_CONCURRENT_STREAMS = 0x3
SETTING_INITIAL_WINDOW_SIZE = 0x4
SETTING_MAX_FRAME_SIZE = 0x5
SETTING_MAX_HEADER_LIST_SIZE = 0x6

# RFC 7541 Appendix A static table (entries used by this lockstep).
HPACK_STATIC: tuple[tuple[str, str], ...] = (
    (":authority", ""),
    (":method", "GET"),
    (":method", "POST"),
    (":path", "/"),
    (":path", "/index.html"),
    (":scheme", "http"),
    (":scheme", "https"),
    (":status", "200"),
    (":status", "204"),
    (":status", "206"),
    (":status", "304"),
    (":status", "400"),
    (":status", "404"),
    (":status", "500"),
    ("accept-charset", ""),
    ("accept-encoding", "gzip, deflate"),
    ("accept-language", ""),
    ("accept-ranges", ""),
    ("accept", ""),
    ("access-control-allow-origin", ""),
    ("age", ""),
    ("allow", ""),
    ("authorization", ""),
    ("cache-control", ""),
    ("content-disposition", ""),
    ("content-encoding", ""),
    ("content-language", ""),
    ("content-length", ""),
    ("content-location", ""),
    ("content-range", ""),
    ("content-type", ""),
)


def _static_index(name: str, value: str | None = None) -> int:
    needle_name = str(name or "").lower()
    if value is None:
        for index, (static_name, _static_value) in enumerate(HPACK_STATIC, start=1):
            if static_name == needle_name:
                return index
        return 0
    needle_value = str(value or "")
    for index, (static_name, static_value) in enumerate(HPACK_STATIC, start=1):
        if static_name == needle_name and static_value == needle_value:
            return index
    return 0


def hpack_int(value: int, n: int, leading: int = 0) -> bytes:
    """RFC 7541 section 5.1 integer representation."""

    maxv = (1 << n) - 1
    number = int(value)
    if number < 0:
        raise Http2ActuationError("illegal_hpack_int")
    if number < maxv:
        return bytes([leading | number])
    out = bytearray([leading | maxv])
    remain = number - maxv
    while remain >= 128:
        out.append((remain & 0x7F) | 0x80)
        remain >>= 7
    out.append(remain)
    return bytes(out)


def read_hpack_int(data: bytes, offset: int, n: int) -> tuple[int, int]:
    raw = bytes(data or b"")
    if offset >= len(raw):
        raise Http2ActuationError("short_hpack")
    mask = (1 << n) - 1
    value = raw[offset] & mask
    offset += 1
    if value < mask:
        return value, offset
    shift = 0
    while True:
        if offset >= len(raw):
            raise Http2ActuationError("short_hpack")
        byte = raw[offset]
        offset += 1
        value += (byte & 0x7F) << shift
        shift += 7
        if byte & 0x80 == 0:
            return value, offset
        if shift > 63:
            raise Http2ActuationError("hpack_int_overflow")


def hpack_string(text: str) -> bytes:
    """RFC 7541 section 5.2 string literal without Huffman coding."""

    raw = str(text or "").encode("ascii")
    return hpack_int(len(raw), 7, leading=0) + raw


def read_hpack_string(data: bytes, offset: int) -> tuple[str, int]:
    raw = bytes(data or b"")
    if offset >= len(raw):
        raise Http2ActuationError("short_hpack")
    if raw[offset] & 0x80:
        raise Http2ActuationError("huffman_unsupported")
    length, offset = read_hpack_int(raw, offset, 7)
    body = raw[offset : offset + length]
    if len(body) != length:
        raise Http2ActuationError("short_hpack")
    return body.decode("ascii", errors="strict"), offset + length


def hpack_encode(headers: Sequence[tuple[str, str]]) -> bytes:
    """RFC 7541 header block: indexed static entries, else literal without indexing."""

    out = bytearray()
    for name, value in headers:
        field_name = str(name or "").lower()
        field_value = str(value or "")
        full = _static_index(field_name, field_value)
        if full:
            out.extend(hpack_int(full, 7, leading=0x80))
            continue
        name_index = _static_index(field_name)
        if name_index:
            out.extend(hpack_int(name_index, 4, leading=0x00))
            out.extend(hpack_string(field_value))
            continue
        out.append(0x00)
        out.extend(hpack_string(field_name))
        out.extend(hpack_string(field_value))
    return bytes(out)


def hpack_decode(payload: bytes) -> list[tuple[str, str]]:
    """RFC 7541 header-block decoder for indexed and literal-without-indexing rows."""

    headers: list[tuple[str, str]] = []
    offset = 0
    data = bytes(payload or b"")
    while offset < len(data):
        first = data[offset]
        if first & 0x80:
            index, offset = read_hpack_int(data, offset, 7)
            if index <= 0 or index > len(HPACK_STATIC):
                raise Http2ActuationError("illegal_hpack_index")
            headers.append(HPACK_STATIC[index - 1])
            continue
        if first & 0xC0 == 0x40:
            raise Http2ActuationError("incremental_indexing_unsupported")
        if first & 0xE0 == 0x20:
            _size, offset = read_hpack_int(data, offset, 5)
            continue
        index, offset = read_hpack_int(data, offset, 4)
        if index == 0:
            name, offset = read_hpack_string(data, offset)
        elif index <= len(HPACK_STATIC):
            name = HPACK_STATIC[index - 1][0]
        else:
            raise Http2ActuationError("illegal_hpack_index")
        value, offset = read_hpack_string(data, offset)
        headers.append((name, value))
    return headers


def encode_http2_frame(
    payload: bytes,
    *,
    ftype: int,
    flags: int = 0,
    stream_id: int = 0,
) -> bytes:
    """RFC 9113 section 4.1 frame header + payload."""

    body = bytes(payload or b"")
    if len(body) > 0xFFFFFF:
        raise Http2ActuationError("frame_too_large")
    header = struct.pack(">I", len(body))[1:]
    header += bytes([int(ftype) & 0xFF, int(flags) & 0xFF])
    header += struct.pack(">I", int(stream_id) & 0x7FFFFFFF)
    return header + body


def parse_http2_frame(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 9:
        raise Http2ActuationError("short_frame")
    length = int.from_bytes(raw[:3], "big")
    ftype = raw[3]
    flags = raw[4]
    stream_id = struct.unpack(">I", raw[5:9])[0] & 0x7FFFFFFF
    if 9 + length > len(raw):
        raise Http2ActuationError("short_frame")
    payload = raw[9 : 9 + length]
    return {
        "length": int(length),
        "type": int(ftype),
        "flags": int(flags),
        "stream_id": int(stream_id),
        "payload": payload,
        "is_settings": int(ftype) == FRAME_SETTINGS,
        "ack": bool(int(flags) & FLAG_ACK) and int(ftype) == FRAME_SETTINGS,
    }


def encode_settings_payload(params: Sequence[tuple[int, int]]) -> bytes:
    """RFC 9113 section 6.5.1 SETTINGS parameter encoding."""

    parts: list[bytes] = []
    for ident, value in params:
        parts.append(struct.pack("!HI", int(ident) & 0xFFFF, int(value) & 0xFFFFFFFF))
    return b"".join(parts)


def decode_settings_payload(payload: bytes) -> list[tuple[int, int]]:
    raw = bytes(payload or b"")
    if len(raw) % 6 != 0:
        raise Http2ActuationError("illegal_settings")
    params: list[tuple[int, int]] = []
    for offset in range(0, len(raw), 6):
        ident, value = struct.unpack("!HI", raw[offset : offset + 6])
        params.append((int(ident), int(value)))
    return params


def connection_preface() -> bytes:
    """RFC 9113 section 3.4 client connection preface."""

    return CONNECTION_PREFACE


def parse_connection_preface(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if raw != CONNECTION_PREFACE:
        raise Http2ActuationError("illegal_preface")
    return {
        "kind": "preface",
        "preface": CONNECTION_PREFACE,
        "length": len(CONNECTION_PREFACE),
        "http2_version": "HTTP/2.0",
    }


def http2_header_list(identity: str, settingsid: int) -> tuple[tuple[str, str], ...]:
    keyid = f"{int(settingsid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        (":method", "POST"),
        (":scheme", "https"),
        (":authority", host),
        (":path", f"/http2/{keyid}"),
        ("content-type", "application/octet-stream"),
    )


def http2_settings_params(identity: str, settingsid: int) -> tuple[tuple[int, int], ...]:
    headers = hpack_encode(http2_header_list(identity, settingsid))
    return (
        (SETTING_HEADER_TABLE_SIZE, 4096),
        (SETTING_ENABLE_PUSH, 0),
        (SETTING_MAX_CONCURRENT_STREAMS, 100),
        (SETTING_INITIAL_WINDOW_SIZE, 65535),
        (SETTING_MAX_FRAME_SIZE, 16384),
        (SETTING_MAX_HEADER_LIST_SIZE, len(headers) + 1024),
    )


def http2_settings_frame(identity: str, settingsid: int, *, ack: bool = False) -> bytes:
    payload = b"" if ack else encode_settings_payload(http2_settings_params(identity, settingsid))
    flags = FLAG_ACK if ack else 0
    return encode_http2_frame(payload, ftype=FRAME_SETTINGS, flags=flags, stream_id=0)


def http2_preface_block(identity: str, settingsid: int) -> bytes:
    """Client connection preface followed by the first SETTINGS frame."""

    return connection_preface() + http2_settings_frame(identity, settingsid)


def request_settingsid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"settingsid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_settingsid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-settingsid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_hpack(settingsid: int = EMPTY_SETTINGSID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        hpack_encode(http2_header_list(token or SENTINEL, int(settingsid) & 0xFFFFFFFF))
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_SETTINGSID = request_settingsid(SENTINEL)
DEFAULT_HPACK = request_hpack(DEFAULT_SETTINGSID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    settingsid: int,
    hpack: int,
    include_settingsid: bool = True,
) -> bytes:
    live_settingsid = int(settingsid) & 0xFFFFFFFF if include_settingsid else EMPTY_SETTINGSID
    live_hpack = int(hpack) & 0xFFFFFFFF if include_settingsid and live_settingsid else EMPTY_HPACK
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_hpack, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_settingsid) if live_settingsid else b""
    header = bytearray()
    header.append(H2_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_preface(
    *,
    identity: str,
    settingsid: int,
    hpack: int | None = None,
    include_settingsid: bool = True,
) -> bytes:
    live_settingsid = int(settingsid) & 0xFFFFFFFF if include_settingsid else EMPTY_SETTINGSID
    live_hpack = int(hpack) if hpack is not None else request_hpack(live_settingsid, identity)
    return encode_packet(
        FRAME_PREFACE,
        identity=identity,
        settingsid=live_settingsid,
        hpack=live_hpack,
        include_settingsid=include_settingsid,
    )


def encode_settings(
    *,
    identity: str,
    settingsid: int,
    hpack: int | None = None,
    include_settingsid: bool = True,
) -> bytes:
    live_settingsid = int(settingsid) & 0xFFFFFFFF if include_settingsid else EMPTY_SETTINGSID
    live_hpack = int(hpack) if hpack is not None else request_hpack(live_settingsid, identity)
    return encode_packet(
        FRAME_SETTINGS,
        identity=identity,
        settingsid=live_settingsid,
        hpack=live_hpack,
        include_settingsid=include_settingsid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise Http2ActuationError("short_packet")
    first = raw[0]
    if first != H2_FIRST:
        raise Http2ActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise Http2ActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == SETTINGSID_SIZE:
        live_settingsid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_settingsid = EMPTY_SETTINGSID
    else:
        raise Http2ActuationError("illegal_settingsid")
    if offset >= len(raw):
        raise Http2ActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_PREFACE, FRAME_SETTINGS}:
        raise Http2ActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise Http2ActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise Http2ActuationError("checksum_failed")
    if len(payload) < 5:
        raise Http2ActuationError("short_packet")
    live_hpack, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise Http2ActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_settingsid = int(live_settingsid) != EMPTY_SETTINGSID
    has_hpack = has_settingsid and int(live_hpack) != EMPTY_HPACK
    is_preface = frame_type == FRAME_PREFACE
    is_settings = frame_type == FRAME_SETTINGS
    return {
        "type": int(frame_type),
        "is_preface": is_preface,
        "is_settings": is_settings,
        "is_response": is_settings,
        "settingsid": int(live_settingsid),
        "has_settingsid": has_settingsid,
        "hpack": int(live_hpack),
        "has_hpack": has_hpack,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http2_version": "HTTP/2.0",
    }


class Http2Client:
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
            raise Http2ActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_settings"] or not packet["is_response"]:
            raise Http2ActuationError("hpack_required")
        if not packet["has_settingsid"]:
            raise Http2ActuationError("settingsid_required")
        if not packet["has_hpack"]:
            raise Http2ActuationError("hpack_required")
        return packet

    def exchange(self, packet: bytes, *, wait_hpack: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_hpack:
            raise Http2ActuationError("hpack_required")
        reply = self._recv()
        return {
            "session": reply,
            "settingsid": int(reply.get("settingsid") or EMPTY_SETTINGSID),
            "identity": str(reply.get("identity") or ""),
            "hpack": int(reply.get("hpack") or EMPTY_HPACK),
        }

    def serialize(
        self,
        identity: str,
        settingsid: int,
        hpack: int = EMPTY_HPACK,
        *,
        wait_hpack: bool = True,
        include_settingsid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_settings(
            identity=identity,
            settingsid=settingsid,
            hpack=hpack or request_hpack(settingsid, identity),
            include_settingsid=include_settingsid,
        )
        return self.exchange(packet, wait_hpack=wait_hpack)


class Http2Session:
    """SETTINGSID-gated loopback RFC 9113 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        settingsid_gate: int = DEFAULT_SETTINGSID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.settingsid_gate = int(settingsid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.settingsid = EMPTY_SETTINGSID
        self.hpack = EMPTY_HPACK
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

    def store_settingsid_once(self, identity: str, settingsid: int, hpack: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(settingsid or EMPTY_SETTINGSID)
            live_hpack = int(hpack or EMPTY_HPACK)
            if not self.identity and name and live:
                self.identity = name
                self.settingsid = live
                self.hpack = live_hpack or request_hpack(live, name)
                self.stored = True
            return str(self.identity), int(self.settingsid), int(self.hpack)

    def read_settingsid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.settingsid), int(self.hpack)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "settingsid": EMPTY_SETTINGSID,
            "hpack": EMPTY_HPACK,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _settingsid_missing(self) -> bool:
        return not int(self.settingsid_gate or 0)

    def _reply_decode(self, peer: tuple[str, int], identity: str, settingsid: int, hpack: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_settings(
            identity=identity,
            settingsid=settingsid,
            hpack=hpack,
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
            except Http2ActuationError:
                continue
            if not packet.get("is_preface") and not packet.get("is_settings"):
                continue
            if not packet.get("has_settingsid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_settingsid, stored_hpack = self.store_settingsid_once(
                identity,
                int(packet.get("settingsid") or EMPTY_SETTINGSID),
                int(packet.get("hpack") or EMPTY_HPACK),
            )
            if not stored_name or not stored_settingsid or not stored_hpack:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_preface"):
                    self.opened = True
                if packet.get("is_settings"):
                    self.handshook = True
                self.retrieved = True
            self._reply_decode(peer, stored_name, stored_settingsid, stored_hpack)

    def bind(self) -> dict[str, Any]:
        if self._settingsid_missing():
            return self._forbidden("missing_settingsid")
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
        do_preface_cycle: bool = True,
        do_settings: bool = True,
        do_hpack: bool = True,
        replay: bool = True,
        use_settingsid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._settingsid_missing():
            return self._forbidden("missing_settingsid")
        live_token = str(token or SENTINEL)
        origin_settingsid = request_settingsid(live_token)
        origin_hpack = request_hpack(origin_settingsid, live_token)
        client: Http2Client | None = None
        independent: Http2Client | None = None
        try:
            client = Http2Client(self.host, int(self.port))
            if not do_preface_cycle:
                return self._conflict("preface_required")
            bind_packet = encode_preface(
                identity=live_token,
                settingsid=origin_settingsid,
                hpack=origin_hpack,
                include_settingsid=use_settingsid,
            )
            if not use_settingsid:
                try:
                    client.exchange(bind_packet, wait_hpack=True)
                except Http2ActuationError:
                    return self._conflict("settingsid_required")
                return self._conflict("settingsid_required")
            client.send(bind_packet)
            if not do_settings:
                return self._conflict("settings_required")
            proxy_packet = encode_settings(
                identity=live_token,
                settingsid=origin_settingsid,
                hpack=origin_hpack,
                include_settingsid=True,
            )
            if not do_hpack:
                try:
                    client.exchange(proxy_packet, wait_hpack=False)
                except Http2ActuationError as error:
                    if str(error) == "hpack_required":
                        return self._conflict("hpack_required")
                    return self._conflict("hpack_required")
                return self._conflict("hpack_required")
            try:
                reply = client.exchange(proxy_packet, wait_hpack=True)
            except Http2ActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("settingsid_required")
                if reason == "hpack_required":
                    return self._conflict("hpack_required")
                return self._conflict("preface_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("preface_required")
            if int(reply.get("settingsid") or EMPTY_SETTINGSID) != origin_settingsid:
                return self._conflict("hpack_required")
            if int(reply.get("hpack") or EMPTY_HPACK) != origin_hpack:
                return self._conflict("hpack_required")
            self.retrieved = True
            if replay:
                independent = Http2Client(self.host, int(self.port))
                try:
                    poll = independent.serialize(
                        POLL_TOKEN,
                        poll_settingsid(live_token),
                        request_hpack(poll_settingsid(live_token), POLL_TOKEN),
                        wait_hpack=True,
                    )
                except Http2ActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_settingsid, stored_hpack = self.read_settingsid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_settingsid != origin_settingsid
                    or stored_hpack != origin_hpack
                    or int(poll.get("settingsid") or EMPTY_SETTINGSID) != origin_settingsid
                    or int(poll.get("hpack") or EMPTY_HPACK) != origin_hpack
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_settingsid}:{origin_hpack}:{live_token}:{hpack_encode(http2_header_list(live_token, origin_settingsid)).hex()}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "settingsid": origin_settingsid,
                "hpack": origin_hpack,
                "preface_frame": True,
                "settings": True,
                "hpack_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "settingsid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_http2_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "settingsid": origin_settingsid,
                "hpack": origin_hpack,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "preface_frame": True,
                "settings": True,
                "hpack_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "settingsid_bound": True,
            }
        except (OSError, Http2ActuationError) as error:
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
        live = independent_http2_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "settingsid": int(live.get("settingsid") or EMPTY_SETTINGSID),
            "hpack": int(live.get("hpack") or EMPTY_HPACK),
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


def call_http2_tool(session: Http2Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one HTTP/2 tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_preface_cycle = True if arguments.get("preface_cycle") is None else bool(arguments.get("preface_cycle"))
    do_settings = True if arguments.get("settings") is None else bool(arguments.get("settings"))
    do_hpack = True if arguments.get("hpack") is None else bool(arguments.get("hpack"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_settingsid = True if arguments.get("use_settingsid") is None else bool(arguments.get("use_settingsid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_preface_cycle=do_preface_cycle,
            do_settings=do_settings,
            do_hpack=do_hpack,
            replay=replay,
            use_settingsid=use_settingsid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise Http2ActuationError(f"unsupported http2 action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_http2_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed HTTP/2 hpack digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "settingsid": EMPTY_SETTINGSID,
        "hpack": EMPTY_HPACK,
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
            "preface_frame",
            "settings",
            "hpack_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "settingsid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    settingsid = int(payload.get("settingsid") or EMPTY_SETTINGSID)
    hpack = int(payload.get("hpack") or EMPTY_HPACK)
    dual = port > 0 and bool(settingsid) and bool(hpack)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "settingsid": settingsid,
        "hpack": hpack,
        "size": int(payload.get("size") or 0),
        "port": port,
        "preface_frame": payload.get("preface_frame") is True,
        "settings": payload.get("settings") is True,
        "hpack_response": payload.get("hpack_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "settingsid_bound": payload.get("settingsid_bound") is True,
    }


def run_http2_workflow(
    *,
    with_settingsid: bool = True,
    skip_bind: bool = False,
    do_preface_cycle: bool = True,
    do_settings: bool = True,
    do_hpack: bool = True,
    replay: bool = True,
    use_settingsid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9113 PREFACE/SETTINGS settingsid cycle workflow."""

    descriptor = http2_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP2_TOOL_PROVIDER),
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
        raise Http2ActuationError(f"http2 tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="http2-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = Http2Session(out, settingsid_gate=DEFAULT_SETTINGSID if with_settingsid else EMPTY_SETTINGSID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "preface_cycle": do_preface_cycle,
            "settings": do_settings,
            "hpack": do_hpack,
            "replay": replay,
            "use_settingsid": use_settingsid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_http2_tool(session, arguments))
            except Http2ActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_http2_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_settingsid
        and not skip_bind
        and do_preface_cycle
        and do_settings
        and do_hpack
        and replay
        and use_settingsid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "http2_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_settingsid": with_settingsid,
        "skip_bind": skip_bind,
        "preface_frame": do_preface_cycle,
        "settings": do_settings,
        "hpack": do_hpack,
        "replay": replay,
        "use_settingsid": use_settingsid,
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
        "settingsid_value": int(publish_result.get("settingsid") or independent.get("settingsid") or EMPTY_SETTINGSID),
        "hpack_value": int(publish_result.get("hpack") or independent.get("hpack") or EMPTY_HPACK),
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
        "settingsid": int(trace_body["settingsid_value"] or EMPTY_SETTINGSID),
        "hpack": int(trace_body["hpack_value"] or EMPTY_HPACK),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_settingsid": with_settingsid,
        "skip_bind": skip_bind,
        "preface_cycle": do_preface_cycle,
        "settings_cycle": do_settings,
        "hpack_cycle": do_hpack,
        "replay": replay,
        "use_settingsid": use_settingsid,
    }


def verify_http2_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed HTTP/2 trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_http2_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    settingsid = int(trace.get("settingsid_value") or independent.get("settingsid") or EMPTY_SETTINGSID)
    hpack = int(trace.get("hpack_value") or independent.get("hpack") or EMPTY_HPACK)
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
        "preface_frame": independent.get("preface_frame") is True,
        "settings": independent.get("settings") is True,
        "hpack_response": independent.get("hpack_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "settingsid_bound": independent.get("settingsid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "hpack_recorded": (
            port > 0
            and settingsid == DEFAULT_SETTINGSID
            and hpack == DEFAULT_HPACK
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def http2_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.http2_actuation import "
        "builtin_http2_actuation_proof; r=builtin_http2_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='http2_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_http2_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTP2_ACTUATION_ID,
        name="First-class RFC 9113 HTTP/2 PREFACE/SETTINGS actuation",
        description=(
            "Missions that require a http2 tool can opt the http2 provider in, "
            "bind a loopback RFC 9113 HTTP/2 origin, complete a PREFACE "
            "with a non-empty settingsid, lockstep a SETTINGS that carries the "
            "stored hpack, independently poll the stored preface "
            "hpack on a later socket, and seal a digest-chained hpack. Default "
            "routing stays fail-closed; a missing settingsid keeps the hole "
            "falsifiable, and skip-PREFACE/SETTINGS/HPACK/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.http2_actuation:builtin_http2_actuation_proof",
        proof_command=http2_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.http11-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/http2_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/httpcache_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required http2 tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9113 daemon, speaks a "
            "PREFACE then SETTINGS over HTTP/2 with a non-empty settingsid and "
            "hpack, independently polls the stored preface hpack on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9112 HTTP/1.1 lockstep is proved. "
            "Missing settingsids, skip-PREFACE, skip-SETTINGS, skip-hpack, skip-REPLAY, "
            "and a PREFACE aimed without a settingsid stay fail-closed. "
            "Later genesis can take RFC 9111 HTTP Caching STORE/REVALIDATE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("http2", "rfc9113", "http", "settingsid", "hpack", "preface", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T094949Z-0f477b07",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_http2_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9113 HTTP/2 lockstep actuation seals a hpack digest."""

    from blackhole_agent.httpcache_actuation import HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID
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

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = HTTP2_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTP2_ACTUATION_GOAL) == (
        HTTP2_ACTUATION_ID,
    )
    checks["leftover_text_binds_http2"] = leftover_marker_ids(HTTP2_LEFTOVER) == (
        HTTP2_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID, "httpcache"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_http2"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"http2_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTP2_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTP2_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    preface = connection_preface()
    parsed_preface = parse_connection_preface(preface)
    headers = http2_header_list(SENTINEL, DEFAULT_SETTINGSID)
    packed_headers = hpack_encode(headers)
    decoded_headers = hpack_decode(packed_headers)
    settings = http2_settings_frame(SENTINEL, DEFAULT_SETTINGSID)
    parsed_settings = parse_http2_frame(settings)
    params = decode_settings_payload(parsed_settings["payload"])
    rebuilt_settings = encode_http2_frame(
        encode_settings_payload(params),
        ftype=FRAME_SETTINGS,
        flags=0,
        stream_id=0,
    )
    checks["connection_preface_roundtrip"] = (
        parsed_preface["kind"] == "preface"
        and parsed_preface["http2_version"] == "HTTP/2.0"
        and hmac.compare_digest(preface, CONNECTION_PREFACE)
        and preface.startswith(b"PRI * HTTP/2.0")
    )
    checks["hpack_header_roundtrip"] = (
        decoded_headers == list(headers)
        and decoded_headers[0] == (":method", "POST")
        and decoded_headers[1] == (":scheme", "https")
        and decoded_headers[3] == (":path", f"/http2/{DEFAULT_SETTINGSID:08x}")
        and DEFAULT_HPACK == request_hpack(DEFAULT_SETTINGSID, SENTINEL)
    )
    checks["settings_frame_roundtrip"] = (
        parsed_settings["is_settings"] is True
        and parsed_settings["ack"] is False
        and parsed_settings["stream_id"] == 0
        and parsed_settings["type"] == FRAME_SETTINGS
        and params[0] == (SETTING_HEADER_TABLE_SIZE, 4096)
        and params[1] == (SETTING_ENABLE_PUSH, 0)
        and hmac.compare_digest(settings, rebuilt_settings)
    )
    checks["catalog_names_http2"] = (
        len(catalog) > 73
        and catalog[73]["id"] == HTTP2_ACTUATION_ID
        and catalog[72]["id"] == HTTP11_ACTUATION_ID
        and catalog[73]["source"] == "genesis_bind_http2"
    )
    checks["catalog_names_httpcache"] = (
        len(catalog) > 74
        and catalog[74]["id"] == HTTPCACHE_ACTUATION_ID
        and catalog[74]["source"] == "genesis_bind_httpcache"
    )
    family = capability_family(HTTP2_ACTUATION_GOAL)
    checks["family_is_http2"] = "http2" in family
    checks["family_is_rfc9113"] = "rfc9113" in family
    checks["family_is_settingsid"] = "settingsid" in family
    checks["family_is_hpack"] = "hpack" in family
    checks["family_is_preface"] = "preface" in family
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
        "dtls" not in family and "rfc6347" not in family and "cookie" not in family and "epoch" not in family
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
    checks["family_is_not_httpcache"] = (
        "httpcache" not in family
        and "rfc9111" not in family
        and "cacheid" not in family
        and "freshness" not in family
        and "validator" not in family
    )
    packed = encode_preface(identity=SENTINEL, settingsid=DEFAULT_SETTINGSID, hpack=DEFAULT_HPACK)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_preface"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_settingsid"] is True
        and parsed["settingsid"] == DEFAULT_SETTINGSID
        and parsed["hpack"] == DEFAULT_HPACK
        and parsed["is_response"] is False
        and parsed["is_settings"] is False
        and parsed["type"] == FRAME_PREFACE
        and parsed["first_byte"] == H2_FIRST
    )
    shook = encode_settings(
        identity=SENTINEL,
        settingsid=DEFAULT_SETTINGSID,
        hpack=DEFAULT_HPACK,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_settings"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_preface"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["settingsid"] == DEFAULT_SETTINGSID
        and answer_parsed["hpack"] == DEFAULT_HPACK
        and answer_parsed["has_hpack"] is True
        and answer_parsed["type"] == FRAME_SETTINGS
        and answer_parsed["first_byte"] == H2_FIRST
    )
    bare = encode_preface(identity=SENTINEL, settingsid=DEFAULT_SETTINGSID, include_settingsid=False)
    checks["missing_settingsid_is_unauthenticated"] = parse_message(bare)["has_settingsid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    http2_signature = semantic_signature(HTTP2_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(http2_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_http2 = ToolDescriptor(name="remote_http2", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_http2)
    checks["naive_mcp_http2_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = http2_tool_descriptor()
    default_http2 = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP2_TOOL_PROVIDER),
    )
    checks["default_http2_provider_is_unsupported"] = (
        default_http2.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTP2_TOOL_PROVIDER}" in default_http2.reasons
    )
    checks["opted_in_http2_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_http2],
        required_tool_names=("local_memory", "http2"),
    )
    checks["naive_preflight_missing_http2"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["http2"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "http2"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP2_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "http2" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="http2-actuation-") as tmp:
        root = Path(tmp)
        missing = run_http2_workflow(with_settingsid=False, output_dir=root / "missing")
        skip_bind = run_http2_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_preface_cycle = run_http2_workflow(do_preface_cycle=False, output_dir=root / "skip-preface-cycle")
        skip_settings = run_http2_workflow(do_settings=False, output_dir=root / "skip-settings")
        skip_hpack = run_http2_workflow(do_hpack=False, output_dir=root / "skip-hpack")
        skip_replay = run_http2_workflow(replay=False, output_dir=root / "skip-replay")
        skip_settingsid = run_http2_workflow(use_settingsid=False, output_dir=root / "skip-settingsid")
        live = run_http2_workflow(output_dir=root / "live")
        verify = verify_http2_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_http2_trace(clone)
        checks["naive_without_settingsid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_settingsid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_preface_cycle_stays_empty"] = (
            skip_preface_cycle["ok"] is False
            and skip_preface_cycle["error"] == "preface_required"
            and skip_preface_cycle["final_status"] == 409
            and skip_preface_cycle["payload_exists"] is False
        )
        checks["skip_settings_stays_empty"] = (
            skip_settings["ok"] is False
            and skip_settings["error"] == "settings_required"
            and skip_settings["final_status"] == 409
            and skip_settings["payload_exists"] is False
        )
        checks["skip_hpack_stays_empty"] = (
            skip_hpack["ok"] is False
            and skip_hpack["error"] == "hpack_required"
            and skip_hpack["final_status"] == 409
            and skip_hpack["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_settingsid_stays_empty"] = (
            skip_settingsid["ok"] is False
            and skip_settingsid["error"] == "settingsid_required"
            and skip_settingsid["final_status"] == 409
            and skip_settingsid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_hpack"] = (
            int(live.get("settingsid") or 0) == DEFAULT_SETTINGSID
            and int(live.get("hpack") or 0) == DEFAULT_HPACK
            and int(live.get("port") or 0) > 0
        )
        checks["token_settingsid_encode_settings_hpack_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_preface_cycle["ok"] is False
            and skip_settings["ok"] is False
            and skip_hpack["ok"] is False
            and skip_replay["ok"] is False
            and skip_settingsid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="http2-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTP2_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_http2"] = (
        live_goal == HTTP2_ACTUATION_GOAL
        and HTTP2_ACTUATION_ID in live_done
        and live_source == "genesis_bind_http2"
    )

    with tempfile.TemporaryDirectory(prefix="http2-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTP2_LEFTOVER, root)
        register_catalog_proved(root, HTTP2_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTP2_LEFTOVER, root)
        after = leftover_is_open(HTTP2_LEFTOVER, root)
    checks["http2_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_http2_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTP2_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_http2_actuation_capability()
    return {
        "ok": ok,
        "action": "http2_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTP2_ACTUATION_GOAL,
        "done_when": HTTP2_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
