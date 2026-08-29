from blackhole_agent.experience_fuel import leftover_next_step
from blackhole_agent.kernel_class_closure import (
    CLASS_CLOSURE_REQUIREMENTS,
    KERNEL_TURN_FAILED,
    builtin_kernel_class_closure_proof,
    class_is_closed,
)
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import HARVESTED_MISSION_PLANE_LEFTOVER
from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST


def test_harvested_402_is_still_quota_exhausted():
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    assert failure.class_id == "quota_exhausted"
    assert failure.retryable is False


def test_harvested_leftover_text_is_still_detected():
    leftover = leftover_next_step(HARVESTED_MISSION_PLANE_LEFTOVER)
    assert "mission-plane" in leftover
    assert leftover_next_step("None. Mission complete.") == ""


def test_builtin_proof_consumes_closed_402_class(tmp_path):
    report = builtin_kernel_class_closure_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_class_closure"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["open_class_is_harvested"]
    assert report["checks"]["proved_closers_drop_class"]
    assert report["checks"]["partial_closers_keep_class"]
    assert report["checks"]["unrelated_leftover_stays_open"]
    assert report["checks"]["harvest_false_keeps_402_default"]
    assert report["checks"]["preserves_operator_goal_when_closed"]
    assert class_is_closed("unknown-class", tmp_path) is False
    assert KERNEL_TURN_FAILED in CLASS_CLOSURE_REQUIREMENTS
    assert LOCAL_KERNEL == "local"
    assert "capability.kernel-class-closure" in LOCAL_DENYLIST
    assert report["checks"]["closes_genesis_selection_blocked"]
    assert report["checks"]["closes_validation_replay_failed"]
    assert report["checks"]["lineage_merge_imports_proofs"]
    assert report["checks"]["merged_ledger_closes_selection_class"]
