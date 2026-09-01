from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.imap_actuation import IMAP_ACTUATION_GOAL, IMAP_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.ldap_actuation import (
    DEFAULT_ENTRY_DN,
    LDAP_ACTUATION_DONE_WHEN,
    LDAP_ACTUATION_GOAL,
    LDAP_ACTUATION_ID,
    SENTINEL,
    builtin_ldap_actuation_proof,
    independent_ldap_entry,
    run_ldap_workflow,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
from blackhole_agent.redis_actuation import REDIS_ACTUATION_GOAL, REDIS_ACTUATION_ID
from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    LDAP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    ldap_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_ldap_actuation_plane() -> None:
    assert leftover_marker_ids(LDAP_ACTUATION_GOAL) == (LDAP_ACTUATION_ID,)
    assert LDAP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    assert leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    assert leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    assert leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    assert leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (SQLITE_ACTUATION_ID,)
    assert LDAP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert LDAP_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert LDAP_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    assert LDAP_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    assert LDAP_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert LDAP_ACTUATION_ID not in leftover_marker_ids(SQLITE_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    assert REDIS_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    assert IMAP_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    assert SQLITE_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(DNS_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(MQTT_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(REDIS_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(IMAP_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(SMTP_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(LDAP_ACTUATION_GOAL),
            semantic_signature(SQLITE_ACTUATION_GOAL),
        )
        < 0.82
    )


def test_opted_in_ldap_tool_completes_bind_add_search_workflow() -> None:
    descriptor = ldap_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, LDAP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("ldap",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, LDAP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["ldap"]

    missing = run_ldap_workflow(with_secret=False)
    unauth = run_ldap_workflow(authenticate=False)
    wrong = run_ldap_workflow(password="wrong-secret")
    skip_add = run_ldap_workflow(add=False)
    skip_search = run_ldap_workflow(search=False)
    live = run_ldap_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "bind_required"
    assert unauth["final_status"] == 530
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_add["ok"] is False
    assert skip_add["error"] == "add_required"
    assert skip_search["ok"] is False
    assert skip_search["error"] == "search_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_ldap_entry(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["bound"] is True
    assert row["added"] is True
    assert row["searched"] is True
    assert row["independent"] is True
    assert row["dn"] == DEFAULT_ENTRY_DN


def test_builtin_proof_seals_ldap_actuation() -> None:
    report = builtin_ldap_actuation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "ldap_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_ldap"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unauthenticated_add_is_forbidden"]
    assert report["checks"]["wrong_secret_is_forbidden"]
    assert report["checks"]["skip_add_stays_empty"]
    assert report["checks"]["skip_search_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_entry"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_ldap"]
    assert report["mission_goal"] == LDAP_ACTUATION_GOAL
    assert report["done_when"] == LDAP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[LDAP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "ldap" in capability.tags
    assert "directory" in capability.tags
    assert "identity" in capability.tags


def test_selection_gate_accepts_ldap_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        LDAP_ACTUATION_GOAL,
        LDAP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(LDAP_ACTUATION_GOAL)
    assert "ldap" in family
    assert "directory" in family
    assert "identity" in family
    assert "nameserver" not in family
    assert "mqtt" not in family
    assert "redi" not in family
    assert "blpop" not in family
    assert "imap" not in family
    assert "smtp" not in family
    assert "webhook" not in family
    assert "catalog" not in family
