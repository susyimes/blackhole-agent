"""Replay an unclassified comparison through the agent shell after cmd.exe fails.

cmd.exe rejects ``if (1 -eq 1) { exit 0 } else { exit 4 }`` because ``-eq`` is
not cmd syntax. The statement is not a classified PowerShell form, so replay
used to stop at that cmd failure. A failed cmd launch now runs again in the
agent shell, and an agent-shell exit 0 is the replay result. A native program
that already exits 4 under cmd stays 4. A cmd ``set VAR=value&&`` chain that
already exits 0 is not run again.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def observe() -> tuple[bool, dict]:
    from blackhole_agent.unbound import powershell_replay_argv, replay_validation_command

    python = str(Path(sys.executable).resolve())
    comparison = "if (1 -eq 1) { exit 0 } else { exit 4 }"
    native = f'"{python}" -c "import sys; raise SystemExit(4)"'
    chain = (
        f'set BH_FALLBACK_MARK=1&& "{python}" -c "import os,sys; '
        "raise SystemExit(0 if os.environ.get('BH_FALLBACK_MARK')=='1' else 7)\""
    )
    comparison_result = replay_validation_command(Path("."), comparison, timeout=30)
    native_result = replay_validation_command(Path("."), native, timeout=30)
    chain_result = replay_validation_command(Path("."), chain, timeout=30)
    observed = {
        "comparison_unclassified": powershell_replay_argv(comparison) is None,
        "comparison_exit": comparison_result.get("reproduced_exit_code"),
        "comparison_ok": comparison_result.get("ok"),
        "comparison_fallback": comparison_result.get("shell_fallback"),
        "native_exit": native_result.get("reproduced_exit_code"),
        "native_ok": native_result.get("ok"),
        "native_fallback": native_result.get("shell_fallback"),
        "chain_exit": chain_result.get("reproduced_exit_code"),
        "chain_ok": chain_result.get("ok"),
        "chain_fallback": chain_result.get("shell_fallback"),
    }
    passed = (
        observed["comparison_unclassified"] is True
        and observed["comparison_ok"] is True
        and observed["comparison_exit"] == 0
        and observed["comparison_fallback"] is True
        and observed["native_ok"] is False
        and observed["native_exit"] == 4
        and observed["native_fallback"] is not True
        and observed["chain_ok"] is True
        and observed["chain_exit"] == 0
        and observed["chain_fallback"] is not True
    )
    return passed, observed


def test_unclassified_comparison_falls_back_to_the_agent_shell() -> None:
    passed, observed = observe()
    assert passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:500]}
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
