"""Acceptance probe: MCP hosts solve declarative goals over the served ledger.

The controller replays probes on baseline and candidate source trees, so
this probe is fully self-contained and exits 0 for both met and unmet
outcomes. On baseline source the server has no goal-solving tool:
``tools/list`` lacks ``solve_goal`` and calling it is a protocol error, so
the probe reports passed=false. On candidate source it must:

1. complete a real MCP ``initialize`` over a live stdio pipe against a
   hermetic fixture ledger with two chainable proved capabilities
   (raw_text -> reversed_text -> shouted_text);
2. discover ``solve_goal`` in ``tools/list`` with an inputSchema naming
   ``initial_state`` and ``goal``;
3. call ``solve_goal`` with only an initial state and a goal key — the
   client names no capability — and receive a structuredContent result
   with ``solved: true``, a derived two-step plan in causal order, the
   correct threaded outcome, per-step response digests, and a
   ``plan_digest`` the probe recomputes over the returned fields;
4. observe per-step ``notifications/progress`` (progress 1..2, total 2)
   on the attached progress token while the plan executes;
5. receive an honest ``solved: false`` (not an error) for a goal no
   proved program covers, and ``isError`` for a malformed goal.

Prints JSON with boolean passed and nonempty observed.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

_REVERSER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

_SHOUTER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'shouted_text': state['reversed_text'].upper()}))\n"
)

_SOLVE_TOOL = "solve_goal"


def _write_tool(root: Path, slug: str, source: str, requires: list, provides: list) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    case_in = {key: "ab" for key in requires}
    case_in_two = {key: "cd" for key in requires}
    manifest = {
        "schema_version": 1,
        "slug": slug,
        "name": f"probe {slug}",
        "command": ["python", "tool.py"],
        "requires": requires,
        "provides": provides,
        "cases": [
            {"input": case_in, "expect": {key: "x" for key in provides}},
            {"input": case_in_two, "expect": {key: "y" for key in provides}},
        ],
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    root.mkdir(parents=True)
    _write_tool(root, "text-reverser", _REVERSER, ["raw_text"], ["reversed_text"])
    _write_tool(root, "text-shouter", _SHOUTER, ["reversed_text"], ["shouted_text"])
    capabilities = {}
    for slug in ("text-reverser", "text-shouter"):
        capability_id = f"capability.absorbed-{slug}"
        capabilities[capability_id] = {
            "id": capability_id,
            "name": f"probe {slug}",
            "kind": "python",
            "last_proved_at": "2026-01-01T00:00:00Z",
            "last_proof_exit_code": 0,
        }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


class _StdioClient:
    """Minimal NDJSON JSON-RPC client; records notifications while waiting."""

    def __init__(self, process: subprocess.Popen) -> None:
        self._process = process
        self._lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self._next_id = 0
        self.notifications: list[dict] = []

    def _pump(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def request(self, method: str, params: dict | None = None, *, timeout: float = 60.0) -> dict:
        self._next_id += 1
        request_id = self._next_id
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()
        while True:
            try:
                line = self._lines.get(timeout=timeout)
            except queue.Empty as exc:
                raise TimeoutError(f"no response to {method} within {timeout}s") from exc
            if line is None:
                raise ConnectionError(f"server stdout closed while awaiting {method}")
            payload = json.loads(line)
            if not isinstance(payload, dict):
                continue
            if payload.get("id") == request_id:
                return payload
            if "id" not in payload and payload.get("method"):
                self.notifications.append(payload)

    def drain_notifications(self, *, grace: float = 2.0) -> None:
        while True:
            try:
                line = self._lines.get(timeout=grace)
            except queue.Empty:
                return
            if line is None:
                return
            payload = json.loads(line)
            if isinstance(payload, dict) and "id" not in payload and payload.get("method"):
                self.notifications.append(payload)


def _spawn(src_root: Path, root: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        [sys.executable, "-m", "blackhole_agent.mcp_capability_server", "--root", str(root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _expected_plan_digest(result: dict) -> str:
    from blackhole_agent.capability_service import _digest

    return _digest(
        {
            "initial_state": {"raw_text": "blackhole"},
            "goal": result.get("goal"),
            "plan": result.get("plan"),
            "steps": [
                {"capability_id": step["capability_id"], "response_digest": step["response_digest"]}
                for step in result.get("steps") or []
            ],
            "outcome": result.get("outcome"),
        }
    )


def _check_fixture_server(src_root: Path, observed: dict) -> bool:
    with tempfile.TemporaryDirectory(prefix="mcp-goal-probe-") as directory:
        root = _build_fixture_root(Path(directory))
        process = _spawn(src_root, root)
        try:
            client = _StdioClient(process)
            handshake = client.request(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "acceptance-probe", "version": "1.0.0"},
                },
            )
            result = handshake.get("result") or {}
            observed["handshake_protocol"] = result.get("protocolVersion")
            handshake_ok = result.get("protocolVersion") == "2025-03-26"

            listing = client.request("tools/list", {})
            tools = (listing.get("result") or {}).get("tools") or []
            solve_tools = [tool for tool in tools if tool.get("name") == _SOLVE_TOOL]
            observed["solve_tool_listed"] = bool(solve_tools)
            schema = (solve_tools[0].get("inputSchema") if solve_tools else {}) or {}
            observed["solve_tool_required"] = schema.get("required")
            listing_ok = (
                len(solve_tools) == 1
                and schema.get("required") == ["initial_state", "goal"]
            )

            called = client.request(
                "tools/call",
                {
                    "name": _SOLVE_TOOL,
                    "arguments": {
                        "initial_state": {"raw_text": "blackhole"},
                        "goal": ["shouted_text"],
                    },
                    "_meta": {"progressToken": "probe-goal-1"},
                },
            )
            client.drain_notifications()
            call_result = called.get("result") or {}
            structured = call_result.get("structuredContent") or {}
            observed["structured"] = structured
            observed["is_error"] = call_result.get("isError")

            expected_plan = [
                "capability.absorbed-text-reverser",
                "capability.absorbed-text-shouter",
            ]
            steps = structured.get("steps") or []
            solve_ok = (
                call_result.get("isError") is False
                and structured.get("ok") is True
                and structured.get("solved") is True
                and structured.get("plan") == expected_plan
                and structured.get("outcome") == {"shouted_text": "blackhole"[::-1].upper()}
                and len(steps) == 2
                and all(step.get("response_digest") for step in steps)
            )
            digest = structured.get("plan_digest")
            try:
                digest_ok = bool(digest) and digest == _expected_plan_digest(structured)
            except Exception as error:
                observed["digest_error"] = f"{type(error).__name__}: {error}"
                digest_ok = False
            observed["plan_digest_verified"] = digest_ok

            progress = [
                note.get("params") or {}
                for note in client.notifications
                if note.get("method") == "notifications/progress"
                and (note.get("params") or {}).get("progressToken") == "probe-goal-1"
            ]
            observed["progress_notifications"] = progress
            step_progress = [p for p in progress if p.get("total") == 2]
            progress_ok = [p.get("progress") for p in step_progress] == [1, 2]

            unsolvable = client.request(
                "tools/call",
                {
                    "name": _SOLVE_TOOL,
                    "arguments": {"initial_state": {}, "goal": ["no_such_state_key"]},
                },
            )
            unsolved_result = (unsolvable.get("result") or {}).get("structuredContent") or {}
            observed["unsolvable"] = unsolved_result
            unsolvable_ok = (
                (unsolvable.get("result") or {}).get("isError") is False
                and unsolved_result.get("solved") is False
                and unsolved_result.get("plan") is None
            )

            malformed = client.request(
                "tools/call",
                {"name": _SOLVE_TOOL, "arguments": {"initial_state": {}, "goal": []}},
            )
            malformed_result = malformed.get("result") or {}
            observed["malformed_is_error"] = malformed_result.get("isError")
            malformed_ok = malformed_result.get("isError") is True

            observed["checks"] = {
                "handshake": handshake_ok,
                "solve_tool_listed": listing_ok,
                "solve_derives_and_executes": solve_ok,
                "plan_digest": digest_ok,
                "per_step_progress": progress_ok,
                "unsolvable_honest": unsolvable_ok,
                "malformed_refused": malformed_ok,
            }
            return all(observed["checks"].values())
        finally:
            process.kill()


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-goal-solving"}
    try:
        import blackhole_agent.mcp_capability_server as server
    except Exception as error:  # baseline source tree has no capability MCP server
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    if not hasattr(server, "SOLVE_TOOL_NAME"):
        observed["detail"] = "server module has no goal-solving tool"
        return {"passed": False, "observed": observed}

    src_root = Path(server.__file__).resolve().parents[1]
    try:
        fixture_ok = _check_fixture_server(src_root, observed)
    except Exception as error:
        observed["fixture_error"] = f"{type(error).__name__}: {error}"
        fixture_ok = False
    observed["fixture_ok"] = fixture_ok
    return {"passed": bool(fixture_ok), "observed": observed}


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as error:  # never crash the sweep: unmet, not crashed
        verdict = {
            "passed": False,
            "observed": {
                "family": "mcp-goal-solving",
                "fatal": f"{type(error).__name__}: {error}",
            },
        }
    print(json.dumps(verdict))
    sys.exit(0)
