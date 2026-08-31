from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_http_event_stream import MCP_HTTP_EVENT_GOAL, MCP_HTTP_EVENT_ID
from blackhole_agent.publication_resilience import PUBLICATION_RESILIENCE_GOAL, PUBLICATION_RESILIENCE_ID
from blackhole_agent.browser_actuation import (
    BROWSER_ACTUATION_DONE_WHEN,
    BROWSER_ACTUATION_GOAL,
    BROWSER_ACTUATION_ID,
    SENTINEL,
    builtin_browser_actuation_proof,
    start_fixture_app,
    run_browser_workflow,
)
from blackhole_agent.tool_routing import (
    BROWSER_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    browser_tool_descriptor,
    build_tool_routing_preflight,
    route_tool_descriptor,
)


def test_goal_binds_browser_actuation_plane() -> None:
    assert leftover_marker_ids(BROWSER_ACTUATION_GOAL) == (BROWSER_ACTUATION_ID,)
    assert BROWSER_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(PUBLICATION_RESILIENCE_GOAL) == (PUBLICATION_RESILIENCE_ID,)
    assert leftover_marker_ids(MCP_HTTP_EVENT_GOAL) == (MCP_HTTP_EVENT_ID,)
    assert BROWSER_ACTUATION_ID not in leftover_marker_ids(PUBLICATION_RESILIENCE_GOAL)
    assert BROWSER_ACTUATION_ID not in leftover_marker_ids(MCP_HTTP_EVENT_GOAL)


def test_opted_in_browser_tool_completes_cookie_gated_workflow() -> None:
    descriptor = browser_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BROWSER_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("browser",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BROWSER_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["browser"]

    with start_fixture_app() as app:
        blocked = run_browser_workflow(app.url, send_cookies=False)
        live = run_browser_workflow(app.url)
    assert blocked["ok"] is False
    assert blocked["final_status"] == 403
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["echo"] == "sealed-note"


def test_builtin_proof_seals_browser_actuation() -> None:
    report = builtin_browser_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "browser_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_browser"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_cookies_is_forbidden"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_echoes_note"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_browser"]
    assert report["mission_goal"] == BROWSER_ACTUATION_GOAL
    assert report["done_when"] == BROWSER_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[BROWSER_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "browser" in capability.tags
    assert "actuation" in capability.tags
