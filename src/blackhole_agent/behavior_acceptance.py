"""Run the same acceptance script against a historical checkout and working-tree bytes.

Each snapshot includes src and any files or directories declared by leading
``# replay-input: relative/path`` comments. The candidate reads tracked and
nonignored new files from the working tree. Each run gets private durable state.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from blackhole_agent.revision_checkout import RevisionCheckout

_PROBE_BOOTSTRAP = """\
import os
import runpy
import sys

source, script = map(os.path.abspath, sys.argv[1:])
# The isolated interpreter uses sys.path. Workers launched by the probe inherit PYTHONPATH.
os.environ["PYTHONPATH"] = source
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path[:0] = [source, os.path.dirname(script)]
sys.argv = [script]
sys.stdout.reconfigure(encoding="utf-8", errors="strict")
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
runpy.run_path(script, run_name="__main__")
"""


def outcome_probe_command(implementation: Path, script: Path) -> list[str]:
    """Select the source for the isolated probe and ordinary Python workers it launches."""
    return [sys.executable, "-I", "-B", "-X", "utf8", "-c", _PROBE_BOOTSTRAP, str(implementation), str(script)]


def execute_outcome_probe(
    implementation: Path | None,
    script: Path,
    *,
    timeout: float = 120,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Capture a probe's UTF-8 output. Standalone scripts can omit a source tree."""
    command = [sys.executable, str(script)] if implementation is None else outcome_probe_command(implementation, script)
    completed = subprocess.run(
        command,
        cwd=cwd or Path(script).parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def probe_verdict(stdout: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(stdout.rstrip().splitlines()[-1])
    except (IndexError, ValueError):
        return None
    if isinstance(payload, dict) and type(payload.get("passed")) is bool and payload.get("observed"):
        return payload
    return None


def _relative_input(name: str) -> str:
    if (
        "\\" in name or ":" in name or "\x00" in name
        or any(part.casefold() in {"", ".", "..", ".git"} for part in name.split("/"))
    ):
        raise ValueError(f"unsupported replay input path: {name!r}")
    return name


def _input_paths(source: bytes) -> list[str]:
    paths = ["src"]
    for raw in source.removeprefix(b"\xef\xbb\xbf").splitlines():
        line = raw.strip()
        if line.startswith(b"# replay-input:"):
            paths.append(_relative_input(line.partition(b":")[2].strip().decode("utf-8")))
        elif line and not line.startswith(b"#"):
            break
    return list(dict.fromkeys(paths))


def _shared_inputs(directory: Path) -> list[str]:
    manifest = directory / "replay-inputs.txt"
    if not manifest.exists():
        return []
    if manifest.resolve() != manifest:
        raise ValueError("unsupported link to replay-inputs.txt")
    lines = (line.strip() for line in manifest.read_text(encoding="utf-8").splitlines())
    return [_relative_input(line) for line in lines if line and not line.startswith("#")]


def historical_snapshot(root: Path, revision: str, paths: list[str], destination: Path) -> None:
    checkout = RevisionCheckout(root, revision, destination.parent)
    modes = checkout.modes(*paths)
    for name, mode in modes.items():
        path = destination / _relative_input(os.fsdecode(name))
        if mode not in {b"100644", b"100755"} or not path.resolve().is_relative_to(destination):
            raise ValueError(f"unsupported link/path in baseline: {os.fsdecode(name)}")
    checkout.write(destination, modes)


def read_probe(root: Path, probe_path: str | Path) -> tuple[bytes, list[str], list[str]]:
    probe = (root / probe_path).resolve()
    directory = root / "tests" / "acceptance"
    if not probe.is_relative_to(directory) or probe.suffix != ".py" or not probe.is_file():
        raise ValueError("acceptance_probe must name a Python file inside tests/acceptance")
    source = probe.read_bytes()
    return source, _input_paths(source), _shared_inputs(directory)


def _candidate_snapshot(root: Path, paths: list[str], destination: Path) -> None:
    entries = subprocess.check_output(
        ["git", "--literal-pathspecs", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *paths],
        cwd=root, stderr=subprocess.PIPE, timeout=60,
    )
    for raw in dict.fromkeys(entries.split(b"\0")[:-1]):
        name = _relative_input(os.fsdecode(raw))
        source = root / name
        if source.resolve() != source:
            raise ValueError(f"unsupported link/path in candidate: {name}")
        if not source.exists():
            continue  # An unstaged deletion is part of the candidate.
        if source.is_dir() and not (source / ".git").exists():
            continue  # A tracked file can be replaced by a directory of new files.
        if not source.is_file():
            raise ValueError(f"unsupported candidate file type: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def replay_behavior_acceptance(
    workspace: Path,
    baseline_ref: str,
    probe_path: str,
    *,
    timeout: int = 120,
) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "baseline_ref": baseline_ref, "probe": probe_path}
    try:
        root = workspace.resolve()
        if not baseline_ref or baseline_ref.startswith("-"):
            raise ValueError("a controller-owned baseline commit is required")
        source, required, shared = read_probe(root, probe_path)
        result["probe_sha256"] = hashlib.sha256(source).hexdigest()
        revision = subprocess.check_output(
            ["git", "rev-parse", "--verify", f"{baseline_ref}^{{commit}}"],
            cwd=root, stderr=subprocess.PIPE, timeout=30,
        ).decode("ascii").strip()
        paths = list(dict.fromkeys([*required, *shared]))
        result.update(baseline_commit=revision, required_inputs=required, shared_inputs=shared)
        with tempfile.TemporaryDirectory(prefix="blackhole-acceptance-") as directory:
            scratch = Path(directory).resolve()
            historical_snapshot(root, revision, paths, scratch / "baseline")
            _candidate_snapshot(root, paths, scratch / "candidate")
            labels = ("baseline", "candidate")
            for label in labels:
                for path in required:
                    if not (scratch / label / path).exists():
                        raise ValueError(f"{label} missing replay input: {path}")
            for label in labels:
                run_dir = scratch / f"run-{label}"
                run_dir.mkdir()
                script = run_dir / "outcome_probe.py"
                script.write_bytes(source)
                completed = execute_outcome_probe(
                    scratch / label / "src", script, timeout=timeout,
                    env={**os.environ, "BLACKHOLE_DURABLE_ROOT": str(run_dir / "durable")},
                )
                evidence: dict[str, Any] = {
                    "exit_code": completed["exit_code"],
                    "stdout_tail": completed["stdout"][-4000:],
                    "stderr_tail": completed["stderr"][-4000:],
                }
                result[label] = evidence
                if completed["exit_code"]:
                    raise ValueError(f"{label} probe crashed; this is not behavioral acceptance evidence")
                payload = probe_verdict(completed["stdout"])
                if payload is None:
                    raise ValueError(f"{label} probe needs boolean passed and nonempty observed")
                evidence["outcome"] = payload
            result["ok"] = (
                result["baseline"]["outcome"]["passed"] is False and result["candidate"]["outcome"]["passed"] is True
            )
            if not result["ok"]:
                result["error"] = "the same probe must show baseline passed=false and candidate passed=true"
    except subprocess.CalledProcessError as exc:
        result["error"] = (exc.stderr or b"").decode("utf-8", "replace").strip()[-2000:] or str(exc)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
    return result
