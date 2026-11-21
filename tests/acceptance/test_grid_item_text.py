"""Size grid columns from the text inside their items.

max-content columns stay on the unwrapped line, so BBB starts at x 20.
auto columns then absorb the leftover space in the 200px grid. A 40px
column does not shrink around AA. A 25px column wraps AA BB onto two
lines, and the following block starts under that second line.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects grid item text exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_PAIR = (
    '<div id="page"><div id="grid"><div id="a">AA</div><div id="b">BBB</div></div>'
    '<p id="next">Z</p></div>'
)
_ONE = '<div id="page"><div id="grid"><div id="a">AA</div></div><p id="next">Z</p></div>'
_WRAP = '<div id="page"><div id="grid"><div id="a">AA BB</div></div><p id="next">Z</p></div>'
_MAX = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 200px; grid-template-columns: max-content max-content; }
"""
_AUTO = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 200px; grid-template-columns: auto auto; }
"""
_WIDE = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 200px; grid-template-columns: 40px; }
"""
_NARROW = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 200px; grid-template-columns: 25px; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _placed(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "lines": [
            {"text": line.get("text"), "y": line.get("y")}
            for line in line_list
        ]
        if isinstance((line_list := box.get("lines")), list)
        else None,
    }


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    return [line for line in box["lines"] if isinstance(line, dict)]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    packed = _lay(layout_normal_flow, _PAIR, _MAX)
    stretched = _lay(layout_normal_flow, _PAIR, _AUTO)
    wide = _lay(layout_normal_flow, _ONE, _WIDE)
    narrow = _lay(layout_normal_flow, _WRAP, _NARROW)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    narrow_lines = _lines(take(narrow, "a"))
    wide_lines = _lines(take(wide, "a"))
    observed: dict[str, object] = {
        "packed_outcome": packed.get("outcome"),
        "packed_reason": packed.get("reason"),
        "packed_a": _placed(take(packed, "a")),
        "packed_b": _placed(take(packed, "b")),
        "packed_grid": _placed(take(packed, "grid")),
        "packed_next": _placed(take(packed, "next")),
        "stretch_outcome": stretched.get("outcome"),
        "stretch_reason": stretched.get("reason"),
        "stretch_a": _placed(take(stretched, "a")),
        "stretch_b": _placed(take(stretched, "b")),
        "wide_outcome": wide.get("outcome"),
        "wide_reason": wide.get("reason"),
        "wide_a": _placed(take(wide, "a")),
        "wide_next": _placed(take(wide, "next")),
        "narrow_outcome": narrow.get("outcome"),
        "narrow_reason": narrow.get("reason"),
        "narrow_a": _placed(take(narrow, "a")),
        "narrow_next": _placed(take(narrow, "next")),
    }
    checks = {
        "max_content_column_matches_the_text": (
            packed.get("outcome") == "placed"
            and _near(take(packed, "a"), x=0, y=0, content_width=20, content_height=10)
            and _near(take(packed, "b"), x=20, y=0, content_width=30, content_height=10)
            and _near(take(packed, "grid"), content_width=200, content_height=10)
            and isinstance(take(packed, "next"), dict)
            and take(packed, "next").get("y") == 10
        ),
        "auto_columns_absorb_leftover_space": (
            stretched.get("outcome") == "placed"
            and _near(take(stretched, "a"), x=0, y=0, content_width=95, content_height=10)
            and _near(take(stretched, "b"), x=95, y=0, content_width=105, content_height=10)
            and isinstance(take(stretched, "next"), dict)
            and take(stretched, "next").get("y") == 10
        ),
        "fixed_column_does_not_shrink_to_the_text": (
            wide.get("outcome") == "placed"
            and _near(take(wide, "a"), x=0, y=0, content_width=40, content_height=10)
            and [line.get("text") for line in wide_lines] == ["AA"]
            and isinstance(take(wide, "next"), dict)
            and take(wide, "next").get("y") == 10
        ),
        "narrow_fixed_column_wraps_onto_a_second_line": (
            narrow.get("outcome") == "placed"
            and _near(take(narrow, "a"), x=0, y=0, content_width=25, content_height=20)
            and [line.get("text") for line in narrow_lines] == ["AA", "BB"]
            and isinstance(take(narrow, "next"), dict)
            and take(narrow, "next").get("y") == 20
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
