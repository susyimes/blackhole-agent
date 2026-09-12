"""Acceptance probe: mission workspaces self-heal hermetic validation tooling.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe
is fully self-contained: it generates a minimal project whose dev tooling
is declared as an optional extra — exactly how this repository declares
pytest/ruff/pyyaml — syncs it the way a fresh Unbound worktree is synced
(runtime deps only), observes that the project venv then lacks the dev
tools, invokes the runtime repair hook, and observes the tools importing
from the project venv itself.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both
met and unmet outcomes so the controller can replay the same probe on
baseline and candidate source trees.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

_PYPROJECT = """\
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "probe-mini"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest", "ruff", "pyyaml"]

[tool.setuptools]
py-modules = []
"""


def _run(command: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "validation-env-repair"}
    try:
        from blackhole_agent.validation_env import (
            ensure_validation_environment,
            validation_environment_report,
            venv_python,
        )
    except Exception as error:  # baseline source tree has no repair hook
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    with tempfile.TemporaryDirectory(prefix="validation-env-probe-") as directory:
        project = Path(directory) / "proj"
        project.mkdir()
        (project / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")

        # a fresh worktree syncs runtime deps only: dev tooling is absent
        fresh = _run(["uv", "sync"], project)
        before = validation_environment_report(project)
        interpreter = venv_python(project)
        drifted = _run(
            [str(interpreter), "-c", "import pytest"],
            project,
            timeout=60,
        )

        repaired = ensure_validation_environment(project)
        hermetic = _run(
            [
                str(interpreter),
                "-c",
                "import pathlib, pytest, ruff, yaml; "
                "print(pathlib.Path(pytest.__file__).resolve())",
            ],
            project,
            timeout=60,
        )
        tool_path = (hermetic.stdout or "").strip()
        in_venv = ".venv" in tool_path and str(project) in tool_path

    checks = {
        "fresh_sync_succeeds": fresh.returncode == 0,
        "fresh_venv_lacks_dev_tools": before.get("ok") is False
        and "pytest" in (before.get("missing_tools") or []),
        "fresh_venv_cannot_import_pytest": drifted.returncode != 0,
        "repair_reports_ok": repaired.get("ok") is True,
        "repair_was_needed": repaired.get("repaired") is True,
        "tools_import_from_project_venv": hermetic.returncode == 0 and in_venv,
    }
    observed.update(
        {
            "checks": checks,
            "before_missing": before.get("missing_tools"),
            "after_missing": repaired.get("missing_tools"),
            "tool_path": tool_path,
            "sentinel": "BH-VALIDATION-ENV-HERMETIC" if all(checks.values()) else "",
        }
    )
    return {"passed": bool(all(checks.values())), "observed": observed}


if __name__ == "__main__":
    try:
        outcome = main()
    except Exception as error:  # an unmet outcome must exit 0, not crash
        outcome = {
            "passed": False,
            "observed": {
                "family": "validation-env-repair",
                "error": type(error).__name__,
                "detail": str(error),
            },
        }
    print(json.dumps(outcome, sort_keys=True))
    sys.exit(0)
