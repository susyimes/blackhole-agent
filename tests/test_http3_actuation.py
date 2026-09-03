from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.datachannel_actuation import DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.http3_actuation import (
    DEFAULT_QPACK,
    DEFAULT_STREAMID,
    EMPTY_STREAMID,
    FRAME_SETTINGS,
    HTTP3_ACTUATION_DONE_WHEN,
    HTTP3_ACTUATION_GOAL,
    HTTP3_ACTUATION_ID,
    HTTP3_LEFTOVER,
    SENTINEL,
    STREAM_FIRST,
    builtin_http3_actuation_proof,
    crc32c,
    encode_headers,
    encode_settings,
    independent_http3_digest,
    parse_message,
    run_http3_workflow,
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
    HTTP3_TOOL_PROVIDER,
    build_tool_routing_preflight,
    http3_tool_descriptor,
    route_tool_descriptor,
)
from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
from blackhole_agent.webtransport_actuation import (
    WEBTRANSPORT_ACTUATION_GOAL,
    WEBTRANSPORT_ACTUATION_ID,
)

NEIGHBORS = (
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
    WEBTRANSPORT_ACTUATION_GOAL,
)
NEIGHBOR_IDS = (
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
    WEBTRANSPORT_ACTUATION_ID,
)


def test_goal_binds_http3_actuation_plane() -> None:
    assert leftover_marker_ids(HTTP3_ACTUATION_GOAL) == (HTTP3_ACTUATION_ID,)
    assert leftover_marker_ids(HTTP3_LEFTOVER) == (HTTP3_ACTUATION_ID,)
    assert HTTP3_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(WEBTRANSPORT_ACTUATION_GOAL) == (WEBTRANSPORT_ACTUATION_ID,)
    for goal, capability_id in zip(NEIGHBORS, NEIGHBOR_IDS, strict=True):
        assert leftover_marker_ids(goal) == (capability_id,)
        assert HTTP3_ACTUATION_ID not in leftover_marker_ids(goal)
        assert capability_id not in leftover_marker_ids(HTTP3_ACTUATION_GOAL)
    http3_signature = semantic_signature(HTTP3_ACTUATION_GOAL)
    for neighbor in NEIGHBORS:
        assert semantic_similarity(http3_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_http3_tool_completes_settings_headers_poll() -> None:
    descriptor = http3_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP3_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("http3",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTP3_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["http3"]

    missing = run_http3_workflow(with_streamid=False)
    skip_bind = run_http3_workflow(skip_bind=True)
    skip_settings = run_http3_workflow(do_settings=False)
    skip_headers = run_http3_workflow(do_headers=False)
    skip_qpack = run_http3_workflow(do_qpack=False)
    skip_replay = run_http3_workflow(replay=False)
    skip_streamid = run_http3_workflow(use_streamid=False)
    live = run_http3_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_streamid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_settings["ok"] is False
    assert skip_settings["error"] == "settings_required"
    assert skip_headers["ok"] is False
    assert skip_headers["error"] == "headers_required"
    assert skip_qpack["ok"] is False
    assert skip_qpack["error"] == "qpack_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_streamid["ok"] is False
    assert skip_streamid["error"] == "streamid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_http3_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["settings"] is True
    assert row["headers"] is True
    assert row["qpack_response"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["streamid_bound"] is True
    assert row["digest"]
    assert live["streamid"] == DEFAULT_STREAMID
    assert live["qpack"] == DEFAULT_QPACK
    assert int(live["port"]) > 0
    opened = parse_message(
        encode_settings(identity=SENTINEL, streamid=DEFAULT_STREAMID, qpack=DEFAULT_QPACK)
    )
    assert opened["is_settings"] is True and opened["is_response"] is False
    assert opened["identity"] == SENTINEL and opened["streamid"] == DEFAULT_STREAMID
    assert opened["qpack"] == DEFAULT_QPACK
    assert opened["type"] == FRAME_SETTINGS
    assert opened["first_byte"] == STREAM_FIRST
    headers = parse_message(
        encode_headers(identity=SENTINEL, streamid=DEFAULT_STREAMID, qpack=DEFAULT_QPACK)
    )
    assert headers["is_headers"] is True and headers["is_response"] is True
    assert headers["streamid"] == DEFAULT_STREAMID
    assert headers["qpack"] == DEFAULT_QPACK
    packed = encode_settings(identity=SENTINEL, streamid=DEFAULT_STREAMID, qpack=DEFAULT_QPACK)
    zeroed = packed[:-4] + (0).to_bytes(4, "big")
    assert crc32c(zeroed) == int.from_bytes(packed[-4:], "big")
    bare = parse_message(encode_settings(identity=SENTINEL, streamid=DEFAULT_STREAMID, include_streamid=False))
    assert bare["has_streamid"] is False
    assert bare["streamid"] == EMPTY_STREAMID


def test_builtin_proof_seals_http3_actuation() -> None:
    report = builtin_http3_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "http3_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_http3"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_streamid_is_forbidden"]
    assert report["checks"]["skip_settings_stays_empty"]
    assert report["checks"]["skip_headers_stays_empty"]
    assert report["checks"]["skip_qpack_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_streamid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_qpack"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_http3"]
    assert report["checks"]["catalog_names_webtransport"]
    assert report["checks"]["leftover_text_binds_http3"]
    assert report["checks"]["proved_http3_consumes_leftover"]
    assert report["mission_goal"] == HTTP3_ACTUATION_GOAL
    assert report["done_when"] == HTTP3_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[HTTP3_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "http3" in capability.tags
    assert "rfc9114" in capability.tags
    assert "udp" in capability.tags
    assert "streamid" in capability.tags
    assert "qpack" in capability.tags


def test_selection_gate_accepts_http3_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        HTTP3_ACTUATION_GOAL,
        HTTP3_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(HTTP3_ACTUATION_GOAL)
    assert "http3" in family
    assert "rfc9114" in family
    assert "streamid" in family
    assert "qpack" in family
    assert "rfc9000" not in family
    assert "dcid" not in family
    assert "webtransport" not in family
    assert "rfc9220" not in family
    assert "sessionid" not in family
