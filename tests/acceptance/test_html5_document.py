"""HTML documents that crashed html5lib 1.1 now return a tree.

The anchor/MathML document, the nested select, and the table that contains
svg and a second html element each serialize to a tree. A paragraph and a
table cell keep their text.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json


_MATH = ")<a><math><TR><a><mI><a><p><a>"
_SELECT = "-<math><sElect><mi><sElect><sElect>"
_TABLE = "ñ<table><svg><html>"
_MATH_TREE = ")<a><math><tr><a><mi></mi></a><a></a></math></a><p><a></a><a></a>"
_SELECT_TREE = "-<math><select><mi><select></select></mi></select></math>"
_TABLE_TREE = "ñ<svg></svg><table></table>"


def observe() -> tuple[bool, dict]:
    observed: dict = {}
    try:
        from blackhole_agent.html5_document import parse_html
    except Exception as exc:  # noqa: BLE001 - baseline without the parser still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    documents = {
        "math_anchor": _MATH,
        "nested_select": _SELECT,
        "table_svg": _TABLE,
        "paragraph": "<p>ok</p>",
        "table_cell": "<table><tr><td>a</td></tr></table>",
    }
    parsed: dict[str, str] = {}
    for name, document in documents.items():
        try:
            parsed[name] = parse_html(document)
        except Exception as exc:  # noqa: BLE001 - an unmet document stays observable
            observed[name] = {"error": type(exc).__name__, "detail": str(exc)[:240]}
            return False, observed
    observed.update(parsed)
    passed = bool(
        parsed["math_anchor"] == _MATH_TREE
        and parsed["nested_select"] == _SELECT_TREE
        and parsed["table_svg"] == _TABLE_TREE
        and parsed["paragraph"] == "<p>ok"
        and parsed["table_cell"] == "<table><tr><td>a</table>"
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
