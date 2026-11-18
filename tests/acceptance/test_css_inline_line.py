"""One CSS inline line keeps the strut and aligns each inline box.

A strut of ascent 8, descent 2, line-height 14 and x-height 8 is 14 tall
with the baseline at 10. A shorter text box stays inside it. A baseline
text box of ascent 16, descent 4 and line-height 20 grows the line to 20
and the baseline to 16. An atomic margin box 30 tall puts its top on the
line top and the baseline at 30. Height 10 with margin-top 2 and
margin-bottom 4 does the same at 16. Middle of an atomic 12 tall starts at
8. A length of 6 on a 10px text box starts at the line top, with line
height 18 and baseline 14. Text-top of an atomic 12 tall starts 2 below
the line top. Text-bottom starts on the line top. A top-aligned atomic 40
tall keeps baseline 10 and grows the line to 40. A bottom-aligned atomic
40 tall moves the baseline to 36. A top box of 40 beside a bottom box of
18 keeps baseline 10, with the bottom box at 22. A strut line-height of 8
below its 10px content stays 8 tall with baseline 7. A negative
line-height, a negative atomic height, and an unknown alignment are invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_STRUT = {"ascent": 8, "descent": 2, "line_height": 14, "x_height": 8}


def _close(got: object, expected: float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - expected) <= 1e-6


def _line(result: object, height: float, baseline: float) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "resolved"
        and _close(result.get("line_height"), height)
        and _close(result.get("baseline"), baseline)
        and isinstance(result.get("boxes"), list)
    )


def _box(result: object, name: str, top: float, height: float) -> bool:
    if not isinstance(result, dict):
        return False
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return False
    for box in boxes:
        if isinstance(box, dict) and box.get("id") == name:
            return _close(box.get("top"), top) and _close(box.get("height"), height)
    return False


def _invalid(result: object) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "invalid"
        and result.get("line_height") is None
        and result.get("baseline") is None
        and result.get("boxes") is None
    )


def _text(name: str, ascent: float, descent: float, line_height: float, align: object = "baseline") -> dict[str, object]:
    return {
        "id": name,
        "kind": "text",
        "ascent": ascent,
        "descent": descent,
        "line_height": line_height,
        "vertical_align": align,
    }


def _atomic(name: str, height: float, align: object = "baseline", **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"id": name, "kind": "atomic", "height": height, "vertical_align": align}
    payload.update(extra)
    return payload


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_inline_line import layout_inline_line
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def place(name: str, boxes: object, strut: object = _STRUT) -> dict[str, object]:
        try:
            result = layout_inline_line(strut, boxes)
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    alone = place("strut_only", [])
    checks.append(_line(alone, 14, 10))
    checks.append(alone.get("boxes") == [])

    short = place("shorter_text_stays_inside_the_strut", [_text("em", 4, 1, 6)])
    checks.append(_line(short, 14, 10))
    checks.append(_box(short, "em", 5.5, 6))

    tall = place("baseline_text_grows_the_line", [_text("em", 16, 4, 20)])
    checks.append(_line(tall, 20, 16))
    checks.append(_box(tall, "em", 0, 20))

    image = place("atomic_baseline", [_atomic("img", 30)])
    checks.append(_line(image, 34, 30))
    checks.append(_box(image, "img", 0, 30))

    margins = place(
        "atomic_margin_box",
        [_atomic("img", 10, margin_top=2, margin_bottom=4)],
    )
    checks.append(_line(margins, 20, 16))
    checks.append(_box(margins, "img", 0, 16))

    middle = place("middle_atomic", [_atomic("img", 12, "middle")])
    checks.append(_line(middle, 20, 10))
    checks.append(_box(middle, "img", 8, 12))

    raised = place("length_raises_text", [_text("em", 8, 2, 10, 6)])
    checks.append(_line(raised, 18, 14))
    checks.append(_box(raised, "em", 0, 10))

    text_top = place("text_top", [_atomic("img", 12, "text-top")])
    checks.append(_line(text_top, 14, 10))
    checks.append(_box(text_top, "img", 2, 12))

    text_bottom = place("text_bottom", [_atomic("img", 12, "text-bottom")])
    checks.append(_line(text_bottom, 14, 10))
    checks.append(_box(text_bottom, "img", 0, 12))

    top = place("top_grows_down", [_atomic("img", 40, "top")])
    checks.append(_line(top, 40, 10))
    checks.append(_box(top, "img", 0, 40))

    bottom = place("bottom_grows_up", [_atomic("img", 40, "bottom")])
    checks.append(_line(bottom, 40, 36))
    checks.append(_box(bottom, "img", 0, 40))

    both = place(
        "top_wins_the_tie",
        [_atomic("high", 40, "top"), _atomic("low", 18, "bottom")],
    )
    checks.append(_line(both, 40, 10))
    checks.append(_box(both, "high", 0, 40))
    checks.append(_box(both, "low", 22, 18))

    tight = place(
        "negative_half_leading",
        [],
        {"ascent": 8, "descent": 2, "line_height": 8, "x_height": 4},
    )
    checks.append(_line(tight, 8, 7))

    checks.append(_invalid(place("negative_line_height", [], {**_STRUT, "line_height": -1})))
    checks.append(_invalid(place("negative_atomic_height", [_atomic("img", -1)])))
    checks.append(_invalid(place("unknown_alignment", [_atomic("img", 10, "sub")])))
    checks.append(_invalid(place("boolean_height", [_atomic("img", True)])))  # type: ignore[arg-type]

    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
