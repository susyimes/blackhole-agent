"""Place normal-flow items from grid-template-areas and bracketed line names.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A grid that still rejects names still exits 0.
"""

from __future__ import annotations

import json

_AREAS = """
<div id="page">
  <div id="grid">
    <div id="main"></div>
    <div id="side"></div>
    <div id="head"></div>
  </div>
  <div id="after"></div>
</div>
"""

_AREA_STYLE = """
#page { width: 200px; }
#grid {
  display: grid;
  width: 120px;
  grid-template-columns: 40px 80px;
  grid-template-rows: 10px 20px;
  grid-template-areas: "head head" "side main";
}
#head { grid-area: head; }
#side { grid-area: side; }
#main { grid-area: main; }
#after { height: 8px; }
"""

_NAMED = """
<div id="page">
  <div id="grid">
    <div id="right"></div>
    <div id="left"></div>
  </div>
  <div id="after"></div>
</div>
"""

_NAMED_STYLE = """
#page { width: 200px; }
#grid {
  display: grid;
  width: 90px;
  grid-template-columns: [side-start] 30px [side-end main-start] 60px [main-end];
  grid-template-rows: 12px;
}
#left { grid-column: side-start / side-end; grid-row: 1; }
#right { grid-column: main-start / main-end; grid-row: 1; }
#after { height: 8px; }
"""

_BENT = """
<div id="page">
  <div id="grid"><div id="a"></div></div>
</div>
"""

_BENT_STYLE = """
#page { width: 200px; }
#grid {
  display: grid;
  width: 20px;
  grid-template-columns: 10px 10px;
  grid-template-rows: 10px 10px;
  grid-template-areas: "a a" "a b";
}
#a { grid-area: a; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _near(box: dict[str, object] | None, **expected: int) -> bool:
    if box is None:
        return False
    return all(box.get(key) == value for key, value in expected.items())


def _lay(markup: str, stylesheet: str) -> dict[str, object]:
    from blackhole_agent.css_normal_flow import layout_normal_flow

    placed = layout_normal_flow(markup, stylesheet, viewport_width=200)
    return placed if isinstance(placed, dict) else {"outcome": "invalid", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        areas = _lay(_AREAS, _AREA_STYLE)
        named = _lay(_NAMED, _NAMED_STYLE)
        bent = _lay(_BENT, _BENT_STYLE)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    area_boxes = areas.get("boxes")
    named_boxes = named.get("boxes")
    head = _box(area_boxes, "head")
    side = _box(area_boxes, "side")
    main = _box(area_boxes, "main")
    after = _box(area_boxes, "after")
    left = _box(named_boxes, "left")
    right = _box(named_boxes, "right")
    named_after = _box(named_boxes, "after")
    observed: dict[str, object] = {
        "areas_outcome": areas.get("outcome"),
        "areas_reason": areas.get("reason"),
        "head": head,
        "side": side,
        "main": main,
        "after": after,
        "named_outcome": named.get("outcome"),
        "named_reason": named.get("reason"),
        "left": left,
        "right": right,
        "named_after": named_after,
        "bent_outcome": bent.get("outcome"),
        "bent_reason": bent.get("reason"),
    }
    checks = {
        "areas_placed": areas.get("outcome") == "placed",
        "head": _near(head, x=0, y=0, content_width=120, content_height=10),
        "side": _near(side, x=0, y=10, content_width=40, content_height=20),
        "main": _near(main, x=40, y=10, content_width=80, content_height=20),
        "after": _near(after, x=0, y=30, content_height=8),
        "named_placed": named.get("outcome") == "placed",
        "left": _near(left, x=0, y=0, content_width=30, content_height=12),
        "right": _near(right, x=30, y=0, content_width=60, content_height=12),
        "named_after": _near(named_after, x=0, y=12, content_height=8),
        "bent": (
            bent.get("outcome") == "invalid"
            and bent.get("boxes") is None
            and "rectangle" in str(bent.get("reason") or "")
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
