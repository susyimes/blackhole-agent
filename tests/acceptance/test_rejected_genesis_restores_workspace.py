"""Replay the dirty-worktree leak from rejected mission 20261030T005435Z-1557230e."""

import json
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.unbound import KernelTurnResult, UnboundMission, run_unbound_turn, save_mission


def observe() -> tuple[bool, dict]:
    with tempfile.TemporaryDirectory(prefix="bh-rejected-genesis-") as directory:
        root = Path(directory)
        work, state_path = root / "repo", root / "mission/state.json"
        work.mkdir()

        def git(*args):
            return subprocess.check_output(["git", *args], cwd=work, stderr=subprocess.PIPE, text=True).strip()

        git("init", "-b", "main")
        git("config", "user.name", "Probe")
        git("config", "user.email", "probe@example.invalid")
        git("config", "commit.gpgSign", "false")
        src = work / "src"
        src.mkdir()
        seed, other, rejected, kept = (src / name for name in ("seed.py", "other.py", "rejected_extra.py", "kept_extra.py"))
        seed.write_text("VALUE = 1\n")
        other.write_text("OTHER = 1\n")
        (work / ".gitignore").write_text(".venv/\n")
        git("add", ".")
        git("commit", "-m", "seed")
        head = git("rev-parse", "HEAD")
        venv, outside = work / ".venv/pyvenv.cfg", root / "outside.txt"
        venv.parent.mkdir()
        venv.write_text("keep-venv\n")
        outside.write_text("keep-outside\n")
        save_mission(state_path, UnboundMission(
            schema_version=1, mission_id="acceptance-restore", created_at="", updated_at="", repo_path=str(work),
            workspace_path=str(work), branch="main", target_branch="main", base_head=head, last_milestone_head=head,
        ))
        seen = {}

        def kernel(state, prompt, turn_dir, **kwargs):
            if state.iteration == 0:
                seed.write_text("VALUE = rejected\n")
                rejected.write_text("rejected\n")
                decision = dict(status="complete", mission_goal="none", done_when="none", done_when_met=True)
            else:
                seen.update(seen_seed=seed.read_text(), seen_extra=rejected.exists())
                seed.write_text("VALUE = kept\n")
                kept.write_text("kept\n")
                decision = dict(status="continue", mission_goal="Repair the failed sample marker for the operator.",
                                done_when="The marker file contains the recovered word.")
            return KernelTurnResult(state.kernel, json.dumps(decision), state.session_id, ("probe-kernel",), "")

        first = run_unbound_turn(state_path, kernel_runner=kernel)
        seen.update(turn1_accepted=first["selection_gate"]["accepted"], turn1_seed=seed.read_text(),
                    turn1_extra=rejected.exists(), turn1_clean=(first.get("rejected_workspace_restore") or {}).get("clean"))
        seed.write_text("VALUE = leftover\n")
        rejected.write_text("leftover\n")
        second = run_unbound_turn(state_path, kernel_runner=kernel)
        seen.update(turn2_accepted=second["selection_gate"]["accepted"], turn2_seed=seed.read_text(),
                    kept_extra=kept.read_text(), other=other.read_text(), venv=venv.read_text(), outside=outside.read_text())
        expected = {
            "turn1_accepted": False, "turn1_seed": "VALUE = 1\n", "turn1_extra": False, "turn1_clean": True,
            "seen_seed": "VALUE = 1\n", "seen_extra": False, "turn2_accepted": True, "turn2_seed": "VALUE = kept\n",
            "kept_extra": "kept\n", "other": "OTHER = 1\n", "venv": "keep-venv\n", "outside": "keep-outside\n",
        }
        return seen == expected and second.get("rejected_workspace_restore") is None, seen


if __name__ == "__main__":
    try:
        passed, observed = observe()
    except Exception as error:
        passed, observed = False, {"error": str(error)}
    print(json.dumps({"passed": passed, "observed": observed}))
