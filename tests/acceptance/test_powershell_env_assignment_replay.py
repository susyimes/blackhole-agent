"""Controller replay must run a PowerShell env assignment without '&'.

The quoted call-operator form already reaches pwsh. Agents also report
``$env:PYTHONPATH = '<dir>'; <python> <probe> <dir>`` with no call operator.
cmd.exe replay of that form exits 1 and rejects a milestone whose agent
command exited 0.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def observe() -> tuple[bool, dict]:
    from blackhole_agent.unbound import replay_validation_command

    with tempfile.TemporaryDirectory(prefix="bh-ps-assign-") as directory:
        root = Path(directory)
        script = root / "child.py"
        script.write_text(
            "import os, sys\n"
            "expected = sys.argv[1]\n"
            "got = os.environ.get('PYTHONPATH', '')\n"
            "print('PYPATH=' + got)\n"
            "raise SystemExit(0 if got == expected else 2)\n",
            encoding="utf-8",
        )
        expected = str(root)
        python = str(Path(sys.executable))
        if any(character.isspace() for character in python):
            raise RuntimeError("python path contains spaces")
        success_command = (
            f"$env:PYTHONPATH = {_ps_quote(expected)}; "
            f"{python} {_ps_quote(str(script))} {_ps_quote(expected)}"
        )
        failure_command = (
            f"$env:PYTHONPATH = {_ps_quote(expected)}; "
            f"{python} -c {_ps_quote('import sys; raise SystemExit(3)')}"
        )
        missing_command = "$env:PYTHONPATH = 'src'; C:\\no\\such\\blackhole-python.exe 'x.py'"
        cmd_command = f'set PYTHONPATH={expected}&& "{python}" "{script}" "{expected}"'
        success = replay_validation_command(root, success_command, timeout=30)
        failure = replay_validation_command(root, failure_command, timeout=30)
        missing = replay_validation_command(root, missing_command, timeout=30)
        cmd_result = replay_validation_command(root, cmd_command, timeout=30)
    stdout = str(success.get("stdout_tail") or "")
    observed = {
        "assignment_exit": success.get("reproduced_exit_code"),
        "assignment_ok": success.get("ok"),
        "assignment_saw_path": f"PYPATH={expected}" in stdout,
        "failure_exit": failure.get("reproduced_exit_code"),
        "failure_ok": failure.get("ok"),
        "missing_exit": missing.get("reproduced_exit_code"),
        "missing_ok": missing.get("ok"),
        "cmd_exit": cmd_result.get("reproduced_exit_code"),
        "cmd_ok": cmd_result.get("ok"),
        "call_operator_absent": "&" not in success_command,
    }
    passed = (
        observed["call_operator_absent"] is True
        and observed["assignment_ok"] is True
        and observed["assignment_exit"] == 0
        and observed["assignment_saw_path"] is True
        and observed["failure_ok"] is False
        and observed["failure_exit"] == 3
        and observed["missing_ok"] is False
        and observed["missing_exit"] not in (0, None)
        and observed["cmd_ok"] is True
        and observed["cmd_exit"] == 0
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
