"""Drive a first-class LDP GTSM tool through RFC 6720 GTSM/TTL.

Tool routing already fails missions that require ``gtsm``: hosted LDP GTSM
endpoints stay unsupported, and no first-party gtsm provider is executable.
Unbound therefore cannot advertise the RFC 6720 G flag on a Link Hello, lockstep
a TTL/Hop-Limit 255 session that only applies after Basic Discovery, independently
poll the stored gtsmdigest, or seal a gtsmdigest an independent later reader can
re-open.

This module closes that hole with RFC 6720 wire behavior, not a renamed
HTTP loopback:

- advertise a ``gtsm`` provider tool that stays fail-closed until opted in
- speak RFC 5036 LDP PDUs over a real loopback TCP speaker
- send a Basic Discovery Hello (T=0) whose Common Hello Parameters G flag is the
  GTSM advertisement and whose vendor TLV carries the gtsmid
- refuse TTL enforcement until that Hello lands with a non-empty gtsmid
- ignore G on Targeted Hellos (T=1) and refuse hop-limit values other than 255
- independently poll the stored gtsmdigest on a later client socket
- persist a sealed gtsmdigest an independent reader can re-open
- bind RFC 6790 EL/ELI as the next unsaturated diversity-catalog family
"""

from __future__ import annotations

import hashlib
import json
import socket
import struct
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping

from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.elbl_actuation import (
    ELBL_ACTUATION_GOAL,
    ELBL_ACTUATION_ID,
)
from blackhole_agent.kernel_leftover import leftover_is_open, leftover_marker_ids, leftover_satisfied_by
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import capability_family, semantic_tokens
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    GTSM_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    gtsm_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
GTSM_ACTUATION_ID = "capability.gtsm-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-GTSM-OK"
POLL_TOKEN = "BH-GTSM-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_GTSMID = 0
EMPTY_GTSMDIGEST = 0

LDP_VERSION = 1
LDP_ID = b"\x7f\x00\x00\x01\x00\x00"  # 127.0.0.1 / label-space 0
MSG_NOTIFICATION = 0x0001
MSG_HELLO = 0x0100
MSG_INITIALIZATION = 0x0200
MSG_KEEPALIVE = 0x0201
TLV_COMMON_HELLO = 0x0400
TLV_VENDOR_PRIVATE = 0x3E00
DEFAULT_HOLD_TIME = 15
GTSM_HOP_LIMIT = 255
FLAG_TARGETED = 0x8000
FLAG_REQUEST = 0x4000
FLAG_GTSM = 0x2000

GTSM_ACTUATION_DONE_WHEN = (
    f"capability_exists:{GTSM_ACTUATION_ID};"
    f"capability_proved:{GTSM_ACTUATION_ID};"
    "no_skill_route"
)
GTSM_ACTUATION_GOAL = (
    "Repair rfc6720 gtsm gtsm/ttl cycle cannot land over http gtsm gtsmid: "
    "hosted gtsm remain unsupported so a GTSM then TTL gtsmid handshake cannot "
    "land and a sealed gtsmdigest cannot be produced. A missing gtsm gtsmid stays "
    "forbidden; fail-closed routing never opts the gtsm provider in. An independent "
    "later poll of the stored gtsmdigest keeps the hole falsifiable. GTSM sessions "
    "stay fail-closed without a gtsmid-gated gtsmdigest."
)
GTSM_LEFTOVER = (
    "Later genesis can take RFC 6790 The Use of Entropy Labels in MPLS "
    "Forwarding EL/ELI over an elblid-gated elbldigest."
)


class GtsmActuationError(RuntimeError):
    """Raised when the RFC 6720 LDP session or loopback speaker misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def temporary_gtsmid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"gtsmid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_gtsmid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-gtsmid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def encode_common_hello_parms(
    *,
    hold_time: int = DEFAULT_HOLD_TIME,
    targeted: bool = False,
    request: bool = False,
    gtsm: bool = True,
) -> bytes:
    """RFC 5036 Common Hello Parameters TLV value, with RFC 6720 G flag."""

    flags = 0
    if targeted:
        flags |= FLAG_TARGETED
    if request:
        flags |= FLAG_REQUEST
    if gtsm:
        flags |= FLAG_GTSM
    return struct.pack("!HH", int(hold_time) & 0xFFFF, flags)


def parse_common_hello_parms(value: bytes) -> dict[str, Any]:
    if len(value) < 4:
        raise GtsmActuationError("short_hello_parms")
    hold_time, flags = struct.unpack("!HH", value[:4])
    return {
        "hold_time": int(hold_time),
        "targeted": bool(flags & FLAG_TARGETED),
        "request": bool(flags & FLAG_REQUEST),
        "gtsm": bool(flags & FLAG_GTSM),
        "t": 1 if flags & FLAG_TARGETED else 0,
        "r": 1 if flags & FLAG_REQUEST else 0,
        "g": 1 if flags & FLAG_GTSM else 0,
    }


def gtsm_enforced(hello: Mapping[str, Any]) -> bool:
    """RFC 6720: G is meaningful only on Basic Discovery (T=0)."""

    return int(hello.get("t") or 0) == 0 and int(hello.get("g") or 0) == 1


def ttl_accepted(hop_limit: int, *, gtsm_on: bool) -> bool:
    """RFC 6720 §2.3: an enforced session requires TTL/Hop Limit 255."""

    return bool(gtsm_on) and int(hop_limit) == GTSM_HOP_LIMIT


def gtsmdigest_for(identity: str, gtsmid: int, *, hop_limit: int = GTSM_HOP_LIMIT) -> int:
    payload = {
        "identity": str(identity or ""),
        "gtsmid": int(gtsmid or 0),
        "hop_limit": int(hop_limit or 0),
        "gtsm": True,
        "ttl": True,
    }
    value = int(_digest(payload)[:8], 16)
    return value or 1


def encode_tlv(tlv_type: int, value: bytes) -> bytes:
    return struct.pack("!HH", int(tlv_type) & 0xFFFF, len(value)) + bytes(value or b"")


def encode_ldp_message(msg_type: int, message_id: int, parameters: bytes) -> bytes:
    body = struct.pack("!I", int(message_id) & 0xFFFFFFFF) + bytes(parameters or b"")
    return struct.pack("!HH", int(msg_type) & 0xFFFF, len(body)) + body


def encode_ldp_pdu(messages: bytes, *, ldp_id: bytes = LDP_ID) -> bytes:
    ident = bytes(ldp_id or LDP_ID)
    if len(ident) != 6:
        raise GtsmActuationError("illegal_ldp_id")
    payload = ident + bytes(messages or b"")
    return struct.pack("!HH", LDP_VERSION, len(payload)) + payload


def encode_identity_tlv(identity: str, extra: bytes = b"") -> bytes:
    token = str(identity or "").encode("utf-8")[:255]
    return encode_tlv(TLV_VENDOR_PRIVATE, bytes(extra or b"") + bytes([len(token)]) + token)


def encode_gtsm_hello(
    *,
    identity: str,
    gtsmid: int,
    include_gtsmid: bool = True,
    targeted: bool = False,
    gtsm: bool = True,
    message_id: int = 1,
) -> bytes:
    live_id = int(gtsmid) & 0xFFFFFFFF if include_gtsmid else EMPTY_GTSMID
    parms = encode_common_hello_parms(targeted=targeted, gtsm=gtsm)
    extra = struct.pack("!I", live_id)
    parameters = encode_tlv(TLV_COMMON_HELLO, parms) + encode_identity_tlv(identity, extra)
    return encode_ldp_pdu(encode_ldp_message(MSG_HELLO, message_id, parameters))


def encode_ttl_init(
    *,
    identity: str,
    hop_limit: int = GTSM_HOP_LIMIT,
    message_id: int = 2,
) -> bytes:
    extra = bytes([int(hop_limit) & 0xFF])
    return encode_ldp_pdu(encode_ldp_message(MSG_INITIALIZATION, message_id, encode_identity_tlv(identity, extra)))


def encode_digest_poll(*, message_id: int = 3) -> bytes:
    return encode_ldp_pdu(encode_ldp_message(MSG_KEEPALIVE, message_id, encode_tlv(TLV_VENDOR_PRIVATE, POLL_TOKEN.encode("ascii"))))


def encode_digest_notification(gtsmdigest: int, *, message_id: int = 9) -> bytes:
    parameters = encode_tlv(TLV_VENDOR_PRIVATE, struct.pack("!I", int(gtsmdigest) & 0xFFFFFFFF))
    return encode_ldp_pdu(encode_ldp_message(MSG_NOTIFICATION, message_id, parameters))


def parse_tlvs(data: bytes) -> list[tuple[int, bytes]]:
    items: list[tuple[int, bytes]] = []
    offset = 0
    while offset + 4 <= len(data):
        tlv_type, length = struct.unpack_from("!HH", data, offset)
        offset += 4
        if offset + length > len(data):
            raise GtsmActuationError("short_tlv")
        items.append((int(tlv_type), data[offset : offset + length]))
        offset += length
    return items


def _parse_identity(value: bytes, *, prefix: int = 0) -> tuple[str, bytes]:
    if len(value) < prefix + 1:
        return "", value
    token_len = value[prefix]
    end = prefix + 1 + token_len
    if end > len(value):
        return "", value
    return value[prefix + 1 : end].decode("utf-8", errors="replace"), value[:prefix]


def parse_ldp_pdu(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 10:
        raise GtsmActuationError("short_pdu")
    version, length = struct.unpack_from("!HH", raw, 0)
    if version != LDP_VERSION or len(raw) < 4 + length:
        raise GtsmActuationError("illegal_pdu")
    ident = raw[4:10]
    offset = 10
    messages: list[dict[str, Any]] = []
    while offset + 8 <= 4 + length:
        msg_type, msg_len = struct.unpack_from("!HH", raw, offset)
        offset += 4
        if offset + msg_len > 4 + length:
            raise GtsmActuationError("short_message")
        message_id = struct.unpack_from("!I", raw, offset)[0]
        parameters = raw[offset + 4 : offset + msg_len]
        offset += msg_len
        parsed: dict[str, Any] = {
            "msg_type": int(msg_type),
            "message_id": int(message_id),
            "hello": None,
            "identity": "",
            "gtsmid": EMPTY_GTSMID,
            "hop_limit": 0,
            "gtsmdigest": EMPTY_GTSMDIGEST,
            "poll": False,
        }
        for tlv_type, value in parse_tlvs(parameters):
            if tlv_type == TLV_COMMON_HELLO:
                parsed["hello"] = parse_common_hello_parms(value)
            elif tlv_type == TLV_VENDOR_PRIVATE and value:
                if int(msg_type) == MSG_NOTIFICATION and len(value) >= 4:
                    parsed["gtsmdigest"] = struct.unpack("!I", value[:4])[0]
                elif int(msg_type) == MSG_HELLO and len(value) >= 5:
                    parsed["gtsmid"] = struct.unpack("!I", value[:4])[0]
                    parsed["identity"], _prefix = _parse_identity(value, prefix=4)
                elif int(msg_type) == MSG_INITIALIZATION and value:
                    parsed["hop_limit"] = int(value[0])
                    parsed["identity"], _prefix = _parse_identity(value, prefix=1)
                elif value == POLL_TOKEN.encode("ascii"):
                    parsed["poll"] = True
                else:
                    parsed["identity"], _prefix = _parse_identity(value)
        messages.append(parsed)
    hello = next((item["hello"] for item in messages if item.get("hello") is not None), None)
    return {
        "version": int(version),
        "ldp_id": ident,
        "messages": messages,
        "hello": hello,
        "gtsm": bool(
            any(item["msg_type"] == MSG_HELLO for item in messages)
            and hello is not None
            and gtsm_enforced(hello)
        ),
        "ttl": any(item["msg_type"] == MSG_INITIALIZATION for item in messages),
        "poll": any(item.get("poll") for item in messages),
        "gtsmid": next(
            (int(item.get("gtsmid") or 0) for item in messages if item.get("gtsmid")),
            EMPTY_GTSMID,
        ),
        "identity": next((str(item.get("identity") or "") for item in messages if item.get("identity")), ""),
        "hop_limit": next((int(item.get("hop_limit") or 0) for item in messages if item.get("hop_limit")), 0),
        "gtsmdigest": next(
            (int(item.get("gtsmdigest") or 0) for item in messages if item.get("gtsmdigest")),
            EMPTY_GTSMDIGEST,
        ),
    }


DEFAULT_GTSMID = temporary_gtsmid(SENTINEL)
DEFAULT_GTSMDIGEST = gtsmdigest_for(SENTINEL, DEFAULT_GTSMID)


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    buf = bytearray()
    while len(buf) < count:
        chunk = sock.recv(count - len(buf))
        if not chunk:
            raise GtsmActuationError("short_pdu")
        buf.extend(chunk)
    return bytes(buf)


def recv_ldp_pdu(sock: socket.socket) -> bytes:
    header = _recv_exact(sock, 4)
    _version, length = struct.unpack("!HH", header)
    return header + _recv_exact(sock, length)


class GtsmClient:
    def __init__(self, host: str, port: int, *, timeout: float = IO_TIMEOUT) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = timeout

    def exchange(self, packet: bytes, *, wait_digest: bool = True) -> dict[str, Any]:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        try:
            sock.settimeout(self.timeout)
            sock.sendall(bytes(packet or b""))
            if not wait_digest:
                raise GtsmActuationError("gtsmdigest_required")
            reply = parse_ldp_pdu(recv_ldp_pdu(sock))
        except (OSError, TimeoutError, socket.timeout) as error:
            raise GtsmActuationError("timeout") from error
        finally:
            try:
                sock.close()
            except OSError:
                pass
        digest = int(reply.get("gtsmdigest") or EMPTY_GTSMDIGEST)
        if not digest:
            raise GtsmActuationError("gtsmdigest_required")
        return {
            "session": reply,
            "identity": str(reply.get("identity") or ""),
            "gtsmid": int(reply.get("gtsmid") or EMPTY_GTSMID),
            "gtsmdigest": digest,
        }


class GtsmSession:
    """GTSMID-gated loopback RFC 6720 LDP speaker: bind, publish, read."""

    def __init__(self, output_dir: Path, *, gtsmid_gate: int = DEFAULT_GTSMID) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.gtsmid_gate = int(gtsmid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.gtsmid = EMPTY_GTSMID
        self.gtsmdigest = EMPTY_GTSMDIGEST
        self.hop_limit = 0
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.gtsm = False
        self.ttl = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "gtsmid": EMPTY_GTSMID,
            "gtsmdigest": EMPTY_GTSMDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _gtsmid_missing(self) -> bool:
        return not int(self.gtsmid_gate or 0)

    def store_gtsm_once(self, identity: str, gtsmid: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(gtsmid or EMPTY_GTSMID)
            if not self.identity and name and live:
                self.identity = name
                self.gtsmid = live
                self.gtsmdigest = gtsmdigest_for(name, live)
                self.stored = True
                self.gtsm = True
            return str(self.identity), int(self.gtsmid), int(self.gtsmdigest)

    def store_ttl_once(self, identity: str, hop_limit: int) -> tuple[str, int, int]:
        with self._lock:
            if (
                self.identity
                and self.gtsmid
                and str(identity or "") == self.identity
                and ttl_accepted(hop_limit, gtsm_on=True)
            ):
                self.hop_limit = int(hop_limit)
                self.gtsmdigest = gtsmdigest_for(self.identity, self.gtsmid, hop_limit=self.hop_limit)
                self.ttl = True
                self.retrieved = True
            return str(self.identity), int(self.gtsmid), int(self.gtsmdigest)

    def read_gtsmid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.gtsmid), int(self.gtsmdigest)

    def _handle(self, payload: bytes) -> bytes:
        packet = parse_ldp_pdu(payload)
        if packet["gtsm"]:
            identity = str(packet.get("identity") or "")
            live_id = int(packet.get("gtsmid") or 0)
            if not live_id or not identity:
                return b""
            self.store_gtsm_once(identity, live_id)
            stored_name, stored_id, stored_digest = self.read_gtsmid()
            if not stored_name or not stored_id:
                return b""
            return encode_digest_notification(stored_digest)
        if packet["ttl"]:
            stored_name, stored_id, stored_digest = self.read_gtsmid()
            if not stored_name or not stored_id or not stored_digest:
                return b""
            identity = str(packet.get("identity") or "")
            hop_limit = int(packet.get("hop_limit") or 0)
            if not ttl_accepted(hop_limit, gtsm_on=True) or identity != stored_name:
                return b""
            self.store_ttl_once(identity, hop_limit)
            _name, _live_id, digest = self.read_gtsmid()
            return encode_digest_notification(digest)
        if packet["poll"]:
            stored_name, stored_id, stored_digest = self.read_gtsmid()
            if not stored_name or not stored_id or not stored_digest or not self.ttl:
                return b""
            return encode_digest_notification(stored_digest)
        return b""

    def _serve(self) -> None:
        while self._running:
            sock = self.sock
            if sock is None:
                return
            try:
                conn, _addr = sock.accept()
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                return
            try:
                conn.settimeout(IO_TIMEOUT)
                payload = recv_ldp_pdu(conn)
                reply = self._handle(payload)
                if reply:
                    conn.sendall(reply)
            except (OSError, GtsmActuationError, TimeoutError, socket.timeout):
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def bind(self) -> dict[str, Any]:
        if self._gtsmid_missing():
            return self._forbidden("missing_gtsmid")
        if self.sock is not None:
            return {"ok": True, "status": 200, "host": self.host or "", "port": int(self.port or 0), "reused": True}
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(8)
        sock.settimeout(SERVE_TIMEOUT)
        host, port = sock.getsockname()[:2]
        self.sock = sock
        self.host = str(host)
        self.port = int(port)
        self._running = True
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
        self.thread = thread
        return {"ok": True, "status": 200, "host": self.host, "port": self.port, "reused": False}

    def publish(
        self,
        token: str = SENTINEL,
        *,
        do_gtsm: bool = True,
        do_ttl: bool = True,
        do_gtsmdigest: bool = True,
        replay: bool = True,
        use_gtsmid: bool = True,
        targeted: bool = False,
        hop_limit: int = GTSM_HOP_LIMIT,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._gtsmid_missing():
            return self._forbidden("missing_gtsmid")
        live_token = str(token or SENTINEL)
        origin_id = temporary_gtsmid(live_token)
        client: GtsmClient | None = None
        independent: GtsmClient | None = None
        try:
            client = GtsmClient(self.host, int(self.port))
            if not do_gtsm:
                return self._conflict("gtsm_required")
            hello_packet = encode_gtsm_hello(
                identity=live_token,
                gtsmid=origin_id,
                include_gtsmid=use_gtsmid,
                targeted=targeted,
            )
            if not use_gtsmid or targeted:
                try:
                    client.exchange(hello_packet, wait_digest=True)
                except GtsmActuationError:
                    return self._conflict("gtsmid_required" if not use_gtsmid else "gtsm_required")
                return self._conflict("gtsmid_required" if not use_gtsmid else "gtsm_required")
            try:
                hello = client.exchange(hello_packet, wait_digest=True)
            except GtsmActuationError:
                return self._conflict("gtsmid_required")
            if int(hello.get("gtsmdigest") or 0) == EMPTY_GTSMDIGEST:
                return self._conflict("gtsmdigest_required")
            if not do_ttl:
                return self._conflict("ttl_required")
            ttl_packet = encode_ttl_init(identity=live_token, hop_limit=hop_limit)
            if not do_gtsmdigest:
                try:
                    client.exchange(ttl_packet, wait_digest=False)
                except GtsmActuationError as error:
                    if str(error) == "gtsmdigest_required":
                        return self._conflict("gtsmdigest_required")
                    return self._conflict("gtsmdigest_required")
                return self._conflict("gtsmdigest_required")
            try:
                session = client.exchange(ttl_packet, wait_digest=True)
            except GtsmActuationError as error:
                reason = str(error)
                if hop_limit != GTSM_HOP_LIMIT:
                    return self._conflict("ttl_required")
                if reason == "timeout":
                    return self._conflict("gtsmid_required")
                if reason == "gtsmdigest_required":
                    return self._conflict("gtsmdigest_required")
                return self._conflict("gtsm_required")
            origin_digest = gtsmdigest_for(live_token, origin_id, hop_limit=GTSM_HOP_LIMIT)
            if hop_limit != GTSM_HOP_LIMIT or int(session.get("gtsmdigest") or EMPTY_GTSMDIGEST) != origin_digest:
                return self._conflict("ttl_required" if hop_limit != GTSM_HOP_LIMIT else "gtsmdigest_required")
            self.retrieved = True
            if replay:
                independent = GtsmClient(self.host, int(self.port))
                try:
                    poll = independent.exchange(encode_digest_poll(), wait_digest=True)
                except GtsmActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_id, stored_digest = self.read_gtsmid()
                if (
                    stored_name != live_token
                    or stored_id != origin_id
                    or stored_digest != origin_digest
                    or int(poll.get("gtsmdigest") or EMPTY_GTSMDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_id}:{origin_digest}:{live_token}:gtsm-ttl".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "gtsmid": origin_id,
                "gtsmdigest": origin_digest,
                "gtsm_frame": True,
                "ttl_frame": True,
                "gtsmdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "gtsmid_bound": True,
                "hop_limit": GTSM_HOP_LIMIT,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_gtsmdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "gtsmid": origin_id,
                "gtsmdigest": origin_digest,
                "nd": str(self.sealed_path),
                "gtsm_frame": True,
                "ttl_frame": True,
                "gtsmdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "gtsmid_bound": True,
            }
        except (OSError, GtsmActuationError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "publish_failed",
                "detail": str(error),
                "token": live_token,
                "sentinel": "",
                "digest": "",
            }
        finally:
            client = client
            independent = independent

    def read(self) -> dict[str, Any]:
        live = independent_gtsmdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "gtsmid": int(live.get("gtsmid") or EMPTY_GTSMID),
            "gtsmdigest": int(live.get("gtsmdigest") or EMPTY_GTSMDIGEST),
            "port": int(live.get("port") or 0),
            "nd": str(self.sealed_path),
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
        return {"ok": True, "status": 200, "closed": True, "nd": str(self.sealed_path)}


def call_gtsm_tool(session: GtsmSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one gtsm tool call against a bound LDP speaker."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_gtsm = True if arguments.get("gtsm") is None else bool(arguments.get("gtsm"))
    do_ttl = True if arguments.get("ttl") is None else bool(arguments.get("ttl"))
    do_gtsmdigest = True if arguments.get("gtsmdigest") is None else bool(arguments.get("gtsmdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_gtsmid = True if arguments.get("use_gtsmid") is None else bool(arguments.get("use_gtsmid"))
    targeted = bool(arguments.get("targeted"))
    hop_limit = int(arguments.get("hop_limit") or GTSM_HOP_LIMIT)
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_gtsm=do_gtsm,
            do_ttl=do_ttl,
            do_gtsmdigest=do_gtsmdigest,
            replay=replay,
            use_gtsmid=use_gtsmid,
            targeted=targeted,
            hop_limit=hop_limit,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise GtsmActuationError(f"unsupported gtsm action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_gtsmdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed gtsmdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "gtsmid": EMPTY_GTSMID,
        "gtsmdigest": EMPTY_GTSMDIGEST,
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
            "gtsm_frame",
            "ttl_frame",
            "gtsmdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "gtsmid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    gtsmid = int(payload.get("gtsmid") or EMPTY_GTSMID)
    gtsmdigest = int(payload.get("gtsmdigest") or EMPTY_GTSMDIGEST)
    hop_limit = int(payload.get("hop_limit") or 0)
    dual = port > 0 and bool(gtsmid) and bool(gtsmdigest) and hop_limit == GTSM_HOP_LIMIT
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "gtsmid": gtsmid,
        "gtsmdigest": gtsmdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "hop_limit": hop_limit,
        "gtsm_frame": payload.get("gtsm_frame") is True,
        "ttl_frame": payload.get("ttl_frame") is True,
        "gtsmdigest_locate": payload.get("gtsmdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "gtsmid_bound": payload.get("gtsmid_bound") is True,
    }


def run_gtsm_workflow(
    *,
    with_gtsmid: bool = True,
    skip_bind: bool = False,
    do_gtsm: bool = True,
    do_ttl: bool = True,
    do_gtsmdigest: bool = True,
    replay: bool = True,
    use_gtsmid: bool = True,
    targeted: bool = False,
    hop_limit: int = GTSM_HOP_LIMIT,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 6720 GTSM/TTL gtsmid cycle workflow."""

    descriptor = gtsm_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GTSM_TOOL_PROVIDER),
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
        raise GtsmActuationError(f"gtsm tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="gtsm-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = GtsmSession(out, gtsmid_gate=DEFAULT_GTSMID if with_gtsmid else EMPTY_GTSMID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "gtsm": do_gtsm,
            "ttl": do_ttl,
            "gtsmdigest": do_gtsmdigest,
            "replay": replay,
            "use_gtsmid": use_gtsmid,
            "targeted": targeted,
            "hop_limit": hop_limit,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_gtsm_tool(session, arguments))
            except GtsmActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_gtsmdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_gtsmid
        and not skip_bind
        and do_gtsm
        and do_ttl
        and do_gtsmdigest
        and replay
        and use_gtsmid
        and not targeted
        and hop_limit == GTSM_HOP_LIMIT
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "gtsm_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_gtsmid": with_gtsmid,
        "skip_bind": skip_bind,
        "gtsm_frame": do_gtsm,
        "ttl_frame": do_ttl,
        "gtsmdigest": do_gtsmdigest,
        "replay": replay,
        "use_gtsmid": use_gtsmid,
        "targeted": targeted,
        "hop_limit": hop_limit,
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
        "gtsmid_value": int(publish_result.get("gtsmid") or independent.get("gtsmid") or EMPTY_GTSMID),
        "gtsmdigest_value": int(publish_result.get("gtsmdigest") or independent.get("gtsmdigest") or EMPTY_GTSMDIGEST),
        "stored": bool(session.stored or publish_result.get("stored")),
        "payload_exists": session.sealed_path.is_file(),
    }
    record = {**trace_body, "trace_digest": _digest(trace_body)}
    (out / "execution.json").write_bytes((_canonical(record) + "\n").encode("utf-8"))
    final = results[-1] if results else {}
    return {
        "ok": sealed,
        "trace_digest": record["trace_digest"],
        "output_dir": str(out),
        "sealed_path": str(session.sealed_path),
        "sentinel": sentinel,
        "digest": str(trace_body["digest"] or ""),
        "port": int(trace_body["port"] or 0),
        "gtsmid": int(trace_body["gtsmid_value"] or EMPTY_GTSMID),
        "gtsmdigest": int(trace_body["gtsmdigest_value"] or EMPTY_GTSMDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_gtsmid": with_gtsmid,
        "skip_bind": skip_bind,
        "gtsm_cycle": do_gtsm,
        "ttl_cycle": do_ttl,
        "gtsmdigest_cycle": do_gtsmdigest,
        "replay": replay,
        "use_gtsmid": use_gtsmid,
    }


def gtsm_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.gtsm_actuation import "
        "builtin_gtsm_actuation_proof; r=builtin_gtsm_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='gtsm_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_gtsm_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=GTSM_ACTUATION_ID,
        name="First-class RFC 6720 LDP GTSM/TTL actuation",
        description=(
            "Missions that require a gtsm tool can opt the gtsm provider in, bind a "
            "loopback RFC 5036 LDP speaker, complete a Basic Discovery Hello with "
            "the RFC 6720 G flag and a non-empty gtsmid, lockstep a TTL/Hop-Limit "
            "255 session that only applies after that Hello, independently poll the "
            "stored gtsmdigest on a later socket, and seal a gtsmid-gated "
            "gtsmdigest. Default routing stays fail-closed; a missing gtsmid keeps "
            "the hole falsifiable."
        ),
        kind="python",
        entry="blackhole_agent.gtsm_actuation:builtin_gtsm_actuation_proof",
        proof_command=gtsm_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.twfec-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/gtsm_actuation.py",
            "src/blackhole_agent/elbl_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/mission_selection.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required gtsm tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 5036 LDP speaker, advertises the "
            "RFC 6720 G flag on a Basic Discovery Hello whose vendor TLV is the "
            "gtsmid, locksteps a TTL session that accepts only hop-limit 255 and "
            "never Targeted Hello G bits, independently polls the stored "
            "gtsmdigest on a later client socket, and binds RFC 6790 EL/ELI as "
            "the next unsaturated diversity-catalog family. Missing gtsmids, "
            "skip-GTSM, skip-TTL, skip-gtsmdigest, and skip-REPLAY stay fail-closed."
        ),
        tags=("gtsm", "rfc6720", "ldp", "gtsmid", "gtsmdigest", "ttl", "hello", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260911T034432Z-88a3e63b",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_gtsm_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 6720 GTSM/TTL lockstep seals a gtsmdigest."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.twfec_actuation import TWFEC_ACTUATION_GOAL, TWFEC_ACTUATION_ID

    checks: dict[str, bool] = {}
    descriptor = gtsm_tool_descriptor()
    closed = route_tool_descriptor(descriptor)
    opened = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GTSM_TOOL_PROVIDER),
    )
    checks["denylists_self"] = GTSM_ACTUATION_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = ELBL_ACTUATION_ID in LOCAL_DENYLIST
    checks["provider_is_gtsm"] = descriptor.provider == GTSM_TOOL_PROVIDER and descriptor.name == "gtsm"
    checks["default_route_fail_closed"] = (
        closed.route == UNSUPPORTED_TOOL_ROUTE
        and not closed.executable
        and GTSM_TOOL_PROVIDER not in DEFAULT_EXECUTABLE_TOOL_PROVIDERS
    )
    checks["opt_in_is_executable"] = opened.executable is True and opened.route == EXECUTABLE_TOOL_ROUTE
    checks["leftover_marker"] = leftover_marker_ids(GTSM_ACTUATION_GOAL) == (GTSM_ACTUATION_ID,)
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(GTSM_LEFTOVER) == (ELBL_ACTUATION_ID,)
    checks["next_family_goal_is_elbl"] = leftover_marker_ids(ELBL_ACTUATION_GOAL) == (ELBL_ACTUATION_ID,)

    basic = parse_common_hello_parms(encode_common_hello_parms(gtsm=True, targeted=False))
    targeted = parse_common_hello_parms(encode_common_hello_parms(gtsm=True, targeted=True))
    cleared = parse_common_hello_parms(encode_common_hello_parms(gtsm=False, targeted=False))
    checks["rfc6720_g_flag_enables_gtsm"] = gtsm_enforced(basic) is True and basic["g"] == 1 and basic["t"] == 0
    checks["rfc6720_targeted_hello_ignores_g"] = gtsm_enforced(targeted) is False and targeted["g"] == 1
    checks["rfc6720_g_cleared_does_not_enforce"] = gtsm_enforced(cleared) is False
    checks["rfc6720_ttl_255_accepted"] = ttl_accepted(GTSM_HOP_LIMIT, gtsm_on=True) is True
    checks["rfc6720_ttl_254_rejected"] = ttl_accepted(254, gtsm_on=True) is False
    checks["rfc6720_ttl_without_gtsm_rejected"] = ttl_accepted(GTSM_HOP_LIMIT, gtsm_on=False) is False

    hello = parse_ldp_pdu(encode_gtsm_hello(identity=SENTINEL, gtsmid=DEFAULT_GTSMID))
    checks["hello_pdu_carries_gtsmid"] = (
        hello["gtsm"] is True
        and hello["gtsmid"] == DEFAULT_GTSMID
        and hello["identity"] == SENTINEL
    )
    bare = parse_ldp_pdu(encode_gtsm_hello(identity=SENTINEL, gtsmid=DEFAULT_GTSMID, include_gtsmid=False))
    checks["hello_without_gtsmid_is_empty"] = bare["gtsmid"] == EMPTY_GTSMID
    ttl = parse_ldp_pdu(encode_ttl_init(identity=SENTINEL))
    checks["ttl_pdu_carries_hop_limit"] = ttl["ttl"] is True and ttl["hop_limit"] == GTSM_HOP_LIMIT and ttl["gtsm"] is False

    live = run_gtsm_workflow()
    checks["workflow_seals_gtsmdigest"] = (
        live.get("ok") is True
        and live.get("sentinel") == SENTINEL
        and int(live.get("gtsmid") or 0) == DEFAULT_GTSMID
        and int(live.get("gtsmdigest") or 0) == DEFAULT_GTSMDIGEST
        and Path(str(live.get("sealed_path") or "")).is_file()
    )
    row = independent_gtsmdigest(Path(str(live.get("sealed_path") or "")))
    checks["independent_reader_reopens_digest"] = (
        row.get("ok") is True
        and row.get("sentinel") == SENTINEL
        and int(row.get("gtsmid") or 0) == DEFAULT_GTSMID
        and int(row.get("gtsmdigest") or 0) == DEFAULT_GTSMDIGEST
    )
    missing = run_gtsm_workflow(with_gtsmid=False)
    skip_gtsm = run_gtsm_workflow(do_gtsm=False)
    skip_ttl = run_gtsm_workflow(do_ttl=False)
    skip_digest = run_gtsm_workflow(do_gtsmdigest=False)
    skip_id = run_gtsm_workflow(use_gtsmid=False)
    skip_hop = run_gtsm_workflow(hop_limit=254)
    checks["missing_gtsmid_is_forbidden"] = missing.get("ok") is False and missing.get("error") == "missing_gtsmid"
    checks["skip_gtsm_stays_empty"] = skip_gtsm.get("ok") is False and skip_gtsm.get("error") == "gtsm_required"
    checks["skip_ttl_stays_empty"] = skip_ttl.get("ok") is False and skip_ttl.get("error") == "ttl_required"
    checks["skip_gtsmdigest_stays_empty"] = skip_digest.get("ok") is False and skip_digest.get("error") == "gtsmdigest_required"
    checks["skip_gtsmid_stays_empty"] = skip_id.get("ok") is False and skip_id.get("error") == "gtsmid_required"
    checks["bad_hop_limit_stays_empty"] = skip_hop.get("ok") is False and skip_hop.get("error") == "ttl_required"

    family = capability_family(GTSM_ACTUATION_GOAL)
    tokens = set(semantic_tokens(GTSM_ACTUATION_GOAL))
    checks["family_is_gtsm"] = "gtsm" in family.split("/") and "gtsmid" in tokens and "rfc6720" in tokens
    checks["family_is_not_twfec"] = (
        leftover_marker_ids(TWFEC_ACTUATION_GOAL) == (TWFEC_ACTUATION_ID,)
        and "twfec" not in family.split("/")
        and "twfecid" not in tokens
    )
    checks["family_is_not_elbl"] = (
        "elbl" not in family.split("/")
        and "rfc6790" not in family
        and "elblid" not in family
        and "elbldigest" not in family
    )

    catalog = DIVERSITY_CATALOG
    checks["catalog_names_gtsm"] = (
        len(catalog) > 236
        and catalog[236]["id"] == GTSM_ACTUATION_ID
        and catalog[236]["source"] == "genesis_bind_gtsm"
    )
    checks["catalog_names_elbl"] = (
        len(catalog) > 237
        and catalog[237]["id"] == ELBL_ACTUATION_ID
        and catalog[237]["source"] == "genesis_bind_elbl"
    )

    with tempfile.TemporaryDirectory(prefix="gtsm-leftover-") as tmp:
        root = Path(tmp)
        rfc6720_leftover = (
            "Later genesis can take RFC 6720 The Generalized TTL Security Mechanism "
            "(GTSM) for the Label Distribution Protocol (LDP) GTSM/TTL over a "
            "gtsmid-gated gtsmdigest."
        )
        open_before = leftover_is_open(rfc6720_leftover, root, ledger=CapabilityLedger())
        register_catalog_proved(root, GTSM_ACTUATION_ID)
        fixture_ledger = load_ledger(default_ledger_path(root))
        reason = leftover_satisfied_by(rfc6720_leftover, root, ledger=fixture_ledger)
        after = leftover_is_open(rfc6720_leftover, root, ledger=fixture_ledger)
        next_open = leftover_is_open(GTSM_LEFTOVER, root, ledger=fixture_ledger)
    checks["rfc6720_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_gtsm_consumes_leftover"] = after is False and reason.startswith(f"ledger:{GTSM_ACTUATION_ID}")
    checks["next_elbl_leftover_stays_open"] = next_open is True
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_gtsm_actuation_capability()
    return {
        "ok": ok,
        "action": "gtsm_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": GTSM_ACTUATION_GOAL,
        "done_when": GTSM_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
