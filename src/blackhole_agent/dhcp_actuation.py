"""Drive a first-class DHCP tool through RFC 2131 DISCOVER/OFFER/ACK.

Tool routing already fails missions that require ``dhcp``: hosted DHCP
plugins stay on the unsupported MCP provider, and no first-party DHCP
provider is executable. Unbound therefore cannot speak DISCOVER, lockstep an
OFFER/ACK xid exchange over UDP BOOTP, independently poll the stored yiaddr
lease, or seal a lease digest an independent later reader can re-open.

This module closes that hole:

- advertise a ``dhcp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2131 daemon
- keep a missing-xid client so the transaction-id hole stays falsifiable
- refuse OFFER/ACK until DISCOVER lands with a non-zero xid
- independently poll the stored yiaddr lease on a later client socket
- persist a sealed lease digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RADIUS
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
from typing import Any, Mapping, Sequence

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
    DHCP_TOOL_PROVIDER,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    dhcp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
DHCP_ACTUATION_ID = "capability.dhcp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-DHCP-OK"
POLL_TOKEN = "BH-DHCP-POLL"
DEFAULT_YIADDR = "192.0.2.10"
DEFAULT_SERVER = "192.0.2.1"
DEFAULT_LEASE = 3600
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
BOOTP_FIXED = 236
MAGIC = b"\x63\x82\x53\x63"
BOOTREQUEST = 1
BOOTREPLY = 2
HTYPE_ETHER = 1
HLEN_ETHER = 6
DHCPDISCOVER = 1
DHCPOFFER = 2
DHCPACK = 5
OPT_HOSTNAME = 12
OPT_LEASE_TIME = 51
OPT_SERVER_ID = 54
OPT_MSG_TYPE = 53
OPT_CLIENT_ID = 61
OPT_PAD = 0
OPT_END = 255
HEADER_STRUCT = struct.Struct("!BBBBIHH4s4s4s4s16s64s128s")

DHCP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DHCP_ACTUATION_ID};"
    f"capability_proved:{DHCP_ACTUATION_ID};"
    "no_skill_route"
)
DHCP_ACTUATION_GOAL = (
    "Repair rfc2131 dhcp discover/offer/ack cycle cannot land over udp "
    "bootp: hosted dhcp tools remain unsupported so a DISCOVER then OFFER "
    "then ACK xid exchange cannot land and a sealed lease digest cannot be "
    "produced. A missing dhcp xid stays forbidden; fail-closed routing never "
    "opts the dhcp provider in. An independent later poll of the stored "
    "yiaddr lease keeps the hole falsifiable."
)


class DhcpActuationError(RuntimeError):
    """Raised when the DHCP session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_xid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(str(token or SENTINEL).encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_xid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


DEFAULT_XID = request_xid(SENTINEL)


def client_chaddr(token: str = SENTINEL) -> bytes:
    digest = hashlib.sha256(f"chaddr:{token or SENTINEL}".encode("utf-8")).digest()
    return b"\x02" + digest[:5]


def encode_options(options: Sequence[tuple[int, bytes]]) -> bytes:
    chunks = [MAGIC]
    for code, value in options:
        raw = bytes(value or b"")
        if len(raw) > 255:
            raise DhcpActuationError("option_too_long")
        chunks.append(bytes((int(code) & 0xFF, len(raw))) + raw)
    chunks.append(bytes((OPT_END,)))
    return b"".join(chunks)


def parse_options(data: bytes) -> list[tuple[int, bytes]]:
    raw = bytes(data or b"")
    if len(raw) < 4 or raw[:4] != MAGIC:
        raise DhcpActuationError("missing_cookie")
    options: list[tuple[int, bytes]] = []
    offset = 4
    while offset < len(raw):
        code = raw[offset]
        if code == OPT_END:
            break
        if code == OPT_PAD:
            offset += 1
            continue
        if offset + 2 > len(raw):
            raise DhcpActuationError("short_option")
        length = raw[offset + 1]
        if offset + 2 + length > len(raw):
            raise DhcpActuationError("illegal_option")
        options.append((code, raw[offset + 2 : offset + 2 + length]))
        offset += 2 + length
    return options


def option_value(options: Sequence[tuple[int, bytes]], code: int) -> bytes:
    for opt_code, value in options:
        if int(opt_code) == int(code):
            return bytes(value or b"")
    return b""


def encode_packet(
    *,
    op: int,
    xid: int,
    msg_type: int,
    hostname: str = "",
    yiaddr: str = "0.0.0.0",
    siaddr: str = "0.0.0.0",
    chaddr: bytes | None = None,
    include_xid: bool = True,
) -> bytes:
    live_xid = int(xid) & 0xFFFFFFFF if include_xid else 0
    mac = bytes(chaddr or client_chaddr(hostname or SENTINEL))
    if len(mac) < 16:
        mac = mac + b"\x00" * (16 - len(mac))
    options: list[tuple[int, bytes]] = [
        (OPT_MSG_TYPE, bytes((int(msg_type) & 0xFF,))),
    ]
    name = str(hostname or "")
    if name:
        encoded = name.encode("utf-8")
        options.append((OPT_HOSTNAME, encoded))
        options.append((OPT_CLIENT_ID, encoded))
    if int(msg_type) in {DHCPOFFER, DHCPACK}:
        options.append((OPT_LEASE_TIME, int(DEFAULT_LEASE).to_bytes(4, "big")))
        options.append((OPT_SERVER_ID, socket.inet_aton(siaddr or DEFAULT_SERVER)))
    header = HEADER_STRUCT.pack(
        int(op) & 0xFF,
        HTYPE_ETHER,
        HLEN_ETHER,
        0,
        live_xid,
        0,
        0x8000,
        socket.inet_aton("0.0.0.0"),
        socket.inet_aton(yiaddr or "0.0.0.0"),
        socket.inet_aton(siaddr or "0.0.0.0"),
        socket.inet_aton("0.0.0.0"),
        mac[:16],
        b"\x00" * 64,
        b"\x00" * 128,
    )
    return header + encode_options(options)


def encode_discover(
    *,
    xid: int,
    hostname: str,
    include_xid: bool = True,
) -> bytes:
    return encode_packet(
        op=BOOTREQUEST,
        xid=xid,
        msg_type=DHCPDISCOVER,
        hostname=hostname,
        include_xid=include_xid,
        chaddr=client_chaddr(hostname),
    )


def encode_offer(
    *,
    xid: int,
    hostname: str,
    yiaddr: str = DEFAULT_YIADDR,
    include_xid: bool = True,
) -> bytes:
    return encode_packet(
        op=BOOTREPLY,
        xid=xid,
        msg_type=DHCPOFFER,
        hostname=hostname,
        yiaddr=yiaddr,
        siaddr=DEFAULT_SERVER,
        include_xid=include_xid,
        chaddr=client_chaddr(hostname),
    )


def encode_ack(
    *,
    xid: int,
    hostname: str,
    yiaddr: str = DEFAULT_YIADDR,
    include_xid: bool = True,
) -> bytes:
    return encode_packet(
        op=BOOTREPLY,
        xid=xid,
        msg_type=DHCPACK,
        hostname=hostname,
        yiaddr=yiaddr,
        siaddr=DEFAULT_SERVER,
        include_xid=include_xid,
        chaddr=client_chaddr(hostname),
    )


def parse_packet(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < BOOTP_FIXED + 4:
        raise DhcpActuationError("short_packet")
    unpacked = HEADER_STRUCT.unpack(raw[:BOOTP_FIXED])
    op, htype, hlen, _hops, xid, _secs, _flags, _ci, yi, si, _gi, chaddr, _sname, _file = unpacked
    if int(op) not in {BOOTREQUEST, BOOTREPLY}:
        raise DhcpActuationError("illegal_op")
    if int(htype) != HTYPE_ETHER or int(hlen) != HLEN_ETHER:
        raise DhcpActuationError("illegal_htype")
    options = parse_options(raw[BOOTP_FIXED:])
    msg_raw = option_value(options, OPT_MSG_TYPE)
    if not msg_raw:
        raise DhcpActuationError("missing_msg_type")
    hostname = option_value(options, OPT_HOSTNAME).decode("utf-8", errors="replace")
    yiaddr = socket.inet_ntoa(bytes(yi))
    return {
        "op": int(op),
        "xid": int(xid),
        "yiaddr": yiaddr,
        "siaddr": socket.inet_ntoa(bytes(si)),
        "chaddr": bytes(chaddr),
        "msg_type": int(msg_raw[0]),
        "hostname": hostname,
        "has_hostname": bool(hostname),
        "has_xid": int(xid) != 0,
        "options": options,
    }


class _DhcpClient:
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

    def _recv(self, expected_type: int, xid: int) -> dict[str, Any]:
        try:
            payload, _addr = self.sock.recvfrom(4096)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise DhcpActuationError("timeout") from error
        packet = parse_packet(payload)
        if packet["msg_type"] != int(expected_type):
            if int(expected_type) == DHCPOFFER:
                raise DhcpActuationError("offer_required")
            raise DhcpActuationError("ack_required")
        if int(xid) and packet["xid"] != int(xid):
            raise DhcpActuationError("xid_required")
        if not packet["has_xid"]:
            raise DhcpActuationError("xid_required")
        return packet

    def exchange(
        self,
        packet: bytes,
        xid: int,
        *,
        wait_offer: bool = True,
        wait_ack: bool = True,
    ) -> dict[str, Any]:
        self.sock.sendto(bytes(packet or b""), (self.host, self.port))
        if not wait_offer:
            raise DhcpActuationError("offer_required")
        offer = self._recv(DHCPOFFER, xid)
        if not wait_ack:
            raise DhcpActuationError("ack_required")
        ack = self._recv(DHCPACK, xid)
        if str(ack.get("yiaddr") or "") != str(offer.get("yiaddr") or ""):
            raise DhcpActuationError("ack_required")
        return {
            "offer": offer,
            "ack": ack,
            "xid": int(ack.get("xid") or 0),
            "yiaddr": str(ack.get("yiaddr") or ""),
            "hostname": str(ack.get("hostname") or offer.get("hostname") or ""),
        }

    def discover(
        self,
        hostname: str,
        xid: int,
        *,
        wait_offer: bool = True,
        wait_ack: bool = True,
        include_xid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_discover(xid=xid, hostname=hostname, include_xid=include_xid)
        return self.exchange(packet, xid if include_xid else 0, wait_offer=wait_offer, wait_ack=wait_ack)


class DhcpSession:
    """Xid-gated loopback RFC 2131 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        xid_gate: int = DEFAULT_XID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.xid_gate = int(xid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.hostname = ""
        self.yiaddr = ""
        self.lease_xid = 0
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

    def store_lease_once(self, hostname: str, yiaddr: str, xid: int) -> tuple[str, str, int]:
        with self._lock:
            name = str(hostname or "")
            address = str(yiaddr or DEFAULT_YIADDR)
            if not self.hostname and name:
                self.hostname = name
                self.yiaddr = address
                self.lease_xid = int(xid)
                self.stored = True
            return str(self.hostname), str(self.yiaddr), int(self.lease_xid)

    def read_lease(self) -> tuple[str, str, int]:
        with self._lock:
            return str(self.hostname), str(self.yiaddr), int(self.lease_xid)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "yiaddr": "",
            "xid": 0,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _reply(self, peer: tuple[str, int], xid: int, hostname: str, yiaddr: str) -> None:
        sock = self.sock
        if sock is None:
            return
        offer = encode_offer(xid=xid, hostname=hostname, yiaddr=yiaddr)
        ack = encode_ack(xid=xid, hostname=hostname, yiaddr=yiaddr)
        try:
            sock.sendto(offer, peer)
            sock.sendto(ack, peer)
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
            except DhcpActuationError:
                continue
            if packet.get("op") != BOOTREQUEST:
                continue
            if packet.get("msg_type") != DHCPDISCOVER:
                continue
            if not packet.get("has_xid"):
                continue
            hostname = str(packet.get("hostname") or "")
            if not hostname:
                continue
            stored_name, stored_yiaddr, stored_xid = self.store_lease_once(
                hostname,
                DEFAULT_YIADDR,
                int(packet.get("xid") or 0),
            )
            peer = (str(addr[0]), int(addr[1]))
            reply_xid = int(packet.get("xid") or stored_xid)
            self._reply(peer, reply_xid, stored_name, stored_yiaddr)

    def bind(self) -> dict[str, Any]:
        if not self.xid_gate:
            return self._forbidden("missing_xid")
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
        do_discover: bool = True,
        do_offer: bool = True,
        do_ack: bool = True,
        replay: bool = True,
        use_xid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.xid_gate:
            return self._forbidden("missing_xid")
        live_token = str(token or SENTINEL)
        origin_xid = request_xid(live_token)
        client: _DhcpClient | None = None
        independent: _DhcpClient | None = None
        try:
            client = _DhcpClient(self.host, int(self.port))
            if not do_discover:
                return self._conflict("discover_required")
            packet = encode_discover(
                xid=origin_xid,
                hostname=live_token,
                include_xid=use_xid,
            )
            if not use_xid:
                try:
                    client.exchange(packet, origin_xid, wait_offer=True, wait_ack=True)
                except DhcpActuationError:
                    return self._conflict("xid_required")
                return self._conflict("xid_required")
            if not do_offer:
                try:
                    client.exchange(packet, origin_xid, wait_offer=False, wait_ack=False)
                except DhcpActuationError as error:
                    if str(error) == "offer_required":
                        return self._conflict("offer_required")
                    return self._conflict("offer_required")
                return self._conflict("offer_required")
            if not do_ack:
                try:
                    client.exchange(packet, origin_xid, wait_offer=True, wait_ack=False)
                except DhcpActuationError as error:
                    if str(error) == "ack_required":
                        return self._conflict("ack_required")
                    return self._conflict("ack_required")
                return self._conflict("ack_required")
            try:
                reply = client.exchange(packet, origin_xid, wait_offer=True, wait_ack=True)
            except DhcpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("xid_required")
                if reason == "offer_required":
                    return self._conflict("offer_required")
                if reason == "ack_required":
                    return self._conflict("ack_required")
                return self._conflict("discover_required")
            if str(reply.get("hostname") or "") != live_token:
                return self._conflict("discover_required")
            if str(reply.get("yiaddr") or "") != DEFAULT_YIADDR:
                return self._conflict("ack_required")
            self.retrieved = True
            if replay:
                independent = _DhcpClient(self.host, int(self.port))
                try:
                    poll = independent.discover(
                        POLL_TOKEN,
                        poll_xid(live_token),
                        wait_offer=True,
                        wait_ack=True,
                    )
                except DhcpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_yiaddr, _stored_xid = self.read_lease()
                if (
                    str(poll.get("hostname") or "") != live_token
                    or stored_name != live_token
                    or stored_yiaddr != DEFAULT_YIADDR
                    or str(poll.get("yiaddr") or "") != DEFAULT_YIADDR
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{DEFAULT_YIADDR}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "yiaddr": DEFAULT_YIADDR,
                "xid": origin_xid,
                "discover": True,
                "offer": True,
                "ack": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "xid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_dhcp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "yiaddr": DEFAULT_YIADDR,
                "xid": origin_xid,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "discover": True,
                "offer": True,
                "ack": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "xid_bound": True,
            }
        except (OSError, DhcpActuationError) as error:
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
        live = independent_dhcp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "yiaddr": str(live.get("yiaddr") or ""),
            "xid": int(live.get("xid") or 0),
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


def call_dhcp_tool(session: DhcpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one DHCP tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_discover = True if arguments.get("discover") is None else bool(arguments.get("discover"))
    do_offer = True if arguments.get("offer") is None else bool(arguments.get("offer"))
    do_ack = True if arguments.get("ack") is None else bool(arguments.get("ack"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_xid = True if arguments.get("use_xid") is None else bool(arguments.get("use_xid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_discover=do_discover,
            do_offer=do_offer,
            do_ack=do_ack,
            replay=replay,
            use_xid=use_xid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise DhcpActuationError(f"unsupported dhcp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_dhcp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed DHCP lease digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "yiaddr": "",
        "port": 0,
        "xid": 0,
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
            "discover",
            "offer",
            "ack",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "xid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    yiaddr = str(payload.get("yiaddr") or "")
    xid = int(payload.get("xid") or 0)
    dual = port > 0 and bool(yiaddr) and xid > 0
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "yiaddr": yiaddr,
        "size": int(payload.get("size") or 0),
        "port": port,
        "xid": xid,
        "discover": payload.get("discover") is True,
        "offer": payload.get("offer") is True,
        "ack": payload.get("ack") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "xid_bound": payload.get("xid_bound") is True,
    }


def run_dhcp_workflow(
    *,
    with_xid: bool = True,
    skip_bind: bool = False,
    do_discover: bool = True,
    do_offer: bool = True,
    do_ack: bool = True,
    replay: bool = True,
    use_xid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2131 DISCOVER/OFFER/ACK workflow."""

    descriptor = dhcp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DHCP_TOOL_PROVIDER),
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
        raise DhcpActuationError(f"dhcp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="dhcp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = DhcpSession(out, xid_gate=DEFAULT_XID if with_xid else 0)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "discover": do_discover,
            "offer": do_offer,
            "ack": do_ack,
            "replay": replay,
            "use_xid": use_xid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_dhcp_tool(session, arguments))
            except DhcpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_dhcp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_xid
        and not skip_bind
        and do_discover
        and do_offer
        and do_ack
        and replay
        and use_xid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "dhcp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_xid": with_xid,
        "skip_bind": skip_bind,
        "discover": do_discover,
        "offer": do_offer,
        "ack": do_ack,
        "replay": replay,
        "use_xid": use_xid,
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
        "yiaddr_value": str(publish_result.get("yiaddr") or independent.get("yiaddr") or ""),
        "xid_value": int(publish_result.get("xid") or independent.get("xid") or 0),
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
        "yiaddr": str(trace_body["yiaddr_value"] or ""),
        "xid": int(trace_body["xid_value"] or 0),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_xid": with_xid,
        "skip_bind": skip_bind,
        "discover": do_discover,
        "offer": do_offer,
        "ack": do_ack,
        "replay": replay,
        "use_xid": use_xid,
    }


def verify_dhcp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed DHCP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_dhcp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    yiaddr = str(trace.get("yiaddr_value") or independent.get("yiaddr") or "")
    xid = int(trace.get("xid_value") or independent.get("xid") or 0)
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
        "discover": independent.get("discover") is True,
        "offer": independent.get("offer") is True,
        "ack": independent.get("ack") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "xid_bound": independent.get("xid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "yiaddr_bound": port > 0 and yiaddr == DEFAULT_YIADDR and xid > 0,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def dhcp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.dhcp_actuation import "
        "builtin_dhcp_actuation_proof; r=builtin_dhcp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='dhcp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_dhcp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=DHCP_ACTUATION_ID,
        name="First-class RFC 2131 DHCP DISCOVER/OFFER/ACK actuation",
        description=(
            "Missions that require a dhcp tool can opt the dhcp provider in, "
            "bind a loopback RFC 2131 UDP BOOTP daemon, complete DISCOVER with a "
            "non-zero xid, lockstep an OFFER then ACK that carries the stored "
            "yiaddr lease, independently poll the stored yiaddr on a later "
            "socket, and seal a digest-chained lease. Default routing stays "
            "fail-closed; a missing xid keeps the hole falsifiable, and "
            "skip-DISCOVER/OFFER/ACK/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.dhcp_actuation:builtin_dhcp_actuation_proof",
        proof_command=dhcp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.radius-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/dhcp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/ike_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required dhcp tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 2131 daemon, speaks DISCOVER then "
            "OFFER then ACK over UDP BOOTP with a non-zero xid, independently "
            "polls the stored yiaddr lease on a later client socket, and binds "
            "this family as the next diversity-catalog successor once RFC 2865 "
            "RADIUS lockstep is proved. Missing xids, skip-DISCOVER, skip-OFFER, "
            "skip-ACK, skip-REPLAY, and DISCOVER aimed without an xid stay "
            "fail-closed. Later genesis can take RFC 7296 IKE SA_INIT/AUTH as "
            "the next unsaturated diversity-catalog family."
        ),
        tags=("dhcp", "rfc2131", "udp", "bootp", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T202754Z-2d2889a0",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_dhcp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2131 DHCP lockstep actuation seals a lease digest."""

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
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = DHCP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    checks["radius_goal_is_not_dhcp"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_dhcp"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_dhcp"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_dhcp"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_dhcp"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_dhcp"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_dhcp"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["ike_goal_is_not_dhcp"] = leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    checks["dhcp_goal_is_not_radius"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["dhcp_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["dhcp_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["dhcp_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["dhcp_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["dhcp_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["dhcp_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["dhcp_goal_is_not_ike"] = IKE_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["radius_marker_stays_radius"] = DHCP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["ntp_marker_stays_ntp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = DHCP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = DHCP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["ike_marker_stays_ike"] = DHCP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_dhcp"] = (
        len(catalog) > 51
        and catalog[51]["id"] == DHCP_ACTUATION_ID
        and catalog[50]["id"] == RADIUS_ACTUATION_ID
        and catalog[51]["source"] == "genesis_bind_dhcp"
    )
    checks["catalog_names_ike"] = (
        len(catalog) > 52
        and catalog[52]["id"] == IKE_ACTUATION_ID
        and catalog[52]["source"] == "genesis_bind_ike"
    )
    family = capability_family(DHCP_ACTUATION_GOAL)
    checks["family_is_dhcp"] = "dhcp" in family
    checks["family_is_rfc2131"] = "rfc2131" in family
    checks["family_is_not_radius"] = (
        "radius" not in family and "radiu" not in family and "rfc2865" not in family
    )
    checks["family_is_not_ntp"] = "ntp" not in family and "rfc5905" not in family and "keyid" not in family
    checks["family_is_not_syslog"] = "syslog" not in family and "nilvalue" not in family
    checks["family_is_not_snmp"] = "snmp" not in family and "varbind" not in family
    checks["family_is_not_tftp"] = "tftp" not in family and "rfc1350" not in family
    checks["family_is_not_ftp"] = "ftpd" not in family and "pasv" not in family
    checks["family_is_not_dns"] = "tsig" not in family and "nameserver" not in family
    checks["family_is_not_ike"] = "ike" not in family and "rfc7296" not in family and "spi" not in family
    packed = encode_discover(xid=DEFAULT_XID, hostname=SENTINEL)
    parsed = parse_packet(packed)
    checks["discover_roundtrip"] = (
        parsed["op"] == BOOTREQUEST
        and parsed["msg_type"] == DHCPDISCOVER
        and parsed["hostname"] == SENTINEL
        and parsed["has_hostname"] is True
        and parsed["has_xid"] is True
        and parsed["xid"] == DEFAULT_XID
    )
    offer_packet = encode_offer(xid=DEFAULT_XID, hostname=SENTINEL, yiaddr=DEFAULT_YIADDR)
    offer = parse_packet(offer_packet)
    checks["offer_roundtrip"] = (
        offer["op"] == BOOTREPLY
        and offer["msg_type"] == DHCPOFFER
        and offer["hostname"] == SENTINEL
        and offer["yiaddr"] == DEFAULT_YIADDR
        and offer["xid"] == DEFAULT_XID
    )
    ack_packet = encode_ack(xid=DEFAULT_XID, hostname=SENTINEL, yiaddr=DEFAULT_YIADDR)
    ack = parse_packet(ack_packet)
    checks["ack_roundtrip"] = (
        ack["op"] == BOOTREPLY
        and ack["msg_type"] == DHCPACK
        and ack["hostname"] == SENTINEL
        and ack["yiaddr"] == DEFAULT_YIADDR
        and ack["xid"] == DEFAULT_XID
    )
    bare = encode_discover(xid=DEFAULT_XID, hostname=SENTINEL, include_xid=False)
    checks["missing_xid_is_unauthenticated"] = parse_packet(bare)["has_xid"] is False
    neighbors = (
        RADIUS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        IKE_ACTUATION_GOAL,
    )
    dhcp_signature = semantic_signature(DHCP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(dhcp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_dhcp = ToolDescriptor(name="remote_dhcp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_dhcp)
    checks["naive_mcp_dhcp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = dhcp_tool_descriptor()
    default_dhcp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DHCP_TOOL_PROVIDER),
    )
    checks["default_dhcp_provider_is_unsupported"] = (
        default_dhcp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{DHCP_TOOL_PROVIDER}" in default_dhcp.reasons
    )
    checks["opted_in_dhcp_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_dhcp],
        required_tool_names=("local_memory", "dhcp"),
    )
    checks["naive_preflight_missing_dhcp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["dhcp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "dhcp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DHCP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "dhcp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="dhcp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_dhcp_workflow(with_xid=False, output_dir=root / "missing")
        skip_bind = run_dhcp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_discover = run_dhcp_workflow(do_discover=False, output_dir=root / "skip-discover")
        skip_offer = run_dhcp_workflow(do_offer=False, output_dir=root / "skip-offer")
        skip_ack = run_dhcp_workflow(do_ack=False, output_dir=root / "skip-ack")
        skip_replay = run_dhcp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_xid = run_dhcp_workflow(use_xid=False, output_dir=root / "skip-xid")
        live = run_dhcp_workflow(output_dir=root / "live")
        verify = verify_dhcp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_dhcp_trace(clone)
        checks["naive_without_xid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_xid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_discover_stays_empty"] = (
            skip_discover["ok"] is False
            and skip_discover["error"] == "discover_required"
            and skip_discover["final_status"] == 409
            and skip_discover["payload_exists"] is False
        )
        checks["skip_offer_stays_empty"] = (
            skip_offer["ok"] is False
            and skip_offer["error"] == "offer_required"
            and skip_offer["final_status"] == 409
            and skip_offer["payload_exists"] is False
        )
        checks["skip_ack_stays_empty"] = (
            skip_ack["ok"] is False
            and skip_ack["error"] == "ack_required"
            and skip_ack["final_status"] == 409
            and skip_ack["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_xid_stays_empty"] = (
            skip_xid["ok"] is False
            and skip_xid["error"] == "xid_required"
            and skip_xid["final_status"] == 409
            and skip_xid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_yiaddr"] = live.get("yiaddr") == DEFAULT_YIADDR and int(live.get("port") or 0) > 0
        checks["token_xid_discover_offer_ack_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_discover["ok"] is False
            and skip_offer["ok"] is False
            and skip_ack["ok"] is False
            and skip_replay["ok"] is False
            and skip_xid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="dhcp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != DHCP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_dhcp"] = (
        live_goal == DHCP_ACTUATION_GOAL
        and DHCP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_dhcp"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_dhcp_actuation_capability()
    return {
        "ok": ok,
        "action": "dhcp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": DHCP_ACTUATION_GOAL,
        "done_when": DHCP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
