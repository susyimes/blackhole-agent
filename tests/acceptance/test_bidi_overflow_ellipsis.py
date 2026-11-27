"""Physical paint and source carets for the W3C CSS Overflow 3 section 5.1 examples."""

import json

from blackhole_agent.css_normal_flow import element_from_document, layout_normal_flow


WORD = "שלום 123456"
ELLIPSIS = "text-overflow: ellipsis;"


def sample(text, *, width=90, direction="ltr", overflow="hidden", style=ELLIPSIS, points=()):
    markup = f"<div id='label' dir='{direction}'>{text}</div><div id='after'>Z</div>"
    css = f"#label {{ width:{width}px; font-size:10px; white-space:pre; overflow:{overflow}; {style} }}"
    result = layout_normal_flow(markup, css, viewport_width=width)
    if result["outcome"] != "placed":
        return {"error": result["reason"]}
    boxes = {box["id"]: box for box in result["boxes"]}
    lines = boxes["label"]["lines"]
    hits = [element_from_document(markup, css, x, 5, viewport_width=width) for x in points]
    return {
        "paint": ["".join(g["ch"] for g in row["glyphs"]) if "glyphs" in row else row["text"] for row in lines],
        "cells": [[(g["x"], g["width"]) for g in row.get("glyphs", [])] for row in lines],
        "layout": [(row["text"], row["x"], row["y"], row["content_width"], row["height"]) for row in lines],
        "after_y": boxes["after"]["y"],
        "hits": [(hit.get("id"), hit.get("caret")) for hit in hits],
    }


def observe():
    observed = {}
    checks = []
    # The reference strings below are in physical left-to-right paint order.
    for direction, expected, origin, mark_x, offsets in (
        ("ltr", "123456 ם…", 0, 80, (3, 2)),
        ("rtl", "…456 םולש", -20, 0, (7, 8)),
    ):
        points = (mark_x + 1, mark_x + 9)
        label = sample(WORD, direction=direction, points=points)
        control = sample(WORD, direction=direction, points=points, style="text-overflow:clip;")
        observed[direction] = label
        checks.extend((
            label.get("paint") == [expected],
            label.get("cells") == [[(x, 10) for x in range(0, 90, 10)]],
            label.get("layout") == control.get("layout") == [(WORD, origin, 0, 110, 10)],
            label.get("after_y") == control.get("after_y") == 10,
            label.get("hits") == control.get("hits") == [("label", {"line": 0, "offset": i}) for i in offsets],
        ))
    cases = (
        ("exact_fit", "ABCDE", 50, "hidden", ELLIPSIS, ["ABCDE"]),
        ("visible", "ABCDEFG", 50, "visible", ELLIPSIS, ["ABCDEFG"]),
        ("default_clip", "ABCDEFG", 50, "hidden", "", ["ABCDEFG"]),
        ("css_direction", WORD, 90, "hidden", ELLIPSIS + "direction:rtl;", ["…456 םולש"]),
        ("each_line", "ABCDE\nOK\nVWXYZ", 30, "auto", ELLIPSIS, ["AB…", "OK", "VW…"]),
        ("whole_cluster", "Ae\u0301🇫🇷XYZ", 40, "clip", ELLIPSIS, ["Ae\u0301…"]),
        ("first_cell", "ABC", 5, "hidden", ELLIPSIS, ["A"]),
        ("start_edge_only", "ABCDEFG", 50, "scroll", ELLIPSIS + "text-align:right;", ["ABCDEFG"]),
    )
    for name, text, width, overflow, style, expected in cases:
        result = sample(text, width=width, overflow=overflow, style=style)
        observed[name] = result.get("paint", result)
        checks.append(observed[name] == expected and result.get("after_y") == 10 * len(expected))
    padded = sample("ABCDEFG", width=40, style=ELLIPSIS + "padding-left:7px;")
    observed["padded_cells"] = padded.get("cells", padded)
    checks.append(observed["padded_cells"] == [[(7, 10), (17, 10), (27, 10), (37, 10)]] and padded["paint"] == ["ABC…"])
    return {"passed": all(checks), "observed": observed}


if __name__ == "__main__":
    print(json.dumps(observe()))
