"""Recover original text from two pointer hits on a wrapped paragraph."""

import json

from blackhole_agent.css_normal_flow import element_from_document


def observe():
    source = "A😀   אבא"
    rules = "#p { width: 40px; font-size: 10px; line-height: 10px; }"

    def hit(content, x, y=5, extra="", sibling=""):
        page = f'<div id="page"><div id="p">{content}</div>{sibling}</div>'
        result = element_from_document(page, rules + extra, x, y, viewport_width=200)
        return [result["outcome"], result.get("id"), result.get("caret")]

    def text_hit(line, offset):
        return ["hit", "p", {"line": line, "offset": offset}]

    positions = [(11, 5), (19, 5), (1, 15), (9, 15), (21, 15), (29, 15)]
    wrapped = [hit(source, x, y) for x, y in positions]
    start, end = wrapped[0][2], wrapped[2][2]
    selected = None
    if (
        isinstance(start, dict) and type(start.get("offset")) is int
        and isinstance(end, dict) and type(end.get("offset")) is int
    ):
        raw = source.encode("utf-16-le")
        selected = raw[2 * start["offset"] : 2 * end["offset"]].decode("utf-16-le", "replace")

    float_rules = "#p { width: 80px; direction: rtl; } #f { float: left; width: 20px; height: 10px; }"
    floated = '<div id="f"></div>אב'
    hidden = 'A<b id="skip">😀</b>B'
    cover_rules = "#cover { position: absolute; top: 0px; left: 10px; width: 10px; height: 10px; z-index: 1; }"
    cover = '<div id="cover"></div>'
    observed = {
        "wrapped": wrapped,
        "selected": selected,
        "collapsed_space": [hit("A   B", x) for x in (11, 19)],
        "combining": [hit("e\u0301x", x) for x in (1, 9)],
        "joined_emoji": [hit("👩‍💻", x) for x in (7, 12)],
        "mixed_inline": [hit("a<span>אב</span>b", x) for x in (11, 19, 29, 39)],
        "segment_break": [hit("中\n文", x) for x in (11, 19)],
        "rtl_float": [hit(floated, x, extra=float_rules) for x in (125, 181, 199)],
        "float_with_text": [hit('<div id="f">😀</div>אב', x, extra=float_rules) for x in (181, 199)],
        "hidden_text": [hit(hidden, x, extra="#skip { display: none; }") for x in (9, 11)],
        "covered": hit(source, 11, extra=cover_rules, sibling=cover),
        "through": hit(source, 11, extra=cover_rules + "#cover { pointer-events: none; }", sibling=cover),
        "empty": hit(source, 38, 15),
        "outside": hit(source, 201, 15),
        "generated": [hit("A", x, extra='#p::before { content: "X"; }') for x in (1, 19)],
    }
    expected = {
        "wrapped": [text_hit(0, 1), text_hit(0, 3), text_hit(1, 9), text_hit(1, 8), text_hit(1, 7), text_hit(1, 6)],
        "selected": "😀   אבא",
        "collapsed_space": [text_hit(0, 1), text_hit(0, 4)],
        "combining": [text_hit(0, 0), text_hit(0, 2)],
        "joined_emoji": [text_hit(0, 0), text_hit(0, 5)],
        "mixed_inline": [text_hit(0, 3), text_hit(0, 2), text_hit(0, 1), text_hit(0, 4)],
        "segment_break": [text_hit(0, 2), text_hit(0, 3)],
        "rtl_float": [["hit", "f", None], text_hit(0, 2), text_hit(0, 0)],
        "float_with_text": [text_hit(0, 4), text_hit(0, 2)],
        "hidden_text": [text_hit(0, 1), text_hit(0, 3)],
        "covered": ["hit", "cover", None],
        "through": text_hit(0, 1),
        "empty": ["hit", "p", None],
        "outside": ["miss", None, None],
        "generated": [["hit", "p", None], text_hit(0, 1)],
    }
    return {"passed": observed == expected, "observed": observed}


if __name__ == "__main__":
    print(json.dumps(observe()))
