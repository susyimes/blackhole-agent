from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.ice_actuation import (
    DEFAULT_FOUNDATION,
    DEFAULT_UFRAG,
    HOST_PRIORITY,
    SENTINEL,
    ICE_ACTUATION_DONE_WHEN,
    ICE_ACTUATION_GOAL,
    ICE_ACTUATION_ID,
    builtin_ice_actuation_proof,
    encode_check,
    encode_nominate,
    encode_success,
    independent_ice_digest,
    parse_message,
    run_ice_workflow,
)
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
    ICE_TOOL_PROVIDER,
    build_tool_routing_preflight,
    ice_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

NEIGHBORS = (
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
    DTLS_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    DTLS_ACTUATION_ID,
)


def test_goal_binds_ice_actuation_plane() -> None:
    assert leftover_marker_ids(ICE_ACTUATION_GOAL) == (ICE_ACTUATION_ID,)
    assert ICE_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(DTLS_ACTUATION_GOAL) == (DTLS_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert ICE_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    ice_signature = semantic_signature(ICE_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(ice_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_ice_tool_completes_check_nominate_poll() -> None:
    descriptor = ice_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICE_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("ice",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICE_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["ice"]

    missing = run_ice_workflow(with_ufrag=False)
    skip_bind = run_ice_workflow(skip_bind=True)
    skip_check = run_ice_workflow(do_check=False)
    skip_nominate = run_ice_workflow(do_nominate=False)
    skip_success = run_ice_workflow(do_success=False)
    skip_replay = run_ice_workflow(replay=False)
    skip_ufrag = run_ice_workflow(use_ufrag=False)
    live = run_ice_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_ufrag"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_check["ok"] is False
    assert skip_check["error"] == "check_required"
    assert skip_nominate["ok"] is False
    assert skip_nominate["error"] == "nominate_required"
    assert skip_success["ok"] is False
    assert skip_success["error"] == "success_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_ufrag["ok"] is False
    assert skip_ufrag["error"] == "ufrag_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_ice_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["check"] is True
    assert row["nominate"] is True
    assert row["success_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["ufrag_bound"] is True
    assert row["digest"]
    assert live["ufrag"] == DEFAULT_UFRAG
    assert live["foundation"] == DEFAULT_FOUNDATION
    assert int(live["port"]) > 0
    check = parse_message(
        encode_check(identity=SENTINEL, ufrag=DEFAULT_UFRAG, foundation=DEFAULT_FOUNDATION)
    )
    assert check["is_check"] is True and check["is_response"] is False
    assert check["identity"] == SENTINEL and check["ufrag"] == DEFAULT_UFRAG
    assert check["foundation"] == DEFAULT_FOUNDATION
    assert check["priority"] == HOST_PRIORITY
    nominate = parse_message(
        encode_nominate(identity=SENTINEL, ufrag=DEFAULT_UFRAG, foundation=DEFAULT_FOUNDATION)
    )
    assert nominate["is_nominate"] is True and nominate["use_candidate"] is True
    response = parse_message(
        encode_success(
            identity=SENTINEL,
            ufrag=DEFAULT_UFRAG,
            foundation=DEFAULT_FOUNDATION,
            mapped_port=3478,
        )
    )
    assert response["is_success"] is True and response["is_response"] is True
    assert response["ufrag"] == DEFAULT_UFRAG
    assert response["foundation"] == DEFAULT_FOUNDATION
    assert response["mapped_port"] == 3478
    bare = parse_message(
        encode_check(identity=SENTINEL, ufrag=DEFAULT_UFRAG, include_ufrag=False)
    )
    assert bare["has_ufrag"] is False


def test_builtin_proof_seals_ice_actuation() -> None:
    report = builtin_ice_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "ice_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_ice"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_ufrag_is_forbidden"]
    assert report["checks"]["skip_check_stays_empty"]
    assert report["checks"]["skip_nominate_stays_empty"]
    assert report["checks"]["skip_success_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_ufrag_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_ufrag"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_ice"]
    assert report["checks"]["catalog_names_dtls"]
    assert report["mission_goal"] == ICE_ACTUATION_GOAL
    assert report["done_when"] == ICE_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[ICE_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "ice" in capability.tags
    assert "rfc8445" in capability.tags
    assert "udp" in capability.tags
    assert "ufrag" in capability.tags
    assert "foundation" in capability.tags


def test_selection_gate_accepts_ice_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        ICE_ACTUATION_GOAL,
        ICE_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(ICE_ACTUATION_GOAL)
    assert "ice" in family
    assert "rfc8445" in family
    assert "ufrag" in family
    assert "foundation" in family
    assert "turn" not in family
    assert "rfc5766" not in family
    assert "dtls" not in family
    assert "rfc6347" not in family
    assert "cookie" not in family
