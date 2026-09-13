"""Acceptance probe: sharded suite execution is bounded and resumable.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both
met and unmet outcomes so the controller can replay the same probe on
baseline and candidate source trees.

The mission condition is a bare ambient interpreter (mission workspaces
are uv venvs with runtime deps only). The replay host's own interpreter
may carry pytest, which would erase the before/after contrast, so the
probe builds its own bare venv (--without-pip, no site packages) and
points the runner's ambient interpreter at it: baseline source then has
no way to execute shards (passed=false) while candidate source must
obtain a pytest-capable interpreter on its own (passed=true).
"""

from __future__ import annotations

import json
import os
import subprocess
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


def _bare_interpreter(parent: Path) -> str:
    """Create a venv with no installed packages and return its interpreter."""

    venv_dir = parent / "bare-venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv_dir)],
        check=True,
        capture_output=True,
        timeout=180,
    )
    return str(venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))


def _lacks_pytest(interpreter: str) -> bool:
    completed = subprocess.run(
        [interpreter, "-c", "import pytest"],
        capture_output=True,
        timeout=60,
    )
    return completed.returncode != 0


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

        bare = _bare_interpreter(repo)
        fixture_bare = _lacks_pytest(bare)
        real_executable = sys.executable
        sys.executable = bare
        try:
            first = run_suite_shards(repo, shard_count=2, shard_timeout=120, ledger_path=ledger)
            second = run_suite_shards(repo, shard_count=2, shard_timeout=120, ledger_path=ledger)

            # Touch one test file: exactly its shard must re-run, the other resumes.
            (tests_dir / "test_shard_0.py").write_text(_PASSING_TEST.format(index=0) + "\n", encoding="utf-8")
            third = run_suite_shards(repo, shard_count=2, shard_timeout=120, ledger_path=ledger)

            # A failing shard must fail the aggregate without blocking other shards.
            (tests_dir / "test_shard_1.py").write_text(_FAILING_TEST, encoding="utf-8")
            fourth = run_suite_shards(repo, shard_count=2, shard_timeout=120, ledger_path=ledger)
        finally:
            sys.executable = real_executable
        ledger_persisted = ledger.is_file()

    checks = {
        "fixture_ambient_lacks_pytest": fixture_bare,
        "first_run_all_green": first.get("ok") is True and first.get("shards_passed") == 2,
        "second_run_fully_resumed": second.get("ok") is True and second.get("shards_resumed") == 2,
        "content_change_reruns_one_shard": third.get("shards_resumed") == 1 and third.get("ok") is True,
        "failing_shard_fails_aggregate": fourth.get("ok") is False and fourth.get("shards_failed") == 1,
        "failure_does_not_block_peers": fourth.get("shards_passed") == 1,
        "self_served_pytest_runner": first.get("pytest_runner") == "uv-ephemeral",
        "ledger_persisted": ledger_persisted,
    }
    observed.update(
        {
            "checks": checks,
            "first": {key: first.get(key) for key in ("ok", "shards_passed", "shards_resumed")},
            "second": {key: second.get(key) for key in ("ok", "shards_passed", "shards_resumed")},
            "third": {key: third.get(key) for key in ("ok", "shards_passed", "shards_resumed")},
            "fourth": {key: fourth.get(key) for key in ("ok", "shards_passed", "shards_failed")},
            "pytest_runner": first.get("pytest_runner"),
            "sentinel": "BH-SUITE-SHARDS-OK" if all(checks.values()) else "",
        }
    )
    return {"passed": bool(all(checks.values())), "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
    sys.exit(0)
