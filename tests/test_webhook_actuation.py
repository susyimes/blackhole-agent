from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    WEBHOOK_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    webhook_tool_descriptor,
)
from blackhole_agent.webhook_actuation import (
    SENTINEL,
    WEBHOOK_ACTUATION_DONE_WHEN,
    WEBHOOK_ACTUATION_GOAL,
    WEBHOOK_ACTUATION_ID,
    builtin_webhook_actuation_proof,
    independent_webhook_payload,
    run_webhook_workflow,
)


def test_goal_binds_webhook_actuation_plane() -> None:
    assert leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (WEBHOOK_ACTUATION_ID,)
    assert WEBHOOK_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (SQLITE_ACTUATION_ID,)
    assert leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (GMAIL_ACTUATION_ID,)
    assert WEBHOOK_ACTUATION_ID not in leftover_marker_ids(SQLITE_ACTUATION_GOAL)
    assert WEBHOOK_ACTUATION_ID not in leftover_marker_ids(GMAIL_ACTUATION_GOAL)
    assert SQLITE_ACTUATION_ID not in leftover_marker_ids(WEBHOOK_ACTUATION_GOAL)
    assert GMAIL_ACTUATION_ID not in leftover_marker_ids(WEBHOOK_ACTUATION_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(WEBHOOK_ACTUATION_GOAL),
            semantic_signature(SQLITE_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(WEBHOOK_ACTUATION_GOAL),
            semantic_signature(GMAIL_ACTUATION_GOAL),
        )
        < 0.82
    )


def test_opted_in_webhook_tool_completes_hmac_gated_workflow() -> None:
    descriptor = webhook_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBHOOK_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("webhook",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBHOOK_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["webhook"]

    missing = run_webhook_workflow(with_secret=False)
    unsigned = run_webhook_workflow(signed=False)
    unverified = run_webhook_workflow(skip_verify=True)
    live = run_webhook_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unsigned["ok"] is False
    assert unsigned["error"] == "signature_gated"
    assert unverified["ok"] is False
    assert unverified["sentinel"] == ""
    assert unverified["independent_sentinel"] == ""
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert live["verified"] is True
    assert Path(live["sealed_path"]).is_file()
    row = independent_webhook_payload(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["verified"] is True


def test_builtin_proof_seals_webhook_actuation() -> None:
    report = builtin_webhook_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "webhook_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_webhook"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unsigned_delivery_is_forbidden"]
    assert report["checks"]["unverified_ack_is_forbidden"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_payload"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_webhook"]
    assert report["mission_goal"] == WEBHOOK_ACTUATION_GOAL
    assert report["done_when"] == WEBHOOK_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[WEBHOOK_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "webhook" in capability.tags
    assert "hmac" in capability.tags


def test_selection_gate_accepts_webhook_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        WEBHOOK_ACTUATION_GOAL,
        WEBHOOK_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(WEBHOOK_ACTUATION_GOAL)
    assert "webhook" in family
    assert "sqlite" not in family
    assert "git-publication" not in family
    assert "browser" not in family
    assert "timeout" not in family
    assert not family.startswith("kernel-runtime")
