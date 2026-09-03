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
from blackhole_agent.masque_actuation import MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID
from blackhole_agent.ohttp_actuation import (
    DEFAULT_CONFIGID,
    DEFAULT_GATEWAY,
    EMPTY_CONFIGID,
    FRAME_ENCAPSULATE,
    OHTTP_ACTUATION_DONE_WHEN,
    OHTTP_ACTUATION_GOAL,
    OHTTP_ACTUATION_ID,
    OHTTP_LEFTOVER,
    OH_FIRST,
    SENTINEL,
    builtin_ohttp_actuation_proof,
    crc32c,
    encode_decapsulate,
    encode_encapsulate,
    independent_ohttp_digest,
    parse_message,
    run_ohttp_workflow,
)
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
    OHTTP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    ohttp_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
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
    OHSVCB_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    OHSVCB_ACTUATION_ID,
)


def test_goal_binds_ohttp_actuation_plane() -> None:
    assert leftover_marker_ids(OHTTP_ACTUATION_GOAL) == (OHTTP_ACTUATION_ID,)
    assert leftover_marker_ids(OHTTP_LEFTOVER) == (OHTTP_ACTUATION_ID,)
    assert OHTTP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(OHSVCB_ACTUATION_GOAL) == (OHSVCB_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert OHTTP_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(OHTTP_ACTUATION_GOAL)
    ohttp_signature = semantic_signature(OHTTP_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(ohttp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_ohttp_tool_completes_encapsulate_decapsulate_poll() -> None:
    descriptor = ohttp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, OHTTP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("ohttp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, OHTTP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["ohttp"]

    missing = run_ohttp_workflow(with_configid=False)
    skip_bind = run_ohttp_workflow(skip_bind=True)
    skip_encapsulate_cycle = run_ohttp_workflow(do_encapsulate_cycle=False)
    skip_decapsulate = run_ohttp_workflow(do_decapsulate=False)
    skip_gateway = run_ohttp_workflow(do_gateway=False)
    skip_replay = run_ohttp_workflow(replay=False)
    skip_configid = run_ohttp_workflow(use_configid=False)
    live = run_ohttp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_configid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_encapsulate_cycle["ok"] is False
    assert skip_encapsulate_cycle["error"] == "encapsulate_required"
    assert skip_decapsulate["ok"] is False
    assert skip_decapsulate["error"] == "decapsulate_required"
    assert skip_gateway["ok"] is False
    assert skip_gateway["error"] == "gateway_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_configid["ok"] is False
    assert skip_configid["error"] == "configid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_ohttp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["encapsulate"] is True
    assert row["decapsulate"] is True
    assert row["gateway_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["configid_bound"] is True
    assert row["digest"]
    assert live["configid"] == DEFAULT_CONFIGID
    assert live["gateway"] == DEFAULT_GATEWAY
    assert int(live["port"]) > 0
    encapsulated = parse_message(
        encode_encapsulate(identity=SENTINEL, configid=DEFAULT_CONFIGID, gateway=DEFAULT_GATEWAY)
    )
    assert encapsulated["is_encapsulate"] is True and encapsulated["is_response"] is False
    assert encapsulated["identity"] == SENTINEL and encapsulated["configid"] == DEFAULT_CONFIGID
    assert encapsulated["gateway"] == DEFAULT_GATEWAY
    assert encapsulated["type"] == FRAME_ENCAPSULATE
    assert encapsulated["first_byte"] == OH_FIRST
    decapsulated = parse_message(
        encode_decapsulate(identity=SENTINEL, configid=DEFAULT_CONFIGID, gateway=DEFAULT_GATEWAY)
    )
    assert decapsulated["is_decapsulate"] is True and decapsulated["is_response"] is True
    assert decapsulated["configid"] == DEFAULT_CONFIGID
    assert decapsulated["gateway"] == DEFAULT_GATEWAY
    packed = encode_encapsulate(identity=SENTINEL, configid=DEFAULT_CONFIGID, gateway=DEFAULT_GATEWAY)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(
        encode_encapsulate(identity=SENTINEL, configid=DEFAULT_CONFIGID, include_configid=False)
    )
    assert bare["has_configid"] is False
    assert bare["configid"] == EMPTY_CONFIGID


def test_builtin_proof_seals_ohttp_actuation() -> None:
    report = builtin_ohttp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "ohttp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_ohttp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_configid_is_forbidden"]
    assert report["checks"]["skip_encapsulate_cycle_stays_empty"]
    assert report["checks"]["skip_decapsulate_stays_empty"]
    assert report["checks"]["skip_gateway_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_configid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_gateway"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_ohttp"]
    assert report["checks"]["catalog_names_ohttp"]
    assert report["checks"]["catalog_names_ohsvcb"]
    assert report["checks"]["leftover_text_binds_ohttp"]
    assert report["checks"]["proved_ohttp_consumes_leftover"]
    assert report["mission_goal"] == OHTTP_ACTUATION_GOAL
    assert report["done_when"] == OHTTP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[OHTTP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "ohttp" in capability.tags
    assert "rfc9458" in capability.tags
    assert "http" in capability.tags
    assert "configid" in capability.tags
    assert "gateway" in capability.tags


def test_selection_gate_accepts_ohttp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        OHTTP_ACTUATION_GOAL,
        OHTTP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(OHTTP_ACTUATION_GOAL)
    assert "ohttp" in family
    assert "rfc9458" in family
    assert "configid" in family
    assert "gateway" in family
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
    assert "ohsvcb" not in family
    assert "rfc9540" not in family
    assert "svcbid" not in family
