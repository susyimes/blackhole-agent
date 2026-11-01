"""Controller replay must run the harvested PowerShell validation form.

Mission 20261101T123515Z-b531bbb1 reported exit 0 for
``$env:PYTHONPATH = 'src'; & '<python>' <probe>``. cmd.exe replay returned
exit 1 and rejected the milestone. This probe prints JSON with boolean
passed and nonempty observed. Both outcomes exit 0.
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

    with tempfile.TemporaryDirectory(prefix="bh-ps-replay-") as directory:
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
        success_command = (
            f"$env:PYTHONPATH = {_ps_quote(expected)}; "
            f"& {_ps_quote(python)} {_ps_quote(str(script))} {_ps_quote(expected)}"
        )
        failure_command = (
            f"$env:PYTHONPATH = {_ps_quote(expected)}; "
            f"& {_ps_quote(python)} -c {_ps_quote('import sys; raise SystemExit(3)')}"
        )
        missing_command = (
            "$env:PYTHONPATH = 'src'; & 'C:\\no\\such\\blackhole-python.exe' 'x.py'"
        )
        cmd_command = (
            f'set PYTHONPATH={expected}&& "{python}" "{script}" "{expected}"'
        )
        success = replay_validation_command(root, success_command, timeout=30)
        failure = replay_validation_command(root, failure_command, timeout=30)
        missing = replay_validation_command(root, missing_command, timeout=30)
        cmd_result = replay_validation_command(root, cmd_command, timeout=30)
    stdout = str(success.get("stdout_tail") or "")
    observed = {
        "powershell_exit": success.get("reproduced_exit_code"),
        "powershell_ok": success.get("ok"),
        "powershell_saw_path": f"PYPATH={expected}" in stdout,
        "failure_exit": failure.get("reproduced_exit_code"),
        "failure_ok": failure.get("ok"),
        "missing_exit": missing.get("reproduced_exit_code"),
        "missing_ok": missing.get("ok"),
        "cmd_exit": cmd_result.get("reproduced_exit_code"),
        "cmd_ok": cmd_result.get("ok"),
    }
    passed = (
        observed["powershell_ok"] is True
        and observed["powershell_exit"] == 0
        and observed["powershell_saw_path"] is True
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
