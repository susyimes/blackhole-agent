"""Evidence-based brakes on renamed demos and content-free fallback loops.

These are quality checks, not a claim to measure intelligence or protocol
conformance. Names, ledger timestamps and model prose are not progress.
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

LOCAL_NO_PROGRESS_LIMIT = 6


def behavior_family(text: str) -> str:
    """Recognize the observed handshake/digest recipe without a protocol list."""
    lowered = text.lower()
    features = (
        bool(re.search(r"handshake|lockstep|two.phase|two.stage", lowered)),
        bool(re.search(r"digest|checksum", lowered)),
        bool(re.search(r"sealed|seal a|seal the", lowered)),
        bool(re.search(r"later (?:poll|reader)|independent.*(?:poll|read)|loopback", lowered)),
        bool(re.search(r"missing.*(?:id|identifier)|non.empty.*(?:id|identifier)|id.gated", lowered)),
    )
    return "network/handshake-digest-demo" if sum(features) >= 3 else ""


def ledger_only_contract(text: str) -> bool:
    """An inventory/proof-register predicate is not an outcome acceptance test.

    Only classify complete structured clauses; do not discard additional real
    acceptance prose just because it mentions capability_exists.
    """
    parts = [p.strip() for p in text.strip().split(";") if p.strip()]
    static = re.compile(
        r"(?:capability_exists|capability_proved|ledger_has|min_capabilities|min_primitives):[\w.\-]+"
        r"|no_skill_route"
    )
    return bool(parts) and all(static.fullmatch(p) for p in parts)


def content_fingerprint(workspace: Path, paths: Iterable[str]) -> str:
    """Hash current contents, including deletions; ignore ledger/state churn."""
    digest = hashlib.sha256()
    root = workspace.resolve()
    for rel in sorted(set(paths)):
        normalized = rel.replace("\\", "/")
        if normalized.startswith((".blackhole-agent/", "artifacts/", "capabilities/")):
            continue
        path = (root / rel).resolve()
        if not path.is_relative_to(root):
            continue
        digest.update(normalized.encode("utf-8"))
        if path.is_file():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    digest.update(chunk)
        else:
            digest.update(b"<deleted>")
    return digest.hexdigest()


def record_local_progress(state: Any, *, kernel: str, before: str, after: str, milestone: bool) -> dict[str, Any]:
    changed = before != after or milestone
    if kernel != "local" or changed:
        state.local_no_progress_count = 0
    else:
        state.local_no_progress_count = int(state.local_no_progress_count) + 1
    return {
        "before": before,
        "after": after,
        "content_changed": changed,
        "consecutive_local_no_progress": state.local_no_progress_count,
        "limit": LOCAL_NO_PROGRESS_LIMIT,
        "blocked": state.local_no_progress_count >= LOCAL_NO_PROGRESS_LIMIT,
    }


def _shape(node: ast.AST) -> Any:
    # Keep operations and control flow, remove identifiers/literals/docstrings.
    if isinstance(node, ast.Constant):
        return ("Constant", type(node.value).__name__)
    values = []
    for name, value in ast.iter_fields(node):
        if name in {"id", "name", "arg", "attr", "module", "asname", "type_comment"}:
            continue
        if isinstance(value, ast.AST):
            values.append((name, _shape(value)))
        elif isinstance(value, list):
            values.append(
                (
                    name,
                    tuple(
                        _shape(v)
                        for v in value
                        if isinstance(v, ast.AST)
                        and not (
                            isinstance(v, ast.Expr)
                            and isinstance(v.value, ast.Constant)
                            and isinstance(v.value.value, str)
                        )
                    ),
                )
            )
        else:
            values.append((name, value))
    return (type(node).__name__, tuple(values))


def implementation_shapes(source: str) -> Counter[str]:
    tree = ast.parse(source)
    shapes: Counter[str] = Counter()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.name.startswith(("builtin_", "ensure_")):
            continue
        shapes[hashlib.sha256(repr(_shape(node)).encode()).hexdigest()] += 1
    return shapes


def find_renamed_implementations(
    workspace: Path, changed_paths: Iterable[str], *, baseline_ref: str = ""
) -> list[str]:
    """Reject large near-identical sibling modules, not small shared helpers.

    Only compare Python implementation siblings; don't crawl artifacts/vendor
    trees. A normalized 90% match is a review signal, not a conformance score.
    """
    changed = set(changed_paths)
    candidates = [workspace / p for p in changed if p.startswith("src/") and p.endswith(".py")]
    cache: dict[Path, Counter[str]] = {}

    def shapes(path: Path) -> Counter[str]:
        if path not in cache:
            try:
                cache[path] = implementation_shapes(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, SyntaxError):
                cache[path] = Counter()
        return cache[path]

    matches = []
    for candidate in candidates:
        left = shapes(candidate)
        count = sum(left.values())
        if count < 12:
            continue
        if baseline_ref and not baseline_ref.startswith("-"):
            # A repair to an existing implementation may legitimately change
            # only one parser/transport function. Gate expansions of stubs and
            # new modules, not useful small fixes proved by before/after replay.
            prior = subprocess.run(
                ["git", "show", f"{baseline_ref}:{candidate.relative_to(workspace).as_posix()}"],
                cwd=workspace, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            )
            if prior.returncode == 0:
                try:
                    if sum(implementation_shapes(prior.stdout).values()) >= 12:
                        continue
                except SyntaxError:
                    pass
        for peer in candidate.parent.glob("*.py"):
            if peer == candidate or peer.relative_to(workspace).as_posix() in changed:
                continue
            right = shapes(peer)
            denominator = max(count, sum(right.values()))
            if sum((left & right).values()) / denominator >= 0.90:
                matches.append(
                    f"{candidate.relative_to(workspace).as_posix()} ~= {peer.relative_to(workspace).as_posix()}"
                )
                break
    return matches
