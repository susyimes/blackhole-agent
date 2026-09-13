"""Acceptance probe: the invocation plane resource-governs untrusted tools.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe is
fully self-contained: it builds a minimal ledger with a healthy vendored tool
and a memory-hog vendored tool, starts the invocation plane as a separate OS
process (the way an operator would), and drives it over a real loopback
socket. It expects the hog invocation to be attributed to the enforced
tree-wide memory limit with a distinct ``resource_limit`` verdict, the
offending capability to be durably quarantined in the ledger, a repeat
invocation to be refused fail-closed without spawning the tool again (its
run-marker file stays untouched), and an unaffected capability to keep
serving afterwards.

On the baseline source tree (no resource governance) the hog either succeeds
or fails as an ordinary tool error with no violation verdict and no ledger
quarantine, so the checks below report passed=false without crashing.

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

_HEALTHY_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

_HOG_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    # A run marker proves whether the tool process was spawned at all.
    "with open('runs.txt', 'a', encoding='utf-8') as fh:\n"
    "    fh.write(state['label'] + '\\n')\n"
    "chunks = []\n"
    # 48 x 16 MiB = 768 MiB, committed page by page so the hog must exceed any
    # enforced tree memory limit far below that.
    "for _ in range(48):\n"
    "    chunk = bytearray(16 << 20)\n"
    "    for i in range(0, len(chunk), 4096):\n"
    "        chunk[i] = 1\n"
    "    chunks.append(chunk)\n"
    "print(json.dumps({'hog_done': len(chunks)}))\n"
)


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None


def _write_tool(root: Path, slug: str, source: str, requires: list, provides: list) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    case_input = {key: "probe" for key in requires}
    manifest = {
        "schema_version": 1,
        "slug": slug,
        "name": f"probe {slug}",
        "command": ["python", "tool.py"],
        "requires": requires,
        "provides": provides,
        # Cases are validated but never executed by the plane; the expect
        # values only need to reference declared provides keys.
        "cases": [
            {"input": case_input, "expect": {provides[0]: "x"}},
            {"input": case_input, "expect": {provides[0]: "y"}},
        ],
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "text-reverser", _HEALTHY_TOOL, ["raw_text"], ["reversed_text"])
    _write_tool(root, "memory-hog", _HOG_TOOL, ["label"], ["hog_done"])
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
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }
    capabilities = {
        "capability.absorbed-text-reverser": dict(
            entry, id="capability.absorbed-text-reverser", name="probe text reverser"
        ),
        "capability.absorbed-memory-hog": dict(
            entry, id="capability.absorbed-memory-hog", name="probe memory hog"
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
    observed: dict[str, object] = {"family": "resource-governed-plane"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:  # baseline source tree has no invocation plane
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="resource-governed-plane-probe-") as directory:
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

            hog_id = "capability.absorbed-memory-hog"
            reverser_id = "capability.absorbed-text-reverser"
            marker_path = (
                root / "capabilities" / "absorbed" / "memory-hog" / "runs.txt"
            )

            status, hog = _request(
                "POST", f"{base}/invoke", {"capability_id": hog_id, "input": {"label": "first"}}
            )
            hog = hog if isinstance(hog, dict) else {}
            observed["hog_status"] = status
            observed["hog_verdict"] = hog.get("violation")
            observed["hog_resource"] = hog.get("resource")
            violation_ok = (
                status == 502
                and hog.get("ok") is False
                and hog.get("violation") == "resource_limit"
                and hog.get("quarantined") is True
                and isinstance(hog.get("resource"), dict)
                and hog["resource"].get("resource") == "memory"
            )

            ledger = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
            hog_entry = (ledger.get("capabilities") or {}).get(hog_id) or {}
            quarantine = hog_entry.get("resource_quarantine")
            observed["ledger_quarantine"] = quarantine
            ledger_ok = (
                isinstance(quarantine, dict)
                and quarantine.get("resource") == "memory"
                and bool(quarantine.get("reason"))
            )

            status, repeat = _request(
                "POST", f"{base}/invoke", {"capability_id": hog_id, "input": {"label": "second"}}
            )
            repeat = repeat if isinstance(repeat, dict) else {}
            observed["repeat_status"] = status
            observed["repeat_verdict"] = repeat.get("violation")
            runs = (
                marker_path.read_text(encoding="utf-8").splitlines()
                if marker_path.is_file()
                else []
            )
            observed["tool_runs"] = runs
            repeat_ok = (
                status == 409
                and repeat.get("ok") is False
                and repeat.get("violation") == "resource_quarantined"
                and runs == ["first"]  # refused before the tool could spawn again
            )

            status, healthy = _request(
                "POST",
                f"{base}/invoke",
                {"capability_id": reverser_id, "input": {"raw_text": "blackhole"}},
            )
            output = healthy.get("output") if isinstance(healthy, dict) else None
            observed["healthy_status"] = status
            observed["healthy_output"] = output
            healthy_ok = status == 200 and output == {"reversed_text": "elohkcalb"}

            observed["checks"] = {
                "resource_limit_verdict": violation_ok,
                "ledger_quarantine": ledger_ok,
                "reinvoke_refused_without_spawn": repeat_ok,
                "plane_keeps_serving": healthy_ok,
            }
            passed = violation_ok and ledger_ok and repeat_ok and healthy_ok
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
