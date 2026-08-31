"""Drive a first-class browser tool through a form-driven local web workflow.

Tool routing already fails missions that require ``browser``: the only
descriptor in preflight fixtures is an MCP ``remote_browser`` whose provider
is unsupported by default, and the hosted browser plugin never stays live.
Unbound therefore cannot execute or seal a cookie-gated web workflow.

This module closes that hole:

- advertise a ``browser`` provider tool that stays fail-closed until opted in
- drive navigate / click / type / submit against a local fixture app
- keep a no-cookie client so the session hole stays falsifiable
- seal a digest-chained actuation trace
- bind this family as the next diversity-catalog successor
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import json
import re
import shutil
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from html import unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

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
    BROWSER_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    browser_tool_descriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
BROWSER_ACTUATION_ID = "capability.browser-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-browser"
SENTINEL = "BH-BROWSER-OK"
SESSION_COOKIE = "bh_session"
SESSION_VALUE = "ok"
DEFAULT_NOTE = "sealed-note"

BROWSER_ACTUATION_DONE_WHEN = (
    f"capability_exists:{BROWSER_ACTUATION_ID};"
    f"capability_proved:{BROWSER_ACTUATION_ID};"
    "no_skill_route"
)
BROWSER_ACTUATION_GOAL = (
    "Repair first-class browser actuation: missions that require a browser "
    "tool fail preflight because the only browser descriptor is an unsupported "
    "MCP provider, so a form-driven web workflow cannot be executed or sealed."
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_LINK_RE = re.compile(
    r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_FORM_RE = re.compile(
    r'<form\b([^>]*)>(.*?)</form>',
    re.IGNORECASE | re.DOTALL,
)
_ATTR_RE = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"')
_INPUT_RE = re.compile(r"<input\b([^>]*)/?>", re.IGNORECASE)
_ID_RE = re.compile(
    r'<([a-z0-9]+)\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</\1>',
    re.IGNORECASE | re.DOTALL,
)


class BrowserActuationError(RuntimeError):
    """Raised when the browser session or fixture app misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _visible_text(html: str) -> str:
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", html or ""))).strip()


def _attrs(blob: str) -> dict[str, str]:
    return {key.lower(): value for key, value in _ATTR_RE.findall(blob or "")}


def parse_links(html: str) -> list[tuple[str, str]]:
    return [
        (href, _visible_text(label))
        for href, label in _LINK_RE.findall(html or "")
    ]


def parse_forms(html: str) -> list[dict[str, Any]]:
    forms: list[dict[str, Any]] = []
    for header, body in _FORM_RE.findall(html or ""):
        attrs = _attrs(header)
        fields: dict[str, str] = {}
        for raw in _INPUT_RE.findall(body):
            item = _attrs(raw)
            name = str(item.get("name") or "").strip()
            if name:
                fields[name] = str(item.get("value") or "")
        forms.append(
            {
                "action": str(attrs.get("action") or ""),
                "method": str(attrs.get("method") or "get").upper(),
                "fields": fields,
            }
        )
    return forms


def element_text(html: str, element_id: str) -> str:
    for _tag, found_id, inner in _ID_RE.findall(html or ""):
        if found_id == element_id:
            return _visible_text(inner)
    return ""


@dataclass
class BrowserPage:
    url: str
    html: str
    status: int

    def text(self) -> str:
        return _visible_text(self.html)

    def element(self, element_id: str) -> str:
        return element_text(self.html, element_id)


class BrowserSession:
    """Cookie-aware loopback browser: navigate, click, type, submit."""

    def __init__(self, *, send_cookies: bool = True, timeout_seconds: float = 5.0) -> None:
        self.send_cookies = bool(send_cookies)
        self.timeout_seconds = float(timeout_seconds)
        self.jar = http.cookiejar.CookieJar()
        handlers = [ProxyHandler({})]
        if self.send_cookies:
            handlers.append(HTTPCookieProcessor(self.jar))
        self.opener = build_opener(*handlers)
        self.page: BrowserPage | None = None
        self.fields: dict[str, str] = {}
        self.history: list[dict[str, Any]] = []

    def goto(self, url: str) -> BrowserPage:
        return self._open("GET", url)

    def click(self, label: str) -> BrowserPage:
        if self.page is None:
            raise BrowserActuationError("click requires a loaded page")
        wanted = str(label or "").strip()
        for href, text in parse_links(self.page.html):
            if text == wanted:
                return self.goto(urljoin(self.page.url, href))
        raise BrowserActuationError(f"no link labelled {wanted!r}")

    def fill(self, name: str, value: str) -> None:
        self.fields[str(name)] = str(value)

    def submit(self) -> BrowserPage:
        if self.page is None:
            raise BrowserActuationError("submit requires a loaded page")
        forms = parse_forms(self.page.html)
        if not forms:
            raise BrowserActuationError("no form on the current page")
        form = forms[0]
        payload = {**form["fields"], **self.fields}
        target = urljoin(self.page.url, str(form["action"] or self.page.url))
        method = str(form["method"] or "GET").upper()
        if method == "GET":
            joined = target + ("&" if "?" in target else "?") + urlencode(payload)
            return self._open("GET", joined)
        return self._open("POST", target, urlencode(payload).encode("utf-8"))

    def snapshot(self) -> str:
        if self.page is None:
            return ""
        return self.page.text()

    def _open(self, method: str, url: str, data: bytes | None = None) -> BrowserPage:
        request = Request(url, data=data, method=method)
        if method == "POST":
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                page = BrowserPage(url=str(response.geturl()), html=body, status=int(response.status))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            page = BrowserPage(url=str(error.geturl() or url), html=body, status=int(error.code))
        except URLError as error:
            raise BrowserActuationError(f"browser request failed: {error}") from error
        self.page = page
        self.fields = {}
        self.history.append({"method": method, "url": url, "status": page.status, "final_url": page.url})
        return page


class _FixtureState:
    def __init__(self) -> None:
        self.notes: list[str] = []


class _FixtureHandler(BaseHTTPRequestHandler):
    server: "_FixtureServer"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _authed(self) -> bool:
        cookie = str(self.headers.get("Cookie") or "")
        return f"{SESSION_COOKIE}={SESSION_VALUE}" in cookie

    def _send(self, status: int, html: str, *, headers: list[tuple[str, str]] | None = None) -> None:
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        path = str(urljoin("/", self.path).split("?", 1)[0])
        if path in {"/", "/index.html"}:
            self._send(
                200,
                "<html><body><h1>Portal</h1><p id=\"status\">anonymous</p>"
                "<a href=\"/login\">Sign in</a></body></html>",
            )
            return
        if path == "/login":
            self._send(
                200,
                "<html><body><h1>Unlock</h1>"
                "<form action=\"/login\" method=\"post\">"
                "<input name=\"token\" id=\"token\" />"
                "<button type=\"submit\">Unlock</button>"
                "</form></body></html>",
            )
            return
        if path == "/dashboard":
            if not self._authed():
                self._send(403, "<html><body><p id=\"status\">forbidden</p></body></html>")
                return
            self._send(200, _dashboard_html())
            return
        self._send(404, "<html><body><p id=\"status\">missing</p></body></html>")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        fields = {key: (values[-1] if values else "") for key, values in parse_qs(raw.decode("utf-8")).items()}
        path = str(urljoin("/", self.path).split("?", 1)[0])
        if path == "/login":
            if str(fields.get("token") or "") != UNLOCK_TOKEN:
                self._send(
                    200,
                    "<html><body><p id=\"status\">denied</p>"
                    "<form action=\"/login\" method=\"post\">"
                    "<input name=\"token\" id=\"token\" />"
                    "<button type=\"submit\">Unlock</button>"
                    "</form></body></html>",
                )
                return
            self.send_response(303)
            self.send_header("Location", "/dashboard")
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={SESSION_VALUE}; Path=/; HttpOnly")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/echo":
            if not self._authed():
                self._send(403, "<html><body><p id=\"status\">forbidden</p></body></html>")
                return
            note = str(fields.get("note") or "")
            self.server.state.notes.append(note)
            self._send(
                200,
                "<html><body>"
                f"<p id=\"echo\">{note}</p>"
                f"<p id=\"sentinel\">{SENTINEL}</p>"
                "</body></html>",
            )
            return
        self._send(404, "<html><body><p id=\"status\">missing</p></body></html>")


def _dashboard_html() -> str:
    return (
        "<html><body><h1>Dashboard</h1>"
        f"<p id=\"sentinel\">{SENTINEL}</p>"
        "<form action=\"/echo\" method=\"post\">"
        "<input name=\"note\" id=\"note\" />"
        "<button type=\"submit\">Save</button>"
        "</form></body></html>"
    )


class _FixtureServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(address, handler)
        self.state = _FixtureState()


@dataclass
class FixtureApp:
    url: str
    server: _FixtureServer
    thread: threading.Thread


@contextmanager
def start_fixture_app() -> Iterator[FixtureApp]:
    """Serve the cookie-gated portal on loopback."""

    server = _FixtureServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    handle = FixtureApp(url=f"http://{host}:{port}", server=server, thread=thread)
    try:
        yield handle
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def call_browser_tool(session: BrowserSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one browser tool call against an open session."""

    action = str(arguments.get("action") or "").strip()
    if action == "navigate":
        session.goto(str(arguments.get("url") or ""))
    elif action == "click":
        session.click(str(arguments.get("text") or ""))
    elif action == "type":
        session.fill(str(arguments.get("name") or ""), str(arguments.get("text") or ""))
    elif action == "submit":
        session.submit()
    elif action == "read":
        pass
    else:
        raise BrowserActuationError(f"unsupported browser action: {action!r}")
    page = session.page
    if page is None:
        raise BrowserActuationError("browser tool produced no page")
    return {
        "action": action,
        "url": page.url,
        "status": page.status,
        "text": session.snapshot(),
        "sentinel": page.element("sentinel"),
        "echo": page.element("echo"),
        "status_text": page.element("status"),
    }


def run_browser_workflow(
    base_url: str,
    *,
    token: str = UNLOCK_TOKEN,
    note: str = DEFAULT_NOTE,
    send_cookies: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the form-driven login+echo workflow and seal a digest-chained trace."""

    descriptor = browser_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BROWSER_TOOL_PROVIDER),
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
        raise BrowserActuationError(f"browser tool did not route executable: {decision.reasons}")

    session = BrowserSession(send_cookies=send_cookies)
    calls = [
        {"action": "navigate", "url": f"{base_url.rstrip('/')}/"},
        {"action": "click", "text": "Sign in"},
        {"action": "type", "name": "token", "text": token},
        {"action": "submit"},
        {"action": "type", "name": "note", "text": note},
        {"action": "submit"},
        {"action": "read"},
    ]
    results: list[dict[str, Any]] = []
    for arguments in calls:
        try:
            results.append(call_browser_tool(session, arguments))
        except BrowserActuationError as error:
            results.append({"action": arguments["action"], "error": str(error)})
            break
        if session.page is not None and session.page.status >= 400:
            break

    final = results[-1] if results else {}
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "browser_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "base_url": base_url,
        "send_cookies": send_cookies,
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "sentinel": final.get("sentinel") or "",
        "echo": final.get("echo") or "",
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}
    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="browser-live-"))
    out.mkdir(parents=True, exist_ok=True)
    from blackhole_agent.capability_compounder import atomic_write_json

    atomic_write_json(out / "execution.json", trace)
    return {
        "ok": bool(decision.executable and final.get("sentinel") == SENTINEL and final.get("echo") == note),
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "sentinel": final.get("sentinel") or "",
        "echo": final.get("echo") or "",
        "final_status": int(final.get("status") or 0),
        "send_cookies": send_cookies,
        "result_text": str(final.get("text") or ""),
    }


def verify_browser_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed browser trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "routing_executable": routing.get("executable") is True
        and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "echo_recorded": bool(trace.get("echo")),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def browser_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.browser_actuation import "
        "builtin_browser_actuation_proof; r=builtin_browser_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='browser_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_browser_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=BROWSER_ACTUATION_ID,
        name="First-class browser actuation",
        description=(
            "Missions that require a browser tool can opt the browser provider "
            "in, drive a cookie-gated form workflow on a local page, and seal "
            "a digest-chained actuation trace. Default routing stays fail-closed; "
            "a no-cookie client keeps the session hole falsifiable."
        ),
        kind="python",
        entry="blackhole_agent.browser_actuation:builtin_browser_actuation_proof",
        proof_command=browser_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
        ),
        behavior_paths=(
            "src/blackhole_agent/browser_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required browser tool is executable after explicit provider "
            "opt-in: Unbound navigates, fills, and submits a cookie-gated local "
            "form workflow, seals a tamper-evident trace, and binds this family "
            "as the next diversity-catalog successor once publication is proved."
        ),
        tags=("browser", "actuation", "routing", "web", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T010250Z-45c24e1a",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_browser_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in browser actuation seals a cookie-gated workflow."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_http_event_stream import MCP_HTTP_EVENT_GOAL, MCP_HTTP_EVENT_ID
    from blackhole_agent.publication_resilience import (
        PUBLICATION_RESILIENCE_GOAL,
        PUBLICATION_RESILIENCE_ID,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = BROWSER_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(BROWSER_ACTUATION_GOAL) == (
        BROWSER_ACTUATION_ID,
    )
    checks["publication_goal_is_not_browser"] = leftover_marker_ids(PUBLICATION_RESILIENCE_GOAL) != (
        BROWSER_ACTUATION_ID,
    )
    checks["event_stream_goal_is_not_browser"] = leftover_marker_ids(MCP_HTTP_EVENT_GOAL) != (
        BROWSER_ACTUATION_ID,
    )
    checks["publication_marker_stays_publication"] = leftover_marker_ids(
        PUBLICATION_RESILIENCE_GOAL
    ) == (PUBLICATION_RESILIENCE_ID,)
    checks["event_stream_marker_stays_event"] = leftover_marker_ids(MCP_HTTP_EVENT_GOAL) == (
        MCP_HTTP_EVENT_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_browser"] = (
        len(catalog) > 9
        and catalog[9]["id"] == BROWSER_ACTUATION_ID
        and catalog[8]["id"] == PUBLICATION_RESILIENCE_ID
    )

    mcp_browser = ToolDescriptor(name="remote_browser", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_browser)
    checks["naive_mcp_browser_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = browser_tool_descriptor()
    default_browser = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BROWSER_TOOL_PROVIDER),
    )
    checks["default_browser_provider_is_unsupported"] = (
        default_browser.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{BROWSER_TOOL_PROVIDER}" in default_browser.reasons
    )
    checks["opted_in_browser_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_browser],
        required_tool_names=("local_memory", "browser"),
    )
    checks["naive_preflight_missing_browser"] = (
        naive_preflight["ok"] is False
        and naive_preflight["missing_required_tool_names"] == ["browser"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "browser"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BROWSER_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "browser" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with start_fixture_app() as app, tempfile.TemporaryDirectory(prefix="browser-actuation-") as tmp:
        root = Path(tmp)
        naive = run_browser_workflow(app.url, send_cookies=False, output_dir=root / "naive")
        checks["naive_without_cookies_is_forbidden"] = (
            naive["ok"] is False
            and naive["sentinel"] == ""
            and naive["final_status"] == 403
            and "forbidden" in naive["result_text"]
        )
        live = run_browser_workflow(app.url, output_dir=root / "live")
        verify = verify_browser_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_browser_trace(clone)
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_echoes_note"] = live["echo"] == DEFAULT_NOTE
        checks["cookie_session_is_required"] = naive["ok"] is False and live["ok"] is True
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="browser-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != BROWSER_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_browser"] = (
        live_goal == BROWSER_ACTUATION_GOAL
        and BROWSER_ACTUATION_ID in live_done
        and live_source == "genesis_bind_browser"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_browser_actuation_capability()
    return {
        "ok": ok,
        "action": "browser_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": BROWSER_ACTUATION_GOAL,
        "done_when": BROWSER_ACTUATION_DONE_WHEN,
    }
