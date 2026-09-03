"""Drive a first-class Oblivious HTTP tool through RFC 9458 ENCAPSULATE/DECAPSULATE.

Tool routing already fails missions that require ``ohttp``: hosted ohttp
endpoints stay on the unsupported MCP provider, and no first-party ohttp
provider is executable. Unbound therefore cannot speak an ENCAPSULATE,
lockstep a DECAPSULATE configid handshake over HTTP Oblivious HTTP CONFIGID,
independently poll the stored gateway, or seal a gateway digest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``ohttp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9458 daemon
- keep a missing-configid client so the ohttp-configid hole stays falsifiable
- refuse DECAPSULATE verify until an ENCAPSULATE lands with a non-empty configid
- independently poll the stored gateway on a later client socket
- persist a sealed gateway digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9484 CONNECT-IP
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
    OHTTP_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    ohttp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
OHTTP_ACTUATION_ID = "capability.ohttp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-OH-OK"
POLL_TOKEN = "BH-OH-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_CONFIGID = 0
EMPTY_GATEWAY = 0
OH_FIRST = 0x20  # RFC 9180 DHKEM(X25519, HKDF-SHA256) kem_id
CONFIGID_SIZE = 4
GATEWAY_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DECAPSULATE = 0x02  # RFC 9458 Encapsulated Response
FRAME_ENCAPSULATE = 0x01  # RFC 9458 Encapsulated Request
OHTTP_KEM_ID = 0x0020  # DHKEM(X25519, HKDF-SHA256)
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
OHTTP_LEFTOVER = (
    "Later genesis can take RFC 9458 Oblivious HTTP ENCAPSULATE/DECAPSULATE over a "
    "configid-gated gateway digest."
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


OHTTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{OHTTP_ACTUATION_ID};"
    f"capability_proved:{OHTTP_ACTUATION_ID};"
    "no_skill_route"
)
OHTTP_ACTUATION_GOAL = (
    "Repair rfc9458 ohttp encapsulate/decapsulate cycle cannot land over http "
    "ohttp configid: hosted ohttp endpoints remain unsupported so an ENCAPSULATE then "
    "DECAPSULATE configid handshake cannot land and a sealed gateway digest "
    "cannot be produced. A missing ohttp configid stays forbidden; fail-closed "
    "routing never opts the ohttp provider in. An independent later poll of the "
    "stored gateway config keeps the hole falsifiable."
)


class OhttpActuationError(RuntimeError):
    """Raised when the Oblivious HTTP session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_configid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"configid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_configid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-configid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_gateway(configid: int = EMPTY_CONFIGID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"gateway:{int(configid) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_CONFIGID = request_configid(SENTINEL)
DEFAULT_GATEWAY = request_gateway(DEFAULT_CONFIGID, SENTINEL)


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
        raise OhttpActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise OhttpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise OhttpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise OhttpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    configid: int,
    gateway: int,
    include_configid: bool = True,
) -> bytes:
    live_configid = int(configid) & 0xFFFFFFFF if include_configid else EMPTY_CONFIGID
    live_gateway = int(gateway) & 0xFFFFFFFF if include_configid and live_configid else EMPTY_GATEWAY
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_gateway, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_configid) if live_configid else b""
    header = bytearray()
    header.append(OH_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_encapsulate(
    *,
    identity: str,
    configid: int,
    gateway: int | None = None,
    include_configid: bool = True,
) -> bytes:
    live_configid = int(configid) & 0xFFFFFFFF if include_configid else EMPTY_CONFIGID
    live_gateway = int(gateway) if gateway is not None else request_gateway(live_configid, identity)
    return encode_packet(
        FRAME_ENCAPSULATE,
        identity=identity,
        configid=live_configid,
        gateway=live_gateway,
        include_configid=include_configid,
    )


def encode_decapsulate(
    *,
    identity: str,
    configid: int,
    gateway: int | None = None,
    include_configid: bool = True,
) -> bytes:
    live_configid = int(configid) & 0xFFFFFFFF if include_configid else EMPTY_CONFIGID
    live_gateway = int(gateway) if gateway is not None else request_gateway(live_configid, identity)
    return encode_packet(
        FRAME_DECAPSULATE,
        identity=identity,
        configid=live_configid,
        gateway=live_gateway,
        include_configid=include_configid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise OhttpActuationError("short_packet")
    first = raw[0]
    if first != OH_FIRST:
        raise OhttpActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise OhttpActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == CONFIGID_SIZE:
        live_configid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_configid = EMPTY_CONFIGID
    else:
        raise OhttpActuationError("illegal_configid")
    if offset >= len(raw):
        raise OhttpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ENCAPSULATE, FRAME_DECAPSULATE}:
        raise OhttpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise OhttpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise OhttpActuationError("checksum_failed")
    if len(payload) < 5:
        raise OhttpActuationError("short_packet")
    live_gateway, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise OhttpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_configid = int(live_configid) != EMPTY_CONFIGID
    has_gateway = has_configid and int(live_gateway) != EMPTY_GATEWAY
    is_encapsulate = frame_type == FRAME_ENCAPSULATE
    is_decapsulate = frame_type == FRAME_DECAPSULATE
    return {
        "type": int(frame_type),
        "is_encapsulate": is_encapsulate,
        "is_decapsulate": is_decapsulate,
        "is_response": is_decapsulate,
        "configid": int(live_configid),
        "has_configid": has_configid,
        "gateway": int(live_gateway),
        "has_gateway": has_gateway,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "ohttp_kem_id": OHTTP_KEM_ID,
    }


class OhttpClient:
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
            raise OhttpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_decapsulate"] or not packet["is_response"]:
            raise OhttpActuationError("gateway_required")
        if not packet["has_configid"]:
            raise OhttpActuationError("configid_required")
        if not packet["has_gateway"]:
            raise OhttpActuationError("gateway_required")
        return packet

    def exchange(self, packet: bytes, *, wait_gateway: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_gateway:
            raise OhttpActuationError("gateway_required")
        reply = self._recv()
        return {
            "session": reply,
            "configid": int(reply.get("configid") or EMPTY_CONFIGID),
            "identity": str(reply.get("identity") or ""),
            "gateway": int(reply.get("gateway") or EMPTY_GATEWAY),
        }

    def decapsulate(
        self,
        identity: str,
        configid: int,
        gateway: int = EMPTY_GATEWAY,
        *,
        wait_gateway: bool = True,
        include_configid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_decapsulate(
            identity=identity,
            configid=configid,
            gateway=gateway or request_gateway(configid, identity),
            include_configid=include_configid,
        )
        return self.exchange(packet, wait_gateway=wait_gateway)


class OhttpSession:
    """CONFIGID-gated loopback RFC 9458 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        configid_gate: int = DEFAULT_CONFIGID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.configid_gate = int(configid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.configid = EMPTY_CONFIGID
        self.gateway = EMPTY_GATEWAY
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

    def store_configid_once(self, identity: str, configid: int, gateway: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(configid or EMPTY_CONFIGID)
            live_gateway = int(gateway or EMPTY_GATEWAY)
            if not self.identity and name and live:
                self.identity = name
                self.configid = live
                self.gateway = live_gateway or request_gateway(live, name)
                self.stored = True
            return str(self.identity), int(self.configid), int(self.gateway)

    def read_configid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.configid), int(self.gateway)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "configid": EMPTY_CONFIGID,
            "gateway": EMPTY_GATEWAY,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _configid_missing(self) -> bool:
        return not int(self.configid_gate or 0)

    def _reply_decapsulate(self, peer: tuple[str, int], identity: str, configid: int, gateway: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_decapsulate(
            identity=identity,
            configid=configid,
            gateway=gateway,
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
            except OhttpActuationError:
                continue
            if not packet.get("is_encapsulate") and not packet.get("is_decapsulate"):
                continue
            if not packet.get("has_configid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_configid, stored_gateway = self.store_configid_once(
                identity,
                int(packet.get("configid") or EMPTY_CONFIGID),
                int(packet.get("gateway") or EMPTY_GATEWAY),
            )
            if not stored_name or not stored_configid or not stored_gateway:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_encapsulate"):
                    self.opened = True
                if packet.get("is_decapsulate"):
                    self.handshook = True
                self.retrieved = True
            self._reply_decapsulate(peer, stored_name, stored_configid, stored_gateway)

    def bind(self) -> dict[str, Any]:
        if self._configid_missing():
            return self._forbidden("missing_configid")
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
        do_encapsulate_cycle: bool = True,
        do_decapsulate: bool = True,
        do_gateway: bool = True,
        replay: bool = True,
        use_configid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._configid_missing():
            return self._forbidden("missing_configid")
        live_token = str(token or SENTINEL)
        origin_configid = request_configid(live_token)
        origin_gateway = request_gateway(origin_configid, live_token)
        client: OhttpClient | None = None
        independent: OhttpClient | None = None
        try:
            client = OhttpClient(self.host, int(self.port))
            if not do_encapsulate_cycle:
                return self._conflict("encapsulate_required")
            bind_packet = encode_encapsulate(
                identity=live_token,
                configid=origin_configid,
                gateway=origin_gateway,
                include_configid=use_configid,
            )
            if not use_configid:
                try:
                    client.exchange(bind_packet, wait_gateway=True)
                except OhttpActuationError:
                    return self._conflict("configid_required")
                return self._conflict("configid_required")
            client.send(bind_packet)
            if not do_decapsulate:
                return self._conflict("decapsulate_required")
            proxy_packet = encode_decapsulate(
                identity=live_token,
                configid=origin_configid,
                gateway=origin_gateway,
                include_configid=True,
            )
            if not do_gateway:
                try:
                    client.exchange(proxy_packet, wait_gateway=False)
                except OhttpActuationError as error:
                    if str(error) == "gateway_required":
                        return self._conflict("gateway_required")
                    return self._conflict("gateway_required")
                return self._conflict("gateway_required")
            try:
                reply = client.exchange(proxy_packet, wait_gateway=True)
            except OhttpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("configid_required")
                if reason == "gateway_required":
                    return self._conflict("gateway_required")
                return self._conflict("encapsulate_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("encapsulate_required")
            if int(reply.get("configid") or EMPTY_CONFIGID) != origin_configid:
                return self._conflict("gateway_required")
            if int(reply.get("gateway") or EMPTY_GATEWAY) != origin_gateway:
                return self._conflict("gateway_required")
            self.retrieved = True
            if replay:
                independent = OhttpClient(self.host, int(self.port))
                try:
                    poll = independent.decapsulate(
                        POLL_TOKEN,
                        poll_configid(live_token),
                        request_gateway(poll_configid(live_token), POLL_TOKEN),
                        wait_gateway=True,
                    )
                except OhttpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_configid, stored_gateway = self.read_configid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_configid != origin_configid
                    or stored_gateway != origin_gateway
                    or int(poll.get("configid") or EMPTY_CONFIGID) != origin_configid
                    or int(poll.get("gateway") or EMPTY_GATEWAY) != origin_gateway
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_configid}:{origin_gateway}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "configid": origin_configid,
                "gateway": origin_gateway,
                "encapsulate": True,
                "decapsulate": True,
                "gateway_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "configid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_ohttp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "configid": origin_configid,
                "gateway": origin_gateway,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "encapsulate": True,
                "decapsulate": True,
                "gateway_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "configid_bound": True,
            }
        except (OSError, OhttpActuationError) as error:
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
        live = independent_ohttp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "configid": int(live.get("configid") or EMPTY_CONFIGID),
            "gateway": int(live.get("gateway") or EMPTY_GATEWAY),
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


def call_ohttp_tool(session: OhttpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one OHTTP tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_encapsulate_cycle = True if arguments.get("encapsulate_cycle") is None else bool(arguments.get("encapsulate_cycle"))
    do_decapsulate = True if arguments.get("decapsulate") is None else bool(arguments.get("decapsulate"))
    do_gateway = True if arguments.get("gateway") is None else bool(arguments.get("gateway"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_configid = True if arguments.get("use_configid") is None else bool(arguments.get("use_configid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_encapsulate_cycle=do_encapsulate_cycle,
            do_decapsulate=do_decapsulate,
            do_gateway=do_gateway,
            replay=replay,
            use_configid=use_configid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise OhttpActuationError(f"unsupported ohttp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_ohttp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed OHTTP gateway digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "configid": EMPTY_CONFIGID,
        "gateway": EMPTY_GATEWAY,
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
            "encapsulate",
            "decapsulate",
            "gateway_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "configid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    configid = int(payload.get("configid") or EMPTY_CONFIGID)
    gateway = int(payload.get("gateway") or EMPTY_GATEWAY)
    dual = port > 0 and bool(configid) and bool(gateway)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "configid": configid,
        "gateway": gateway,
        "size": int(payload.get("size") or 0),
        "port": port,
        "encapsulate": payload.get("encapsulate") is True,
        "decapsulate": payload.get("decapsulate") is True,
        "gateway_response": payload.get("gateway_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "configid_bound": payload.get("configid_bound") is True,
    }


def run_ohttp_workflow(
    *,
    with_configid: bool = True,
    skip_bind: bool = False,
    do_encapsulate_cycle: bool = True,
    do_decapsulate: bool = True,
    do_gateway: bool = True,
    replay: bool = True,
    use_configid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9458 ENCAPSULATE/DECAPSULATE configid cycle workflow."""

    descriptor = ohttp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, OHTTP_TOOL_PROVIDER),
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
        raise OhttpActuationError(f"ohttp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ohttp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = OhttpSession(out, configid_gate=DEFAULT_CONFIGID if with_configid else EMPTY_CONFIGID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "encapsulate_cycle": do_encapsulate_cycle,
            "decapsulate": do_decapsulate,
            "gateway": do_gateway,
            "replay": replay,
            "use_configid": use_configid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_ohttp_tool(session, arguments))
            except OhttpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_ohttp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_configid
        and not skip_bind
        and do_encapsulate_cycle
        and do_decapsulate
        and do_gateway
        and replay
        and use_configid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ohttp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_configid": with_configid,
        "skip_bind": skip_bind,
        "encapsulate": do_encapsulate_cycle,
        "decapsulate": do_decapsulate,
        "gateway": do_gateway,
        "replay": replay,
        "use_configid": use_configid,
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
        "configid_value": int(publish_result.get("configid") or independent.get("configid") or EMPTY_CONFIGID),
        "gateway_value": int(publish_result.get("gateway") or independent.get("gateway") or EMPTY_GATEWAY),
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
        "configid": int(trace_body["configid_value"] or EMPTY_CONFIGID),
        "gateway": int(trace_body["gateway_value"] or EMPTY_GATEWAY),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_configid": with_configid,
        "skip_bind": skip_bind,
        "encapsulate_cycle": do_encapsulate_cycle,
        "decapsulate_cycle": do_decapsulate,
        "gateway_cycle": do_gateway,
        "replay": replay,
        "use_configid": use_configid,
    }


def verify_ohttp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed OHTTP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_ohttp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    configid = int(trace.get("configid_value") or independent.get("configid") or EMPTY_CONFIGID)
    gateway = int(trace.get("gateway_value") or independent.get("gateway") or EMPTY_GATEWAY)
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
        "encapsulate": independent.get("encapsulate") is True,
        "decapsulate": independent.get("decapsulate") is True,
        "gateway_response": independent.get("gateway_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "configid_bound": independent.get("configid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "gateway_recorded": (
            port > 0
            and configid == DEFAULT_CONFIGID
            and gateway == DEFAULT_GATEWAY
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}

def ohttp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.ohttp_actuation import "
        "builtin_ohttp_actuation_proof; r=builtin_ohttp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='ohttp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_ohttp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=OHTTP_ACTUATION_ID,
        name="First-class RFC 9458 Oblivious HTTP ENCAPSULATE/DECAPSULATE actuation",
        description=(
            "Missions that require an ohttp tool can opt the ohttp provider in, "
            "bind a loopback RFC 9458 Oblivious HTTP gateway, complete an ENCAPSULATE "
            "with a non-empty configid, lockstep a DECAPSULATE that carries the "
            "stored gateway, independently poll the stored "
            "gateway on a later socket, and seal a digest-chained gateway. Default "
            "routing stays fail-closed; a missing configid keeps the hole "
            "falsifiable, and skip-ENCAPSULATE/DECAPSULATE/GATEWAY/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.ohttp_actuation:builtin_ohttp_actuation_proof",
        proof_command=ohttp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.connectip-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/ohttp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/ohsvcb_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required ohttp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9458 daemon, speaks an "
            "ENCAPSULATE then DECAPSULATE over Oblivious HTTP with a non-empty configid and "
            "gateway, independently polls the stored gateway on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9484 CONNECT-IP lockstep is proved. "
            "Missing configids, skip-ENCAPSULATE, skip-DECAPSULATE, skip-gateway, skip-REPLAY, "
            "and an ENCAPSULATE aimed without a configid stay fail-closed. "
            "Later genesis can take RFC 9540 Oblivious Service Binding QUERY/ANSWER as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("ohttp", "rfc9458", "http", "configid", "gateway", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T060945Z-f6f01fa3",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_ohttp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9458 Oblivious HTTP lockstep actuation seals a gateway digest."""

    from blackhole_agent.ohsvcb_actuation import OHSVCB_ACTUATION_GOAL, OHSVCB_ACTUATION_ID
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
    checks["denylists_self"] = OHTTP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(OHTTP_ACTUATION_GOAL) == (
        OHTTP_ACTUATION_ID,
    )
    checks["leftover_text_binds_ohttp"] = leftover_marker_ids(OHTTP_LEFTOVER) == (
        OHTTP_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (OHSVCB_ACTUATION_GOAL, OHSVCB_ACTUATION_ID, "ohsvcb"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_ohttp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"ohttp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            OHTTP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = OHTTP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    checks["catalog_names_ohttp"] = (
        len(catalog) > 67
        and catalog[67]["id"] == OHTTP_ACTUATION_ID
        and catalog[66]["id"] == CONNECTIP_ACTUATION_ID
        and catalog[67]["source"] == "genesis_bind_ohttp"
    )
    checks["catalog_names_ohsvcb"] = (
        len(catalog) > 68
        and catalog[68]["id"] == OHSVCB_ACTUATION_ID
        and catalog[68]["source"] == "genesis_bind_ohsvcb"
    )
    family = capability_family(OHTTP_ACTUATION_GOAL)
    checks["family_is_ohttp"] = "ohttp" in family
    checks["family_is_rfc9458"] = "rfc9458" in family
    checks["family_is_configid"] = "configid" in family
    checks["family_is_gateway"] = "gateway" in family
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
    checks["family_is_not_ohsvcb"] = (
        "ohsvcb" not in family
        and "rfc9540" not in family
        and "svcbid" not in family
        and "keyconf" not in family
    )
    packed = encode_encapsulate(identity=SENTINEL, configid=DEFAULT_CONFIGID, gateway=DEFAULT_GATEWAY)
    parsed = parse_message(packed)
    checks["encapsulate_roundtrip"] = (
        parsed["is_encapsulate"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_configid"] is True
        and parsed["configid"] == DEFAULT_CONFIGID
        and parsed["gateway"] == DEFAULT_GATEWAY
        and parsed["is_response"] is False
        and parsed["is_decapsulate"] is False
        and parsed["type"] == FRAME_ENCAPSULATE
        and parsed["first_byte"] == OH_FIRST
    )
    shook = encode_decapsulate(
        identity=SENTINEL,
        configid=DEFAULT_CONFIGID,
        gateway=DEFAULT_GATEWAY,
    )
    decapsulate_parsed = parse_message(shook)
    checks["decapsulate_roundtrip"] = (
        decapsulate_parsed["is_decapsulate"] is True
        and decapsulate_parsed["is_response"] is True
        and decapsulate_parsed["is_encapsulate"] is False
        and decapsulate_parsed["identity"] == SENTINEL
        and decapsulate_parsed["configid"] == DEFAULT_CONFIGID
        and decapsulate_parsed["gateway"] == DEFAULT_GATEWAY
        and decapsulate_parsed["has_gateway"] is True
        and decapsulate_parsed["type"] == FRAME_DECAPSULATE
        and decapsulate_parsed["first_byte"] == OH_FIRST
    )
    bare = encode_encapsulate(identity=SENTINEL, configid=DEFAULT_CONFIGID, include_configid=False)
    checks["missing_configid_is_unauthenticated"] = parse_message(bare)["has_configid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    ohttp_signature = semantic_signature(OHTTP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(ohttp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_ohttp = ToolDescriptor(name="remote_ohttp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_ohttp)
    checks["naive_mcp_ohttp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = ohttp_tool_descriptor()
    default_ohttp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, OHTTP_TOOL_PROVIDER),
    )
    checks["default_ohttp_provider_is_unsupported"] = (
        default_ohttp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{OHTTP_TOOL_PROVIDER}" in default_ohttp.reasons
    )
    checks["opted_in_ohttp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_ohttp],
        required_tool_names=("local_memory", "ohttp"),
    )
    checks["naive_preflight_missing_ohttp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["ohttp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "ohttp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, OHTTP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "ohttp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="ohttp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_ohttp_workflow(with_configid=False, output_dir=root / "missing")
        skip_bind = run_ohttp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_encapsulate_cycle = run_ohttp_workflow(do_encapsulate_cycle=False, output_dir=root / "skip-bind-cycle")
        skip_decapsulate = run_ohttp_workflow(do_decapsulate=False, output_dir=root / "skip-proxy")
        skip_gateway = run_ohttp_workflow(do_gateway=False, output_dir=root / "skip-gateway")
        skip_replay = run_ohttp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_configid = run_ohttp_workflow(use_configid=False, output_dir=root / "skip-configid")
        live = run_ohttp_workflow(output_dir=root / "live")
        verify = verify_ohttp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_ohttp_trace(clone)
        checks["naive_without_configid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_configid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_encapsulate_cycle_stays_empty"] = (
            skip_encapsulate_cycle["ok"] is False
            and skip_encapsulate_cycle["error"] == "encapsulate_required"
            and skip_encapsulate_cycle["final_status"] == 409
            and skip_encapsulate_cycle["payload_exists"] is False
        )
        checks["skip_decapsulate_stays_empty"] = (
            skip_decapsulate["ok"] is False
            and skip_decapsulate["error"] == "decapsulate_required"
            and skip_decapsulate["final_status"] == 409
            and skip_decapsulate["payload_exists"] is False
        )
        checks["skip_gateway_stays_empty"] = (
            skip_gateway["ok"] is False
            and skip_gateway["error"] == "gateway_required"
            and skip_gateway["final_status"] == 409
            and skip_gateway["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_configid_stays_empty"] = (
            skip_configid["ok"] is False
            and skip_configid["error"] == "configid_required"
            and skip_configid["final_status"] == 409
            and skip_configid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_gateway"] = (
            int(live.get("configid") or 0) == DEFAULT_CONFIGID
            and int(live.get("gateway") or 0) == DEFAULT_GATEWAY
            and int(live.get("port") or 0) > 0
        )
        checks["token_configid_encapsulate_decapsulate_gateway_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_encapsulate_cycle["ok"] is False
            and skip_decapsulate["ok"] is False
            and skip_gateway["ok"] is False
            and skip_replay["ok"] is False
            and skip_configid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="ohttp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != OHTTP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_ohttp"] = (
        live_goal == OHTTP_ACTUATION_GOAL
        and OHTTP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_ohttp"
    )

    with tempfile.TemporaryDirectory(prefix="ohttp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(OHTTP_LEFTOVER, root)
        register_catalog_proved(root, OHTTP_ACTUATION_ID)
        reason = leftover_satisfied_by(OHTTP_LEFTOVER, root)
        after = leftover_is_open(OHTTP_LEFTOVER, root)
    checks["ohttp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_ohttp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{OHTTP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_ohttp_actuation_capability()
    return {
        "ok": ok,
        "action": "ohttp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": OHTTP_ACTUATION_GOAL,
        "done_when": OHTTP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
