"""Ledger structural attestation: an independent second path to readiness.

``capability.ledger-inventory`` attests ledger readiness by counting entries.
That is one behavior, one failure domain at the capability level: if its
proof stamp goes red, every goal that needs a readiness signal loses it.
This module provides a genuinely independent second attestation:

- **structural validation**, not counting — the ledger file must parse, carry
  the expected schema version, every entry must carry the fields the runtime
  relies on (id, kind, entry, proof_command, proof stamp), and every declared
  dependency must resolve to a known capability id;
- a different code path with no shared behavior with the inventory step, so
  a proof-stamp failure of one provider leaves the other able to attest.

Honesty boundary: both providers read the same ledger file, so this is
redundancy at the capability/proof-stamp level — the axis the fragility
audit measures — not at the data-source level. A corrupted ledger file
defeats both, and this module says so rather than claiming otherwise.

The registered proof (:func:`builtin_ledger_attestation`) attests the live
ledger and falsifies two corrupted-ledger shapes (unresolved dependency,
missing required field) on scratch payloads: both must be reported not
ready, never rounded up.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    default_ledger_path,
    legacy_pipeline_was_used,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_SCHEMA_VERSION = 1
REQUIRED_FIELDS = (
    "id",
    "name",
    "kind",
    "entry",
    "proof_command",
    "dependencies",
    "last_proof_exit_code",
)


def attest_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Structurally attest one ledger payload (pure, no side effects)."""

    capabilities = payload.get("capabilities")
    findings: list[str] = []
    if payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        findings.append(f"schema_version:{payload.get('schema_version')}")
    if not isinstance(capabilities, Mapping) or not capabilities:
        findings.append("capabilities:missing-or-empty")
        capabilities = {}

    missing_fields: dict[str, list[str]] = {}
    unresolved_dependencies: dict[str, list[str]] = {}
    for capability_id, entry in capabilities.items():
        if not isinstance(entry, Mapping):
            missing_fields[str(capability_id)] = ["<entry-not-a-mapping>"]
            continue
        absent = [field for field in REQUIRED_FIELDS if field not in entry]
        if absent:
            missing_fields[str(capability_id)] = absent
        dangling = [
            dependency
            for dependency in (entry.get("dependencies") or [])
            if dependency not in capabilities
        ]
        if dangling:
            unresolved_dependencies[str(capability_id)] = sorted(str(dep) for dep in dangling)

    count = len(capabilities)
    ready = not findings and not missing_fields and not unresolved_dependencies and count >= 2
    return {
        "ready": ready,
        "count": count,
        "schema_version_ok": payload.get("schema_version") == EXPECTED_SCHEMA_VERSION,
        "missing_fields": missing_fields,
        "unresolved_dependencies": unresolved_dependencies,
        "findings": findings,
    }


def attest_ledger_structure(repo_path: Path | None = None) -> dict[str, Any]:
    """Attest the live ledger file's structure."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "ready": False,
            "count": 0,
            "schema_version_ok": False,
            "missing_fields": {},
            "unresolved_dependencies": {},
            "findings": [f"ledger-unreadable:{type(error).__name__}"],
        }
    return attest_payload(payload)


def builtin_ledger_attestation() -> dict[str, Any]:
    """Registered proof for ``capability.ledger-attestation``.

    Attests the live ledger (must be ready), then falsifies two corrupted
    shapes on scratch payloads: an unresolved dependency reference and a
    missing required field must both be reported not ready. Determinism is
    proven by a repeated live attestation.
    """

    live = attest_ledger_structure()
    if not live["ready"]:
        return {"ok": False, "stage": "live-attestation", "attestation": live}
    again = attest_ledger_structure()
    if again != live:
        return {"ok": False, "stage": "determinism"}

    unresolved = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "capabilities": {
            "cap.a": {
                "id": "cap.a",
                "name": "a",
                "kind": "python",
                "entry": "m:f",
                "proof_command": "true",
                "dependencies": ["cap.missing"],
                "last_proof_exit_code": 0,
            },
        },
    }
    unresolved_result = attest_payload(unresolved)
    if unresolved_result["ready"] or "cap.a" not in unresolved_result["unresolved_dependencies"]:
        return {"ok": False, "stage": "unresolved-falsification", "attestation": unresolved_result}

    missing_field = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "capabilities": {
            "cap.a": {
                "id": "cap.a",
                "name": "a",
                "kind": "python",
                "entry": "m:f",
                "dependencies": [],
                "last_proof_exit_code": 0,
            },
            "cap.b": {
                "id": "cap.b",
                "name": "b",
                "kind": "python",
                "entry": "m:g",
                "proof_command": "true",
                "dependencies": [],
                "last_proof_exit_code": 0,
            },
        },
    }
    missing_result = attest_payload(missing_field)
    if missing_result["ready"] or missing_result["missing_fields"].get("cap.a") != ["proof_command"]:
        return {"ok": False, "stage": "missing-field-falsification", "attestation": missing_result}

    return {
        "ok": not legacy_pipeline_was_used(),
        "attestation": live,
        "deterministic": True,
        "unresolved_detected": True,
        "missing_field_detected": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ledger structural attestation")
    parser.add_argument("--repo-path", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    result = attest_ledger_structure(args.repo_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ready") else 1


if __name__ == "__main__":
    sys.exit(main())
