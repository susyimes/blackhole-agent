"""Tests for the grounded growth scout (live-trend -> hypothesis -> sealed artifact)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent import grounded_growth as gg
from blackhole_agent.github_growth import TrendingRepository

FIXTURE = Path(__file__).parent / "fixtures" / "grounded_scan_payload.json"


def _repo(full_name: str, *, stars: int, description: str = "", topics: list[str] | None = None) -> TrendingRepository:
    return TrendingRepository(
        full_name=full_name,
        html_url=f"https://github.com/{full_name}",
        description=description,
        language="Python",
        stargazers_count=stars,
        forks_count=0,
        open_issues_count=0,
        created_at="2026-07-20T00:00:00Z",
        updated_at="2026-07-30T00:00:00Z",
        pushed_at="2026-07-30T00:00:00Z",
        topics=topics or [],
    )


def test_matched_terms_and_primary_surface() -> None:
    repo = _repo("a/mcp-tool-agent", stars=10, description="MCP tool router for agents", topics=["mcp", "agents"])
    terms = gg.repository_matched_terms(repo)
    assert "mcp" in terms and "tool" in terms and "agent" in terms
    surface, pattern = gg.repository_primary_surface(terms)
    assert surface == "src/blackhole_agent/tool_routing.py"
    assert "tool" in pattern


def test_fallback_surface_for_unmatched_repo() -> None:
    repo = _repo("a/boring-lib", stars=3, description="a csv pretty printer")
    surface, _ = gg.repository_primary_surface(gg.repository_matched_terms(repo))
    assert surface == gg.FALLBACK_SURFACE[0]


def test_distill_is_deterministic_and_ranked() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    repos = gg.payload_to_repositories(payload)
    first = gg.distill_hypotheses(repos)
    second = gg.distill_hypotheses(list(reversed(repos)))
    assert first == second
    scores = [item["score"] for item in first]
    assert scores == sorted(scores, reverse=True)
    assert [item["rank"] for item in first] == list(range(1, len(first) + 1))
    assert all(item["sources"] for item in first)
    assert all(item["target_surface"].startswith("src/blackhole_agent/") for item in first)


def test_replay_verify_roundtrip(tmp_path: Path) -> None:
    summary = gg.run_replay_scan(FIXTURE, output_dir=tmp_path / "scan")
    assert summary["ok"] and summary["hypothesis_count"] > 0
    verified = gg.verify_grounded_scan(tmp_path / "scan")
    assert verified["ok"], verified
    assert verified["scan_digest"] == summary["scan_digest"]


def test_tampered_payload_fails_verification(tmp_path: Path) -> None:
    gg.run_replay_scan(FIXTURE, output_dir=tmp_path / "scan")
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["items"][0]["stargazers_count"] += 1
    (tmp_path / "scan" / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
    verified = gg.verify_grounded_scan(tmp_path / "scan")
    assert not verified["ok"]
    assert not verified["checks"]["payload_digest"]


def test_builtin_proof_passes() -> None:
    result = gg.builtin_grounded_scan_proof()
    assert result["ok"], result
    assert result["tamper_detected"] is True
    assert result["hypothesis_count"] > 0


def test_cli_replay(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = gg.main(["--replay", str(FIXTURE), "--output-dir", str(tmp_path / "scan")])
    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"]
