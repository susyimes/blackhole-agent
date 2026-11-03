"""Shrink a measured Python module without reopening a closed decision.

A later copy of a top-level function is removed when its signature and body
match an earlier function. Functions named in ``pinned`` stay byte-for-byte,
so a closed decision such as ``cache_decision`` cannot be rewritten by the
shrink.
"""

from __future__ import annotations

import ast
from typing import Iterable, Sequence


def shrink_measured_source(
    source: str,
    *,
    pinned: Sequence[str] = ("cache_decision",),
) -> dict[str, object]:
    """Return source with duplicate top-level functions removed.

    ``pinned`` names are never deleted and their text must still match after
    the shrink. A pinned name that is absent stays absent. The first copy of
    any other signature is kept.
    """

    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    pinned_names = {str(name) for name in pinned}
    pinned_text = _function_text(lines, tree, pinned_names)
    seen: dict[str, str] = {}
    remove_at: set[int] = set()
    removed: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name in pinned_names:
            continue
        signature = _signature(node)
        if signature in seen:
            remove_at.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
            removed.append(node.name)
            continue
        seen[signature] = node.name
    kept = [line for index, line in enumerate(lines, start=1) if index not in remove_at]
    rewritten = "".join(kept)
    rewritten_lines = rewritten.splitlines(keepends=True)
    rewritten_tree = ast.parse(rewritten)
    intact = _pinned_intact(pinned_text, rewritten_lines, rewritten_tree, pinned_names)
    return {
        "source": rewritten,
        "lines_before": _line_count(lines),
        "lines_after": _line_count(rewritten_lines),
        "removed": removed,
        "pinned_intact": intact,
        "shrunk": bool(removed) and intact and _line_count(rewritten_lines) < _line_count(lines),
    }


def _signature(node: ast.FunctionDef) -> str:
    body = ast.Module(body=list(node.body), type_ignores=[])
    return ast.dump(node.args, include_attributes=False) + ast.dump(body, include_attributes=False)


def _function_text(
    lines: list[str],
    tree: ast.AST,
    names: Iterable[str],
) -> dict[str, str]:
    wanted = set(names)
    found: dict[str, str] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            end = node.end_lineno or node.lineno
            found[node.name] = "".join(lines[node.lineno - 1 : end])
    return found


def _pinned_intact(
    pinned_text: dict[str, str],
    lines: list[str],
    tree: ast.AST,
    pinned_names: set[str],
) -> bool:
    found = _function_text(lines, tree, pinned_names)
    return found == pinned_text


def _line_count(lines: list[str]) -> int:
    if not lines:
        return 0
    if len(lines) == 1 and lines[0] == "":
        return 0
    return len(lines)
