"""Drive a first-class CONNECT-IP tool through RFC 9484 ASSIGN/ADVERTISE.

Tool routing already fails missions that require ``connectip``: hosted connectip
endpoints stay on the unsupported MCP provider, and no first-party connectip
provider is executable. Unbound therefore cannot speak an ASSIGN,
lockstep an ADVERTISE prefixid handshake over HTTP CONNECT-IP PREFIXID,
independently poll the stored assigned ipaddr, or seal an ipaddr digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``connectip`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9484 daemon
- keep a missing-prefixid client so the connectip-prefixid hole stays falsifiable
- refuse ADVERTISE verify until an ASSIGN lands with a non-empty prefixid
- independently poll the stored assigned ipaddr on a later client socket
- persist a sealed ipaddr digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9298 MASQUE
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
    CONNECTIP_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    connectip_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
CONNECTIP_ACTUATION_ID = "capability.connectip-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-CIP-OK"
POLL_TOKEN = "BH-CIP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_PREFIXID = 0
EMPTY_IPADDR = 0
CIP_FIRST = 0x01  # RFC 9484 ADDRESS_ASSIGN capsule type
PREFIXID_SIZE = 4
IPADDR_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_ADVERTISE = 0x03  # RFC 9484 ROUTE_ADVERTISEMENT
FRAME_ASSIGN = 0x01  # RFC 9484 ADDRESS_ASSIGN
CONNECTIP_IP_VERSION = 4  # IPv4 sockaddr
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
CONNECTIP_LEFTOVER = (
    "Later genesis can take RFC 9484 CONNECT-IP ASSIGN/ADVERTISE over a "
    "prefixid-gated ipaddr digest."
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


CONNECTIP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{CONNECTIP_ACTUATION_ID};"
    f"capability_proved:{CONNECTIP_ACTUATION_ID};"
    "no_skill_route"
)
CONNECTIP_ACTUATION_GOAL = (
    "Repair rfc9484 connectip assign/advertise cycle cannot land over http "
    "connectip prefixid: hosted connectip endpoints remain unsupported so an ASSIGN then "
    "ADVERTISE prefixid handshake cannot land and a sealed ipaddr digest "
    "cannot be produced. A missing connectip prefixid stays forbidden; fail-closed "
    "routing never opts the connectip provider in. An independent later poll of the "
    "stored assigned ipaddr keeps the hole falsifiable."
)


class ConnectipActuationError(RuntimeError):
    """Raised when the CONNECT-IP session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_prefixid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"prefixid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_prefixid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-prefixid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_ipaddr(prefixid: int = EMPTY_PREFIXID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"ipaddr:{int(prefixid) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_PREFIXID = request_prefixid(SENTINEL)
DEFAULT_IPADDR = request_ipaddr(DEFAULT_PREFIXID, SENTINEL)


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
        raise ConnectipActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise ConnectipActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise ConnectipActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise ConnectipActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    prefixid: int,
    ipaddr: int,
    include_prefixid: bool = True,
) -> bytes:
    live_prefixid = int(prefixid) & 0xFFFFFFFF if include_prefixid else EMPTY_PREFIXID
    live_ipaddr = int(ipaddr) & 0xFFFFFFFF if include_prefixid and live_prefixid else EMPTY_IPADDR
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_ipaddr, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_prefixid) if live_prefixid else b""
    header = bytearray()
    header.append(CIP_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_assign(
    *,
    identity: str,
    prefixid: int,
    ipaddr: int | None = None,
    include_prefixid: bool = True,
) -> bytes:
    live_prefixid = int(prefixid) & 0xFFFFFFFF if include_prefixid else EMPTY_PREFIXID
    live_ipaddr = int(ipaddr) if ipaddr is not None else request_ipaddr(live_prefixid, identity)
    return encode_packet(
        FRAME_ASSIGN,
        identity=identity,
        prefixid=live_prefixid,
        ipaddr=live_ipaddr,
        include_prefixid=include_prefixid,
    )


def encode_advertise(
    *,
    identity: str,
    prefixid: int,
    ipaddr: int | None = None,
    include_prefixid: bool = True,
) -> bytes:
    live_prefixid = int(prefixid) & 0xFFFFFFFF if include_prefixid else EMPTY_PREFIXID
    live_ipaddr = int(ipaddr) if ipaddr is not None else request_ipaddr(live_prefixid, identity)
    return encode_packet(
        FRAME_ADVERTISE,
        identity=identity,
        prefixid=live_prefixid,
        ipaddr=live_ipaddr,
        include_prefixid=include_prefixid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise ConnectipActuationError("short_packet")
    first = raw[0]
    if first != CIP_FIRST:
        raise ConnectipActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise ConnectipActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == PREFIXID_SIZE:
        live_prefixid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_prefixid = EMPTY_PREFIXID
    else:
        raise ConnectipActuationError("illegal_prefixid")
    if offset >= len(raw):
        raise ConnectipActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ASSIGN, FRAME_ADVERTISE}:
        raise ConnectipActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise ConnectipActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise ConnectipActuationError("checksum_failed")
    if len(payload) < 5:
        raise ConnectipActuationError("short_packet")
    live_ipaddr, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise ConnectipActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_prefixid = int(live_prefixid) != EMPTY_PREFIXID
    has_ipaddr = has_prefixid and int(live_ipaddr) != EMPTY_IPADDR
    is_assign = frame_type == FRAME_ASSIGN
    is_advertise = frame_type == FRAME_ADVERTISE
    return {
        "type": int(frame_type),
        "is_assign": is_assign,
        "is_advertise": is_advertise,
        "is_response": is_advertise,
        "prefixid": int(live_prefixid),
        "has_prefixid": has_prefixid,
        "ipaddr": int(live_ipaddr),
        "has_ipaddr": has_ipaddr,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "connectip_ip_version": CONNECTIP_IP_VERSION,
    }


class ConnectipClient:
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
            raise ConnectipActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_advertise"] or not packet["is_response"]:
            raise ConnectipActuationError("ipaddr_required")
        if not packet["has_prefixid"]:
            raise ConnectipActuationError("prefixid_required")
        if not packet["has_ipaddr"]:
            raise ConnectipActuationError("ipaddr_required")
        return packet

    def exchange(self, packet: bytes, *, wait_ipaddr: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_ipaddr:
            raise ConnectipActuationError("ipaddr_required")
        reply = self._recv()
        return {
            "session": reply,
            "prefixid": int(reply.get("prefixid") or EMPTY_PREFIXID),
            "identity": str(reply.get("identity") or ""),
            "ipaddr": int(reply.get("ipaddr") or EMPTY_IPADDR),
        }

    def advertise(
        self,
        identity: str,
        prefixid: int,
        ipaddr: int = EMPTY_IPADDR,
        *,
        wait_ipaddr: bool = True,
        include_prefixid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_advertise(
            identity=identity,
            prefixid=prefixid,
            ipaddr=ipaddr or request_ipaddr(prefixid, identity),
            include_prefixid=include_prefixid,
        )
        return self.exchange(packet, wait_ipaddr=wait_ipaddr)


class ConnectipSession:
    """PREFIXID-gated loopback RFC 9484 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        prefixid_gate: int = DEFAULT_PREFIXID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prefixid_gate = int(prefixid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.prefixid = EMPTY_PREFIXID
        self.ipaddr = EMPTY_IPADDR
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

    def store_prefixid_once(self, identity: str, prefixid: int, ipaddr: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(prefixid or EMPTY_PREFIXID)
            live_ipaddr = int(ipaddr or EMPTY_IPADDR)
            if not self.identity and name and live:
                self.identity = name
                self.prefixid = live
                self.ipaddr = live_ipaddr or request_ipaddr(live, name)
                self.stored = True
            return str(self.identity), int(self.prefixid), int(self.ipaddr)

    def read_prefixid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.prefixid), int(self.ipaddr)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "prefixid": EMPTY_PREFIXID,
            "ipaddr": EMPTY_IPADDR,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _prefixid_missing(self) -> bool:
        return not int(self.prefixid_gate or 0)

    def _reply_advertise(self, peer: tuple[str, int], identity: str, prefixid: int, ipaddr: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_advertise(
            identity=identity,
            prefixid=prefixid,
            ipaddr=ipaddr,
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
            except ConnectipActuationError:
                continue
            if not packet.get("is_assign") and not packet.get("is_advertise"):
                continue
            if not packet.get("has_prefixid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_prefixid, stored_ipaddr = self.store_prefixid_once(
                identity,
                int(packet.get("prefixid") or EMPTY_PREFIXID),
                int(packet.get("ipaddr") or EMPTY_IPADDR),
            )
            if not stored_name or not stored_prefixid or not stored_ipaddr:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_assign"):
                    self.opened = True
                if packet.get("is_advertise"):
                    self.handshook = True
                self.retrieved = True
            self._reply_advertise(peer, stored_name, stored_prefixid, stored_ipaddr)

    def bind(self) -> dict[str, Any]:
        if self._prefixid_missing():
            return self._forbidden("missing_prefixid")
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
        do_assign_cycle: bool = True,
        do_advertise: bool = True,
        do_ipaddr: bool = True,
        replay: bool = True,
        use_prefixid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._prefixid_missing():
            return self._forbidden("missing_prefixid")
        live_token = str(token or SENTINEL)
        origin_prefixid = request_prefixid(live_token)
        origin_ipaddr = request_ipaddr(origin_prefixid, live_token)
        client: ConnectipClient | None = None
        independent: ConnectipClient | None = None
        try:
            client = ConnectipClient(self.host, int(self.port))
            if not do_assign_cycle:
                return self._conflict("assign_required")
            bind_packet = encode_assign(
                identity=live_token,
                prefixid=origin_prefixid,
                ipaddr=origin_ipaddr,
                include_prefixid=use_prefixid,
            )
            if not use_prefixid:
                try:
                    client.exchange(bind_packet, wait_ipaddr=True)
                except ConnectipActuationError:
                    return self._conflict("prefixid_required")
                return self._conflict("prefixid_required")
            client.send(bind_packet)
            if not do_advertise:
                return self._conflict("advertise_required")
            proxy_packet = encode_advertise(
                identity=live_token,
                prefixid=origin_prefixid,
                ipaddr=origin_ipaddr,
                include_prefixid=True,
            )
            if not do_ipaddr:
                try:
                    client.exchange(proxy_packet, wait_ipaddr=False)
                except ConnectipActuationError as error:
                    if str(error) == "ipaddr_required":
                        return self._conflict("ipaddr_required")
                    return self._conflict("ipaddr_required")
                return self._conflict("ipaddr_required")
            try:
                reply = client.exchange(proxy_packet, wait_ipaddr=True)
            except ConnectipActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("prefixid_required")
                if reason == "ipaddr_required":
                    return self._conflict("ipaddr_required")
                return self._conflict("assign_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("assign_required")
            if int(reply.get("prefixid") or EMPTY_PREFIXID) != origin_prefixid:
                return self._conflict("ipaddr_required")
            if int(reply.get("ipaddr") or EMPTY_IPADDR) != origin_ipaddr:
                return self._conflict("ipaddr_required")
            self.retrieved = True
            if replay:
                independent = ConnectipClient(self.host, int(self.port))
                try:
                    poll = independent.advertise(
                        POLL_TOKEN,
                        poll_prefixid(live_token),
                        request_ipaddr(poll_prefixid(live_token), POLL_TOKEN),
                        wait_ipaddr=True,
                    )
                except ConnectipActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_prefixid, stored_ipaddr = self.read_prefixid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_prefixid != origin_prefixid
                    or stored_ipaddr != origin_ipaddr
                    or int(poll.get("prefixid") or EMPTY_PREFIXID) != origin_prefixid
                    or int(poll.get("ipaddr") or EMPTY_IPADDR) != origin_ipaddr
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_prefixid}:{origin_ipaddr}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "prefixid": origin_prefixid,
                "ipaddr": origin_ipaddr,
                "assign": True,
                "advertise": True,
                "ipaddr_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "prefixid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_connectip_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "prefixid": origin_prefixid,
                "ipaddr": origin_ipaddr,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "assign": True,
                "advertise": True,
                "ipaddr_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "prefixid_bound": True,
            }
        except (OSError, ConnectipActuationError) as error:
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
        live = independent_connectip_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "prefixid": int(live.get("prefixid") or EMPTY_PREFIXID),
            "ipaddr": int(live.get("ipaddr") or EMPTY_IPADDR),
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


def call_connectip_tool(session: ConnectipSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one CONNECTIP tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_assign_cycle = True if arguments.get("assign_cycle") is None else bool(arguments.get("assign_cycle"))
    do_advertise = True if arguments.get("advertise") is None else bool(arguments.get("advertise"))
    do_ipaddr = True if arguments.get("ipaddr") is None else bool(arguments.get("ipaddr"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_prefixid = True if arguments.get("use_prefixid") is None else bool(arguments.get("use_prefixid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_assign_cycle=do_assign_cycle,
            do_advertise=do_advertise,
            do_ipaddr=do_ipaddr,
            replay=replay,
            use_prefixid=use_prefixid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise ConnectipActuationError(f"unsupported connectip action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_connectip_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed CONNECTIP ipaddr digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "prefixid": EMPTY_PREFIXID,
        "ipaddr": EMPTY_IPADDR,
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
            "assign",
            "advertise",
            "ipaddr_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "prefixid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    prefixid = int(payload.get("prefixid") or EMPTY_PREFIXID)
    ipaddr = int(payload.get("ipaddr") or EMPTY_IPADDR)
    dual = port > 0 and bool(prefixid) and bool(ipaddr)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "prefixid": prefixid,
        "ipaddr": ipaddr,
        "size": int(payload.get("size") or 0),
        "port": port,
        "assign": payload.get("assign") is True,
        "advertise": payload.get("advertise") is True,
        "ipaddr_response": payload.get("ipaddr_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "prefixid_bound": payload.get("prefixid_bound") is True,
    }


def run_connectip_workflow(
    *,
    with_prefixid: bool = True,
    skip_bind: bool = False,
    do_assign_cycle: bool = True,
    do_advertise: bool = True,
    do_ipaddr: bool = True,
    replay: bool = True,
    use_prefixid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9484 ASSIGN/ADVERTISE prefixid cycle workflow."""

    descriptor = connectip_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CONNECTIP_TOOL_PROVIDER),
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
        raise ConnectipActuationError(f"connectip tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="connectip-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = ConnectipSession(out, prefixid_gate=DEFAULT_PREFIXID if with_prefixid else EMPTY_PREFIXID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "assign_cycle": do_assign_cycle,
            "advertise": do_advertise,
            "ipaddr": do_ipaddr,
            "replay": replay,
            "use_prefixid": use_prefixid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_connectip_tool(session, arguments))
            except ConnectipActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_connectip_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_prefixid
        and not skip_bind
        and do_assign_cycle
        and do_advertise
        and do_ipaddr
        and replay
        and use_prefixid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "connectip_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_prefixid": with_prefixid,
        "skip_bind": skip_bind,
        "assign": do_assign_cycle,
        "advertise": do_advertise,
        "ipaddr": do_ipaddr,
        "replay": replay,
        "use_prefixid": use_prefixid,
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
        "prefixid_value": int(publish_result.get("prefixid") or independent.get("prefixid") or EMPTY_PREFIXID),
        "ipaddr_value": int(publish_result.get("ipaddr") or independent.get("ipaddr") or EMPTY_IPADDR),
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
        "prefixid": int(trace_body["prefixid_value"] or EMPTY_PREFIXID),
        "ipaddr": int(trace_body["ipaddr_value"] or EMPTY_IPADDR),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_prefixid": with_prefixid,
        "skip_bind": skip_bind,
        "assign_cycle": do_assign_cycle,
        "advertise_cycle": do_advertise,
        "ipaddr_cycle": do_ipaddr,
        "replay": replay,
        "use_prefixid": use_prefixid,
    }


def verify_connectip_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed CONNECTIP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_connectip_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    prefixid = int(trace.get("prefixid_value") or independent.get("prefixid") or EMPTY_PREFIXID)
    ipaddr = int(trace.get("ipaddr_value") or independent.get("ipaddr") or EMPTY_IPADDR)
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
        "assign": independent.get("assign") is True,
        "advertise": independent.get("advertise") is True,
        "ipaddr_response": independent.get("ipaddr_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "prefixid_bound": independent.get("prefixid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "ipaddr_recorded": (
            port > 0
            and prefixid == DEFAULT_PREFIXID
            and ipaddr == DEFAULT_IPADDR
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}

def connectip_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.connectip_actuation import "
        "builtin_connectip_actuation_proof; r=builtin_connectip_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='connectip_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_connectip_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=CONNECTIP_ACTUATION_ID,
        name="First-class RFC 9484 CONNECT-IP ASSIGN/ADVERTISE actuation",
        description=(
            "Missions that require a connectip tool can opt the connectip provider in, "
            "bind a loopback RFC 9484 HTTP CONNECT-IP endpoint, complete an ASSIGN "
            "with a non-empty prefixid, lockstep an ADVERTISE that carries the "
            "stored assigned ipaddr, independently poll the stored assigned "
            "ipaddr on a later socket, and seal a digest-chained ipaddr. Default "
            "routing stays fail-closed; a missing prefixid keeps the hole "
            "falsifiable, and skip-ASSIGN/ADVERTISE/IPADDR/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.connectip_actuation:builtin_connectip_actuation_proof",
        proof_command=connectip_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.masque-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/connectip_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/ohttp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required connectip tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9484 daemon, speaks an "
            "ASSIGN then ADVERTISE over HTTP CONNECT-IP with a non-empty prefixid and "
            "assigned ipaddr, independently polls the stored assigned ipaddr on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9298 MASQUE lockstep is proved. "
            "Missing prefixids, skip-ASSIGN, skip-ADVERTISE, skip-ipaddr, skip-REPLAY, "
            "and an ASSIGN aimed without a prefixid stay fail-closed. "
            "Later genesis can take RFC 9458 Oblivious HTTP ENCAPSULATE/DECAPSULATE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("connectip", "rfc9484", "http", "prefixid", "ipaddr", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T053455Z-df8c2061",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_connectip_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9484 CONNECT-IP lockstep actuation seals an ipaddr digest."""

    from blackhole_agent.ohttp_actuation import OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID
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
    checks["denylists_self"] = CONNECTIP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(CONNECTIP_ACTUATION_GOAL) == (
        CONNECTIP_ACTUATION_ID,
    )
    checks["leftover_text_binds_connectip"] = leftover_marker_ids(CONNECTIP_LEFTOVER) == (
        CONNECTIP_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID, "ohttp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_connectip"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"connectip_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            CONNECTIP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = CONNECTIP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    checks["catalog_names_connectip"] = (
        len(catalog) > 66
        and catalog[66]["id"] == CONNECTIP_ACTUATION_ID
        and catalog[65]["id"] == MASQUE_ACTUATION_ID
        and catalog[66]["source"] == "genesis_bind_connectip"
    )
    checks["catalog_names_ohttp"] = (
        len(catalog) > 67
        and catalog[67]["id"] == OHTTP_ACTUATION_ID
        and catalog[67]["source"] == "genesis_bind_ohttp"
    )
    family = capability_family(CONNECTIP_ACTUATION_GOAL)
    checks["family_is_connectip"] = "connectip" in family
    checks["family_is_rfc9484"] = "rfc9484" in family
    checks["family_is_prefixid"] = "prefixid" in family
    checks["family_is_ipaddr"] = "ipaddr" in family
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
    checks["family_is_not_ohttp"] = (
        "ohttp" not in family
        and "rfc9458" not in family
        and "configid" not in family
        and "gateway" not in family
    )
    packed = encode_assign(identity=SENTINEL, prefixid=DEFAULT_PREFIXID, ipaddr=DEFAULT_IPADDR)
    parsed = parse_message(packed)
    checks["assign_roundtrip"] = (
        parsed["is_assign"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_prefixid"] is True
        and parsed["prefixid"] == DEFAULT_PREFIXID
        and parsed["ipaddr"] == DEFAULT_IPADDR
        and parsed["is_response"] is False
        and parsed["is_advertise"] is False
        and parsed["type"] == FRAME_ASSIGN
        and parsed["first_byte"] == CIP_FIRST
    )
    shook = encode_advertise(
        identity=SENTINEL,
        prefixid=DEFAULT_PREFIXID,
        ipaddr=DEFAULT_IPADDR,
    )
    advertise_parsed = parse_message(shook)
    checks["advertise_roundtrip"] = (
        advertise_parsed["is_advertise"] is True
        and advertise_parsed["is_response"] is True
        and advertise_parsed["is_assign"] is False
        and advertise_parsed["identity"] == SENTINEL
        and advertise_parsed["prefixid"] == DEFAULT_PREFIXID
        and advertise_parsed["ipaddr"] == DEFAULT_IPADDR
        and advertise_parsed["has_ipaddr"] is True
        and advertise_parsed["type"] == FRAME_ADVERTISE
        and advertise_parsed["first_byte"] == CIP_FIRST
    )
    bare = encode_assign(identity=SENTINEL, prefixid=DEFAULT_PREFIXID, include_prefixid=False)
    checks["missing_prefixid_is_unauthenticated"] = parse_message(bare)["has_prefixid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    connectip_signature = semantic_signature(CONNECTIP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(connectip_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_connectip = ToolDescriptor(name="remote_connectip", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_connectip)
    checks["naive_mcp_connectip_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = connectip_tool_descriptor()
    default_connectip = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CONNECTIP_TOOL_PROVIDER),
    )
    checks["default_connectip_provider_is_unsupported"] = (
        default_connectip.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{CONNECTIP_TOOL_PROVIDER}" in default_connectip.reasons
    )
    checks["opted_in_connectip_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_connectip],
        required_tool_names=("local_memory", "connectip"),
    )
    checks["naive_preflight_missing_connectip"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["connectip"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "connectip"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CONNECTIP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "connectip" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="connectip-actuation-") as tmp:
        root = Path(tmp)
        missing = run_connectip_workflow(with_prefixid=False, output_dir=root / "missing")
        skip_bind = run_connectip_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_assign_cycle = run_connectip_workflow(do_assign_cycle=False, output_dir=root / "skip-bind-cycle")
        skip_advertise = run_connectip_workflow(do_advertise=False, output_dir=root / "skip-proxy")
        skip_ipaddr = run_connectip_workflow(do_ipaddr=False, output_dir=root / "skip-ipaddr")
        skip_replay = run_connectip_workflow(replay=False, output_dir=root / "skip-replay")
        skip_prefixid = run_connectip_workflow(use_prefixid=False, output_dir=root / "skip-prefixid")
        live = run_connectip_workflow(output_dir=root / "live")
        verify = verify_connectip_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_connectip_trace(clone)
        checks["naive_without_prefixid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_prefixid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_assign_cycle_stays_empty"] = (
            skip_assign_cycle["ok"] is False
            and skip_assign_cycle["error"] == "assign_required"
            and skip_assign_cycle["final_status"] == 409
            and skip_assign_cycle["payload_exists"] is False
        )
        checks["skip_advertise_stays_empty"] = (
            skip_advertise["ok"] is False
            and skip_advertise["error"] == "advertise_required"
            and skip_advertise["final_status"] == 409
            and skip_advertise["payload_exists"] is False
        )
        checks["skip_ipaddr_stays_empty"] = (
            skip_ipaddr["ok"] is False
            and skip_ipaddr["error"] == "ipaddr_required"
            and skip_ipaddr["final_status"] == 409
            and skip_ipaddr["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_prefixid_stays_empty"] = (
            skip_prefixid["ok"] is False
            and skip_prefixid["error"] == "prefixid_required"
            and skip_prefixid["final_status"] == 409
            and skip_prefixid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_ipaddr"] = (
            int(live.get("prefixid") or 0) == DEFAULT_PREFIXID
            and int(live.get("ipaddr") or 0) == DEFAULT_IPADDR
            and int(live.get("port") or 0) > 0
        )
        checks["token_prefixid_assign_advertise_ipaddr_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_assign_cycle["ok"] is False
            and skip_advertise["ok"] is False
            and skip_ipaddr["ok"] is False
            and skip_replay["ok"] is False
            and skip_prefixid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="connectip-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != CONNECTIP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_connectip"] = (
        live_goal == CONNECTIP_ACTUATION_GOAL
        and CONNECTIP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_connectip"
    )

    with tempfile.TemporaryDirectory(prefix="connectip-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(CONNECTIP_LEFTOVER, root)
        register_catalog_proved(root, CONNECTIP_ACTUATION_ID)
        reason = leftover_satisfied_by(CONNECTIP_LEFTOVER, root)
        after = leftover_is_open(CONNECTIP_LEFTOVER, root)
    checks["connectip_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_connectip_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{CONNECTIP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_connectip_actuation_capability()
    return {
        "ok": ok,
        "action": "connectip_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": CONNECTIP_ACTUATION_GOAL,
        "done_when": CONNECTIP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
