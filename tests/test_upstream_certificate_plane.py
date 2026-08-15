"""Shared certificate-plane I/O is the live path for every spine family."""

from __future__ import annotations

import inspect

from blackhole_agent.upstream_certificate_plane import (
    builtin_certificate_plane_proof,
    load_irreversible_certificate,
    resolve_certificate_path,
    write_irreversible_certificate,
)
from blackhole_agent.upstream_control_engine import (
    continuity_checkpoint_path,
    load_total_spine_continuity_checkpoint,
    load_total_spine_execution_certificate,
    load_total_spine_federation_certificate,
    load_total_spine_finality_certificate,
    write_total_spine_execution_certificate,
    write_total_spine_federation_certificate,
    write_total_spine_finality_certificate,
)
from blackhole_agent.upstream_total_spine_actuation import (
    load_total_spine_actuation_certificate,
    write_total_spine_actuation_certificate,
)
from blackhole_agent.upstream_total_spine_clearing import (
    load_total_spine_clearing_certificate,
    write_total_spine_clearing_certificate,
)
from blackhole_agent.upstream_total_spine_effects import (
    load_certificate,
    write_certificate,
)
from blackhole_agent.upstream_total_spine_settlement import (
    load_total_spine_settlement_certificate,
    write_total_spine_settlement_certificate,
)


def test_builtin_certificate_plane_proof() -> None:
    result = builtin_certificate_plane_proof()
    assert result["ok"] is True
    assert result["wired_count"] >= 8
    assert result["used_skill_route_discovery"] is False
    assert all(result["wired"].values())


def test_live_wrappers_call_the_plane() -> None:
    writes = {
        "finality": write_total_spine_finality_certificate,
        "federation": write_total_spine_federation_certificate,
        "execution": write_total_spine_execution_certificate,
        "actuation": write_total_spine_actuation_certificate,
        "settlement": write_total_spine_settlement_certificate,
        "clearing": write_total_spine_clearing_certificate,
        "pair": write_certificate,
    }
    loads = {
        "finality": load_total_spine_finality_certificate,
        "federation": load_total_spine_federation_certificate,
        "execution": load_total_spine_execution_certificate,
        "actuation": load_total_spine_actuation_certificate,
        "settlement": load_total_spine_settlement_certificate,
        "clearing": load_total_spine_clearing_certificate,
        "pair": load_certificate,
        "continuity": load_total_spine_continuity_checkpoint,
    }
    for name, fn in writes.items():
        assert "write_irreversible_certificate" in inspect.getsource(fn), name
    for name, fn in loads.items():
        assert "load_irreversible_certificate" in inspect.getsource(fn), name
    assert "resolve_certificate_path" in inspect.getsource(continuity_checkpoint_path)
    assert resolve_certificate_path is not None
    assert write_irreversible_certificate is not None
    assert load_irreversible_certificate is not None
