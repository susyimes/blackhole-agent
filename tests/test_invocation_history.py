"""Unit tests for invocation evidence journaling and evidence-ranked planning."""

from __future__ import annotations

import io
import json
from pathlib import Path

from blackhole_agent.capability_service import (
    plan_goal_program,
    plan_goal_programs,
    solve_goal_request,
)
from blackhole_agent.invocation_history import (
    journal_path,
    load_capability_stats,
    load_records,
    plan_evidence,
    program_rank_key,
    rank_programs,
    record_invocation,
)
from tests.acceptance.test_evidence_ranked_solve import FAST_ID, FLAKY_REVERSER, REVERSER, SLOW_ID, fixture


def _two_route_root(tmp_path: Path, fast_source: str = REVERSER) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    fixture(root, fast_source)
    return root, SLOW_ID, FAST_ID


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
    journal = journal_path(tmp_path)
    journal.parent.mkdir(parents=True)
    journal.write_text(
        'not json\n{"capability_id": "c", "ok": true, "duration_ms": 5}\n{"bad": 1}\n',
        encoding="utf-8",
    )
    records = load_records(tmp_path)
    assert len(records) == 1
    assert records[0]["capability_id"] == "c"


def test_record_limit_reads_tail_only(tmp_path: Path, monkeypatch) -> None:
    journal = journal_path(tmp_path)
    journal.parent.mkdir()
    old = b'{"capability_id":"old","duration_ms":1,"ok":true}\n'
    journal.write_bytes(old * ((16 << 20) // len(old)))
    for index in range(10):
        record_invocation(tmp_path, f"capability.{index % 2}", duration_ms=1.0, ok=True)

    class MeteredFile(io.FileIO):
        bytes_read = 0

        def read(self, size=-1):
            data = super().read(size)
            self.bytes_read += len(data)
            return data

    with MeteredFile(journal) as stream:
        monkeypatch.setattr(Path, "open", lambda path, mode: stream)
        records = load_records(tmp_path, record_limit=4)
        assert 0 < stream.bytes_read <= 128 * 1024
    assert [r["capability_id"] for r in records] == [
        "capability.0", "capability.1", "capability.0", "capability.1",
    ]


def test_legacy_records_span_blocks_and_survive_an_unterminated_last_line(tmp_path: Path) -> None:
    journal = journal_path(tmp_path)
    journal.parent.mkdir()
    large = {"capability_id": "古", "duration_ms": 2, "ok": False, "error": "雑" * 70000}
    last = {"capability_id": "newer", "duration_ms": 3, "ok": True}
    invalid = [dict(last, duration_ms=value) for value in [True, -1, float("nan"), 10 ** 310]]
    data = b"\r\n".join(json.dumps(r, ensure_ascii=False).encode() for r in [large, *invalid, last])
    journal.write_bytes(b"unreadable\xff\r" + data)
    assert load_records(tmp_path, record_limit=2) == [large, last]
    record_invocation(tmp_path, "latest", duration_ms=4, ok=True)
    assert journal.read_bytes().startswith(b"unreadable\xff\r" + data + b"\n")
    assert [r["capability_id"] for r in load_records(tmp_path)] == ["古", "newer", "latest"]


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


def test_mid_execution_failure_falls_back_to_next_ranked_program(tmp_path: Path) -> None:
    root, slow, fast = _two_route_root(tmp_path, FLAKY_REVERSER)
    for _ in range(3):
        record_invocation(root, slow, duration_ms=800.0, ok=True)
        record_invocation(root, fast, duration_ms=30.0, ok=True)
    result = solve_goal_request(root, {"raw_text": "failme"}, ["goal_text"])
    assert result["solved"] is True
    assert result["plan"] == [slow]
    assert result["outcome"] == {"goal_text": "emliaf"}
    assert result["fallbacks"] == [
        {"capability_id": fast, "error": result["fallbacks"][0]["error"], "replaced_by": [slow]}
    ]
    assert "exited 3" in result["fallbacks"][0]["error"]
    # The failure itself was journaled, penalizing the route in future rankings.
    stats = load_capability_stats(root)
    assert stats[fast]["failures"] == 1


def test_failed_capability_is_never_retried_within_one_request(tmp_path: Path) -> None:
    root, slow, fast = _two_route_root(tmp_path, FLAKY_REVERSER)
    # Make the slow route fail too: no viable program remains after the
    # fast route's failure, so the original error propagates honestly.
    (root / "capabilities" / "absorbed" / "a-slow-route" / "tool.py").write_text(
        "import sys\nsys.exit(3)\n", encoding="utf-8"
    )
    record_invocation(root, fast, duration_ms=30.0, ok=True)
    record_invocation(root, slow, duration_ms=800.0, ok=True)
    import pytest

    from blackhole_agent.capability_service import InvocationError

    with pytest.raises(InvocationError):
        solve_goal_request(root, {"raw_text": "failme"}, ["goal_text"])
    stats = load_capability_stats(root)
    # Fast failed once (not retried); slow failed once as the fallback attempt.
    assert stats[fast]["failures"] == 1
    assert stats[slow]["failures"] == 1


def test_successful_solve_reports_empty_fallbacks(tmp_path: Path) -> None:
    root, slow, fast = _two_route_root(tmp_path)
    result = solve_goal_request(root, {"raw_text": "unbound"}, ["goal_text"])
    assert result["fallbacks"] == []
