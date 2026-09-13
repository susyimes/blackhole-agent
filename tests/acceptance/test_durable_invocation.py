"""Real HTTP side-effect acceptance, replayable against isolated baseline src.

No repository fixtures, proof flags, receipt-file inspection or mocks are
used to judge the outcome. The fixture is an append tool; its externally
observable writes and HTTP replies decide acceptance. Exit 0 either way.
"""

from __future__ import annotations

import http.client
import json
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TOOL = '''import json, os, sys, time, uuid
from pathlib import Path
s = json.load(sys.stdin)
with open(s['events'], 'a', encoding='utf-8') as f:
    f.write(s['label'] + '\\n')
    f.flush()
    os.fsync(f.fileno())
if s['mode'] == 'hold':
    end = time.monotonic() + 8
    while not Path(s['gate']).exists() and time.monotonic() < end:
        time.sleep(.02)
if s['mode'] == 'fail':
    sys.exit('fixture failure after append')
print(json.dumps({'saved': s['label'], 'token': str(uuid.uuid4())}))
'''


def fixture(root: Path) -> None:
    tool = root / "capabilities" / "absorbed" / "append-event"
    tool.mkdir(parents=True)
    (tool / "tool.py").write_text(TOOL, encoding="utf-8")
    (tool / "absorption.json").write_text(json.dumps({
        "schema_version": 1, "slug": "append-event", "name": "append event",
        "command": [sys.executable, "tool.py"],
        "requires": ["events", "label", "gate", "mode"], "provides": ["saved", "token"],
        "cases": [{"input": {
            "events": str(root / "unused-proof-events.txt"), "label": label,
            "gate": "", "mode": "ok",
        }, "expect": {"saved": label}} for label in ("a", "b")],
    }), encoding="utf-8")
    cid = "capability.absorbed-append-event"
    (root / "capabilities" / "ledger.json").write_text(json.dumps({
        "schema_version": 1, "capabilities": {cid: {
            "id": cid, "name": "append event", "kind": "python",
            "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
            "proof_command": "python -c pass", "dependencies": [], "behavior_paths": [],
            "last_proof_exit_code": 0, "last_proved_at": "2026-01-01T00:00:00Z",
        }},
    }), encoding="utf-8")


def request(base: str, method: str, path: str, payload=None, key=None) -> tuple[int, dict, dict]:
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["Idempotency-Key"] = key
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read()), dict(response.headers)
    except HTTPError as exc:
        return exc.code, json.loads(exc.read()), dict(exc.headers)
    except (OSError, URLError, http.client.HTTPException) as exc:
        return 0, {"transport_error": type(exc).__name__}, {}


class Server:
    def __init__(self, src: Path, root: Path):
        code = (
            "import sys;sys.path.insert(0,sys.argv[1]);from pathlib import Path;"
            "from blackhole_agent.capability_service import serve;serve(Path(sys.argv[2]))"
        )
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-c", code, str(src), str(root)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        ready = []
        reader = threading.Thread(target=lambda: ready.append(self.process.stdout.readline()), daemon=True)
        reader.start()
        reader.join(20)
        try:
            self.port = json.loads(ready[0])["listening"]
        except (IndexError, KeyError, ValueError):
            self.stop()
            raise RuntimeError("HTTP service did not become ready")
        self.base = f"http://127.0.0.1:{self.port}"

    def stop(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=10)
        if self.process.stdout:
            self.process.stdout.close()


def counts(events: Path, label: str) -> int:
    return events.read_text(encoding="utf-8").splitlines().count(label) if events.exists() else 0


def wait_for(predicate, seconds=5) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.02)
    return False


def main() -> dict:
    observed = {"family": "durable-idempotent-side-effects"}
    servers = []
    try:
        import blackhole_agent.capability_service as service

        src = Path(service.__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="invocation-acceptance-") as directory:
            root = Path(directory)
            fixture(root)
            events = root / "effects.txt"

            def payload(label, mode="ok"):
                return {"capability_id": "capability.absorbed-append-event", "input": {
                    "events": str(events), "label": label,
                    "gate": str(root / (label + ".release")), "mode": mode,
                }}

            server = Server(src, root)
            servers.append(server)
            peer = Server(src, root)
            servers.append(peer)
            checks = {}
            with ThreadPoolExecutor(max_workers=9) as clients:
                held = payload("concurrent", "hold")
                first = clients.submit(request, server.base, "POST", "/invoke", held, "shared-key")
                started = wait_for(lambda: counts(events, "concurrent") >= 1)
                duplicates = [clients.submit(
                    request, server.base if i % 2 else peer.base, "POST", "/invoke", held, "shared-key"
                ) for i in range(6)]
                independent = request(peer.base, "POST", "/invoke", payload("independent"), "independent-key")
                early = wait_for(lambda: all(f.done() for f in duplicates), seconds=3)
                active = request(server.base, "GET", "/invocations/shared-key")
                (root / "concurrent.release").touch()
                original = first.result(15)
                duplicates = [f.result(15) for f in duplicates]
                replay = request(peer.base, "POST", "/invoke", held, "shared-key")
                checks["concurrent_admission"] = (
                    started and early and original[0] == 200 and counts(events, "concurrent") == 1
                    and all(r[0] == 409 and r[1].get("code") in {"in_progress", "outcome_unknown"}
                            for r in duplicates)
                    and active[1].get("state") == "in_progress"
                )
                checks["independent_key_progress"] = independent[0] == 200 and counts(events, "independent") == 1
                checks["cross_process_replay"] = replay[:2] == original[:2]
                observed["concurrent_append_count"] = counts(events, "concurrent")
                observed["duplicate_statuses"] = [r[0] for r in duplicates]

                conflict = request(server.base, "POST", "/invoke", payload("conflict"), "shared-key")
                checks["payload_conflict"] = (
                    conflict[0] == 409 and conflict[1].get("code") == "idempotency_conflict"
                    and counts(events, "conflict") == 0
                )

                # Abandon the HTTP response entirely; recover by key alone.
                connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
                connection.request("POST", "/invoke", json.dumps(payload("lost")), {
                    "Content-Type": "application/json", "Idempotency-Key": "lost-key",
                })
                connection.close()
                wait_for(lambda: counts(events, "lost") >= 1)
                receipt = request(server.base, "GET", "/invocations/lost-key")
                if receipt[0] == 200:
                    wait_for(lambda: request(server.base, "GET", "/invocations/lost-key")[1].get("state") == "completed")
                    receipt = request(server.base, "GET", "/invocations/lost-key")
                recovered = request(server.base, "POST", "/invoke", payload("lost"), "lost-key")
                checks["lost_response_recovery"] = (
                    counts(events, "lost") == 1 and recovered[0] == 200
                    and receipt[1].get("response") == recovered[1]
                    and recovered[2].get("Idempotency-Replayed") == "true"
                )

                failure = request(server.base, "POST", "/invoke", payload("failed", "fail"), "failed-key")
                failed_replay = request(peer.base, "POST", "/invoke", payload("failed", "fail"), "failed-key")
                checks["failed_effect_not_retried"] = (
                    failure[0] == 502 and failure[:2] == failed_replay[:2] and counts(events, "failed") == 1
                )

                crashing = payload("crash", "hold")
                pending = clients.submit(request, server.base, "POST", "/invoke", crashing, "crash-key")
                crash_started = wait_for(lambda: counts(events, "crash") >= 1)
                server.stop()
                peer.stop()
                (root / "crash.release").touch()
                pending.result(15)
                server = Server(src, root)
                servers.append(server)
                unknown = request(server.base, "GET", "/invocations/crash-key")
                refused = request(server.base, "POST", "/invoke", crashing, "crash-key")
                restarted = request(server.base, "POST", "/invoke", held, "shared-key")
                checks["restart_response_replay"] = restarted[:2] == original[:2] and counts(events, "concurrent") == 1
                restarted_failure = request(server.base, "POST", "/invoke", payload("failed", "fail"), "failed-key")
                checks["restart_error_replay"] = restarted_failure[:2] == failure[:2] and counts(events, "failed") == 1
                checks["crash_outcome_reconciliation"] = (
                    crash_started and unknown[1].get("state") == "outcome_unknown"
                    and refused[0] == 409 and refused[1].get("code") == "outcome_unknown"
                    and counts(events, "crash") == 1
                )
                observed["crash_append_count"] = counts(events, "crash")
                observed["crash_retry"] = {"status": refused[0], "code": refused[1].get("code")}
                # Distinct new work still executes after the interrupted call.
                healthy = request(server.base, "POST", "/invoke", payload("after-crash"), "new-key")
                checks["post_crash_progress"] = healthy[0] == 200 and counts(events, "after-crash") == 1

                invalid = request(server.base, "POST", "/invoke", payload("invalid"), "../invalid")
                checks["invalid_key_refusal"] = invalid[0] == 400 and counts(events, "invalid") == 0
                unsupported = request(server.base, "POST", "/solve", {
                    "initial_state": {"saved": "already"}, "goal": ["saved"],
                }, "unsupported-key")
                checks["unsupported_route_refusal"] = unsupported[0] == 400
                connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
                raw = json.dumps(payload("multiple-keys")).encode()
                connection.putrequest("POST", "/invoke")
                connection.putheader("Content-Type", "application/json")
                connection.putheader("Content-Length", str(len(raw)))
                connection.putheader("Idempotency-Key", "first-key")
                connection.putheader("Idempotency-Key", "second-key")
                connection.endheaders(raw)
                response = connection.getresponse()
                checks["multiple_key_refusal"] = response.status == 400 and counts(events, "multiple-keys") == 0
                response.read()
                connection.close()
                unkeyed = [request(server.base, "POST", "/invoke", payload("unkeyed")) for _ in range(2)]
                checks["unkeyed_compatibility"] = all(r[0] == 200 for r in unkeyed) and counts(events, "unkeyed") == 2

            observed["checks"] = checks
            return {"passed": all(checks.values()), "observed": observed}
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        for server in servers:
            server.stop()


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
