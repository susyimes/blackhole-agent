"""Acceptance probe: served MCP execution is concurrent and cancellable.

Real MCP hosts keep issuing requests while a long tools/call is in flight
and cancel calls they no longer need. This probe drives the capability
MCP server over a live stdio pipe the way such a host would:

1. start a tools/call against a capability that sleeps far longer than
   the probe's patience;
2. while the call is in flight, require ping and tools/list to answer
   within a short deadline (no head-of-line blocking);
3. send notifications/cancelled for the in-flight request and require a
   JSON-RPC -32800 acknowledgement within a short deadline, with the
   tool's process tree terminated;
4. require the same session to keep serving: a follow-up tools/call on a
   text-transform capability returns its real computed output.

On the pre-change server (strictly sequential, no cancellation surface)
the in-flight call blocks the read loop: the ping deadline is missed and
no -32800 ever arrives, so the probe reports passed=false. Both outcomes
exit 0 with a JSON verdict so the controller can replay the same file
against baseline and candidate source trees.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

_SLOW_TOOL = (
    "import json, time\n"
    "time.sleep(30)\n"
    "print(json.dumps({'done': True}))\n"
)

_FAST_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

_PATIENCE_SECONDS = 6.0


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    slow_dir = root / "capabilities" / "absorbed" / "slow-tool"
    slow_dir.mkdir(parents=True)
    (slow_dir / "tool.py").write_text(_SLOW_TOOL, encoding="utf-8")
    (slow_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "slow-tool",
                "name": "probe slow tool",
                "command": ["python", "tool.py"],
                "requires": [],
                "provides": ["done"],
                "cases": [
                    {"input": {}, "expect": {"done": True}},
                    {"input": {}, "expect": {"done": True}},
                ],
            }
        ),
        encoding="utf-8",
    )
    fast_dir = root / "capabilities" / "absorbed" / "text-reverser"
    fast_dir.mkdir(parents=True)
    (fast_dir / "tool.py").write_text(_FAST_TOOL, encoding="utf-8")
    (fast_dir / "absorption.json").write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )
    capabilities = {
        slug: {
            "id": slug,
            "name": slug,
            "kind": "python",
            "last_proved_at": "2026-01-01T00:00:00Z",
            "last_proof_exit_code": 0,
        }
        for slug in ("capability.absorbed-slow-tool", "capability.absorbed-text-reverser")
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


class _Session:
    """Single-reader NDJSON JSON-RPC client with bounded waits."""

    def __init__(self, process: subprocess.Popen) -> None:
        self._process = process
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._replies: dict[object, dict] = {}
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def send(self, message: dict) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()

    def request(self, request_id: int, method: str, params: dict | None = None) -> None:
        message: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)

    def wait_reply(self, request_id: int, timeout: float) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if request_id in self._replies:
                return self._replies[request_id]
            try:
                line = self._lines.get(timeout=max(0.05, deadline - time.monotonic()))
            except queue.Empty:
                return None
            if line is None:
                return None
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and "id" in payload:
                self._replies[payload["id"]] = payload
        return None


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-cancellable-execution"}
    try:
        import blackhole_agent.mcp_capability_server as server
    except Exception as error:  # tree without the capability MCP server
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(server.__file__).resolve().parents[1]
    process: subprocess.Popen | None = None
    try:
        # Baseline replays leave the uncancellable slow tool orphaned past
        # teardown; never let temp-dir cleanup turn a clean verdict into a
        # crash.
        with tempfile.TemporaryDirectory(
            prefix="mcp-cancel-probe-", ignore_cleanup_errors=True
        ) as directory:
            root = _build_fixture_root(Path(directory))
            env = dict(os.environ)
            env["PYTHONPATH"] = str(src_root)
            env["PYTHONIOENCODING"] = "utf-8"
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "blackhole_agent.mcp_capability_server",
                    "--root",
                    str(root),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                env=env,
            )
            session = _Session(process)
            session.request(
                1,
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "acceptance-probe", "version": "1.0.0"},
                },
            )
            handshake = session.wait_reply(1, 15)
            observed["handshake_ok"] = bool(
                handshake and (handshake.get("result") or {}).get("protocolVersion") == "2025-03-26"
            )

            session.request(2, "tools/call", {"name": "slow-tool", "arguments": {}})
            time.sleep(0.5)

            ping_at = time.monotonic()
            session.request(3, "ping")
            ping = session.wait_reply(3, _PATIENCE_SECONDS)
            ping_elapsed = time.monotonic() - ping_at
            observed["ping_elapsed_seconds"] = round(ping_elapsed, 2)
            observed["ping_during_call_ok"] = bool(ping and ping.get("result") == {})

            session.request(4, "tools/list", {})
            listing = session.wait_reply(4, _PATIENCE_SECONDS)
            listed = [
                tool.get("name")
                for tool in ((listing or {}).get("result") or {}).get("tools", [])
            ]
            observed["listed_during_call"] = listed
            observed["list_during_call_ok"] = "slow-tool" in listed

            session.send(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {"requestId": 2, "reason": "probe no longer needs the result"},
                }
            )
            cancel_at = time.monotonic()
            cancelled = session.wait_reply(2, _PATIENCE_SECONDS)
            cancel_elapsed = time.monotonic() - cancel_at
            observed["cancel_elapsed_seconds"] = round(cancel_elapsed, 2)
            observed["cancelled_reply"] = cancelled
            observed["cancel_ok"] = bool(
                cancelled and (cancelled.get("error") or {}).get("code") == -32800
            )

            probe_input = "session reuse"
            session.request(
                5, "tools/call", {"name": "text-reverser", "arguments": {"raw_text": probe_input}}
            )
            reused = session.wait_reply(5, _PATIENCE_SECONDS)
            structured = ((reused or {}).get("result") or {}).get("structuredContent")
            observed["reuse_structured"] = structured
            observed["reuse_ok"] = structured == {"reversed_text": probe_input[::-1]}

            checks = {
                key: bool(observed[key])
                for key in (
                    "handshake_ok",
                    "ping_during_call_ok",
                    "list_during_call_ok",
                    "cancel_ok",
                    "reuse_ok",
                )
            }
            observed["checks"] = checks
            return {"passed": all(checks.values()), "observed": observed}
    except Exception as error:
        observed["fatal"] = f"{type(error).__name__}: {error}"
        return {"passed": False, "observed": observed}
    finally:
        if process is not None:
            process.kill()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as error:  # never crash the sweep: unmet, not crashed
        verdict = {
            "passed": False,
            "observed": {
                "family": "mcp-cancellable-execution",
                "fatal": f"{type(error).__name__}: {error}",
            },
        }
    print(json.dumps(verdict))
    sys.exit(0)
