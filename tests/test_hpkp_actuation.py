from pathlib import Path

from blackhole_agent.expectct_actuation import (
    EXPECTCT_ACTUATION_GOAL,
    EXPECTCT_ACTUATION_ID,
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
from blackhole_agent.hpkp_actuation import (
    DEFAULT_PINID,
    DEFAULT_PINDIGEST,
    DEFAULT_PKP,
    EMPTY_PINID,
    FRAME_REPORT,
    FRAME_PIN,
    HPKP_ACTUATION_DONE_WHEN,
    HPKP_ACTUATION_GOAL,
    HPKP_ACTUATION_ID,
    HPKP_LEFTOVER,
    PK_FIRST,
    REPORT_PKP,
    RFC_PKP_FIELD,
    RFC_PKP_REPORT,
    SENTINEL,
    PKP_HEADER,
    builtin_hpkp_actuation_proof,
    canonical_report,
    canonical_pin,
    crc32c,
    encode_report,
    encode_pin,
    encode_pkp_header,
    independent_hpkp_digest,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_pkp,
    parse_pkp_header,
    report_request,
    report_response,
    run_hpkp_workflow,
    serialize_pkp,
    pin_request,
    pin_response,
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
    HPKP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    build_tool_routing_preflight,
    hpkp_tool_descriptor,
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
    EXPECTCT_ACTUATION_GOAL,
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
    EXPECTCT_ACTUATION_ID,
)


def test_goal_binds_hpkp_actuation_plane() -> None:
    assert leftover_marker_ids(HPKP_ACTUATION_GOAL) == (HPKP_ACTUATION_ID,)
    assert leftover_marker_ids(HPKP_LEFTOVER) == (HPKP_ACTUATION_ID,)
    assert HPKP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HSTS_ACTUATION_GOAL) == (HSTS_ACTUATION_ID,)
    assert leftover_marker_ids(EXPECTCT_ACTUATION_GOAL) == (EXPECTCT_ACTUATION_ID,)
    assert leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (ALTSVC_ACTUATION_ID,)
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert HSTS_ACTUATION_ID in LOCAL_DENYLIST
    assert EXPECTCT_ACTUATION_ID in LOCAL_DENYLIST
    assert ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert HPKP_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(HPKP_ACTUATION_GOAL)
    hpkp_signature = semantic_signature(HPKP_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(hpkp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_hpkp_tool_completes_pin_report_poll() -> None:
    descriptor = hpkp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HPKP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("hpkp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HPKP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["hpkp"]

    missing = run_hpkp_workflow(with_pinid=False)
    skip_bind = run_hpkp_workflow(skip_bind=True)
    skip_pin = run_hpkp_workflow(do_pin=False)
    skip_report = run_hpkp_workflow(do_report=False)
    skip_pindigest = run_hpkp_workflow(do_pindigest=False)
    skip_replay = run_hpkp_workflow(replay=False)
    skip_pinid = run_hpkp_workflow(use_pinid=False)
    live = run_hpkp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_pinid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_pin["ok"] is False
    assert skip_pin["error"] == "pin_required"
    assert skip_report["ok"] is False
    assert skip_report["error"] == "report_required"
    assert skip_pindigest["ok"] is False
    assert skip_pindigest["error"] == "pindigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_pinid["ok"] is False
    assert skip_pinid["error"] == "pinid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_hpkp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["pin_frame"] is True
    assert row["report_frame"] is True
    assert row["pindigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["pinid_bound"] is True
    assert row["digest"]
    assert live["pinid"] == DEFAULT_PINID
    assert live["pindigest"] == DEFAULT_PINDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_pin(identity=SENTINEL, pinid=DEFAULT_PINID, pindigest=DEFAULT_PINDIGEST)
    )
    assert queried["is_pin"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["pinid"] == DEFAULT_PINID
    assert queried["pindigest"] == DEFAULT_PINDIGEST
    assert queried["type"] == FRAME_PIN
    assert queried["first_byte"] == PK_FIRST
    answered = parse_message(
        encode_report(identity=SENTINEL, pinid=DEFAULT_PINID, pindigest=DEFAULT_PINDIGEST)
    )
    assert answered["is_report"] is True and answered["is_response"] is True
    assert answered["pinid"] == DEFAULT_PINID
    assert answered["pindigest"] == DEFAULT_PINDIGEST
    packed = encode_pin(identity=SENTINEL, pinid=DEFAULT_PINID, pindigest=DEFAULT_PINDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_pin(identity=SENTINEL, pinid=DEFAULT_PINID, include_pinid=False)
    )
    assert bare["has_pinid"] is False
    assert bare["pinid"] == EMPTY_PINID
    advertised = serialize_pkp(DEFAULT_PKP)
    assert advertised == RFC_PKP_FIELD
    assert parse_pkp(advertised) == DEFAULT_PKP
    assert parse_pkp(RFC_PKP_REPORT) == REPORT_PKP
    header = parse_pkp_header(encode_pkp_header(DEFAULT_PKP))
    assert header["field_value"] == RFC_PKP_FIELD
    assert header["header"] == PKP_HEADER
    asked = parse_http_request(pin_request(SENTINEL, DEFAULT_PINID))
    listed = parse_http_request(report_request(SENTINEL, DEFAULT_PINID, DEFAULT_PINDIGEST))
    got = parse_http_response(pin_response(SENTINEL, DEFAULT_PINID, DEFAULT_PINDIGEST))
    preload_reply = parse_http_response(
        report_response(SENTINEL, DEFAULT_PINID, DEFAULT_PINDIGEST)
    )
    assert asked["method"] == "GET"
    assert asked["pk_kind"] == "pin"
    assert listed["pk_kind"] == "report"
    assert got["status"] == 200
    assert preload_reply["status"] == 200
    assert got["policy"] == DEFAULT_PKP
    assert preload_reply["policy"] == REPORT_PKP
    assert canonical_pin(SENTINEL, DEFAULT_PINID).startswith("max-age=")
    assert "pindigest=" in canonical_report(SENTINEL, DEFAULT_PINID, DEFAULT_PINDIGEST)


def test_builtin_proof_seals_hpkp_actuation() -> None:
    report = builtin_hpkp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "hpkp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_hpkp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_pinid_is_forbidden"]
    assert report["checks"]["skip_pin_stays_empty"]
    assert report["checks"]["skip_report_stays_empty"]
    assert report["checks"]["skip_pindigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_pinid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_pindigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_hpkp"]
    assert report["checks"]["catalog_names_hpkp"]
    assert report["checks"]["catalog_names_expectct"]
    assert report["checks"]["leftover_text_binds_hpkp"]
    assert report["checks"]["proved_hpkp_consumes_leftover"]
    assert report["mission_goal"] == HPKP_ACTUATION_GOAL
    assert report["done_when"] == HPKP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[HPKP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "hpkp" in capability.tags
    assert "rfc7469" in capability.tags
    assert "http" in capability.tags
    assert "pinid" in capability.tags
    assert "pindigest" in capability.tags
    assert "report" in capability.tags


def test_selection_gate_accepts_hpkp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        HPKP_ACTUATION_GOAL,
        HPKP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(HPKP_ACTUATION_GOAL)
    assert "hpkp" in family
    assert "rfc7469" in family
    assert "pinid" in family
    assert "pindigest" in family
    assert "altsvc" not in family
    assert "rfc7838" not in family
    assert "altsvcid" not in family
    assert "hsts" not in family
    assert "expectct" not in family
    assert "rfc9163" not in family
    assert "ctid" not in family
    assert "ctdigest" not in family
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
