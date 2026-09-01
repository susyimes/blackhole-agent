from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.ike_actuation import (
    DEFAULT_ISPI,
    DEFAULT_ISPI_HEX,
    DEFAULT_RSPI,
    FLAG_INITIATOR,
    FLAG_RESPONSE,
    IKE_AUTH,
    IKE_SA_INIT,
    SENTINEL,
    IKE_ACTUATION_DONE_WHEN,
    IKE_ACTUATION_GOAL,
    IKE_ACTUATION_ID,
    builtin_ike_actuation_proof,
    encode_auth,
    encode_sa_init,
    independent_ike_digest,
    parse_packet,
    run_ike_workflow,
)
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
from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    IKE_TOOL_PROVIDER,
    build_tool_routing_preflight,
    ike_tool_descriptor,
    route_tool_descriptor,
)


def test_goal_binds_ike_actuation_plane() -> None:
    assert leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    assert IKE_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    assert leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    assert leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    assert leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    assert leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    assert leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert IKE_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    assert DHCP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert RADIUS_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    assert SIP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    ike_signature = semantic_signature(IKE_ACTUATION_GOAL)
    for neighbor in (
        DHCP_ACTUATION_GOAL,
        RADIUS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        SIP_ACTUATION_GOAL,
    ):
        assert semantic_similarity(ike_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_ike_tool_completes_sa_init_auth_poll() -> None:
    descriptor = ike_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IKE_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("ike",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IKE_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["ike"]

    missing = run_ike_workflow(with_spi=False)
    skip_bind = run_ike_workflow(skip_bind=True)
    skip_sa_init = run_ike_workflow(do_sa_init=False)
    skip_auth = run_ike_workflow(do_auth=False)
    skip_replay = run_ike_workflow(replay=False)
    skip_spi = run_ike_workflow(use_spi=False)
    live = run_ike_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_spi"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_sa_init["ok"] is False
    assert skip_sa_init["error"] == "sa_init_required"
    assert skip_auth["ok"] is False
    assert skip_auth["error"] == "auth_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_spi["ok"] is False
    assert skip_spi["error"] == "spi_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_ike_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["sa_init"] is True
    assert row["auth"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["spi_bound"] is True
    assert row["digest"]
    assert live["initiator_spi"] == DEFAULT_ISPI_HEX
    assert int(live["port"]) > 0
    sa_init = parse_packet(encode_sa_init(initiator_spi=DEFAULT_ISPI, identity=SENTINEL))
    assert sa_init["exchange"] == IKE_SA_INIT and sa_init["is_initiator"] is True
    assert sa_init["identity"] == SENTINEL and sa_init["initiator_spi"] == DEFAULT_ISPI
    assert sa_init["flags"] == FLAG_INITIATOR
    response = parse_packet(
        encode_sa_init(
            initiator_spi=DEFAULT_ISPI,
            responder_spi=DEFAULT_RSPI,
            identity=SENTINEL,
            response=True,
        )
    )
    assert response["exchange"] == IKE_SA_INIT and response["is_response"] is True
    assert response["responder_spi"] == DEFAULT_RSPI
    assert response["flags"] == FLAG_RESPONSE
    auth = parse_packet(
        encode_auth(initiator_spi=DEFAULT_ISPI, responder_spi=DEFAULT_RSPI, identity=SENTINEL)
    )
    assert auth["exchange"] == IKE_AUTH and auth["identity"] == SENTINEL
    assert auth["initiator_spi"] == DEFAULT_ISPI
    bare = parse_packet(
        encode_sa_init(initiator_spi=DEFAULT_ISPI, identity=SENTINEL, include_spi=False)
    )
    assert bare["has_spi"] is False


def test_builtin_proof_seals_ike_actuation() -> None:
    report = builtin_ike_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "ike_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_ike"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_spi_is_forbidden"]
    assert report["checks"]["skip_sa_init_stays_empty"]
    assert report["checks"]["skip_auth_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_spi_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_spi"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_ike"]
    assert report["checks"]["catalog_names_sip"]
    assert report["mission_goal"] == IKE_ACTUATION_GOAL
    assert report["done_when"] == IKE_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[IKE_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "ike" in capability.tags
    assert "rfc7296" in capability.tags
    assert "udp" in capability.tags
    assert "spi" in capability.tags


def test_selection_gate_accepts_ike_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        IKE_ACTUATION_GOAL,
        IKE_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(IKE_ACTUATION_GOAL)
    assert "ike" in family
    assert "rfc7296" in family
    assert "spi" in family
    assert "dhcp" not in family
    assert "rfc2131" not in family
    assert "sip" not in family
    assert "rfc3261" not in family
