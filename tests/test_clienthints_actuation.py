from pathlib import Path

from blackhole_agent.earlyhints_actuation import (
    EARLYHINTS_ACTUATION_GOAL,
    EARLYHINTS_ACTUATION_ID,
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
from blackhole_agent.structuredfields_actuation import (
    STRUCTUREDFIELDS_ACTUATION_GOAL,
    STRUCTUREDFIELDS_ACTUATION_ID,
)
from blackhole_agent.clienthints_actuation import (
    ACCEPT_CH_FIELDS,
    CRITICAL_CH_FIELDS,
    DEFAULT_CHID,
    DEFAULT_HINTSDIGEST,
    EMPTY_CHID,
    FRAME_ACCEPTCH,
    FRAME_CRITCH,
    CLIENTHINTS_ACTUATION_DONE_WHEN,
    CLIENTHINTS_ACTUATION_GOAL,
    CLIENTHINTS_ACTUATION_ID,
    CLIENTHINTS_LEFTOVER,
    CH_FIRST,
    SENTINEL,
    acceptch_request,
    acceptch_response,
    builtin_clienthints_actuation_proof,
    canonical_accept_ch,
    canonical_crit_ch,
    crc32c,
    critch_request,
    critch_response,
    encode_acceptch,
    encode_critch,
    independent_clienthints_digest,
    is_token,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_token_list,
    run_clienthints_workflow,
    serialize_token_list,
    token_list_matches,
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
    CLIENTHINTS_TOOL_PROVIDER,
    build_tool_routing_preflight,
    clienthints_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
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
    EARLYHINTS_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    EARLYHINTS_ACTUATION_ID,
)


def test_goal_binds_clienthints_actuation_plane() -> None:
    assert leftover_marker_ids(CLIENTHINTS_ACTUATION_GOAL) == (CLIENTHINTS_ACTUATION_ID,)
    assert leftover_marker_ids(CLIENTHINTS_LEFTOVER) == (CLIENTHINTS_ACTUATION_ID,)
    assert CLIENTHINTS_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert leftover_marker_ids(STRUCTUREDFIELDS_ACTUATION_GOAL) == (STRUCTUREDFIELDS_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPSMANTICS_ACTUATION_GOAL) == (HTTPSMANTICS_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPCACHE_ACTUATION_GOAL) == (HTTPCACHE_ACTUATION_ID,)
    assert leftover_marker_ids(HTTP2_ACTUATION_GOAL) == (HTTP2_ACTUATION_ID,)
    assert EARLYHINTS_ACTUATION_ID in LOCAL_DENYLIST
    assert STRUCTUREDFIELDS_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPSMANTICS_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPCACHE_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert CLIENTHINTS_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(CLIENTHINTS_ACTUATION_GOAL)
    clienthints_signature = semantic_signature(CLIENTHINTS_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(clienthints_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_clienthints_tool_completes_acceptch_critch_poll() -> None:
    descriptor = clienthints_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CLIENTHINTS_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("clienthints",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, CLIENTHINTS_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["clienthints"]

    missing = run_clienthints_workflow(with_chid=False)
    skip_bind = run_clienthints_workflow(skip_bind=True)
    skip_acceptch = run_clienthints_workflow(do_acceptch=False)
    skip_critch = run_clienthints_workflow(do_critch=False)
    skip_hintsdigest = run_clienthints_workflow(do_hintsdigest=False)
    skip_replay = run_clienthints_workflow(replay=False)
    skip_chid = run_clienthints_workflow(use_chid=False)
    live = run_clienthints_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_chid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_acceptch["ok"] is False
    assert skip_acceptch["error"] == "acceptch_required"
    assert skip_critch["ok"] is False
    assert skip_critch["error"] == "critch_required"
    assert skip_hintsdigest["ok"] is False
    assert skip_hintsdigest["error"] == "hintsdigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_chid["ok"] is False
    assert skip_chid["error"] == "chid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_clienthints_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["acceptch_frame"] is True
    assert row["critch"] is True
    assert row["hintsdigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["chid_bound"] is True
    assert row["digest"]
    assert live["chid"] == DEFAULT_CHID
    assert live["hintsdigest"] == DEFAULT_HINTSDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_acceptch(identity=SENTINEL, chid=DEFAULT_CHID, hintsdigest=DEFAULT_HINTSDIGEST)
    )
    assert queried["is_acceptch"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["chid"] == DEFAULT_CHID
    assert queried["hintsdigest"] == DEFAULT_HINTSDIGEST
    assert queried["type"] == FRAME_ACCEPTCH
    assert queried["first_byte"] == CH_FIRST
    answered = parse_message(
        encode_critch(identity=SENTINEL, chid=DEFAULT_CHID, hintsdigest=DEFAULT_HINTSDIGEST)
    )
    assert answered["is_critch"] is True and answered["is_response"] is True
    assert answered["chid"] == DEFAULT_CHID
    assert answered["hintsdigest"] == DEFAULT_HINTSDIGEST
    packed = encode_acceptch(identity=SENTINEL, chid=DEFAULT_CHID, hintsdigest=DEFAULT_HINTSDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_acceptch(identity=SENTINEL, chid=DEFAULT_CHID, include_chid=False)
    )
    assert bare["has_chid"] is False
    assert bare["chid"] == EMPTY_CHID
    advertised = serialize_token_list(ACCEPT_CH_FIELDS)
    assert parse_token_list(advertised) == ACCEPT_CH_FIELDS
    assert serialize_token_list(parse_token_list(advertised)) == advertised
    assert is_token("DPR") is True
    assert is_token("BH-CH-OK") is True
    asked = parse_http_request(acceptch_request(SENTINEL, DEFAULT_CHID))
    listed = parse_http_request(critch_request(SENTINEL, DEFAULT_CHID, DEFAULT_HINTSDIGEST))
    got = parse_http_response(acceptch_response(SENTINEL, DEFAULT_CHID, DEFAULT_HINTSDIGEST))
    crit_reply = parse_http_response(critch_response(SENTINEL, DEFAULT_CHID, DEFAULT_HINTSDIGEST))
    assert asked["method"] == "GET"
    assert asked["ch_kind"] == "acceptch"
    assert listed["ch_kind"] == "critch"
    assert got["status"] == 200
    assert crit_reply["crit_ch"] == CRITICAL_CH_FIELDS
    assert token_list_matches(serialize_token_list(got["accept_ch"]), advertised)
    assert parse_token_list("Sec-CH-Example, Sec-CH-Example-Other") == (
        "Sec-CH-Example",
        "Sec-CH-Example-Other",
    )
    assert canonical_accept_ch(SENTINEL, DEFAULT_CHID).startswith("DPR, Width, Viewport-Width")
    assert "chid=" in canonical_crit_ch(SENTINEL, DEFAULT_CHID, DEFAULT_HINTSDIGEST)


def test_builtin_proof_seals_clienthints_actuation() -> None:
    report = builtin_clienthints_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "clienthints_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_clienthints"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_chid_is_forbidden"]
    assert report["checks"]["skip_acceptch_stays_empty"]
    assert report["checks"]["skip_critch_stays_empty"]
    assert report["checks"]["skip_hintsdigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_chid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_hintsdigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_clienthints"]
    assert report["checks"]["catalog_names_clienthints"]
    assert report["checks"]["catalog_names_earlyhints"]
    assert report["checks"]["leftover_text_binds_clienthints"]
    assert report["checks"]["proved_clienthints_consumes_leftover"]
    assert report["mission_goal"] == CLIENTHINTS_ACTUATION_GOAL
    assert report["done_when"] == CLIENTHINTS_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[CLIENTHINTS_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "clienthints" in capability.tags
    assert "rfc8942" in capability.tags
    assert "http" in capability.tags
    assert "chid" in capability.tags
    assert "hintsdigest" in capability.tags


def test_selection_gate_accepts_clienthints_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        CLIENTHINTS_ACTUATION_GOAL,
        CLIENTHINTS_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(CLIENTHINTS_ACTUATION_GOAL)
    assert "clienthint" in family
    assert "acceptch" in family
    assert "chid" in family
    assert "critch" in family
    assert "hintsdigest" in family
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
    assert "httpcache" not in family
    assert "rfc9111" not in family
    assert "cacheid" not in family
    assert "freshness" not in family
    assert "http11" not in family
    assert "rfc9112" not in family
    assert "requestid" not in family
    assert "startline" not in family
    assert "httpsemantic" not in family
    assert "rfc9110" not in family
    assert "methodid" not in family
    assert "fieldsection" not in family
    assert "structuredfield" not in family
    assert "rfc8941" not in family
    assert "dictid" not in family
    assert "sfv" not in family
    assert "earlyhint" not in family
    assert "rfc8297" not in family
    assert "linkid" not in family
    assert "earlydigest" not in family
