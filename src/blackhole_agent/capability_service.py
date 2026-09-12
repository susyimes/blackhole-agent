"""Live invocation plane: the compounded ledger answers real HTTP clients.

The ledger holds hundreds of proved, absorbed capabilities, but until now
nothing outside the repository's own proof harness could call one: the only
way to execute a vendored tool was to re-run its frozen proof cases. This
module turns the ledger into a service:

- ``GET /capabilities`` lists every *invocable* capability — proved
  (``last_proof_exit_code == 0``) absorbed entries whose vendored manifest is
  present — with the declared ``requires``/``provides`` contract and a digest
  of the listing, so a client can verify it is looking at the same ledger.
- ``POST /invoke`` executes one absorbed capability end-to-end: the request
  input is validated strictly against the manifest's ``requires`` keys
  (missing or extra keys are refused before anything runs), the vendored
  command runs as a real subprocess against the vendored tree, and the
  declared ``provides`` fragment is returned with a response digest binding
  capability id, input, and output.
- ``POST /contract`` machine-evaluates a semicolon-separated done_when outcome
  contract against the served ledger: ``program_passes`` steps execute for real
  (isolated subprocesses against the ledger's own entries), and the verdict
  carries per-predicate results, the skill-route attestation, and a contract
  digest binding the done_when text to the evaluated predicates and verdict.
- The plane is fail-closed: unknown, unproved, or non-absorbed capability
  ids, malformed bodies, missing/extra input keys, and empty or
  non-machine-checkable done_when texts all return a non-2xx JSON error and
  never spawn a subprocess.

Determinism contract: listing digests and response digests are pure
functions of ledger content and invocation payload; durations and
timestamps are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_absorption import (
    capability_id_for_slug,
    load_manifest,
)
from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    evaluate_outcome_contract,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)

SCHEMA_VERSION = 1
SERVICE_CAPABILITY_ID = "capability.ledger-invocation-plane"
SERVICE_CAPABILITY_NAME = "Live HTTP invocation plane for the compounded ledger"
REPO_ROOT = Path(__file__).resolve().parents[2]
ABSORBED_ID_PREFIX = "capability.absorbed-"
INVOKE_TIMEOUT_SECONDS = 30
CONTRACT_TIMEOUT_SECONDS = 120
MAX_BODY_BYTES = 1 << 20


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def absorbed_root(root: Path) -> Path:
    return root / "capabilities" / "absorbed"


def load_invocable_capabilities(root: Path) -> dict[str, dict[str, Any]]:
    """Return proved absorbed capabilities with a readable vendored manifest."""

    path = root / "capabilities" / "ledger.json"
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = ledger.get("capabilities")
    if not isinstance(entries, dict):
        return {}
    invocable: dict[str, dict[str, Any]] = {}
    for capability_id, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        if not capability_id.startswith(ABSORBED_ID_PREFIX):
            continue
        if entry.get("last_proof_exit_code") != 0:
            continue
        slug = capability_id[len(ABSORBED_ID_PREFIX):]
        tool_root = absorbed_root(root) / slug
        try:
            manifest = load_manifest(tool_root)
        except ValueError:
            continue
        invocable[capability_id] = {
            "id": capability_id,
            "slug": slug,
            "name": str(entry.get("name") or manifest.get("name") or slug),
            "requires": [str(key) for key in manifest["requires"]],
            "provides": [str(key) for key in manifest["provides"]],
            "command": [str(part) for part in manifest["command"]],
            "tool_root": str(tool_root),
        }
    return invocable


def capability_listing(root: Path) -> dict[str, Any]:
    """Public listing payload: contract fields only, sorted, digest-bound."""

    invocable = load_invocable_capabilities(root)
    capabilities = [
        {
            "id": item["id"],
            "slug": item["slug"],
            "name": item["name"],
            "requires": item["requires"],
            "provides": item["provides"],
        }
        for item in (invocable[key] for key in sorted(invocable))
    ]
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "count": len(capabilities),
        "capabilities": capabilities,
        "listing_digest": _digest(capabilities),
    }


def _normalized_command(command: Sequence[str]) -> list[str]:
    parts = [str(part) for part in command]
    if parts and parts[0] in {"python", "python3", "python.exe"}:
        parts[0] = sys.executable
    return parts


def _tool_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class InvocationError(Exception):
    """Fail-closed refusal raised before or during tool execution."""

    def __init__(self, status: int, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.error = error


def invoke_capability(
    root: Path,
    capability_id: str,
    provided_input: Any,
    *,
    timeout: int = INVOKE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute one proved absorbed capability against its vendored tree."""

    if not isinstance(capability_id, str) or not capability_id.strip():
        raise InvocationError(400, "capability_id must be a non-empty string")
    invocable = load_invocable_capabilities(root)
    item = invocable.get(capability_id)
    if item is None:
        raise InvocationError(404, f"unknown or non-invocable capability: {capability_id}")
    if not isinstance(provided_input, dict):
        raise InvocationError(422, "input must be a JSON object")
    requires = set(item["requires"])
    keys = set(provided_input)
    missing = sorted(requires - keys)
    extra = sorted(keys - requires)
    if missing or extra:
        problems = []
        if missing:
            problems.append(f"missing required keys: {missing}")
        if extra:
            problems.append(f"unexpected keys: {extra}")
        raise InvocationError(422, "; ".join(problems))
    command = _normalized_command(item["command"])
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(provided_input),
            capture_output=True,
            text=True,
            cwd=item["tool_root"],
            env=_tool_env(),
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InvocationError(502, f"tool execution failed: {type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip().splitlines()
        detail = stderr[0] if stderr else "no stderr"
        raise InvocationError(502, f"tool exited {completed.returncode}: {detail}")
    try:
        fragment = json.loads(completed.stdout or "")
    except json.JSONDecodeError as exc:
        raise InvocationError(502, f"tool stdout is not a JSON fragment: {exc}") from exc
    if not isinstance(fragment, dict):
        raise InvocationError(502, "tool stdout must be a JSON object")
    missing_provides = [key for key in item["provides"] if key not in fragment]
    if missing_provides:
        raise InvocationError(502, f"tool output missing provides keys: {missing_provides}")
    output = {key: fragment[key] for key in item["provides"]}
    return {
        "ok": True,
        "capability_id": capability_id,
        "output": output,
        "response_digest": _digest(
            {"capability_id": capability_id, "input": provided_input, "output": output}
        ),
    }


def evaluate_contract_request(
    root: Path,
    done_when: Any,
    *,
    timeout: int = CONTRACT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Machine-evaluate a done_when outcome contract against the served ledger.

    ``program_passes`` predicates execute for real via the outcome-contract
    evaluator; the response distills the verdict and binds it with a digest.
    Empty or non-machine-checkable contracts are refused before any program
    step runs.
    """

    if not isinstance(done_when, str) or not done_when.strip():
        raise InvocationError(422, "done_when must be a non-empty string")
    text = done_when.strip()
    result = evaluate_outcome_contract(
        Path(root).resolve(), text, run_programs=True, timeout=timeout
    )
    if not result.get("machine_checkable"):
        raise InvocationError(422, "done_when has no machine-checkable predicates")
    verdict = {
        "ok": bool(result.get("ok")) and not result.get("used_skill_route_discovery"),
        "done_when": text,
        "met": result.get("met"),
        "passed_count": result.get("passed_count"),
        "failed_count": result.get("failed_count"),
        "predicate_count": result.get("predicate_count"),
        "results": result.get("results") or [],
        "used_skill_route_discovery": bool(result.get("used_skill_route_discovery")),
    }
    verdict["contract_digest"] = _digest(
        {
            "done_when": text,
            "met": verdict["met"],
            "results": verdict["results"],
            "used_skill_route_discovery": verdict["used_skill_route_discovery"],
        }
    )
    return verdict


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def build_server(root: Path, *, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Bind the invocation plane; port 0 selects an ephemeral port."""

    service_root = Path(root).resolve()

    class CapabilityHandler(BaseHTTPRequestHandler):
        server_version = "blackhole-capability-service/1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                _json_response(self, 200, {"ok": True, "schema_version": SCHEMA_VERSION})
                return
            if self.path == "/capabilities":
                _json_response(self, 200, capability_listing(service_root))
                return
            _json_response(self, 404, {"ok": False, "error": f"unknown path: {self.path}"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in {"/invoke", "/contract"}:
                _json_response(self, 404, {"ok": False, "error": f"unknown path: {self.path}"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                _json_response(self, 400, {"ok": False, "error": "invalid Content-Length"})
                return
            if length <= 0 or length > MAX_BODY_BYTES:
                _json_response(self, 400, {"ok": False, "error": "missing or oversized body"})
                return
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                _json_response(self, 400, {"ok": False, "error": f"body is not valid JSON: {exc}"})
                return
            if not isinstance(body, dict):
                _json_response(self, 400, {"ok": False, "error": "body must be a JSON object"})
                return
            try:
                if self.path == "/contract":
                    result = evaluate_contract_request(service_root, body.get("done_when"))
                else:
                    result = invoke_capability(
                        service_root, body.get("capability_id"), body.get("input")
                    )
            except InvocationError as exc:
                _json_response(self, exc.status, {"ok": False, "error": exc.error})
                return
            _json_response(self, 200, result)

    server = ThreadingHTTPServer((host, port), CapabilityHandler)
    server.daemon_threads = True
    return server


def serve(root: Path, *, port: int = 0, host: str = "127.0.0.1") -> int:
    """Run the invocation plane until interrupted; prints a readiness line."""

    server = build_server(root, host=host, port=port)
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    listing = capability_listing(Path(root).resolve())
    print(
        json.dumps(
            {
                "listening": bound_port,
                "host": bound_host,
                "invocable_count": listing["count"],
                "listing_digest": listing["listing_digest"],
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _http_request(
    method: str,
    url: str,
    payload: Mapping[str, Any] | None = None,
    *,
    timeout: int = 30,
) -> tuple[int, Any]:
    from urllib import request as urlrequest
    from urllib.error import HTTPError, URLError

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except json.JSONDecodeError:
            return exc.code, None
    except (URLError, TimeoutError, OSError):
        return 0, None


def builtin_capability_service_proof(root: Path | None = None) -> dict[str, Any]:
    """Hermetic proof: the live ledger answers a real loopback HTTP client."""

    service_root = (root or REPO_ROOT).resolve()
    server = build_server(service_root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    checks: dict[str, bool] = {}
    detail: dict[str, Any] = {}
    try:
        port = server.server_address[1]
        base = f"http://127.0.0.1:{port}"
        status, listing = _http_request("GET", f"{base}/capabilities")
        target_id = capability_id_for_slug("text-reverser")
        listed = {
            item["id"]: item for item in (listing or {}).get("capabilities", [])
        } if isinstance(listing, dict) else {}
        checks["listing_ok"] = status == 200 and isinstance(listing, dict) and listing.get("ok")
        checks["text_reverser_listed"] = target_id in listed
        checks["contract_exposed"] = listed.get(target_id, {}).get("requires") == ["raw_text"]
        status, invoked = _http_request(
            "POST",
            f"{base}/invoke",
            {"capability_id": target_id, "input": {"raw_text": "blackhole"}},
        )
        checks["invoke_ok"] = (
            status == 200
            and isinstance(invoked, dict)
            and invoked.get("output", {}).get("reversed_text") == "elohkcalb"
        )
        detail["invoked"] = invoked
        status, refused = _http_request(
            "POST",
            f"{base}/invoke",
            {"capability_id": "capability.absorbed-does-not-exist", "input": {}},
        )
        checks["unknown_refused"] = status == 404 and isinstance(refused, dict) and not refused.get("ok")
        status, bad_keys = _http_request(
            "POST",
            f"{base}/invoke",
            {"capability_id": target_id, "input": {"wrong_key": "x"}},
        )
        checks["bad_input_refused"] = status == 422 and isinstance(bad_keys, dict) and not bad_keys.get("ok")
        status, contract = _http_request(
            "POST",
            f"{base}/contract",
            {"done_when": "program_passes:capability.ledger-inventory;no_skill_route"},
            timeout=CONTRACT_TIMEOUT_SECONDS + 30,
        )
        checks["contract_met"] = (
            status == 200
            and isinstance(contract, dict)
            and contract.get("met") is True
            and contract.get("used_skill_route_discovery") is False
            and bool(contract.get("contract_digest"))
        )
        detail["contract"] = contract
        status, unmet = _http_request(
            "POST",
            f"{base}/contract",
            {"done_when": "program_passes:capability.absorbed-does-not-exist;no_skill_route"},
        )
        checks["unmet_contract_reported"] = (
            status == 200 and isinstance(unmet, dict) and unmet.get("met") is False
        )
        status, refused_contract = _http_request("POST", f"{base}/contract", {"done_when": "  "})
        checks["empty_contract_refused"] = (
            status == 422
            and isinstance(refused_contract, dict)
            and not refused_contract.get("ok")
        )
        status, free_text = _http_request(
            "POST", f"{base}/contract", {"done_when": "the ledger is healthy"}
        )
        checks["non_machine_contract_refused"] = (
            status == 422 and isinstance(free_text, dict) and not free_text.get("ok")
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
    return {
        "ok": bool(checks) and all(checks.values()),
        "action": "capability_service",
        "checks": checks,
        "detail": detail,
    }


def capability_service_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.capability_service import "
        "builtin_capability_service_proof; r=builtin_capability_service_proof(); "
        "assert r['ok'] and r.get('action')=='capability_service' "
        "and all(r['checks'].values())\""
    )


def ensure_capability_service_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the invocation plane on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SERVICE_CAPABILITY_ID,
        name=SERVICE_CAPABILITY_NAME,
        description=(
            "The compounded ledger answers real HTTP clients: GET /capabilities "
            "lists every proved absorbed capability with its requires/provides "
            "contract and a listing digest, POST /invoke executes one "
            "absorbed capability as a real subprocess against its vendored "
            "tree, returning the declared provides fragment with a response "
            "digest, and POST /contract machine-evaluates a done_when outcome "
            "contract with real program_passes execution, per-predicate "
            "verdicts, skill-route attestation, and a contract digest. "
            "Unknown, unproved, or non-absorbed ids, malformed inputs, and "
            "empty or non-machine-checkable contracts are refused fail-closed "
            "without spawning a subprocess."
        ),
        kind="python",
        entry="blackhole_agent.capability_service:builtin_capability_service_proof",
        proof_command=capability_service_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.absorbed-text-reverser",
        ),
        behavior_paths=(
            "src/blackhole_agent/capability_service.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Proved ledger capabilities are callable from outside the proof "
            "harness: an external HTTP client can discover the invocable set, "
            "execute an absorbed tool end-to-end, and machine-check a "
            "done_when outcome contract with real program_passes execution "
            "and skill-route attestation, with strict input validation and "
            "fail-closed refusals for unknown or unproved ids and for empty "
            "or non-machine-checkable contracts."
        ),
        tags=("ledger", "invocation", "contract", "http", "service", "operator-plane"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live capability invocation plane")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_parser = sub.add_parser("serve", help="serve the invocation plane over HTTP")
    serve_parser.add_argument("--port", type=int, default=0, help="0 picks an ephemeral port")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--root", type=Path, default=REPO_ROOT)
    proof_parser = sub.add_parser("proof", help="run the hermetic invocation-plane proof")
    proof_parser.add_argument("--root", type=Path, default=REPO_ROOT)
    sub.add_parser("register", help="register the capability on the live ledger")
    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve(args.root, port=args.port, host=args.host)
    if args.command == "proof":
        result = builtin_capability_service_proof(args.root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    capability = ensure_capability_service_capability()
    print(json.dumps({"registered": capability.id}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
