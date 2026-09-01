from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.ntp_actuation import (
    DEFAULT_KEYID,
    MODE_CLIENT,
    MODE_SERVER,
    SENTINEL,
    SENTINEL_REFID,
    NTP_ACTUATION_DONE_WHEN,
    NTP_ACTUATION_GOAL,
    NTP_ACTUATION_ID,
    builtin_ntp_actuation_proof,
    encode_packet,
    independent_ntp_digest,
    parse_packet,
    run_ntp_workflow,
    sentinel_timestamp,
    verify_mac,
)
from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    NTP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    ntp_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_ntp_actuation_plane() -> None:
    assert leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    assert NTP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    assert leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    assert leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    ntp_signature = semantic_signature(NTP_ACTUATION_GOAL)
    for neighbor in (
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        RADIUS_ACTUATION_GOAL,
    ):
        assert semantic_similarity(ntp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_ntp_tool_completes_client_server_origin_poll() -> None:
    descriptor = ntp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, NTP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("ntp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, NTP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["ntp"]

    missing = run_ntp_workflow(with_keyid=False)
    skip_bind = run_ntp_workflow(skip_bind=True)
    skip_client = run_ntp_workflow(do_client=False)
    skip_server = run_ntp_workflow(do_server=False)
    skip_originate = run_ntp_workflow(originate=False)
    skip_receive = run_ntp_workflow(receive=False)
    skip_transmit = run_ntp_workflow(transmit=False)
    skip_replay = run_ntp_workflow(replay=False)
    skip_keyid = run_ntp_workflow(use_keyid=False)
    live = run_ntp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_keyid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_client["ok"] is False
    assert skip_client["error"] == "client_required"
    assert skip_server["ok"] is False
    assert skip_server["error"] == "server_required"
    assert skip_originate["ok"] is False
    assert skip_originate["error"] == "originate_required"
    assert skip_receive["ok"] is False
    assert skip_receive["error"] == "receive_required"
    assert skip_transmit["ok"] is False
    assert skip_transmit["error"] == "transmit_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_keyid["ok"] is False
    assert skip_keyid["error"] == "keyid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_ntp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["client"] is True
    assert row["server"] is True
    assert row["originate_sent"] is True
    assert row["receive_sent"] is True
    assert row["transmit_sent"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["keyid_bound"] is True
    assert row["digest"]
    assert int(live["originate"]) == sentinel_timestamp()
    assert int(live["port"]) > 0
    origin = sentinel_timestamp()
    client = parse_packet(encode_packet(mode=MODE_CLIENT, transmit=origin))
    assert client["mode"] == MODE_CLIENT and client["keyid"] == DEFAULT_KEYID
    assert client["transmit"] == origin and verify_mac(encode_packet(mode=MODE_CLIENT, transmit=origin))
    server = parse_packet(
        encode_packet(
            mode=MODE_SERVER,
            originate=origin,
            receive=origin + 1,
            transmit=origin + 2,
            reference=origin,
        )
    )
    assert server["mode"] == MODE_SERVER and server["originate"] == origin
    assert server["refid"] == SENTINEL_REFID
    bare = parse_packet(encode_packet(mode=MODE_CLIENT, transmit=origin, include_keyid=False))
    assert bare["authenticated"] is False and bare["keyid"] == 0


def test_builtin_proof_seals_ntp_actuation() -> None:
    report = builtin_ntp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "ntp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_ntp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_keyid_is_forbidden"]
    assert report["checks"]["skip_client_stays_empty"]
    assert report["checks"]["skip_server_stays_empty"]
    assert report["checks"]["skip_originate_stays_empty"]
    assert report["checks"]["skip_receive_stays_empty"]
    assert report["checks"]["skip_transmit_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_keyid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_origin"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_ntp"]
    assert report["checks"]["catalog_names_radius"]
    assert report["checks"]["catalog_names_dhcp"]
    assert report["mission_goal"] == NTP_ACTUATION_GOAL
    assert report["done_when"] == NTP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[NTP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "ntp" in capability.tags
    assert "rfc5905" in capability.tags
    assert "udp" in capability.tags


def test_selection_gate_accepts_ntp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        NTP_ACTUATION_GOAL,
        NTP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(NTP_ACTUATION_GOAL)
    assert "ntp" in family
    assert "rfc5905" in family
    assert "keyid" in family
    assert "syslog" not in family
    assert "nilvalue" not in family
    assert "radius" not in family
    assert "radiu" not in family
    assert "rfc2865" not in family
