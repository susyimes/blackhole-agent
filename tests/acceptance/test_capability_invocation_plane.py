"""Acceptance probe: the compounded ledger answers a real external HTTP client.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe
is fully self-contained: it builds a minimal ledger plus vendored absorbed
tool in a temp directory, starts the invocation plane as a separate OS
process (the way an operator would), and drives it over a real loopback
socket — listing the invocable set, executing the vendored tool through
``POST /invoke``, and confirming fail-closed refusals for an unknown id and
for an unproved capability.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay the same probe on baseline
and candidate source trees.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_TOOL, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "slug": "text-reverser",
        "name": "probe text reverser",
        "command": ["python", "tool.py"],
        "requires": ["raw_text"],
        "provides": ["reversed_text"],
        "cases": [
            {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
            {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
        ],
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    entry = {
        "id": "",
        "name": "",
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "uv run python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "capability_delta": "",
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    proved = dict(entry, last_proved_at="2026-01-01T00:00:00Z", last_proof_exit_code=0)
    unproved = dict(entry, last_proved_at=None, last_proof_exit_code=1)
    capabilities = {
        "capability.absorbed-text-reverser": dict(
            proved, id="capability.absorbed-text-reverser", name="probe text reverser"
        ),
        "capability.absorbed-unproved-tool": dict(
            unproved, id="capability.absorbed-unproved-tool", name="unproved"
        ),
        "repo.import-health": dict(proved, id="repo.import-health", name="import health"),
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


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "capability-invocation-plane"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:  # baseline source tree has no invocation plane
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="capability-service-probe-") as directory:
        root = _build_fixture_root(Path(directory))
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
                observed["detail"] = "server never reported a listening port"
                return {"passed": False, "observed": observed}
            base = f"http://127.0.0.1:{ready['listening']}"

            deadline = time.monotonic() + 30
            status, listing = 0, None
            while time.monotonic() < deadline:
                try:
                    status, listing = _request("GET", f"{base}/capabilities")
                    break
                except URLError:
                    time.sleep(0.2)
            listed_ids = (
                [item["id"] for item in listing.get("capabilities", [])]
                if isinstance(listing, dict)
                else []
            )
            observed["listing_status"] = status
            observed["listed_ids"] = listed_ids
            listing_ok = status == 200 and listed_ids == ["capability.absorbed-text-reverser"]

            status, invoked = _request(
                "POST",
                f"{base}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": "blackhole unbound"},
                },
            )
            output = invoked.get("output") if isinstance(invoked, dict) else None
            observed["invoke_status"] = status
            observed["invoke_output"] = output
            invoke_ok = status == 200 and output == {"reversed_text": "dnuobnu elohkcalb"}

            status, refused = _request(
                "POST",
                f"{base}/invoke",
                {"capability_id": "capability.absorbed-not-real", "input": {}},
            )
            observed["unknown_status"] = status
            unknown_ok = status == 404 and isinstance(refused, dict) and refused.get("ok") is False

            status, refused_unproved = _request(
                "POST",
                f"{base}/invoke",
                {"capability_id": "capability.absorbed-unproved-tool", "input": {}},
            )
            observed["unproved_status"] = status
            unproved_ok = (
                status == 404
                and isinstance(refused_unproved, dict)
                and refused_unproved.get("ok") is False
            )

            observed["checks"] = {
                "listing": listing_ok,
                "invoke": invoke_ok,
                "unknown_refused": unknown_ok,
                "unproved_refused": unproved_ok,
            }
            passed = listing_ok and invoke_ok and unknown_ok and unproved_ok
            return {"passed": passed, "observed": observed}
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
