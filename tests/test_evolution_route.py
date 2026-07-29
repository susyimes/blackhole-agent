"""Tests for capability-compounder evolution surface redirects."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from blackhole_agent.capability_compounder import (
    CapabilityLedger,
    default_ledger_path,
    save_ledger,
    seed_bootstrap_capabilities,
)
from blackhole_agent.evolution_route import (
    COMPOUND_SURFACE,
    LEGACY_GROWTH_SURFACE,
    build_compound_wake_command,
    build_skill_route_compounder_redirect_pipeline,
    resolve_supervisor_evolution_surface,
    should_redirect_skill_route_pipeline,
)
from blackhole_agent.github_growth import attach_skill_route_discovery_capability_pipeline
from blackhole_agent.supervisor import SupervisorConfig, build_wake_command, resolve_wake_surface


def _seed_ledger(repo: Path) -> None:
    ledger = seed_bootstrap_capabilities(CapabilityLedger())
    save_ledger(default_ledger_path(repo), ledger)


def test_should_redirect_when_ledger_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BLACKHOLE_FORCE_SKILL_ROUTE_PIPELINE", raising=False)
    monkeypatch.delenv("BLACKHOLE_PREFER_CAPABILITY_COMPOUNDER", raising=False)
    assert should_redirect_skill_route_pipeline(tmp_path) is False
    _seed_ledger(tmp_path)
    assert should_redirect_skill_route_pipeline(tmp_path) is True


def test_force_skill_route_disables_redirect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_ledger(tmp_path)
    monkeypatch.setenv("BLACKHOLE_FORCE_SKILL_ROUTE_PIPELINE", "1")
    assert should_redirect_skill_route_pipeline(tmp_path) is False


def test_redirect_pipeline_freezes_pin_cascade(tmp_path: Path):
    _seed_ledger(tmp_path)
    pipeline = build_skill_route_compounder_redirect_pipeline(
        proposals=[{"proposal_id": "prop-skill-pipeline-reverse-flow-test"}],
        repo_path=tmp_path,
        source_digest="digest-1",
    )
    assert pipeline["status"] == "redirected_to_capability_compounder"
    assert pipeline["skill_route_pin_cascade_frozen"] is True
    assert pipeline["supervisor_next_action"] == "run_capability_compounder_compose_or_demo"
    assert "continue_cascade_wake_route_apply_follow_pin" in pipeline["skill_route_nested_stages_omitted"]
    assert "pin_call_next_call_follow" in pipeline["skill_route_nested_stages_omitted"]
    assert pipeline["evolution_surface"] == COMPOUND_SURFACE


def test_attach_skill_route_redirects_when_ledger_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BLACKHOLE_FORCE_SKILL_ROUTE_PIPELINE", raising=False)
    _seed_ledger(tmp_path)
    digest = {
        "digest_id": "d1",
        "repo_path": str(tmp_path),
        "proposals": [{"proposal_id": "prop-skill-pipeline-reverse-flow-test", "kind": "code_patch"}],
        "items": [],
    }
    attach_skill_route_discovery_capability_pipeline(digest)
    pipeline = digest["skill_route_discovery_capability_pipeline"]
    assert digest["evolution_surface"] == COMPOUND_SURFACE
    assert pipeline["controller_surface"] == "capability_compounder_redirect"
    assert pipeline["skill_route_pin_cascade_frozen"] is True
    # Nested residual pin/cascade stages must not be packaged.
    assert "residual_adjacent_focused_validation_activation_external_acceptance" not in pipeline


def test_attach_skill_route_keeps_legacy_when_forced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BLACKHOLE_FORCE_SKILL_ROUTE_PIPELINE", "1")
    _seed_ledger(tmp_path)
    digest = {
        "digest_id": "d2",
        "repo_path": str(tmp_path),
        "prefer_capability_compounder": True,
        "proposals": [],
        "items": [],
    }
    attach_skill_route_discovery_capability_pipeline(digest)
    pipeline = digest["skill_route_discovery_capability_pipeline"]
    assert pipeline.get("controller_surface") == "skill_route_discovery_capability_pipeline"
    assert pipeline.get("skill_route_pin_cascade_frozen") is not True


def test_supervisor_codex_redirects_to_compound_when_ledger_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BLACKHOLE_FORCE_SKILL_ROUTE_PIPELINE", raising=False)
    _seed_ledger(tmp_path)
    config = SupervisorConfig(
        repo_path=tmp_path,
        output_dir=tmp_path / "supervisor",
        evolution_mode="codex",
        prefer_capability_compounder=True,
        model="gpt-5.5",
    )
    surface = resolve_wake_surface(config)
    assert surface["surface"] == COMPOUND_SURFACE
    assert surface["redirected"] is True
    command = build_wake_command(config)
    assert command[:5] == [
        sys.executable,
        "-m",
        "blackhole_agent.unbound",
        "capability",
        "demo",
    ]
    assert "blackhole_agent.github_growth" not in command


def test_supervisor_legacy_when_prefer_disabled(tmp_path: Path):
    _seed_ledger(tmp_path)
    config = SupervisorConfig(
        repo_path=tmp_path,
        output_dir=tmp_path / "supervisor",
        evolution_mode="codex",
        prefer_capability_compounder=False,
        model="gpt-5.5",
    )
    surface = resolve_wake_surface(config)
    assert surface["surface"] == LEGACY_GROWTH_SURFACE
    command = build_wake_command(config)
    assert command[:3] == [sys.executable, "-m", "blackhole_agent.github_growth"]


def test_explicit_compound_mode_command(tmp_path: Path):
    config = SupervisorConfig(
        repo_path=tmp_path,
        output_dir=tmp_path / "supervisor",
        evolution_mode="compound",
    )
    command = build_wake_command(config)
    assert "capability" in command and "demo" in command


def test_build_compound_wake_command_compose_mode(tmp_path: Path):
    command = build_compound_wake_command(repo_path=tmp_path, use_demo=False)
    assert command[3:5] == ["capability", "compose"]


def test_resolve_supervisor_explicit_compound(tmp_path: Path):
    decision = resolve_supervisor_evolution_surface(
        evolution_mode="compound",
        repo_path=tmp_path,
        prefer_capability_compounder=False,
    )
    assert decision["effective_mode"] == "compound"
    assert decision["surface"] == COMPOUND_SURFACE
