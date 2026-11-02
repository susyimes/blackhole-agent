"""Replay a PowerShell cmdlet statement that cmd.exe rejects.

Missions 20261102T061647Z and 20261102T065739Z submitted Set-Location before
the program. A statement that is only a cmdlet, with no variable assignment
and no call operator, was still handed to cmd.exe. cmd.exe exits 1 and names
Set-Location as not a command. Replay must change directory, run the program,
and keep native exit code 3. A cmd set-and-and chain stays on cmd. A cmdlet
written inside a quoted argument stays on cmd.

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
    code = "import os,sys; sys.stdout.write('bh-cmdlet|' + os.getcwd()); raise SystemExit(3)"
    with tempfile.TemporaryDirectory(prefix="bh-cmdlet-") as directory:
        root = Path(directory)
        target = root / "cmdlet nest"
        target.mkdir()
        command = f"Set-Location {_ps_quote(str(target))}; {python} -c {_ps_quote(code)}"
        push = f"Push-Location {_ps_quote(str(target))}; {python} -c {_ps_quote('import sys; raise SystemExit(0)')}"
        quoted = f'{python} -c "import sys; raise SystemExit(0 if \'Set-Location\' == \'Set-Location\' else 1)"'
        cmd_chain = (
            f'set BH_CMDLET_MARK=bh-cmd-chain&& "{python}" -c "import os,sys; '
            "raise SystemExit(0 if os.environ.get('BH_CMDLET_MARK')=='bh-cmd-chain' else 1)\""
        )
        result = replay_validation_command(root, command, timeout=30)
        quoted_result = replay_validation_command(root, quoted, timeout=30)
        cmd_result = replay_validation_command(root, cmd_chain, timeout=30)
    stdout = str(result.get("stdout_tail") or "")
    printed = ""
    if "bh-cmdlet|" in stdout:
        printed = stdout.split("bh-cmdlet|", 1)[1].strip().splitlines()[0].strip()
    cwd_ok = False
    if printed:
        try:
            cwd_ok = Path(printed).resolve() == target.resolve()
        except OSError:
            cwd_ok = False
    observed = {
        "cmdlet_without_assignment_or_call": "$" not in command and "&" not in command,
        "executable_unquoted": " " not in python,
        "set_location_routed_to_pwsh": powershell_replay_argv(command) is not None,
        "push_location_routed_to_pwsh": powershell_replay_argv(push) is not None,
        "get_location_routed_to_pwsh": powershell_replay_argv("Get-Location") is not None,
        "set_location_exit": result.get("reproduced_exit_code"),
        "set_location_marker": "bh-cmdlet|" in stdout,
        "set_location_cwd": cwd_ok,
        "quoted_cmdlet_stays_on_cmd": powershell_replay_argv(quoted) is None,
        "quoted_exit": quoted_result.get("reproduced_exit_code"),
        "cmd_chain_stays_on_cmd": powershell_replay_argv(cmd_chain) is None,
        "cmd_chain_exit": cmd_result.get("reproduced_exit_code"),
        "cmd_chain_ok": cmd_result.get("ok"),
    }
    passed = (
        observed["cmdlet_without_assignment_or_call"] is True
        and observed["executable_unquoted"] is True
        and observed["set_location_routed_to_pwsh"] is True
        and observed["push_location_routed_to_pwsh"] is True
        and observed["get_location_routed_to_pwsh"] is True
        and observed["set_location_exit"] == 3
        and observed["set_location_marker"] is True
        and observed["set_location_cwd"] is True
        and observed["quoted_cmdlet_stays_on_cmd"] is True
        and observed["quoted_exit"] == 0
        and observed["cmd_chain_stays_on_cmd"] is True
        and observed["cmd_chain_ok"] is True
        and observed["cmd_chain_exit"] == 0
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:
        passed = False
        observed = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
