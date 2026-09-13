"""Acceptance probe: an unsolvable goal drives real zero-spec acquisition.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe
is fully self-contained: it builds a fresh workspace (bare pyproject, empty
capability ledger) and a bare manifest-less candidate package in a temp
directory, then drives the goal-foraging CLI as a separate OS process the
way an operator would:

1. the goal ``shout_output`` is honestly unsolvable over the empty ledger;
   with one forage candidate the CLI must infer the spec, absorb, prove,
   and register the capability, then plan and execute it for real,
   returning the outcome computed by the freshly foraged tool;
2. a follow-up solve of the same goal *without* candidates must now solve
   from the durably grown ledger — proof the acquisition was real, not a
   one-shot shim;
3. in a fresh workspace with no candidates the same goal must stay
   honestly unsolved, naming the uncovered key.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay the same probe on baseline
and candidate source trees: the baseline tree has no
``blackhole_agent.goal_foraging`` module, so the probe reports
passed=false.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_PACKAGE_SOURCE = '''"""Probe fixture: an uncooperative module with mixed candidates."""

CONSTANT = 42


def shout(text):
    return text.upper() + "!"


def brittle(text):
    if not text:
        raise ValueError("empty input refused")
    return text.strip().title()


def needs_two(first, second):
    return first + second


def _hidden(text):
    return text
'''


def _build_workspace(base: Path) -> Path:
    root = base / "workspace"
    (root / "capabilities").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "probe-workspace"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": {}}),
        encoding="utf-8",
    )
    return root


def _build_candidate(base: Path) -> Path:
    package = base / "shout-lab"
    package.mkdir(parents=True)
    (package / "shout_lab.py").write_text(_PACKAGE_SOURCE, encoding="utf-8")
    return package


def _run_cli(src_root: Path, root: Path, goal: str, candidates: list[dict]) -> dict:
    command = [
        sys.executable,
        "-m",
        "blackhole_agent.goal_foraging",
        "solve",
        "--root",
        str(root),
        "--state",
        json.dumps({"text": "blackhole unbound"}),
        "--goal",
        goal,
    ]
    for candidate in candidates:
        command += ["--candidate", json.dumps(candidate)]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    try:
        body = json.loads(completed.stdout or "")
    except json.JSONDecodeError:
        body = None
    return {
        "exit_code": completed.returncode,
        "body": body,
        "stderr": (completed.stderr or "").strip().splitlines()[:3],
    }


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "goal-driven-foraging"}
    try:
        import blackhole_agent.goal_foraging as goal_foraging
    except Exception as error:  # baseline source tree has no goal-foraging loop
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(goal_foraging, "solve_with_forage"):
        observed["detail"] = "baseline module has no solve_with_forage"
        return {"passed": False, "observed": observed}

    src_root = Path(goal_foraging.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="goal-foraging-probe-") as directory:
        base = Path(directory)
        workspace = _build_workspace(base / "first")
        package = _build_candidate(base / "pkg")
        candidate = {
            "name": "shout-lab (probe fixture package)",
            "slug": "shout-lab",
            "hint": "shout_lab",
            "source": str(package),
            "origin": {"kind": "fixture", "source": "probe-synthesized"},
        }

        driven = _run_cli(src_root, workspace, "shout_output", [candidate])
        observed["driven_exit"] = driven["exit_code"]
        body = driven["body"] if isinstance(driven["body"], dict) else {}
        observed["driven_solved"] = body.get("solved")
        observed["driven_plan"] = body.get("plan")
        observed["driven_outcome"] = body.get("outcome")
        observed["driven_acquisition"] = body.get("acquisition")
        observed["driven_stderr"] = driven["stderr"]
        acquisition = body.get("acquisition") if isinstance(body.get("acquisition"), dict) else {}
        driven_ok = (
            driven["exit_code"] == 0
            and body.get("solved") is True
            and body.get("plan") == ["capability.absorbed-shout-lab"]
            and body.get("outcome") == {"shout_output": "BLACKHOLE UNBOUND!"}
            and acquisition.get("needed") is True
            and "capability.absorbed-shout-lab"
            in (acquisition.get("acquired_capability_ids") or [])
            and bool(body.get("plan_digest"))
        )

        replay = _run_cli(src_root, workspace, "shout_output", [])
        replay_body = replay["body"] if isinstance(replay["body"], dict) else {}
        replay_acquisition = (
            replay_body.get("acquisition")
            if isinstance(replay_body.get("acquisition"), dict)
            else {}
        )
        observed["replay_solved"] = replay_body.get("solved")
        observed["replay_outcome"] = replay_body.get("outcome")
        replay_ok = (
            replay["exit_code"] == 0
            and replay_body.get("solved") is True
            and replay_body.get("outcome") == {"shout_output": "BLACKHOLE UNBOUND!"}
            and replay_acquisition.get("needed") is False
        )

        fresh = _build_workspace(base / "second")
        honest = _run_cli(src_root, fresh, "shout_output", [])
        honest_body = honest["body"] if isinstance(honest["body"], dict) else {}
        observed["honest_solved"] = honest_body.get("solved")
        observed["honest_uncovered"] = honest_body.get("uncovered")
        honest_ok = (
            honest["exit_code"] == 0
            and honest_body.get("solved") is False
            and honest_body.get("plan") is None
            and honest_body.get("uncovered") == ["shout_output"]
        )

        observed["checks"] = {
            "forage_closed_the_goal": driven_ok,
            "acquisition_durable": replay_ok,
            "uncovered_goal_honest": honest_ok,
        }
        passed = driven_ok and replay_ok and honest_ok
        return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict))
    sys.exit(0)
