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
    assert report["checks"]["diverged_remote_is_refused"]
    assert report["checks"]["diverged_remote_is_unchanged"]
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
