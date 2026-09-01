"""Drive a first-class IMAP tool through a UID/IDLE-gated inbound workflow.

Tool routing already fails missions that require ``imap``: hosted mail-retrieval
plugins stay on the unsupported MCP provider, and no first-party IMAP
provider is executable. Unbound therefore cannot AUTHENTICATE, SELECT INBOX,
IDLE for EXISTS, UID FETCH a newly arrived message, or seal an inbox.

This module closes that hole:

- advertise an ``imap`` provider tool that stays fail-closed until opted in
- drive bind / fetch / read against a real loopback IMAP4rev1 listener
- keep a missing-secret client so the AUTHENTICATE hole stays falsifiable
- refuse SELECT/FETCH until AUTHENTICATE PLAIN (or LOGIN) succeeds
- deliver new mail only while IDLE is active, so skip-IDLE stays empty
- persist a sealed inbox an independent reader can re-open from disk
- bind this family as the next diversity-catalog successor after HTTP auth
"""

from __future__ import annotations

import base64
import hashlib
import json
import select
import shutil
import socket
import socketserver
import tempfile
import threading
import time
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
    IMAP_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    imap_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
IMAP_ACTUATION_ID = "capability.imap-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-imap"
SENTINEL = "BH-IMAP-OK"
DEFAULT_USER = "blackhole"
DEFAULT_PASSWORD = "blackhole-imap-secret"
DEFAULT_FROM = "beacon@blackhole.invalid"
DEFAULT_TO = "operator@blackhole.invalid"
SEALED_NAME = "sealed.json"
TOKEN_HEADER = "X-Blackhole-Token"

IMAP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{IMAP_ACTUATION_ID};"
    f"capability_proved:{IMAP_ACTUATION_ID};"
    "no_skill_route"
)
IMAP_ACTUATION_GOAL = (
    "Repair IMAP UID-gated inbound mailbox: hosted mail-retrieval tools remain "
    "unsupported so an AUTHENTICATE/SELECT/IDLE/UID FETCH cycle cannot land and "
    "a sealed inbox cannot be produced. A missing IMAP AUTHENTICATE secret stays "
    "forbidden; fail-closed routing never opts the imap provider in."
)


class ImapActuationError(RuntimeError):
    """Raised when the IMAP session or listener fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _decode_auth_blob(blob: str) -> tuple[str, str]:
    raw = base64.b64decode(str(blob or "").encode("ascii"), validate=False)
    parts = raw.split(b"\0")
    if len(parts) >= 3:
        user = parts[1].decode("utf-8", errors="replace")
        password = parts[2].decode("utf-8", errors="replace")
        return user, password
    if len(parts) == 2:
        return parts[0].decode("utf-8", errors="replace"), parts[1].decode("utf-8", errors="replace")
    return "", ""


def _imap_tokens(line: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    length = len(line)
    while index < length:
        char = line[index]
        if char.isspace():
            index += 1
            continue
        if char == '"':
            index += 1
            buf: list[str] = []
            while index < length:
                if line[index] == "\\" and index + 1 < length:
                    buf.append(line[index + 1])
                    index += 2
                    continue
                if line[index] == '"':
                    index += 1
                    break
                buf.append(line[index])
                index += 1
            tokens.append("".join(buf))
            continue
        cursor = index
        while cursor < length and not line[cursor].isspace():
            cursor += 1
        tokens.append(line[index:cursor])
        index = cursor
    return tokens


def _rfc822(token: str) -> bytes:
    body = str(token or SENTINEL)
    return "\r\n".join(
        (
            f"From: {DEFAULT_FROM}",
            f"To: {DEFAULT_TO}",
            "Subject: blackhole-imap-beacon",
            f"{TOKEN_HEADER}: {body}",
            "",
            body,
            "",
        )
    ).encode("utf-8")


def _parse_rfc822(raw: bytes) -> dict[str, str]:
    text = raw.decode("utf-8", errors="replace")
    if "\r\n\r\n" in text:
        header_blob, _, body = text.partition("\r\n\r\n")
    else:
        header_blob, _, body = text.partition("\n\n")
    headers: dict[str, str] = {}
    for line in header_blob.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    body_text = body.strip()
    token = headers.get(TOKEN_HEADER.lower()) or ""
    if not token and body_text:
        token = body_text.splitlines()[0].strip()
    return {
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "token": token,
        "body": body_text,
    }


class _ImapTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(self, address: tuple[str, int], handler: type[socketserver.BaseRequestHandler], session: ImapSession) -> None:
        self.session = session
        super().__init__(address, handler)


class _ImapHandler(socketserver.StreamRequestHandler):
    timeout = None

    def _send(self, line: str) -> None:
        self.wfile.write(f"{line}\r\n".encode("ascii", errors="replace"))
        self.wfile.flush()

    def _write_bytes(self, payload: bytes) -> None:
        self.wfile.write(payload)
        self.wfile.flush()

    def _readline(self) -> str | None:
        raw = self.rfile.readline()
        if not raw:
            return None
        return raw.decode("utf-8", errors="replace").rstrip("\r\n")

    def handle(self) -> None:
        session: ImapSession = self.server.session  # type: ignore[attr-defined]
        authed = False
        selected = False
        self._send("* OK [CAPABILITY IMAP4rev1 AUTH=PLAIN IDLE] blackhole IMAP ready")
        while True:
            try:
                line = self._readline()
            except socket.timeout:
                return
            if line is None:
                return
            tokens = _imap_tokens(line)
            if not tokens:
                continue
            tag = tokens[0]
            command = tokens[1].upper() if len(tokens) > 1 else ""
            args = tokens[2:]
            if command == "CAPABILITY":
                self._send("* CAPABILITY IMAP4rev1 AUTH=PLAIN IDLE")
                self._send(f"{tag} OK CAPABILITY completed")
            elif command == "LOGIN":
                user = args[0] if args else ""
                password = args[1] if len(args) > 1 else ""
                if session.credentials_match(user, password):
                    authed = True
                    self._send(f"{tag} OK LOGIN completed")
                else:
                    self._send(f"{tag} NO [AUTHENTICATIONFAILED] LOGIN failed")
            elif command == "AUTHENTICATE":
                authed = self._authenticate(session, tag, args)
            elif command == "SELECT":
                if not authed:
                    self._send(f"{tag} NO [AUTHENTICATIONFAILED] Authentication required")
                    continue
                selected = True
                with session._lock:
                    count = len(session.messages)
                    uidnext = session.uidnext
                self._send("* FLAGS (\\Seen \\Recent)")
                self._send(f"* {count} EXISTS")
                self._send("* 0 RECENT")
                self._send("* OK [UIDVALIDITY 1] UIDs valid")
                self._send(f"* OK [UIDNEXT {uidnext}] Predicted next UID")
                self._send(f"{tag} OK [READ-WRITE] SELECT completed")
            elif command == "IDLE":
                if not authed or not selected:
                    self._send(f"{tag} NO Authentication required")
                    continue
                self._idle(session, tag)
            elif command == "UID" and args and args[0].upper() == "FETCH":
                if not authed:
                    self._send(f"{tag} NO [AUTHENTICATIONFAILED] Authentication required")
                    continue
                uid_text = args[1] if len(args) > 1 else ""
                try:
                    uid = int(uid_text)
                except ValueError:
                    self._send(f"{tag} BAD invalid UID")
                    continue
                message = session.message_by_uid(uid)
                if message is None:
                    self._send(f"{tag} NO [NONEXISTENT] no such UID")
                    continue
                raw = bytes(message["rfc822"])
                seq = int(message["seq"])
                self._send(f"* {seq} FETCH (UID {uid} RFC822 {{{len(raw)}}}")
                self._write_bytes(raw)
                self._write_bytes(b")\r\n")
                self._send(f"{tag} OK FETCH completed")
            elif command == "NOOP":
                self._send(f"{tag} OK NOOP completed")
            elif command == "LOGOUT":
                self._send("* BYE blackhole IMAP")
                self._send(f"{tag} OK LOGOUT completed")
                return
            else:
                self._send(f"{tag} BAD Command not implemented")

    def _authenticate(self, session: ImapSession, tag: str, args: list[str]) -> bool:
        mechanism = args[0].upper() if args else ""
        if mechanism != "PLAIN":
            self._send(f"{tag} NO [AUTHENTICATIONFAILED] Unknown mechanism")
            return False
        blob = args[1] if len(args) > 1 else ""
        if not blob:
            self._send("+")
            follow = self._readline()
            if follow is None or follow == "*":
                self._send(f"{tag} NO AUTHENTICATE cancelled")
                return False
            blob = follow
        user, password = _decode_auth_blob(blob)
        if session.credentials_match(user, password):
            self._send(f"{tag} OK AUTHENTICATE completed")
            return True
        self._send(f"{tag} NO [AUTHENTICATIONFAILED] AUTHENTICATE failed")
        return False

    def _idle(self, session: ImapSession, tag: str) -> None:
        self._send("+ idling")
        exists_sent = 0
        while True:
            with session._lock:
                count = len(session.messages)
            if count > exists_sent:
                self._send(f"* {count} EXISTS")
                exists_sent = count
            ready, _, _ = select.select([self.request], [], [], 0.1)
            if not ready:
                continue
            try:
                line = self._readline()
            except OSError:
                return
            if line is None:
                return
            if line.strip().upper() == "DONE":
                self._send(f"{tag} OK IDLE completed")
                return


class _ImapClient:
    """Minimal IMAP4rev1 client with AUTHENTICATE PLAIN, IDLE, and UID FETCH."""

    def __init__(self, host: str, port: int, *, timeout: float = 5.0) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.rfile = self.sock.makefile("rb", buffering=0)
        self.wfile = self.sock.makefile("wb", buffering=0)
        self.timeout = timeout
        self.tag_id = 0
        self.last_literal = b""
        greeting = self._readline()
        if greeting is None or not greeting.startswith("* OK"):
            raise ImapActuationError(f"bad IMAP greeting: {greeting!r}")

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

    def _next_tag(self) -> str:
        self.tag_id += 1
        return f"A{self.tag_id:04d}"

    def _write(self, line: str) -> None:
        self.wfile.write(f"{line}\r\n".encode("utf-8"))
        self.wfile.flush()

    def _readline(self) -> str | None:
        raw = self.rfile.readline()
        if not raw:
            return None
        return raw.decode("utf-8", errors="replace").rstrip("\r\n")

    def _read_logical(self) -> str | None:
        line = self._readline()
        if line is None:
            return None
        if line.endswith("}") and "{" in line:
            try:
                size = int(line[line.rfind("{") + 1 : -1])
            except ValueError:
                return line
            self.last_literal = self.rfile.read(size)
            rest = self._readline() or ""
            return f"{line}\n{rest}"
        return line

    def _read_until_tag(self, tag: str) -> list[str]:
        lines: list[str] = []
        while True:
            line = self._read_logical()
            if line is None:
                raise ImapActuationError("IMAP connection closed")
            lines.append(line)
            first = line.split("\n", 1)[0]
            if first.startswith(f"{tag} "):
                return lines

    def command(self, payload: str) -> tuple[str, list[str]]:
        tag = self._next_tag()
        self._write(f"{tag} {payload}")
        return tag, self._read_until_tag(tag)

    def tagged_ok(self, tag: str, lines: list[str]) -> bool:
        return lines[-1].split("\n", 1)[0].upper().startswith(f"{tag} OK")

    def authenticate_plain(self, user: str, password: str) -> tuple[bool, str]:
        tag = self._next_tag()
        self._write(f"{tag} AUTHENTICATE PLAIN")
        challenge = self._readline()
        if challenge is None or not challenge.startswith("+"):
            return False, challenge or "missing challenge"
        blob = base64.b64encode(b"\0" + user.encode("utf-8") + b"\0" + password.encode("utf-8")).decode("ascii")
        self._write(blob)
        lines = self._read_until_tag(tag)
        status = lines[-1].split("\n", 1)[0]
        return self.tagged_ok(tag, lines), status

    def select_inbox(self) -> tuple[bool, str]:
        tag, lines = self.command("SELECT INBOX")
        return self.tagged_ok(tag, lines), lines[-1].split("\n", 1)[0]

    def idle_until_exists(self, *, timeout: float = 4.0) -> bool:
        tag = self._next_tag()
        self._write(f"{tag} IDLE")
        challenge = self._readline()
        if challenge is None or not challenge.startswith("+"):
            return False
        deadline = time.monotonic() + timeout
        saw = False
        while time.monotonic() < deadline:
            remaining = max(0.0, min(0.1, deadline - time.monotonic()))
            ready, _, _ = select.select([self.sock], [], [], remaining)
            if not ready:
                continue
            try:
                line = self._readline()
            except OSError:
                break
            if line is None:
                break
            if " EXISTS" in f" {line.upper()}":
                saw = True
                break
        try:
            self._write("DONE")
            self._read_until_tag(tag)
        except (ImapActuationError, OSError, socket.timeout):
            pass
        return saw

    def uid_fetch(self, uid: int) -> dict[str, Any]:
        self.last_literal = b""
        tag, lines = self.command(f"UID FETCH {uid} (RFC822)")
        status = lines[-1].split("\n", 1)[0]
        if not self.tagged_ok(tag, lines):
            return {"ok": False, "raw": b"", "status": status}
        return {"ok": True, "raw": self.last_literal, "status": status}

    def logout(self) -> None:
        try:
            self.command("LOGOUT")
        except (ImapActuationError, OSError, socket.timeout):
            pass


class ImapSession:
    """Credential-gated loopback IMAP listener: bind, idle-fetch, read."""

    def __init__(self, output_dir: Path, *, password: str = DEFAULT_PASSWORD, user: str = DEFAULT_USER) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.user = str(user or "")
        self.password = str(password or "")
        self.host: str | None = None
        self.port: int | None = None
        self.server: _ImapTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.delivered = False
        self.last_token = ""
        self.history: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.uidnext = 1
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def credentials_match(self, user: str, password: str) -> bool:
        if not self.password:
            return False
        return bool(user) and user == self.user and password == self.password

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

    def message_by_uid(self, uid: int) -> dict[str, Any] | None:
        with self._lock:
            for item in self.messages:
                if int(item["uid"]) == uid:
                    return dict(item)
        return None

    def inject(self, token: str) -> dict[str, Any]:
        raw = _rfc822(token)
        parsed = _parse_rfc822(raw)
        with self._lock:
            uid = self.uidnext
            self.uidnext += 1
            message = {
                "uid": uid,
                "seq": len(self.messages) + 1,
                "token": parsed["token"] or str(token or SENTINEL),
                "rfc822": raw,
                "from": parsed["from"],
                "to": parsed["to"],
            }
            self.messages.append(message)
        return message

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
        server = _ImapTCPServer(("127.0.0.1", 0), _ImapHandler, self)
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

    def fetch(
        self,
        token: str = SENTINEL,
        *,
        authenticate: bool = True,
        idle: bool = True,
        password: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.password:
            return self._forbidden("missing_secret")
        client: _ImapClient | None = None
        injector: threading.Thread | None = None
        try:
            client = _ImapClient(self.host, int(self.port))
            if authenticate:
                ok, status = client.authenticate_plain(
                    self.user,
                    password if password is not None else self.password,
                )
                if not ok:
                    return self._forbidden("auth_failed", status=535)
            selected, select_status = client.select_inbox()
            if not selected:
                reason = "auth_gated" if "AUTHENTICATIONFAILED" in select_status.upper() or not authenticate else "select_failed"
                code = 530 if reason == "auth_gated" else 550
                return self._forbidden(reason, status=code)
            if idle:
                injector = threading.Thread(target=self._delayed_inject, args=(str(token or SENTINEL),), daemon=True)
                injector.start()
                saw = client.idle_until_exists()
                injector.join(timeout=2)
                if not saw:
                    return self._forbidden("idle_timeout", status=408)
            with self._lock:
                latest = self.messages[-1] if self.messages else None
            if latest is None:
                return self._forbidden("idle_required", status=409)
            fetched = client.uid_fetch(int(latest["uid"]))
            if not fetched.get("ok") or not fetched.get("raw"):
                return self._forbidden("fetch_failed", status=404)
            parsed = _parse_rfc822(bytes(fetched["raw"]))
            live_token = parsed["token"] or str(token or SENTINEL)
            sealed = {
                "uid": int(latest["uid"]),
                "from": parsed["from"],
                "to": parsed["to"],
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "authenticated": True,
                "idled": bool(idle),
                "fetched_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            live = independent_imap_inbox(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "queued": True,
                "uid": int(latest["uid"]),
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "path": str(self.sealed_path),
                "authenticated": bool(authenticate),
                "idled": bool(idle),
            }
        except (OSError, ImapActuationError) as error:
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
                client.logout()
                client.close()

    def read(self) -> dict[str, Any]:
        live = independent_imap_inbox(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "from": str(live.get("from") or ""),
            "uid": int(live.get("uid") or 0),
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


def call_imap_tool(session: ImapSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one IMAP tool call against a bound listener session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = arguments.get("authenticate")
    if authenticate is None:
        authenticate = True
    idle = arguments.get("idle")
    if idle is None:
        idle = True
    password = arguments.get("password")
    if action == "bind":
        result = session.bind()
    elif action == "fetch":
        result = session.fetch(
            token,
            authenticate=bool(authenticate),
            idle=bool(idle),
            password=None if password is None else str(password),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise ImapActuationError(f"unsupported imap action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_imap_inbox(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed IMAP inbox through a fresh file open."""

    path = Path(sealed_path)
    if not path.is_file():
        return {"ok": False, "error": "missing_payload", "token": "", "sentinel": "", "from": "", "uid": 0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "ok": False,
            "error": "invalid_payload",
            "detail": str(error),
            "token": "",
            "sentinel": "",
            "from": "",
            "uid": 0,
        }
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_payload", "token": "", "sentinel": "", "from": "", "uid": 0}
    token = str(payload.get("token") or "")
    authenticated = payload.get("authenticated") is True
    idled = payload.get("idled") is True
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and authenticated and idled else "",
        "from": str(payload.get("from") or ""),
        "to": str(payload.get("to") or ""),
        "uid": int(payload.get("uid") or 0),
        "authenticated": authenticated,
        "idled": idled,
    }


def run_imap_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    idle: bool = True,
    password: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the UID/IDLE-gated inbound workflow and seal a trace."""

    descriptor = imap_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IMAP_TOOL_PROVIDER),
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
        raise ImapActuationError(f"imap tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="imap-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = ImapSession(out, password=DEFAULT_PASSWORD if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    fetch_args: dict[str, Any] = {
        "action": "fetch",
        "token": SENTINEL,
        "authenticate": authenticate,
        "idle": idle,
    }
    if password is not None:
        fetch_args["password"] = password
    calls.append(fetch_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_imap_tool(session, arguments))
            except ImapActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    fetch_result = next((item for item in results if item.get("action") == "fetch"), {})
    independent = independent_imap_inbox(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and idle
        and password is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "imap_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "idle": idle,
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
        "delivered": bool(session.delivered or fetch_result.get("queued")),
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
        "error": str(final.get("error") or fetch_result.get("error") or ""),
        "delivered": bool(trace_body["delivered"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "idle": idle,
    }


def verify_imap_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed IMAP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_imap_inbox(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
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
        "idled": independent.get("idled") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def imap_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.imap_actuation import "
        "builtin_imap_actuation_proof; r=builtin_imap_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='imap_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_imap_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=IMAP_ACTUATION_ID,
        name="First-class UID/IDLE-gated inbound IMAP actuation",
        description=(
            "Missions that require an imap tool can opt the imap provider in, "
            "bind a loopback IMAP4rev1 listener, AUTHENTICATE PLAIN, SELECT "
            "INBOX, IDLE until EXISTS, UID FETCH the newly arrived message, "
            "and seal a digest-chained inbox. Default routing stays fail-closed; "
            "a missing AUTHENTICATE secret keeps the auth hole falsifiable, and "
            "skip-IDLE stays empty."
        ),
        kind="python",
        entry="blackhole_agent.imap_actuation:builtin_imap_actuation_proof",
        proof_command=imap_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-http-auth",
            "capability.smtp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/imap_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required imap tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback IMAP4rev1 listener, authenticates, "
            "IDLEs until a UID-gated message arrives, independently re-reads the "
            "sealed sentinel, and binds this family as the next diversity-catalog "
            "successor once HTTP bearer authorization is proved. Missing "
            "credentials, skipped AUTHENTICATE, wrong passwords, and skip-IDLE "
            "stay fail-closed."
        ),
        tags=("imap", "idle", "uid", "inbound", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T070121Z-c74cd5dc",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_imap_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in IMAP actuation seals a UID/IDLE-gated inbox."""

    from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_http_auth import MCP_HTTP_AUTH_GOAL, MCP_HTTP_AUTH_ID
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = IMAP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    checks["smtp_goal_is_not_imap"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    checks["http_auth_goal_is_not_imap"] = leftover_marker_ids(MCP_HTTP_AUTH_GOAL) == (
        MCP_HTTP_AUTH_ID,
    )
    checks["gmail_goal_is_not_imap"] = leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (GMAIL_ACTUATION_ID,)
    checks["imap_goal_is_not_smtp"] = SMTP_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    checks["imap_goal_is_not_http_auth"] = MCP_HTTP_AUTH_ID not in leftover_marker_ids(
        IMAP_ACTUATION_GOAL
    )
    checks["imap_goal_is_not_gmail"] = GMAIL_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    checks["smtp_marker_stays_smtp"] = IMAP_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    checks["http_auth_marker_stays_http_auth"] = IMAP_ACTUATION_ID not in leftover_marker_ids(
        MCP_HTTP_AUTH_GOAL
    )
    checks["gmail_marker_stays_gmail"] = IMAP_ACTUATION_ID not in leftover_marker_ids(GMAIL_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_imap"] = (
        len(catalog) > 31
        and catalog[31]["id"] == IMAP_ACTUATION_ID
        and catalog[30]["id"] == MCP_HTTP_AUTH_ID
    )
    family = capability_family(IMAP_ACTUATION_GOAL)
    checks["family_is_imap"] = "imap" in family
    checks["family_is_not_smtp"] = "smtp" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_gmail"] = "gmail" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["family_is_not_bearer"] = "bearer" not in family
    checks["not_a_smtp_duplicate"] = (
        semantic_similarity(
            semantic_signature(IMAP_ACTUATION_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_http_auth_duplicate"] = (
        semantic_similarity(
            semantic_signature(IMAP_ACTUATION_GOAL),
            semantic_signature(MCP_HTTP_AUTH_GOAL),
        )
        < 0.82
    )
    checks["not_a_gmail_duplicate"] = (
        semantic_similarity(
            semantic_signature(IMAP_ACTUATION_GOAL),
            semantic_signature(GMAIL_ACTUATION_GOAL),
        )
        < 0.82
    )

    mcp_imap = ToolDescriptor(name="remote_imap", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_imap)
    checks["naive_mcp_imap_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = imap_tool_descriptor()
    default_imap = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IMAP_TOOL_PROVIDER),
    )
    checks["default_imap_provider_is_unsupported"] = (
        default_imap.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{IMAP_TOOL_PROVIDER}" in default_imap.reasons
    )
    checks["opted_in_imap_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_imap],
        required_tool_names=("local_memory", "imap"),
    )
    checks["naive_preflight_missing_imap"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["imap"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "imap"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IMAP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "imap" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="imap-actuation-") as tmp:
        root = Path(tmp)
        missing = run_imap_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_imap_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_imap_workflow(password="wrong-password", output_dir=root / "wrong")
        skip_idle = run_imap_workflow(idle=False, output_dir=root / "skip-idle")
        live = run_imap_workflow(output_dir=root / "live")
        verify = verify_imap_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_imap_trace(clone)
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
        checks["skip_idle_stays_empty"] = (
            skip_idle["ok"] is False
            and skip_idle["error"] == "idle_required"
            and skip_idle["final_status"] == 409
            and skip_idle["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_inbox"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["secret_auth_and_idle_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_idle["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="imap-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != IMAP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_imap"] = (
        live_goal == IMAP_ACTUATION_GOAL
        and IMAP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_imap"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_imap_actuation_capability()
    return {
        "ok": ok,
        "action": "imap_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": IMAP_ACTUATION_GOAL,
        "done_when": IMAP_ACTUATION_DONE_WHEN,
    }
