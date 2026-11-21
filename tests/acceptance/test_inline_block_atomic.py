"""Place an inline-block in the line as one atomic shrink-to-fit box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still stretches the inline-block like a block
exits 0 with passed false.
"""

from __future__ import annotations

import json
import sys

_WIDE = '<p id="row">A<span id="atom">BB</span>C</p>'
_WIDE_CSS = """
#row { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; }
"""

_SPACE = '<p id="row">A <span id="atom">BB</span> C</p>'

_FIT = '<p id="fit"><span id="atom">BB CC</span></p>'
_FIT_CSS = """
#fit { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; }
"""

_TALL = '<p id="tall">A<span id="big">B</span>C</p>'
_TALL_CSS = """
#tall { font-size: 10px; line-height: 10px; }
#big { display: inline-block; font-size: 20px; line-height: 20px; }
"""

_NOWRAP_CSS = """
#row { font-size: 10px; line-height: 10px; white-space: nowrap; }
#atom { display: inline-block; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None, index: int) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list):
        return None
    lines = box["lines"]
    if index >= len(lines) or not isinstance(lines[index], dict):
        return None
    return lines[index]


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, markup: str, stylesheet: str, width: int) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _compact(line: dict[str, object] | None) -> dict[str, object] | None:
    if line is None:
        return None
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "height": line.get("height"),
        "content_width": line.get("content_width"),
        "runs": line.get("runs"),
        "atoms": line.get("atoms"),
    }


def _placed(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "lines": [_compact(line) for line in box["lines"]] if isinstance(box.get("lines"), list) else None,
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    wide = _lay(layout_normal_flow, _WIDE, _WIDE_CSS, 200)
    narrow = _lay(layout_normal_flow, _WIDE, _WIDE_CSS, 25)
    spaced = _lay(layout_normal_flow, _SPACE, _WIDE_CSS, 200)
    fit = _lay(layout_normal_flow, _FIT, _FIT_CSS, 200)
    tall = _lay(layout_normal_flow, _TALL, _TALL_CSS, 200)
    nowrap = _lay(layout_normal_flow, _WIDE, _NOWRAP_CSS, 25)

    wide_row = _box(wide.get("boxes"), "row")
    wide_atom = _box(wide.get("boxes"), "atom")
    narrow_row = _box(narrow.get("boxes"), "row")
    narrow_atom = _box(narrow.get("boxes"), "atom")
    space_row = _box(spaced.get("boxes"), "row")
    space_atom = _box(spaced.get("boxes"), "atom")
    fit_box = _box(fit.get("boxes"), "fit")
    fit_atom = _box(fit.get("boxes"), "atom")
    tall_box = _box(tall.get("boxes"), "tall")
    tall_atom = _box(tall.get("boxes"), "big")
    nowrap_row = _box(nowrap.get("boxes"), "row")
    nowrap_atom = _box(nowrap.get("boxes"), "atom")

    wide_line = _line(wide_row, 0)
    narrow_lines = [_line(narrow_row, index) for index in range(3)]
    space_line = _line(space_row, 0)
    fit_line = _line(fit_box, 0)
    tall_line = _line(tall_box, 0)
    nowrap_line = _line(nowrap_row, 0)
    observed: dict[str, object] = {
        "wide_outcome": wide.get("outcome"),
        "wide_reason": wide.get("reason"),
        "wide_row": _placed(wide_row),
        "wide_atom": _placed(wide_atom),
        "narrow_outcome": narrow.get("outcome"),
        "narrow_row": _placed(narrow_row),
        "narrow_atom": _placed(narrow_atom),
        "space_outcome": spaced.get("outcome"),
        "space_line": _compact(space_line),
        "space_atom": _placed(space_atom),
        "fit_outcome": fit.get("outcome"),
        "fit_atom": _placed(fit_atom),
        "tall_outcome": tall.get("outcome"),
        "tall_line": _compact(tall_line),
        "tall_atom": _placed(tall_atom),
        "nowrap_outcome": nowrap.get("outcome"),
        "nowrap_line": _compact(nowrap_line),
        "nowrap_atom": _placed(nowrap_atom),
    }
    checks = {
        "wide": (
            wide.get("outcome") == "placed"
            and _near(wide_row, content_height=10)
            and _near(
                wide_line,
                text="AC",
                x=0,
                y=0,
                height=10,
                content_width=40,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 20}],
            )
            and _near(wide_atom, x=10, y=0, content_width=20, content_height=10)
            and _near(_line(wide_atom, 0), text="BB", x=10, y=0, height=10, content_width=20)
            and isinstance(wide_row, dict)
            and isinstance(wide_row.get("lines"), list)
            and len(wide_row["lines"]) == 1
        ),
        "narrow": (
            narrow.get("outcome") == "placed"
            and _near(narrow_row, content_height=30)
            and _near(
                narrow_lines[0],
                text="A",
                x=0,
                y=0,
                height=10,
                content_width=10,
                runs=[{"text": "A", "x": 0, "font_size": 10, "width": 10}],
            )
            and _near(
                narrow_lines[1],
                text="",
                x=0,
                y=10,
                height=10,
                content_width=20,
                atoms=[{"id": "atom", "x": 0, "width": 20}],
            )
            and _near(
                narrow_lines[2],
                text="C",
                x=0,
                y=20,
                height=10,
                content_width=10,
                runs=[{"text": "C", "x": 0, "font_size": 10, "width": 10}],
            )
            and _near(narrow_atom, x=0, y=10, content_width=20, content_height=10)
            and isinstance(narrow_row, dict)
            and isinstance(narrow_row.get("lines"), list)
            and len(narrow_row["lines"]) == 3
        ),
        "space": (
            spaced.get("outcome") == "placed"
            and _near(
                space_line,
                text="A  C",
                x=0,
                y=0,
                height=10,
                content_width=60,
                runs=[
                    {"text": "A ", "x": 0, "font_size": 10, "width": 20},
                    {"text": " C", "x": 40, "font_size": 10, "width": 20},
                ],
                atoms=[{"id": "atom", "x": 20, "width": 20}],
            )
            and _near(space_atom, x=20, y=0, content_width=20, content_height=10)
        ),
        "shrink": (
            fit.get("outcome") == "placed"
            and _near(fit_atom, x=0, y=0, content_width=50, content_height=10)
            and _near(_line(fit_atom, 0), text="BB CC", content_width=50)
            and _near(fit_line, text="", content_width=50, height=10, atoms=[{"id": "atom", "x": 0, "width": 50}])
            and isinstance(fit_box, dict)
            and fit_box.get("content_width") == 200
        ),
        "tall": (
            tall.get("outcome") == "placed"
            and _near(tall_box, content_height=20)
            and _near(
                tall_line,
                text="AC",
                x=0,
                y=0,
                height=20,
                content_width=40,
                atoms=[{"id": "big", "x": 10, "width": 20}],
            )
            and _near(tall_atom, x=10, y=0, content_width=20, content_height=20)
        ),
        "nowrap": (
            nowrap.get("outcome") == "placed"
            and _near(nowrap_row, content_width=25, content_height=10)
            and _near(
                nowrap_line,
                text="AC",
                y=0,
                height=10,
                content_width=40,
                atoms=[{"id": "atom", "x": 10, "width": 20}],
            )
            and _near(nowrap_atom, x=10, y=0, content_width=20, content_height=10)
            and isinstance(nowrap_row, dict)
            and isinstance(nowrap_row.get("lines"), list)
            and len(nowrap_row["lines"]) == 1
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
