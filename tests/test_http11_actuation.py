from pathlib import Path

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
from blackhole_agent.http11_actuation import (
    DEFAULT_REQUESTID,
    DEFAULT_STARTLINE,
    EMPTY_REQUESTID,
    FRAME_PARSE,
    HTTP11_ACTUATION_DONE_WHEN,
    HTTP11_ACTUATION_GOAL,
    HTTP11_ACTUATION_ID,
    HTTP11_LEFTOVER,
    HTTP_VERSION,
    H11_FIRST,
    SENTINEL,
    builtin_http11_actuation_proof,
    crc32c,
    encode_parse,
    encode_serialize,
    independent_http11_digest,
    parse_message,
    parse_request,
    run_http11_workflow,
    serialize_request,
)
from blackhole_agent.bhttp_actuation import BHTTP_ACTUATION_GOAL, BHTTP_ACTUATION_ID
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
    HTTP11_TOOL_PROVIDER,
    build_tool_routing_preflight,
    http11_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
    BHTTP_ACTUATION_GOAL,
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
    HTTP2_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
    BHTTP_ACTUATION_ID,
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
    HTTP2_ACTUATION_ID,
)


def test_goal_binds_http11_actuation_plane() -> None:
    assert leftover_marker_ids(HTTP11_ACTUATION_GOAL) == (HTTP11_ACTUATION_ID,)
    assert leftover_marker_ids(HTTP11_LEFTOVER) == (HTTP11_ACTUATION_ID,)
    assert HTTP11_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HTTP2_ACTUATION_GOAL) == (HTTP2_ACTUATION_ID,)
    assert leftover_marker_ids(BHTTP_ACTUATION_GOAL) == (BHTTP_ACTUATION_ID,)
    assert HTTP2_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert HTTP11_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(HTTP11_ACTUATION_GOAL)
    http11_signature = semantic_signature(HTTP11_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(http11_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_http11_tool_completes_parse_serialize_poll() -> None:
    descriptor = http11_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP11_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("http11",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP11_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["http11"]

    missing = run_http11_workflow(with_requestid=False)
    skip_bind = run_http11_workflow(skip_bind=True)
    skip_parse_cycle = run_http11_workflow(do_parse_cycle=False)
    skip_serialize = run_http11_workflow(do_serialize=False)
    skip_startline = run_http11_workflow(do_startline=False)
    skip_replay = run_http11_workflow(replay=False)
    skip_requestid = run_http11_workflow(use_requestid=False)
    live = run_http11_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_requestid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_parse_cycle["ok"] is False
    assert skip_parse_cycle["error"] == "parse_required"
    assert skip_serialize["ok"] is False
    assert skip_serialize["error"] == "serialize_required"
    assert skip_startline["ok"] is False
    assert skip_startline["error"] == "startline_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_requestid["ok"] is False
    assert skip_requestid["error"] == "requestid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_http11_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["parse_frame"] is True
    assert row["serialize"] is True
    assert row["startline_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["requestid_bound"] is True
    assert row["digest"]
    assert live["requestid"] == DEFAULT_REQUESTID
    assert live["startline"] == DEFAULT_STARTLINE
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_parse(identity=SENTINEL, requestid=DEFAULT_REQUESTID, startline=DEFAULT_STARTLINE)
    )
    assert queried["is_parse"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["requestid"] == DEFAULT_REQUESTID
    assert queried["startline"] == DEFAULT_STARTLINE
    assert queried["type"] == FRAME_PARSE
    assert queried["first_byte"] == H11_FIRST
    answered = parse_message(
        encode_serialize(identity=SENTINEL, requestid=DEFAULT_REQUESTID, startline=DEFAULT_STARTLINE)
    )
    assert answered["is_serialize"] is True and answered["is_response"] is True
    assert answered["requestid"] == DEFAULT_REQUESTID
    assert answered["startline"] == DEFAULT_STARTLINE
    packed = encode_parse(identity=SENTINEL, requestid=DEFAULT_REQUESTID, startline=DEFAULT_STARTLINE)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_parse(identity=SENTINEL, requestid=DEFAULT_REQUESTID, include_requestid=False)
    )
    assert bare["has_requestid"] is False
    assert bare["requestid"] == EMPTY_REQUESTID
    body = f"{SENTINEL}:{DEFAULT_REQUESTID:08x}".encode("ascii")
    request = serialize_request(
        method="POST",
        target=f"/http11/{DEFAULT_REQUESTID:08x}",
        version=HTTP_VERSION,
        headers=(
            ("Host", SENTINEL),
            ("Content-Type", "application/octet-stream"),
            ("Content-Length", str(len(body))),
        ),
        body=body,
    )
    decoded = parse_request(request)
    assert decoded["version"] == HTTP_VERSION
    assert decoded["method"] == "POST"
    assert decoded["target"] == f"/http11/{DEFAULT_REQUESTID:08x}"
    assert decoded["start_line"] == f"POST /http11/{DEFAULT_REQUESTID:08x} {HTTP_VERSION}"
    assert decoded["body"] == body


def test_builtin_proof_seals_http11_actuation() -> None:
    report = builtin_http11_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "http11_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_http11"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_requestid_is_forbidden"]
    assert report["checks"]["skip_parse_cycle_stays_empty"]
    assert report["checks"]["skip_serialize_stays_empty"]
    assert report["checks"]["skip_startline_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_requestid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_startline"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_http11"]
    assert report["checks"]["catalog_names_http11"]
    assert report["checks"]["catalog_names_http2"]
    assert report["checks"]["leftover_text_binds_http11"]
    assert report["checks"]["proved_http11_consumes_leftover"]
    assert report["mission_goal"] == HTTP11_ACTUATION_GOAL
    assert report["done_when"] == HTTP11_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[HTTP11_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "http11" in capability.tags
    assert "rfc9112" in capability.tags
    assert "http" in capability.tags
    assert "requestid" in capability.tags
    assert "startline" in capability.tags
    assert "httpmessage" in capability.tags


def test_selection_gate_accepts_http11_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        HTTP11_ACTUATION_GOAL,
        HTTP11_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(HTTP11_ACTUATION_GOAL)
    assert "http11" in family
    assert "rfc9112" in family
    assert "requestid" in family
    assert "startline" in family
    assert "httpmessage" in family
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
    assert "bhttp" not in family
    assert "rfc9292" not in family
    assert "messageid" not in family
    assert "http2" not in family
    assert "rfc9113" not in family
    assert "settingsid" not in family
    assert "hpack" not in family
