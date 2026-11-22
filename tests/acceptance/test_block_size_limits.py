"""Clamp an automatic horizontal block with min-height and max-height.

A 10px line with min-height 100px grows its border box to 100px. An 80px
child under max-height 40px leaves the parent border at 40px and keeps the
child at its content position. min-height 80px wins over max-height 30px.
min-height 50% of a 200px parent becomes 100px, and the same percentage
inside an automatic parent leaves a 10px line alone. border-box min-height
50px with 30px of vertical padding and border uses a 20px content floor.
A non-zero min-height keeps a child margin from collapsing through, so the
next sibling starts after the used border edge plus the parent's own margin.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_SHARED = "margin:0px;font-size:10px;"


def _place(markup: str, stylesheet: str) -> dict[str, object]:
    from blackhole_agent.css_normal_flow import layout_normal_flow

    placed = layout_normal_flow(markup, stylesheet, viewport_width=400)
    return placed if isinstance(placed, dict) else {"outcome": "error", "boxes": None}


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _case(markup: str, stylesheet: str, *idents: str) -> dict[str, object]:
    placed = _place(markup, stylesheet)
    observed: dict[str, object] = {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
    }
    for ident in idents:
        box = _box(placed.get("boxes"), ident)
        observed[ident] = None if box is None else {
            "y": box.get("y"),
            "border_height": box.get("border_height"),
            "content_height": box.get("content_height"),
        }
    return observed


def observe() -> tuple[bool, dict[str, object]]:
    try:
        grown = _case(
            '<div id="page"><div id="box">A</div><div id="next">Z</div></div>',
            f"#page,#box,#next{{{_SHARED}}}#box{{min-height:100px;}}",
            "box",
            "next",
        )
        clamped = _case(
            '<div id="page"><div id="box"><div id="inner"></div></div><div id="next">Z</div></div>',
            f"#page,#box,#inner,#next{{{_SHARED}}}#box{{max-height:40px;}}#inner{{height:80px;}}",
            "box",
            "inner",
            "next",
        )
        minimum = _case(
            '<div id="page"><div id="box"><div id="inner"></div></div><div id="next">Z</div></div>',
            f"#page,#box,#inner,#next{{{_SHARED}}}#box{{min-height:80px;max-height:30px;}}#inner{{height:100px;}}",
            "box",
            "inner",
            "next",
        )
        percent = _case(
            '<div id="page"><div id="parent"><div id="child"><div id="inner"></div></div></div><div id="next">Z</div></div>',
            f"#page,#parent,#child,#inner,#next{{{_SHARED}}}#parent{{height:200px;}}#child{{min-height:50%;}}#inner{{height:20px;}}",
            "parent",
            "child",
            "next",
        )
        loose = _case(
            '<div id="page"><div id="loose"><div id="kid">A</div></div><div id="after">Z</div></div>',
            f"#page,#loose,#kid,#after{{{_SHARED}}}#kid{{min-height:50%;}}",
            "kid",
            "after",
        )
        border = _case(
            '<div id="page"><div id="box">A</div><div id="next">Z</div></div>',
            f"#page,#box,#next{{{_SHARED}}}#box{{box-sizing:border-box;min-height:50px;padding-top:10px;padding-bottom:10px;border-top-width:5px;border-top-style:solid;border-bottom-width:5px;border-bottom-style:solid;}}",
            "box",
            "next",
        )
        separated = _case(
            '<div id="page"><div id="box"><div id="inner"></div></div><div id="next">Z</div></div>',
            f"#page,#next{{{_SHARED}}}#box{{min-height:100px;margin-bottom:5px;font-size:10px;}}#inner{{height:10px;margin-bottom:30px;font-size:10px;}}",
            "box",
            "inner",
            "next",
        )
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed = {
        "grown": grown,
        "clamped": clamped,
        "minimum": minimum,
        "percent": percent,
        "loose": loose,
        "border": border,
        "separated": separated,
    }
    checks = {
        "grown_box": _metric(grown, "box", "border_height") == 100,
        "grown_next": _metric(grown, "next", "y") == 100,
        "clamped_box": _metric(clamped, "box", "border_height") == 40,
        "clamped_inner": _metric(clamped, "inner", "y") == 0 and _metric(clamped, "inner", "border_height") == 80,
        "clamped_next": _metric(clamped, "next", "y") == 40,
        "minimum_wins": _metric(minimum, "box", "border_height") == 80,
        "minimum_inner": _metric(minimum, "inner", "border_height") == 100,
        "minimum_next": _metric(minimum, "next", "y") == 80,
        "percent_child": _metric(percent, "child", "border_height") == 100,
        "percent_parent": _metric(percent, "parent", "border_height") == 200,
        "percent_next": _metric(percent, "next", "y") == 200,
        "loose_kid": _metric(loose, "kid", "border_height") == 10,
        "loose_after": _metric(loose, "after", "y") == 10,
        "border_box": _metric(border, "box", "border_height") == 50 and _metric(border, "box", "content_height") == 20,
        "border_next": _metric(border, "next", "y") == 50,
        "separated_box": _metric(separated, "box", "border_height") == 100,
        "separated_inner": _metric(separated, "inner", "y") == 0 and _metric(separated, "inner", "border_height") == 10,
        "separated_next": _metric(separated, "next", "y") == 105,
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def _metric(case: dict[str, object], ident: str, field: str) -> object:
    box = case.get(ident)
    if not isinstance(box, dict) or case.get("outcome") != "placed":
        return None
    return box.get(field)


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": bool(passed), "observed": observed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
