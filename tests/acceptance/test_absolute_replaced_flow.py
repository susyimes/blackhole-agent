"""Size an absolutely positioned replaced image from its intrinsic box.

Definite insets keep that size. A specified width keeps the ratio. Equal
automatic margins center it. A maximum width shrinks it and keeps the ratio.
object-fit contain maps the concrete object. A fixed image uses the same
size. An inline image with automatic insets keeps the line's static slot.
A sticky image and a vertical writing mode stay invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json

_HOST = (
    '<div id="host"><img id="photo" width="40" height="20"><div id="next"></div></div>'
)
_HOST_CSS = "#host { position: relative; width: 200px; height: 100px; } #next { height: 10px; }"
_INSET = (
    _HOST,
    _HOST_CSS + " #photo { position: absolute; left: 10px; top: 8px; }",
)
_RATIO = (
    _HOST,
    _HOST_CSS + " #photo { position: absolute; left: 0px; top: 0px; width: 80px; height: auto; }",
)
_CENTER = (
    _HOST,
    _HOST_CSS
    + " #photo { position: absolute; left: 0px; right: 0px; top: 0px; bottom: 0px;"
    + " margin-left: auto; margin-right: auto; margin-top: auto; margin-bottom: auto; }",
)
_CLAMP = (
    _HOST,
    _HOST_CSS + " #photo { position: absolute; left: 0px; top: 0px; max-width: 20px; }",
)
_CONTAIN = (
    '<div id="host"><img id="photo" width="400" height="200"><div id="next"></div></div>',
    "#host { position: relative; width: 200px; height: 100px; }"
    " #photo { position: absolute; left: 0px; top: 0px; width: 100px; height: 100px;"
    " object-fit: contain; } #next { height: 10px; }",
)
_FIXED = (
    _HOST,
    "#host { position: relative; width: 200px; height: 100px; }"
    " #photo { position: fixed; left: 4px; top: 6px; } #next { height: 10px; }",
)
_LINE = (
    '<div id="host">AA<img id="photo" width="20" height="10"></div>',
    "#host { font-size: 10px; line-height: 10px; width: 200px; } #photo { position: absolute; }",
)
_RELATIVE = (
    '<img id="photo" width="10" height="10">',
    "#photo { position: sticky; left: 5px; }",
)
_VERTICAL = (
    '<img id="photo" width="40" height="20">',
    "#photo { position: absolute; left: 0px; top: 0px; writing-mode: vertical-rl; }",
)


def _place(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=800)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(result, dict):
        return {"outcome": "error", "reason": "result", "boxes": None}
    return result


def _box(result: dict[str, object], box_id: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == box_id:
            return item
    return None


def _pack(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    packed = {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "margin_left": box.get("margin_left"),
        "margin_right": box.get("margin_right"),
        "margin_top": box.get("margin_top"),
        "margin_bottom": box.get("margin_bottom"),
    }
    if "object" in box:
        packed["object"] = box.get("object")
    return packed


def _line_text(box: dict[str, object] | None) -> str:
    if not isinstance(box, dict):
        return ""
    lines = box.get("lines")
    if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
        return ""
    return str(lines[0].get("text") or "")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    inset = _place(layout_normal_flow, *_INSET)
    ratio = _place(layout_normal_flow, *_RATIO)
    center = _place(layout_normal_flow, *_CENTER)
    clamp = _place(layout_normal_flow, *_CLAMP)
    contain = _place(layout_normal_flow, *_CONTAIN)
    fixed = _place(layout_normal_flow, *_FIXED)
    line = _place(layout_normal_flow, *_LINE)
    relative = _place(layout_normal_flow, *_RELATIVE)
    vertical = _place(layout_normal_flow, *_VERTICAL)
    photo = _box(inset, "photo")
    nxt = _box(inset, "next")
    ratio_photo = _box(ratio, "photo")
    centered = _box(center, "photo")
    center_next = _box(center, "next")
    clamped = _box(clamp, "photo")
    fitted = _box(contain, "photo")
    contain_next = _box(contain, "next")
    pinned = _box(fixed, "photo")
    fixed_next = _box(fixed, "next")
    slotted = _box(line, "photo")
    host = _box(line, "host")
    observed = {
        "inset": _pack(photo),
        "inset_next_y": None if nxt is None else nxt.get("y"),
        "ratio": _pack(ratio_photo),
        "center": _pack(centered),
        "center_next_y": None if center_next is None else center_next.get("y"),
        "clamp": _pack(clamped),
        "contain": _pack(fitted),
        "contain_next_y": None if contain_next is None else contain_next.get("y"),
        "fixed": _pack(pinned),
        "fixed_next_y": None if fixed_next is None else fixed_next.get("y"),
        "line": _pack(slotted),
        "line_text": _line_text(host),
        "line_height": None if host is None else host.get("content_height"),
        "relative_outcome": relative.get("outcome"),
        "relative_reason": relative.get("reason"),
        "vertical_outcome": vertical.get("outcome"),
        "vertical_reason": vertical.get("reason"),
    }
    passed = (
        inset.get("outcome") == "placed"
        and photo is not None
        and photo.get("x") == 10
        and photo.get("y") == 8
        and photo.get("content_width") == 40
        and photo.get("content_height") == 20
        and nxt is not None
        and nxt.get("y") == 0
        and ratio.get("outcome") == "placed"
        and ratio_photo is not None
        and ratio_photo.get("content_width") == 80
        and ratio_photo.get("content_height") == 40
        and ratio_photo.get("x") == 0
        and ratio_photo.get("y") == 0
        and center.get("outcome") == "placed"
        and centered is not None
        and centered.get("content_width") == 40
        and centered.get("content_height") == 20
        and centered.get("x") == 80
        and centered.get("y") == 40
        and centered.get("margin_left") == 80
        and centered.get("margin_right") == 80
        and center_next is not None
        and center_next.get("y") == 0
        and clamp.get("outcome") == "placed"
        and clamped is not None
        and clamped.get("content_width") == 20
        and clamped.get("content_height") == 10
        and contain.get("outcome") == "placed"
        and fitted is not None
        and fitted.get("content_width") == 100
        and fitted.get("content_height") == 100
        and fitted.get("object") == {"x": 0, "y": 25, "width": 100, "height": 50}
        and contain_next is not None
        and contain_next.get("y") == 0
        and fixed.get("outcome") == "placed"
        and pinned is not None
        and pinned.get("x") == 4
        and pinned.get("y") == 6
        and pinned.get("content_width") == 40
        and pinned.get("content_height") == 20
        and fixed_next is not None
        and fixed_next.get("y") == 0
        and line.get("outcome") == "placed"
        and slotted is not None
        and slotted.get("x") == 20
        and slotted.get("y") == 0
        and slotted.get("content_width") == 20
        and slotted.get("content_height") == 10
        and _line_text(host) == "AA"
        and host is not None
        and host.get("content_height") == 10
        and relative.get("outcome") == "invalid"
        and relative.get("reason") == "positioned replaced element is unsupported"
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "replaced writing mode is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
