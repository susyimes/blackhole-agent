"""Resolve stepped, exponential, and trigonometric CSS math as a used length.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A solver that only accepts calc(), min(), max(), and clamp()
still exits 0.
"""

from __future__ import annotations

import json
import math


def _near(found: object, expected: float, tol: float = 1e-6) -> bool:
    return isinstance(found, (int, float)) and not isinstance(found, bool) and abs(float(found) - expected) <= tol


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_block_width import used_block_width
        from blackhole_agent.css_length_math import resolve_length_math
    except Exception as exc:  # noqa: BLE001 - baseline without the solver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def length(name: str, expression: str, expected: float) -> None:
        try:
            row = resolve_length_math(expression, percentage_basis=100)
        except Exception as exc:  # noqa: BLE001 - a raised solve is an unmet outcome
            row = {"outcome": "error", "px": None, "reason": f"{type(exc).__name__}: {exc}"}
        observed[name] = row if isinstance(row, dict) else {"outcome": "error"}
        checks.append(
            isinstance(row, dict)
            and row.get("outcome") == "resolved"
            and row.get("reason") is None
            and _near(row.get("px"), expected)
        )

    def invalid(name: str, expression: str, reason: str) -> None:
        try:
            row = resolve_length_math(expression, percentage_basis=100)
        except Exception as exc:  # noqa: BLE001 - a raised solve is an unmet outcome
            row = {"outcome": "error", "px": None, "reason": f"{type(exc).__name__}: {exc}"}
        observed[name] = row if isinstance(row, dict) else {"outcome": "error"}
        checks.append(
            isinstance(row, dict) and row.get("outcome") == "invalid" and row.get("px") is None and row.get("reason") == reason
        )

    length("hypot", "hypot(3px, 4px)", 5)
    length("hypot_negative", "hypot(-3px, 4px)", 5)
    length("mod_positive", "mod(18px, 5px)", 3)
    length("mod_negative_dividend", "mod(-18px, 5px)", 2)
    length("rem_negative_dividend", "rem(-18px, 5px)", -3)
    length("mod_negative_step", "mod(10px, -3px)", -2)
    length("rem_negative_step", "rem(10px, -3px)", 1)
    length("round_up", "round(up, 10.2px, 1px)", 11)
    length("round_tie_positive", "round(nearest, 10.5px, 1px)", 11)
    length("round_tie_negative", "round(nearest, -10.5px, 1px)", -10)
    length("pow_negative_base", "calc(pow(-2, 3) * 1px)", -8)
    length("sin_turn", "calc(sin(0.25turn) * 8px)", 8)
    length("cos_grad", "calc(cos(200grad) * 7px)", -7)
    length("sin_atan2", "calc(sin(atan2(3px, 4px)) * 10px)", 6)
    length("cos_atan2_quadrant", "calc(cos(atan2(1, -1)) * 10px)", -5 * math.sqrt(2))
    length("log10", "calc(log(100, 10) * 1px)", 2)
    length("abs_length", "abs(-12px)", 12)
    length("sign_length", "calc(sign(-4px) * 5px)", -5)
    length("case_fold", "calc(SIN(90DEG) * 2px)", 2)
    length("inverse_round_trip", "calc(sin(asin(1)) * 9px)", 9)
    length("exp_zero", "calc(exp(0) * 4px)", 4)

    try:
        block = used_block_width(containing_block=200, width="hypot(30px, 40px)")
    except Exception as exc:  # noqa: BLE001 - a raised solve is an unmet outcome
        block = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
    observed["block_hypot"] = block if isinstance(block, dict) else {"outcome": "error"}
    checks.append(
        isinstance(block, dict)
        and block.get("outcome") == "sized"
        and block.get("content") == 50
        and block.get("margin_right") == 150
        and block.get("containing_block") == 200
    )

    invalid("round_omitted_step", "round(10px)", "math is invalid")
    invalid("sin_length", "sin(10px)", "type")
    invalid("hypot_mixed", "hypot(3px, 4)", "type")
    invalid("length_over_length", "calc(10px / 2px)", "type")
    invalid("line_width", "round(line-width, 10px)", "math is invalid")
    invalid("tan_asymptote", "calc(tan(90deg) * 1px)", "non-finite")
    invalid("pow_fractional_negative", "calc(pow(-8, 1/3) * 1px)", "non-finite")
    invalid("sqrt_negative", "calc(sqrt(-1) * 1px)", "non-finite")

    passed = all(checks) and bool(checks)
    if not passed:
        observed["failed"] = [name for name, ok in zip(observed, checks, strict=False) if not ok]
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
