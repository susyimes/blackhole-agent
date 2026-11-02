"""Replay a native program piped into a PowerShell command.

cmd.exe still launched ``python -c ... | Out-Null`` and ``foreach`` because
neither is a statement-initial verb from the old prefix table. Out-Null and
foreach are not programs, so the native exit code disappeared. Replay must
return exit code 3 for both. A cmd ``set VAR=value&&`` chain must still
return exit code 0 with that variable visible to the program.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def observe() -> tuple[bool, dict]:
    from blackhole_agent.unbound import replay_validation_command

    python = str(Path(sys.executable).resolve())
    root = Path(sys.executable).resolve().parent
    code = "import sys; raise SystemExit(3)"
    pipeline = f'{python} -c "{code}" | Out-Null'
    foreach = f'foreach ($i in 1) {{ {python} -c "{code}" }}'
    try_statement = f'try {{ {python} -c "{code}" }} catch {{ exit 9 }}'
    chain = (
        f'set BH_REPLAY_PROBE=src&& "{python}" -c "import os,sys; '
        "raise SystemExit(0 if os.environ.get('BH_REPLAY_PROBE')=='src' else 4)\""
    )
    quoted = (
        f'{python} -c "import sys; raise SystemExit(0 if sys.argv[1] == chr(36)+\'env:FOO\' else 1)" '
        '"$env:FOO"'
    )
    pipeline_result = replay_validation_command(root, pipeline, timeout=30)
    foreach_result = replay_validation_command(root, foreach, timeout=30)
    try_result = replay_validation_command(root, try_statement, timeout=30)
    chain_result = replay_validation_command(root, chain, timeout=30)
    quoted_result = replay_validation_command(root, quoted, timeout=30)
    observed = {
        "pipeline_exit": pipeline_result.get("reproduced_exit_code"),
        "foreach_exit": foreach_result.get("reproduced_exit_code"),
        "try_exit": try_result.get("reproduced_exit_code"),
        "set_chain_exit": chain_result.get("reproduced_exit_code"),
        "quoted_dollar_exit": quoted_result.get("reproduced_exit_code"),
        "pipeline_stderr": (pipeline_result.get("stderr_tail") or "")[-240:],
        "foreach_stderr": (foreach_result.get("stderr_tail") or "")[-240:],
    }
    passed = (
        observed["pipeline_exit"] == 3
        and observed["foreach_exit"] == 3
        and observed["try_exit"] == 3
        and observed["set_chain_exit"] == 0
        and observed["quoted_dollar_exit"] == 0
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
