from pathlib import Path

from blackhole_agent.browser_cdp_actuation import BROWSER_CDP_GOAL, BROWSER_CDP_ID
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
from blackhole_agent.github_actuation import (
    GITHUB_ACTUATION_DONE_WHEN,
    GITHUB_ACTUATION_GOAL,
    GITHUB_ACTUATION_ID,
    OPEN_ISSUE_NUMBER,
    SENTINEL,
    builtin_github_actuation_proof,
    run_github_workflow,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    GITHUB_TOOL_PROVIDER,
    build_tool_routing_preflight,
    github_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_github_actuation_plane() -> None:
    assert leftover_marker_ids(GITHUB_ACTUATION_GOAL) == (GITHUB_ACTUATION_ID,)
    assert GITHUB_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (GMAIL_ACTUATION_ID,)
    assert leftover_marker_ids(BROWSER_CDP_GOAL) == (BROWSER_CDP_ID,)
    assert GITHUB_ACTUATION_ID not in leftover_marker_ids(GMAIL_ACTUATION_GOAL)
    assert GITHUB_ACTUATION_ID not in leftover_marker_ids(BROWSER_CDP_GOAL)
    assert GMAIL_ACTUATION_ID not in leftover_marker_ids(GITHUB_ACTUATION_GOAL)
    assert BROWSER_CDP_ID not in leftover_marker_ids(GITHUB_ACTUATION_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(GITHUB_ACTUATION_GOAL),
            semantic_signature(GMAIL_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(GITHUB_ACTUATION_GOAL),
            semantic_signature(BROWSER_CDP_GOAL),
        )
        < 0.82
    )


def test_opted_in_github_tool_completes_issue_gated_workflow() -> None:
    descriptor = github_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GITHUB_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("github",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GITHUB_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["github"]

    blocked = run_github_workflow(authed=False)
    unlabeled = run_github_workflow(skip_label=True)
    live = run_github_workflow()
    assert blocked["ok"] is False
    assert blocked["final_status"] == 403
    assert blocked["error"] == "unauthenticated"
    assert unlabeled["ok"] is False
    assert unlabeled["error"] == "label_gated"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["labelled"] is True
    assert live["issue_state"] == "closed"
    assert f"Closes #{OPEN_ISSUE_NUMBER}" in live["pr_body"]


def test_builtin_proof_seals_github_actuation() -> None:
    report = builtin_github_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "github_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_github"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_auth_is_forbidden"]
    assert report["checks"]["unlabelled_pr_is_forbidden"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_seals_pull_request"]
    assert report["checks"]["workflow_closes_labelled_issue"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_github"]
    assert report["mission_goal"] == GITHUB_ACTUATION_GOAL
    assert report["done_when"] == GITHUB_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[GITHUB_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "github" in capability.tags
    assert "pull-request" in capability.tags


def test_selection_gate_accepts_git_publication_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        GITHUB_ACTUATION_GOAL,
        GITHUB_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(GITHUB_ACTUATION_GOAL)
    assert "git-publication" in family
    assert "browser" not in family
    assert "timeout" not in family
    assert not family.startswith("kernel-runtime")
