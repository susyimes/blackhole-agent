from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
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
from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    TURN_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    turn_tool_descriptor,
)
from blackhole_agent.turn_actuation import (
    DEFAULT_NONCE,
    DEFAULT_NONCE_HEX,
    SENTINEL,
    TURN_ACTUATION_DONE_WHEN,
    TURN_ACTUATION_GOAL,
    TURN_ACTUATION_ID,
    builtin_turn_actuation_proof,
    encode_allocate,
    encode_success,
    independent_turn_digest,
    parse_message,
    run_turn_workflow,
)

NEIGHBORS = (
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
    ICE_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    ICE_ACTUATION_ID,
)


def test_goal_binds_turn_actuation_plane() -> None:
    assert leftover_marker_ids(TURN_ACTUATION_GOAL) == (TURN_ACTUATION_ID,)
    assert TURN_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(ICE_ACTUATION_GOAL) == (ICE_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert TURN_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    turn_signature = semantic_signature(TURN_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(turn_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_turn_tool_completes_allocate_success_poll() -> None:
    descriptor = turn_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TURN_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("turn",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TURN_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["turn"]

    missing = run_turn_workflow(with_nonce=False)
    skip_bind = run_turn_workflow(skip_bind=True)
    skip_allocate = run_turn_workflow(do_allocate=False)
    skip_success = run_turn_workflow(do_success=False)
    skip_replay = run_turn_workflow(replay=False)
    skip_nonce = run_turn_workflow(use_nonce=False)
    live = run_turn_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_nonce"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_allocate["ok"] is False
    assert skip_allocate["error"] == "allocate_required"
    assert skip_success["ok"] is False
    assert skip_success["error"] == "success_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_nonce["ok"] is False
    assert skip_nonce["error"] == "nonce_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_turn_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["allocate"] is True
    assert row["success_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["nonce_bound"] is True
    assert row["digest"]
    assert live["nonce"] == DEFAULT_NONCE_HEX
    assert int(live["port"]) > 0
    allocate = parse_message(encode_allocate(identity=SENTINEL, nonce=DEFAULT_NONCE))
    assert allocate["is_allocate"] is True and allocate["is_response"] is False
    assert allocate["identity"] == SENTINEL and allocate["nonce"] == DEFAULT_NONCE
    response = parse_message(encode_success(identity=SENTINEL, nonce=DEFAULT_NONCE, relayed_port=49152))
    assert response["is_success"] is True and response["is_response"] is True
    assert response["nonce"] == DEFAULT_NONCE
    assert response["relayed_port"] == 49152
    bare = parse_message(
        encode_allocate(identity=SENTINEL, nonce=DEFAULT_NONCE, include_nonce=False)
    )
    assert bare["has_nonce"] is False


def test_builtin_proof_seals_turn_actuation() -> None:
    report = builtin_turn_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "turn_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_turn"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_nonce_is_forbidden"]
    assert report["checks"]["skip_allocate_stays_empty"]
    assert report["checks"]["skip_success_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_nonce_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_nonce"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_turn"]
    assert report["checks"]["catalog_names_ice"]
    assert report["mission_goal"] == TURN_ACTUATION_GOAL
    assert report["done_when"] == TURN_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[TURN_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "turn" in capability.tags
    assert "rfc5766" in capability.tags
    assert "udp" in capability.tags
    assert "nonce" in capability.tags
    assert "relay" in capability.tags


def test_selection_gate_accepts_turn_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        TURN_ACTUATION_GOAL,
        TURN_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(TURN_ACTUATION_GOAL)
    assert "turn" in family
    assert "rfc5766" in family
    assert "relay" in family
    assert "nonce" in family
    assert "stun" not in family
    assert "rfc5389" not in family
    assert "ice" not in family
    assert "rfc8445" not in family
