from pathlib import Path

from blackhole_agent.contentdisposition_actuation import (
    CONTENTDISPOSITION_ACTUATION_GOAL,
    CONTENTDISPOSITION_ACTUATION_ID,
)
from blackhole_agent.weborigin_actuation import (
    WEBORIGIN_ACTUATION_GOAL,
    WEBORIGIN_ACTUATION_ID,
)
from blackhole_agent.hpkp_actuation import (
    HPKP_ACTUATION_GOAL,
    HPKP_ACTUATION_ID,
)
from blackhole_agent.xfo_actuation import (
    XFO_ACTUATION_GOAL,
    XFO_ACTUATION_ID,
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
from blackhole_agent.httpcookie_actuation import (
    DEFAULT_COOKIEID,
    DEFAULT_COOKIEDIGEST,
    DEFAULT_SETCOOKIE,
    EMPTY_COOKIEID,
    FRAME_COOKIE,
    FRAME_SETCOOKIE,
    HTTPCOOKIE_ACTUATION_DONE_WHEN,
    HTTPCOOKIE_ACTUATION_GOAL,
    HTTPCOOKIE_ACTUATION_ID,
    HTTPCOOKIE_LEFTOVER,
    CK_FIRST,
    COOKIE_POLICY,
    RFC_SETCOOKIE_FIELD,
    RFC_COOKIE_FIELD,
    SENTINEL,
    SETCOOKIE_HEADER,
    builtin_httpcookie_actuation_proof,
    canonical_cookie,
    canonical_setcookie,
    crc32c,
    encode_cookie,
    encode_setcookie,
    encode_httpcookie_header,
    independent_httpcookie_digest,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_httpcookie,
    parse_httpcookie_header,
    cookie_request,
    cookie_response,
    run_httpcookie_workflow,
    serialize_httpcookie,
    setcookie_request,
    setcookie_response,
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
    HTTPCOOKIE_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    build_tool_routing_preflight,
    httpcookie_tool_descriptor,
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
    WEBORIGIN_ACTUATION_GOAL,
    CONTENTDISPOSITION_ACTUATION_GOAL,
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
    WEBORIGIN_ACTUATION_ID,
    CONTENTDISPOSITION_ACTUATION_ID,
)


def test_goal_binds_httpcookie_actuation_plane() -> None:
    assert leftover_marker_ids(HTTPCOOKIE_ACTUATION_GOAL) == (HTTPCOOKIE_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPCOOKIE_LEFTOVER) == (HTTPCOOKIE_ACTUATION_ID,)
    assert leftover_marker_ids(CONTENTDISPOSITION_ACTUATION_GOAL) == (CONTENTDISPOSITION_ACTUATION_ID,)
    assert leftover_marker_ids(WEBORIGIN_ACTUATION_GOAL) == (WEBORIGIN_ACTUATION_ID,)
    assert leftover_marker_ids(XFO_ACTUATION_GOAL) == (XFO_ACTUATION_ID,)
    assert HTTPCOOKIE_ACTUATION_ID in LOCAL_DENYLIST
    assert CONTENTDISPOSITION_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBORIGIN_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HSTS_ACTUATION_GOAL) == (HSTS_ACTUATION_ID,)
    assert leftover_marker_ids(HPKP_ACTUATION_GOAL) == (HPKP_ACTUATION_ID,)
    assert leftover_marker_ids(CONTENTDISPOSITION_ACTUATION_GOAL) == (CONTENTDISPOSITION_ACTUATION_ID,)
    assert leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (ALTSVC_ACTUATION_ID,)
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert HSTS_ACTUATION_ID in LOCAL_DENYLIST
    assert HPKP_ACTUATION_ID in LOCAL_DENYLIST
    assert CONTENTDISPOSITION_ACTUATION_ID in LOCAL_DENYLIST
    assert ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert HTTPCOOKIE_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(HTTPCOOKIE_ACTUATION_GOAL)
    httpcookie_signature = semantic_signature(HTTPCOOKIE_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(httpcookie_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_httpcookie_tool_completes_setcookie_cookie_poll() -> None:
    descriptor = httpcookie_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPCOOKIE_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("httpcookie",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPCOOKIE_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["httpcookie"]

    missing = run_httpcookie_workflow(with_cookieid=False)
    skip_bind = run_httpcookie_workflow(skip_bind=True)
    skip_setcookie = run_httpcookie_workflow(do_setcookie=False)
    skip_cookie = run_httpcookie_workflow(do_cookie=False)
    skip_cookiedigest = run_httpcookie_workflow(do_cookiedigest=False)
    skip_replay = run_httpcookie_workflow(replay=False)
    skip_cookieid = run_httpcookie_workflow(use_cookieid=False)
    live = run_httpcookie_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_cookieid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_setcookie["ok"] is False
    assert skip_setcookie["error"] == "setcookie_required"
    assert skip_cookie["ok"] is False
    assert skip_cookie["error"] == "cookie_required"
    assert skip_cookiedigest["ok"] is False
    assert skip_cookiedigest["error"] == "cookiedigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_cookieid["ok"] is False
    assert skip_cookieid["error"] == "cookieid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_httpcookie_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["setcookie_frame"] is True
    assert row["cookie_frame"] is True
    assert row["cookiedigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["cookieid_bound"] is True
    assert row["digest"]
    assert live["cookieid"] == DEFAULT_COOKIEID
    assert live["cookiedigest"] == DEFAULT_COOKIEDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_setcookie(identity=SENTINEL, cookieid=DEFAULT_COOKIEID, cookiedigest=DEFAULT_COOKIEDIGEST)
    )
    assert queried["is_setcookie"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["cookieid"] == DEFAULT_COOKIEID
    assert queried["cookiedigest"] == DEFAULT_COOKIEDIGEST
    assert queried["type"] == FRAME_SETCOOKIE
    assert queried["first_byte"] == CK_FIRST
    answered = parse_message(
        encode_cookie(identity=SENTINEL, cookieid=DEFAULT_COOKIEID, cookiedigest=DEFAULT_COOKIEDIGEST)
    )
    assert answered["is_cookie"] is True and answered["is_response"] is True
    assert answered["cookieid"] == DEFAULT_COOKIEID
    assert answered["cookiedigest"] == DEFAULT_COOKIEDIGEST
    packed = encode_setcookie(identity=SENTINEL, cookieid=DEFAULT_COOKIEID, cookiedigest=DEFAULT_COOKIEDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_setcookie(identity=SENTINEL, cookieid=DEFAULT_COOKIEID, include_cookieid=False)
    )
    assert bare["has_cookieid"] is False
    assert bare["cookieid"] == EMPTY_COOKIEID
    advertised = serialize_httpcookie(DEFAULT_SETCOOKIE)
    assert advertised == RFC_SETCOOKIE_FIELD
    assert parse_httpcookie(advertised) == DEFAULT_SETCOOKIE
    assert parse_httpcookie(RFC_COOKIE_FIELD) == COOKIE_POLICY
    header = parse_httpcookie_header(encode_httpcookie_header(DEFAULT_SETCOOKIE))
    assert header["field_value"] == RFC_SETCOOKIE_FIELD
    assert header["header"] == SETCOOKIE_HEADER
    asked = parse_http_request(setcookie_request(SENTINEL, DEFAULT_COOKIEID))
    listed = parse_http_request(cookie_request(SENTINEL, DEFAULT_COOKIEID, DEFAULT_COOKIEDIGEST))
    got = parse_http_response(setcookie_response(SENTINEL, DEFAULT_COOKIEID, DEFAULT_COOKIEDIGEST))
    preload_reply = parse_http_response(
        cookie_response(SENTINEL, DEFAULT_COOKIEID, DEFAULT_COOKIEDIGEST)
    )
    assert asked["method"] == "GET"
    assert asked["httpcookie_kind"] == "setcookie"
    assert listed["httpcookie_kind"] == "cookie"
    assert got["status"] == 200
    assert preload_reply["status"] == 200
    assert got["policy"] == DEFAULT_SETCOOKIE
    assert preload_reply["policy"] == COOKIE_POLICY
    assert canonical_setcookie(SENTINEL, DEFAULT_COOKIEID).startswith("SET-COOKIE")
    assert "cookiedigest=" in canonical_cookie(SENTINEL, DEFAULT_COOKIEID, DEFAULT_COOKIEDIGEST)


def test_builtin_proof_seals_httpcookie_actuation() -> None:
    report = builtin_httpcookie_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "httpcookie_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_httpcookie"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_cookieid_is_forbidden"]
    assert report["checks"]["skip_setcookie_stays_empty"]
    assert report["checks"]["skip_cookie_stays_empty"]
    assert report["checks"]["skip_cookiedigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_cookieid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_cookiedigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_httpcookie"]
    assert report["checks"]["catalog_names_httpcookie"]
    assert report["checks"]["catalog_names_contentdisposition"]
    assert report["checks"]["leftover_text_binds_httpcookie"]
    assert report["checks"]["proved_httpcookie_consumes_leftover"]
    assert report["mission_goal"] == HTTPCOOKIE_ACTUATION_GOAL
    assert report["done_when"] == HTTPCOOKIE_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[HTTPCOOKIE_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "httpcookie" in capability.tags
    assert "rfc6265" in capability.tags
    assert "http" in capability.tags
    assert "cookieid" in capability.tags
    assert "cookiedigest" in capability.tags
    assert "cookie" in capability.tags


def test_selection_gate_accepts_httpcookie_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        HTTPCOOKIE_ACTUATION_GOAL,
        HTTPCOOKIE_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(HTTPCOOKIE_ACTUATION_GOAL)
    assert "httpcookie" in family
    assert "rfc6265" in family
    assert "cookieid" in family
    assert "cookiedigest" in family
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
    assert "contentdisposition" not in family
    assert "rfc6266" not in family
    assert "dispositionid" not in family
    assert "dispositiondigest" not in family
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
