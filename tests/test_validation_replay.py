from pathlib import Path

from blackhole_agent.kernel_class_closure import CLASS_CLOSURE_REQUIREMENTS, class_is_closed
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.pattern_register import classify_unbound_turn
from blackhole_agent.unbound import TurnDecision, evaluate_milestone, reproduce_validation
from blackhole_agent.validation_replay import (
    VALIDATION_REPLAY_FAILED,
    VALIDATION_REPLAY_RESILIENCE_ID,
    _LATER_OCCURRENCE_PROOF,
    builtin_validation_replay_resilience_proof,
    derived_witness_command,
    is_growth_proof_command,
    poison_unbounded_proof_runner,
    trusted_witness_command,
)


def test_builtin_proof_closes_validation_replay_failed_class():
    report = builtin_validation_replay_resilience_proof()
    assert report["ok"] is True, report.get("failed")
    assert report["action"] == "validation_replay_resilience"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["later_extract_witness_replays"]
    assert report["checks"]["hang_without_witness_still_times_out"]
    assert report["checks"]["unbound_witness_cannot_launder_hang"]
    assert report["checks"]["proved_closer_drops_forced_mission"]
    assert report["checks"]["repair_is_not_named_instance_patch"]
    assert VALIDATION_REPLAY_FAILED in CLASS_CLOSURE_REQUIREMENTS
    assert VALIDATION_REPLAY_RESILIENCE_ID in LOCAL_DENYLIST
    assert class_is_closed("unknown-class", Path(".")) is False


def test_growth_proof_rewrites_to_verify_without_naming_one_depth():
    later = derived_witness_command(_LATER_OCCURRENCE_PROOF)
    assert is_growth_proof_command(_LATER_OCCURRENCE_PROOF)
    assert later.endswith("python-nonuple-nested-instance-verify")
    assert not is_growth_proof_command(later)
    assert derived_witness_command('python -c "pass"') == ""
    assert trusted_witness_command(
        {"command": _LATER_OCCURRENCE_PROOF, "exit_code": 0, "witness_command": 'python -c "pass"'}
    ) == later


def test_reproduce_validation_prefers_derived_witness(tmp_path):
    runner = poison_unbounded_proof_runner()
    witnessed = reproduce_validation(
        tmp_path,
        ({"command": _LATER_OCCURRENCE_PROOF, "exit_code": 0, "summary": "later"},),
        timeout=1,
        command_runner=runner,
    )
    hang = reproduce_validation(
        tmp_path,
        ({"command": 'python -c "import time; time.sleep(30)"', "exit_code": 0, "summary": "hang"},),
        timeout=1,
        command_runner=runner,
    )
    assert witnessed[0]["ok"] is True
    assert witnessed[0]["witnessed"] is True
    assert hang[0]["ok"] is False
    assert hang[0]["timed_out"] is True


def test_milestone_gate_accepts_witnessed_growth_proof(tmp_path):
    runner = poison_unbounded_proof_runner()
    accepted = evaluate_milestone(
        TurnDecision.from_payload(
            {
                "status": "milestone",
                "summary": "witnessed",
                "strategy": "class-level",
                "next_step": "none",
                "capability_delta": "Replay uses a bounded verify witness.",
                "outcome_evidence": ["src/blackhole_agent/validation_replay.py"],
                "validation": [{"command": _LATER_OCCURRENCE_PROOF, "exit_code": 0, "summary": "ok"}],
                "done_when_met": False,
                "commit_message": "",
                "mission_goal": "",
                "done_when": "",
            }
        ),
        changed_paths=["src/blackhole_agent/validation_replay.py"],
        workspace=tmp_path,
        command_runner=runner,
        replay_timeout=1,
    )
    rejected = evaluate_milestone(
        TurnDecision.from_payload(
            {
                "status": "milestone",
                "summary": "hang",
                "strategy": "class-level",
                "next_step": "none",
                "capability_delta": "Hangs still fail closed.",
                "outcome_evidence": ["src/blackhole_agent/validation_replay.py"],
                "validation": [
                    {"command": 'python -c "import time; time.sleep(30)"', "exit_code": 0, "summary": "hang"}
                ],
                "done_when_met": False,
                "commit_message": "",
                "mission_goal": "",
                "done_when": "",
            }
        ),
        changed_paths=["src/blackhole_agent/validation_replay.py"],
        workspace=tmp_path,
        command_runner=runner,
        replay_timeout=1,
    )
    assert accepted.accepted is True
    assert rejected.accepted is False
    assert any("timed out" in reason for reason in rejected.reasons)


def test_classify_timeout_stays_validation_replay_failed():
    events = classify_unbound_turn(
        {
            "iteration": 286,
            "milestone_gate": {
                "requested": True,
                "accepted": False,
                "reasons": [
                    "validation replay timed out: uv run python -m "
                    "blackhole_agent.capability_application_growth "
                    "python-nonuple-nested-instance-proof"
                ],
            },
        }
    )
    assert events[0]["class_id"] == VALIDATION_REPLAY_FAILED


def test_leftover_binds_validation_replay_resilience():
    leftover = (
        "Repair validation replay timeout: a true capability proof is rejected "
        "because controller replay times out on a long command."
    )
    assert leftover_marker_ids(leftover) == (VALIDATION_REPLAY_RESILIENCE_ID,)
