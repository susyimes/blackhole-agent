"""Unit tests for multi-round durable loop engine (hermetic)."""

from __future__ import annotations

from blackhole_agent import upstream_epoch as ue
from blackhole_agent import upstream_loop_engine as le
from blackhole_agent import upstream_program as up
from blackhole_agent import upstream_succession as us


def test_loop_dialects_registered() -> None:
    assert le.list_loop_dialects() == ["program", "succession", "epoch"]
    for name in le.list_loop_dialects():
        d = le.get_loop_dialect(name)
        assert d.name == name
        assert d.child
        assert d.child_plural


def test_succession_and_epoch_owned_by_engine() -> None:
    assert us.LOOP_ENGINE is True
    assert ue.LOOP_ENGINE is True
    assert up.LOOP_ENGINE_NESTED is True


def test_builtin_loop_engine_proof_green() -> None:
    result = le.builtin_loop_engine_proof()
    assert result["ok"], result
    assert result["dialect_count"] == 3
    assert result["succession_loop_engine"]
    assert result["epoch_loop_engine"]
    assert result["program_loop_engine_nested"] or result["program_loop_engine"]
    assert result["live_proofs_ok"]
    assert result["seal_verified"]
    assert result["tamper_detected"]
    assert result.get("done_when_met")
    assert not result["used_skill_route_discovery"]
