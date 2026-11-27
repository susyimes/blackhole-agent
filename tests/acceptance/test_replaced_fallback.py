"""Suppress fallback inside a supporting canvas or video.

The replaced box keeps its used size. Fallback text and elements do not
generate boxes or line text, so the following block or item starts on that
edge. A vertical writing mode and a relative replaced box stay invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json

_BLOCK = (
    '<div id="page"><canvas id="shot" width="40" height="20">FALLBACK'
    '<div id="kid">Hi</div></canvas><div id="next">Z</div></div>',
    "#shot { display: block; } #kid { display: block; height: 100px; } #next { height: 10px; }",
)
_VIDEO = (
    '<div id="page"><video id="clip" width="80" height="30">Hi</video><div id="next">Z</div></div>',
    "#clip { display: block; } #next { height: 10px; }",
)
_INLINE = (
    '<div id="page">A<canvas id="shot" width="20" height="10">QQ</canvas>B</div>',
    "#page { font-size: 10px; line-height: 10px; width: 200px; }",
)
_INLINE_BLOCK = (
    '<div id="page">A<video id="clip" width="30" height="10">Hi</video>B</div>',
    "#page { font-size: 10px; line-height: 10px; width: 200px; } #clip { display: inline-block; }",
)
_FLOAT = (
    '<div id="page"><canvas id="shot" width="40" height="20">FALLBACK</canvas>'
    '<div id="next">Z</div></div>',
    "#page { width: 200px; } #shot { float: left; } #next { height: 10px; }",
)
_ABSOLUTE = (
    '<div id="host"><canvas id="shot" width="40" height="20">FALLBACK</canvas>'
    '<div id="next"></div></div>',
    "#host { position: relative; width: 200px; height: 100px; }"
    " #shot { position: absolute; left: 10px; top: 8px; display: block; } #next { height: 10px; }",
)
_FLEX = (
    '<div id="page"><canvas id="shot" width="40" height="20">FALLBACK'
    '<div id="kid">Hi</div></canvas><div id="next">Z</div></div>',
    "#page { display: flex; width: 200px; } #shot { width: 40px; height: 20px; }"
    " #kid { height: 100px; } #next { width: 30px; height: 10px; }",
)
_GRID = (
    '<div id="page"><canvas id="shot" width="40" height="20">FALLBACK'
    '<div id="kid">Hi</div></canvas><div id="next">Z</div></div>',
    "#page { display: grid; grid-template-columns: 40px 30px; width: 200px; }"
    " #shot { width: 40px; height: 20px; } #kid { height: 100px; } #next { height: 10px; }",
)
_VERTICAL = (
    '<canvas id="shot" width="40" height="20">FALLBACK</canvas>',
    "#shot { display: block; writing-mode: vertical-rl; }",
)
_RELATIVE = (
    '<canvas id="shot" width="20" height="10">QQ</canvas>',
    "#shot { position: relative; }",
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


def _ids(result: dict[str, object]) -> list[str]:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return []
    return [str(item.get("id")) for item in boxes if isinstance(item, dict)]


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


def _pack(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
    }


def _clean(result: dict[str, object], *banned: str) -> bool:
    if any(name in _ids(result) for name in ("kid",)):
        return False
    blob = " ".join(_texts(result))
    return not any(word in blob for word in banned)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    block = _place(layout_normal_flow, *_BLOCK)
    video = _place(layout_normal_flow, *_VIDEO)
    inline = _place(layout_normal_flow, *_INLINE)
    inline_block = _place(layout_normal_flow, *_INLINE_BLOCK)
    floated = _place(layout_normal_flow, *_FLOAT)
    absolute = _place(layout_normal_flow, *_ABSOLUTE)
    flex = _place(layout_normal_flow, *_FLEX)
    grid = _place(layout_normal_flow, *_GRID)
    vertical = _place(layout_normal_flow, *_VERTICAL)
    relative = _place(layout_normal_flow, *_RELATIVE)

    shot = _box(block, "shot")
    nxt = _box(block, "next")
    clip = _box(video, "clip")
    video_next = _box(video, "next")
    atom = _box(inline, "shot")
    inline_page = _box(inline, "page")
    iblock = _box(inline_block, "clip")
    iblock_page = _box(inline_block, "page")
    float_shot = _box(floated, "shot")
    float_next = _box(floated, "next")
    float_page = _box(floated, "page")
    abs_shot = _box(absolute, "shot")
    abs_next = _box(absolute, "next")
    flex_shot = _box(flex, "shot")
    flex_next = _box(flex, "next")
    grid_shot = _box(grid, "shot")
    grid_next = _box(grid, "next")
    inline_line = None
    if inline_page is not None and isinstance(inline_page.get("lines"), list) and inline_page["lines"]:
        first = inline_page["lines"][0]
        if isinstance(first, dict):
            inline_line = first.get("text")
    iblock_line = None
    if iblock_page is not None and isinstance(iblock_page.get("lines"), list) and iblock_page["lines"]:
        first = iblock_page["lines"][0]
        if isinstance(first, dict):
            iblock_line = first.get("text")

    observed: dict[str, object] = {
        "block": _pack(shot),
        "block_next_y": None if nxt is None else nxt.get("y"),
        "block_texts": _texts(block),
        "video": _pack(clip),
        "video_next_y": None if video_next is None else video_next.get("y"),
        "video_texts": _texts(video),
        "inline": _pack(atom),
        "inline_text": inline_line,
        "inline_block": _pack(iblock),
        "inline_block_text": iblock_line,
        "float": _pack(float_shot),
        "float_next_y": None if float_next is None else float_next.get("y"),
        "float_page_height": None if float_page is None else float_page.get("content_height"),
        "absolute": _pack(abs_shot),
        "absolute_next_y": None if abs_next is None else abs_next.get("y"),
        "flex": _pack(flex_shot),
        "flex_next_x": None if flex_next is None else flex_next.get("x"),
        "grid": _pack(grid_shot),
        "grid_next_x": None if grid_next is None else grid_next.get("x"),
        "vertical_reason": vertical.get("reason"),
        "relative_reason": relative.get("reason"),
    }
    passed = (
        block.get("outcome") == "placed"
        and shot is not None
        and shot.get("x") == 0
        and shot.get("y") == 0
        and shot.get("content_width") == 40
        and shot.get("content_height") == 20
        and nxt is not None
        and nxt.get("y") == 20
        and _clean(block, "FALLBACK", "Hi")
        and video.get("outcome") == "placed"
        and clip is not None
        and clip.get("content_width") == 80
        and clip.get("content_height") == 30
        and video_next is not None
        and video_next.get("y") == 30
        and _texts(video) == ["Z"]
        and inline.get("outcome") == "placed"
        and inline_line == "AB"
        and atom is not None
        and atom.get("x") == 10
        and atom.get("content_width") == 20
        and atom.get("content_height") == 10
        and _clean(inline, "QQ")
        and inline_block.get("outcome") == "placed"
        and iblock_line == "AB"
        and iblock is not None
        and iblock.get("x") == 10
        and iblock.get("content_width") == 30
        and iblock.get("content_height") == 10
        and _clean(inline_block, "Hi")
        and floated.get("outcome") == "placed"
        and float_shot is not None
        and float_shot.get("x") == 0
        and float_shot.get("y") == 0
        and float_shot.get("content_width") == 40
        and float_shot.get("content_height") == 20
        and float_next is not None
        and float_next.get("y") == 0
        and float_page is not None
        and float_page.get("content_height") == 20
        and _clean(floated, "FALLBACK")
        and absolute.get("outcome") == "placed"
        and abs_shot is not None
        and abs_shot.get("x") == 10
        and abs_shot.get("y") == 8
        and abs_shot.get("content_width") == 40
        and abs_shot.get("content_height") == 20
        and abs_next is not None
        and abs_next.get("y") == 0
        and _clean(absolute, "FALLBACK")
        and flex.get("outcome") == "placed"
        and flex_shot is not None
        and flex_shot.get("content_width") == 40
        and flex_shot.get("content_height") == 20
        and flex_next is not None
        and flex_next.get("x") == 40
        and _clean(flex, "FALLBACK", "Hi")
        and grid.get("outcome") == "placed"
        and grid_shot is not None
        and grid_shot.get("content_width") == 40
        and grid_shot.get("content_height") == 20
        and grid_next is not None
        and grid_next.get("x") == 40
        and _clean(grid, "FALLBACK", "Hi")
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "replaced writing mode is unsupported"
        and relative.get("outcome") == "invalid"
        and relative.get("reason") == "positioned replaced element is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
