"""Distill the live capability ledger down to seeds and durable leaves.

The ledger rewards compounding, and compounding rewards re-packaging: composed
stacks, dynamic combinations, hierarchical / meta / superstack pillars, and
catalog tower hosts (civilization, cosmos, *continuum) accumulate faster than
new primitive coverage. This maintenance tool archives every entry that is not
a bootstrap seed, a durable leaf, or a dependency of one, so the live ledger
stays a set of invocable abilities instead of a naming scheme.

Kept:
- every ``_BOOTSTRAP_SEED_TABLE`` id (re-seeded on every growth call anyway)
- ``domain.*`` / ``repo.*`` / ``unbound.*`` / ``evolution.*`` leaves
- ``capability.synthesized-*`` (backed by capabilities/synthesized-steps.json)
- ``capability.absorbed-*`` (backed by vendored trees under capabilities/absorbed/)
- the transitive dependency closure of all of the above

Archived entries are preserved verbatim under ``artifacts/ledger-archive/`` so
history stays reviewable and restorable.

Usage:
    python scripts/distill_ledger.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from blackhole_agent.capability_compounder import _BOOTSTRAP_SEED_TABLE  # noqa: E402

LEDGER_PATH = REPO_ROOT / "capabilities" / "ledger.json"
ARCHIVE_DIR = REPO_ROOT / "artifacts" / "ledger-archive"

KEEP_PREFIXES = ("domain.", "repo.", "unbound.", "evolution.")
KEEP_CAPABILITY_PREFIXES = ("capability.synthesized-", "capability.absorbed-")
KEEP_IDS = {
    "capability.foraging-plane",
    "capability.forage-target-plane",
    "capability.acquisition-plane",
    "capability.absorption-plane",
}

# Previously force-archived when vendored-tree seals drifted even though
# frozen cases still passed. Reseal restores checkout-reproducible digests,
# so green absorbed leaves stay in the live ledger.
FORCE_ARCHIVE_IDS: set[str] = set()


def keep_set(capabilities: dict[str, dict]) -> set[str]:
    kept: set[str] = {str(entry["id"]) for entry in _BOOTSTRAP_SEED_TABLE}
    kept.update(KEEP_IDS & set(capabilities))
    for capability_id in capabilities:
        if capability_id.startswith(KEEP_PREFIXES) or capability_id.startswith(KEEP_CAPABILITY_PREFIXES):
            kept.add(capability_id)
    kept.difference_update(FORCE_ARCHIVE_IDS)
    # Dependency closure: a kept entry must never reference an archived id.
    changed = True
    while changed:
        changed = False
        for capability_id in list(kept):
            entry = capabilities.get(capability_id)
            if not entry:
                continue
            for dependency in entry.get("dependencies") or []:
                if dependency in capabilities and dependency not in kept:
                    kept.add(dependency)
                    changed = True
    blocked = kept & FORCE_ARCHIVE_IDS
    if blocked:
        raise SystemExit(f"force-archived ids still have kept dependents: {sorted(blocked)}")
    return kept


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report the partition without writing.")
    args = parser.parse_args()

    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    capabilities: dict[str, dict] = ledger.get("capabilities") or {}
    kept_ids = keep_set(capabilities)
    archived = {cid: entry for cid, entry in capabilities.items() if cid not in kept_ids}
    kept = {cid: capabilities[cid] for cid in sorted(capabilities) if cid in kept_ids}

    print(f"total={len(capabilities)} kept={len(kept)} archived={len(archived)}")
    for cid in sorted(archived):
        print(f"  archive {cid}")
    if args.dry_run:
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVE_DIR / f"{timestamp}-distilled.json"
    archive_payload = {
        "schema_version": ledger.get("schema_version"),
        "archived_at": timestamp,
        "reason": "ledger distill: archive re-packaged stacks, dynamic compositions, and catalog tower hosts",
        "source_updated_at": ledger.get("updated_at"),
        "archived_count": len(archived),
        "capabilities": {cid: archived[cid] for cid in sorted(archived)},
    }
    archive_path.write_text(json.dumps(archive_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    ledger["capabilities"] = kept
    ledger["updated_at"] = datetime.now(timezone.utc).isoformat()
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"archive={archive_path.relative_to(REPO_ROOT)}")
    print(f"ledger={LEDGER_PATH.relative_to(REPO_ROOT)} entries={len(kept)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
