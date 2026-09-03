from pathlib import Path

from blackhole_agent.http11_actuation import HTTP11_ACTUATION_GOAL, HTTP11_ACTUATION_ID
from blackhole_agent.http2_actuation import HTTP2_ACTUATION_GOAL, HTTP2_ACTUATION_ID
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
from blackhole_agent.bhttp_actuation import (
    DEFAULT_MESSAGEID,
    DEFAULT_BINARYMSG,
    EMPTY_MESSAGEID,
    FRAME_ENCODE,
    BHTTP_ACTUATION_DONE_WHEN,
    BHTTP_ACTUATION_GOAL,
    BHTTP_ACTUATION_ID,
    BHTTP_LEFTOVER,
    BH_FIRST,
    FRAMING_KNOWN_REQUEST,
    SENTINEL,
    builtin_bhttp_actuation_proof,
    crc32c,
    decode_known_length_request,
    encode_decode,
    encode_encode,
    encode_known_length_request,
    independent_bhttp_digest,
    parse_message,
    run_bhttp_workflow,
)
from blackhole_agent.digestfields_actuation import DIGESTFIELDS_ACTUATION_GOAL, DIGESTFIELDS_ACTUATION_ID
from blackhole_agent.httpsig_actuation import HTTPSIG_ACTUATION_GOAL, HTTPSIG_ACTUATION_ID
from blackhole_agent.ohsvcb_actuation import OHSVCB_ACTUATION_GOAL, OHSVCB_ACTUATION_ID
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
    BHTTP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    bhttp_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
    DIGESTFIELDS_ACTUATION_GOAL,
    HTTPSIG_ACTUATION_GOAL,
    OHSVCB_ACTUATION_GOAL,
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
    HTTP11_ACTUATION_GOAL,
    HTTP2_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
    DIGESTFIELDS_ACTUATION_ID,
    HTTPSIG_ACTUATION_ID,
    OHSVCB_ACTUATION_ID,
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
    HTTP11_ACTUATION_ID,
    HTTP2_ACTUATION_ID,
)


def test_goal_binds_bhttp_actuation_plane() -> None:
    assert leftover_marker_ids(BHTTP_ACTUATION_GOAL) == (BHTTP_ACTUATION_ID,)
    assert leftover_marker_ids(BHTTP_LEFTOVER) == (BHTTP_ACTUATION_ID,)
    assert BHTTP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HTTP11_ACTUATION_GOAL) == (HTTP11_ACTUATION_ID,)
    assert leftover_marker_ids(HTTP2_ACTUATION_GOAL) == (HTTP2_ACTUATION_ID,)
    assert leftover_marker_ids(DIGESTFIELDS_ACTUATION_GOAL) == (DIGESTFIELDS_ACTUATION_ID,)
    assert HTTP11_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTP2_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert BHTTP_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(BHTTP_ACTUATION_GOAL)
    bhttp_signature = semantic_signature(BHTTP_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(bhttp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_bhttp_tool_completes_encode_decode_poll() -> None:
    descriptor = bhttp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BHTTP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("bhttp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, BHTTP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["bhttp"]

    missing = run_bhttp_workflow(with_messageid=False)
    skip_bind = run_bhttp_workflow(skip_bind=True)
    skip_encode_cycle = run_bhttp_workflow(do_encode_cycle=False)
    skip_decode = run_bhttp_workflow(do_decode=False)
    skip_binarymsg = run_bhttp_workflow(do_binarymsg=False)
    skip_replay = run_bhttp_workflow(replay=False)
    skip_messageid = run_bhttp_workflow(use_messageid=False)
    live = run_bhttp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_messageid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_encode_cycle["ok"] is False
    assert skip_encode_cycle["error"] == "encode_required"
    assert skip_decode["ok"] is False
    assert skip_decode["error"] == "decode_required"
    assert skip_binarymsg["ok"] is False
    assert skip_binarymsg["error"] == "binarymsg_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_messageid["ok"] is False
    assert skip_messageid["error"] == "messageid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_bhttp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["encode_frame"] is True
    assert row["decode"] is True
    assert row["binarymsg_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["messageid_bound"] is True
    assert row["digest"]
    assert live["messageid"] == DEFAULT_MESSAGEID
    assert live["binarymsg"] == DEFAULT_BINARYMSG
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_encode(identity=SENTINEL, messageid=DEFAULT_MESSAGEID, binarymsg=DEFAULT_BINARYMSG)
    )
    assert queried["is_encode"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["messageid"] == DEFAULT_MESSAGEID
    assert queried["binarymsg"] == DEFAULT_BINARYMSG
    assert queried["type"] == FRAME_ENCODE
    assert queried["first_byte"] == BH_FIRST
    answered = parse_message(
        encode_decode(identity=SENTINEL, messageid=DEFAULT_MESSAGEID, binarymsg=DEFAULT_BINARYMSG)
    )
    assert answered["is_decode"] is True and answered["is_response"] is True
    assert answered["messageid"] == DEFAULT_MESSAGEID
    assert answered["binarymsg"] == DEFAULT_BINARYMSG
    packed = encode_encode(identity=SENTINEL, messageid=DEFAULT_MESSAGEID, binarymsg=DEFAULT_BINARYMSG)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_encode(identity=SENTINEL, messageid=DEFAULT_MESSAGEID, include_messageid=False)
    )
    assert bare["has_messageid"] is False
    assert bare["messageid"] == EMPTY_MESSAGEID
    request = encode_known_length_request(
        method="POST",
        scheme="https",
        authority=SENTINEL,
        path=f"/bhttp/{DEFAULT_MESSAGEID:08x}",
        headers=(("content-type", "application/octet-stream"),),
        content=f"{SENTINEL}:{DEFAULT_MESSAGEID:08x}".encode("utf-8"),
    )
    decoded = decode_known_length_request(request)
    assert decoded["framing_indicator"] == FRAMING_KNOWN_REQUEST
    assert decoded["method"] == "POST"
    assert decoded["path"] == f"/bhttp/{DEFAULT_MESSAGEID:08x}"


def test_builtin_proof_seals_bhttp_actuation() -> None:
    report = builtin_bhttp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "bhttp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_bhttp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_messageid_is_forbidden"]
    assert report["checks"]["skip_encode_cycle_stays_empty"]
    assert report["checks"]["skip_decode_stays_empty"]
    assert report["checks"]["skip_binarymsg_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_messageid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_binarymsg"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_bhttp"]
    assert report["checks"]["catalog_names_bhttp"]
    assert report["checks"]["catalog_names_http11"]
    assert report["checks"]["catalog_names_http2"]
    assert report["checks"]["leftover_text_binds_bhttp"]
    assert report["checks"]["proved_bhttp_consumes_leftover"]
    assert report["mission_goal"] == BHTTP_ACTUATION_GOAL
    assert report["done_when"] == BHTTP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[BHTTP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "bhttp" in capability.tags
    assert "rfc9292" in capability.tags
    assert "http" in capability.tags
    assert "messageid" in capability.tags
    assert "binarymsg" in capability.tags


def test_selection_gate_accepts_bhttp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        BHTTP_ACTUATION_GOAL,
        BHTTP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(BHTTP_ACTUATION_GOAL)
    assert "bhttp" in family
    assert "rfc9292" in family
    assert "messageid" in family
    assert "binarymsg" in family
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
    assert "ohsvcb" not in family
    assert "rfc9540" not in family
    assert "svcbid" not in family
    assert "digestfield" not in family
    assert "rfc9530" not in family
    assert "digestid" not in family
    assert "http11" not in family
    assert "rfc9112" not in family
    assert "requestid" not in family
    assert "http2" not in family
    assert "rfc9113" not in family
    assert "settingsid" not in family
