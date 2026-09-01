"""Drive a first-class webhook tool through an HMAC-gated inbound workflow.

Tool routing already fails missions that require ``webhook``: hosted callback
plugins stay on the unsupported MCP provider, and no first-party webhook
provider is executable. Unbound therefore cannot bind a loopback listener,
verify an X-Hub-Signature-256 delivery, or seal an inbound payload.

This module closes that hole:

- advertise a ``webhook`` provider tool that stays fail-closed until opted in
- drive bind / receive / verify / ack / read against a real loopback HTTP
  listener that records the raw POST body
- keep a missing-secret client so the HMAC hole stays falsifiable
- refuse ack until the delivery signature verifies with hmac.compare_digest
- persist a sealed payload an independent reader can re-open from disk
- bind this family as the next diversity-catalog successor after SQLite
"""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    UNSUPPORTED_TOOL_ROUTE,
    WEBHOOK_TOOL_PROVIDER,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    webhook_tool_descriptor,
)

SCHEMA_VERSION = 1
WEBHOOK_ACTUATION_ID = "capability.webhook-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-webhook"
SENTINEL = "BH-WEBHOOK-OK"
DEFAULT_SECRET = "blackhole-webhook-secret"
DEFAULT_PATH = "/hooks/beacon"
SEALED_NAME = "sealed.json"
SIGNATURE_HEADER = "X-Hub-Signature-256"

WEBHOOK_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WEBHOOK_ACTUATION_ID};"
    f"capability_proved:{WEBHOOK_ACTUATION_ID};"
    "no_skill_route"
)
WEBHOOK_ACTUATION_GOAL = (
    "Repair HMAC-gated inbound webhook actuation: hosted callback tools remain "
    "unsupported so an unsigned callback cannot be verified and a sealed webhook "
    "payload cannot be produced. A missing hmac secret stays forbidden; fail-closed "
    "routing never opts the webhook provider in."
)


class WebhookActuationError(RuntimeError):
    """Raised when the webhook session or listener fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def sign_webhook(secret: str, body: bytes) -> str:
    """Return a GitHub-style ``sha256=`` hex HMAC over the raw POST body."""

    digest = hmac.new(str(secret).encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class _WebhookHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], session: WebhookSession) -> None:
        self.session = session
        super().__init__(address, handler)


class _WebhookHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib
        session: WebhookSession = self.server.session  # type: ignore[attr-defined]
        if self.path.rstrip("/") != DEFAULT_PATH:
            self.send_error(404, "not a webhook endpoint")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b""
        signature = self.headers.get(SIGNATURE_HEADER) or ""
        delivery_id = session.record_delivery(raw, signature)
        body = _canonical({"accepted": True, "delivery_id": delivery_id}).encode("utf-8")
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WebhookSession:
    """Secret-gated loopback listener: bind, receive, verify, ack, read."""

    def __init__(self, output_dir: Path, *, secret: str = DEFAULT_SECRET) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.secret = str(secret or "")
        self.url: str | None = None
        self.server: _WebhookHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.last_raw: bytes | None = None
        self.last_signature = ""
        self.last_delivery_id = ""
        self.delivery_count = 0
        self.verified = False
        self.acked = False
        self.history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def _forbidden(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 403,
            "error": reason,
            "token": "",
            "sentinel": "",
            "verified": self.verified,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 409,
            "error": reason,
            "token": "",
            "sentinel": "",
            "verified": self.verified,
        }

    def record_delivery(self, raw: bytes, signature: str) -> str:
        with self._lock:
            self.delivery_count += 1
            self.last_raw = bytes(raw)
            self.last_signature = str(signature or "")
            self.last_delivery_id = f"del-{self.delivery_count}"
            self.verified = False
            self.acked = False
            return self.last_delivery_id

    def bind(self) -> dict[str, Any]:
        if not self.secret:
            return self._forbidden("missing_secret")
        if self.server is not None:
            return {
                "ok": True,
                "status": 200,
                "url": self.url or "",
                "reused": True,
            }
        server = _WebhookHTTPServer(("127.0.0.1", 0), _WebhookHandler, self)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        self.server = server
        self.thread = thread
        self.url = f"http://{host}:{int(port)}{DEFAULT_PATH}"
        return {
            "ok": True,
            "status": 200,
            "url": self.url,
            "path": DEFAULT_PATH,
            "reused": False,
        }

    def receive(self, token: str = SENTINEL, *, signed: bool = True) -> dict[str, Any]:
        if self.url is None:
            return self._conflict("not_bound")
        payload = {"event": "beacon", "token": str(token or SENTINEL)}
        body = _canonical(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if signed:
            if not self.secret:
                return self._forbidden("missing_secret")
            headers[SIGNATURE_HEADER] = sign_webhook(self.secret, body)
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=5) as response:
                status = int(response.status)
                raw = response.read()
        except urllib.error.HTTPError as error:
            return {
                "ok": False,
                "status": int(error.code),
                "error": "http_error",
                "detail": str(error),
                "token": str(token or SENTINEL),
                "sentinel": "",
            }
        except urllib.error.URLError as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error.reason),
                "token": str(token or SENTINEL),
                "sentinel": "",
            }
        try:
            accepted = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            accepted = {}
        return {
            "ok": status == 202,
            "status": status,
            "accepted": bool(accepted.get("accepted")),
            "delivery_id": str(accepted.get("delivery_id") or self.last_delivery_id),
            "signed": bool(signed),
            "bytes": len(body),
            "token": str(token or SENTINEL),
        }

    def verify(self) -> dict[str, Any]:
        if self.url is None:
            return self._conflict("not_bound")
        if self.last_raw is None:
            return self._conflict("no_delivery")
        if not self.secret:
            return self._forbidden("missing_secret")
        expected = sign_webhook(self.secret, self.last_raw)
        provided = str(self.last_signature or "")
        try:
            matched = bool(provided) and hmac.compare_digest(expected, provided)
        except (TypeError, ValueError):
            matched = False
        if not matched:
            self.verified = False
            return self._forbidden("signature_gated")
        self.verified = True
        token = ""
        try:
            parsed = json.loads(self.last_raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            token = str(parsed.get("token") or "")
        return {
            "ok": True,
            "status": 200,
            "verified": True,
            "delivery_id": self.last_delivery_id,
            "signature": expected,
            "token": token,
        }

    def ack(self) -> dict[str, Any]:
        if not self.verified:
            return self._forbidden("signature_gated")
        if self.last_raw is None:
            return self._conflict("no_delivery")
        try:
            parsed = json.loads(self.last_raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {}
        token = str(parsed.get("token") or "") if isinstance(parsed, dict) else ""
        sealed = {
            "delivery_id": self.last_delivery_id,
            "token": token,
            "sentinel": SENTINEL if token == SENTINEL else "",
            "signature": str(self.last_signature or ""),
            "verified": True,
            "acked_at": utc_now_iso(),
        }
        self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
        self.acked = True
        return {
            "ok": True,
            "status": 200,
            "acked": True,
            "token": token,
            "sentinel": sealed["sentinel"],
            "path": str(self.sealed_path),
            "delivery_id": self.last_delivery_id,
        }

    def read(self) -> dict[str, Any]:
        live = independent_webhook_payload(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "delivery_id": str(live.get("delivery_id") or ""),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        server = self.server
        thread = self.thread
        self.server = None
        self.thread = None
        self.url = None
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
            thread.join(timeout=5)
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_webhook_tool(session: WebhookSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one webhook tool call against a bound listener session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    signed = arguments.get("signed")
    if signed is None:
        signed = True
    if action == "bind":
        result = session.bind()
    elif action == "receive":
        result = session.receive(token, signed=bool(signed))
    elif action == "verify":
        result = session.verify()
    elif action == "ack":
        result = session.ack()
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise WebhookActuationError(f"unsupported webhook action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_webhook_payload(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed webhook payload through a fresh file open."""

    path = Path(sealed_path)
    if not path.is_file():
        return {"ok": False, "error": "missing_payload", "token": "", "sentinel": "", "delivery_id": ""}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "ok": False,
            "error": "invalid_payload",
            "detail": str(error),
            "token": "",
            "sentinel": "",
            "delivery_id": "",
        }
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_payload", "token": "", "sentinel": "", "delivery_id": ""}
    token = str(payload.get("token") or "")
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and payload.get("verified") is True else "",
        "delivery_id": str(payload.get("delivery_id") or ""),
        "verified": payload.get("verified") is True,
        "signature": str(payload.get("signature") or ""),
    }


def run_webhook_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    signed: bool = True,
    skip_verify: bool = False,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the HMAC-gated inbound workflow and seal a trace."""

    descriptor = webhook_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBHOOK_TOOL_PROVIDER),
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
        raise WebhookActuationError(f"webhook tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="webhook-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = WebhookSession(out, secret=DEFAULT_SECRET if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append({"action": "receive", "token": SENTINEL, "signed": signed})
    if not skip_verify:
        calls.append({"action": "verify"})
    calls.extend([{"action": "ack"}, {"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_webhook_tool(session, arguments))
            except WebhookActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    ack_result = next((item for item in results if item.get("action") == "ack"), {})
    verify_result = next((item for item in results if item.get("action") == "verify"), {})
    independent = independent_webhook_payload(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and signed
        and not skip_verify
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "webhook_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "signed": signed,
        "skip_verify": skip_verify,
        "sealed_path": str(session.sealed_path),
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "independent": independent,
        "independent_digest": _digest(independent),
        "sentinel": sentinel,
        "verified": bool(verify_result.get("verified") or session.verified),
        "acked": bool(ack_result.get("acked") or session.acked),
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
        "error": str(final.get("error") or ack_result.get("error") or verify_result.get("error") or ""),
        "verified": bool(trace_body["verified"]),
        "acked": bool(trace_body["acked"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "signed": signed,
        "skip_verify": skip_verify,
    }


def verify_webhook_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed webhook trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_webhook_payload(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
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
        "verified": trace.get("verified") is True,
        "acked": trace.get("acked") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def webhook_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.webhook_actuation import "
        "builtin_webhook_actuation_proof; r=builtin_webhook_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='webhook_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_webhook_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=WEBHOOK_ACTUATION_ID,
        name="First-class HMAC-gated inbound webhook actuation",
        description=(
            "Missions that require a webhook tool can opt the webhook provider in, "
            "bind a loopback HTTP listener, verify an X-Hub-Signature-256 delivery, "
            "and seal a digest-chained inbound payload. Default routing stays "
            "fail-closed; a missing HMAC secret keeps the auth hole falsifiable, "
            "and ack stays signature-gated."
        ),
        kind="python",
        entry="blackhole_agent.webhook_actuation:builtin_webhook_actuation_proof",
        proof_command=webhook_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.sqlite-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/webhook_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required webhook tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback HTTP listener, verifies an HMAC-SHA256 "
            "delivery, independently re-reads the sealed sentinel, and binds this "
            "family as the next diversity-catalog successor once SQLite actuation "
            "is proved. Missing secrets, unsigned deliveries, and unverified acks "
            "stay fail-closed."
        ),
        tags=("webhook", "hmac", "inbound", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T042613Z-97951a74",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_webhook_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in webhook actuation seals an HMAC-gated payload."""

    from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mission_selection import capability_family
    from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = WEBHOOK_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (
        WEBHOOK_ACTUATION_ID,
    )
    checks["sqlite_goal_is_not_webhook"] = leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (
        SQLITE_ACTUATION_ID,
    )
    checks["gmail_goal_is_not_webhook"] = leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (
        GMAIL_ACTUATION_ID,
    )
    checks["webhook_goal_is_not_sqlite"] = SQLITE_ACTUATION_ID not in leftover_marker_ids(
        WEBHOOK_ACTUATION_GOAL
    )
    checks["webhook_goal_is_not_gmail"] = GMAIL_ACTUATION_ID not in leftover_marker_ids(
        WEBHOOK_ACTUATION_GOAL
    )
    checks["sqlite_marker_stays_sqlite"] = WEBHOOK_ACTUATION_ID not in leftover_marker_ids(
        SQLITE_ACTUATION_GOAL
    )
    checks["gmail_marker_stays_gmail"] = WEBHOOK_ACTUATION_ID not in leftover_marker_ids(
        GMAIL_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_webhook"] = (
        len(catalog) > 26
        and catalog[26]["id"] == WEBHOOK_ACTUATION_ID
        and catalog[25]["id"] == SQLITE_ACTUATION_ID
    )
    family = capability_family(WEBHOOK_ACTUATION_GOAL)
    checks["family_is_webhook"] = "webhook" in family
    checks["family_is_not_sqlite"] = "sqlite" not in family
    checks["family_is_not_git_publication"] = "git-publication" not in family
    checks["family_is_not_browser"] = "browser" not in family
    checks["family_is_not_timeout"] = "timeout" not in family

    mcp_webhook = ToolDescriptor(name="remote_webhook", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_webhook)
    checks["naive_mcp_webhook_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = webhook_tool_descriptor()
    default_webhook = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBHOOK_TOOL_PROVIDER),
    )
    checks["default_webhook_provider_is_unsupported"] = (
        default_webhook.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{WEBHOOK_TOOL_PROVIDER}" in default_webhook.reasons
    )
    checks["opted_in_webhook_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_webhook],
        required_tool_names=("local_memory", "webhook"),
    )
    checks["naive_preflight_missing_webhook"] = (
        naive_preflight["ok"] is False
        and naive_preflight["missing_required_tool_names"] == ["webhook"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "webhook"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBHOOK_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "webhook" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="webhook-actuation-") as tmp:
        root = Path(tmp)
        missing = run_webhook_workflow(
            with_secret=False,
            output_dir=root / "missing",
        )
        unsigned = run_webhook_workflow(signed=False, output_dir=root / "unsigned")
        unverified = run_webhook_workflow(skip_verify=True, output_dir=root / "unverified")
        live = run_webhook_workflow(output_dir=root / "live")
        verify = verify_webhook_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_webhook_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unsigned_delivery_is_forbidden"] = (
            unsigned["ok"] is False
            and unsigned["final_status"] == 403
            and unsigned["error"] == "signature_gated"
            and unsigned["verified"] is False
        )
        checks["unverified_ack_is_forbidden"] = (
            unverified["ok"] is False
            and unverified["sentinel"] == ""
            and unverified["independent_sentinel"] == ""
            and unverified["acked"] is False
            and unverified["payload_exists"] is False
            and unverified["error"] == "signature_gated"
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_payload"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["secret_signature_and_verify_are_required"] = (
            missing["ok"] is False
            and unsigned["ok"] is False
            and unverified["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="webhook-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != WEBHOOK_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_webhook"] = (
        live_goal == WEBHOOK_ACTUATION_GOAL
        and WEBHOOK_ACTUATION_ID in live_done
        and live_source == "genesis_bind_webhook"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_webhook_actuation_capability()
    return {
        "ok": ok,
        "action": "webhook_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": WEBHOOK_ACTUATION_GOAL,
        "done_when": WEBHOOK_ACTUATION_DONE_WHEN,
    }
