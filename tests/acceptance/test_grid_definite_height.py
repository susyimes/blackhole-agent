"""Use a definite grid height as the block size of the grid.

Fixed rows keep their size. Flexible rows share the leftover content height
after row gaps. A flex factor below one leaves the rest of that content box
empty. Rows that overflow the specified height do not move the following
block. An automatic height sizes a single 1fr row to that line.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects a definite grid height exits 0.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_TWO = '<div id="page"><div id="grid"><div id="a">AB</div><div id="b">CD</div></div><div id="after"></div></div>'
_ONE = '<div id="page"><div id="grid"><div id="a">AB</div></div><div id="after"></div></div>'
_SPLIT = (
    _FONT
    + "#grid { display: grid; width: 100px; height: 80px; "
    + "grid-template-columns: 100px; grid-template-rows: 20px 1fr; }\n"
    + "#after { height: 8px; }\n"
)
_EQUAL = (
    _FONT
    + "#grid { display: grid; width: 100px; height: 80px; "
    + "grid-template-columns: 100px; grid-template-rows: 1fr 1fr; }\n"
)
_HALF = (
    _FONT
    + "#grid { display: grid; width: 100px; height: 80px; "
    + "grid-template-columns: 100px; grid-template-rows: 0.5fr; }\n"
)
_GAP = (
    _FONT
    + "#grid { display: grid; width: 100px; height: 80px; row-gap: 10px; "
    + "grid-template-columns: 100px; grid-template-rows: 20px 1fr; }\n"
)
_OVERFLOW = (
    _FONT
    + "#grid { display: grid; width: 100px; height: 40px; "
    + "grid-template-columns: 100px; grid-template-rows: 30px 30px; }\n"
)
_TINY = (
    _FONT
    + "#grid { display: grid; width: 100px; height: 4px; "
    + "grid-template-columns: 100px; grid-template-rows: 1fr; }\n"
)
_INDEFINITE = (
    _FONT
    + "#grid { display: grid; width: 100px; "
    + "grid-template-columns: 100px; grid-template-rows: 1fr; }\n"
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


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    if not isinstance(line, dict):
        return None
    return {"text": line.get("text"), "x": line.get("x"), "y": line.get("y")}


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=240)
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
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
        "line": _line(box),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    split = _lay(layout_normal_flow, _TWO, _SPLIT)
    equal = _lay(layout_normal_flow, _TWO, _EQUAL)
    half = _lay(layout_normal_flow, _ONE, _HALF)
    gapped = _lay(layout_normal_flow, _TWO, _GAP)
    overflow = _lay(layout_normal_flow, _TWO, _OVERFLOW)
    tiny = _lay(layout_normal_flow, _ONE, _TINY)
    indefinite = _lay(layout_normal_flow, _ONE, _INDEFINITE)
    observed: dict[str, object] = {
        "split_outcome": split.get("outcome"),
        "split_reason": split.get("reason"),
        "split_grid": _view(split, "grid"),
        "split_a": _view(split, "a"),
        "split_b": _view(split, "b"),
        "split_after": _view(split, "after"),
        "equal_outcome": equal.get("outcome"),
        "equal_a": _view(equal, "a"),
        "equal_b": _view(equal, "b"),
        "equal_after": _view(equal, "after"),
        "half_outcome": half.get("outcome"),
        "half_grid": _view(half, "grid"),
        "half_a": _view(half, "a"),
        "half_after": _view(half, "after"),
        "gap_outcome": gapped.get("outcome"),
        "gap_a": _view(gapped, "a"),
        "gap_b": _view(gapped, "b"),
        "gap_after": _view(gapped, "after"),
        "overflow_outcome": overflow.get("outcome"),
        "overflow_grid": _view(overflow, "grid"),
        "overflow_a": _view(overflow, "a"),
        "overflow_b": _view(overflow, "b"),
        "overflow_after": _view(overflow, "after"),
        "tiny_outcome": tiny.get("outcome"),
        "tiny_grid": _view(tiny, "grid"),
        "tiny_a": _view(tiny, "a"),
        "tiny_after": _view(tiny, "after"),
        "indefinite_outcome": indefinite.get("outcome"),
        "indefinite_reason": indefinite.get("reason"),
    }
    checks = {
        "fixed_and_flex_rows_share_the_content_height": (
            split.get("outcome") == "placed"
            and _near(_box(split.get("boxes"), "grid"), y=0, content_height=80, border_height=80)
            and _near(_box(split.get("boxes"), "a"), x=0, y=0, content_height=20, border_height=20)
            and _near(_line(_box(split.get("boxes"), "a")), text="AB", x=0, y=0)
            and _near(_box(split.get("boxes"), "b"), x=0, y=20, content_height=60, border_height=60)
            and _near(_line(_box(split.get("boxes"), "b")), text="CD", x=0, y=20)
            and _near(_box(split.get("boxes"), "after"), y=80)
        ),
        "equal_flex_rows_split_the_content_height": (
            equal.get("outcome") == "placed"
            and _near(_box(equal.get("boxes"), "a"), y=0, content_height=40, border_height=40)
            and _near(_box(equal.get("boxes"), "b"), y=40, content_height=40, border_height=40)
            and _near(_box(equal.get("boxes"), "after"), y=80)
        ),
        "fractional_flex_leaves_the_rest_of_the_content_box_empty": (
            half.get("outcome") == "placed"
            and _near(_box(half.get("boxes"), "grid"), content_height=80, border_height=80)
            and _near(_box(half.get("boxes"), "a"), y=0, content_height=40, border_height=40)
            and _near(_box(half.get("boxes"), "after"), y=80)
        ),
        "row_gap_is_reserved_before_flex_rows_grow": (
            gapped.get("outcome") == "placed"
            and _near(_box(gapped.get("boxes"), "a"), y=0, content_height=20, border_height=20)
            and _near(_box(gapped.get("boxes"), "b"), y=30, content_height=50, border_height=50)
            and _near(_box(gapped.get("boxes"), "after"), y=80)
        ),
        "overflowing_rows_do_not_move_the_following_block": (
            overflow.get("outcome") == "placed"
            and _near(_box(overflow.get("boxes"), "grid"), content_height=40, border_height=40)
            and _near(_box(overflow.get("boxes"), "a"), y=0, content_height=30, border_height=30)
            and _near(_box(overflow.get("boxes"), "b"), y=30, content_height=30, border_height=30)
            and _near(_box(overflow.get("boxes"), "after"), y=40)
        ),
        "content_minimum_grows_a_flex_row_past_the_specified_height": (
            tiny.get("outcome") == "placed"
            and _near(_box(tiny.get("boxes"), "grid"), content_height=4, border_height=4)
            and _near(_box(tiny.get("boxes"), "a"), y=0, content_height=10, border_height=10)
            and _near(_line(_box(tiny.get("boxes"), "a")), text="AB", y=0)
            and _near(_box(tiny.get("boxes"), "after"), y=4)
        ),
        "indefinite_height_sizes_a_flex_row_to_its_line": (
            indefinite.get("outcome") == "placed"
            and _near(_box(indefinite.get("boxes"), "grid"), y=0, content_height=10, border_height=10)
            and _near(_box(indefinite.get("boxes"), "a"), y=0, content_height=10, border_height=10)
            and _near(_line(_box(indefinite.get("boxes"), "a")), text="AB", x=0, y=0)
            and _near(_box(indefinite.get("boxes"), "after"), y=10)
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
