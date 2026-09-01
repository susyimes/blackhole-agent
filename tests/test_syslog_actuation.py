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
from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.syslog_actuation import (
    DEFAULT_HOSTNAME,
    DEFAULT_PRI,
    NILVALUE,
    SENTINEL,
    SYSLOG_ACTUATION_DONE_WHEN,
    SYSLOG_ACTUATION_GOAL,
    SYSLOG_ACTUATION_ID,
    builtin_syslog_actuation_proof,
    encode_structured_data,
    encode_syslog,
    independent_syslog_digest,
    parse_sd_params,
    parse_syslog,
    run_syslog_workflow,
)
from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    SYSLOG_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    syslog_tool_descriptor,
)


def test_goal_binds_syslog_actuation_plane() -> None:
    assert leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    assert SYSLOG_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    assert leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert SYSLOG_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    assert NTP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    syslog_signature = semantic_signature(SYSLOG_ACTUATION_GOAL)
    for neighbor in (
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
    ):
        assert semantic_similarity(syslog_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_syslog_tool_completes_pri_header_sd_msg_replay() -> None:
    descriptor = syslog_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SYSLOG_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("syslog",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SYSLOG_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["syslog"]

    missing = run_syslog_workflow(with_hostname=False)
    skip_bind = run_syslog_workflow(skip_bind=True)
    skip_pri = run_syslog_workflow(do_pri=False)
    skip_header = run_syslog_workflow(do_header=False)
    skip_sd = run_syslog_workflow(do_structured_data=False)
    skip_msg = run_syslog_workflow(do_msg=False)
    skip_replay = run_syslog_workflow(replay=False)
    skip_hostname = run_syslog_workflow(use_hostname=False)
    live = run_syslog_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_hostname"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_pri["ok"] is False
    assert skip_pri["error"] == "pri_required"
    assert skip_header["ok"] is False
    assert skip_header["error"] == "header_required"
    assert skip_sd["ok"] is False
    assert skip_sd["error"] == "structured_data_required"
    assert skip_msg["ok"] is False
    assert skip_msg["error"] == "msg_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_hostname["ok"] is False
    assert skip_hostname["error"] == "hostname_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_syslog_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["pri_sent"] is True
    assert row["header"] is True
    assert row["structured_data_sent"] is True
    assert row["msg"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["hostname_bound"] is True
    assert row["digest"]
    assert int(live["pri"]) == DEFAULT_PRI
    assert int(live["port"]) > 0
    packed = parse_syslog(encode_syslog(msg=SENTINEL))
    assert packed["pri"] == DEFAULT_PRI and packed["hostname"] == DEFAULT_HOSTNAME
    assert packed["nilvalue_hostname"] is False
    assert packed["msg"] == SENTINEL
    params = parse_sd_params(packed["structured_data"])
    assert params.get("sentinel") == SENTINEL
    nil_host = parse_syslog(encode_syslog(hostname=NILVALUE))
    assert nil_host["nilvalue_hostname"] is True
    nil_sd = parse_syslog(encode_syslog(include_structured_data=False))
    assert nil_sd["nilvalue_structured_data"] is True
    escaped = parse_syslog(
        encode_syslog(
            structured_data=encode_structured_data(params={"note": 'a"b\\c]d'}),
            msg=SENTINEL,
        )
    )
    assert parse_sd_params(escaped["structured_data"]).get("note") == 'a"b\\c]d'


def test_builtin_proof_seals_syslog_actuation() -> None:
    report = builtin_syslog_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "syslog_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_syslog"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_hostname_is_forbidden"]
    assert report["checks"]["skip_pri_stays_empty"]
    assert report["checks"]["skip_header_stays_empty"]
    assert report["checks"]["skip_structured_data_stays_empty"]
    assert report["checks"]["skip_msg_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_hostname_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_pri"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_syslog"]
    assert report["checks"]["catalog_names_ntp"]
    assert report["mission_goal"] == SYSLOG_ACTUATION_GOAL
    assert report["done_when"] == SYSLOG_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[SYSLOG_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "syslog" in capability.tags
    assert "rfc5424" in capability.tags
    assert "udp" in capability.tags


def test_selection_gate_accepts_syslog_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        SYSLOG_ACTUATION_GOAL,
        SYSLOG_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(SYSLOG_ACTUATION_GOAL)
    assert "syslog" in family
    assert "rfc5424" in family
    assert "nilvalue" in family
    assert "snmp" not in family
    assert "varbind" not in family
    assert "ntp" not in family
    assert "rfc5905" not in family
