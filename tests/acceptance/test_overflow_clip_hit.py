"""Clip a document hit to an overflow scrollport's padding edge.

A marginless page places a port with a 10px border, an 80 by 20 content box,
and a child whose border box is 80 by 40 at (10, 10). The padding edge runs
from (10, 10) to (90, 30). The bottom border still covers (20, 35). The child
continues to y 50, past the port and past the following block that occupies
y 40 through y 48.

``hidden``, ``clip``, ``scroll``, and ``auto`` hit the child at (20, 15), the
port at (20, 35), and nothing at (20, 49). ``visible`` hits the child at all
three points. The following block stays at y 40 and takes (20, 42).

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><div id="port"><div id="child"></div></div><div id="next"></div></div>'
_RESET = "#page, #port, #child, #next { margin: 0px; }\n"
_GEOM = (
    "#port { width: 80px; height: 20px; border-width: 10px; border-style: solid; }\n"
    "#child { width: 80px; height: 40px; }\n"
    "#next { height: 8px; }\n"
)
_CLIPPING = ("hidden", "clip", "scroll", "auto")
_POINTS = {"inside": (20, 15), "border": (20, 35), "past": (20, 49), "follow": (20, 42)}


def _css(overflow: str) -> str:
    return _RESET + _GEOM + f"#port {{ overflow: {overflow}; }}\n"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lay(layout, overflow: str) -> dict[str, object]:
    try:
        placed = layout(_PAGE, _css(overflow), viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _hit(find, overflow: str, point: tuple[int, int]) -> dict[str, object]:
    try:
        found = find(_PAGE, _css(overflow), point[0], point[1], viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised hit is an unmet outcome
        return {"outcome": "error", "id": None, "reason": f"{type(exc).__name__}: {exc}"}
    return found if isinstance(found, dict) else {"outcome": "error", "id": None, "reason": "hit is invalid"}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import element_from_document, layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: dict[str, bool] = {}
    for overflow in (*_CLIPPING, "visible"):
        placed = _lay(layout_normal_flow, overflow)
        port = _box(placed.get("boxes"), "port")
        child = _box(placed.get("boxes"), "child")
        nxt = _box(placed.get("boxes"), "next")
        hits = {name: _hit(element_from_document, overflow, point) for name, point in _POINTS.items()}
        observed[overflow] = {
            "port": None if port is None else {"y": port.get("y"), "border_height": port.get("border_height")},
            "child": None
            if child is None
            else {"x": child.get("x"), "y": child.get("y"), "border_height": child.get("border_height")},
            "next": None if nxt is None else {"y": nxt.get("y"), "border_height": nxt.get("border_height")},
            "hits": {name: {"outcome": item.get("outcome"), "id": item.get("id")} for name, item in hits.items()},
        }
        clipped = overflow in _CLIPPING
        border_id = "port" if clipped else "child"
        past_miss = hits["past"].get("outcome") == "miss" and hits["past"].get("id") is None
        checks[f"{overflow}_geometry"] = (
            placed.get("outcome") == "placed"
            and port is not None
            and port.get("y") == 0
            and port.get("border_height") == 40
            and child is not None
            and child.get("x") == 10
            and child.get("y") == 10
            and child.get("border_height") == 40
            and nxt is not None
            and nxt.get("y") == 40
            and nxt.get("border_height") == 8
        )
        checks[f"{overflow}_inside"] = hits["inside"].get("outcome") == "hit" and hits["inside"].get("id") == "child"
        checks[f"{overflow}_border"] = hits["border"].get("outcome") == "hit" and hits["border"].get("id") == border_id
        checks[f"{overflow}_past"] = past_miss if clipped else (
            hits["past"].get("outcome") == "hit" and hits["past"].get("id") == "child"
        )
        checks[f"{overflow}_follow"] = hits["follow"].get("outcome") == "hit" and hits["follow"].get("id") == "next"
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
