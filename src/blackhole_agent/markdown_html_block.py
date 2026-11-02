"""Render CommonMark with HTML blocks that survive a blank line in a list.

Absorbed markdown-it 14 and markdown-it-py 4.0.0 stopped an HTML block
whenever the next line was outdented. Inside a list item a blank line is
outdented, so a comment or script ended before its closing sequence and the
rest of the block was parsed as a paragraph. Types 6 and 7 still end on a
blank line. ``render_commonmark`` uses the absorbed markdown-it-py parser.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _vendored_root() -> Path:
    root = (
        Path(__file__).resolve().parents[2]
        / "capabilities"
        / "absorbed"
        / "markdown-it-py"
        / "markdown_it_py-4.0.0"
    )
    if not (root / "markdown_it" / "rules_block" / "html_block.py").is_file():
        raise FileNotFoundError(root)
    return root


def _call_vendored(operation):
    src = _vendored_root()
    saved = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == "markdown_it" or name.startswith("markdown_it.")
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
            if name == "markdown_it" or name.startswith("markdown_it."):
                del sys.modules[name]
        sys.modules.update(saved)


def render_commonmark(source: str) -> str:
    """Render ``source`` with the absorbed CommonMark parser."""

    def run() -> str:
        import markdown_it

        loaded = Path(markdown_it.__file__).resolve()
        if _vendored_root() not in loaded.parents:
            raise ImportError(f"absorbed markdown-it-py was not loaded from {_vendored_root()}")
        if markdown_it.__version__ != "4.0.0":
            raise ImportError(f"unexpected markdown-it-py version {markdown_it.__version__}")
        return str(markdown_it.MarkdownIt("commonmark").render(source))

    return _call_vendored(run)
