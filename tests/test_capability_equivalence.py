"""Tests for the capability equivalence gate."""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path

import pytest

from blackhole_agent.capability_equivalence import (
    _strip_volatile,
    _surface_entry,
    builtin_equivalence_proof,
    capture_snapshot,
    load_snapshot,
    snapshot_digest,
    validate_probe,
    verify_snapshot,
    write_snapshot,
)


def _module_fixture(tmp_path: Path, answer: int = 42) -> None:
    # Different-length rewrites defeat same-second mtime+size pyc caching.
    (tmp_path / "gate_fixture_mod.py").write_text(
        f"ANSWER = {answer}\n\n\ndef greet(name: str) -> str:\n    return f'hello {{name}}'\n",
        encoding="utf-8",
    )


def _probes(tmp_path: Path) -> list[dict[str, object]]:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"level": 1}), encoding="utf-8")
    return [
        {"kind": "api-surface", "id": "surface", "modules": ["gate_fixture_mod"]},
        {
            "kind": "command",
            "id": "state",
            "argv": [
                sys.executable,
                "-c",
                "import json, sys; print(json.dumps(json.load(open(sys.argv[1]))))",
                str(state_path),
            ],
        },
    ]


@pytest.fixture()
def scratch(tmp_path: Path):
    _module_fixture(tmp_path)
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    yield tmp_path
    sys.path.remove(str(tmp_path))
    sys.modules.pop("gate_fixture_mod", None)


def test_validate_probe_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="unsupported probe kind"):
        validate_probe({"kind": "nope", "id": "x"})
    with pytest.raises(ValueError, match="probe id is required"):
        validate_probe({"kind": "command", "argv": ["true"]})
    with pytest.raises(ValueError, match="argv"):
        validate_probe({"kind": "command", "id": "x", "argv": []})
    with pytest.raises(ValueError, match="module"):
        validate_probe({"kind": "api-surface", "id": "x", "modules": "json"})
    with pytest.raises(ValueError, match="path"):
        validate_probe({"kind": "pytest", "id": "x", "paths": []})


def test_strip_volatile_drops_timestamps_and_durations() -> None:
    payload = {
        "ok": True,
        "run_at": "2026-01-01",
        "duration_seconds": 3,
        "nested": [{"timestamp_ms": 5, "keep": 1}],
        "elapsed_total": 9,
    }
    assert _strip_volatile(payload) == {"ok": True, "nested": [{"keep": 1}]}


def test_capture_verify_roundtrip(scratch: Path) -> None:
    snapshot = capture_snapshot("roundtrip", _probes(scratch), cwd=scratch)
    assert snapshot["snapshot_digest"] == snapshot_digest(snapshot)
    verdict = verify_snapshot(snapshot, cwd=scratch)
    assert verdict["ok"], verdict
    assert verdict["digest_match"] and verdict["probe_count"] == 2


def test_snapshot_digest_ignores_captured_at(scratch: Path) -> None:
    snapshot = capture_snapshot("volatile-time", _probes(scratch), cwd=scratch)
    shifted = dict(snapshot, captured_at="1970-01-01T00:00:00Z")
    assert snapshot_digest(shifted) == snapshot["snapshot_digest"]


def test_tampered_snapshot_fails_digest(scratch: Path) -> None:
    snapshot = capture_snapshot("tamper", _probes(scratch), cwd=scratch)
    forged = copy.deepcopy(snapshot)
    forged["results"]["state"]["exit_code"] = 3
    verdict = verify_snapshot(forged, cwd=scratch)
    assert not verdict["ok"]
    assert verdict["digest_match"] is False


def test_command_drift_detected(scratch: Path) -> None:
    snapshot = capture_snapshot("drift", _probes(scratch), cwd=scratch)
    (scratch / "state.json").write_text(json.dumps({"level": 2}), encoding="utf-8")
    verdict = verify_snapshot(snapshot, cwd=scratch)
    assert not verdict["ok"]
    assert verdict["digest_match"]
    assert verdict["drifted_probes"] == ["state"]


def test_surface_drift_detected(scratch: Path) -> None:
    snapshot = capture_snapshot("surface-drift", _probes(scratch), cwd=scratch)
    _module_fixture(scratch, answer=43000)
    importlib.invalidate_caches()
    sys.modules.pop("gate_fixture_mod", None)
    verdict = verify_snapshot(snapshot, cwd=scratch)
    assert not verdict["ok"]
    assert "surface" in verdict["drifted_probes"]


def test_volatile_command_output_is_normalized(scratch: Path) -> None:
    probes = [
        {
            "kind": "command",
            "id": "volatile",
            "argv": [
                sys.executable,
                "-c",
                "import json, time; print(json.dumps({'ok': True, 'run_at': time.time()}))",
            ],
        }
    ]
    snapshot = capture_snapshot("volatile", probes, cwd=scratch)
    verdict = verify_snapshot(snapshot, cwd=scratch)
    assert verdict["ok"], verdict


def test_pytest_probe_counts(scratch: Path) -> None:
    test_file = scratch / "test_gate_fixture.py"
    test_file.write_text(
        "def test_a():\n    assert True\n\n\ndef test_b():\n    assert True\n",
        encoding="utf-8",
    )
    probes = [{"kind": "pytest", "id": "tests", "paths": [str(test_file)]}]
    snapshot = capture_snapshot("pytest-probe", probes, cwd=scratch)
    result = snapshot["results"]["tests"]
    assert result == {"exit_code": 0, "tests": 2, "failures": 0, "errors": 0, "skipped": 0}
    assert verify_snapshot(snapshot, cwd=scratch)["ok"]
    test_file.write_text("def test_a():\n    assert False\n", encoding="utf-8")
    verdict = verify_snapshot(snapshot, cwd=scratch)
    assert not verdict["ok"] and verdict["drifted_probes"] == ["tests"]


def test_write_and_load_snapshot(scratch: Path, tmp_path: Path) -> None:
    snapshot = capture_snapshot("persisted", _probes(scratch), cwd=scratch)
    path = write_snapshot(snapshot, tmp_path / "out")
    loaded = load_snapshot(path)
    assert loaded["snapshot_digest"] == snapshot["snapshot_digest"]
    assert verify_snapshot(loaded, cwd=scratch)["ok"]


def test_capture_requires_unique_probe_ids(scratch: Path) -> None:
    probes = _probes(scratch)
    probes.append(dict(probes[0]))
    with pytest.raises(ValueError, match="unique"):
        capture_snapshot("dupes", probes, cwd=scratch)


def test_verify_rejects_wrong_kind() -> None:
    verdict = verify_snapshot({"schema_version": 1, "kind": "other"}, cwd=Path("."))
    assert not verdict["ok"]


def test_surface_signatures_strip_memory_addresses() -> None:
    import dataclasses

    entry = _surface_entry("field", dataclasses.field)
    assert "0x" not in entry[2] or "0x…" in entry[2]
    assert " at 0x…>" in entry[2]


def test_builtin_equivalence_proof() -> None:
    result = builtin_equivalence_proof()
    assert result["ok"], result
    assert all(result["checks"].values())
    assert not result["used_skill_route_discovery"]
