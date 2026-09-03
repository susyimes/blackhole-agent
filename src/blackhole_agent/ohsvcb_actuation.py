"""Drive a first-class Oblivious Service Binding tool through RFC 9540 QUERY/ANSWER.

Tool routing already fails missions that require ``ohsvcb``: hosted ohsvcb
endpoints stay on the unsupported MCP provider, and no first-party ohsvcb
provider is executable. Unbound therefore cannot speak a QUERY,
lockstep an ANSWER svcbid handshake over DNS Oblivious Service Binding SVCBID,
independently poll the stored keyconf, or seal a keyconf digest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``ohsvcb`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9540 daemon
- keep a missing-svcbid client so the ohsvcb-svcbid hole stays falsifiable
- refuse ANSWER verify until a QUERY lands with a non-empty svcbid
- independently poll the stored keyconf on a later client socket
- persist a sealed keyconf digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9458 Oblivious HTTP
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
    OHSVCB_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    ohsvcb_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
OHSVCB_ACTUATION_ID = "capability.ohsvcb-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-OS-OK"
POLL_TOKEN = "BH-OS-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_SVCBID = 0
EMPTY_KEYCONF = 0
OS_FIRST = 0x40  # RFC 9460/9540 SVCB RR type
SVCBID_SIZE = 4
KEYCONF_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_ANSWER = 0x02  # RFC 9540 DNS SVCB Answer
FRAME_QUERY = 0x01  # RFC 9540 DNS SVCB Query
OHSVCB_PARAM_KEY = 8  # RFC 9540 ohttp SvcParamKey
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
OHSVCB_LEFTOVER = (
    "Later genesis can take RFC 9540 Oblivious Service Binding QUERY/ANSWER over a "
    "svcbid-gated keyconf digest."
)


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


OHSVCB_ACTUATION_DONE_WHEN = (
    f"capability_exists:{OHSVCB_ACTUATION_ID};"
    f"capability_proved:{OHSVCB_ACTUATION_ID};"
    "no_skill_route"
)
OHSVCB_ACTUATION_GOAL = (
    "Repair rfc9540 ohsvcb query/answer cycle cannot land over dns "
    "ohsvcb svcbid: hosted ohsvcb endpoints remain unsupported so a QUERY then "
    "ANSWER svcbid handshake cannot land and a sealed keyconf digest "
    "cannot be produced. A missing ohsvcb svcbid stays forbidden; fail-closed "
    "routing never opts the ohsvcb provider in. An independent later poll of the "
    "stored service keyconf keeps the hole falsifiable."
)


class OhsvcbActuationError(RuntimeError):
    """Raised when the Oblivious Service Binding session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_svcbid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"svcbid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_svcbid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-svcbid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_keyconf(svcbid: int = EMPTY_SVCBID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"keyconf:{int(svcbid) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_SVCBID = request_svcbid(SENTINEL)
DEFAULT_KEYCONF = request_keyconf(DEFAULT_SVCBID, SENTINEL)


def encode_varint(value: int) -> bytes:
    number = int(value)
    if number < 0:
        number = 0
    if number <= 63:
        return bytes([number])
    if number <= 16383:
        return struct.pack("!H", 0x4000 | number)
    if number <= 1073741823:
        return struct.pack("!I", 0x80000000 | number)
    return struct.pack("!Q", 0xC000000000000000 | (number & 0x3FFFFFFFFFFFFFFF))


def decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    raw = bytes(data or b"")
    if offset >= len(raw):
        raise OhsvcbActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise OhsvcbActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise OhsvcbActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise OhsvcbActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    svcbid: int,
    keyconf: int,
    include_svcbid: bool = True,
) -> bytes:
    live_svcbid = int(svcbid) & 0xFFFFFFFF if include_svcbid else EMPTY_SVCBID
    live_keyconf = int(keyconf) & 0xFFFFFFFF if include_svcbid and live_svcbid else EMPTY_KEYCONF
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_keyconf, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_svcbid) if live_svcbid else b""
    header = bytearray()
    header.append(OS_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_query(
    *,
    identity: str,
    svcbid: int,
    keyconf: int | None = None,
    include_svcbid: bool = True,
) -> bytes:
    live_svcbid = int(svcbid) & 0xFFFFFFFF if include_svcbid else EMPTY_SVCBID
    live_keyconf = int(keyconf) if keyconf is not None else request_keyconf(live_svcbid, identity)
    return encode_packet(
        FRAME_QUERY,
        identity=identity,
        svcbid=live_svcbid,
        keyconf=live_keyconf,
        include_svcbid=include_svcbid,
    )


def encode_answer(
    *,
    identity: str,
    svcbid: int,
    keyconf: int | None = None,
    include_svcbid: bool = True,
) -> bytes:
    live_svcbid = int(svcbid) & 0xFFFFFFFF if include_svcbid else EMPTY_SVCBID
    live_keyconf = int(keyconf) if keyconf is not None else request_keyconf(live_svcbid, identity)
    return encode_packet(
        FRAME_ANSWER,
        identity=identity,
        svcbid=live_svcbid,
        keyconf=live_keyconf,
        include_svcbid=include_svcbid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise OhsvcbActuationError("short_packet")
    first = raw[0]
    if first != OS_FIRST:
        raise OhsvcbActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise OhsvcbActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == SVCBID_SIZE:
        live_svcbid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_svcbid = EMPTY_SVCBID
    else:
        raise OhsvcbActuationError("illegal_svcbid")
    if offset >= len(raw):
        raise OhsvcbActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_QUERY, FRAME_ANSWER}:
        raise OhsvcbActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise OhsvcbActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise OhsvcbActuationError("checksum_failed")
    if len(payload) < 5:
        raise OhsvcbActuationError("short_packet")
    live_keyconf, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise OhsvcbActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_svcbid = int(live_svcbid) != EMPTY_SVCBID
    has_keyconf = has_svcbid and int(live_keyconf) != EMPTY_KEYCONF
    is_query = frame_type == FRAME_QUERY
    is_answer = frame_type == FRAME_ANSWER
    return {
        "type": int(frame_type),
        "is_query": is_query,
        "is_answer": is_answer,
        "is_response": is_answer,
        "svcbid": int(live_svcbid),
        "has_svcbid": has_svcbid,
        "keyconf": int(live_keyconf),
        "has_keyconf": has_keyconf,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "ohsvcb_param_key": OHSVCB_PARAM_KEY,
    }


class OhsvcbClient:
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
            raise OhsvcbActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_answer"] or not packet["is_response"]:
            raise OhsvcbActuationError("keyconf_required")
        if not packet["has_svcbid"]:
            raise OhsvcbActuationError("svcbid_required")
        if not packet["has_keyconf"]:
            raise OhsvcbActuationError("keyconf_required")
        return packet

    def exchange(self, packet: bytes, *, wait_keyconf: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_keyconf:
            raise OhsvcbActuationError("keyconf_required")
        reply = self._recv()
        return {
            "session": reply,
            "svcbid": int(reply.get("svcbid") or EMPTY_SVCBID),
            "identity": str(reply.get("identity") or ""),
            "keyconf": int(reply.get("keyconf") or EMPTY_KEYCONF),
        }

    def answer(
        self,
        identity: str,
        svcbid: int,
        keyconf: int = EMPTY_KEYCONF,
        *,
        wait_keyconf: bool = True,
        include_svcbid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_answer(
            identity=identity,
            svcbid=svcbid,
            keyconf=keyconf or request_keyconf(svcbid, identity),
            include_svcbid=include_svcbid,
        )
        return self.exchange(packet, wait_keyconf=wait_keyconf)


class OhsvcbSession:
    """SVCBID-gated loopback RFC 9540 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        svcbid_gate: int = DEFAULT_SVCBID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.svcbid_gate = int(svcbid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.svcbid = EMPTY_SVCBID
        self.keyconf = EMPTY_KEYCONF
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.opened = False
        self.handshook = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_svcbid_once(self, identity: str, svcbid: int, keyconf: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(svcbid or EMPTY_SVCBID)
            live_keyconf = int(keyconf or EMPTY_KEYCONF)
            if not self.identity and name and live:
                self.identity = name
                self.svcbid = live
                self.keyconf = live_keyconf or request_keyconf(live, name)
                self.stored = True
            return str(self.identity), int(self.svcbid), int(self.keyconf)

    def read_svcbid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.svcbid), int(self.keyconf)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "svcbid": EMPTY_SVCBID,
            "keyconf": EMPTY_KEYCONF,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _svcbid_missing(self) -> bool:
        return not int(self.svcbid_gate or 0)

    def _reply_answer(self, peer: tuple[str, int], identity: str, svcbid: int, keyconf: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_answer(
            identity=identity,
            svcbid=svcbid,
            keyconf=keyconf,
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
            except OhsvcbActuationError:
                continue
            if not packet.get("is_query") and not packet.get("is_answer"):
                continue
            if not packet.get("has_svcbid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_svcbid, stored_keyconf = self.store_svcbid_once(
                identity,
                int(packet.get("svcbid") or EMPTY_SVCBID),
                int(packet.get("keyconf") or EMPTY_KEYCONF),
            )
            if not stored_name or not stored_svcbid or not stored_keyconf:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_query"):
                    self.opened = True
                if packet.get("is_answer"):
                    self.handshook = True
                self.retrieved = True
            self._reply_answer(peer, stored_name, stored_svcbid, stored_keyconf)

    def bind(self) -> dict[str, Any]:
        if self._svcbid_missing():
            return self._forbidden("missing_svcbid")
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
        do_query_cycle: bool = True,
        do_answer: bool = True,
        do_keyconf: bool = True,
        replay: bool = True,
        use_svcbid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._svcbid_missing():
            return self._forbidden("missing_svcbid")
        live_token = str(token or SENTINEL)
        origin_svcbid = request_svcbid(live_token)
        origin_keyconf = request_keyconf(origin_svcbid, live_token)
        client: OhsvcbClient | None = None
        independent: OhsvcbClient | None = None
        try:
            client = OhsvcbClient(self.host, int(self.port))
            if not do_query_cycle:
                return self._conflict("query_required")
            bind_packet = encode_query(
                identity=live_token,
                svcbid=origin_svcbid,
                keyconf=origin_keyconf,
                include_svcbid=use_svcbid,
            )
            if not use_svcbid:
                try:
                    client.exchange(bind_packet, wait_keyconf=True)
                except OhsvcbActuationError:
                    return self._conflict("svcbid_required")
                return self._conflict("svcbid_required")
            client.send(bind_packet)
            if not do_answer:
                return self._conflict("answer_required")
            proxy_packet = encode_answer(
                identity=live_token,
                svcbid=origin_svcbid,
                keyconf=origin_keyconf,
                include_svcbid=True,
            )
            if not do_keyconf:
                try:
                    client.exchange(proxy_packet, wait_keyconf=False)
                except OhsvcbActuationError as error:
                    if str(error) == "keyconf_required":
                        return self._conflict("keyconf_required")
                    return self._conflict("keyconf_required")
                return self._conflict("keyconf_required")
            try:
                reply = client.exchange(proxy_packet, wait_keyconf=True)
            except OhsvcbActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("svcbid_required")
                if reason == "keyconf_required":
                    return self._conflict("keyconf_required")
                return self._conflict("query_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("query_required")
            if int(reply.get("svcbid") or EMPTY_SVCBID) != origin_svcbid:
                return self._conflict("keyconf_required")
            if int(reply.get("keyconf") or EMPTY_KEYCONF) != origin_keyconf:
                return self._conflict("keyconf_required")
            self.retrieved = True
            if replay:
                independent = OhsvcbClient(self.host, int(self.port))
                try:
                    poll = independent.answer(
                        POLL_TOKEN,
                        poll_svcbid(live_token),
                        request_keyconf(poll_svcbid(live_token), POLL_TOKEN),
                        wait_keyconf=True,
                    )
                except OhsvcbActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_svcbid, stored_keyconf = self.read_svcbid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_svcbid != origin_svcbid
                    or stored_keyconf != origin_keyconf
                    or int(poll.get("svcbid") or EMPTY_SVCBID) != origin_svcbid
                    or int(poll.get("keyconf") or EMPTY_KEYCONF) != origin_keyconf
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_svcbid}:{origin_keyconf}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "svcbid": origin_svcbid,
                "keyconf": origin_keyconf,
                "query": True,
                "answer": True,
                "keyconf_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "svcbid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_ohsvcb_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "svcbid": origin_svcbid,
                "keyconf": origin_keyconf,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "query": True,
                "answer": True,
                "keyconf_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "svcbid_bound": True,
            }
        except (OSError, OhsvcbActuationError) as error:
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
        live = independent_ohsvcb_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "svcbid": int(live.get("svcbid") or EMPTY_SVCBID),
            "keyconf": int(live.get("keyconf") or EMPTY_KEYCONF),
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


def call_ohsvcb_tool(session: OhsvcbSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one OHSVCB tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_query_cycle = True if arguments.get("query_cycle") is None else bool(arguments.get("query_cycle"))
    do_answer = True if arguments.get("answer") is None else bool(arguments.get("answer"))
    do_keyconf = True if arguments.get("keyconf") is None else bool(arguments.get("keyconf"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_svcbid = True if arguments.get("use_svcbid") is None else bool(arguments.get("use_svcbid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_query_cycle=do_query_cycle,
            do_answer=do_answer,
            do_keyconf=do_keyconf,
            replay=replay,
            use_svcbid=use_svcbid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise OhsvcbActuationError(f"unsupported ohsvcb action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_ohsvcb_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed OHSVCB keyconf digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "svcbid": EMPTY_SVCBID,
        "keyconf": EMPTY_KEYCONF,
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
            "query",
            "answer",
            "keyconf_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "svcbid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    svcbid = int(payload.get("svcbid") or EMPTY_SVCBID)
    keyconf = int(payload.get("keyconf") or EMPTY_KEYCONF)
    dual = port > 0 and bool(svcbid) and bool(keyconf)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "svcbid": svcbid,
        "keyconf": keyconf,
        "size": int(payload.get("size") or 0),
        "port": port,
        "query": payload.get("query") is True,
        "answer": payload.get("answer") is True,
        "keyconf_response": payload.get("keyconf_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "svcbid_bound": payload.get("svcbid_bound") is True,
    }


def run_ohsvcb_workflow(
    *,
    with_svcbid: bool = True,
    skip_bind: bool = False,
    do_query_cycle: bool = True,
    do_answer: bool = True,
    do_keyconf: bool = True,
    replay: bool = True,
    use_svcbid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9540 QUERY/ANSWER svcbid cycle workflow."""

    descriptor = ohsvcb_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, OHSVCB_TOOL_PROVIDER),
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
        raise OhsvcbActuationError(f"ohsvcb tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ohsvcb-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = OhsvcbSession(out, svcbid_gate=DEFAULT_SVCBID if with_svcbid else EMPTY_SVCBID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "query_cycle": do_query_cycle,
            "answer": do_answer,
            "keyconf": do_keyconf,
            "replay": replay,
            "use_svcbid": use_svcbid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_ohsvcb_tool(session, arguments))
            except OhsvcbActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_ohsvcb_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_svcbid
        and not skip_bind
        and do_query_cycle
        and do_answer
        and do_keyconf
        and replay
        and use_svcbid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ohsvcb_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_svcbid": with_svcbid,
        "skip_bind": skip_bind,
        "query": do_query_cycle,
        "answer": do_answer,
        "keyconf": do_keyconf,
        "replay": replay,
        "use_svcbid": use_svcbid,
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
        "svcbid_value": int(publish_result.get("svcbid") or independent.get("svcbid") or EMPTY_SVCBID),
        "keyconf_value": int(publish_result.get("keyconf") or independent.get("keyconf") or EMPTY_KEYCONF),
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
        "svcbid": int(trace_body["svcbid_value"] or EMPTY_SVCBID),
        "keyconf": int(trace_body["keyconf_value"] or EMPTY_KEYCONF),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_svcbid": with_svcbid,
        "skip_bind": skip_bind,
        "query_cycle": do_query_cycle,
        "answer_cycle": do_answer,
        "keyconf_cycle": do_keyconf,
        "replay": replay,
        "use_svcbid": use_svcbid,
    }


def verify_ohsvcb_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed OHSVCB trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_ohsvcb_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    svcbid = int(trace.get("svcbid_value") or independent.get("svcbid") or EMPTY_SVCBID)
    keyconf = int(trace.get("keyconf_value") or independent.get("keyconf") or EMPTY_KEYCONF)
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
        "query": independent.get("query") is True,
        "answer": independent.get("answer") is True,
        "keyconf_response": independent.get("keyconf_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "svcbid_bound": independent.get("svcbid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "keyconf_recorded": (
            port > 0
            and svcbid == DEFAULT_SVCBID
            and keyconf == DEFAULT_KEYCONF
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}

def ohsvcb_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.ohsvcb_actuation import "
        "builtin_ohsvcb_actuation_proof; r=builtin_ohsvcb_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='ohsvcb_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_ohsvcb_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=OHSVCB_ACTUATION_ID,
        name="First-class RFC 9540 Oblivious Service Binding QUERY/ANSWER actuation",
        description=(
            "Missions that require an ohsvcb tool can opt the ohsvcb provider in, "
            "bind a loopback RFC 9540 Oblivious Service Binding nameserver, complete a QUERY "
            "with a non-empty svcbid, lockstep an ANSWER that carries the "
            "stored keyconf, independently poll the stored "
            "keyconf on a later socket, and seal a digest-chained keyconf. Default "
            "routing stays fail-closed; a missing svcbid keeps the hole "
            "falsifiable, and skip-QUERY/ANSWER/KEYCONF/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.ohsvcb_actuation:builtin_ohsvcb_actuation_proof",
        proof_command=ohsvcb_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.ohttp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/ohsvcb_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/httpsig_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required ohsvcb tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9540 daemon, speaks a "
            "QUERY then ANSWER over Oblivious Service Binding with a non-empty svcbid and "
            "keyconf, independently polls the stored keyconf on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9458 Oblivious HTTP lockstep is proved. "
            "Missing svcbids, skip-QUERY, skip-ANSWER, skip-keyconf, skip-REPLAY, "
            "and a QUERY aimed without a svcbid stay fail-closed. "
            "Later genesis can take RFC 9421 HTTP Message Signatures SIGN/VERIFY as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("ohsvcb", "rfc9540", "dns", "svcbid", "keyconf", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T065012Z-1e8a3b8a",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_ohsvcb_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9540 Oblivious Service Binding lockstep actuation seals a keyconf digest."""

    from blackhole_agent.httpsig_actuation import HTTPSIG_ACTUATION_GOAL, HTTPSIG_ACTUATION_ID
    from blackhole_agent.ohttp_actuation import OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID
    from blackhole_agent.connectip_actuation import CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID
    from blackhole_agent.masque_actuation import MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID
    from blackhole_agent.datagram_actuation import DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID
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
    from blackhole_agent.kernel_leftover import leftover_is_open, leftover_satisfied_by
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
    from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
    from blackhole_agent.webtransport_actuation import (
        WEBTRANSPORT_ACTUATION_GOAL,
        WEBTRANSPORT_ACTUATION_ID,
    )
    from blackhole_agent.quic_actuation import QUIC_ACTUATION_GOAL, QUIC_ACTUATION_ID
    from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
    from blackhole_agent.sctp_actuation import SCTP_ACTUATION_GOAL, SCTP_ACTUATION_ID
    from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.srtp_actuation import SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID
    from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
    from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
    from blackhole_agent.datachannel_actuation import (
        DATACHANNEL_ACTUATION_GOAL,
        DATACHANNEL_ACTUATION_ID,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = OHSVCB_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(OHSVCB_ACTUATION_GOAL) == (
        OHSVCB_ACTUATION_ID,
    )
    checks["leftover_text_binds_ohsvcb"] = leftover_marker_ids(OHSVCB_LEFTOVER) == (
        OHSVCB_ACTUATION_ID,
    )
    neighbor_goals = (
        (OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID, "ohttp"),
        (CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID, "connectip"),
        (MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID, "masque"),
        (DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID, "datagram"),
        (WEBTRANSPORT_ACTUATION_GOAL, WEBTRANSPORT_ACTUATION_ID, "webtransport"),
        (HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID, "http3"),
        (QUIC_ACTUATION_GOAL, QUIC_ACTUATION_ID, "quic"),
        (DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID, "datachannel"),
        (SCTP_ACTUATION_GOAL, SCTP_ACTUATION_ID, "sctp"),
        (SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID, "srtp"),
        (DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID, "dtls"),
        (ICE_ACTUATION_GOAL, ICE_ACTUATION_ID, "ice"),
        (TURN_ACTUATION_GOAL, TURN_ACTUATION_ID, "turn"),
        (STUN_ACTUATION_GOAL, STUN_ACTUATION_ID, "stun"),
        (SIP_ACTUATION_GOAL, SIP_ACTUATION_ID, "sip"),
        (IKE_ACTUATION_GOAL, IKE_ACTUATION_ID, "ike"),
        (DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID, "dhcp"),
        (RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID, "radius"),
        (NTP_ACTUATION_GOAL, NTP_ACTUATION_ID, "ntp"),
        (SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID, "syslog"),
        (SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID, "snmp"),
        (TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID, "tftp"),
        (FTP_ACTUATION_GOAL, FTP_ACTUATION_ID, "ftp"),
        (DNS_ACTUATION_GOAL, DNS_ACTUATION_ID, "dns"),
        (HTTPSIG_ACTUATION_GOAL, HTTPSIG_ACTUATION_ID, "httpsig"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_ohsvcb"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"ohsvcb_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            OHSVCB_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = OHSVCB_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    checks["catalog_names_ohsvcb"] = (
        len(catalog) > 68
        and catalog[68]["id"] == OHSVCB_ACTUATION_ID
        and catalog[67]["id"] == OHTTP_ACTUATION_ID
        and catalog[68]["source"] == "genesis_bind_ohsvcb"
    )
    checks["catalog_names_httpsig"] = (
        len(catalog) > 69
        and catalog[69]["id"] == HTTPSIG_ACTUATION_ID
        and catalog[69]["source"] == "genesis_bind_httpsig"
    )
    family = capability_family(OHSVCB_ACTUATION_GOAL)
    checks["family_is_ohsvcb"] = "ohsvcb" in family
    checks["family_is_rfc9540"] = "rfc9540" in family
    checks["family_is_svcbid"] = "svcbid" in family
    checks["family_is_keyconf"] = "keyconf" in family
    checks["family_is_not_ohttp"] = (
        "ohttp" not in family
        and "rfc9458" not in family
        and "configid" not in family
        and "gateway" not in family
    )
    checks["family_is_not_connectip"] = (
        "connectip" not in family
        and "rfc9484" not in family
        and "prefixid" not in family
        and "ipaddr" not in family
    )
    checks["family_is_not_masque"] = (
        "masque" not in family
        and "rfc9298" not in family
        and "targetid" not in family
        and "authority" not in family
    )
    checks["family_is_not_datagram"] = (
        "datagram" not in family
        and "rfc9221" not in family
        and "flowid" not in family
        and "contextid" not in family
    )
    checks["family_is_not_webtransport"] = (
        "webtransport" not in family
        and "rfc9220" not in family
        and "sessionid" not in family
        and "capsule" not in family
    )
    checks["family_is_not_http3"] = (
        "http3" not in family
        and "rfc9114" not in family
        and "streamid" not in family
        and "qpack" not in family
    )
    checks["family_is_not_quic"] = (
        "quic" not in family
        and "rfc9000" not in family
        and "dcid" not in family
        and "pktnum" not in family
    )
    checks["family_is_not_datachannel"] = (
        "datachannel" not in family
        and "rfc8831" not in family
        and "ppid" not in family
        and "dcep" not in family
    )
    checks["family_is_not_sctp_association"] = (
        "rfc4960" not in family and "vtag" not in family and "tsn" not in family
    )
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
    checks["family_is_not_httpsig"] = (
        "httpsig" not in family
        and "rfc9421" not in family
        and "sigid" not in family
        and "sigbase" not in family
    )
    packed = encode_query(identity=SENTINEL, svcbid=DEFAULT_SVCBID, keyconf=DEFAULT_KEYCONF)
    parsed = parse_message(packed)
    checks["query_roundtrip"] = (
        parsed["is_query"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_svcbid"] is True
        and parsed["svcbid"] == DEFAULT_SVCBID
        and parsed["keyconf"] == DEFAULT_KEYCONF
        and parsed["is_response"] is False
        and parsed["is_answer"] is False
        and parsed["type"] == FRAME_QUERY
        and parsed["first_byte"] == OS_FIRST
    )
    shook = encode_answer(
        identity=SENTINEL,
        svcbid=DEFAULT_SVCBID,
        keyconf=DEFAULT_KEYCONF,
    )
    answer_parsed = parse_message(shook)
    checks["answer_roundtrip"] = (
        answer_parsed["is_answer"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_query"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["svcbid"] == DEFAULT_SVCBID
        and answer_parsed["keyconf"] == DEFAULT_KEYCONF
        and answer_parsed["has_keyconf"] is True
        and answer_parsed["type"] == FRAME_ANSWER
        and answer_parsed["first_byte"] == OS_FIRST
    )
    bare = encode_query(identity=SENTINEL, svcbid=DEFAULT_SVCBID, include_svcbid=False)
    checks["missing_svcbid_is_unauthenticated"] = parse_message(bare)["has_svcbid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    ohsvcb_signature = semantic_signature(OHSVCB_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(ohsvcb_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_ohsvcb = ToolDescriptor(name="remote_ohsvcb", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_ohsvcb)
    checks["naive_mcp_ohsvcb_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = ohsvcb_tool_descriptor()
    default_ohsvcb = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, OHSVCB_TOOL_PROVIDER),
    )
    checks["default_ohsvcb_provider_is_unsupported"] = (
        default_ohsvcb.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{OHSVCB_TOOL_PROVIDER}" in default_ohsvcb.reasons
    )
    checks["opted_in_ohsvcb_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_ohsvcb],
        required_tool_names=("local_memory", "ohsvcb"),
    )
    checks["naive_preflight_missing_ohsvcb"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["ohsvcb"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "ohsvcb"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, OHSVCB_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "ohsvcb" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="ohsvcb-actuation-") as tmp:
        root = Path(tmp)
        missing = run_ohsvcb_workflow(with_svcbid=False, output_dir=root / "missing")
        skip_bind = run_ohsvcb_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_query_cycle = run_ohsvcb_workflow(do_query_cycle=False, output_dir=root / "skip-bind-cycle")
        skip_answer = run_ohsvcb_workflow(do_answer=False, output_dir=root / "skip-proxy")
        skip_keyconf = run_ohsvcb_workflow(do_keyconf=False, output_dir=root / "skip-keyconf")
        skip_replay = run_ohsvcb_workflow(replay=False, output_dir=root / "skip-replay")
        skip_svcbid = run_ohsvcb_workflow(use_svcbid=False, output_dir=root / "skip-svcbid")
        live = run_ohsvcb_workflow(output_dir=root / "live")
        verify = verify_ohsvcb_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_ohsvcb_trace(clone)
        checks["naive_without_svcbid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_svcbid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_query_cycle_stays_empty"] = (
            skip_query_cycle["ok"] is False
            and skip_query_cycle["error"] == "query_required"
            and skip_query_cycle["final_status"] == 409
            and skip_query_cycle["payload_exists"] is False
        )
        checks["skip_answer_stays_empty"] = (
            skip_answer["ok"] is False
            and skip_answer["error"] == "answer_required"
            and skip_answer["final_status"] == 409
            and skip_answer["payload_exists"] is False
        )
        checks["skip_keyconf_stays_empty"] = (
            skip_keyconf["ok"] is False
            and skip_keyconf["error"] == "keyconf_required"
            and skip_keyconf["final_status"] == 409
            and skip_keyconf["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_svcbid_stays_empty"] = (
            skip_svcbid["ok"] is False
            and skip_svcbid["error"] == "svcbid_required"
            and skip_svcbid["final_status"] == 409
            and skip_svcbid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_keyconf"] = (
            int(live.get("svcbid") or 0) == DEFAULT_SVCBID
            and int(live.get("keyconf") or 0) == DEFAULT_KEYCONF
            and int(live.get("port") or 0) > 0
        )
        checks["token_svcbid_query_answer_keyconf_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_query_cycle["ok"] is False
            and skip_answer["ok"] is False
            and skip_keyconf["ok"] is False
            and skip_replay["ok"] is False
            and skip_svcbid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="ohsvcb-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != OHSVCB_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_ohsvcb"] = (
        live_goal == OHSVCB_ACTUATION_GOAL
        and OHSVCB_ACTUATION_ID in live_done
        and live_source == "genesis_bind_ohsvcb"
    )

    with tempfile.TemporaryDirectory(prefix="ohsvcb-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(OHSVCB_LEFTOVER, root)
        register_catalog_proved(root, OHSVCB_ACTUATION_ID)
        reason = leftover_satisfied_by(OHSVCB_LEFTOVER, root)
        after = leftover_is_open(OHSVCB_LEFTOVER, root)
    checks["ohsvcb_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_ohsvcb_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{OHSVCB_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_ohsvcb_actuation_capability()
    return {
        "ok": ok,
        "action": "ohsvcb_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": OHSVCB_ACTUATION_GOAL,
        "done_when": OHSVCB_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
