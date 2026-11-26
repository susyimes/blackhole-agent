"""Paint a Hebrew or mixed line beside and below a physical float."""

import json

from blackhole_agent.css_normal_flow import layout_normal_flow

_PAGE = '<div id="page"><div id="line">{floated}{text}</div><div id="next">Z</div></div>'
_SIBLING = '<div id="page">{floated}<div id="line">{text}</div><div id="next">Z</div></div>'


def _case(text, width, *, float_height=20, side="left", extra="", page=_PAGE):
    floated = '<div id="flo"></div>' if float_height else ""
    width_rule = f"width: {width}px;" if width is not None else ""
    rules = (
        "#line, #next { font-size: 10px; line-height: 10px; } "
        f"#line {{ {width_rule} }} #flo {{ float: {side}; width: 20px; height: {float_height}px; }}"
    )
    result = layout_normal_flow(page.format(floated=floated, text=text), rules + extra, viewport_width=200)
    if result["outcome"] != "placed":
        return result["outcome"]
    boxes = {box["id"]: box for box in result["boxes"]}
    rows = boxes.get("line", {}).get("lines", [])
    fields = {"text", "x", "y", "height", "glyphs"}
    flo = boxes.get("flo")
    return {
        "lines": [{k: v for k, v in row.items() if k in fields} for row in rows],
        "flo": None if flo is None else [flo.get("x"), flo.get("y")],
        "next_y": boxes.get("next", {}).get("y"),
    }


def _line(text, x, y, visual=None):
    row = {"text": text, "x": x, "y": y, "height": 10}
    if visual is not None:
        row["glyphs"] = [{"ch": ch, "x": x + i * 10, "width": 10} for i, ch in enumerate(visual)]
    return row


def observe():
    rtl = "#line { direction: rtl; }"
    observed = {
        "beside": _case("אבגד", 60),
        "under": _case("aa אבגד", 50),
        "mixed": _case("a אב", 70, float_height=10),
        "justified": _case("aa אבגד bb", 110, float_height=0, extra="#line { text-align: justify; }"),
        "relative": _case('<span id="rel">אבגד</span>', 60, extra="#rel { position: relative; left: 4px; }"),
        "rtl": _case("אבגד", 60, extra=rtl),
        "rtl_short": _case("אב", 80, extra=rtl),
        "rtl_wrap": _case("אב אבגד", 80, float_height=10, extra=rtl),
        "rtl_right": _case("אבגד", 80, side="right", extra=rtl),
        "vertical": _case("אב", None, extra=rtl + "#line { writing-mode: vertical-rl; height: 80px; }"),
        "rtl_sibling": _case("אבגד", 80, extra=rtl, page=_SIBLING),
    }
    expected = {
        "beside": {"flo": [0, 0], "next_y": 20, "lines": [_line("אבגד", 20, 0, "דגבא")]},
        "under": {"flo": [0, 0], "next_y": 30, "lines": [_line("aa", 20, 0), _line("אבגד", 0, 20, "דגבא")]},
        "mixed": {"flo": [0, 0], "next_y": 10, "lines": [_line("a אב", 20, 0, "a בא")]},
        "justified": {"flo": None, "next_y": 10, "lines": [_line("aa אבגד bb", 0, 0)]},
        "relative": {"flo": [0, 0], "next_y": 20, "lines": [_line("אבגד", 20, 0)]},
        "rtl": {"flo": [140, 0], "next_y": 20, "lines": [_line("אבגד", 160, 0, "דגבא")]},
        "rtl_short": {"flo": [120, 0], "next_y": 20, "lines": [_line("אב", 180, 0, "בא")]},
        "rtl_wrap": {"flo": [120, 0], "next_y": 20, "lines": [_line("אב", 180, 0, "בא"), _line("אבגד", 160, 10, "דגבא")]},
        "rtl_right": {"flo": [180, 0], "next_y": 20, "lines": [_line("אבגד", 140, 0, "דגבא")]},
        "vertical": "invalid",
        "rtl_sibling": "invalid",
    }
    return observed == expected, observed


if __name__ == "__main__":
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
