"""Tests for growing unplannable goals from six-level nested-namespace Python class-instance sdists."""

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
    PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,
    PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK,
    PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG,
    PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID,
    PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG,
    REPO_ROOT,
    replay_application_python_sextuple_nested_namespace_class_instance_growth_plane_proof,
    grow_application_task,
    load_python_sextuple_nested_namespace_class_instance_apply_catalog,
    run_application_python_sextuple_nested_namespace_class_instance_growth_plane,
    verify_application_python_sextuple_nested_namespace_class_instance_growth_plane,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_forage_growth import match_forage_goal, strip_declared_provides
from blackhole_agent.capability_forage_targets import forage_request_for, query_from_goal, rank_catalog
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_python_sextuple_nested_namespace_class_instance_catalog_is_live_fetched_sdist() -> None:
    catalog = load_python_sextuple_nested_namespace_class_instance_apply_catalog()
    assert catalog["query"] == query_from_goal(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal)
    assert catalog["network_used"] is False
    assert "npm" in catalog["registries"] and "pypi" in catalog["registries"]
    assert not any(item.get("source") or item.get("replay_source") for item in catalog["items"])
    winner = next(
        item
        for item in catalog["items"]
        if item["slug"] == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG
    )
    request = forage_request_for(winner, live_fetch=True)
    assert request["origin"]["kind"] == "pypi-live"
    assert Path(request["source"]).is_file()


def test_python_sextuple_nested_namespace_class_instance_match_selects_airflow_amazon() -> None:
    catalog = load_python_sextuple_nested_namespace_class_instance_apply_catalog()
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(catalog["items"]), absorbed=absorbed)
    assert trend["winner"]["slug"] == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG
    matched = match_forage_goal(
        (PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        live_fetch=True,
    )
    assert matched["ok"], matched
    assert matched["winner"]["slug"] == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG
    covering = matched["covering"] or {}
    assert PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY in covering["inferred_provides"]
    assert covering.get("python_sextuple_nested_namespace_class_instance") is True
    assert covering.get("python_sextuple_nested_namespace_class_static") is False
    assert covering.get("python_quintuple_nested_namespace_class_static") is False
    assert covering.get("python_quintuple_nested_namespace_class_instance") is False
    assert covering.get("python_quadruple_nested_namespace_class_static") is False
    assert covering.get("python_triple_nested_namespace_class_static") is False
    assert covering.get("python_deep_nested_namespace_class_static") is False
    assert covering.get("python_nested_namespace_class_static") is False
    assert covering.get("python_class_static") is False
    assert covering.get("python_class_instance") is False
    assert covering.get("named_export_class") is False
    assert covering.get("default_export") is False


def test_grow_from_python_sextuple_nested_namespace_class_instance_catalog_forages_airflow_amazon() -> None:
    catalog = load_python_sextuple_nested_namespace_class_instance_apply_catalog()
    result = grow_application_task(
        PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK,
        catalog=catalog,
        forage=True,
        hide_before=[PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID],
        live_fetch=True,
    )
    assert result["ok"], result
    assert result["grew"] is True
    assert result["winner_slug"] == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG
    assert (result.get("forage") or {}).get("origin", {}).get("kind") == "pypi-live"


def test_python_sextuple_nested_namespace_class_instance_plane_grows_and_rejects_tamper(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "report"
    plane = run_application_python_sextuple_nested_namespace_class_instance_growth_plane(report_dir)
    assert plane["ok"], plane
    assert plane["winner"] == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG
    assert plane["grade"]["python_sextuple_nested_namespace_class_instance_selected"]
    assert plane["grade"]["winner_is_python_sextuple_nested_namespace_class_instance"]
    assert plane["grade"]["winner_is_not_python_nested_namespace_class_instance"]
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    hidden = build_application_registry(
        ledger,
        hide=[PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID],
        include_synthesized=True,
        include_absorbed=True,
    )
    assert plan_application_task(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK, hidden) is None
    grown = build_application_registry(ledger, include_synthesized=True, include_absorbed=True)
    solved = run_application_task(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK, grown)
    assert solved["ok"], solved
    verification = verify_application_python_sextuple_nested_namespace_class_instance_growth_plane(report_dir)
    assert verification["ok"], verification
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["grow_winner_is_apache_airflow_providers_amazon"] = False
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_application_python_sextuple_nested_namespace_class_instance_growth_plane(report_dir)["ok"]


def test_builtin_application_python_sextuple_nested_namespace_class_instance_growth_plane_proof() -> None:
    result = replay_application_python_sextuple_nested_namespace_class_instance_growth_plane_proof()
    assert result["ok"], result
    assert result["action"] == "application_python_sextuple_nested_namespace_class_instance_growth_plane"
    assert result["grow_winner_is_apache_airflow_providers_amazon"]
    assert result["python_sextuple_nested_namespace_class_instance_selected"]
    assert result["winner_is_python_sextuple_nested_namespace_class_instance"]
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "six submodule levels down so sdists whose covering API is a six-level nested "
        "Class().method instance rather than a five-level nested Class().method instance "
        "can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-sext-nested-instance-growth-plane",
    )
    assert result["used_skill_route_discovery"] is False
