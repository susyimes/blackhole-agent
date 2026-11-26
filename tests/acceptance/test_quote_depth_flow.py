"""Insert open-quote and close-quote glyphs from the quotes property.

On a marginless page at 10px font and line-height, a q around HI with quotes
A/B becomes the line AHIB and the next block stays at y 10. The omitted
property uses U+201C and U+201D. quotes none leaves HI. An inner q under that
none uses the second pair. display none does not consume a pair. A close at
quotation zero adds nothing. Two opens and two closes produce ACHIDB. A third
quotation repeats the last pair. A 30px line whose quote strings contain
spaces wraps to W, BB, Z and starts the next block at y 30; the same text
without quote keywords stays one line at y 10. An odd list, open-quote(),
vertical-rl, and direction rtl are rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_BASE = "html, body, div, p, q { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_PAGE = '<div id="page"><p id="t">{body}</p><p id="next">Z</p></div>'
_QUOTES = (
    "q::before { content: open-quote; }\n"
    "q::after { content: close-quote; }\n"
)


def _lay(markup: str, stylesheet: str) -> dict[str, object]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    try:
        placed = layout_normal_flow(markup, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _box(placed: dict[str, object], ident: str) -> dict[str, object] | None:
    boxes = placed.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lines(placed: dict[str, object]) -> tuple:
    box = _box(placed, "t")
    if box is None or not isinstance(box.get("lines"), list):
        return ()
    return tuple(
        (line.get("text"), line.get("content_width"), line.get("y"))
        for line in box["lines"]
        if isinstance(line, dict)
    )


def _view(placed: dict[str, object]) -> dict[str, object]:
    nxt = _box(placed, "next")
    box = _box(placed, "t")
    return {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "lines": _lines(placed),
        "height": None if box is None else box.get("content_height"),
        "next_y": None if nxt is None else nxt.get("y"),
    }


def _page(body: str, css: str) -> dict[str, object]:
    return _view(_lay(_PAGE.format(body=body), _BASE + css))


def observe() -> tuple[bool, dict[str, object]]:
    pair = _page("<q>HI</q>", _QUOTES + 'q { quotes: "A" "B"; }\n')
    auto = _page("<q>HI</q>", _QUOTES)
    none = _page("<q>HI</q>", _QUOTES + "q { quotes: none; }\n")
    inner = _page(
        '<q id="outer"><q id="inner">HI</q></q>',
        _QUOTES + 'q { quotes: none; }\n#inner { quotes: "A" "B" "C" "D"; }\n',
    )
    dead = _page(
        '<q id="dead">NO</q><q>HI</q>',
        _QUOTES + 'q { quotes: "A" "B" "C" "D"; }\n#dead { display: none; }\n',
    )
    ignored = _page("HI", '#t::before { content: close-quote; }\n#t { quotes: "A" "B"; }\n')
    doubled = _page(
        "HI",
        "#t::before { content: open-quote open-quote; }\n"
        "#t::after { content: close-quote close-quote; }\n"
        '#t { quotes: "A" "B" "C" "D"; }\n',
    )
    third = _page(
        "<q>1<q>2<q>3</q></q></q>",
        _QUOTES + 'q { quotes: "A" "B" "C" "D"; }\n',
    )
    phantom = _page(
        '<q id="outer">X<q id="inner">HI</q>Y</q>',
        "#outer::before { content: no-open-quote; }\n"
        "#outer::after { content: close-quote; }\n"
        "#inner::before { content: open-quote; }\n"
        "#inner::after { content: close-quote; }\n"
        'q { quotes: "A" "B" "C" "D"; }\n',
    )
    wrapped = _page(
        "<q>BB</q>",
        '#t { width: 30px; }\nq { quotes: "W " " Z"; }\n' + _QUOTES,
    )
    plain = _page("<q>BB</q>", "#t { width: 30px; }\n")
    odd = _page("<q>HI</q>", _QUOTES + 'q { quotes: "A"; }\n')
    paren = _page("<q>HI</q>", "q::before { content: open-quote(); }\n")
    vertical = _page(
        "<q>HI</q>",
        _QUOTES + "#t { writing-mode: vertical-rl; height: 40px; }\n",
    )
    rtl = _page("<q>HI</q>", _QUOTES + "#t { direction: rtl; }\n")

    observed = {
        "pair": pair,
        "auto": auto,
        "none": none,
        "inner": inner,
        "dead": dead,
        "ignored": ignored,
        "doubled": doubled,
        "third": third,
        "phantom": phantom,
        "wrapped": wrapped,
        "plain": plain,
        "odd": odd,
        "paren": paren,
        "vertical": vertical,
        "rtl": rtl,
    }
    placed = {
        "outcome": "placed",
        "reason": None,
    }
    passed = (
        pair == {**placed, "lines": (("AHIB", 40, 0),), "height": 10, "next_y": 10}
        and auto == {**placed, "lines": (("\u201cHI\u201d", 40, 0),), "height": 10, "next_y": 10}
        and none == {**placed, "lines": (("HI", 20, 0),), "height": 10, "next_y": 10}
        and inner == {**placed, "lines": (("CHID", 40, 0),), "height": 10, "next_y": 10}
        and dead == {**placed, "lines": (("AHIB", 40, 0),), "height": 10, "next_y": 10}
        and ignored == {**placed, "lines": (("HI", 20, 0),), "height": 10, "next_y": 10}
        and doubled == {**placed, "lines": (("ACHIDB", 60, 0),), "height": 10, "next_y": 10}
        and third == {**placed, "lines": (("A1C2C3DDB", 90, 0),), "height": 10, "next_y": 10}
        and phantom == {**placed, "lines": (("XCHIDYB", 70, 0),), "height": 10, "next_y": 10}
        and wrapped
        == {
            **placed,
            "lines": (("W", 10, 0), ("BB", 20, 10), ("Z", 10, 20)),
            "height": 30,
            "next_y": 30,
        }
        and plain == {**placed, "lines": (("BB", 20, 0),), "height": 10, "next_y": 10}
        and odd == {"outcome": "invalid", "reason": "quotes is invalid", "lines": (), "height": None, "next_y": None}
        and paren
        == {
            "outcome": "invalid",
            "reason": "generated content is unsupported",
            "lines": (),
            "height": None,
            "next_y": None,
        }
        and vertical
        == {
            "outcome": "invalid",
            "reason": "quote content is unsupported",
            "lines": (),
            "height": None,
            "next_y": None,
        }
        and rtl
        == {
            "outcome": "invalid",
            "reason": "quote content is unsupported",
            "lines": (),
            "height": None,
            "next_y": None,
        }
    )
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
