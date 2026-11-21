"""Lay out a descendant from an inline-size container query.

A named query uses the container's content box and does not style the
container itself. A different name does not lend that size. A later
unconditional width wins the cascade. Without container-type the same
query leaves the unconditional width in place. The following block starts
under the container.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A reader that still rejects @container exits 0 with passed
false.
"""

from __future__ import annotations

import json

_PAGE = (
    '<div id="page"><div id="card"><div id="item"></div></div>'
    '<p id="next">Z</p></div>'
)
_BASE = (
    "#page { font-size: 10px; line-height: 10px; }\n"
    "#item { width: 40px; height: 10px; }\n"
    "#next { font-size: 10px; line-height: 10px; }\n"
)
_WIDE = (
    _BASE
    + "#card { container-type: inline-size; container-name: card; width: 200px; }\n"
    + "@container card (min-width: 150px) { #item { width: 80px; } }\n"
    + "@container other (min-width: 150px) { #item { width: 10px; } }\n"
    + "@container (min-width: 100px) { #card { width: 50px; } }\n"
)
_NARROW = _WIDE.replace("width: 200px;", "width: 100px;", 1)
_UNTYPED = (
    _BASE
    + "#card { container-name: card; width: 200px; }\n"
    + "@container card (min-width: 150px) { #item { width: 80px; } }\n"
)
_LATER = (
    _BASE
    + "#card { container-type: inline-size; width: 200px; }\n"
    + "@container (min-width: 150px) { #item { width: 80px; } }\n"
    + "#item { width: 30px; }\n"
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lay(layout, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(_PAGE, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _widths(placed: dict[str, object]) -> dict[str, object]:
    card = _box(placed.get("boxes"), "card")
    item = _box(placed.get("boxes"), "item")
    nxt = _box(placed.get("boxes"), "next")
    under = (
        card is not None
        and nxt is not None
        and nxt.get("y") == int(card.get("y") or 0) + int(card.get("border_height") or 0)
    )
    return {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "card": None if card is None else card.get("content_width"),
        "item": None if item is None else item.get("content_width"),
        "next_under_card": under,
    }


def main() -> int:
    observed: dict[str, object] = {}
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - missing layout is an unmet outcome
        print(json.dumps({"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}}))
        return 0
    observed["wide"] = _widths(_lay(layout_normal_flow, _WIDE))
    observed["narrow"] = _widths(_lay(layout_normal_flow, _NARROW))
    observed["untyped"] = _widths(_lay(layout_normal_flow, _UNTYPED))
    observed["later"] = _widths(_lay(layout_normal_flow, _LATER))
    wide = observed["wide"]
    narrow = observed["narrow"]
    untyped = observed["untyped"]
    later = observed["later"]
    passed = (
        isinstance(wide, dict)
        and wide.get("card") == 200
        and wide.get("item") == 80
        and wide.get("next_under_card") is True
        and isinstance(narrow, dict)
        and narrow.get("card") == 100
        and narrow.get("item") == 40
        and narrow.get("next_under_card") is True
        and isinstance(untyped, dict)
        and untyped.get("item") == 40
        and isinstance(later, dict)
        and later.get("item") == 30
        and later.get("card") == 200
    )
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
