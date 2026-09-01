from pathlib import Path

from blackhole_agent.amqp_actuation import AMQP_ACTUATION_GOAL, AMQP_ACTUATION_ID
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
from blackhole_agent.grpc_actuation import GRPC_ACTUATION_GOAL, GRPC_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
from blackhole_agent.ssh_actuation import SSH_ACTUATION_GOAL, SSH_ACTUATION_ID
from blackhole_agent.tftp_actuation import (
    BLOCK_SIZE,
    TFTP_ACTUATION_DONE_WHEN,
    TFTP_ACTUATION_GOAL,
    TFTP_ACTUATION_ID,
    SENTINEL,
    builtin_tftp_actuation_proof,
    encode_ack,
    encode_data,
    encode_request,
    independent_tftp_digest,
    iter_blocks,
    parse_packet,
    run_tftp_workflow,
    sentinel_body,
)
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    TFTP_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    tftp_tool_descriptor,
)


def test_goal_binds_tftp_actuation_plane() -> None:
    assert leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    assert TFTP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert leftover_marker_ids(AMQP_ACTUATION_GOAL) == (AMQP_ACTUATION_ID,)
    assert leftover_marker_ids(GRPC_ACTUATION_GOAL) == (GRPC_ACTUATION_ID,)
    assert leftover_marker_ids(SSH_ACTUATION_GOAL) == (SSH_ACTUATION_ID,)
    assert leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    assert leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    assert TFTP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert AMQP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert GRPC_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert SSH_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert DNS_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    assert SNMP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    tftp_signature = semantic_signature(TFTP_ACTUATION_GOAL)
    for neighbor in (
        FTP_ACTUATION_GOAL,
        AMQP_ACTUATION_GOAL,
        GRPC_ACTUATION_GOAL,
        SSH_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
    ):
        assert semantic_similarity(tftp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_tftp_tool_completes_wrq_data_ack_rrq_replay() -> None:
    descriptor = tftp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TFTP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("tftp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TFTP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["tftp"]

    missing = run_tftp_workflow(with_tid=False)
    skip_bind = run_tftp_workflow(skip_bind=True)
    skip_wrq = run_tftp_workflow(wrq=False)
    skip_data = run_tftp_workflow(data=False)
    skip_ack = run_tftp_workflow(ack=False)
    skip_retr = run_tftp_workflow(retrieve=False)
    skip_replay = run_tftp_workflow(replay=False)
    skip_tid = run_tftp_workflow(use_transfer_tid=False)
    live = run_tftp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_tid"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_wrq["ok"] is False
    assert skip_wrq["error"] == "wrq_required"
    assert skip_data["ok"] is False
    assert skip_data["error"] == "data_required"
    assert skip_ack["ok"] is False
    assert skip_ack["error"] == "ack_required"
    assert skip_retr["ok"] is False
    assert skip_retr["error"] == "retrieve_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert skip_tid["ok"] is False
    assert skip_tid["error"] == "tid_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_tftp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["wrq"] is True
    assert row["data"] is True
    assert row["ack"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["tid_bound"] is True
    assert row["digest"]
    assert int(live["transfer_tid"]) > 0
    assert int(live["well_known_port"]) > 0
    assert int(live["transfer_tid"]) != int(live["well_known_port"])
    wrq = parse_packet(encode_request(2, "beacon.bin"))
    assert wrq["opcode"] == 2 and wrq["filename"] == "beacon.bin"
    ack = parse_packet(encode_ack(0))
    data = parse_packet(encode_data(1, b"xy"))
    assert ack["block"] == 0 and data["payload"] == b"xy"
    blocks = iter_blocks(sentinel_body())
    assert len(blocks) == 2 and len(blocks[0]) == BLOCK_SIZE


def test_builtin_proof_seals_tftp_actuation() -> None:
    report = builtin_tftp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "tftp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_tftp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_tid_is_forbidden"]
    assert report["checks"]["skip_wrq_stays_empty"]
    assert report["checks"]["skip_data_stays_empty"]
    assert report["checks"]["skip_ack_stays_empty"]
    assert report["checks"]["skip_retrieve_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["skip_tid_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_distinct_tids"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_tftp"]
    assert report["checks"]["catalog_names_snmp"]
    assert report["mission_goal"] == TFTP_ACTUATION_GOAL
    assert report["done_when"] == TFTP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[TFTP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "tftp" in capability.tags
    assert "rfc1350" in capability.tags
    assert "udp" in capability.tags


def test_selection_gate_accepts_tftp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        TFTP_ACTUATION_GOAL,
        TFTP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(TFTP_ACTUATION_GOAL)
    assert "tftp" in family
    assert "rfc1350" in family
    assert "ftpd" not in family
    assert "pasv" not in family
    assert "amqp" not in family
    assert "openssh" not in family
    assert "auth" not in family.split("/")
