from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.datachannel_actuation import DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
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
from blackhole_agent.quic_actuation import (
    DEFAULT_DCID,
    DEFAULT_PKTNUM,
    EMPTY_DCID,
    PACKET_INITIAL,
    QUIC_ACTUATION_DONE_WHEN,
    QUIC_ACTUATION_GOAL,
    QUIC_ACTUATION_ID,
    SENTINEL,
    builtin_quic_actuation_proof,
    crc32c,
    encode_handshake,
    encode_initial,
    independent_quic_digest,
    parse_message,
    run_quic_workflow,
)
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
    QUIC_TOOL_PROVIDER,
    build_tool_routing_preflight,
    quic_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

NEIGHBORS = (
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
    HTTP3_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    HTTP3_ACTUATION_ID,
)


def test_goal_binds_quic_actuation_plane() -> None:
    assert leftover_marker_ids(QUIC_ACTUATION_GOAL) == (QUIC_ACTUATION_ID,)
    assert QUIC_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HTTP3_ACTUATION_GOAL) == (HTTP3_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert QUIC_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(QUIC_ACTUATION_GOAL)
    quic_signature = semantic_signature(QUIC_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(quic_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_quic_tool_completes_initial_handshake_poll() -> None:
    descriptor = quic_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, QUIC_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("quic",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, QUIC_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["quic"]

    missing = run_quic_workflow(with_dcid=False)
    skip_bind = run_quic_workflow(skip_bind=True)
    skip_initial = run_quic_workflow(do_initial=False)
    skip_handshake = run_quic_workflow(do_handshake=False)
    skip_pktnum = run_quic_workflow(do_pktnum=False)
    skip_replay = run_quic_workflow(replay=False)
    skip_dcid = run_quic_workflow(use_dcid=False)
    live = run_quic_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_dcid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_initial["ok"] is False
    assert skip_initial["error"] == "initial_required"
    assert skip_handshake["ok"] is False
    assert skip_handshake["error"] == "handshake_required"
    assert skip_pktnum["ok"] is False
    assert skip_pktnum["error"] == "pktnum_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_dcid["ok"] is False
    assert skip_dcid["error"] == "dcid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_quic_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["initial"] is True
    assert row["handshake"] is True
    assert row["pktnum_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["dcid_bound"] is True
    assert row["digest"]
    assert live["dcid"] == DEFAULT_DCID
    assert live["pktnum"] == DEFAULT_PKTNUM
    assert int(live["port"]) > 0
    opened = parse_message(encode_initial(identity=SENTINEL, dcid=DEFAULT_DCID, pktnum=DEFAULT_PKTNUM))
    assert opened["is_initial"] is True and opened["is_response"] is False
    assert opened["identity"] == SENTINEL and opened["dcid"] == DEFAULT_DCID
    assert opened["pktnum"] == DEFAULT_PKTNUM
    assert opened["type"] == PACKET_INITIAL
    handshake = parse_message(encode_handshake(identity=SENTINEL, dcid=DEFAULT_DCID, pktnum=DEFAULT_PKTNUM))
    assert handshake["is_handshake"] is True and handshake["is_response"] is True
    assert handshake["dcid"] == DEFAULT_DCID
    assert handshake["pktnum"] == DEFAULT_PKTNUM
    packed = encode_initial(identity=SENTINEL, dcid=DEFAULT_DCID, pktnum=DEFAULT_PKTNUM)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(encode_initial(identity=SENTINEL, dcid=DEFAULT_DCID, include_dcid=False))
    assert bare["has_dcid"] is False
    assert bare["dcid"] == EMPTY_DCID


def test_builtin_proof_seals_quic_actuation() -> None:
    report = builtin_quic_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "quic_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_quic"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_dcid_is_forbidden"]
    assert report["checks"]["skip_initial_stays_empty"]
    assert report["checks"]["skip_handshake_stays_empty"]
    assert report["checks"]["skip_pktnum_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_dcid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_pktnum"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_quic"]
    assert report["checks"]["catalog_names_http3"]
    assert report["mission_goal"] == QUIC_ACTUATION_GOAL
    assert report["done_when"] == QUIC_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[QUIC_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "quic" in capability.tags
    assert "rfc9000" in capability.tags
    assert "udp" in capability.tags
    assert "dcid" in capability.tags
    assert "pktnum" in capability.tags


def test_selection_gate_accepts_quic_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        QUIC_ACTUATION_GOAL,
        QUIC_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(QUIC_ACTUATION_GOAL)
    assert "quic" in family
    assert "rfc9000" in family
    assert "dcid" in family
    assert "pktnum" in family
    assert "rfc8831" not in family
    assert "ppid" not in family
    assert "http3" not in family
    assert "rfc9114" not in family
    assert "streamid" not in family
