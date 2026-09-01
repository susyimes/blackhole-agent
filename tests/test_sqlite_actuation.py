from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.github_actuation import GITHUB_ACTUATION_GOAL, GITHUB_ACTUATION_ID
from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.sqlite_actuation import (
    SENTINEL,
    SQLITE_ACTUATION_DONE_WHEN,
    SQLITE_ACTUATION_GOAL,
    SQLITE_ACTUATION_ID,
    builtin_sqlite_actuation_proof,
    independent_beacon_row,
    run_sqlite_workflow,
)
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    SQLITE_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    sqlite_tool_descriptor,
)


def test_goal_binds_sqlite_actuation_plane() -> None:
    assert leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (SQLITE_ACTUATION_ID,)
    assert SQLITE_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(GITHUB_ACTUATION_GOAL) == (GITHUB_ACTUATION_ID,)
    assert leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (GMAIL_ACTUATION_ID,)
    assert SQLITE_ACTUATION_ID not in leftover_marker_ids(GITHUB_ACTUATION_GOAL)
    assert SQLITE_ACTUATION_ID not in leftover_marker_ids(GMAIL_ACTUATION_GOAL)
    assert GITHUB_ACTUATION_ID not in leftover_marker_ids(SQLITE_ACTUATION_GOAL)
    assert GMAIL_ACTUATION_ID not in leftover_marker_ids(SQLITE_ACTUATION_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(SQLITE_ACTUATION_GOAL),
            semantic_signature(GITHUB_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(SQLITE_ACTUATION_GOAL),
            semantic_signature(GMAIL_ACTUATION_GOAL),
        )
        < 0.82
    )


def test_opted_in_sqlite_tool_completes_schema_gated_workflow() -> None:
    descriptor = sqlite_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SQLITE_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("sqlite",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SQLITE_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["sqlite"]

    missing = run_sqlite_workflow(create_if_missing=False)
    unmigrated = run_sqlite_workflow(skip_schema=True)
    rolled = run_sqlite_workflow(skip_commit=True)
    live = run_sqlite_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_database"
    assert unmigrated["ok"] is False
    assert unmigrated["error"] == "schema_gated"
    assert rolled["ok"] is False
    assert rolled["sentinel"] == ""
    assert rolled["independent_sentinel"] == ""
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert live["schema_applied"] is True
    assert Path(live["db_path"]).is_file()
    row = independent_beacon_row(Path(live["db_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["row_count"] == 1


def test_builtin_proof_seals_sqlite_actuation() -> None:
    report = builtin_sqlite_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "sqlite_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_sqlite"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_file_is_forbidden"]
    assert report["checks"]["unmigrated_insert_is_forbidden"]
    assert report["checks"]["uncommitted_insert_rolls_back"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_row"]
    assert report["checks"]["workflow_writes_sqlite_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_sqlite"]
    assert report["mission_goal"] == SQLITE_ACTUATION_GOAL
    assert report["done_when"] == SQLITE_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[SQLITE_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "sqlite" in capability.tags
    assert "transaction" in capability.tags


def test_selection_gate_accepts_sqlite_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        SQLITE_ACTUATION_GOAL,
        SQLITE_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(SQLITE_ACTUATION_GOAL)
    assert "sqlite" in family
    assert "git-publication" not in family
    assert "browser" not in family
    assert "timeout" not in family
    assert not family.startswith("kernel-runtime")
