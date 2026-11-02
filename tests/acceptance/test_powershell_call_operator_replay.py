"""Controller replay must run a PowerShell call operator with no $env: assignment.

The agent shell is pwsh. A reported validation of the form
``& '<python>' -m ruff check ...`` exited 0, and cmd.exe replay exited 1
because ``&`` is not a call operator there. Commands that assign
``$env:`` were already routed to pwsh. This form has no assignment.

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

    with tempfile.TemporaryDirectory(prefix="bh-ps-call-") as directory:
        root = Path(directory)
        script = root / "child.py"
        script.write_text(
            "print('CALL_OK')\nraise SystemExit(0)\n",
            encoding="utf-8",
        )
        python = str(Path(sys.executable))
        success_command = f"& {_ps_quote(python)} {_ps_quote(str(script))}"
        failure_command = (
            f"& {_ps_quote(python)} -c {_ps_quote('import sys; raise SystemExit(3)')}"
        )
        missing_command = "& 'C:\\no\\such\\blackhole-python.exe' -c 'import sys'"
        cmd_command = f'"{python}" -c "import sys; raise SystemExit(0)"'
        success = replay_validation_command(root, success_command, timeout=30)
        failure = replay_validation_command(root, failure_command, timeout=30)
        missing = replay_validation_command(root, missing_command, timeout=30)
        cmd_result = replay_validation_command(root, cmd_command, timeout=30)
    stdout = str(success.get("stdout_tail") or "")
    observed = {
        "call_exit": success.get("reproduced_exit_code"),
        "call_ok": success.get("ok"),
        "call_saw_marker": "CALL_OK" in stdout,
        "failure_exit": failure.get("reproduced_exit_code"),
        "failure_ok": failure.get("ok"),
        "missing_exit": missing.get("reproduced_exit_code"),
        "missing_ok": missing.get("ok"),
        "cmd_exit": cmd_result.get("reproduced_exit_code"),
        "cmd_ok": cmd_result.get("ok"),
        "env_assignment_absent": "$env:" not in success_command.lower(),
        "call_operator_present": success_command.startswith("& "),
    }
    passed = (
        observed["env_assignment_absent"] is True
        and observed["call_operator_present"] is True
        and observed["call_ok"] is True
        and observed["call_exit"] == 0
        and observed["call_saw_marker"] is True
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
