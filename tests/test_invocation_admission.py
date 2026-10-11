"""Hermetic tests for the global in-flight tool admission limiter."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from blackhole_agent.invocation_admission import (
    DEFAULT_MAX_INFLIGHT,
    MAX_INFLIGHT_ENV,
    AdmissionLimited,
    AdmissionLimiter,
    parse_max_inflight,
)
from blackhole_agent.invocation_receipts import InvocationReceipts, ReceiptError


def test_parse_max_inflight_clamps_and_falls_back() -> None:
    assert parse_max_inflight(None) == DEFAULT_MAX_INFLIGHT
    assert parse_max_inflight("") == DEFAULT_MAX_INFLIGHT
    assert parse_max_inflight("nope") == DEFAULT_MAX_INFLIGHT
    assert parse_max_inflight("0") == DEFAULT_MAX_INFLIGHT
    assert parse_max_inflight("99999") == DEFAULT_MAX_INFLIGHT
    assert parse_max_inflight("1") == 1
    assert parse_max_inflight("8") == 8


def test_limiter_refuses_when_full_then_releases() -> None:
    limiter = AdmissionLimiter()
    limiter.configure(1)
    limiter.acquire()
    with pytest.raises(AdmissionLimited) as caught:
        limiter.acquire()
    assert caught.value.max_inflight == 1
    assert caught.value.inflight == 1
    assert caught.value.payload()["violation"] == "admission_limited"
    limiter.release()
    limiter.acquire()
    limiter.release()
    snap = limiter.snapshot()
    assert snap == {"inflight": 0, "max_inflight": 1}


def test_limiter_reads_env_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = AdmissionLimiter()
    monkeypatch.setenv(MAX_INFLIGHT_ENV, "2")
    assert limiter.max_inflight() == 2
    monkeypatch.setenv(MAX_INFLIGHT_ENV, "not-a-number")
    assert limiter.max_inflight() == DEFAULT_MAX_INFLIGHT


def test_slot_context_releases_on_error() -> None:
    limiter = AdmissionLimiter()
    limiter.configure(1)
    with pytest.raises(RuntimeError):
        with limiter.slot():
            raise RuntimeError("boom")
    limiter.acquire()
    limiter.release()


def test_concurrent_acquire_never_exceeds_cap() -> None:
    limiter = AdmissionLimiter()
    limiter.configure(2)
    acquired = []
    refused = []

    def attempt() -> None:
        try:
            limiter.acquire()
            acquired.append(1)
        except AdmissionLimited:
            refused.append(1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: attempt(), range(8)))
    assert len(acquired) == 2
    assert len(refused) == 6
    limiter.release()
    limiter.release()


def test_receipts_drop_429_reservation(tmp_path) -> None:
    store = InvocationReceipts(tmp_path)

    def refuse() -> tuple[int, dict]:
        return 429, {"ok": False, "error": "too many", "violation": "admission_limited"}

    status, payload, replayed = store.execute("k1", "capability.absorbed-x", {"a": 1}, refuse)
    assert status == 429 and replayed is False and payload["ok"] is False
    with pytest.raises(ReceiptError) as caught:
        store.lookup("k1")
    assert caught.value.status == 404

    def ok() -> tuple[int, dict]:
        return 200, {"ok": True, "output": {"reversed_text": "a"}}

    status, payload, replayed = store.execute("k1", "capability.absorbed-x", {"a": 1}, ok)
    assert status == 200 and replayed is False and payload["ok"] is True
