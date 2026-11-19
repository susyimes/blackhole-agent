"""Resolve calc, min, max, and clamp into a block's used content width.

A 400px containing block with width calc(100% - 20px) has content 380, and
the margin equation gives the extra 20px to the end margin. clamp(40px, 10%,
30px) in 200px is 40 because the lower bound wins. min(50%, 100px) in 300px
is 100. calc(100% - 10px * 2) in 100px is 80. A glued sign, a length added
to a bare number, and a top-level division by zero are invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the solver still exits 0.
"""

from __future__ import annotations

import json


def _close(got: object, expected: int | float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - float(expected)) <= 1e-9


def _is(result: object, **expected: object) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "sized":
        return False
    for key, want in expected.items():
        if isinstance(want, bool) or not isinstance(want, (int, float)):
            if result.get(key) != want:
                return False
        elif not _close(result.get(key), want):
            return False
    return True


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_block_width import used_block_width
    except Exception as exc:  # noqa: BLE001 - baseline without the solver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, **kwargs: object) -> dict[str, object]:
        try:
            result = used_block_width(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised solve is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result if isinstance(result, dict) else {"outcome": "error"}
        return observed[name]

    gutter = keep("subtract_percent", containing_block=400, width="calc(100% - 20px)")
    checks.append(_is(gutter, content=380, margin_left=0, margin_right=20, border_box=380, margin_box=400))

    comment = keep("comment_is_whitespace", containing_block=400, width="calc(100% /* gutter */ - 20px)")
    checks.append(_is(comment, content=380, margin_right=20))

    inverted = keep("clamp_lower_bound_wins", containing_block=200, width="clamp(40px, 10%, 30px)")
    checks.append(_is(inverted, content=40, margin_left=0, margin_right=160))

    capped = keep("min_percent_and_px", containing_block=300, width="min(50%, 100px)")
    checks.append(_is(capped, content=100, margin_right=200))

    product = keep("product_before_sum", containing_block=100, width="calc(100% - 10px * 2)")
    checks.append(_is(product, content=80, margin_right=20))

    tight = keep("multiply_without_whitespace", containing_block=100, width="calc(2*10px)")
    checks.append(_is(tight, content=20, margin_right=80))

    nested = keep("max_of_calc", containing_block=100, width="max(calc(100% - 80px), 40px)")
    checks.append(_is(nested, content=40, margin_right=60))

    absorbed = keep("min_absorbs_infinity", containing_block=100, width="min(10px, 10px / 0)")
    checks.append(_is(absorbed, content=10, margin_right=90))

    border_box = keep(
        "border_box_math",
        containing_block=200,
        width="calc(100% - 20px)",
        padding_left=10,
        padding_right=10,
        box_sizing="border-box",
    )
    checks.append(_is(border_box, content=160, border_box=180, margin_right=20, padding_left=10))

    floor = keep(
        "negative_min_math_is_zero",
        containing_block=100,
        width="auto",
        min_width="calc(0px - 10px)",
    )
    checks.append(_is(floor, content=100, margin_left=0, margin_right=0))

    border = keep(
        "border_math_length",
        containing_block=100,
        width="auto",
        border_left="calc(8px)",
        border_right="calc(8px)",
    )
    checks.append(_is(border, content=84, border_left=8, border_right=8, border_box=100))

    def rejected(name: str, **kwargs: object) -> None:
        got = keep(name, containing_block=100, **kwargs)
        checks.append(got.get("outcome") == "invalid" and got.get("content") is None)

    rejected("glued_sign", width="calc(10px -5px)")
    rejected("number_plus_length", width="calc(10px + 2)")
    rejected("divide_by_zero", width="calc(100% / 0)")
    rejected("length_over_length", width="calc(10px / 2px)")
    rejected("negative_width_math", width="calc(10px - 30px)")
    rejected("unitless_zero", width="calc(0)")
    rejected("border_percentage", border_left="calc(10%)")

    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    if not observed:
        observed = {"error": "empty observation"}
    print(json.dumps({"passed": bool(passed), "observed": observed}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
