from pathlib import Path

from blackhole_agent.bhttp_actuation import BHTTP_ACTUATION_GOAL, BHTTP_ACTUATION_ID
from blackhole_agent.http11_actuation import HTTP11_ACTUATION_GOAL, HTTP11_ACTUATION_ID
from blackhole_agent.http2_actuation import HTTP2_ACTUATION_GOAL, HTTP2_ACTUATION_ID
from blackhole_agent.httpcache_actuation import HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID
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
from blackhole_agent.digestfields_actuation import (
    DEFAULT_DIGESTID,
    DEFAULT_CONTENTDIGEST,
    EMPTY_DIGESTID,
    FRAME_DIGEST,
    DIGESTFIELDS_ACTUATION_DONE_WHEN,
    DIGESTFIELDS_ACTUATION_GOAL,
    DIGESTFIELDS_ACTUATION_ID,
    DIGESTFIELDS_LEFTOVER,
    DF_FIRST,
    SENTINEL,
    builtin_digestfields_actuation_proof,
    content_digest_sfv,
    crc32c,
    encode_verify,
    encode_digest,
    independent_digestfields_digest,
    parse_message,
    run_digestfields_workflow,
)
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
    DIGESTFIELDS_TOOL_PROVIDER,
    build_tool_routing_preflight,
    digestfields_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
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
    BHTTP_ACTUATION_GOAL,
    HTTP11_ACTUATION_GOAL,
    HTTP2_ACTUATION_GOAL,
    HTTPCACHE_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    BHTTP_ACTUATION_ID,
    HTTP11_ACTUATION_ID,
    HTTP2_ACTUATION_ID,
    HTTPCACHE_ACTUATION_ID,
)


def test_goal_binds_digestfields_actuation_plane() -> None:
    assert leftover_marker_ids(DIGESTFIELDS_ACTUATION_GOAL) == (DIGESTFIELDS_ACTUATION_ID,)
    assert leftover_marker_ids(DIGESTFIELDS_LEFTOVER) == (DIGESTFIELDS_ACTUATION_ID,)
    assert DIGESTFIELDS_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(BHTTP_ACTUATION_GOAL) == (BHTTP_ACTUATION_ID,)
    assert leftover_marker_ids(HTTP11_ACTUATION_GOAL) == (HTTP11_ACTUATION_ID,)
    assert leftover_marker_ids(HTTP2_ACTUATION_GOAL) == (HTTP2_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPCACHE_ACTUATION_GOAL) == (HTTPCACHE_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPSIG_ACTUATION_GOAL) == (HTTPSIG_ACTUATION_ID,)
    assert BHTTP_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTP11_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTP2_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPCACHE_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert DIGESTFIELDS_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(DIGESTFIELDS_ACTUATION_GOAL)
    digestfields_signature = semantic_signature(DIGESTFIELDS_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(digestfields_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_digestfields_tool_completes_digest_verify_poll() -> None:
    descriptor = digestfields_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DIGESTFIELDS_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("digestfields",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DIGESTFIELDS_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["digestfields"]

    missing = run_digestfields_workflow(with_digestid=False)
    skip_bind = run_digestfields_workflow(skip_bind=True)
    skip_digest_cycle = run_digestfields_workflow(do_digest_cycle=False)
    skip_verify = run_digestfields_workflow(do_verify=False)
    skip_contentdigest = run_digestfields_workflow(do_contentdigest=False)
    skip_replay = run_digestfields_workflow(replay=False)
    skip_digestid = run_digestfields_workflow(use_digestid=False)
    live = run_digestfields_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_digestid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_digest_cycle["ok"] is False
    assert skip_digest_cycle["error"] == "digest_required"
    assert skip_verify["ok"] is False
    assert skip_verify["error"] == "verify_required"
    assert skip_contentdigest["ok"] is False
    assert skip_contentdigest["error"] == "contentdigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_digestid["ok"] is False
    assert skip_digestid["error"] == "digestid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_digestfields_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["digest_frame"] is True
    assert row["verify"] is True
    assert row["contentdigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["digestid_bound"] is True
    assert row["digest"]
    assert live["digestid"] == DEFAULT_DIGESTID
    assert live["contentdigest"] == DEFAULT_CONTENTDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_digest(identity=SENTINEL, digestid=DEFAULT_DIGESTID, contentdigest=DEFAULT_CONTENTDIGEST)
    )
    assert queried["is_digest"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["digestid"] == DEFAULT_DIGESTID
    assert queried["contentdigest"] == DEFAULT_CONTENTDIGEST
    assert queried["type"] == FRAME_DIGEST
    assert queried["first_byte"] == DF_FIRST
    answered = parse_message(
        encode_verify(identity=SENTINEL, digestid=DEFAULT_DIGESTID, contentdigest=DEFAULT_CONTENTDIGEST)
    )
    assert answered["is_verify"] is True and answered["is_response"] is True
    assert answered["digestid"] == DEFAULT_DIGESTID
    assert answered["contentdigest"] == DEFAULT_CONTENTDIGEST
    packed = encode_digest(identity=SENTINEL, digestid=DEFAULT_DIGESTID, contentdigest=DEFAULT_CONTENTDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_digest(identity=SENTINEL, digestid=DEFAULT_DIGESTID, include_digestid=False)
    )
    assert bare["has_digestid"] is False
    assert bare["digestid"] == EMPTY_DIGESTID
    sfv = content_digest_sfv(SENTINEL, DEFAULT_DIGESTID)
    assert sfv.startswith("sha-256=:") and sfv.endswith(":")


def test_builtin_proof_seals_digestfields_actuation() -> None:
    report = builtin_digestfields_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "digestfields_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_digestfields"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_digestid_is_forbidden"]
    assert report["checks"]["skip_digest_cycle_stays_empty"]
    assert report["checks"]["skip_verify_stays_empty"]
    assert report["checks"]["skip_contentdigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_digestid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_contentdigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_digestfields"]
    assert report["checks"]["catalog_names_digestfields"]
    assert report["checks"]["catalog_names_bhttp"]
    assert report["checks"]["catalog_names_http11"]
    assert report["checks"]["catalog_names_http2"]
    assert report["checks"]["catalog_names_httpcache"]
    assert report["checks"]["leftover_text_binds_digestfields"]
    assert report["checks"]["proved_digestfields_consumes_leftover"]
    assert report["mission_goal"] == DIGESTFIELDS_ACTUATION_GOAL
    assert report["done_when"] == DIGESTFIELDS_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[DIGESTFIELDS_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "digestfields" in capability.tags
    assert "rfc9530" in capability.tags
    assert "http" in capability.tags
    assert "digestid" in capability.tags
    assert "contentdigest" in capability.tags


def test_selection_gate_accepts_digestfields_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        DIGESTFIELDS_ACTUATION_GOAL,
        DIGESTFIELDS_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(DIGESTFIELDS_ACTUATION_GOAL)
    assert "digestfield" in family
    assert "rfc9530" in family
    assert "digestid" in family
    assert "contentdigest" in family
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
    assert "bhttp" not in family
    assert "rfc9292" not in family
    assert "messageid" not in family
    assert "http11" not in family
    assert "rfc9112" not in family
    assert "requestid" not in family
    assert "http2" not in family
    assert "rfc9113" not in family
    assert "settingsid" not in family
    assert "httpcache" not in family
    assert "rfc9111" not in family
    assert "cacheid" not in family
