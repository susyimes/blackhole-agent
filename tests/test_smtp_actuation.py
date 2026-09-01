from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_tools_list_changed import (
    MCP_TOOLS_CHANGED_GOAL,
    MCP_TOOLS_CHANGED_ID,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.smtp_actuation import (
    SENTINEL,
    SMTP_ACTUATION_DONE_WHEN,
    SMTP_ACTUATION_GOAL,
    SMTP_ACTUATION_ID,
    builtin_smtp_actuation_proof,
    independent_smtp_mailbox,
    run_smtp_workflow,
)
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    SMTP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    smtp_tool_descriptor,
)
from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID


def test_goal_binds_smtp_actuation_plane() -> None:
    assert leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    assert SMTP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL) == (MCP_TOOLS_CHANGED_ID,)
    assert leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (WEBHOOK_ACTUATION_ID,)
    assert leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (GMAIL_ACTUATION_ID,)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(WEBHOOK_ACTUATION_GOAL)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(GMAIL_ACTUATION_GOAL)
    assert MCP_TOOLS_CHANGED_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert WEBHOOK_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert GMAIL_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(SMTP_ACTUATION_GOAL),
            semantic_signature(WEBHOOK_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(SMTP_ACTUATION_GOAL),
            semantic_signature(GMAIL_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(SMTP_ACTUATION_GOAL),
            semantic_signature(MCP_TOOLS_CHANGED_GOAL),
        )
        < 0.82
    )


def test_opted_in_smtp_tool_completes_envelope_gated_workflow() -> None:
    descriptor = smtp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SMTP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("smtp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SMTP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["smtp"]

    missing = run_smtp_workflow(with_secret=False)
    unauth = run_smtp_workflow(authenticate=False)
    wrong = run_smtp_workflow(password="wrong-password")
    live = run_smtp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "auth_gated"
    assert unauth["final_status"] == 530
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_smtp_mailbox(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["authenticated"] is True


def test_builtin_proof_seals_smtp_actuation() -> None:
    report = builtin_smtp_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "smtp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_smtp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unauthenticated_mail_from_is_forbidden"]
    assert report["checks"]["wrong_password_is_forbidden"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_mailbox"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_smtp"]
    assert report["mission_goal"] == SMTP_ACTUATION_GOAL
    assert report["done_when"] == SMTP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[SMTP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "smtp" in capability.tags
    assert "envelope" in capability.tags


def test_selection_gate_accepts_smtp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        SMTP_ACTUATION_GOAL,
        SMTP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(SMTP_ACTUATION_GOAL)
    assert "smtp" in family
    assert "webhook" not in family
    assert "catalog" not in family
    assert "timeout" not in family
    assert "git-publication" not in family
    assert "browser" not in family
    assert not family.startswith("kernel-runtime")
