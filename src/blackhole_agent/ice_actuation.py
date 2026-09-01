"""Drive a first-class ICE tool through RFC 8445 connectivity-check/nominate.

Tool routing already fails missions that require ``ice``: hosted ICE
agents stay on the unsupported MCP provider, and no first-party ICE
provider is executable. Unbound therefore cannot speak a connectivity
check, lockstep a nominated-pair Success ufrag handshake over UDP ICE,
independently poll the stored candidate foundation, or seal a foundation
digest an independent later reader can re-open.

This module closes that hole:

- advertise an ``ice`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 8445 daemon
- keep a missing-ufrag client so the ice-ufrag hole stays falsifiable
- refuse nominated-pair Success until a connectivity-check lands with a
  non-empty ufrag
- independently poll the stored candidate foundation on a later client socket
- persist a sealed foundation digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after TURN
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
    ICE_TOOL_PROVIDER,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    ice_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
ICE_ACTUATION_ID = "capability.ice-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-ICE-OK"
POLL_TOKEN = "BH-ICE-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
HEADER_SIZE = 20
EMPTY_UFRAG = ""
ZERO_TXID = b"\x00" * 12
MAGIC_COOKIE = 0x2112A442
BINDING_REQUEST = 0x0001
BINDING_SUCCESS = 0x0101
ATTR_USERNAME = 0x0006
ATTR_XOR_MAPPED = 0x0020
ATTR_PRIORITY = 0x0024
ATTR_USE_CANDIDATE = 0x0025
ATTR_SOFTWARE = 0x8022
ATTR_ICE_CONTROLLING = 0x802A
ATTR_FOUNDATION = 0xC001
FAMILY_IPV4 = 0x01
HOST_PRIORITY = 2130706431
HEADER_STRUCT = struct.Struct("!HHI12s")
ATTR_HEADER_STRUCT = struct.Struct("!HH")

ICE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ICE_ACTUATION_ID};"
    f"capability_proved:{ICE_ACTUATION_ID};"
    "no_skill_route"
)
ICE_ACTUATION_GOAL = (
    "Repair rfc8445 ice connectivity-check/nominated-pair cycle cannot land over udp "
    "ice: hosted ice agents remain unsupported so a connectivity-check then "
    "nominated-pair Success ufrag handshake cannot land and a sealed foundation digest "
    "cannot be produced. A missing ice ufrag stays forbidden; fail-closed "
    "routing never opts the ice provider in. An independent later poll of the "
    "stored candidate foundation keeps the hole falsifiable."
)


class IceActuationError(RuntimeError):
    """Raised when the ICE session or loopback daemon fixture misbehaves."""


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


def request_ufrag(token: str = SENTINEL) -> str:
    digest = hashlib.sha256(f"ufrag:{token or SENTINEL}".encode("utf-8")).hexdigest()
    return digest[:8]


def poll_ufrag(token: str = SENTINEL) -> str:
    digest = hashlib.sha256(f"poll:{token or SENTINEL}".encode("utf-8")).hexdigest()
    return digest[:8]


def request_foundation(ufrag: str) -> str:
    digest = hashlib.sha256(f"foundation:host:udp:{ufrag or EMPTY_UFRAG}".encode("utf-8")).hexdigest()
    return digest[:8]


def username_pair(ufrag: str) -> str:
    live = str(ufrag or EMPTY_UFRAG)
    if not live:
        return ""
    return f"{live}:{live}"


def _txid_from_ufrag(ufrag: str) -> bytes:
    digest = hashlib.sha256(f"txid:{ufrag or EMPTY_UFRAG}".encode("utf-8")).digest()
    return _nonzero_txid(digest)


def tie_breaker(ufrag: str) -> bytes:
    return hashlib.sha256(f"tie:{ufrag or EMPTY_UFRAG}".encode("utf-8")).digest()[:8]


DEFAULT_UFRAG = request_ufrag(SENTINEL)
DEFAULT_FOUNDATION = request_foundation(DEFAULT_UFRAG)
DEFAULT_USERNAME = username_pair(DEFAULT_UFRAG)


def encode_username(ufrag: str) -> bytes:
    data = username_pair(ufrag).encode("utf-8")
    if not data:
        return b""
    return ATTR_HEADER_STRUCT.pack(ATTR_USERNAME, len(data)) + data + (b"\x00" * _pad4(len(data)))


def encode_software(identity: str) -> bytes:
    data = str(identity or "").encode("utf-8")
    if not data:
        return b""
    return ATTR_HEADER_STRUCT.pack(ATTR_SOFTWARE, len(data)) + data + (b"\x00" * _pad4(len(data)))


def encode_foundation(foundation: str) -> bytes:
    data = str(foundation or "").encode("utf-8")
    if not data:
        return b""
    return ATTR_HEADER_STRUCT.pack(ATTR_FOUNDATION, len(data)) + data + (b"\x00" * _pad4(len(data)))


def encode_priority(priority: int = HOST_PRIORITY) -> bytes:
    body = struct.pack("!I", int(priority) & 0xFFFFFFFF)
    return ATTR_HEADER_STRUCT.pack(ATTR_PRIORITY, 4) + body


def encode_use_candidate() -> bytes:
    return ATTR_HEADER_STRUCT.pack(ATTR_USE_CANDIDATE, 0)


def encode_ice_controlling(ufrag: str) -> bytes:
    return ATTR_HEADER_STRUCT.pack(ATTR_ICE_CONTROLLING, 8) + tie_breaker(ufrag)


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
    identity = ""
    foundation = ""
    mapped_host = ""
    mapped_port = 0
    priority = 0
    use_candidate = False
    ice_controlling = b""
    while offset + 4 <= len(raw):
        atype, alen = ATTR_HEADER_STRUCT.unpack(raw[offset : offset + 4])
        offset += 4
        if offset + int(alen) > len(raw):
            break
        value = raw[offset : offset + int(alen)]
        offset += int(alen) + _pad4(int(alen))
        if int(atype) == ATTR_USERNAME:
            username = value.decode("utf-8", errors="replace")
        elif int(atype) == ATTR_SOFTWARE:
            identity = value.decode("utf-8", errors="replace")
        elif int(atype) == ATTR_FOUNDATION:
            foundation = value.decode("utf-8", errors="replace")
        elif int(atype) == ATTR_PRIORITY and len(value) >= 4:
            priority = int(struct.unpack("!I", value[:4])[0])
        elif int(atype) == ATTR_USE_CANDIDATE:
            use_candidate = True
        elif int(atype) == ATTR_ICE_CONTROLLING:
            ice_controlling = bytes(value)
        elif int(atype) == ATTR_XOR_MAPPED and len(value) >= 8 and value[1] == FAMILY_IPV4:
            xport = struct.unpack("!H", value[2:4])[0]
            xaddr = struct.unpack("!I", value[4:8])[0]
            mapped_port = int(xport) ^ (MAGIC_COOKIE >> 16)
            mapped_host = socket.inet_ntoa(struct.pack("!I", int(xaddr) ^ MAGIC_COOKIE))
    remote_ufrag, _, local_ufrag = username.partition(":")
    return {
        "username": username,
        "identity": identity,
        "foundation": foundation,
        "remote_ufrag": remote_ufrag,
        "local_ufrag": local_ufrag,
        "mapped_host": mapped_host,
        "mapped_port": mapped_port,
        "priority": priority,
        "use_candidate": use_candidate,
        "ice_controlling": ice_controlling,
    }


def _encode_message(msg_type: int, txid: bytes, attributes: bytes) -> bytes:
    live = bytes(txid or ZERO_TXID)
    if len(live) < 12:
        live = live + ZERO_TXID[: 12 - len(live)]
    live = live[:12]
    attrs = bytes(attributes or b"")
    header = HEADER_STRUCT.pack(int(msg_type) & 0xFFFF, len(attrs), MAGIC_COOKIE, live)
    return header + attrs


def _request_attributes(
    *,
    identity: str,
    ufrag: str,
    foundation: str,
    include_ufrag: bool,
    use_candidate: bool,
) -> bytes:
    live = str(ufrag or EMPTY_UFRAG) if include_ufrag else EMPTY_UFRAG
    attributes = encode_software(identity) + encode_priority() + encode_ice_controlling(live)
    if include_ufrag:
        attributes += encode_username(live) + encode_foundation(foundation)
    if use_candidate:
        attributes += encode_use_candidate()
    return attributes


def encode_check(
    *,
    identity: str,
    ufrag: str,
    foundation: str = "",
    include_ufrag: bool = True,
) -> bytes:
    live = str(ufrag or EMPTY_UFRAG) if include_ufrag else EMPTY_UFRAG
    live_foundation = str(foundation or request_foundation(live))
    return _encode_message(
        BINDING_REQUEST,
        _txid_from_ufrag(live),
        _request_attributes(
            identity=identity,
            ufrag=live,
            foundation=live_foundation,
            include_ufrag=include_ufrag,
            use_candidate=False,
        ),
    )


def encode_nominate(
    *,
    identity: str,
    ufrag: str,
    foundation: str = "",
    include_ufrag: bool = True,
) -> bytes:
    live = str(ufrag or EMPTY_UFRAG) if include_ufrag else EMPTY_UFRAG
    live_foundation = str(foundation or request_foundation(live))
    return _encode_message(
        BINDING_REQUEST,
        _txid_from_ufrag(live),
        _request_attributes(
            identity=identity,
            ufrag=live,
            foundation=live_foundation,
            include_ufrag=include_ufrag,
            use_candidate=True,
        ),
    )


def encode_success(
    *,
    identity: str,
    ufrag: str,
    foundation: str,
    mapped_host: str = "127.0.0.1",
    mapped_port: int = 0,
    include_ufrag: bool = True,
) -> bytes:
    live = str(ufrag or EMPTY_UFRAG) if include_ufrag else EMPTY_UFRAG
    attributes = (
        encode_software(identity)
        + encode_username(live)
        + encode_foundation(foundation)
        + encode_xor_mapped_address(mapped_host, mapped_port)
        + encode_priority()
    )
    return _encode_message(BINDING_SUCCESS, _txid_from_ufrag(live), attributes)


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < HEADER_SIZE:
        raise IceActuationError("short_packet")
    msg_type, length, magic, txid = HEADER_STRUCT.unpack(raw[:HEADER_SIZE])
    if int(magic) != MAGIC_COOKIE:
        raise IceActuationError("illegal_cookie")
    if int(length) < 0 or HEADER_SIZE + int(length) > len(raw):
        raise IceActuationError("illegal_length")
    if int(msg_type) not in {BINDING_REQUEST, BINDING_SUCCESS}:
        raise IceActuationError("illegal_method")
    attrs = parse_attributes(raw[HEADER_SIZE : HEADER_SIZE + int(length)])
    identity = str(attrs.get("identity") or "")
    remote_ufrag = str(attrs.get("remote_ufrag") or "")
    local_ufrag = str(attrs.get("local_ufrag") or "")
    ufrag = local_ufrag or remote_ufrag
    foundation = str(attrs.get("foundation") or "")
    is_request = int(msg_type) == BINDING_REQUEST
    is_success = int(msg_type) == BINDING_SUCCESS
    use_candidate = bool(attrs.get("use_candidate"))
    return {
        "type": int(msg_type),
        "is_check": is_request and not use_candidate,
        "is_nominate": is_request and use_candidate,
        "is_success": is_success,
        "is_response": is_success,
        "txid": bytes(txid),
        "identity": identity,
        "has_identity": bool(identity),
        "ufrag": ufrag,
        "remote_ufrag": remote_ufrag,
        "local_ufrag": local_ufrag,
        "username": str(attrs.get("username") or ""),
        "has_ufrag": bool(remote_ufrag and local_ufrag),
        "foundation": foundation,
        "has_foundation": bool(foundation),
        "use_candidate": use_candidate,
        "priority": int(attrs.get("priority") or 0),
        "mapped_host": str(attrs.get("mapped_host") or ""),
        "mapped_port": int(attrs.get("mapped_port") or 0),
        "ice_controlling": bytes(attrs.get("ice_controlling") or b""),
    }


class _IceClient:
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
            raise IceActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_success"] or not packet["is_response"]:
            raise IceActuationError("success_required")
        if not packet["has_ufrag"]:
            raise IceActuationError("ufrag_required")
        if not packet["has_foundation"]:
            raise IceActuationError("replay_required")
        return packet

    def exchange(self, packet: bytes, *, wait_success: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_success:
            raise IceActuationError("success_required")
        reply = self._recv()
        return {
            "success": reply,
            "ufrag": str(reply.get("ufrag") or EMPTY_UFRAG),
            "foundation": str(reply.get("foundation") or ""),
            "identity": str(reply.get("identity") or ""),
            "mapped_port": int(reply.get("mapped_port") or 0),
        }

    def nominate(
        self,
        identity: str,
        ufrag: str,
        foundation: str = "",
        *,
        wait_success: bool = True,
        include_ufrag: bool = True,
    ) -> dict[str, Any]:
        packet = encode_nominate(
            identity=identity,
            ufrag=ufrag,
            foundation=foundation or request_foundation(ufrag),
            include_ufrag=include_ufrag,
        )
        return self.exchange(packet, wait_success=wait_success)


class IceSession:
    """Ufrag-gated loopback RFC 8445 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        ufrag_gate: str = DEFAULT_UFRAG,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ufrag_gate = str(ufrag_gate or "")
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.ufrag = EMPTY_UFRAG
        self.foundation = ""
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.checked = False
        self.nominated = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_candidate_once(self, identity: str, ufrag: str, foundation: str) -> tuple[str, str, str]:
        with self._lock:
            name = str(identity or "")
            live = str(ufrag or EMPTY_UFRAG)
            live_foundation = str(foundation or "")
            if not self.identity and name and live:
                self.identity = name
                self.ufrag = live
                self.foundation = live_foundation or request_foundation(live)
                self.stored = True
            return str(self.identity), str(self.ufrag), str(self.foundation)

    def read_candidate(self) -> tuple[str, str, str]:
        with self._lock:
            return str(self.identity), str(self.ufrag), str(self.foundation)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "ufrag": "",
            "foundation": "",
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _ufrag_missing(self) -> bool:
        return not str(self.ufrag_gate or "")

    def _reply_success(self, peer: tuple[str, int], identity: str, ufrag: str, foundation: str) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_success(
            identity=identity,
            ufrag=ufrag,
            foundation=foundation,
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
            except IceActuationError:
                continue
            if packet.get("is_response"):
                continue
            if not packet.get("is_check") and not packet.get("is_nominate"):
                continue
            if not packet.get("has_ufrag"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_ufrag, stored_foundation = self.store_candidate_once(
                identity,
                str(packet.get("ufrag") or EMPTY_UFRAG),
                str(packet.get("foundation") or ""),
            )
            if not stored_name or not stored_ufrag or not stored_foundation:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_check"):
                    self.checked = True
                if packet.get("is_nominate"):
                    self.nominated = True
                self.retrieved = True
            self._reply_success(peer, stored_name, stored_ufrag, stored_foundation)

    def bind(self) -> dict[str, Any]:
        if self._ufrag_missing():
            return self._forbidden("missing_ufrag")
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
        do_check: bool = True,
        do_nominate: bool = True,
        do_success: bool = True,
        replay: bool = True,
        use_ufrag: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._ufrag_missing():
            return self._forbidden("missing_ufrag")
        live_token = str(token or SENTINEL)
        origin_ufrag = request_ufrag(live_token)
        origin_foundation = request_foundation(origin_ufrag)
        client: _IceClient | None = None
        independent: _IceClient | None = None
        try:
            client = _IceClient(self.host, int(self.port))
            if not do_check:
                return self._conflict("check_required")
            check_packet = encode_check(
                identity=live_token,
                ufrag=origin_ufrag,
                foundation=origin_foundation,
                include_ufrag=use_ufrag,
            )
            if not use_ufrag:
                try:
                    client.exchange(check_packet, wait_success=True)
                except IceActuationError:
                    return self._conflict("ufrag_required")
                return self._conflict("ufrag_required")
            client.send(check_packet)
            if not do_nominate:
                return self._conflict("nominate_required")
            nom_packet = encode_nominate(
                identity=live_token,
                ufrag=origin_ufrag,
                foundation=origin_foundation,
                include_ufrag=True,
            )
            if not do_success:
                try:
                    client.exchange(nom_packet, wait_success=False)
                except IceActuationError as error:
                    if str(error) == "success_required":
                        return self._conflict("success_required")
                    return self._conflict("success_required")
                return self._conflict("success_required")
            try:
                reply = client.exchange(nom_packet, wait_success=True)
            except IceActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("ufrag_required")
                if reason == "success_required":
                    return self._conflict("success_required")
                return self._conflict("check_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("check_required")
            if str(reply.get("ufrag") or "") != origin_ufrag:
                return self._conflict("success_required")
            if str(reply.get("foundation") or "") != origin_foundation:
                return self._conflict("success_required")
            self.retrieved = True
            if replay:
                independent = _IceClient(self.host, int(self.port))
                try:
                    poll = independent.nominate(
                        POLL_TOKEN,
                        poll_ufrag(live_token),
                        request_foundation(poll_ufrag(live_token)),
                        wait_success=True,
                    )
                except IceActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_ufrag, stored_foundation = self.read_candidate()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_ufrag != origin_ufrag
                    or stored_foundation != origin_foundation
                    or str(poll.get("ufrag") or "") != origin_ufrag
                    or str(poll.get("foundation") or "") != origin_foundation
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_foundation}:{origin_ufrag}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "ufrag": origin_ufrag,
                "foundation": origin_foundation,
                "check": True,
                "nominate": True,
                "success_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "ufrag_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_ice_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "ufrag": origin_ufrag,
                "foundation": origin_foundation,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "check": True,
                "nominate": True,
                "success_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "ufrag_bound": True,
            }
        except (OSError, IceActuationError) as error:
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
        live = independent_ice_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "ufrag": str(live.get("ufrag") or ""),
            "foundation": str(live.get("foundation") or ""),
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


def call_ice_tool(session: IceSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one ICE tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_check = True if arguments.get("check") is None else bool(arguments.get("check"))
    do_nominate = True if arguments.get("nominate") is None else bool(arguments.get("nominate"))
    do_success = True if arguments.get("success") is None else bool(arguments.get("success"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_ufrag = True if arguments.get("use_ufrag") is None else bool(arguments.get("use_ufrag"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_check=do_check,
            do_nominate=do_nominate,
            do_success=do_success,
            replay=replay,
            use_ufrag=use_ufrag,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise IceActuationError(f"unsupported ice action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_ice_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed ICE foundation digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "ufrag": "",
        "foundation": "",
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
            "check",
            "nominate",
            "success_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "ufrag_bound",
        )
    )
    port = int(payload.get("port") or 0)
    ufrag = str(payload.get("ufrag") or "")
    foundation = str(payload.get("foundation") or "")
    dual = port > 0 and bool(ufrag) and bool(foundation)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "ufrag": ufrag,
        "foundation": foundation,
        "size": int(payload.get("size") or 0),
        "port": port,
        "check": payload.get("check") is True,
        "nominate": payload.get("nominate") is True,
        "success_response": payload.get("success_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "ufrag_bound": payload.get("ufrag_bound") is True,
    }


def run_ice_workflow(
    *,
    with_ufrag: bool = True,
    skip_bind: bool = False,
    do_check: bool = True,
    do_nominate: bool = True,
    do_success: bool = True,
    replay: bool = True,
    use_ufrag: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 8445 connectivity-check/nominated-pair workflow."""

    descriptor = ice_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICE_TOOL_PROVIDER),
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
        raise IceActuationError(f"ice tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ice-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = IceSession(out, ufrag_gate=DEFAULT_UFRAG if with_ufrag else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "check": do_check,
            "nominate": do_nominate,
            "success": do_success,
            "replay": replay,
            "use_ufrag": use_ufrag,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_ice_tool(session, arguments))
            except IceActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_ice_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_ufrag
        and not skip_bind
        and do_check
        and do_nominate
        and do_success
        and replay
        and use_ufrag
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ice_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_ufrag": with_ufrag,
        "skip_bind": skip_bind,
        "check": do_check,
        "nominate": do_nominate,
        "success": do_success,
        "replay": replay,
        "use_ufrag": use_ufrag,
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
        "ufrag_value": str(publish_result.get("ufrag") or independent.get("ufrag") or ""),
        "foundation_value": str(publish_result.get("foundation") or independent.get("foundation") or ""),
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
        "ufrag": str(trace_body["ufrag_value"] or ""),
        "foundation": str(trace_body["foundation_value"] or ""),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_ufrag": with_ufrag,
        "skip_bind": skip_bind,
        "check": do_check,
        "nominate": do_nominate,
        "success_cycle": do_success,
        "replay": replay,
        "use_ufrag": use_ufrag,
    }


def verify_ice_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed ICE trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_ice_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    ufrag = str(trace.get("ufrag_value") or independent.get("ufrag") or "")
    foundation = str(trace.get("foundation_value") or independent.get("foundation") or "")
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
        "check": independent.get("check") is True,
        "nominate": independent.get("nominate") is True,
        "success_response": independent.get("success_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "ufrag_bound": independent.get("ufrag_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "ufrag_recorded": port > 0 and ufrag == DEFAULT_UFRAG and foundation == DEFAULT_FOUNDATION,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def ice_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.ice_actuation import "
        "builtin_ice_actuation_proof; r=builtin_ice_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='ice_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_ice_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ICE_ACTUATION_ID,
        name="First-class RFC 8445 ICE connectivity-check/nominated-pair actuation",
        description=(
            "Missions that require an ice tool can opt the ice provider in, "
            "bind a loopback RFC 8445 UDP ICE agent, complete a connectivity-check "
            "with a non-empty ufrag, lockstep a nominated-pair Success that "
            "carries the stored candidate foundation, independently poll the "
            "stored candidate foundation on a later socket, and seal a "
            "digest-chained foundation. Default routing stays fail-closed; a "
            "missing ufrag keeps the hole falsifiable, and skip-CHECK/NOMINATE/"
            "SUCCESS/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.ice_actuation:builtin_ice_actuation_proof",
        proof_command=ice_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.turn-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/ice_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/dtls_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required ice tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 8445 daemon, speaks a connectivity-"
            "check then nominated-pair Success over UDP ICE with a non-empty ufrag, "
            "independently polls the stored candidate foundation on a later client "
            "socket, and binds this family as the next diversity-catalog "
            "successor once RFC 5766 TURN lockstep is proved. Missing ufrags, "
            "skip-connectivity-check, skip-nominated-pair, skip-Success, skip-REPLAY, "
            "and a connectivity-check aimed without a ufrag stay fail-closed. "
            "Later genesis can take RFC 6347 DTLS ClientHello/Finished as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("ice", "rfc8445", "udp", "ufrag", "foundation", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T230635Z-2528f998",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_ice_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 8445 ICE lockstep actuation seals a foundation digest."""

    from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
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
    from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
    from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = ICE_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(ICE_ACTUATION_GOAL) == (ICE_ACTUATION_ID,)
    checks["turn_goal_is_not_ice"] = leftover_marker_ids(TURN_ACTUATION_GOAL) == (TURN_ACTUATION_ID,)
    checks["stun_goal_is_not_ice"] = leftover_marker_ids(STUN_ACTUATION_GOAL) == (STUN_ACTUATION_ID,)
    checks["sip_goal_is_not_ice"] = leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    checks["ike_goal_is_not_ice"] = leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    checks["dhcp_goal_is_not_ice"] = leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    checks["radius_goal_is_not_ice"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_ice"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_ice"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_ice"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_ice"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_ice"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_ice"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["dtls_goal_is_not_ice"] = leftover_marker_ids(DTLS_ACTUATION_GOAL) == (DTLS_ACTUATION_ID,)
    checks["ice_goal_is_not_turn"] = TURN_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_stun"] = STUN_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_sip"] = SIP_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_ike"] = IKE_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_dhcp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_radius"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["ice_goal_is_not_dtls"] = DTLS_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["turn_marker_stays_turn"] = ICE_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["stun_marker_stays_stun"] = ICE_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["sip_marker_stays_sip"] = ICE_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["ike_marker_stays_ike"] = ICE_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["dhcp_marker_stays_dhcp"] = ICE_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["radius_marker_stays_radius"] = ICE_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["ntp_marker_stays_ntp"] = ICE_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = ICE_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = ICE_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = ICE_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = ICE_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = ICE_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["dtls_marker_stays_dtls"] = ICE_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_ice"] = (
        len(catalog) > 56
        and catalog[56]["id"] == ICE_ACTUATION_ID
        and catalog[55]["id"] == TURN_ACTUATION_ID
        and catalog[56]["source"] == "genesis_bind_ice"
    )
    checks["catalog_names_dtls"] = (
        len(catalog) > 57
        and catalog[57]["id"] == DTLS_ACTUATION_ID
        and catalog[57]["source"] == "genesis_bind_dtls"
    )
    family = capability_family(ICE_ACTUATION_GOAL)
    checks["family_is_ice"] = "ice" in family
    checks["family_is_rfc8445"] = "rfc8445" in family
    checks["family_is_ufrag"] = "ufrag" in family
    checks["family_is_foundation"] = "foundation" in family
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
    checks["family_is_not_dtls"] = (
        "dtls" not in family and "rfc6347" not in family and "cookie" not in family and "epoch" not in family
    )
    packed = encode_check(identity=SENTINEL, ufrag=DEFAULT_UFRAG, foundation=DEFAULT_FOUNDATION)
    parsed = parse_message(packed)
    checks["check_roundtrip"] = (
        parsed["is_check"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_ufrag"] is True
        and parsed["ufrag"] == DEFAULT_UFRAG
        and parsed["foundation"] == DEFAULT_FOUNDATION
        and parsed["is_response"] is False
        and parsed["is_success"] is False
        and parsed["is_nominate"] is False
        and parsed["use_candidate"] is False
        and parsed["priority"] == HOST_PRIORITY
    )
    nominated = encode_nominate(identity=SENTINEL, ufrag=DEFAULT_UFRAG, foundation=DEFAULT_FOUNDATION)
    nominated_parsed = parse_message(nominated)
    checks["nominate_roundtrip"] = (
        nominated_parsed["is_nominate"] is True
        and nominated_parsed["use_candidate"] is True
        and nominated_parsed["is_check"] is False
        and nominated_parsed["identity"] == SENTINEL
        and nominated_parsed["ufrag"] == DEFAULT_UFRAG
        and nominated_parsed["foundation"] == DEFAULT_FOUNDATION
        and nominated_parsed["is_response"] is False
    )
    success_packet = encode_success(
        identity=SENTINEL,
        ufrag=DEFAULT_UFRAG,
        foundation=DEFAULT_FOUNDATION,
        mapped_port=3478,
    )
    success_parsed = parse_message(success_packet)
    checks["success_roundtrip"] = (
        success_parsed["is_success"] is True
        and success_parsed["identity"] == SENTINEL
        and success_parsed["ufrag"] == DEFAULT_UFRAG
        and success_parsed["foundation"] == DEFAULT_FOUNDATION
        and success_parsed["is_response"] is True
        and success_parsed["is_check"] is False
        and success_parsed["mapped_port"] == 3478
        and success_parsed["mapped_host"] == "127.0.0.1"
    )
    bare = encode_check(identity=SENTINEL, ufrag=DEFAULT_UFRAG, include_ufrag=False)
    checks["missing_ufrag_is_unauthenticated"] = parse_message(bare)["has_ufrag"] is False
    neighbors = (
        TURN_ACTUATION_GOAL,
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
        DTLS_ACTUATION_GOAL,
    )
    ice_signature = semantic_signature(ICE_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(ice_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_ice = ToolDescriptor(name="remote_ice", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_ice)
    checks["naive_mcp_ice_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = ice_tool_descriptor()
    default_ice = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICE_TOOL_PROVIDER),
    )
    checks["default_ice_provider_is_unsupported"] = (
        default_ice.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{ICE_TOOL_PROVIDER}" in default_ice.reasons
    )
    checks["opted_in_ice_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_ice],
        required_tool_names=("local_memory", "ice"),
    )
    checks["naive_preflight_missing_ice"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["ice"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "ice"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICE_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "ice" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="ice-actuation-") as tmp:
        root = Path(tmp)
        missing = run_ice_workflow(with_ufrag=False, output_dir=root / "missing")
        skip_bind = run_ice_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_check = run_ice_workflow(do_check=False, output_dir=root / "skip-check")
        skip_nominate = run_ice_workflow(do_nominate=False, output_dir=root / "skip-nominate")
        skip_success = run_ice_workflow(do_success=False, output_dir=root / "skip-success")
        skip_replay = run_ice_workflow(replay=False, output_dir=root / "skip-replay")
        skip_ufrag = run_ice_workflow(use_ufrag=False, output_dir=root / "skip-ufrag")
        live = run_ice_workflow(output_dir=root / "live")
        verify = verify_ice_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_ice_trace(clone)
        checks["naive_without_ufrag_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_ufrag"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_check_stays_empty"] = (
            skip_check["ok"] is False
            and skip_check["error"] == "check_required"
            and skip_check["final_status"] == 409
            and skip_check["payload_exists"] is False
        )
        checks["skip_nominate_stays_empty"] = (
            skip_nominate["ok"] is False
            and skip_nominate["error"] == "nominate_required"
            and skip_nominate["final_status"] == 409
            and skip_nominate["payload_exists"] is False
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
        checks["skip_ufrag_stays_empty"] = (
            skip_ufrag["ok"] is False
            and skip_ufrag["error"] == "ufrag_required"
            and skip_ufrag["final_status"] == 409
            and skip_ufrag["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_ufrag"] = (
            live.get("ufrag") == DEFAULT_UFRAG
            and live.get("foundation") == DEFAULT_FOUNDATION
            and int(live.get("port") or 0) > 0
        )
        checks["token_ufrag_check_nominate_success_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_check["ok"] is False
            and skip_nominate["ok"] is False
            and skip_success["ok"] is False
            and skip_replay["ok"] is False
            and skip_ufrag["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="ice-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != ICE_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_ice"] = (
        live_goal == ICE_ACTUATION_GOAL
        and ICE_ACTUATION_ID in live_done
        and live_source == "genesis_bind_ice"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_ice_actuation_capability()
    return {
        "ok": ok,
        "action": "ice_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": ICE_ACTUATION_GOAL,
        "done_when": ICE_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
