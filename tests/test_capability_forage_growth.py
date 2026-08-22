"""Tests for goal-driven forage matching that ignores catalog provides."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_forage_growth import (
    DECOY_SLUG,
    GOAL_KEY,
    REPO_ROOT,
    WINNER_SLUG,
    builtin_forage_growth_plane_proof,
    load_growth_catalog,
    match_forage_goal,
    run_forage_growth_plane,
    strip_declared_provides,
    verify_forage_growth_plane,
)
from blackhole_agent.capability_forage_targets import HERMETIC_ABSORBED_SLUGS, rank_catalog


def test_stripped_trend_picks_the_popular_decoy() -> None:
    catalog = load_growth_catalog()
    ranking = rank_catalog(
        strip_declared_provides(catalog["items"]),
        absorbed=sorted(HERMETIC_ABSORBED_SLUGS),
    )
    assert ranking["ok"], ranking
    assert ranking["winner"]["slug"] == DECOY_SLUG


def test_lying_catalog_provides_would_pick_the_decoy() -> None:
    catalog = load_growth_catalog()
    lying = rank_catalog(
        catalog["items"],
        absorbed=sorted(HERMETIC_ABSORBED_SLUGS),
        goal_keys=(GOAL_KEY,),
    )
    assert lying["ok"], lying
    assert lying["winner"]["slug"] == DECOY_SLUG
    pick = next(item for item in catalog["items"] if item["slug"] == DECOY_SLUG)
    assert GOAL_KEY in pick["provides"]


def test_match_skips_decoy_and_selects_flip() -> None:
    result = match_forage_goal((GOAL_KEY,), absorbed=sorted(HERMETIC_ABSORBED_SLUGS), forage=False)
    assert result["ok"], result
    assert result["winner"]["slug"] == WINNER_SLUG
    assert GOAL_KEY in (result["covering"] or {}).get("inferred_provides", [])
    decoy = next(row for row in result["probes"] if row["slug"] == DECOY_SLUG)
    assert decoy["skip_reason"] == "not_covering"
    assert GOAL_KEY not in decoy["inferred_provides"]
    assert (result["trend_winner"] or {}).get("slug") == DECOY_SLUG


def test_empty_goal_and_uncovered_goal_are_honest_refusals() -> None:
    empty = match_forage_goal((), absorbed=sorted(HERMETIC_ABSORBED_SLUGS), forage=False)
    assert empty["ok"] is False
    assert empty["error"] == "empty forage goal"
    missed = match_forage_goal(("unicorn_output",), absorbed=sorted(HERMETIC_ABSORBED_SLUGS), forage=False)
    assert missed["ok"] is False
    assert missed["error"] == "no forage match"
    assert missed["winner"] is None


def test_plane_forages_winner_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_forage_growth_plane(report_dir)
    assert plane["ok"], plane
    assert plane["winner"] == WINNER_SLUG
    assert plane["grade"]["catalog_provides_ignored"]
    assert plane["grade"]["lying_catalog_picks_decoy"]
    assert plane["grade"]["unplannable_before"]
    assert plane["grade"]["grown_plan_solved"]
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    assert "capability.absorbed-forage-flip" in ledger.capabilities
    verification = verify_forage_growth_plane(report_dir)
    assert verification["ok"], verification
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["match_is_forage_flip"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_forage_growth_plane(report_dir)["ok"]


def test_builtin_forage_growth_plane_proof() -> None:
    result = builtin_forage_growth_plane_proof()
    assert result["ok"], result
    assert result["action"] == "forage_growth_plane"
    assert result["match_is_forage_flip"]
    assert result["catalog_provides_ignored"]
    assert result["tampered_rejected"]
    assert result["used_skill_route_discovery"] is False
