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
from blackhole_agent.postgres_actuation import (
    DEFAULT_USER,
    POSTGRES_ACTUATION_DONE_WHEN,
    POSTGRES_ACTUATION_GOAL,
    POSTGRES_ACTUATION_ID,
    SENTINEL,
    builtin_postgres_actuation_proof,
    independent_postgres_row,
    run_postgres_workflow,
)
from blackhole_agent.redis_actuation import REDIS_ACTUATION_GOAL, REDIS_ACTUATION_ID
from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    POSTGRES_TOOL_PROVIDER,
    build_tool_routing_preflight,
    postgres_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_postgres_actuation_plane() -> None:
    assert leftover_marker_ids(POSTGRES_ACTUATION_GOAL) == (POSTGRES_ACTUATION_ID,)
    assert POSTGRES_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(LDAP_ACTUATION_GOAL) == (LDAP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    assert leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    assert leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    assert leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    assert leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (SQLITE_ACTUATION_ID,)
    assert POSTGRES_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    assert POSTGRES_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert POSTGRES_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert POSTGRES_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    assert POSTGRES_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    assert POSTGRES_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert POSTGRES_ACTUATION_ID not in leftover_marker_ids(SQLITE_ACTUATION_GOAL)
    assert LDAP_ACTUATION_ID not in leftover_marker_ids(POSTGRES_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(POSTGRES_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(POSTGRES_ACTUATION_GOAL)
    assert REDIS_ACTUATION_ID not in leftover_marker_ids(POSTGRES_ACTUATION_GOAL)
    assert IMAP_ACTUATION_ID not in leftover_marker_ids(POSTGRES_ACTUATION_GOAL)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(POSTGRES_ACTUATION_GOAL)
    assert SQLITE_ACTUATION_ID not in leftover_marker_ids(POSTGRES_ACTUATION_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(LDAP_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(DNS_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(MQTT_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(REDIS_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(IMAP_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(POSTGRES_ACTUATION_GOAL),
            semantic_signature(SQLITE_ACTUATION_GOAL),
        )
        < 0.82
    )


def test_opted_in_postgres_tool_completes_startup_password_query_workflow() -> None:
    descriptor = postgres_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, POSTGRES_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("postgres",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, POSTGRES_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["postgres"]

    missing = run_postgres_workflow(with_secret=False)
    unauth = run_postgres_workflow(authenticate=False)
    wrong = run_postgres_workflow(password="wrong-secret")
    skip_insert = run_postgres_workflow(insert=False)
    skip_query = run_postgres_workflow(query=False)
    live = run_postgres_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "auth_required"
    assert unauth["final_status"] == 530
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_insert["ok"] is False
    assert skip_insert["error"] == "insert_required"
    assert skip_query["ok"] is False
    assert skip_query["error"] == "query_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_postgres_row(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["authenticated"] is True
    assert row["inserted"] is True
    assert row["queried"] is True
    assert row["independent"] is True
    assert row["user"] == DEFAULT_USER


def test_builtin_proof_seals_postgres_actuation() -> None:
    report = builtin_postgres_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "postgres_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_postgres"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unauthenticated_query_is_forbidden"]
    assert report["checks"]["wrong_secret_is_forbidden"]
    assert report["checks"]["skip_insert_stays_empty"]
    assert report["checks"]["skip_query_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_row"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_postgres"]
    assert report["mission_goal"] == POSTGRES_ACTUATION_GOAL
    assert report["done_when"] == POSTGRES_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[POSTGRES_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "postgres" in capability.tags
    assert "postgresql" in capability.tags
    assert "sql" in capability.tags
    assert "wire" in capability.tags


def test_selection_gate_accepts_postgres_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        POSTGRES_ACTUATION_GOAL,
        POSTGRES_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(POSTGRES_ACTUATION_GOAL)
    assert "postgresql" in family
    assert "frontend" in family
    assert "backend" in family
    assert "query" in family
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
