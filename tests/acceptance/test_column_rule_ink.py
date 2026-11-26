"""Paint a CSS column-rule between occupied columns without moving them.

A 230px multicol with three 70px columns and a 10px gap centers a 4px rule
at x 73 and x 153. The third gap is omitted when that column is empty. A
fixed 40px column-height keeps the stroke at 40 while the content is 30. A
spanner row has no stroke. A 16px rule stays centered and spills out of the
gap. An odd leftover pixel stays on the inline end. none, hidden, a zero
width, and a rule declared only on a child paint nothing. A negative width
is invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_BASE = (
    "html, body, div { margin: 0px; }\n"
    "#page { font-size: 10px; line-height: 10px; width: 400px; }\n"
    "#next { height: 8px; }\n"
)
_THREE = "#cols { column-count: 3; column-gap: 10px; width: 230px; }\n"
_PAIR = "#a, #b { height: 20px; }\n"
_TRIPLE = "#a, #b, #c { height: 20px; }\n"


def _markup(ids: str) -> str:
    children = "".join(f'<div id="{ident}"></div>' for ident in ids.split())
    return f'<div id="page"><div id="cols">{children}</div><div id="next"></div></div>'


def _layout(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = function(markup, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(placed, dict):
        return {"outcome": "error", "reason": "layout is invalid", "boxes": None}
    return placed


def _box(result: dict[str, object], ident: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _edge(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result, ident)
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
    }


def _rules(result: dict[str, object]) -> object:
    box = _box(result, "cols")
    if box is None:
        return None
    return box.get("rules")


def _stroke(x: int, y: int, width: int, height: int, color: str = "#010203") -> dict[str, object]:
    return {"color": color, "height": height, "style": "solid", "width": width, "x": x, "y": y}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    def lay(ids: str, stylesheet: str) -> dict[str, object]:
        return _layout(layout_normal_flow, _markup(ids), _BASE + stylesheet)

    occupied = lay("a b c", _THREE + "#cols { column-rule: 4px solid #010203; }\n" + _TRIPLE)
    partial = lay("a b", _THREE + "#cols { column-rule: 4px solid #010203; }\n" + _PAIR)
    single = lay("a", _THREE + "#cols { column-rule: 4px solid #010203; }\n#a { height: 20px; }\n")
    bare = lay("a b c", _THREE + _TRIPLE)
    wide = lay("a b c", _THREE + "#cols { column-rule: 16px solid #010203; }\n" + _TRIPLE)
    odd = lay("a b c", _THREE + "#cols { column-rule: 3px solid #010203; }\n" + _TRIPLE)
    fixed = lay(
        "a b",
        _THREE + "#cols { column-height: 40px; row-gap: 0px; column-rule: 4px solid #010203; }\n"
        "#a, #b { height: 30px; }\n",
    )
    spanned = lay(
        "a b s c d",
        "#cols { column-count: 2; column-gap: 10px; width: 110px; column-height: 40px; "
        "row-gap: 10px; column-rule: 4px solid #010203; }\n"
        "#a, #b, #c, #d { height: 30px; }\n#s { height: 12px; column-span: all; }\n",
    )
    filled = lay(
        "a b c",
        _THREE + "#cols { height: 40px; column-fill: auto; column-rule: 4px solid #010203; }\n"
        "#a, #b, #c { height: 15px; }\n",
    )
    current = lay("a b", _THREE + "#cols { color: #c00; column-rule: 4px solid; }\n" + _PAIR)
    reset = lay(
        "a b",
        _THREE + "#cols { column-rule-width: 8px; column-rule: solid #010203; }\n" + _PAIR,
    )
    longer = lay(
        "a b",
        _THREE + "#cols { column-rule: 4px solid #010203; column-rule-width: 8px; }\n" + _PAIR,
    )
    absent = lay("a b", _THREE + "#cols { column-rule: none; }\n" + _PAIR)
    hidden = lay("a b", _THREE + "#cols { column-rule: 4px hidden #010203; }\n" + _PAIR)
    zero = lay("a b", _THREE + "#cols { column-rule: 0 solid #010203; }\n" + _PAIR)
    child = lay(
        "a b",
        _THREE + "#a { height: 20px; column-rule: 4px solid #010203; }\n#b { height: 20px; }\n",
    )
    padded = lay(
        "a b",
        _THREE + "#cols { padding: 4px; border-width: 2px; border-style: solid; "
        "column-rule: 4px solid #010203; }\n" + _PAIR,
    )
    broken = lay("a", "#cols { column-rule: -1px solid; }\n#a { height: 10px; }\n")
    inherited = lay("a", "#cols { column-rule: inherit; }\n")
    observed: dict[str, object] = {
        "occupied": {"outcome": occupied.get("outcome"), "rules": _rules(occupied), "next": _edge(occupied, "next")},
        "partial": {"rules": _rules(partial)},
        "single": {"has_rules": "rules" in (_box(single, "cols") or {})},
        "wide": {"rules": _rules(wide), "next_y": (_edge(wide, "next") or {}).get("y")},
        "odd": {"rules": _rules(odd)},
        "fixed": {
            "rules": _rules(fixed),
            "a": _edge(fixed, "a"),
            "next_y": (_edge(fixed, "next") or {}).get("y"),
        },
        "spanned": {
            "rules": _rules(spanned),
            "s": _edge(spanned, "s"),
            "next_y": (_edge(spanned, "next") or {}).get("y"),
        },
        "filled": {"rules": _rules(filled), "b": _edge(filled, "b"), "c": _edge(filled, "c")},
        "current": {"rules": _rules(current)},
        "reset": {"rules": _rules(reset)},
        "longer": {"rules": _rules(longer)},
        "absent": {"has_rules": "rules" in (_box(absent, "cols") or {})},
        "hidden": {"has_rules": "rules" in (_box(hidden, "cols") or {})},
        "zero": {"has_rules": "rules" in (_box(zero, "cols") or {})},
        "child": {"has_rules": "rules" in (_box(child, "cols") or {}) or "rules" in (_box(child, "a") or {})},
        "padded": {"rules": _rules(padded), "a": _edge(padded, "a"), "next_y": (_edge(padded, "next") or {}).get("y")},
        "broken": {"outcome": broken.get("outcome"), "reason": broken.get("reason")},
        "inherit": {"outcome": inherited.get("outcome"), "reason": inherited.get("reason")},
    }
    same_columns = (
        occupied.get("outcome") == "placed"
        and bare.get("outcome") == "placed"
        and _edge(occupied, "a") == _edge(bare, "a")
        and _edge(occupied, "b") == _edge(bare, "b")
        and _edge(occupied, "c") == _edge(bare, "c")
        and _edge(occupied, "cols") == _edge(bare, "cols")
        and _edge(occupied, "next") == _edge(bare, "next") == {"x": 0, "y": 20, "content_width": 400, "content_height": 8}
        and _edge(wide, "a") == _edge(bare, "a")
        and _edge(wide, "next") == _edge(bare, "next")
    )
    checks = {
        "occupied_gaps_keep_the_columns": same_columns
        and _rules(occupied) == [_stroke(73, 0, 4, 20), _stroke(153, 0, 4, 20)],
        "empty_column_has_no_rule": _rules(partial) == [_stroke(73, 0, 4, 20)]
        and "rules" not in (_box(single, "cols") or {}),
        "wide_rule_stays_centered": _rules(wide) == [_stroke(67, 0, 16, 20), _stroke(147, 0, 16, 20)],
        "odd_pixel_stays_on_the_inline_end": _rules(odd) == [_stroke(73, 0, 3, 20), _stroke(153, 0, 3, 20)],
        "fixed_height_includes_the_unused_block": fixed.get("outcome") == "placed"
        and _rules(fixed) == [_stroke(73, 0, 4, 40)]
        and _edge(fixed, "a") == {"x": 0, "y": 0, "content_width": 70, "content_height": 30}
        and (_edge(fixed, "next") or {}).get("y") == 40,
        "spanner_row_has_no_rule": spanned.get("outcome") == "placed"
        and _rules(spanned) == [_stroke(53, 0, 4, 40), _stroke(53, 100, 4, 40)]
        and _edge(spanned, "s") == {"x": 0, "y": 50, "content_width": 110, "content_height": 12}
        and (_edge(spanned, "next") or {}).get("y") == 140,
        "auto_fill_uses_the_column_box": filled.get("outcome") == "placed"
        and _rules(filled) == [_stroke(73, 0, 4, 40)]
        and _edge(filled, "b") == {"x": 0, "y": 15, "content_width": 70, "content_height": 15}
        and _edge(filled, "c") == {"x": 80, "y": 0, "content_width": 70, "content_height": 15},
        "omitted_color_uses_currentcolor": _rules(current) == [_stroke(73, 0, 4, 20, "#cc0000")],
        "later_shorthand_resets_the_width": _rules(reset) == [_stroke(73, 0, 3, 20)],
        "later_longhand_sets_the_width": _rules(longer) == [_stroke(71, 0, 8, 20)],
        "none_hidden_and_zero_paint_nothing": absent.get("outcome") == "placed"
        and "rules" not in (_box(absent, "cols") or {})
        and "rules" not in (_box(hidden, "cols") or {})
        and "rules" not in (_box(zero, "cols") or {})
        and (_edge(absent, "next") or {}).get("y") == 20,
        "child_rule_is_not_inherited": child.get("outcome") == "placed"
        and "rules" not in (_box(child, "cols") or {})
        and "rules" not in (_box(child, "a") or {}),
        "padding_insets_the_stroke_with_the_columns": padded.get("outcome") == "placed"
        and _rules(padded) == [_stroke(79, 6, 4, 20)]
        and _edge(padded, "a") == {"x": 6, "y": 6, "content_width": 70, "content_height": 20}
        and (_edge(padded, "next") or {}).get("y") == 32,
        "negative_width_is_invalid": broken.get("outcome") == "invalid"
        and broken.get("reason") == "column-rule is invalid",
        "inherit_is_rejected": inherited.get("outcome") == "invalid"
        and inherited.get("reason") == "column-rule inherit is unsupported",
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
