"""Isolate a dead MCP initialize handshake so live plugins keep serving.

A single-session client can time out, but a multi-plugin plane that starts
handshakes sequentially still fails closed: one plugin whose initialize
response never arrives aborts remaining plugins and tears down ones that
already came up. The whole MCP plane stops serving.

This module closes that hole:

- handshake each plugin independently, concurrently
- isolate a hung or connection-closed initialize without failing the plane
- keep live servers serving tools
- leave the fail-closed sequential path available so the hole stays falsifiable
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

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
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
    is_mcp_transport_failure,
)

SCHEMA_VERSION = 1
MCP_HANDSHAKE_ID = "capability.mcp-handshake-isolation"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEAD_HANDSHAKE_TIMEOUT_SECONDS = 1.25
LIVE_HANDSHAKE_TIMEOUT_SECONDS = 20.0

MCP_HANDSHAKE_DONE_WHEN = (
    f"capability_exists:{MCP_HANDSHAKE_ID};"
    f"capability_proved:{MCP_HANDSHAKE_ID};"
    "no_skill_route"
)
MCP_HANDSHAKE_GOAL = (
    "Repair MCP client handshake isolation: a plugin whose initialize response "
    "never arrives still fails the whole MCP plane; isolate the dead handshake so "
    "live servers keep serving."
)


def hang_initialize_command() -> list[str]:
    """Plugin that never writes an initialize result."""

    return [sys.executable, "-c", "import time; time.sleep(3600)"]


def closed_initialize_command() -> list[str]:
    """Plugin whose process exits before an initialize result arrives."""

    return [sys.executable, "-c", "raise SystemExit(0)"]


class McpPluginSpec:
    """One named stdio plugin on the MCP plane."""

    def __init__(
        self,
        name: str,
        command: Sequence[str],
        *,
        timeout_seconds: float = LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    ) -> None:
        self.name = str(name)
        self.command = [str(part) for part in command]
        self.timeout_seconds = float(timeout_seconds)


class McpPluginPlane:
    """Connected MCP plugins after handshake, with dead slots isolated."""

    def __init__(self) -> None:
        self.plane_failed = False
        self.fail_error = ""
        self.isolate_hung_calls = True
        self._sessions: dict[str, McpStdioSession] = {}
        self._isolated: dict[str, str] = {}
        self._tools: dict[str, tuple[str, ...]] = {}

    @property
    def live_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._sessions))

    @property
    def isolated_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._isolated))

    def serving(self) -> bool:
        return bool(self._sessions)

    def isolated_error(self, name: str) -> str:
        return str(self._isolated.get(name) or "")

    def advertised_tools(self, name: str) -> tuple[str, ...]:
        return tuple(self._tools.get(name) or ())

    def call_tool(self, server: str, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(server)
        if session is None:
            error = self.isolated_error(server) or "unknown plugin"
            raise McpProtocolError(f"plugin {server!r} is not serving: {error}")
        try:
            return session.call_tool(name, arguments)
        except McpProtocolError as exc:
            if self.isolate_hung_calls and is_mcp_transport_failure(exc):
                self._accept_isolated(server, str(exc))
            raise

    def snapshot(self) -> dict[str, Any]:
        return {
            "plane_failed": self.plane_failed,
            "fail_error": self.fail_error,
            "live": list(self.live_names),
            "isolated": list(self.isolated_names),
            "serving": self.serving(),
            "isolated_errors": dict(self._isolated),
        }

    def close(self) -> None:
        for session in list(self._sessions.values()):
            session.kill()
        self._sessions.clear()

    def __enter__(self) -> "McpPluginPlane":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _accept_live(self, name: str, session: McpStdioSession, tools: Sequence[str] = ()) -> None:
        self._sessions[name] = session
        self._tools[name] = tuple(str(item) for item in tools if str(item))
        self._isolated.pop(name, None)

    def _accept_isolated(self, name: str, error: str) -> None:
        self._isolated[name] = str(error)
        session = self._sessions.pop(name, None)
        if session is not None:
            session.kill()
        self._tools.pop(name, None)


def connect_mcp_plane(
    plugins: Sequence[McpPluginSpec],
    *,
    isolate_dead: bool = True,
    isolate_hung_calls: bool = True,
) -> McpPluginPlane:
    """Connect a multi-plugin MCP plane.

    ``isolate_dead=True`` (default) handshakes plugins concurrently and keeps
    live servers serving when one initialize never arrives.
    ``isolate_dead=False`` is the fail-closed hole: any dead handshake aborts
    the whole plane, including plugins that already came up.

    ``isolate_hung_calls=True`` (default) isolates a plugin whose tools/list
    or tools/call never returns so sibling servers keep serving.
    ``isolate_hung_calls=False`` is the post-handshake hole: a hung tools/list
    is accepted as live with no tools, and a hung tools/call stays on the plane.
    """

    specs = list(plugins)
    names = [spec.name for spec in specs]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate MCP plugin names: {names}")
    plane = McpPluginPlane()
    plane.isolate_hung_calls = bool(isolate_hung_calls)
    if not isolate_dead:
        return _connect_fail_closed(plane, specs)
    return _connect_isolated(plane, specs)


def _record_live(plane: McpPluginPlane, spec: McpPluginSpec, session: McpStdioSession) -> None:
    tools: tuple[str, ...] = ()
    try:
        payload = session.list_tools()
        tools = tuple(
            str(item.get("name") or "")
            for item in (payload.get("tools") or [])
            if isinstance(item, Mapping) and item.get("name")
        )
    except McpProtocolError:
        tools = ()
    plane._accept_live(spec.name, session, tools)


def _handshake_session(spec: McpPluginSpec) -> tuple[McpStdioSession | None, str]:
    session = McpStdioSession(spec.command, timeout_seconds=spec.timeout_seconds)
    try:
        session.start()
        return session, ""
    except Exception as exc:
        session.kill()
        return None, str(exc)


def _connect_fail_closed(plane: McpPluginPlane, specs: Sequence[McpPluginSpec]) -> McpPluginPlane:
    started: list[tuple[McpPluginSpec, McpStdioSession]] = []
    try:
        for spec in specs:
            session, error = _handshake_session(spec)
            if session is None:
                raise McpProtocolError(error or f"handshake failed for {spec.name}")
            started.append((spec, session))
        for spec, session in started:
            _record_live(plane, spec, session)
        return plane
    except Exception as exc:
        for _, session in started:
            session.kill()
        plane.plane_failed = True
        plane.fail_error = str(exc)
        for spec in specs:
            plane._accept_isolated(spec.name, f"plane failed closed: {exc}")
        return plane


def _connect_isolated(plane: McpPluginPlane, specs: Sequence[McpPluginSpec]) -> McpPluginPlane:
    results: dict[str, tuple[McpStdioSession | None, str]] = {}
    lock = threading.Lock()

    def worker(spec: McpPluginSpec) -> None:
        session, error = _handshake_session(spec)
        with lock:
            results[spec.name] = (session, error)

    threads = [threading.Thread(target=worker, args=(spec,), daemon=True) for spec in specs]
    for thread in threads:
        thread.start()
    budget = max((spec.timeout_seconds for spec in specs), default=LIVE_HANDSHAKE_TIMEOUT_SECONDS) + 10.0
    for thread in threads:
        thread.join(timeout=budget)

    pending: list[tuple[McpPluginSpec, McpStdioSession]] = []
    for spec in specs:
        recorded = results.get(spec.name)
        if recorded is None:
            plane._accept_isolated(spec.name, "handshake worker did not finish")
            continue
        session, error = recorded
        if session is None:
            plane._accept_isolated(spec.name, error or "initialize response never arrived")
            continue
        pending.append((spec, session))

    if not plane.isolate_hung_calls:
        for spec, session in pending:
            _record_live(plane, spec, session)
        return plane

    discovery: dict[str, tuple[tuple[str, ...] | None, str]] = {}

    def discover(spec: McpPluginSpec, session: McpStdioSession) -> None:
        try:
            payload = session.list_tools()
            tools = tuple(
                str(item.get("name") or "")
                for item in (payload.get("tools") or [])
                if isinstance(item, Mapping) and item.get("name")
            )
            with lock:
                discovery[spec.name] = (tools, "")
        except Exception as exc:
            with lock:
                discovery[spec.name] = (None, str(exc))

    discover_threads = [
        threading.Thread(target=discover, args=(spec, session), daemon=True)
        for spec, session in pending
    ]
    for thread in discover_threads:
        thread.start()
    discover_budget = max(
        (spec.timeout_seconds for spec, _ in pending),
        default=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    ) + 10.0
    for thread in discover_threads:
        thread.join(timeout=discover_budget)

    for spec, session in pending:
        recorded_discovery = discovery.get(spec.name)
        if recorded_discovery is None:
            plane._accept_isolated(spec.name, "tools/list never returned")
            session.kill()
            continue
        tools, error = recorded_discovery
        if tools is None:
            plane._accept_isolated(spec.name, error or "tools/list never returned")
            session.kill()
            continue
        plane._accept_live(spec.name, session, tools)
    return plane


def mcp_handshake_isolation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_handshake_isolation import "
        "builtin_mcp_handshake_isolation_proof; r=builtin_mcp_handshake_isolation_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_handshake_isolation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_handshake_isolation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_HANDSHAKE_ID,
        name="MCP client handshake isolation",
        description=(
            "A multi-plugin MCP plane isolates a plugin whose initialize "
            "response never arrives so live servers keep serving tools instead "
            "of failing the whole plane."
        ),
        kind="python",
        entry="blackhole_agent.mcp_handshake_isolation:builtin_mcp_handshake_isolation_proof",
        proof_command=mcp_handshake_isolation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A plugin whose initialize response never arrives is isolated on "
            "the MCP plane; live servers keep serving instead of the whole "
            "plane failing closed with them."
        ),
        tags=("mcp", "handshake", "isolation", "resilience", "client"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260830T014112Z-78a7bd2d",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_spec(name: str) -> McpPluginSpec:
    return McpPluginSpec(name, echo_server_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)


def _hang_spec(name: str) -> McpPluginSpec:
    return McpPluginSpec(name, hang_initialize_command(), timeout_seconds=DEAD_HANDSHAKE_TIMEOUT_SECONDS)


def _closed_spec(name: str) -> McpPluginSpec:
    return McpPluginSpec(name, closed_initialize_command(), timeout_seconds=DEAD_HANDSHAKE_TIMEOUT_SECONDS)


def _echo_text(plane: McpPluginPlane, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, "echo", {"text": text}))


def builtin_mcp_handshake_isolation_proof() -> dict[str, Any]:
    """Hermetic proof: a dead initialize is isolated; live servers keep serving."""

    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_HANDSHAKE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_HANDSHAKE_GOAL) == (MCP_HANDSHAKE_ID,)
    checks["schema_version"] = SCHEMA_VERSION == 1

    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG

    checks["catalog_names_handshake"] = DIVERSITY_CATALOG[3]["id"] == MCP_HANDSHAKE_ID

    naive_hang_first = connect_mcp_plane(
        [_hang_spec("dead"), _echo_spec("live")],
        isolate_dead=False,
    )
    try:
        checks["naive_hang_first_fails_plane"] = (
            naive_hang_first.plane_failed is True
            and naive_hang_first.serving() is False
            and naive_hang_first.live_names == ()
            and "dead" in naive_hang_first.isolated_names
            and "live" in naive_hang_first.isolated_names
        )
    finally:
        naive_hang_first.close()

    naive_live_first = connect_mcp_plane(
        [_echo_spec("live"), _hang_spec("dead")],
        isolate_dead=False,
    )
    try:
        checks["naive_live_first_tears_down"] = (
            naive_live_first.plane_failed is True
            and naive_live_first.serving() is False
            and naive_live_first.live_names == ()
        )
    finally:
        naive_live_first.close()

    isolated_hang = connect_mcp_plane(
        [_hang_spec("dead"), _echo_spec("live")],
        isolate_dead=True,
    )
    try:
        served = _echo_text(isolated_hang, "live", "keep-serving")
        dead_raised = False
        try:
            isolated_hang.call_tool("dead", "echo", {"text": "nope"})
        except McpProtocolError:
            dead_raised = True
        checks["isolated_hang_keeps_live"] = (
            isolated_hang.plane_failed is False
            and isolated_hang.serving() is True
            and isolated_hang.live_names == ("live",)
            and isolated_hang.isolated_names == ("dead",)
            and served == "keep-serving"
            and "echo" in isolated_hang.advertised_tools("live")
            and dead_raised
        )
        checks["isolated_call_on_dead_raises"] = dead_raised
    finally:
        isolated_hang.close()

    isolated_mixed = connect_mcp_plane(
        [_echo_spec("alpha"), _hang_spec("dead"), _echo_spec("beta")],
        isolate_dead=True,
    )
    try:
        alpha = _echo_text(isolated_mixed, "alpha", "from-alpha")
        beta = _echo_text(isolated_mixed, "beta", "from-beta")
        checks["isolated_mixed_two_live"] = (
            isolated_mixed.plane_failed is False
            and isolated_mixed.live_names == ("alpha", "beta")
            and isolated_mixed.isolated_names == ("dead",)
            and alpha == "from-alpha"
            and beta == "from-beta"
        )
    finally:
        isolated_mixed.close()

    isolated_closed = connect_mcp_plane(
        [_closed_spec("dead"), _echo_spec("live")],
        isolate_dead=True,
    )
    try:
        served = _echo_text(isolated_closed, "live", "after-closed")
        closed_error = isolated_closed.isolated_error("dead").lower()
        checks["isolated_closed_initialize_keeps_live"] = (
            isolated_closed.plane_failed is False
            and isolated_closed.live_names == ("live",)
            and isolated_closed.isolated_names == ("dead",)
            and served == "after-closed"
            and bool(closed_error)
        )
    finally:
        isolated_closed.close()

    isolated_all_live = connect_mcp_plane([_echo_spec("only")], isolate_dead=True)
    try:
        checks["isolated_all_live"] = (
            isolated_all_live.plane_failed is False
            and isolated_all_live.live_names == ("only",)
            and isolated_all_live.isolated_names == ()
            and _echo_text(isolated_all_live, "only", "solo") == "solo"
        )
    finally:
        isolated_all_live.close()

    isolated_all_dead = connect_mcp_plane([_hang_spec("dead")], isolate_dead=True)
    try:
        checks["isolated_all_dead_does_not_fail_plane"] = (
            isolated_all_dead.plane_failed is False
            and isolated_all_dead.serving() is False
            and isolated_all_dead.isolated_names == ("dead",)
        )
    finally:
        isolated_all_dead.close()

    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_handshake_isolation_capability()
    return {
        "ok": ok,
        "action": "mcp_handshake_isolation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_HANDSHAKE_GOAL,
        "done_when": MCP_HANDSHAKE_DONE_WHEN,
    }
