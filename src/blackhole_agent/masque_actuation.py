"""Drive a first-class MASQUE tool through RFC 9298 BIND/PROXY.

Tool routing already fails missions that require ``masque``: hosted masque
endpoints stay on the unsupported MCP provider, and no first-party masque
provider is executable. Unbound therefore cannot speak a BIND,
lockstep a PROXY targetid handshake over HTTP MASQUE TARGETID,
independently poll the stored proxy authority, or seal an authority digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``masque`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9298 daemon
- keep a missing-targetid client so the masque-targetid hole stays falsifiable
- refuse PROXY verify until a BIND lands with a non-empty targetid
- independently poll the stored proxy authority on a later client socket
- persist a sealed authority digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after QUIC DATAGRAM
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
    MASQUE_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    masque_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
MASQUE_ACTUATION_ID = "capability.masque-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-MQ-OK"
POLL_TOKEN = "BH-MQ-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_TARGETID = 0
EMPTY_AUTHORITY = 0
MQ_FIRST = 0x00  # RFC 9297 HTTP Datagram capsule
CID_SIZE = 4
AUTHORITY_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_PROXY = 0x00  # RFC 9298 CONNECT-UDP DATAGRAM
FRAME_BIND = 0x01  # CONNECT-UDP bind/listen
MASQUE_AUTHORITY_TYPE = 0x00  # RFC 9298 Context ID 0
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
MASQUE_LEFTOVER = (
    "Later genesis can take RFC 9298 MASQUE CONNECT-UDP BIND/PROXY over a "
    "targetid-gated authority digest."
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


MASQUE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MASQUE_ACTUATION_ID};"
    f"capability_proved:{MASQUE_ACTUATION_ID};"
    "no_skill_route"
)
MASQUE_ACTUATION_GOAL = (
    "Repair rfc9298 masque bind/proxy cycle cannot land over http "
    "masque targetid: hosted masque endpoints remain unsupported so a BIND then "
    "PROXY targetid handshake cannot land and a sealed authority digest "
    "cannot be produced. A missing masque targetid stays forbidden; fail-closed "
    "routing never opts the masque provider in. An independent later poll of the "
    "stored proxy authority keeps the hole falsifiable."
)


class MasqueActuationError(RuntimeError):
    """Raised when the MASQUE session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_targetid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"targetid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_targetid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-targetid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_authority(targetid: int = EMPTY_TARGETID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"authority:{int(targetid) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_TARGETID = request_targetid(SENTINEL)
DEFAULT_AUTHORITY = request_authority(DEFAULT_TARGETID, SENTINEL)


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
        raise MasqueActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise MasqueActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise MasqueActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise MasqueActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    targetid: int,
    authority: int,
    include_targetid: bool = True,
) -> bytes:
    live_targetid = int(targetid) & 0xFFFFFFFF if include_targetid else EMPTY_TARGETID
    live_authority = int(authority) & 0xFFFFFFFF if include_targetid and live_targetid else EMPTY_AUTHORITY
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_authority, len(ident)) + ident
    target_bytes = struct.pack("!I", live_targetid) if live_targetid else b""
    header = bytearray()
    header.append(MQ_FIRST)
    header.append(len(target_bytes))
    header.extend(target_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_bind(
    *,
    identity: str,
    targetid: int,
    authority: int | None = None,
    include_targetid: bool = True,
) -> bytes:
    live_targetid = int(targetid) & 0xFFFFFFFF if include_targetid else EMPTY_TARGETID
    live_authority = int(authority) if authority is not None else request_authority(live_targetid, identity)
    return encode_packet(
        FRAME_BIND,
        identity=identity,
        targetid=live_targetid,
        authority=live_authority,
        include_targetid=include_targetid,
    )


def encode_proxy(
    *,
    identity: str,
    targetid: int,
    authority: int | None = None,
    include_targetid: bool = True,
) -> bytes:
    live_targetid = int(targetid) & 0xFFFFFFFF if include_targetid else EMPTY_TARGETID
    live_authority = int(authority) if authority is not None else request_authority(live_targetid, identity)
    return encode_packet(
        FRAME_PROXY,
        identity=identity,
        targetid=live_targetid,
        authority=live_authority,
        include_targetid=include_targetid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise MasqueActuationError("short_packet")
    first = raw[0]
    if first != MQ_FIRST:
        raise MasqueActuationError("illegal_header")
    offset = 1
    target_len = raw[offset]
    offset += 1
    if offset + target_len > len(raw):
        raise MasqueActuationError("short_packet")
    target_bytes = raw[offset : offset + target_len]
    offset += target_len
    if target_len == CID_SIZE:
        live_targetid = struct.unpack("!I", target_bytes)[0]
    elif target_len == 0:
        live_targetid = EMPTY_TARGETID
    else:
        raise MasqueActuationError("illegal_targetid")
    if offset >= len(raw):
        raise MasqueActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_BIND, FRAME_PROXY}:
        raise MasqueActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise MasqueActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise MasqueActuationError("checksum_failed")
    if len(payload) < 5:
        raise MasqueActuationError("short_packet")
    live_authority, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise MasqueActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_targetid = int(live_targetid) != EMPTY_TARGETID
    has_authority = has_targetid and int(live_authority) != EMPTY_AUTHORITY
    is_bind = frame_type == FRAME_BIND
    is_proxy = frame_type == FRAME_PROXY
    return {
        "type": int(frame_type),
        "is_bind": is_bind,
        "is_proxy": is_proxy,
        "is_response": is_proxy,
        "targetid": int(live_targetid),
        "has_targetid": has_targetid,
        "authority": int(live_authority),
        "has_authority": has_authority,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "target_len": int(target_len),
        "masque_authority_type": MASQUE_AUTHORITY_TYPE,
    }


class MasqueClient:
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
            raise MasqueActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_proxy"] or not packet["is_response"]:
            raise MasqueActuationError("authority_required")
        if not packet["has_targetid"]:
            raise MasqueActuationError("targetid_required")
        if not packet["has_authority"]:
            raise MasqueActuationError("authority_required")
        return packet

    def exchange(self, packet: bytes, *, wait_authority: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_authority:
            raise MasqueActuationError("authority_required")
        reply = self._recv()
        return {
            "session": reply,
            "targetid": int(reply.get("targetid") or EMPTY_TARGETID),
            "identity": str(reply.get("identity") or ""),
            "authority": int(reply.get("authority") or EMPTY_AUTHORITY),
        }

    def proxy(
        self,
        identity: str,
        targetid: int,
        authority: int = EMPTY_AUTHORITY,
        *,
        wait_authority: bool = True,
        include_targetid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_proxy(
            identity=identity,
            targetid=targetid,
            authority=authority or request_authority(targetid, identity),
            include_targetid=include_targetid,
        )
        return self.exchange(packet, wait_authority=wait_authority)


class MasqueSession:
    """TARGETID-gated loopback RFC 9298 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        targetid_gate: int = DEFAULT_TARGETID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.targetid_gate = int(targetid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.targetid = EMPTY_TARGETID
        self.authority = EMPTY_AUTHORITY
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

    def store_targetid_once(self, identity: str, targetid: int, authority: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(targetid or EMPTY_TARGETID)
            live_authority = int(authority or EMPTY_AUTHORITY)
            if not self.identity and name and live:
                self.identity = name
                self.targetid = live
                self.authority = live_authority or request_authority(live, name)
                self.stored = True
            return str(self.identity), int(self.targetid), int(self.authority)

    def read_targetid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.targetid), int(self.authority)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "targetid": EMPTY_TARGETID,
            "authority": EMPTY_AUTHORITY,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _targetid_missing(self) -> bool:
        return not int(self.targetid_gate or 0)

    def _reply_proxy(self, peer: tuple[str, int], identity: str, targetid: int, authority: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_proxy(
            identity=identity,
            targetid=targetid,
            authority=authority,
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
            except MasqueActuationError:
                continue
            if not packet.get("is_bind") and not packet.get("is_proxy"):
                continue
            if not packet.get("has_targetid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_targetid, stored_authority = self.store_targetid_once(
                identity,
                int(packet.get("targetid") or EMPTY_TARGETID),
                int(packet.get("authority") or EMPTY_AUTHORITY),
            )
            if not stored_name or not stored_targetid or not stored_authority:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_bind"):
                    self.opened = True
                if packet.get("is_proxy"):
                    self.handshook = True
                self.retrieved = True
            self._reply_proxy(peer, stored_name, stored_targetid, stored_authority)

    def bind(self) -> dict[str, Any]:
        if self._targetid_missing():
            return self._forbidden("missing_targetid")
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
        do_bind_cycle: bool = True,
        do_proxy: bool = True,
        do_authority: bool = True,
        replay: bool = True,
        use_targetid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._targetid_missing():
            return self._forbidden("missing_targetid")
        live_token = str(token or SENTINEL)
        origin_targetid = request_targetid(live_token)
        origin_authority = request_authority(origin_targetid, live_token)
        client: MasqueClient | None = None
        independent: MasqueClient | None = None
        try:
            client = MasqueClient(self.host, int(self.port))
            if not do_bind_cycle:
                return self._conflict("bind_required")
            bind_packet = encode_bind(
                identity=live_token,
                targetid=origin_targetid,
                authority=origin_authority,
                include_targetid=use_targetid,
            )
            if not use_targetid:
                try:
                    client.exchange(bind_packet, wait_authority=True)
                except MasqueActuationError:
                    return self._conflict("targetid_required")
                return self._conflict("targetid_required")
            client.send(bind_packet)
            if not do_proxy:
                return self._conflict("proxy_required")
            proxy_packet = encode_proxy(
                identity=live_token,
                targetid=origin_targetid,
                authority=origin_authority,
                include_targetid=True,
            )
            if not do_authority:
                try:
                    client.exchange(proxy_packet, wait_authority=False)
                except MasqueActuationError as error:
                    if str(error) == "authority_required":
                        return self._conflict("authority_required")
                    return self._conflict("authority_required")
                return self._conflict("authority_required")
            try:
                reply = client.exchange(proxy_packet, wait_authority=True)
            except MasqueActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("targetid_required")
                if reason == "authority_required":
                    return self._conflict("authority_required")
                return self._conflict("bind_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("bind_required")
            if int(reply.get("targetid") or EMPTY_TARGETID) != origin_targetid:
                return self._conflict("authority_required")
            if int(reply.get("authority") or EMPTY_AUTHORITY) != origin_authority:
                return self._conflict("authority_required")
            self.retrieved = True
            if replay:
                independent = MasqueClient(self.host, int(self.port))
                try:
                    poll = independent.proxy(
                        POLL_TOKEN,
                        poll_targetid(live_token),
                        request_authority(poll_targetid(live_token), POLL_TOKEN),
                        wait_authority=True,
                    )
                except MasqueActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_targetid, stored_authority = self.read_targetid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_targetid != origin_targetid
                    or stored_authority != origin_authority
                    or int(poll.get("targetid") or EMPTY_TARGETID) != origin_targetid
                    or int(poll.get("authority") or EMPTY_AUTHORITY) != origin_authority
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_targetid}:{origin_authority}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "targetid": origin_targetid,
                "authority": origin_authority,
                "bind": True,
                "proxy": True,
                "authority_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "targetid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_masque_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "targetid": origin_targetid,
                "authority": origin_authority,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "bind": True,
                "proxy": True,
                "authority_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "targetid_bound": True,
            }
        except (OSError, MasqueActuationError) as error:
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
        live = independent_masque_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "targetid": int(live.get("targetid") or EMPTY_TARGETID),
            "authority": int(live.get("authority") or EMPTY_AUTHORITY),
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


def call_masque_tool(session: MasqueSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one MASQUE tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_bind_cycle = True if arguments.get("bind_cycle") is None else bool(arguments.get("bind_cycle"))
    do_proxy = True if arguments.get("proxy") is None else bool(arguments.get("proxy"))
    do_authority = True if arguments.get("authority") is None else bool(arguments.get("authority"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_targetid = True if arguments.get("use_targetid") is None else bool(arguments.get("use_targetid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_bind_cycle=do_bind_cycle,
            do_proxy=do_proxy,
            do_authority=do_authority,
            replay=replay,
            use_targetid=use_targetid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise MasqueActuationError(f"unsupported masque action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_masque_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed MASQUE authority digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "targetid": EMPTY_TARGETID,
        "authority": EMPTY_AUTHORITY,
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
            "bind",
            "proxy",
            "authority_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "targetid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    targetid = int(payload.get("targetid") or EMPTY_TARGETID)
    authority = int(payload.get("authority") or EMPTY_AUTHORITY)
    dual = port > 0 and bool(targetid) and bool(authority)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "targetid": targetid,
        "authority": authority,
        "size": int(payload.get("size") or 0),
        "port": port,
        "bind": payload.get("bind") is True,
        "proxy": payload.get("proxy") is True,
        "authority_response": payload.get("authority_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "targetid_bound": payload.get("targetid_bound") is True,
    }


def run_masque_workflow(
    *,
    with_targetid: bool = True,
    skip_bind: bool = False,
    do_bind_cycle: bool = True,
    do_proxy: bool = True,
    do_authority: bool = True,
    replay: bool = True,
    use_targetid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9298 BIND/PROXY targetid cycle workflow."""

    descriptor = masque_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MASQUE_TOOL_PROVIDER),
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
        raise MasqueActuationError(f"masque tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="masque-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = MasqueSession(out, targetid_gate=DEFAULT_TARGETID if with_targetid else EMPTY_TARGETID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "bind_cycle": do_bind_cycle,
            "proxy": do_proxy,
            "authority": do_authority,
            "replay": replay,
            "use_targetid": use_targetid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_masque_tool(session, arguments))
            except MasqueActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_masque_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_targetid
        and not skip_bind
        and do_bind_cycle
        and do_proxy
        and do_authority
        and replay
        and use_targetid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "masque_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_targetid": with_targetid,
        "skip_bind": skip_bind,
        "bind": do_bind_cycle,
        "proxy": do_proxy,
        "authority": do_authority,
        "replay": replay,
        "use_targetid": use_targetid,
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
        "targetid_value": int(publish_result.get("targetid") or independent.get("targetid") or EMPTY_TARGETID),
        "authority_value": int(publish_result.get("authority") or independent.get("authority") or EMPTY_AUTHORITY),
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
        "targetid": int(trace_body["targetid_value"] or EMPTY_TARGETID),
        "authority": int(trace_body["authority_value"] or EMPTY_AUTHORITY),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_targetid": with_targetid,
        "skip_bind": skip_bind,
        "bind_cycle": do_bind_cycle,
        "proxy_cycle": do_proxy,
        "authority_cycle": do_authority,
        "replay": replay,
        "use_targetid": use_targetid,
    }


def verify_masque_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed MASQUE trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_masque_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    targetid = int(trace.get("targetid_value") or independent.get("targetid") or EMPTY_TARGETID)
    authority = int(trace.get("authority_value") or independent.get("authority") or EMPTY_AUTHORITY)
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
        "bind": independent.get("bind") is True,
        "proxy": independent.get("proxy") is True,
        "authority_response": independent.get("authority_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "targetid_bound": independent.get("targetid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "authority_recorded": (
            port > 0
            and targetid == DEFAULT_TARGETID
            and authority == DEFAULT_AUTHORITY
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}

def masque_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.masque_actuation import "
        "builtin_masque_actuation_proof; r=builtin_masque_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='masque_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_masque_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MASQUE_ACTUATION_ID,
        name="First-class RFC 9298 MASQUE BIND/PROXY actuation",
        description=(
            "Missions that require a masque tool can opt the masque provider in, "
            "bind a loopback RFC 9298 HTTP MASQUE endpoint, complete a BIND "
            "with a non-empty targetid, lockstep a PROXY that carries the "
            "stored proxy authority, independently poll the stored proxy "
            "authority on a later socket, and seal a digest-chained authority. Default "
            "routing stays fail-closed; a missing targetid keeps the hole "
            "falsifiable, and skip-BIND/PROXY/AUTHORITY/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.masque_actuation:builtin_masque_actuation_proof",
        proof_command=masque_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.datagram-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/masque_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/connectip_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required masque tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9298 daemon, speaks a "
            "BIND then PROXY over HTTP MASQUE with a non-empty targetid and "
            "proxy authority, independently polls the stored proxy authority on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9221 QUIC DATAGRAM lockstep is proved. "
            "Missing targetids, skip-BIND, skip-PROXY, skip-authority, skip-REPLAY, "
            "and a BIND aimed without a targetid stay fail-closed. "
            "Later genesis can take RFC 9484 CONNECT-IP ASSIGN/ADVERTISE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("masque", "rfc9298", "http", "targetid", "authority", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T050041Z-3ee35fa7",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_masque_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9298 MASQUE lockstep actuation seals an authority digest."""

    from blackhole_agent.connectip_actuation import CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID
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
    checks["denylists_self"] = MASQUE_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MASQUE_ACTUATION_GOAL) == (
        MASQUE_ACTUATION_ID,
    )
    checks["leftover_text_binds_masque"] = leftover_marker_ids(MASQUE_LEFTOVER) == (
        MASQUE_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID, "connectip"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_masque"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"masque_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            MASQUE_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = MASQUE_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    checks["catalog_names_masque"] = (
        len(catalog) > 65
        and catalog[65]["id"] == MASQUE_ACTUATION_ID
        and catalog[64]["id"] == DATAGRAM_ACTUATION_ID
        and catalog[65]["source"] == "genesis_bind_masque"
    )
    checks["catalog_names_connectip"] = (
        len(catalog) > 66
        and catalog[66]["id"] == CONNECTIP_ACTUATION_ID
        and catalog[66]["source"] == "genesis_bind_connectip"
    )
    family = capability_family(MASQUE_ACTUATION_GOAL)
    checks["family_is_masque"] = "masque" in family
    checks["family_is_rfc9298"] = "rfc9298" in family
    checks["family_is_targetid"] = "targetid" in family
    checks["family_is_authority"] = "authority" in family
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
    checks["family_is_not_connectip"] = (
        "connectip" not in family
        and "rfc9484" not in family
        and "prefixid" not in family
        and "ipaddr" not in family
    )
    packed = encode_bind(identity=SENTINEL, targetid=DEFAULT_TARGETID, authority=DEFAULT_AUTHORITY)
    parsed = parse_message(packed)
    checks["bind_roundtrip"] = (
        parsed["is_bind"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_targetid"] is True
        and parsed["targetid"] == DEFAULT_TARGETID
        and parsed["authority"] == DEFAULT_AUTHORITY
        and parsed["is_response"] is False
        and parsed["is_proxy"] is False
        and parsed["type"] == FRAME_BIND
        and parsed["first_byte"] == MQ_FIRST
    )
    shook = encode_proxy(
        identity=SENTINEL,
        targetid=DEFAULT_TARGETID,
        authority=DEFAULT_AUTHORITY,
    )
    proxy_parsed = parse_message(shook)
    checks["proxy_roundtrip"] = (
        proxy_parsed["is_proxy"] is True
        and proxy_parsed["is_response"] is True
        and proxy_parsed["is_bind"] is False
        and proxy_parsed["identity"] == SENTINEL
        and proxy_parsed["targetid"] == DEFAULT_TARGETID
        and proxy_parsed["authority"] == DEFAULT_AUTHORITY
        and proxy_parsed["has_authority"] is True
        and proxy_parsed["type"] == FRAME_PROXY
        and proxy_parsed["first_byte"] == MQ_FIRST
    )
    bare = encode_bind(identity=SENTINEL, targetid=DEFAULT_TARGETID, include_targetid=False)
    checks["missing_targetid_is_unauthenticated"] = parse_message(bare)["has_targetid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    masque_signature = semantic_signature(MASQUE_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(masque_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_masque = ToolDescriptor(name="remote_masque", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_masque)
    checks["naive_mcp_masque_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = masque_tool_descriptor()
    default_masque = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MASQUE_TOOL_PROVIDER),
    )
    checks["default_masque_provider_is_unsupported"] = (
        default_masque.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{MASQUE_TOOL_PROVIDER}" in default_masque.reasons
    )
    checks["opted_in_masque_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_masque],
        required_tool_names=("local_memory", "masque"),
    )
    checks["naive_preflight_missing_masque"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["masque"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "masque"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MASQUE_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "masque" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="masque-actuation-") as tmp:
        root = Path(tmp)
        missing = run_masque_workflow(with_targetid=False, output_dir=root / "missing")
        skip_bind = run_masque_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_bind_cycle = run_masque_workflow(do_bind_cycle=False, output_dir=root / "skip-bind-cycle")
        skip_proxy = run_masque_workflow(do_proxy=False, output_dir=root / "skip-proxy")
        skip_authority = run_masque_workflow(do_authority=False, output_dir=root / "skip-authority")
        skip_replay = run_masque_workflow(replay=False, output_dir=root / "skip-replay")
        skip_targetid = run_masque_workflow(use_targetid=False, output_dir=root / "skip-targetid")
        live = run_masque_workflow(output_dir=root / "live")
        verify = verify_masque_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_masque_trace(clone)
        checks["naive_without_targetid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_targetid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_bind_cycle_stays_empty"] = (
            skip_bind_cycle["ok"] is False
            and skip_bind_cycle["error"] == "bind_required"
            and skip_bind_cycle["final_status"] == 409
            and skip_bind_cycle["payload_exists"] is False
        )
        checks["skip_proxy_stays_empty"] = (
            skip_proxy["ok"] is False
            and skip_proxy["error"] == "proxy_required"
            and skip_proxy["final_status"] == 409
            and skip_proxy["payload_exists"] is False
        )
        checks["skip_authority_stays_empty"] = (
            skip_authority["ok"] is False
            and skip_authority["error"] == "authority_required"
            and skip_authority["final_status"] == 409
            and skip_authority["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_targetid_stays_empty"] = (
            skip_targetid["ok"] is False
            and skip_targetid["error"] == "targetid_required"
            and skip_targetid["final_status"] == 409
            and skip_targetid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_authority"] = (
            int(live.get("targetid") or 0) == DEFAULT_TARGETID
            and int(live.get("authority") or 0) == DEFAULT_AUTHORITY
            and int(live.get("port") or 0) > 0
        )
        checks["token_targetid_bind_proxy_authority_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_bind_cycle["ok"] is False
            and skip_proxy["ok"] is False
            and skip_authority["ok"] is False
            and skip_replay["ok"] is False
            and skip_targetid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="masque-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MASQUE_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_masque"] = (
        live_goal == MASQUE_ACTUATION_GOAL
        and MASQUE_ACTUATION_ID in live_done
        and live_source == "genesis_bind_masque"
    )

    with tempfile.TemporaryDirectory(prefix="masque-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(MASQUE_LEFTOVER, root)
        register_catalog_proved(root, MASQUE_ACTUATION_ID)
        reason = leftover_satisfied_by(MASQUE_LEFTOVER, root)
        after = leftover_is_open(MASQUE_LEFTOVER, root)
    checks["masque_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_masque_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{MASQUE_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_masque_actuation_capability()
    return {
        "ok": ok,
        "action": "masque_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MASQUE_ACTUATION_GOAL,
        "done_when": MASQUE_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
