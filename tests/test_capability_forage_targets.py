"""Tests for trend-driven forage-target selection."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_forage_targets import (
    GOAL_OVERRIDE_SLUG,
    HERMETIC_ABSORBED_SLUGS,
    REPO_ROOT,
    WINNER_SLUG,
    builtin_forage_target_plane_proof,
    load_catalog,
    query_from_goal,
    rank_catalog,
    refresh_registry_catalog,
    run_forage_target_plane,
    select_forage_target,
    verify_forage_target_plane,
)


def test_trend_ranking_skips_absorbed_and_nonviable() -> None:
    catalog = load_catalog()
    ranking = rank_catalog(catalog["items"], absorbed=sorted(HERMETIC_ABSORBED_SLUGS))
    assert ranking["ok"], ranking
    assert ranking["winner"]["slug"] == WINNER_SLUG
    skipped = {row["slug"]: row["skip_reason"] for row in ranking["skipped"]}
    assert skipped["inflection"] == "already_absorbed"
    assert skipped["forage-lab"] == "already_absorbed"
    assert skipped["forage-empty"] == "nonviable"
    assert "js-shouter" in {row["slug"] for row in ranking["ranked"]}


def test_goal_key_overrides_download_trend() -> None:
    catalog = load_catalog()
    ranking = rank_catalog(
        catalog["items"],
        absorbed=sorted(HERMETIC_ABSORBED_SLUGS),
        goal_keys=("shouted_text",),
    )
    assert ranking["ok"], ranking
    assert ranking["winner"]["slug"] == GOAL_OVERRIDE_SLUG
    assert ranking["winner"]["goal_score"] > ranking["winner"]["trend_score"]


def test_empty_catalog_and_all_absorbed_are_honest_refusals() -> None:
    empty = rank_catalog([], absorbed=sorted(HERMETIC_ABSORBED_SLUGS))
    assert empty["ok"] is False
    assert empty["error"] == "empty forage catalog"
    catalog = load_catalog()
    slugs = [str(item["slug"]) for item in catalog["items"]]
    refused = rank_catalog(catalog["items"], absorbed=slugs)
    assert refused["ok"] is False
    assert refused["error"] == "no forage target"


def test_select_without_forage_does_not_need_a_named_package() -> None:
    result = select_forage_target(absorbed=sorted(HERMETIC_ABSORBED_SLUGS), forage=False)
    assert result["ok"]
    assert result["winner"]["slug"] == WINNER_SLUG
    assert "forage" not in result


def test_plane_forages_winner_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_forage_target_plane(report_dir)
    assert plane["ok"], plane
    assert plane["winner"] == WINNER_SLUG
    assert plane["grade"]["goal_overrides_trend"]
    assert plane["grade"]["unplannable_before"]
    assert plane["grade"]["grown_plan_solved"]
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    assert "capability.absorbed-forage-pick" in ledger.capabilities
    verification = verify_forage_target_plane(report_dir)
    assert verification["ok"], verification
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["winner_is_forage_pick"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_forage_target_plane(report_dir)["ok"]


def test_query_from_goal_strips_output_suffix() -> None:
    assert query_from_goal(("rotate_output",)) == "rotate"
    assert query_from_goal(("flip_output", "shout_output")) == "flip shout"


def test_refresh_replay_is_npm_and_pypi_without_network() -> None:
    catalog = refresh_registry_catalog("rotate", live=False)
    assert catalog["ok"], catalog
    assert catalog["replay"] is True
    assert catalog["network_used"] is False
    assert catalog["live"] is False
    assert "npm" in catalog["registries"]
    assert "pypi" in catalog["registries"]
    slugs = {item["slug"] for item in catalog["items"]}
    assert "left-pad" in slugs
    assert "forage-rotate" in slugs
    rotate = next(item for item in catalog["items"] if item["slug"] == "forage-rotate")
    assert rotate["source"] == ""
    assert rotate["replay_source"]
    assert rotate["registry"] == "pypi"


def test_builtin_forage_target_plane_proof() -> None:
    result = builtin_forage_target_plane_proof()
    assert result["ok"], result
    assert result["action"] == "forage_target_plane"
    assert result["winner_is_forage_pick"]
    assert result["goal_overrides_trend"]
    assert result["tampered_rejected"]
    assert result["used_skill_route_discovery"] is False
