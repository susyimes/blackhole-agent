"""Place an inline-block in the anonymous block beside a float and a block.

A 40 by 20 left float, AA, a shrink-to-fit inline-block, and CC share the
anonymous line: the line starts at x 40 and the atomic border box starts at
x 60. The block sibling's line stays at x 40, y 10, where the float still
overlaps. A 180px inline-block drops intact to x 0, y 20 and the sibling
starts at y 30. A right float leaves the fitting atomic box at x 20. A
shaped float and an atomic box taller than the strut stay rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the anonymous atomic box exits
0 with passed false.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_PAGE = '<div id="page">{body}<div id="next">Z</div></div>'
_FIT = '<div id="p"><div id="f">F</div>AA<span id="atom">BB</span>CC<div id="sib">DD</div></div>'
_DROP = '<div id="p"><div id="f">F</div>AA<span id="atom">BB</span><div id="sib">DD</div></div>'


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


def _line_with(boxes: object, text: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if not isinstance(item, dict):
            continue
        for line in item.get("lines") or []:
            if isinstance(line, dict) and line.get("text") == text:
                return line
    return None


def _owner(boxes: object, text: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if not isinstance(item, dict):
            continue
        for line in item.get("lines") or []:
            if isinstance(line, dict) and line.get("text") == text:
                return item
    return None


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

    fit_css = "#f { float: left; width: 40px; height: 20px; }\n#atom { display: inline-block; }\n"
    drop_css = "#f { float: left; width: 40px; height: 20px; }\n#atom { display: inline-block; width: 180px; }\n"
    right_css = "#f { float: right; width: 40px; height: 20px; }\n#atom { display: inline-block; }\n"
    shaped_css = (
        "#f { float: left; width: 40px; height: 40px; shape-outside: circle(20px at 20px 20px); }\n"
        "#atom { display: inline-block; }\n"
    )
    tall_css = "#f { float: left; width: 40px; height: 20px; }\n#atom { display: inline-block; height: 30px; }\n"
    fit = _lay(layout_normal_flow, _FIT, fit_css)
    drop = _lay(layout_normal_flow, _DROP, drop_css)
    right = _lay(layout_normal_flow, _FIT, right_css)
    shaped = _lay(layout_normal_flow, _FIT, shaped_css)
    tall = _lay(layout_normal_flow, _DROP, tall_css)

    def snap(result: dict[str, object]) -> dict[str, object]:
        boxes = result.get("boxes")
        parent = _box(boxes, "p")
        owner = _owner(boxes, "AACC") or _owner(boxes, "AA")
        return {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "p": _at(parent),
            "p_lines": 0 if parent is None else len(parent.get("lines") or []),
            "f": _at(_box(boxes, "f")),
            "atom": _at(_box(boxes, "atom")),
            "sib": _at(_box(boxes, "sib")),
            "next": _at(_box(boxes, "next")),
            "line": _line_at(_line_with(boxes, "AACC") or _line_with(boxes, "AA")),
            "sib_line": _line_at(_line_with(boxes, "DD")),
            "owner": None if owner is None else {"id": owner.get("id"), "w": owner.get("content_width")},
        }

    observed = {
        "fit": snap(fit),
        "drop": snap(drop),
        "right": snap(right),
        "shaped": snap(shaped),
        "tall": snap(tall),
    }
    fit_line = observed["fit"]["line"]
    drop_line = observed["drop"]["line"]
    fit_owner = observed["fit"]["owner"] if isinstance(observed["fit"]["owner"], dict) else {}
    checks = {
        "anonymous_line_holds_the_fitting_atomic_box": (
            fit.get("outcome") == "placed"
            and observed["fit"]["p_lines"] == 0
            and str(fit_owner.get("id") or "").startswith("anon-")
            and fit_owner.get("w") == 200
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
            and observed["fit"]["sib_line"] == {
                "text": "DD",
                "x": 40,
                "y": 10,
                "h": 10,
                "w": 20,
                "runs": None,
                "atoms": None,
            }
            and observed["fit"]["sib"]["y"] == 10
            and observed["fit"]["next"]["y"] == 20
            and observed["fit"]["p"]["h"] == 20
        ),
        "wide_atomic_box_drops_and_the_sibling_follows": (
            drop.get("outcome") == "placed"
            and drop_line["text"] == "AA"
            and drop_line["x"] == 40
            and drop_line["y"] == 0
            and observed["drop"]["atom"] == {"x": 0, "y": 20, "w": 180, "h": 10}
            and observed["drop"]["sib"]["y"] == 30
            and observed["drop"]["sib_line"]["x"] == 0
            and observed["drop"]["sib_line"]["y"] == 30
            and observed["drop"]["next"]["y"] == 40
        ),
        "right_float_leaves_the_atomic_box_at_the_line_start": (
            right.get("outcome") == "placed"
            and observed["right"]["line"]["x"] == 0
            and observed["right"]["line"]["text"] == "AACC"
            and observed["right"]["atom"] == {"x": 20, "y": 0, "w": 20, "h": 10}
            and observed["right"]["f"]["x"] == 160
            and observed["right"]["sib"]["y"] == 10
            and observed["right"]["sib_line"]["x"] == 0
            and observed["right"]["next"]["y"] == 20
        ),
        "shaped_float_stays_invalid": shaped.get("outcome") == "invalid" and shaped.get("boxes") is None,
        "taller_atomic_box_stays_invalid": tall.get("outcome") == "invalid" and tall.get("boxes") is None,
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
