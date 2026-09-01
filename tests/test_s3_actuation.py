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
from blackhole_agent.s3_actuation import (
    DEFAULT_BUCKET,
    S3_ACTUATION_DONE_WHEN,
    S3_ACTUATION_GOAL,
    S3_ACTUATION_ID,
    SENTINEL,
    builtin_s3_actuation_proof,
    independent_s3_object,
    run_s3_workflow,
)
from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    S3_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    s3_tool_descriptor,
)
from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID


def test_goal_binds_s3_actuation_plane() -> None:
    assert leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    assert S3_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(POSTGRES_ACTUATION_GOAL) == (POSTGRES_ACTUATION_ID,)
    assert leftover_marker_ids(LDAP_ACTUATION_GOAL) == (LDAP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    assert leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    assert leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    assert leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    assert leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (SQLITE_ACTUATION_ID,)
    assert leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (WEBHOOK_ACTUATION_ID,)
    assert S3_ACTUATION_ID not in leftover_marker_ids(POSTGRES_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(REDIS_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(SQLITE_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(WEBHOOK_ACTUATION_GOAL)
    assert POSTGRES_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert LDAP_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert REDIS_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert IMAP_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert SQLITE_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert WEBHOOK_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    s3_signature = semantic_signature(S3_ACTUATION_GOAL)
    for neighbor in (
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
        assert semantic_similarity(s3_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_s3_tool_completes_sigv4_put_get_list_workflow() -> None:
    descriptor = s3_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, S3_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("s3",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, S3_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["s3"]

    missing = run_s3_workflow(with_secret=False)
    unauth = run_s3_workflow(authenticate=False)
    wrong = run_s3_workflow(secret="wrong-secret")
    skip_put = run_s3_workflow(put=False)
    skip_get = run_s3_workflow(get=False)
    skip_list = run_s3_workflow(list_bucket=False)
    live = run_s3_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "auth_required"
    assert unauth["final_status"] == 403
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_put["ok"] is False
    assert skip_put["error"] == "put_required"
    assert skip_get["ok"] is False
    assert skip_get["error"] == "get_required"
    assert skip_list["ok"] is False
    assert skip_list["error"] == "list_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_s3_object(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["authenticated"] is True
    assert row["put"] is True
    assert row["got"] is True
    assert row["listed"] is True
    assert row["independent"] is True
    assert row["bucket"] == DEFAULT_BUCKET
    assert row["etag"]


def test_builtin_proof_seals_s3_actuation() -> None:
    report = builtin_s3_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "s3_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_s3"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unsigned_put_is_forbidden"]
    assert report["checks"]["wrong_secret_is_forbidden"]
    assert report["checks"]["skip_put_stays_empty"]
    assert report["checks"]["skip_get_stays_empty"]
    assert report["checks"]["skip_list_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_object"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_s3"]
    assert report["mission_goal"] == S3_ACTUATION_GOAL
    assert report["done_when"] == S3_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[S3_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "s3" in capability.tags
    assert "object-store" in capability.tags
    assert "sigv4" in capability.tags
    assert "putobject" in capability.tags


def test_selection_gate_accepts_s3_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        S3_ACTUATION_GOAL,
        S3_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(S3_ACTUATION_GOAL)
    assert "object" in family
    assert "store" in family
    assert "bucket" in family
    assert "putobject" in family
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
