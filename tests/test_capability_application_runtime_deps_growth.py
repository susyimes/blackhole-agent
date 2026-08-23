"""Tests for growing unplannable goals from import-unclosed live-fetched sdists."""

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
    REPO_ROOT,
    RUNTIME_DEPS_DEP_NAME,
    RUNTIME_DEPS_GOAL_KEY,
    RUNTIME_DEPS_GROW_TASK,
    RUNTIME_DEPS_NPM_DECOY_SLUG,
    RUNTIME_DEPS_WINNER_CAPABILITY_ID,
    RUNTIME_DEPS_WINNER_SLUG,
    builtin_application_runtime_deps_growth_plane_proof,
    grow_application_task,
    load_runtime_deps_apply_catalog,
    run_application_runtime_deps_growth_plane,
    verify_application_runtime_deps_growth_plane,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_forage_growth import match_forage_goal, strip_declared_provides
from blackhole_agent.capability_forage_targets import forage_request_for, query_from_goal, rank_catalog
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_runtime_deps_catalog_is_live_fetched_unclosed_sdist() -> None:
    catalog = load_runtime_deps_apply_catalog()
    assert catalog["query"] == query_from_goal(RUNTIME_DEPS_GROW_TASK.goal)
    assert catalog["network_used"] is False
    assert "npm" in catalog["registries"] and "pypi" in catalog["registries"]
    assert not any(item.get("source") or item.get("replay_source") for item in catalog["items"])
    winner = next(item for item in catalog["items"] if item["slug"] == RUNTIME_DEPS_WINNER_SLUG)
    request = forage_request_for(winner, live_fetch=True)
    assert request["origin"]["kind"] == "pypi-live"
    assert Path(request["source"]).is_file()


def test_runtime_deps_match_selects_python_slugify_and_closes_deps() -> None:
    catalog = load_runtime_deps_apply_catalog()
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(catalog["items"]), absorbed=absorbed)
    assert trend["winner"]["slug"] == RUNTIME_DEPS_NPM_DECOY_SLUG
    matched = match_forage_goal(
        (RUNTIME_DEPS_GOAL_KEY,), catalog=catalog, absorbed=absorbed, forage=False, live_fetch=True
    )
    assert matched["ok"], matched
    assert matched["winner"]["slug"] == RUNTIME_DEPS_WINNER_SLUG
    covering = matched["covering"] or {}
    assert RUNTIME_DEPS_GOAL_KEY in covering["inferred_provides"]
    assert any(item.get("name") == RUNTIME_DEPS_DEP_NAME for item in covering.get("runtime_deps") or [])
    assert covering.get("extra_paths")


def test_grow_from_runtime_deps_catalog_forages_python_slugify() -> None:
    catalog = load_runtime_deps_apply_catalog()
    result = grow_application_task(
        RUNTIME_DEPS_GROW_TASK,
        catalog=catalog,
        forage=True,
        hide_before=[RUNTIME_DEPS_WINNER_CAPABILITY_ID],
        live_fetch=True,
    )
    assert result["ok"], result
    assert result["grew"] is True
    assert result["winner_slug"] == RUNTIME_DEPS_WINNER_SLUG
    assert (result.get("forage") or {}).get("origin", {}).get("kind") == "pypi-live"
    assert any(
        item.get("name") == RUNTIME_DEPS_DEP_NAME for item in (result.get("forage") or {}).get("runtime_deps") or []
    )


def test_runtime_deps_plane_grows_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_application_runtime_deps_growth_plane(report_dir)
    assert plane["ok"], plane
    assert plane["winner"] == RUNTIME_DEPS_WINNER_SLUG
    assert plane["grade"]["unclosed_without_deps"]
    assert plane["grade"]["winner_runtime_deps_closed"]
    assert plane["grade"]["extra_paths_vendored"]
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    hidden = build_application_registry(
        ledger,
        hide=[RUNTIME_DEPS_WINNER_CAPABILITY_ID],
        include_synthesized=True,
        include_absorbed=True,
    )
    assert plan_application_task(RUNTIME_DEPS_GROW_TASK, hidden) is None
    grown = build_application_registry(ledger, include_synthesized=True, include_absorbed=True)
    solved = run_application_task(RUNTIME_DEPS_GROW_TASK, grown)
    assert solved["ok"], solved
    verification = verify_application_runtime_deps_growth_plane(report_dir)
    assert verification["ok"], verification
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["grow_winner_is_python_slugify"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_application_runtime_deps_growth_plane(report_dir)["ok"]


def test_builtin_application_runtime_deps_growth_plane_proof() -> None:
    result = builtin_application_runtime_deps_growth_plane_proof()
    assert result["ok"], result
    assert result["action"] == "application_runtime_deps_growth_plane"
    assert result["grow_winner_is_python_slugify"]
    assert result["unclosed_without_deps"]
    assert result["winner_runtime_deps_closed"]
    leftover = (
        "Optional later work is installing transitive runtime dependencies of a "
        "fetched registry package so application-growth can forage import-unclosed sdists."
    )
    assert leftover_marker_ids(leftover) == ("capability.application-runtime-deps-growth-plane",)
    assert result["used_skill_route_discovery"] is False
