"""Block children stack on a vertical parent's block axis."""

import json

from blackhole_agent.css_normal_flow import layout_normal_flow


PAGE = '<div id="page"><div id="v">{0}</div><p id="next">Z</p></div>'
BASE = (
    "html, body, p, div {margin:0px} #page {font-size:10px;line-height:10px} "
    "#v {writing-mode:vertical-rl}"
)


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

    pair, reason = _placed(
        PAGE.format('<div id="a">AB</div><div id="b">CD</div>'),
        BASE,
    )
    if pair is None:
        observed["pair"] = reason
        passed = False
    else:
        observed["pair"] = {
            "v": _box(pair, "v"),
            "a": _box(pair, "a"),
            "b": _box(pair, "b"),
            "a_line": _line(pair, "a"),
            "b_line": _line(pair, "b"),
            "next_y": pair["next"]["y"],
        }
        passed = passed and observed["pair"] == {
            "v": (0, 0, 20, 20),
            "a": (10, 0, 10, 20),
            "b": (0, 0, 10, 20),
            "a_line": (("AB", 10, 0, 10, 20),),
            "b_line": (("CD", 0, 0, 10, 20),),
            "next_y": 20,
        }

    left, reason = _placed(
        PAGE.format('<div id="a">AB</div><div id="b">CD</div>'),
        BASE + " #v {writing-mode:vertical-lr}",
    )
    if left is None:
        observed["left"] = reason
        passed = False
    else:
        observed["left"] = {"a": _box(left, "a"), "b": _box(left, "b"), "next_y": left["next"]["y"]}
        passed = passed and observed["left"] == {
            "a": (0, 0, 10, 20),
            "b": (10, 0, 10, 20),
            "next_y": 20,
        }

    wrapped, reason = _placed(
        PAGE.format('<div id="a">AB CD</div>'),
        BASE + " #v {height:20px}",
    )
    if wrapped is None:
        observed["wrap"] = reason
        passed = False
    else:
        observed["wrap"] = {
            "v": _box(wrapped, "v"),
            "lines": _line(wrapped, "a"),
            "next_y": wrapped["next"]["y"],
        }
        passed = passed and observed["wrap"] == {
            "v": (0, 0, 20, 20),
            "lines": (("AB", 10, 0, 10, 20), ("CD", 0, 0, 10, 20)),
            "next_y": 20,
        }

    stretched, reason = _placed(
        PAGE.format('<div id="a">AB</div>'),
        BASE + " #v {height:40px}",
    )
    if stretched is None:
        observed["stretch"] = reason
        passed = False
    else:
        observed["stretch"] = {
            "a": _box(stretched, "a"),
            "content_height": stretched["a"]["content_height"],
            "line": _line(stretched, "a"),
            "next_y": stretched["next"]["y"],
        }
        passed = passed and observed["stretch"] == {
            "a": (0, 0, 10, 40),
            "content_height": 40,
            "line": (("AB", 0, 0, 10, 20),),
            "next_y": 40,
        }

    nested, reason = _placed(
        PAGE.format('<div id="a"><div id="b">AB</div></div>'),
        BASE,
    )
    if nested is None:
        observed["grandchild"] = reason
        passed = False
    else:
        observed["grandchild"] = {
            "v": _box(nested, "v"),
            "b_line": _line(nested, "b"),
            "next_y": nested["next"]["y"],
        }
        passed = passed and observed["grandchild"] == {
            "v": (0, 0, 10, 20),
            "b_line": (("AB", 0, 0, 10, 20),),
            "next_y": 20,
        }

    direct, reason = _placed(PAGE.format("AB"), BASE)
    if direct is None:
        observed["direct"] = reason
        passed = False
    else:
        observed["direct"] = {"v": _box(direct, "v"), "line": _line(direct, "v"), "next_y": direct["next"]["y"]}
        passed = passed and observed["direct"] == {
            "v": (0, 0, 10, 20),
            "line": (("AB", 0, 0, 10, 20),),
            "next_y": 20,
        }

    expect_invalid(
        "float",
        PAGE.format('<div id="a">AB</div>'),
        BASE + " #a {float:left}",
    )
    horizontal, reason = _placed(
        PAGE.format('<div id="a">AB</div>'),
        BASE + " #a {writing-mode:horizontal-tb}",
    )
    if horizontal is None:
        observed["horizontal"] = reason
        passed = False
    else:
        observed["horizontal"] = {
            "v": _box(horizontal, "v"),
            "a": _box(horizontal, "a"),
            "line": _line(horizontal, "a"),
            "next_y": horizontal["next"]["y"],
        }
        passed = passed and observed["horizontal"] == {
            "v": (0, 0, 20, 10),
            "a": (0, 0, 20, 10),
            "line": (("AB", 0, 0, 20, 10),),
            "next_y": 10,
        }
    expect_invalid(
        "margin",
        PAGE.format('<div id="a">AB</div>'),
        BASE + " #a {margin-top:10px}",
    )
    return passed, observed


if __name__ == "__main__":
    try:
        passed, observed = observe()
    except (KeyError, IndexError, TypeError, ValueError) as error:
        passed, observed = False, {"geometry_error": f"{type(error).__name__}: {error}"}
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))
