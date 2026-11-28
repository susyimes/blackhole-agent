import json
import subprocess
from pathlib import Path

import pytest

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
from blackhole_agent.registry_publication import merge_registry
from blackhole_agent.unbound import publish_lineage
from tests.test_unbound import init_repository


def catalog(**rows):
    entries = {key: {"id": key, "name": key, "kind": "command", "entry": "git status",
                     "proof_command": "git status", **fields} for key, fields in rows.items()}
    return json.dumps({"capabilities": entries, "schema_version": 1})


def test_registry_preserves_whole_winning_record_and_proof_timestamp():
    base = catalog(one={}, two={})
    peer = catalog(one={"updated_at": "2026-09-01T00:00:00Z"}, two={"last_proved_at": "peer"})
    mission = catalog(one={"entry": "git log", "updated_at": "2026-08-01T00:00:00Z"}, two={})
    rows = json.loads(merge_registry(base, peer, mission))["capabilities"]
    assert rows["one"] == json.loads(mission)["capabilities"]["one"]
    assert rows["two"] == json.loads(peer)["capabilities"]["two"]
    created = json.loads(merge_registry(None, catalog(first={}), catalog(second={})))
    assert set(created["capabilities"]) == {"first", "second"}


@pytest.mark.parametrize(("base", "peer", "mission", "reason"), [
    (catalog(one={}), catalog(), catalog(one={"last_proved_at": "new"}), "competing edits"),
    (catalog(), catalog(one={"extra": True}), catalog(one={"extra": 1}), "competing edits"),
    (catalog(one={}, two={}), catalog(one={"dependencies": ["two"]}, two={}),
     catalog(one={}, two={"dependencies": ["one"]}), "cycle"),
    (catalog(), '{"capabilities": {}, "capabilities": {}}', catalog(one={}), "duplicate"),
    (catalog(), catalog(one={}).replace('"schema_version": 1', '"schema_version": 2'), catalog(two={}), "format"),
], ids=["delete-edit", "json-types", "combined-cycle", "duplicate-key", "future-schema"])
def test_registry_refuses_ambiguous_or_invalid_merge(base, peer, mission, reason):
    with pytest.raises(ValueError, match=reason):
        merge_registry(base, peer, mission)


def exercise_transport_retry(tmp_path: Path, error: str) -> list[list[str]]:
    repo, receiver = tmp_path / "repo", tmp_path / "receiver.git"
    repo.mkdir()
    init_repository(repo)
    subprocess.run(["git", "init", "--bare", "-q", str(receiver)], check=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    pushes = []

    def transport(command, **kwargs):
        if "push" in command:
            pushes.append(list(command))
            if len(pushes) == 1:
                return subprocess.CompletedProcess(command, 1, "", error)
        return subprocess.run(command, **kwargs)

    receipt = publish_lineage(repo, commit, str(receiver), "main", command_runner=transport)
    head = subprocess.check_output(["git", "rev-parse", "refs/heads/main"], cwd=receiver, text=True).strip()
    assert receipt.ok and receipt.remote_after == head == commit
    assert len(pushes) == 2
    return pushes


def test_reviews_each_receiving_branch_before_any_push(tmp_path):
    writer = tmp_path / "writer"
    writer.mkdir()
    init_repository(writer)

    def git(*args, cwd=writer):
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.PIPE).strip()

    base = git("rev-parse", "HEAD")
    protected = writer / "src" / "blackhole_agent" / "persona.py"
    protected.parent.mkdir()
    protected.write_text("# fixture\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "protected change")
    target = git("rev-parse", "HEAD")
    primary, secondary = tmp_path / "primary.git", tmp_path / "secondary.git"
    git("remote", "add", "both", str(primary))
    for receiver, head in ((primary, target), (secondary, base)):
        git("init", "--bare", "-q", str(receiver))
        git("push", str(receiver), f"{head}:refs/heads/main")
        git("remote", "set-url", "--add", "--push", "both", str(receiver))

    refused = publish_lineage(writer, target, "both", "main")
    assert not refused.ok and "src/blackhole_agent/persona.py" in refused.error
    assert git("rev-parse", "refs/heads/main", cwd=secondary) == base
    approved = publish_lineage(writer, target, "both", "main", operator_acknowledged=True)
    assert approved.ok and approved.remote_after == target
    assert all(git("rev-parse", "refs/heads/main", cwd=repo) == target for repo in (primary, secondary))


def test_post_buffer_overflow_retries_once(tmp_path: Path) -> None:
    from blackhole_agent.publication_resilience import (
        POST_BUFFER_RETRY_BYTES,
        is_post_buffer_overflow,
    )

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

    pushes = exercise_transport_retry(tmp_path, harvested)
    assert f"http.postBuffer={POST_BUFFER_RETRY_BYTES}" in pushes[1]
    assert "http.postBuffer=" not in " ".join(pushes[0])


def test_schannel_handshake_retries_the_same_push_once(tmp_path: Path) -> None:
    from blackhole_agent.publication_resilience import (
        is_post_buffer_overflow,
        is_schannel_handshake_failure,
    )

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

    pushes = exercise_transport_retry(tmp_path, handshake)
    assert pushes[0] == pushes[1]
    assert "http.postBuffer=" not in " ".join(pushes[0])


def test_http_transport_abort_retries_the_same_push_once(tmp_path: Path) -> None:
    from blackhole_agent.publication_resilience import (
        is_http_transport_abort,
        is_post_buffer_overflow,
        is_schannel_handshake_failure,
    )

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

    pushes = exercise_transport_retry(tmp_path, empty_reply)
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
