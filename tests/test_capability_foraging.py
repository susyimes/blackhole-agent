"""Tests for the capability foraging plane."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_foraging import (
    FIXTURE_EMPTY_PACKAGE,
    FIXTURE_FORAGE_PACKAGE,
    FIXTURE_NODE_EMPTY_PACKAGE,
    FIXTURE_NODE_FORAGE_PACKAGE,
    STEWARDSHIP_ROOT,
    builtin_foraging_plane_proof,
    detect_import_root,
    detect_node_entry,
    detect_package_runtime,
    hermetic_forage_requests,
    infer_acquisition_spec,
    introspect_module,
    introspect_node_module,
    probe_domains_for,
    run_foraging_plane,
    verify_foraging_plane,
    forage_package,
)


def test_probe_domains_are_fixed_and_split() -> None:
    for domain in probe_domains_for("str"):
        assert len(domain["selection"]) >= 2
        assert len(domain["held_out"]) >= 1
        assert not set(domain["selection"]) & set(domain["held_out"])
    assert probe_domains_for("int")[0]["domain"] == "int"
    assert probe_domains_for("dict") == ()


def test_detect_import_root_fixture(tmp_path: Path) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "forage_lab.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    assert detect_import_root(staged, "forage_lab") == (".", "forage_lab")


def test_detect_import_root_src_layout(tmp_path: Path) -> None:
    package = tmp_path / "staged" / "demo-1.0" / "src" / "demo"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    assert detect_import_root(tmp_path / "staged", "demo") == ("demo-1.0/src", "demo")


def test_detect_import_root_ambiguous_refused(tmp_path: Path) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "alpha.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    (staged / "beta.py").write_text("def g(x):\n    return x\n", encoding="utf-8")
    try:
        detect_import_root(staged, "missing_hint")
    except ValueError as exc:
        assert "cannot detect a unique import root" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("ambiguous import root must be refused")


def test_introspection_enumerates_public_functions() -> None:
    result = introspect_module(FIXTURE_FORAGE_PACKAGE, "forage_lab", ".")
    assert result["ok"]
    names = [candidate["name"] for candidate in result["candidates"]]
    assert "shout" in names and "whisper" in names and "brittle" in names
    assert "_hidden" not in names and "CONSTANT" not in names


def test_introspection_import_failure_refused(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("import nonexistent_module_xyz\n", encoding="utf-8")
    result = introspect_module(tmp_path, "broken", ".")
    assert not result["ok"]
    assert "import failed" in result["error"]


def test_inference_recovers_complete_spec(tmp_path: Path) -> None:
    result = infer_acquisition_spec(
        slug="forage-lab",
        name="forage-lab (uncooperative fixture package)",
        source=FIXTURE_FORAGE_PACKAGE,
        staging_root=tmp_path,
        hint="forage_lab",
    )
    assert result["ok"]
    spec = result["spec"]
    assert spec.import_name == "forage_lab"
    assert spec.callable_name == "shout"
    assert spec.requires == ("text",)
    assert len(spec.probes) >= 3
    record = result["record"]
    assert "held-out probe failed" in record["rejected"]["brittle"]


def test_inference_refuses_package_without_candidate(tmp_path: Path) -> None:
    result = infer_acquisition_spec(
        slug="forage-empty",
        name="forage-empty (no viable candidate fixture)",
        source=FIXTURE_EMPTY_PACKAGE,
        staging_root=tmp_path,
        hint="forage_empty",
    )
    assert not result["ok"]
    assert result["stage"] == "select"


def test_inference_refuses_missing_callable_behavior(tmp_path: Path) -> None:
    # A candidate that raises on selection probes must never win.
    result = infer_acquisition_spec(
        slug="forage-empty",
        name="forage-empty renamed",
        source=FIXTURE_EMPTY_PACKAGE,
        staging_root=tmp_path,
        hint="",
    )
    assert not result["ok"]


def test_forage_fixture_package_end_to_end(tmp_path: Path) -> None:
    request = hermetic_forage_requests()[0]
    result = forage_package(request)
    assert result["ok"], result
    assert result["capability_id"] == "capability.absorbed-forage-lab"
    assert result["inference"]["winner"] == "shout"


def test_forage_stewardship_sdist_with_inferred_spec() -> None:
    request = {
        "name": "tomli TOML parser (stewardship sdist, inferred spec)",
        "slug": "tomli-foraged",
        "hint": "tomli",
        "source": STEWARDSHIP_ROOT / "tomli-2.4.1" / "tomli-2.4.1.tar.gz",
        "version": "2.4.1",
        "origin": {"kind": "pypi-sdist", "source": "stewardship/tomli-2.4.1/tomli-2.4.1.tar.gz"},
    }
    result = forage_package(request)
    assert result["ok"], result
    assert result["inference"]["import_name"] == "tomli"
    assert result["inference"]["domain"] == "toml"


def test_plane_runs_and_verifies(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_foraging_plane(report_dir)
    assert plane["ok"], plane
    assert plane["grade"]["forages_ok"] == plane["grade"]["forage_count"]
    verification = verify_foraging_plane(report_dir)
    assert verification["ok"], verification


def test_tampered_report_fails_verification(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_foraging_plane(report_dir)
    assert plane["ok"]
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["ok"] = not report["grade"]["ok"]
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_foraging_plane(report_dir)["ok"]


def test_builtin_foraging_plane_proof() -> None:
    result = builtin_foraging_plane_proof()
    assert result["ok"], result
    assert result["winner_is_shout"]
    assert result["brittle_rejected"]
    assert result["empty_refused"]
    assert result["tampered_rejected"]
    assert result["node_runtime"]
    assert result["node_winner_is_shout"]
    assert result["node_bundle_has_whisper"]
    assert result["node_forage_ok"]
    assert result["node_bundle_acquired"]
    assert result["used_skill_route_discovery"] is False


def test_detect_node_runtime_and_entry() -> None:
    assert detect_package_runtime(FIXTURE_NODE_FORAGE_PACKAGE) == "node"
    assert detect_package_runtime(FIXTURE_FORAGE_PACKAGE) == "python"
    path_root, entry = detect_node_entry(FIXTURE_NODE_FORAGE_PACKAGE, "forage-js")
    assert path_root == "."
    assert entry == "index.mjs"


def test_node_introspection_enumerates_exported_functions() -> None:
    result = introspect_node_module(FIXTURE_NODE_FORAGE_PACKAGE, "index.mjs")
    assert result["ok"], result
    names = [candidate["name"] for candidate in result["candidates"]]
    assert "shout" in names and "whisper" in names and "brittle" in names
    assert "_hidden" not in names and "CONSTANT" not in names and "needsThree" not in names


def test_node_inference_recovers_bundle(tmp_path: Path) -> None:
    result = infer_acquisition_spec(
        slug="forage-js",
        name="forage-js (uncooperative node fixture package)",
        source=FIXTURE_NODE_FORAGE_PACKAGE,
        staging_root=tmp_path,
        hint="forage-js",
        runtime="node",
    )
    assert result["ok"], result
    spec = result["spec"]
    assert spec.runtime == "node"
    assert spec.entry == "index.mjs"
    assert spec.callable_name == "shout"
    assert result["record"]["winner"] == "shout"
    assert "whisper" in result["record"]["bundle"]
    assert "held-out probe failed" in result["record"]["rejected"]["brittle"]
    extras = [item.callable_name for item in result["bundle_specs"]]
    assert "whisper" in extras


def test_node_inference_refuses_package_without_candidate(tmp_path: Path) -> None:
    result = infer_acquisition_spec(
        slug="forage-js-empty",
        name="forage-js-empty",
        source=FIXTURE_NODE_EMPTY_PACKAGE,
        staging_root=tmp_path,
        hint="forage-js-empty",
        runtime="node",
    )
    assert not result["ok"]
    assert result["stage"] == "select"


def test_forage_node_fixture_end_to_end() -> None:
    result = forage_package(
        {
            "name": "forage-js (uncooperative node fixture package)",
            "slug": "forage-js",
            "hint": "forage-js",
            "runtime": "node",
            "source": FIXTURE_NODE_FORAGE_PACKAGE,
            "origin": {"kind": "fixture", "source": "tests/fixtures/external_packages/forage-js"},
        }
    )
    assert result["ok"], result
    assert result["runtime"] == "node"
    assert result["capability_id"] == "capability.absorbed-forage-js"
    assert result["inference"]["winner"] == "shout"
    assert any(item.get("callable") == "whisper" and item.get("ok") for item in result["bundle"])
