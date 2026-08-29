"""Tests for typed bridges across independently absorbed tools."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_absorbed_composition import (
    ABSORBED_COMPOSITION_ID,
    CANONICAL_CONSUMER_SLUG,
    CANONICAL_PRODUCER_SLUG,
    builtin_absorbed_composition_bridge_proof,
    composition_registry,
    composition_task,
    load_persisted_bridge_steps,
    make_bridge_step,
    mapping_for,
    pair_is_live_compatible,
    persist_bridge_pair,
    run_absorbed_composition_plane,
    run_composition_honesty,
    select_composition_pair,
    verify_absorbed_composition_report,
)
from blackhole_agent.capability_absorption import load_persisted_absorbed_steps, load_persisted_records
from blackhole_agent.capability_application import (
    build_application_registry,
    plan_application_task,
    run_application_task,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger


def _canonical_pair():
    records = {str(item.get("slug") or ""): item for item in load_persisted_records()}
    steps = load_persisted_absorbed_steps()
    producer = records[CANONICAL_PRODUCER_SLUG]
    consumer = records[CANONICAL_CONSUMER_SLUG]
    assert pair_is_live_compatible(producer, consumer, steps)
    pair = select_composition_pair([producer, consumer], steps=steps)
    assert pair is not None
    return pair, steps


def test_canonical_pair_is_python_to_node_and_isolated() -> None:
    pair, _steps = _canonical_pair()
    assert pair["producer_slug"] == CANONICAL_PRODUCER_SLUG
    assert pair["consumer_slug"] == CANONICAL_CONSUMER_SLUG
    assert pair["producer_runtime"] == "python"
    assert pair["consumer_runtime"] == "node"
    assert mapping_for(
        next(item for item in load_persisted_records() if item["slug"] == CANONICAL_PRODUCER_SLUG),
        next(item for item in load_persisted_records() if item["slug"] == CANONICAL_CONSUMER_SLUG),
    ) == {"reversed_text": ["arg0", "arg1"]}


def test_goal_is_unplannable_without_bridge_and_solved_with_it() -> None:
    pair, steps = _canonical_pair()
    honesty = run_composition_honesty(pair, steps)
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["grown_plan"] == [
        pair["producer_id"],
        pair["bridge_id"],
        pair["consumer_id"],
    ]
    assert honesty["task"]["oracle"]["snake_case_output"] == "enalp_noitprosba"
    assert honesty["task"]["initial_state"]["raw_text"] == "absorption plane"


def test_hiding_any_member_breaks_the_plan() -> None:
    pair, steps = _canonical_pair()
    task = composition_task(pair, steps)
    assert plan_application_task(task, composition_registry(steps, pair, hide=[pair["producer_id"]])) is None
    assert plan_application_task(task, composition_registry(steps, pair, hide=[pair["consumer_id"]])) is None
    assert plan_application_task(task, composition_registry(steps, pair, hide=[pair["bridge_id"]])) is None


def test_bridge_persists_and_enters_absorbed_registry(tmp_path: Path) -> None:
    pair, _steps = _canonical_pair()
    persist_path = tmp_path / "absorbed-bridges.json"
    persist_bridge_pair(pair, path=persist_path)
    steps = load_persisted_bridge_steps(persist_path)
    assert pair["bridge_id"] in steps
    ledger = load_ledger(default_ledger_path(Path(".")))
    # Default application registry stays isolated from absorbed bridges.
    base = build_application_registry(ledger)
    assert pair["bridge_id"] not in base
    assert make_bridge_step(pair).provides == ("arg0", "arg1")


def test_plane_seals_and_verifies(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_absorbed_composition_plane(report_dir)
    assert result["ok"], result
    verification = verify_absorbed_composition_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["grown_plan_solved"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_absorbed_composition_report(report_dir)["ok"] is False


def test_builtin_proof_is_falsifiable() -> None:
    result = builtin_absorbed_composition_bridge_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert result["verdicts"]["cross_runtime"]
    assert not result["used_skill_route_discovery"]
    assert ABSORBED_COMPOSITION_ID.startswith("capability.absorbed-")
    task = composition_task(
        result["pair"],
        load_persisted_absorbed_steps(),
    )
    grown = build_application_registry(load_ledger(default_ledger_path(Path("."))), include_absorbed=True)
    planned = run_application_task(task, grown)
    assert planned["ok"], planned
    assert result["pair"]["bridge_id"] in (planned["plan"] or [])
