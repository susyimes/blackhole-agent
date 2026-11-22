"""Fill a height-constrained multicol container in source order.

``column-fill: auto`` with a definite height parks a child that does not fit
in the next column, honors a column break, keeps an avoid-column pair
together, and overflows the last column. The following block stays under
the specified border box. An automatic height still balances. ``column-span:
all`` inside the fixed fill shortens the line above the spanner and keeps
that specified height.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects column-fill auto exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_PAGE = "#page { font-size: 10px; line-height: 10px; }\n"
_THREE = (
    '<div id="page"><div id="cols"><p id="a">A</p><p id="b">B</p><p id="c">C</p>'
    '</div><p id="next">Z</p></div>'
)
_TWO = (
    '<div id="page"><div id="cols"><p id="a">A</p><p id="b">B</p></div>'
    '<p id="next">Z</p></div>'
)
_SPAN = (
    '<div id="page"><div id="cols"><p id="a">A</p><p id="span">S</p></div>'
    '<p id="next">Z</p></div>'
)
_FIXED = _PAGE + "#cols { column-count: 2; column-gap: 0px; width: 80px; height: 20px; column-fill: auto; }\n"
_TALL = _FIXED + "#a, #b, #c { height: 20px; }\n"
_BREAK = (
    _PAGE
    + "#cols { column-count: 2; column-gap: 0px; width: 80px; height: 40px; column-fill: auto; }\n"
    + "#a, #b { height: 10px; }\n"
)
_PAGE_BREAK = _BREAK + "#b { break-before: page; }\n"
_COLUMN_BREAK = _BREAK + "#b { break-before: column; }\n"
_AFTER_BREAK = _BREAK + "#a { break-after: column; }\n"
_EMPTY_BREAK = _BREAK + "#a { break-before: column; }\n"
_AVOID = (
    _PAGE
    + "#cols { column-count: 2; column-gap: 0px; width: 80px; height: 30px; column-fill: auto; }\n"
    + "#a, #b { height: 10px; }\n"
    + "#c { height: 20px; break-before: avoid-column; }\n"
)
_OPEN = _PAGE + "#cols { column-count: 2; column-gap: 0px; width: 40px; column-fill: auto; }\n"
_SPANNED = (
    _PAGE
    + "#cols { column-count: 2; column-gap: 0px; width: 80px; height: 40px; column-fill: auto; }\n"
    + "#span { column-span: all; }\n"
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _view(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "overflow": _lay(layout_normal_flow, _THREE, _TALL),
        "page_break": _lay(layout_normal_flow, _TWO, _PAGE_BREAK),
        "column_break": _lay(layout_normal_flow, _TWO, _COLUMN_BREAK),
        "after_break": _lay(layout_normal_flow, _TWO, _AFTER_BREAK),
        "empty_break": _lay(layout_normal_flow, _TWO, _EMPTY_BREAK),
        "avoid": _lay(layout_normal_flow, _THREE, _AVOID),
        "open": _lay(layout_normal_flow, _THREE, _OPEN),
        "span": _lay(layout_normal_flow, _SPAN, _SPANNED),
    }

    def take(name: str, ident: str) -> dict[str, object] | None:
        return _box(cases[name].get("boxes"), ident)

    observed: dict[str, object] = {
        name: {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "a": _view(result, "a"),
            "b": _view(result, "b"),
            "c": _view(result, "c"),
            "span": _view(result, "span"),
            "cols": _view(result, "cols"),
            "next_y": None if _box(result.get("boxes"), "next") is None else _box(result.get("boxes"), "next").get("y"),
        }
        for name, result in cases.items()
    }
    checks = {
        "third_child_overflows_the_last_column_and_the_next_block_stays_at_the_border": (
            cases["overflow"].get("outcome") == "placed"
            and _near(take("overflow", "a"), x=0, y=0, content_width=40, content_height=20)
            and _near(take("overflow", "b"), x=40, y=0, content_width=40, content_height=20)
            and _near(take("overflow", "c"), x=40, y=20, content_width=40, content_height=20)
            and _near(take("overflow", "cols"), content_height=20)
            and _near(take("overflow", "next"), y=20)
        ),
        "break_before_page_keeps_the_second_child_in_the_first_column": (
            cases["page_break"].get("outcome") == "placed"
            and _near(take("page_break", "a"), x=0, y=0, content_height=10)
            and _near(take("page_break", "b"), x=0, y=10, content_height=10)
            and _near(take("page_break", "next"), y=40)
        ),
        "break_before_column_parks_the_second_child_in_the_next_column": (
            cases["column_break"].get("outcome") == "placed"
            and _near(take("column_break", "a"), x=0, y=0)
            and _near(take("column_break", "b"), x=40, y=0)
            and _near(take("column_break", "next"), y=40)
        ),
        "break_after_column_does_the_same": (
            cases["after_break"].get("outcome") == "placed"
            and _near(take("after_break", "a"), x=0, y=0)
            and _near(take("after_break", "b"), x=40, y=0)
        ),
        "a_column_break_on_the_first_child_does_not_leave_an_empty_column": (
            cases["empty_break"].get("outcome") == "placed"
            and _near(take("empty_break", "a"), x=0, y=0)
            and _near(take("empty_break", "b"), x=0, y=10)
        ),
        "avoid_column_moves_the_fitting_pair_together": (
            cases["avoid"].get("outcome") == "placed"
            and _near(take("avoid", "a"), x=0, y=0, content_height=10)
            and _near(take("avoid", "b"), x=40, y=0, content_height=10)
            and _near(take("avoid", "c"), x=40, y=10, content_height=20)
            and _near(take("avoid", "cols"), content_height=30)
            and _near(take("avoid", "next"), y=30)
        ),
        "an_automatic_height_still_balances": (
            cases["open"].get("outcome") == "placed"
            and _near(take("open", "a"), x=0, y=0, content_width=20, content_height=10)
            and _near(take("open", "b"), x=0, y=10, content_width=20, content_height=10)
            and _near(take("open", "c"), x=20, y=0, content_width=20, content_height=10)
            and _near(take("open", "next"), y=20)
        ),
        "a_spanner_inside_the_fixed_fill_shortens_the_line_and_keeps_the_height": (
            cases["span"].get("outcome") == "placed"
            and _near(take("span", "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take("span", "span"), x=0, y=10, content_width=80, content_height=10)
            and _near(take("span", "cols"), content_height=40)
            and _near(take("span", "next"), y=40)
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 even when it fails
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    payload = {"passed": bool(passed), "observed": observed if observed else {"error": "empty"}}
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    except (UnicodeEncodeError, TypeError) as exc:
        encoded = json.dumps(
            {"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}},
            separators=(",", ":"),
        ).encode("ascii")
    sys.stdout.buffer.write(encoded + b"\n")


if __name__ == "__main__":
    main()
