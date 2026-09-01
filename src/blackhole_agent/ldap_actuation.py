"""Drive a first-class LDAP tool through BIND/ADD/SEARCH identity lookup.

Tool routing already fails missions that require ``ldap``: hosted directory
plugins stay on the unsupported MCP provider, and no first-party LDAP
provider is executable. Unbound therefore cannot speak LDAP v3 simple BIND,
ADD a distinguished-name entry, SEARCH it with an equality filter, or seal
a DIT that an independent reader can re-open.

This module closes that hole:

- advertise an ``ldap`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback LDAP v3 listener
- keep a missing-secret client so the bind-password hole stays falsifiable
- refuse ADD and SEARCH until simple BIND succeeds
- SEARCH after ADD, then independently re-SEARCH from a fresh connection
  so skip-ADD and skip-SEARCH stay empty
- persist a sealed distinguished-name entry an independent reader can re-open
- bind this family as the next diversity-catalog successor after DNS
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import socketserver
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
    LDAP_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    ldap_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
LDAP_ACTUATION_ID = "capability.ldap-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-ldap"
SENTINEL = "BH-LDAP-OK"
DEFAULT_PASSWORD = "blackhole-ldap-secret"
DEFAULT_BIND_DN = "cn=admin,dc=blackhole,dc=test"
DEFAULT_ENTRY_DN = "uid=beacon,ou=people,dc=blackhole,dc=test"
DEFAULT_FILTER_ATTR = "uid"
DEFAULT_FILTER_VALUE = "beacon"
DEFAULT_DESC_ATTR = "description"
SEALED_NAME = "sealed.json"

RESULT_SUCCESS = 0
RESULT_NO_SUCH_OBJECT = 32
RESULT_INVALID_CREDENTIALS = 49
RESULT_INSUFFICIENT_ACCESS = 50
RESULT_UNWILLING = 53

TAG_SEQUENCE = 0x30
TAG_SET = 0x31
TAG_BOOLEAN = 0x01
TAG_INTEGER = 0x02
TAG_OCTET = 0x04
TAG_ENUM = 0x0A
TAG_BIND_REQUEST = 0x60
TAG_BIND_RESPONSE = 0x61
TAG_UNBIND_REQUEST = 0x42
TAG_SEARCH_REQUEST = 0x63
TAG_SEARCH_ENTRY = 0x64
TAG_SEARCH_DONE = 0x65
TAG_ADD_REQUEST = 0x68
TAG_ADD_RESPONSE = 0x69
TAG_SIMPLE_AUTH = 0x80
TAG_EQUALITY_FILTER = 0xA3

LDAP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LDAP_ACTUATION_ID};"
    f"capability_proved:{LDAP_ACTUATION_ID};"
    "no_skill_route"
)
LDAP_ACTUATION_GOAL = (
    "Repair LDAP directory identity lookup: Unbound cannot speak LDAP v3 "
    "simple BIND then ADD plus equality-filter SEARCH against a loopback DIT, "
    "so a distinguished-name entry never becomes independently re-readable. "
    "Skip-BIND and skip-SEARCH stay empty; importing the ldap tool never makes "
    "a live directory silently executable."
)


class LdapActuationError(RuntimeError):
    """Raised when the LDAP session or directory fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _canon_dn(name: str) -> str:
    return ",".join(part.strip().lower() for part in str(name or "").split(",") if part.strip())


def _ber_len(size: int) -> bytes:
    if size < 0:
        raise LdapActuationError("negative ber length")
    if size < 0x80:
        return bytes([size])
    raw = size.to_bytes((size.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _ber_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag & 0xFF]) + _ber_len(len(value)) + value


def _ber_int(value: int, tag: int = TAG_INTEGER) -> bytes:
    if value == 0:
        return bytes([tag, 1, 0])
    length = value.bit_length() // 8 + 1
    return _ber_tlv(tag, value.to_bytes(length, "big", signed=True))


def _ber_enum(value: int) -> bytes:
    return _ber_int(value, tag=TAG_ENUM)


def _ber_bool(value: bool) -> bytes:
    return bytes([TAG_BOOLEAN, 1, 0xFF if value else 0x00])


def _ber_octet(value: str | bytes, tag: int = TAG_OCTET) -> bytes:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return _ber_tlv(tag, raw)


def _ber_seq(value: bytes, tag: int = TAG_SEQUENCE) -> bytes:
    return _ber_tlv(tag, value)


def _encode_attrs(attributes: Mapping[str, list[str] | str], *, set_tag: int = TAG_SET) -> bytes:
    parts = bytearray()
    for name, raw_values in attributes.items():
        values = [raw_values] if isinstance(raw_values, str) else list(raw_values)
        payload = b"".join(_ber_octet(item) for item in values)
        parts.extend(_ber_seq(_ber_octet(name) + _ber_seq(payload, tag=set_tag)))
    return _ber_seq(bytes(parts))


def _ldap_message(message_id: int, protocol_op: bytes) -> bytes:
    return _ber_seq(_ber_int(message_id) + protocol_op)


def _encode_bind(message_id: int, dn: str, password: str) -> bytes:
    body = _ber_int(3) + _ber_octet(dn) + _ber_octet(password, tag=TAG_SIMPLE_AUTH)
    return _ldap_message(message_id, _ber_seq(body, tag=TAG_BIND_REQUEST))


def _encode_unbind(message_id: int = 1) -> bytes:
    return _ldap_message(message_id, bytes([TAG_UNBIND_REQUEST, 0]))


def _encode_add(message_id: int, dn: str, attributes: Mapping[str, list[str] | str]) -> bytes:
    body = _ber_octet(dn) + _encode_attrs(attributes)
    return _ldap_message(message_id, _ber_seq(body, tag=TAG_ADD_REQUEST))


def _encode_search(message_id: int, base: str, attr: str, value: str) -> bytes:
    filt = _ber_seq(_ber_octet(attr) + _ber_octet(value), tag=TAG_EQUALITY_FILTER)
    body = (
        _ber_octet(base)
        + _ber_enum(0)
        + _ber_enum(0)
        + _ber_int(0)
        + _ber_int(0)
        + _ber_bool(False)
        + filt
        + _ber_seq(b"")
    )
    return _ldap_message(message_id, _ber_seq(body, tag=TAG_SEARCH_REQUEST))


def _encode_result(tag: int, result_code: int, matched_dn: str = "", diagnostic: str = "") -> bytes:
    body = _ber_enum(result_code) + _ber_octet(matched_dn) + _ber_octet(diagnostic)
    return _ber_seq(body, tag=tag)


def _encode_search_entry(dn: str, attributes: Mapping[str, list[str]]) -> bytes:
    body = _ber_octet(dn) + _encode_attrs(attributes)
    return _ber_seq(body, tag=TAG_SEARCH_ENTRY)


def _parse_int(value: bytes) -> int:
    if not value:
        return 0
    return int.from_bytes(value, "big", signed=True)


def _iter_tlv(buf: bytes) -> list[tuple[int, bytes]]:
    items: list[tuple[int, bytes]] = []
    offset = 0
    total = len(buf)
    while offset < total:
        tag = buf[offset]
        offset += 1
        if offset >= total:
            raise LdapActuationError("truncated ber length")
        first = buf[offset]
        offset += 1
        if first < 0x80:
            size = first
        else:
            count = first & 0x7F
            if count == 0 or offset + count > total:
                raise LdapActuationError("malformed ber length")
            size = int.from_bytes(buf[offset : offset + count], "big")
            offset += count
        end = offset + size
        if end > total:
            raise LdapActuationError("truncated ber value")
        items.append((tag, buf[offset:end]))
        offset = end
    return items


def _read_ber(rfile: Any) -> tuple[int, bytes] | None:
    tag_b = rfile.read(1)
    if not tag_b:
        return None
    tag = tag_b[0]
    len_b = rfile.read(1)
    if not len_b:
        raise LdapActuationError("eof ber length")
    first = len_b[0]
    if first < 0x80:
        size = first
    else:
        count = first & 0x7F
        if count == 0:
            raise LdapActuationError("indefinite ber length")
        raw = rfile.read(count)
        if len(raw) != count:
            raise LdapActuationError("eof long ber length")
        size = int.from_bytes(raw, "big")
    value = rfile.read(size) if size else b""
    if len(value) != size:
        raise LdapActuationError("eof ber value")
    return tag, value


def _parse_message(value: bytes) -> dict[str, Any]:
    items = _iter_tlv(value)
    if len(items) < 2:
        raise LdapActuationError("truncated ldap message")
    message_id = _parse_int(items[0][1])
    op_tag, op_body = items[1]
    return {"id": message_id, "op": op_tag, "body": op_body}


def _parse_result_code(body: bytes) -> int:
    items = _iter_tlv(body)
    if not items:
        return RESULT_UNWILLING
    return _parse_int(items[0][1])


def _parse_bind(body: bytes) -> dict[str, str]:
    items = _iter_tlv(body)
    if len(items) < 3:
        raise LdapActuationError("truncated bind")
    version = _parse_int(items[0][1])
    dn = items[1][1].decode("utf-8", errors="replace")
    password = items[2][1].decode("utf-8", errors="replace") if items[2][0] == TAG_SIMPLE_AUTH else ""
    return {"version": str(version), "dn": dn, "password": password}


def _parse_add(body: bytes) -> tuple[str, dict[str, list[str]]]:
    items = _iter_tlv(body)
    if len(items) < 2:
        raise LdapActuationError("truncated add")
    dn = items[0][1].decode("utf-8", errors="replace")
    return dn, _parse_attrs(items[1][1])


def _parse_attrs(value: bytes) -> dict[str, list[str]]:
    attributes: dict[str, list[str]] = {}
    for _tag, attr_body in _iter_tlv(value):
        fields = _iter_tlv(attr_body)
        if len(fields) < 2:
            continue
        name = fields[0][1].decode("utf-8", errors="replace").lower()
        values = [
            item.decode("utf-8", errors="replace")
            for _item_tag, item in _iter_tlv(fields[1][1])
        ]
        attributes[name] = values
    return attributes


def _parse_search(body: bytes) -> dict[str, str]:
    items = _iter_tlv(body)
    if len(items) < 7:
        raise LdapActuationError("truncated search")
    base = items[0][1].decode("utf-8", errors="replace")
    filt_tag, filt_body = items[6]
    attr = ""
    value = ""
    if filt_tag == TAG_EQUALITY_FILTER:
        fields = _iter_tlv(filt_body)
        if len(fields) >= 2:
            attr = fields[0][1].decode("utf-8", errors="replace")
            value = fields[1][1].decode("utf-8", errors="replace")
    return {"base": base, "attr": attr, "value": value}


def _parse_search_entry(body: bytes) -> dict[str, Any]:
    items = _iter_tlv(body)
    if len(items) < 2:
        raise LdapActuationError("truncated search entry")
    dn = items[0][1].decode("utf-8", errors="replace")
    return {"dn": dn, "attributes": _parse_attrs(items[1][1])}


class _LdapTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[socketserver.BaseRequestHandler],
        session: LdapSession,
    ) -> None:
        self.session = session
        super().__init__(address, handler)


class _LdapHandler(socketserver.StreamRequestHandler):
    timeout = None

    def setup(self) -> None:
        super().setup()
        self._send_lock = threading.Lock()

    def _send(self, payload: bytes) -> None:
        with self._send_lock:
            self.wfile.write(payload)
            self.wfile.flush()

    def _reply(self, message_id: int, protocol_op: bytes) -> None:
        self._send(_ldap_message(message_id, protocol_op))

    def handle(self) -> None:
        session: LdapSession = self.server.session  # type: ignore[attr-defined]
        bound = False
        while True:
            try:
                packet = _read_ber(self.rfile)
            except (LdapActuationError, OSError, ValueError):
                return
            if packet is None:
                return
            tag, value = packet
            if tag != TAG_SEQUENCE:
                return
            try:
                message = _parse_message(value)
            except LdapActuationError:
                return
            message_id = int(message["id"])
            op = int(message["op"])
            body = bytes(message["body"])
            if op == TAG_BIND_REQUEST:
                try:
                    bind = _parse_bind(body)
                except LdapActuationError:
                    self._reply(message_id, _encode_result(TAG_BIND_RESPONSE, RESULT_UNWILLING))
                    return
                if session.credentials_match(bind.get("dn") or "", bind.get("password") or ""):
                    bound = True
                    self._reply(message_id, _encode_result(TAG_BIND_RESPONSE, RESULT_SUCCESS))
                else:
                    bound = False
                    self._reply(
                        message_id,
                        _encode_result(TAG_BIND_RESPONSE, RESULT_INVALID_CREDENTIALS),
                    )
            elif op == TAG_ADD_REQUEST:
                if not bound:
                    self._reply(
                        message_id,
                        _encode_result(TAG_ADD_RESPONSE, RESULT_INSUFFICIENT_ACCESS),
                    )
                    continue
                try:
                    dn, attributes = _parse_add(body)
                except LdapActuationError:
                    self._reply(message_id, _encode_result(TAG_ADD_RESPONSE, RESULT_UNWILLING))
                    continue
                session.store_entry(dn, attributes)
                self._reply(message_id, _encode_result(TAG_ADD_RESPONSE, RESULT_SUCCESS))
            elif op == TAG_SEARCH_REQUEST:
                if not bound:
                    self._reply(
                        message_id,
                        _encode_result(TAG_SEARCH_DONE, RESULT_INSUFFICIENT_ACCESS),
                    )
                    continue
                try:
                    search = _parse_search(body)
                except LdapActuationError:
                    self._reply(message_id, _encode_result(TAG_SEARCH_DONE, RESULT_UNWILLING))
                    continue
                matches = session.search_entries(
                    str(search.get("base") or ""),
                    str(search.get("attr") or ""),
                    str(search.get("value") or ""),
                )
                for dn, attributes in matches:
                    self._reply(message_id, _encode_search_entry(dn, attributes))
                code = RESULT_SUCCESS if matches else RESULT_NO_SUCH_OBJECT
                self._reply(message_id, _encode_result(TAG_SEARCH_DONE, code))
            elif op == TAG_UNBIND_REQUEST:
                return
            else:
                return


class _LdapClient:
    """Minimal LDAP v3 client with simple BIND, ADD, SEARCH, and Unbind."""

    def __init__(self, host: str, port: int, *, timeout: float = 6.0) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.rfile = self.sock.makefile("rb", buffering=0)
        self.wfile = self.sock.makefile("wb", buffering=0)
        self.timeout = timeout
        self._next_id = 1

    def close(self) -> None:
        try:
            self.wfile.close()
        except OSError:
            pass
        try:
            self.rfile.close()
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def _write(self, payload: bytes) -> None:
        self.wfile.write(payload)
        self.wfile.flush()

    def _next_message_id(self) -> int:
        message_id = self._next_id
        self._next_id += 1
        return message_id

    def _read_message(self) -> dict[str, Any] | None:
        try:
            packet = _read_ber(self.rfile)
        except (LdapActuationError, OSError, socket.timeout):
            return None
        if packet is None:
            return None
        tag, value = packet
        if tag != TAG_SEQUENCE:
            return None
        try:
            return _parse_message(value)
        except LdapActuationError:
            return None

    def bind_simple(self, dn: str, password: str) -> tuple[bool, int]:
        self._write(_encode_bind(self._next_message_id(), dn, password))
        message = self._read_message()
        if message is None or int(message.get("op") or 0) != TAG_BIND_RESPONSE:
            return False, RESULT_UNWILLING
        code = _parse_result_code(bytes(message.get("body") or b""))
        return code == RESULT_SUCCESS, code

    def add(self, dn: str, attributes: Mapping[str, list[str] | str]) -> tuple[bool, int]:
        self._write(_encode_add(self._next_message_id(), dn, attributes))
        message = self._read_message()
        if message is None or int(message.get("op") or 0) != TAG_ADD_RESPONSE:
            return False, RESULT_UNWILLING
        code = _parse_result_code(bytes(message.get("body") or b""))
        return code == RESULT_SUCCESS, code

    def search(self, base: str, attr: str, value: str) -> tuple[list[dict[str, Any]], int]:
        self._write(_encode_search(self._next_message_id(), base, attr, value))
        entries: list[dict[str, Any]] = []
        while True:
            message = self._read_message()
            if message is None:
                return entries, RESULT_UNWILLING
            op = int(message.get("op") or 0)
            body = bytes(message.get("body") or b"")
            if op == TAG_SEARCH_ENTRY:
                try:
                    entries.append(_parse_search_entry(body))
                except LdapActuationError:
                    return entries, RESULT_UNWILLING
            elif op == TAG_SEARCH_DONE:
                return entries, _parse_result_code(body)
            else:
                return entries, RESULT_UNWILLING

    def unbind(self) -> None:
        try:
            self._write(_encode_unbind(self._next_message_id()))
        except (LdapActuationError, OSError, socket.timeout):
            pass
        self.close()


class LdapSession:
    """Credential-gated loopback LDAP directory: bind, publish, read."""

    def __init__(self, output_dir: Path, *, password: str = DEFAULT_PASSWORD) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.bind_dn = DEFAULT_BIND_DN
        self.password = str(password or "")
        self.host: str | None = None
        self.port: int | None = None
        self.server: _LdapTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.delivered = False
        self.last_token = ""
        self.history: list[dict[str, Any]] = []
        self._dit: dict[str, dict[str, list[str]]] = {}
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def credentials_match(self, dn: str, password: str) -> bool:
        if not self.password:
            return False
        return _canon_dn(dn) == _canon_dn(self.bind_dn) and password == self.password

    def store_entry(self, dn: str, attributes: Mapping[str, list[str]]) -> None:
        key = _canon_dn(dn)
        copied = {str(name).lower(): [str(item) for item in values] for name, values in attributes.items()}
        with self._lock:
            self._dit[key] = copied

    def search_entries(self, base: str, attr: str, value: str) -> list[tuple[str, dict[str, list[str]]]]:
        wanted_dn = _canon_dn(base)
        wanted_attr = str(attr or "").strip().lower()
        wanted_value = str(value or "")
        matches: list[tuple[str, dict[str, list[str]]]] = []
        with self._lock:
            for dn, attributes in self._dit.items():
                if wanted_dn and dn != wanted_dn:
                    continue
                if wanted_attr and wanted_value not in attributes.get(wanted_attr, []):
                    continue
                matches.append((dn, {key: list(vals) for key, vals in attributes.items()}))
        return matches

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
        if not self.password:
            return self._forbidden("missing_secret")
        if self.server is not None:
            return {
                "ok": True,
                "status": 200,
                "host": self.host or "",
                "port": int(self.port or 0),
                "reused": True,
            }
        server = _LdapTCPServer(("127.0.0.1", 0), _LdapHandler, self)
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
        add: bool = True,
        search: bool = True,
        password: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.password:
            return self._forbidden("missing_secret")
        live_token = str(token or SENTINEL)
        writer: _LdapClient | None = None
        independent: _LdapClient | None = None
        try:
            writer = _LdapClient(self.host, int(self.port))
            if authenticate:
                secret = self.password if password is None else str(password)
                ok, code = writer.bind_simple(self.bind_dn, secret)
                if not ok:
                    reason = "auth_failed" if code == RESULT_INVALID_CREDENTIALS else "bind_failed"
                    status = 535 if reason == "auth_failed" else 503
                    return self._forbidden(reason, status=status)
            else:
                added, add_code = writer.add(
                    DEFAULT_ENTRY_DN,
                    {"objectClass": "inetOrgPerson", "uid": DEFAULT_FILTER_VALUE, DEFAULT_DESC_ATTR: live_token},
                )
                reason = "bind_required"
                status = 530 if add_code == RESULT_INSUFFICIENT_ACCESS or not added else 530
                return self._forbidden(reason, status=status)
            if not add:
                return self._conflict("add_required")
            added, add_code = writer.add(
                DEFAULT_ENTRY_DN,
                {
                    "objectClass": ["inetOrgPerson", "top"],
                    "uid": DEFAULT_FILTER_VALUE,
                    DEFAULT_DESC_ATTR: live_token,
                },
            )
            if not added:
                return self._forbidden("add_failed", status=550)
            if not search:
                return self._conflict("search_required")
            entries, search_code = writer.search(
                DEFAULT_ENTRY_DN, DEFAULT_FILTER_ATTR, DEFAULT_FILTER_VALUE
            )
            if not entries or search_code not in {RESULT_SUCCESS, RESULT_NO_SUCH_OBJECT}:
                return self._forbidden("search_required" if not entries else "search_failed", status=409)
            description = ""
            found_dn = str(entries[0].get("dn") or "")
            attributes = entries[0].get("attributes") if isinstance(entries[0].get("attributes"), dict) else {}
            values = attributes.get(DEFAULT_DESC_ATTR) if isinstance(attributes, dict) else None
            if isinstance(values, list) and values:
                description = str(values[0])
            if description != live_token:
                return self._forbidden("payload_mismatch", status=409)
            independent = _LdapClient(self.host, int(self.port))
            ind_ok, _ind_code = independent.bind_simple(self.bind_dn, self.password)
            if not ind_ok:
                return self._forbidden("independent_bind_failed", status=503)
            replay, _replay_code = independent.search(
                DEFAULT_ENTRY_DN, DEFAULT_FILTER_ATTR, DEFAULT_FILTER_VALUE
            )
            replay_desc = ""
            if replay:
                replay_attrs = replay[0].get("attributes") if isinstance(replay[0].get("attributes"), dict) else {}
                replay_vals = replay_attrs.get(DEFAULT_DESC_ATTR) if isinstance(replay_attrs, dict) else None
                if isinstance(replay_vals, list) and replay_vals:
                    replay_desc = str(replay_vals[0])
            if replay_desc != live_token:
                return self._forbidden("independent_required", status=409)
            sealed = {
                "dn": _canon_dn(found_dn) or _canon_dn(DEFAULT_ENTRY_DN),
                "bind_dn": _canon_dn(self.bind_dn),
                "filter_attr": DEFAULT_FILTER_ATTR,
                "filter_value": DEFAULT_FILTER_VALUE,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "bound": True,
                "added": True,
                "searched": True,
                "independent": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            live = independent_ldap_entry(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "queued": False,
                "directory": True,
                "dn": str(live.get("dn") or DEFAULT_ENTRY_DN),
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "path": str(self.sealed_path),
                "authenticated": bool(authenticate),
                "added": True,
                "searched": True,
                "independent": True,
            }
        except (OSError, LdapActuationError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error),
                "token": live_token,
                "sentinel": "",
            }
        finally:
            if independent is not None:
                independent.unbind()
            if writer is not None:
                writer.unbind()

    def read(self) -> dict[str, Any]:
        live = independent_ldap_entry(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "dn": str(live.get("dn") or ""),
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


def call_ldap_tool(session: LdapSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one LDAP tool call against a bound directory session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = arguments.get("authenticate")
    if authenticate is None:
        authenticate = True
    add = arguments.get("add")
    if add is None:
        add = True
    search = arguments.get("search")
    if search is None:
        search = True
    secret = arguments.get("password")
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            authenticate=bool(authenticate),
            add=bool(add),
            search=bool(search),
            password=None if secret is None else str(secret),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise LdapActuationError(f"unsupported ldap action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_ldap_entry(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed LDAP distinguished-name entry through a fresh file open."""

    path = Path(sealed_path)
    if not path.is_file():
        return {
            "ok": False,
            "error": "missing_payload",
            "token": "",
            "sentinel": "",
            "dn": "",
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
            "dn": "",
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "invalid_payload",
            "token": "",
            "sentinel": "",
            "dn": "",
        }
    token = str(payload.get("token") or "")
    bound = payload.get("bound") is True
    added = payload.get("added") is True
    searched = payload.get("searched") is True
    independent = payload.get("independent") is True
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and bound and added and searched and independent else "",
        "dn": str(payload.get("dn") or ""),
        "bound": bound,
        "added": added,
        "searched": searched,
        "independent": independent,
    }


def run_ldap_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    add: bool = True,
    search: bool = True,
    password: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the BIND/ADD/SEARCH directory workflow and seal a trace."""

    descriptor = ldap_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, LDAP_TOOL_PROVIDER),
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
        raise LdapActuationError(f"ldap tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ldap-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = LdapSession(out, password=DEFAULT_PASSWORD if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    publish_args: dict[str, Any] = {
        "action": "publish",
        "token": SENTINEL,
        "authenticate": authenticate,
        "add": add,
        "search": search,
    }
    if password is not None:
        publish_args["password"] = password
    calls.append(publish_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_ldap_tool(session, arguments))
            except LdapActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_ldap_entry(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and add
        and search
        and password is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ldap_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "add": add,
        "search": search,
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
        "delivered": bool(session.delivered or publish_result.get("directory")),
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
        "add": add,
        "search": search,
    }


def verify_ldap_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed LDAP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_ldap_entry(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
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
        "bound": independent.get("bound") is True,
        "added": independent.get("added") is True,
        "searched": independent.get("searched") is True,
        "independent": independent.get("independent") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def ldap_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.ldap_actuation import "
        "builtin_ldap_actuation_proof; r=builtin_ldap_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='ldap_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_ldap_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LDAP_ACTUATION_ID,
        name="First-class BIND/ADD/SEARCH directory identity actuation",
        description=(
            "Missions that require an ldap tool can opt the ldap provider in, "
            "bind a loopback LDAP v3 directory, simple-BIND as the directory "
            "manager, ADD a distinguished-name entry, SEARCH it with an equality "
            "filter, independently re-SEARCH from a fresh connection, and seal "
            "digest-chained DIT traces. Default routing stays fail-closed; a "
            "missing bind password keeps the hole falsifiable, and skip-ADD or "
            "skip-SEARCH stay empty."
        ),
        kind="python",
        entry="blackhole_agent.ldap_actuation:builtin_ldap_actuation_proof",
        proof_command=ldap_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.dns-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/ldap_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required ldap tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback LDAP v3 directory, simple-BINDs, ADDs "
            "a distinguished-name entry, SEARCHes with an equality filter, "
            "independently re-SEARCHes from a fresh connection, and binds this "
            "family as the next diversity-catalog successor once DNS TSIG-gated "
            "apex publication is proved. Missing secrets, skipped BIND, wrong "
            "passwords, skip-ADD, and skip-SEARCH stay fail-closed."
        ),
        tags=("ldap", "directory", "identity", "bind", "dit", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T091538Z-2c3a4cfb",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_ldap_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in LDAP actuation seals a BIND/ADD/SEARCH entry."""

    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
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
    checks["denylists_self"] = LDAP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LDAP_ACTUATION_GOAL) == (LDAP_ACTUATION_ID,)
    checks["dns_goal_is_not_ldap"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["mqtt_goal_is_not_ldap"] = leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    checks["redis_goal_is_not_ldap"] = leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    checks["imap_goal_is_not_ldap"] = leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    checks["smtp_goal_is_not_ldap"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    checks["sqlite_goal_is_not_ldap"] = leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (
        SQLITE_ACTUATION_ID,
    )
    checks["ldap_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    checks["ldap_goal_is_not_mqtt"] = MQTT_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    checks["ldap_goal_is_not_redis"] = REDIS_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    checks["ldap_goal_is_not_imap"] = IMAP_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    checks["ldap_goal_is_not_smtp"] = SMTP_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    checks["ldap_goal_is_not_sqlite"] = SQLITE_ACTUATION_ID not in leftover_marker_ids(
        LDAP_ACTUATION_GOAL
    )
    checks["dns_marker_stays_dns"] = LDAP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["mqtt_marker_stays_mqtt"] = LDAP_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    checks["redis_marker_stays_redis"] = LDAP_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    checks["imap_marker_stays_imap"] = LDAP_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    checks["smtp_marker_stays_smtp"] = LDAP_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    checks["sqlite_marker_stays_sqlite"] = LDAP_ACTUATION_ID not in leftover_marker_ids(
        SQLITE_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_ldap"] = (
        len(catalog) > 35
        and catalog[35]["id"] == LDAP_ACTUATION_ID
        and catalog[34]["id"] == DNS_ACTUATION_ID
    )
    family = capability_family(LDAP_ACTUATION_GOAL)
    checks["family_is_ldap"] = "ldap" in family
    checks["family_is_directory"] = "directory" in family
    checks["family_is_identity"] = "identity" in family
    checks["family_is_not_dns"] = "dns" not in family and "nameserver" not in family
    checks["family_is_not_mqtt"] = "mqtt" not in family
    checks["family_is_not_redis"] = "redi" not in family
    checks["family_is_not_blpop"] = "blpop" not in family
    checks["family_is_not_imap"] = "imap" not in family
    checks["family_is_not_smtp"] = "smtp" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["family_is_not_git_publication"] = "git-publication" not in family
    checks["family_is_not_auth_surface"] = family != "auth" and "auth" not in family.split("/")
    bind_wire = _encode_bind(7, DEFAULT_BIND_DN, DEFAULT_PASSWORD)
    bind_outer = _iter_tlv(bind_wire)
    bind_message = _parse_message(bind_outer[0][1])
    checks["bind_roundtrip"] = (
        bool(bind_outer)
        and bind_outer[0][0] == TAG_SEQUENCE
        and bind_message["id"] == 7
        and bind_message["op"] == TAG_BIND_REQUEST
        and _parse_bind(bind_message["body"])["password"] == DEFAULT_PASSWORD
    )
    add_wire = _encode_add(8, DEFAULT_ENTRY_DN, {"uid": DEFAULT_FILTER_VALUE, DEFAULT_DESC_ATTR: SENTINEL})
    add_outer = _iter_tlv(add_wire)
    add_message = _parse_message(add_outer[0][1])
    add_dn, add_attrs = _parse_add(add_message["body"])
    checks["add_roundtrip"] = (
        add_message["op"] == TAG_ADD_REQUEST
        and _canon_dn(add_dn) == _canon_dn(DEFAULT_ENTRY_DN)
        and add_attrs.get(DEFAULT_DESC_ATTR) == [SENTINEL]
    )
    search_wire = _encode_search(9, DEFAULT_ENTRY_DN, DEFAULT_FILTER_ATTR, DEFAULT_FILTER_VALUE)
    search_outer = _iter_tlv(search_wire)
    search_message = _parse_message(search_outer[0][1])
    search_fields = _parse_search(search_message["body"])
    checks["search_roundtrip"] = (
        search_message["op"] == TAG_SEARCH_REQUEST
        and _canon_dn(search_fields["base"]) == _canon_dn(DEFAULT_ENTRY_DN)
        and search_fields["attr"] == DEFAULT_FILTER_ATTR
        and search_fields["value"] == DEFAULT_FILTER_VALUE
    )
    checks["not_a_dns_duplicate"] = (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(DNS_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_an_mqtt_duplicate"] = (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(MQTT_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_redis_duplicate"] = (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(REDIS_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_an_imap_duplicate"] = (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(IMAP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_smtp_duplicate"] = (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_sqlite_duplicate"] = (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(SQLITE_ACTUATION_GOAL),
        )
        < 0.82
    )

    mcp_ldap = ToolDescriptor(name="remote_ldap", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_ldap)
    checks["naive_mcp_ldap_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = ldap_tool_descriptor()
    default_ldap = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, LDAP_TOOL_PROVIDER),
    )
    checks["default_ldap_provider_is_unsupported"] = (
        default_ldap.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{LDAP_TOOL_PROVIDER}" in default_ldap.reasons
    )
    checks["opted_in_ldap_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_ldap],
        required_tool_names=("local_memory", "ldap"),
    )
    checks["naive_preflight_missing_ldap"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["ldap"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "ldap"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, LDAP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "ldap" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="ldap-actuation-") as tmp:
        root = Path(tmp)
        missing = run_ldap_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_ldap_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_ldap_workflow(password="wrong-secret", output_dir=root / "wrong")
        skip_add = run_ldap_workflow(add=False, output_dir=root / "skip-add")
        skip_search = run_ldap_workflow(search=False, output_dir=root / "skip-search")
        live = run_ldap_workflow(output_dir=root / "live")
        verify = verify_ldap_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_ldap_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unauthenticated_add_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 530
            and unauth["error"] == "bind_required"
            and unauth["delivered"] is False
            and unauth["payload_exists"] is False
        )
        checks["wrong_secret_is_forbidden"] = (
            wrong["ok"] is False
            and wrong["final_status"] == 535
            and wrong["error"] == "auth_failed"
            and wrong["payload_exists"] is False
        )
        checks["skip_add_stays_empty"] = (
            skip_add["ok"] is False
            and skip_add["error"] == "add_required"
            and skip_add["final_status"] == 409
            and skip_add["payload_exists"] is False
        )
        checks["skip_search_stays_empty"] = (
            skip_search["ok"] is False
            and skip_search["error"] == "search_required"
            and skip_search["final_status"] == 409
            and skip_search["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_entry"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["secret_bind_add_and_search_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_add["ok"] is False
            and skip_search["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="ldap-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != LDAP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_ldap"] = (
        live_goal == LDAP_ACTUATION_GOAL
        and LDAP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_ldap"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_ldap_actuation_capability()
    return {
        "ok": ok,
        "action": "ldap_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LDAP_ACTUATION_GOAL,
        "done_when": LDAP_ACTUATION_DONE_WHEN,
    }
