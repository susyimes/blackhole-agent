"""Hermetic tests for the live GitHub actuation trace contract."""

from __future__ import annotations

import json

from blackhole_agent import github_live
from blackhole_agent.capability_compounder import atomic_write_json


def _sealed_trace(tmp_path):
    outcome = {
        "sentinel": "abc123",
        "repo": "octo/sandbox",
        "bug_check_failed_before_fix": True,
        "fix_check": {"ok": True, "stdout": "check ok"},
        "issue": {"number": 1, "url": "https://example/1", "state": "CLOSED"},
        "pr": {"number": 2, "url": "https://example/2", "state": "MERGED", "merged_at": "2026-07-31T00:00:00Z"},
        "merged_main_contains_fix": True,
    }
    stages = {"auth": {"login": "octo"}, "outcome": outcome}
    body = {
        "schema_version": github_live.SCHEMA_VERSION,
        "kind": "github_live_change_trace",
        "recorded_at": "2026-07-31T00:00:00Z",
        "sentinel": "abc123",
        "repo": "octo/sandbox",
        "stages": stages,
        "stages_digest": github_live._digest(stages),
        "outcome": outcome,
        "outcome_digest": github_live._digest(outcome),
    }
    trace = {**body, "trace_digest": github_live._digest(body)}
    atomic_write_json(tmp_path / "change.json", trace)
    return trace


def test_verify_accepts_intact_trace(tmp_path):
    trace = _sealed_trace(tmp_path)
    result = github_live.verify_change_trace(tmp_path)
    assert result["ok"], result
    assert result["trace_digest"] == trace["trace_digest"]
    assert all(result["checks"].values())


def test_verify_rejects_tampered_outcome(tmp_path):
    _sealed_trace(tmp_path)
    trace = json.loads((tmp_path / "change.json").read_text(encoding="utf-8"))
    trace["outcome"]["pr"]["state"] = "OPEN"
    atomic_write_json(tmp_path / "change.json", trace)
    result = github_live.verify_change_trace(tmp_path)
    assert not result["ok"]
    assert not result["checks"]["outcome_digest"]


def test_verify_rejects_unmerged_pr(tmp_path):
    trace = _sealed_trace(tmp_path)
    trace["outcome"]["pr"]["state"] = "CLOSED"
    trace["outcome"]["pr"]["merged_at"] = None
    trace["outcome_digest"] = github_live._digest(trace["outcome"])
    body = {k: v for k, v in trace.items() if k != "trace_digest"}
    trace["trace_digest"] = github_live._digest(body)
    atomic_write_json(tmp_path / "change.json", trace)
    result = github_live.verify_change_trace(tmp_path)
    assert not result["ok"]
    assert not result["checks"]["pr_merged"]


def test_verify_missing_trace_fails(tmp_path):
    result = github_live.verify_change_trace(tmp_path)
    assert not result["ok"]
    assert "missing" in result["error"]
