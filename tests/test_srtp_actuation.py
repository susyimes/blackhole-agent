from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
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
from blackhole_agent.sctp_actuation import SCTP_ACTUATION_GOAL, SCTP_ACTUATION_ID
from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.srtp_actuation import (
    DEFAULT_ROC,
    DEFAULT_SSRC,
    SENTINEL,
    VERSION_RTP,
    SRTP_ACTUATION_DONE_WHEN,
    SRTP_ACTUATION_GOAL,
    SRTP_ACTUATION_ID,
    builtin_srtp_actuation_proof,
    encode_protect,
    encode_unprotect,
    independent_srtp_digest,
    parse_message,
    run_srtp_workflow,
)
from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    SRTP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    srtp_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

NEIGHBORS = (
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
    SCTP_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    SCTP_ACTUATION_ID,
)


def test_goal_binds_srtp_actuation_plane() -> None:
    assert leftover_marker_ids(SRTP_ACTUATION_GOAL) == (SRTP_ACTUATION_ID,)
    assert SRTP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(SCTP_ACTUATION_GOAL) == (SCTP_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert SRTP_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    srtp_signature = semantic_signature(SRTP_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(srtp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_srtp_tool_completes_protect_unprotect_poll() -> None:
    descriptor = srtp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SRTP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("srtp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SRTP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["srtp"]

    missing = run_srtp_workflow(with_ssrc=False)
    skip_bind = run_srtp_workflow(skip_bind=True)
    skip_protect = run_srtp_workflow(do_protect=False)
    skip_unprotect = run_srtp_workflow(do_unprotect=False)
    skip_roc = run_srtp_workflow(do_roc=False)
    skip_replay = run_srtp_workflow(replay=False)
    skip_ssrc = run_srtp_workflow(use_ssrc=False)
    live = run_srtp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_ssrc"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_protect["ok"] is False
    assert skip_protect["error"] == "protect_required"
    assert skip_unprotect["ok"] is False
    assert skip_unprotect["error"] == "unprotect_required"
    assert skip_roc["ok"] is False
    assert skip_roc["error"] == "roc_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_ssrc["ok"] is False
    assert skip_ssrc["error"] == "ssrc_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_srtp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["protect"] is True
    assert row["unprotect"] is True
    assert row["roc_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["ssrc_bound"] is True
    assert row["digest"]
    assert live["ssrc"] == DEFAULT_SSRC
    assert live["roc"] == DEFAULT_ROC
    assert int(live["port"]) > 0
    protect = parse_message(encode_protect(identity=SENTINEL, ssrc=DEFAULT_SSRC, roc=DEFAULT_ROC))
    assert protect["is_protect"] is True and protect["is_response"] is False
    assert protect["identity"] == SENTINEL and protect["ssrc"] == DEFAULT_SSRC
    assert protect["roc"] == DEFAULT_ROC
    assert protect["version"] == VERSION_RTP
    unprotect = parse_message(
        encode_unprotect(identity=SENTINEL, ssrc=DEFAULT_SSRC, roc=DEFAULT_ROC)
    )
    assert unprotect["is_unprotect"] is True and unprotect["is_response"] is True
    assert unprotect["ssrc"] == DEFAULT_SSRC
    assert unprotect["roc"] == DEFAULT_ROC
    packed = encode_protect(identity=SENTINEL, ssrc=DEFAULT_SSRC, roc=DEFAULT_ROC)
    assert packed[0] >> 6 == VERSION_RTP
    bare = parse_message(encode_protect(identity=SENTINEL, ssrc=DEFAULT_SSRC, include_ssrc=False))
    assert bare["has_ssrc"] is False


def test_builtin_proof_seals_srtp_actuation() -> None:
    report = builtin_srtp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "srtp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_srtp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_ssrc_is_forbidden"]
    assert report["checks"]["skip_protect_stays_empty"]
    assert report["checks"]["skip_unprotect_stays_empty"]
    assert report["checks"]["skip_roc_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_ssrc_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_roc"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_srtp"]
    assert report["checks"]["catalog_names_sctp"]
    assert report["mission_goal"] == SRTP_ACTUATION_GOAL
    assert report["done_when"] == SRTP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[SRTP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "srtp" in capability.tags
    assert "rfc3711" in capability.tags
    assert "udp" in capability.tags
    assert "ssrc" in capability.tags
    assert "roc" in capability.tags


def test_selection_gate_accepts_srtp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        SRTP_ACTUATION_GOAL,
        SRTP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(SRTP_ACTUATION_GOAL)
    assert "srtp" in family
    assert "rfc3711" in family
    assert "ssrc" in family
    assert "roc" in family
    assert "dtls" not in family
    assert "rfc6347" not in family
    assert "sctp" not in family
    assert "rfc4960" not in family
    assert "vtag" not in family
