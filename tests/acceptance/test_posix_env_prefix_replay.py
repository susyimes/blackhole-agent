"""Controller replay must apply a leading POSIX environment prefix.

Harvested 2026-09-13: ``PYTHONPATH=src uv run python ...`` was reported with
exit 0, and cmd replay exited 1 because it executed ``PYTHONPATH=src`` as
the program. PowerShell does not accept that prefix, so sending the same
text to pwsh cannot reproduce the child environment. The prefix is removed
and applied to the child. A cmd ``set NAME=value&&`` chain stays on cmd.
A ``NAME=value&&`` token is not a prefix. An assignment that appears only
inside a quoted argument does not change the child environment.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def observe() -> tuple[bool, dict]:
    from blackhole_agent.unbound import powershell_replay_argv, replay_validation_command

    python = str(Path(sys.executable))
    value = "bh-posix-replay"
    mark = "b19004cb"
    success = (
        f"PYTHONPATH={value} BH_POSIX_PROBE={mark} \"{python}\" -c "
        "\"import os,sys; raise SystemExit(0 if os.environ.get('PYTHONPATH')=="
        f"'{value}' and os.environ.get('BH_POSIX_PROBE')=='{mark}' else 1)\""
    )
    failure = f"PYTHONPATH={value} \"{python}\" -c \"import sys; raise SystemExit(3)\""
    quoted = (
        f"\"{python}\" -c \"import os,sys; raise SystemExit(0 if "
        f"os.environ.get('BH_POSIX_PROBE')!='{mark}' else 1)\""
    )
    cmd_chain = (
        f"set BH_POSIX_MARK={mark}&& \"{python}\" -c \"import os,sys; "
        f"raise SystemExit(0 if os.environ.get('BH_POSIX_MARK')=='{mark}' else 1)\""
    )
    stuck = f"PYTHONPATH={value}&& \"{python}\" -c \"import sys; raise SystemExit(0)\""
    bare = f"PYTHONPATH={value}"
    with tempfile.TemporaryDirectory(prefix="bh-posix-prefix-") as directory:
        root = Path(directory)
        success_result = replay_validation_command(root, success, timeout=30)
        failure_result = replay_validation_command(root, failure, timeout=30)
        quoted_result = replay_validation_command(root, quoted, timeout=30)
        cmd_result = replay_validation_command(root, cmd_chain, timeout=30)
        stuck_result = replay_validation_command(root, stuck, timeout=30)
        bare_result = replay_validation_command(root, bare, timeout=30)
    observed = {
        "prefix_command": success,
        "prefix_not_powershell": powershell_replay_argv(success) is None,
        "success_exit": success_result.get("reproduced_exit_code"),
        "success_ok": success_result.get("ok"),
        "failure_exit": failure_result.get("reproduced_exit_code"),
        "failure_ok": failure_result.get("ok"),
        "quoted_exit": quoted_result.get("reproduced_exit_code"),
        "quoted_ok": quoted_result.get("ok"),
        "cmd_chain_exit": cmd_result.get("reproduced_exit_code"),
        "cmd_chain_ok": cmd_result.get("ok"),
        "ampersand_exit": stuck_result.get("reproduced_exit_code"),
        "ampersand_ok": stuck_result.get("ok"),
        "bare_exit": bare_result.get("reproduced_exit_code"),
        "bare_ok": bare_result.get("ok"),
    }
    passed = (
        observed["prefix_not_powershell"] is True
        and observed["success_ok"] is True
        and observed["success_exit"] == 0
        and observed["failure_ok"] is False
        and observed["failure_exit"] == 3
        and observed["quoted_ok"] is True
        and observed["quoted_exit"] == 0
        and observed["cmd_chain_ok"] is True
        and observed["cmd_chain_exit"] == 0
        and observed["ampersand_ok"] is False
        and observed["bare_ok"] is False
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
