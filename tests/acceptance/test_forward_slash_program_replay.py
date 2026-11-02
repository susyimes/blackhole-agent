"""Controller replay must start a relative program path that uses forward slashes.

Harvested 2026-10-10: ``.venv/Scripts/python.exe -m pytest ...`` was reported
with exit 0 from pwsh. cmd.exe treated ``/`` as a switch, executed ``.venv``,
and exited 1. The program token is rewritten to backslashes. The command is
not sent to pwsh. A backslash program and a quoted argument that contains a
slash keep their native exit codes.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def observe() -> tuple[bool, dict]:
    from blackhole_agent.unbound import powershell_replay_argv, replay_validation_command

    python = Path(sys.executable).resolve()
    root = python.parent.parent
    relative = python.relative_to(root).as_posix()
    if "/" not in relative:
        return False, {"error": "interpreter path has no relative slash to replay"}
    forward = f'{relative} -c "import sys; raise SystemExit(3)"'
    backward = str(python)
    quoted_program = f'"{backward}"' if " " in backward else backward
    native = f'{quoted_program} -c "import sys; raise SystemExit(3)"'
    slashed_argument = (
        f'{quoted_program} -c "import sys; raise SystemExit(0 if \'/\' in \'a/b\' else 1)"'
    )
    forward_result = replay_validation_command(root, forward, timeout=30)
    native_result = replay_validation_command(root, native, timeout=30)
    argument_result = replay_validation_command(root, slashed_argument, timeout=30)
    observed = {
        "program": relative,
        "forward_not_powershell": powershell_replay_argv(forward) is None,
        "forward_exit": forward_result.get("reproduced_exit_code"),
        "forward_ok": forward_result.get("ok"),
        "native_exit": native_result.get("reproduced_exit_code"),
        "native_ok": native_result.get("ok"),
        "argument_exit": argument_result.get("reproduced_exit_code"),
        "argument_ok": argument_result.get("ok"),
    }
    passed = (
        observed["forward_not_powershell"] is True
        and observed["forward_exit"] == 3
        and observed["forward_ok"] is False
        and observed["native_exit"] == 3
        and observed["native_ok"] is False
        and observed["argument_exit"] == 0
        and observed["argument_ok"] is True
    )
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - probe must exit 0 with an unmet outcome
        passed = False
        observed = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
