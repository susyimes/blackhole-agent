from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.datachannel_actuation import DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
from blackhole_agent.datagram_actuation import (
    DEFAULT_CONTEXTID,
    DEFAULT_FLOWID,
    EMPTY_FLOWID,
    FRAME_SEND,
    DATAGRAM_ACTUATION_DONE_WHEN,
    DATAGRAM_ACTUATION_GOAL,
    DATAGRAM_ACTUATION_ID,
    DATAGRAM_LEFTOVER,
    SENTINEL,
    DG_FIRST,
    builtin_datagram_actuation_proof,
    crc32c,
    encode_echo,
    encode_send,
    independent_datagram_digest,
    parse_message,
    run_datagram_workflow,
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
    DATAGRAM_TOOL_PROVIDER,
    build_tool_routing_preflight,
    datagram_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)
from blackhole_agent.masque_actuation import (
    MASQUE_ACTUATION_GOAL,
    MASQUE_ACTUATION_ID,
)

NEIGHBORS = (
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
    MASQUE_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    MASQUE_ACTUATION_ID,
)


def test_goal_binds_datagram_actuation_plane() -> None:
    assert leftover_marker_ids(DATAGRAM_ACTUATION_GOAL) == (DATAGRAM_ACTUATION_ID,)
    assert leftover_marker_ids(DATAGRAM_LEFTOVER) == (DATAGRAM_ACTUATION_ID,)
    assert DATAGRAM_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MASQUE_ACTUATION_GOAL) == (MASQUE_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert DATAGRAM_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(DATAGRAM_ACTUATION_GOAL)
    datagram_signature = semantic_signature(DATAGRAM_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(datagram_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_datagram_tool_completes_send_echo_poll() -> None:
    descriptor = datagram_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DATAGRAM_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("datagram",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DATAGRAM_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["datagram"]

    missing = run_datagram_workflow(with_flowid=False)
    skip_bind = run_datagram_workflow(skip_bind=True)
    skip_send = run_datagram_workflow(do_send=False)
    skip_echo = run_datagram_workflow(do_echo=False)
    skip_contextid = run_datagram_workflow(do_contextid=False)
    skip_replay = run_datagram_workflow(replay=False)
    skip_flowid = run_datagram_workflow(use_flowid=False)
    live = run_datagram_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_flowid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_send["ok"] is False
    assert skip_send["error"] == "send_required"
    assert skip_echo["ok"] is False
    assert skip_echo["error"] == "echo_required"
    assert skip_contextid["ok"] is False
    assert skip_contextid["error"] == "contextid_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_flowid["ok"] is False
    assert skip_flowid["error"] == "flowid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_datagram_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["send"] is True
    assert row["echo"] is True
    assert row["contextid_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["flowid_bound"] is True
    assert row["digest"]
    assert live["flowid"] == DEFAULT_FLOWID
    assert live["contextid"] == DEFAULT_CONTEXTID
    assert int(live["port"]) > 0
    opened = parse_message(
        encode_send(identity=SENTINEL, flowid=DEFAULT_FLOWID, contextid=DEFAULT_CONTEXTID)
    )
    assert opened["is_send"] is True and opened["is_response"] is False
    assert opened["identity"] == SENTINEL and opened["flowid"] == DEFAULT_FLOWID
    assert opened["contextid"] == DEFAULT_CONTEXTID
    assert opened["type"] == FRAME_SEND
    assert opened["first_byte"] == DG_FIRST
    echoed = parse_message(
        encode_echo(identity=SENTINEL, flowid=DEFAULT_FLOWID, contextid=DEFAULT_CONTEXTID)
    )
    assert echoed["is_echo"] is True and echoed["is_response"] is True
    assert echoed["flowid"] == DEFAULT_FLOWID
    assert echoed["contextid"] == DEFAULT_CONTEXTID
    packed = encode_send(identity=SENTINEL, flowid=DEFAULT_FLOWID, contextid=DEFAULT_CONTEXTID)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(encode_send(identity=SENTINEL, flowid=DEFAULT_FLOWID, include_flowid=False))
    assert bare["has_flowid"] is False
    assert bare["flowid"] == EMPTY_FLOWID


def test_builtin_proof_seals_datagram_actuation() -> None:
    report = builtin_datagram_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "datagram_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_datagram"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_flowid_is_forbidden"]
    assert report["checks"]["skip_send_stays_empty"]
    assert report["checks"]["skip_echo_stays_empty"]
    assert report["checks"]["skip_contextid_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_flowid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_contextid"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_datagram"]
    assert report["checks"]["catalog_names_masque"]
    assert report["checks"]["leftover_text_binds_datagram"]
    assert report["checks"]["proved_datagram_consumes_leftover"]
    assert report["mission_goal"] == DATAGRAM_ACTUATION_GOAL
    assert report["done_when"] == DATAGRAM_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[DATAGRAM_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "datagram" in capability.tags
    assert "rfc9221" in capability.tags
    assert "udp" in capability.tags
    assert "flowid" in capability.tags
    assert "contextid" in capability.tags


def test_selection_gate_accepts_datagram_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        DATAGRAM_ACTUATION_GOAL,
        DATAGRAM_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(DATAGRAM_ACTUATION_GOAL)
    assert "datagram" in family
    assert "rfc9221" in family
    assert "flowid" in family
    assert "contextid" in family
    assert "rfc9000" not in family
    assert "http3" not in family
    assert "rfc9114" not in family
    assert "dcid" not in family
    assert "webtransport" not in family
    assert "rfc9220" not in family
    assert "sessionid" not in family
    assert "masque" not in family
    assert "rfc9298" not in family
    assert "targetid" not in family
