"""A Kimi launch must not spawn when Windows cannot hold the prompt.

Harvested mission 20260731T101902Z-e1bfdef8 exited 1. The stderr bytes are
GBK "命令行太长。" decoded as UTF-8, which leaves U+FFFD around U+032B.
That death stayed a retryable CLI error, so the same kimi.CMD line was tried
again.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

# Exact stderr stored for kimi-run-20260731T102251Z.json.
HARVESTED_STDERR = "\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\u032b\ufffd\ufffd\ufffd\ufffd\n"
KIMI_ERROR = "Kimi CLI failed with exit code 1"
LONG_PROMPT = "x" * 12000


def _stream(message: str) -> str:
    return "\n".join(
        [
            json.dumps({"role": "assistant", "content": message}),
            json.dumps(
                {
                    "role": "meta",
                    "type": "session.resume_hint",
                    "session_id": "session-kimi-short",
                }
            ),
        ]
    )


def _launch(bin_path: Path, prompt: str, work: Path) -> tuple[list[list[str]], str]:
    from blackhole_agent.kernels.kimi_cli import KimiCliConfig, KimiCliKernel

    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append([str(part) for part in command])
        return subprocess.CompletedProcess(command, 0, stdout=_stream("ok"), stderr="")

    error = ""
    try:
        KimiCliKernel(
            KimiCliConfig(kimi_bin=str(bin_path)),
            command_runner=runner,
        ).run(prompt, cwd=work, output_dir=work / "out", timeout_seconds=5)
    except Exception as exc:  # noqa: BLE001 - the probe records the launch outcome
        error = str(exc)
    return calls, error


def observe() -> tuple[bool, dict]:
    from blackhole_agent.kernel_salvage import classify_kernel_failure, salvage_kernel_failure

    death = classify_kernel_failure(
        returncode=1,
        stderr_tail=HARVESTED_STDERR,
        error=KIMI_ERROR,
    )
    english = classify_kernel_failure(
        returncode=1,
        stderr_tail="The command line is too long.\n",
        error=KIMI_ERROR,
    )
    win206 = classify_kernel_failure(
        returncode=1,
        stderr_tail="The filename or extension is too long.\n",
        error=KIMI_ERROR,
    )
    bare = classify_kernel_failure(
        returncode=1,
        stderr_tail="warning: the path is too long\n",
        error=KIMI_ERROR,
    )
    zero = classify_kernel_failure(
        returncode=0,
        stderr_tail="The command line is too long.\n",
        last_message="finished",
        error="",
    )
    salvaged = salvage_kernel_failure(
        error=KIMI_ERROR,
        current_kernel="kimi",
        artifact={
            "returncode": 1,
            "timed_out": False,
            "stderr_tail": HARVESTED_STDERR,
            "stdout_tail": "",
            "last_message": "",
        },
        installed_kernels=set(),
        allow_failover=True,
    )
    with tempfile.TemporaryDirectory(prefix="kimi-cmd-limit-") as tmp:
        root = Path(tmp)
        cmd = root / "kimi.CMD"
        cmd.write_text("@echo off\r\n", encoding="ascii")
        node_dir = root / "node"
        entry = node_dir / "node_modules" / "@moonshot-ai" / "kimi-code" / "dist" / "main.mjs"
        entry.parent.mkdir(parents=True)
        entry.write_text("", encoding="ascii")
        node_cmd = node_dir / "kimi.CMD"
        node_cmd.write_text("@echo off\r\n", encoding="ascii")
        (node_dir / "node.exe").write_bytes(b"")
        overflow_calls, overflow_error = _launch(cmd, LONG_PROMPT, root / "overflow")
        short_calls, short_error = _launch(cmd, "ping", root / "short")
        node_calls, node_error = _launch(node_cmd, LONG_PROMPT, root / "node")

    overflow_spawned = bool(overflow_calls)
    short_ok = bool(short_calls) and any("ping" in part for command in short_calls for part in command)
    node_ok = bool(node_calls) and any(LONG_PROMPT in part for command in node_calls for part in command)
    observed = {
        "death_class": death.class_id,
        "death_retryable": death.retryable,
        "english_class": english.class_id,
        "win206_class": win206.class_id,
        "bare_class": bare.class_id,
        "bare_retryable": bare.retryable,
        "zero_class": zero.class_id,
        "salvage_class": salvaged.class_id,
        "salvage_status": salvaged.decision.get("status"),
        "overflow_spawned": overflow_spawned,
        "overflow_error": overflow_error[:180],
        "short_ok": short_ok,
        "short_error": short_error[:180],
        "node_ok": node_ok,
        "node_error": node_error[:180],
    }
    passed = (
        death.class_id == "command_line_too_long"
        and death.retryable is False
        and english.class_id == "command_line_too_long"
        and win206.class_id == "command_line_too_long"
        and bare.class_id == "cli_error"
        and bare.retryable is True
        and zero.class_id != "command_line_too_long"
        and salvaged.class_id == "command_line_too_long"
        and salvaged.decision.get("status") == "blocked"
        and overflow_spawned is False
        and "命令行太长" in overflow_error
        and short_ok
        and node_ok
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as error:  # noqa: BLE001 - unmet outcome must still print JSON
        passed = False
        observed = {"error": str(error)}
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
