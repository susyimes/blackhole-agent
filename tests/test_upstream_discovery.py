"""Unit tests for the upstream discovery plane (pure paths only; no probing)."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# node runtime (driver.runtime="node"; smoke tests need a real node runtime)

node_available = pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not on PATH")

_NODE_PRELUDE = (
    "function render(text, plugins) {\n"
    "    return require(TARGET_DIR).render_text(text);\n"
    "}\n"
)


def test_node_worker_source_embeds_every_generator_and_driver() -> None:
    src = ud._node_worker_source(_NODE_PRELUDE)
    for name in ud.GENERATORS:
        assert f"GENERATORS[{json.dumps(name)}]" in src
    assert "__GENERATOR_SOURCES__" not in src
    assert "__DRIVER_PRELUDE__" not in src
    assert _NODE_PRELUDE in src
    assert "process.hrtime.bigint" in src


def test_synthesize_node_repro_writes_standalone_script(tmp_path) -> None:
    repro = ud.synthesize_repro("nested_link", "complexity", 1875, tmp_path, _NODE_PRELUDE, "node")
    assert repro.suffix == ".cjs"
    content = repro.read_text(encoding="utf-8")
    assert "function gen(n)" in content
    assert "'['.repeat(n)" in content
    assert _NODE_PRELUDE in content
    assert "process.exit(defect ? 1 : 0)" in content
    assert "process.argv[2]" in content


def _make_quirk_npm_target(tmp_path):
    """Fabricated npm target whose render_text carries two planted defects.

    Quadratic on '[' count (complexity oracle, nested_link) and an uncaught
    RangeError on '~~' (crash oracle, unclosed_spoiler). Every other shape is
    linear, so the rest of the battery must stay silent (negative controls).
    """
    index_js = (
        b"exports.render_text = function (text) {\n"
        b"    if (text.includes('~~')) { throw new RangeError('spoiler stack overflow'); }\n"
        b"    let c = 0;\n"
        b"    for (let i = 0; i < text.length; i++) {\n"
        b"        if (text[i] === '[') {\n"
        b"            for (let j = 0; j < text.length; j++) { c += text.charCodeAt(j) & 1; }\n"
        b"        }\n"
        b"    }\n"
        b"    return c;\n"
        b"};\n"
    )
    pkg_json = json.dumps({"name": "quirk", "version": "1.0.0", "main": "index.js"}).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in (("package/package.json", pkg_json), ("package/index.js", index_js)):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    tarball = buf.getvalue()
    target_root = tmp_path / "quirk-1.0.0"
    target_root.mkdir()
    (target_root / "quirk-1.0.0.tgz").write_bytes(tarball)
    manifest = {
        "name": "quirk",
        "version": "1.0.0",
        "sdist": "quirk-1.0.0.tgz",
        "sdist_sha256": hashlib.sha256(tarball).hexdigest(),
        "src_subdir": "package",
        "driver": {"prelude": _NODE_PRELUDE, "smoke_input": "x", "runtime": "node"},
        "defects": [],
    }
    (target_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return target_root


@node_available
def test_node_discovery_scan_flags_both_oracles(tmp_path) -> None:
    target_root = _make_quirk_npm_target(tmp_path)
    scan = ud.run_discovery_scan(target_root, artifact_root=tmp_path / "artifacts")
    assert scan["ok"], scan
    report_dir = Path(scan["report_dir"])
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["driver_runtime"] == "node"

    by_gen = {f["generator"]: f for f in report["findings"]}
    assert by_gen["nested_link"]["flagged"] and by_gen["nested_link"]["kind"] == "complexity"
    assert by_gen["unclosed_spoiler"]["flagged"] and by_gen["unclosed_spoiler"]["kind"] == "crash"
    assert by_gen["unclosed_spoiler"]["pristine_repro_exit"] == 1
    # inline_links also flags: its text contains '[', and the planted defect
    # is quadratic in '[' count x length -- an honest positive, not noise.
    assert by_gen["inline_links"]["flagged"] and by_gen["inline_links"]["kind"] == "complexity"
    # negative controls: bracket-free benign shapes stay silent
    assert not by_gen["digit_run"]["flagged"]
    assert not by_gen["table_row"]["flagged"]
    assert not by_gen["nested_emphasis"]["flagged"]

    for gen in ("nested_link", "unclosed_spoiler"):
        repro = report_dir / by_gen[gen]["repro"]
        assert repro.suffix == ".cjs"
        assert ud._sha256_file(repro) == by_gen[gen]["repro_sha256"]

    assert ud.verify_discovery_report(report_dir)["ok"]

    # the synthesized node repro independently re-detects the defect on the
    # pristine tree (exit 1), not just inside the scan harness
    scratch = tmp_path / "pristine"
    src_dir = ud.extract_pristine(ud.load_target(target_root), scratch)
    repro = report_dir / by_gen["unclosed_spoiler"]["repro"]
    assert ud.run_repro(repro, src_dir) == 1


def test_load_target_defaults_runtime_to_python(tmp_path) -> None:
    manifest = {
        "name": "x",
        "version": "1.0",
        "sdist": "x.tar.gz",
        "sdist_sha256": "0" * 64,
        "src_subdir": "x-1.0/src",
        "driver": {"prelude": _TEST_PRELUDE},
        "defects": [],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert ud.load_target(tmp_path).driver_runtime == "python"
