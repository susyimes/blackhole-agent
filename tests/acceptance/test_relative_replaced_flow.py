"""Shift a relative replaced image after its line keeps the static slot.

The border box moves by the used left and top. Neighboring glyphs and the
following block stay on the static coordinates. Fallback text is not
generated. A sticky image and a vertical writing mode stay invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json

_PAGE = "#page { font-size: 10px; line-height: 10px; width: 200px; } #next { height: 10px; }"
_IMG = (
    '<div id="page">A<img id="photo" width="20" height="10">B</div><div id="next">Z</div>',
    _PAGE + " #photo { position: relative; left: 6px; top: 4px; }",
)
_CANVAS = (
    '<div id="page">A<canvas id="shot" width="30" height="12">NO</canvas></div><div id="next">Z</div>',
    _PAGE + " #shot { position: relative; left: 8px; }",
)
_VIDEO = (
    '<div id="page">A<video id="clip" width="40" height="10"></video>B</div><div id="next">Z</div>',
    _PAGE + " #clip { position: relative; right: 8px; }",
)
_PAIR = (
    '<div id="page">A<img id="photo" width="20" height="10"></div><div id="next">Z</div>',
    _PAGE + " #photo { position: relative; left: 5px; right: 9px; }",
)
_BLOCK = (
    '<div id="page"><canvas id="shot" width="40" height="20">NO</canvas><div id="next">Z</div></div>',
    "#shot { display: block; position: relative; left: 5px; top: 7px; } #next { height: 10px; }",
)
_IBLOCK = (
    '<div id="page">A<img id="photo" width="20" height="10">B</div><div id="next">Z</div>',
    _PAGE + " #photo { display: inline-block; position: relative; left: 6px; top: 4px; }",
)
_NEST = (
    '<div id="page"><div id="outer">A<img id="photo" width="20" height="10"></div>'
    '<div id="next">Z</div></div>',
    _PAGE + " #outer { position: relative; left: 10px; } #photo { position: relative; left: 4px; }",
)
_STICKY = (
    '<img id="photo" width="10" height="10">',
    "#photo { position: sticky; top: 0px; }",
)
_VERTICAL = (
    '<img id="photo" width="20" height="10">',
    "#photo { position: relative; left: 4px; writing-mode: vertical-rl; }",
)
_HIT = (
    '<div id="page">A<img id="photo" width="20" height="10">B</div>',
    "#page { font-size: 10px; line-height: 10px; width: 200px; } "
    "#photo { position: relative; left: 6px; top: 4px; }",
)


def _place(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=400)
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


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(box, dict):
        return None
    lines = box.get("lines")
    if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
        return None
    return lines[0]


def _runs(box: dict[str, object] | None) -> dict[str, dict[str, object]]:
    line = _line(box)
    found: dict[str, dict[str, object]] = {}
    if line is None or not isinstance(line.get("runs"), list):
        return found
    for run in line["runs"]:
        if isinstance(run, dict) and isinstance(run.get("text"), str):
            found[str(run["text"])] = {"x": run.get("x"), "width": run.get("width")}
    return found


def _slot(box: dict[str, object] | None, atom_id: str) -> int | None:
    line = _line(box)
    if line is None or not isinstance(line.get("atoms"), list):
        return None
    for atom in line["atoms"]:
        if isinstance(atom, dict) and atom.get("id") == atom_id:
            value = atom.get("x")
            return value if isinstance(value, int) else None
    return None


def _texts(result: dict[str, object]) -> list[str]:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return []
    texts: list[str] = []
    for item in boxes:
        if not isinstance(item, dict):
            continue
        lines = item.get("lines")
        if not isinstance(lines, list):
            continue
        for line in lines:
            if isinstance(line, dict) and isinstance(line.get("text"), str):
                texts.append(line["text"])
    return texts


def _hit(function, x: int, y: int) -> dict[str, object]:
    try:
        result = function(*_HIT, x, y, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised hit is an unmet outcome
        return {"outcome": "error", "id": None, "reason": f"{type(exc).__name__}: {exc}"}
    if not isinstance(result, dict):
        return {"outcome": "error", "id": None, "reason": "result"}
    return result


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import element_from_document, layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    image = _place(layout_normal_flow, *_IMG)
    canvas = _place(layout_normal_flow, *_CANVAS)
    video = _place(layout_normal_flow, *_VIDEO)
    pair = _place(layout_normal_flow, *_PAIR)
    block = _place(layout_normal_flow, *_BLOCK)
    iblock = _place(layout_normal_flow, *_IBLOCK)
    nest = _place(layout_normal_flow, *_NEST)
    sticky = _place(layout_normal_flow, *_STICKY)
    vertical = _place(layout_normal_flow, *_VERTICAL)
    on_image = _hit(element_from_document, 18, 6)
    in_gap = _hit(element_from_document, 12, 2)

    page = _box(image, "page")
    photo = _box(image, "photo")
    nxt = _box(image, "next")
    shot_page = _box(canvas, "page")
    shot = _box(canvas, "shot")
    shot_next = _box(canvas, "next")
    clip = _box(video, "clip")
    clip_page = _box(video, "page")
    clip_next = _box(video, "next")
    paired = _box(pair, "photo")
    pair_next = _box(pair, "next")
    block_shot = _box(block, "shot")
    block_next = _box(block, "next")
    atomic = _box(iblock, "photo")
    outer = _box(nest, "outer")
    nested = _box(nest, "photo")
    nest_next = _box(nest, "next")
    image_runs = _runs(page)
    video_runs = _runs(clip_page)
    outer_runs = _runs(outer)

    observed: dict[str, object] = {
        "image": None if photo is None else {"x": photo.get("x"), "y": photo.get("y")},
        "image_slot": _slot(page, "photo"),
        "image_runs": image_runs,
        "image_next_y": None if nxt is None else nxt.get("y"),
        "canvas": None
        if shot is None
        else {
            "x": shot.get("x"),
            "y": shot.get("y"),
            "content_width": shot.get("content_width"),
            "content_height": shot.get("content_height"),
        },
        "canvas_height": None if shot_page is None else shot_page.get("content_height"),
        "canvas_next_y": None if shot_next is None else shot_next.get("y"),
        "canvas_texts": _texts(canvas),
        "video": None if clip is None else {"x": clip.get("x"), "y": clip.get("y")},
        "video_runs": video_runs,
        "video_next_y": None if clip_next is None else clip_next.get("y"),
        "pair": None if paired is None else {"x": paired.get("x"), "y": paired.get("y")},
        "pair_next_y": None if pair_next is None else pair_next.get("y"),
        "block": None if block_shot is None else {"x": block_shot.get("x"), "y": block_shot.get("y")},
        "block_next_y": None if block_next is None else block_next.get("y"),
        "block_texts": _texts(block),
        "inline_block": None if atomic is None else {"x": atomic.get("x"), "y": atomic.get("y")},
        "nest": None if nested is None else {"x": nested.get("x"), "y": nested.get("y")},
        "outer": None if outer is None else {"x": outer.get("x"), "y": outer.get("y")},
        "outer_runs": outer_runs,
        "nest_next_y": None if nest_next is None else nest_next.get("y"),
        "hit": on_image.get("id"),
        "gap": in_gap.get("id"),
        "sticky_reason": sticky.get("reason"),
        "vertical_reason": vertical.get("reason"),
    }
    passed = (
        image.get("outcome") == "placed"
        and photo is not None
        and photo.get("x") == 16
        and photo.get("y") == 4
        and photo.get("content_width") == 20
        and photo.get("content_height") == 10
        and _slot(page, "photo") == 10
        and image_runs.get("A") == {"x": 0, "width": 10}
        and image_runs.get("B") == {"x": 30, "width": 10}
        and nxt is not None
        and nxt.get("y") == 10
        and canvas.get("outcome") == "placed"
        and shot is not None
        and shot.get("x") == 18
        and shot.get("y") == 0
        and shot.get("content_width") == 30
        and shot.get("content_height") == 12
        and shot_page is not None
        and shot_page.get("content_height") == 12
        and shot_next is not None
        and shot_next.get("y") == 12
        and "NO" not in " ".join(_texts(canvas))
        and video.get("outcome") == "placed"
        and clip is not None
        and clip.get("x") == 2
        and clip.get("y") == 0
        and video_runs.get("A") == {"x": 0, "width": 10}
        and video_runs.get("B") == {"x": 50, "width": 10}
        and clip_next is not None
        and clip_next.get("y") == 10
        and pair.get("outcome") == "placed"
        and paired is not None
        and paired.get("x") == 15
        and paired.get("y") == 0
        and pair_next is not None
        and pair_next.get("y") == 10
        and block.get("outcome") == "placed"
        and block_shot is not None
        and block_shot.get("x") == 5
        and block_shot.get("y") == 7
        and block_next is not None
        and block_next.get("y") == 20
        and "NO" not in " ".join(_texts(block))
        and iblock.get("outcome") == "placed"
        and atomic is not None
        and atomic.get("x") == 16
        and atomic.get("y") == 4
        and nest.get("outcome") == "placed"
        and outer is not None
        and outer.get("x") == 10
        and outer_runs.get("A") == {"x": 10, "width": 10}
        and nested is not None
        and nested.get("x") == 24
        and nested.get("y") == 0
        and nest_next is not None
        and nest_next.get("y") == 10
        and on_image.get("outcome") == "hit"
        and on_image.get("id") == "photo"
        and in_gap.get("outcome") == "hit"
        and in_gap.get("id") == "page"
        and sticky.get("outcome") == "invalid"
        and sticky.get("reason") == "positioned replaced element is unsupported"
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "inline-block writing mode is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
