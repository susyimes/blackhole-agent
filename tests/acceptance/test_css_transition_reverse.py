"""Interrupt a CSS length transition.

Prints JSON with boolean passed and nonempty observed. Exit 0 whether or not
the candidate implements reversing. A missing sampler is an unmet outcome.
"""

from __future__ import annotations

import json


def change(
    time_ms: float,
    value: str,
    *,
    duration: str = "1000ms",
    delay: str = "0ms",
    easing: str = "linear",
    transition: bool = True,
) -> dict[str, object]:
    return {
        "time_ms": time_ms,
        "value": value,
        "duration": duration,
        "delay": delay,
        "easing": easing,
        "transition": transition,
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_transition import interrupt_css_transition
    except Exception as exc:  # noqa: BLE001 - baseline without the sampler still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def run(name: str, changes: list[dict[str, object]], sample: float) -> dict[str, object]:
        try:
            result = interrupt_css_transition("0px", changes, sample)
        except Exception as exc:  # noqa: BLE001 - a raised sample is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        observed[name] = result if isinstance(result, dict) else {"outcome": "error"}
        return observed[name]

    def near(result: dict[str, object], value: float) -> bool:
        found = result.get("value")
        return (
            isinstance(found, (int, float))
            and not isinstance(found, bool)
            and abs(float(found) - value) < 1e-6
        )

    forward = change(0, "100px")
    reverse = run("reverse", [forward, change(250, "0px")], 375)
    checks.append(
        reverse.get("outcome") == "transitioning"
        and reverse.get("applying") is True
        and reverse.get("reversing") is True
        and reverse.get("shortening") == 0.25
        and reverse.get("unit") == "px"
        and reverse.get("value") == 12.5
    )

    retarget = run("retarget", [forward, change(250, "200px")], 750)
    checks.append(
        retarget.get("outcome") == "transitioning"
        and retarget.get("applying") is True
        and retarget.get("reversing") is False
        and retarget.get("shortening") == 1
        and retarget.get("value") == 112.5
    )

    eased = run("eased_reverse", [forward, change(250, "0px", easing="ease")], 375)
    checks.append(
        eased.get("outcome") == "transitioning"
        and eased.get("reversing") is True
        and near(eased, 4.9399153103785775)
        and eased.get("value") != 12.5
    )

    overshoot = run(
        "overshoot_reverse",
        [
            change(0, "100px", easing="cubic-bezier(0.5, 1.5, 0.5, 1)"),
            change(500, "0px"),
        ],
        1000,
    )
    checks.append(
        overshoot.get("outcome") == "transitioning"
        and overshoot.get("shortening") == 1
        and overshoot.get("reversing") is False
        and near(overshoot, 53.125)
        and not near(overshoot, 50)
    )

    negative_delay = run("negative_delay", [change(0, "100px", delay="-250ms")], 0)
    checks.append(
        negative_delay.get("outcome") == "transitioning"
        and negative_delay.get("applying") is True
        and negative_delay.get("value") == 25
    )

    held = run(
        "duration_kept",
        [forward, change(250, "100px", duration="5000ms")],
        500,
    )
    checks.append(
        held.get("outcome") == "transitioning"
        and held.get("value") == 50
        and held.get("shortening") == 1
    )

    cancelled = run("cancelled", [forward, change(250, "25px")], 250)
    checks.append(
        cancelled.get("outcome") == "settled"
        and cancelled.get("applying") is False
        and cancelled.get("reason") == "cancelled"
        and cancelled.get("value") == 25
    )

    second = run(
        "second_reverse",
        [forward, change(250, "0px"), change(375, "100px")],
        812.5,
    )
    checks.append(
        second.get("outcome") == "transitioning"
        and second.get("applying") is True
        and second.get("reversing") is True
        and second.get("shortening") == 0.875
        and second.get("value") == 56.25
    )

    removed = run("removed", [forward, change(250, "100px", transition=False)], 250)
    checks.append(
        removed.get("outcome") == "settled"
        and removed.get("applying") is False
        and removed.get("reason") == "removed"
        and removed.get("value") == 100
    )

    delayed = run("delayed_reverse", [forward, change(250, "0px", delay="100ms")], 300)
    midpoint = run("delayed_reverse_mid", [forward, change(250, "0px", delay="100ms")], 475)
    checks.append(
        delayed.get("applying") is True
        and delayed.get("value") == 25
        and midpoint.get("applying") is True
        and midpoint.get("value") == 12.5
        and midpoint.get("shortening") == 0.25
    )
    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
