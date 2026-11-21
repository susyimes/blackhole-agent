"""Place a grid item's margin box inside the track area.

Definite margins shrink a stretched item and enlarge an automatic row.
An auto margin consumes leftover space in a fixed track or a fixed row and
does not enlarge an automatic track. A max-content column grows by a definite
horizontal margin and no further. An item with no margin still stretches.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects grid item margins exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_PAGE = '<div id="page"><div id="grid"><div id="a">AA</div></div><p id="next">Z</p></div>'
_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_COLUMN = "#grid { display: grid; width: 200px; grid-template-columns: 200px; }\n"
_MAX = "#grid { display: grid; width: 200px; grid-template-columns: max-content; }\n"
_ROW = (
    "#grid { display: grid; width: 200px; grid-template-columns: 200px; "
    "grid-template-rows: 40px; }\n"
)


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


def _lay(layout, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(_PAGE, _FONT + stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _placed(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "shrink": _lay(layout_normal_flow, _COLUMN + "#a { margin-left: 10px; margin-right: 30px; }\n"),
        "max_content": _lay(layout_normal_flow, _MAX + "#a { margin-left: 10px; }\n"),
        "auto_start": _lay(layout_normal_flow, _COLUMN + "#a { width: 20px; margin-left: auto; }\n"),
        "auto_both": _lay(
            layout_normal_flow,
            _COLUMN + "#a { width: 20px; margin-left: auto; margin-right: auto; }\n",
        ),
        "top": _lay(layout_normal_flow, _COLUMN + "#a { margin-top: 10px; }\n"),
        "top_auto_row": _lay(layout_normal_flow, _ROW + "#a { height: 10px; margin-top: auto; }\n"),
        "top_auto_flow": _lay(layout_normal_flow, _COLUMN + "#a { margin-top: auto; }\n"),
        "stretch": _lay(layout_normal_flow, _COLUMN),
    }
    observed: dict[str, object] = {
        name: {"outcome": result.get("outcome"), "reason": result.get("reason"), "a": _placed(result, "a"), "next": _placed(result, "next")}
        for name, result in cases.items()
    }
    checks = {
        "definite_margins_shrink_the_stretched_item": (
            cases["shrink"].get("outcome") == "placed"
            and _near(_box(cases["shrink"].get("boxes"), "a"), x=10, y=0, content_width=160, content_height=10)
            and _near(_box(cases["shrink"].get("boxes"), "next"), y=10)
        ),
        "max_content_column_grows_by_the_definite_margin": (
            cases["max_content"].get("outcome") == "placed"
            and _near(_box(cases["max_content"].get("boxes"), "a"), x=10, y=0, content_width=20, content_height=10)
            and _near(_box(cases["max_content"].get("boxes"), "next"), y=10)
        ),
        "auto_margin_consumes_leftover_track_space": (
            cases["auto_start"].get("outcome") == "placed"
            and _near(_box(cases["auto_start"].get("boxes"), "a"), x=180, y=0, content_width=20, content_height=10)
            and _near(_box(cases["auto_start"].get("boxes"), "next"), y=10)
        ),
        "two_auto_margins_split_the_leftover_track": (
            cases["auto_both"].get("outcome") == "placed"
            and _near(_box(cases["auto_both"].get("boxes"), "a"), x=90, y=0, content_width=20)
        ),
        "definite_top_margin_enlarges_the_automatic_row": (
            cases["top"].get("outcome") == "placed"
            and _near(_box(cases["top"].get("boxes"), "a"), x=0, y=10, content_width=200, content_height=10)
            and _near(_box(cases["top"].get("boxes"), "next"), y=20)
        ),
        "auto_top_margin_packs_a_fixed_row_without_moving_the_next_block": (
            cases["top_auto_row"].get("outcome") == "placed"
            and _near(_box(cases["top_auto_row"].get("boxes"), "a"), x=0, y=30, content_width=200, content_height=10)
            and _near(_box(cases["top_auto_row"].get("boxes"), "next"), y=40)
        ),
        "auto_top_margin_does_not_enlarge_an_automatic_row": (
            cases["top_auto_flow"].get("outcome") == "placed"
            and _near(_box(cases["top_auto_flow"].get("boxes"), "a"), x=0, y=0, content_width=200, content_height=10)
            and _near(_box(cases["top_auto_flow"].get("boxes"), "next"), y=10)
        ),
        "an_item_without_a_margin_still_stretches": (
            cases["stretch"].get("outcome") == "placed"
            and _near(_box(cases["stretch"].get("boxes"), "a"), x=0, y=0, content_width=200, content_height=10)
            and _near(_box(cases["stretch"].get("boxes"), "next"), y=10)
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
