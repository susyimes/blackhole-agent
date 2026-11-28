"""Prepare the mission worktree's Python tools for validation and replay.

Repair targets its .venv. Replayed commands search that environment first and
can select a different import path or uv project explicitly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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


def validation_process_env(
    workspace: Path, overrides: dict[str, str] | None = None, *, for_sync: bool = False,
) -> dict[str, str]:
    """Activate the workspace toolchain in the child. Explicit command assignments win."""
    root = workspace.resolve()
    python = venv_python(root)
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    if for_sync or python.is_file() or (root / "pyproject.toml").is_file():
        for key in ("PYTHONPATH", "UV_PROJECT", "UV_WORKING_DIR", "UV_PROJECT_ENVIRONMENT"):
            env.pop(key, None)
        env["VIRTUAL_ENV"] = str(root / ".venv")
        if for_sync:
            # Use the controller's uv to bootstrap this target. Nested uv commands select their own project.
            env["UV_PROJECT_ENVIRONMENT"] = env["VIRTUAL_ENV"]
        else:
            env["PATH"] = os.pathsep.join((str(python.parent), env.get("PATH", os.defpath)))
    if overrides:
        env.update({key.upper() if os.name == "nt" else key: value for key, value in overrides.items()})
    return env


def _missing_modules(repo_path: Path, command_runner: CommandRunner) -> tuple[str, ...] | None:
    """Return None for an absent interpreter, otherwise its missing dev imports."""
    interpreter = venv_python(repo_path.resolve())
    if not interpreter.is_file():
        return None
    probe = (
        "import importlib.util, json; "
        f"print(json.dumps([m for m in {list(DEV_TOOL_MODULES)!r} "
        "if importlib.util.find_spec(m) is None]))"
    )
    try:
        completed = command_runner(
            [str(interpreter), "-I", "-c", probe], cwd=repo_path, capture_output=True, text=True, timeout=60,
        )
        if completed.returncode == 0:
            missing = json.loads(completed.stdout)
            if isinstance(missing, list) and all(name in DEV_TOOL_MODULES for name in missing):
                return tuple(missing)
    except Exception:
        pass
    return DEV_TOOL_MODULES


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
    missing = _missing_modules(repo_path, command_runner)
    venv_present = missing is not None
    missing = missing if missing is not None else DEV_TOOL_MODULES
    return {
        "ok": venv_present and not missing,
        "venv_present": venv_present,
        "venv_python": str(venv_python(repo_path)),
        "missing_tools": list(missing),
        "foreign_path_fallback": list(_foreign_fallbacks(repo_path, missing)) if missing else [],
        "sync_command": ["uv", "sync", "--extra", DEV_EXTRA],
    }


def ensure_validation_environment(
    repo_path: Path,
    *,
    command_runner: CommandRunner = subprocess.run,
    timeout: int = SYNC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Sync the dev extra into this workspace when its interpreter lacks required tools."""
    repo_path = Path(repo_path)
    before = validation_environment_report(repo_path, command_runner=command_runner)
    if before["ok"]:
        before["repaired"] = False
        return before
    try:
        completed = command_runner(
            before["sync_command"], cwd=repo_path, env=validation_process_env(repo_path, for_sync=True),
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as error:
        before["repaired"] = False
        before["sync_error"] = str(error)
        return before
    after = validation_environment_report(repo_path, command_runner=command_runner)
    after.update(
        repaired=after["ok"], sync_exit_code=completed.returncode,
        missing_before=before["missing_tools"], foreign_path_fallback_before=before["foreign_path_fallback"],
    )
    return after


def main(argv: list[str] | None = None) -> int:
    """CLI: repair (or inspect) a workspace validation environment."""

    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo_path", nargs="?", default=".")
    parser.add_argument("--check", action="store_true", help="inspect the environment without syncing")
    args = parser.parse_args(argv)
    action = validation_environment_report if args.check else ensure_validation_environment
    report = action(Path(args.repo_path))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
