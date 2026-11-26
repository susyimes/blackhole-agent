"""Lengthen a one-word last line when text-wrap is pretty.

Earlier lines stay on the first-fit breaks. Balance still rewrites the whole
block, and wrap still leaves the orphan. Prints JSON with boolean passed and
nonempty observed. Exit 0 for both a miss and a hit.
"""

from __future__ import annotations

import json

_FONT = "font-size: 10px; line-height: 10px; margin: 0px; "
_THREE = "AA BB CC DD EE FF GG"
_PRETTY = (
    f"<div id='page'>{_THREE}</div><div id='next'>Z</div>",
    f"#page {{ width: 80px; {_FONT}text-wrap: pretty; }} #next {{ {_FONT}}}",
    400,
)
_STYLE = (
    f"<div id='page'>{_THREE}</div><div id='next'>Z</div>",
    f"#page {{ width: 80px; {_FONT}text-wrap-style: pretty; }} #next {{ {_FONT}}}",
    400,
)
_WRAP = (
    f"<div id='page'>{_THREE}</div><div id='next'>Z</div>",
    f"#page {{ width: 80px; {_FONT}text-wrap: wrap; }} #next {{ {_FONT}}}",
    400,
)
_BALANCE = (
    f"<div id='page'>{_THREE}</div><div id='next'>Z</div>",
    f"#page {{ width: 80px; {_FONT}text-wrap: balance; }} #next {{ {_FONT}}}",
    400,
)
_WIDE = (
    "<div id='page'>AAAA BBBB CCCC DDDD</div><div id='next'>Z</div>",
    f"#page {{ width: 140px; {_FONT}text-wrap: pretty; }} #next {{ {_FONT}}}",
    400,
)
_LONG = " ".join(f"W{i:02d}" for i in range(31))
_ELEVEN = (
    f"<div id='page'>{_LONG}</div><div id='next'>Z</div>",
    f"#page {{ width: 110px; {_FONT}text-wrap: pretty; }} #next {{ {_FONT}}}",
    400,
)
_ELEVEN_BALANCE = (
    f"<div id='page'>{_LONG}</div><div id='next'>Z</div>",
    f"#page {{ width: 110px; {_FONT}text-wrap: balance; }} #next {{ {_FONT}}}",
    400,
)
_NARROW = (
    "<div id='page'>AA BB</div><div id='next'>Z</div>",
    f"#page {{ width: 30px; {_FONT}text-wrap: pretty; }} #next {{ {_FONT}}}",
    400,
)
_INHERIT = (
    f"<div id='page'><div id='child'>{_THREE}</div><div id='plain'>{_THREE}</div></div>",
    f"#page {{ width: 200px; {_FONT}text-wrap: pretty; }} "
    f"#child {{ width: 80px; }} #plain {{ width: 80px; text-wrap: wrap; }}",
    400,
)
_FLOAT = (
    "<div id='host'><div id='float'>ZZ</div>AA BB CC DD EE FF GG</div>",
    f"#host {{ width: 80px; {_FONT}text-wrap: pretty; }} #float {{ float: left; }}",
    400,
)
_INDENT = (
    "<div id='page'>AA BB CC DD</div>",
    f"#page {{ width: 80px; {_FONT}text-wrap: pretty; text-indent: 10px; }}",
    400,
)
_VERTICAL = (
    "<div id='page'>AA BB</div>",
    f"#page {{ writing-mode: vertical-rl; height: 40px; {_FONT}text-wrap: pretty; }}",
    400,
)
_INLINE = (
    "<div id='page'>AA<span>BB</span></div>",
    "#page { width: 80px; font-size: 10px; } span { text-wrap: pretty; }",
    80,
)
_STABLE = (
    "<div id='page'>AB</div>",
    "#page { width: 40px; font-size: 10px; text-wrap: stable; }",
    80,
)

_ORPHAN = (("AA BB CC", 0, 80), ("DD EE", 10, 50), ("FF GG", 20, 50))
_GREEDY = (("AA BB CC", 0, 80), ("DD EE FF", 10, 80), ("GG", 20, 20))
_EVEN = (("AA BB", 0, 50), ("CC DD", 10, 50), ("EE FF GG", 20, 80))


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


def _next_y(result: dict[str, object]) -> object:
    box = _box(result, "next")
    if box is None:
        return None
    return box.get("y")


def _matches(lines: list[dict[str, object]], expected: tuple[tuple[str, int, int], ...]) -> bool:
    if len(lines) != len(expected):
        return False
    for line, (text, y, width) in zip(lines, expected):
        if line.get("text") != text or line.get("x") != 0 or line.get("y") != y or line.get("content_width") != width:
            return False
    return True


def _rejected(result: dict[str, object], reason: str) -> bool:
    return result.get("outcome") == "invalid" and result.get("reason") == reason


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    pretty = _place(layout_normal_flow, *_PRETTY)
    style = _place(layout_normal_flow, *_STYLE)
    wrap = _place(layout_normal_flow, *_WRAP)
    balance = _place(layout_normal_flow, *_BALANCE)
    wide = _place(layout_normal_flow, *_WIDE)
    eleven = _place(layout_normal_flow, *_ELEVEN)
    eleven_balance = _place(layout_normal_flow, *_ELEVEN_BALANCE)
    narrow = _place(layout_normal_flow, *_NARROW)
    inherited = _place(layout_normal_flow, *_INHERIT)
    floated = _place(layout_normal_flow, *_FLOAT)
    indent = _place(layout_normal_flow, *_INDENT)
    vertical = _place(layout_normal_flow, *_VERTICAL)
    inline = _place(layout_normal_flow, *_INLINE)
    stable = _place(layout_normal_flow, *_STABLE)
    pretty_lines = _lines(_box(pretty, "page"))
    style_lines = _lines(_box(style, "page"))
    wrap_lines = _lines(_box(wrap, "page"))
    balance_lines = _lines(_box(balance, "page"))
    wide_lines = _lines(_box(wide, "page"))
    eleven_lines = _lines(_box(eleven, "page"))
    eleven_balance_lines = _lines(_box(eleven_balance, "page"))
    narrow_lines = _lines(_box(narrow, "page"))
    child_lines = _lines(_box(inherited, "child"))
    plain_lines = _lines(_box(inherited, "plain"))
    observed: dict[str, object] = {
        "pretty": [_pack(line) for line in pretty_lines],
        "pretty_next_y": _next_y(pretty),
        "pretty_outcome": pretty.get("outcome"),
        "pretty_reason": pretty.get("reason"),
        "style": [_pack(line) for line in style_lines],
        "wrap": [_pack(line) for line in wrap_lines],
        "wrap_next_y": _next_y(wrap),
        "balance": [_pack(line) for line in balance_lines],
        "balance_next_y": _next_y(balance),
        "wide": [_pack(line) for line in wide_lines],
        "wide_next_y": _next_y(wide),
        "eleven_count": len(eleven_lines),
        "eleven_first": _pack(eleven_lines[0]) if eleven_lines else None,
        "eleven_penultimate": _pack(eleven_lines[-2]) if len(eleven_lines) > 1 else None,
        "eleven_last": _pack(eleven_lines[-1]) if eleven_lines else None,
        "eleven_next_y": _next_y(eleven),
        "eleven_balance_last": _pack(eleven_balance_lines[-1]) if eleven_balance_lines else None,
        "eleven_balance_count": len(eleven_balance_lines),
        "narrow": [_pack(line) for line in narrow_lines],
        "narrow_next_y": _next_y(narrow),
        "child": [_pack(line) for line in child_lines],
        "plain": [_pack(line) for line in plain_lines],
        "plain_y": None if _box(inherited, "plain") is None else _box(inherited, "plain").get("y"),
        "float_reason": floated.get("reason"),
        "indent_reason": indent.get("reason"),
        "vertical_reason": vertical.get("reason"),
        "inline_reason": inline.get("reason"),
        "stable_reason": stable.get("reason"),
    }
    passed = (
        pretty.get("outcome") == "placed"
        and _matches(pretty_lines, _ORPHAN)
        and observed["pretty_next_y"] == 30
        and style.get("outcome") == "placed"
        and _matches(style_lines, _ORPHAN)
        and wrap.get("outcome") == "placed"
        and _matches(wrap_lines, _GREEDY)
        and observed["wrap_next_y"] == 30
        and balance.get("outcome") == "placed"
        and _matches(balance_lines, _EVEN)
        and observed["balance_next_y"] == 30
        and wide.get("outcome") == "placed"
        and _matches(wide_lines, (("AAAA BBBB", 0, 90), ("CCCC DDDD", 10, 90)))
        and observed["wide_next_y"] == 20
        and eleven.get("outcome") == "placed"
        and len(eleven_lines) == 11
        and eleven_lines[0].get("text") == "W00 W01 W02"
        and eleven_lines[0].get("y") == 0
        and eleven_lines[0].get("content_width") == 110
        and eleven_lines[-2].get("text") == "W27 W28"
        and eleven_lines[-2].get("y") == 90
        and eleven_lines[-2].get("content_width") == 70
        and eleven_lines[-1].get("text") == "W29 W30"
        and eleven_lines[-1].get("y") == 100
        and eleven_lines[-1].get("content_width") == 70
        and observed["eleven_next_y"] == 110
        and eleven_balance.get("outcome") == "placed"
        and len(eleven_balance_lines) == 11
        and eleven_balance_lines[-1].get("text") == "W30"
        and eleven_balance_lines[-1].get("content_width") == 30
        and narrow.get("outcome") == "placed"
        and _matches(narrow_lines, (("AA", 0, 20), ("BB", 10, 20)))
        and observed["narrow_next_y"] == 20
        and inherited.get("outcome") == "placed"
        and _matches(child_lines, _ORPHAN)
        and _matches(plain_lines, tuple((text, y + 30, width) for text, y, width in _GREEDY))
        and observed["plain_y"] == 30
        and _rejected(floated, "pretty text wrap is unsupported")
        and _rejected(indent, "pretty text wrap is unsupported")
        and _rejected(vertical, "pretty text wrap is unsupported")
        and _rejected(inline, "inline text-wrap is unsupported")
        and _rejected(stable, "text-wrap is invalid")
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
