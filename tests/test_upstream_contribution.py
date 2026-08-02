"""Unit tests for the upstream contribution plane (hermetic; no network)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from blackhole_agent import upstream_contribution as uc


def _target(tmp_path: Path) -> Path:
    return uc._proof_target(tmp_path / "stewardship")


def _fetcher(tag_archive: bytes, head_archive: bytes | None = None):
    repo_url = "https://github.com/proof/contribprobe"
    tag_url = uc.github_archive_url(repo_url, uc._PROOF_VERSION)
    head_url = uc.github_archive_url(repo_url, "HEAD")

    def get(url: str) -> bytes:
        if url == head_url:
            if head_archive is None:
                raise ValueError("no head archive")
            return head_archive
        if url == tag_url:
            return tag_archive
        raise ValueError(f"unexpected url {url}")

    return get


def test_github_archive_url_strips_repo_shapes() -> None:
    assert (
        uc.github_archive_url("https://github.com/hukkin/tomli", "2.4.1")
        == "https://codeload.github.com/hukkin/tomli/tar.gz/2.4.1"
    )
    assert uc.github_archive_url("https://github.com/hukkin/tomli.git/", "HEAD").endswith(
        "/hukkin/tomli/tar.gz/HEAD"
    )


def test_rebase_patch_paths_strips_sdist_top_dir() -> None:
    rebased = uc.rebase_patch_paths(uc._PROOF_PATCH, f"{uc._PROOF_PKG}-{uc._PROOF_VERSION}")
    assert f"a/{uc._PROOF_PKG}/__init__.py" not in rebased
    assert f"a/src/{uc._PROOF_PKG}/__init__.py" in rebased
    with pytest.raises(uc.ContributionRejected) as excinfo:
        uc.rebase_patch_paths("--- a/other/x.py\n+++ b/other/x.py\n", "tomli-2.4.1")
    assert excinfo.value.verdict == "patch_rebase"


def test_synthesize_regression_test_shape() -> None:
    text = uc.synthesize_regression_test("boom-valueerror", "boom.py", "tests", "src")
    assert "parents[1]" in text
    assert "'src'" in text
    assert "def test_boom_valueerror_regression" in text
    compile(text, "<synth>", "exec")


def test_build_contribution_submittable_end_to_end(tmp_path) -> None:
    target = _target(tmp_path)
    tag = uc._proof_archive(uc._PROOF_INIT_BUGGY)
    head = uc._proof_archive(uc._PROOF_INIT_BUGGY, top=f"{uc._PROOF_PKG}-HEAD")
    result = uc.build_contribution(
        target, "boom-valueerror", out_root=tmp_path / "out", fetcher=_fetcher(tag, head)
    )
    assert result["ok"] and result["submittable"]
    assert result["baseline"]["passed"] == 2
    assert result["patched"]["passed"] == 3  # 2 pristine + 1 synthesized regression
    bundle_dir = Path(result["bundle_dir"])
    assert (bundle_dir / "contribution.patch").exists()
    assert (bundle_dir / "boom.py").exists()
    verified = uc.verify_contribution_bundle(bundle_dir)
    assert verified["ok"] and verified["submittable"]


def test_build_contribution_triages_already_fixed_at_head(tmp_path) -> None:
    target = _target(tmp_path)
    tag = uc._proof_archive(uc._PROOF_INIT_BUGGY)
    head = uc._proof_archive(uc._PROOF_INIT_FIXED, top=f"{uc._PROOF_PKG}-HEAD")
    result = uc.build_contribution(
        target, "boom-valueerror", out_root=tmp_path / "out", fetcher=_fetcher(tag, head)
    )
    assert result["ok"] and not result["submittable"]
    assert result["verdict"] == "already_fixed_at_head"
    bundle = json.loads((Path(result["bundle_dir"]) / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["submittable"] is False
    assert bundle["payload_sha256"] == {}


def test_build_contribution_rejects_breaking_patch(tmp_path) -> None:
    target = _target(tmp_path)
    (target / "patches" / "boom.patch").write_text(uc._PROOF_BREAKING_PATCH, encoding="utf-8")
    tag = uc._proof_archive(uc._PROOF_INIT_BUGGY)
    head = uc._proof_archive(uc._PROOF_INIT_BUGGY, top=f"{uc._PROOF_PKG}-HEAD")
    with pytest.raises(uc.ContributionRejected) as excinfo:
        uc.build_contribution(
            target, "boom-valueerror", out_root=tmp_path / "out", fetcher=_fetcher(tag, head)
        )
    assert excinfo.value.verdict == "patch_regression"


def test_build_contribution_rejects_defect_absent_at_tag(tmp_path) -> None:
    target = _target(tmp_path)
    tag = uc._proof_archive(uc._PROOF_INIT_FIXED)  # tag already fixed: stale claim
    head = uc._proof_archive(uc._PROOF_INIT_FIXED, top=f"{uc._PROOF_PKG}-HEAD")
    with pytest.raises(uc.ContributionRejected) as excinfo:
        uc.build_contribution(
            target, "boom-valueerror", out_root=tmp_path / "out", fetcher=_fetcher(tag, head)
        )
    assert excinfo.value.verdict == "defect_absent_at_tag"


def test_build_contribution_rejects_unknown_defect(tmp_path) -> None:
    target = _target(tmp_path)
    with pytest.raises(uc.ContributionRejected) as excinfo:
        uc.build_contribution(target, "nope", out_root=tmp_path / "out", fetcher=_fetcher(b""))
    assert excinfo.value.verdict == "defect_unknown"


def test_verify_contribution_bundle_detects_tamper(tmp_path) -> None:
    target = _target(tmp_path)
    tag = uc._proof_archive(uc._PROOF_INIT_BUGGY)
    head = uc._proof_archive(uc._PROOF_INIT_BUGGY, top=f"{uc._PROOF_PKG}-HEAD")
    result = uc.build_contribution(
        target, "boom-valueerror", out_root=tmp_path / "out", fetcher=_fetcher(tag, head)
    )
    bundle_dir = Path(result["bundle_dir"])
    payload = bundle_dir / "contribution.patch"
    payload.write_text(payload.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    verified = uc.verify_contribution_bundle(bundle_dir)
    assert not verified["ok"]
    assert "contribution.patch" in verified["mismatched"]


def test_builtin_proof_ok() -> None:
    result = uc.builtin_upstream_contribution_proof()
    assert result["ok"], result
    assert not result["used_skill_route_discovery"]


# ---------------------------------------------------------------------------
# npm ecosystem (node runtime; hermetic fabricated repo)

node_available = pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not on PATH")


@node_available
def test_npm_contribution_leg_submittable_and_triaged(tmp_path: Path) -> None:
    target = uc._npm_proof_target(tmp_path / "stewardship")
    tag_archive = uc._npm_proof_archive(uc._NPM_INDEX_BUGGY, top=f"{uc._NPM_PKG}-{uc._NPM_VERSION}")
    repo_url = "https://github.com/proof/quirkcontrib"
    tag_url = uc.github_archive_url(repo_url, uc._NPM_VERSION)
    head_url = uc.github_archive_url(repo_url, "HEAD")

    def fetcher_unfixed(url: str) -> bytes:
        if url == head_url:
            return uc._npm_proof_archive(uc._NPM_INDEX_BUGGY, top=f"{uc._NPM_PKG}-HEAD")
        if url == tag_url:
            return tag_archive
        raise ValueError(url)

    built = uc.build_contribution(target, "spoiler-crash", out_root=tmp_path / "artifacts", fetcher=fetcher_unfixed)
    assert built["ok"] and built["submittable"]
    assert built["baseline"]["ok"] and built["patched"]["ok"]
    # the installed regression test joined the patched suite
    assert built["patched"]["passed"] > built["baseline"]["passed"]
    verdict = uc.verify_contribution_bundle(Path(built["bundle_dir"]))
    assert verdict["ok"], verdict
    payloads = json.loads((Path(built["bundle_dir"]) / "bundle.json").read_text(encoding="utf-8"))["payload_sha256"]
    assert "contribution.patch" in payloads and "regression.test.cjs" in payloads

    def fetcher_fixed(url: str) -> bytes:
        if url == head_url:
            return uc._npm_proof_archive(uc._NPM_INDEX_FIXED, top=f"{uc._NPM_PKG}-HEAD")
        return tag_archive

    triaged = uc.build_contribution(target, "spoiler-crash", out_root=tmp_path / "artifacts-fixed", fetcher=fetcher_fixed)
    assert triaged["ok"] and not triaged["submittable"]
    assert triaged["verdict"] == "already_fixed_at_head"


@node_available
def test_npm_contribution_requires_repo_native_patch(tmp_path: Path) -> None:
    target = uc._npm_proof_target(tmp_path / "stewardship")
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    del manifest["defects"][0]["repo_patch"]
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(uc.ContributionRejected) as excinfo:
        uc.build_contribution(target, "spoiler-crash", out_root=tmp_path / "artifacts", fetcher=lambda u: b"")
    assert excinfo.value.verdict == "repo_patch_missing"


def test_builtin_contribution_proof_covers_npm_leg() -> None:
    if shutil.which("node") is None:
        pytest.skip("node runtime not on PATH")
    proof = uc.builtin_upstream_contribution_proof()
    assert proof["ok"], proof
    assert proof["npm_submittable_sealed"] and proof["npm_tamper_detected"]
