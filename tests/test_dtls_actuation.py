from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import (
    CONTENT_HANDSHAKE,
    DEFAULT_COOKIE,
    DEFAULT_EPOCH,
    DEFAULT_VERIFY,
    SENTINEL,
    VERSION_DTLS12,
    DTLS_ACTUATION_DONE_WHEN,
    DTLS_ACTUATION_GOAL,
    DTLS_ACTUATION_ID,
    builtin_dtls_actuation_proof,
    encode_finished,
    encode_hello,
    independent_dtls_digest,
    parse_message,
    run_dtls_workflow,
)
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
from blackhole_agent.srtp_actuation import SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID
from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    DTLS_TOOL_PROVIDER,
    build_tool_routing_preflight,
    dtls_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

NEIGHBORS = (
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
    SRTP_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    SRTP_ACTUATION_ID,
)


def test_goal_binds_dtls_actuation_plane() -> None:
    assert leftover_marker_ids(DTLS_ACTUATION_GOAL) == (DTLS_ACTUATION_ID,)
    assert DTLS_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(SRTP_ACTUATION_GOAL) == (SRTP_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert DTLS_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    dtls_signature = semantic_signature(DTLS_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(dtls_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_dtls_tool_completes_hello_finished_poll() -> None:
    descriptor = dtls_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DTLS_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("dtls",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DTLS_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["dtls"]

    missing = run_dtls_workflow(with_cookie=False)
    skip_bind = run_dtls_workflow(skip_bind=True)
    skip_hello = run_dtls_workflow(do_hello=False)
    skip_finished = run_dtls_workflow(do_finished=False)
    skip_verify = run_dtls_workflow(do_verify=False)
    skip_replay = run_dtls_workflow(replay=False)
    skip_cookie = run_dtls_workflow(use_cookie=False)
    live = run_dtls_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_cookie"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_hello["ok"] is False
    assert skip_hello["error"] == "hello_required"
    assert skip_finished["ok"] is False
    assert skip_finished["error"] == "finished_required"
    assert skip_verify["ok"] is False
    assert skip_verify["error"] == "verify_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_cookie["ok"] is False
    assert skip_cookie["error"] == "cookie_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_dtls_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["hello"] is True
    assert row["finished"] is True
    assert row["verify_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["cookie_bound"] is True
    assert row["digest"]
    assert live["cookie"] == DEFAULT_COOKIE
    assert live["verify"] == DEFAULT_VERIFY
    assert live["epoch"] == DEFAULT_EPOCH
    assert int(live["port"]) > 0
    hello = parse_message(encode_hello(identity=SENTINEL, cookie=DEFAULT_COOKIE))
    assert hello["is_hello"] is True and hello["is_response"] is False
    assert hello["identity"] == SENTINEL and hello["cookie"] == DEFAULT_COOKIE
    assert hello["epoch"] == DEFAULT_EPOCH
    assert hello["content_type"] == CONTENT_HANDSHAKE
    assert hello["version"] == VERSION_DTLS12
    finished = parse_message(
        encode_finished(identity=SENTINEL, cookie=DEFAULT_COOKIE, verify=DEFAULT_VERIFY)
    )
    assert finished["is_finished"] is True and finished["is_response"] is True
    assert finished["cookie"] == DEFAULT_COOKIE
    assert finished["verify"] == DEFAULT_VERIFY
    packed = encode_hello(identity=SENTINEL, cookie=DEFAULT_COOKIE)
    assert packed[0] == CONTENT_HANDSHAKE
    assert packed[1:3] == VERSION_DTLS12.to_bytes(2, "big")
    bare = parse_message(encode_hello(identity=SENTINEL, cookie=DEFAULT_COOKIE, include_cookie=False))
    assert bare["has_cookie"] is False


def test_builtin_proof_seals_dtls_actuation() -> None:
    report = builtin_dtls_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "dtls_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_dtls"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_cookie_is_forbidden"]
    assert report["checks"]["skip_hello_stays_empty"]
    assert report["checks"]["skip_finished_stays_empty"]
    assert report["checks"]["skip_verify_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_cookie_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_cookie"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_dtls"]
    assert report["checks"]["catalog_names_srtp"]
    assert report["mission_goal"] == DTLS_ACTUATION_GOAL
    assert report["done_when"] == DTLS_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[DTLS_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "dtls" in capability.tags
    assert "rfc6347" in capability.tags
    assert "udp" in capability.tags
    assert "cookie" in capability.tags
    assert "epoch" in capability.tags


def test_selection_gate_accepts_dtls_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        DTLS_ACTUATION_GOAL,
        DTLS_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(DTLS_ACTUATION_GOAL)
    assert "dtls" in family
    assert "rfc6347" in family
    assert "cookie" in family
    assert "epoch" in family
    assert "ice" not in family
    assert "rfc8445" not in family
    assert "srtp" not in family
    assert "rfc3711" not in family
    assert "roc" not in family
