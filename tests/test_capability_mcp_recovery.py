"""Mixed MCP+absorbed pipelines must be recoverable."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_application import APPLICATION_TASKS
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_mcp_application import MCP_APPLICATION_BRIDGE_ID, MCP_SHA256_ID
from blackhole_agent.capability_mcp_recovery import (
    MCP_RECOVERY_ID,
    builtin_mcp_recovery_proof,
    compute_recovery_verdicts,
    run_mcp_recovery_plane,
    verify_mcp_recovery_report,
)
from blackhole_agent.capability_mcp_reliability import MCP_RELIABILITY_ID, load_mcp_composition_tasks
from blackhole_agent.capability_mcp_stack import MCP_STACK_ID
from blackhole_agent.capability_recovery import BREAK_STALE_STAMP, run_recovery_loop
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_default_recovery_ignores_red_mcp_hop() -> None:
    tasks = load_mcp_composition_tasks()
    assert tasks, "persisted mixed MCP+absorbed bridge must yield a composition goal"
    mcp_ids = {task.id for task in tasks}
    report = run_recovery_loop(breaks={MCP_SHA256_ID: BREAK_STALE_STAMP})
    watched = {record["id"] for record in report["task_records"]}
    assert mcp_ids.isdisjoint(watched)
    assert {task.id for task in APPLICATION_TASKS} == watched
    assert report["ok"] is True
    assert report["recovery"]["repair_count"] == 0
    assert MCP_SHA256_ID not in report["blocked_capabilities"]


def test_mcp_recovery_heals_hop_and_fails_honestly() -> None:
    honesty = compute_recovery_verdicts()
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["verdicts"]["base_isolation"]
    assert honesty["verdicts"]["live_mcp_healthy"]
    assert honesty["verdicts"]["mcp_hop_stale_healed"]
    assert honesty["verdicts"]["mcp_hop_unrepairable_honest"]
    assert "mcp-compose-text-reverser-echo-sha256" in honesty["mcp_ids"]
    assert honesty["mcp_id"] == MCP_SHA256_ID
    assert honesty["healed"]["repair_verdicts"][MCP_SHA256_ID] == "repaired"
    assert honesty["unrepairable"]["repair_verdicts"][MCP_SHA256_ID] == "unrepairable"


def test_plane_seals_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_mcp_recovery_plane(report_dir)
    assert result["ok"], result
    verification = verify_mcp_recovery_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["mcp_hop_stale_healed"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_mcp_recovery_report(report_dir)["ok"] is False


def test_leftover_binds_mcp_recovery_plane() -> None:
    leftover = (
        "Optional later work is watching mixed MCP+absorbed goals in the "
        "recovery plane so a red MCP hop is healed."
    )
    assert leftover_marker_ids(leftover) == (MCP_RECOVERY_ID,)
    assert MCP_RELIABILITY_ID not in leftover_marker_ids(leftover)
    assert MCP_STACK_ID not in leftover_marker_ids(leftover)
    assert MCP_APPLICATION_BRIDGE_ID not in leftover_marker_ids(leftover)


def test_reliability_leftover_stays_on_the_watch_plane() -> None:
    leftover = (
        "Optional later work is watching mixed MCP+absorbed goals in the "
        "reliability plane so a hidden MCP hop is named drift."
    )
    assert leftover_marker_ids(leftover) == (MCP_RELIABILITY_ID,)
    assert MCP_RECOVERY_ID not in leftover_marker_ids(leftover)


def test_builtin_proof_registers_and_is_falsifiable() -> None:
    result = builtin_mcp_recovery_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert not result["used_skill_route_discovery"]
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_RECOVERY_ID]
    assert capability.last_proof_exit_code == 0
    assert "recovery" in capability.tags
    assert "mcp" in capability.tags
