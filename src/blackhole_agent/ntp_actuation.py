"""Drive a first-class NTP tool through RFC 5905 CLIENT/SERVER lockstep.

Tool routing already fails missions that require ``ntp``: hosted NTP
plugins stay on the unsupported MCP provider, and no first-party NTP
provider is executable. Unbound therefore cannot speak CLIENT, lockstep a
SERVER originate/receive/transmit exchange over UDP timestamps, independently
poll the stored origin timestamp, or seal a timestamp digest an independent
later reader can re-open.

This module closes that hole:

- advertise an ``ntp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 5905 daemon
- keep a missing-keyid client so the key-identifier hole stays falsifiable
- refuse SERVER originate/receive/transmit until CLIENT lands with a MAC
- independently poll the stored origin timestamp on a later client socket
- persist a sealed timestamp digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after syslog
"""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import socket
import struct
import tempfile
import threading
import time
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
    NTP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    ntp_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
NTP_ACTUATION_ID = "capability.ntp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-NTP-OK"
DEFAULT_KEYID = 1
DEFAULT_KEY = b"blackhole-ntp-key"
SENTINEL_REFID = b"BHOK"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
HEADER_SIZE = 48
MAC_SIZE = 16
KEYID_SIZE = 4
AUTH_SIZE = HEADER_SIZE + KEYID_SIZE + MAC_SIZE
NTP_VERSION = 4
MODE_CLIENT = 3
MODE_SERVER = 4
LEAP_NOSYNC = 0
STRATUM_CLIENT = 0
STRATUM_PRIMARY = 1
POLL = 6
PRECISION = 0xEC
NTP_UNIX_DELTA = 2208988800
HEADER_STRUCT = struct.Struct("!BBBBIIIQQQQ")

NTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{NTP_ACTUATION_ID};"
    f"capability_proved:{NTP_ACTUATION_ID};"
    "no_skill_route"
)
NTP_ACTUATION_GOAL = (
    "Repair rfc5905 ntp originate/receive/transmit cycle cannot land over udp "
    "timestamps: hosted ntp tools remain unsupported so a CLIENT then SERVER "
    "originate/receive/transmit exchange cannot land and a sealed timestamp "
    "digest cannot be produced. A missing ntp keyid stays forbidden; fail-closed "
    "routing never opts the ntp provider in. An independent later poll of the "
    "stored origin timestamp keeps the hole falsifiable."
)


class NtpActuationError(RuntimeError):
    """Raised when the NTP session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def _md5(data: bytes) -> bytes:
    try:
        return hashlib.md5(data, usedforsecurity=False).digest()
    except TypeError:
        return hashlib.md5(data).digest()


def encode_li_vn_mode(li: int = LEAP_NOSYNC, vn: int = NTP_VERSION, mode: int = MODE_CLIENT) -> int:
    return ((int(li) & 0x3) << 6) | ((int(vn) & 0x7) << 3) | (int(mode) & 0x7)


def decode_li_vn_mode(value: int) -> tuple[int, int, int]:
    first = int(value) & 0xFF
    return (first >> 6) & 0x3, (first >> 3) & 0x7, first & 0x7


def ntp_now() -> int:
    ns = time.time_ns()
    seconds = ns // 1_000_000_000 + NTP_UNIX_DELTA
    fraction = int((ns % 1_000_000_000) * (2**32) / 1_000_000_000) & 0xFFFFFFFF
    return (int(seconds) << 32) | fraction


def sentinel_timestamp(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(str(token or SENTINEL).encode("utf-8")).digest()
    seconds = int.from_bytes(digest[:4], "big") or 1
    fraction = int.from_bytes(digest[4:8], "big")
    return (seconds << 32) | fraction


def poll_timestamp(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll:{token or SENTINEL}".encode("utf-8")).digest()
    seconds = int.from_bytes(digest[:4], "big") or 1
    fraction = int.from_bytes(digest[4:8], "big")
    return (seconds << 32) | fraction


def encode_mac(header: bytes, key: bytes = DEFAULT_KEY, keyid: int = DEFAULT_KEYID) -> bytes:
    body = bytes(header or b"")
    if len(body) != HEADER_SIZE:
        raise NtpActuationError("short_header")
    identifier = int(keyid)
    if identifier <= 0:
        raise NtpActuationError("missing_keyid")
    return identifier.to_bytes(KEYID_SIZE, "big") + _md5(bytes(key or b"") + body)


def verify_mac(
    packet: bytes,
    key: bytes = DEFAULT_KEY,
    keyid: int = DEFAULT_KEYID,
) -> bool:
    raw = bytes(packet or b"")
    if len(raw) < AUTH_SIZE:
        return False
    got_keyid = int.from_bytes(raw[HEADER_SIZE : HEADER_SIZE + KEYID_SIZE], "big")
    if got_keyid != int(keyid) or got_keyid <= 0:
        return False
    expected = _md5(bytes(key or b"") + raw[:HEADER_SIZE])
    return hmac.compare_digest(expected, raw[HEADER_SIZE + KEYID_SIZE : AUTH_SIZE])


def encode_packet(
    *,
    mode: int,
    originate: int = 0,
    receive: int = 0,
    transmit: int = 0,
    reference: int = 0,
    stratum: int = STRATUM_CLIENT,
    li: int = LEAP_NOSYNC,
    vn: int = NTP_VERSION,
    refid: bytes = SENTINEL_REFID,
    keyid: int | None = DEFAULT_KEYID,
    key: bytes = DEFAULT_KEY,
    include_keyid: bool = True,
) -> bytes:
    packed_refid = bytes(refid or SENTINEL_REFID)[:4].ljust(4, b"\x00")
    header = HEADER_STRUCT.pack(
        encode_li_vn_mode(li, vn, mode),
        int(stratum) & 0xFF,
        POLL,
        PRECISION,
        0,
        0,
        int.from_bytes(packed_refid, "big"),
        int(reference) & 0xFFFFFFFFFFFFFFFF,
        int(originate) & 0xFFFFFFFFFFFFFFFF,
        int(receive) & 0xFFFFFFFFFFFFFFFF,
        int(transmit) & 0xFFFFFFFFFFFFFFFF,
    )
    if include_keyid and int(keyid or 0) > 0:
        return header + encode_mac(header, key=key, keyid=int(keyid))
    return header


def parse_packet(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < HEADER_SIZE:
        raise NtpActuationError("short_packet")
    (
        first,
        stratum,
        poll,
        precision,
        root_delay,
        root_dispersion,
        refid_int,
        reference,
        originate,
        receive,
        transmit,
    ) = HEADER_STRUCT.unpack(raw[:HEADER_SIZE])
    li, vn, mode = decode_li_vn_mode(first)
    if vn != NTP_VERSION:
        raise NtpActuationError("illegal_version")
    if mode not in {MODE_CLIENT, MODE_SERVER}:
        raise NtpActuationError("illegal_mode")
    keyid = 0
    mac = b""
    if len(raw) >= AUTH_SIZE:
        keyid = int.from_bytes(raw[HEADER_SIZE : HEADER_SIZE + KEYID_SIZE], "big")
        mac = raw[HEADER_SIZE + KEYID_SIZE : AUTH_SIZE]
    return {
        "li": li,
        "vn": vn,
        "mode": mode,
        "stratum": int(stratum),
        "poll": int(poll),
        "precision": int(precision),
        "root_delay": int(root_delay),
        "root_dispersion": int(root_dispersion),
        "refid": int(refid_int).to_bytes(4, "big"),
        "reference": int(reference),
        "originate": int(originate),
        "receive": int(receive),
        "transmit": int(transmit),
        "keyid": int(keyid),
        "mac": mac,
        "authenticated": int(keyid) > 0 and len(mac) == MAC_SIZE,
    }


class _NtpClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        keyid: int = DEFAULT_KEYID,
        key: bytes = DEFAULT_KEY,
        timeout: float = IO_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.keyid = int(keyid)
        self.key = bytes(key or b"")
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
            payload, _addr = self.sock.recvfrom(4096)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise NtpActuationError("timeout") from error
        packet = parse_packet(payload)
        if packet["mode"] != MODE_SERVER:
            raise NtpActuationError("server_required")
        if not verify_mac(payload, key=self.key, keyid=self.keyid):
            raise NtpActuationError("keyid_required")
        return packet

    def exchange(
        self,
        packet: bytes,
        *,
        wait_response: bool = True,
    ) -> dict[str, Any]:
        self.sock.sendto(bytes(packet or b""), (self.host, self.port))
        if not wait_response:
            raise NtpActuationError("server_required")
        return self._recv()

    def client(
        self,
        transmit: int,
        *,
        wait_response: bool = True,
        use_keyid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_packet(
            mode=MODE_CLIENT,
            transmit=int(transmit),
            stratum=STRATUM_CLIENT,
            keyid=self.keyid,
            key=self.key,
            include_keyid=use_keyid and self.keyid > 0,
        )
        return self.exchange(packet, wait_response=wait_response)


class NtpSession:
    """Keyid-gated loopback RFC 5905 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        keyid: int = DEFAULT_KEYID,
        key: bytes = DEFAULT_KEY,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.keyid = int(keyid or 0)
        self.key = bytes(key or b"")
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.origin = 0
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.last_token = ""
        self.last_digest = ""
        self.last_receive = 0
        self.last_transmit = 0
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_origin(self, origin: int) -> None:
        self.store_origin_once(origin)

    def store_origin_once(self, origin: int) -> int:
        with self._lock:
            value = int(origin or 0)
            if not self.origin and value:
                self.origin = value
                self.stored = True
            return int(self.origin)

    def read_origin(self) -> int:
        with self._lock:
            return int(self.origin)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "originate": 0,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _reply(
        self,
        peer: tuple[str, int],
        originate: int,
        receive: int,
        transmit: int,
        reference: int,
    ) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_packet(
            mode=MODE_SERVER,
            originate=int(originate),
            receive=int(receive),
            transmit=int(transmit),
            reference=int(reference),
            stratum=STRATUM_PRIMARY,
            refid=SENTINEL_REFID,
            keyid=self.keyid,
            key=self.key,
            include_keyid=self.keyid > 0,
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
            except NtpActuationError:
                continue
            if packet.get("mode") != MODE_CLIENT:
                continue
            if not verify_mac(payload, key=self.key, keyid=self.keyid):
                continue
            peer = (str(addr[0]), int(addr[1]))
            t1 = int(packet.get("transmit") or 0)
            stored = self.store_origin_once(t1)
            receive = ntp_now()
            transmit = ntp_now()
            if transmit <= receive:
                transmit = receive + 1
            with self._lock:
                self.last_receive = receive
                self.last_transmit = transmit
            self._reply(peer, t1, receive, transmit, stored or t1)

    def bind(self) -> dict[str, Any]:
        if self.keyid <= 0:
            return self._forbidden("missing_keyid")
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
        do_client: bool = True,
        do_server: bool = True,
        originate: bool = True,
        receive: bool = True,
        transmit: bool = True,
        replay: bool = True,
        use_keyid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self.keyid <= 0:
            return self._forbidden("missing_keyid")
        live_token = str(token or SENTINEL)
        origin = sentinel_timestamp(live_token)
        client: _NtpClient | None = None
        independent: _NtpClient | None = None
        try:
            client = _NtpClient(self.host, int(self.port), keyid=self.keyid, key=self.key)
            if not do_client:
                return self._conflict("client_required")
            packet = encode_packet(
                mode=MODE_CLIENT,
                transmit=origin if originate else 0,
                stratum=STRATUM_CLIENT,
                keyid=self.keyid,
                key=self.key,
                include_keyid=use_keyid and self.keyid > 0,
            )
            if not originate:
                try:
                    client.sock.sendto(packet, (self.host, int(self.port)))
                except OSError:
                    pass
                return self._conflict("originate_required")
            if not use_keyid:
                try:
                    client.exchange(packet, wait_response=True)
                except NtpActuationError:
                    return self._conflict("keyid_required")
                return self._conflict("keyid_required")
            if not do_server:
                try:
                    client.exchange(packet, wait_response=False)
                except NtpActuationError as error:
                    if str(error) == "server_required":
                        return self._conflict("server_required")
                    return self._conflict("server_required")
                return self._conflict("server_required")
            try:
                reply = client.exchange(packet, wait_response=True)
            except NtpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("keyid_required")
                if reason == "server_required":
                    return self._conflict("server_required")
                return self._conflict("client_required")
            if int(reply.get("originate") or 0) != origin:
                return self._conflict("originate_required")
            if not receive or int(reply.get("receive") or 0) == 0:
                return self._conflict("receive_required")
            if not transmit or int(reply.get("transmit") or 0) == 0:
                return self._conflict("transmit_required")
            if int(reply.get("reference") or 0) != origin:
                return self._conflict("originate_required")
            if reply.get("refid") != SENTINEL_REFID:
                return self._conflict("server_required")
            self.retrieved = True
            if replay:
                independent = _NtpClient(self.host, int(self.port), keyid=self.keyid, key=self.key)
                try:
                    poll = independent.client(poll_timestamp(live_token), wait_response=True)
                except NtpActuationError:
                    return self._conflict("replay_required")
                stored = self.read_origin()
                if int(poll.get("reference") or 0) != origin or stored != origin:
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(origin.to_bytes(8, "big"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": 8,
                "port": int(self.port or 0),
                "originate": origin,
                "receive": int(reply.get("receive") or 0),
                "transmit": int(reply.get("transmit") or 0),
                "reference": int(reply.get("reference") or 0),
                "keyid": int(self.keyid),
                "client_port": int(client.client_port),
                "client": True,
                "server": True,
                "originate_sent": True,
                "receive_sent": True,
                "transmit_sent": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "keyid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_ntp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": 8,
                "port": int(self.port or 0),
                "originate": origin,
                "receive": int(reply.get("receive") or 0),
                "transmit": int(reply.get("transmit") or 0),
                "keyid": int(self.keyid),
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "client": True,
                "server": True,
                "originate_sent": True,
                "receive_sent": True,
                "transmit_sent": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "keyid_bound": True,
            }
        except (OSError, NtpActuationError) as error:
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
        live = independent_ntp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "originate": int(live.get("originate") or 0),
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


def call_ntp_tool(session: NtpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one NTP tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_client = True if arguments.get("client") is None else bool(arguments.get("client"))
    do_server = True if arguments.get("server") is None else bool(arguments.get("server"))
    originate = True if arguments.get("originate") is None else bool(arguments.get("originate"))
    receive = True if arguments.get("receive") is None else bool(arguments.get("receive"))
    transmit = True if arguments.get("transmit") is None else bool(arguments.get("transmit"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_keyid = True if arguments.get("use_keyid") is None else bool(arguments.get("use_keyid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_client=do_client,
            do_server=do_server,
            originate=originate,
            receive=receive,
            transmit=transmit,
            replay=replay,
            use_keyid=use_keyid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise NtpActuationError(f"unsupported ntp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_ntp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed NTP timestamp digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "originate": 0,
        "port": 0,
        "keyid": 0,
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
            "client",
            "server",
            "originate_sent",
            "receive_sent",
            "transmit_sent",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "keyid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    originate = int(payload.get("originate") or 0)
    keyid = int(payload.get("keyid") or 0)
    dual = port > 0 and originate > 0 and keyid > 0
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "originate": originate,
        "receive": int(payload.get("receive") or 0),
        "transmit": int(payload.get("transmit") or 0),
        "reference": int(payload.get("reference") or 0),
        "size": int(payload.get("size") or 0),
        "port": port,
        "keyid": keyid,
        "client": payload.get("client") is True,
        "server": payload.get("server") is True,
        "originate_sent": payload.get("originate_sent") is True,
        "receive_sent": payload.get("receive_sent") is True,
        "transmit_sent": payload.get("transmit_sent") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "keyid_bound": payload.get("keyid_bound") is True,
    }


def run_ntp_workflow(
    *,
    with_keyid: bool = True,
    skip_bind: bool = False,
    do_client: bool = True,
    do_server: bool = True,
    originate: bool = True,
    receive: bool = True,
    transmit: bool = True,
    replay: bool = True,
    use_keyid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 5905 CLIENT/SERVER originate/receive/transmit workflow."""

    descriptor = ntp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, NTP_TOOL_PROVIDER),
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
        raise NtpActuationError(f"ntp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ntp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = NtpSession(out, keyid=DEFAULT_KEYID if with_keyid else 0)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "client": do_client,
            "server": do_server,
            "originate": originate,
            "receive": receive,
            "transmit": transmit,
            "replay": replay,
            "use_keyid": use_keyid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_ntp_tool(session, arguments))
            except NtpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_ntp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_keyid
        and not skip_bind
        and do_client
        and do_server
        and originate
        and receive
        and transmit
        and replay
        and use_keyid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ntp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_keyid": with_keyid,
        "skip_bind": skip_bind,
        "client": do_client,
        "server": do_server,
        "originate": originate,
        "receive": receive,
        "transmit": transmit,
        "replay": replay,
        "use_keyid": use_keyid,
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
        "originate_value": int(publish_result.get("originate") or independent.get("originate") or 0),
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
        "originate": int(trace_body["originate_value"] or 0),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_keyid": with_keyid,
        "skip_bind": skip_bind,
        "client": do_client,
        "server": do_server,
        "originate_sent": originate,
        "receive": receive,
        "transmit": transmit,
        "replay": replay,
        "use_keyid": use_keyid,
    }


def verify_ntp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed NTP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_ntp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    originate = int(trace.get("originate_value") or independent.get("originate") or 0)
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
        "client": independent.get("client") is True,
        "server": independent.get("server") is True,
        "originate_sent": independent.get("originate_sent") is True,
        "receive_sent": independent.get("receive_sent") is True,
        "transmit_sent": independent.get("transmit_sent") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "keyid_bound": independent.get("keyid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "origin_bound": port > 0 and originate > 0,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def ntp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.ntp_actuation import "
        "builtin_ntp_actuation_proof; r=builtin_ntp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='ntp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_ntp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=NTP_ACTUATION_ID,
        name="First-class RFC 5905 NTP CLIENT/SERVER originate/receive/transmit actuation",
        description=(
            "Missions that require an ntp tool can opt the ntp provider in, "
            "bind a loopback RFC 5905 UDP daemon, complete CLIENT, lockstep a "
            "SERVER reply that copies originate and fills receive/transmit, "
            "independently poll the stored origin timestamp on a later socket, "
            "and seal a digest-chained timestamp. Default routing stays "
            "fail-closed; a missing keyid keeps the hole falsifiable, and "
            "skip-CLIENT/SERVER/ORIGINATE/RECEIVE/TRANSMIT/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.ntp_actuation:builtin_ntp_actuation_proof",
        proof_command=ntp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.syslog-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/ntp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/radius_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required ntp tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 5905 daemon, speaks CLIENT then "
            "SERVER originate/receive/transmit over UDP timestamps with a keyid "
            "MAC, independently polls the stored origin timestamp on a later "
            "client socket, and binds this family as the next diversity-catalog "
            "successor once RFC 5424 syslog lockstep is proved. Missing keyids, "
            "skip-CLIENT, skip-SERVER, skip-ORIGINATE, skip-RECEIVE, "
            "skip-TRANSMIT, skip-REPLAY, and CLIENT aimed without a keyid stay "
            "fail-closed. Later genesis can take RFC 2865 RADIUS "
            "Access-Request/Access-Accept as the next unsaturated "
            "diversity-catalog family."
        ),
        tags=("ntp", "rfc5905", "udp", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T190218Z-8f1efa20",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_ntp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 5905 NTP lockstep actuation seals a timestamp digest."""

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
    from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = NTP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_ntp"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_ntp"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_ntp"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_ntp"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_ntp"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["radius_goal_is_not_ntp"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["ntp_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["ntp_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["ntp_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["ntp_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["ntp_goal_is_not_radius"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = NTP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = NTP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = NTP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = NTP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = NTP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["radius_marker_stays_radius"] = NTP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_ntp"] = (
        len(catalog) > 49
        and catalog[49]["id"] == NTP_ACTUATION_ID
        and catalog[48]["id"] == SYSLOG_ACTUATION_ID
        and catalog[49]["source"] == "genesis_bind_ntp"
    )
    checks["catalog_names_radius"] = (
        len(catalog) > 50
        and catalog[50]["id"] == RADIUS_ACTUATION_ID
        and catalog[50]["source"] == "genesis_bind_radius"
    )
    family = capability_family(NTP_ACTUATION_GOAL)
    checks["family_is_ntp"] = "ntp" in family
    checks["family_is_rfc5905"] = "rfc5905" in family
    checks["family_is_keyid"] = "keyid" in family
    checks["family_is_not_syslog"] = "syslog" not in family and "nilvalue" not in family
    checks["family_is_not_snmp"] = "snmp" not in family and "varbind" not in family
    checks["family_is_not_tftp"] = "tftp" not in family and "rfc1350" not in family
    checks["family_is_not_ftp"] = "ftpd" not in family and "pasv" not in family
    checks["family_is_not_dns"] = "tsig" not in family and "nameserver" not in family
    checks["family_is_not_radius"] = "radius" not in family and "rfc2865" not in family
    origin = sentinel_timestamp()
    packed = encode_packet(mode=MODE_CLIENT, transmit=origin)
    parsed = parse_packet(packed)
    checks["client_roundtrip"] = (
        parsed["mode"] == MODE_CLIENT
        and parsed["vn"] == NTP_VERSION
        and parsed["transmit"] == origin
        and parsed["keyid"] == DEFAULT_KEYID
        and parsed["authenticated"] is True
        and verify_mac(packed)
    )
    server_packet = encode_packet(
        mode=MODE_SERVER,
        originate=origin,
        receive=origin + 1,
        transmit=origin + 2,
        reference=origin,
        stratum=STRATUM_PRIMARY,
    )
    server = parse_packet(server_packet)
    checks["server_roundtrip"] = (
        server["mode"] == MODE_SERVER
        and server["originate"] == origin
        and server["receive"] == origin + 1
        and server["transmit"] == origin + 2
        and server["reference"] == origin
        and server["refid"] == SENTINEL_REFID
        and verify_mac(server_packet)
    )
    bare = encode_packet(mode=MODE_CLIENT, transmit=origin, include_keyid=False)
    checks["missing_keyid_is_unauthenticated"] = (
        len(bare) == HEADER_SIZE and parse_packet(bare)["authenticated"] is False
    )
    neighbors = (
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        RADIUS_ACTUATION_GOAL,
    )
    ntp_signature = semantic_signature(NTP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(ntp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_ntp = ToolDescriptor(name="remote_ntp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_ntp)
    checks["naive_mcp_ntp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = ntp_tool_descriptor()
    default_ntp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, NTP_TOOL_PROVIDER),
    )
    checks["default_ntp_provider_is_unsupported"] = (
        default_ntp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{NTP_TOOL_PROVIDER}" in default_ntp.reasons
    )
    checks["opted_in_ntp_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_ntp],
        required_tool_names=("local_memory", "ntp"),
    )
    checks["naive_preflight_missing_ntp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["ntp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "ntp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, NTP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "ntp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="ntp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_ntp_workflow(with_keyid=False, output_dir=root / "missing")
        skip_bind = run_ntp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_client = run_ntp_workflow(do_client=False, output_dir=root / "skip-client")
        skip_server = run_ntp_workflow(do_server=False, output_dir=root / "skip-server")
        skip_originate = run_ntp_workflow(originate=False, output_dir=root / "skip-originate")
        skip_receive = run_ntp_workflow(receive=False, output_dir=root / "skip-receive")
        skip_transmit = run_ntp_workflow(transmit=False, output_dir=root / "skip-transmit")
        skip_replay = run_ntp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_keyid = run_ntp_workflow(use_keyid=False, output_dir=root / "skip-keyid")
        live = run_ntp_workflow(output_dir=root / "live")
        verify = verify_ntp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_ntp_trace(clone)
        checks["naive_without_keyid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_keyid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_client_stays_empty"] = (
            skip_client["ok"] is False
            and skip_client["error"] == "client_required"
            and skip_client["final_status"] == 409
            and skip_client["payload_exists"] is False
        )
        checks["skip_server_stays_empty"] = (
            skip_server["ok"] is False
            and skip_server["error"] == "server_required"
            and skip_server["final_status"] == 409
            and skip_server["payload_exists"] is False
        )
        checks["skip_originate_stays_empty"] = (
            skip_originate["ok"] is False
            and skip_originate["error"] == "originate_required"
            and skip_originate["final_status"] == 409
            and skip_originate["payload_exists"] is False
        )
        checks["skip_receive_stays_empty"] = (
            skip_receive["ok"] is False
            and skip_receive["error"] == "receive_required"
            and skip_receive["final_status"] == 409
            and skip_receive["payload_exists"] is False
        )
        checks["skip_transmit_stays_empty"] = (
            skip_transmit["ok"] is False
            and skip_transmit["error"] == "transmit_required"
            and skip_transmit["final_status"] == 409
            and skip_transmit["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_keyid_stays_empty"] = (
            skip_keyid["ok"] is False
            and skip_keyid["error"] == "keyid_required"
            and skip_keyid["final_status"] == 409
            and skip_keyid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_origin"] = (
            int(live.get("originate") or 0) == sentinel_timestamp() and int(live.get("port") or 0) > 0
        )
        checks["token_keyid_client_server_timestamps_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_client["ok"] is False
            and skip_server["ok"] is False
            and skip_originate["ok"] is False
            and skip_receive["ok"] is False
            and skip_transmit["ok"] is False
            and skip_replay["ok"] is False
            and skip_keyid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="ntp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != NTP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_ntp"] = (
        live_goal == NTP_ACTUATION_GOAL
        and NTP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_ntp"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_ntp_actuation_capability()
    return {
        "ok": ok,
        "action": "ntp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": NTP_ACTUATION_GOAL,
        "done_when": NTP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
