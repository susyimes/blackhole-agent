"""Apply CSS line-break strictness to horizontal lines.

On a marginless page at font-size 10px and line-height 10px, lang zh text
U+6587 U+301C in a 10px block is two lines and the following block starts
at y 20 when line-break is omitted, normal, or loose, and one line of
content width 20 with the following block at y 10 when line-break is
strict. lang ja text U+3042 U+3083 in a 10px block is one line and the
following block starts at y 10 when line-break is omitted or strict, and
two lines with the following block at y 20 when line-break is loose. Latin
AB in a 10px block is one line of content width 20 and the following block
at y 10 when line-break is omitted, and two lines with the following block
at y 20 when line-break is anywhere. A child without its own declaration
inherits strict. An invalid keyword, a declaration on an inline, and
strict on a vertical or right-to-left box are rejected. A vertical box
that omits the property still lays out.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_BASE = "html, body, div, span { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_WAVE = "\u6587\u301c"
_KANA = "\u3042\u3083"


def _lay(markup: str, css: str) -> dict[str, object]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    try:
        placed = layout_normal_flow(markup, _BASE + css, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(placed, dict):
        return {"outcome": "error", "reason": "layout is invalid", "boxes": None}
    return placed


def _box(placed: dict[str, object], ident: str) -> dict[str, object] | None:
    boxes = placed.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    found = []
    for item in box["lines"]:
        if isinstance(item, dict):
            found.append(
                {
                    "text": item.get("text"),
                    "y": item.get("y"),
                    "width": item.get("content_width"),
                    "height": item.get("height"),
                }
            )
    return found


def _row(markup: str, css: str) -> dict[str, object]:
    placed = _lay(markup, css)
    nxt = _box(placed, "next")
    return {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "lines": _lines(_box(placed, "row")),
        "next_y": None if nxt is None else nxt.get("y"),
    }


def _one(lines: object, text: str, width: int) -> bool:
    return lines == [{"text": text, "y": 0, "width": width, "height": 10}]


def _two(lines: object, first: str, second: str) -> bool:
    return lines == [
        {"text": first, "y": 0, "width": 10, "height": 10},
        {"text": second, "y": 10, "width": 10, "height": 10},
    ]


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def main() -> None:
    wave = f'<div id="row" lang="zh">{_WAVE}</div><div id="next">N</div>'
    kana = f'<div id="row" lang="ja">{_KANA}</div><div id="next">N</div>'
    latin = '<div id="row">AB</div><div id="next">N</div>'
    wave_omitted = _row(wave, "#row { width: 10px; }\n")
    wave_normal = _row(wave, "#row { width: 10px; line-break: normal; }\n")
    wave_loose = _row(wave, "#row { width: 10px; line-break: loose; }\n")
    wave_strict = _row(wave, "#row { width: 10px; line-break: strict; }\n")
    kana_omitted = _row(kana, "#row { width: 10px; }\n")
    kana_strict = _row(kana, "#row { width: 10px; line-break: strict; }\n")
    kana_loose = _row(kana, "#row { width: 10px; line-break: loose; }\n")
    latin_omitted = _row(latin, "#row { width: 10px; }\n")
    latin_anywhere = _row(latin, "#row { width: 10px; line-break: anywhere; }\n")
    inherited = _row(
        f'<div id="host" lang="zh"><div id="row">{_WAVE}</div></div><div id="next">N</div>',
        "#host { line-break: strict; }\n#row { width: 10px; }\n",
    )
    invalid = _row(wave, "#row { width: 10px; line-break: sideways; }\n")
    vertical = _row(wave, "#row { width: 10px; writing-mode: vertical-rl; }\n")
    vertical_strict = _row(wave, "#row { width: 10px; writing-mode: vertical-rl; line-break: strict; }\n")
    rtl_strict = _row(wave, "#row { width: 10px; direction: rtl; line-break: strict; }\n")
    inline = _row(
        f'<div id="row" lang="zh">{_WAVE[0]}<span>{_WAVE[1]}</span></div><div id="next">N</div>',
        "#row { width: 10px; }\n#row span { line-break: strict; }\n",
    )
    checks = {
        "omitted_wavedash_breaks": _two(wave_omitted["lines"], _WAVE[0], _WAVE[1]) and wave_omitted["next_y"] == 20,
        "normal_wavedash_breaks": _two(wave_normal["lines"], _WAVE[0], _WAVE[1]) and wave_normal["next_y"] == 20,
        "loose_wavedash_breaks": _two(wave_loose["lines"], _WAVE[0], _WAVE[1]) and wave_loose["next_y"] == 20,
        "strict_wavedash_stays": _one(wave_strict["lines"], _WAVE, 20) and wave_strict["next_y"] == 10,
        "omitted_small_kana_stays": _one(kana_omitted["lines"], _KANA, 20) and kana_omitted["next_y"] == 10,
        "strict_small_kana_stays": _one(kana_strict["lines"], _KANA, 20) and kana_strict["next_y"] == 10,
        "loose_small_kana_breaks": _two(kana_loose["lines"], _KANA[0], _KANA[1]) and kana_loose["next_y"] == 20,
        "omitted_latin_stays": _one(latin_omitted["lines"], "AB", 20) and latin_omitted["next_y"] == 10,
        "anywhere_latin_breaks": _two(latin_anywhere["lines"], "A", "B") and latin_anywhere["next_y"] == 20,
        "child_inherits_strict": _one(inherited["lines"], _WAVE, 20) and inherited["next_y"] == 10,
        "invalid_keyword_is_rejected": invalid["outcome"] == "invalid" and invalid["reason"] == "line-break is invalid",
        "vertical_without_line_break_lays_out": vertical["outcome"] == "placed",
        "vertical_strict_is_rejected": vertical_strict["outcome"] == "invalid"
        and vertical_strict["reason"] == "line-break writing mode is unsupported",
        "rtl_strict_is_rejected": rtl_strict["outcome"] == "invalid"
        and rtl_strict["reason"] == "line-break writing mode is unsupported",
        "inline_declaration_is_rejected": inline["outcome"] == "invalid"
        and inline["reason"] == "inline line-break is unsupported",
    }
    observed = {
        "checks": checks,
        "wave_omitted": wave_omitted,
        "wave_normal": wave_normal,
        "wave_loose": wave_loose,
        "wave_strict": wave_strict,
        "kana_omitted": kana_omitted,
        "kana_strict": kana_strict,
        "kana_loose": kana_loose,
        "latin_omitted": latin_omitted,
        "latin_anywhere": latin_anywhere,
        "inherited": inherited,
        "invalid": {"outcome": invalid["outcome"], "reason": invalid["reason"]},
        "vertical": {"outcome": vertical["outcome"], "reason": vertical["reason"]},
        "vertical_strict": {"outcome": vertical_strict["outcome"], "reason": vertical_strict["reason"]},
        "rtl_strict": {"outcome": rtl_strict["outcome"], "reason": rtl_strict["reason"]},
        "inline": {"outcome": inline["outcome"], "reason": inline["reason"]},
    }
    _emit({"passed": all(checks.values()) and bool(observed), "observed": observed})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        _emit({"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}})
