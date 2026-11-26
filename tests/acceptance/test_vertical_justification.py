"""Open leftover gaps down a vertical line.

AA BB CC DD at 10px in a 100px vertical-rl measure paints AA, BB and CC in
the right column at y 0, 40 and 80. DD stays packed at the top of the left
column, and the next block starts at y 100. vertical-lr swaps the columns.
justify-all stretches AA BB so BB paints at y 60. text-justify none leaves
BB at y 30. text-align-last justify stretches only CC DD, so DD paints at
y 40. inter-character gives AA and BB a physical height of 30 and paints BB
at y 50. A 40px nowrap measure does not compress BB away from y 30. A 30px
measure keeps the single words AA and BB at y 0. Inherited justify matches
the 100px measure. rtl, sideways-lr, preserved spaces, a relative inline,
an inline-block, and a mixed font stay unplaced.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json
import sys

_FONT = "html, body, p, div { margin: 0px; }\n#page { font-size: 10px; line-height: 10px; }\n"
_PAGE = '<div id="page"><div id="v">{body}</div><p id="next">Z</p></div>'


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
        placed = layout(_PAGE.format(body=body), _FONT + stylesheet, viewport_width=120)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _rejected(result: dict[str, object]) -> bool:
    return result.get("outcome") == "invalid" and result.get("boxes") is None


def _runs(result: dict[str, object], index: int = 0) -> dict[str, object]:
    line = _line(_box(result.get("boxes"), "v"), index)
    found: dict[str, object] = {}
    if line is None or not isinstance(line.get("runs"), list):
        return found
    for run in line["runs"]:
        if isinstance(run, dict) and isinstance(run.get("text"), str):
            found[str(run["text"])] = {
                "x": run.get("x"),
                "y": run.get("y"),
                "width": run.get("width"),
                "height": run.get("height"),
            }
    return found


def _facts(result: dict[str, object], index: int = 0) -> dict[str, object]:
    box = _box(result.get("boxes"), "v")
    line = _line(box, index)
    nxt = _box(result.get("boxes"), "next")
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "text": None if line is None else line.get("text"),
        "x": None if line is None else line.get("x"),
        "y": None if line is None else line.get("y"),
        "content_width": None if line is None else line.get("content_width"),
        "height": None if line is None else line.get("height"),
        "border_width": None if box is None else box.get("border_width"),
        "border_height": None if box is None else box.get("border_height"),
        "next_y": None if nxt is None else nxt.get("y"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    words = "AA BB CC DD"
    pair = "AA BB"
    cases = {
        "justify": _lay(layout_normal_flow, words, "#v { writing-mode: vertical-rl; height: 100px; text-align: justify; }\n"),
        "inherit": _lay(
            layout_normal_flow,
            words,
            "#page { text-align: justify; }\n#v { writing-mode: vertical-rl; height: 100px; }\n",
        ),
        "left": _lay(layout_normal_flow, words, "#v { writing-mode: vertical-lr; height: 100px; text-align: justify; }\n"),
        "all": _lay(layout_normal_flow, pair, "#v { writing-mode: vertical-rl; height: 80px; text-align: justify-all; }\n"),
        "none": _lay(
            layout_normal_flow,
            pair,
            "#v { writing-mode: vertical-rl; height: 80px; text-align: justify; text-justify: none; }\n",
        ),
        "last": _lay(layout_normal_flow, words, "#v { writing-mode: vertical-rl; height: 60px; text-align-last: justify; }\n"),
        "character": _lay(
            layout_normal_flow,
            pair,
            "#v { writing-mode: vertical-rl; height: 80px; text-align: justify-all; text-justify: inter-character; }\n",
        ),
        "nowrap": _lay(
            layout_normal_flow,
            pair,
            "#v { writing-mode: vertical-rl; height: 40px; white-space: nowrap; text-align: justify-all; }\n",
        ),
        "single": _lay(layout_normal_flow, pair, "#v { writing-mode: vertical-rl; height: 30px; text-align: justify; }\n"),
        "rtl": _lay(
            layout_normal_flow,
            pair,
            "#v { writing-mode: vertical-rl; height: 80px; direction: rtl; text-align: justify; }\n",
        ),
        "sideways": _lay(
            layout_normal_flow,
            pair,
            "#v { writing-mode: sideways-lr; height: 80px; text-align: justify-all; }\n",
        ),
        "pre": _lay(
            layout_normal_flow,
            pair,
            "#v { writing-mode: vertical-rl; height: 80px; white-space: pre; text-align: justify; }\n",
        ),
        "relative": _lay(
            layout_normal_flow,
            'AA <span id="r">BB</span>',
            "#v { writing-mode: vertical-rl; height: 80px; text-align: justify-all; }\n#r { position: relative; top: 5px; }\n",
        ),
        "atom": _lay(
            layout_normal_flow,
            'AA<span id="a">BB</span>',
            "#v { writing-mode: vertical-rl; height: 80px; text-align: justify-all; }\n#a { display: inline-block; }\n",
        ),
        "mixed": _lay(
            layout_normal_flow,
            "AA<span>BB</span>",
            "#v { writing-mode: vertical-rl; height: 80px; text-align: justify-all; }\nspan { font-size: 20px; }\n",
        ),
    }
    spread = _runs(cases["justify"])
    packed = _runs(cases["justify"], 1)
    inherited = _runs(cases["inherit"])
    left = _runs(cases["left"])
    left_tail = _runs(cases["left"], 1)
    stretched = _runs(cases["all"])
    frozen = _runs(cases["none"])
    last = _runs(cases["last"], 1)
    characters = _runs(cases["character"])
    overflow = _runs(cases["nowrap"])
    alone = _runs(cases["single"])
    below = _runs(cases["single"], 1)
    word = {"x": 10, "y": 0, "width": 10, "height": 20}
    checks = {
        "justify_spreads_the_right_column_and_packs_the_last": (
            _facts(cases["justify"]).get("text") == "AA BB CC"
            and _facts(cases["justify"]).get("x") == 10
            and _facts(cases["justify"]).get("height") == 100
            and _facts(cases["justify"]).get("content_width") == 10
            and _facts(cases["justify"]).get("border_width") == 20
            and _facts(cases["justify"]).get("border_height") == 100
            and _facts(cases["justify"], 1).get("text") == "DD"
            and _facts(cases["justify"], 1).get("x") == 0
            and _facts(cases["justify"], 1).get("height") == 20
            and _facts(cases["justify"]).get("next_y") == 100
            and spread.get("AA") == {"x": 10, "y": 0, "width": 10, "height": 20}
            and spread.get("BB") == {"x": 10, "y": 40, "width": 10, "height": 20}
            and spread.get("CC") == {"x": 10, "y": 80, "width": 10, "height": 20}
            and packed.get("DD") == {"x": 0, "y": 0, "width": 10, "height": 20}
        ),
        "justify_inherits_from_the_parent": (
            inherited.get("BB") == {"x": 10, "y": 40, "width": 10, "height": 20}
            and inherited.get("CC") == {"x": 10, "y": 80, "width": 10, "height": 20}
            and _facts(cases["inherit"]).get("next_y") == 100
        ),
        "vertical_lr_spreads_the_left_column": (
            left.get("AA") == {"x": 0, "y": 0, "width": 10, "height": 20}
            and left.get("BB") == {"x": 0, "y": 40, "width": 10, "height": 20}
            and left.get("CC") == {"x": 0, "y": 80, "width": 10, "height": 20}
            and left_tail.get("DD") == {"x": 10, "y": 0, "width": 10, "height": 20}
            and _facts(cases["left"]).get("next_y") == 100
        ),
        "justify_all_stretches_the_only_column": (
            _facts(cases["all"]).get("text") == "AA BB"
            and _facts(cases["all"]).get("height") == 80
            and _facts(cases["all"]).get("border_width") == 10
            and _facts(cases["all"]).get("next_y") == 80
            and stretched.get("AA") == {"x": 0, "y": 0, "width": 10, "height": 20}
            and stretched.get("BB") == {"x": 0, "y": 60, "width": 10, "height": 20}
        ),
        "text_justify_none_keeps_the_original_gap": (
            _facts(cases["none"]).get("height") == 50
            and frozen.get("BB") == {"x": 0, "y": 30, "width": 10, "height": 20}
            and _facts(cases["none"]).get("next_y") == 80
        ),
        "text_align_last_justify_stretches_only_the_last_column": (
            _facts(cases["last"]).get("text") == "AA BB"
            and _facts(cases["last"]).get("x") == 10
            and _facts(cases["last"]).get("height") == 50
            and _runs(cases["last"]) == {}
            and _facts(cases["last"], 1).get("text") == "CC DD"
            and _facts(cases["last"], 1).get("height") == 60
            and last.get("CC") == {"x": 0, "y": 0, "width": 10, "height": 20}
            and last.get("DD") == {"x": 0, "y": 40, "width": 10, "height": 20}
            and _facts(cases["last"]).get("next_y") == 60
        ),
        "inter_character_opens_gaps_inside_the_word": (
            characters.get("AA") == {"x": 0, "y": 0, "width": 10, "height": 30}
            and characters.get("BB") == {"x": 0, "y": 50, "width": 10, "height": 30}
            and _facts(cases["character"]).get("height") == 80
        ),
        "nowrap_does_not_compress_an_overflowing_column": (
            _facts(cases["nowrap"]).get("height") == 50
            and _facts(cases["nowrap"]).get("border_height") == 40
            and overflow.get("BB") == {"x": 0, "y": 30, "width": 10, "height": 20}
            and _facts(cases["nowrap"]).get("next_y") == 40
        ),
        "a_column_without_an_interior_gap_stays_packed": (
            _facts(cases["single"]).get("text") == "AA"
            and alone.get("AA") == word
            and _facts(cases["single"], 1).get("text") == "BB"
            and below.get("BB") == {"x": 0, "y": 0, "width": 10, "height": 20}
            and _facts(cases["single"]).get("next_y") == 30
        ),
        "rtl_justification_is_rejected": _rejected(cases["rtl"]),
        "sideways_justification_is_rejected": _rejected(cases["sideways"]),
        "preserved_white_space_is_rejected": _rejected(cases["pre"]),
        "relative_inline_is_rejected": _rejected(cases["relative"]),
        "inline_block_is_rejected": _rejected(cases["atom"]),
        "mixed_font_is_rejected": _rejected(cases["mixed"]),
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
