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
  and unresolved executions return 409 without executing again. ``POST
  /solve`` honors the same header, binding the key to initial state plus
  goal so a dropped declarative solve is safe to retry without running the
  planned program twice. MCP ``tools/call`` (including ``solve_goal``)
  honors ``_meta.idempotencyKey`` through the same receipt store.
  ``GET /invocations/{key}`` retrieves the response or the in-progress/unknown
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
  with an empty plan. ``dry_run: true`` (or ``Prefer: solve=preview``)
  returns that ranked program, ``plan_evidence``, and a ``dry_run``
  verdict without starting a subprocess, writing a tool canary, healing
  quarantines, or occupying an admission slot. A live solve of the same
  goal still executes. ``GET /health`` reports ``solve_plan_preview``.
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
  plane and execute real capabilities and goals. The same page creates
  durable goal sessions, answers elicitation for missing external keys,
  resumes interrupted sessions, cancels running ones, and watches
  ``GET /sessions/{id}/events``. Invoke from the page uses
  ``Accept: text/event-stream`` so live stdout/stderr appear before the
  JSON result. In-flight ``/invoke``
  and ``/solve`` fetches carry an AbortController; cancelling them (or
  closing the tab) hangs up the HTTP socket so the plane can reap the
  tool tree.
- ``GET /sessions/{id}/events`` with ``Accept: text/event-stream`` is
  the session reverse channel: each persisted transition is written as
  SSE (snapshot first) so a browser can watch ``awaiting_input`` through
  ``solved`` or ``cancelled`` without polling. GET without a known
  session is 404; GET that does not accept the event stream is 406. The
  stream closes after a terminal status. JSON ``POST /invoke`` remains
  the default; ``Accept: text/event-stream`` opts into live output.
- ``POST /sessions`` may include ``notify_url`` and ``notify_secret``.
  When the session reaches a terminal status the plane POSTs a
  GitHub-style HMAC-signed JSON body (``X-Hub-Signature-256``) to that
  URL so a disconnected operator still receives the outcome. Only
  loopback http(s) URLs are accepted; redirects are not followed; 5xx
  and transport failures retry a bounded number of times. The secret
  is stored on the session record and redacted from every HTTP
  response. A session without ``notify_url`` does not POST. REST
  ``POST /invoke`` is unchanged.
- Dropped HTTP clients do not leak tool processes: ``POST /invoke`` and
  ``POST /solve`` watch the request socket while the owned command tree
  runs. A hang-up, reset, or aborted curl sets the same cancel event
  goal sessions and the MCP server already thread into
  :func:`run_captured_process`, so the Windows job / POSIX process group
  is terminated instead of running out the wall-clock timeout. The
  aborted request answers ``499`` with ``cancelled: true`` when the
  client is still writable; a follow-up invoke on the same server still
  works.
- The same process serves Streamable HTTP MCP at ``POST /mcp``: an HTTP-only
  MCP host completes ``initialize``, lists invocable absorbed tools, and
  ``tools/call`` executes them through the governed plane (sandbox, resource
  bounds, disconnect-cancel). Sessions are identified by ``Mcp-Session-Id``;
  ``DELETE /mcp`` ends one. ``GET /mcp`` with that session and
  ``Accept: text/event-stream`` is the reverse channel: progress
  notifications for a ``progressToken`` ``tools/call`` are written as SSE,
  a concurrent ``POST /mcp`` of ``notifications/cancelled`` reaps the
  in-flight tool tree so the original POST answers JSON-RPC ``-32800``,
  and a ledger mutation that changes the invocable tool set publishes
  ``notifications/tools/list_changed`` (and ``resources/list_changed``)
  so a connected host re-lists without a new session. ``initialize``
  advertises ``tools.listChanged`` and ``resources.listChanged``.
  GET without a session is 404; GET that does not accept the event stream
  is 406. REST ``POST /invoke`` is unchanged. The same catalog also exposes
  MCP resources (public contracts and tool schemas) and a
  ``prepare_capability_call`` prompt with an embedded live contract;
  retrieving metadata never executes a capability.
- Operator authentication is fail-closed when a token is configured
  (``--token`` or ``BLACKHOLE_INVOCATION_TOKEN``): catalog and session
  reads, every mutating route, invocation-receipt lookups, and ``/mcp``
  require ``Authorization: Bearer``. A missing or malformed header answers
  ``401`` with ``WWW-Authenticate`` and never spawns a subprocess; a
  wrong token answers ``403`` the same way. ``GET /health`` and the
  operator console document stay reachable without a token so liveness
  probes and the page itself still load; the console attaches the
  operator token to the invoke/solve/session fetches it already makes.
  An unset token keeps the historical open loopback plane.
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
- Concurrent trees are globally admitted, not just per-tree bounded:
  ``POST /invoke``, ``POST /solve``, session steps, and MCP ``tools/call``
  share one in-flight cap (``BLACKHOLE_MAX_INFLIGHT``, default 8). A request
  that would start another untrusted tree while the cap is full is answered
  ``429`` with ``violation: admission_limited`` and ``Retry-After`` and never
  spawns. ``GET /health`` reports the live ``inflight`` / ``max_inflight``
  snapshot so an operator can see the cap without a token. Idempotent
  ``429`` responses are not stored as durable receipts: the key may be
  reused once a slot is free.
- Captured tool stdout and stderr are size-capped, not just the child's
  job RAM: ``POST /invoke`` (and solve/session/MCP ``tools/call``) never
  loads more than ``BLACKHOLE_MAX_OUTPUT_BYTES`` (default 1 MiB) of either
  stream into the trusted process. A tool that prints a large JSON blob is
  reaped and answered ``502`` with ``violation: output_limited``; the HTTP
  body does not echo the oversized blob. ``GET /health`` reports
  ``max_output_bytes``. Kernel and git subprocesses omit the cap.
- ``POST /invoke`` with ``Accept: text/event-stream`` (and without
  ``application/json``) streams captured stdout and stderr as SSE
  ``output`` events while the owned tree is still running, then a
  terminal ``result`` or ``error`` event. The operator console uses
  that Accept header so a browser watches a running tool instead of
  waiting for the JSON blob. Default JSON ``POST /invoke`` is
  unchanged. Idempotent invokes keep the saved JSON receipt.
  ``GET /health`` reports ``live_invoke_stream``.
- ``POST /solve`` with ``dry_run: true`` or ``Prefer: solve=preview`` is
  a plan preview: the same evidence-ranked planner runs, the response
  names the program that would execute, and no owned tool tree starts.
  ``GET /health`` reports ``solve_plan_preview``. The operator console
  preview control posts that flag. Idempotency receipts bind the
  preview flag so a later live solve with the same key is a new
  operation.
- Tool execution is filesystem-sandboxed: the owned tree runs inside an
  OS-enforced allowlist (Windows AppContainer, Linux Landlock) of the
  vendored tool tree, a per-invocation scratch directory, and the
  interpreter prefix. The served checkout is host-owned: a tool that
  opens ledger.json, source, or a workspace canary outside its vendored
  tree receives ``PermissionError``, and writes there do not land.
  Declared stdin/stdout behavior still runs.
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
import hmac
import json
import os
import queue
import select
import socket
import subprocess
import sys
import threading
import uuid
from collections import OrderedDict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

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
from blackhole_agent.invocation_admission import (
    ADMISSION,
    MAX_INFLIGHT_ENV,
    AdmissionLimited,
)
from blackhole_agent.invocation_history import (
    load_capability_stats,
    monotonic_ms,
    plan_evidence,
    rank_programs,
    record_invocation,
)
from blackhole_agent.process_capture import (
    MAX_OUTPUT_BYTES_ENV,
    OutputLimitExceeded,
    ProcessCancelled,
    ResourceLimits,
    configure_max_output_bytes,
    current_max_output_bytes,
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
CLIENT_DISCONNECTED_STATUS = 499
DISCONNECT_POLL_SECONDS = 0.05
# When several minimal programs cover a goal, the planner enumerates at most
# this many of them and ranks by recorded invocation evidence (failures,
# then mean duration), keeping selection bounded and deterministic.
SOLVE_PLAN_CANDIDATES = 8
# Self-healing solves re-prove at most this many quarantined blockers per
# request: supervised re-proof re-executes frozen cases for real, so the
# healing budget is bounded like every other governed execution.
SOLVE_MAX_HEALED = 4
# A failing planned step falls back to the next-ranked viable program for
# the remaining goal; the fallback budget is bounded like the healing one
# and a capability is never retried within one request.
SOLVE_MAX_FALLBACKS = 4
MAX_BODY_BYTES = 1 << 20
INVOCATION_TOKEN_ENV = "BLACKHOLE_INVOCATION_TOKEN"
WWW_AUTHENTICATE = 'Bearer realm="blackhole-invocation-plane"'
MCP_HTTP_PATH = "/mcp"
MAX_MCP_HTTP_SESSIONS = 1024
SOLVE_PREVIEW_PREFER = "solve=preview"
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


def resolve_invocation_token(explicit: str | None = None) -> str:
    """Return the operator bearer token from ``--token`` or the process env."""

    if explicit is not None:
        return str(explicit).strip()
    return str(os.environ.get(INVOCATION_TOKEN_ENV, "") or "").strip()


def parse_bearer_token(header: str | None) -> str | None:
    """Return the offered bearer token, or None when the header is not Bearer."""

    if not header:
        return None
    scheme, separator, rest = header.strip().partition(" ")
    if separator != " " or scheme.lower() != "bearer":
        return None
    offered = rest.strip()
    return offered or None


def bearer_token_matches(offered: str, expected: str) -> bool:
    """Constant-time compare of utf-8 bearer tokens."""

    return hmac.compare_digest(offered.encode("utf-8"), expected.encode("utf-8"))


def parse_solve_dry_run(value: Any) -> bool:
    """Return the dry-run flag; non-boolean values are refused fail-closed."""

    if value is None:
        return False
    if isinstance(value, bool):
        return value
    raise InvocationError(422, "dry_run must be a boolean when present")


def prefer_solve_preview(header: str | None) -> bool:
    """True when a Prefer header requests ``solve=preview``."""

    if not header:
        return False
    for part in str(header).split(","):
        token = part.strip().split(";", 1)[0].strip().lower()
        if token == SOLVE_PREVIEW_PREFER:
            return True
    return False


def resolve_solve_dry_run(body: Mapping[str, Any] | None, prefer_header: str | None) -> bool:
    """Preview when the JSON flag or Prefer: solve=preview is set."""

    flagged = parse_solve_dry_run((body or {}).get("dry_run"))
    return flagged or prefer_solve_preview(prefer_header)


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


def _sandbox_roots(root: Path, tool_root: Path) -> list[Path]:
    """Allow the vendored tree; never the served checkout.

    The capture layer still adds a per-invocation scratch directory and the
    interpreter prefix. The workspace root used to be on this allowlist, so
    a live POST /invoke could rewrite ledger.json or plant files beside
    source. That path is now host-owned: untrusted tools cannot read or
    write it even when they are given the absolute path as input.
    """

    workspace = Path(root).resolve()
    vendored = Path(tool_root).resolve()
    if vendored == workspace:
        raise ValueError("vendored tool tree must not be the served checkout root")
    return [vendored]


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
    *,
    root: Path,
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
            sandbox_roots=_sandbox_roots(root, tool_root),
            max_output_bytes=current_max_output_bytes(),
        )
    except OutputLimitExceeded as exc:
        return {"ok": False, "error": str(exc), "violation": exc.payload()}
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
        _run_governed_case(
            Path(item["tool_root"]), manifest["command"], case, limits, timeout, root=root
        )
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
    output_listener: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Execute one proved absorbed capability against its vendored tree.

    When ``cancel_event`` is given and becomes set while the tool runs, the
    tool's owned process tree is terminated and :class:`ProcessCancelled`
    propagates to the caller (goal sessions use this for ``DELETE``).
    When ``output_listener`` is given, each captured stdout/stderr chunk is
    delivered as ``output_listener(stream, text)`` while the tool still runs.
    """

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
    started_ms = monotonic_ms()

    def record(ok: bool, error: str | None = None) -> None:
        record_invocation(
            root, capability_id, duration_ms=monotonic_ms() - started_ms, ok=ok, error=error
        )

    try:
        with ADMISSION.slot():
            completed = run_captured_process(
                command,
                cwd=Path(item["tool_root"]),
                timeout=timeout,
                input=json.dumps(provided_input),
                env=_tool_env(),
                resource_limits=limits,
                cancel_event=cancel_event,
                sandbox_roots=_sandbox_roots(root, Path(item["tool_root"])),
                max_output_bytes=current_max_output_bytes(),
                on_output=output_listener,
            )
    except AdmissionLimited as exc:
        record(False, "admission_limited")
        raise InvocationError(
            429,
            str(exc),
            extra=exc.payload(),
        ) from exc
    except OutputLimitExceeded as exc:
        record(False, "output_limited")
        raise InvocationError(
            502,
            str(exc),
            extra=exc.payload(),
        ) from exc
    except ProcessCancelled:
        raise
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        record(False, f"{type(exc).__name__}: {exc}")
        raise InvocationError(502, f"tool execution failed: {type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        violation = detect_resource_violation(completed, limits)
        if violation is not None:
            record(False, violation["reason"])
            record_resource_quarantine(root, capability_id, violation)
            raise InvocationError(
                502,
                f"tool violated the enforced resource limits: {violation['reason']}",
                extra={"violation": "resource_limit", "resource": violation, "quarantined": True},
            )
        stderr = (completed.stderr or "").strip().splitlines()
        detail = stderr[0] if stderr else "no stderr"
        record(False, f"exited {completed.returncode}: {detail}")
        raise InvocationError(502, f"tool exited {completed.returncode}: {detail}")
    try:
        fragment = json.loads(completed.stdout or "")
    except json.JSONDecodeError as exc:
        record(False, "stdout is not a JSON fragment")
        raise InvocationError(502, f"tool stdout is not a JSON fragment: {exc}") from exc
    if not isinstance(fragment, dict):
        record(False, "stdout is not a JSON object")
        raise InvocationError(502, "tool stdout must be a JSON object")
    missing_provides = [key for key in item["provides"] if key not in fragment]
    if missing_provides:
        record(False, f"missing provides keys: {missing_provides}")
        raise InvocationError(502, f"tool output missing provides keys: {missing_provides}")
    output = {key: fragment[key] for key in item["provides"]}
    record(True)
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
                max_output_bytes=current_max_output_bytes(),
            )
        except OutputLimitExceeded as exc:
            return subprocess.CompletedProcess(argv, 125, "", str(exc))
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


def plan_goal_programs(
    invocable: Mapping[str, Mapping[str, Any]],
    initial_keys: set[str],
    goal_keys: Sequence[str],
    *,
    max_steps: int = SOLVE_MAX_STEPS,
    max_candidates: int = SOLVE_PLAN_CANDIDATES,
) -> list[list[str]] | None:
    """Enumerate up to ``max_candidates`` minimal-length programs for a goal.

    Same BFS as :func:`plan_goal_program`, but instead of stopping at the
    first covering program it collects every covering program at the
    shallowest depth (up to the cap), in deterministic lexicographic order.
    The caller ranks these candidates; with one candidate the choice is the
    same program the single-plan BFS would return. Returns ``None`` when no
    program exists — an honest unsolvable, never a fabricated sequence.
    """

    goal = set(goal_keys)
    start = frozenset(initial_keys)
    if goal <= start:
        return []
    queue: deque[tuple[frozenset[str], tuple[str, ...]]] = deque([(start, ())])
    visited = {start}
    found: list[list[str]] = []
    found_depth: int | None = None
    while queue:
        available, program = queue.popleft()
        if found_depth is not None and len(program) >= found_depth:
            break
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
                found_depth = len(new_program)
                found.append(list(new_program))
                if len(found) >= max_candidates:
                    return found
                continue
            if new_available not in visited:
                visited.add(new_available)
                queue.append((new_available, new_program))
    return found or None


def heal_quarantined_blockers(
    root: Path,
    invocable: Mapping[str, Mapping[str, Any]],
    program: Sequence[str],
    *,
    timeout: int = INVOKE_TIMEOUT_SECONDS,
    attempted: set[str] | None = None,
    max_healed: int = SOLVE_MAX_HEALED,
) -> list[dict[str, Any]]:
    """Re-proof the quarantined members of ``program`` under governed frozen-case execution.

    Shared by one-shot solves and durable sessions: each quarantined blocker
    goes through the same supervised re-proof ``POST /reproof`` performs.
    ``attempted`` carries ids already tried within the request/session so a
    capability is never healed twice on one goal, and the total attempt count
    stays bounded by ``max_healed``. Every attempt is returned with its case
    verdicts, reinstated or not.
    """

    tried = attempted if attempted is not None else set()
    budget = max_healed - len(tried)
    blockers = [
        capability_id
        for capability_id in dict.fromkeys(program)
        if isinstance(invocable.get(capability_id), Mapping)
        and invocable[capability_id].get("quarantine")
        and capability_id not in tried
    ]
    healing: list[dict[str, Any]] = []
    for capability_id in blockers[: max(budget, 0)]:
        tried.add(capability_id)
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
    return healing


def _preview_solve_result(
    initial_state: Mapping[str, Any],
    goal_keys: list[str],
    program: list[str] | None,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    """Side-effect-free solve verdict: the plan that would run, no subprocess."""

    if program is None:
        result: dict[str, Any] = {
            "ok": True,
            "solved": False,
            "dry_run": True,
            "goal": goal_keys,
            "plan": None,
            "steps": [],
            "reason": "no proved capability program covers the goal",
        }
        if evidence is not None:
            result["plan_evidence"] = evidence
        return result
    result = {
        "ok": True,
        "solved": True,
        "dry_run": True,
        "goal": goal_keys,
        "plan": list(program),
        "steps": [],
        "plan_digest": _digest(
            {
                "initial_state": dict(initial_state),
                "goal": goal_keys,
                "plan": list(program),
                "dry_run": True,
            }
        ),
    }
    if evidence is not None:
        result["plan_evidence"] = evidence
    if not program:
        result["outcome"] = {key: initial_state[key] for key in goal_keys}
    return result


def solve_goal_request(
    root: Path,
    initial_state: Any,
    goal: Any,
    *,
    timeout: int = INVOKE_TIMEOUT_SECONDS,
    max_steps: int = SOLVE_MAX_STEPS,
    cancel_event: threading.Event | None = None,
    step_observer: Any = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Derive and execute a capability program for a declarative goal.

    The request names no capability: the planner derives minimal candidate
    programs from the served ledger's ``requires``/``provides`` contracts and
    ranks them by the workspace's recorded invocation evidence (fewest
    recorded failures, then lowest recorded mean duration, then deterministic
    order — degenerating to plain lexicographic order when no evidence
    exists). The chosen program executes for real through
    :func:`invoke_capability` with state threaded from step outputs into
    downstream inputs, and the response's ``plan_evidence`` trace records
    every considered candidate with the measured stats that decided.
    Unsolvable goals return an honest ``solved: false`` verdict without
    spawning a subprocess; malformed requests are refused before planning.

    Quarantined capabilities are excluded from planning. When the only
    program for a goal runs through quarantined steps, the solve heals
    instead of failing: each quarantined blocker (at most
    :data:`SOLVE_MAX_HEALED`) is re-proved inline through supervised
    governed re-execution of its frozen absorption cases — the same
    re-proof ``POST /reproof`` performs — and the goal is replanned against
    the reloaded ledger. A capability quarantined *mid-execution* (a
    concurrent violation, or one attributed to the running step) is healed
    the same way and the remaining goal is replanned from the threaded
    state. The response's ``healing`` trace records every attempt with its
    case verdicts; a blocker whose cases genuinely fail keeps its
    quarantine and yields an honest ``solved: false`` naming it. A step
    that fails mid-execution with an ordinary tool error (or an unhealable
    quarantine while alternatives remain) falls back within the same
    request: the remaining goal is replanned evidence-ranked over the
    healthy pool minus the failed capabilities, and the response's
    ``fallbacks`` trace records each failed step and the program that
    replaced it. A capability is never retried within one request, and the
    fallback budget is bounded by :data:`SOLVE_MAX_FALLBACKS`.

    ``cancel_event`` terminates the in-flight step's owned process tree
    (``ProcessCancelled`` propagates). ``step_observer(index, total,
    capability_id)`` is invoked after each completed step so streaming
    transports (the MCP capability server) can report per-step progress.

    ``dry_run`` returns the evidence-ranked program without executing,
    healing, or falling back: no owned tool tree starts. Unsolvable
    previews stay ``solved: false``; a covering program is ``solved: true``
    with ``dry_run: true`` and empty ``steps``.
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
    attempted: set[str] = set()

    def healthy_subset(pool: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        return {cid: item for cid, item in pool.items() if not item.get("quarantine")}

    def evidence_ranked_plan(
        pool: Mapping[str, Mapping[str, Any]], state_keys: set[str], goals: list[str]
    ) -> tuple[list[str] | None, dict[str, Any] | None]:
        """Pick the best minimal program by recorded invocation evidence.

        Several proved programs often cover the same goal; a purely syntactic
        planner cannot tell a route that fails every third run from one that
        never has. Candidates are ranked by the workspace's invocation
        journal (fewest recorded failures, then lowest recorded mean
        duration, then deterministic order); with no journal the choice
        degenerates to the previous lexicographic order.
        """

        candidates = plan_goal_programs(pool, state_keys, goals, max_steps=max_steps)
        if not candidates:
            return (None, None) if candidates is None else ([], None)
        stats = load_capability_stats(root)
        ranked = rank_programs(candidates, stats)
        return ranked[0], plan_evidence(ranked, stats, selected=ranked[0])

    healthy = healthy_subset(invocable)
    program, evidence = evidence_ranked_plan(healthy, set(initial_state), goal_keys)
    if program is None and not dry_run:
        # No healthy program. When a program exists only through quarantined
        # capabilities, heal instead of giving up: re-prove exactly the
        # quarantined blockers under governed re-execution of their frozen
        # cases, then replan against the reloaded ledger.
        blocked_program = plan_goal_program(
            invocable, set(initial_state), goal_keys, max_steps=max_steps
        )
        if blocked_program is not None:
            entries = heal_quarantined_blockers(
                root, invocable, blocked_program, timeout=timeout, attempted=attempted
            )
            healing.extend(entries)
            if any(entry["reinstated"] for entry in entries):
                invocable = load_invocable_capabilities(root)
                healthy = healthy_subset(invocable)
                program, evidence = evidence_ranked_plan(healthy, set(initial_state), goal_keys)
    if dry_run:
        return _preview_solve_result(initial_state, goal_keys, program, evidence)
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
    executed_program: list[str] = []
    fallbacks: list[dict[str, Any]] = []
    failed_steps: set[str] = set()
    remaining = list(program)
    while remaining:
        capability_id = remaining[0]
        item = invocable[capability_id]
        step_input = {key: state[key] for key in item["requires"]}
        try:
            result = invoke_capability(
                root, capability_id, step_input, timeout=timeout, cancel_event=cancel_event
            )
        except InvocationError as exc:
            violation = (exc.extra or {}).get("violation")
            # Mid-execution quarantine (a concurrent request's violation, or a
            # violation attributed to this step): heal once, then replan the
            # remaining goal evidence-ranked from the threaded state.
            if (
                violation in {"resource_quarantined", "resource_limit"}
                and capability_id not in attempted
                and len(attempted) < SOLVE_MAX_HEALED
            ):
                # The quarantine was recorded after this request's planning
                # snapshot; reload so the healer can see it.
                invocable = load_invocable_capabilities(root)
                entries = heal_quarantined_blockers(
                    root, invocable, [capability_id], timeout=timeout, attempted=attempted
                )
                healing.extend(entries)
                if entries and entries[-1]["reinstated"]:
                    invocable = load_invocable_capabilities(root)
                    replanned, replanned_evidence = evidence_ranked_plan(
                        healthy_subset(invocable),
                        set(state),
                        [key for key in goal_keys if key not in state],
                    )
                    if replanned is not None:
                        if replanned_evidence is not None:
                            evidence = replanned_evidence
                        remaining = replanned
                        continue
            # Ordinary mid-execution failure (or an unhealable quarantine
            # with alternatives left): the failed step's provides never
            # entered the threaded state, so fall back to the next-ranked
            # viable program for the remaining goal instead of dying.
            if capability_id in failed_steps or len(fallbacks) >= SOLVE_MAX_FALLBACKS:
                raise
            failed_steps.add(capability_id)
            invocable = load_invocable_capabilities(root)
            pool = {
                cid: candidate
                for cid, candidate in healthy_subset(invocable).items()
                if cid not in failed_steps
            }
            replanned, replanned_evidence = evidence_ranked_plan(
                pool, set(state), [key for key in goal_keys if key not in state]
            )
            if replanned is None:
                raise
            fallbacks.append(
                {
                    "capability_id": capability_id,
                    "error": exc.error,
                    "replaced_by": list(replanned),
                }
            )
            if replanned_evidence is not None:
                evidence = replanned_evidence
            remaining = replanned
            continue
        state.update(result["output"])
        executed_program.append(capability_id)
        remaining.pop(0)
        steps.append(
            {
                "capability_id": capability_id,
                "input": step_input,
                "output": result["output"],
                "response_digest": result["response_digest"],
            }
        )
        if step_observer is not None:
            step_observer(len(steps), len(steps) + len(remaining), capability_id)
    outcome = {key: state[key] for key in goal_keys}
    return {
        "ok": True,
        "solved": True,
        "goal": goal_keys,
        "plan": executed_program,
        "steps": steps,
        "outcome": outcome,
        "healing": healing,
        "fallbacks": fallbacks,
        "plan_evidence": evidence,
        "plan_digest": _digest(
            {
                "initial_state": initial_state,
                "goal": goal_keys,
                "plan": executed_program,
                "steps": [
                    {"capability_id": step["capability_id"], "response_digest": step["response_digest"]}
                    for step in steps
                ],
                "outcome": outcome,
            }
        ),
    }


def http_client_disconnected(sock: socket.socket | None) -> bool:
    """True when the HTTP peer has closed or reset the request socket."""

    if sock is None:
        return True
    try:
        readable, _, errored = select.select([sock], [], [sock], 0)
    except (OSError, ValueError, TypeError):
        return True
    if errored:
        return True
    if not readable:
        return False
    try:
        peeked = sock.recv(1, socket.MSG_PEEK)
    except BlockingIOError:
        return False
    except (ConnectionResetError, ConnectionAbortedError, ConnectionRefusedError, OSError):
        return True
    return peeked == b""


def arm_http_disconnect_cancel(
    handler: BaseHTTPRequestHandler,
) -> tuple[threading.Event, Callable[[], None]]:
    """Cancel an in-flight tool tree when the HTTP client hangs up.

    Returns ``(cancel_event, stop)``. ``stop`` must run after the invocation
    returns so the watcher thread does not outlive the request.
    """

    cancel_event = threading.Event()
    stop_watch = threading.Event()
    sock = getattr(handler, "connection", None)

    def watch() -> None:
        while not stop_watch.wait(DISCONNECT_POLL_SECONDS):
            if http_client_disconnected(sock):
                cancel_event.set()
                return

    threading.Thread(target=watch, daemon=True, name="bh-http-disconnect").start()

    def stop() -> None:
        stop_watch.set()

    return cancel_event, stop


def _write_cancelled(handler: BaseHTTPRequestHandler) -> None:
    try:
        _json_response(
            handler,
            CLIENT_DISCONNECTED_STATUS,
            {
                "ok": False,
                "cancelled": True,
                "error": "invocation cancelled because the HTTP client disconnected",
            },
        )
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError, TimeoutError):
        return


def _drain_request_body(handler: BaseHTTPRequestHandler, *, limit: int = MAX_BODY_BYTES) -> None:
    """Consume a POST body so a fail-closed reply does not RST the client."""

    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        return
    if length <= 0:
        return
    remaining = min(length, limit)
    while remaining > 0:
        chunk = handler.rfile.read(min(remaining, 65536))
        if not chunk:
            return
        remaining -= len(chunk)


def _mcp_http_path(path: str) -> bool:
    return path.split("?", 1)[0].rstrip("/") == MCP_HTTP_PATH


def _encode_mcp_sse(payload: Mapping[str, Any]) -> bytes:
    data = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=True)
    return f"event: message\ndata: {data}\n\n".encode("utf-8")


def _encode_session_sse(payload: Mapping[str, Any]) -> bytes:
    data = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=True)
    return f"event: session\ndata: {data}\n\n".encode("utf-8")


def _encode_invoke_sse(event: str, payload: Mapping[str, Any]) -> bytes:
    data = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=True)
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


def _wants_live_invoke_stream(handler: BaseHTTPRequestHandler) -> bool:
    accept = (handler.headers.get("Accept") or "").lower()
    return "text/event-stream" in accept and "application/json" not in accept


def _stream_live_invoke(
    handler: BaseHTTPRequestHandler,
    root: Path,
    body: Mapping[str, Any],
    cancel_event: threading.Event | None,
) -> None:
    """POST /invoke reverse channel: output events while the tree still runs."""

    try:
        handler.close_connection = True
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.flush()
    except OSError:
        if cancel_event is not None:
            cancel_event.set()
        return

    def emit(event: str, payload: Mapping[str, Any]) -> bool:
        try:
            handler.wfile.write(_encode_invoke_sse(event, payload))
            handler.wfile.flush()
            return True
        except OSError:
            if cancel_event is not None:
                cancel_event.set()
            return False

    def listener(stream: str, text: str) -> None:
        emit("output", {"stream": stream, "text": text})

    if not emit("started", {"capability_id": body.get("capability_id")}):
        return
    try:
        result = invoke_capability(
            root,
            body.get("capability_id"),
            body.get("input"),
            cancel_event=cancel_event,
            output_listener=listener,
        )
    except ProcessCancelled:
        emit("error", {"ok": False, "cancelled": True, "error": "cancelled"})
        return
    except InvocationError as exc:
        payload = {"ok": False, "error": exc.error, **exc.extra}
        emit("error", payload)
        return
    emit("result", result)


def _write_mcp_rpc(
    handler: BaseHTTPRequestHandler,
    payload: Mapping[str, Any],
    *,
    status: int = 200,
    session: str = "",
) -> None:
    accept = (handler.headers.get("Accept") or "").lower()
    prefer_sse = "text/event-stream" in accept and "application/json" not in accept
    if prefer_sse:
        body = _encode_mcp_sse(payload)
        content_type = "text/event-stream"
    else:
        body = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        content_type = "application/json"
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    if session:
        handler.send_header("Mcp-Session-Id", session)
    handler.end_headers()
    handler.wfile.write(body)


def _write_mcp_accepted(handler: BaseHTTPRequestHandler, *, session: str = "") -> None:
    handler.send_response(202)
    handler.send_header("Content-Length", "0")
    if session:
        handler.send_header("Mcp-Session-Id", session)
    handler.end_headers()


def _admission_retry_headers(status: int, payload: Mapping[str, Any]) -> dict[str, str] | None:
    if status != 429:
        return None
    retry = payload.get("retry_after", 1)
    return {"Retry-After": str(retry)}


def _invocation_error_response(handler: BaseHTTPRequestHandler, exc: InvocationError) -> None:
    payload = {"ok": False, "error": exc.error, **exc.extra}
    _json_response(handler, exc.status, payload, headers=_admission_retry_headers(exc.status, payload))


def _json_response(
    handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any],
    *, replayed: bool | None = None, headers: Mapping[str, str] | None = None,
) -> None:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if replayed is not None:
        handler.send_header("Idempotency-Replayed", "true" if replayed else "false")
    if headers:
        for key, value in headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def build_server(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    token: str | None = None,
) -> ThreadingHTTPServer:
    """Bind the invocation plane; port 0 selects an ephemeral port."""

    service_root = Path(root).resolve()
    invocation_token = resolve_invocation_token(token)
    from blackhole_agent.capability_sessions import TERMINAL_STATUSES, SessionManager
    from blackhole_agent.invocation_receipts import (
        InvocationReceipts,
        ReceiptError,
        request_digest,
        solve_request_digest,
    )

    sessions = SessionManager(service_root)
    sessions.recover()
    receipts = InvocationReceipts(service_root)
    from blackhole_agent.mcp_capability_server import (
        CapabilityCatalog,
        CatalogChangeWatcher,
        McpHttpSession,
        handle_http_rpc,
    )

    mcp_catalog = CapabilityCatalog(service_root)
    mcp_sessions: OrderedDict[str, McpHttpSession] = OrderedDict()
    mcp_session_lock = threading.Lock()

    def _mint_mcp_session() -> str:
        token = uuid.uuid4().hex
        state = McpHttpSession()
        evicted: list[McpHttpSession] = []
        with mcp_session_lock:
            while len(mcp_sessions) >= MAX_MCP_HTTP_SESSIONS:
                _, old = mcp_sessions.popitem(last=False)
                evicted.append(old)
            mcp_sessions[token] = state
        for old in evicted:
            old.close()
        return token

    def _touch_mcp_session(token: str) -> McpHttpSession | None:
        with mcp_session_lock:
            state = mcp_sessions.get(token)
            if state is None:
                return None
            mcp_sessions.move_to_end(token)
            return state

    def _drop_mcp_session(token: str) -> bool:
        with mcp_session_lock:
            state = mcp_sessions.pop(token, None)
        if state is None:
            return False
        state.close()
        return True

    def _broadcast_catalog_change(payload: Mapping[str, Any]) -> None:
        with mcp_session_lock:
            states = list(mcp_sessions.values())
        for state in states:
            state.publish(payload)

    catalog_watcher = CatalogChangeWatcher(mcp_catalog, _broadcast_catalog_change)
    catalog_watcher.start()

    class CapabilityHandler(BaseHTTPRequestHandler):
        server_version = "blackhole-capability-service/1"
        disable_nagle_algorithm = True
        wbufsize = 0

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

        def _session_events_id(self) -> str | None:
            path = self.path.split("?", 1)[0]
            prefix = "/sessions/"
            suffix = "/events"
            if not path.startswith(prefix) or not path.endswith(suffix):
                return None
            rest = path[len(prefix) : -len(suffix)]
            if rest and "/" not in rest:
                return rest
            return None

        def _authorize(self) -> bool:
            if not invocation_token:
                return True
            offered = parse_bearer_token(self.headers.get("Authorization"))
            if offered is None:
                if self.command in {"POST", "DELETE", "PUT", "PATCH"}:
                    _drain_request_body(self)
                _json_response(
                    self,
                    401,
                    {"ok": False, "error": "authorization_required"},
                    headers={"WWW-Authenticate": WWW_AUTHENTICATE},
                )
                return False
            if not bearer_token_matches(offered, invocation_token):
                if self.command in {"POST", "DELETE", "PUT", "PATCH"}:
                    _drain_request_body(self)
                _json_response(self, 403, {"ok": False, "error": "authorization_rejected"})
                return False
            return True

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
                snapshot = ADMISSION.snapshot()
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "schema_version": SCHEMA_VERSION,
                        "inflight": snapshot["inflight"],
                        "max_inflight": snapshot["max_inflight"],
                        "max_output_bytes": current_max_output_bytes(),
                        "live_invoke_stream": True,
                        "mcp_tools_list_changed": True,
                        "solve_idempotency": True,
                        "mcp_call_idempotency": True,
                        "solve_plan_preview": True,
                    },
                )
                return
            if not self._authorize():
                return
            if _mcp_http_path(path):
                offered = str(self.headers.get("Mcp-Session-Id") or "").strip()
                state = _touch_mcp_session(offered) if offered else None
                if not offered or state is None:
                    _json_response(self, 404, {"ok": False, "error": "mcp_session_unknown"})
                    return
                accept = (self.headers.get("Accept") or "").lower()
                if "text/event-stream" not in accept:
                    _json_response(
                        self,
                        406,
                        {"ok": False, "error": "mcp_get_requires_event_stream"},
                    )
                    return
                listener = state.subscribe()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Mcp-Session-Id", offered)
                    self.end_headers()
                    try:
                        self.wfile.flush()
                    except OSError:
                        return
                    sock = getattr(self, "connection", None)
                    while not state.closed:
                        if http_client_disconnected(sock):
                            break
                        try:
                            item = listener.get(timeout=DISCONNECT_POLL_SECONDS)
                        except queue.Empty:
                            continue
                        if item is None:
                            break
                        try:
                            self.wfile.write(_encode_mcp_sse(item))
                            self.wfile.flush()
                        except OSError:
                            break
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    return
                finally:
                    state.unsubscribe(listener)
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
            events_id = self._session_events_id()
            if events_id is not None:
                try:
                    sessions.get_session(events_id)
                except InvocationError as exc:
                    _json_response(self, exc.status, {"ok": False, "error": exc.error, **exc.extra})
                    return
                accept = (self.headers.get("Accept") or "").lower()
                if "text/event-stream" not in accept:
                    _json_response(
                        self,
                        406,
                        {"ok": False, "error": "session_get_events_requires_event_stream"},
                    )
                    return
                listener = sessions.subscribe_events(events_id)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()
                    try:
                        self.wfile.flush()
                    except OSError:
                        return
                    sock = getattr(self, "connection", None)
                    while True:
                        if http_client_disconnected(sock):
                            break
                        try:
                            item = listener.get(timeout=DISCONNECT_POLL_SECONDS)
                        except queue.Empty:
                            continue
                        if item is None:
                            break
                        try:
                            self.wfile.write(_encode_session_sse(item))
                            self.wfile.flush()
                        except OSError:
                            break
                        if str(item.get("status") or "") in TERMINAL_STATUSES:
                            break
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    return
                finally:
                    sessions.unsubscribe_events(events_id, listener)
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
            if not self._authorize():
                return
            if _mcp_http_path(self.path):
                offered = str(self.headers.get("Mcp-Session-Id") or "").strip()
                if not offered or not _drop_mcp_session(offered):
                    _json_response(self, 404, {"ok": False, "error": "mcp_session_unknown"})
                    return
                _json_response(self, 200, {"ok": True, "closed": True})
                return
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
            if not self._authorize():
                return
            path = self.path.split("?", 1)[0]
            if _mcp_http_path(path):
                self._handle_mcp_post()
                return
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
                _drain_request_body(self)
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
                if path not in {"/invoke", "/solve"} or len(keys) != 1:
                    _json_response(self, 400, {
                        "ok": False,
                        "error": "one Idempotency-Key is supported only on POST /invoke and POST /solve",
                    })
                    return
            dry_run = False
            if path == "/solve":
                try:
                    dry_run = resolve_solve_dry_run(body, self.headers.get("Prefer"))
                except InvocationError as exc:
                    _json_response(self, exc.status, {"ok": False, "error": exc.error, **exc.extra})
                    return

            cancel_event: threading.Event | None = None
            stop_watch: Callable[[], None] | None = None
            if path in {"/invoke", "/solve"} and not dry_run:
                cancel_event, stop_watch = arm_http_disconnect_cancel(self)
            try:
                if keys:
                    def operation() -> tuple[int, dict[str, Any]]:
                        try:
                            if path == "/solve":
                                return 200, solve_goal_request(
                                    service_root,
                                    body.get("initial_state"),
                                    body.get("goal"),
                                    cancel_event=cancel_event,
                                    dry_run=dry_run,
                                )
                            return 200, invoke_capability(
                                service_root,
                                body.get("capability_id"),
                                body.get("input"),
                                cancel_event=cancel_event,
                            )
                        except InvocationError as exc:
                            return exc.status, {"ok": False, "error": exc.error, **exc.extra}

                    digest = (
                        solve_request_digest(
                            body.get("initial_state"), body.get("goal"), dry_run=dry_run
                        )
                        if path == "/solve"
                        else request_digest(body.get("capability_id"), body.get("input"))
                    )
                    try:
                        status, result, replayed = receipts.execute_digest(
                            keys[0], digest, operation
                        )
                    except ReceiptError as exc:
                        _json_response(self, exc.status, exc.payload)
                        return
                    extra_headers = _admission_retry_headers(status, result) if isinstance(result, dict) else None
                    _json_response(self, status, result, replayed=replayed, headers=extra_headers)
                    return
                if path == "/invoke" and _wants_live_invoke_stream(self):
                    _stream_live_invoke(self, service_root, body, cancel_event)
                    return
                try:
                    if path == "/contract":
                        result = evaluate_contract_request(service_root, body.get("done_when"))
                    elif path == "/solve":
                        result = solve_goal_request(
                            service_root,
                            body.get("initial_state"),
                            body.get("goal"),
                            cancel_event=cancel_event,
                            dry_run=dry_run,
                        )
                    elif path == "/reproof":
                        result = reproof_capability(service_root, body.get("capability_id"))
                    elif path == "/sessions":
                        result = sessions.create_session(
                            body.get("initial_state"),
                            body.get("goal"),
                            notify_url=body.get("notify_url"),
                            notify_secret=body.get("notify_secret"),
                        )
                    elif session_action == "input":
                        result = sessions.supply_input(session_id, body.get("input"))
                    elif session_action == "resume":
                        result = sessions.resume_session(session_id)
                    else:
                        result = invoke_capability(
                            service_root,
                            body.get("capability_id"),
                            body.get("input"),
                            cancel_event=cancel_event,
                        )
                except InvocationError as exc:
                    _invocation_error_response(self, exc)
                    return
                except ProcessCancelled:
                    _write_cancelled(self)
                    return
                _json_response(self, 200, result)
            except ProcessCancelled:
                _write_cancelled(self)
            finally:
                if stop_watch is not None:
                    stop_watch()

        def _handle_mcp_post(self) -> None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                _json_response(self, 400, {"ok": False, "error": "invalid Content-Length"})
                return
            if length <= 0 or length > MAX_BODY_BYTES:
                _json_response(self, 400, {"ok": False, "error": "missing or oversized body"})
                return
            raw = self.rfile.read(length)
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _write_mcp_rpc(
                    self,
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}},
                    status=400,
                )
                return
            if not isinstance(message, dict):
                _write_mcp_rpc(
                    self,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "invalid request"},
                    },
                    status=400,
                )
                return
            method = str(message.get("method") or "")
            offered = str(self.headers.get("Mcp-Session-Id") or "").strip()
            session = offered
            session_state = None
            if method == "initialize":
                session = _mint_mcp_session()
                session_state = _touch_mcp_session(session)
            else:
                session_state = _touch_mcp_session(offered) if offered else None
                if session_state is None:
                    _json_response(self, 404, {"ok": False, "error": "mcp_session_unknown"})
                    return
            cancel_event, stop_watch = arm_http_disconnect_cancel(self)
            try:
                try:
                    response = handle_http_rpc(
                        mcp_catalog,
                        message,
                        cancel_event=cancel_event,
                        session=session_state,
                    )
                except ProcessCancelled:
                    _write_cancelled(self)
                    return
                if response is None:
                    _write_mcp_accepted(self, session=session)
                    return
                _write_mcp_rpc(self, response, session=session)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return
            finally:
                stop_watch()

    server = ThreadingHTTPServer((host, port), CapabilityHandler)
    server.daemon_threads = True
    original_close = server.server_close

    def _close_with_watcher() -> None:
        catalog_watcher.stop()
        original_close()

    server.server_close = _close_with_watcher  # type: ignore[method-assign]
    return server


def serve(
    root: Path,
    *,
    port: int = 0,
    host: str = "127.0.0.1",
    token: str | None = None,
    max_inflight: int | None = None,
    max_output_bytes: int | None = None,
) -> int:
    """Run the invocation plane until interrupted; prints a readiness line."""

    if max_inflight is not None:
        ADMISSION.configure(max_inflight)
    configure_max_output_bytes(max_output_bytes)
    invocation_token = resolve_invocation_token(token)
    server = build_server(root, host=host, port=port, token=invocation_token)
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    listing = capability_listing(Path(root).resolve())
    print(
        json.dumps(
            {
                "listening": bound_port,
                "host": bound_host,
                "invocable_count": listing["count"],
                "listing_digest": listing["listing_digest"],
                "auth_required": bool(invocation_token),
                "mcp_path": MCP_HTTP_PATH,
                "max_inflight": ADMISSION.max_inflight(),
                "max_output_bytes": current_max_output_bytes(),
                "mcp_tools_list_changed": True,
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
    headers: Mapping[str, str] | None = None,
) -> tuple[int, Any]:
    status, body, _hdrs = _http_request_ex(
        method, url, payload, timeout=timeout, headers=headers
    )
    return status, body


def _http_request_ex(
    method: str,
    url: str,
    payload: Mapping[str, Any] | None = None,
    *,
    timeout: int = 30,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, Any, dict[str, str]]:
    from urllib import request as urlrequest
    from urllib.error import HTTPError, URLError

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            captured = {key.lower(): value for key, value in response.headers.items()}
            raw = response.read().decode("utf-8")
            try:
                parsed: Any = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            return response.status, parsed, captured
    except HTTPError as exc:
        captured = {key.lower(): value for key, value in (exc.headers.items() if exc.headers else [])}
        try:
            return exc.code, json.loads(exc.read().decode("utf-8")), captured
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return exc.code, None, captured
    except (URLError, TimeoutError, OSError):
        return 0, None, {}


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
        status, health = _http_request("GET", f"{base}/health")
        checks["solve_plan_preview_health"] = (
            status == 200 and isinstance(health, dict) and health.get("solve_plan_preview") is True
        )
        status, preview = _http_request(
            "POST",
            f"{base}/solve",
            {
                "initial_state": {"raw_text": "blackhole"},
                "goal": ["reversed_text"],
                "dry_run": True,
            },
        )
        checks["solve_plan_preview"] = (
            status == 200
            and isinstance(preview, dict)
            and preview.get("solved") is True
            and preview.get("dry_run") is True
            and preview.get("plan") == [target_id]
            and preview.get("steps") == []
            and "outcome" not in preview
        )
        status, preview_header = _http_request(
            "POST",
            f"{base}/solve",
            {"initial_state": {"raw_text": "blackhole"}, "goal": ["reversed_text"]},
            headers={"Prefer": "solve=preview"},
        )
        checks["solve_plan_preview_prefer"] = (
            status == 200
            and isinstance(preview_header, dict)
            and preview_header.get("dry_run") is True
            and preview_header.get("plan") == [target_id]
            and preview_header.get("steps") == []
        )
        mcp_url = f"{base}{MCP_HTTP_PATH}"
        status, handshake, mcp_headers = _http_request_ex(
            "POST",
            mcp_url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "capability-service-proof", "version": "1"},
                },
            },
        )
        mcp_session = str(mcp_headers.get("mcp-session-id") or "")
        handshake_result = handshake.get("result") if isinstance(handshake, dict) else None
        checks["mcp_initialize"] = (
            status == 200
            and isinstance(handshake_result, dict)
            and bool(mcp_session)
            and "serverInfo" in handshake_result
        )
        mcp_hdr = {"Mcp-Session-Id": mcp_session} if mcp_session else None
        tool_names: list[str] = []
        cursor = ""
        list_status = 0
        for page_id in range(16):
            params: dict[str, Any] = {"cursor": cursor} if cursor else {}
            list_status, listed_rpc = _http_request(
                "POST",
                mcp_url,
                {"jsonrpc": "2.0", "id": 2 + page_id, "method": "tools/list", "params": params},
                headers=mcp_hdr,
            )
            page = listed_rpc.get("result") if isinstance(listed_rpc, dict) else None
            listed_tools = page.get("tools") if isinstance(page, dict) else None
            if isinstance(listed_tools, list):
                tool_names.extend(
                    str(item.get("name"))
                    for item in listed_tools
                    if isinstance(item, dict) and item.get("name")
                )
            cursor = str((page or {}).get("nextCursor") or "") if isinstance(page, dict) else ""
            if not cursor or "text-reverser" in tool_names:
                break
        checks["mcp_lists_reverser"] = list_status == 200 and "text-reverser" in tool_names
        probe_text = "mcp-http-plane"
        status, called = _http_request(
            "POST",
            mcp_url,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "text-reverser",
                    "arguments": {"raw_text": probe_text},
                },
            },
            headers=mcp_hdr,
        )
        call_result = called.get("result") if isinstance(called, dict) else None
        structured = (
            call_result.get("structuredContent") if isinstance(call_result, dict) else None
        )
        checks["mcp_tools_call_executes"] = (
            status == 200
            and isinstance(structured, dict)
            and structured.get("reversed_text") == probe_text[::-1]
            and call_result.get("isError") is False
        )
        detail["mcp_call"] = called
        status, unknown_tool = _http_request(
            "POST",
            mcp_url,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "not-a-real-tool", "arguments": {}},
            },
            headers=mcp_hdr,
        )
        unknown_error = unknown_tool.get("error") if isinstance(unknown_tool, dict) else None
        checks["mcp_unknown_tool_rpc"] = (
            status == 200
            and isinstance(unknown_error, dict)
            and unknown_error.get("code") == -32602
        )
        status, missing_session = _http_request(
            "POST",
            mcp_url,
            {"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}},
        )
        checks["mcp_session_required"] = (
            status == 404
            and isinstance(missing_session, dict)
            and missing_session.get("error") == "mcp_session_unknown"
        )
        status, solved_mcp = _http_request(
            "POST",
            mcp_url,
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "solve_goal",
                    "arguments": {
                        "initial_state": {"raw_text": probe_text},
                        "goal": ["reversed_text"],
                    },
                },
            },
            headers=mcp_hdr,
        )
        solve_structured = (
            (solved_mcp.get("result") or {}).get("structuredContent")
            if isinstance(solved_mcp, dict)
            else None
        )
        checks["mcp_solve_goal"] = (
            status == 200
            and isinstance(solve_structured, dict)
            and solve_structured.get("solved") is True
            and solve_structured.get("outcome", {}).get("reversed_text") == probe_text[::-1]
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
            "without spawning a subprocess. dry_run or Prefer: solve=preview "
            "returns that ranked program without executing untrusted tools. "
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
    serve_parser.add_argument(
        "--token",
        default=None,
        help="operator bearer token; defaults to BLACKHOLE_INVOCATION_TOKEN",
    )
    serve_parser.add_argument(
        "--max-inflight",
        type=int,
        default=None,
        help=f"cap concurrent untrusted tool trees; defaults to {MAX_INFLIGHT_ENV} or 8",
    )
    serve_parser.add_argument(
        "--max-output-bytes",
        type=int,
        default=None,
        help=(
            "cap captured untrusted-tool stdout/stderr bytes; defaults to "
            f"{MAX_OUTPUT_BYTES_ENV} or 1048576"
        ),
    )
    proof_parser = sub.add_parser("proof", help="run the hermetic invocation-plane proof")
    proof_parser.add_argument("--root", type=Path, default=REPO_ROOT)
    sub.add_parser("register", help="register the capability on the live ledger")
    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve(
            args.root,
            port=args.port,
            host=args.host,
            token=args.token,
            max_inflight=args.max_inflight,
            max_output_bytes=args.max_output_bytes,
        )
    if args.command == "proof":
        result = builtin_capability_service_proof(args.root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    capability = ensure_capability_service_capability()
    print(json.dumps({"registered": capability.id}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
