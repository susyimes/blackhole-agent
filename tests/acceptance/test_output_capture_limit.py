"""Acceptance probe: the live plane caps captured untrusted-tool stdout.

Per-tree job memory limits still leave the trusted parent exposed: after the
child finishes, POST /invoke used to decode the entire stdout file into the
service process. A fixture tool that prints a large JSON blob can therefore
exhaust host RAM even though its own job stayed small.

This probe starts the invocation plane as a separate OS process with
BLACKHOLE_MAX_OUTPUT_BYTES=65536, invokes a fixture tool whose stdout JSON
exceeds that cap, and requires HTTP 502 with violation output_limited whose
body does not contain the oversized blob. GET /health reports the cap. A
follow-up text-reverser invoke still returns the declared reverse output.

On the pre-mission plane the oversized invoke returns HTTP 200 whose output
includes the blob, so the probe reports passed=false. Both outcomes exit 0
with JSON ``passed`` and nonempty ``observed``.
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

PROBE_TEXT = "output-cap-cb834721"
EXPECTED = PROBE_TEXT[::-1]
CAP_BYTES = 65536
BLOB_SIZE = 200000

_BOMB_TOOL = r"""
import json, sys
from pathlib import Path
state = json.load(sys.stdin)
Path(state["canary_path"]).write_text("ran", encoding="utf-8")
print(json.dumps({"blob": "A" * int(state["size"])}))
"""

_FAST_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)


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


def _write_tool(root: Path, slug: str, source: str, requires: list[str], provides: list[str]) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
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
                        "expect": {key: "x" for key in provides},
                    }
                    for _ in ("a", "b")
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "stdout-bomb", _BOMB_TOOL, ["canary_path", "size"], ["blob"])
    _write_tool(root, "text-reverser", _FAST_TOOL, ["raw_text"], ["reversed_text"])
    capabilities = {
        "capability.absorbed-stdout-bomb": _ledger_entry(
            "capability.absorbed-stdout-bomb", "probe stdout bomb"
        ),
        "capability.absorbed-text-reverser": _ledger_entry(
            "capability.absorbed-text-reverser", "probe text reverser"
        ),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline()
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def _request(
    method: str, url: str, payload: dict | None = None, *, timeout: int = 30
) -> tuple[int, object, int]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = None
            return response.status, body, len(raw)
    except HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = None
        return exc.code, body, len(raw)


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "output-capture-limit"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="output-capture-limit-probe-", ignore_cleanup_errors=True)
    try:
        base = Path(scratch.name)
        root = _build_fixture_root(base)
        bomb_canary = root / "capabilities" / "absorbed" / "stdout-bomb" / "canary.txt"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_root)
        env["PYTHONIOENCODING"] = "utf-8"
        env["BLACKHOLE_MAX_OUTPUT_BYTES"] = str(CAP_BYTES)
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

            port = int(ready["listening"])
            base_url = f"http://127.0.0.1:{port}"

            health_status, health, _health_len = _request("GET", f"{base_url}/health")
            observed["health_status"] = health_status
            observed["health"] = health
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("ok") is True
                and int(health.get("max_output_bytes") or 0) == CAP_BYTES
            )

            bomb_status, bomb, bomb_len = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-stdout-bomb",
                    "input": {"canary_path": str(bomb_canary), "size": BLOB_SIZE},
                },
                timeout=40,
            )
            bomb_output = bomb.get("output") if isinstance(bomb, dict) else None
            blob = bomb_output.get("blob") if isinstance(bomb_output, dict) else None
            blob_len = len(blob) if isinstance(blob, str) else 0
            error_text = str(bomb.get("error") or "") if isinstance(bomb, dict) else ""
            observed["bomb_status"] = bomb_status
            observed["bomb_body_len"] = bomb_len
            observed["bomb_blob_len"] = blob_len
            observed["bomb_violation"] = bomb.get("violation") if isinstance(bomb, dict) else None
            observed["bomb_ok_field"] = bomb.get("ok") if isinstance(bomb, dict) else None
            observed["bomb_error_len"] = len(error_text)
            observed["bomb_error_has_blob"] = ("A" * 1024) in error_text
            bomb_ok = (
                bomb_status == 502
                and isinstance(bomb, dict)
                and bomb.get("ok") is False
                and bomb.get("violation") == "output_limited"
                and bomb_len < CAP_BYTES
                and blob_len == 0
                and ("A" * 1024) not in error_text
            )

            follow_status, follow, _follow_len = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": PROBE_TEXT},
                },
            )
            output = follow.get("output") if isinstance(follow, dict) else None
            observed["follow_status"] = follow_status
            observed["follow_output"] = output
            follow_ok = (
                follow_status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == EXPECTED
            )
            observed["checks"] = {
                "health_reports_cap": health_ok,
                "bomb_refused_without_blob": bomb_ok,
                "follow_up_invoke_ok": follow_ok,
            }
            return {
                "passed": bool(health_ok and bomb_ok and follow_ok),
                "observed": observed,
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
    finally:
        try:
            scratch.cleanup()
        except OSError:
            pass


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as exc:
        verdict = {
            "passed": False,
            "observed": {
                "error": type(exc).__name__,
                "detail": str(exc),
                "family": "output-capture-limit",
            },
        }
    print(json.dumps(verdict))
    sys.exit(0)
