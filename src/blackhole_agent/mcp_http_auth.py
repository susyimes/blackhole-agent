"""Complete MCP HTTP initialize after a 401 WWW-Authenticate bearer challenge.

Streamable HTTP already POSTs JSON-RPC. A spec-compliant hosted plugin that
protects ``/mcp`` with OAuth 2.1 still cannot complete initialize: the client
never reads ``WWW-Authenticate``, never fetches RFC 9728 resource metadata,
never exchanges ``client_credentials``, and never retries with
``Authorization: Bearer``.

This module closes that hole:

- parse 401 ``WWW-Authenticate`` for ``resource_metadata``
- GET protected-resource metadata and authorization-server metadata
- POST ``client_credentials`` to the token endpoint with the resource indicator
- retry initialize and tools/call with ``Authorization: Bearer``
- keep a skip-token path so the 401 challenge stays falsifiable
- let a bearer-gated HTTP plugin and a stdio sibling serve together
- bind this family as the next diversity-catalog successor after SMTP
"""

from __future__ import annotations

import json
import re
import secrets
import tempfile
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin
from urllib.request import ProxyHandler, Request, build_opener

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
from blackhole_agent.mcp_client import McpProtocolError, _extract_text, echo_server_command
from blackhole_agent.mcp_echo_server import handle_message
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_http_transport import McpHttpSession
from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID

SCHEMA_VERSION = 1
MCP_HTTP_AUTH_ID = "capability.mcp-http-auth"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "BH-HTTP-AUTH-OK"
PROTECTED_SERVER_NAME = "blackhole-protected-mcp"
DEFAULT_CLIENT_ID = "blackhole-mcp"
DEFAULT_CLIENT_SECRET = "blackhole-mcp-secret"
GATED_TOOL_NAME = "echo"

MCP_HTTP_AUTH_DONE_WHEN = (
    f"capability_exists:{MCP_HTTP_AUTH_ID};"
    f"capability_proved:{MCP_HTTP_AUTH_ID};"
    "no_skill_route"
)
MCP_HTTP_AUTH_GOAL = (
    "Repair MCP HTTP bearer authorization: a hosted plugin that answers "
    "initialize with 401 WWW-Authenticate never receives a resource-metadata "
    "discovery or client-credentials token, so a bearer-gated tools/call stays "
    "forbidden. Sessions that skip the token keep the 401 challenge falsifiable."
)

_CHALLENGE_PARAM = re.compile(r'([A-Za-z0-9_]+)=("([^"]*)"|([^\s,]+))')


class HttpAuthHandle:
    """Loopback OAuth-protected streamable-HTTP MCP server."""

    def __init__(self, origin: str, mcp_url: str, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        self.origin = origin
        self.mcp_url = mcp_url
        self.server = server
        self.thread = thread

    @property
    def resource_metadata_url(self) -> str:
        return f"{self.origin}/.well-known/oauth-protected-resource"

    @property
    def authorization_server_url(self) -> str:
        return f"{self.origin}/.well-known/oauth-authorization-server"

    @property
    def token_url(self) -> str:
        return f"{self.origin}/token"


def parse_www_authenticate(header: str) -> dict[str, str]:
    """Parse a Bearer WWW-Authenticate challenge into scheme plus parameters."""

    text = str(header or "").strip()
    if not text:
        return {}
    scheme, _, rest = text.partition(" ")
    params = {"scheme": scheme.strip()}
    for match in _CHALLENGE_PARAM.finditer(rest):
        key = match.group(1)
        value = match.group(3) if match.group(3) is not None else (match.group(4) or "")
        params[key] = value
    return params


def _json_request(url: str, *, timeout_seconds: float, data: bytes | None = None, headers: Mapping[str, str] | None = None) -> dict[str, Any]:
    request_headers = {"Accept": "application/json", **dict(headers or {})}
    request = Request(url, data=data, headers=request_headers, method="POST" if data is not None else "GET")
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except HTTPError as error:
        status = int(error.code)
        try:
            error.read()
        except Exception:  # noqa: BLE001 - drain the HTTPError body
            pass
        raise McpProtocolError(f"http {status} for {url}", status_code=status) from error
    except (TimeoutError, URLError, OSError) as error:
        raise McpProtocolError(f"timeout fetching {url}") from error
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise McpProtocolError(f"malformed JSON from {url}") from error
    if not isinstance(payload, dict):
        raise McpProtocolError(f"malformed JSON object from {url}")
    return payload


def discover_token_endpoint(metadata_url: str, *, timeout_seconds: float) -> tuple[str, str]:
    """Return ``(token_endpoint, resource)`` from RFC 9728 then RFC 8414 metadata."""

    resource_metadata = _json_request(metadata_url, timeout_seconds=timeout_seconds)
    resource = str(resource_metadata.get("resource") or "")
    servers = resource_metadata.get("authorization_servers") or []
    issuer = str(servers[0]) if servers else ""
    if not issuer:
        raise McpProtocolError(f"resource metadata missing authorization_servers: {metadata_url}")
    well_known = urljoin(issuer.rstrip("/") + "/", ".well-known/oauth-authorization-server")
    as_metadata = _json_request(well_known, timeout_seconds=timeout_seconds)
    token_endpoint = str(as_metadata.get("token_endpoint") or "")
    if not token_endpoint:
        raise McpProtocolError(f"authorization server missing token_endpoint: {well_known}")
    return token_endpoint, resource


def exchange_client_credentials(
    metadata_url: str,
    *,
    client_id: str,
    client_secret: str,
    resource: str,
    timeout_seconds: float = 8.0,
) -> tuple[str, str]:
    """Exchange client_credentials against the discovered token endpoint.

    Returns ``(access_token, token_endpoint)``.
    """

    if not client_secret:
        raise McpProtocolError("missing client_secret", status_code=401)
    token_endpoint, advertised_resource = discover_token_endpoint(
        metadata_url, timeout_seconds=timeout_seconds
    )
    target = str(resource or advertised_resource or "")
    body = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "resource": target,
        }
    ).encode("utf-8")
    payload = _json_request(
        token_endpoint,
        timeout_seconds=timeout_seconds,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = str(payload.get("access_token") or "")
    if not token:
        raise McpProtocolError(f"token endpoint returned no access_token: {token_endpoint}")
    return token, token_endpoint


class _ProtectedMcpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(address, handler)
        self.client_id = DEFAULT_CLIENT_ID
        self.client_secret = DEFAULT_CLIENT_SECRET
        self.tokens: set[str] = set()
        self.lock = threading.Lock()

    @property
    def origin(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def mcp_url(self) -> str:
        return f"{self.origin}/mcp"


class _ProtectedMcpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib
        path = self.path.split("?", 1)[0]
        if path == "/.well-known/oauth-protected-resource":
            self._write_json(
                {
                    "resource": self.server.mcp_url,  # type: ignore[attr-defined]
                    "authorization_servers": [self.server.origin],  # type: ignore[attr-defined]
                    "bearer_methods_supported": ["header"],
                }
            )
            return
        if path == "/.well-known/oauth-authorization-server":
            origin = self.server.origin  # type: ignore[attr-defined]
            self._write_json(
                {
                    "issuer": origin,
                    "token_endpoint": f"{origin}/token",
                    "grant_types_supported": ["client_credentials"],
                }
            )
            return
        if path.rstrip("/") == "/mcp":
            self.send_error(405, "POST-only MCP endpoint")
            return
        self.send_error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib
        path = self.path.split("?", 1)[0]
        if path == "/token":
            self._token()
            return
        if path.rstrip("/") != "/mcp":
            self.send_error(404, "not an MCP endpoint")
            return
        if not self._bearer_ok():
            self._challenge()
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            message = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}},
                status=400,
            )
            return
        if not isinstance(message, dict):
            self._write_json(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}},
                status=400,
            )
            return
        response = _protect_response(message, handle_message(message))
        if response is None:
            self.send_response(202)
            self.end_headers()
            return
        self._write_json(response)

    def _token(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b""
        fields = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
        grant = (fields.get("grant_type") or [""])[0]
        client_id = (fields.get("client_id") or [""])[0]
        client_secret = (fields.get("client_secret") or [""])[0]
        resource = (fields.get("resource") or [""])[0]
        server: _ProtectedMcpServer = self.server  # type: ignore[assignment]
        if grant != "client_credentials":
            self._write_json({"error": "unsupported_grant_type"}, status=400)
            return
        if client_id != server.client_id or client_secret != server.client_secret:
            self._write_json({"error": "invalid_client"}, status=401)
            return
        if resource != server.mcp_url:
            self._write_json({"error": "invalid_target"}, status=400)
            return
        token = secrets.token_hex(16)
        with server.lock:
            server.tokens.add(token)
        self._write_json({"access_token": token, "token_type": "Bearer", "expires_in": 3600})

    def _bearer_ok(self) -> bool:
        header = self.headers.get("Authorization") or ""
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return False
        server: _ProtectedMcpServer = self.server  # type: ignore[assignment]
        with server.lock:
            return token.strip() in server.tokens

    def _challenge(self) -> None:
        metadata = f"{self.server.origin}/.well-known/oauth-protected-resource"  # type: ignore[attr-defined]
        body = b'{"error":"invalid_token"}'
        self.send_response(401)
        self.send_header(
            "WWW-Authenticate",
            f'Bearer realm="mcp", resource_metadata="{metadata}"',
        )
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_json(self, payload: Mapping[str, Any], *, status: int = 200) -> None:
        body = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _protect_response(message: Mapping[str, Any], response: dict[str, Any] | None) -> dict[str, Any] | None:
    if response is None:
        return None
    method = str(message.get("method") or "")
    if method == "initialize":
        result = dict(response.get("result") or {})
        result["serverInfo"] = {"name": PROTECTED_SERVER_NAME, "version": "1.0.0"}
        return {**response, "result": result}
    if method == "tools/call":
        params = message.get("params") or {}
        if str(params.get("name") or "") == GATED_TOOL_NAME:
            result = dict(response.get("result") or {})
            content = list(result.get("content") or [])
            if content and isinstance(content[0], dict):
                text = str(content[0].get("text") or "")
                content = [{**content[0], "text": f"{text}|{UNLOCK_TOKEN}"}]
                result["content"] = content
            return {**response, "result": result}
    return response


@contextmanager
def start_protected_mcp_server() -> Iterator[HttpAuthHandle]:
    """Serve OAuth metadata, a token endpoint, and a bearer-gated MCP POST."""

    server = _ProtectedMcpServer(("127.0.0.1", 0), _ProtectedMcpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    handle = HttpAuthHandle(
        origin=server.origin,
        mcp_url=server.mcp_url,
        server=server,
        thread=thread,
    )
    try:
        yield handle
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def is_mcp_http_unauthorized(exc: BaseException) -> bool:
    """True when initialize/tools/call was rejected with HTTP 401."""

    status = getattr(exc, "status_code", None)
    if status == 401:
        return True
    return "http 401" in str(exc).lower()


def mcp_http_auth_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_http_auth import "
        "builtin_mcp_http_auth_proof; r=builtin_mcp_http_auth_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_http_auth' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_http_auth_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_HTTP_AUTH_ID,
        name="MCP HTTP bearer authorization",
        description=(
            "A hosted MCP plugin that challenges initialize with 401 "
            "WWW-Authenticate completes after RFC 9728 resource-metadata "
            "discovery and a client_credentials token exchange, then serves a "
            "bearer-gated tools/call. Sessions that skip the token stay 401."
        ),
        kind="python",
        entry="blackhole_agent.mcp_http_auth:builtin_mcp_http_auth_proof",
        proof_command=mcp_http_auth_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-http-transport",
            "capability.smtp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_http_auth.py",
            "src/blackhole_agent/mcp_http_transport.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Hosted MCP HTTP servers that protect initialize with OAuth 2.1 "
            "stay on the live plane: Unbound reads WWW-Authenticate, discovers "
            "RFC 9728 resource metadata, exchanges client_credentials, retries "
            "with Authorization: Bearer, and a bearer-gated tools/call returns "
            "the sealed payload. Skip-token sessions keep the 401 challenge "
            "falsifiable, and this family binds as the next diversity-catalog "
            "successor once SMTP is proved."
        ),
        tags=("mcp", "http", "oauth", "bearer", "authorization", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T062958Z-dff4543a",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mcp_http_auth_proof() -> dict[str, Any]:
    """Hermetic proof: 401 WWW-Authenticate unlocks after a bearer token exchange."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_http_transport import MCP_HTTP_GOAL, MCP_HTTP_ID, start_http_echo_server
    from blackhole_agent.mcp_tools_list_changed import MCP_TOOLS_CHANGED_GOAL, MCP_TOOLS_CHANGED_ID
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_HTTP_AUTH_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_HTTP_AUTH_GOAL) == (MCP_HTTP_AUTH_ID,)
    checks["smtp_goal_is_not_http_auth"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (
        SMTP_ACTUATION_ID,
    )
    checks["http_goal_is_not_http_auth"] = leftover_marker_ids(MCP_HTTP_GOAL) == (MCP_HTTP_ID,)
    checks["tools_changed_goal_is_not_http_auth"] = leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL) == (
        MCP_TOOLS_CHANGED_ID,
    )
    checks["webhook_goal_is_not_http_auth"] = leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (
        WEBHOOK_ACTUATION_ID,
    )
    checks["http_auth_goal_is_not_smtp"] = SMTP_ACTUATION_ID not in leftover_marker_ids(
        MCP_HTTP_AUTH_GOAL
    )
    checks["http_auth_goal_is_not_http_transport"] = MCP_HTTP_ID not in leftover_marker_ids(
        MCP_HTTP_AUTH_GOAL
    )
    checks["http_auth_goal_is_not_tools_changed"] = MCP_TOOLS_CHANGED_ID not in leftover_marker_ids(
        MCP_HTTP_AUTH_GOAL
    )
    checks["http_auth_goal_is_not_webhook"] = WEBHOOK_ACTUATION_ID not in leftover_marker_ids(
        MCP_HTTP_AUTH_GOAL
    )
    checks["smtp_marker_stays_smtp"] = MCP_HTTP_AUTH_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    checks["http_marker_stays_http"] = MCP_HTTP_AUTH_ID not in leftover_marker_ids(MCP_HTTP_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_http_auth"] = (
        len(catalog) > 30
        and catalog[30]["id"] == MCP_HTTP_AUTH_ID
        and catalog[29]["id"] == SMTP_ACTUATION_ID
    )
    family = capability_family(MCP_HTTP_AUTH_GOAL)
    checks["family_is_bearer"] = "bearer" in family
    checks["family_is_authorization"] = "authorization" in family
    checks["family_is_not_smtp"] = "smtp" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_webhook"] = "webhook" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["not_a_smtp_duplicate"] = (
        semantic_similarity(
            semantic_signature(MCP_HTTP_AUTH_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_http_transport_duplicate"] = (
        semantic_similarity(
            semantic_signature(MCP_HTTP_AUTH_GOAL),
            semantic_signature(MCP_HTTP_GOAL),
        )
        < 0.82
    )
    checks["not_a_tools_changed_duplicate"] = (
        semantic_similarity(
            semantic_signature(MCP_HTTP_AUTH_GOAL),
            semantic_signature(MCP_TOOLS_CHANGED_GOAL),
        )
        < 0.82
    )

    challenge = parse_www_authenticate(
        'Bearer realm="mcp", resource_metadata="http://127.0.0.1:9/.well-known/oauth-protected-resource"'
    )
    checks["parses_resource_metadata_challenge"] = (
        challenge.get("scheme") == "Bearer"
        and challenge.get("realm") == "mcp"
        and challenge.get("resource_metadata", "").endswith("oauth-protected-resource")
    )

    with start_http_echo_server() as open_http:
        open_session = McpHttpSession(open_http.url, timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
        try:
            open_session.start()
            echoed = _extract_text(open_session.call_tool(GATED_TOOL_NAME, {"text": "open"}))
            checks["open_http_still_serves_without_bearer"] = (
                echoed == "open" and bool(open_session.session_id)
            )
        finally:
            open_session.kill()

    with start_protected_mcp_server() as hosted:
        naive = McpHttpSession(hosted.mcp_url, timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
        naive_unauthorized = False
        try:
            naive.start()
        except McpProtocolError as exc:
            naive_unauthorized = is_mcp_http_unauthorized(exc) and bool(exc.www_authenticate)
        finally:
            naive.kill()
        checks["naive_without_token_is_401"] = naive_unauthorized

        missing_secret = McpHttpSession(
            hosted.mcp_url,
            timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
            client_id=DEFAULT_CLIENT_ID,
            client_secret="",
            authorize_on_401=True,
        )
        missing_unauthorized = False
        try:
            missing_secret.start()
        except McpProtocolError as exc:
            missing_unauthorized = is_mcp_http_unauthorized(exc)
        finally:
            missing_secret.kill()
        checks["missing_client_secret_stays_401"] = missing_unauthorized

        wrong = McpHttpSession(
            hosted.mcp_url,
            timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
            access_token="forged-token",
        )
        wrong_unauthorized = False
        try:
            wrong.start()
        except McpProtocolError as exc:
            wrong_unauthorized = is_mcp_http_unauthorized(exc)
        finally:
            wrong.kill()
        checks["wrong_bearer_is_401"] = wrong_unauthorized

        live = McpHttpSession(
            hosted.mcp_url,
            timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
            client_id=DEFAULT_CLIENT_ID,
            client_secret=DEFAULT_CLIENT_SECRET,
            authorize_on_401=True,
            listen_event_stream=False,
        )
        try:
            live.start()
            tools = live.list_tools()
            names = tuple(
                str(item.get("name") or "")
                for item in (tools.get("tools") or [])
                if isinstance(item, Mapping)
            )
            served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
            checks["live_discovers_resource_metadata"] = (
                live.resource_metadata_url == hosted.resource_metadata_url
            )
            checks["live_exchanges_client_credentials"] = (
                bool(live.access_token) and live.token_endpoint == hosted.token_url
            )
            checks["live_initialize_names_protected_server"] = (
                live.server_info.get("name") == PROTECTED_SERVER_NAME
            )
            checks["live_lists_echo"] = GATED_TOOL_NAME in names
            checks["bearer_gated_tool_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
        finally:
            live.kill()

        mixed = connect_mcp_plane(
            [
                McpPluginSpec(
                    "hosted",
                    timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
                    url=hosted.mcp_url,
                    client_id=DEFAULT_CLIENT_ID,
                    client_secret=DEFAULT_CLIENT_SECRET,
                    authorize_on_401=True,
                ),
                McpPluginSpec("live", echo_server_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS),
            ],
            isolate_dead=True,
            isolate_hung_calls=True,
        )
        try:
            hosted_echo = _extract_text(mixed.call_tool("hosted", GATED_TOOL_NAME, {"text": "from-hosted"}))
            sibling = _extract_text(mixed.call_tool("live", GATED_TOOL_NAME, {"text": "from-echo"}))
            checks["mixed_bearer_http_and_stdio_serve"] = (
                mixed.plane_failed is False
                and mixed.live_names == ("hosted", "live")
                and hosted_echo == f"from-hosted|{UNLOCK_TOKEN}"
                and sibling == "from-echo"
            )
        finally:
            mixed.close()

        skipped = connect_mcp_plane(
            [
                McpPluginSpec(
                    "hosted",
                    timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
                    url=hosted.mcp_url,
                ),
                McpPluginSpec("live", echo_server_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS),
            ],
            isolate_dead=True,
            isolate_hung_calls=True,
        )
        try:
            sibling = _extract_text(skipped.call_tool("live", GATED_TOOL_NAME, {"text": "still-here"}))
            checks["skip_token_isolates_protected_plugin"] = (
                skipped.plane_failed is False
                and skipped.live_names == ("live",)
                and "hosted" in skipped.isolated_names
                and sibling == "still-here"
            )
        finally:
            skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-http-auth-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_HTTP_AUTH_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_http_auth"] = (
        live_goal == MCP_HTTP_AUTH_GOAL
        and MCP_HTTP_AUTH_ID in live_done
        and live_source == "genesis_bind_http_auth"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_http_auth_capability()
    return {
        "ok": ok,
        "action": "mcp_http_auth",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_HTTP_AUTH_GOAL,
        "done_when": MCP_HTTP_AUTH_DONE_WHEN,
    }
