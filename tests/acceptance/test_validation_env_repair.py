"""Repair a runtime-only uv checkout, then import its real dev tools in isolation."""

import json
import os
import subprocess
import tempfile
from functools import partial
from pathlib import Path
from unittest.mock import patch


PROJECT = """\
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "probe-mini"
version = "0.1.0"
requires-python = ">=3.10"

[project.optional-dependencies]
dev = ["pytest", "ruff", "pyyaml"]

[tool.setuptools]
py-modules = []
"""


def observe(project):
    from blackhole_agent.validation_env import ensure_validation_environment, validation_environment_report, venv_python

    (project / "pyproject.toml").write_text(PROJECT, encoding="utf-8")
    venv = project / ".venv"
    # The initial uv sync belongs to this fixture, including when replay inherits an active project.
    with patch.dict(os.environ, UV_PROJECT=str(project), UV_WORKING_DIR=str(project), UV_PROJECT_ENVIRONMENT=str(venv)):
        run = partial(subprocess.run, cwd=project, capture_output=True, text=True, timeout=600)
        fresh = run(["uv", "sync"])
        python = [str(venv_python(project)), "-I", "-c"]
        before = validation_environment_report(project)
        drifted = run([*python, "import pytest"])
        repaired = ensure_validation_environment(project)
        imports = run([*python, "import pytest, ruff, yaml; print(pytest.__file__)"])
    tool_path = imports.stdout.strip()
    checks = {
        "fresh_sync_succeeds": fresh.returncode == 0,
        "fresh_venv_lacks_dev_tools": not before["ok"] and "pytest" in before["missing_tools"],
        "fresh_venv_cannot_import_pytest": drifted.returncode != 0,
        "repair_reports_ok": repaired["ok"],
        "repair_was_needed": repaired["repaired"],
        "tools_import_from_project_venv": imports.returncode == 0 and Path(tool_path).is_relative_to(venv),
    }
    passed = all(checks.values())
    observed = {
        "family": "validation-env-repair", "checks": checks, "tool_path": tool_path,
        "before_missing": before["missing_tools"], "after_missing": repaired["missing_tools"],
        "sentinel": "BH-VALIDATION-ENV-HERMETIC" if passed else "",
    }
    return {"passed": passed, "observed": observed}


def main():
    with tempfile.TemporaryDirectory(prefix="validation-env-probe-") as directory:
        try:
            return observe(Path(directory).resolve())
        except Exception as error:
            observed = {"family": "validation-env-repair", "error": type(error).__name__, "detail": str(error)}
            return {"passed": False, "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
