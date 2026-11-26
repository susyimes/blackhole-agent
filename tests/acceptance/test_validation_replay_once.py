"""Observe the validator's own writes alongside the controller's replay receipt."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from blackhole_agent.unbound import replay_validation_command


VALIDATOR = """\
import sys
from pathlib import Path

log = Path(sys.argv[1])
with log.open("a", encoding="utf-8") as stream:
    print("called", file=stream)
attempt = len(log.read_text(encoding="utf-8").splitlines())
print(f"out {attempt}")
print(f"err {attempt}", file=sys.stderr)
raise SystemExit(int(sys.argv[2]) if attempt == 1 else 0)
"""


def observe():
    python = Path(sys.executable)
    # Both shells can launch the same bare program name even if its path contains spaces.
    path = os.pathsep.join((str(python.parent), os.environ.get("PATH", "")))
    with tempfile.TemporaryDirectory(prefix="bh-replay-once-") as directory, patch.dict(os.environ, PATH=path):
        root = Path(directory)
        (root / "check.py").write_text(VALIDATOR, encoding="utf-8")
        observations = {}
        for name, tail in (("failure", "23"), ("success", "0"), ("chain", "0 && bh_absent_replay_fixture")):
            receipt = replay_validation_command(root, f"{python.name} check.py {name} {tail}")
            log = root / name
            observations[name] = {
                "writes": len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0,
                "exit": receipt["reproduced_exit_code"],
                "ok": receipt["ok"],
                "stdout": receipt["stdout_tail"].strip(),
                "stderr": receipt["stderr_tail"].strip(),
            }
        failure, success, chain = (observations[name] for name in ("failure", "success", "chain"))
        passed = (
            failure == dict(writes=1, exit=23, ok=False, stdout="out 1", stderr="err 1")
            and success == dict(writes=1, exit=0, ok=True, stdout="out 1", stderr="err 1")
            and chain["writes"] == 1
            and chain["exit"] not in (None, 0)
            and chain["ok"] is False
        )
        if os.name == "nt":
            exits = []
            for value in (1, 0):
                command = f"if (1 -eq {value}) {{ exit 0 }} else {{ exit 5 }}"
                exits.append(replay_validation_command(root, command)["reproduced_exit_code"])
            observations["powershell_exits"] = exits
            recovery = replay_validation_command(root, "bh_absent_replay_fixture || exit /b 9")
            alias = replay_validation_command(root, "gci -Name check.py | findstr /x check.py")
            observations["cmd_recovery_exit"] = recovery["reproduced_exit_code"]
            observations["alias_output"] = alias["stdout_tail"].strip()
            passed = (
                passed and exits == [0, 5] and recovery["reproduced_exit_code"] == 9
                and alias["ok"] and observations["alias_output"] == "check.py"
            )
        return {"passed": passed, "observed": observations}


def test_validation_runs_once():
    outcome = observe()
    assert outcome["passed"], outcome


if __name__ == "__main__":
    print(json.dumps(observe()))
