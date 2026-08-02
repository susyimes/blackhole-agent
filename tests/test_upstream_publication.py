"""Unit tests for the upstream publication plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent import upstream_publication as up


def _setup(tmp_path: Path):
    upstream, fork = up._proof_remotes(tmp_path / "remotes", up._PROOF_SOURCE_V1)
    gh = up._FakeGh(fork)
    manifest = {"contribution": {"tests_subdir": "tests"}}
    bundle_dir = up._proof_write_bundle(
        tmp_path / "bundle-root",
        patch=up._PROOF_PATCH,
        test_text=up._PROOF_TEST,
        repro_text=up._PROOF_REPRO,
    )
    return upstream, fork, gh, manifest, bundle_dir


def test_load_submittable_bundle_requires_submittable(tmp_path) -> None:
    bundle_dir = up._proof_write_bundle(
        tmp_path, patch=up._PROOF_PATCH, test_text=up._PROOF_TEST,
        repro_text=up._PROOF_REPRO, submittable=False,
    )
    with pytest.raises(up.PublicationRefused) as excinfo:
        up.load_submittable_bundle(bundle_dir)
    assert excinfo.value.verdict == "bundle_not_submittable"


def test_load_submittable_bundle_detects_tampering(tmp_path) -> None:
    bundle_dir = up._proof_write_bundle(
        tmp_path, patch=up._PROOF_PATCH, test_text=up._PROOF_TEST,
        repro_text=up._PROOF_REPRO,
    )
    patch_path = bundle_dir / "contribution.patch"
    patch_path.write_bytes(patch_path.read_bytes() + b"\n")
    with pytest.raises(up.PublicationRefused) as excinfo:
        up.load_submittable_bundle(bundle_dir)
    assert excinfo.value.verdict == "bundle_seal"


def test_dry_run_passes_gates_without_outward_action(tmp_path) -> None:
    _, _, gh, manifest, bundle_dir = _setup(tmp_path)
    result = up.publish_contribution(
        bundle_dir, publish=False, gh=gh, verifier=up._proof_verifier,
        manifest=manifest, out_root=tmp_path / "receipts",
    )
    assert result["ok"] and result["verdict"] == "dry_run_gates_passed"
    assert result["branch"] == "blackhole/masking-quadratic"
    assert not gh.prs and not gh.forked


def test_publish_end_to_end_seals_verifiable_receipt(tmp_path) -> None:
    _, _, gh, manifest, bundle_dir = _setup(tmp_path)
    result = up.publish_contribution(
        bundle_dir, publish=True, gh=gh, verifier=up._proof_verifier,
        manifest=manifest, out_root=tmp_path / "receipts",
    )
    assert result["ok"] and result["verdict"] == "published"
    assert len(gh.prs) == 1
    receipt_dir = Path(result["receipt_dir"])
    assert (receipt_dir / "pr-body.md").exists()
    assert (receipt_dir / "commit-message.txt").exists()
    offline = up.verify_publication_receipt(receipt_dir)
    assert offline["ok"] and offline["published"]
    online = up.verify_publication_receipt(receipt_dir, gh=gh)
    assert online["ok"] and online["live_pr"]["state"] == "OPEN"
    assert online["live_pr"]["headRefOid"] == result["head_sha"]


def test_pr_body_discloses_automation_and_digests(tmp_path) -> None:
    bundle_dir = up._proof_write_bundle(
        tmp_path, patch=up._PROOF_PATCH, test_text=up._PROOF_TEST,
        repro_text=up._PROOF_REPRO,
    )
    bundle = up.load_submittable_bundle(bundle_dir)
    body = up.render_pr_body(bundle, "scaling.test.py", "repro.py")
    assert "autonomous stewardship agent" in body
    assert "sha256" in body
    for digest in bundle["payload_sha256"].values():
        assert digest in body


def test_commit_message_carries_automation_trailer(tmp_path) -> None:
    bundle_dir = up._proof_write_bundle(
        tmp_path, patch=up._PROOF_PATCH, test_text=up._PROOF_TEST,
        repro_text=up._PROOF_REPRO,
    )
    bundle = up.load_submittable_bundle(bundle_dir)
    message = up.render_commit_message(bundle)
    assert up.AUTOMATION_TRAILER in message
    assert message.startswith("fix: ")


def test_republication_is_idempotent(tmp_path) -> None:
    _, _, gh, manifest, bundle_dir = _setup(tmp_path)
    first = up.publish_contribution(
        bundle_dir, publish=True, gh=gh, verifier=up._proof_verifier,
        manifest=manifest, out_root=tmp_path / "receipts",
    )
    assert first["verdict"] == "published"
    second = up.publish_contribution(
        bundle_dir, publish=True, gh=gh, verifier=up._proof_verifier,
        manifest=manifest, out_root=tmp_path / "receipts",
    )
    assert second["verdict"] == "already_published"
    assert len(gh.prs) == 1
    verified = up.verify_publication_receipt(Path(second["receipt_dir"]), gh=gh)
    assert verified["ok"] and verified["verdict"] == "already_published"


def test_merged_pr_is_triaged_never_republished(tmp_path) -> None:
    _, _, gh, manifest, bundle_dir = _setup(tmp_path)
    up.publish_contribution(
        bundle_dir, publish=True, gh=gh, verifier=up._proof_verifier,
        manifest=manifest, out_root=tmp_path / "receipts",
    )
    gh.prs[0]["state"] = "MERGED"
    result = up.publish_contribution(
        bundle_dir, publish=True, gh=gh, verifier=up._proof_verifier,
        manifest=manifest, out_root=tmp_path / "receipts",
    )
    assert result["verdict"] == "upstream_already_merged"
    assert len(gh.prs) == 1


def test_diverged_patch_refuses_with_receipt(tmp_path) -> None:
    upstream, fork = up._proof_remotes(tmp_path / "div", up._PROOF_SOURCE_V2)
    gh = up._FakeGh(fork)
    bundle_dir = up._proof_write_bundle(
        tmp_path / "divbundle", patch=up._PROOF_PATCH,
        test_text=up._PROOF_TEST, repro_text=up._PROOF_REPRO,
    )
    result = up.publish_contribution(
        bundle_dir, publish=True, gh=gh, verifier=up._proof_verifier,
        manifest={"contribution": {"tests_subdir": "tests"}},
        out_root=tmp_path / "receipts",
    )
    assert result["verdict"] == "patch_diverged_at_head"
    assert not gh.prs
    assert up.verify_publication_receipt(Path(result["receipt_dir"]))["ok"]


def test_builtin_proof_passes() -> None:
    result = up.builtin_upstream_publication_proof()
    assert result["ok"], json.dumps(result, indent=2)
    assert not result["used_skill_route_discovery"]
