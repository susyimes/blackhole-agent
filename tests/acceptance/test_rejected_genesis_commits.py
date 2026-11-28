# replay-input: capabilities/ledger.json
# replay-input: tests/fixtures/proposal_replay/benign_agent_harness.json
"""Observe a rejected turn and its successor through real Git history and the milestone runner."""

import json
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.unbound import KernelTurnResult, UnboundMission, run_unbound_turn, save_mission


def observe(root: Path) -> dict:
    repo, work, state_path = root / "controller", root / "work", root / "mission/state.json"
    repo.mkdir()

    def git(*args, cwd=work):
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, encoding="utf-8", stderr=subprocess.PIPE).strip()

    git("init", "-qb", "main", cwd=repo)
    for key, value in (("user.name", "Probe"), ("user.email", "probe@example.invalid"), ("commit.gpgSign", "false")):
        git("config", key, value, cwd=repo)
    (repo / "src").mkdir()
    (repo / "src/totals.py").write_text("def total(values):\n    return 0\n", encoding="utf-8")
    probe = "tests/acceptance/test_total.py"
    (repo / probe).parent.mkdir(parents=True)
    (repo / probe).write_text(
        "import json\nfrom totals import total\nvalue = total([7, -3, 2])\n"
        "print(json.dumps({'passed': value == 6, 'observed': {'sum': value}}))\n", encoding="utf-8",
    )
    (repo / ".gitignore").write_text(".blackhole-agent/\nlocal.note\n", encoding="utf-8")
    git("add", ".", cwd=repo)
    git("commit", "-qm", "Seed total calculator", cwd=repo)
    base = git("rev-parse", "HEAD", cwd=repo)
    git("worktree", "add", "-qb", "mission", str(work), base, cwd=repo)
    note = work / "operator.note"
    note.write_bytes(b"keep this commit")
    git("add", note.name)
    git("commit", "-qm", "Operator handoff")
    entry = git("rev-parse", "HEAD")
    (work / "local.note").write_bytes(b"private\x00bytes")
    save_mission(state_path, UnboundMission(
        schema_version=1, mission_id="rejection", created_at="", updated_at="", repo_path=str(repo),
        workspace_path=str(work), branch="mission", target_branch="main", base_head=base, last_milestone_head=base,
    ))
    seen = {}

    def kernel(state, prompt, turn_dir, **kwargs):
        if state.iteration == 0:
            draft = work / "draft.txt"
            draft.write_text("first draft", encoding="utf-8")
            git("add", draft.name)
            git("commit", "-qm", "First draft")
            draft.write_text("second draft", encoding="utf-8")
            (work / ".gitignore").write_text(".blackhole-agent/\n", encoding="utf-8")
            git("add", "local.note")
            git("rm", "-q", note.name)
            git("commit", "-qam", "Second draft")
            seen["tip"] = git("rev-parse", "HEAD")
            (work / "loose.txt").write_bytes(b"uncommitted")
            decision = dict(status="continue", mission_goal="none", done_when="none")
        else:
            seen["next_entry"] = git("rev-parse", "HEAD")
            (work / "src/totals.py").write_text("def total(values):\n    return sum(values)\n", encoding="utf-8")
            decision = dict(
                status="milestone", mission_goal="Repair signed batch totals in the calculator.",
                done_when="Summing seven, minus three and two returns six.", capability_delta="Sum signed inputs.",
                outcome_evidence=["The calculator returns 6."], acceptance_probe=probe,
                validation=[{"command": "git diff --check", "exit_code": 0}],
            )
        return KernelTurnResult(state.kernel, json.dumps(decision), "", (), "")

    first = run_unbound_turn(state_path, kernel_runner=kernel)
    ref = (first.get("rejected_workspace_restore") or {}).get("recovery_ref")
    restored = git("rev-parse", "HEAD") == entry and git("write-tree") == git("rev-parse", f"{entry}^{{tree}}")
    drafts = [git("show", f"{rev}:draft.txt") for rev in (ref + "^", ref)] if ref else []
    clean = not git("status", "--porcelain", "--untracked-files=all")
    second = run_unbound_turn(state_path, kernel_runner=kernel)
    observed = {
        "selection_rejected": first["selection_gate"]["accepted"] is False,
        "entry_restored": restored and clean and seen["next_entry"] == entry,
        "recovered_drafts": drafts, "tip_recoverable": bool(ref) and git("rev-parse", ref) == seen["tip"],
        "next_status": second["effective_status"], "next_parent_is_entry": git("rev-parse", "HEAD^") == entry,
        "changed_since_entry": git("diff", "--name-only", entry, "HEAD").splitlines(),
        "operator_note_kept": note.is_file() and note.read_bytes() == b"keep this commit",
        "ignored_bytes_kept": (work / "local.note").is_file() and (work / "local.note").read_bytes() == b"private\x00bytes",
        "main_untouched": git("rev-parse", "main") == base,
    }
    if second["effective_status"] != "milestone":
        observed["successor_refusal"] = second["milestone_gate"]["reasons"]
    passed = all(observed[key] for key in ("selection_rejected", "entry_restored", "tip_recoverable",
                 "next_parent_is_entry", "operator_note_kept", "ignored_bytes_kept", "main_untouched"))
    return {"passed": passed and drafts == ["first draft", "second draft"] and second["effective_status"] == "milestone"
            and observed["changed_since_entry"] == ["src/totals.py"], "observed": observed}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="bh-rejected-commits-") as directory:
        try:
            outcome = observe(Path(directory))
        except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
            outcome = {"passed": False, "observed": {"error": str(error)}}
        print(json.dumps(outcome))
