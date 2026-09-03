from pathlib import Path

from blackhole_agent.httpsemantics_actuation import HTTPSMANTICS_ACTUATION_GOAL, HTTPSMANTICS_ACTUATION_ID
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
from blackhole_agent.httpcache_actuation import (
    DEFAULT_CACHEID,
    DEFAULT_FRESHNESS,
    EMPTY_CACHEID,
    FRAME_REVALIDATE,
    FRAME_STORE,
    HTTPCACHE_ACTUATION_DONE_WHEN,
    HTTPCACHE_ACTUATION_GOAL,
    HTTPCACHE_ACTUATION_ID,
    HTTPCACHE_LEFTOVER,
    HC_FIRST,
    SENTINEL,
    builtin_httpcache_actuation_proof,
    cache_control_header,
    crc32c,
    encode_revalidate,
    encode_store,
    etag_validator,
    format_cache_control,
    independent_httpcache_digest,
    parse_cache_control,
    parse_etag,
    parse_message,
    parse_revalidate_request,
    parse_stored_response,
    revalidate_not_modified,
    revalidate_request,
    run_httpcache_workflow,
    stored_response,
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
    HTTPCACHE_TOOL_PROVIDER,
    build_tool_routing_preflight,
    httpcache_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
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
    HTTPSMANTICS_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    HTTPSMANTICS_ACTUATION_ID,
)


def test_goal_binds_httpcache_actuation_plane() -> None:
    assert leftover_marker_ids(HTTPCACHE_ACTUATION_GOAL) == (HTTPCACHE_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPCACHE_LEFTOVER) == (HTTPCACHE_ACTUATION_ID,)
    assert HTTPCACHE_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HTTPSMANTICS_ACTUATION_GOAL) == (HTTPSMANTICS_ACTUATION_ID,)
    assert leftover_marker_ids(HTTP2_ACTUATION_GOAL) == (HTTP2_ACTUATION_ID,)
    assert leftover_marker_ids(HTTP11_ACTUATION_GOAL) == (HTTP11_ACTUATION_ID,)
    assert HTTPSMANTICS_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTP2_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert HTTPCACHE_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(HTTPCACHE_ACTUATION_GOAL)
    httpcache_signature = semantic_signature(HTTPCACHE_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(httpcache_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_httpcache_tool_completes_store_revalidate_poll() -> None:
    descriptor = httpcache_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPCACHE_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("httpcache",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPCACHE_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["httpcache"]

    missing = run_httpcache_workflow(with_cacheid=False)
    skip_bind = run_httpcache_workflow(skip_bind=True)
    skip_store_cycle = run_httpcache_workflow(do_store_cycle=False)
    skip_revalidate = run_httpcache_workflow(do_revalidate=False)
    skip_freshness = run_httpcache_workflow(do_freshness=False)
    skip_replay = run_httpcache_workflow(replay=False)
    skip_cacheid = run_httpcache_workflow(use_cacheid=False)
    live = run_httpcache_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_cacheid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_store_cycle["ok"] is False
    assert skip_store_cycle["error"] == "store_required"
    assert skip_revalidate["ok"] is False
    assert skip_revalidate["error"] == "revalidate_required"
    assert skip_freshness["ok"] is False
    assert skip_freshness["error"] == "freshness_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_cacheid["ok"] is False
    assert skip_cacheid["error"] == "cacheid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_httpcache_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["store_frame"] is True
    assert row["revalidate"] is True
    assert row["freshness_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["cacheid_bound"] is True
    assert row["digest"]
    assert live["cacheid"] == DEFAULT_CACHEID
    assert live["freshness"] == DEFAULT_FRESHNESS
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_store(identity=SENTINEL, cacheid=DEFAULT_CACHEID, freshness=DEFAULT_FRESHNESS)
    )
    assert queried["is_store"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["cacheid"] == DEFAULT_CACHEID
    assert queried["freshness"] == DEFAULT_FRESHNESS
    assert queried["type"] == FRAME_STORE
    assert queried["first_byte"] == HC_FIRST
    answered = parse_message(
        encode_revalidate(identity=SENTINEL, cacheid=DEFAULT_CACHEID, freshness=DEFAULT_FRESHNESS)
    )
    assert answered["is_revalidate"] is True and answered["is_response"] is True
    assert answered["cacheid"] == DEFAULT_CACHEID
    assert answered["freshness"] == DEFAULT_FRESHNESS
    packed = encode_store(identity=SENTINEL, cacheid=DEFAULT_CACHEID, freshness=DEFAULT_FRESHNESS)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_store(identity=SENTINEL, cacheid=DEFAULT_CACHEID, include_cacheid=False)
    )
    assert bare["has_cacheid"] is False
    assert bare["cacheid"] == EMPTY_CACHEID
    directives = parse_cache_control(cache_control_header(SENTINEL, DEFAULT_CACHEID))
    assert directives[1] == ("public", None)
    assert format_cache_control(directives) == cache_control_header(SENTINEL, DEFAULT_CACHEID)
    etag = parse_etag(etag_validator(SENTINEL, DEFAULT_CACHEID))
    assert etag["opaque"] == f"{DEFAULT_CACHEID:08x}"
    stored = parse_stored_response(stored_response(SENTINEL, DEFAULT_CACHEID))
    asked = parse_revalidate_request(revalidate_request(SENTINEL, DEFAULT_CACHEID))
    answered_http = revalidate_not_modified(stored, asked)
    assert stored["status"] == 200
    assert stored["fresh"] is True
    assert asked["method"] == "GET"
    assert answered_http["not_modified"] is True
    assert answered_http["status"] == 304


def test_builtin_proof_seals_httpcache_actuation() -> None:
    report = builtin_httpcache_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "httpcache_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_httpcache"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_cacheid_is_forbidden"]
    assert report["checks"]["skip_store_cycle_stays_empty"]
    assert report["checks"]["skip_revalidate_stays_empty"]
    assert report["checks"]["skip_freshness_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_cacheid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_freshness"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_httpcache"]
    assert report["checks"]["catalog_names_httpcache"]
    assert report["checks"]["catalog_names_httpsemantics"]
    assert report["checks"]["leftover_text_binds_httpcache"]
    assert report["checks"]["proved_httpcache_consumes_leftover"]
    assert report["mission_goal"] == HTTPCACHE_ACTUATION_GOAL
    assert report["done_when"] == HTTPCACHE_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[HTTPCACHE_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "httpcache" in capability.tags
    assert "rfc9111" in capability.tags
    assert "http" in capability.tags
    assert "cacheid" in capability.tags
    assert "freshness" in capability.tags
    assert "validator" in capability.tags


def test_selection_gate_accepts_httpcache_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        HTTPCACHE_ACTUATION_GOAL,
        HTTPCACHE_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(HTTPCACHE_ACTUATION_GOAL)
    assert "httpcache" in family
    assert "rfc9111" in family
    assert "cacheid" in family
    assert "freshness" in family
    assert "validator" in family
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
    assert "httpsemantic" not in family
    assert "rfc9110" not in family
    assert "methodid" not in family
    assert "fieldsection" not in family
    assert "http11" not in family
    assert "rfc9112" not in family
    assert "requestid" not in family
    assert "startline" not in family
