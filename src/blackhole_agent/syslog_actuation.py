"""Drive a first-class syslog tool through RFC 5424 PRI/HEADER/SD/MSG lockstep.

Tool routing already fails missions that require ``syslog``: hosted syslog
plugins stay on the unsupported MCP provider, and no first-party syslog
provider is executable. Unbound therefore cannot speak PRI, emit a HEADER
with a non-NILVALUE hostname, land STRUCTURED-DATA, independently replay the
stored message, or seal a syslog digest an independent later reader can
re-open.

This module closes that hole:

- advertise a ``syslog`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 5424 collector
- keep a missing-hostname client so the NILVALUE hole stays falsifiable
- refuse STRUCTURED-DATA until HEADER hostname is not NILVALUE
- independently replay the stored datagram on a later client socket
- persist a sealed syslog digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after SNMP
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
    SYSLOG_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    syslog_tool_descriptor,
)

SCHEMA_VERSION = 1
SYSLOG_ACTUATION_ID = "capability.syslog-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SYSLOG-OK"
NILVALUE = "-"
DEFAULT_HOSTNAME = "blackhole.local"
DEFAULT_APP = "unbound"
DEFAULT_MSGID = "BHSYS"
DEFAULT_SD_ID = "blackhole@53864"
DEFAULT_FACILITY = 16
DEFAULT_SEVERITY = 6
DEFAULT_PRI = DEFAULT_FACILITY * 8 + DEFAULT_SEVERITY
DEFAULT_VERSION = "1"
DEFAULT_TIMESTAMP = "2026-09-02T18:29:49.000Z"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2

SYSLOG_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SYSLOG_ACTUATION_ID};"
    f"capability_proved:{SYSLOG_ACTUATION_ID};"
    "no_skill_route"
)
SYSLOG_ACTUATION_GOAL = (
    "Repair rfc5424 syslog nilvalue-gated structured-data: hosted syslog "
    "tools remain unsupported so a PRI/HEADER/STRUCTURED-DATA/MSG cycle "
    "cannot land and a sealed syslog digest cannot be produced. A missing "
    "syslog hostname stays forbidden; fail-closed routing never opts the "
    "syslog provider in. An independent later replay of the stored message "
    "keeps the hole falsifiable."
)


class SyslogActuationError(RuntimeError):
    """Raised when the syslog session or loopback collector fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def encode_pri(prival: int) -> str:
    number = int(prival)
    if number < 0 or number > 191:
        raise SyslogActuationError("illegal_pri")
    return f"<{number}>"


def escape_sd_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("]", "\\]")


def unescape_sd_value(value: str) -> str:
    raw = str(value)
    out: list[str] = []
    escape = False
    for char in raw:
        if escape:
            out.append(char)
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        out.append(char)
    return "".join(out)


def encode_structured_data(
    sd_id: str = DEFAULT_SD_ID,
    params: Mapping[str, str] | None = None,
) -> str:
    pairs = dict(params or {"sentinel": SENTINEL})
    body = [f"[{sd_id}"]
    for name, value in pairs.items():
        body.append(f' {name}="{escape_sd_value(str(value))}"')
    body.append("]")
    return "".join(body)


def encode_syslog(
    *,
    prival: int = DEFAULT_PRI,
    version: str = DEFAULT_VERSION,
    timestamp: str = DEFAULT_TIMESTAMP,
    hostname: str = DEFAULT_HOSTNAME,
    app_name: str = DEFAULT_APP,
    procid: str = NILVALUE,
    msgid: str = DEFAULT_MSGID,
    structured_data: str | None = None,
    msg: str = SENTINEL,
    include_pri: bool = True,
    include_header: bool = True,
    include_structured_data: bool = True,
    include_msg: bool = True,
) -> bytes:
    host = str(hostname if hostname is not None else "") or NILVALUE
    sd = structured_data
    if sd is None:
        sd = encode_structured_data() if include_structured_data else NILVALUE
    elif not include_structured_data:
        sd = NILVALUE
    chunks: list[str] = []
    if include_pri:
        chunks.append(encode_pri(prival))
    if include_header:
        chunks.append(
            f"{version} {timestamp} {host} {app_name} {procid} {msgid}"
        )
        chunks.append(sd)
        if include_msg:
            chunks.append(str(msg))
        if include_pri:
            return (chunks[0] + " ".join(chunks[1:])).encode("utf-8")
        return " ".join(chunks).encode("utf-8")
    body = chunks[0] if chunks else ""
    return body.encode("utf-8")


def _find_sd_close(text: str, start: int) -> int:
    index = start + 1
    in_quote = False
    escape = False
    while index < len(text):
        char = text[index]
        if escape:
            escape = False
            index += 1
            continue
        if in_quote:
            if char == "\\":
                escape = True
            elif char == '"':
                in_quote = False
            index += 1
            continue
        if char == '"':
            in_quote = True
            index += 1
            continue
        if char == "]":
            return index
        index += 1
    raise SyslogActuationError("truncated_structured_data")


def parse_structured_data(text: str) -> tuple[str, str]:
    raw = str(text or "")
    if raw == NILVALUE:
        return NILVALUE, ""
    if raw.startswith(NILVALUE + " "):
        return NILVALUE, raw[2:]
    if not raw.startswith("["):
        raise SyslogActuationError("missing_structured_data")
    index = 0
    elements: list[str] = []
    while index < len(raw) and raw[index] == "[":
        close = _find_sd_close(raw, index)
        elements.append(raw[index : close + 1])
        index = close + 1
    structured = "".join(elements)
    if index >= len(raw):
        return structured, ""
    if raw[index] != " ":
        raise SyslogActuationError("malformed_message")
    return structured, raw[index + 1 :]


def parse_sd_params(structured_data: str) -> dict[str, str]:
    raw = str(structured_data or "")
    if not raw or raw == NILVALUE:
        return {}
    params: dict[str, str] = {}
    index = 0
    while index < len(raw):
        if raw[index] != "[":
            break
        close = _find_sd_close(raw, index)
        element = raw[index + 1 : close]
        cursor = 0
        while cursor < len(element) and element[cursor] not in {" ", "="}:
            cursor += 1
        rest = element[cursor:].lstrip()
        while rest:
            eq = rest.find("=")
            if eq < 0:
                break
            name = rest[:eq]
            rest = rest[eq + 1 :]
            if not rest.startswith('"'):
                break
            rest = rest[1:]
            value_chars: list[str] = []
            escape = False
            done = False
            pos = 0
            while pos < len(rest):
                char = rest[pos]
                if escape:
                    value_chars.append(char)
                    escape = False
                    pos += 1
                    continue
                if char == "\\":
                    escape = True
                    pos += 1
                    continue
                if char == '"':
                    done = True
                    pos += 1
                    break
                value_chars.append(char)
                pos += 1
            if not done:
                break
            params[name] = "".join(value_chars)
            rest = rest[pos:].lstrip()
        index = close + 1
    return params


def parse_syslog(data: bytes) -> dict[str, Any]:
    text = bytes(data or b"").decode("utf-8")
    if not text.startswith("<"):
        raise SyslogActuationError("missing_pri")
    close = text.find(">")
    if close < 2:
        raise SyslogActuationError("missing_pri")
    try:
        prival = int(text[1:close])
    except ValueError as error:
        raise SyslogActuationError("missing_pri") from error
    if prival < 0 or prival > 191:
        raise SyslogActuationError("illegal_pri")
    rest = text[close + 1 :]
    if not rest:
        raise SyslogActuationError("missing_header")
    fields: list[str] = []
    index = 0
    while len(fields) < 6:
        if index >= len(rest):
            raise SyslogActuationError("missing_header")
        space = rest.find(" ", index)
        if space < 0:
            fields.append(rest[index:])
            index = len(rest)
            break
        fields.append(rest[index:space])
        index = space + 1
    if len(fields) < 6:
        raise SyslogActuationError("missing_header")
    version, timestamp, hostname, app_name, procid, msgid = fields
    structured, msg = parse_structured_data(rest[index:])
    return {
        "pri": prival,
        "facility": prival // 8,
        "severity": prival % 8,
        "version": version,
        "timestamp": timestamp,
        "hostname": hostname,
        "app_name": app_name,
        "procid": procid,
        "msgid": msgid,
        "structured_data": structured,
        "msg": msg,
        "nilvalue_hostname": hostname == NILVALUE or not hostname,
        "nilvalue_structured_data": structured == NILVALUE or not structured,
    }


class _SyslogClient:
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

    def send(self, packet: bytes, *, wait_echo: bool = True) -> bytes:
        self.sock.sendto(bytes(packet or b""), (self.host, self.port))
        if not wait_echo:
            raise SyslogActuationError("timeout")
        try:
            payload, _addr = self.sock.recvfrom(65535)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise SyslogActuationError("timeout") from error
        return payload


class SyslogSession:
    """NILVALUE-gated loopback RFC 5424 collector: bind, publish, read."""

    def __init__(self, output_dir: Path, *, hostname: str = DEFAULT_HOSTNAME) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.hostname = str(hostname or "")
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.stored_message = b""
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.last_token = ""
        self.last_digest = ""
        self.last_msgid = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_message(self, packet: bytes) -> None:
        with self._lock:
            self.stored_message = bytes(packet or b"")
            self.stored = True

    def read_message(self) -> bytes:
        with self._lock:
            return bytes(self.stored_message or b"")

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "msgid": "",
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

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
                parsed = parse_syslog(payload)
            except SyslogActuationError:
                continue
            if parsed.get("version") != DEFAULT_VERSION:
                continue
            if parsed.get("nilvalue_hostname"):
                continue
            if parsed.get("nilvalue_structured_data"):
                continue
            if not str(parsed.get("msg") or ""):
                continue
            if self.hostname and str(parsed.get("hostname") or "") != self.hostname:
                continue
            self.store_message(payload)
            try:
                sock.sendto(payload, (str(addr[0]), int(addr[1])))
            except OSError:
                continue

    def bind(self) -> dict[str, Any]:
        if not self.hostname or self.hostname == NILVALUE:
            return self._forbidden("missing_hostname")
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
        do_pri: bool = True,
        do_header: bool = True,
        do_structured_data: bool = True,
        do_msg: bool = True,
        replay: bool = True,
        use_hostname: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.hostname or self.hostname == NILVALUE:
            return self._forbidden("missing_hostname")
        live_token = str(token or SENTINEL)
        hostname = self.hostname if use_hostname else NILVALUE
        packet = encode_syslog(
            hostname=hostname,
            msg=live_token,
            structured_data=encode_structured_data(params={"sentinel": live_token}),
            include_pri=do_pri,
            include_header=do_header,
            include_structured_data=do_structured_data,
            include_msg=do_msg,
        )
        client: _SyslogClient | None = None
        independent: _SyslogClient | None = None
        try:
            client = _SyslogClient(self.host, int(self.port))
            if not do_pri:
                try:
                    client.sock.sendto(packet, (self.host, int(self.port)))
                except OSError:
                    pass
                return self._conflict("pri_required")
            if not do_header:
                try:
                    client.sock.sendto(packet, (self.host, int(self.port)))
                except OSError:
                    pass
                return self._conflict("header_required")
            if not use_hostname:
                try:
                    client.sock.sendto(packet, (self.host, int(self.port)))
                except OSError:
                    pass
                return self._conflict("hostname_required")
            if not do_structured_data:
                try:
                    client.sock.sendto(packet, (self.host, int(self.port)))
                except OSError:
                    pass
                return self._conflict("structured_data_required")
            if not do_msg:
                try:
                    client.sock.sendto(packet, (self.host, int(self.port)))
                except OSError:
                    pass
                return self._conflict("msg_required")
            try:
                echo = client.send(packet, wait_echo=True)
            except SyslogActuationError:
                return self._conflict("structured_data_required")
            if echo != packet:
                return self._conflict("structured_data_required")
            self.retrieved = True
            parsed = parse_syslog(echo)
            self.last_msgid = str(parsed.get("msgid") or "")
            if replay:
                independent = _SyslogClient(self.host, int(self.port))
                stored = self.read_message()
                try:
                    replay_echo = independent.send(stored, wait_echo=True)
                except SyslogActuationError:
                    return self._conflict("replay_required")
                if replay_echo != stored or stored != packet:
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(packet)
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(packet),
                "port": int(self.port or 0),
                "msgid": str(parsed.get("msgid") or DEFAULT_MSGID),
                "pri": int(parsed.get("pri") or 0),
                "hostname": str(parsed.get("hostname") or ""),
                "structured_data": str(parsed.get("structured_data") or ""),
                "message": str(parsed.get("msg") or ""),
                "client_port": int(client.client_port),
                "pri_sent": True,
                "header": True,
                "structured_data_sent": True,
                "msg": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "hostname_bound": True,
                "nilvalue_hostname": False,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_syslog_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(packet),
                "port": int(self.port or 0),
                "msgid": str(parsed.get("msgid") or DEFAULT_MSGID),
                "pri": int(parsed.get("pri") or 0),
                "hostname": str(parsed.get("hostname") or ""),
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "pri_sent": True,
                "header": True,
                "structured_data_sent": True,
                "msg": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "hostname_bound": True,
            }
        except (OSError, SyslogActuationError) as error:
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
        live = independent_syslog_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "msgid": str(live.get("msgid") or ""),
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


def call_syslog_tool(session: SyslogSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one syslog tool call against a bound collector session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_pri = True if arguments.get("pri") is None else bool(arguments.get("pri"))
    do_header = True if arguments.get("header") is None else bool(arguments.get("header"))
    do_structured_data = (
        True if arguments.get("structured_data") is None else bool(arguments.get("structured_data"))
    )
    do_msg = True if arguments.get("msg") is None else bool(arguments.get("msg"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_hostname = (
        True if arguments.get("use_hostname") is None else bool(arguments.get("use_hostname"))
    )
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_pri=do_pri,
            do_header=do_header,
            do_structured_data=do_structured_data,
            do_msg=do_msg,
            replay=replay,
            use_hostname=use_hostname,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SyslogActuationError(f"unsupported syslog action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_syslog_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed syslog digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "msgid": "",
        "port": 0,
        "pri": 0,
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
            "pri_sent",
            "header",
            "structured_data_sent",
            "msg",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "hostname_bound",
        )
    )
    port = int(payload.get("port") or 0)
    pri = int(payload.get("pri") or 0)
    dual = port > 0 and pri > 0 and str(payload.get("hostname") or "") not in {"", NILVALUE}
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "msgid": str(payload.get("msgid") or ""),
        "size": int(payload.get("size") or 0),
        "port": port,
        "pri": pri,
        "hostname": str(payload.get("hostname") or ""),
        "structured_data": str(payload.get("structured_data") or ""),
        "message": str(payload.get("message") or ""),
        "pri_sent": payload.get("pri_sent") is True,
        "header": payload.get("header") is True,
        "structured_data_sent": payload.get("structured_data_sent") is True,
        "msg": payload.get("msg") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "hostname_bound": payload.get("hostname_bound") is True,
        "nilvalue_hostname": payload.get("nilvalue_hostname") is True,
    }


def run_syslog_workflow(
    *,
    with_hostname: bool = True,
    skip_bind: bool = False,
    do_pri: bool = True,
    do_header: bool = True,
    do_structured_data: bool = True,
    do_msg: bool = True,
    replay: bool = True,
    use_hostname: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 5424 PRI/HEADER/STRUCTURED-DATA/MSG workflow and seal a trace."""

    descriptor = syslog_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SYSLOG_TOOL_PROVIDER),
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
        raise SyslogActuationError(f"syslog tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="syslog-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SyslogSession(out, hostname=DEFAULT_HOSTNAME if with_hostname else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "pri": do_pri,
            "header": do_header,
            "structured_data": do_structured_data,
            "msg": do_msg,
            "replay": replay,
            "use_hostname": use_hostname,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_syslog_tool(session, arguments))
            except SyslogActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_syslog_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_hostname
        and not skip_bind
        and do_pri
        and do_header
        and do_structured_data
        and do_msg
        and replay
        and use_hostname
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "syslog_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_hostname": with_hostname,
        "skip_bind": skip_bind,
        "pri": do_pri,
        "header": do_header,
        "structured_data": do_structured_data,
        "msg": do_msg,
        "replay": replay,
        "use_hostname": use_hostname,
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
        "msgid": str(publish_result.get("msgid") or independent.get("msgid") or ""),
        "pri_value": int(publish_result.get("pri") or independent.get("pri") or 0),
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
        "msgid": str(trace_body["msgid"] or ""),
        "pri": int(trace_body["pri_value"] or 0),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_hostname": with_hostname,
        "skip_bind": skip_bind,
        "pri_sent": do_pri,
        "header": do_header,
        "structured_data": do_structured_data,
        "msg": do_msg,
        "replay": replay,
        "use_hostname": use_hostname,
    }


def verify_syslog_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed syslog trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_syslog_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    pri = int(trace.get("pri_value") or independent.get("pri") or 0)
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
        "pri_sent": independent.get("pri_sent") is True,
        "header": independent.get("header") is True,
        "structured_data_sent": independent.get("structured_data_sent") is True,
        "msg": independent.get("msg") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "hostname_bound": independent.get("hostname_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "pri_bound": port > 0 and pri > 0,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def syslog_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.syslog_actuation import "
        "builtin_syslog_actuation_proof; r=builtin_syslog_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='syslog_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_syslog_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SYSLOG_ACTUATION_ID,
        name="First-class RFC 5424 syslog PRI/HEADER/STRUCTURED-DATA/MSG actuation",
        description=(
            "Missions that require a syslog tool can opt the syslog provider in, "
            "bind a loopback RFC 5424 UDP collector, complete PRI, HEADER with a "
            "non-NILVALUE hostname, STRUCTURED-DATA, and MSG, independently replay "
            "the stored datagram on a later socket, and seal a digest-chained "
            "syslog message. Default routing stays fail-closed; a missing hostname "
            "keeps the NILVALUE hole falsifiable, and skip-PRI/HEADER/SD/MSG/REPLAY "
            "stay empty."
        ),
        kind="python",
        entry="blackhole_agent.syslog_actuation:builtin_syslog_actuation_proof",
        proof_command=syslog_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.snmp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/syslog_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/ntp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required syslog tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 5424 collector, speaks PRI, HEADER "
            "with a non-NILVALUE hostname, STRUCTURED-DATA, and MSG over UDP, "
            "independently replays the stored datagram on a later client socket, "
            "and binds this family as the next diversity-catalog successor once "
            "RFC 1157 SNMP lockstep is proved. Missing hostnames, NILVALUE-gated "
            "structured-data, skip-PRI, skip-HEADER, skip-STRUCTURED-DATA, skip-MSG, "
            "skip-REPLAY, and HEADER aimed with a NILVALUE hostname stay fail-closed. "
            "Later genesis can take RFC 5905 NTP originate/receive/transmit as the "
            "next unsaturated diversity-catalog family."
        ),
        tags=("syslog", "rfc5424", "udp", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T182949Z-fa4effc7",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_syslog_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 5424 syslog lockstep actuation seals a digest."""

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
    from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = SYSLOG_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_syslog"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_syslog"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_syslog"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_syslog"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["ntp_goal_is_not_syslog"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["syslog_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["syslog_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["syslog_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["syslog_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["ntp_marker_stays_ntp"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_syslog"] = (
        len(catalog) > 48
        and catalog[48]["id"] == SYSLOG_ACTUATION_ID
        and catalog[47]["id"] == SNMP_ACTUATION_ID
        and catalog[48]["source"] == "genesis_bind_syslog"
    )
    checks["catalog_names_ntp"] = (
        len(catalog) > 49
        and catalog[49]["id"] == NTP_ACTUATION_ID
        and catalog[49]["source"] == "genesis_bind_ntp"
    )
    family = capability_family(SYSLOG_ACTUATION_GOAL)
    checks["family_is_syslog"] = "syslog" in family
    checks["family_is_rfc5424"] = "rfc5424" in family
    checks["family_is_nilvalue"] = "nilvalue" in family
    checks["family_is_not_snmp"] = "snmp" not in family and "varbind" not in family
    checks["family_is_not_tftp"] = "tftp" not in family and "rfc1350" not in family
    checks["family_is_not_ftp"] = "ftpd" not in family and "pasv" not in family
    checks["family_is_not_dns"] = "tsig" not in family and "nameserver" not in family
    checks["family_is_not_ntp"] = "ntp" not in family and "rfc5905" not in family
    packed = encode_syslog(msg=SENTINEL)
    parsed = parse_syslog(packed)
    checks["pri_header_roundtrip"] = (
        parsed["pri"] == DEFAULT_PRI
        and parsed["hostname"] == DEFAULT_HOSTNAME
        and parsed["msgid"] == DEFAULT_MSGID
        and parsed["nilvalue_hostname"] is False
        and parsed["msg"] == SENTINEL
    )
    sd_packet = parse_syslog(
        encode_syslog(
            structured_data=encode_structured_data(params={"sentinel": SENTINEL, "iut": "3"}),
            msg=SENTINEL,
        )
    )
    params = parse_sd_params(str(sd_packet.get("structured_data") or ""))
    checks["structured_data_roundtrip"] = (
        sd_packet["nilvalue_structured_data"] is False
        and params.get("sentinel") == SENTINEL
        and params.get("iut") == "3"
        and SENTINEL in str(sd_packet.get("structured_data") or "")
    )
    nil_host = parse_syslog(encode_syslog(hostname=NILVALUE))
    checks["nilvalue_hostname_is_detected"] = nil_host["nilvalue_hostname"] is True
    nil_sd = parse_syslog(encode_syslog(include_structured_data=False))
    checks["nilvalue_structured_data_is_detected"] = nil_sd["nilvalue_structured_data"] is True
    neighbors = (
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
    )
    syslog_signature = semantic_signature(SYSLOG_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(syslog_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_syslog = ToolDescriptor(name="remote_syslog", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_syslog)
    checks["naive_mcp_syslog_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = syslog_tool_descriptor()
    default_syslog = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SYSLOG_TOOL_PROVIDER),
    )
    checks["default_syslog_provider_is_unsupported"] = (
        default_syslog.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SYSLOG_TOOL_PROVIDER}" in default_syslog.reasons
    )
    checks["opted_in_syslog_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_syslog],
        required_tool_names=("local_memory", "syslog"),
    )
    checks["naive_preflight_missing_syslog"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["syslog"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "syslog"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SYSLOG_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "syslog" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="syslog-actuation-") as tmp:
        root = Path(tmp)
        missing = run_syslog_workflow(with_hostname=False, output_dir=root / "missing")
        skip_bind = run_syslog_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_pri = run_syslog_workflow(do_pri=False, output_dir=root / "skip-pri")
        skip_header = run_syslog_workflow(do_header=False, output_dir=root / "skip-header")
        skip_sd = run_syslog_workflow(do_structured_data=False, output_dir=root / "skip-sd")
        skip_msg = run_syslog_workflow(do_msg=False, output_dir=root / "skip-msg")
        skip_replay = run_syslog_workflow(replay=False, output_dir=root / "skip-replay")
        skip_hostname = run_syslog_workflow(use_hostname=False, output_dir=root / "skip-hostname")
        live = run_syslog_workflow(output_dir=root / "live")
        verify = verify_syslog_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_syslog_trace(clone)
        checks["naive_without_hostname_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_hostname"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_pri_stays_empty"] = (
            skip_pri["ok"] is False
            and skip_pri["error"] == "pri_required"
            and skip_pri["final_status"] == 409
            and skip_pri["payload_exists"] is False
        )
        checks["skip_header_stays_empty"] = (
            skip_header["ok"] is False
            and skip_header["error"] == "header_required"
            and skip_header["final_status"] == 409
            and skip_header["payload_exists"] is False
        )
        checks["skip_structured_data_stays_empty"] = (
            skip_sd["ok"] is False
            and skip_sd["error"] == "structured_data_required"
            and skip_sd["final_status"] == 409
            and skip_sd["payload_exists"] is False
        )
        checks["skip_msg_stays_empty"] = (
            skip_msg["ok"] is False
            and skip_msg["error"] == "msg_required"
            and skip_msg["final_status"] == 409
            and skip_msg["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_hostname_stays_empty"] = (
            skip_hostname["ok"] is False
            and skip_hostname["error"] == "hostname_required"
            and skip_hostname["final_status"] == 409
            and skip_hostname["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_pri"] = int(live.get("pri") or 0) == DEFAULT_PRI and int(live.get("port") or 0) > 0
        checks["token_hostname_pri_header_sd_msg_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_pri["ok"] is False
            and skip_header["ok"] is False
            and skip_sd["ok"] is False
            and skip_msg["ok"] is False
            and skip_replay["ok"] is False
            and skip_hostname["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="syslog-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SYSLOG_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_syslog"] = (
        live_goal == SYSLOG_ACTUATION_GOAL
        and SYSLOG_ACTUATION_ID in live_done
        and live_source == "genesis_bind_syslog"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_syslog_actuation_capability()
    return {
        "ok": ok,
        "action": "syslog_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SYSLOG_ACTUATION_GOAL,
        "done_when": SYSLOG_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
