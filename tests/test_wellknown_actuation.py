from pathlib import Path

from blackhole_agent.httppatch_actuation import (
    HTTPPATCH_ACTUATION_GOAL,
    HTTPPATCH_ACTUATION_ID,
)
from blackhole_agent.webdav_actuation import (
    WEBDAV_ACTUATION_GOAL,
    WEBDAV_ACTUATION_ID,
)
from blackhole_agent.stalecontent_actuation import (
    STALECONTENT_ACTUATION_GOAL,
    STALECONTENT_ACTUATION_ID,
)
from blackhole_agent.extvalue_actuation import (
    EXTVALUE_ACTUATION_GOAL,
    EXTVALUE_ACTUATION_ID,
)
from blackhole_agent.weblinking_actuation import (
    WEBLINKING_ACTUATION_GOAL,
    WEBLINKING_ACTUATION_ID,
)
from blackhole_agent.httpcookie_actuation import (
    HTTPCOOKIE_ACTUATION_GOAL,
    HTTPCOOKIE_ACTUATION_ID,
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
from blackhole_agent.wellknown_actuation import (
    DEFAULT_SUFFIXID,
    DEFAULT_SUFFIXDIGEST,
    DEFAULT_DISCOVERY,
    EMPTY_SUFFIXID,
    FRAME_SUFFIX,
    FRAME_DISCOVERY,
    WELLKNOWN_ACTUATION_DONE_WHEN,
    WELLKNOWN_ACTUATION_GOAL,
    WELLKNOWN_ACTUATION_ID,
    WELLKNOWN_LEFTOVER,
    WK_FIRST,
    SUFFIX_POLICY,
    RFC_DISCOVERY_FIELD,
    RFC_SUFFIX_FIELD,
    SENTINEL,
    DISCOVERY_HEADER,
    builtin_wellknown_actuation_proof,
    canonical_suffix,
    canonical_discovery,
    crc32c,
    encode_suffix,
    encode_discovery,
    encode_wellknown_header,
    independent_wellknown_digest,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_wellknown,
    parse_wellknown_header,
    suffix_request,
    suffix_response,
    run_wellknown_workflow,
    serialize_wellknown,
    discovery_request,
    discovery_response,
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
    WELLKNOWN_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    build_tool_routing_preflight,
    wellknown_tool_descriptor,
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
    HTTPCOOKIE_ACTUATION_GOAL,
    WEBLINKING_ACTUATION_GOAL,
    EXTVALUE_ACTUATION_GOAL,
    WEBDAV_ACTUATION_GOAL,
    HTTPPATCH_ACTUATION_GOAL,
    STALECONTENT_ACTUATION_GOAL,
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
    HTTPCOOKIE_ACTUATION_ID,
    WEBLINKING_ACTUATION_ID,
    EXTVALUE_ACTUATION_ID,
    WEBDAV_ACTUATION_ID,
    HTTPPATCH_ACTUATION_ID,
    STALECONTENT_ACTUATION_ID,
)


def test_goal_binds_wellknown_actuation_plane() -> None:
    assert leftover_marker_ids(WELLKNOWN_ACTUATION_GOAL) == (WELLKNOWN_ACTUATION_ID,)
    assert leftover_marker_ids(WELLKNOWN_LEFTOVER) == (WELLKNOWN_ACTUATION_ID,)
    assert leftover_marker_ids(WEBDAV_ACTUATION_GOAL) == (WEBDAV_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPPATCH_ACTUATION_GOAL) == (HTTPPATCH_ACTUATION_ID,)
    assert leftover_marker_ids(STALECONTENT_ACTUATION_GOAL) == (STALECONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EXTVALUE_ACTUATION_GOAL) == (EXTVALUE_ACTUATION_ID,)
    assert leftover_marker_ids(WEBLINKING_ACTUATION_GOAL) == (WEBLINKING_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPCOOKIE_ACTUATION_GOAL) == (HTTPCOOKIE_ACTUATION_ID,)
    assert leftover_marker_ids(WEBORIGIN_ACTUATION_GOAL) == (WEBORIGIN_ACTUATION_ID,)
    assert leftover_marker_ids(XFO_ACTUATION_GOAL) == (XFO_ACTUATION_ID,)
    assert WELLKNOWN_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBDAV_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPPATCH_ACTUATION_ID in LOCAL_DENYLIST
    assert STALECONTENT_ACTUATION_ID in LOCAL_DENYLIST
    assert EXTVALUE_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBLINKING_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPCOOKIE_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBORIGIN_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HSTS_ACTUATION_GOAL) == (HSTS_ACTUATION_ID,)
    assert leftover_marker_ids(HPKP_ACTUATION_GOAL) == (HPKP_ACTUATION_ID,)
    assert leftover_marker_ids(WEBDAV_ACTUATION_GOAL) == (WEBDAV_ACTUATION_ID,)
    assert leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (ALTSVC_ACTUATION_ID,)
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert HSTS_ACTUATION_ID in LOCAL_DENYLIST
    assert HPKP_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBDAV_ACTUATION_ID in LOCAL_DENYLIST
    assert ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert WELLKNOWN_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(WELLKNOWN_ACTUATION_GOAL)
    wellknown_signature = semantic_signature(WELLKNOWN_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(wellknown_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_wellknown_tool_completes_discovery_suffix_poll() -> None:
    descriptor = wellknown_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WELLKNOWN_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("wellknown",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WELLKNOWN_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["wellknown"]

    missing = run_wellknown_workflow(with_suffixid=False)
    skip_bind = run_wellknown_workflow(skip_bind=True)
    skip_discovery = run_wellknown_workflow(do_discovery=False)
    skip_suffix = run_wellknown_workflow(do_suffix=False)
    skip_suffixdigest = run_wellknown_workflow(do_suffixdigest=False)
    skip_replay = run_wellknown_workflow(replay=False)
    skip_suffixid = run_wellknown_workflow(use_suffixid=False)
    live = run_wellknown_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_suffixid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_discovery["ok"] is False
    assert skip_discovery["error"] == "discovery_required"
    assert skip_suffix["ok"] is False
    assert skip_suffix["error"] == "suffix_required"
    assert skip_suffixdigest["ok"] is False
    assert skip_suffixdigest["error"] == "suffixdigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_suffixid["ok"] is False
    assert skip_suffixid["error"] == "suffixid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_wellknown_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["discovery_frame"] is True
    assert row["suffix_frame"] is True
    assert row["suffixdigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["suffixid_bound"] is True
    assert row["digest"]
    assert live["suffixid"] == DEFAULT_SUFFIXID
    assert live["suffixdigest"] == DEFAULT_SUFFIXDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_discovery(identity=SENTINEL, suffixid=DEFAULT_SUFFIXID, suffixdigest=DEFAULT_SUFFIXDIGEST)
    )
    assert queried["is_discovery"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["suffixid"] == DEFAULT_SUFFIXID
    assert queried["suffixdigest"] == DEFAULT_SUFFIXDIGEST
    assert queried["type"] == FRAME_DISCOVERY
    assert queried["first_byte"] == WK_FIRST
    answered = parse_message(
        encode_suffix(identity=SENTINEL, suffixid=DEFAULT_SUFFIXID, suffixdigest=DEFAULT_SUFFIXDIGEST)
    )
    assert answered["is_suffix"] is True and answered["is_response"] is True
    assert answered["suffixid"] == DEFAULT_SUFFIXID
    assert answered["suffixdigest"] == DEFAULT_SUFFIXDIGEST
    packed = encode_discovery(identity=SENTINEL, suffixid=DEFAULT_SUFFIXID, suffixdigest=DEFAULT_SUFFIXDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_discovery(identity=SENTINEL, suffixid=DEFAULT_SUFFIXID, include_suffixid=False)
    )
    assert bare["has_suffixid"] is False
    assert bare["suffixid"] == EMPTY_SUFFIXID
    advertised = serialize_wellknown(DEFAULT_DISCOVERY)
    assert advertised == RFC_DISCOVERY_FIELD
    assert parse_wellknown(advertised) == DEFAULT_DISCOVERY
    assert parse_wellknown(RFC_SUFFIX_FIELD) == SUFFIX_POLICY
    header = parse_wellknown_header(encode_wellknown_header(DEFAULT_DISCOVERY))
    assert header["field_value"] == RFC_DISCOVERY_FIELD
    assert header["header"] == DISCOVERY_HEADER
    asked = parse_http_request(discovery_request(SENTINEL, DEFAULT_SUFFIXID))
    listed = parse_http_request(suffix_request(SENTINEL, DEFAULT_SUFFIXID, DEFAULT_SUFFIXDIGEST))
    got = parse_http_response(discovery_response(SENTINEL, DEFAULT_SUFFIXID, DEFAULT_SUFFIXDIGEST))
    preload_reply = parse_http_response(
        suffix_response(SENTINEL, DEFAULT_SUFFIXID, DEFAULT_SUFFIXDIGEST)
    )
    assert asked["method"] == "DISCOVERY"
    assert asked["wellknown_kind"] == "discovery"
    assert listed["wellknown_kind"] == "suffix"
    assert got["status"] == 200
    assert preload_reply["status"] == 200
    assert got["policy"] == DEFAULT_DISCOVERY
    assert preload_reply["policy"] == SUFFIX_POLICY
    assert canonical_discovery(SENTINEL, DEFAULT_SUFFIXID).startswith("DISCOVERY")
    assert "suffixdigest=" in canonical_suffix(SENTINEL, DEFAULT_SUFFIXID, DEFAULT_SUFFIXDIGEST)


def test_builtin_proof_seals_wellknown_actuation() -> None:
    report = builtin_wellknown_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "wellknown_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_wellknown"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_suffixid_is_forbidden"]
    assert report["checks"]["skip_discovery_stays_empty"]
    assert report["checks"]["skip_suffix_stays_empty"]
    assert report["checks"]["skip_suffixdigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_suffixid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_suffixdigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_wellknown"]
    assert report["checks"]["catalog_names_wellknown"]
    assert report["checks"]["catalog_names_webdav"]
    assert report["checks"]["leftover_text_binds_wellknown"]
    assert report["checks"]["proved_wellknown_consumes_leftover"]
    assert report["mission_goal"] == WELLKNOWN_ACTUATION_GOAL
    assert report["done_when"] == WELLKNOWN_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[WELLKNOWN_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "wellknown" in capability.tags
    assert "rfc5785" in capability.tags
    assert "http" in capability.tags
    assert "suffixid" in capability.tags
    assert "suffixdigest" in capability.tags
    assert "discovery" in capability.tags


def test_selection_gate_accepts_wellknown_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        WELLKNOWN_ACTUATION_GOAL,
        WELLKNOWN_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(WELLKNOWN_ACTUATION_GOAL)
    family_tokens = set(family.split("/"))
    assert "wellknown" in family
    assert "rfc5785" in family
    assert "suffixid" in family
    assert "suffixdigest" in family
    assert "chid" not in family_tokens
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
    assert "httppatch" not in family
    assert "rfc5789" not in family
    assert "patchid" not in family
    assert "patchdigest" not in family
    assert "webdav" not in family
    assert "rfc4918" not in family
    assert "lockid" not in family
    assert "lockdigest" not in family
    assert "stalecontent" not in family
    assert "rfc5861" not in family
    assert "staleid" not in family
    assert "staledigest" not in family
    assert "weblinking" not in family
    assert "rfc5988" not in family
    assert "relationid" not in family
    assert "relationdigest" not in family
    assert "httpcookie" not in family
    assert "rfc6265" not in family
    assert "cookieid" not in family
    assert "cookiedigest" not in family
    assert "webdav" not in family
    assert "rfc4918" not in family
    assert "lockid" not in family
    assert "lockdigest" not in family
    assert "rfc9000" not in family
    assert "http3" not in family
    assert "earlyhint" not in family
    assert "rfc8297" not in family
    assert "linkid" not in family
    assert "clienthint" not in family
    assert "rfc8942" not in family
    assert "chid" not in family_tokens
    assert "structuredfield" not in family
    assert "rfc8941" not in family
    assert "dictid" not in family
    assert "sfv" not in family
