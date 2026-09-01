from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
from blackhole_agent.imap_actuation import (
    IMAP_ACTUATION_DONE_WHEN,
    IMAP_ACTUATION_GOAL,
    IMAP_ACTUATION_ID,
    SENTINEL,
    builtin_imap_actuation_proof,
    independent_imap_inbox,
    run_imap_workflow,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_http_auth import MCP_HTTP_AUTH_GOAL, MCP_HTTP_AUTH_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    IMAP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    imap_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_imap_actuation_plane() -> None:
    assert leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    assert IMAP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    assert leftover_marker_ids(MCP_HTTP_AUTH_GOAL) == (MCP_HTTP_AUTH_ID,)
    assert leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (GMAIL_ACTUATION_ID,)
    assert IMAP_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert IMAP_ACTUATION_ID not in leftover_marker_ids(MCP_HTTP_AUTH_GOAL)
    assert IMAP_ACTUATION_ID not in leftover_marker_ids(GMAIL_ACTUATION_GOAL)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    assert MCP_HTTP_AUTH_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    assert GMAIL_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(IMAP_ACTUATION_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(IMAP_ACTUATION_GOAL),
            semantic_signature(MCP_HTTP_AUTH_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(IMAP_ACTUATION_GOAL),
            semantic_signature(GMAIL_ACTUATION_GOAL),
        )
        < 0.82
    )


def test_opted_in_imap_tool_completes_uid_idle_workflow() -> None:
    descriptor = imap_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IMAP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("imap",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IMAP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["imap"]

    missing = run_imap_workflow(with_secret=False)
    unauth = run_imap_workflow(authenticate=False)
    wrong = run_imap_workflow(password="wrong-password")
    skip_idle = run_imap_workflow(idle=False)
    live = run_imap_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "auth_gated"
    assert unauth["final_status"] == 530
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_idle["ok"] is False
    assert skip_idle["error"] == "idle_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_imap_inbox(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["authenticated"] is True
    assert row["idled"] is True
    assert int(row["uid"]) >= 1


def test_builtin_proof_seals_imap_actuation() -> None:
    report = builtin_imap_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "imap_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_imap"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unauthenticated_select_is_forbidden"]
    assert report["checks"]["wrong_password_is_forbidden"]
    assert report["checks"]["skip_idle_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_inbox"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_imap"]
    assert report["mission_goal"] == IMAP_ACTUATION_GOAL
    assert report["done_when"] == IMAP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[IMAP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "imap" in capability.tags
    assert "idle" in capability.tags


def test_selection_gate_accepts_imap_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        IMAP_ACTUATION_GOAL,
        IMAP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(IMAP_ACTUATION_GOAL)
    assert "imap" in family
    assert "smtp" not in family
    assert "webhook" not in family
    assert "catalog" not in family
    assert "timeout" not in family
    assert "git-publication" not in family
    assert "browser" not in family
    assert "bearer" not in family
    assert not family.startswith("kernel-runtime")
