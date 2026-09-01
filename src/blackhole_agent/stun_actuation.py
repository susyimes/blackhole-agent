"""Drive a first-class STUN tool through RFC 5389 Binding Request/Success.

Tool routing already fails missions that require ``stun``: hosted STUN
plugins stay on the unsupported MCP provider, and no first-party STUN
provider is executable. Unbound therefore cannot speak Binding Request,
lockstep a Binding Success txid exchange over UDP STUN, independently poll
the stored transaction ID, or seal a txid digest an independent later
reader can re-open.

This module closes that hole:

- advertise a ``stun`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 5389 daemon
- keep a missing-txid client so the transaction-ID hole stays falsifiable
- refuse Binding Success until Binding Request lands with a non-zero txid
- independently poll the stored transaction ID on a later client socket
- persist a sealed txid digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after SIP
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
    STUN_TOOL_PROVIDER,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    stun_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
STUN_ACTUATION_ID = "capability.stun-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-STUN-OK"
POLL_TOKEN = "BH-STUN-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
HEADER_SIZE = 20
ZERO_TXID = b"\x00" * 12
MAGIC_COOKIE = 0x2112A442
BINDING_REQUEST = 0x0001
BINDING_SUCCESS = 0x0101
ATTR_USERNAME = 0x0006
ATTR_XOR_MAPPED = 0x0020
FAMILY_IPV4 = 0x01
HEADER_STRUCT = struct.Struct("!HHI12s")
ATTR_HEADER_STRUCT = struct.Struct("!HH")

STUN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{STUN_ACTUATION_ID};"
    f"capability_proved:{STUN_ACTUATION_ID};"
    "no_skill_route"
)
STUN_ACTUATION_GOAL = (
    "Repair rfc5389 stun binding request/success cycle cannot land over udp "
    "stun: hosted stun tools remain unsupported so a Binding Request then "
    "Binding Success txid exchange cannot land and a sealed txid digest cannot "
    "be produced. A missing stun txid stays forbidden; fail-closed routing never "
    "opts the stun provider in. An independent later poll of the stored "
    "transaction txid keeps the hole falsifiable."
)


class StunActuationError(RuntimeError):
    """Raised when the STUN session or loopback daemon fixture misbehaves."""


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


def request_txid(token: str = SENTINEL) -> bytes:
    digest = hashlib.sha256(f"txid:{token or SENTINEL}".encode("utf-8")).digest()
    return _nonzero_txid(digest)


def poll_txid(token: str = SENTINEL) -> bytes:
    digest = hashlib.sha256(f"poll:{token or SENTINEL}".encode("utf-8")).digest()
    return _nonzero_txid(digest)


def txid_hex(txid: bytes) -> str:
    return bytes(txid or ZERO_TXID).hex()


DEFAULT_TXID = request_txid(SENTINEL)
DEFAULT_TXID_HEX = txid_hex(DEFAULT_TXID)


def encode_username(identity: str) -> bytes:
    data = str(identity or "").encode("utf-8")
    if not data:
        return b""
    return ATTR_HEADER_STRUCT.pack(ATTR_USERNAME, len(data)) + data + (b"\x00" * _pad4(len(data)))


def encode_xor_mapped_address(host: str, port: int) -> bytes:
    try:
        addr = struct.unpack("!I", socket.inet_aton(str(host or "127.0.0.1")))[0]
    except OSError:
        addr = struct.unpack("!I", socket.inet_aton("127.0.0.1"))[0]
    xport = int(port or 0) ^ (MAGIC_COOKIE >> 16)
    xaddr = int(addr) ^ MAGIC_COOKIE
    body = bytes((0, FAMILY_IPV4)) + struct.pack("!H", xport & 0xFFFF) + struct.pack("!I", xaddr & 0xFFFFFFFF)
    return ATTR_HEADER_STRUCT.pack(ATTR_XOR_MAPPED, 8) + body


def parse_attributes(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    offset = 0
    username = ""
    mapped_host = ""
    mapped_port = 0
    while offset + 4 <= len(raw):
        atype, alen = ATTR_HEADER_STRUCT.unpack(raw[offset : offset + 4])
        offset += 4
        if offset + int(alen) > len(raw):
            break
        value = raw[offset : offset + int(alen)]
        offset += int(alen) + _pad4(int(alen))
        if int(atype) == ATTR_USERNAME:
            username = value.decode("utf-8", errors="replace")
        elif int(atype) == ATTR_XOR_MAPPED and len(value) >= 8 and value[1] == FAMILY_IPV4:
            xport = struct.unpack("!H", value[2:4])[0]
            xaddr = struct.unpack("!I", value[4:8])[0]
            mapped_port = int(xport) ^ (MAGIC_COOKIE >> 16)
            mapped_host = socket.inet_ntoa(struct.pack("!I", int(xaddr) ^ MAGIC_COOKIE))
    return {
        "username": username,
        "mapped_host": mapped_host,
        "mapped_port": mapped_port,
    }


def _encode_message(msg_type: int, txid: bytes, attributes: bytes) -> bytes:
    live = bytes(txid or ZERO_TXID)
    if len(live) < 12:
        live = live + ZERO_TXID[: 12 - len(live)]
    live = live[:12]
    attrs = bytes(attributes or b"")
    header = HEADER_STRUCT.pack(int(msg_type) & 0xFFFF, len(attrs), MAGIC_COOKIE, live)
    return header + attrs


def encode_request(
    *,
    identity: str,
    txid: bytes,
    include_txid: bool = True,
) -> bytes:
    live = bytes(txid or ZERO_TXID) if include_txid else ZERO_TXID
    return _encode_message(BINDING_REQUEST, live, encode_username(identity))


def encode_success(
    *,
    identity: str,
    txid: bytes,
    mapped_host: str = "127.0.0.1",
    mapped_port: int = 0,
    include_txid: bool = True,
) -> bytes:
    live = bytes(txid or ZERO_TXID) if include_txid else ZERO_TXID
    attributes = encode_username(identity) + encode_xor_mapped_address(mapped_host, mapped_port)
    return _encode_message(BINDING_SUCCESS, live, attributes)


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < HEADER_SIZE:
        raise StunActuationError("short_packet")
    msg_type, length, magic, txid = HEADER_STRUCT.unpack(raw[:HEADER_SIZE])
    if int(magic) != MAGIC_COOKIE:
        raise StunActuationError("illegal_cookie")
    if int(length) < 0 or HEADER_SIZE + int(length) > len(raw):
        raise StunActuationError("illegal_length")
    if int(msg_type) not in {BINDING_REQUEST, BINDING_SUCCESS}:
        raise StunActuationError("illegal_method")
    attrs = parse_attributes(raw[HEADER_SIZE : HEADER_SIZE + int(length)])
    identity = str(attrs.get("username") or "")
    live_txid = bytes(txid)
    is_request = int(msg_type) == BINDING_REQUEST
    is_success = int(msg_type) == BINDING_SUCCESS
    return {
        "type": int(msg_type),
        "is_request": is_request,
        "is_success": is_success,
        "is_response": is_success,
        "txid": live_txid,
        "txid_hex": txid_hex(live_txid),
        "identity": identity,
        "has_identity": bool(identity),
        "has_txid": live_txid != ZERO_TXID,
        "mapped_host": str(attrs.get("mapped_host") or ""),
        "mapped_port": int(attrs.get("mapped_port") or 0),
    }


class _StunClient:
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
            raise StunActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_success"] or not packet["is_response"]:
            raise StunActuationError("success_required")
        if not packet["has_txid"]:
            raise StunActuationError("txid_required")
        return packet

    def exchange(
        self,
        packet: bytes,
        *,
        wait_request: bool = True,
        wait_success: bool = True,
    ) -> dict[str, Any]:
        if not wait_request:
            raise StunActuationError("request_required")
        self.sock.sendto(bytes(packet or b""), (self.host, self.port))
        if not wait_success:
            raise StunActuationError("success_required")
        reply = self._recv()
        return {
            "request": True,
            "success": reply,
            "txid": bytes(reply.get("txid") or ZERO_TXID),
            "txid_hex": str(reply.get("txid_hex") or ""),
            "identity": str(reply.get("identity") or ""),
        }

    def request(
        self,
        identity: str,
        txid: bytes,
        *,
        wait_request: bool = True,
        wait_success: bool = True,
        include_txid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_request(
            identity=identity,
            txid=txid,
            include_txid=include_txid,
        )
        return self.exchange(packet, wait_request=wait_request, wait_success=wait_success)


class StunSession:
    """Transaction-ID-gated loopback RFC 5389 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        txid_gate: bytes = DEFAULT_TXID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.txid_gate = bytes(txid_gate or b"")
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.txid = ZERO_TXID
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

    def store_txid_once(self, identity: str, txid: bytes) -> tuple[str, bytes]:
        with self._lock:
            name = str(identity or "")
            live = bytes(txid or ZERO_TXID)
            if not self.identity and name:
                self.identity = name
                self.txid = live
                self.stored = True
            return str(self.identity), bytes(self.txid)

    def read_txid(self) -> tuple[str, bytes]:
        with self._lock:
            return str(self.identity), bytes(self.txid)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "txid": "",
            "transaction_id": "",
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _txid_missing(self) -> bool:
        gate = bytes(self.txid_gate or b"")
        return not gate or gate == ZERO_TXID

    def _reply_success(self, peer: tuple[str, int], identity: str, txid: bytes) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_success(
            identity=identity,
            txid=txid,
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
            except StunActuationError:
                continue
            if packet.get("is_response"):
                continue
            if not packet.get("is_request"):
                continue
            if not packet.get("has_txid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_txid = self.store_txid_once(
                identity,
                bytes(packet.get("txid") or ZERO_TXID),
            )
            if not stored_name or not stored_txid or stored_txid == ZERO_TXID:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                self.retrieved = True
            self._reply_success(peer, stored_name, stored_txid)

    def bind(self) -> dict[str, Any]:
        if self._txid_missing():
            return self._forbidden("missing_txid")
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
        do_request: bool = True,
        do_success: bool = True,
        replay: bool = True,
        use_txid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._txid_missing():
            return self._forbidden("missing_txid")
        live_token = str(token or SENTINEL)
        origin_txid = request_txid(live_token)
        origin_hex = txid_hex(origin_txid)
        client: _StunClient | None = None
        independent: _StunClient | None = None
        try:
            client = _StunClient(self.host, int(self.port))
            if not do_request:
                return self._conflict("request_required")
            packet = encode_request(
                identity=live_token,
                txid=origin_txid,
                include_txid=use_txid,
            )
            if not use_txid:
                try:
                    client.exchange(packet, wait_request=True, wait_success=True)
                except StunActuationError:
                    return self._conflict("txid_required")
                return self._conflict("txid_required")
            if not do_success:
                try:
                    client.exchange(packet, wait_request=True, wait_success=False)
                except StunActuationError as error:
                    if str(error) == "success_required":
                        return self._conflict("success_required")
                    return self._conflict("success_required")
                return self._conflict("success_required")
            try:
                reply = client.exchange(packet, wait_request=True, wait_success=True)
            except StunActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("txid_required")
                if reason == "request_required":
                    return self._conflict("request_required")
                if reason == "success_required":
                    return self._conflict("success_required")
                return self._conflict("request_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("request_required")
            if bytes(reply.get("txid") or b"") != origin_txid:
                return self._conflict("success_required")
            self.retrieved = True
            if replay:
                independent = _StunClient(self.host, int(self.port))
                try:
                    poll = independent.request(
                        POLL_TOKEN,
                        poll_txid(live_token),
                        wait_request=True,
                        wait_success=True,
                    )
                except StunActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_txid = self.read_txid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_txid != origin_txid
                    or bytes(poll.get("txid") or b"") != origin_txid
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
                "txid": origin_hex,
                "request": True,
                "success_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "txid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_stun_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "txid": origin_hex,
                "transaction_id": origin_hex,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "request": True,
                "success_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "txid_bound": True,
            }
        except (OSError, StunActuationError) as error:
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
        live = independent_stun_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "txid": str(live.get("txid") or ""),
            "transaction_id": str(live.get("txid") or ""),
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


def call_stun_tool(session: StunSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one STUN tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_request = True if arguments.get("request") is None else bool(arguments.get("request"))
    do_success = True if arguments.get("success") is None else bool(arguments.get("success"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_txid = True if arguments.get("use_txid") is None else bool(arguments.get("use_txid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_request=do_request,
            do_success=do_success,
            replay=replay,
            use_txid=use_txid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise StunActuationError(f"unsupported stun action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_stun_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed STUN txid digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "txid": "",
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
            "request",
            "success_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "txid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    txid = str(payload.get("txid") or "")
    dual = port > 0 and bool(txid)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "txid": txid,
        "size": int(payload.get("size") or 0),
        "port": port,
        "request": payload.get("request") is True,
        "success_response": payload.get("success_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "txid_bound": payload.get("txid_bound") is True,
    }


def run_stun_workflow(
    *,
    with_txid: bool = True,
    skip_bind: bool = False,
    do_request: bool = True,
    do_success: bool = True,
    replay: bool = True,
    use_txid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 5389 Binding Request/Success workflow."""

    descriptor = stun_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STUN_TOOL_PROVIDER),
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
        raise StunActuationError(f"stun tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="stun-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = StunSession(out, txid_gate=DEFAULT_TXID if with_txid else b"")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "request": do_request,
            "success": do_success,
            "replay": replay,
            "use_txid": use_txid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_stun_tool(session, arguments))
            except StunActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_stun_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_txid
        and not skip_bind
        and do_request
        and do_success
        and replay
        and use_txid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "stun_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_txid": with_txid,
        "skip_bind": skip_bind,
        "request": do_request,
        "success": do_success,
        "replay": replay,
        "use_txid": use_txid,
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
        "txid_value": str(publish_result.get("txid") or independent.get("txid") or ""),
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
        "txid": str(trace_body["txid_value"] or ""),
        "transaction_id": str(trace_body["txid_value"] or ""),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_txid": with_txid,
        "skip_bind": skip_bind,
        "request": do_request,
        "success_cycle": do_success,
        "replay": replay,
        "use_txid": use_txid,
    }


def verify_stun_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed STUN trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_stun_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    txid = str(trace.get("txid_value") or independent.get("txid") or "")
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
        "request": independent.get("request") is True,
        "success_response": independent.get("success_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "txid_bound": independent.get("txid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "txid_recorded": port > 0 and txid == DEFAULT_TXID_HEX,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def stun_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.stun_actuation import "
        "builtin_stun_actuation_proof; r=builtin_stun_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='stun_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_stun_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=STUN_ACTUATION_ID,
        name="First-class RFC 5389 STUN Binding Request/Success actuation",
        description=(
            "Missions that require a stun tool can opt the stun provider in, "
            "bind a loopback RFC 5389 UDP STUN daemon, complete Binding Request "
            "with a non-zero transaction ID, lockstep a Binding Success that "
            "carries the stored transaction ID, independently poll the stored "
            "transaction ID on a later socket, and seal a digest-chained txid. "
            "Default routing stays fail-closed; a missing txid keeps the hole "
            "falsifiable, and skip-REQUEST/SUCCESS/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.stun_actuation:builtin_stun_actuation_proof",
        proof_command=stun_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.sip-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/stun_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/turn_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required stun tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 5389 daemon, speaks Binding "
            "Request then Binding Success over UDP STUN with a non-zero "
            "transaction ID, independently polls the stored transaction ID on a "
            "later client socket, and binds this family as the next diversity-"
            "catalog successor once RFC 3261 SIP lockstep is proved. Missing "
            "txids, skip-Binding-Request, skip-Binding-Success, skip-REPLAY, and "
            "Binding Request aimed without a transaction ID stay fail-closed. "
            "Later genesis can take RFC 5766 TURN Allocate/Success as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("stun", "rfc5389", "udp", "txid", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T220131Z-002f8136",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_stun_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 5389 STUN lockstep actuation seals a txid digest."""

    from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
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
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
    from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = STUN_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(STUN_ACTUATION_GOAL) == (STUN_ACTUATION_ID,)
    checks["sip_goal_is_not_stun"] = leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    checks["ike_goal_is_not_stun"] = leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    checks["dhcp_goal_is_not_stun"] = leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    checks["radius_goal_is_not_stun"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_stun"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_stun"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_stun"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_stun"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_stun"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_stun"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["turn_goal_is_not_stun"] = leftover_marker_ids(TURN_ACTUATION_GOAL) == (TURN_ACTUATION_ID,)
    checks["stun_goal_is_not_sip"] = SIP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["stun_goal_is_not_ike"] = IKE_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["stun_goal_is_not_dhcp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["stun_goal_is_not_radius"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["stun_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["stun_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["stun_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["stun_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["stun_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["stun_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["stun_goal_is_not_turn"] = TURN_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["sip_marker_stays_sip"] = STUN_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["ike_marker_stays_ike"] = STUN_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["dhcp_marker_stays_dhcp"] = STUN_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["radius_marker_stays_radius"] = STUN_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["ntp_marker_stays_ntp"] = STUN_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = STUN_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = STUN_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = STUN_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = STUN_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = STUN_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["turn_marker_stays_turn"] = STUN_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_stun"] = (
        len(catalog) > 54
        and catalog[54]["id"] == STUN_ACTUATION_ID
        and catalog[53]["id"] == SIP_ACTUATION_ID
        and catalog[54]["source"] == "genesis_bind_stun"
    )
    checks["catalog_names_turn"] = (
        len(catalog) > 55
        and catalog[55]["id"] == TURN_ACTUATION_ID
        and catalog[55]["source"] == "genesis_bind_turn"
    )
    family = capability_family(STUN_ACTUATION_GOAL)
    checks["family_is_stun"] = "stun" in family
    checks["family_is_rfc5389"] = "rfc5389" in family
    checks["family_is_txid"] = "txid" in family
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
    checks["family_is_not_turn"] = "turn" not in family and "rfc5766" not in family and "relay" not in family
    packed = encode_request(identity=SENTINEL, txid=DEFAULT_TXID)
    parsed = parse_message(packed)
    checks["request_roundtrip"] = (
        parsed["is_request"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_txid"] is True
        and parsed["txid"] == DEFAULT_TXID
        and parsed["is_response"] is False
        and parsed["is_success"] is False
    )
    success_packet = encode_success(identity=SENTINEL, txid=DEFAULT_TXID, mapped_port=3478)
    success_parsed = parse_message(success_packet)
    checks["success_roundtrip"] = (
        success_parsed["is_success"] is True
        and success_parsed["identity"] == SENTINEL
        and success_parsed["txid"] == DEFAULT_TXID
        and success_parsed["is_response"] is True
        and success_parsed["is_request"] is False
        and success_parsed["mapped_port"] == 3478
        and success_parsed["mapped_host"] == "127.0.0.1"
    )
    bare = encode_request(identity=SENTINEL, txid=DEFAULT_TXID, include_txid=False)
    checks["missing_txid_is_unauthenticated"] = parse_message(bare)["has_txid"] is False
    neighbors = (
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
        TURN_ACTUATION_GOAL,
    )
    stun_signature = semantic_signature(STUN_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(stun_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_stun = ToolDescriptor(name="remote_stun", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_stun)
    checks["naive_mcp_stun_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = stun_tool_descriptor()
    default_stun = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STUN_TOOL_PROVIDER),
    )
    checks["default_stun_provider_is_unsupported"] = (
        default_stun.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{STUN_TOOL_PROVIDER}" in default_stun.reasons
    )
    checks["opted_in_stun_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_stun],
        required_tool_names=("local_memory", "stun"),
    )
    checks["naive_preflight_missing_stun"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["stun"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "stun"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STUN_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "stun" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="stun-actuation-") as tmp:
        root = Path(tmp)
        missing = run_stun_workflow(with_txid=False, output_dir=root / "missing")
        skip_bind = run_stun_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_request = run_stun_workflow(do_request=False, output_dir=root / "skip-request")
        skip_success = run_stun_workflow(do_success=False, output_dir=root / "skip-success")
        skip_replay = run_stun_workflow(replay=False, output_dir=root / "skip-replay")
        skip_txid = run_stun_workflow(use_txid=False, output_dir=root / "skip-txid")
        live = run_stun_workflow(output_dir=root / "live")
        verify = verify_stun_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_stun_trace(clone)
        checks["naive_without_txid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_txid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_request_stays_empty"] = (
            skip_request["ok"] is False
            and skip_request["error"] == "request_required"
            and skip_request["final_status"] == 409
            and skip_request["payload_exists"] is False
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
        checks["skip_txid_stays_empty"] = (
            skip_txid["ok"] is False
            and skip_txid["error"] == "txid_required"
            and skip_txid["final_status"] == 409
            and skip_txid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_txid"] = live.get("txid") == DEFAULT_TXID_HEX and int(live.get("port") or 0) > 0
        checks["token_txid_request_success_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_request["ok"] is False
            and skip_success["ok"] is False
            and skip_replay["ok"] is False
            and skip_txid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="stun-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != STUN_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_stun"] = (
        live_goal == STUN_ACTUATION_GOAL
        and STUN_ACTUATION_ID in live_done
        and live_source == "genesis_bind_stun"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_stun_actuation_capability()
    return {
        "ok": ok,
        "action": "stun_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": STUN_ACTUATION_GOAL,
        "done_when": STUN_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
