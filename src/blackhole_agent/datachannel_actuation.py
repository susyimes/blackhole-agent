"""Drive a first-class Data Channel tool through RFC 8831 OPEN/ACK.

Tool routing already fails missions that require ``datachannel``: hosted
datachannel endpoints stay on the unsupported MCP provider, and no
first-party datachannel provider is executable. Unbound therefore cannot
speak an OPEN, lockstep an ACK ppid handshake over SCTP Data Channel
PPID, independently poll the stored channel dcep, or seal a dcep digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``datachannel`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 8831/8832 daemon
- keep a missing-ppid client so the datachannel-ppid hole stays falsifiable
- refuse ACK verify until an OPEN lands with a non-empty ppid
- independently poll the stored channel dcep on a later client socket
- persist a sealed dcep digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after SCTP
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
    DATACHANNEL_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    datachannel_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
DATACHANNEL_ACTUATION_ID = "capability.datachannel-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-DC-OK"
POLL_TOKEN = "BH-DC-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
COMMON_HEADER_SIZE = 12
DATA_CHUNK_HEADER_SIZE = 16
DCEP_OPEN_FIXED = 12
DCEP_ACK_FIXED = 8
EMPTY_PPID = 0
EMPTY_DCEP = 0
DEFAULT_SRC_PORT = 5000
DEFAULT_DST_PORT = 5000
DEFAULT_SID = 0
DEFAULT_SSN = 0
DEFAULT_PRIORITY = 256
CHUNK_DATA = 0
FLAG_BEGIN_END = 0x03
DCEP_ACK = 0x02
DCEP_OPEN = 0x03
CHANNEL_RELIABLE = 0x00
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283


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


DATACHANNEL_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DATACHANNEL_ACTUATION_ID};"
    f"capability_proved:{DATACHANNEL_ACTUATION_ID};"
    "no_skill_route"
)
DATACHANNEL_ACTUATION_GOAL = (
    "Repair rfc8831 datachannel open/ack cycle cannot land over sctp "
    "datachannel ppid: hosted datachannel endpoints remain unsupported so an OPEN then "
    "ACK ppid handshake cannot land and a sealed dcep digest "
    "cannot be produced. A missing datachannel ppid stays forbidden; fail-closed "
    "routing never opts the datachannel provider in. An independent later poll of the "
    "stored channel dcep keeps the hole falsifiable."
)


class DatachannelActuationError(RuntimeError):
    """Raised when the Data Channel session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_ppid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"ppid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_ppid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-ppid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_dcep(ppid: int = EMPTY_PPID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"dcep:{int(ppid) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_PPID = request_ppid(SENTINEL)
DEFAULT_DCEP = request_dcep(DEFAULT_PPID, SENTINEL)


def _pad4(data: bytes) -> bytes:
    pad = (4 - (len(data) % 4)) % 4
    return bytes(data or b"") + (b"\x00" * pad)


def encode_dcep_open(*, identity: str, dcep: int) -> bytes:
    label = str(identity or "").encode("utf-8")[:255]
    protocol = b""
    return (
        struct.pack(
            "!BBHIHH",
            DCEP_OPEN,
            CHANNEL_RELIABLE,
            DEFAULT_PRIORITY,
            int(dcep) & 0xFFFFFFFF,
            len(label),
            len(protocol),
        )
        + label
        + protocol
    )


def encode_dcep_ack(*, identity: str, dcep: int) -> bytes:
    label = str(identity or "").encode("utf-8")[:255]
    return struct.pack("!BBHI", DCEP_ACK, 0, len(label), int(dcep) & 0xFFFFFFFF) + label


def encode_packet(
    message_type: int,
    *,
    identity: str,
    ppid: int,
    dcep: int,
    src_port: int = DEFAULT_SRC_PORT,
    dst_port: int = DEFAULT_DST_PORT,
    include_ppid: bool = True,
) -> bytes:
    live_ppid = int(ppid) & 0xFFFFFFFF if include_ppid else EMPTY_PPID
    live_dcep = int(dcep) & 0xFFFFFFFF if include_ppid and live_ppid else EMPTY_DCEP
    if int(message_type) == DCEP_OPEN:
        user = encode_dcep_open(identity=identity, dcep=live_dcep)
    else:
        user = encode_dcep_ack(identity=identity, dcep=live_dcep)
    chunk_length = DATA_CHUNK_HEADER_SIZE + len(user)
    chunk = _pad4(
        struct.pack("!BBH", CHUNK_DATA, FLAG_BEGIN_END, chunk_length)
        + struct.pack("!I", live_dcep)
        + struct.pack("!HH", DEFAULT_SID, DEFAULT_SSN)
        + struct.pack("!I", live_ppid)
        + user
    )
    header = struct.pack(
        "!HHI",
        int(src_port) & 0xFFFF,
        int(dst_port) & 0xFFFF,
        0,
    )
    packet = header + struct.pack("!I", 0) + chunk
    checksum = crc32c(packet)
    return header + struct.pack("!I", checksum) + chunk


def encode_open(
    *,
    identity: str,
    ppid: int,
    dcep: int | None = None,
    include_ppid: bool = True,
    src_port: int = DEFAULT_SRC_PORT,
    dst_port: int = DEFAULT_DST_PORT,
) -> bytes:
    live_ppid = int(ppid) & 0xFFFFFFFF if include_ppid else EMPTY_PPID
    live_dcep = int(dcep) if dcep is not None else request_dcep(live_ppid, identity)
    return encode_packet(
        DCEP_OPEN,
        identity=identity,
        ppid=live_ppid,
        dcep=live_dcep,
        src_port=src_port,
        dst_port=dst_port,
        include_ppid=include_ppid,
    )


def encode_ack(
    *,
    identity: str,
    ppid: int,
    dcep: int | None = None,
    include_ppid: bool = True,
    src_port: int = DEFAULT_SRC_PORT,
    dst_port: int = DEFAULT_DST_PORT,
) -> bytes:
    live_ppid = int(ppid) & 0xFFFFFFFF if include_ppid else EMPTY_PPID
    live_dcep = int(dcep) if dcep is not None else request_dcep(live_ppid, identity)
    return encode_packet(
        DCEP_ACK,
        identity=identity,
        ppid=live_ppid,
        dcep=live_dcep,
        src_port=src_port,
        dst_port=dst_port,
        include_ppid=include_ppid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < COMMON_HEADER_SIZE + DATA_CHUNK_HEADER_SIZE:
        raise DatachannelActuationError("short_packet")
    src_port, dst_port, header_vtag, checksum = struct.unpack("!HHII", raw[:COMMON_HEADER_SIZE])
    zeroed = raw[:8] + struct.pack("!I", 0) + raw[COMMON_HEADER_SIZE:]
    if int(checksum) != crc32c(zeroed):
        raise DatachannelActuationError("checksum_failed")
    chunk_type, _flags, chunk_length = struct.unpack(
        "!BBH", raw[COMMON_HEADER_SIZE : COMMON_HEADER_SIZE + 4]
    )
    if int(chunk_type) != CHUNK_DATA:
        raise DatachannelActuationError("illegal_chunk")
    end = COMMON_HEADER_SIZE + int(chunk_length)
    if int(chunk_length) < DATA_CHUNK_HEADER_SIZE or end > len(raw):
        raise DatachannelActuationError("short_packet")
    body = raw[COMMON_HEADER_SIZE + 4 : end]
    tsn = struct.unpack("!I", body[:4])[0]
    sid, ssn = struct.unpack("!HH", body[4:8])
    live_ppid = struct.unpack("!I", body[8:12])[0]
    user = body[12:]
    if not user:
        raise DatachannelActuationError("illegal_dcep")
    message_type = int(user[0])
    if message_type not in {DCEP_OPEN, DCEP_ACK}:
        raise DatachannelActuationError("illegal_dcep")
    identity = ""
    live_dcep = int(tsn)
    if message_type == DCEP_OPEN:
        if len(user) < DCEP_OPEN_FIXED:
            raise DatachannelActuationError("short_packet")
        _typ, _channel, _priority, reliability, label_len, proto_len = struct.unpack(
            "!BBHIHH", user[:DCEP_OPEN_FIXED]
        )
        label_end = DCEP_OPEN_FIXED + int(label_len)
        if label_end + int(proto_len) > len(user):
            raise DatachannelActuationError("short_packet")
        identity = user[DCEP_OPEN_FIXED:label_end].decode("utf-8", errors="replace")
        live_dcep = int(reliability)
    else:
        if len(user) < DCEP_ACK_FIXED:
            raise DatachannelActuationError("short_packet")
        _typ, _reserved, label_len, ack_dcep = struct.unpack("!BBHI", user[:DCEP_ACK_FIXED])
        label_end = DCEP_ACK_FIXED + int(label_len)
        if label_end > len(user):
            raise DatachannelActuationError("short_packet")
        identity = user[DCEP_ACK_FIXED:label_end].decode("utf-8", errors="replace")
        live_dcep = int(ack_dcep)
    has_ppid = int(live_ppid) != EMPTY_PPID
    has_dcep = has_ppid and int(live_dcep) != EMPTY_DCEP
    is_open = message_type == DCEP_OPEN
    is_ack = message_type == DCEP_ACK
    return {
        "type": message_type,
        "is_open": is_open,
        "is_ack": is_ack,
        "is_response": is_ack,
        "src_port": int(src_port),
        "dst_port": int(dst_port),
        "header_vtag": int(header_vtag),
        "ppid": int(live_ppid),
        "has_ppid": has_ppid,
        "dcep": int(live_dcep),
        "has_dcep": has_dcep,
        "tsn": int(tsn),
        "sid": int(sid),
        "ssn": int(ssn),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "chunk_type": int(chunk_type),
    }


class _DatachannelClient:
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
            raise DatachannelActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_ack"] or not packet["is_response"]:
            raise DatachannelActuationError("dcep_required")
        if not packet["has_ppid"]:
            raise DatachannelActuationError("ppid_required")
        if not packet["has_dcep"]:
            raise DatachannelActuationError("dcep_required")
        return packet

    def exchange(self, packet: bytes, *, wait_dcep: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_dcep:
            raise DatachannelActuationError("dcep_required")
        reply = self._recv()
        return {
            "ack": reply,
            "ppid": int(reply.get("ppid") or EMPTY_PPID),
            "identity": str(reply.get("identity") or ""),
            "dcep": int(reply.get("dcep") or EMPTY_DCEP),
        }

    def ack(
        self,
        identity: str,
        ppid: int,
        dcep: int = EMPTY_DCEP,
        *,
        wait_dcep: bool = True,
        include_ppid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_ack(
            identity=identity,
            ppid=ppid,
            dcep=dcep or request_dcep(ppid, identity),
            include_ppid=include_ppid,
            src_port=self.client_port,
            dst_port=self.port,
        )
        return self.exchange(packet, wait_dcep=wait_dcep)


class DatachannelSession:
    """PPID-gated loopback RFC 8831 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        ppid_gate: int = DEFAULT_PPID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ppid_gate = int(ppid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.ppid = EMPTY_PPID
        self.dcep = EMPTY_DCEP
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.opened = False
        self.acked = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_ppid_once(self, identity: str, ppid: int, dcep: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(ppid or EMPTY_PPID)
            live_dcep = int(dcep or EMPTY_DCEP)
            if not self.identity and name and live:
                self.identity = name
                self.ppid = live
                self.dcep = live_dcep or request_dcep(live, name)
                self.stored = True
            return str(self.identity), int(self.ppid), int(self.dcep)

    def read_ppid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.ppid), int(self.dcep)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "ppid": EMPTY_PPID,
            "dcep": EMPTY_DCEP,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _ppid_missing(self) -> bool:
        return not int(self.ppid_gate or 0)

    def _reply_ack(self, peer: tuple[str, int], identity: str, ppid: int, dcep: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_ack(
            identity=identity,
            ppid=ppid,
            dcep=dcep,
            src_port=int(self.port or DEFAULT_SRC_PORT),
            dst_port=int(peer[1]),
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
            except DatachannelActuationError:
                continue
            if not packet.get("is_open") and not packet.get("is_ack"):
                continue
            if not packet.get("has_ppid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_ppid, stored_dcep = self.store_ppid_once(
                identity,
                int(packet.get("ppid") or EMPTY_PPID),
                int(packet.get("dcep") or EMPTY_DCEP),
            )
            if not stored_name or not stored_ppid or not stored_dcep:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_open"):
                    self.opened = True
                if packet.get("is_ack"):
                    self.acked = True
                self.retrieved = True
            self._reply_ack(peer, stored_name, stored_ppid, stored_dcep)

    def bind(self) -> dict[str, Any]:
        if self._ppid_missing():
            return self._forbidden("missing_ppid")
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
        do_open: bool = True,
        do_ack: bool = True,
        do_dcep: bool = True,
        replay: bool = True,
        use_ppid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._ppid_missing():
            return self._forbidden("missing_ppid")
        live_token = str(token or SENTINEL)
        origin_ppid = request_ppid(live_token)
        origin_dcep = request_dcep(origin_ppid, live_token)
        client: _DatachannelClient | None = None
        independent: _DatachannelClient | None = None
        try:
            client = _DatachannelClient(self.host, int(self.port))
            if not do_open:
                return self._conflict("open_required")
            open_packet = encode_open(
                identity=live_token,
                ppid=origin_ppid,
                dcep=origin_dcep,
                include_ppid=use_ppid,
                src_port=client.client_port,
                dst_port=int(self.port),
            )
            if not use_ppid:
                try:
                    client.exchange(open_packet, wait_dcep=True)
                except DatachannelActuationError:
                    return self._conflict("ppid_required")
                return self._conflict("ppid_required")
            client.send(open_packet)
            if not do_ack:
                return self._conflict("ack_required")
            ack_packet = encode_ack(
                identity=live_token,
                ppid=origin_ppid,
                dcep=origin_dcep,
                include_ppid=True,
                src_port=client.client_port,
                dst_port=int(self.port),
            )
            if not do_dcep:
                try:
                    client.exchange(ack_packet, wait_dcep=False)
                except DatachannelActuationError as error:
                    if str(error) == "dcep_required":
                        return self._conflict("dcep_required")
                    return self._conflict("dcep_required")
                return self._conflict("dcep_required")
            try:
                reply = client.exchange(ack_packet, wait_dcep=True)
            except DatachannelActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("ppid_required")
                if reason == "dcep_required":
                    return self._conflict("dcep_required")
                return self._conflict("open_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("open_required")
            if int(reply.get("ppid") or EMPTY_PPID) != origin_ppid:
                return self._conflict("dcep_required")
            if int(reply.get("dcep") or EMPTY_DCEP) != origin_dcep:
                return self._conflict("dcep_required")
            self.retrieved = True
            if replay:
                independent = _DatachannelClient(self.host, int(self.port))
                try:
                    poll = independent.ack(
                        POLL_TOKEN,
                        poll_ppid(live_token),
                        request_dcep(poll_ppid(live_token), POLL_TOKEN),
                        wait_dcep=True,
                    )
                except DatachannelActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_ppid, stored_dcep = self.read_ppid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_ppid != origin_ppid
                    or stored_dcep != origin_dcep
                    or int(poll.get("ppid") or EMPTY_PPID) != origin_ppid
                    or int(poll.get("dcep") or EMPTY_DCEP) != origin_dcep
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_ppid}:{origin_dcep}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "ppid": origin_ppid,
                "dcep": origin_dcep,
                "open": True,
                "ack": True,
                "dcep_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "ppid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_datachannel_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "ppid": origin_ppid,
                "dcep": origin_dcep,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "open": True,
                "ack": True,
                "dcep_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "ppid_bound": True,
            }
        except (OSError, DatachannelActuationError) as error:
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
        live = independent_datachannel_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "ppid": int(live.get("ppid") or EMPTY_PPID),
            "dcep": int(live.get("dcep") or EMPTY_DCEP),
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


def call_datachannel_tool(session: DatachannelSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one Data Channel tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_open = True if arguments.get("open") is None else bool(arguments.get("open"))
    do_ack = True if arguments.get("ack") is None else bool(arguments.get("ack"))
    do_dcep = True if arguments.get("dcep") is None else bool(arguments.get("dcep"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_ppid = True if arguments.get("use_ppid") is None else bool(arguments.get("use_ppid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_open=do_open,
            do_ack=do_ack,
            do_dcep=do_dcep,
            replay=replay,
            use_ppid=use_ppid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise DatachannelActuationError(f"unsupported datachannel action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_datachannel_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed Data Channel dcep digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "ppid": EMPTY_PPID,
        "dcep": EMPTY_DCEP,
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
            "open",
            "ack",
            "dcep_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "ppid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    ppid = int(payload.get("ppid") or EMPTY_PPID)
    dcep = int(payload.get("dcep") or EMPTY_DCEP)
    dual = port > 0 and bool(ppid) and bool(dcep)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "ppid": ppid,
        "dcep": dcep,
        "size": int(payload.get("size") or 0),
        "port": port,
        "open": payload.get("open") is True,
        "ack": payload.get("ack") is True,
        "dcep_response": payload.get("dcep_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "ppid_bound": payload.get("ppid_bound") is True,
    }


def run_datachannel_workflow(
    *,
    with_ppid: bool = True,
    skip_bind: bool = False,
    do_open: bool = True,
    do_ack: bool = True,
    do_dcep: bool = True,
    replay: bool = True,
    use_ppid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 8831 OPEN/ACK ppid cycle workflow."""

    descriptor = datachannel_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DATACHANNEL_TOOL_PROVIDER),
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
        raise DatachannelActuationError(f"datachannel tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="datachannel-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = DatachannelSession(out, ppid_gate=DEFAULT_PPID if with_ppid else EMPTY_PPID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "open": do_open,
            "ack": do_ack,
            "dcep": do_dcep,
            "replay": replay,
            "use_ppid": use_ppid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_datachannel_tool(session, arguments))
            except DatachannelActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_datachannel_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_ppid
        and not skip_bind
        and do_open
        and do_ack
        and do_dcep
        and replay
        and use_ppid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "datachannel_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_ppid": with_ppid,
        "skip_bind": skip_bind,
        "open": do_open,
        "ack": do_ack,
        "dcep": do_dcep,
        "replay": replay,
        "use_ppid": use_ppid,
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
        "ppid_value": int(publish_result.get("ppid") or independent.get("ppid") or EMPTY_PPID),
        "dcep_value": int(publish_result.get("dcep") or independent.get("dcep") or EMPTY_DCEP),
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
        "ppid": int(trace_body["ppid_value"] or EMPTY_PPID),
        "dcep": int(trace_body["dcep_value"] or EMPTY_DCEP),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_ppid": with_ppid,
        "skip_bind": skip_bind,
        "open": do_open,
        "ack": do_ack,
        "dcep_cycle": do_dcep,
        "replay": replay,
        "use_ppid": use_ppid,
    }


def verify_datachannel_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Data Channel trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_datachannel_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    ppid = int(trace.get("ppid_value") or independent.get("ppid") or EMPTY_PPID)
    dcep = int(trace.get("dcep_value") or independent.get("dcep") or EMPTY_DCEP)
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
        "open": independent.get("open") is True,
        "ack": independent.get("ack") is True,
        "dcep_response": independent.get("dcep_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "ppid_bound": independent.get("ppid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "dcep_recorded": (
            port > 0
            and ppid == DEFAULT_PPID
            and dcep == DEFAULT_DCEP
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def datachannel_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.datachannel_actuation import "
        "builtin_datachannel_actuation_proof; r=builtin_datachannel_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='datachannel_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_datachannel_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=DATACHANNEL_ACTUATION_ID,
        name="First-class RFC 8831 Data Channel OPEN/ACK actuation",
        description=(
            "Missions that require a datachannel tool can opt the datachannel "
            "provider in, bind a loopback RFC 8831 SCTP Data Channel endpoint, "
            "complete an OPEN with a non-empty ppid, lockstep an ACK that "
            "carries the stored channel dcep, independently poll the stored "
            "channel dcep on a later socket, and seal a digest-chained dcep. "
            "Default routing stays fail-closed; a missing ppid keeps the hole "
            "falsifiable, and skip-OPEN/ACK/DCEP/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.datachannel_actuation:builtin_datachannel_actuation_proof",
        proof_command=datachannel_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.sctp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/datachannel_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/quic_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required datachannel tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 8831 daemon, speaks an "
            "OPEN then ACK over SCTP Data Channel with a non-empty ppid and "
            "channel dcep, independently polls the stored channel dcep on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 4960 SCTP lockstep is proved. "
            "Missing ppids, skip-OPEN, skip-ACK, skip-dcep, skip-REPLAY, "
            "and an OPEN aimed without a ppid stay fail-closed. "
            "Later genesis can take RFC 9000 QUIC INITIAL/HANDSHAKE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("datachannel", "rfc8831", "sctp", "ppid", "dcep", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260902T021957Z-8977004f",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_datachannel_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 8831 Data Channel lockstep actuation seals a dcep digest."""

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

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = DATACHANNEL_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(DATACHANNEL_ACTUATION_GOAL) == (
        DATACHANNEL_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (QUIC_ACTUATION_GOAL, QUIC_ACTUATION_ID, "quic"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_datachannel"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"datachannel_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            DATACHANNEL_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = DATACHANNEL_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    checks["catalog_names_datachannel"] = (
        len(catalog) > 60
        and catalog[60]["id"] == DATACHANNEL_ACTUATION_ID
        and catalog[59]["id"] == SCTP_ACTUATION_ID
        and catalog[60]["source"] == "genesis_bind_datachannel"
    )
    checks["catalog_names_quic"] = (
        len(catalog) > 61
        and catalog[61]["id"] == QUIC_ACTUATION_ID
        and catalog[61]["source"] == "genesis_bind_quic"
    )
    family = capability_family(DATACHANNEL_ACTUATION_GOAL)
    checks["family_is_datachannel"] = "datachannel" in family
    checks["family_is_rfc8831"] = "rfc8831" in family
    checks["family_is_ppid"] = "ppid" in family
    checks["family_is_dcep"] = "dcep" in family
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
    checks["family_is_not_quic"] = (
        "quic" not in family
        and "rfc9000" not in family
        and "dcid" not in family
        and "pktnum" not in family
    )
    packed = encode_open(identity=SENTINEL, ppid=DEFAULT_PPID, dcep=DEFAULT_DCEP)
    parsed = parse_message(packed)
    checks["open_roundtrip"] = (
        parsed["is_open"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_ppid"] is True
        and parsed["ppid"] == DEFAULT_PPID
        and parsed["dcep"] == DEFAULT_DCEP
        and parsed["is_response"] is False
        and parsed["is_ack"] is False
        and parsed["type"] == DCEP_OPEN
        and parsed["chunk_type"] == CHUNK_DATA
    )
    acked = encode_ack(
        identity=SENTINEL,
        ppid=DEFAULT_PPID,
        dcep=DEFAULT_DCEP,
    )
    ack_parsed = parse_message(acked)
    checks["ack_roundtrip"] = (
        ack_parsed["is_ack"] is True
        and ack_parsed["is_response"] is True
        and ack_parsed["is_open"] is False
        and ack_parsed["identity"] == SENTINEL
        and ack_parsed["ppid"] == DEFAULT_PPID
        and ack_parsed["dcep"] == DEFAULT_DCEP
        and ack_parsed["has_dcep"] is True
        and ack_parsed["type"] == DCEP_ACK
    )
    bare = encode_open(identity=SENTINEL, ppid=DEFAULT_PPID, include_ppid=False)
    checks["missing_ppid_is_unauthenticated"] = parse_message(bare)["has_ppid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    datachannel_signature = semantic_signature(DATACHANNEL_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(datachannel_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_datachannel = ToolDescriptor(name="remote_datachannel", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_datachannel)
    checks["naive_mcp_datachannel_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = datachannel_tool_descriptor()
    default_datachannel = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DATACHANNEL_TOOL_PROVIDER),
    )
    checks["default_datachannel_provider_is_unsupported"] = (
        default_datachannel.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{DATACHANNEL_TOOL_PROVIDER}" in default_datachannel.reasons
    )
    checks["opted_in_datachannel_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_datachannel],
        required_tool_names=("local_memory", "datachannel"),
    )
    checks["naive_preflight_missing_datachannel"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["datachannel"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "datachannel"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DATACHANNEL_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "datachannel" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="datachannel-actuation-") as tmp:
        root = Path(tmp)
        missing = run_datachannel_workflow(with_ppid=False, output_dir=root / "missing")
        skip_bind = run_datachannel_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_open = run_datachannel_workflow(do_open=False, output_dir=root / "skip-open")
        skip_ack = run_datachannel_workflow(do_ack=False, output_dir=root / "skip-ack")
        skip_dcep = run_datachannel_workflow(do_dcep=False, output_dir=root / "skip-dcep")
        skip_replay = run_datachannel_workflow(replay=False, output_dir=root / "skip-replay")
        skip_ppid = run_datachannel_workflow(use_ppid=False, output_dir=root / "skip-ppid")
        live = run_datachannel_workflow(output_dir=root / "live")
        verify = verify_datachannel_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_datachannel_trace(clone)
        checks["naive_without_ppid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_ppid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_open_stays_empty"] = (
            skip_open["ok"] is False
            and skip_open["error"] == "open_required"
            and skip_open["final_status"] == 409
            and skip_open["payload_exists"] is False
        )
        checks["skip_ack_stays_empty"] = (
            skip_ack["ok"] is False
            and skip_ack["error"] == "ack_required"
            and skip_ack["final_status"] == 409
            and skip_ack["payload_exists"] is False
        )
        checks["skip_dcep_stays_empty"] = (
            skip_dcep["ok"] is False
            and skip_dcep["error"] == "dcep_required"
            and skip_dcep["final_status"] == 409
            and skip_dcep["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_ppid_stays_empty"] = (
            skip_ppid["ok"] is False
            and skip_ppid["error"] == "ppid_required"
            and skip_ppid["final_status"] == 409
            and skip_ppid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_dcep"] = (
            int(live.get("ppid") or 0) == DEFAULT_PPID
            and int(live.get("dcep") or 0) == DEFAULT_DCEP
            and int(live.get("port") or 0) > 0
        )
        checks["token_ppid_open_ack_dcep_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_open["ok"] is False
            and skip_ack["ok"] is False
            and skip_dcep["ok"] is False
            and skip_replay["ok"] is False
            and skip_ppid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="datachannel-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != DATACHANNEL_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_datachannel"] = (
        live_goal == DATACHANNEL_ACTUATION_GOAL
        and DATACHANNEL_ACTUATION_ID in live_done
        and live_source == "genesis_bind_datachannel"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_datachannel_actuation_capability()
    return {
        "ok": ok,
        "action": "datachannel_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": DATACHANNEL_ACTUATION_GOAL,
        "done_when": DATACHANNEL_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
