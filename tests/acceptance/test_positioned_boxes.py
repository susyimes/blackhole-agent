"""Shift a relative block, place an absolute child, and pin a fixed box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still ignores positioned boxes exits 0 with
passed false.
"""

from __future__ import annotations

import json

_MARKUP = (
    '<div id="page"><div id="card"><p id="flow">Stay</p>'
    '<i id="badge"></i><b id="pin"></b></div><p id="next">After</p></div>'
)

_STYLESHEET = """
#card { position: relative; left: 10px; top: 20px; width: 100px; padding-top: 2px; padding-left: 6px; }
#flow, #next { font-size: 10px; line-height: 20px; }
#badge { position: absolute; top: 4px; left: 8px; width: 12px; height: 12px; }
#pin { position: fixed; top: 0px; left: 0px; width: 5px; height: 5px; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None, index: int) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list):
        return None
    lines = box["lines"]
    if index >= len(lines) or not isinstance(lines[index], dict):
        return None
    return lines[index]


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    try:
        placed = layout_normal_flow(_MARKUP, _STYLESHEET, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        placed = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    try:
        rejected = layout_normal_flow(
            '<div id="page"><i id="nope"></i></div>',
            "#nope { position: absolute; left: 0px; top: 0px; width: -1px; height: 12px; }",
            viewport_width=200,
        )
    except Exception as exc:  # noqa: BLE001 - a raised rejection is an unmet outcome
        rejected = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}

    boxes = placed.get("boxes") if isinstance(placed, dict) else None
    page = _box(boxes, "page")
    card = _box(boxes, "card")
    flow = _box(boxes, "flow")
    badge = _box(boxes, "badge")
    pin = _box(boxes, "pin")
    nxt = _box(boxes, "next")
    observed: dict[str, object] = {
        "outcome": placed.get("outcome") if isinstance(placed, dict) else None,
        "reason": placed.get("reason") if isinstance(placed, dict) else None,
        "page": page,
        "card": card,
        "flow": flow,
        "badge": badge,
        "pin": pin,
        "next": nxt,
        "rejected_outcome": rejected.get("outcome") if isinstance(rejected, dict) else None,
        "rejected_reason": rejected.get("reason") if isinstance(rejected, dict) else None,
    }
    checks = {
        "placed": placed.get("outcome") == "placed" if isinstance(placed, dict) else False,
        "page": _near(page, x=0, y=0, content_width=200, content_height=42),
        "card": _near(
            card,
            x=10,
            y=20,
            content_width=100,
            content_height=20,
            border_width=106,
            border_height=22,
        ),
        "flow": _near(flow, x=16, y=22, content_width=100, content_height=20),
        "stay": _near(_line(flow, 0), text="Stay", x=16, y=22, height=20, content_width=40),
        "badge": _near(badge, x=18, y=24, content_width=12, content_height=12),
        "pin": _near(pin, x=0, y=0, content_width=5, content_height=5),
        "next": _near(nxt, x=0, y=22, content_width=200, content_height=20),
        "after": _near(_line(nxt, 0), text="After", x=0, y=22, height=20, content_width=50),
        "negative_absolute_width": (
            isinstance(rejected, dict)
            and rejected.get("outcome") == "invalid"
            and rejected.get("boxes") is None
            and rejected.get("reason") == "size is invalid"
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
