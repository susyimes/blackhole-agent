"""Hit-test a laid-out document from front to back.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without element_from_document exits 0 with passed false.
"""

from __future__ import annotations

import json

_FLOAT = (
    '<div id="page"><div id="pin"></div><div id="copy"></div></div>',
    "#pin { float: left; width: 50px; height: 40px; } #copy { width: 80px; height: 40px; }",
)
_RAISED = (
    '<div id="page"><div id="raised"></div><div id="cover"></div></div>',
    "#page { width: 100px; height: 100px; } "
    "#raised, #cover { position: absolute; top: 0px; left: 0px; width: 40px; height: 40px; } "
    "#raised { z-index: 1; }",
)
_BEHIND = (
    '<div id="page"><div id="parent"><div id="behind"></div></div></div>',
    "#page { width: 100px; height: 100px; } "
    "#parent { position: relative; width: 80px; height: 80px; } "
    "#behind { position: absolute; z-index: -1; top: 0px; left: 0px; width: 80px; height: 80px; }",
)
_GHOST = (
    '<div id="page"><div id="under"></div><div id="ghost"></div></div>',
    "#page { width: 100px; height: 100px; } "
    "#under, #ghost { position: absolute; top: 0px; left: 0px; width: 30px; height: 30px; } "
    "#ghost { z-index: 1; pointer-events: none; }",
)
_HIDDEN = (
    '<div id="page"><div id="under"></div><div id="shade"></div></div>',
    "#page { width: 100px; height: 100px; } "
    "#under, #shade { position: absolute; top: 0px; left: 0px; width: 30px; height: 30px; } "
    "#shade { z-index: 1; visibility: hidden; }",
)
_BAD = (
    '<div id="page"><div id="bad"></div></div>',
    "#bad { position: absolute; z-index: middle; top: 0px; left: 0px; width: 10px; height: 10px; }",
)


def _hit(function, markup: str, stylesheet: str, x: int, y: int) -> dict[str, object]:
    try:
        found = function(
            markup,
            stylesheet,
            x,
            y,
            viewport_width=200,
        )
    except Exception as exc:  # noqa: BLE001 - a raised hit is an unmet outcome
        return {"outcome": "error", "id": None, "reason": f"{type(exc).__name__}: {exc}"}
    if not isinstance(found, dict):
        return {"outcome": "error", "id": None, "reason": "result"}
    return found


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import element_from_document, layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the hit function still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    float_hit = _hit(element_from_document, *_FLOAT, 10, 10)
    raised_hit = _hit(element_from_document, *_RAISED, 10, 10)
    behind_hit = _hit(element_from_document, *_BEHIND, 10, 10)
    ghost_hit = _hit(element_from_document, *_GHOST, 10, 10)
    hidden_hit = _hit(element_from_document, *_HIDDEN, 10, 10)
    missed = _hit(element_from_document, *_FLOAT, 10, 90)
    invalid = _hit(element_from_document, *_BAD, 4, 4)
    try:
        placed = layout_normal_flow(_BAD[0], _BAD[1], viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        placed = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    boxes = placed.get("boxes") if isinstance(placed, dict) else None
    bad_box = None
    if isinstance(boxes, list):
        for item in boxes:
            if isinstance(item, dict) and item.get("id") == "bad":
                bad_box = item
                break
    observed: dict[str, object] = {
        "float": float_hit,
        "raised": raised_hit,
        "behind": behind_hit,
        "ghost": ghost_hit,
        "hidden": hidden_hit,
        "miss": missed,
        "invalid": invalid,
        "layout_outcome": placed.get("outcome") if isinstance(placed, dict) else None,
        "bad_box": bad_box,
    }
    passed = (
        float_hit.get("outcome") == "hit"
        and float_hit.get("id") == "pin"
        and raised_hit.get("outcome") == "hit"
        and raised_hit.get("id") == "raised"
        and behind_hit.get("outcome") == "hit"
        and behind_hit.get("id") == "parent"
        and ghost_hit.get("outcome") == "hit"
        and ghost_hit.get("id") == "under"
        and hidden_hit.get("outcome") == "hit"
        and hidden_hit.get("id") == "under"
        and missed.get("outcome") == "miss"
        and missed.get("id") is None
        and invalid.get("outcome") == "invalid"
        and invalid.get("id") is None
        and invalid.get("reason") == "z-index is invalid"
        and isinstance(placed, dict)
        and placed.get("outcome") == "placed"
        and isinstance(bad_box, dict)
        and bad_box.get("x") == 0
        and bad_box.get("y") == 0
        and bad_box.get("border_width") == 10
        and bad_box.get("border_height") == 10
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
