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

    codex_account = classify_run_artifact(
        {
            "returncode": 1,
            "stdout_tail": (
                "The 'grok-4.6' model is not supported when using Codex with a ChatGPT account."
            ),
            "stderr_tail": (
                "Unknown model grok-4.6 is used. This will use fallback model metadata."
            ),
            "last_message": "",
        },
        error="Codex CLI failed with exit code 1",
    )
    assert codex_account.class_id == "model_unavailable"
    assert codex_account.retryable is False
    codex_salvage = salvage_kernel_failure(
        error="Codex CLI failed with exit code 1",
        current_kernel="codex",
        artifact={
            "returncode": 1,
            "stdout_tail": (
                "The 'grok-4.6' model is not supported when using Codex with a ChatGPT account."
            ),
            "last_message": "",
        },
        installed_kernels={"codex", "grok"},
    )
    assert codex_salvage.failover_kernel == "grok"
    assert codex_salvage.decision["status"] == "continue"


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


def test_codex_responses_404_is_not_a_retryable_cli_error():
    missing = classify_run_artifact(
        {
            "returncode": 1,
            "stdout_tail": (
                '{"type":"turn.failed","error":{"message":"unexpected status 404 Not Found: '
                'Unknown error, url: https://chatgpt.com/backend-api/codex/responses"}}'
            ),
            "stderr_tail": (
                "failed to connect to websocket: HTTP error: 404 Not Found, "
                "url: wss://chatgpt.com/backend-api/codex/responses"
            ),
            "last_message": "",
            "session_id": "01a067d1-2173-7fb2-9cae-f3b9b80e0910",
        },
        error="Codex CLI failed with exit code 1",
    )
    assert missing.class_id == "responses_endpoint_missing"
    assert missing.retryable is False
    salvaged = salvage_kernel_failure(
        error="Codex CLI failed with exit code 1",
        current_kernel="codex",
        artifact={
            "returncode": 1,
            "stdout_tail": (
                "unexpected status 404 Not Found: Unknown error, "
                "url: https://chatgpt.com/backend-api/codex/responses"
            ),
            "last_message": "",
            "session_id": "01a067d1-2173-7fb2-9cae-f3b9b80e0910",
        },
        installed_kernels={"codex", "grok"},
    )
    assert salvaged.failover_kernel == "grok"
    assert salvaged.decision["status"] == "continue"

    bare = classify_kernel_failure(
        returncode=1,
        stderr_tail="warning: upstream returned 404 Not Found for an unrelated asset",
        error="Codex CLI failed with exit code 1",
    )
    assert bare.class_id == "cli_error"
    assert bare.retryable is True

    session_404 = classify_kernel_failure(
        returncode=1,
        stderr_tail="Failed to restore session from remote\nsession get failed: 404 Not Found",
        error="Grok CLI failed with exit code 1",
    )
    assert session_404.class_id == "session_not_found"

    zero_exit = classify_kernel_failure(
        returncode=0,
        stderr_tail=(
            "unexpected status 404 Not Found, url: https://chatgpt.com/backend-api/codex/responses"
        ),
        last_message="finished",
    )
    assert zero_exit.class_id != "responses_endpoint_missing"


def test_kimi_connection_error_after_step_retries_is_not_retryable():
    death = classify_run_artifact(
        {
            "returncode": 1,
            "stderr_tail": (
                "error: failed to run prompt: provider.connection_error: Connection error.\n"
                "See log: C:/Users/svmes/.kimi-code/logs/kimi-code.log\n"
            ),
            "stdout_tail": (
                '{"role":"meta","type":"turn.step.retrying","failed_attempt":1,'
                '"next_attempt":2,"max_attempts":3,"error_name":"APIConnectionError",'
                '"error_message":"Connection error."}\n'
                '{"role":"meta","type":"turn.step.retrying","failed_attempt":2,'
                '"next_attempt":3,"max_attempts":3,"error_name":"APIConnectionError",'
                '"error_message":"Connection error."}\n'
            ),
            "last_message": "",
            "session_id": "session_5128790f-82f6-4329-a51a-6e93af6c126c",
        },
        error="Kimi CLI failed with exit code 1",
    )
    assert death.class_id == "provider_connection_failed"
    assert death.retryable is False
    salvaged = salvage_kernel_failure(
        error="Kimi CLI failed with exit code 1",
        current_kernel="kimi",
        artifact={
            "returncode": 1,
            "stderr_tail": "failed to run prompt: provider.connection_error: Connection error.",
            "stdout_tail": (
                '{"type":"turn.step.retrying","error_name":"APIConnectionError",'
                '"error_message":"Connection error."}'
            ),
            "last_message": "",
            "session_id": "session_5128790f-82f6-4329-a51a-6e93af6c126c",
        },
        installed_kernels={"kimi", "grok"},
    )
    assert salvaged.failover_kernel == "grok"
    assert salvaged.decision["status"] == "continue"

    bare = classify_kernel_failure(
        returncode=1,
        stderr_tail="warning: Connection error. left in an unrelated log line",
        error="Kimi CLI failed with exit code 1",
    )
    assert bare.class_id == "cli_error"
    assert bare.retryable is True

    token_fetch = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "error: failed to run prompt: provider.connection_error: "
            'OAuth provider "managed:kimi-code" failed to fetch an access token: '
            "fetch failed: read ECONNRESET"
        ),
        error="Kimi CLI failed with exit code 1",
    )
    assert token_fetch.class_id == "auth_failed"
    assert token_fetch.retryable is False

    zero_exit = classify_kernel_failure(
        returncode=0,
        stderr_tail="provider.connection_error: Connection error.",
        stdout_tail='{"type":"turn.step.retrying","error_name":"APIConnectionError"}',
        last_message="finished",
    )
    assert zero_exit.class_id != "provider_connection_failed"


def test_grok_signed_out_is_not_retryable():
    death = classify_run_artifact(
        {
            "returncode": 1,
            "stderr_tail": (
                "WARN config: ignored unrecognized or invalid entry path=privacy\n"
                'WARN Failed to fetch models: Auth("No auth credentials for cli-chat-proxy")\n'
                "Error: Not signed in. Run `grok login` to authenticate "
                "(or `grok login --device-code` if no browser is available).\n"
            ),
            "stdout_tail": (
                '{"type":"error","message":"Not signed in. Run `grok login` to authenticate '
                '(or `grok login --device-code` if no browser is available)."}\n'
            ),
            "last_message": "",
            "session_id": "",
        },
        error="Grok CLI failed with exit code 1",
    )
    assert death.class_id == "auth_failed"
    assert death.retryable is False
    salvaged = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact={
            "returncode": 1,
            "stderr_tail": "Error: Not signed in. Run `grok login` to authenticate.",
            "stdout_tail": '{"type":"error","message":"Not signed in. Run `grok login`."}',
            "last_message": "",
        },
        installed_kernels={"grok", "codex"},
    )
    assert salvaged.class_id == "auth_failed"
    assert salvaged.failover_kernel == "codex"
    assert salvaged.decision["status"] == "continue"

    warning = classify_kernel_failure(
        returncode=1,
        stderr_tail='WARN Failed to fetch models: Auth("No auth credentials for cli-chat-proxy")',
        error="Grok CLI failed with exit code 1",
    )
    assert warning.class_id == "cli_error"
    assert warning.retryable is True

    zero_exit = classify_kernel_failure(
        returncode=0,
        stderr_tail="Error: Not signed in. Run `grok login` to authenticate.",
        last_message="finished",
    )
    assert zero_exit.class_id != "auth_failed"


def test_grok_response_stream_is_not_retryable():
    decode = classify_run_artifact(
        {
            "returncode": 1,
            "stderr_tail": (
                'ERROR error=Internal error: "reqwest error stream: Transport error: '
                'error decoding response body"'
            ),
            "stdout_tail": (
                '{"type":"error","message":"Internal error: reqwest error stream: '
                'Transport error: error decoding response body"}'
            ),
            "last_message": "",
            "command": ["grok.EXE", "--session-id", "ee2bb879-65e7-4691-93ce-892d36f159c8"],
        },
        error="Grok CLI failed with exit code 1",
    )
    assert decode.class_id == "response_stream_failed"
    assert decode.retryable is False

    sending = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "ERROR error=Internal error: "
            '"reqwest error stream: error sending request for url '
            '(https://cli-chat-proxy.grok.com/v1/responses)"'
        ),
        error="Grok CLI failed with exit code 1",
    )
    assert sending.class_id == "response_stream_failed"
    assert sending.retryable is False

    salvaged = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact={
            "returncode": 1,
            "stderr_tail": (
                'ERROR error=Internal error: "reqwest error stream: '
                'error decoding response body"'
            ),
            "last_message": "",
        },
        installed_kernels={"grok", "codex"},
    )
    assert salvaged.class_id == "response_stream_failed"
    assert salvaged.failover_kernel == "codex"
    assert salvaged.decision["status"] == "continue"

    telemetry = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            'ERROR name="BatchSpanProcessor.ExportError" '
            'error="Operation failed: HTTP export failed: network error"'
        ),
        error="Grok CLI failed with exit code 1",
    )
    assert telemetry.class_id == "cli_error"
    assert telemetry.retryable is True

    settings_fetch = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "WARN Settings fetch network error: error sending request for url "
            "(https://cli-chat-proxy.grok.com/v1/settings) attempt=2\n"
            "ERROR Settings fetch failed after 3 attempts"
        ),
        error="Grok CLI failed with exit code 1",
    )
    assert settings_fetch.class_id == "cli_error"
    assert settings_fetch.retryable is True

    zero_exit = classify_kernel_failure(
        returncode=0,
        stderr_tail='ERROR error=Internal error: "reqwest error stream: error decoding response body"',
        last_message="finished",
    )
    assert zero_exit.class_id != "response_stream_failed"

    hidden_by_mcp_timeout = classify_kernel_failure(
        returncode=1,
        timed_out=False,
        stderr_tail=(
            "WARN MCP server init failed server=gmail error=MCP server 'gmail' timed out after 90s\n"
            "ERROR error=Internal error: "
            '"reqwest error stream: error sending request for url '
            '(https://cli-chat-proxy.grok.com/v1/responses)"\n'
        ),
        error="Grok CLI failed with exit code 1",
    )
    assert hidden_by_mcp_timeout.class_id == "response_stream_failed"
    assert hidden_by_mcp_timeout.retryable is False

    bare_mcp_timeout = classify_kernel_failure(
        returncode=1,
        timed_out=False,
        stderr_tail="WARN MCP server init failed server=gmail error=MCP server 'gmail' timed out after 90s\n",
        error="Grok CLI failed with exit code 1",
    )
    assert bare_mcp_timeout.class_id == "timeout"
    assert bare_mcp_timeout.retryable is True


def test_grok_inference_idle_timeout_is_not_a_tool_timeout():
    from blackhole_agent.kernel_salvage import INFERENCE_IDLE_TIMEOUT, classify_run_artifact

    harvested = classify_run_artifact(
        {
            "returncode": 124,
            "timed_out": True,
            "stderr_tail": (
                "WARN grep timed out timeout_secs=20\n"
                'ERROR error=Internal error: "inference idle timeout after 3600s with no chunks"\n'
                "WARN auth: file lock timed out, waiting for sibling to finish\n"
            ),
            "stdout_tail": (
                '{"type":"error","message":"inference idle timeout after 3600s with no chunks"}'
            ),
            "last_message": (
                'Internal error: {\n  "message": "inference idle timeout after 3600s with no chunks"\n}'
            ),
            "command": ["grok.EXE", "--session-id", "a3f87572-fb23-4403-9500-d6ad0149baa9"],
        },
        error="Grok CLI timed out after 7200 seconds",
    )
    assert harvested.class_id == INFERENCE_IDLE_TIMEOUT
    assert harvested.retryable is False

    bare_timeout = classify_run_artifact(
        {
            "returncode": 124,
            "timed_out": True,
            "stderr_tail": "WARN grep timed out timeout_secs=20\nWARN auth: file lock timed out\n",
            "last_message": "",
        },
        error="Grok CLI timed out after 7200 seconds",
    )
    assert bare_timeout.class_id == "timeout"
    assert bare_timeout.retryable is True

    zero_exit = classify_run_artifact(
        {
            "returncode": 0,
            "timed_out": False,
            "stderr_tail": 'ERROR error=Internal error: "inference idle timeout after 3600s with no chunks"',
            "last_message": "finished",
        },
    )
    assert zero_exit.class_id != INFERENCE_IDLE_TIMEOUT


def test_grok_doom_loop_is_not_a_tool_timeout():
    from blackhole_agent.kernel_salvage import DOOM_LOOP_REPETITION, classify_run_artifact

    session = "49babe86-c4a7-44ad-a8ce-0608c2acd2c8"
    harvested = classify_run_artifact(
        {
            "returncode": 124,
            "timed_out": True,
            "stderr_tail": (
                "WARN grep timed out timeout_secs=20\n"
                "WARN doom-loop recovery: retaining the failed response and retrying with guidance "
                "reason=doom loop detected: tail_repetition:64@thinking attempt=1 "
                'max_retries=2 outcome="resampled_with_reminder"\n'
            ),
            "last_message": "Still inspecting the repository.",
            "command": ["grok.EXE", "--session-id", session],
        },
        error="Grok CLI timed out after 7200 seconds",
    )
    assert harvested.class_id == DOOM_LOOP_REPETITION
    assert harvested.retryable is False

    bare_timeout = classify_run_artifact(
        {
            "returncode": 124,
            "timed_out": True,
            "stderr_tail": "WARN grep timed out timeout_secs=20\n",
            "last_message": "",
        },
        error="Grok CLI timed out after 7200 seconds",
    )
    assert bare_timeout.class_id == "timeout"
    assert bare_timeout.retryable is True

    zero_exit = classify_run_artifact(
        {
            "returncode": 0,
            "timed_out": False,
            "stderr_tail": (
                "WARN doom-loop recovery: resample budget spent "
                "reason=doom loop detected: tail_repetition:64@thinking\n"
            ),
            "last_message": "finished",
        },
    )
    assert zero_exit.class_id != DOOM_LOOP_REPETITION


def test_grok_dead_session_actor_is_not_a_file_lock_timeout():
    from blackhole_agent.kernel_salvage import SESSION_ACTOR_DEAD, classify_run_artifact

    session = "858749f4-3c21-4375-955c-65c08166b900"
    harvested = classify_run_artifact(
        {
            "returncode": 124,
            "timed_out": True,
            "stderr_tail": (
                "WARN auth: file lock timed out, waiting for sibling to finish\n"
                "WARN Resident session actor exited unexpectedly; reaping as DeadFailed "
                f"session_id={session}\n"
            ),
            "stdout_tail": '{"num_turns": 26}',
            "last_message": "keep going",
            "command": ["grok.EXE", "--session-id", session],
        },
        error="Grok CLI timed out after 7200 seconds",
    )
    assert harvested.class_id == SESSION_ACTOR_DEAD
    assert harvested.retryable is False

    file_lock = classify_run_artifact(
        {
            "returncode": 124,
            "timed_out": True,
            "stderr_tail": "WARN auth: file lock timed out, waiting for sibling to finish\n",
            "last_message": "",
        },
        error="Grok CLI timed out after 7200 seconds",
    )
    assert file_lock.class_id == "timeout"
    assert file_lock.retryable is True

    zero_exit = classify_run_artifact(
        {
            "returncode": 0,
            "timed_out": False,
            "stderr_tail": (
                "WARN Resident session actor exited unexpectedly; reaping as DeadFailed "
                f"session_id={session}\n"
            ),
            "last_message": "finished",
        },
    )
    assert zero_exit.class_id != SESSION_ACTOR_DEAD


def test_grok_token_generation_500_is_not_a_tool_timeout():
    from blackhole_agent.kernel_salvage import TOKEN_GENERATION_FAILED, classify_run_artifact

    harvested = classify_run_artifact(
        {
            "returncode": 1,
            "timed_out": False,
            "stderr_tail": (
                "WARN grep timed out timeout_secs=20\n"
                "ERROR error=Internal error: API error (status 500 Internal Server Error): "
                "error: Internal error during token generation\n"
            ),
            "stdout_tail": (
                '{"type":"error","message":"API error (status 500 Internal Server Error): '
                'error: Internal error during token generation"}'
            ),
            "last_message": "",
            "command": ["grok.EXE", "--session-id", "9c8f416d-2184-4380-8ff1-0427cc159e94"],
        },
        error="Grok CLI failed with exit code 1",
    )
    assert harvested.class_id == TOKEN_GENERATION_FAILED
    assert harvested.retryable is False

    bare_timeout = classify_run_artifact(
        {
            "returncode": 124,
            "timed_out": True,
            "stderr_tail": "WARN grep timed out timeout_secs=20",
            "last_message": "",
        },
        error="Grok CLI timed out after 600 seconds",
    )
    assert bare_timeout.class_id == "timeout"
    assert bare_timeout.retryable is True


def test_grok_max_tokens_truncation_hidden_by_grep_timeout():
    from blackhole_agent.kernel_salvage import OUTPUT_TRUNCATED, classify_run_artifact

    harvested = classify_run_artifact(
        {
            "returncode": 1,
            "timed_out": False,
            "stderr_tail": (
                "WARN grep timed out timeout_secs=20\n"
                "ERROR error=Internal error: {\n"
                '  "message": "response truncated by max_tokens",\n'
                '  "error_kind": "max_tokens_truncation"\n'
                "}\n"
                "WARN Final signal sync timed out during exit\n"
            ),
            "stdout_tail": (
                '{"type":"error","message":"response truncated by max_tokens",'
                '"error_kind":"max_tokens_truncation","num_turns":25}'
            ),
            "last_message": "",
            "command": ["grok.EXE", "--session-id", "7878ab71-f28d-4a71-a2d6-bc40e293145e"],
        },
        error="Grok CLI failed with exit code 1",
    )
    assert harvested.class_id == OUTPUT_TRUNCATED
    assert harvested.retryable is False

    bare_timeout = classify_run_artifact(
        {
            "returncode": 1,
            "timed_out": False,
            "stderr_tail": "WARN grep timed out timeout_secs=20\n",
            "last_message": "",
        },
        error="Grok CLI failed with exit code 1",
    )
    assert bare_timeout.class_id == "timeout"
    assert bare_timeout.retryable is True

    one_phrase = classify_run_artifact(
        {
            "returncode": 1,
            "timed_out": False,
            "stderr_tail": (
                "WARN grep timed out timeout_secs=20\n"
                "notes mention max_tokens_truncation only\n"
            ),
            "last_message": "",
        },
        error="Grok CLI failed with exit code 1",
    )
    assert one_phrase.class_id == "timeout"

    clean = classify_run_artifact(
        {
            "returncode": 1,
            "timed_out": False,
            "stderr_tail": 'ERROR error=Internal error: "response truncated by max_tokens"',
            "last_message": "",
        },
        error="Grok CLI failed with exit code 1",
    )
    assert clean.class_id == OUTPUT_TRUNCATED

    zero_exit = classify_run_artifact(
        {
            "returncode": 0,
            "timed_out": False,
            "stderr_tail": (
                "response truncated by max_tokens error_kind max_tokens_truncation"
            ),
            "last_message": "finished",
        },
    )
    assert zero_exit.class_id != OUTPUT_TRUNCATED


def test_grok_auth_wake_blip_resumes_session_without_tripping_auth():
    from blackhole_agent.kernel_salvage import AUTH_TEMPORARILY_UNAVAILABLE, classify_run_artifact

    harvested = classify_run_artifact(
        {
            "returncode": 124,
            "timed_out": True,
            "stderr_tail": (
                "WARN headless: background wait timed out, exiting\n"
                "Authentication is temporarily unavailable (often a network blip right after wake). "
                "Your session is still signed in and will recover automatically. "
                "no need to run /login."
            ),
            "stdout_tail": "Unauthorized (401) from https://cli-chat-proxy.grok.com/v1/responses",
            "last_message": "",
            "command": ["grok.EXE", "--session-id", "2460a176-d5fb-457c-bd14-1bc6fd28b28e"],
        },
        error="Grok CLI timed out after 600 seconds",
    )
    assert harvested.class_id == AUTH_TEMPORARILY_UNAVAILABLE
    assert harvested.retryable is False

    bare_timeout = classify_run_artifact(
        {
            "returncode": 124,
            "timed_out": True,
            "stderr_tail": "WARN headless: background wait timed out, exiting",
            "last_message": "",
        },
        error="Grok CLI timed out after 600 seconds",
    )
    assert bare_timeout.class_id == "timeout"
    assert bare_timeout.retryable is True

    bare_401 = classify_run_artifact(
        {
            "returncode": 1,
            "timed_out": False,
            "stderr_tail": "ERROR Unauthorized (401) Invalid or expired credentials",
            "last_message": "",
        },
        error="Grok CLI failed with exit code 1",
    )
    assert bare_401.class_id == "auth_failed"

    zero_exit = classify_run_artifact(
        {
            "returncode": 0,
            "timed_out": False,
            "stderr_tail": (
                "Authentication is temporarily unavailable. "
                "Your session is still signed in. no need to run /login."
            ),
            "last_message": "finished",
        },
    )
    assert zero_exit.class_id != AUTH_TEMPORARILY_UNAVAILABLE


def test_builtin_proof_replays_harvested_failure():
    report = builtin_kernel_decision_salvage_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_decision_salvage"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
