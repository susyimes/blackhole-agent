"""Acceptance probe: the live plane caps untrusted-tool scratch disk.

Filesystem sandbox already confines writes to per-invocation TEMP, and
job RAM / captured stdout are size-capped, but that TEMP directory itself
was unbounded. A fixture tool that dumps a large file into TEMP can fill
the host volume even though its own job stayed small.

This probe starts the invocation plane as a separate OS process with
BLACKHOLE_MAX_SCRATCH_BYTES=65536, invokes a fixture tool that writes a
200000-byte file into TEMP, and requires HTTP 502 with violation
scratch_limited whose body does not contain the oversized blob. GET
/health reports the cap. A small scratch write still succeeds. A
follow-up text-reverser invoke still returns the declared reverse output.

On the pre-mission plane the oversized invoke returns HTTP 200 whose
output includes the wrote byte count, so the probe reports passed=false.
Both outcomes exit 0 with JSON ``passed`` and nonempty ``observed``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError

PROBE_TEXT = "scratch-cap-dfcd4b63"
EXPECTED = PROBE_TEXT[::-1]
CAP_BYTES = 65536
BLOB_SIZE = 200000

_BOMB_TOOL = r"""
import json, os, sys
from pathlib import Path
state = json.load(sys.stdin)
scratch = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
blob = scratch / "bomb.bin"
blob.write_bytes(b"A" * int(state["size"]))
print(json.dumps({"reversed_text": state["raw_text"][::-1], "wrote": blob.stat().st_size}))
"""

_SMALL_TOOL = r"""
import json, os, sys
from pathlib import Path
state = json.load(sys.stdin)
scratch = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
marker = scratch / "ok.bin"
marker.write_bytes(b"ok")
print(json.dumps({
    "reversed_text": state["raw_text"][::-1],
    "scratch_ok": marker.read_bytes() == b"ok",
}))
"""

_FAST_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)


def _ledger_entry(capability_id: str, name: str) -> dict:
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


def _write_tool(root: Path, slug: str, source: str, requires: list[str], provides: list[str]) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": f"probe {slug}",
                "command": ["python", "tool.py"],
                "requires": requires,
                "provides": provides,
                "cases": [
                    {
                        "input": {key: "x" for key in requires},
                        "expect": {provides[0]: "x"},
                    }
                    for _ in ("a", "b")
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(
        root,
        "scratch-bomb",
        _BOMB_TOOL,
        ["raw_text", "size"],
        ["reversed_text", "wrote"],
    )
    _write_tool(
        root,
        "scratch-small",
        _SMALL_TOOL,
        ["raw_text"],
        ["reversed_text", "scratch_ok"],
    )
    _write_tool(root, "text-reverser", _FAST_TOOL, ["raw_text"], ["reversed_text"])
    capabilities = {
        "capability.absorbed-scratch-bomb": _ledger_entry(
            "capability.absorbed-scratch-bomb", "probe scratch bomb"
        ),
        "capability.absorbed-scratch-small": _ledger_entry(
            "capability.absorbed-scratch-small", "probe scratch small"
        ),
        "capability.absorbed-text-reverser": _ledger_entry(
            "capability.absorbed-text-reverser", "probe text reverser"
        ),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    try:
        line = process.stdout.readline()
        sink["ready_line"] = line[:500] if isinstance(line, str) else ""
        sink["ready"] = json.loads(line)
    except Exception as exc:
        sink["ready"] = None
        sink["ready_error"] = f"{type(exc).__name__}: {exc}"


def _request(
    method: str, url: str, payload: dict | None = None, *, timeout: int = 30
) -> tuple[int, object, int]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = None
            return response.status, body, len(raw)
    except HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = None
        return exc.code, body, len(raw)


def _reclaim_package_temp() -> None:
    """Drop leftover AppContainer TEMP files so sequential probe runs stay isolated."""

    try:
        local = os.environ.get("LOCALAPPDATA") or ""
        if os.name != "nt" or not local:
            return
        folder = Path(local) / "Packages" / "bh.unbound.tool.v3" / "AC" / "Temp"
        if not folder.is_dir():
            return
        for dirpath, _dirnames, filenames in os.walk(folder):
            for name in filenames:
                try:
                    (Path(dirpath) / name).unlink()
                except OSError:
                    continue
    except Exception:
        return


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "scratch-disk-limit"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="scratch-disk-limit-probe-", ignore_cleanup_errors=True)
    try:
        base = Path(scratch.name)
        root = _build_fixture_root(base)
        _reclaim_package_temp()
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_root)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["BLACKHOLE_MAX_SCRATCH_BYTES"] = str(CAP_BYTES)
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
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        try:
            sink: dict[str, object] = {}
            reader = threading.Thread(target=_read_ready_line, args=(process, sink), daemon=True)
            reader.start()
            reader.join(timeout=60)
            ready = sink.get("ready")
            observed["ready"] = ready
            if sink.get("ready_error"):
                observed["ready_error"] = sink.get("ready_error")
            if not isinstance(ready, dict) or not ready.get("listening"):
                err = process.stderr.read() if process.stderr else ""
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = err[-2000:] if isinstance(err, str) else ""
                observed["ready_line"] = sink.get("ready_line")
                return {"passed": False, "observed": observed}

            port = int(ready["listening"])
            base_url = f"http://127.0.0.1:{port}"

            health_status, health, _health_len = _request("GET", f"{base_url}/health")
            observed["health_status"] = health_status
            observed["health"] = health
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("ok") is True
                and int(health.get("max_scratch_bytes") or 0) == CAP_BYTES
            )

            bomb_status, bomb, bomb_len = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-scratch-bomb",
                    "input": {"raw_text": PROBE_TEXT, "size": BLOB_SIZE},
                },
                timeout=40,
            )
            bomb_output = bomb.get("output") if isinstance(bomb, dict) else None
            wrote = bomb_output.get("wrote") if isinstance(bomb_output, dict) else None
            error_text = str(bomb.get("error") or "") if isinstance(bomb, dict) else ""
            raw_dump = json.dumps(bomb) if bomb is not None else ""
            observed["bomb_status"] = bomb_status
            observed["bomb_body_len"] = bomb_len
            observed["bomb_wrote"] = wrote
            observed["bomb_violation"] = bomb.get("violation") if isinstance(bomb, dict) else None
            observed["bomb_ok_field"] = bomb.get("ok") if isinstance(bomb, dict) else None
            observed["bomb_error_len"] = len(error_text)
            observed["bomb_error_has_blob"] = ("A" * 1024) in error_text
            bomb_ok = (
                bomb_status == 502
                and isinstance(bomb, dict)
                and bomb.get("ok") is False
                and bomb.get("violation") == "scratch_limited"
                and bomb_len < CAP_BYTES
                and wrote is None
                and ("A" * 1024) not in error_text
                and ("A" * 1024) not in raw_dump
            )

            small_status, small, _small_len = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-scratch-small",
                    "input": {"raw_text": PROBE_TEXT},
                },
            )
            small_output = small.get("output") if isinstance(small, dict) else None
            observed["small_status"] = small_status
            observed["small_output"] = small_output
            observed["small_violation"] = small.get("violation") if isinstance(small, dict) else None
            observed["small_error"] = small.get("error") if isinstance(small, dict) else None
            small_ok = (
                small_status == 200
                and isinstance(small_output, dict)
                and small_output.get("reversed_text") == EXPECTED
                and small_output.get("scratch_ok") is True
            )

            follow_status, follow, _follow_len = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": PROBE_TEXT},
                },
            )
            output = follow.get("output") if isinstance(follow, dict) else None
            observed["follow_status"] = follow_status
            observed["follow_output"] = output
            observed["follow_violation"] = follow.get("violation") if isinstance(follow, dict) else None
            follow_ok = (
                follow_status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == EXPECTED
            )
            observed["checks"] = {
                "health_reports_cap": health_ok,
                "bomb_refused_without_blob": bomb_ok,
                "small_scratch_write_ok": small_ok,
                "follow_up_invoke_ok": follow_ok,
            }
            return {
                "passed": bool(health_ok and bomb_ok and small_ok and follow_ok),
                "observed": observed,
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
    finally:
        try:
            scratch.cleanup()
        except OSError:
            pass


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as exc:
        verdict = {
            "passed": False,
            "observed": {
                "error": type(exc).__name__,
                "detail": str(exc),
                "family": "scratch-disk-limit",
            },
        }
    print(json.dumps(verdict))
    sys.exit(0)
