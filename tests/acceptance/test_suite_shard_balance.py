"""Retain timing profiles from older shard ledgers and rerun their unverified passes.

Shard 2296c7cf previously timed out at 900s when round-robin packing paired
the heaviest files. An eight-test workload makes both packing and execution observable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_PASSING_TEST = """from pathlib import Path

def test_ok_{index}():
    with Path('../executions').open('a') as trace:
        print({index}, file=trace)
    assert {index} == {index}
"""


def _bare_interpreter(parent: Path) -> str:
    venv_dir = parent / "bare-venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv_dir)], check=True, timeout=180)
    return str(venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))


def _load(shard: list[Path], weights: dict[str, float]) -> float:
    return sum(weights.get(path.name, 0.0) for path in shard)


def _exercise() -> dict[str, object]:
    from blackhole_agent.suite_shards import run_suite_shards, shard_digest, shard_files

    with tempfile.TemporaryDirectory(prefix="suite-shard-balance-") as directory:
        repo = Path(directory) / "suite"
        tests_dir = repo / "tests"
        tests_dir.mkdir(parents=True)
        for index in range(8):
            (tests_dir / f"test_pack_{index}.py").write_text(
                _PASSING_TEST.format(index=index), encoding="utf-8"
            )
        files = sorted(tests_dir.glob("test_*.py"))
        # interleaved heavies: round-robin pairs two heavy files per shard
        weights = {
            f"test_pack_{index}.py": (300.0 if index % 2 == 0 else 1.0) for index in range(8)
        }
        round_robin = shard_files(files, 4)
        balanced = shard_files(files, 4, weights=weights)

        rr_loads = [round(_load(shard, weights), 3) for shard in round_robin]
        balanced_loads = [round(_load(shard, weights), 3) for shard in balanced]
        heavy_spread = sum(
            1 for shard in balanced if any(weights.get(path.name, 0.0) > 100.0 for path in shard)
        )

        old_records = {shard_digest(repo, group): {"status": "passed", "exit_code": 0} for group in balanced}
        old_records["seed"] = {"status": "timed_out", "file_durations": weights}
        ledger = repo / "ledger.json"
        ledger.write_text(json.dumps({"shards": old_records}), encoding="utf-8")
        with patch.object(sys, "executable", _bare_interpreter(repo)):
            report = run_suite_shards(repo, shard_count=4, shard_timeout=120, ledger_path=ledger)
        estimates = [record.get("estimated_seconds") for record in report["shards"]]
        trace = repo.parent / "executions"
        executions = sorted(map(int, trace.read_text().splitlines())) if trace.exists() else []

    checks = {
        "round_robin_concentrates_heavy_files": max(rr_loads) >= 2 * max(min(rr_loads), 1.0),
        "balanced_spreads_heavy_files": heavy_spread == 4,
        "balanced_within_bound": max(balanced_loads) <= 310.0,
        "packing_covers_same_files": {p.name for s in balanced for p in s}
        == {p.name for s in round_robin for p in s},
        "end_to_end_green": report.get("ok") is True,
        "legacy_passes_reexecuted": executions == list(range(8)) and report["shards_resumed"] == 0,
        "self_served_pytest_runner": report.get("pytest_runner") == "uv-ephemeral",
        "report_marked_balanced": report.get("balanced") is True,
        "estimates_recorded": len(estimates) == 4
        and all(isinstance(value, (int, float)) for value in estimates)
        and max(estimates) <= 320.0,
    }
    passed = all(checks.values())
    observed = {"family": "suite-shards-balance", "checks": checks, "round_robin_loads": rr_loads,
                "balanced_loads": balanced_loads, "estimated_seconds": estimates, "executions": executions,
                "pytest_runner": report["pytest_runner"], "sentinel": "BH-SHARD-BALANCE-OK" if passed else ""}
    return {"passed": passed, "observed": observed}


def main() -> dict[str, object]:
    try:
        return _exercise()
    except Exception as error:
        return {"passed": False, "observed": {"error": f"{type(error).__name__}: {error}"}}


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
