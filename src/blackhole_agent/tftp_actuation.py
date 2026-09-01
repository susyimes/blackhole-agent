"""Drive a first-class TFTP tool through RFC 1350 RRQ/WRQ/DATA/ACK lockstep.

Tool routing already fails missions that require ``tftp``: hosted file-transfer
plugins stay on the unsupported MCP provider, and no first-party TFTP
provider is executable. Unbound therefore cannot speak WRQ, lockstep DATA/ACK
opcodes over UDP, independently RRQ the stored octet stream, or seal a block
digest an independent later reader can re-open.

This module closes that hole:

- advertise a ``tftp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1350 listener
- keep a missing-TID client so the transfer-id hole stays falsifiable
- refuse DATA/ACK until WRQ lands and the server replies from a distinct TID
- independently RRQ the stored body on a later client socket
- persist a sealed block digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after FTP
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
    TFTP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    tftp_tool_descriptor,
)

SCHEMA_VERSION = 1
TFTP_ACTUATION_ID = "capability.tftp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-TFTP-OK"
DEFAULT_TID = 1350
DEFAULT_NAME = "beacon.bin"
DEFAULT_MODE = "octet"
SEALED_NAME = "sealed.json"
BLOCK_SIZE = 512
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2

OP_RRQ = 1
OP_WRQ = 2
OP_DATA = 3
OP_ACK = 4
OP_ERROR = 5
ERR_NOT_FOUND = 1
ERR_ILLEGAL = 4
ERR_UNKNOWN_TID = 5

TFTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TFTP_ACTUATION_ID};"
    f"capability_proved:{TFTP_ACTUATION_ID};"
    "no_skill_route"
)
TFTP_ACTUATION_GOAL = (
    "Repair rfc1350 tftp rrq/wrq/data/ack cycle cannot land over udp lockstep "
    "opcodes: hosted tftp tools remain unsupported so a WRQ then DATA/ACK "
    "opcode exchange cannot land and a sealed block digest cannot be produced. "
    "A missing tftp tid stays forbidden; fail-closed routing never opts the "
    "tftp provider in. An independent later RRQ of the stored octet stream "
    "keeps the hole falsifiable."
)


class TftpActuationError(RuntimeError):
    """Raised when the TFTP session or loopback listener fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def sentinel_body(token: str = SENTINEL) -> bytes:
    raw = str(token or SENTINEL).encode("utf-8")
    # Two DATA packets so skip-ACK cannot pretend the lockstep completed.
    need = BLOCK_SIZE + 1
    if len(raw) >= need:
        return raw
    return raw + bytes(need - len(raw))


def iter_blocks(body: bytes) -> list[bytes]:
    payload = bytes(body or b"")
    if not payload:
        return [b""]
    blocks = [payload[index : index + BLOCK_SIZE] for index in range(0, len(payload), BLOCK_SIZE)]
    if len(blocks[-1]) == BLOCK_SIZE:
        blocks.append(b"")
    return blocks


def encode_request(opcode: int, filename: str, mode: str = DEFAULT_MODE) -> bytes:
    return (
        struct.pack("!H", int(opcode))
        + str(filename or DEFAULT_NAME).encode("ascii", errors="replace")
        + b"\x00"
        + str(mode or DEFAULT_MODE).encode("ascii", errors="replace")
        + b"\x00"
    )


def encode_data(block: int, payload: bytes) -> bytes:
    return struct.pack("!HH", OP_DATA, int(block) & 0xFFFF) + bytes(payload or b"")


def encode_ack(block: int) -> bytes:
    return struct.pack("!HH", OP_ACK, int(block) & 0xFFFF)


def encode_error(code: int, message: str) -> bytes:
    return (
        struct.pack("!HH", OP_ERROR, int(code) & 0xFFFF)
        + str(message or "").encode("ascii", errors="replace")
        + b"\x00"
    )


def parse_packet(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 2:
        raise TftpActuationError("truncated_packet")
    opcode = struct.unpack_from("!H", raw, 0)[0]
    if opcode in {OP_RRQ, OP_WRQ}:
        parts = raw[2:].split(b"\x00")
        if len(parts) < 2 or not parts[0]:
            raise TftpActuationError("malformed_request")
        return {
            "opcode": opcode,
            "filename": parts[0].decode("ascii", errors="replace"),
            "mode": (parts[1].decode("ascii", errors="replace") or DEFAULT_MODE).lower(),
        }
    if opcode == OP_DATA:
        if len(raw) < 4:
            raise TftpActuationError("truncated_data")
        return {
            "opcode": opcode,
            "block": struct.unpack_from("!H", raw, 2)[0],
            "payload": raw[4:],
        }
    if opcode == OP_ACK:
        if len(raw) < 4:
            raise TftpActuationError("truncated_ack")
        return {"opcode": opcode, "block": struct.unpack_from("!H", raw, 2)[0]}
    if opcode == OP_ERROR:
        if len(raw) < 4:
            raise TftpActuationError("truncated_error")
        return {
            "opcode": opcode,
            "code": struct.unpack_from("!H", raw, 2)[0],
            "message": raw[4:].split(b"\x00", 1)[0].decode("ascii", errors="replace"),
        }
    raise TftpActuationError("illegal_opcode")


class _TftpClient:
    def __init__(self, host: str, port: int, *, timeout: float = IO_TIMEOUT) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.server_tid = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(timeout)
        self.client_tid = int(self.sock.getsockname()[1])

    def close(self) -> None:
        sock = self.sock
        self.sock = None  # type: ignore[assignment]
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass

    def _recv(self) -> tuple[dict[str, Any], tuple[str, int]]:
        try:
            payload, addr = self.sock.recvfrom(4096)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise TftpActuationError("timeout") from error
        return parse_packet(payload), (str(addr[0]), int(addr[1]))

    def wrq(
        self,
        filename: str,
        body: bytes,
        *,
        send_data: bool = True,
        use_transfer_tid: bool = True,
    ) -> int:
        self.sock.sendto(encode_request(OP_WRQ, filename), (self.host, self.port))
        packet, addr = self._recv()
        if packet["opcode"] == OP_ERROR:
            raise TftpActuationError("unknown_tid" if int(packet.get("code") or 0) == ERR_UNKNOWN_TID else "wrq_required")
        ack_block = packet.get("block")
        if packet["opcode"] != OP_ACK or ack_block is None or int(ack_block) != 0:
            raise TftpActuationError("ack_required")
        self.server_tid = int(addr[1])
        if not send_data:
            raise TftpActuationError("data_required")
        dest_port = self.server_tid if use_transfer_tid else self.port
        dest = (self.host, dest_port)
        for block, chunk in enumerate(iter_blocks(body), start=1):
            self.sock.sendto(encode_data(block, chunk), dest)
            packet, _ack_addr = self._recv()
            if packet["opcode"] == OP_ERROR:
                raise TftpActuationError(
                    "unknown_tid" if int(packet.get("code") or 0) == ERR_UNKNOWN_TID else "data_required"
                )
            if packet["opcode"] != OP_ACK or int(packet.get("block") or -1) != block:
                raise TftpActuationError("ack_required")
        return self.server_tid

    def rrq(self, filename: str, *, send_ack: bool = True) -> bytes:
        self.sock.sendto(encode_request(OP_RRQ, filename), (self.host, self.port))
        chunks: list[bytes] = []
        while True:
            packet, addr = self._recv()
            if packet["opcode"] == OP_ERROR:
                raise TftpActuationError("retrieve_required")
            if packet["opcode"] != OP_DATA:
                raise TftpActuationError("retrieve_required")
            chunks.append(bytes(packet.get("payload") or b""))
            if send_ack:
                self.sock.sendto(encode_ack(int(packet["block"])), addr)
            payload = bytes(packet.get("payload") or b"")
            if len(payload) < BLOCK_SIZE:
                break
            if not send_ack:
                raise TftpActuationError("ack_required")
        return b"".join(chunks)


class TftpSession:
    """TID-gated loopback RFC 1350 listener: bind, publish, read."""

    def __init__(self, output_dir: Path, *, tid: int = DEFAULT_TID) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tid = int(tid or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.well_known: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.files: dict[str, bytes] = {}
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.last_token = ""
        self.last_digest = ""
        self.last_transfer_tid = 0
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()
        self._transfers: list[socket.socket] = []

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_file(self, name: str, body: bytes) -> None:
        with self._lock:
            self.files[str(name or DEFAULT_NAME)] = bytes(body or b"")
            self.stored = True

    def read_file(self, name: str) -> bytes | None:
        with self._lock:
            if str(name or DEFAULT_NAME) not in self.files:
                return None
            return self.files[str(name or DEFAULT_NAME)]

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "well_known_port": int(self.port or 0),
            "transfer_tid": 0,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _track(self, sock: socket.socket) -> socket.socket:
        with self._lock:
            self._transfers.append(sock)
        return sock

    def _serve(self) -> None:
        while self._running:
            sock = self.well_known
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
            except TftpActuationError:
                continue
            opcode = int(packet.get("opcode") or 0)
            peer = (str(addr[0]), int(addr[1]))
            if opcode in {OP_RRQ, OP_WRQ}:
                self._start_transfer(peer, str(packet.get("filename") or DEFAULT_NAME), opcode)
                continue
            try:
                sock.sendto(encode_error(ERR_UNKNOWN_TID, "Unknown transfer ID"), peer)
            except OSError:
                return

    def _start_transfer(self, peer: tuple[str, int], filename: str, opcode: int) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(IO_TIMEOUT)
        self._track(sock)
        tid = int(sock.getsockname()[1])
        with self._lock:
            self.last_transfer_tid = tid
        target = self._run_wrq if opcode == OP_WRQ else self._run_rrq
        thread = threading.Thread(target=target, args=(sock, peer, filename), daemon=True)
        thread.start()

    def _run_wrq(self, sock: socket.socket, peer: tuple[str, int], filename: str) -> None:
        try:
            sock.sendto(encode_ack(0), peer)
            chunks: list[bytes] = []
            expected = 1
            while True:
                payload, addr = sock.recvfrom(4096)
                if (str(addr[0]), int(addr[1])) != peer:
                    sock.sendto(encode_error(ERR_UNKNOWN_TID, "Unknown transfer ID"), addr)
                    continue
                packet = parse_packet(payload)
                if packet["opcode"] != OP_DATA or int(packet.get("block") or 0) != expected:
                    sock.sendto(encode_error(ERR_ILLEGAL, "Illegal TFTP operation"), addr)
                    continue
                chunk = bytes(packet.get("payload") or b"")
                chunks.append(chunk)
                sock.sendto(encode_ack(expected), peer)
                if len(chunk) < BLOCK_SIZE:
                    self.store_file(filename, b"".join(chunks))
                    return
                expected += 1
        except (OSError, TimeoutError, socket.timeout, TftpActuationError):
            return

    def _run_rrq(self, sock: socket.socket, peer: tuple[str, int], filename: str) -> None:
        body = self.read_file(filename)
        try:
            if body is None:
                sock.sendto(encode_error(ERR_NOT_FOUND, "File not found"), peer)
                return
            for block, chunk in enumerate(iter_blocks(body), start=1):
                sock.sendto(encode_data(block, chunk), peer)
                payload, addr = sock.recvfrom(4096)
                if (str(addr[0]), int(addr[1])) != peer:
                    sock.sendto(encode_error(ERR_UNKNOWN_TID, "Unknown transfer ID"), addr)
                    continue
                packet = parse_packet(payload)
                if packet["opcode"] != OP_ACK or int(packet.get("block") or 0) != block:
                    sock.sendto(encode_error(ERR_ILLEGAL, "Illegal TFTP operation"), addr)
                    return
        except (OSError, TimeoutError, socket.timeout, TftpActuationError):
            return

    def bind(self) -> dict[str, Any]:
        if not self.tid:
            return self._forbidden("missing_tid")
        if self.well_known is not None:
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
        self.well_known = sock
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
        wrq: bool = True,
        data: bool = True,
        ack: bool = True,
        retrieve: bool = True,
        replay: bool = True,
        use_transfer_tid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.tid:
            return self._forbidden("missing_tid")
        live_token = str(token or SENTINEL)
        body = sentinel_body(live_token)
        client: _TftpClient | None = None
        independent: _TftpClient | None = None
        try:
            client = _TftpClient(self.host, int(self.port))
            if not wrq:
                return self._conflict("wrq_required")
            try:
                transfer_tid = client.wrq(
                    DEFAULT_NAME,
                    body,
                    send_data=data,
                    use_transfer_tid=use_transfer_tid,
                )
            except TftpActuationError as error:
                reason = str(error)
                if reason == "unknown_tid":
                    return self._conflict("tid_required")
                if reason == "data_required":
                    return self._conflict("data_required")
                if reason == "ack_required":
                    return self._conflict("ack_required")
                return self._conflict("wrq_required")
            if transfer_tid == int(self.port or 0):
                return self._conflict("tid_collision")
            self.last_transfer_tid = int(transfer_tid)
            retrieved_body = b""
            if retrieve:
                try:
                    retrieved_body = client.rrq(DEFAULT_NAME, send_ack=ack)
                except TftpActuationError as error:
                    reason = str(error)
                    if reason == "ack_required":
                        return self._conflict("ack_required")
                    return self._conflict("retrieve_required")
                if retrieved_body != body:
                    return self._conflict("retrieve_required")
                self.retrieved = True
            elif replay:
                return self._conflict("retrieve_required")
            if replay:
                independent = _TftpClient(self.host, int(self.port))
                try:
                    replay_body = independent.rrq(DEFAULT_NAME, send_ack=True)
                except TftpActuationError:
                    return self._conflict("replay_required")
                if replay_body != body:
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(body)
            sealed = {
                "name": DEFAULT_NAME,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(body),
                "well_known_port": int(self.port or 0),
                "transfer_tid": int(self.last_transfer_tid),
                "client_tid": int(client.client_tid),
                "wrq": True,
                "data": True,
                "ack": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "tid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_tftp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "name": DEFAULT_NAME,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(body),
                "well_known_port": int(self.port or 0),
                "transfer_tid": int(self.last_transfer_tid),
                "client_tid": int(client.client_tid),
                "path": str(self.sealed_path),
                "wrq": True,
                "data": True,
                "ack": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "tid_bound": True,
            }
        except (OSError, TftpActuationError) as error:
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
        live = independent_tftp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "name": str(live.get("name") or ""),
            "well_known_port": int(live.get("well_known_port") or 0),
            "transfer_tid": int(live.get("transfer_tid") or 0),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        self._running = False
        sock = self.well_known
        thread = self.thread
        self.well_known = None
        self.thread = None
        self.host = None
        self.port = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        with self._lock:
            transfers = list(self._transfers)
            self._transfers.clear()
        for item in transfers:
            try:
                item.close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=1)
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_tftp_tool(session: TftpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one TFTP tool call against a bound listener session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    wrq = True if arguments.get("wrq") is None else bool(arguments.get("wrq"))
    data = True if arguments.get("data") is None else bool(arguments.get("data"))
    ack = True if arguments.get("ack") is None else bool(arguments.get("ack"))
    retrieve = True if arguments.get("retrieve") is None else bool(arguments.get("retrieve"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_transfer_tid = (
        True if arguments.get("use_transfer_tid") is None else bool(arguments.get("use_transfer_tid"))
    )
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            wrq=wrq,
            data=data,
            ack=ack,
            retrieve=retrieve,
            replay=replay,
            use_transfer_tid=use_transfer_tid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise TftpActuationError(f"unsupported tftp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_tftp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed TFTP block digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "name": "",
        "well_known_port": 0,
        "transfer_tid": 0,
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
            "wrq",
            "data",
            "ack",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "tid_bound",
        )
    )
    well_known_port = int(payload.get("well_known_port") or 0)
    transfer_tid = int(payload.get("transfer_tid") or 0)
    dual = transfer_tid > 0 and well_known_port > 0 and transfer_tid != well_known_port
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "name": str(payload.get("name") or ""),
        "size": int(payload.get("size") or 0),
        "well_known_port": well_known_port,
        "transfer_tid": transfer_tid,
        "wrq": payload.get("wrq") is True,
        "data": payload.get("data") is True,
        "ack": payload.get("ack") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "tid_bound": payload.get("tid_bound") is True,
    }


def run_tftp_workflow(
    *,
    with_tid: bool = True,
    skip_bind: bool = False,
    wrq: bool = True,
    data: bool = True,
    ack: bool = True,
    retrieve: bool = True,
    replay: bool = True,
    use_transfer_tid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1350 RRQ/WRQ/DATA/ACK workflow and seal a trace."""

    descriptor = tftp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TFTP_TOOL_PROVIDER),
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
        raise TftpActuationError(f"tftp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="tftp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = TftpSession(out, tid=DEFAULT_TID if with_tid else 0)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "wrq": wrq,
            "data": data,
            "ack": ack,
            "retrieve": retrieve,
            "replay": replay,
            "use_transfer_tid": use_transfer_tid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_tftp_tool(session, arguments))
            except TftpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_tftp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_tid
        and not skip_bind
        and wrq
        and data
        and ack
        and retrieve
        and replay
        and use_transfer_tid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "tftp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_tid": with_tid,
        "skip_bind": skip_bind,
        "wrq": wrq,
        "data": data,
        "ack": ack,
        "retrieve": retrieve,
        "replay": replay,
        "use_transfer_tid": use_transfer_tid,
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
        "well_known_port": int(publish_result.get("well_known_port") or independent.get("well_known_port") or 0),
        "transfer_tid": int(publish_result.get("transfer_tid") or independent.get("transfer_tid") or 0),
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
        "well_known_port": int(trace_body["well_known_port"] or 0),
        "transfer_tid": int(trace_body["transfer_tid"] or 0),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_tid": with_tid,
        "skip_bind": skip_bind,
        "wrq": wrq,
        "data": data,
        "ack": ack,
        "retrieve": retrieve,
        "replay": replay,
        "use_transfer_tid": use_transfer_tid,
    }


def verify_tftp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed TFTP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_tftp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    well_known_port = int(trace.get("well_known_port") or independent.get("well_known_port") or 0)
    transfer_tid = int(trace.get("transfer_tid") or independent.get("transfer_tid") or 0)
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
        "wrq": independent.get("wrq") is True,
        "data": independent.get("data") is True,
        "ack": independent.get("ack") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "tid_bound": independent.get("tid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "distinct_tids": transfer_tid > 0 and well_known_port > 0 and transfer_tid != well_known_port,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def tftp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.tftp_actuation import "
        "builtin_tftp_actuation_proof; r=builtin_tftp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='tftp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_tftp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=TFTP_ACTUATION_ID,
        name="First-class RFC 1350 TFTP RRQ/WRQ/DATA/ACK actuation",
        description=(
            "Missions that require a tftp tool can opt the tftp provider in, "
            "bind a loopback RFC 1350 UDP listener, complete WRQ, lockstep "
            "DATA/ACK opcodes from a distinct transfer TID, RRQ the stored "
            "octet stream on the same client, independently RRQ it on a later "
            "socket, and seal a digest-chained block transfer. Default routing "
            "stays fail-closed; a missing TID keeps the hole falsifiable, and "
            "skip-WRQ/DATA/ACK/RRQ/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.tftp_actuation:builtin_tftp_actuation_proof",
        proof_command=tftp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.ftp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/tftp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/snmp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required tftp tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 1350 listener, speaks WRQ, "
            "DATA/ACK lockstep opcodes from a distinct UDP TID, RRQ the stored "
            "octet stream, independently RRQ it on a later client socket, and "
            "binds this family as the next diversity-catalog successor once "
            "RFC 959 FTP PASV transfer is proved. Missing TIDs, skip-WRQ, "
            "skip-DATA, skip-ACK, skip-RRQ, skip-REPLAY, and DATA aimed at the "
            "well-known port stay fail-closed. Later genesis can take RFC 1157 "
            "SNMP GET/SET/RESPONSE as the next unsaturated diversity-catalog "
            "family."
        ),
        tags=("tftp", "rfc1350", "udp", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T172057Z-9d4b32cb",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_tftp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1350 TFTP lockstep actuation seals a block digest."""

    from blackhole_agent.amqp_actuation import AMQP_ACTUATION_GOAL, AMQP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
    from blackhole_agent.grpc_actuation import GRPC_ACTUATION_GOAL, GRPC_ACTUATION_ID
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
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.ssh_actuation import SSH_ACTUATION_GOAL, SSH_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = TFTP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_tftp"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["amqp_goal_is_not_tftp"] = leftover_marker_ids(AMQP_ACTUATION_GOAL) == (AMQP_ACTUATION_ID,)
    checks["grpc_goal_is_not_tftp"] = leftover_marker_ids(GRPC_ACTUATION_GOAL) == (GRPC_ACTUATION_ID,)
    checks["ssh_goal_is_not_tftp"] = leftover_marker_ids(SSH_ACTUATION_GOAL) == (SSH_ACTUATION_ID,)
    checks["dns_goal_is_not_tftp"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["snmp_goal_is_not_tftp"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["tftp_goal_is_not_amqp"] = AMQP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["tftp_goal_is_not_grpc"] = GRPC_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["tftp_goal_is_not_ssh"] = SSH_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["tftp_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["tftp_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["amqp_marker_stays_amqp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    checks["grpc_marker_stays_grpc"] = TFTP_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    checks["ssh_marker_stays_ssh"] = TFTP_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = TFTP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_tftp"] = (
        len(catalog) > 46
        and catalog[46]["id"] == TFTP_ACTUATION_ID
        and catalog[45]["id"] == FTP_ACTUATION_ID
    )
    checks["catalog_names_snmp"] = (
        len(catalog) > 47
        and catalog[47]["id"] == SNMP_ACTUATION_ID
        and catalog[47]["source"] == "genesis_bind_snmp"
    )
    family = capability_family(TFTP_ACTUATION_GOAL)
    checks["family_is_tftp"] = "tftp" in family
    checks["family_is_rfc1350"] = "rfc1350" in family
    checks["family_is_not_ftp"] = "ftpd" not in family and "pasv" not in family
    checks["family_is_not_amqp"] = "amqp" not in family and "queue" not in family
    checks["family_is_not_grpc"] = "grpc" not in family and "http2" not in family
    checks["family_is_not_openssh"] = "openssh" not in family and "ssh" not in family
    checks["family_is_not_dns"] = "tsig" not in family and "nameserver" not in family
    checks["family_is_not_snmp"] = "snmp" not in family and "varbind" not in family
    packed = encode_request(OP_WRQ, DEFAULT_NAME, DEFAULT_MODE)
    parsed = parse_packet(packed)
    checks["wrq_roundtrip"] = parsed["opcode"] == OP_WRQ and parsed["filename"] == DEFAULT_NAME
    ack = parse_packet(encode_ack(0))
    data_packet = parse_packet(encode_data(1, b"abc"))
    checks["data_ack_roundtrip"] = ack["opcode"] == OP_ACK and data_packet["payload"] == b"abc"
    blocks = iter_blocks(sentinel_body())
    checks["lockstep_needs_two_blocks"] = len(blocks) == 2 and len(blocks[0]) == BLOCK_SIZE
    neighbors = (
        FTP_ACTUATION_GOAL,
        AMQP_ACTUATION_GOAL,
        GRPC_ACTUATION_GOAL,
        SSH_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
    )
    tftp_signature = semantic_signature(TFTP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(tftp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_tftp = ToolDescriptor(name="remote_tftp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_tftp)
    checks["naive_mcp_tftp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = tftp_tool_descriptor()
    default_tftp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TFTP_TOOL_PROVIDER),
    )
    checks["default_tftp_provider_is_unsupported"] = (
        default_tftp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{TFTP_TOOL_PROVIDER}" in default_tftp.reasons
    )
    checks["opted_in_tftp_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_tftp],
        required_tool_names=("local_memory", "tftp"),
    )
    checks["naive_preflight_missing_tftp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["tftp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "tftp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TFTP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "tftp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="tftp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_tftp_workflow(with_tid=False, output_dir=root / "missing")
        skip_bind = run_tftp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_wrq = run_tftp_workflow(wrq=False, output_dir=root / "skip-wrq")
        skip_data = run_tftp_workflow(data=False, output_dir=root / "skip-data")
        skip_ack = run_tftp_workflow(ack=False, output_dir=root / "skip-ack")
        skip_retr = run_tftp_workflow(retrieve=False, output_dir=root / "skip-retr")
        skip_replay = run_tftp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_tid = run_tftp_workflow(use_transfer_tid=False, output_dir=root / "skip-tid")
        live = run_tftp_workflow(output_dir=root / "live")
        verify = verify_tftp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_tftp_trace(clone)
        checks["naive_without_tid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_tid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_wrq_stays_empty"] = (
            skip_wrq["ok"] is False
            and skip_wrq["error"] == "wrq_required"
            and skip_wrq["final_status"] == 409
            and skip_wrq["payload_exists"] is False
        )
        checks["skip_data_stays_empty"] = (
            skip_data["ok"] is False
            and skip_data["error"] == "data_required"
            and skip_data["final_status"] == 409
            and skip_data["payload_exists"] is False
        )
        checks["skip_ack_stays_empty"] = (
            skip_ack["ok"] is False
            and skip_ack["error"] == "ack_required"
            and skip_ack["final_status"] == 409
            and skip_ack["payload_exists"] is False
        )
        checks["skip_retrieve_stays_empty"] = (
            skip_retr["ok"] is False
            and skip_retr["error"] == "retrieve_required"
            and skip_retr["final_status"] == 409
            and skip_retr["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_tid_stays_empty"] = (
            skip_tid["ok"] is False
            and skip_tid["error"] == "tid_required"
            and skip_tid["final_status"] == 409
            and skip_tid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_distinct_tids"] = (
            int(live.get("transfer_tid") or 0) > 0
            and int(live.get("well_known_port") or 0) > 0
            and int(live.get("transfer_tid") or 0) != int(live.get("well_known_port") or 0)
        )
        checks["token_tid_wrq_data_ack_rrq_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_wrq["ok"] is False
            and skip_data["ok"] is False
            and skip_ack["ok"] is False
            and skip_retr["ok"] is False
            and skip_replay["ok"] is False
            and skip_tid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="tftp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != TFTP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_tftp"] = (
        live_goal == TFTP_ACTUATION_GOAL
        and TFTP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_tftp"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_tftp_actuation_capability()
    return {
        "ok": ok,
        "action": "tftp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": TFTP_ACTUATION_GOAL,
        "done_when": TFTP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
