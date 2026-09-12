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
from blackhole_agent.rdnss_actuation import (
    RDNSS_ACTUATION_GOAL,
    RDNSS_ACTUATION_ID,
)
from blackhole_agent.addrpolicy_actuation import (
    ADDRPOLICY_ACTUATION_GOAL,
    ADDRPOLICY_ACTUATION_ID,
)
from blackhole_agent.addrselect_actuation import (
    ADDRSELECT_ACTUATION_GOAL,
    ADDRSELECT_ACTUATION_ID,
)
from blackhole_agent.ipv6scope_actuation import (
    IPV6SCOPE_ACTUATION_GOAL,
    IPV6SCOPE_ACTUATION_ID,
)
from blackhole_agent.ipv6addr_actuation import (
    IPV6ADDR_ACTUATION_GOAL,
    IPV6ADDR_ACTUATION_ID,
)
from blackhole_agent.ula_actuation import (
    ULA_ACTUATION_GOAL,
    ULA_ACTUATION_ID,
)
from blackhole_agent.cga_actuation import (
    CGA_ACTUATION_GOAL,
    CGA_ACTUATION_ID,
)
from blackhole_agent.opaqueiid_actuation import (
    OPAQUEIID_ACTUATION_GOAL,
    OPAQUEIID_ACTUATION_ID,
)
from blackhole_agent.tempaddr_actuation import (
    TEMPADDR_ACTUATION_GOAL,
    TEMPADDR_ACTUATION_ID,
)
from blackhole_agent.slaac_actuation import (
    SLAAC_ACTUATION_GOAL,
    SLAAC_ACTUATION_ID,
)
from blackhole_agent.ndp_actuation import (
    NDP_ACTUATION_GOAL,
    NDP_ACTUATION_ID,
)
from blackhole_agent.mld_actuation import (
    MLD_ACTUATION_GOAL,
    MLD_ACTUATION_ID,
)
from blackhole_agent.igmp_actuation import (
    IGMP_ACTUATION_GOAL,
    IGMP_ACTUATION_ID,
)
from blackhole_agent.rarp_actuation import (
    RARP_ACTUATION_GOAL,
    RARP_ACTUATION_ID,
)
from blackhole_agent.arp_actuation import (
    ARP_ACTUATION_GOAL,
    ARP_ACTUATION_ID,
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
from blackhole_agent.firsthop_actuation import (
    DEFAULT_HOPID,
    DEFAULT_HOPDIGEST,
    DEFAULT_SOURCE,
    EMPTY_HOPID,
    FRAME_DEST,
    FRAME_SOURCE,
    FIRSTHOP_ACTUATION_DONE_WHEN,
    FIRSTHOP_ACTUATION_GOAL,
    FIRSTHOP_ACTUATION_ID,
    FIRSTHOP_LEFTOVER,
    FIRSTHOP_FIRST,
    DEST_HOP,
    RFC_SOURCE_FIELD,
    RFC_DEST_FIELD,
    SENTINEL,
    SOURCE_HEADER,
    builtin_firsthop_actuation_proof,
    canonical_public,
    canonical_temporary,
    crc32c,
    encode_public,
    encode_temporary,
    encode_firsthop_header,
    independent_hopdigest,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_firsthop,
    parse_firsthop_header,
    public_request,
    public_response,
    run_firsthop_workflow,
    serialize_firsthop,
    temporary_request,
    temporary_response,
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
    FIRSTHOP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    build_tool_routing_preflight,
    firsthop_tool_descriptor,
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
    RDNSS_ACTUATION_GOAL,
    ADDRPOLICY_ACTUATION_GOAL,
    ADDRSELECT_ACTUATION_GOAL,
    IPV6SCOPE_ACTUATION_GOAL,
    IPV6ADDR_ACTUATION_GOAL,
    ULA_ACTUATION_GOAL,
    CGA_ACTUATION_GOAL,
    OPAQUEIID_ACTUATION_GOAL,
    TEMPADDR_ACTUATION_GOAL,
    SLAAC_ACTUATION_GOAL,
    NDP_ACTUATION_GOAL,
    MLD_ACTUATION_GOAL,
    IGMP_ACTUATION_GOAL,
    RARP_ACTUATION_GOAL,
    ARP_ACTUATION_GOAL,
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
    RDNSS_ACTUATION_ID,
    ADDRPOLICY_ACTUATION_ID,
    ADDRSELECT_ACTUATION_ID,
    IPV6SCOPE_ACTUATION_ID,
    IPV6ADDR_ACTUATION_ID,
    ULA_ACTUATION_ID,
    CGA_ACTUATION_ID,
    OPAQUEIID_ACTUATION_ID,
    TEMPADDR_ACTUATION_ID,
    SLAAC_ACTUATION_ID,
    NDP_ACTUATION_ID,
    MLD_ACTUATION_ID,
    IGMP_ACTUATION_ID,
    RARP_ACTUATION_ID,
    ARP_ACTUATION_ID,
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


def test_goal_binds_firsthop_actuation_plane() -> None:
    assert leftover_marker_ids(FIRSTHOP_ACTUATION_GOAL) == (FIRSTHOP_ACTUATION_ID,)
    assert leftover_marker_ids(ADDRPOLICY_ACTUATION_GOAL) == (ADDRPOLICY_ACTUATION_ID,)
    assert leftover_marker_ids(ADDRSELECT_ACTUATION_GOAL) == (ADDRSELECT_ACTUATION_ID,)
    assert leftover_marker_ids(RDNSS_ACTUATION_GOAL) == (RDNSS_ACTUATION_ID,)
    assert ADDRPOLICY_ACTUATION_ID in LOCAL_DENYLIST
    assert ADDRSELECT_ACTUATION_ID in LOCAL_DENYLIST
    assert RDNSS_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(FIRSTHOP_LEFTOVER) == (FIRSTHOP_ACTUATION_ID,)
    assert leftover_marker_ids(RDNSS_ACTUATION_GOAL) == (RDNSS_ACTUATION_ID,)
    assert leftover_marker_ids(IPV6SCOPE_ACTUATION_GOAL) == (IPV6SCOPE_ACTUATION_ID,)
    assert leftover_marker_ids(IPV6ADDR_ACTUATION_GOAL) == (IPV6ADDR_ACTUATION_ID,)
    assert leftover_marker_ids(ULA_ACTUATION_GOAL) == (ULA_ACTUATION_ID,)
    assert leftover_marker_ids(CGA_ACTUATION_GOAL) == (CGA_ACTUATION_ID,)
    assert leftover_marker_ids(OPAQUEIID_ACTUATION_GOAL) == (OPAQUEIID_ACTUATION_ID,)
    assert OPAQUEIID_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(TEMPADDR_ACTUATION_GOAL) == (TEMPADDR_ACTUATION_ID,)
    assert leftover_marker_ids(SLAAC_ACTUATION_GOAL) == (SLAAC_ACTUATION_ID,)
    assert leftover_marker_ids(NDP_ACTUATION_GOAL) == (NDP_ACTUATION_ID,)
    assert leftover_marker_ids(MLD_ACTUATION_GOAL) == (MLD_ACTUATION_ID,)
    assert leftover_marker_ids(IGMP_ACTUATION_GOAL) == (IGMP_ACTUATION_ID,)
    assert leftover_marker_ids(RARP_ACTUATION_GOAL) == (RARP_ACTUATION_ID,)
    assert leftover_marker_ids(ARP_ACTUATION_GOAL) == (ARP_ACTUATION_ID,)
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
    assert FIRSTHOP_ACTUATION_ID in LOCAL_DENYLIST
    assert ULA_ACTUATION_ID in LOCAL_DENYLIST
    assert FIRSTHOP_ACTUATION_ID in LOCAL_DENYLIST
    assert RDNSS_ACTUATION_ID in LOCAL_DENYLIST
    assert IPV6SCOPE_ACTUATION_ID in LOCAL_DENYLIST
    assert CGA_ACTUATION_ID in LOCAL_DENYLIST
    assert TEMPADDR_ACTUATION_ID in LOCAL_DENYLIST
    assert SLAAC_ACTUATION_ID in LOCAL_DENYLIST
    assert NDP_ACTUATION_ID in LOCAL_DENYLIST
    assert MLD_ACTUATION_ID in LOCAL_DENYLIST
    assert IGMP_ACTUATION_ID in LOCAL_DENYLIST
    assert RARP_ACTUATION_ID in LOCAL_DENYLIST
    assert ARP_ACTUATION_ID in LOCAL_DENYLIST
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
    assert FIRSTHOP_ACTUATION_ID in LOCAL_DENYLIST
    assert FIRSTHOP_ACTUATION_ID in LOCAL_DENYLIST
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
    assert FIRSTHOP_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPSTATE_ACTUATION_ID in LOCAL_DENYLIST
    assert FIRSTHOP_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPSTATE_ACTUATION_ID in LOCAL_DENYLIST
    assert SPNEGO_ACTUATION_ID in LOCAL_DENYLIST
    assert STALECONTENT_ACTUATION_ID in LOCAL_DENYLIST
    assert EXTVALUE_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBLINKING_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPCOOKIE_ACTUATION_ID in LOCAL_DENYLIST
    assert WEBORIGIN_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HSTS_ACTUATION_GOAL) == (HSTS_ACTUATION_ID,)
    assert leftover_marker_ids(HPKP_ACTUATION_GOAL) == (HPKP_ACTUATION_ID,)
    assert leftover_marker_ids(FIRSTHOP_ACTUATION_GOAL) == (FIRSTHOP_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPSTATE_ACTUATION_GOAL) == (HTTPSTATE_ACTUATION_ID,)
    assert leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (ALTSVC_ACTUATION_ID,)
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert HSTS_ACTUATION_ID in LOCAL_DENYLIST
    assert HPKP_ACTUATION_ID in LOCAL_DENYLIST
    assert FIRSTHOP_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPSTATE_ACTUATION_ID in LOCAL_DENYLIST
    assert ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert FIRSTHOP_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(FIRSTHOP_ACTUATION_GOAL)
    icp_signature = semantic_signature(FIRSTHOP_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(icp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_firsthop_tool_completes_body_transfer_poll() -> None:
    descriptor = firsthop_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FIRSTHOP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("firsthop",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FIRSTHOP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["firsthop"]

    missing = run_firsthop_workflow(with_hopid=False)
    skip_bind = run_firsthop_workflow(skip_bind=True)
    skip_temporary = run_firsthop_workflow(do_temporary=False)
    skip_public = run_firsthop_workflow(do_public=False)
    skip_hopdigest = run_firsthop_workflow(do_hopdigest=False)
    skip_replay = run_firsthop_workflow(replay=False)
    skip_hopid = run_firsthop_workflow(use_hopid=False)
    live = run_firsthop_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_hopid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_temporary["ok"] is False
    assert skip_temporary["error"] == "temporary_required"
    assert skip_public["ok"] is False
    assert skip_public["error"] == "public_required"
    assert skip_hopdigest["ok"] is False
    assert skip_hopdigest["error"] == "hopdigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_hopid["ok"] is False
    assert skip_hopid["error"] == "hopid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_hopdigest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["temporary_frame"] is True
    assert row["public_frame"] is True
    assert row["hopdigest_locate"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["hopid_bound"] is True
    assert row["digest"]
    assert live["hopid"] == DEFAULT_HOPID
    assert live["hopdigest"] == DEFAULT_HOPDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_temporary(identity=SENTINEL, hopid=DEFAULT_HOPID, hopdigest=DEFAULT_HOPDIGEST)
    )
    assert queried["is_temporary"] is True and queried["is_public"] is False
    assert queried["identity"] == SENTINEL and queried["hopid"] == DEFAULT_HOPID
    assert queried["hopdigest"] == DEFAULT_HOPDIGEST
    assert queried["type"] == FRAME_SOURCE
    assert queried["first_byte"] == FIRSTHOP_FIRST
    answered = parse_message(
        encode_public(identity=SENTINEL, hopid=DEFAULT_HOPID, hopdigest=DEFAULT_HOPDIGEST)
    )
    assert answered["is_public"] is True and answered["is_public"] is True
    assert answered["hopid"] == DEFAULT_HOPID
    assert answered["hopdigest"] == DEFAULT_HOPDIGEST
    packed = encode_temporary(identity=SENTINEL, hopid=DEFAULT_HOPID, hopdigest=DEFAULT_HOPDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_temporary(identity=SENTINEL, hopid=DEFAULT_HOPID, include_hopid=False)
    )
    assert bare["has_hopid"] is False
    assert bare["hopid"] == EMPTY_HOPID
    publicised = serialize_firsthop(DEFAULT_SOURCE)
    assert publicised == RFC_SOURCE_FIELD
    assert parse_firsthop(publicised) == DEFAULT_SOURCE
    assert parse_firsthop(RFC_DEST_FIELD) == DEST_HOP
    header = parse_firsthop_header(encode_firsthop_header(DEFAULT_SOURCE))
    assert header["field_value"] == RFC_SOURCE_FIELD
    assert header["header"] == SOURCE_HEADER
    asked = parse_http_request(temporary_request(SENTINEL, DEFAULT_HOPID))
    listed = parse_http_request(public_request(SENTINEL, DEFAULT_HOPID, DEFAULT_HOPDIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_HOPID, DEFAULT_HOPDIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_HOPID, DEFAULT_HOPDIGEST)
    )
    assert asked["method"] == "FIRST"
    assert asked["firsthop_kind"] == "first"
    assert listed["firsthop_kind"] == "hop"
    assert got["status"] == 200
    assert preload_public["status"] == 200
    assert got["policy"] == DEFAULT_SOURCE
    assert preload_public["policy"] == DEST_HOP
    assert canonical_temporary(SENTINEL, DEFAULT_HOPID).startswith("FIRST")
    assert "hopdigest=" in canonical_public(SENTINEL, DEFAULT_HOPID, DEFAULT_HOPDIGEST)


def test_builtin_proof_seals_firsthop_actuation() -> None:
    report = builtin_firsthop_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "firsthop_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_firsthop"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_hopid_is_forbidden"]
    assert report["checks"]["skip_temporary_stays_empty"]
    assert report["checks"]["skip_public_stays_empty"]
    assert report["checks"]["skip_hopdigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_hopid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_hopdigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_firsthop"]
    assert report["checks"]["catalog_names_addrselect"]
    assert report["checks"]["catalog_names_addrpolicy"]
    assert report["checks"]["catalog_names_firsthop"]
    assert report["checks"]["catalog_names_rdnss"]
    assert report["checks"]["leftover_text_binds_firsthop"]
    assert report["checks"]["proved_firsthop_consumes_leftover"]
    assert report["mission_goal"] == FIRSTHOP_ACTUATION_GOAL
    assert report["done_when"] == FIRSTHOP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[FIRSTHOP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "firsthop" in capability.tags
    assert "rfc8028" in capability.tags
    assert "http" in capability.tags
    assert "hopid" in capability.tags
    assert "hopdigest" in capability.tags
    assert "first" in capability.tags
    assert "hop" in capability.tags


def test_selection_gate_rejects_ledger_only_firsthop_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        FIRSTHOP_ACTUATION_GOAL,
        FIRSTHOP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is False
    assert gate.reasons == (
        "marginal_value_gate: ledger registration/self-proof alone is not an outcome acceptance contract",
    )
    assert gate.scalar_extension is False
    family = capability_family(FIRSTHOP_ACTUATION_GOAL)
    family_tokens = set(family.split("/"))
    assert "firsthop" in family.split("/")
    assert "rfc8028" in family
    assert "hopid" in family
    assert "hopdigest" in family
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
    assert "rdnss" not in family.split("/")
    assert "rfc8106" not in family
    assert "rdnssid" not in family
    assert "rdnssdigest" not in family
    assert "addrpolicy" not in family.split("/")
    assert "rfc7078" not in family
    assert "policyid" not in family
    assert "policydigest" not in family
    assert "addrselect" not in family.split("/")
    assert "rfc6724" not in family
    assert "selectid" not in family
    assert "selectdigest" not in family
    assert "ipv6scope" not in family.split("/")
    assert "rfc4007" not in family
    assert "scopeid" not in family
    assert "scopedigest" not in family
    assert "ipv6addr" not in family.split("/")
    assert "ula" not in family.split("/")
    assert "send" not in family.split("/")
    assert "cga" not in family.split("/")
    assert "opaqueiid" not in family.split("/")
    assert "rfc7217" not in family
    assert "opaqueid" not in family
    assert "opaquedigest" not in family
    assert "tempaddr" not in family.split("/")
    assert "rfc4941" not in family
    assert "tempaddrid" not in family
    assert "tempaddrdigest" not in family
    assert "slaac" not in family.split("/")
    assert "ndp" not in family.split("/")
    assert "mld" not in family.split("/")
    assert "igmp" not in family.split("/")
    assert "rarp" not in family.split("/")
    assert "arp" not in family.split("/")
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
    assert "rfc4291" not in family
    assert "rfc4193" not in family
    assert "rfc3971" not in family
    assert "rfc3972" not in family
    assert "rfc4862" not in family
    assert "rfc4861" not in family
    assert "rfc2710" not in family
    assert "rfc1112" not in family
    assert "rfc903" not in family
    assert "rfc826" not in family
    assert "rfc791" not in family
    assert "ipv6addrid" not in family
    assert "ulaid" not in family
    assert "sendid" not in family
    assert "cgaid" not in family
    assert "ndpid" not in family
    assert "mldid" not in family
    assert "igmpid" not in family
    assert "rarpid" not in family
    assert "arpid" not in family.split("/")
    assert "ipid" not in family
    assert "ipv6addrdigest" not in family
    assert "uladigest" not in family
    assert "senddigest" not in family
    assert "cgadigest" not in family
    assert "ndpdigest" not in family
    assert "mlddigest" not in family
    assert "igmpdigest" not in family
    assert "rarpdigest" not in family
    assert "arpdigest" not in family.split("/")
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
    assert "rfc4291" not in family
    assert "rfc791" not in family
    assert "rfc2109" not in family
    assert "ipv6addrid" not in family
    assert "ipid" not in family
    assert "stateid" not in family
    assert "ipv6addrdigest" not in family
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
