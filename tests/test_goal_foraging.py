"""Goal-driven foraging: unsolvable goals acquire what they need."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent.capability_foraging import FIXTURE_FORAGE_PACKAGE
from blackhole_agent.capability_service import InvocationError
from blackhole_agent.goal_foraging import solve_with_forage, uncovered_goal_keys


def _workspace(root: Path) -> Path:
    (root / "capabilities").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "test-workspace"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": {}}),
        encoding="utf-8",
    )
    return root


def _candidate() -> dict:
    return {
        "name": "forage-lab (uncooperative fixture package)",
        "slug": "forage-lab",
        "hint": "forage_lab",
        "source": str(FIXTURE_FORAGE_PACKAGE),
        "origin": {"kind": "fixture", "source": "tests/fixtures/external_packages/forage-lab"},
    }


def test_uncovered_goal_keys_closure() -> None:
    invocable = {
        "capability.a": {"requires": ["x"], "provides": ["y"]},
        "capability.b": {"requires": ["y"], "provides": ["z"]},
    }
    assert uncovered_goal_keys(invocable, {"x"}, ["z", "w"]) == ["w"]
    assert uncovered_goal_keys(invocable, {"x"}, ["z"]) == []
    assert uncovered_goal_keys(invocable, set(), ["z"]) == ["z"]


def test_unsolvable_without_candidates_is_honest(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "ws")
    verdict = solve_with_forage(root, {"text": "blackhole unbound"}, ["shout_output"], [])
    assert verdict["ok"] is True
    assert verdict["solved"] is False
    assert verdict["plan"] is None
    assert verdict["uncovered"] == ["shout_output"]
    assert verdict["acquisition"] == {
        "needed": True,
        "foraged": [],
        "acquired_capability_ids": [],
    }


def test_forage_candidate_closes_the_goal(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "ws")
    verdict = solve_with_forage(
        root, {"text": "blackhole unbound"}, ["shout_output"], [_candidate()]
    )
    assert verdict["ok"] is True, verdict
    assert verdict["solved"] is True
    assert verdict["plan"] == ["capability.absorbed-forage-lab"]
    assert verdict["outcome"] == {"shout_output": "BLACKHOLE UNBOUND!"}
    acquisition = verdict["acquisition"]
    assert acquisition["needed"] is True
    assert acquisition["acquired_capability_ids"] == ["capability.absorbed-forage-lab"]
    assert acquisition["foraged"][0]["ok"] is True

    # The acquisition is durable: the same goal now solves with no candidates.
    replay = solve_with_forage(root, {"text": "blackhole unbound"}, ["shout_output"], [])
    assert replay["solved"] is True
    assert replay["outcome"] == {"shout_output": "BLACKHOLE UNBOUND!"}
    assert replay["acquisition"]["needed"] is False


def test_failed_candidate_leaves_goal_unsolved(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "ws")
    bad = {"name": "missing-package", "slug": "missing-package", "source": str(tmp_path / "nope")}
    verdict = solve_with_forage(root, {"text": "x"}, ["shout_output"], [bad])
    assert verdict["ok"] is True
    assert verdict["solved"] is False
    assert verdict["reason"] == "no forage candidate closed the goal"
    assert verdict["uncovered"] == ["shout_output"]
    attempts = verdict["acquisition"]["foraged"]
    assert len(attempts) == 1
    assert attempts[0]["ok"] is False
    assert attempts[0]["stage"] == "fetch"


def test_malformed_requests_refused(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "ws")
    with pytest.raises(InvocationError):
        solve_with_forage(root, {"text": "x"}, [], [])
    with pytest.raises(InvocationError):
        solve_with_forage(root, "not-a-dict", ["k"], [])
    with pytest.raises(InvocationError):
        solve_with_forage(root, {"text": "x"}, ["k"], [{"source": "x"}])
    with pytest.raises(InvocationError):
        solve_with_forage(root, {"text": "x"}, ["k"], [{"name": "n"}])
    with pytest.raises(InvocationError):
        solve_with_forage(
            root, {"text": "x"}, ["k"], [{"name": f"n{i}", "source": "s"} for i in range(9)]
        )


def test_env_root_restored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from blackhole_agent.capability_absorption import REPO_ROOT_ENV

    monkeypatch.setenv(REPO_ROOT_ENV, "sentinel")
    root = _workspace(tmp_path / "ws")
    solve_with_forage(root, {"text": "x"}, ["shout_output"], [])
    assert os.environ[REPO_ROOT_ENV] == "sentinel"
