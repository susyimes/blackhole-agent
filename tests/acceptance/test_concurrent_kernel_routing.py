"""Observe which provider actually receives a turn after overlapping successes and quota failures."""

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from blackhole_agent.kernel_health import kernel_health_snapshot
from blackhole_agent.kernel_salvage import execute_kernel_turn_with_salvage
from blackhole_agent.unbound import KernelTurnResult

START = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
PROVIDERS = ("grok", "kimi", "cursor")


def turn(root, requested, now, on_call=None):
    calls = []
    state = SimpleNamespace(kernel=requested, repo_path=str(root), session_id="", session_started=False)

    def respond(state, prompt, turn_dir, **kwargs):
        calls.append(state.kernel)
        if on_call:
            try:
                on_call(state.kernel)
            except RuntimeError as error:
                artifact = turn_dir / "kernel" / f"latest-{state.kernel}-run.json"
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text(json.dumps({"returncode": 1, "stderr_tail": str(error)}), encoding="utf-8")
                raise
        return KernelTurnResult(state.kernel, '{"status":"continue","summary":"served"}', "", (), "")

    execute_kernel_turn_with_salvage(
        state, "check service", root / uuid4().hex, kernel_runner=respond,
        installed_kernels={*PROVIDERS, requested}, now=now, probe_peers=False,
    )
    return calls


def worker(mode, root):
    if mode == "fail":
        def exhaust(provider):
            if provider in ("grok", "kimi"):
                raise RuntimeError("API error (status 402 Payment Required): usage balance exhausted")

        return turn(root, "grok", START, exhaust)
    during = START + timedelta(minutes=1)
    later = START + timedelta(hours=7)
    return {
        "during_cooldown": [turn(root, name, during) for name in ("grok", "kimi")],
        "after_cooldown": turn(root, "grok", later),
        "ready_after_recovery": kernel_health_snapshot(root, now=later)["ready"],
    }


def in_new_process(mode, root):
    output = subprocess.check_output([sys.executable, __file__, mode, str(root)], text=True, timeout=30)
    return json.loads(output)


def observe():
    observed = {}
    with tempfile.TemporaryDirectory() as scratch:
        for slow in ("cursor", "grok", "codex", "kimi"):
            root = Path(scratch) / slow
            case = observed[slow] = {}

            def overlap(provider):
                # The original turn has dispatched. Another process records both refusals before it returns.
                if provider == slow and "quota_failover" not in case:
                    case["quota_failover"] = in_new_process("fail", root)
                    if slow == "codex":
                        raise RuntimeError("CLI exited during the request")
                    if slow == "kimi":
                        raise RuntimeError("Error: Session ID fixture-session is already in use.")

            case["overlapping_request"] = turn(root, slow, START, overlap)
            case.update(in_new_process("route", root))
    passed = all(
        case["overlapping_request"] == ([slow, "cursor"] if slow in {"codex", "kimi"} else [slow])
        and case["quota_failover"] == list(PROVIDERS)
        and case["during_cooldown"] == [["cursor"], ["cursor"]]
        and case["after_cooldown"] == ["grok"] and "grok" in case["ready_after_recovery"]
        for slow, case in observed.items()
    )
    return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    result = worker(sys.argv[1], Path(sys.argv[2])) if len(sys.argv) == 3 else observe()
    print(json.dumps(result))
