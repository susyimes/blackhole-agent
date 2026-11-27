"""Flip an anchored box when its position-area cannot hold it.

An absolute box whose block-start area is shorter than its margin box moves
to the anchor's block-end edge when position-try-fallbacks is flip-block.
Omitting the property keeps the overflowing block-start position. A base
area that already fits ignores the tactic. An unknown tactic is invalid.
The anchor and the following in-flow block stay put.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = '<div id="card"></div><div id="tip"></div><div id="next"></div>'
_CARD = "#card { anchor-name: --card; margin-left: 100px; width: 40px; height: 20px; }"
_TIP = (
    "#tip { position: absolute; position-anchor: --card; position-area: block-start;"
    " width: 50px; height: 30px; }"
)
_NEXT = "#next { width: 10px; height: 10px; }"
_OVERFLOW = (_PAGE, _CARD + _TIP + " #tip { position-try-fallbacks: flip-block; }" + _NEXT)
_BARE = (_PAGE, _CARD + _TIP + _NEXT)
_FITTING = (
    _PAGE,
    _CARD.replace("width:", "margin-top: 40px; width:")
    + _TIP
    + " #tip { position-try-fallbacks: flip-block; }"
    + _NEXT,
)
_FITTING_BARE = (
    _PAGE,
    _CARD.replace("width:", "margin-top: 40px; width:") + _TIP + _NEXT,
)
_UNKNOWN = (_PAGE, _CARD + _TIP + " #tip { position-try-fallbacks: spin; }" + _NEXT)


def _place(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=400, viewport_height=300)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
    if not isinstance(result, dict):
        return {"outcome": "error", "reason": "result"}
    return result


def _box(result: dict[str, object], box_id: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == box_id:
            return item
    return None


def _number(value: object) -> int | None:
    if type(value) is bool or not isinstance(value, (int, float)):
        return None
    return int(value)


def _edge(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
        "position_try": box.get("position_try"),
    }


def _centered(card: dict[str, object] | None, tip: dict[str, object] | None) -> bool:
    if card is None or tip is None:
        return False
    card_x, card_w = _number(card.get("x")), _number(card.get("border_width"))
    tip_x, tip_w = _number(tip.get("x")), _number(tip.get("border_width"))
    if None in {card_x, card_w, tip_x, tip_w}:
        return False
    return 2 * tip_x + tip_w == 2 * card_x + card_w and tip_w == 50


def _on_start(card: dict[str, object] | None, tip: dict[str, object] | None) -> bool:
    if card is None or tip is None:
        return False
    card_y = _number(card.get("y"))
    tip_y, tip_h = _number(tip.get("y")), _number(tip.get("border_height"))
    if None in {card_y, tip_y, tip_h}:
        return False
    return tip_y + tip_h == card_y and tip_h == 30


def _on_end(card: dict[str, object] | None, tip: dict[str, object] | None) -> bool:
    if card is None or tip is None:
        return False
    card_y, card_h = _number(card.get("y")), _number(card.get("border_height"))
    tip_y = _number(tip.get("y"))
    if None in {card_y, card_h, tip_y}:
        return False
    return tip_y == card_y + card_h and tip_y >= 0


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    flipped = _place(layout_normal_flow, *_OVERFLOW)
    bare = _place(layout_normal_flow, *_BARE)
    fitting = _place(layout_normal_flow, *_FITTING)
    fitting_bare = _place(layout_normal_flow, *_FITTING_BARE)
    unknown = _place(layout_normal_flow, *_UNKNOWN)
    flip_card, flip_tip, flip_next = _box(flipped, "card"), _box(flipped, "tip"), _box(flipped, "next")
    bare_card, bare_tip, bare_next = _box(bare, "card"), _box(bare, "tip"), _box(bare, "next")
    fit_card, fit_tip = _box(fitting, "card"), _box(fitting, "tip")
    fit_bare_tip = _box(fitting_bare, "tip")
    observed: dict[str, object] = {
        "flipped": {
            "outcome": flipped.get("outcome"),
            "reason": flipped.get("reason"),
            "card": _edge(flip_card),
            "tip": _edge(flip_tip),
            "next": _edge(flip_next),
        },
        "bare": {
            "outcome": bare.get("outcome"),
            "tip": _edge(bare_tip),
            "next": _edge(bare_next),
        },
        "fitting": {
            "outcome": fitting.get("outcome"),
            "tip": _edge(fit_tip),
            "card": _edge(fit_card),
        },
        "unknown": {"outcome": unknown.get("outcome"), "reason": unknown.get("reason")},
    }
    bare_y = _number(None if bare_tip is None else bare_tip.get("y"))
    passed = (
        flipped.get("outcome") == "placed"
        and bare.get("outcome") == "placed"
        and fitting.get("outcome") == "placed"
        and fitting_bare.get("outcome") == "placed"
        and _centered(flip_card, flip_tip)
        and _on_end(flip_card, flip_tip)
        and flip_tip is not None
        and flip_tip.get("position_try") == "flip-block"
        and _centered(bare_card, bare_tip)
        and _on_start(bare_card, bare_tip)
        and bare_y is not None
        and bare_y < 0
        and bare_tip is not None
        and "position_try" not in bare_tip
        and flip_card is not None
        and bare_card is not None
        and flip_card.get("x") == bare_card.get("x")
        and flip_card.get("y") == bare_card.get("y")
        and flip_next is not None
        and bare_next is not None
        and flip_next.get("x") == bare_next.get("x")
        and flip_next.get("y") == bare_next.get("y")
        and _centered(fit_card, fit_tip)
        and _on_start(fit_card, fit_tip)
        and _number(None if fit_tip is None else fit_tip.get("y")) is not None
        and _number(fit_tip.get("y")) >= 0
        and fit_tip is not None
        and fit_tip.get("position_try") == "base"
        and fit_bare_tip is not None
        and fit_tip.get("x") == fit_bare_tip.get("x")
        and fit_tip.get("y") == fit_bare_tip.get("y")
        and unknown.get("outcome") == "invalid"
        and unknown.get("reason") == "position-try-fallbacks is invalid"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
