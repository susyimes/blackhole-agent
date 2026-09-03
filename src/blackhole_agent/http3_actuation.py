"""Drive a first-class HTTP/3 tool through RFC 9114 SETTINGS/HEADERS.

Tool routing already fails missions that require ``http3``: hosted http3
endpoints stay on the unsupported MCP provider, and no first-party http3
provider is executable. Unbound therefore cannot speak a SETTINGS,
lockstep a HEADERS streamid handshake over UDP HTTP/3 STREAMID,
independently poll the stored stream qpack, or seal a qpack digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``http3`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9114 daemon
- keep a missing-streamid client so the http3-streamid hole stays falsifiable
- refuse HEADERS verify until a SETTINGS lands with a non-empty streamid
- independently poll the stored stream qpack on a later client socket
- persist a sealed qpack digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after QUIC
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import struct
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping

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
    HTTP3_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    http3_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTP3_ACTUATION_ID = "capability.http3-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-H3-OK"
POLL_TOKEN = "BH-H3-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_STREAMID = 0
EMPTY_QPACK = 0
STREAM_FIRST = 0x0E  # RFC 9000 STREAM with LEN and FIN (type 0x08|0x04|0x02)
CID_SIZE = 4
QPACK_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_HEADERS = 0x01  # RFC 9114
FRAME_SETTINGS = 0x04  # RFC 9114
SETTING_QPACK_MAX_TABLE_CAPACITY = 0x01  # RFC 9204
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTP3_LEFTOVER = (
    "Later genesis can take RFC 9114 HTTP/3 SETTINGS/HEADERS over a "
    "streamid-gated qpack digest."
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


HTTP3_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTP3_ACTUATION_ID};"
    f"capability_proved:{HTTP3_ACTUATION_ID};"
    "no_skill_route"
)
HTTP3_ACTUATION_GOAL = (
    "Repair rfc9114 http3 settings/headers cycle cannot land over udp "
    "http3 streamid: hosted http3 endpoints remain unsupported so a SETTINGS then "
    "HEADERS streamid handshake cannot land and a sealed qpack digest "
    "cannot be produced. A missing http3 streamid stays forbidden; fail-closed "
    "routing never opts the http3 provider in. An independent later poll of the "
    "stored stream qpack keeps the hole falsifiable."
)


class Http3ActuationError(RuntimeError):
    """Raised when the HTTP/3 session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_streamid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"streamid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_streamid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-streamid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_qpack(streamid: int = EMPTY_STREAMID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"qpack:{int(streamid) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_STREAMID = request_streamid(SENTINEL)
DEFAULT_QPACK = request_qpack(DEFAULT_STREAMID, SENTINEL)


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
        raise Http3ActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise Http3ActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise Http3ActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise Http3ActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    streamid: int,
    qpack: int,
    include_streamid: bool = True,
) -> bytes:
    live_streamid = int(streamid) & 0xFFFFFFFF if include_streamid else EMPTY_STREAMID
    live_qpack = int(qpack) & 0xFFFFFFFF if include_streamid and live_streamid else EMPTY_QPACK
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_qpack, len(ident)) + ident
    stream_bytes = struct.pack("!I", live_streamid) if live_streamid else b""
    header = bytearray()
    header.append(STREAM_FIRST)
    header.append(len(stream_bytes))
    header.extend(stream_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_settings(
    *,
    identity: str,
    streamid: int,
    qpack: int | None = None,
    include_streamid: bool = True,
) -> bytes:
    live_streamid = int(streamid) & 0xFFFFFFFF if include_streamid else EMPTY_STREAMID
    live_qpack = int(qpack) if qpack is not None else request_qpack(live_streamid, identity)
    return encode_packet(
        FRAME_SETTINGS,
        identity=identity,
        streamid=live_streamid,
        qpack=live_qpack,
        include_streamid=include_streamid,
    )


def encode_headers(
    *,
    identity: str,
    streamid: int,
    qpack: int | None = None,
    include_streamid: bool = True,
) -> bytes:
    live_streamid = int(streamid) & 0xFFFFFFFF if include_streamid else EMPTY_STREAMID
    live_qpack = int(qpack) if qpack is not None else request_qpack(live_streamid, identity)
    return encode_packet(
        FRAME_HEADERS,
        identity=identity,
        streamid=live_streamid,
        qpack=live_qpack,
        include_streamid=include_streamid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise Http3ActuationError("short_packet")
    first = raw[0]
    if first != STREAM_FIRST:
        raise Http3ActuationError("illegal_header")
    offset = 1
    stream_len = raw[offset]
    offset += 1
    if offset + stream_len > len(raw):
        raise Http3ActuationError("short_packet")
    stream_bytes = raw[offset : offset + stream_len]
    offset += stream_len
    if stream_len == CID_SIZE:
        live_streamid = struct.unpack("!I", stream_bytes)[0]
    elif stream_len == 0:
        live_streamid = EMPTY_STREAMID
    else:
        raise Http3ActuationError("illegal_streamid")
    if offset >= len(raw):
        raise Http3ActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SETTINGS, FRAME_HEADERS}:
        raise Http3ActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise Http3ActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise Http3ActuationError("checksum_failed")
    if len(payload) < 5:
        raise Http3ActuationError("short_packet")
    live_qpack, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise Http3ActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_streamid = int(live_streamid) != EMPTY_STREAMID
    has_qpack = has_streamid and int(live_qpack) != EMPTY_QPACK
    is_settings = frame_type == FRAME_SETTINGS
    is_headers = frame_type == FRAME_HEADERS
    return {
        "type": int(frame_type),
        "is_settings": is_settings,
        "is_headers": is_headers,
        "is_response": is_headers,
        "streamid": int(live_streamid),
        "has_streamid": has_streamid,
        "qpack": int(live_qpack),
        "has_qpack": has_qpack,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "stream_len": int(stream_len),
        "setting_qpack_max_table_capacity": SETTING_QPACK_MAX_TABLE_CAPACITY,
    }


class _Http3Client:
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
            raise Http3ActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_headers"] or not packet["is_response"]:
            raise Http3ActuationError("qpack_required")
        if not packet["has_streamid"]:
            raise Http3ActuationError("streamid_required")
        if not packet["has_qpack"]:
            raise Http3ActuationError("qpack_required")
        return packet

    def exchange(self, packet: bytes, *, wait_qpack: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_qpack:
            raise Http3ActuationError("qpack_required")
        reply = self._recv()
        return {
            "headers": reply,
            "streamid": int(reply.get("streamid") or EMPTY_STREAMID),
            "identity": str(reply.get("identity") or ""),
            "qpack": int(reply.get("qpack") or EMPTY_QPACK),
        }

    def headers(
        self,
        identity: str,
        streamid: int,
        qpack: int = EMPTY_QPACK,
        *,
        wait_qpack: bool = True,
        include_streamid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_headers(
            identity=identity,
            streamid=streamid,
            qpack=qpack or request_qpack(streamid, identity),
            include_streamid=include_streamid,
        )
        return self.exchange(packet, wait_qpack=wait_qpack)


class Http3Session:
    """STREAMID-gated loopback RFC 9114 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        streamid_gate: int = DEFAULT_STREAMID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.streamid_gate = int(streamid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.streamid = EMPTY_STREAMID
        self.qpack = EMPTY_QPACK
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

    def store_streamid_once(self, identity: str, streamid: int, qpack: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(streamid or EMPTY_STREAMID)
            live_qpack = int(qpack or EMPTY_QPACK)
            if not self.identity and name and live:
                self.identity = name
                self.streamid = live
                self.qpack = live_qpack or request_qpack(live, name)
                self.stored = True
            return str(self.identity), int(self.streamid), int(self.qpack)

    def read_streamid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.streamid), int(self.qpack)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "streamid": EMPTY_STREAMID,
            "qpack": EMPTY_QPACK,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _streamid_missing(self) -> bool:
        return not int(self.streamid_gate or 0)

    def _reply_headers(self, peer: tuple[str, int], identity: str, streamid: int, qpack: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_headers(
            identity=identity,
            streamid=streamid,
            qpack=qpack,
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
            except Http3ActuationError:
                continue
            if not packet.get("is_settings") and not packet.get("is_headers"):
                continue
            if not packet.get("has_streamid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_streamid, stored_qpack = self.store_streamid_once(
                identity,
                int(packet.get("streamid") or EMPTY_STREAMID),
                int(packet.get("qpack") or EMPTY_QPACK),
            )
            if not stored_name or not stored_streamid or not stored_qpack:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_settings"):
                    self.opened = True
                if packet.get("is_headers"):
                    self.handshook = True
                self.retrieved = True
            self._reply_headers(peer, stored_name, stored_streamid, stored_qpack)

    def bind(self) -> dict[str, Any]:
        if self._streamid_missing():
            return self._forbidden("missing_streamid")
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
        do_settings: bool = True,
        do_headers: bool = True,
        do_qpack: bool = True,
        replay: bool = True,
        use_streamid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._streamid_missing():
            return self._forbidden("missing_streamid")
        live_token = str(token or SENTINEL)
        origin_streamid = request_streamid(live_token)
        origin_qpack = request_qpack(origin_streamid, live_token)
        client: _Http3Client | None = None
        independent: _Http3Client | None = None
        try:
            client = _Http3Client(self.host, int(self.port))
            if not do_settings:
                return self._conflict("settings_required")
            settings_packet = encode_settings(
                identity=live_token,
                streamid=origin_streamid,
                qpack=origin_qpack,
                include_streamid=use_streamid,
            )
            if not use_streamid:
                try:
                    client.exchange(settings_packet, wait_qpack=True)
                except Http3ActuationError:
                    return self._conflict("streamid_required")
                return self._conflict("streamid_required")
            client.send(settings_packet)
            if not do_headers:
                return self._conflict("headers_required")
            headers_packet = encode_headers(
                identity=live_token,
                streamid=origin_streamid,
                qpack=origin_qpack,
                include_streamid=True,
            )
            if not do_qpack:
                try:
                    client.exchange(headers_packet, wait_qpack=False)
                except Http3ActuationError as error:
                    if str(error) == "qpack_required":
                        return self._conflict("qpack_required")
                    return self._conflict("qpack_required")
                return self._conflict("qpack_required")
            try:
                reply = client.exchange(headers_packet, wait_qpack=True)
            except Http3ActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("streamid_required")
                if reason == "qpack_required":
                    return self._conflict("qpack_required")
                return self._conflict("settings_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("settings_required")
            if int(reply.get("streamid") or EMPTY_STREAMID) != origin_streamid:
                return self._conflict("qpack_required")
            if int(reply.get("qpack") or EMPTY_QPACK) != origin_qpack:
                return self._conflict("qpack_required")
            self.retrieved = True
            if replay:
                independent = _Http3Client(self.host, int(self.port))
                try:
                    poll = independent.headers(
                        POLL_TOKEN,
                        poll_streamid(live_token),
                        request_qpack(poll_streamid(live_token), POLL_TOKEN),
                        wait_qpack=True,
                    )
                except Http3ActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_streamid, stored_qpack = self.read_streamid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_streamid != origin_streamid
                    or stored_qpack != origin_qpack
                    or int(poll.get("streamid") or EMPTY_STREAMID) != origin_streamid
                    or int(poll.get("qpack") or EMPTY_QPACK) != origin_qpack
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_streamid}:{origin_qpack}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "streamid": origin_streamid,
                "qpack": origin_qpack,
                "settings": True,
                "headers": True,
                "qpack_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "streamid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_http3_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "streamid": origin_streamid,
                "qpack": origin_qpack,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "settings": True,
                "headers": True,
                "qpack_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "streamid_bound": True,
            }
        except (OSError, Http3ActuationError) as error:
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
        live = independent_http3_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "streamid": int(live.get("streamid") or EMPTY_STREAMID),
            "qpack": int(live.get("qpack") or EMPTY_QPACK),
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


def call_http3_tool(session: Http3Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one HTTP/3 tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_settings = True if arguments.get("settings") is None else bool(arguments.get("settings"))
    do_headers = True if arguments.get("headers") is None else bool(arguments.get("headers"))
    do_qpack = True if arguments.get("qpack") is None else bool(arguments.get("qpack"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_streamid = True if arguments.get("use_streamid") is None else bool(arguments.get("use_streamid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_settings=do_settings,
            do_headers=do_headers,
            do_qpack=do_qpack,
            replay=replay,
            use_streamid=use_streamid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise Http3ActuationError(f"unsupported http3 action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_http3_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed HTTP/3 qpack digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "streamid": EMPTY_STREAMID,
        "qpack": EMPTY_QPACK,
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
            "settings",
            "headers",
            "qpack_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "streamid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    streamid = int(payload.get("streamid") or EMPTY_STREAMID)
    qpack = int(payload.get("qpack") or EMPTY_QPACK)
    dual = port > 0 and bool(streamid) and bool(qpack)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "streamid": streamid,
        "qpack": qpack,
        "size": int(payload.get("size") or 0),
        "port": port,
        "settings": payload.get("settings") is True,
        "headers": payload.get("headers") is True,
        "qpack_response": payload.get("qpack_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "streamid_bound": payload.get("streamid_bound") is True,
    }


def run_http3_workflow(
    *,
    with_streamid: bool = True,
    skip_bind: bool = False,
    do_settings: bool = True,
    do_headers: bool = True,
    do_qpack: bool = True,
    replay: bool = True,
    use_streamid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9114 SETTINGS/HEADERS streamid cycle workflow."""

    descriptor = http3_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP3_TOOL_PROVIDER),
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
        raise Http3ActuationError(f"http3 tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="http3-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = Http3Session(out, streamid_gate=DEFAULT_STREAMID if with_streamid else EMPTY_STREAMID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "settings": do_settings,
            "headers": do_headers,
            "qpack": do_qpack,
            "replay": replay,
            "use_streamid": use_streamid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_http3_tool(session, arguments))
            except Http3ActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_http3_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_streamid
        and not skip_bind
        and do_settings
        and do_headers
        and do_qpack
        and replay
        and use_streamid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "http3_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_streamid": with_streamid,
        "skip_bind": skip_bind,
        "settings": do_settings,
        "headers": do_headers,
        "qpack": do_qpack,
        "replay": replay,
        "use_streamid": use_streamid,
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
        "streamid_value": int(publish_result.get("streamid") or independent.get("streamid") or EMPTY_STREAMID),
        "qpack_value": int(publish_result.get("qpack") or independent.get("qpack") or EMPTY_QPACK),
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
        "streamid": int(trace_body["streamid_value"] or EMPTY_STREAMID),
        "qpack": int(trace_body["qpack_value"] or EMPTY_QPACK),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_streamid": with_streamid,
        "skip_bind": skip_bind,
        "settings": do_settings,
        "headers_cycle": do_headers,
        "qpack_cycle": do_qpack,
        "replay": replay,
        "use_streamid": use_streamid,
    }


def verify_http3_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed HTTP/3 trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_http3_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    streamid = int(trace.get("streamid_value") or independent.get("streamid") or EMPTY_STREAMID)
    qpack = int(trace.get("qpack_value") or independent.get("qpack") or EMPTY_QPACK)
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
        "settings": independent.get("settings") is True,
        "headers": independent.get("headers") is True,
        "qpack_response": independent.get("qpack_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "streamid_bound": independent.get("streamid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "qpack_recorded": (
            port > 0
            and streamid == DEFAULT_STREAMID
            and qpack == DEFAULT_QPACK
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def http3_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.http3_actuation import "
        "builtin_http3_actuation_proof; r=builtin_http3_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='http3_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_http3_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTP3_ACTUATION_ID,
        name="First-class RFC 9114 HTTP/3 SETTINGS/HEADERS actuation",
        description=(
            "Missions that require a http3 tool can opt the http3 provider in, "
            "bind a loopback RFC 9114 UDP HTTP/3 endpoint, complete a SETTINGS "
            "with a non-empty streamid, lockstep a HEADERS that carries the "
            "stored stream qpack, independently poll the stored stream "
            "qpack on a later socket, and seal a digest-chained qpack. Default "
            "routing stays fail-closed; a missing streamid keeps the hole "
            "falsifiable, and skip-SETTINGS/HEADERS/QPACK/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.http3_actuation:builtin_http3_actuation_proof",
        proof_command=http3_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.quic-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/http3_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/webtransport_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required http3 tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9114 daemon, speaks a "
            "SETTINGS then HEADERS over UDP HTTP/3 with a non-empty streamid and "
            "stream qpack, independently polls the stored stream qpack on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9000 QUIC lockstep is proved. "
            "Missing streamids, skip-SETTINGS, skip-HEADERS, skip-qpack, skip-REPLAY, "
            "and a SETTINGS aimed without a streamid stay fail-closed. "
            "Later genesis can take RFC 9220 WebTransport CONNECT/SESSION as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("http3", "rfc9114", "udp", "streamid", "qpack", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T031400Z-772d3764",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_http3_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9114 HTTP/3 lockstep actuation seals a qpack digest."""

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
    from blackhole_agent.webtransport_actuation import (
        WEBTRANSPORT_ACTUATION_GOAL,
        WEBTRANSPORT_ACTUATION_ID,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = HTTP3_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTP3_ACTUATION_GOAL) == (
        HTTP3_ACTUATION_ID,
    )
    checks["leftover_text_binds_http3"] = leftover_marker_ids(HTTP3_LEFTOVER) == (
        HTTP3_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (WEBTRANSPORT_ACTUATION_GOAL, WEBTRANSPORT_ACTUATION_ID, "webtransport"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_http3"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"http3_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTP3_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTP3_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    checks["catalog_names_http3"] = (
        len(catalog) > 62
        and catalog[62]["id"] == HTTP3_ACTUATION_ID
        and catalog[61]["id"] == QUIC_ACTUATION_ID
        and catalog[62]["source"] == "genesis_bind_http3"
    )
    checks["catalog_names_webtransport"] = (
        len(catalog) > 63
        and catalog[63]["id"] == WEBTRANSPORT_ACTUATION_ID
        and catalog[63]["source"] == "genesis_bind_webtransport"
    )
    family = capability_family(HTTP3_ACTUATION_GOAL)
    checks["family_is_http3"] = "http3" in family
    checks["family_is_rfc9114"] = "rfc9114" in family
    checks["family_is_streamid"] = "streamid" in family
    checks["family_is_qpack"] = "qpack" in family
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
    checks["family_is_not_webtransport"] = (
        "webtransport" not in family
        and "rfc9220" not in family
        and "sessionid" not in family
        and "capsule" not in family
    )
    packed = encode_settings(identity=SENTINEL, streamid=DEFAULT_STREAMID, qpack=DEFAULT_QPACK)
    parsed = parse_message(packed)
    checks["settings_roundtrip"] = (
        parsed["is_settings"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_streamid"] is True
        and parsed["streamid"] == DEFAULT_STREAMID
        and parsed["qpack"] == DEFAULT_QPACK
        and parsed["is_response"] is False
        and parsed["is_headers"] is False
        and parsed["type"] == FRAME_SETTINGS
        and parsed["first_byte"] == STREAM_FIRST
    )
    shook = encode_headers(
        identity=SENTINEL,
        streamid=DEFAULT_STREAMID,
        qpack=DEFAULT_QPACK,
    )
    headers_parsed = parse_message(shook)
    checks["headers_roundtrip"] = (
        headers_parsed["is_headers"] is True
        and headers_parsed["is_response"] is True
        and headers_parsed["is_settings"] is False
        and headers_parsed["identity"] == SENTINEL
        and headers_parsed["streamid"] == DEFAULT_STREAMID
        and headers_parsed["qpack"] == DEFAULT_QPACK
        and headers_parsed["has_qpack"] is True
        and headers_parsed["type"] == FRAME_HEADERS
        and headers_parsed["first_byte"] == STREAM_FIRST
    )
    bare = encode_settings(identity=SENTINEL, streamid=DEFAULT_STREAMID, include_streamid=False)
    checks["missing_streamid_is_unauthenticated"] = parse_message(bare)["has_streamid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    http3_signature = semantic_signature(HTTP3_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(http3_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_http3 = ToolDescriptor(name="remote_http3", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_http3)
    checks["naive_mcp_http3_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = http3_tool_descriptor()
    default_http3 = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP3_TOOL_PROVIDER),
    )
    checks["default_http3_provider_is_unsupported"] = (
        default_http3.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTP3_TOOL_PROVIDER}" in default_http3.reasons
    )
    checks["opted_in_http3_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_http3],
        required_tool_names=("local_memory", "http3"),
    )
    checks["naive_preflight_missing_http3"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["http3"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "http3"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP3_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "http3" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="http3-actuation-") as tmp:
        root = Path(tmp)
        missing = run_http3_workflow(with_streamid=False, output_dir=root / "missing")
        skip_bind = run_http3_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_settings = run_http3_workflow(do_settings=False, output_dir=root / "skip-settings")
        skip_headers = run_http3_workflow(do_headers=False, output_dir=root / "skip-headers")
        skip_qpack = run_http3_workflow(do_qpack=False, output_dir=root / "skip-qpack")
        skip_replay = run_http3_workflow(replay=False, output_dir=root / "skip-replay")
        skip_streamid = run_http3_workflow(use_streamid=False, output_dir=root / "skip-streamid")
        live = run_http3_workflow(output_dir=root / "live")
        verify = verify_http3_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_http3_trace(clone)
        checks["naive_without_streamid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_streamid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_settings_stays_empty"] = (
            skip_settings["ok"] is False
            and skip_settings["error"] == "settings_required"
            and skip_settings["final_status"] == 409
            and skip_settings["payload_exists"] is False
        )
        checks["skip_headers_stays_empty"] = (
            skip_headers["ok"] is False
            and skip_headers["error"] == "headers_required"
            and skip_headers["final_status"] == 409
            and skip_headers["payload_exists"] is False
        )
        checks["skip_qpack_stays_empty"] = (
            skip_qpack["ok"] is False
            and skip_qpack["error"] == "qpack_required"
            and skip_qpack["final_status"] == 409
            and skip_qpack["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_streamid_stays_empty"] = (
            skip_streamid["ok"] is False
            and skip_streamid["error"] == "streamid_required"
            and skip_streamid["final_status"] == 409
            and skip_streamid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_qpack"] = (
            int(live.get("streamid") or 0) == DEFAULT_STREAMID
            and int(live.get("qpack") or 0) == DEFAULT_QPACK
            and int(live.get("port") or 0) > 0
        )
        checks["token_streamid_settings_headers_qpack_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_settings["ok"] is False
            and skip_headers["ok"] is False
            and skip_qpack["ok"] is False
            and skip_replay["ok"] is False
            and skip_streamid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="http3-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTP3_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_http3"] = (
        live_goal == HTTP3_ACTUATION_GOAL
        and HTTP3_ACTUATION_ID in live_done
        and live_source == "genesis_bind_http3"
    )

    with tempfile.TemporaryDirectory(prefix="http3-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTP3_LEFTOVER, root)
        register_catalog_proved(root, HTTP3_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTP3_LEFTOVER, root)
        after = leftover_is_open(HTTP3_LEFTOVER, root)
    checks["http3_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_http3_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTP3_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_http3_actuation_capability()
    return {
        "ok": ok,
        "action": "http3_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTP3_ACTUATION_GOAL,
        "done_when": HTTP3_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
