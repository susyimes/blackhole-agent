from pathlib import Path

from blackhole_agent.pattern_register import (
    PatternRegister,
    builtin_pattern_register,
    classify_supervisor_pass,
    classify_unbound_turn,
    ingest_supervisor_pass,
    ingest_unbound_turn,
    load_register,
    maybe_resolve_from_goal,
    record_occurrence,
    required_pattern_mission,
    resolve_class,
)
from blackhole_agent.unbound import create_mission


def test_three_recurrences_force_the_next_mission():
    register = PatternRegister(recurrence_threshold=3)
    for index in range(2):
        record_occurrence(register, "health_check_failed", source="test", summary=f"n={index}")
    assert required_pattern_mission(Path("."), register=register) is None

    record_occurrence(register, "health_check_failed", source="test", summary="n=2")
    forced = required_pattern_mission(Path("."), register=register)

    assert forced is not None
    assert forced["class_id"] == "health_check_failed"
    assert "structural fix" in forced["goal"]
    assert register.classes["health_check_failed"].status == "forced"


def test_resolve_clears_force_until_the_class_recurs_again():
    register = PatternRegister(recurrence_threshold=2)
    record_occurrence(register, "kernel_turn_failed", source="test", summary="a")
    record_occurrence(register, "kernel_turn_failed", source="test", summary="b")
    resolve_class(register, "kernel_turn_failed", structural_fix="harden decision parsing")

    assert required_pattern_mission(Path("."), register=register) is None
    assert register.classes["kernel_turn_failed"].open_count == 0
    assert register.classes["kernel_turn_failed"].status == "resolved"

    record_occurrence(register, "kernel_turn_failed", source="test", summary="c")
    assert register.classes["kernel_turn_failed"].status == "open"
    record_occurrence(register, "kernel_turn_failed", source="test", summary="d")
    assert register.classes["kernel_turn_failed"].status == "forced"


def test_classify_supervisor_pass_maps_health_and_protected_paths():
    health = classify_supervisor_pass(
        {
            "pass_id": "p1",
            "returncode": 0,
            "promotion_result": {
                "attempted": True,
                "promoted": False,
                "health_checks": [{"returncode": 7}],
            },
        }
    )
    protected = classify_supervisor_pass(
        {
            "pass_id": "p2",
            "returncode": 0,
            "promotion_result": {
                "attempted": True,
                "promoted": False,
                "protected_paths_blocked": True,
                "protected_paths_touched": ["src/blackhole_agent/supervisor.py"],
            },
        }
    )

    assert health[0]["class_id"] == "health_check_failed"
    assert protected[0]["class_id"] == "protected_path_blocked"


def test_classify_supervisor_pass_treats_blocked_without_touched_paths_as_refusal():
    events = classify_supervisor_pass(
        {
            "pass_id": "p3",
            "returncode": 0,
            "promotion_result": {
                "attempted": True,
                "promoted": False,
                "protected_paths_blocked": True,
                "protected_paths_touched": [],
            },
        }
    )

    assert events[0]["class_id"] == "promotion_refused"


def test_classify_unbound_turn_maps_paperwork_and_kernel_errors():
    paperwork = classify_unbound_turn(
        {
            "iteration": 2,
            "milestone_gate": {
                "requested": True,
                "accepted": False,
                "reasons": ["changes are limited to docs, tests, artifacts, or controller state"],
            },
        }
    )
    kernel = classify_unbound_turn({"iteration": 1, "effective_status": "error", "error": "no json"})

    assert paperwork[0]["class_id"] == "paperwork_milestone"
    assert kernel[0]["class_id"] == "kernel_turn_failed"

    longpath = classify_unbound_turn(
        {
            "iteration": 288,
            "milestone_gate": {
                "requested": True,
                "accepted": False,
                "reasons": [
                    "milestone commit failed: git add -A failed: warning: could not "
                    "open directory 'artifacts/tmp-infer-airflow-amazon/': Filename too long"
                ],
            },
        }
    )
    assert longpath[0]["class_id"] == "milestone_rejected"


def test_ingest_and_forced_mission_persist(tmp_path):
    ingest_supervisor_pass(
        tmp_path,
        {
            "pass_id": "p1",
            "returncode": 3,
            "stderr_tail": "child failed",
        },
    )
    ingest_supervisor_pass(
        tmp_path,
        {
            "pass_id": "p2",
            "returncode": 3,
            "stderr_tail": "child failed again",
        },
    )
    ingest_supervisor_pass(
        tmp_path,
        {
            "pass_id": "p3",
            "returncode": 3,
            "stderr_tail": "child failed a third time",
        },
    )
    register = load_register(tmp_path)
    forced = required_pattern_mission(tmp_path)

    assert register.classes["supervisor_pass_failed"].open_count == 3
    assert forced is not None
    assert forced["class_id"] == "supervisor_pass_failed"
    assert maybe_resolve_from_goal(tmp_path, forced["goal"], structural_fix="fixed the child class")
    assert required_pattern_mission(tmp_path) is None


def test_create_mission_adopts_forced_pattern_class(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    import subprocess

    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Blackhole Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "blackhole@example.invalid"], cwd=repo, check=True)
    (repo / "src").mkdir()
    (repo / "src" / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True, text=True)

    for index in range(3):
        ingest_unbound_turn(
            repo,
            {
                "iteration": index,
                "effective_status": "error",
                "error": f"kernel boom {index}",
            },
        )

    state_path = create_mission(repo_path=repo, worktree_parent=tmp_path / "worktrees")
    from blackhole_agent.unbound import load_mission

    state = load_mission(state_path)
    assert state.stage == "execution"
    assert "kernel_turn_failed" in state.goal
    assert "resolved" in state.done_when


def test_builtin_pattern_register_is_green():
    assert builtin_pattern_register()["ok"] is True
