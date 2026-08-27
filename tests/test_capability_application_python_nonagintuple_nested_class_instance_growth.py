"""Tests for ninety-level nested-namespace Python class-instance forage."""

from __future__ import annotations

from pathlib import Path

from blackhole_agent.capability_application_growth import (
    PYTHON_NONAGINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE,
    PYTHON_NONAGINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK,
    load_python_nonagintuple_nested_namespace_class_instance_apply_catalog,
    replay_application_python_nonagintuple_nested_namespace_class_instance_growth_plane_proof,
)
from blackhole_agent.capability_forage_targets import query_from_goal
from blackhole_agent.capability_foraging import _extracted_cache_dir
from blackhole_agent.experience_fuel import leftover_next_step
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_python_nonagintuple_nested_namespace_class_instance_catalog_query() -> None:
    catalog = load_python_nonagintuple_nested_namespace_class_instance_apply_catalog()
    assert catalog["query"] == query_from_goal(PYTHON_NONAGINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal)
    assert catalog["network_used"] is False
    assert "npm" in catalog["registries"] and "pypi" in catalog["registries"]
    assert not any(item.get("source") or item.get("replay_source") for item in catalog["items"])


def test_python_nonagintuple_nested_namespace_class_instance_replay_proof() -> None:
    result = replay_application_python_nonagintuple_nested_namespace_class_instance_growth_plane_proof()
    assert result["ok"], result
    assert result["action"] == "application_python_nonagintuple_nested_namespace_class_instance_growth_plane"
    assert result["python_nonagintuple_nested_namespace_class_instance_selected"]
    assert result["winner"] == PYTHON_NONAGINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety submodule levels down so sdists whose covering API is a ninety-level nested "
        "Class().method instance rather than an eighty-nine-level nested Class().method instance "
        "can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-nonagint-nested-instance-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert result["used_skill_route_discovery"] is False
    assert result["extra_leaf_cache_skips_wheel_filename"]


def test_extracted_extra_leaf_cache_avoids_wheel_filename() -> None:
    wheel = Path("apache_airflow_providers_common_compat-1.18.0-py3-none-any.whl")
    cache = _extracted_cache_dir("apache-airflow-providers-common-compat", "1.18.0", wheel)
    assert cache.name == "1.18.0"
    assert ".whl" not in str(cache)
