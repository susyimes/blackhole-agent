from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_cursor_pagination import MCP_CURSOR_GOAL, MCP_CURSOR_ID
from blackhole_agent.mcp_http_event_stream import MCP_HTTP_EVENT_GOAL, MCP_HTTP_EVENT_ID
from blackhole_agent.mcp_structured_output import MCP_STRUCTURED_GOAL, MCP_STRUCTURED_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
from blackhole_agent.s3_actuation import S3_ACTUATION_GOAL, S3_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    WEBSOCKET_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    websocket_tool_descriptor,
)
from blackhole_agent.watch_actuation import WATCH_ACTUATION_GOAL, WATCH_ACTUATION_ID
from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID
from blackhole_agent.websocket_actuation import (
    GUID,
    SENTINEL,
    WEBSOCKET_ACTUATION_DONE_WHEN,
    WEBSOCKET_ACTUATION_GOAL,
    WEBSOCKET_ACTUATION_ID,
    builtin_websocket_actuation_proof,
    independent_websocket_digest,
    run_websocket_workflow,
    websocket_accept_key,
)


def test_goal_binds_websocket_actuation_plane() -> None:
    assert leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL) == (WEBSOCKET_ACTUATION_ID,)
    assert WEBSOCKET_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_STRUCTURED_GOAL) == (MCP_STRUCTURED_ID,)
    assert leftover_marker_ids(MCP_CURSOR_GOAL) == (MCP_CURSOR_ID,)
    assert leftover_marker_ids(WATCH_ACTUATION_GOAL) == (WATCH_ACTUATION_ID,)
    assert leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    assert leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    assert leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (WEBHOOK_ACTUATION_ID,)
    assert leftover_marker_ids(MCP_HTTP_EVENT_GOAL) == (MCP_HTTP_EVENT_ID,)
    assert WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(MCP_STRUCTURED_GOAL)
    assert WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(MCP_CURSOR_GOAL)
    assert WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(WEBHOOK_ACTUATION_GOAL)
    assert WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(MCP_HTTP_EVENT_GOAL)
    assert MCP_STRUCTURED_ID not in leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL)
    assert MCP_CURSOR_ID not in leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL)
    assert WEBHOOK_ACTUATION_ID not in leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL)
    assert MCP_HTTP_EVENT_ID not in leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL)
    websocket_signature = semantic_signature(WEBSOCKET_ACTUATION_GOAL)
    for neighbor in (
        MCP_STRUCTURED_GOAL,
        MCP_CURSOR_GOAL,
        WATCH_ACTUATION_GOAL,
        S3_ACTUATION_GOAL,
        MQTT_ACTUATION_GOAL,
        WEBHOOK_ACTUATION_GOAL,
        MCP_HTTP_EVENT_GOAL,
    ):
        assert semantic_similarity(websocket_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_websocket_tool_completes_upgrade_send_receive_pong_replay() -> None:
    descriptor = websocket_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBSOCKET_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("websocket",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBSOCKET_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["websocket"]

    missing = run_websocket_workflow(with_secret=False)
    unauth = run_websocket_workflow(authenticate=False)
    wrong = run_websocket_workflow(secret="wrong-token")
    skip_bind = run_websocket_workflow(skip_bind=True)
    skip_upgrade = run_websocket_workflow(upgrade=False)
    skip_send = run_websocket_workflow(send=False)
    skip_receive = run_websocket_workflow(receive=False)
    skip_pong = run_websocket_workflow(pong=False)
    skip_mask = run_websocket_workflow(mask=False)
    skip_replay = run_websocket_workflow(replay=False)
    live = run_websocket_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "auth_required"
    assert unauth["final_status"] == 401
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "websocket_required"
    assert skip_upgrade["ok"] is False
    assert skip_upgrade["error"] == "upgrade_required"
    assert skip_send["ok"] is False
    assert skip_send["error"] == "send_required"
    assert skip_receive["ok"] is False
    assert skip_receive["error"] == "receive_required"
    assert skip_pong["ok"] is False
    assert skip_pong["error"] == "pong_required"
    assert skip_mask["ok"] is False
    assert skip_mask["error"] == "mask_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_websocket_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["authenticated"] is True
    assert row["upgraded"] is True
    assert row["sent"] is True
    assert row["received"] is True
    assert row["ponged"] is True
    assert row["masked"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["digest"]
    assert live["accept"]


def test_builtin_proof_seals_websocket_actuation() -> None:
    report = builtin_websocket_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "websocket_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_websocket"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unsigned_upgrade_is_forbidden"]
    assert report["checks"]["wrong_token_is_forbidden"]
    assert report["checks"]["skip_upgrade_stays_empty"]
    assert report["checks"]["skip_send_stays_empty"]
    assert report["checks"]["skip_receive_stays_empty"]
    assert report["checks"]["skip_pong_stays_empty"]
    assert report["checks"]["unmasked_client_frame_is_rejected"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_websocket"]
    assert report["checks"]["accept_key_is_rfc6455"]
    assert report["mission_goal"] == WEBSOCKET_ACTUATION_GOAL
    assert report["done_when"] == WEBSOCKET_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[WEBSOCKET_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "websocket" in capability.tags
    assert "rfc6455" in capability.tags
    assert "upgrade" in capability.tags
    assert "framing" in capability.tags
    assert GUID in "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    assert websocket_accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def test_selection_gate_accepts_websocket_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        WEBSOCKET_ACTUATION_GOAL,
        WEBSOCKET_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(WEBSOCKET_ACTUATION_GOAL)
    assert "rfc6455" in family
    assert "websocket" in family
    assert "upgrade" in family
    assert "framing" in family
    assert "watch" not in family
    assert "path" not in family
    assert "structured" not in family
    assert "cursor" not in family
    assert "object" not in family
    assert "webhook" not in family
    assert "mqtt" not in family
    assert "catalog" not in family
