from pathlib import Path

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
from blackhole_agent.contentdisposition_actuation import (
    DEFAULT_DISPOSITIONID,
    DEFAULT_DISPOSITIONDIGEST,
    DEFAULT_DISPOSITION,
    EMPTY_DISPOSITIONID,
    FRAME_ATTACHMENT,
    FRAME_DISPOSITION,
    CONTENTDISPOSITION_ACTUATION_DONE_WHEN,
    CONTENTDISPOSITION_ACTUATION_GOAL,
    CONTENTDISPOSITION_ACTUATION_ID,
    CONTENTDISPOSITION_LEFTOVER,
    CD_FIRST,
    ATTACHMENT_POLICY,
    RFC_DISPOSITION_FIELD,
    RFC_ATTACHMENT_FIELD,
    SENTINEL,
    DISPOSITION_HEADER,
    builtin_contentdisposition_actuation_proof,
    canonical_attachment,
    canonical_disposition,
    crc32c,
    encode_attachment,
    encode_disposition,
    encode_contentdisposition_header,
    independent_contentdisposition_digest,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_contentdisposition,
    parse_contentdisposition_header,
    attachment_request,
    attachment_response,
    run_contentdisposition_workflow,
    serialize_contentdisposition,
    disposition_request,
    disposition_response,
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
    CONTENTDISPOSITION_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    build_tool_routing_preflight,
    contentdisposition_tool_descriptor,
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
)


def test_goal_binds_contentdisposition_actuation_plane() -> None:
    assert leftover_marker_ids(CONTENTDISPOSITION_ACTUATION_GOAL) == (CONTENTDISPOSITION_ACTUATION_ID,)
    assert leftover_marker_ids(CONTENTDISPOSITION_LEFTOVER) == (CONTENTDISPOSITION_ACTUATION_ID,)
    assert leftover_marker_ids(WEBLINKING_ACTUATION_GOAL) == (WEBLINKING_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPCOOKIE_ACTUATION_GOAL) == (HTTPCOOKIE_ACTUATION_ID,)
    assert leftover_marker_ids(WEBORIGIN_ACTUATION_GOAL) == (WEBORIGIN_ACTUATION_ID,)
    assert leftover_marker_ids(XFO_ACTUATION_GOAL) == (XFO_ACTUATION_ID,)
    assert CONTENTDISPOSITION_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBLINKING_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPCOOKIE_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBORIGIN_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HSTS_ACTUATION_GOAL) == (HSTS_ACTUATION_ID,)
    assert leftover_marker_ids(HPKP_ACTUATION_GOAL) == (HPKP_ACTUATION_ID,)
    assert leftover_marker_ids(WEBLINKING_ACTUATION_GOAL) == (WEBLINKING_ACTUATION_ID,)
    assert leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (ALTSVC_ACTUATION_ID,)
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert HSTS_ACTUATION_ID in LOCAL_DENYLIST
    assert HPKP_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBLINKING_ACTUATION_ID in LOCAL_DENYLIST
    assert ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert CONTENTDISPOSITION_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(CONTENTDISPOSITION_ACTUATION_GOAL)
    contentdisposition_signature = semantic_signature(CONTENTDISPOSITION_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(contentdisposition_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_contentdisposition_tool_completes_disposition_attachment_poll() -> None:
    descriptor = contentdisposition_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CONTENTDISPOSITION_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("contentdisposition",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CONTENTDISPOSITION_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["contentdisposition"]

    missing = run_contentdisposition_workflow(with_dispositionid=False)
    skip_bind = run_contentdisposition_workflow(skip_bind=True)
    skip_disposition = run_contentdisposition_workflow(do_disposition=False)
    skip_attachment = run_contentdisposition_workflow(do_attachment=False)
    skip_dispositiondigest = run_contentdisposition_workflow(do_dispositiondigest=False)
    skip_replay = run_contentdisposition_workflow(replay=False)
    skip_dispositionid = run_contentdisposition_workflow(use_dispositionid=False)
    live = run_contentdisposition_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_dispositionid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_disposition["ok"] is False
    assert skip_disposition["error"] == "disposition_required"
    assert skip_attachment["ok"] is False
    assert skip_attachment["error"] == "attachment_required"
    assert skip_dispositiondigest["ok"] is False
    assert skip_dispositiondigest["error"] == "dispositiondigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_dispositionid["ok"] is False
    assert skip_dispositionid["error"] == "dispositionid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_contentdisposition_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["disposition_frame"] is True
    assert row["attachment_frame"] is True
    assert row["dispositiondigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["dispositionid_bound"] is True
    assert row["digest"]
    assert live["dispositionid"] == DEFAULT_DISPOSITIONID
    assert live["dispositiondigest"] == DEFAULT_DISPOSITIONDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_disposition(identity=SENTINEL, dispositionid=DEFAULT_DISPOSITIONID, dispositiondigest=DEFAULT_DISPOSITIONDIGEST)
    )
    assert queried["is_disposition"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["dispositionid"] == DEFAULT_DISPOSITIONID
    assert queried["dispositiondigest"] == DEFAULT_DISPOSITIONDIGEST
    assert queried["type"] == FRAME_DISPOSITION
    assert queried["first_byte"] == CD_FIRST
    answered = parse_message(
        encode_attachment(identity=SENTINEL, dispositionid=DEFAULT_DISPOSITIONID, dispositiondigest=DEFAULT_DISPOSITIONDIGEST)
    )
    assert answered["is_attachment"] is True and answered["is_response"] is True
    assert answered["dispositionid"] == DEFAULT_DISPOSITIONID
    assert answered["dispositiondigest"] == DEFAULT_DISPOSITIONDIGEST
    packed = encode_disposition(identity=SENTINEL, dispositionid=DEFAULT_DISPOSITIONID, dispositiondigest=DEFAULT_DISPOSITIONDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_disposition(identity=SENTINEL, dispositionid=DEFAULT_DISPOSITIONID, include_dispositionid=False)
    )
    assert bare["has_dispositionid"] is False
    assert bare["dispositionid"] == EMPTY_DISPOSITIONID
    advertised = serialize_contentdisposition(DEFAULT_DISPOSITION)
    assert advertised == RFC_DISPOSITION_FIELD
    assert parse_contentdisposition(advertised) == DEFAULT_DISPOSITION
    assert parse_contentdisposition(RFC_ATTACHMENT_FIELD) == ATTACHMENT_POLICY
    header = parse_contentdisposition_header(encode_contentdisposition_header(DEFAULT_DISPOSITION))
    assert header["field_value"] == RFC_DISPOSITION_FIELD
    assert header["header"] == DISPOSITION_HEADER
    asked = parse_http_request(disposition_request(SENTINEL, DEFAULT_DISPOSITIONID))
    listed = parse_http_request(attachment_request(SENTINEL, DEFAULT_DISPOSITIONID, DEFAULT_DISPOSITIONDIGEST))
    got = parse_http_response(disposition_response(SENTINEL, DEFAULT_DISPOSITIONID, DEFAULT_DISPOSITIONDIGEST))
    preload_reply = parse_http_response(
        attachment_response(SENTINEL, DEFAULT_DISPOSITIONID, DEFAULT_DISPOSITIONDIGEST)
    )
    assert asked["method"] == "GET"
    assert asked["contentdisposition_kind"] == "disposition"
    assert listed["contentdisposition_kind"] == "attachment"
    assert got["status"] == 200
    assert preload_reply["status"] == 200
    assert got["policy"] == DEFAULT_DISPOSITION
    assert preload_reply["policy"] == ATTACHMENT_POLICY
    assert canonical_disposition(SENTINEL, DEFAULT_DISPOSITIONID).startswith("DISPOSITION")
    assert "dispositiondigest=" in canonical_attachment(SENTINEL, DEFAULT_DISPOSITIONID, DEFAULT_DISPOSITIONDIGEST)


def test_builtin_proof_seals_contentdisposition_actuation() -> None:
    report = builtin_contentdisposition_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "contentdisposition_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_contentdisposition"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_dispositionid_is_forbidden"]
    assert report["checks"]["skip_disposition_stays_empty"]
    assert report["checks"]["skip_attachment_stays_empty"]
    assert report["checks"]["skip_dispositiondigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_dispositionid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_dispositiondigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_contentdisposition"]
    assert report["checks"]["catalog_names_contentdisposition"]
    assert report["checks"]["catalog_names_weblinking"]
    assert report["checks"]["leftover_text_binds_contentdisposition"]
    assert report["checks"]["proved_contentdisposition_consumes_leftover"]
    assert report["mission_goal"] == CONTENTDISPOSITION_ACTUATION_GOAL
    assert report["done_when"] == CONTENTDISPOSITION_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[CONTENTDISPOSITION_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "contentdisposition" in capability.tags
    assert "rfc6266" in capability.tags
    assert "http" in capability.tags
    assert "dispositionid" in capability.tags
    assert "dispositiondigest" in capability.tags
    assert "attachment" in capability.tags


def test_selection_gate_accepts_contentdisposition_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        CONTENTDISPOSITION_ACTUATION_GOAL,
        CONTENTDISPOSITION_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(CONTENTDISPOSITION_ACTUATION_GOAL)
    assert "contentdisposition" in family
    assert "rfc6266" in family
    assert "dispositionid" in family
    assert "dispositiondigest" in family
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
    assert "weblinking" not in family
    assert "rfc5988" not in family
    assert "relationid" not in family
    assert "relationdigest" not in family
    assert "httpcookie" not in family
    assert "rfc6265" not in family
    assert "cookieid" not in family
    assert "cookiedigest" not in family
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
