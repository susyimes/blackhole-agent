"""Place an inline-block in the line shortened by a float.

A 40 by 20 left float leaves AA and a shrink-to-fit BB on the shortened
line: the line starts at x 40 and the atomic border box starts at x 60.
A 180px inline-block does not fit that gap, so AA stays beside the float
and the atomic box starts at x 0, y 20. A right float leaves the fitting
atomic box at x 20. The following block starts under the taller float.
An inline-block beside that float and a block sibling stays invalid, and
so does a shaped float.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the atomic box exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_PAGE = '<div id="page">{body}<div id="next">Z</div></div>'


def _lay(layout, body: str, stylesheet: str, width: int = 200) -> dict[str, object]:
    try:
        placed = layout(_PAGE.format(body=body), _FONT + stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


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


def _at(box: dict[str, object] | None) -> dict[str, object]:
    if box is None:
        return {"x": None, "y": None, "w": None, "h": None}
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "w": box.get("content_width"),
        "h": box.get("content_height"),
    }


def _line_at(line: dict[str, object] | None) -> dict[str, object]:
    if line is None:
        return {"text": None, "x": None, "y": None, "h": None, "w": None, "runs": None, "atoms": None}
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "h": line.get("height"),
        "w": line.get("content_width"),
        "runs": line.get("runs"),
        "atoms": line.get("atoms"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    fit = _lay(
        layout_normal_flow,
        '<div id="p"><div id="f">F</div>AA<span id="atom">BB</span>CC</div>',
        "#f { float: left; width: 40px; height: 20px; }\n#atom { display: inline-block; }\n",
    )
    drop = _lay(
        layout_normal_flow,
        '<div id="p"><div id="f">F</div>AA<span id="atom">BB</span></div>',
        "#f { float: left; width: 40px; height: 20px; }\n#atom { display: inline-block; width: 180px; }\n",
    )
    right = _lay(
        layout_normal_flow,
        '<div id="p"><div id="f">F</div>AA<span id="atom">BB</span>CC</div>',
        "#f { float: right; width: 40px; height: 20px; }\n#atom { display: inline-block; }\n",
    )
    mixed = _lay(
        layout_normal_flow,
        '<div id="p"><div id="f">F</div>AA<span id="atom">BB</span><div id="b">CC</div></div>',
        "#f { float: left; width: 40px; height: 20px; }\n#atom { display: inline-block; }\n",
    )
    shaped = _lay(
        layout_normal_flow,
        '<div id="p"><div id="f">F</div>AA<span id="atom">BB</span></div>',
        "#f { float: left; width: 40px; height: 40px; shape-outside: circle(20px at 20px 20px); }\n"
        "#atom { display: inline-block; }\n",
    )

    def snap(result: dict[str, object]) -> dict[str, object]:
        boxes = result.get("boxes")
        parent = _box(boxes, "p")
        return {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "p": _at(parent),
            "f": _at(_box(boxes, "f")),
            "atom": _at(_box(boxes, "atom")),
            "next": _at(_box(boxes, "next")),
            "line": _line_at(_line(parent)),
            "lines": None if parent is None else parent.get("lines"),
        }

    observed = {
        "fit": snap(fit),
        "drop": snap(drop),
        "right": snap(right),
        "mixed": snap(mixed),
        "shaped": snap(shaped),
    }
    fit_line = observed["fit"]["line"]
    drop_parent = _box(drop.get("boxes"), "p")
    drop_lines = drop_parent.get("lines") if isinstance(drop_parent, dict) else None
    drop_second = drop_lines[1] if isinstance(drop_lines, list) and len(drop_lines) > 1 else None
    checks = {
        "fitting_atomic_box_shares_the_shortened_line": (
            fit.get("outcome") == "placed"
            and fit_line == {
                "text": "AACC",
                "x": 40,
                "y": 0,
                "h": 10,
                "w": 60,
                "runs": [
                    {"text": "AA", "x": 40, "font_size": 10, "width": 20},
                    {"text": "CC", "x": 80, "font_size": 10, "width": 20},
                ],
                "atoms": [{"id": "atom", "x": 60, "width": 20}],
            }
            and observed["fit"]["atom"] == {"x": 60, "y": 0, "w": 20, "h": 10}
            and observed["fit"]["f"] == {"x": 0, "y": 0, "w": 40, "h": 20}
            and observed["fit"]["next"]["y"] == 20
            and observed["fit"]["p"]["h"] == 20
        ),
        "wide_atomic_box_moves_below_the_float": (
            drop.get("outcome") == "placed"
            and observed["drop"]["line"]["text"] == "AA"
            and observed["drop"]["line"]["x"] == 40
            and observed["drop"]["line"]["y"] == 0
            and isinstance(drop_second, dict)
            and drop_second.get("y") == 20
            and observed["drop"]["atom"] == {"x": 0, "y": 20, "w": 180, "h": 10}
            and observed["drop"]["next"]["y"] == 30
        ),
        "right_float_leaves_the_atomic_box_at_the_start": (
            right.get("outcome") == "placed"
            and observed["right"]["line"]["x"] == 0
            and observed["right"]["line"]["text"] == "AACC"
            and observed["right"]["atom"] == {"x": 20, "y": 0, "w": 20, "h": 10}
            and observed["right"]["f"]["x"] == 160
            and observed["right"]["next"]["y"] == 20
        ),
        "inline_block_beside_a_float_and_a_block_stays_invalid": (
            mixed.get("outcome") == "invalid" and mixed.get("boxes") is None
        ),
        "shaped_float_stays_invalid": (
            shaped.get("outcome") == "invalid" and shaped.get("boxes") is None
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
