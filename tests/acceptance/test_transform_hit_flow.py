"""Hit-test an in-flow box through its CSS transform.

A marginless page places a 40 by 40 subject at (0, 0), a 10 by 10 child in
that corner, and a 10px follower at y 40. ``rotate(90deg)`` around the
top-left corner leaves those border boxes in place. The child is hit at
(-5, 5), the subject at (-20, 20), and the old rectangle at (5, 5) falls
through to the page. ``translate(30px, 0px)`` hits (35, 10) and misses
(10, 10) without moving the follower. ``none`` keeps the untransformed hit.
An unparsable transform is invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = (
    '<div id="page"><div id="mover"><div id="inner"></div></div>'
    '<div id="next"></div></div>'
)
_RESET = "#page, #mover, #inner, #next { margin: 0px; }\n"
_GEOM = "#mover { width: 40px; height: 40px; }\n#inner { width: 10px; height: 10px; }\n#next { height: 10px; }\n"


def _css(transform: str, origin: str = "0px 0px") -> str:
    return _RESET + _GEOM + f"#mover {{ transform: {transform}; transform-origin: {origin}; }}\n"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lay(layout, transform: str) -> dict[str, object]:
    try:
        placed = layout(_PAGE, _css(transform), viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _hit(find, transform: str, point: tuple[int, int]) -> dict[str, object]:
    try:
        found = find(_PAGE, _css(transform), point[0], point[1], viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised hit is an unmet outcome
        return {"outcome": "error", "id": None, "reason": f"{type(exc).__name__}: {exc}"}
    return found if isinstance(found, dict) else {"outcome": "error", "id": None, "reason": "hit is invalid"}


def _edge(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import element_from_document, layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: dict[str, bool] = {}
    for name, transform, points in (
        (
            "rotate",
            "rotate(90deg)",
            {"child": (-5, 5), "subject": (-20, 20), "old": (5, 5), "follow": (4, 44)},
        ),
        (
            "translate",
            "translate(30px, 0px)",
            {"moved": (50, 10), "old": (10, 10), "follow": (4, 44)},
        ),
        (
            "none",
            "none",
            {"inside": (20, 20), "outside": (-20, 20), "follow": (4, 44)},
        ),
    ):
        placed = _lay(layout_normal_flow, transform)
        hits = {label: _hit(element_from_document, transform, point) for label, point in points.items()}
        observed[name] = {
            "outcome": placed.get("outcome"),
            "reason": placed.get("reason"),
            "mover": _edge(_box(placed.get("boxes"), "mover")),
            "inner": _edge(_box(placed.get("boxes"), "inner")),
            "next": _edge(_box(placed.get("boxes"), "next")),
            "hits": {label: {"outcome": item.get("outcome"), "id": item.get("id")} for label, item in hits.items()},
        }

    broken = _lay(layout_normal_flow, "not-a-transform")
    broken_hit = _hit(element_from_document, "not-a-transform", (20, 20))
    observed["broken"] = {
        "layout": {"outcome": broken.get("outcome"), "reason": broken.get("reason")},
        "hit": {"outcome": broken_hit.get("outcome"), "id": broken_hit.get("id"), "reason": broken_hit.get("reason")},
    }

    def placed_still(name: str) -> bool:
        row = observed[name]
        return (
            isinstance(row, dict)
            and row.get("outcome") == "placed"
            and row.get("mover") == {"x": 0, "y": 0, "border_width": 40, "border_height": 40}
            and row.get("inner") == {"x": 0, "y": 0, "border_width": 10, "border_height": 10}
            and row.get("next") == {"x": 0, "y": 40, "border_width": 200, "border_height": 10}
        )

    def hit_id(name: str, label: str) -> object:
        row = observed[name]
        if not isinstance(row, dict):
            return None
        hits = row.get("hits")
        if not isinstance(hits, dict):
            return None
        item = hits.get(label)
        if not isinstance(item, dict) or item.get("outcome") != "hit":
            return None
        return item.get("id")

    checks["rotate_keeps_the_flow"] = placed_still("rotate")
    checks["rotate_hits_the_child_outside_the_rectangle"] = hit_id("rotate", "child") == "inner"
    checks["rotate_hits_the_subject_outside_the_rectangle"] = hit_id("rotate", "subject") == "mover"
    checks["rotate_misses_the_old_rectangle"] = hit_id("rotate", "old") == "page"
    checks["rotate_follower_stays_under_the_stack"] = hit_id("rotate", "follow") == "next"
    checks["translate_keeps_the_flow"] = placed_still("translate")
    checks["translate_hits_the_shifted_box"] = hit_id("translate", "moved") == "mover"
    checks["translate_misses_the_old_rectangle"] = hit_id("translate", "old") == "page"
    checks["translate_follower_stays_under_the_stack"] = hit_id("translate", "follow") == "next"
    checks["none_hits_the_layout_box"] = placed_still("none") and hit_id("none", "inside") == "mover"
    checks["none_misses_the_rotated_region"] = hit_id("none", "outside") is None
    checks["none_follower_stays_under_the_stack"] = hit_id("none", "follow") == "next"
    broken_row = observed["broken"]
    checks["unparsable_transform_is_invalid"] = (
        isinstance(broken_row, dict)
        and broken_row.get("layout") == {"outcome": "invalid", "reason": "transform is invalid"}
        and broken_row.get("hit") == {"outcome": "invalid", "id": None, "reason": "transform is invalid"}
    )
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
