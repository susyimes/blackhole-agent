"""Bounded, resumable full-suite execution across session windows.

The full unit suite outlives a single session, so a plain ``pytest tests/``
run never finishes: progress is lost every time the session ends. This
runner shards the suite by test file into bounded batches, runs each shard
in a fresh subprocess with its own timeout, and records per-shard results
in a durable ledger after every shard. Re-invoking the runner skips shards
whose file set and contents are unchanged and already green, so a
full-suite pass can be assembled across any number of session restarts.

Acceptance probes under ``tests/acceptance`` are standalone scripts swept
by ``blackhole_agent.acceptance_sweep``; this runner covers the pytest unit
suite only.

CLI: ``python -m blackhole_agent.suite_shards [--repo PATH]
[--shards N] [--shard-timeout SECONDS] [--ledger PATH] [--no-resume]``
prints the aggregate report and exits 0 only when every shard is green
(freshly or via resume).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

DEFAULT_SHARD_COUNT = 8
DEFAULT_SHARD_TIMEOUT = 600
DEFAULT_LEDGER = Path("artifacts") / "suite-shards-ledger.json"


def list_test_files(repo_root: Path) -> list[Path]:
    """Return the top-level unit test files of the repository, sorted."""

    tests_dir = Path(repo_root) / "tests"
    if not tests_dir.is_dir():
        return []
    return sorted(path for path in tests_dir.glob("test_*.py") if path.is_file())


def shard_files(files: Sequence[Path], shard_count: int) -> list[list[Path]]:
    """Distribute files round-robin into at most shard_count deterministic shards."""

    count = max(1, min(int(shard_count), len(files) or 1))
    shards: list[list[Path]] = [[] for _ in range(count)]
    for index, path in enumerate(sorted(files)):
        shards[index % count].append(path)
    return [shard for shard in shards if shard]


def shard_digest(repo_root: Path, files: Sequence[Path]) -> str:
    """Content-address a shard so changed test files force a re-run."""

    root = Path(repo_root).resolve()
    digest = hashlib.sha1()
    for path in sorted(files):
        resolved = path.resolve()
        digest.update(str(resolved.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(resolved.read_bytes())
    return digest.hexdigest()


def _load_ledger(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"shards": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("shards"), dict):
        return {"shards": {}}
    return payload


def _save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(path.suffix + ".tmp")
    scratch.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(scratch, path)


def _run_shard(repo_root: Path, files: Sequence[Path], *, timeout: int, env: dict[str, str]) -> dict[str, Any]:
    record: dict[str, Any] = {"status": "", "exit_code": None, "duration_seconds": 0.0, "output_tail": ""}
    relpaths = [str(path.resolve().relative_to(Path(repo_root).resolve())) for path in files]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *relpaths],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        record["status"] = "timed_out"
        record["duration_seconds"] = round(time.monotonic() - started, 3)
        return record
    except OSError as error:
        record["status"] = "error"
        record["output_tail"] = f"{type(error).__name__}: {error}"
        record["duration_seconds"] = round(time.monotonic() - started, 3)
        return record
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    record["exit_code"] = completed.returncode
    record["status"] = "passed" if completed.returncode == 0 else "failed"
    record["output_tail"] = (completed.stdout + completed.stderr)[-400:]
    return record


def run_suite_shards(
    repo_root: Path,
    *,
    shard_count: int = DEFAULT_SHARD_COUNT,
    shard_timeout: int = DEFAULT_SHARD_TIMEOUT,
    ledger_path: Path | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    """Run the unit suite in bounded shards, resuming green shards from the ledger."""

    root = Path(repo_root).resolve()
    ledger_file = Path(ledger_path) if ledger_path else root / DEFAULT_LEDGER
    if not ledger_file.is_absolute():
        ledger_file = root / ledger_file
    ledger = _load_ledger(ledger_file)
    shards = shard_files(list_test_files(root), shard_count)
    env = dict(os.environ)
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="blackhole-suite-shards-") as overlay:
        env["BLACKHOLE_DURABLE_ROOT"] = overlay
        for index, files in enumerate(shards):
            key = shard_digest(root, files)
            entry: dict[str, Any] = {
                "index": index,
                "files": len(files),
                "digest": key,
                "resumed": False,
            }
            previous = ledger["shards"].get(key)
            if resume and isinstance(previous, dict) and previous.get("status") == "passed":
                entry.update(
                    {
                        "status": "passed",
                        "exit_code": previous.get("exit_code"),
                        "duration_seconds": previous.get("duration_seconds"),
                        "resumed": True,
                    }
                )
            else:
                entry.update(_run_shard(root, files, timeout=shard_timeout, env=env))
                ledger["shards"][key] = {
                    "status": entry["status"],
                    "exit_code": entry["exit_code"],
                    "duration_seconds": entry["duration_seconds"],
                }
                try:
                    _save_ledger(ledger_file, ledger)
                except OSError:
                    entry["ledger_error"] = "could not persist shard result"
            records.append(entry)
    report: dict[str, Any] = {
        "shards_total": len(records),
        "shards_passed": sum(1 for record in records if record["status"] == "passed"),
        "shards_failed": sum(1 for record in records if record["status"] in ("failed", "error")),
        "shards_timed_out": sum(1 for record in records if record["status"] == "timed_out"),
        "shards_resumed": sum(1 for record in records if record["resumed"]),
        "duration_seconds": round(sum(float(record.get("duration_seconds") or 0) for record in records), 3),
        "ledger_path": str(ledger_file),
        "shards": records,
    }
    report["ok"] = bool(records) and all(record["status"] == "passed" for record in records)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the unit suite in bounded, resumable shards.")
    parser.add_argument("--repo", default=".", help="repository root containing tests/")
    parser.add_argument("--shards", type=int, default=DEFAULT_SHARD_COUNT, help="number of shards")
    parser.add_argument("--shard-timeout", type=int, default=DEFAULT_SHARD_TIMEOUT, help="per-shard timeout in seconds")
    parser.add_argument("--ledger", default="", help="ledger path; defaults to artifacts/suite-shards-ledger.json")
    parser.add_argument("--no-resume", action="store_true", help="re-run shards even when the ledger is green")
    args = parser.parse_args(argv)
    report = run_suite_shards(
        Path(args.repo),
        shard_count=args.shards,
        shard_timeout=args.shard_timeout,
        ledger_path=Path(args.ledger) if args.ledger else None,
        resume=not args.no_resume,
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
