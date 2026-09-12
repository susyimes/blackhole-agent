from pathlib import Path

from blackhole_agent.tcp_actuation import (
    TCP_ACTUATION_GOAL,
    TCP_ACTUATION_ID,
)
from blackhole_agent.udp_actuation import (
    UDP_ACTUATION_GOAL,
    UDP_ACTUATION_ID,
)

from blackhole_agent.spnego_actuation import (
    SPNEGO_ACTUATION_GOAL,
    SPNEGO_ACTUATION_ID,
)
from blackhole_agent.rarp_actuation import (
    RARP_ACTUATION_GOAL,
    RARP_ACTUATION_ID,
)
from blackhole_agent.ip_actuation import (
    IP_ACTUATION_GOAL,
    IP_ACTUATION_ID,
)
from blackhole_agent.icmp_actuation import (
    ICMP_ACTUATION_GOAL,
    ICMP_ACTUATION_ID,
)
from blackhole_agent.telnet_actuation import (
    TELNET_ACTUATION_GOAL,
    TELNET_ACTUATION_ID,
)
from blackhole_agent.finger_actuation import (
    FINGER_ACTUATION_GOAL,
    FINGER_ACTUATION_ID,
)
from blackhole_agent.mime_actuation import (
    MIME_ACTUATION_GOAL,
    MIME_ACTUATION_ID,
)
from blackhole_agent.uri_actuation import (
    URI_ACTUATION_GOAL,
    URI_ACTUATION_ID,
)
from blackhole_agent.http10_actuation import (
    HTTP10_ACTUATION_GOAL,
    HTTP10_ACTUATION_ID,
)
from blackhole_agent.httpstate_actuation import (
    HTTPSTATE_ACTUATION_GOAL,
    HTTPSTATE_ACTUATION_ID,
)
from blackhole_agent.httpver_actuation import (
    HTTPVER_ACTUATION_GOAL,
    HTTPVER_ACTUATION_ID,
)
from blackhole_agent.icp_actuation import (
    ICP_ACTUATION_GOAL,
    ICP_ACTUATION_ID,
)
from blackhole_agent.tcn_actuation import (
    TCN_ACTUATION_GOAL,
    TCN_ACTUATION_ID,
)
from blackhole_agent.httpauth_actuation import (
    HTTPAUTH_ACTUATION_GOAL,
    HTTPAUTH_ACTUATION_ID,
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
from blackhole_agent.digestauth_actuation import (
    DIGESTAUTH_ACTUATION_GOAL,
    DIGESTAUTH_ACTUATION_ID,
)
from blackhole_agent.arp_actuation import (
    DEFAULT_ARPID,
    DEFAULT_ARPDIGEST,
    DEFAULT_REQUEST,
    EMPTY_ARPID,
    FRAME_REPLY,
    FRAME_REQUEST,
    ARP_ACTUATION_DONE_WHEN,
    ARP_ACTUATION_GOAL,
    ARP_ACTUATION_ID,
    ARP_LEFTOVER,
    ARP_FIRST,
    REPLY_POLICY,
    RFC_REQUEST_FIELD,
    RFC_REPLY_FIELD,
    SENTINEL,
    REQUEST_HEADER,
    builtin_arp_actuation_proof,
    canonical_reply,
    canonical_request,
    crc32c,
    encode_reply,
    encode_request,
    encode_arp_header,
    independent_arpdigest,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_arp,
    parse_arp_header,
    reply_request,
    reply_response,
    run_arp_workflow,
    serialize_arp,
    request_request,
    request_response,
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
    ARP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    build_tool_routing_preflight,
    arp_tool_descriptor,
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
    RARP_ACTUATION_GOAL,
    IP_ACTUATION_GOAL,
    ICMP_ACTUATION_GOAL,
    UDP_ACTUATION_GOAL,
    TCP_ACTUATION_GOAL,
    TELNET_ACTUATION_GOAL,
    FINGER_ACTUATION_GOAL,
    MIME_ACTUATION_GOAL,
    URI_ACTUATION_GOAL,
    HTTP10_ACTUATION_GOAL,
    DIGESTAUTH_ACTUATION_GOAL,
    HTTPSTATE_ACTUATION_GOAL,
    HTTPVER_ACTUATION_GOAL,
    ICP_ACTUATION_GOAL,
    TCN_ACTUATION_GOAL,
    HTTPAUTH_ACTUATION_GOAL,
    SPNEGO_ACTUATION_GOAL,
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
    RARP_ACTUATION_ID,
    IP_ACTUATION_ID,
    ICMP_ACTUATION_ID,
    UDP_ACTUATION_ID,
    TCP_ACTUATION_ID,
    TELNET_ACTUATION_ID,
    FINGER_ACTUATION_ID,
    MIME_ACTUATION_ID,
    URI_ACTUATION_ID,
    HTTP10_ACTUATION_ID,
    DIGESTAUTH_ACTUATION_ID,
    HTTPSTATE_ACTUATION_ID,
    HTTPVER_ACTUATION_ID,
    ICP_ACTUATION_ID,
    TCN_ACTUATION_ID,
    HTTPAUTH_ACTUATION_ID,
    SPNEGO_ACTUATION_ID,
    STALECONTENT_ACTUATION_ID,
)


def test_goal_binds_arp_actuation_plane() -> None:
    assert leftover_marker_ids(ARP_ACTUATION_GOAL) == (ARP_ACTUATION_ID,)
    assert leftover_marker_ids(ARP_LEFTOVER) == (ARP_ACTUATION_ID,)
    assert leftover_marker_ids(RARP_ACTUATION_GOAL) == (RARP_ACTUATION_ID,)
    assert leftover_marker_ids(IP_ACTUATION_GOAL) == (IP_ACTUATION_ID,)
    assert leftover_marker_ids(ICMP_ACTUATION_GOAL) == (ICMP_ACTUATION_ID,)
    assert leftover_marker_ids(UDP_ACTUATION_GOAL) == (UDP_ACTUATION_ID,)
    assert leftover_marker_ids(TCP_ACTUATION_GOAL) == (TCP_ACTUATION_ID,)
    assert leftover_marker_ids(TELNET_ACTUATION_GOAL) == (TELNET_ACTUATION_ID,)
    assert leftover_marker_ids(FINGER_ACTUATION_GOAL) == (FINGER_ACTUATION_ID,)
    assert leftover_marker_ids(MIME_ACTUATION_GOAL) == (MIME_ACTUATION_ID,)
    assert leftover_marker_ids(URI_ACTUATION_GOAL) == (URI_ACTUATION_ID,)
    assert leftover_marker_ids(HTTP10_ACTUATION_GOAL) == (HTTP10_ACTUATION_ID,)
    assert HTTP10_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(DIGESTAUTH_ACTUATION_GOAL) == (DIGESTAUTH_ACTUATION_ID,)
    assert RARP_ACTUATION_ID in LOCAL_DENYLIST
    assert IP_ACTUATION_ID in LOCAL_DENYLIST
    assert TELNET_ACTUATION_ID in LOCAL_DENYLIST
    assert FINGER_ACTUATION_ID in LOCAL_DENYLIST
    assert MIME_ACTUATION_ID in LOCAL_DENYLIST
    assert URI_ACTUATION_ID in LOCAL_DENYLIST
    assert DIGESTAUTH_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HTTPSTATE_ACTUATION_GOAL) == (HTTPSTATE_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPAUTH_ACTUATION_GOAL) == (HTTPAUTH_ACTUATION_ID,)
    assert leftover_marker_ids(TCN_ACTUATION_GOAL) == (TCN_ACTUATION_ID,)
    assert leftover_marker_ids(ICP_ACTUATION_GOAL) == (ICP_ACTUATION_ID,)
    assert ARP_ACTUATION_ID in LOCAL_DENYLIST
    assert ARP_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPSTATE_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPAUTH_ACTUATION_ID in LOCAL_DENYLIST
    assert TCN_ACTUATION_ID in LOCAL_DENYLIST
    assert ICP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(SPNEGO_ACTUATION_GOAL) == (SPNEGO_ACTUATION_ID,)
    assert leftover_marker_ids(STALECONTENT_ACTUATION_GOAL) == (STALECONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EXTVALUE_ACTUATION_GOAL) == (EXTVALUE_ACTUATION_ID,)
    assert leftover_marker_ids(WEBLINKING_ACTUATION_GOAL) == (WEBLINKING_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPCOOKIE_ACTUATION_GOAL) == (HTTPCOOKIE_ACTUATION_ID,)
    assert leftover_marker_ids(WEBORIGIN_ACTUATION_GOAL) == (WEBORIGIN_ACTUATION_ID,)
    assert leftover_marker_ids(XFO_ACTUATION_GOAL) == (XFO_ACTUATION_ID,)
    assert ARP_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPSTATE_ACTUATION_ID in LOCAL_DENYLIST
    assert ARP_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPSTATE_ACTUATION_ID in LOCAL_DENYLIST
    assert SPNEGO_ACTUATION_ID in LOCAL_DENYLIST
    assert STALECONTENT_ACTUATION_ID in LOCAL_DENYLIST
    assert EXTVALUE_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBLINKING_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPCOOKIE_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBORIGIN_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HSTS_ACTUATION_GOAL) == (HSTS_ACTUATION_ID,)
    assert leftover_marker_ids(HPKP_ACTUATION_GOAL) == (HPKP_ACTUATION_ID,)
    assert leftover_marker_ids(ARP_ACTUATION_GOAL) == (ARP_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPSTATE_ACTUATION_GOAL) == (HTTPSTATE_ACTUATION_ID,)
    assert leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (ALTSVC_ACTUATION_ID,)
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert HSTS_ACTUATION_ID in LOCAL_DENYLIST
    assert HPKP_ACTUATION_ID in LOCAL_DENYLIST
    assert ARP_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPSTATE_ACTUATION_ID in LOCAL_DENYLIST
    assert ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert ARP_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(ARP_ACTUATION_GOAL)
    icp_signature = semantic_signature(ARP_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(icp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_arp_tool_completes_body_transfer_poll() -> None:
    descriptor = arp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ARP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("arp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ARP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["arp"]

    missing = run_arp_workflow(with_arpid=False)
    skip_bind = run_arp_workflow(skip_bind=True)
    skip_request = run_arp_workflow(do_request=False)
    skip_reply = run_arp_workflow(do_reply=False)
    skip_arpdigest = run_arp_workflow(do_arpdigest=False)
    skip_replay = run_arp_workflow(replay=False)
    skip_arpid = run_arp_workflow(use_arpid=False)
    live = run_arp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_arpid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_request["ok"] is False
    assert skip_request["error"] == "request_required"
    assert skip_reply["ok"] is False
    assert skip_reply["error"] == "reply_required"
    assert skip_arpdigest["ok"] is False
    assert skip_arpdigest["error"] == "arpdigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_arpid["ok"] is False
    assert skip_arpid["error"] == "arpid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_arpdigest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["request_frame"] is True
    assert row["reply_frame"] is True
    assert row["arpdigest_locate"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["arpid_bound"] is True
    assert row["digest"]
    assert live["arpid"] == DEFAULT_ARPID
    assert live["arpdigest"] == DEFAULT_ARPDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_request(identity=SENTINEL, arpid=DEFAULT_ARPID, arpdigest=DEFAULT_ARPDIGEST)
    )
    assert queried["is_request"] is True and queried["is_reply"] is False
    assert queried["identity"] == SENTINEL and queried["arpid"] == DEFAULT_ARPID
    assert queried["arpdigest"] == DEFAULT_ARPDIGEST
    assert queried["type"] == FRAME_REQUEST
    assert queried["first_byte"] == ARP_FIRST
    answered = parse_message(
        encode_reply(identity=SENTINEL, arpid=DEFAULT_ARPID, arpdigest=DEFAULT_ARPDIGEST)
    )
    assert answered["is_reply"] is True and answered["is_reply"] is True
    assert answered["arpid"] == DEFAULT_ARPID
    assert answered["arpdigest"] == DEFAULT_ARPDIGEST
    packed = encode_request(identity=SENTINEL, arpid=DEFAULT_ARPID, arpdigest=DEFAULT_ARPDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_request(identity=SENTINEL, arpid=DEFAULT_ARPID, include_arpid=False)
    )
    assert bare["has_arpid"] is False
    assert bare["arpid"] == EMPTY_ARPID
    advertised = serialize_arp(DEFAULT_REQUEST)
    assert advertised == RFC_REQUEST_FIELD
    assert parse_arp(advertised) == DEFAULT_REQUEST
    assert parse_arp(RFC_REPLY_FIELD) == REPLY_POLICY
    header = parse_arp_header(encode_arp_header(DEFAULT_REQUEST))
    assert header["field_value"] == RFC_REQUEST_FIELD
    assert header["header"] == REQUEST_HEADER
    asked = parse_http_request(request_request(SENTINEL, DEFAULT_ARPID))
    listed = parse_http_request(reply_request(SENTINEL, DEFAULT_ARPID, DEFAULT_ARPDIGEST))
    got = parse_http_response(request_response(SENTINEL, DEFAULT_ARPID, DEFAULT_ARPDIGEST))
    preload_reply = parse_http_response(
        reply_response(SENTINEL, DEFAULT_ARPID, DEFAULT_ARPDIGEST)
    )
    assert asked["method"] == "REQUEST"
    assert asked["arp_kind"] == "request"
    assert listed["arp_kind"] == "reply"
    assert got["status"] == 200
    assert preload_reply["status"] == 200
    assert got["policy"] == DEFAULT_REQUEST
    assert preload_reply["policy"] == REPLY_POLICY
    assert canonical_request(SENTINEL, DEFAULT_ARPID).startswith("REQUEST")
    assert "arpdigest=" in canonical_reply(SENTINEL, DEFAULT_ARPID, DEFAULT_ARPDIGEST)


def test_builtin_proof_seals_arp_actuation() -> None:
    report = builtin_arp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "arp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_arp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_arpid_is_forbidden"]
    assert report["checks"]["skip_request_stays_empty"]
    assert report["checks"]["skip_reply_stays_empty"]
    assert report["checks"]["skip_arpdigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_arpid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_arpdigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_arp"]
    assert report["checks"]["catalog_names_arp"]
    assert report["checks"]["catalog_names_rarp"]
    assert report["checks"]["leftover_text_binds_arp"]
    assert report["checks"]["proved_arp_consumes_leftover"]
    assert report["mission_goal"] == ARP_ACTUATION_GOAL
    assert report["done_when"] == ARP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[ARP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "arp" in capability.tags
    assert "rfc826" in capability.tags
    assert "http" in capability.tags
    assert "arpid" in capability.tags
    assert "arpdigest" in capability.tags
    assert "request" in capability.tags


def test_selection_gate_rejects_ledger_only_arp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        ARP_ACTUATION_GOAL,
        ARP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is False
    assert gate.reasons == (
        "marginal_value_gate: ledger registration/self-proof alone is not an outcome acceptance contract",
    )
    assert gate.scalar_extension is False
    family = capability_family(ARP_ACTUATION_GOAL)
    family_tokens = set(family.split("/"))
    assert "arp" in family.split("/")
    assert "rfc826" in family
    assert "arpid" in family
    assert "arpdigest" in family
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
    assert "spnego" not in family
    assert "rfc4559" not in family
    assert "negotiateid" not in family
    assert "negotiatedigest" not in family
    assert "rarp" not in family.split("/")
    assert "ip" not in family.split("/")
    assert "udp" not in family.split("/")
    assert "tcp" not in family.split("/")
    assert "telnet" not in family.split("/")
    assert "finger" not in family.split("/")
    assert "rfc768" not in family
    assert "udpid" not in family
    assert "udpdigest" not in family
    assert "rfc793" not in family
    assert "tcpid" not in family
    assert "tcpdigest" not in family
    assert "rfc903" not in family
    assert "rfc791" not in family
    assert "rarpid" not in family
    assert "ipid" not in family
    assert "rarpdigest" not in family
    assert "ipdigest" not in family
    assert "rfc854" not in family
    assert "telnetid" not in family
    assert "telnetdigest" not in family
    assert "rfc1288" not in family
    assert "fingerid" not in family
    assert "fingerdigest" not in family
    assert "mime" not in family.split("/")
    assert "rfc1521" not in family
    assert "mimeid" not in family
    assert "mimedigest" not in family
    assert "uri" not in family.split("/")
    assert "rfc1630" not in family
    assert "uriid" not in family
    assert "uridigest" not in family
    assert "http10" not in family.split("/")
    assert "rfc1945" not in family
    assert "http10id" not in family
    assert "http10digest" not in family
    assert "digestauth" not in family
    assert "rfc2069" not in family
    assert "httpstate" not in family
    assert "rfc903" not in family
    assert "rfc791" not in family
    assert "rfc2109" not in family
    assert "rarpid" not in family
    assert "ipid" not in family
    assert "stateid" not in family
    assert "rarpdigest" not in family
    assert "ipdigest" not in family
    assert "statedigest" not in family
    assert "icp" not in family
    assert "rfc2186" not in family
    assert "queryid" not in family
    assert "icpdigest" not in family
    assert "tcn" not in family
    assert "rfc2295" not in family
    assert "variantid" not in family
    assert "choicedigest" not in family
    assert "httpauth" not in family
    assert "httpauth" not in family
    assert "rfc2617" not in family
    assert "nonceid" not in family
    assert "authdigest" not in family
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
    assert "httpver" not in family
    assert "rfc2145" not in family
    assert "versionid" not in family
    assert "versiondigest" not in family
    assert "icp" not in family
    assert "rfc2186" not in family
    assert "queryid" not in family
    assert "icpdigest" not in family
    assert "tcn" not in family
    assert "rfc2295" not in family
    assert "variantid" not in family
    assert "choicedigest" not in family
    assert "httpauth" not in family
    assert "httpauth" not in family
    assert "rfc2617" not in family
    assert "nonceid" not in family
    assert "authdigest" not in family
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
