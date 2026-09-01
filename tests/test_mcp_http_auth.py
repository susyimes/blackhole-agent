from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import McpProtocolError, _extract_text, echo_server_command
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_http_auth import (
    DEFAULT_CLIENT_ID,
    DEFAULT_CLIENT_SECRET,
    MCP_HTTP_AUTH_DONE_WHEN,
    MCP_HTTP_AUTH_GOAL,
    MCP_HTTP_AUTH_ID,
    UNLOCK_TOKEN,
    builtin_mcp_http_auth_proof,
    is_mcp_http_unauthorized,
    parse_www_authenticate,
    start_protected_mcp_server,
)
from blackhole_agent.mcp_http_transport import (
    MCP_HTTP_GOAL,
    MCP_HTTP_ID,
    McpHttpSession,
    start_http_echo_server,
)
from blackhole_agent.mcp_tools_list_changed import MCP_TOOLS_CHANGED_GOAL, MCP_TOOLS_CHANGED_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID


def test_goal_binds_http_auth_plane() -> None:
    assert leftover_marker_ids(MCP_HTTP_AUTH_GOAL) == (MCP_HTTP_AUTH_ID,)
    assert MCP_HTTP_AUTH_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    assert leftover_marker_ids(MCP_HTTP_GOAL) == (MCP_HTTP_ID,)
    assert leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL) == (MCP_TOOLS_CHANGED_ID,)
    assert leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (WEBHOOK_ACTUATION_ID,)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(MCP_HTTP_AUTH_GOAL)
    assert MCP_HTTP_ID not in leftover_marker_ids(MCP_HTTP_AUTH_GOAL)
    assert MCP_HTTP_AUTH_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert MCP_HTTP_AUTH_ID not in leftover_marker_ids(MCP_HTTP_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_HTTP_AUTH_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MCP_HTTP_AUTH_GOAL),
            semantic_signature(MCP_HTTP_GOAL),
        )
        < 0.82
    )


def test_parse_www_authenticate_extracts_resource_metadata() -> None:
    parsed = parse_www_authenticate(
        'Bearer realm="mcp", resource_metadata="http://127.0.0.1:9/.well-known/oauth-protected-resource"'
    )
    assert parsed["scheme"] == "Bearer"
    assert parsed["realm"] == "mcp"
    assert parsed["resource_metadata"].endswith("oauth-protected-resource")


def test_skip_token_stays_401_and_bearer_unlocks_echo() -> None:
    with start_protected_mcp_server() as hosted:
        naive = McpHttpSession(hosted.mcp_url, timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
        try:
            try:
                naive.start()
                raise AssertionError("unauthenticated initialize should 401")
            except McpProtocolError as exc:
                assert is_mcp_http_unauthorized(exc)
                assert "resource_metadata" in exc.www_authenticate
        finally:
            naive.kill()

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
            echoed = _extract_text(live.call_tool("echo", {"text": "auth-ok"}))
            assert live.server_info["name"] == "blackhole-protected-mcp"
            assert echoed == f"auth-ok|{UNLOCK_TOKEN}"
            assert live.access_token
        finally:
            live.kill()


def test_skip_token_isolates_protected_plugin_beside_stdio() -> None:
    with start_protected_mcp_server() as hosted:
        plane = connect_mcp_plane(
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
            assert plane.plane_failed is False
            assert plane.live_names == ("live",)
            assert "hosted" in plane.isolated_names
            assert _extract_text(plane.call_tool("live", "echo", {"text": "sibling"})) == "sibling"
        finally:
            plane.close()


def test_open_http_echo_still_serves_without_bearer() -> None:
    with start_http_echo_server() as hosted:
        session = McpHttpSession(hosted.url, timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
        try:
            session.start()
            assert _extract_text(session.call_tool("echo", {"text": "open"})) == "open"
        finally:
            session.kill()


def test_builtin_proof_seals_http_auth() -> None:
    report = builtin_mcp_http_auth_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_http_auth"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_without_token_is_401"]
    assert report["checks"]["missing_client_secret_stays_401"]
    assert report["checks"]["wrong_bearer_is_401"]
    assert report["checks"]["bearer_gated_tool_call_succeeds"]
    assert report["checks"]["mixed_bearer_http_and_stdio_serve"]
    assert report["checks"]["skip_token_isolates_protected_plugin"]
    assert report["checks"]["exhausted_catalog_binds_http_auth"]
    assert report["mission_goal"] == MCP_HTTP_AUTH_GOAL
    assert report["done_when"] == MCP_HTTP_AUTH_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_HTTP_AUTH_ID]
    assert capability.last_proof_exit_code == 0
    assert "oauth" in capability.tags
    assert "bearer" in capability.tags


def test_selection_gate_accepts_http_auth_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_HTTP_AUTH_GOAL,
        MCP_HTTP_AUTH_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_HTTP_AUTH_GOAL)
    assert "bearer" in family
    assert "authorization" in family
    assert "smtp" not in family
    assert "webhook" not in family
    assert "catalog" not in family
    assert "timeout" not in family
