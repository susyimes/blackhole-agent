"""Exercise recovery in a reused turn directory with a saved provider response."""

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from blackhole_agent.kernel_salvage import execute_kernel_turn_with_salvage
from blackhole_agent.kernels.kimi_cli import KimiCliConfig, KimiCliKernel


def exercise(root, scenario):
    provider = "kimi" if scenario == "missing" else "grok"
    receipt_name = f"latest-{provider}-run.json"
    reply = json.dumps({"status": "blocked", "summary": "awaiting the operator"})
    saved = json.dumps({"last_message": reply, "returncode": 1, "session_id": "receipt-session"}).encode()
    prior = root / "kernel" / receipt_name
    prior.parent.mkdir(parents=True)
    prior.write_bytes(saved)
    calls = []
    work = root / "continued.txt"

    def launch(state, prompt, directory, **kwargs):
        calls.append(state.session_id)
        if scenario == "missing":
            # An installed executable with a required but absent model fails the real CLI preflight.
            adapter = KimiCliKernel(KimiCliConfig(kimi_bin=sys.executable, require_explicit_route=True))
            return adapter.run(prompt, cwd=root, output_dir=directory / "kernel")
        receipt = directory / "kernel" / receipt_name
        receipt.parent.mkdir(parents=True, exist_ok=True)
        if scenario == "reissued":
            receipt.write_bytes(saved)
        elif scenario == "late":
            # A different writer updates the operator's latest file while this launch is in flight.
            prior.write_text(json.dumps({"last_message": reply, "session_id": "late-session"}), encoding="utf-8")
        elif scenario == "unreadable":
            receipt.write_bytes(b'{"last_message":"\xff')
        elif scenario == "retry" and len(calls) == 1:
            receipt.write_text(json.dumps({
                "returncode": 1, "session_id": "current-session",
                "stderr_tail": "response truncated by max_tokens",
            }), encoding="utf-8")
        raise RuntimeError("Grok CLI failed with exit code 1")

    def continue_work(state, workspace):
        with (workspace / work.name).open("a", encoding="utf-8") as stream:
            stream.write("continued\n")
        return {"status": "continue", "summary": "picked up the current work"}

    state = SimpleNamespace(kernel=provider, session_id="", session_started=False, workspace_path=str(root))

    def resume():
        return execute_kernel_turn_with_salvage(
            state, "resume work", root, kernel_runner=launch, local_action=continue_work,
            installed_kernels=set(), probe_peers=False, persist_health=False,
        )

    result, decision, _ = resume()
    observed = {
        "sessions": calls.copy(),
        "returned_session": result.session_id,
        "status": decision.status,
        "summary": decision.summary,
        "continuations": work.read_text(encoding="utf-8").splitlines() if work.exists() else [],
    }
    if scenario == "reissued":
        saved = json.dumps({"last_message": reply, "returncode": 1, "session_id": "next-session"}).encode()
        resume()
        observed["archived_session"] = json.loads(Path(result.result_path).read_bytes())["session_id"]
        observed["latest_session"] = json.loads(prior.read_bytes())["session_id"]
    return observed


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        observed = {}
        for case in ("missing", "retry", "reissued", "unreadable", "late"):
            try:
                observed[case] = exercise(Path(directory) / case, case)
            except Exception as error:
                observed[case] = {"error": type(error).__name__}
    continued = {
        "sessions": [""], "returned_session": "local", "status": "continue",
        "summary": "picked up the current work", "continuations": ["continued"],
    }
    expected = {
        "missing": continued,
        "unreadable": continued,
        "late": continued,
        "retry": {**continued, "sessions": ["", "current-session"]},
        "reissued": {
            "sessions": [""], "returned_session": "receipt-session", "status": "blocked",
            "summary": "awaiting the operator", "continuations": [],
            "archived_session": "receipt-session", "latest_session": "next-session",
        },
    }
    print(json.dumps({"passed": observed == expected, "observed": observed}))
