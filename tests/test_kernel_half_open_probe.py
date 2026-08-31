from datetime import timedelta
from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_half_open_persist import HALF_OPEN_PERSIST_GOAL, HALF_OPEN_PERSIST_ID
from blackhole_agent.kernel_half_open_probe import (
    HALF_OPEN_PROBE_DONE_WHEN,
    HALF_OPEN_PROBE_GOAL,
    HALF_OPEN_PROBE_ID,
    builtin_kernel_half_open_probe_proof,
    half_open_peer_names,
    probe_half_open_peer_kernels,
)
from blackhole_agent.kernel_health import (
    KernelHealth,
    _utc_now,
    recorded_kernel_state,
    save_kernel_health,
    trip_kernel,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_plugin_reconnect import MCP_RECONNECT_GOAL, MCP_RECONNECT_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_half_open_probe_plane() -> None:
    assert leftover_marker_ids(HALF_OPEN_PROBE_GOAL) == (HALF_OPEN_PROBE_ID,)
    assert HALF_OPEN_PROBE_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HALF_OPEN_PERSIST_GOAL) == (HALF_OPEN_PERSIST_ID,)
    assert leftover_marker_ids(MCP_RECONNECT_GOAL) == (MCP_RECONNECT_ID,)
    assert HALF_OPEN_PROBE_ID not in leftover_marker_ids(HALF_OPEN_PERSIST_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(HALF_OPEN_PROBE_GOAL),
            semantic_signature(HALF_OPEN_PERSIST_GOAL),
        )
        < 0.82
    )


def test_half_open_peer_is_recovered_without_touching_requested(tmp_path: Path) -> None:
    health = KernelHealth()
    tripped = _utc_now()
    trip_kernel(health, "kimi", "quota_exhausted", "402", now=tripped)
    later = tripped + timedelta(hours=7)
    pinged: list[str] = []
    report = probe_half_open_peer_kernels(
        health,
        requested="grok",
        installed={"grok", "kimi"},
        probe=lambda name: pinged.append(name) or {"ok": True, "class_id": "", "evidence": name},
        now=later,
        persist=lambda: save_kernel_health(tmp_path, health, now=later),
    )
    assert pinged == ["kimi"]
    assert report["recovered"] == ["kimi"]
    assert report["requested"] == "grok"
    assert recorded_kernel_state(tmp_path, "kimi") == "closed"
    assert half_open_peer_names(
        health,
        requested="grok",
        installed={"grok", "kimi"},
        now=later,
    ) == ()


def test_builtin_proof_pings_half_open_peers_without_hijacking_mission() -> None:
    report = builtin_kernel_half_open_probe_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_half_open_probe"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_leaves_peer_half_open"]
    assert report["checks"]["recovers_healthy_peer"]
    assert report["checks"]["retrips_quota_peer"]
    assert report["checks"]["does_not_hijack_requested_kernel"]
    assert report["checks"]["exhausted_catalog_binds_probe"]
    assert report["mission_goal"] == HALF_OPEN_PROBE_GOAL
    assert report["done_when"] == HALF_OPEN_PROBE_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[HALF_OPEN_PROBE_ID]
    assert capability.last_proof_exit_code == 0
    assert "probe" in capability.tags
    assert "peer" in capability.tags


def test_selection_gate_accepts_peer_probe_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        HALF_OPEN_PROBE_GOAL,
        HALF_OPEN_PROBE_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(HALF_OPEN_PROBE_GOAL)
    assert family.startswith("kernel-runtime")
