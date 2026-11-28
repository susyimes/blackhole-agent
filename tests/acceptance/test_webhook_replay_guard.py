"""Retry a real signed delivery after the HTTP acknowledgment and then its worker are lost."""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from queue import Queue
from threading import Barrier, Thread

SECRET = "webhook-probe-secret"
TOKEN = "webhook-probe-client"
CAPABILITY = "capability.absorbed-issue-receipt"
TOOL = """import json, os, sys, time, uuid
from pathlib import Path

label = json.load(sys.stdin)["label"]
out = Path(os.environ["BLACKHOLE_EFFECT_DIR"])
receipt = uuid.uuid4().hex
(out / "issuing").write_text(receipt, encoding="ascii")
(out / "issuing").replace(out / label)
if label in {"lost-response", "lost-worker"}:
    deadline = time.monotonic() + 20
    while not (out / "release").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
print(json.dumps({"issued": label, "receipt": receipt}))
"""


def install_tool(root):
    catalog = root / "capabilities"
    tool = catalog / "absorbed" / "issue-receipt"
    tool.mkdir(parents=True)
    (tool / "tool.py").write_text(TOOL, encoding="utf-8")
    manifest = {
        "schema_version": 1, "slug": tool.name, "name": "Issue a receipt",
        "command": ["python", "tool.py"], "requires": ["label"], "provides": ["issued", "receipt"],
        "cases": [{"input": {"label": label}, "expect": {"issued": label}} for label in ("a", "b")],
    }
    (tool / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    (catalog / "ledger.json").write_text(json.dumps({"capabilities": {CAPABILITY: {"last_proof_exit_code": 0}}}),
                                         encoding="utf-8")


@contextmanager
def server(root, *, hooks=True):
    import blackhole_agent

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(blackhole_agent.__file__).resolve().parents[1])
    for key in ("BLACKHOLE_WEBHOOK_SECRET", "BLACKHOLE_WEBHOOK_HOOK"):
        env.pop(key, None)
    argv = [sys.executable, "-m", "blackhole_agent.capability_service", "serve",
            "--root", str(root), "--port", "0", "--token", TOKEN]
    if hooks:
        argv.extend(["--webhook-secret", SECRET, "--webhook-hook", "issue=" + CAPABILITY])
    with subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as process:
        try:
            ready = Queue()
            Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
            yield json.loads(ready.get(timeout=15))["listening"], process
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


def request(port, path, label=None, *, drop_response=False):
    headers = {"Authorization": "Bearer " + TOKEN}
    raw = None
    if label is not None:
        raw = json.dumps({"input": {"label": label}}).encode()
        headers["Content-Type"] = "application/json"
        headers["X-Hub-Signature-256"] = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=8)) as client:
        client.request("GET" if raw is None else "POST", path, raw, headers)
        if not drop_response:
            with client.getresponse() as reply:
                return reply.status, json.load(reply)


def until(read, ready, seconds=5):
    deadline = time.monotonic() + seconds
    while True:
        value = read()
        if ready(value) or time.monotonic() >= deadline:
            return value
        time.sleep(0.025)


def observe(root, stack, observed):
    install_tool(root)
    effects = root / ".blackhole-agent" / "invocation-artifacts"

    def receipts(label, count=1):
        return until(lambda: sorted(effects.glob("*/" + label)), lambda paths: len(paths) >= count)

    def get(port, run_id):
        status, row = request(port, "/hooks/" + (run_id or "unknown"))
        return row if status == 200 else {"http": status, "error": row.get("error")}

    def completed(port, run_id):
        return until(lambda: get(port, run_id), lambda row: row.get("status") == "completed")

    def post(port, label):
        return request(port, "/hooks/issue", label)

    def retry(port, label):
        status, row = post(port, label)
        return [status, row.get("error"), row.get("run_id")]

    owner, process = stack.enter_context(server(root))
    peer, peer_process = stack.enter_context(server(root))
    health = request(owner, "/health")[1]["webhook_replay_guard"]
    warm_status, warm = post(peer, "warm")
    warm_result = completed(peer, warm.get("run_id"))
    observed["independent_delivery"] = [warm_status, (warm_result.get("output") or {}).get("issued")]

    request(owner, "/hooks/issue", "lost-response", drop_response=True)
    first = receipts("lost-response")[0]
    issued = first.read_text(encoding="ascii")
    origin = retry(owner, "lost-response")
    other = retry(peer, "lost-response")
    recovered = other[2]
    live = get(peer, recovered).get("status")
    for mark in receipts("lost-response", 2 if other[0] == 202 else 1):
        (mark.parent / "release").touch()
    result = completed(peer, recovered)
    observed["lost_ack"] = {"origin_retry": origin, "peer_retry": other, "peer_saw": live,
                            "output": result.get("output"), "issued_receipt": issued,
                            "effects": len(receipts("lost-response"))}

    accepted, crash = post(owner, "lost-worker")
    crash_id = crash.get("run_id")
    abandoned = receipts("lost-worker")[0]
    stack.callback((abandoned.parent / "release").touch)
    before = get(peer, crash_id).get("status")
    process.kill()
    process.wait(timeout=10)
    after = until(lambda: get(peer, crash_id), lambda row: row.get("status") == "interrupted").get("status")
    orphan_retry = retry(peer, "lost-worker")
    orphan_marks = receipts("lost-worker", 2 if orphan_retry[0] == 202 else 1)
    for mark in orphan_marks:
        (mark.parent / "release").touch()
    observed["worker_exit"] = {"accepted": accepted, "before": before, "after": after,
                               "retry": orphan_retry, "original": crash_id, "effects": len(orphan_marks)}

    peer_process.kill()
    peer_process.wait(timeout=10)
    restarted, _ = stack.enter_context(server(root))
    persisted = retry(restarted, "lost-response")
    saved = get(restarted, recovered)
    observed["restart"] = {"retry": persisted, "output": saved.get("output"),
                           "worker_status": get(restarted, crash_id).get("status")}
    new_peer, _ = stack.enter_context(server(root))
    barrier = Barrier(2)

    def simultaneous(port):
        barrier.wait(timeout=5)
        return retry(port, "fresh")

    with ThreadPoolExecutor(max_workers=2) as clients:
        replies = sorted(clients.map(simultaneous, (new_peer, restarted)), key=lambda row: row[0])
    new_id = replies[0][2]
    fresh = completed(restarted, new_id)
    fresh_marks = receipts("fresh", sum(row[0] == 202 for row in replies))
    observed["concurrent_delivery"] = {"replies": replies, "output": fresh.get("output"), "effects": len(fresh_marks)}
    closed, _ = stack.enter_context(server(root, hooks=False))
    disabled = request(closed, "/health")[1]["webhook_replay_guard"]
    closed_status, closed_body = post(closed, "disabled")
    observed["opt_in"] = [health, disabled, closed_status, closed_body.get("error")]

    duplicate = [409, "webhook_replayed", recovered]
    expected = {"issued": "lost-response", "receipt": issued}
    return (
        observed["independent_delivery"] == [202, "warm"]
        and bool(issued and recovered) and origin == other == persisted == duplicate
        and live == "running" and result.get("output") == saved.get("output") == expected
        and len(receipts("lost-response")) == 1
        and accepted == 202 and bool(crash_id) and before == "running" and after == "interrupted"
        and orphan_retry == [409, "webhook_replayed", crash_id] and len(orphan_marks) == 1
        and observed["restart"]["worker_status"] == "interrupted"
        and bool(new_id) and new_id != recovered and replies == [[202, None, new_id], [409, "webhook_replayed", new_id]]
        and len(fresh_marks) == 1 and fresh.get("output") == {"issued": "fresh", "receipt": fresh_marks[0].read_text()}
        and observed["opt_in"] == [True, False, 404, "webhook_disabled"]
    )


def main():
    observed = {}
    try:
        with tempfile.TemporaryDirectory(prefix="webhook-receipts-") as directory, ExitStack() as stack:
            passed = observe(Path(directory), stack, observed)
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        passed = False
    return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main()))
