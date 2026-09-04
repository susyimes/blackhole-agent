from pathlib import Path

from blackhole_agent.hpkp_actuation import (
    HPKP_ACTUATION_GOAL,
    HPKP_ACTUATION_ID,
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
from blackhole_agent.hsts_actuation import (
    DEFAULT_HSTSID,
    DEFAULT_STSDIGEST,
    DEFAULT_STS,
    EMPTY_HSTSID,
    FRAME_PRELOAD,
    FRAME_STS,
    HSTS_ACTUATION_DONE_WHEN,
    HSTS_ACTUATION_GOAL,
    HSTS_ACTUATION_ID,
    HSTS_LEFTOVER,
    HS_FIRST,
    PRELOAD_STS,
    RFC_STS_FIELD,
    RFC_STS_PRELOAD,
    SENTINEL,
    STS_HEADER,
    builtin_hsts_actuation_proof,
    canonical_preload,
    canonical_sts,
    crc32c,
    encode_preload,
    encode_sts,
    encode_sts_header,
    independent_hsts_digest,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_sts,
    parse_sts_header,
    preload_request,
    preload_response,
    run_hsts_workflow,
    serialize_sts,
    sts_request,
    sts_response,
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
    HSTS_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    build_tool_routing_preflight,
    hsts_tool_descriptor,
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
    HPKP_ACTUATION_GOAL,
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
    HPKP_ACTUATION_ID,
)


def test_goal_binds_hsts_actuation_plane() -> None:
    assert leftover_marker_ids(HSTS_ACTUATION_GOAL) == (HSTS_ACTUATION_ID,)
    assert leftover_marker_ids(HSTS_LEFTOVER) == (HSTS_ACTUATION_ID,)
    assert HSTS_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(HPKP_ACTUATION_GOAL) == (HPKP_ACTUATION_ID,)
    assert leftover_marker_ids(ALTSVC_ACTUATION_GOAL) == (ALTSVC_ACTUATION_ID,)
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert HPKP_ACTUATION_ID in LOCAL_DENYLIST
    assert ALTSVC_ACTUATION_ID in LOCAL_DENYLIST
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert HSTS_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(HSTS_ACTUATION_GOAL)
    hsts_signature = semantic_signature(HSTS_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(hsts_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_hsts_tool_completes_sts_preload_poll() -> None:
    descriptor = hsts_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HSTS_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("hsts",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HSTS_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["hsts"]

    missing = run_hsts_workflow(with_hstsid=False)
    skip_bind = run_hsts_workflow(skip_bind=True)
    skip_sts = run_hsts_workflow(do_sts=False)
    skip_preload = run_hsts_workflow(do_preload=False)
    skip_stsdigest = run_hsts_workflow(do_stsdigest=False)
    skip_replay = run_hsts_workflow(replay=False)
    skip_hstsid = run_hsts_workflow(use_hstsid=False)
    live = run_hsts_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_hstsid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_sts["ok"] is False
    assert skip_sts["error"] == "sts_required"
    assert skip_preload["ok"] is False
    assert skip_preload["error"] == "preload_required"
    assert skip_stsdigest["ok"] is False
    assert skip_stsdigest["error"] == "stsdigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_hstsid["ok"] is False
    assert skip_hstsid["error"] == "hstsid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_hsts_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["sts_frame"] is True
    assert row["preload_frame"] is True
    assert row["stsdigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["hstsid_bound"] is True
    assert row["digest"]
    assert live["hstsid"] == DEFAULT_HSTSID
    assert live["stsdigest"] == DEFAULT_STSDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_sts(identity=SENTINEL, hstsid=DEFAULT_HSTSID, stsdigest=DEFAULT_STSDIGEST)
    )
    assert queried["is_sts"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["hstsid"] == DEFAULT_HSTSID
    assert queried["stsdigest"] == DEFAULT_STSDIGEST
    assert queried["type"] == FRAME_STS
    assert queried["first_byte"] == HS_FIRST
    answered = parse_message(
        encode_preload(identity=SENTINEL, hstsid=DEFAULT_HSTSID, stsdigest=DEFAULT_STSDIGEST)
    )
    assert answered["is_preload"] is True and answered["is_response"] is True
    assert answered["hstsid"] == DEFAULT_HSTSID
    assert answered["stsdigest"] == DEFAULT_STSDIGEST
    packed = encode_sts(identity=SENTINEL, hstsid=DEFAULT_HSTSID, stsdigest=DEFAULT_STSDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_sts(identity=SENTINEL, hstsid=DEFAULT_HSTSID, include_hstsid=False)
    )
    assert bare["has_hstsid"] is False
    assert bare["hstsid"] == EMPTY_HSTSID
    advertised = serialize_sts(DEFAULT_STS)
    assert advertised == RFC_STS_FIELD
    assert parse_sts(advertised) == DEFAULT_STS
    assert parse_sts(RFC_STS_PRELOAD) == PRELOAD_STS
    header = parse_sts_header(encode_sts_header(DEFAULT_STS))
    assert header["field_value"] == RFC_STS_FIELD
    assert header["header"] == STS_HEADER
    asked = parse_http_request(sts_request(SENTINEL, DEFAULT_HSTSID))
    listed = parse_http_request(preload_request(SENTINEL, DEFAULT_HSTSID, DEFAULT_STSDIGEST))
    got = parse_http_response(sts_response(SENTINEL, DEFAULT_HSTSID, DEFAULT_STSDIGEST))
    preload_reply = parse_http_response(
        preload_response(SENTINEL, DEFAULT_HSTSID, DEFAULT_STSDIGEST)
    )
    assert asked["method"] == "GET"
    assert asked["hs_kind"] == "sts"
    assert listed["hs_kind"] == "preload"
    assert got["status"] == 200
    assert preload_reply["status"] == 200
    assert got["policy"] == DEFAULT_STS
    assert preload_reply["policy"] == PRELOAD_STS
    assert canonical_sts(SENTINEL, DEFAULT_HSTSID).startswith("max-age=")
    assert "stsdigest=" in canonical_preload(SENTINEL, DEFAULT_HSTSID, DEFAULT_STSDIGEST)


def test_builtin_proof_seals_hsts_actuation() -> None:
    report = builtin_hsts_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "hsts_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_hsts"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_hstsid_is_forbidden"]
    assert report["checks"]["skip_sts_stays_empty"]
    assert report["checks"]["skip_preload_stays_empty"]
    assert report["checks"]["skip_stsdigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_hstsid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_stsdigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_hsts"]
    assert report["checks"]["catalog_names_hsts"]
    assert report["checks"]["catalog_names_hpkp"]
    assert report["checks"]["leftover_text_binds_hsts"]
    assert report["checks"]["proved_hsts_consumes_leftover"]
    assert report["mission_goal"] == HSTS_ACTUATION_GOAL
    assert report["done_when"] == HSTS_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[HSTS_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "hsts" in capability.tags
    assert "rfc6797" in capability.tags
    assert "http" in capability.tags
    assert "hstsid" in capability.tags
    assert "stsdigest" in capability.tags
    assert "preload" in capability.tags


def test_selection_gate_accepts_hsts_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        HSTS_ACTUATION_GOAL,
        HSTS_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(HSTS_ACTUATION_GOAL)
    assert "hsts" in family
    assert "rfc6797" in family
    assert "hstsid" in family
    assert "stsdigest" in family
    assert "altsvc" not in family
    assert "rfc7838" not in family
    assert "altsvcid" not in family
    assert "hpkp" not in family
    assert "rfc7469" not in family
    assert "pinid" not in family
    assert "pindigest" not in family
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
