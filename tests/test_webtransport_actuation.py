from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.datachannel_actuation import DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    DEFAULT_CAPSULE,
    DEFAULT_SESSIONID,
    EMPTY_SESSIONID,
    FRAME_CONNECT,
    WEBTRANSPORT_ACTUATION_DONE_WHEN,
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
    WEBTRANSPORT_LEFTOVER,
    SENTINEL,
    WT_FIRST,
    builtin_webtransport_actuation_proof,
    crc32c,
    encode_session,
    encode_connect,
    independent_webtransport_digest,
    parse_message,
    run_webtransport_workflow,
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
    WEBTRANSPORT_TOOL_PROVIDER,
    build_tool_routing_preflight,
    webtransport_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.datagram_actuation import (
    DATAGRAM_ACTUATION_GOAL,
    DATAGRAM_ACTUATION_ID,
)

NEIGHBORS = (
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
    DATAGRAM_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    DATAGRAM_ACTUATION_ID,
)


def test_goal_binds_webtransport_actuation_plane() -> None:
    assert leftover_marker_ids(WEBTRANSPORT_ACTUATION_GOAL) == (WEBTRANSPORT_ACTUATION_ID,)
    assert leftover_marker_ids(WEBTRANSPORT_LEFTOVER) == (WEBTRANSPORT_ACTUATION_ID,)
    assert WEBTRANSPORT_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(DATAGRAM_ACTUATION_GOAL) == (DATAGRAM_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert WEBTRANSPORT_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(WEBTRANSPORT_ACTUATION_GOAL)
    webtransport_signature = semantic_signature(WEBTRANSPORT_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(webtransport_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_webtransport_tool_completes_connect_session_poll() -> None:
    descriptor = webtransport_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBTRANSPORT_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("webtransport",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBTRANSPORT_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["webtransport"]

    missing = run_webtransport_workflow(with_sessionid=False)
    skip_bind = run_webtransport_workflow(skip_bind=True)
    skip_connect = run_webtransport_workflow(do_connect=False)
    skip_session = run_webtransport_workflow(do_session=False)
    skip_capsule = run_webtransport_workflow(do_capsule=False)
    skip_replay = run_webtransport_workflow(replay=False)
    skip_sessionid = run_webtransport_workflow(use_sessionid=False)
    live = run_webtransport_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_sessionid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_connect["ok"] is False
    assert skip_connect["error"] == "connect_required"
    assert skip_session["ok"] is False
    assert skip_session["error"] == "session_required"
    assert skip_capsule["ok"] is False
    assert skip_capsule["error"] == "capsule_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_sessionid["ok"] is False
    assert skip_sessionid["error"] == "sessionid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_webtransport_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["connect"] is True
    assert row["session"] is True
    assert row["capsule_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["sessionid_bound"] is True
    assert row["digest"]
    assert live["sessionid"] == DEFAULT_SESSIONID
    assert live["capsule"] == DEFAULT_CAPSULE
    assert int(live["port"]) > 0
    opened = parse_message(
        encode_connect(identity=SENTINEL, sessionid=DEFAULT_SESSIONID, capsule=DEFAULT_CAPSULE)
    )
    assert opened["is_connect"] is True and opened["is_response"] is False
    assert opened["identity"] == SENTINEL and opened["sessionid"] == DEFAULT_SESSIONID
    assert opened["capsule"] == DEFAULT_CAPSULE
    assert opened["type"] == FRAME_CONNECT
    assert opened["first_byte"] == WT_FIRST
    session = parse_message(
        encode_session(identity=SENTINEL, sessionid=DEFAULT_SESSIONID, capsule=DEFAULT_CAPSULE)
    )
    assert session["is_session"] is True and session["is_response"] is True
    assert session["sessionid"] == DEFAULT_SESSIONID
    assert session["capsule"] == DEFAULT_CAPSULE
    packed = encode_connect(identity=SENTINEL, sessionid=DEFAULT_SESSIONID, capsule=DEFAULT_CAPSULE)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(encode_connect(identity=SENTINEL, sessionid=DEFAULT_SESSIONID, include_sessionid=False))
    assert bare["has_sessionid"] is False
    assert bare["sessionid"] == EMPTY_SESSIONID


def test_builtin_proof_seals_webtransport_actuation() -> None:
    report = builtin_webtransport_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "webtransport_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_webtransport"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_sessionid_is_forbidden"]
    assert report["checks"]["skip_connect_stays_empty"]
    assert report["checks"]["skip_session_stays_empty"]
    assert report["checks"]["skip_capsule_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_sessionid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_capsule"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_webtransport"]
    assert report["checks"]["catalog_names_datagram"]
    assert report["checks"]["leftover_text_binds_webtransport"]
    assert report["checks"]["proved_webtransport_consumes_leftover"]
    assert report["mission_goal"] == WEBTRANSPORT_ACTUATION_GOAL
    assert report["done_when"] == WEBTRANSPORT_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[WEBTRANSPORT_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "webtransport" in capability.tags
    assert "rfc9220" in capability.tags
    assert "udp" in capability.tags
    assert "sessionid" in capability.tags
    assert "capsule" in capability.tags


def test_selection_gate_accepts_webtransport_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        WEBTRANSPORT_ACTUATION_GOAL,
        WEBTRANSPORT_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(WEBTRANSPORT_ACTUATION_GOAL)
    assert "webtransport" in family
    assert "rfc9220" in family
    assert "sessionid" in family
    assert "capsule" in family
    assert "rfc9000" not in family
    assert "http3" not in family
    assert "rfc9114" not in family
    assert "dcid" not in family
    assert "datagram" not in family
    assert "rfc9221" not in family
    assert "flowid" not in family
