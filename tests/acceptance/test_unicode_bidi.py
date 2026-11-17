"""Resolve embedding levels and visual order for one bidirectional paragraph.

An isolate keeps an inner number from moving the letters outside it. A
European number after Arabic letters joins through a comma, and the same
comma stays apart between a European number and an Arabic-Indic number.
Brackets in the UAX #9 example take the embedding direction. A European
number in a right-to-left paragraph keeps its left-to-right order.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the resolver still exits 0.
"""

from __future__ import annotations

import json


def _levels(result: object, expected: list[int | None]) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return False
    return result.get("levels") == expected


def _order(result: object, expected: list[int]) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return False
    return result.get("visual_order") == expected


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.unicode_bidi import resolve_bidi
    except Exception as exc:  # noqa: BLE001 - baseline without the resolver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, text: str, direction: str = "ltr") -> dict[str, object]:
        try:
            result = resolve_bidi(text, direction)
        except Exception as exc:  # noqa: BLE001 - a raised resolve is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    latin = keep("latin", "ab")
    checks.append(latin.get("paragraph_level") == 0)
    checks.append(_levels(latin, [0, 0]) and _order(latin, [0, 1]))

    hebrew = keep("hebrew", "\u05d0\u05d1")
    checks.append(_levels(hebrew, [1, 1]) and _order(hebrew, [1, 0]))

    numbers = keep("numbers_rtl", "123", "rtl")
    checks.append(numbers.get("paragraph_level") == 1)
    checks.append(_levels(numbers, [2, 2, 2]) and _order(numbers, [0, 1, 2]))

    arabic = keep("arabic_number", "\u0627\u0031\u002c\u0032")
    checks.append(_levels(arabic, [1, 2, 2, 2]) and _order(arabic, [1, 2, 3, 0]))

    mixed = keep("mixed_numbers", "\u05d0\u0031\u002c\u0661")
    checks.append(_levels(mixed, [1, 2, 1, 2]) and _order(mixed, [3, 2, 1, 0]))

    isolated = keep("isolated_number", "\u0061\u2067\u05d0\u2069\u0031")
    checks.append(_levels(isolated, [0, 0, 1, 0, 0]) and _order(isolated, [0, 1, 2, 3, 4]))
    bare = keep("bare_number", "\u0061\u05d0\u0031")
    checks.append(_levels(bare, [0, 1, 2]) and _order(bare, [0, 2, 1]))

    brackets = "\u05d0\u05d1\u0028\u05d2\u05d3\u005b\u0026\u0065\u0066\u005d\u002e\u0029\u0067\u0068"
    ltr_brackets = keep("brackets_ltr", brackets)
    checks.append(
        _levels(ltr_brackets, [1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        and _order(ltr_brackets, [1, 0, 2, 4, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13])
    )
    rtl_brackets = keep("brackets_rtl", brackets, "rtl")
    checks.append(rtl_brackets.get("paragraph_level") == 1)
    checks.append(
        _levels(rtl_brackets, [1, 1, 1, 1, 1, 1, 1, 2, 2, 1, 1, 1, 2, 2])
        and _order(rtl_brackets, [12, 13, 11, 10, 9, 7, 8, 6, 5, 4, 3, 2, 1, 0])
    )

    mark = keep("bracket_mark", "\u0061\u0028\u0062\u0029\u0331", "rtl")
    checks.append(_levels(mark, [2, 2, 2, 2, 2]) and _order(mark, [0, 1, 2, 3, 4]))

    embedding = keep(
        "override_isolate",
        "\u202e\u0061\u202a\u0062\u202c\u2066\u0063\u2069\u202a\u0064\u202c\u0065\u202c",
        "auto",
    )
    checks.append(embedding.get("paragraph_level") == 0)
    checks.append(
        _levels(embedding, [None, 1, None, 2, None, 1, 2, 1, None, 2, None, 1, None])
        and _order(embedding, [11, 9, 7, 6, 5, 3, 1])
    )

    auto_hebrew = keep("auto_hebrew", "\u05d0", "auto")
    checks.append(auto_hebrew.get("paragraph_level") == 1 and _levels(auto_hebrew, [1]))
    auto_latin = keep("auto_latin", "a", "auto")
    checks.append(auto_latin.get("paragraph_level") == 0 and _levels(auto_latin, [0]))

    invalid = keep("bad_direction", "ab", "sideways")
    checks.append(invalid.get("outcome") == "invalid" and invalid.get("levels") is None)
    missing = keep("missing_text", "")
    # keep() always passes a string; exercise the type gate directly.
    try:
        not_text = resolve_bidi(None, "ltr")  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
        not_text = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
    observed["not_text"] = not_text
    checks.append(isinstance(not_text, dict) and not_text.get("outcome") == "invalid" and not_text.get("levels") is None)
    checks.append(missing.get("outcome") == "resolved" and missing.get("levels") == [] and missing.get("visual_order") == [])

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
