"""Drive a first-class LDP Typed Wildcard FEC tool through RFC 6667 TYPED/WILDCARD.

Tool routing already fails missions that require ``twfec``: hosted LDP
Typed Wildcard FEC endpoints stay unsupported, and no first-party twfec
provider is executable. Unbound therefore cannot install a PWid FEC Label
Mapping, lockstep a Typed Wildcard withdraw that matches only that FEC
type, independently poll the stored twfecdigest, or seal a twfecdigest an
independent later reader can re-open.

This module closes that hole with RFC 6667 wire behavior, not a renamed
HTTP loopback:

- advertise a ``twfec`` provider tool that stays fail-closed until opted in
- speak RFC 5036 LDP PDUs over a real loopback TCP speaker
- install a TYPED RFC 4447 PWid FEC (0x80) whose PW ID is the twfecid
- refuse WILDCARD until a TYPED mapping lands with a non-empty twfecid
- match RFC 5918/6667 Typed Wildcard FEC (0x05) against stored PWid FECs
  and never against Generalized PWid (0x81)
- independently poll the stored twfecdigest on a later client socket
- persist a sealed twfecdigest an independent reader can re-open
- bind RFC 6720 GTSM/TTL as the next unsaturated diversity-catalog family
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
from blackhole_agent.gtsm_actuation import (
    GTSM_ACTUATION_GOAL,
    GTSM_ACTUATION_ID,
    GTSM_LEFTOVER,
)
from blackhole_agent.kernel_leftover import leftover_is_open, leftover_marker_ids, leftover_satisfied_by
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import capability_family, semantic_tokens
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    TWFEC_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    route_tool_descriptor,
    twfec_tool_descriptor,
)

SCHEMA_VERSION = 1
TWFEC_ACTUATION_ID = "capability.twfec-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-TWFEC-OK"
POLL_TOKEN = "BH-TWFEC-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_TWFECID = 0
EMPTY_TWFECDIGEST = 0

LDP_VERSION = 1
LDP_ID = b"\x7f\x00\x00\x01\x00\x00"  # 127.0.0.1 / label-space 0
MSG_NOTIFICATION = 0x0001
MSG_LABEL_MAPPING = 0x0400
MSG_LABEL_REQUEST = 0x0401
MSG_LABEL_WITHDRAW = 0x0402
TLV_FEC = 0x0100
TLV_GENERIC_LABEL = 0x0200
TLV_VENDOR_PRIVATE = 0x3E00
TYPED_WILDCARD_FEC_TYPE = 0x05
PWID_FEC_TYPE = 0x80
GEN_PWID_FEC_TYPE = 0x81
ETHERNET_PW_TYPE = 0x0005
DEFAULT_GROUP_ID = 1
DEFAULT_LABEL = 0x00010001

TWFEC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TWFEC_ACTUATION_ID};"
    f"capability_proved:{TWFEC_ACTUATION_ID};"
    "no_skill_route"
)
TWFEC_ACTUATION_GOAL = (
    "Repair rfc6667 twfec typed/wildcard cycle cannot land over http twfec twfecid: "
    "hosted twfec remain unsupported so a TYPED then WILDCARD twfecid handshake cannot "
    "land and a sealed twfecdigest cannot be produced. A missing twfec twfecid stays "
    "forbidden; fail-closed routing never opts the twfec provider in. An independent "
    "later poll of the stored twfecdigest keeps the hole falsifiable. TWFEC sessions "
    "stay fail-closed without a twfecid-gated twfecdigest."
)
TWFEC_LEFTOVER = GTSM_LEFTOVER


class TwfecActuationError(RuntimeError):
    """Raised when the RFC 6667 LDP session or loopback speaker misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def temporary_twfecid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"twfecid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_twfecid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-twfecid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def encode_pwid_fec(*, pw_type: int, group_id: int, pw_id: int, control_word: bool = False) -> bytes:
    """RFC 4447 PWid FEC Element (type 0x80) without interface parameters."""

    flags_type = (0x8000 if control_word else 0) | (int(pw_type) & 0x7FFF)
    return struct.pack("!BHBII", PWID_FEC_TYPE, flags_type, 0, int(group_id) & 0xFFFFFFFF, int(pw_id) & 0xFFFFFFFF)


def encode_gen_pwid_fec(*, agi_type: int = 0, agi: bytes = b"") -> bytes:
    """RFC 4447 Generalized PWid FEC Element (type 0x81) stub used only as a mismatch peer."""

    value = bytes(agi or b"")
    return struct.pack("!BB", GEN_PWID_FEC_TYPE, int(agi_type) & 0xFF) + bytes([len(value)]) + value


def encode_typed_wildcard_fec(*, fec_type: int, pw_type: int | None = None) -> bytes:
    """RFC 5918 Typed Wildcard FEC Element with RFC 6667 PWid FEC Type Info."""

    if pw_type is None:
        return struct.pack("!BBB", TYPED_WILDCARD_FEC_TYPE, int(fec_type) & 0xFF, 0)
    info = struct.pack("!HH", int(pw_type) & 0x7FFF, 0)
    return struct.pack("!BBB", TYPED_WILDCARD_FEC_TYPE, int(fec_type) & 0xFF, len(info)) + info


def parse_fec_element(data: bytes, offset: int = 0) -> tuple[dict[str, Any], int]:
    if offset >= len(data):
        raise TwfecActuationError("short_fec")
    kind = data[offset]
    if kind == PWID_FEC_TYPE:
        if offset + 12 > len(data):
            raise TwfecActuationError("short_pwid")
        _type, flags_type, info_len, group_id, pw_id = struct.unpack_from("!BHBII", data, offset)
        end = offset + 12 + info_len
        if end > len(data):
            raise TwfecActuationError("short_pwid")
        return (
            {
                "kind": "pwid",
                "fec_type": PWID_FEC_TYPE,
                "pw_type": int(flags_type) & 0x7FFF,
                "control_word": bool(int(flags_type) & 0x8000),
                "group_id": int(group_id),
                "pw_id": int(pw_id),
                "twfecid": int(pw_id),
            },
            end,
        )
    if kind == GEN_PWID_FEC_TYPE:
        if offset + 3 > len(data):
            raise TwfecActuationError("short_gen_pwid")
        agi_type = data[offset + 1]
        agi_len = data[offset + 2]
        end = offset + 3 + agi_len
        if end > len(data):
            raise TwfecActuationError("short_gen_pwid")
        return (
            {
                "kind": "gen_pwid",
                "fec_type": GEN_PWID_FEC_TYPE,
                "agi_type": int(agi_type),
                "agi": data[offset + 3 : end],
                "pw_id": EMPTY_TWFECID,
                "twfecid": EMPTY_TWFECID,
            },
            end,
        )
    if kind == TYPED_WILDCARD_FEC_TYPE:
        if offset + 3 > len(data):
            raise TwfecActuationError("short_wildcard")
        fec_type = data[offset + 1]
        info_len = data[offset + 2]
        end = offset + 3 + info_len
        if end > len(data):
            raise TwfecActuationError("short_wildcard")
        info = data[offset + 3 : end]
        pw_type = None
        if fec_type == PWID_FEC_TYPE and len(info) >= 2:
            pw_type = struct.unpack_from("!H", info, 0)[0] & 0x7FFF
        return (
            {
                "kind": "typed_wildcard",
                "fec_type": TYPED_WILDCARD_FEC_TYPE,
                "target_fec_type": int(fec_type),
                "pw_type": pw_type,
            },
            end,
        )
    raise TwfecActuationError("unknown_fec")


def match_typed_wildcard(stored: Mapping[str, Any], wildcard: Mapping[str, Any]) -> bool:
    """RFC 6667: a PWid typed wildcard matches stored PWid FECs only.

    Generalized PWid (0x81) never matches a PWid (0x80) wildcard. When FEC
    Type Info carries a PW type, only that PW type matches. Len=0 matches every
    stored PWid FEC.
    """

    if str(wildcard.get("kind") or "") != "typed_wildcard":
        return False
    target = int(wildcard.get("target_fec_type") or 0)
    stored_type = int(stored.get("fec_type") or 0)
    if stored_type != target:
        return False
    if target != PWID_FEC_TYPE:
        return stored_type == target
    if str(stored.get("kind") or "") != "pwid":
        return False
    wanted = wildcard.get("pw_type")
    if wanted is None:
        return int(stored.get("pw_id") or 0) != EMPTY_TWFECID
    return int(stored.get("pw_type") or 0) == int(wanted) and int(stored.get("pw_id") or 0) != EMPTY_TWFECID


def twfecdigest_for(identity: str, mappings: SequenceLike) -> int:
    rows = []
    for item in mappings:
        rows.append(
            {
                "identity": str(identity or ""),
                "fec_type": int(item.get("fec_type") or 0),
                "pw_type": int(item.get("pw_type") or 0),
                "group_id": int(item.get("group_id") or 0),
                "twfecid": int(item.get("twfecid") or item.get("pw_id") or 0),
            }
        )
    rows.sort(key=lambda row: (row["fec_type"], row["pw_type"], row["group_id"], row["twfecid"]))
    value = int(_digest(rows)[:8], 16)
    return value or 1


SequenceLike = tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]]


def encode_tlv(tlv_type: int, value: bytes) -> bytes:
    return struct.pack("!HH", int(tlv_type) & 0xFFFF, len(value)) + bytes(value or b"")


def encode_ldp_message(msg_type: int, message_id: int, parameters: bytes) -> bytes:
    body = struct.pack("!I", int(message_id) & 0xFFFFFFFF) + bytes(parameters or b"")
    return struct.pack("!HH", int(msg_type) & 0xFFFF, len(body)) + body


def encode_ldp_pdu(messages: bytes, *, ldp_id: bytes = LDP_ID) -> bytes:
    ident = bytes(ldp_id or LDP_ID)
    if len(ident) != 6:
        raise TwfecActuationError("illegal_ldp_id")
    payload = ident + bytes(messages or b"")
    return struct.pack("!HH", LDP_VERSION, len(payload)) + payload


def encode_typed_mapping(
    *,
    identity: str,
    twfecid: int,
    pw_type: int = ETHERNET_PW_TYPE,
    include_twfecid: bool = True,
    message_id: int = 1,
) -> bytes:
    live_id = int(twfecid) & 0xFFFFFFFF if include_twfecid else EMPTY_TWFECID
    fec = encode_pwid_fec(pw_type=pw_type, group_id=DEFAULT_GROUP_ID, pw_id=live_id)
    token = str(identity or "").encode("utf-8")[:255]
    parameters = (
        encode_tlv(TLV_FEC, fec)
        + encode_tlv(TLV_GENERIC_LABEL, struct.pack("!I", DEFAULT_LABEL))
        + encode_tlv(TLV_VENDOR_PRIVATE, bytes([len(token)]) + token)
    )
    return encode_ldp_pdu(encode_ldp_message(MSG_LABEL_MAPPING, message_id, parameters))


def encode_wildcard_withdraw(
    *,
    fec_type: int = PWID_FEC_TYPE,
    pw_type: int | None = ETHERNET_PW_TYPE,
    message_id: int = 2,
) -> bytes:
    fec = encode_typed_wildcard_fec(fec_type=fec_type, pw_type=pw_type)
    return encode_ldp_pdu(encode_ldp_message(MSG_LABEL_WITHDRAW, message_id, encode_tlv(TLV_FEC, fec)))


def encode_wildcard_request(
    *,
    fec_type: int = PWID_FEC_TYPE,
    pw_type: int | None = ETHERNET_PW_TYPE,
    message_id: int = 3,
) -> bytes:
    fec = encode_typed_wildcard_fec(fec_type=fec_type, pw_type=pw_type)
    return encode_ldp_pdu(encode_ldp_message(MSG_LABEL_REQUEST, message_id, encode_tlv(TLV_FEC, fec)))


def parse_tlvs(data: bytes) -> list[tuple[int, bytes]]:
    items: list[tuple[int, bytes]] = []
    offset = 0
    while offset + 4 <= len(data):
        tlv_type, length = struct.unpack_from("!HH", data, offset)
        offset += 4
        if offset + length > len(data):
            raise TwfecActuationError("short_tlv")
        items.append((int(tlv_type), data[offset : offset + length]))
        offset += length
    return items


def parse_ldp_pdu(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 10:
        raise TwfecActuationError("short_pdu")
    version, length = struct.unpack_from("!HH", raw, 0)
    if version != LDP_VERSION or len(raw) < 4 + length:
        raise TwfecActuationError("illegal_pdu")
    ident = raw[4:10]
    offset = 10
    messages: list[dict[str, Any]] = []
    while offset + 8 <= 4 + length:
        msg_type, msg_len = struct.unpack_from("!HH", raw, offset)
        offset += 4
        if offset + msg_len > 4 + length:
            raise TwfecActuationError("short_message")
        message_id = struct.unpack_from("!I", raw, offset)[0]
        parameters = raw[offset + 4 : offset + msg_len]
        offset += msg_len
        parsed: dict[str, Any] = {
            "msg_type": int(msg_type),
            "message_id": int(message_id),
            "fecs": [],
            "label": 0,
            "identity": "",
            "twfecdigest": EMPTY_TWFECDIGEST,
        }
        for tlv_type, value in parse_tlvs(parameters):
            if tlv_type == TLV_FEC:
                cursor = 0
                while cursor < len(value):
                    fec, cursor = parse_fec_element(value, cursor)
                    parsed["fecs"].append(fec)
            elif tlv_type == TLV_GENERIC_LABEL and len(value) >= 4:
                parsed["label"] = struct.unpack("!I", value[:4])[0]
            elif tlv_type == TLV_VENDOR_PRIVATE and value:
                if int(msg_type) == MSG_NOTIFICATION and len(value) >= 4:
                    parsed["twfecdigest"] = struct.unpack("!I", value[:4])[0]
                else:
                    token_len = value[0]
                    parsed["identity"] = value[1 : 1 + token_len].decode("utf-8", errors="replace")
        messages.append(parsed)
    return {
        "version": int(version),
        "ldp_id": ident,
        "messages": messages,
        "typed": any(item["msg_type"] == MSG_LABEL_MAPPING and any(fec.get("kind") == "pwid" for fec in item["fecs"]) for item in messages),
        "wildcard": any(
            item["msg_type"] in {MSG_LABEL_WITHDRAW, MSG_LABEL_REQUEST}
            and any(fec.get("kind") == "typed_wildcard" for fec in item["fecs"])
            for item in messages
        ),
        "twfecid": next(
            (
                int(fec.get("twfecid") or 0)
                for item in messages
                for fec in item["fecs"]
                if fec.get("kind") == "pwid"
            ),
            EMPTY_TWFECID,
        ),
        "identity": next((str(item.get("identity") or "") for item in messages if item.get("identity")), ""),
        "twfecdigest": next(
            (int(item.get("twfecdigest") or 0) for item in messages if item.get("twfecdigest")),
            EMPTY_TWFECDIGEST,
        ),
    }


DEFAULT_TWFECID = temporary_twfecid(SENTINEL)
DEFAULT_TWFECDIGEST = twfecdigest_for(
    SENTINEL,
    (
        {
            "fec_type": PWID_FEC_TYPE,
            "pw_type": ETHERNET_PW_TYPE,
            "group_id": DEFAULT_GROUP_ID,
            "twfecid": DEFAULT_TWFECID,
        },
    ),
)


def encode_digest_notification(twfecdigest: int, *, message_id: int = 9) -> bytes:
    parameters = encode_tlv(TLV_VENDOR_PRIVATE, struct.pack("!I", int(twfecdigest) & 0xFFFFFFFF))
    return encode_ldp_pdu(encode_ldp_message(MSG_NOTIFICATION, message_id, parameters))


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    buf = bytearray()
    while len(buf) < count:
        chunk = sock.recv(count - len(buf))
        if not chunk:
            raise TwfecActuationError("short_pdu")
        buf.extend(chunk)
    return bytes(buf)


def recv_ldp_pdu(sock: socket.socket) -> bytes:
    header = _recv_exact(sock, 4)
    _version, length = struct.unpack("!HH", header)
    return header + _recv_exact(sock, length)


class TwfecClient:
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
                raise TwfecActuationError("twfecdigest_required")
            reply = parse_ldp_pdu(recv_ldp_pdu(sock))
        except (OSError, TimeoutError, socket.timeout) as error:
            raise TwfecActuationError("timeout") from error
        finally:
            try:
                sock.close()
            except OSError:
                pass
        digest = int(reply.get("twfecdigest") or EMPTY_TWFECDIGEST)
        if not digest:
            raise TwfecActuationError("twfecdigest_required")
        return {
            "session": reply,
            "identity": str(reply.get("identity") or ""),
            "twfecid": int(reply.get("twfecid") or EMPTY_TWFECID),
            "twfecdigest": digest,
        }


class TwfecSession:
    """TWFECID-gated loopback RFC 6667 LDP speaker: bind, publish, read."""

    def __init__(self, output_dir: Path, *, twfecid_gate: int = DEFAULT_TWFECID) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.twfecid_gate = int(twfecid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.twfecid = EMPTY_TWFECID
        self.twfecdigest = EMPTY_TWFECDIGEST
        self.mappings: list[dict[str, Any]] = []
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.typed = False
        self.wildcard = False
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
            "twfecid": EMPTY_TWFECID,
            "twfecdigest": EMPTY_TWFECDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _twfecid_missing(self) -> bool:
        return not int(self.twfecid_gate or 0)

    def store_typed_once(self, identity: str, mapping: Mapping[str, Any]) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(mapping.get("twfecid") or mapping.get("pw_id") or EMPTY_TWFECID)
            if not self.identity and name and live:
                row = {
                    "kind": "pwid",
                    "fec_type": PWID_FEC_TYPE,
                    "pw_type": int(mapping.get("pw_type") or ETHERNET_PW_TYPE),
                    "group_id": int(mapping.get("group_id") or DEFAULT_GROUP_ID),
                    "pw_id": live,
                    "twfecid": live,
                }
                self.identity = name
                self.twfecid = live
                self.mappings = [row]
                self.twfecdigest = twfecdigest_for(name, self.mappings)
                self.stored = True
                self.typed = True
            return str(self.identity), int(self.twfecid), int(self.twfecdigest)

    def read_twfecid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.twfecid), int(self.twfecdigest)

    def _handle(self, payload: bytes) -> bytes:
        packet = parse_ldp_pdu(payload)
        if packet["typed"]:
            mapping = next(fec for item in packet["messages"] for fec in item["fecs"] if fec.get("kind") == "pwid")
            identity = str(packet.get("identity") or "")
            if not int(mapping.get("twfecid") or 0) or not identity:
                return b""
            self.store_typed_once(identity, mapping)
            stored_name, stored_id, stored_digest = self.read_twfecid()
            if not stored_name or not stored_id:
                return b""
            return encode_digest_notification(stored_digest)
        if packet["wildcard"]:
            wildcard = next(
                fec for item in packet["messages"] for fec in item["fecs"] if fec.get("kind") == "typed_wildcard"
            )
            stored_name, stored_id, stored_digest = self.read_twfecid()
            if not stored_name or not stored_id or not stored_digest:
                return b""
            with self._lock:
                matched = [row for row in self.mappings if match_typed_wildcard(row, wildcard)]
            if not matched:
                return b""
            digest = twfecdigest_for(stored_name, matched)
            with self._lock:
                self.twfecdigest = digest
                self.wildcard = True
                self.retrieved = True
            return encode_digest_notification(digest)
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
            except (OSError, TwfecActuationError, TimeoutError, socket.timeout):
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def bind(self) -> dict[str, Any]:
        if self._twfecid_missing():
            return self._forbidden("missing_twfecid")
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
        do_typed: bool = True,
        do_wildcard: bool = True,
        do_twfecdigest: bool = True,
        replay: bool = True,
        use_twfecid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._twfecid_missing():
            return self._forbidden("missing_twfecid")
        live_token = str(token or SENTINEL)
        origin_id = temporary_twfecid(live_token)
        client: TwfecClient | None = None
        independent: TwfecClient | None = None
        try:
            client = TwfecClient(self.host, int(self.port))
            if not do_typed:
                return self._conflict("typed_required")
            typed_packet = encode_typed_mapping(
                identity=live_token,
                twfecid=origin_id,
                include_twfecid=use_twfecid,
            )
            if not use_twfecid:
                try:
                    client.exchange(typed_packet, wait_digest=True)
                except TwfecActuationError:
                    return self._conflict("twfecid_required")
                return self._conflict("twfecid_required")
            try:
                typed = client.exchange(typed_packet, wait_digest=True)
            except TwfecActuationError:
                return self._conflict("twfecid_required")
            if int(typed.get("twfecdigest") or 0) == EMPTY_TWFECDIGEST:
                return self._conflict("twfecdigest_required")
            if not do_wildcard:
                return self._conflict("wildcard_required")
            wildcard_packet = encode_wildcard_withdraw()
            if not do_twfecdigest:
                try:
                    client.exchange(wildcard_packet, wait_digest=False)
                except TwfecActuationError as error:
                    if str(error) == "twfecdigest_required":
                        return self._conflict("twfecdigest_required")
                    return self._conflict("twfecdigest_required")
                return self._conflict("twfecdigest_required")
            try:
                session = client.exchange(wildcard_packet, wait_digest=True)
            except TwfecActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("twfecid_required")
                if reason == "twfecdigest_required":
                    return self._conflict("twfecdigest_required")
                return self._conflict("typed_required")
            origin_digest = twfecdigest_for(
                live_token,
                (
                    {
                        "fec_type": PWID_FEC_TYPE,
                        "pw_type": ETHERNET_PW_TYPE,
                        "group_id": DEFAULT_GROUP_ID,
                        "twfecid": origin_id,
                    },
                ),
            )
            if int(session.get("twfecdigest") or EMPTY_TWFECDIGEST) != origin_digest:
                return self._conflict("twfecdigest_required")
            self.retrieved = True
            if replay:
                independent = TwfecClient(self.host, int(self.port))
                try:
                    poll = independent.exchange(encode_wildcard_request(), wait_digest=True)
                except TwfecActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_id, stored_digest = self.read_twfecid()
                if (
                    stored_name != live_token
                    or stored_id != origin_id
                    or stored_digest != origin_digest
                    or int(poll.get("twfecdigest") or EMPTY_TWFECDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_id}:{origin_digest}:{live_token}:typed-wildcard".encode("utf-8")
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "twfecid": origin_id,
                "twfecdigest": origin_digest,
                "typed_frame": True,
                "wildcard_frame": True,
                "twfecdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "twfecid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_twfecdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "twfecid": origin_id,
                "twfecdigest": origin_digest,
                "nd": str(self.sealed_path),
                "typed_frame": True,
                "wildcard_frame": True,
                "twfecdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "twfecid_bound": True,
            }
        except (OSError, TwfecActuationError) as error:
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
        live = independent_twfecdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "twfecid": int(live.get("twfecid") or EMPTY_TWFECID),
            "twfecdigest": int(live.get("twfecdigest") or EMPTY_TWFECDIGEST),
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


def call_twfec_tool(session: TwfecSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one twfec tool call against a bound LDP speaker."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_typed = True if arguments.get("typed") is None else bool(arguments.get("typed"))
    do_wildcard = True if arguments.get("wildcard") is None else bool(arguments.get("wildcard"))
    do_twfecdigest = True if arguments.get("twfecdigest") is None else bool(arguments.get("twfecdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_twfecid = True if arguments.get("use_twfecid") is None else bool(arguments.get("use_twfecid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_typed=do_typed,
            do_wildcard=do_wildcard,
            do_twfecdigest=do_twfecdigest,
            replay=replay,
            use_twfecid=use_twfecid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise TwfecActuationError(f"unsupported twfec action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_twfecdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed twfecdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "twfecid": EMPTY_TWFECID,
        "twfecdigest": EMPTY_TWFECDIGEST,
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
            "typed_frame",
            "wildcard_frame",
            "twfecdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "twfecid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    twfecid = int(payload.get("twfecid") or EMPTY_TWFECID)
    twfecdigest = int(payload.get("twfecdigest") or EMPTY_TWFECDIGEST)
    dual = port > 0 and bool(twfecid) and bool(twfecdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "twfecid": twfecid,
        "twfecdigest": twfecdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "typed_frame": payload.get("typed_frame") is True,
        "wildcard_frame": payload.get("wildcard_frame") is True,
        "twfecdigest_locate": payload.get("twfecdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "twfecid_bound": payload.get("twfecid_bound") is True,
    }


def run_twfec_workflow(
    *,
    with_twfecid: bool = True,
    skip_bind: bool = False,
    do_typed: bool = True,
    do_wildcard: bool = True,
    do_twfecdigest: bool = True,
    replay: bool = True,
    use_twfecid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 6667 TYPED/WILDCARD twfecid cycle workflow."""

    descriptor = twfec_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TWFEC_TOOL_PROVIDER),
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
        raise TwfecActuationError(f"twfec tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="twfec-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = TwfecSession(out, twfecid_gate=DEFAULT_TWFECID if with_twfecid else EMPTY_TWFECID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "typed": do_typed,
            "wildcard": do_wildcard,
            "twfecdigest": do_twfecdigest,
            "replay": replay,
            "use_twfecid": use_twfecid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_twfec_tool(session, arguments))
            except TwfecActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_twfecdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_twfecid
        and not skip_bind
        and do_typed
        and do_wildcard
        and do_twfecdigest
        and replay
        and use_twfecid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "twfec_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_twfecid": with_twfecid,
        "skip_bind": skip_bind,
        "typed_frame": do_typed,
        "wildcard_frame": do_wildcard,
        "twfecdigest": do_twfecdigest,
        "replay": replay,
        "use_twfecid": use_twfecid,
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
        "twfecid_value": int(publish_result.get("twfecid") or independent.get("twfecid") or EMPTY_TWFECID),
        "twfecdigest_value": int(publish_result.get("twfecdigest") or independent.get("twfecdigest") or EMPTY_TWFECDIGEST),
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
        "twfecid": int(trace_body["twfecid_value"] or EMPTY_TWFECID),
        "twfecdigest": int(trace_body["twfecdigest_value"] or EMPTY_TWFECDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_twfecid": with_twfecid,
        "skip_bind": skip_bind,
        "typed_cycle": do_typed,
        "wildcard_cycle": do_wildcard,
        "twfecdigest_cycle": do_twfecdigest,
        "replay": replay,
        "use_twfecid": use_twfecid,
    }


def twfec_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.twfec_actuation import "
        "builtin_twfec_actuation_proof; r=builtin_twfec_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='twfec_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_twfec_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=TWFEC_ACTUATION_ID,
        name="First-class RFC 6667 LDP Typed Wildcard FEC TYPED/WILDCARD actuation",
        description=(
            "Missions that require a twfec tool can opt the twfec provider in, bind a "
            "loopback RFC 5036 LDP speaker, complete a TYPED PWid FEC Label Mapping "
            "with a non-empty twfecid, lockstep an RFC 6667 Typed Wildcard WILDCARD "
            "that matches only PWid FECs, independently poll the stored twfecdigest "
            "on a later socket, and seal a twfecid-gated twfecdigest. Default routing "
            "stays fail-closed; a missing twfecid keeps the hole falsifiable."
        ),
        kind="python",
        entry="blackhole_agent.twfec_actuation:builtin_twfec_actuation_proof",
        proof_command=twfec_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.wildad-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/twfec_actuation.py",
            "src/blackhole_agent/gtsm_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/mission_selection.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required twfec tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 5036 LDP speaker, installs a TYPED "
            "RFC 4447 PWid FEC whose PW ID is the twfecid, locksteps an RFC 6667 "
            "Typed Wildcard WILDCARD that matches PWid Ethernet and never Generalized "
            "PWid, independently polls the stored twfecdigest on a later client "
            "socket, and binds RFC 6720 GTSM/TTL as the next unsaturated "
            "diversity-catalog family. Missing twfecids, skip-TYPED, skip-WILDCARD, "
            "skip-twfecdigest, and skip-REPLAY stay fail-closed."
        ),
        tags=("twfec", "rfc6667", "ldp", "twfecid", "twfecdigest", "typed", "wildcard", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260910T105130Z-2fbef8d4",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_twfec_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 6667 TYPED/WILDCARD lockstep seals a twfecdigest."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.wildad_actuation import WILDAD_ACTUATION_GOAL, WILDAD_ACTUATION_ID

    checks: dict[str, bool] = {}
    descriptor = twfec_tool_descriptor()
    closed = route_tool_descriptor(descriptor)
    opened = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TWFEC_TOOL_PROVIDER),
    )
    checks["denylists_self"] = TWFEC_ACTUATION_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = GTSM_ACTUATION_ID in LOCAL_DENYLIST
    checks["provider_is_twfec"] = descriptor.provider == TWFEC_TOOL_PROVIDER and descriptor.name == "twfec"
    checks["default_route_fail_closed"] = (
        closed.route == UNSUPPORTED_TOOL_ROUTE
        and not closed.executable
        and TWFEC_TOOL_PROVIDER not in DEFAULT_EXECUTABLE_TOOL_PROVIDERS
    )
    checks["opt_in_is_executable"] = opened.executable is True and opened.route == EXECUTABLE_TOOL_ROUTE
    checks["leftover_marker"] = leftover_marker_ids(TWFEC_ACTUATION_GOAL) == (TWFEC_ACTUATION_ID,)
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(TWFEC_LEFTOVER) == (GTSM_ACTUATION_ID,)
    checks["next_family_goal_is_gtsm"] = leftover_marker_ids(GTSM_ACTUATION_GOAL) == (GTSM_ACTUATION_ID,)

    pwid = {
        "kind": "pwid",
        "fec_type": PWID_FEC_TYPE,
        "pw_type": ETHERNET_PW_TYPE,
        "group_id": DEFAULT_GROUP_ID,
        "pw_id": DEFAULT_TWFECID,
        "twfecid": DEFAULT_TWFECID,
    }
    gen = {"kind": "gen_pwid", "fec_type": GEN_PWID_FEC_TYPE, "pw_id": DEFAULT_TWFECID, "twfecid": DEFAULT_TWFECID}
    wildcard_all = parse_fec_element(encode_typed_wildcard_fec(fec_type=PWID_FEC_TYPE))[0]
    wildcard_eth = parse_fec_element(encode_typed_wildcard_fec(fec_type=PWID_FEC_TYPE, pw_type=ETHERNET_PW_TYPE))[0]
    wildcard_other = parse_fec_element(encode_typed_wildcard_fec(fec_type=PWID_FEC_TYPE, pw_type=0x0004))[0]
    wildcard_gen = parse_fec_element(encode_typed_wildcard_fec(fec_type=GEN_PWID_FEC_TYPE))[0]
    checks["rfc6667_wildcard_matches_pwid"] = match_typed_wildcard(pwid, wildcard_eth) and match_typed_wildcard(pwid, wildcard_all)
    checks["rfc6667_wildcard_rejects_gen_pwid"] = not match_typed_wildcard(gen, wildcard_eth) and not match_typed_wildcard(pwid, wildcard_gen)
    checks["rfc6667_pw_type_filter"] = not match_typed_wildcard(pwid, wildcard_other)
    checks["rfc6667_empty_twfecid_does_not_match"] = not match_typed_wildcard(
        {**pwid, "pw_id": EMPTY_TWFECID, "twfecid": EMPTY_TWFECID},
        wildcard_eth,
    )

    typed = parse_ldp_pdu(encode_typed_mapping(identity=SENTINEL, twfecid=DEFAULT_TWFECID))
    checks["typed_pdu_carries_twfecid"] = (
        typed["typed"] is True
        and typed["twfecid"] == DEFAULT_TWFECID
        and typed["identity"] == SENTINEL
    )
    bare = parse_ldp_pdu(encode_typed_mapping(identity=SENTINEL, twfecid=DEFAULT_TWFECID, include_twfecid=False))
    checks["typed_without_twfecid_is_empty"] = bare["twfecid"] == EMPTY_TWFECID
    withdraw = parse_ldp_pdu(encode_wildcard_withdraw())
    checks["wildcard_pdu_is_typed_wildcard"] = withdraw["wildcard"] is True and withdraw["typed"] is False

    live = run_twfec_workflow()
    checks["workflow_seals_twfecdigest"] = (
        live.get("ok") is True
        and live.get("sentinel") == SENTINEL
        and int(live.get("twfecid") or 0) == DEFAULT_TWFECID
        and int(live.get("twfecdigest") or 0) == DEFAULT_TWFECDIGEST
        and Path(str(live.get("sealed_path") or "")).is_file()
    )
    row = independent_twfecdigest(Path(str(live.get("sealed_path") or "")))
    checks["independent_reader_reopens_digest"] = (
        row.get("ok") is True
        and row.get("sentinel") == SENTINEL
        and int(row.get("twfecid") or 0) == DEFAULT_TWFECID
        and int(row.get("twfecdigest") or 0) == DEFAULT_TWFECDIGEST
    )
    missing = run_twfec_workflow(with_twfecid=False)
    skip_typed = run_twfec_workflow(do_typed=False)
    skip_wildcard = run_twfec_workflow(do_wildcard=False)
    skip_digest = run_twfec_workflow(do_twfecdigest=False)
    skip_id = run_twfec_workflow(use_twfecid=False)
    checks["missing_twfecid_is_forbidden"] = missing.get("ok") is False and missing.get("error") == "missing_twfecid"
    checks["skip_typed_stays_empty"] = skip_typed.get("ok") is False and skip_typed.get("error") == "typed_required"
    checks["skip_wildcard_stays_empty"] = skip_wildcard.get("ok") is False and skip_wildcard.get("error") == "wildcard_required"
    checks["skip_twfecdigest_stays_empty"] = skip_digest.get("ok") is False and skip_digest.get("error") == "twfecdigest_required"
    checks["skip_twfecid_stays_empty"] = skip_id.get("ok") is False and skip_id.get("error") == "twfecid_required"

    family = capability_family(TWFEC_ACTUATION_GOAL)
    tokens = set(semantic_tokens(TWFEC_ACTUATION_GOAL))
    checks["family_is_twfec"] = "twfec" in family.split("/") and "twfecid" in tokens and "rfc6667" in tokens
    checks["family_is_not_wildad"] = (
        leftover_marker_ids(WILDAD_ACTUATION_GOAL) == (WILDAD_ACTUATION_ID,)
        and "wildad" not in family.split("/")
        and "wildid" not in tokens
    )
    checks["family_is_not_gtsm"] = (
        "gtsm" not in family.split("/")
        and "rfc6720" not in family
        and "gtsmid" not in family
        and "gtsmdigest" not in family
    )

    catalog = DIVERSITY_CATALOG
    checks["catalog_names_twfec"] = (
        len(catalog) > 235
        and catalog[235]["id"] == TWFEC_ACTUATION_ID
        and catalog[235]["source"] == "genesis_bind_twfec"
    )
    checks["catalog_names_gtsm"] = (
        len(catalog) > 236
        and catalog[236]["id"] == GTSM_ACTUATION_ID
        and catalog[236]["source"] == "genesis_bind_gtsm"
    )

    with tempfile.TemporaryDirectory(prefix="twfec-leftover-") as tmp:
        root = Path(tmp)
        rfc6667_leftover = (
            "Later genesis can take RFC 6667 LDP Typed Wildcard FEC TYPED/WILDCARD "
            "over a twfecid-gated twfecdigest."
        )
        open_before = leftover_is_open(rfc6667_leftover, root, ledger=CapabilityLedger())
        register_catalog_proved(root, TWFEC_ACTUATION_ID)
        fixture_ledger = load_ledger(default_ledger_path(root))
        reason = leftover_satisfied_by(rfc6667_leftover, root, ledger=fixture_ledger)
        after = leftover_is_open(rfc6667_leftover, root, ledger=fixture_ledger)
        next_open = leftover_is_open(TWFEC_LEFTOVER, root, ledger=fixture_ledger)
    checks["rfc6667_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_twfec_consumes_leftover"] = after is False and reason.startswith(f"ledger:{TWFEC_ACTUATION_ID}")
    checks["next_gtsm_leftover_stays_open"] = next_open is True
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_twfec_actuation_capability()
    return {
        "ok": ok,
        "action": "twfec_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": TWFEC_ACTUATION_GOAL,
        "done_when": TWFEC_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
