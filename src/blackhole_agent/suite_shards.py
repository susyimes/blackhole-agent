"""Run bounded pytest shards and resume passes against the same working inputs.

Shared inputs cover tracked and nonignored files in Git, or project files in a
standalone suite. Each shard also owns its top-level test files. Interpreter
caches and this runner's ledger are outputs. Use --no-resume when tests depend
on external state. See ``python -m blackhole_agent.suite_shards --help``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.file_guard import atomic_write_json, file_guard
from blackhole_agent.suite_inputs import file_digest, inputs_digest, suite_inputs

DEFAULT_SHARD_COUNT = 8
DEFAULT_SHARD_TIMEOUT = 600
DEFAULT_LEDGER = Path("artifacts") / "suite-shards-ledger.json"
PYTEST_PREFLIGHT_TIMEOUT = 60


def list_test_files(repo_root: Path) -> list[Path]:
    return sorted(p for p in (Path(repo_root) / "tests").glob("test_*.py") if p.is_file())


def shard_files(
    files: Sequence[Path],
    shard_count: int,
    weights: Mapping[str, float] | None = None,
) -> list[list[Path]]:
    """Deal round-robin initially, then pack longest-running files first."""
    count = min(max(1, int(shard_count)), len(files))
    if not weights:
        ordered = sorted(files)
        return [ordered[i::count] for i in range(count)]
    shards: list[list[Path]] = [[] for _ in range(count)]
    loads = [0.0] * count
    ordered = sorted(files, key=lambda path: (-float(weights.get(path.name, 0.0)), str(path)))
    for path in ordered:
        index = min(range(count), key=lambda i: (loads[i], len(shards[i]), i))
        shards[index].append(path)
        loads[index] += float(weights.get(path.name, 0.0))
    return [shard for shard in shards if shard]


def shard_digest(repo_root: Path, files: Sequence[Path], *, contents: Mapping[Path, bytes] | None = None) -> str:
    root = Path(repo_root).resolve()
    entries = []
    for path in files:
        name = os.fsencode(path.absolute().relative_to(root).as_posix())
        entries.append((name, contents[path] if contents is not None else file_digest(path)))
    return inputs_digest(entries)


_DURATION_LINE = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s+(?:call|setup|teardown)\s+(\S+?)\s*$")


def parse_test_durations(output: str) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Sum per-file seconds and keep the ten slowest tests."""
    per_file: dict[str, float] = {}
    per_test: dict[str, float] = {}
    for line in output.splitlines():
        match = _DURATION_LINE.match(line)
        if not match:
            continue
        seconds = float(match.group(1))
        nodeid = match.group(2)
        per_test[nodeid] = per_test.get(nodeid, 0.0) + seconds
        name = nodeid.split("::")[0].replace("\\", "/").rsplit("/", 1)[-1]
        per_file[name] = per_file.get(name, 0.0) + seconds
    slowest = sorted(per_test.items(), key=lambda item: (-item[1], item[0]))[:10]
    return (
        {name: round(value, 3) for name, value in sorted(per_file.items())},
        [{"test": nodeid, "seconds": round(value, 3)} for nodeid, value in slowest],
    )


def ledger_file_weights(ledger: Mapping[str, Any], *, bucket_seconds: float = 10.0) -> dict[str, float]:
    """Bucket the slowest recorded time per file, including partial runs."""
    weights: dict[str, float] = {}
    shards = ledger.get("shards") if isinstance(ledger, Mapping) else None
    if not isinstance(shards, Mapping):
        return weights
    for record in shards.values():
        durations = record.get("file_durations") if isinstance(record, Mapping) else None
        if not isinstance(durations, Mapping):
            continue
        for name, seconds in durations.items():
            try:
                value = float(seconds)
            except (TypeError, ValueError):
                continue
            weights[str(name)] = max(weights.get(str(name), 0.0), value)
    if bucket_seconds <= 0:
        return weights
    return {name: math.ceil(value / bucket_seconds) * bucket_seconds for name, value in weights.items()}


def _load_ledger(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("shards"), dict):
            return payload
    except (OSError, ValueError):
        pass
    return {"shards": {}}


def _save_shard(path: Path, key: str, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_guard(path):
        ledger = _load_ledger(path)
        ledger["shards"][key] = record
        atomic_write_json(path, ledger)


def _locked_pytest_spec() -> str:
    try:
        text = (Path(__file__).resolve().parents[2] / "uv.lock").read_text(encoding="utf-8", errors="replace")
    except (OSError, IndexError):
        return "pytest"
    match = re.search(r'(?ms)^\[\[package\]\]\s*^name = "pytest"\s*^version = "([^"]+)"', text)
    return f"pytest=={match.group(1)}" if match else "pytest"


def resolve_pytest_command() -> tuple[list[str], str]:
    """Prefer ambient pytest, falling back to uv for a bare mission venv."""

    ambient = [sys.executable, "-m", "pytest"]
    try:
        check = subprocess.run(
            [sys.executable, "-c", "import pytest"], capture_output=True, timeout=PYTEST_PREFLIGHT_TIMEOUT,
        )
        if check.returncode == 0:
            return ambient, "ambient"
    except (OSError, subprocess.SubprocessError):
        pass
    uv = shutil.which("uv")
    if uv is None:
        return ambient, "ambient-missing-pytest"
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    launcher = [uv, "run", "--python", version, "--with", _locked_pytest_spec(), "--no-project"]
    return [*launcher, "--", "python", "-m", "pytest"], "uv-ephemeral"


def _run_shard(
    repo_root: Path,
    files: Sequence[Path],
    *,
    timeout: int,
    env: dict[str, str],
    pytest_command: Sequence[str],
) -> dict[str, Any]:
    relpaths = [str(path.relative_to(repo_root)) for path in files]
    started = time.monotonic()
    code = None
    try:
        completed = subprocess.run(
            [*pytest_command, "-q", "--durations=0", *relpaths],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        code = completed.returncode
        status = "passed" if code == 0 else "failed"
        output = completed.stdout + completed.stderr
    except subprocess.TimeoutExpired as error:
        status = "timed_out"
        output = error.output or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
    except OSError as error:
        status = "error"
        output = f"{type(error).__name__}: {error}"
    file_durations, slowest_tests = parse_test_durations(output)
    return {
        "status": status, "exit_code": code, "duration_seconds": round(time.monotonic() - started, 3),
        "file_durations": file_durations, "slowest_tests": slowest_tests, "output_tail": output[-400:],
    }


def run_suite_shards(
    repo_root: Path,
    *,
    shard_count: int = DEFAULT_SHARD_COUNT,
    shard_timeout: int = DEFAULT_SHARD_TIMEOUT,
    ledger_path: Path | None = None,
    resume: bool = True,
    balance: bool = True,
) -> dict[str, Any]:
    """Save each verified shard before starting the next one."""
    root = Path(repo_root).resolve()
    ledger_file = (root / (ledger_path or DEFAULT_LEDGER)).resolve()
    ledger = _load_ledger(ledger_file)
    weights = ledger_file_weights(ledger) if balance else {}
    pytest_command, pytest_runner = resolve_pytest_command()
    env = dict(os.environ)
    if (root / "src").is_dir():
        env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(root / "src"), env.get("PYTHONPATH"))))
    errors = []

    def snapshot():
        try:
            return suite_inputs(root, ledger_file)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(str(exc))
            return None

    initial = snapshot()
    files = sorted(initial[1]) if initial is not None else list_test_files(root)
    shards = shard_files(files, shard_count, weights=weights)
    settings = {k: v for k, v in env.items() if k.startswith("PYTEST_") or k == "PYTHONPATH"}
    identity = [initial[0] if initial else None, str(root), sys.platform, sys.version,
                pytest_runner, pytest_command, settings]
    context = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="blackhole-suite-shards-") as overlay:
        env["BLACKHOLE_DURABLE_ROOT"] = overlay
        # Equal-length edits inside a bytecode timestamp tick must reach the interpreter.
        env["PYTHONPYCACHEPREFIX"] = str(Path(overlay) / "pycache")
        for index, group in enumerate(shards):
            key = shard_digest(root, group, contents=initial[1]) if initial else ""
            entry: dict[str, Any] = {
                "index": index, "files": len(group), "digest": key, "resumed": False, "pytest_runner": pytest_runner,
            }
            records.append(entry)
            if weights:
                entry["estimated_seconds"] = round(sum(weights.get(path.name, 0.0) for path in group), 3)
            previous = ledger["shards"].get(key)
            result = None
            if (
                resume and initial is not None and isinstance(previous, dict) and previous.get("context") == context
                and previous.get("status") == "passed" and previous.get("exit_code") == 0
            ):
                entry.update(status="passed", exit_code=0, resumed=True)
                entry["duration_seconds"] = previous.get("duration_seconds")
                if index + 1 < len(shards):
                    continue
            else:
                result = _run_shard(root, group, timeout=shard_timeout, env=env, pytest_command=pytest_command)
                entry.update(result)
            if initial is None:
                continue
            if snapshot() != initial:
                entry["status"] = "inputs_changed"
                errors.append("checkout inputs changed during the suite run")
                break
            if result is not None:
                saved = dict(result, context=context)
                del saved["output_tail"]
                try:
                    _save_shard(ledger_file, key, saved)
                except OSError:
                    entry["ledger_error"] = "could not persist shard result"
    report: dict[str, Any] = {
        "shards_total": len(shards),
        "shards_passed": sum(1 for record in records if record["status"] == "passed"),
        "shards_failed": sum(1 for record in records if record["status"] in ("failed", "error", "inputs_changed")),
        "shards_timed_out": sum(1 for record in records if record["status"] == "timed_out"),
        "shards_resumed": sum(1 for record in records if record["resumed"]),
        "balanced": bool(weights),
        "pytest_runner": pytest_runner,
        "duration_seconds": round(sum(float(record.get("duration_seconds") or 0) for record in records), 3),
        "ledger_path": str(ledger_file),
        "shards": records,
    }
    if errors:
        report["input_errors"] = errors
    report["ok"] = bool(records) and all(record["status"] == "passed" for record in records)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the unit suite in bounded, resumable shards.")
    parser.add_argument("--repo", default=".", help="repository root containing tests/")
    parser.add_argument("--shards", type=int, default=DEFAULT_SHARD_COUNT, help="number of shards")
    parser.add_argument("--shard-timeout", type=int, default=DEFAULT_SHARD_TIMEOUT, help="per-shard timeout in seconds")
    parser.add_argument("--ledger", default="", help="ledger path; defaults to artifacts/suite-shards-ledger.json")
    parser.add_argument("--no-resume", action="store_true", help="re-run shards even when the ledger is green")
    parser.add_argument("--no-balance", action="store_true", help="pack round-robin and ignore duration profiles")
    args = parser.parse_args(argv)
    report = run_suite_shards(
        Path(args.repo),
        shard_count=args.shards,
        shard_timeout=args.shard_timeout,
        ledger_path=Path(args.ledger) if args.ledger else None,
        resume=not args.no_resume,
        balance=not args.no_balance,
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
