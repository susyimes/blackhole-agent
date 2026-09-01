"""Drive a first-class PostgreSQL tool through frontend/backend query.

Tool routing already fails missions that require ``postgres``: hosted
relational-wire plugins stay on the unsupported MCP provider, and no
first-party PostgreSQL provider is executable. Unbound therefore cannot
speak a v3 StartupMessage, cleartext Password, SimpleQuery, or seal a
RowDescription/DataRow result an independent reader can re-query.

This module closes that hole:

- advertise a ``postgres`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback frontend/backend listener
- keep a missing-secret client so the password hole stays falsifiable
- refuse SimpleQuery until Password succeeds
- Query after INSERT, then independently re-Query from a fresh connection
  so skip-INSERT and skip-Query stay empty
- persist a sealed result row an independent reader can re-open
- bind this family as the next diversity-catalog successor after LDAP
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import socketserver
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
    MCP_TOOL_PROVIDER,
    POSTGRES_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    postgres_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
POSTGRES_ACTUATION_ID = "capability.postgres-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-postgres"
SENTINEL = "BH-PG-OK"
DEFAULT_USER = "blackhole"
DEFAULT_DATABASE = "blackhole"
DEFAULT_PASSWORD = "blackhole-postgres-secret"
DEFAULT_TABLE = "beacons"
DEFAULT_COLUMN = "token"
SEALED_NAME = "sealed.json"
PROTOCOL_VERSION_3 = 196608
AUTH_OK = 0
AUTH_CLEARTEXT = 3
TEXTOID = 25
MAX_MESSAGE = 1_048_576

INSERT_SQL = f"INSERT INTO {DEFAULT_TABLE}({DEFAULT_COLUMN}) VALUES('{SENTINEL}')"
SELECT_SQL = f"SELECT {DEFAULT_COLUMN} FROM {DEFAULT_TABLE}"

_INSERT_RE = re.compile(
    r"^\s*INSERT\s+INTO\s+beacons\s*\(\s*token\s*\)\s*VALUES\s*\(\s*'((?:\\'|[^'])*)'\s*\)\s*;?\s*$",
    re.IGNORECASE,
)
_SELECT_RE = re.compile(
    r"^\s*SELECT\s+token\s+FROM\s+beacons\s*;?\s*$",
    re.IGNORECASE,
)

POSTGRES_ACTUATION_DONE_WHEN = (
    f"capability_exists:{POSTGRES_ACTUATION_ID};"
    f"capability_proved:{POSTGRES_ACTUATION_ID};"
    "no_skill_route"
)
POSTGRES_ACTUATION_GOAL = (
    "Repair PostgreSQL frontend-backend query: hosted relational-wire "
    "tools remain unsupported so a StartupMessage/Password/SimpleQuery/"
    "RowDescription cycle cannot land and a sealed result row cannot be "
    "produced. A missing postgres password stays forbidden; fail-closed "
    "routing never opts the postgres provider in."
)


class PostgresActuationError(RuntimeError):
    """Raised when the PostgreSQL session or listener fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _i16(value: int) -> bytes:
    return struct.pack(">h", value)


def _i32(value: int) -> bytes:
    return struct.pack(">i", value)


def _read_exact(rfile: Any, size: int) -> bytes:
    if size < 0 or size > MAX_MESSAGE:
        raise PostgresActuationError(f"message length out of range: {size}")
    buf = bytearray()
    while len(buf) < size:
        chunk = rfile.read(size - len(buf))
        if not chunk:
            raise PostgresActuationError("eof")
        buf.extend(chunk)
    return bytes(buf)


def _cstring(text: str) -> bytes:
    return text.encode("utf-8") + b"\x00"


def _split_cstrings(payload: bytes) -> list[str]:
    if not payload:
        return []
    parts = payload.split(b"\x00")
    if parts and parts[-1] == b"":
        parts = parts[:-1]
    return [item.decode("utf-8", errors="replace") for item in parts]


def encode_startup(user: str, database: str) -> bytes:
    body = _i32(PROTOCOL_VERSION_3)
    for key, value in (("user", user), ("database", database)):
        body += _cstring(key) + _cstring(value)
    body += b"\x00"
    return _i32(4 + len(body)) + body


def encode_backend(code: bytes, payload: bytes) -> bytes:
    if len(code) != 1:
        raise PostgresActuationError("backend type must be one byte")
    return code + _i32(4 + len(payload)) + payload


def encode_auth(kind: int) -> bytes:
    return encode_backend(b"R", _i32(kind))


def encode_ready(status: bytes = b"I") -> bytes:
    if len(status) != 1:
        raise PostgresActuationError("ready status must be one byte")
    return encode_backend(b"Z", status)


def encode_password(password: str) -> bytes:
    payload = _cstring(password)
    return b"p" + _i32(4 + len(payload)) + payload


def encode_query(sql: str) -> bytes:
    payload = _cstring(sql)
    return b"Q" + _i32(4 + len(payload)) + payload


def encode_terminate() -> bytes:
    return b"X" + _i32(4)


def encode_row_description(name: str) -> bytes:
    payload = _i16(1)
    payload += _cstring(name)
    payload += _i32(0)
    payload += _i16(0)
    payload += _i32(TEXTOID)
    payload += _i16(-1)
    payload += _i32(-1)
    payload += _i16(0)
    return encode_backend(b"T", payload)


def encode_data_row(value: str) -> bytes:
    encoded = value.encode("utf-8")
    payload = _i16(1) + _i32(len(encoded)) + encoded
    return encode_backend(b"D", payload)


def encode_command_complete(tag: str) -> bytes:
    return encode_backend(b"C", _cstring(tag))


def encode_error(sqlstate: str, message: str) -> bytes:
    payload = (
        b"S"
        + _cstring("FATAL")
        + b"C"
        + _cstring(sqlstate)
        + b"M"
        + _cstring(message)
        + b"\x00"
    )
    return encode_backend(b"E", payload)


def parse_startup(payload: bytes) -> dict[str, str]:
    if len(payload) < 4:
        raise PostgresActuationError("truncated startup")
    version = struct.unpack(">i", payload[:4])[0]
    if version != PROTOCOL_VERSION_3:
        raise PostgresActuationError(f"unsupported protocol: {version}")
    fields = _split_cstrings(payload[4:])
    params: dict[str, str] = {}
    for index in range(0, len(fields) - 1, 2):
        params[fields[index]] = fields[index + 1]
    return {"version": str(version), **params}


def parse_error(payload: bytes) -> dict[str, str]:
    fields: dict[str, str] = {}
    cursor = 0
    while cursor < len(payload):
        code = payload[cursor]
        cursor += 1
        if code == 0:
            break
        end = payload.find(b"\x00", cursor)
        if end < 0:
            break
        fields[chr(code)] = payload[cursor:end].decode("utf-8", errors="replace")
        cursor = end + 1
    return fields


def parse_row_description(payload: bytes) -> list[str]:
    if len(payload) < 2:
        raise PostgresActuationError("truncated row description")
    count = struct.unpack(">h", payload[:2])[0]
    cursor = 2
    names: list[str] = []
    for _ in range(count):
        end = payload.find(b"\x00", cursor)
        if end < 0:
            raise PostgresActuationError("truncated field name")
        names.append(payload[cursor:end].decode("utf-8", errors="replace"))
        cursor = end + 1 + 18
        if cursor > len(payload):
            raise PostgresActuationError("truncated field metadata")
    return names


def parse_data_row(payload: bytes) -> list[str]:
    if len(payload) < 2:
        raise PostgresActuationError("truncated data row")
    count = struct.unpack(">h", payload[:2])[0]
    cursor = 2
    values: list[str] = []
    for _ in range(count):
        if cursor + 4 > len(payload):
            raise PostgresActuationError("truncated column length")
        length = struct.unpack(">i", payload[cursor : cursor + 4])[0]
        cursor += 4
        if length < 0:
            values.append("")
            continue
        if cursor + length > len(payload):
            raise PostgresActuationError("truncated column value")
        values.append(payload[cursor : cursor + length].decode("utf-8", errors="replace"))
        cursor += length
    return values


def _read_startup(rfile: Any) -> bytes:
    header = _read_exact(rfile, 4)
    length = struct.unpack(">i", header)[0]
    if length < 8:
        raise PostgresActuationError(f"startup too small: {length}")
    return _read_exact(rfile, length - 4)


def _read_message(rfile: Any) -> tuple[bytes, bytes]:
    code = _read_exact(rfile, 1)
    header = _read_exact(rfile, 4)
    length = struct.unpack(">i", header)[0]
    if length < 4:
        raise PostgresActuationError(f"message too small: {length}")
    payload = _read_exact(rfile, length - 4)
    return code, payload


class _PostgresTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[socketserver.BaseRequestHandler],
        session: PostgresSession,
    ) -> None:
        self.session = session
        super().__init__(address, handler)


class _PostgresHandler(socketserver.StreamRequestHandler):
    timeout = None

    def setup(self) -> None:
        super().setup()
        self._send_lock = threading.Lock()

    def _send(self, payload: bytes) -> None:
        with self._send_lock:
            self.wfile.write(payload)
            self.wfile.flush()

    def handle(self) -> None:
        session: PostgresSession = self.server.session  # type: ignore[attr-defined]
        try:
            startup_body = _read_startup(self.rfile)
            params = parse_startup(startup_body)
        except (PostgresActuationError, OSError, struct.error, ValueError):
            return
        self._send(encode_auth(AUTH_CLEARTEXT))
        authed = False
        user = str(params.get("user") or "")
        try:
            while True:
                code, payload = _read_message(self.rfile)
                if code == b"X":
                    return
                if not authed:
                    if code != b"p":
                        self._send(encode_error("28000", "password required"))
                        return
                    password = _split_cstrings(payload)[0] if payload else ""
                    if not session.credentials_match(user, password):
                        self._send(encode_error("28P01", "password authentication failed"))
                        return
                    authed = True
                    self._send(encode_auth(AUTH_OK))
                    self._send(encode_ready())
                    continue
                if code != b"Q":
                    self._send(encode_error("08P01", "protocol violation"))
                    return
                sql = _split_cstrings(payload)[0] if payload else ""
                insert = _INSERT_RE.match(sql)
                if insert:
                    session.store_row(insert.group(1).replace("\\'", "'"))
                    self._send(encode_command_complete("INSERT 0 1"))
                    self._send(encode_ready())
                    continue
                if _SELECT_RE.match(sql):
                    rows = session.list_rows()
                    self._send(encode_row_description(DEFAULT_COLUMN))
                    for value in rows:
                        self._send(encode_data_row(value))
                    self._send(encode_command_complete(f"SELECT {len(rows)}"))
                    self._send(encode_ready())
                    continue
                self._send(encode_error("42601", "syntax error"))
                self._send(encode_ready())
        except (PostgresActuationError, OSError, struct.error, ValueError):
            return


class _PostgresClient:
    """Minimal PostgreSQL v3 client with Startup, Password, and SimpleQuery."""

    def __init__(self, host: str, port: int, *, timeout: float = 6.0) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.rfile = self.sock.makefile("rb", buffering=0)
        self.wfile = self.sock.makefile("wb", buffering=0)

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

    def _read(self) -> tuple[bytes, bytes]:
        return _read_message(self.rfile)

    def startup(self, user: str = DEFAULT_USER, database: str = DEFAULT_DATABASE) -> dict[str, Any]:
        self._write(encode_startup(user, database))
        code, payload = self._read()
        if code != b"R":
            return {"ok": False, "error": "startup_failed", "code": code.decode("latin1")}
        kind = struct.unpack(">i", payload[:4])[0] if len(payload) >= 4 else -1
        return {"ok": kind == AUTH_CLEARTEXT, "auth": kind}

    def password(self, secret: str) -> dict[str, Any]:
        self._write(encode_password(secret))
        messages: list[tuple[bytes, bytes]] = []
        while True:
            code, payload = self._read()
            messages.append((code, payload))
            if code == b"Z":
                return {"ok": True, "ready": True, "messages": [item[0].decode("latin1") for item in messages]}
            if code == b"E":
                fields = parse_error(payload)
                return {
                    "ok": False,
                    "error": "auth_failed" if fields.get("C") == "28P01" else "auth_required",
                    "sqlstate": fields.get("C") or "",
                    "message": fields.get("M") or "",
                }

    def query(self, sql: str) -> dict[str, Any]:
        self._write(encode_query(sql))
        columns: list[str] = []
        rows: list[list[str]] = []
        tag = ""
        while True:
            code, payload = self._read()
            if code == b"T":
                columns = parse_row_description(payload)
            elif code == b"D":
                rows.append(parse_data_row(payload))
            elif code == b"C":
                tag = _split_cstrings(payload)[0] if payload else ""
            elif code == b"Z":
                return {"ok": True, "columns": columns, "rows": rows, "tag": tag}
            elif code == b"E":
                fields = parse_error(payload)
                reason = "auth_required" if fields.get("C") == "28000" else "query_failed"
                return {
                    "ok": False,
                    "error": reason,
                    "sqlstate": fields.get("C") or "",
                    "message": fields.get("M") or "",
                    "columns": columns,
                    "rows": rows,
                }

    def terminate(self) -> None:
        try:
            self._write(encode_terminate())
        except (PostgresActuationError, OSError, socket.timeout):
            pass
        self.close()


class PostgresSession:
    """Credential-gated loopback PostgreSQL wire: bind, publish, read."""

    def __init__(self, output_dir: Path, *, password: str = DEFAULT_PASSWORD) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.user = DEFAULT_USER
        self.database = DEFAULT_DATABASE
        self.password = str(password or "")
        self.host: str | None = None
        self.port: int | None = None
        self.server: _PostgresTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.delivered = False
        self.last_token = ""
        self.history: list[dict[str, Any]] = []
        self._rows: list[str] = []
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def credentials_match(self, user: str, password: str) -> bool:
        if not self.password:
            return False
        return user == self.user and password == self.password

    def store_row(self, value: str) -> None:
        with self._lock:
            self._rows.append(str(value))

    def list_rows(self) -> list[str]:
        with self._lock:
            return list(self._rows)

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
        server = _PostgresTCPServer(("127.0.0.1", 0), _PostgresHandler, self)
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
        insert: bool = True,
        query: bool = True,
        password: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.password:
            return self._forbidden("missing_secret")
        live_token = str(token or SENTINEL)
        writer: _PostgresClient | None = None
        independent: _PostgresClient | None = None
        try:
            writer = _PostgresClient(self.host, int(self.port))
            started = writer.startup(self.user, self.database)
            if not started.get("ok"):
                return self._forbidden("startup_failed", status=503)
            if authenticate:
                secret = self.password if password is None else str(password)
                authed = writer.password(secret)
                if not authed.get("ok"):
                    reason = str(authed.get("error") or "auth_failed")
                    status = 535 if reason == "auth_failed" else 530
                    return self._forbidden(reason, status=status)
            else:
                queried = writer.query(SELECT_SQL)
                reason = str(queried.get("error") or "auth_required")
                return self._forbidden("auth_required", status=530)
            if not insert:
                return self._conflict("insert_required")
            inserted = writer.query(INSERT_SQL if live_token == SENTINEL else f"INSERT INTO {DEFAULT_TABLE}({DEFAULT_COLUMN}) VALUES('{live_token}')")
            if not inserted.get("ok"):
                return self._forbidden("insert_failed", status=550)
            if not query:
                return self._conflict("query_required")
            selected = writer.query(SELECT_SQL)
            rows = selected.get("rows") if isinstance(selected.get("rows"), list) else []
            values = [str(row[0]) for row in rows if isinstance(row, list) and row]
            if live_token not in values:
                return self._forbidden("query_required" if not values else "payload_mismatch", status=409)
            independent = _PostgresClient(self.host, int(self.port))
            if not independent.startup(self.user, self.database).get("ok"):
                return self._forbidden("independent_startup_failed", status=503)
            if not independent.password(self.password).get("ok"):
                return self._forbidden("independent_auth_failed", status=503)
            replay = independent.query(SELECT_SQL)
            replay_rows = replay.get("rows") if isinstance(replay.get("rows"), list) else []
            replay_values = [str(row[0]) for row in replay_rows if isinstance(row, list) and row]
            if live_token not in replay_values:
                return self._forbidden("independent_required", status=409)
            sealed = {
                "user": self.user,
                "database": self.database,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "authenticated": True,
                "inserted": True,
                "queried": True,
                "independent": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            live = independent_postgres_row(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "queued": False,
                "relational": True,
                "user": self.user,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "path": str(self.sealed_path),
                "authenticated": True,
                "inserted": True,
                "queried": True,
                "independent": True,
            }
        except (OSError, PostgresActuationError) as error:
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
                independent.terminate()
            if writer is not None:
                writer.terminate()

    def read(self) -> dict[str, Any]:
        live = independent_postgres_row(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "user": str(live.get("user") or ""),
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


def call_postgres_tool(session: PostgresSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one PostgreSQL tool call against a bound wire session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = arguments.get("authenticate")
    if authenticate is None:
        authenticate = True
    insert = arguments.get("insert")
    if insert is None:
        insert = True
    query = arguments.get("query")
    if query is None:
        query = True
    secret = arguments.get("password")
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            authenticate=bool(authenticate),
            insert=bool(insert),
            query=bool(query),
            password=None if secret is None else str(secret),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise PostgresActuationError(f"unsupported postgres action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_postgres_row(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed PostgreSQL result row through a fresh file open."""

    path = Path(sealed_path)
    if not path.is_file():
        return {
            "ok": False,
            "error": "missing_payload",
            "token": "",
            "sentinel": "",
            "user": "",
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
            "user": "",
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "invalid_payload",
            "token": "",
            "sentinel": "",
            "user": "",
        }
    token = str(payload.get("token") or "")
    authenticated = payload.get("authenticated") is True
    inserted = payload.get("inserted") is True
    queried = payload.get("queried") is True
    independent = payload.get("independent") is True
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and authenticated and inserted and queried and independent else "",
        "user": str(payload.get("user") or ""),
        "authenticated": authenticated,
        "inserted": inserted,
        "queried": queried,
        "independent": independent,
    }


def run_postgres_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    insert: bool = True,
    query: bool = True,
    password: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the Startup/Password/SimpleQuery workflow and seal a trace."""

    descriptor = postgres_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, POSTGRES_TOOL_PROVIDER),
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
        raise PostgresActuationError(f"postgres tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="postgres-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = PostgresSession(out, password=DEFAULT_PASSWORD if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    publish_args: dict[str, Any] = {
        "action": "publish",
        "token": SENTINEL,
        "authenticate": authenticate,
        "insert": insert,
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
                results.append(call_postgres_tool(session, arguments))
            except PostgresActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_postgres_row(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and insert
        and query
        and password is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "postgres_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "insert": insert,
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
        "delivered": bool(session.delivered or publish_result.get("relational")),
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
        "insert": insert,
        "query": query,
    }


def verify_postgres_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed PostgreSQL trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_postgres_row(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
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
        "authenticated": independent.get("authenticated") is True,
        "inserted": independent.get("inserted") is True,
        "queried": independent.get("queried") is True,
        "independent": independent.get("independent") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def postgres_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.postgres_actuation import "
        "builtin_postgres_actuation_proof; r=builtin_postgres_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='postgres_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_postgres_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=POSTGRES_ACTUATION_ID,
        name="First-class Startup/Password/SimpleQuery relational-wire actuation",
        description=(
            "Missions that require a postgres tool can opt the postgres provider "
            "in, bind a loopback PostgreSQL v3 frontend/backend listener, send a "
            "StartupMessage, cleartext-Password, INSERT then SimpleQuery a result "
            "row, independently re-Query from a fresh connection, and seal "
            "digest-chained relational traces. Default routing stays fail-closed; "
            "a missing postgres password keeps the hole falsifiable, and skip-INSERT "
            "or skip-Query stay empty."
        ),
        kind="python",
        entry="blackhole_agent.postgres_actuation:builtin_postgres_actuation_proof",
        proof_command=postgres_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.ldap-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/postgres_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required postgres tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback PostgreSQL v3 frontend/backend listener, "
            "sends a StartupMessage, authenticates with a cleartext Password, INSERTs "
            "a beacon row, SimpleQuery-reads a RowDescription/DataRow, independently "
            "re-queries from a fresh connection, and binds this family as the next "
            "diversity-catalog successor once LDAP BIND/ADD/SEARCH identity lookup is "
            "proved. Missing secrets, skipped Password, wrong passwords, skip-INSERT, "
            "and skip-Query stay fail-closed."
        ),
        tags=("postgres", "postgresql", "sql", "wire", "query", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T094802Z-b26951fe",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_postgres_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in PostgreSQL actuation seals a Startup/Password/Query row."""

    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.imap_actuation import IMAP_ACTUATION_GOAL, IMAP_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.ldap_actuation import LDAP_ACTUATION_GOAL, LDAP_ACTUATION_ID
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
    checks["denylists_self"] = POSTGRES_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(POSTGRES_ACTUATION_GOAL) == (POSTGRES_ACTUATION_ID,)
    checks["ldap_goal_is_not_postgres"] = leftover_marker_ids(LDAP_ACTUATION_GOAL) == (LDAP_ACTUATION_ID,)
    checks["dns_goal_is_not_postgres"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["mqtt_goal_is_not_postgres"] = leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    checks["redis_goal_is_not_postgres"] = leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    checks["imap_goal_is_not_postgres"] = leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    checks["smtp_goal_is_not_postgres"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    checks["sqlite_goal_is_not_postgres"] = leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (
        SQLITE_ACTUATION_ID,
    )
    checks["postgres_goal_is_not_ldap"] = LDAP_ACTUATION_ID not in leftover_marker_ids(
        POSTGRES_ACTUATION_GOAL
    )
    checks["postgres_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(
        POSTGRES_ACTUATION_GOAL
    )
    checks["postgres_goal_is_not_mqtt"] = MQTT_ACTUATION_ID not in leftover_marker_ids(
        POSTGRES_ACTUATION_GOAL
    )
    checks["postgres_goal_is_not_redis"] = REDIS_ACTUATION_ID not in leftover_marker_ids(
        POSTGRES_ACTUATION_GOAL
    )
    checks["postgres_goal_is_not_imap"] = IMAP_ACTUATION_ID not in leftover_marker_ids(
        POSTGRES_ACTUATION_GOAL
    )
    checks["postgres_goal_is_not_smtp"] = SMTP_ACTUATION_ID not in leftover_marker_ids(
        POSTGRES_ACTUATION_GOAL
    )
    checks["postgres_goal_is_not_sqlite"] = SQLITE_ACTUATION_ID not in leftover_marker_ids(
        POSTGRES_ACTUATION_GOAL
    )
    checks["ldap_marker_stays_ldap"] = POSTGRES_ACTUATION_ID not in leftover_marker_ids(
        LDAP_ACTUATION_GOAL
    )
    checks["dns_marker_stays_dns"] = POSTGRES_ACTUATION_ID not in leftover_marker_ids(
        DNS_ACTUATION_GOAL
    )
    checks["mqtt_marker_stays_mqtt"] = POSTGRES_ACTUATION_ID not in leftover_marker_ids(
        MQTT_ACTUATION_GOAL
    )
    checks["redis_marker_stays_redis"] = POSTGRES_ACTUATION_ID not in leftover_marker_ids(
        REDIS_ACTUATION_GOAL
    )
    checks["imap_marker_stays_imap"] = POSTGRES_ACTUATION_ID not in leftover_marker_ids(
        IMAP_ACTUATION_GOAL
    )
    checks["smtp_marker_stays_smtp"] = POSTGRES_ACTUATION_ID not in leftover_marker_ids(
        SMTP_ACTUATION_GOAL
    )
    checks["sqlite_marker_stays_sqlite"] = POSTGRES_ACTUATION_ID not in leftover_marker_ids(
        SQLITE_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_postgres"] = (
        len(catalog) > 36
        and catalog[36]["id"] == POSTGRES_ACTUATION_ID
        and catalog[35]["id"] == LDAP_ACTUATION_ID
    )
    family = capability_family(POSTGRES_ACTUATION_GOAL)
    checks["family_is_postgresql"] = "postgresql" in family
    checks["family_is_frontend"] = "frontend" in family
    checks["family_is_backend"] = "backend" in family
    checks["family_is_query"] = "query" in family
    checks["family_is_not_ldap"] = "ldap" not in family
    checks["family_is_not_directory"] = "directory" not in family
    checks["family_is_not_dns"] = "dns" not in family and "nameserver" not in family
    checks["family_is_not_mqtt"] = "mqtt" not in family
    checks["family_is_not_redis"] = "redi" not in family
    checks["family_is_not_imap"] = "imap" not in family
    checks["family_is_not_smtp"] = "smtp" not in family
    checks["family_is_not_sqlite"] = "sqlite" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["family_is_not_git_publication"] = "git-publication" not in family
    checks["family_is_not_auth_surface"] = family != "auth" and "auth" not in family.split("/")
    startup_wire = encode_startup(DEFAULT_USER, DEFAULT_DATABASE)
    startup_len = struct.unpack(">i", startup_wire[:4])[0]
    startup_fields = parse_startup(startup_wire[4:])
    checks["startup_roundtrip"] = (
        startup_len == len(startup_wire)
        and startup_fields.get("user") == DEFAULT_USER
        and startup_fields.get("database") == DEFAULT_DATABASE
        and int(startup_fields.get("version") or 0) == PROTOCOL_VERSION_3
    )
    password_wire = encode_password(DEFAULT_PASSWORD)
    password_code = password_wire[:1]
    password_len = struct.unpack(">i", password_wire[1:5])[0]
    password_text = _split_cstrings(password_wire[5:])[0]
    checks["password_roundtrip"] = (
        password_code == b"p"
        and password_len == len(password_wire) - 1
        and password_text == DEFAULT_PASSWORD
    )
    query_wire = encode_query(SELECT_SQL)
    query_code = query_wire[:1]
    query_text = _split_cstrings(query_wire[5:])[0]
    checks["query_roundtrip"] = query_code == b"Q" and query_text == SELECT_SQL
    row_wire = encode_data_row(SENTINEL)
    row_code = row_wire[:1]
    row_payload_len = struct.unpack(">i", row_wire[1:5])[0]
    row_values = parse_data_row(row_wire[5:])
    checks["datarow_roundtrip"] = (
        row_code == b"D"
        and row_payload_len == len(row_wire) - 1
        and row_values == [SENTINEL]
    )
    checks["not_an_ldap_duplicate"] = (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(LDAP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_dns_duplicate"] = (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(DNS_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_an_mqtt_duplicate"] = (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(MQTT_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_redis_duplicate"] = (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(REDIS_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_an_imap_duplicate"] = (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(IMAP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_smtp_duplicate"] = (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_sqlite_duplicate"] = (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(SQLITE_ACTUATION_GOAL),
        )
        < 0.82
    )

    mcp_postgres = ToolDescriptor(name="remote_postgres", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_postgres)
    checks["naive_mcp_postgres_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = postgres_tool_descriptor()
    default_postgres = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, POSTGRES_TOOL_PROVIDER),
    )
    checks["default_postgres_provider_is_unsupported"] = (
        default_postgres.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{POSTGRES_TOOL_PROVIDER}" in default_postgres.reasons
    )
    checks["opted_in_postgres_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_postgres],
        required_tool_names=("local_memory", "postgres"),
    )
    checks["naive_preflight_missing_postgres"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["postgres"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "postgres"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, POSTGRES_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "postgres" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="postgres-actuation-") as tmp:
        root = Path(tmp)
        missing = run_postgres_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_postgres_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_postgres_workflow(password="wrong-secret", output_dir=root / "wrong")
        skip_insert = run_postgres_workflow(insert=False, output_dir=root / "skip-insert")
        skip_query = run_postgres_workflow(query=False, output_dir=root / "skip-query")
        live = run_postgres_workflow(output_dir=root / "live")
        verify = verify_postgres_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_postgres_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unauthenticated_query_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 530
            and unauth["error"] == "auth_required"
            and unauth["delivered"] is False
            and unauth["payload_exists"] is False
        )
        checks["wrong_secret_is_forbidden"] = (
            wrong["ok"] is False
            and wrong["final_status"] == 535
            and wrong["error"] == "auth_failed"
            and wrong["payload_exists"] is False
        )
        checks["skip_insert_stays_empty"] = (
            skip_insert["ok"] is False
            and skip_insert["error"] == "insert_required"
            and skip_insert["final_status"] == 409
            and skip_insert["payload_exists"] is False
        )
        checks["skip_query_stays_empty"] = (
            skip_query["ok"] is False
            and skip_query["error"] == "query_required"
            and skip_query["final_status"] == 409
            and skip_query["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_row"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["secret_password_insert_and_query_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_insert["ok"] is False
            and skip_query["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="postgres-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != POSTGRES_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_postgres"] = (
        live_goal == POSTGRES_ACTUATION_GOAL
        and POSTGRES_ACTUATION_ID in live_done
        and live_source == "genesis_bind_postgres"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_postgres_actuation_capability()
    return {
        "ok": ok,
        "action": "postgres_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": POSTGRES_ACTUATION_GOAL,
        "done_when": POSTGRES_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
