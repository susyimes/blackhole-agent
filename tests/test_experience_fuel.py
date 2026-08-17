import json
from pathlib import Path

from blackhole_agent.experience_fuel import (
    builtin_experience_fuel,
    harvest_experience,
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
