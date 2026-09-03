from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.datachannel_actuation import (
    CHUNK_DATA,
    DATACHANNEL_ACTUATION_DONE_WHEN,
    DATACHANNEL_ACTUATION_GOAL,
    DATACHANNEL_ACTUATION_ID,
    DEFAULT_DCEP,
    DEFAULT_PPID,
    DCEP_OPEN,
    EMPTY_PPID,
    SENTINEL,
    builtin_datachannel_actuation_proof,
    crc32c,
    encode_ack,
    encode_open,
    independent_datachannel_digest,
    parse_message,
    run_datachannel_workflow,
)
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
    DATACHANNEL_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    build_tool_routing_preflight,
    datachannel_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

NEIGHBORS = (
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
    QUIC_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    QUIC_ACTUATION_ID,
)


def test_goal_binds_datachannel_actuation_plane() -> None:
    assert leftover_marker_ids(DATACHANNEL_ACTUATION_GOAL) == (DATACHANNEL_ACTUATION_ID,)
    assert DATACHANNEL_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(QUIC_ACTUATION_GOAL) == (QUIC_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert DATACHANNEL_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(DATACHANNEL_ACTUATION_GOAL)
    datachannel_signature = semantic_signature(DATACHANNEL_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(datachannel_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_datachannel_tool_completes_open_ack_poll() -> None:
    descriptor = datachannel_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DATACHANNEL_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("datachannel",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DATACHANNEL_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["datachannel"]

    missing = run_datachannel_workflow(with_ppid=False)
    skip_bind = run_datachannel_workflow(skip_bind=True)
    skip_open = run_datachannel_workflow(do_open=False)
    skip_ack = run_datachannel_workflow(do_ack=False)
    skip_dcep = run_datachannel_workflow(do_dcep=False)
    skip_replay = run_datachannel_workflow(replay=False)
    skip_ppid = run_datachannel_workflow(use_ppid=False)
    live = run_datachannel_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_ppid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_open["ok"] is False
    assert skip_open["error"] == "open_required"
    assert skip_ack["ok"] is False
    assert skip_ack["error"] == "ack_required"
    assert skip_dcep["ok"] is False
    assert skip_dcep["error"] == "dcep_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_ppid["ok"] is False
    assert skip_ppid["error"] == "ppid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_datachannel_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["open"] is True
    assert row["ack"] is True
    assert row["dcep_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["ppid_bound"] is True
    assert row["digest"]
    assert live["ppid"] == DEFAULT_PPID
    assert live["dcep"] == DEFAULT_DCEP
    assert int(live["port"]) > 0
    opened = parse_message(encode_open(identity=SENTINEL, ppid=DEFAULT_PPID, dcep=DEFAULT_DCEP))
    assert opened["is_open"] is True and opened["is_response"] is False
    assert opened["identity"] == SENTINEL and opened["ppid"] == DEFAULT_PPID
    assert opened["dcep"] == DEFAULT_DCEP
    assert opened["type"] == DCEP_OPEN
    assert opened["chunk_type"] == CHUNK_DATA
    ack = parse_message(encode_ack(identity=SENTINEL, ppid=DEFAULT_PPID, dcep=DEFAULT_DCEP))
    assert ack["is_ack"] is True and ack["is_response"] is True
    assert ack["ppid"] == DEFAULT_PPID
    assert ack["dcep"] == DEFAULT_DCEP
    packed = encode_open(identity=SENTINEL, ppid=DEFAULT_PPID, dcep=DEFAULT_DCEP)
    zeroed = packed[:8] + (0).to_bytes(4, "big") + packed[12:]
    assert crc32c(zeroed) == int.from_bytes(packed[8:12], "big")
    bare = parse_message(encode_open(identity=SENTINEL, ppid=DEFAULT_PPID, include_ppid=False))
    assert bare["has_ppid"] is False
    assert bare["ppid"] == EMPTY_PPID


def test_builtin_proof_seals_datachannel_actuation() -> None:
    report = builtin_datachannel_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "datachannel_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_datachannel"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_ppid_is_forbidden"]
    assert report["checks"]["skip_open_stays_empty"]
    assert report["checks"]["skip_ack_stays_empty"]
    assert report["checks"]["skip_dcep_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_ppid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_dcep"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_datachannel"]
    assert report["checks"]["catalog_names_quic"]
    assert report["mission_goal"] == DATACHANNEL_ACTUATION_GOAL
    assert report["done_when"] == DATACHANNEL_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[DATACHANNEL_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "datachannel" in capability.tags
    assert "rfc8831" in capability.tags
    assert "sctp" in capability.tags
    assert "ppid" in capability.tags
    assert "dcep" in capability.tags


def test_selection_gate_accepts_datachannel_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        DATACHANNEL_ACTUATION_GOAL,
        DATACHANNEL_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(DATACHANNEL_ACTUATION_GOAL)
    assert "datachannel" in family
    assert "rfc8831" in family
    assert "ppid" in family
    assert "dcep" in family
    assert "rfc4960" not in family
    assert "vtag" not in family
    assert "quic" not in family
    assert "rfc9000" not in family
    assert "dcid" not in family
