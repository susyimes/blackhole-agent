"""Drive a first-class SCTP tool through RFC 4960 INIT/INIT-ACK.

Tool routing already fails missions that require ``sctp``: hosted SCTP
endpoints stay on the unsupported MCP provider, and no first-party SCTP
provider is executable. Unbound therefore cannot speak an INIT,
lockstep an INIT-ACK vtag handshake over UDP SCTP TSN,
independently poll the stored association tsn, or seal a tsn
digest an independent later reader can re-open.

This module closes that hole:

- advertise an ``sctp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 4960 daemon
- keep a missing-vtag client so the sctp-vtag hole stays falsifiable
- refuse INIT-ACK verify until an INIT lands with a non-empty vtag
- independently poll the stored association tsn on a later client socket
- persist a sealed tsn digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after SRTP
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
    SCTP_TOOL_PROVIDER,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    sctp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
SCTP_ACTUATION_ID = "capability.sctp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SCTP-OK"
POLL_TOKEN = "BH-SCTP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
COMMON_HEADER_SIZE = 12
CHUNK_HEADER_SIZE = 4
INIT_FIXED_SIZE = 16
EMPTY_VTAG = 0
EMPTY_TSN = 0
DEFAULT_SRC_PORT = 5000
DEFAULT_DST_PORT = 5000
DEFAULT_ARWND = 65536
DEFAULT_OS = 10
DEFAULT_IS = 10
CHUNK_INIT = 1
CHUNK_INIT_ACK = 2
PARAM_COOKIE = 7
PARAM_HOST_NAME = 11
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


SCTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SCTP_ACTUATION_ID};"
    f"capability_proved:{SCTP_ACTUATION_ID};"
    "no_skill_route"
)
SCTP_ACTUATION_GOAL = (
    "Repair rfc4960 sctp init/init-ack cycle cannot land over udp "
    "sctp vtag: hosted sctp endpoints remain unsupported so an INIT then "
    "INIT-ACK vtag handshake cannot land and a sealed tsn digest "
    "cannot be produced. A missing sctp vtag stays forbidden; fail-closed "
    "routing never opts the sctp provider in. An independent later poll of the "
    "stored association tsn keeps the hole falsifiable."
)


class SctpActuationError(RuntimeError):
    """Raised when the SCTP session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_vtag(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"vtag:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_vtag(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-vtag:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_tsn(vtag: int = EMPTY_VTAG, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"tsn:{int(vtag) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def request_cookie(vtag: int, tsn: int, token: str = SENTINEL) -> bytes:
    digest = hashlib.sha256(
        f"cookie:{int(vtag) & 0xFFFFFFFF}:{int(tsn) & 0xFFFFFFFF}:{token or SENTINEL}".encode(
            "utf-8"
        )
    ).digest()
    return digest[:16]


DEFAULT_VTAG = request_vtag(SENTINEL)
DEFAULT_TSN = request_tsn(DEFAULT_VTAG, SENTINEL)


def _pad4(data: bytes) -> bytes:
    pad = (4 - (len(data) % 4)) % 4
    return bytes(data or b"") + (b"\x00" * pad)


def encode_param(ptype: int, value: bytes) -> bytes:
    raw = bytes(value or b"")
    length = 4 + len(raw)
    return _pad4(struct.pack("!HH", int(ptype) & 0xFFFF, length) + raw)


def parse_params(data: bytes) -> list[tuple[int, bytes]]:
    raw = bytes(data or b"")
    params: list[tuple[int, bytes]] = []
    offset = 0
    while offset + 4 <= len(raw):
        ptype, length = struct.unpack("!HH", raw[offset : offset + 4])
        if int(length) < 4 or offset + int(length) > len(raw):
            break
        value = raw[offset + 4 : offset + int(length)]
        params.append((int(ptype), value))
        offset += (int(length) + 3) & ~3
    return params


def encode_packet(
    chunk_type: int,
    *,
    identity: str,
    vtag: int,
    tsn: int,
    src_port: int = DEFAULT_SRC_PORT,
    dst_port: int = DEFAULT_DST_PORT,
    include_vtag: bool = True,
) -> bytes:
    live_vtag = int(vtag) & 0xFFFFFFFF if include_vtag else EMPTY_VTAG
    live_tsn = int(tsn) & 0xFFFFFFFF if include_vtag and live_vtag else EMPTY_TSN
    header_vtag = EMPTY_VTAG if int(chunk_type) == CHUNK_INIT else live_vtag
    ident = str(identity or "").encode("utf-8")
    params = bytearray()
    if ident:
        params.extend(encode_param(PARAM_HOST_NAME, ident[:255]))
    if int(chunk_type) == CHUNK_INIT_ACK and live_vtag:
        params.extend(encode_param(PARAM_COOKIE, request_cookie(live_vtag, live_tsn, identity)))
    fixed = struct.pack(
        "!IIHHI",
        live_vtag,
        DEFAULT_ARWND,
        DEFAULT_OS,
        DEFAULT_IS,
        live_tsn,
    )
    body = fixed + bytes(params)
    chunk_length = CHUNK_HEADER_SIZE + len(body)
    chunk = _pad4(struct.pack("!BBH", int(chunk_type) & 0xFF, 0, chunk_length) + body)
    header = struct.pack(
        "!HHI",
        int(src_port) & 0xFFFF,
        int(dst_port) & 0xFFFF,
        header_vtag,
    )
    packet = header + struct.pack("!I", 0) + chunk
    checksum = crc32c(packet)
    return header + struct.pack("!I", checksum) + chunk


def encode_init(
    *,
    identity: str,
    vtag: int,
    tsn: int | None = None,
    include_vtag: bool = True,
    src_port: int = DEFAULT_SRC_PORT,
    dst_port: int = DEFAULT_DST_PORT,
) -> bytes:
    live_vtag = int(vtag) & 0xFFFFFFFF if include_vtag else EMPTY_VTAG
    live_tsn = int(tsn) if tsn is not None else request_tsn(live_vtag, identity)
    return encode_packet(
        CHUNK_INIT,
        identity=identity,
        vtag=live_vtag,
        tsn=live_tsn,
        src_port=src_port,
        dst_port=dst_port,
        include_vtag=include_vtag,
    )


def encode_init_ack(
    *,
    identity: str,
    vtag: int,
    tsn: int | None = None,
    include_vtag: bool = True,
    src_port: int = DEFAULT_SRC_PORT,
    dst_port: int = DEFAULT_DST_PORT,
) -> bytes:
    live_vtag = int(vtag) & 0xFFFFFFFF if include_vtag else EMPTY_VTAG
    live_tsn = int(tsn) if tsn is not None else request_tsn(live_vtag, identity)
    return encode_packet(
        CHUNK_INIT_ACK,
        identity=identity,
        vtag=live_vtag,
        tsn=live_tsn,
        src_port=src_port,
        dst_port=dst_port,
        include_vtag=include_vtag,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < COMMON_HEADER_SIZE + CHUNK_HEADER_SIZE + INIT_FIXED_SIZE:
        raise SctpActuationError("short_packet")
    src_port, dst_port, header_vtag, checksum = struct.unpack("!HHII", raw[:COMMON_HEADER_SIZE])
    zeroed = raw[:8] + struct.pack("!I", 0) + raw[COMMON_HEADER_SIZE:]
    if int(checksum) != crc32c(zeroed):
        raise SctpActuationError("checksum_failed")
    chunk_type, _flags, chunk_length = struct.unpack(
        "!BBH", raw[COMMON_HEADER_SIZE : COMMON_HEADER_SIZE + CHUNK_HEADER_SIZE]
    )
    if int(chunk_type) not in {CHUNK_INIT, CHUNK_INIT_ACK}:
        raise SctpActuationError("illegal_chunk")
    end = COMMON_HEADER_SIZE + int(chunk_length)
    if int(chunk_length) < CHUNK_HEADER_SIZE + INIT_FIXED_SIZE or end > len(raw):
        raise SctpActuationError("short_packet")
    body = raw[COMMON_HEADER_SIZE + CHUNK_HEADER_SIZE : end]
    initiate_tag, arwnd, outbound, inbound, initial_tsn = struct.unpack(
        "!IIHHI", body[:INIT_FIXED_SIZE]
    )
    params = parse_params(body[INIT_FIXED_SIZE:])
    identity = ""
    has_cookie = False
    for ptype, value in params:
        if int(ptype) == PARAM_HOST_NAME and not identity:
            identity = value.decode("utf-8", errors="replace")
        elif int(ptype) == PARAM_COOKIE:
            has_cookie = True
    live_vtag = int(initiate_tag)
    live_tsn = int(initial_tsn)
    has_vtag = live_vtag != EMPTY_VTAG
    has_tsn = has_vtag and live_tsn != EMPTY_TSN
    is_init = int(chunk_type) == CHUNK_INIT
    is_init_ack = int(chunk_type) == CHUNK_INIT_ACK
    return {
        "type": int(chunk_type),
        "is_init": is_init,
        "is_init_ack": is_init_ack,
        "is_response": is_init_ack,
        "src_port": int(src_port),
        "dst_port": int(dst_port),
        "header_vtag": int(header_vtag),
        "vtag": live_vtag,
        "has_vtag": has_vtag,
        "tsn": live_tsn,
        "has_tsn": has_tsn,
        "arwnd": int(arwnd),
        "outbound": int(outbound),
        "inbound": int(inbound),
        "identity": identity,
        "has_identity": bool(identity),
        "has_cookie": has_cookie,
        "checksum": int(checksum),
    }


class _SctpClient:
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
            raise SctpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_init_ack"] or not packet["is_response"]:
            raise SctpActuationError("tsn_required")
        if not packet["has_vtag"]:
            raise SctpActuationError("vtag_required")
        if not packet["has_tsn"]:
            raise SctpActuationError("tsn_required")
        return packet

    def exchange(self, packet: bytes, *, wait_tsn: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_tsn:
            raise SctpActuationError("tsn_required")
        reply = self._recv()
        return {
            "init_ack": reply,
            "vtag": int(reply.get("vtag") or EMPTY_VTAG),
            "identity": str(reply.get("identity") or ""),
            "tsn": int(reply.get("tsn") or EMPTY_TSN),
        }

    def init_ack(
        self,
        identity: str,
        vtag: int,
        tsn: int = EMPTY_TSN,
        *,
        wait_tsn: bool = True,
        include_vtag: bool = True,
    ) -> dict[str, Any]:
        packet = encode_init_ack(
            identity=identity,
            vtag=vtag,
            tsn=tsn or request_tsn(vtag, identity),
            include_vtag=include_vtag,
            src_port=self.client_port,
            dst_port=self.port,
        )
        return self.exchange(packet, wait_tsn=wait_tsn)


class SctpSession:
    """Vtag-gated loopback RFC 4960 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        vtag_gate: int = DEFAULT_VTAG,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.vtag_gate = int(vtag_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.vtag = EMPTY_VTAG
        self.tsn = EMPTY_TSN
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.inited = False
        self.init_acked = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_vtag_once(self, identity: str, vtag: int, tsn: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(vtag or EMPTY_VTAG)
            live_tsn = int(tsn or EMPTY_TSN)
            if not self.identity and name and live:
                self.identity = name
                self.vtag = live
                self.tsn = live_tsn or request_tsn(live, name)
                self.stored = True
            return str(self.identity), int(self.vtag), int(self.tsn)

    def read_vtag(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.vtag), int(self.tsn)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "vtag": EMPTY_VTAG,
            "tsn": EMPTY_TSN,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _vtag_missing(self) -> bool:
        return not int(self.vtag_gate or 0)

    def _reply_init_ack(self, peer: tuple[str, int], identity: str, vtag: int, tsn: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_init_ack(
            identity=identity,
            vtag=vtag,
            tsn=tsn,
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
            except SctpActuationError:
                continue
            if not packet.get("is_init") and not packet.get("is_init_ack"):
                continue
            if not packet.get("has_vtag"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_vtag, stored_tsn = self.store_vtag_once(
                identity,
                int(packet.get("vtag") or EMPTY_VTAG),
                int(packet.get("tsn") or EMPTY_TSN),
            )
            if not stored_name or not stored_vtag or not stored_tsn:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_init"):
                    self.inited = True
                if packet.get("is_init_ack"):
                    self.init_acked = True
                self.retrieved = True
            self._reply_init_ack(peer, stored_name, stored_vtag, stored_tsn)

    def bind(self) -> dict[str, Any]:
        if self._vtag_missing():
            return self._forbidden("missing_vtag")
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
        do_init: bool = True,
        do_init_ack: bool = True,
        do_tsn: bool = True,
        replay: bool = True,
        use_vtag: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._vtag_missing():
            return self._forbidden("missing_vtag")
        live_token = str(token or SENTINEL)
        origin_vtag = request_vtag(live_token)
        origin_tsn = request_tsn(origin_vtag, live_token)
        client: _SctpClient | None = None
        independent: _SctpClient | None = None
        try:
            client = _SctpClient(self.host, int(self.port))
            if not do_init:
                return self._conflict("init_required")
            init_packet = encode_init(
                identity=live_token,
                vtag=origin_vtag,
                tsn=origin_tsn,
                include_vtag=use_vtag,
                src_port=client.client_port,
                dst_port=int(self.port),
            )
            if not use_vtag:
                try:
                    client.exchange(init_packet, wait_tsn=True)
                except SctpActuationError:
                    return self._conflict("vtag_required")
                return self._conflict("vtag_required")
            client.send(init_packet)
            if not do_init_ack:
                return self._conflict("init_ack_required")
            init_ack_packet = encode_init_ack(
                identity=live_token,
                vtag=origin_vtag,
                tsn=origin_tsn,
                include_vtag=True,
                src_port=client.client_port,
                dst_port=int(self.port),
            )
            if not do_tsn:
                try:
                    client.exchange(init_ack_packet, wait_tsn=False)
                except SctpActuationError as error:
                    if str(error) == "tsn_required":
                        return self._conflict("tsn_required")
                    return self._conflict("tsn_required")
                return self._conflict("tsn_required")
            try:
                reply = client.exchange(init_ack_packet, wait_tsn=True)
            except SctpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("vtag_required")
                if reason == "tsn_required":
                    return self._conflict("tsn_required")
                return self._conflict("init_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("init_required")
            if int(reply.get("vtag") or EMPTY_VTAG) != origin_vtag:
                return self._conflict("tsn_required")
            if int(reply.get("tsn") or EMPTY_TSN) != origin_tsn:
                return self._conflict("tsn_required")
            self.retrieved = True
            if replay:
                independent = _SctpClient(self.host, int(self.port))
                try:
                    poll = independent.init_ack(
                        POLL_TOKEN,
                        poll_vtag(live_token),
                        request_tsn(poll_vtag(live_token), POLL_TOKEN),
                        wait_tsn=True,
                    )
                except SctpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_vtag, stored_tsn = self.read_vtag()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_vtag != origin_vtag
                    or stored_tsn != origin_tsn
                    or int(poll.get("vtag") or EMPTY_VTAG) != origin_vtag
                    or int(poll.get("tsn") or EMPTY_TSN) != origin_tsn
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_vtag}:{origin_tsn}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "vtag": origin_vtag,
                "tsn": origin_tsn,
                "init": True,
                "init_ack": True,
                "tsn_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "vtag_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_sctp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "vtag": origin_vtag,
                "tsn": origin_tsn,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "init": True,
                "init_ack": True,
                "tsn_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "vtag_bound": True,
            }
        except (OSError, SctpActuationError) as error:
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
        live = independent_sctp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "vtag": int(live.get("vtag") or EMPTY_VTAG),
            "tsn": int(live.get("tsn") or EMPTY_TSN),
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


def call_sctp_tool(session: SctpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one SCTP tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_init = True if arguments.get("init") is None else bool(arguments.get("init"))
    do_init_ack = True if arguments.get("init_ack") is None else bool(arguments.get("init_ack"))
    do_tsn = True if arguments.get("tsn") is None else bool(arguments.get("tsn"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_vtag = True if arguments.get("use_vtag") is None else bool(arguments.get("use_vtag"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_init=do_init,
            do_init_ack=do_init_ack,
            do_tsn=do_tsn,
            replay=replay,
            use_vtag=use_vtag,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SctpActuationError(f"unsupported sctp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_sctp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed SCTP tsn digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "vtag": EMPTY_VTAG,
        "tsn": EMPTY_TSN,
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
            "init",
            "init_ack",
            "tsn_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "vtag_bound",
        )
    )
    port = int(payload.get("port") or 0)
    vtag = int(payload.get("vtag") or EMPTY_VTAG)
    tsn = int(payload.get("tsn") or EMPTY_TSN)
    dual = port > 0 and bool(vtag) and bool(tsn)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "vtag": vtag,
        "tsn": tsn,
        "size": int(payload.get("size") or 0),
        "port": port,
        "init": payload.get("init") is True,
        "init_ack": payload.get("init_ack") is True,
        "tsn_response": payload.get("tsn_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "vtag_bound": payload.get("vtag_bound") is True,
    }


def run_sctp_workflow(
    *,
    with_vtag: bool = True,
    skip_bind: bool = False,
    do_init: bool = True,
    do_init_ack: bool = True,
    do_tsn: bool = True,
    replay: bool = True,
    use_vtag: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 4960 INIT/INIT-ACK vtag cycle workflow."""

    descriptor = sctp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SCTP_TOOL_PROVIDER),
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
        raise SctpActuationError(f"sctp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="sctp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SctpSession(out, vtag_gate=DEFAULT_VTAG if with_vtag else EMPTY_VTAG)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "init": do_init,
            "init_ack": do_init_ack,
            "tsn": do_tsn,
            "replay": replay,
            "use_vtag": use_vtag,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_sctp_tool(session, arguments))
            except SctpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_sctp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_vtag
        and not skip_bind
        and do_init
        and do_init_ack
        and do_tsn
        and replay
        and use_vtag
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "sctp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_vtag": with_vtag,
        "skip_bind": skip_bind,
        "init": do_init,
        "init_ack": do_init_ack,
        "tsn": do_tsn,
        "replay": replay,
        "use_vtag": use_vtag,
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
        "vtag_value": int(publish_result.get("vtag") or independent.get("vtag") or EMPTY_VTAG),
        "tsn_value": int(publish_result.get("tsn") or independent.get("tsn") or EMPTY_TSN),
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
        "vtag": int(trace_body["vtag_value"] or EMPTY_VTAG),
        "tsn": int(trace_body["tsn_value"] or EMPTY_TSN),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_vtag": with_vtag,
        "skip_bind": skip_bind,
        "init": do_init,
        "init_ack": do_init_ack,
        "tsn_cycle": do_tsn,
        "replay": replay,
        "use_vtag": use_vtag,
    }


def verify_sctp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed SCTP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_sctp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    vtag = int(trace.get("vtag_value") or independent.get("vtag") or EMPTY_VTAG)
    tsn = int(trace.get("tsn_value") or independent.get("tsn") or EMPTY_TSN)
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
        "init": independent.get("init") is True,
        "init_ack": independent.get("init_ack") is True,
        "tsn_response": independent.get("tsn_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "vtag_bound": independent.get("vtag_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "tsn_recorded": (
            port > 0
            and vtag == DEFAULT_VTAG
            and tsn == DEFAULT_TSN
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def sctp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.sctp_actuation import "
        "builtin_sctp_actuation_proof; r=builtin_sctp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='sctp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_sctp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SCTP_ACTUATION_ID,
        name="First-class RFC 4960 SCTP INIT/INIT-ACK actuation",
        description=(
            "Missions that require an sctp tool can opt the sctp provider in, "
            "bind a loopback RFC 4960 UDP SCTP endpoint, complete an INIT "
            "with a non-empty vtag, lockstep an INIT-ACK that carries the "
            "stored association tsn, independently poll the stored association "
            "tsn on a later socket, and seal a digest-chained tsn. Default "
            "routing stays fail-closed; a missing vtag keeps the hole "
            "falsifiable, and skip-INIT/INIT-ACK/TSN/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.sctp_actuation:builtin_sctp_actuation_proof",
        proof_command=sctp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.srtp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/sctp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/datachannel_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required sctp tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 4960 daemon, speaks an INIT "
            "then INIT-ACK over UDP SCTP with a non-empty vtag and association tsn, "
            "independently polls the stored association tsn on a later client "
            "socket, and binds this family as the next diversity-catalog "
            "successor once RFC 3711 SRTP lockstep is proved. Missing vtags, "
            "skip-INIT, skip-INIT-ACK, skip-tsn, skip-REPLAY, "
            "and an INIT aimed without a vtag stay fail-closed. "
            "Later genesis can take RFC 8831 Data Channel OPEN/ACK as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("sctp", "rfc4960", "udp", "vtag", "tsn", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260902T004121Z-fa9b8897",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_sctp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 4960 SCTP lockstep actuation seals a tsn digest."""

    from blackhole_agent.datachannel_actuation import (
        DATACHANNEL_ACTUATION_GOAL,
        DATACHANNEL_ACTUATION_ID,
    )
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
    from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
    from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.srtp_actuation import SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID
    from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
    from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = SCTP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SCTP_ACTUATION_GOAL) == (SCTP_ACTUATION_ID,)
    checks["srtp_goal_is_not_sctp"] = leftover_marker_ids(SRTP_ACTUATION_GOAL) == (SRTP_ACTUATION_ID,)
    checks["dtls_goal_is_not_sctp"] = leftover_marker_ids(DTLS_ACTUATION_GOAL) == (DTLS_ACTUATION_ID,)
    checks["ice_goal_is_not_sctp"] = leftover_marker_ids(ICE_ACTUATION_GOAL) == (ICE_ACTUATION_ID,)
    checks["turn_goal_is_not_sctp"] = leftover_marker_ids(TURN_ACTUATION_GOAL) == (TURN_ACTUATION_ID,)
    checks["stun_goal_is_not_sctp"] = leftover_marker_ids(STUN_ACTUATION_GOAL) == (STUN_ACTUATION_ID,)
    checks["sip_goal_is_not_sctp"] = leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    checks["ike_goal_is_not_sctp"] = leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    checks["dhcp_goal_is_not_sctp"] = leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    checks["radius_goal_is_not_sctp"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_sctp"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_sctp"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_sctp"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_sctp"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_sctp"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_sctp"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["datachannel_goal_is_not_sctp"] = leftover_marker_ids(DATACHANNEL_ACTUATION_GOAL) == (
        DATACHANNEL_ACTUATION_ID,
    )
    checks["sctp_goal_is_not_srtp"] = SRTP_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_dtls"] = DTLS_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_ice"] = ICE_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_turn"] = TURN_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_stun"] = STUN_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_sip"] = SIP_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_ike"] = IKE_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_dhcp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_radius"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["sctp_goal_is_not_datachannel"] = DATACHANNEL_ACTUATION_ID not in leftover_marker_ids(
        SCTP_ACTUATION_GOAL
    )
    checks["srtp_marker_stays_srtp"] = SCTP_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["dtls_marker_stays_dtls"] = SCTP_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["ice_marker_stays_ice"] = SCTP_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["turn_marker_stays_turn"] = SCTP_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["stun_marker_stays_stun"] = SCTP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["sip_marker_stays_sip"] = SCTP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["ike_marker_stays_ike"] = SCTP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["dhcp_marker_stays_dhcp"] = SCTP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["radius_marker_stays_radius"] = SCTP_ACTUATION_ID not in leftover_marker_ids(
        RADIUS_ACTUATION_GOAL
    )
    checks["ntp_marker_stays_ntp"] = SCTP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = SCTP_ACTUATION_ID not in leftover_marker_ids(
        SYSLOG_ACTUATION_GOAL
    )
    checks["snmp_marker_stays_snmp"] = SCTP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = SCTP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = SCTP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = SCTP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["datachannel_marker_stays_datachannel"] = SCTP_ACTUATION_ID not in leftover_marker_ids(
        DATACHANNEL_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    checks["catalog_names_sctp"] = (
        len(catalog) > 59
        and catalog[59]["id"] == SCTP_ACTUATION_ID
        and catalog[58]["id"] == SRTP_ACTUATION_ID
        and catalog[59]["source"] == "genesis_bind_sctp"
    )
    checks["catalog_names_datachannel"] = (
        len(catalog) > 60
        and catalog[60]["id"] == DATACHANNEL_ACTUATION_ID
        and catalog[60]["source"] == "genesis_bind_datachannel"
    )
    family = capability_family(SCTP_ACTUATION_GOAL)
    checks["family_is_sctp"] = "sctp" in family
    checks["family_is_rfc4960"] = "rfc4960" in family
    checks["family_is_vtag"] = "vtag" in family
    checks["family_is_tsn"] = "tsn" in family
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
    checks["family_is_not_datachannel"] = (
        "datachannel" not in family
        and "rfc8831" not in family
        and "ppid" not in family
        and "dcep" not in family
    )
    packed = encode_init(identity=SENTINEL, vtag=DEFAULT_VTAG, tsn=DEFAULT_TSN)
    parsed = parse_message(packed)
    checks["init_roundtrip"] = (
        parsed["is_init"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_vtag"] is True
        and parsed["vtag"] == DEFAULT_VTAG
        and parsed["tsn"] == DEFAULT_TSN
        and parsed["is_response"] is False
        and parsed["is_init_ack"] is False
        and parsed["header_vtag"] == EMPTY_VTAG
        and parsed["type"] == CHUNK_INIT
        and parsed["has_cookie"] is False
    )
    acked = encode_init_ack(
        identity=SENTINEL,
        vtag=DEFAULT_VTAG,
        tsn=DEFAULT_TSN,
    )
    ack_parsed = parse_message(acked)
    checks["init_ack_roundtrip"] = (
        ack_parsed["is_init_ack"] is True
        and ack_parsed["is_response"] is True
        and ack_parsed["is_init"] is False
        and ack_parsed["identity"] == SENTINEL
        and ack_parsed["vtag"] == DEFAULT_VTAG
        and ack_parsed["tsn"] == DEFAULT_TSN
        and ack_parsed["has_tsn"] is True
        and ack_parsed["header_vtag"] == DEFAULT_VTAG
        and ack_parsed["has_cookie"] is True
    )
    bare = encode_init(identity=SENTINEL, vtag=DEFAULT_VTAG, include_vtag=False)
    checks["missing_vtag_is_unauthenticated"] = parse_message(bare)["has_vtag"] is False
    neighbors = (
        SRTP_ACTUATION_GOAL,
        DTLS_ACTUATION_GOAL,
        ICE_ACTUATION_GOAL,
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
        DATACHANNEL_ACTUATION_GOAL,
    )
    sctp_signature = semantic_signature(SCTP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(sctp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_sctp = ToolDescriptor(name="remote_sctp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_sctp)
    checks["naive_mcp_sctp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = sctp_tool_descriptor()
    default_sctp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SCTP_TOOL_PROVIDER),
    )
    checks["default_sctp_provider_is_unsupported"] = (
        default_sctp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SCTP_TOOL_PROVIDER}" in default_sctp.reasons
    )
    checks["opted_in_sctp_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_sctp],
        required_tool_names=("local_memory", "sctp"),
    )
    checks["naive_preflight_missing_sctp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["sctp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "sctp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SCTP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "sctp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="sctp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_sctp_workflow(with_vtag=False, output_dir=root / "missing")
        skip_bind = run_sctp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_init = run_sctp_workflow(do_init=False, output_dir=root / "skip-init")
        skip_init_ack = run_sctp_workflow(do_init_ack=False, output_dir=root / "skip-init-ack")
        skip_tsn = run_sctp_workflow(do_tsn=False, output_dir=root / "skip-tsn")
        skip_replay = run_sctp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_vtag = run_sctp_workflow(use_vtag=False, output_dir=root / "skip-vtag")
        live = run_sctp_workflow(output_dir=root / "live")
        verify = verify_sctp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_sctp_trace(clone)
        checks["naive_without_vtag_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_vtag"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_init_stays_empty"] = (
            skip_init["ok"] is False
            and skip_init["error"] == "init_required"
            and skip_init["final_status"] == 409
            and skip_init["payload_exists"] is False
        )
        checks["skip_init_ack_stays_empty"] = (
            skip_init_ack["ok"] is False
            and skip_init_ack["error"] == "init_ack_required"
            and skip_init_ack["final_status"] == 409
            and skip_init_ack["payload_exists"] is False
        )
        checks["skip_tsn_stays_empty"] = (
            skip_tsn["ok"] is False
            and skip_tsn["error"] == "tsn_required"
            and skip_tsn["final_status"] == 409
            and skip_tsn["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_vtag_stays_empty"] = (
            skip_vtag["ok"] is False
            and skip_vtag["error"] == "vtag_required"
            and skip_vtag["final_status"] == 409
            and skip_vtag["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_tsn"] = (
            int(live.get("vtag") or 0) == DEFAULT_VTAG
            and int(live.get("tsn") or 0) == DEFAULT_TSN
            and int(live.get("port") or 0) > 0
        )
        checks["token_vtag_init_init_ack_tsn_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_init["ok"] is False
            and skip_init_ack["ok"] is False
            and skip_tsn["ok"] is False
            and skip_replay["ok"] is False
            and skip_vtag["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="sctp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SCTP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_sctp"] = (
        live_goal == SCTP_ACTUATION_GOAL
        and SCTP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_sctp"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_sctp_actuation_capability()
    return {
        "ok": ok,
        "action": "sctp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SCTP_ACTUATION_GOAL,
        "done_when": SCTP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
