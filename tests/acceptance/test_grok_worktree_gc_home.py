"""Grok's own worktree GC must see a home directory on Windows.

Harvested kernel stderr records ``auto worktree gc failed`` because neither
``$GROK_HOME`` nor ``$HOME`` is set. The controller environment has
``USERPROFILE`` and Grok does not read that variable, so session worktrees
are never collected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


def _restore(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _launch(cwd: Path, output_dir: Path, **overrides: str | None) -> dict | None:
    from blackhole_agent.kernels.grok_cli import GrokCliKernel
    import blackhole_agent.kernels.grok_cli as grok_cli

    grok_cli.shutil.which = lambda _name: "C:/tools/grok.exe"
    seen: dict[str, dict | None] = {}

    def runner(command, **kwargs):
        seen["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"text": "ok", "stopReason": "EndTurn"}),
            stderr="",
        )

    saved = {key: os.environ.get(key) for key in ("HOME", "GROK_HOME", "USERPROFILE")}
    try:
        for key in saved:
            os.environ.pop(key, None)
        for key, value in overrides.items():
            if value is not None:
                os.environ[key] = value
        GrokCliKernel(command_runner=runner).run(
            "Collect session worktrees.",
            cwd=cwd,
            output_dir=output_dir,
            timeout_seconds=30,
        )
    finally:
        _restore(saved)
    env = seen.get("env")
    return env if isinstance(env, dict) else None


def _home_of(env: dict | None) -> str:
    if not isinstance(env, dict):
        return ""
    for key, value in env.items():
        if str(key).casefold() == "home":
            return str(value or "").strip()
    return ""


def _named(env: dict | None, name: str) -> str:
    if not isinstance(env, dict):
        return ""
    for key, value in env.items():
        if str(key).casefold() == name.casefold():
            return str(value or "").strip()
    return ""


def observe() -> tuple[bool, dict]:
    with tempfile.TemporaryDirectory(prefix="grok-home-") as temporary:
        root = Path(temporary)
        profile = root / "profile"
        preset = root / "preset-home"
        grok_home = root / "grok-home"
        missing = root / "missing-profile"
        profile.mkdir()
        preset.mkdir()
        grok_home.mkdir()
        filled = _launch(root, root / "filled", USERPROFILE=str(profile))
        preserved = _launch(
            root,
            root / "preserved",
            USERPROFILE=str(profile),
            HOME=str(preset),
        )
        explicit = _launch(
            root,
            root / "explicit",
            USERPROFILE=str(profile),
            GROK_HOME=str(grok_home),
        )
        absent = _launch(root, root / "absent", USERPROFILE=str(missing))

    filled_home = _home_of(filled)
    preserved_home = _home_of(preserved)
    explicit_home = _home_of(explicit)
    explicit_grok_home = _named(explicit, "GROK_HOME")
    absent_home = _home_of(absent)
    copied_process_env = isinstance(filled, dict) and len(filled) > 3
    profile_home_filled = filled_home == str(profile) and not _named(filled, "GROK_HOME")
    explicit_home_preserved = preserved_home == str(preset)
    grok_home_preserved = explicit_grok_home == str(grok_home) and explicit_home == ""
    missing_profile_not_used = absent_home == ""
    passed = (
        copied_process_env
        and profile_home_filled
        and explicit_home_preserved
        and grok_home_preserved
        and missing_profile_not_used
    )
    observed = {
        "harvested_failure": "auto worktree gc failed error=neither $GROK_HOME nor $HOME is set",
        "profile_home_filled": profile_home_filled,
        "filled_home_is_profile": filled_home == str(profile),
        "process_env_copied": copied_process_env,
        "explicit_home_preserved": explicit_home_preserved,
        "grok_home_preserved": grok_home_preserved,
        "missing_profile_not_used": missing_profile_not_used,
    }
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as error:  # noqa: BLE001 - unmet outcome must still print JSON
        passed = False
        observed = {"error": type(error).__name__, "detail": str(error)}
    print(json.dumps({"passed": bool(passed), "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
