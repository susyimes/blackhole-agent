"""Parse HTML documents that html5lib 1.1 crashes on.

MathML adoption and a select nested in MathML used to raise while a full
document was being built. A table that ends on a second html element did the
same. The absorbed parser now finishes those documents, and this entry returns
the serialized tree.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


_HTML5LIB = None


def _package_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "capabilities"
        / "absorbed"
        / "html5lib"
        / "html5lib-1.1"
    )


def _ensure_import_deps() -> None:
    """html5lib 1.1 imports six and webencodings before it parses a string."""

    if "six" not in sys.modules:
        try:
            import six  # noqa: F401
        except ImportError:
            import http.client
            import urllib

            six = types.ModuleType("six")
            six.text_type = str
            six.binary_type = bytes
            six.string_types = (str,)
            six.PY2 = False
            six.PY3 = True
            six.unichr = chr
            six.with_metaclass = lambda meta, *bases: meta("NewBase", bases, {})
            six.viewkeys = lambda mapping: mapping.keys()
            moves = types.ModuleType("six.moves")
            moves.http_client = http.client
            moves.urllib = urllib
            sys.modules["six"] = six
            sys.modules["six.moves"] = moves
    if "webencodings" not in sys.modules:
        try:
            import webencodings  # noqa: F401
        except ImportError:
            webencodings = types.ModuleType("webencodings")

            class _Encoding:
                name = "utf-8"

            webencodings.lookup = lambda _label: _Encoding()
            sys.modules["webencodings"] = webencodings


def _html5lib():
    global _HTML5LIB
    if _HTML5LIB is not None:
        return _HTML5LIB
    _ensure_import_deps()
    package = _package_dir()
    sys.path.insert(0, str(package))
    import html5lib

    loaded = Path(html5lib.__file__).resolve()
    if package not in loaded.parents:
        raise ImportError(f"absorbed html5lib was not loaded from {package}")
    _HTML5LIB = html5lib
    return html5lib


def parse_html(markup: str) -> str:
    """Parse a document and return the html5lib serialization of its tree."""

    html5lib = _html5lib()
    document = html5lib.parse(markup)
    walker = html5lib.getTreeWalker("etree")
    from html5lib.serializer import HTMLSerializer

    return "".join(HTMLSerializer().serialize(walker(document)))
