"""Size an absolute box from an in-flow anchor border box.

A marginless card with width 80px, height 40px, and padding-left 10px has
border width 90. ``anchor-size(width)`` and ``anchor-size(height)`` copy
that border box onto an absolute or fixed tip. ``anchor-size(block)`` uses
the card's border height. A 30px fallback and a 50% fallback apply when the
anchor is missing. A missing fallback, a static box, a float anchor, an
anchor inside the tip, and a vertical tip stay invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_PAGE = '<div id="page"><div id="card"></div><div id="tip"></div><div id="next"></div></div>'
_RESET = "#page, #card, #tip, #next { margin: 0px; }"
_CARD = "#card { anchor-name: --card; width: 80px; height: 40px; padding-left: 10px; }"
_NEXT = "#next { height: 10px; }"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _edge(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
    }


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    copy = _lay(
        layout_normal_flow,
        _PAGE,
        _RESET
        + _CARD
        + _NEXT
        + "#tip { position: absolute; position-anchor: --card; left: 0px; top: 0px;"
        + " width: anchor-size(width); height: anchor-size(height); }",
    )
    fixed = _lay(
        layout_normal_flow,
        _PAGE,
        _RESET
        + _CARD
        + _NEXT
        + "#tip { position: fixed; position-anchor: --card; left: 0px; top: 0px;"
        + " width: anchor-size(width); height: anchor-size(height); }",
    )
    block = _lay(
        layout_normal_flow,
        _PAGE,
        _RESET
        + _CARD
        + _NEXT
        + "#tip { position: absolute; left: 0px; top: 0px; width: anchor-size(--card block); height: 10px; }",
    )
    floor = _lay(
        layout_normal_flow,
        _PAGE,
        _RESET
        + _CARD
        + _NEXT
        + "#tip { position: absolute; position-anchor: --card; left: 0px; top: 0px;"
        + " width: 10px; min-width: anchor-size(width); height: 10px; }",
    )
    fallback = _lay(
        layout_normal_flow,
        '<div id="page"><div id="tip"></div><div id="next"></div></div>',
        "#page, #tip, #next { margin: 0px; }"
        + "#tip { position: absolute; left: 0px; top: 0px; width: anchor-size(width, 30px); height: 10px; }"
        + "#next { height: 10px; }",
    )
    percent = _lay(
        layout_normal_flow,
        '<div id="page"><div id="tip"></div></div>',
        "#page, #tip { margin: 0px; }"
        + "#tip { position: absolute; left: 0px; top: 0px; width: anchor-size(width, 50%); height: 10px; }",
    )
    static = _lay(
        layout_normal_flow,
        '<div id="page"><div id="card"></div></div>',
        "#page, #card { margin: 0px; } #card { width: anchor-size(width); height: 10px; }",
    )
    floated = _lay(
        layout_normal_flow,
        _PAGE,
        _RESET
        + "#card { float: left; anchor-name: --card; width: 80px; height: 40px; }"
        + "#tip { position: absolute; left: 0px; top: 0px; width: anchor-size(--card width); height: 10px; }"
        + _NEXT,
    )
    inside = _lay(
        layout_normal_flow,
        '<div id="page"><div id="tip"><div id="card"></div></div></div>',
        "#page, #tip, #card { margin: 0px; }"
        + "#tip { position: absolute; left: 0px; top: 0px; width: anchor-size(--card width); height: 10px; }"
        + "#card { anchor-name: --card; width: 20px; height: 10px; }",
    )
    missing = _lay(
        layout_normal_flow,
        '<div id="page"><div id="tip"></div></div>',
        "#page, #tip { margin: 0px; }"
        + "#tip { position: absolute; left: 0px; top: 0px; width: anchor-size(width); height: 10px; }",
    )
    vertical = _lay(
        layout_normal_flow,
        _PAGE,
        _RESET
        + _CARD
        + "#tip { position: absolute; writing-mode: vertical-rl; left: 0px; top: 0px;"
        + " width: anchor-size(--card width); height: 10px; }",
    )
    card = _edge(_box(copy.get("boxes"), "card"))
    tip = _edge(_box(copy.get("boxes"), "tip"))
    nxt = _edge(_box(copy.get("boxes"), "next"))
    observed: dict[str, object] = {
        "copy": {"outcome": copy.get("outcome"), "card": card, "tip": tip, "next": nxt},
        "fixed": _edge(_box(fixed.get("boxes"), "tip")),
        "block": _edge(_box(block.get("boxes"), "tip")),
        "min_width": _edge(_box(floor.get("boxes"), "tip")),
        "fallback": _edge(_box(fallback.get("boxes"), "tip")),
        "fallback_next_y": None if _box(fallback.get("boxes"), "next") is None else _box(fallback.get("boxes"), "next").get("y"),
        "percent": _edge(_box(percent.get("boxes"), "tip")),
        "static": static.get("reason"),
        "float": floated.get("reason"),
        "inside": inside.get("reason"),
        "missing": missing.get("reason"),
        "vertical": vertical.get("reason"),
    }
    square = {"x": 0, "y": 0, "content_width": 90, "content_height": 40, "border_width": 90, "border_height": 40}
    checks = {
        "card_border_box_includes_padding": copy.get("outcome") == "placed"
        and card == {"x": 0, "y": 0, "content_width": 80, "content_height": 40, "border_width": 90, "border_height": 40},
        "absolute_copies_the_anchor_border_box": tip == square,
        "following_block_stays_under_the_card": nxt is not None and nxt.get("y") == 40 and nxt.get("border_height") == 10,
        "fixed_copies_the_same_border_box": fixed.get("outcome") == "placed" and observed["fixed"] == square,
        "block_axis_uses_the_anchor_height": block.get("outcome") == "placed"
        and observed["block"]
        == {"x": 0, "y": 0, "content_width": 40, "content_height": 10, "border_width": 40, "border_height": 10},
        "min_width_uses_the_anchor_border_width": floor.get("outcome") == "placed"
        and observed["min_width"]
        == {"x": 0, "y": 0, "content_width": 90, "content_height": 10, "border_width": 90, "border_height": 10},
        "missing_anchor_uses_a_length_fallback": fallback.get("outcome") == "placed"
        and observed["fallback"]
        == {"x": 0, "y": 0, "content_width": 30, "content_height": 10, "border_width": 30, "border_height": 10}
        and observed["fallback_next_y"] == 0,
        "missing_anchor_resolves_a_percentage_fallback": percent.get("outcome") == "placed"
        and observed["percent"]
        == {"x": 0, "y": 0, "content_width": 100, "content_height": 10, "border_width": 100, "border_height": 10},
        "static_anchor_size_is_rejected": static.get("outcome") == "invalid",
        "float_anchor_is_rejected": floated.get("outcome") == "invalid" and floated.get("reason") == "anchor is out of flow",
        "inner_anchor_is_rejected": inside.get("outcome") == "invalid"
        and inside.get("reason") == "anchor is inside the positioned box",
        "missing_fallback_is_rejected": missing.get("outcome") == "invalid"
        and missing.get("reason") == "anchor-size fallback is missing",
        "vertical_anchor_size_is_rejected": vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "anchor-size is unsupported",
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
