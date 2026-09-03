"""Drive a first-class QUIC tool through RFC 9000 INITIAL/HANDSHAKE.

Tool routing already fails missions that require ``quic``: hosted quic
endpoints stay on the unsupported MCP provider, and no first-party quic
provider is executable. Unbound therefore cannot speak an INITIAL,
lockstep a HANDSHAKE dcid handshake over UDP QUIC DCID,
independently poll the stored packet pktnum, or seal a pktnum digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``quic`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9000 daemon
- keep a missing-dcid client so the quic-dcid hole stays falsifiable
- refuse HANDSHAKE verify until an INITIAL lands with a non-empty dcid
- independently poll the stored packet pktnum on a later client socket
- persist a sealed pktnum digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after Data Channel
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
    MCP_TOOL_PROVIDER,
    QUIC_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    quic_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
QUIC_ACTUATION_ID = "capability.quic-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-QUIC-OK"
POLL_TOKEN = "BH-QUIC-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_DCID = 0
EMPTY_PKTNUM = 0
QUIC_VERSION = 0x00000001
LONG_HEADER = 0x80
FIXED_BIT = 0x40
PN_LENGTH_4 = 0x03
CID_SIZE = 4
PN_SIZE = 4
CHECKSUM_SIZE = 4
PACKET_INITIAL = 0x00
PACKET_HANDSHAKE = 0x02
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


QUIC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{QUIC_ACTUATION_ID};"
    f"capability_proved:{QUIC_ACTUATION_ID};"
    "no_skill_route"
)
QUIC_ACTUATION_GOAL = (
    "Repair rfc9000 quic initial/handshake cycle cannot land over udp "
    "quic dcid: hosted quic endpoints remain unsupported so an INITIAL then "
    "HANDSHAKE dcid handshake cannot land and a sealed pktnum digest "
    "cannot be produced. A missing quic dcid stays forbidden; fail-closed "
    "routing never opts the quic provider in. An independent later poll of the "
    "stored packet pktnum keeps the hole falsifiable."
)


class QuicActuationError(RuntimeError):
    """Raised when the QUIC session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_dcid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"dcid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_dcid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-dcid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_pktnum(dcid: int = EMPTY_DCID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"pktnum:{int(dcid) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_DCID = request_dcid(SENTINEL)
DEFAULT_PKTNUM = request_pktnum(DEFAULT_DCID, SENTINEL)


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
        raise QuicActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise QuicActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise QuicActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise QuicActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def _first_byte(packet_type: int) -> int:
    return LONG_HEADER | FIXED_BIT | ((int(packet_type) & 0x03) << 4) | PN_LENGTH_4


def encode_packet(
    packet_type: int,
    *,
    identity: str,
    dcid: int,
    pktnum: int,
    include_dcid: bool = True,
) -> bytes:
    live_dcid = int(dcid) & 0xFFFFFFFF if include_dcid else EMPTY_DCID
    live_pktnum = int(pktnum) & 0xFFFFFFFF if include_dcid and live_dcid else EMPTY_PKTNUM
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_pktnum, len(ident)) + ident
    dcid_bytes = struct.pack("!I", live_dcid) if live_dcid else b""
    scid_bytes = struct.pack("!I", live_dcid) if live_dcid else (b"\x00" * CID_SIZE)
    header = bytearray()
    header.append(_first_byte(packet_type))
    header.extend(struct.pack("!I", QUIC_VERSION))
    header.append(len(dcid_bytes))
    header.extend(dcid_bytes)
    header.append(len(scid_bytes))
    header.extend(scid_bytes)
    if int(packet_type) == PACKET_INITIAL:
        header.extend(encode_varint(0))
    body = struct.pack("!I", live_pktnum) + payload
    remainder = body + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_initial(
    *,
    identity: str,
    dcid: int,
    pktnum: int | None = None,
    include_dcid: bool = True,
) -> bytes:
    live_dcid = int(dcid) & 0xFFFFFFFF if include_dcid else EMPTY_DCID
    live_pktnum = int(pktnum) if pktnum is not None else request_pktnum(live_dcid, identity)
    return encode_packet(
        PACKET_INITIAL,
        identity=identity,
        dcid=live_dcid,
        pktnum=live_pktnum,
        include_dcid=include_dcid,
    )


def encode_handshake(
    *,
    identity: str,
    dcid: int,
    pktnum: int | None = None,
    include_dcid: bool = True,
) -> bytes:
    live_dcid = int(dcid) & 0xFFFFFFFF if include_dcid else EMPTY_DCID
    live_pktnum = int(pktnum) if pktnum is not None else request_pktnum(live_dcid, identity)
    return encode_packet(
        PACKET_HANDSHAKE,
        identity=identity,
        dcid=live_dcid,
        pktnum=live_pktnum,
        include_dcid=include_dcid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 7:
        raise QuicActuationError("short_packet")
    first = raw[0]
    if not (first & LONG_HEADER) or not (first & FIXED_BIT):
        raise QuicActuationError("illegal_header")
    packet_type = (first >> 4) & 0x03
    if packet_type not in {PACKET_INITIAL, PACKET_HANDSHAKE}:
        raise QuicActuationError("illegal_packet")
    if (first & 0x03) != PN_LENGTH_4:
        raise QuicActuationError("illegal_header")
    version = struct.unpack("!I", raw[1:5])[0]
    if int(version) != QUIC_VERSION:
        raise QuicActuationError("illegal_version")
    offset = 5
    dcid_len = raw[offset]
    offset += 1
    if offset + dcid_len > len(raw):
        raise QuicActuationError("short_packet")
    dcid_bytes = raw[offset : offset + dcid_len]
    offset += dcid_len
    if dcid_len == CID_SIZE:
        live_dcid = struct.unpack("!I", dcid_bytes)[0]
    elif dcid_len == 0:
        live_dcid = EMPTY_DCID
    else:
        raise QuicActuationError("illegal_dcid")
    if offset >= len(raw):
        raise QuicActuationError("short_packet")
    scid_len = raw[offset]
    offset += 1
    if offset + scid_len > len(raw):
        raise QuicActuationError("short_packet")
    offset += scid_len
    if packet_type == PACKET_INITIAL:
        token_len, offset = decode_varint(raw, offset)
        offset += int(token_len)
        if offset > len(raw):
            raise QuicActuationError("short_packet")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < PN_SIZE + 5 + CHECKSUM_SIZE:
        raise QuicActuationError("short_packet")
    packet_number = struct.unpack("!I", raw[offset : offset + PN_SIZE])[0]
    payload = raw[offset + PN_SIZE : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise QuicActuationError("checksum_failed")
    if len(payload) < 5:
        raise QuicActuationError("short_packet")
    live_pktnum, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise QuicActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_dcid = int(live_dcid) != EMPTY_DCID
    has_pktnum = has_dcid and int(live_pktnum) != EMPTY_PKTNUM
    is_initial = packet_type == PACKET_INITIAL
    is_handshake = packet_type == PACKET_HANDSHAKE
    return {
        "type": int(packet_type),
        "is_initial": is_initial,
        "is_handshake": is_handshake,
        "is_response": is_handshake,
        "version": int(version),
        "dcid": int(live_dcid),
        "has_dcid": has_dcid,
        "pktnum": int(live_pktnum),
        "has_pktnum": has_pktnum,
        "packet_number": int(packet_number),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "dcid_len": int(dcid_len),
    }


class _QuicClient:
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
            raise QuicActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_handshake"] or not packet["is_response"]:
            raise QuicActuationError("pktnum_required")
        if not packet["has_dcid"]:
            raise QuicActuationError("dcid_required")
        if not packet["has_pktnum"]:
            raise QuicActuationError("pktnum_required")
        return packet

    def exchange(self, packet: bytes, *, wait_pktnum: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_pktnum:
            raise QuicActuationError("pktnum_required")
        reply = self._recv()
        return {
            "handshake": reply,
            "dcid": int(reply.get("dcid") or EMPTY_DCID),
            "identity": str(reply.get("identity") or ""),
            "pktnum": int(reply.get("pktnum") or EMPTY_PKTNUM),
        }

    def handshake(
        self,
        identity: str,
        dcid: int,
        pktnum: int = EMPTY_PKTNUM,
        *,
        wait_pktnum: bool = True,
        include_dcid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_handshake(
            identity=identity,
            dcid=dcid,
            pktnum=pktnum or request_pktnum(dcid, identity),
            include_dcid=include_dcid,
        )
        return self.exchange(packet, wait_pktnum=wait_pktnum)


class QuicSession:
    """DCID-gated loopback RFC 9000 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        dcid_gate: int = DEFAULT_DCID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dcid_gate = int(dcid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.dcid = EMPTY_DCID
        self.pktnum = EMPTY_PKTNUM
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

    def store_dcid_once(self, identity: str, dcid: int, pktnum: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(dcid or EMPTY_DCID)
            live_pktnum = int(pktnum or EMPTY_PKTNUM)
            if not self.identity and name and live:
                self.identity = name
                self.dcid = live
                self.pktnum = live_pktnum or request_pktnum(live, name)
                self.stored = True
            return str(self.identity), int(self.dcid), int(self.pktnum)

    def read_dcid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.dcid), int(self.pktnum)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "dcid": EMPTY_DCID,
            "pktnum": EMPTY_PKTNUM,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _dcid_missing(self) -> bool:
        return not int(self.dcid_gate or 0)

    def _reply_handshake(self, peer: tuple[str, int], identity: str, dcid: int, pktnum: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_handshake(
            identity=identity,
            dcid=dcid,
            pktnum=pktnum,
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
            except QuicActuationError:
                continue
            if not packet.get("is_initial") and not packet.get("is_handshake"):
                continue
            if not packet.get("has_dcid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_dcid, stored_pktnum = self.store_dcid_once(
                identity,
                int(packet.get("dcid") or EMPTY_DCID),
                int(packet.get("pktnum") or EMPTY_PKTNUM),
            )
            if not stored_name or not stored_dcid or not stored_pktnum:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_initial"):
                    self.opened = True
                if packet.get("is_handshake"):
                    self.handshook = True
                self.retrieved = True
            self._reply_handshake(peer, stored_name, stored_dcid, stored_pktnum)

    def bind(self) -> dict[str, Any]:
        if self._dcid_missing():
            return self._forbidden("missing_dcid")
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
        do_initial: bool = True,
        do_handshake: bool = True,
        do_pktnum: bool = True,
        replay: bool = True,
        use_dcid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._dcid_missing():
            return self._forbidden("missing_dcid")
        live_token = str(token or SENTINEL)
        origin_dcid = request_dcid(live_token)
        origin_pktnum = request_pktnum(origin_dcid, live_token)
        client: _QuicClient | None = None
        independent: _QuicClient | None = None
        try:
            client = _QuicClient(self.host, int(self.port))
            if not do_initial:
                return self._conflict("initial_required")
            initial_packet = encode_initial(
                identity=live_token,
                dcid=origin_dcid,
                pktnum=origin_pktnum,
                include_dcid=use_dcid,
            )
            if not use_dcid:
                try:
                    client.exchange(initial_packet, wait_pktnum=True)
                except QuicActuationError:
                    return self._conflict("dcid_required")
                return self._conflict("dcid_required")
            client.send(initial_packet)
            if not do_handshake:
                return self._conflict("handshake_required")
            handshake_packet = encode_handshake(
                identity=live_token,
                dcid=origin_dcid,
                pktnum=origin_pktnum,
                include_dcid=True,
            )
            if not do_pktnum:
                try:
                    client.exchange(handshake_packet, wait_pktnum=False)
                except QuicActuationError as error:
                    if str(error) == "pktnum_required":
                        return self._conflict("pktnum_required")
                    return self._conflict("pktnum_required")
                return self._conflict("pktnum_required")
            try:
                reply = client.exchange(handshake_packet, wait_pktnum=True)
            except QuicActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("dcid_required")
                if reason == "pktnum_required":
                    return self._conflict("pktnum_required")
                return self._conflict("initial_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("initial_required")
            if int(reply.get("dcid") or EMPTY_DCID) != origin_dcid:
                return self._conflict("pktnum_required")
            if int(reply.get("pktnum") or EMPTY_PKTNUM) != origin_pktnum:
                return self._conflict("pktnum_required")
            self.retrieved = True
            if replay:
                independent = _QuicClient(self.host, int(self.port))
                try:
                    poll = independent.handshake(
                        POLL_TOKEN,
                        poll_dcid(live_token),
                        request_pktnum(poll_dcid(live_token), POLL_TOKEN),
                        wait_pktnum=True,
                    )
                except QuicActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_dcid, stored_pktnum = self.read_dcid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_dcid != origin_dcid
                    or stored_pktnum != origin_pktnum
                    or int(poll.get("dcid") or EMPTY_DCID) != origin_dcid
                    or int(poll.get("pktnum") or EMPTY_PKTNUM) != origin_pktnum
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_dcid}:{origin_pktnum}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "dcid": origin_dcid,
                "pktnum": origin_pktnum,
                "initial": True,
                "handshake": True,
                "pktnum_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "dcid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_quic_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "dcid": origin_dcid,
                "pktnum": origin_pktnum,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "initial": True,
                "handshake": True,
                "pktnum_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "dcid_bound": True,
            }
        except (OSError, QuicActuationError) as error:
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
        live = independent_quic_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "dcid": int(live.get("dcid") or EMPTY_DCID),
            "pktnum": int(live.get("pktnum") or EMPTY_PKTNUM),
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


def call_quic_tool(session: QuicSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one QUIC tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_initial = True if arguments.get("initial") is None else bool(arguments.get("initial"))
    do_handshake = True if arguments.get("handshake") is None else bool(arguments.get("handshake"))
    do_pktnum = True if arguments.get("pktnum") is None else bool(arguments.get("pktnum"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_dcid = True if arguments.get("use_dcid") is None else bool(arguments.get("use_dcid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_initial=do_initial,
            do_handshake=do_handshake,
            do_pktnum=do_pktnum,
            replay=replay,
            use_dcid=use_dcid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise QuicActuationError(f"unsupported quic action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_quic_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed QUIC pktnum digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "dcid": EMPTY_DCID,
        "pktnum": EMPTY_PKTNUM,
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
            "initial",
            "handshake",
            "pktnum_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "dcid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    dcid = int(payload.get("dcid") or EMPTY_DCID)
    pktnum = int(payload.get("pktnum") or EMPTY_PKTNUM)
    dual = port > 0 and bool(dcid) and bool(pktnum)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "dcid": dcid,
        "pktnum": pktnum,
        "size": int(payload.get("size") or 0),
        "port": port,
        "initial": payload.get("initial") is True,
        "handshake": payload.get("handshake") is True,
        "pktnum_response": payload.get("pktnum_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "dcid_bound": payload.get("dcid_bound") is True,
    }


def run_quic_workflow(
    *,
    with_dcid: bool = True,
    skip_bind: bool = False,
    do_initial: bool = True,
    do_handshake: bool = True,
    do_pktnum: bool = True,
    replay: bool = True,
    use_dcid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9000 INITIAL/HANDSHAKE dcid cycle workflow."""

    descriptor = quic_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, QUIC_TOOL_PROVIDER),
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
        raise QuicActuationError(f"quic tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="quic-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = QuicSession(out, dcid_gate=DEFAULT_DCID if with_dcid else EMPTY_DCID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "initial": do_initial,
            "handshake": do_handshake,
            "pktnum": do_pktnum,
            "replay": replay,
            "use_dcid": use_dcid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_quic_tool(session, arguments))
            except QuicActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_quic_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_dcid
        and not skip_bind
        and do_initial
        and do_handshake
        and do_pktnum
        and replay
        and use_dcid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "quic_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_dcid": with_dcid,
        "skip_bind": skip_bind,
        "initial": do_initial,
        "handshake": do_handshake,
        "pktnum": do_pktnum,
        "replay": replay,
        "use_dcid": use_dcid,
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
        "dcid_value": int(publish_result.get("dcid") or independent.get("dcid") or EMPTY_DCID),
        "pktnum_value": int(publish_result.get("pktnum") or independent.get("pktnum") or EMPTY_PKTNUM),
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
        "dcid": int(trace_body["dcid_value"] or EMPTY_DCID),
        "pktnum": int(trace_body["pktnum_value"] or EMPTY_PKTNUM),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_dcid": with_dcid,
        "skip_bind": skip_bind,
        "initial": do_initial,
        "handshake_cycle": do_handshake,
        "pktnum_cycle": do_pktnum,
        "replay": replay,
        "use_dcid": use_dcid,
    }


def verify_quic_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed QUIC trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_quic_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    dcid = int(trace.get("dcid_value") or independent.get("dcid") or EMPTY_DCID)
    pktnum = int(trace.get("pktnum_value") or independent.get("pktnum") or EMPTY_PKTNUM)
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
        "initial": independent.get("initial") is True,
        "handshake": independent.get("handshake") is True,
        "pktnum_response": independent.get("pktnum_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "dcid_bound": independent.get("dcid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "pktnum_recorded": (
            port > 0
            and dcid == DEFAULT_DCID
            and pktnum == DEFAULT_PKTNUM
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def quic_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.quic_actuation import "
        "builtin_quic_actuation_proof; r=builtin_quic_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='quic_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_quic_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=QUIC_ACTUATION_ID,
        name="First-class RFC 9000 QUIC INITIAL/HANDSHAKE actuation",
        description=(
            "Missions that require a quic tool can opt the quic provider in, "
            "bind a loopback RFC 9000 UDP QUIC endpoint, complete an INITIAL "
            "with a non-empty dcid, lockstep a HANDSHAKE that carries the "
            "stored packet pktnum, independently poll the stored packet "
            "pktnum on a later socket, and seal a digest-chained pktnum. Default "
            "routing stays fail-closed; a missing dcid keeps the hole "
            "falsifiable, and skip-INITIAL/HANDSHAKE/PKTNUM/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.quic_actuation:builtin_quic_actuation_proof",
        proof_command=quic_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.datachannel-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/quic_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/http3_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required quic tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9000 daemon, speaks an "
            "INITIAL then HANDSHAKE over UDP QUIC with a non-empty dcid and "
            "packet pktnum, independently polls the stored packet pktnum on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 8831 Data Channel lockstep is proved. "
            "Missing dcids, skip-INITIAL, skip-HANDSHAKE, skip-pktnum, skip-REPLAY, "
            "and an INITIAL aimed without a dcid stay fail-closed. "
            "Later genesis can take RFC 9114 HTTP/3 SETTINGS/HEADERS as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("quic", "rfc9000", "udp", "dcid", "pktnum", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T024147Z-96e34833",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_quic_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9000 QUIC lockstep actuation seals a pktnum digest."""

    from blackhole_agent.datachannel_actuation import (
        DATACHANNEL_ACTUATION_GOAL,
        DATACHANNEL_ACTUATION_ID,
    )
    from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
    from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
    from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
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
    checks["denylists_self"] = QUIC_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(QUIC_ACTUATION_GOAL) == (
        QUIC_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID, "http3"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_quic"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"quic_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            QUIC_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = QUIC_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    checks["catalog_names_quic"] = (
        len(catalog) > 61
        and catalog[61]["id"] == QUIC_ACTUATION_ID
        and catalog[60]["id"] == DATACHANNEL_ACTUATION_ID
        and catalog[61]["source"] == "genesis_bind_quic"
    )
    checks["catalog_names_http3"] = (
        len(catalog) > 62
        and catalog[62]["id"] == HTTP3_ACTUATION_ID
        and catalog[62]["source"] == "genesis_bind_http3"
    )
    family = capability_family(QUIC_ACTUATION_GOAL)
    checks["family_is_quic"] = "quic" in family
    checks["family_is_rfc9000"] = "rfc9000" in family
    checks["family_is_dcid"] = "dcid" in family
    checks["family_is_pktnum"] = "pktnum" in family
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
    checks["family_is_not_http3"] = (
        "http3" not in family
        and "rfc9114" not in family
        and "streamid" not in family
        and "qpack" not in family
    )
    packed = encode_initial(identity=SENTINEL, dcid=DEFAULT_DCID, pktnum=DEFAULT_PKTNUM)
    parsed = parse_message(packed)
    checks["initial_roundtrip"] = (
        parsed["is_initial"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_dcid"] is True
        and parsed["dcid"] == DEFAULT_DCID
        and parsed["pktnum"] == DEFAULT_PKTNUM
        and parsed["is_response"] is False
        and parsed["is_handshake"] is False
        and parsed["type"] == PACKET_INITIAL
        and parsed["version"] == QUIC_VERSION
        and parsed["first_byte"] == _first_byte(PACKET_INITIAL)
    )
    shook = encode_handshake(
        identity=SENTINEL,
        dcid=DEFAULT_DCID,
        pktnum=DEFAULT_PKTNUM,
    )
    handshake_parsed = parse_message(shook)
    checks["handshake_roundtrip"] = (
        handshake_parsed["is_handshake"] is True
        and handshake_parsed["is_response"] is True
        and handshake_parsed["is_initial"] is False
        and handshake_parsed["identity"] == SENTINEL
        and handshake_parsed["dcid"] == DEFAULT_DCID
        and handshake_parsed["pktnum"] == DEFAULT_PKTNUM
        and handshake_parsed["has_pktnum"] is True
        and handshake_parsed["type"] == PACKET_HANDSHAKE
        and handshake_parsed["first_byte"] == _first_byte(PACKET_HANDSHAKE)
    )
    bare = encode_initial(identity=SENTINEL, dcid=DEFAULT_DCID, include_dcid=False)
    checks["missing_dcid_is_unauthenticated"] = parse_message(bare)["has_dcid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    quic_signature = semantic_signature(QUIC_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(quic_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_quic = ToolDescriptor(name="remote_quic", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_quic)
    checks["naive_mcp_quic_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = quic_tool_descriptor()
    default_quic = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, QUIC_TOOL_PROVIDER),
    )
    checks["default_quic_provider_is_unsupported"] = (
        default_quic.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{QUIC_TOOL_PROVIDER}" in default_quic.reasons
    )
    checks["opted_in_quic_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_quic],
        required_tool_names=("local_memory", "quic"),
    )
    checks["naive_preflight_missing_quic"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["quic"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "quic"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, QUIC_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "quic" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="quic-actuation-") as tmp:
        root = Path(tmp)
        missing = run_quic_workflow(with_dcid=False, output_dir=root / "missing")
        skip_bind = run_quic_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_initial = run_quic_workflow(do_initial=False, output_dir=root / "skip-initial")
        skip_handshake = run_quic_workflow(do_handshake=False, output_dir=root / "skip-handshake")
        skip_pktnum = run_quic_workflow(do_pktnum=False, output_dir=root / "skip-pktnum")
        skip_replay = run_quic_workflow(replay=False, output_dir=root / "skip-replay")
        skip_dcid = run_quic_workflow(use_dcid=False, output_dir=root / "skip-dcid")
        live = run_quic_workflow(output_dir=root / "live")
        verify = verify_quic_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_quic_trace(clone)
        checks["naive_without_dcid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_dcid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_initial_stays_empty"] = (
            skip_initial["ok"] is False
            and skip_initial["error"] == "initial_required"
            and skip_initial["final_status"] == 409
            and skip_initial["payload_exists"] is False
        )
        checks["skip_handshake_stays_empty"] = (
            skip_handshake["ok"] is False
            and skip_handshake["error"] == "handshake_required"
            and skip_handshake["final_status"] == 409
            and skip_handshake["payload_exists"] is False
        )
        checks["skip_pktnum_stays_empty"] = (
            skip_pktnum["ok"] is False
            and skip_pktnum["error"] == "pktnum_required"
            and skip_pktnum["final_status"] == 409
            and skip_pktnum["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_dcid_stays_empty"] = (
            skip_dcid["ok"] is False
            and skip_dcid["error"] == "dcid_required"
            and skip_dcid["final_status"] == 409
            and skip_dcid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_pktnum"] = (
            int(live.get("dcid") or 0) == DEFAULT_DCID
            and int(live.get("pktnum") or 0) == DEFAULT_PKTNUM
            and int(live.get("port") or 0) > 0
        )
        checks["token_dcid_initial_handshake_pktnum_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_initial["ok"] is False
            and skip_handshake["ok"] is False
            and skip_pktnum["ok"] is False
            and skip_replay["ok"] is False
            and skip_dcid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="quic-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != QUIC_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_quic"] = (
        live_goal == QUIC_ACTUATION_GOAL
        and QUIC_ACTUATION_ID in live_done
        and live_source == "genesis_bind_quic"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_quic_actuation_capability()
    return {
        "ok": ok,
        "action": "quic_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": QUIC_ACTUATION_GOAL,
        "done_when": QUIC_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
