"""Reconcile committed registry entries while Git merges the rest of the tree."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any, Callable

from blackhole_agent.capability_compounder import (
    DEFAULT_LEDGER_RELATIVE, SCHEMA_VERSION, CapabilityLedger, utc_now_iso, validate_capability,
)

LEDGER = DEFAULT_LEDGER_RELATIVE.as_posix()


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate registry key")
    return result


def _document(text: str) -> dict:
    doc = json.loads(text, object_pairs_hook=_unique_keys)
    if not isinstance(doc, dict) or not isinstance(doc.get("capabilities"), dict):
        raise ValueError("unsupported registry format")
    version = doc.get("schema_version", SCHEMA_VERSION)
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ValueError("unsupported registry format")
    for name, row in doc["capabilities"].items():
        if not isinstance(row, dict) or row.get("id", name) != name:
            raise ValueError(f"invalid registry entry {name!r}")
        deps = row.get("dependencies", [])
        if not isinstance(deps, list) or not all(isinstance(dep, str) for dep in deps):
            raise ValueError(f"invalid dependencies for {name!r}")
    return doc


def _written_at(row: dict) -> datetime:
    stamp = row.get("updated_at", "")
    if not stamp:
        return datetime.min.replace(tzinfo=timezone.utc)
    if not isinstance(stamp, str):
        raise ValueError("invalid registration timestamp")
    instant = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError(f"registration timestamp has no UTC offset: {stamp!r}")
    return instant


def _merge_keys(base: dict, peer: dict, mission: dict, *, registrations: bool = False) -> dict:
    def signature(doc: dict, key: str) -> str | None:
        if key not in doc:
            return None
        value = doc[key]
        if registrations:
            value = {field: data for field, data in value.items() if field != "updated_at"}
        # JSON distinguishes true from 1, and null from an absent field.
        return json.dumps(value, sort_keys=True, allow_nan=False)

    result = {}
    for key in sorted(base.keys() | peer.keys() | mission.keys()):
        before, left, right = (signature(doc, key) for doc in (base, peer, mission))
        if left != right and left != before and right != before:
            raise ValueError(f"competing edits to {key!r}")
        winner = mission if left == before else peer
        if key in winner:
            result[key] = winner[key]
            if registrations and left == right and peer[key].get("updated_at") != mission[key].get("updated_at"):
                result[key] = max((peer[key], mission[key]), key=_written_at)
    return result


def merge_registry(base: str | None, peer: str, mission: str) -> bytes:
    """Merge whole records, including deletions and unknown fields, then check the resulting graph."""
    documents = [_document(base) if base is not None else {}, _document(peer), _document(mission)]
    entries = _merge_keys(*(doc.pop("capabilities", {}) for doc in documents), registrations=True)
    for doc in documents:
        doc.pop("updated_at", None)  # save_ledger assigns this to each new revision.
    merged = dict(_merge_keys(*documents), capabilities=entries, updated_at=utc_now_iso())
    try:
        ledger = CapabilityLedger.from_dict(merged)
        for item in ledger.capabilities.values():
            validate_capability(item, existing=ledger.capabilities)
        TopologicalSorter({key: item.dependencies for key, item in ledger.capabilities.items()}).prepare()
    except (TypeError, KeyError, AttributeError) as error:
        raise ValueError(f"invalid capability record: {error}") from error
    return (json.dumps(merged, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def _only_registry_conflict(details: str) -> bool:
    # With -z, Git emits path counts and stable conflict types separately from translated prose.
    paths, sep, messages = details.partition("\0\0")
    if paths != LEDGER or not sep:
        return False
    fields = iter(messages.removesuffix("\0").split("\0"))
    found = False
    for count in fields:
        if not count.isdecimal():
            return False
        names = [next(fields, None) for _ in range(int(count))]
        kind = next(fields, None)
        if next(fields, None) is None:
            return False
        if kind == "Auto-merging":
            continue
        if names != [LEDGER] or kind not in {"CONFLICT (contents)", "CONFLICT (add/add)"}:
            return False
        found = True
    return found


def publication_tree(git: Callable, peer: str, mission: str) -> str:
    """Return an integrable tree or an empty string for an unresolved Git conflict."""
    bases = git("merge-base", "--all", peer, mission, check=False)
    if bases.returncode not in (0, 1):
        raise RuntimeError(bases.stderr.strip() or "Git could not read the merge bases")
    ancestors = bases.stdout.splitlines()
    if not ancestors or mission in ancestors:
        return ""
    merged = git("merge-tree", "--write-tree", "--name-only", "-z", peer, mission, check=False)
    tree, sep, details = merged.stdout.partition("\0")
    if not sep or merged.returncode not in (0, 1):
        raise RuntimeError(merged.stderr.strip() or "Git could not compute the merge tree")
    if merged.returncode and not _only_registry_conflict(details):
        return ""

    def entry(revision: str) -> tuple[str, ...]:
        info = git("ls-tree", "--full-tree", revision, "--", LEDGER).stdout.partition("\t")[0]
        return tuple(info.split())  # mode, type, object ID. Empty for an absent path.

    unchanged = "" if merged.returncode else tree
    left, right = entry(peer), entry(mission)
    if left == right:
        return unchanged
    originals = {entry(revision) for revision in ancestors}
    if len(originals) != 1:
        raise ValueError("multiple merge bases disagree about the registry")
    original = originals.pop()
    if original in (left, right):
        return unchanged
    # Only reconcile regular files still at the registered path. Git owns structural conflicts.
    target = entry(tree)
    if any(not item or item[0] not in {"100644", "100755"} for item in (left, right, target, original or left)):
        raise ValueError("incompatible registry file types or deletion")

    def contents(item: tuple[str, ...]) -> str:
        return git("cat-file", "blob", item[2], exact_stdout=True).stdout

    data = merge_registry(contents(original) if original else None, contents(left), contents(right))
    blob = git("hash-object", "-w", "--stdin", input_bytes=data).stdout.strip()
    git_dir = git("rev-parse", "--absolute-git-dir").stdout.rstrip("\r\n")
    with tempfile.TemporaryDirectory(prefix="bh-merge-index-") as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}

        def index(*args: str):
            return git("-C", directory, f"--git-dir={git_dir}", "-c", "core.splitIndex=false",
                       "-c", "core.fsmonitor=false", "-c", f"core.hooksPath={directory}/hooks", *args, env=env)

        index("read-tree", "--no-sparse-checkout", tree)
        index("update-index", "--cacheinfo", f"{target[0]},{blob},{LEDGER}")
        return index("write-tree").stdout.strip()
