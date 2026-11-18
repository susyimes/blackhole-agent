"""Replay the same outcome probe against baseline and candidate implementations.

The probe is an executable Python file under tests/acceptance. It prints a
JSON object with boolean passed and nonempty observed, exiting zero even for
an unmet outcome. Crashes/import errors/timeouts are not a failing baseline.
This is regression evidence, not an assertion of third-party conformance.

Isolated children run in UTF-8 mode. A captured pipe would otherwise use the
ANSI code page, and Hangul on that pipe becomes UnicodeEncodeError.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
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
        archive = subprocess.run(
            ["git", "archive", "--format=tar", revision, "src"],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout
        with tempfile.TemporaryDirectory(prefix="blackhole-acceptance-") as directory:
            scratch = Path(directory)
            baseline = scratch / "baseline"
            baseline.mkdir()
            with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
                for member in bundle.getmembers():
                    destination = (baseline / member.name).resolve()
                    if not destination.is_relative_to(baseline) or not (member.isfile() or member.isdir()):
                        raise ValueError("unsupported link/path in baseline source archive")
                    if member.isdir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        stream = bundle.extractfile(member)
                        if stream is not None:
                            destination.write_bytes(stream.read())
            script = scratch / "outcome_probe.py"
            script.write_bytes(source)
            for label, implementation in (("baseline", baseline / "src"), ("candidate", root / "src")):
                run_dir = scratch / f"run-{label}"
                run_dir.mkdir()
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
    except (OSError, ValueError, IndexError, subprocess.SubprocessError, tarfile.TarError) as exc:
        result["error"] = str(exc)
    return result
