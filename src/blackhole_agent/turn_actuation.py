"""Drive a first-class TURN tool through RFC 5766 Allocate/Success.

Tool routing already fails missions that require ``turn``: hosted TURN
plugins stay on the unsupported MCP provider, and no first-party TURN
provider is executable. Unbound therefore cannot speak Allocate, lockstep
an Allocation Success nonce handshake over UDP TURN, independently poll
the stored allocation nonce, or seal a relay digest an independent later
reader can re-open.

This module closes that hole:

- advertise a ``turn`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 5766 daemon
- keep a missing-nonce client so the allocation-nonce hole stays falsifiable
- refuse Allocation Success until Allocate lands with a non-empty nonce
- independently poll the stored allocation nonce on a later client socket
- persist a sealed relay digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after STUN
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
    TURN_TOOL_PROVIDER,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    turn_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
TURN_ACTUATION_ID = "capability.turn-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-TURN-OK"
POLL_TOKEN = "BH-TURN-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
HEADER_SIZE = 20
EMPTY_NONCE = b""
ZERO_TXID = b"\x00" * 12
MAGIC_COOKIE = 0x2112A442
ALLOCATE_REQUEST = 0x0003
ALLOCATE_SUCCESS = 0x0103
ATTR_USERNAME = 0x0006
ATTR_LIFETIME = 0x000D
ATTR_NONCE = 0x0015
ATTR_XOR_RELAYED = 0x0016
ATTR_REQUESTED_TRANSPORT = 0x0019
ATTR_XOR_MAPPED = 0x0020
FAMILY_IPV4 = 0x01
PROTO_UDP = 17
DEFAULT_LIFETIME = 600
HEADER_STRUCT = struct.Struct("!HHI12s")
ATTR_HEADER_STRUCT = struct.Struct("!HH")

TURN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TURN_ACTUATION_ID};"
    f"capability_proved:{TURN_ACTUATION_ID};"
    "no_skill_route"
)
TURN_ACTUATION_GOAL = (
    "Repair rfc5766 turn allocate/success cycle cannot land over udp "
    "turn: hosted turn relays remain unsupported so an Allocate then "
    "Allocation Success nonce handshake cannot land and a sealed relay digest "
    "cannot be produced. A missing turn nonce stays forbidden; fail-closed "
    "routing never opts the turn provider in. An independent later poll of the "
    "stored allocation nonce keeps the hole falsifiable."
)


class TurnActuationError(RuntimeError):
    """Raised when the TURN session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def _pad4(length: int) -> int:
    return (4 - (int(length) % 4)) % 4


def _nonzero_txid(digest: bytes) -> bytes:
    value = bytes(digest[:12])
    if value == ZERO_TXID:
        return b"\x00" * 11 + b"\x01"
    return value


def request_nonce(token: str = SENTINEL) -> bytes:
    digest = hashlib.sha256(f"nonce:{token or SENTINEL}".encode("utf-8")).digest()
    return bytes(digest[:16])


def poll_nonce(token: str = SENTINEL) -> bytes:
    digest = hashlib.sha256(f"poll:{token or SENTINEL}".encode("utf-8")).digest()
    return bytes(digest[:16])


def nonce_hex(nonce: bytes) -> str:
    return bytes(nonce or EMPTY_NONCE).hex()


def _txid_from_nonce(nonce: bytes) -> bytes:
    digest = hashlib.sha256(b"txid:" + bytes(nonce or EMPTY_NONCE)).digest()
    return _nonzero_txid(digest)


DEFAULT_NONCE = request_nonce(SENTINEL)
DEFAULT_NONCE_HEX = nonce_hex(DEFAULT_NONCE)


def encode_username(identity: str) -> bytes:
    data = str(identity or "").encode("utf-8")
    if not data:
        return b""
    return ATTR_HEADER_STRUCT.pack(ATTR_USERNAME, len(data)) + data + (b"\x00" * _pad4(len(data)))


def encode_nonce(nonce: bytes) -> bytes:
    data = bytes(nonce or EMPTY_NONCE)
    if not data:
        return b""
    return ATTR_HEADER_STRUCT.pack(ATTR_NONCE, len(data)) + data + (b"\x00" * _pad4(len(data)))


def encode_requested_transport(protocol: int = PROTO_UDP) -> bytes:
    body = bytes((int(protocol) & 0xFF, 0, 0, 0))
    return ATTR_HEADER_STRUCT.pack(ATTR_REQUESTED_TRANSPORT, 4) + body


def encode_lifetime(seconds: int = DEFAULT_LIFETIME) -> bytes:
    body = struct.pack("!I", int(seconds) & 0xFFFFFFFF)
    return ATTR_HEADER_STRUCT.pack(ATTR_LIFETIME, 4) + body


def encode_xor_address(attr_type: int, host: str, port: int) -> bytes:
    try:
        addr = struct.unpack("!I", socket.inet_aton(str(host or "127.0.0.1")))[0]
    except OSError:
        addr = struct.unpack("!I", socket.inet_aton("127.0.0.1"))[0]
    xport = int(port or 0) ^ (MAGIC_COOKIE >> 16)
    xaddr = int(addr) ^ MAGIC_COOKIE
    body = bytes((0, FAMILY_IPV4)) + struct.pack("!H", xport & 0xFFFF) + struct.pack("!I", xaddr & 0xFFFFFFFF)
    return ATTR_HEADER_STRUCT.pack(int(attr_type) & 0xFFFF, 8) + body


def encode_xor_relayed_address(host: str, port: int) -> bytes:
    return encode_xor_address(ATTR_XOR_RELAYED, host, port)


def encode_xor_mapped_address(host: str, port: int) -> bytes:
    return encode_xor_address(ATTR_XOR_MAPPED, host, port)


def _decode_xor_address(value: bytes) -> tuple[str, int]:
    if len(value) < 8 or value[1] != FAMILY_IPV4:
        return "", 0
    xport = struct.unpack("!H", value[2:4])[0]
    xaddr = struct.unpack("!I", value[4:8])[0]
    mapped_port = int(xport) ^ (MAGIC_COOKIE >> 16)
    mapped_host = socket.inet_ntoa(struct.pack("!I", int(xaddr) ^ MAGIC_COOKIE))
    return mapped_host, mapped_port


def parse_attributes(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    offset = 0
    username = ""
    nonce = EMPTY_NONCE
    relayed_host = ""
    relayed_port = 0
    mapped_host = ""
    mapped_port = 0
    lifetime = 0
    transport = 0
    while offset + 4 <= len(raw):
        atype, alen = ATTR_HEADER_STRUCT.unpack(raw[offset : offset + 4])
        offset += 4
        if offset + int(alen) > len(raw):
            break
        value = raw[offset : offset + int(alen)]
        offset += int(alen) + _pad4(int(alen))
        if int(atype) == ATTR_USERNAME:
            username = value.decode("utf-8", errors="replace")
        elif int(atype) == ATTR_NONCE:
            nonce = bytes(value)
        elif int(atype) == ATTR_XOR_RELAYED:
            relayed_host, relayed_port = _decode_xor_address(value)
        elif int(atype) == ATTR_XOR_MAPPED:
            mapped_host, mapped_port = _decode_xor_address(value)
        elif int(atype) == ATTR_LIFETIME and len(value) >= 4:
            lifetime = int(struct.unpack("!I", value[:4])[0])
        elif int(atype) == ATTR_REQUESTED_TRANSPORT and value:
            transport = int(value[0])
    return {
        "username": username,
        "nonce": nonce,
        "relayed_host": relayed_host,
        "relayed_port": relayed_port,
        "mapped_host": mapped_host,
        "mapped_port": mapped_port,
        "lifetime": lifetime,
        "transport": transport,
    }


def _encode_message(msg_type: int, txid: bytes, attributes: bytes) -> bytes:
    live = bytes(txid or ZERO_TXID)
    if len(live) < 12:
        live = live + ZERO_TXID[: 12 - len(live)]
    live = live[:12]
    attrs = bytes(attributes or b"")
    header = HEADER_STRUCT.pack(int(msg_type) & 0xFFFF, len(attrs), MAGIC_COOKIE, live)
    return header + attrs


def encode_allocate(
    *,
    identity: str,
    nonce: bytes,
    include_nonce: bool = True,
) -> bytes:
    live = bytes(nonce or EMPTY_NONCE) if include_nonce else EMPTY_NONCE
    attributes = encode_username(identity) + encode_requested_transport()
    if include_nonce:
        attributes += encode_nonce(live)
    return _encode_message(ALLOCATE_REQUEST, _txid_from_nonce(live), attributes)


def encode_success(
    *,
    identity: str,
    nonce: bytes,
    relayed_host: str = "127.0.0.1",
    relayed_port: int = 0,
    mapped_host: str = "127.0.0.1",
    mapped_port: int = 0,
    include_nonce: bool = True,
) -> bytes:
    live = bytes(nonce or EMPTY_NONCE) if include_nonce else EMPTY_NONCE
    attributes = (
        encode_username(identity)
        + encode_nonce(live)
        + encode_lifetime()
        + encode_xor_relayed_address(relayed_host, relayed_port)
        + encode_xor_mapped_address(mapped_host, mapped_port)
    )
    return _encode_message(ALLOCATE_SUCCESS, _txid_from_nonce(live), attributes)


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < HEADER_SIZE:
        raise TurnActuationError("short_packet")
    msg_type, length, magic, txid = HEADER_STRUCT.unpack(raw[:HEADER_SIZE])
    if int(magic) != MAGIC_COOKIE:
        raise TurnActuationError("illegal_cookie")
    if int(length) < 0 or HEADER_SIZE + int(length) > len(raw):
        raise TurnActuationError("illegal_length")
    if int(msg_type) not in {ALLOCATE_REQUEST, ALLOCATE_SUCCESS}:
        raise TurnActuationError("illegal_method")
    attrs = parse_attributes(raw[HEADER_SIZE : HEADER_SIZE + int(length)])
    identity = str(attrs.get("username") or "")
    live_nonce = bytes(attrs.get("nonce") or EMPTY_NONCE)
    is_allocate = int(msg_type) == ALLOCATE_REQUEST
    is_success = int(msg_type) == ALLOCATE_SUCCESS
    return {
        "type": int(msg_type),
        "is_allocate": is_allocate,
        "is_success": is_success,
        "is_response": is_success,
        "txid": bytes(txid),
        "nonce": live_nonce,
        "nonce_hex": nonce_hex(live_nonce),
        "identity": identity,
        "has_identity": bool(identity),
        "has_nonce": bool(live_nonce),
        "relayed_host": str(attrs.get("relayed_host") or ""),
        "relayed_port": int(attrs.get("relayed_port") or 0),
        "mapped_host": str(attrs.get("mapped_host") or ""),
        "mapped_port": int(attrs.get("mapped_port") or 0),
        "lifetime": int(attrs.get("lifetime") or 0),
        "transport": int(attrs.get("transport") or 0),
    }


class _TurnClient:
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

    def _recv(self) -> dict[str, Any]:
        try:
            payload, _addr = self.sock.recvfrom(65535)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise TurnActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_success"] or not packet["is_response"]:
            raise TurnActuationError("success_required")
        if not packet["has_nonce"]:
            raise TurnActuationError("nonce_required")
        return packet

    def exchange(
        self,
        packet: bytes,
        *,
        wait_allocate: bool = True,
        wait_success: bool = True,
    ) -> dict[str, Any]:
        if not wait_allocate:
            raise TurnActuationError("allocate_required")
        self.sock.sendto(bytes(packet or b""), (self.host, self.port))
        if not wait_success:
            raise TurnActuationError("success_required")
        reply = self._recv()
        return {
            "allocate": True,
            "success": reply,
            "nonce": bytes(reply.get("nonce") or EMPTY_NONCE),
            "nonce_hex": str(reply.get("nonce_hex") or ""),
            "identity": str(reply.get("identity") or ""),
            "relayed_port": int(reply.get("relayed_port") or 0),
        }

    def allocate(
        self,
        identity: str,
        nonce: bytes,
        *,
        wait_allocate: bool = True,
        wait_success: bool = True,
        include_nonce: bool = True,
    ) -> dict[str, Any]:
        packet = encode_allocate(
            identity=identity,
            nonce=nonce,
            include_nonce=include_nonce,
        )
        return self.exchange(packet, wait_allocate=wait_allocate, wait_success=wait_success)


class TurnSession:
    """Nonce-gated loopback RFC 5766 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        nonce_gate: bytes = DEFAULT_NONCE,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.nonce_gate = bytes(nonce_gate or b"")
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.relay_sock: socket.socket | None = None
        self.relay_host = "127.0.0.1"
        self.relay_port = 0
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.nonce = EMPTY_NONCE
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_nonce_once(self, identity: str, nonce: bytes) -> tuple[str, bytes]:
        with self._lock:
            name = str(identity or "")
            live = bytes(nonce or EMPTY_NONCE)
            if not self.identity and name:
                self.identity = name
                self.nonce = live
                self.stored = True
            return str(self.identity), bytes(self.nonce)

    def read_nonce(self) -> tuple[str, bytes]:
        with self._lock:
            return str(self.identity), bytes(self.nonce)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "nonce": "",
            "allocation_nonce": "",
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _nonce_missing(self) -> bool:
        gate = bytes(self.nonce_gate or b"")
        return not gate

    def _ensure_relay(self) -> tuple[str, int]:
        if self.relay_sock is not None and int(self.relay_port or 0) > 0:
            return str(self.relay_host), int(self.relay_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()[:2]
        self.relay_sock = sock
        self.relay_host = str(host)
        self.relay_port = int(port)
        return self.relay_host, self.relay_port

    def _reply_success(self, peer: tuple[str, int], identity: str, nonce: bytes) -> None:
        sock = self.sock
        if sock is None:
            return
        relay_host, relay_port = self._ensure_relay()
        packet = encode_success(
            identity=identity,
            nonce=nonce,
            relayed_host=relay_host,
            relayed_port=relay_port,
            mapped_host=str(peer[0]),
            mapped_port=int(peer[1]),
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
            except TurnActuationError:
                continue
            if packet.get("is_response"):
                continue
            if not packet.get("is_allocate"):
                continue
            if not packet.get("has_nonce"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_nonce = self.store_nonce_once(
                identity,
                bytes(packet.get("nonce") or EMPTY_NONCE),
            )
            if not stored_name or not stored_nonce:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                self.retrieved = True
            self._reply_success(peer, stored_name, stored_nonce)

    def bind(self) -> dict[str, Any]:
        if self._nonce_missing():
            return self._forbidden("missing_nonce")
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
        self._ensure_relay()
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
        do_allocate: bool = True,
        do_success: bool = True,
        replay: bool = True,
        use_nonce: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._nonce_missing():
            return self._forbidden("missing_nonce")
        live_token = str(token or SENTINEL)
        origin_nonce = request_nonce(live_token)
        origin_hex = nonce_hex(origin_nonce)
        client: _TurnClient | None = None
        independent: _TurnClient | None = None
        try:
            client = _TurnClient(self.host, int(self.port))
            if not do_allocate:
                return self._conflict("allocate_required")
            packet = encode_allocate(
                identity=live_token,
                nonce=origin_nonce,
                include_nonce=use_nonce,
            )
            if not use_nonce:
                try:
                    client.exchange(packet, wait_allocate=True, wait_success=True)
                except TurnActuationError:
                    return self._conflict("nonce_required")
                return self._conflict("nonce_required")
            if not do_success:
                try:
                    client.exchange(packet, wait_allocate=True, wait_success=False)
                except TurnActuationError as error:
                    if str(error) == "success_required":
                        return self._conflict("success_required")
                    return self._conflict("success_required")
                return self._conflict("success_required")
            try:
                reply = client.exchange(packet, wait_allocate=True, wait_success=True)
            except TurnActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("nonce_required")
                if reason == "allocate_required":
                    return self._conflict("allocate_required")
                if reason == "success_required":
                    return self._conflict("success_required")
                return self._conflict("allocate_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("allocate_required")
            if bytes(reply.get("nonce") or b"") != origin_nonce:
                return self._conflict("success_required")
            if int(reply.get("relayed_port") or 0) <= 0:
                return self._conflict("success_required")
            self.retrieved = True
            if replay:
                independent = _TurnClient(self.host, int(self.port))
                try:
                    poll = independent.allocate(
                        POLL_TOKEN,
                        poll_nonce(live_token),
                        wait_allocate=True,
                        wait_success=True,
                    )
                except TurnActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_nonce = self.read_nonce()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_nonce != origin_nonce
                    or bytes(poll.get("nonce") or b"") != origin_nonce
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_hex}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "nonce": origin_hex,
                "relayed_port": int(self.relay_port or 0),
                "allocate": True,
                "success_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "nonce_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_turn_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "nonce": origin_hex,
                "allocation_nonce": origin_hex,
                "relayed_port": int(self.relay_port or 0),
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "allocate": True,
                "success_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "nonce_bound": True,
            }
        except (OSError, TurnActuationError) as error:
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
        live = independent_turn_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "nonce": str(live.get("nonce") or ""),
            "allocation_nonce": str(live.get("nonce") or ""),
            "port": int(live.get("port") or 0),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        self._running = False
        sock = self.sock
        relay = self.relay_sock
        thread = self.thread
        self.sock = None
        self.relay_sock = None
        self.thread = None
        self.host = None
        self.port = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if relay is not None:
            try:
                relay.close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=1)
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_turn_tool(session: TurnSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one TURN tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_allocate = True if arguments.get("allocate") is None else bool(arguments.get("allocate"))
    do_success = True if arguments.get("success") is None else bool(arguments.get("success"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_nonce = True if arguments.get("use_nonce") is None else bool(arguments.get("use_nonce"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_allocate=do_allocate,
            do_success=do_success,
            replay=replay,
            use_nonce=use_nonce,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise TurnActuationError(f"unsupported turn action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_turn_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed TURN relay digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "nonce": "",
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
            "allocate",
            "success_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "nonce_bound",
        )
    )
    port = int(payload.get("port") or 0)
    nonce = str(payload.get("nonce") or "")
    dual = port > 0 and bool(nonce)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "nonce": nonce,
        "size": int(payload.get("size") or 0),
        "port": port,
        "relayed_port": int(payload.get("relayed_port") or 0),
        "allocate": payload.get("allocate") is True,
        "success_response": payload.get("success_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "nonce_bound": payload.get("nonce_bound") is True,
    }


def run_turn_workflow(
    *,
    with_nonce: bool = True,
    skip_bind: bool = False,
    do_allocate: bool = True,
    do_success: bool = True,
    replay: bool = True,
    use_nonce: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 5766 Allocate/Success workflow."""

    descriptor = turn_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TURN_TOOL_PROVIDER),
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
        raise TurnActuationError(f"turn tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="turn-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = TurnSession(out, nonce_gate=DEFAULT_NONCE if with_nonce else b"")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "allocate": do_allocate,
            "success": do_success,
            "replay": replay,
            "use_nonce": use_nonce,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_turn_tool(session, arguments))
            except TurnActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_turn_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_nonce
        and not skip_bind
        and do_allocate
        and do_success
        and replay
        and use_nonce
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "turn_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_nonce": with_nonce,
        "skip_bind": skip_bind,
        "allocate": do_allocate,
        "success": do_success,
        "replay": replay,
        "use_nonce": use_nonce,
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
        "nonce_value": str(publish_result.get("nonce") or independent.get("nonce") or ""),
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
        "nonce": str(trace_body["nonce_value"] or ""),
        "allocation_nonce": str(trace_body["nonce_value"] or ""),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_nonce": with_nonce,
        "skip_bind": skip_bind,
        "allocate": do_allocate,
        "success_cycle": do_success,
        "replay": replay,
        "use_nonce": use_nonce,
    }


def verify_turn_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed TURN trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_turn_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    nonce = str(trace.get("nonce_value") or independent.get("nonce") or "")
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
        "allocate": independent.get("allocate") is True,
        "success_response": independent.get("success_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "nonce_bound": independent.get("nonce_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "nonce_recorded": port > 0 and nonce == DEFAULT_NONCE_HEX,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def turn_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.turn_actuation import "
        "builtin_turn_actuation_proof; r=builtin_turn_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='turn_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_turn_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=TURN_ACTUATION_ID,
        name="First-class RFC 5766 TURN Allocate/Success actuation",
        description=(
            "Missions that require a turn tool can opt the turn provider in, "
            "bind a loopback RFC 5766 UDP TURN relay, complete Allocate with a "
            "non-empty nonce, lockstep an Allocation Success that carries the "
            "stored allocation nonce and XOR-RELAYED-ADDRESS, independently "
            "poll the stored allocation nonce on a later socket, and seal a "
            "digest-chained relay. Default routing stays fail-closed; a missing "
            "nonce keeps the hole falsifiable, and skip-ALLOCATE/SUCCESS/REPLAY "
            "stay empty."
        ),
        kind="python",
        entry="blackhole_agent.turn_actuation:builtin_turn_actuation_proof",
        proof_command=turn_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.stun-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/turn_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/ice_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required turn tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 5766 daemon, speaks Allocate "
            "then Allocation Success over UDP TURN with a non-empty nonce, "
            "independently polls the stored allocation nonce on a later client "
            "socket, and binds this family as the next diversity-catalog "
            "successor once RFC 5389 STUN lockstep is proved. Missing nonces, "
            "skip-Allocate, skip-Allocation-Success, skip-REPLAY, and Allocate "
            "aimed without a nonce stay fail-closed. Later genesis can take "
            "RFC 8445 ICE connectivity-check/nominated-pair as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("turn", "rfc5766", "udp", "nonce", "relay", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T223141Z-6fc9a7e3",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_turn_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 5766 TURN lockstep actuation seals a relay digest."""

    from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
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
    from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
    from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = TURN_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(TURN_ACTUATION_GOAL) == (TURN_ACTUATION_ID,)
    checks["stun_goal_is_not_turn"] = leftover_marker_ids(STUN_ACTUATION_GOAL) == (STUN_ACTUATION_ID,)
    checks["sip_goal_is_not_turn"] = leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    checks["ike_goal_is_not_turn"] = leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    checks["dhcp_goal_is_not_turn"] = leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    checks["radius_goal_is_not_turn"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_turn"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_turn"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_turn"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_turn"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_turn"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_turn"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["ice_goal_is_not_turn"] = leftover_marker_ids(ICE_ACTUATION_GOAL) == (ICE_ACTUATION_ID,)
    checks["turn_goal_is_not_stun"] = STUN_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_sip"] = SIP_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_ike"] = IKE_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_dhcp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_radius"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["turn_goal_is_not_ice"] = ICE_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["stun_marker_stays_stun"] = TURN_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["sip_marker_stays_sip"] = TURN_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["ike_marker_stays_ike"] = TURN_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["dhcp_marker_stays_dhcp"] = TURN_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["radius_marker_stays_radius"] = TURN_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["ntp_marker_stays_ntp"] = TURN_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = TURN_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = TURN_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = TURN_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = TURN_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = TURN_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["ice_marker_stays_ice"] = TURN_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_turn"] = (
        len(catalog) > 55
        and catalog[55]["id"] == TURN_ACTUATION_ID
        and catalog[54]["id"] == STUN_ACTUATION_ID
        and catalog[55]["source"] == "genesis_bind_turn"
    )
    checks["catalog_names_ice"] = (
        len(catalog) > 56
        and catalog[56]["id"] == ICE_ACTUATION_ID
        and catalog[56]["source"] == "genesis_bind_ice"
    )
    family = capability_family(TURN_ACTUATION_GOAL)
    checks["family_is_turn"] = "turn" in family
    checks["family_is_rfc5766"] = "rfc5766" in family
    checks["family_is_relay"] = "relay" in family
    checks["family_is_nonce"] = "nonce" in family
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
    checks["family_is_not_ice"] = (
        "ice" not in family and "rfc8445" not in family and "ufrag" not in family and "foundation" not in family
    )
    packed = encode_allocate(identity=SENTINEL, nonce=DEFAULT_NONCE)
    parsed = parse_message(packed)
    checks["allocate_roundtrip"] = (
        parsed["is_allocate"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_nonce"] is True
        and parsed["nonce"] == DEFAULT_NONCE
        and parsed["is_response"] is False
        and parsed["is_success"] is False
        and parsed["transport"] == PROTO_UDP
    )
    success_packet = encode_success(
        identity=SENTINEL,
        nonce=DEFAULT_NONCE,
        relayed_port=49152,
        mapped_port=3478,
    )
    success_parsed = parse_message(success_packet)
    checks["success_roundtrip"] = (
        success_parsed["is_success"] is True
        and success_parsed["identity"] == SENTINEL
        and success_parsed["nonce"] == DEFAULT_NONCE
        and success_parsed["is_response"] is True
        and success_parsed["is_allocate"] is False
        and success_parsed["relayed_port"] == 49152
        and success_parsed["relayed_host"] == "127.0.0.1"
        and success_parsed["mapped_port"] == 3478
        and success_parsed["lifetime"] == DEFAULT_LIFETIME
    )
    bare = encode_allocate(identity=SENTINEL, nonce=DEFAULT_NONCE, include_nonce=False)
    checks["missing_nonce_is_unauthenticated"] = parse_message(bare)["has_nonce"] is False
    neighbors = (
        STUN_ACTUATION_GOAL,
        SIP_ACTUATION_GOAL,
        IKE_ACTUATION_GOAL,
        DHCP_ACTUATION_GOAL,
        RADIUS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        ICE_ACTUATION_GOAL,
    )
    turn_signature = semantic_signature(TURN_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(turn_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_turn = ToolDescriptor(name="remote_turn", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_turn)
    checks["naive_mcp_turn_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = turn_tool_descriptor()
    default_turn = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TURN_TOOL_PROVIDER),
    )
    checks["default_turn_provider_is_unsupported"] = (
        default_turn.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{TURN_TOOL_PROVIDER}" in default_turn.reasons
    )
    checks["opted_in_turn_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_turn],
        required_tool_names=("local_memory", "turn"),
    )
    checks["naive_preflight_missing_turn"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["turn"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "turn"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TURN_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "turn" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="turn-actuation-") as tmp:
        root = Path(tmp)
        missing = run_turn_workflow(with_nonce=False, output_dir=root / "missing")
        skip_bind = run_turn_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_allocate = run_turn_workflow(do_allocate=False, output_dir=root / "skip-allocate")
        skip_success = run_turn_workflow(do_success=False, output_dir=root / "skip-success")
        skip_replay = run_turn_workflow(replay=False, output_dir=root / "skip-replay")
        skip_nonce = run_turn_workflow(use_nonce=False, output_dir=root / "skip-nonce")
        live = run_turn_workflow(output_dir=root / "live")
        verify = verify_turn_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_turn_trace(clone)
        checks["naive_without_nonce_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_nonce"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_allocate_stays_empty"] = (
            skip_allocate["ok"] is False
            and skip_allocate["error"] == "allocate_required"
            and skip_allocate["final_status"] == 409
            and skip_allocate["payload_exists"] is False
        )
        checks["skip_success_stays_empty"] = (
            skip_success["ok"] is False
            and skip_success["error"] == "success_required"
            and skip_success["final_status"] == 409
            and skip_success["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_nonce_stays_empty"] = (
            skip_nonce["ok"] is False
            and skip_nonce["error"] == "nonce_required"
            and skip_nonce["final_status"] == 409
            and skip_nonce["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_nonce"] = live.get("nonce") == DEFAULT_NONCE_HEX and int(live.get("port") or 0) > 0
        checks["token_nonce_allocate_success_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_allocate["ok"] is False
            and skip_success["ok"] is False
            and skip_replay["ok"] is False
            and skip_nonce["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="turn-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != TURN_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_turn"] = (
        live_goal == TURN_ACTUATION_GOAL
        and TURN_ACTUATION_ID in live_done
        and live_source == "genesis_bind_turn"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_turn_actuation_capability()
    return {
        "ok": ok,
        "action": "turn_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": TURN_ACTUATION_GOAL,
        "done_when": TURN_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
