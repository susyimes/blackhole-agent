"""Skip the contents of a block with content-visibility hidden.

On a marginless page at 10px font and line-height, HELLO is one 10px line and
the next block starts at y 10. content-visibility hidden drops that line, so
the next block starts at y 0. A 20px height stays and is the hit target. A
40px contain-intrinsic-block-size is the empty content height, and the same
length on a visible box does not move the line. Padding remains. auto,
visible, and an omitted property keep the 10px line. A vertical box, an
inline, a negative length, and an unknown visibility value are rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_BASE = "html, body, div, span { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_PAGE = '<div id="page"><div id="skip">HELLO</div><div id="next">Z</div></div>'
_KID = '<div id="page"><div id="skip"><div id="kid">HELLO</div></div><div id="next">Z</div></div>'
_INLINE = '<div id="page"><div id="copy">A<span id="s">B</span></div><div id="next">Z</div></div>'


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line_text(box: dict[str, object] | None) -> str | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    if not isinstance(line, dict):
        return None
    text = line.get("text")
    return text if isinstance(text, str) else None


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _hit(find, markup: str, stylesheet: str, x: int, y: int) -> dict[str, object]:
    try:
        found = find(markup, stylesheet, x, y, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised hit is an unmet outcome
        return {"outcome": "error", "id": None, "reason": f"{type(exc).__name__}: {exc}"}
    return found if isinstance(found, dict) else {"outcome": "error", "id": None, "reason": "hit is invalid"}


def _spot(placed: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(placed.get("boxes"), ident)
    if box is None:
        return None
    lines = box.get("lines")
    return {
        "y": box.get("y"),
        "content_height": box.get("content_height"),
        "border_height": box.get("border_height"),
        "line_count": len(lines) if isinstance(lines, list) else None,
        "text": _line_text(box),
    }


def _invalid(placed: dict[str, object], reason: str) -> bool:
    return placed.get("outcome") == "invalid" and placed.get("reason") == reason


def _kept(spot: dict[str, object] | None, y: int) -> bool:
    return (
        spot is not None
        and spot.get("y") == 0
        and spot.get("content_height") == 10
        and spot.get("border_height") == 10
        and spot.get("text") == "HELLO"
        and spot.get("line_count") == 1
        and y == 10
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import element_from_document, layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "omitted": _BASE + "#skip { }\n",
        "visible": _BASE + "#skip { content-visibility: visible; }\n",
        "auto": _BASE + "#skip { content-visibility: auto; }\n",
        "hidden": _BASE + "#skip { content-visibility: hidden; }\n",
        "fixed": _BASE + "#skip { content-visibility: hidden; height: 20px; }\n",
        "intrinsic": _BASE + "#skip { content-visibility: hidden; contain-intrinsic-block-size: 40px; }\n",
        "visible_intrinsic": _BASE + "#skip { content-visibility: visible; contain-intrinsic-block-size: 40px; }\n",
        "padding": _BASE + "#skip { content-visibility: hidden; padding: 4px 0px; }\n",
        "none_size": _BASE + "#skip { content-visibility: hidden; contain-intrinsic-block-size: none; }\n",
        "flow": _BASE + "#skip { display: flow-root; content-visibility: hidden; }\n",
        "shorthand": _BASE + "#skip { content-visibility: hidden; contain-intrinsic-size: 10px 40px; }\n",
    }
    placed = {name: _lay(layout_normal_flow, _PAGE, css) for name, css in cases.items()}
    kid_css = _BASE + "#skip { content-visibility: hidden; height: 20px; }\n"
    kid = _lay(layout_normal_flow, _KID, kid_css)
    vertical = _lay(
        layout_normal_flow,
        _PAGE,
        _BASE + "#skip { height: 80px; writing-mode: vertical-rl; content-visibility: hidden; }\n",
    )
    inline = _lay(layout_normal_flow, _INLINE, _BASE + "#s { content-visibility: hidden; }\n")
    bad_visibility = _lay(layout_normal_flow, _PAGE, _BASE + "#skip { content-visibility: none; }\n")
    bad_size = _lay(
        layout_normal_flow,
        _PAGE,
        _BASE + "#skip { contain-intrinsic-block-size: -1px; }\n",
    )
    hidden_hit = _hit(element_from_document, _PAGE, cases["hidden"], 4, 4)
    fixed_hit = _hit(element_from_document, _PAGE, cases["fixed"], 4, 5)
    kid_hit = _hit(element_from_document, _KID, kid_css, 4, 5)

    spots = {name: _spot(item, "skip") for name, item in placed.items()}
    followers = {name: _spot(item, "next") for name, item in placed.items()}
    observed: dict[str, object] = {
        "skip": spots,
        "next": {name: None if item is None else item.get("y") for name, item in followers.items()},
        "kid_skip": _spot(kid, "skip"),
        "kid_next_y": None if _spot(kid, "next") is None else _spot(kid, "next").get("y"),
        "hidden_hit": {"id": hidden_hit.get("id"), "caret": hidden_hit.get("caret"), "outcome": hidden_hit.get("outcome")},
        "fixed_hit": {"id": fixed_hit.get("id"), "caret": "caret" in fixed_hit, "outcome": fixed_hit.get("outcome")},
        "kid_hit": {"id": kid_hit.get("id"), "outcome": kid_hit.get("outcome")},
        "vertical": vertical.get("reason"),
        "inline": inline.get("reason"),
        "bad_visibility": bad_visibility.get("reason"),
        "bad_size": bad_size.get("reason"),
    }
    hidden = spots["hidden"]
    fixed = spots["fixed"]
    intrinsic = spots["intrinsic"]
    padding = spots["padding"]
    shorthand = spots["shorthand"]
    passed = (
        all(item.get("outcome") == "placed" for item in placed.values())
        and _kept(spots["omitted"], followers["omitted"].get("y") if followers["omitted"] else -1)
        and _kept(spots["visible"], followers["visible"].get("y") if followers["visible"] else -1)
        and _kept(spots["auto"], followers["auto"].get("y") if followers["auto"] else -1)
        and _kept(spots["visible_intrinsic"], followers["visible_intrinsic"].get("y") if followers["visible_intrinsic"] else -1)
        and hidden is not None
        and hidden.get("content_height") == 0
        and hidden.get("border_height") == 0
        and hidden.get("line_count") == 0
        and followers["hidden"] is not None
        and followers["hidden"].get("y") == 0
        and fixed is not None
        and fixed.get("content_height") == 20
        and fixed.get("border_height") == 20
        and fixed.get("line_count") == 0
        and followers["fixed"] is not None
        and followers["fixed"].get("y") == 20
        and intrinsic is not None
        and intrinsic.get("content_height") == 40
        and intrinsic.get("border_height") == 40
        and intrinsic.get("line_count") == 0
        and followers["intrinsic"] is not None
        and followers["intrinsic"].get("y") == 40
        and padding is not None
        and padding.get("content_height") == 0
        and padding.get("border_height") == 8
        and followers["padding"] is not None
        and followers["padding"].get("y") == 8
        and spots["none_size"] is not None
        and spots["none_size"].get("content_height") == 0
        and followers["none_size"] is not None
        and followers["none_size"].get("y") == 0
        and spots["flow"] is not None
        and spots["flow"].get("content_height") == 0
        and followers["flow"] is not None
        and followers["flow"].get("y") == 0
        and shorthand is not None
        and shorthand.get("content_height") == 40
        and followers["shorthand"] is not None
        and followers["shorthand"].get("y") == 40
        and kid.get("outcome") == "placed"
        and _spot(kid, "skip") is not None
        and _spot(kid, "skip").get("content_height") == 20
        and _spot(kid, "next") is not None
        and _spot(kid, "next").get("y") == 20
        and hidden_hit.get("outcome") == "hit"
        and hidden_hit.get("id") == "next"
        and fixed_hit.get("outcome") == "hit"
        and fixed_hit.get("id") == "skip"
        and "caret" not in fixed_hit
        and kid_hit.get("outcome") == "hit"
        and kid_hit.get("id") == "skip"
        and "caret" not in kid_hit
        and _invalid(vertical, "content-visibility writing mode is unsupported")
        and _invalid(inline, "content-visibility display is unsupported")
        and _invalid(bad_visibility, "content-visibility is invalid")
        and _invalid(bad_size, "contain-intrinsic-block-size is invalid")
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
