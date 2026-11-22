"""Place column-span:all inside a height-constrained column-fill:auto container.

The line before the spanner is balanced and shortened. The spanner takes
the full content width. The line after it fills the leftover block size in
source order, including a column break, and the following block stays at
the specified multicol height.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the spanner exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_PAGE = "#page { font-size: 10px; line-height: 10px; }\n"
_MARK = (
    '<div id="page"><div id="cols"><p id="a">A</p><p id="b">B</p>'
    '<p id="span">S</p><p id="c">C</p><p id="d">D</p></div><p id="next">Z</p></div>'
)
_CSS = (
    _PAGE
    + "#cols { column-count: 2; column-gap: 0px; width: 80px; height: 100px; column-fill: auto; }\n"
    + "#a, #b { height: 40px; }\n"
    + "#span { column-span: all; height: 20px; }\n"
    + "#c, #d { height: 20px; }\n"
)
_BREAK = _CSS + "#d { break-before: column; }\n"
_PLAIN = (
    '<div id="page"><div id="cols"><p id="a">A</p><p id="b">B</p><p id="c">C</p>'
    '</div><p id="next">Z</p></div>'
)
_PLAIN_CSS = (
    _PAGE
    + "#cols { column-count: 2; column-gap: 0px; width: 80px; height: 20px; column-fill: auto; }\n"
    + "#a, #b, #c { height: 20px; }\n"
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

    spanned = _lay(layout_normal_flow, _MARK, _CSS)
    broken = _lay(layout_normal_flow, _MARK, _BREAK)
    plain = _lay(layout_normal_flow, _PLAIN, _PLAIN_CSS)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    observed = {
        "span_outcome": spanned.get("outcome"),
        "span_reason": spanned.get("reason"),
        "a": _view(spanned, "a"),
        "b": _view(spanned, "b"),
        "span": _view(spanned, "span"),
        "c": _view(spanned, "c"),
        "d": _view(spanned, "d"),
        "cols": _view(spanned, "cols"),
        "next_y": None if take(spanned, "next") is None else take(spanned, "next").get("y"),
        "break_d": _view(broken, "d"),
        "break_next_y": None if take(broken, "next") is None else take(broken, "next").get("y"),
        "plain_outcome": plain.get("outcome"),
        "plain_c": _view(plain, "c"),
        "plain_next_y": None if take(plain, "next") is None else take(plain, "next").get("y"),
    }
    checks = {
        "content_before_the_spanner_is_balanced_and_shortened": (
            spanned.get("outcome") == "placed"
            and _near(take(spanned, "a"), x=0, y=0, content_width=40, content_height=40)
            and _near(take(spanned, "b"), x=40, y=0, content_width=40, content_height=40)
        ),
        "the_spanner_uses_the_full_content_width_under_that_line": (
            _near(take(spanned, "span"), x=0, y=40, content_width=80, content_height=20)
        ),
        "content_after_the_spanner_fills_the_leftover_column_in_source_order": (
            _near(take(spanned, "c"), x=0, y=60, content_width=40, content_height=20)
            and _near(take(spanned, "d"), x=0, y=80, content_width=40, content_height=20)
        ),
        "the_following_block_stays_at_the_specified_height": (
            _near(take(spanned, "cols"), content_height=100)
            and _near(take(spanned, "next"), y=100)
        ),
        "a_column_break_after_the_spanner_starts_the_next_column": (
            broken.get("outcome") == "placed"
            and _near(take(broken, "d"), x=40, y=60, content_width=40, content_height=20)
            and _near(take(broken, "next"), y=100)
        ),
        "a_fixed_fill_without_a_spanner_still_overflows_the_last_column": (
            plain.get("outcome") == "placed"
            and _near(take(plain, "a"), x=0, y=0, content_width=40, content_height=20)
            and _near(take(plain, "b"), x=40, y=0, content_width=40, content_height=20)
            and _near(take(plain, "c"), x=40, y=20, content_width=40, content_height=20)
            and _near(take(plain, "next"), y=20)
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
