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
from blackhole_agent.sip_actuation import (
    DEFAULT_CALLID,
    SENTINEL,
    SIP_ACTUATION_DONE_WHEN,
    SIP_ACTUATION_GOAL,
    SIP_ACTUATION_ID,
    builtin_sip_actuation_proof,
    encode_invite,
    encode_ok,
    independent_sip_digest,
    parse_message,
    run_sip_workflow,
)
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    SIP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    sip_tool_descriptor,
)


def test_goal_binds_sip_actuation_plane() -> None:
    assert leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    assert SIP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    assert leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    assert leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    assert leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    assert leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    assert leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    assert leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(STUN_ACTUATION_GOAL) == (STUN_ACTUATION_ID,)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert STUN_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    sip_signature = semantic_signature(SIP_ACTUATION_GOAL)
    for neighbor in (
        IKE_ACTUATION_GOAL,
        DHCP_ACTUATION_GOAL,
        RADIUS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        STUN_ACTUATION_GOAL,
    ):
        assert semantic_similarity(sip_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_sip_tool_completes_invite_ok_poll() -> None:
    descriptor = sip_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("sip",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["sip"]

    missing = run_sip_workflow(with_callid=False)
    skip_bind = run_sip_workflow(skip_bind=True)
    skip_invite = run_sip_workflow(do_invite=False)
    skip_ok = run_sip_workflow(do_ok=False)
    skip_replay = run_sip_workflow(replay=False)
    skip_callid = run_sip_workflow(use_callid=False)
    live = run_sip_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_callid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_invite["ok"] is False
    assert skip_invite["error"] == "invite_required"
    assert skip_ok["ok"] is False
    assert skip_ok["error"] == "ok_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_callid["ok"] is False
    assert skip_callid["error"] == "callid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_sip_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["invite"] is True
    assert row["ok_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["callid_bound"] is True
    assert row["digest"]
    assert live["call_id"] == DEFAULT_CALLID
    assert int(live["port"]) > 0
    invite = parse_message(encode_invite(identity=SENTINEL, call_id=DEFAULT_CALLID))
    assert invite["is_invite"] is True and invite["is_response"] is False
    assert invite["identity"] == SENTINEL and invite["call_id"] == DEFAULT_CALLID
    response = parse_message(encode_ok(identity=SENTINEL, call_id=DEFAULT_CALLID))
    assert response["is_ok"] is True and response["is_response"] is True
    assert response["call_id"] == DEFAULT_CALLID
    bare = parse_message(
        encode_invite(identity=SENTINEL, call_id=DEFAULT_CALLID, include_callid=False)
    )
    assert bare["has_callid"] is False


def test_builtin_proof_seals_sip_actuation() -> None:
    report = builtin_sip_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "sip_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_sip"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_callid_is_forbidden"]
    assert report["checks"]["skip_invite_stays_empty"]
    assert report["checks"]["skip_ok_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_callid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_callid"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_sip"]
    assert report["checks"]["catalog_names_stun"]
    assert report["mission_goal"] == SIP_ACTUATION_GOAL
    assert report["done_when"] == SIP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[SIP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "sip" in capability.tags
    assert "rfc3261" in capability.tags
    assert "udp" in capability.tags
    assert "callid" in capability.tags


def test_selection_gate_accepts_sip_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        SIP_ACTUATION_GOAL,
        SIP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(SIP_ACTUATION_GOAL)
    assert "sip" in family
    assert "rfc3261" in family
    assert "callid" in family
    assert "ike" not in family
    assert "rfc7296" not in family
    assert "stun" not in family
    assert "rfc5389" not in family
