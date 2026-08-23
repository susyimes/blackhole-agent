"""Tests for growing unplannable goals from default-exported-object live-fetched npm tarballs."""

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
    NODE_DEFAULT_EXPORT_OBJECT_DEP_NAME,
    NODE_DEFAULT_EXPORT_OBJECT_GOAL_KEY,
    NODE_DEFAULT_EXPORT_OBJECT_GROW_TASK,
    NODE_DEFAULT_EXPORT_OBJECT_NPM_DECOY_SLUG,
    NODE_DEFAULT_EXPORT_OBJECT_WINNER_CAPABILITY_ID,
    NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG,
    REPO_ROOT,
    builtin_application_node_default_export_object_growth_plane_proof,
    grow_application_task,
    load_node_default_export_object_apply_catalog,
    run_application_node_default_export_object_growth_plane,
    verify_application_node_default_export_object_growth_plane,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_forage_growth import match_forage_goal, strip_declared_provides
from blackhole_agent.capability_forage_targets import forage_request_for, query_from_goal, rank_catalog
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_node_default_export_object_catalog_is_live_fetched_namespace_tarball() -> None:
    catalog = load_node_default_export_object_apply_catalog()
    assert catalog["query"] == query_from_goal(NODE_DEFAULT_EXPORT_OBJECT_GROW_TASK.goal)
    assert catalog["network_used"] is False
    assert "npm" in catalog["registries"] and "pypi" in catalog["registries"]
    assert not any(item.get("source") or item.get("replay_source") for item in catalog["items"])
    winner = next(item for item in catalog["items"] if item["slug"] == NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG)
    request = forage_request_for(winner, live_fetch=True)
    assert request["origin"]["kind"] == "npm-live"
    assert Path(request["source"]).is_file()


def test_node_default_export_object_match_selects_query_string_and_closes_deps() -> None:
    catalog = load_node_default_export_object_apply_catalog()
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(catalog["items"]), absorbed=absorbed)
    assert trend["winner"]["slug"] == NODE_DEFAULT_EXPORT_OBJECT_NPM_DECOY_SLUG
    matched = match_forage_goal(
        (NODE_DEFAULT_EXPORT_OBJECT_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        live_fetch=True,
    )
    assert matched["ok"], matched
    assert matched["winner"]["slug"] == NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG
    covering = matched["covering"] or {}
    assert NODE_DEFAULT_EXPORT_OBJECT_GOAL_KEY in covering["inferred_provides"]
    assert covering.get("default_export") is True
    assert covering.get("default_export_object") is True
    assert any(
        item.get("name") == NODE_DEFAULT_EXPORT_OBJECT_DEP_NAME for item in covering.get("runtime_deps") or []
    )
    assert covering.get("extra_paths")


def test_grow_from_node_default_export_object_catalog_forages_query_string() -> None:
    catalog = load_node_default_export_object_apply_catalog()
    result = grow_application_task(
        NODE_DEFAULT_EXPORT_OBJECT_GROW_TASK,
        catalog=catalog,
        forage=True,
        hide_before=[NODE_DEFAULT_EXPORT_OBJECT_WINNER_CAPABILITY_ID],
        live_fetch=True,
    )
    assert result["ok"], result
    assert result["grew"] is True
    assert result["winner_slug"] == NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG
    assert (result.get("forage") or {}).get("origin", {}).get("kind") == "npm-live"
    assert any(
        item.get("name") == NODE_DEFAULT_EXPORT_OBJECT_DEP_NAME
        for item in (result.get("forage") or {}).get("runtime_deps") or []
    )


def test_node_default_export_object_plane_grows_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_application_node_default_export_object_growth_plane(report_dir)
    assert plane["ok"], plane
    assert plane["winner"] == NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG
    assert plane["grade"]["unclosed_without_deps"]
    assert plane["grade"]["named_only_unselected"]
    assert plane["grade"]["winner_is_default_export"]
    assert plane["grade"]["winner_is_default_export_object"]
    assert plane["grade"]["winner_runtime_deps_closed"]
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    hidden = build_application_registry(
        ledger,
        hide=[NODE_DEFAULT_EXPORT_OBJECT_WINNER_CAPABILITY_ID],
        include_synthesized=True,
        include_absorbed=True,
    )
    assert plan_application_task(NODE_DEFAULT_EXPORT_OBJECT_GROW_TASK, hidden) is None
    grown = build_application_registry(ledger, include_synthesized=True, include_absorbed=True)
    solved = run_application_task(NODE_DEFAULT_EXPORT_OBJECT_GROW_TASK, grown)
    assert solved["ok"], solved
    verification = verify_application_node_default_export_object_growth_plane(report_dir)
    assert verification["ok"], verification
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["grow_winner_is_query_string"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_application_node_default_export_object_growth_plane(report_dir)["ok"]


def test_builtin_application_node_default_export_object_growth_plane_proof() -> None:
    result = builtin_application_node_default_export_object_growth_plane_proof()
    assert result["ok"], result
    assert result["action"] == "application_node_default_export_object_growth_plane"
    assert result["grow_winner_is_query_string"]
    assert result["named_only_unselected"]
    assert result["winner_is_default_export"]
    assert result["winner_is_default_export_object"]
    leftover = (
        "Optional later work is reflecting Node default-exported objects so packages "
        "whose default export is a namespace of functions rather than a single function "
        "can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-node-default-export-object-growth-plane",
    )
    assert result["used_skill_route_discovery"] is False
