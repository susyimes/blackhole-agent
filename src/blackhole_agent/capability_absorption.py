"""Capability absorption plane: external tools become first-class ledger capabilities.

The synthesis plane grows capabilities *from the goal's frozen cases*; the
grounded-growth scout distills external trends into *hypotheses*. Neither
imports behavior that already exists outside this repository. This module
closes that gap — **absorption**:

- an external tool ships (or is given) an ``absorption.json`` manifest at its
  root declaring a slug, an invocation command, the state keys it requires
  and provides, and at least two frozen input/output cases;
- the tool contract is uniform and state-threading: the command reads a JSON
  state object on stdin and writes a JSON fragment on stdout, so the absorbed
  capability composes with the application plane like any other step;
- absorption **vendors** a snapshot of the external tree into
  ``capabilities/absorbed/<slug>/`` and records a deterministic tree digest —
  the capability is thereafter hermetic: proofs replay against the vendored
  snapshot, never against the moving external source;
- the absorbed capability is registered in the live ledger with a proof that
  re-checks the vendored tree digest, re-checks the persisted record digest,
  and re-executes every frozen case against the vendored tool — a hand-edited
  persistence record, a tampered vendored file, or a drifting tool all fail
  the proof;
- the plane proves end-to-end honesty over the live ledger: a goal requiring
  the external behavior is honestly unplannable before absorption, plans and
  executes to the expected outcome after absorption, and becomes unplannable
  again under ablation of the absorbed capability;
- a digest-sealed report under ``artifacts/capability-absorption/`` whose
  grade is a pure function of recorded verdicts; verification re-grades,
  re-checks every digest, and re-runs the live honesty checks, so a forged
  verdict or tampered report fails verification;
- the tree digest covers only version-controllable content: packaging
  metadata (``*.egg-info``/``*.dist-info``) that ``.gitignore`` excludes is
  skipped, so every seal is reproducible from a clean checkout; records
  sealed before that invariant drifted beyond repair-by-checkout are
  re-sealed by :func:`reseal_absorbed_records`, which re-executes the frozen
  cases first and refuses any record whose behavior no longer passes.

Determinism contract: tree digests, case execution order, and every verdict
must be reproducible across runs on the same checkout. Durations and
timestamps are diagnostics only and are excluded from every digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_application import (
    ApplicationStep,
    ApplicationTask,
    build_application_registry,
    plan_application_task,
    run_application_task,
)
from blackhole_agent.capability_compounder import (
    Capability,
    atomic_write_json,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    prove_capability,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path, durable_write_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-absorption"
LATEST_POINTER = DEFAULT_ARTIFACT_DIR / "latest-absorption.json"
ABSORBED_ROOT = REPO_ROOT / "capabilities" / "absorbed"
PERSIST_PATH = REPO_ROOT / "capabilities" / "absorbed-steps.json"
MANIFEST_NAME = "absorption.json"
FIXTURE_TOOL = REPO_ROOT / "tests" / "fixtures" / "external_tools" / "text-reverser"

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
_STATE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_TREE_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    ".nox",
    ".venv",
    "node_modules",
}
# Packaging-metadata directory suffixes. Sdists ship ``*.egg-info`` (and wheels
# ``*.dist-info``) trees that ``.gitignore`` excludes from version control, so a
# digest that covers them can never be reproduced from a clean checkout.
_TREE_SKIP_SUFFIXES = (".egg-info", ".dist-info")
CASE_TIMEOUT_SECONDS = 30


def _tree_skip_part(part: str) -> bool:
    return part in _TREE_SKIP_DIRS or part.endswith(_TREE_SKIP_SUFFIXES)


# ---------------------------------------------------------------------------
# Canonical digests.
# ---------------------------------------------------------------------------


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def tree_digest(root: Path) -> str:
    """Deterministic digest over a vendored tool tree.

    Covers every file's relative path and content in sorted order; VCS,
    interpreter-cache, and packaging-metadata directories are excluded so a
    proof run never changes the digest it checks and the seal stays
    reproducible from a clean checkout (git never tracks ``*.egg-info``).
    """

    entries: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if any(_tree_skip_part(part) for part in path.parts):
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        content = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append((relative, content))
    return _digest(entries)


# ---------------------------------------------------------------------------
# Manifest loading and validation.
# ---------------------------------------------------------------------------


def load_manifest(source_path: Path) -> dict[str, Any]:
    """Load and validate the ``absorption.json`` manifest of an external tool."""

    manifest_path = source_path / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(f"absorption manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"absorption manifest is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("absorption manifest must be a JSON object")
    if int(manifest.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ValueError(f"unsupported absorption schema_version: {manifest.get('schema_version')!r}")
    slug = str(manifest.get("slug") or "")
    if not SLUG_PATTERN.match(slug):
        raise ValueError(f"invalid absorption slug: {slug!r}")
    command = manifest.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part.strip() for part in command)
    ):
        raise ValueError("absorption command must be a non-empty list of strings")
    for field in ("requires", "provides"):
        keys = manifest.get(field)
        if (
            not isinstance(keys, list)
            or not keys
            or not all(isinstance(key, str) and _STATE_KEY_PATTERN.match(key) for key in keys)
            or len(set(keys)) != len(keys)
        ):
            raise ValueError(f"absorption {field} must be unique snake_case state keys")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) < 2:
        raise ValueError("absorption requires at least two frozen cases")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {index} must be an object")
        case_input = case.get("input")
        case_expect = case.get("expect")
        if not isinstance(case_input, dict) or not isinstance(case_expect, dict) or not case_expect:
            raise ValueError(f"case {index} needs an input object and a non-empty expect object")
        missing = [key for key in manifest["requires"] if key not in case_input]
        if missing:
            raise ValueError(f"case {index} input is missing required keys: {missing}")
        unknown = [key for key in case_expect if key not in set(manifest["provides"])]
        if unknown:
            raise ValueError(f"case {index} expects undeclared provides keys: {unknown}")
    if not str(manifest.get("name") or "").strip():
        raise ValueError("absorption manifest requires a name")
    return manifest


def capability_id_for_slug(slug: str) -> str:
    return f"capability.absorbed-{slug}"


def _normalized_command(command: Sequence[str]) -> list[str]:
    """Resolve an interpreter alias to this environment's interpreter."""

    parts = [str(part) for part in command]
    if parts and parts[0] in {"python", "python3", "python.exe"}:
        parts[0] = sys.executable
    return parts


def _case_env() -> dict[str, str]:
    env = dict(os.environ)
    # Never let a proof run litter the vendored tree with bytecode caches:
    # the tree digest must be stable across runs.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# ---------------------------------------------------------------------------
# Case execution against a tool tree.
# ---------------------------------------------------------------------------


def run_absorption_case(
    tool_root: Path,
    command: Sequence[str],
    case: Mapping[str, Any],
    *,
    timeout: int = CASE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute one frozen case: JSON state in, JSON fragment out, exact match."""

    resolved = _normalized_command(command)
    try:
        completed = subprocess.run(
            resolved,
            input=json.dumps(case["input"]),
            capture_output=True,
            text=True,
            cwd=tool_root,
            env=_case_env(),
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip().splitlines()
        return {
            "ok": False,
            "error": f"exit {completed.returncode}: {stderr[0] if stderr else 'no stderr'}",
        }
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
    return {"ok": True, "output": {key: fragment[key] for key in expect}}


def run_absorption_cases(
    tool_root: Path,
    manifest: Mapping[str, Any],
    *,
    timeout: int = CASE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run every frozen case in declared order; all must pass."""

    results = [
        run_absorption_case(tool_root, manifest["command"], case, timeout=timeout)
        for case in manifest["cases"]
    ]
    return {
        "ok": all(result["ok"] for result in results),
        "case_count": len(results),
        "cases_pass": all(result["ok"] for result in results),
        "case_results": results,
    }


# ---------------------------------------------------------------------------
# Durable persistence of absorbed steps.
# ---------------------------------------------------------------------------


def _record_body(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "record_digest"}


def record_digest(record: Mapping[str, Any]) -> str:
    return _digest(_record_body(record))


def load_persisted_records(path: Path | None = None) -> list[dict[str, Any]]:
    persist_path = durable_read_path(path or PERSIST_PATH)
    if not persist_path.is_file():
        return []
    payload = json.loads(persist_path.read_text(encoding="utf-8"))
    records = payload.get("steps")
    if not isinstance(records, list):
        raise ValueError(f"absorbed steps file is malformed: {persist_path}")
    return [dict(record) for record in records]


def _write_persisted_records(records: Sequence[Mapping[str, Any]], path: Path | None = None) -> bool:
    """Idempotently persist absorbed-step records. Returns True when rewritten."""

    persist_path = path or PERSIST_PATH
    body = [dict(record) for record in records]
    if persist_path.is_file():
        existing = json.loads(persist_path.read_text(encoding="utf-8"))
        if existing.get("steps") == body:
            return False
    atomic_write_json(
        persist_path,
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "absorbed_steps",
            "absorbed_at": utc_now_iso(),
            "steps": body,
            "steps_digest": _digest(body),
        },
    )
    return True


def absorbed_step_record(
    manifest: Mapping[str, Any],
    vendored_tree_digest: str,
    *,
    origin: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the durable record for one absorbed tool (digest appended)."""

    slug = str(manifest["slug"])
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capability_id": capability_id_for_slug(slug),
        "slug": slug,
        "name": str(manifest["name"]),
        "version": str(manifest.get("version") or ""),
        "command": [str(part) for part in manifest["command"]],
        "requires": [str(key) for key in manifest["requires"]],
        "provides": [str(key) for key in manifest["provides"]],
        "cases": [dict(case) for case in manifest["cases"]],
        "vendored_tree_digest": vendored_tree_digest,
        "origin": dict(origin or manifest.get("origin") or {}),
    }
    record["record_digest"] = record_digest(record)
    return record


def upsert_persisted_record(record: Mapping[str, Any], path: Path | None = None) -> bool:
    records = [item for item in load_persisted_records(path) if item.get("slug") != record["slug"]]
    records.append(dict(record))
    records.sort(key=lambda item: str(item.get("slug") or ""))
    return _write_persisted_records(records, path)


# ---------------------------------------------------------------------------
# Proof: vendored tree + record digest + frozen cases, all re-executed.
# ---------------------------------------------------------------------------


def _prove_record(
    record: Mapping[str, Any],
    vendored_dir: Path,
    *,
    timeout: int = CASE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    expected_record_digest = str(record.get("record_digest") or "")
    record_digest_match = bool(expected_record_digest) and record_digest(record) == expected_record_digest
    actual_tree = tree_digest(vendored_dir) if vendored_dir.is_dir() else ""
    tree_digest_match = bool(actual_tree) and actual_tree == str(record.get("vendored_tree_digest") or "")
    manifest = {
        "command": record["command"],
        "requires": record["requires"],
        "provides": record["provides"],
        "cases": record["cases"],
    }
    cases = (
        run_absorption_cases(vendored_dir, manifest, timeout=timeout)
        if tree_digest_match
        else {"ok": False, "case_count": len(record["cases"]), "cases_pass": False, "case_results": []}
    )
    ok = record_digest_match and tree_digest_match and cases["ok"]
    return {
        "ok": ok,
        "slug": record.get("slug"),
        "capability_id": record.get("capability_id"),
        "record_digest_match": record_digest_match,
        "tree_digest_match": tree_digest_match,
        "cases_pass": bool(cases["ok"]),
        "case_count": cases["case_count"],
    }


def prove_absorbed_capability(
    slug: str,
    *,
    persist_path: Path | None = None,
    vendored_root: Path | None = None,
) -> dict[str, Any]:
    """Re-prove one absorbed capability from its durable record and vendored tree."""

    records = {str(record.get("slug")): record for record in load_persisted_records(persist_path)}
    record = records.get(slug)
    if record is None:
        return {
            "ok": False,
            "slug": slug,
            "error": "no persisted absorption record",
            "record_digest_match": False,
            "tree_digest_match": False,
            "cases_pass": False,
        }
    vendored_dir = durable_read_path((vendored_root or ABSORBED_ROOT) / slug)
    return _prove_record(record, vendored_dir)


def absorbed_proof_command(slug: str) -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_absorption import '
        f"prove_absorbed_capability; r=prove_absorbed_capability('{slug}'); "
        "assert r['ok'] and r['record_digest_match'] and r['tree_digest_match'] "
        "and r['cases_pass']\""
    )


# ---------------------------------------------------------------------------
# Repair: audited reseal of records whose seal is not checkout-reproducible.
# ---------------------------------------------------------------------------


def reseal_absorbed_records(
    *,
    persist_path: Path | None = None,
    vendored_root: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Re-seal absorbed records whose vendored tree drifted from the seal.

    A seal is only meaningful when it is reproducible from the committed
    checkout. Past planes digested packaging metadata (``*.egg-info``) that
    git never tracks, so their records could never prove again. For every
    drifted record this re-executes the frozen cases against the on-disk
    vendored tree and — only when every case still passes — rewrites the
    record with the checkout-reproducible tree digest. A record whose cases
    fail is *refused*: drift plus broken behavior is tampering, not drift.
    Every decision is sealed into a repair receipt under
    ``artifacts/capability-absorption/``.
    """

    records = load_persisted_records(persist_path)
    root = vendored_root or ABSORBED_ROOT
    rewritten: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    unchanged: list[str] = []
    updated_records: list[dict[str, Any]] = []
    for record in records:
        slug = str(record.get("slug") or "")
        vendored_dir = durable_read_path(root / slug)
        actual_tree = tree_digest(vendored_dir) if vendored_dir.is_dir() else ""
        if actual_tree and actual_tree == str(record.get("vendored_tree_digest") or ""):
            unchanged.append(slug)
            updated_records.append(record)
            continue
        manifest = {
            "command": record["command"],
            "requires": record["requires"],
            "provides": record["provides"],
            "cases": record["cases"],
        }
        cases = run_absorption_cases(vendored_dir, manifest) if actual_tree else {
            "ok": False,
            "case_count": len(record["cases"]),
            "cases_pass": False,
            "case_results": [],
        }
        if not cases["ok"]:
            refusals.append(
                {
                    "slug": slug,
                    "reason": "frozen cases fail against the drifted tree"
                    if actual_tree
                    else "vendored tree is missing",
                    "sealed_tree_digest": record.get("vendored_tree_digest"),
                    "actual_tree_digest": actual_tree or None,
                }
            )
            updated_records.append(record)
            continue
        resealed = dict(record)
        resealed["vendored_tree_digest"] = actual_tree
        resealed["record_digest"] = record_digest(resealed)
        rewritten.append(
            {
                "slug": slug,
                "previous_tree_digest": record.get("vendored_tree_digest"),
                "resealed_tree_digest": actual_tree,
                "case_count": cases["case_count"],
            }
        )
        updated_records.append(resealed)

    persisted = _write_persisted_records(updated_records, persist_path) if rewritten else False
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "absorption_reseal_receipt",
        "resealed_at": utc_now_iso(),
        "record_count": len(records),
        "unchanged": sorted(unchanged),
        "resealed": rewritten,
        "refusals": refusals,
        "persisted": persisted,
        "ok": not refusals,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    receipt["receipt_digest"] = _digest(
        {key: value for key, value in receipt.items() if key != "receipt_digest"}
    )
    target_dir = output_dir or DEFAULT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "latest-reseal.json", receipt)
    return receipt


def sync_green_absorbed_capabilities(
    *,
    repo_root: Path = REPO_ROOT,
    persist_path: Path | None = None,
) -> dict[str, Any]:
    """Register every absorbed record whose live proof is green onto the ledger.

    Distill previously force-archived drifted seals even when frozen cases
    still passed. After reseal, this restores those leaves so they remain
    invocable instead of sitting only in ``absorbed-steps.json``.
    """

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    restored: list[str] = []
    skipped: list[str] = []
    now = utc_now_iso()
    for record in load_persisted_records(persist_path):
        slug = str(record.get("slug") or "")
        proof = prove_absorbed_capability(slug, persist_path=persist_path)
        if not proof.get("ok"):
            skipped.append(slug)
            continue
        capability_id = str(record.get("capability_id") or capability_id_for_slug(slug))
        dependencies = tuple(
            dependency
            for dependency in ("repo.import-health", "capability.ledger-inventory")
            if dependency in ledger.capabilities
        )
        capability = Capability(
            id=capability_id,
            name=f"Absorbed external capability: {record.get('name') or slug}",
            description=(
                f"Absorbed from external tool '{slug}' "
                f"({(record.get('origin') or {}).get('kind', 'unknown')} origin "
                f"{(record.get('origin') or {}).get('source', '')}): provides "
                f"{record.get('provides')} from {record.get('requires')}. Vendored "
                f"under capabilities/absorbed/{slug}/ with a tree digest; the proof "
                "re-checks the persisted record digest, the vendored tree digest, "
                "and re-executes every frozen case."
            ),
            kind="python",
            entry="blackhole_agent.capability_absorption:demo_absorbed_steps",
            proof_command=absorbed_proof_command(slug),
            dependencies=dependencies,
            behavior_paths=(
                "src/blackhole_agent/capability_absorption.py",
                "capabilities/absorbed-steps.json",
                f"capabilities/absorbed/{slug}/",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                f"External tool '{slug}' is now a first-class invocable capability "
                f"providing {record.get('provides')}."
            ),
            tags=("absorbed", "external"),
            last_proved_at=now,
            last_proof_exit_code=0,
        )
        ledger = register_capability(ledger, capability, replace=True)
        restored.append(capability_id)
    save_ledger(ledger_path, ledger)
    return {
        "ok": True,
        "restored": restored,
        "skipped": skipped,
        "count": len(restored),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


# ---------------------------------------------------------------------------
# Absorption: vendor, persist, register, prove.
# ---------------------------------------------------------------------------


def absorb_external_capability(
    source_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
    origin: Mapping[str, Any] | None = None,
    ledger_path: Path | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """Absorb one external tool into a first-class proved ledger capability.

    The manifest's frozen cases must pass against the original source
    (pre-flight), the tree is vendored under ``capabilities/absorbed/<slug>/``,
    the cases must pass again against the vendored snapshot, the durable
    record is upserted, and the capability is registered and proved in the
    live ledger. Idempotent: re-absorbing an unchanged tool rewrites nothing.
    """

    manifest = load_manifest(source_path)
    slug = str(manifest["slug"])
    capability_id = capability_id_for_slug(slug)

    preflight = run_absorption_cases(source_path, manifest)
    if not preflight["ok"]:
        return {"ok": False, "stage": "preflight", "slug": slug, "preflight": preflight}

    vendored_dir = durable_write_path(repo_root / "capabilities" / "absorbed" / slug)
    if vendored_dir.exists():
        shutil.rmtree(vendored_dir)
    shutil.copytree(
        source_path,
        vendored_dir,
        ignore=shutil.ignore_patterns(
            ".git",
            ".hg",
            ".svn",
            "__pycache__",
            "*.pyc",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            ".tox",
            ".nox",
            ".venv",
            "node_modules",
            "*.egg-info",
            "*.dist-info",
        ),
    )
    vendored = run_absorption_cases(vendored_dir, manifest)
    if not vendored["ok"]:
        return {"ok": False, "stage": "vendored-cases", "slug": slug, "vendored": vendored}
    vendored_tree_digest = tree_digest(vendored_dir)

    record = absorbed_step_record(manifest, vendored_tree_digest, origin=origin)
    persist_path = repo_root / "capabilities" / "absorbed-steps.json"
    upsert_persisted_record(record, persist_path)

    resolved_ledger_path = ledger_path or default_ledger_path(repo_root)
    ledger = load_ledger(resolved_ledger_path)
    # Base dependencies only. The absorbed capability must not depend on the
    # absorption plane: the plane's own proof re-absorbs, which would make the
    # dependency graph recurse at proof time.
    dependencies = tuple(
        dependency
        for dependency in ("repo.import-health", "capability.ledger-inventory")
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id=capability_id,
        name=f"Absorbed external capability: {record['name']}",
        description=(
            f"Absorbed from external tool '{slug}' ({record['origin'].get('kind', 'unknown')} "
            f"origin {record['origin'].get('source', '')}): provides {record['provides']} from "
            f"{record['requires']}. Vendored under capabilities/absorbed/{slug}/ with a tree "
            "digest; the proof re-checks the persisted record digest, the vendored tree digest, "
            "and re-executes every frozen case, so a hand-edited record or tampered file fails."
        ),
        kind="python",
        entry="blackhole_agent.capability_absorption:demo_absorbed_steps",
        proof_command=absorbed_proof_command(slug),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_absorption.py",
            "capabilities/absorbed-steps.json",
            f"capabilities/absorbed/{slug}/",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            f"External tool '{slug}' is now a first-class invocable capability providing "
            f"{record['provides']}; goals needing it plan and execute through the application "
            "plane where they were honestly unplannable before absorption."
        ),
        tags=("absorbed", "external"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(resolved_ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability_id, cwd=repo_root, timeout=timeout)
    save_ledger(resolved_ledger_path, ledger)
    return {
        "ok": proof.ok,
        "stage": "proved" if proof.ok else "proof",
        "slug": slug,
        "capability_id": capability_id,
        "vendored_tree_digest": vendored_tree_digest,
        "proof_exit_code": proof.exit_code,
        "proof_summary": proof.summary,
    }


# ---------------------------------------------------------------------------
# Planner integration: absorbed records become invocable application steps.
# ---------------------------------------------------------------------------


def load_persisted_absorbed_steps(path: Path | None = None) -> dict[str, ApplicationStep]:
    """Rebuild invocable application steps from the persisted absorbed records.

    The persisted record plus the vendored tree *is* the capability; honesty
    is enforced by ``prove_absorbed_capability`` re-executing the frozen cases
    against the digest-checked vendored snapshot.
    """

    steps: dict[str, ApplicationStep] = {}
    for record in load_persisted_records(path):
        slug = str(record["slug"])
        command = [str(part) for part in record["command"]]
        requires = tuple(str(key) for key in record["requires"])
        provides = tuple(str(key) for key in record["provides"])
        vendored_dir = durable_read_path(ABSORBED_ROOT / slug)

        def invoke(
            state: Mapping[str, Any],
            _dir: Path = vendored_dir,
            _command: Sequence[str] = command,
            _requires: tuple[str, ...] = requires,
            _provides: tuple[str, ...] = provides,
        ) -> dict[str, Any]:
            case = {"input": {key: state[key] for key in _requires}}
            resolved = _normalized_command(_command)
            completed = subprocess.run(
                resolved,
                input=json.dumps(case["input"]),
                capture_output=True,
                text=True,
                cwd=_dir,
                env=_case_env(),
                timeout=CASE_TIMEOUT_SECONDS,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"absorbed tool exited {completed.returncode}: {completed.stderr.strip()}")
            fragment = json.loads(completed.stdout or "{}")
            if not isinstance(fragment, dict):
                raise RuntimeError("absorbed tool stdout was not a JSON object")
            return {key: fragment[key] for key in _provides}

        steps[str(record["capability_id"])] = ApplicationStep(
            capability_id=str(record["capability_id"]),
            requires=requires,
            provides=provides,
            invoke=invoke,
        )
    return steps


# ---------------------------------------------------------------------------
# Absorption plane: sealed end-to-end honesty demonstration.
# ---------------------------------------------------------------------------


def _absorption_task(record: Mapping[str, Any]) -> ApplicationTask:
    case = record["cases"][0]
    return ApplicationTask(
        id=f"absorbed-{record['slug']}",
        description=(
            f"Goal requiring the absorbed external capability '{record['slug']}': "
            f"produce {record['provides']} from the initial state."
        ),
        initial_state=dict(case["input"]),
        goal=tuple(str(key) for key in record["provides"]),
        oracle=dict(case["expect"]),
    )


def scenario_report_name(slug: str) -> str:
    return f"{slug}-report.json"


def _first_vendored_file(vendored_dir: Path) -> Path:
    for path in sorted(vendored_dir.rglob("*")):
        if any(_tree_skip_part(part) for part in path.parts):
            continue
        if path.is_file():
            return path
    raise ValueError(f"vendored tree has no files: {vendored_dir}")


def run_absorption_scenario(slug: str, output_dir: Path | None = None) -> dict[str, Any]:
    """Run the sealed end-to-end honesty scenario for one absorbed capability.

    Honesty chain: the absorbed goal is honestly unplannable with the
    capability hidden (pre-absorption), plans and executes to the oracle with
    it visible (post-absorption), is unplannable again under ablation, a
    tampered vendored tree fails its proof, and a hand-edited persistence
    record fails its record digest. Works for any persisted absorbed record —
    fixture or live-cloned external repository alike.
    """

    records = {str(item.get("slug")): item for item in load_persisted_records()}
    record = records.get(slug)
    if record is None:
        return {"ok": False, "stage": "record", "error": f"no persisted absorption record: {slug}"}
    capability_id = str(record["capability_id"])
    task = _absorption_task(record)

    ledger = load_ledger(default_ledger_path(REPO_ROOT))

    # Pre-absorption honesty: with the absorbed capability hidden, no plan exists.
    base_registry = build_application_registry(
        ledger, hide=[capability_id], include_synthesized=True, include_absorbed=True
    )
    before_plan = plan_application_task(task, base_registry)
    unplannable_before = before_plan is None

    # Post-absorption: the grown registry plans and executes to the oracle.
    grown_registry = build_application_registry(ledger, include_synthesized=True, include_absorbed=True)
    grown_result = run_application_task(task, grown_registry)
    grown_plan_solved = bool(
        grown_result["ok"] and grown_result["plan"] and capability_id in grown_result["plan"]
    )

    # Ablation: hiding the absorbed capability makes the goal unplannable again.
    ablated_registry = build_application_registry(
        ledger, hide=[capability_id], include_synthesized=True, include_absorbed=True
    )
    ablation_unplannable = plan_application_task(task, ablated_registry) is None

    # Tamper: corrupt a copy of the vendored tree; the proof must fail.
    with tempfile.TemporaryDirectory(prefix="blackhole-absorption-tamper-") as tmp:
        tampered_root = Path(tmp) / "absorbed"
        shutil.copytree(durable_read_path(ABSORBED_ROOT / slug), tampered_root / slug)
        victim = _first_vendored_file(tampered_root / slug)
        victim.write_bytes(victim.read_bytes() + b"\n# tampered\n")
        tamper_proof = prove_absorbed_capability(slug, vendored_root=tampered_root)
    tamper_rejected = not tamper_proof["ok"]

    # Forgery: hand-edit the persisted record; the record digest must fail.
    forged = dict(record)
    forged["name"] = "hand-edited forgery"
    forgery_rejected = record_digest(forged) != str(forged["record_digest"])

    proof = prove_absorbed_capability(slug)
    live_proof_ok = bool(proof["ok"])

    verdicts = {
        "unplannable_before": unplannable_before,
        "grown_plan_solved": grown_plan_solved,
        "ablation_unplannable": ablation_unplannable,
        "tamper_rejected": tamper_rejected,
        "forgery_rejected": forgery_rejected,
        "live_proof_ok": live_proof_ok,
    }
    grade = {
        "verdict_count": len(verdicts),
        "verdicts_passed": sum(1 for verdict in verdicts.values() if verdict),
        "ok": all(verdicts.values()),
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_absorption_scenario",
        "generated_at": utc_now_iso(),
        "slug": slug,
        "capability_id": capability_id,
        "origin": dict(record.get("origin") or {}),
        "vendored_tree_digest": record["vendored_tree_digest"],
        "record_digest": record["record_digest"],
        "task": {
            "id": task.id,
            "goal": list(task.goal),
            "initial_state": dict(task.initial_state),
            "oracle": dict(task.oracle),
        },
        "grown_plan": grown_result["plan"],
        "verdicts": verdicts,
        "grade": grade,
    }
    report["report_digest"] = _digest(
        {key: value for key, value in report.items() if key not in {"generated_at", "report_digest"}}
    )

    target_dir = output_dir or DEFAULT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    report_name = scenario_report_name(slug)
    atomic_write_json(target_dir / report_name, report)
    atomic_write_json(
        LATEST_POINTER,
        {"report": report_name, "report_digest": report["report_digest"], "ok": grade["ok"]},
    )
    return {"ok": grade["ok"], "report_dir": str(target_dir), **verdicts, "grade": grade}


def run_absorption_plane(output_dir: Path | None = None) -> dict[str, Any]:
    """Run the sealed absorption demonstration over the live ledger.

    Absorbs the fixture external tool (idempotently) and then runs the same
    end-to-end honesty scenario that any absorbed capability — including a
    live-cloned external repository — is graded by.
    """

    if not FIXTURE_TOOL.is_dir():
        return {"ok": False, "stage": "fixture", "error": f"fixture tool missing: {FIXTURE_TOOL}"}
    absorption = absorb_external_capability(FIXTURE_TOOL)
    if not absorption["ok"]:
        return {"ok": False, "stage": "absorb", "absorption": absorption}
    return run_absorption_scenario(str(absorption["slug"]), output_dir)


def verify_absorption_plane(report_dir: Path, *, slug: str | None = None) -> dict[str, Any]:
    """Re-grade a sealed absorption report; any forgery or drift fails."""

    if slug:
        report_path = report_dir / scenario_report_name(slug)
    else:
        candidates = sorted(report_dir.glob("*-report.json"))
        report_path = candidates[0] if candidates else report_dir / "<none>"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    expected_digest = _digest(
        {key: value for key, value in report.items() if key not in {"generated_at", "report_digest"}}
    )
    digest_ok = expected_digest == report.get("report_digest")

    verdicts = report.get("verdicts") or {}
    expected_grade = {
        "verdict_count": len(verdicts),
        "verdicts_passed": sum(1 for verdict in verdicts.values() if verdict),
        "ok": all(verdicts.values()) if verdicts else False,
    }
    grade_ok = expected_grade == report.get("grade")

    slug = str(report.get("slug") or "")
    capability_id = str(report.get("capability_id") or "")
    live_proof = prove_absorbed_capability(slug) if slug else {"ok": False}
    live_proof_ok = bool(live_proof["ok"])

    live_honesty_ok = False
    records = {str(item.get("slug")): item for item in load_persisted_records()}
    record = records.get(slug)
    if record is not None and record_digest(record) == report.get("record_digest"):
        ledger = load_ledger(default_ledger_path(REPO_ROOT))
        task = _absorption_task(record)
        grown_registry = build_application_registry(
            ledger, include_synthesized=True, include_absorbed=True
        )
        grown_result = run_application_task(task, grown_registry)
        ablated_registry = build_application_registry(
            ledger, hide=[capability_id], include_synthesized=True, include_absorbed=True
        )
        live_honesty_ok = bool(
            grown_result["ok"]
            and capability_id in (grown_result["plan"] or [])
            and plan_application_task(task, ablated_registry) is None
        )

    ok = digest_ok and grade_ok and live_proof_ok and live_honesty_ok
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "grade_ok": grade_ok,
        "live_proof_ok": live_proof_ok,
        "live_honesty_ok": live_honesty_ok,
    }


def builtin_absorption_plane_proof() -> dict[str, Any]:
    """Registered proof: run the plane into a scratch dir and verify the seal."""

    with tempfile.TemporaryDirectory(prefix="blackhole-absorption-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        result = run_absorption_plane(report_dir)
        if not result.get("ok"):
            return {**result, "verify_ok": False}
        verification = verify_absorption_plane(report_dir)
    ok = bool(result["ok"] and verification["ok"])
    return {**result, "ok": ok, "verify_ok": bool(verification["ok"]), "verification": verification}


def absorption_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_absorption import '
        "builtin_absorption_plane_proof; r=builtin_absorption_plane_proof(); "
        "assert r['ok'] and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('tamper_rejected') "
        "and r.get('forgery_rejected') and r.get('verify_ok')\""
    )


def demo_absorbed_steps() -> dict[str, Any]:
    """Entry surface: absorb the fixture tool and summarize the invocable steps."""

    result = absorb_external_capability(FIXTURE_TOOL)
    steps = load_persisted_absorbed_steps()
    return {
        "ok": bool(result["ok"]),
        "absorbed": sorted(steps),
        "step_count": len(steps),
    }


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability absorption plane")
    sub = parser.add_subparsers(dest="command_name", required=True)

    absorb_parser = sub.add_parser("absorb", help="absorb an external tool into the ledger")
    absorb_parser.add_argument("--source", required=True, type=Path)
    absorb_parser.add_argument("--origin-kind", default="")
    absorb_parser.add_argument("--origin-source", default="")
    absorb_parser.add_argument("--origin-commit", default="")

    prove_parser = sub.add_parser("prove", help="re-prove one absorbed capability")
    prove_parser.add_argument("--slug", required=True)

    sub.add_parser("demo", help="run the sealed absorption demonstration")

    scenario_parser = sub.add_parser(
        "scenario", help="run the sealed honesty scenario for one absorbed capability"
    )
    scenario_parser.add_argument("--slug", required=True)
    scenario_parser.add_argument("--output-dir", type=Path, default=None)

    verify_parser = sub.add_parser("verify", help="verify a sealed absorption report")
    verify_parser.add_argument("--report-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    verify_parser.add_argument("--slug", default=None)

    args = parser.parse_args(argv)
    if args.command_name == "absorb":
        origin = {
            key: value
            for key, value in {
                "kind": args.origin_kind,
                "source": args.origin_source,
                "commit": args.origin_commit,
            }.items()
            if value
        }
        result = absorb_external_capability(args.source, origin=origin or None)
    elif args.command_name == "prove":
        result = prove_absorbed_capability(args.slug)
    elif args.command_name == "demo":
        result = run_absorption_plane()
    elif args.command_name == "scenario":
        result = run_absorption_scenario(args.slug, args.output_dir)
    else:
        result = verify_absorption_plane(args.report_dir, slug=args.slug)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
