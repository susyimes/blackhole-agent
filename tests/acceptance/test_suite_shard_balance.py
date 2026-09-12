"""Acceptance probe: recorded slow-test profiles rebalance shard packing.

The 12-way sharded run bound each shard to 900s, and shard 2296c7cf
timed out because round-robin packing concentrated the slow test files
by position. The shard runner now harvests per-file duration profiles
into its ledger and packs shards longest-processing-time first, so a
skewed profile spreads heavy files under the bound.

This probe builds a synthetic suite whose round-robin packing doubles
the heaviest shard, seeds the runner ledger with the skewed profile, and
checks that packing spreads the heavy files and that the end-to-end run
records per-shard estimates. Prints JSON with boolean passed and
nonempty observed; exits 0 for both met and unmet outcomes so the
controller can replay the same probe on baseline and candidate trees.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_PASSING_TEST = """def test_ok_{index}():
    assert {index} == {index}
"""


def _load(shard: list[Path], weights: dict[str, float]) -> float:
    return sum(weights.get(path.name, 0.0) for path in shard)


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "suite-shards-balance"}
    try:
        from blackhole_agent.suite_shards import run_suite_shards, shard_files
    except Exception as error:  # baseline source tree predates the runner change
        observed["error"] = f"{type(error).__name__}: {error}"
        return {"passed": False, "observed": observed}

    with tempfile.TemporaryDirectory(prefix="suite-shard-balance-") as directory:
        repo = Path(directory)
        tests_dir = repo / "tests"
        tests_dir.mkdir()
        for index in range(8):
            (tests_dir / f"test_pack_{index}.py").write_text(
                _PASSING_TEST.format(index=index), encoding="utf-8"
            )
        files = sorted(tests_dir.glob("test_*.py"))
        # interleaved heavies: round-robin pairs two heavy files per shard
        weights = {
            f"test_pack_{index}.py": (300.0 if index % 2 == 0 else 1.0) for index in range(8)
        }
        try:
            round_robin = shard_files(files, 4)
            balanced = shard_files(files, 4, weights=weights)
        except TypeError as error:  # baseline shard_files has no weights parameter
            observed["error"] = f"shard_files lacks duration-aware packing: {error}"
            return {"passed": False, "observed": observed}

        rr_loads = [round(_load(shard, weights), 3) for shard in round_robin]
        balanced_loads = [round(_load(shard, weights), 3) for shard in balanced]
        heavy_spread = sum(
            1 for shard in balanced if any(weights.get(path.name, 0.0) > 100.0 for path in shard)
        )

        # end-to-end: a ledger seeded with the skewed profile (as recorded
        # from a timed-out shard) must drive the runner's packing
        ledger = repo / "ledger.json"
        ledger.write_text(
            json.dumps({"shards": {"seed": {"status": "timed_out", "file_durations": weights}}}),
            encoding="utf-8",
        )
        report = run_suite_shards(repo, shard_count=4, shard_timeout=120, ledger_path=ledger)
        estimates = [
            record.get("estimated_seconds")
            for record in report.get("shards", [])
            if isinstance(record, dict)
        ]

    checks = {
        "round_robin_concentrates_heavy_files": max(rr_loads) >= 2 * max(min(rr_loads), 1.0),
        "balanced_spreads_heavy_files": heavy_spread == 4,
        "balanced_within_bound": max(balanced_loads) <= 310.0,
        "packing_covers_same_files": {p.name for s in balanced for p in s}
        == {p.name for s in round_robin for p in s},
        "end_to_end_green": report.get("ok") is True,
        "report_marked_balanced": report.get("balanced") is True,
        "estimates_recorded": len(estimates) == 4
        and all(isinstance(value, (int, float)) for value in estimates)
        and max(estimates) <= 320.0,
    }
    observed.update(
        {
            "checks": checks,
            "round_robin_loads": rr_loads,
            "balanced_loads": balanced_loads,
            "estimated_seconds": estimates,
            "sentinel": "BH-SHARD-BALANCE-OK" if all(checks.values()) else "",
        }
    )
    return {"passed": bool(all(checks.values())), "observed": observed}


if __name__ == "__main__":
    try:
        result = main()
    except Exception as error:  # crashes never count; report unmet instead
        result = {"passed": False, "observed": {"error": f"{type(error).__name__}: {error}"}}
    print(json.dumps(result, sort_keys=True))
    sys.exit(0)
