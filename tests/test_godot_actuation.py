from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.browser_actuation import BROWSER_ACTUATION_GOAL, BROWSER_ACTUATION_ID
from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
from blackhole_agent.godot_actuation import (
    DEFAULT_NODE_NAME,
    DEFAULT_SCENE_PATH,
    GODOT_ACTUATION_DONE_WHEN,
    GODOT_ACTUATION_GOAL,
    GODOT_ACTUATION_ID,
    SENTINEL,
    Scene,
    builtin_godot_actuation_proof,
    run_godot_workflow,
)
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    GODOT_TOOL_PROVIDER,
    build_tool_routing_preflight,
    godot_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_godot_actuation_plane() -> None:
    assert leftover_marker_ids(GODOT_ACTUATION_GOAL) == (GODOT_ACTUATION_ID,)
    assert GODOT_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (GMAIL_ACTUATION_ID,)
    assert leftover_marker_ids(BROWSER_ACTUATION_GOAL) == (BROWSER_ACTUATION_ID,)
    assert GODOT_ACTUATION_ID not in leftover_marker_ids(GMAIL_ACTUATION_GOAL)
    assert GODOT_ACTUATION_ID not in leftover_marker_ids(BROWSER_ACTUATION_GOAL)


def test_opted_in_godot_tool_completes_project_gated_workflow() -> None:
    descriptor = godot_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GODOT_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("godot",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GODOT_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["godot"]

    blocked = run_godot_workflow(project_open=False)
    unscene = run_godot_workflow(skip_scene=True)
    live = run_godot_workflow()
    assert blocked["ok"] is False
    assert blocked["final_status"] == 403
    assert blocked["error"] == "project_gated"
    assert unscene["ok"] is False
    assert unscene["error"] == "scene_gated"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["scene_saved"] is True
    assert "[gd_scene" in live["tscn"]
    assert 'text = "BH-GODOT-OK"' in live["tscn"]
    parsed = Scene.from_tscn(DEFAULT_SCENE_PATH, live["tscn"])
    beacon = parsed.find(DEFAULT_NODE_NAME)
    assert beacon is not None
    assert beacon.type == "Label"


def test_builtin_proof_seals_godot_actuation() -> None:
    report = builtin_godot_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "godot_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_godot"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_project_is_forbidden"]
    assert report["checks"]["unscene_node_is_forbidden"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_writes_godot4_tscn"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_godot"]
    assert report["mission_goal"] == GODOT_ACTUATION_GOAL
    assert report["done_when"] == GODOT_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[GODOT_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "godot" in capability.tags
    assert "scene" in capability.tags
