"""Drive a first-class SMTP tool through an envelope-gated outbound workflow.

Tool routing already fails missions that require ``smtp``: hosted mail-transport
plugins stay on the unsupported MCP provider, and no first-party SMTP
provider is executable. Unbound therefore cannot AUTH, speak MAIL FROM /
RCPT TO / DATA, or seal a delivered mailbox.

This module closes that hole:

- advertise an ``smtp`` provider tool that stays fail-closed until opted in
- drive bind / send / read against a real loopback SMTP listener
- keep a missing-credential client so the LOGIN hole stays falsifiable
- refuse MAIL FROM until AUTH PLAIN (or LOGIN) succeeds
- persist a sealed mailbox an independent reader can re-open from disk
- bind this family as the next diversity-catalog successor after tools/list_changed
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import smtplib
import socketserver
import tempfile
import threading
from email.message import EmailMessage
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
    SMTP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    smtp_tool_descriptor,
)

SCHEMA_VERSION = 1
SMTP_ACTUATION_ID = "capability.smtp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-smtp"
SENTINEL = "BH-SMTP-OK"
DEFAULT_USER = "blackhole"
DEFAULT_PASSWORD = "blackhole-smtp-secret"
DEFAULT_FROM = "beacon@blackhole.invalid"
DEFAULT_TO = "operator@blackhole.invalid"
SEALED_NAME = "sealed.json"
TOKEN_HEADER = "X-Blackhole-Token"

SMTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SMTP_ACTUATION_ID};"
    f"capability_proved:{SMTP_ACTUATION_ID};"
    "no_skill_route"
)
SMTP_ACTUATION_GOAL = (
    "Repair SMTP envelope-gated outbound delivery: hosted mail-transport tools "
    "remain unsupported so a MAIL FROM/RCPT TO/DATA transaction cannot land and "
    "a sealed mailbox cannot be produced. A missing LOGIN credential stays "
    "forbidden; fail-closed routing never opts the smtp provider in."
)


class SmtpActuationError(RuntimeError):
    """Raised when the SMTP session or listener fixture misbehaves."""


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


class _SmtpTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(self, address: tuple[str, int], handler: type[socketserver.BaseRequestHandler], session: SmtpSession) -> None:
        self.session = session
        super().__init__(address, handler)


class _SmtpHandler(socketserver.StreamRequestHandler):
    timeout = 8

    def _send(self, line: str) -> None:
        self.wfile.write(f"{line}\r\n".encode("ascii", errors="replace"))
        self.wfile.flush()

    def _readline(self) -> str | None:
        raw = self.rfile.readline()
        if not raw:
            return None
        return raw.decode("utf-8", errors="replace").rstrip("\r\n")

    def handle(self) -> None:
        session: SmtpSession = self.server.session  # type: ignore[attr-defined]
        authed = False
        mail_from = ""
        rcpt: list[str] = []
        self._send("220 blackhole ESMTP")
        while True:
            line = self._readline()
            if line is None:
                return
            verb, _, rest = line.partition(" ")
            command = verb.upper()
            argument = rest.strip()
            if command == "EHLO":
                self._send("250-blackhole")
                self._send("250-AUTH PLAIN LOGIN")
                self._send("250 OK")
            elif command == "HELO":
                self._send("250 blackhole")
            elif command == "AUTH":
                authed = self._auth(session, argument)
            elif command == "MAIL":
                if not authed:
                    self._send("530 5.7.0 Authentication required")
                    continue
                mail_from = argument.split(":", 1)[-1].strip().strip("<>")
                rcpt = []
                self._send("250 2.1.0 OK")
            elif command == "RCPT":
                if not authed:
                    self._send("530 5.7.0 Authentication required")
                    continue
                if not mail_from:
                    self._send("503 5.5.1 MAIL first")
                    continue
                rcpt.append(argument.split(":", 1)[-1].strip().strip("<>"))
                self._send("250 2.1.5 OK")
            elif command == "DATA":
                if not authed:
                    self._send("530 5.7.0 Authentication required")
                    continue
                if not mail_from or not rcpt:
                    self._send("503 5.5.1 Need MAIL and RCPT")
                    continue
                self._send("354 End data with <CR><LF>.<CR><LF>")
                chunks: list[bytes] = []
                while True:
                    raw = self.rfile.readline()
                    if not raw:
                        return
                    if raw in (b".\r\n", b".\n"):
                        break
                    if raw.startswith(b"."):
                        raw = raw[1:]
                    chunks.append(raw)
                parsed = _parse_rfc822(b"".join(chunks))
                token = parsed["token"]
                session.accept_message(mail_from, rcpt, token)
                mail_from = ""
                rcpt = []
                self._send("250 2.0.0 Queued")
            elif command == "RSET":
                mail_from = ""
                rcpt = []
                self._send("250 2.0.0 OK")
            elif command == "NOOP":
                self._send("250 2.0.0 OK")
            elif command == "QUIT":
                self._send("221 2.0.0 Bye")
                return
            else:
                self._send("502 5.5.1 Command not implemented")

    def _auth(self, session: SmtpSession, argument: str) -> bool:
        mechanism, _, blob = argument.partition(" ")
        kind = mechanism.upper()
        if kind == "PLAIN":
            if not blob:
                self._send("334 ")
                follow = self._readline()
                if follow is None:
                    return False
                blob = follow
            user, password = _decode_auth_blob(blob)
            if session.credentials_match(user, password):
                self._send("235 2.7.0 Authentication successful")
                return True
            self._send("535 5.7.8 Authentication failed")
            return False
        if kind == "LOGIN":
            if not blob:
                self._send("334 VXNlcm5hbWU6")
                follow = self._readline()
                if follow is None:
                    return False
                user_blob = follow
            else:
                user_blob = blob
            self._send("334 UGFzc3dvcmQ6")
            pass_blob = self._readline()
            if pass_blob is None:
                return False
            try:
                user = base64.b64decode(user_blob.encode("ascii"), validate=False).decode("utf-8", errors="replace")
                password = base64.b64decode(pass_blob.encode("ascii"), validate=False).decode("utf-8", errors="replace")
            except (ValueError, UnicodeError):
                self._send("535 5.7.8 Authentication failed")
                return False
            if session.credentials_match(user, password):
                self._send("235 2.7.0 Authentication successful")
                return True
            self._send("535 5.7.8 Authentication failed")
            return False
        self._send("504 5.5.4 Unknown AUTH mechanism")
        return False


class SmtpSession:
    """Credential-gated loopback SMTP listener: bind, send, read."""

    def __init__(self, output_dir: Path, *, password: str = DEFAULT_PASSWORD, user: str = DEFAULT_USER) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.user = str(user or "")
        self.password = str(password or "")
        self.host: str | None = None
        self.port: int | None = None
        self.server: _SmtpTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.delivered = False
        self.last_token = ""
        self.history: list[dict[str, Any]] = []
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

    def accept_message(self, mail_from: str, rcpt: list[str], token: str) -> None:
        with self._lock:
            sealed = {
                "from": mail_from,
                "to": list(rcpt),
                "token": token,
                "sentinel": SENTINEL if token == SENTINEL else "",
                "authenticated": True,
                "queued_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = token

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
        server = _SmtpTCPServer(("127.0.0.1", 0), _SmtpHandler, self)
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

    def send(
        self,
        token: str = SENTINEL,
        *,
        authenticate: bool = True,
        password: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.password:
            return self._forbidden("missing_secret")
        message = EmailMessage()
        message["From"] = DEFAULT_FROM
        message["To"] = DEFAULT_TO
        message["Subject"] = "blackhole-smtp-beacon"
        message[TOKEN_HEADER] = str(token or SENTINEL)
        message.set_content(str(token or SENTINEL))
        try:
            with smtplib.SMTP(self.host, int(self.port), timeout=5) as client:
                client.ehlo()
                if authenticate:
                    try:
                        client.login(self.user, password if password is not None else self.password)
                    except smtplib.SMTPAuthenticationError:
                        return self._forbidden("auth_failed", status=535)
                    except smtplib.SMTPException as error:
                        return {
                            "ok": False,
                            "status": 535,
                            "error": "auth_failed",
                            "detail": str(error),
                            "token": str(token or SENTINEL),
                            "sentinel": "",
                        }
                try:
                    refused = client.send_message(message)
                except smtplib.SMTPSenderRefused as error:
                    code = int(error.smtp_code or 530)
                    reason = "auth_gated" if code == 530 else "sender_refused"
                    return self._forbidden(reason, status=code)
                except smtplib.SMTPRecipientsRefused:
                    return self._forbidden("rcpt_gated", status=550)
                except smtplib.SMTPDataError as error:
                    return self._forbidden("data_gated", status=int(error.smtp_code or 554))
        except (OSError, smtplib.SMTPException) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error),
                "token": str(token or SENTINEL),
                "sentinel": "",
            }
        if refused:
            return self._forbidden("rcpt_gated", status=550)
        live = independent_smtp_mailbox(self.sealed_path)
        return {
            "ok": True,
            "status": 250,
            "queued": True,
            "token": str(token or SENTINEL),
            "sentinel": str(live.get("sentinel") or ""),
            "path": str(self.sealed_path),
            "authenticated": bool(authenticate),
        }

    def read(self) -> dict[str, Any]:
        live = independent_smtp_mailbox(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "from": str(live.get("from") or ""),
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


def call_smtp_tool(session: SmtpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one SMTP tool call against a bound listener session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = arguments.get("authenticate")
    if authenticate is None:
        authenticate = True
    password = arguments.get("password")
    if action == "bind":
        result = session.bind()
    elif action == "send":
        result = session.send(
            token,
            authenticate=bool(authenticate),
            password=None if password is None else str(password),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SmtpActuationError(f"unsupported smtp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_smtp_mailbox(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed SMTP mailbox through a fresh file open."""

    path = Path(sealed_path)
    if not path.is_file():
        return {"ok": False, "error": "missing_payload", "token": "", "sentinel": "", "from": ""}
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
        }
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_payload", "token": "", "sentinel": "", "from": ""}
    token = str(payload.get("token") or "")
    authenticated = payload.get("authenticated") is True
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and authenticated else "",
        "from": str(payload.get("from") or ""),
        "to": list(payload.get("to") or []),
        "authenticated": authenticated,
    }


def run_smtp_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    password: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the envelope-gated outbound workflow and seal a trace."""

    descriptor = smtp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SMTP_TOOL_PROVIDER),
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
        raise SmtpActuationError(f"smtp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="smtp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SmtpSession(out, password=DEFAULT_PASSWORD if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    send_args: dict[str, Any] = {"action": "send", "token": SENTINEL, "authenticate": authenticate}
    if password is not None:
        send_args["password"] = password
    calls.append(send_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_smtp_tool(session, arguments))
            except SmtpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    send_result = next((item for item in results if item.get("action") == "send"), {})
    independent = independent_smtp_mailbox(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and password is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "smtp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
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
        "delivered": bool(session.delivered or send_result.get("queued")),
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
        "error": str(final.get("error") or send_result.get("error") or ""),
        "delivered": bool(trace_body["delivered"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
    }


def verify_smtp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed SMTP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_smtp_mailbox(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
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
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def smtp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.smtp_actuation import "
        "builtin_smtp_actuation_proof; r=builtin_smtp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='smtp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_smtp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SMTP_ACTUATION_ID,
        name="First-class envelope-gated outbound SMTP actuation",
        description=(
            "Missions that require an smtp tool can opt the smtp provider in, "
            "bind a loopback SMTP listener, AUTH PLAIN, land a MAIL FROM / "
            "RCPT TO / DATA transaction, and seal a digest-chained mailbox. "
            "Default routing stays fail-closed; a missing LOGIN credential keeps "
            "the auth hole falsifiable, and unauthenticated MAIL FROM stays gated."
        ),
        kind="python",
        entry="blackhole_agent.smtp_actuation:builtin_smtp_actuation_proof",
        proof_command=smtp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-tools-list-changed",
        ),
        behavior_paths=(
            "src/blackhole_agent/smtp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required smtp tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback SMTP listener, authenticates, lands "
            "an envelope-gated message, independently re-reads the sealed sentinel, "
            "and binds this family as the next diversity-catalog successor once "
            "tools/list_changed is proved. Missing credentials, skipped AUTH, "
            "and wrong passwords stay fail-closed."
        ),
        tags=("smtp", "envelope", "outbound", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T055411Z-3030f77f",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_smtp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in SMTP actuation seals an envelope-gated mailbox."""

    from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_tools_list_changed import (
        MCP_TOOLS_CHANGED_GOAL,
        MCP_TOOLS_CHANGED_ID,
    )
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = SMTP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    checks["tools_changed_goal_is_not_smtp"] = leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL) == (
        MCP_TOOLS_CHANGED_ID,
    )
    checks["webhook_goal_is_not_smtp"] = leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (
        WEBHOOK_ACTUATION_ID,
    )
    checks["gmail_goal_is_not_smtp"] = leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (
        GMAIL_ACTUATION_ID,
    )
    checks["smtp_goal_is_not_tools_changed"] = MCP_TOOLS_CHANGED_ID not in leftover_marker_ids(
        SMTP_ACTUATION_GOAL
    )
    checks["smtp_goal_is_not_webhook"] = WEBHOOK_ACTUATION_ID not in leftover_marker_ids(
        SMTP_ACTUATION_GOAL
    )
    checks["smtp_goal_is_not_gmail"] = GMAIL_ACTUATION_ID not in leftover_marker_ids(
        SMTP_ACTUATION_GOAL
    )
    checks["tools_changed_marker_stays_tools_changed"] = SMTP_ACTUATION_ID not in leftover_marker_ids(
        MCP_TOOLS_CHANGED_GOAL
    )
    checks["webhook_marker_stays_webhook"] = SMTP_ACTUATION_ID not in leftover_marker_ids(
        WEBHOOK_ACTUATION_GOAL
    )
    checks["gmail_marker_stays_gmail"] = SMTP_ACTUATION_ID not in leftover_marker_ids(
        GMAIL_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_smtp"] = (
        len(catalog) > 29
        and catalog[29]["id"] == SMTP_ACTUATION_ID
        and catalog[28]["id"] == MCP_TOOLS_CHANGED_ID
    )
    family = capability_family(SMTP_ACTUATION_GOAL)
    checks["family_is_smtp"] = "smtp" in family
    checks["family_is_not_webhook"] = "webhook" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_gmail"] = "gmail" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["not_a_webhook_duplicate"] = (
        semantic_similarity(
            semantic_signature(SMTP_ACTUATION_GOAL),
            semantic_signature(WEBHOOK_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_gmail_duplicate"] = (
        semantic_similarity(
            semantic_signature(SMTP_ACTUATION_GOAL),
            semantic_signature(GMAIL_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_tools_changed_duplicate"] = (
        semantic_similarity(
            semantic_signature(SMTP_ACTUATION_GOAL),
            semantic_signature(MCP_TOOLS_CHANGED_GOAL),
        )
        < 0.82
    )

    mcp_smtp = ToolDescriptor(name="remote_smtp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_smtp)
    checks["naive_mcp_smtp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = smtp_tool_descriptor()
    default_smtp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SMTP_TOOL_PROVIDER),
    )
    checks["default_smtp_provider_is_unsupported"] = (
        default_smtp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SMTP_TOOL_PROVIDER}" in default_smtp.reasons
    )
    checks["opted_in_smtp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_smtp],
        required_tool_names=("local_memory", "smtp"),
    )
    checks["naive_preflight_missing_smtp"] = (
        naive_preflight["ok"] is False
        and naive_preflight["missing_required_tool_names"] == ["smtp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "smtp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SMTP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "smtp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="smtp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_smtp_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_smtp_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_smtp_workflow(password="wrong-password", output_dir=root / "wrong")
        live = run_smtp_workflow(output_dir=root / "live")
        verify = verify_smtp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_smtp_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unauthenticated_mail_from_is_forbidden"] = (
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
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_mailbox"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["secret_auth_and_envelope_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="smtp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SMTP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_smtp"] = (
        live_goal == SMTP_ACTUATION_GOAL
        and SMTP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_smtp"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_smtp_actuation_capability()
    return {
        "ok": ok,
        "action": "smtp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SMTP_ACTUATION_GOAL,
        "done_when": SMTP_ACTUATION_DONE_WHEN,
    }
