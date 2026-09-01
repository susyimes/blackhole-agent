from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.imap_actuation import IMAP_ACTUATION_GOAL, IMAP_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.mqtt_actuation import (
    MQTT_ACTUATION_DONE_WHEN,
    MQTT_ACTUATION_GOAL,
    MQTT_ACTUATION_ID,
    SENTINEL,
    builtin_mqtt_actuation_proof,
    independent_mqtt_topic,
    run_mqtt_workflow,
    topic_matches,
)
from blackhole_agent.redis_actuation import REDIS_ACTUATION_GOAL, REDIS_ACTUATION_ID
from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    MQTT_TOOL_PROVIDER,
    build_tool_routing_preflight,
    mqtt_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_mqtt_actuation_plane() -> None:
    assert leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    assert MQTT_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    assert leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    assert leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    assert leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (SQLITE_ACTUATION_ID,)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(SQLITE_ACTUATION_GOAL)
    assert REDIS_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert IMAP_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert SQLITE_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MQTT_ACTUATION_GOAL),
            semantic_signature(REDIS_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MQTT_ACTUATION_GOAL),
            semantic_signature(IMAP_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MQTT_ACTUATION_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MQTT_ACTUATION_GOAL),
            semantic_signature(SQLITE_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert topic_matches("sensors/+", "sensors/heartbeat")
    assert not topic_matches("sensors/+", "other/heartbeat")


def test_opted_in_mqtt_tool_completes_retained_fanout_workflow() -> None:
    descriptor = mqtt_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MQTT_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("mqtt",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MQTT_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["mqtt"]

    missing = run_mqtt_workflow(with_secret=False)
    unauth = run_mqtt_workflow(authenticate=False)
    wrong = run_mqtt_workflow(password="wrong-password")
    skip_subscribe = run_mqtt_workflow(subscribe=False)
    skip_retain = run_mqtt_workflow(retain=False)
    live = run_mqtt_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "connect_required"
    assert unauth["final_status"] == 530
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_subscribe["ok"] is False
    assert skip_subscribe["error"] == "subscribe_required"
    assert skip_retain["ok"] is False
    assert skip_retain["error"] == "retain_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_mqtt_topic(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["connected"] is True
    assert row["subscribed"] is True
    assert row["retained"] is True
    assert row["independent"] is True
    assert row["topic"] == "sensors/heartbeat"
    assert row["filter"] == "sensors/+"


def test_builtin_proof_seals_mqtt_actuation() -> None:
    report = builtin_mqtt_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mqtt_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_mqtt"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unauthenticated_subscribe_is_forbidden"]
    assert report["checks"]["wrong_password_is_forbidden"]
    assert report["checks"]["skip_subscribe_stays_empty"]
    assert report["checks"]["skip_retain_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_topic"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_mqtt"]
    assert report["mission_goal"] == MQTT_ACTUATION_GOAL
    assert report["done_when"] == MQTT_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MQTT_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "mqtt" in capability.tags
    assert "retained" in capability.tags
    assert "fanout" in capability.tags


def test_selection_gate_accepts_mqtt_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MQTT_ACTUATION_GOAL,
        MQTT_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MQTT_ACTUATION_GOAL)
    assert "mqtt" in family
    assert "retained" in family
    assert "fanout" in family
    assert "redi" not in family
    assert "blpop" not in family
    assert "imap" not in family
    assert "smtp" not in family
    assert "webhook" not in family
    assert "catalog" not in family
    assert "timeout" not in family
    assert "git-publication" not in family
    assert "browser" not in family
    assert "bearer" not in family
    assert "auth" not in family.split("/")
    assert not family.startswith("kernel-runtime")
