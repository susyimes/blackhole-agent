from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.imap_actuation import IMAP_ACTUATION_GOAL, IMAP_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.ldap_actuation import LDAP_ACTUATION_GOAL, LDAP_ACTUATION_ID
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
from blackhole_agent.postgres_actuation import POSTGRES_ACTUATION_GOAL, POSTGRES_ACTUATION_ID
from blackhole_agent.redis_actuation import REDIS_ACTUATION_GOAL, REDIS_ACTUATION_ID
from blackhole_agent.s3_actuation import S3_ACTUATION_GOAL, S3_ACTUATION_ID
from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    WATCH_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    watch_tool_descriptor,
)
from blackhole_agent.watch_actuation import (
    WATCH_ACTUATION_DONE_WHEN,
    WATCH_ACTUATION_GOAL,
    WATCH_ACTUATION_ID,
    SENTINEL,
    builtin_watch_actuation_proof,
    independent_watch_digest,
    run_watch_workflow,
)
from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID


def test_goal_binds_watch_actuation_plane() -> None:
    assert leftover_marker_ids(WATCH_ACTUATION_GOAL) == (WATCH_ACTUATION_ID,)
    assert WATCH_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    assert leftover_marker_ids(POSTGRES_ACTUATION_GOAL) == (POSTGRES_ACTUATION_ID,)
    assert leftover_marker_ids(LDAP_ACTUATION_GOAL) == (LDAP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    assert leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    assert leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    assert leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    assert leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (SQLITE_ACTUATION_ID,)
    assert leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (WEBHOOK_ACTUATION_ID,)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(POSTGRES_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(SQLITE_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(WEBHOOK_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert POSTGRES_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert LDAP_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert REDIS_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert IMAP_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert SQLITE_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert WEBHOOK_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    watch_signature = semantic_signature(WATCH_ACTUATION_GOAL)
    for neighbor in (
        S3_ACTUATION_GOAL,
        POSTGRES_ACTUATION_GOAL,
        LDAP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        MQTT_ACTUATION_GOAL,
        REDIS_ACTUATION_GOAL,
        IMAP_ACTUATION_GOAL,
        SMTP_ACTUATION_GOAL,
        SQLITE_ACTUATION_GOAL,
        WEBHOOK_ACTUATION_GOAL,
    ):
        assert semantic_similarity(watch_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_watch_tool_completes_create_modify_consume_workflow() -> None:
    descriptor = watch_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WATCH_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("watch",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WATCH_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["watch"]

    missing = run_watch_workflow(with_secret=False)
    missing_root = run_watch_workflow(with_root=False)
    unauth = run_watch_workflow(authenticate=False)
    wrong = run_watch_workflow(secret="wrong-token")
    skip_watch = run_watch_workflow(skip_bind=True)
    skip_create = run_watch_workflow(create=False)
    skip_modify = run_watch_workflow(modify=False)
    skip_consume = run_watch_workflow(consume=False)
    live = run_watch_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert missing_root["ok"] is False
    assert missing_root["error"] == "missing_root"
    assert missing_root["final_status"] == 403
    assert unauth["ok"] is False
    assert unauth["error"] == "auth_required"
    assert unauth["final_status"] == 403
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_watch["ok"] is False
    assert skip_watch["error"] == "watch_required"
    assert skip_create["ok"] is False
    assert skip_create["error"] == "create_required"
    assert skip_modify["ok"] is False
    assert skip_modify["error"] == "modify_required"
    assert skip_consume["ok"] is False
    assert skip_consume["error"] == "consume_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_watch_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["authenticated"] is True
    assert row["watched"] is True
    assert row["created"] is True
    assert row["modified"] is True
    assert row["consumed"] is True
    assert row["independent"] is True
    assert row["digest"]


def test_builtin_proof_seals_watch_actuation() -> None:
    report = builtin_watch_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "watch_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_watch"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["missing_root_is_forbidden"]
    assert report["checks"]["unsigned_watch_is_forbidden"]
    assert report["checks"]["wrong_token_is_forbidden"]
    assert report["checks"]["skip_watch_stays_empty"]
    assert report["checks"]["skip_create_stays_empty"]
    assert report["checks"]["skip_modify_stays_empty"]
    assert report["checks"]["skip_consume_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_watch"]
    assert report["mission_goal"] == WATCH_ACTUATION_GOAL
    assert report["done_when"] == WATCH_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[WATCH_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "watch" in capability.tags
    assert "path-watch" in capability.tags
    assert "filesystem" in capability.tags
    assert "mutation" in capability.tags


def test_selection_gate_accepts_watch_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        WATCH_ACTUATION_GOAL,
        WATCH_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(WATCH_ACTUATION_GOAL)
    assert "path" in family
    assert "watch" in family
    assert "change" in family
    assert "actuation" in family
    assert "object" not in family
    assert "postgresql" not in family
    assert "ldap" not in family
    assert "directory" not in family
    assert "nameserver" not in family
    assert "mqtt" not in family
    assert "redi" not in family
    assert "imap" not in family
    assert "smtp" not in family
    assert "sqlite" not in family
    assert "webhook" not in family
    assert "catalog" not in family
