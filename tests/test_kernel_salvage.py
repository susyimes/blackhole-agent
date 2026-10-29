import json

from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_salvage import (
    HARVESTED_GROK_402,
    builtin_kernel_decision_salvage_proof,
    classify_kernel_failure,
    classify_run_artifact,
    salvage_kernel_failure,
    select_failover_kernel,
)


def test_harvested_402_is_quota_and_failsover_to_local_without_peer():
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    assert failure.class_id == "quota_exhausted"
    assert failure.retryable is False

    salvaged = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels=set(),
    )
    assert salvaged.decision["status"] == "continue"
    assert salvaged.failover_kernel == LOCAL_KERNEL

    blocked = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels=set(),
        allow_failover=False,
    )
    assert blocked.decision["status"] == "blocked"
    assert blocked.failover_kernel == ""


def test_quota_failsover_to_installed_peer_and_salvages_embedded_decision():
    salvaged = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels={"codex", "kimi"},
    )
    assert salvaged.failover_kernel == "codex"
    assert salvaged.decision["status"] == "continue"
    assert select_failover_kernel("grok", {"kimi"}) == "kimi"

    embedded = salvage_kernel_failure(
        error="exit 1",
        current_kernel="grok",
        last_message=json.dumps({"status": "continue", "summary": "partial"}),
        installed_kernels=set(),
    )
    assert embedded.source == "message"
    assert embedded.decision["summary"] == "partial"


def test_occupied_session_releases_once_then_the_same_kernel_continues():
    occupied = "f187f002-4163-45d5-bb0b-affc94cd98b0"
    other = "a10d7289-5951-4c1f-875b-82c5973b88c7"
    stderr = f"Error: Error: Session ID {occupied} is already in use.\n"
    artifact = {
        "returncode": 1,
        "timed_out": False,
        "stdout_tail": "",
        "stderr_tail": stderr,
        "last_message": "",
    }
    failure = classify_run_artifact(
        artifact,
        error="Grok CLI failed with exit code 1; result details were written to latest-grok-run.json.",
    )
    assert failure.class_id == "session_already_in_use"
    assert failure.retryable is False
    other_failure = classify_run_artifact(
        {**artifact, "stderr_tail": f"Error: Error: Session ID {other} is already in use.\n"},
        error="Grok CLI failed with exit code 1",
    )
    assert other_failure.class_id == "session_already_in_use"

    salvaged = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=artifact,
        installed_kernels={"grok", "cursor"},
    )
    assert salvaged.failover_kernel == ""
    assert salvaged.decision["status"] == "continue"
    assert "fresh session" in salvaged.decision["next_step"].lower()
    assert "grok" in salvaged.decision["next_step"].lower()


def test_missing_remote_session_is_not_a_retryable_cli_error():
    missing = "5e8a33de-5b06-42a7-b238-d3106f402fb2"
    artifact = {
        "returncode": 1,
        "timed_out": False,
        "stdout_tail": "",
        "stderr_tail": (
            "WARN auto worktree gc failed error=neither $GROK_HOME nor $HOME is set\n"
            f'Session "{missing}" not found locally, restoring conversation from remote...\n'
            "Error: Failed to restore session from remote: fetching session record: "
            "session get failed: 404 Not Found\n"
        ),
        "last_message": "",
        "command": ["grok", "--resume", missing],
    }
    failure = classify_run_artifact(
        artifact,
        error="Grok CLI failed with exit code 1; result details were written to latest-grok-run.json.",
    )
    assert failure.class_id == "session_not_found"
    assert failure.retryable is False
    salvaged = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=artifact,
        installed_kernels={"grok", "cursor"},
    )
    assert salvaged.failover_kernel == ""
    assert salvaged.decision["status"] == "continue"
    assert "fresh session" in salvaged.decision["next_step"].lower()
    bare = classify_kernel_failure(
        returncode=1,
        stderr_tail="404 Not Found",
        error="Grok CLI failed with exit code 1",
    )
    assert bare.class_id == "cli_error"
    assert bare.retryable is True
    quoted = classify_kernel_failure(
        returncode=0,
        last_message="Failed to restore session from remote: session get failed: 404 Not Found",
    )
    assert quoted.class_id != "session_not_found"


def test_second_occupied_session_collision_failsover_instead_of_looping():
    import tempfile
    from pathlib import Path

    from blackhole_agent.kernel_salvage import execute_kernel_turn_with_salvage
    from blackhole_agent.unbound import KernelTurnResult

    stderr = "Error: Error: Session ID occupied-id is already in use.\n"
    calls: list[str] = []

    class _State:
        kernel = "grok"
        session_id = "occupied-id"
        session_started = False
        model = "grok-4.6"
        repo_path = ""

    def runner(state, prompt, turn_dir, **kwargs):
        del prompt, kwargs
        calls.append(state.kernel)
        kernel_dir = Path(turn_dir) / "kernel"
        kernel_dir.mkdir(parents=True, exist_ok=True)
        (kernel_dir / f"latest-{state.kernel}-run.json").write_text(
            json.dumps(
                {
                    "returncode": 1,
                    "stderr_tail": stderr,
                    "stdout_tail": "",
                    "last_message": "",
                    "timed_out": False,
                }
            ),
            encoding="utf-8",
        )
        if state.kernel == "kimi":
            return KernelTurnResult(
                kernel="kimi",
                last_message=json.dumps({"status": "continue", "summary": "peer"}),
                session_id="peer",
                command=("kimi",),
                result_path="",
            )
        raise RuntimeError("Grok CLI failed with exit code 1")

    state = _State()
    with tempfile.TemporaryDirectory(prefix="occupied-session-loop-") as tmp:
        _result, decision, meta = execute_kernel_turn_with_salvage(
            state,
            "prompt",
            Path(tmp) / "turn",
            kernel_runner=runner,
            installed_kernels={"grok", "kimi"},
            probe_peers=False,
            persist_health=False,
        )
    assert calls == ["grok", "grok", "kimi"]
    assert state.kernel == "kimi"
    assert decision.status == "continue"
    assert meta.get("source") == "failover"


def test_pre_session_tls_abort_is_not_a_retryable_cli_error():
    artifact = {
        "returncode": 1,
        "timed_out": False,
        "stdout_tail": "",
        "stderr_tail": (
            "Error: [aborted] Client network socket disconnected before secure "
            "TLS connection was established\n\nmissing terminal result"
        ),
        "last_message": "",
        "session_id": "",
        "decision_final": False,
    }
    failure = classify_run_artifact(
        artifact,
        error="Cursor CLI failed (exit 1): " + artifact["stderr_tail"],
    )
    assert failure.class_id == "pre_session_transport_abort"
    assert failure.retryable is False

    salvaged = salvage_kernel_failure(
        error="Cursor CLI failed (exit 1): " + artifact["stderr_tail"],
        current_kernel="cursor",
        artifact=artifact,
        installed_kernels={"grok", "cursor"},
    )
    assert salvaged.failover_kernel == "grok"
    assert salvaged.decision["status"] == "continue"
    assert "grok" in salvaged.decision["next_step"].lower()

    established = classify_run_artifact({**artifact, "session_id": "already-open"})
    assert established.class_id != "pre_session_transport_abort"


def test_spending_limit_403_is_quota_and_bare_forbidden_is_not():
    spending = classify_run_artifact(
        {
            "returncode": 1,
            "timed_out": False,
            "stdout_tail": (
                '{"type":"error","message":"API error (status 403 Forbidden): '
                'personal-team-blocked:spending-limit: You have run out of credits"}'
            ),
            "stderr_tail": (
                "status=403 Forbidden error_message=personal-team-blocked:spending-limit: "
                "You have run out of credits"
            ),
            "last_message": "",
            "session_id": "",
        },
        error="Grok CLI failed with exit code 1",
    )
    assert spending.class_id == "quota_exhausted"
    assert spending.retryable is False
    kimi = classify_run_artifact(
        {
            "returncode": 1,
            "stderr_tail": (
                "provider.auth_error: 403 You've reached your usage limit for this billing cycle."
            ),
            "last_message": "",
        },
        error="Kimi CLI failed with exit code 1",
    )
    assert kimi.class_id == "quota_exhausted"
    assert kimi.retryable is False
    bare = classify_run_artifact(
        {"returncode": 1, "stderr_tail": "HTTP 403 Forbidden", "last_message": ""},
        error="request failed",
    )
    assert bare.class_id == "cli_error"
    assert bare.retryable is True


def test_rejected_model_failsover_and_unknown_model_warning_does_not():
    cursor = {
        "returncode": 1,
        "timed_out": False,
        "stdout_tail": "",
        "stderr_tail": (
            "Cannot use this model: grok-4.7-xhigh. Available models: \n\n"
            "missing terminal result"
        ),
        "last_message": "",
        "session_id": "",
        "decision_final": False,
    }
    failure = classify_run_artifact(
        cursor,
        error="Cursor CLI failed (exit 1): " + cursor["stderr_tail"],
    )
    assert failure.class_id == "model_unavailable"
    assert failure.retryable is False
    salvaged = salvage_kernel_failure(
        error="Cursor CLI failed (exit 1): " + cursor["stderr_tail"],
        current_kernel="cursor",
        artifact=cursor,
        installed_kernels={"grok", "cursor"},
    )
    assert salvaged.failover_kernel == "grok"
    assert salvaged.decision["status"] == "continue"
    assert "grok" in salvaged.decision["next_step"].lower()

    kimi = classify_run_artifact(
        {
            "returncode": 1,
            "stderr_tail": (
                'error: failed to run prompt: Model "grok-4.6" is not configured '
                "in config.toml."
            ),
            "last_message": "",
            "session_id": "",
        },
        error="Kimi CLI failed with exit code 1",
    )
    assert kimi.class_id == "model_unavailable"
    assert kimi.retryable is False

    warning = classify_run_artifact(
        {
            "returncode": 1,
            "stderr_tail": (
                "Unknown model grok-4.6 is used. This will use fallback model metadata."
            ),
            "last_message": "",
        },
        error="Codex CLI failed with exit code 1",
    )
    assert warning.class_id == "cli_error"
    assert warning.retryable is True


def test_token_fetch_failure_is_auth_and_a_socket_reset_is_not():
    tls = {
        "returncode": 1,
        "timed_out": False,
        "stdout_tail": "",
        "stderr_tail": (
            "error: failed to run prompt: provider.connection_error: OAuth provider "
            '"managed:kimi-code" failed to fetch an access token: OAuth request to '
            "https://auth.kimi.com/api/oauth/token failed: fetch failed: Client network "
            "socket disconnected before secure TLS connection was established\n"
        ),
        "last_message": "",
        "session_id": "session_fb6168fb-ca57-4fa5-851f-16f00d85139b",
    }
    failure = classify_run_artifact(tls, error="Kimi CLI failed with exit code 1")
    assert failure.class_id == "auth_failed"
    assert failure.retryable is False
    salvaged = salvage_kernel_failure(
        error="Kimi CLI failed with exit code 1",
        current_kernel="kimi",
        artifact=tls,
        installed_kernels={"kimi", "codex"},
    )
    assert salvaged.failover_kernel == "codex"
    assert salvaged.decision["status"] == "continue"

    dns = classify_run_artifact(
        {
            "returncode": 1,
            "stderr_tail": (
                "provider.connection_error: OAuth provider "
                '"managed:kimi-code" failed to fetch an access token: '
                "getaddrinfo ENOTFOUND auth.kimi.com"
            ),
            "last_message": "",
            "session_id": "",
        },
        error="Kimi CLI failed with exit code 1",
    )
    assert dns.class_id == "auth_failed"
    assert dns.retryable is False

    reset = classify_run_artifact(
        {
            "returncode": 1,
            "stderr_tail": "fetch failed: read ECONNRESET",
            "last_message": "",
            "session_id": "session_fb6168fb-ca57-4fa5-851f-16f00d85139b",
        },
        error="Kimi CLI failed with exit code 1",
    )
    assert reset.class_id == "cli_error"
    assert reset.retryable is True

    established_tls = classify_run_artifact(
        {
            "returncode": 1,
            "stderr_tail": (
                "Client network socket disconnected before secure TLS connection was established"
            ),
            "last_message": "",
            "session_id": "already-open",
        },
        error="Cursor CLI failed with exit code 1",
    )
    assert established_tls.class_id == "cli_error"
    assert established_tls.retryable is True


def test_provider_overload_is_not_quota_or_a_bare_429():
    overload = classify_run_artifact(
        {
            "returncode": 1,
            "stderr_tail": (
                "error: failed to run prompt: provider.rate_limit: 429 "
                "The engine is currently overloaded, please try again later\n"
            ),
            "stdout_tail": (
                '{"error_name":"APIProviderRateLimitError",'
                '"error_message":"429 The engine is currently overloaded, please try again later"}'
            ),
            "last_message": "",
            "session_id": "session_101821fc-f52d-4822-ba75-9729754be536",
        },
        error="Kimi CLI failed with exit code 1",
    )
    assert overload.class_id == "provider_overloaded"
    assert overload.retryable is False
    salvaged = salvage_kernel_failure(
        error="Kimi CLI failed with exit code 1",
        current_kernel="kimi",
        artifact={
            "returncode": 1,
            "stderr_tail": (
                "provider.rate_limit: 429 The engine is currently overloaded, "
                "please try again later"
            ),
            "last_message": "",
            "session_id": "session_101821fc-f52d-4822-ba75-9729754be536",
        },
        installed_kernels={"kimi", "grok"},
    )
    assert salvaged.failover_kernel == "grok"
    assert salvaged.decision["status"] == "continue"

    bare = classify_kernel_failure(
        returncode=1,
        stderr_tail="warning: status_code=429 left in an unrelated log line",
        error="Kimi CLI failed with exit code 1",
    )
    assert bare.class_id == "cli_error"
    assert bare.retryable is True

    zero_exit = classify_kernel_failure(
        returncode=0,
        stderr_tail="provider.rate_limit: 429 The engine is currently overloaded",
        last_message="finished",
    )
    assert zero_exit.class_id != "provider_overloaded"


def test_builtin_proof_replays_harvested_failure():
    report = builtin_kernel_decision_salvage_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_decision_salvage"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
