from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_class_closure import CLASS_CLOSURE_REQUIREMENTS
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_http_event_stream import MCP_HTTP_EVENT_GOAL, MCP_HTTP_EVENT_ID
from blackhole_agent.publication_resilience import (
    PUBLICATION_FAILED,
    PUBLICATION_RESILIENCE_DONE_WHEN,
    PUBLICATION_RESILIENCE_GOAL,
    PUBLICATION_RESILIENCE_ID,
    builtin_publication_resilience_proof,
)


def test_post_buffer_overflow_retries_once(tmp_path: Path) -> None:
    import subprocess

    from blackhole_agent.publication_resilience import (
        POST_BUFFER_RETRY_BYTES,
        is_post_buffer_overflow,
    )
    from blackhole_agent.unbound import publish_lineage

    harvested = (
        "error: unable to rewind rpc post data - try increasing http.postBuffer\n"
        "error: RPC failed; curl 65 schannel: server closed abruptly (missing close_notify)\n"
    )
    handshake = (
        "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
        "schannel: failed to receive handshake, SSL/TLS connection failed\n"
    )
    assert is_post_buffer_overflow(harvested)
    assert not is_post_buffer_overflow(handshake)

    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "publish@test.local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Publish Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = [str(part) for part in command]
        if tokens and tokens[0] == "git" and "push" in tokens:
            pushes.append(tokens)
            if not any(part.startswith("http.postBuffer=") for part in tokens):
                return subprocess.CompletedProcess(tokens, 1, stdout="", stderr=harvested)
        return subprocess.run(tokens, **kwargs)  # type: ignore[arg-type]

    result = publish_lineage(repo, commit_sha, str(remote), "main", command_runner=runner)
    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert result.ok is True
    assert result.remote_after == commit_sha
    assert remote_head == commit_sha
    assert len(pushes) == 2
    assert f"http.postBuffer={POST_BUFFER_RETRY_BYTES}" in pushes[1]
    assert "http.postBuffer=" not in " ".join(pushes[0])


def test_schannel_handshake_retries_the_same_push_once(tmp_path: Path) -> None:
    import subprocess

    from blackhole_agent.publication_resilience import (
        is_post_buffer_overflow,
        is_schannel_handshake_failure,
    )
    from blackhole_agent.unbound import publish_lineage

    handshake = (
        "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
        "schannel: failed to receive handshake, SSL/TLS connection failed\n"
    )
    close_notify = (
        "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
        "schannel: server closed abruptly (missing close_notify)\n"
    )
    post_buffer = (
        "error: unable to rewind rpc post data - try increasing http.postBuffer\n"
        "error: RPC failed; curl 65 schannel: server closed abruptly (missing close_notify)\n"
    )
    assert is_schannel_handshake_failure(handshake)
    assert is_schannel_handshake_failure(close_notify)
    assert not is_schannel_handshake_failure(post_buffer)
    assert not is_schannel_handshake_failure("protected path publication blocked")
    assert is_post_buffer_overflow(post_buffer)

    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "publish@test.local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Publish Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = [str(part) for part in command]
        if tokens and tokens[0] == "git" and "push" in tokens:
            pushes.append(tokens)
            if len(pushes) == 1:
                return subprocess.CompletedProcess(tokens, 1, stdout="", stderr=handshake)
        return subprocess.run(tokens, **kwargs)  # type: ignore[arg-type]

    result = publish_lineage(repo, commit_sha, str(remote), "main", command_runner=runner)
    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert result.ok is True
    assert result.remote_after == commit_sha
    assert remote_head == commit_sha
    assert len(pushes) == 2
    assert pushes[0] == pushes[1]
    assert "http.postBuffer=" not in " ".join(pushes[0])


def test_http_transport_abort_retries_the_same_push_once(tmp_path: Path) -> None:
    import subprocess

    from blackhole_agent.publication_resilience import (
        is_http_transport_abort,
        is_post_buffer_overflow,
        is_schannel_handshake_failure,
    )
    from blackhole_agent.unbound import publish_lineage

    empty_reply = (
        "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
        "Empty reply from server\n"
    )
    connect = (
        "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
        "Failed to connect to github.com port 443 after 21097 ms: Could not connect to server\n"
    )
    dns = (
        "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
        "Could not resolve host: github.com\n"
    )
    handshake = (
        "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
        "schannel: failed to receive handshake, SSL/TLS connection failed\n"
    )
    post_buffer = (
        "error: unable to rewind rpc post data - try increasing http.postBuffer\n"
        "error: RPC failed; curl 65 Recv failure: Connection was reset\n"
    )
    assert is_http_transport_abort(empty_reply)
    assert is_http_transport_abort(connect)
    assert is_http_transport_abort(dns)
    assert not is_http_transport_abort(handshake)
    assert not is_http_transport_abort(post_buffer)
    assert not is_http_transport_abort("protected paths require operator acknowledgment")
    assert not is_schannel_handshake_failure(empty_reply)
    assert is_post_buffer_overflow(post_buffer)

    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "publish@test.local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Publish Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = [str(part) for part in command]
        if tokens and tokens[0] == "git" and "push" in tokens:
            pushes.append(tokens)
            if len(pushes) == 1:
                return subprocess.CompletedProcess(tokens, 1, stdout="", stderr=empty_reply)
        return subprocess.run(tokens, **kwargs)  # type: ignore[arg-type]

    result = publish_lineage(repo, commit_sha, str(remote), "main", command_runner=runner)
    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert result.ok is True
    assert result.remote_after == commit_sha
    assert remote_head == commit_sha
    assert len(pushes) == 2
    assert pushes[0] == pushes[1]
    assert "http.postBuffer=" not in " ".join(pushes[0])


def test_protected_path_refusal_drops_pending_publish() -> None:
    from blackhole_agent.protected_paths import evaluate_protected_paths_gate
    from blackhole_agent.publication_resilience import (
        PROTECTED_PATH_REFUSAL_MARKER,
        apply_publication_failure,
        is_terminal_publication_error,
    )

    harvested = (
        "protected paths require operator acknowledgment: "
        "src/blackhole_agent/experience_fuel.py"
    )
    dns = (
        "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
        "Could not resolve host: github.com"
    )
    connect = (
        "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
        "Failed to connect to github.com port 443 after 21097 ms: Could not connect to server"
    )
    assert PROTECTED_PATH_REFUSAL_MARKER in harvested
    assert is_terminal_publication_error(harvested)
    assert not is_terminal_publication_error(dns)
    assert not is_terminal_publication_error(connect)

    verdict = evaluate_protected_paths_gate(
        ("src/blackhole_agent/experience_fuel.py",),
        operator_acknowledged=False,
    )
    assert verdict.blocked is True
    assert verdict.operator_acknowledged is False
    pending = {
        "pending_publish_ref": "e7b754131c475cdb13012f16f8b29f212125fd56",
        "pending_publish_mission_id": "20260817T150703Z-4f1451c3",
        "last_publish_error": "",
    }
    apply_publication_failure(pending, f"{verdict.reason}: {verdict.touched[0]}")
    assert pending["pending_publish_ref"] == ""
    assert pending["pending_publish_mission_id"] == ""
    assert pending["last_publish_error"].startswith(PROTECTED_PATH_REFUSAL_MARKER)

    transient = {
        "pending_publish_ref": "e7b754131c475cdb13012f16f8b29f212125fd56",
        "pending_publish_mission_id": "20260817T150703Z-4f1451c3",
        "last_publish_error": "",
    }
    apply_publication_failure(transient, dns)
    assert transient["pending_publish_ref"] == "e7b754131c475cdb13012f16f8b29f212125fd56"
    assert transient["pending_publish_mission_id"] == "20260817T150703Z-4f1451c3"


def test_goal_binds_publication_resilience_plane() -> None:
    assert leftover_marker_ids(PUBLICATION_RESILIENCE_GOAL) == (PUBLICATION_RESILIENCE_ID,)
    assert CLASS_CLOSURE_REQUIREMENTS[PUBLICATION_FAILED] == (PUBLICATION_RESILIENCE_ID,)
    assert PUBLICATION_RESILIENCE_ID in LOCAL_DENYLIST
    assert PUBLICATION_RESILIENCE_ID not in leftover_marker_ids(MCP_HTTP_EVENT_GOAL)
    assert leftover_marker_ids(MCP_HTTP_EVENT_GOAL) == (MCP_HTTP_EVENT_ID,)


def test_builtin_proof_refuses_diverged_remote_head() -> None:
    report = builtin_publication_resilience_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "publication_resilience"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["diverged_clean_merge_publishes"]
    assert report["checks"]["diverged_clean_merge_fast_forwards"]
    assert report["checks"]["conflicting_divergence_is_refused"]
    assert report["checks"]["conflicting_remote_is_unchanged"]
    assert report["checks"]["same_sha_republication_is_idempotent"]
    assert report["checks"]["ancestor_fast_forward_publishes"]
    assert report["checks"]["terminal_mismatch_drops_pending"]
    assert report["checks"]["transient_error_keeps_pending"]
    assert report["checks"]["harvests_sticky_publish_error"]
    assert report["checks"]["proved_closer_drops_class"]
    assert report["checks"]["exhausted_catalog_rejects_ledger_only_publication"]
    assert report["checks"]["exhausted_catalog_stays_unbound_without_gate_passing_successor"]
    assert report["mission_goal"] == PUBLICATION_RESILIENCE_GOAL
    assert report["done_when"] == PUBLICATION_RESILIENCE_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[PUBLICATION_RESILIENCE_ID]
    assert capability.last_proof_exit_code == 0
    assert "publication" in capability.tags
    assert "git" in capability.tags
