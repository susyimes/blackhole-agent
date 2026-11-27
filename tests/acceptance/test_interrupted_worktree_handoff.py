"""Run one real mission turn per case with offline kernel transports and a temporary Git workspace."""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from blackhole_agent.kernel_health import KernelHealth, save_kernel_health, trip_kernel
from blackhole_agent.unbound import KernelTurnResult, UnboundMission, run_unbound_turn, save_mission


def observe(root: Path, case: str) -> dict:
    work = root / "work"
    work.mkdir(parents=True)

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=work, text=True, stderr=subprocess.PIPE).strip()

    git("init", "-b", "main")
    (work / ".gitignore").write_text(".blackhole-agent/\n", encoding="utf-8")
    amounts = work / "amounts.txt"
    amounts.write_text("1\n", encoding="utf-8")
    soul = work / "soul.md"
    soul.write_text("Original turn instructions", encoding="utf-8")
    git("add", ".")
    git(
        "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgSign=false", "commit", "-m", "seed",
    )
    head = git("rev-parse", "HEAD")
    goal = "Reconcile the outstanding invoice."
    done = "Return the total of the recorded amounts."
    state_file = root / "mission" / "state.json"
    state = UnboundMission(
        schema_version=1, mission_id="invoice", created_at="", updated_at="", repo_path=str(work),
        workspace_path=str(work), branch="main", target_branch="main", goal=goal, done_when=done,
        stage="execution", selection_checked=True, kernel="cursor", base_head=head, last_milestone_head=head,
        session_id="original-session", session_started=True, decision_only_resume=case == "cooldown",
    )
    save_mission(state_file, state)
    # This fixture has no old checkouts to reclaim before the turn.
    budget = work / ".blackhole-agent" / "unbound" / "storage-budget.json"
    budget.parent.mkdir(parents=True)
    budget.write_text('{"worktree_reclaim": {"reclaimed": []}}', encoding="utf-8")

    def leave_work():
        amounts.write_text("17\n25\n", encoding="utf-8")
        git("add", "amounts.txt")
        parent = work / "tests" / "acceptance"
        parent.mkdir(parents=True)
        pending = Path(tempfile.mkdtemp(prefix="invoice-", dir=parent)) / "total.py"
        pending.write_text(
            "from pathlib import Path\nprint(sum(map(int, Path('amounts.txt').read_text().splitlines())))\n",
            encoding="utf-8",
        )
        if case == "crowded":
            for prefix in ("before", "z-after"):
                for n in range(40):
                    (work / f"{prefix}-{n:02}-{'x' * 68}").touch()

    if case == "cooldown":
        leave_work()
        health = KernelHealth()
        trip_kernel(health, "cursor", "quota_exhausted", "offline fixture")
        save_kernel_health(work, health)

    launches = []

    def transport(active, task, turn_dir, **kwargs):
        short = "Do not call tools." in task
        launches.append([active.kernel, active.session_id, short])
        if active.kernel == "cursor":
            if len(launches) == 1:
                leave_work()
                soul.write_text("Instructions for next turn", encoding="utf-8")
            error = "RetriableError: Agent turn stopped after repeated resume attempts made no progress"
            if case == "truncated" and len(launches) == 1:
                error = "response truncated by max_tokens (max_tokens_truncation)"
            kernel_dir = turn_dir / "kernel"
            kernel_dir.mkdir(exist_ok=True)
            failure = {
                "returncode": 1, "stderr_tail": error, "session_id": active.session_id, "decision_final": False,
            }
            (kernel_dir / "latest-cursor-run.json").write_text(json.dumps(failure), encoding="utf-8")
            raise RuntimeError(error)

        listing = task
        status_file = re.search(r"^Full Git status file: (.+)$", task, re.MULTILINE)
        if status_file:
            saved = Path(status_file[1])
            if saved.parent == turn_dir:
                listing = json.loads(saved.read_text(encoding="utf-8"))["status"]
        probe_name = r"tests/acceptance/invoice-[\w-]+/total\.py"
        path = re.search(probe_name, listing)
        total = None
        if path and not short:
            result = subprocess.run(
                [sys.executable, "-I", path.group()], cwd=active.workspace_path,
                text=True, capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                total = result.stdout.strip()
        receipt = {
            "total": total,
            "contract": goal in task and done in task,
            "workspace": "amounts.txt" in task and "(clean)" not in task,
            "turn_instructions": "Original turn instructions" in task and "Instructions for next turn" not in task,
            "decision_schema": '"acceptance_probe"' in task,
            "used_full_listing": bool(path and not re.search(probe_name, task)),
        }
        message = json.dumps({"status": "continue", "summary": json.dumps(receipt)})
        return KernelTurnResult(active.kernel, message, "new-session", (), "")

    with patch("blackhole_agent.kernel_salvage.installed_first_class_kernels", return_value={"cursor", "codex"}):
        record = run_unbound_turn(state_file, kernel_runner=transport)
    return {
        "launches": launches, "receipt": json.loads(record["summary"]), "source": record["kernel_salvage"]["source"],
        "staged": git("diff", "--cached", "--name-only"), "turn": record["iteration"],
    }


def main():
    with tempfile.TemporaryDirectory() as directory:
        cases = ("interrupted", "truncated", "cooldown", "crowded")
        observed = {case: observe(Path(directory) / case, case) for case in cases}
    initial = ["cursor", "original-session", False]
    resumed = ["cursor", "original-session", True]
    fresh = ["codex", "", False]
    routes = {
        "interrupted": [initial, fresh], "truncated": [initial, resumed, fresh],
        "cooldown": [fresh], "crowded": [initial, fresh],
    }
    passed = all(
        row["launches"] == routes[case] and row["receipt"]["total"] == "42"
        and all(row["receipt"][k] for k in ("contract", "workspace", "turn_instructions", "decision_schema"))
        and row["receipt"]["used_full_listing"] == (case == "crowded")
        and row["staged"] == "amounts.txt" and row["turn"] == 1
        and row["source"] == ("kernel" if case == "cooldown" else "failover")
        for case, row in observed.items()
    )
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
