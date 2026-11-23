"""Draw a normal-flow line with the CSS font face that covers each character.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects @font-face reports passed false.
"""

from __future__ import annotations

import json

_FALLBACK = (
    "<div id='page'>AB字☺</div>",
    """
    @font-face { font-family: Latin; font-weight: 400; unicode-range: U+0041-005A; }
    @font-face { font-family: Han; font-weight: 400; unicode-range: U+5B57; }
    #page { font-family: Latin, Han; font-size: 10px; width: 200px; }
    """,
)
_WEIGHT = (
    "<div id='host'><div id='regular'>AB</div><div id='heavy'>CD</div></div>",
    """
    @font-face { font-family: Pair; font-weight: 400; }
    @font-face { font-family: Pair; font-weight: 700; }
    #host { font-family: Pair; font-weight: 400; font-size: 10px; }
    #regular, #heavy { width: 80px; }
    #heavy { font-weight: 700; }
    """,
)
_PLAIN = (
    "<div id='page'>AB</div>",
    "#page { font-size: 10px; width: 40px; }",
)


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


def _runs(line: dict[str, object] | None) -> list[dict[str, object]]:
    if line is None or not isinstance(line.get("runs"), list):
        return []
    return [item for item in line["runs"] if isinstance(item, dict)]


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _faces(line: dict[str, object] | None) -> list[dict[str, object]]:
    return [{"text": run.get("text"), "font_face": run.get("font_face")} for run in _runs(line)]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    fallback = _lay(layout_normal_flow, *_FALLBACK)
    weight = _lay(layout_normal_flow, *_WEIGHT)
    plain = _lay(layout_normal_flow, *_PLAIN)
    fallback_line = _line(_box(fallback.get("boxes"), "page"))
    regular_line = _line(_box(weight.get("boxes"), "regular"))
    heavy_line = _line(_box(weight.get("boxes"), "heavy"))
    plain_line = _line(_box(plain.get("boxes"), "page"))
    fallback_faces = _faces(fallback_line)
    observed: dict[str, object] = {
        "fallback_outcome": fallback.get("outcome"),
        "fallback_reason": fallback.get("reason"),
        "fallback_text": None if fallback_line is None else fallback_line.get("text"),
        "fallback_faces": fallback_faces,
        "regular_face": _faces(regular_line),
        "heavy_face": _faces(heavy_line),
        "plain_outcome": plain.get("outcome"),
        "plain_text": None if plain_line is None else plain_line.get("text"),
        "plain_has_face": any("font_face" in run for run in _runs(plain_line)),
    }
    passed = (
        fallback.get("outcome") == "placed"
        and fallback_line is not None
        and fallback_line.get("text") == "AB字☺"
        and fallback_faces
        == [
            {"text": "AB", "font_face": "Latin/400/normal"},
            {"text": "字", "font_face": "Han/400/normal"},
            {"text": "☺", "font_face": None},
        ]
        and weight.get("outcome") == "placed"
        and _faces(regular_line) == [{"text": "AB", "font_face": "Pair/400/normal"}]
        and _faces(heavy_line) == [{"text": "CD", "font_face": "Pair/700/normal"}]
        and plain.get("outcome") == "placed"
        and plain_line is not None
        and plain_line.get("text") == "AB"
        and observed["plain_has_face"] is False
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
