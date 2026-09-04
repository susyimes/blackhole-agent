from pathlib import Path

from blackhole_agent.encryptedcontent_actuation import (
    ENCRYPTEDCONTENT_ACTUATION_GOAL,
    ENCRYPTEDCONTENT_ACTUATION_ID,
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
from blackhole_agent.earlyhints_actuation import (
    DEFAULT_LINKS,
    HINT_LINKS,
    DEFAULT_LINKID,
    DEFAULT_EARLYDIGEST,
    EMPTY_LINKID,
    FRAME_LINK,
    FRAME_HINT,
    EARLYHINTS_ACTUATION_DONE_WHEN,
    EARLYHINTS_ACTUATION_GOAL,
    EARLYHINTS_ACTUATION_ID,
    EARLYHINTS_LEFTOVER,
    EH_FIRST,
    SENTINEL,
    link_request,
    link_response,
    builtin_earlyhints_actuation_proof,
    canonical_link,
    canonical_hint,
    crc32c,
    hint_request,
    hint_response,
    encode_link,
    encode_hint,
    independent_earlyhints_digest,
    is_token,
    parse_http_request,
    parse_http_response,
    parse_message,
    parse_link_list,
    run_earlyhints_workflow,
    serialize_link_list,
    link_list_matches,
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
    EARLYHINTS_TOOL_PROVIDER,
    build_tool_routing_preflight,
    earlyhints_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
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
    ENCRYPTEDCONTENT_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    ENCRYPTEDCONTENT_ACTUATION_ID,
)


def test_goal_binds_earlyhints_actuation_plane() -> None:
    assert leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL) == (EARLYHINTS_ACTUATION_ID,)
    assert leftover_marker_ids(EARLYHINTS_LEFTOVER) == (EARLYHINTS_ACTUATION_ID,)
    assert EARLYHINTS_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(ENCRYPTEDCONTENT_ACTUATION_GOAL) == (ENCRYPTEDCONTENT_ACTUATION_ID,)
    assert leftover_marker_ids(CLIENTHINTS_ACTUATION_GOAL) == (CLIENTHINTS_ACTUATION_ID,)
    assert leftover_marker_ids(STRUCTUREDFIELDS_ACTUATION_GOAL) == (STRUCTUREDFIELDS_ACTUATION_ID,)
    assert ENCRYPTEDCONTENT_ACTUATION_ID in LOCAL_DENYLIST
    assert CLIENTHINTS_ACTUATION_ID in LOCAL_DENYLIST
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert EARLYHINTS_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(EARLYHINTS_ACTUATION_GOAL)
    earlyhints_signature = semantic_signature(EARLYHINTS_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(earlyhints_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_earlyhints_tool_completes_link_hint_poll() -> None:
    descriptor = earlyhints_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EARLYHINTS_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("earlyhints",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EARLYHINTS_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["earlyhints"]

    missing = run_earlyhints_workflow(with_linkid=False)
    skip_bind = run_earlyhints_workflow(skip_bind=True)
    skip_link = run_earlyhints_workflow(do_link=False)
    skip_hint = run_earlyhints_workflow(do_hint=False)
    skip_earlydigest = run_earlyhints_workflow(do_earlydigest=False)
    skip_replay = run_earlyhints_workflow(replay=False)
    skip_linkid = run_earlyhints_workflow(use_linkid=False)
    live = run_earlyhints_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_linkid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_link["ok"] is False
    assert skip_link["error"] == "link_required"
    assert skip_hint["ok"] is False
    assert skip_hint["error"] == "hint_required"
    assert skip_earlydigest["ok"] is False
    assert skip_earlydigest["error"] == "earlydigest_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_linkid["ok"] is False
    assert skip_linkid["error"] == "linkid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_earlyhints_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["link_frame"] is True
    assert row["hint"] is True
    assert row["earlydigest_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["linkid_bound"] is True
    assert row["digest"]
    assert live["linkid"] == DEFAULT_LINKID
    assert live["earlydigest"] == DEFAULT_EARLYDIGEST
    assert int(live["port"]) > 0
    queried = parse_message(
        encode_link(identity=SENTINEL, linkid=DEFAULT_LINKID, earlydigest=DEFAULT_EARLYDIGEST)
    )
    assert queried["is_link"] is True and queried["is_response"] is False
    assert queried["identity"] == SENTINEL and queried["linkid"] == DEFAULT_LINKID
    assert queried["earlydigest"] == DEFAULT_EARLYDIGEST
    assert queried["type"] == FRAME_LINK
    assert queried["first_byte"] == EH_FIRST
    answered = parse_message(
        encode_hint(identity=SENTINEL, linkid=DEFAULT_LINKID, earlydigest=DEFAULT_EARLYDIGEST)
    )
    assert answered["is_hint"] is True and answered["is_response"] is True
    assert answered["linkid"] == DEFAULT_LINKID
    assert answered["earlydigest"] == DEFAULT_EARLYDIGEST
    packed = encode_link(identity=SENTINEL, linkid=DEFAULT_LINKID, earlydigest=DEFAULT_EARLYDIGEST)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_link(identity=SENTINEL, linkid=DEFAULT_LINKID, include_linkid=False)
    )
    assert bare["has_linkid"] is False
    assert bare["linkid"] == EMPTY_LINKID
    advertised = serialize_link_list(DEFAULT_LINKS)
    assert parse_link_list(advertised) == DEFAULT_LINKS
    assert serialize_link_list(parse_link_list(advertised)) == advertised
    assert is_token("preload") is True
    assert is_token("BH-EH-OK") is True
    asked = parse_http_request(link_request(SENTINEL, DEFAULT_LINKID))
    listed = parse_http_request(hint_request(SENTINEL, DEFAULT_LINKID, DEFAULT_EARLYDIGEST))
    got = parse_http_response(link_response(SENTINEL, DEFAULT_LINKID, DEFAULT_EARLYDIGEST))
    hint_reply = parse_http_response(hint_response(SENTINEL, DEFAULT_LINKID, DEFAULT_EARLYDIGEST))
    assert asked["method"] == "GET"
    assert asked["eh_kind"] == "link"
    assert listed["eh_kind"] == "hint"
    assert got["status"] == 103
    assert hint_reply["hint_links"] == HINT_LINKS
    assert link_list_matches(serialize_link_list(got["links"]), advertised)
    assert parse_link_list(
        "</style.css>; rel=preload; as=style, </script.js>; rel=preload; as=script"
    ) == DEFAULT_LINKS
    assert canonical_link(SENTINEL, DEFAULT_LINKID).startswith("</style.css>")
    assert "linkid=" in canonical_hint(SENTINEL, DEFAULT_LINKID, DEFAULT_EARLYDIGEST)


def test_builtin_proof_seals_earlyhints_actuation() -> None:
    report = builtin_earlyhints_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "earlyhints_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_earlyhints"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_linkid_is_forbidden"]
    assert report["checks"]["skip_link_stays_empty"]
    assert report["checks"]["skip_hint_stays_empty"]
    assert report["checks"]["skip_earlydigest_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_linkid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_earlydigest"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_earlyhints"]
    assert report["checks"]["catalog_names_earlyhints"]
    assert report["checks"]["catalog_names_encryptedcontent"]
    assert report["checks"]["leftover_text_binds_earlyhints"]
    assert report["checks"]["proved_earlyhints_consumes_leftover"]
    assert report["mission_goal"] == EARLYHINTS_ACTUATION_GOAL
    assert report["done_when"] == EARLYHINTS_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[EARLYHINTS_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "earlyhints" in capability.tags
    assert "rfc8297" in capability.tags
    assert "http" in capability.tags
    assert "linkid" in capability.tags
    assert "earlydigest" in capability.tags


def test_selection_gate_accepts_earlyhints_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        EARLYHINTS_ACTUATION_GOAL,
        EARLYHINTS_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(EARLYHINTS_ACTUATION_GOAL)
    assert "earlyhint" in family
    assert "rfc8297" in family
    assert "linkid" in family
    assert "earlydigest" in family
    assert "clienthint" not in family
    assert "rfc8942" not in family
    assert "chid" not in family
    assert "encryptedcontent" not in family
    assert "rfc8188" not in family
    assert "encid" not in family
    assert "ecedigest" not in family
    assert "rfc9000" not in family
    assert "http3" not in family
    assert "structuredfield" not in family
    assert "rfc8941" not in family
    assert "dictid" not in family
    assert "sfv" not in family
