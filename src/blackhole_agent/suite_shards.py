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
from functools import cached_property
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence

from blackhole_agent.file_guard import atomic_write_json, file_guard
from blackhole_agent.process_capture import ProcessCancelled, run_captured_process
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
    """Read pytest terminal durations when a parallel worker owns the reporting."""
    per_test: dict[str, float] = {}
    for line in output.splitlines():
        match = _DURATION_LINE.match(line)
        if not match:
            continue
        seconds = float(match.group(1))
        nodeid = match.group(2)
        per_test[nodeid] = per_test.get(nodeid, 0.0) + seconds
    return _duration_profile(per_test)


def _duration_profile(per_test: dict[str, float]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    per_file: dict[str, float] = {}
    for nodeid, seconds in per_test.items():
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


class _CaseWatch:
    """Read flushed phase transitions outside pytest, including when its interpreter is stuck."""

    def __init__(self, directory: Path, stream: BinaryIO, seconds: float | None):
        self.directory = directory
        self.stream = stream
        self.seconds = seconds
        self.entered: set[int] = set()
        self.timeouts: list[dict[str, str]] = []
        self.failures: list[dict[str, str]] = []
        self.durations: dict[str, float] = {}
        self.active: tuple[int, str] | None = None
        self.started = 0.0
        self.worker_expired = False

    @cached_property
    def collection(self) -> dict[str, Any]:
        # Pytest flushes the selection before reporting the first case.
        return json.loads((self.directory / "collection.json").read_bytes())

    def describe(self, index: int, phase: str) -> dict[str, str]:
        return {"nodeid": self.collection["nodeids"][index], "phase": phase}

    def refresh(self) -> None:
        while True:
            offset = self.stream.tell()
            line = self.stream.readline()
            if not line.endswith(b"\n"):
                self.stream.seek(offset)
                return
            index, event, value = json.loads(line)
            if event == "expired":
                self.worker_expired = True
                continue
            if event == "result":
                phase, outcome, duration = value
                nodeid = self.collection["nodeids"][index]
                self.durations[nodeid] = self.durations.get(nodeid, 0.0) + duration
                if outcome == "failed":
                    self.failures.append(self.describe(index, phase))
                continue
            if event == "setup":
                self.entered.add(index)
                self.started = value
            self.active = None if event == "finished" else (index, event)

    def is_set(self) -> bool:
        self.refresh()
        return self.active is not None and self.seconds is not None and time.monotonic() - self.started >= self.seconds

    def after_case_timeout(self) -> bool:
        """Save the interrupted case and select only unentered items for another worker."""
        assert self.active is not None
        self.timeouts.append(self.describe(*self.active))
        self.refresh()  # The tree is now stopped. Account for any last transitions.
        self.stream.truncate(self.stream.tell())  # Discard an unterminated final record before another writer appends.
        self.active = None
        self.worker_expired = False
        failures = len(self.timeouts) + len(self.failures)
        if self.collection["maxfail"] and failures >= self.collection["maxfail"]:
            return False
        if len(self.entered) == len(self.collection["nodeids"]):
            return False
        (self.directory / "recovery.json").write_text(
            json.dumps({"entered": sorted(self.entered), "failures": failures}), encoding="ascii",
        )
        return True


def _run_shard(
    repo_root: Path,
    files: Sequence[Path],
    *,
    timeout: int,
    env: dict[str, str],
    pytest_command: Sequence[str],
    case_timeout: float | None,
    directory: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    directory.mkdir()
    shutil.copyfile(Path(__file__).with_name("_pytest_cases.py"), directory / "_blackhole_pytest_cases.py")
    command = [*pytest_command, "-q", "--durations=0", "-p", "_blackhole_pytest_cases",
               *(str(path.relative_to(repo_root)) for path in files)]
    env = dict(env, PYTHONPATH=os.pathsep.join(filter(None, (str(directory), env.get("PYTHONPATH")))),
               _BLACKHOLE_CASE_DEADLINE=str(case_timeout) if case_timeout is not None else "")
    shard_expiry = None
    code, status, output = None, "timed_out", ""
    with (directory / "events").open("w+b") as events:
        watch = _CaseWatch(directory, events, case_timeout)
        while (remaining := started + timeout - time.monotonic()) > 0:
            try:
                completed = run_captured_process(command, cwd=repo_root, env=env, timeout=remaining,
                                                 cancel_event=watch if case_timeout is not None else None)
                output = completed.stdout + completed.stderr
                watch.refresh()
                if not watch.worker_expired:
                    if not watch.timeouts:
                        code = completed.returncode
                        status = "passed" if code == 0 else "failed"
                    elif completed.returncode not in (0, 1):
                        code, status = completed.returncode, "error"
                    break
            except ProcessCancelled:
                pass  # The same recovery handles a live hang and a worker that stopped at a phase boundary.
            except subprocess.TimeoutExpired as error:
                output = (error.output or "") + (error.stderr or "")
                watch.refresh()
                if watch.active is not None:
                    shard_expiry = watch.describe(*watch.active)
                break
            except (OSError, RuntimeError) as error:
                status, output = "error", f"{type(error).__name__}: {error}"
                break
            if not watch.after_case_timeout():
                break
        watch.refresh()
    if watch.entered:
        file_durations, slowest_tests = _duration_profile(watch.durations)
    else:
        file_durations, slowest_tests = parse_test_durations(output)
    return {
        "status": status, "exit_code": code, "duration_seconds": round(time.monotonic() - started, 3),
        "timed_out_cases": watch.timeouts, "failed_cases": watch.failures, "active_at_shard_timeout": shard_expiry,
        "file_durations": file_durations, "slowest_tests": slowest_tests, "output_tail": output[-400:],
    }


def run_suite_shards(
    repo_root: Path,
    *,
    shard_count: int = DEFAULT_SHARD_COUNT,
    shard_timeout: int = DEFAULT_SHARD_TIMEOUT,
    case_timeout: float | None = None,
    ledger_path: Path | None = None,
    resume: bool = True,
    balance: bool = True,
) -> dict[str, Any]:
    """Save each verified shard before starting the next one."""
    if case_timeout is not None and (not math.isfinite(case_timeout) or case_timeout <= 0):
        raise ValueError("case_timeout must be positive and finite")
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
    if case_timeout is not None:
        identity.append(case_timeout)
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
                result = _run_shard(root, group, timeout=shard_timeout, env=env, pytest_command=pytest_command,
                                    case_timeout=case_timeout, directory=Path(overlay) / f"shard-{index}")
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
    parser.add_argument("--case-timeout", type=float, default=os.environ.get("BLACKHOLE_PYTEST_CASE_TIMEOUT"),
                        help="stop a stalled serial pytest case and run remaining cases within the shard deadline")
    parser.add_argument("--ledger", default="", help="ledger path; defaults to artifacts/suite-shards-ledger.json")
    parser.add_argument("--no-resume", action="store_true", help="re-run shards even when the ledger is green")
    parser.add_argument("--no-balance", action="store_true", help="pack round-robin and ignore duration profiles")
    args = parser.parse_args(argv)
    if args.case_timeout is not None and (not math.isfinite(args.case_timeout) or args.case_timeout <= 0):
        parser.error("--case-timeout must be positive and finite")
    report = run_suite_shards(
        Path(args.repo),
        shard_count=args.shards,
        shard_timeout=args.shard_timeout,
        case_timeout=args.case_timeout,
        ledger_path=Path(args.ledger) if args.ledger else None,
        resume=not args.no_resume,
        balance=not args.no_balance,
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
