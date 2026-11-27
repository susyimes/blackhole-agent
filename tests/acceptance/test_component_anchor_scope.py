"""Measure component-local anchor insets, sizes and positioning areas."""

import json

from blackhole_agent.css_normal_flow import layout_normal_flow

PAGE = """
<div id="guide"></div>
<section class="card">
  <div id="a"></div><div id="badge"></div>
  <div id="first" class="tip"></div><div id="shared" class="guide"></div>
  <section id="nested">
    <div id="b"></div><div id="area"></div><div id="hidden" class="guide"></div>
  </section>
  <div id="again" class="tip"></div>
</section>
<section class="card">
  <div id="c"></div><div id="second" class="tip"></div><div id="private"></div>
</section>
<div id="outside" class="tip"></div><div id="next"></div>
"""
CSS = """
.card { anchor-scope: --pin, --badge; }
#nested { anchor-scope: all; }
#guide { anchor-name: --guide; margin-left: 3px; width: 11px; height: 4px; }
#a, #b, #c { anchor-name: --pin; }
#a { margin-left: 20px; width: 32px; height: 10px; }
#b { margin-left: 110px; width: 18px; height: 8px; }
#c { margin-left: 60px; width: 45px; height: 12px; }
#badge { anchor-name: --badge; margin-left: 70px; width: 9px; height: 0px; }
.tip, .guide, #area, #private { position: absolute; height: 4px; }
.tip { position-anchor: --pin; left: anchor(right, 1px); top: anchor(bottom, 2px);
       width: anchor-size(width, 7px); }
.guide { left: anchor(--guide right, 1px); top: anchor(--guide bottom, 2px);
         width: anchor-size(--guide width, 7px); }
#area { position-anchor: --pin; position-area: inline-end; width: anchor-size(width); }
#second { position: fixed; }
#private { left: anchor(--badge right, 1px); top: 3px; width: 5px; }
#next { width: 3px; height: 4px; }
"""

# Physical x, y, width and height in CSS pixels.
EXPECTED = {
    "first": [52, 14, 32, 4], "shared": [14, 4, 11, 4], "area": [128, 16, 18, 4],
    "hidden": [1, 2, 7, 4], "again": [52, 14, 32, 4], "second": [105, 34, 45, 4],
    "private": [1, 3, 5, 4], "outside": [1, 2, 7, 4], "next": [0, 34, 3, 4],
}
OWNER = """
<div id="frame"><div id="own"></div><div id="reset"><div id="inherit"></div></div></div>
<div id="outside"></div><div id="exported"></div>
"""
ALIASES = """
#frame { anchor-name: --Pin, --pin; anchor-scope: --Pin; margin-left: 30px; width: 26px; height: 18px; }
#reset { anchor-scope: inherit; }
#own, #inherit, #outside, #exported { position: absolute; position-anchor: --Pin; height: 4px;
    left: anchor(right, 1px); top: anchor(bottom, 2px); width: anchor-size(width, 7px); }
#exported { position-anchor: --pin; }
"""
AT_FRAME = [56, 18, 26, 4]
FALLBACK = [1, 2, 7, 4]
CASES = {
    "components": (PAGE, CSS, EXPECTED),
    "boxless_wrappers": (PAGE, CSS + ".card, #nested { display: contents; }", EXPECTED),
    "aliases": (OWNER, ALIASES, {"own": AT_FRAME, "inherit": FALLBACK, "outside": FALLBACK, "exported": AT_FRAME}),
    "private_only": (
        OWNER, ALIASES.replace("--Pin, --pin", "--Pin"),
        {"own": AT_FRAME, "inherit": FALLBACK, "outside": FALLBACK, "exported": FALLBACK},
    ),
}


def rectangles(markup, css, ids):
    layout = layout_normal_flow(markup, css, viewport_width=400, viewport_height=300)
    if layout["outcome"] != "placed":
        return {"outcome": layout["outcome"], "reason": layout.get("reason")}
    return {
        box["id"]: [box[key] for key in ("x", "y", "border_width", "border_height")]
        for box in layout["boxes"] if box["id"] in ids
    }


if __name__ == "__main__":
    observed = {case: rectangles(*fixture) for case, fixture in CASES.items()}
    passed = all(observed[case] == expected for case, (_, _, expected) in CASES.items())
    print(json.dumps({"passed": passed, "observed": observed}))
