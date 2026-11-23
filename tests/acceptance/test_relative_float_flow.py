"""Paint a relative inline on the line a float already shortened.

In a marginless 240px viewport, a 40 by 20 left float leaves AA at x 40,
shifts BB by left 5px and top 4px to x 65 y 4, and keeps CC at x 80. The
float stays at the origin and the following block stays at y 20. A 50
percent left on a 100px paragraph adds 50px. A 70px paragraph wraps the
spaced word BB onto the second line still beside the float, at x 45 y 13.
A later block sibling stays at y 10 while the float still overlaps it. A
vertical-rl paragraph, a sticky inline, and a relative inline-block stay
unplaced.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the float case exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_SHIFT = (
    '<div id="page"><div id="p"><div id="f">F</div>'
    'AA<span id="rel">BB</span>CC</div><div id="next">Z</div></div>'
)
_PERCENT = (
    '<div id="page"><div id="p"><div id="f">F</div>'
    'AA<span id="rel">BB</span>CC</div><div id="next">Z</div></div>'
)
_WRAP = (
    '<div id="page"><div id="p"><div id="f">F</div>'
    'AA <span id="rel">BB</span></div><div id="next">Z</div></div>'
)
_SIBLING = (
    '<div id="page"><div id="p"><div id="f">F</div>'
    'AA<span id="rel">BB</span>CC<div id="after">ZZ</div></div>'
    '<div id="next">Z</div></div>'
)
_VERTICAL = (
    '<div id="page"><div id="p"><div id="f">F</div>'
    'AA<span id="rel">BB</span></div></div>'
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lines_named(result: dict[str, object], text: str) -> list[dict[str, object]]:
    boxes = result.get("boxes")
    found: list[dict[str, object]] = []
    if not isinstance(boxes, list):
        return found
    for box in boxes:
        if not isinstance(box, dict) or not isinstance(box.get("lines"), list):
            continue
        for line in box["lines"]:
            if isinstance(line, dict) and line.get("text") == text:
                found.append(line)
    return found


def _runs(line: dict[str, object] | None) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    if line is None or not isinstance(line.get("runs"), list):
        return found
    for run in line["runs"]:
        if isinstance(run, dict) and isinstance(run.get("text"), str):
            found[str(run["text"])] = {
                "x": run.get("x"),
                "y": run.get("y"),
                "width": run.get("width"),
            }
    return found


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, _FONT + stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _point(result: dict[str, object], ident: str) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "x": None if box is None else box.get("x"),
        "y": None if box is None else box.get("y"),
        "w": None if box is None else box.get("content_width"),
        "h": None if box is None else box.get("content_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    shift = _lay(
        layout_normal_flow,
        _SHIFT,
        "#f { float: left; width: 40px; height: 20px; }\n"
        "#rel { position: relative; left: 5px; top: 4px; }\n",
    )
    percent = _lay(
        layout_normal_flow,
        _PERCENT,
        "#p { width: 100px; }\n"
        "#f { float: left; width: 40px; height: 10px; }\n"
        "#rel { position: relative; left: 50%; }\n",
    )
    wrapped = _lay(
        layout_normal_flow,
        _WRAP,
        "#p { width: 70px; }\n"
        "#f { float: left; width: 40px; height: 20px; }\n"
        "#rel { position: relative; left: 5px; top: 3px; }\n",
    )
    sibling = _lay(
        layout_normal_flow,
        _SIBLING,
        "#f { float: left; width: 40px; height: 30px; }\n"
        "#rel { position: relative; left: 5px; top: 4px; }\n",
    )
    vertical = _lay(
        layout_normal_flow,
        _VERTICAL,
        "#p { writing-mode: vertical-rl; }\n"
        "#f { float: left; width: 40px; height: 20px; }\n"
        "#rel { position: relative; left: 5px; }\n",
    )
    sticky = _lay(
        layout_normal_flow,
        _SHIFT,
        "#f { float: left; width: 40px; height: 20px; }\n#rel { position: sticky; top: 0; }\n",
    )
    atom = _lay(
        layout_normal_flow,
        _SHIFT,
        "#f { float: left; width: 40px; height: 20px; }\n"
        "#rel { display: inline-block; position: relative; left: 5px; }\n",
    )

    shift_line = _lines_named(shift, "AABBCC")
    percent_line = _lines_named(percent, "AABBCC")
    wrap_aa = _lines_named(wrapped, "AA")
    wrap_bb = _lines_named(wrapped, "BB")
    sib_line = _lines_named(sibling, "AABBCC")
    after_line = _lines_named(sibling, "ZZ")
    shift_runs = _runs(shift_line[0] if shift_line else None)
    percent_runs = _runs(percent_line[0] if percent_line else None)
    wrap_runs = _runs(wrap_bb[0] if wrap_bb else None)
    sib_runs = _runs(sib_line[0] if sib_line else None)

    def line_at(lines: list[dict[str, object]], index: int = 0) -> dict[str, object]:
        if len(lines) <= index:
            return {"x": None, "y": None, "height": None}
        line = lines[index]
        return {"x": line.get("x"), "y": line.get("y"), "height": line.get("height")}

    observed: dict[str, object] = {
        "shift": {
            "line": line_at(shift_line),
            "runs": shift_runs,
            "float": _point(shift, "f"),
            "next": _point(shift, "next"),
            "reason": shift.get("reason"),
        },
        "percent": {
            "line": line_at(percent_line),
            "runs": percent_runs,
            "next": _point(percent, "next"),
            "reason": percent.get("reason"),
        },
        "wrap": {
            "first": line_at(wrap_aa),
            "second": line_at(wrap_bb),
            "runs": wrap_runs,
            "next": _point(wrapped, "next"),
            "reason": wrapped.get("reason"),
        },
        "sibling": {
            "line": line_at(sib_line),
            "runs": sib_runs,
            "after": _point(sibling, "after"),
            "after_line": line_at(after_line),
            "next": _point(sibling, "next"),
            "reason": sibling.get("reason"),
        },
        "vertical": vertical.get("reason"),
        "sticky": sticky.get("reason"),
        "atom": atom.get("reason"),
    }
    checks = {
        "relative_glyph_tracks_the_shortened_line": (
            shift.get("outcome") == "placed"
            and line_at(shift_line) == {"x": 40, "y": 0, "height": 10}
            and shift_runs.get("AA") == {"x": 40, "y": 0, "width": 20}
            and shift_runs.get("BB") == {"x": 65, "y": 4, "width": 20}
            and shift_runs.get("CC") == {"x": 80, "y": 0, "width": 20}
            and _point(shift, "f")["x"] == 0
            and _point(shift, "f")["y"] == 0
            and _point(shift, "f")["w"] == 40
            and _point(shift, "f")["h"] == 20
            and _point(shift, "next")["y"] == 20
        ),
        "percentage_left_uses_the_paragraph_width": (
            percent.get("outcome") == "placed"
            and line_at(percent_line) == {"x": 40, "y": 0, "height": 10}
            and percent_runs.get("AA") == {"x": 40, "y": 0, "width": 20}
            and percent_runs.get("BB") == {"x": 110, "y": 0, "width": 20}
            and percent_runs.get("CC") == {"x": 80, "y": 0, "width": 20}
            and _point(percent, "next")["y"] == 10
        ),
        "wrapped_fragment_stays_beside_the_float": (
            wrapped.get("outcome") == "placed"
            and line_at(wrap_aa) == {"x": 40, "y": 0, "height": 10}
            and line_at(wrap_bb) == {"x": 40, "y": 10, "height": 10}
            and wrap_runs.get("BB") == {"x": 45, "y": 13, "width": 20}
            and _point(wrapped, "next")["y"] == 20
        ),
        "following_block_keeps_its_static_position": (
            sibling.get("outcome") == "placed"
            and line_at(sib_line) == {"x": 40, "y": 0, "height": 10}
            and sib_runs.get("BB") == {"x": 65, "y": 4, "width": 20}
            and _point(sibling, "after")["y"] == 10
            and line_at(after_line) == {"x": 40, "y": 10, "height": 10}
            and _point(sibling, "next")["y"] == 30
        ),
        "vertical_paragraph_is_rejected": vertical.get("outcome") == "invalid" and vertical.get("boxes") is None,
        "sticky_inline_is_rejected": sticky.get("outcome") == "invalid" and sticky.get("boxes") is None,
        "relative_inline_block_is_rejected": atom.get("outcome") == "invalid" and atom.get("boxes") is None,
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
