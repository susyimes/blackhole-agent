"""Outcome probe: live invoke harvests TEMP files and serves them over HTTP.

POST /invoke currently deletes per-invocation TEMP after the tool exits, so a
capability that writes a report cannot be retrieved by a client. This probe
starts the invocation plane as a separate OS process and requires:

1. GET /health reports invocation_artifacts true.
2. POST /invoke of a fixture that writes report.txt (and nested out/note.txt)
   into TEMP returns HTTP 200 with invocation_id and those artifact names.
3. GET /artifacts/{id} lists both files with nonzero bytes.
4. GET /artifacts/{id}/report.txt returns the exact marker bytes the tool wrote.
5. GET /artifacts/{id}/out/note.txt returns the nested marker.
6. GET /artifacts/{id}/../ledger.json and GET /artifacts/missing-id are refused.
7. POST /invoke of the sibling text-reverser still returns the declared reverse
   and does not advertise the writer's files.

On the pre-mission plane serve_invocation_artifact is missing or GET
/artifacts is 404, so the probe reports passed=false. Both outcomes exit 0
with JSON passed and nonempty observed.
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
from urllib.error import HTTPError, URLError

PROBE_TEXT = "artifact-harvest-d97dc002"
EXPECTED_REVERSE = PROBE_TEXT[::-1]
MARKER = "BH-ARTIFACT-OK-d97dc002"
NESTED_MARKER = "BH-ARTIFACT-NESTED-d97dc002"
WRITER_ID = "capability.absorbed-artifact-writer"
REVERSE_ID = "capability.absorbed-text-reverser"

_WRITER_TOOL = r"""
import json, os, sys
from pathlib import Path
state = json.load(sys.stdin)
scratch = Path(os.environ.get("TEMP") or os.environ.get("TMP") or os.environ.get("TMPDIR") or ".")
(scratch / "report.txt").write_text(state["marker"], encoding="utf-8")
nested = scratch / "out"
nested.mkdir(exist_ok=True)
(nested / "note.txt").write_text(state["nested"], encoding="utf-8")
print(json.dumps({"saved": state["marker"]}))
"""

_REVERSE_TOOL = (
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
        "artifact-writer",
        _WRITER_TOOL,
        ["marker", "nested"],
        ["saved"],
    )
    _write_tool(root, "text-reverser", _REVERSE_TOOL, ["raw_text"], ["reversed_text"])
    capabilities = {
        WRITER_ID: _ledger_entry(WRITER_ID, "probe artifact writer"),
        REVERSE_ID: _ledger_entry(REVERSE_ID, "probe text reverser"),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    try:
        line = process.stdout.readline() if process.stdout is not None else ""
        sink["ready_line"] = line[:500] if isinstance(line, str) else ""
        sink["ready"] = json.loads(line)
    except Exception as exc:
        sink["ready"] = None
        sink["ready_error"] = f"{type(exc).__name__}: {exc}"


def _request_json(method: str, url: str, payload: dict | None = None, *, timeout: int = 40) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            try:
                return response.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return response.status, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, raw
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def _request_bytes(url: str, *, timeout: int = 20) -> tuple[int, bytes]:
    req = urlrequest.Request(url, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()
    except (URLError, TimeoutError, OSError):
        return 0, b""


def _stop_plane(process: subprocess.Popen) -> str:
    process.kill()
    try:
        _out, err = process.communicate(timeout=10)
    except Exception:
        err = ""
    return err if isinstance(err, str) else ""


def _artifact_names(payload: object) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    rows = payload.get("artifacts")
    if rows is None:
        rows = payload.get("files")
    if not isinstance(rows, list):
        return set()
    names: set[str] = set()
    for row in rows:
        if isinstance(row, dict) and row.get("name"):
            names.add(str(row["name"]))
        elif isinstance(row, str):
            names.add(row)
    return names


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "invocation-artifacts"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(service, "serve_invocation_artifact"):
        observed["detail"] = "baseline plane has no invocation artifact HTTP surface"
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="invocation-artifacts-probe-", ignore_cleanup_errors=True)
    process: subprocess.Popen | None = None
    try:
        root = _build_fixture_root(Path(scratch.name))
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_root)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
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
        sink: dict[str, object] = {}
        reader = threading.Thread(target=_read_ready_line, args=(process, sink), daemon=True)
        reader.start()
        reader.join(timeout=60)
        ready = sink.get("ready")
        observed["ready"] = ready
        if not isinstance(ready, dict) or "listening" not in ready:
            observed["ready_error"] = sink.get("ready_error")
            observed["stderr"] = _stop_plane(process)[-2000:]
            process = None
            return {"passed": False, "observed": observed}

        port = int(ready["listening"])
        base = f"http://127.0.0.1:{port}"

        health_status, health = _request_json("GET", f"{base}/health")
        observed["health_status"] = health_status
        observed["health_flag"] = health.get("invocation_artifacts") if isinstance(health, dict) else None
        health_ok = (
            health_status == 200
            and isinstance(health, dict)
            and health.get("invocation_artifacts") is True
        )

        write_status, written = _request_json(
            "POST",
            f"{base}/invoke",
            {
                "capability_id": WRITER_ID,
                "input": {"marker": MARKER, "nested": NESTED_MARKER},
            },
        )
        observed["write_status"] = write_status
        observed["write_output"] = written.get("output") if isinstance(written, dict) else None
        invocation_id = written.get("invocation_id") if isinstance(written, dict) else None
        write_names = _artifact_names(written)
        observed["write_invocation_id"] = invocation_id
        observed["write_artifacts"] = sorted(write_names)
        write_ok = (
            write_status == 200
            and isinstance(written, dict)
            and written.get("ok") is True
            and written.get("output") == {"saved": MARKER}
            and isinstance(invocation_id, str)
            and bool(invocation_id)
            and "report.txt" in write_names
            and "out/note.txt" in write_names
        )

        list_status, listing = _request_json("GET", f"{base}/artifacts/{invocation_id}")
        list_names = _artifact_names(listing)
        observed["list_status"] = list_status
        observed["list_files"] = listing.get("files") if isinstance(listing, dict) else None
        list_ok = (
            list_status == 200
            and isinstance(listing, dict)
            and listing.get("ok") is True
            and listing.get("invocation_id") == invocation_id
            and "report.txt" in list_names
            and "out/note.txt" in list_names
        )

        report_status, report_body = _request_bytes(f"{base}/artifacts/{invocation_id}/report.txt")
        nested_status, nested_body = _request_bytes(f"{base}/artifacts/{invocation_id}/out/note.txt")
        observed["report_status"] = report_status
        observed["nested_status"] = nested_status
        observed["report_body"] = report_body.decode("utf-8", errors="replace")[:200]
        observed["nested_body"] = nested_body.decode("utf-8", errors="replace")[:200]
        files_ok = (
            report_status == 200
            and report_body == MARKER.encode("utf-8")
            and nested_status == 200
            and nested_body == NESTED_MARKER.encode("utf-8")
        )

        traverse_status, traverse_body = _request_json(
            "GET", f"{base}/artifacts/{invocation_id}/%2e%2e/ledger.json"
        )
        missing_status, missing_body = _request_json("GET", f"{base}/artifacts/missing-invocation-id")
        observed["traverse_status"] = traverse_status
        observed["traverse_error"] = (
            traverse_body.get("error") if isinstance(traverse_body, dict) else traverse_body
        )
        observed["missing_status"] = missing_status
        refuse_ok = (
            traverse_status in {400, 404}
            and (not isinstance(traverse_body, (bytes, str)) or MARKER not in str(traverse_body))
            and missing_status == 404
            and isinstance(missing_body, dict)
            and missing_body.get("ok") is False
        )

        follow_status, follow = _request_json(
            "POST",
            f"{base}/invoke",
            {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
        )
        follow_output = follow.get("output") if isinstance(follow, dict) else None
        follow_names = _artifact_names(follow)
        observed["follow_status"] = follow_status
        observed["follow_output"] = follow_output
        observed["follow_artifacts"] = sorted(follow_names)
        follow_ok = (
            follow_status == 200
            and isinstance(follow, dict)
            and follow.get("ok") is True
            and follow_output == {"reversed_text": EXPECTED_REVERSE}
            and "report.txt" not in follow_names
        )

        passed = bool(
            health_ok and write_ok and list_ok and files_ok and refuse_ok and follow_ok
        )
        observed["checks"] = {
            "health_ok": health_ok,
            "write_ok": write_ok,
            "list_ok": list_ok,
            "files_ok": files_ok,
            "refuse_ok": refuse_ok,
            "follow_ok": follow_ok,
        }
        return {"passed": passed, "observed": observed}
    finally:
        if process is not None:
            observed["stderr"] = _stop_plane(process)[-2000:]
        scratch.cleanup()


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0)
