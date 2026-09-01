from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.ike_actuation import IKE_ACTUATION_GOAL, IKE_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.stun_actuation import (
    DEFAULT_TXID,
    DEFAULT_TXID_HEX,
    SENTINEL,
    STUN_ACTUATION_DONE_WHEN,
    STUN_ACTUATION_GOAL,
    STUN_ACTUATION_ID,
    builtin_stun_actuation_proof,
    encode_request,
    encode_success,
    independent_stun_digest,
    parse_message,
    run_stun_workflow,
)
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    STUN_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    stun_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID


def test_goal_binds_stun_actuation_plane() -> None:
    assert leftover_marker_ids(STUN_ACTUATION_GOAL) == (STUN_ACTUATION_ID,)
    assert STUN_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    assert leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    assert leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    assert leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    assert leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    assert leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    assert leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    assert leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(TURN_ACTUATION_GOAL) == (TURN_ACTUATION_ID,)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert TURN_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    stun_signature = semantic_signature(STUN_ACTUATION_GOAL)
    for neighbor in (
        SIP_ACTUATION_GOAL,
        IKE_ACTUATION_GOAL,
        DHCP_ACTUATION_GOAL,
        RADIUS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        TURN_ACTUATION_GOAL,
    ):
        assert semantic_similarity(stun_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_stun_tool_completes_binding_success_poll() -> None:
    descriptor = stun_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STUN_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("stun",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STUN_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["stun"]

    missing = run_stun_workflow(with_txid=False)
    skip_bind = run_stun_workflow(skip_bind=True)
    skip_request = run_stun_workflow(do_request=False)
    skip_success = run_stun_workflow(do_success=False)
    skip_replay = run_stun_workflow(replay=False)
    skip_txid = run_stun_workflow(use_txid=False)
    live = run_stun_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_txid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_request["ok"] is False
    assert skip_request["error"] == "request_required"
    assert skip_success["ok"] is False
    assert skip_success["error"] == "success_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_txid["ok"] is False
    assert skip_txid["error"] == "txid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_stun_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["request"] is True
    assert row["success_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["txid_bound"] is True
    assert row["digest"]
    assert live["txid"] == DEFAULT_TXID_HEX
    assert int(live["port"]) > 0
    request = parse_message(encode_request(identity=SENTINEL, txid=DEFAULT_TXID))
    assert request["is_request"] is True and request["is_response"] is False
    assert request["identity"] == SENTINEL and request["txid"] == DEFAULT_TXID
    response = parse_message(encode_success(identity=SENTINEL, txid=DEFAULT_TXID))
    assert response["is_success"] is True and response["is_response"] is True
    assert response["txid"] == DEFAULT_TXID
    bare = parse_message(
        encode_request(identity=SENTINEL, txid=DEFAULT_TXID, include_txid=False)
    )
    assert bare["has_txid"] is False


def test_builtin_proof_seals_stun_actuation() -> None:
    report = builtin_stun_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "stun_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_stun"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_txid_is_forbidden"]
    assert report["checks"]["skip_request_stays_empty"]
    assert report["checks"]["skip_success_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_txid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_txid"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_stun"]
    assert report["checks"]["catalog_names_turn"]
    assert report["mission_goal"] == STUN_ACTUATION_GOAL
    assert report["done_when"] == STUN_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[STUN_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "stun" in capability.tags
    assert "rfc5389" in capability.tags
    assert "udp" in capability.tags
    assert "txid" in capability.tags


def test_selection_gate_accepts_stun_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        STUN_ACTUATION_GOAL,
        STUN_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(STUN_ACTUATION_GOAL)
    assert "stun" in family
    assert "rfc5389" in family
    assert "txid" in family
    assert "sip" not in family
    assert "rfc3261" not in family
    assert "turn" not in family
    assert "rfc5766" not in family
