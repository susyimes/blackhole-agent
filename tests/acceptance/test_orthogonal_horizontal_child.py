"""A horizontal-tb block keeps horizontal lines inside a vertical parent."""

import json

from blackhole_agent.css_normal_flow import layout_normal_flow


PAGE = '<div id="page"><div id="v">{0}</div><p id="next">Z</p></div>'
BASE = "html, body, p, div {margin:0px} #page {font-size:10px;line-height:10px} "


def _placed(html, css):
    result = layout_normal_flow(html, css, viewport_width=120)
    if result["outcome"] != "placed":
        return None, result["reason"]
    return {item["id"]: item for item in result["boxes"]}, None


def _box(boxes, name):
    item = boxes[name]
    return tuple(item[key] for key in ("x", "y", "border_width", "border_height"))


def _line(boxes, name):
    return tuple(
        (line["text"], line["x"], line["y"], line["content_width"], line["height"])
        for line in boxes[name]["lines"]
    )


def observe():
    observed = {}
    passed = True

    def expect_invalid(name, html, css):
        nonlocal passed
        boxes, reason = _placed(html, css)
        observed[name] = "placed" if boxes is not None else reason
        passed = passed and boxes is None

    def expect(name, html, css, wanted):
        nonlocal passed
        boxes, reason = _placed(html, css)
        if boxes is None:
            observed[name] = reason
            passed = False
            return
        observed[name] = {
            "v": _box(boxes, "v"),
            "a": _box(boxes, "a") if "a" in boxes else None,
            "b": _box(boxes, "b") if "b" in boxes else None,
            "a_line": _line(boxes, "a") if "a" in boxes else None,
            "b_line": _line(boxes, "b") if "b" in boxes else None,
            "next_y": boxes["next"]["y"],
        }
        passed = passed and observed[name] == wanted

    horizontal = " #a {writing-mode:horizontal-tb} #b {writing-mode:horizontal-tb}"
    expect(
        "right",
        PAGE.format('<div id="a">AB</div><div id="b">CD</div>'),
        BASE + "#v {writing-mode:vertical-rl}" + horizontal,
        {
            "v": (0, 0, 40, 10),
            "a": (20, 0, 20, 10),
            "b": (0, 0, 20, 10),
            "a_line": (("AB", 20, 0, 20, 10),),
            "b_line": (("CD", 0, 0, 20, 10),),
            "next_y": 10,
        },
    )
    expect(
        "left",
        PAGE.format('<div id="a">AB</div><div id="b">CD</div>'),
        BASE + "#v {writing-mode:vertical-lr}" + horizontal,
        {
            "v": (0, 0, 40, 10),
            "a": (0, 0, 20, 10),
            "b": (20, 0, 20, 10),
            "a_line": (("AB", 0, 0, 20, 10),),
            "b_line": (("CD", 20, 0, 20, 10),),
            "next_y": 10,
        },
    )
    expect(
        "wrap",
        PAGE.format('<div id="a">AB CD</div>'),
        BASE + "#v {writing-mode:vertical-rl;width:20px} #a {writing-mode:horizontal-tb}",
        {
            "v": (0, 0, 20, 20),
            "a": (0, 0, 20, 20),
            "b": None,
            "a_line": (("AB", 0, 0, 20, 10), ("CD", 0, 10, 20, 10)),
            "b_line": None,
            "next_y": 20,
        },
    )
    expect(
        "short",
        PAGE.format('<div id="a">AB</div>'),
        BASE + "#v {writing-mode:vertical-rl;height:40px} #a {writing-mode:horizontal-tb}",
        {
            "v": (0, 0, 20, 40),
            "a": (0, 0, 20, 10),
            "b": None,
            "a_line": (("AB", 0, 0, 20, 10),),
            "b_line": None,
            "next_y": 40,
        },
    )
    expect(
        "beside",
        PAGE.format('<div id="a">AB</div><div id="b">EF</div>'),
        BASE + "#v {writing-mode:vertical-rl} #a {writing-mode:horizontal-tb}",
        {
            "v": (0, 0, 30, 20),
            "a": (10, 0, 20, 10),
            "b": (0, 0, 10, 20),
            "a_line": (("AB", 10, 0, 20, 10),),
            "b_line": (("EF", 0, 0, 10, 20),),
            "next_y": 20,
        },
    )
    expect_invalid(
        "float",
        PAGE.format('<div id="a">AB</div>'),
        BASE + "#v {writing-mode:vertical-rl} #a {writing-mode:horizontal-tb;float:left}",
    )
    expect_invalid(
        "margin",
        PAGE.format('<div id="a">AB</div>'),
        BASE + "#v {writing-mode:vertical-rl} #a {writing-mode:horizontal-tb;margin-top:10px}",
    )
    expect(
        "definite_pair",
        PAGE.format('<div id="a">AB</div><div id="b">CD</div>'),
        BASE + "#v {writing-mode:vertical-rl;width:20px}" + horizontal,
        {
            "v": (0, 0, 20, 10),
            "a": (0, 0, 20, 10),
            "b": (-20, 0, 20, 10),
            "a_line": (("AB", 0, 0, 20, 10),),
            "b_line": (("CD", -20, 0, 20, 10),),
            "next_y": 10,
        },
    )
    return passed, observed


if __name__ == "__main__":
    try:
        passed, observed = observe()
    except (KeyError, IndexError, TypeError, ValueError) as error:
        passed, observed = False, {"geometry_error": f"{type(error).__name__}: {error}"}
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))
