"""Physical rectangles in CSS pixels with a uniform 10px font and line height."""

import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import NamedTuple

from blackhole_agent import html5_document
from blackhole_agent.css_normal_flow import layout_normal_flow


class Case(NamedTuple):
    text: str
    css: str
    box: tuple
    lines: tuple  # (text, x, y, width, height) in document order
    next_y: int
    content: tuple | None = None
    parent: str = ""
    viewport_height: int | None = None


PAGE = '<div id="page"><div id="v">{}</div><p id="next">Z</p></div>'
BASE = 'html, body, p {margin:0px} #page {font-size:10px;line-height:10px} #v {writing-mode:vertical-rl}'
WRAPPED = (("AB", 10, 0, 10, 20), ("CD", 0, 0, 10, 20))
BOTTOM = (("AB", 0, 10, 10, 20),)
CASES = {
    "right_to_left": Case("AB CD", "height:20px", (0, 0, 20, 20), WRAPPED, 20),
    "left_to_right": Case("AB CD", "writing-mode:vertical-lr;height:20px", (0, 0, 20, 20),
                          (("AB", 0, 0, 10, 20), ("CD", 10, 0, 10, 20)), 20),
    "intrinsic": Case("AB", "", (0, 0, 10, 20), (("AB", 0, 0, 10, 20),), 20),
    "rtl": Case("AB", "direction:rtl;height:30px", (0, 0, 10, 30), BOTTOM, 30),
    "sideways": Case("AB", "writing-mode:sideways-lr;height:30px", (0, 0, 10, 30), BOTTOM, 30),
    # CSS Writing Modes 4 §5.1 specifies a used direction of ltr for upright.
    "upright": Case("AB", "direction:rtl;text-orientation:upright;height:30px", (0, 0, 10, 30),
                    (("AB", 0, 0, 10, 20),), 30),
    "percentage": Case("AB CD", "height:50%", (0, 0, 20, 40), WRAPPED, 40, parent="height:80px"),
    "viewport_percentage": Case("AB CD EF", "height:50%;padding:3px", (0, 0, 36, 36),
                                (("AB", 23, 3, 10, 20), ("CD", 13, 3, 10, 20), ("EF", 3, 3, 10, 20)),
                                36, content=(30, 30), viewport_height=60),
    "border_box": Case("AB CD", "inline-size:50%;block-size:50%;box-sizing:border-box;padding-inline:3px;"
                       "padding-block:4px;border-width:2px;border-style:solid;margin:0px auto 6px",
                       (30, 0, 60, 30), (("AB", 74, 5, 10, 20), ("CD", 64, 5, 10, 20)), 36,
                       content=(48, 20), parent="height:60px"),
    "content_box": Case("AB CD", "inline-size:20px;padding:3px 7px 1px 2px;border-width:1px;"
                        "border-style:solid;margin-left:4px;margin-bottom:5px",
                        (12, 6, 31, 26), (("AB", 25, 10, 10, 20), ("CD", 15, 10, 10, 20)), 37,
                        content=(20, 20), parent="width:100px;padding-left:8px;padding-top:6px"),
    "ideographs": Case("天地玄黃", "", (0, 0, 20, 30), (("天地玄", 10, 0, 10, 30), ("黃", 0, 0, 10, 10)),
                       30, viewport_height=30),
    "preformatted": Case("AB\nC", "white-space:pre;text-align:end", (0, 0, 20, 20),
                         (("AB", 10, 0, 10, 20), ("C", 0, 10, 10, 10)), 20),
    "size_limits": Case("AB CD", "max-inline-size:20px;min-block-size:30px;padding-inline:2px",
                        (0, 0, 30, 24), (("AB", 20, 2, 10, 20), ("CD", 10, 2, 10, 20)), 24,
                        content=(30, 20)),
    "horizontal": Case("AB", "writing-mode:horizontal-tb", (0, 0, 120, 10), (("AB", 0, 0, 20, 10),), 10),
}


def supply_html_parser():
    """Restore the baseline's genuine runtime data to a src-only replay archive."""
    package = html5_document._package_dir() / "html5lib"
    if (package / "__init__.py").is_file():
        return
    root = Path(html5_document.__file__).resolve().parents[2]
    if (root / ".git").exists() or not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise RuntimeError("the checkout is missing its absorbed HTML parser")
    checkout = next((p.parent for p in map(Path, sys.path) if (p.parent / ".git").exists()), None)
    if checkout is None:
        raise RuntimeError("the replay requires the installed project's Git object database")
    # Git tree of capabilities/absorbed/html5lib/html5lib-1.1/html5lib at mission genesis.
    tree = "397395a7d05f3f55ebd5bcb029a66b55bac0306b"
    archive = subprocess.check_output(["git", "-C", str(checkout), "archive", "--format=zip", tree], timeout=30)
    with zipfile.ZipFile(io.BytesIO(archive)) as files:
        files.extractall(package)


def observe():
    supply_html_parser()
    observed = {}
    passed = True
    for name, case in CASES.items():
        css = BASE + f"#page {{{case.parent}}} #v {{{case.css}}}"
        result = layout_normal_flow(PAGE.format(case.text), css, viewport_width=120, viewport_height=case.viewport_height)
        if result["outcome"] != "placed":
            passed = False
            observed[name] = result["reason"]
            continue
        boxes = {b["id"]: b for b in result["boxes"]}
        box = boxes["v"]
        border = tuple(box[key] for key in ("x", "y", "border_width", "border_height"))
        content = (box["content_width"], box["content_height"])
        lines = tuple(tuple(line[key] for key in ("text", "x", "y", "content_width", "height")) for line in box["lines"])
        next_y = boxes["next"]["y"]
        observed[name] = {"border_xywh": border, "content_wh": content, "lines": lines, "next_y": next_y}
        passed &= (border, content, lines, next_y) == (case.box, case.content or case.box[2:], case.lines, case.next_y)
    nested = layout_normal_flow(PAGE.format("<div>AB</div>"), BASE, viewport_width=120)
    if nested["outcome"] != "placed":
        observed["nested"] = nested["reason"]
        return False, observed
    boxes = {item["id"]: item for item in nested["boxes"]}
    child = boxes["div"]
    border = tuple(boxes["v"][key] for key in ("x", "y", "border_width", "border_height"))
    line = tuple(child["lines"][0][key] for key in ("text", "x", "y", "content_width", "height"))
    observed["nested"] = {
        "border_xywh": border,
        "child_xywh": tuple(child[key] for key in ("x", "y", "border_width", "border_height")),
        "line": line,
        "next_y": boxes["next"]["y"],
    }
    nested_ok = (
        border == (0, 0, 10, 20)
        and observed["nested"]["child_xywh"] == (0, 0, 10, 20)
        and line == ("AB", 0, 0, 10, 20)
        and boxes["next"]["y"] == 20
        and boxes["v"]["lines"] == []
    )
    return passed and nested_ok, observed


if __name__ == "__main__":
    try:
        passed, observed = observe()
    except (KeyError, IndexError, TypeError, ValueError) as error:
        passed, observed = False, {"geometry_error": f"{type(error).__name__}: {error}"}
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))
