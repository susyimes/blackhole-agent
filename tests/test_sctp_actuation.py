from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.datachannel_actuation import DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
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
from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
from blackhole_agent.sctp_actuation import (
    CHUNK_INIT,
    DEFAULT_TSN,
    DEFAULT_VTAG,
    EMPTY_VTAG,
    SENTINEL,
    SCTP_ACTUATION_DONE_WHEN,
    SCTP_ACTUATION_GOAL,
    SCTP_ACTUATION_ID,
    builtin_sctp_actuation_proof,
    crc32c,
    encode_init,
    encode_init_ack,
    independent_sctp_digest,
    parse_message,
    run_sctp_workflow,
)
from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.srtp_actuation import SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID
from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    SCTP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    sctp_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

NEIGHBORS = (
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
    DATACHANNEL_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    DATACHANNEL_ACTUATION_ID,
)


def test_goal_binds_sctp_actuation_plane() -> None:
    assert leftover_marker_ids(SCTP_ACTUATION_GOAL) == (SCTP_ACTUATION_ID,)
    assert SCTP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(DATACHANNEL_ACTUATION_GOAL) == (DATACHANNEL_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert SCTP_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    sctp_signature = semantic_signature(SCTP_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(sctp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_sctp_tool_completes_init_init_ack_poll() -> None:
    descriptor = sctp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SCTP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("sctp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SCTP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["sctp"]

    missing = run_sctp_workflow(with_vtag=False)
    skip_bind = run_sctp_workflow(skip_bind=True)
    skip_init = run_sctp_workflow(do_init=False)
    skip_init_ack = run_sctp_workflow(do_init_ack=False)
    skip_tsn = run_sctp_workflow(do_tsn=False)
    skip_replay = run_sctp_workflow(replay=False)
    skip_vtag = run_sctp_workflow(use_vtag=False)
    live = run_sctp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_vtag"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_init["ok"] is False
    assert skip_init["error"] == "init_required"
    assert skip_init_ack["ok"] is False
    assert skip_init_ack["error"] == "init_ack_required"
    assert skip_tsn["ok"] is False
    assert skip_tsn["error"] == "tsn_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_vtag["ok"] is False
    assert skip_vtag["error"] == "vtag_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_sctp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["init"] is True
    assert row["init_ack"] is True
    assert row["tsn_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["vtag_bound"] is True
    assert row["digest"]
    assert live["vtag"] == DEFAULT_VTAG
    assert live["tsn"] == DEFAULT_TSN
    assert int(live["port"]) > 0
    init = parse_message(encode_init(identity=SENTINEL, vtag=DEFAULT_VTAG, tsn=DEFAULT_TSN))
    assert init["is_init"] is True and init["is_response"] is False
    assert init["identity"] == SENTINEL and init["vtag"] == DEFAULT_VTAG
    assert init["tsn"] == DEFAULT_TSN
    assert init["type"] == CHUNK_INIT
    assert init["header_vtag"] == EMPTY_VTAG
    init_ack = parse_message(
        encode_init_ack(identity=SENTINEL, vtag=DEFAULT_VTAG, tsn=DEFAULT_TSN)
    )
    assert init_ack["is_init_ack"] is True and init_ack["is_response"] is True
    assert init_ack["vtag"] == DEFAULT_VTAG
    assert init_ack["tsn"] == DEFAULT_TSN
    packed = encode_init(identity=SENTINEL, vtag=DEFAULT_VTAG, tsn=DEFAULT_TSN)
    zeroed = packed[:8] + (0).to_bytes(4, "big") + packed[12:]
    assert crc32c(zeroed) == int.from_bytes(packed[8:12], "big")
    bare = parse_message(encode_init(identity=SENTINEL, vtag=DEFAULT_VTAG, include_vtag=False))
    assert bare["has_vtag"] is False


def test_builtin_proof_seals_sctp_actuation() -> None:
    report = builtin_sctp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "sctp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_sctp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_vtag_is_forbidden"]
    assert report["checks"]["skip_init_stays_empty"]
    assert report["checks"]["skip_init_ack_stays_empty"]
    assert report["checks"]["skip_tsn_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_vtag_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_tsn"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_sctp"]
    assert report["checks"]["catalog_names_datachannel"]
    assert report["mission_goal"] == SCTP_ACTUATION_GOAL
    assert report["done_when"] == SCTP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[SCTP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "sctp" in capability.tags
    assert "rfc4960" in capability.tags
    assert "udp" in capability.tags
    assert "vtag" in capability.tags
    assert "tsn" in capability.tags


def test_selection_gate_accepts_sctp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        SCTP_ACTUATION_GOAL,
        SCTP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(SCTP_ACTUATION_GOAL)
    assert "sctp" in family
    assert "rfc4960" in family
    assert "vtag" in family
    assert "tsn" in family
    assert "srtp" not in family
    assert "rfc3711" not in family
    assert "datachannel" not in family
    assert "rfc8831" not in family
    assert "ppid" not in family
