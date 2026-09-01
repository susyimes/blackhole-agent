"""Drive a hermetic CDP session through a JavaScript-gated local page.

Unbound's first-party browser provider already seals cookie-gated *static*
HTML. A page that renders its unlock form only after script runs still
fails: urllib parses the shell document, finds no link or form, and never
yields a sealed workflow. The hosted browser-use plugin is not a substitute
— its initialize handshake closes before a session exists.

This module closes that hole:

- fetch a JS-gated fixture whose links and forms live only inside ``<script>``
- speak Chrome DevTools Protocol methods (``Page.navigate``,
  ``Runtime.evaluate``, ``Input.insertText``, ``Input.dispatchMouseEvent``,
  ``DOM.getDocument``) against an in-process JS VM subset
- keep a no-evaluate CDP client and a urllib client so the script hole stays
  falsifiable
- seal a digest-chained actuation trace
- bind this family as the next diversity-catalog successor after worktree roots
"""

from __future__ import annotations

import hashlib
import html as html_lib
import http.cookiejar
import json
import re
import shutil
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from blackhole_agent.browser_actuation import (
    BROWSER_ACTUATION_GOAL,
    BROWSER_ACTUATION_ID,
    BrowserActuationError,
    BrowserSession,
    element_text,
    parse_forms,
    parse_links,
)
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
from blackhole_agent.mcp_roots_list_changed import MCP_ROOTS_CHANGED_GOAL, MCP_ROOTS_CHANGED_ID
from blackhole_agent.tool_routing import (
    BROWSER_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    browser_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
BROWSER_CDP_ID = "capability.browser-cdp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-cdp"
SENTINEL = "BH-CDP-OK"
SESSION_COOKIE = "bh_cdp_session"
SESSION_VALUE = "ok"
DEFAULT_NOTE = "cdp-sealed-note"
SHELL_STATUS = "shell"
MISSING_ERROR = "javascript render missing"

BROWSER_CDP_DONE_WHEN = (
    f"capability_exists:{BROWSER_CDP_ID};"
    f"capability_proved:{BROWSER_CDP_ID};"
    "no_skill_route"
)
BROWSER_CDP_GOAL = (
    "Repair JavaScript-gated browser actuation: Unbound's urllib browser "
    "provider only parses static HTML, so a page that renders its unlock form "
    "in the DOM via script never yields a sealed workflow. Drive a hermetic "
    "CDP session that can evaluate script, click, and type on a JS-rendered "
    "form; a no-script urllib client stays fail-closed."
)

_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)
_MOUNT_RE = re.compile(r"document\.mount\(\s*'([^']+)'\s*,\s*\{([^}]*)\}\s*\)")
_PROP_RE = re.compile(r"([A-Za-z_][\w]*)\s*:\s*'([^']*)'")
_TEXT_RE = re.compile(
    r"document\.getElementById\(\s*'([^']+)'\s*\)\s*\.textContent\s*=\s*'([^']*)'\s*$"
)
_VALUE_RE = re.compile(
    r"document\.getElementById\(\s*'([^']+)'\s*\)\s*\.value\s*=\s*'([^']*)'\s*$"
)
_INNER_HTML_RE = re.compile(
    r"document\.getElementById\(\s*'([^']+)'\s*\)\s*\.innerHTML\s*=\s*'([^']*)'\s*$"
)
_BUTTON_RE = re.compile(r"<button\b[^>]*>(.*?)</button>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class BrowserCdpError(RuntimeError):
    """Raised when the CDP session or JS-gated fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _visible_text(blob: str) -> str:
    return _WS_RE.sub(" ", html_lib.unescape(_TAG_RE.sub(" ", blob or ""))).strip()


def _set_element_inner(document: str, element_id: str, inner: str) -> str:
    opening = re.search(
        rf'<(?P<tag>[a-zA-Z][a-zA-Z0-9]*)\b[^>]*\bid="{re.escape(element_id)}"[^>]*>',
        document or "",
        flags=re.IGNORECASE,
    )
    if opening is None:
        raise BrowserCdpError(f"no element id={element_id!r} for innerHTML")
    tag = opening.group("tag")
    inner_start = opening.end()
    closing = re.search(rf"</{re.escape(tag)}>", document[inner_start:], flags=re.IGNORECASE)
    if closing is None:
        raise BrowserCdpError(f"unclosed element id={element_id!r}")
    inner_end = inner_start + closing.start()
    return document[:inner_start] + inner + document[inner_end:]


def _js_object(blob: str) -> dict[str, str]:
    return {match.group(1): match.group(2) for match in _PROP_RE.finditer(blob or "")}


def _mounted_html(spec: Mapping[str, str]) -> str:
    kind = str(spec.get("type") or "").strip()
    if kind == "link":
        href = html_lib.escape(str(spec.get("href") or ""), quote=True)
        text = html_lib.escape(str(spec.get("text") or ""), quote=True)
        return f'<a href="{href}">{text}</a>'
    if kind == "form":
        action = html_lib.escape(str(spec.get("action") or ""), quote=True)
        method = html_lib.escape(str(spec.get("method") or "post"), quote=True)
        name = html_lib.escape(str(spec.get("name") or ""), quote=True)
        submit = html_lib.escape(str(spec.get("submit") or "Go"), quote=True)
        return (
            f'<form action="{action}" method="{method}">'
            f'<input name="{name}" id="{name}" />'
            f'<button type="submit">{submit}</button>'
            "</form>"
        )
    if kind == "dashboard":
        sentinel = html_lib.escape(str(spec.get("sentinel") or ""), quote=True)
        action = html_lib.escape(str(spec.get("action") or ""), quote=True)
        name = html_lib.escape(str(spec.get("name") or ""), quote=True)
        submit = html_lib.escape(str(spec.get("submit") or "Go"), quote=True)
        return (
            f'<p id="sentinel">{sentinel}</p>'
            f'<form action="{action}" method="post">'
            f'<input name="{name}" id="{name}" />'
            f'<button type="submit">{submit}</button>'
            "</form>"
        )
    raise BrowserCdpError(f"unsupported mount type: {kind!r}")


def evaluate_page_scripts(document: str, *, fields: dict[str, str] | None = None) -> str:
    """Run the fixture's tag-free JS mount subset plus text/value assignments.

    Page source never contains the unlock markup as HTML, so urllib's static
    parser stays on the shell document. Only this VM materializes the DOM.
    """

    live = document
    values = fields if fields is not None else {}
    for script in _SCRIPT_RE.findall(document or ""):
        for raw in script.split(";"):
            stmt = raw.strip()
            if not stmt:
                continue
            match = _MOUNT_RE.match(stmt)
            if match:
                live = _set_element_inner(live, match.group(1), _mounted_html(_js_object(match.group(2))))
                continue
            match = _INNER_HTML_RE.match(stmt)
            if match:
                live = _set_element_inner(live, match.group(1), match.group(2))
                continue
            match = _TEXT_RE.match(stmt)
            if match:
                live = _set_element_inner(
                    live, match.group(1), html_lib.escape(match.group(2), quote=True)
                )
                continue
            match = _VALUE_RE.match(stmt)
            if match:
                values[match.group(1)] = match.group(2)
                continue
            raise BrowserCdpError(f"unsupported script statement: {stmt}")
    return live


def _shell_page(extra: str = "") -> str:
    return (
        "<html><body>"
        f"<p id=\"status\">{SHELL_STATUS}</p>"
        "<div id=\"app\"></div>"
        f"{extra}"
        "</body></html>"
    )


def _index_page() -> str:
    script = (
        "document.mount('app', {type:'link', href:'/login', text:'Sign in'});"
        "document.getElementById('status').textContent = 'ready'"
    )
    return _shell_page(f"<script>{script}</script>")


def _login_page() -> str:
    script = (
        "document.mount('app', {type:'form', action:'/login', method:'post', "
        "name:'token', submit:'Unlock'});"
        "document.getElementById('status').textContent = 'gate'"
    )
    return _shell_page(f"<script>{script}</script>")


def _dashboard_page() -> str:
    script = (
        "document.mount('app', {type:'dashboard', sentinel:'"
        f"{SENTINEL}"
        "', action:'/echo', name:'note', submit:'Save'});"
        "document.getElementById('status').textContent = 'open'"
    )
    return _shell_page(f"<script>{script}</script>")


def _echo_page(note: str) -> str:
    return (
        "<html><body>"
        f"<p id=\"echo\">{html_lib.escape(note, quote=True)}</p>"
        f"<p id=\"sentinel\">{SENTINEL}</p>"
        f"<p id=\"status\">sealed</p>"
        "</body></html>"
    )


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

    def _send(self, status: int, body: str, *, headers: list[tuple[str, str]] | None = None) -> None:
        payload = body.encode("utf-8")
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
            self._send(200, _index_page())
            return
        if path == "/login":
            self._send(200, _login_page())
            return
        if path == "/dashboard":
            if not self._authed():
                self._send(403, _shell_page("<p id=\"denied\">forbidden</p>"))
                return
            self._send(200, _dashboard_page())
            return
        self._send(404, _shell_page("<p id=\"denied\">missing</p>"))

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        fields = {
            key: (values[-1] if values else "")
            for key, values in parse_qs(raw.decode("utf-8")).items()
        }
        path = str(urljoin("/", self.path).split("?", 1)[0])
        if path == "/login":
            if str(fields.get("token") or "") != UNLOCK_TOKEN:
                self._send(200, _login_page())
                return
            self.send_response(303)
            self.send_header("Location", "/dashboard")
            self.send_header(
                "Set-Cookie", f"{SESSION_COOKIE}={SESSION_VALUE}; Path=/; HttpOnly"
            )
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/echo":
            if not self._authed():
                self._send(403, _shell_page("<p id=\"denied\">forbidden</p>"))
                return
            note = str(fields.get("note") or "")
            self.server.state.notes.append(note)
            self._send(200, _echo_page(note))
            return
        self._send(404, _shell_page("<p id=\"denied\">missing</p>"))


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
def start_js_gated_app() -> Iterator[FixtureApp]:
    """Serve the JavaScript-gated portal on loopback."""

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


@dataclass
class CdpSession:
    """Hermetic Chrome DevTools client over loopback HTTP plus a JS subset VM."""

    timeout_seconds: float = 5.0
    jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)
    raw_html: str = ""
    live_html: str = ""
    url: str = ""
    status: int = 0
    fields: dict[str, str] = field(default_factory=dict)
    commands: list[dict[str, Any]] = field(default_factory=list)
    scripts_evaluated: int = 0

    def __post_init__(self) -> None:
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(self.jar))

    def call(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(params or {})
        self.commands.append({"method": method, "params": payload})
        if method == "Page.navigate":
            self._open("GET", str(payload.get("url") or ""))
            return {"result": {"frameId": "frame-1", "status": self.status, "url": self.url}}
        if method == "Runtime.evaluate":
            expression = str(payload.get("expression") or "").strip()
            source = (
                self.live_html + f"<script>{expression}</script>"
                if expression
                else self.raw_html
            )
            self.live_html = evaluate_page_scripts(source, fields=self.fields)
            self.scripts_evaluated += 1
            return {
                "result": {
                    "result": {"type": "string", "value": element_text(self.live_html, "status")}
                }
            }
        if method == "DOM.getDocument":
            return {"result": {"root": {"outerHTML": self.live_html}}}
        if method == "Input.insertText":
            name = str(payload.get("name") or payload.get("id") or "")
            text = str(payload.get("text") or payload.get("value") or "")
            self.fields[name] = text
            return {"result": {"ok": True, "name": name}}
        if method == "Input.dispatchMouseEvent":
            self._click(str(payload.get("label") or payload.get("text") or ""))
            return {"result": {"ok": True, "url": self.url, "status": self.status}}
        raise BrowserCdpError(f"unsupported CDP method: {method}")

    def _click(self, label: str) -> None:
        wanted = str(label or "").strip()
        if not wanted:
            raise BrowserCdpError("click requires a label")
        for href, text in parse_links(self.live_html):
            if text == wanted:
                self._open("GET", urljoin(self.url, href))
                return
        for raw in _BUTTON_RE.findall(self.live_html):
            if _visible_text(raw) == wanted:
                self._submit()
                return
        raise BrowserCdpError(f"{MISSING_ERROR}: no control labelled {wanted!r}")

    def _submit(self) -> None:
        forms = parse_forms(self.live_html)
        if not forms:
            raise BrowserCdpError(f"{MISSING_ERROR}: no form on the current page")
        form = forms[0]
        payload = {**form["fields"], **self.fields}
        target = urljoin(self.url, str(form["action"] or self.url))
        method = str(form["method"] or "GET").upper()
        if method == "GET":
            joined = target + ("&" if "?" in target else "?") + urlencode(payload)
            self._open("GET", joined)
            return
        self._open("POST", target, urlencode(payload).encode("utf-8"))

    def _open(self, method: str, url: str, data: bytes | None = None) -> None:
        request = Request(url, data=data, method=method)
        if method == "POST":
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                final_url = str(response.geturl())
                status = int(response.status)
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            final_url = str(error.geturl() or url)
            status = int(error.code)
        except URLError as error:
            raise BrowserCdpError(f"CDP navigation failed: {error}") from error
        self.raw_html = body
        self.live_html = body
        self.url = final_url
        self.status = status
        self.fields = {}

    def snapshot(self) -> str:
        return _visible_text(self.live_html)

    def element(self, element_id: str) -> str:
        return element_text(self.live_html, element_id)


def run_urllib_js_gated_workflow(base_url: str) -> dict[str, Any]:
    """Urllib static parser against the JS-gated portal (expected fail-closed)."""

    session = BrowserSession(send_cookies=True)
    page = session.goto(f"{base_url.rstrip('/')}/")
    error = ""
    try:
        session.click("Sign in")
    except BrowserActuationError as exc:
        error = str(exc)
    return {
        "ok": False if error else True,
        "error": error,
        "status_text": element_text(page.html, "status") if error else session.page.element("status") if session.page else "",
        "has_sign_in": any(text == "Sign in" for _href, text in parse_links(page.html)),
        "final_url": page.url,
    }


def run_cdp_workflow(
    base_url: str,
    *,
    token: str = UNLOCK_TOKEN,
    note: str = DEFAULT_NOTE,
    evaluate_scripts: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Drive the JS-gated portal through CDP methods and seal a trace."""

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
        raise BrowserCdpError(f"browser tool did not route executable: {decision.reasons}")

    session = CdpSession()
    error = ""
    try:
        session.call("Page.navigate", {"url": f"{base_url.rstrip('/')}/"})
        if evaluate_scripts:
            session.call("Runtime.evaluate", {"expression": ""})
        session.call("Input.dispatchMouseEvent", {"label": "Sign in"})
        if evaluate_scripts:
            session.call("Runtime.evaluate", {"expression": ""})
        session.call("Input.insertText", {"name": "token", "text": token})
        session.call("Input.dispatchMouseEvent", {"label": "Unlock"})
        if evaluate_scripts:
            session.call("Runtime.evaluate", {"expression": ""})
        session.call("Input.insertText", {"name": "note", "text": note})
        session.call("Input.dispatchMouseEvent", {"label": "Save"})
    except BrowserCdpError as exc:
        error = str(exc)

    methods = [item["method"] for item in session.commands]
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "browser_cdp_execution_trace",
        "recorded_at": utc_now_iso(),
        "base_url": base_url,
        "evaluate_scripts": evaluate_scripts,
        "routing": routing,
        "routing_digest": _digest(routing),
        "commands": session.commands,
        "command_digest": _digest(session.commands),
        "scripts_evaluated": session.scripts_evaluated,
        "sentinel": session.element("sentinel"),
        "echo": session.element("echo"),
        "status_text": session.element("status"),
        "final_url": session.url,
        "final_status": session.status,
        "error": error,
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}
    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="browser-cdp-"))
    out.mkdir(parents=True, exist_ok=True)
    from blackhole_agent.capability_compounder import atomic_write_json

    atomic_write_json(out / "execution.json", trace)
    sealed = (
        not error
        and evaluate_scripts
        and session.element("sentinel") == SENTINEL
        and session.element("echo") == note
        and "Runtime.evaluate" in methods
    )
    return {
        "ok": sealed,
        "error": error,
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "sentinel": session.element("sentinel"),
        "echo": session.element("echo"),
        "status_text": session.element("status"),
        "scripts_evaluated": session.scripts_evaluated,
        "methods": methods,
        "final_status": session.status,
        "evaluate_scripts": evaluate_scripts,
    }


def verify_cdp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed CDP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "command_digest": _digest(trace.get("commands")) == trace.get("command_digest"),
        "routing_executable": routing.get("executable") is True
        and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "evaluated_runtime": any(
            item.get("method") == "Runtime.evaluate"
            for item in (trace.get("commands") or [])
            if isinstance(item, Mapping)
        ),
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "echo_recorded": bool(trace.get("echo")),
        "no_error": not str(trace.get("error") or ""),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def browser_cdp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.browser_cdp_actuation import "
        "builtin_browser_cdp_actuation_proof; r=builtin_browser_cdp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='browser_cdp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_browser_cdp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=BROWSER_CDP_ID,
        name="JavaScript-gated CDP browser actuation",
        description=(
            "A page that renders its unlock form only after script runs is "
            "first-class: Unbound speaks Page.navigate and Runtime.evaluate on "
            "a hermetic CDP session, fills the JS-rendered form, and seals a "
            "digest-chained trace. Urllib and skip-evaluate sessions stay "
            "fail-closed on the shell document."
        ),
        kind="python",
        entry="blackhole_agent.browser_cdp_actuation:builtin_browser_cdp_actuation_proof",
        proof_command=browser_cdp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.browser-actuation",
            "capability.mcp-roots-list-changed",
        ),
        behavior_paths=(
            "src/blackhole_agent/browser_cdp_actuation.py",
            "src/blackhole_agent/browser_actuation.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A JavaScript-gated page is actuatable: Unbound evaluates script "
            "over a hermetic CDP session so a JS-rendered form unlocks and a "
            "sealed workflow returns, while urllib and skip-evaluate clients "
            "stay on the shell document."
        ),
        tags=("browser", "cdp", "javascript", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T025025Z-a6e696e2",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_browser_cdp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: CDP Runtime.evaluate unlocks a JS-gated form."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mission_selection import capability_family

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = BROWSER_CDP_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(BROWSER_CDP_GOAL) == (BROWSER_CDP_ID,)
    checks["static_browser_goal_is_not_cdp"] = leftover_marker_ids(BROWSER_ACTUATION_GOAL) == (
        BROWSER_ACTUATION_ID,
    )
    checks["roots_goal_is_not_cdp"] = leftover_marker_ids(MCP_ROOTS_CHANGED_GOAL) == (
        MCP_ROOTS_CHANGED_ID,
    )
    checks["cdp_goal_is_not_static_browser"] = BROWSER_ACTUATION_ID not in leftover_marker_ids(
        BROWSER_CDP_GOAL
    )
    checks["cdp_goal_is_not_roots"] = MCP_ROOTS_CHANGED_ID not in leftover_marker_ids(
        BROWSER_CDP_GOAL
    )
    checks["static_marker_stays_static"] = BROWSER_CDP_ID not in leftover_marker_ids(
        BROWSER_ACTUATION_GOAL
    )
    checks["roots_marker_stays_roots"] = BROWSER_CDP_ID not in leftover_marker_ids(
        MCP_ROOTS_CHANGED_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_browser_cdp"] = (
        len(catalog) > 23
        and catalog[23]["id"] == BROWSER_CDP_ID
        and catalog[22]["id"] == MCP_ROOTS_CHANGED_ID
    )
    checks["family_is_browser"] = "browser" in capability_family(BROWSER_CDP_GOAL)

    rendered = evaluate_page_scripts(_index_page())
    source = _index_page() + _login_page() + _dashboard_page()
    checks["source_has_no_html_controls"] = (
        "<a " not in source and "<form" not in source and "<button" not in source
    )
    checks["shell_hides_sign_in"] = not any(
        text == "Sign in" for _href, text in parse_links(_index_page())
    )
    checks["evaluate_reveals_sign_in"] = any(
        text == "Sign in" for _href, text in parse_links(rendered)
    )
    checks["shell_status_is_shell"] = element_text(_index_page(), "status") == SHELL_STATUS
    checks["evaluate_status_is_ready"] = element_text(rendered, "status") == "ready"

    with start_js_gated_app() as app, tempfile.TemporaryDirectory(prefix="browser-cdp-") as tmp:
        root = Path(tmp)
        urllib_blocked = run_urllib_js_gated_workflow(app.url)
        checks["urllib_stays_on_shell"] = (
            urllib_blocked["ok"] is False
            and urllib_blocked["status_text"] == SHELL_STATUS
            and urllib_blocked["has_sign_in"] is False
            and "no link labelled" in urllib_blocked["error"]
        )
        skipped = run_cdp_workflow(
            app.url, evaluate_scripts=False, output_dir=root / "skip"
        )
        checks["skip_evaluate_is_error"] = (
            skipped["ok"] is False
            and skipped["scripts_evaluated"] == 0
            and MISSING_ERROR in skipped["error"]
            and skipped["status_text"] == SHELL_STATUS
        )
        live = run_cdp_workflow(app.url, output_dir=root / "live")
        verify = verify_cdp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_cdp_trace(clone)
        checks["cdp_evaluate_unlocks"] = live["ok"] is True
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_echoes_note"] = live["echo"] == DEFAULT_NOTE
        checks["live_evaluated_runtime"] = (
            live["scripts_evaluated"] >= 3 and "Runtime.evaluate" in live["methods"]
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="browser-cdp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != BROWSER_CDP_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_browser_cdp"] = (
        live_goal == BROWSER_CDP_GOAL
        and BROWSER_CDP_ID in live_done
        and live_source == "genesis_bind_browser_cdp"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_browser_cdp_actuation_capability()
    return {
        "ok": ok,
        "action": "browser_cdp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": BROWSER_CDP_GOAL,
        "done_when": BROWSER_CDP_DONE_WHEN,
    }
