"""Hit-test the element a formatting context placed under a point.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects flex, grid, or table boxes exits
0 with passed false.
"""

from __future__ import annotations

import json

_BETWEEN = (
    '<div id="page"><div id="row"><span id="a"></span><span id="b"></span></div></div>',
    "#page { font-size: 10px; line-height: 10px; }"
    "#row { display: flex; width: 100px; justify-content: space-between; }"
    "#a, #b { flex: none; width: 20px; height: 10px; }",
)
_INLINE = (
    '<div id="page"><p id="row">A<span id="atom"><span id="grow"></span>'
    '<span id="more"></span></span>C</p></div>',
    "#page, #row { font-size: 10px; line-height: 10px; }"
    "#atom { display: inline-flex; width: 30px; height: 10px; }"
    "#grow { flex: 1; } #more { flex: 2; }",
)
_GRID = (
    '<div id="page"><div id="grid"><div id="a">A</div><div id="b">B</div></div></div>',
    "#page { font-size: 10px; }"
    "#grid { display: grid; width: 40px; grid-template-columns: 20px 20px; grid-auto-rows: 10px; }",
)
_TABLE = (
    '<div id="page"><div id="table"><div id="row"><div id="a">AA</div>'
    '<div id="b">BBB</div></div></div></div>',
    "#page { font-size: 10px; line-height: 10px; }"
    "#table { display: table; } #row { display: table-row; } #a, #b { display: table-cell; }",
)
_COVER = (
    '<div id="page"><div id="row"><span id="item"></span></div><div id="cover"></div></div>',
    "#page { font-size: 10px; line-height: 10px; }"
    "#row { display: flex; width: 40px; height: 40px; }"
    "#item { flex: 1; height: 40px; }"
    "#cover { position: absolute; z-index: 1; top: 0px; left: 0px; width: 20px; height: 20px; }",
)


def _hit(function, markup: str, stylesheet: str, x: int, y: int) -> dict[str, object]:
    try:
        found = function(markup, stylesheet, x, y, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised hit is an unmet outcome
        return {"outcome": "error", "id": None, "reason": f"{type(exc).__name__}: {exc}"}
    if not isinstance(found, dict):
        return {"outcome": "error", "id": None, "reason": "result"}
    return found


def _same(found: dict[str, object], outcome: str, ident: str | None) -> bool:
    return found.get("outcome") == outcome and found.get("id") == ident


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import element_from_document
    except Exception as exc:  # noqa: BLE001 - baseline without the hit function still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    points = {
        "flex_item": (*_BETWEEN, 10, 5),
        "flex_gap": (*_BETWEEN, 50, 5),
        "flex_end": (*_BETWEEN, 90, 5),
        "flex_right_edge": (*_BETWEEN, 20, 5),
        "flex_miss": (*_BETWEEN, 5, 40),
        "word": (*_INLINE, 5, 5),
        "inline_grow": (*_INLINE, 15, 5),
        "inline_more": (*_INLINE, 25, 5),
        "grid_a": (*_GRID, 5, 5),
        "grid_b": (*_GRID, 25, 5),
        "cell_a": (*_TABLE, 5, 5),
        "cell_b": (*_TABLE, 25, 5),
        "cover": (*_COVER, 5, 5),
        "item_beside_cover": (*_COVER, 30, 5),
    }
    observed = {
        name: _hit(element_from_document, markup, stylesheet, x, y)
        for name, (markup, stylesheet, x, y) in points.items()
    }
    passed = (
        _same(observed["flex_item"], "hit", "a")
        and _same(observed["flex_gap"], "hit", "row")
        and _same(observed["flex_end"], "hit", "b")
        and _same(observed["flex_right_edge"], "hit", "row")
        and _same(observed["flex_miss"], "miss", None)
        and _same(observed["word"], "hit", "row")
        and _same(observed["inline_grow"], "hit", "grow")
        and _same(observed["inline_more"], "hit", "more")
        and _same(observed["grid_a"], "hit", "a")
        and _same(observed["grid_b"], "hit", "b")
        and _same(observed["cell_a"], "hit", "a")
        and _same(observed["cell_b"], "hit", "b")
        and _same(observed["cover"], "hit", "cover")
        and _same(observed["item_beside_cover"], "hit", "item")
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
