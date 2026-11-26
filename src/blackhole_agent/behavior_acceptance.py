"""Replay the same outcome probe against baseline and candidate implementations.

The probe is an executable Python file under tests/acceptance. It prints a
JSON object with boolean passed and nonempty observed, exiting zero even for
an unmet outcome. Each run gets its own copy of src. Leading comments of the
form "# replay-input: relative/path" also include required files or directories.
The baseline reads committed blobs. The candidate reads the working bytes of
tracked and nonignored new files under the same paths.

Isolated children run in UTF-8 mode. A captured pipe would otherwise use the
ANSI code page, and Hangul on that pipe becomes UnicodeEncodeError.
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

# ``-I`` ignores PYTHONUTF8. ``-X utf8`` is a command flag, so it still applies.
# The bootstrap reconfigures the pipe again before the probe prints.
_UTF8_PROBE_BOOTSTRAP = (
    "import sys,runpy;"
    "sys.stdout.reconfigure(encoding='utf-8',errors='strict');"
    "sys.stderr.reconfigure(encoding='utf-8',errors='backslashreplace');"
    "sys.path.insert(0,sys.argv[1]);"
    "runpy.run_path(sys.argv[2],run_name='__main__')"
)


def outcome_probe_command(implementation: Path, script: Path) -> list[str]:
    """Return the isolated argv used to run one acceptance probe."""

    return [
        sys.executable,
        "-I",
        "-X",
        "utf8",
        "-c",
        _UTF8_PROBE_BOOTSTRAP,
        str(implementation),
        str(script),
    ]


def execute_outcome_probe(
    implementation: Path,
    script: Path,
    *,
    timeout: int = 120,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one probe and decode its pipe as UTF-8.

    ``stdout`` contains the characters the probe printed, including Hangul
    that a GBK pipe would have refused to encode.
    """

    completed = subprocess.run(
        outcome_probe_command(implementation, script),
        cwd=cwd or Path(script).parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return {
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


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
            name = _relative_input(line.partition(b":")[2].strip().decode("utf-8"))
            if name not in paths:
                paths.append(name)
        elif line and not line.startswith(b"#"):
            break
    return paths


def _shared_inputs(directory: Path) -> list[str]:
    manifest = directory / "replay-inputs.txt"
    if not manifest.exists():
        return []
    if manifest.resolve() != manifest:
        raise ValueError("unsupported link to replay-inputs.txt")
    lines = (line.strip() for line in manifest.read_text(encoding="utf-8").splitlines())
    return [_relative_input(line) for line in lines if line and not line.startswith("#")]


def _git_files(root: Path, *args: str) -> list[bytes]:
    output = subprocess.check_output(
        ["git", "--literal-pathspecs", *args], cwd=root, stderr=subprocess.PIPE, timeout=60,
    )
    return output.rstrip(b"\0").split(b"\0") if output else []


def _baseline_snapshot(root: Path, revision: str, paths: list[str], destination: Path) -> None:
    # Read blobs directly. git archive would silently omit export-ignore files.
    files = []
    for entry in _git_files(root, "ls-tree", "-rz", "--full-tree", revision, "--", *paths):
        info, name = entry.split(b"\t", 1)
        mode, kind, oid = info.split()
        path = destination / _relative_input(os.fsdecode(name))
        if kind != b"blob" or mode not in {b"100644", b"100755"} or not path.resolve().is_relative_to(destination):
            raise ValueError(f"unsupported link/path in baseline: {os.fsdecode(name)}")
        files.append((path, oid, mode))
    with tempfile.TemporaryFile() as blobs:
        subprocess.run(
            ["git", "cat-file", "--batch"], cwd=root, input=b"".join(oid + b"\n" for _, oid, _ in files),
            stdout=blobs, stderr=subprocess.PIPE, check=True, timeout=60,
        )
        blobs.seek(0)
        for path, oid, mode in files:
            actual_oid, kind, size = blobs.readline().split()
            if actual_oid != oid or kind != b"blob":
                raise ValueError(f"missing baseline blob {oid!r}")
            path.parent.mkdir(parents=True, exist_ok=True)
            remaining = int(size)
            with path.open("xb") as target:
                while remaining:
                    chunk = blobs.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        raise ValueError(f"incomplete baseline blob {oid!r}")
                    target.write(chunk)
                    remaining -= len(chunk)
            if blobs.read(1) != b"\n":
                raise ValueError(f"incomplete baseline blob {oid!r}")
            if mode == b"100755":
                path.chmod(0o755)


def _candidate_snapshot(root: Path, paths: list[str], destination: Path) -> None:
    entries = _git_files(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *paths)
    for raw in dict.fromkeys(entries):
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
        probe = (root / probe_path).resolve()
        accepted_root = root / "tests" / "acceptance"
        if not probe.is_relative_to(accepted_root) or probe.suffix != ".py" or not probe.is_file():
            raise ValueError("acceptance_probe must name a Python file inside tests/acceptance")
        if not baseline_ref or baseline_ref.startswith("-"):
            raise ValueError("a controller-owned baseline commit is required")
        source = probe.read_bytes()
        result["probe_sha256"] = hashlib.sha256(source).hexdigest()
        revision = subprocess.run(
            ["git", "rev-parse", "--verify", f"{baseline_ref}^{{commit}}"],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=30,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
        required = _input_paths(source)
        shared = _shared_inputs(accepted_root)
        paths = list(dict.fromkeys([*required, *shared]))
        result.update(baseline_commit=revision, required_inputs=required, shared_inputs=shared)
        with tempfile.TemporaryDirectory(prefix="blackhole-acceptance-") as directory:
            scratch = Path(directory).resolve()
            baseline = scratch / "baseline"
            candidate = scratch / "candidate"
            _baseline_snapshot(root, revision, paths, baseline)
            _candidate_snapshot(root, paths, candidate)
            for label, snapshot in (("baseline", baseline), ("candidate", candidate)):
                for path in required:
                    if not (snapshot / path).exists():
                        raise ValueError(f"{label} missing replay input: {path}")
            for label, implementation in (("baseline", baseline / "src"), ("candidate", candidate / "src")):
                run_dir = scratch / f"run-{label}"
                run_dir.mkdir()
                script = run_dir / "outcome_probe.py"
                script.write_bytes(source)
                env = dict(os.environ)
                env["BLACKHOLE_DURABLE_ROOT"] = str(run_dir / "durable")
                completed = execute_outcome_probe(
                    implementation,
                    script,
                    timeout=timeout,
                    cwd=run_dir,
                    env=env,
                )
                evidence: dict[str, Any] = {
                    "exit_code": completed["exit_code"],
                    "stdout_tail": completed["stdout"][-4000:],
                    "stderr_tail": completed["stderr"][-4000:],
                }
                result[label] = evidence
                if completed["exit_code"]:
                    raise ValueError(f"{label} probe crashed; this is not behavioral acceptance evidence")
                payload = json.loads(completed["stdout"].strip().splitlines()[-1])
                if (
                    not isinstance(payload, dict)
                    or type(payload.get("passed")) is not bool
                    or not payload.get("observed")
                ):
                    raise ValueError(f"{label} probe needs boolean passed and nonempty observed")
                evidence["outcome"] = payload
            result["ok"] = (
                result["baseline"]["outcome"]["passed"] is False and result["candidate"]["outcome"]["passed"] is True
            )
            if not result["ok"]:
                result["error"] = "the same probe must show baseline passed=false and candidate passed=true"
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
    return result
