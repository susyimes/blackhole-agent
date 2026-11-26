"""Size an in-flow replaced image from its CSS aspect-ratio.

A plain ratio replaces the intrinsic ratio. ``auto`` with a ratio keeps the
intrinsic ratio when the attributes supply one. A specified height stays
specified, and a maximum clamps only the automatic axis. An absolute image
uses that same ratio and leaves the following block at its static position.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_RESET = "#page, #photo, #clip, #box, #next, #abs { margin: 0px; }"
_PHOTO = (
    '<div id="page"><img id="photo" width="400" height="200">'
    '<div id="next"></div></div>'
)
_BARE = '<div id="page"><img id="photo"><div id="next"></div></div>'
_VIDEO = (
    '<div id="page"><video id="clip" width="400" height="200"></video>'
    '<div id="next"></div></div>'
)
_BLOCK = '<div id="page"><div id="box"></div><div id="next"></div></div>'
_ABS = (
    '<div id="page"><img id="abs" width="400" height="200">'
    '<div id="next"></div></div>'
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _edge(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "border_height": box.get("border_height"),
    }


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "square": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET + "#photo { display: block; width: 100px; height: auto; aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "defer": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET + "#photo { display: block; width: 100px; height: auto; aspect-ratio: auto 1 / 1; } #next { height: 10px; }",
        ),
        "bare": _lay(
            layout_normal_flow,
            _BARE,
            _RESET + "#photo { display: block; width: 80px; height: auto; aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "intrinsic": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET + "#photo { display: block; width: 100px; height: auto; } #next { height: 10px; }",
        ),
        "both_auto": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET + "#photo { display: block; aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "specified": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET + "#photo { display: block; width: 100px; height: 40px; aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "capped": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET
            + "#photo { display: block; width: 100px; height: auto; aspect-ratio: 1 / 1; max-height: 40px; } #next { height: 10px; }",
        ),
        "video": _lay(
            layout_normal_flow,
            _VIDEO,
            _RESET + "#clip { display: block; width: 100px; height: auto; aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "block": _lay(
            layout_normal_flow,
            _BLOCK,
            _RESET + "#box { width: 100px; aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "absolute": _lay(
            layout_normal_flow,
            _ABS,
            _RESET
            + "#abs { position: absolute; left: 0px; top: 0px; width: 100px; height: auto; aspect-ratio: 1 / 1; }"
            + " #next { height: 10px; }",
        ),
    }
    observed: dict[str, object] = {}
    edges: dict[str, tuple[dict[str, object] | None, dict[str, object] | None]] = {}
    for name, placed in cases.items():
        boxes = placed.get("boxes")
        photo_id = "clip" if name == "video" else "box" if name == "block" else "abs" if name == "absolute" else "photo"
        photo = _box(boxes, photo_id)
        nxt = _box(boxes, "next")
        edges[name] = (photo, nxt)
        observed[name] = {
            "outcome": placed.get("outcome"),
            "reason": placed.get("reason"),
            "box": _edge(photo),
            "next": _edge(nxt),
        }

    def sized(name: str, **expected: object) -> bool:
        photo, nxt = edges[name]
        return (
            cases[name].get("outcome") == "placed"
            and _near(photo, **expected)
            and nxt is not None
            and nxt.get("y") == expected.get("content_height")
        )

    checks = {
        "square_replaces_the_intrinsic_ratio": sized(
            "square", x=0, y=0, content_width=100, content_height=100, border_height=100
        ),
        "auto_ratio_keeps_the_intrinsic_ratio": sized(
            "defer", x=0, y=0, content_width=100, content_height=50, border_height=50
        ),
        "missing_intrinsic_uses_the_specified_ratio": sized(
            "bare", x=0, y=0, content_width=80, content_height=80, border_height=80
        ),
        "omitted_property_keeps_the_intrinsic_rectangle": sized(
            "intrinsic", x=0, y=0, content_width=100, content_height=50, border_height=50
        ),
        "both_automatic_axes_keep_both_intrinsic_dimensions": sized(
            "both_auto", x=0, y=0, content_width=400, content_height=200, border_height=200
        ),
        "specified_height_stays_specified": sized(
            "specified", x=0, y=0, content_width=100, content_height=40, border_height=40
        ),
        "maximum_clamps_only_the_automatic_axis": sized(
            "capped", x=0, y=0, content_width=100, content_height=40, border_height=40
        ),
        "video_uses_the_same_preferred_ratio": sized(
            "video", x=0, y=0, content_width=100, content_height=100, border_height=100
        ),
        "non_replaced_block_still_transfers": sized(
            "block", x=0, y=0, content_width=100, content_height=100, border_height=100
        ),
        "absolute_image_uses_the_preferred_ratio": cases["absolute"].get("outcome") == "placed"
        and _near(
            edges["absolute"][0], x=0, y=0, content_width=100, content_height=100, border_height=100
        )
        and edges["absolute"][1] is not None
        and edges["absolute"][1].get("y") == 0,
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
