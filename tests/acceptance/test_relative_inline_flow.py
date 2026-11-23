"""Shift a relative inline inside a normal-flow line without reflowing it.

AA<span>BB</span>CC at 10px paints BB at x 25 y 4 when the span is relative
with left 5px and top 4px. CC stays at x 40. The line stays at y 0 and the
following block stays at y 10. An over-constrained ltr pair keeps left.
left 50% of a 40px paragraph adds 20px. top 50% of an automatic height adds
nothing, and top 50% of a 20px height paints BB at y 10. A nested left 3px
inside left 5px adds to 8px. text-align center keeps the extra 5px on the
centered static position. A 50px wrap still breaks before CC, and only that
fragment moves. A left float shortens the line and the relative glyph keeps
its left offset. Sticky inlines, relative inline-blocks, and an inline-block
inside the span are rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects relative inlines exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_PAGE = '<div id="page">{body}<div id="next">Z</div></div>'
_LINE = '<div id="p">AA<span id="rel">BB</span>CC</div>'
_NEST = '<div id="p"><span id="outer">AA<span id="inner">BB</span></span>CC</div>'
_WRAP = '<div id="p">AA BB <span id="rel">CC</span> DD</div>'
_ATOM = '<div id="p"><span id="rel">A<span id="atom">BB</span></span>CC</div>'
_FLOAT = '<div id="p"><div id="f">F</div>AA<span id="rel">BB</span></div>'


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


def _run(line: dict[str, object] | None, text: str) -> dict[str, object] | None:
    if line is None or not isinstance(line.get("runs"), list):
        return None
    for run in line["runs"]:
        if isinstance(run, dict) and run.get("text") == text:
            return run
    return None


def _lay(layout, body: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(_PAGE.format(body=body), _FONT + stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _rejected(result: dict[str, object]) -> bool:
    return result.get("outcome") == "invalid" and result.get("boxes") is None


def _placed(result: dict[str, object], ident: str, index: int = 0) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    line = _line(box, index)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "x": None if box is None else box.get("x"),
        "y": None if box is None else box.get("y"),
        "h": None if box is None else box.get("content_height"),
        "text": None if line is None else line.get("text"),
        "line_x": None if line is None else line.get("x"),
        "line_y": None if line is None else line.get("y"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "shift": _lay(layout_normal_flow, _LINE, "#rel { position: relative; left: 5px; top: 4px; }\n"),
        "pair": _lay(
            layout_normal_flow,
            _LINE,
            "#rel { position: relative; left: 5px; right: 9px; }\n",
        ),
        "rtl": _lay(
            layout_normal_flow,
            _LINE,
            "#rel { position: relative; direction: rtl; left: 5px; right: 9px; }\n",
        ),
        "percent": _lay(
            layout_normal_flow,
            _LINE,
            "#p { width: 40px; }\n#rel { position: relative; left: 50%; }\n",
        ),
        "auto_top": _lay(layout_normal_flow, _LINE, "#rel { position: relative; top: 50%; }\n"),
        "fixed_top": _lay(
            layout_normal_flow,
            _LINE,
            "#p { height: 20px; }\n#rel { position: relative; top: 50%; }\n",
        ),
        "nest": _lay(
            layout_normal_flow,
            _NEST,
            "#outer { position: relative; left: 5px; }\n#inner { position: relative; left: 3px; }\n",
        ),
        "center": _lay(
            layout_normal_flow,
            _LINE,
            "#p { width: 100px; text-align: center; }\n#rel { position: relative; left: 5px; }\n",
        ),
        "wrap": _lay(
            layout_normal_flow,
            _WRAP,
            "#p { width: 50px; }\n#rel { position: relative; left: 5px; }\n",
        ),
        "sticky": _lay(layout_normal_flow, _LINE, "#rel { position: sticky; top: 0; }\n"),
        "atom": _lay(
            layout_normal_flow,
            _LINE,
            "#rel { display: inline-block; position: relative; left: 5px; }\n",
        ),
        "inside": _lay(
            layout_normal_flow,
            _ATOM,
            "#rel { position: relative; left: 5px; }\n#atom { display: inline-block; }\n",
        ),
        "float": _lay(
            layout_normal_flow,
            _FLOAT,
            "#f { float: left; }\n#rel { position: relative; left: 5px; }\n",
        ),
    }

    def runs(name: str, index: int = 0) -> dict[str, object]:
        line = _line(_box(cases[name].get("boxes"), "p"), index)
        found = {}
        if line is not None and isinstance(line.get("runs"), list):
            for run in line["runs"]:
                if isinstance(run, dict) and isinstance(run.get("text"), str):
                    found[str(run["text"])] = {"x": run.get("x"), "y": run.get("y"), "width": run.get("width")}
        return found

    observed: dict[str, object] = {
        name: {"p": _placed(result, "p"), "p2": _placed(result, "p", 1), "next": _placed(result, "next")}
        for name, result in cases.items()
    }
    observed["runs"] = {name: runs(name) for name in ("shift", "pair", "rtl", "percent", "auto_top", "fixed_top", "center")}
    observed["nest_runs"] = runs("nest")
    observed["wrap_runs"] = {"first": runs("wrap"), "second": runs("wrap", 1)}
    shift = runs("shift")
    pair = runs("pair")
    rtl = runs("rtl")
    percent = runs("percent")
    auto_top = runs("auto_top")
    fixed_top = runs("fixed_top")
    nest = runs("nest")
    center = runs("center")
    wrapped = runs("wrap", 1)
    checks = {
        "relative_inline_shifts_without_moving_the_line": (
            cases["shift"].get("outcome") == "placed"
            and _placed(cases["shift"], "p").get("text") == "AABBCC"
            and _placed(cases["shift"], "p").get("line_x") == 0
            and _placed(cases["shift"], "p").get("line_y") == 0
            and _placed(cases["shift"], "next").get("y") == 10
            and shift.get("AA") == {"x": 0, "y": 0, "width": 20}
            and shift.get("BB") == {"x": 25, "y": 4, "width": 20}
            and shift.get("CC") == {"x": 40, "y": 0, "width": 20}
        ),
        "ltr_overconstraint_keeps_left": (
            cases["pair"].get("outcome") == "placed"
            and pair.get("BB") == {"x": 25, "y": 0, "width": 20}
            and pair.get("CC") == {"x": 40, "y": 0, "width": 20}
        ),
        "rtl_overconstraint_keeps_right": (
            cases["rtl"].get("outcome") == "placed"
            and rtl.get("BB") == {"x": 11, "y": 0, "width": 20}
            and rtl.get("CC") == {"x": 40, "y": 0, "width": 20}
        ),
        "percentage_left_uses_the_paragraph_width": (
            cases["percent"].get("outcome") == "placed"
            and _placed(cases["percent"], "p").get("text") == "AABBCC"
            and percent.get("BB") == {"x": 40, "y": 0, "width": 20}
            and _placed(cases["percent"], "next").get("y") == 10
        ),
        "percentage_top_of_an_automatic_height_stays_put": (
            cases["auto_top"].get("outcome") == "placed"
            and auto_top.get("BB") == {"x": 20, "y": 0, "width": 20}
        ),
        "percentage_top_of_a_definite_height_moves_the_glyph": (
            cases["fixed_top"].get("outcome") == "placed"
            and fixed_top.get("BB") == {"x": 20, "y": 10, "width": 20}
            and _placed(cases["fixed_top"], "p").get("line_y") == 0
            and _placed(cases["fixed_top"], "next").get("y") == 20
        ),
        "nested_relative_offsets_add": (
            cases["nest"].get("outcome") == "placed"
            and nest.get("AA") == {"x": 5, "y": 0, "width": 20}
            and nest.get("BB") == {"x": 28, "y": 0, "width": 20}
            and nest.get("CC") == {"x": 40, "y": 0, "width": 20}
            and _placed(cases["nest"], "next").get("y") == 10
        ),
        "centered_line_keeps_the_relative_offset": (
            cases["center"].get("outcome") == "placed"
            and _placed(cases["center"], "p").get("line_x") == 20
            and center.get("BB") == {"x": 45, "y": 0, "width": 20}
            and center.get("CC") == {"x": 60, "y": 0, "width": 20}
            and _placed(cases["center"], "next").get("y") == 10
        ),
        "wrapping_keeps_the_break_and_shifts_the_fragment": (
            cases["wrap"].get("outcome") == "placed"
            and _placed(cases["wrap"], "p").get("text") == "AA BB"
            and _placed(cases["wrap"], "p", 1).get("text") == "CC DD"
            and _placed(cases["wrap"], "p", 1).get("line_y") == 10
            and wrapped.get("CC") == {"x": 5, "y": 10, "width": 20}
            and wrapped.get(" DD") == {"x": 20, "y": 10, "width": 30}
            and _placed(cases["wrap"], "next").get("y") == 20
        ),
        "sticky_inline_is_rejected": _rejected(cases["sticky"]),
        "relative_inline_block_is_rejected": _rejected(cases["atom"]),
        "inline_block_inside_relative_inline_is_rejected": _rejected(cases["inside"]),
        "float_beside_relative_inline_shifts_the_glyph": (
            cases["float"].get("outcome") == "placed"
            and _placed(cases["float"], "p").get("text") == "AABB"
            and _placed(cases["float"], "p").get("line_x") == 10
            and _placed(cases["float"], "p").get("line_y") == 0
            and runs("float").get("AA") == {"x": 10, "y": 0, "width": 20}
            and runs("float").get("BB") == {"x": 35, "y": 0, "width": 20}
            and _placed(cases["float"], "next").get("y") == 10
            and _placed(cases["float"], "f").get("x") == 0
            and _placed(cases["float"], "f").get("y") == 0
        ),
    }
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
