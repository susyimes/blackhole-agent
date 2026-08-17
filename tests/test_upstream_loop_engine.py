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


def test_full_leaf_stack_owned_by_engine() -> None:
    assert us.LOOP_ENGINE is True
    assert ue.LOOP_ENGINE is True
    assert up.LOOP_ENGINE is True
    assert up.LOOP_ENGINE_NESTED is True


def test_loop_dialect_vocabulary_is_hermetic() -> None:
    # The ledger-bound capstone proof left with the tower dialect: loop
    # dialects stay testable without asserting their own ledger registration.
    for name in le.list_loop_dialects():
        dialect = le.get_loop_dialect(name)
        assert dialect.child
        assert dialect.child_plural
