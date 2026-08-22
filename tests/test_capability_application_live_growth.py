"""Tests for growing unplannable goals from a replayed npm+pypi catalog."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_application import plan_application_task, run_application_task
from blackhole_agent.capability_application_growth import (
    APPLY_ABSORBED_SLUGS,
    DECOY_SLUG,
    GOAL_KEY,
    GROW_TASK,
    LIVE_NPM_DECOY_SLUG,
    REPO_ROOT,
    WINNER_SLUG,
    builtin_application_live_growth_plane_proof,
    grow_application_task,
    load_apply_catalog,
    load_live_apply_catalog,
    run_application_live_growth_plane,
    verify_application_live_growth_plane,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_application import build_application_registry
from blackhole_agent.capability_forage_growth import match_forage_goal, strip_declared_provides
from blackhole_agent.capability_forage_targets import query_from_goal, rank_catalog


def test_live_catalog_is_not_the_frozen_apply_catalog() -> None:
    live = load_live_apply_catalog()
    frozen = load_apply_catalog()
    assert live["query"] == query_from_goal(GROW_TASK.goal)
    assert live["query"] != frozen["query"]
    assert live["network_used"] is False
    assert "npm" in live["registries"] and "pypi" in live["registries"]
    assert not any(item.get("source") for item in live["items"])


def test_live_trend_picks_npm_decoy_and_match_selects_rotate() -> None:
    catalog = load_live_apply_catalog()
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(catalog["items"]), absorbed=absorbed)
    assert trend["winner"]["slug"] == LIVE_NPM_DECOY_SLUG
    lying = rank_catalog(catalog["items"], absorbed=absorbed, goal_keys=(GOAL_KEY,))
    assert lying["winner"]["slug"] == LIVE_NPM_DECOY_SLUG
    matched = match_forage_goal((GOAL_KEY,), catalog=catalog, absorbed=absorbed, forage=False)
    assert matched["ok"], matched
    assert matched["winner"]["slug"] == WINNER_SLUG
    npm = next(row for row in matched["probes"] if row["slug"] == LIVE_NPM_DECOY_SLUG)
    assert npm["skip_reason"] == "no_source"
    pypi = next(row for row in matched["probes"] if row["slug"] == DECOY_SLUG)
    assert pypi["skip_reason"] == "not_covering"


def test_grow_from_live_catalog_forages_rotate() -> None:
    catalog = load_live_apply_catalog()
    result = grow_application_task(
        GROW_TASK,
        catalog=catalog,
        forage=True,
        hide_before=["capability.absorbed-forage-rotate"],
    )
    assert result["ok"], result
    assert result["grew"] is True
    assert result["winner_slug"] == WINNER_SLUG
    assert result["used_forage_growth_plane"] is False


def test_live_plane_grows_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_application_live_growth_plane(report_dir)
    assert plane["ok"], plane
    assert plane["winner"] == WINNER_SLUG
    assert plane["query"] == "rotate"
    assert "npm" in plane["registries"] and "pypi" in plane["registries"]
    assert plane["grade"]["not_frozen_apply_catalog"]
    assert plane["grade"]["network_unused"]
    assert plane["grade"]["trend_npm_decoy_wins"]
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
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
    verification = verify_application_live_growth_plane(report_dir)
    assert verification["ok"], verification
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["grow_winner_is_forage_rotate"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_application_live_growth_plane(report_dir)["ok"]


def test_builtin_application_live_growth_plane_proof() -> None:
    result = builtin_application_live_growth_plane_proof()
    assert result["ok"], result
    assert result["action"] == "application_live_growth_plane"
    assert result["grow_winner_is_forage_rotate"]
    assert result["query_from_goal"]
    assert result["network_unused"]
    assert result["used_skill_route_discovery"] is False
