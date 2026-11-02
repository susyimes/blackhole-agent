"""Footnote labels are recorded in the index map.

The absorbed mistune 3.4.0 renderer still asked ``key not in notes`` for every
inline reference. ``notes`` is a list, so n distinct references scanned n
labels each. The index map is already maintained beside that list. Membership
belongs on the map. A list that rejects membership tests must still accept a
new label, and ``mistune.html`` — the entry the absorption adapter calls —
must keep emitting one item per distinct label.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from typing import Any

_SLUG = "mistune-markdown"


class _RejectingList(list):
    """Label list whose membership test fails closed.

    The repaired parser must not ask this list whether a key is present.
    Appending a newly admitted label is allowed.
    """

    def __contains__(self, item: object) -> bool:
        raise AssertionError("footnote membership must use footnote_indexes")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _vendored_src() -> Path:
    src = _repo_root() / "capabilities" / "absorbed" / _SLUG / "src"
    if not (src / "mistune" / "__init__.py").is_file():
        raise FileNotFoundError(src / "mistune" / "__init__.py")
    return src


def _call_vendored(operation):
    src = _vendored_src()
    saved = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == "mistune" or name.startswith("mistune.")
    }
    sys.path.insert(0, str(src))
    try:
        importlib.invalidate_caches()
        return operation()
    finally:
        try:
            sys.path.remove(str(src))
        except ValueError:
            pass
        for name in list(sys.modules):
            if name == "mistune" or name.startswith("mistune."):
                del sys.modules[name]
        sys.modules.update(saved)


def footnote_admission() -> dict[str, Any]:
    """Admit label SECOND while the label list rejects membership tests."""

    def run() -> dict[str, Any]:
        from mistune.core import InlineState
        from mistune.inline_parser import InlineParser
        from mistune.plugins.footnotes import INLINE_FOOTNOTE, parse_inline_footnote

        notes = _RejectingList(["FIRST"])
        indexes = {"FIRST": 0}
        state = InlineState(
            {
                "ref_footnotes": {"FIRST": "First note", "SECOND": "Second note"},
                "footnotes": notes,
                "footnote_indexes": indexes,
            }
        )
        match = re.match(INLINE_FOOTNOTE, "[^second]")
        if match is None:
            return {
                "error": "no match",
                "notes": list(notes),
                "indexes": dict(indexes),
                "tokens": [],
            }
        error = ""
        try:
            parse_inline_footnote(InlineParser(), match, state)
        except AssertionError as exc:
            error = str(exc)
        return {
            "error": error,
            "notes": list(notes),
            "indexes": dict(indexes),
            "tokens": list(state.tokens),
        }

    return _call_vendored(run)


def render_markdown(source: str) -> str:
    """Render with the same ``mistune.html`` entry the absorption adapter uses."""

    def run() -> str:
        import mistune

        return str(mistune.html(source))

    return _call_vendored(run)
