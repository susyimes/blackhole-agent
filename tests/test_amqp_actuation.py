from pathlib import Path

from blackhole_agent.amqp_actuation import (
    AMQP_ACTUATION_DONE_WHEN,
    AMQP_ACTUATION_GOAL,
    AMQP_ACTUATION_ID,
    PROTOCOL_HEADER,
    SENTINEL,
    builtin_amqp_actuation_proof,
    decode_plain_response,
    encode_frame,
    encode_plain_response,
    encode_start_ok,
    independent_amqp_digest,
    parse_method,
    parse_start_ok,
    run_amqp_workflow,
)
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.grpc_actuation import GRPC_ACTUATION_GOAL, GRPC_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
from blackhole_agent.redis_actuation import REDIS_ACTUATION_GOAL, REDIS_ACTUATION_ID
from blackhole_agent.ssh_actuation import SSH_ACTUATION_GOAL, SSH_ACTUATION_ID
from blackhole_agent.tool_routing import (
    AMQP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    amqp_tool_descriptor,
    build_tool_routing_preflight,
    route_tool_descriptor,
)
from blackhole_agent.websocket_actuation import WEBSOCKET_ACTUATION_GOAL, WEBSOCKET_ACTUATION_ID


def test_goal_binds_amqp_actuation_plane() -> None:
    assert leftover_marker_ids(AMQP_ACTUATION_GOAL) == (AMQP_ACTUATION_ID,)
    assert AMQP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(GRPC_ACTUATION_GOAL) == (GRPC_ACTUATION_ID,)
    assert leftover_marker_ids(SSH_ACTUATION_GOAL) == (SSH_ACTUATION_ID,)
    assert leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL) == (WEBSOCKET_ACTUATION_ID,)
    assert leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    assert leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    assert AMQP_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    assert AMQP_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    assert AMQP_ACTUATION_ID not in leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL)
    assert AMQP_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert AMQP_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    assert GRPC_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    assert SSH_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    assert WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    assert REDIS_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    amqp_signature = semantic_signature(AMQP_ACTUATION_GOAL)
    for neighbor in (
        GRPC_ACTUATION_GOAL,
        SSH_ACTUATION_GOAL,
        WEBSOCKET_ACTUATION_GOAL,
        MQTT_ACTUATION_GOAL,
        REDIS_ACTUATION_GOAL,
    ):
        assert semantic_similarity(amqp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_amqp_tool_completes_protocol_connection_channel_declare_publish_deliver_replay() -> None:
    descriptor = amqp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, AMQP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("amqp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, AMQP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["amqp"]

    missing = run_amqp_workflow(with_secret=False)
    unauth = run_amqp_workflow(authenticate=False)
    wrong = run_amqp_workflow(password="wrong-password")
    skip_bind = run_amqp_workflow(skip_bind=True)
    skip_protocol = run_amqp_workflow(protocol=False)
    skip_connection = run_amqp_workflow(connection=False)
    skip_channel = run_amqp_workflow(channel=False)
    skip_declare = run_amqp_workflow(declare=False)
    skip_publish = run_amqp_workflow(publish=False)
    skip_consume = run_amqp_workflow(consume=False)
    skip_replay = run_amqp_workflow(replay=False)
    live = run_amqp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "connection_required"
    assert unauth["final_status"] == 530
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_protocol["ok"] is False
    assert skip_protocol["error"] == "protocol_required"
    assert skip_connection["ok"] is False
    assert skip_connection["error"] == "connection_required"
    assert skip_channel["ok"] is False
    assert skip_channel["error"] == "channel_required"
    assert skip_declare["ok"] is False
    assert skip_declare["error"] == "declare_required"
    assert skip_publish["ok"] is False
    assert skip_publish["error"] == "publish_required"
    assert skip_consume["ok"] is False
    assert skip_consume["error"] == "deliver_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_amqp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["protocol"] is True
    assert row["connected"] is True
    assert row["channeled"] is True
    assert row["declared"] is True
    assert row["published"] is True
    assert row["delivered"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["authenticated"] is True
    assert row["digest"]
    assert int(live["delivery_tag"]) > 0
    assert PROTOCOL_HEADER == b"AMQP\x00\x00\x09\x01"
    user, secret = decode_plain_response(encode_plain_response("u", "p"))
    assert user == "u" and secret == "p"
    start_ok = parse_start_ok(parse_method(encode_start_ok("u", "p")[7:-1])[2])
    assert start_ok["mechanism"] == "PLAIN"
    assert start_ok["username"] == "u"
    packed = encode_frame(1, 1, b"abcd")
    assert packed[7:11] == b"abcd"
    assert packed[-1] == 0xCE


def test_builtin_proof_seals_amqp_actuation() -> None:
    report = builtin_amqp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "amqp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_amqp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unauthenticated_channel_is_forbidden"]
    assert report["checks"]["wrong_password_is_forbidden"]
    assert report["checks"]["skip_protocol_stays_empty"]
    assert report["checks"]["skip_connection_stays_empty"]
    assert report["checks"]["skip_channel_stays_empty"]
    assert report["checks"]["skip_declare_stays_empty"]
    assert report["checks"]["skip_publish_stays_empty"]
    assert report["checks"]["skip_consume_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_amqp"]
    assert report["checks"]["frame_roundtrip"]
    assert report["checks"]["plain_roundtrip"]
    assert report["mission_goal"] == AMQP_ACTUATION_GOAL
    assert report["done_when"] == AMQP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[AMQP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "amqp" in capability.tags
    assert "work-queue" in capability.tags
    assert "delivery" in capability.tags


def test_selection_gate_accepts_amqp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        AMQP_ACTUATION_GOAL,
        AMQP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(AMQP_ACTUATION_GOAL)
    assert "amqp" in family
    assert "queue" in family
    assert "delivery" in family
    assert "grpc" not in family
    assert "http2" not in family
    assert "openssh" not in family
    assert "websocket" not in family
    assert "rfc6455" not in family
    assert "mqtt" not in family
    assert "redi" not in family
    assert "blpop" not in family
    assert "auth" not in family.split("/")
