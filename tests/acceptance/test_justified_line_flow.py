"""Spread leftover space through the gaps of a justified line.

AA BB CC DD at 10px in a 100px paragraph paints AA at x 0, BB at x 40 and
CC at x 80 on the first line. DD stays packed at x 0 on the second line, and
the following block starts at y 20. justify-all stretches the only line of
AA BB so BB paints at x 60. text-justify none leaves BB at x 30.
text-align-last center centers DD at x 40 while the first line still
stretches. text-align-last justify stretches only CC DD, so DD paints at
x 40 inside a 60px paragraph. inter-character widens AA and BB to 30px and
paints BB at x 50. A 40px nowrap line does not compress BB away from x 30.
A 30px paragraph keeps the single words AA and BB at x 0. A left float
shortens the first line: AA, BB and CC paint at x 10, 45 and 80. Inherited
justify matches the 100px paragraph. Relative, rtl, pre, inline-block,
mixed font, and an unknown text-justify value are rejected. A vertical-rl
measure of 40px packs AA and BB into separate columns.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_PAGE = '<div id="page">{body}<div id="next">Z</div></div>'


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None, index: int = 0) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or len(box["lines"]) <= index:
        return None
    line = box["lines"][index]
    return line if isinstance(line, dict) else None


def _lay(layout, body: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(_PAGE.format(body=body), _FONT + stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _rejected(result: dict[str, object]) -> bool:
    return result.get("outcome") == "invalid" and result.get("boxes") is None


def _runs(result: dict[str, object], ident: str = "p", index: int = 0) -> dict[str, object]:
    line = _line(_box(result.get("boxes"), ident), index)
    found: dict[str, object] = {}
    if line is None or not isinstance(line.get("runs"), list):
        return found
    for run in line["runs"]:
        if isinstance(run, dict) and isinstance(run.get("text"), str):
            found[str(run["text"])] = {"x": run.get("x"), "y": run.get("y"), "width": run.get("width")}
    return found


def _facts(result: dict[str, object], ident: str = "p", index: int = 0) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    line = _line(box, index)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "text": None if line is None else line.get("text"),
        "x": None if line is None else line.get("x"),
        "y": None if line is None else line.get("y"),
        "content_width": None if line is None else line.get("content_width"),
        "next_y": None if _box(result.get("boxes"), "next") is None else _box(result.get("boxes"), "next").get("y"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    words = '<div id="p">AA BB CC DD</div>'
    pair = '<div id="p">AA BB</div>'
    cases = {
        "justify": _lay(layout_normal_flow, words, "#p { width: 100px; text-align: justify; }\n"),
        "inherit": _lay(
            layout_normal_flow,
            words,
            "#page { text-align: justify; }\n#p { width: 100px; }\n",
        ),
        "all": _lay(layout_normal_flow, pair, "#p { width: 80px; text-align: justify-all; }\n"),
        "none": _lay(
            layout_normal_flow,
            pair,
            "#p { width: 80px; text-align: justify; text-justify: none; }\n",
        ),
        "last_center": _lay(
            layout_normal_flow,
            words,
            "#p { width: 100px; text-align: justify; text-align-last: center; }\n",
        ),
        "last_justify": _lay(layout_normal_flow, words, "#p { width: 60px; text-align-last: justify; }\n"),
        "character": _lay(
            layout_normal_flow,
            pair,
            "#p { width: 80px; text-align: justify-all; text-justify: inter-character; }\n",
        ),
        "nowrap": _lay(
            layout_normal_flow,
            pair,
            "#p { width: 40px; white-space: nowrap; text-align: justify-all; }\n",
        ),
        "single": _lay(layout_normal_flow, pair, "#p { width: 30px; text-align: justify; }\n"),
        "float": _lay(
            layout_normal_flow,
            '<div id="f">F</div><div id="p">AA BB CC DD</div>',
            "#f { float: left; }\n#p { width: 100px; text-align: justify; }\n",
        ),
        "relative": _lay(
            layout_normal_flow,
            '<div id="p"><span id="r">BB</span></div>',
            "#p { width: 80px; text-align: justify; }\n#r { position: relative; left: 5px; }\n",
        ),
        "rtl": _lay(layout_normal_flow, pair, "#p { width: 80px; direction: rtl; text-align: justify; }\n"),
        "pre": _lay(layout_normal_flow, pair, "#p { width: 80px; white-space: pre; text-align: justify; }\n"),
        "atom": _lay(
            layout_normal_flow,
            '<div id="p">AA<span id="a">BB</span></div>',
            "#p { width: 80px; text-align: justify; }\n#a { display: inline-block; }\n",
        ),
        "mixed": _lay(
            layout_normal_flow,
            '<div id="p">AA<span>BB</span></div>',
            "#p { width: 80px; text-align: justify; }\nspan { font-size: 20px; }\n",
        ),
        "vertical": _lay(
            layout_normal_flow,
            '<div id="v">AA BB</div>',
            "#v { writing-mode: vertical-rl; height: 40px; text-align: justify; }\n",
        ),
        "invalid": _lay(layout_normal_flow, pair, "#p { width: 80px; text-justify: sideways; }\n"),
    }
    justify = _runs(cases["justify"])
    second = _runs(cases["justify"], index=1)
    inherited = _runs(cases["inherit"])
    stretched = _runs(cases["all"])
    frozen = _runs(cases["none"])
    centered = _runs(cases["last_center"], index=1)
    last = _runs(cases["last_justify"], index=1)
    characters = _runs(cases["character"])
    overflow = _runs(cases["nowrap"])
    alone = _runs(cases["single"])
    below = _runs(cases["single"], index=1)
    floated = _runs(cases["float"])
    checks = {
        "justify_spreads_interior_gaps_and_packs_the_last_line": (
            _facts(cases["justify"]).get("text") == "AA BB CC"
            and _facts(cases["justify"]).get("content_width") == 100
            and _facts(cases["justify"], index=1).get("text") == "DD"
            and _facts(cases["justify"], index=1).get("x") == 0
            and _facts(cases["justify"], index=1).get("content_width") == 20
            and _facts(cases["justify"]).get("next_y") == 20
            and justify.get("AA") == {"x": 0, "y": 0, "width": 20}
            and justify.get("BB") == {"x": 40, "y": 0, "width": 20}
            and justify.get("CC") == {"x": 80, "y": 0, "width": 20}
            and second.get("DD") == {"x": 0, "y": 10, "width": 20}
        ),
        "justify_inherits_from_the_parent": (
            inherited.get("BB") == {"x": 40, "y": 0, "width": 20}
            and inherited.get("CC") == {"x": 80, "y": 0, "width": 20}
            and _facts(cases["inherit"]).get("next_y") == 20
        ),
        "justify_all_stretches_the_only_line": (
            _facts(cases["all"]).get("text") == "AA BB"
            and _facts(cases["all"]).get("content_width") == 80
            and _facts(cases["all"]).get("next_y") == 10
            and stretched.get("AA") == {"x": 0, "y": 0, "width": 20}
            and stretched.get("BB") == {"x": 60, "y": 0, "width": 20}
        ),
        "text_justify_none_keeps_the_original_gap": (
            _facts(cases["none"]).get("content_width") == 50
            and frozen.get("BB") == {"x": 30, "y": 0, "width": 20}
            and _facts(cases["none"]).get("next_y") == 10
        ),
        "text_align_last_center_moves_only_the_last_line": (
            _runs(cases["last_center"]).get("BB") == {"x": 40, "y": 0, "width": 20}
            and _facts(cases["last_center"], index=1).get("x") == 40
            and _facts(cases["last_center"], index=1).get("content_width") == 20
            and centered.get("DD") == {"x": 40, "y": 10, "width": 20}
            and _facts(cases["last_center"]).get("next_y") == 20
        ),
        "text_align_last_justify_leaves_the_first_line_packed": (
            _facts(cases["last_justify"]).get("text") == "AA BB"
            and _facts(cases["last_justify"]).get("content_width") == 50
            and _facts(cases["last_justify"]).get("x") == 0
            and _facts(cases["last_justify"], index=1).get("text") == "CC DD"
            and _facts(cases["last_justify"], index=1).get("content_width") == 60
            and last.get("CC") == {"x": 0, "y": 10, "width": 20}
            and last.get("DD") == {"x": 40, "y": 10, "width": 20}
            and _facts(cases["last_justify"]).get("next_y") == 20
        ),
        "inter_character_opens_gaps_inside_the_word": (
            characters.get("AA") == {"x": 0, "y": 0, "width": 30}
            and characters.get("BB") == {"x": 50, "y": 0, "width": 30}
            and _facts(cases["character"]).get("content_width") == 80
        ),
        "nowrap_does_not_compress_an_overflowing_line": (
            _facts(cases["nowrap"]).get("content_width") == 50
            and overflow.get("BB") == {"x": 30, "y": 0, "width": 20}
            and _facts(cases["nowrap"]).get("next_y") == 10
        ),
        "a_line_without_an_interior_gap_stays_packed": (
            _facts(cases["single"]).get("text") == "AA"
            and alone.get("AA") == {"x": 0, "y": 0, "width": 20}
            and _facts(cases["single"], index=1).get("text") == "BB"
            and below.get("BB") == {"x": 0, "y": 10, "width": 20}
            and _facts(cases["single"]).get("next_y") == 20
        ),
        "a_float_shortens_the_line_that_justification_fills": (
            _facts(cases["float"]).get("x") == 10
            and _facts(cases["float"]).get("content_width") == 90
            and floated.get("AA") == {"x": 10, "y": 0, "width": 20}
            and floated.get("BB") == {"x": 45, "y": 0, "width": 20}
            and floated.get("CC") == {"x": 80, "y": 0, "width": 20}
            and _facts(cases["float"], index=1).get("x") == 0
            and _runs(cases["float"], index=1).get("DD") == {"x": 0, "y": 10, "width": 20}
            and _facts(cases["float"]).get("next_y") == 20
        ),
        "relative_inline_is_rejected": _rejected(cases["relative"]),
        "rtl_justification_is_rejected": _rejected(cases["rtl"]),
        "preserved_white_space_is_rejected": _rejected(cases["pre"]),
        "inline_block_is_rejected": _rejected(cases["atom"]),
        "mixed_font_is_rejected": _rejected(cases["mixed"]),
        "vertical_measure_packs_each_word_in_its_own_column": (
            _facts(cases["vertical"], "v").get("text") == "AA"
            and _facts(cases["vertical"], "v").get("x") == 10
            and _facts(cases["vertical"], "v").get("content_width") == 10
            and _facts(cases["vertical"], "v", 1).get("text") == "BB"
            and _facts(cases["vertical"], "v", 1).get("x") == 0
            and _runs(cases["vertical"], "v").get("AA") == {"x": 10, "y": 0, "width": 10}
            and _runs(cases["vertical"], "v", 1).get("BB") == {"x": 0, "y": 0, "width": 10}
            and _facts(cases["vertical"], "v").get("next_y") == 40
        ),
        "unknown_text_justify_is_rejected": _rejected(cases["invalid"]),
    }
    observed = {name: _facts(result) for name, result in cases.items()}
    observed["checks"] = checks
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
