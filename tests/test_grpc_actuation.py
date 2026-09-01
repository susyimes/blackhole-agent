from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.grpc_actuation import (
    SENTINEL,
    GRPC_ACTUATION_DONE_WHEN,
    GRPC_ACTUATION_GOAL,
    GRPC_ACTUATION_ID,
    builtin_grpc_actuation_proof,
    decode_grpc_message,
    decode_hpack_headers,
    decode_proto_map,
    encode_grpc_message,
    encode_hpack_headers,
    encode_seal_reply,
    encode_seal_request,
    independent_grpc_digest,
    run_grpc_workflow,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
from blackhole_agent.s3_actuation import S3_ACTUATION_GOAL, S3_ACTUATION_ID
from blackhole_agent.ssh_actuation import SSH_ACTUATION_GOAL, SSH_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    GRPC_TOOL_PROVIDER,
    build_tool_routing_preflight,
    grpc_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.watch_actuation import WATCH_ACTUATION_GOAL, WATCH_ACTUATION_ID
from blackhole_agent.websocket_actuation import WEBSOCKET_ACTUATION_GOAL, WEBSOCKET_ACTUATION_ID


def test_goal_binds_grpc_actuation_plane() -> None:
    assert leftover_marker_ids(GRPC_ACTUATION_GOAL) == (GRPC_ACTUATION_ID,)
    assert GRPC_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(SSH_ACTUATION_GOAL) == (SSH_ACTUATION_ID,)
    assert leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL) == (WEBSOCKET_ACTUATION_ID,)
    assert leftover_marker_ids(WATCH_ACTUATION_GOAL) == (WATCH_ACTUATION_ID,)
    assert leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    assert leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    assert GRPC_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    assert GRPC_ACTUATION_ID not in leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL)
    assert GRPC_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert GRPC_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert GRPC_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert SSH_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    assert WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    grpc_signature = semantic_signature(GRPC_ACTUATION_GOAL)
    for neighbor in (
        SSH_ACTUATION_GOAL,
        WEBSOCKET_ACTUATION_GOAL,
        WATCH_ACTUATION_GOAL,
        S3_ACTUATION_GOAL,
        MQTT_ACTUATION_GOAL,
    ):
        assert semantic_similarity(grpc_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_grpc_tool_completes_preface_settings_headers_data_trailers_replay() -> None:
    descriptor = grpc_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GRPC_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("grpc",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GRPC_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["grpc"]

    missing = run_grpc_workflow(with_secret=False)
    unauth = run_grpc_workflow(authenticate=False)
    wrong = run_grpc_workflow(secret="wrong-token")
    skip_bind = run_grpc_workflow(skip_bind=True)
    skip_preface = run_grpc_workflow(preface=False)
    skip_settings = run_grpc_workflow(settings=False)
    skip_headers = run_grpc_workflow(headers=False)
    skip_data = run_grpc_workflow(data=False)
    skip_trailers = run_grpc_workflow(trailers=False)
    skip_replay = run_grpc_workflow(replay=False)
    live = run_grpc_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "auth_required"
    assert unauth["final_status"] == 401
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "grpc_required"
    assert skip_preface["ok"] is False
    assert skip_preface["error"] == "preface_required"
    assert skip_settings["ok"] is False
    assert skip_settings["error"] == "settings_required"
    assert skip_headers["ok"] is False
    assert skip_headers["error"] == "headers_required"
    assert skip_data["ok"] is False
    assert skip_data["error"] == "data_required"
    assert skip_trailers["ok"] is False
    assert skip_trailers["error"] == "trailers_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_grpc_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["authenticated"] is True
    assert row["prefaced"] is True
    assert row["settings"] is True
    assert row["headers"] is True
    assert row["data"] is True
    assert row["trailers"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["digest"]
    assert len(live["session_id"]) == 64
    request = encode_seal_request(SENTINEL)
    assert decode_proto_map(request)[1] == SENTINEL.encode("utf-8")
    assert decode_grpc_message(encode_grpc_message(request)) == request
    reply = encode_seal_reply(SENTINEL, "abc")
    fields = decode_proto_map(reply)
    assert fields[1] == SENTINEL.encode("utf-8")
    assert fields[2] == b"abc"
    packed = encode_hpack_headers(((":path", "/blackhole.v1.Actuator/Seal"), ("te", "trailers")))
    decoded = decode_hpack_headers(packed)
    assert decoded[":path"] == "/blackhole.v1.Actuator/Seal"
    assert decoded["te"] == "trailers"


def test_builtin_proof_seals_grpc_actuation() -> None:
    report = builtin_grpc_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "grpc_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_grpc"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unsigned_rpc_is_forbidden"]
    assert report["checks"]["wrong_token_is_forbidden"]
    assert report["checks"]["skip_preface_stays_empty"]
    assert report["checks"]["skip_settings_stays_empty"]
    assert report["checks"]["skip_headers_stays_empty"]
    assert report["checks"]["skip_data_stays_empty"]
    assert report["checks"]["skip_trailers_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_grpc"]
    assert report["checks"]["hpack_literal_roundtrip"]
    assert report["checks"]["grpc_envelope_roundtrip"]
    assert report["mission_goal"] == GRPC_ACTUATION_GOAL
    assert report["done_when"] == GRPC_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[GRPC_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "grpc" in capability.tags
    assert "http2" in capability.tags
    assert "rpc" in capability.tags
    assert "protobuf" in capability.tags


def test_selection_gate_accepts_grpc_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        GRPC_ACTUATION_GOAL,
        GRPC_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(GRPC_ACTUATION_GOAL)
    assert "grpc" in family
    assert "http2" in family
    assert "length" in family
    assert "prefixed" in family
    assert "openssh" not in family
    assert "websocket" not in family
    assert "rfc6455" not in family
    assert "watch" not in family
    assert "path" not in family
    assert "object" not in family
    assert "mqtt" not in family
