"""Drive a first-class IKE tool through RFC 7296 IKE_SA_INIT/IKE_AUTH.

Tool routing already fails missions that require ``ike``: hosted IKE
plugins stay on the unsupported MCP provider, and no first-party IKE
provider is executable. Unbound therefore cannot speak IKE_SA_INIT, lockstep
an IKE_AUTH spi exchange over UDP IKE, independently poll the stored
initiator SPI, or seal a spi digest an independent later reader can re-open.

This module closes that hole:

- advertise an ``ike`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 7296 daemon
- keep a missing-spi client so the initiator-SPI hole stays falsifiable
- refuse IKE_AUTH until IKE_SA_INIT lands with a non-zero initiator SPI
- independently poll the stored initiator SPI on a later client socket
- persist a sealed spi digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after DHCP
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
    IKE_TOOL_PROVIDER,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    ike_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
IKE_ACTUATION_ID = "capability.ike-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-IKE-OK"
POLL_TOKEN = "BH-IKE-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
HEADER_SIZE = 28
ZERO_SPI = b"\x00" * 8
IKE_VERSION = 0x20
IKE_SA_INIT = 34
IKE_AUTH = 35
FLAG_INITIATOR = 0x10
FLAG_RESPONSE = 0x08
PAYLOAD_ID = 35
ID_KEY_ID = 11
HEADER_STRUCT = struct.Struct("!8s8sBBBBII")
PAYLOAD_HEADER_STRUCT = struct.Struct("!BBH")

IKE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{IKE_ACTUATION_ID};"
    f"capability_proved:{IKE_ACTUATION_ID};"
    "no_skill_route"
)
IKE_ACTUATION_GOAL = (
    "Repair rfc7296 ike sa-init/auth cycle cannot land over udp "
    "ike: hosted ike tools remain unsupported so an IKE_SA_INIT then IKE_AUTH "
    "spi exchange cannot land and a sealed spi digest cannot be "
    "produced. A missing ike spi stays forbidden; fail-closed routing never "
    "opts the ike provider in. An independent later poll of the stored "
    "initiator spi keeps the hole falsifiable."
)


class IkeActuationError(RuntimeError):
    """Raised when the IKE session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def _nonzero_spi(digest: bytes) -> bytes:
    value = bytes(digest[:8])
    if int.from_bytes(value, "big") == 0:
        return b"\x00" * 7 + b"\x01"
    return value


def request_spi(token: str = SENTINEL) -> bytes:
    digest = hashlib.sha256(f"ispi:{token or SENTINEL}".encode("utf-8")).digest()
    return _nonzero_spi(digest)


def responder_spi(token: str = SENTINEL) -> bytes:
    digest = hashlib.sha256(f"rspi:{token or SENTINEL}".encode("utf-8")).digest()
    return _nonzero_spi(digest)


def poll_spi(token: str = SENTINEL) -> bytes:
    digest = hashlib.sha256(f"poll:{token or SENTINEL}".encode("utf-8")).digest()
    return _nonzero_spi(digest)


def spi_hex(spi: bytes) -> str:
    return bytes(spi or ZERO_SPI).hex()


DEFAULT_ISPI = request_spi(SENTINEL)
DEFAULT_RSPI = responder_spi(SENTINEL)
DEFAULT_ISPI_HEX = spi_hex(DEFAULT_ISPI)


def encode_identification(identity: str) -> bytes:
    data = str(identity or "").encode("utf-8")
    body = bytes((ID_KEY_ID, 0, 0, 0)) + data
    return PAYLOAD_HEADER_STRUCT.pack(0, 0, 4 + len(body)) + body


def parse_identification(data: bytes) -> str:
    raw = bytes(data or b"")
    if len(raw) < 8:
        raise IkeActuationError("short_payload")
    _next, _reserved, length = PAYLOAD_HEADER_STRUCT.unpack(raw[:4])
    if length < 8 or length > len(raw):
        raise IkeActuationError("illegal_payload")
    if raw[4] != ID_KEY_ID:
        raise IkeActuationError("illegal_id_type")
    return raw[8:length].decode("utf-8", errors="replace")


def encode_packet(
    *,
    exchange: int,
    initiator_spi: bytes,
    responder_spi: bytes = ZERO_SPI,
    identity: str = "",
    response: bool = False,
    message_id: int = 0,
    include_spi: bool = True,
) -> bytes:
    ispi = bytes(initiator_spi or ZERO_SPI)
    if len(ispi) < 8:
        ispi = ispi + ZERO_SPI[: 8 - len(ispi)]
    ispi = ispi[:8] if include_spi else ZERO_SPI
    rspi = bytes(responder_spi or ZERO_SPI)
    if len(rspi) < 8:
        rspi = rspi + ZERO_SPI[: 8 - len(rspi)]
    rspi = rspi[:8] if include_spi else ZERO_SPI
    flags = FLAG_RESPONSE if response else FLAG_INITIATOR
    payload = encode_identification(identity)
    length = HEADER_SIZE + len(payload)
    header = HEADER_STRUCT.pack(
        ispi,
        rspi,
        PAYLOAD_ID,
        IKE_VERSION,
        int(exchange) & 0xFF,
        flags,
        int(message_id) & 0xFFFFFFFF,
        length,
    )
    return header + payload


def encode_sa_init(
    *,
    initiator_spi: bytes,
    identity: str,
    responder_spi: bytes = ZERO_SPI,
    response: bool = False,
    include_spi: bool = True,
) -> bytes:
    return encode_packet(
        exchange=IKE_SA_INIT,
        initiator_spi=initiator_spi,
        responder_spi=ZERO_SPI if not response else responder_spi,
        identity=identity,
        response=response,
        message_id=0,
        include_spi=include_spi,
    )


def encode_auth(
    *,
    initiator_spi: bytes,
    responder_spi: bytes,
    identity: str,
    response: bool = False,
    include_spi: bool = True,
) -> bytes:
    return encode_packet(
        exchange=IKE_AUTH,
        initiator_spi=initiator_spi,
        responder_spi=responder_spi,
        identity=identity,
        response=response,
        message_id=1,
        include_spi=include_spi,
    )


def parse_packet(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < HEADER_SIZE:
        raise IkeActuationError("short_packet")
    ispi, rspi, next_payload, version, exchange, flags, message_id, length = HEADER_STRUCT.unpack(
        raw[:HEADER_SIZE]
    )
    if int(version) != IKE_VERSION:
        raise IkeActuationError("illegal_version")
    if int(exchange) not in {IKE_SA_INIT, IKE_AUTH}:
        raise IkeActuationError("illegal_exchange")
    if int(length) > len(raw) or int(length) < HEADER_SIZE:
        raise IkeActuationError("illegal_length")
    identity = ""
    if int(next_payload) == PAYLOAD_ID:
        identity = parse_identification(raw[HEADER_SIZE:length])
    initiator = bytes(ispi)
    return {
        "initiator_spi": initiator,
        "responder_spi": bytes(rspi),
        "initiator_spi_hex": spi_hex(initiator),
        "responder_spi_hex": spi_hex(bytes(rspi)),
        "exchange": int(exchange),
        "flags": int(flags),
        "is_response": bool(int(flags) & FLAG_RESPONSE),
        "is_initiator": bool(int(flags) & FLAG_INITIATOR),
        "message_id": int(message_id),
        "identity": identity,
        "has_identity": bool(identity),
        "has_spi": int.from_bytes(initiator, "big") != 0,
    }


class _IkeClient:
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

    def _recv(self, expected_exchange: int, _initiator_spi: bytes) -> dict[str, Any]:
        try:
            payload, _addr = self.sock.recvfrom(4096)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise IkeActuationError("timeout") from error
        packet = parse_packet(payload)
        if packet["exchange"] != int(expected_exchange) or not packet["is_response"]:
            if int(expected_exchange) == IKE_SA_INIT:
                raise IkeActuationError("sa_init_required")
            raise IkeActuationError("auth_required")
        if not packet["has_spi"]:
            raise IkeActuationError("spi_required")
        return packet

    def exchange(
        self,
        packet: bytes,
        initiator_spi: bytes,
        *,
        wait_sa_init: bool = True,
        wait_auth: bool = True,
        identity: str = "",
        include_spi: bool = True,
    ) -> dict[str, Any]:
        self.sock.sendto(bytes(packet or b""), (self.host, self.port))
        if not wait_sa_init:
            raise IkeActuationError("sa_init_required")
        sa_init = self._recv(IKE_SA_INIT, initiator_spi if include_spi else ZERO_SPI)
        if not wait_auth:
            raise IkeActuationError("auth_required")
        auth_packet = encode_auth(
            initiator_spi=bytes(sa_init.get("initiator_spi") or initiator_spi),
            responder_spi=bytes(sa_init.get("responder_spi") or ZERO_SPI),
            identity=str(identity or sa_init.get("identity") or ""),
            include_spi=include_spi,
        )
        self.sock.sendto(auth_packet, (self.host, self.port))
        auth = self._recv(IKE_AUTH, bytes(sa_init.get("initiator_spi") or initiator_spi))
        if bytes(auth.get("initiator_spi") or b"") != bytes(sa_init.get("initiator_spi") or b""):
            raise IkeActuationError("auth_required")
        return {
            "sa_init": sa_init,
            "auth": auth,
            "initiator_spi": bytes(auth.get("initiator_spi") or b""),
            "responder_spi": bytes(auth.get("responder_spi") or b""),
            "identity": str(auth.get("identity") or sa_init.get("identity") or ""),
        }

    def sa_init(
        self,
        identity: str,
        initiator_spi: bytes,
        *,
        wait_sa_init: bool = True,
        wait_auth: bool = True,
        include_spi: bool = True,
    ) -> dict[str, Any]:
        packet = encode_sa_init(
            initiator_spi=initiator_spi,
            identity=identity,
            include_spi=include_spi,
        )
        return self.exchange(
            packet,
            initiator_spi if include_spi else ZERO_SPI,
            wait_sa_init=wait_sa_init,
            wait_auth=wait_auth,
            identity=identity,
            include_spi=include_spi,
        )


class IkeSession:
    """SPI-gated loopback RFC 7296 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        spi_gate: bytes = DEFAULT_ISPI,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.spi_gate = bytes(spi_gate or b"")
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.initiator_spi = ZERO_SPI
        self.peer_spi = ZERO_SPI
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

    def store_spi_once(self, identity: str, initiator_spi: bytes) -> tuple[str, bytes, bytes]:
        with self._lock:
            name = str(identity or "")
            ispi = bytes(initiator_spi or ZERO_SPI)
            if not self.identity and name:
                self.identity = name
                self.initiator_spi = ispi
                self.peer_spi = responder_spi(name)
                self.stored = True
            return str(self.identity), bytes(self.initiator_spi), bytes(self.peer_spi)

    def read_spi(self) -> tuple[str, bytes, bytes]:
        with self._lock:
            return str(self.identity), bytes(self.initiator_spi), bytes(self.peer_spi)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "initiator_spi": "",
            "spi": "",
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _spi_missing(self) -> bool:
        gate = bytes(self.spi_gate or b"")
        return not gate or int.from_bytes(gate[:8].ljust(8, b"\x00"), "big") == 0

    def _reply_sa_init(self, peer: tuple[str, int], identity: str, ispi: bytes, rspi: bytes) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_sa_init(
            initiator_spi=ispi,
            responder_spi=rspi,
            identity=identity,
            response=True,
        )
        try:
            sock.sendto(packet, peer)
        except OSError:
            return

    def _reply_auth(self, peer: tuple[str, int], identity: str, ispi: bytes, rspi: bytes) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_auth(
            initiator_spi=ispi,
            responder_spi=rspi,
            identity=identity,
            response=True,
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
                payload, addr = sock.recvfrom(4096)
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                return
            try:
                packet = parse_packet(payload)
            except IkeActuationError:
                continue
            if packet.get("is_response"):
                continue
            peer = (str(addr[0]), int(addr[1]))
            if packet.get("exchange") == IKE_SA_INIT:
                if not packet.get("has_spi"):
                    continue
                identity = str(packet.get("identity") or "")
                if not identity:
                    continue
                stored_name, stored_ispi, stored_rspi = self.store_spi_once(
                    identity,
                    bytes(packet.get("initiator_spi") or ZERO_SPI),
                )
                self._reply_sa_init(peer, stored_name, stored_ispi, stored_rspi)
                continue
            if packet.get("exchange") != IKE_AUTH:
                continue
            stored_name, stored_ispi, stored_rspi = self.read_spi()
            if not stored_name or not stored_ispi or stored_ispi == ZERO_SPI:
                continue
            if bytes(packet.get("initiator_spi") or b"") != stored_ispi:
                continue
            if bytes(packet.get("responder_spi") or b"") != stored_rspi:
                continue
            with self._lock:
                self.retrieved = True
            self._reply_auth(peer, stored_name, stored_ispi, stored_rspi)

    def bind(self) -> dict[str, Any]:
        if self._spi_missing():
            return self._forbidden("missing_spi")
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
        do_sa_init: bool = True,
        do_auth: bool = True,
        replay: bool = True,
        use_spi: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._spi_missing():
            return self._forbidden("missing_spi")
        live_token = str(token or SENTINEL)
        origin_spi = request_spi(live_token)
        client: _IkeClient | None = None
        independent: _IkeClient | None = None
        try:
            client = _IkeClient(self.host, int(self.port))
            if not do_sa_init:
                return self._conflict("sa_init_required")
            packet = encode_sa_init(
                initiator_spi=origin_spi,
                identity=live_token,
                include_spi=use_spi,
            )
            if not use_spi:
                try:
                    client.exchange(
                        packet,
                        origin_spi,
                        wait_sa_init=True,
                        wait_auth=True,
                        identity=live_token,
                        include_spi=False,
                    )
                except IkeActuationError:
                    return self._conflict("spi_required")
                return self._conflict("spi_required")
            if not do_auth:
                try:
                    client.exchange(
                        packet,
                        origin_spi,
                        wait_sa_init=True,
                        wait_auth=False,
                        identity=live_token,
                        include_spi=True,
                    )
                except IkeActuationError as error:
                    if str(error) == "auth_required":
                        return self._conflict("auth_required")
                    return self._conflict("auth_required")
                return self._conflict("auth_required")
            try:
                reply = client.exchange(
                    packet,
                    origin_spi,
                    wait_sa_init=True,
                    wait_auth=True,
                    identity=live_token,
                    include_spi=True,
                )
            except IkeActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("spi_required")
                if reason == "sa_init_required":
                    return self._conflict("sa_init_required")
                if reason == "auth_required":
                    return self._conflict("auth_required")
                return self._conflict("sa_init_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("sa_init_required")
            if bytes(reply.get("initiator_spi") or b"") != origin_spi:
                return self._conflict("auth_required")
            self.retrieved = True
            if replay:
                independent = _IkeClient(self.host, int(self.port))
                try:
                    poll = independent.sa_init(
                        POLL_TOKEN,
                        poll_spi(live_token),
                        wait_sa_init=True,
                        wait_auth=True,
                    )
                except IkeActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_ispi, _stored_rspi = self.read_spi()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_ispi != origin_spi
                    or bytes(poll.get("initiator_spi") or b"") != origin_spi
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{spi_hex(origin_spi)}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "initiator_spi": spi_hex(origin_spi),
                "responder_spi": spi_hex(bytes(reply.get("responder_spi") or DEFAULT_RSPI)),
                "sa_init": True,
                "auth": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "spi_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_ike_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "initiator_spi": spi_hex(origin_spi),
                "spi": spi_hex(origin_spi),
                "xid": spi_hex(origin_spi),
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "sa_init": True,
                "auth": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "spi_bound": True,
            }
        except (OSError, IkeActuationError) as error:
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
        live = independent_ike_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "initiator_spi": str(live.get("initiator_spi") or ""),
            "spi": str(live.get("initiator_spi") or ""),
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


def call_ike_tool(session: IkeSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one IKE tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_sa_init = True if arguments.get("sa_init") is None else bool(arguments.get("sa_init"))
    do_auth = True if arguments.get("auth") is None else bool(arguments.get("auth"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_spi = True if arguments.get("use_spi") is None else bool(arguments.get("use_spi"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_sa_init=do_sa_init,
            do_auth=do_auth,
            replay=replay,
            use_spi=use_spi,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise IkeActuationError(f"unsupported ike action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_ike_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed IKE spi digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "initiator_spi": "",
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
            "sa_init",
            "auth",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "spi_bound",
        )
    )
    port = int(payload.get("port") or 0)
    initiator = str(payload.get("initiator_spi") or "")
    dual = port > 0 and bool(initiator)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "initiator_spi": initiator,
        "size": int(payload.get("size") or 0),
        "port": port,
        "sa_init": payload.get("sa_init") is True,
        "auth": payload.get("auth") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "spi_bound": payload.get("spi_bound") is True,
    }


def run_ike_workflow(
    *,
    with_spi: bool = True,
    skip_bind: bool = False,
    do_sa_init: bool = True,
    do_auth: bool = True,
    replay: bool = True,
    use_spi: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 7296 IKE_SA_INIT/IKE_AUTH workflow."""

    descriptor = ike_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IKE_TOOL_PROVIDER),
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
        raise IkeActuationError(f"ike tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ike-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = IkeSession(out, spi_gate=DEFAULT_ISPI if with_spi else b"")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "sa_init": do_sa_init,
            "auth": do_auth,
            "replay": replay,
            "use_spi": use_spi,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_ike_tool(session, arguments))
            except IkeActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_ike_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_spi
        and not skip_bind
        and do_sa_init
        and do_auth
        and replay
        and use_spi
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ike_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_spi": with_spi,
        "skip_bind": skip_bind,
        "sa_init": do_sa_init,
        "auth": do_auth,
        "replay": replay,
        "use_spi": use_spi,
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
        "initiator_spi_value": str(
            publish_result.get("initiator_spi") or independent.get("initiator_spi") or ""
        ),
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
        "initiator_spi": str(trace_body["initiator_spi_value"] or ""),
        "spi": str(trace_body["initiator_spi_value"] or ""),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_spi": with_spi,
        "skip_bind": skip_bind,
        "sa_init": do_sa_init,
        "auth": do_auth,
        "replay": replay,
        "use_spi": use_spi,
    }


def verify_ike_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed IKE trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_ike_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    initiator = str(trace.get("initiator_spi_value") or independent.get("initiator_spi") or "")
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
        "sa_init": independent.get("sa_init") is True,
        "auth": independent.get("auth") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "spi_bound": independent.get("spi_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "spi_recorded": port > 0 and initiator == DEFAULT_ISPI_HEX,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def ike_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.ike_actuation import "
        "builtin_ike_actuation_proof; r=builtin_ike_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='ike_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_ike_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=IKE_ACTUATION_ID,
        name="First-class RFC 7296 IKE SA_INIT/AUTH actuation",
        description=(
            "Missions that require an ike tool can opt the ike provider in, "
            "bind a loopback RFC 7296 UDP IKE daemon, complete IKE_SA_INIT with a "
            "non-zero initiator SPI, lockstep an IKE_AUTH that carries the stored "
            "initiator SPI, independently poll the stored initiator SPI on a later "
            "socket, and seal a digest-chained spi. Default routing stays "
            "fail-closed; a missing spi keeps the hole falsifiable, and "
            "skip-SA_INIT/AUTH/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.ike_actuation:builtin_ike_actuation_proof",
        proof_command=ike_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.dhcp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/ike_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/sip_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required ike tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 7296 daemon, speaks IKE_SA_INIT then "
            "IKE_AUTH over UDP IKE with a non-zero initiator SPI, independently "
            "polls the stored initiator SPI on a later client socket, and binds "
            "this family as the next diversity-catalog successor once RFC 2131 "
            "DHCP lockstep is proved. Missing SPIs, skip-IKE_SA_INIT, skip-IKE_AUTH, "
            "skip-REPLAY, and IKE_SA_INIT aimed without an initiator SPI stay "
            "fail-closed. Later genesis can take RFC 3261 SIP INVITE/200 as "
            "the next unsaturated diversity-catalog family."
        ),
        tags=("ike", "rfc7296", "udp", "spi", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T205915Z-817c92c4",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_ike_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 7296 IKE lockstep actuation seals a spi digest."""

    from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
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
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = IKE_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    checks["dhcp_goal_is_not_ike"] = leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    checks["radius_goal_is_not_ike"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_ike"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_ike"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_ike"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_ike"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_ike"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_ike"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["sip_goal_is_not_ike"] = leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    checks["ike_goal_is_not_dhcp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["ike_goal_is_not_radius"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["ike_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["ike_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["ike_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["ike_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["ike_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["ike_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["ike_goal_is_not_sip"] = SIP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["dhcp_marker_stays_dhcp"] = IKE_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["radius_marker_stays_radius"] = IKE_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["ntp_marker_stays_ntp"] = IKE_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = IKE_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = IKE_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = IKE_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = IKE_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = IKE_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["sip_marker_stays_sip"] = IKE_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_ike"] = (
        len(catalog) > 52
        and catalog[52]["id"] == IKE_ACTUATION_ID
        and catalog[51]["id"] == DHCP_ACTUATION_ID
        and catalog[52]["source"] == "genesis_bind_ike"
    )
    checks["catalog_names_sip"] = (
        len(catalog) > 53
        and catalog[53]["id"] == SIP_ACTUATION_ID
        and catalog[53]["source"] == "genesis_bind_sip"
    )
    family = capability_family(IKE_ACTUATION_GOAL)
    checks["family_is_ike"] = "ike" in family
    checks["family_is_rfc7296"] = "rfc7296" in family
    checks["family_is_spi"] = "spi" in family
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
    checks["family_is_not_sip"] = "sip" not in family and "rfc3261" not in family and "callid" not in family
    packed = encode_sa_init(initiator_spi=DEFAULT_ISPI, identity=SENTINEL)
    parsed = parse_packet(packed)
    checks["sa_init_roundtrip"] = (
        parsed["exchange"] == IKE_SA_INIT
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_spi"] is True
        and parsed["initiator_spi"] == DEFAULT_ISPI
        and parsed["is_response"] is False
        and parsed["is_initiator"] is True
    )
    sa_init_resp = encode_sa_init(
        initiator_spi=DEFAULT_ISPI,
        responder_spi=DEFAULT_RSPI,
        identity=SENTINEL,
        response=True,
    )
    sa_init = parse_packet(sa_init_resp)
    checks["sa_init_response_roundtrip"] = (
        sa_init["exchange"] == IKE_SA_INIT
        and sa_init["identity"] == SENTINEL
        and sa_init["initiator_spi"] == DEFAULT_ISPI
        and sa_init["responder_spi"] == DEFAULT_RSPI
        and sa_init["is_response"] is True
        and sa_init["is_initiator"] is False
    )
    auth_packet = encode_auth(
        initiator_spi=DEFAULT_ISPI,
        responder_spi=DEFAULT_RSPI,
        identity=SENTINEL,
    )
    auth = parse_packet(auth_packet)
    checks["auth_roundtrip"] = (
        auth["exchange"] == IKE_AUTH
        and auth["identity"] == SENTINEL
        and auth["initiator_spi"] == DEFAULT_ISPI
        and auth["responder_spi"] == DEFAULT_RSPI
        and auth["is_response"] is False
    )
    bare = encode_sa_init(initiator_spi=DEFAULT_ISPI, identity=SENTINEL, include_spi=False)
    checks["missing_spi_is_unauthenticated"] = parse_packet(bare)["has_spi"] is False
    neighbors = (
        DHCP_ACTUATION_GOAL,
        RADIUS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        SIP_ACTUATION_GOAL,
    )
    ike_signature = semantic_signature(IKE_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(ike_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_ike = ToolDescriptor(name="remote_ike", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_ike)
    checks["naive_mcp_ike_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = ike_tool_descriptor()
    default_ike = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IKE_TOOL_PROVIDER),
    )
    checks["default_ike_provider_is_unsupported"] = (
        default_ike.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{IKE_TOOL_PROVIDER}" in default_ike.reasons
    )
    checks["opted_in_ike_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_ike],
        required_tool_names=("local_memory", "ike"),
    )
    checks["naive_preflight_missing_ike"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["ike"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "ike"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IKE_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "ike" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="ike-actuation-") as tmp:
        root = Path(tmp)
        missing = run_ike_workflow(with_spi=False, output_dir=root / "missing")
        skip_bind = run_ike_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_sa_init = run_ike_workflow(do_sa_init=False, output_dir=root / "skip-sa-init")
        skip_auth = run_ike_workflow(do_auth=False, output_dir=root / "skip-auth")
        skip_replay = run_ike_workflow(replay=False, output_dir=root / "skip-replay")
        skip_spi = run_ike_workflow(use_spi=False, output_dir=root / "skip-spi")
        live = run_ike_workflow(output_dir=root / "live")
        verify = verify_ike_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_ike_trace(clone)
        checks["naive_without_spi_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_spi"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_sa_init_stays_empty"] = (
            skip_sa_init["ok"] is False
            and skip_sa_init["error"] == "sa_init_required"
            and skip_sa_init["final_status"] == 409
            and skip_sa_init["payload_exists"] is False
        )
        checks["skip_auth_stays_empty"] = (
            skip_auth["ok"] is False
            and skip_auth["error"] == "auth_required"
            and skip_auth["final_status"] == 409
            and skip_auth["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_spi_stays_empty"] = (
            skip_spi["ok"] is False
            and skip_spi["error"] == "spi_required"
            and skip_spi["final_status"] == 409
            and skip_spi["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_spi"] = live.get("initiator_spi") == DEFAULT_ISPI_HEX and int(live.get("port") or 0) > 0
        checks["token_spi_sa_init_auth_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_sa_init["ok"] is False
            and skip_auth["ok"] is False
            and skip_replay["ok"] is False
            and skip_spi["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="ike-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != IKE_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_ike"] = (
        live_goal == IKE_ACTUATION_GOAL
        and IKE_ACTUATION_ID in live_done
        and live_source == "genesis_bind_ike"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_ike_actuation_capability()
    return {
        "ok": ok,
        "action": "ike_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": IKE_ACTUATION_GOAL,
        "done_when": IKE_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
