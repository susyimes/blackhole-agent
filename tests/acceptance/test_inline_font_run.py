"""Place each inline run at its own font size and line height.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects an inline font size exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_WIDE = '<p id="copy">Hi <b id="big">BIG</b> end</p>'
_WIDE_CSS = """
#copy { font-size: 10px; line-height: 20px; }
#big { font-size: 20px; line-height: 40px; }
"""

_STRUT = '<p id="short">Go <b id="tiny">NOW</b></p>'
_STRUT_CSS = """
#short { font-size: 10px; line-height: 20px; }
#tiny { line-height: 10px; }
"""

_ALIGN = '<p id="bad">Hi <b id="shift">BIG</b></p>'
_ALIGN_CSS = """
#bad { font-size: 10px; }
#shift { font-size: 20px; text-align: center; }
"""

_FLOAT = '<p id="mix"><b id="big">BIG</b><i id="pin">X</i> tail</p>'
_FLOAT_CSS = """
#mix { font-size: 10px; line-height: 20px; }
#big { font-size: 20px; }
#pin { float: left; }
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
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    wide = _lay(layout_normal_flow, _WIDE, _WIDE_CSS, 400)
    narrow = _lay(layout_normal_flow, _WIDE, _WIDE_CSS, 70)
    strut = _lay(layout_normal_flow, _STRUT, _STRUT_CSS, 200)
    aligned = _lay(layout_normal_flow, _ALIGN, _ALIGN_CSS, 200)
    floated = _lay(layout_normal_flow, _FLOAT, _FLOAT_CSS, 200)

    wide_box = _box(wide.get("boxes"), "copy")
    narrow_box = _box(narrow.get("boxes"), "copy")
    strut_box = _box(strut.get("boxes"), "short")
    wide_line = _line(wide_box, 0)
    narrow_lines = [_line(narrow_box, index) for index in range(3)]
    strut_line = _line(strut_box, 0)
    observed: dict[str, object] = {
        "wide_outcome": wide.get("outcome"),
        "wide_reason": wide.get("reason"),
        "wide_height": wide_box.get("content_height") if isinstance(wide_box, dict) else None,
        "wide_line": _compact(wide_line),
        "narrow_outcome": narrow.get("outcome"),
        "narrow_height": narrow_box.get("content_height") if isinstance(narrow_box, dict) else None,
        "narrow_lines": [_compact(line) for line in narrow_lines],
        "strut_outcome": strut.get("outcome"),
        "strut_height": strut_box.get("content_height") if isinstance(strut_box, dict) else None,
        "strut_line": _compact(strut_line),
        "align_outcome": aligned.get("outcome"),
        "align_reason": aligned.get("reason"),
        "float_outcome": floated.get("outcome"),
        "float_reason": floated.get("reason"),
    }
    checks = {
        "wide": (
            wide.get("outcome") == "placed"
            and _near(wide_box, content_height=40)
            and _near(
                wide_line,
                text="Hi BIG end",
                x=0,
                y=0,
                height=40,
                content_width=130,
                runs=[
                    {"text": "Hi ", "x": 0, "font_size": 10, "width": 30},
                    {"text": "BIG", "x": 30, "font_size": 20, "width": 60},
                    {"text": " end", "x": 90, "font_size": 10, "width": 40},
                ],
            )
            and isinstance(wide_box, dict)
            and isinstance(wide_box.get("lines"), list)
            and len(wide_box["lines"]) == 1
        ),
        "narrow": (
            narrow.get("outcome") == "placed"
            and _near(narrow_box, content_height=80)
            and _near(
                narrow_lines[0],
                text="Hi",
                x=0,
                y=0,
                height=20,
                content_width=20,
                runs=[{"text": "Hi", "x": 0, "font_size": 10, "width": 20}],
            )
            and _near(
                narrow_lines[1],
                text="BIG",
                x=0,
                y=20,
                height=40,
                content_width=60,
                runs=[{"text": "BIG", "x": 0, "font_size": 20, "width": 60}],
            )
            and _near(
                narrow_lines[2],
                text="end",
                x=0,
                y=60,
                height=20,
                content_width=30,
                runs=[{"text": "end", "x": 0, "font_size": 10, "width": 30}],
            )
        ),
        "strut": (
            strut.get("outcome") == "placed"
            and _near(strut_box, content_height=20)
            and _near(
                strut_line,
                text="Go NOW",
                x=0,
                y=0,
                height=20,
                content_width=60,
                runs=[
                    {"text": "Go ", "x": 0, "font_size": 10, "width": 30},
                    {"text": "NOW", "x": 30, "font_size": 10, "width": 30},
                ],
            )
        ),
        "inline_text_align": (
            aligned.get("outcome") == "invalid"
            and aligned.get("boxes") is None
            and aligned.get("reason") == "inline text-align is unsupported"
        ),
        "float_beside_mixed": (
            floated.get("outcome") == "invalid"
            and floated.get("boxes") is None
            and floated.get("reason") == "inline font beside a float is unsupported"
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
