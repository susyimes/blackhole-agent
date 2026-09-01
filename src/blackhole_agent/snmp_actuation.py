"""Drive a first-class SNMP tool through RFC 1157 GET/SET/RESPONSE lockstep.

Tool routing already fails missions that require ``snmp``: hosted SNMP
plugins stay on the unsupported MCP provider, and no first-party SNMP
provider is executable. Unbound therefore cannot speak SET, lockstep
GET/RESPONSE PDUs over UDP, independently GET the stored varbind, or seal a
varbind digest an independent later reader can re-open.

This module closes that hole:

- advertise an ``snmp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1157 listener
- keep a missing-community client so the community hole stays falsifiable
- refuse GET/RESPONSE until SET lands and the agent echoes a GetResponse
- independently GET the stored varbind on a later client socket
- persist a sealed varbind digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after TFTP
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
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
    SNMP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    snmp_tool_descriptor,
)

SCHEMA_VERSION = 1
SNMP_ACTUATION_ID = "capability.snmp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SNMP-OK"
DEFAULT_COMMUNITY = "blackhole"
DEFAULT_OID = "1.3.6.1.4.1.53864.1.1.1"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2

VERSION_V1 = 0
PDU_GET = 0xA0
PDU_GET_NEXT = 0xA1
PDU_RESPONSE = 0xA2
PDU_SET = 0xA3
ERR_NO_ERROR = 0
ERR_NO_SUCH_NAME = 2
ERR_GEN = 5
TAG_SEQUENCE = 0x30
TAG_INTEGER = 0x02
TAG_OCTET = 0x04
TAG_NULL = 0x05
TAG_OID = 0x06

SNMP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SNMP_ACTUATION_ID};"
    f"capability_proved:{SNMP_ACTUATION_ID};"
    "no_skill_route"
)
SNMP_ACTUATION_GOAL = (
    "Repair rfc1157 snmp get/set/response cycle cannot land over udp lockstep "
    "pdus: hosted snmp tools remain unsupported so a SET then GET/RESPONSE "
    "pdu exchange cannot land and a sealed varbind digest cannot be produced. "
    "A missing snmp community stays forbidden; fail-closed routing never opts "
    "the snmp provider in. An independent later GET of the stored varbind "
    "keeps the hole falsifiable."
)


class SnmpActuationError(RuntimeError):
    """Raised when the SNMP session or loopback listener fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def sentinel_value(token: str = SENTINEL) -> bytes:
    return str(token or SENTINEL).encode("utf-8")


def _ber_len(n: int) -> bytes:
    size = int(n)
    if size < 0:
        raise SnmpActuationError("negative_length")
    if size < 128:
        return bytes([size])
    body = size.to_bytes((size.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _ber_tlv(tag: int, content: bytes) -> bytes:
    raw = bytes(content or b"")
    return bytes([int(tag) & 0xFF]) + _ber_len(len(raw)) + raw


def encode_integer(value: int) -> bytes:
    number = int(value)
    if number == 0:
        return _ber_tlv(TAG_INTEGER, b"\x00")
    length = 1
    while True:
        try:
            raw = number.to_bytes(length, "big", signed=True)
        except OverflowError:
            length += 1
            continue
        return _ber_tlv(TAG_INTEGER, raw)


def encode_octet(value: bytes | str) -> bytes:
    if isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = bytes(value or b"")
    return _ber_tlv(TAG_OCTET, raw)


def encode_null() -> bytes:
    return _ber_tlv(TAG_NULL, b"")


def encode_oid(oid: str) -> bytes:
    parts = [int(part) for part in str(oid or DEFAULT_OID).strip(".").split(".") if part]
    if len(parts) < 2:
        raise SnmpActuationError("short_oid")
    body = bytearray([40 * parts[0] + parts[1]])
    for number in parts[2:]:
        if number < 0:
            raise SnmpActuationError("negative_oid")
        stack = [number & 0x7F]
        number >>= 7
        while number:
            stack.append(0x80 | (number & 0x7F))
            number >>= 7
        body.extend(reversed(stack))
    return _ber_tlv(TAG_OID, bytes(body))


def encode_sequence(items: list[bytes], tag: int = TAG_SEQUENCE) -> bytes:
    return _ber_tlv(tag, b"".join(bytes(item or b"") for item in items))


def encode_varbind(oid: str, value: bytes | None) -> bytes:
    if value is None:
        return encode_sequence([encode_oid(oid), encode_null()])
    return encode_sequence([encode_oid(oid), encode_octet(value)])


def encode_pdu(
    pdu_type: int,
    request_id: int,
    varbinds: list[tuple[str, bytes | None]],
    *,
    error_status: int = ERR_NO_ERROR,
    error_index: int = 0,
) -> bytes:
    bindings = encode_sequence([encode_varbind(oid, value) for oid, value in varbinds])
    return encode_sequence(
        [
            encode_integer(request_id),
            encode_integer(error_status),
            encode_integer(error_index),
            bindings,
        ],
        tag=int(pdu_type) & 0xFF,
    )


def encode_message(community: str, pdu: bytes) -> bytes:
    return encode_sequence(
        [
            encode_integer(VERSION_V1),
            encode_octet(str(community or "").encode("ascii", errors="replace")),
            bytes(pdu or b""),
        ]
    )


def _read_tlv(buf: bytes, offset: int) -> tuple[int, bytes, int]:
    raw = bytes(buf or b"")
    if offset >= len(raw):
        raise SnmpActuationError("truncated_tag")
    tag = raw[offset]
    offset += 1
    if offset >= len(raw):
        raise SnmpActuationError("truncated_length")
    first = raw[offset]
    offset += 1
    if first < 128:
        length = first
    else:
        count = first & 0x7F
        if count == 0 or offset + count > len(raw):
            raise SnmpActuationError("truncated_length")
        length = int.from_bytes(raw[offset : offset + count], "big")
        offset += count
    if offset + length > len(raw):
        raise SnmpActuationError("truncated_value")
    return tag, raw[offset : offset + length], offset + length


def _read_all_tlvs(buf: bytes) -> list[tuple[int, bytes]]:
    items: list[tuple[int, bytes]] = []
    offset = 0
    raw = bytes(buf or b"")
    while offset < len(raw):
        tag, content, offset = _read_tlv(raw, offset)
        items.append((tag, content))
    return items


def decode_integer(content: bytes) -> int:
    raw = bytes(content or b"")
    if not raw:
        raise SnmpActuationError("empty_integer")
    return int.from_bytes(raw, "big", signed=True)


def decode_oid(content: bytes) -> str:
    raw = bytes(content or b"")
    if not raw:
        raise SnmpActuationError("empty_oid")
    first = raw[0]
    parts = [first // 40, first % 40]
    acc = 0
    for byte in raw[1:]:
        acc = (acc << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(acc)
            acc = 0
    if raw[-1] & 0x80:
        raise SnmpActuationError("truncated_oid")
    return ".".join(str(part) for part in parts)


def decode_varbind(content: bytes) -> dict[str, Any]:
    items = _read_all_tlvs(content)
    if len(items) < 2 or items[0][0] != TAG_OID:
        raise SnmpActuationError("malformed_varbind")
    tag, value = items[1]
    decoded: bytes | None
    if tag == TAG_NULL:
        decoded = None
    elif tag == TAG_OCTET:
        decoded = value
    elif tag == TAG_INTEGER:
        decoded = str(decode_integer(value)).encode("ascii")
    else:
        decoded = value
    return {"oid": decode_oid(items[0][1]), "tag": tag, "value": decoded}


def parse_packet(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    tag, content, _end = _read_tlv(raw, 0)
    if tag != TAG_SEQUENCE:
        raise SnmpActuationError("not_a_message")
    items = _read_all_tlvs(content)
    if len(items) < 3:
        raise SnmpActuationError("short_message")
    version_tag, version_body = items[0]
    community_tag, community_body = items[1]
    pdu_tag, pdu_body = items[2]
    if version_tag != TAG_INTEGER or community_tag != TAG_OCTET:
        raise SnmpActuationError("malformed_message")
    if pdu_tag not in {PDU_GET, PDU_GET_NEXT, PDU_RESPONSE, PDU_SET}:
        raise SnmpActuationError("illegal_pdu")
    fields = _read_all_tlvs(pdu_body)
    if len(fields) < 4:
        raise SnmpActuationError("short_pdu")
    if fields[0][0] != TAG_INTEGER or fields[1][0] != TAG_INTEGER or fields[2][0] != TAG_INTEGER:
        raise SnmpActuationError("malformed_pdu")
    if fields[3][0] != TAG_SEQUENCE:
        raise SnmpActuationError("malformed_varbind_list")
    varbinds = [decode_varbind(item[1]) for item in _read_all_tlvs(fields[3][1]) if item[0] == TAG_SEQUENCE]
    return {
        "version": decode_integer(version_body),
        "community": community_body.decode("ascii", errors="replace"),
        "pdu_type": pdu_tag,
        "request_id": decode_integer(fields[0][1]),
        "error_status": decode_integer(fields[1][1]),
        "error_index": decode_integer(fields[2][1]),
        "varbinds": varbinds,
    }


class _SnmpClient:
    def __init__(self, host: str, port: int, *, community: str, timeout: float = IO_TIMEOUT) -> None:
        self.host = host
        self.port = int(port)
        self.community = str(community or "")
        self.timeout = timeout
        self.request_id = 0
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

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def _recv(self) -> dict[str, Any]:
        try:
            payload, _addr = self.sock.recvfrom(4096)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise SnmpActuationError("timeout") from error
        return parse_packet(payload)

    def _exchange(
        self,
        pdu_type: int,
        varbinds: list[tuple[str, bytes | None]],
        *,
        community: str | None = None,
        wait_response: bool = True,
    ) -> dict[str, Any]:
        request_id = self._next_id()
        packet = encode_message(
            community if community is not None else self.community,
            encode_pdu(pdu_type, request_id, varbinds),
        )
        self.sock.sendto(packet, (self.host, self.port))
        if not wait_response:
            raise SnmpActuationError("response_required")
        reply = self._recv()
        if reply["pdu_type"] != PDU_RESPONSE or int(reply.get("request_id") or -1) != request_id:
            raise SnmpActuationError("response_required")
        return reply

    def set(
        self,
        oid: str,
        value: bytes,
        *,
        wait_response: bool = True,
        use_community: bool = True,
    ) -> dict[str, Any]:
        community = self.community if use_community else ""
        reply = self._exchange(
            PDU_SET,
            [(oid, bytes(value or b""))],
            community=community,
            wait_response=wait_response,
        )
        if int(reply.get("error_status") or 0) != ERR_NO_ERROR:
            raise SnmpActuationError("set_required")
        return reply

    def get(self, oid: str, *, wait_response: bool = True) -> bytes:
        reply = self._exchange(PDU_GET, [(oid, None)], wait_response=wait_response)
        if int(reply.get("error_status") or 0) != ERR_NO_ERROR:
            raise SnmpActuationError("get_required")
        varbinds = list(reply.get("varbinds") or [])
        if not varbinds or varbinds[0].get("oid") != oid or varbinds[0].get("value") is None:
            raise SnmpActuationError("get_required")
        return bytes(varbinds[0]["value"] or b"")


class SnmpSession:
    """Community-gated loopback RFC 1157 listener: bind, publish, read."""

    def __init__(self, output_dir: Path, *, community: str = DEFAULT_COMMUNITY) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.community = str(community or "")
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.varbinds: dict[str, bytes] = {}
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.last_token = ""
        self.last_digest = ""
        self.last_request_id = 0
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_varbind(self, oid: str, value: bytes) -> None:
        with self._lock:
            self.varbinds[str(oid or DEFAULT_OID)] = bytes(value or b"")
            self.stored = True

    def read_varbind(self, oid: str) -> bytes | None:
        with self._lock:
            if str(oid or DEFAULT_OID) not in self.varbinds:
                return None
            return self.varbinds[str(oid or DEFAULT_OID)]

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "request_id": 0,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _reply(self, peer: tuple[str, int], community: str, request_id: int, varbinds: list[tuple[str, bytes | None]], *, error_status: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_message(
            community,
            encode_pdu(PDU_RESPONSE, request_id, varbinds, error_status=error_status),
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
            except SnmpActuationError:
                continue
            if packet.get("version") != VERSION_V1:
                continue
            if str(packet.get("community") or "") != self.community:
                continue
            peer = (str(addr[0]), int(addr[1]))
            request_id = int(packet.get("request_id") or 0)
            with self._lock:
                self.last_request_id = request_id
            pdu_type = int(packet.get("pdu_type") or 0)
            varbinds = list(packet.get("varbinds") or [])
            if pdu_type == PDU_SET:
                stored: list[tuple[str, bytes | None]] = []
                for item in varbinds:
                    oid = str(item.get("oid") or DEFAULT_OID)
                    value = item.get("value")
                    if value is None:
                        self._reply(peer, self.community, request_id, [(oid, None)], error_status=ERR_GEN)
                        stored = []
                        break
                    self.store_varbind(oid, bytes(value))
                    stored.append((oid, bytes(value)))
                if stored:
                    self._reply(peer, self.community, request_id, stored, error_status=ERR_NO_ERROR)
                continue
            if pdu_type == PDU_GET:
                echoed: list[tuple[str, bytes | None]] = []
                missing = False
                for item in varbinds:
                    oid = str(item.get("oid") or DEFAULT_OID)
                    value = self.read_varbind(oid)
                    if value is None:
                        missing = True
                        echoed.append((oid, None))
                        break
                    echoed.append((oid, value))
                self._reply(
                    peer,
                    self.community,
                    request_id,
                    echoed or [(DEFAULT_OID, None)],
                    error_status=ERR_NO_SUCH_NAME if missing else ERR_NO_ERROR,
                )
                continue

    def bind(self) -> dict[str, Any]:
        if not self.community:
            return self._forbidden("missing_community")
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
        do_set: bool = True,
        do_get: bool = True,
        response: bool = True,
        replay: bool = True,
        use_community: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.community:
            return self._forbidden("missing_community")
        live_token = str(token or SENTINEL)
        value = sentinel_value(live_token)
        client: _SnmpClient | None = None
        independent: _SnmpClient | None = None
        try:
            client = _SnmpClient(self.host, int(self.port), community=self.community)
            if not do_set:
                return self._conflict("set_required")
            try:
                set_reply = client.set(
                    DEFAULT_OID,
                    value,
                    wait_response=response,
                    use_community=use_community,
                )
            except SnmpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("community_required")
                if reason == "response_required":
                    return self._conflict("response_required")
                return self._conflict("set_required")
            self.last_request_id = int(set_reply.get("request_id") or 0)
            retrieved_value = b""
            if do_get:
                try:
                    retrieved_value = client.get(DEFAULT_OID, wait_response=True)
                except SnmpActuationError:
                    return self._conflict("get_required")
                if retrieved_value != value:
                    return self._conflict("get_required")
                self.retrieved = True
            elif replay:
                return self._conflict("get_required")
            if replay:
                independent = _SnmpClient(self.host, int(self.port), community=self.community)
                try:
                    replay_value = independent.get(DEFAULT_OID, wait_response=True)
                except SnmpActuationError:
                    return self._conflict("replay_required")
                if replay_value != value:
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(value)
            sealed = {
                "oid": DEFAULT_OID,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(value),
                "port": int(self.port or 0),
                "request_id": int(self.last_request_id),
                "client_port": int(client.client_port),
                "set": True,
                "get": True,
                "response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "community_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_snmp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "oid": DEFAULT_OID,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(value),
                "port": int(self.port or 0),
                "request_id": int(self.last_request_id),
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "set": True,
                "get": True,
                "response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "community_bound": True,
            }
        except (OSError, SnmpActuationError) as error:
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
        live = independent_snmp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "oid": str(live.get("oid") or ""),
            "port": int(live.get("port") or 0),
            "request_id": int(live.get("request_id") or 0),
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


def call_snmp_tool(session: SnmpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one SNMP tool call against a bound listener session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_set = True if arguments.get("set") is None else bool(arguments.get("set"))
    do_get = True if arguments.get("get") is None else bool(arguments.get("get"))
    response = True if arguments.get("response") is None else bool(arguments.get("response"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_community = (
        True if arguments.get("use_community") is None else bool(arguments.get("use_community"))
    )
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_set=do_set,
            do_get=do_get,
            response=response,
            replay=replay,
            use_community=use_community,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SnmpActuationError(f"unsupported snmp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_snmp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed SNMP varbind digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "oid": "",
        "port": 0,
        "request_id": 0,
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
            "set",
            "get",
            "response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "community_bound",
        )
    )
    port = int(payload.get("port") or 0)
    request_id = int(payload.get("request_id") or 0)
    dual = port > 0 and request_id > 0
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "oid": str(payload.get("oid") or ""),
        "size": int(payload.get("size") or 0),
        "port": port,
        "request_id": request_id,
        "set": payload.get("set") is True,
        "get": payload.get("get") is True,
        "response": payload.get("response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "community_bound": payload.get("community_bound") is True,
    }


def run_snmp_workflow(
    *,
    with_community: bool = True,
    skip_bind: bool = False,
    do_set: bool = True,
    do_get: bool = True,
    response: bool = True,
    replay: bool = True,
    use_community: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1157 SET/GET/RESPONSE workflow and seal a trace."""

    descriptor = snmp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SNMP_TOOL_PROVIDER),
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
        raise SnmpActuationError(f"snmp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="snmp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SnmpSession(out, community=DEFAULT_COMMUNITY if with_community else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "set": do_set,
            "get": do_get,
            "response": response,
            "replay": replay,
            "use_community": use_community,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_snmp_tool(session, arguments))
            except SnmpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_snmp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_community
        and not skip_bind
        and do_set
        and do_get
        and response
        and replay
        and use_community
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "snmp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_community": with_community,
        "skip_bind": skip_bind,
        "set": do_set,
        "get": do_get,
        "response": response,
        "replay": replay,
        "use_community": use_community,
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
        "request_id": int(publish_result.get("request_id") or independent.get("request_id") or 0),
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
        "request_id": int(trace_body["request_id"] or 0),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_community": with_community,
        "skip_bind": skip_bind,
        "set": do_set,
        "get": do_get,
        "response": response,
        "replay": replay,
        "use_community": use_community,
    }


def verify_snmp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed SNMP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_snmp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    request_id = int(trace.get("request_id") or independent.get("request_id") or 0)
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
        "set": independent.get("set") is True,
        "get": independent.get("get") is True,
        "response": independent.get("response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "community_bound": independent.get("community_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "request_id_bound": port > 0 and request_id > 0,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def snmp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.snmp_actuation import "
        "builtin_snmp_actuation_proof; r=builtin_snmp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='snmp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_snmp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SNMP_ACTUATION_ID,
        name="First-class RFC 1157 SNMP GET/SET/RESPONSE actuation",
        description=(
            "Missions that require an snmp tool can opt the snmp provider in, "
            "bind a loopback RFC 1157 UDP listener, complete SET, lockstep "
            "GET/RESPONSE PDUs with a community string, GET the stored "
            "varbind on the same client, independently GET it on a later "
            "socket, and seal a digest-chained varbind. Default routing "
            "stays fail-closed; a missing community keeps the hole "
            "falsifiable, and skip-SET/GET/RESPONSE/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.snmp_actuation:builtin_snmp_actuation_proof",
        proof_command=snmp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.tftp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/snmp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/syslog_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required snmp tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 1157 listener, speaks SET, "
            "GET/RESPONSE lockstep PDUs over UDP with a community string, GET "
            "the stored varbind, independently GET it on a later client "
            "socket, and binds this family as the next diversity-catalog "
            "successor once RFC 1350 TFTP lockstep is proved. Missing "
            "communities, skip-SET, skip-GET, skip-RESPONSE, skip-REPLAY, "
            "and SET aimed with an empty community stay fail-closed. Later "
            "genesis can take RFC 5424 syslog PRI/HEADER/MSG as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("snmp", "rfc1157", "udp", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T175638Z-527371ed",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_snmp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1157 SNMP lockstep actuation seals a varbind digest."""

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
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = SNMP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_snmp"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_snmp"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_snmp"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["syslog_goal_is_not_snmp"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["snmp_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["snmp_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["snmp_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = SNMP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = SNMP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_snmp"] = (
        len(catalog) > 47
        and catalog[47]["id"] == SNMP_ACTUATION_ID
        and catalog[46]["id"] == TFTP_ACTUATION_ID
        and catalog[47]["source"] == "genesis_bind_snmp"
    )
    checks["catalog_names_syslog"] = (
        len(catalog) > 48
        and catalog[48]["id"] == SYSLOG_ACTUATION_ID
        and catalog[48]["source"] == "genesis_bind_syslog"
    )
    family = capability_family(SNMP_ACTUATION_GOAL)
    checks["family_is_snmp"] = "snmp" in family
    checks["family_is_rfc1157"] = "rfc1157" in family
    checks["family_is_not_tftp"] = "tftp" not in family and "rfc1350" not in family
    checks["family_is_not_ftp"] = "ftpd" not in family and "pasv" not in family
    checks["family_is_not_dns"] = "tsig" not in family and "nameserver" not in family
    checks["family_is_not_syslog"] = "syslog" not in family and "nilvalue" not in family
    packed = encode_message(
        DEFAULT_COMMUNITY,
        encode_pdu(PDU_SET, 7, [(DEFAULT_OID, sentinel_value())]),
    )
    parsed = parse_packet(packed)
    checks["set_roundtrip"] = (
        parsed["pdu_type"] == PDU_SET
        and parsed["community"] == DEFAULT_COMMUNITY
        and parsed["request_id"] == 7
        and parsed["varbinds"][0]["oid"] == DEFAULT_OID
        and parsed["varbinds"][0]["value"] == sentinel_value()
    )
    get_packet = parse_packet(
        encode_message(DEFAULT_COMMUNITY, encode_pdu(PDU_GET, 8, [(DEFAULT_OID, None)]))
    )
    response_packet = parse_packet(
        encode_message(
            DEFAULT_COMMUNITY,
            encode_pdu(PDU_RESPONSE, 8, [(DEFAULT_OID, sentinel_value())]),
        )
    )
    checks["get_response_roundtrip"] = (
        get_packet["pdu_type"] == PDU_GET
        and get_packet["varbinds"][0]["value"] is None
        and response_packet["pdu_type"] == PDU_RESPONSE
        and response_packet["varbinds"][0]["value"] == sentinel_value()
    )
    neighbors = (
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
    )
    snmp_signature = semantic_signature(SNMP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(snmp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_snmp = ToolDescriptor(name="remote_snmp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_snmp)
    checks["naive_mcp_snmp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = snmp_tool_descriptor()
    default_snmp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SNMP_TOOL_PROVIDER),
    )
    checks["default_snmp_provider_is_unsupported"] = (
        default_snmp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SNMP_TOOL_PROVIDER}" in default_snmp.reasons
    )
    checks["opted_in_snmp_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_snmp],
        required_tool_names=("local_memory", "snmp"),
    )
    checks["naive_preflight_missing_snmp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["snmp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "snmp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SNMP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "snmp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="snmp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_snmp_workflow(with_community=False, output_dir=root / "missing")
        skip_bind = run_snmp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_set = run_snmp_workflow(do_set=False, output_dir=root / "skip-set")
        skip_response = run_snmp_workflow(response=False, output_dir=root / "skip-response")
        skip_get = run_snmp_workflow(do_get=False, output_dir=root / "skip-get")
        skip_replay = run_snmp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_community = run_snmp_workflow(use_community=False, output_dir=root / "skip-community")
        live = run_snmp_workflow(output_dir=root / "live")
        verify = verify_snmp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_snmp_trace(clone)
        checks["naive_without_community_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_community"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_set_stays_empty"] = (
            skip_set["ok"] is False
            and skip_set["error"] == "set_required"
            and skip_set["final_status"] == 409
            and skip_set["payload_exists"] is False
        )
        checks["skip_response_stays_empty"] = (
            skip_response["ok"] is False
            and skip_response["error"] == "response_required"
            and skip_response["final_status"] == 409
            and skip_response["payload_exists"] is False
        )
        checks["skip_get_stays_empty"] = (
            skip_get["ok"] is False
            and skip_get["error"] == "get_required"
            and skip_get["final_status"] == 409
            and skip_get["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_community_stays_empty"] = (
            skip_community["ok"] is False
            and skip_community["error"] == "community_required"
            and skip_community["final_status"] == 409
            and skip_community["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_request_id"] = (
            int(live.get("request_id") or 0) > 0 and int(live.get("port") or 0) > 0
        )
        checks["token_community_set_get_response_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_set["ok"] is False
            and skip_response["ok"] is False
            and skip_get["ok"] is False
            and skip_replay["ok"] is False
            and skip_community["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="snmp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SNMP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_snmp"] = (
        live_goal == SNMP_ACTUATION_GOAL
        and SNMP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_snmp"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_snmp_actuation_capability()
    return {
        "ok": ok,
        "action": "snmp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SNMP_ACTUATION_GOAL,
        "done_when": SNMP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
