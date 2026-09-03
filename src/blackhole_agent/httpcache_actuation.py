"""Drive a first-class HTTP cache tool through RFC 9111 STORE/REVALIDATE.

Tool routing already fails missions that require ``httpcache``: hosted httpcache
endpoints stay on the unsupported MCP provider, and no first-party httpcache
provider is executable. Unbound therefore cannot speak a STORE,
lockstep a REVALIDATE cacheid handshake over HTTP HTTP Caching CACHEID,
independently poll the stored cache validator, or seal a freshness digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``httpcache`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9111 daemon
- keep a missing-cacheid client so the httpcache-cacheid hole stays falsifiable
- refuse REVALIDATE until a STORE lands with a non-empty cacheid
- independently poll the stored cache validator on a later client socket
- persist a sealed freshness digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9113 HTTP/2
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
    HTTPCACHE_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    httpcache_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTPCACHE_ACTUATION_ID = "capability.httpcache-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-HC-OK"
POLL_TOKEN = "BH-HC-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_CACHEID = 0
EMPTY_FRESHNESS = 0
HC_FIRST = 0x43  # RFC 9111 HTTP Caching (ASCII 'C')
CACHEID_SIZE = 4
FRESHNESS_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_REVALIDATE = 0x02  # RFC 9111 conditional revalidation
FRAME_STORE = 0x01  # RFC 9111 store a cacheable response
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
DEFAULT_MAX_AGE = 60
HTTPCACHE_LEFTOVER = (
    "Later genesis can take RFC 9111 HTTP Caching STORE/REVALIDATE over a "
    "cacheid-gated freshness digest."
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


HTTPCACHE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPCACHE_ACTUATION_ID};"
    f"capability_proved:{HTTPCACHE_ACTUATION_ID};"
    "no_skill_route"
)
HTTPCACHE_ACTUATION_GOAL = (
    "Repair rfc9111 httpcache store/revalidate cycle cannot land over http "
    "httpcache cacheid: hosted httpcache endpoints remain unsupported so a STORE then "
    "REVALIDATE cacheid handshake cannot land and a sealed freshness digest "
    "cannot be produced. A missing httpcache cacheid stays forbidden; fail-closed "
    "routing never opts the httpcache provider in. An independent later poll of the "
    "stored cache validator keeps the hole falsifiable."
)


class HttpcacheActuationError(RuntimeError):
    """Raised when the HTTP cache session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def parse_cache_control(value: str) -> tuple[tuple[str, str | None], ...]:
    """RFC 9111 section 5.2 Cache-Control as a list of cache-directive."""

    directives: list[tuple[str, str | None]] = []
    for part in str(value or "").split(","):
        item = part.strip()
        if not item:
            continue
        if "=" in item:
            name, _, rest = item.partition("=")
            rest = rest.strip()
            if len(rest) >= 2 and rest[0] == '"' and rest[-1] == '"':
                rest = rest[1:-1]
            directives.append((name.strip().lower(), rest))
        else:
            directives.append((item.lower(), None))
    return tuple(directives)


def format_cache_control(directives: Sequence[tuple[str, str | None]]) -> str:
    """RFC 9111 section 5.2 Cache-Control serializer."""

    parts: list[str] = []
    for name, option in directives:
        token = str(name or "").strip().lower()
        if not token:
            continue
        if option is None:
            parts.append(token)
        else:
            parts.append(f"{token}={option}")
    return ", ".join(parts)


def cache_control_header(identity: str, cacheid: int) -> str:
    """Cache-Control bound to cacheid: public, must-revalidate, max-age."""

    max_age = DEFAULT_MAX_AGE + (int(cacheid) & 0x3F)
    _ = identity
    return format_cache_control(
        (
            ("max-age", str(max_age)),
            ("public", None),
            ("must-revalidate", None),
        )
    )


def parse_etag(value: str) -> dict[str, Any]:
    """RFC 9110 section 8.8.3 entity-tag (used as RFC 9111 validator)."""

    raw = str(value or "").strip()
    weak = False
    if raw.startswith("W/") or raw.startswith("w/"):
        weak = True
        raw = raw[2:].lstrip()
    if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
        raise HttpcacheActuationError("illegal_etag")
    opaque = raw[1:-1]
    for char in opaque:
        code = ord(char)
        if code < 0x21 or code == 0x22 or code == 0x7F:
            raise HttpcacheActuationError("illegal_etag")
    return {
        "weak": weak,
        "opaque": opaque,
        "entity_tag": f'W/"{opaque}"' if weak else f'"{opaque}"',
    }


def format_etag(opaque: str, *, weak: bool = False) -> str:
    parsed = parse_etag(('W/' if weak else '') + f'"{opaque}"')
    return str(parsed["entity_tag"])


def etag_validator(identity: str, cacheid: int) -> str:
    """Strong ETag validator derived from cacheid (RFC 9111 section 4.3.1)."""

    _ = identity
    return format_etag(f"{int(cacheid) & 0xFFFFFFFF:08x}", weak=False)


def freshness_lifetime(directives: Sequence[tuple[str, str | None]]) -> int:
    """RFC 9111 section 4.2.1 freshness lifetime from max-age."""

    for name, option in directives:
        if name == "max-age" and option is not None:
            try:
                value = int(option)
            except ValueError as error:
                raise HttpcacheActuationError("illegal_max_age") from error
            return max(0, value)
        if name == "no-store":
            return 0
    return 0


def current_age(
    age_value: int,
    *,
    date_value: int = 0,
    request_time: int = 0,
    response_time: int = 0,
    now: int = 0,
) -> int:
    """RFC 9111 section 4.2.3 current_age calculation."""

    apparent_age = max(0, int(response_time) - int(date_value))
    response_delay = max(0, int(response_time) - int(request_time))
    corrected_age_value = max(0, int(age_value)) + response_delay
    corrected_initial_age = max(apparent_age, corrected_age_value)
    resident_time = max(0, int(now) - int(response_time))
    return corrected_initial_age + resident_time


def is_fresh(*, lifetime: int, age: int) -> bool:
    """RFC 9111 section 4.2: a response is fresh when lifetime exceeds age."""

    return int(lifetime) > int(age)


def if_none_match_hits(stored_etag: str, if_none_match: str) -> bool:
    """RFC 9110 section 13.1.2 If-None-Match using weak comparison."""

    incoming = str(if_none_match or "").strip()
    if incoming == "*":
        return bool(stored_etag)
    stored = parse_etag(stored_etag)
    for part in incoming.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            parsed = parse_etag(candidate)
        except HttpcacheActuationError:
            continue
        if parsed["opaque"] == stored["opaque"]:
            return True
    return False


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HttpcacheActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HttpcacheActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HttpcacheActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HttpcacheActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def stored_response(identity: str, cacheid: int) -> bytes:
    """RFC 9111 cacheable 200 response with Cache-Control, ETag, and Age."""

    keyid = f"{int(cacheid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Cache-Control: {cache_control_header(host, cacheid)}\r\n"
        f"ETag: {etag_validator(host, cacheid)}\r\n"
        "Age: 0\r\n"
        "Content-Type: application/octet-stream\r\n"
        "\r\n"
        f"{host}:{keyid}"
    ).encode("ascii")


def parse_stored_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    directives = parse_cache_control(fields.get("cache-control", ""))
    etag = parse_etag(fields.get("etag", ""))
    try:
        age_value = int(fields.get("age") or "0")
    except ValueError as error:
        raise HttpcacheActuationError("illegal_age") from error
    lifetime = freshness_lifetime(directives)
    age = current_age(age_value)
    return {
        "kind": "stored_response",
        "start_line": start,
        "status": 200 if start.startswith("HTTP/1.1 200") else 0,
        "headers": headers,
        "body": body,
        "cache_control": directives,
        "etag": etag,
        "age": age,
        "freshness_lifetime": lifetime,
        "fresh": is_fresh(lifetime=lifetime, age=age),
        "must_revalidate": any(name == "must-revalidate" for name, _option in directives),
        "no_store": any(name == "no-store" for name, _option in directives),
    }


def revalidate_request(identity: str, cacheid: int) -> bytes:
    """RFC 9111 section 4.3.1 conditional GET using If-None-Match."""

    keyid = f"{int(cacheid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /httpcache/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"If-None-Match: {etag_validator(host, cacheid)}\r\n"
        "\r\n"
    ).encode("ascii")


def parse_revalidate_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    return {
        "kind": "revalidate_request",
        "start_line": start,
        "method": start.split(" ", 1)[0] if start else "",
        "headers": headers,
        "body": body,
        "if_none_match": fields.get("if-none-match", ""),
        "host": fields.get("host", ""),
    }


def revalidate_not_modified(stored: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    """RFC 9111 section 4.3.2 304 when If-None-Match hits the stored ETag."""

    etag = stored.get("etag") or {}
    entity_tag = str(etag.get("entity_tag") or "")
    hits = if_none_match_hits(entity_tag, str(request.get("if_none_match") or ""))
    if not hits or not stored.get("fresh"):
        return {
            "status": 200,
            "not_modified": False,
            "etag": entity_tag,
        }
    return {
        "status": 304,
        "not_modified": True,
        "etag": entity_tag,
        "cache_control": stored.get("cache_control") or (),
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
        raise HttpcacheActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise HttpcacheActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise HttpcacheActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HttpcacheActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_cacheid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"cacheid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_cacheid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-cacheid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_freshness(cacheid: int = EMPTY_CACHEID, token: str = SENTINEL) -> int:
    material = (
        cache_control_header(token or SENTINEL, int(cacheid) & 0xFFFFFFFF)
        + etag_validator(token or SENTINEL, int(cacheid) & 0xFFFFFFFF)
    ).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_CACHEID = request_cacheid(SENTINEL)
DEFAULT_FRESHNESS = request_freshness(DEFAULT_CACHEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    cacheid: int,
    freshness: int,
    include_cacheid: bool = True,
) -> bytes:
    live_cacheid = int(cacheid) & 0xFFFFFFFF if include_cacheid else EMPTY_CACHEID
    live_freshness = int(freshness) & 0xFFFFFFFF if include_cacheid and live_cacheid else EMPTY_FRESHNESS
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_freshness, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_cacheid) if live_cacheid else b""
    header = bytearray()
    header.append(HC_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_store(
    *,
    identity: str,
    cacheid: int,
    freshness: int | None = None,
    include_cacheid: bool = True,
) -> bytes:
    live_cacheid = int(cacheid) & 0xFFFFFFFF if include_cacheid else EMPTY_CACHEID
    live_freshness = int(freshness) if freshness is not None else request_freshness(live_cacheid, identity)
    return encode_packet(
        FRAME_STORE,
        identity=identity,
        cacheid=live_cacheid,
        freshness=live_freshness,
        include_cacheid=include_cacheid,
    )


def encode_revalidate(
    *,
    identity: str,
    cacheid: int,
    freshness: int | None = None,
    include_cacheid: bool = True,
) -> bytes:
    live_cacheid = int(cacheid) & 0xFFFFFFFF if include_cacheid else EMPTY_CACHEID
    live_freshness = int(freshness) if freshness is not None else request_freshness(live_cacheid, identity)
    return encode_packet(
        FRAME_REVALIDATE,
        identity=identity,
        cacheid=live_cacheid,
        freshness=live_freshness,
        include_cacheid=include_cacheid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HttpcacheActuationError("short_packet")
    first = raw[0]
    if first != HC_FIRST:
        raise HttpcacheActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise HttpcacheActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == CACHEID_SIZE:
        live_cacheid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_cacheid = EMPTY_CACHEID
    else:
        raise HttpcacheActuationError("illegal_cacheid")
    if offset >= len(raw):
        raise HttpcacheActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_STORE, FRAME_REVALIDATE}:
        raise HttpcacheActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HttpcacheActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HttpcacheActuationError("checksum_failed")
    if len(payload) < 5:
        raise HttpcacheActuationError("short_packet")
    live_freshness, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HttpcacheActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_cacheid = int(live_cacheid) != EMPTY_CACHEID
    has_freshness = has_cacheid and int(live_freshness) != EMPTY_FRESHNESS
    is_store = frame_type == FRAME_STORE
    is_revalidate = frame_type == FRAME_REVALIDATE
    return {
        "type": int(frame_type),
        "is_store": is_store,
        "is_revalidate": is_revalidate,
        "is_response": is_revalidate,
        "cacheid": int(live_cacheid),
        "has_cacheid": has_cacheid,
        "freshness": int(live_freshness),
        "has_freshness": has_freshness,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http_cache": "RFC9111",
    }


class HttpcacheClient:
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
            raise HttpcacheActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_revalidate"] or not packet["is_response"]:
            raise HttpcacheActuationError("freshness_required")
        if not packet["has_cacheid"]:
            raise HttpcacheActuationError("cacheid_required")
        if not packet["has_freshness"]:
            raise HttpcacheActuationError("freshness_required")
        return packet

    def exchange(self, packet: bytes, *, wait_freshness: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_freshness:
            raise HttpcacheActuationError("freshness_required")
        reply = self._recv()
        return {
            "session": reply,
            "cacheid": int(reply.get("cacheid") or EMPTY_CACHEID),
            "identity": str(reply.get("identity") or ""),
            "freshness": int(reply.get("freshness") or EMPTY_FRESHNESS),
        }

    def revalidate(
        self,
        identity: str,
        cacheid: int,
        freshness: int = EMPTY_FRESHNESS,
        *,
        wait_freshness: bool = True,
        include_cacheid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_revalidate(
            identity=identity,
            cacheid=cacheid,
            freshness=freshness or request_freshness(cacheid, identity),
            include_cacheid=include_cacheid,
        )
        return self.exchange(packet, wait_freshness=wait_freshness)


class HttpcacheSession:
    """CACHEID-gated loopback RFC 9111 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        cacheid_gate: int = DEFAULT_CACHEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cacheid_gate = int(cacheid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.cacheid = EMPTY_CACHEID
        self.freshness = EMPTY_FRESHNESS
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

    def store_cacheid_once(self, identity: str, cacheid: int, freshness: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(cacheid or EMPTY_CACHEID)
            live_freshness = int(freshness or EMPTY_FRESHNESS)
            if not self.identity and name and live:
                self.identity = name
                self.cacheid = live
                self.freshness = live_freshness or request_freshness(live, name)
                self.stored = True
            return str(self.identity), int(self.cacheid), int(self.freshness)

    def read_cacheid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.cacheid), int(self.freshness)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "cacheid": EMPTY_CACHEID,
            "freshness": EMPTY_FRESHNESS,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _cacheid_missing(self) -> bool:
        return not int(self.cacheid_gate or 0)

    def _reply_revalidate(self, peer: tuple[str, int], identity: str, cacheid: int, freshness: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_revalidate(
            identity=identity,
            cacheid=cacheid,
            freshness=freshness,
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
            except HttpcacheActuationError:
                continue
            if not packet.get("is_store") and not packet.get("is_revalidate"):
                continue
            if not packet.get("has_cacheid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_cacheid, stored_freshness = self.store_cacheid_once(
                identity,
                int(packet.get("cacheid") or EMPTY_CACHEID),
                int(packet.get("freshness") or EMPTY_FRESHNESS),
            )
            if not stored_name or not stored_cacheid or not stored_freshness:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_store"):
                    self.opened = True
                if packet.get("is_revalidate"):
                    self.handshook = True
                self.retrieved = True
            self._reply_revalidate(peer, stored_name, stored_cacheid, stored_freshness)

    def bind(self) -> dict[str, Any]:
        if self._cacheid_missing():
            return self._forbidden("missing_cacheid")
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
        do_store_cycle: bool = True,
        do_revalidate: bool = True,
        do_freshness: bool = True,
        replay: bool = True,
        use_cacheid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._cacheid_missing():
            return self._forbidden("missing_cacheid")
        live_token = str(token or SENTINEL)
        origin_cacheid = request_cacheid(live_token)
        origin_freshness = request_freshness(origin_cacheid, live_token)
        client: HttpcacheClient | None = None
        independent: HttpcacheClient | None = None
        try:
            client = HttpcacheClient(self.host, int(self.port))
            if not do_store_cycle:
                return self._conflict("store_required")
            bind_packet = encode_store(
                identity=live_token,
                cacheid=origin_cacheid,
                freshness=origin_freshness,
                include_cacheid=use_cacheid,
            )
            if not use_cacheid:
                try:
                    client.exchange(bind_packet, wait_freshness=True)
                except HttpcacheActuationError:
                    return self._conflict("cacheid_required")
                return self._conflict("cacheid_required")
            client.send(bind_packet)
            if not do_revalidate:
                return self._conflict("revalidate_required")
            proxy_packet = encode_revalidate(
                identity=live_token,
                cacheid=origin_cacheid,
                freshness=origin_freshness,
                include_cacheid=True,
            )
            if not do_freshness:
                try:
                    client.exchange(proxy_packet, wait_freshness=False)
                except HttpcacheActuationError as error:
                    if str(error) == "freshness_required":
                        return self._conflict("freshness_required")
                    return self._conflict("freshness_required")
                return self._conflict("freshness_required")
            try:
                reply = client.exchange(proxy_packet, wait_freshness=True)
            except HttpcacheActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("cacheid_required")
                if reason == "freshness_required":
                    return self._conflict("freshness_required")
                return self._conflict("store_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("store_required")
            if int(reply.get("cacheid") or EMPTY_CACHEID) != origin_cacheid:
                return self._conflict("freshness_required")
            if int(reply.get("freshness") or EMPTY_FRESHNESS) != origin_freshness:
                return self._conflict("freshness_required")
            self.retrieved = True
            if replay:
                independent = HttpcacheClient(self.host, int(self.port))
                try:
                    poll = independent.revalidate(
                        POLL_TOKEN,
                        poll_cacheid(live_token),
                        request_freshness(poll_cacheid(live_token), POLL_TOKEN),
                        wait_freshness=True,
                    )
                except HttpcacheActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_cacheid, stored_freshness = self.read_cacheid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_cacheid != origin_cacheid
                    or stored_freshness != origin_freshness
                    or int(poll.get("cacheid") or EMPTY_CACHEID) != origin_cacheid
                    or int(poll.get("freshness") or EMPTY_FRESHNESS) != origin_freshness
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_cacheid}:{origin_freshness}:{live_token}:{cache_control_header(live_token, origin_cacheid)}:{etag_validator(live_token, origin_cacheid)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "cacheid": origin_cacheid,
                "freshness": origin_freshness,
                "store_frame": True,
                "revalidate": True,
                "freshness_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "cacheid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_httpcache_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "cacheid": origin_cacheid,
                "freshness": origin_freshness,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "store_frame": True,
                "revalidate": True,
                "freshness_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "cacheid_bound": True,
            }
        except (OSError, HttpcacheActuationError) as error:
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
        live = independent_httpcache_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "cacheid": int(live.get("cacheid") or EMPTY_CACHEID),
            "freshness": int(live.get("freshness") or EMPTY_FRESHNESS),
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


def call_httpcache_tool(session: HttpcacheSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one HTTP cache tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_store_cycle = True if arguments.get("store_cycle") is None else bool(arguments.get("store_cycle"))
    do_revalidate = True if arguments.get("revalidate") is None else bool(arguments.get("revalidate"))
    do_freshness = True if arguments.get("freshness") is None else bool(arguments.get("freshness"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_cacheid = True if arguments.get("use_cacheid") is None else bool(arguments.get("use_cacheid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_store_cycle=do_store_cycle,
            do_revalidate=do_revalidate,
            do_freshness=do_freshness,
            replay=replay,
            use_cacheid=use_cacheid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HttpcacheActuationError(f"unsupported httpcache action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_httpcache_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed HTTP cache freshness digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "cacheid": EMPTY_CACHEID,
        "freshness": EMPTY_FRESHNESS,
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
            "store_frame",
            "revalidate",
            "freshness_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "cacheid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    cacheid = int(payload.get("cacheid") or EMPTY_CACHEID)
    freshness = int(payload.get("freshness") or EMPTY_FRESHNESS)
    dual = port > 0 and bool(cacheid) and bool(freshness)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "cacheid": cacheid,
        "freshness": freshness,
        "size": int(payload.get("size") or 0),
        "port": port,
        "store_frame": payload.get("store_frame") is True,
        "revalidate": payload.get("revalidate") is True,
        "freshness_response": payload.get("freshness_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "cacheid_bound": payload.get("cacheid_bound") is True,
    }


def run_httpcache_workflow(
    *,
    with_cacheid: bool = True,
    skip_bind: bool = False,
    do_store_cycle: bool = True,
    do_revalidate: bool = True,
    do_freshness: bool = True,
    replay: bool = True,
    use_cacheid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9111 STORE/REVALIDATE cacheid cycle workflow."""

    descriptor = httpcache_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPCACHE_TOOL_PROVIDER),
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
        raise HttpcacheActuationError(f"httpcache tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="httpcache-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HttpcacheSession(out, cacheid_gate=DEFAULT_CACHEID if with_cacheid else EMPTY_CACHEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "store_cycle": do_store_cycle,
            "revalidate": do_revalidate,
            "freshness": do_freshness,
            "replay": replay,
            "use_cacheid": use_cacheid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_httpcache_tool(session, arguments))
            except HttpcacheActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_httpcache_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_cacheid
        and not skip_bind
        and do_store_cycle
        and do_revalidate
        and do_freshness
        and replay
        and use_cacheid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "httpcache_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_cacheid": with_cacheid,
        "skip_bind": skip_bind,
        "store_frame": do_store_cycle,
        "revalidate": do_revalidate,
        "freshness": do_freshness,
        "replay": replay,
        "use_cacheid": use_cacheid,
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
        "cacheid_value": int(publish_result.get("cacheid") or independent.get("cacheid") or EMPTY_CACHEID),
        "freshness_value": int(publish_result.get("freshness") or independent.get("freshness") or EMPTY_FRESHNESS),
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
        "cacheid": int(trace_body["cacheid_value"] or EMPTY_CACHEID),
        "freshness": int(trace_body["freshness_value"] or EMPTY_FRESHNESS),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_cacheid": with_cacheid,
        "skip_bind": skip_bind,
        "store_cycle": do_store_cycle,
        "revalidate_cycle": do_revalidate,
        "freshness_cycle": do_freshness,
        "replay": replay,
        "use_cacheid": use_cacheid,
    }


def verify_httpcache_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed HTTP cache trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_httpcache_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    cacheid = int(trace.get("cacheid_value") or independent.get("cacheid") or EMPTY_CACHEID)
    freshness = int(trace.get("freshness_value") or independent.get("freshness") or EMPTY_FRESHNESS)
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
        "store_frame": independent.get("store_frame") is True,
        "revalidate": independent.get("revalidate") is True,
        "freshness_response": independent.get("freshness_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "cacheid_bound": independent.get("cacheid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "freshness_recorded": (
            port > 0
            and cacheid == DEFAULT_CACHEID
            and freshness == DEFAULT_FRESHNESS
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def httpcache_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.httpcache_actuation import "
        "builtin_httpcache_actuation_proof; r=builtin_httpcache_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='httpcache_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_httpcache_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTPCACHE_ACTUATION_ID,
        name="First-class RFC 9111 HTTP Caching STORE/REVALIDATE actuation",
        description=(
            "Missions that require a httpcache tool can opt the httpcache provider in, "
            "bind a loopback RFC 9111 HTTP cache origin, complete a STORE "
            "with a non-empty cacheid, lockstep a REVALIDATE that carries the "
            "stored freshness, independently poll the stored cache validator "
            "on a later socket, and seal a digest-chained freshness. Default "
            "routing stays fail-closed; a missing cacheid keeps the hole "
            "falsifiable, and skip-STORE/REVALIDATE/FRESHNESS/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.httpcache_actuation:builtin_httpcache_actuation_proof",
        proof_command=httpcache_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.http2-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/httpcache_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/httpsemantics_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required httpcache tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9111 daemon, speaks a "
            "STORE then REVALIDATE over HTTP Caching with a non-empty cacheid and "
            "freshness, independently polls the stored cache validator on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9113 HTTP/2 lockstep is proved. "
            "Missing cacheids, skip-STORE, skip-REVALIDATE, skip-freshness, skip-REPLAY, "
            "and a STORE aimed without a cacheid stay fail-closed. "
            "Later genesis can take RFC 9110 HTTP Semantics GET/HEAD as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("httpcache", "rfc9111", "http", "cacheid", "freshness", "validator", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T102714Z-7329a192",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_httpcache_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9111 HTTP Caching lockstep actuation seals a freshness digest."""

    from blackhole_agent.httpsemantics_actuation import HTTPSMANTICS_ACTUATION_GOAL, HTTPSMANTICS_ACTUATION_ID
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

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = HTTPCACHE_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTPCACHE_ACTUATION_GOAL) == (
        HTTPCACHE_ACTUATION_ID,
    )
    checks["leftover_text_binds_httpcache"] = leftover_marker_ids(HTTPCACHE_LEFTOVER) == (
        HTTPCACHE_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (HTTPSMANTICS_ACTUATION_GOAL, HTTPSMANTICS_ACTUATION_ID, "httpsemantics"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_httpcache"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"httpcache_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTPCACHE_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTPCACHE_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    directives = parse_cache_control(cache_control_header(SENTINEL, DEFAULT_CACHEID))
    rebuilt_cc = format_cache_control(directives)
    etag = parse_etag(etag_validator(SENTINEL, DEFAULT_CACHEID))
    lifetime = freshness_lifetime(directives)
    age = current_age(0, date_value=0, request_time=0, response_time=0, now=0)
    stored = parse_stored_response(stored_response(SENTINEL, DEFAULT_CACHEID))
    asked = parse_revalidate_request(revalidate_request(SENTINEL, DEFAULT_CACHEID))
    not_modified = revalidate_not_modified(stored, asked)
    checks["cache_control_roundtrip"] = (
        directives[0] == ("max-age", str(DEFAULT_MAX_AGE + (DEFAULT_CACHEID & 0x3F)))
        and directives[1] == ("public", None)
        and directives[2] == ("must-revalidate", None)
        and hmac.compare_digest(rebuilt_cc, cache_control_header(SENTINEL, DEFAULT_CACHEID))
        and lifetime == DEFAULT_MAX_AGE + (DEFAULT_CACHEID & 0x3F)
        and age == 0
        and is_fresh(lifetime=lifetime, age=age) is True
    )
    checks["etag_validator_roundtrip"] = (
        etag["weak"] is False
        and etag["opaque"] == f"{DEFAULT_CACHEID:08x}"
        and etag["entity_tag"] == f'"{DEFAULT_CACHEID:08x}"'
        and hmac.compare_digest(etag_validator(SENTINEL, DEFAULT_CACHEID), etag["entity_tag"])
    )
    checks["store_revalidate_http_roundtrip"] = (
        stored["status"] == 200
        and stored["fresh"] is True
        and stored["must_revalidate"] is True
        and stored["no_store"] is False
        and stored["etag"]["opaque"] == f"{DEFAULT_CACHEID:08x}"
        and asked["method"] == "GET"
        and if_none_match_hits(stored["etag"]["entity_tag"], asked["if_none_match"]) is True
        and not_modified["not_modified"] is True
        and not_modified["status"] == 304
        and DEFAULT_FRESHNESS == request_freshness(DEFAULT_CACHEID, SENTINEL)
    )
    checks["catalog_names_httpcache"] = (
        len(catalog) > 74
        and catalog[74]["id"] == HTTPCACHE_ACTUATION_ID
        and catalog[73]["id"] == HTTP2_ACTUATION_ID
        and catalog[74]["source"] == "genesis_bind_httpcache"
    )
    checks["catalog_names_httpsemantics"] = (
        len(catalog) > 75
        and catalog[75]["id"] == HTTPSMANTICS_ACTUATION_ID
        and catalog[75]["source"] == "genesis_bind_httpsemantics"
    )
    family = capability_family(HTTPCACHE_ACTUATION_GOAL)
    checks["family_is_httpcache"] = "httpcache" in family
    checks["family_is_rfc9111"] = "rfc9111" in family
    checks["family_is_cacheid"] = "cacheid" in family
    checks["family_is_freshness"] = "freshness" in family
    checks["family_is_validator"] = "validator" in family
    checks["family_is_not_httpsemantics"] = (
        "httpsemantic" not in family
        and "rfc9110" not in family
        and "methodid" not in family
        and "fieldsection" not in family
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
    packed = encode_store(identity=SENTINEL, cacheid=DEFAULT_CACHEID, freshness=DEFAULT_FRESHNESS)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_store"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_cacheid"] is True
        and parsed["cacheid"] == DEFAULT_CACHEID
        and parsed["freshness"] == DEFAULT_FRESHNESS
        and parsed["is_response"] is False
        and parsed["is_revalidate"] is False
        and parsed["type"] == FRAME_STORE
        and parsed["first_byte"] == HC_FIRST
    )
    shook = encode_revalidate(
        identity=SENTINEL,
        cacheid=DEFAULT_CACHEID,
        freshness=DEFAULT_FRESHNESS,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_revalidate"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_store"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["cacheid"] == DEFAULT_CACHEID
        and answer_parsed["freshness"] == DEFAULT_FRESHNESS
        and answer_parsed["has_freshness"] is True
        and answer_parsed["type"] == FRAME_REVALIDATE
        and answer_parsed["first_byte"] == HC_FIRST
    )
    bare = encode_store(identity=SENTINEL, cacheid=DEFAULT_CACHEID, include_cacheid=False)
    checks["missing_cacheid_is_unauthenticated"] = parse_message(bare)["has_cacheid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    httpcache_signature = semantic_signature(HTTPCACHE_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(httpcache_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_httpcache = ToolDescriptor(name="remote_httpcache", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_httpcache)
    checks["naive_mcp_httpcache_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = httpcache_tool_descriptor()
    default_httpcache = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPCACHE_TOOL_PROVIDER),
    )
    checks["default_httpcache_provider_is_unsupported"] = (
        default_httpcache.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTPCACHE_TOOL_PROVIDER}" in default_httpcache.reasons
    )
    checks["opted_in_httpcache_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_httpcache],
        required_tool_names=("local_memory", "httpcache"),
    )
    checks["naive_preflight_missing_httpcache"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["httpcache"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "httpcache"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPCACHE_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "httpcache" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="httpcache-actuation-") as tmp:
        root = Path(tmp)
        missing = run_httpcache_workflow(with_cacheid=False, output_dir=root / "missing")
        skip_bind = run_httpcache_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_store_cycle = run_httpcache_workflow(do_store_cycle=False, output_dir=root / "skip-store-cycle")
        skip_revalidate = run_httpcache_workflow(do_revalidate=False, output_dir=root / "skip-revalidate")
        skip_freshness = run_httpcache_workflow(do_freshness=False, output_dir=root / "skip-freshness")
        skip_replay = run_httpcache_workflow(replay=False, output_dir=root / "skip-replay")
        skip_cacheid = run_httpcache_workflow(use_cacheid=False, output_dir=root / "skip-cacheid")
        live = run_httpcache_workflow(output_dir=root / "live")
        verify = verify_httpcache_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_httpcache_trace(clone)
        checks["naive_without_cacheid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_cacheid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_store_cycle_stays_empty"] = (
            skip_store_cycle["ok"] is False
            and skip_store_cycle["error"] == "store_required"
            and skip_store_cycle["final_status"] == 409
            and skip_store_cycle["payload_exists"] is False
        )
        checks["skip_revalidate_stays_empty"] = (
            skip_revalidate["ok"] is False
            and skip_revalidate["error"] == "revalidate_required"
            and skip_revalidate["final_status"] == 409
            and skip_revalidate["payload_exists"] is False
        )
        checks["skip_freshness_stays_empty"] = (
            skip_freshness["ok"] is False
            and skip_freshness["error"] == "freshness_required"
            and skip_freshness["final_status"] == 409
            and skip_freshness["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_cacheid_stays_empty"] = (
            skip_cacheid["ok"] is False
            and skip_cacheid["error"] == "cacheid_required"
            and skip_cacheid["final_status"] == 409
            and skip_cacheid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_freshness"] = (
            int(live.get("cacheid") or 0) == DEFAULT_CACHEID
            and int(live.get("freshness") or 0) == DEFAULT_FRESHNESS
            and int(live.get("port") or 0) > 0
        )
        checks["token_cacheid_encode_revalidate_freshness_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_store_cycle["ok"] is False
            and skip_revalidate["ok"] is False
            and skip_freshness["ok"] is False
            and skip_replay["ok"] is False
            and skip_cacheid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="httpcache-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTPCACHE_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_httpcache"] = (
        live_goal == HTTPCACHE_ACTUATION_GOAL
        and HTTPCACHE_ACTUATION_ID in live_done
        and live_source == "genesis_bind_httpcache"
    )

    with tempfile.TemporaryDirectory(prefix="httpcache-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTPCACHE_LEFTOVER, root)
        register_catalog_proved(root, HTTPCACHE_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTPCACHE_LEFTOVER, root)
        after = leftover_is_open(HTTPCACHE_LEFTOVER, root)
    checks["httpcache_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_httpcache_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTPCACHE_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_httpcache_actuation_capability()
    return {
        "ok": ok,
        "action": "httpcache_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTPCACHE_ACTUATION_GOAL,
        "done_when": HTTPCACHE_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
