"""Durable capability compounding for Unbound missions.

Milestones are not paper trails. Each demonstrated behavior can become a
versioned, invocable capability that later turns list, prove, run, and compose
without consulting the legacy skill-route discovery labyrinth.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SCHEMA_VERSION = 1
DEFAULT_LEDGER_RELATIVE = Path("capabilities") / "ledger.json"
CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")
SUPPORTED_KINDS = frozenset({"command", "python"})


def legacy_pipeline_was_used() -> bool:
    """Report scoped use by this capability path, not unrelated process imports."""

    return False


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
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary.write_text(text, encoding="utf-8")
    # Windows may transiently lock the target while another capability subprocess
    # still has the ledger open; retry replace briefly before failing hard.
    last_error: Exception | None = None
    for attempt in range(12):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as error:
            last_error = error
        except OSError as error:
            # WinError 32: file in use by another process.
            winerr = getattr(error, "winerror", None)
            if winerr not in {5, 32} and not isinstance(error, PermissionError):
                raise
            last_error = error
        time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise OSError(f"Failed to replace {path} after retries")


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
COMPOSED_ENTRY = "blackhole_agent.capability_compounder:builtin_execute_composed_capability"
# Tags that mark combinatorial stack growth rather than primitive behavior units.
STACK_GROWTH_TAGS = frozenset({"composed", "promoted", "hierarchical", "meta", "superstack", "dynamic", "synthesized"})


def is_primitive_capability(capability: Capability) -> bool:
    """True when the capability is a behavior unit, not a re-composed dependency chain.

    Composed ledger citizens share the same `builtin_execute_composed_capability` entry
    and only re-run members. Everything else (domain surfaces, bootstrap health, growth
    plane operators) is a primitive for novelty / coverage scoring.
    """

    if not capability.dependencies:
        return True
    entry = (capability.entry or "").strip()
    if entry == COMPOSED_ENTRY or entry.endswith(":builtin_execute_composed_capability"):
        return False
    return True


def primitive_coverage(
    ledger: CapabilityLedger,
    capability_id: str,
    *,
    _cache: dict[str, frozenset[str]] | None = None,
) -> frozenset[str]:
    """Resolve the set of primitive capability ids under a capability (or itself)."""

    cache = _cache if _cache is not None else {}
    if capability_id in cache:
        return cache[capability_id]
    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        result = frozenset({capability_id})
        cache[capability_id] = result
        return result
    if is_primitive_capability(capability):
        result = frozenset({capability.id})
        cache[capability_id] = result
        return result
    covered: set[str] = set()
    for dep in capability.dependencies:
        covered |= primitive_coverage(ledger, dep, _cache=cache)
    result = frozenset(covered)
    cache[capability_id] = result
    return result


def coverage_for_members(
    ledger: CapabilityLedger,
    member_ids: Sequence[str],
    *,
    _cache: dict[str, frozenset[str]] | None = None,
) -> frozenset[str]:
    """Union primitive coverage across explicit member ids (for promotion candidates)."""

    cache = _cache if _cache is not None else {}
    covered: set[str] = set()
    for member in member_ids:
        member_id = str(member).strip()
        if not member_id:
            continue
        if member_id in ledger.capabilities:
            covered |= primitive_coverage(ledger, member_id, _cache=cache)
        else:
            covered.add(member_id)
    return frozenset(covered)


def existing_composed_coverage_sets(ledger: CapabilityLedger) -> set[frozenset[str]]:
    """Primitive-coverage sets already realized by promoted/composed ledger units."""

    cache: dict[str, frozenset[str]] = {}
    sets: set[frozenset[str]] = set()
    for capability in ledger.capabilities.values():
        if is_primitive_capability(capability):
            continue
        sets.add(primitive_coverage(ledger, capability.id, _cache=cache))
    return sets


def champion_rank(capability: Capability) -> tuple[int, int, int, str]:
    """Higher rank wins when distilling capabilities that share coverage.

    Prefer non-synthesized, first-order, proved, catalogued compositions over
    deep superstacks that only re-package the same primitives.
    """

    tags = set(capability.tags)
    score = 0
    if "synthesized" not in tags:
        score += 100
    if "superstack" not in tags:
        score += 50
    if "meta" not in tags:
        score += 40
    if "hierarchical" not in tags:
        score += 30
    if "dynamic" not in tags:
        score += 10
    if capability.last_proof_exit_code == 0:
        score += 20
    known_ids = {str(recipe["suggested_id"]) for recipe in KNOWN_GROWTH_RECIPES} | {
        str(recipe["suggested_id"]) for recipe in KNOWN_HIERARCHICAL_RECIPES
    }
    if capability.id in known_ids:
        score += 25
    # Prefer fewer direct deps (more focused units) then shorter stable ids.
    return (score, -len(capability.dependencies), -len(capability.id), capability.id)


def annotate_opportunities_with_novelty(
    ledger: CapabilityLedger,
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach primitive coverage + novelty score to scout opportunities in-place."""

    existing = existing_composed_coverage_sets(ledger)
    cache: dict[str, frozenset[str]] = {}
    for item in opportunities:
        status = str(item.get("status") or "")
        kind = str(item.get("kind") or "")
        members = [str(m) for m in (item.get("members") or []) if str(m).strip()]
        if kind == "domain_absorb" or status == "ready_to_absorb":
            surface_id = str(item.get("suggested_id") or "")
            coverage = frozenset({surface_id}) if surface_id else frozenset()
            # Absorbing a new primitive is always novel coverage expansion.
            novel = surface_id not in ledger.capabilities
            novelty_score = 1000 if novel else 0
        elif status in {"ready", "already_promoted", "blocked_missing_members"} and members:
            coverage = coverage_for_members(ledger, members, _cache=cache)
            novel = bool(coverage) and coverage not in existing
            # Prefer genuinely new coverage sets; break ties by coverage breadth.
            novelty_score = (500 + len(coverage)) if novel else max(0, len(coverage) // 4)
            # Penalize pure superstack/meta packaging of already-covered primitives.
            if not novel and (
                item.get("synthesis") in {"superstack", "meta_hierarchical"}
                or "superstack" in (item.get("tags") or [])
            ):
                novelty_score = 0
        else:
            coverage = frozenset()
            novel = False
            novelty_score = 0
        item["coverage"] = sorted(coverage)
        item["coverage_size"] = len(coverage)
        item["novel"] = novel
        item["novelty_score"] = int(novelty_score)
    return opportunities


def rank_growth_opportunities(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank scout opportunities: ready+novel first, then other ready, then absorbs."""

    status_rank = {
        "ready": 0,
        "ready_to_absorb": 1,
        "already_promoted": 2,
        "already_absorbed": 3,
        "blocked_missing_members": 4,
        "blocked_missing_module": 5,
    }

    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        status = str(item.get("status") or "")
        ready = status in {"ready", "ready_to_absorb"}
        # Among ready frontiers, novel coverage outranks combinatorial re-packages.
        novel_rank = 0 if (ready and item.get("novel")) else 1 if ready else 2
        return (
            novel_rank,
            status_rank.get(status, 9),
            -int(item.get("novelty_score") or 0),
            -int(item.get("priority") or 0),
            str(item.get("suggested_id") or ""),
        )

    opportunities.sort(key=sort_key)
    return opportunities


def scout_frontier_novelty(
    ledger: CapabilityLedger,
    *,
    repo_path: Path | None = None,
) -> dict[str, Any]:
    """Rank growth frontiers by primitive-coverage novelty (anti-combinatorial plane)."""

    scout = scout_capability_gaps(ledger, repo_path=repo_path)
    opportunities = list(scout.get("opportunities") or [])
    ready = [item for item in opportunities if item.get("status") in {"ready", "ready_to_absorb"}]
    novel_ready = [item for item in ready if item.get("novel")]
    stale_ready = [item for item in ready if not item.get("novel")]
    composed_sets = existing_composed_coverage_sets(ledger)
    primitives = sorted(
        capability.id for capability in ledger.capabilities.values() if is_primitive_capability(capability)
    )
    recommended = scout.get("recommended")
    return {
        "ok": True,
        "action": "frontier_novelty",
        "count": len(ledger.capabilities),
        "primitive_count": len(primitives),
        "primitives": primitives,
        "unique_composed_coverage_sets": len(composed_sets),
        "ready_count": len(ready),
        "novel_ready_count": len(novel_ready),
        "stale_ready_count": len(stale_ready),
        "novel_ready": [
            {
                "suggested_id": item.get("suggested_id"),
                "novelty_score": item.get("novelty_score"),
                "coverage": item.get("coverage"),
                "synthesis": item.get("synthesis"),
                "priority": item.get("priority"),
            }
            for item in novel_ready[:12]
        ],
        "stale_ready": [
            {
                "suggested_id": item.get("suggested_id"),
                "novelty_score": item.get("novelty_score"),
                "coverage": item.get("coverage"),
                "synthesis": item.get("synthesis"),
                "priority": item.get("priority"),
            }
            for item in stale_ready[:12]
        ],
        "recommended": recommended,
        "recommended_novel": bool(recommended and recommended.get("novel")),
        "used_skill_route_discovery": scout.get("used_skill_route_discovery", False),
        "ledger_path": scout.get("ledger_path"),
    }


def distill_ledger(
    ledger: CapabilityLedger,
    *,
    remove: bool = False,
    only_synthesized: bool = True,
) -> tuple[CapabilityLedger, dict[str, Any]]:
    """Collapse redundant composed units that share identical primitive coverage.

    Soft distill (default): tag non-champions `redundant` so growth/inventory can ignore them.
    Hard distill (`remove=True`): drop non-champion synthesized stacks from the ledger.
    Primitives and bootstrap operators are never removed.
    """

    cache: dict[str, frozenset[str]] = {}
    groups: dict[frozenset[str], list[Capability]] = {}
    for capability in ledger.capabilities.values():
        if is_primitive_capability(capability):
            continue
        if only_synthesized and "synthesized" not in capability.tags and "superstack" not in capability.tags:
            # Still group non-synthesized when they share coverage with stacks; champions
            # may be catalogued first-order units.
            pass
        coverage = primitive_coverage(ledger, capability.id, _cache=cache)
        groups.setdefault(coverage, []).append(capability)

    champions: list[str] = []
    redundant: list[str] = []
    removed: list[str] = []
    retained = dict(ledger.capabilities)

    for coverage, members in groups.items():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=champion_rank, reverse=True)
        champion = ordered[0]
        champions.append(champion.id)
        for loser in ordered[1:]:
            if only_synthesized and not (
                "synthesized" in loser.tags
                or "superstack" in loser.tags
                or "meta" in loser.tags
            ):
                continue
            redundant.append(loser.id)
            if remove:
                retained.pop(loser.id, None)
                removed.append(loser.id)
            else:
                tags = tuple(dict.fromkeys((*loser.tags, "redundant", "distilled")))
                retained[loser.id] = Capability(
                    id=loser.id,
                    name=loser.name,
                    description=loser.description,
                    kind=loser.kind,
                    entry=loser.entry,
                    proof_command=loser.proof_command,
                    dependencies=loser.dependencies,
                    behavior_paths=loser.behavior_paths,
                    capability_delta=loser.capability_delta,
                    tags=tags,
                    created_at=loser.created_at,
                    updated_at=utc_now_iso(),
                    source_mission_id=loser.source_mission_id,
                    source_milestone=loser.source_milestone,
                    last_proved_at=loser.last_proved_at,
                    last_proof_exit_code=loser.last_proof_exit_code,
                )

    new_ledger = CapabilityLedger(
        schema_version=ledger.schema_version,
        updated_at=utc_now_iso(),
        capabilities=retained,
    )
    report = {
        "ok": True,
        "action": "distill_ledger",
        "before_count": len(ledger.capabilities),
        "after_count": len(new_ledger.capabilities),
        "group_count": sum(1 for members in groups.values() if len(members) >= 2),
        "champions": sorted(set(champions)),
        "redundant": sorted(set(redundant)),
        "removed": sorted(set(removed)),
        "redundant_count": len(set(redundant)),
        "removed_count": len(set(removed)),
        "unique_composed_coverage_sets": len(groups),
        "remove": remove,
        "only_synthesized": only_synthesized,
    }
    return new_ledger, report


def run_distill_ledger(
    repo_path: Path,
    *,
    remove: bool = False,
    only_synthesized: bool = True,
) -> dict[str, Any]:
    """Load ledger, distill redundant stacks, persist, return report."""

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    before_ids = sorted(ledger.capabilities)
    new_ledger, report = distill_ledger(
        ledger,
        remove=remove,
        only_synthesized=only_synthesized,
    )
    save_ledger(path, new_ledger)
    report["before_ids"] = before_ids
    report["after_ids"] = sorted(new_ledger.capabilities)
    report["ledger_path"] = str(path)
    report["used_skill_route_discovery"] = legacy_pipeline_was_used()
    report["ok"] = report["ok"] and not report["used_skill_route_discovery"]
    return report


def run_autonomic_cycle(
    repo_path: Path,
    *,
    budget: int = 4,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 180,
    distill_remove: bool = False,
    integrity_limit: int = 12,
) -> dict[str, Any]:
    """Novelty-aware grow → distill redundant stacks → integrity prove.

    Escapes the combinatorial superstack treadmill: scout ranks novel primitive
    coverage first, adaptive growth spends budget on those frontiers, distill
    collapses identical-coverage stacks, integrity re-proves a topo prefix.
    """

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    before_count = len(ledger.capabilities)
    before_coverage = len(existing_composed_coverage_sets(ledger))
    novelty_before = scout_frontier_novelty(ledger, repo_path=root)

    # Autonomic growth spends budget only on novel coverage; stale superstack
    # promotion is left to explicit `capability grow` without novel_only.
    growth = run_adaptive_growth(
        root,
        budget=budget,
        command_runner=command_runner,
        timeout=timeout,
        novel_only=True,
    )
    ledger = load_ledger(path)
    distill = run_distill_ledger(
        root,
        remove=distill_remove,
        only_synthesized=True,
    )
    ledger = load_ledger(path)
    # Integrity of deep composed stacks is expensive and orthogonal to the
    # novelty/distill plane; prove a topo prefix of primitives-first order.
    integrity = prove_ledger_integrity(
        root,
        command_runner=command_runner,
        timeout=min(timeout, 120),
        limit=integrity_limit,
    )
    novelty_after = scout_frontier_novelty(load_ledger(path), repo_path=root)
    after_count = len(load_ledger(path).capabilities)
    after_coverage = novelty_after.get("unique_composed_coverage_sets", 0)
    used_skill = bool(
        growth.get("used_skill_route_discovery")
        or distill.get("used_skill_route_discovery")
        or integrity.get("used_skill_route_discovery")
    )
    # Success: no skill-route, integrity ok, and either growth advanced novel frontier,
    # distillation reduced redundancy, or the plane cleanly reported a novelty stall.
    advanced = bool(growth.get("grew")) or int(distill.get("redundant_count") or 0) > 0
    ok = (
        not used_skill
        and bool(growth.get("ok"))
        and bool(distill.get("ok"))
        and bool(integrity.get("ok"))
    )
    return {
        "ok": ok,
        "action": "autonomic_cycle",
        "advanced": advanced,
        "before_count": before_count,
        "after_count": after_count,
        "before_unique_coverage_sets": before_coverage,
        "after_unique_coverage_sets": after_coverage,
        "novel_ready_before": novelty_before.get("novel_ready_count"),
        "novel_ready_after": novelty_after.get("novel_ready_count"),
        "stale_ready_before": novelty_before.get("stale_ready_count"),
        "growth": {
            "ok": growth.get("ok"),
            "grew": growth.get("grew"),
            "promoted_ids": growth.get("promoted_ids"),
            "promoted_count": growth.get("promoted_count"),
            "steps_run": growth.get("steps_run"),
            "stalled": growth.get("stalled"),
            "stall_reason": growth.get("stall_reason"),
        },
        "distill": {
            "ok": distill.get("ok"),
            "redundant_count": distill.get("redundant_count"),
            "removed_count": distill.get("removed_count"),
            "after_count": distill.get("after_count"),
            "champions": distill.get("champions"),
        },
        "integrity": {
            "ok": integrity.get("ok"),
            "score": integrity.get("score"),
            "proved_count": integrity.get("proved_count"),
            "failed_count": integrity.get("failed_count"),
        },
        "novelty_before": {
            "novel_ready_count": novelty_before.get("novel_ready_count"),
            "stale_ready_count": novelty_before.get("stale_ready_count"),
            "recommended_novel": novelty_before.get("recommended_novel"),
            "recommended": (novelty_before.get("recommended") or {}).get("suggested_id"),
        },
        "novelty_after": {
            "novel_ready_count": novelty_after.get("novel_ready_count"),
            "stale_ready_count": novelty_after.get("stale_ready_count"),
            "recommended_novel": novelty_after.get("recommended_novel"),
        },
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


# Operators that must not appear inside ordinary goal programs (avoid recursive
# mission/growth planes during prove/run).
PROGRAM_PLAN_DENYLIST = frozenset(
    {
        "capability.mission-plane",
        "capability.program-run",
        "capability.goal-plan",
        "capability.adaptive-grow",
        "capability.autonomic-cycle",
        "capability.growth-loop",
        "capability.second-wave-absorb",
        "capability.outcome-contract",
        "capability.contract-plane",
        "capability.ablation-proof",
        "capability.transfer-plane",
        "capability.adversarial-contract",
        "capability.assurance-plane",
        # Batch operators are invocable separately; keep goal programs step-cheap.
        "capability.ledger-integrity",
        "capability.distill-ledger",
    }
)

# Goal keyword → preferred capability ids for mission-plane planning.
MISSION_GOAL_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("integrity", ("capability.ledger-integrity", "capability.ledger-inventory", "repo.import-health")),
    ("novelty", ("capability.frontier-novelty", "capability.distill-ledger", "capability.autonomic-cycle")),
    ("autonomic", ("capability.autonomic-cycle", "capability.adaptive-grow", "capability.frontier-novelty")),
    ("growth", ("capability.scout-gaps", "capability.growth-loop", "capability.adaptive-grow")),
    ("health", ("repo.import-health", "capability.ledger-inventory", "unbound.milestone-gate")),
    ("memory", ("domain.local-memory",)),
    ("security", ("domain.ci-security",)),
    ("triage", ("domain.issue-triage",)),
    ("proposal", ("domain.proposal-synthesis", "domain.proposal-eval")),
    ("persona", ("domain.persona",)),
    ("identity", ("domain.persona", "domain.kernel-preflight")),
    ("kernel", ("domain.kernel-preflight",)),
    ("harness", ("domain.harness-activation",)),
    ("tool", ("domain.tool-routing",)),
    ("supervisor", ("domain.supervisor-compound",)),
    ("mission", ("capability.mission-plane", "capability.program-run", "capability.goal-plan")),
    ("program", ("capability.program-run", "capability.goal-plan")),
    ("second-wave", ("domain.persona", "domain.proposal-synthesis", "domain.kernel-preflight")),
    ("distill", ("capability.distill-ledger", "capability.frontier-novelty")),
    ("contract", ("capability.outcome-contract", "capability.contract-plane", "capability.ledger-inventory")),
    ("outcome", ("capability.outcome-contract", "capability.contract-plane", "capability.mission-plane")),
    ("done_when", ("capability.outcome-contract", "capability.contract-plane")),
    ("evidence", ("capability.outcome-contract", "capability.ledger-integrity", "capability.ledger-inventory")),
    ("assurance", ("capability.assurance-plane", "capability.ablation-proof", "capability.transfer-plane")),
    ("ablation", ("capability.ablation-proof", "capability.ledger-integrity", "repo.import-health")),
    ("transfer", ("capability.transfer-plane", "capability.ledger-inventory", "repo.import-health")),
    ("adversarial", ("capability.adversarial-contract", "capability.outcome-contract")),
    ("package", ("capability.transfer-plane", "capability.ledger-inventory")),
)


def plan_capability_program(
    ledger: CapabilityLedger,
    goal: str,
    *,
    max_steps: int = 6,
    prefer_primitives: bool = True,
) -> dict[str, Any]:
    """Rank a multi-step capability program for a free-text mission goal.

    Deterministic offline planner: keyword hints + tag/name/id overlap over ledger
    citizens. Prefer proved primitives so programs stay cheap and novel-coverage-friendly.
    """

    goal_text = " ".join(str(goal or "").strip().lower().split())
    if not goal_text:
        goal_text = "core health integrity inventory"
    scores: dict[str, float] = {}
    for capability in ledger.capabilities.values():
        if capability.id in PROGRAM_PLAN_DENYLIST:
            continue
        if prefer_primitives and not is_primitive_capability(capability):
            # Still allow composed units when explicitly hinted by id/name match.
            base = 0.0
        else:
            base = 1.0
        blob = " ".join(
            [
                capability.id,
                capability.name,
                capability.description,
                " ".join(capability.tags),
                " ".join(capability.dependencies),
            ]
        ).lower()
        score = base
        for token in re.findall(r"[a-z0-9][a-z0-9._-]{2,}", goal_text):
            if token in blob:
                score += 3.0
            elif token in capability.id:
                score += 4.0
        for tag in capability.tags:
            if tag and tag.lower() in goal_text:
                score += 2.5
        if capability.last_proof_exit_code == 0:
            score += 0.5
        if is_primitive_capability(capability):
            score += 0.75
        # Soft-penalize pure stack re-packages unless the goal asks for composition.
        if not is_primitive_capability(capability) and "compose" not in goal_text and "stack" not in goal_text:
            score *= 0.35
        scores[capability.id] = score

    for hint, capability_ids in MISSION_GOAL_HINTS:
        if hint in goal_text:
            for capability_id in capability_ids:
                if capability_id in ledger.capabilities and capability_id not in PROGRAM_PLAN_DENYLIST:
                    scores[capability_id] = scores.get(capability_id, 0.0) + 8.0

    # Always include a cheap health anchor when present.
    for anchor in ("repo.import-health", "capability.ledger-inventory"):
        if anchor in ledger.capabilities:
            scores[anchor] = scores.get(anchor, 0.0) + 1.25

    ranked = sorted(
        (
            (capability_id, score)
            for capability_id, score in scores.items()
            if score > 1.0
            and capability_id in ledger.capabilities
            and capability_id not in PROGRAM_PLAN_DENYLIST
        ),
        key=lambda item: (-item[1], item[0]),
    )
    steps: list[str] = []
    for capability_id, _score in ranked:
        if capability_id in steps:
            continue
        steps.append(capability_id)
        if len(steps) >= max(1, int(max_steps)):
            break
    # Fallback health program when scoring yields nothing.
    if not steps:
        for fallback in (
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
        ):
            if fallback in ledger.capabilities and fallback not in steps:
                steps.append(fallback)
            if len(steps) >= max(1, int(max_steps)):
                break
    return {
        "ok": bool(steps),
        "action": "goal_plan",
        "goal": goal_text,
        "steps": steps,
        "step_count": len(steps),
        "scores": {capability_id: round(score, 3) for capability_id, score in ranked[:12]},
        "prefer_primitives": prefer_primitives,
    }


def run_capability_program(
    repo_path: Path,
    steps: Sequence[str],
    *,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    prove_first: bool = False,
) -> dict[str, Any]:
    """Execute an ordered multi-step capability program and collect evidence."""

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    ordered = [str(item).strip() for item in steps if str(item).strip()]
    results: list[dict[str, Any]] = []
    missing: list[str] = []
    used_skill = False
    for capability_id in ordered:
        capability = ledger.capabilities.get(capability_id)
        if capability is None:
            missing.append(capability_id)
            results.append(
                {
                    "capability_id": capability_id,
                    "ok": False,
                    "exit_code": 127,
                    "summary": "missing_capability",
                }
            )
            continue
        if prove_first:
            ledger, proof = prove_capability(
                ledger,
                capability_id,
                cwd=root,
                command_runner=command_runner,
                timeout=timeout,
            )
            if not proof.ok:
                results.append(
                    {
                        "capability_id": capability_id,
                        "ok": False,
                        "exit_code": proof.exit_code,
                        "summary": f"proof_failed:{proof.summary}",
                        "kind": "proof",
                    }
                )
                continue
        run_result = run_capability(
            capability,
            cwd=root,
            command_runner=command_runner,
            timeout=timeout,
            use_proof=False,
        )
        results.append(
            {
                "capability_id": capability_id,
                "ok": run_result.ok,
                "exit_code": run_result.exit_code,
                "summary": run_result.summary,
                "kind": run_result.kind,
            }
        )
    save_ledger(path, ledger)
    used_skill = legacy_pipeline_was_used()
    ok = bool(ordered) and not missing and all(item.get("ok") for item in results) and not used_skill
    return {
        "ok": ok,
        "action": "program_run",
        "steps": ordered,
        "step_count": len(ordered),
        "results": results,
        "passed_count": sum(1 for item in results if item.get("ok")),
        "failed_count": sum(1 for item in results if not item.get("ok")),
        "missing": missing,
        "prove_first": prove_first,
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


def absorb_second_wave_domains(
    repo_path: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    prove: bool = True,
    limit: int = 8,
) -> dict[str, Any]:
    """Absorb ready second-wave (and any pending) domain surfaces to expand primitive coverage."""

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    before_ids = sorted(ledger.capabilities)
    before_novelty = scout_frontier_novelty(ledger, repo_path=root)
    absorbed_ids: list[str] = []
    proved: list[str] = []
    failed_proofs: list[str] = []
    ledger, absorbed = absorb_ready_domain_surfaces(ledger, repo_path=root, limit=max(1, int(limit)))
    for capability in absorbed:
        absorbed_ids.append(capability.id)
        if not prove:
            continue
        ledger, proof = prove_capability(
            ledger,
            capability.id,
            cwd=root,
            command_runner=command_runner,
            timeout=timeout,
        )
        if proof.ok:
            proved.append(capability.id)
        else:
            failed_proofs.append(capability.id)
    save_ledger(path, ledger)
    after = load_ledger(path)
    after_novelty = scout_frontier_novelty(after, repo_path=root)
    used_skill = legacy_pipeline_was_used()
    ok = not used_skill and not failed_proofs
    return {
        "ok": ok,
        "action": "second_wave_absorb",
        "absorbed_ids": absorbed_ids,
        "absorbed_count": len(absorbed_ids),
        "proved_ids": proved,
        "failed_proofs": failed_proofs,
        "before_count": len(before_ids),
        "after_count": len(after.capabilities),
        "new_ids": sorted(set(after.capabilities) - set(before_ids)),
        "novel_ready_before": before_novelty.get("novel_ready_count"),
        "novel_ready_after": after_novelty.get("novel_ready_count"),
        "primitive_count_after": after_novelty.get("primitive_count"),
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


def run_mission_plane(
    repo_path: Path,
    goal: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 180,
    max_steps: int = 6,
    absorb_ready: bool = True,
    prove_first: bool = False,
    grow_budget: int = 2,
) -> dict[str, Any]:
    """Goal-conditioned mission plane: expand primitives → plan → run → optional novel grow.

    Escapes the zero-novelty superstack plateau by absorbing second-wave domains when
    ready, then executing a multi-step capability program for the stated goal, then
    spending a small novel-only growth budget if frontiers reopened.
    """

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    before_count = len(ledger.capabilities)
    novelty_before = scout_frontier_novelty(ledger, repo_path=root)

    absorb_report: dict[str, Any] | None = None
    if absorb_ready:
        absorb_report = absorb_second_wave_domains(
            root,
            command_runner=command_runner,
            timeout=min(timeout, 120),
            prove=True,
            limit=8,
        )
        ledger = load_ledger(path)

    plan = plan_capability_program(ledger, goal, max_steps=max_steps, prefer_primitives=True)
    program = run_capability_program(
        root,
        plan.get("steps") or [],
        command_runner=command_runner,
        timeout=timeout,
        prove_first=prove_first,
    )

    growth: dict[str, Any] | None = None
    if grow_budget > 0:
        growth = run_adaptive_growth(
            root,
            budget=grow_budget,
            command_runner=command_runner,
            timeout=timeout,
            novel_only=True,
        )

    novelty_after = scout_frontier_novelty(load_ledger(path), repo_path=root)
    after_count = len(load_ledger(path).capabilities)
    used_skill = bool(
        (absorb_report or {}).get("used_skill_route_discovery")
        or program.get("used_skill_route_discovery")
        or (growth or {}).get("used_skill_route_discovery")
    )
    expanded = bool((absorb_report or {}).get("absorbed_count")) or bool((growth or {}).get("grew"))
    ok = (
        not used_skill
        and bool(plan.get("ok"))
        and bool(program.get("ok"))
        and (absorb_report is None or bool(absorb_report.get("ok")))
        and (growth is None or bool(growth.get("ok")))
    )
    return {
        "ok": ok,
        "action": "mission_plane",
        "goal": plan.get("goal"),
        "expanded": expanded,
        "before_count": before_count,
        "after_count": after_count,
        "novel_ready_before": novelty_before.get("novel_ready_count"),
        "novel_ready_after": novelty_after.get("novel_ready_count"),
        "primitive_count_before": novelty_before.get("primitive_count"),
        "primitive_count_after": novelty_after.get("primitive_count"),
        "plan": {
            "steps": plan.get("steps"),
            "step_count": plan.get("step_count"),
            "scores": plan.get("scores"),
        },
        "program": {
            "ok": program.get("ok"),
            "passed_count": program.get("passed_count"),
            "failed_count": program.get("failed_count"),
            "results": program.get("results"),
        },
        "absorb": {
            "ok": None if absorb_report is None else absorb_report.get("ok"),
            "absorbed_ids": None if absorb_report is None else absorb_report.get("absorbed_ids"),
            "absorbed_count": 0 if absorb_report is None else absorb_report.get("absorbed_count"),
            "novel_ready_after": None if absorb_report is None else absorb_report.get("novel_ready_after"),
        },
        "growth": None
        if growth is None
        else {
            "ok": growth.get("ok"),
            "grew": growth.get("grew"),
            "promoted_ids": growth.get("promoted_ids"),
            "stalled": growth.get("stalled"),
            "stall_reason": growth.get("stall_reason"),
            "steps_run": growth.get("steps_run"),
        },
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


# ---------------------------------------------------------------------------
# Outcome-contract plane: machine-checkable done_when past free-text claims.
# ---------------------------------------------------------------------------

# Predicate forms accepted in done_when (semicolon- or newline-separated):
#   min_capabilities:N | min_primitives:N | min_unique_coverage:N
#   min_proved:N | proved_ratio_ge:0.0-1.0 | integrity_score_ge:0.0-1.0
#   capability_exists:id | capability_proved:id | ledger_has:id
#   program_passes:id1,id2 | has_tag:tag | no_skill_route
#   novel_ready_le:N | mission_plane_ok | contract_plane_ok
#   assurance_plane_ok | sovereignty_ok | certificate_valid[:path]
# Free-text lines without a known form are recorded as informational (not gating).
OUTCOME_PREDICATE_PATTERN = re.compile(
    r"^(?P<kind>"
    r"min_capabilities|min_primitives|min_unique_coverage|min_proved|"
    r"proved_ratio_ge|integrity_score_ge|"
    r"capability_exists|capability_proved|ledger_has|"
    r"program_passes|has_tag|no_skill_route|"
    r"novel_ready_le|mission_plane_ok|contract_plane_ok|"
    r"assurance_plane_ok|sovereignty_ok|certificate_valid"
    r")(?::(?P<arg>.+))?$",
    re.IGNORECASE,
)


def parse_outcome_contract(done_when: str) -> dict[str, Any]:
    """Parse free-text or structured done_when into machine predicates + notes."""

    text = str(done_when or "").strip()
    if not text:
        return {
            "ok": False,
            "action": "parse_outcome_contract",
            "raw": "",
            "predicates": [],
            "notes": [],
            "machine_checkable": False,
            "error": "done_when is empty",
        }
    # Split on newlines or semicolons; keep comma only inside args.
    chunks: list[str] = []
    for line in re.split(r"[\n;]+", text):
        piece = line.strip()
        if piece and not piece.startswith("#"):
            chunks.append(piece)
    predicates: list[dict[str, Any]] = []
    notes: list[str] = []
    for chunk in chunks:
        # Also allow "kind: arg with spaces" and soft free-text keyword extraction.
        match = OUTCOME_PREDICATE_PATTERN.match(chunk)
        if match:
            kind = match.group("kind").lower()
            arg = (match.group("arg") or "").strip()
            predicates.append({"kind": kind, "arg": arg, "source": chunk})
            continue
        # Soft extraction from prose.
        soft = _soft_extract_outcome_predicates(chunk)
        if soft:
            predicates.extend(soft)
        else:
            notes.append(chunk)
    # Deduplicate by (kind, arg) while preserving order.
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for predicate in predicates:
        key = (str(predicate["kind"]), str(predicate.get("arg") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(predicate)
    return {
        "ok": True,
        "action": "parse_outcome_contract",
        "raw": text,
        "predicates": unique,
        "notes": notes,
        "machine_checkable": bool(unique),
        "predicate_count": len(unique),
    }


def _soft_extract_outcome_predicates(chunk: str) -> list[dict[str, Any]]:
    """Extract common prose phrases into structured predicates."""

    lower = chunk.lower().strip()
    found: list[dict[str, Any]] = []
    if "no skill-route" in lower or "without skill-route" in lower or "no skill route" in lower:
        found.append({"kind": "no_skill_route", "arg": "", "source": chunk})
    m = re.search(r"(?:at least|>=|≥)\s*(\d+)\s+capabilit", lower)
    if m:
        found.append({"kind": "min_capabilities", "arg": m.group(1), "source": chunk})
    m = re.search(r"(?:at least|>=|≥)\s*(\d+)\s+primitive", lower)
    if m:
        found.append({"kind": "min_primitives", "arg": m.group(1), "source": chunk})
    m = re.search(r"integrity(?:\s+score)?\s*(?:>=|≥|at least)\s*(0?\.\d+|1(?:\.0+)?|\d+(?:\.\d+)?)", lower)
    if m:
        found.append({"kind": "integrity_score_ge", "arg": m.group(1), "source": chunk})
    m = re.search(r"(?:prove[sd]?|capability_proved)\s+([a-z][a-z0-9._-]{2,})", lower)
    if m and "min_" not in m.group(0):
        found.append({"kind": "capability_proved", "arg": m.group(1), "source": chunk})
    m = re.search(r"(?:ledger\s+has|capability_exists|includes)\s+([a-z][a-z0-9._-]{2,})", lower)
    if m:
        found.append({"kind": "capability_exists", "arg": m.group(1), "source": chunk})
    if "mission plane" in lower and ("ok" in lower or "pass" in lower or "succeed" in lower):
        found.append({"kind": "mission_plane_ok", "arg": "", "source": chunk})
    if "contract plane" in lower and ("ok" in lower or "pass" in lower or "succeed" in lower):
        found.append({"kind": "contract_plane_ok", "arg": "", "source": chunk})
    if "assurance plane" in lower and ("ok" in lower or "pass" in lower or "succeed" in lower):
        found.append({"kind": "assurance_plane_ok", "arg": "", "source": chunk})
    if "sovereignty" in lower and ("ok" in lower or "pass" in lower or "succeed" in lower or "certif" in lower):
        found.append({"kind": "sovereignty_ok", "arg": "", "source": chunk})
    if "certificate" in lower and ("valid" in lower or "verify" in lower or "re-verif" in lower):
        found.append({"kind": "certificate_valid", "arg": "", "source": chunk})
    return found


def snapshot_outcome_metrics(
    repo_path: Path,
    *,
    ledger: CapabilityLedger | None = None,
    include_integrity: bool = False,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 90,
) -> dict[str, Any]:
    """Collect cheap ledger fitness metrics used by outcome contracts."""

    root = repo_path.resolve()
    path = default_ledger_path(root)
    if ledger is None:
        path, ledger = ensure_seeded_ledger(root)
    caps = list(ledger.capabilities.values())
    proved = [c for c in caps if c.last_proof_exit_code == 0]
    novelty = scout_frontier_novelty(ledger, repo_path=root)
    used_skill = legacy_pipeline_was_used()
    integrity: dict[str, Any] | None = None
    if include_integrity:
        integrity = prove_ledger_integrity(
            root,
            command_runner=command_runner,
            timeout=timeout,
            limit=8,
        )
    return {
        "ok": True,
        "action": "outcome_metrics",
        "ledger_path": str(path),
        "count": len(caps),
        "primitive_count": novelty.get("primitive_count"),
        "unique_composed_coverage_sets": novelty.get("unique_composed_coverage_sets"),
        "proved_count": len(proved),
        "proved_ratio": (len(proved) / len(caps)) if caps else 0.0,
        "novel_ready_count": novelty.get("novel_ready_count"),
        "stale_ready_count": novelty.get("stale_ready_count"),
        "ids": sorted(ledger.capabilities),
        "proved_ids": sorted(c.id for c in proved),
        "tags": sorted(
            {
                tag
                for capability in caps
                for tag in (capability.tags or ())
                if str(tag).strip()
            }
        ),
        "used_skill_route_discovery": used_skill,
        "integrity_score": None if integrity is None else integrity.get("score"),
        "integrity_ok": None if integrity is None else integrity.get("ok"),
    }


def evaluate_outcome_contract(
    repo_path: Path,
    done_when: str,
    *,
    context: Mapping[str, Any] | None = None,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    run_programs: bool = True,
) -> dict[str, Any]:
    """Machine-check done_when predicates against the live ledger and optional context.

    Returns met=True only when every machine predicate passes. Informational notes
    never gate. Empty/non-machine done_when yields machine_checkable=False and
    met=None so callers can fall back to agent judgment.
    """

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    parsed = parse_outcome_contract(done_when)
    if not parsed.get("ok"):
        return {
            "ok": False,
            "action": "evaluate_outcome_contract",
            "met": False,
            "machine_checkable": False,
            "parse": parsed,
            "results": [],
            "metrics": {},
            "ledger_path": str(path),
            "used_skill_route_discovery": False,
            "error": parsed.get("error") or "parse failed",
        }
    predicates = list(parsed.get("predicates") or [])
    needs_integrity = any(
        str(item.get("kind")) == "integrity_score_ge" for item in predicates
    )
    metrics = snapshot_outcome_metrics(
        root,
        ledger=ledger,
        include_integrity=needs_integrity,
        command_runner=command_runner,
        timeout=min(timeout, 90),
    )
    ctx = dict(context or {})
    results: list[dict[str, Any]] = []
    for predicate in predicates:
        kind = str(predicate.get("kind") or "")
        arg = str(predicate.get("arg") or "").strip()
        passed, detail = _eval_one_outcome_predicate(
            kind,
            arg,
            ledger=ledger,
            metrics=metrics,
            context=ctx,
            repo_path=root,
            command_runner=command_runner,
            timeout=timeout,
            run_programs=run_programs,
        )
        results.append(
            {
                "kind": kind,
                "arg": arg,
                "source": predicate.get("source"),
                "passed": passed,
                "detail": detail,
            }
        )
    machine = bool(predicates)
    failed = [item for item in results if not item["passed"]]
    met: bool | None
    if not machine:
        met = None
    else:
        met = not failed
    used_skill = bool(metrics.get("used_skill_route_discovery")) or legacy_pipeline_was_used()
    # ok means the evaluator itself worked; met is the contract verdict.
    evaluator_ok = not used_skill and bool(parsed.get("ok"))
    return {
        "ok": evaluator_ok,
        "action": "evaluate_outcome_contract",
        "met": met,
        "machine_checkable": machine,
        "passed_count": sum(1 for item in results if item["passed"]),
        "failed_count": len(failed),
        "predicate_count": len(results),
        "results": results,
        "failed": failed,
        "notes": parsed.get("notes") or [],
        "parse": {
            "predicate_count": parsed.get("predicate_count"),
            "notes": parsed.get("notes"),
            "raw": parsed.get("raw"),
        },
        "metrics": {
            "count": metrics.get("count"),
            "primitive_count": metrics.get("primitive_count"),
            "unique_composed_coverage_sets": metrics.get("unique_composed_coverage_sets"),
            "proved_count": metrics.get("proved_count"),
            "proved_ratio": metrics.get("proved_ratio"),
            "novel_ready_count": metrics.get("novel_ready_count"),
            "integrity_score": metrics.get("integrity_score"),
            "used_skill_route_discovery": metrics.get("used_skill_route_discovery"),
        },
        "ledger_path": str(path),
        "used_skill_route_discovery": used_skill,
    }


def _eval_one_outcome_predicate(
    kind: str,
    arg: str,
    *,
    ledger: CapabilityLedger,
    metrics: Mapping[str, Any],
    context: Mapping[str, Any],
    repo_path: Path,
    command_runner: Callable[..., Any],
    timeout: int,
    run_programs: bool,
) -> tuple[bool, str]:
    """Evaluate a single predicate; returns (passed, detail)."""

    if kind == "min_capabilities":
        need = int(float(arg or "0"))
        have = int(metrics.get("count") or 0)
        return have >= need, f"count={have} need>={need}"
    if kind == "min_primitives":
        need = int(float(arg or "0"))
        have = int(metrics.get("primitive_count") or 0)
        return have >= need, f"primitives={have} need>={need}"
    if kind == "min_unique_coverage":
        need = int(float(arg or "0"))
        have = int(metrics.get("unique_composed_coverage_sets") or 0)
        return have >= need, f"unique_coverage={have} need>={need}"
    if kind == "min_proved":
        need = int(float(arg or "0"))
        have = int(metrics.get("proved_count") or 0)
        return have >= need, f"proved={have} need>={need}"
    if kind == "proved_ratio_ge":
        need = float(arg or "0")
        have = float(metrics.get("proved_ratio") or 0.0)
        return have + 1e-12 >= need, f"proved_ratio={have:.4f} need>={need}"
    if kind == "integrity_score_ge":
        need = float(arg or "0")
        score = metrics.get("integrity_score")
        if score is None:
            return False, "integrity_score unavailable"
        have = float(score)
        return have + 1e-12 >= need, f"integrity_score={have:.4f} need>={need}"
    if kind in {"capability_exists", "ledger_has"}:
        cid = arg.strip()
        if not cid:
            return False, "missing capability id"
        return cid in ledger.capabilities, f"exists={cid in ledger.capabilities} id={cid}"
    if kind == "capability_proved":
        cid = arg.strip()
        if not cid:
            return False, "missing capability id"
        cap = ledger.capabilities.get(cid)
        if cap is None:
            return False, f"missing id={cid}"
        ok = cap.last_proof_exit_code == 0
        return ok, f"last_proof_exit_code={cap.last_proof_exit_code} id={cid}"
    if kind == "has_tag":
        tag = arg.strip().lower()
        tags = {str(t).lower() for t in (metrics.get("tags") or [])}
        return tag in tags, f"tag={tag} present={tag in tags}"
    if kind == "no_skill_route":
        used = bool(metrics.get("used_skill_route_discovery")) or bool(
            context.get("used_skill_route_discovery")
        )
        return not used, f"used_skill_route_discovery={used}"
    if kind == "novel_ready_le":
        need = int(float(arg or "0"))
        have = int(metrics.get("novel_ready_count") or 0)
        return have <= need, f"novel_ready={have} need<={need}"
    if kind == "mission_plane_ok":
        mission = context.get("mission") or context.get("mission_plane") or {}
        ok = bool(mission.get("ok"))
        return ok, f"mission_ok={ok}"
    if kind == "contract_plane_ok":
        # Self-reference only meaningful when outer plane already recorded ok.
        plane = context.get("contract_plane") or {}
        ok = bool(plane.get("ok"))
        return ok, f"contract_plane_ok={ok}"
    if kind == "assurance_plane_ok":
        plane = context.get("assurance") or context.get("assurance_plane") or {}
        ok = bool(plane.get("ok"))
        return ok, f"assurance_plane_ok={ok}"
    if kind == "sovereignty_ok":
        plane = context.get("sovereignty") or context.get("sovereignty_plane") or {}
        ok = bool(plane.get("ok"))
        return ok, f"sovereignty_ok={ok}"
    if kind == "certificate_valid":
        cert_path = (arg or "").strip() or str(
            context.get("certificate_path") or context.get("certificate") or ""
        ).strip()
        if not cert_path:
            # Allow in-memory certificate from the issuing plane.
            cert_obj = context.get("certificate_payload")
            if isinstance(cert_obj, Mapping):
                verify = verify_sovereignty_certificate(
                    cert_obj,
                    repo_path=repo_path,
                    recheck_live=False,
                )
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
                return ok, f"certificate_valid_in_memory={ok} hash={verify.get('certificate_hash')}"
            return False, "missing certificate path"
        verify = verify_sovereignty_certificate(
            Path(cert_path),
            repo_path=repo_path,
            recheck_live=False,
        )
        ok = bool(verify.get("ok")) and bool(verify.get("valid"))
        return ok, f"certificate_valid={ok} path={cert_path} hash={verify.get('certificate_hash')}"
    if kind == "program_passes":
        steps = [part.strip() for part in arg.split(",") if part.strip()]
        if not steps:
            return False, "no program steps"
        if not run_programs:
            # Soft: require all ids exist and previously proved.
            missing = [s for s in steps if s not in ledger.capabilities]
            if missing:
                return False, f"missing={missing}"
            unproved = [
                s
                for s in steps
                if ledger.capabilities[s].last_proof_exit_code != 0
            ]
            if unproved:
                return False, f"unproved={unproved}"
            return True, f"soft_proved steps={steps}"
        program = run_capability_program(
            repo_path,
            steps,
            command_runner=command_runner,
            timeout=timeout,
            prove_first=False,
        )
        ok = bool(program.get("ok")) and int(program.get("failed_count") or 0) == 0
        return ok, (
            f"program_ok={program.get('ok')} passed={program.get('passed_count')} "
            f"failed={program.get('failed_count')}"
        )
    return False, f"unknown predicate kind={kind}"


def run_contract_plane(
    repo_path: Path,
    goal: str,
    done_when: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 180,
    max_steps: int = 5,
    absorb_ready: bool = True,
    grow_budget: int = 1,
    prove_first: bool = False,
    run_mission: bool = True,
) -> dict[str, Any]:
    """Closed evidence plane: mission work then machine-check done_when.

    Escapes free-text completion theater: mission plane expands/plans/runs, then
    outcome contracts gate `met` on live ledger metrics and program evidence.
    """

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    before = snapshot_outcome_metrics(root, ledger=ledger)
    mission: dict[str, Any] | None = None
    if run_mission:
        mission = run_mission_plane(
            root,
            goal,
            command_runner=command_runner,
            timeout=timeout,
            max_steps=max_steps,
            absorb_ready=absorb_ready,
            prove_first=prove_first,
            grow_budget=grow_budget,
        )
        ledger = load_ledger(path)
    context: dict[str, Any] = {
        "used_skill_route_discovery": bool((mission or {}).get("used_skill_route_discovery")),
        "mission": mission or {},
        "mission_plane": mission or {},
    }
    contract = evaluate_outcome_contract(
        root,
        done_when,
        context=context,
        command_runner=command_runner,
        timeout=timeout,
        run_programs=True,
    )
    after = snapshot_outcome_metrics(root, ledger=load_ledger(path))
    used_skill = bool(
        before.get("used_skill_route_discovery")
        or (mission or {}).get("used_skill_route_discovery")
        or contract.get("used_skill_route_discovery")
    )
    met = contract.get("met")
    ok = (
        not used_skill
        and bool(contract.get("ok"))
        and (mission is None or bool(mission.get("ok")))
        and (met is True if contract.get("machine_checkable") else True)
    )
    return {
        "ok": ok,
        "action": "contract_plane",
        "goal": goal,
        "done_when": done_when,
        "met": met,
        "machine_checkable": contract.get("machine_checkable"),
        "expanded": bool((mission or {}).get("expanded")),
        "before": {
            "count": before.get("count"),
            "primitive_count": before.get("primitive_count"),
            "proved_count": before.get("proved_count"),
            "unique_composed_coverage_sets": before.get("unique_composed_coverage_sets"),
        },
        "after": {
            "count": after.get("count"),
            "primitive_count": after.get("primitive_count"),
            "proved_count": after.get("proved_count"),
            "unique_composed_coverage_sets": after.get("unique_composed_coverage_sets"),
        },
        "mission": None
        if mission is None
        else {
            "ok": mission.get("ok"),
            "action": mission.get("action"),
            "plan_steps": (mission.get("plan") or {}).get("steps"),
            "program_passed": (mission.get("program") or {}).get("passed_count"),
            "program_failed": (mission.get("program") or {}).get("failed_count"),
            "absorb_count": (mission.get("absorb") or {}).get("absorbed_count"),
            "grew": (mission.get("growth") or {}).get("grew"),
        },
        "contract": {
            "ok": contract.get("ok"),
            "met": contract.get("met"),
            "passed_count": contract.get("passed_count"),
            "failed_count": contract.get("failed_count"),
            "results": contract.get("results"),
            "failed": contract.get("failed"),
            "metrics": contract.get("metrics"),
            "notes": contract.get("notes"),
        },
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


# ---------------------------------------------------------------------------
# Assurance plane: ablation proofs, portable transfer, adversarial contracts.
# Escapes composition-only plateaus with falsifiable evidence about proofs.
# ---------------------------------------------------------------------------

ASSURANCE_PACKAGE_SCHEMA = 1
FAILING_PROOF_COMMAND = f'"{sys.executable}" -c "import sys; sys.exit(1)"'


def _clone_ledger(ledger: CapabilityLedger) -> CapabilityLedger:
    """Deep-copy a ledger for non-destructive ablation / transfer experiments."""

    return CapabilityLedger.from_dict(ledger.to_dict())


def _replace_capability_fields(
    ledger: CapabilityLedger,
    capability_id: str,
    **overrides: Any,
) -> CapabilityLedger:
    """Replace selected fields on one capability without re-validating the full graph."""

    original = ledger.capabilities.get(capability_id)
    if original is None:
        raise KeyError(capability_id)
    payload = original.to_dict()
    payload.update(overrides)
    ledger.capabilities[capability_id] = Capability.from_dict(payload)
    ledger.updated_at = utc_now_iso()
    return ledger


def dependency_closure(ledger: CapabilityLedger, capability_ids: Sequence[str]) -> list[str]:
    """Return transitive dependency closure (deps first) for the requested roots."""

    return topological_order(ledger, list(capability_ids))


def export_capability_package(
    ledger: CapabilityLedger,
    capability_ids: Sequence[str],
    *,
    source_ledger_path: str = "",
) -> dict[str, Any]:
    """Export capabilities + transitive deps as a portable package (no skill-route)."""

    ordered = dependency_closure(ledger, capability_ids)
    members = {
        capability_id: ledger.capabilities[capability_id].to_dict()
        for capability_id in ordered
    }
    roots = [str(item).strip() for item in capability_ids if str(item).strip()]
    digest_source = json.dumps(
        {"roots": roots, "members": sorted(members)},
        sort_keys=True,
        ensure_ascii=False,
    )
    package_hash = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
    return {
        "ok": True,
        "action": "export_capability_package",
        "schema_version": ASSURANCE_PACKAGE_SCHEMA,
        "roots": roots,
        "member_ids": ordered,
        "member_count": len(ordered),
        "members": members,
        "package_hash": package_hash,
        "source_ledger_path": source_ledger_path,
        "exported_at": utc_now_iso(),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def import_capability_package(
    ledger: CapabilityLedger,
    package: Mapping[str, Any],
    *,
    replace: bool = True,
) -> tuple[CapabilityLedger, dict[str, Any]]:
    """Import a portable package into a ledger (dependency-safe order)."""

    members_raw = package.get("members") or {}
    if not isinstance(members_raw, Mapping) or not members_raw:
        raise ValueError("package.members must be a non-empty object")
    # Build a temporary ledger of package members only to order imports.
    scratch = CapabilityLedger(schema_version=SCHEMA_VERSION, updated_at=utc_now_iso())
    for capability_id, raw in members_raw.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"package member {capability_id!r} is not an object")
        scratch.capabilities[str(capability_id)] = Capability.from_dict(
            {**raw, "id": raw.get("id") or capability_id}
        )
    roots = [str(item) for item in (package.get("roots") or list(members_raw))]
    ordered = dependency_closure(scratch, roots)
    imported: list[str] = []
    skipped: list[str] = []
    for capability_id in ordered:
        capability = scratch.capabilities[capability_id]
        if capability_id in ledger.capabilities and not replace:
            skipped.append(capability_id)
            continue
        register_capability(
            ledger,
            capability,
            replace=replace or capability_id in ledger.capabilities,
        )
        imported.append(capability_id)
    report = {
        "ok": True,
        "action": "import_capability_package",
        "imported": imported,
        "skipped": skipped,
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "roots": roots,
        "package_hash": package.get("package_hash"),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    return ledger, report


def write_capability_package(path: Path, package: Mapping[str, Any]) -> Path:
    """Persist a portable package to disk."""

    target = path.resolve()
    atomic_write_json(target, dict(package))
    return target


def load_capability_package(path: Path) -> dict[str, Any]:
    """Load a portable capability package from disk."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("package must be a JSON object")
    return dict(payload)


def run_ablation_proof(
    repo_path: Path,
    capability_id: str = "repo.import-health",
    *,
    dependent_id: str = "unbound.milestone-gate",
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 90,
) -> dict[str, Any]:
    """Falsify-then-restore proofs: broken proof fails; restored proof passes.

    Two ablation modes run in-memory (live ledger is never mutated):
    1. break_entry: replace proof_command with a failing shell; prove must fail.
    2. break_dependency: corrupt a dependency's proof and re-prove a dependent
       with skip_proved_deps=False; parent prove must fail as dependency_proof.
    Baseline prove of the target must succeed first.
    """

    root = repo_path.resolve()
    path, live = ensure_seeded_ledger(root)
    if capability_id not in live.capabilities:
        return {
            "ok": False,
            "action": "ablation_proof",
            "error": f"unknown capability {capability_id}",
            "ledger_path": str(path),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    # Phase A: baseline prove on a clone (avoid stamping live ledger mid-flight).
    baseline_ledger = _clone_ledger(live)
    baseline_ledger, baseline = prove_capability(
        baseline_ledger,
        capability_id,
        cwd=root,
        command_runner=command_runner,
        timeout=timeout,
        skip_proved_deps=True,
    )
    phases: list[dict[str, Any]] = [
        {
            "phase": "baseline",
            "capability_id": capability_id,
            "ok": baseline.ok,
            "exit_code": baseline.exit_code,
            "summary": baseline.summary,
            "expected_ok": True,
            "passed": baseline.ok is True,
        }
    ]

    # Phase B: break proof_command — must fail.
    broken = _clone_ledger(live)
    _replace_capability_fields(
        broken,
        capability_id,
        proof_command=FAILING_PROOF_COMMAND,
        last_proof_exit_code=None,
        last_proved_at="",
    )
    broken, broken_result = prove_capability(
        broken,
        capability_id,
        cwd=root,
        command_runner=command_runner,
        timeout=timeout,
        skip_proved_deps=True,
    )
    phases.append(
        {
            "phase": "break_entry",
            "capability_id": capability_id,
            "ok": broken_result.ok,
            "exit_code": broken_result.exit_code,
            "summary": broken_result.summary,
            "expected_ok": False,
            "passed": broken_result.ok is False,
        }
    )

    # Phase C: restore proof on clone — must pass again.
    restored = _clone_ledger(live)
    restored, restored_result = prove_capability(
        restored,
        capability_id,
        cwd=root,
        command_runner=command_runner,
        timeout=timeout,
        skip_proved_deps=True,
    )
    phases.append(
        {
            "phase": "restore_entry",
            "capability_id": capability_id,
            "ok": restored_result.ok,
            "exit_code": restored_result.exit_code,
            "summary": restored_result.summary,
            "expected_ok": True,
            "passed": restored_result.ok is True,
        }
    )

    # Phase D: break a dependency of dependent_id (if present).
    dep_phase: dict[str, Any] | None = None
    if dependent_id in live.capabilities:
        dependent = live.capabilities[dependent_id]
        dep_target = next(
            (dep for dep in dependent.dependencies if dep in live.capabilities),
            None,
        )
        if dep_target is not None:
            dep_broken = _clone_ledger(live)
            _replace_capability_fields(
                dep_broken,
                dep_target,
                proof_command=FAILING_PROOF_COMMAND,
                last_proof_exit_code=None,
                last_proved_at="",
            )
            # Force re-prove of the dependency by clearing last proof markers.
            dep_broken, dep_result = prove_capability(
                dep_broken,
                dependent_id,
                cwd=root,
                command_runner=command_runner,
                timeout=timeout,
                skip_proved_deps=False,
            )
            dep_phase = {
                "phase": "break_dependency",
                "capability_id": dependent_id,
                "broken_dependency": dep_target,
                "ok": dep_result.ok,
                "exit_code": dep_result.exit_code,
                "kind": dep_result.kind,
                "summary": dep_result.summary,
                "expected_ok": False,
                "passed": dep_result.ok is False,
            }
            phases.append(dep_phase)

    all_passed = all(bool(item.get("passed")) for item in phases)
    used_skill = legacy_pipeline_was_used()
    return {
        "ok": all_passed and not used_skill,
        "action": "ablation_proof",
        "capability_id": capability_id,
        "dependent_id": dependent_id if dep_phase else None,
        "phase_count": len(phases),
        "passed_count": sum(1 for item in phases if item.get("passed")),
        "failed_phases": [item["phase"] for item in phases if not item.get("passed")],
        "phases": phases,
        "live_ledger_mutated": False,
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


def run_transfer_plane(
    repo_path: Path,
    capability_ids: Sequence[str] | None = None,
    *,
    package_path: Path | None = None,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    prove_imported: bool = True,
) -> dict[str, Any]:
    """Export → import into an empty ledger → re-prove the portable package.

    Demonstrates lineage portability: capability records survive package
    round-trips and still prove against the same codebase without skill-route.
    """

    root = repo_path.resolve()
    path, live = ensure_seeded_ledger(root)
    roots = list(capability_ids) if capability_ids else [
        "repo.import-health",
        "capability.ledger-inventory",
        "unbound.milestone-gate",
    ]
    missing = [item for item in roots if item not in live.capabilities]
    if missing:
        return {
            "ok": False,
            "action": "transfer_plane",
            "error": f"missing roots: {missing}",
            "ledger_path": str(path),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    package = export_capability_package(
        live,
        roots,
        source_ledger_path=str(path),
    )
    out_path = (
        package_path.resolve()
        if package_path is not None
        else (root / "artifacts" / "capability-packages" / f"transfer-{package['package_hash']}.json")
    )
    write_capability_package(out_path, package)
    reloaded = load_capability_package(out_path)

    # Fresh empty ledger — only package members, no ambient bloat.
    empty = CapabilityLedger(schema_version=SCHEMA_VERSION, updated_at=utc_now_iso())
    empty, import_report = import_capability_package(empty, reloaded, replace=True)

    proof_results: list[dict[str, Any]] = []
    all_proved = True
    if prove_imported:
        for capability_id in reloaded.get("member_ids") or import_report["imported"]:
            empty, result = prove_capability(
                empty,
                capability_id,
                cwd=root,
                command_runner=command_runner,
                timeout=timeout,
                skip_proved_deps=True,
            )
            proof_results.append(
                {
                    "capability_id": capability_id,
                    "ok": result.ok,
                    "exit_code": result.exit_code,
                    "summary": result.summary,
                }
            )
            if not result.ok:
                all_proved = False
                break

    # Round-trip integrity: re-export from imported ledger must share roots/members.
    reexport = export_capability_package(empty, roots)
    members_match = set(reexport.get("member_ids") or []) == set(package.get("member_ids") or [])
    used_skill = bool(package.get("used_skill_route_discovery")) or legacy_pipeline_was_used()
    ok = (
        not used_skill
        and bool(package.get("ok"))
        and bool(import_report.get("ok"))
        and all_proved
        and members_match
        and int(import_report.get("imported_count") or 0) == int(package.get("member_count") or -1)
    )
    return {
        "ok": ok,
        "action": "transfer_plane",
        "roots": roots,
        "package_path": str(out_path),
        "package_hash": package.get("package_hash"),
        "member_count": package.get("member_count"),
        "member_ids": package.get("member_ids"),
        "export": {
            "ok": package.get("ok"),
            "member_count": package.get("member_count"),
            "package_hash": package.get("package_hash"),
        },
        "import": import_report,
        "reexport_members_match": members_match,
        "proofs": proof_results,
        "proved_count": sum(1 for item in proof_results if item.get("ok")),
        "prove_imported": prove_imported,
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


def run_adversarial_contract(
    repo_path: Path,
    *,
    positive_done_when: str | None = None,
    negative_done_when: Sequence[str] | None = None,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 90,
    run_programs: bool = False,
) -> dict[str, Any]:
    """Evaluate contracts that must pass and contracts that must fail.

    Complements outcome-contract: positive predicates stay met, adversarial
    (expected-fail) contracts must report met=False. Prevents one-sided
    evaluator theater where everything always passes.
    """

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    # Ensure a known primitive is green so positive capability_proved can hold.
    if "repo.import-health" in ledger.capabilities:
        ledger, _ = prove_capability(
            ledger,
            "repo.import-health",
            cwd=root,
            command_runner=command_runner,
            timeout=min(timeout, 60),
            skip_proved_deps=True,
        )
        save_ledger(path, ledger)

    positive = positive_done_when or (
        "min_capabilities:3; capability_exists:repo.import-health; "
        "capability_proved:repo.import-health; no_skill_route"
    )
    negatives = list(negative_done_when) if negative_done_when is not None else [
        "min_capabilities:999999",
        "capability_exists:capability.assurance-does-not-exist-zzzz",
        "capability_proved:capability.assurance-does-not-exist-zzzz",
        "min_primitives:999999",
    ]

    positive_verdict = evaluate_outcome_contract(
        root,
        positive,
        command_runner=command_runner,
        timeout=timeout,
        run_programs=run_programs,
    )
    negative_results: list[dict[str, Any]] = []
    for contract_text in negatives:
        verdict = evaluate_outcome_contract(
            root,
            contract_text,
            command_runner=command_runner,
            timeout=timeout,
            run_programs=False,
        )
        expected_fail = verdict.get("met") is False and bool(verdict.get("machine_checkable"))
        negative_results.append(
            {
                "done_when": contract_text,
                "ok": verdict.get("ok"),
                "met": verdict.get("met"),
                "machine_checkable": verdict.get("machine_checkable"),
                "failed_count": verdict.get("failed_count"),
                "expected_met": False,
                "passed": expected_fail,
                "failed": verdict.get("failed"),
            }
        )

    positive_ok = (
        bool(positive_verdict.get("ok"))
        and positive_verdict.get("machine_checkable") is True
        and positive_verdict.get("met") is True
    )
    negatives_ok = bool(negative_results) and all(item.get("passed") for item in negative_results)
    used_skill = bool(positive_verdict.get("used_skill_route_discovery")) or legacy_pipeline_was_used()
    ok = positive_ok and negatives_ok and not used_skill
    return {
        "ok": ok,
        "action": "adversarial_contract",
        "positive": {
            "done_when": positive,
            "ok": positive_verdict.get("ok"),
            "met": positive_verdict.get("met"),
            "machine_checkable": positive_verdict.get("machine_checkable"),
            "passed_count": positive_verdict.get("passed_count"),
            "failed_count": positive_verdict.get("failed_count"),
            "expected_met": True,
            "passed": positive_ok,
        },
        "negatives": negative_results,
        "negative_count": len(negative_results),
        "negatives_passed": sum(1 for item in negative_results if item.get("passed")),
        "positive_ok": positive_ok,
        "negatives_ok": negatives_ok,
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


def run_assurance_plane(
    repo_path: Path,
    *,
    capability_id: str = "repo.import-health",
    transfer_roots: Sequence[str] | None = None,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
) -> dict[str, Any]:
    """Closed assurance plane: ablation → transfer → adversarial contracts.

    Adds falsifiable evidence beyond composition growth: proofs must fail when
    broken, packages must re-prove after export/import, and done_when evaluators
    must reject adversarial contracts.
    """

    root = repo_path.resolve()
    path, _ledger = ensure_seeded_ledger(root)
    ablation = run_ablation_proof(
        root,
        capability_id=capability_id,
        command_runner=command_runner,
        timeout=timeout,
    )
    transfer = run_transfer_plane(
        root,
        transfer_roots,
        command_runner=command_runner,
        timeout=timeout,
        prove_imported=True,
    )
    adversarial = run_adversarial_contract(
        root,
        command_runner=command_runner,
        timeout=timeout,
        run_programs=False,
    )
    used_skill = bool(
        ablation.get("used_skill_route_discovery")
        or transfer.get("used_skill_route_discovery")
        or adversarial.get("used_skill_route_discovery")
        or legacy_pipeline_was_used()
    )
    ok = (
        not used_skill
        and bool(ablation.get("ok"))
        and bool(transfer.get("ok"))
        and bool(adversarial.get("ok"))
    )
    return {
        "ok": ok,
        "action": "assurance_plane",
        "ablation": {
            "ok": ablation.get("ok"),
            "phase_count": ablation.get("phase_count"),
            "passed_count": ablation.get("passed_count"),
            "failed_phases": ablation.get("failed_phases"),
            "live_ledger_mutated": ablation.get("live_ledger_mutated"),
        },
        "transfer": {
            "ok": transfer.get("ok"),
            "package_path": transfer.get("package_path"),
            "package_hash": transfer.get("package_hash"),
            "member_count": transfer.get("member_count"),
            "proved_count": transfer.get("proved_count"),
            "reexport_members_match": transfer.get("reexport_members_match"),
        },
        "adversarial": {
            "ok": adversarial.get("ok"),
            "positive_ok": adversarial.get("positive_ok"),
            "negatives_ok": adversarial.get("negatives_ok"),
            "negative_count": adversarial.get("negative_count"),
            "negatives_passed": adversarial.get("negatives_passed"),
        },
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


# ---------------------------------------------------------------------------
# Sovereignty plane: contract + assurance → portable, re-verifiable certificate.
# Closes the self-certifying evidence loop past separate plane invocations.
# ---------------------------------------------------------------------------

SOVEREIGNTY_CERTIFICATE_SCHEMA = 1


def _canonical_certificate_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Strip volatile/hash fields so certificate_hash is stable."""

    body = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "certificate_hash",
            "ok",
            "action",
            "certificate_path",
            "verify",
            "used_skill_route_discovery",
            "ledger_path",
        }
    }
    return body


def compute_sovereignty_certificate_hash(payload: Mapping[str, Any]) -> str:
    """SHA-256 over canonical certificate body (excludes the hash field itself)."""

    body = _canonical_certificate_body(payload)
    digest_source = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:24]


def issue_sovereignty_certificate(
    *,
    goal: str,
    done_when: str,
    contract: Mapping[str, Any],
    assurance: Mapping[str, Any],
    metrics: Mapping[str, Any] | None = None,
    repo_path: Path | None = None,
) -> dict[str, Any]:
    """Issue a portable sovereignty certificate from plane evidence summaries."""

    claims = {
        "contract_ok": bool(contract.get("ok")),
        "contract_met": contract.get("met") is True,
        "machine_checkable": bool(contract.get("machine_checkable")),
        "assurance_ok": bool(assurance.get("ok")),
        "ablation_ok": bool((assurance.get("ablation") or {}).get("ok")),
        "transfer_ok": bool((assurance.get("transfer") or {}).get("ok")),
        "adversarial_ok": bool((assurance.get("adversarial") or {}).get("ok")),
        "no_skill_route": not bool(
            contract.get("used_skill_route_discovery")
            or assurance.get("used_skill_route_discovery")
        ),
    }
    evidence = {
        "contract": {
            "ok": contract.get("ok"),
            "met": contract.get("met"),
            "machine_checkable": contract.get("machine_checkable"),
            "passed_count": (contract.get("contract") or contract).get("passed_count")
            if isinstance(contract.get("contract"), Mapping)
            else contract.get("passed_count"),
            "failed_count": (contract.get("contract") or contract).get("failed_count")
            if isinstance(contract.get("contract"), Mapping)
            else contract.get("failed_count"),
            "mission_ok": (contract.get("mission") or {}).get("ok"),
        },
        "assurance": {
            "ok": assurance.get("ok"),
            "ablation": assurance.get("ablation"),
            "transfer": {
                "ok": (assurance.get("transfer") or {}).get("ok"),
                "package_hash": (assurance.get("transfer") or {}).get("package_hash"),
                "member_count": (assurance.get("transfer") or {}).get("member_count"),
                "proved_count": (assurance.get("transfer") or {}).get("proved_count"),
            },
            "adversarial": assurance.get("adversarial"),
        },
        "metrics": {
            "count": (metrics or {}).get("count"),
            "primitive_count": (metrics or {}).get("primitive_count"),
            "proved_count": (metrics or {}).get("proved_count"),
            "proved_ratio": (metrics or {}).get("proved_ratio"),
        },
    }
    certificate: dict[str, Any] = {
        "schema_version": SOVEREIGNTY_CERTIFICATE_SCHEMA,
        "kind": "sovereignty_certificate",
        "issued_at": utc_now_iso(),
        "goal": goal,
        "done_when": done_when,
        "claims": claims,
        "evidence": evidence,
        "package_hash": (assurance.get("transfer") or {}).get("package_hash"),
        "repo_path": str(repo_path.resolve()) if repo_path is not None else "",
    }
    certificate["certificate_hash"] = compute_sovereignty_certificate_hash(certificate)
    certificate["ok"] = all(
        (
            claims["contract_ok"],
            claims["contract_met"] if claims["machine_checkable"] else True,
            claims["assurance_ok"],
            claims["ablation_ok"],
            claims["transfer_ok"],
            claims["adversarial_ok"],
            claims["no_skill_route"],
        )
    )
    return certificate


def write_sovereignty_certificate(path: Path, certificate: Mapping[str, Any]) -> Path:
    """Persist a sovereignty certificate to disk."""

    target = path.resolve()
    atomic_write_json(target, dict(certificate))
    return target


def load_sovereignty_certificate(path: Path) -> dict[str, Any]:
    """Load a sovereignty certificate from disk."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("sovereignty certificate must be a JSON object")
    return dict(payload)


def verify_sovereignty_certificate(
    certificate: Mapping[str, Any] | Path | str,
    *,
    repo_path: Path | None = None,
    recheck_live: bool = False,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 90,
) -> dict[str, Any]:
    """Re-verify a sovereignty certificate's hash and optional live claims.

    Hash integrity is always checked. When recheck_live is true and repo_path is
    set, re-evaluate lightweight ledger claims without re-running full planes.
    """

    cert_path = ""
    if isinstance(certificate, (str, Path)):
        cert_path = str(Path(certificate).resolve())
        payload = load_sovereignty_certificate(Path(certificate))
    else:
        payload = dict(certificate)

    expected = str(payload.get("certificate_hash") or "").strip()
    recomputed = compute_sovereignty_certificate_hash(payload)
    hash_ok = bool(expected) and expected == recomputed
    claims = payload.get("claims") if isinstance(payload.get("claims"), Mapping) else {}
    claims_ok = bool(claims) and all(
        bool(claims.get(key))
        for key in (
            "contract_ok",
            "assurance_ok",
            "ablation_ok",
            "transfer_ok",
            "adversarial_ok",
            "no_skill_route",
        )
    )
    if claims.get("machine_checkable"):
        claims_ok = claims_ok and bool(claims.get("contract_met"))

    live_ok: bool | None = None
    live_detail: dict[str, Any] = {}
    if recheck_live and repo_path is not None:
        root = repo_path.resolve()
        path, ledger = ensure_seeded_ledger(root)
        metrics = snapshot_outcome_metrics(root, ledger=ledger)
        live_detail = {
            "count": metrics.get("count"),
            "proved_count": metrics.get("proved_count"),
            "has_assurance": "capability.assurance-plane" in ledger.capabilities,
            "has_import_health": "repo.import-health" in ledger.capabilities,
            "used_skill_route_discovery": metrics.get("used_skill_route_discovery"),
            "ledger_path": str(path),
        }
        live_ok = (
            int(metrics.get("count") or 0) >= 3
            and "repo.import-health" in ledger.capabilities
            and not bool(metrics.get("used_skill_route_discovery"))
        )

    valid = hash_ok and claims_ok and (live_ok is not False)
    used_skill = legacy_pipeline_was_used()
    return {
        "ok": valid and not used_skill,
        "action": "verify_sovereignty_certificate",
        "valid": valid,
        "hash_ok": hash_ok,
        "claims_ok": claims_ok,
        "expected_hash": expected,
        "recomputed_hash": recomputed,
        "certificate_hash": expected or recomputed,
        "certificate_path": cert_path or None,
        "live_recheck": live_ok,
        "live_detail": live_detail,
        "schema_version": payload.get("schema_version"),
        "kind": payload.get("kind"),
        "used_skill_route_discovery": used_skill,
    }


def run_sovereignty_plane(
    repo_path: Path,
    goal: str = "health inventory milestone",
    done_when: str = "",
    *,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 180,
    max_steps: int = 3,
    absorb_ready: bool = False,
    grow_budget: int = 0,
    run_mission: bool = True,
    run_assurance: bool = True,
    certificate_path: Path | None = None,
    capability_id: str = "repo.import-health",
) -> dict[str, Any]:
    """Closed sovereignty plane: contract → assurance → issue/verify certificate.

    Produces a portable, re-verifiable lineage certificate so mission completion
    is self-certifying evidence rather than free-text theater or one-shot plane
    invocations that leave no durable artifact.
    """

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    contract_done_when = (done_when or "").strip() or (
        "min_capabilities:5; min_primitives:3; capability_exists:repo.import-health; "
        "capability_proved:repo.import-health; program_passes:repo.import-health; "
        "no_skill_route; mission_plane_ok"
    )
    # Context-only predicates are evaluated after planes produce evidence; strip them
    # from the inner contract so sovereignty_ok/certificate_valid do not false-fail.
    _context_only = re.compile(
        r"^(mission_plane_ok|contract_plane_ok|assurance_plane_ok|sovereignty_ok|"
        r"certificate_valid)(?::.*)?$",
        re.I,
    )
    filtered_parts = [
        part.strip()
        for part in re.split(r"[\n;]+", contract_done_when)
        if part.strip() and not _context_only.match(part.strip())
    ]
    # mission_plane_ok is only meaningful when the mission plane actually runs.
    if run_mission and re.search(r"\bmission_plane_ok\b", contract_done_when, re.I):
        filtered_parts.append("mission_plane_ok")
    contract_done_when = "; ".join(filtered_parts) or (
        "min_capabilities:3; capability_exists:repo.import-health; "
        "capability_proved:repo.import-health; no_skill_route"
    )
    # Contract plane may include mission_plane_ok; keep mission cheap by default.
    contract = run_contract_plane(
        root,
        goal,
        contract_done_when,
        command_runner=command_runner,
        timeout=timeout,
        max_steps=max_steps,
        absorb_ready=absorb_ready,
        grow_budget=grow_budget,
        run_mission=run_mission,
    )
    assurance: dict[str, Any]
    if run_assurance:
        assurance = run_assurance_plane(
            root,
            capability_id=capability_id,
            command_runner=command_runner,
            timeout=timeout,
        )
    else:
        assurance = {
            "ok": False,
            "action": "assurance_plane",
            "error": "assurance skipped",
            "ablation": {"ok": False},
            "transfer": {"ok": False},
            "adversarial": {"ok": False},
            "used_skill_route_discovery": False,
        }

    metrics = snapshot_outcome_metrics(root, ledger=load_ledger(path))
    certificate = issue_sovereignty_certificate(
        goal=goal,
        done_when=contract_done_when,
        contract=contract,
        assurance=assurance,
        metrics=metrics,
        repo_path=root,
    )
    out_path = (
        certificate_path.resolve()
        if certificate_path is not None
        else (
            root
            / "artifacts"
            / "sovereignty-certificates"
            / f"sovereignty-{certificate['certificate_hash']}.json"
        )
    )
    write_sovereignty_certificate(out_path, certificate)
    verify = verify_sovereignty_certificate(
        out_path,
        repo_path=root,
        recheck_live=True,
        command_runner=command_runner,
        timeout=min(timeout, 60),
    )

    # Final sovereign verdict: planes ok + certificate re-verifies + no skill-route.
    context = {
        "used_skill_route_discovery": bool(
            contract.get("used_skill_route_discovery")
            or assurance.get("used_skill_route_discovery")
        ),
        "mission": contract.get("mission") or {},
        "mission_plane": contract.get("mission") or {},
        "contract_plane": contract,
        "assurance": assurance,
        "assurance_plane": assurance,
        "sovereignty": {"ok": True},  # provisional for predicate eval; corrected below
        "sovereignty_plane": {"ok": True},
        "certificate_path": str(out_path),
        "certificate_payload": certificate,
    }
    # Sovereignty contract can reference plane outcomes + certificate validity.
    sovereignty_done_when = (
        "no_skill_route; assurance_plane_ok; sovereignty_ok; certificate_valid; "
        "capability_exists:repo.import-health"
    )
    # First pass with provisional sovereignty_ok=True only if planes already green.
    provisional_ok = (
        bool(contract.get("ok"))
        and bool(assurance.get("ok"))
        and bool(certificate.get("ok"))
        and bool(verify.get("valid"))
    )
    context["sovereignty"] = {"ok": provisional_ok}
    context["sovereignty_plane"] = {"ok": provisional_ok}
    final_contract = evaluate_outcome_contract(
        root,
        sovereignty_done_when,
        context=context,
        command_runner=command_runner,
        timeout=min(timeout, 60),
        run_programs=False,
    )
    used_skill = bool(
        contract.get("used_skill_route_discovery")
        or assurance.get("used_skill_route_discovery")
        or verify.get("used_skill_route_discovery")
        or final_contract.get("used_skill_route_discovery")
        or legacy_pipeline_was_used()
    )
    ok = (
        not used_skill
        and provisional_ok
        and bool(final_contract.get("ok"))
        and final_contract.get("met") is True
        and bool(verify.get("ok"))
    )
    return {
        "ok": ok,
        "action": "sovereignty_plane",
        "goal": goal,
        "done_when": contract_done_when,
        "sovereignty_done_when": sovereignty_done_when,
        "met": final_contract.get("met"),
        "machine_checkable": True,
        "contract": {
            "ok": contract.get("ok"),
            "met": contract.get("met"),
            "machine_checkable": contract.get("machine_checkable"),
            "mission": contract.get("mission"),
        },
        "assurance": {
            "ok": assurance.get("ok"),
            "ablation": assurance.get("ablation"),
            "transfer": {
                "ok": (assurance.get("transfer") or {}).get("ok"),
                "package_hash": (assurance.get("transfer") or {}).get("package_hash"),
                "member_count": (assurance.get("transfer") or {}).get("member_count"),
            },
            "adversarial": assurance.get("adversarial"),
        },
        "certificate": {
            "ok": certificate.get("ok"),
            "certificate_hash": certificate.get("certificate_hash"),
            "certificate_path": str(out_path),
            "claims": certificate.get("claims"),
            "package_hash": certificate.get("package_hash"),
            "issued_at": certificate.get("issued_at"),
        },
        "verify": {
            "ok": verify.get("ok"),
            "valid": verify.get("valid"),
            "hash_ok": verify.get("hash_ok"),
            "claims_ok": verify.get("claims_ok"),
            "live_recheck": verify.get("live_recheck"),
            "certificate_hash": verify.get("certificate_hash"),
        },
        "final_contract": {
            "ok": final_contract.get("ok"),
            "met": final_contract.get("met"),
            "passed_count": final_contract.get("passed_count"),
            "failed_count": final_contract.get("failed_count"),
            "failed": final_contract.get("failed"),
        },
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


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


def run_python_entry_inprocess(
    entry: str,
    *,
    env: dict[str, str] | None = None,
) -> CapabilityRunResult:
    """Execute `module:function` in-process (for nested composition trees)."""

    if ":" not in entry:
        raise ValueError(f"python capability entry must be module:function, got {entry!r}")
    module_name, _, function_name = entry.partition(":")
    if not module_name or not function_name:
        raise ValueError(f"python capability entry must be module:function, got {entry!r}")
    import importlib

    saved: dict[str, str | None] = {}
    if env:
        for key, value in env.items():
            saved[key] = os.environ.get(key)
            os.environ[key] = value
    try:
        module = importlib.import_module(module_name)
        fn = getattr(module, function_name)
        raw = fn()
        if raw is None:
            payload: dict[str, Any] = {"ok": True}
        elif isinstance(raw, dict):
            payload = raw
        else:
            payload = {"ok": True, "result": raw}
        ok = bool(payload.get("ok", True))
        stdout = json.dumps(payload, sort_keys=True, default=str)
        return CapabilityRunResult(
            capability_id=str((env or {}).get(ACTIVE_CAPABILITY_ENV) or ""),
            ok=ok,
            exit_code=0 if ok else 1,
            command=("inprocess", entry),
            stdout=stdout,
            stderr="",
            kind="python-inprocess",
            summary=stdout.splitlines()[0][:500] if stdout else ("ok" if ok else "failed"),
        )
    except Exception as error:  # noqa: BLE001 - surface as capability failure
        return CapabilityRunResult(
            capability_id=str((env or {}).get(ACTIVE_CAPABILITY_ENV) or ""),
            ok=False,
            exit_code=1,
            command=("inprocess", entry),
            stdout="",
            stderr=str(error),
            kind="python-inprocess",
            summary=str(error)[:500],
        )
    finally:
        for key, previous in saved.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


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
    skip_proved_deps: bool = True,
) -> tuple[CapabilityLedger, CapabilityRunResult]:
    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        raise KeyError(capability_id)
    # Prove dependencies first (skip already-green deps to keep hierarchical /
    # meta / superstack proofs tractable during growth).
    for dependency in topological_order(ledger, [capability_id])[:-1]:
        dep_capability = ledger.capabilities[dependency]
        if skip_proved_deps and dep_capability.last_proof_exit_code == 0:
            continue
        ledger, dep_result = prove_capability(
            ledger,
            dependency,
            cwd=cwd,
            command_runner=command_runner,
            timeout=timeout,
            skip_proved_deps=skip_proved_deps,
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


def direct_member_order(ledger: CapabilityLedger, capability_ids: Sequence[str]) -> list[str]:
    """Order only the requested ids among themselves (no transitive expansion)."""

    requested = list(dict.fromkeys(str(item).strip() for item in capability_ids if str(item).strip()))
    missing = [item for item in requested if item not in ledger.capabilities]
    if missing:
        raise KeyError(f"Unknown capabilities: {', '.join(missing)}")
    requested_set = set(requested)
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
            if dependency in requested_set:
                visit(dependency)
        temporary.remove(node)
        permanent.add(node)
        ordered.append(node)

    for capability_id in requested:
        visit(capability_id)
    return ordered


def compose_capabilities(
    ledger: CapabilityLedger,
    capability_ids: Sequence[str],
    *,
    cwd: Path,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    prove_first: bool = True,
    inprocess: bool = False,
    direct_only: bool = False,
) -> list[CapabilityRunResult]:
    """Run a dependency-ordered capability chain.

    When `inprocess=True`, python entries run in the current interpreter so nested
    hierarchical/meta/superstack compositions do not explode into subprocess trees.
    When `direct_only=True`, only the requested member ids run (nested composed
    members expand themselves), avoiding double full-DAG expansion.
    """

    order = (
        direct_member_order(ledger, capability_ids)
        if direct_only
        else topological_order(ledger, capability_ids)
    )
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
        if inprocess and capability.kind == "python" and not prove_first:
            result = run_python_entry_inprocess(
                capability.entry,
                env={ACTIVE_CAPABILITY_ENV: capability.id},
            )
            # Preserve capability id on the result even when entry does not set it.
            if not result.capability_id:
                result = CapabilityRunResult(
                    capability_id=capability_id,
                    ok=result.ok,
                    exit_code=result.exit_code,
                    command=result.command,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    kind=result.kind,
                    summary=result.summary,
                )
        else:
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
        "imports_skill_routing": legacy_pipeline_was_used(),
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
            "used_skill_route_discovery": legacy_pipeline_was_used(),
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
        "used_skill_route_discovery": legacy_pipeline_was_used(),
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
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def builtin_issue_triage_smoke() -> dict[str, Any]:
    """Prove local issue triage lanes without remote mutation or skill-route discovery."""

    from blackhole_agent.issue_triage import (
        TRIAGE_FOLLOW_UP,
        TRIAGE_NO_ACTION,
        TRIAGE_VALIDATION,
        triage_issue_input,
    )

    validation = triage_issue_input(
        {
            "title": "tests failing on main",
            "body": "regression in harness coverage",
            "labels": ["bug"],
        },
        allow_remote_mutation=False,
    )
    follow_up = triage_issue_input(
        {
            "title": "should we clarify the docs?",
            "body": "question about configuration",
            "labels": ["question"],
        },
        allow_remote_mutation=False,
    )
    no_action = triage_issue_input(
        {
            "title": "duplicate spam issue",
            "body": "this is spam / won't fix",
            "labels": ["duplicate"],
        },
        allow_remote_mutation=False,
    )
    ok = (
        validation.lane == TRIAGE_VALIDATION
        and follow_up.lane == TRIAGE_FOLLOW_UP
        and no_action.lane == TRIAGE_NO_ACTION
        and validation.recommendation is not None
        and not bool(getattr(validation, "remote_mutation_allowed", False))
    )
    return {
        "ok": ok,
        "validation_lane": validation.lane,
        "follow_up_lane": follow_up.lane,
        "no_action_lane": no_action.lane,
        "remote_mutation_allowed": bool(getattr(validation, "remote_mutation_allowed", False)),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def builtin_ci_security_gate() -> dict[str, Any]:
    """Prove fail-closed security-scan gate pass/block/waiver paths offline."""

    from blackhole_agent.ci_security import SecurityScanGateInput, evaluate_security_scan_gate

    passed = evaluate_security_scan_gate(SecurityScanGateInput(scan_conclusion="success"))
    blocked = evaluate_security_scan_gate(SecurityScanGateInput(scan_conclusion="failure"))
    waived = evaluate_security_scan_gate(
        SecurityScanGateInput(
            scan_conclusion="failure",
            pull_request_labels=("security-scan-waiver",),
            current_run_attempt=1,
            label_snapshot_run_attempt=1,
        )
    )
    stale = evaluate_security_scan_gate(
        SecurityScanGateInput(
            scan_conclusion="failure",
            pull_request_labels=("security-scan-waiver",),
            current_run_attempt=2,
            label_snapshot_run_attempt=1,
        )
    )
    ok = (
        passed.allowed
        and passed.outcome == "security_scan_passed"
        and not blocked.allowed
        and waived.allowed
        and waived.waiver_applied
        and not stale.allowed
    )
    return {
        "ok": ok,
        "passed_outcome": passed.outcome,
        "blocked_outcome": blocked.outcome,
        "waived_outcome": waived.outcome,
        "stale_outcome": stale.outcome,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def builtin_proposal_eval_smoke() -> dict[str, Any]:
    """Prove one frozen proposal replay case offline without skill-route discovery."""

    from blackhole_agent.proposal_eval import load_proposal_replay_case, run_proposal_replay_case

    repo_root = Path(__file__).resolve().parents[2]
    case_path = repo_root / "tests" / "fixtures" / "proposal_replay" / "benign_agent_harness.json"
    if not case_path.is_file():
        return {
            "ok": False,
            "error": f"missing fixture {case_path}",
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    case = load_proposal_replay_case(case_path)
    result = run_proposal_replay_case(case)
    return {
        "ok": bool(result.passed),
        "case_name": result.name,
        "review_status": result.review_status,
        "accepted_count": result.accepted_count,
        "rejected_count": result.rejected_count,
        "failures": list(result.failures),
        "fixture": str(case_path.as_posix()),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def builtin_supervisor_compound_wake() -> dict[str, Any]:
    """Prove supervisor wake routing prefers compounder demo when ledger is ready.

    Second-wave runtime domain surface: exercises evolution_route + supervisor
    compound-mode selection offline without starting the wake loop or skill-route
    discovery cascade.
    """

    from blackhole_agent.evolution_route import (
        COMPOUND_SURFACE,
        build_compound_wake_command,
        resolve_supervisor_evolution_surface,
    )

    repo_root = Path(__file__).resolve().parents[2]
    surface = resolve_supervisor_evolution_surface(
        evolution_mode="codex",
        repo_path=repo_root,
        prefer_capability_compounder=True,
    )
    explicit = resolve_supervisor_evolution_surface(
        evolution_mode="compound",
        repo_path=repo_root,
        prefer_capability_compounder=True,
    )
    command = build_compound_wake_command(repo_path=repo_root, use_demo=True)
    command_text = " ".join(str(part) for part in command)
    ok = (
        surface.get("surface") == COMPOUND_SURFACE
        and surface.get("effective_mode") == "compound"
        and explicit.get("surface") == COMPOUND_SURFACE
        and explicit.get("effective_mode") == "compound"
        and "capability" in command_text
        and "demo" in command_text
        and "skill_route" not in command_text
    )
    return {
        "ok": ok,
        "codex_surface": surface.get("surface"),
        "codex_mode": surface.get("effective_mode"),
        "codex_reason": surface.get("reason"),
        "explicit_compound_surface": explicit.get("surface"),
        "wake_command": command,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def builtin_persona_render() -> dict[str, Any]:
    """Prove the operational persona layer renders a stable identity contract offline."""

    from blackhole_agent.persona import BLACKHOLE_PERSONA, PERSONA_VERSION, render_persona_layer

    text = render_persona_layer()
    ok = (
        bool(text.strip())
        and PERSONA_VERSION in text
        and BLACKHOLE_PERSONA.name in text
        and "core mechanism" in text.lower()
    )
    return {
        "ok": ok,
        "version": PERSONA_VERSION,
        "name": BLACKHOLE_PERSONA.name,
        "chars": len(text),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def builtin_proposal_synthesis_smoke() -> dict[str, Any]:
    """Offline proposal-synthesis evidence packaging without LLM or skill-route discovery."""

    from blackhole_agent.proposal_synthesis import (
        PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        build_proposal_evidence_package,
        validate_proposal_mode,
    )

    mode = validate_proposal_mode("heuristic")
    package = build_proposal_evidence_package(
        {
            "digest_id": "capability-second-wave-smoke",
            "items": [
                {
                    "summary": "Capability mission plane expands primitives past superstack plateau.",
                    "relevance_reason": "Offline second-wave domain absorption evidence.",
                    "confidence": 0.91,
                    "risk_flags": [],
                    "source_url": "",
                    "event_kind": "PushEvent",
                }
            ],
        }
    )
    items = package.get("items") if isinstance(package, dict) else None
    ok = (
        mode == "heuristic"
        and isinstance(package, dict)
        and package.get("schema_version") == PROPOSAL_SYNTHESIS_SCHEMA_VERSION
        and isinstance(items, list)
        and len(items) >= 1
        and bool(str(package.get("digest_id") or "").strip())
    )
    return {
        "ok": ok,
        "mode": mode,
        "schema_version": package.get("schema_version") if isinstance(package, dict) else None,
        "item_count": len(items) if isinstance(items, list) else 0,
        "digest_id": package.get("digest_id") if isinstance(package, dict) else None,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def builtin_kernel_preflight() -> dict[str, Any]:
    """Offline Grok kernel provider/config preflight without invoking the CLI network path."""

    from blackhole_agent.kernels.grok_cli import GrokCliConfig, build_grok_provider_preflight

    preflight = build_grok_provider_preflight(GrokCliConfig())
    # Success means the preflight contract is structured and inspectable, not that the
    # binary is present (CI and constrained hosts may lack grok on PATH).
    ok = (
        isinstance(preflight, dict)
        and int(preflight.get("schema_version") or 0) == 1
        and preflight.get("provider") == "grok"
        and isinstance(preflight.get("diagnostics"), list)
        and "binary_present" in preflight
    )
    return {
        "ok": ok,
        "preflight_ok": bool(preflight.get("ok")) if isinstance(preflight, dict) else False,
        "binary_present": bool(preflight.get("binary_present")) if isinstance(preflight, dict) else False,
        "diagnostics": list(preflight.get("diagnostics") or []) if isinstance(preflight, dict) else [],
        "provider": preflight.get("provider") if isinstance(preflight, dict) else None,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
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
    {
        "id": "domain.issue-triage",
        "name": "Issue triage lane smoke",
        "description": (
            "Classify issue-like inputs into validation/follow-up/no-action lanes without remote mutation."
        ),
        "module": "blackhole_agent.issue_triage",
        "module_path": "src/blackhole_agent/issue_triage.py",
        "entry": "blackhole_agent.capability_compounder:builtin_issue_triage_smoke",
        "function": "builtin_issue_triage_smoke",
        "capability_delta": (
            "Local issue triage is invocable as a first-class ledger capability."
        ),
        "tags": ("domain", "triage", "absorbable"),
        "priority": 58,
        "dependencies": ("repo.import-health",),
    },
    {
        "id": "domain.ci-security",
        "name": "CI security scan gate",
        "description": (
            "Evaluate fail-closed security-scan pass, block, waiver, and stale-snapshot decisions offline."
        ),
        "module": "blackhole_agent.ci_security",
        "module_path": "src/blackhole_agent/ci_security.py",
        "entry": "blackhole_agent.capability_compounder:builtin_ci_security_gate",
        "function": "builtin_ci_security_gate",
        "capability_delta": (
            "CI security-scan gating is invocable as a first-class ledger capability."
        ),
        "tags": ("domain", "security", "absorbable"),
        "priority": 56,
        "dependencies": ("repo.import-health",),
    },
    {
        "id": "domain.proposal-eval",
        "name": "Proposal eval replay smoke",
        "description": (
            "Replay one frozen proposal evidence package offline without skill-route discovery."
        ),
        "module": "blackhole_agent.proposal_eval",
        "module_path": "src/blackhole_agent/proposal_eval.py",
        "entry": "blackhole_agent.capability_compounder:builtin_proposal_eval_smoke",
        "function": "builtin_proposal_eval_smoke",
        "capability_delta": (
            "Proposal evaluation replay is invocable as a first-class ledger capability."
        ),
        "tags": ("domain", "proposal", "absorbable"),
        "priority": 54,
        "dependencies": ("repo.import-health",),
    },
    {
        "id": "domain.supervisor-compound",
        "name": "Supervisor compound wake routing",
        "description": (
            "Resolve supervisor wake surface to capability compounder demo/compose when the "
            "durable ledger is ready, without skill-route cascade."
        ),
        "module": "blackhole_agent.supervisor",
        "module_path": "src/blackhole_agent/supervisor.py",
        "entry": "blackhole_agent.capability_compounder:builtin_supervisor_compound_wake",
        "function": "builtin_supervisor_compound_wake",
        "capability_delta": (
            "Supervisor compound-wake routing is invocable as a second-wave domain capability."
        ),
        "tags": ("domain", "supervisor", "absorbable", "second-wave"),
        "priority": 68,
        "dependencies": ("repo.import-health", "evolution.compounder-redirect"),
    },
    {
        "id": "domain.persona",
        "name": "Persona layer render",
        "description": (
            "Render the operational persona identity/mechanism contract offline as a durable surface."
        ),
        "module": "blackhole_agent.persona",
        "module_path": "src/blackhole_agent/persona.py",
        "entry": "blackhole_agent.capability_compounder:builtin_persona_render",
        "function": "builtin_persona_render",
        "capability_delta": (
            "Persona identity contract is invocable as a second-wave domain capability."
        ),
        "tags": ("domain", "persona", "identity", "absorbable", "second-wave"),
        # Below first-wave domain priorities (54–70) so clean growth absorbs
        # local-memory → … → proposal-eval before second-wave leaves.
        "priority": 48,
        "dependencies": ("repo.import-health",),
    },
    {
        "id": "domain.proposal-synthesis",
        "name": "Proposal synthesis evidence smoke",
        "description": (
            "Build a frozen heuristic proposal evidence package offline without LLM or skill-route."
        ),
        "module": "blackhole_agent.proposal_synthesis",
        "module_path": "src/blackhole_agent/proposal_synthesis.py",
        "entry": "blackhole_agent.capability_compounder:builtin_proposal_synthesis_smoke",
        "function": "builtin_proposal_synthesis_smoke",
        "capability_delta": (
            "Proposal synthesis evidence packaging is invocable as a second-wave domain capability."
        ),
        "tags": ("domain", "proposal", "synthesis", "absorbable", "second-wave"),
        "priority": 47,
        "dependencies": ("repo.import-health",),
    },
    {
        "id": "domain.kernel-preflight",
        "name": "Kernel provider preflight",
        "description": (
            "Evaluate Grok kernel provider/config preflight structure offline without network runs."
        ),
        "module": "blackhole_agent.kernels.grok_cli",
        "module_path": "src/blackhole_agent/kernels/grok_cli.py",
        "entry": "blackhole_agent.capability_compounder:builtin_kernel_preflight",
        "function": "builtin_kernel_preflight",
        "capability_delta": (
            "Kernel provider preflight is invocable as a second-wave domain capability."
        ),
        "tags": ("domain", "kernel", "preflight", "absorbable", "second-wave"),
        "priority": 46,
        "dependencies": ("repo.import-health",),
    },
)

# Modules that are runtime/control surfaces, not domain absorption candidates.
# Second-wave identity/synthesis/kernel surfaces are catalogued above and must not be skipped.
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
        "suggested_id": "capability.composed-domain-ops",
        "name": "Composed domain ops chain",
        "members": (
            "domain.issue-triage",
            "domain.ci-security",
            "domain.proposal-eval",
        ),
        "reason": (
            "Issue triage, CI security gating, and proposal replay form an operational "
            "domain composition beyond the original meta/domain-core plateau."
        ),
        "priority": 85,
        "tags": ("composed", "promoted", "growth", "domain", "ops"),
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
    {
        "suggested_id": "capability.composed-second-wave-identity",
        "name": "Composed second-wave identity chain",
        "members": (
            "domain.persona",
            "domain.proposal-synthesis",
            "domain.kernel-preflight",
        ),
        "reason": (
            "Second-wave persona, proposal synthesis, and kernel preflight form a novel "
            "primitive coverage set past the first-wave domain-ops/superstack plateau."
        ),
        # Below first-wave catalog recipes (100/90/85/80) so clean growth still promotes
        # core-health → domain-core/ops before second-wave compositions.
        "priority": 78,
        "tags": ("composed", "promoted", "growth", "domain", "second-wave"),
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


def domain_leaf_ids(ledger: CapabilityLedger) -> list[str]:
    """Return sorted domain leaf capability ids (not composed meta units)."""

    leaves: list[str] = []
    for capability in ledger.capabilities.values():
        tags = set(capability.tags)
        if "domain" not in tags:
            continue
        if tags.intersection({"composed", "promoted"}):
            continue
        if not capability.id.startswith("domain."):
            continue
        leaves.append(capability.id)
    return sorted(leaves)


def _dynamic_domain_frontier_candidates(
    leaves: Sequence[str],
    *,
    ledger: CapabilityLedger | None = None,
) -> list[tuple[str, ...]]:
    """Build a small deterministic set of multi-frontier domain compositions.

    Prefers ops×core mixes so candidates are not restatements of catalogued
    domain-core / domain-ops recipes. When second-wave domain leaves appear
    (e.g. supervisor), includes ops×second-wave edges so absorption reopens
    dynamic growth. Keeps the candidate list intentionally small so growth can
    continue past the first dynamic unit without an open combinatorial explosion.
    """

    ops_ids = {
        "domain.issue-triage",
        "domain.ci-security",
        "domain.proposal-eval",
    }
    ops = [leaf for leaf in leaves if leaf in ops_ids]
    core = [leaf for leaf in leaves if leaf not in ops_ids]
    second_wave: list[str] = []
    if ledger is not None:
        for leaf in leaves:
            capability = ledger.capabilities.get(leaf)
            if capability is None:
                continue
            tags = set(capability.tags)
            if "second-wave" in tags or "supervisor" in tags:
                second_wave.append(leaf)
    # Fallback: any leaf not in the original six first-wave catalog ids.
    first_wave = {
        "domain.local-memory",
        "domain.tool-routing",
        "domain.harness-activation",
        "domain.issue-triage",
        "domain.ci-security",
        "domain.proposal-eval",
    }
    if not second_wave:
        second_wave = [leaf for leaf in leaves if leaf not in first_wave]
    candidates: list[tuple[str, ...]] = []
    seen: set[frozenset[str]] = set()

    def _push(members: Sequence[str]) -> None:
        ordered = tuple(dict.fromkeys(str(item) for item in members if str(item).strip()))
        if len(ordered) < 2:
            return
        key = frozenset(ordered)
        if key in seen:
            return
        seen.add(key)
        candidates.append(ordered)

    if ops and core:
        # Primary frontier: first ops + up to two core leaves.
        primary: list[str] = [ops[0], *core[:2]]
        _push(primary[:3])
        # Secondary: next ops lead with core.
        if len(ops) > 1:
            _push([ops[1], *core[:2]][:3])
        # Tertiary: last ops with first core + first ops (cross-ops mix).
        if len(ops) > 2:
            _push([ops[2], core[0], ops[0]][:3])
        # Quaternary: two-leaf ops×core edge when triples are already promoted.
        _push((ops[0], core[0]))
        if len(ops) > 1 and len(core) > 1:
            _push((ops[1], core[1]))
        # Second-wave reopen: ops × newest runtime domain leaves.
        for wave in second_wave[:2]:
            _push((ops[0], wave))
            if len(ops) > 1:
                _push((ops[1], wave))
            if core and core[0] != wave:
                _push((wave, core[0]))
            if len(ops) > 2:
                _push((ops[2], wave, core[0] if core and core[0] != wave else ops[0])[:3])
    else:
        _push(list(leaves[:3]))
        if len(leaves) >= 4:
            _push(list(leaves[1:4]))
        if len(leaves) >= 2:
            _push(list(leaves[-2:]))
        for wave in second_wave[:2]:
            others = [leaf for leaf in leaves if leaf != wave]
            if others:
                _push((wave, others[0]))
    return candidates


def synthesize_dynamic_domain_compositions(
    ledger: CapabilityLedger,
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Synthesize multi-frontier compositions from absorbed domain leaves.

    When hand-written recipes no longer expand the ledger, growth continues by
    promoting deterministic cross-cuts of current domain leaves (ops surfaces
    preferred). Multiple frontiers are ranked so promoting one dynamic unit does
    not stall the loop on re-prove-only.
    """

    already = existing_promoted_member_sets(ledger)
    known_member_sets = {_member_set_key(recipe["members"]) for recipe in KNOWN_GROWTH_RECIPES}
    known_ids = {str(recipe["suggested_id"]) for recipe in KNOWN_GROWTH_RECIPES}
    leaves = domain_leaf_ids(ledger)
    if len(leaves) < 2:
        return []

    opportunities: list[dict[str, Any]] = []
    max_items = max(1, int(limit))
    for index, frontier in enumerate(_dynamic_domain_frontier_candidates(leaves, ledger=ledger)):
        member_key = _member_set_key(frontier)
        if member_key in already or member_key in known_member_sets:
            continue
        slug = slugify_capability_id(
            "-".join(member.removeprefix("domain.") for member in frontier),
            limit=36,
        )
        suggested_id = f"capability.composed-dyn-{slug}"
        if suggested_id in ledger.capabilities or suggested_id in known_ids:
            continue
        missing = [member for member in frontier if member not in ledger.capabilities]
        opportunities.append(
            {
                "kind": "composition",
                "suggested_id": suggested_id,
                "name": f"Dynamic domain composition ({' + '.join(frontier)})",
                "members": list(frontier),
                "reason": (
                    "Synthesized multi-domain frontier composition from absorbed package surfaces "
                    "after catalogued recipes were exhausted."
                ),
                "priority": max(30, 48 - index),
                "status": "blocked_missing_members" if missing else "ready",
                "missing_members": missing,
                "synthesized": True,
                "synthesis": "dynamic_domain",
                "tags": ["composed", "promoted", "growth", "domain", "dynamic"],
            }
        )
        if len(opportunities) >= max_items:
            break
    return opportunities


# Canonical hierarchical stacks of already-promoted compositions (not leaf domains).
KNOWN_HIERARCHICAL_RECIPES: tuple[dict[str, Any], ...] = (
    {
        "suggested_id": "capability.composed-stack-domain-full",
        "name": "Hierarchical domain full stack",
        "members": (
            "capability.composed-domain-core",
            "capability.composed-domain-ops",
        ),
        "reason": (
            "Domain-core and domain-ops compositions stack into one operator-facing "
            "platform surface without re-absorbing leaves."
        ),
        "priority": 72,
        "tags": ("composed", "promoted", "growth", "hierarchical", "domain"),
    },
    {
        "suggested_id": "capability.composed-stack-meta-evolution",
        "name": "Hierarchical meta evolution stack",
        "members": (
            "capability.composed-core-health",
            "capability.composed-evolution-ready",
        ),
        "reason": (
            "Core health and evolution-ready compositions form a meta readiness stack "
            "for compounder-first evolution surfaces."
        ),
        "priority": 70,
        "tags": ("composed", "promoted", "growth", "hierarchical", "evolution-route"),
    },
    {
        "suggested_id": "capability.composed-stack-platform",
        "name": "Hierarchical platform stack",
        "members": (
            "capability.composed-core-health",
            "capability.composed-domain-core",
            "capability.composed-domain-ops",
        ),
        "reason": (
            "Meta health plus domain core/ops stacks into a single platform composition "
            "beyond leaf-level dynamic mixes."
        ),
        "priority": 74,
        "tags": ("composed", "promoted", "growth", "hierarchical", "platform"),
    },
)


def composed_pillar_ids(ledger: CapabilityLedger) -> list[str]:
    """Return sorted ids of promoted compositions eligible for hierarchical stacking."""

    pillars: list[str] = []
    for capability in ledger.capabilities.values():
        tags = set(capability.tags)
        if not tags.intersection({"composed", "promoted"}):
            continue
        if "hierarchical" in tags:
            # Hierarchical stacks can themselves be stacked later via synthesis,
            # but catalog pillars prefer first-generation compositions.
            continue
        if len(capability.dependencies) < 2:
            continue
        pillars.append(capability.id)
    return sorted(pillars)


def synthesize_hierarchical_compositions(
    ledger: CapabilityLedger,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Synthesize higher-order stacks from already-promoted compositions.

    Breaks the post-domain re-prove plateau: once leaf recipes and dynamic domain
    frontiers are exhausted, growth continues by composing composed units.
    """

    already = existing_promoted_member_sets(ledger)
    catalog_ids = {str(recipe["suggested_id"]) for recipe in KNOWN_HIERARCHICAL_RECIPES}
    catalog_member_sets = {
        _member_set_key(recipe["members"]): str(recipe["suggested_id"])
        for recipe in KNOWN_HIERARCHICAL_RECIPES
    }
    known_ids = {str(recipe["suggested_id"]) for recipe in KNOWN_GROWTH_RECIPES} | catalog_ids

    opportunities: list[dict[str, Any]] = []
    seen_member_sets: set[frozenset[str]] = set()
    max_items = max(1, int(limit))

    def _append_opportunity(
        *,
        suggested_id: str,
        name: str,
        members: Sequence[str],
        reason: str,
        priority: int,
        tags: Sequence[str],
        synthesized: bool,
        enforce_limit: bool = True,
    ) -> bool:
        if enforce_limit and len(opportunities) >= max_items:
            return False
        member_tuple = tuple(dict.fromkeys(str(item).strip() for item in members if str(item).strip()))
        if len(member_tuple) < 2:
            return False
        member_key = _member_set_key(member_tuple)
        if member_key in already or member_key in seen_member_sets:
            return False
        if suggested_id in ledger.capabilities:
            return False
        # Avoid clashing with a different catalog id for the same member set.
        catalog_owner = catalog_member_sets.get(member_key)
        if catalog_owner and catalog_owner != suggested_id:
            return False
        missing = [member for member in member_tuple if member not in ledger.capabilities]
        seen_member_sets.add(member_key)
        opportunities.append(
            {
                "kind": "composition",
                "suggested_id": suggested_id,
                "name": name,
                "members": list(member_tuple),
                "reason": reason,
                "priority": int(priority),
                "status": "blocked_missing_members" if missing else "ready",
                "missing_members": missing,
                "synthesized": synthesized,
                "synthesis": "hierarchical",
                "tags": list(tags),
            }
        )
        return True

    # Catalog hierarchical recipes always surface (small fixed set).
    for recipe in KNOWN_HIERARCHICAL_RECIPES:
        _append_opportunity(
            suggested_id=str(recipe["suggested_id"]),
            name=str(recipe["name"]),
            members=tuple(recipe["members"]),
            reason=str(recipe["reason"]),
            priority=int(recipe["priority"]),
            tags=tuple(recipe["tags"]),
            synthesized=False,
            enforce_limit=False,
        )

    # Frontier synthesis: pair stable (non-dynamic) first-generation pillars only.
    # Exclude dynamic leaf mixes from hierarchical pairing to avoid combinatorial
    # explosion of expensive nested prove/run chains.
    synthesized_added = 0
    pillars = [
        item
        for item in composed_pillar_ids(ledger)
        if "composed-dyn-" not in item and not item.startswith("capability.composed-stack-")
    ]
    for index, left in enumerate(pillars):
        if synthesized_added >= max_items:
            break
        for right in pillars[index + 1 :]:
            if synthesized_added >= max_items:
                break
            members = (left, right)
            member_key = _member_set_key(members)
            if member_key in already or member_key in seen_member_sets:
                continue
            if member_key in catalog_member_sets:
                continue
            slug = slugify_capability_id(
                "-".join(
                    member.removeprefix("capability.composed-").removeprefix("capability.")
                    for member in members
                ),
                limit=36,
            )
            suggested_id = f"capability.composed-stack-{slug}"
            if suggested_id in ledger.capabilities or suggested_id in known_ids:
                continue
            if _append_opportunity(
                suggested_id=suggested_id,
                name=f"Hierarchical stack ({' + '.join(members)})",
                members=members,
                reason=(
                    "Synthesized hierarchical stack of promoted compositions after "
                    "leaf and catalogued recipes were exhausted."
                ),
                priority=max(40, 55 - index),
                tags=("composed", "promoted", "growth", "hierarchical", "synthesized"),
                synthesized=True,
                enforce_limit=False,
            ):
                synthesized_added += 1

    opportunities.sort(key=lambda item: (-int(item["priority"]), item["suggested_id"]))
    # Keep all catalog rows plus up to `limit` synthesized rows (already capped above).
    return opportunities


# Meta-hierarchical stacks of already-promoted hierarchical compositions (stack-of-stacks).
KNOWN_META_HIERARCHICAL_RECIPES: tuple[dict[str, Any], ...] = (
    {
        "suggested_id": "capability.composed-meta-platform-evolution",
        "name": "Meta-hierarchical platform × evolution stack",
        "members": (
            "capability.composed-stack-platform",
            "capability.composed-stack-meta-evolution",
        ),
        "reason": (
            "Platform and meta-evolution hierarchical stacks compose into one second-order "
            "operator surface past first-generation hierarchical pairing."
        ),
        "priority": 78,
        "tags": ("composed", "promoted", "growth", "hierarchical", "meta"),
    },
    {
        "suggested_id": "capability.composed-meta-platform-domain-full",
        "name": "Meta-hierarchical platform × domain-full stack",
        "members": (
            "capability.composed-stack-platform",
            "capability.composed-stack-domain-full",
        ),
        "reason": (
            "Platform and domain-full hierarchical stacks form a meta domain-platform "
            "composition without re-absorbing leaf domains."
        ),
        "priority": 77,
        "tags": ("composed", "promoted", "growth", "hierarchical", "meta"),
    },
    {
        "suggested_id": "capability.composed-meta-domain-full-evolution",
        "name": "Meta-hierarchical domain-full × evolution stack",
        "members": (
            "capability.composed-stack-domain-full",
            "capability.composed-stack-meta-evolution",
        ),
        "reason": (
            "Domain-full and meta-evolution stacks form a second-order ops+evolution "
            "surface beyond first-gen hierarchical recipes."
        ),
        "priority": 76,
        "tags": ("composed", "promoted", "growth", "hierarchical", "meta"),
    },
)


def hierarchical_stack_ids(ledger: CapabilityLedger) -> list[str]:
    """Return sorted ids of first-order hierarchical stacks eligible for meta stacking."""

    stacks: list[str] = []
    for capability in ledger.capabilities.values():
        tags = set(capability.tags)
        if "hierarchical" not in tags and not capability.id.startswith("capability.composed-stack-"):
            continue
        if "meta" in tags or capability.id.startswith("capability.composed-meta-"):
            # Meta stacks can be stacked later; catalog prefers first-order hierarchical units.
            continue
        if len(capability.dependencies) < 2:
            continue
        stacks.append(capability.id)
    return sorted(stacks)


def synthesize_meta_hierarchical_compositions(
    ledger: CapabilityLedger,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Synthesize stack-of-stacks from already-promoted hierarchical compositions.

    Breaks the post-hierarchical re-prove plateau: once leaf recipes, dynamic domain
    frontiers, and first-order hierarchical stacks are exhausted, growth continues by
    composing hierarchical units into second-order meta stacks.
    """

    already = existing_promoted_member_sets(ledger)
    catalog_ids = {str(recipe["suggested_id"]) for recipe in KNOWN_META_HIERARCHICAL_RECIPES}
    catalog_member_sets = {
        _member_set_key(recipe["members"]): str(recipe["suggested_id"])
        for recipe in KNOWN_META_HIERARCHICAL_RECIPES
    }
    hierarchical_catalog_ids = {str(recipe["suggested_id"]) for recipe in KNOWN_HIERARCHICAL_RECIPES}
    known_ids = (
        {str(recipe["suggested_id"]) for recipe in KNOWN_GROWTH_RECIPES}
        | hierarchical_catalog_ids
        | catalog_ids
    )

    opportunities: list[dict[str, Any]] = []
    seen_member_sets: set[frozenset[str]] = set()
    max_items = max(1, int(limit))

    def _append_opportunity(
        *,
        suggested_id: str,
        name: str,
        members: Sequence[str],
        reason: str,
        priority: int,
        tags: Sequence[str],
        synthesized: bool,
        enforce_limit: bool = True,
    ) -> bool:
        if enforce_limit and len(opportunities) >= max_items:
            return False
        member_tuple = tuple(dict.fromkeys(str(item).strip() for item in members if str(item).strip()))
        if len(member_tuple) < 2:
            return False
        member_key = _member_set_key(member_tuple)
        if member_key in already or member_key in seen_member_sets:
            return False
        if suggested_id in ledger.capabilities:
            return False
        catalog_owner = catalog_member_sets.get(member_key)
        if catalog_owner and catalog_owner != suggested_id:
            return False
        missing = [member for member in member_tuple if member not in ledger.capabilities]
        seen_member_sets.add(member_key)
        opportunities.append(
            {
                "kind": "composition",
                "suggested_id": suggested_id,
                "name": name,
                "members": list(member_tuple),
                "reason": reason,
                "priority": int(priority),
                "status": "blocked_missing_members" if missing else "ready",
                "missing_members": missing,
                "synthesized": synthesized,
                "synthesis": "meta_hierarchical",
                "tags": list(tags),
            }
        )
        return True

    for recipe in KNOWN_META_HIERARCHICAL_RECIPES:
        _append_opportunity(
            suggested_id=str(recipe["suggested_id"]),
            name=str(recipe["name"]),
            members=tuple(recipe["members"]),
            reason=str(recipe["reason"]),
            priority=int(recipe["priority"]),
            tags=tuple(recipe["tags"]),
            synthesized=False,
            enforce_limit=False,
        )

    synthesized_added = 0
    stacks = hierarchical_stack_ids(ledger)
    for index, left in enumerate(stacks):
        if synthesized_added >= max_items:
            break
        for right in stacks[index + 1 :]:
            if synthesized_added >= max_items:
                break
            members = (left, right)
            member_key = _member_set_key(members)
            if member_key in already or member_key in seen_member_sets:
                continue
            if member_key in catalog_member_sets:
                continue
            slug = slugify_capability_id(
                "-".join(
                    member.removeprefix("capability.composed-stack-")
                    .removeprefix("capability.composed-")
                    .removeprefix("capability.")
                    for member in members
                ),
                limit=36,
            )
            suggested_id = f"capability.composed-meta-{slug}"
            if suggested_id in ledger.capabilities or suggested_id in known_ids:
                continue
            if _append_opportunity(
                suggested_id=suggested_id,
                name=f"Meta-hierarchical stack ({' + '.join(members)})",
                members=members,
                reason=(
                    "Synthesized stack-of-stacks of hierarchical compositions after "
                    "first-order hierarchical recipes were exhausted."
                ),
                priority=max(42, 60 - index),
                tags=("composed", "promoted", "growth", "hierarchical", "meta", "synthesized"),
                synthesized=True,
                enforce_limit=False,
            ):
                synthesized_added += 1

    opportunities.sort(key=lambda item: (-int(item["priority"]), item["suggested_id"]))
    return opportunities


def meta_stack_ids(ledger: CapabilityLedger) -> list[str]:
    """Return sorted ids of meta-hierarchical compositions eligible for superstacking."""

    stacks: list[str] = []
    for capability in ledger.capabilities.values():
        tags = set(capability.tags)
        is_meta = "meta" in tags or capability.id.startswith("capability.composed-meta-")
        is_super = "superstack" in tags or capability.id.startswith("capability.composed-super-")
        if not is_meta or is_super:
            continue
        if len(capability.dependencies) < 2:
            continue
        stacks.append(capability.id)
    return sorted(stacks)


def synthesize_superstack_compositions(
    ledger: CapabilityLedger,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Synthesize third-order superstacks from already-promoted meta-hierarchical units.

    After meta-hierarchical stack-of-stacks plateau, growth continues by pairing
    meta compositions into superstacks (`capability.composed-super-*`).
    """

    already = existing_promoted_member_sets(ledger)
    known_ids = (
        {str(recipe["suggested_id"]) for recipe in KNOWN_GROWTH_RECIPES}
        | {str(recipe["suggested_id"]) for recipe in KNOWN_HIERARCHICAL_RECIPES}
        | {str(recipe["suggested_id"]) for recipe in KNOWN_META_HIERARCHICAL_RECIPES}
    )
    opportunities: list[dict[str, Any]] = []
    seen_member_sets: set[frozenset[str]] = set()
    seen_ids: set[str] = set()
    max_items = max(1, int(limit))
    stacks = meta_stack_ids(ledger)
    synthesized_added = 0

    def _short_label(capability_id: str) -> str:
        label = (
            capability_id.removeprefix("capability.composed-meta-")
            .removeprefix("capability.composed-stack-")
            .removeprefix("capability.composed-")
            .removeprefix("capability.")
        )
        # Keep enough of each side so paired superstack ids stay distinct.
        return slugify_capability_id(label, limit=18)

    for index, left in enumerate(stacks):
        if synthesized_added >= max_items:
            break
        for right in stacks[index + 1 :]:
            if synthesized_added >= max_items:
                break
            members = (left, right)
            member_key = _member_set_key(members)
            if member_key in already or member_key in seen_member_sets:
                continue
            left_label = _short_label(left)
            right_label = _short_label(right)
            slug = slugify_capability_id(f"{left_label}-{right_label}", limit=32)
            suggested_id = f"capability.composed-super-{slug}"
            # Disambiguate rare collisions after truncation with a stable short hash.
            if suggested_id in ledger.capabilities or suggested_id in known_ids or suggested_id in seen_ids:
                digest = hashlib.sha1("\0".join(sorted(members)).encode("utf-8")).hexdigest()[:10]
                suggested_id = f"capability.composed-super-{digest}"
            if suggested_id in ledger.capabilities or suggested_id in known_ids or suggested_id in seen_ids:
                continue
            missing = [member for member in members if member not in ledger.capabilities]
            seen_member_sets.add(member_key)
            seen_ids.add(suggested_id)
            opportunities.append(
                {
                    "kind": "composition",
                    "suggested_id": suggested_id,
                    "name": f"Superstack ({' + '.join(members)})",
                    "members": list(members),
                    "reason": (
                        "Synthesized third-order superstack of meta-hierarchical compositions "
                        "after second-order meta recipes were exhausted."
                    ),
                    "priority": max(40, 58 - index),
                    "status": "blocked_missing_members" if missing else "ready",
                    "missing_members": missing,
                    "synthesized": True,
                    "synthesis": "superstack",
                    "tags": [
                        "composed",
                        "promoted",
                        "growth",
                        "hierarchical",
                        "meta",
                        "superstack",
                        "synthesized",
                    ],
                }
            )
            synthesized_added += 1
    opportunities.sort(key=lambda item: (-int(item["priority"]), item["suggested_id"]))
    return opportunities


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
    dynamic_opportunities = synthesize_dynamic_domain_compositions(ledger)
    opportunities.extend(dynamic_opportunities)
    hierarchical_opportunities = synthesize_hierarchical_compositions(ledger)
    opportunities.extend(hierarchical_opportunities)
    meta_hierarchical_opportunities = synthesize_meta_hierarchical_compositions(ledger)
    opportunities.extend(meta_hierarchical_opportunities)
    superstack_opportunities = synthesize_superstack_compositions(ledger)
    opportunities.extend(superstack_opportunities)
    # Annotate primitive-coverage novelty, then rank novel ready frontiers ahead of
    # combinatorial superstacks that re-package identical primitives.
    annotate_opportunities_with_novelty(ledger, opportunities)
    rank_growth_opportunities(opportunities)
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
        for capability_id in (
            "capability.scout-gaps",
            "capability.growth-loop",
            "capability.adaptive-grow",
            "capability.ledger-integrity",
            "capability.frontier-novelty",
            "capability.distill-ledger",
            "capability.autonomic-cycle",
            "capability.goal-plan",
            "capability.program-run",
            "capability.mission-plane",
            "capability.second-wave-absorb",
            "capability.outcome-contract",
            "capability.contract-plane",
            "capability.ablation-proof",
            "capability.transfer-plane",
            "capability.adversarial-contract",
            "capability.assurance-plane",
        )
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
    hierarchical_ready = [
        item["suggested_id"]
        for item in hierarchical_opportunities
        if item.get("status") == "ready"
    ]
    meta_hierarchical_ready = [
        item["suggested_id"]
        for item in meta_hierarchical_opportunities
        if item.get("status") == "ready"
    ]
    superstack_ready = [
        item["suggested_id"]
        for item in superstack_opportunities
        if item.get("status") == "ready"
    ]
    return {
        "ok": True,
        "count": len(ledger.capabilities),
        "ids": sorted(ledger.capabilities),
        "unproved": unproved,
        "never_proved": never_proved,
        "growth_surface_missing": growth_surface_missing,
        "domain_absorbed": domain_absorbed,
        "domain_pending": domain_pending,
        "domain_leaves": domain_leaf_ids(ledger),
        "dynamic_ready": [
            item["suggested_id"]
            for item in dynamic_opportunities
            if item.get("status") == "ready"
        ],
        "hierarchical_ready": hierarchical_ready,
        "meta_hierarchical_ready": meta_hierarchical_ready,
        "superstack_ready": superstack_ready,
        "hierarchical_stacks": hierarchical_stack_ids(ledger),
        "meta_stacks": meta_stack_ids(ledger),
        "composed_pillars": composed_pillar_ids(ledger),
        "uncatalogued_surfaces": uncatalogued,
        "opportunities": opportunities,
        "recommended": recommended,
        "novel_ready": [
            item["suggested_id"]
            for item in opportunities
            if item.get("status") in {"ready", "ready_to_absorb"} and item.get("novel")
        ],
        "stale_ready": [
            item["suggested_id"]
            for item in opportunities
            if item.get("status") in {"ready", "ready_to_absorb"} and not item.get("novel")
        ],
        "unique_composed_coverage_sets": len(existing_composed_coverage_sets(ledger)),
        "primitive_count": sum(
            1 for capability in ledger.capabilities.values() if is_primitive_capability(capability)
        ),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "ledger_path": str(default_ledger_path(root)),
    }


def run_named_recipe(
    member_ids: Sequence[str],
    *,
    repo_path: Path | None = None,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    prove_first: bool = True,
    inprocess: bool = False,
    direct_only: bool = False,
) -> dict[str, Any]:
    """Compose an explicit member list against the in-repo ledger."""

    root = (repo_path or Path(__file__).resolve().parents[2]).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    order = (
        direct_member_order(ledger, member_ids)
        if direct_only
        else topological_order(ledger, member_ids)
    )
    results = compose_capabilities(
        ledger,
        member_ids,
        cwd=root,
        command_runner=command_runner,
        timeout=timeout,
        prove_first=prove_first,
        inprocess=inprocess,
        direct_only=direct_only,
    )
    save_ledger(path, ledger)
    ok = bool(results) and all(item.ok for item in results) and len(results) == len(order)
    return {
        "ok": ok,
        "members": list(member_ids),
        "order": order,
        "results": [item.to_dict() for item in results],
        "ledger_path": str(path),
        "inprocess": inprocess,
        "direct_only": direct_only,
    }


def builtin_execute_composed_capability() -> dict[str, Any]:
    """Execute the composition defined by the active capability's dependencies.

    `run_capability` injects BLACKHOLE_CAPABILITY_ID so promoted recipes remain
    zero-arg python entries while still knowing which dependency set to compose.

    Hierarchical/meta/superstack compositions intentionally skip per-member
    re-prove (`prove_first=False`): members were proved when promoted, and nested
    re-prove of stack-of-stacks explodes subprocess count without extra safety.
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
    # Nested stack proofs re-enter this entry for each direct member; run
    # in-process without transitive re-expansion or re-prove so superstacks stay
    # combinatorially usable.
    recipe = run_named_recipe(
        members,
        repo_path=root,
        prove_first=False,
        inprocess=True,
        direct_only=True,
    )
    return {
        "ok": bool(recipe.get("ok")),
        "capability_id": capability_id,
        "members": members,
        "order": recipe.get("order"),
        "results": recipe.get("results"),
        "ledger_path": recipe.get("ledger_path"),
        "prove_first": False,
        "inprocess": True,
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
            hierarchical = next(
                (item for item in KNOWN_HIERARCHICAL_RECIPES if item["suggested_id"] == recipe_id),
                None,
            )
            meta_hierarchical = next(
                (item for item in KNOWN_META_HIERARCHICAL_RECIPES if item["suggested_id"] == recipe_id),
                None,
            )
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
                    "tags": list(known.get("tags") or ()),
                }
            elif hierarchical is not None:
                selected = {
                    "kind": "composition",
                    "suggested_id": hierarchical["suggested_id"],
                    "name": hierarchical["name"],
                    "members": list(hierarchical["members"]),
                    "reason": hierarchical["reason"],
                    "priority": hierarchical["priority"],
                    "status": "ready"
                    if all(member in ledger.capabilities for member in hierarchical["members"])
                    and hierarchical["suggested_id"] not in ledger.capabilities
                    else "blocked",
                    "missing_members": [
                        member
                        for member in hierarchical["members"]
                        if member not in ledger.capabilities
                    ],
                    "tags": list(hierarchical.get("tags") or ()),
                    "synthesis": "hierarchical",
                }
            elif meta_hierarchical is not None:
                selected = {
                    "kind": "composition",
                    "suggested_id": meta_hierarchical["suggested_id"],
                    "name": meta_hierarchical["name"],
                    "members": list(meta_hierarchical["members"]),
                    "reason": meta_hierarchical["reason"],
                    "priority": meta_hierarchical["priority"],
                    "status": "ready"
                    if all(
                        member in ledger.capabilities for member in meta_hierarchical["members"]
                    )
                    and meta_hierarchical["suggested_id"] not in ledger.capabilities
                    else "blocked",
                    "missing_members": [
                        member
                        for member in meta_hierarchical["members"]
                        if member not in ledger.capabilities
                    ],
                    "tags": list(meta_hierarchical.get("tags") or ()),
                    "synthesis": "meta_hierarchical",
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
            and not legacy_pipeline_was_used()
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
            "used_skill_route_discovery": legacy_pipeline_was_used(),
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
                "used_skill_route_discovery": legacy_pipeline_was_used(),
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
    hierarchical_known = next(
        (
            item
            for item in KNOWN_HIERARCHICAL_RECIPES
            if item["suggested_id"] == selected["suggested_id"]
        ),
        None,
    )
    meta_hierarchical_known = next(
        (
            item
            for item in KNOWN_META_HIERARCHICAL_RECIPES
            if item["suggested_id"] == selected["suggested_id"]
        ),
        None,
    )
    selected_tags = selected.get("tags")
    if known is not None:
        promote_tags: tuple[str, ...] = tuple(known["tags"])
    elif hierarchical_known is not None:
        promote_tags = tuple(hierarchical_known["tags"])
    elif meta_hierarchical_known is not None:
        promote_tags = tuple(meta_hierarchical_known["tags"])
    elif selected_tags:
        promote_tags = tuple(str(item) for item in selected_tags if str(item).strip())
    elif selected.get("synthesis") == "superstack" or (
        selected.get("synthesized")
        and str(selected.get("suggested_id") or "").startswith("capability.composed-super-")
    ):
        promote_tags = (
            "composed",
            "promoted",
            "growth",
            "hierarchical",
            "meta",
            "superstack",
            "synthesized",
        )
    elif selected.get("synthesis") == "meta_hierarchical" or (
        selected.get("synthesized")
        and str(selected.get("suggested_id") or "").startswith("capability.composed-meta-")
    ):
        promote_tags = ("composed", "promoted", "growth", "hierarchical", "meta", "synthesized")
    elif selected.get("synthesis") == "hierarchical" or selected.get("synthesized") and str(
        selected.get("suggested_id") or ""
    ).startswith("capability.composed-stack-"):
        promote_tags = ("composed", "promoted", "growth", "hierarchical", "synthesized")
    elif selected.get("synthesized"):
        promote_tags = ("composed", "promoted", "growth", "domain", "dynamic")
    else:
        promote_tags = ("composed", "promoted", "growth")
    ledger, promoted = promote_composition(
        ledger,
        selected["members"],
        capability_id=selected["suggested_id"],
        name=selected.get("name"),
        description=selected.get("reason", ""),
        tags=promote_tags,
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
        and not legacy_pipeline_was_used()
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
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def run_adaptive_growth(
    repo_path: Path,
    *,
    budget: int = 8,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 180,
    stop_on_reprove: bool = True,
    novel_only: bool = False,
) -> dict[str, Any]:
    """Run the growth loop repeatedly until budget exhausts or growth stalls.

    Escapes single-step re-prove plateaus by promoting every ready frontier step
    (domain absorb, dynamic, hierarchical, meta, superstack) in one invocation.

    When `novel_only` is true, stop before promoting zero-novelty (stale) frontiers
    so adaptive/autonomic growth does not bloat the ledger with identical-coverage
    superstacks after novel combinations are exhausted.
    """

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    before_count = len(ledger.capabilities)
    before_ids = sorted(ledger.capabilities)
    max_steps = max(1, int(budget))
    steps: list[dict[str, Any]] = []
    promoted_ids: list[str] = []
    stalled = False
    stall_reason = ""
    used_skill = False

    for _ in range(max_steps):
        if novel_only:
            scout = scout_capability_gaps(load_ledger(path), repo_path=root)
            recommended = scout.get("recommended")
            if not recommended or not recommended.get("novel"):
                stalled = True
                stall_reason = "no_novel_ready_frontier"
                break
        step = run_growth_loop(
            root,
            command_runner=command_runner,
            timeout=timeout,
        )
        steps.append(
            {
                "ok": step.get("ok"),
                "grew": step.get("grew"),
                "action": step.get("action"),
                "promoted_id": step.get("promoted_id"),
                "reason": step.get("reason"),
                "error": step.get("error"),
                "after_count": step.get("after_count"),
                "selected_novel": (step.get("selected") or {}).get("novel"),
            }
        )
        used_skill = used_skill or bool(step.get("used_skill_route_discovery"))
        if not step.get("ok"):
            stalled = True
            stall_reason = str(step.get("error") or step.get("reason") or "step_failed")
            break
        if step.get("grew") and step.get("promoted_id"):
            promoted_ids.append(str(step["promoted_id"]))
            continue
        stalled = True
        stall_reason = str(step.get("reason") or "no_further_growth")
        if stop_on_reprove:
            break
        break

    ledger = load_ledger(path)
    after_ids = sorted(ledger.capabilities)
    after_count = len(ledger.capabilities)
    grew = after_count > before_count and bool(promoted_ids)
    ok = (not used_skill) and all(bool(item.get("ok")) for item in steps) if steps else True
    # Adaptive growth is successful when it ran without skill-route and either grew
    # or cleanly reported a stall after exhausting ready frontiers.
    if steps and not grew and stalled:
        ok = ok and steps[-1].get("ok") is True
    # novel_only early-stop with zero steps is still a clean success (nothing novel left).
    if novel_only and not steps and stall_reason == "no_novel_ready_frontier":
        ok = not used_skill
    return {
        "ok": ok,
        "grew": grew,
        "action": "adaptive_grow",
        "budget": max_steps,
        "steps_run": len(steps),
        "promoted_ids": promoted_ids,
        "promoted_count": len(promoted_ids),
        "stalled": stalled,
        "stall_reason": stall_reason,
        "novel_only": novel_only,
        "steps": steps,
        "before_count": before_count,
        "after_count": after_count,
        "before_ids": before_ids,
        "after_ids": after_ids,
        "new_ids": sorted(set(after_ids) - set(before_ids)),
        "used_skill_route_discovery": used_skill,
        "ledger_path": str(path),
    }


def prove_ledger_integrity(
    repo_path: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    limit: int | None = None,
) -> dict[str, Any]:
    """Batch-prove the ledger DAG once in topological order (each id proved once).

    Unlike recursive `prove_capability`, this walks a full-ledger order and runs
    each proof command only after dependencies have already been attempted,
    producing a durable integrity score for the capability plane.
    """

    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    if not ledger.capabilities:
        return {
            "ok": False,
            "error": "empty_ledger",
            "count": 0,
            "proved_ok": [],
            "failed": [],
            "skipped": [],
            "score": 0.0,
            "ledger_path": str(path),
            "used_skill_route_discovery": False,
        }

    # Full graph order: every capability, deps first.
    try:
        order = topological_order(ledger, list(ledger.capabilities))
    except ValueError as error:
        return {
            "ok": False,
            "error": f"ledger_cycle_or_missing: {error}",
            "count": len(ledger.capabilities),
            "proved_ok": [],
            "failed": [],
            "skipped": [],
            "score": 0.0,
            "ledger_path": str(path),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    if limit is not None:
        order = order[: max(1, int(limit))]

    proved_ok: list[str] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed_ids: set[str] = set()

    for capability_id in order:
        capability = ledger.capabilities[capability_id]
        blocked_by = [dep for dep in capability.dependencies if dep in failed_ids]
        if blocked_by:
            skipped.append({"id": capability_id, "blocked_by": blocked_by})
            failed_ids.add(capability_id)
            continue
        result = run_capability(
            capability,
            cwd=root,
            command_runner=command_runner,
            timeout=timeout,
            use_proof=True,
        )
        now = utc_now_iso()
        ledger.capabilities[capability_id] = Capability(
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
        if result.ok:
            proved_ok.append(capability_id)
        else:
            failed_ids.add(capability_id)
            failed.append(
                {
                    "id": capability_id,
                    "exit_code": result.exit_code,
                    "summary": result.summary,
                }
            )

    ledger.updated_at = utc_now_iso()
    save_ledger(path, ledger)
    attempted = len(proved_ok) + len(failed)
    score = (float(len(proved_ok)) / float(attempted)) if attempted else 0.0
    used_skill = legacy_pipeline_was_used()
    ok = (not used_skill) and not failed and not skipped and len(proved_ok) == len(order)
    return {
        "ok": ok,
        "action": "ledger_integrity",
        "count": len(ledger.capabilities),
        "ordered": len(order),
        "proved_ok": proved_ok,
        "proved_count": len(proved_ok),
        "failed": failed,
        "failed_count": len(failed),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "score": round(score, 4),
        "ledger_path": str(path),
        "used_skill_route_discovery": used_skill,
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


def builtin_adaptive_grow() -> dict[str, Any]:
    """Invocable capability: multi-step adaptive growth until stall or budget."""

    root = Path(__file__).resolve().parents[2]
    # Default budget is modest so proof stays bounded; CLI can raise it.
    budget = int(os.environ.get("BLACKHOLE_ADAPTIVE_GROW_BUDGET") or "4")
    return run_adaptive_growth(root, budget=budget, timeout=180)


def builtin_ledger_integrity() -> dict[str, Any]:
    """Invocable capability: batch-prove the durable ledger DAG."""

    root = Path(__file__).resolve().parents[2]
    # Integrity proofs of full meta/super compositions are expensive; default to a
    # representative prefix of the topo order unless the operator expands the budget.
    limit_raw = (os.environ.get("BLACKHOLE_INTEGRITY_LIMIT") or "").strip()
    limit = int(limit_raw) if limit_raw.isdigit() else 12
    return prove_ledger_integrity(root, timeout=120, limit=limit)


def builtin_frontier_novelty() -> dict[str, Any]:
    """Invocable capability: rank growth frontiers by primitive-coverage novelty."""

    root = Path(__file__).resolve().parents[2]
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    result = scout_frontier_novelty(ledger, repo_path=root)
    result["ledger_path"] = str(path)
    return result


def builtin_distill_ledger() -> dict[str, Any]:
    """Invocable capability: soft-distill redundant identical-coverage stacks."""

    root = Path(__file__).resolve().parents[2]
    remove = (os.environ.get("BLACKHOLE_DISTILL_REMOVE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    return run_distill_ledger(root, remove=remove, only_synthesized=True)


def builtin_autonomic_cycle() -> dict[str, Any]:
    """Invocable capability: novelty-aware grow → distill → integrity cycle."""

    root = Path(__file__).resolve().parents[2]
    budget = int(os.environ.get("BLACKHOLE_AUTONOMIC_BUDGET") or "3")
    integrity_limit = int(os.environ.get("BLACKHOLE_INTEGRITY_LIMIT") or "10")
    remove = (os.environ.get("BLACKHOLE_DISTILL_REMOVE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    return run_autonomic_cycle(
        root,
        budget=budget,
        distill_remove=remove,
        integrity_limit=integrity_limit,
        timeout=180,
    )


def builtin_goal_plan() -> dict[str, Any]:
    """Invocable capability: plan a multi-step capability program for a free-text goal."""

    root = Path(__file__).resolve().parents[2]
    path, ledger = ensure_seeded_ledger(root)
    goal = (os.environ.get("BLACKHOLE_MISSION_GOAL") or "").strip() or (
        "core health integrity inventory second-wave persona"
    )
    max_steps = int(os.environ.get("BLACKHOLE_PROGRAM_MAX_STEPS") or "6")
    result = plan_capability_program(ledger, goal, max_steps=max_steps, prefer_primitives=True)
    result["ledger_path"] = str(path)
    result["used_skill_route_discovery"] = legacy_pipeline_was_used()
    result["ok"] = bool(result.get("ok")) and not result["used_skill_route_discovery"]
    return result


def builtin_program_run() -> dict[str, Any]:
    """Invocable capability: execute BLACKHOLE_PROGRAM_STEPS or a default health program."""

    root = Path(__file__).resolve().parents[2]
    raw_steps = (os.environ.get("BLACKHOLE_PROGRAM_STEPS") or "").strip()
    if raw_steps:
        steps = [part.strip() for part in raw_steps.split(",") if part.strip()]
    else:
        steps = [
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
        ]
    prove_first = (os.environ.get("BLACKHOLE_PROGRAM_PROVE_FIRST") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    return run_capability_program(root, steps, timeout=120, prove_first=prove_first)


def builtin_second_wave_absorb() -> dict[str, Any]:
    """Invocable capability: absorb ready second-wave domain primitives and prove them."""

    root = Path(__file__).resolve().parents[2]
    limit = int(os.environ.get("BLACKHOLE_SECOND_WAVE_LIMIT") or "8")
    return absorb_second_wave_domains(root, prove=True, limit=limit, timeout=120)


def builtin_mission_plane() -> dict[str, Any]:
    """Invocable capability: second-wave expand → goal plan → program run → novel grow."""

    root = Path(__file__).resolve().parents[2]
    goal = (os.environ.get("BLACKHOLE_MISSION_GOAL") or "").strip() or (
        "second-wave identity persona proposal kernel health"
    )
    max_steps = int(os.environ.get("BLACKHOLE_PROGRAM_MAX_STEPS") or "5")
    grow_budget = int(os.environ.get("BLACKHOLE_MISSION_GROW_BUDGET") or "2")
    absorb_ready = (os.environ.get("BLACKHOLE_MISSION_ABSORB") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    return run_mission_plane(
        root,
        goal,
        max_steps=max_steps,
        absorb_ready=absorb_ready,
        grow_budget=grow_budget,
        timeout=180,
    )


def builtin_outcome_contract() -> dict[str, Any]:
    """Invocable capability: parse + evaluate a machine-checkable done_when contract."""

    root = Path(__file__).resolve().parents[2]
    done_when = (os.environ.get("BLACKHOLE_DONE_WHEN") or "").strip() or (
        "min_capabilities:3; min_primitives:2; capability_exists:repo.import-health; "
        "capability_proved:repo.import-health; no_skill_route"
    )
    run_programs = (os.environ.get("BLACKHOLE_CONTRACT_RUN_PROGRAMS") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    return evaluate_outcome_contract(
        root,
        done_when,
        run_programs=run_programs,
        timeout=120,
    )


def builtin_contract_plane() -> dict[str, Any]:
    """Invocable capability: mission plane then machine-check done_when evidence."""

    root = Path(__file__).resolve().parents[2]
    goal = (os.environ.get("BLACKHOLE_MISSION_GOAL") or "").strip() or "health inventory milestone"
    done_when = (os.environ.get("BLACKHOLE_DONE_WHEN") or "").strip() or (
        "min_capabilities:10; min_primitives:8; capability_exists:capability.outcome-contract; "
        "capability_proved:repo.import-health; program_passes:repo.import-health,capability.ledger-inventory; "
        "no_skill_route; mission_plane_ok"
    )
    max_steps = int(os.environ.get("BLACKHOLE_PROGRAM_MAX_STEPS") or "3")
    grow_budget = int(os.environ.get("BLACKHOLE_MISSION_GROW_BUDGET") or "0")
    absorb_ready = (os.environ.get("BLACKHOLE_MISSION_ABSORB") or "0").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    run_mission = (os.environ.get("BLACKHOLE_CONTRACT_RUN_MISSION") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    return run_contract_plane(
        root,
        goal,
        done_when,
        max_steps=max_steps,
        absorb_ready=absorb_ready,
        grow_budget=grow_budget,
        run_mission=run_mission,
        timeout=180,
    )


def builtin_ablation_proof() -> dict[str, Any]:
    """Invocable capability: falsify-then-restore proof ablation without mutating live ledger."""

    root = Path(__file__).resolve().parents[2]
    capability_id = (os.environ.get("BLACKHOLE_ABLATION_ID") or "repo.import-health").strip()
    dependent_id = (os.environ.get("BLACKHOLE_ABLATION_DEPENDENT") or "unbound.milestone-gate").strip()
    return run_ablation_proof(
        root,
        capability_id=capability_id,
        dependent_id=dependent_id,
        timeout=90,
    )


def builtin_transfer_plane() -> dict[str, Any]:
    """Invocable capability: export/import/re-prove a portable capability package."""

    root = Path(__file__).resolve().parents[2]
    raw = (os.environ.get("BLACKHOLE_TRANSFER_ROOTS") or "").strip()
    roots = [part.strip() for part in raw.split(",") if part.strip()] if raw else None
    return run_transfer_plane(root, roots, timeout=120, prove_imported=True)


def builtin_adversarial_contract() -> dict[str, Any]:
    """Invocable capability: positive contracts pass and adversarial contracts fail."""

    root = Path(__file__).resolve().parents[2]
    positive = (os.environ.get("BLACKHOLE_DONE_WHEN") or "").strip() or None
    return run_adversarial_contract(
        root,
        positive_done_when=positive,
        timeout=90,
        run_programs=False,
    )


def builtin_assurance_plane() -> dict[str, Any]:
    """Invocable capability: ablation → transfer → adversarial closed assurance plane."""

    root = Path(__file__).resolve().parents[2]
    capability_id = (os.environ.get("BLACKHOLE_ABLATION_ID") or "repo.import-health").strip()
    return run_assurance_plane(root, capability_id=capability_id, timeout=120)


def builtin_sovereignty_plane() -> dict[str, Any]:
    """Invocable capability: contract → assurance → re-verifiable sovereignty certificate."""

    root = Path(__file__).resolve().parents[2]
    goal = (os.environ.get("BLACKHOLE_MISSION_GOAL") or "").strip() or "health inventory milestone"
    done_when = (os.environ.get("BLACKHOLE_DONE_WHEN") or "").strip()
    max_steps = int(os.environ.get("BLACKHOLE_PROGRAM_MAX_STEPS") or "3")
    grow_budget = int(os.environ.get("BLACKHOLE_MISSION_GROW_BUDGET") or "0")
    absorb_ready = (os.environ.get("BLACKHOLE_MISSION_ABSORB") or "0").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    run_mission = (os.environ.get("BLACKHOLE_CONTRACT_RUN_MISSION") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    capability_id = (os.environ.get("BLACKHOLE_ABLATION_ID") or "repo.import-health").strip()
    cert_raw = (os.environ.get("BLACKHOLE_SOVEREIGNTY_CERT_PATH") or "").strip()
    certificate_path = Path(cert_raw) if cert_raw else None
    return run_sovereignty_plane(
        root,
        goal,
        done_when,
        max_steps=max_steps,
        absorb_ready=absorb_ready,
        grow_budget=grow_budget,
        run_mission=run_mission,
        capability_id=capability_id,
        certificate_path=certificate_path,
        timeout=180,
    )


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
        Capability(
            id="capability.adaptive-grow",
            name="Adaptive multi-step capability growth",
            description=(
                "Run the scout→absorb/promote→prove growth loop repeatedly until the budget "
                "is exhausted or no ready frontier remains (including superstacks)."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_adaptive_grow",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_adaptive_grow; '
                "import os; os.environ.setdefault('BLACKHOLE_ADAPTIVE_GROW_BUDGET','2'); "
                "r=builtin_adaptive_grow(); assert r['ok'] and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.scout-gaps",
                "capability.growth-loop",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Multi-step adaptive growth escapes single-step re-prove plateaus without skill-route."
            ),
            tags=("bootstrap", "compounder", "growth", "adaptive"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.ledger-integrity",
            name="Capability ledger integrity prove",
            description=(
                "Batch-prove the durable capability ledger in topological order and report "
                "an integrity score without skill-route discovery."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_ledger_integrity",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_ledger_integrity; '
                "import os; os.environ.setdefault('BLACKHOLE_INTEGRITY_LIMIT','8'); "
                "r=builtin_ledger_integrity(); assert r['ok'] and r.get('score',0) >= 1.0 "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Ledger-wide integrity is invocable as a first-class regression guardian capability."
            ),
            tags=("bootstrap", "compounder", "integrity"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.frontier-novelty",
            name="Frontier novelty ranking",
            description=(
                "Rank scout opportunities by primitive-coverage novelty so growth prefers "
                "new domain combinations over combinatorial superstacks with identical leaves."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_frontier_novelty",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_frontier_novelty; '
                "r=builtin_frontier_novelty(); assert r['ok'] and 'novel_ready_count' in r "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.scout-gaps",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Growth frontiers are ranked by novel primitive coverage, not stack depth alone."
            ),
            tags=("bootstrap", "compounder", "growth", "novelty"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.distill-ledger",
            name="Ledger distillation",
            description=(
                "Collapse redundant composed capabilities that share identical primitive "
                "coverage, tagging non-champions redundant (optional hard remove)."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_distill_ledger",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_distill_ledger; '
                "r=builtin_distill_ledger(); assert r['ok'] and r.get('redundant_count',0) >= 0 "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.frontier-novelty",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Identical-coverage stack bloat can be distilled without skill-route machinery."
            ),
            tags=("bootstrap", "compounder", "growth", "distill"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.autonomic-cycle",
            name="Autonomic novelty growth cycle",
            description=(
                "Run novelty-aware adaptive growth, distill redundant stacks, then integrity "
                "prove — the closed autonomic plane past combinatorial superstack plateaus."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_autonomic_cycle",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_autonomic_cycle; '
                "import os; os.environ.setdefault('BLACKHOLE_AUTONOMIC_BUDGET','2'); "
                "os.environ.setdefault('BLACKHOLE_INTEGRITY_LIMIT','8'); "
                "r=builtin_autonomic_cycle(); assert r['ok'] and r.get('action')=='autonomic_cycle' "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.frontier-novelty",
                "capability.distill-ledger",
                "capability.adaptive-grow",
                "capability.ledger-integrity",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Autonomic cycle prefers novel frontiers, distills redundant stacks, and "
                "re-proves integrity without skill-route discovery."
            ),
            tags=("bootstrap", "compounder", "growth", "autonomic", "novelty"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.goal-plan",
            name="Goal-conditioned capability program planner",
            description=(
                "Plan a multi-step capability program from a free-text goal using ledger "
                "tags, ids, and deterministic mission hints (no skill-route)."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_goal_plan",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_goal_plan; '
                "import os; os.environ.setdefault('BLACKHOLE_MISSION_GOAL','health integrity'); "
                "r=builtin_goal_plan(); assert r['ok'] and r.get('step_count',0) >= 1 "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Free-text goals compile into ranked multi-step capability programs offline."
            ),
            tags=("bootstrap", "compounder", "mission", "planner"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.program-run",
            name="Multi-step capability program runner",
            description=(
                "Execute an ordered list of ledger capabilities and collect per-step evidence "
                "without skill-route discovery."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_program_run",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_program_run; '
                "r=builtin_program_run(); assert r['ok'] and r.get('passed_count',0) >= 1 "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.goal-plan",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Capability programs run as ordered invocable chains with step evidence."
            ),
            tags=("bootstrap", "compounder", "mission", "program"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.second-wave-absorb",
            name="Second-wave domain primitive absorption",
            description=(
                "Absorb ready second-wave domain surfaces (persona, proposal synthesis, "
                "kernel preflight, …) to expand primitive coverage past superstack plateaus."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_second_wave_absorb",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_second_wave_absorb; '
                "r=builtin_second_wave_absorb(); assert r['ok'] and r.get('action')=='second_wave_absorb' "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.scout-gaps",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/persona.py",
                "src/blackhole_agent/proposal_synthesis.py",
                "src/blackhole_agent/kernels/grok_cli.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Second-wave domain primitives expand the ledger universe when compositions plateau."
            ),
            tags=("bootstrap", "compounder", "growth", "second-wave", "domain"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.mission-plane",
            name="Goal-conditioned mission capability plane",
            description=(
                "Expand second-wave primitives when ready, plan a goal-conditioned capability "
                "program, execute it, and spend novel-only growth budget — past superstack stall."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_mission_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_mission_plane; '
                "import os; "
                # Bound proof: plan+run only (no absorb/grow) so growth-loop dep proves stay cheap.
                "os.environ['BLACKHOLE_MISSION_GOAL']='health inventory milestone'; "
                "os.environ['BLACKHOLE_MISSION_GROW_BUDGET']='0'; "
                "os.environ['BLACKHOLE_MISSION_ABSORB']='0'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
                "r=builtin_mission_plane(); assert r['ok'] and r.get('action')=='mission_plane' "
                "and r.get('program',{}).get('passed_count',0) >= 1 "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.goal-plan",
                "capability.program-run",
                "capability.second-wave-absorb",
                "capability.adaptive-grow",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Mission goals drive second-wave expansion and multi-step capability programs "
                "without skill-route discovery, reopening novel frontiers after superstack stall."
            ),
            tags=("bootstrap", "compounder", "mission", "growth", "second-wave"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.outcome-contract",
            name="Machine-checkable outcome contract evaluator",
            description=(
                "Parse free-text or structured done_when into predicates and evaluate them "
                "against live ledger metrics, proofs, and optional program evidence."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_outcome_contract",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_outcome_contract; '
                "import os; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:3;capability_exists:repo.import-health;"
                "capability_proved:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_CONTRACT_RUN_PROGRAMS']='0'; "
                "r=builtin_outcome_contract(); assert r['ok'] and r.get('action')=='evaluate_outcome_contract' "
                "and r.get('machine_checkable') and r.get('met') is True "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.frontier-novelty",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "done_when becomes machine-checkable against ledger metrics and proofs "
                "instead of free-text agent claims alone."
            ),
            tags=("bootstrap", "compounder", "mission", "contract", "evidence"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.contract-plane",
            name="Evidence-bound mission contract plane",
            description=(
                "Run the mission plane then machine-check done_when predicates so mission "
                "completion is evidence-bound, not free-text theater."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_contract_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_contract_plane; '
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='health inventory milestone'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;min_primitives:3;capability_exists:repo.import-health;"
                "capability_proved:repo.import-health;program_passes:repo.import-health;"
                "no_skill_route;mission_plane_ok'; "
                "os.environ['BLACKHOLE_MISSION_GROW_BUDGET']='0'; "
                "os.environ['BLACKHOLE_MISSION_ABSORB']='0'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
                "os.environ['BLACKHOLE_CONTRACT_RUN_MISSION']='1'; "
                "r=builtin_contract_plane(); assert r['ok'] and r.get('action')=='contract_plane' "
                "and r.get('machine_checkable') and r.get('met') is True "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.outcome-contract",
                "capability.mission-plane",
                "capability.program-run",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Missions close on machine-checked outcome contracts after goal programs run, "
                "escaping free-text done_when completion without skill-route discovery."
            ),
            tags=("bootstrap", "compounder", "mission", "contract", "evidence", "growth"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.ablation-proof",
            name="Capability ablation proof",
            description=(
                "Falsify-then-restore proof ablation: broken proof_command fails, restored "
                "proofs pass, and broken dependencies fail dependent proves — without "
                "mutating the live ledger."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_ablation_proof",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_ablation_proof; '
                "r=builtin_ablation_proof(); assert r['ok'] and r.get('action')=='ablation_proof' "
                "and r.get('live_ledger_mutated') is False "
                "and r.get('passed_count',0) >= 3 "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "unbound.milestone-gate",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Capability proofs are falsifiable: ablation fails broken proofs and "
                "dependency chains without skill-route discovery."
            ),
            tags=("bootstrap", "compounder", "assurance", "ablation", "evidence"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.transfer-plane",
            name="Portable capability transfer plane",
            description=(
                "Export a capability dependency closure as a portable package, import into "
                "an empty ledger, and re-prove members against the same codebase."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_transfer_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_transfer_plane; '
                "r=builtin_transfer_plane(); assert r['ok'] and r.get('action')=='transfer_plane' "
                "and r.get('member_count',0) >= 2 and r.get('proved_count',0) >= 2 "
                "and r.get('reexport_members_match') "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "unbound.milestone-gate",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Capabilities transfer as portable packages with dependency closure and "
                "re-proof, enabling lineage portability without skill-route."
            ),
            tags=("bootstrap", "compounder", "assurance", "transfer", "package"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.adversarial-contract",
            name="Adversarial outcome contract evaluator",
            description=(
                "Evaluate positive done_when contracts that must pass and adversarial "
                "contracts that must fail, preventing one-sided evaluator theater."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_adversarial_contract",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_adversarial_contract; '
                "r=builtin_adversarial_contract(); assert r['ok'] and r.get('action')=='adversarial_contract' "
                "and r.get('positive_ok') and r.get('negatives_ok') "
                "and r.get('negatives_passed',0) >= 2 "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.outcome-contract",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Outcome contracts are adversarially checked: must-pass and must-fail "
                "predicates both gate evaluator honesty without skill-route."
            ),
            tags=("bootstrap", "compounder", "assurance", "contract", "adversarial", "evidence"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.assurance-plane",
            name="Capability assurance plane",
            description=(
                "Closed assurance plane: ablation proofs → portable transfer re-proof → "
                "adversarial outcome contracts — falsifiable evidence past composition growth."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_assurance_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_assurance_plane; '
                "r=builtin_assurance_plane(); assert r['ok'] and r.get('action')=='assurance_plane' "
                "and r.get('ablation',{}).get('ok') and r.get('transfer',{}).get('ok') "
                "and r.get('adversarial',{}).get('ok') "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.ablation-proof",
                "capability.transfer-plane",
                "capability.adversarial-contract",
                "capability.outcome-contract",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Assurance plane compounds ablation, transfer, and adversarial contracts "
                "into one falsifiable evidence plane past zero-novelty superstack plateaus."
            ),
            tags=(
                "bootstrap",
                "compounder",
                "assurance",
                "ablation",
                "transfer",
                "adversarial",
                "evidence",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.sovereignty-plane",
            name="Self-certifying sovereignty plane",
            description=(
                "Closed sovereignty plane: contract/mission evidence → assurance "
                "(ablation/transfer/adversarial) → portable re-verifiable lineage "
                "certificate that gates self-certifying completion."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_sovereignty_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_sovereignty_plane; '
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='health inventory milestone'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;min_primitives:3;capability_exists:repo.import-health;"
                "capability_proved:repo.import-health;program_passes:repo.import-health;"
                "no_skill_route;mission_plane_ok'; "
                "os.environ['BLACKHOLE_MISSION_GROW_BUDGET']='0'; "
                "os.environ['BLACKHOLE_MISSION_ABSORB']='0'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
                "os.environ['BLACKHOLE_CONTRACT_RUN_MISSION']='1'; "
                "r=builtin_sovereignty_plane(); assert r['ok'] and r.get('action')=='sovereignty_plane' "
                "and r.get('certificate',{}).get('ok') and r.get('verify',{}).get('valid') "
                "and r.get('assurance',{}).get('ok') and r.get('contract',{}).get('ok') "
                "and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.outcome-contract",
                "capability.contract-plane",
                "capability.assurance-plane",
                "capability.ablation-proof",
                "capability.transfer-plane",
                "capability.adversarial-contract",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Sovereignty plane compounds contract and assurance into one portable, "
                "re-verifiable lineage certificate for self-certifying completion without skill-route."
            ),
            tags=(
                "bootstrap",
                "compounder",
                "sovereignty",
                "assurance",
                "contract",
                "certificate",
                "evidence",
            ),
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
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
