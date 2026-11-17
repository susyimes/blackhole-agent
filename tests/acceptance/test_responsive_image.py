"""Image candidate selection from srcset, sizes, and picture sources.

A comma inside a URL stays there. A comma after a URL does not make the
next token a density descriptor. Width descriptors divide by the sizes
length. The earliest density at or above the device pixel ratio wins, and
a repeated density keeps the earlier URL. Picture sources are skipped when
their type or media does not apply, and they do not inherit the img src.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the decision is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

WEB = ("image/png", "image/webp")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.responsive_image import select_image
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}

    def keep(name: str, **kwargs: object) -> None:
        try:
            result = select_image(**kwargs)  # type: ignore[arg-type]
            observed[name] = [
                result["url"],
                result["density"],
                result["source_size"],
                result["slot"],
                result["source_index"],
            ]
        except Exception as exc:  # noqa: BLE001 - a rejected input is an unmet outcome
            observed[name] = f"{type(exc).__name__}: {exc}"

    keep(
        "comma_inside_url",
        srcset="https://cdn.example/a,b.png 2x",
        device_pixel_ratio=2,
        viewport_width=1000,
    )
    keep(
        "data_url_comma",
        srcset="data:image/gif;base64,AAAA 1x",
        viewport_width=1000,
    )
    keep("comma_is_not_descriptor", srcset="hero.jpg, 2x", device_pixel_ratio=2, viewport_width=1000)
    keep("explicit_density", srcset="hero.jpg 2x", device_pixel_ratio=2, viewport_width=1000)
    keep(
        "fallback_for_higher_density",
        src="fallback.jpg",
        srcset="hero.jpg 2x",
        viewport_width=1000,
    )
    keep(
        "explicit_one_keeps_candidate",
        src="fallback.jpg",
        srcset="hero.jpg 1x",
        viewport_width=1000,
    )
    keep(
        "width_blocks_fallback",
        src="fallback.jpg",
        srcset="hero.jpg 200w",
        sizes="100px",
        viewport_width=1000,
    )
    keep(
        "narrow_viewport_picks_small",
        srcset="small.jpg 100w, large.jpg 400w",
        sizes="100vw",
        viewport_width=100,
    )
    keep(
        "narrow_viewport_high_ratio",
        srcset="small.jpg 100w, large.jpg 400w",
        sizes="100vw",
        viewport_width=100,
        device_pixel_ratio=2,
    )
    keep(
        "wide_viewport_picks_large",
        srcset="small.jpg 100w, large.jpg 400w",
        sizes="100vw",
        viewport_width=400,
    )
    keep("earlier_duplicate_density", srcset="a.jpg 2x, b.jpg 2x", device_pixel_ratio=2, viewport_width=1000)
    keep("ratio_above_every_candidate", srcset="a.jpg 1x, b.jpg 2x", device_pixel_ratio=3, viewport_width=1000)
    keep("zero_width_dropped", src="fallback.jpg", srcset="a.jpg 0w", viewport_width=1000)
    keep("zero_value_width_dropped", src="fallback.jpg", srcset="a.jpg 00w", viewport_width=1000)
    keep("uppercase_width_dropped", src="fallback.jpg", srcset="a.jpg 100W", sizes="100px", viewport_width=1000)
    keep("uppercase_density_dropped", src="fallback.jpg", srcset="a.jpg 2X", viewport_width=1000)
    keep("mixed_descriptors_dropped", src="fallback.jpg", srcset="a.jpg 100w 2x", sizes="100px", viewport_width=1000)
    keep("bare_height_dropped", src="fallback.jpg", srcset="a.jpg 20h", viewport_width=1000)
    keep(
        "height_with_width_kept",
        src="nope.jpg",
        srcset="a.jpg 100w 20h",
        sizes="100px",
        viewport_width=1000,
    )
    keep("zero_density_kept", srcset="a.jpg 0x", viewport_width=1000)
    keep("dangling_fraction_dropped", src="fallback.jpg", srcset="bad.jpg 5.x", viewport_width=1000)
    keep("leading_dot_density", srcset="half.jpg .5x, full.jpg 2x", viewport_width=1000)
    keep("leading_dot_kept", srcset="half.jpg .5x", viewport_width=1000)
    keep("exponent_one_suppresses_fallback", src="fallback.jpg", srcset="hero.jpg 1e0x", device_pixel_ratio=2, viewport_width=1000)
    keep(
        "sizes_media_matches",
        srcset="a.jpg 200w",
        sizes="(max-width: 600px) 100px, 50vw",
        viewport_width=500,
    )
    keep(
        "sizes_media_misses",
        srcset="a.jpg 200w",
        sizes="(max-width: 600px) 100px, 50vw",
        viewport_width=800,
    )
    keep(
        "bare_length_ends_list",
        srcset="a.jpg 100w",
        sizes="100px, 50vw",
        viewport_width=800,
    )
    keep(
        "calc_length",
        srcset="a.jpg 1800w",
        sizes="calc(100vw - 100px)",
        viewport_width=1000,
    )
    keep("auto_ignored", srcset="a.jpg 240w", sizes="auto, 80px", viewport_width=1000)
    keep(
        "auto_uses_layout_width",
        srcset="a.jpg 240w",
        sizes="auto, 80px",
        viewport_width=1000,
        auto_sizes=True,
        layout_width=240,
    )
    keep("zero_source_size", srcset="a.jpg 100w", sizes="0px", viewport_width=1000)
    keep(
        "negative_calc_uses_viewport",
        srcset="a.jpg 1000w",
        sizes="calc(0px - 10px)",
        viewport_width=1000,
    )
    keep("em_length", srcset="a.jpg 64w", sizes="2em", viewport_width=1000)
    keep(
        "picture_wide",
        src="fallback.png",
        viewport_width=800,
        supported_types=WEB,
        sources=[
            {"srcset": "art.avif 1x", "type": "image/avif"},
            {"srcset": "wide.webp 1x", "type": "image/webp", "media": "screen and (min-width: 700px)"},
            {"srcset": "narrow.webp 1x", "type": "image/webp", "media": "(max-width: 699px)"},
        ],
    )
    keep(
        "picture_narrow",
        src="fallback.png",
        viewport_width=500,
        supported_types=WEB,
        sources=[
            {"srcset": "art.avif 1x", "type": "image/avif"},
            {"srcset": "wide.webp 1x", "type": "image/webp", "media": "screen and (min-width: 700px)"},
            {"srcset": "narrow.webp 1x", "type": "image/webp", "media": "(max-width: 699px)"},
        ],
    )
    keep(
        "picture_type_falls_through",
        src="fallback.png",
        viewport_width=800,
        supported_types=("image/png",),
        sources=[{"srcset": "art.avif 1x", "type": "image/avif"}, {"srcset": "wide.webp 1x", "type": "image/webp"}],
    )
    keep(
        "print_media_skipped",
        viewport_width=1000,
        supported_types=WEB,
        sources=[
            {"srcset": "print.webp 1x", "media": "print", "type": "image/webp"},
            {"srcset": "screen.webp 1x", "media": "screen", "type": "image/webp"},
        ],
    )
    keep(
        "negated_screen_skipped",
        src="fallback.png",
        viewport_width=1000,
        supported_types=WEB,
        sources=[{"srcset": "nope.webp 1x", "media": "not screen", "type": "image/webp"}],
    )
    keep(
        "malformed_media_skipped",
        src="fallback.png",
        viewport_width=1000,
        supported_types=WEB,
        sources=[{"srcset": "nope.webp 1x", "media": "(((((", "type": "image/webp"}],
    )
    keep(
        "picture_ignores_img_src",
        src="fallback.jpg",
        viewport_width=1000,
        sources=[{"srcset": "wide.jpg 200w", "sizes": "100px"}],
    )
    keep(
        "mime_parameters",
        viewport_width=1000,
        supported_types=("image/webp",),
        sources=[{"srcset": "a.webp 1x", "type": "Image/WebP;charset=utf-8"}],
    )
    keep(
        "empty_source_skipped",
        viewport_width=1000,
        supported_types=WEB,
        sources=[{"srcset": "", "type": "image/webp"}, {"srcset": "ok.webp 1x", "type": "image/webp"}],
    )
    keep(
        "earlier_source_wins",
        viewport_width=1000,
        supported_types=WEB,
        sources=[
            {"srcset": "first.webp 1x", "type": "image/webp"},
            {"srcset": "second.webp 1x", "type": "image/webp"},
        ],
    )
    keep(
        "whitespace_srcset",
        srcset="  small.jpg   100w,\n  large.jpg   400w  ",
        sizes="100px",
        device_pixel_ratio=2,
        viewport_width=1000,
    )
    keep("nothing_to_load", src="", srcset="", viewport_width=1000)

    expected = {
        "comma_inside_url": ["https://cdn.example/a,b.png", 2, 1000, "img", None],
        "data_url_comma": ["data:image/gif;base64,AAAA", 1, 1000, "img", None],
        "comma_is_not_descriptor": ["hero.jpg", 1, 1000, "img", None],
        "explicit_density": ["hero.jpg", 2, 1000, "img", None],
        "fallback_for_higher_density": ["fallback.jpg", 1, 1000, "img", None],
        "explicit_one_keeps_candidate": ["hero.jpg", 1, 1000, "img", None],
        "width_blocks_fallback": ["hero.jpg", 2, 100, "img", None],
        "narrow_viewport_picks_small": ["small.jpg", 1, 100, "img", None],
        "narrow_viewport_high_ratio": ["large.jpg", 4, 100, "img", None],
        "wide_viewport_picks_large": ["large.jpg", 1, 400, "img", None],
        "earlier_duplicate_density": ["a.jpg", 2, 1000, "img", None],
        "ratio_above_every_candidate": ["b.jpg", 2, 1000, "img", None],
        "zero_width_dropped": ["fallback.jpg", 1, 1000, "img", None],
        "zero_value_width_dropped": ["fallback.jpg", 1, 1000, "img", None],
        "uppercase_width_dropped": ["fallback.jpg", 1, 100, "img", None],
        "uppercase_density_dropped": ["fallback.jpg", 1, 1000, "img", None],
        "mixed_descriptors_dropped": ["fallback.jpg", 1, 100, "img", None],
        "bare_height_dropped": ["fallback.jpg", 1, 1000, "img", None],
        "height_with_width_kept": ["a.jpg", 1, 100, "img", None],
        "zero_density_kept": ["a.jpg", 0, 1000, "img", None],
        "dangling_fraction_dropped": ["fallback.jpg", 1, 1000, "img", None],
        "leading_dot_density": ["full.jpg", 2, 1000, "img", None],
        "leading_dot_kept": ["half.jpg", 0.5, 1000, "img", None],
        "exponent_one_suppresses_fallback": ["hero.jpg", 1, 1000, "img", None],
        "sizes_media_matches": ["a.jpg", 2, 100, "img", None],
        "sizes_media_misses": ["a.jpg", 0.5, 400, "img", None],
        "bare_length_ends_list": ["a.jpg", 1, 100, "img", None],
        "calc_length": ["a.jpg", 2, 900, "img", None],
        "auto_ignored": ["a.jpg", 3, 80, "img", None],
        "auto_uses_layout_width": ["a.jpg", 1, 240, "img", None],
        "zero_source_size": ["a.jpg", "inf", 0, "img", None],
        "negative_calc_uses_viewport": ["a.jpg", 1, 1000, "img", None],
        "em_length": ["a.jpg", 2, 32, "img", None],
        "picture_wide": ["wide.webp", 1, 800, "source", 1],
        "picture_narrow": ["narrow.webp", 1, 500, "source", 2],
        "picture_type_falls_through": ["fallback.png", 1, 800, "img", None],
        "print_media_skipped": ["screen.webp", 1, 1000, "source", 1],
        "negated_screen_skipped": ["fallback.png", 1, 1000, "img", None],
        "malformed_media_skipped": ["fallback.png", 1, 1000, "img", None],
        "picture_ignores_img_src": ["wide.jpg", 2, 100, "source", 0],
        "mime_parameters": ["a.webp", 1, 1000, "source", 0],
        "empty_source_skipped": ["ok.webp", 1, 1000, "source", 1],
        "earlier_source_wins": ["first.webp", 1, 1000, "source", 0],
        "whitespace_srcset": ["large.jpg", 4, 100, "img", None],
        "nothing_to_load": ["", None, 1000, "", None],
    }
    return observed == expected, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
