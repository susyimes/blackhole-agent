"""A healable red absorbed producer must restore mixed absorbed stack health."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_absorbed_composition import ABSORBED_COMPOSITION_ID
from blackhole_agent.capability_absorbed_recovery import ABSORBED_RECOVERY_ID
from blackhole_agent.capability_absorbed_stack import ABSORBED_STACK_ID
from blackhole_agent.capability_absorbed_stack_repair import (
    ABSORBED_STACK_REPAIR_ID,
    builtin_absorbed_stack_repair_proof,
    compute_repair_verdicts,
    run_absorbed_stack_repair_plane,
    verify_absorbed_stack_repair_report,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_mcp_stack_repair import MCP_STACK_REPAIR_ID
from blackhole_agent.experience_fuel import leftover_next_step
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_healable_producer_restores_mixed_absorbed_stack_health() -> None:
    honesty = compute_repair_verdicts()
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["verdicts"]["base_isolation"]
    assert honesty["verdicts"]["live_absorbed_stack_healthy"]
    assert honesty["verdicts"]["red_producer_fails_stack"]
    assert honesty["verdicts"]["healable_producer_restores_stack"]
    assert honesty["verdicts"]["unrepairable_producer_leaves_stack_unhealthy"]
    assert honesty["producer_id"] == "capability.absorbed-text-reverser"
    assert honesty["composition_id"] == "absorbed-compose-text-reverser-snake-case"
    assert honesty["live"]["health"]["healthy"] is True
    assert honesty["red"]["health"]["healthy"] is False
    assert "absorbed-compose-text-reverser-snake-case" in honesty["red"]["drifted_goals"]
    assert honesty["healed"]["repair"]["verdict"] == "repaired"
    assert honesty["healed"]["health"]["healthy"] is True
    assert honesty["healed"]["health"]["green_count"] == 4
    assert honesty["healed"]["drifted_goals"] == []
    assert honesty["unrepairable"]["repair"]["verdict"] == "unrepairable"
    assert honesty["unrepairable"]["health"]["healthy"] is False
    assert "absorbed-compose-text-reverser-snake-case" in honesty["unrepairable"]["drifted_goals"]


def test_plane_seals_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_absorbed_stack_repair_plane(report_dir)
    assert result["ok"], result
    verification = verify_absorbed_stack_repair_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["healable_producer_restores_stack"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_absorbed_stack_repair_report(report_dir)["ok"] is False


def test_leftover_binds_absorbed_stack_repair_plane() -> None:
    leftover = (
        "Optional later work is mixed absorbed stack repair so a healable "
        "producer restores mixed absorbed stack health."
    )
    assert leftover_marker_ids(leftover) == (ABSORBED_STACK_REPAIR_ID,)
    assert ABSORBED_STACK_ID not in leftover_marker_ids(leftover)
    assert ABSORBED_RECOVERY_ID not in leftover_marker_ids(leftover)
    assert ABSORBED_COMPOSITION_ID not in leftover_marker_ids(leftover)
    assert MCP_STACK_REPAIR_ID not in leftover_marker_ids(leftover)
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "healable producer" in leftover_next_step(prefixed)


def test_mcp_stack_repair_leftover_stays_on_the_mcp_plane() -> None:
    leftover = (
        "Optional later work is mixed stack repair so a healable hop "
        "restores mixed stack health."
    )
    assert leftover_marker_ids(leftover) == (MCP_STACK_REPAIR_ID,)
    assert ABSORBED_STACK_REPAIR_ID not in leftover_marker_ids(leftover)


def test_stack_health_leftover_stays_on_the_grade_plane() -> None:
    leftover = (
        "Optional later work is folding absorbed composition pipelines into "
        "goal-stack health so a red producer fails the mixed absorbed stack grade."
    )
    assert leftover_marker_ids(leftover) == (ABSORBED_STACK_ID,)
    assert ABSORBED_STACK_REPAIR_ID not in leftover_marker_ids(leftover)


def test_recovery_leftover_stays_on_the_heal_plane() -> None:
    leftover = (
        "Repair recovery failure: a red absorbed producer leaves the typed "
        "composition pipeline unplannable, but the recovery loop never heals it."
    )
    assert leftover_marker_ids(leftover) == (ABSORBED_RECOVERY_ID,)
    assert ABSORBED_STACK_REPAIR_ID not in leftover_marker_ids(leftover)


def test_builtin_proof_registers_and_is_falsifiable() -> None:
    result = builtin_absorbed_stack_repair_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert not result["used_skill_route_discovery"]
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[ABSORBED_STACK_REPAIR_ID]
    assert capability.last_proof_exit_code == 0
    assert "repair" in capability.tags
    assert "absorbed" in capability.tags
