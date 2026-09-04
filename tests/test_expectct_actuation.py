from pathlib import Path

from blackhole_agent.xfo_actuation import (
    XFO_ACTUATION_GOAL,
    XFO_ACTUATION_ID,
)
from blackhole_agent.hpkp_actuation import (
    HPKP_ACTUATION_GOAL,
    HPKP_ACTUATION_ID,
)
from blackhole_agent.hsts_actuation import (
    HSTS_ACTUATION_GOAL,
    HSTS_ACTUATION_ID,
)
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
from blackhole_agent.http11_actuation import HTTP11_ACTUATION_GOAL, HTTP11_ACTUATION_ID
from blackhole_agent.http2_actuation import HTTP2_ACTUATION_GOAL, HTTP2_ACTUATION_ID
from blackhole_agent.httpcache_actuation import HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID
from blackhole_agent.httpsemantics_actuation import HTTPSMANTICS_ACTUATION_GOAL, HTTPSMANTICS_ACTUATION_ID
from blackhole_agent.clienthints_actuation import CLIENTHINTS_ACTUATION_GOAL, CLIENTHINTS_ACTUATION_ID
from blackhole_agent.structuredfields_actuation import (
    STRUCTUREDFIELDS_ACTUATION_GOAL,
    STRUCTUREDFIELDS_ACTUATION_ID,
)
from blackhole_agent.earlyhints_actuation import EARLYHINTS_ACTUATION_GOAL, EARLYHINTS_ACTUATION_ID
from blackhole_agent.encryptedcontent_actuation import (
    ENCRYPTEDCONTENT_ACTUATION_GOAL,
    ENCRYPTEDCONTENT_ACTUATION_ID,
)
from blackhole_agent.altsvc_actuation import ALTSVC_ACTUATION_GOAL, ALTSVC_ACTUATION_ID
from blackhole_agent.expectct_actuation import (
    DEFAULT_CTID,
    DEFAULT_CTDIGEST,
    DEFAULT_CT,
    EMPTY_CTID,
    FRAME_REPORT,
    FRAME_EXPECT,
    EXPECTCT_ACTUATION_DONE_WHEN,
    EXPECTCT_ACTUATION_GOAL,
    EXPECTCT_ACTUATION_ID,
    EXPECTCT_LEFTOVER,
    CT_FIRST,
    REPORT_CT,
    RFC_CT_FIELD,
    RFC_CT_REPORT,
    SENTINEL,
    CT_HEADER,
    builtin_expectct_actuation_proof,
    canonical_report,
    canonical_expect,
    crc32c,
    encode_report,
    encode_expect,
    encode_ct_header,
    independent_expectct_digest,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_ct,
    parse_ct_header,
    report_request,
    report_response,
    run_expectct_workflow,
    serialize_ct,
    expect_request,
    expect_response,
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
    EXPECTCT_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    build_tool_routing_preflight,
    expectct_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
    ALTSVC_ACTUATION_GOAL,
    ENCRYPTEDCONTENT_ACTUATION_GOAL,
    EARLYHINTS_ACTUATION_GOAL,
    CLIENTHINTS_ACTUATION_GOAL,
    STRUCTUREDFIELDS_ACTUATION_GOAL,
    HTTPSMANTICS_ACTUATION_GOAL,
    HTTPCACHE_ACTUATION_GOAL,
    HTTP2_ACTUATION_GOAL,
    HTTP11_ACTUATION_GOAL,
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
    HSTS_ACTUATION_GOAL,
    HPKP_ACTUATION_GOAL,
    XFO_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
    ALTSVC_ACTUATION_ID,
    ENCRYPTEDCONTENT_ACTUATION_ID,
    EARLYHINTS_ACTUATION_ID,
    CLIENTHINTS_ACTUATION_ID,
    STRUCTUREDFIELDS_ACTUATION_ID,
    HTTPSMANTICS_ACTUATION_ID,
    HTTPCACHE_ACTUATION_ID,
    HTTP2_ACTUATION_ID,
    HTTP11_ACTUATION_ID,
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
    HSTS_ACTUATION_ID,
    HPKP_ACTUATION_ID,
    XFO_ACTUATION_ID,
)


def test_goal_binds_expectct_actuation_plane() -> None:
    assert leftover_marker_ids(EXPECTCT_ACTUATION_GOAL) == (EXPECTCT_ACTUATION_ID,)
    assert leftover_marker_ids(EXPECTCT_LEFTOVER) == (EXPECTCT_ACTUATION_ID,)
    assert EXPECTCT_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HSTS_ACTUATION_GOAL) == (HSTS_ACTUATION_ID,)
    assert leftover_marker_ids(HPKP_ACTUATION_GOAL) == (HPKP_ACTUATION_ID,)
    assert leftover_marker_ids(XFO_ACTUATION_GOAL) == (XFO_ACTUATION_ID,)
    assert leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (ALTSVC_ACTUATION_ID,)
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert HSTS_ACTUATION_ID in LOCAL_DENYLIST
    assert HPKP_ACTUATION_ID in LOCAL_DENYLIST
    assert XFO_ACTUATION_ID in LOCAL_DENYLIST
    assert ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert EXPECTCT_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(EXPECTCT_ACTUATION_GOAL)
    expectct_signature = semantic_signature(EXPECTCT_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(expectct_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_expectct_tool_completes_pin_report_poll() -> None:
    descriptor = expectct_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EXPECTCT_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("expectct",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EXPECTCT_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["expectct"]

    missing = run_expectct_workflow(with_ctid=False)
    skip_bind = run_expectct_workflow(skip_bind=True)
    skip_expect = run_expectct_workflow(do_expect=False)
    skip_report = run_expectct_workflow(do_report=False)
    skip_ctdigest = run_expectct_workflow(do_ctdigest=False)
    skip_replay = run_expectct_workflow(replay=False)
    skip_ctid = run_expectct_workflow(use_ctid=False)
    live = run_expectct_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_ctid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_expect["ok"] is False
    assert skip_expect["error"] == "expect_required"
    assert skip_report["ok"] is False
    assert skip_report["error"] == "report_required"
    assert skip_ctdigest["ok"] is False
    assert skip_ctdigest["error"] == "ctdigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_ctid["ok"] is False
    assert skip_ctid["error"] == "ctid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_expectct_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["expect_frame"] is True
    assert row["report_frame"] is True
    assert row["ctdigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["ctid_bound"] is True
    assert row["digest"]
    assert live["ctid"] == DEFAULT_CTID
    assert live["ctdigest"] == DEFAULT_CTDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_expect(identity=SENTINEL, ctid=DEFAULT_CTID, ctdigest=DEFAULT_CTDIGEST)
    )
    assert queried["is_expect"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["ctid"] == DEFAULT_CTID
    assert queried["ctdigest"] == DEFAULT_CTDIGEST
    assert queried["type"] == FRAME_EXPECT
    assert queried["first_byte"] == CT_FIRST
    answered = parse_message(
        encode_report(identity=SENTINEL, ctid=DEFAULT_CTID, ctdigest=DEFAULT_CTDIGEST)
    )
    assert answered["is_report"] is True and answered["is_response"] is True
    assert answered["ctid"] == DEFAULT_CTID
    assert answered["ctdigest"] == DEFAULT_CTDIGEST
    packed = encode_expect(identity=SENTINEL, ctid=DEFAULT_CTID, ctdigest=DEFAULT_CTDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_expect(identity=SENTINEL, ctid=DEFAULT_CTID, include_ctid=False)
    )
    assert bare["has_ctid"] is False
    assert bare["ctid"] == EMPTY_CTID
    advertised = serialize_ct(DEFAULT_CT)
    assert advertised == RFC_CT_FIELD
    assert parse_ct(advertised) == DEFAULT_CT
    assert parse_ct(RFC_CT_REPORT) == REPORT_CT
    header = parse_ct_header(encode_ct_header(DEFAULT_CT))
    assert header["field_value"] == RFC_CT_FIELD
    assert header["header"] == CT_HEADER
    asked = parse_http_request(expect_request(SENTINEL, DEFAULT_CTID))
    listed = parse_http_request(report_request(SENTINEL, DEFAULT_CTID, DEFAULT_CTDIGEST))
    got = parse_http_response(expect_response(SENTINEL, DEFAULT_CTID, DEFAULT_CTDIGEST))
    preload_reply = parse_http_response(
        report_response(SENTINEL, DEFAULT_CTID, DEFAULT_CTDIGEST)
    )
    assert asked["method"] == "GET"
    assert asked["ct_kind"] == "expect"
    assert listed["ct_kind"] == "report"
    assert got["status"] == 200
    assert preload_reply["status"] == 200
    assert got["policy"] == DEFAULT_CT
    assert preload_reply["policy"] == REPORT_CT
    assert canonical_expect(SENTINEL, DEFAULT_CTID).startswith("max-age=")
    assert "ctdigest=" in canonical_report(SENTINEL, DEFAULT_CTID, DEFAULT_CTDIGEST)


def test_builtin_proof_seals_expectct_actuation() -> None:
    report = builtin_expectct_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "expectct_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_expectct"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_ctid_is_forbidden"]
    assert report["checks"]["skip_expect_stays_empty"]
    assert report["checks"]["skip_report_stays_empty"]
    assert report["checks"]["skip_ctdigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_ctid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_ctdigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_expectct"]
    assert report["checks"]["catalog_names_expectct"]
    assert report["checks"]["catalog_names_xfo"]
    assert report["checks"]["leftover_text_binds_expectct"]
    assert report["checks"]["proved_expectct_consumes_leftover"]
    assert report["mission_goal"] == EXPECTCT_ACTUATION_GOAL
    assert report["done_when"] == EXPECTCT_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[EXPECTCT_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "expectct" in capability.tags
    assert "rfc9163" in capability.tags
    assert "http" in capability.tags
    assert "ctid" in capability.tags
    assert "ctdigest" in capability.tags
    assert "report" in capability.tags


def test_selection_gate_accepts_expectct_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        EXPECTCT_ACTUATION_GOAL,
        EXPECTCT_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(EXPECTCT_ACTUATION_GOAL)
    assert "expectct" in family
    assert "rfc9163" in family
    assert "ctid" in family
    assert "ctdigest" in family
    assert "altsvc" not in family
    assert "rfc7838" not in family
    assert "altsvcid" not in family
    assert "hsts" not in family
    assert "hpkp" not in family
    assert "rfc7469" not in family
    assert "pinid" not in family
    assert "pindigest" not in family
    assert "xfo" not in family
    assert "rfc7034" not in family
    assert "frameid" not in family
    assert "framedigest" not in family
    assert "rfc9000" not in family
    assert "http3" not in family
    assert "earlyhint" not in family
    assert "rfc8297" not in family
    assert "linkid" not in family
    assert "clienthint" not in family
    assert "rfc8942" not in family
    assert "chid" not in family
    assert "structuredfield" not in family
    assert "rfc8941" not in family
    assert "dictid" not in family
    assert "sfv" not in family
