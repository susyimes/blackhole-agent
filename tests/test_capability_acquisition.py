"""Tests for the capability acquisition plane."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent.capability_absorption import (
    load_manifest,
    prove_absorbed_capability,
    run_absorption_case,
    run_absorption_cases,
)
from blackhole_agent.capability_acquisition import (
    AcquisitionSpec,
    FIXTURE_PACKAGE,
    acquire_capability,
    builtin_acquisition_plane_proof,
    fixture_acquisition_spec,
    fixture_node_acquisition_spec,
    stage_acquisition_source,
    stewardship_acquisition_specs,
    synthesize_acquisition,
    synthesize_adapter_source,
    verify_acquisition_plane,
)


def test_spec_validate_accepts_fixture() -> None:
    spec = fixture_acquisition_spec().validate()
    assert spec.slug == "json-indenter"
    assert spec.provides == "indented_json"


def test_spec_validate_rejects_bad_slug() -> None:
    spec = fixture_acquisition_spec()
    with pytest.raises(ValueError, match="invalid acquisition slug"):
        AcquisitionSpec(
            slug="Bad Slug",
            name=spec.name,
            source=spec.source,
            import_name=spec.import_name,
            callable_name=spec.callable_name,
            requires=spec.requires,
            provides=spec.provides,
            probes=spec.probes,
        ).validate()


def test_spec_validate_rejects_missing_source(tmp_path: Path) -> None:
    spec = fixture_acquisition_spec()
    with pytest.raises(ValueError, match="source not found"):
        AcquisitionSpec(
            slug=spec.slug,
            name=spec.name,
            source=tmp_path / "nope",
            import_name=spec.import_name,
            callable_name=spec.callable_name,
            requires=spec.requires,
            provides=spec.provides,
            probes=spec.probes,
        ).validate()


def test_spec_validate_rejects_single_probe() -> None:
    spec = fixture_acquisition_spec()
    with pytest.raises(ValueError, match="at least two probe"):
        AcquisitionSpec(
            slug=spec.slug,
            name=spec.name,
            source=spec.source,
            import_name=spec.import_name,
            callable_name=spec.callable_name,
            requires=spec.requires,
            provides=spec.provides,
            probes=spec.probes[:1],
        ).validate()


def test_stage_directory_source(tmp_path: Path) -> None:
    staged = tmp_path / "staged"
    stage_acquisition_source(FIXTURE_PACKAGE, staged)
    assert (staged / "json_indenter.py").is_file()
    assert not (staged / "absorption.json").exists()


def test_stage_tarball_source(tmp_path: Path) -> None:
    spec = stewardship_acquisition_specs()[0]
    staged = tmp_path / "staged"
    stage_acquisition_source(spec.source, staged)
    assert (staged / "tomli-2.4.1" / "src" / "tomli" / "__init__.py").is_file()


def test_stage_rejects_unknown_source(tmp_path: Path) -> None:
    bogus = tmp_path / "tool.rar"
    bogus.write_bytes(b"not a tar")
    with pytest.raises(ValueError, match="unsupported acquisition source"):
        stage_acquisition_source(bogus, tmp_path / "staged")
    bogus_zip = tmp_path / "tool.zip"
    bogus_zip.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="unsupported acquisition source"):
        stage_acquisition_source(bogus_zip, tmp_path / "staged")


def test_stage_skips_vendored_tests_trees(tmp_path: Path) -> None:
    import tarfile

    payload = tmp_path / "payload"
    (payload / "demo").mkdir(parents=True)
    (payload / "demo" / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (payload / "tests").mkdir()
    (payload / "tests" / "test_demo.py").write_text("assert True\n", encoding="utf-8")
    archive = tmp_path / "demo-1.0.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload / "demo", arcname="demo-1.0/demo")
        tar.add(payload / "tests", arcname="demo-1.0/tests")
    staged = tmp_path / "staged"
    stage_acquisition_source(archive, staged)
    assert (staged / "demo-1.0" / "demo" / "__init__.py").is_file()
    assert not (staged / "demo-1.0" / "tests").exists()


def test_stage_wheel_or_zip_source(tmp_path: Path) -> None:
    import zipfile

    wheel = tmp_path / "demo-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("demo/__init__.py", "VALUE = 1\n")
    staged = tmp_path / "staged"
    stage_acquisition_source(wheel, staged)
    assert (staged / "demo" / "__init__.py").is_file()


def test_adapter_source_is_generic_and_deterministic() -> None:
    spec = fixture_acquisition_spec()
    first = synthesize_adapter_source(spec)
    assert first == synthesize_adapter_source(spec)
    assert "json_indenter" in first and "indented_json" in first


def test_synthesis_derives_cases_from_real_behavior(tmp_path: Path) -> None:
    result = synthesize_acquisition(fixture_acquisition_spec(), tmp_path)
    assert result["ok"], result
    manifest = result["manifest"]
    assert manifest["slug"] == "json-indenter"
    assert len(manifest["cases"]) == 2
    first = manifest["cases"][0]
    assert first["expect"]["indented_json"] == '{\n  "a": 2,\n  "b": 1\n}'
    # The synthesized tree passes the absorption plane's own validation.
    validated = load_manifest(Path(result["staged_dir"]))
    assert validated["provides"] == ["indented_json"]
    cases = run_absorption_cases(Path(result["staged_dir"]), validated)
    assert cases["ok"], cases


def test_synthesis_refuses_missing_callable(tmp_path: Path) -> None:
    spec = fixture_acquisition_spec()
    result = synthesize_acquisition(
        AcquisitionSpec(
            slug=spec.slug,
            name=spec.name,
            source=spec.source,
            import_name=spec.import_name,
            callable_name="missing_function",
            requires=spec.requires,
            provides=spec.provides,
            probes=spec.probes,
        ),
        tmp_path,
    )
    assert not result["ok"]
    assert result["stage"] == "probe"
    # Refused before a manifest exists: nothing absorbable is left behind.
    assert not (tmp_path / spec.slug / "absorption.json").exists()


def test_synthesis_refuses_failing_probe(tmp_path: Path) -> None:
    spec = fixture_acquisition_spec()
    result = synthesize_acquisition(
        AcquisitionSpec(
            slug=spec.slug,
            name=spec.name,
            source=spec.source,
            import_name=spec.import_name,
            callable_name=spec.callable_name,
            requires=spec.requires,
            provides=spec.provides,
            probes=({"raw_json": '{"broken"'}, *spec.probes),
        ),
        tmp_path,
    )
    assert not result["ok"]
    assert result["stage"] == "probe"


def test_synthesis_refuses_bad_path_root(tmp_path: Path) -> None:
    spec = fixture_acquisition_spec()
    result = synthesize_acquisition(
        AcquisitionSpec(
            slug=spec.slug,
            name=spec.name,
            source=spec.source,
            import_name=spec.import_name,
            callable_name=spec.callable_name,
            requires=spec.requires,
            provides=spec.provides,
            probes=spec.probes,
            path_root="missing-subdir",
        ),
        tmp_path,
    )
    assert not result["ok"]
    assert result["stage"] == "stage"


def test_tampered_derived_expectation_fails(tmp_path: Path) -> None:
    result = synthesize_acquisition(fixture_acquisition_spec(), tmp_path)
    assert result["ok"], result
    staged_dir = Path(result["staged_dir"])
    manifest_path = staged_dir / "absorption.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cases"][0]["expect"] = {"indented_json": "hand-edited"}
    tampered = run_absorption_case(staged_dir, manifest["command"], manifest["cases"][0])
    assert not tampered["ok"]


def test_acquire_fixture_package_end_to_end() -> None:
    result = acquire_capability(fixture_acquisition_spec(), scenario=True)
    assert result["ok"], result
    assert result["capability_id"] == "capability.absorbed-json-indenter"
    honesty = result["honesty"]
    assert honesty["unplannable_before"]
    assert honesty["grown_plan_solved"]
    assert honesty["ablation_unplannable"]
    proof = prove_absorbed_capability("json-indenter")
    assert proof["ok"], proof


def test_stewardship_specs_synthesize(tmp_path: Path) -> None:
    specs = stewardship_acquisition_specs()
    assert {spec.slug for spec in specs} == {"tomli-parser", "python-markdown", "marked-renderer"}
    for spec in specs:
        result = synthesize_acquisition(spec, tmp_path)
        assert result["ok"], result
        assert result["case_count"] >= 2


def test_node_adapter_source_is_generic_and_deterministic() -> None:
    spec = fixture_node_acquisition_spec()
    first = synthesize_adapter_source(spec)
    assert first == synthesize_adapter_source(spec)
    assert "index.mjs" in first and "shouted_text" in first


def test_node_synthesis_derives_cases_from_real_behavior(tmp_path: Path) -> None:
    result = synthesize_acquisition(fixture_node_acquisition_spec(), tmp_path)
    assert result["ok"], result
    manifest = result["manifest"]
    assert manifest["slug"] == "js-shouter"
    assert manifest["command"][0] == "node"
    first = manifest["cases"][0]
    assert first["expect"]["shouted_text"] == "HELLO UNBOUND"
    validated = load_manifest(Path(result["staged_dir"]))
    cases = run_absorption_cases(Path(result["staged_dir"]), validated)
    assert cases["ok"], cases


def test_node_synthesis_refuses_missing_callable(tmp_path: Path) -> None:
    spec = fixture_node_acquisition_spec()
    result = synthesize_acquisition(
        AcquisitionSpec(
            slug=spec.slug,
            name=spec.name,
            source=spec.source,
            import_name=spec.import_name,
            callable_name="missing_function",
            requires=spec.requires,
            provides=spec.provides,
            runtime="node",
            entry=spec.entry,
            probes=spec.probes,
        ),
        tmp_path,
    )
    assert not result["ok"]
    assert result["stage"] == "probe"
    assert not (tmp_path / spec.slug / "absorption.json").exists()


def test_node_synthesis_refuses_failing_probe(tmp_path: Path) -> None:
    spec = fixture_node_acquisition_spec()
    result = synthesize_acquisition(
        AcquisitionSpec(
            slug=spec.slug,
            name=spec.name,
            source=spec.source,
            import_name=spec.import_name,
            callable_name=spec.callable_name,
            requires=spec.requires,
            provides=spec.provides,
            runtime="node",
            entry=spec.entry,
            probes=({"quiet_text": 42}, *spec.probes),
        ),
        tmp_path,
    )
    assert not result["ok"]
    assert result["stage"] == "probe"


def test_node_synthesis_refuses_missing_entry(tmp_path: Path) -> None:
    spec = fixture_node_acquisition_spec()
    result = synthesize_acquisition(
        AcquisitionSpec(
            slug=spec.slug,
            name=spec.name,
            source=spec.source,
            import_name=spec.import_name,
            callable_name=spec.callable_name,
            requires=spec.requires,
            provides=spec.provides,
            runtime="node",
            entry="missing.mjs",
            probes=spec.probes,
        ),
        tmp_path,
    )
    assert not result["ok"]
    assert result["stage"] == "stage"


def test_spec_validate_rejects_unknown_runtime() -> None:
    spec = fixture_acquisition_spec()
    with pytest.raises(ValueError, match="unsupported acquisition runtime"):
        AcquisitionSpec(
            slug=spec.slug,
            name=spec.name,
            source=spec.source,
            import_name=spec.import_name,
            callable_name=spec.callable_name,
            requires=spec.requires,
            provides=spec.provides,
            runtime="ruby",
            probes=spec.probes,
        ).validate()


def test_spec_validate_rejects_escaping_node_entry() -> None:
    spec = fixture_node_acquisition_spec()
    with pytest.raises(ValueError, match="entry must stay inside"):
        AcquisitionSpec(
            slug=spec.slug,
            name=spec.name,
            source=spec.source,
            import_name=spec.import_name,
            callable_name=spec.callable_name,
            requires=spec.requires,
            provides=spec.provides,
            runtime="node",
            entry="../escape.mjs",
            probes=spec.probes,
        ).validate()


def test_builtin_acquisition_plane_proof() -> None:
    result = builtin_acquisition_plane_proof()
    assert result["ok"], result
    assert result["synthesis_ok"]
    assert result["bad_callable_refused"]
    assert result["failing_probe_refused"]
    assert result["tampered_case_rejected"]
    assert result["node_synthesis_ok"]
    assert result["node_bad_callable_refused"]
    assert result["plane_ok"]
    assert result["verify_ok"]


def test_verify_acquisition_plane_rejects_forgery(tmp_path: Path) -> None:
    from blackhole_agent.capability_acquisition import run_acquisition_plane

    report_dir = tmp_path / "report"
    result = run_acquisition_plane(report_dir)
    assert result["ok"], result
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["ok"] = False  # forged downgrade
    report_path.write_text(json.dumps(report), encoding="utf-8")
    verification = verify_acquisition_plane(report_dir)
    assert not verification["ok"]
    assert not verification["digest_ok"]


def test_verify_acquisition_plane_missing_report(tmp_path: Path) -> None:
    verification = verify_acquisition_plane(tmp_path)
    assert not verification["ok"]
