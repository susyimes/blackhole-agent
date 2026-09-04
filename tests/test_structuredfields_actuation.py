from pathlib import Path

from blackhole_agent.clienthints_actuation import (
    CLIENTHINTS_ACTUATION_GOAL,
    CLIENTHINTS_ACTUATION_ID,
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
    DEFAULT_DICTID,
    DEFAULT_SFV,
    EMPTY_DICTID,
    FRAME_DICT,
    FRAME_LIST,
    STRUCTUREDFIELDS_ACTUATION_DONE_WHEN,
    STRUCTUREDFIELDS_ACTUATION_GOAL,
    STRUCTUREDFIELDS_ACTUATION_ID,
    STRUCTUREDFIELDS_LEFTOVER,
    SF_FIRST,
    SENTINEL,
    builtin_structuredfields_actuation_proof,
    canonical_dictionary,
    canonical_list,
    crc32c,
    dict_request,
    dict_response,
    encode_dict,
    encode_list,
    independent_structuredfields_digest,
    is_key,
    is_token,
    list_matches,
    list_request,
    list_response,
    parse_dictionary,
    parse_http_request,
    parse_http_response,
    parse_list,
    parse_message,
    representation_dictionary,
    run_structuredfields_workflow,
    serialize_dictionary,
    serialize_list,
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
    STRUCTUREDFIELDS_TOOL_PROVIDER,
    build_tool_routing_preflight,
    structuredfields_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
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
    CLIENTHINTS_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    CLIENTHINTS_ACTUATION_ID,
)


def test_goal_binds_structuredfields_actuation_plane() -> None:
    assert leftover_marker_ids(STRUCTUREDFIELDS_ACTUATION_GOAL) == (STRUCTUREDFIELDS_ACTUATION_ID,)
    assert leftover_marker_ids(STRUCTUREDFIELDS_LEFTOVER) == (STRUCTUREDFIELDS_ACTUATION_ID,)
    assert STRUCTUREDFIELDS_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(CLIENTHINTS_ACTUATION_GOAL) == (CLIENTHINTS_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPSMANTICS_ACTUATION_GOAL) == (HTTPSMANTICS_ACTUATION_ID,)
    assert leftover_marker_ids(HTTPCACHE_ACTUATION_GOAL) == (HTTPCACHE_ACTUATION_ID,)
    assert leftover_marker_ids(HTTP2_ACTUATION_GOAL) == (HTTP2_ACTUATION_ID,)
    assert CLIENTHINTS_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPSMANTICS_ACTUATION_ID in LOCAL_DENYLIST
    assert HTTPCACHE_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert STRUCTUREDFIELDS_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(STRUCTUREDFIELDS_ACTUATION_GOAL)
    structuredfields_signature = semantic_signature(STRUCTUREDFIELDS_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(structuredfields_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_structuredfields_tool_completes_dict_list_poll() -> None:
    descriptor = structuredfields_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STRUCTUREDFIELDS_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("structuredfields",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STRUCTUREDFIELDS_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["structuredfields"]

    missing = run_structuredfields_workflow(with_dictid=False)
    skip_bind = run_structuredfields_workflow(skip_bind=True)
    skip_dict_cycle = run_structuredfields_workflow(do_dict_cycle=False)
    skip_list = run_structuredfields_workflow(do_list=False)
    skip_sfv = run_structuredfields_workflow(do_sfv=False)
    skip_replay = run_structuredfields_workflow(replay=False)
    skip_dictid = run_structuredfields_workflow(use_dictid=False)
    live = run_structuredfields_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_dictid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_dict_cycle["ok"] is False
    assert skip_dict_cycle["error"] == "dict_required"
    assert skip_list["ok"] is False
    assert skip_list["error"] == "list_required"
    assert skip_sfv["ok"] is False
    assert skip_sfv["error"] == "sfv_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_dictid["ok"] is False
    assert skip_dictid["error"] == "dictid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_structuredfields_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["dict_frame"] is True
    assert row["list"] is True
    assert row["sfv_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["dictid_bound"] is True
    assert row["digest"]
    assert live["dictid"] == DEFAULT_DICTID
    assert live["sfv"] == DEFAULT_SFV
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_dict(identity=SENTINEL, dictid=DEFAULT_DICTID, sfv=DEFAULT_SFV)
    )
    assert queried["is_dict"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["dictid"] == DEFAULT_DICTID
    assert queried["sfv"] == DEFAULT_SFV
    assert queried["type"] == FRAME_DICT
    assert queried["first_byte"] == SF_FIRST
    answered = parse_message(
        encode_list(identity=SENTINEL, dictid=DEFAULT_DICTID, sfv=DEFAULT_SFV)
    )
    assert answered["is_list"] is True and answered["is_response"] is True
    assert answered["dictid"] == DEFAULT_DICTID
    assert answered["sfv"] == DEFAULT_SFV
    packed = encode_dict(identity=SENTINEL, dictid=DEFAULT_DICTID, sfv=DEFAULT_SFV)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_dict(identity=SENTINEL, dictid=DEFAULT_DICTID, include_dictid=False)
    )
    assert bare["has_dictid"] is False
    assert bare["dictid"] == EMPTY_DICTID
    dictionary = canonical_dictionary(SENTINEL, DEFAULT_DICTID)
    assert parse_dictionary(dictionary)[0] == ("identity", (SENTINEL, ()))
    assert serialize_dictionary(parse_dictionary(dictionary)) == dictionary
    assert is_key("identity") is True
    assert is_token("BH-SF-OK") is True
    asked = parse_http_request(dict_request(SENTINEL, DEFAULT_DICTID))
    listed = parse_http_request(list_request(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV))
    got = parse_http_response(dict_response(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV))
    list_reply = parse_http_response(list_response(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV))
    assert asked["method"] == "PUT"
    assert asked["sf_kind"] == "dictionary"
    assert listed["sf_kind"] == "list"
    assert got["status"] == 200
    assert list_reply["sf_kind"] == "list"
    assert list_matches(list_reply["body"].decode("ascii"), canonical_list(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV))
    assert parse_list('1;foo=1, 2, "str"')[2] == ("str", ())
    assert parse_dictionary("a=1, b=2;foo=3, c, d=?0")[2] == ("c", (True, ()))
    assert representation_dictionary(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV).startswith("identity=")


def test_builtin_proof_seals_structuredfields_actuation() -> None:
    report = builtin_structuredfields_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "structuredfields_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_structuredfields"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_dictid_is_forbidden"]
    assert report["checks"]["skip_dict_cycle_stays_empty"]
    assert report["checks"]["skip_list_stays_empty"]
    assert report["checks"]["skip_sfv_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_dictid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_sfv"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_structuredfields"]
    assert report["checks"]["catalog_names_structuredfields"]
    assert report["checks"]["catalog_names_clienthints"]
    assert report["checks"]["leftover_text_binds_structuredfields"]
    assert report["checks"]["proved_structuredfields_consumes_leftover"]
    assert report["mission_goal"] == STRUCTUREDFIELDS_ACTUATION_GOAL
    assert report["done_when"] == STRUCTUREDFIELDS_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[STRUCTUREDFIELDS_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "structuredfields" in capability.tags
    assert "rfc8941" in capability.tags
    assert "http" in capability.tags
    assert "dictid" in capability.tags
    assert "sfv" in capability.tags


def test_selection_gate_accepts_structuredfields_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        STRUCTUREDFIELDS_ACTUATION_GOAL,
        STRUCTUREDFIELDS_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(STRUCTUREDFIELDS_ACTUATION_GOAL)
    assert "structuredfield" in family
    assert "rfc8941" in family
    assert "dictid" in family
    assert "sfv" in family
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
    assert "clienthint" not in family
    assert "rfc8942" not in family
    assert "chid" not in family
    assert "acceptch" not in family
    assert "hintsdigest" not in family
