"""A sandboxed tool's files are readable while it is still running.

The live plane grants one host-visible effect directory per invocation and
reports the tool's exception line when a write is refused. This script
prints JSON with boolean passed and nonempty observed, and exits 0 for
both met and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError

HEARTBEAT_ID = "capability.absorbed-effect-heartbeat"
DENIAL_ID = "capability.absorbed-tree-writer"
HEARTBEAT_TOOL = """import json, os, sys, time
from pathlib import Path
json.load(sys.stdin)
raw = os.environ.get("BLACKHOLE_EFFECT_DIR", "")
if not raw:
    print(json.dumps({"beats": 0}))
    raise SystemExit(0)
path = Path(raw) / "heartbeat.txt"
for n in range(1, 16):
    path.write_text(str(n), encoding="utf-8")
    time.sleep(0.1)
print(json.dumps({"beats": n}))
"""
DENIAL_TOOL = """import json, sys
from pathlib import Path
json.load(sys.stdin)
Path("side.txt").write_text("nope", encoding="utf-8")
print(json.dumps({"saved": "nope"}))
"""


def _entry(capability_id: str) -> dict:
    return {
        "id": capability_id,
        "name": capability_id,
        "description": "effect directory probe",
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "python -c pass",
        "dependencies": [],
        "behavior_paths": [],
        "capability_delta": "",
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }


def _write_tool(root: Path, slug: str, source: str, requires: list[str], provides: list[str]) -> Path:
    directory = root / "capabilities" / "absorbed" / slug
    directory.mkdir(parents=True)
    (directory / "tool.py").write_text(source, encoding="utf-8")
    (directory / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": slug,
                "command": ["python", "tool.py"],
                "requires": requires,
                "provides": provides,
                "cases": [
                    {
                        "input": {key: word for key in requires},
                        "expect": {key: word for key in provides},
                    }
                    for word in ("ab", "cd")
                ],
            }
        ),
        encoding="utf-8",
    )
    return directory


def _request(url: str, payload: dict | None = None, timeout: float = 20) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST" if payload is not None else "GET")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            return response.status, body if isinstance(body, dict) else {"body": body}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw[:400]}
        return exc.code, body if isinstance(body, dict) else {"body": body}
    except URLError as exc:
        return 0, {"error": str(exc)}


def _max_beat(root: Path) -> int:
    artifacts = root / ".blackhole-agent" / "invocation-artifacts"
    best = 0
    if not artifacts.is_dir():
        return 0
    for path in artifacts.glob("*/heartbeat.txt"):
        try:
            best = max(best, int(path.read_text(encoding="utf-8").strip() or "0"))
        except (OSError, ValueError):
            continue
    return best


def _observe(root: Path) -> dict:
    from blackhole_agent.capability_service import build_server

    denial_dir = _write_tool(root, "tree-writer", DENIAL_TOOL, ["raw_text"], ["saved"])
    _write_tool(root, "effect-heartbeat", HEARTBEAT_TOOL, ["raw_text"], ["beats"])
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {
                    HEARTBEAT_ID: _entry(HEARTBEAT_ID),
                    DENIAL_ID: _entry(DENIAL_ID),
                },
            }
        ),
        encoding="utf-8",
    )
    httpd = build_server(root, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    observed: dict = {}
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        health_status, health = _request(f"{base}/health")
        observed["health_status"] = health_status
        observed["invocation_effect_dir"] = bool(health.get("invocation_effect_dir"))
        box: dict = {}

        def _call() -> None:
            box["status"], box["body"] = _request(
                f"{base}/invoke",
                {"capability_id": HEARTBEAT_ID, "input": {"raw_text": "go"}},
                timeout=20,
            )

        caller = threading.Thread(target=_call, daemon=True)
        caller.start()
        samples: list[int] = []
        live_increase = False
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            value = _max_beat(root)
            if value:
                samples.append(value)
            if caller.is_alive() and len(samples) >= 2 and samples[-1] > samples[0]:
                live_increase = True
                break
            if not caller.is_alive():
                break
            time.sleep(0.05)
        observed["heartbeat_still_running"] = bool(live_increase and caller.is_alive())
        caller.join(timeout=15)
        observed["heartbeat_status"] = box.get("status")
        heartbeat_body = box.get("body") if isinstance(box.get("body"), dict) else {}
        observed["heartbeat_error"] = str(heartbeat_body.get("error") or "")[:300]
        observed["heartbeat_samples"] = samples
        observed["heartbeat_live_increase"] = live_increase
        denial_status, denial = _request(
            f"{base}/invoke",
            {"capability_id": DENIAL_ID, "input": {"raw_text": "go"}},
            timeout=20,
        )
        error = str(denial.get("error") or "")
        observed["denial_status"] = denial_status
        observed["denial_error"] = error[:400]
        observed["vendored_write_absent"] = not (denial_dir / "side.txt").exists()
        observed["permission_error_reported"] = "PermissionError" in error
        passed = bool(
            live_increase
            and denial_status == 502
            and "PermissionError" in error
            and not (denial_dir / "side.txt").exists()
        )
        observed["passed"] = passed
        return observed
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def main() -> int:
    observed: dict = {}
    try:
        with tempfile.TemporaryDirectory(prefix="bh-effect-probe-") as temporary:
            observed = _observe(Path(temporary))
    except Exception as exc:
        observed = {"error": f"{type(exc).__name__}: {exc}", "passed": False}
    passed = bool(observed.get("passed"))
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
