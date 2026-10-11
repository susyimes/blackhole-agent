"""Least-privilege bearer tokens for the live invocation plane.

A configured ``--token`` currently authorizes every mutating route: a CI
job that only needs one fixture tool can POST /invoke every untrusted
tool, import bundles, and drive goal sessions. This module closes that
hole with opt-in scoped bearers:

- ``--token-scope TOKEN=id[,id...]`` (repeatable) or ``BLACKHOLE_TOKEN_SCOPE``
  registers additional bearers that may invoke only the listed tool ids
- the operator ``--token`` stays unrestricted
- a disallowed POST /invoke is HTTP 403 ``tool_not_allowed`` and never
  spawns
- GET /capabilities for a scoped bearer lists only the allowed ids and
  includes ``token_scoped`` / ``token_allowlist``
- GET /console with that bearer embeds the same allowlist in the page
- a disallowed MCP ``tools/call`` name is JSON-RPC ``-32602`` and never
  spawns
- POST /solve plans only over those ids
- admin routes (bundles, contract, reproof, sessions) stay operator-only
- a plane without ``--token-scope`` keeps historical all-allow bearer
  behavior, so the hole stays falsifiable
"""

from __future__ import annotations

import contextvars
import hmac
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
TOKEN_SCOPE_ENV = "BLACKHOLE_TOKEN_SCOPE"
TOOL_NOT_ALLOWED = "tool_not_allowed"
ADMIN_REQUIRED = "admin_required"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:~-]{1,128}$")
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class TokenScopeError(ValueError):
    """Fail-closed refusal of a malformed token-scope configuration."""

    def __init__(self, detail: str) -> None:
        self.payload = {
            "ok": False,
            "error": "token_scope_invalid",
            "detail": str(detail),
        }
        super().__init__(detail)


@dataclass(frozen=True)
class TokenPrincipal:
    """Authenticated caller: unrestricted operator or a scoped allowlist."""

    unrestricted: bool
    allowed: frozenset[str] = frozenset()

    def allows(self, capability_id: str) -> bool:
        if self.unrestricted:
            return True
        return str(capability_id) in self.allowed


UNRESTRICTED = TokenPrincipal(unrestricted=True, allowed=frozenset())


@dataclass(frozen=True)
class TokenScopeTable:
    """Parsed scoped bearers. ``enabled`` is true when at least one exists."""

    entries: tuple[tuple[str, frozenset[str]], ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.entries)

    @property
    def count(self) -> int:
        return len(self.entries)

    def health(self) -> dict[str, Any]:
        return {
            "token_scopes": self.enabled,
            "token_scope_count": self.count,
        }


EMPTY_SCOPES = TokenScopeTable()

_PRINCIPAL: contextvars.ContextVar[TokenPrincipal] = contextvars.ContextVar(
    "bh_invocation_principal",
    default=UNRESTRICTED,
)


def current_principal() -> TokenPrincipal:
    return _PRINCIPAL.get()


def bind_principal(principal: TokenPrincipal) -> None:
    _PRINCIPAL.set(principal)


def reset_principal() -> None:
    _PRINCIPAL.set(UNRESTRICTED)


def principal_allowlist_payload(principal: TokenPrincipal | None = None) -> dict[str, Any]:
    """Public view of the current (or given) bearer's tool allowlist."""

    actor = current_principal() if principal is None else principal
    if actor.unrestricted:
        return {"scoped": False, "allow": None}
    return {"scoped": True, "allow": sorted(actor.allowed)}


def bind_optional_bearer(
    offered: str | None,
    operator: str,
    table: TokenScopeTable,
) -> TokenPrincipal:
    """Bind a principal for public pages such as GET /console.

    A missing or unrecognized bearer stays unrestricted so the HTML shell
    still loads; a recognized scoped bearer filters the embedded catalog.
    """

    reset_principal()
    if not offered:
        bind_principal(UNRESTRICTED)
        return UNRESTRICTED
    principal = authenticate_bearer(str(offered), operator, table)
    actor = UNRESTRICTED if principal is None else principal
    bind_principal(actor)
    return actor


def _compare(offered: str, expected: str) -> bool:
    return hmac.compare_digest(offered.encode("utf-8"), expected.encode("utf-8"))


def authenticate_bearer(
    offered: str,
    operator: str,
    table: TokenScopeTable,
) -> TokenPrincipal | None:
    """Return the principal for ``offered``, or None when no secret matches.

    Every registered secret is compared so a non-match does not short-circuit
    on the first mismatch. The operator token wins when it also appears as a
    scoped secret.
    """

    offered_text = str(offered or "")
    matched_operator = bool(operator) and _compare(offered_text, str(operator))
    matched_allowed: frozenset[str] | None = None
    for secret, allowed in table.entries:
        if _compare(offered_text, secret):
            matched_allowed = allowed
    if matched_operator:
        return UNRESTRICTED
    if matched_allowed is not None:
        return TokenPrincipal(unrestricted=False, allowed=matched_allowed)
    return None


def auth_is_required(operator: str, table: TokenScopeTable) -> bool:
    return bool(str(operator or "").strip()) or table.enabled


def parse_token_scope_clause(raw: str) -> tuple[str, frozenset[str]]:
    """Parse one ``TOKEN=id[,id...]`` clause."""

    text = str(raw or "").strip()
    if not text:
        raise TokenScopeError("token-scope clause is empty")
    if "=" not in text:
        raise TokenScopeError("token-scope clause must be TOKEN=id[,id...]")
    token, _, rest = text.partition("=")
    token = token.strip()
    if not _TOKEN_RE.fullmatch(token):
        raise TokenScopeError("token-scope secret must be 1-128 letters, digits, or ._:~-")
    ids = [part.strip() for part in rest.split(",") if part.strip()]
    if not ids:
        raise TokenScopeError("token-scope clause lists no tool ids")
    allowed: set[str] = set()
    for item in ids:
        if not _ID_RE.fullmatch(item):
            raise TokenScopeError(f"token-scope tool id is invalid: {item!r}")
        allowed.add(item)
    return token, frozenset(allowed)


def _from_mapping(payload: Mapping[str, Any]) -> list[tuple[str, frozenset[str]]]:
    parsed: list[tuple[str, frozenset[str]]] = []
    for token, value in payload.items():
        secret = str(token).strip()
        if not _TOKEN_RE.fullmatch(secret):
            raise TokenScopeError("token-scope secret must be 1-128 letters, digits, or ._:~-")
        if isinstance(value, str):
            ids = [part.strip() for part in value.split(",") if part.strip()]
        elif isinstance(value, (list, tuple)):
            ids = [str(item).strip() for item in value if str(item).strip()]
        else:
            raise TokenScopeError("token-scope allow list must be a string or array")
        if not ids:
            raise TokenScopeError("token-scope clause lists no tool ids")
        allowed: set[str] = set()
        for item in ids:
            if not _ID_RE.fullmatch(item):
                raise TokenScopeError(f"token-scope tool id is invalid: {item!r}")
            allowed.add(item)
        parsed.append((secret, frozenset(allowed)))
    return parsed


def _from_env_text(text: str) -> list[tuple[str, frozenset[str]]]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise TokenScopeError(f"BLACKHOLE_TOKEN_SCOPE is not JSON: {exc}") from exc
        if isinstance(payload, dict):
            return _from_mapping(payload)
        if isinstance(payload, list):
            parsed: list[tuple[str, frozenset[str]]] = []
            for item in payload:
                if isinstance(item, str):
                    parsed.append(parse_token_scope_clause(item))
                    continue
                if not isinstance(item, dict):
                    raise TokenScopeError("BLACKHOLE_TOKEN_SCOPE list entries must be objects or clauses")
                token = str(item.get("token") or "").strip()
                allow = item.get("allow")
                if not token:
                    raise TokenScopeError("token-scope object is missing token")
                parsed.extend(_from_mapping({token: allow}))
            return parsed
        raise TokenScopeError("BLACKHOLE_TOKEN_SCOPE JSON must be an object or array")
    return [parse_token_scope_clause(stripped)]


def resolve_token_scopes(
    explicit: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> TokenScopeTable:
    """Collect scoped bearers from CLI flags, else the process environment."""

    merged: dict[str, set[str]] = {}

    def add(token: str, allowed: frozenset[str]) -> None:
        merged.setdefault(token, set()).update(allowed)

    if explicit:
        for raw in explicit:
            token, allowed = parse_token_scope_clause(str(raw))
            add(token, allowed)
    else:
        source = env if env is not None else os.environ
        for token, allowed in _from_env_text(str(source.get(TOKEN_SCOPE_ENV) or "")):
            add(token, allowed)
    entries = tuple(
        (token, frozenset(allowed))
        for token, allowed in sorted(merged.items(), key=lambda item: item[0])
    )
    return TokenScopeTable(entries=entries)


def filter_invocable(
    invocable: Mapping[str, Any],
    principal: TokenPrincipal | None = None,
) -> dict[str, Any]:
    """Return the invocable subset the principal may see or plan over."""

    actor = UNRESTRICTED if principal is None else principal
    if actor.unrestricted:
        return dict(invocable)
    return {
        capability_id: item
        for capability_id, item in invocable.items()
        if actor.allows(capability_id)
    }


def tool_is_allowed(capability_id: Any, principal: TokenPrincipal | None = None) -> bool:
    """True when the principal may invoke ``capability_id``."""

    actor = current_principal() if principal is None else principal
    return actor.allows(str(capability_id or ""))


TOKEN_SCOPE_CONSOLE_MCP_ID = "capability.token-scope-console-mcp"
TOKEN_SCOPE_CONSOLE_MCP_NAME = "Scoped token console allowlist and MCP invalid-params"


def builtin_token_scope_console_mcp_proof() -> dict[str, Any]:
    """Hermetic proof: GET /console shows a scoped allowlist; MCP refuses others."""

    import html as html_lib
    import re
    import tempfile
    import threading
    from pathlib import Path
    from urllib import request as urlrequest
    from urllib.error import HTTPError, URLError

    from blackhole_agent.capability_compounder import legacy_pipeline_was_used
    from blackhole_agent.capability_service import build_server

    shout_id = "capability.absorbed-scope-shout"
    reverse_id = "capability.absorbed-text-reverser"
    operator = "operator-token-proof"
    scoped = "scoped-token-proof"
    probe_text = "scope-console-mcp"
    expected_reverse = probe_text[::-1]
    shout_output = "BLACKHOLE UNBOUND!"

    def write_workspace(root: Path) -> None:
        reverse_dir = root / "capabilities" / "absorbed" / "text-reverser"
        reverse_dir.mkdir(parents=True)
        (reverse_dir / "tool.py").write_text(
            "import json, sys\n"
            "state = json.load(sys.stdin)\n"
            "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n",
            encoding="utf-8",
        )
        (reverse_dir / "absorption.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "slug": "text-reverser",
                    "name": "probe text reverser",
                    "command": ["python", "tool.py"],
                    "requires": ["raw_text"],
                    "provides": ["reversed_text"],
                    "cases": [
                        {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
                        {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
                    ],
                }
            ),
            encoding="utf-8",
        )
        shout_dir = root / "capabilities" / "absorbed" / "scope-shout"
        shout_dir.mkdir(parents=True)
        (shout_dir / "tool.py").write_text(
            "import json, sys\n"
            "state = json.load(sys.stdin)\n"
            "print(json.dumps({'shout_output': state['text'].upper() + '!'}))\n",
            encoding="utf-8",
        )
        (shout_dir / "absorption.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "slug": "scope-shout",
                    "name": "probe scope shout",
                    "command": ["python", "tool.py"],
                    "requires": ["text"],
                    "provides": ["shout_output"],
                    "cases": [
                        {"input": {"text": "ab"}, "expect": {"shout_output": "AB!"}},
                        {"input": {"text": "cd"}, "expect": {"shout_output": "CD!"}},
                    ],
                }
            ),
            encoding="utf-8",
        )
        entry = {
            "kind": "python",
            "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
            "proof_command": "uv run python -c \"pass\"",
            "dependencies": [],
            "behavior_paths": [],
            "capability_delta": "",
            "tags": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "last_proved_at": "2026-01-01T00:00:00Z",
            "last_proof_exit_code": 0,
        }
        (root / "capabilities" / "ledger.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "updated_at": "",
                    "capabilities": {
                        reverse_id: dict(entry, id=reverse_id, name="probe text reverser"),
                        shout_id: dict(entry, id=shout_id, name="probe scope shout"),
                    },
                }
            ),
            encoding="utf-8",
        )

    def request(
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        *,
        token: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/json, text/event-stream")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urlrequest.urlopen(req, timeout=45) as response:
                captured = {key.lower(): value for key, value in response.headers.items()}
                raw = response.read().decode("utf-8")
                try:
                    parsed: Any = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    parsed = raw
                return response.status, parsed, captured
        except HTTPError as exc:
            captured = {
                key.lower(): value for key, value in (exc.headers.items() if exc.headers else [])
            }
            try:
                return exc.code, json.loads(exc.read().decode("utf-8")), captured
            except Exception:
                return exc.code, None, captured
        except (URLError, TimeoutError, OSError):
            return 0, None, {}

    def parse_allowlist(page: Any) -> dict[str, Any] | None:
        if not isinstance(page, str):
            return None
        match = re.search(r'<pre id="token-allowlist">(.*?)</pre>', page, re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(html_lib.unescape(match.group(1).strip()))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def mcp_session(mcp: str, token: str) -> str:
        _status, _body, headers = request(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "token-scope-console-mcp-proof", "version": "1"},
                },
            },
            token=token,
        )
        return str(headers.get("mcp-session-id") or "")

    def mcp_call(mcp: str, token: str, session: str, request_id: int, name: str, arguments: dict) -> Any:
        _status, body, _headers = request(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            token=token,
            headers={"Mcp-Session-Id": session},
        )
        return body

    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="token-scope-console-mcp-proof-") as directory:
        root = Path(directory) / "repo"
        write_workspace(root)
        scopes = resolve_token_scopes([f"{scoped}={shout_id}"])
        server = build_server(root, host="127.0.0.1", port=0, token=operator, token_scopes=scopes)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            mcp = f"{base}/mcp"
            health_status, health, _ = request("GET", f"{base}/health")
            checks["health"] = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("token_scopes") is True
            )
            console_status, page, headers = request("GET", f"{base}/console", token=scoped)
            allowlist = parse_allowlist(page)
            page_text = page if isinstance(page, str) else ""
            checks["console_allowlist"] = (
                console_status == 200
                and "text/html" in str(headers.get("content-type") or "")
                and isinstance(allowlist, dict)
                and allowlist.get("scoped") is True
                and allowlist.get("allow") == [shout_id]
                and shout_id in page_text
                and reverse_id not in page_text
            )
            session = mcp_session(mcp, scoped)
            shouted = mcp_call(
                mcp, scoped, session, 2, "scope-shout", {"text": "blackhole unbound"}
            )
            shout_result = shouted.get("result") if isinstance(shouted, dict) else None
            shout_structured = (
                shout_result.get("structuredContent") if isinstance(shout_result, dict) else None
            )
            checks["scoped_mcp_shout"] = (
                bool(session)
                and isinstance(shout_structured, dict)
                and shout_structured.get("shout_output") == shout_output
            )
            denied = mcp_call(
                mcp, scoped, session, 3, "text-reverser", {"raw_text": probe_text}
            )
            denied_error = denied.get("error") if isinstance(denied, dict) else None
            checks["scoped_mcp_invalid_params"] = (
                isinstance(denied_error, dict)
                and denied_error.get("code") == -32602
                and "tool not allowed" in str(denied_error.get("message") or "").lower()
                and expected_reverse not in json.dumps(denied)
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        closed_root = Path(directory) / "closed"
        write_workspace(closed_root)
        closed = build_server(closed_root, host="127.0.0.1", port=0, token=operator)
        closed_thread = threading.Thread(target=closed.serve_forever, daemon=True)
        closed_thread.start()
        try:
            closed_base = f"http://127.0.0.1:{closed.server_address[1]}"
            closed_health_status, closed_health, _ = request("GET", f"{closed_base}/health")
            closed_console_status, closed_page, _ = request(
                "GET", f"{closed_base}/console", token=operator
            )
            closed_allowlist = parse_allowlist(closed_page)
            closed_session = mcp_session(f"{closed_base}/mcp", operator)
            closed_reversed = mcp_call(
                f"{closed_base}/mcp",
                operator,
                closed_session,
                2,
                "text-reverser",
                {"raw_text": probe_text},
            )
            closed_result = (
                closed_reversed.get("result") if isinstance(closed_reversed, dict) else None
            )
            closed_structured = (
                closed_result.get("structuredContent") if isinstance(closed_result, dict) else None
            )
            checks["fail_closed"] = (
                closed_health_status == 200
                and isinstance(closed_health, dict)
                and closed_health.get("token_scopes") is False
                and closed_console_status == 200
                and (closed_allowlist is None or closed_allowlist.get("scoped") is not True)
                and isinstance(closed_structured, dict)
                and closed_structured.get("reversed_text") == expected_reverse
            )
        finally:
            closed.shutdown()
            closed.server_close()
            closed_thread.join(timeout=5)

    return {
        "ok": bool(checks) and all(checks.values()),
        "action": "token_scope_console_mcp",
        "checks": checks,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def ensure_token_scope_console_mcp_capability(*, repo_path: Path | None = None) -> Any:
    """Register the scoped-console / MCP invalid-params capability on the ledger."""

    from blackhole_agent.capability_compounder import (
        Capability,
        default_ledger_path,
        register_capability,
        save_ledger,
        load_ledger,
        utc_now_iso,
    )

    result = builtin_token_scope_console_mcp_proof()
    if not result.get("ok"):
        raise RuntimeError(f"token-scope console/MCP proof failed: {result}")
    root = Path(repo_path) if repo_path is not None else Path(__file__).resolve().parents[2]
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=TOKEN_SCOPE_CONSOLE_MCP_ID,
        name=TOKEN_SCOPE_CONSOLE_MCP_NAME,
        description=(
            "A scoped bearer loading GET /console sees only its allowed tool ids "
            "in the embedded catalog and token allowlist. MCP tools/call of a "
            "disallowed name is JSON-RPC -32602 invalid params and never spawns. "
            "A plane without --token-scope keeps historical all-allow behavior."
        ),
        kind="python",
        entry="blackhole_agent.invocation_token_scopes:builtin_token_scope_console_mcp_proof",
        proof_command=(
            "uv run python -c \"from blackhole_agent.invocation_token_scopes import "
            "builtin_token_scope_console_mcp_proof; r=builtin_token_scope_console_mcp_proof(); "
            "assert r['ok'] and r.get('action')=='token_scope_console_mcp' and "
            "all(r['checks'].values()) and not r.get('used_skill_route_discovery')\""
        ),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.ledger-invocation-plane",
        ),
        behavior_paths=(
            "src/blackhole_agent/invocation_token_scopes.py",
            "src/blackhole_agent/capability_console.py",
            "src/blackhole_agent/capability_service.py",
            "src/blackhole_agent/mcp_capability_server.py",
            "src/blackhole_agent/kernel_leftover.py",
        ),
        capability_delta=(
            "A scoped live-invocation bearer loading GET /console sees its tool "
            "allowlist in the served page, and MCP tools/call of a name outside "
            "that allowlist is JSON-RPC invalid-params without spawning the tool."
        ),
        tags=("invocation", "token-scope", "console", "mcp", "authorization"),
        source_mission_id="20261011T134105Z-8e2b3589",
        source_milestone=1,
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability
