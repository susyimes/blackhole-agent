"""Mixed font sizes on a horizontal block inside a vertical parent.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that rejects the mixed run reports passed false.
"""

from __future__ import annotations

import json

_RULES = "html, body, div, p { margin: 0px } #page { font-size: 10px; line-height: 10px } "
_AUTO = (
    "<div id='page'><div id='v'><div id='a'>A<span>B</span></div></div><p id='n'>Z</p></div>",
    _RULES + "#v { writing-mode: vertical-rl } #a { writing-mode: horizontal-tb } span { font-size: 20px }",
)
_WRAP = (
    "<div id='page'><div id='v'><div id='a'>A<span>B</span> C</div></div><p id='n'>Z</p></div>",
    _RULES
    + "#v { writing-mode: vertical-rl; width: 40px } "
    + "#a { writing-mode: horizontal-tb } span { font-size: 20px }",
)
_TALL = (
    "<div id='page'><div id='v'><div id='a'>A<span>B</span></div></div><p id='n'>Z</p></div>",
    _RULES
    + "#v { writing-mode: vertical-rl; height: 40px } "
    + "#a { writing-mode: horizontal-tb } span { font-size: 20px }",
)
_BESIDE = (
    "<div id='page'><div id='v'><div id='a'>A<span>B</span></div><div id='b'>EF</div></div><p id='n'>Z</p></div>",
    _RULES + "#v { writing-mode: vertical-rl } #a { writing-mode: horizontal-tb } span { font-size: 20px }",
)
_LEFT = (
    "<div id='page'><div id='v'><div id='a'>A<span>B</span></div></div><p id='n'>Z</p></div>",
    _RULES + "#v { writing-mode: vertical-lr } #a { writing-mode: horizontal-tb } span { font-size: 20px }",
)
_JUSTIFY = (
    "<div id='page'><div id='v'><div id='a'>A<span>B</span> C</div></div></div>",
    _RULES
    + "#v { writing-mode: vertical-rl; width: 80px } "
    + "#a { writing-mode: horizontal-tb; text-align: justify } span { font-size: 20px }",
)
_FLOAT = (
    "<div id='page'><div id='v'><div id='a'>A<span>B</span></div></div></div>",
    _RULES
    + "#v { writing-mode: vertical-rl } "
    + "#a { writing-mode: horizontal-tb; float: left } span { font-size: 20px }",
)
_NESTED = (
    "<div id='page'><div id='v'><div id='a'><div>AB</div></div></div></div>",
    _RULES + "#v { writing-mode: vertical-rl } #a { writing-mode: horizontal-tb }",
)

_AB_RUNS = [
    {"text": "A", "x": 0, "font_size": 10, "width": 10},
    {"text": "B", "x": 10, "font_size": 20, "width": 20},
]


def _place(layout, html: str, css: str) -> dict:
    try:
        result = layout(html, css, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a miss must still print JSON
        return {"outcome": "invalid", "reason": f"{type(exc).__name__}: {exc}"}
    return result if isinstance(result, dict) else {"outcome": "invalid", "reason": "layout is invalid"}


def _box(result: dict, name: str) -> dict | None:
    if result.get("outcome") != "placed":
        return None
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == name:
            return item
    return None


def _edges(box: dict | None) -> tuple | None:
    if box is None:
        return None
    return tuple(box.get(key) for key in ("x", "y", "border_width", "border_height"))


def _lines(box: dict | None) -> list | None:
    if box is None or not isinstance(box.get("lines"), list):
        return None
    lines = []
    for line in box["lines"]:
        if not isinstance(line, dict):
            return None
        runs = line.get("runs")
        recorded = None
        if isinstance(runs, list):
            recorded = [
                {
                    "text": run.get("text"),
                    "x": run.get("x"),
                    "font_size": run.get("font_size"),
                    "width": run.get("width"),
                }
                for run in runs
                if isinstance(run, dict)
            ]
        lines.append(
            {
                "text": line.get("text"),
                "x": line.get("x"),
                "y": line.get("y"),
                "content_width": line.get("content_width"),
                "height": line.get("height"),
                "runs": recorded,
            }
        )
    return lines


def observe() -> tuple[bool, dict]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    auto = _place(layout_normal_flow, *_AUTO)
    wrap = _place(layout_normal_flow, *_WRAP)
    tall = _place(layout_normal_flow, *_TALL)
    beside = _place(layout_normal_flow, *_BESIDE)
    left = _place(layout_normal_flow, *_LEFT)
    justify = _place(layout_normal_flow, *_JUSTIFY)
    floated = _place(layout_normal_flow, *_FLOAT)
    nested = _place(layout_normal_flow, *_NESTED)
    auto_box = _box(auto, "a")
    wrap_box = _box(wrap, "a")
    beside_a = _box(beside, "a")
    beside_b = _box(beside, "b")
    observed: dict[str, object] = {
        "auto": _edges(_box(auto, "v")),
        "auto_child": _edges(auto_box),
        "auto_lines": _lines(auto_box),
        "auto_next": None if _box(auto, "n") is None else _box(auto, "n").get("y"),
        "wrap": _edges(_box(wrap, "v")),
        "wrap_lines": _lines(wrap_box),
        "wrap_next": None if _box(wrap, "n") is None else _box(wrap, "n").get("y"),
        "tall": _edges(_box(tall, "v")),
        "tall_child": _edges(_box(tall, "a")),
        "tall_next": None if _box(tall, "n") is None else _box(tall, "n").get("y"),
        "beside": _edges(_box(beside, "v")),
        "beside_a": _edges(beside_a),
        "beside_b": _edges(beside_b),
        "beside_lines": _lines(beside_a),
        "beside_next": None if _box(beside, "n") is None else _box(beside, "n").get("y"),
        "left": _edges(_box(left, "a")),
        "left_next": None if _box(left, "n") is None else _box(left, "n").get("y"),
        "justify": justify.get("outcome"),
        "justify_reason": justify.get("reason"),
        "float": floated.get("outcome"),
        "nested": nested.get("outcome"),
        "nested_reason": nested.get("reason"),
    }
    beside_runs = [
        {"text": "A", "x": 10, "font_size": 10, "width": 10},
        {"text": "B", "x": 20, "font_size": 20, "width": 20},
    ]
    passed = (
        auto.get("outcome") == "placed"
        and observed["auto"] == (0, 0, 30, 15)
        and observed["auto_child"] == (0, 0, 30, 15)
        and observed["auto_lines"]
        == [
            {
                "text": "AB",
                "x": 0,
                "y": 0,
                "content_width": 30,
                "height": 15,
                "runs": _AB_RUNS,
            }
        ]
        and observed["auto_next"] == 15
        and wrap.get("outcome") == "placed"
        and observed["wrap"] == (0, 0, 40, 25)
        and observed["wrap_lines"]
        == [
            {
                "text": "AB",
                "x": 0,
                "y": 0,
                "content_width": 30,
                "height": 15,
                "runs": _AB_RUNS,
            },
            {
                "text": "C",
                "x": 0,
                "y": 15,
                "content_width": 10,
                "height": 10,
                "runs": [{"text": "C", "x": 0, "font_size": 10, "width": 10}],
            },
        ]
        and observed["wrap_next"] == 25
        and tall.get("outcome") == "placed"
        and observed["tall"] == (0, 0, 30, 40)
        and observed["tall_child"] == (0, 0, 30, 15)
        and observed["tall_next"] == 40
        and beside.get("outcome") == "placed"
        and observed["beside"] == (0, 0, 40, 20)
        and observed["beside_a"] == (10, 0, 30, 15)
        and observed["beside_b"] == (0, 0, 10, 20)
        and observed["beside_lines"]
        == [
            {
                "text": "AB",
                "x": 10,
                "y": 0,
                "content_width": 30,
                "height": 15,
                "runs": beside_runs,
            }
        ]
        and observed["beside_next"] == 20
        and left.get("outcome") == "placed"
        and observed["left"] == (0, 0, 30, 15)
        and observed["left_next"] == 15
        and justify.get("outcome") == "invalid"
        and justify.get("reason") == "justified mixed font is unsupported"
        and floated.get("outcome") == "invalid"
        and nested.get("outcome") == "invalid"
        and nested.get("reason") == "orthogonal nested block is unsupported"
    )
    return passed, observed


if __name__ == "__main__":
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
