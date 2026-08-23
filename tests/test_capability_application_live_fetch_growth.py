"""Tests for growing unplannable goals from live-fetched registry hits."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_application import (
    build_application_registry,
    plan_application_task,
    run_application_task,
)
from blackhole_agent.capability_application_growth import (
    APPLY_ABSORBED_SLUGS,
    LIVE_FETCH_GOAL_KEY,
    LIVE_FETCH_GROW_TASK,
    LIVE_FETCH_NPM_DECOY_SLUG,
    LIVE_FETCH_WINNER_CAPABILITY_ID,
    LIVE_FETCH_WINNER_SLUG,
    REPO_ROOT,
    builtin_application_live_fetch_growth_plane_proof,
    grow_application_task,
    load_live_fetch_apply_catalog,
    run_application_live_fetch_growth_plane,
    verify_application_live_fetch_growth_plane,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_forage_growth import match_forage_goal, strip_declared_provides
from blackhole_agent.capability_forage_targets import (
    forage_request_for,
    query_from_goal,
    rank_catalog,
    registry_replay_archive,
)


def test_live_fetch_catalog_has_no_stewardship_archive() -> None:
    catalog = load_live_fetch_apply_catalog()
    assert catalog["query"] == query_from_goal(LIVE_FETCH_GROW_TASK.goal)
    assert catalog["network_used"] is False
    assert "npm" in catalog["registries"] and "pypi" in catalog["registries"]
    assert not any(item.get("source") or item.get("replay_source") for item in catalog["items"])
    winner = next(item for item in catalog["items"] if item["slug"] == LIVE_FETCH_WINNER_SLUG)
    assert registry_replay_archive(winner) is None
    hermetic = forage_request_for(winner)
    assert hermetic["registry"] == "pypi"
    assert "source" not in hermetic
    request = forage_request_for(winner, live_fetch=True)
    assert request["origin"]["kind"] == "pypi-live"
    assert not str(request["origin"]["source"]).replace("\\", "/").startswith("stewardship/")
    assert Path(request["source"]).is_file()


def test_live_fetch_trend_picks_npm_decoy_and_match_selects_titlecase() -> None:
    catalog = load_live_fetch_apply_catalog()
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(catalog["items"]), absorbed=absorbed)
    assert trend["winner"]["slug"] == LIVE_FETCH_NPM_DECOY_SLUG
    lying = rank_catalog(catalog["items"], absorbed=absorbed, goal_keys=(LIVE_FETCH_GOAL_KEY,))
    assert lying["winner"]["slug"] == LIVE_FETCH_NPM_DECOY_SLUG
    matched = match_forage_goal(
        (LIVE_FETCH_GOAL_KEY,), catalog=catalog, absorbed=absorbed, forage=False, live_fetch=True
    )
    assert matched["ok"], matched
    assert matched["winner"]["slug"] == LIVE_FETCH_WINNER_SLUG
    npm = next(row for row in matched["probes"] if row["slug"] == LIVE_FETCH_NPM_DECOY_SLUG)
    assert npm["skip_reason"] != "no_source"
    assert LIVE_FETCH_GOAL_KEY not in npm["inferred_provides"]
    origin = forage_request_for(matched["winner"], live_fetch=True)["origin"]
    assert origin["kind"] == "pypi-live"


def test_grow_from_live_fetch_catalog_forages_titlecase() -> None:
    catalog = load_live_fetch_apply_catalog()
    result = grow_application_task(
        LIVE_FETCH_GROW_TASK,
        catalog=catalog,
        forage=True,
        hide_before=[LIVE_FETCH_WINNER_CAPABILITY_ID],
        live_fetch=True,
    )
    assert result["ok"], result
    assert result["grew"] is True
    assert result["winner_slug"] == LIVE_FETCH_WINNER_SLUG
    assert result["used_forage_growth_plane"] is False
    assert (result.get("forage") or {}).get("fixture_overlay") is False
    assert (result.get("forage") or {}).get("origin", {}).get("kind") == "pypi-live"


def test_live_fetch_plane_grows_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_application_live_fetch_growth_plane(report_dir)
    assert plane["ok"], plane
    assert plane["winner"] == LIVE_FETCH_WINNER_SLUG
    assert plane["query"] == "titlecase"
    assert "npm" in plane["registries"] and "pypi" in plane["registries"]
    assert plane["grade"]["winner_origin_live"]
    assert plane["grade"]["no_stewardship_archive"]
    assert plane["grade"]["npm_decoy_not_no_source"]
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    hidden = build_application_registry(
        ledger,
        hide=[LIVE_FETCH_WINNER_CAPABILITY_ID],
        include_synthesized=True,
        include_absorbed=True,
    )
    assert plan_application_task(LIVE_FETCH_GROW_TASK, hidden) is None
    grown = build_application_registry(ledger, include_synthesized=True, include_absorbed=True)
    solved = run_application_task(LIVE_FETCH_GROW_TASK, grown)
    assert solved["ok"], solved
    verification = verify_application_live_fetch_growth_plane(report_dir)
    assert verification["ok"], verification
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["grow_winner_is_titlecase"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_application_live_fetch_growth_plane(report_dir)["ok"]


def test_builtin_application_live_fetch_growth_plane_proof() -> None:
    result = builtin_application_live_fetch_growth_plane_proof()
    assert result["ok"], result
    assert result["action"] == "application_live_fetch_growth_plane"
    assert result["grow_winner_is_titlecase"]
    assert result["winner_origin_live"]
    assert result["no_stewardship_archive"]
    assert result["npm_decoy_not_no_source"]
    assert result["used_skill_route_discovery"] is False
