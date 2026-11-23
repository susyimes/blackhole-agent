"""Balance a horizontal block when text-wrap says so.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A block that still paints the first-fit breaks reports
passed false.
"""

from __future__ import annotations

import json

_WORDS = "AAAA BBBB CCCC DDDD"
_BALANCE = (
    f"<div id='page'>{_WORDS}</div><div id='next'>Z</div>",
    "#page { width: 140px; font-size: 10px; text-wrap: balance; } #next { font-size: 10px; }",
    400,
)
_STYLE = (
    f"<div id='page'>{_WORDS}</div><div id='next'>Z</div>",
    "#page { width: 140px; font-size: 10px; text-wrap-style: balance; } #next { font-size: 10px; }",
    400,
)
_WRAP = (
    f"<div id='page'>{_WORDS}</div><div id='next'>Z</div>",
    "#page { width: 140px; font-size: 10px; text-wrap: wrap; } #next { font-size: 10px; }",
    400,
)
_INHERIT = (
    "<div id='page'><div id='child'>AAAA BBBB CCCC DDDD</div>"
    "<div id='plain'>AAAA BBBB CCCC DDDD</div></div>",
    "#page { width: 200px; font-size: 10px; text-wrap: balance; } "
    "#child { width: 140px; } #plain { width: 140px; text-wrap: wrap; }",
    400,
)
_TEN = (
    "<div id='page'>" + " ".join(f"W{i:02d}" for i in range(28)) + "</div><div id='next'>Z</div>",
    "#page { width: 110px; font-size: 10px; text-wrap: balance; } #next { font-size: 10px; }",
    400,
)
_ELEVEN = (
    "<div id='page'>" + " ".join(f"W{i:02d}" for i in range(31)) + "</div><div id='next'>Z</div>",
    "#page { width: 110px; font-size: 10px; text-wrap: balance; } #next { font-size: 10px; }",
    400,
)
_PRETTY = (
    "<div id='page'>AB</div>",
    "#page { width: 40px; font-size: 10px; text-wrap: pretty; }",
    80,
)
_INLINE = (
    "<div id='page'>AA<span>BB</span></div>",
    "#page { width: 80px; font-size: 10px; } span { text-wrap: balance; }",
    80,
)
_FLOAT = (
    "<div id='host'><div id='float'>ZZ</div>AAAA BBBB CCCC DDDD</div>",
    "#host { width: 140px; font-size: 10px; text-wrap: balance; } #float { float: left; }",
    400,
)


def _place(function, markup: str, stylesheet: str, viewport_width: int) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=viewport_width)
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
    return [item for item in box["lines"] if isinstance(item, dict)]


def _pack(line: dict[str, object] | None) -> dict[str, object] | None:
    if line is None:
        return None
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "width": line.get("content_width"),
    }


def _balanced(lines: list[dict[str, object]]) -> bool:
    return (
        len(lines) == 2
        and lines[0].get("text") == "AAAA BBBB"
        and lines[0].get("x") == 0
        and lines[0].get("y") == 0
        and lines[0].get("content_width") == 90
        and lines[1].get("text") == "CCCC DDDD"
        and lines[1].get("x") == 0
        and lines[1].get("y") == 10
        and lines[1].get("content_width") == 90
    )


def _first_fit(lines: list[dict[str, object]], *, y: int) -> bool:
    return (
        len(lines) == 2
        and lines[0].get("text") == "AAAA BBBB CCCC"
        and lines[0].get("x") == 0
        and lines[0].get("y") == y
        and lines[0].get("content_width") == 140
        and lines[1].get("text") == "DDDD"
        and lines[1].get("x") == 0
        and lines[1].get("y") == y + 10
        and lines[1].get("content_width") == 40
    )


def _ends(lines: list[dict[str, object]]) -> dict[str, object]:
    if not lines:
        return {"count": 0, "first": None, "last": None}
    return {"count": len(lines), "first": _pack(lines[0]), "last": _pack(lines[-1])}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    balance = _place(layout_normal_flow, *_BALANCE)
    style = _place(layout_normal_flow, *_STYLE)
    wrap = _place(layout_normal_flow, *_WRAP)
    inherited = _place(layout_normal_flow, *_INHERIT)
    ten = _place(layout_normal_flow, *_TEN)
    eleven = _place(layout_normal_flow, *_ELEVEN)
    pretty = _place(layout_normal_flow, *_PRETTY)
    inline = _place(layout_normal_flow, *_INLINE)
    floated = _place(layout_normal_flow, *_FLOAT)
    balance_lines = _lines(_box(balance, "page"))
    style_lines = _lines(_box(style, "page"))
    wrap_lines = _lines(_box(wrap, "page"))
    child_lines = _lines(_box(inherited, "child"))
    plain_lines = _lines(_box(inherited, "plain"))
    ten_lines = _lines(_box(ten, "page"))
    eleven_lines = _lines(_box(eleven, "page"))
    observed: dict[str, object] = {
        "balance": [_pack(line) for line in balance_lines],
        "balance_next_y": None if _box(balance, "next") is None else _box(balance, "next").get("y"),
        "style": [_pack(line) for line in style_lines],
        "wrap": [_pack(line) for line in wrap_lines],
        "child": [_pack(line) for line in child_lines],
        "plain": [_pack(line) for line in plain_lines],
        "ten": _ends(ten_lines),
        "ten_next_y": None if _box(ten, "next") is None else _box(ten, "next").get("y"),
        "eleven": _ends(eleven_lines),
        "eleven_next_y": None if _box(eleven, "next") is None else _box(eleven, "next").get("y"),
        "pretty": pretty.get("outcome"),
        "pretty_reason": pretty.get("reason"),
        "inline": inline.get("outcome"),
        "inline_reason": inline.get("reason"),
        "float": floated.get("outcome"),
        "float_reason": floated.get("reason"),
    }
    passed = (
        balance.get("outcome") == "placed"
        and _balanced(balance_lines)
        and observed["balance_next_y"] == 20
        and style.get("outcome") == "placed"
        and _balanced(style_lines)
        and wrap.get("outcome") == "placed"
        and _first_fit(wrap_lines, y=0)
        and inherited.get("outcome") == "placed"
        and _balanced(child_lines)
        and _first_fit(plain_lines, y=20)
        and ten.get("outcome") == "placed"
        and len(ten_lines) == 10
        and ten_lines[0].get("text") == "W00 W01"
        and ten_lines[0].get("y") == 0
        and ten_lines[0].get("content_width") == 70
        and ten_lines[-1].get("text") == "W25 W26 W27"
        and observed["ten_next_y"] == 100
        and eleven.get("outcome") == "placed"
        and len(eleven_lines) == 11
        and eleven_lines[0].get("text") == "W00 W01 W02"
        and eleven_lines[0].get("y") == 0
        and eleven_lines[0].get("content_width") == 110
        and eleven_lines[-1].get("text") == "W30"
        and observed["eleven_next_y"] == 110
        and pretty.get("outcome") == "invalid"
        and pretty.get("reason") == "text-wrap is invalid"
        and inline.get("outcome") == "invalid"
        and inline.get("reason") == "inline text-wrap is unsupported"
        and floated.get("outcome") == "invalid"
        and floated.get("reason") == "balanced text wrap is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
