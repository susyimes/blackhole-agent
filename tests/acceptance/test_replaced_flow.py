"""Place a replaced image in normal flow.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still stretches an image reports passed false.
"""

from __future__ import annotations

import json

_INTRINSIC = (
    '<div id="page"><img id="photo" width="400" height="200"><div id="next"></div></div>',
    "#photo { display: block; } #next { height: 10px; }",
)
_RATIO = (
    '<div id="page"><img id="photo" width="400" height="200"><div id="next"></div></div>',
    "#photo { display: block; width: 100px; height: auto; } #next { height: 10px; }",
)
_CENTER = (
    '<div id="page"><img id="photo" width="100" height="50"></div>',
    "#page { width: 400px; } #photo { display: block; margin-left: auto; margin-right: auto; }",
)
_FALLBACK = (
    '<div id="page"><img id="photo"><div id="next"></div></div>',
    "#photo { display: block; } #next { height: 10px; }",
)
_INLINE = (
    '<div id="page">A<img id="photo" width="20" height="10">B</div>',
    "",
)
_CONTAIN = (
    '<div id="page"><img id="photo" width="400" height="200"></div>',
    "#photo { display: block; width: 100px; height: 100px; object-fit: contain; }",
)
_CHILD = (
    '<video id="bad"><div id="kid"></div></video>',
    "#bad { display: block; width: 40px; height: 10px; }",
)
_PLAIN = (
    '<div id="page"></div>',
    "#page { width: 40px; height: 10px; }",
)


def _place(function, markup: str, stylesheet: str, viewport_width: int) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=viewport_width)
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
    }
    if "object" in box:
        packed["object"] = box.get("object")
    return packed


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    intrinsic = _place(layout_normal_flow, *_INTRINSIC, 800)
    ratio = _place(layout_normal_flow, *_RATIO, 800)
    center = _place(layout_normal_flow, *_CENTER, 800)
    fallback = _place(layout_normal_flow, *_FALLBACK, 800)
    inline = _place(layout_normal_flow, *_INLINE, 200)
    contain = _place(layout_normal_flow, *_CONTAIN, 200)
    child = _place(layout_normal_flow, *_CHILD, 200)
    plain = _place(layout_normal_flow, *_PLAIN, 200)

    photo = _box(intrinsic, "photo")
    nxt = _box(intrinsic, "next")
    ratio_photo = _box(ratio, "photo")
    ratio_next = _box(ratio, "next")
    centered = _box(center, "photo")
    bare = _box(fallback, "photo")
    bare_next = _box(fallback, "next")
    atom = _box(inline, "photo")
    page = _box(inline, "page")
    fitted = _box(contain, "photo")
    plain_page = _box(plain, "page")
    line = None
    if page is not None and isinstance(page.get("lines"), list) and page["lines"]:
        first = page["lines"][0]
        if isinstance(first, dict):
            line = first

    observed: dict[str, object] = {
        "intrinsic": _pack(photo),
        "intrinsic_next_y": None if nxt is None else nxt.get("y"),
        "ratio": _pack(ratio_photo),
        "ratio_next_y": None if ratio_next is None else ratio_next.get("y"),
        "center": _pack(centered),
        "fallback": _pack(bare),
        "fallback_next_y": None if bare_next is None else bare_next.get("y"),
        "inline": _pack(atom),
        "inline_line": None
        if line is None
        else {"text": line.get("text"), "runs": line.get("runs"), "height": line.get("height")},
        "contain": _pack(fitted),
        "child_outcome": child.get("outcome"),
        "child_reason": child.get("reason"),
        "plain": _pack(plain_page),
    }
    runs = line.get("runs") if isinstance(line, dict) else None
    bee = runs[1] if isinstance(runs, list) and len(runs) > 1 and isinstance(runs[1], dict) else None
    passed = (
        intrinsic.get("outcome") == "placed"
        and photo is not None
        and photo.get("content_width") == 400
        and photo.get("content_height") == 200
        and photo.get("margin_left") == 0
        and photo.get("margin_right") == 400
        and photo.get("x") == 0
        and photo.get("y") == 0
        and nxt is not None
        and nxt.get("y") == 200
        and ratio.get("outcome") == "placed"
        and ratio_photo is not None
        and ratio_photo.get("content_width") == 100
        and ratio_photo.get("content_height") == 50
        and ratio_next is not None
        and ratio_next.get("y") == 50
        and center.get("outcome") == "placed"
        and centered is not None
        and centered.get("content_width") == 100
        and centered.get("content_height") == 50
        and centered.get("margin_left") == 150
        and centered.get("margin_right") == 150
        and centered.get("x") == 150
        and fallback.get("outcome") == "placed"
        and bare is not None
        and bare.get("content_width") == 300
        and bare.get("content_height") == 150
        and bare_next is not None
        and bare_next.get("y") == 150
        and inline.get("outcome") == "placed"
        and atom is not None
        and atom.get("content_width") == 20
        and atom.get("content_height") == 10
        and atom.get("x") == 16
        and atom.get("y") == 6
        and isinstance(line, dict)
        and line.get("text") == "AB"
        and line.get("height") == 16
        and bee is not None
        and bee.get("x") == 36
        and contain.get("outcome") == "placed"
        and fitted is not None
        and fitted.get("content_width") == 100
        and fitted.get("content_height") == 100
        and fitted.get("object") == {"x": 0, "y": 25, "width": 100, "height": 50}
        and child.get("outcome") == "invalid"
        and child.get("reason") == "replaced content is unsupported"
        and plain.get("outcome") == "placed"
        and plain_page is not None
        and plain_page.get("content_width") == 40
        and plain_page.get("content_height") == 10
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
