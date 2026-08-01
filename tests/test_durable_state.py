"""Unit tests for the durable-state overlay.

The overlay is what keeps the tracked capability ledger and artifact trees
byte-stable while tests and sandbox flows exercise planes against the real
repository root.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    default_ledger_path,
    load_ledger,
)
from blackhole_agent.durable_state import (
    durable_forget,
    durable_read_path,
    durable_write_path,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "overlay"
    monkeypatch.setenv("BLACKHOLE_DURABLE_ROOT", str(root))
    return root


def test_write_redirect_preserves_relative_layout(overlay: Path) -> None:
    target = default_ledger_path(REPO_ROOT)
    redirected = durable_write_path(target)
    assert redirected == overlay / "capabilities" / "ledger.json"
    assert durable_write_path(target) != target


def test_paths_outside_worktree_are_untouched(overlay: Path, tmp_path: Path) -> None:
    outside = tmp_path / "plain" / "state.json"
    assert durable_write_path(outside) == outside
    assert durable_read_path(outside) == outside


def test_read_through_falls_back_to_committed_file(overlay: Path) -> None:
    target = default_ledger_path(REPO_ROOT)
    assert durable_read_path(target) == target


def test_write_then_read_observes_overlay_copy(overlay: Path) -> None:
    target = REPO_ROOT / "capabilities" / "overlay-probe.json"
    atomic_write_json(target, {"probe": 1})
    try:
        assert not target.exists()
        overlay_copy = overlay / "capabilities" / "overlay-probe.json"
        assert json.loads(overlay_copy.read_text(encoding="utf-8")) == {"probe": 1}
        assert durable_read_path(target) == overlay_copy
    finally:
        durable_forget(target)


def test_forget_tombstones_real_file_without_deleting_it(overlay: Path) -> None:
    target = default_ledger_path(REPO_ROOT)
    before = target.read_bytes()
    durable_forget(target)
    assert target.exists()  # committed file untouched
    assert not durable_read_path(target).exists()  # but readers see it as gone
    # Rewriting clears the tombstone and produces an overlay copy.
    atomic_write_json(target, {"schema_version": 1, "capabilities": {}})
    rewritten = overlay / "capabilities" / "ledger.json"
    assert durable_read_path(target) == rewritten
    assert target.read_bytes() == before


def test_overlay_disabled_is_inert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BLACKHOLE_DURABLE_ROOT", raising=False)
    target = default_ledger_path(REPO_ROOT)
    assert durable_write_path(target) == target
    assert durable_read_path(target) == target


def test_ledger_round_trip_stays_off_the_checkout(overlay: Path) -> None:
    from blackhole_agent.capability_compounder import CapabilityLedger, save_ledger

    target = REPO_ROOT / "capabilities" / "overlay-ledger-probe.json"
    ledger = CapabilityLedger()
    save_ledger(target, ledger)
    try:
        assert not target.exists()
        loaded = load_ledger(target)
        assert loaded.schema_version == ledger.schema_version
    finally:
        durable_forget(target)
