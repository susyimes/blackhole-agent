"""Tests for growing unplannable application goals through forage matching."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_application import (
    ApplicationTask,
    build_application_registry,
    plan_application_task,
    run_application_task,
)
from blackhole_agent.capability_application_growth import (
    ALREADY_SOLVABLE_TASK,
    APPLY_ABSORBED_SLUGS,
    DECOY_SLUG,
    GOAL_KEY,
    GROW_TASK,
    REPO_ROOT,
    UNCOVERED_TASK,
    WINNER_SLUG,
    builtin_application_growth_plane_proof,
    grow_application_task,
    load_apply_catalog,
    run_application_growth_plane,
    verify_application_growth_plane,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_forage_growth import match_forage_goal, strip_declared_provides
from blackhole_agent.capability_forage_targets import rank_catalog


def test_stripped_trend_picks_the_popular_decoy() -> None:
    catalog = load_apply_catalog()
    ranking = rank_catalog(
        strip_declared_provides(catalog["items"]),
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
    )
    assert ranking["ok"], ranking
    assert ranking["winner"]["slug"] == DECOY_SLUG


def test_lying_catalog_provides_would_pick_the_decoy() -> None:
    catalog = load_apply_catalog()
    lying = rank_catalog(
        catalog["items"],
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        goal_keys=(GOAL_KEY,),
    )
    assert lying["ok"], lying
    assert lying["winner"]["slug"] == DECOY_SLUG
    pick = next(item for item in catalog["items"] if item["slug"] == DECOY_SLUG)
    assert GOAL_KEY in pick["provides"]


def test_match_skips_decoy_and_selects_rotate() -> None:
    result = match_forage_goal(
        (GOAL_KEY,),
        catalog=load_apply_catalog(),
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=False,
    )
    assert result["ok"], result
    assert result["winner"]["slug"] == WINNER_SLUG
    assert GOAL_KEY in (result["covering"] or {}).get("inferred_provides", [])
    decoy = next(row for row in result["probes"] if row["slug"] == DECOY_SLUG)
    assert decoy["skip_reason"] == "not_covering"
    assert GOAL_KEY not in decoy["inferred_provides"]
    assert (result["trend_winner"] or {}).get("slug") == DECOY_SLUG


def test_already_solvable_task_does_not_forage() -> None:
    result = grow_application_task(ALREADY_SOLVABLE_TASK, forage=True)
    assert result["ok"], result
    assert result["grew"] is False
    assert result["forage"] is None
    assert result["unplannable_before"] is False
    assert result["used_forage_growth_plane"] is False
    assert result.get("plan")


def test_uncovered_goal_stays_honestly_unsolved() -> None:
    result = grow_application_task(UNCOVERED_TASK, forage=True)
    assert result["ok"] is False
    assert result["error"] == "no forage match"
    assert result["grew"] is False
    assert result["plan"] is None
    assert result["used_forage_growth_plane"] is False


def test_grow_flag_on_application_task_skips_forage_when_plannable() -> None:
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    registry = build_application_registry(ledger)
    result = run_application_task(ALREADY_SOLVABLE_TASK, registry, grow=True)
    assert result["ok"], result
    assert result.get("grew") is False
    assert result.get("used_forage_growth_plane") is False
    assert plan_application_task(ALREADY_SOLVABLE_TASK, registry) is not None


def test_plane_grows_unplannable_task_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_application_growth_plane(report_dir)
    assert plane["ok"], plane
    assert plane["winner"] == WINNER_SLUG
    assert plane["grade"]["already_solvable_skips_forage"]
    assert plane["grade"]["uncovered_stays_unsolved"]
    assert plane["grade"]["catalog_provides_ignored"]
    assert plane["grade"]["no_separate_plane_invocation"]
    assert plane["grade"]["unplannable_before"]
    assert plane["grade"]["grown_plan_solved"]
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    assert "capability.absorbed-forage-rotate" in ledger.capabilities
    hidden = build_application_registry(
        ledger,
        hide=["capability.absorbed-forage-rotate"],
        include_synthesized=True,
        include_absorbed=True,
    )
    assert plan_application_task(GROW_TASK, hidden) is None
    grown = build_application_registry(ledger, include_synthesized=True, include_absorbed=True)
    solved = run_application_task(GROW_TASK, grown)
    assert solved["ok"], solved
    assert "capability.absorbed-forage-rotate" in (solved.get("plan") or [])
    verification = verify_application_growth_plane(report_dir)
    assert verification["ok"], verification
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["grow_winner_is_forage_rotate"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_application_growth_plane(report_dir)["ok"]


def test_builtin_application_growth_plane_proof() -> None:
    result = builtin_application_growth_plane_proof()
    assert result["ok"], result
    assert result["action"] == "application_growth_plane"
    assert result["grow_winner_is_forage_rotate"]
    assert result["already_solvable_skips_forage"]
    assert result["no_separate_plane_invocation"]
    assert result["tampered_rejected"]
    assert result["used_skill_route_discovery"] is False


def test_grow_task_oracle_matches_fixture_behavior() -> None:
    assert GROW_TASK.oracle[GOAL_KEY] == f"rotated:{GROW_TASK.initial_state['text']}"
    assert isinstance(UNCOVERED_TASK, ApplicationTask)
