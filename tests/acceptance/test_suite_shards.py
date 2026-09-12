"""Acceptance probe: sharded suite execution is bounded and resumable.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both
met and unmet outcomes so the controller can replay the same probe on
baseline and candidate source trees.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_PASSING_TEST = """def test_ok_{index}():
    assert {index} == {index}
"""

_FAILING_TEST = """def test_broken():
    assert False
"""


def _write_suite(tests_dir: Path, count: int) -> None:
    for index in range(count):
        (tests_dir / f"test_shard_{index}.py").write_text(_PASSING_TEST.format(index=index), encoding="utf-8")


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "suite-shards"}
    try:
        from blackhole_agent.suite_shards import run_suite_shards
    except Exception as error:  # baseline source tree has no sharded runner
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    with tempfile.TemporaryDirectory(prefix="suite-shards-probe-") as directory:
        repo = Path(directory)
        tests_dir = repo / "tests"
        tests_dir.mkdir()
        _write_suite(tests_dir, 4)
        ledger = repo / "ledger.json"

        first = run_suite_shards(repo, shard_count=2, shard_timeout=120, ledger_path=ledger)
        second = run_suite_shards(repo, shard_count=2, shard_timeout=120, ledger_path=ledger)

        # Touch one test file: exactly its shard must re-run, the other resumes.
        (tests_dir / "test_shard_0.py").write_text(_PASSING_TEST.format(index=0) + "\n", encoding="utf-8")
        third = run_suite_shards(repo, shard_count=2, shard_timeout=120, ledger_path=ledger)

        # A failing shard must fail the aggregate without blocking other shards.
        (tests_dir / "test_shard_1.py").write_text(_FAILING_TEST, encoding="utf-8")
        fourth = run_suite_shards(repo, shard_count=2, shard_timeout=120, ledger_path=ledger)
        ledger_persisted = ledger.is_file()

    checks = {
        "first_run_all_green": first.get("ok") is True and first.get("shards_passed") == 2,
        "second_run_fully_resumed": second.get("ok") is True and second.get("shards_resumed") == 2,
        "content_change_reruns_one_shard": third.get("shards_resumed") == 1 and third.get("ok") is True,
        "failing_shard_fails_aggregate": fourth.get("ok") is False and fourth.get("shards_failed") == 1,
        "failure_does_not_block_peers": fourth.get("shards_passed") == 1,
        "ledger_persisted": ledger_persisted,
    }
    observed.update(
        {
            "checks": checks,
            "first": {key: first.get(key) for key in ("ok", "shards_passed", "shards_resumed")},
            "second": {key: second.get(key) for key in ("ok", "shards_passed", "shards_resumed")},
            "third": {key: third.get(key) for key in ("ok", "shards_passed", "shards_resumed")},
            "fourth": {key: fourth.get(key) for key in ("ok", "shards_passed", "shards_failed")},
            "sentinel": "BH-SUITE-SHARDS-OK" if all(checks.values()) else "",
        }
    )
    return {"passed": bool(all(checks.values())), "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
    sys.exit(0)
