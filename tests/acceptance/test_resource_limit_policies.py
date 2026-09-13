"""Acceptance probe: per-capability resource limits and proof-time profiles.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe is
fully self-contained: it builds a fixture ledger whose capabilities declare
their own ``resource_limits`` policies, starts the invocation plane as a
separate OS process, and drives it over a real loopback socket. It expects:
a big-worker whose declared 512 MiB policy lets a ~300 MiB workload succeed
that the 256 MiB default would kill; a tiny-box tool whose declared 64 MiB
policy gets it quarantined with limit evidence naming ITS policy (not the
default) when its workload exceeds it; and a re-proof of a quarantined
capability recording an observed ``resource_profile`` (peak committed memory
under the enforced limit) into the ledger entry.

On the baseline source tree the plane ignores per-capability policies: the
big-worker is killed at the default limit instead of succeeding, so the
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

# Allocates state['megabytes'] MiB in page-committed 16 MiB chunks, then
# reports how many chunks it committed.
_WORKER_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "target = int(state['megabytes'])\n"
    "chunks = []\n"
    "for _ in range(max(1, target // 16)):\n"
    "    chunk = bytearray(16 << 20)\n"
    "    for i in range(0, len(chunk), 4096):\n"
    "        chunk[i] = 1\n"
    "    chunks.append(chunk)\n"
    "print(json.dumps({'committed_mb': len(chunks) * 16}))\n"
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


def _entry(capability_id: str, name: str, resource_limits: dict | None = None,
           quarantined: bool = False) -> dict:
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
    if quarantined:
        entry["resource_quarantine"] = {
            "reason": "seeded quarantine for re-proof profiling",
            "resource": "memory",
            "limit_bytes": 1,
            "peak_job_memory_bytes": 1,
            "quarantined_at": "2026-01-01T00:00:00Z",
        }
    return entry


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    worker_cases = [
        {"input": {"megabytes": 16}, "expect": {"committed_mb": 16}},
        {"input": {"megabytes": 32}, "expect": {"committed_mb": 32}},
    ]
    _write_tool(root, "big-worker", _WORKER_TOOL, ["megabytes"], ["committed_mb"], worker_cases)
    _write_tool(root, "tiny-box", _WORKER_TOOL, ["megabytes"], ["committed_mb"], worker_cases)
    reverser_cases = [
        {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
        {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
    ]
    _write_tool(root, "profiled-reverser", _HEALTHY_TOOL, ["raw_text"], ["reversed_text"],
                reverser_cases)

    capabilities = {
        # Declared 512 MiB policy: a ~300 MiB workload must succeed here even
        # though it exceeds the 256 MiB plane default.
        "capability.absorbed-big-worker": _entry(
            "capability.absorbed-big-worker", "probe big worker",
            resource_limits={"memory_bytes": 512 << 20, "max_processes": 8},
        ),
        # Declared 64 MiB policy: a 128 MiB workload must be caught by THIS
        # tighter limit, with the verdict naming the policy's limit bytes.
        "capability.absorbed-tiny-box": _entry(
            "capability.absorbed-tiny-box", "probe tiny box",
            resource_limits={"memory_bytes": 64 << 20},
        ),
        # Pre-quarantined healthy tool: re-proof must reinstate it AND record
        # an observed resource profile into the ledger entry.
        "capability.absorbed-profiled-reverser": _entry(
            "capability.absorbed-profiled-reverser", "probe profiled reverser",
            quarantined=True,
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
    observed: dict[str, object] = {"family": "resource-limit-policies"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:  # baseline source tree has no invocation plane
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="resource-limit-policy-probe-") as directory:
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

            big_id = "capability.absorbed-big-worker"
            tiny_id = "capability.absorbed-tiny-box"
            profiled_id = "capability.absorbed-profiled-reverser"

            # 1. Declared 512 MiB policy: 304 MiB workload succeeds.
            status, big = _request(
                "POST", f"{base}/invoke",
                {"capability_id": big_id, "input": {"megabytes": 304}},
            )
            output = big.get("output") if isinstance(big, dict) else None
            observed["big_status"] = status
            observed["big_output"] = output
            big_ok = status == 200 and output == {"committed_mb": 304}

            # 2. Declared 64 MiB policy: 128 MiB workload is caught by the
            #    capability's own tighter limit; verdict names the policy.
            status, tiny = _request(
                "POST", f"{base}/invoke",
                {"capability_id": tiny_id, "input": {"megabytes": 128}},
            )
            tiny = tiny if isinstance(tiny, dict) else {}
            resource = tiny.get("resource") if isinstance(tiny.get("resource"), dict) else {}
            observed["tiny_status"] = status
            observed["tiny_verdict"] = tiny.get("violation")
            observed["tiny_limit"] = resource.get("limit_bytes")
            tiny_entry = _ledger_entry(root, tiny_id)
            tiny_ok = (
                status == 502
                and tiny.get("violation") == "resource_limit"
                and resource.get("limit_bytes") == (64 << 20)
                and isinstance(tiny_entry.get("resource_quarantine"), dict)
                and tiny_entry["resource_quarantine"].get("limit_bytes") == (64 << 20)
            )

            # 3. Supervised re-proof reinstates the quarantined reverser AND
            #    records an observed resource profile in its ledger entry.
            status, reproof = _request(
                "POST", f"{base}/reproof", {"capability_id": profiled_id}
            )
            reproof = reproof if isinstance(reproof, dict) else {}
            profile = _ledger_entry(root, profiled_id).get("resource_profile")
            observed["reproof_status"] = status
            observed["reproof_profile"] = reproof.get("resource_profile")
            observed["ledger_profile"] = profile
            profile_ok = (
                status == 200
                and reproof.get("reinstated") is True
                and isinstance(profile, dict)
                and int(profile.get("peak_job_memory_bytes") or 0) > 0
                and int(profile.get("observed_under_limit_bytes") or 0) == (256 << 20)
            )

            observed["checks"] = {
                "declared_relaxed_policy_serves": big_ok,
                "declared_tighter_policy_enforced": tiny_ok,
                "reproof_records_resource_profile": profile_ok,
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
