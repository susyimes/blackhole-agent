"""TOML loading for documents the standard library still rejects.

CPython ``tomllib`` is a TOML 1.0 parser: a multiline inline table, a trailing
comma in that table, ``\\e`` and ``\\xHH`` escapes, and a time written without
seconds are decode errors. It also leaks ``ValueError`` when a decimal integer
has more digits than ``sys.get_int_max_str_digits()``. The absorbed parser
accepts those 1.1 forms and raises ``TOMLDecodeError`` for that integer. A
``parse_float`` callback's own ``ValueError`` is not a digit-limit leak and
still propagates. An unknown escape stays a decode error.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_VENDORED_SLUGS = ("tomli", "tomli-foraged", "tomli-parser")


def loads(text: str, *, parse_float=float):
    """Parse ``text`` with the absorbed TOML 1.1 parser."""

    return vendored_loads("tomli", text, parse_float=parse_float)


def vendored_slugs() -> tuple[str, ...]:
    return _VENDORED_SLUGS


def vendored_loads(slug: str, text: str, *, parse_float=float):
    """Parse with one absorbed tomli slug. The slug's parser is the contract."""

    module = _vendored_module(slug)
    return module.loads(text, parse_float=parse_float)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _vendored_module(slug: str):
    if slug not in _VENDORED_SLUGS:
        raise KeyError(slug)
    src = (
        _repo_root()
        / "capabilities"
        / "absorbed"
        / slug
        / "tomli-2.4.1"
        / "src"
    )
    init = src / "tomli" / "__init__.py"
    if not init.is_file():
        raise FileNotFoundError(init)
    saved = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == "tomli" or name.startswith("tomli.")
    }
    sys.path.insert(0, str(src))
    try:
        module = importlib.import_module("tomli")
    finally:
        try:
            sys.path.remove(str(src))
        except ValueError:
            pass
        for name in list(sys.modules):
            if name == "tomli" or name.startswith("tomli."):
                del sys.modules[name]
        sys.modules.update(saved)
    return module
