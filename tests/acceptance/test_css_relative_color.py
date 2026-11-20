"""Rewrite a CSS color with relative color syntax.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without relative colors still exits 0.
"""

from __future__ import annotations

import json


def _near(found: object, expected: float, tol: float = 1e-6) -> bool:
    return isinstance(found, (int, float)) and not isinstance(found, bool) and abs(float(found) - expected) <= tol


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_relative_color import resolve_relative_color
    except Exception as exc:  # noqa: BLE001 - baseline without the resolver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def resolved(
        name: str,
        expression: str,
        space: str,
        components: tuple[float | None, float | None, float | None],
        alpha: float | None,
    ) -> None:
        row = resolve_relative_color(expression)
        observed[name] = row
        found = row.get("components")
        ok = (
            row.get("outcome") == "resolved"
            and row.get("space") == space
            and row.get("reason") == ""
            and isinstance(found, list)
            and len(found) == 3
        )
        if ok:
            for actual, expected in zip(found, components, strict=True):
                if expected is None:
                    ok = actual is None
                else:
                    ok = _near(actual, expected)
                if not ok:
                    break
        if alpha is None:
            ok = ok and row.get("alpha") is None
        else:
            ok = ok and _near(row.get("alpha"), alpha)
        checks.append(ok)

    def rejected(name: str, expression: str, reason: str) -> None:
        row = resolve_relative_color(expression)
        observed[name] = row
        checks.append(
            row.get("outcome") == "invalid"
            and row.get("reason") == reason
            and row.get("components") == []
            and row.get("alpha") is None
            and row.get("space") == ""
        )

    resolved("indianred", "rgb(from indianred 255 g b)", "srgb", (1, 92 / 255, 92 / 255), 1)
    resolved(
        "darkblue",
        "rgb(from darkblue 16 32 b / 0.5)",
        "srgb",
        (16 / 255, 32 / 255, 139 / 255),
        0.5,
    )
    resolved(
        "oklab_spec",
        "oklab(from oklab(54.3% -22.5% -5%) calc(1.0 - l) calc(a * 0.8) b)",
        "oklab",
        (0.457, -0.072, -0.02),
        1,
    )
    resolved(
        "oklch_hue",
        "oklch(from oklch(52.6% 0.115 44.6deg) l c calc(h + 90))",
        "oklch",
        (0.526, 0.115, 134.6),
        1,
    )
    resolved(
        "alpha_clamp",
        "oklch(from oklch(78% 0.06 75 / 0.7) l c h / calc(alpha * 2))",
        "oklch",
        (0.78, 0.06, 75),
        1,
    )
    resolved(
        "carried_hue",
        "oklch(from hsl(none 3% 50%) calc(l * 0.8) c h)",
        "oklch",
        (0.5920051953306076 * 0.8, 0.009356089965783484, None),
        1,
    )
    resolved(
        "missing_as_zero",
        "oklch(from oklch(0.5 0.1 none) l c calc(h + 180))",
        "oklch",
        (0.5, 0.1, 180),
        1,
    )
    resolved(
        "missing_stays",
        "oklch(from oklch(0.5 0.1 none) l c h)",
        "oklch",
        (0.5, 0.1, None),
        1,
    )
    resolved(
        "hue_not_wrapped",
        "hsl(from hsl(300 40% 30%) calc(h + 90) s l)",
        "hsl",
        (390, 40, 30),
        1,
    )
    resolved(
        "hue_normalized",
        "hsl(from hsl(-90 40% 30%) h s l)",
        "hsl",
        (270, 40, 30),
        1,
    )
    resolved(
        "turn",
        "hsl(from hsl(20 10% 10%) calc(h + 0.5turn) s l)",
        "hsl",
        (200, 10, 10),
        1,
    )
    resolved(
        "color_alpha_keyword",
        "color(from color(srgb 0 0 0 / 60%) srgb alpha 0.6 0.6 / 0.9)",
        "srgb",
        (0.6, 0.6, 0.6),
        0.9,
    )
    resolved(
        "rgb_alpha_keyword",
        "rgb(from rgb(0 0 0 / 60%) alpha 153 153 / 0.9)",
        "srgb",
        (0.6 / 255, 153 / 255, 153 / 255),
        0.9,
    )
    resolved(
        "grayscale_red",
        "rgb(from red calc(r * .3 + g * .59 + b * .11) calc(r * .3 + g * .59 + b * .11) calc(r * .3 + g * .59 + b * .11))",
        "srgb",
        (76.5 / 255, 76.5 / 255, 76.5 / 255),
        1,
    )
    resolved(
        "out_of_gamut",
        "rgb(from red calc(r + 20) g calc(b - 5))",
        "srgb",
        (275 / 255, 0, -5 / 255),
        1,
    )
    resolved("lab_percent", "lab(from lab(40 10 -10) l 100% b)", "lab", (40, 125, -10), 1)
    resolved(
        "omitted_alpha",
        "rgb(from rgb(10 20 30 / 0.25) r g b)",
        "srgb",
        (10 / 255, 20 / 255, 30 / 255),
        0.25,
    )
    resolved(
        "alpha_fn",
        "alpha(from oklch(60% 0.25 315 / 0.8) / calc(alpha * 0.5))",
        "oklch",
        (0.6, 0.25, 315),
        0.4,
    )
    resolved("alpha_none", "alpha(from red / none)", "srgb", (1, 0, 0), None)
    resolved(
        "sea_green",
        "hsl(from lightseagreen calc(h + 180) s l)",
        "hsl",
        (176.71232876712332 + 180, 69.52380952380946, 41.176470588235304),
        1,
    )
    resolved("white_hue", "oklch(from white l c h)", "oklch", (1, 0, None), 1)
    resolved(
        "nested",
        "rgb(from rgb(from #cd5c5c 255 g b) r g b / 40%)",
        "srgb",
        (1, 92 / 255, 92 / 255),
        0.4,
    )
    resolved("rgb_percent", "rgb(from red calc(50%) g b)", "srgb", (0.5, 0, 0), 1)

    rejected("legacy_commas", "rgba(from darkblue 16, 32, b, 0.5)", "syntax")
    rejected("absolute", "rgb(255 0 0)", "syntax")
    rejected("var", "rgb(from var(--base) r g b)", "color")
    rejected("divide", "rgb(from red calc(r / 0) g b)", "math")
    rejected("display_p3", "color(from red display-p3 r g b)", "space")

    passed = all(checks) and bool(checks)
    if not passed:
        observed["failed"] = [name for name, ok in zip(observed, checks, strict=False) if not ok]
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
