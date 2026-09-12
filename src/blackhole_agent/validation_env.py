"""Hermetic validation environments for Unbound mission workspaces.

A fresh mission worktree starts with no ``.venv``. The first ``uv run``
syncs only the project's runtime dependencies: the dev tooling declared
under ``[project.optional-dependencies].dev`` (pytest, ruff, pyyaml) is an
optional extra and is never installed by default. From that point every
bare ``uv run pytest`` or ``uv run ruff`` inside the workspace silently
falls back to whatever executable happens to be on ``PATH`` — on this
fleet that is a foreign agent venv whose interpreter lacks the project's
own dependencies, so the suite fails collection with misleading
``ModuleNotFoundError`` noise and milestone validation evidence is
computed by the wrong toolchain.

This module makes the workspace self-healing instead:

- :func:`validation_environment_report` inspects the workspace venv and
  reports which dev tools are importable there and whether a foreign
  ``PATH`` fallback would be picked up for the missing ones;
- :func:`ensure_validation_environment` repairs a drifted or missing
  environment by running ``uv sync --extra dev`` inside the workspace and
  re-checking, so a subsequent bare ``uv run pytest`` resolves to the
  project venv's locked toolchain.

The Unbound runtime calls the repair hook after worktree creation and
before replaying agent-reported validation commands, so both new and
long-lived workspaces stay hermetic.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

DEV_EXTRA = "dev"
# importable module names provided by the dev extra (pyyaml imports as yaml)
DEV_TOOL_MODULES: tuple[str, ...] = ("pytest", "ruff", "yaml")
DEV_TOOL_EXECUTABLES: tuple[str, ...] = ("pytest", "ruff")
SYNC_TIMEOUT_SECONDS = 600
CommandRunner = Callable[..., Any]


def venv_python(repo_path: Path) -> Path:
    """Return the project venv interpreter path for this platform."""

    if os.name == "nt":
        return Path(repo_path) / ".venv" / "Scripts" / "python.exe"
    return Path(repo_path) / ".venv" / "bin" / "python"


def _missing_modules(
    repo_path: Path,
    *,
    command_runner: CommandRunner,
) -> tuple[str, ...] | None:
    """Return dev tool modules not importable in the project venv.

    Returns ``None`` when the venv interpreter itself is absent.
    """

    interpreter = venv_python(repo_path)
    if not interpreter.exists():
        return None
    probe = (
        "import importlib.util, json; "
        f"print(json.dumps([m for m in {list(DEV_TOOL_MODULES)!r} "
        "if importlib.util.find_spec(m) is None]))"
    )
    try:
        completed = command_runner(
            [str(interpreter), "-c", probe],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return tuple(DEV_TOOL_MODULES)
    if completed.returncode != 0:
        return tuple(DEV_TOOL_MODULES)
    try:
        missing = json.loads(completed.stdout.strip() or "[]")
    except ValueError:
        return tuple(DEV_TOOL_MODULES)
    return tuple(str(item) for item in missing)


def _foreign_fallbacks(repo_path: Path, missing: tuple[str, ...]) -> tuple[str, ...]:
    """Return missing tools that a bare ``uv run`` would resolve on PATH."""

    venv_root = (Path(repo_path) / ".venv").resolve()
    fallbacks: list[str] = []
    for name in DEV_TOOL_EXECUTABLES:
        if name not in missing:
            continue
        resolved = shutil.which(name)
        if not resolved:
            continue
        try:
            if venv_root not in Path(resolved).resolve().parents:
                fallbacks.append(name)
        except OSError:
            fallbacks.append(name)
    return tuple(fallbacks)


def validation_environment_report(
    repo_path: Path,
    *,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    """Inspect the workspace venv for hermetic dev tooling."""

    repo_path = Path(repo_path)
    missing = _missing_modules(repo_path, command_runner=command_runner)
    venv_present = missing is not None
    missing = missing if missing is not None else tuple(DEV_TOOL_MODULES)
    foreign = _foreign_fallbacks(repo_path, missing) if missing else ()
    return {
        "ok": venv_present and not missing,
        "venv_present": venv_present,
        "venv_python": str(venv_python(repo_path)),
        "missing_tools": list(missing),
        "foreign_path_fallback": list(foreign),
        "sync_command": ["uv", "sync", "--extra", DEV_EXTRA],
    }


def ensure_validation_environment(
    repo_path: Path,
    *,
    command_runner: CommandRunner = subprocess.run,
    timeout: int = SYNC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Repair the workspace venv so dev tooling resolves hermetically.

    Idempotent: a healthy environment is left untouched. A missing or
    drifted environment is repaired with one ``uv sync --extra dev`` and
    re-inspected; the report records before/after state so callers can
    surface the repair in mission evidence.
    """

    repo_path = Path(repo_path)
    before = validation_environment_report(repo_path, command_runner=command_runner)
    if before["ok"]:
        before["repaired"] = False
        return before
    try:
        completed = command_runner(
            list(before["sync_command"]),
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        sync_exit = completed.returncode
    except Exception as error:
        before["repaired"] = False
        before["sync_error"] = str(error)
        return before
    after = validation_environment_report(repo_path, command_runner=command_runner)
    after.update(
        {
            "repaired": after["ok"],
            "sync_exit_code": sync_exit,
            "missing_before": before["missing_tools"],
            "foreign_path_fallback_before": before["foreign_path_fallback"],
        }
    )
    return after


def main(argv: list[str] | None = None) -> int:
    """CLI: repair (or inspect) a workspace validation environment."""

    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo_path", nargs="?", default=".")
    parser.add_argument(
        "--check",
        action="store_true",
        help="inspect only; do not run the repair sync",
    )
    args = parser.parse_args(argv)
    if args.check:
        report = validation_environment_report(Path(args.repo_path))
    else:
        report = ensure_validation_environment(Path(args.repo_path))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
