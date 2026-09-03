from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.connectip_actuation import CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID
from blackhole_agent.datachannel_actuation import DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
from blackhole_agent.datagram_actuation import DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID
from blackhole_agent.masque_actuation import MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID
from blackhole_agent.ohttp_actuation import OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID
from blackhole_agent.ohsvcb_actuation import (
    DEFAULT_SVCBID,
    DEFAULT_KEYCONF,
    EMPTY_SVCBID,
    FRAME_QUERY,
    OHSVCB_ACTUATION_DONE_WHEN,
    OHSVCB_ACTUATION_GOAL,
    OHSVCB_ACTUATION_ID,
    OHSVCB_LEFTOVER,
    OS_FIRST,
    SENTINEL,
    builtin_ohsvcb_actuation_proof,
    crc32c,
    encode_answer,
    encode_query,
    independent_ohsvcb_digest,
    parse_message,
    run_ohsvcb_workflow,
)
from blackhole_agent.httpsig_actuation import HTTPSIG_ACTUATION_GOAL, HTTPSIG_ACTUATION_ID
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
    OHSVCB_TOOL_PROVIDER,
    build_tool_routing_preflight,
    ohsvcb_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
    OHTTP_ACTUATION_GOAL,
    CONNECTIP_ACTUATION_GOAL,
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
    HTTPSIG_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
    OHTTP_ACTUATION_ID,
    CONNECTIP_ACTUATION_ID,
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
    HTTPSIG_ACTUATION_ID,
)


def test_goal_binds_ohsvcb_actuation_plane() -> None:
    assert leftover_marker_ids(OHSVCB_ACTUATION_GOAL) == (OHSVCB_ACTUATION_ID,)
    assert leftover_marker_ids(OHSVCB_LEFTOVER) == (OHSVCB_ACTUATION_ID,)
    assert OHSVCB_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HTTPSIG_ACTUATION_GOAL) == (HTTPSIG_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert OHSVCB_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(OHSVCB_ACTUATION_GOAL)
    ohsvcb_signature = semantic_signature(OHSVCB_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(ohsvcb_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_ohsvcb_tool_completes_query_answer_poll() -> None:
    descriptor = ohsvcb_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, OHSVCB_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("ohsvcb",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, OHSVCB_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["ohsvcb"]

    missing = run_ohsvcb_workflow(with_svcbid=False)
    skip_bind = run_ohsvcb_workflow(skip_bind=True)
    skip_query_cycle = run_ohsvcb_workflow(do_query_cycle=False)
    skip_answer = run_ohsvcb_workflow(do_answer=False)
    skip_keyconf = run_ohsvcb_workflow(do_keyconf=False)
    skip_replay = run_ohsvcb_workflow(replay=False)
    skip_svcbid = run_ohsvcb_workflow(use_svcbid=False)
    live = run_ohsvcb_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_svcbid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_query_cycle["ok"] is False
    assert skip_query_cycle["error"] == "query_required"
    assert skip_answer["ok"] is False
    assert skip_answer["error"] == "answer_required"
    assert skip_keyconf["ok"] is False
    assert skip_keyconf["error"] == "keyconf_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_svcbid["ok"] is False
    assert skip_svcbid["error"] == "svcbid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_ohsvcb_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["query"] is True
    assert row["answer"] is True
    assert row["keyconf_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["svcbid_bound"] is True
    assert row["digest"]
    assert live["svcbid"] == DEFAULT_SVCBID
    assert live["keyconf"] == DEFAULT_KEYCONF
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_query(identity=SENTINEL, svcbid=DEFAULT_SVCBID, keyconf=DEFAULT_KEYCONF)
    )
    assert queried["is_query"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["svcbid"] == DEFAULT_SVCBID
    assert queried["keyconf"] == DEFAULT_KEYCONF
    assert queried["type"] == FRAME_QUERY
    assert queried["first_byte"] == OS_FIRST
    answered = parse_message(
        encode_answer(identity=SENTINEL, svcbid=DEFAULT_SVCBID, keyconf=DEFAULT_KEYCONF)
    )
    assert answered["is_answer"] is True and answered["is_response"] is True
    assert answered["svcbid"] == DEFAULT_SVCBID
    assert answered["keyconf"] == DEFAULT_KEYCONF
    packed = encode_query(identity=SENTINEL, svcbid=DEFAULT_SVCBID, keyconf=DEFAULT_KEYCONF)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_query(identity=SENTINEL, svcbid=DEFAULT_SVCBID, include_svcbid=False)
    )
    assert bare["has_svcbid"] is False
    assert bare["svcbid"] == EMPTY_SVCBID


def test_builtin_proof_seals_ohsvcb_actuation() -> None:
    report = builtin_ohsvcb_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "ohsvcb_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_ohsvcb"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_svcbid_is_forbidden"]
    assert report["checks"]["skip_query_cycle_stays_empty"]
    assert report["checks"]["skip_answer_stays_empty"]
    assert report["checks"]["skip_keyconf_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_svcbid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_keyconf"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_ohsvcb"]
    assert report["checks"]["catalog_names_ohsvcb"]
    assert report["checks"]["catalog_names_httpsig"]
    assert report["checks"]["leftover_text_binds_ohsvcb"]
    assert report["checks"]["proved_ohsvcb_consumes_leftover"]
    assert report["mission_goal"] == OHSVCB_ACTUATION_GOAL
    assert report["done_when"] == OHSVCB_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[OHSVCB_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "ohsvcb" in capability.tags
    assert "rfc9540" in capability.tags
    assert "dns" in capability.tags
    assert "svcbid" in capability.tags
    assert "keyconf" in capability.tags


def test_selection_gate_accepts_ohsvcb_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        OHSVCB_ACTUATION_GOAL,
        OHSVCB_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(OHSVCB_ACTUATION_GOAL)
    assert "ohsvcb" in family
    assert "rfc9540" in family
    assert "svcbid" in family
    assert "keyconf" in family
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
    assert "connectip" not in family
    assert "rfc9484" not in family
    assert "prefixid" not in family
    assert "ohttp" not in family
    assert "rfc9458" not in family
    assert "configid" not in family
    assert "httpsig" not in family
    assert "rfc9421" not in family
    assert "sigid" not in family
