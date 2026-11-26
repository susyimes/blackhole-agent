import subprocess
from pathlib import Path

import pytest

from blackhole_agent.kernel_class_closure import CLASS_CLOSURE_REQUIREMENTS, class_is_closed
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.milestone_commit import (
    MILESTONE_COMMIT_RESILIENCE_ID,
    MILESTONE_REJECTED,
    _init_repo,
    builtin_milestone_commit_resilience_proof,
    is_regenerable_scratch,
    is_tree_walking_git_add,
    is_unreadable_tree_error,
    poison_tree_walking_git_add,
    stage_milestone_paths,
)
from blackhole_agent.pattern_register import classify_unbound_turn
from blackhole_agent.unbound import TurnDecision, commit_milestone, git_head


def test_builtin_proof_closes_milestone_rejected_class():
    report = builtin_milestone_commit_resilience_proof()
    assert report["ok"] is True, report.get("failed")
    assert report["action"] == "milestone_commit_resilience"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["commits_behavior_while_add_all_is_poisoned"]
    assert report["checks"]["later_extract_still_on_disk"]
    assert report["checks"]["instance_airflow_tree_was_never_required"]
    assert report["checks"]["repeating_airflow_delete_would_not_apply"]
    assert report["checks"]["proved_closer_drops_forced_mission"]
    assert MILESTONE_REJECTED in CLASS_CLOSURE_REQUIREMENTS
    assert MILESTONE_COMMIT_RESILIENCE_ID in LOCAL_DENYLIST
    assert class_is_closed("unknown-class", Path(".")) is False


def test_tree_walking_add_is_the_recorded_class():
    assert is_tree_walking_git_add(["git", "add", "-A"])
    assert is_tree_walking_git_add(["git", "add", "--all"])
    assert is_tree_walking_git_add(["git", "add", "."])
    assert not is_tree_walking_git_add(["git", "add", "--", "src/capability.py"])
    assert is_unreadable_tree_error(
        "git add -A failed: warning: could not open directory 'x': Filename too long"
    )
    assert is_regenerable_scratch(
        "artifacts/capability-foraging/extracted/other-sdist-not-airflow/leaf.txt"
    )
    assert not is_regenerable_scratch("src/blackhole_agent/unbound.py")


def test_classify_longpath_commit_failure_stays_milestone_rejected():
    events = classify_unbound_turn(
        {
            "iteration": 287,
            "milestone_gate": {
                "requested": True,
                "accepted": False,
                "reasons": [
                    "milestone commit failed: git add -A failed: warning: could not "
                    "open directory 'artifacts/capability-foraging/extracted/"
                    "other-sdist-not-airflow/': Filename too long"
                ],
            },
        }
    )

    assert events[0]["class_id"] == "milestone_rejected"


def test_commit_milestone_survives_poisoned_git_add_all(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    from blackhole_agent.milestone_commit import _write_later_occurrence_scratch

    _init_repo(repo)
    leaf = _write_later_occurrence_scratch(repo)
    (repo / "src" / "capability.py").write_text("print('ok')\n", encoding="utf-8")
    decision = TurnDecision.from_payload({"status": "milestone", "commit_message": "Add executable capability path"})
    before = git_head(repo)
    sha = commit_milestone(repo, decision, 1, command_runner=poison_tree_walking_git_add())

    assert sha != before
    assert leaf.is_file()
    assert not (repo / "artifacts" / "tmp-infer-airflow-amazon").exists()


def test_unreadable_path_fallback_keeps_literal_selection(tmp_path):
    _init_repo(tmp_path)
    selected, neighbor = "src/part[1].py", "src/part1.py"
    (tmp_path / "docs").mkdir()
    for path in (selected, neighbor, "docs/long.txt", "src/long.py"):
        (tmp_path / path).write_bytes(b"keep")

    def unreadable(command, **kwargs):
        paths = (kwargs.get("input") or b"").split(b"\0")
        if b"docs/long.txt" in paths or b"src/long.py" in paths:
            return subprocess.CompletedProcess(command, 128, b"", b"Filename too long")
        return subprocess.run(command, **kwargs)

    result = stage_milestone_paths(tmp_path, [selected, "docs/long.txt"], command_runner=unreadable)
    assert result == {"staged": [selected], "skipped": ["docs/long.txt"]}
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only", "-z"], cwd=tmp_path)
    assert staged == selected.encode() + b"\0"
    with pytest.raises(RuntimeError, match="Filename too long"):
        stage_milestone_paths(tmp_path, ["src/long.py"], command_runner=unreadable)
