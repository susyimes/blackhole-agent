import json
from pathlib import Path

import pytest

from blackhole_agent.experience_fuel import (
    builtin_experience_fuel,
    harvest_experience,
    leftover_next_step,
    merge_experience_into_proposals,
    render_experience_for_genesis,
)
from blackhole_agent.github_growth import build_self_evolution_plan
from blackhole_agent.pattern_register import ingest_supervisor_pass
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def _write_failed_pass(repo: Path) -> None:
    output = repo / ".blackhole-agent" / "supervisor"
    output.mkdir(parents=True)
    payload = {
        "pass_id": "20260817T010000Z",
        "returncode": 3,
        "stderr_tail": "kernel crashed",
        "finished_at": "2026-08-17T01:00:00Z",
    }
    (output / "latest-supervisor-pass.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    (output / "supervisor-pass-20260817T010000Z.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_harvest_reads_supervisor_failures(tmp_path):
    _write_failed_pass(tmp_path)

    fuel = harvest_experience(tmp_path)

    assert fuel.candidates
    assert any(item.class_id == "supervisor_pass_failed" for item in fuel.candidates)


def test_forced_class_becomes_the_first_proposal(tmp_path):
    for index in range(3):
        ingest_supervisor_pass(
            tmp_path,
            {"pass_id": f"p{index}", "returncode": 9, "stderr_tail": "health"},
        )
    merged = merge_experience_into_proposals(
        [{"proposal_id": "trend-1", "kind": "test", "summary": "borrow a trend"}],
        tmp_path,
    )

    assert merged[0]["proposal_source"] == "experience"
    assert merged[0]["experience_forced"] is True
    assert merged[0]["experience_class_id"] == "supervisor_pass_failed"


def test_genesis_prompt_includes_harvested_candidates(tmp_path):
    _write_failed_pass(tmp_path)
    block = render_experience_for_genesis(tmp_path)
    state = UnboundMission(
        schema_version=1,
        mission_id="mission-1",
        created_at="2026-08-17T00:00:00Z",
        updated_at="2026-08-17T00:00:00Z",
        repo_path=str(tmp_path),
        workspace_path=str(tmp_path),
        branch="unbound/test",
        target_branch="main",
        stage="genesis",
    )
    prompt = build_turn_prompt(
        state,
        {"head": "abc", "status": "", "diff_stat": "", "recent_commits": ""},
        state_path=tmp_path / "state.json",
    )

    assert "Operational experience" in block
    assert "supervisor_pass_failed" in block
    assert "Operational experience" in prompt
    assert "Prefer a harvested operational failure" in prompt


def test_self_evolution_plan_uses_experience_without_force(tmp_path):
    for index in range(3):
        ingest_supervisor_pass(
            tmp_path,
            {"pass_id": f"p{index}", "returncode": 4, "stderr_tail": "fail"},
        )
    empty = {
        "digest_id": "github-growth-empty",
        "generated_at": "2026-08-17T00:00:00Z",
        "proposals": [],
    }

    plan = build_self_evolution_plan(empty, repo_path=tmp_path)

    assert plan is not None
    assert "supervisor_pass_failed" in plan.task
    assert "Protected governance paths are off the automatic write path" in plan.task


def test_builtin_experience_fuel_is_green():
    assert builtin_experience_fuel()["ok"] is True


@pytest.mark.parametrize("notice", [
    "Mission complete; later genesis can take login-task repair if a registration goes missing or disabled.",
    "Mission complete. Later genesis may repair the cache if entries expire.",
    "None. Mission complete: later genesis could restore the worker if it disappears.",
    "MISSION COMPLETE; LATER GENESIS CAN repair the launcher IF it fails",
    "Mission complete;\n later genesis can repair the backup if\n it becomes unavailable.",
    "Controller records the milestone; later genesis can take capability.loop-login-stale (stale command/launcher pointing at a moved repo).",
    "Controller records the milestone. Later genesis may take capability.loop-login-stale (stale launcher pointing at a moved repo).",
    "None. Controller records the milestone: later genesis could take capability.loop-login-stale (moved repo).",
    "Mission contract met; later genesis can decide whether old inventoried orphans become adoptable or reclaimable with operator acknowledgment.",
    "None. Mission contract met: later genesis may decide whether the bundle is adoptable (pending operator acknowledgment).",
    "MISSION CONTRACT MET; LATER GENESIS COULD DECIDE WHETHER THE WORKER STAYS IF IT FAILS",
])
def test_completed_contingency_is_not_outstanding_work(notice):
    assert leftover_next_step(notice) == ""


@pytest.mark.parametrize("notice", [
    "Mission complete; later genesis can take login-task repair so missing registrations are restored.",
    "Mission complete. Later genesis can repair the registration because it is missing.",
    "Mission complete. Optional follow-on is joining STEWARDSHIP_STACK as one cross-engine charter.",
    "None. Mission complete. Optional later work is extending package.submodule support.",
    "Later genesis can repair the registration if it is missing.",
    "Mission complete; later genesis must repair the registration if it is missing.",
    "Mission complete; later genesis can repair the cache if it fails. Follow-on: fix the broken launcher now.",
    "Mission complete; later genesis can repair the cache if it fails; follow-on: fix the launcher now.",
    "Follow-on: fix the launcher now. Mission complete; later genesis can repair the cache if it fails.",
    "Mission complete. Later genesis can implement if-expression parsing for the planner.",
    "Controller records the milestone; later genesis can take login-task repair so stale registrations are re-pointed.",
    "Controller records the milestone; later genesis can take capability.loop-login-stale (moved repo). Follow-on: re-point the launcher now.",
    "Controller records the milestone; later genesis must take capability.loop-login-stale (moved repo).",
    "Mission contract met; later genesis can decide the roadmap.",
    "Mission contract met. Follow-on: repair the stale launcher registration now.",
    "Mission contract met; later genesis must decide whether the worker stays.",
])
def test_completion_does_not_hide_explicit_or_ambiguous_followup(notice):
    assert leftover_next_step(notice)
