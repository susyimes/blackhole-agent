from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.ohttp_actuation import OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID
from blackhole_agent.datachannel_actuation import DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
from blackhole_agent.datagram_actuation import DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID
from blackhole_agent.masque_actuation import MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID
from blackhole_agent.connectip_actuation import (
    DEFAULT_IPADDR,
    DEFAULT_PREFIXID,
    EMPTY_PREFIXID,
    FRAME_ASSIGN,
    CONNECTIP_ACTUATION_DONE_WHEN,
    CONNECTIP_ACTUATION_GOAL,
    CONNECTIP_ACTUATION_ID,
    CONNECTIP_LEFTOVER,
    SENTINEL,
    CIP_FIRST,
    builtin_connectip_actuation_proof,
    crc32c,
    encode_advertise,
    encode_assign,
    independent_connectip_digest,
    parse_message,
    run_connectip_workflow,
)
from blackhole_agent.ice_actuation import ICE_ACTUATION_GOAL, ICE_ACTUATION_ID
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
from blackhole_agent.quic_actuation import QUIC_ACTUATION_GOAL, QUIC_ACTUATION_ID
from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
from blackhole_agent.sctp_actuation import SCTP_ACTUATION_GOAL, SCTP_ACTUATION_ID
from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.srtp_actuation import SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID
from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    CONNECTIP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    connectip_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
    MASQUE_ACTUATION_GOAL,
    DATAGRAM_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_GOAL,
    HTTP3_ACTUATION_GOAL,
    QUIC_ACTUATION_GOAL,
    DATACHANNEL_ACTUATION_GOAL,
    SCTP_ACTUATION_GOAL,
    SRTP_ACTUATION_GOAL,
    DTLS_ACTUATION_GOAL,
    ICE_ACTUATION_GOAL,
    TURN_ACTUATION_GOAL,
    STUN_ACTUATION_GOAL,
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
    OHTTP_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
    MASQUE_ACTUATION_ID,
    DATAGRAM_ACTUATION_ID,
    WEBTRANSPORT_ACTUATION_ID,
    HTTP3_ACTUATION_ID,
    QUIC_ACTUATION_ID,
    DATACHANNEL_ACTUATION_ID,
    SCTP_ACTUATION_ID,
    SRTP_ACTUATION_ID,
    DTLS_ACTUATION_ID,
    ICE_ACTUATION_ID,
    TURN_ACTUATION_ID,
    STUN_ACTUATION_ID,
    SIP_ACTUATION_ID,
    IKE_ACTUATION_ID,
    DHCP_ACTUATION_ID,
    RADIUS_ACTUATION_ID,
    NTP_ACTUATION_ID,
    SYSLOG_ACTUATION_ID,
    SNMP_ACTUATION_ID,
    TFTP_ACTUATION_ID,
    FTP_ACTUATION_ID,
    DNS_ACTUATION_ID,
    OHTTP_ACTUATION_ID,
)


def test_goal_binds_connectip_actuation_plane() -> None:
    assert leftover_marker_ids(CONNECTIP_ACTUATION_GOAL) == (CONNECTIP_ACTUATION_ID,)
    assert leftover_marker_ids(CONNECTIP_LEFTOVER) == (CONNECTIP_ACTUATION_ID,)
    assert CONNECTIP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(OHTTP_ACTUATION_GOAL) == (OHTTP_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert CONNECTIP_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(CONNECTIP_ACTUATION_GOAL)
    connectip_signature = semantic_signature(CONNECTIP_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(connectip_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_connectip_tool_completes_assign_advertise_poll() -> None:
    descriptor = connectip_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CONNECTIP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("connectip",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CONNECTIP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["connectip"]

    missing = run_connectip_workflow(with_prefixid=False)
    skip_bind = run_connectip_workflow(skip_bind=True)
    skip_assign_cycle = run_connectip_workflow(do_assign_cycle=False)
    skip_advertise = run_connectip_workflow(do_advertise=False)
    skip_ipaddr = run_connectip_workflow(do_ipaddr=False)
    skip_replay = run_connectip_workflow(replay=False)
    skip_prefixid = run_connectip_workflow(use_prefixid=False)
    live = run_connectip_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_prefixid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_assign_cycle["ok"] is False
    assert skip_assign_cycle["error"] == "assign_required"
    assert skip_advertise["ok"] is False
    assert skip_advertise["error"] == "advertise_required"
    assert skip_ipaddr["ok"] is False
    assert skip_ipaddr["error"] == "ipaddr_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_prefixid["ok"] is False
    assert skip_prefixid["error"] == "prefixid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_connectip_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["assign"] is True
    assert row["advertise"] is True
    assert row["ipaddr_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["prefixid_bound"] is True
    assert row["digest"]
    assert live["prefixid"] == DEFAULT_PREFIXID
    assert live["ipaddr"] == DEFAULT_IPADDR
    assert int(live["port"]) > 0
    assigned = parse_message(
        encode_assign(identity=SENTINEL, prefixid=DEFAULT_PREFIXID, ipaddr=DEFAULT_IPADDR)
    )
    assert assigned["is_assign"] is True and assigned["is_response"] is False
    assert assigned["identity"] == SENTINEL and assigned["prefixid"] == DEFAULT_PREFIXID
    assert assigned["ipaddr"] == DEFAULT_IPADDR
    assert assigned["type"] == FRAME_ASSIGN
    assert assigned["first_byte"] == CIP_FIRST
    advertised = parse_message(
        encode_advertise(identity=SENTINEL, prefixid=DEFAULT_PREFIXID, ipaddr=DEFAULT_IPADDR)
    )
    assert advertised["is_advertise"] is True and advertised["is_response"] is True
    assert advertised["prefixid"] == DEFAULT_PREFIXID
    assert advertised["ipaddr"] == DEFAULT_IPADDR
    packed = encode_assign(identity=SENTINEL, prefixid=DEFAULT_PREFIXID, ipaddr=DEFAULT_IPADDR)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(encode_assign(identity=SENTINEL, prefixid=DEFAULT_PREFIXID, include_prefixid=False))
    assert bare["has_prefixid"] is False
    assert bare["prefixid"] == EMPTY_PREFIXID


def test_builtin_proof_seals_connectip_actuation() -> None:
    report = builtin_connectip_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "connectip_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_connectip"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_prefixid_is_forbidden"]
    assert report["checks"]["skip_assign_cycle_stays_empty"]
    assert report["checks"]["skip_advertise_stays_empty"]
    assert report["checks"]["skip_ipaddr_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_prefixid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_ipaddr"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_connectip"]
    assert report["checks"]["catalog_names_connectip"]
    assert report["checks"]["catalog_names_ohttp"]
    assert report["checks"]["leftover_text_binds_connectip"]
    assert report["checks"]["proved_connectip_consumes_leftover"]
    assert report["mission_goal"] == CONNECTIP_ACTUATION_GOAL
    assert report["done_when"] == CONNECTIP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[CONNECTIP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "connectip" in capability.tags
    assert "rfc9484" in capability.tags
    assert "http" in capability.tags
    assert "prefixid" in capability.tags
    assert "ipaddr" in capability.tags


def test_selection_gate_accepts_connectip_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        CONNECTIP_ACTUATION_GOAL,
        CONNECTIP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(CONNECTIP_ACTUATION_GOAL)
    assert "connectip" in family
    assert "rfc9484" in family
    assert "prefixid" in family
    assert "ipaddr" in family
    assert "rfc9000" not in family
    assert "http3" not in family
    assert "rfc9114" not in family
    assert "dcid" not in family
    assert "webtransport" not in family
    assert "rfc9220" not in family
    assert "sessionid" not in family
    assert "datagram" not in family
    assert "rfc9221" not in family
    assert "flowid" not in family
    assert "masque" not in family
    assert "rfc9298" not in family
    assert "targetid" not in family
    assert "ohttp" not in family
    assert "rfc9458" not in family
    assert "configid" not in family
