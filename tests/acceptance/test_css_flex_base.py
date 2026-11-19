"""Resolve one flex item's unclamped base and its hypothetical main size.

A zero specified size that includes its padding keeps a negative inner base.
The hypothetical size floors that content box at zero. A transferred ratio
beats both the max-content contribution and a min-content constraint. Without
a ratio, that constraint uses the min-content contribution. A definite
percentage and calc() resolve against a definite container, and a percentage
of an indefinite container does not. An automatic basis uses a definite main
size. The minimum clamps only the hypothetical size and wins over a smaller
maximum. The inner base is what a flex line then distributes.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the resolver still exits 0.
"""

from __future__ import annotations

import json


def _close(got: object, expected: int | float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - float(expected)) <= 1e-6


def _resolved(result: object) -> dict[str, object]:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return {}
    return result


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_flex_base import resolve_flex_base
        from blackhole_agent.css_flex_line import resolve_flex_line
    except Exception as exc:  # noqa: BLE001 - baseline without the resolver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, container: object = "indefinite", **kwargs: object) -> dict[str, object]:
        try:
            result = resolve_flex_base(container, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised resolve is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    negative = _resolved(
        keep(
            "negative_inner",
            400,
            flex_basis=0,
            padding=12,
            border=8,
            box_sizing="border-box",
            minimum=0,
        )
    )
    checks.append(_close(negative.get("inner_base"), -20))
    checks.append(_close(negative.get("outer_base"), 0))
    checks.append(_close(negative.get("hypothetical_inner"), 0))

    transferred = _resolved(
        keep(
            "transferred",
            flex_basis="content",
            cross=40,
            ratio=2,
            min_content=5,
            max_content=200,
            constraint="min-content",
            minimum=0,
        )
    )
    checks.append(transferred.get("basis") == "transferred")
    checks.append(_close(transferred.get("inner_base"), 80))

    constrained = _resolved(
        keep(
            "min_constraint",
            flex_basis="content",
            constraint="min-content",
            min_content=30,
            max_content=200,
            ratio="none",
            minimum=0,
        )
    )
    checks.append(_close(constrained.get("inner_base"), 30))

    intrinsic = _resolved(
        keep(
            "min_content_basis",
            flex_basis="min-content",
            constraint="max-content",
            min_content=30,
            max_content=200,
            minimum=0,
        )
    )
    checks.append(_close(intrinsic.get("inner_base"), 30))

    fitted = _resolved(
        keep(
            "fit_content",
            100,
            flex_basis="fit-content",
            min_content=30,
            max_content=200,
            minimum=0,
        )
    )
    checks.append(_close(fitted.get("inner_base"), 100))

    math = _resolved(keep("calc_basis", 400, flex_basis="calc(100% - 20px)", minimum=0))
    checks.append(_close(math.get("inner_base"), 380))

    percent = _resolved(keep("definite_percent", 200, flex_basis="50%", minimum=0))
    checks.append(_close(percent.get("inner_base"), 100))

    indefinite = _resolved(
        keep(
            "indefinite_percent",
            "indefinite",
            flex_basis="50%",
            min_content=30,
            max_content=200,
            minimum=0,
        )
    )
    checks.append(_close(indefinite.get("inner_base"), 200))

    automatic = _resolved(keep("automatic_main", flex_basis="auto", main_size=80, minimum=0))
    checks.append(_close(automatic.get("inner_base"), 80))

    clamped = _resolved(keep("minimum_wins", flex_basis=100, minimum=90, maximum=70))
    checks.append(_close(clamped.get("inner_base"), 100))
    checks.append(_close(clamped.get("hypothetical_inner"), 90))

    raised = _resolved(
        keep(
            "automatic_minimum",
            flex_basis=10,
            main_size="auto",
            minimum="auto",
            min_content=40,
            max_content=40,
        )
    )
    checks.append(_close(raised.get("inner_base"), 10))
    checks.append(_close(raised.get("hypothetical_inner"), 40))

    try:
        distributed = resolve_flex_line(
            300,
            [
                {"base": automatic.get("inner_base"), "grow": 1, "shrink": 1, "minimum": 0},
                {"base": percent.get("inner_base"), "grow": 1, "shrink": 1, "minimum": 0},
            ],
        )
    except Exception as exc:  # noqa: BLE001 - a raised line resolve is an unmet outcome
        distributed = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
    observed["distributed"] = distributed
    sizes = distributed.get("main_sizes") if isinstance(distributed, dict) else None
    checks.append(
        isinstance(distributed, dict)
        and distributed.get("outcome") == "resolved"
        and isinstance(sizes, list)
        and len(sizes) == 2
        and _close(sizes[0], 140)
        and _close(sizes[1], 160)
    )

    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
