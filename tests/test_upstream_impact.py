"""Unit tests for the upstream impact plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent import upstream_impact as ui


def test_builtin_proof_green() -> None:
    result = ui.builtin_upstream_impact_proof()
    assert result["ok"]
    assert result["open_classified"]
    assert result["merged_classified"]
    assert result["closed_classified"]
    assert result["diverged_classified"]
    assert result["released_classified"]
    assert result["missing_classified"]
    assert result["certificate_verified"]
    assert result["tamper_detected"]
    assert result["unsealed_refused"]
    assert result["not_published_refused"]
    assert result["portfolio_assessed"]
    assert not result["used_skill_route_discovery"]


def test_classify_open_and_diverged() -> None:
    receipt = {
        "head_sha": "a" * 40,
        "pull_request": {"number": 1, "headRefOid": "a" * 40},
        "upstream_repo": "https://github.com/proof/x",
        "verdict": "published",
    }
    open_live = {
        "number": 1,
        "state": "OPEN",
        "headRefOid": "a" * 40,
        "mergedAt": None,
    }
    assert ui.classify_impact(receipt, open_live)["outcome"] == "impact_open"

    diverged_live = {
        "number": 1,
        "state": "OPEN",
        "headRefOid": "b" * 40,
        "mergedAt": None,
    }
    assert ui.classify_impact(receipt, diverged_live)["outcome"] == "impact_open_diverged"


def test_classify_merged_closed_missing_released() -> None:
    receipt = {
        "head_sha": "a" * 40,
        "pull_request": {"number": 2},
        "verdict": "published",
    }
    merged = ui.classify_impact(
        receipt,
        {"number": 2, "state": "MERGED", "headRefOid": "a" * 40, "mergedAt": "t"},
    )
    assert merged["outcome"] == "impact_merged"

    closed = ui.classify_impact(
        receipt,
        {"number": 2, "state": "CLOSED", "headRefOid": "a" * 40, "mergedAt": None},
    )
    assert closed["outcome"] == "impact_closed_unmerged"

    missing = ui.classify_impact(receipt, None)
    assert missing["outcome"] == "impact_pr_missing"

    released = ui.classify_impact(
        receipt,
        {"number": 2, "state": "OPEN", "headRefOid": "a" * 40},
        absorption={"released": True, "release_version": "9.9.9"},
    )
    assert released["outcome"] == "impact_released"


def test_unsealed_publication_refused(tmp_path: Path) -> None:
    receipt_dir = ui._proof_publication_receipt(tmp_path)
    (receipt_dir / "pr-body.md").write_bytes(b"tampered")
    with pytest.raises(ui.ImpactRefused) as excinfo:
        ui.assess_publication_impact(receipt_dir, gh=ui._FakeImpactGh())
    assert excinfo.value.verdict == "receipt_unsealed"


def test_not_published_refused(tmp_path: Path) -> None:
    receipt_dir = ui._proof_publication_receipt(
        tmp_path,
        verdict="dry_run_gates_passed",
        published=False,
    )
    with pytest.raises(ui.ImpactRefused) as excinfo:
        ui.assess_publication_impact(receipt_dir, gh=ui._FakeImpactGh())
    assert excinfo.value.verdict == "receipt_not_published"


def test_assess_seals_verifiable_certificate(tmp_path: Path) -> None:
    head = "e" * 40
    receipt_dir = ui._proof_publication_receipt(tmp_path, head_sha=head, pr_number=3)
    gh = ui._FakeImpactGh({
        ("proof/impactprobe", 3): {
            "number": 3,
            "url": "https://github.com/proof/impactprobe/pull/3",
            "state": "OPEN",
            "headRefOid": head,
            "mergedAt": None,
            "closedAt": None,
            "title": "t",
            "baseRefName": "main",
        }
    })
    result = ui.assess_publication_impact(
        receipt_dir, gh=gh, out_root=tmp_path / "impact"
    )
    assert result["ok"] and result["outcome"] == "impact_open"
    checked = ui.verify_impact_certificate(Path(result["certificate_dir"]))
    assert checked["ok"]
    cert = json.loads(
        (Path(result["certificate_dir"]) / "certificate.json").read_text(encoding="utf-8")
    )
    assert cert["pr_number"] == 3
    assert cert["impact_digest"] == result["impact_digest"]


def test_discover_prefers_newest_published(tmp_path: Path) -> None:
    root = tmp_path / "pubs"
    older = ui._proof_publication_receipt(
        root / "old",
        defect_id="d1",
        name="pkg",
        version="1.0.0",
    )
    # Rewrite created_at to be older.
    older_receipt = json.loads((older / "receipt.json").read_text(encoding="utf-8"))
    older_receipt["created_at"] = "2020-01-01T00:00:00Z"
    (older / "receipt.json").write_text(json.dumps(older_receipt, indent=2), encoding="utf-8")

    newer = ui._proof_publication_receipt(
        root / "new",
        defect_id="d1",
        name="pkg",
        version="1.0.0",
        pr_number=99,
    )
    newer_receipt = json.loads((newer / "receipt.json").read_text(encoding="utf-8"))
    newer_receipt["created_at"] = "2026-06-01T00:00:00Z"
    (newer / "receipt.json").write_text(json.dumps(newer_receipt, indent=2), encoding="utf-8")

    # Non-published must be ignored.
    ui._proof_publication_receipt(
        root / "dry",
        defect_id="d1",
        name="pkg",
        version="1.0.0",
        verdict="dry_run_gates_passed",
        published=False,
        pr_number=100,
    )

    found = ui.discover_published_receipts(root)
    assert len(found) == 1
    found_receipt = json.loads((found[0] / "receipt.json").read_text(encoding="utf-8"))
    assert found_receipt["pull_request"]["number"] == 99
