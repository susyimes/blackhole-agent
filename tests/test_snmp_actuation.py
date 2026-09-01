from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.snmp_actuation import (
    DEFAULT_COMMUNITY,
    DEFAULT_OID,
    PDU_GET,
    PDU_RESPONSE,
    PDU_SET,
    SENTINEL,
    SNMP_ACTUATION_DONE_WHEN,
    SNMP_ACTUATION_GOAL,
    SNMP_ACTUATION_ID,
    builtin_snmp_actuation_proof,
    encode_message,
    encode_pdu,
    independent_snmp_digest,
    parse_packet,
    run_snmp_workflow,
    sentinel_value,
)
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    SNMP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    snmp_tool_descriptor,
)


def test_goal_binds_snmp_actuation_plane() -> None:
    assert leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    assert SNMP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    snmp_signature = semantic_signature(SNMP_ACTUATION_GOAL)
    for neighbor in (
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
    ):
        assert semantic_similarity(snmp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_snmp_tool_completes_set_get_response_replay() -> None:
    descriptor = snmp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SNMP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("snmp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SNMP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["snmp"]

    missing = run_snmp_workflow(with_community=False)
    skip_bind = run_snmp_workflow(skip_bind=True)
    skip_set = run_snmp_workflow(do_set=False)
    skip_response = run_snmp_workflow(response=False)
    skip_get = run_snmp_workflow(do_get=False)
    skip_replay = run_snmp_workflow(replay=False)
    skip_community = run_snmp_workflow(use_community=False)
    live = run_snmp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_community"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_set["ok"] is False
    assert skip_set["error"] == "set_required"
    assert skip_response["ok"] is False
    assert skip_response["error"] == "response_required"
    assert skip_get["ok"] is False
    assert skip_get["error"] == "get_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_community["ok"] is False
    assert skip_community["error"] == "community_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_snmp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["set"] is True
    assert row["get"] is True
    assert row["response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["community_bound"] is True
    assert row["digest"]
    assert int(live["request_id"]) > 0
    assert int(live["port"]) > 0
    set_pdu = parse_packet(
        encode_message(DEFAULT_COMMUNITY, encode_pdu(PDU_SET, 1, [(DEFAULT_OID, sentinel_value())]))
    )
    assert set_pdu["pdu_type"] == PDU_SET and set_pdu["community"] == DEFAULT_COMMUNITY
    get_pdu = parse_packet(
        encode_message(DEFAULT_COMMUNITY, encode_pdu(PDU_GET, 2, [(DEFAULT_OID, None)]))
    )
    response = parse_packet(
        encode_message(
            DEFAULT_COMMUNITY,
            encode_pdu(PDU_RESPONSE, 2, [(DEFAULT_OID, sentinel_value())]),
        )
    )
    assert get_pdu["varbinds"][0]["value"] is None
    assert response["varbinds"][0]["value"] == sentinel_value()


def test_builtin_proof_seals_snmp_actuation() -> None:
    report = builtin_snmp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "snmp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_snmp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_community_is_forbidden"]
    assert report["checks"]["skip_set_stays_empty"]
    assert report["checks"]["skip_response_stays_empty"]
    assert report["checks"]["skip_get_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_community_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_request_id"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_snmp"]
    assert report["checks"]["catalog_names_syslog"]
    assert report["mission_goal"] == SNMP_ACTUATION_GOAL
    assert report["done_when"] == SNMP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[SNMP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "snmp" in capability.tags
    assert "rfc1157" in capability.tags
    assert "udp" in capability.tags


def test_selection_gate_accepts_snmp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        SNMP_ACTUATION_GOAL,
        SNMP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(SNMP_ACTUATION_GOAL)
    assert "snmp" in family
    assert "rfc1157" in family
    assert "tftp" not in family
    assert "rfc1350" not in family
    assert "syslog" not in family
    assert "nilvalue" not in family
