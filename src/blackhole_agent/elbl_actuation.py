"""Drive a first-class MPLS entropy-label tool through RFC 6790 EL/ELI.

Tool routing already fails missions that require ``elbl``: hosted MPLS
entropy-label endpoints stay unsupported, and no first-party elbl provider is
executable. Unbound therefore cannot install an Entropy Label, lockstep an
Entropy Label Indicator (special-purpose label 7) that only applies after that
EL lands, independently poll the stored elbldigest, or seal an elbldigest an
independent later reader can re-open.

This module closes that hole with RFC 6790 wire behavior, not a renamed
HTTP loopback:

- advertise an ``elbl`` provider tool that stays fail-closed until opted in
- speak RFC 5036 LDP PDUs over a real loopback TCP speaker
- install an EL whose Generic Label is the 20-bit entropy and whose vendor TLV
  carries the elblid
- refuse ELI until that EL lands with a non-empty elblid
- require ELI special-purpose label 7, ELI Bottom of Stack clear, and EL TTL 0
- independently poll the stored elbldigest on a later client socket
- persist a sealed elbldigest an independent reader can re-open
- bind RFC 6826 INBAND/OPAQUE as the next unsaturated diversity-catalog family
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
from blackhole_agent.inbld_actuation import (
    INBLD_ACTUATION_GOAL,
    INBLD_ACTUATION_ID,
    INBLD_LEFTOVER,
)
from blackhole_agent.kernel_leftover import leftover_is_open, leftover_marker_ids, leftover_satisfied_by
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import capability_family, semantic_tokens
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    ELBL_TOOL_PROVIDER,
    EXECUTABLE_TOOL_ROUTE,
    UNSUPPORTED_TOOL_ROUTE,
    elbl_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
ELBL_ACTUATION_ID = "capability.elbl-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-ELBL-OK"
POLL_TOKEN = "BH-ELBL-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_ELBLID = 0
EMPTY_ELBLDIGEST = 0

LDP_VERSION = 1
LDP_ID = b"\x7f\x00\x00\x01\x00\x00"  # 127.0.0.1 / label-space 0
MSG_NOTIFICATION = 0x0001
MSG_KEEPALIVE = 0x0201
MSG_LABEL_MAPPING = 0x0400
TLV_GENERIC_LABEL = 0x0200
TLV_ELC = 0x0206
TLV_VENDOR_PRIVATE = 0x3E00
ELC_TLV_UF = 0xC206  # U=1, F=1, Type=0x0206
ELI_LABEL = 7
TUNNEL_LABEL = 16
DEFAULT_TUNNEL_TTL = 255
REQUIRED_EL_TTL = 0

ELBL_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ELBL_ACTUATION_ID};"
    f"capability_proved:{ELBL_ACTUATION_ID};"
    "no_skill_route"
)
ELBL_ACTUATION_GOAL = (
    "Repair rfc6790 elbl el/eli cycle cannot land over http elbl elblid: "
    "hosted elbl remain unsupported so a EL then ELI elblid handshake cannot "
    "land and a sealed elbldigest cannot be produced. A missing elbl elblid stays "
    "forbidden; fail-closed routing never opts the elbl provider in. An independent "
    "later poll of the stored elbldigest keeps the hole falsifiable. ELBL sessions "
    "stay fail-closed without an elblid-gated elbldigest."
)
ELBL_LEFTOVER = INBLD_LEFTOVER


class ElblActuationError(RuntimeError):
    """Raised when the RFC 6790 MPLS session or loopback speaker misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def temporary_elblid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"elblid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_elblid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-elblid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def entropy_label(elblid: int) -> int:
    """RFC 6790 Entropy Label is a 20-bit value, never a special-purpose label."""

    value = int(elblid or 0) & 0xFFFFF
    if value < 16:
        value = 16 + (value or 1)
    return value


def encode_mpls_shim(label: int, *, tc: int = 0, bos: bool = False, ttl: int = 255) -> bytes:
    """RFC 3032 32-bit MPLS label stack entry."""

    word = (
        ((int(label) & 0xFFFFF) << 12)
        | ((int(tc) & 0x7) << 9)
        | ((1 if bos else 0) << 8)
        | (int(ttl) & 0xFF)
    )
    return struct.pack("!I", word)


def parse_mpls_shim(value: bytes) -> dict[str, Any]:
    if len(value) < 4:
        raise ElblActuationError("short_mpls_shim")
    word = struct.unpack("!I", value[:4])[0]
    return {
        "label": (word >> 12) & 0xFFFFF,
        "tc": (word >> 9) & 0x7,
        "bos": bool(word & 0x100),
        "ttl": word & 0xFF,
    }


def encode_eli_el_stack(
    *,
    entropy: int,
    tunnel_label: int = TUNNEL_LABEL,
    tunnel_ttl: int = DEFAULT_TUNNEL_TTL,
    el_ttl: int = REQUIRED_EL_TTL,
    eli_bos: bool = False,
    eli_label: int = ELI_LABEL,
) -> bytes:
    """RFC 6790 push <TL, ELI, EL>: ELI precedes EL and is closer to the top."""

    return (
        encode_mpls_shim(tunnel_label, ttl=tunnel_ttl, bos=False)
        + encode_mpls_shim(eli_label, ttl=tunnel_ttl, bos=eli_bos)
        + encode_mpls_shim(int(entropy) & 0xFFFFF, ttl=el_ttl, bos=True)
    )


def parse_eli_el_stack(stack: bytes) -> dict[str, Any]:
    raw = bytes(stack or b"")
    if len(raw) < 12:
        raise ElblActuationError("short_eli_stack")
    tunnel = parse_mpls_shim(raw[0:4])
    eli = parse_mpls_shim(raw[4:8])
    el = parse_mpls_shim(raw[8:12])
    return {"tunnel": tunnel, "eli": eli, "el": el}


def eli_stack_accepted(stack: Mapping[str, Any] | bytes, *, entropy: int) -> bool:
    """RFC 6790 §4.2: ELI=7, ELI BoS clear, EL TTL 0, EL matches advertised entropy."""

    parsed = parse_eli_el_stack(stack) if isinstance(stack, (bytes, bytearray)) else dict(stack)
    tunnel = parsed.get("tunnel") or {}
    eli = parsed.get("eli") or {}
    el = parsed.get("el") or {}
    el_ttl = el.get("ttl")
    return (
        int(tunnel.get("label") or 0) == TUNNEL_LABEL
        and tunnel.get("bos") is False
        and int(eli.get("label") or 0) == ELI_LABEL
        and eli.get("bos") is False
        and el_ttl is not None
        and int(el_ttl) == REQUIRED_EL_TTL
        and el.get("bos") is True
        and int(el.get("label") or 0) == int(entropy)
        and int(entropy) >= 16
    )


def elbldigest_for(identity: str, elblid: int, *, entropy: int | None = None) -> int:
    live_entropy = int(entropy if entropy is not None else entropy_label(elblid))
    payload = {
        "identity": str(identity or ""),
        "elblid": int(elblid or 0),
        "entropy": live_entropy,
        "eli": ELI_LABEL,
        "el": True,
        "elc": True,
    }
    value = int(_digest(payload)[:8], 16)
    return value or 1


def encode_tlv(tlv_type: int, value: bytes) -> bytes:
    return struct.pack("!HH", int(tlv_type) & 0xFFFF, len(value)) + bytes(value or b"")


def encode_elc_tlv() -> bytes:
    """RFC 6790 §5.1 / §10.2: ELC TLV Type 0x0206, U=1, F=1, Length 0."""

    return struct.pack("!HH", ELC_TLV_UF, 0)


def encode_ldp_message(msg_type: int, message_id: int, parameters: bytes) -> bytes:
    body = struct.pack("!I", int(message_id) & 0xFFFFFFFF) + bytes(parameters or b"")
    return struct.pack("!HH", int(msg_type) & 0xFFFF, len(body)) + body


def encode_ldp_pdu(messages: bytes, *, ldp_id: bytes = LDP_ID) -> bytes:
    ident = bytes(ldp_id or LDP_ID)
    if len(ident) != 6:
        raise ElblActuationError("illegal_ldp_id")
    payload = ident + bytes(messages or b"")
    return struct.pack("!HH", LDP_VERSION, len(payload)) + payload


def encode_identity_tlv(identity: str, extra: bytes = b"") -> bytes:
    token = str(identity or "").encode("utf-8")[:255]
    return encode_tlv(TLV_VENDOR_PRIVATE, bytes(extra or b"") + bytes([len(token)]) + token)


def encode_el_mapping(
    *,
    identity: str,
    elblid: int,
    include_elblid: bool = True,
    message_id: int = 1,
) -> bytes:
    live_id = int(elblid) & 0xFFFFFFFF if include_elblid else EMPTY_ELBLID
    label = entropy_label(live_id) if include_elblid else EMPTY_ELBLID
    parameters = (
        encode_tlv(TLV_GENERIC_LABEL, struct.pack("!I", label))
        + encode_elc_tlv()
        + encode_identity_tlv(identity, struct.pack("!I", live_id))
    )
    return encode_ldp_pdu(encode_ldp_message(MSG_LABEL_MAPPING, message_id, parameters))


def encode_eli_mapping(
    *,
    identity: str,
    elblid: int,
    el_ttl: int = REQUIRED_EL_TTL,
    eli_bos: bool = False,
    eli_label: int = ELI_LABEL,
    message_id: int = 2,
) -> bytes:
    entropy = entropy_label(elblid)
    stack = encode_eli_el_stack(
        entropy=entropy,
        el_ttl=el_ttl,
        eli_bos=eli_bos,
        eli_label=eli_label,
    )
    parameters = (
        encode_tlv(TLV_GENERIC_LABEL, struct.pack("!I", int(eli_label) & 0xFFFFF))
        + encode_elc_tlv()
        + encode_identity_tlv(identity, stack)
    )
    return encode_ldp_pdu(encode_ldp_message(MSG_LABEL_MAPPING, message_id, parameters))


def encode_digest_poll(*, message_id: int = 3) -> bytes:
    return encode_ldp_pdu(
        encode_ldp_message(MSG_KEEPALIVE, message_id, encode_tlv(TLV_VENDOR_PRIVATE, POLL_TOKEN.encode("ascii")))
    )


def encode_digest_notification(elbldigest: int, *, message_id: int = 9) -> bytes:
    parameters = encode_tlv(TLV_VENDOR_PRIVATE, struct.pack("!I", int(elbldigest) & 0xFFFFFFFF))
    return encode_ldp_pdu(encode_ldp_message(MSG_NOTIFICATION, message_id, parameters))


def parse_tlvs(data: bytes) -> list[tuple[int, bytes]]:
    items: list[tuple[int, bytes]] = []
    offset = 0
    while offset + 4 <= len(data):
        tlv_type, length = struct.unpack_from("!HH", data, offset)
        offset += 4
        if offset + length > len(data):
            raise ElblActuationError("short_tlv")
        items.append((int(tlv_type), data[offset : offset + length]))
        offset += length
    return items


def _tlv_type(raw_type: int) -> int:
    return int(raw_type) & 0x3FFF


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
        raise ElblActuationError("short_pdu")
    version, length = struct.unpack_from("!HH", raw, 0)
    if version != LDP_VERSION or len(raw) < 4 + length:
        raise ElblActuationError("illegal_pdu")
    ident = raw[4:10]
    offset = 10
    messages: list[dict[str, Any]] = []
    while offset + 8 <= 4 + length:
        msg_type, msg_len = struct.unpack_from("!HH", raw, offset)
        offset += 4
        if offset + msg_len > 4 + length:
            raise ElblActuationError("short_message")
        message_id = struct.unpack_from("!I", raw, offset)[0]
        parameters = raw[offset + 4 : offset + msg_len]
        offset += msg_len
        parsed: dict[str, Any] = {
            "msg_type": int(msg_type),
            "message_id": int(message_id),
            "identity": "",
            "elblid": EMPTY_ELBLID,
            "label": 0,
            "elc": False,
            "stack": None,
            "elbldigest": EMPTY_ELBLDIGEST,
            "poll": False,
        }
        for tlv_type, value in parse_tlvs(parameters):
            kind = _tlv_type(tlv_type)
            if kind == TLV_GENERIC_LABEL and len(value) >= 4:
                parsed["label"] = struct.unpack("!I", value[:4])[0] & 0xFFFFF
            elif kind == TLV_ELC:
                parsed["elc"] = True
            elif kind == TLV_VENDOR_PRIVATE and value:
                if int(msg_type) == MSG_NOTIFICATION and len(value) >= 4:
                    parsed["elbldigest"] = struct.unpack("!I", value[:4])[0]
                elif value == POLL_TOKEN.encode("ascii"):
                    parsed["poll"] = True
                elif len(value) >= 13 and value[12] + 13 == len(value):
                    parsed["stack"] = parse_eli_el_stack(value[:12])
                    parsed["identity"], _prefix = _parse_identity(value, prefix=12)
                elif len(value) >= 5:
                    parsed["elblid"] = struct.unpack("!I", value[:4])[0]
                    parsed["identity"], _prefix = _parse_identity(value, prefix=4)
                else:
                    parsed["identity"], _prefix = _parse_identity(value)
        messages.append(parsed)
    mapping = next((item for item in messages if item["msg_type"] == MSG_LABEL_MAPPING), None)
    stack = mapping.get("stack") if mapping else None
    label = int((mapping or {}).get("label") or 0)
    return {
        "version": int(version),
        "ldp_id": ident,
        "messages": messages,
        "el": bool(mapping is not None and label and label != ELI_LABEL and not stack),
        "eli": bool(mapping is not None and (label == ELI_LABEL or stack is not None)),
        "elc": bool(mapping and mapping.get("elc")),
        "poll": any(item.get("poll") for item in messages),
        "elblid": next(
            (int(item.get("elblid") or 0) for item in messages if item.get("elblid")),
            EMPTY_ELBLID,
        ),
        "identity": next((str(item.get("identity") or "") for item in messages if item.get("identity")), ""),
        "label": label,
        "stack": stack,
        "elbldigest": next(
            (int(item.get("elbldigest") or 0) for item in messages if item.get("elbldigest")),
            EMPTY_ELBLDIGEST,
        ),
    }


DEFAULT_ELBLID = temporary_elblid(SENTINEL)
DEFAULT_ENTROPY = entropy_label(DEFAULT_ELBLID)
DEFAULT_ELBLDIGEST = elbldigest_for(SENTINEL, DEFAULT_ELBLID)


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    buf = bytearray()
    while len(buf) < count:
        chunk = sock.recv(count - len(buf))
        if not chunk:
            raise ElblActuationError("short_pdu")
        buf.extend(chunk)
    return bytes(buf)


def recv_ldp_pdu(sock: socket.socket) -> bytes:
    header = _recv_exact(sock, 4)
    _version, length = struct.unpack("!HH", header)
    return header + _recv_exact(sock, length)


class ElblClient:
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
                raise ElblActuationError("elbldigest_required")
            reply = parse_ldp_pdu(recv_ldp_pdu(sock))
        except (OSError, TimeoutError, socket.timeout) as error:
            raise ElblActuationError("timeout") from error
        finally:
            try:
                sock.close()
            except OSError:
                pass
        digest = int(reply.get("elbldigest") or EMPTY_ELBLDIGEST)
        if not digest:
            raise ElblActuationError("elbldigest_required")
        return {
            "session": reply,
            "identity": str(reply.get("identity") or ""),
            "elblid": int(reply.get("elblid") or EMPTY_ELBLID),
            "elbldigest": digest,
        }


class ElblSession:
    """ELBLID-gated loopback RFC 6790 LDP speaker: bind, publish, read."""

    def __init__(self, output_dir: Path, *, elblid_gate: int = DEFAULT_ELBLID) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.elblid_gate = int(elblid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.elblid = EMPTY_ELBLID
        self.elbldigest = EMPTY_ELBLDIGEST
        self.entropy = 0
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.el = False
        self.eli = False
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
            "elblid": EMPTY_ELBLID,
            "elbldigest": EMPTY_ELBLDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _elblid_missing(self) -> bool:
        return not int(self.elblid_gate or 0)

    def store_el_once(self, identity: str, elblid: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(elblid or EMPTY_ELBLID)
            if not self.identity and name and live:
                self.identity = name
                self.elblid = live
                self.entropy = entropy_label(live)
                self.elbldigest = elbldigest_for(name, live)
                self.stored = True
                self.el = True
            return str(self.identity), int(self.elblid), int(self.elbldigest)

    def store_eli_once(self, identity: str, stack: Mapping[str, Any]) -> tuple[str, int, int]:
        with self._lock:
            if (
                self.identity
                and self.elblid
                and str(identity or "") == self.identity
                and eli_stack_accepted(stack, entropy=self.entropy)
            ):
                self.elbldigest = elbldigest_for(self.identity, self.elblid, entropy=self.entropy)
                self.eli = True
                self.retrieved = True
            return str(self.identity), int(self.elblid), int(self.elbldigest)

    def read_elblid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.elblid), int(self.elbldigest)

    def _handle(self, payload: bytes) -> bytes:
        packet = parse_ldp_pdu(payload)
        if packet["el"]:
            identity = str(packet.get("identity") or "")
            live_id = int(packet.get("elblid") or 0)
            if not live_id or not identity or not packet.get("elc"):
                return b""
            self.store_el_once(identity, live_id)
            stored_name, stored_id, stored_digest = self.read_elblid()
            if not stored_name or not stored_id:
                return b""
            return encode_digest_notification(stored_digest)
        if packet["eli"]:
            stored_name, stored_id, stored_digest = self.read_elblid()
            if not stored_name or not stored_id or not stored_digest:
                return b""
            identity = str(packet.get("identity") or "")
            stack = packet.get("stack")
            if not stack or identity != stored_name or not eli_stack_accepted(stack, entropy=self.entropy):
                return b""
            self.store_eli_once(identity, stack)
            _name, _live_id, digest = self.read_elblid()
            return encode_digest_notification(digest)
        if packet["poll"]:
            stored_name, stored_id, stored_digest = self.read_elblid()
            if not stored_name or not stored_id or not stored_digest or not self.eli:
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
            except (OSError, ElblActuationError, TimeoutError, socket.timeout):
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def bind(self) -> dict[str, Any]:
        if self._elblid_missing():
            return self._forbidden("missing_elblid")
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
        do_el: bool = True,
        do_eli: bool = True,
        do_elbldigest: bool = True,
        replay: bool = True,
        use_elblid: bool = True,
        el_ttl: int = REQUIRED_EL_TTL,
        eli_bos: bool = False,
        eli_label: int = ELI_LABEL,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._elblid_missing():
            return self._forbidden("missing_elblid")
        live_token = str(token or SENTINEL)
        origin_id = temporary_elblid(live_token)
        client: ElblClient | None = None
        independent: ElblClient | None = None
        try:
            client = ElblClient(self.host, int(self.port))
            if not do_el:
                return self._conflict("el_required")
            el_packet = encode_el_mapping(identity=live_token, elblid=origin_id, include_elblid=use_elblid)
            if not use_elblid:
                try:
                    client.exchange(el_packet, wait_digest=True)
                except ElblActuationError:
                    return self._conflict("elblid_required")
                return self._conflict("elblid_required")
            try:
                hello = client.exchange(el_packet, wait_digest=True)
            except ElblActuationError:
                return self._conflict("elblid_required")
            if int(hello.get("elbldigest") or 0) == EMPTY_ELBLDIGEST:
                return self._conflict("elbldigest_required")
            if not do_eli:
                return self._conflict("eli_required")
            eli_packet = encode_eli_mapping(
                identity=live_token,
                elblid=origin_id,
                el_ttl=el_ttl,
                eli_bos=eli_bos,
                eli_label=eli_label,
            )
            if not do_elbldigest:
                try:
                    client.exchange(eli_packet, wait_digest=False)
                except ElblActuationError:
                    return self._conflict("elbldigest_required")
                return self._conflict("elbldigest_required")
            try:
                session = client.exchange(eli_packet, wait_digest=True)
            except ElblActuationError as error:
                reason = str(error)
                if el_ttl != REQUIRED_EL_TTL or eli_bos or eli_label != ELI_LABEL:
                    return self._conflict("eli_required")
                if reason == "timeout":
                    return self._conflict("elblid_required")
                if reason == "elbldigest_required":
                    return self._conflict("elbldigest_required")
                return self._conflict("el_required")
            origin_digest = elbldigest_for(live_token, origin_id)
            illegal_eli = el_ttl != REQUIRED_EL_TTL or eli_bos or eli_label != ELI_LABEL
            if illegal_eli or int(session.get("elbldigest") or EMPTY_ELBLDIGEST) != origin_digest:
                return self._conflict("eli_required" if illegal_eli else "elbldigest_required")
            self.retrieved = True
            if replay:
                independent = ElblClient(self.host, int(self.port))
                try:
                    poll = independent.exchange(encode_digest_poll(), wait_digest=True)
                except ElblActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_id, stored_digest = self.read_elblid()
                if (
                    stored_name != live_token
                    or stored_id != origin_id
                    or stored_digest != origin_digest
                    or int(poll.get("elbldigest") or EMPTY_ELBLDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_id}:{origin_digest}:{live_token}:el-eli".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "elblid": origin_id,
                "elbldigest": origin_digest,
                "entropy": entropy_label(origin_id),
                "eli_label": ELI_LABEL,
                "el_frame": True,
                "eli_frame": True,
                "elbldigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "elblid_bound": True,
                "el_ttl": REQUIRED_EL_TTL,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_elbldigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "elblid": origin_id,
                "elbldigest": origin_digest,
                "nd": str(self.sealed_path),
                "el_frame": True,
                "eli_frame": True,
                "elbldigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "elblid_bound": True,
            }
        except (OSError, ElblActuationError) as error:
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
        live = independent_elbldigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "elblid": int(live.get("elblid") or EMPTY_ELBLID),
            "elbldigest": int(live.get("elbldigest") or EMPTY_ELBLDIGEST),
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


def call_elbl_tool(session: ElblSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one elbl tool call against a bound LDP speaker."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_el = True if arguments.get("el") is None else bool(arguments.get("el"))
    do_eli = True if arguments.get("eli") is None else bool(arguments.get("eli"))
    do_elbldigest = True if arguments.get("elbldigest") is None else bool(arguments.get("elbldigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_elblid = True if arguments.get("use_elblid") is None else bool(arguments.get("use_elblid"))
    el_ttl = int(arguments.get("el_ttl") if arguments.get("el_ttl") is not None else REQUIRED_EL_TTL)
    eli_bos = bool(arguments.get("eli_bos"))
    eli_label = int(arguments.get("eli_label") or ELI_LABEL)
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_el=do_el,
            do_eli=do_eli,
            do_elbldigest=do_elbldigest,
            replay=replay,
            use_elblid=use_elblid,
            el_ttl=el_ttl,
            eli_bos=eli_bos,
            eli_label=eli_label,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise ElblActuationError(f"unsupported elbl action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_elbldigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed elbldigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "elblid": EMPTY_ELBLID,
        "elbldigest": EMPTY_ELBLDIGEST,
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
            "el_frame",
            "eli_frame",
            "elbldigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "elblid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    elblid = int(payload.get("elblid") or EMPTY_ELBLID)
    elbldigest = int(payload.get("elbldigest") or EMPTY_ELBLDIGEST)
    eli_label = int(payload.get("eli_label") or 0)
    el_ttl = int(payload.get("el_ttl") if payload.get("el_ttl") is not None else -1)
    dual = port > 0 and bool(elblid) and bool(elbldigest) and eli_label == ELI_LABEL and el_ttl == REQUIRED_EL_TTL
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "elblid": elblid,
        "elbldigest": elbldigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "eli_label": eli_label,
        "el_ttl": el_ttl,
        "el_frame": payload.get("el_frame") is True,
        "eli_frame": payload.get("eli_frame") is True,
        "elbldigest_locate": payload.get("elbldigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "elblid_bound": payload.get("elblid_bound") is True,
    }


def run_elbl_workflow(
    *,
    with_elblid: bool = True,
    skip_bind: bool = False,
    do_el: bool = True,
    do_eli: bool = True,
    do_elbldigest: bool = True,
    replay: bool = True,
    use_elblid: bool = True,
    el_ttl: int = REQUIRED_EL_TTL,
    eli_bos: bool = False,
    eli_label: int = ELI_LABEL,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 6790 EL/ELI elblid cycle workflow."""

    descriptor = elbl_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ELBL_TOOL_PROVIDER),
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
        raise ElblActuationError(f"elbl tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="elbl-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = ElblSession(out, elblid_gate=DEFAULT_ELBLID if with_elblid else EMPTY_ELBLID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "el": do_el,
            "eli": do_eli,
            "elbldigest": do_elbldigest,
            "replay": replay,
            "use_elblid": use_elblid,
            "el_ttl": el_ttl,
            "eli_bos": eli_bos,
            "eli_label": eli_label,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_elbl_tool(session, arguments))
            except ElblActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_elbldigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_elblid
        and not skip_bind
        and do_el
        and do_eli
        and do_elbldigest
        and replay
        and use_elblid
        and el_ttl == REQUIRED_EL_TTL
        and not eli_bos
        and eli_label == ELI_LABEL
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elbl_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_elblid": with_elblid,
        "skip_bind": skip_bind,
        "el_frame": do_el,
        "eli_frame": do_eli,
        "elbldigest": do_elbldigest,
        "replay": replay,
        "use_elblid": use_elblid,
        "el_ttl": el_ttl,
        "eli_bos": eli_bos,
        "eli_label": eli_label,
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
        "elblid_value": int(publish_result.get("elblid") or independent.get("elblid") or EMPTY_ELBLID),
        "elbldigest_value": int(publish_result.get("elbldigest") or independent.get("elbldigest") or EMPTY_ELBLDIGEST),
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
        "elblid": int(trace_body["elblid_value"] or EMPTY_ELBLID),
        "elbldigest": int(trace_body["elbldigest_value"] or EMPTY_ELBLDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_elblid": with_elblid,
        "skip_bind": skip_bind,
        "el_cycle": do_el,
        "eli_cycle": do_eli,
        "elbldigest_cycle": do_elbldigest,
        "replay": replay,
        "use_elblid": use_elblid,
    }


def elbl_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.elbl_actuation import "
        "builtin_elbl_actuation_proof; r=builtin_elbl_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='elbl_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_elbl_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ELBL_ACTUATION_ID,
        name="First-class RFC 6790 MPLS EL/ELI actuation",
        description=(
            "Missions that require an elbl tool can opt the elbl provider in, bind a "
            "loopback RFC 5036 LDP speaker, complete an Entropy Label Mapping with a "
            "non-empty elblid and the RFC 6790 ELC TLV, lockstep an Entropy Label "
            "Indicator whose special-purpose label is 7, whose Bottom of Stack bit "
            "stays clear, and whose Entropy Label TTL is 0, independently poll the "
            "stored elbldigest on a later socket, and seal an elblid-gated "
            "elbldigest. Default routing stays fail-closed; a missing elblid keeps "
            "the hole falsifiable."
        ),
        kind="python",
        entry="blackhole_agent.elbl_actuation:builtin_elbl_actuation_proof",
        proof_command=elbl_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.gtsm-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/elbl_actuation.py",
            "src/blackhole_agent/inbld_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/mission_selection.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required elbl tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 5036 LDP speaker, installs an "
            "RFC 6790 Entropy Label whose vendor TLV is the elblid and whose "
            "mapping carries the ELC TLV, locksteps an ELI special-purpose label "
            "7 that accepts only EL TTL 0 and a clear ELI Bottom of Stack bit, "
            "independently polls the stored elbldigest on a later client socket, "
            "and binds RFC 6826 INBAND/OPAQUE as the next unsaturated "
            "diversity-catalog family. Missing elblids, skip-EL, skip-ELI, "
            "skip-elbldigest, and skip-REPLAY stay fail-closed."
        ),
        tags=("elbl", "rfc6790", "mpls", "elblid", "elbldigest", "el", "eli", "elc", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260911T040956Z-19869b6a",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_elbl_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 6790 EL/ELI lockstep seals an elbldigest."""

    from blackhole_agent.gtsm_actuation import GTSM_ACTUATION_GOAL, GTSM_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG

    checks: dict[str, bool] = {}
    descriptor = elbl_tool_descriptor()
    closed = route_tool_descriptor(descriptor)
    opened = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ELBL_TOOL_PROVIDER),
    )
    checks["denylists_self"] = ELBL_ACTUATION_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = INBLD_ACTUATION_ID in LOCAL_DENYLIST
    checks["provider_is_elbl"] = descriptor.provider == ELBL_TOOL_PROVIDER and descriptor.name == "elbl"
    checks["default_route_fail_closed"] = (
        closed.route == UNSUPPORTED_TOOL_ROUTE
        and not closed.executable
        and ELBL_TOOL_PROVIDER not in DEFAULT_EXECUTABLE_TOOL_PROVIDERS
    )
    checks["opt_in_is_executable"] = opened.executable is True and opened.route == EXECUTABLE_TOOL_ROUTE
    checks["leftover_marker"] = leftover_marker_ids(ELBL_ACTUATION_GOAL) == (ELBL_ACTUATION_ID,)
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(ELBL_LEFTOVER) == (INBLD_ACTUATION_ID,)
    checks["next_family_goal_is_inbld"] = leftover_marker_ids(INBLD_ACTUATION_GOAL) == (INBLD_ACTUATION_ID,)

    legal = parse_eli_el_stack(encode_eli_el_stack(entropy=DEFAULT_ENTROPY))
    checks["rfc6790_eli_is_special_label_7"] = legal["eli"]["label"] == ELI_LABEL and legal["eli"]["bos"] is False
    checks["rfc6790_el_ttl_must_be_zero"] = legal["el"]["ttl"] == REQUIRED_EL_TTL and legal["el"]["bos"] is True
    checks["rfc6790_eli_precedes_el"] = legal["tunnel"]["bos"] is False and legal["el"]["label"] == DEFAULT_ENTROPY
    checks["rfc6790_legal_stack_accepted"] = eli_stack_accepted(legal, entropy=DEFAULT_ENTROPY) is True
    bad_ttl = parse_eli_el_stack(encode_eli_el_stack(entropy=DEFAULT_ENTROPY, el_ttl=1))
    checks["rfc6790_el_ttl_nonzero_rejected"] = eli_stack_accepted(bad_ttl, entropy=DEFAULT_ENTROPY) is False
    bad_bos = parse_eli_el_stack(encode_eli_el_stack(entropy=DEFAULT_ENTROPY, eli_bos=True))
    checks["rfc6790_eli_bos_rejected"] = eli_stack_accepted(bad_bos, entropy=DEFAULT_ENTROPY) is False
    bad_label = parse_eli_el_stack(encode_eli_el_stack(entropy=DEFAULT_ENTROPY, eli_label=13))
    checks["rfc6790_non_eli_label_rejected"] = eli_stack_accepted(bad_label, entropy=DEFAULT_ENTROPY) is False

    el_pdu = parse_ldp_pdu(encode_el_mapping(identity=SENTINEL, elblid=DEFAULT_ELBLID))
    checks["el_pdu_carries_elblid"] = (
        el_pdu["el"] is True
        and el_pdu["eli"] is False
        and el_pdu["elc"] is True
        and el_pdu["elblid"] == DEFAULT_ELBLID
        and el_pdu["label"] == DEFAULT_ENTROPY
        and el_pdu["identity"] == SENTINEL
    )
    bare = parse_ldp_pdu(encode_el_mapping(identity=SENTINEL, elblid=DEFAULT_ELBLID, include_elblid=False))
    checks["el_without_elblid_is_empty"] = bare["elblid"] == EMPTY_ELBLID
    eli_pdu = parse_ldp_pdu(encode_eli_mapping(identity=SENTINEL, elblid=DEFAULT_ELBLID))
    checks["eli_pdu_carries_label_7"] = (
        eli_pdu["eli"] is True
        and eli_pdu["el"] is False
        and eli_pdu["elc"] is True
        and eli_pdu["label"] == ELI_LABEL
        and eli_pdu["stack"] is not None
        and eli_stack_accepted(eli_pdu["stack"], entropy=DEFAULT_ENTROPY)
    )

    live = run_elbl_workflow()
    checks["workflow_seals_elbldigest"] = (
        live.get("ok") is True
        and live.get("sentinel") == SENTINEL
        and int(live.get("elblid") or 0) == DEFAULT_ELBLID
        and int(live.get("elbldigest") or 0) == DEFAULT_ELBLDIGEST
        and Path(str(live.get("sealed_path") or "")).is_file()
    )
    row = independent_elbldigest(Path(str(live.get("sealed_path") or "")))
    checks["independent_reader_reopens_digest"] = (
        row.get("ok") is True
        and row.get("sentinel") == SENTINEL
        and int(row.get("elblid") or 0) == DEFAULT_ELBLID
        and int(row.get("elbldigest") or 0) == DEFAULT_ELBLDIGEST
    )
    missing = run_elbl_workflow(with_elblid=False)
    skip_el = run_elbl_workflow(do_el=False)
    skip_eli = run_elbl_workflow(do_eli=False)
    skip_digest = run_elbl_workflow(do_elbldigest=False)
    skip_id = run_elbl_workflow(use_elblid=False)
    skip_ttl = run_elbl_workflow(el_ttl=1)
    checks["missing_elblid_is_forbidden"] = missing.get("ok") is False and missing.get("error") == "missing_elblid"
    checks["skip_el_stays_empty"] = skip_el.get("ok") is False and skip_el.get("error") == "el_required"
    checks["skip_eli_stays_empty"] = skip_eli.get("ok") is False and skip_eli.get("error") == "eli_required"
    checks["skip_elbldigest_stays_empty"] = skip_digest.get("ok") is False and skip_digest.get("error") == "elbldigest_required"
    checks["skip_elblid_stays_empty"] = skip_id.get("ok") is False and skip_id.get("error") == "elblid_required"
    checks["bad_el_ttl_stays_empty"] = skip_ttl.get("ok") is False and skip_ttl.get("error") == "eli_required"

    family = capability_family(ELBL_ACTUATION_GOAL)
    tokens = set(semantic_tokens(ELBL_ACTUATION_GOAL))
    checks["family_is_elbl"] = "elbl" in family.split("/") and "elblid" in tokens and "rfc6790" in tokens
    checks["family_is_not_gtsm"] = (
        leftover_marker_ids(GTSM_ACTUATION_GOAL) == (GTSM_ACTUATION_ID,)
        and "gtsm" not in family.split("/")
        and "gtsmid" not in tokens
    )
    checks["family_is_not_inbld"] = (
        "inbld" not in family.split("/")
        and "rfc6826" not in family
        and "inbldid" not in family
        and "inbldigest" not in family
    )

    catalog = DIVERSITY_CATALOG
    checks["catalog_names_elbl"] = (
        len(catalog) > 237
        and catalog[237]["id"] == ELBL_ACTUATION_ID
        and catalog[237]["source"] == "genesis_bind_elbl"
    )
    checks["catalog_names_inbld"] = (
        len(catalog) > 238
        and catalog[238]["id"] == INBLD_ACTUATION_ID
        and catalog[238]["source"] == "genesis_bind_inbld"
    )

    with tempfile.TemporaryDirectory(prefix="elbl-leftover-") as tmp:
        root = Path(tmp)
        rfc6790_leftover = (
            "Later genesis can take RFC 6790 The Use of Entropy Labels in MPLS "
            "Forwarding EL/ELI over an elblid-gated elbldigest."
        )
        open_before = leftover_is_open(rfc6790_leftover, root, ledger=CapabilityLedger())
        register_catalog_proved(root, ELBL_ACTUATION_ID)
        fixture_ledger = load_ledger(default_ledger_path(root))
        reason = leftover_satisfied_by(rfc6790_leftover, root, ledger=fixture_ledger)
        after = leftover_is_open(rfc6790_leftover, root, ledger=fixture_ledger)
        next_open = leftover_is_open(ELBL_LEFTOVER, root, ledger=fixture_ledger)
    checks["rfc6790_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_elbl_consumes_leftover"] = after is False and reason.startswith(f"ledger:{ELBL_ACTUATION_ID}")
    checks["next_inbld_leftover_stays_open"] = next_open is True
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_elbl_actuation_capability()
    return {
        "ok": ok,
        "action": "elbl_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": ELBL_ACTUATION_GOAL,
        "done_when": ELBL_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
