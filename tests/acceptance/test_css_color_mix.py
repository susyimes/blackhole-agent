"""Mix CSS colors in a named interpolation space.

Premultiplied alpha, a missing channel, a powerless hue, and the short and
long hue arcs all change the mixed color. An omitted space is Oklab.
Percentages below 100% scale alpha after the blend, and 0% plus 0% still
blends the channels before the result becomes transparent.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the mixer still exits 0.
"""

from __future__ import annotations

import json


def _linear(value: float) -> float:
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _close(got: object, expected: float, tolerance: float, *, hue: bool = False) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    number = float(got)
    if hue:
        return abs((number - expected + 180) % 360 - 180) <= tolerance
    return abs(number - expected) <= tolerance


def _channels(
    result: dict[str, object],
    expected: tuple[float, float, float],
    alpha: float,
    *,
    tolerance: float = 1e-6,
    hue_index: int | None = None,
    hue_tolerance: float | None = None,
) -> bool:
    components = result.get("components")
    if not isinstance(components, list) or len(components) != 3:
        return False
    if not _close(result.get("alpha"), alpha, tolerance):
        return False
    for index, want in enumerate(expected):
        used = hue_tolerance if hue_index == index and hue_tolerance is not None else tolerance
        if not _close(components[index], want, used, hue=hue_index == index):
            return False
    return True


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_color_mix import mix_color
    except Exception as exc:  # noqa: BLE001 - baseline without the mixer still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}

    def keep(name: str, expression: str) -> dict[str, object]:
        try:
            result = mix_color(expression)
        except Exception as exc:  # noqa: BLE001 - a raised mix is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result

    checks: list[bool] = []
    plain = keep("srgb_half", "color-mix(in srgb, red, blue)")
    checks.append(plain.get("outcome") == "mixed" and plain.get("space") == "srgb")
    checks.append(_channels(plain, (0.5, 0.0, 0.5), 1.0))
    low = keep("under_half", "color-mix(in srgb, red 20%, blue 20%)")
    checks.append(_channels(low, (0.5, 0.0, 0.5), 0.4))
    high = keep("over_half", "color-mix(in srgb, red 80%, blue 80%)")
    checks.append(_channels(high, (0.5, 0.0, 0.5), 1.0))
    zeros = keep("zero_percent", "color-mix(in srgb, red 0%, blue 0%)")
    checks.append(_channels(zeros, (0.5, 0.0, 0.5), 0.0))
    quarter = keep("omitted_percent", "color-mix(in srgb, red 25%, blue)")
    checks.append(_channels(quarter, (0.25, 0.0, 0.75), 1.0))
    premultiplied = keep(
        "premultiplied",
        "color-mix(in srgb, rgb(100% 0% 0% / 0.7) 25%, rgb(0% 100% 0% / 0.2))",
    )
    checks.append(_channels(premultiplied, (0.175 / 0.325, 0.15 / 0.325, 0.0), 0.325, tolerance=1e-9))
    scaled = keep(
        "alpha_multiplier",
        "color-mix(in srgb, rgb(100% 0% 0% / 0.7) 20%, rgb(0% 100% 0% / 0.2) 60%)",
    )
    checks.append(_channels(scaled, (0.175 / 0.325, 0.15 / 0.325, 0.0), 0.26, tolerance=1e-9))
    transparent = keep("transparent_red", "color-mix(in srgb, rgb(100% 0% 0% / 0), blue)")
    checks.append(_channels(transparent, (0.0, 0.0, 1.0), 0.5))
    missing = keep("missing_red", "color-mix(in srgb, rgb(none 100% 0%), rgb(100% 0% 0%))")
    checks.append(_channels(missing, (1.0, 0.5, 0.0), 1.0))
    short = keep("oklch_short", "color-mix(in oklch, oklch(0.6 0.24 30), oklch(0.8 0.15 90))")
    checks.append(short.get("hue_method") == "shorter")
    checks.append(_channels(short, (0.7, 0.195, 60.0), 1.0, hue_index=2))
    long = keep("oklch_long", "color-mix(in oklch longer hue, oklch(0.6 0.24 30), oklch(0.8 0.15 90))")
    checks.append(long.get("hue_method") == "longer")
    checks.append(_channels(long, (0.7, 0.195, 240.0), 1.0, hue_index=2))
    rising = keep(
        "oklch_increasing",
        "color-mix(in oklch increasing hue, oklch(0.5 0.1 30), oklch(0.7 0.1 190))",
    )
    checks.append(_channels(rising, (0.6, 0.1, 110.0), 1.0, hue_index=2))
    falling = keep(
        "oklch_decreasing",
        "color-mix(in oklch decreasing hue, oklch(0.5 0.1 30), oklch(0.7 0.1 190))",
    )
    checks.append(_channels(falling, (0.6, 0.1, 290.0), 1.0, hue_index=2))
    explicit_gray = keep("explicit_gray_hue", "color-mix(in hsl, hsl(0 0% 50%), hsl(120 100% 50%))")
    checks.append(_channels(explicit_gray, (60.0, 50.0, 50.0), 1.0, hue_index=0))
    hsl_short = keep("hsl_short", "color-mix(in hsl, red, blue)")
    checks.append(_channels(hsl_short, (300.0, 100.0, 50.0), 1.0, hue_index=0, hue_tolerance=1e-4))
    hsl_long = keep("hsl_long", "color-mix(in hsl longer hue, red, blue)")
    checks.append(_channels(hsl_long, (120.0, 100.0, 50.0), 1.0, hue_index=0, hue_tolerance=1e-4))
    blue = keep("blue_oklch", "color-mix(in oklch, blue)")
    white_blue = keep("white_blue_hue", "color-mix(in oklch, white, blue)")
    blue_channels = blue.get("components")
    mixed_channels = white_blue.get("components")
    hue_kept = False
    if (
        isinstance(blue_channels, list)
        and isinstance(mixed_channels, list)
        and len(blue_channels) == 3
        and len(mixed_channels) == 3
    ):
        hue_kept = _close(mixed_channels[2], float(blue_channels[2]), 1e-4, hue=True)
        halfway = (float(blue_channels[2]) / 2) % 360
        hue_kept = hue_kept and not _close(mixed_channels[2], halfway, 20, hue=True)
        hue_kept = hue_kept and _close(blue_channels[0], 0.45201, 0.002)
        hue_kept = hue_kept and _close(blue_channels[1], 0.31321, 0.002)
        hue_kept = hue_kept and _close(blue_channels[2], 264.052, 0.2, hue=True)
    checks.append(hue_kept)
    default = keep("default_oklab", "color-mix(red, blue)")
    explicit = keep("explicit_oklab", "color-mix(in oklab, red, blue)")
    same_space = default.get("space") == "oklab" and explicit.get("space") == "oklab"
    default_channels = default.get("components")
    explicit_channels = explicit.get("components")
    if isinstance(default_channels, list) and isinstance(explicit_channels, list):
        same_space = same_space and all(
            _close(default_channels[index], float(explicit_channels[index]), 1e-9) for index in range(3)
        )
        same_space = same_space and not _close(default_channels[0], 0.5, 0.02)
    else:
        same_space = False
    checks.append(same_space)
    third = keep("three_srgb", "color-mix(in srgb, red, lime, blue)")
    checks.append(_channels(third, (1 / 3, 1 / 3, 1 / 3), 1.0, tolerance=1e-9))
    rejected = keep("rectangular_hue", "color-mix(in srgb shorter hue, red, blue)")
    checks.append(rejected.get("outcome") == "invalid")
    lab_white = keep("lab_white", "color-mix(in lab, white)")
    checks.append(_channels(lab_white, (100.0, 0.0, 0.0), 1.0, tolerance=1e-4))
    oklab_white = keep("oklab_white", "color-mix(in oklab, white)")
    checks.append(_channels(oklab_white, (1.0, 0.0, 0.0), 1.0, tolerance=1e-5))
    carried = keep("carried_missing", "color-mix(in oklab, rgb(none none none / 50%), red)")
    red_oklab = keep("red_oklab", "color-mix(in oklab, red)")
    carried_ok = False
    carried_channels = carried.get("components")
    red_channels = red_oklab.get("components")
    if isinstance(carried_channels, list) and isinstance(red_channels, list):
        carried_ok = _close(carried.get("alpha"), 0.75, 1e-6) and all(
            _close(carried_channels[index], float(red_channels[index]), 1e-6) for index in range(3)
        )
    checks.append(carried_ok)
    gray = 128 / 255
    encoded = keep("srgb_gray", "color-mix(in srgb, #808080, white)")
    linear = keep("linear_gray", "color-mix(in srgb-linear, #808080, white)")
    encoded_ok = _channels(encoded, ((gray + 1) / 2, (gray + 1) / 2, (gray + 1) / 2), 1.0, tolerance=1e-9)
    linear_expected = (_linear(gray) + 1) / 2
    linear_ok = _channels(
        linear,
        (linear_expected, linear_expected, linear_expected),
        1.0,
        tolerance=1e-9,
    )
    linear_channels = linear.get("components")
    separated = isinstance(linear_channels, list) and not _close(linear_channels[0], (gray + 1) / 2, 0.05)
    checks.append(encoded_ok and linear_ok and separated)
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
