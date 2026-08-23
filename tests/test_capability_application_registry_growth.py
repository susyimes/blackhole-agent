"""Tests for growing unplannable goals from registry hits with no fixture overlay."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_application import build_application_registry, plan_application_task, run_application_task
from blackhole_agent.capability_application_growth import (
    APPLY_ABSORBED_SLUGS,
    REGISTRY_GOAL_KEY,
    REGISTRY_GROW_TASK,
    REGISTRY_PYPI_DECOY_SLUG,
    REGISTRY_WINNER_CAPABILITY_ID,
    REGISTRY_WINNER_SLUG,
    REPO_ROOT,
    builtin_application_registry_growth_plane_proof,
    grow_application_task,
    load_registry_apply_catalog,
    run_application_registry_growth_plane,
    verify_application_registry_growth_plane,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_forage_growth import match_forage_goal, strip_declared_provides
from blackhole_agent.capability_forage_targets import forage_request_for, query_from_goal, rank_catalog


def test_registry_catalog_has_no_fixture_overlay() -> None:
    catalog = load_registry_apply_catalog()
    assert catalog["query"] == query_from_goal(REGISTRY_GROW_TASK.goal)
    assert catalog["network_used"] is False
    assert "npm" in catalog["registries"] and "pypi" in catalog["registries"]
    assert not any(item.get("source") or item.get("replay_source") for item in catalog["items"])
    request = forage_request_for(next(item for item in catalog["items"] if item["slug"] == REGISTRY_WINNER_SLUG))
    assert request["origin"]["kind"] == "npm-tarball"
    assert "replay_source" not in request
    assert Path(request["source"]).is_file()


def test_registry_trend_picks_pypi_decoy_and_match_selects_marked() -> None:
    catalog = load_registry_apply_catalog()
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(catalog["items"]), absorbed=absorbed)
    assert trend["winner"]["slug"] == REGISTRY_PYPI_DECOY_SLUG
    lying = rank_catalog(catalog["items"], absorbed=absorbed, goal_keys=(REGISTRY_GOAL_KEY,))
    assert lying["winner"]["slug"] == REGISTRY_PYPI_DECOY_SLUG
    matched = match_forage_goal((REGISTRY_GOAL_KEY,), catalog=catalog, absorbed=absorbed, forage=False)
    assert matched["ok"], matched
    assert matched["winner"]["slug"] == REGISTRY_WINNER_SLUG
    pypi = next(row for row in matched["probes"] if row["slug"] == REGISTRY_PYPI_DECOY_SLUG)
    assert pypi["skip_reason"] != "no_source"
    assert pypi["skip_reason"] == "not_covering"
    assert REGISTRY_GOAL_KEY not in pypi["inferred_provides"]
    origin = forage_request_for(matched["winner"])["origin"]
    assert origin["kind"] != "fixture"


def test_grow_from_registry_catalog_forages_marked() -> None:
    catalog = load_registry_apply_catalog()
    result = grow_application_task(
        REGISTRY_GROW_TASK,
        catalog=catalog,
        forage=True,
        hide_before=[REGISTRY_WINNER_CAPABILITY_ID],
    )
    assert result["ok"], result
    assert result["grew"] is True
    assert result["winner_slug"] == REGISTRY_WINNER_SLUG
    assert result["used_forage_growth_plane"] is False
    assert (result.get("forage") or {}).get("fixture_overlay") is False
    assert (result.get("forage") or {}).get("origin", {}).get("kind") == "npm-tarball"


def test_registry_plane_grows_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_application_registry_growth_plane(report_dir)
    assert plane["ok"], plane
    assert plane["winner"] == REGISTRY_WINNER_SLUG
    assert plane["query"] == "marked"
    assert "npm" in plane["registries"] and "pypi" in plane["registries"]
    assert plane["grade"]["no_replay_source_field"]
    assert plane["grade"]["winner_origin_not_fixture"]
    assert plane["grade"]["pypi_decoy_not_no_source"]
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    hidden = build_application_registry(
        ledger,
        hide=[REGISTRY_WINNER_CAPABILITY_ID],
        include_synthesized=True,
        include_absorbed=True,
    )
    assert plan_application_task(REGISTRY_GROW_TASK, hidden) is None
    grown = build_application_registry(ledger, include_synthesized=True, include_absorbed=True)
    solved = run_application_task(REGISTRY_GROW_TASK, grown)
    assert solved["ok"], solved
    verification = verify_application_registry_growth_plane(report_dir)
    assert verification["ok"], verification
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["grow_winner_is_marked"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_application_registry_growth_plane(report_dir)["ok"]


def test_builtin_application_registry_growth_plane_proof() -> None:
    result = builtin_application_registry_growth_plane_proof()
    assert result["ok"], result
    assert result["action"] == "application_registry_growth_plane"
    assert result["grow_winner_is_marked"]
    assert result["no_replay_source_field"]
    assert result["winner_origin_not_fixture"]
    assert result["pypi_decoy_not_no_source"]
    assert result["used_skill_route_discovery"] is False
