"""Acceptance probe: /contract program execution is resource-governed.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe is
fully self-contained: it builds a fixture ledger whose capabilities are shell
commands — one committing ~768 MiB of memory, one healthy — starts the
invocation plane as a separate OS process, and drives POST /contract over a
real loopback socket. It expects the hog's program_passes contract to be
honestly reported NOT met (the governed command tree is killed by the
enforced memory bound instead of consuming host memory unchecked), while the
healthy capability's contract is met and the plane keeps serving.

On the baseline source tree, /contract runs program steps through an
ungoverned subprocess.run: the hog commits its memory unimpeded and the
contract is reported met, so the checks below report passed=false without
crashing.

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

# Commits 768 MiB (page-touched) then prints ok. Exceeds the plane's 512 MiB
# contract bound; succeeds easily when ungoverned.
_HOG_COMMAND = (
    "python -c \"b=bytearray(768*1024*1024);mv=memoryview(b);"
    "mv[::4096]=b'x'*(768*1024*1024//4096);print('ok')\""
)
_OK_COMMAND = "python -c \"print('ok')\""


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


def _entry(capability_id: str, name: str, command: str) -> dict:
    return {
        "id": capability_id,
        "name": name,
        "description": f"probe fixture {name}",
        "kind": "command",
        "entry": command,
        "proof_command": "python -c \"print('proof')\"",
        "dependencies": [],
        "behavior_paths": [],
        "capability_delta": "",
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    capabilities = {
        "capability.probe-hog-command": _entry(
            "capability.probe-hog-command", "probe hog command", _HOG_COMMAND
        ),
        "capability.probe-ok-command": _entry(
            "capability.probe-ok-command", "probe ok command", _OK_COMMAND
        ),
    }
    ledger_dir = root / "capabilities"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "ledger.json").write_text(
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
    observed: dict[str, object] = {"family": "resource-governed-contract"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:  # baseline source tree has no invocation plane
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="resource-contract-probe-") as directory:
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
                try:
                    _request("GET", f"{base}/health")
                    break
                except URLError:
                    time.sleep(0.2)

            # The hog's program step must be killed by the governed memory
            # bound: the contract is honestly reported NOT met.
            started = time.monotonic()
            status, hog = _request(
                "POST", f"{base}/contract",
                {"done_when": "program_passes:capability.probe-hog-command"},
            )
            elapsed = time.monotonic() - started
            hog = hog if isinstance(hog, dict) else {}
            observed["hog_status"] = status
            observed["hog_met"] = hog.get("met")
            observed["hog_results"] = hog.get("results")
            observed["hog_elapsed_seconds"] = round(elapsed, 1)
            hog_ok = status == 200 and hog.get("met") is False and elapsed < 60

            # A healthy command's contract still passes under governance.
            status, healthy = _request(
                "POST", f"{base}/contract",
                {"done_when": "program_passes:capability.probe-ok-command"},
            )
            healthy = healthy if isinstance(healthy, dict) else {}
            observed["healthy_status"] = status
            observed["healthy_met"] = healthy.get("met")
            healthy_ok = status == 200 and healthy.get("met") is True

            # The plane stays alive after the killed program step.
            status, health = _request("GET", f"{base}/health")
            observed["health_status"] = status
            alive_ok = status == 200 and isinstance(health, dict) and health.get("ok") is True

            observed["checks"] = {
                "hog_contract_honestly_unmet": hog_ok,
                "healthy_contract_met": healthy_ok,
                "plane_alive": alive_ok,
            }
            passed = all(observed["checks"].values())
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
