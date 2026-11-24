"""Case text before wrapping so a German eszett can move the next word.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still paints the source characters reports
passed false.
"""

from __future__ import annotations

import json

_RULES = "font-size: 10px; line-height: 10px; "
_UPPER = (
    "<div id='p'>aß aß</div><div id='n'>Z</div>",
    f"#p {{ width: 50px; {_RULES}text-transform: uppercase; }} #n {{ height: 10px; {_RULES}}}",
)
_SOURCE = (
    "<div id='p'>aß aß</div><div id='n'>Z</div>",
    f"#p {{ width: 50px; {_RULES}}} #n {{ height: 10px; {_RULES}}}",
)
_LOWER = (
    "<div id='p'>AA</div>",
    f"#p {{ width: 80px; {_RULES}text-transform: lowercase; }}",
)
_CAP = (
    "<div id='p'>hello world</div>",
    f"#p {{ width: 200px; {_RULES}text-transform: capitalize; }}",
)
_INHERIT = (
    "<div id='p'><div id='c'>ß</div></div>",
    f"#p {{ width: 80px; {_RULES}text-transform: uppercase; }}",
)
_RESET = (
    "<div id='p'><div id='c'>ß</div></div>",
    f"#p {{ width: 80px; {_RULES}text-transform: uppercase; }} #c {{ text-transform: none; }}",
)
_SPAN = (
    "<div id='p'>a<span>ß</span>b</div>",
    f"#p {{ width: 80px; {_RULES}text-transform: uppercase; }}",
)


def _place(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(result, dict):
        return {"outcome": "error", "reason": "result", "boxes": None}
    return result


def _box(result: dict[str, object], box_id: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == box_id:
            return item
    return None


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    return [
        {
            "text": item.get("text"),
            "x": item.get("x"),
            "y": item.get("y"),
            "width": item.get("content_width"),
        }
        for item in box["lines"]
        if isinstance(item, dict)
    ]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    upper = _place(layout_normal_flow, *_UPPER)
    source = _place(layout_normal_flow, *_SOURCE)
    lower = _place(layout_normal_flow, *_LOWER)
    capital = _place(layout_normal_flow, *_CAP)
    inherited = _place(layout_normal_flow, *_INHERIT)
    reset = _place(layout_normal_flow, *_RESET)
    span = _place(layout_normal_flow, *_SPAN)
    vertical = _place(
        layout_normal_flow,
        "<div id='p'>ab</div>",
        f"#p {{ writing-mode: vertical-rl; height: 40px; {_RULES}text-transform: uppercase; }}",
    )
    inline = _place(
        layout_normal_flow,
        "<div id='p'>a<span>b</span></div>",
        f"#p {{ width: 80px; {_RULES}}} span {{ text-transform: uppercase; }}",
    )
    flexed = _place(
        layout_normal_flow,
        "<div id='p'><div>aa</div></div>",
        f"#p {{ display: flex; width: 80px; {_RULES}text-transform: uppercase; }}",
    )
    rtl = _place(
        layout_normal_flow,
        "<div id='p'>ab</div>",
        f"#p {{ direction: rtl; width: 40px; {_RULES}text-transform: uppercase; }}",
    )
    observed: dict[str, object] = {
        "upper": _lines(_box(upper, "p")),
        "next": None if _box(upper, "n") is None else _box(upper, "n").get("y"),
        "source": _lines(_box(source, "p")),
        "source_next": None if _box(source, "n") is None else _box(source, "n").get("y"),
        "lower": _lines(_box(lower, "p")),
        "capitalize": _lines(_box(capital, "p")),
        "inherit": _lines(_box(inherited, "c")),
        "reset": _lines(_box(reset, "c")),
        "span": _lines(_box(span, "p")),
        "vertical": vertical.get("outcome"),
        "vertical_reason": vertical.get("reason"),
        "inline": inline.get("outcome"),
        "inline_reason": inline.get("reason"),
        "flex": flexed.get("outcome"),
        "flex_reason": flexed.get("reason"),
        "rtl": rtl.get("outcome"),
        "rtl_reason": rtl.get("reason"),
    }
    passed = (
        upper.get("outcome") == "placed"
        and observed["upper"]
        == [
            {"text": "ASS", "x": 0, "y": 0, "width": 30},
            {"text": "ASS", "x": 0, "y": 10, "width": 30},
        ]
        and observed["next"] == 20
        and source.get("outcome") == "placed"
        and observed["source"] == [{"text": "aß aß", "x": 0, "y": 0, "width": 50}]
        and observed["source_next"] == 10
        and observed["lower"] == [{"text": "aa", "x": 0, "y": 0, "width": 20}]
        and observed["capitalize"] == [{"text": "Hello World", "x": 0, "y": 0, "width": 110}]
        and observed["inherit"] == [{"text": "SS", "x": 0, "y": 0, "width": 20}]
        and observed["reset"] == [{"text": "ß", "x": 0, "y": 0, "width": 10}]
        and observed["span"] == [{"text": "ASSB", "x": 0, "y": 0, "width": 40}]
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "text-transform is unsupported"
        and inline.get("outcome") == "invalid"
        and inline.get("reason") == "inline text-transform is unsupported"
        and flexed.get("outcome") == "invalid"
        and flexed.get("reason") == "text-transform is unsupported"
        and rtl.get("outcome") == "invalid"
        and rtl.get("reason") == "text-transform is unsupported"
    )
    return passed, observed


if __name__ == "__main__":
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
