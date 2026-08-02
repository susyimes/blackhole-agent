"""Unit tests for the upstream discovery plane (pure paths only; no probing)."""

from __future__ import annotations

import json

from blackhole_agent import upstream_discovery as ud

_TEST_PRELUDE = "def render(text, plugins):\n    return None"


def test_max_exponent_flags_quadratic_growth() -> None:
    times = [(1000, 0.1), (2000, 0.4), (4000, 1.6)]
    assert ud._max_exponent(times) >= 1.9


def test_max_exponent_ignores_linear_growth_and_noise() -> None:
    linear = [(1000, 0.5), (2000, 1.0), (4000, 2.0)]
    assert ud._max_exponent(linear) <= 1.01
    noisy = [(1000, 0.001), (2000, 0.5)]  # below the 0.02s noise floor
    assert ud._max_exponent(noisy) == 0.0


def test_worker_source_embeds_every_generator_and_driver() -> None:
    src = ud._worker_source(_TEST_PRELUDE)
    for name in ud.GENERATORS:
        assert f"GENERATORS[{name!r}]" in src
    assert "__GENERATOR_SOURCES__" not in src
    assert "__DRIVER_PRELUDE__" not in src
    assert _TEST_PRELUDE in src


def test_synthesize_repro_writes_standalone_script(tmp_path) -> None:
    repro = ud.synthesize_repro("nested_link", "complexity", 1875, tmp_path, _TEST_PRELUDE)
    content = repro.read_text(encoding="utf-8")
    assert "def gen(n):" in content
    assert "'[' * n" in content
    assert _TEST_PRELUDE in content
    assert "render(text, PLUGINS)" in content
    assert "sys.exit(1 if defect else 0)" in content


def test_report_verification_detects_tampered_verdict(tmp_path) -> None:
    repro = ud.synthesize_repro("footnote_refs", "complexity", 3500, tmp_path / "repros", _TEST_PRELUDE)
    finding = {
        "generator": "footnote_refs",
        "kind": "complexity",
        "flagged": True,
        "minimized_n": 3500,
        "repro": str(repro.relative_to(tmp_path)),
        "repro_sha256": ud._sha256_file(repro),
        "pristine_repro_exit": 1,
    }
    report = {
        "schema_version": ud.SCHEMA_VERSION,
        "target": {"name": "mistune", "version": "3.2.1"},
        "sdist_sha256": "0" * 64,
        "findings": [finding],
        "finding_count": 1,
        "scanned_at": "2026-08-02T00:00:00Z",
    }
    report["chain_digest"] = ud._report_chain(report)
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert ud.verify_discovery_report(tmp_path)["ok"]

    tampered = json.loads(json.dumps(report))
    tampered["findings"][0]["flagged"] = False
    (tmp_path / "report.json").write_text(json.dumps(tampered), encoding="utf-8")
    verdict = ud.verify_discovery_report(tmp_path)
    assert not verdict["ok"]
    assert any("chain digest" in p for p in verdict["problems"])


def test_report_verification_detects_tampered_repro_file(tmp_path) -> None:
    repro = ud.synthesize_repro("nested_link", "complexity", 1875, tmp_path / "repros", _TEST_PRELUDE)
    finding = {
        "generator": "nested_link",
        "kind": "complexity",
        "flagged": True,
        "minimized_n": 1875,
        "repro": str(repro.relative_to(tmp_path)),
        "repro_sha256": ud._sha256_file(repro),
        "pristine_repro_exit": 1,
    }
    report = {
        "schema_version": ud.SCHEMA_VERSION,
        "target": {"name": "mistune", "version": "3.2.1"},
        "sdist_sha256": "0" * 64,
        "findings": [finding],
        "finding_count": 1,
        "scanned_at": "2026-08-02T00:00:00Z",
    }
    report["chain_digest"] = ud._report_chain(report)
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    repro.write_text("# tampered\n", encoding="utf-8")
    verdict = ud.verify_discovery_report(tmp_path)
    assert not verdict["ok"]
    assert any("hash mismatch" in p for p in verdict["problems"])


def test_load_target_never_reads_defects(tmp_path) -> None:
    manifest = {
        "name": "x",
        "version": "1.0",
        "sdist": "x.tar.gz",
        "sdist_sha256": "0" * 64,
        "src_subdir": "x-1.0/src",
        "driver": {"prelude": _TEST_PRELUDE},
        "defects": [{"id": "curated-only"}],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    target = ud.load_target(tmp_path)
    assert target.name == "x"
    assert target.driver_prelude == _TEST_PRELUDE
    assert not hasattr(target, "defects")
