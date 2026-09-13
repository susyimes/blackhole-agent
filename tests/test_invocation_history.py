"""Unit tests for invocation evidence journaling and evidence-ranked planning."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_service import (
    plan_goal_program,
    plan_goal_programs,
    solve_goal_request,
)
from blackhole_agent.invocation_history import (
    load_capability_stats,
    load_records,
    plan_evidence,
    program_rank_key,
    rank_programs,
    record_invocation,
)

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'goal_text': state['raw_text'][::-1]}))\n"
)


def _write_tool(root: Path, slug: str) -> str:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(json.dumps({
        "schema_version": 1,
        "slug": slug,
        "name": f"fixture {slug}",
        "command": ["python", "tool.py"],
        "requires": ["raw_text"],
        "provides": ["goal_text"],
        "cases": [
            {"input": {"raw_text": "ab"}, "expect": {"goal_text": "ba"}},
            {"input": {"raw_text": "cd"}, "expect": {"goal_text": "dc"}},
        ],
    }), encoding="utf-8")
    return f"capability.absorbed-{slug}"


def _two_route_root(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    slow = _write_tool(root, "a-slow-route")
    fast = _write_tool(root, "z-fast-route")
    (root / "capabilities" / "ledger.json").write_text(json.dumps({
        "schema_version": 1,
        "capabilities": {
            cid: {
                "id": cid, "name": cid, "kind": "python",
                "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
                "proof_command": "python -c pass", "dependencies": [], "behavior_paths": [],
                "last_proof_exit_code": 0, "last_proved_at": "2026-01-01T00:00:00Z",
            }
            for cid in (slow, fast)
        },
    }), encoding="utf-8")
    return root, slow, fast


def test_record_and_aggregate_stats(tmp_path: Path) -> None:
    record_invocation(tmp_path, "capability.x", duration_ms=100.0, ok=True)
    record_invocation(tmp_path, "capability.x", duration_ms=300.0, ok=False, error="boom")
    record_invocation(tmp_path, "capability.y", duration_ms=50.0, ok=True)
    stats = load_capability_stats(tmp_path)
    assert stats["capability.x"]["invocations"] == 2
    assert stats["capability.x"]["failures"] == 1
    assert stats["capability.x"]["mean_duration_ms"] == 200.0
    assert stats["capability.x"]["last_ok"] is False
    assert stats["capability.y"]["failures"] == 0


def test_missing_and_corrupt_journal_is_empty_not_fatal(tmp_path: Path) -> None:
    assert load_records(tmp_path) == []
    assert load_capability_stats(tmp_path) == {}
    journal = tmp_path / ".blackhole-agent" / "invocation-history.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text(
        'not json\n{"capability_id": "c", "ok": true, "duration_ms": 5}\n{"bad": 1}\n',
        encoding="utf-8",
    )
    records = load_records(tmp_path)
    assert len(records) == 1
    assert records[0]["capability_id"] == "c"


def test_record_limit_reads_tail_only(tmp_path: Path) -> None:
    for index in range(10):
        record_invocation(tmp_path, f"capability.{index % 2}", duration_ms=1.0, ok=True)
    records = load_records(tmp_path, record_limit=4)
    assert len(records) == 4
    assert [r["capability_id"] for r in records] == [
        "capability.0", "capability.1", "capability.0", "capability.1",
    ]


def test_ranking_prefers_fewer_failures_then_speed_then_order() -> None:
    stats = {
        "a": {"invocations": 3, "failures": 1, "mean_duration_ms": 10.0},
        "b": {"invocations": 3, "failures": 0, "mean_duration_ms": 900.0},
        "c": {"invocations": 3, "failures": 0, "mean_duration_ms": 40.0},
    }
    ranked = rank_programs([["a"], ["b"], ["c"]], stats)
    assert ranked == [["c"], ["b"], ["a"]]
    # No evidence anywhere: degenerates to lexicographic order.
    assert rank_programs([["c"], ["a"], ["b"]], {}) == [["a"], ["b"], ["c"]]
    key = program_rank_key(["a"], stats)
    assert key[0] == 1 and key[3] == ("a",)


def test_plan_evidence_is_auditable() -> None:
    stats = {"x": {"invocations": 2, "failures": 0, "mean_duration_ms": 12.0}}
    evidence = plan_evidence([["x"], ["y"]], stats, selected=["x"])
    assert evidence["candidates_considered"] == 2
    assert evidence["selected"] == ["x"]
    slow_step = evidence["ranking"][1]["steps"][0]
    assert slow_step["capability_id"] == "y"
    assert slow_step["measured"] is False
    assert slow_step["recorded_invocations"] == 0


def test_plan_goal_programs_enumerates_all_minimal_routes(tmp_path: Path) -> None:
    root, slow, fast = _two_route_root(tmp_path)
    from blackhole_agent.capability_service import load_invocable_capabilities

    invocable = load_invocable_capabilities(root)
    candidates = plan_goal_programs(invocable, {"raw_text"}, ["goal_text"])
    assert candidates == [[slow], [fast]]
    assert plan_goal_program(invocable, {"raw_text"}, ["goal_text"]) == [slow]
    assert plan_goal_programs(invocable, {"raw_text"}, ["goal_text"], max_candidates=1) == [[slow]]
    assert plan_goal_programs(invocable, {"goal_text"}, ["goal_text"]) == []
    assert plan_goal_programs(invocable, set(), ["goal_text"]) is None


def test_solve_prefers_evidence_and_records_execution(tmp_path: Path) -> None:
    root, slow, fast = _two_route_root(tmp_path)
    for _ in range(3):
        record_invocation(root, slow, duration_ms=800.0, ok=True)
        record_invocation(root, fast, duration_ms=30.0, ok=True)
    result = solve_goal_request(root, {"raw_text": "unbound"}, ["goal_text"])
    assert result["solved"] is True
    assert result["plan"] == [fast]
    assert result["outcome"] == {"goal_text": "dnuobnu"}
    evidence = result["plan_evidence"]
    assert evidence["candidates_considered"] == 2
    assert evidence["ranking"][0]["program"] == [fast]
    # The solve itself appended fresh evidence for the executed capability.
    stats = load_capability_stats(root)
    assert stats[fast]["invocations"] == 4
    assert stats[slow]["invocations"] == 3


def test_solve_without_history_keeps_lexicographic_order(tmp_path: Path) -> None:
    root, slow, fast = _two_route_root(tmp_path)
    result = solve_goal_request(root, {"raw_text": "unbound"}, ["goal_text"])
    assert result["solved"] is True
    assert result["plan"] == [slow]
    assert result["plan_evidence"]["candidates_considered"] == 2
