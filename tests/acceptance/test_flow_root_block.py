"""Place a flow-root as its own block formatting context.

A flow-root keeps a child's top margin inside, so the parent at y 10 is 40
tall, the child paints at y 40, and the next block starts at y 50. The same
tree as a block pulls that margin out: the parent and child sit at y 30 and
the next block starts at y 40. An empty flow-root with margins 15 and 25
keeps them apart and the next block starts at y 40; the empty block
collapses them and the next block starts at y 25. Beside a 50 by 40 left
float, automatic Hello sits at x 50 in a 150px content box, width 100px
stays at x 50, and width 160px drops to y 40. A plain block keeps the full
200px width and only moves its line to x 50. vertical-rl, rtl, a replaced
flow-root, and column-count stay unplaced.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json
import sys

_BASE = (
    "html, body, div, p, img { margin: 0px; }\n"
    "#page { font-size: 10px; line-height: 10px; width: 200px; }\n"
    "#next { height: 10px; }\n"
)
_PIN = "#pin { float: left; width: 50px; height: 40px; }\n"
_CHILD = '<div id="page"><div id="hole"><div id="child">A</div></div><p id="next">Z</p></div>'
_EMPTY = '<div id="page"><div id="hole"></div><p id="next">Z</p></div>'
_FLOAT = '<div id="page"><div id="pin">F</div><div id="hole">Hello</div><p id="next">Z</p></div>'


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    return line if isinstance(line, dict) else None


def _lay(layout, html: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(html, _BASE + stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _at(result: dict[str, object], ident: str) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    line = _line(box)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "x": None if box is None else box.get("x"),
        "y": None if box is None else box.get("y"),
        "content_width": None if box is None else box.get("content_width"),
        "content_height": None if box is None else box.get("content_height"),
        "line_x": None if line is None else line.get("x"),
        "line_text": None if line is None else line.get("text"),
    }


def _rejected(result: dict[str, object]) -> bool:
    return result.get("outcome") == "invalid" and result.get("boxes") is None


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "child_flow": _lay(
            layout_normal_flow,
            _CHILD,
            "#hole { display: flow-root; margin-top: 10px; }\n#child { margin-top: 30px; height: 10px; }\n",
        ),
        "child_block": _lay(
            layout_normal_flow,
            _CHILD,
            "#hole { margin-top: 10px; }\n#child { margin-top: 30px; height: 10px; }\n",
        ),
        "empty_flow": _lay(
            layout_normal_flow,
            _EMPTY,
            "#hole { display: flow-root; margin-top: 15px; margin-bottom: 25px; }\n",
        ),
        "empty_block": _lay(
            layout_normal_flow,
            _EMPTY,
            "#hole { margin-top: 15px; margin-bottom: 25px; }\n",
        ),
        "float_auto": _lay(layout_normal_flow, _FLOAT, _PIN + "#hole { display: flow-root; }\n"),
        "float_block": _lay(layout_normal_flow, _FLOAT, _PIN),
        "float_100": _lay(
            layout_normal_flow, _FLOAT, _PIN + "#hole { display: flow-root; width: 100px; }\n"
        ),
        "float_160": _lay(
            layout_normal_flow, _FLOAT, _PIN + "#hole { display: flow-root; width: 160px; }\n"
        ),
        "vertical": _lay(
            layout_normal_flow,
            '<div id="page"><div id="hole">AB</div></div>',
            "#hole { display: flow-root; writing-mode: vertical-rl; }\n",
        ),
        "rtl": _lay(
            layout_normal_flow,
            '<div id="page"><div id="hole">Hello</div></div>',
            "#hole { display: flow-root; direction: rtl; }\n",
        ),
        "replaced": _lay(
            layout_normal_flow,
            '<div id="page"><img id="hole" width="10" height="10"></div>',
            "#hole { display: flow-root; }\n",
        ),
        "columns": _lay(
            layout_normal_flow,
            '<div id="page"><div id="hole">Hello</div></div>',
            "#hole { display: flow-root; column-count: 2; }\n",
        ),
    }
    facts = {name: _at(result, "hole") for name, result in cases.items()}
    facts["child"] = _at(cases["child_flow"], "child")
    facts["next_flow"] = _at(cases["child_flow"], "next")
    facts["next_block"] = _at(cases["child_block"], "next")
    facts["next_empty_flow"] = _at(cases["empty_flow"], "next")
    facts["next_empty_block"] = _at(cases["empty_block"], "next")
    facts["next_160"] = _at(cases["float_160"], "next")
    checks = {
        "flow_root_keeps_the_child_margin_inside": (
            facts["child_flow"]["y"] == 10
            and facts["child_flow"]["content_height"] == 40
            and facts["child"]["y"] == 40
            and facts["child"]["content_height"] == 10
            and facts["next_flow"]["y"] == 50
        ),
        "a_block_pulls_the_child_margin_out": (
            facts["child_block"]["y"] == 30
            and facts["child_block"]["content_height"] == 10
            and facts["next_block"]["y"] == 40
        ),
        "an_empty_flow_root_keeps_its_margins_apart": (
            facts["empty_flow"]["y"] == 15
            and facts["empty_flow"]["content_height"] == 0
            and facts["next_empty_flow"]["y"] == 40
        ),
        "an_empty_block_collapses_through": facts["next_empty_block"]["y"] == 25,
        "automatic_flow_root_fills_the_space_beside_a_float": (
            facts["float_auto"]["x"] == 50
            and facts["float_auto"]["y"] == 0
            and facts["float_auto"]["content_width"] == 150
            and facts["float_auto"]["line_x"] == 50
            and facts["float_auto"]["line_text"] == "Hello"
        ),
        "a_plain_block_keeps_its_width_under_the_float": (
            facts["float_block"]["x"] == 0
            and facts["float_block"]["content_width"] == 200
            and facts["float_block"]["line_x"] == 50
        ),
        "a_fitting_width_stays_beside_the_float": (
            facts["float_100"]["x"] == 50
            and facts["float_100"]["y"] == 0
            and facts["float_100"]["content_width"] == 100
            and facts["float_100"]["line_x"] == 50
        ),
        "a_width_that_does_not_fit_starts_under_the_float": (
            facts["float_160"]["x"] == 0
            and facts["float_160"]["y"] == 40
            and facts["float_160"]["content_width"] == 160
            and facts["float_160"]["line_x"] == 0
            and facts["next_160"]["y"] == 50
        ),
        "vertical_flow_root_is_rejected": _rejected(cases["vertical"]),
        "rtl_flow_root_is_rejected": _rejected(cases["rtl"]),
        "replaced_flow_root_is_rejected": _rejected(cases["replaced"]),
        "flow_root_columns_are_rejected": _rejected(cases["columns"]),
    }
    observed = {"checks": checks, "facts": facts}
    return all(checks.values()), observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 even when it fails
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    payload = {"passed": bool(passed), "observed": observed if observed else {"error": "empty"}}
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    except (UnicodeEncodeError, TypeError) as exc:
        encoded = json.dumps(
            {"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}},
            separators=(",", ":"),
        ).encode("ascii")
    sys.stdout.buffer.write(encoded + b"\n")


if __name__ == "__main__":
    main()
