"""A Kimi kernel that cannot fetch an access token must not be launched again.

Harvested runs (2026-08-02 and 2026-08-03) exited 1 with
provider.connection_error and "failed to fetch an access token" after a TLS
disconnect, ENOTFOUND auth.kimi.com, or ECONNRESET. A session id was often
already present, so the empty-session transport rule did not match, and the
death stayed a retryable CLI error. The next resolution launched Kimi again.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

HARVESTED_KIMI_TOKEN_TLS = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": "",
    "stderr_tail": (
        "error: failed to run prompt: provider.connection_error: OAuth provider "
        '"managed:kimi-code" failed to fetch an access token: OAuth request to '
        "https://auth.kimi.com/api/oauth/token failed: fetch failed: Client network "
        "socket disconnected before secure TLS connection was established\n"
        "See log: C:/Users/svmes/.kimi-code/logs/kimi-code.log\n"
    ),
    "last_message": "",
    "session_id": "session_fb6168fb-ca57-4fa5-851f-16f00d85139b",
}
HARVESTED_KIMI_TOKEN_DNS = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": "",
    "stderr_tail": (
        "error: failed to run prompt: provider.connection_error: OAuth provider "
        '"managed:kimi-code" failed to fetch an access token: OAuth request to '
        "https://auth.kimi.com/api/oauth/token failed: fetch failed: "
        "getaddrinfo ENOTFOUND auth.kimi.com\n"
    ),
    "last_message": "",
    "session_id": "",
}
KIMI_ERROR = (
    "Kimi CLI failed with exit code 1; result details were written to latest-kimi-run.json."
)


def _continue_message(summary: str) -> str:
    return json.dumps(
        {
            "status": "continue",
            "summary": summary,
            "strategy": "continue",
            "next_step": "continue the mission",
            "capability_delta": "",
            "outcome_evidence": [],
            "validation": [],
            "done_when_met": False,
        }
    )


def observe() -> tuple[bool, dict]:
    from blackhole_agent.kernel_health import kernel_is_available, load_kernel_health
    from blackhole_agent.kernel_salvage import (
        classify_kernel_failure,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
    )
    from blackhole_agent.unbound import KernelTurnResult

    token_tls = classify_run_artifact(HARVESTED_KIMI_TOKEN_TLS, error=KIMI_ERROR)
    token_dns = classify_run_artifact(HARVESTED_KIMI_TOKEN_DNS, error=KIMI_ERROR)
    socket_reset = classify_kernel_failure(
        returncode=1,
        stderr_tail="fetch failed: read ECONNRESET",
        session_id="session_fb6168fb-ca57-4fa5-851f-16f00d85139b",
        error="Kimi CLI failed with exit code 1",
    )
    established_tls = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "Client network socket disconnected before secure TLS connection was established"
        ),
        session_id="already-open",
        error="Cursor CLI failed with exit code 1",
    )
    empty_session_tls = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "Client network socket disconnected before secure TLS connection was established"
        ),
        session_id="",
        error="Cursor CLI failed with exit code 1",
    )
    calls: dict[str, list[str]] = {"first": [], "second": []}

    class _State:
        kernel = "kimi"
        session_id = "session_fb6168fb-ca57-4fa5-851f-16f00d85139b"
        session_started = True
        model = "kimi"
        repo_path = ""

    def runner(bucket: str):
        def run(state, prompt, turn_dir, **kwargs):
            del prompt, kwargs
            calls[bucket].append(state.kernel)
            if state.kernel == "kimi":
                kernel_dir = Path(turn_dir) / "kernel"
                kernel_dir.mkdir(parents=True, exist_ok=True)
                (kernel_dir / "latest-kimi-run.json").write_text(
                    json.dumps(HARVESTED_KIMI_TOKEN_TLS),
                    encoding="utf-8",
                )
                raise RuntimeError(KIMI_ERROR)
            return KernelTurnResult(
                kernel=state.kernel,
                last_message=_continue_message(f"{state.kernel} continued"),
                session_id="peer-session",
                command=(state.kernel,),
                result_path="",
            )

        return run

    with tempfile.TemporaryDirectory(prefix="oauth-token-fetch-") as tmp:
        repo = Path(tmp)
        first = _State()
        first.repo_path = str(repo)
        _result, first_decision, first_meta = execute_kernel_turn_with_salvage(
            first,
            "prompt",
            repo / "turn-1",
            kernel_runner=runner("first"),
            installed_kernels={"kimi", "codex"},
            probe_peers=False,
        )
        health = load_kernel_health(repo)
        breaker = health.kernels.get("kimi")
        circuit_open = not kernel_is_available(health, "kimi")
        circuit_class = breaker.class_id if breaker is not None else ""
        second = _State()
        second.repo_path = str(repo)
        _second_result, second_decision, second_meta = execute_kernel_turn_with_salvage(
            second,
            "prompt",
            repo / "turn-2",
            kernel_runner=runner("second"),
            installed_kernels={"kimi", "codex"},
            probe_peers=False,
        )

    observed = {
        "token_tls_class": token_tls.class_id,
        "token_tls_retryable": token_tls.retryable,
        "token_dns_class": token_dns.class_id,
        "token_dns_retryable": token_dns.retryable,
        "socket_reset_class": socket_reset.class_id,
        "socket_reset_retryable": socket_reset.retryable,
        "established_tls_class": established_tls.class_id,
        "established_tls_retryable": established_tls.retryable,
        "empty_session_tls_class": empty_session_tls.class_id,
        "first_calls": calls["first"],
        "first_status": first_decision.status,
        "first_source": first_meta.get("source"),
        "first_class": first_meta.get("class_id"),
        "first_failover": first_meta.get("failover_kernel"),
        "first_kernel": first.kernel,
        "circuit_open": circuit_open,
        "circuit_class": circuit_class,
        "second_calls": calls["second"],
        "second_status": second_decision.status,
        "second_kernel": second.kernel,
        "second_rerouted_from": second_meta.get("rerouted_from"),
    }
    passed = bool(
        token_tls.class_id == "auth_failed"
        and token_tls.retryable is False
        and token_dns.class_id == "auth_failed"
        and token_dns.retryable is False
        and socket_reset.class_id == "cli_error"
        and socket_reset.retryable is True
        and established_tls.class_id == "cli_error"
        and established_tls.retryable is True
        and empty_session_tls.class_id == "pre_session_transport_abort"
        and calls["first"] == ["kimi", "codex"]
        and first_decision.status == "continue"
        and first_meta.get("source") == "failover"
        and first_meta.get("class_id") == "auth_failed"
        and first_meta.get("failover_kernel") == "codex"
        and first.kernel == "codex"
        and circuit_open is True
        and circuit_class == "auth_failed"
        and calls["second"] == ["codex"]
        and "kimi" not in calls["second"]
        and second_decision.status == "continue"
        and second.kernel == "codex"
        and second_meta.get("rerouted_from") == "kimi"
    )
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcomes must still print JSON
        passed = False
        observed = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
