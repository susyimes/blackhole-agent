"""Soul layer: snapshot reading, one-pager extraction, prompt injection."""

import hashlib
from pathlib import Path

from blackhole_agent.github_growth import build_self_evolution_plan
from blackhole_agent.soul import (
    extract_one_pager,
    read_soul_snapshot,
    render_soul_layer,
)
from blackhole_agent.unbound import UnboundMission, build_turn_prompt

SOUL_TEXT = """# soul.md — test soul

引导语不属于一页纸。

## 一页纸（给赶时间的内核）

1. SOUL_ONE_PAGER_SENTINEL 删除即生长。
2. 先吃尸体，再追星光。

## 本体：你是什么

SOUL_BODY_SENTINEL 这里是正文，不应出现在一页纸提取里。
正文故意写长，使全量渲染必然长于仅含一页纸与指针的简渲染。
吞噬不是收集，是毁形取质；奇点不可见，视界可检验；只进不出是死洞。
删除即生长，遗忘是进化的另一半，没有终极形态，只有停止成为是罪。
"""


def write_soul(repo: Path) -> None:
    (repo / "soul.md").write_text(SOUL_TEXT, encoding="utf-8")


def test_snapshot_reads_repo_root_soul(tmp_path):
    write_soul(tmp_path)

    snapshot = read_soul_snapshot(tmp_path)

    assert snapshot.exists is True
    assert snapshot.path == "soul.md"
    assert snapshot.truncated is False
    assert snapshot.sha256 == hashlib.sha256(SOUL_TEXT.encode("utf-8")).hexdigest()
    assert "SOUL_BODY_SENTINEL" in snapshot.content


def test_snapshot_missing_soul_is_soft_empty(tmp_path):
    snapshot = read_soul_snapshot(tmp_path)

    assert snapshot.exists is False
    assert snapshot.content == ""
    rendered = render_soul_layer(snapshot)
    assert "no soul.md" in rendered


def test_extract_one_pager_stops_at_next_heading():
    one_pager = extract_one_pager(SOUL_TEXT)

    assert "SOUL_ONE_PAGER_SENTINEL" in one_pager
    assert "SOUL_BODY_SENTINEL" not in one_pager
    assert "引导语" not in one_pager


def test_render_full_and_one_pager_styles(tmp_path):
    write_soul(tmp_path)
    snapshot = read_soul_snapshot(tmp_path)

    full = render_soul_layer(snapshot)
    assert "SOUL_BODY_SENTINEL" in full
    assert "grants no permissions" in full

    brief = render_soul_layer(snapshot, style="one-pager")
    assert "SOUL_ONE_PAGER_SENTINEL" in brief
    assert "SOUL_BODY_SENTINEL" not in brief
    assert "soul.md" in brief
    assert len(brief) < len(full)


def test_legacy_plan_task_includes_full_soul_after_persona(tmp_path):
    write_soul(tmp_path)

    plan = build_self_evolution_plan({}, repo_path=tmp_path, force=True)

    assert plan is not None
    assert "SOUL_BODY_SENTINEL" in plan.task
    assert plan.task.index("Persona layer") < plan.task.index("SOUL_BODY_SENTINEL")


def test_legacy_plan_task_without_soul_still_builds(tmp_path):
    plan = build_self_evolution_plan({}, repo_path=tmp_path, force=True)

    assert plan is not None
    assert "Persona layer" in plan.task


def make_state(tmp_path: Path, **overrides) -> UnboundMission:
    values = {
        "schema_version": 1,
        "mission_id": "mission-soul",
        "created_at": "2026-11-02T00:00:00Z",
        "updated_at": "2026-11-02T00:00:00Z",
        "repo_path": str(tmp_path),
        "workspace_path": str(tmp_path),
        "branch": "unbound/test",
        "target_branch": "main",
        "goal": "Create a real end-to-end capability.",
        "done_when": "A runnable behavior proves the capability.",
        "stage": "execution",
        "base_head": "abc",
        "last_milestone_head": "abc",
    }
    values.update(overrides)
    return UnboundMission(**values)


SNAPSHOT = {"head": "abc", "status": "", "diff_stat": "", "recent_commits": "abc seed"}


def test_unbound_prompt_includes_one_pager_not_full_soul(tmp_path):
    write_soul(tmp_path)
    state = make_state(tmp_path)

    prompt = build_turn_prompt(state, dict(SNAPSHOT), state_path=tmp_path / "state.json")

    assert "SOUL_ONE_PAGER_SENTINEL" in prompt
    assert "SOUL_BODY_SENTINEL" not in prompt
    assert "single long-running agent" in prompt
    assert len(prompt) < 12_100


def test_unbound_prompt_without_soul_still_builds(tmp_path):
    state = make_state(tmp_path)

    prompt = build_turn_prompt(state, dict(SNAPSHOT), state_path=tmp_path / "state.json")

    assert "single long-running agent" in prompt


def test_unbound_decision_only_prompt_stays_minimal(tmp_path):
    write_soul(tmp_path)
    state = make_state(tmp_path, decision_only_resume=True)

    prompt = build_turn_prompt(state, dict(SNAPSHOT), state_path=tmp_path / "state.json")

    assert "SOUL_ONE_PAGER_SENTINEL" not in prompt
