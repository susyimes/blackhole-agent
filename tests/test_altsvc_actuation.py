from pathlib import Path

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
from blackhole_agent.altsvc_actuation import (
    ALPN_H2,
    DEFAULT_ALTS,
    DEFAULT_ALTSVCID,
    DEFAULT_ORIGINDIGEST,
    EMPTY_ALTSVCID,
    FRAME_ALTSVC,
    FRAME_ORIGIN,
    ALTSVC_ACTUATION_DONE_WHEN,
    ALTSVC_ACTUATION_GOAL,
    ALTSVC_ACTUATION_ID,
    ALTSVC_LEFTOVER,
    AS_FIRST,
    HTTP2_ALTSVC_TYPE,
    RFC_ALTSVC_DUAL,
    RFC_ALTSVC_FIELD,
    SENTINEL,
    altsvc_request,
    altsvc_response,
    builtin_altsvc_actuation_proof,
    canonical_altsvc,
    canonical_origin,
    crc32c,
    encode_altsvc,
    encode_altsvc_frame,
    encode_origin,
    encode_origin_frame,
    independent_altsvc_digest,
    origin_request,
    origin_response,
    origin_uri,
    parse_alt_svc,
    parse_altsvc_frame,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_origin_frame,
    run_altsvc_workflow,
    serialize_alt_svc,
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
    ALTSVC_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    build_tool_routing_preflight,
    altsvc_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
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
)
NEIGHBOR_IDS = (
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
)


def test_goal_binds_altsvc_actuation_plane() -> None:
    assert leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (ALTSVC_ACTUATION_ID,)
    assert leftover_marker_ids(ALTSVC_LEFTOVER) == (ALTSVC_ACTUATION_ID,)
    assert ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HSTS_ACTUATION_GOAL) == (HSTS_ACTUATION_ID,)
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert HSTS_ACTUATION_ID in LOCAL_DENYLIST
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert ALTSVC_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(ALTSVC_ACTUATION_GOAL)
    altsvc_signature = semantic_signature(ALTSVC_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(altsvc_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_altsvc_tool_completes_altsvc_origin_poll() -> None:
    descriptor = altsvc_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ALTSVC_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("altsvc",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ALTSVC_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["altsvc"]

    missing = run_altsvc_workflow(with_altsvcid=False)
    skip_bind = run_altsvc_workflow(skip_bind=True)
    skip_altsvc = run_altsvc_workflow(do_altsvc=False)
    skip_origin = run_altsvc_workflow(do_origin=False)
    skip_origindigest = run_altsvc_workflow(do_origindigest=False)
    skip_replay = run_altsvc_workflow(replay=False)
    skip_altsvcid = run_altsvc_workflow(use_altsvcid=False)
    live = run_altsvc_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_altsvcid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_altsvc["ok"] is False
    assert skip_altsvc["error"] == "altsvc_required"
    assert skip_origin["ok"] is False
    assert skip_origin["error"] == "origin_required"
    assert skip_origindigest["ok"] is False
    assert skip_origindigest["error"] == "origindigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_altsvcid["ok"] is False
    assert skip_altsvcid["error"] == "altsvcid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_altsvc_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["altsvc_frame"] is True
    assert row["origin_frame"] is True
    assert row["origindigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["altsvcid_bound"] is True
    assert row["digest"]
    assert live["altsvcid"] == DEFAULT_ALTSVCID
    assert live["origindigest"] == DEFAULT_ORIGINDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_altsvc(identity=SENTINEL, altsvcid=DEFAULT_ALTSVCID, origindigest=DEFAULT_ORIGINDIGEST)
    )
    assert queried["is_altsvc"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["altsvcid"] == DEFAULT_ALTSVCID
    assert queried["origindigest"] == DEFAULT_ORIGINDIGEST
    assert queried["type"] == FRAME_ALTSVC
    assert queried["first_byte"] == AS_FIRST
    answered = parse_message(
        encode_origin(identity=SENTINEL, altsvcid=DEFAULT_ALTSVCID, origindigest=DEFAULT_ORIGINDIGEST)
    )
    assert answered["is_origin"] is True and answered["is_response"] is True
    assert answered["altsvcid"] == DEFAULT_ALTSVCID
    assert answered["origindigest"] == DEFAULT_ORIGINDIGEST
    packed = encode_altsvc(identity=SENTINEL, altsvcid=DEFAULT_ALTSVCID, origindigest=DEFAULT_ORIGINDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_altsvc(identity=SENTINEL, altsvcid=DEFAULT_ALTSVCID, include_altsvcid=False)
    )
    assert bare["has_altsvcid"] is False
    assert bare["altsvcid"] == EMPTY_ALTSVCID
    advertised = serialize_alt_svc(DEFAULT_ALTS)
    assert advertised == RFC_ALTSVC_FIELD
    assert parse_alt_svc(advertised) == DEFAULT_ALTS
    assert parse_alt_svc(RFC_ALTSVC_DUAL) == (
        ("h2", "alt.example.com", 8000, 0, 0),
        ("h2", "", 443, 0, 0),
    )
    frame = parse_altsvc_frame(encode_altsvc_frame("", advertised))
    assert frame["field_value"] == RFC_ALTSVC_FIELD
    assert frame["frame_type"] == HTTP2_ALTSVC_TYPE
    assert parse_origin_frame(encode_origin_frame((origin_uri(SENTINEL),))) == (origin_uri(SENTINEL),)
    asked = parse_http_request(altsvc_request(SENTINEL, DEFAULT_ALTSVCID))
    listed = parse_http_request(origin_request(SENTINEL, DEFAULT_ALTSVCID, DEFAULT_ORIGINDIGEST))
    got = parse_http_response(altsvc_response(SENTINEL, DEFAULT_ALTSVCID, DEFAULT_ORIGINDIGEST))
    origin_reply = parse_http_response(
        origin_response(SENTINEL, DEFAULT_ALTSVCID, DEFAULT_ORIGINDIGEST)
    )
    assert asked["method"] == "GET"
    assert asked["as_kind"] == "altsvc"
    assert listed["as_kind"] == "origin"
    assert got["status"] == 200
    assert origin_reply["status"] == 200
    assert got["alts"] == DEFAULT_ALTS
    assert origin_reply["origin"] == origin_uri(SENTINEL)
    assert canonical_altsvc(SENTINEL, DEFAULT_ALTSVCID).startswith(ALPN_H2)
    assert "origindigest=" in canonical_origin(SENTINEL, DEFAULT_ALTSVCID, DEFAULT_ORIGINDIGEST)


def test_builtin_proof_seals_altsvc_actuation() -> None:
    report = builtin_altsvc_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "altsvc_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_altsvc"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_altsvcid_is_forbidden"]
    assert report["checks"]["skip_altsvc_stays_empty"]
    assert report["checks"]["skip_origin_stays_empty"]
    assert report["checks"]["skip_origindigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_altsvcid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_origindigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_altsvc"]
    assert report["checks"]["catalog_names_altsvc"]
    assert report["checks"]["catalog_names_hsts"]
    assert report["checks"]["leftover_text_binds_altsvc"]
    assert report["checks"]["proved_altsvc_consumes_leftover"]
    assert report["mission_goal"] == ALTSVC_ACTUATION_GOAL
    assert report["done_when"] == ALTSVC_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[ALTSVC_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "altsvc" in capability.tags
    assert "rfc7838" in capability.tags
    assert "http" in capability.tags
    assert "altsvcid" in capability.tags
    assert "origindigest" in capability.tags
    assert "h2" in capability.tags


def test_selection_gate_accepts_altsvc_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        ALTSVC_ACTUATION_GOAL,
        ALTSVC_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(ALTSVC_ACTUATION_GOAL)
    assert "altsvc" in family
    assert "rfc7838" in family
    assert "altsvcid" in family
    assert "origindigest" in family
    assert "encryptedcontent" not in family
    assert "rfc8188" not in family
    assert "encid" not in family
    assert "hsts" not in family
    assert "rfc6797" not in family
    assert "hstsid" not in family
    assert "stsdigest" not in family
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
