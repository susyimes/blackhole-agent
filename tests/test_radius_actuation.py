from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
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
from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
from blackhole_agent.radius_actuation import (
    ATTR_USER_PASSWORD,
    CODE_ACCESS_ACCEPT,
    CODE_ACCESS_REQUEST,
    DEFAULT_PASSWORD,
    DEFAULT_SECRET,
    SENTINEL,
    RADIUS_ACTUATION_DONE_WHEN,
    RADIUS_ACTUATION_GOAL,
    RADIUS_ACTUATION_ID,
    attribute_value,
    builtin_radius_actuation_proof,
    encode_accept,
    encode_request,
    independent_radius_digest,
    parse_packet,
    reveal_password,
    request_authenticator,
    run_radius_workflow,
    verify_accept,
)
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    RADIUS_TOOL_PROVIDER,
    build_tool_routing_preflight,
    radius_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_radius_actuation_plane() -> None:
    assert leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    assert RADIUS_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    assert leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    assert leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    assert leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    radius_signature = semantic_signature(RADIUS_ACTUATION_GOAL)
    for neighbor in (
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        DHCP_ACTUATION_GOAL,
    ):
        assert semantic_similarity(radius_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_radius_tool_completes_request_accept_username_poll() -> None:
    descriptor = radius_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, RADIUS_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("radius",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, RADIUS_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["radius"]

    missing = run_radius_workflow(with_secret=False)
    skip_bind = run_radius_workflow(skip_bind=True)
    skip_request = run_radius_workflow(do_request=False)
    skip_accept = run_radius_workflow(do_accept=False)
    skip_username = run_radius_workflow(do_username=False)
    skip_replay = run_radius_workflow(replay=False)
    skip_secret = run_radius_workflow(use_secret=False)
    live = run_radius_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_request["ok"] is False
    assert skip_request["error"] == "request_required"
    assert skip_accept["ok"] is False
    assert skip_accept["error"] == "accept_required"
    assert skip_username["ok"] is False
    assert skip_username["error"] == "username_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_secret["ok"] is False
    assert skip_secret["error"] == "secret_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_radius_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["request"] is True
    assert row["accept"] is True
    assert row["username_sent"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["secret_bound"] is True
    assert row["digest"]
    assert live["username"] == SENTINEL
    assert int(live["port"]) > 0
    origin = request_authenticator()
    request = parse_packet(encode_request(identifier=1, username=SENTINEL, authenticator=origin))
    assert request["code"] == CODE_ACCESS_REQUEST and request["username"] == SENTINEL
    assert reveal_password(
        attribute_value(request["attributes"], ATTR_USER_PASSWORD),
        DEFAULT_SECRET,
        origin,
    ) == DEFAULT_PASSWORD
    accept = parse_packet(encode_accept(identifier=1, request_auth=origin, username=SENTINEL))
    assert accept["code"] == CODE_ACCESS_ACCEPT and accept["username"] == SENTINEL
    assert verify_accept(encode_accept(identifier=1, request_auth=origin, username=SENTINEL), origin, DEFAULT_SECRET)
    bare = parse_packet(
        encode_request(identifier=1, username=SENTINEL, authenticator=origin, include_password=False)
    )
    assert bare["authenticated"] is False and bare["has_password"] is False


def test_builtin_proof_seals_radius_actuation() -> None:
    report = builtin_radius_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "radius_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_radius"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["skip_request_stays_empty"]
    assert report["checks"]["skip_accept_stays_empty"]
    assert report["checks"]["skip_username_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_secret_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_username"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_radius"]
    assert report["checks"]["catalog_names_dhcp"]
    assert report["mission_goal"] == RADIUS_ACTUATION_GOAL
    assert report["done_when"] == RADIUS_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[RADIUS_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "radius" in capability.tags
    assert "rfc2865" in capability.tags
    assert "udp" in capability.tags


def test_selection_gate_accepts_radius_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        RADIUS_ACTUATION_GOAL,
        RADIUS_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(RADIUS_ACTUATION_GOAL)
    assert "radiu" in family
    assert "rfc2865" in family
    assert "ntp" not in family
    assert "keyid" not in family
    assert "dhcp" not in family
    assert "rfc2131" not in family
