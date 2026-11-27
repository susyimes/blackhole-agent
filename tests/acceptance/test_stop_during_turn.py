"""Issue stop from another process while a real mission turn has pending work."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from blackhole_agent import unbound


def observe(root):
    work = root / "work"
    work.mkdir()
    state_path = root / "mission" / "state.json"

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=work, stderr=subprocess.PIPE, text=True).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "commit.gpgSign", "false")
    (work / ".gitignore").write_text(".blackhole-agent/\n", encoding="utf-8")
    git("add", ".gitignore")
    git("commit", "-m", "seed")
    head = git("rev-parse", "HEAD")
    unbound.save_mission(state_path, unbound.UnboundMission(
        schema_version=1, mission_id="count", created_at="", updated_at="", repo_path=str(work),
        workspace_path=str(work), branch="main", target_branch="main", goal="Count completed batches.",
        done_when="All batches were counted.", stage="execution", operator_supplied=True,
        selection_checked=True, kernel="cursor", base_head=head, last_milestone_head=head,
    ))

    def cli(command):
        launch = "import sys; sys.path.insert(0,sys.argv.pop(1)); from blackhole_agent.unbound import app; app()"
        return subprocess.check_output([
            sys.executable, "-I", "-X", "utf8", "-c", launch, str(Path(unbound.__file__).resolve().parents[1]),
            command, "--state-path", str(state_path),
        ], cwd=root, text=True, encoding="utf-8", timeout=20)

    def tick(outcome, *operator_commands):
        def batch(state, prompt, turn_dir, **kwargs):
            with (work / "batches.txt").open("a", encoding="utf-8") as handle:
                handle.write(f"{state.iteration + 1}\n")
            for command in operator_commands:
                cli(command)
            decision = {"status": outcome, "summary": "Counted a batch."}
            if outcome in {"milestone", "complete"}:
                decision.update(
                    capability_delta="Persist the counted batches.", done_when_met=outcome == "complete",
                    outcome_evidence=[f"batches.txt includes batch {state.iteration + 1}"],
                    validation=[{"command": "git diff --check", "exit_code": 0}],
                )
            return unbound.KernelTurnResult(state.kernel, json.dumps(decision), "batch-session", (), "")

        return unbound.run_unbound_turn(state_path, kernel_runner=batch)

    first = tick("milestone", "stop")
    saved = json.loads(cli("status"))
    try:
        tick("continue")
    except RuntimeError as error:
        if "Mission is stopped" not in str(error):
            raise
    before_resume = (work / "batches.txt").read_text().splitlines()
    cli("resume")
    resumed = tick("continue", "stop", "resume")
    final = json.loads(cli("status"))
    observed = {
        "after_stop": [saved["status"], saved["iteration"]],
        "milestone_preserved": (
            first["effective_status"] == "milestone" and saved["milestone_count"] == 1
            and saved["last_milestone_head"] == first["commit_sha"] == git("rev-parse", "HEAD")
            and git("show", "HEAD:batches.txt") == "1"
        ),
        "batches_before_resume": before_resume,
        "after_resume": [final["status"], resumed["iteration"], final["iteration"]],
        "batches_after_resume": (work / "batches.txt").read_text().splitlines(),
    }
    finished = tick("complete", "stop")
    cli("stop")  # A retry can arrive after the finishing checkpoint.
    closed = json.loads(cli("status"))
    observed["after_completion"] = [closed["status"], closed["iteration"], closed["milestone_count"]]
    observed["completed_work"] = git("show", "HEAD:batches.txt").splitlines() if finished["commit_sha"] else []
    return observed


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="mission-stop-") as directory:
        observed = observe(Path(directory))
    passed = observed == {
        "after_stop": ["stopped", 1], "milestone_preserved": True, "batches_before_resume": ["1"],
        "after_resume": ["active", 2, 2], "batches_after_resume": ["1", "2"],
        "after_completion": ["complete", 3, 2], "completed_work": ["1", "2", "3"],
    }
    print(json.dumps({"passed": passed, "observed": observed}))
