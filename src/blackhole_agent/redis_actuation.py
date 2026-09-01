"""Drive a first-class Redis tool through a BLPOP-gated work-queue workflow.

Tool routing already fails missions that require ``redis``: hosted cache-queue
plugins stay on the unsupported MCP provider, and no first-party Redis
provider is executable. Unbound therefore cannot speak requirepass AUTH,
SELECT a logical database, BLPOP a newly RPUSH'd job, or seal a queue.

This module closes that hole:

- advertise a ``redis`` provider tool that stays fail-closed until opted in
- drive bind / pop / read against a real loopback RESP listener
- keep a missing-secret client so the requirepass hole stays falsifiable
- refuse SELECT/BLPOP until AUTH succeeds
- deliver a new job only while BLPOP is blocked, so skip-BLPOP stays empty
- persist a sealed queue an independent reader can re-open from disk
- bind this family as the next diversity-catalog successor after IMAP
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import socketserver
import tempfile
import threading
import time
from collections import deque
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
    REDIS_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    redis_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
REDIS_ACTUATION_ID = "capability.redis-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-redis"
SENTINEL = "BH-REDIS-OK"
DEFAULT_PASSWORD = "blackhole-redis-secret"
DEFAULT_DB = 0
DEFAULT_KEY = "jobs"
SEALED_NAME = "sealed.json"

REDIS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{REDIS_ACTUATION_ID};"
    f"capability_proved:{REDIS_ACTUATION_ID};"
    "no_skill_route"
)
REDIS_ACTUATION_GOAL = (
    "Repair Redis BLPOP-gated work queue: hosted cache-queue tools remain "
    "unsupported so a requirepass/SELECT/BLPOP cycle cannot land and a sealed "
    "job payload cannot be produced. A missing Redis requirepass secret stays "
    "forbidden; fail-closed routing never opts the redis provider in."
)


class RedisActuationError(RuntimeError):
    """Raised when the Redis session or listener fixture misbehaves."""


class _RedisError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _encode_bulk(value: str | bytes) -> bytes:
    raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
    return f"${len(raw)}\r\n".encode("ascii") + raw + b"\r\n"


def _encode_array(items: list[str | bytes]) -> bytes:
    parts = [f"*{len(items)}\r\n".encode("ascii")]
    for item in items:
        parts.append(_encode_bulk(item))
    return b"".join(parts)


def _encode_simple(value: str) -> bytes:
    return f"+{value}\r\n".encode("utf-8")


def _encode_error(value: str) -> bytes:
    return f"-{value}\r\n".encode("utf-8")


def _encode_int(value: int) -> bytes:
    return f":{value}\r\n".encode("ascii")


def _read_resp(rfile: Any) -> Any:
    header = rfile.readline()
    if not header:
        return None
    prefix = header[:1]
    rest = header[1:].rstrip(b"\r\n")
    if prefix == b"+":
        return rest.decode("utf-8", errors="replace")
    if prefix == b"-":
        raise _RedisError(rest.decode("utf-8", errors="replace"))
    if prefix == b":":
        return int(rest)
    if prefix == b"$":
        size = int(rest)
        if size < 0:
            return None
        payload = rfile.read(size)
        rfile.read(2)
        return payload
    if prefix == b"*":
        count = int(rest)
        if count < 0:
            return None
        return [_read_resp(rfile) for _ in range(count)]
    raise RedisActuationError(f"unsupported RESP prefix: {header!r}")


def _as_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


class _RedisTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(self, address: tuple[str, int], handler: type[socketserver.BaseRequestHandler], session: RedisSession) -> None:
        self.session = session
        super().__init__(address, handler)


class _RedisHandler(socketserver.StreamRequestHandler):
    timeout = None

    def _send(self, payload: bytes) -> None:
        self.wfile.write(payload)
        self.wfile.flush()

    def handle(self) -> None:
        session: RedisSession = self.server.session  # type: ignore[attr-defined]
        authed = False
        selected: int | None = None
        while True:
            try:
                message = _read_resp(self.rfile)
            except (_RedisError, RedisActuationError, OSError, ValueError):
                return
            if message is None:
                return
            if not isinstance(message, list) or not message:
                self._send(_encode_error("ERR protocol error"))
                continue
            command = _as_text(message[0]).upper()
            args = [_as_text(item) for item in message[1:]]
            if command == "AUTH":
                secret = args[-1] if args else ""
                if session.credentials_match(secret):
                    authed = True
                    self._send(_encode_simple("OK"))
                else:
                    self._send(_encode_error("ERR invalid password"))
            elif command == "PING":
                self._send(_encode_simple("PONG"))
            elif command == "QUIT":
                self._send(_encode_simple("OK"))
                return
            elif command == "SELECT":
                if not authed:
                    self._send(_encode_error("NOAUTH Authentication required."))
                    continue
                try:
                    index = int(args[0]) if args else DEFAULT_DB
                except ValueError:
                    self._send(_encode_error("ERR invalid DB index"))
                    continue
                selected = index
                self._send(_encode_simple("OK"))
            elif command == "RPUSH":
                if not authed:
                    self._send(_encode_error("NOAUTH Authentication required."))
                    continue
                if selected is None:
                    self._send(_encode_error("ERR SELECT the database first"))
                    continue
                if len(args) < 2:
                    self._send(_encode_error("ERR wrong number of arguments"))
                    continue
                length = session.rpush(selected, args[0], args[1])
                self._send(_encode_int(length))
            elif command in {"BLPOP", "LPOP"}:
                if not authed:
                    self._send(_encode_error("NOAUTH Authentication required."))
                    continue
                if selected is None:
                    self._send(_encode_error("ERR SELECT the database first"))
                    continue
                key = args[0] if args else DEFAULT_KEY
                if command == "LPOP":
                    value = session.lpop(selected, key)
                    if value is None:
                        self._send(b"$-1\r\n")
                    else:
                        self._send(_encode_bulk(value))
                    continue
                timeout = 0.0
                if len(args) > 1:
                    try:
                        timeout = float(args[1])
                    except ValueError:
                        timeout = 0.0
                value = session.blpop(selected, key, timeout=timeout)
                if value is None:
                    self._send(b"*-1\r\n")
                else:
                    self._send(_encode_array([key, value]))
            else:
                self._send(_encode_error(f"ERR unknown command '{command}'"))


class _RedisClient:
    """Minimal RESP client with AUTH, SELECT, BLPOP, and LPOP."""

    def __init__(self, host: str, port: int, *, timeout: float = 6.0) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.rfile = self.sock.makefile("rb", buffering=0)
        self.wfile = self.sock.makefile("wb", buffering=0)
        self.timeout = timeout

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

    def _write(self, items: list[str | bytes]) -> None:
        self.wfile.write(_encode_array(items))
        self.wfile.flush()

    def command(self, *items: str) -> Any:
        self._write(list(items))
        return _read_resp(self.rfile)

    def auth(self, password: str) -> tuple[bool, str]:
        try:
            reply = self.command("AUTH", password)
        except _RedisError as error:
            return False, error.message
        return reply == "OK", str(reply)

    def select(self, index: int = DEFAULT_DB) -> tuple[bool, str]:
        try:
            reply = self.command("SELECT", str(index))
        except _RedisError as error:
            return False, error.message
        return reply == "OK", str(reply)

    def blpop(self, key: str, *, timeout: float = 4.0) -> str | None:
        try:
            reply = self.command("BLPOP", key, str(int(timeout)))
        except _RedisError:
            return None
        if not isinstance(reply, list) or len(reply) < 2:
            return None
        return _as_text(reply[1])

    def lpop(self, key: str) -> str | None:
        try:
            reply = self.command("LPOP", key)
        except _RedisError:
            return None
        if reply is None:
            return None
        return _as_text(reply)

    def quit(self) -> None:
        try:
            self.command("QUIT")
        except (RedisActuationError, _RedisError, OSError, socket.timeout):
            pass


class RedisSession:
    """Credential-gated loopback Redis listener: bind, blpop, read."""

    def __init__(self, output_dir: Path, *, password: str = DEFAULT_PASSWORD) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.password = str(password or "")
        self.host: str | None = None
        self.port: int | None = None
        self.server: _RedisTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.delivered = False
        self.last_token = ""
        self.history: list[dict[str, Any]] = []
        self._queues: dict[tuple[int, str], deque[str]] = {}
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def credentials_match(self, password: str) -> bool:
        if not self.password:
            return False
        return password == self.password

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

    def _queue(self, db: int, key: str) -> deque[str]:
        slot = (int(db), str(key))
        if slot not in self._queues:
            self._queues[slot] = deque()
        return self._queues[slot]

    def rpush(self, db: int, key: str, value: str) -> int:
        with self._cv:
            queue = self._queue(db, key)
            queue.append(str(value))
            self._cv.notify_all()
            return len(queue)

    def lpop(self, db: int, key: str) -> str | None:
        with self._cv:
            queue = self._queue(db, key)
            if not queue:
                return None
            return queue.popleft()

    def blpop(self, db: int, key: str, *, timeout: float = 4.0) -> str | None:
        deadline = time.monotonic() + max(0.0, float(timeout))
        with self._cv:
            while True:
                queue = self._queue(db, key)
                if queue:
                    return queue.popleft()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cv.wait(timeout=remaining)

    def inject(self, token: str) -> dict[str, Any]:
        value = str(token or SENTINEL)
        length = self.rpush(DEFAULT_DB, DEFAULT_KEY, value)
        return {"db": DEFAULT_DB, "key": DEFAULT_KEY, "token": value, "length": length}

    def _delayed_inject(self, token: str) -> None:
        time.sleep(0.05)
        self.inject(token)

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
        server = _RedisTCPServer(("127.0.0.1", 0), _RedisHandler, self)
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

    def pop(
        self,
        token: str = SENTINEL,
        *,
        authenticate: bool = True,
        blpop: bool = True,
        password: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.password:
            return self._forbidden("missing_secret")
        client: _RedisClient | None = None
        injector: threading.Thread | None = None
        try:
            client = _RedisClient(self.host, int(self.port))
            if authenticate:
                ok, status = client.auth(password if password is not None else self.password)
                if not ok:
                    return self._forbidden("auth_failed", status=535)
            selected, select_status = client.select(DEFAULT_DB)
            if not selected:
                reason = (
                    "auth_gated"
                    if "NOAUTH" in select_status.upper() or not authenticate
                    else "select_failed"
                )
                code = 530 if reason == "auth_gated" else 550
                return self._forbidden(reason, status=code)
            live_token = ""
            blocked = False
            if blpop:
                injector = threading.Thread(
                    target=self._delayed_inject,
                    args=(str(token or SENTINEL),),
                    daemon=True,
                )
                injector.start()
                popped = client.blpop(DEFAULT_KEY, timeout=4.0)
                injector.join(timeout=2)
                if popped is None:
                    return self._forbidden("blpop_timeout", status=408)
                live_token = popped
                blocked = True
            else:
                popped = client.lpop(DEFAULT_KEY)
                if popped is None:
                    return self._forbidden("blpop_required", status=409)
                live_token = popped
            sealed = {
                "db": DEFAULT_DB,
                "key": DEFAULT_KEY,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "authenticated": True,
                "selected": True,
                "blocked": blocked,
                "popped_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            live = independent_redis_queue(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "queued": True,
                "db": DEFAULT_DB,
                "key": DEFAULT_KEY,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "path": str(self.sealed_path),
                "authenticated": bool(authenticate),
                "blocked": blocked,
            }
        except (OSError, RedisActuationError, _RedisError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error),
                "token": str(token or SENTINEL),
                "sentinel": "",
            }
        finally:
            if injector is not None and injector.is_alive():
                injector.join(timeout=1)
            if client is not None:
                client.quit()
                client.close()

    def read(self) -> dict[str, Any]:
        live = independent_redis_queue(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "key": str(live.get("key") or ""),
            "db": int(live.get("db") or 0),
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


def call_redis_tool(session: RedisSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one Redis tool call against a bound listener session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = arguments.get("authenticate")
    if authenticate is None:
        authenticate = True
    blpop = arguments.get("blpop")
    if blpop is None:
        blpop = True
    password = arguments.get("password")
    if action == "bind":
        result = session.bind()
    elif action == "pop":
        result = session.pop(
            token,
            authenticate=bool(authenticate),
            blpop=bool(blpop),
            password=None if password is None else str(password),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise RedisActuationError(f"unsupported redis action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_redis_queue(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed Redis queue through a fresh file open."""

    path = Path(sealed_path)
    if not path.is_file():
        return {"ok": False, "error": "missing_payload", "token": "", "sentinel": "", "key": "", "db": 0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "ok": False,
            "error": "invalid_payload",
            "detail": str(error),
            "token": "",
            "sentinel": "",
            "key": "",
            "db": 0,
        }
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_payload", "token": "", "sentinel": "", "key": "", "db": 0}
    token = str(payload.get("token") or "")
    authenticated = payload.get("authenticated") is True
    selected = payload.get("selected") is True
    blocked = payload.get("blocked") is True
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and authenticated and selected and blocked else "",
        "key": str(payload.get("key") or ""),
        "db": int(payload.get("db") or 0),
        "authenticated": authenticated,
        "selected": selected,
        "blocked": blocked,
    }


def run_redis_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    blpop: bool = True,
    password: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the requirepass/SELECT/BLPOP-gated workflow and seal a trace."""

    descriptor = redis_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, REDIS_TOOL_PROVIDER),
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
        raise RedisActuationError(f"redis tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="redis-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = RedisSession(out, password=DEFAULT_PASSWORD if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    pop_args: dict[str, Any] = {
        "action": "pop",
        "token": SENTINEL,
        "authenticate": authenticate,
        "blpop": blpop,
    }
    if password is not None:
        pop_args["password"] = password
    calls.append(pop_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_redis_tool(session, arguments))
            except RedisActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    pop_result = next((item for item in results if item.get("action") == "pop"), {})
    independent = independent_redis_queue(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and blpop
        and password is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "redis_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "blpop": blpop,
        "wrong_password": password is not None,
        "sealed_path": str(session.sealed_path),
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "independent": independent,
        "independent_digest": _digest(independent),
        "sentinel": sentinel,
        "delivered": bool(session.delivered or pop_result.get("queued")),
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
        "error": str(final.get("error") or pop_result.get("error") or ""),
        "delivered": bool(trace_body["delivered"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "blpop": blpop,
    }


def verify_redis_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Redis trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_redis_queue(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
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
        "selected": independent.get("selected") is True,
        "blocked": independent.get("blocked") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def redis_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.redis_actuation import "
        "builtin_redis_actuation_proof; r=builtin_redis_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='redis_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_redis_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=REDIS_ACTUATION_ID,
        name="First-class BLPOP-gated Redis work-queue actuation",
        description=(
            "Missions that require a redis tool can opt the redis provider in, "
            "bind a loopback RESP listener, AUTH with requirepass, SELECT a "
            "logical database, BLPOP a newly RPUSH'd job, and seal a "
            "digest-chained queue. Default routing stays fail-closed; a missing "
            "requirepass secret keeps the hole falsifiable, and skip-BLPOP stays "
            "empty."
        ),
        kind="python",
        entry="blackhole_agent.redis_actuation:builtin_redis_actuation_proof",
        proof_command=redis_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.imap-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/redis_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required redis tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RESP listener, authenticates with "
            "requirepass, SELECTs a database, BLPOP-waits until a job is RPUSH'd, "
            "independently re-reads the sealed sentinel, and binds this family as "
            "the next diversity-catalog successor once IMAP UID/IDLE inbound mail "
            "is proved. Missing credentials, skipped AUTH, wrong passwords, and "
            "skip-BLPOP stay fail-closed."
        ),
        tags=("redis", "blpop", "queue", "resp", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T073344Z-22b53591",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_redis_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in Redis actuation seals a BLPOP-gated queue."""

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
    from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
    from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = REDIS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    checks["imap_goal_is_not_redis"] = leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    checks["smtp_goal_is_not_redis"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    checks["sqlite_goal_is_not_redis"] = leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (
        SQLITE_ACTUATION_ID,
    )
    checks["redis_goal_is_not_imap"] = IMAP_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    checks["redis_goal_is_not_smtp"] = SMTP_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    checks["redis_goal_is_not_sqlite"] = SQLITE_ACTUATION_ID not in leftover_marker_ids(
        REDIS_ACTUATION_GOAL
    )
    checks["imap_marker_stays_imap"] = REDIS_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    checks["smtp_marker_stays_smtp"] = REDIS_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    checks["sqlite_marker_stays_sqlite"] = REDIS_ACTUATION_ID not in leftover_marker_ids(
        SQLITE_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_redis"] = (
        len(catalog) > 32
        and catalog[32]["id"] == REDIS_ACTUATION_ID
        and catalog[31]["id"] == IMAP_ACTUATION_ID
    )
    family = capability_family(REDIS_ACTUATION_GOAL)
    checks["family_is_redis"] = "redi" in family
    checks["family_is_blpop"] = "blpop" in family
    checks["family_is_not_imap"] = "imap" not in family
    checks["family_is_not_smtp"] = "smtp" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["family_is_not_auth_surface"] = family != "auth" and "auth" not in family.split("/")
    checks["not_an_imap_duplicate"] = (
        semantic_similarity(
            semantic_signature(REDIS_ACTUATION_GOAL),
            semantic_signature(IMAP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_smtp_duplicate"] = (
        semantic_similarity(
            semantic_signature(REDIS_ACTUATION_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_sqlite_duplicate"] = (
        semantic_similarity(
            semantic_signature(REDIS_ACTUATION_GOAL),
            semantic_signature(SQLITE_ACTUATION_GOAL),
        )
        < 0.82
    )

    mcp_redis = ToolDescriptor(name="remote_redis", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_redis)
    checks["naive_mcp_redis_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = redis_tool_descriptor()
    default_redis = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, REDIS_TOOL_PROVIDER),
    )
    checks["default_redis_provider_is_unsupported"] = (
        default_redis.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{REDIS_TOOL_PROVIDER}" in default_redis.reasons
    )
    checks["opted_in_redis_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_redis],
        required_tool_names=("local_memory", "redis"),
    )
    checks["naive_preflight_missing_redis"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["redis"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "redis"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, REDIS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "redis" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="redis-actuation-") as tmp:
        root = Path(tmp)
        missing = run_redis_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_redis_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_redis_workflow(password="wrong-password", output_dir=root / "wrong")
        skip_blpop = run_redis_workflow(blpop=False, output_dir=root / "skip-blpop")
        live = run_redis_workflow(output_dir=root / "live")
        verify = verify_redis_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_redis_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unauthenticated_select_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 530
            and unauth["error"] == "auth_gated"
            and unauth["delivered"] is False
            and unauth["payload_exists"] is False
        )
        checks["wrong_password_is_forbidden"] = (
            wrong["ok"] is False
            and wrong["final_status"] == 535
            and wrong["error"] == "auth_failed"
            and wrong["payload_exists"] is False
        )
        checks["skip_blpop_stays_empty"] = (
            skip_blpop["ok"] is False
            and skip_blpop["error"] == "blpop_required"
            and skip_blpop["final_status"] == 409
            and skip_blpop["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_queue"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["secret_auth_and_blpop_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_blpop["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="redis-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != REDIS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_redis"] = (
        live_goal == REDIS_ACTUATION_GOAL
        and REDIS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_redis"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_redis_actuation_capability()
    return {
        "ok": ok,
        "action": "redis_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": REDIS_ACTUATION_GOAL,
        "done_when": REDIS_ACTUATION_DONE_WHEN,
    }
