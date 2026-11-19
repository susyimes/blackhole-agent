"""Align inline boxes inside one already broken line.

start and end follow direction. left and right stay physical. justify
expands interior separators, not a removed trailing separator. pre keeps
that trailing separator in the width without expanding it.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the aligner still exits 0.
"""

from __future__ import annotations

import json

_WORDS = (
    {"id": "a", "width": 20, "space_after": 4},
    {"id": "b", "width": 10, "space_after": 4},
    {"id": "c", "width": 30, "space_after": 8},
)
_CHARS = (
    {"id": "a", "width": 10},
    {"id": "b", "width": 10},
    {"id": "c", "width": 10},
)


def _xs(result: object) -> list[object] | None:
    if not isinstance(result, dict) or result.get("outcome") != "aligned":
        return None
    items = result.get("items")
    if not isinstance(items, list):
        return None
    return [item.get("x") if isinstance(item, dict) else None for item in items]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_text_align import align_inline_line
    except Exception as exc:  # noqa: BLE001 - baseline without the aligner still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, **kwargs: object) -> dict[str, object]:
        try:
            result = align_inline_line(100, _WORDS, **kwargs)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - a raised align is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result if isinstance(result, dict) else {"outcome": "error"}
        return observed[name]

    start = keep("start")
    checks.append(
        _xs(start) == [0, 24, 38]
        and start.get("content_width") == 68
        and start.get("trailing_included") is False
        and start.get("trailing_width") == 8
        and start.get("alignment") == "left"
    )
    end = keep("end", text_align="end")
    checks.append(_xs(end) == [32, 56, 70] and end.get("alignment") == "right")
    center = keep("center", text_align="center")
    checks.append(_xs(center) == [16, 40, 54] and center.get("alignment") == "center")
    justified = keep("justify", text_align="justify")
    checks.append(
        _xs(justified) == [0, 40, 70]
        and justified.get("justified") is True
        and justified.get("content_width") == 100
        and justified.get("trailing_included") is False
    )
    last = keep("justify_last", text_align="justify", last_line=True)
    checks.append(_xs(last) == [0, 24, 38] and last.get("justified") is False)
    justify_all = keep(
        "justify_all",
        text_align="justify-all",
        text_align_last="center",
        last_line=True,
    )
    checks.append(_xs(justify_all) == [0, 40, 70] and justify_all.get("justified") is True)
    rtl = keep("rtl_start", direction="rtl")
    checks.append(_xs(rtl) == [80, 66, 32] and rtl.get("alignment") == "right")
    matched = keep("match_parent", text_align="match-parent", direction="rtl", parent_direction="ltr")
    checks.append(_xs(matched) == [48, 34, 0] and matched.get("alignment") == "left")

    try:
        characters = align_inline_line(
            100,
            _CHARS,
            text_align="justify",
            text_justify="inter-character",
        )
        words = align_inline_line(100, _CHARS, text_align="justify", text_justify="inter-word")
    except Exception as exc:  # noqa: BLE001 - a raised align is an unmet outcome
        characters = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        words = characters
    observed["inter_character"] = characters if isinstance(characters, dict) else {"outcome": "error"}
    observed["inter_word"] = words if isinstance(words, dict) else {"outcome": "error"}
    checks.append(_xs(observed["inter_character"]) == [0, 45, 90])
    checks.append(_xs(observed["inter_word"]) == [0, 10, 20])

    try:
        preserved = align_inline_line(
            100,
            (
                {"id": "a", "width": 20, "space_after": 4},
                {"id": "b", "width": 10, "space_after": 8},
            ),
            text_align="justify",
            white_space="pre",
        )
    except Exception as exc:  # noqa: BLE001 - a raised align is an unmet outcome
        preserved = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
    observed["pre_justify"] = preserved if isinstance(preserved, dict) else {"outcome": "error"}
    checks.append(
        _xs(observed["pre_justify"]) == [0, 82]
        and observed["pre_justify"].get("content_width") == 100
        and observed["pre_justify"].get("trailing_included") is True
        and observed["pre_justify"].get("trailing_width") == 8
        and observed["pre_justify"].get("trailing_x") == 92
    )

    try:
        negative = align_inline_line(-1, _WORDS)
    except Exception as exc:  # noqa: BLE001 - a raised align is an unmet outcome
        negative = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
    observed["negative"] = negative if isinstance(negative, dict) else {"outcome": "error"}
    checks.append(
        negative.get("outcome") == "invalid"
        and negative.get("reason") == "line width cannot be negative"
        and negative.get("items") is None
    )
    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet behavior and baseline both exit 0
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
