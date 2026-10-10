"""Acceptance probe: untrusted HTTP-invoked tools cannot mutate the checkout.

The filesystem sandbox already blocked host paths *outside* the served
workspace, but the workspace root itself was on the allowlist. A live
POST /invoke could rewrite capabilities/ledger.json or plant files beside
source. This probe builds a minimal ledger whose tool reports whether it
can read and overwrite a workspace canary and the served ledger, starts
the invocation plane as a separate OS process, and drives a real loopback
``POST /invoke``.

On the candidate plane the tool must reverse its input, read a file inside
its vendored tree, fail to read or overwrite the workspace canary, fail to
overwrite the ledger, and a follow-up text-reverser invoke must still
return the correct declared output from the original ledger. On the
previous-milestone plane the canary (and ledger) are writable, so the
probe reports ``passed=false``.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError

_PROBE = r"""
import json, pathlib, sys
state = json.load(sys.stdin)
obs = {"reversed_text": state["raw_text"][::-1]}
canary = pathlib.Path(state["canary_path"])
ledger = pathlib.Path(state["ledger_path"])
try:
    obs["canary_text"] = canary.read_text(encoding="utf-8")
    obs["canary_readable"] = True
except Exception as exc:
    obs["canary_readable"] = False
    obs["canary_error"] = type(exc).__name__
try:
    canary.write_text("PWNED", encoding="utf-8")
    obs["canary_writable"] = True
except Exception as exc:
    obs["canary_writable"] = False
    obs["canary_write_error"] = type(exc).__name__
try:
    ledger.write_text("PWNED-LEDGER", encoding="utf-8")
    obs["ledger_writable"] = True
except Exception as exc:
    obs["ledger_writable"] = False
    obs["ledger_write_error"] = type(exc).__name__
try:
    obs["inside_text"] = pathlib.Path("inside.txt").read_text(encoding="utf-8")
    obs["inside_readable"] = True
except Exception as exc:
    obs["inside_readable"] = False
    obs["inside_error"] = type(exc).__name__
print(json.dumps(obs))
"""

_REVERSER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

CANARY_VALUE = "workspace-canary-3299360d"


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=45) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None


def _ledger_entry(capability_id: str, name: str) -> dict:
    return {
        "id": capability_id,
        "name": name,
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "uv run python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "capability_delta": "",
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }


def _write_tool(
    root: Path,
    slug: str,
    source: str,
    requires: list[str],
    provides: list[str],
    extra_files: dict[str, str] | None = None,
) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    for name, body in (extra_files or {}).items():
        (tool_dir / name).write_text(body, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": f"probe {slug}",
                "command": ["python", "tool.py"],
                "requires": requires,
                "provides": provides,
                "cases": [
                    {
                        "input": {key: "x" for key in requires},
                        "expect": {provides[0]: "x"},
                    }
                    for _ in ("ab", "cd")
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(
        root,
        "ws-probe",
        _PROBE,
        ["raw_text", "canary_path", "ledger_path"],
        [
            "reversed_text",
            "canary_readable",
            "canary_writable",
            "ledger_writable",
            "inside_readable",
        ],
        extra_files={"inside.txt": "inside-ok"},
    )
    _write_tool(root, "text-reverser", _REVERSER, ["raw_text"], ["reversed_text"])
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {
                    "capability.absorbed-ws-probe": _ledger_entry(
                        "capability.absorbed-ws-probe", "probe workspace integrity"
                    ),
                    "capability.absorbed-text-reverser": _ledger_entry(
                        "capability.absorbed-text-reverser", "probe text reverser"
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "workspace-canary.txt").write_text(CANARY_VALUE, encoding="utf-8")
    return root


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline()
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "tool-workspace-integrity"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="tool-ws-integrity-probe-") as directory:
        base = Path(directory)
        root = _build_fixture_root(base)
        canary = root / "workspace-canary.txt"
        ledger = root / "capabilities" / "ledger.json"
        original_ledger = ledger.read_text(encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_root)
        env["PYTHONIOENCODING"] = "utf-8"
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "blackhole_agent.capability_service",
                "serve",
                "--port",
                "0",
                "--root",
                str(root),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        try:
            sink: dict[str, object] = {}
            reader = threading.Thread(target=_read_ready_line, args=(process, sink), daemon=True)
            reader.start()
            reader.join(timeout=60)
            ready = sink.get("ready")
            observed["ready"] = ready
            if not isinstance(ready, dict) or not ready.get("listening"):
                err = process.stderr.read() if process.stderr else ""
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = err[-2000:] if isinstance(err, str) else ""
                return {"passed": False, "observed": observed}
            base_url = f"http://127.0.0.1:{ready['listening']}"
            status, invoked = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-ws-probe",
                    "input": {
                        "raw_text": "blackhole",
                        "canary_path": str(canary),
                        "ledger_path": str(ledger),
                    },
                },
            )
            output = invoked.get("output") if isinstance(invoked, dict) else None
            observed["invoke_status"] = status
            observed["output"] = output
            if isinstance(invoked, dict) and invoked.get("error"):
                observed["invoke_error"] = invoked.get("error")
            follow_status, follow = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": "blackhole"},
                },
            )
            follow_output = follow.get("output") if isinstance(follow, dict) else None
            observed["follow_status"] = follow_status
            observed["follow_output"] = follow_output
            canary_bytes = canary.read_text(encoding="utf-8") if canary.is_file() else ""
            ledger_bytes = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
            observed["canary_bytes"] = canary_bytes
            observed["ledger_intact"] = ledger_bytes == original_ledger
            behavior_ok = (
                status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == "elohkcalb"
            )
            inside_ok = isinstance(output, dict) and output.get("inside_readable") is True
            canary_blocked = (
                isinstance(output, dict)
                and output.get("canary_readable") is False
                and output.get("canary_writable") is False
                and canary_bytes == CANARY_VALUE
            )
            ledger_blocked = (
                isinstance(output, dict)
                and output.get("ledger_writable") is False
                and ledger_bytes == original_ledger
                and "PWNED-LEDGER" not in ledger_bytes
            )
            follow_ok = (
                follow_status == 200
                and isinstance(follow_output, dict)
                and follow_output.get("reversed_text") == "elohkcalb"
            )
            observed["checks"] = {
                "tool_behavior_correct": behavior_ok,
                "vendored_file_readable": inside_ok,
                "workspace_canary_blocked": canary_blocked,
                "ledger_unwritable": ledger_blocked,
                "followup_reverser_ok": follow_ok,
            }
            return {
                "passed": bool(
                    behavior_ok and inside_ok and canary_blocked and ledger_blocked and follow_ok
                ),
                "observed": observed,
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict))
    sys.exit(0)
