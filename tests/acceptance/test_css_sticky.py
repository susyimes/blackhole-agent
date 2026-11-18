"""A scrollport holds a sticky border edge, and the containing block lets it go.

A start inset only shifts that edge toward the end. An end inset only shifts
the opposite edge toward the start. A 300px scrollport around a 200px border
box with a 20px start inset leaves a 280px sticky view. A 100px scrollport
reduces the end inset to -120 so the view stays 200px and the start edge
still meets 20. An end inset still pulls a shorter box that has crossed the
far edge. Invalid lengths report an invalid outcome.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the sticky offset still exits 0.
"""

from __future__ import annotations

import json


def _close(got: object, expected: float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - expected) <= 1e-6


def _resolved(result: object, **expected: object) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return False
    for key, want in expected.items():
        got = result.get(key)
        if isinstance(want, bool):
            if got is not want:
                return False
        elif isinstance(want, (int, float)):
            if not _close(got, float(want)):
                return False
        elif got != want:
            return False
    return True


def _invalid(result: object) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "invalid"
        and result.get("offset") is None
        and result.get("border_start") is None
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_sticky import sticky_offset
    except Exception as exc:  # noqa: BLE001 - baseline without the offset still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def place(name: str, *args: object, **kwargs: object) -> dict[str, object]:
        try:
            result = sticky_offset(*args, **kwargs)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    resting = place("still_in_flow", 100, 40, 200, 0, 800, start=10)
    checks.append(
        _resolved(
            resting,
            offset=0,
            border_start=100,
            sticky_view_size=190,
            effective_start_inset=10,
            effective_end_inset=0,
            start_anchored=True,
            end_anchored=False,
        )
    )

    stuck = place("stuck_to_start", 100, 40, 200, 0, 800, scroll=150, start=10)
    checks.append(_resolved(stuck, offset=60, border_start=160, start_anchored=True))

    released = place("released_by_containing_end", 100, 40, 300, 0, 200, scroll=180, start=0)
    checks.append(_resolved(released, offset=60, border_start=160))

    stuck_end = place("stuck_to_end", 800, 50, 400, 0, 2000, end=20)
    checks.append(
        _resolved(
            stuck_end,
            offset=-470,
            border_start=330,
            sticky_view_size=380,
            effective_end_inset=20,
            start_anchored=False,
            end_anchored=True,
        )
    )

    capped = place("end_capped_by_containing_start", 800, 50, 400, 700, 2000, end=0)
    checks.append(_resolved(capped, offset=-100, border_start=700))

    unpulled = place("auto_end_does_not_pull", 800, 50, 400, 0, 2000, start=10)
    checks.append(_resolved(unpulled, offset=0, border_start=800, end_anchored=False))

    both = place("end_still_binds_when_the_box_fits", 800, 50, 400, 0, 5000, start=10, end=20)
    checks.append(_resolved(both, offset=-470, border_start=330, start_anchored=True, end_anchored=True))

    loose = place("spec_view_of_280", 0, 200, 300, 0, 1000, start=20)
    checks.append(
        _resolved(
            loose,
            offset=20,
            border_start=20,
            sticky_view_size=280,
            effective_start_inset=20,
            effective_end_inset=0,
            end_anchored=False,
        )
    )

    tight = place("spec_view_of_200", 0, 200, 100, 0, 2000, start=20)
    checks.append(
        _resolved(
            tight,
            offset=20,
            border_start=20,
            sticky_view_size=200,
            effective_end_inset=-120,
            end_anchored=False,
        )
    )

    wins = place("tall_box_start_inset_wins", 0, 200, 100, 0, 2000, start=20, end=20)
    checks.append(
        _resolved(
            wins,
            offset=20,
            border_start=20,
            sticky_view_size=200,
            effective_start_inset=20,
            effective_end_inset=-120,
            start_anchored=True,
            end_anchored=True,
        )
    )

    held = place("tall_box_stays_on_the_start_inset", 0, 200, 100, -500, 1000, scroll=50, start=20, end=20)
    checks.append(_resolved(held, offset=70, border_start=70, effective_end_inset=-120))

    negative = place("negative_start_inset", 0, 30, 200, 0, 400, scroll=25, start=-10)
    checks.append(_resolved(negative, offset=15, border_start=15))

    shifted = place("scrollport_origin_shifts_the_inset", 40, 20, 200, 0, 400, port_origin=50, start=10)
    checks.append(_resolved(shifted, offset=20, border_start=60))

    fractional = place("fractional_inset", 0, 20, 100, 0, 200, start=10.5)
    checks.append(_resolved(fractional, offset=10.5, border_start=10.5))

    idle = place("both_insets_automatic", 40, 20, 200, 0, 400, scroll=80, start=" Auto ")
    checks.append(
        _resolved(
            idle,
            offset=0,
            border_start=40,
            sticky_view_size=None,
            effective_start_inset=None,
            effective_end_inset=None,
            start_anchored=False,
            end_anchored=False,
        )
    )

    blocked = place("already_past_the_containing_end", 180, 40, 300, 0, 200, scroll=250, start=0)
    checks.append(_resolved(blocked, offset=0, border_start=180))

    above = place("already_before_the_containing_start", 40, 30, 50, 50, 400, end=0)
    checks.append(_resolved(above, offset=0, border_start=40, sticky_view_size=50))

    checks.append(_invalid(place("negative_border", 0, -1, 100, 0, 100)))
    checks.append(_invalid(place("boolean_border", True, 10, 100, 0, 100)))
    checks.append(_invalid(place("unknown_inset", 0, 10, 100, 0, 100, start="none")))
    checks.append(_invalid(place("negative_scrollport", 0, 10, -5, 0, 100)))
    checks.append(_invalid(place("reversed_containing_block", 0, 10, 100, 20, 10)))
    checks.append(_invalid(place("infinite_scroll", 0, 10, 100, 0, 100, scroll=float("inf"))))
    checks.append(_invalid(place("nan_origin", float("nan"), 10, 100, 0, 100)))

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
