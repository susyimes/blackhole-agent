"""Let a document pointer fall through the area outside a border-radius curve.

A marginless page places a 40 by 40 subject at (0, 0), a 10 by 10 child in
that corner, and a 10px follower at y 40. ``border-radius: 20px`` keeps those
rectangles. The child is hit at (1, 1), the page at the rounded-away corner
(39, 1), and the subject at (20, 20). ``20px / 10px`` keeps (12, 1) on the
ellipse and gives (10, 1) to the page. Overlapping ``40px 40px 0px 0px``
shrinks before the test, so (20, 1) stays on the subject. ``0px`` and a
missing radius keep the square corner. An unparsable radius is invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = (
    '<div id="page"><div id="round"><div id="chip"></div></div>'
    '<div id="next"></div></div>'
)
_RESET = "#page, #round, #chip, #next { margin: 0px; }\n"
_GEOM = "#round { width: 40px; height: 40px; }\n#chip { width: 10px; height: 10px; }\n#next { height: 10px; }\n"


def _css(radius: str | None) -> str:
    extra = "" if radius is None else f"#round {{ border-radius: {radius}; }}\n"
    return _RESET + _GEOM + extra


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lay(layout, radius: str | None) -> dict[str, object]:
    try:
        placed = layout(_PAGE, _css(radius), viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _hit(find, radius: str | None, point: tuple[int, int]) -> dict[str, object]:
    try:
        found = find(_PAGE, _css(radius), point[0], point[1], viewport_width=200)
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
    cases = (
        ("circle", "20px", {"child": (1, 1), "corner": (39, 1), "inside": (20, 20), "follow": (4, 44)}),
        ("square", None, {"corner": (39, 1), "follow": (4, 44)}),
        ("zero", "0px", {"corner": (39, 1)}),
        ("ellipse", "20px / 10px", {"inside": (12, 1), "outside": (10, 1), "child": (1, 1)}),
        ("overlap", "40px 40px 0px 0px", {"inside": (20, 1), "corner": (39, 1)}),
    )
    for name, radius, points in cases:
        placed = _lay(layout_normal_flow, radius)
        hits = {label: _hit(element_from_document, radius, point) for label, point in points.items()}
        observed[name] = {
            "outcome": placed.get("outcome"),
            "reason": placed.get("reason"),
            "round": _edge(_box(placed.get("boxes"), "round")),
            "chip": _edge(_box(placed.get("boxes"), "chip")),
            "next": _edge(_box(placed.get("boxes"), "next")),
            "hits": {label: {"outcome": item.get("outcome"), "id": item.get("id")} for label, item in hits.items()},
        }

    broken = _lay(layout_normal_flow, "not-a-radius")
    broken_hit = _hit(element_from_document, "not-a-radius", (20, 20))
    observed["broken"] = {
        "layout": {"outcome": broken.get("outcome"), "reason": broken.get("reason")},
        "hit": {"outcome": broken_hit.get("outcome"), "id": broken_hit.get("id"), "reason": broken_hit.get("reason")},
    }

    def placed_still(name: str) -> bool:
        row = observed[name]
        return (
            isinstance(row, dict)
            and row.get("outcome") == "placed"
            and row.get("round") == {"x": 0, "y": 0, "border_width": 40, "border_height": 40}
            and row.get("chip") == {"x": 0, "y": 0, "border_width": 10, "border_height": 10}
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

    checks["circle_keeps_the_flow"] = placed_still("circle")
    checks["circle_child_keeps_the_corner"] = hit_id("circle", "child") == "chip"
    checks["circle_corner_falls_through"] = hit_id("circle", "corner") == "page"
    checks["circle_center_stays_on_the_subject"] = hit_id("circle", "inside") == "round"
    checks["circle_follower_stays_under_the_stack"] = hit_id("circle", "follow") == "next"
    checks["square_corner_stays_on_the_subject"] = placed_still("square") and hit_id("square", "corner") == "round"
    checks["square_follower_stays_under_the_stack"] = hit_id("square", "follow") == "next"
    checks["zero_corner_stays_on_the_subject"] = placed_still("zero") and hit_id("zero", "corner") == "round"
    checks["ellipse_keeps_the_flow"] = placed_still("ellipse")
    checks["ellipse_interior_stays_selectable"] = hit_id("ellipse", "inside") == "round"
    checks["ellipse_outside_falls_through"] = hit_id("ellipse", "outside") == "page"
    checks["ellipse_child_keeps_the_corner"] = hit_id("ellipse", "child") == "chip"
    checks["overlap_keeps_the_flow"] = placed_still("overlap")
    checks["overlap_shrunk_interior_stays_selectable"] = hit_id("overlap", "inside") == "round"
    checks["overlap_corner_falls_through"] = hit_id("overlap", "corner") == "page"
    broken_row = observed["broken"]
    checks["unparsable_radius_is_invalid"] = (
        isinstance(broken_row, dict)
        and broken_row.get("layout") == {"outcome": "invalid", "reason": "border-radius is invalid"}
        and broken_row.get("hit") == {"outcome": "invalid", "id": None, "reason": "border-radius is invalid"}
    )
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
