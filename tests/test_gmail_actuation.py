from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.browser_actuation import BROWSER_ACTUATION_GOAL, BROWSER_ACTUATION_ID
from blackhole_agent.publication_resilience import PUBLICATION_RESILIENCE_GOAL, PUBLICATION_RESILIENCE_ID
from blackhole_agent.gmail_actuation import (
    GMAIL_ACTUATION_DONE_WHEN,
    GMAIL_ACTUATION_GOAL,
    GMAIL_ACTUATION_ID,
    SENTINEL,
    builtin_gmail_actuation_proof,
    run_gmail_workflow,
)
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    GMAIL_TOOL_PROVIDER,
    build_tool_routing_preflight,
    gmail_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_gmail_actuation_plane() -> None:
    assert leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (GMAIL_ACTUATION_ID,)
    assert GMAIL_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(BROWSER_ACTUATION_GOAL) == (BROWSER_ACTUATION_ID,)
    assert leftover_marker_ids(PUBLICATION_RESILIENCE_GOAL) == (PUBLICATION_RESILIENCE_ID,)
    assert GMAIL_ACTUATION_ID not in leftover_marker_ids(BROWSER_ACTUATION_GOAL)
    assert GMAIL_ACTUATION_ID not in leftover_marker_ids(PUBLICATION_RESILIENCE_GOAL)


def test_opted_in_gmail_tool_completes_label_gated_workflow() -> None:
    descriptor = gmail_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GMAIL_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("gmail",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GMAIL_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["gmail"]

    blocked = run_gmail_workflow(authed=False)
    unlabeled = run_gmail_workflow(skip_label=True)
    live = run_gmail_workflow()
    assert blocked["ok"] is False
    assert blocked["final_status"] == 403
    assert unlabeled["ok"] is False
    assert unlabeled["error"] == "label_gated"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["labelled"] is True


def test_builtin_proof_seals_gmail_actuation() -> None:
    report = builtin_gmail_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "gmail_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_gmail"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_auth_is_forbidden"]
    assert report["checks"]["unlabelled_draft_is_forbidden"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_seals_draft"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_gmail"]
    assert report["mission_goal"] == GMAIL_ACTUATION_GOAL
    assert report["done_when"] == GMAIL_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[GMAIL_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "gmail" in capability.tags
    assert "auth" in capability.tags
