"""Acceptance probe: POST /bundles imports a capability onto the live plane.

CLI bundle transfer already re-proves a sealed payload into a checkout, but
the live invocation plane had no HTTP import path: a peer-exported bundle
never became invocable over POST /invoke. This probe starts the plane as a
separate OS process and requires:

1. GET /health reports bundle_import true when started with --bundle-import.
2. POST /bundles of a fixture absorbed tool returns HTTP 200 with imported
   true and the capability id.
3. GET /capabilities lists that id.
4. POST /invoke of that id returns the declared output.
5. POST /bundles of a tampered payload returns HTTP 400 and does not list
   a second id.
6. A plane started without --bundle-import reports bundle_import false and
   POST /bundles is HTTP 400 bundle_disabled.
7. POST /invoke of the text-reverser still returns the declared reverse.

On the pre-mission plane --bundle-import is unknown or POST /bundles is
404/400 without importing, so the probe reports passed=false. Both
outcomes exit 0 with JSON passed and nonempty observed.
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

PROBE_TEXT = "bundle-import-11c9fd20"
EXPECTED_REVERSE = PROBE_TEXT[::-1]
REVERSE_ID = "capability.absorbed-text-reverser"
SHOUT_ID = "capability.absorbed-bundle-shout"
SHOUT_INPUT = {"text": "blackhole unbound"}
SHOUT_OUTPUT = "BLACKHOLE UNBOUND!"
TAMPER_ID = "capability.absorbed-bundle-tamper"

_REVERSE_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)
_SHOUT_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'shout_output': state['text'].upper() + '!'}))\n"
)


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    timeout: int = 60,
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            try:
                parsed: object = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return response.status, parsed
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def _write_reverser(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "probe-workspace"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(_REVERSE_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
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
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {
                    REVERSE_ID: {
                        "id": REVERSE_ID,
                        "name": "probe text reverser",
                        "description": "probe fixture reverser",
                        "kind": "python",
                        "last_proved_at": "2026-01-01T00:00:00Z",
                        "last_proof_exit_code": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _write_source_tool(root: Path, *, slug: str, capability_id: str, tool: str, manifest: dict) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(tool, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {
                    capability_id: {
                        "id": capability_id,
                        "name": manifest["name"],
                        "description": manifest["name"],
                        "kind": "python",
                        "last_proved_at": "2026-01-01T00:00:00Z",
                        "last_proof_exit_code": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline() if process.stdout is not None else ""
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def _start_plane(
    src_root: Path,
    root: Path,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.Popen, dict[str, object]]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("BLACKHOLE_BUNDLE_IMPORT", None)
    command = [
        sys.executable,
        "-m",
        "blackhole_agent.capability_service",
        "serve",
        "--port",
        "0",
        "--root",
        str(root),
    ]
    if extra_args:
        command.extend(extra_args)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    sink: dict[str, object] = {}
    reader = threading.Thread(target=_read_ready_line, args=(process, sink), daemon=True)
    reader.start()
    reader.join(timeout=60)
    return process, sink


def _stop_plane(process: subprocess.Popen) -> str:
    process.kill()
    try:
        _out, err = process.communicate(timeout=10)
    except Exception:
        err = ""
    return err if isinstance(err, str) else ""


def _listing_ids(listing: object) -> list[str]:
    if not isinstance(listing, dict):
        return []
    return [
        str(item.get("id"))
        for item in (listing.get("capabilities") or [])
        if isinstance(item, dict)
    ]


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "bundle-import"}
    try:
        import blackhole_agent.capability_bundle as bundles
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(service, "import_bundle_http_request"):
        observed["detail"] = "baseline plane has no live bundle import"
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="bundle-import-probe-") as directory:
        base = Path(directory)
        root = base / "repo"
        _write_reverser(root)

        source = base / "source"
        source.mkdir()
        _write_source_tool(
            source,
            slug="bundle-shout",
            capability_id=SHOUT_ID,
            tool=_SHOUT_TOOL,
            manifest={
                "schema_version": 1,
                "slug": "bundle-shout",
                "name": "probe bundle shout",
                "command": ["python", "tool.py"],
                "requires": ["text"],
                "provides": ["shout_output"],
                "cases": [
                    {"input": {"text": "hi"}, "expect": {"shout_output": "HI!"}},
                    {"input": {"text": "ok"}, "expect": {"shout_output": "OK!"}},
                ],
            },
        )
        exported = bundles.export_capability_bundle(source, SHOUT_ID, base / "shout.bundle.json")
        bundle = json.loads((base / "shout.bundle.json").read_text(encoding="utf-8"))
        observed["exported"] = exported

        tampered = json.loads(json.dumps(bundle))
        record = tampered["files"]["tool.py"]
        record["content_b64"] = ("A" if record["content_b64"][0] != "A" else "B") + record["content_b64"][1:]
        tampered["capability_id"] = TAMPER_ID
        tampered["slug"] = "bundle-tamper"

        process, sink = _start_plane(src_root, root, ["--bundle-import"])
        try:
            ready = sink.get("ready")
            observed["ready"] = ready
            if not isinstance(ready, dict) or not ready.get("listening"):
                err = _stop_plane(process)
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            url = f"http://127.0.0.1:{ready['listening']}"
            observed["ready_bundle_import"] = ready.get("bundle_import")

            health_status, health = _request("GET", f"{url}/health")
            observed["health_status"] = health_status
            observed["health"] = health if isinstance(health, dict) else None
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("bundle_import") is True
            )

            import_status, imported = _request("POST", f"{url}/bundles", bundle, timeout=180)
            observed["import_status"] = import_status
            observed["imported"] = imported if isinstance(imported, dict) else None
            import_ok = (
                import_status == 200
                and isinstance(imported, dict)
                and imported.get("imported") is True
                and imported.get("capability_id") == SHOUT_ID
            )

            cap_status, listing = _request("GET", f"{url}/capabilities")
            ids = _listing_ids(listing)
            observed["capability_ids"] = ids
            listed_ok = cap_status == 200 and SHOUT_ID in ids

            shout_status, shouted = _request(
                "POST",
                f"{url}/invoke",
                {"capability_id": SHOUT_ID, "input": SHOUT_INPUT},
            )
            observed["shout_status"] = shout_status
            observed["shouted"] = shouted if isinstance(shouted, dict) else None
            shout_ok = (
                shout_status == 200
                and isinstance(shouted, dict)
                and shouted.get("output", {}).get("shout_output") == SHOUT_OUTPUT
            )

            before_absorbed = {
                path.name
                for path in (root / "capabilities" / "absorbed").iterdir()
                if path.is_dir()
            }
            tamper_status, tamper = _request("POST", f"{url}/bundles", tampered, timeout=60)
            observed["tamper_status"] = tamper_status
            observed["tamper"] = tamper if isinstance(tamper, dict) else None
            after_ids = _listing_ids(_request("GET", f"{url}/capabilities")[1])
            after_absorbed = {
                path.name
                for path in (root / "capabilities" / "absorbed").iterdir()
                if path.is_dir()
            }
            tamper_ok = (
                tamper_status == 400
                and isinstance(tamper, dict)
                and tamper.get("error") in {"tampered", "malformed"}
                and TAMPER_ID not in after_ids
                and after_absorbed == before_absorbed
            )

            reverse_status, reversed_body = _request(
                "POST",
                f"{url}/invoke",
                {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
            )
            observed["reverse_status"] = reverse_status
            observed["reversed"] = reversed_body if isinstance(reversed_body, dict) else None
            reverse_ok = (
                reverse_status == 200
                and isinstance(reversed_body, dict)
                and reversed_body.get("output", {}).get("reversed_text") == EXPECTED_REVERSE
            )
        finally:
            observed["server_stderr"] = (_stop_plane(process) or "")[-4000:]

        closed_root = base / "closed"
        _write_reverser(closed_root)
        closed, closed_sink = _start_plane(src_root, closed_root)
        try:
            closed_ready = closed_sink.get("ready")
            observed["closed_ready"] = closed_ready
            if not isinstance(closed_ready, dict) or not closed_ready.get("listening"):
                err = _stop_plane(closed)
                observed["closed_detail"] = "closed plane never reported a listening port"
                observed["closed_stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            closed_url = f"http://127.0.0.1:{closed_ready['listening']}"
            closed_health_status, closed_health = _request("GET", f"{closed_url}/health")
            observed["closed_health"] = closed_health if isinstance(closed_health, dict) else None
            closed_health_ok = (
                closed_health_status == 200
                and isinstance(closed_health, dict)
                and closed_health.get("bundle_import") is False
            )
            refused_status, refused = _request("POST", f"{closed_url}/bundles", bundle, timeout=30)
            observed["closed_refused"] = refused if isinstance(refused, dict) else None
            refused_ok = (
                refused_status == 400
                and isinstance(refused, dict)
                and refused.get("error") == "bundle_disabled"
            )
            closed_reverse_status, closed_reversed = _request(
                "POST",
                f"{closed_url}/invoke",
                {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
            )
            closed_reverse_ok = (
                closed_reverse_status == 200
                and isinstance(closed_reversed, dict)
                and closed_reversed.get("output", {}).get("reversed_text") == EXPECTED_REVERSE
            )
            closed_ok = closed_health_ok and refused_ok and closed_reverse_ok
        finally:
            observed["closed_stderr"] = (_stop_plane(closed) or "")[-4000:]

        passed = all(
            (
                health_ok,
                import_ok,
                listed_ok,
                shout_ok,
                tamper_ok,
                reverse_ok,
                closed_ok,
            )
        )
        observed["checks"] = {
            "health": health_ok,
            "import": import_ok,
            "listed": listed_ok,
            "shout_invoke": shout_ok,
            "tamper": tamper_ok,
            "reverse_invoke": reverse_ok,
            "fail_closed": closed_ok,
        }
        return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict))
    sys.exit(0)
