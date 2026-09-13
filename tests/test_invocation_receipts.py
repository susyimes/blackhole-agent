"""Failure-window checks for durable invocation admission."""

from contextlib import contextmanager

import pytest

from blackhole_agent.invocation_receipts import InvocationReceipts, ReceiptError


def test_canonical_request_and_restart_replay(tmp_path):
    effects = []

    def operation():
        effects.append("written")
        return 200, {"output": len(effects)}

    first = InvocationReceipts(tmp_path).execute("work", "cap", {"a": 1, "b": {"c": 2}}, operation)
    restarted = InvocationReceipts(tmp_path)
    repeated = restarted.execute("work", "cap", {"b": {"c": 2}, "a": 1}, operation)
    assert first == (200, {"output": 1}, False)
    assert repeated == (200, {"output": 1}, True)
    assert restarted.lookup("work")["response"] == first[1]
    for capability, value in [("other", {"a": 1, "b": {"c": 2}}), ("cap", {"a": 3})]:
        with pytest.raises(ReceiptError) as caught:
            restarted.execute("work", capability, value, operation)
        assert caught.value.payload["code"] == "idempotency_conflict"
    assert effects == ["written"]


@pytest.mark.parametrize("key", ["", "../work", "work/key", "a" * 129, "a b", "中文", "key\n", None])
def test_invalid_keys_never_execute(tmp_path, key):
    effects = []
    with pytest.raises(ReceiptError) as caught:
        InvocationReceipts(tmp_path).execute(key, "cap", {}, lambda: effects.append("written"))
    assert caught.value.status == 400
    assert not effects


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_input_never_reserves_or_executes(tmp_path, value):
    receipts = InvocationReceipts(tmp_path)
    effects = []
    with pytest.raises(ReceiptError) as caught:
        receipts.execute("work", "cap", {"n": value}, lambda: effects.append("written"))
    assert caught.value.status == 400
    with pytest.raises(ReceiptError) as missing:
        receipts.lookup("work")
    assert missing.value.status == 404
    assert not effects


def test_unwritable_store_never_executes(tmp_path):
    (tmp_path / ".blackhole-agent").write_text("not a directory")
    effects = []
    with pytest.raises(ReceiptError) as caught:
        InvocationReceipts(tmp_path).execute("work", "cap", {}, lambda: effects.append("written"))
    assert caught.value.status == 503
    assert not effects


def test_unexpected_failure_after_effect_remains_unknown(tmp_path):
    effects = []

    def operation():
        effects.append("written")
        raise RuntimeError("lost result after external side effect")

    receipts = InvocationReceipts(tmp_path)
    with pytest.raises(ReceiptError) as caught:
        receipts.execute("work", "cap", {}, operation)
    assert caught.value.status == 500
    assert receipts.lookup("work")["state"] == "outcome_unknown"
    with pytest.raises(ReceiptError) as replay:
        InvocationReceipts(tmp_path).execute("work", "cap", {}, operation)
    assert replay.value.status == 409
    assert replay.value.payload["code"] == "outcome_unknown"
    assert effects == ["written"]


def test_completion_storage_failure_does_not_acknowledge_or_repeat(tmp_path, monkeypatch):
    receipts = InvocationReceipts(tmp_path)
    database = receipts._database
    transactions = 0
    effects = []

    @contextmanager
    def fail_completion():
        nonlocal transactions
        transactions += 1
        if transactions == 2:
            raise ReceiptError(503, "receipt_store_unavailable", "injected full disk")
        with database() as connection:
            yield connection

    def operation():
        effects.append("written")
        return 200, {"saved": True}

    monkeypatch.setattr(receipts, "_database", fail_completion)
    with pytest.raises(ReceiptError) as caught:
        receipts.execute("work", "cap", {}, operation)
    assert caught.value.status == 503
    restarted = InvocationReceipts(tmp_path)
    assert restarted.lookup("work")["state"] == "outcome_unknown"
    with pytest.raises(ReceiptError) as replay:
        restarted.execute("work", "cap", {}, operation)
    assert replay.value.status == 409
    assert effects == ["written"]


def test_error_responses_are_durable_even_after_side_effect(tmp_path):
    effects = []

    def operation():
        effects.append("written")
        return 502, {"ok": False, "error": "tool exited after append"}

    first = InvocationReceipts(tmp_path).execute("work", "cap", {}, operation)
    second = InvocationReceipts(tmp_path).execute("work", "cap", {}, operation)
    assert first[:2] == second[:2]
    assert second[2] is True
    assert effects == ["written"]
