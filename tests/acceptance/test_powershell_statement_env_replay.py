"""Controller replay must keep a PowerShell env assignment that follows a statement.

A leading ``$env:`` assignment already reaches pwsh. The same assignment after
another statement, ``Set-Location <dir>; $env:NAME = 'value'; <python>``, was
still sent to cmd.exe, which exits 1 and drops the native code. An assignment
written inside a quoted Python string is not that statement and stays on cmd.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def observe() -> tuple[bool, dict]:
    from blackhole_agent.unbound import powershell_replay_argv, replay_validation_command

    with tempfile.TemporaryDirectory(prefix="bh-ps-stmt-") as directory:
        root = Path(directory)
        python = str(Path(sys.executable))
        # Bind the interpreter in a variable, then call it. A quoted
        # ``& '<python>'`` is already routed; ``& $py`` is not, so a leading
        # statement is what must move this command onto pwsh.
        prefix = f"$py = {_ps_quote(python)}; Set-Location {_ps_quote(str(root))}; "
        success_code = (
            'import os,sys; raise SystemExit(0 if os.environ.get("BH_REPLAY_MARK")=="kept" else 4)'
        )
        success_command = (
            f"{prefix}$env:BH_REPLAY_MARK = 'kept'; & $py -c {_ps_quote(success_code)}"
        )
        failure_command = (
            f"{prefix}$env:BH_REPLAY_MARK = 'kept'; "
            f"& $py -c {_ps_quote('import sys; raise SystemExit(3)')}"
        )
        embedded_command = (
            f'"{python}" -c "import sys; s=\'; $env:FOO = 1\'; raise SystemExit(0)"'
        )
        cmd_command = f'"{python}" -c "import sys; raise SystemExit(0)"'
        success = replay_validation_command(root, success_command, timeout=30)
        failure = replay_validation_command(root, failure_command, timeout=30)
        embedded = replay_validation_command(root, embedded_command, timeout=30)
        cmd_result = replay_validation_command(root, cmd_command, timeout=30)
    observed = {
        "statement_before_assignment": (
            not success_command.lower().lstrip().startswith("$env:")
            and "; $env:bh_replay_mark" in success_command.lower()
        ),
        "success_routed_to_pwsh": powershell_replay_argv(success_command) is not None,
        "success_exit": success.get("reproduced_exit_code"),
        "success_ok": success.get("ok"),
        "failure_exit": failure.get("reproduced_exit_code"),
        "failure_ok": failure.get("ok"),
        "embedded_stays_on_cmd": powershell_replay_argv(embedded_command) is None,
        "embedded_exit": embedded.get("reproduced_exit_code"),
        "embedded_ok": embedded.get("ok"),
        "cmd_exit": cmd_result.get("reproduced_exit_code"),
        "cmd_ok": cmd_result.get("ok"),
    }
    passed = (
        observed["statement_before_assignment"] is True
        and observed["success_routed_to_pwsh"] is True
        and observed["success_ok"] is True
        and observed["success_exit"] == 0
        and observed["failure_ok"] is False
        and observed["failure_exit"] == 3
        and observed["embedded_stays_on_cmd"] is True
        and observed["embedded_ok"] is True
        and observed["embedded_exit"] == 0
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
