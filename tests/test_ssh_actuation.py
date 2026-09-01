from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.ldap_actuation import LDAP_ACTUATION_GOAL, LDAP_ACTUATION_ID
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
from blackhole_agent.postgres_actuation import POSTGRES_ACTUATION_GOAL, POSTGRES_ACTUATION_ID
from blackhole_agent.s3_actuation import S3_ACTUATION_GOAL, S3_ACTUATION_ID
from blackhole_agent.ssh_actuation import (
    SENTINEL,
    SSH_ACTUATION_DONE_WHEN,
    SSH_ACTUATION_GOAL,
    SSH_ACTUATION_ID,
    builtin_ssh_actuation_proof,
    dh_private,
    dh_public,
    dh_shared,
    independent_ssh_digest,
    run_ssh_workflow,
    sign_kex_hash,
    verify_kex_signature,
)
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    SSH_TOOL_PROVIDER,
    build_tool_routing_preflight,
    route_tool_descriptor,
    ssh_tool_descriptor,
)
from blackhole_agent.watch_actuation import WATCH_ACTUATION_GOAL, WATCH_ACTUATION_ID
from blackhole_agent.websocket_actuation import WEBSOCKET_ACTUATION_GOAL, WEBSOCKET_ACTUATION_ID


def test_goal_binds_ssh_actuation_plane() -> None:
    assert leftover_marker_ids(SSH_ACTUATION_GOAL) == (SSH_ACTUATION_ID,)
    assert SSH_ACTUATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL) == (WEBSOCKET_ACTUATION_ID,)
    assert leftover_marker_ids(WATCH_ACTUATION_GOAL) == (WATCH_ACTUATION_ID,)
    assert leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    assert leftover_marker_ids(POSTGRES_ACTUATION_GOAL) == (POSTGRES_ACTUATION_ID,)
    assert leftover_marker_ids(LDAP_ACTUATION_GOAL) == (LDAP_ACTUATION_ID,)
    assert leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    assert SSH_ACTUATION_ID not in leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL)
    assert SSH_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert SSH_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    assert SSH_ACTUATION_ID not in leftover_marker_ids(POSTGRES_ACTUATION_GOAL)
    assert SSH_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    assert SSH_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    assert WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    assert S3_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    assert POSTGRES_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    assert LDAP_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    assert MQTT_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    ssh_signature = semantic_signature(SSH_ACTUATION_GOAL)
    for neighbor in (
        WEBSOCKET_ACTUATION_GOAL,
        WATCH_ACTUATION_GOAL,
        S3_ACTUATION_GOAL,
        POSTGRES_ACTUATION_GOAL,
        LDAP_ACTUATION_GOAL,
        MQTT_ACTUATION_GOAL,
    ):
        assert semantic_similarity(ssh_signature, semantic_signature(neighbor)) < 0.82


def test_opted_in_ssh_tool_completes_identify_kex_userauth_exec_replay() -> None:
    descriptor = ssh_tool_descriptor()
    naive = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SSH_TOOL_PROVIDER),
    )
    assert naive.executable is False
    assert opted.executable is True

    preflight = build_tool_routing_preflight(
        [descriptor],
        required_tool_names=("ssh",),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SSH_TOOL_PROVIDER),
    )
    assert preflight["ok"] is True
    assert preflight["executable_tool_names"] == ["ssh"]

    missing = run_ssh_workflow(with_secret=False)
    unauth = run_ssh_workflow(authenticate=False)
    wrong = run_ssh_workflow(password="wrong-token")
    skip_bind = run_ssh_workflow(skip_bind=True)
    skip_identify = run_ssh_workflow(identify=False)
    skip_kex = run_ssh_workflow(kex=False)
    skip_mac = run_ssh_workflow(mac=False)
    skip_channel = run_ssh_workflow(channel=False)
    skip_exec = run_ssh_workflow(exec_command=False)
    skip_receive = run_ssh_workflow(receive=False)
    skip_replay = run_ssh_workflow(replay=False)
    live = run_ssh_workflow()
    assert missing["ok"] is False
    assert missing["final_status"] == 403
    assert missing["error"] == "missing_secret"
    assert unauth["ok"] is False
    assert unauth["error"] == "auth_required"
    assert unauth["final_status"] == 401
    assert wrong["ok"] is False
    assert wrong["error"] == "auth_failed"
    assert skip_bind["ok"] is False
    assert skip_bind["error"] == "ssh_required"
    assert skip_identify["ok"] is False
    assert skip_identify["error"] == "identify_required"
    assert skip_kex["ok"] is False
    assert skip_kex["error"] == "kex_required"
    assert skip_mac["ok"] is False
    assert skip_mac["error"] == "mac_required"
    assert skip_channel["ok"] is False
    assert skip_channel["error"] == "channel_required"
    assert skip_exec["ok"] is False
    assert skip_exec["error"] == "exec_required"
    assert skip_receive["ok"] is False
    assert skip_receive["error"] == "receive_required"
    assert skip_replay["ok"] is False
    assert skip_replay["error"] == "replay_required"
    assert live["ok"] is True
    assert live["sentinel"] == SENTINEL
    assert live["independent_sentinel"] == SENTINEL
    assert Path(live["sealed_path"]).is_file()
    row = independent_ssh_digest(Path(live["sealed_path"]))
    assert row["sentinel"] == SENTINEL
    assert row["authenticated"] is True
    assert row["identified"] is True
    assert row["kexed"] is True
    assert row["macced"] is True
    assert row["channeled"] is True
    assert row["execed"] is True
    assert row["received"] is True
    assert row["replayed"] is True
    assert row["independent"] is True
    assert row["digest"]
    assert len(live["session_id"]) == 64
    left = dh_private()
    right = dh_private()
    assert dh_shared(dh_public(right), left) == dh_shared(dh_public(left), right)
    sample = b"0" * 32
    assert verify_kex_signature(sample, sign_kex_hash(sample))


def test_builtin_proof_seals_ssh_actuation() -> None:
    report = builtin_ssh_actuation_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "ssh_actuation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_preflight_missing_ssh"]
    assert report["checks"]["opted_in_preflight_ok"]
    assert report["checks"]["naive_without_secret_is_forbidden"]
    assert report["checks"]["unsigned_exec_is_forbidden"]
    assert report["checks"]["wrong_password_is_forbidden"]
    assert report["checks"]["skip_identify_stays_empty"]
    assert report["checks"]["skip_kex_stays_empty"]
    assert report["checks"]["skip_mac_stays_empty"]
    assert report["checks"]["skip_exec_stays_empty"]
    assert report["checks"]["skip_replay_stays_empty"]
    assert report["checks"]["workflow_extracts_sentinel"]
    assert report["checks"]["workflow_commits_independent_digest"]
    assert report["checks"]["workflow_writes_sealed_file"]
    assert report["checks"]["sealed_trace_verifies"]
    assert report["checks"]["tampered_trace_fails"]
    assert report["checks"]["exhausted_catalog_binds_ssh"]
    assert report["checks"]["group14_dh_agrees"]
    assert report["mission_goal"] == SSH_ACTUATION_GOAL
    assert report["done_when"] == SSH_ACTUATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[SSH_ACTUATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "ssh" in capability.tags
    assert "openssh" in capability.tags
    assert "exec" in capability.tags
    assert "kex" in capability.tags


def test_selection_gate_accepts_ssh_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        SSH_ACTUATION_GOAL,
        SSH_ACTUATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(SSH_ACTUATION_GOAL)
    assert "openssh" in family
    assert "exec" in family
    assert "binary" in family
    assert "packet" in family
    assert "websocket" not in family
    assert "rfc6455" not in family
    assert "watch" not in family
    assert "path" not in family
    assert "postgres" not in family
    assert "ldap" not in family
    assert "object" not in family
    assert "mqtt" not in family
