"""A sticky child sticks after its sticky parent is stopped by the containing block.

The child keeps the parent's shift while the parent can still move. Once the
parent padding edge can no longer follow the viewport, the child still meets
the viewport top inset until that same padding edge stops the child. The
intro and the rest ride only with the parent. The following sibling stays
at its static position.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects nested sticky exits 0 with
passed false.
"""

from __future__ import annotations

import json

_MARKUP = (
    '<div id="page"><div id="section"><div id="intro"></div><div id="head">H</div>'
    '<div id="rest"></div></div><div id="after">A</div></div>'
)
_CSS = (
    "#page { height: 400px; margin: 0px; }\n"
    "#section { position: sticky; top: 0px; height: 200px; margin: 0px; }\n"
    "#intro { height: 100px; margin: 0px; }\n"
    "#head { position: sticky; top: 0px; height: 40px; margin: 0px; }\n"
    "#rest { height: 60px; margin: 0px; }\n"
    "#after { height: 20px; margin: 0px; }\n"
)
_SCROLLS = {
    0: {"section": 0, "intro": 0, "head": 100, "rest": 140, "after": 200},
    100: {"section": 100, "intro": 100, "head": 200, "rest": 240, "after": 200},
    320: {"section": 200, "intro": 200, "head": 320, "rest": 340, "after": 200},
    370: {"section": 200, "intro": 200, "head": 360, "rest": 340, "after": 200},
}


def _ys(result: dict[str, object]) -> dict[str, object]:
    found: dict[str, object] = {}
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return found
    for item in boxes:
        if not isinstance(item, dict):
            continue
        ident = item.get("id")
        if ident in {"section", "intro", "head", "rest", "after"}:
            found[str(ident)] = {
                "x": item.get("x"),
                "y": item.get("y"),
                "border_height": item.get("border_height"),
            }
    return found


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    passed = True
    for scroll, expect in _SCROLLS.items():
        try:
            result = layout_normal_flow(
                _MARKUP,
                _CSS,
                viewport_width=300,
                viewport_height=400,
                scroll_y=scroll,
            )
        except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            result = {"outcome": "error", "reason": "layout is invalid"}
        places = _ys(result)
        observed[str(scroll)] = {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "boxes": places,
        }
        if result.get("outcome") != "placed":
            passed = False
            continue
        for ident, y in expect.items():
            box = places.get(ident)
            height = {"section": 200, "intro": 100, "head": 40, "rest": 60, "after": 20}[ident]
            if not isinstance(box, dict) or box.get("x") != 0 or box.get("y") != y or box.get("border_height") != height:
                passed = False
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
