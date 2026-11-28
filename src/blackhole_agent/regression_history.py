"""Locate a persistent pass-to-fail transition on the first-parent release line."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from blackhole_agent.acceptance_sweep import run_probe
from blackhole_agent.behavior_acceptance import historical_snapshot, read_probe

MAX_HISTORY_SAMPLES = 24


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=repo, stderr=subprocess.PIPE, timeout=30)


def checkout_state(repo: Path, output: Path) -> tuple[str, bool]:
    """Read HEAD and cleanliness together. Hygiene's own output cannot dirty a release."""
    if not (repo / ".git").exists():
        return "", False
    paths = ["."]
    repo, output = repo.resolve(), output.resolve()
    if output.is_relative_to(repo):
        paths.append(":(top,exclude,literal)" + output.relative_to(repo).as_posix())
    try:
        rows = _git(repo, "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=normal", "--", *paths)
    except (OSError, subprocess.SubprocessError):
        return "", False
    entries = rows.split(b"\0")
    prefix = b"# branch.oid "
    oid = next((row.removeprefix(prefix) for row in entries if row.startswith(prefix)), b"")
    if not oid or oid == b"(initial)":
        return "", False
    return oid.decode("ascii"), all(not row or row.startswith(b"# ") for row in entries)


def bisect_regression(
    repo: Path, probe: str | Path, good: str, bad: str, *, timeout: int = 120, deadline: float | None = None,
) -> dict[str, Any]:
    """Bisect a persistent regression. Failed probe execution leaves the revision undecided."""
    repo = repo.resolve()
    samples: dict[str, dict[str, Any]] = {}
    result: dict[str, Any] = {"samples": samples, "first_bad": None}
    if deadline is not None and time.monotonic() >= deadline:
        return {**result, "status": "budget_exhausted"}
    try:
        source, required, shared = read_probe(repo, probe)
        result["probe_sha256"] = hashlib.sha256(source).hexdigest()
        good, bad = (
            _git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()
            for ref in (good, bad)
        )
        result.update(good_commit=good, bad_commit=bad)
        history = _git(repo, "rev-list", "--first-parent", "--reverse", "--parents", f"{good}..{bad}").splitlines()
        if good != bad and (not history or history[0].split()[1:2] != [good.encode()]):
            return {**result, "status": "not_first_parent"}
        commits = [good, *(row.split()[0].decode() for row in history)]
        paths = list(dict.fromkeys([*required, *shared]))

        def observe(index: int) -> bool | None:
            revision = commits[index]
            if revision in samples:
                return samples[revision].get("passed")
            try:
                with tempfile.TemporaryDirectory(prefix="blackhole-release-") as directory:
                    scratch = Path(directory).resolve()
                    tree = scratch / "release"
                    historical_snapshot(repo, revision, paths, tree)
                    for name in required:
                        if not (tree / name).exists():
                            raise ValueError(f"missing replay input: {name}")
                    script = tree / "tests" / "acceptance" / Path(probe).name
                    script.parent.mkdir(parents=True, exist_ok=True)
                    script.write_bytes(source)
                    budget = timeout if deadline is None else min(timeout, max(0, deadline - time.monotonic()))
                    env = {**os.environ, "BLACKHOLE_DURABLE_ROOT": str(scratch / "durable")}
                    row = run_probe(script, timeout=budget, env=env)
                    if row["error"]:
                        raise ValueError(f"{row['error']} {row.get('stderr_tail', '')}".strip())
                    samples[revision] = {"passed": row["passed"], "observed": row["observed"]}
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                samples[revision] = {"error": str(exc)}
            return samples[revision].get("passed")

        lo, hi = 0, len(commits) - 1
        for endpoint, index, expected in (("bad", hi, False), ("good", lo, True)):
            if deadline is not None and time.monotonic() >= deadline:
                return {**result, "status": "budget_exhausted"}
            passed = observe(index)
            if passed is not expected:
                reason = {None: "untestable", True: "passed", False: "failed"}[passed]
                return {**result, "status": f"{endpoint}_endpoint_{reason}"}
        remaining = list(range(lo + 1, hi))
        while remaining and len(samples) < MAX_HISTORY_SAMPLES and (deadline is None or time.monotonic() < deadline):
            middle = len(remaining) // 2
            index = remaining.pop(middle)
            passed = observe(index)
            if passed is True:
                lo, remaining = index, remaining[middle:]
            elif passed is False:
                hi, remaining = index, remaining[:middle]
        result.update(last_good=commits[lo], candidates=commits[lo + 1:hi + 1])
        if hi == lo + 1:
            return {**result, "status": "located", "first_bad": commits[hi]}
        return {**result, "status": "budget_exhausted" if remaining else "ambiguous"}
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        return {**result, "status": "unavailable", "error": str(exc)}
