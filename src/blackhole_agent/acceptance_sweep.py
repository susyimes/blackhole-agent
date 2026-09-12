"""Execute every standalone acceptance probe and aggregate the verdicts.

Probes under ``tests/acceptance`` are scripts, not pytest tests: each
prints a JSON object with boolean ``passed`` and nonempty ``observed`` and
exits 0 for both met and unmet outcomes so the controller can replay the
same file against baseline and candidate source trees. Several legacy
probes call ``sys.exit`` at module scope, which aborts pytest collection,
so they are excluded from pytest and swept here instead, each in a fresh
subprocess with a durable-state overlay that keeps the worktree clean.

CLI: ``python -m blackhole_agent.acceptance_sweep [--repo PATH]
[--timeout SECONDS] [--probe NAME ...]`` prints the aggregate report and
exits 0 only when every selected probe ran to completion with a parseable
verdict (met and unmet outcomes both count; crashes and timeouts do not).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

DEFAULT_PROBE_TIMEOUT = 300


def iter_acceptance_probes(repo_root: Path) -> list[Path]:
    """Return the standalone probe scripts of the repository, sorted."""

    acceptance_dir = Path(repo_root) / "tests" / "acceptance"
    if not acceptance_dir.is_dir():
        return []
    return sorted(acceptance_dir.glob("test_*.py"))


def _parse_verdict(stdout: str) -> dict[str, Any] | None:
    lines = [line for line in stdout.strip().splitlines() if line.strip()]
    if not lines:
        return None
    try:
        payload = json.loads(lines[-1])
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    if type(payload.get("passed")) is not bool or not payload.get("observed"):
        return None
    return payload


def run_probe(probe: Path, *, timeout: int = DEFAULT_PROBE_TIMEOUT, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Run one probe in a fresh subprocess and adjudicate its verdict."""

    record: dict[str, Any] = {
        "path": str(probe),
        "exit_code": None,
        "timed_out": False,
        "passed": None,
        "observed": None,
        "error": "",
        "duration_seconds": 0.0,
    }
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, str(probe)],
            cwd=str(probe.parent.parent.parent) if probe.parent.name == "acceptance" else None,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        record["timed_out"] = True
        record["error"] = f"probe exceeded {timeout}s"
        record["duration_seconds"] = round(time.monotonic() - started, 3)
        return record
    except OSError as error:
        record["error"] = f"{type(error).__name__}: {error}"
        record["duration_seconds"] = round(time.monotonic() - started, 3)
        return record
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    record["exit_code"] = completed.returncode
    verdict = _parse_verdict(completed.stdout)
    if verdict is None:
        record["error"] = "probe did not print a JSON verdict with boolean passed and nonempty observed"
        record["stderr_tail"] = completed.stderr[-400:]
        return record
    record["passed"] = verdict["passed"]
    record["observed"] = verdict["observed"]
    if completed.returncode != 0:
        record["error"] = f"probe exited {completed.returncode}; the contract requires exit 0 for met and unmet outcomes"
    return record


def sweep_acceptance_probes(
    repo_root: Path,
    *,
    timeout: int = DEFAULT_PROBE_TIMEOUT,
    only: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run every selected probe and return an aggregate machine-readable report."""

    probes = iter_acceptance_probes(Path(repo_root))
    if only:
        wanted = {Path(name).stem for name in only}
        probes = [probe for probe in probes if probe.stem in wanted]
    env = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="blackhole-acceptance-sweep-") as overlay:
        env["BLACKHOLE_DURABLE_ROOT"] = overlay
        records = [run_probe(probe, timeout=timeout, env=env) for probe in probes]
    report: dict[str, Any] = {
        "total": len(records),
        "executed": sum(1 for record in records if record["exit_code"] is not None),
        "met": sum(1 for record in records if record["passed"] is True),
        "unmet": sum(1 for record in records if record["passed"] is False),
        "crashed": sum(1 for record in records if record["exit_code"] not in (0, None)),
        "timed_out": sum(1 for record in records if record["timed_out"]),
        "invalid": sum(1 for record in records if record["passed"] is None and not record["timed_out"]),
        "probes": records,
    }
    report["ok"] = bool(records) and all(
        record["exit_code"] == 0 and record["passed"] is not None for record in records
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep standalone acceptance probes and aggregate verdicts.")
    parser.add_argument("--repo", default=".", help="repository root containing tests/acceptance")
    parser.add_argument("--timeout", type=int, default=DEFAULT_PROBE_TIMEOUT, help="per-probe timeout in seconds")
    parser.add_argument("--probe", action="append", default=[], help="restrict to named probe(s); repeatable")
    args = parser.parse_args(argv)
    report = sweep_acceptance_probes(Path(args.repo), timeout=args.timeout, only=args.probe or None)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
