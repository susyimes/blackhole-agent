"""A command cmd.exe rejects keeps the agent shell's failed exit code.

cmd.exe turns ``if (1 -eq 0) { exit 0 } else { exit 5 }`` into exit 1 before
any program runs. The agent shell runs that comparison and exits 5. Replay
keeps exit 5. A native program cmd.exe actually starts still keeps its own
exit, and a comparison the agent shell can satisfy still exits 0.

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
    rejected = "if (1 -eq 0) { exit 0 } else { exit 5 }"
    native = f'"{python}" -c "import sys; raise SystemExit(4)"'
    traced = (
        f'"{python}" -c "import sys; sys.stderr.write(\'traceback-marker\\n\'); '
        'raise SystemExit(1)"'
    )
    satisfied = "if (1 -eq 1) { exit 0 } else { exit 4 }"
    rejected_result = replay_validation_command(Path("."), rejected, timeout=30)
    native_result = replay_validation_command(Path("."), native, timeout=30)
    traced_result = replay_validation_command(Path("."), traced, timeout=30)
    satisfied_result = replay_validation_command(Path("."), satisfied, timeout=30)
    observed = {
        "rejected_exit": rejected_result.get("reproduced_exit_code"),
        "rejected_ok": rejected_result.get("ok"),
        "rejected_fallback": rejected_result.get("shell_fallback"),
        "native_exit": native_result.get("reproduced_exit_code"),
        "native_fallback": native_result.get("shell_fallback"),
        "traced_exit": traced_result.get("reproduced_exit_code"),
        "traced_fallback": traced_result.get("shell_fallback"),
        "satisfied_exit": satisfied_result.get("reproduced_exit_code"),
        "satisfied_ok": satisfied_result.get("ok"),
        "satisfied_fallback": satisfied_result.get("shell_fallback"),
    }
    passed = (
        observed["rejected_exit"] == 5
        and observed["rejected_ok"] is False
        and observed["rejected_fallback"] is True
        and observed["native_exit"] == 4
        and observed["native_fallback"] is not True
        and observed["traced_exit"] == 1
        and observed["traced_fallback"] is not True
        and observed["satisfied_exit"] == 0
        and observed["satisfied_ok"] is True
        and observed["satisfied_fallback"] is True
    )
    return passed, observed


def test_rejected_cmd_launch_keeps_agent_shell_exit() -> None:
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
