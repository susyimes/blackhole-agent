"""Tests for growing unplannable goals from class-static live-fetched npm tarballs."""

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
    NODE_CLASS_STATIC_GOAL_KEY,
    NODE_CLASS_STATIC_GROW_TASK,
    NODE_CLASS_STATIC_NPM_DECOY_SLUG,
    NODE_CLASS_STATIC_WINNER_CAPABILITY_ID,
    NODE_CLASS_STATIC_WINNER_SLUG,
    REPO_ROOT,
    builtin_application_node_class_static_growth_plane_proof,
    grow_application_task,
    load_node_class_static_apply_catalog,
    run_application_node_class_static_growth_plane,
    verify_application_node_class_static_growth_plane,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_forage_growth import match_forage_goal, strip_declared_provides
from blackhole_agent.capability_forage_targets import forage_request_for, query_from_goal, rank_catalog
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_node_class_static_catalog_is_live_fetched_class_static_tarball() -> None:
    catalog = load_node_class_static_apply_catalog()
    assert catalog["query"] == query_from_goal(NODE_CLASS_STATIC_GROW_TASK.goal)
    assert catalog["network_used"] is False
    assert "npm" in catalog["registries"] and "pypi" in catalog["registries"]
    assert not any(item.get("source") or item.get("replay_source") for item in catalog["items"])
    winner = next(item for item in catalog["items"] if item["slug"] == NODE_CLASS_STATIC_WINNER_SLUG)
    request = forage_request_for(winner, live_fetch=True)
    assert request["origin"]["kind"] == "npm-live"
    assert Path(request["source"]).is_file()


def test_node_class_static_match_selects_spark_md5() -> None:
    catalog = load_node_class_static_apply_catalog()
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(catalog["items"]), absorbed=absorbed)
    assert trend["winner"]["slug"] == NODE_CLASS_STATIC_NPM_DECOY_SLUG
    matched = match_forage_goal(
        (NODE_CLASS_STATIC_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        live_fetch=True,
    )
    assert matched["ok"], matched
    assert matched["winner"]["slug"] == NODE_CLASS_STATIC_WINNER_SLUG
    covering = matched["covering"] or {}
    assert NODE_CLASS_STATIC_GOAL_KEY in covering["inferred_provides"]
    assert covering.get("default_export") is True
    assert covering.get("default_export_class_static") is True
    assert covering.get("default_export_class") is False
    assert covering.get("default_export_object") is False


def test_grow_from_node_class_static_catalog_forages_spark_md5() -> None:
    catalog = load_node_class_static_apply_catalog()
    result = grow_application_task(
        NODE_CLASS_STATIC_GROW_TASK,
        catalog=catalog,
        forage=True,
        hide_before=[NODE_CLASS_STATIC_WINNER_CAPABILITY_ID],
        live_fetch=True,
    )
    assert result["ok"], result
    assert result["grew"] is True
    assert result["winner_slug"] == NODE_CLASS_STATIC_WINNER_SLUG
    assert (result.get("forage") or {}).get("origin", {}).get("kind") == "npm-live"


def test_node_class_static_plane_grows_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_application_node_class_static_growth_plane(report_dir)
    assert plane["ok"], plane
    assert plane["winner"] == NODE_CLASS_STATIC_WINNER_SLUG
    assert plane["grade"]["named_only_unselected"]
    assert plane["grade"]["winner_is_default_export"]
    assert plane["grade"]["winner_is_default_export_class_static"]
    assert plane["grade"]["winner_is_not_default_export_class"]
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    hidden = build_application_registry(
        ledger,
        hide=[NODE_CLASS_STATIC_WINNER_CAPABILITY_ID],
        include_synthesized=True,
        include_absorbed=True,
    )
    assert plan_application_task(NODE_CLASS_STATIC_GROW_TASK, hidden) is None
    grown = build_application_registry(ledger, include_synthesized=True, include_absorbed=True)
    solved = run_application_task(NODE_CLASS_STATIC_GROW_TASK, grown)
    assert solved["ok"], solved
    verification = verify_application_node_class_static_growth_plane(report_dir)
    assert verification["ok"], verification
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["grow_winner_is_spark_md5"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_application_node_class_static_growth_plane(report_dir)["ok"]


def test_builtin_application_node_class_static_growth_plane_proof() -> None:
    result = builtin_application_node_class_static_growth_plane_proof()
    assert result["ok"], result
    assert result["action"] == "application_node_class_static_growth_plane"
    assert result["grow_winner_is_spark_md5"]
    assert result["named_only_unselected"]
    assert result["winner_is_default_export"]
    assert result["winner_is_default_export_class_static"]
    leftover = (
        "Optional later work is reflecting Node class static methods so packages "
        "whose callable API is Class.method rather than new Class().method can be "
        "foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-node-class-static-growth-plane",
    )
    assert result["used_skill_route_discovery"] is False
