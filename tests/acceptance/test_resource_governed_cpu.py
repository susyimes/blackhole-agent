"""Acceptance probe: the plane enforces tree-wide CPU-time budgets.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe is
fully self-contained: it builds a fixture ledger with a CPU-spinner tool
(declared 3-second cpu_seconds policy) and a healthy tool, starts the
invocation plane as a separate OS process, and drives it over a real
loopback socket. It expects the spinner to be terminated by the enforced
CPU budget with a distinct resource_limit verdict attributed to cpu_time
(with job user-time accounting as evidence), the capability quarantined in
the ledger with cpu evidence, a repeat invocation refused without spawning
the tool again, and the healthy tool still served afterwards.

On the baseline source tree the plane has no CPU budget: the spinner runs
until the wall-clock timeout and fails as an ordinary execution error with
no violation verdict and no quarantine, so the checks below report
passed=false without crashing.

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

_SPINNER_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    # A run marker proves whether the tool process was spawned at all.
    "with open('runs.txt', 'a', encoding='utf-8') as fh:\n"
    "    fh.write(state['label'] + '\\n')\n"
    # Burn CPU for far longer than any governed budget allows.
    "x = 0\n"
    "while True:\n"
    "    x += 1\n"
)

_HEALTHY_TOOL = (
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
        with urlrequest.urlopen(req, timeout=90) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None


def _write_tool(root: Path, slug: str, source: str, requires: list, provides: list,
                cases: list) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "slug": slug,
        "name": f"probe {slug}",
        "command": ["python", "tool.py"],
        "requires": requires,
        "provides": provides,
        "cases": cases,
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")


def _entry(capability_id: str, name: str, resource_limits: dict | None = None) -> dict:
    entry = {
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
    if resource_limits:
        entry["resource_limits"] = resource_limits
    return entry


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    spinner_cases = [
        {"input": {"label": "a"}, "expect": {"done": 1}},
        {"input": {"label": "b"}, "expect": {"done": 1}},
    ]
    _write_tool(root, "cpu-spinner", _SPINNER_TOOL, ["label"], ["done"], spinner_cases)
    reverser_cases = [
        {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
        {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
    ]
    _write_tool(root, "text-reverser", _HEALTHY_TOOL, ["raw_text"], ["reversed_text"], reverser_cases)
    capabilities = {
        # Declared 3-second CPU budget: the infinite spinner must be caught
        # by THIS policy quickly, with the verdict attributed to cpu_time.
        "capability.absorbed-cpu-spinner": _entry(
            "capability.absorbed-cpu-spinner", "probe cpu spinner",
            resource_limits={"cpu_seconds": 3},
        ),
        "capability.absorbed-text-reverser": _entry(
            "capability.absorbed-text-reverser", "probe text reverser"
        ),
    }
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
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
    observed: dict[str, object] = {"family": "resource-governed-cpu"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:  # baseline source tree has no invocation plane
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="resource-cpu-probe-") as directory:
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

            spinner_id = "capability.absorbed-cpu-spinner"
            reverser_id = "capability.absorbed-text-reverser"
            marker_path = root / "capabilities" / "absorbed" / "cpu-spinner" / "runs.txt"

            started = time.monotonic()
            status, spin = _request(
                "POST", f"{base}/invoke",
                {"capability_id": spinner_id, "input": {"label": "first"}},
            )
            elapsed = time.monotonic() - started
            spin = spin if isinstance(spin, dict) else {}
            resource = spin.get("resource") if isinstance(spin.get("resource"), dict) else {}
            observed["spin_status"] = status
            observed["spin_verdict"] = spin.get("violation")
            observed["spin_resource"] = resource
            observed["spin_elapsed_seconds"] = round(elapsed, 1)
            violation_ok = (
                status == 502
                and spin.get("ok") is False
                and spin.get("violation") == "resource_limit"
                and spin.get("quarantined") is True
                and resource.get("resource") == "cpu_time"
                and resource.get("limit_cpu_seconds") == 3
                and elapsed < 30  # CPU budget kills it long before the wall timeout
            )

            ledger = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
            spin_entry = (ledger.get("capabilities") or {}).get(spinner_id) or {}
            quarantine = spin_entry.get("resource_quarantine")
            observed["ledger_quarantine"] = quarantine
            ledger_ok = (
                isinstance(quarantine, dict)
                and quarantine.get("resource") == "cpu_time"
                and quarantine.get("limit_cpu_seconds") == 3
                and bool(quarantine.get("reason"))
            )

            status, repeat = _request(
                "POST", f"{base}/invoke",
                {"capability_id": spinner_id, "input": {"label": "second"}},
            )
            repeat = repeat if isinstance(repeat, dict) else {}
            runs = (
                marker_path.read_text(encoding="utf-8").splitlines()
                if marker_path.is_file()
                else []
            )
            observed["repeat_status"] = status
            observed["tool_runs"] = runs
            repeat_ok = (
                status == 409
                and repeat.get("violation") == "resource_quarantined"
                and runs == ["first"]
            )

            status, healthy = _request(
                "POST", f"{base}/invoke",
                {"capability_id": reverser_id, "input": {"raw_text": "blackhole"}},
            )
            output = healthy.get("output") if isinstance(healthy, dict) else None
            observed["healthy_status"] = status
            healthy_ok = status == 200 and output == {"reversed_text": "elohkcalb"}

            observed["checks"] = {
                "cpu_limit_verdict": violation_ok,
                "ledger_quarantine": ledger_ok,
                "reinvoke_refused_without_spawn": repeat_ok,
                "plane_keeps_serving": healthy_ok,
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
