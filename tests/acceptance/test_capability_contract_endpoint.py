"""Acceptance probe: the invocation plane machine-checks done_when contracts.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe
is fully self-contained: it builds a minimal fixture repo (a ledger holding
one proved python capability plus its entry module), starts the invocation
plane as a separate OS process (the way an operator would), and drives the
``POST /contract`` endpoint over a real loopback socket — confirming that a
``program_passes:...;no_skill_route`` contract is machine-evaluated with a
real program execution, per-predicate verdicts, a skill-route attestation,
and a binding contract digest, while empty and non-machine-checkable
contracts are refused fail-closed.

On the baseline source tree the plane has no ``/contract`` route: the POST
is refused with 404 and this probe reports passed=False. Prints JSON with
boolean passed and nonempty observed. Exits 0 for both met and unmet
outcomes so the controller can replay the same probe on baseline and
candidate source trees.
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

_FIXTURE_MODULE = (
    "def run():\n"
    "    return {'ok': True, 'echo': 'fixture'}\n"
)


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=120) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None
    except (URLError, TimeoutError, OSError):
        return 0, None


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    (root / "capabilities").mkdir(parents=True)
    (root / "fixture_probe_cap.py").write_text(_FIXTURE_MODULE, encoding="utf-8")
    entry = {
        "id": "",
        "name": "",
        "description": "probe fixture capability",
        "kind": "python",
        "entry": "fixture_probe_cap:run",
        "proof_command": "python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "capability_delta": "",
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }
    capabilities = {
        "capability.fixture-echo": dict(
            entry, id="capability.fixture-echo", name="probe fixture echo"
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


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "capability-contract-endpoint"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:  # baseline source tree has no invocation plane
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(service, "evaluate_contract_request"):
        observed["detail"] = "baseline source tree has no contract endpoint"
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="capability-contract-probe-") as directory:
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
            while time.monotonic() < deadline:
                status, health = _request("GET", f"{base}/health")
                if status:
                    break
                time.sleep(0.2)
            observed["health_status"] = status

            status, verdict = _request(
                "POST",
                f"{base}/contract",
                {"done_when": "program_passes:capability.fixture-echo;no_skill_route"},
            )
            observed["met_status"] = status
            observed["met_verdict"] = verdict
            predicates = (
                {item.get("kind"): item.get("passed") for item in verdict.get("results", [])}
                if isinstance(verdict, dict)
                else {}
            )
            met_ok = (
                status == 200
                and isinstance(verdict, dict)
                and verdict.get("met") is True
                and verdict.get("used_skill_route_discovery") is False
                and predicates.get("program_passes") is True
                and predicates.get("no_skill_route") is True
                and bool(verdict.get("contract_digest"))
            )

            status, unmet = _request(
                "POST",
                f"{base}/contract",
                {"done_when": "program_passes:capability.fixture-missing;no_skill_route"},
            )
            observed["unmet_status"] = status
            observed["unmet_met"] = unmet.get("met") if isinstance(unmet, dict) else None
            unmet_ok = status == 200 and isinstance(unmet, dict) and unmet.get("met") is False

            status, empty = _request("POST", f"{base}/contract", {"done_when": "   "})
            observed["empty_status"] = status
            empty_ok = status == 422 and isinstance(empty, dict) and empty.get("ok") is False

            status, free_text = _request(
                "POST", f"{base}/contract", {"done_when": "the ledger feels healthy"}
            )
            observed["free_text_status"] = status
            free_text_ok = (
                status == 422 and isinstance(free_text, dict) and free_text.get("ok") is False
            )

            observed["checks"] = {
                "contract_met": met_ok,
                "unmet_reported": unmet_ok,
                "empty_refused": empty_ok,
                "free_text_refused": free_text_ok,
            }
            passed = met_ok and unmet_ok and empty_ok and free_text_ok
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
