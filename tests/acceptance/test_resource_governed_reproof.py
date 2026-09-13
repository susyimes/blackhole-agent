"""Acceptance probe: quarantine lifts only through supervised governed re-proof.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe is
fully self-contained: it builds a fixture ledger with a healthy tool, a
memory-hog tool, and a pre-quarantined reformed tool; starts the invocation
plane as a separate OS process; and drives it over a real loopback socket.
It expects: the pre-quarantined tool to be refused on /invoke, reinstated by
POST /reproof after its frozen cases pass under the enforced resource limits
(ledger quarantine cleared, resource_reproof recorded), and then invocable
again; the memory hog to be quarantined by a live invocation and to STAY
quarantined after /reproof because its frozen cases violate the memory limit
again; and /reproof to refuse unknown and non-quarantined capabilities.

On the baseline source tree the plane has no /reproof route (404), so the
checks below report passed=false without crashing.

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
    "with open('runs.txt', 'a', encoding='utf-8') as fh:\n"
    "    fh.write(state['label'] + '\\n')\n"
    "chunks = []\n"
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


def _entry(capability_id: str, name: str) -> dict:
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


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    reverser_cases = [
        {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
        {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
    ]
    _write_tool(root, "text-reverser", _HEALTHY_TOOL, ["raw_text"], ["reversed_text"], reverser_cases)
    _write_tool(root, "reformed-reverser", _HEALTHY_TOOL, ["raw_text"], ["reversed_text"], reverser_cases)
    hog_cases = [
        {"input": {"label": "case-a"}, "expect": {"hog_done": 48}},
        {"input": {"label": "case-b"}, "expect": {"hog_done": 48}},
    ]
    _write_tool(root, "memory-hog", _HOG_TOOL, ["label"], ["hog_done"], hog_cases)

    reformed_id = "capability.absorbed-reformed-reverser"
    reformed = _entry(reformed_id, "probe reformed reverser")
    reformed["resource_quarantine"] = {
        "reason": "seeded quarantine: earlier run exceeded the memory limit",
        "resource": "memory",
        "limit_bytes": 268435456,
        "peak_job_memory_bytes": 270000000,
        "quarantined_at": "2026-01-01T00:00:00Z",
    }
    capabilities = {
        "capability.absorbed-text-reverser": _entry(
            "capability.absorbed-text-reverser", "probe text reverser"
        ),
        reformed_id: reformed,
        "capability.absorbed-memory-hog": _entry(
            "capability.absorbed-memory-hog", "probe memory hog"
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


def _ledger_entry(root: Path, capability_id: str) -> dict:
    document = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
    return (document.get("capabilities") or {}).get(capability_id) or {}


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "resource-governed-reproof"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:  # baseline source tree has no invocation plane
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="resource-reproof-probe-") as directory:
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

            reformed_id = "capability.absorbed-reformed-reverser"
            hog_id = "capability.absorbed-memory-hog"
            healthy_id = "capability.absorbed-text-reverser"

            # 1. Pre-quarantined capability is refused on invoke.
            status, refused = _request(
                "POST", f"{base}/invoke",
                {"capability_id": reformed_id, "input": {"raw_text": "ab"}},
            )
            refused = refused if isinstance(refused, dict) else {}
            observed["pre_invoke_status"] = status
            pre_ok = status == 409 and refused.get("violation") == "resource_quarantined"

            # 2. Supervised re-proof reinstates it: frozen cases pass governed.
            status, reproof = _request(
                "POST", f"{base}/reproof", {"capability_id": reformed_id}
            )
            reproof = reproof if isinstance(reproof, dict) else {}
            observed["reproof_status"] = status
            observed["reproof_reinstated"] = reproof.get("reinstated")
            entry = _ledger_entry(root, reformed_id)
            observed["reproof_record"] = entry.get("resource_reproof")
            reinstate_ok = (
                status == 200
                and reproof.get("reinstated") is True
                and reproof.get("cases_pass") is True
                and bool(reproof.get("reproof_digest"))
                and "resource_quarantine" not in entry
                and isinstance(entry.get("resource_reproof"), dict)
                and entry["resource_reproof"].get("cases_pass") is True
            )

            # 3. Reinstated capability invokes normally again.
            status, invoked = _request(
                "POST", f"{base}/invoke",
                {"capability_id": reformed_id, "input": {"raw_text": "blackhole"}},
            )
            output = invoked.get("output") if isinstance(invoked, dict) else None
            observed["post_invoke_status"] = status
            observed["post_invoke_output"] = output
            post_ok = status == 200 and output == {"reversed_text": "elohkcalb"}

            # 4. The hog is quarantined by a live violating invocation...
            status, hog = _request(
                "POST", f"{base}/invoke", {"capability_id": hog_id, "input": {"label": "live"}}
            )
            hog = hog if isinstance(hog, dict) else {}
            observed["hog_status"] = status
            observed["hog_verdict"] = hog.get("violation")
            hog_quarantined = status == 502 and hog.get("violation") == "resource_limit"

            # 5. ...and STAYS quarantined: re-proof re-runs its frozen cases
            #    under the same enforced limit and they violate it again.
            status, hog_reproof = _request(
                "POST", f"{base}/reproof", {"capability_id": hog_id}
            )
            hog_reproof = hog_reproof if isinstance(hog_reproof, dict) else {}
            observed["hog_reproof_status"] = status
            observed["hog_reproof_reinstated"] = hog_reproof.get("reinstated")
            hog_entry = _ledger_entry(root, hog_id)
            status, hog_repeat = _request(
                "POST", f"{base}/invoke", {"capability_id": hog_id, "input": {"label": "after"}}
            )
            hog_repeat = hog_repeat if isinstance(hog_repeat, dict) else {}
            observed["hog_repeat_status"] = status
            hog_stays_ok = (
                status == 409
                and hog_repeat.get("violation") == "resource_quarantined"
                and hog_reproof.get("ok") is True
                and hog_reproof.get("reinstated") is False
                and hog_reproof.get("cases_pass") is False
                and isinstance(hog_entry.get("resource_quarantine"), dict)
            )

            # 6. Fail-closed refusals: unknown id and non-quarantined capability.
            status, unknown = _request(
                "POST", f"{base}/reproof", {"capability_id": "capability.absorbed-nope"}
            )
            observed["unknown_status"] = status
            unknown_ok = status == 404 and isinstance(unknown, dict) and unknown.get("ok") is False

            status, not_quarantined = _request(
                "POST", f"{base}/reproof", {"capability_id": healthy_id}
            )
            observed["not_quarantined_status"] = status
            not_quarantined_ok = (
                status == 409
                and isinstance(not_quarantined, dict)
                and not_quarantined.get("ok") is False
            )

            observed["checks"] = {
                "quarantined_invoke_refused": pre_ok,
                "reproof_reinstates": reinstate_ok,
                "reinstated_invokes": post_ok,
                "hog_quarantined": hog_quarantined,
                "hog_reproof_stays_quarantined": hog_stays_ok,
                "unknown_refused": unknown_ok,
                "non_quarantined_refused": not_quarantined_ok,
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
