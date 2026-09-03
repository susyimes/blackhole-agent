from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.connectip_actuation import CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID
from blackhole_agent.datachannel_actuation import DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
from blackhole_agent.datagram_actuation import DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID
from blackhole_agent.masque_actuation import (
    DEFAULT_AUTHORITY,
    DEFAULT_TARGETID,
    EMPTY_TARGETID,
    FRAME_BIND,
    MASQUE_ACTUATION_DONE_WHEN,
    MASQUE_ACTUATION_GOAL,
    MASQUE_ACTUATION_ID,
    MASQUE_LEFTOVER,
    SENTINEL,
    MQ_FIRST,
    builtin_masque_actuation_proof,
    crc32c,
    encode_proxy,
    encode_bind,
    independent_masque_digest,
    parse_message,
    run_masque_workflow,
)
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
    MASQUE_TOOL_PROVIDER,
    build_tool_routing_preflight,
    masque_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
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
    CONNECTIP_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    CONNECTIP_ACTUATION_ID,
)


def test_goal_binds_masque_actuation_plane() -> None:
    assert leftover_marker_ids(MASQUE_ACTUATION_GOAL) == (MASQUE_ACTUATION_ID,)
    assert leftover_marker_ids(MASQUE_LEFTOVER) == (MASQUE_ACTUATION_ID,)
    assert MASQUE_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(CONNECTIP_ACTUATION_GOAL) == (CONNECTIP_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert MASQUE_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(MASQUE_ACTUATION_GOAL)
    masque_signature = semantic_signature(MASQUE_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(masque_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_masque_tool_completes_bind_proxy_poll() -> None:
    descriptor = masque_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MASQUE_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("masque",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MASQUE_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["masque"]

    missing = run_masque_workflow(with_targetid=False)
    skip_bind = run_masque_workflow(skip_bind=True)
    skip_bind_cycle = run_masque_workflow(do_bind_cycle=False)
    skip_proxy = run_masque_workflow(do_proxy=False)
    skip_authority = run_masque_workflow(do_authority=False)
    skip_replay = run_masque_workflow(replay=False)
    skip_targetid = run_masque_workflow(use_targetid=False)
    live = run_masque_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_targetid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_bind_cycle["ok"] is False
    assert skip_bind_cycle["error"] == "bind_required"
    assert skip_proxy["ok"] is False
    assert skip_proxy["error"] == "proxy_required"
    assert skip_authority["ok"] is False
    assert skip_authority["error"] == "authority_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_targetid["ok"] is False
    assert skip_targetid["error"] == "targetid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_masque_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["bind"] is True
    assert row["proxy"] is True
    assert row["authority_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["targetid_bound"] is True
    assert row["digest"]
    assert live["targetid"] == DEFAULT_TARGETID
    assert live["authority"] == DEFAULT_AUTHORITY
    assert int(live["port"]) > 0
    opened = parse_message(
        encode_bind(identity=SENTINEL, targetid=DEFAULT_TARGETID, authority=DEFAULT_AUTHORITY)
    )
    assert opened["is_bind"] is True and opened["is_response"] is False
    assert opened["identity"] == SENTINEL and opened["targetid"] == DEFAULT_TARGETID
    assert opened["authority"] == DEFAULT_AUTHORITY
    assert opened["type"] == FRAME_BIND
    assert opened["first_byte"] == MQ_FIRST
    proxied = parse_message(
        encode_proxy(identity=SENTINEL, targetid=DEFAULT_TARGETID, authority=DEFAULT_AUTHORITY)
    )
    assert proxied["is_proxy"] is True and proxied["is_response"] is True
    assert proxied["targetid"] == DEFAULT_TARGETID
    assert proxied["authority"] == DEFAULT_AUTHORITY
    packed = encode_bind(identity=SENTINEL, targetid=DEFAULT_TARGETID, authority=DEFAULT_AUTHORITY)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(encode_bind(identity=SENTINEL, targetid=DEFAULT_TARGETID, include_targetid=False))
    assert bare["has_targetid"] is False
    assert bare["targetid"] == EMPTY_TARGETID


def test_builtin_proof_seals_masque_actuation() -> None:
    report = builtin_masque_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "masque_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_masque"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_targetid_is_forbidden"]
    assert report["checks"]["skip_bind_cycle_stays_empty"]
    assert report["checks"]["skip_proxy_stays_empty"]
    assert report["checks"]["skip_authority_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_targetid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_authority"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_masque"]
    assert report["checks"]["catalog_names_connectip"]
    assert report["checks"]["leftover_text_binds_masque"]
    assert report["checks"]["proved_masque_consumes_leftover"]
    assert report["mission_goal"] == MASQUE_ACTUATION_GOAL
    assert report["done_when"] == MASQUE_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MASQUE_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "masque" in capability.tags
    assert "rfc9298" in capability.tags
    assert "http" in capability.tags
    assert "targetid" in capability.tags
    assert "authority" in capability.tags


def test_selection_gate_accepts_masque_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MASQUE_ACTUATION_GOAL,
        MASQUE_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MASQUE_ACTUATION_GOAL)
    assert "masque" in family
    assert "rfc9298" in family
    assert "targetid" in family
    assert "authority" in family
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
    assert "connectip" not in family
    assert "rfc9484" not in family
    assert "prefixid" not in family
