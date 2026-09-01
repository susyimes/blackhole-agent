from pathlib import Path

from blackhole_agent.browser_actuation import BROWSER_ACTUATION_GOAL, BROWSER_ACTUATION_ID
from blackhole_agent.browser_cdp_actuation import (
    BROWSER_CDP_DONE_WHEN,
    BROWSER_CDP_GOAL,
    BROWSER_CDP_ID,
    DEFAULT_NOTE,
    MISSING_ERROR,
    SENTINEL,
    SHELL_STATUS,
    builtin_browser_cdp_actuation_proof,
    evaluate_page_scripts,
    run_cdp_workflow,
    run_urllib_js_gated_workflow,
    start_js_gated_app,
    _index_page,
    _login_page,
)
from blackhole_agent.browser_actuation import parse_forms, parse_links
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_roots_list_changed import MCP_ROOTS_CHANGED_GOAL, MCP_ROOTS_CHANGED_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_javascript_cdp_plane() -> None:
    assert leftover_marker_ids(BROWSER_CDP_GOAL) == (BROWSER_CDP_ID,)
    assert BROWSER_CDP_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(BROWSER_ACTUATION_GOAL) == (BROWSER_ACTUATION_ID,)
    assert leftover_marker_ids(MCP_ROOTS_CHANGED_GOAL) == (MCP_ROOTS_CHANGED_ID,)
    assert BROWSER_CDP_ID not in leftover_marker_ids(BROWSER_ACTUATION_GOAL)
    assert BROWSER_CDP_ID not in leftover_marker_ids(MCP_ROOTS_CHANGED_GOAL)
    assert BROWSER_ACTUATION_ID not in leftover_marker_ids(BROWSER_CDP_GOAL)
    assert MCP_ROOTS_CHANGED_ID not in leftover_marker_ids(BROWSER_CDP_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(BROWSER_CDP_GOAL),
            semantic_signature(BROWSER_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(BROWSER_CDP_GOAL),
            semantic_signature(MCP_ROOTS_CHANGED_GOAL),
        )
        < 0.82
    )


def test_page_source_hides_controls_until_evaluate() -> None:
    source = _index_page() + _login_page()
    assert "<a " not in source
    assert "<form" not in source
    assert not parse_links(_index_page())
    assert not parse_forms(_login_page())
    rendered = evaluate_page_scripts(_index_page())
    assert any(text == "Sign in" for _href, text in parse_links(rendered))
    login = evaluate_page_scripts(_login_page())
    assert parse_forms(login)


def test_urllib_cannot_open_javascript_gated_portal() -> None:
    with start_js_gated_app() as app:
        blocked = run_urllib_js_gated_workflow(app.url)
    assert blocked["ok"] is False
    assert blocked["status_text"] == SHELL_STATUS
    assert blocked["has_sign_in"] is False
    assert "no link labelled" in blocked["error"]


def test_skip_evaluate_stays_on_shell() -> None:
    with start_js_gated_app() as app:
        skipped = run_cdp_workflow(app.url, evaluate_scripts=False)
    assert skipped["ok"] is False
    assert skipped["scripts_evaluated"] == 0
    assert MISSING_ERROR in skipped["error"]
    assert skipped["status_text"] == SHELL_STATUS


def test_cdp_evaluate_unlocks_javascript_gated_workflow() -> None:
    with start_js_gated_app() as app:
        live = run_cdp_workflow(app.url)
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["echo"] == DEFAULT_NOTE
    assert "Runtime.evaluate" in live["methods"]
    assert live["scripts_evaluated"] >= 3


def test_builtin_proof_seals_javascript_cdp_actuation() -> None:
    report = builtin_browser_cdp_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "browser_cdp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["urllib_stays_on_shell"]
    assert report["checks"]["skip_evaluate_is_error"]
    assert report["checks"]["cdp_evaluate_unlocks"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_echoes_note"]
    assert report["checks"]["source_has_no_html_controls"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_browser_cdp"]
    assert report["mission_goal"] == BROWSER_CDP_GOAL
    assert report["done_when"] == BROWSER_CDP_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[BROWSER_CDP_ID]
    assert capability.last_proof_exit_code == 0
    assert "browser" in capability.tags
    assert "cdp" in capability.tags
    assert "javascript" in capability.tags


def test_selection_gate_accepts_browser_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        BROWSER_CDP_GOAL,
        BROWSER_CDP_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(BROWSER_CDP_GOAL)
    assert "browser" in family
    assert "timeout" not in family
    assert "worktree" not in family
    assert not family.startswith("kernel-runtime")
