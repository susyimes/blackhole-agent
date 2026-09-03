"""Drive a first-class QUIC DATAGRAM tool through RFC 9221 SEND/ECHO.

Tool routing already fails missions that require ``datagram``: hosted datagram
endpoints stay on the unsupported MCP provider, and no first-party datagram
provider is executable. Unbound therefore cannot speak a SEND,
lockstep an ECHO flowid handshake over UDP QUIC DATAGRAM FLOWID,
independently poll the stored flow contextid, or seal a contextid digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``datagram`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9221 daemon
- keep a missing-flowid client so the datagram-flowid hole stays falsifiable
- refuse ECHO verify until a SEND lands with a non-empty flowid
- independently poll the stored flow contextid on a later client socket
- persist a sealed contextid digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after WebTransport
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
    DATAGRAM_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    datagram_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
DATAGRAM_ACTUATION_ID = "capability.datagram-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-DG-OK"
POLL_TOKEN = "BH-DG-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_FLOWID = 0
EMPTY_CONTEXTID = 0
DG_FIRST = 0x30  # RFC 9221 DATAGRAM without Length
CID_SIZE = 4
CONTEXTID_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_ECHO = 0x31  # RFC 9221 DATAGRAM with Length (echo)
FRAME_SEND = 0x30  # RFC 9221 DATAGRAM without Length
DATAGRAM_CONTEXTID_TYPE = 0x00  # RFC 9297 DATAGRAM contextid
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
DATAGRAM_LEFTOVER = (
    "Later genesis can take RFC 9221 QUIC DATAGRAM SEND/ECHO over a "
    "flowid-gated contextid digest."
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


DATAGRAM_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DATAGRAM_ACTUATION_ID};"
    f"capability_proved:{DATAGRAM_ACTUATION_ID};"
    "no_skill_route"
)
DATAGRAM_ACTUATION_GOAL = (
    "Repair rfc9221 datagram send/echo cycle cannot land over udp "
    "datagram flowid: hosted datagram endpoints remain unsupported so a SEND then "
    "ECHO flowid handshake cannot land and a sealed contextid digest "
    "cannot be produced. A missing datagram flowid stays forbidden; fail-closed "
    "routing never opts the datagram provider in. An independent later poll of the "
    "stored flow contextid keeps the hole falsifiable."
)


class DatagramActuationError(RuntimeError):
    """Raised when the QUIC DATAGRAM session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_flowid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"flowid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_flowid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-flowid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_contextid(flowid: int = EMPTY_FLOWID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"contextid:{int(flowid) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_FLOWID = request_flowid(SENTINEL)
DEFAULT_CONTEXTID = request_contextid(DEFAULT_FLOWID, SENTINEL)


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
        raise DatagramActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise DatagramActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise DatagramActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise DatagramActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    flowid: int,
    contextid: int,
    include_flowid: bool = True,
) -> bytes:
    live_flowid = int(flowid) & 0xFFFFFFFF if include_flowid else EMPTY_FLOWID
    live_contextid = int(contextid) & 0xFFFFFFFF if include_flowid and live_flowid else EMPTY_CONTEXTID
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_contextid, len(ident)) + ident
    flow_bytes = struct.pack("!I", live_flowid) if live_flowid else b""
    header = bytearray()
    header.append(DG_FIRST)
    header.append(len(flow_bytes))
    header.extend(flow_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_send(
    *,
    identity: str,
    flowid: int,
    contextid: int | None = None,
    include_flowid: bool = True,
) -> bytes:
    live_flowid = int(flowid) & 0xFFFFFFFF if include_flowid else EMPTY_FLOWID
    live_contextid = int(contextid) if contextid is not None else request_contextid(live_flowid, identity)
    return encode_packet(
        FRAME_SEND,
        identity=identity,
        flowid=live_flowid,
        contextid=live_contextid,
        include_flowid=include_flowid,
    )


def encode_echo(
    *,
    identity: str,
    flowid: int,
    contextid: int | None = None,
    include_flowid: bool = True,
) -> bytes:
    live_flowid = int(flowid) & 0xFFFFFFFF if include_flowid else EMPTY_FLOWID
    live_contextid = int(contextid) if contextid is not None else request_contextid(live_flowid, identity)
    return encode_packet(
        FRAME_ECHO,
        identity=identity,
        flowid=live_flowid,
        contextid=live_contextid,
        include_flowid=include_flowid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise DatagramActuationError("short_packet")
    first = raw[0]
    if first != DG_FIRST:
        raise DatagramActuationError("illegal_header")
    offset = 1
    flow_len = raw[offset]
    offset += 1
    if offset + flow_len > len(raw):
        raise DatagramActuationError("short_packet")
    flow_bytes = raw[offset : offset + flow_len]
    offset += flow_len
    if flow_len == CID_SIZE:
        live_flowid = struct.unpack("!I", flow_bytes)[0]
    elif flow_len == 0:
        live_flowid = EMPTY_FLOWID
    else:
        raise DatagramActuationError("illegal_flowid")
    if offset >= len(raw):
        raise DatagramActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SEND, FRAME_ECHO}:
        raise DatagramActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise DatagramActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise DatagramActuationError("checksum_failed")
    if len(payload) < 5:
        raise DatagramActuationError("short_packet")
    live_contextid, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise DatagramActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_flowid = int(live_flowid) != EMPTY_FLOWID
    has_contextid = has_flowid and int(live_contextid) != EMPTY_CONTEXTID
    is_send = frame_type == FRAME_SEND
    is_echo = frame_type == FRAME_ECHO
    return {
        "type": int(frame_type),
        "is_send": is_send,
        "is_echo": is_echo,
        "is_response": is_echo,
        "flowid": int(live_flowid),
        "has_flowid": has_flowid,
        "contextid": int(live_contextid),
        "has_contextid": has_contextid,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "flow_len": int(flow_len),
        "datagram_contextid_type": DATAGRAM_CONTEXTID_TYPE,
    }


class DatagramClient:
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
            raise DatagramActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_echo"] or not packet["is_response"]:
            raise DatagramActuationError("contextid_required")
        if not packet["has_flowid"]:
            raise DatagramActuationError("flowid_required")
        if not packet["has_contextid"]:
            raise DatagramActuationError("contextid_required")
        return packet

    def exchange(self, packet: bytes, *, wait_contextid: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_contextid:
            raise DatagramActuationError("contextid_required")
        reply = self._recv()
        return {
            "session": reply,
            "flowid": int(reply.get("flowid") or EMPTY_FLOWID),
            "identity": str(reply.get("identity") or ""),
            "contextid": int(reply.get("contextid") or EMPTY_CONTEXTID),
        }

    def echo(
        self,
        identity: str,
        flowid: int,
        contextid: int = EMPTY_CONTEXTID,
        *,
        wait_contextid: bool = True,
        include_flowid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_echo(
            identity=identity,
            flowid=flowid,
            contextid=contextid or request_contextid(flowid, identity),
            include_flowid=include_flowid,
        )
        return self.exchange(packet, wait_contextid=wait_contextid)


class DatagramSession:
    """FLOWID-gated loopback RFC 9221 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        flowid_gate: int = DEFAULT_FLOWID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.flowid_gate = int(flowid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.flowid = EMPTY_FLOWID
        self.contextid = EMPTY_CONTEXTID
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

    def store_flowid_once(self, identity: str, flowid: int, contextid: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(flowid or EMPTY_FLOWID)
            live_contextid = int(contextid or EMPTY_CONTEXTID)
            if not self.identity and name and live:
                self.identity = name
                self.flowid = live
                self.contextid = live_contextid or request_contextid(live, name)
                self.stored = True
            return str(self.identity), int(self.flowid), int(self.contextid)

    def read_flowid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.flowid), int(self.contextid)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "flowid": EMPTY_FLOWID,
            "contextid": EMPTY_CONTEXTID,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _flowid_missing(self) -> bool:
        return not int(self.flowid_gate or 0)

    def _reply_echo(self, peer: tuple[str, int], identity: str, flowid: int, contextid: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_echo(
            identity=identity,
            flowid=flowid,
            contextid=contextid,
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
            except DatagramActuationError:
                continue
            if not packet.get("is_send") and not packet.get("is_echo"):
                continue
            if not packet.get("has_flowid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_flowid, stored_contextid = self.store_flowid_once(
                identity,
                int(packet.get("flowid") or EMPTY_FLOWID),
                int(packet.get("contextid") or EMPTY_CONTEXTID),
            )
            if not stored_name or not stored_flowid or not stored_contextid:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_send"):
                    self.opened = True
                if packet.get("is_echo"):
                    self.handshook = True
                self.retrieved = True
            self._reply_echo(peer, stored_name, stored_flowid, stored_contextid)

    def bind(self) -> dict[str, Any]:
        if self._flowid_missing():
            return self._forbidden("missing_flowid")
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
        do_send: bool = True,
        do_echo: bool = True,
        do_contextid: bool = True,
        replay: bool = True,
        use_flowid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._flowid_missing():
            return self._forbidden("missing_flowid")
        live_token = str(token or SENTINEL)
        origin_flowid = request_flowid(live_token)
        origin_contextid = request_contextid(origin_flowid, live_token)
        client: DatagramClient | None = None
        independent: DatagramClient | None = None
        try:
            client = DatagramClient(self.host, int(self.port))
            if not do_send:
                return self._conflict("send_required")
            send_packet = encode_send(
                identity=live_token,
                flowid=origin_flowid,
                contextid=origin_contextid,
                include_flowid=use_flowid,
            )
            if not use_flowid:
                try:
                    client.exchange(send_packet, wait_contextid=True)
                except DatagramActuationError:
                    return self._conflict("flowid_required")
                return self._conflict("flowid_required")
            client.send(send_packet)
            if not do_echo:
                return self._conflict("echo_required")
            echo_packet = encode_echo(
                identity=live_token,
                flowid=origin_flowid,
                contextid=origin_contextid,
                include_flowid=True,
            )
            if not do_contextid:
                try:
                    client.exchange(echo_packet, wait_contextid=False)
                except DatagramActuationError as error:
                    if str(error) == "contextid_required":
                        return self._conflict("contextid_required")
                    return self._conflict("contextid_required")
                return self._conflict("contextid_required")
            try:
                reply = client.exchange(echo_packet, wait_contextid=True)
            except DatagramActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("flowid_required")
                if reason == "contextid_required":
                    return self._conflict("contextid_required")
                return self._conflict("send_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("send_required")
            if int(reply.get("flowid") or EMPTY_FLOWID) != origin_flowid:
                return self._conflict("contextid_required")
            if int(reply.get("contextid") or EMPTY_CONTEXTID) != origin_contextid:
                return self._conflict("contextid_required")
            self.retrieved = True
            if replay:
                independent = DatagramClient(self.host, int(self.port))
                try:
                    poll = independent.echo(
                        POLL_TOKEN,
                        poll_flowid(live_token),
                        request_contextid(poll_flowid(live_token), POLL_TOKEN),
                        wait_contextid=True,
                    )
                except DatagramActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_flowid, stored_contextid = self.read_flowid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_flowid != origin_flowid
                    or stored_contextid != origin_contextid
                    or int(poll.get("flowid") or EMPTY_FLOWID) != origin_flowid
                    or int(poll.get("contextid") or EMPTY_CONTEXTID) != origin_contextid
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_flowid}:{origin_contextid}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "flowid": origin_flowid,
                "contextid": origin_contextid,
                "send": True,
                "echo": True,
                "contextid_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "flowid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_datagram_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "flowid": origin_flowid,
                "contextid": origin_contextid,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "send": True,
                "echo": True,
                "contextid_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "flowid_bound": True,
            }
        except (OSError, DatagramActuationError) as error:
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
        live = independent_datagram_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "flowid": int(live.get("flowid") or EMPTY_FLOWID),
            "contextid": int(live.get("contextid") or EMPTY_CONTEXTID),
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


def call_datagram_tool(session: DatagramSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one QUIC DATAGRAM tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_send = True if arguments.get("send") is None else bool(arguments.get("send"))
    do_echo = True if arguments.get("echo") is None else bool(arguments.get("echo"))
    do_contextid = True if arguments.get("contextid") is None else bool(arguments.get("contextid"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_flowid = True if arguments.get("use_flowid") is None else bool(arguments.get("use_flowid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_send=do_send,
            do_echo=do_echo,
            do_contextid=do_contextid,
            replay=replay,
            use_flowid=use_flowid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise DatagramActuationError(f"unsupported datagram action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_datagram_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed QUIC DATAGRAM contextid digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "flowid": EMPTY_FLOWID,
        "contextid": EMPTY_CONTEXTID,
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
            "send",
            "echo",
            "contextid_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "flowid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    flowid = int(payload.get("flowid") or EMPTY_FLOWID)
    contextid = int(payload.get("contextid") or EMPTY_CONTEXTID)
    dual = port > 0 and bool(flowid) and bool(contextid)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "flowid": flowid,
        "contextid": contextid,
        "size": int(payload.get("size") or 0),
        "port": port,
        "send": payload.get("send") is True,
        "echo": payload.get("echo") is True,
        "contextid_response": payload.get("contextid_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "flowid_bound": payload.get("flowid_bound") is True,
    }


def run_datagram_workflow(
    *,
    with_flowid: bool = True,
    skip_bind: bool = False,
    do_send: bool = True,
    do_echo: bool = True,
    do_contextid: bool = True,
    replay: bool = True,
    use_flowid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9221 SEND/ECHO flowid cycle workflow."""

    descriptor = datagram_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DATAGRAM_TOOL_PROVIDER),
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
        raise DatagramActuationError(f"datagram tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="datagram-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = DatagramSession(out, flowid_gate=DEFAULT_FLOWID if with_flowid else EMPTY_FLOWID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "send": do_send,
            "echo": do_echo,
            "contextid": do_contextid,
            "replay": replay,
            "use_flowid": use_flowid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_datagram_tool(session, arguments))
            except DatagramActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_datagram_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_flowid
        and not skip_bind
        and do_send
        and do_echo
        and do_contextid
        and replay
        and use_flowid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "datagram_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_flowid": with_flowid,
        "skip_bind": skip_bind,
        "send": do_send,
        "echo": do_echo,
        "contextid": do_contextid,
        "replay": replay,
        "use_flowid": use_flowid,
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
        "flowid_value": int(publish_result.get("flowid") or independent.get("flowid") or EMPTY_FLOWID),
        "contextid_value": int(publish_result.get("contextid") or independent.get("contextid") or EMPTY_CONTEXTID),
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
        "flowid": int(trace_body["flowid_value"] or EMPTY_FLOWID),
        "contextid": int(trace_body["contextid_value"] or EMPTY_CONTEXTID),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_flowid": with_flowid,
        "skip_bind": skip_bind,
        "connect": do_send,
        "echo_cycle": do_echo,
        "contextid_cycle": do_contextid,
        "replay": replay,
        "use_flowid": use_flowid,
    }


def verify_datagram_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed QUIC DATAGRAM trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_datagram_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    flowid = int(trace.get("flowid_value") or independent.get("flowid") or EMPTY_FLOWID)
    contextid = int(trace.get("contextid_value") or independent.get("contextid") or EMPTY_CONTEXTID)
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
        "send": independent.get("send") is True,
        "echo": independent.get("echo") is True,
        "contextid_response": independent.get("contextid_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "flowid_bound": independent.get("flowid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "contextid_recorded": (
            port > 0
            and flowid == DEFAULT_FLOWID
            and contextid == DEFAULT_CONTEXTID
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def datagram_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.datagram_actuation import "
        "builtin_datagram_actuation_proof; r=builtin_datagram_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='datagram_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_datagram_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=DATAGRAM_ACTUATION_ID,
        name="First-class RFC 9221 QUIC DATAGRAM SEND/ECHO actuation",
        description=(
            "Missions that require a datagram tool can opt the datagram provider in, "
            "bind a loopback RFC 9221 UDP QUIC DATAGRAM endpoint, complete a SEND "
            "with a non-empty flowid, lockstep an ECHO that carries the "
            "stored flow contextid, independently poll the stored flow "
            "contextid on a later socket, and seal a digest-chained contextid. Default "
            "routing stays fail-closed; a missing flowid keeps the hole "
            "falsifiable, and skip-SEND/ECHO/CONTEXTID/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.datagram_actuation:builtin_datagram_actuation_proof",
        proof_command=datagram_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.webtransport-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/datagram_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/masque_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required datagram tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9221 daemon, speaks a "
            "SEND then ECHO over UDP QUIC DATAGRAM with a non-empty flowid and "
            "flow contextid, independently polls the stored flow contextid on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9220 WebTransport lockstep is proved. "
            "Missing flowids, skip-SEND, skip-ECHO, skip-contextid, skip-REPLAY, "
            "and a SEND aimed without a flowid stay fail-closed. "
            "Later genesis can take RFC 9298 MASQUE CONNECT-UDP as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("datagram", "rfc9221", "udp", "flowid", "contextid", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T042621Z-cd13c4aa",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_datagram_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9221 QUIC DATAGRAM lockstep actuation seals a contextid digest."""

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
    from blackhole_agent.masque_actuation import (
        MASQUE_ACTUATION_GOAL,
        MASQUE_ACTUATION_ID,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = DATAGRAM_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(DATAGRAM_ACTUATION_GOAL) == (
        DATAGRAM_ACTUATION_ID,
    )
    checks["leftover_text_binds_datagram"] = leftover_marker_ids(DATAGRAM_LEFTOVER) == (
        DATAGRAM_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID, "masque"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_datagram"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"datagram_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            DATAGRAM_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = DATAGRAM_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    checks["catalog_names_datagram"] = (
        len(catalog) > 64
        and catalog[64]["id"] == DATAGRAM_ACTUATION_ID
        and catalog[63]["id"] == WEBTRANSPORT_ACTUATION_ID
        and catalog[64]["source"] == "genesis_bind_datagram"
    )
    checks["catalog_names_masque"] = (
        len(catalog) > 65
        and catalog[65]["id"] == MASQUE_ACTUATION_ID
        and catalog[65]["source"] == "genesis_bind_masque"
    )
    family = capability_family(DATAGRAM_ACTUATION_GOAL)
    checks["family_is_datagram"] = "datagram" in family
    checks["family_is_rfc9221"] = "rfc9221" in family
    checks["family_is_flowid"] = "flowid" in family
    checks["family_is_contextid"] = "contextid" in family
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
    checks["family_is_not_masque"] = (
        "masque" not in family
        and "rfc9298" not in family
        and "targetid" not in family
        and "authority" not in family
    )
    packed = encode_send(identity=SENTINEL, flowid=DEFAULT_FLOWID, contextid=DEFAULT_CONTEXTID)
    parsed = parse_message(packed)
    checks["send_roundtrip"] = (
        parsed["is_send"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_flowid"] is True
        and parsed["flowid"] == DEFAULT_FLOWID
        and parsed["contextid"] == DEFAULT_CONTEXTID
        and parsed["is_response"] is False
        and parsed["is_echo"] is False
        and parsed["type"] == FRAME_SEND
        and parsed["first_byte"] == DG_FIRST
    )
    shook = encode_echo(
        identity=SENTINEL,
        flowid=DEFAULT_FLOWID,
        contextid=DEFAULT_CONTEXTID,
    )
    echo_parsed = parse_message(shook)
    checks["echo_roundtrip"] = (
        echo_parsed["is_echo"] is True
        and echo_parsed["is_response"] is True
        and echo_parsed["is_send"] is False
        and echo_parsed["identity"] == SENTINEL
        and echo_parsed["flowid"] == DEFAULT_FLOWID
        and echo_parsed["contextid"] == DEFAULT_CONTEXTID
        and echo_parsed["has_contextid"] is True
        and echo_parsed["type"] == FRAME_ECHO
        and echo_parsed["first_byte"] == DG_FIRST
    )
    bare = encode_send(identity=SENTINEL, flowid=DEFAULT_FLOWID, include_flowid=False)
    checks["missing_flowid_is_unauthenticated"] = parse_message(bare)["has_flowid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    datagram_signature = semantic_signature(DATAGRAM_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(datagram_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_datagram = ToolDescriptor(name="remote_datagram", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_datagram)
    checks["naive_mcp_datagram_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = datagram_tool_descriptor()
    default_datagram = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DATAGRAM_TOOL_PROVIDER),
    )
    checks["default_datagram_provider_is_unsupported"] = (
        default_datagram.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{DATAGRAM_TOOL_PROVIDER}" in default_datagram.reasons
    )
    checks["opted_in_datagram_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_datagram],
        required_tool_names=("local_memory", "datagram"),
    )
    checks["naive_preflight_missing_datagram"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["datagram"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "datagram"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DATAGRAM_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "datagram" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="datagram-actuation-") as tmp:
        root = Path(tmp)
        missing = run_datagram_workflow(with_flowid=False, output_dir=root / "missing")
        skip_bind = run_datagram_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_send = run_datagram_workflow(do_send=False, output_dir=root / "skip-connect")
        skip_echo = run_datagram_workflow(do_echo=False, output_dir=root / "skip-session")
        skip_contextid = run_datagram_workflow(do_contextid=False, output_dir=root / "skip-contextid")
        skip_replay = run_datagram_workflow(replay=False, output_dir=root / "skip-replay")
        skip_flowid = run_datagram_workflow(use_flowid=False, output_dir=root / "skip-flowid")
        live = run_datagram_workflow(output_dir=root / "live")
        verify = verify_datagram_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_datagram_trace(clone)
        checks["naive_without_flowid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_flowid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_send_stays_empty"] = (
            skip_send["ok"] is False
            and skip_send["error"] == "send_required"
            and skip_send["final_status"] == 409
            and skip_send["payload_exists"] is False
        )
        checks["skip_echo_stays_empty"] = (
            skip_echo["ok"] is False
            and skip_echo["error"] == "echo_required"
            and skip_echo["final_status"] == 409
            and skip_echo["payload_exists"] is False
        )
        checks["skip_contextid_stays_empty"] = (
            skip_contextid["ok"] is False
            and skip_contextid["error"] == "contextid_required"
            and skip_contextid["final_status"] == 409
            and skip_contextid["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_flowid_stays_empty"] = (
            skip_flowid["ok"] is False
            and skip_flowid["error"] == "flowid_required"
            and skip_flowid["final_status"] == 409
            and skip_flowid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_contextid"] = (
            int(live.get("flowid") or 0) == DEFAULT_FLOWID
            and int(live.get("contextid") or 0) == DEFAULT_CONTEXTID
            and int(live.get("port") or 0) > 0
        )
        checks["token_flowid_send_echo_contextid_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_send["ok"] is False
            and skip_echo["ok"] is False
            and skip_contextid["ok"] is False
            and skip_replay["ok"] is False
            and skip_flowid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="datagram-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != DATAGRAM_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_datagram"] = (
        live_goal == DATAGRAM_ACTUATION_GOAL
        and DATAGRAM_ACTUATION_ID in live_done
        and live_source == "genesis_bind_datagram"
    )

    with tempfile.TemporaryDirectory(prefix="datagram-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(DATAGRAM_LEFTOVER, root)
        register_catalog_proved(root, DATAGRAM_ACTUATION_ID)
        reason = leftover_satisfied_by(DATAGRAM_LEFTOVER, root)
        after = leftover_is_open(DATAGRAM_LEFTOVER, root)
    checks["datagram_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_datagram_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{DATAGRAM_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_datagram_actuation_capability()
    return {
        "ok": ok,
        "action": "datagram_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": DATAGRAM_ACTUATION_GOAL,
        "done_when": DATAGRAM_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
