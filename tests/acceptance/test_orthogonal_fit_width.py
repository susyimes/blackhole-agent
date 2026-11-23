"""A definite vertical width shrinks each horizontal child to fit."""

import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from blackhole_agent import html5_document
from blackhole_agent.css_normal_flow import layout_normal_flow


PAGE = '<div id="page"><div id="v">{0}</div><p id="next">Z</p></div>'
BASE = "html, body, p, div {margin:0px} #page {font-size:10px;line-height:10px} "


def supply_html_parser():
    """Restore the baseline's genuine runtime data to a src-only replay archive."""
    package = html5_document._package_dir() / "html5lib"
    if (package / "__init__.py").is_file():
        return
    root = Path(html5_document.__file__).resolve().parents[2]
    if (root / ".git").exists() or not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise RuntimeError("the checkout is missing its absorbed HTML parser")
    checkout = next((item.parent for item in map(Path, sys.path) if (item.parent / ".git").exists()), None)
    if checkout is None:
        raise RuntimeError("the replay requires the installed project's Git object database")
    tree = "397395a7d05f3f55ebd5bcb029a66b55bac0306b"
    archive = subprocess.check_output(["git", "-C", str(checkout), "archive", "--format=zip", tree], timeout=30)
    with zipfile.ZipFile(io.BytesIO(archive)) as files:
        files.extractall(package)


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
    supply_html_parser()
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
            "a": _box(boxes, "a"),
            "b": _box(boxes, "b") if "b" in boxes else None,
            "a_line": _line(boxes, "a"),
            "b_line": _line(boxes, "b") if "b" in boxes else None,
            "next_y": boxes["next"]["y"],
        }
        passed = passed and observed[name] == wanted

    horizontal = " #a {writing-mode:horizontal-tb} #b {writing-mode:horizontal-tb}"
    expect(
        "inside",
        PAGE.format('<div id="a">AB</div><div id="b">EF</div>'),
        BASE + "#v {writing-mode:vertical-rl;width:50px} #a {writing-mode:horizontal-tb}",
        {
            "v": (0, 0, 50, 20),
            "a": (30, 0, 20, 10),
            "b": (20, 0, 10, 20),
            "a_line": (("AB", 30, 0, 20, 10),),
            "b_line": (("EF", 20, 0, 10, 20),),
            "next_y": 20,
        },
    )
    expect(
        "wide_pair",
        PAGE.format('<div id="a">AB</div><div id="b">CD</div>'),
        BASE + "#v {writing-mode:vertical-rl;width:50px}" + horizontal,
        {
            "v": (0, 0, 50, 10),
            "a": (30, 0, 20, 10),
            "b": (10, 0, 20, 10),
            "a_line": (("AB", 30, 0, 20, 10),),
            "b_line": (("CD", 10, 0, 20, 10),),
            "next_y": 10,
        },
    )
    expect(
        "overflow_right",
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
    expect(
        "overflow_left",
        PAGE.format('<div id="a">AB</div><div id="b">CD</div>'),
        BASE + "#v {writing-mode:vertical-lr;width:20px}" + horizontal,
        {
            "v": (0, 0, 20, 10),
            "a": (0, 0, 20, 10),
            "b": (20, 0, 20, 10),
            "a_line": (("AB", 0, 0, 20, 10),),
            "b_line": (("CD", 20, 0, 20, 10),),
            "next_y": 10,
        },
    )
    expect(
        "short",
        PAGE.format('<div id="a">AB</div>'),
        BASE + "#v {writing-mode:vertical-rl;width:50px} #a {writing-mode:horizontal-tb}",
        {
            "v": (0, 0, 50, 10),
            "a": (30, 0, 20, 10),
            "b": None,
            "a_line": (("AB", 30, 0, 20, 10),),
            "b_line": None,
            "next_y": 10,
        },
    )
    expect(
        "unbreakable",
        PAGE.format('<div id="a">ABCDE</div>'),
        BASE + "#v {writing-mode:vertical-rl;width:20px} #a {writing-mode:horizontal-tb}",
        {
            "v": (0, 0, 20, 10),
            "a": (-30, 0, 50, 10),
            "b": None,
            "a_line": (("ABCDE", -30, 0, 50, 10),),
            "b_line": None,
            "next_y": 10,
        },
    )
    expect(
        "wrapped_sibling",
        PAGE.format('<div id="a">AB CD</div><div id="b">EF</div>'),
        BASE + "#v {writing-mode:vertical-rl;width:20px} #a {writing-mode:horizontal-tb}",
        {
            "v": (0, 0, 20, 20),
            "a": (0, 0, 20, 20),
            "b": (-10, 0, 10, 20),
            "a_line": (("AB", 0, 0, 20, 10), ("CD", 0, 10, 20, 10)),
            "b_line": (("EF", -10, 0, 10, 20),),
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
        "specified",
        PAGE.format('<div id="a">AB</div>'),
        BASE + "#v {writing-mode:vertical-rl;width:50px} #a {writing-mode:horizontal-tb;width:40px}",
        {
            "v": (0, 0, 50, 10),
            "a": (10, 0, 40, 10),
            "b": None,
            "a_line": (("AB", 10, 0, 20, 10),),
            "b_line": None,
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
