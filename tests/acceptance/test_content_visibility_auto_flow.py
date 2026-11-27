"""Skip content-visibility auto only when the box starts below the viewport.

On a marginless page at 10px font and line-height, eight preserved lines
after a 200px spacer are 80px tall. With a 100px viewport and scroll_y 0
the box starts at the fold, so auto plus contain-intrinsic-block-size 30px
drops the lines and the next block starts at y 230. scroll_y 200 meets the
box, so the lines stay and the next block starts at y 280. A one-line box
at the origin keeps its 10px line when the intrinsic size is 30px. An
omitted viewport height keeps the eight lines. A vertical box below the
fold is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_BASE = "html, body, div { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_LINES = "A\nB\nC\nD\nE\nF\nG\nH"
_STACK = (
    f'<div id="page"><div id="spacer"></div><div id="skip">{_LINES}</div>'
    '<div id="next">Z</div></div>'
)
_ORIGIN = '<div id="page"><div id="skip">HELLO</div><div id="next">Z</div></div>'
_AUTO = (
    "#spacer { height: 200px; } "
    "#skip { white-space: pre; content-visibility: auto; contain-intrinsic-block-size: 30px; }\n"
)
_NEAR = (
    "#skip { content-visibility: auto; contain-intrinsic-block-size: 30px; }\n"
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lay(layout, markup: str, stylesheet: str, **kwargs: object) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=400, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _spot(placed: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(placed.get("boxes"), ident)
    if box is None:
        return None
    lines = box.get("lines")
    return {
        "y": box.get("y"),
        "content_height": box.get("content_height"),
        "line_count": len(lines) if isinstance(lines, list) else None,
    }


def _next_y(placed: dict[str, object]) -> object:
    spot = _spot(placed, "next")
    return None if spot is None else spot.get("y")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    below = _lay(layout_normal_flow, _STACK, _BASE + _AUTO, viewport_height=100, scroll_y=0)
    scrolled = _lay(layout_normal_flow, _STACK, _BASE + _AUTO, viewport_height=100, scroll_y=200)
    origin = _lay(layout_normal_flow, _ORIGIN, _BASE + _NEAR, viewport_height=100, scroll_y=0)
    omitted = _lay(layout_normal_flow, _STACK, _BASE + _AUTO)
    vertical = _lay(
        layout_normal_flow,
        _STACK,
        _BASE + "#spacer { height: 200px; } #skip { height: 80px; writing-mode: vertical-rl; content-visibility: auto; }\n",
        viewport_height=100,
        scroll_y=0,
    )
    hidden = _lay(
        layout_normal_flow,
        _ORIGIN,
        _BASE + "#skip { content-visibility: hidden; }\n",
        viewport_height=100,
    )
    observed = {
        "below": {"skip": _spot(below, "skip"), "next_y": _next_y(below), "outcome": below.get("outcome")},
        "scrolled": {
            "skip": _spot(scrolled, "skip"),
            "next_y": _next_y(scrolled),
            "outcome": scrolled.get("outcome"),
        },
        "origin": {"skip": _spot(origin, "skip"), "next_y": _next_y(origin), "outcome": origin.get("outcome")},
        "omitted": {"skip": _spot(omitted, "skip"), "next_y": _next_y(omitted), "outcome": omitted.get("outcome")},
        "vertical": vertical.get("reason"),
        "hidden": {"skip": _spot(hidden, "skip"), "next_y": _next_y(hidden), "outcome": hidden.get("outcome")},
    }
    below_skip = observed["below"]["skip"]
    scrolled_skip = observed["scrolled"]["skip"]
    origin_skip = observed["origin"]["skip"]
    omitted_skip = observed["omitted"]["skip"]
    hidden_skip = observed["hidden"]["skip"]
    passed = (
        below.get("outcome") == "placed"
        and isinstance(below_skip, dict)
        and below_skip.get("y") == 200
        and below_skip.get("content_height") == 30
        and below_skip.get("line_count") == 0
        and observed["below"]["next_y"] == 230
        and scrolled.get("outcome") == "placed"
        and isinstance(scrolled_skip, dict)
        and scrolled_skip.get("content_height") == 80
        and scrolled_skip.get("line_count") == 8
        and observed["scrolled"]["next_y"] == 280
        and origin.get("outcome") == "placed"
        and isinstance(origin_skip, dict)
        and origin_skip.get("content_height") == 10
        and origin_skip.get("line_count") == 1
        and observed["origin"]["next_y"] == 10
        and omitted.get("outcome") == "placed"
        and isinstance(omitted_skip, dict)
        and omitted_skip.get("content_height") == 80
        and omitted_skip.get("line_count") == 8
        and observed["omitted"]["next_y"] == 280
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "content-visibility writing mode is unsupported"
        and hidden.get("outcome") == "placed"
        and isinstance(hidden_skip, dict)
        and hidden_skip.get("content_height") == 0
        and hidden_skip.get("line_count") == 0
        and observed["hidden"]["next_y"] == 0
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
