"""Drive a first-class Binary HTTP tool through RFC 9292 ENCODE/DECODE.

Tool routing already fails missions that require ``bhttp``: hosted bhttp
endpoints stay on the unsupported MCP provider, and no first-party bhttp
provider is executable. Unbound therefore cannot speak an ENCODE,
lockstep a DECODE messageid handshake over HTTP Binary HTTP MESSAGEID,
independently poll the stored binarymsg, or seal a binarymsg digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``bhttp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9292 daemon
- keep a missing-messageid client so the bhttp-messageid hole stays falsifiable
- refuse DECODE until an ENCODE lands with a non-empty messageid
- independently poll the stored binarymsg on a later client socket
- persist a sealed binarymsg digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9530 Digest Fields
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
    BHTTP_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    bhttp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
BHTTP_ACTUATION_ID = "capability.bhttp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-BIN-OK"
POLL_TOKEN = "BH-BIN-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_MESSAGEID = 0
EMPTY_BINARYMSG = 0
BH_FIRST = 0x42  # RFC 9292 Binary HTTP (ASCII 'B')
MESSAGEID_SIZE = 4
BINARYMSG_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DECODE = 0x02  # RFC 9292 Binary HTTP decode
FRAME_ENCODE = 0x01  # RFC 9292 Binary HTTP encode
FRAMING_KNOWN_REQUEST = 0  # RFC 9292 section 3.3
FRAMING_KNOWN_RESPONSE = 1
FRAMING_INDET_REQUEST = 2
FRAMING_INDET_RESPONSE = 3
BHTTP_ALG_ID = FRAMING_KNOWN_REQUEST
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
BHTTP_LEFTOVER = (
    "Later genesis can take RFC 9292 Binary HTTP ENCODE/DECODE over a "
    "messageid-gated binarymsg digest."
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


BHTTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{BHTTP_ACTUATION_ID};"
    f"capability_proved:{BHTTP_ACTUATION_ID};"
    "no_skill_route"
)
BHTTP_ACTUATION_GOAL = (
    "Repair rfc9292 bhttp encode/decode cycle cannot land over http "
    "bhttp messageid: hosted bhttp endpoints remain unsupported so an ENCODE then "
    "DECODE messageid handshake cannot land and a sealed binarymsg digest "
    "cannot be produced. A missing bhttp messageid stays forbidden; fail-closed "
    "routing never opts the bhttp provider in. An independent later poll of the "
    "stored message binarymsg keeps the hole falsifiable."
)


class BhttpActuationError(RuntimeError):
    """Raised when the Binary HTTP session or loopback daemon fixture misbehaves."""


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
        raise BhttpActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise BhttpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise BhttpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise BhttpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def encode_bhttp_string(value: str | bytes) -> bytes:
    data = value.encode("utf-8") if isinstance(value, str) else bytes(value or b"")
    return encode_varint(len(data)) + data


def decode_bhttp_string(data: bytes, offset: int) -> tuple[bytes, int]:
    length, offset = decode_varint(data, offset)
    end = offset + int(length)
    if end > len(data):
        raise BhttpActuationError("short_packet")
    return data[offset:end], end


def encode_field_section(fields: Sequence[tuple[str, str]]) -> bytes:
    body = b"".join(
        encode_bhttp_string(str(name or "").lower()) + encode_bhttp_string(str(value or ""))
        for name, value in fields
    )
    return encode_varint(len(body)) + body


def decode_field_section(data: bytes, offset: int) -> tuple[list[tuple[str, str]], int]:
    section_len, offset = decode_varint(data, offset)
    end = offset + int(section_len)
    if end > len(data):
        raise BhttpActuationError("short_packet")
    fields: list[tuple[str, str]] = []
    cursor = offset
    while cursor < end:
        name, cursor = decode_bhttp_string(data, cursor)
        value, cursor = decode_bhttp_string(data, cursor)
        fields.append((name.decode("utf-8", errors="replace"), value.decode("utf-8", errors="replace")))
    if cursor != end:
        raise BhttpActuationError("illegal_fields")
    return fields, end


def encode_known_length_request(
    *,
    method: str,
    scheme: str,
    authority: str,
    path: str,
    headers: Sequence[tuple[str, str]] = (),
    content: bytes = b"",
    trailers: Sequence[tuple[str, str]] = (),
) -> bytes:
    """RFC 9292 section 3.6 Known-Length Request."""

    return (
        encode_varint(FRAMING_KNOWN_REQUEST)
        + encode_bhttp_string(method)
        + encode_bhttp_string(scheme)
        + encode_bhttp_string(authority)
        + encode_bhttp_string(path)
        + encode_field_section(headers)
        + encode_varint(len(content))
        + bytes(content or b"")
        + encode_field_section(trailers)
    )


def decode_known_length_request(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    framing, offset = decode_varint(raw, 0)
    if framing != FRAMING_KNOWN_REQUEST:
        raise BhttpActuationError("illegal_framing")
    method, offset = decode_bhttp_string(raw, offset)
    scheme, offset = decode_bhttp_string(raw, offset)
    authority, offset = decode_bhttp_string(raw, offset)
    path, offset = decode_bhttp_string(raw, offset)
    headers, offset = decode_field_section(raw, offset)
    content_len, offset = decode_varint(raw, offset)
    content_end = offset + int(content_len)
    if content_end > len(raw):
        raise BhttpActuationError("short_packet")
    content = raw[offset:content_end]
    trailers, _end = decode_field_section(raw, content_end)
    return {
        "framing_indicator": int(framing),
        "method": method.decode("utf-8", errors="replace"),
        "scheme": scheme.decode("utf-8", errors="replace"),
        "authority": authority.decode("utf-8", errors="replace"),
        "path": path.decode("utf-8", errors="replace"),
        "headers": headers,
        "content": content,
        "trailers": trailers,
    }


def encode_known_length_response(
    *,
    status: int,
    headers: Sequence[tuple[str, str]] = (),
    content: bytes = b"",
    trailers: Sequence[tuple[str, str]] = (),
) -> bytes:
    """RFC 9292 section 3.7 Known-Length Response."""

    return (
        encode_varint(FRAMING_KNOWN_RESPONSE)
        + encode_varint(int(status) & 0xFFFFFFFF)
        + encode_field_section(headers)
        + encode_varint(len(content))
        + bytes(content or b"")
        + encode_field_section(trailers)
    )


def decode_known_length_response(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    framing, offset = decode_varint(raw, 0)
    if framing != FRAMING_KNOWN_RESPONSE:
        raise BhttpActuationError("illegal_framing")
    status, offset = decode_varint(raw, offset)
    headers, offset = decode_field_section(raw, offset)
    content_len, offset = decode_varint(raw, offset)
    content_end = offset + int(content_len)
    if content_end > len(raw):
        raise BhttpActuationError("short_packet")
    content = raw[offset:content_end]
    trailers, _end = decode_field_section(raw, content_end)
    return {
        "framing_indicator": int(framing),
        "status": int(status),
        "headers": headers,
        "content": content,
        "trailers": trailers,
    }


def binary_http_request(identity: str, messageid: int) -> bytes:
    """RFC 9292 known-length request bound to messageid."""

    keyid = f"{int(messageid) & 0xFFFFFFFF:08x}"
    content = f"{identity}:{keyid}".encode("utf-8")
    return encode_known_length_request(
        method="POST",
        scheme="https",
        authority=str(identity or ""),
        path=f"/bhttp/{keyid}",
        headers=(("content-type", "application/octet-stream"),),
        content=content,
    )


def binary_http_response(identity: str, messageid: int) -> bytes:
    """RFC 9292 known-length response echoing the stored Binary HTTP request."""

    encoded = binary_http_request(identity, messageid)
    return encode_known_length_response(
        status=200,
        headers=(("content-type", "application/octet-stream"),),
        content=encoded,
    )


def request_messageid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"messageid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_messageid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-messageid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_binarymsg(messageid: int = EMPTY_MESSAGEID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(binary_http_request(token or SENTINEL, int(messageid) & 0xFFFFFFFF)).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_MESSAGEID = request_messageid(SENTINEL)
DEFAULT_BINARYMSG = request_binarymsg(DEFAULT_MESSAGEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    messageid: int,
    binarymsg: int,
    include_messageid: bool = True,
) -> bytes:
    live_messageid = int(messageid) & 0xFFFFFFFF if include_messageid else EMPTY_MESSAGEID
    live_binarymsg = int(binarymsg) & 0xFFFFFFFF if include_messageid and live_messageid else EMPTY_BINARYMSG
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_binarymsg, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_messageid) if live_messageid else b""
    header = bytearray()
    header.append(BH_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_encode(
    *,
    identity: str,
    messageid: int,
    binarymsg: int | None = None,
    include_messageid: bool = True,
) -> bytes:
    live_messageid = int(messageid) & 0xFFFFFFFF if include_messageid else EMPTY_MESSAGEID
    live_binarymsg = int(binarymsg) if binarymsg is not None else request_binarymsg(live_messageid, identity)
    return encode_packet(
        FRAME_ENCODE,
        identity=identity,
        messageid=live_messageid,
        binarymsg=live_binarymsg,
        include_messageid=include_messageid,
    )


def encode_decode(
    *,
    identity: str,
    messageid: int,
    binarymsg: int | None = None,
    include_messageid: bool = True,
) -> bytes:
    live_messageid = int(messageid) & 0xFFFFFFFF if include_messageid else EMPTY_MESSAGEID
    live_binarymsg = int(binarymsg) if binarymsg is not None else request_binarymsg(live_messageid, identity)
    return encode_packet(
        FRAME_DECODE,
        identity=identity,
        messageid=live_messageid,
        binarymsg=live_binarymsg,
        include_messageid=include_messageid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise BhttpActuationError("short_packet")
    first = raw[0]
    if first != BH_FIRST:
        raise BhttpActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise BhttpActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == MESSAGEID_SIZE:
        live_messageid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_messageid = EMPTY_MESSAGEID
    else:
        raise BhttpActuationError("illegal_messageid")
    if offset >= len(raw):
        raise BhttpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ENCODE, FRAME_DECODE}:
        raise BhttpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise BhttpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise BhttpActuationError("checksum_failed")
    if len(payload) < 5:
        raise BhttpActuationError("short_packet")
    live_binarymsg, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise BhttpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_messageid = int(live_messageid) != EMPTY_MESSAGEID
    has_binarymsg = has_messageid and int(live_binarymsg) != EMPTY_BINARYMSG
    is_encode = frame_type == FRAME_ENCODE
    is_decode = frame_type == FRAME_DECODE
    return {
        "type": int(frame_type),
        "is_encode": is_encode,
        "is_decode": is_decode,
        "is_response": is_decode,
        "messageid": int(live_messageid),
        "has_messageid": has_messageid,
        "binarymsg": int(live_binarymsg),
        "has_binarymsg": has_binarymsg,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "bhttp_alg_id": BHTTP_ALG_ID,
    }


class BhttpClient:
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
            raise BhttpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_decode"] or not packet["is_response"]:
            raise BhttpActuationError("binarymsg_required")
        if not packet["has_messageid"]:
            raise BhttpActuationError("messageid_required")
        if not packet["has_binarymsg"]:
            raise BhttpActuationError("binarymsg_required")
        return packet

    def exchange(self, packet: bytes, *, wait_binarymsg: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_binarymsg:
            raise BhttpActuationError("binarymsg_required")
        reply = self._recv()
        return {
            "session": reply,
            "messageid": int(reply.get("messageid") or EMPTY_MESSAGEID),
            "identity": str(reply.get("identity") or ""),
            "binarymsg": int(reply.get("binarymsg") or EMPTY_BINARYMSG),
        }

    def decode(
        self,
        identity: str,
        messageid: int,
        binarymsg: int = EMPTY_BINARYMSG,
        *,
        wait_binarymsg: bool = True,
        include_messageid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_decode(
            identity=identity,
            messageid=messageid,
            binarymsg=binarymsg or request_binarymsg(messageid, identity),
            include_messageid=include_messageid,
        )
        return self.exchange(packet, wait_binarymsg=wait_binarymsg)


class BhttpSession:
    """MESSAGEID-gated loopback RFC 9292 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        messageid_gate: int = DEFAULT_MESSAGEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.messageid_gate = int(messageid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.messageid = EMPTY_MESSAGEID
        self.binarymsg = EMPTY_BINARYMSG
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

    def store_messageid_once(self, identity: str, messageid: int, binarymsg: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(messageid or EMPTY_MESSAGEID)
            live_binarymsg = int(binarymsg or EMPTY_BINARYMSG)
            if not self.identity and name and live:
                self.identity = name
                self.messageid = live
                self.binarymsg = live_binarymsg or request_binarymsg(live, name)
                self.stored = True
            return str(self.identity), int(self.messageid), int(self.binarymsg)

    def read_messageid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.messageid), int(self.binarymsg)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "messageid": EMPTY_MESSAGEID,
            "binarymsg": EMPTY_BINARYMSG,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _messageid_missing(self) -> bool:
        return not int(self.messageid_gate or 0)

    def _reply_decode(self, peer: tuple[str, int], identity: str, messageid: int, binarymsg: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_decode(
            identity=identity,
            messageid=messageid,
            binarymsg=binarymsg,
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
            except BhttpActuationError:
                continue
            if not packet.get("is_encode") and not packet.get("is_decode"):
                continue
            if not packet.get("has_messageid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_messageid, stored_binarymsg = self.store_messageid_once(
                identity,
                int(packet.get("messageid") or EMPTY_MESSAGEID),
                int(packet.get("binarymsg") or EMPTY_BINARYMSG),
            )
            if not stored_name or not stored_messageid or not stored_binarymsg:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_encode"):
                    self.opened = True
                if packet.get("is_decode"):
                    self.handshook = True
                self.retrieved = True
            self._reply_decode(peer, stored_name, stored_messageid, stored_binarymsg)

    def bind(self) -> dict[str, Any]:
        if self._messageid_missing():
            return self._forbidden("missing_messageid")
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
        do_encode_cycle: bool = True,
        do_decode: bool = True,
        do_binarymsg: bool = True,
        replay: bool = True,
        use_messageid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._messageid_missing():
            return self._forbidden("missing_messageid")
        live_token = str(token or SENTINEL)
        origin_messageid = request_messageid(live_token)
        origin_binarymsg = request_binarymsg(origin_messageid, live_token)
        client: BhttpClient | None = None
        independent: BhttpClient | None = None
        try:
            client = BhttpClient(self.host, int(self.port))
            if not do_encode_cycle:
                return self._conflict("encode_required")
            bind_packet = encode_encode(
                identity=live_token,
                messageid=origin_messageid,
                binarymsg=origin_binarymsg,
                include_messageid=use_messageid,
            )
            if not use_messageid:
                try:
                    client.exchange(bind_packet, wait_binarymsg=True)
                except BhttpActuationError:
                    return self._conflict("messageid_required")
                return self._conflict("messageid_required")
            client.send(bind_packet)
            if not do_decode:
                return self._conflict("decode_required")
            proxy_packet = encode_decode(
                identity=live_token,
                messageid=origin_messageid,
                binarymsg=origin_binarymsg,
                include_messageid=True,
            )
            if not do_binarymsg:
                try:
                    client.exchange(proxy_packet, wait_binarymsg=False)
                except BhttpActuationError as error:
                    if str(error) == "binarymsg_required":
                        return self._conflict("binarymsg_required")
                    return self._conflict("binarymsg_required")
                return self._conflict("binarymsg_required")
            try:
                reply = client.exchange(proxy_packet, wait_binarymsg=True)
            except BhttpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("messageid_required")
                if reason == "binarymsg_required":
                    return self._conflict("binarymsg_required")
                return self._conflict("encode_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("encode_required")
            if int(reply.get("messageid") or EMPTY_MESSAGEID) != origin_messageid:
                return self._conflict("binarymsg_required")
            if int(reply.get("binarymsg") or EMPTY_BINARYMSG) != origin_binarymsg:
                return self._conflict("binarymsg_required")
            self.retrieved = True
            if replay:
                independent = BhttpClient(self.host, int(self.port))
                try:
                    poll = independent.decode(
                        POLL_TOKEN,
                        poll_messageid(live_token),
                        request_binarymsg(poll_messageid(live_token), POLL_TOKEN),
                        wait_binarymsg=True,
                    )
                except BhttpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_messageid, stored_binarymsg = self.read_messageid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_messageid != origin_messageid
                    or stored_binarymsg != origin_binarymsg
                    or int(poll.get("messageid") or EMPTY_MESSAGEID) != origin_messageid
                    or int(poll.get("binarymsg") or EMPTY_BINARYMSG) != origin_binarymsg
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_messageid}:{origin_binarymsg}:{live_token}:{binary_http_request(live_token, origin_messageid).hex()}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "messageid": origin_messageid,
                "binarymsg": origin_binarymsg,
                "encode_frame": True,
                "decode": True,
                "binarymsg_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "messageid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_bhttp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "messageid": origin_messageid,
                "binarymsg": origin_binarymsg,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "encode_frame": True,
                "decode": True,
                "binarymsg_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "messageid_bound": True,
            }
        except (OSError, BhttpActuationError) as error:
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
        live = independent_bhttp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "messageid": int(live.get("messageid") or EMPTY_MESSAGEID),
            "binarymsg": int(live.get("binarymsg") or EMPTY_BINARYMSG),
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


def call_bhttp_tool(session: BhttpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one BHTTP tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_encode_cycle = True if arguments.get("encode_cycle") is None else bool(arguments.get("encode_cycle"))
    do_decode = True if arguments.get("decode") is None else bool(arguments.get("decode"))
    do_binarymsg = True if arguments.get("binarymsg") is None else bool(arguments.get("binarymsg"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_messageid = True if arguments.get("use_messageid") is None else bool(arguments.get("use_messageid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_encode_cycle=do_encode_cycle,
            do_decode=do_decode,
            do_binarymsg=do_binarymsg,
            replay=replay,
            use_messageid=use_messageid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise BhttpActuationError(f"unsupported bhttp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_bhttp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed BHTTP binarymsg digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "messageid": EMPTY_MESSAGEID,
        "binarymsg": EMPTY_BINARYMSG,
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
            "encode_frame",
            "decode",
            "binarymsg_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "messageid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    messageid = int(payload.get("messageid") or EMPTY_MESSAGEID)
    binarymsg = int(payload.get("binarymsg") or EMPTY_BINARYMSG)
    dual = port > 0 and bool(messageid) and bool(binarymsg)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "messageid": messageid,
        "binarymsg": binarymsg,
        "size": int(payload.get("size") or 0),
        "port": port,
        "encode_frame": payload.get("encode_frame") is True,
        "decode": payload.get("decode") is True,
        "binarymsg_response": payload.get("binarymsg_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "messageid_bound": payload.get("messageid_bound") is True,
    }


def run_bhttp_workflow(
    *,
    with_messageid: bool = True,
    skip_bind: bool = False,
    do_encode_cycle: bool = True,
    do_decode: bool = True,
    do_binarymsg: bool = True,
    replay: bool = True,
    use_messageid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9292 ENCODE/DECODE messageid cycle workflow."""

    descriptor = bhttp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BHTTP_TOOL_PROVIDER),
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
        raise BhttpActuationError(f"bhttp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="bhttp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = BhttpSession(out, messageid_gate=DEFAULT_MESSAGEID if with_messageid else EMPTY_MESSAGEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "encode_cycle": do_encode_cycle,
            "decode": do_decode,
            "binarymsg": do_binarymsg,
            "replay": replay,
            "use_messageid": use_messageid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_bhttp_tool(session, arguments))
            except BhttpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_bhttp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_messageid
        and not skip_bind
        and do_encode_cycle
        and do_decode
        and do_binarymsg
        and replay
        and use_messageid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "bhttp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_messageid": with_messageid,
        "skip_bind": skip_bind,
        "encode_frame": do_encode_cycle,
        "decode": do_decode,
        "binarymsg": do_binarymsg,
        "replay": replay,
        "use_messageid": use_messageid,
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
        "messageid_value": int(publish_result.get("messageid") or independent.get("messageid") or EMPTY_MESSAGEID),
        "binarymsg_value": int(publish_result.get("binarymsg") or independent.get("binarymsg") or EMPTY_BINARYMSG),
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
        "messageid": int(trace_body["messageid_value"] or EMPTY_MESSAGEID),
        "binarymsg": int(trace_body["binarymsg_value"] or EMPTY_BINARYMSG),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_messageid": with_messageid,
        "skip_bind": skip_bind,
        "encode_cycle": do_encode_cycle,
        "decode_cycle": do_decode,
        "binarymsg_cycle": do_binarymsg,
        "replay": replay,
        "use_messageid": use_messageid,
    }


def verify_bhttp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed BHTTP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_bhttp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    messageid = int(trace.get("messageid_value") or independent.get("messageid") or EMPTY_MESSAGEID)
    binarymsg = int(trace.get("binarymsg_value") or independent.get("binarymsg") or EMPTY_BINARYMSG)
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
        "encode_frame": independent.get("encode_frame") is True,
        "decode": independent.get("decode") is True,
        "binarymsg_response": independent.get("binarymsg_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "messageid_bound": independent.get("messageid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "binarymsg_recorded": (
            port > 0
            and messageid == DEFAULT_MESSAGEID
            and binarymsg == DEFAULT_BINARYMSG
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def bhttp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.bhttp_actuation import "
        "builtin_bhttp_actuation_proof; r=builtin_bhttp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='bhttp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_bhttp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=BHTTP_ACTUATION_ID,
        name="First-class RFC 9292 Binary HTTP ENCODE/DECODE actuation",
        description=(
            "Missions that require a bhttp tool can opt the bhttp provider in, "
            "bind a loopback RFC 9292 Binary HTTP origin, complete an ENCODE "
            "with a non-empty messageid, lockstep a DECODE that carries the "
            "stored binarymsg, independently poll the stored "
            "binarymsg on a later socket, and seal a digest-chained binarymsg. Default "
            "routing stays fail-closed; a missing messageid keeps the hole "
            "falsifiable, and skip-ENCODE/DECODE/BINARYMSG/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.bhttp_actuation:builtin_bhttp_actuation_proof",
        proof_command=bhttp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.digestfields-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/bhttp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/http11_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required bhttp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9292 daemon, speaks an "
            "ENCODE then DECODE over Binary HTTP with a non-empty messageid and "
            "binarymsg, independently polls the stored binarymsg on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9530 Digest Fields lockstep is proved. "
            "Missing messageids, skip-ENCODE, skip-DECODE, skip-binarymsg, skip-REPLAY, "
            "and an ENCODE aimed without a messageid stay fail-closed. "
            "Later genesis can take RFC 9112 HTTP/1.1 PARSE/SERIALIZE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("bhttp", "rfc9292", "http", "messageid", "binarymsg", "binary-http", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T083710Z-aafa394c",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_bhttp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9292 Binary HTTP lockstep actuation seals a binarymsg digest."""

    from blackhole_agent.http11_actuation import HTTP11_ACTUATION_GOAL, HTTP11_ACTUATION_ID
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
    checks["denylists_self"] = BHTTP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(BHTTP_ACTUATION_GOAL) == (
        BHTTP_ACTUATION_ID,
    )
    checks["leftover_text_binds_bhttp"] = leftover_marker_ids(BHTTP_LEFTOVER) == (
        BHTTP_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (HTTP11_ACTUATION_GOAL, HTTP11_ACTUATION_ID, "http11"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_bhttp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"bhttp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            BHTTP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = BHTTP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    encoded = binary_http_request(SENTINEL, DEFAULT_MESSAGEID)
    decoded = decode_known_length_request(encoded)
    expected_path = f"/bhttp/{DEFAULT_MESSAGEID:08x}"
    expected_content = f"{SENTINEL}:{DEFAULT_MESSAGEID:08x}".encode("utf-8")
    rebuilt = encode_known_length_request(
        method="POST",
        scheme="https",
        authority=SENTINEL,
        path=expected_path,
        headers=(("content-type", "application/octet-stream"),),
        content=expected_content,
    )
    checks["bhttp_known_length_request_roundtrip"] = (
        decoded["framing_indicator"] == FRAMING_KNOWN_REQUEST
        and decoded["method"] == "POST"
        and decoded["scheme"] == "https"
        and decoded["authority"] == SENTINEL
        and decoded["path"] == expected_path
        and decoded["content"] == expected_content
        and hmac.compare_digest(encoded, rebuilt)
        and DEFAULT_BINARYMSG == request_binarymsg(DEFAULT_MESSAGEID, SENTINEL)
    )
    response = binary_http_response(SENTINEL, DEFAULT_MESSAGEID)
    parsed_response = decode_known_length_response(response)
    checks["bhttp_known_length_response_roundtrip"] = (
        parsed_response["framing_indicator"] == FRAMING_KNOWN_RESPONSE
        and parsed_response["status"] == 200
        and parsed_response["content"] == encoded
    )
    checks["catalog_names_bhttp"] = (
        len(catalog) > 71
        and catalog[71]["id"] == BHTTP_ACTUATION_ID
        and catalog[70]["id"] == DIGESTFIELDS_ACTUATION_ID
        and catalog[71]["source"] == "genesis_bind_bhttp"
    )
    checks["catalog_names_http11"] = (
        len(catalog) > 72
        and catalog[72]["id"] == HTTP11_ACTUATION_ID
        and catalog[72]["source"] == "genesis_bind_http11"
    )
    family = capability_family(BHTTP_ACTUATION_GOAL)
    checks["family_is_bhttp"] = "bhttp" in family
    checks["family_is_rfc9292"] = "rfc9292" in family
    checks["family_is_messageid"] = "messageid" in family
    checks["family_is_binarymsg"] = "binarymsg" in family
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
    checks["family_is_not_http11"] = (
        "http11" not in family
        and "rfc9112" not in family
        and "requestid" not in family
        and "startline" not in family
        and "httpmessage" not in family
    )
    packed = encode_encode(identity=SENTINEL, messageid=DEFAULT_MESSAGEID, binarymsg=DEFAULT_BINARYMSG)
    parsed = parse_message(packed)
    checks["encode_roundtrip"] = (
        parsed["is_encode"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_messageid"] is True
        and parsed["messageid"] == DEFAULT_MESSAGEID
        and parsed["binarymsg"] == DEFAULT_BINARYMSG
        and parsed["is_response"] is False
        and parsed["is_decode"] is False
        and parsed["type"] == FRAME_ENCODE
        and parsed["first_byte"] == BH_FIRST
    )
    shook = encode_decode(
        identity=SENTINEL,
        messageid=DEFAULT_MESSAGEID,
        binarymsg=DEFAULT_BINARYMSG,
    )
    answer_parsed = parse_message(shook)
    checks["decode_roundtrip"] = (
        answer_parsed["is_decode"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_encode"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["messageid"] == DEFAULT_MESSAGEID
        and answer_parsed["binarymsg"] == DEFAULT_BINARYMSG
        and answer_parsed["has_binarymsg"] is True
        and answer_parsed["type"] == FRAME_DECODE
        and answer_parsed["first_byte"] == BH_FIRST
    )
    bare = encode_encode(identity=SENTINEL, messageid=DEFAULT_MESSAGEID, include_messageid=False)
    checks["missing_messageid_is_unauthenticated"] = parse_message(bare)["has_messageid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    bhttp_signature = semantic_signature(BHTTP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(bhttp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_bhttp = ToolDescriptor(name="remote_bhttp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_bhttp)
    checks["naive_mcp_bhttp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = bhttp_tool_descriptor()
    default_bhttp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BHTTP_TOOL_PROVIDER),
    )
    checks["default_bhttp_provider_is_unsupported"] = (
        default_bhttp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{BHTTP_TOOL_PROVIDER}" in default_bhttp.reasons
    )
    checks["opted_in_bhttp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_bhttp],
        required_tool_names=("local_memory", "bhttp"),
    )
    checks["naive_preflight_missing_bhttp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["bhttp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "bhttp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BHTTP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "bhttp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="bhttp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_bhttp_workflow(with_messageid=False, output_dir=root / "missing")
        skip_bind = run_bhttp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_encode_cycle = run_bhttp_workflow(do_encode_cycle=False, output_dir=root / "skip-encode-cycle")
        skip_decode = run_bhttp_workflow(do_decode=False, output_dir=root / "skip-decode")
        skip_binarymsg = run_bhttp_workflow(do_binarymsg=False, output_dir=root / "skip-binarymsg")
        skip_replay = run_bhttp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_messageid = run_bhttp_workflow(use_messageid=False, output_dir=root / "skip-messageid")
        live = run_bhttp_workflow(output_dir=root / "live")
        verify = verify_bhttp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_bhttp_trace(clone)
        checks["naive_without_messageid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_messageid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_encode_cycle_stays_empty"] = (
            skip_encode_cycle["ok"] is False
            and skip_encode_cycle["error"] == "encode_required"
            and skip_encode_cycle["final_status"] == 409
            and skip_encode_cycle["payload_exists"] is False
        )
        checks["skip_decode_stays_empty"] = (
            skip_decode["ok"] is False
            and skip_decode["error"] == "decode_required"
            and skip_decode["final_status"] == 409
            and skip_decode["payload_exists"] is False
        )
        checks["skip_binarymsg_stays_empty"] = (
            skip_binarymsg["ok"] is False
            and skip_binarymsg["error"] == "binarymsg_required"
            and skip_binarymsg["final_status"] == 409
            and skip_binarymsg["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_messageid_stays_empty"] = (
            skip_messageid["ok"] is False
            and skip_messageid["error"] == "messageid_required"
            and skip_messageid["final_status"] == 409
            and skip_messageid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_binarymsg"] = (
            int(live.get("messageid") or 0) == DEFAULT_MESSAGEID
            and int(live.get("binarymsg") or 0) == DEFAULT_BINARYMSG
            and int(live.get("port") or 0) > 0
        )
        checks["token_messageid_encode_decode_binarymsg_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_encode_cycle["ok"] is False
            and skip_decode["ok"] is False
            and skip_binarymsg["ok"] is False
            and skip_replay["ok"] is False
            and skip_messageid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="bhttp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != BHTTP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_bhttp"] = (
        live_goal == BHTTP_ACTUATION_GOAL
        and BHTTP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_bhttp"
    )

    with tempfile.TemporaryDirectory(prefix="bhttp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(BHTTP_LEFTOVER, root)
        register_catalog_proved(root, BHTTP_ACTUATION_ID)
        reason = leftover_satisfied_by(BHTTP_LEFTOVER, root)
        after = leftover_is_open(BHTTP_LEFTOVER, root)
    checks["bhttp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_bhttp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{BHTTP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_bhttp_actuation_capability()
    return {
        "ok": ok,
        "action": "bhttp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": BHTTP_ACTUATION_GOAL,
        "done_when": BHTTP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
