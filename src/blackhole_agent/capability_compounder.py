"""Durable capability compounding for Unbound missions.

Milestones are not paper trails. Each demonstrated behavior can become a
versioned, invocable capability that later turns list, prove, run, and compose
without consulting the legacy skill-route discovery labyrinth.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SCHEMA_VERSION = 1
DEFAULT_LEDGER_RELATIVE = Path("capabilities") / "ledger.json"
CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")
SUPPORTED_KINDS = frozenset({"command", "python"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def slugify_capability_id(value: str, *, limit: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        slug = "capability"
    if slug[0].isdigit():
        slug = f"cap-{slug}"
    return slug[:limit].rstrip("-")


@dataclass(frozen=True)
class Capability:
    """One durable, invocable local capability."""

    id: str
    name: str
    description: str
    kind: str
    entry: str
    proof_command: str
    dependencies: tuple[str, ...] = ()
    behavior_paths: tuple[str, ...] = ()
    capability_delta: str = ""
    tags: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    source_mission_id: str = ""
    source_milestone: int | None = None
    last_proved_at: str = ""
    last_proof_exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["dependencies"] = list(self.dependencies)
        payload["behavior_paths"] = list(self.behavior_paths)
        payload["tags"] = list(self.tags)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Capability":
        known = {item.name for item in fields(cls)}
        values: dict[str, Any] = {}
        for key in known:
            if key not in payload:
                continue
            value = payload[key]
            if key in {"dependencies", "behavior_paths", "tags"}:
                values[key] = tuple(str(item).strip() for item in (value or []) if str(item).strip())
            elif key == "source_milestone":
                if value is None or value == "":
                    values[key] = None
                else:
                    values[key] = int(value)
            elif key == "last_proof_exit_code":
                if value is None or value == "":
                    values[key] = None
                else:
                    values[key] = int(value)
            else:
                values[key] = str(value) if value is not None and key != "kind" else value
                if key in {
                    "id",
                    "name",
                    "description",
                    "kind",
                    "entry",
                    "proof_command",
                    "capability_delta",
                    "created_at",
                    "updated_at",
                    "source_mission_id",
                    "last_proved_at",
                }:
                    values[key] = "" if value is None else str(value)
        return cls(**values)


@dataclass
class CapabilityLedger:
    """Versioned registry of compounded capabilities."""

    schema_version: int = SCHEMA_VERSION
    updated_at: str = ""
    capabilities: dict[str, Capability] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "capabilities": {
                capability_id: capability.to_dict()
                for capability_id, capability in sorted(self.capabilities.items())
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapabilityLedger":
        raw_caps = payload.get("capabilities") or {}
        if not isinstance(raw_caps, Mapping):
            raise ValueError("capabilities must be an object")
        capabilities: dict[str, Capability] = {}
        for capability_id, raw in raw_caps.items():
            if not isinstance(raw, Mapping):
                continue
            capability = Capability.from_dict({**raw, "id": raw.get("id") or capability_id})
            capabilities[capability.id] = capability
        return cls(
            schema_version=int(payload.get("schema_version") or SCHEMA_VERSION),
            updated_at=str(payload.get("updated_at") or ""),
            capabilities=capabilities,
        )


@dataclass(frozen=True)
class CapabilityRunResult:
    capability_id: str
    ok: bool
    exit_code: int
    command: tuple[str, ...]
    stdout: str
    stderr: str
    kind: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "ok": self.ok,
            "exit_code": self.exit_code,
            "command": list(self.command),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "kind": self.kind,
            "summary": self.summary,
        }


def default_ledger_path(repo_path: Path) -> Path:
    return (repo_path / DEFAULT_LEDGER_RELATIVE).resolve()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_ledger(path: Path) -> CapabilityLedger:
    if not path.exists():
        return CapabilityLedger(updated_at=utc_now_iso())
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Capability ledger must be a JSON object: {path}")
    ledger = CapabilityLedger.from_dict(payload)
    if ledger.schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported capability ledger schema {ledger.schema_version}; expected {SCHEMA_VERSION}."
        )
    return ledger


def save_ledger(path: Path, ledger: CapabilityLedger) -> None:
    ledger.updated_at = utc_now_iso()
    atomic_write_json(path, ledger.to_dict())


def validate_capability(capability: Capability, *, existing: Mapping[str, Capability] | None = None) -> None:
    if not CAPABILITY_ID_PATTERN.match(capability.id):
        raise ValueError(
            f"Invalid capability id {capability.id!r}; expected lowercase token matching {CAPABILITY_ID_PATTERN.pattern}"
        )
    if capability.kind not in SUPPORTED_KINDS:
        raise ValueError(f"Unsupported capability kind {capability.kind!r}; expected one of {sorted(SUPPORTED_KINDS)}")
    if not capability.name.strip():
        raise ValueError("capability name is required")
    if not capability.entry.strip():
        raise ValueError("capability entry is required")
    if not capability.proof_command.strip():
        raise ValueError("capability proof_command is required")
    existing = existing or {}
    for dependency in capability.dependencies:
        if dependency == capability.id:
            raise ValueError(f"capability {capability.id} cannot depend on itself")
        if dependency not in existing and existing is not None:
            # Allow forward references only when the dependency exists in the ledger.
            # Callers pass the full ledger map for cycle-aware registration.
            if dependency not in existing:
                raise ValueError(f"capability {capability.id} depends on missing capability {dependency!r}")


def _detect_cycles(capabilities: Mapping[str, Capability]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: list[str] = []

    def walk(node: str, stack: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            cycles.append(" -> ".join([*stack, node]))
            return
        visiting.add(node)
        capability = capabilities.get(node)
        if capability is not None:
            for dependency in capability.dependencies:
                walk(dependency, [*stack, node])
        visiting.remove(node)
        visited.add(node)

    for capability_id in capabilities:
        walk(capability_id, [])
    return cycles


def register_capability(
    ledger: CapabilityLedger,
    capability: Capability,
    *,
    replace: bool = False,
) -> CapabilityLedger:
    """Insert or replace one capability and re-validate the graph."""

    if capability.id in ledger.capabilities and not replace:
        raise ValueError(f"Capability already exists: {capability.id}")
    now = utc_now_iso()
    previous = ledger.capabilities.get(capability.id)
    stamped = Capability(
        id=capability.id,
        name=capability.name,
        description=capability.description,
        kind=capability.kind,
        entry=capability.entry,
        proof_command=capability.proof_command,
        dependencies=capability.dependencies,
        behavior_paths=capability.behavior_paths,
        capability_delta=capability.capability_delta,
        tags=capability.tags,
        created_at=previous.created_at if previous and previous.created_at else (capability.created_at or now),
        updated_at=now,
        source_mission_id=capability.source_mission_id or (previous.source_mission_id if previous else ""),
        source_milestone=(
            capability.source_milestone
            if capability.source_milestone is not None
            else (previous.source_milestone if previous else None)
        ),
        last_proved_at=previous.last_proved_at if previous else capability.last_proved_at,
        last_proof_exit_code=previous.last_proof_exit_code if previous else capability.last_proof_exit_code,
    )
    candidate = dict(ledger.capabilities)
    candidate[stamped.id] = stamped
    # Validate dependencies against the candidate graph (missing deps fail).
    for item in candidate.values():
        for dependency in item.dependencies:
            if dependency not in candidate:
                raise ValueError(f"capability {item.id} depends on missing capability {dependency!r}")
            if dependency == item.id:
                raise ValueError(f"capability {item.id} cannot depend on itself")
    if stamped.kind not in SUPPORTED_KINDS:
        raise ValueError(f"Unsupported capability kind {stamped.kind!r}")
    if not CAPABILITY_ID_PATTERN.match(stamped.id):
        raise ValueError(f"Invalid capability id {stamped.id!r}")
    if not stamped.name.strip() or not stamped.entry.strip() or not stamped.proof_command.strip():
        raise ValueError("name, entry, and proof_command are required")
    cycles = _detect_cycles(candidate)
    if cycles:
        raise ValueError(f"capability dependency cycle detected: {cycles[0]}")
    ledger.capabilities = candidate
    ledger.updated_at = now
    return ledger


def remove_capability(ledger: CapabilityLedger, capability_id: str) -> CapabilityLedger:
    if capability_id not in ledger.capabilities:
        raise KeyError(capability_id)
    dependents = [
        item.id
        for item in ledger.capabilities.values()
        if capability_id in item.dependencies and item.id != capability_id
    ]
    if dependents:
        raise ValueError(
            f"Cannot remove {capability_id}; required by: {', '.join(sorted(dependents))}"
        )
    del ledger.capabilities[capability_id]
    ledger.updated_at = utc_now_iso()
    return ledger


def topological_order(ledger: CapabilityLedger, capability_ids: Sequence[str]) -> list[str]:
    """Return dependency-respecting order for the requested capability ids."""

    requested = list(dict.fromkeys(capability_ids))
    missing = [item for item in requested if item not in ledger.capabilities]
    if missing:
        raise KeyError(f"Unknown capabilities: {', '.join(missing)}")

    needed: set[str] = set()

    def collect(capability_id: str) -> None:
        if capability_id in needed:
            return
        capability = ledger.capabilities[capability_id]
        for dependency in capability.dependencies:
            collect(dependency)
        needed.add(capability_id)

    for capability_id in requested:
        collect(capability_id)

    ordered: list[str] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(node: str) -> None:
        if node in permanent:
            return
        if node in temporary:
            raise ValueError(f"capability dependency cycle involving {node}")
        temporary.add(node)
        for dependency in ledger.capabilities[node].dependencies:
            if dependency in needed:
                visit(dependency)
        temporary.remove(node)
        permanent.add(node)
        ordered.append(node)

    for capability_id in sorted(needed):
        visit(capability_id)
    # Keep requested capabilities last while preserving deps-first order.
    return ordered


def _pythonpath_env(cwd: Path, env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build a subprocess env that always inherits the parent process environment.

    Callers may pass overrides (e.g. BLACKHOLE_CAPABILITY_ID); those are merged
    on top of os.environ so Windows shell proofs still see ComSpec/SystemRoot.
    """

    merged = dict(os.environ)
    if env:
        merged.update({str(key): str(value) for key, value in env.items()})
    source_root = str((cwd / "src").resolve()) if (cwd / "src").exists() else str(cwd.resolve())
    existing = merged.get("PYTHONPATH", "")
    merged["PYTHONPATH"] = source_root + (os.pathsep + existing if existing else "")
    return merged


def _run_shell(
    command: str,
    *,
    cwd: Path,
    command_runner: Callable[..., Any],
    timeout: int,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return command_runner(
        command,
        cwd=cwd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_pythonpath_env(cwd, env),
    )


ACTIVE_CAPABILITY_ENV = "BLACKHOLE_CAPABILITY_ID"


def run_python_entry(
    entry: str,
    *,
    cwd: Path,
    timeout: int = 120,
    command_runner: Callable[..., Any] = subprocess.run,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute `module:function` in a subprocess for isolation."""

    if ":" not in entry:
        raise ValueError(f"python capability entry must be module:function, got {entry!r}")
    module_name, _, function_name = entry.partition(":")
    if not module_name or not function_name:
        raise ValueError(f"python capability entry must be module:function, got {entry!r}")
    script = (
        "import importlib, json, sys\n"
        f"module = importlib.import_module({module_name!r})\n"
        f"fn = getattr(module, {function_name!r})\n"
        "result = fn()\n"
        "if result is None:\n"
        "    print(json.dumps({'ok': True}))\n"
        "elif isinstance(result, dict):\n"
        "    print(json.dumps(result, sort_keys=True, default=str))\n"
        "else:\n"
        "    print(result)\n"
    )
    return command_runner(
        [sys.executable, "-c", script],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_pythonpath_env(cwd, env),
    )


def run_capability(
    capability: Capability,
    *,
    cwd: Path,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    use_proof: bool = False,
) -> CapabilityRunResult:
    """Run a capability entry (or its proof command)."""

    active_env = {ACTIVE_CAPABILITY_ENV: capability.id}
    if use_proof:
        command_text = capability.proof_command
        completed = _run_shell(
            command_text,
            cwd=cwd,
            command_runner=command_runner,
            timeout=timeout,
            env=active_env,
        )
        command_tuple = ("shell", command_text)
        kind = "proof"
    elif capability.kind == "command":
        command_text = capability.entry
        completed = _run_shell(
            command_text,
            cwd=cwd,
            command_runner=command_runner,
            timeout=timeout,
            env=active_env,
        )
        command_tuple = ("shell", command_text)
        kind = "command"
    elif capability.kind == "python":
        completed = run_python_entry(
            capability.entry,
            cwd=cwd,
            timeout=timeout,
            command_runner=command_runner,
            env=active_env,
        )
        command_tuple = (sys.executable, "-c", f"<run {capability.entry}>")
        kind = "python"
    else:
        raise ValueError(f"Unsupported capability kind: {capability.kind}")

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    exit_code = int(completed.returncode)
    ok = exit_code == 0
    summary = stdout.splitlines()[0] if stdout else (stderr.splitlines()[0] if stderr else f"exit {exit_code}")
    return CapabilityRunResult(
        capability_id=capability.id,
        ok=ok,
        exit_code=exit_code,
        command=command_tuple,
        stdout=stdout,
        stderr=stderr,
        kind=kind,
        summary=summary[:500],
    )


def prove_capability(
    ledger: CapabilityLedger,
    capability_id: str,
    *,
    cwd: Path,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
) -> tuple[CapabilityLedger, CapabilityRunResult]:
    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        raise KeyError(capability_id)
    # Prove dependencies first.
    for dependency in topological_order(ledger, [capability_id])[:-1]:
        ledger, dep_result = prove_capability(
            ledger,
            dependency,
            cwd=cwd,
            command_runner=command_runner,
            timeout=timeout,
        )
        if not dep_result.ok:
            return ledger, CapabilityRunResult(
                capability_id=capability_id,
                ok=False,
                exit_code=dep_result.exit_code,
                command=dep_result.command,
                stdout=dep_result.stdout,
                stderr=dep_result.stderr,
                kind="dependency_proof",
                summary=f"dependency {dependency} failed proof: {dep_result.summary}",
            )
    result = run_capability(
        capability,
        cwd=cwd,
        command_runner=command_runner,
        timeout=timeout,
        use_proof=True,
    )
    now = utc_now_iso()
    updated = Capability(
        id=capability.id,
        name=capability.name,
        description=capability.description,
        kind=capability.kind,
        entry=capability.entry,
        proof_command=capability.proof_command,
        dependencies=capability.dependencies,
        behavior_paths=capability.behavior_paths,
        capability_delta=capability.capability_delta,
        tags=capability.tags,
        created_at=capability.created_at,
        updated_at=now,
        source_mission_id=capability.source_mission_id,
        source_milestone=capability.source_milestone,
        last_proved_at=now,
        last_proof_exit_code=result.exit_code,
    )
    ledger.capabilities[capability_id] = updated
    ledger.updated_at = now
    return ledger, result


def compose_capabilities(
    ledger: CapabilityLedger,
    capability_ids: Sequence[str],
    *,
    cwd: Path,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    prove_first: bool = True,
) -> list[CapabilityRunResult]:
    """Run a dependency-ordered capability chain."""

    order = topological_order(ledger, capability_ids)
    results: list[CapabilityRunResult] = []
    for capability_id in order:
        capability = ledger.capabilities[capability_id]
        if prove_first:
            ledger, proof = prove_capability(
                ledger,
                capability_id,
                cwd=cwd,
                command_runner=command_runner,
                timeout=timeout,
            )
            if not proof.ok:
                results.append(proof)
                break
        result = run_capability(
            capability,
            cwd=cwd,
            command_runner=command_runner,
            timeout=timeout,
            use_proof=False,
        )
        results.append(result)
        if not result.ok:
            break
    return results


def ledger_prompt_summary(ledger: CapabilityLedger, *, limit: int = 12) -> str:
    """Compact inventory for Unbound turn prompts."""

    if not ledger.capabilities:
        return "(empty capability ledger — no compounded capabilities yet)"
    rows: list[dict[str, Any]] = []
    for capability in sorted(ledger.capabilities.values(), key=lambda item: item.id)[:limit]:
        rows.append(
            {
                "id": capability.id,
                "name": capability.name,
                "kind": capability.kind,
                "deps": list(capability.dependencies),
                "proved": capability.last_proof_exit_code == 0,
                "delta": (capability.capability_delta or "")[:120],
            }
        )
    omitted = max(0, len(ledger.capabilities) - limit)
    payload = {"count": len(ledger.capabilities), "capabilities": rows}
    if omitted:
        payload["omitted"] = omitted
    return json.dumps(payload, indent=2, ensure_ascii=False)


def capability_from_milestone(
    *,
    capability_id: str | None,
    name: str,
    description: str,
    capability_delta: str,
    proof_command: str,
    behavior_paths: Sequence[str],
    mission_id: str = "",
    milestone_number: int | None = None,
    entry: str | None = None,
    kind: str = "command",
    dependencies: Sequence[str] = (),
    tags: Sequence[str] = (),
) -> Capability:
    """Build a capability record from an accepted Unbound milestone."""

    resolved_id = capability_id or slugify_capability_id(name or capability_delta or "milestone")
    resolved_entry = entry or proof_command
    return Capability(
        id=resolved_id,
        name=name or resolved_id,
        description=description or capability_delta or name,
        kind=kind,
        entry=resolved_entry,
        proof_command=proof_command,
        dependencies=tuple(dependencies),
        behavior_paths=tuple(path for path in behavior_paths if path),
        capability_delta=capability_delta,
        tags=tuple(tags),
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
        source_mission_id=mission_id,
        source_milestone=milestone_number,
    )


# --- Built-in python capability targets (invoked via module:function) ---


def builtin_repo_import_health() -> dict[str, Any]:
    """Prove the package imports cleanly without legacy skill-route machinery."""

    import blackhole_agent
    from blackhole_agent import capability_compounder, unbound

    skill_route_symbols = [name for name in dir(capability_compounder) if "skill_route" in name.lower()]
    return {
        "ok": True,
        "package_version": getattr(blackhole_agent, "__version__", ""),
        "unbound_module": unbound.__name__,
        "compounder_module": capability_compounder.__name__,
        "skill_route_symbols_in_compounder": skill_route_symbols,
        "imports_skill_routing": "skill_routing" in sys.modules,
    }


def builtin_milestone_gate_smoke() -> dict[str, Any]:
    """Exercise the Unbound milestone gate against a synthetic behavior change."""

    from blackhole_agent.unbound import TurnDecision, evaluate_milestone

    decision = TurnDecision.from_payload(
        {
            "status": "milestone",
            "summary": "capability compounder smoke",
            "strategy": "direct",
            "next_step": "compose",
            "capability_delta": "Milestone gate accepts behavior paths.",
            "outcome_evidence": ["synthetic path src/blackhole_agent/capability_compounder.py"],
            "validation": [{"command": "true", "exit_code": 0, "summary": "ok"}],
            "done_when_met": False,
            "commit_message": "",
            "mission_goal": "",
            "done_when": "",
        }
    )
    accepted = evaluate_milestone(
        decision,
        changed_paths=["src/blackhole_agent/capability_compounder.py"],
    )
    rejected = evaluate_milestone(
        decision,
        changed_paths=["docs/unbound-v2.md", "tests/test_unbound.py"],
    )
    return {
        "ok": accepted.accepted and not rejected.accepted,
        "accepted_behavior": accepted.accepted,
        "rejected_docs_only": not rejected.accepted,
        "reject_reasons": list(rejected.reasons),
    }


def builtin_ledger_inventory() -> dict[str, Any]:
    """Return the in-repo ledger inventory for composition demos."""

    # Resolve repo root from this file: src/blackhole_agent/capability_compounder.py
    repo_root = Path(__file__).resolve().parents[2]
    path = default_ledger_path(repo_root)
    ledger = load_ledger(path)
    return {
        "ok": True,
        "ledger_path": str(path),
        "count": len(ledger.capabilities),
        "ids": sorted(ledger.capabilities),
        "updated_at": ledger.updated_at,
    }


def builtin_evolution_route_redirect() -> dict[str, Any]:
    """Prove supervisor/skill-route surfaces redirect to the compounder when ready."""

    from blackhole_agent.evolution_route import (
        COMPOUND_SURFACE,
        build_skill_route_compounder_redirect_pipeline,
        resolve_supervisor_evolution_surface,
        should_redirect_skill_route_pipeline,
    )

    repo_root = Path(__file__).resolve().parents[2]
    redirected = should_redirect_skill_route_pipeline(repo_root)
    surface = resolve_supervisor_evolution_surface(
        evolution_mode="codex",
        repo_path=repo_root,
        prefer_capability_compounder=True,
    )
    pipeline = build_skill_route_compounder_redirect_pipeline(repo_path=repo_root)
    ok = (
        redirected
        and surface.get("surface") == COMPOUND_SURFACE
        and surface.get("effective_mode") == "compound"
        and pipeline.get("skill_route_pin_cascade_frozen") is True
        and pipeline.get("supervisor_next_action") == "run_capability_compounder_compose_or_demo"
    )
    return {
        "ok": ok,
        "redirected": redirected,
        "surface": surface.get("surface"),
        "effective_mode": surface.get("effective_mode"),
        "reason": surface.get("reason"),
        "pipeline_status": pipeline.get("status"),
        "pin_cascade_frozen": pipeline.get("skill_route_pin_cascade_frozen"),
    }


def builtin_local_memory_roundtrip() -> dict[str, Any]:
    """Prove local memory write/read/delete and privacy rejection without skill-route."""

    import tempfile

    from blackhole_agent.local_memory import LocalMemoryStore, MemoryPrivacyError

    with tempfile.TemporaryDirectory(prefix="blackhole-cap-memory-") as tmp:
        store = LocalMemoryStore(Path(tmp), namespace="cap-smoke")
        store.write("hello", "public note", tags=("smoke",))
        entry = store.read("hello")
        listed = store.list(tag="smoke")
        deleted = store.delete("hello")
        privacy_blocked = False
        try:
            store.write("secret-key", "sk-" + ("x" * 24))
        except MemoryPrivacyError:
            privacy_blocked = True
        ok = bool(entry is not None and listed and deleted and privacy_blocked)
        return {
            "ok": ok,
            "read_key": entry.key if entry else None,
            "list_count": len(listed),
            "deleted": deleted,
            "privacy_guard": privacy_blocked,
            "used_skill_route_discovery": "skill_routing" in sys.modules
            or "blackhole_agent.skill_routing" in sys.modules,
        }


def builtin_tool_routing_preflight() -> dict[str, Any]:
    """Prove tool routing preflight + executable registry for local tools."""

    from blackhole_agent.tool_routing import (
        ToolDescriptor,
        build_tool_routing_preflight,
        executable_tool_registry,
    )

    descriptors = (
        ToolDescriptor(
            name="local_memory",
            description="Local memory tool",
            provider="local",
            tool_type="function",
        ),
        ToolDescriptor(
            name="review_only_tool",
            description="Needs human review",
            provider="local",
            tool_type="function",
            risk_flags=("privacy-leakage",),
        ),
    )
    preflight = build_tool_routing_preflight(
        descriptors,
        required_tool_names=("local_memory",),
    )
    registry = executable_tool_registry(descriptors)
    ok = (
        bool(preflight.get("ok"))
        and "local_memory" in preflight.get("executable_tool_names", [])
        and "local_memory" in registry
        and "local_memory" not in preflight.get("missing_required_tool_names", [])
    )
    return {
        "ok": ok,
        "executable_tool_names": list(preflight.get("executable_tool_names") or []),
        "route_counts": dict(preflight.get("route_counts") or {}),
        "registry_keys": sorted(registry),
        "missing_required": list(preflight.get("missing_required_tool_names") or []),
        "used_skill_route_discovery": "skill_routing" in sys.modules
        or "blackhole_agent.skill_routing" in sys.modules,
    }


def builtin_harness_activation_gate() -> dict[str, Any]:
    """Prove harness eval activation gate decisions for ready vs blocked modes."""

    from blackhole_agent.harness_eval import agent_harness_eval_activation_gate

    ready = agent_harness_eval_activation_gate("none")
    blocked = agent_harness_eval_activation_gate("review_only_safety_boundary")
    weak = agent_harness_eval_activation_gate("weak_harness_evidence")
    ok = (
        bool(ready.get("local_eval_activation_allowed"))
        and not bool(blocked.get("local_eval_activation_allowed"))
        and not bool(weak.get("local_eval_activation_allowed"))
        and ready.get("decision") == "ready_for_local_eval_activation"
        and not bool(ready.get("external_harness_execution_allowed"))
    )
    return {
        "ok": ok,
        "ready_decision": ready.get("decision"),
        "blocked_decision": blocked.get("decision"),
        "weak_decision": weak.get("decision"),
        "local_eval_activation_allowed": ready.get("local_eval_activation_allowed"),
        "used_skill_route_discovery": "skill_routing" in sys.modules
        or "blackhole_agent.skill_routing" in sys.modules,
    }


# --- Growth loop: scout → absorb domain / promote composition → prove ---

# Domain package surfaces the compounder can absorb into the ledger (beyond meta self-composition).
DOMAIN_SURFACE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "domain.local-memory",
        "name": "Local memory privacy roundtrip",
        "description": (
            "Write/read/list/delete through LocalMemoryStore and reject secret payloads."
        ),
        "module": "blackhole_agent.local_memory",
        "module_path": "src/blackhole_agent/local_memory.py",
        "entry": "blackhole_agent.capability_compounder:builtin_local_memory_roundtrip",
        "function": "builtin_local_memory_roundtrip",
        "capability_delta": (
            "Local memory with privacy guards is invocable as a first-class ledger capability."
        ),
        "tags": ("domain", "memory", "absorbable"),
        "priority": 70,
        "dependencies": ("repo.import-health",),
    },
    {
        "id": "domain.tool-routing",
        "name": "Tool routing preflight",
        "description": (
            "Route local tool descriptors, report executable tools, and build a registry."
        ),
        "module": "blackhole_agent.tool_routing",
        "module_path": "src/blackhole_agent/tool_routing.py",
        "entry": "blackhole_agent.capability_compounder:builtin_tool_routing_preflight",
        "function": "builtin_tool_routing_preflight",
        "capability_delta": (
            "Tool routing preflight is invocable as a first-class ledger capability."
        ),
        "tags": ("domain", "tools", "absorbable"),
        "priority": 65,
        "dependencies": ("repo.import-health",),
    },
    {
        "id": "domain.harness-activation",
        "name": "Harness activation gate",
        "description": (
            "Decide whether local agent harness evaluation may activate for a failure mode."
        ),
        "module": "blackhole_agent.harness_eval",
        "module_path": "src/blackhole_agent/harness_eval.py",
        "entry": "blackhole_agent.capability_compounder:builtin_harness_activation_gate",
        "function": "builtin_harness_activation_gate",
        "capability_delta": (
            "Harness activation gating is invocable as a first-class ledger capability."
        ),
        "tags": ("domain", "harness", "absorbable"),
        "priority": 60,
        "dependencies": ("repo.import-health",),
    },
)

# Modules that are runtime/control surfaces, not domain absorption candidates.
_DOMAIN_SCOUT_SKIP_STEMS = frozenset(
    {
        "__init__",
        "capability_compounder",
        "unbound",
        "cli",
        "evolution_route",
        "supervisor",
        "github_growth",
        "skill_routing",
        "self_model",
        "persona",
        "ci_security",
        "proposal_synthesis",
    }
)

# Canonical multi-capability recipes the compounder can promote into durable capabilities.
KNOWN_GROWTH_RECIPES: tuple[dict[str, Any], ...] = (
    {
        "suggested_id": "capability.composed-core-health",
        "name": "Composed core health chain",
        "members": (
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
        ),
        "reason": "Core health/inventory/gate chain is composable and operator-useful as one invocable unit.",
        "priority": 100,
        "tags": ("composed", "promoted", "growth"),
    },
    {
        "suggested_id": "capability.composed-domain-core",
        "name": "Composed domain core chain",
        "members": (
            "domain.local-memory",
            "domain.tool-routing",
            "domain.harness-activation",
        ),
        "reason": (
            "Domain memory, tool routing, and harness activation form a non-meta "
            "composition the growth loop can promote once absorbed."
        ),
        "priority": 90,
        "tags": ("composed", "promoted", "growth", "domain"),
    },
    {
        "suggested_id": "capability.composed-evolution-ready",
        "name": "Composed evolution-ready chain",
        "members": (
            "repo.import-health",
            "capability.ledger-inventory",
            "evolution.compounder-redirect",
        ),
        "reason": "Evolution redirect readiness can be re-proved as a single composed capability.",
        "priority": 80,
        "tags": ("composed", "promoted", "growth", "evolution-route"),
    },
)


def _member_set_key(member_ids: Sequence[str]) -> frozenset[str]:
    return frozenset(str(item).strip() for item in member_ids if str(item).strip())


def existing_promoted_member_sets(ledger: CapabilityLedger) -> set[frozenset[str]]:
    """Return dependency sets already represented by promoted/composed capabilities."""

    promoted: set[frozenset[str]] = set()
    for capability in ledger.capabilities.values():
        tags = set(capability.tags)
        if tags.intersection({"composed", "promoted"}) and capability.dependencies:
            promoted.add(_member_set_key(capability.dependencies))
    return promoted


def resolve_domain_surface(surface_id: str) -> dict[str, Any]:
    """Return one domain surface catalog entry or raise KeyError."""

    for surface in DOMAIN_SURFACE_CATALOG:
        if surface["id"] == surface_id:
            return dict(surface)
    raise KeyError(surface_id)


def capability_from_domain_surface(surface: Mapping[str, Any]) -> Capability:
    """Materialize a domain catalog entry as a durable Capability record."""

    function_name = str(surface["function"])
    proof_command = (
        f'"{sys.executable}" -c '
        f'"from blackhole_agent.capability_compounder import {function_name}; '
        f"r={function_name}(); assert r['ok']\""
    )
    dependencies = tuple(str(item) for item in (surface.get("dependencies") or ()) if str(item).strip())
    tags = tuple(str(item) for item in (surface.get("tags") or ()) if str(item).strip())
    module_path = str(surface.get("module_path") or "")
    behavior_paths = tuple(
        path for path in (module_path, "src/blackhole_agent/capability_compounder.py") if path
    )
    return Capability(
        id=str(surface["id"]),
        name=str(surface.get("name") or surface["id"]),
        description=str(surface.get("description") or surface.get("name") or surface["id"]),
        kind="python",
        entry=str(surface["entry"]),
        proof_command=proof_command,
        dependencies=dependencies,
        behavior_paths=behavior_paths,
        capability_delta=str(surface.get("capability_delta") or ""),
        tags=tags,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )


def scout_package_surfaces(
    repo_path: Path,
    *,
    ledger: CapabilityLedger | None = None,
) -> list[dict[str, Any]]:
    """Filesystem scout for package modules not yet catalogued as domain surfaces."""

    package_dir = (repo_path / "src" / "blackhole_agent").resolve()
    if not package_dir.is_dir():
        return []
    catalogued_paths = {
        str(surface.get("module_path") or "").replace("\\", "/") for surface in DOMAIN_SURFACE_CATALOG
    }
    ledger_ids = set(ledger.capabilities) if ledger is not None else set()
    rows: list[dict[str, Any]] = []
    for path in sorted(package_dir.glob("*.py")):
        stem = path.stem
        if stem in _DOMAIN_SCOUT_SKIP_STEMS or stem.startswith("test"):
            continue
        rel = f"src/blackhole_agent/{path.name}"
        if rel in catalogued_paths:
            continue
        suggested_id = f"domain.{slugify_capability_id(stem)}"
        rows.append(
            {
                "module": f"blackhole_agent.{stem}",
                "module_path": rel,
                "suggested_id": suggested_id,
                "status": "already_absorbed" if suggested_id in ledger_ids else "uncatalogued_surface",
                "reason": "Package module present but not in DOMAIN_SURFACE_CATALOG.",
            }
        )
    return rows


def scout_domain_surfaces(
    ledger: CapabilityLedger,
    *,
    repo_path: Path,
) -> list[dict[str, Any]]:
    """Rank absorbable domain surfaces from the catalog against the filesystem and ledger."""

    root = repo_path.resolve()
    opportunities: list[dict[str, Any]] = []
    for surface in DOMAIN_SURFACE_CATALOG:
        module_path = root / str(surface["module_path"])
        present = module_path.is_file()
        surface_id = str(surface["id"])
        if surface_id in ledger.capabilities:
            status = "already_absorbed"
        elif not present:
            status = "blocked_missing_module"
        else:
            status = "ready_to_absorb"
        opportunities.append(
            {
                "kind": "domain_absorb",
                "suggested_id": surface_id,
                "name": surface["name"],
                "members": [surface_id],
                "reason": (
                    f"Absorb package surface {surface['module']} into the durable ledger."
                    if status == "ready_to_absorb"
                    else surface.get("description") or surface["name"]
                ),
                "priority": int(surface.get("priority") or 50),
                "status": status,
                "missing_members": [],
                "module": surface["module"],
                "module_path": surface["module_path"],
                "module_present": present,
            }
        )
    opportunities.sort(
        key=lambda item: (
            0 if item["status"] == "ready_to_absorb" else 1 if item["status"] == "already_absorbed" else 2,
            -int(item["priority"]),
            item["suggested_id"],
        )
    )
    return opportunities


def absorb_domain_surface(
    ledger: CapabilityLedger,
    surface_id: str,
    *,
    replace: bool = False,
) -> tuple[CapabilityLedger, Capability]:
    """Register one catalogued domain surface as a durable invocable capability."""

    surface = resolve_domain_surface(surface_id)
    capability = capability_from_domain_surface(surface)
    if capability.id in ledger.capabilities and not replace:
        # Idempotent absorb: return existing record without error.
        return ledger, ledger.capabilities[capability.id]
    ledger = register_capability(ledger, capability, replace=replace or capability.id in ledger.capabilities)
    return ledger, ledger.capabilities[capability.id]


def absorb_ready_domain_surfaces(
    ledger: CapabilityLedger,
    *,
    repo_path: Path,
    limit: int = 1,
) -> tuple[CapabilityLedger, list[Capability]]:
    """Absorb up to `limit` ready domain surfaces (filesystem-present, not yet in ledger)."""

    absorbed: list[Capability] = []
    for opportunity in scout_domain_surfaces(ledger, repo_path=repo_path):
        if opportunity["status"] != "ready_to_absorb":
            continue
        ledger, capability = absorb_domain_surface(ledger, opportunity["suggested_id"], replace=False)
        absorbed.append(capability)
        if len(absorbed) >= max(1, int(limit)):
            break
    return ledger, absorbed


def scout_capability_gaps(
    ledger: CapabilityLedger,
    *,
    repo_path: Path | None = None,
) -> dict[str, Any]:
    """Rank ledger growth opportunities without skill-route machinery.

    Includes composition-promotion recipes and domain-surface absorption from the
    package filesystem, so growth continues after meta self-composition is exhausted.
    """

    root = (repo_path or Path(__file__).resolve().parents[2]).resolve()
    unproved = sorted(
        item.id
        for item in ledger.capabilities.values()
        if item.last_proof_exit_code not in (0,)
    )
    never_proved = sorted(
        item.id for item in ledger.capabilities.values() if not item.last_proved_at
    )
    already = existing_promoted_member_sets(ledger)
    opportunities: list[dict[str, Any]] = []
    for recipe in KNOWN_GROWTH_RECIPES:
        members = tuple(recipe["members"])
        missing = [member for member in members if member not in ledger.capabilities]
        member_key = _member_set_key(members)
        already_promoted = member_key in already or recipe["suggested_id"] in ledger.capabilities
        status = "ready"
        if missing:
            status = "blocked_missing_members"
        elif already_promoted:
            status = "already_promoted"
        opportunities.append(
            {
                "kind": "composition",
                "suggested_id": recipe["suggested_id"],
                "name": recipe["name"],
                "members": list(members),
                "reason": recipe["reason"],
                "priority": int(recipe["priority"]),
                "status": status,
                "missing_members": missing,
            }
        )
    domain_opportunities = scout_domain_surfaces(ledger, repo_path=root)
    opportunities.extend(domain_opportunities)
    # Prefer ready compositions, then ready domain absorbs, then already-done, then blocked.
    status_rank = {
        "ready": 0,
        "ready_to_absorb": 1,
        "already_promoted": 2,
        "already_absorbed": 3,
        "blocked_missing_members": 4,
        "blocked_missing_module": 5,
    }
    opportunities.sort(
        key=lambda item: (
            status_rank.get(str(item["status"]), 9),
            -int(item["priority"]),
            item["suggested_id"],
        )
    )
    recommended = next(
        (
            item
            for item in opportunities
            if item["status"] in {"ready", "ready_to_absorb"}
        ),
        None,
    )
    growth_surface_missing = [
        capability_id
        for capability_id in ("capability.scout-gaps", "capability.growth-loop")
        if capability_id not in ledger.capabilities
    ]
    uncatalogued = scout_package_surfaces(root, ledger=ledger)
    domain_ids = {surface["id"] for surface in DOMAIN_SURFACE_CATALOG}
    domain_absorbed = sorted(domain_ids.intersection(ledger.capabilities))
    domain_pending = sorted(
        item["suggested_id"]
        for item in domain_opportunities
        if item["status"] == "ready_to_absorb"
    )
    return {
        "ok": True,
        "count": len(ledger.capabilities),
        "ids": sorted(ledger.capabilities),
        "unproved": unproved,
        "never_proved": never_proved,
        "growth_surface_missing": growth_surface_missing,
        "domain_absorbed": domain_absorbed,
        "domain_pending": domain_pending,
        "uncatalogued_surfaces": uncatalogued,
        "opportunities": opportunities,
        "recommended": recommended,
        "used_skill_route_discovery": "skill_routing" in sys.modules
        or "blackhole_agent.skill_routing" in sys.modules,
        "ledger_path": str(default_ledger_path(root)),
    }


def run_named_recipe(
    member_ids: Sequence[str],
    *,
    repo_path: Path | None = None,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    prove_first: bool = True,
) -> dict[str, Any]:
    """Compose an explicit member list against the in-repo ledger."""

    root = (repo_path or Path(__file__).resolve().parents[2]).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    order = topological_order(ledger, member_ids)
    results = compose_capabilities(
        ledger,
        member_ids,
        cwd=root,
        command_runner=command_runner,
        timeout=timeout,
        prove_first=prove_first,
    )
    save_ledger(path, ledger)
    ok = bool(results) and all(item.ok for item in results) and len(results) == len(order)
    return {
        "ok": ok,
        "members": list(member_ids),
        "order": order,
        "results": [item.to_dict() for item in results],
        "ledger_path": str(path),
    }


def builtin_execute_composed_capability() -> dict[str, Any]:
    """Execute the composition defined by the active capability's dependencies.

    `run_capability` injects BLACKHOLE_CAPABILITY_ID so promoted recipes remain
    zero-arg python entries while still knowing which dependency set to compose.
    """

    capability_id = (os.environ.get(ACTIVE_CAPABILITY_ENV) or "").strip()
    root = Path(__file__).resolve().parents[2]
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    if not capability_id:
        return {"ok": False, "error": f"{ACTIVE_CAPABILITY_ENV} is not set"}
    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        return {"ok": False, "error": f"unknown capability {capability_id}", "capability_id": capability_id}
    members = list(capability.dependencies)
    if not members:
        return {
            "ok": False,
            "error": "composed capability has no dependencies to run",
            "capability_id": capability_id,
        }
    recipe = run_named_recipe(members, repo_path=root)
    return {
        "ok": bool(recipe.get("ok")),
        "capability_id": capability_id,
        "members": members,
        "order": recipe.get("order"),
        "results": recipe.get("results"),
        "ledger_path": recipe.get("ledger_path"),
    }


def promote_composition(
    ledger: CapabilityLedger,
    member_ids: Sequence[str],
    *,
    capability_id: str | None = None,
    name: str | None = None,
    description: str = "",
    capability_delta: str = "",
    tags: Sequence[str] = ("composed", "promoted", "growth"),
    replace: bool = False,
) -> tuple[CapabilityLedger, Capability]:
    """Materialize a successful multi-capability chain as one durable capability."""

    members = tuple(dict.fromkeys(str(item).strip() for item in member_ids if str(item).strip()))
    if len(members) < 2:
        raise ValueError("promote_composition requires at least two member capability ids")
    missing = [member for member in members if member not in ledger.capabilities]
    if missing:
        raise ValueError(f"cannot promote; missing members: {', '.join(missing)}")
    # Validate the graph can order the members.
    topological_order(ledger, members)

    known = next(
        (
            recipe
            for recipe in KNOWN_GROWTH_RECIPES
            if _member_set_key(recipe["members"]) == _member_set_key(members)
        ),
        None,
    )
    resolved_id = capability_id or (known["suggested_id"] if known else None)
    if not resolved_id:
        resolved_id = "capability.composed-" + slugify_capability_id("-".join(members), limit=40)
    resolved_name = name or (known["name"] if known else f"Composed {' + '.join(members)}")
    resolved_delta = capability_delta or (
        f"Promoted multi-capability composition of {', '.join(members)} into one invocable unit."
    )
    resolved_description = description or (
        f"Dependency-ordered composition of: {', '.join(members)}."
    )
    proof = (
        f'"{sys.executable}" -c '
        '"from blackhole_agent.capability_compounder import builtin_execute_composed_capability; '
        "import os; "
        f"os.environ[{ACTIVE_CAPABILITY_ENV!r}]={resolved_id!r}; "
        "r=builtin_execute_composed_capability(); assert r['ok']\""
    )
    capability = Capability(
        id=resolved_id,
        name=resolved_name,
        description=resolved_description,
        kind="python",
        entry="blackhole_agent.capability_compounder:builtin_execute_composed_capability",
        proof_command=proof,
        dependencies=members,
        behavior_paths=(
            "src/blackhole_agent/capability_compounder.py",
            "capabilities/ledger.json",
        ),
        capability_delta=resolved_delta,
        tags=tuple(dict.fromkeys(tags)),
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    register_capability(ledger, capability, replace=replace or resolved_id in ledger.capabilities)
    return ledger, capability


def run_growth_loop(
    repo_path: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    recipe_id: str | None = None,
) -> dict[str, Any]:
    """Scout → absorb domain surface or promote composition → prove.

    Grows the ledger without skill-route machinery. When meta compositions are
    exhausted, absorbs catalogued domain package surfaces and can promote a
    multi-domain composition.
    """

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    before_count = len(ledger.capabilities)
    before_ids = sorted(ledger.capabilities)
    scout = scout_capability_gaps(ledger, repo_path=root)

    selected: dict[str, Any] | None = None
    if recipe_id:
        selected = next(
            (item for item in scout["opportunities"] if item["suggested_id"] == recipe_id),
            None,
        )
        if selected is None:
            # Allow direct member promotion by suggested id even if not in scout list.
            known = next((item for item in KNOWN_GROWTH_RECIPES if item["suggested_id"] == recipe_id), None)
            domain = next((item for item in DOMAIN_SURFACE_CATALOG if item["id"] == recipe_id), None)
            if known is not None:
                selected = {
                    "kind": "composition",
                    "suggested_id": known["suggested_id"],
                    "name": known["name"],
                    "members": list(known["members"]),
                    "reason": known["reason"],
                    "priority": known["priority"],
                    "status": "ready"
                    if all(member in ledger.capabilities for member in known["members"])
                    and known["suggested_id"] not in ledger.capabilities
                    else "blocked",
                    "missing_members": [
                        member for member in known["members"] if member not in ledger.capabilities
                    ],
                }
            elif domain is not None:
                selected = {
                    "kind": "domain_absorb",
                    "suggested_id": domain["id"],
                    "name": domain["name"],
                    "members": [domain["id"]],
                    "reason": f"Absorb package surface {domain['module']}.",
                    "priority": int(domain.get("priority") or 50),
                    "status": "already_absorbed"
                    if domain["id"] in ledger.capabilities
                    else "ready_to_absorb",
                    "missing_members": [],
                }
            else:
                return {
                    "ok": False,
                    "grew": False,
                    "error": f"unknown recipe_id {recipe_id!r}",
                    "scout": scout,
                    "before_count": before_count,
                    "after_count": before_count,
                    "used_skill_route_discovery": scout["used_skill_route_discovery"],
                }
    else:
        selected = scout.get("recommended")

    if not selected:
        # All known recipes already promoted (or blocked): re-prove the best existing one.
        already = [
            item
            for item in scout["opportunities"]
            if item["status"] in {"already_promoted", "already_absorbed"}
            and item["suggested_id"] in ledger.capabilities
        ]
        if not already:
            return {
                "ok": True,
                "grew": False,
                "reason": "no_ready_growth_opportunities",
                "scout": scout,
                "before_count": before_count,
                "after_count": before_count,
                "before_ids": before_ids,
                "after_ids": before_ids,
                "used_skill_route_discovery": scout["used_skill_route_discovery"],
            }
        selected = already[0]
        # Fall through into the already_promoted re-prove path below.

    # Domain absorption path — grows beyond meta self-composition.
    if selected.get("status") == "ready_to_absorb" or (
        selected.get("kind") == "domain_absorb" and selected["suggested_id"] not in ledger.capabilities
    ):
        surface_id = str(selected["suggested_id"])
        ledger, absorbed = absorb_domain_surface(ledger, surface_id, replace=False)
        save_ledger(path, ledger)
        ledger, proof = prove_capability(
            ledger,
            absorbed.id,
            cwd=root,
            command_runner=command_runner,
            timeout=timeout,
        )
        save_ledger(path, ledger)
        run_result = run_capability(
            ledger.capabilities[absorbed.id],
            cwd=root,
            command_runner=command_runner,
            timeout=timeout,
            use_proof=False,
        )
        after_ids = sorted(ledger.capabilities)
        grew = absorbed.id not in before_ids and absorbed.id in ledger.capabilities
        ok = (
            proof.ok
            and run_result.ok
            and grew
            and len(ledger.capabilities) > before_count
            and not (
                "skill_routing" in sys.modules or "blackhole_agent.skill_routing" in sys.modules
            )
        )
        return {
            "ok": ok,
            "grew": grew,
            "action": "absorb_domain",
            "promoted_id": absorbed.id,
            "absorbed_id": absorbed.id,
            "absorbed": absorbed.to_dict(),
            "scout": scout,
            "selected": selected,
            "proof": proof.to_dict(),
            "run": run_result.to_dict(),
            "before_count": before_count,
            "after_count": len(ledger.capabilities),
            "before_ids": before_ids,
            "after_ids": after_ids,
            "used_skill_route_discovery": "skill_routing" in sys.modules
            or "blackhole_agent.skill_routing" in sys.modules,
        }

    if (
        selected.get("status") in {"already_promoted", "already_absorbed"}
        or selected["suggested_id"] in ledger.capabilities
    ):
        # Re-prove the existing capability instead of no-op failure.
        # Skip this branch for multi-member compositions that are still missing.
        if selected.get("status") == "ready" and selected.get("kind") == "composition":
            pass  # fall through to promote
        elif selected.get("missing_members"):
            return {
                "ok": False,
                "grew": False,
                "error": f"missing members: {', '.join(selected['missing_members'])}",
                "selected": selected,
                "scout": scout,
                "before_count": before_count,
                "after_count": before_count,
                "used_skill_route_discovery": scout["used_skill_route_discovery"],
            }
        else:
            promoted_id = selected["suggested_id"]
            if promoted_id not in ledger.capabilities:
                return {
                    "ok": False,
                    "grew": False,
                    "error": f"capability {promoted_id} not in ledger",
                    "selected": selected,
                    "scout": scout,
                    "before_count": before_count,
                    "after_count": before_count,
                    "used_skill_route_discovery": scout["used_skill_route_discovery"],
                }
            ledger, proof = prove_capability(
                ledger,
                promoted_id,
                cwd=root,
                command_runner=command_runner,
                timeout=timeout,
            )
            save_ledger(path, ledger)
            run_result = run_capability(
                ledger.capabilities[promoted_id],
                cwd=root,
                command_runner=command_runner,
                timeout=timeout,
                use_proof=False,
            )
            return {
                "ok": proof.ok and run_result.ok,
                "grew": False,
                "action": "reprove",
                "reason": "already_promoted_reproved"
                if selected.get("status") == "already_promoted"
                else "already_absorbed_reproved",
                "promoted_id": promoted_id,
                "scout": scout,
                "selected": selected,
                "proof": proof.to_dict(),
                "run": run_result.to_dict(),
                "before_count": before_count,
                "after_count": len(ledger.capabilities),
                "before_ids": before_ids,
                "after_ids": sorted(ledger.capabilities),
                "used_skill_route_discovery": "skill_routing" in sys.modules
                or "blackhole_agent.skill_routing" in sys.modules,
            }

    if selected.get("missing_members"):
        return {
            "ok": False,
            "grew": False,
            "error": f"missing members: {', '.join(selected['missing_members'])}",
            "selected": selected,
            "scout": scout,
            "before_count": before_count,
            "after_count": before_count,
            "used_skill_route_discovery": scout["used_skill_route_discovery"],
        }

    known = next(
        (item for item in KNOWN_GROWTH_RECIPES if item["suggested_id"] == selected["suggested_id"]),
        None,
    )
    ledger, promoted = promote_composition(
        ledger,
        selected["members"],
        capability_id=selected["suggested_id"],
        name=selected.get("name"),
        description=selected.get("reason", ""),
        tags=tuple(known["tags"]) if known else ("composed", "promoted", "growth"),
        replace=False,
    )
    save_ledger(path, ledger)
    ledger, proof = prove_capability(
        ledger,
        promoted.id,
        cwd=root,
        command_runner=command_runner,
        timeout=timeout,
    )
    save_ledger(path, ledger)
    run_result = run_capability(
        ledger.capabilities[promoted.id],
        cwd=root,
        command_runner=command_runner,
        timeout=timeout,
        use_proof=False,
    )
    after_ids = sorted(ledger.capabilities)
    grew = promoted.id not in before_ids and promoted.id in ledger.capabilities
    ok = (
        proof.ok
        and run_result.ok
        and grew
        and len(ledger.capabilities) > before_count
        and not (
            "skill_routing" in sys.modules or "blackhole_agent.skill_routing" in sys.modules
        )
    )
    return {
        "ok": ok,
        "grew": grew,
        "action": "promote_composition",
        "promoted_id": promoted.id,
        "promoted": promoted.to_dict(),
        "scout": scout,
        "selected": selected,
        "proof": proof.to_dict(),
        "run": run_result.to_dict(),
        "before_count": before_count,
        "after_count": len(ledger.capabilities),
        "before_ids": before_ids,
        "after_ids": after_ids,
        "used_skill_route_discovery": "skill_routing" in sys.modules
        or "blackhole_agent.skill_routing" in sys.modules,
    }


def builtin_scout_gaps() -> dict[str, Any]:
    """Invocable capability: scout the durable ledger for growth opportunities."""

    root = Path(__file__).resolve().parents[2]
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    result = scout_capability_gaps(ledger, repo_path=root)
    result["ledger_path"] = str(path)
    return result


def builtin_growth_loop() -> dict[str, Any]:
    """Invocable capability: run scout → promote → prove growth once."""

    root = Path(__file__).resolve().parents[2]
    return run_growth_loop(root)


def seed_bootstrap_capabilities(ledger: CapabilityLedger) -> CapabilityLedger:
    """Install the minimal compoundable bootstrap set if missing."""

    seeds = [
        Capability(
            id="repo.import-health",
            name="Repository import health",
            description="Import blackhole_agent, unbound, and the compounder without skill-route coupling.",
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_repo_import_health",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_repo_import_health; '
                "r=builtin_repo_import_health(); assert r['ok'] and not r['skill_route_symbols_in_compounder']\""
            ),
            dependencies=(),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
            ),
            capability_delta="Runtime can prove package import health independent of skill-route machinery.",
            tags=("bootstrap", "health"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="unbound.milestone-gate",
            name="Unbound milestone gate smoke",
            description="Verify behavior-path milestone gating accepts code and rejects docs/tests-only diffs.",
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_milestone_gate_smoke",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_milestone_gate_smoke; '
                "r=builtin_milestone_gate_smoke(); assert r['ok']\""
            ),
            dependencies=("repo.import-health",),
            behavior_paths=("src/blackhole_agent/unbound.py",),
            capability_delta="Milestone acceptance is enforceable as an invocable capability.",
            tags=("bootstrap", "unbound"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.ledger-inventory",
            name="Capability ledger inventory",
            description="Load and summarize the durable in-repo capability ledger.",
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_ledger_inventory",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_ledger_inventory; '
                "r=builtin_ledger_inventory(); assert r['ok'] and r['count'] >= 2\""
            ),
            dependencies=("repo.import-health",),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "capabilities/ledger.json",
            ),
            capability_delta="Capability inventory is queryable as a first-class local capability.",
            tags=("bootstrap", "compounder"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="evolution.compounder-redirect",
            name="Evolution surface compounder redirect",
            description=(
                "Supervisor codex wakes and skill-route digest attachment redirect to "
                "capability compounder prove/compose instead of pin/cascade paperwork."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_evolution_route_redirect",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_evolution_route_redirect; '
                "r=builtin_evolution_route_redirect(); assert r['ok'] and r['pin_cascade_frozen']\""
            ),
            dependencies=("repo.import-health", "capability.ledger-inventory"),
            behavior_paths=(
                "src/blackhole_agent/evolution_route.py",
                "src/blackhole_agent/supervisor.py",
                "src/blackhole_agent/github_growth.py",
            ),
            capability_delta=(
                "Legacy evolution surfaces redirect to the compounder when the ledger is ready."
            ),
            tags=("bootstrap", "evolution-route"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.scout-gaps",
            name="Capability growth gap scout",
            description=(
                "Inspect the durable ledger for unproved capabilities and ranked "
                "composition-promotion opportunities without skill-route discovery."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_scout_gaps",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_scout_gaps; '
                "r=builtin_scout_gaps(); assert r['ok'] and isinstance(r.get('opportunities'), list)\""
            ),
            dependencies=("repo.import-health", "capability.ledger-inventory"),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Ledger growth opportunities are scannable as a first-class invocable capability."
            ),
            tags=("bootstrap", "compounder", "growth"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.growth-loop",
            name="Capability compounder growth loop",
            description=(
                "Scout the ledger, promote a ready multi-capability composition into a durable "
                "capability, then prove and run it — the closed compounding loop."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_growth_loop",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_growth_loop; '
                "r=builtin_growth_loop(); assert r['ok'] and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.scout-gaps",
                "unbound.milestone-gate",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "The compounder can grow itself by promoting compositions without skill-route machinery."
            ),
            tags=("bootstrap", "compounder", "growth"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
    ]
    for seed in seeds:
        if seed.id not in ledger.capabilities:
            register_capability(ledger, seed, replace=False)
        else:
            register_capability(ledger, seed, replace=True)
    return ledger


def ensure_seeded_ledger(repo_path: Path) -> tuple[Path, CapabilityLedger]:
    path = default_ledger_path(repo_path)
    ledger = load_ledger(path)
    before = set(ledger.capabilities)
    ledger = seed_bootstrap_capabilities(ledger)
    if set(ledger.capabilities) != before or not path.exists():
        save_ledger(path, ledger)
    else:
        # Still persist proof metadata updates only when caller asks; seeds already current.
        save_ledger(path, ledger)
    return path, ledger


def run_end_to_end_demo(
    repo_path: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
) -> dict[str, Any]:
    """Seed, prove, and compose bootstrap capabilities without skill-route imports."""

    path, ledger = ensure_seeded_ledger(repo_path)
    # Explicitly avoid importing skill_routing during the demo path.
    import_probe = builtin_repo_import_health()
    compose_ids = [
        "repo.import-health",
        "unbound.milestone-gate",
        "capability.ledger-inventory",
        "evolution.compounder-redirect",
    ]
    # Compose the bootstrap set that is present (redirect capability may be new).
    present = [item for item in compose_ids if item in ledger.capabilities]
    results = compose_capabilities(
        ledger,
        present,
        cwd=repo_path,
        command_runner=command_runner,
        timeout=timeout,
        prove_first=True,
    )
    save_ledger(path, ledger)
    ok = (
        bool(results)
        and all(item.ok for item in results)
        and len(results) == len(topological_order(ledger, present))
        and len(present) >= 3
    )
    return {
        "ok": ok,
        "ledger_path": str(path),
        "capability_count": len(ledger.capabilities),
        "composed": [item.to_dict() for item in results],
        "import_probe": import_probe,
        "used_skill_route_discovery": "skill_routing" in sys.modules
        or "blackhole_agent.skill_routing" in sys.modules,
    }
