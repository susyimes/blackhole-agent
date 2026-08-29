"""Live MCP tools must compose with absorbed Python leaves in the planner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from blackhole_agent.capability_absorption import load_persisted_absorbed_steps
from blackhole_agent.capability_application import (
    APPLICATION_TASKS,
    build_application_registry,
    plan_application_task,
    run_application_task,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_mcp_application import (
    CANONICAL_CONSUMER_SLUG,
    CANONICAL_PRODUCER_SLUG,
    CANONICAL_PROVIDE,
    MCP_APPLICATION_BRIDGE_ID,
    MCP_SHA256_ID,
    builtin_mcp_application_bridge_proof,
    builtin_mcp_echo_sha256_proof,
    canonical_mcp_pair,
    make_mcp_step,
    mixed_registry,
    mixed_task,
    persist_mcp_bridge_pair,
    persist_mcp_steps,
    mcp_step_record,
    run_mcp_application_plane,
    run_mcp_composition_honesty,
    verify_mcp_application_report,
)
from blackhole_agent.capability_watchdog import run_goal_watchdog
from blackhole_agent.kernel_leftover import leftover_marker_ids


def _canonical_pair():
    pair = canonical_mcp_pair()
    assert pair is not None
    return pair, load_persisted_absorbed_steps()


def test_mcp_sha256_step_matches_hashlib() -> None:
    result = builtin_mcp_echo_sha256_proof()
    assert result["ok"], result
    assert result["digest_match"]
    expected = hashlib.sha256(b"absorption plane").hexdigest()
    assert result["mcp_sha256_hex"] == expected
    assert make_mcp_step().capability_id == MCP_SHA256_ID


def test_canonical_pair_is_python_to_mcp_and_isolated() -> None:
    pair, _steps = _canonical_pair()
    assert pair["producer_slug"] == CANONICAL_PRODUCER_SLUG
    assert pair["consumer_slug"] == CANONICAL_CONSUMER_SLUG
    assert pair["producer_runtime"] == "python"
    assert pair["consumer_runtime"] == "mcp"
    assert pair["consumer_id"] == MCP_SHA256_ID
    assert pair["mapping"] == {"reversed_text": ["text"]}


def test_mixed_goal_is_unplannable_without_mcp_or_bridge_and_solved_with_both() -> None:
    pair, steps = _canonical_pair()
    honesty = run_mcp_composition_honesty(pair, absorbed_steps=steps)
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["grown_plan"] == [
        pair["producer_id"],
        pair["bridge_id"],
        pair["consumer_id"],
    ]
    assert honesty["task"]["initial_state"]["raw_text"] == "absorption plane"
    reversed_text = "enalp noitprosba"
    expected = hashlib.sha256(reversed_text.encode("utf-8")).hexdigest()
    assert honesty["task"]["oracle"][CANONICAL_PROVIDE] == expected
    original = hashlib.sha256(b"absorption plane").hexdigest()
    assert expected != original


def test_hiding_any_member_breaks_the_mixed_plan() -> None:
    pair, steps = _canonical_pair()
    task = mixed_task(pair, absorbed_steps=steps)
    assert plan_application_task(task, mixed_registry(pair, absorbed_steps=steps, hide=[pair["producer_id"]])) is None
    assert plan_application_task(task, mixed_registry(pair, absorbed_steps=steps, hide=[pair["consumer_id"]])) is None
    assert plan_application_task(task, mixed_registry(pair, absorbed_steps=steps, hide=[pair["bridge_id"]])) is None


def test_default_watchdog_ignores_mcp_composition_goals() -> None:
    pair, steps = _canonical_pair()
    task = mixed_task(pair, absorbed_steps=steps)
    report = run_goal_watchdog()
    watched = {record["id"] for record in report["goal_results"]}
    assert task.id not in watched
    assert {item.id for item in APPLICATION_TASKS} == watched


def test_grown_registry_plans_mixed_goal_after_persist(tmp_path: Path) -> None:
    pair, _steps = _canonical_pair()
    persist_mcp_steps([mcp_step_record()], path=tmp_path / "mcp-steps.json")
    persist_mcp_bridge_pair(pair, path=tmp_path / "mcp-bridges.json")
    persist_mcp_steps([mcp_step_record()])
    persist_mcp_bridge_pair(pair)
    from blackhole_agent.capability_mcp_application import ensure_mcp_application_bridge_capability

    ensure_mcp_application_bridge_capability()
    ledger = load_ledger(default_ledger_path(Path(".")))
    base = build_application_registry(ledger)
    assert pair["bridge_id"] not in base
    assert pair["consumer_id"] not in base
    grown = build_application_registry(ledger, include_absorbed=True)
    assert pair["consumer_id"] in grown
    assert pair["bridge_id"] in grown
    task = mixed_task(pair)
    planned = run_application_task(task, grown)
    assert planned["ok"], planned
    assert planned["plan"] == [pair["producer_id"], pair["bridge_id"], pair["consumer_id"]]


def test_plane_seals_and_verifies(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_mcp_application_plane(report_dir)
    assert result["ok"], result
    verification = verify_mcp_application_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["grown_plan_solved"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_mcp_application_report(report_dir)["ok"] is False


def test_leftover_binds_mcp_application_bridge() -> None:
    leftover = (
        "Repair planner isolation of live MCP tools: import a live MCP tool as "
        "an application step and compose it with an independently absorbed "
        "Python tool so a mixed MCP+absorbed goal is planner-derived and "
        "solvable, and hiding either member or the bridge fails the outcome."
    )
    assert leftover_marker_ids(leftover) == (MCP_APPLICATION_BRIDGE_ID,)


def test_builtin_proof_is_falsifiable() -> None:
    result = builtin_mcp_application_bridge_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert result["verdicts"]["cross_runtime"]
    assert result["verdicts"]["skip_producer_broke"]
    assert not result["used_skill_route_discovery"]
    ledger = load_ledger(default_ledger_path(Path(".")))
    assert ledger.capabilities[MCP_APPLICATION_BRIDGE_ID].last_proof_exit_code == 0
    assert ledger.capabilities[MCP_SHA256_ID].last_proof_exit_code == 0
