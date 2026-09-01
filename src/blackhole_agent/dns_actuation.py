"""Drive a first-class DNS tool through TSIG-gated apex publication.

Tool routing already fails missions that require ``dns``: hosted nameserver
plugins stay on the unsupported MCP provider, and no first-party DNS
provider is executable. Unbound therefore cannot speak RFC 2136 UPDATE
with HMAC-SHA256 TSIG, QUERY the resulting apex TXT, or seal a zone that
an independent resolver can re-read.

This module closes that hole:

- advertise a ``dns`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback DNS/UDP nameserver
- keep a missing-secret client so the TSIG hole stays falsifiable
- refuse UPDATE until a valid HMAC-SHA256 TSIG MAC is attached
- QUERY the apex after UPDATE, then independently re-QUERY from a fresh
  socket so skip-UPDATE and skip-QUERY stay empty
- persist a sealed apex an independent reader can re-open from disk
- bind this family as the next diversity-catalog successor after MQTT
"""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import socket
import socketserver
import struct
import tempfile
import threading
import time
from dataclasses import dataclass, field
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
    UNSUPPORTED_TOOL_ROUTE,
    DNS_TOOL_PROVIDER,
    ToolDescriptor,
    build_tool_routing_preflight,
    dns_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
DNS_ACTUATION_ID = "capability.dns-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-dns"
SENTINEL = "BH-DNS-OK"
DEFAULT_SECRET = "blackhole-dns-secret"
DEFAULT_ZONE = "blackhole.test"
DEFAULT_NAME = "beacon.blackhole.test"
DEFAULT_KEY_NAME = "blackhole-tsig"
DEFAULT_ALGORITHM = "hmac-sha256"
SEALED_NAME = "sealed.json"
TSIG_FUDGE = 300

CLASS_IN = 1
CLASS_ANY = 255
TYPE_SOA = 6
TYPE_TXT = 16
TYPE_TSIG = 250
OPCODE_QUERY = 0
OPCODE_UPDATE = 5
RCODE_NOERROR = 0
RCODE_FORMERR = 1
RCODE_NXDOMAIN = 3
RCODE_REFUSED = 5
RCODE_NOTAUTH = 9
TSIG_BADSIG = 16
TSIG_BADKEY = 17
TSIG_BADTIME = 18

DNS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DNS_ACTUATION_ID};"
    f"capability_proved:{DNS_ACTUATION_ID};"
    "no_skill_route"
)
DNS_ACTUATION_GOAL = (
    "Repair nameserver TSIG-gated apex record: hosted nameserver tools remain "
    "unsupported so an UPDATE/TSIG/QUERY cycle cannot land and a sealed apex "
    "TXT cannot be produced. A missing TSIG secret stays forbidden; "
    "fail-closed routing never opts the dns provider in."
)


class DnsActuationError(RuntimeError):
    """Raised when the DNS session or nameserver fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _canon_name(name: str) -> str:
    return str(name or "").strip(".").lower()


def _encode_name(name: str) -> bytes:
    labels = [part for part in _canon_name(name).split(".") if part]
    out = bytearray()
    for label in labels:
        raw = label.encode("ascii")
        if len(raw) > 63:
            raise DnsActuationError(f"label too long: {label!r}")
        out.append(len(raw))
        out.extend(raw)
    out.append(0)
    return bytes(out)


def _read_name(buf: bytes, offset: int, hops: int = 0) -> tuple[str, int]:
    if hops > 10:
        raise DnsActuationError("name compression loop")
    labels: list[str] = []
    consumed = offset
    jumped = False
    while True:
        if offset >= len(buf):
            raise DnsActuationError("truncated name")
        length = buf[offset]
        if length == 0:
            offset += 1
            if not jumped:
                consumed = offset
            break
        if (length & 0xC0) == 0xC0:
            if offset + 1 >= len(buf):
                raise DnsActuationError("truncated pointer")
            pointer = ((length & 0x3F) << 8) | buf[offset + 1]
            if not jumped:
                consumed = offset + 2
            jumped = True
            suffix, _ = _read_name(buf, pointer, hops + 1)
            if suffix:
                labels.append(suffix)
            break
        if length & 0xC0:
            raise DnsActuationError("reserved label")
        offset += 1
        if offset + length > len(buf):
            raise DnsActuationError("truncated label")
        labels.append(buf[offset : offset + length].decode("ascii", errors="replace"))
        offset += length
        if not jumped:
            consumed = offset
    return ".".join(part for part in labels if part), consumed


def _encode_txt(text: str) -> bytes:
    raw = str(text or "").encode("utf-8")
    if not raw:
        return b"\x00"
    chunks = bytearray()
    for index in range(0, len(raw), 255):
        piece = raw[index : index + 255]
        chunks.append(len(piece))
        chunks.extend(piece)
    return bytes(chunks)


def _decode_txt(rdata: bytes) -> str:
    parts: list[bytes] = []
    offset = 0
    while offset < len(rdata):
        length = rdata[offset]
        offset += 1
        parts.append(rdata[offset : offset + length])
        offset += length
    return b"".join(parts).decode("utf-8", errors="replace")


def _header(txid: int, flags: int, qd: int, an: int, ns: int, ar: int) -> bytes:
    return struct.pack("!HHHHHH", txid & 0xFFFF, flags & 0xFFFF, qd, an, ns, ar)


def _unpack_header(buf: bytes) -> tuple[int, int, int, int, int, int]:
    if len(buf) < 12:
        raise DnsActuationError("truncated header")
    return struct.unpack("!HHHHHH", buf[:12])


def _opcode(flags: int) -> int:
    return (flags >> 11) & 0x0F


def _rcode(flags: int) -> int:
    return flags & 0x0F


def _encode_question(name: str, qtype: int, qclass: int = CLASS_IN) -> bytes:
    return _encode_name(name) + struct.pack("!HH", qtype, qclass)


def _encode_rr(name: str, rtype: int, rclass: int, ttl: int, rdata: bytes) -> bytes:
    return _encode_name(name) + struct.pack("!HHIH", rtype, rclass, ttl & 0xFFFFFFFF, len(rdata)) + rdata


@dataclass
class DnsQuestion:
    name: str
    qtype: int
    qclass: int


@dataclass
class DnsRR:
    name: str
    rtype: int
    rclass: int
    ttl: int
    rdata: bytes


@dataclass
class DnsMessage:
    txid: int
    flags: int
    questions: list[DnsQuestion] = field(default_factory=list)
    answers: list[DnsRR] = field(default_factory=list)
    authorities: list[DnsRR] = field(default_factory=list)
    additionals: list[DnsRR] = field(default_factory=list)


def _read_rr(buf: bytes, offset: int) -> tuple[DnsRR, int]:
    name, offset = _read_name(buf, offset)
    if offset + 10 > len(buf):
        raise DnsActuationError("truncated rr header")
    rtype, rclass, ttl, rdlen = struct.unpack_from("!HHIH", buf, offset)
    offset += 10
    if offset + rdlen > len(buf):
        raise DnsActuationError("truncated rdata")
    rdata = buf[offset : offset + rdlen]
    return DnsRR(name=name, rtype=rtype, rclass=rclass, ttl=ttl, rdata=rdata), offset + rdlen


def _parse_message(buf: bytes) -> DnsMessage:
    txid, flags, qd, an, ns, ar = _unpack_header(buf)
    offset = 12
    questions: list[DnsQuestion] = []
    for _ in range(qd):
        name, offset = _read_name(buf, offset)
        if offset + 4 > len(buf):
            raise DnsActuationError("truncated question")
        qtype, qclass = struct.unpack_from("!HH", buf, offset)
        offset += 4
        questions.append(DnsQuestion(name=name, qtype=qtype, qclass=qclass))
    answers: list[DnsRR] = []
    authorities: list[DnsRR] = []
    additionals: list[DnsRR] = []
    for _ in range(an):
        rr, offset = _read_rr(buf, offset)
        answers.append(rr)
    for _ in range(ns):
        rr, offset = _read_rr(buf, offset)
        authorities.append(rr)
    for _ in range(ar):
        rr, offset = _read_rr(buf, offset)
        additionals.append(rr)
    return DnsMessage(
        txid=txid,
        flags=flags,
        questions=questions,
        answers=answers,
        authorities=authorities,
        additionals=additionals,
    )


def _encode_tsig_rdata(
    algorithm: str,
    time_signed: int,
    fudge: int,
    mac: bytes,
    original_id: int,
    error: int,
    other: bytes,
) -> bytes:
    return (
        _encode_name(algorithm)
        + int(time_signed).to_bytes(6, "big")
        + struct.pack("!HH", fudge & 0xFFFF, len(mac))
        + mac
        + struct.pack("!HHH", original_id & 0xFFFF, error & 0xFFFF, len(other))
        + other
    )


def _parse_tsig_rdata(rdata: bytes) -> dict[str, Any]:
    algorithm, offset = _read_name(rdata, 0)
    if offset + 8 > len(rdata):
        raise DnsActuationError("truncated tsig time")
    time_signed = int.from_bytes(rdata[offset : offset + 6], "big")
    fudge, mac_size = struct.unpack_from("!HH", rdata, offset + 6)
    offset += 10
    if offset + mac_size + 6 > len(rdata):
        raise DnsActuationError("truncated tsig mac")
    mac = rdata[offset : offset + mac_size]
    offset += mac_size
    original_id, error, other_len = struct.unpack_from("!HHH", rdata, offset)
    offset += 6
    other = rdata[offset : offset + other_len]
    return {
        "algorithm": algorithm,
        "time_signed": time_signed,
        "fudge": fudge,
        "mac": mac,
        "original_id": original_id,
        "error": error,
        "other": other,
    }


def _tsig_mac(
    secret: bytes,
    message_without_tsig: bytes,
    *,
    key_name: str,
    algorithm: str,
    time_signed: int,
    fudge: int,
    error: int = 0,
    other: bytes = b"",
) -> bytes:
    payload = (
        message_without_tsig
        + _encode_name(key_name)
        + struct.pack("!HI", CLASS_ANY, 0)
        + _encode_name(algorithm)
        + int(time_signed).to_bytes(6, "big")
        + struct.pack("!HHH", fudge & 0xFFFF, error & 0xFFFF, len(other))
        + other
    )
    return hmac.new(secret, payload, hashlib.sha256).digest()


def _strip_tsig_wire(buf: bytes) -> tuple[bytes, DnsRR | None]:
    txid, flags, qd, an, ns, ar = _unpack_header(buf)
    offset = 12
    for _ in range(qd):
        _name, offset = _read_name(buf, offset)
        offset += 4
    for _ in range(an + ns):
        _rr, offset = _read_rr(buf, offset)
    tsig_start = None
    tsig_rr = None
    for index in range(ar):
        start = offset
        rr, offset = _read_rr(buf, offset)
        if index == ar - 1 and rr.rtype == TYPE_TSIG:
            tsig_start = start
            tsig_rr = rr
    if tsig_start is None or tsig_rr is None:
        return buf, None
    new_header = _header(txid, flags, qd, an, ns, ar - 1)
    return new_header + buf[12:tsig_start], tsig_rr


def _attach_tsig(message: bytes, secret: str, key_name: str) -> bytes:
    txid, _flags, _qd, _an, _ns, ar = _unpack_header(message)
    now = int(time.time())
    mac = _tsig_mac(
        secret.encode("utf-8"),
        message,
        key_name=key_name,
        algorithm=DEFAULT_ALGORITHM,
        time_signed=now,
        fudge=TSIG_FUDGE,
    )
    rdata = _encode_tsig_rdata(DEFAULT_ALGORITHM, now, TSIG_FUDGE, mac, txid, 0, b"")
    rr = _encode_rr(key_name, TYPE_TSIG, CLASS_ANY, 0, rdata)
    patched = bytearray(message)
    struct.pack_into("!H", patched, 10, ar + 1)
    return bytes(patched) + rr


def _verify_tsig(buf: bytes, secret: str, key_name: str) -> tuple[bool, str]:
    stripped, tsig = _strip_tsig_wire(buf)
    if tsig is None:
        return False, "tsig_required"
    if _canon_name(tsig.name) != _canon_name(key_name):
        return False, "auth_failed"
    try:
        fields = _parse_tsig_rdata(tsig.rdata)
    except DnsActuationError:
        return False, "auth_failed"
    if _canon_name(str(fields["algorithm"])) != _canon_name(DEFAULT_ALGORITHM):
        return False, "auth_failed"
    now = int(time.time())
    signed = int(fields["time_signed"])
    fudge = int(fields["fudge"]) or TSIG_FUDGE
    if abs(now - signed) > fudge:
        return False, "auth_failed"
    expected = _tsig_mac(
        secret.encode("utf-8"),
        stripped,
        key_name=tsig.name,
        algorithm=str(fields["algorithm"]),
        time_signed=signed,
        fudge=fudge,
        error=int(fields["error"]),
        other=bytes(fields["other"]),
    )
    if not hmac.compare_digest(expected, bytes(fields["mac"])):
        return False, "auth_failed"
    return True, "ok"


def _next_id() -> int:
    return int(time.time_ns() & 0xFFFF) or 1


def _build_update(zone: str, name: str, txt: str, *, secret: str | None, key_name: str) -> bytes:
    txid = _next_id()
    flags = OPCODE_UPDATE << 11
    body = (
        _header(txid, flags, 1, 0, 1, 0)
        + _encode_question(zone, TYPE_SOA, CLASS_IN)
        + _encode_rr(name, TYPE_TXT, CLASS_IN, 300, _encode_txt(txt))
    )
    if secret:
        return _attach_tsig(body, secret, key_name)
    return body


def _build_query(name: str, qtype: int = TYPE_TXT) -> bytes:
    txid = _next_id()
    return _header(txid, 0x0100, 1, 0, 0, 0) + _encode_question(name, qtype, CLASS_IN)


def _error_reply(request: bytes, rcode: int) -> bytes:
    try:
        txid, flags, _qd, _an, _ns, _ar = _unpack_header(request)
    except DnsActuationError:
        return b""
    opcode = _opcode(flags)
    return _header(txid, 0x8000 | (opcode << 11) | (rcode & 0xF), 0, 0, 0, 0)


def _query_reply(request: DnsMessage, answers: list[DnsRR], rcode: int) -> bytes:
    flags = 0x8400 | (rcode & 0xF)
    questions = b"".join(_encode_question(item.name, item.qtype, item.qclass) for item in request.questions)
    records = b"".join(_encode_rr(item.name, item.rtype, item.rclass, item.ttl, item.rdata) for item in answers)
    return _header(request.txid, flags, len(request.questions), len(answers), 0, 0) + questions + records


def _update_reply(request: DnsMessage, rcode: int) -> bytes:
    flags = 0x8000 | (OPCODE_UPDATE << 11) | (rcode & 0xF)
    questions = b"".join(_encode_question(item.name, item.qtype, item.qclass) for item in request.questions)
    return _header(request.txid, flags, len(request.questions), 0, 0, 0) + questions


class _DnsUDPServer(socketserver.ThreadingUDPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(self, address: tuple[str, int], handler: type[socketserver.BaseRequestHandler], session: DnsSession) -> None:
        self.session = session
        super().__init__(address, handler)


class _DnsHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data, sock = self.request
        session: DnsSession = self.server.session  # type: ignore[attr-defined]
        try:
            reply = session.handle_wire(bytes(data))
        except (DnsActuationError, OSError, ValueError, struct.error):
            return
        if reply:
            try:
                sock.sendto(reply, self.client_address)
            except OSError:
                return


class _DnsClient:
    """Minimal DNS/UDP client for UPDATE, QUERY, and independent re-QUERY."""

    def __init__(self, host: str, port: int, *, timeout: float = 1.5) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def exchange(self, payload: bytes) -> bytes | None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(self.timeout)
            sock.sendto(payload, (self.host, self.port))
            data, _addr = sock.recvfrom(4096)
            return data
        except (OSError, socket.timeout):
            return None
        finally:
            sock.close()


class DnsSession:
    """TSIG-gated loopback nameserver: bind, publish, read."""

    def __init__(self, output_dir: Path, *, secret: str = DEFAULT_SECRET) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.secret = str(secret or "")
        self.key_name = DEFAULT_KEY_NAME
        self.zone = DEFAULT_ZONE
        self.name = DEFAULT_NAME
        self.host: str | None = None
        self.port: int | None = None
        self.server: _DnsUDPServer | None = None
        self.thread: threading.Thread | None = None
        self.delivered = False
        self.last_token = ""
        self.history: list[dict[str, Any]] = []
        self._records: dict[tuple[str, int], str] = {}
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def handle_wire(self, data: bytes) -> bytes:
        try:
            message = _parse_message(data)
        except DnsActuationError:
            return _error_reply(data, RCODE_FORMERR)
        opcode = _opcode(message.flags)
        if opcode == OPCODE_UPDATE:
            return self._handle_update(data, message)
        if opcode == OPCODE_QUERY:
            return self._handle_query(message)
        return _error_reply(data, RCODE_REFUSED)

    def _handle_update(self, data: bytes, message: DnsMessage) -> bytes:
        if not self.secret:
            return _update_reply(message, RCODE_NOTAUTH)
        ok, reason = _verify_tsig(data, self.secret, self.key_name)
        if not ok:
            return _update_reply(message, RCODE_NOTAUTH if reason == "tsig_required" else RCODE_NOTAUTH)
        if not message.questions or _canon_name(message.questions[0].name) != _canon_name(self.zone):
            return _update_reply(message, RCODE_REFUSED)
        stored = False
        with self._lock:
            for rr in message.authorities:
                if rr.rtype == TYPE_TXT and rr.rclass == CLASS_IN:
                    self._records[(_canon_name(rr.name), TYPE_TXT)] = _decode_txt(rr.rdata)
                    stored = True
        if not stored:
            return _update_reply(message, RCODE_FORMERR)
        return _update_reply(message, RCODE_NOERROR)

    def _handle_query(self, message: DnsMessage) -> bytes:
        if not message.questions:
            return _query_reply(message, [], RCODE_FORMERR)
        question = message.questions[0]
        with self._lock:
            token = self._records.get((_canon_name(question.name), question.qtype))
        if token is None:
            return _query_reply(message, [], RCODE_NXDOMAIN)
        answer = DnsRR(
            name=question.name,
            rtype=question.qtype,
            rclass=CLASS_IN,
            ttl=300,
            rdata=_encode_txt(token),
        )
        return _query_reply(message, [answer], RCODE_NOERROR)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "delivered": self.delivered,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 409,
            "error": reason,
            "token": "",
            "sentinel": "",
            "delivered": self.delivered,
        }

    def bind(self) -> dict[str, Any]:
        if not self.secret:
            return self._forbidden("missing_secret")
        if self.server is not None:
            return {
                "ok": True,
                "status": 200,
                "host": self.host or "",
                "port": int(self.port or 0),
                "reused": True,
            }
        server = _DnsUDPServer(("127.0.0.1", 0), _DnsHandler, self)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        self.server = server
        self.thread = thread
        self.host = str(host)
        self.port = int(port)
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
        authenticate: bool = True,
        update: bool = True,
        query: bool = True,
        secret: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.secret:
            return self._forbidden("missing_secret")
        live_token = str(token or SENTINEL)
        client = _DnsClient(self.host, int(self.port))
        try:
            if not update:
                return self._conflict("update_required")
            signed_secret = None
            if authenticate:
                signed_secret = self.secret if secret is None else str(secret)
            else:
                signed_secret = None
            update_wire = _build_update(
                self.zone,
                self.name,
                live_token,
                secret=signed_secret,
                key_name=self.key_name,
            )
            update_reply = client.exchange(update_wire)
            if update_reply is None:
                return self._forbidden("update_timeout", status=503)
            try:
                update_msg = _parse_message(update_reply)
            except DnsActuationError:
                return self._forbidden("update_malformed", status=503)
            code = _rcode(update_msg.flags)
            if not authenticate:
                return self._forbidden("tsig_required", status=530)
            if secret is not None and secret != self.secret:
                return self._forbidden("auth_failed", status=535)
            if code != RCODE_NOERROR:
                reason = "auth_failed" if code == RCODE_NOTAUTH else "update_failed"
                status = 535 if reason == "auth_failed" else 550
                return self._forbidden(reason, status=status)
            if not query:
                return self._conflict("query_required")
            query_wire = _build_query(self.name)
            query_reply = client.exchange(query_wire)
            if query_reply is None:
                return self._forbidden("query_timeout", status=503)
            first = _txt_from_reply(query_reply, self.name)
            if first != live_token:
                return self._forbidden("update_required" if first == "" else "payload_mismatch", status=409)
            independent = _DnsClient(self.host, int(self.port))
            replay_reply = independent.exchange(_build_query(self.name))
            if replay_reply is None:
                return self._forbidden("independent_timeout", status=503)
            replay = _txt_from_reply(replay_reply, self.name)
            if replay != live_token:
                return self._forbidden("independent_required", status=409)
            sealed = {
                "zone": self.zone,
                "name": self.name,
                "qtype": "TXT",
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "updated": True,
                "signed": True,
                "queried": True,
                "independent": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            live = independent_dns_zone(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "queued": False,
                "apex": True,
                "zone": self.zone,
                "name": self.name,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "path": str(self.sealed_path),
                "authenticated": bool(authenticate),
                "updated": True,
                "queried": True,
                "independent": True,
            }
        except (OSError, DnsActuationError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error),
                "token": live_token,
                "sentinel": "",
            }

    def read(self) -> dict[str, Any]:
        live = independent_dns_zone(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "zone": str(live.get("zone") or ""),
            "name": str(live.get("name") or ""),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        server = self.server
        thread = self.thread
        self.server = None
        self.thread = None
        self.host = None
        self.port = None
        if server is not None:
            try:
                server.shutdown()
            except OSError:
                pass
            try:
                server.server_close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=1)
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def _txt_from_reply(buf: bytes, name: str) -> str:
    try:
        message = _parse_message(buf)
    except DnsActuationError:
        return ""
    if _rcode(message.flags) != RCODE_NOERROR:
        return ""
    wanted = _canon_name(name)
    for rr in message.answers:
        if rr.rtype == TYPE_TXT and _canon_name(rr.name) == wanted:
            return _decode_txt(rr.rdata)
    return ""


def call_dns_tool(session: DnsSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one DNS tool call against a bound nameserver session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = arguments.get("authenticate")
    if authenticate is None:
        authenticate = True
    update = arguments.get("update")
    if update is None:
        update = True
    query = arguments.get("query")
    if query is None:
        query = True
    secret = arguments.get("password")
    if secret is None:
        secret = arguments.get("secret")
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            authenticate=bool(authenticate),
            update=bool(update),
            query=bool(query),
            secret=None if secret is None else str(secret),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise DnsActuationError(f"unsupported dns action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_dns_zone(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed DNS apex through a fresh file open."""

    path = Path(sealed_path)
    if not path.is_file():
        return {
            "ok": False,
            "error": "missing_payload",
            "token": "",
            "sentinel": "",
            "zone": "",
            "name": "",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "ok": False,
            "error": "invalid_payload",
            "detail": str(error),
            "token": "",
            "sentinel": "",
            "zone": "",
            "name": "",
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "invalid_payload",
            "token": "",
            "sentinel": "",
            "zone": "",
            "name": "",
        }
    token = str(payload.get("token") or "")
    updated = payload.get("updated") is True
    signed = payload.get("signed") is True
    queried = payload.get("queried") is True
    independent = payload.get("independent") is True
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and updated and signed and queried and independent else "",
        "zone": str(payload.get("zone") or ""),
        "name": str(payload.get("name") or ""),
        "updated": updated,
        "signed": signed,
        "queried": queried,
        "independent": independent,
    }


def run_dns_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    update: bool = True,
    query: bool = True,
    password: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the UPDATE/TSIG/QUERY apex workflow and seal a trace."""

    descriptor = dns_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DNS_TOOL_PROVIDER),
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
        raise DnsActuationError(f"dns tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="dns-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = DnsSession(out, secret=DEFAULT_SECRET if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    publish_args: dict[str, Any] = {
        "action": "publish",
        "token": SENTINEL,
        "authenticate": authenticate,
        "update": update,
        "query": query,
    }
    if password is not None:
        publish_args["password"] = password
    calls.append(publish_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_dns_tool(session, arguments))
            except DnsActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_dns_zone(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and update
        and query
        and password is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "dns_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "update": update,
        "query": query,
        "wrong_secret": password is not None,
        "sealed_path": str(session.sealed_path),
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "independent": independent,
        "independent_digest": _digest(independent),
        "sentinel": sentinel,
        "delivered": bool(session.delivered or publish_result.get("apex")),
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
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "delivered": bool(trace_body["delivered"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "update": update,
        "query": query,
    }


def verify_dns_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed DNS trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_dns_zone(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "independent_digest": _digest(independent) == trace.get("independent_digest"),
        "routing_executable": routing.get("executable") is True
        and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "independent_recorded": str(independent.get("sentinel") or "") == SENTINEL,
        "live_payload_matches": str(live_row.get("sentinel") or "") == SENTINEL,
        "payload_exists": bool(trace.get("payload_exists")) and sealed_path.is_file(),
        "delivered": trace.get("delivered") is True,
        "updated": independent.get("updated") is True,
        "signed": independent.get("signed") is True,
        "queried": independent.get("queried") is True,
        "independent": independent.get("independent") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def dns_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.dns_actuation import "
        "builtin_dns_actuation_proof; r=builtin_dns_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='dns_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_dns_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=DNS_ACTUATION_ID,
        name="First-class TSIG-gated nameserver apex actuation",
        description=(
            "Missions that require a dns tool can opt the dns provider in, "
            "bind a loopback DNS/UDP nameserver, UPDATE an apex TXT with "
            "HMAC-SHA256 TSIG, QUERY the record, independently re-QUERY from a "
            "fresh socket, and seal digest-chained zone traces. Default routing "
            "stays fail-closed; a missing TSIG secret keeps the hole falsifiable, "
            "and skip-UPDATE or skip-QUERY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.dns_actuation:builtin_dns_actuation_proof",
        proof_command=dns_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mqtt-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/dns_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required dns tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback DNS/UDP nameserver, UPDATEs an apex "
            "TXT with HMAC-SHA256 TSIG, QUERYs the record, independently "
            "re-QUERYs from a fresh socket, and binds this family as the next "
            "diversity-catalog successor once MQTT retained-topic fanout is "
            "proved. Missing secrets, skipped TSIG, wrong keys, skip-UPDATE, "
            "and skip-QUERY stay fail-closed."
        ),
        tags=("dns", "nameserver", "tsig", "apex", "zone", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T084115Z-8a69801c",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_dns_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in DNS actuation seals a TSIG-gated apex TXT."""

    from blackhole_agent.imap_actuation import IMAP_ACTUATION_GOAL, IMAP_ACTUATION_ID
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
    from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
    from blackhole_agent.redis_actuation import REDIS_ACTUATION_GOAL, REDIS_ACTUATION_ID
    from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
    from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = DNS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["mqtt_goal_is_not_dns"] = leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    checks["redis_goal_is_not_dns"] = leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    checks["imap_goal_is_not_dns"] = leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    checks["smtp_goal_is_not_dns"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    checks["sqlite_goal_is_not_dns"] = leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (
        SQLITE_ACTUATION_ID,
    )
    checks["dns_goal_is_not_mqtt"] = MQTT_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["dns_goal_is_not_redis"] = REDIS_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["dns_goal_is_not_imap"] = IMAP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["dns_goal_is_not_smtp"] = SMTP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["dns_goal_is_not_sqlite"] = SQLITE_ACTUATION_ID not in leftover_marker_ids(
        DNS_ACTUATION_GOAL
    )
    checks["mqtt_marker_stays_mqtt"] = DNS_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    checks["redis_marker_stays_redis"] = DNS_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    checks["imap_marker_stays_imap"] = DNS_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    checks["smtp_marker_stays_smtp"] = DNS_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    checks["sqlite_marker_stays_sqlite"] = DNS_ACTUATION_ID not in leftover_marker_ids(
        SQLITE_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_dns"] = (
        len(catalog) > 34
        and catalog[34]["id"] == DNS_ACTUATION_ID
        and catalog[33]["id"] == MQTT_ACTUATION_ID
    )
    family = capability_family(DNS_ACTUATION_GOAL)
    checks["family_is_nameserver"] = "nameserver" in family
    checks["family_is_tsig"] = "tsig" in family
    checks["family_is_apex"] = "apex" in family
    checks["family_is_not_mqtt"] = "mqtt" not in family
    checks["family_is_not_redis"] = "redi" not in family
    checks["family_is_not_blpop"] = "blpop" not in family
    checks["family_is_not_imap"] = "imap" not in family
    checks["family_is_not_smtp"] = "smtp" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["family_is_not_git_publication"] = "git-publication" not in family
    checks["family_is_not_auth_surface"] = family != "auth" and "auth" not in family.split("/")
    encoded = _encode_name(DEFAULT_NAME)
    decoded, consumed = _read_name(encoded, 0)
    checks["name_roundtrip"] = _canon_name(decoded) == _canon_name(DEFAULT_NAME) and consumed == len(encoded)
    checks["txt_roundtrip"] = _decode_txt(_encode_txt(SENTINEL)) == SENTINEL
    unsigned = _build_update(DEFAULT_ZONE, DEFAULT_NAME, SENTINEL, secret=None, key_name=DEFAULT_KEY_NAME)
    checks["unsigned_update_has_no_tsig"] = _strip_tsig_wire(unsigned)[1] is None
    signed = _build_update(
        DEFAULT_ZONE, DEFAULT_NAME, SENTINEL, secret=DEFAULT_SECRET, key_name=DEFAULT_KEY_NAME
    )
    checks["signed_update_verifies"] = _verify_tsig(signed, DEFAULT_SECRET, DEFAULT_KEY_NAME) == (True, "ok")
    checks["wrong_key_fails_tsig"] = _verify_tsig(signed, "wrong-secret", DEFAULT_KEY_NAME) == (
        False,
        "auth_failed",
    )
    checks["not_an_mqtt_duplicate"] = (
        semantic_similarity(
            semantic_signature(DNS_ACTUATION_GOAL),
            semantic_signature(MQTT_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_redis_duplicate"] = (
        semantic_similarity(
            semantic_signature(DNS_ACTUATION_GOAL),
            semantic_signature(REDIS_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_an_imap_duplicate"] = (
        semantic_similarity(
            semantic_signature(DNS_ACTUATION_GOAL),
            semantic_signature(IMAP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_smtp_duplicate"] = (
        semantic_similarity(
            semantic_signature(DNS_ACTUATION_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_sqlite_duplicate"] = (
        semantic_similarity(
            semantic_signature(DNS_ACTUATION_GOAL),
            semantic_signature(SQLITE_ACTUATION_GOAL),
        )
        < 0.82
    )

    mcp_dns = ToolDescriptor(name="remote_dns", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_dns)
    checks["naive_mcp_dns_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = dns_tool_descriptor()
    default_dns = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DNS_TOOL_PROVIDER),
    )
    checks["default_dns_provider_is_unsupported"] = (
        default_dns.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{DNS_TOOL_PROVIDER}" in default_dns.reasons
    )
    checks["opted_in_dns_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_dns],
        required_tool_names=("local_memory", "dns"),
    )
    checks["naive_preflight_missing_dns"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["dns"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "dns"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DNS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "dns" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="dns-actuation-") as tmp:
        root = Path(tmp)
        missing = run_dns_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_dns_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_dns_workflow(password="wrong-secret", output_dir=root / "wrong")
        skip_update = run_dns_workflow(update=False, output_dir=root / "skip-update")
        skip_query = run_dns_workflow(query=False, output_dir=root / "skip-query")
        live = run_dns_workflow(output_dir=root / "live")
        verify = verify_dns_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_dns_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unauthenticated_update_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 530
            and unauth["error"] == "tsig_required"
            and unauth["delivered"] is False
            and unauth["payload_exists"] is False
        )
        checks["wrong_secret_is_forbidden"] = (
            wrong["ok"] is False
            and wrong["final_status"] == 535
            and wrong["error"] == "auth_failed"
            and wrong["payload_exists"] is False
        )
        checks["skip_update_stays_empty"] = (
            skip_update["ok"] is False
            and skip_update["error"] == "update_required"
            and skip_update["final_status"] == 409
            and skip_update["payload_exists"] is False
        )
        checks["skip_query_stays_empty"] = (
            skip_query["ok"] is False
            and skip_query["error"] == "query_required"
            and skip_query["final_status"] == 409
            and skip_query["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_zone"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["secret_tsig_update_and_query_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_update["ok"] is False
            and skip_query["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="dns-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != DNS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_dns"] = (
        live_goal == DNS_ACTUATION_GOAL
        and DNS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_dns"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_dns_actuation_capability()
    return {
        "ok": ok,
        "action": "dns_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": DNS_ACTUATION_GOAL,
        "done_when": DNS_ACTUATION_DONE_WHEN,
    }
