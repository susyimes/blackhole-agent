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
- ``POST /invoke`` with ``Idempotency-Key`` durably reserves that key before
  execution and persists the HTTP response before sending it. Identical
  retries replay the saved response across restarts; conflicting payloads
  and unresolved executions return 409 without executing again. ``GET
  /invocations/{key}`` retrieves the response or the in-progress/unknown
  outcome. Receipts do not expire: a crash may occur after a side effect but
  before a response is recorded, so unknown outcomes require reconciliation.
- ``POST /contract`` machine-evaluates a semicolon-separated done_when outcome
  contract against the served ledger: ``program_passes`` steps execute for real
  as governed command trees (bounded memory and process count — a runaway
  proof command fails its step instead of harming the host), and the verdict
  carries per-predicate results, the skill-route attestation, and a contract
  digest binding the done_when text to the evaluated predicates and verdict.
- ``POST /solve`` answers a *declarative goal* instead of a named capability:
  the client supplies only an initial state and a list of goal state keys, a
  BFS planner derives a minimal program over the invocable ledger whose
  ``requires``/``provides`` chain covers the goal, every step executes for
  real through the same fail-closed subprocess machinery with threaded
  state, and the response carries the per-step digests and a plan digest
  binding initial state, goal, program, and outcome. Goals no proved
  capability chain covers return an honest ``solved: false`` verdict without
  spawning a subprocess; goals already satisfied by the initial state solve
  with an empty plan.
- ``POST /sessions`` upgrades one-shot solves into durable, interactive goal
  sessions (:mod:`blackhole_agent.capability_sessions`): when the goal needs
  state keys no invocable capability provides, an elicitation planner names
  exactly the minimal external keys the client must supply (answered as
  ``awaiting_input`` with per-key consumers, no subprocess spawned);
  ``POST /sessions/{id}/input`` resumes execution with the supplied keys;
  execution runs on a background thread whose transitions are persisted
  atomically, so a server restart recovers sessions — mid-execution ones as
  resumable ``interrupted`` — and ``DELETE /sessions/{id}`` cancels a
  running session by terminating the tool's entire owned process tree.
- The plane is fail-closed: unknown, unproved, or non-absorbed capability
  ids, malformed bodies, missing/extra input keys, empty or
  non-machine-checkable done_when texts, and malformed solve requests all
  return a non-2xx JSON error and never spawn a subprocess.
- ``GET /console`` (also ``/``) serves the operator console
  (:mod:`blackhole_agent.capability_console`): one self-contained HTML
  page with the live catalog embedded and inline JavaScript driving
  ``/health``, ``/capabilities``, ``/sessions``, ``/invoke`` and
  ``/solve`` — a browser with zero client installation can inspect the
  plane and execute real capabilities and goals.
- Executed tools are untrusted third-party code: every subprocess runs with
  a scrubbed allowlist environment
  (:data:`blackhole_agent.capability_absorption.TOOL_ENV_PASSTHROUGH`), so
  operator credentials in the plane's own process environment are never
  visible to vendored tools; anything a tool legitimately needs must arrive
  through its declared ``requires`` input keys.
- Tool execution is resource-governed, not just scrubbed: each invocation
  runs as an owned process tree under hard bounds (256 MiB committed memory
  for the whole tree, 32 active processes, 25 CPU-seconds, plus the
  wall-clock timeout). A tool that exceeds the memory or CPU limit is
  attributed deterministically — via job peak-memory and user-time/termination
  accounting, with a visible MemoryError as fallback — is answered with a
  distinct ``resource_limit`` violation verdict, and is durably quarantined
  in the ledger: later invocations are refused with a
  ``resource_quarantined`` verdict before any subprocess is spawned, while
  unaffected capabilities keep serving.
- Quarantine lifts only through supervised re-proof: ``POST /reproof``
  re-executes the quarantined capability's own frozen absorption cases for
  real under the same enforced memory/process limits; all cases passing
  reinstates the capability (recorded as ``resource_reproof`` on the ledger
  entry, with a digest-bound verdict), while any failure or renewed
  violation keeps the quarantine in force with a refreshed reason.
  Non-quarantined capabilities are refused — re-proof is never a general
  proof shortcut.
- Resource policy is per-capability and evidence-based: a ledger entry may
  declare ``resource_limits`` (``memory_bytes``/``max_processes``) which the
  plane enforces in place of the defaults for both live invocations and
  re-proofs (sanity-bounded to a host-safety envelope), and every successful
  re-proof records a ``resource_profile`` — the peak committed memory the
  frozen cases actually needed under the enforced limit — so policies are
  set from observation, not guesswork.

Determinism contract: listing digests, response digests, plans, and plan
digests are pure functions of ledger content and request payload; durations
and timestamps are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_absorption import (
    capability_id_for_slug,
    load_manifest,
    tool_execution_env,
)
from blackhole_agent.capability_compounder import (
    Capability,
    atomic_write_json,
    default_ledger_path,
    evaluate_outcome_contract,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.process_capture import (
    ProcessCancelled,
    ResourceLimits,
    run_captured_process,
)

SCHEMA_VERSION = 1
SERVICE_CAPABILITY_ID = "capability.ledger-invocation-plane"
SERVICE_CAPABILITY_NAME = "Live HTTP invocation plane for the compounded ledger"
REPO_ROOT = Path(__file__).resolve().parents[2]
ABSORBED_ID_PREFIX = "capability.absorbed-"
INVOKE_TIMEOUT_SECONDS = 30
CONTRACT_TIMEOUT_SECONDS = 120
SOLVE_MAX_STEPS = 8
# Self-healing solves re-prove at most this many quarantined blockers per
# request: supervised re-proof re-executes frozen cases for real, so the
# healing budget is bounded like every other governed execution.
SOLVE_MAX_HEALED = 4
MAX_BODY_BYTES = 1 << 20
# Untrusted tools run under hard tree-wide resource bounds: 256 MiB committed
# memory (comfortably above an interpreter's baseline, far below host RAM),
# 32 simultaneously active processes, and 25 CPU-seconds (below the 30s
# wall-clock timeout, so CPU hogs are attributed as resource violations
# rather than plain timeouts).
INVOKE_MEMORY_LIMIT_BYTES = 256 << 20
INVOKE_MAX_PROCESSES = 32
INVOKE_CPU_SECONDS = 25
# Contract program steps (``program_passes``) execute ledger run/proof
# commands — potentially heavy build/test harnesses, and for absorbed
# capabilities they end up running vendored third-party code. They get
# headroom over single-tool invocations but are still bounded: the era of
# ungoverned contract execution is over.
CONTRACT_MEMORY_LIMIT_BYTES = 512 << 20
CONTRACT_MAX_PROCESSES = 64
# Peak committed memory within this ratio of the limit marks a violation even
# when the tool masks its MemoryError with an ordinary nonzero exit.
MEMORY_VIOLATION_PEAK_RATIO = 0.80


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
            "quarantine": (
                dict(entry["resource_quarantine"])
                if isinstance(entry.get("resource_quarantine"), dict)
                else None
            ),
            "limits_override": _validated_limits_override(entry.get("resource_limits")),
        }
    return invocable


# Absolute ceiling for operator-declared per-capability limits: a policy can
# relax or tighten the defaults, never escape the host-safety envelope.
MAX_LIMIT_OVERRIDE_BYTES = 4 << 30
MIN_LIMIT_OVERRIDE_BYTES = 16 << 20


def _validated_limits_override(raw: Any) -> dict[str, int] | None:
    """Sanity-check an operator-declared ``resource_limits`` ledger field."""

    if not isinstance(raw, dict):
        return None
    override: dict[str, int] = {}
    memory = raw.get("memory_bytes")
    if isinstance(memory, int) and MIN_LIMIT_OVERRIDE_BYTES <= memory <= MAX_LIMIT_OVERRIDE_BYTES:
        override["memory_bytes"] = memory
    processes = raw.get("max_processes")
    if isinstance(processes, int) and 1 <= processes <= 256:
        override["max_processes"] = processes
    cpu = raw.get("cpu_seconds")
    if isinstance(cpu, int) and 1 <= cpu <= 3600:
        override["cpu_seconds"] = cpu
    return override or None


def effective_resource_limits(item: Mapping[str, Any]) -> ResourceLimits:
    """Per-capability policy when declared and valid, else the plane defaults."""

    override = _validated_limits_override(item.get("limits_override")) or {}
    return ResourceLimits(
        memory_bytes=int(override.get("memory_bytes") or INVOKE_MEMORY_LIMIT_BYTES),
        max_processes=int(override.get("max_processes") or INVOKE_MAX_PROCESSES),
        cpu_seconds=int(override.get("cpu_seconds") or INVOKE_CPU_SECONDS),
    )


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
    # Vendored tools are untrusted third-party code: run them with the
    # scrubbed allowlist environment, never the operator's ambient secrets.
    return tool_execution_env()


class InvocationError(Exception):
    """Fail-closed refusal raised before or during tool execution."""

    def __init__(self, status: int, error: str, *, extra: Mapping[str, Any] | None = None) -> None:
        super().__init__(error)
        self.status = status
        self.error = error
        self.extra = dict(extra or {})


def detect_resource_violation(
    completed: subprocess.CompletedProcess[str], limits: ResourceLimits
) -> dict[str, Any] | None:
    """Attribute a failed tool run to a resource limit, or return None.

    Windows job accounting is the primary signal: when peak committed memory
    reaches the enforced job limit the failure is a resource violation even if
    the tool disguised it as an ordinary nonzero exit. A visible MemoryError
    under a memory limit is the portable fallback signal.
    """

    stats = getattr(completed, "job_stats", None) or {}
    peak = int(stats.get("peak_job_memory_bytes") or 0)
    stderr = completed.stderr or ""
    if limits.cpu_seconds:
        user_time_100ns = int(stats.get("total_user_time_100ns") or 0)
        terminated = int(stats.get("total_terminated_processes") or 0)
        budget_100ns = limits.cpu_seconds * 10_000_000
        # A CPU-limit kill terminates every active process in the job; the
        # accounting pair (time at budget, processes terminated by the job)
        # distinguishes it from an ordinary crash or a wall-clock timeout.
        if terminated > 0 and user_time_100ns >= int(budget_100ns * 0.85):
            return {
                "resource": "cpu_time",
                "reason": (
                    f"tree consumed its enforced {limits.cpu_seconds}-second "
                    f"CPU budget ({user_time_100ns // 10_000_000}s user time) and "
                    f"was terminated by the job"
                ),
                "limit_cpu_seconds": limits.cpu_seconds,
                "user_time_seconds": user_time_100ns // 10_000_000,
            }
    if limits.memory_bytes:
        if peak >= int(limits.memory_bytes * MEMORY_VIOLATION_PEAK_RATIO):
            return {
                "resource": "memory",
                "reason": (
                    f"peak committed memory {peak} bytes reached the enforced "
                    f"{limits.memory_bytes}-byte tree limit"
                ),
                "limit_bytes": limits.memory_bytes,
                "peak_job_memory_bytes": peak,
            }
        if "MemoryError" in stderr:
            return {
                "resource": "memory",
                "reason": "tool raised MemoryError under the enforced memory limit",
                "limit_bytes": limits.memory_bytes,
                "peak_job_memory_bytes": peak,
            }
    return None


def record_resource_quarantine(
    root: Path, capability_id: str, violation: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Durably quarantine a resource-violating capability in the live ledger.

    The edit is made on the raw ledger document (not a dataclass round-trip)
    so quarantine works for any ledger entry shape and never rewrites other
    entries.
    """

    path = default_ledger_path(Path(root).resolve())
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entries = document.get("capabilities")
    if not isinstance(entries, dict) or not isinstance(entries.get(capability_id), dict):
        return None
    quarantine = {
        "reason": str(violation.get("reason") or "resource limit violated"),
        "resource": str(violation.get("resource") or "unknown"),
        "limit_bytes": violation.get("limit_bytes"),
        "peak_job_memory_bytes": violation.get("peak_job_memory_bytes"),
        "limit_cpu_seconds": violation.get("limit_cpu_seconds"),
        "user_time_seconds": violation.get("user_time_seconds"),
        "quarantined_at": utc_now_iso(),
    }
    entries[capability_id]["resource_quarantine"] = quarantine
    document["updated_at"] = utc_now_iso()
    atomic_write_json(path, document)
    return quarantine


def clear_resource_quarantine(
    root: Path, capability_id: str, reproof: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Lift a quarantine after a supervised re-proof, recording the event."""

    path = default_ledger_path(Path(root).resolve())
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entries = document.get("capabilities")
    if not isinstance(entries, dict) or not isinstance(entries.get(capability_id), dict):
        return None
    entry = entries[capability_id]
    if not isinstance(entry.get("resource_quarantine"), dict):
        return None
    entry.pop("resource_quarantine")
    entry["resource_reproof"] = {
        "reinstated_at": utc_now_iso(),
        "case_count": int(reproof.get("case_count") or 0),
        "cases_pass": bool(reproof.get("cases_pass")),
    }
    document["updated_at"] = utc_now_iso()
    atomic_write_json(path, document)
    return entry["resource_reproof"]


def _run_governed_case(
    tool_root: Path,
    command: Sequence[str],
    case: Mapping[str, Any],
    limits: ResourceLimits,
    timeout: int,
) -> dict[str, Any]:
    """Execute one frozen proof case under the plane's enforced resource bounds."""

    resolved = _normalized_command(command)
    try:
        completed = run_captured_process(
            resolved,
            cwd=Path(tool_root),
            timeout=timeout,
            input=json.dumps(case["input"]),
            env=_tool_env(),
            resource_limits=limits,
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if completed.returncode != 0:
        violation = detect_resource_violation(completed, limits)
        if violation is not None:
            return {"ok": False, "error": violation["reason"], "violation": violation}
        stderr = (completed.stderr or "").strip().splitlines()
        detail = stderr[0] if stderr else "no stderr"
        return {"ok": False, "error": f"exit {completed.returncode}: {detail}"}
    peak = int((getattr(completed, "job_stats", None) or {}).get("peak_job_memory_bytes") or 0)
    try:
        fragment = json.loads(completed.stdout or "")
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"tool stdout is not a JSON fragment: {exc}"}
    if not isinstance(fragment, dict):
        return {"ok": False, "error": "tool stdout must be a JSON object"}
    expect = case["expect"]
    mismatched = {key: fragment.get(key) for key in expect if fragment.get(key) != expect[key]}
    if mismatched:
        return {"ok": False, "error": f"output mismatch on keys: {sorted(mismatched)}"}
    return {
        "ok": True,
        "output": {key: fragment[key] for key in expect},
        "peak_job_memory_bytes": peak,
    }


def record_resource_profile(
    root: Path, capability_id: str, peak_job_memory_bytes: int, limits: ResourceLimits
) -> dict[str, Any] | None:
    """Record the proof-time resource profile observed under governed execution.

    The profile is evidence for operator limit policies: it captures the peak
    committed memory the capability's frozen cases actually needed, so a
    ``resource_limits`` override can be set from observation rather than guesswork.
    """

    if peak_job_memory_bytes <= 0:
        return None
    path = default_ledger_path(Path(root).resolve())
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entries = document.get("capabilities")
    if not isinstance(entries, dict) or not isinstance(entries.get(capability_id), dict):
        return None
    profile = {
        "peak_job_memory_bytes": int(peak_job_memory_bytes),
        "observed_at": utc_now_iso(),
        "observed_under_limit_bytes": limits.memory_bytes,
    }
    entries[capability_id]["resource_profile"] = profile
    document["updated_at"] = utc_now_iso()
    atomic_write_json(path, document)
    return profile


def reproof_capability(
    root: Path,
    capability_id: Any,
    *,
    timeout: int = INVOKE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Reinstate a quarantined capability only when its frozen cases pass governed.

    Quarantine is lifted exclusively through supervised re-proof: the
    capability's own frozen absorption cases re-execute for real under the
    same enforced memory/process limits that govern live invocations. Every
    case passing lifts the quarantine (recorded as ``resource_reproof`` on the
    ledger entry); any failure or renewed resource violation keeps the
    quarantine in force with a refreshed reason. Non-quarantined capabilities
    are refused — re-proof is not a general proof shortcut.
    """

    if not isinstance(capability_id, str) or not capability_id.strip():
        raise InvocationError(400, "capability_id must be a non-empty string")
    capability_id = capability_id.strip()
    invocable = load_invocable_capabilities(root)
    item = invocable.get(capability_id)
    if item is None:
        raise InvocationError(404, f"unknown or non-invocable capability: {capability_id}")
    if not item.get("quarantine"):
        raise InvocationError(409, f"capability is not quarantined: {capability_id}")
    manifest = load_manifest(Path(item["tool_root"]))
    limits = effective_resource_limits(item)
    case_results = [
        _run_governed_case(Path(item["tool_root"]), manifest["command"], case, limits, timeout)
        for case in manifest["cases"]
    ]
    cases_pass = all(result["ok"] for result in case_results)
    reproof_summary = {"case_count": len(case_results), "cases_pass": cases_pass}
    if cases_pass:
        peak = max(
            (int(result.get("peak_job_memory_bytes") or 0) for result in case_results),
            default=0,
        )
        clear_resource_quarantine(root, capability_id, reproof_summary)
        profile = record_resource_profile(root, capability_id, peak, limits)
        reinstated = True
    else:
        first_failure = next(
            (result for result in case_results if not result["ok"]), {"error": "unknown"}
        )
        record_resource_quarantine(
            root,
            capability_id,
            {
                "resource": (first_failure.get("violation") or {}).get("resource", "unknown"),
                "reason": f"re-proof failed under enforced limits: {first_failure['error']}",
                "limit_bytes": (first_failure.get("violation") or {}).get(
                    "limit_bytes", INVOKE_MEMORY_LIMIT_BYTES
                ),
                "peak_job_memory_bytes": (first_failure.get("violation") or {}).get(
                    "peak_job_memory_bytes"
                ),
            },
        )
        reinstated = False
        profile = None
    verdict = {
        "ok": True,
        "capability_id": capability_id,
        "reinstated": reinstated,
        "case_count": len(case_results),
        "cases_pass": cases_pass,
        "case_results": case_results,
        "resource_profile": profile,
        "enforced_limits": {
            "memory_bytes": limits.memory_bytes,
            "max_processes": limits.max_processes,
            "cpu_seconds": limits.cpu_seconds,
        },
    }
    verdict["reproof_digest"] = _digest(
        {
            "capability_id": capability_id,
            "reinstated": reinstated,
            "case_results": case_results,
        }
    )
    return verdict


def invoke_capability(
    root: Path,
    capability_id: str,
    provided_input: Any,
    *,
    timeout: int = INVOKE_TIMEOUT_SECONDS,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Execute one proved absorbed capability against its vendored tree.

    When ``cancel_event`` is given and becomes set while the tool runs, the
    tool's owned process tree is terminated and :class:`ProcessCancelled`
    propagates to the caller (goal sessions use this for ``DELETE``)."""

    if not isinstance(capability_id, str) or not capability_id.strip():
        raise InvocationError(400, "capability_id must be a non-empty string")
    invocable = load_invocable_capabilities(root)
    item = invocable.get(capability_id)
    if item is None:
        raise InvocationError(404, f"unknown or non-invocable capability: {capability_id}")
    if item.get("quarantine"):
        quarantine = item["quarantine"]
        raise InvocationError(
            409,
            "capability quarantined after resource violation: "
            f"{quarantine.get('reason', 'resource limit violated')}",
            extra={"violation": "resource_quarantined", "quarantine": quarantine},
        )
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
    limits = effective_resource_limits(item)
    try:
        completed = run_captured_process(
            command,
            cwd=Path(item["tool_root"]),
            timeout=timeout,
            input=json.dumps(provided_input),
            env=_tool_env(),
            resource_limits=limits,
            cancel_event=cancel_event,
        )
    except ProcessCancelled:
        raise
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        raise InvocationError(502, f"tool execution failed: {type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        violation = detect_resource_violation(completed, limits)
        if violation is not None:
            record_resource_quarantine(root, capability_id, violation)
            raise InvocationError(
                502,
                f"tool violated the enforced resource limits: {violation['reason']}",
                extra={"violation": "resource_limit", "resource": violation, "quarantined": True},
            )
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


def governed_command_runner(limits: ResourceLimits):
    """subprocess.run-compatible command runner that enforces resource bounds.

    Accepts both shell-string and argv-list commands exactly as
    ``capability_compounder`` calls ``subprocess.run``; the whole command tree
    runs owned and bounded via :func:`run_captured_process`. A wall-clock
    timeout surfaces as exit code 124 (a failed step) instead of an
    exception escaping the contract evaluator.
    """

    def run(command, *, cwd, timeout=None, env=None, shell=False, **kwargs):  # noqa: A002
        argv = command if isinstance(command, str) else [str(part) for part in command]
        try:
            return run_captured_process(
                argv,
                cwd=Path(cwd),
                timeout=float(timeout or 120),
                env=({str(key): str(value) for key, value in env.items()} if env else None),
                resource_limits=limits,
                shell=isinstance(command, str) or shell,
            )
        except subprocess.TimeoutExpired as exc:
            stderr = (exc.stderr or "") + "\nwall-clock timeout"
            return subprocess.CompletedProcess(argv, 124, exc.output or "", stderr)

    return run


def evaluate_contract_request(
    root: Path,
    done_when: Any,
    *,
    timeout: int = CONTRACT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Machine-evaluate a done_when outcome contract against the served ledger.

    ``program_passes`` predicates execute for real via the outcome-contract
    evaluator — under the plane's governance: every program step's command
    tree runs owned and bounded (:data:`CONTRACT_MEMORY_LIMIT_BYTES`,
    :data:`CONTRACT_MAX_PROCESSES`), so a runaway proof command is a failed
    step, not a host-level incident. The response distills the verdict and
    binds it with a digest. Empty or non-machine-checkable contracts are
    refused before any program step runs.
    """

    if not isinstance(done_when, str) or not done_when.strip():
        raise InvocationError(422, "done_when must be a non-empty string")
    text = done_when.strip()
    contract_limits = ResourceLimits(
        memory_bytes=CONTRACT_MEMORY_LIMIT_BYTES, max_processes=CONTRACT_MAX_PROCESSES
    )
    result = evaluate_outcome_contract(
        Path(root).resolve(),
        text,
        run_programs=True,
        timeout=timeout,
        command_runner=governed_command_runner(contract_limits),
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


def plan_goal_program(
    invocable: Mapping[str, Mapping[str, Any]],
    initial_keys: set[str],
    goal_keys: Sequence[str],
    *,
    max_steps: int = SOLVE_MAX_STEPS,
) -> list[str] | None:
    """BFS for a minimal invocable-capability program covering the goal keys.

    A step is applicable when every declared ``requires`` key is already
    available; applying it adds its declared ``provides`` keys. BFS over
    monotone key-set growth yields shortest programs first, and the sorted
    capability order makes the derived program deterministic. Returns
    ``None`` when no program exists — an honest unsolvable, never a
    fabricated sequence.
    """

    goal = set(goal_keys)
    start = frozenset(initial_keys)
    if goal <= start:
        return []
    queue: deque[tuple[frozenset[str], tuple[str, ...]]] = deque([(start, ())])
    visited = {start}
    while queue:
        available, program = queue.popleft()
        if len(program) >= max_steps:
            continue
        for capability_id in sorted(invocable):
            if capability_id in program:
                continue
            item = invocable[capability_id]
            if not set(item["requires"]) <= available:
                continue
            new_available = available | frozenset(item["provides"])
            new_program = program + (capability_id,)
            if goal <= new_available:
                return list(new_program)
            if new_available not in visited:
                visited.add(new_available)
                queue.append((new_available, new_program))
    return None


def solve_goal_request(
    root: Path,
    initial_state: Any,
    goal: Any,
    *,
    timeout: int = INVOKE_TIMEOUT_SECONDS,
    max_steps: int = SOLVE_MAX_STEPS,
    cancel_event: threading.Event | None = None,
    step_observer: Any = None,
) -> dict[str, Any]:
    """Derive and execute a capability program for a declarative goal.

    The request names no capability: the planner derives a minimal program
    from the served ledger's ``requires``/``provides`` contracts, and every
    planned step executes for real through :func:`invoke_capability` with
    state threaded from step outputs into downstream inputs. Unsolvable
    goals return an honest ``solved: false`` verdict without spawning a
    subprocess; malformed requests are refused before planning.

    Quarantined capabilities are excluded from planning. When the only
    program for a goal runs through quarantined steps, the solve heals
    instead of failing: each quarantined blocker (at most
    :data:`SOLVE_MAX_HEALED`) is re-proved inline through supervised
    governed re-execution of its frozen absorption cases — the same
    re-proof ``POST /reproof`` performs — and the goal is replanned against
    the reloaded ledger. The response's ``healing`` trace records every
    attempt with its case verdicts; a blocker whose cases genuinely fail
    keeps its quarantine and yields an honest ``solved: false`` naming it.

    ``cancel_event`` terminates the in-flight step's owned process tree
    (``ProcessCancelled`` propagates). ``step_observer(index, total,
    capability_id)`` is invoked after each completed step so streaming
    transports (the MCP capability server) can report per-step progress.
    """

    if not isinstance(initial_state, dict) or not all(
        isinstance(key, str) for key in initial_state
    ):
        raise InvocationError(422, "initial_state must be a JSON object keyed by state keys")
    if (
        not isinstance(goal, list)
        or not goal
        or not all(isinstance(key, str) and key.strip() for key in goal)
    ):
        raise InvocationError(422, "goal must be a non-empty list of state keys")
    goal_keys = list(dict.fromkeys(str(key).strip() for key in goal))
    invocable = load_invocable_capabilities(root)
    healing: list[dict[str, Any]] = []
    healthy = {
        capability_id: item
        for capability_id, item in invocable.items()
        if not item.get("quarantine")
    }
    program = plan_goal_program(
        healthy, set(initial_state), goal_keys, max_steps=max_steps
    )
    if program is None:
        # No healthy program. When a program exists only through quarantined
        # capabilities, heal instead of giving up: re-prove exactly the
        # quarantined blockers under governed re-execution of their frozen
        # cases, then replan against the reloaded ledger. Healing is bounded
        # (SOLVE_MAX_HEALED) and every attempt is recorded, reinstated or not.
        blocked_program = plan_goal_program(
            invocable, set(initial_state), goal_keys, max_steps=max_steps
        )
        if blocked_program is not None:
            blockers = [
                capability_id
                for capability_id in dict.fromkeys(blocked_program)
                if invocable[capability_id].get("quarantine")
            ][:SOLVE_MAX_HEALED]
            for capability_id in blockers:
                try:
                    verdict = reproof_capability(root, capability_id, timeout=timeout)
                except InvocationError as exc:
                    verdict = {"reinstated": False, "error": exc.error}
                entry: dict[str, Any] = {
                    "capability_id": capability_id,
                    "reinstated": bool(verdict.get("reinstated")),
                    "case_count": verdict.get("case_count"),
                    "cases_pass": verdict.get("cases_pass"),
                }
                if verdict.get("error"):
                    entry["error"] = verdict["error"]
                healing.append(entry)
            if any(entry["reinstated"] for entry in healing):
                invocable = load_invocable_capabilities(root)
                healthy = {
                    capability_id: item
                    for capability_id, item in invocable.items()
                    if not item.get("quarantine")
                }
                program = plan_goal_program(
                    healthy, set(initial_state), goal_keys, max_steps=max_steps
                )
    if program is None:
        result: dict[str, Any] = {
            "ok": True,
            "solved": False,
            "goal": goal_keys,
            "plan": None,
            "reason": "no proved capability program covers the goal",
        }
        if healing:
            unhealed = [entry["capability_id"] for entry in healing if not entry["reinstated"]]
            if unhealed:
                result["reason"] = (
                    "goal blocked by quarantined capabilities that failed "
                    "supervised re-proof: " + ", ".join(sorted(unhealed))
                )
            result["healing"] = healing
        return result
    state = dict(initial_state)
    steps: list[dict[str, Any]] = []
    total = len(program)
    for index, capability_id in enumerate(program, start=1):
        item = invocable[capability_id]
        step_input = {key: state[key] for key in item["requires"]}
        result = invoke_capability(
            root, capability_id, step_input, timeout=timeout, cancel_event=cancel_event
        )
        state.update(result["output"])
        steps.append(
            {
                "capability_id": capability_id,
                "input": step_input,
                "output": result["output"],
                "response_digest": result["response_digest"],
            }
        )
        if step_observer is not None:
            step_observer(index, total, capability_id)
    outcome = {key: state[key] for key in goal_keys}
    return {
        "ok": True,
        "solved": True,
        "goal": goal_keys,
        "plan": program,
        "steps": steps,
        "outcome": outcome,
        "healing": healing,
        "plan_digest": _digest(
            {
                "initial_state": initial_state,
                "goal": goal_keys,
                "plan": program,
                "steps": [
                    {"capability_id": step["capability_id"], "response_digest": step["response_digest"]}
                    for step in steps
                ],
                "outcome": outcome,
            }
        ),
    }


def _json_response(
    handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any],
    *, replayed: bool | None = None,
) -> None:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if replayed is not None:
        handler.send_header("Idempotency-Replayed", "true" if replayed else "false")
    handler.end_headers()
    handler.wfile.write(body)


def build_server(root: Path, *, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Bind the invocation plane; port 0 selects an ephemeral port."""

    service_root = Path(root).resolve()
    from blackhole_agent.capability_sessions import SessionManager
    from blackhole_agent.invocation_receipts import InvocationReceipts, ReceiptError

    sessions = SessionManager(service_root)
    sessions.recover()
    receipts = InvocationReceipts(service_root)

    class CapabilityHandler(BaseHTTPRequestHandler):
        server_version = "blackhole-capability-service/1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _session_id(self, prefix: str) -> str | None:
            path = self.path.split("?", 1)[0]
            if not path.startswith(prefix):
                return None
            rest = path[len(prefix):]
            if rest and "/" not in rest:
                return rest
            return None

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in {"/", "/console"}:
                from blackhole_agent.capability_console import console_html

                body = console_html(service_root).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/health":
                _json_response(self, 200, {"ok": True, "schema_version": SCHEMA_VERSION})
                return
            if path == "/capabilities":
                _json_response(self, 200, capability_listing(service_root))
                return
            invocation_key = self._session_id("/invocations/")
            if invocation_key is not None:
                try:
                    result = receipts.lookup(invocation_key)
                except ReceiptError as exc:
                    _json_response(self, exc.status, exc.payload)
                    return
                _json_response(self, 200, result)
                return
            if path == "/sessions":
                _json_response(self, 200, sessions.list_sessions())
                return
            session_id = self._session_id("/sessions/")
            if session_id is not None:
                try:
                    result = sessions.get_session(session_id)
                except InvocationError as exc:
                    _json_response(self, exc.status, {"ok": False, "error": exc.error, **exc.extra})
                    return
                _json_response(self, 200, result)
                return
            _json_response(self, 404, {"ok": False, "error": f"unknown path: {self.path}"})

        def do_DELETE(self) -> None:  # noqa: N802
            session_id = self._session_id("/sessions/")
            if session_id is None:
                _json_response(self, 404, {"ok": False, "error": f"unknown path: {self.path}"})
                return
            try:
                result = sessions.cancel_session(session_id)
            except InvocationError as exc:
                _json_response(self, exc.status, {"ok": False, "error": exc.error, **exc.extra})
                return
            _json_response(self, 200, result)

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            session_id = self._session_id("/sessions/")
            session_action = None
            if session_id is None and path.startswith("/sessions/"):
                rest = path[len("/sessions/"):]
                parts = rest.split("/")
                if len(parts) == 2 and parts[0] and parts[1] in {"input", "resume"}:
                    session_id, session_action = parts[0], parts[1]
            if path not in {"/invoke", "/contract", "/solve", "/reproof", "/sessions"} and not (
                session_id and session_action
            ):
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
            keys = self.headers.get_all("Idempotency-Key", [])
            if keys:
                if path != "/invoke" or len(keys) != 1:
                    _json_response(self, 400, {
                        "ok": False, "error": "one Idempotency-Key is supported only on POST /invoke",
                    })
                    return

                def operation() -> tuple[int, dict[str, Any]]:
                    try:
                        return 200, invoke_capability(
                            service_root, body.get("capability_id"), body.get("input")
                        )
                    except InvocationError as exc:
                        return exc.status, {"ok": False, "error": exc.error, **exc.extra}

                try:
                    status, result, replayed = receipts.execute(
                        keys[0], body.get("capability_id"), body.get("input"), operation
                    )
                except ReceiptError as exc:
                    _json_response(self, exc.status, exc.payload)
                    return
                _json_response(self, status, result, replayed=replayed)
                return
            try:
                if path == "/contract":
                    result = evaluate_contract_request(service_root, body.get("done_when"))
                elif path == "/solve":
                    result = solve_goal_request(
                        service_root, body.get("initial_state"), body.get("goal")
                    )
                elif path == "/reproof":
                    result = reproof_capability(service_root, body.get("capability_id"))
                elif path == "/sessions":
                    result = sessions.create_session(body.get("initial_state"), body.get("goal"))
                elif session_action == "input":
                    result = sessions.supply_input(session_id, body.get("input"))
                elif session_action == "resume":
                    result = sessions.resume_session(session_id)
                else:
                    result = invoke_capability(
                        service_root, body.get("capability_id"), body.get("input")
                    )
            except InvocationError as exc:
                _json_response(self, exc.status, {"ok": False, "error": exc.error, **exc.extra})
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
        status, solved = _http_request(
            "POST",
            f"{base}/solve",
            {"initial_state": {"raw_text": "blackhole"}, "goal": ["reversed_text"]},
        )
        checks["solve_derives_and_executes"] = (
            status == 200
            and isinstance(solved, dict)
            and solved.get("solved") is True
            and solved.get("plan") == [target_id]
            and solved.get("outcome", {}).get("reversed_text") == "elohkcalb"
            and bool(solved.get("plan_digest"))
            and len(solved.get("steps") or []) == 1
        )
        detail["solved"] = solved
        status, unsolved = _http_request(
            "POST",
            f"{base}/solve",
            {"initial_state": {"raw_text": "blackhole"}, "goal": ["no_such_key"]},
        )
        checks["unsolvable_goal_honest"] = (
            status == 200
            and isinstance(unsolved, dict)
            and unsolved.get("solved") is False
            and unsolved.get("plan") is None
        )
        status, satisfied = _http_request(
            "POST",
            f"{base}/solve",
            {"initial_state": {"reversed_text": "elohkcalb"}, "goal": ["reversed_text"]},
        )
        checks["satisfied_goal_empty_plan"] = (
            status == 200
            and isinstance(satisfied, dict)
            and satisfied.get("solved") is True
            and satisfied.get("plan") == []
            and satisfied.get("steps") == []
        )
        status, malformed = _http_request(
            "POST", f"{base}/solve", {"initial_state": {}, "goal": []}
        )
        checks["malformed_solve_refused"] = (
            status == 422 and isinstance(malformed, dict) and not malformed.get("ok")
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
            "POST /solve answers a declarative goal: the client names no "
            "capability, a BFS planner derives a minimal requires/provides "
            "program over the served ledger, every step executes for real "
            "with threaded state, and the response carries per-step digests "
            "and a plan digest binding goal, program, and outcome; goals no "
            "proved program covers return an honest solved=false verdict "
            "without spawning a subprocess. "
            "Unknown, unproved, or non-absorbed ids, malformed inputs, "
            "malformed solve requests, and "
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
            "execute an absorbed tool end-to-end, machine-check a "
            "done_when outcome contract with real program_passes execution "
            "and skill-route attestation, and submit a declarative goal "
            "(initial state plus goal keys) that the plane turns into a "
            "derived minimal capability program executed as real subprocesses "
            "with threaded state and a digest-bound outcome - goals no proved "
            "program covers are honestly reported unsolved without spawning a "
            "subprocess, and malformed or unknown requests are refused "
            "fail-closed."
        ),
        tags=("ledger", "invocation", "contract", "planning", "http", "service", "operator-plane"),
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
