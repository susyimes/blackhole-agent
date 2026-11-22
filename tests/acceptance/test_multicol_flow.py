"""Flow normal-flow children through a CSS multicol container.

A column-count of 2 wraps a child at the used column width and parks the
next child in the other column. Three short boxes balance by stacking two
in the first column. column-span all ends that line. column-width stretches
into the content box. column-fill auto is rejected. The following block
starts under the multicol box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still ignores column-count exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_PAGE = "#page { font-size: 10px; line-height: 10px; }\n"
_WRAP = (
    '<div id="page"><div id="cols"><p id="a">AA BB</p><p id="b">CC</p></div>'
    '<p id="next">Z</p></div>'
)
_WRAP_CSS = _PAGE + "#cols { column-count: 2; column-gap: 0px; width: 80px; }\n"
_STACK = (
    '<div id="page"><div id="cols"><p id="a">A</p><p id="b">B</p><p id="c">C</p></div>'
    '<p id="next">Z</p></div>'
)
_STACK_CSS = _PAGE + "#cols { column-count: 2; column-gap: 0px; width: 40px; }\n"
_SPAN = (
    '<div id="page"><div id="cols"><p id="a">AA</p><p id="span">SPAN</p>'
    '<p id="b">BB</p></div><p id="next">Z</p></div>'
)
_SPAN_CSS = _PAGE + "#cols { column-count: 2; column-gap: 0px; width: 80px; }\n#span { column-span: all; }\n"
_GAP = '<div id="page"><div id="cols"><p id="a">AA</p><p id="b">BB</p></div><p id="next">Z</p></div>'
_GAP_CSS = _PAGE + "#cols { column-count: 2; column-gap: 20px; width: 100px; }\n"
_STRETCH_CSS = _PAGE + "#cols { column-width: 30px; column-gap: 10px; width: 100px; }\n"
_AUTO_CSS = _PAGE + "#cols { column-count: 2; column-gap: 0px; width: 80px; column-fill: auto; }\n"


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

    wrap = _lay(layout_normal_flow, _WRAP, _WRAP_CSS)
    stack = _lay(layout_normal_flow, _STACK, _STACK_CSS)
    span = _lay(layout_normal_flow, _SPAN, _SPAN_CSS)
    gap = _lay(layout_normal_flow, _GAP, _GAP_CSS)
    stretch = _lay(layout_normal_flow, _GAP, _STRETCH_CSS)
    auto = _lay(layout_normal_flow, _GAP, _AUTO_CSS)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    observed: dict[str, object] = {
        "wrap_outcome": wrap.get("outcome"),
        "wrap_reason": wrap.get("reason"),
        "wrap_a": _view(wrap, "a"),
        "wrap_b": _view(wrap, "b"),
        "wrap_cols": _view(wrap, "cols"),
        "wrap_next_y": None if take(wrap, "next") is None else take(wrap, "next").get("y"),
        "stack_outcome": stack.get("outcome"),
        "stack_reason": stack.get("reason"),
        "stack_a": _view(stack, "a"),
        "stack_b": _view(stack, "b"),
        "stack_c": _view(stack, "c"),
        "stack_next_y": None if take(stack, "next") is None else take(stack, "next").get("y"),
        "span_outcome": span.get("outcome"),
        "span_reason": span.get("reason"),
        "span_a": _view(span, "a"),
        "span_box": _view(span, "span"),
        "span_b": _view(span, "b"),
        "span_next_y": None if take(span, "next") is None else take(span, "next").get("y"),
        "gap_outcome": gap.get("outcome"),
        "gap_reason": gap.get("reason"),
        "gap_a": _view(gap, "a"),
        "gap_b": _view(gap, "b"),
        "gap_next_y": None if take(gap, "next") is None else take(gap, "next").get("y"),
        "stretch_outcome": stretch.get("outcome"),
        "stretch_reason": stretch.get("reason"),
        "stretch_a": _view(stretch, "a"),
        "stretch_b": _view(stretch, "b"),
        "stretch_next_y": None if take(stretch, "next") is None else take(stretch, "next").get("y"),
        "auto_outcome": auto.get("outcome"),
        "auto_reason": auto.get("reason"),
    }
    checks = {
        "wrapped_child_uses_the_column_and_the_next_child_sits_beside_it": (
            wrap.get("outcome") == "placed"
            and _near(take(wrap, "a"), x=0, y=0, content_width=40, content_height=20)
            and _near(take(wrap, "b"), x=40, y=0, content_width=40, content_height=10)
            and _near(take(wrap, "cols"), content_height=20)
            and _near(take(wrap, "next"), y=20)
        ),
        "three_boxes_balance_by_stacking_the_second_in_the_first_column": (
            stack.get("outcome") == "placed"
            and _near(take(stack, "a"), x=0, y=0, content_width=20, content_height=10)
            and _near(take(stack, "b"), x=0, y=10, content_width=20, content_height=10)
            and _near(take(stack, "c"), x=20, y=0, content_width=20, content_height=10)
            and _near(take(stack, "next"), y=20)
        ),
        "column_span_all_ends_the_line_and_the_next_child_starts_below": (
            span.get("outcome") == "placed"
            and _near(take(span, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(span, "span"), x=0, y=10, content_width=80, content_height=10)
            and _near(take(span, "b"), x=0, y=20, content_width=40, content_height=10)
            and _near(take(span, "next"), y=30)
        ),
        "column_gap_separates_the_second_child": (
            gap.get("outcome") == "placed"
            and _near(take(gap, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(gap, "b"), x=60, y=0, content_width=40, content_height=10)
            and _near(take(gap, "next"), y=10)
        ),
        "column_width_stretches_to_fill_the_content_box": (
            stretch.get("outcome") == "placed"
            and _near(take(stretch, "a"), x=0, y=0, content_width=45, content_height=10)
            and _near(take(stretch, "b"), x=55, y=0, content_width=45, content_height=10)
            and _near(take(stretch, "next"), y=10)
        ),
        "column_fill_auto_is_rejected": auto.get("outcome") == "invalid",
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
