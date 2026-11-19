"""Reorder each bidirectional line, including a trailing space and a mirrored bracket.

One line of alef, space, bet displays bet, space, alef. The same string
broken after the space displays alef, space and then bet. A right-to-left
paragraph of parenthesis, a, b, parenthesis displays parenthesis, a, b,
parenthesis. A short line end, an empty line, and an unknown direction are
invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    from blackhole_agent.unicode_bidi import reorder_bidi_lines

    hebrew = "\u05d0 \u05d1"
    one = reorder_bidi_lines(hebrew, [3], "ltr")
    split = reorder_bidi_lines(hebrew, [2, 3], "ltr")
    mirrored = reorder_bidi_lines("(ab)", [4], "rtl")
    marked = reorder_bidi_lines("\u05d0\u0307", [2], "ltr")
    short = reorder_bidi_lines(hebrew, [2], "ltr")
    empty = reorder_bidi_lines(hebrew, [1, 1, 3], "ltr")
    direction = reorder_bidi_lines(hebrew, [3], "sideways")
    observed = {
        "one_line": one["lines"][0]["text"] if one.get("lines") else one.get("reason"),
        "split": [line["text"] for line in split["lines"]] if split.get("lines") else split.get("reason"),
        "split_levels": split["lines"][0]["levels"] if split.get("lines") else None,
        "mirrored": mirrored["lines"][0]["text"] if mirrored.get("lines") else mirrored.get("reason"),
        "mirrored_order": mirrored["lines"][0]["visual_order"] if mirrored.get("lines") else None,
        "mark": marked["lines"][0]["text"] if marked.get("lines") else marked.get("reason"),
        "short": short.get("reason"),
        "empty_line": empty.get("reason"),
        "direction": direction.get("reason"),
    }
    passed = (
        observed["one_line"] == "\u05d1 \u05d0"
        and observed["split"] == ["\u05d0 ", "\u05d1"]
        and observed["split_levels"] == [1, 0]
        and observed["mirrored"] == "(ab)"
        and observed["mirrored_order"] == [3, 1, 2, 0]
        and observed["mark"] == "\u05d0\u0307"
        and observed["short"] == "line ends must cover the string"
        and observed["empty_line"] == "line is empty"
        and observed["direction"] == "direction must be ltr, rtl, or auto"
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet behavior and baseline both exit 0
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
