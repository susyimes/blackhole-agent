"""Balance CSS text-wrap-style breaks without changing the line count.

First-fit puts ``a bbbb ccc dd ee`` into ``a bbbb``, ``ccc dd``, and ``ee``.
Shrinking the measure and repeating first-fit keeps that split. Balance moves
the interior break to ``a bbbb``, ``ccc``, and ``dd ee``. A preserved newline
balances each group alone. Eleven lines stay on the first-fit breaks.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A breaker without balance_lines still exits 0.
"""

from __future__ import annotations

import json


def _rows(result: object) -> list[tuple[object, object]] | None:
    if not isinstance(result, dict) or result.get("outcome") != "wrapped":
        return None
    lines = result.get("lines")
    if not isinstance(lines, list) or not lines:
        return None
    packed: list[tuple[object, object]] = []
    for line in lines:
        if not isinstance(line, dict):
            return None
        packed.append((line.get("text"), line.get("content_width")))
    return packed


def _variance(rows: list[tuple[object, object]], width: int) -> float:
    leftovers = [width - int(content) for _text, content in rows]
    mean = sum(leftovers) / len(leftovers)
    return sum((item - mean) ** 2 for item in leftovers) / len(leftovers)


def _unit_block(sizes: list[int]) -> tuple[str, dict[str, int]]:
    chars: list[str] = []
    advances = {" ": 0}
    for index, size in enumerate(sizes):
        if index:
            chars.append(" ")
        glyph = chr(ord("a") + index)
        chars.append(glyph * size)
        advances[glyph] = 1
    return "".join(chars), advances


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_line_break import balance_lines, wrap_lines
    except Exception as exc:  # noqa: BLE001 - baseline without balance still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []
    title_advances = {"a": 10, "b": 10, "c": 10, "d": 10, " ": 10}
    uneven_advances = {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1, " ": 0}

    def take(name: str, fn: object, *args: object, **kwargs: object) -> dict[str, object]:
        try:
            result = fn(*args, **kwargs)  # type: ignore[operator]
        except Exception as exc:  # noqa: BLE001 - a raised break is an unmet outcome
            result = {"outcome": "error", "lines": None, "reason": f"{type(exc).__name__}: {exc}"}
        packed = result if isinstance(result, dict) else {"outcome": "error", "lines": None}
        observed[name] = {
            "outcome": packed.get("outcome"),
            "lines": _rows(packed),
            "reason": packed.get("reason"),
            "min_content": packed.get("min_content"),
            "max_content": packed.get("max_content"),
        }
        return observed[name]

    title = take(
        "title",
        balance_lines,
        "aa bb cc dd",
        80,
        advances=title_advances,
    )
    title_fit = take("title_fit", wrap_lines, "aa bb cc dd", 80, advances=title_advances)
    checks.append(
        title.get("lines") == [("aa bb", 50), ("cc dd", 50)]
        and title_fit.get("lines") == [("aa bb cc", 80), ("dd", 20)]
        and title.get("min_content") == title_fit.get("min_content")
        and title.get("max_content") == title_fit.get("max_content")
    )
    title_lines = title.get("lines")
    fit_lines = title_fit.get("lines")
    if isinstance(title_lines, list) and isinstance(fit_lines, list):
        checks.append(_variance(title_lines, 80) < _variance(fit_lines, 80))
    else:
        checks.append(False)

    uneven = "a bbbb ccc dd ee"
    balanced = take("uneven", balance_lines, uneven, 6, advances=uneven_advances)
    first = take("uneven_fit", wrap_lines, uneven, 6, advances=uneven_advances)
    expected_balance = [("a bbbb", 5), ("ccc", 3), ("dd ee", 4)]
    expected_fit = [("a bbbb", 5), ("ccc dd", 5), ("ee", 2)]
    checks.append(balanced.get("lines") == expected_balance and first.get("lines") == expected_fit)
    narrower: list[object] = []
    narrower_ok = True
    for measure in range(0, 7):
        got = take(f"narrow_{measure}", wrap_lines, uneven, measure, advances=uneven_advances)
        rows = got.get("lines")
        if isinstance(rows, list) and len(rows) == 3 and rows != expected_fit:
            narrower_ok = False
        if isinstance(rows, list) and len(rows) == 3:
            narrower.append(rows)
    observed["narrow_three_line_splits"] = narrower
    checks.append(narrower_ok and bool(narrower))

    preserved = "aa bb cc dd\naa bb cc dd"
    forced = take(
        "forced",
        balance_lines,
        preserved,
        80,
        white_space="pre-line",
        advances=title_advances,
    )
    forced_fit = take(
        "forced_fit",
        wrap_lines,
        preserved,
        80,
        white_space="pre-line",
        advances=title_advances,
    )
    checks.append(
        forced.get("lines")
        == [("aa bb", 50), ("cc dd", 50), ("aa bb", 50), ("cc dd", 50)]
        and forced_fit.get("lines") == [("aa bb cc", 80), ("dd", 20), ("aa bb cc", 80), ("dd", 20)]
    )

    single = take("single", balance_lines, "aa bb", 80, advances=title_advances)
    checks.append(single.get("lines") == [("aa bb", 50)])

    nowrap = take(
        "nowrap",
        balance_lines,
        "aa bb cc dd",
        80,
        white_space="nowrap",
        advances=title_advances,
    )
    checks.append(nowrap.get("lines") == [("aa bb cc dd", 110)])

    sizes = [15, 10, 10, 5, 20, 15, 10, 10, 5, 20, 15, 10, 10, 5]
    long_text, long_advances = _unit_block(sizes)
    long_fit = [
        ("a" * 15, 15),
        ("b" * 10 + " " + "c" * 10, 20),
        ("d" * 5, 5),
        ("e" * 20, 20),
        ("f" * 15, 15),
        ("g" * 10 + " " + "h" * 10, 20),
        ("i" * 5, 5),
        ("j" * 20, 20),
        ("k" * 15, 15),
        ("l" * 10 + " " + "m" * 10, 20),
        ("n" * 5, 5),
    ]
    long = take("eleven", balance_lines, long_text, 20, advances=long_advances)
    long_first = take("eleven_fit", wrap_lines, long_text, 20, advances=long_advances)
    checks.append(long.get("lines") == long_fit and long_first.get("lines") == long_fit)

    invalid = take("invalid", balance_lines, None, 10)
    checks.append(invalid.get("outcome") == "invalid" and invalid.get("lines") is None and bool(invalid.get("reason")))
    return all(checks), observed


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    if not observed:
        observed = {"error": "empty observation"}
    _emit({"passed": bool(passed), "observed": observed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
