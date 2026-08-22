from pathlib import Path

from blackhole_agent.experience_fuel import harvest_experience, leftover_next_step
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact
from blackhole_agent.kernel_succession import (
    builtin_kernel_succession_proof,
    cheap_rotation_exhausted,
    is_succession_capability,
    select_succession_step,
)
from blackhole_agent.local_capability_kernel import is_safe_local_capability
from blackhole_agent.local_mission_sovereignty import LocalCampaign
from blackhole_agent.pattern_register import classify_unbound_turn


def test_harvested_402_is_still_quota_exhausted():
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    assert failure.class_id == "quota_exhausted"
    assert failure.retryable is False


def test_leftover_next_step_keeps_follow_on_and_drops_generic():
    leftover = leftover_next_step(
        "Optional follow-on is a bounded mission-plane program on local "
        "ticks once cheap-anchor rotation is exhausted."
    )
    assert "cheap-anchor" in leftover
    assert leftover_next_step("None. Mission complete.") == ""
    assert leftover_next_step("Resume on a healthy first-class kernel when a breaker closes.") == ""
    later = leftover_next_step(
        "None. Mission complete. Optional later work is live-registry catalog "
        "refresh so application-growth can forage from a live npm/pypi search "
        "instead of a frozen catalog."
    )
    assert later.startswith("Optional later work")
    assert "live-registry catalog refresh" in later


def test_salvage_continue_is_not_kernel_turn_failed():
    events = classify_unbound_turn(
        {
            "iteration": 13,
            "effective_status": "continue",
            "requested_status": "continue",
            "summary": "local campaign advanced",
            "kernel_salvage": {"ok": True, "class_id": "quota_exhausted", "source": "failover"},
        }
    )
    assert not any(item.get("class_id") == "kernel_turn_failed" for item in events)


def test_harvest_sees_leftover_and_salvage(tmp_path: Path):
    mission = tmp_path / ".blackhole-agent" / "unbound" / "missions" / "prior"
    mission.mkdir(parents=True)
    (mission / "state.json").write_text(
        (
            '{"mission_id":"prior","status":"complete","next_step":'
            '"Optional follow-on is a bounded mission-plane program on local '
            'ticks once cheap-anchor rotation is exhausted.",'
            '"last_error":"","recent_turns":[{"iteration":1,'
            '"effective_status":"complete","kernel_salvage":'
            '{"class_id":"quota_exhausted","source":"failover"}}]}'
        ),
        encoding="utf-8",
    )
    fuel = harvest_experience(tmp_path, limit=5)
    assert any(item.class_id == "mission_leftover" for item in fuel.candidates)
    assert any(item.class_id == "quota_exhausted" for item in fuel.candidates)


def test_builtin_proof_escalates_past_cheap_rotation():
    report = builtin_kernel_succession_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_succession"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["local_tick_escalates_after_cheap"]
    assert report["checks"]["recovered_resume_attaches_succession"]
    assert report["checks"]["execute_402_then_succession"]
    assert report["checks"]["leftover_next_step_harvested"]
    assert LOCAL_KERNEL == "local"
    assert callable(is_succession_capability)
    assert callable(is_safe_local_capability)
    assert callable(select_succession_step)
    assert callable(cheap_rotation_exhausted)
    assert LocalCampaign(tick_count=0).completed_ids == []
