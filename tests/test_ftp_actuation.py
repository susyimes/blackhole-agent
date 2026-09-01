from pathlib import Path

from blackhole_agent.amqp_actuation import AMQP_ACTUATION_GOAL, AMQP_ACTUATION_ID
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.ftp_actuation import (
    FTP_ACTUATION_DONE_WHEN,
    FTP_ACTUATION_GOAL,
    FTP_ACTUATION_ID,
    SENTINEL,
    builtin_ftp_actuation_proof,
    encode_pasv_tuple,
    format_pasv_reply,
    independent_ftp_digest,
    parse_pasv_tuple,
    run_ftp_workflow,
)
from blackhole_agent.grpc_actuation import GRPC_ACTUATION_GOAL, GRPC_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.s3_actuation import S3_ACTUATION_GOAL, S3_ACTUATION_ID
from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
from blackhole_agent.ssh_actuation import SSH_ACTUATION_GOAL, SSH_ACTUATION_ID
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    FTP_TOOL_PROVIDER,
    ftp_tool_descriptor,
    build_tool_routing_preflight,
    route_tool_descriptor,
)


def test_goal_binds_ftp_actuation_plane() -> None:
    assert leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    assert FTP_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(AMQP_ACTUATION_GOAL) == (AMQP_ACTUATION_ID,)
    assert leftover_marker_ids(GRPC_ACTUATION_GOAL) == (GRPC_ACTUATION_ID,)
    assert leftover_marker_ids(SSH_ACTUATION_GOAL) == (SSH_ACTUATION_ID,)
    assert leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    assert leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(AMQP_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    assert FTP_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert AMQP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert GRPC_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert SSH_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert SMTP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    ftp_signature = semantic_signature(FTP_ACTUATION_GOAL)
    for neighbor in (
        AMQP_ACTUATION_GOAL,
        GRPC_ACTUATION_GOAL,
        SSH_ACTUATION_GOAL,
        SMTP_ACTUATION_GOAL,
        S3_ACTUATION_GOAL,
    ):
        assert semantic_similarity(ftp_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_ftp_tool_completes_user_pass_type_pasv_stor_retr_replay() -> None:
    descriptor = ftp_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FTP_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("ftp",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, FTP_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["ftp"]

    missing = run_ftp_workflow(with_secret=False)
    unauth = run_ftp_workflow(authenticate=False)
    wrong = run_ftp_workflow(password="wrong-password")
    skip_bind = run_ftp_workflow(skip_bind=True)
    skip_type = run_ftp_workflow(type_binary=False)
    skip_pasv = run_ftp_workflow(pasv=False)
    skip_store = run_ftp_workflow(store=False)
    skip_retr = run_ftp_workflow(retrieve=False)
    skip_replay = run_ftp_workflow(replay=False)
    live = run_ftp_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "login_required"
    assert unauth["final_status"] == 530
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "not_bound"
    assert skip_type["ok"] is False
    assert skip_type["error"] == "type_required"
    assert skip_pasv["ok"] is False
    assert skip_pasv["error"] == "pasv_required"
    assert skip_store["ok"] is False
    assert skip_store["error"] == "store_required"
    assert skip_retr["ok"] is False
    assert skip_retr["error"] == "retrieve_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_ftp_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["login"] is True
    assert row["typed"] is True
    assert row["pasv"] is True
    assert row["stored"] is True
    assert row["retrieved"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["authenticated"] is True
    assert row["digest"]
    assert int(live["data_port"]) > 0
    assert int(live["control_port"]) > 0
    assert int(live["data_port"]) != int(live["control_port"])
    packed = encode_pasv_tuple("127.0.0.1", 2121)
    host, port = parse_pasv_tuple(format_pasv_reply("127.0.0.1", 2121))
    assert packed == "127,0,0,1,8,73"
    assert host == "127.0.0.1" and port == 2121


def test_builtin_proof_seals_ftp_actuation() -> None:
    report = builtin_ftp_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "ftp_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_ftp"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unauthenticated_transfer_is_forbidden"]
    assert report["checks"]["wrong_password_is_forbidden"]
    assert report["checks"]["skip_type_stays_empty"]
    assert report["checks"]["skip_pasv_stays_empty"]
    assert report["checks"]["skip_store_stays_empty"]
    assert report["checks"]["skip_retr_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["workflow_records_dual_channel"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_ftp"]
    assert report["checks"]["pasv_tuple_roundtrip"]
    assert report["mission_goal"] == FTP_ACTUATION_GOAL
    assert report["done_when"] == FTP_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[FTP_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "ftp" in capability.tags
    assert "rfc959" in capability.tags
    assert "pasv" in capability.tags


def test_selection_gate_accepts_ftp_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        FTP_ACTUATION_GOAL,
        FTP_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(FTP_ACTUATION_GOAL)
    assert "ftpd" in family
    assert "pasv" in family
    assert "rfc959" in family
    assert "transfer" in family
    assert "amqp" not in family
    assert "grpc" not in family
    assert "openssh" not in family
    assert "smtp" not in family
    assert "auth" not in family.split("/")
