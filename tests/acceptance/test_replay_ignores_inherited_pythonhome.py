"""Validation replay must not inherit a foreign PYTHONHOME.

Harvested 2026-11-16: a ``python -c`` command that imports the standard
library was reported with exit 0, and controller replay exited 1. The tick
exports PYTHONHOME for another CPython, so the child dies in encodings
before the asserts. An empty directory is enough to cause that death.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def observe() -> tuple[bool, dict]:
    from blackhole_agent.unbound import replay_validation_command

    python = str(Path(sys.executable).resolve())
    command = f"\"{python}\" -c \"import socket; print('socket-ok')\""
    with tempfile.TemporaryDirectory(prefix="bh-pythonhome-") as directory:
        root = Path(directory)
        poison = root / "empty-prefix"
        poison.mkdir()
        saved = os.environ.get("PYTHONHOME")
        os.environ["PYTHONHOME"] = str(poison)
        try:
            result = replay_validation_command(root, command, timeout=30)
        finally:
            if saved is None:
                os.environ.pop("PYTHONHOME", None)
            else:
                os.environ["PYTHONHOME"] = saved
    stdout = str(result.get("stdout_tail") or "")
    observed = {
        "command": command,
        "exit": result.get("reproduced_exit_code"),
        "ok": result.get("ok"),
        "stdout": stdout[-200:],
        "stderr": str(result.get("stderr_tail") or "")[-400:],
    }
    passed = observed["ok"] is True and observed["exit"] == 0 and "socket-ok" in stdout
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:
        passed = False
        observed = {"error": str(exc)}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
