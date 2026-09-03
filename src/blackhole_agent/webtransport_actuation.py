"""Drive a first-class WebTransport tool through RFC 9220 CONNECT/SESSION.

Tool routing already fails missions that require ``webtransport``: hosted webtransport
endpoints stay on the unsupported MCP provider, and no first-party webtransport
provider is executable. Unbound therefore cannot speak a CONNECT,
lockstep a SESSION sessionid handshake over UDP WebTransport SESSIONID,
independently poll the stored session capsule, or seal a capsule digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``webtransport`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9220 daemon
- keep a missing-sessionid client so the webtransport-sessionid hole stays falsifiable
- refuse SESSION verify until a CONNECT lands with a non-empty sessionid
- independently poll the stored session capsule on a later client socket
- persist a sealed capsule digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after HTTP/3
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
    WEBTRANSPORT_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    webtransport_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
WEBTRANSPORT_ACTUATION_ID = "capability.webtransport-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-WT-OK"
POLL_TOKEN = "BH-WT-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_SESSIONID = 0
EMPTY_CAPSULE = 0
WT_FIRST = 0x17  # RFC 9297 capsule lead; distinct from HTTP/3 STREAM 0x0E
CID_SIZE = 4
CAPSULE_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_SESSION = 0x42  # RFC 9220
FRAME_CONNECT = 0x41  # RFC 9220
CAPSULE_CLOSE_WEBTRANSPORT_SESSION = 0x2843  # draft-ietf-webtrans-http3
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
WEBTRANSPORT_LEFTOVER = (
    "Later genesis can take RFC 9220 WebTransport CONNECT/SESSION over a "
    "sessionid-gated capsule digest."
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


WEBTRANSPORT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WEBTRANSPORT_ACTUATION_ID};"
    f"capability_proved:{WEBTRANSPORT_ACTUATION_ID};"
    "no_skill_route"
)
WEBTRANSPORT_ACTUATION_GOAL = (
    "Repair rfc9220 webtransport connect/session cycle cannot land over udp "
    "webtransport sessionid: hosted webtransport endpoints remain unsupported so a CONNECT then "
    "SESSION sessionid handshake cannot land and a sealed capsule digest "
    "cannot be produced. A missing webtransport sessionid stays forbidden; fail-closed "
    "routing never opts the webtransport provider in. An independent later poll of the "
    "stored session capsule keeps the hole falsifiable."
)


class WebtransportActuationError(RuntimeError):
    """Raised when the WebTransport session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_sessionid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"sessionid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_sessionid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-sessionid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_capsule(sessionid: int = EMPTY_SESSIONID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"capsule:{int(sessionid) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_SESSIONID = request_sessionid(SENTINEL)
DEFAULT_CAPSULE = request_capsule(DEFAULT_SESSIONID, SENTINEL)


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
        raise WebtransportActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise WebtransportActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise WebtransportActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise WebtransportActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    sessionid: int,
    capsule: int,
    include_sessionid: bool = True,
) -> bytes:
    live_sessionid = int(sessionid) & 0xFFFFFFFF if include_sessionid else EMPTY_SESSIONID
    live_capsule = int(capsule) & 0xFFFFFFFF if include_sessionid and live_sessionid else EMPTY_CAPSULE
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_capsule, len(ident)) + ident
    session_bytes = struct.pack("!I", live_sessionid) if live_sessionid else b""
    header = bytearray()
    header.append(WT_FIRST)
    header.append(len(session_bytes))
    header.extend(session_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_connect(
    *,
    identity: str,
    sessionid: int,
    capsule: int | None = None,
    include_sessionid: bool = True,
) -> bytes:
    live_sessionid = int(sessionid) & 0xFFFFFFFF if include_sessionid else EMPTY_SESSIONID
    live_capsule = int(capsule) if capsule is not None else request_capsule(live_sessionid, identity)
    return encode_packet(
        FRAME_CONNECT,
        identity=identity,
        sessionid=live_sessionid,
        capsule=live_capsule,
        include_sessionid=include_sessionid,
    )


def encode_session(
    *,
    identity: str,
    sessionid: int,
    capsule: int | None = None,
    include_sessionid: bool = True,
) -> bytes:
    live_sessionid = int(sessionid) & 0xFFFFFFFF if include_sessionid else EMPTY_SESSIONID
    live_capsule = int(capsule) if capsule is not None else request_capsule(live_sessionid, identity)
    return encode_packet(
        FRAME_SESSION,
        identity=identity,
        sessionid=live_sessionid,
        capsule=live_capsule,
        include_sessionid=include_sessionid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise WebtransportActuationError("short_packet")
    first = raw[0]
    if first != WT_FIRST:
        raise WebtransportActuationError("illegal_header")
    offset = 1
    session_len = raw[offset]
    offset += 1
    if offset + session_len > len(raw):
        raise WebtransportActuationError("short_packet")
    session_bytes = raw[offset : offset + session_len]
    offset += session_len
    if session_len == CID_SIZE:
        live_sessionid = struct.unpack("!I", session_bytes)[0]
    elif session_len == 0:
        live_sessionid = EMPTY_SESSIONID
    else:
        raise WebtransportActuationError("illegal_sessionid")
    if offset >= len(raw):
        raise WebtransportActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_CONNECT, FRAME_SESSION}:
        raise WebtransportActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise WebtransportActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise WebtransportActuationError("checksum_failed")
    if len(payload) < 5:
        raise WebtransportActuationError("short_packet")
    live_capsule, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise WebtransportActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_sessionid = int(live_sessionid) != EMPTY_SESSIONID
    has_capsule = has_sessionid and int(live_capsule) != EMPTY_CAPSULE
    is_connect = frame_type == FRAME_CONNECT
    is_session = frame_type == FRAME_SESSION
    return {
        "type": int(frame_type),
        "is_connect": is_connect,
        "is_session": is_session,
        "is_response": is_session,
        "sessionid": int(live_sessionid),
        "has_sessionid": has_sessionid,
        "capsule": int(live_capsule),
        "has_capsule": has_capsule,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "session_len": int(session_len),
        "capsule_close_webtransport_session": CAPSULE_CLOSE_WEBTRANSPORT_SESSION,
    }


class _WebtransportClient:
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
            raise WebtransportActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_session"] or not packet["is_response"]:
            raise WebtransportActuationError("capsule_required")
        if not packet["has_sessionid"]:
            raise WebtransportActuationError("sessionid_required")
        if not packet["has_capsule"]:
            raise WebtransportActuationError("capsule_required")
        return packet

    def exchange(self, packet: bytes, *, wait_capsule: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_capsule:
            raise WebtransportActuationError("capsule_required")
        reply = self._recv()
        return {
            "session": reply,
            "sessionid": int(reply.get("sessionid") or EMPTY_SESSIONID),
            "identity": str(reply.get("identity") or ""),
            "capsule": int(reply.get("capsule") or EMPTY_CAPSULE),
        }

    def session(
        self,
        identity: str,
        sessionid: int,
        capsule: int = EMPTY_CAPSULE,
        *,
        wait_capsule: bool = True,
        include_sessionid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_session(
            identity=identity,
            sessionid=sessionid,
            capsule=capsule or request_capsule(sessionid, identity),
            include_sessionid=include_sessionid,
        )
        return self.exchange(packet, wait_capsule=wait_capsule)


class WebtransportSession:
    """SESSIONID-gated loopback RFC 9220 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        sessionid_gate: int = DEFAULT_SESSIONID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sessionid_gate = int(sessionid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.sessionid = EMPTY_SESSIONID
        self.capsule = EMPTY_CAPSULE
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

    def store_sessionid_once(self, identity: str, sessionid: int, capsule: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(sessionid or EMPTY_SESSIONID)
            live_capsule = int(capsule or EMPTY_CAPSULE)
            if not self.identity and name and live:
                self.identity = name
                self.sessionid = live
                self.capsule = live_capsule or request_capsule(live, name)
                self.stored = True
            return str(self.identity), int(self.sessionid), int(self.capsule)

    def read_sessionid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.sessionid), int(self.capsule)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "sessionid": EMPTY_SESSIONID,
            "capsule": EMPTY_CAPSULE,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _sessionid_missing(self) -> bool:
        return not int(self.sessionid_gate or 0)

    def _reply_session(self, peer: tuple[str, int], identity: str, sessionid: int, capsule: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_session(
            identity=identity,
            sessionid=sessionid,
            capsule=capsule,
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
            except WebtransportActuationError:
                continue
            if not packet.get("is_connect") and not packet.get("is_session"):
                continue
            if not packet.get("has_sessionid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_sessionid, stored_capsule = self.store_sessionid_once(
                identity,
                int(packet.get("sessionid") or EMPTY_SESSIONID),
                int(packet.get("capsule") or EMPTY_CAPSULE),
            )
            if not stored_name or not stored_sessionid or not stored_capsule:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_connect"):
                    self.opened = True
                if packet.get("is_session"):
                    self.handshook = True
                self.retrieved = True
            self._reply_session(peer, stored_name, stored_sessionid, stored_capsule)

    def bind(self) -> dict[str, Any]:
        if self._sessionid_missing():
            return self._forbidden("missing_sessionid")
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
        do_connect: bool = True,
        do_session: bool = True,
        do_capsule: bool = True,
        replay: bool = True,
        use_sessionid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._sessionid_missing():
            return self._forbidden("missing_sessionid")
        live_token = str(token or SENTINEL)
        origin_sessionid = request_sessionid(live_token)
        origin_capsule = request_capsule(origin_sessionid, live_token)
        client: _WebtransportClient | None = None
        independent: _WebtransportClient | None = None
        try:
            client = _WebtransportClient(self.host, int(self.port))
            if not do_connect:
                return self._conflict("connect_required")
            connect_packet = encode_connect(
                identity=live_token,
                sessionid=origin_sessionid,
                capsule=origin_capsule,
                include_sessionid=use_sessionid,
            )
            if not use_sessionid:
                try:
                    client.exchange(connect_packet, wait_capsule=True)
                except WebtransportActuationError:
                    return self._conflict("sessionid_required")
                return self._conflict("sessionid_required")
            client.send(connect_packet)
            if not do_session:
                return self._conflict("session_required")
            session_packet = encode_session(
                identity=live_token,
                sessionid=origin_sessionid,
                capsule=origin_capsule,
                include_sessionid=True,
            )
            if not do_capsule:
                try:
                    client.exchange(session_packet, wait_capsule=False)
                except WebtransportActuationError as error:
                    if str(error) == "capsule_required":
                        return self._conflict("capsule_required")
                    return self._conflict("capsule_required")
                return self._conflict("capsule_required")
            try:
                reply = client.exchange(session_packet, wait_capsule=True)
            except WebtransportActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("sessionid_required")
                if reason == "capsule_required":
                    return self._conflict("capsule_required")
                return self._conflict("connect_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("connect_required")
            if int(reply.get("sessionid") or EMPTY_SESSIONID) != origin_sessionid:
                return self._conflict("capsule_required")
            if int(reply.get("capsule") or EMPTY_CAPSULE) != origin_capsule:
                return self._conflict("capsule_required")
            self.retrieved = True
            if replay:
                independent = _WebtransportClient(self.host, int(self.port))
                try:
                    poll = independent.session(
                        POLL_TOKEN,
                        poll_sessionid(live_token),
                        request_capsule(poll_sessionid(live_token), POLL_TOKEN),
                        wait_capsule=True,
                    )
                except WebtransportActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_sessionid, stored_capsule = self.read_sessionid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_sessionid != origin_sessionid
                    or stored_capsule != origin_capsule
                    or int(poll.get("sessionid") or EMPTY_SESSIONID) != origin_sessionid
                    or int(poll.get("capsule") or EMPTY_CAPSULE) != origin_capsule
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_sessionid}:{origin_capsule}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "sessionid": origin_sessionid,
                "capsule": origin_capsule,
                "connect": True,
                "session": True,
                "capsule_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "sessionid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_webtransport_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "sessionid": origin_sessionid,
                "capsule": origin_capsule,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "connect": True,
                "session": True,
                "capsule_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "sessionid_bound": True,
            }
        except (OSError, WebtransportActuationError) as error:
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
        live = independent_webtransport_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "sessionid": int(live.get("sessionid") or EMPTY_SESSIONID),
            "capsule": int(live.get("capsule") or EMPTY_CAPSULE),
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


def call_webtransport_tool(session: WebtransportSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one WebTransport tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_connect = True if arguments.get("connect") is None else bool(arguments.get("connect"))
    do_session = True if arguments.get("session") is None else bool(arguments.get("session"))
    do_capsule = True if arguments.get("capsule") is None else bool(arguments.get("capsule"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_sessionid = True if arguments.get("use_sessionid") is None else bool(arguments.get("use_sessionid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_connect=do_connect,
            do_session=do_session,
            do_capsule=do_capsule,
            replay=replay,
            use_sessionid=use_sessionid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise WebtransportActuationError(f"unsupported webtransport action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_webtransport_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed WebTransport capsule digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "sessionid": EMPTY_SESSIONID,
        "capsule": EMPTY_CAPSULE,
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
            "connect",
            "session",
            "capsule_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "sessionid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    sessionid = int(payload.get("sessionid") or EMPTY_SESSIONID)
    capsule = int(payload.get("capsule") or EMPTY_CAPSULE)
    dual = port > 0 and bool(sessionid) and bool(capsule)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "sessionid": sessionid,
        "capsule": capsule,
        "size": int(payload.get("size") or 0),
        "port": port,
        "connect": payload.get("connect") is True,
        "session": payload.get("session") is True,
        "capsule_response": payload.get("capsule_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "sessionid_bound": payload.get("sessionid_bound") is True,
    }


def run_webtransport_workflow(
    *,
    with_sessionid: bool = True,
    skip_bind: bool = False,
    do_connect: bool = True,
    do_session: bool = True,
    do_capsule: bool = True,
    replay: bool = True,
    use_sessionid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9220 CONNECT/SESSION sessionid cycle workflow."""

    descriptor = webtransport_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBTRANSPORT_TOOL_PROVIDER),
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
        raise WebtransportActuationError(f"webtransport tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="webtransport-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = WebtransportSession(out, sessionid_gate=DEFAULT_SESSIONID if with_sessionid else EMPTY_SESSIONID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "connect": do_connect,
            "session": do_session,
            "capsule": do_capsule,
            "replay": replay,
            "use_sessionid": use_sessionid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_webtransport_tool(session, arguments))
            except WebtransportActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_webtransport_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_sessionid
        and not skip_bind
        and do_connect
        and do_session
        and do_capsule
        and replay
        and use_sessionid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "webtransport_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_sessionid": with_sessionid,
        "skip_bind": skip_bind,
        "connect": do_connect,
        "session": do_session,
        "capsule": do_capsule,
        "replay": replay,
        "use_sessionid": use_sessionid,
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
        "sessionid_value": int(publish_result.get("sessionid") or independent.get("sessionid") or EMPTY_SESSIONID),
        "capsule_value": int(publish_result.get("capsule") or independent.get("capsule") or EMPTY_CAPSULE),
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
        "sessionid": int(trace_body["sessionid_value"] or EMPTY_SESSIONID),
        "capsule": int(trace_body["capsule_value"] or EMPTY_CAPSULE),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_sessionid": with_sessionid,
        "skip_bind": skip_bind,
        "connect": do_connect,
        "session_cycle": do_session,
        "capsule_cycle": do_capsule,
        "replay": replay,
        "use_sessionid": use_sessionid,
    }


def verify_webtransport_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed WebTransport trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_webtransport_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    sessionid = int(trace.get("sessionid_value") or independent.get("sessionid") or EMPTY_SESSIONID)
    capsule = int(trace.get("capsule_value") or independent.get("capsule") or EMPTY_CAPSULE)
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
        "connect": independent.get("connect") is True,
        "session": independent.get("session") is True,
        "capsule_response": independent.get("capsule_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "sessionid_bound": independent.get("sessionid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "capsule_recorded": (
            port > 0
            and sessionid == DEFAULT_SESSIONID
            and capsule == DEFAULT_CAPSULE
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def webtransport_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.webtransport_actuation import "
        "builtin_webtransport_actuation_proof; r=builtin_webtransport_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='webtransport_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_webtransport_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=WEBTRANSPORT_ACTUATION_ID,
        name="First-class RFC 9220 WebTransport CONNECT/SESSION actuation",
        description=(
            "Missions that require a webtransport tool can opt the webtransport provider in, "
            "bind a loopback RFC 9220 UDP WebTransport endpoint, complete a CONNECT "
            "with a non-empty sessionid, lockstep a SESSION that carries the "
            "stored session capsule, independently poll the stored session "
            "capsule on a later socket, and seal a digest-chained capsule. Default "
            "routing stays fail-closed; a missing sessionid keeps the hole "
            "falsifiable, and skip-CONNECT/SESSION/CAPSULE/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.webtransport_actuation:builtin_webtransport_actuation_proof",
        proof_command=webtransport_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.http3-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/webtransport_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/datagram_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required webtransport tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9220 daemon, speaks a "
            "CONNECT then SESSION over UDP WebTransport with a non-empty sessionid and "
            "session capsule, independently polls the stored session capsule on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9114 HTTP/3 lockstep is proved. "
            "Missing sessionids, skip-CONNECT, skip-SESSION, skip-capsule, skip-REPLAY, "
            "and a CONNECT aimed without a sessionid stay fail-closed. "
            "Later genesis can take RFC 9221 QUIC DATAGRAM SEND/ECHO as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("webtransport", "rfc9220", "udp", "sessionid", "capsule", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T035146Z-26381efe",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_webtransport_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9220 WebTransport lockstep actuation seals a capsule digest."""

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
    from blackhole_agent.datagram_actuation import (
        DATAGRAM_ACTUATION_GOAL,
        DATAGRAM_ACTUATION_ID,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = WEBTRANSPORT_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(WEBTRANSPORT_ACTUATION_GOAL) == (
        WEBTRANSPORT_ACTUATION_ID,
    )
    checks["leftover_text_binds_webtransport"] = leftover_marker_ids(WEBTRANSPORT_LEFTOVER) == (
        WEBTRANSPORT_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID, "datagram"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_webtransport"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"webtransport_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            WEBTRANSPORT_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = WEBTRANSPORT_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    checks["catalog_names_webtransport"] = (
        len(catalog) > 63
        and catalog[63]["id"] == WEBTRANSPORT_ACTUATION_ID
        and catalog[62]["id"] == HTTP3_ACTUATION_ID
        and catalog[63]["source"] == "genesis_bind_webtransport"
    )
    checks["catalog_names_datagram"] = (
        len(catalog) > 64
        and catalog[64]["id"] == DATAGRAM_ACTUATION_ID
        and catalog[64]["source"] == "genesis_bind_datagram"
    )
    family = capability_family(WEBTRANSPORT_ACTUATION_GOAL)
    checks["family_is_webtransport"] = "webtransport" in family
    checks["family_is_rfc9220"] = "rfc9220" in family
    checks["family_is_sessionid"] = "sessionid" in family
    checks["family_is_capsule"] = "capsule" in family
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
    checks["family_is_not_datagram"] = (
        "datagram" not in family
        and "rfc9221" not in family
        and "flowid" not in family
        and "contextid" not in family
    )
    packed = encode_connect(identity=SENTINEL, sessionid=DEFAULT_SESSIONID, capsule=DEFAULT_CAPSULE)
    parsed = parse_message(packed)
    checks["connect_roundtrip"] = (
        parsed["is_connect"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_sessionid"] is True
        and parsed["sessionid"] == DEFAULT_SESSIONID
        and parsed["capsule"] == DEFAULT_CAPSULE
        and parsed["is_response"] is False
        and parsed["is_session"] is False
        and parsed["type"] == FRAME_CONNECT
        and parsed["first_byte"] == WT_FIRST
    )
    shook = encode_session(
        identity=SENTINEL,
        sessionid=DEFAULT_SESSIONID,
        capsule=DEFAULT_CAPSULE,
    )
    session_parsed = parse_message(shook)
    checks["session_roundtrip"] = (
        session_parsed["is_session"] is True
        and session_parsed["is_response"] is True
        and session_parsed["is_connect"] is False
        and session_parsed["identity"] == SENTINEL
        and session_parsed["sessionid"] == DEFAULT_SESSIONID
        and session_parsed["capsule"] == DEFAULT_CAPSULE
        and session_parsed["has_capsule"] is True
        and session_parsed["type"] == FRAME_SESSION
        and session_parsed["first_byte"] == WT_FIRST
    )
    bare = encode_connect(identity=SENTINEL, sessionid=DEFAULT_SESSIONID, include_sessionid=False)
    checks["missing_sessionid_is_unauthenticated"] = parse_message(bare)["has_sessionid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    webtransport_signature = semantic_signature(WEBTRANSPORT_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(webtransport_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_webtransport = ToolDescriptor(name="remote_webtransport", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_webtransport)
    checks["naive_mcp_webtransport_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = webtransport_tool_descriptor()
    default_webtransport = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBTRANSPORT_TOOL_PROVIDER),
    )
    checks["default_webtransport_provider_is_unsupported"] = (
        default_webtransport.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{WEBTRANSPORT_TOOL_PROVIDER}" in default_webtransport.reasons
    )
    checks["opted_in_webtransport_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_webtransport],
        required_tool_names=("local_memory", "webtransport"),
    )
    checks["naive_preflight_missing_webtransport"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["webtransport"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "webtransport"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBTRANSPORT_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "webtransport" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="webtransport-actuation-") as tmp:
        root = Path(tmp)
        missing = run_webtransport_workflow(with_sessionid=False, output_dir=root / "missing")
        skip_bind = run_webtransport_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_connect = run_webtransport_workflow(do_connect=False, output_dir=root / "skip-connect")
        skip_session = run_webtransport_workflow(do_session=False, output_dir=root / "skip-session")
        skip_capsule = run_webtransport_workflow(do_capsule=False, output_dir=root / "skip-capsule")
        skip_replay = run_webtransport_workflow(replay=False, output_dir=root / "skip-replay")
        skip_sessionid = run_webtransport_workflow(use_sessionid=False, output_dir=root / "skip-sessionid")
        live = run_webtransport_workflow(output_dir=root / "live")
        verify = verify_webtransport_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_webtransport_trace(clone)
        checks["naive_without_sessionid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_sessionid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_connect_stays_empty"] = (
            skip_connect["ok"] is False
            and skip_connect["error"] == "connect_required"
            and skip_connect["final_status"] == 409
            and skip_connect["payload_exists"] is False
        )
        checks["skip_session_stays_empty"] = (
            skip_session["ok"] is False
            and skip_session["error"] == "session_required"
            and skip_session["final_status"] == 409
            and skip_session["payload_exists"] is False
        )
        checks["skip_capsule_stays_empty"] = (
            skip_capsule["ok"] is False
            and skip_capsule["error"] == "capsule_required"
            and skip_capsule["final_status"] == 409
            and skip_capsule["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_sessionid_stays_empty"] = (
            skip_sessionid["ok"] is False
            and skip_sessionid["error"] == "sessionid_required"
            and skip_sessionid["final_status"] == 409
            and skip_sessionid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_capsule"] = (
            int(live.get("sessionid") or 0) == DEFAULT_SESSIONID
            and int(live.get("capsule") or 0) == DEFAULT_CAPSULE
            and int(live.get("port") or 0) > 0
        )
        checks["token_sessionid_connect_session_capsule_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_connect["ok"] is False
            and skip_session["ok"] is False
            and skip_capsule["ok"] is False
            and skip_replay["ok"] is False
            and skip_sessionid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="webtransport-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != WEBTRANSPORT_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_webtransport"] = (
        live_goal == WEBTRANSPORT_ACTUATION_GOAL
        and WEBTRANSPORT_ACTUATION_ID in live_done
        and live_source == "genesis_bind_webtransport"
    )

    with tempfile.TemporaryDirectory(prefix="webtransport-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(WEBTRANSPORT_LEFTOVER, root)
        register_catalog_proved(root, WEBTRANSPORT_ACTUATION_ID)
        reason = leftover_satisfied_by(WEBTRANSPORT_LEFTOVER, root)
        after = leftover_is_open(WEBTRANSPORT_LEFTOVER, root)
    checks["webtransport_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_webtransport_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{WEBTRANSPORT_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_webtransport_actuation_capability()
    return {
        "ok": ok,
        "action": "webtransport_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": WEBTRANSPORT_ACTUATION_GOAL,
        "done_when": WEBTRANSPORT_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
