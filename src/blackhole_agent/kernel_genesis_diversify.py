"""Bind a gate-passing successor when the compounding catalog is exhausted.

``bind_gate_passing_successor`` walks the compounding ``SUCCESSOR_CATALOG``.
After program weave is proved, the compounding catalog is exhausted. On live
history that weave is a repetition-gate near-duplicate of fabric/lattice/tower,
so bind returns empty unless forage-shaped history still accepts it. Recovered
kernels and first-class genesis then invent until ``genesis_selection_blocked``.

This module closes that hole:

- detect when the compounding catalog has no remaining gate-passing successor
- rank a diversity catalog of unsaturated capability families
- bind the first open, gate-passing diversity mission
- skip a proved diversity item to the next gate-passing family
- preserve operator fields and unscoped remaining campaign work
"""

from __future__ import annotations

# Compatibility exports used by existing capability proofs. Keep them explicit
# while the selector's own proof now checks outcomes rather than catalog names.
from blackhole_agent.kernel_genesis_bind import (
    KERNEL_GENESIS_BIND_GOAL as KERNEL_GENESIS_BIND_GOAL,
    PROGRAM_WEAVE_GOAL as PROGRAM_WEAVE_GOAL,
    PROGRAM_WEAVE_ID as PROGRAM_WEAVE_ID,
    _State as _State,
    _unscoped_remaining_campaign as _unscoped_remaining_campaign,
    _write_forage_history as _write_forage_history,
    bind_gate_passing_successor as bind_gate_passing_successor,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids as leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST as LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import bind_local_mission as bind_local_mission
from blackhole_agent.mission_selection import semantic_similarity as semantic_similarity

import tempfile
from pathlib import Path
from typing import Any, Sequence

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_genesis_bind import (
    COMPOUND_LOOP_ID,
    COMPOSED_PROGRAM_ID,
    CONSUMED_GROWTH_ID,
    KERNEL_GENESIS_BIND_ID,
    PRIMITIVE_COMPOSE_ID,
    PROGRAM_FABRIC_GOAL,
    PROGRAM_FABRIC_ID,
    PROGRAM_LATTICE_GOAL,
    PROGRAM_LATTICE_ID,
    PROGRAM_STACK_ID,
    PROGRAM_TOWER_GOAL,
    PROGRAM_TOWER_ID,
    _catalog_item_open,
    _consumed_campaign,
    _register_proved,
    _write_complete_mission,
    genesis_bind_is_needed,
)
from blackhole_agent.kernel_half_open_persist import (
    HALF_OPEN_PERSIST_DONE_WHEN,
    HALF_OPEN_PERSIST_GOAL,
    HALF_OPEN_PERSIST_ID,
)
from blackhole_agent.kernel_mission_memory import (
    MISSION_MEMORY_DONE_WHEN,
    MISSION_MEMORY_GOAL,
    MISSION_MEMORY_ID,
)
from blackhole_agent.mcp_call_isolation import (
    MCP_CALL_DONE_WHEN,
    MCP_CALL_GOAL,
    MCP_CALL_ID,
)
from blackhole_agent.mcp_reverse_channel import (
    MCP_REVERSE_DONE_WHEN,
    MCP_REVERSE_GOAL,
    MCP_REVERSE_ID,
)
from blackhole_agent.mcp_http_transport import (
    MCP_HTTP_DONE_WHEN,
    MCP_HTTP_GOAL,
    MCP_HTTP_ID,
)
from blackhole_agent.mcp_http_event_stream import (
    MCP_HTTP_EVENT_DONE_WHEN,
    MCP_HTTP_EVENT_GOAL,
    MCP_HTTP_EVENT_ID,
)
from blackhole_agent.mcp_handshake_isolation import (
    MCP_HANDSHAKE_DONE_WHEN,
    MCP_HANDSHAKE_GOAL,
    MCP_HANDSHAKE_ID,
)
from blackhole_agent.publication_resilience import (
    PUBLICATION_RESILIENCE_DONE_WHEN,
    PUBLICATION_RESILIENCE_GOAL,
    PUBLICATION_RESILIENCE_ID,
)
from blackhole_agent.browser_actuation import (
    BROWSER_ACTUATION_DONE_WHEN,
    BROWSER_ACTUATION_GOAL,
    BROWSER_ACTUATION_ID,
)
from blackhole_agent.gmail_actuation import (
    GMAIL_ACTUATION_DONE_WHEN,
    GMAIL_ACTUATION_GOAL,
    GMAIL_ACTUATION_ID,
)
from blackhole_agent.godot_actuation import (
    GODOT_ACTUATION_DONE_WHEN,
    GODOT_ACTUATION_GOAL,
    GODOT_ACTUATION_ID,
)
from blackhole_agent.mcp_plugin_reconnect import (
    MCP_RECONNECT_DONE_WHEN,
    MCP_RECONNECT_GOAL,
    MCP_RECONNECT_ID,
)
from blackhole_agent.kernel_half_open_probe import (
    HALF_OPEN_PROBE_DONE_WHEN,
    HALF_OPEN_PROBE_GOAL,
    HALF_OPEN_PROBE_ID,
)
from blackhole_agent.mcp_sampling import (
    MCP_SAMPLING_DONE_WHEN,
    MCP_SAMPLING_GOAL,
    MCP_SAMPLING_ID,
)
from blackhole_agent.mcp_resources import (
    MCP_RESOURCES_DONE_WHEN,
    MCP_RESOURCES_GOAL,
    MCP_RESOURCES_ID,
)
from blackhole_agent.mcp_prompts import (
    MCP_PROMPTS_DONE_WHEN,
    MCP_PROMPTS_GOAL,
    MCP_PROMPTS_ID,
)
from blackhole_agent.mcp_completions import (
    MCP_COMPLETIONS_DONE_WHEN,
    MCP_COMPLETIONS_GOAL,
    MCP_COMPLETIONS_ID,
)
from blackhole_agent.mcp_logging import (
    MCP_LOGGING_DONE_WHEN,
    MCP_LOGGING_GOAL,
    MCP_LOGGING_ID,
)
from blackhole_agent.mcp_elicitation import (
    MCP_ELICITATION_DONE_WHEN,
    MCP_ELICITATION_GOAL,
    MCP_ELICITATION_ID,
)
from blackhole_agent.mcp_cancellation import (
    MCP_CANCELLATION_DONE_WHEN,
    MCP_CANCELLATION_GOAL,
    MCP_CANCELLATION_ID,
)
from blackhole_agent.mcp_resource_subscribe import (
    MCP_SUBSCRIBE_DONE_WHEN,
    MCP_SUBSCRIBE_GOAL,
    MCP_SUBSCRIBE_ID,
)
from blackhole_agent.mcp_roots_list_changed import (
    MCP_ROOTS_CHANGED_DONE_WHEN,
    MCP_ROOTS_CHANGED_GOAL,
    MCP_ROOTS_CHANGED_ID,
)
from blackhole_agent.browser_cdp_actuation import (
    BROWSER_CDP_DONE_WHEN,
    BROWSER_CDP_GOAL,
    BROWSER_CDP_ID,
)
from blackhole_agent.github_actuation import (
    GITHUB_ACTUATION_DONE_WHEN,
    GITHUB_ACTUATION_GOAL,
    GITHUB_ACTUATION_ID,
)
from blackhole_agent.sqlite_actuation import (
    SQLITE_ACTUATION_DONE_WHEN,
    SQLITE_ACTUATION_GOAL,
    SQLITE_ACTUATION_ID,
)
from blackhole_agent.webhook_actuation import (
    WEBHOOK_ACTUATION_DONE_WHEN,
    WEBHOOK_ACTUATION_GOAL,
    WEBHOOK_ACTUATION_ID,
)
from blackhole_agent.mcp_progress import (
    MCP_PROGRESS_DONE_WHEN,
    MCP_PROGRESS_GOAL,
    MCP_PROGRESS_ID,
)
from blackhole_agent.mcp_tools_list_changed import (
    MCP_TOOLS_CHANGED_DONE_WHEN,
    MCP_TOOLS_CHANGED_GOAL,
    MCP_TOOLS_CHANGED_ID,
)
from blackhole_agent.smtp_actuation import (
    SMTP_ACTUATION_DONE_WHEN,
    SMTP_ACTUATION_GOAL,
    SMTP_ACTUATION_ID,
)
from blackhole_agent.mcp_http_auth import (
    MCP_HTTP_AUTH_DONE_WHEN,
    MCP_HTTP_AUTH_GOAL,
    MCP_HTTP_AUTH_ID,
)
from blackhole_agent.imap_actuation import (
    IMAP_ACTUATION_DONE_WHEN,
    IMAP_ACTUATION_GOAL,
    IMAP_ACTUATION_ID,
)
from blackhole_agent.redis_actuation import (
    REDIS_ACTUATION_DONE_WHEN,
    REDIS_ACTUATION_GOAL,
    REDIS_ACTUATION_ID,
)
from blackhole_agent.mqtt_actuation import (
    MQTT_ACTUATION_DONE_WHEN,
    MQTT_ACTUATION_GOAL,
    MQTT_ACTUATION_ID,
)
from blackhole_agent.dns_actuation import (
    DNS_ACTUATION_DONE_WHEN,
    DNS_ACTUATION_GOAL,
    DNS_ACTUATION_ID,
)
from blackhole_agent.ldap_actuation import (
    LDAP_ACTUATION_DONE_WHEN,
    LDAP_ACTUATION_GOAL,
    LDAP_ACTUATION_ID,
)
from blackhole_agent.postgres_actuation import (
    POSTGRES_ACTUATION_DONE_WHEN,
    POSTGRES_ACTUATION_GOAL,
    POSTGRES_ACTUATION_ID,
)
from blackhole_agent.s3_actuation import (
    S3_ACTUATION_DONE_WHEN,
    S3_ACTUATION_GOAL,
    S3_ACTUATION_ID,
)
from blackhole_agent.watch_actuation import (
    WATCH_ACTUATION_DONE_WHEN,
    WATCH_ACTUATION_GOAL,
    WATCH_ACTUATION_ID,
)
from blackhole_agent.mcp_cursor_pagination import (
    MCP_CURSOR_DONE_WHEN,
    MCP_CURSOR_GOAL,
    MCP_CURSOR_ID,
)
from blackhole_agent.mcp_structured_output import (
    MCP_STRUCTURED_DONE_WHEN,
    MCP_STRUCTURED_GOAL,
    MCP_STRUCTURED_ID,
)
from blackhole_agent.websocket_actuation import (
    WEBSOCKET_ACTUATION_DONE_WHEN,
    WEBSOCKET_ACTUATION_GOAL,
    WEBSOCKET_ACTUATION_ID,
)
from blackhole_agent.ssh_actuation import (
    SSH_ACTUATION_DONE_WHEN,
    SSH_ACTUATION_GOAL,
    SSH_ACTUATION_ID,
)
from blackhole_agent.grpc_actuation import (
    GRPC_ACTUATION_DONE_WHEN,
    GRPC_ACTUATION_GOAL,
    GRPC_ACTUATION_ID,
)
from blackhole_agent.amqp_actuation import (
    AMQP_ACTUATION_DONE_WHEN,
    AMQP_ACTUATION_GOAL,
    AMQP_ACTUATION_ID,
)
from blackhole_agent.ftp_actuation import (
    FTP_ACTUATION_DONE_WHEN,
    FTP_ACTUATION_GOAL,
    FTP_ACTUATION_ID,
)
from blackhole_agent.tftp_actuation import (
    TFTP_ACTUATION_DONE_WHEN,
    TFTP_ACTUATION_GOAL,
    TFTP_ACTUATION_ID,
)
from blackhole_agent.snmp_actuation import (
    SNMP_ACTUATION_DONE_WHEN,
    SNMP_ACTUATION_GOAL,
    SNMP_ACTUATION_ID,
)
from blackhole_agent.syslog_actuation import (
    SYSLOG_ACTUATION_DONE_WHEN,
    SYSLOG_ACTUATION_GOAL,
    SYSLOG_ACTUATION_ID,
)
from blackhole_agent.ntp_actuation import (
    NTP_ACTUATION_DONE_WHEN,
    NTP_ACTUATION_GOAL,
    NTP_ACTUATION_ID,
)
from blackhole_agent.radius_actuation import (
    RADIUS_ACTUATION_DONE_WHEN,
    RADIUS_ACTUATION_GOAL,
    RADIUS_ACTUATION_ID,
)
from blackhole_agent.dhcp_actuation import (
    DHCP_ACTUATION_DONE_WHEN,
    DHCP_ACTUATION_GOAL,
    DHCP_ACTUATION_ID,
)
from blackhole_agent.ike_actuation import (
    IKE_ACTUATION_DONE_WHEN,
    IKE_ACTUATION_GOAL,
    IKE_ACTUATION_ID,
)
from blackhole_agent.sip_actuation import (
    SIP_ACTUATION_DONE_WHEN,
    SIP_ACTUATION_GOAL,
    SIP_ACTUATION_ID,
)
from blackhole_agent.stun_actuation import (
    STUN_ACTUATION_DONE_WHEN,
    STUN_ACTUATION_GOAL,
    STUN_ACTUATION_ID,
)
from blackhole_agent.turn_actuation import (
    TURN_ACTUATION_DONE_WHEN,
    TURN_ACTUATION_GOAL,
    TURN_ACTUATION_ID,
)
from blackhole_agent.ice_actuation import (
    ICE_ACTUATION_DONE_WHEN,
    ICE_ACTUATION_GOAL,
    ICE_ACTUATION_ID,
)
from blackhole_agent.dtls_actuation import (
    DTLS_ACTUATION_DONE_WHEN,
    DTLS_ACTUATION_GOAL,
    DTLS_ACTUATION_ID,
)
from blackhole_agent.srtp_actuation import (
    SRTP_ACTUATION_DONE_WHEN,
    SRTP_ACTUATION_GOAL,
    SRTP_ACTUATION_ID,
)
from blackhole_agent.sctp_actuation import (
    SCTP_ACTUATION_DONE_WHEN,
    SCTP_ACTUATION_GOAL,
    SCTP_ACTUATION_ID,
)
from blackhole_agent.datachannel_actuation import (
    DATACHANNEL_ACTUATION_DONE_WHEN,
    DATACHANNEL_ACTUATION_GOAL,
    DATACHANNEL_ACTUATION_ID,
)
from blackhole_agent.quic_actuation import (
    QUIC_ACTUATION_DONE_WHEN,
    QUIC_ACTUATION_GOAL,
    QUIC_ACTUATION_ID,
)
from blackhole_agent.http3_actuation import (
    HTTP3_ACTUATION_DONE_WHEN,
    HTTP3_ACTUATION_GOAL,
    HTTP3_ACTUATION_ID,
)
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_DONE_WHEN,
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)
from blackhole_agent.datagram_actuation import (
    DATAGRAM_ACTUATION_DONE_WHEN,
    DATAGRAM_ACTUATION_GOAL,
    DATAGRAM_ACTUATION_ID,
)
from blackhole_agent.masque_actuation import (
    MASQUE_ACTUATION_DONE_WHEN,
    MASQUE_ACTUATION_GOAL,
    MASQUE_ACTUATION_ID,
)
from blackhole_agent.connectip_actuation import (
    CONNECTIP_ACTUATION_DONE_WHEN,
    CONNECTIP_ACTUATION_GOAL,
    CONNECTIP_ACTUATION_ID,
)
from blackhole_agent.ohttp_actuation import (
    OHTTP_ACTUATION_DONE_WHEN,
    OHTTP_ACTUATION_GOAL,
    OHTTP_ACTUATION_ID,
)
from blackhole_agent.ohsvcb_actuation import (
    OHSVCB_ACTUATION_DONE_WHEN,
    OHSVCB_ACTUATION_GOAL,
    OHSVCB_ACTUATION_ID,
)
from blackhole_agent.httpsig_actuation import (
    HTTPSIG_ACTUATION_DONE_WHEN,
    HTTPSIG_ACTUATION_GOAL,
    HTTPSIG_ACTUATION_ID,
)
from blackhole_agent.digestfields_actuation import (
    DIGESTFIELDS_ACTUATION_DONE_WHEN,
    DIGESTFIELDS_ACTUATION_GOAL,
    DIGESTFIELDS_ACTUATION_ID,
)
from blackhole_agent.bhttp_actuation import (
    BHTTP_ACTUATION_DONE_WHEN,
    BHTTP_ACTUATION_GOAL,
    BHTTP_ACTUATION_ID,
)
from blackhole_agent.http11_actuation import (
    HTTP11_ACTUATION_DONE_WHEN,
    HTTP11_ACTUATION_GOAL,
    HTTP11_ACTUATION_ID,
)
from blackhole_agent.http2_actuation import (
    HTTP2_ACTUATION_DONE_WHEN,
    HTTP2_ACTUATION_GOAL,
    HTTP2_ACTUATION_ID,
)
from blackhole_agent.httpcache_actuation import (
    HTTPCACHE_ACTUATION_DONE_WHEN,
    HTTPCACHE_ACTUATION_GOAL,
    HTTPCACHE_ACTUATION_ID,
)
from blackhole_agent.httpsemantics_actuation import (
    HTTPSMANTICS_ACTUATION_DONE_WHEN,
    HTTPSMANTICS_ACTUATION_GOAL,
    HTTPSMANTICS_ACTUATION_ID,
)
from blackhole_agent.structuredfields_actuation import (
    STRUCTUREDFIELDS_ACTUATION_DONE_WHEN,
    STRUCTUREDFIELDS_ACTUATION_GOAL,
    STRUCTUREDFIELDS_ACTUATION_ID,
)
from blackhole_agent.clienthints_actuation import (
    CLIENTHINTS_ACTUATION_DONE_WHEN,
    CLIENTHINTS_ACTUATION_GOAL,
    CLIENTHINTS_ACTUATION_ID,
)
from blackhole_agent.earlyhints_actuation import (
    EARLYHINTS_ACTUATION_DONE_WHEN,
    EARLYHINTS_ACTUATION_GOAL,
    EARLYHINTS_ACTUATION_ID,
)
from blackhole_agent.encryptedcontent_actuation import (
    ENCRYPTEDCONTENT_ACTUATION_DONE_WHEN,
    ENCRYPTEDCONTENT_ACTUATION_GOAL,
    ENCRYPTEDCONTENT_ACTUATION_ID,
)
from blackhole_agent.altsvc_actuation import (
    ALTSVC_ACTUATION_DONE_WHEN,
    ALTSVC_ACTUATION_GOAL,
    ALTSVC_ACTUATION_ID,
)
from blackhole_agent.hsts_actuation import (
    HSTS_ACTUATION_DONE_WHEN,
    HSTS_ACTUATION_GOAL,
    HSTS_ACTUATION_ID,
)
from blackhole_agent.hpkp_actuation import (
    HPKP_ACTUATION_DONE_WHEN,
    HPKP_ACTUATION_GOAL,
    HPKP_ACTUATION_ID,
)
from blackhole_agent.expectct_actuation import (
    EXPECTCT_ACTUATION_DONE_WHEN,
    EXPECTCT_ACTUATION_GOAL,
    EXPECTCT_ACTUATION_ID,
)
from blackhole_agent.xfo_actuation import (
    XFO_ACTUATION_DONE_WHEN,
    XFO_ACTUATION_GOAL,
    XFO_ACTUATION_ID,
)
from blackhole_agent.weborigin_actuation import (
    WEBORIGIN_ACTUATION_DONE_WHEN,
    WEBORIGIN_ACTUATION_GOAL,
    WEBORIGIN_ACTUATION_ID,
)
from blackhole_agent.httpcookie_actuation import (
    HTTPCOOKIE_ACTUATION_DONE_WHEN,
    HTTPCOOKIE_ACTUATION_GOAL,
    HTTPCOOKIE_ACTUATION_ID,
)
from blackhole_agent.contentdisposition_actuation import (
    CONTENTDISPOSITION_ACTUATION_DONE_WHEN,
    CONTENTDISPOSITION_ACTUATION_GOAL,
    CONTENTDISPOSITION_ACTUATION_ID,
)
from blackhole_agent.weblinking_actuation import (
    WEBLINKING_ACTUATION_DONE_WHEN,
    WEBLINKING_ACTUATION_GOAL,
    WEBLINKING_ACTUATION_ID,
)
from blackhole_agent.extvalue_actuation import (
    EXTVALUE_ACTUATION_DONE_WHEN,
    EXTVALUE_ACTUATION_GOAL,
    EXTVALUE_ACTUATION_ID,
)
from blackhole_agent.stalecontent_actuation import (
    STALECONTENT_ACTUATION_DONE_WHEN,
    STALECONTENT_ACTUATION_GOAL,
    STALECONTENT_ACTUATION_ID,
)
from blackhole_agent.httppatch_actuation import (
    HTTPPATCH_ACTUATION_DONE_WHEN,
    HTTPPATCH_ACTUATION_GOAL,
    HTTPPATCH_ACTUATION_ID,
)
from blackhole_agent.wellknown_actuation import (
    WELLKNOWN_ACTUATION_DONE_WHEN,
    WELLKNOWN_ACTUATION_GOAL,
    WELLKNOWN_ACTUATION_ID,
)
from blackhole_agent.webdav_actuation import (
    WEBDAV_ACTUATION_DONE_WHEN,
    WEBDAV_ACTUATION_GOAL,
    WEBDAV_ACTUATION_ID,
)
from blackhole_agent.spnego_actuation import (
    SPNEGO_ACTUATION_DONE_WHEN,
    SPNEGO_ACTUATION_GOAL,
    SPNEGO_ACTUATION_ID,
)
from blackhole_agent.httptls_actuation import (
    HTTPTLS_ACTUATION_DONE_WHEN,
    HTTPTLS_ACTUATION_GOAL,
    HTTPTLS_ACTUATION_ID,
)
from blackhole_agent.httpauth_actuation import (
    HTTPAUTH_ACTUATION_DONE_WHEN,
    HTTPAUTH_ACTUATION_GOAL,
    HTTPAUTH_ACTUATION_ID,
)
from blackhole_agent.tcn_actuation import (
    TCN_ACTUATION_DONE_WHEN,
    TCN_ACTUATION_GOAL,
    TCN_ACTUATION_ID,
)
from blackhole_agent.hitmeter_actuation import (
    HITMETER_ACTUATION_DONE_WHEN,
    HITMETER_ACTUATION_GOAL,
    HITMETER_ACTUATION_ID,
)
from blackhole_agent.icp_actuation import (
    ICP_ACTUATION_DONE_WHEN,
    ICP_ACTUATION_GOAL,
    ICP_ACTUATION_ID,
)
from blackhole_agent.httpver_actuation import (
    HTTPVER_ACTUATION_DONE_WHEN,
    HTTPVER_ACTUATION_GOAL,
    HTTPVER_ACTUATION_ID,
)
from blackhole_agent.httpstate_actuation import (
    HTTPSTATE_ACTUATION_DONE_WHEN,
    HTTPSTATE_ACTUATION_GOAL,
    HTTPSTATE_ACTUATION_ID,
)
from blackhole_agent.digestauth_actuation import (
    DIGESTAUTH_ACTUATION_DONE_WHEN,
    DIGESTAUTH_ACTUATION_GOAL,
    DIGESTAUTH_ACTUATION_ID,
)
from blackhole_agent.http10_actuation import (
    HTTP10_ACTUATION_DONE_WHEN,
    HTTP10_ACTUATION_GOAL,
    HTTP10_ACTUATION_ID,
)
from blackhole_agent.url_actuation import (
    URL_ACTUATION_DONE_WHEN,
    URL_ACTUATION_GOAL,
    URL_ACTUATION_ID,
)
from blackhole_agent.uri_actuation import (
    URI_ACTUATION_DONE_WHEN,
    URI_ACTUATION_GOAL,
    URI_ACTUATION_ID,
)
from blackhole_agent.mime_actuation import (
    MIME_ACTUATION_DONE_WHEN,
    MIME_ACTUATION_GOAL,
    MIME_ACTUATION_ID,
)
from blackhole_agent.gopher_actuation import (
    GOPHER_ACTUATION_DONE_WHEN,
    GOPHER_ACTUATION_GOAL,
    GOPHER_ACTUATION_ID,
)
from blackhole_agent.finger_actuation import (
    FINGER_ACTUATION_DONE_WHEN,
    FINGER_ACTUATION_GOAL,
    FINGER_ACTUATION_ID,
)
from blackhole_agent.lpd_actuation import (
    LPD_ACTUATION_DONE_WHEN,
    LPD_ACTUATION_GOAL,
    LPD_ACTUATION_ID,
)
from blackhole_agent.nntp_actuation import (
    NNTP_ACTUATION_DONE_WHEN,
    NNTP_ACTUATION_GOAL,
    NNTP_ACTUATION_ID,
)
from blackhole_agent.telnet_actuation import (
    TELNET_ACTUATION_DONE_WHEN,
    TELNET_ACTUATION_GOAL,
    TELNET_ACTUATION_ID,
)
from blackhole_agent.tcp_actuation import (
    TCP_ACTUATION_DONE_WHEN,
    TCP_ACTUATION_GOAL,
    TCP_ACTUATION_ID,
)
from blackhole_agent.udp_actuation import (
    UDP_ACTUATION_DONE_WHEN,
    UDP_ACTUATION_GOAL,
    UDP_ACTUATION_ID,
)
from blackhole_agent.icmp_actuation import (
    ICMP_ACTUATION_DONE_WHEN,
    ICMP_ACTUATION_GOAL,
    ICMP_ACTUATION_ID,
)
from blackhole_agent.ip_actuation import (
    IP_ACTUATION_DONE_WHEN,
    IP_ACTUATION_GOAL,
    IP_ACTUATION_ID,
)
from blackhole_agent.arp_actuation import (
    ARP_ACTUATION_DONE_WHEN,
    ARP_ACTUATION_GOAL,
    ARP_ACTUATION_ID,
)
from blackhole_agent.rarp_actuation import (
    RARP_ACTUATION_DONE_WHEN,
    RARP_ACTUATION_GOAL,
    RARP_ACTUATION_ID,
)
from blackhole_agent.igmp_actuation import (
    IGMP_ACTUATION_DONE_WHEN,
    IGMP_ACTUATION_GOAL,
    IGMP_ACTUATION_ID,
)
from blackhole_agent.mld_actuation import (
    MLD_ACTUATION_DONE_WHEN,
    MLD_ACTUATION_GOAL,
    MLD_ACTUATION_ID,
)
from blackhole_agent.ndp_actuation import (
    NDP_ACTUATION_DONE_WHEN,
    NDP_ACTUATION_GOAL,
    NDP_ACTUATION_ID,
)
from blackhole_agent.slaac_actuation import (
    SLAAC_ACTUATION_DONE_WHEN,
    SLAAC_ACTUATION_GOAL,
    SLAAC_ACTUATION_ID,
)
from blackhole_agent.tempaddr_actuation import (
    TEMPADDR_ACTUATION_DONE_WHEN,
    TEMPADDR_ACTUATION_GOAL,
    TEMPADDR_ACTUATION_ID,
)
from blackhole_agent.opaqueiid_actuation import (
    OPAQUEIID_ACTUATION_DONE_WHEN,
    OPAQUEIID_ACTUATION_GOAL,
    OPAQUEIID_ACTUATION_ID,
)
from blackhole_agent.cga_actuation import (
    CGA_ACTUATION_DONE_WHEN,
    CGA_ACTUATION_GOAL,
    CGA_ACTUATION_ID,
)
from blackhole_agent.send_actuation import (
    SEND_ACTUATION_DONE_WHEN,
    SEND_ACTUATION_GOAL,
    SEND_ACTUATION_ID,
)
from blackhole_agent.ula_actuation import (
    ULA_ACTUATION_DONE_WHEN,
    ULA_ACTUATION_GOAL,
    ULA_ACTUATION_ID,
)
from blackhole_agent.ipv6addr_actuation import (
    IPV6ADDR_ACTUATION_DONE_WHEN,
    IPV6ADDR_ACTUATION_GOAL,
    IPV6ADDR_ACTUATION_ID,
)
from blackhole_agent.ipv6scope_actuation import (
    IPV6SCOPE_ACTUATION_DONE_WHEN,
    IPV6SCOPE_ACTUATION_GOAL,
    IPV6SCOPE_ACTUATION_ID,
)
from blackhole_agent.addrselect_actuation import (
    ADDRSELECT_ACTUATION_DONE_WHEN,
    ADDRSELECT_ACTUATION_GOAL,
    ADDRSELECT_ACTUATION_ID,
)
from blackhole_agent.addrpolicy_actuation import (
    ADDRPOLICY_ACTUATION_DONE_WHEN,
    ADDRPOLICY_ACTUATION_GOAL,
    ADDRPOLICY_ACTUATION_ID,
)
from blackhole_agent.firsthop_actuation import (
    FIRSTHOP_ACTUATION_DONE_WHEN,
    FIRSTHOP_ACTUATION_GOAL,
    FIRSTHOP_ACTUATION_ID,
)
from blackhole_agent.rdnss_actuation import (
    RDNSS_ACTUATION_DONE_WHEN,
    RDNSS_ACTUATION_GOAL,
    RDNSS_ACTUATION_ID,
)
from blackhole_agent.pref64_actuation import (
    PREF64_ACTUATION_DONE_WHEN,
    PREF64_ACTUATION_GOAL,
    PREF64_ACTUATION_ID,
)
from blackhole_agent.nat64_actuation import (
    NAT64_ACTUATION_DONE_WHEN,
    NAT64_ACTUATION_GOAL,
    NAT64_ACTUATION_ID,
)
from blackhole_agent.dns64_actuation import (
    DNS64_ACTUATION_DONE_WHEN,
    DNS64_ACTUATION_GOAL,
    DNS64_ACTUATION_ID,
)
from blackhole_agent.xlat_actuation import (
    XLAT_ACTUATION_DONE_WHEN,
    XLAT_ACTUATION_GOAL,
    XLAT_ACTUATION_ID,
)
from blackhole_agent.disc_actuation import (
    DISC_ACTUATION_DONE_WHEN,
    DISC_ACTUATION_GOAL,
    DISC_ACTUATION_ID,
)
from blackhole_agent.dslite_actuation import (
    DSLITE_ACTUATION_DONE_WHEN,
    DSLITE_ACTUATION_GOAL,
    DSLITE_ACTUATION_ID,
)
from blackhole_agent.lw4o6_actuation import (
    LW4O6_ACTUATION_DONE_WHEN,
    LW4O6_ACTUATION_GOAL,
    LW4O6_ACTUATION_ID,
)
from blackhole_agent.mape_actuation import (
    MAPE_ACTUATION_DONE_WHEN,
    MAPE_ACTUATION_GOAL,
    MAPE_ACTUATION_ID,
)
from blackhole_agent.mapt_actuation import (
    MAPT_ACTUATION_DONE_WHEN,
    MAPT_ACTUATION_GOAL,
    MAPT_ACTUATION_ID,
)
from blackhole_agent.s46_actuation import (
    S46_ACTUATION_DONE_WHEN,
    S46_ACTUATION_GOAL,
    S46_ACTUATION_ID,
)
from blackhole_agent.ucpe_actuation import (
    UCPE_ACTUATION_DONE_WHEN,
    UCPE_ACTUATION_GOAL,
    UCPE_ACTUATION_ID,
)
from blackhole_agent.m46_actuation import (
    M46_ACTUATION_DONE_WHEN,
    M46_ACTUATION_GOAL,
    M46_ACTUATION_ID,
)
from blackhole_agent.prefix64_actuation import (
    PREFIX64_ACTUATION_DONE_WHEN,
    PREFIX64_ACTUATION_GOAL,
    PREFIX64_ACTUATION_ID,
)
from blackhole_agent.siit_actuation import (
    SIIT_ACTUATION_DONE_WHEN,
    SIIT_ACTUATION_GOAL,
    SIIT_ACTUATION_ID,
)
from blackhole_agent.eam_actuation import (
    EAM_ACTUATION_DONE_WHEN,
    EAM_ACTUATION_GOAL,
    EAM_ACTUATION_ID,
)
from blackhole_agent.siitdc_actuation import (
    SIITDC_ACTUATION_DONE_WHEN,
    SIITDC_ACTUATION_GOAL,
    SIITDC_ACTUATION_ID,
)
from blackhole_agent.siitdtm_actuation import (
    SIITDTM_ACTUATION_DONE_WHEN,
    SIITDTM_ACTUATION_GOAL,
    SIITDTM_ACTUATION_ID,
)
from blackhole_agent.v4embed_actuation import (
    V4EMBED_ACTUATION_DONE_WHEN,
    V4EMBED_ACTUATION_GOAL,
    V4EMBED_ACTUATION_ID,
)
from blackhole_agent.luprefix_actuation import (
    LUPREFIX_ACTUATION_DONE_WHEN,
    LUPREFIX_ACTUATION_GOAL,
    LUPREFIX_ACTUATION_ID,
)
from blackhole_agent.sixrd_actuation import (
    SIXRD_ACTUATION_DONE_WHEN,
    SIXRD_ACTUATION_GOAL,
    SIXRD_ACTUATION_ID,
)
from blackhole_agent.sixto4_actuation import (
    SIXTO4_ACTUATION_DONE_WHEN,
    SIXTO4_ACTUATION_GOAL,
    SIXTO4_ACTUATION_ID,
)
from blackhole_agent.teredo_actuation import (
    TEREDO_ACTUATION_DONE_WHEN,
    TEREDO_ACTUATION_GOAL,
    TEREDO_ACTUATION_ID,
)
from blackhole_agent.isatap_actuation import (
    ISATAP_ACTUATION_DONE_WHEN,
    ISATAP_ACTUATION_GOAL,
    ISATAP_ACTUATION_ID,
)
from blackhole_agent.sixover4_actuation import (
    SIXOVER4_ACTUATION_DONE_WHEN,
    SIXOVER4_ACTUATION_GOAL,
    SIXOVER4_ACTUATION_ID,
)
from blackhole_agent.sixin4_actuation import (
    SIXIN4_ACTUATION_DONE_WHEN,
    SIXIN4_ACTUATION_GOAL,
    SIXIN4_ACTUATION_ID,
)
from blackhole_agent.tsp_actuation import (
    TSP_ACTUATION_DONE_WHEN,
    TSP_ACTUATION_GOAL,
    TSP_ACTUATION_ID,
)
from blackhole_agent.l2tp_actuation import (
    L2TP_ACTUATION_DONE_WHEN,
    L2TP_ACTUATION_GOAL,
    L2TP_ACTUATION_ID,
)
from blackhole_agent.mesh_actuation import (
    MESH_ACTUATION_DONE_WHEN,
    MESH_ACTUATION_GOAL,
    MESH_ACTUATION_ID,
)
from blackhole_agent.encap_actuation import (
    ENCAP_ACTUATION_DONE_WHEN,
    ENCAP_ACTUATION_GOAL,
    ENCAP_ACTUATION_ID,
)
from blackhole_agent.mpbgp_actuation import (
    MPBGP_ACTUATION_DONE_WHEN,
    MPBGP_ACTUATION_GOAL,
    MPBGP_ACTUATION_ID,
)
from blackhole_agent.bgp4_actuation import (
    BGP4_ACTUATION_DONE_WHEN,
    BGP4_ACTUATION_GOAL,
    BGP4_ACTUATION_ID,
)
from blackhole_agent.rtrefresh_actuation import (
    RTREFRESH_ACTUATION_DONE_WHEN,
    RTREFRESH_ACTUATION_GOAL,
    RTREFRESH_ACTUATION_ID,
)
from blackhole_agent.bgpcomm_actuation import (
    BGPCOMM_ACTUATION_DONE_WHEN,
    BGPCOMM_ACTUATION_GOAL,
    BGPCOMM_ACTUATION_ID,
)
from blackhole_agent.extcomm_actuation import (
    EXTCOMM_ACTUATION_DONE_WHEN,
    EXTCOMM_ACTUATION_GOAL,
    EXTCOMM_ACTUATION_ID,
)
from blackhole_agent.largecomm_actuation import (
    LARGECOMM_ACTUATION_DONE_WHEN,
    LARGECOMM_ACTUATION_GOAL,
    LARGECOMM_ACTUATION_ID,
)
from blackhole_agent.bgpsec_actuation import (
    BGPSEC_ACTUATION_DONE_WHEN,
    BGPSEC_ACTUATION_GOAL,
    BGPSEC_ACTUATION_ID,
)
from blackhole_agent.rtr_actuation import (
    RTR_ACTUATION_DONE_WHEN,
    RTR_ACTUATION_GOAL,
    RTR_ACTUATION_ID,
)
from blackhole_agent.ebgp_actuation import (
    EBGP_ACTUATION_DONE_WHEN,
    EBGP_ACTUATION_GOAL,
    EBGP_ACTUATION_ID,
)
from blackhole_agent.evpn_actuation import (
    EVPN_ACTUATION_DONE_WHEN,
    EVPN_ACTUATION_GOAL,
    EVPN_ACTUATION_ID,
)
from blackhole_agent.etree_actuation import (
    ETREE_ACTUATION_DONE_WHEN,
    ETREE_ACTUATION_GOAL,
    ETREE_ACTUATION_ID,
)
from blackhole_agent.nvo_actuation import (
    NVO_ACTUATION_DONE_WHEN,
    NVO_ACTUATION_GOAL,
    NVO_ACTUATION_ID,
)
from blackhole_agent.dfe_actuation import (
    DFE_ACTUATION_DONE_WHEN,
    DFE_ACTUATION_GOAL,
    DFE_ACTUATION_ID,
)
from blackhole_agent.irb_actuation import (
    IRB_ACTUATION_DONE_WHEN,
    IRB_ACTUATION_GOAL,
    IRB_ACTUATION_ID,
)
from blackhole_agent.ippfx_actuation import (
    IPPFX_ACTUATION_DONE_WHEN,
    IPPFX_ACTUATION_GOAL,
    IPPFX_ACTUATION_ID,
)
from blackhole_agent.proxynd_actuation import (
    PROXYND_ACTUATION_DONE_WHEN,
    PROXYND_ACTUATION_GOAL,
    PROXYND_ACTUATION_ID,
)
from blackhole_agent.imlproxy_actuation import (
    IMLPROXY_ACTUATION_DONE_WHEN,
    IMLPROXY_ACTUATION_GOAL,
    IMLPROXY_ACTUATION_ID,
)
from blackhole_agent.evpnbum_actuation import (
    EVPNBUM_ACTUATION_DONE_WHEN,
    EVPNBUM_ACTUATION_GOAL,
    EVPNBUM_ACTUATION_ID,
)
from blackhole_agent.fxc_actuation import (
    FXC_ACTUATION_DONE_WHEN,
    FXC_ACTUATION_GOAL,
    FXC_ACTUATION_ID,
)
from blackhole_agent.dfrec_actuation import (
    DFREC_ACTUATION_DONE_WHEN,
    DFREC_ACTUATION_GOAL,
    DFREC_ACTUATION_ID,
)
from blackhole_agent.msred_actuation import (
    MSRED_ACTUATION_DONE_WHEN,
    MSRED_ACTUATION_GOAL,
    MSRED_ACTUATION_ID,
)
from blackhole_agent.p2mpir_actuation import (
    P2MPIR_ACTUATION_DONE_WHEN,
    P2MPIR_ACTUATION_GOAL,
    P2MPIR_ACTUATION_ID,
)
from blackhole_agent.oir_actuation import (
    OIR_ACTUATION_DONE_WHEN,
    OIR_ACTUATION_GOAL,
    OIR_ACTUATION_ID,
)
from blackhole_agent.iesi_actuation import (
    IESI_ACTUATION_DONE_WHEN,
    IESI_ACTUATION_GOAL,
    IESI_ACTUATION_ID,
)
from blackhole_agent.pbb_actuation import (
    PBB_ACTUATION_DONE_WHEN,
    PBB_ACTUATION_GOAL,
    PBB_ACTUATION_ID,
)
from blackhole_agent.macip_actuation import (
    MACIP_ACTUATION_DONE_WHEN,
    MACIP_ACTUATION_GOAL,
    MACIP_ACTUATION_ID,
)
from blackhole_agent.evpnreq_actuation import (
    EVPNREQ_ACTUATION_DONE_WHEN,
    EVPNREQ_ACTUATION_GOAL,
    EVPNREQ_ACTUATION_ID,
)
from blackhole_agent.vpls_actuation import (
    VPLS_ACTUATION_DONE_WHEN,
    VPLS_ACTUATION_GOAL,
    VPLS_ACTUATION_ID,
)
from blackhole_agent.ldpsig_actuation import (
    LDPSIG_ACTUATION_DONE_WHEN,
    LDPSIG_ACTUATION_GOAL,
    LDPSIG_ACTUATION_ID,
)
from blackhole_agent.pwldp_actuation import (
    PWLDP_ACTUATION_DONE_WHEN,
    PWLDP_ACTUATION_GOAL,
    PWLDP_ACTUATION_ID,
)
from blackhole_agent.pwe3_actuation import (
    PWE3_ACTUATION_DONE_WHEN,
    PWE3_ACTUATION_GOAL,
    PWE3_ACTUATION_ID,
)
from blackhole_agent.pwreq_actuation import (
    PWREQ_ACTUATION_DONE_WHEN,
    PWREQ_ACTUATION_GOAL,
    PWREQ_ACTUATION_ID,
)
from blackhole_agent.mplsarch_actuation import (
    MPLSARCH_ACTUATION_DONE_WHEN,
    MPLSARCH_ACTUATION_GOAL,
    MPLSARCH_ACTUATION_ID,
)
from blackhole_agent.mplslse_actuation import (
    MPLSLSE_ACTUATION_DONE_WHEN,
    MPLSLSE_ACTUATION_GOAL,
    MPLSLSE_ACTUATION_ID,
)
from blackhole_agent.rsvpte_actuation import (
    RSVPTE_ACTUATION_DONE_WHEN,
    RSVPTE_ACTUATION_GOAL,
    RSVPTE_ACTUATION_ID,
)
from blackhole_agent.gmpls_actuation import (
    GMPLS_ACTUATION_DONE_WHEN,
    GMPLS_ACTUATION_GOAL,
    GMPLS_ACTUATION_ID,
)
from blackhole_agent.lmp_actuation import (
    LMP_ACTUATION_DONE_WHEN,
    LMP_ACTUATION_GOAL,
    LMP_ACTUATION_ID,
)
from blackhole_agent.lsphier_actuation import (
    LSPHIER_ACTUATION_DONE_WHEN,
    LSPHIER_ACTUATION_GOAL,
    LSPHIER_ACTUATION_ID,
)
from blackhole_agent.guni_actuation import (
    GUNI_ACTUATION_DONE_WHEN,
    GUNI_ACTUATION_GOAL,
    GUNI_ACTUATION_ID,
)
from blackhole_agent.lwdm_actuation import (
    LWDM_ACTUATION_DONE_WHEN,
    LWDM_ACTUATION_GOAL,
    LWDM_ACTUATION_ID,
)
from blackhole_agent.otn_actuation import (
    OTN_ACTUATION_DONE_WHEN,
    OTN_ACTUATION_GOAL,
    OTN_ACTUATION_ID,
)
from blackhole_agent.ason_actuation import (
    ASON_ACTUATION_DONE_WHEN,
    ASON_ACTUATION_GOAL,
    ASON_ACTUATION_ID,
)
from blackhole_agent.grec_actuation import (
    GREC_ACTUATION_DONE_WHEN,
    GREC_ACTUATION_GOAL,
    GREC_ACTUATION_ID,
)
from blackhole_agent.e2erec_actuation import (
    E2EREC_ACTUATION_DONE_WHEN,
    E2EREC_ACTUATION_GOAL,
    E2EREC_ACTUATION_ID,
)
from blackhole_agent.segrec_actuation import (
    SEGREC_ACTUATION_DONE_WHEN,
    SEGREC_ACTUATION_GOAL,
    SEGREC_ACTUATION_ID,
)
from blackhole_agent.exroute_actuation import (
    EXROUTE_ACTUATION_DONE_WHEN,
    EXROUTE_ACTUATION_GOAL,
    EXROUTE_ACTUATION_ID,
)
from blackhole_agent.p2mpte_actuation import (
    P2MPTE_ACTUATION_DONE_WHEN,
    P2MPTE_ACTUATION_GOAL,
    P2MPTE_ACTUATION_ID,
)
from blackhole_agent.crankback_actuation import (
    CRANKBACK_ACTUATION_DONE_WHEN,
    CRANKBACK_ACTUATION_GOAL,
    CRANKBACK_ACTUATION_ID,
)
from blackhole_agent.lspstitch_actuation import (
    LSPSTITCH_ACTUATION_DONE_WHEN,
    LSPSTITCH_ACTUATION_GOAL,
    LSPSTITCH_ACTUATION_ID,
)
from blackhole_agent.interas_actuation import (
    INTERAS_ACTUATION_DONE_WHEN,
    INTERAS_ACTUATION_GOAL,
    INTERAS_ACTUATION_ID,
)
from blackhole_agent.perdom_actuation import (
    PERDOM_ACTUATION_DONE_WHEN,
    PERDOM_ACTUATION_GOAL,
    PERDOM_ACTUATION_ID,
)
from blackhole_agent.pcep_actuation import (
    PCEP_ACTUATION_DONE_WHEN,
    PCEP_ACTUATION_GOAL,
    PCEP_ACTUATION_ID,
)
from blackhole_agent.brpc_actuation import (
    BRPC_ACTUATION_DONE_WHEN,
    BRPC_ACTUATION_GOAL,
    BRPC_ACTUATION_ID,
)
from blackhole_agent.dsct_actuation import (
    DSCT_ACTUATION_DONE_WHEN,
    DSCT_ACTUATION_GOAL,
    DSCT_ACTUATION_ID,
)
from blackhole_agent.pathkey_actuation import (
    PATHKEY_ACTUATION_DONE_WHEN,
    PATHKEY_ACTUATION_GOAL,
    PATHKEY_ACTUATION_ID,
)
from blackhole_agent.pcexcl_actuation import (
    PCEXCL_ACTUATION_DONE_WHEN,
    PCEXCL_ACTUATION_GOAL,
    PCEXCL_ACTUATION_ID,
)
from blackhole_agent.objfun_actuation import (
    OBJFUN_ACTUATION_DONE_WHEN,
    OBJFUN_ACTUATION_GOAL,
    OBJFUN_ACTUATION_ID,
)
from blackhole_agent.gco_actuation import (
    GCO_ACTUATION_DONE_WHEN,
    GCO_ACTUATION_GOAL,
    GCO_ACTUATION_ID,
)
from blackhole_agent.ilpce_actuation import (
    ILPCE_ACTUATION_DONE_WHEN,
    ILPCE_ACTUATION_GOAL,
    ILPCE_ACTUATION_ID,
)
from blackhole_agent.pcemon_actuation import (
    PCEMON_ACTUATION_DONE_WHEN,
    PCEMON_ACTUATION_GOAL,
    PCEMON_ACTUATION_ID,
)
from blackhole_agent.pcepmp_actuation import (
    PCEPMP_ACTUATION_DONE_WHEN,
    PCEPMP_ACTUATION_GOAL,
    PCEPMP_ACTUATION_ID,
)
from blackhole_agent.wson_actuation import (
    WSON_ACTUATION_DONE_WHEN,
    WSON_ACTUATION_GOAL,
    WSON_ACTUATION_ID,
)
from blackhole_agent.lsc_actuation import (
    LSC_ACTUATION_DONE_WHEN,
    LSC_ACTUATION_GOAL,
    LSC_ACTUATION_ID,
)
from blackhole_agent.asbw_actuation import (
    ASBW_ACTUATION_DONE_WHEN,
    ASBW_ACTUATION_GOAL,
    ASBW_ACTUATION_ID,
)
from blackhole_agent.smp_actuation import (
    SMP_ACTUATION_DONE_WHEN,
    SMP_ACTUATION_GOAL,
    SMP_ACTUATION_ID,
)
from blackhole_agent.fmoam_actuation import (
    FMOAM_ACTUATION_DONE_WHEN,
    FMOAM_ACTUATION_GOAL,
    FMOAM_ACTUATION_ID,
)
from blackhole_agent.pcv_actuation import (
    PCV_ACTUATION_DONE_WHEN,
    PCV_ACTUATION_GOAL,
    PCV_ACTUATION_ID,
)
from blackhole_agent.lilb_actuation import (
    LILB_ACTUATION_DONE_WHEN,
    LILB_ACTUATION_GOAL,
    LILB_ACTUATION_ID,
)
from blackhole_agent.pwst_actuation import (
    PWST_ACTUATION_DONE_WHEN,
    PWST_ACTUATION_GOAL,
    PWST_ACTUATION_ID,
)
from blackhole_agent.mldp_actuation import (
    MLDP_ACTUATION_DONE_WHEN,
    MLDP_ACTUATION_GOAL,
    MLDP_ACTUATION_ID,
)
from blackhole_agent.mvpn_actuation import (
    MVPN_ACTUATION_DONE_WHEN,
    MVPN_ACTUATION_GOAL,
    MVPN_ACTUATION_ID,
)
from blackhole_agent.pmsi_actuation import (
    PMSI_ACTUATION_DONE_WHEN,
    PMSI_ACTUATION_GOAL,
    PMSI_ACTUATION_ID,
)
from blackhole_agent.wildad_actuation import (
    WILDAD_ACTUATION_DONE_WHEN,
    WILDAD_ACTUATION_GOAL,
    WILDAD_ACTUATION_ID,
)
from blackhole_agent.twfec_actuation import (
    TWFEC_ACTUATION_DONE_WHEN,
    TWFEC_ACTUATION_GOAL,
    TWFEC_ACTUATION_ID,
)
from blackhole_agent.gtsm_actuation import (
    GTSM_ACTUATION_DONE_WHEN,
    GTSM_ACTUATION_GOAL,
    GTSM_ACTUATION_ID,
)
from blackhole_agent.elbl_actuation import (
    ELBL_ACTUATION_DONE_WHEN,
    ELBL_ACTUATION_GOAL,
    ELBL_ACTUATION_ID,
)
from blackhole_agent.local_capability_kernel import _write_fixture_ledger
from blackhole_agent.local_mission_sovereignty import (
    LocalCampaign,
    load_campaign,
    save_campaign,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    load_recent_mission_history,
    semantic_signature,
)

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
GENESIS_DIVERSIFY_ID = "capability.kernel-genesis-diversify"

GENESIS_DIVERSIFY_DONE_WHEN = (
    f"capability_exists:{GENESIS_DIVERSIFY_ID};"
    f"capability_proved:{GENESIS_DIVERSIFY_ID};"
    "no_skill_route"
)
GENESIS_DIVERSIFY_GOAL = (
    "When experience fuel is empty and every remaining catalog successor fails "
    "controller selection gates, repair the empty successor: mint a diversity-ranked "
    "mission on a different capability family in-process so a live consumed campaign "
    "cannot leave genesis unbound."
)

COMPOUNDING_THROUGH_FABRIC = (
    KERNEL_GENESIS_BIND_ID,
    CONSUMED_GROWTH_ID,
    COMPOUND_LOOP_ID,
    PRIMITIVE_COMPOSE_ID,
    COMPOSED_PROGRAM_ID,
    PROGRAM_STACK_ID,
    PROGRAM_TOWER_ID,
    PROGRAM_LATTICE_ID,
    PROGRAM_FABRIC_ID,
)

DIVERSITY_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": GENESIS_DIVERSIFY_ID,
        "goal": GENESIS_DIVERSIFY_GOAL,
        "done_when": GENESIS_DIVERSIFY_DONE_WHEN,
        "source": "genesis_bind_diversity",
    },
    {
        "id": MISSION_MEMORY_ID,
        "goal": MISSION_MEMORY_GOAL,
        "done_when": MISSION_MEMORY_DONE_WHEN,
        "source": "genesis_bind_memory",
    },
    {
        "id": HALF_OPEN_PERSIST_ID,
        "goal": HALF_OPEN_PERSIST_GOAL,
        "done_when": HALF_OPEN_PERSIST_DONE_WHEN,
        "source": "genesis_bind_half_open",
    },
    {
        "id": MCP_HANDSHAKE_ID,
        "goal": MCP_HANDSHAKE_GOAL,
        "done_when": MCP_HANDSHAKE_DONE_WHEN,
        "source": "genesis_bind_handshake",
    },
    {
        "id": MCP_CALL_ID,
        "goal": MCP_CALL_GOAL,
        "done_when": MCP_CALL_DONE_WHEN,
        "source": "genesis_bind_call_isolation",
    },
    {
        "id": MCP_REVERSE_ID,
        "goal": MCP_REVERSE_GOAL,
        "done_when": MCP_REVERSE_DONE_WHEN,
        "source": "genesis_bind_reverse_channel",
    },
    {
        "id": MCP_HTTP_ID,
        "goal": MCP_HTTP_GOAL,
        "done_when": MCP_HTTP_DONE_WHEN,
        "source": "genesis_bind_http_transport",
    },
    {
        "id": MCP_HTTP_EVENT_ID,
        "goal": MCP_HTTP_EVENT_GOAL,
        "done_when": MCP_HTTP_EVENT_DONE_WHEN,
        "source": "genesis_bind_http_event_stream",
    },
    {
        "id": PUBLICATION_RESILIENCE_ID,
        "goal": PUBLICATION_RESILIENCE_GOAL,
        "done_when": PUBLICATION_RESILIENCE_DONE_WHEN,
        "source": "genesis_bind_publication",
    },
    {
        "id": BROWSER_ACTUATION_ID,
        "goal": BROWSER_ACTUATION_GOAL,
        "done_when": BROWSER_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_browser",
    },
    {
        "id": GMAIL_ACTUATION_ID,
        "goal": GMAIL_ACTUATION_GOAL,
        "done_when": GMAIL_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_gmail",
    },
    {
        "id": GODOT_ACTUATION_ID,
        "goal": GODOT_ACTUATION_GOAL,
        "done_when": GODOT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_godot",
    },
    {
        "id": MCP_RECONNECT_ID,
        "goal": MCP_RECONNECT_GOAL,
        "done_when": MCP_RECONNECT_DONE_WHEN,
        "source": "genesis_bind_reconnect",
    },
    {
        "id": HALF_OPEN_PROBE_ID,
        "goal": HALF_OPEN_PROBE_GOAL,
        "done_when": HALF_OPEN_PROBE_DONE_WHEN,
        "source": "genesis_bind_half_open_probe",
    },
    {
        "id": MCP_SAMPLING_ID,
        "goal": MCP_SAMPLING_GOAL,
        "done_when": MCP_SAMPLING_DONE_WHEN,
        "source": "genesis_bind_sampling",
    },
    {
        "id": MCP_RESOURCES_ID,
        "goal": MCP_RESOURCES_GOAL,
        "done_when": MCP_RESOURCES_DONE_WHEN,
        "source": "genesis_bind_resources",
    },
    {
        "id": MCP_PROMPTS_ID,
        "goal": MCP_PROMPTS_GOAL,
        "done_when": MCP_PROMPTS_DONE_WHEN,
        "source": "genesis_bind_prompts",
    },
    {
        "id": MCP_COMPLETIONS_ID,
        "goal": MCP_COMPLETIONS_GOAL,
        "done_when": MCP_COMPLETIONS_DONE_WHEN,
        "source": "genesis_bind_completions",
    },
    {
        "id": MCP_LOGGING_ID,
        "goal": MCP_LOGGING_GOAL,
        "done_when": MCP_LOGGING_DONE_WHEN,
        "source": "genesis_bind_logging",
    },
    {
        "id": MCP_ELICITATION_ID,
        "goal": MCP_ELICITATION_GOAL,
        "done_when": MCP_ELICITATION_DONE_WHEN,
        "source": "genesis_bind_elicitation",
    },
    {
        "id": MCP_CANCELLATION_ID,
        "goal": MCP_CANCELLATION_GOAL,
        "done_when": MCP_CANCELLATION_DONE_WHEN,
        "source": "genesis_bind_cancellation",
    },
    {
        "id": MCP_SUBSCRIBE_ID,
        "goal": MCP_SUBSCRIBE_GOAL,
        "done_when": MCP_SUBSCRIBE_DONE_WHEN,
        "source": "genesis_bind_resource_subscribe",
    },
    {
        "id": MCP_ROOTS_CHANGED_ID,
        "goal": MCP_ROOTS_CHANGED_GOAL,
        "done_when": MCP_ROOTS_CHANGED_DONE_WHEN,
        "source": "genesis_bind_roots_list_changed",
    },
    {
        "id": BROWSER_CDP_ID,
        "goal": BROWSER_CDP_GOAL,
        "done_when": BROWSER_CDP_DONE_WHEN,
        "source": "genesis_bind_browser_cdp",
    },
    {
        "id": GITHUB_ACTUATION_ID,
        "goal": GITHUB_ACTUATION_GOAL,
        "done_when": GITHUB_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_github",
    },
    {
        "id": SQLITE_ACTUATION_ID,
        "goal": SQLITE_ACTUATION_GOAL,
        "done_when": SQLITE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_sqlite",
    },
    {
        "id": WEBHOOK_ACTUATION_ID,
        "goal": WEBHOOK_ACTUATION_GOAL,
        "done_when": WEBHOOK_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_webhook",
    },
    {
        "id": MCP_PROGRESS_ID,
        "goal": MCP_PROGRESS_GOAL,
        "done_when": MCP_PROGRESS_DONE_WHEN,
        "source": "genesis_bind_progress",
    },
    {
        "id": MCP_TOOLS_CHANGED_ID,
        "goal": MCP_TOOLS_CHANGED_GOAL,
        "done_when": MCP_TOOLS_CHANGED_DONE_WHEN,
        "source": "genesis_bind_tools_list_changed",
    },
    {
        "id": SMTP_ACTUATION_ID,
        "goal": SMTP_ACTUATION_GOAL,
        "done_when": SMTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_smtp",
    },
    {
        "id": MCP_HTTP_AUTH_ID,
        "goal": MCP_HTTP_AUTH_GOAL,
        "done_when": MCP_HTTP_AUTH_DONE_WHEN,
        "source": "genesis_bind_http_auth",
    },
    {
        "id": IMAP_ACTUATION_ID,
        "goal": IMAP_ACTUATION_GOAL,
        "done_when": IMAP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_imap",
    },
    {
        "id": REDIS_ACTUATION_ID,
        "goal": REDIS_ACTUATION_GOAL,
        "done_when": REDIS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_redis",
    },
    {
        "id": MQTT_ACTUATION_ID,
        "goal": MQTT_ACTUATION_GOAL,
        "done_when": MQTT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mqtt",
    },
    {
        "id": DNS_ACTUATION_ID,
        "goal": DNS_ACTUATION_GOAL,
        "done_when": DNS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_dns",
    },
    {
        "id": LDAP_ACTUATION_ID,
        "goal": LDAP_ACTUATION_GOAL,
        "done_when": LDAP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ldap",
    },
    {
        "id": POSTGRES_ACTUATION_ID,
        "goal": POSTGRES_ACTUATION_GOAL,
        "done_when": POSTGRES_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_postgres",
    },
    {
        "id": S3_ACTUATION_ID,
        "goal": S3_ACTUATION_GOAL,
        "done_when": S3_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_s3",
    },
    {
        "id": WATCH_ACTUATION_ID,
        "goal": WATCH_ACTUATION_GOAL,
        "done_when": WATCH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_watch",
    },
    {
        "id": MCP_CURSOR_ID,
        "goal": MCP_CURSOR_GOAL,
        "done_when": MCP_CURSOR_DONE_WHEN,
        "source": "genesis_bind_cursor_pagination",
    },
    {
        "id": MCP_STRUCTURED_ID,
        "goal": MCP_STRUCTURED_GOAL,
        "done_when": MCP_STRUCTURED_DONE_WHEN,
        "source": "genesis_bind_structured_output",
    },
    {
        "id": WEBSOCKET_ACTUATION_ID,
        "goal": WEBSOCKET_ACTUATION_GOAL,
        "done_when": WEBSOCKET_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_websocket",
    },
    {
        "id": SSH_ACTUATION_ID,
        "goal": SSH_ACTUATION_GOAL,
        "done_when": SSH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ssh",
    },
    {
        "id": GRPC_ACTUATION_ID,
        "goal": GRPC_ACTUATION_GOAL,
        "done_when": GRPC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_grpc",
    },
    {
        "id": AMQP_ACTUATION_ID,
        "goal": AMQP_ACTUATION_GOAL,
        "done_when": AMQP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_amqp",
    },
    {
        "id": FTP_ACTUATION_ID,
        "goal": FTP_ACTUATION_GOAL,
        "done_when": FTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ftp",
    },
    {
        "id": TFTP_ACTUATION_ID,
        "goal": TFTP_ACTUATION_GOAL,
        "done_when": TFTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_tftp",
    },
    {
        "id": SNMP_ACTUATION_ID,
        "goal": SNMP_ACTUATION_GOAL,
        "done_when": SNMP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_snmp",
    },
    {
        "id": SYSLOG_ACTUATION_ID,
        "goal": SYSLOG_ACTUATION_GOAL,
        "done_when": SYSLOG_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_syslog",
    },
    {
        "id": NTP_ACTUATION_ID,
        "goal": NTP_ACTUATION_GOAL,
        "done_when": NTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ntp",
    },
    {
        "id": RADIUS_ACTUATION_ID,
        "goal": RADIUS_ACTUATION_GOAL,
        "done_when": RADIUS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_radius",
    },
    {
        "id": DHCP_ACTUATION_ID,
        "goal": DHCP_ACTUATION_GOAL,
        "done_when": DHCP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_dhcp",
    },
    {
        "id": IKE_ACTUATION_ID,
        "goal": IKE_ACTUATION_GOAL,
        "done_when": IKE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ike",
    },
    {
        "id": SIP_ACTUATION_ID,
        "goal": SIP_ACTUATION_GOAL,
        "done_when": SIP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_sip",
    },
    {
        "id": STUN_ACTUATION_ID,
        "goal": STUN_ACTUATION_GOAL,
        "done_when": STUN_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_stun",
    },
    {
        "id": TURN_ACTUATION_ID,
        "goal": TURN_ACTUATION_GOAL,
        "done_when": TURN_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_turn",
    },
    {
        "id": ICE_ACTUATION_ID,
        "goal": ICE_ACTUATION_GOAL,
        "done_when": ICE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ice",
    },
    {
        "id": DTLS_ACTUATION_ID,
        "goal": DTLS_ACTUATION_GOAL,
        "done_when": DTLS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_dtls",
    },
    {
        "id": SRTP_ACTUATION_ID,
        "goal": SRTP_ACTUATION_GOAL,
        "done_when": SRTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_srtp",
    },
    {
        "id": SCTP_ACTUATION_ID,
        "goal": SCTP_ACTUATION_GOAL,
        "done_when": SCTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_sctp",
    },
    {
        "id": DATACHANNEL_ACTUATION_ID,
        "goal": DATACHANNEL_ACTUATION_GOAL,
        "done_when": DATACHANNEL_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_datachannel",
    },
    {
        "id": QUIC_ACTUATION_ID,
        "goal": QUIC_ACTUATION_GOAL,
        "done_when": QUIC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_quic",
    },
    {
        "id": HTTP3_ACTUATION_ID,
        "goal": HTTP3_ACTUATION_GOAL,
        "done_when": HTTP3_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_http3",
    },
    {
        "id": WEBTRANSPORT_ACTUATION_ID,
        "goal": WEBTRANSPORT_ACTUATION_GOAL,
        "done_when": WEBTRANSPORT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_webtransport",
    },
    {
        "id": DATAGRAM_ACTUATION_ID,
        "goal": DATAGRAM_ACTUATION_GOAL,
        "done_when": DATAGRAM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_datagram",
    },
    {
        "id": MASQUE_ACTUATION_ID,
        "goal": MASQUE_ACTUATION_GOAL,
        "done_when": MASQUE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_masque",
    },
    {
        "id": CONNECTIP_ACTUATION_ID,
        "goal": CONNECTIP_ACTUATION_GOAL,
        "done_when": CONNECTIP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_connectip",
    },
    {
        "id": OHTTP_ACTUATION_ID,
        "goal": OHTTP_ACTUATION_GOAL,
        "done_when": OHTTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ohttp",
    },
    {
        "id": OHSVCB_ACTUATION_ID,
        "goal": OHSVCB_ACTUATION_GOAL,
        "done_when": OHSVCB_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ohsvcb",
    },
    {
        "id": HTTPSIG_ACTUATION_ID,
        "goal": HTTPSIG_ACTUATION_GOAL,
        "done_when": HTTPSIG_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_httpsig",
    },
    {
        "id": DIGESTFIELDS_ACTUATION_ID,
        "goal": DIGESTFIELDS_ACTUATION_GOAL,
        "done_when": DIGESTFIELDS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_digestfields",
    },
    {
        "id": BHTTP_ACTUATION_ID,
        "goal": BHTTP_ACTUATION_GOAL,
        "done_when": BHTTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_bhttp",
    },
    {
        "id": HTTP11_ACTUATION_ID,
        "goal": HTTP11_ACTUATION_GOAL,
        "done_when": HTTP11_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_http11",
    },
    {
        "id": HTTP2_ACTUATION_ID,
        "goal": HTTP2_ACTUATION_GOAL,
        "done_when": HTTP2_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_http2",
    },
    {
        "id": HTTPCACHE_ACTUATION_ID,
        "goal": HTTPCACHE_ACTUATION_GOAL,
        "done_when": HTTPCACHE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_httpcache",
    },
    {
        "id": HTTPSMANTICS_ACTUATION_ID,
        "goal": HTTPSMANTICS_ACTUATION_GOAL,
        "done_when": HTTPSMANTICS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_httpsemantics",
    },
    {
        "id": STRUCTUREDFIELDS_ACTUATION_ID,
        "goal": STRUCTUREDFIELDS_ACTUATION_GOAL,
        "done_when": STRUCTUREDFIELDS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_structuredfields",
    },
    {
        "id": CLIENTHINTS_ACTUATION_ID,
        "goal": CLIENTHINTS_ACTUATION_GOAL,
        "done_when": CLIENTHINTS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_clienthints",
    },
    {
        "id": EARLYHINTS_ACTUATION_ID,
        "goal": EARLYHINTS_ACTUATION_GOAL,
        "done_when": EARLYHINTS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_earlyhints",
    },
    {
        "id": ENCRYPTEDCONTENT_ACTUATION_ID,
        "goal": ENCRYPTEDCONTENT_ACTUATION_GOAL,
        "done_when": ENCRYPTEDCONTENT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_encryptedcontent",
    },
    {
        "id": ALTSVC_ACTUATION_ID,
        "goal": ALTSVC_ACTUATION_GOAL,
        "done_when": ALTSVC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_altsvc",
    },
    {
        "id": HSTS_ACTUATION_ID,
        "goal": HSTS_ACTUATION_GOAL,
        "done_when": HSTS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_hsts",
    },
    {
        "id": HPKP_ACTUATION_ID,
        "goal": HPKP_ACTUATION_GOAL,
        "done_when": HPKP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_hpkp",
    },
    {
        "id": EXPECTCT_ACTUATION_ID,
        "goal": EXPECTCT_ACTUATION_GOAL,
        "done_when": EXPECTCT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_expectct",
    },
    {
        "id": XFO_ACTUATION_ID,
        "goal": XFO_ACTUATION_GOAL,
        "done_when": XFO_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_xfo",
    },
    {
        "id": WEBORIGIN_ACTUATION_ID,
        "goal": WEBORIGIN_ACTUATION_GOAL,
        "done_when": WEBORIGIN_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_weborigin",
    },
    {
        "id": HTTPCOOKIE_ACTUATION_ID,
        "goal": HTTPCOOKIE_ACTUATION_GOAL,
        "done_when": HTTPCOOKIE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_httpcookie",
    },
    {
        "id": CONTENTDISPOSITION_ACTUATION_ID,
        "goal": CONTENTDISPOSITION_ACTUATION_GOAL,
        "done_when": CONTENTDISPOSITION_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_contentdisposition",
    },
    {
        "id": WEBLINKING_ACTUATION_ID,
        "goal": WEBLINKING_ACTUATION_GOAL,
        "done_when": WEBLINKING_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_weblinking",
    },
    {
        "id": EXTVALUE_ACTUATION_ID,
        "goal": EXTVALUE_ACTUATION_GOAL,
        "done_when": EXTVALUE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_extvalue",
    },
    {
        "id": STALECONTENT_ACTUATION_ID,
        "goal": STALECONTENT_ACTUATION_GOAL,
        "done_when": STALECONTENT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_stalecontent",
    },
    {
        "id": HTTPPATCH_ACTUATION_ID,
        "goal": HTTPPATCH_ACTUATION_GOAL,
        "done_when": HTTPPATCH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_httppatch",
    },
    {
        "id": WELLKNOWN_ACTUATION_ID,
        "goal": WELLKNOWN_ACTUATION_GOAL,
        "done_when": WELLKNOWN_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_wellknown",
    },
    {
        "id": WEBDAV_ACTUATION_ID,
        "goal": WEBDAV_ACTUATION_GOAL,
        "done_when": WEBDAV_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_webdav",
    },
    {
        "id": SPNEGO_ACTUATION_ID,
        "goal": SPNEGO_ACTUATION_GOAL,
        "done_when": SPNEGO_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_spnego",
    },
    {
        "id": HTTPTLS_ACTUATION_ID,
        "goal": HTTPTLS_ACTUATION_GOAL,
        "done_when": HTTPTLS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_httptls",
    },
    {
        "id": HTTPAUTH_ACTUATION_ID,
        "goal": HTTPAUTH_ACTUATION_GOAL,
        "done_when": HTTPAUTH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_httpauth",
    },
    {
        "id": TCN_ACTUATION_ID,
        "goal": TCN_ACTUATION_GOAL,
        "done_when": TCN_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_tcn",
    },
    {
        "id": HITMETER_ACTUATION_ID,
        "goal": HITMETER_ACTUATION_GOAL,
        "done_when": HITMETER_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_hitmeter",
    },
    {
        "id": ICP_ACTUATION_ID,
        "goal": ICP_ACTUATION_GOAL,
        "done_when": ICP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_icp",
    },
    {
        "id": HTTPVER_ACTUATION_ID,
        "goal": HTTPVER_ACTUATION_GOAL,
        "done_when": HTTPVER_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_httpver",
    },
    {
        "id": HTTPSTATE_ACTUATION_ID,
        "goal": HTTPSTATE_ACTUATION_GOAL,
        "done_when": HTTPSTATE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_httpstate",
    },
    {
        "id": DIGESTAUTH_ACTUATION_ID,
        "goal": DIGESTAUTH_ACTUATION_GOAL,
        "done_when": DIGESTAUTH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_digestauth",
    },
    {
        "id": HTTP10_ACTUATION_ID,
        "goal": HTTP10_ACTUATION_GOAL,
        "done_when": HTTP10_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_http10",
    },
    {
        "id": URL_ACTUATION_ID,
        "goal": URL_ACTUATION_GOAL,
        "done_when": URL_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_url",
    },
    {
        "id": URI_ACTUATION_ID,
        "goal": URI_ACTUATION_GOAL,
        "done_when": URI_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_uri",
    },
    {
        "id": MIME_ACTUATION_ID,
        "goal": MIME_ACTUATION_GOAL,
        "done_when": MIME_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mime",
    },
    {
        "id": GOPHER_ACTUATION_ID,
        "goal": GOPHER_ACTUATION_GOAL,
        "done_when": GOPHER_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_gopher",
    },
    {
        "id": FINGER_ACTUATION_ID,
        "goal": FINGER_ACTUATION_GOAL,
        "done_when": FINGER_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_finger",
    },
    {
        "id": LPD_ACTUATION_ID,
        "goal": LPD_ACTUATION_GOAL,
        "done_when": LPD_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_lpd",
    },
    {
        "id": NNTP_ACTUATION_ID,
        "goal": NNTP_ACTUATION_GOAL,
        "done_when": NNTP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_nntp",
    },
    {
        "id": TELNET_ACTUATION_ID,
        "goal": TELNET_ACTUATION_GOAL,
        "done_when": TELNET_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_telnet",
    },
    {
        "id": TCP_ACTUATION_ID,
        "goal": TCP_ACTUATION_GOAL,
        "done_when": TCP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_tcp",
    },
    {
        "id": UDP_ACTUATION_ID,
        "goal": UDP_ACTUATION_GOAL,
        "done_when": UDP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_udp",
    },
    {
        "id": ICMP_ACTUATION_ID,
        "goal": ICMP_ACTUATION_GOAL,
        "done_when": ICMP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_icmp",
    },
    {
        "id": IP_ACTUATION_ID,
        "goal": IP_ACTUATION_GOAL,
        "done_when": IP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ip",
    },
    {
        "id": ARP_ACTUATION_ID,
        "goal": ARP_ACTUATION_GOAL,
        "done_when": ARP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_arp",
    },
    {
        "id": RARP_ACTUATION_ID,
        "goal": RARP_ACTUATION_GOAL,
        "done_when": RARP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_rarp",
    },
    {
        "id": IGMP_ACTUATION_ID,
        "goal": IGMP_ACTUATION_GOAL,
        "done_when": IGMP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_igmp",
    },
    {
        "id": MLD_ACTUATION_ID,
        "goal": MLD_ACTUATION_GOAL,
        "done_when": MLD_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mld",
    },
    {
        "id": NDP_ACTUATION_ID,
        "goal": NDP_ACTUATION_GOAL,
        "done_when": NDP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ndp",
    },
    {
        "id": SLAAC_ACTUATION_ID,
        "goal": SLAAC_ACTUATION_GOAL,
        "done_when": SLAAC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_slaac",
    },
    {
        "id": TEMPADDR_ACTUATION_ID,
        "goal": TEMPADDR_ACTUATION_GOAL,
        "done_when": TEMPADDR_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_tempaddr",
    },
    {
        "id": OPAQUEIID_ACTUATION_ID,
        "goal": OPAQUEIID_ACTUATION_GOAL,
        "done_when": OPAQUEIID_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_opaqueiid",
    },
    {
        "id": CGA_ACTUATION_ID,
        "goal": CGA_ACTUATION_GOAL,
        "done_when": CGA_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_cga",
    },
    {
        "id": SEND_ACTUATION_ID,
        "goal": SEND_ACTUATION_GOAL,
        "done_when": SEND_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_send",
    },
    {
        "id": ULA_ACTUATION_ID,
        "goal": ULA_ACTUATION_GOAL,
        "done_when": ULA_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ula",
    },
    {
        "id": IPV6ADDR_ACTUATION_ID,
        "goal": IPV6ADDR_ACTUATION_GOAL,
        "done_when": IPV6ADDR_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ipv6addr",
    },
    {
        "id": IPV6SCOPE_ACTUATION_ID,
        "goal": IPV6SCOPE_ACTUATION_GOAL,
        "done_when": IPV6SCOPE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ipv6scope",
    },
    {
        "id": ADDRSELECT_ACTUATION_ID,
        "goal": ADDRSELECT_ACTUATION_GOAL,
        "done_when": ADDRSELECT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_addrselect",
    },
    {
        "id": ADDRPOLICY_ACTUATION_ID,
        "goal": ADDRPOLICY_ACTUATION_GOAL,
        "done_when": ADDRPOLICY_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_addrpolicy",
    },
    {
        "id": FIRSTHOP_ACTUATION_ID,
        "goal": FIRSTHOP_ACTUATION_GOAL,
        "done_when": FIRSTHOP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_firsthop",
    },
    {
        "id": RDNSS_ACTUATION_ID,
        "goal": RDNSS_ACTUATION_GOAL,
        "done_when": RDNSS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_rdnss",
    },
    {
        "id": PREF64_ACTUATION_ID,
        "goal": PREF64_ACTUATION_GOAL,
        "done_when": PREF64_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pref64",
    },
    {
        "id": NAT64_ACTUATION_ID,
        "goal": NAT64_ACTUATION_GOAL,
        "done_when": NAT64_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_nat64",
    },
    {
        "id": DNS64_ACTUATION_ID,
        "goal": DNS64_ACTUATION_GOAL,
        "done_when": DNS64_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_dns64",
    },
    {
        "id": XLAT_ACTUATION_ID,
        "goal": XLAT_ACTUATION_GOAL,
        "done_when": XLAT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_xlat",
    },
    {
        "id": DISC_ACTUATION_ID,
        "goal": DISC_ACTUATION_GOAL,
        "done_when": DISC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_disc",
    },
    {
        "id": DSLITE_ACTUATION_ID,
        "goal": DSLITE_ACTUATION_GOAL,
        "done_when": DSLITE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_dslite",
    },
    {
        "id": LW4O6_ACTUATION_ID,
        "goal": LW4O6_ACTUATION_GOAL,
        "done_when": LW4O6_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_lw4o6",
    },
    {
        "id": MAPE_ACTUATION_ID,
        "goal": MAPE_ACTUATION_GOAL,
        "done_when": MAPE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mape",
    },
    {
        "id": MAPT_ACTUATION_ID,
        "goal": MAPT_ACTUATION_GOAL,
        "done_when": MAPT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mapt",
    },
    {
        "id": S46_ACTUATION_ID,
        "goal": S46_ACTUATION_GOAL,
        "done_when": S46_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_s46",
    },
    {
        "id": UCPE_ACTUATION_ID,
        "goal": UCPE_ACTUATION_GOAL,
        "done_when": UCPE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ucpe",
    },
    {
        "id": M46_ACTUATION_ID,
        "goal": M46_ACTUATION_GOAL,
        "done_when": M46_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_m46",
    },
    {
        "id": PREFIX64_ACTUATION_ID,
        "goal": PREFIX64_ACTUATION_GOAL,
        "done_when": PREFIX64_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_prefix64",
    },
    {
        "id": SIIT_ACTUATION_ID,
        "goal": SIIT_ACTUATION_GOAL,
        "done_when": SIIT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_siit",
    },
    {
        "id": EAM_ACTUATION_ID,
        "goal": EAM_ACTUATION_GOAL,
        "done_when": EAM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_eam",
    },
    {
        "id": SIITDC_ACTUATION_ID,
        "goal": SIITDC_ACTUATION_GOAL,
        "done_when": SIITDC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_siitdc",
    },
    {
        "id": SIITDTM_ACTUATION_ID,
        "goal": SIITDTM_ACTUATION_GOAL,
        "done_when": SIITDTM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_siitdtm",
    },
    {
        "id": V4EMBED_ACTUATION_ID,
        "goal": V4EMBED_ACTUATION_GOAL,
        "done_when": V4EMBED_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_v4embed",
    },
    {
        "id": LUPREFIX_ACTUATION_ID,
        "goal": LUPREFIX_ACTUATION_GOAL,
        "done_when": LUPREFIX_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_luprefix",
    },
    {
        "id": SIXRD_ACTUATION_ID,
        "goal": SIXRD_ACTUATION_GOAL,
        "done_when": SIXRD_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_sixrd",
    },
    {
        "id": SIXTO4_ACTUATION_ID,
        "goal": SIXTO4_ACTUATION_GOAL,
        "done_when": SIXTO4_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_sixto4",
    },
    {
        "id": TEREDO_ACTUATION_ID,
        "goal": TEREDO_ACTUATION_GOAL,
        "done_when": TEREDO_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_teredo",
    },
    {
        "id": ISATAP_ACTUATION_ID,
        "goal": ISATAP_ACTUATION_GOAL,
        "done_when": ISATAP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_isatap",
    },
    {
        "id": SIXOVER4_ACTUATION_ID,
        "goal": SIXOVER4_ACTUATION_GOAL,
        "done_when": SIXOVER4_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_sixover4",
    },
    {
        "id": SIXIN4_ACTUATION_ID,
        "goal": SIXIN4_ACTUATION_GOAL,
        "done_when": SIXIN4_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_sixin4",
    },
    {
        "id": TSP_ACTUATION_ID,
        "goal": TSP_ACTUATION_GOAL,
        "done_when": TSP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_tsp",
    },
    {
        "id": L2TP_ACTUATION_ID,
        "goal": L2TP_ACTUATION_GOAL,
        "done_when": L2TP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_l2tp",
    },
    {
        "id": MESH_ACTUATION_ID,
        "goal": MESH_ACTUATION_GOAL,
        "done_when": MESH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mesh",
    },
    {
        "id": ENCAP_ACTUATION_ID,
        "goal": ENCAP_ACTUATION_GOAL,
        "done_when": ENCAP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_encap",
    },
    {
        "id": MPBGP_ACTUATION_ID,
        "goal": MPBGP_ACTUATION_GOAL,
        "done_when": MPBGP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mpbgp",
    },
    {
        "id": BGP4_ACTUATION_ID,
        "goal": BGP4_ACTUATION_GOAL,
        "done_when": BGP4_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_bgp4",
    },
    {
        "id": RTREFRESH_ACTUATION_ID,
        "goal": RTREFRESH_ACTUATION_GOAL,
        "done_when": RTREFRESH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_rtrefresh",
    },
    {
        "id": BGPCOMM_ACTUATION_ID,
        "goal": BGPCOMM_ACTUATION_GOAL,
        "done_when": BGPCOMM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_bgpcomm",
    },
    {
        "id": EXTCOMM_ACTUATION_ID,
        "goal": EXTCOMM_ACTUATION_GOAL,
        "done_when": EXTCOMM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_extcomm",
    },
    {
        "id": LARGECOMM_ACTUATION_ID,
        "goal": LARGECOMM_ACTUATION_GOAL,
        "done_when": LARGECOMM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_largecomm",
    },
    {
        "id": BGPSEC_ACTUATION_ID,
        "goal": BGPSEC_ACTUATION_GOAL,
        "done_when": BGPSEC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_bgpsec",
    },
    {
        "id": RTR_ACTUATION_ID,
        "goal": RTR_ACTUATION_GOAL,
        "done_when": RTR_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_rtr",
    },
    {
        "id": EBGP_ACTUATION_ID,
        "goal": EBGP_ACTUATION_GOAL,
        "done_when": EBGP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ebgp",
    },
    {
        "id": EVPN_ACTUATION_ID,
        "goal": EVPN_ACTUATION_GOAL,
        "done_when": EVPN_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_evpn",
    },
    {
        "id": ETREE_ACTUATION_ID,
        "goal": ETREE_ACTUATION_GOAL,
        "done_when": ETREE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_etree",
    },
    {
        "id": NVO_ACTUATION_ID,
        "goal": NVO_ACTUATION_GOAL,
        "done_when": NVO_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_nvo",
    },
    {
        "id": DFE_ACTUATION_ID,
        "goal": DFE_ACTUATION_GOAL,
        "done_when": DFE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_dfe",
    },
    {
        "id": IRB_ACTUATION_ID,
        "goal": IRB_ACTUATION_GOAL,
        "done_when": IRB_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_irb",
    },
    {
        "id": IPPFX_ACTUATION_ID,
        "goal": IPPFX_ACTUATION_GOAL,
        "done_when": IPPFX_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ippfx",
    },
    {
        "id": PROXYND_ACTUATION_ID,
        "goal": PROXYND_ACTUATION_GOAL,
        "done_when": PROXYND_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_proxynd",
    },
    {
        "id": IMLPROXY_ACTUATION_ID,
        "goal": IMLPROXY_ACTUATION_GOAL,
        "done_when": IMLPROXY_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_imlproxy",
    },
    {
        "id": EVPNBUM_ACTUATION_ID,
        "goal": EVPNBUM_ACTUATION_GOAL,
        "done_when": EVPNBUM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_evpnbum",
    },
    {
        "id": FXC_ACTUATION_ID,
        "goal": FXC_ACTUATION_GOAL,
        "done_when": FXC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_fxc",
    },
    {
        "id": DFREC_ACTUATION_ID,
        "goal": DFREC_ACTUATION_GOAL,
        "done_when": DFREC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_dfrec",
    },
    {
        "id": MSRED_ACTUATION_ID,
        "goal": MSRED_ACTUATION_GOAL,
        "done_when": MSRED_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_msred",
    },
    {
        "id": P2MPIR_ACTUATION_ID,
        "goal": P2MPIR_ACTUATION_GOAL,
        "done_when": P2MPIR_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_p2mpir",
    },
    {
        "id": OIR_ACTUATION_ID,
        "goal": OIR_ACTUATION_GOAL,
        "done_when": OIR_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_oir",
    },
    {
        "id": IESI_ACTUATION_ID,
        "goal": IESI_ACTUATION_GOAL,
        "done_when": IESI_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_iesi",
    },
    {
        "id": PBB_ACTUATION_ID,
        "goal": PBB_ACTUATION_GOAL,
        "done_when": PBB_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pbb",
    },
    {
        "id": MACIP_ACTUATION_ID,
        "goal": MACIP_ACTUATION_GOAL,
        "done_when": MACIP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_macip",
    },
    {
        "id": EVPNREQ_ACTUATION_ID,
        "goal": EVPNREQ_ACTUATION_GOAL,
        "done_when": EVPNREQ_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_evpnreq",
    },
    {
        "id": VPLS_ACTUATION_ID,
        "goal": VPLS_ACTUATION_GOAL,
        "done_when": VPLS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_vpls",
    },
    {
        "id": LDPSIG_ACTUATION_ID,
        "goal": LDPSIG_ACTUATION_GOAL,
        "done_when": LDPSIG_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ldpsig",
    },
    {
        "id": PWLDP_ACTUATION_ID,
        "goal": PWLDP_ACTUATION_GOAL,
        "done_when": PWLDP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pwldp",
    },
    {
        "id": PWE3_ACTUATION_ID,
        "goal": PWE3_ACTUATION_GOAL,
        "done_when": PWE3_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pwe3",
    },
    {
        "id": PWREQ_ACTUATION_ID,
        "goal": PWREQ_ACTUATION_GOAL,
        "done_when": PWREQ_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pwreq",
    },
    {
        "id": MPLSARCH_ACTUATION_ID,
        "goal": MPLSARCH_ACTUATION_GOAL,
        "done_when": MPLSARCH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mplsarch",
    },
    {
        "id": MPLSLSE_ACTUATION_ID,
        "goal": MPLSLSE_ACTUATION_GOAL,
        "done_when": MPLSLSE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mplslse",
    },
    {
        "id": RSVPTE_ACTUATION_ID,
        "goal": RSVPTE_ACTUATION_GOAL,
        "done_when": RSVPTE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_rsvpte",
    },
    {
        "id": GMPLS_ACTUATION_ID,
        "goal": GMPLS_ACTUATION_GOAL,
        "done_when": GMPLS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_gmpls",
    },
    {
        "id": LMP_ACTUATION_ID,
        "goal": LMP_ACTUATION_GOAL,
        "done_when": LMP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_lmp",
    },
    {
        "id": LSPHIER_ACTUATION_ID,
        "goal": LSPHIER_ACTUATION_GOAL,
        "done_when": LSPHIER_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_lsphier",
    },
    {
        "id": GUNI_ACTUATION_ID,
        "goal": GUNI_ACTUATION_GOAL,
        "done_when": GUNI_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_guni",
    },
    {
        "id": LWDM_ACTUATION_ID,
        "goal": LWDM_ACTUATION_GOAL,
        "done_when": LWDM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_lwdm",
    },
    {
        "id": OTN_ACTUATION_ID,
        "goal": OTN_ACTUATION_GOAL,
        "done_when": OTN_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_otn",
    },
    {
        "id": ASON_ACTUATION_ID,
        "goal": ASON_ACTUATION_GOAL,
        "done_when": ASON_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ason",
    },
    {
        "id": GREC_ACTUATION_ID,
        "goal": GREC_ACTUATION_GOAL,
        "done_when": GREC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_grec",
    },
    {
        "id": E2EREC_ACTUATION_ID,
        "goal": E2EREC_ACTUATION_GOAL,
        "done_when": E2EREC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_e2erec",
    },
    {
        "id": SEGREC_ACTUATION_ID,
        "goal": SEGREC_ACTUATION_GOAL,
        "done_when": SEGREC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_segrec",
    },
    {
        "id": EXROUTE_ACTUATION_ID,
        "goal": EXROUTE_ACTUATION_GOAL,
        "done_when": EXROUTE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_exroute",
    },
    {
        "id": P2MPTE_ACTUATION_ID,
        "goal": P2MPTE_ACTUATION_GOAL,
        "done_when": P2MPTE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_p2mpte",
    },
    {
        "id": CRANKBACK_ACTUATION_ID,
        "goal": CRANKBACK_ACTUATION_GOAL,
        "done_when": CRANKBACK_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_crankback",
    },
    {
        "id": LSPSTITCH_ACTUATION_ID,
        "goal": LSPSTITCH_ACTUATION_GOAL,
        "done_when": LSPSTITCH_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_lspstitch",
    },
    {
        "id": INTERAS_ACTUATION_ID,
        "goal": INTERAS_ACTUATION_GOAL,
        "done_when": INTERAS_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_interas",
    },
    {
        "id": PERDOM_ACTUATION_ID,
        "goal": PERDOM_ACTUATION_GOAL,
        "done_when": PERDOM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_perdom",
    },
    {
        "id": PCEP_ACTUATION_ID,
        "goal": PCEP_ACTUATION_GOAL,
        "done_when": PCEP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pcep",
    },
    {
        "id": BRPC_ACTUATION_ID,
        "goal": BRPC_ACTUATION_GOAL,
        "done_when": BRPC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_brpc",
    },
    {
        "id": DSCT_ACTUATION_ID,
        "goal": DSCT_ACTUATION_GOAL,
        "done_when": DSCT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_dsct",
    },
    {
        "id": PATHKEY_ACTUATION_ID,
        "goal": PATHKEY_ACTUATION_GOAL,
        "done_when": PATHKEY_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pathkey",
    },
    {
        "id": PCEXCL_ACTUATION_ID,
        "goal": PCEXCL_ACTUATION_GOAL,
        "done_when": PCEXCL_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pcexcl",
    },
    {
        "id": OBJFUN_ACTUATION_ID,
        "goal": OBJFUN_ACTUATION_GOAL,
        "done_when": OBJFUN_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_objfun",
    },
    {
        "id": GCO_ACTUATION_ID,
        "goal": GCO_ACTUATION_GOAL,
        "done_when": GCO_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_gco",
    },
    {
        "id": ILPCE_ACTUATION_ID,
        "goal": ILPCE_ACTUATION_GOAL,
        "done_when": ILPCE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_ilpce",
    },
    {
        "id": PCEMON_ACTUATION_ID,
        "goal": PCEMON_ACTUATION_GOAL,
        "done_when": PCEMON_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pcemon",
    },
    {
        "id": PCEPMP_ACTUATION_ID,
        "goal": PCEPMP_ACTUATION_GOAL,
        "done_when": PCEPMP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pcepmp",
    },
    {
        "id": WSON_ACTUATION_ID,
        "goal": WSON_ACTUATION_GOAL,
        "done_when": WSON_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_wson",
    },
    {
        "id": LSC_ACTUATION_ID,
        "goal": LSC_ACTUATION_GOAL,
        "done_when": LSC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_lsc",
    },
    {
        "id": ASBW_ACTUATION_ID,
        "goal": ASBW_ACTUATION_GOAL,
        "done_when": ASBW_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_asbw",
    },
    {
        "id": SMP_ACTUATION_ID,
        "goal": SMP_ACTUATION_GOAL,
        "done_when": SMP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_smp",
    },
    {
        "id": FMOAM_ACTUATION_ID,
        "goal": FMOAM_ACTUATION_GOAL,
        "done_when": FMOAM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_fmoam",
    },
    {
        "id": PCV_ACTUATION_ID,
        "goal": PCV_ACTUATION_GOAL,
        "done_when": PCV_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pcv",
    },
    {
        "id": LILB_ACTUATION_ID,
        "goal": LILB_ACTUATION_GOAL,
        "done_when": LILB_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_lilb",
    },
    {
        "id": PWST_ACTUATION_ID,
        "goal": PWST_ACTUATION_GOAL,
        "done_when": PWST_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pwst",
    },
    {
        "id": MLDP_ACTUATION_ID,
        "goal": MLDP_ACTUATION_GOAL,
        "done_when": MLDP_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mldp",
    },
    {
        "id": MVPN_ACTUATION_ID,
        "goal": MVPN_ACTUATION_GOAL,
        "done_when": MVPN_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_mvpn",
    },
    {
        "id": PMSI_ACTUATION_ID,
        "goal": PMSI_ACTUATION_GOAL,
        "done_when": PMSI_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_pmsi",
    },
    {
        "id": WILDAD_ACTUATION_ID,
        "goal": WILDAD_ACTUATION_GOAL,
        "done_when": WILDAD_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_wildad",
    },
    {
        "id": TWFEC_ACTUATION_ID,
        "goal": TWFEC_ACTUATION_GOAL,
        "done_when": TWFEC_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_twfec",
    },
    {
        "id": GTSM_ACTUATION_ID,
        "goal": GTSM_ACTUATION_GOAL,
        "done_when": GTSM_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_gtsm",
    },
    {
        "id": ELBL_ACTUATION_ID,
        "goal": ELBL_ACTUATION_GOAL,
        "done_when": ELBL_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_elbl",
    },
)

_LIVE_SHAPED_GOALS = (
    PROGRAM_TOWER_GOAL,
    PROGRAM_LATTICE_GOAL,
    PROGRAM_FABRIC_GOAL,
    (
        "Repair mixed-stack restoration after a red MCP hop fails the mixed grade: "
        "heal the hop in-process, re-solve the composition, and restore mixed stack "
        "health; an unrepairable hop must leave the stack unhealthy while default "
        "recovery stays blind."
    ),
    (
        "Close operational class `mission_leftover`: Optional later work is mixed "
        "absorbed stack repair so a healable producer restores mixed absorbed stack "
        "health."
    ),
    (
        "Close operational class `mission_leftover`: Optional later work is watching "
        "mixed MCP+absorbed goals in the recovery plane so a red MCP hop is healed."
    ),
    (
        "Repair leftover harvest isolation of the origin ledger: a shipped leftover "
        "still enters genesis fuel because leftover satisfaction only reads the "
        "lagging checkout ledger."
    ),
    (
        "Repair mission-worktree reclamation of stale directories: a path that exists "
        "on disk but is no longer a git working tree still fails git worktree remove, "
        "poisons the GC report, and leaves last_worktree_gc_error sticky so later "
        "valid worktrees never finish clean."
    ),
)


def genesis_diversify_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.kernel_genesis_diversify import "
        "builtin_kernel_genesis_diversify_proof; r=builtin_kernel_genesis_diversify_proof(); "
        "assert r['ok'] and r.get('action')=='kernel_genesis_diversify' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_genesis_diversify_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=GENESIS_DIVERSIFY_ID,
        name="Genesis catalog diversity bind",
        description=(
            "When experience fuel is empty and the compounding catalog's remaining "
            "successor fails controller selection gates, genesis bind ranks a "
            "diversity catalog of unsaturated capability families and fills the "
            "first open gate-passing mission instead of returning empty."
        ),
        kind="python",
        entry="blackhole_agent.kernel_genesis_diversify:builtin_kernel_genesis_diversify_proof",
        proof_command=genesis_diversify_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.kernel-genesis-bind",
        ),
        behavior_paths=(
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/kernel_genesis_bind.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Empty genesis bind after a rejected compounding successor no longer "
            "stalls: a diversity-ranked mission on a different capability family "
            "is bound in-process so recovered kernels cannot leave genesis unbound."
        ),
        tags=("genesis", "selection", "diversity", "catalog", "kernel"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def bind_diversity_successor(
    root: Path,
    *,
    campaign: LocalCampaign | None = None,
    lineage_ref: str = "",
    history: Sequence[Any] | None = None,
) -> tuple[str, str, str]:
    """Return the first open diversity successor that passes selection gates."""

    live_campaign = campaign if campaign is not None else load_campaign(Path(root))
    if not genesis_bind_is_needed(live_campaign):
        return "", "", ""
    live_history = list(
        history
        if history is not None
        else load_recent_mission_history(Path(root))
    )
    for item in DIVERSITY_CATALOG:
        if not _catalog_item_open(item, Path(root), lineage_ref=lineage_ref):
            continue
        goal = str(item.get("goal") or "").strip()
        done_when = str(item.get("done_when") or "").strip()
        if not goal or not done_when:
            continue
        gate = assess_mission_selection(
            Path(root),
            goal,
            done_when,
            history=live_history,
        )
        if gate.accepted:
            return goal, done_when, str(item.get("source") or "genesis_bind_diversity")
    return "", "", ""


def _register_compounding_through_fabric(root: Path) -> None:
    for capability_id in COMPOUNDING_THROUGH_FABRIC:
        _register_proved(root, capability_id)


def _write_live_shaped_history(root: Path) -> None:
    for index, goal in enumerate(_LIVE_SHAPED_GOALS, start=1):
        _write_complete_mission(root, f"live-shaped-{index}", goal, order=index)


def _prepare_exhausted_catalog(root: Path) -> None:
    from blackhole_agent.kernel_unscoped_resume import _register_turn_failed_closers

    _write_fixture_ledger(root)
    _register_turn_failed_closers(root)
    _write_live_shaped_history(root)
    _register_compounding_through_fabric(root)
    save_campaign(root, _consumed_campaign())


def builtin_kernel_genesis_diversify_proof() -> dict[str, Any]:
    """Prove behavioral diversity, rather than enumerating protocol names."""
    from unittest.mock import patch

    from blackhole_agent.mission_selection import MissionHistoryEntry

    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="genesis-diversify-quality-") as tmp:
        root = Path(tmp)
        campaign = _consumed_campaign()
        recipe = "Repair {name} handshake: seal a {name}digest and independently poll it with a later reader."
        history = [
            MissionHistoryEntry(str(i), recipe.format(name=name), semantic_signature(recipe.format(name=name)), name, "complete")
            for i, name in enumerate(("bgp4", "pmsi", "wildad"))
        ]
        repeated = assess_mission_selection(root, recipe.format(name="another_protocol"), "A reference peer works.", history=history)
        checks["renaming_is_repetition"] = not repeated.accepted and repeated.repetition_count == 3
        checks["behavior_family_saturates"] = repeated.recent_family_count == 3
        checks["ledger_only_contract_rejected"] = not assess_mission_selection(
            root, GENESIS_DIVERSIFY_GOAL, GENESIS_DIVERSIFY_DONE_WHEN, history=[]
        ).accepted
        checks["legacy_catalog_not_auto_accepted"] = bind_diversity_successor(root, campaign=campaign, history=[]) == ("", "", "")
        goal = "Repair memory retrieval after process restart without losing the original task context."
        done = "A fresh process answers a fixture question using the previously persisted task context."
        fixture = (
            {"id": "capability.fixture-static", "goal": GENESIS_DIVERSIFY_GOAL, "done_when": GENESIS_DIVERSIFY_DONE_WHEN, "source": "static"},
            {"id": "capability.fixture-outcome", "goal": goal, "done_when": done, "source": "outcome"},
        )
        with patch(__name__ + ".DIVERSITY_CATALOG", fixture):
            chosen = bind_diversity_successor(root, campaign=campaign, history=history)
        checks["chooses_different_measurable_outcome"] = chosen == (goal, done, "outcome")
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    return {
        "ok": all(checks.values()), "action": "kernel_genesis_diversify", "checks": checks,
        "passed_count": sum(checks.values()), "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": GENESIS_DIVERSIFY_GOAL, "done_when": GENESIS_DIVERSIFY_DONE_WHEN,
    }
