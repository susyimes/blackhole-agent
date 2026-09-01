from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dhcp_actuation import (
    BOOTREPLY,
    BOOTREQUEST,
    DEFAULT_XID,
    DEFAULT_YIADDR,
    DHCPACK,
    DHCPDISCOVER,
    DHCPOFFER,
    SENTINEL,
    DHCP_ACTUATION_DONE_WHEN,
    DHCP_ACTUATION_GOAL,
    DHCP_ACTUATION_ID,
    builtin_dhcp_actuation_proof,
    encode_ack,
    encode_discover,
    encode_offer,
    independent_dhcp_digest,
    parse_packet,
    run_dhcp_workflow,
)
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
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    DHCP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    dhcp_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_dhcp_actuation_plane() -> None:
    assert leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    assert DHCP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    assert leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    assert leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    assert leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    assert leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    dhcp_signature = semantic_signature(DHCP_ACTUATION_GOAL)
    for neighbor in (
        RADIUS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        IKE_ACTUATION_GOAL,
    ):
        assert semantic_similarity(dhcp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_dhcp_tool_completes_discover_offer_ack_poll() -> None:
    descriptor = dhcp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DHCP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("dhcp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DHCP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["dhcp"]

    missing = run_dhcp_workflow(with_xid=False)
    skip_bind = run_dhcp_workflow(skip_bind=True)
    skip_discover = run_dhcp_workflow(do_discover=False)
    skip_offer = run_dhcp_workflow(do_offer=False)
    skip_ack = run_dhcp_workflow(do_ack=False)
    skip_replay = run_dhcp_workflow(replay=False)
    skip_xid = run_dhcp_workflow(use_xid=False)
    live = run_dhcp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_xid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_discover["ok"] is False
    assert skip_discover["error"] == "discover_required"
    assert skip_offer["ok"] is False
    assert skip_offer["error"] == "offer_required"
    assert skip_ack["ok"] is False
    assert skip_ack["error"] == "ack_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_xid["ok"] is False
    assert skip_xid["error"] == "xid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_dhcp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["discover"] is True
    assert row["offer"] is True
    assert row["ack"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["xid_bound"] is True
    assert row["digest"]
    assert live["yiaddr"] == DEFAULT_YIADDR
    assert int(live["port"]) > 0
    discover = parse_packet(encode_discover(xid=DEFAULT_XID, hostname=SENTINEL))
    assert discover["op"] == BOOTREQUEST and discover["msg_type"] == DHCPDISCOVER
    assert discover["hostname"] == SENTINEL and discover["xid"] == DEFAULT_XID
    offer = parse_packet(encode_offer(xid=DEFAULT_XID, hostname=SENTINEL))
    assert offer["op"] == BOOTREPLY and offer["msg_type"] == DHCPOFFER
    assert offer["yiaddr"] == DEFAULT_YIADDR
    ack = parse_packet(encode_ack(xid=DEFAULT_XID, hostname=SENTINEL))
    assert ack["op"] == BOOTREPLY and ack["msg_type"] == DHCPACK
    assert ack["yiaddr"] == DEFAULT_YIADDR
    bare = parse_packet(encode_discover(xid=DEFAULT_XID, hostname=SENTINEL, include_xid=False))
    assert bare["has_xid"] is False


def test_builtin_proof_seals_dhcp_actuation() -> None:
    report = builtin_dhcp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "dhcp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_dhcp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_xid_is_forbidden"]
    assert report["checks"]["skip_discover_stays_empty"]
    assert report["checks"]["skip_offer_stays_empty"]
    assert report["checks"]["skip_ack_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_xid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_yiaddr"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_dhcp"]
    assert report["checks"]["catalog_names_ike"]
    assert report["mission_goal"] == DHCP_ACTUATION_GOAL
    assert report["done_when"] == DHCP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[DHCP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "dhcp" in capability.tags
    assert "rfc2131" in capability.tags
    assert "udp" in capability.tags


def test_selection_gate_accepts_dhcp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        DHCP_ACTUATION_GOAL,
        DHCP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(DHCP_ACTUATION_GOAL)
    assert "dhcp" in family
    assert "rfc2131" in family
    assert "radius" not in family
    assert "rfc2865" not in family
    assert "ike" not in family
    assert "rfc7296" not in family
