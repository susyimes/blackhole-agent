"""Replay the harvested pwsh script that binds $py and calls & $py.

Mission 20261102T091949Z-5854d648 reported exit 0 for a newline script that
assigns python.exe to $py and invokes it with the call operator. Controller
replay handed that script to cmd.exe, which exited 1. The same script must
start python and keep the native exit code. A cmd set-and-and chain stays on
cmd. An assignment written inside a quoted argument stays on cmd.

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

    python = str(Path(sys.executable))
    marker = "bh-py-call"
    success_code = f'import sys; sys.stdout.write("{marker}"); raise SystemExit(0)'
    success_command = f"$py = {_ps_quote(python)}\n& $py -c {_ps_quote(success_code)}"
    failure_command = (
        f"$py = {_ps_quote(python)}\n& $py -c {_ps_quote('import sys; raise SystemExit(3)')}"
    )
    embedded_command = (
        f'"{python}" -c "import sys; s=\'$py = 1\'; raise SystemExit(0)"'
    )
    cmd_chain = (
        f'set BH_PY_MARK={marker}&& "{python}" -c "import os,sys; '
        f"raise SystemExit(0 if os.environ.get('BH_PY_MARK')=='{marker}' else 1)\""
    )
    with tempfile.TemporaryDirectory(prefix="bh-py-call-") as directory:
        root = Path(directory)
        success = replay_validation_command(root, success_command, timeout=30)
        failure = replay_validation_command(root, failure_command, timeout=30)
        embedded = replay_validation_command(root, embedded_command, timeout=30)
        cmd_result = replay_validation_command(root, cmd_chain, timeout=30)
    observed = {
        "newline_variable_call": "\n& $py " in success_command and "$env:" not in success_command.lower(),
        "success_routed_to_pwsh": powershell_replay_argv(success_command) is not None,
        "success_exit": success.get("reproduced_exit_code"),
        "success_ok": success.get("ok"),
        "success_marker": marker in str(success.get("stdout_tail") or ""),
        "failure_exit": failure.get("reproduced_exit_code"),
        "failure_ok": failure.get("ok"),
        "embedded_stays_on_cmd": powershell_replay_argv(embedded_command) is None,
        "embedded_exit": embedded.get("reproduced_exit_code"),
        "embedded_ok": embedded.get("ok"),
        "cmd_chain_stays_on_cmd": powershell_replay_argv(cmd_chain) is None,
        "cmd_chain_exit": cmd_result.get("reproduced_exit_code"),
        "cmd_chain_ok": cmd_result.get("ok"),
    }
    passed = (
        observed["newline_variable_call"] is True
        and observed["success_routed_to_pwsh"] is True
        and observed["success_ok"] is True
        and observed["success_exit"] == 0
        and observed["success_marker"] is True
        and observed["failure_ok"] is False
        and observed["failure_exit"] == 3
        and observed["embedded_stays_on_cmd"] is True
        and observed["embedded_ok"] is True
        and observed["embedded_exit"] == 0
        and observed["cmd_chain_stays_on_cmd"] is True
        and observed["cmd_chain_ok"] is True
        and observed["cmd_chain_exit"] == 0
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
