"""Sample a CSS animation at a local time.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
correct sample and a stylesheet the baseline cannot read.
"""

from __future__ import annotations

import json


def sheet(frames: str, decls: dict[str, str]) -> str:
    body = "\n".join(f"  {name}: {value};" for name, value in decls.items())
    return f"@keyframes slide {{\n{frames}\n}}\n.el {{\n  animation-name: slide;\n{body}\n}}\n"


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_animation import sample_css_animation
    except Exception as exc:  # noqa: BLE001 - baseline without the sampler still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def run(name: str, frames: str, decls: dict[str, str], time: float) -> dict[str, object]:
        try:
            result = sample_css_animation(sheet(frames, decls), time)
        except Exception as exc:  # noqa: BLE001 - a raised sample is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        observed[name] = result if isinstance(result, dict) else {"outcome": "error"}
        return observed[name]

    def sampled(name: str, frames: str, decls: dict[str, str], time: float, value: float) -> None:
        result = run(name, frames, decls, time)
        checks.append(
            result.get("outcome") == "sampled"
            and result.get("applying") is True
            and result.get("value") == value
            and result.get("unit") == "px"
        )

    def near(name: str, frames: str, decls: dict[str, str], time: float, value: float) -> None:
        result = run(name, frames, decls, time)
        found = result.get("value")
        checks.append(
            result.get("outcome") == "sampled"
            and result.get("applying") is True
            and isinstance(found, (int, float))
            and not isinstance(found, bool)
            and abs(float(found) - value) < 1e-6
        )

    def idle(name: str, frames: str, decls: dict[str, str], time: float, value: float, reason: str) -> None:
        result = run(name, frames, decls, time)
        checks.append(
            result.get("outcome") == "idle"
            and result.get("applying") is False
            and result.get("value") == value
            and result.get("reason") == reason
        )

    linear = "from { width: 0px; } to { width: 100px; }"
    base = {"animation-duration": "1000ms", "width": "7px"}
    sampled("linear_mid", linear, {**base, "animation-timing-function": "linear"}, 500, 50)
    near(
        "ease_mid",
        linear,
        {**base, "animation-timing-function": "ease"},
        500,
        80.24033875848569,
    )
    ease = observed["ease_mid"]
    checks.append(isinstance(ease, dict) and ease.get("value") != 50)

    interval = "from { width: 0px; animation-timing-function: linear; } to { width: 100px; }"
    sampled(
        "interval_easing",
        interval,
        {**base, "animation-timing-function": "steps(1, end)"},
        500,
        50,
    )
    ignored = "from { width: 0px; } to { width: 100px; animation-timing-function: steps(1, end); }"
    sampled(
        "to_easing_ignored",
        ignored,
        {**base, "animation-timing-function": "linear"},
        500,
        50,
    )
    commented = "from { width: 0px; } /* 50% { width: 999px; } */ to { width: 100px; }"
    sampled("comment_ignored", commented, base, 500, 50)

    steps = "from { width: 0px; animation-timing-function: steps(2, jump-end); } to { width: 100px; }"
    sampled("steps_before_boundary", steps, base, 499, 0)
    sampled("steps_on_boundary", steps, base, 500, 50)
    sampled("step_end_holds", linear, {**base, "animation-timing-function": "steps(1, end)"}, 999, 0)
    sampled(
        "step_end_finish",
        linear,
        {**base, "animation-timing-function": "steps(1, end)", "animation-fill-mode": "forwards"},
        1000,
        100,
    )

    alternate = {**base, "animation-iteration-count": "2", "animation-direction": "alternate"}
    sampled("alternate_second", linear, alternate, 1250, 75)
    sampled(
        "alternate_forwards",
        linear,
        {**alternate, "animation-fill-mode": "forwards"},
        2000,
        0,
    )
    sampled("iteration_boundary", linear, {**base, "animation-iteration-count": "2"}, 1000, 100)

    delay = {**base, "animation-delay": "200ms"}
    idle("delay_none", linear, delay, 100, 7, "")
    sampled("delay_backwards", linear, {**delay, "animation-fill-mode": "backwards"}, 100, 0)
    sampled(
        "delay_reverse",
        linear,
        {**delay, "animation-fill-mode": "backwards", "animation-direction": "reverse"},
        100,
        100,
    )
    idle("after_none", linear, base, 1500, 7, "")
    sampled("after_forwards", linear, {**base, "animation-fill-mode": "forwards"}, 1500, 100)
    sampled("fill_both_before", linear, {**delay, "animation-fill-mode": "both"}, 100, 0)
    sampled("fill_both_after", linear, {**base, "animation-fill-mode": "both"}, 1500, 100)

    sampled(
        "fractional_forwards",
        linear,
        {**base, "animation-iteration-count": "1.5", "animation-fill-mode": "forwards"},
        1500,
        50,
    )
    sampled("negative_delay", linear, {**base, "animation-delay": "-500ms"}, 0, 50)

    omitted = "50% { width: 100px; } to { width: 0px; }"
    omitted_rule = {"animation-duration": "1000ms", "width": "20px"}
    sampled("omitted_start", omitted, omitted_rule, 0, 20)
    sampled("omitted_quarter", omitted, omitted_rule, 250, 60)

    hold = "from { width: 0px; animation-timing-function: linear(0, 0.25 25% 75%, 1); } to { width: 100px; }"
    sampled("linear_hold", hold, base, 500, 25)

    step_start = "from { width: 0px; animation-timing-function: step-start; } to { width: 100px; }"
    sampled("step_start_jump", step_start, base, 0, 100)
    sampled(
        "step_start_delay",
        step_start,
        {**delay, "animation-fill-mode": "backwards"},
        100,
        0,
    )
    sampled(
        "zero_iterations",
        step_start,
        {**base, "animation-iteration-count": "0", "animation-fill-mode": "forwards"},
        0,
        0,
    )

    ease_in = {**base, "animation-timing-function": "ease-in"}
    reverse = {**base, "animation-timing-function": "ease-in", "animation-direction": "reverse"}
    forward_early = run("ease_in_early", linear, ease_in, 250)
    forward_late = run("ease_in_late", linear, ease_in, 750)
    reverse_early = run("ease_in_reverse", linear, reverse, 250)
    early = forward_early.get("value")
    late = forward_late.get("value")
    backed = reverse_early.get("value")
    checks.append(
        forward_early.get("outcome") == "sampled"
        and forward_late.get("outcome") == "sampled"
        and reverse_early.get("outcome") == "sampled"
        and isinstance(early, float)
        and isinstance(late, float)
        and isinstance(backed, float)
        and early != late
        and backed == late
        and abs(early - 50) > 1
    )

    sampled("infinite_third", linear, {**base, "animation-iteration-count": "infinite"}, 2500, 50)

    invalid = run(
        "bad_cubic",
        linear,
        {**base, "animation-timing-function": "cubic-bezier(1.5, 0, 1, 1)"},
        500,
    )
    checks.append(invalid.get("outcome") == "invalid" and invalid.get("reason") == "cubic-bezier")
    bad_steps = run(
        "bad_steps",
        linear,
        {**base, "animation-timing-function": "steps(1, jump-none)"},
        500,
    )
    checks.append(bad_steps.get("outcome") == "invalid" and bad_steps.get("reason") == "steps")

    missing = sheet(linear, base).replace("animation-name: slide", "animation-name: missing")
    try:
        missing_result = sample_css_animation(missing, 500)
    except Exception as exc:  # noqa: BLE001 - a raised sample is an unmet outcome
        missing_result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
    observed["missing_name"] = missing_result
    checks.append(
        missing_result.get("outcome") == "idle"
        and missing_result.get("applying") is False
        and missing_result.get("value") == 7
        and missing_result.get("reason") == "keyframes"
    )
    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
