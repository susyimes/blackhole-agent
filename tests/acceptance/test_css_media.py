"""CSS @media keeps a conditional group only when the viewport matches.

A min-width or max-width edge, a comma, not, and, only, a media type, an
unknown feature, a width range, color scheme, reduced motion, and orientation
change the winning color. A nested condition, a declaration inside a style
rule, that rule's parent specificity, an early-layer important declaration,
and a span inside a scope root do too. An omitted media map leaves a
min-width rule unmatched. A malformed query does not discard a later rule.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A reader that rejects @media is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

P = "<!DOCTYPE html><html><body><p id='t'></p></body></html>"
CARD = "<!DOCTYPE html><html><body><p id='t' class='card'></p></body></html>"
ARTICLE = "<!DOCTYPE html><html><body><article id='plain'><span id='t'></span></article></body></html>"
SCOPE = (
    "<!DOCTYPE html><html><body><div class='card'><span id='in'></span></div>"
    "<span id='out'></span></body></html>"
)
OMIT = None

EXPECTED = {
    "min_width_hit": "red",
    "min_width_miss": "blue",
    "max_width_hit": "red",
    "max_width_miss": "blue",
    "comma_low": "red",
    "comma_mid": "blue",
    "comma_high": "red",
    "not_narrow": "red",
    "not_wide": "blue",
    "not_print": "red",
    "and_hit": "red",
    "and_miss": "blue",
    "only_screen": "red",
    "only_print": "blue",
    "unknown_feature": "blue",
    "malformed_keeps_later": "green",
    "range_below": "blue",
    "range_hit": "red",
    "range_above": "blue",
    "dark": "red",
    "light": "blue",
    "reduced_motion": "red",
    "no_reduced_motion": "blue",
    "landscape": "red",
    "portrait": "blue",
    "nested_condition_hit": "red",
    "nested_condition_miss": "blue",
    "style_declaration_hit": "red",
    "style_declaration_miss": "blue",
    "parent_specificity": "red",
    "parent_specificity_miss": "blue",
    "layer_important_hit": "red",
    "layer_important_miss": "blue",
    "scope_inside": "red",
    "scope_outside": "blue",
    "scope_narrow": "blue",
    "omitted_media": "blue",
    "empty_query": "red",
    "casefold": "red",
    "min_height_hit": "red",
    "min_height_miss": "blue",
    "all_on_print": "red",
    "bare_all": "red",
    "screen_on_print": "blue",
    "not_all": "blue",
}

# name, markup, element, sheet, media (None omits the argument), 
CASES = (
    ("min_width_hit", P, "t", "#t { color: blue } @media (min-width: 600px) { #t { color: red } }", {"width": 600}),
    ("min_width_miss", P, "t", "#t { color: blue } @media (min-width: 600px) { #t { color: red } }", {"width": 599}),
    ("max_width_hit", P, "t", "#t { color: blue } @media (max-width: 400px) { #t { color: red } }", {"width": 400}),
    ("max_width_miss", P, "t", "#t { color: blue } @media (max-width: 400px) { #t { color: red } }", {"width": 401}),
    (
        "comma_low",
        P,
        "t",
        "#t { color: blue } @media (max-width: 200px), (min-width: 800px) { #t { color: red } }",
        {"width": 100},
    ),
    (
        "comma_mid",
        P,
        "t",
        "#t { color: blue } @media (max-width: 200px), (min-width: 800px) { #t { color: red } }",
        {"width": 500},
    ),
    (
        "comma_high",
        P,
        "t",
        "#t { color: blue } @media (max-width: 200px), (min-width: 800px) { #t { color: red } }",
        {"width": 900},
    ),
    (
        "not_narrow",
        P,
        "t",
        "#t { color: blue } @media not screen and (min-width: 600px) { #t { color: red } }",
        {"type": "screen", "width": 100},
    ),
    (
        "not_wide",
        P,
        "t",
        "#t { color: blue } @media not screen and (min-width: 600px) { #t { color: red } }",
        {"type": "screen", "width": 800},
    ),
    (
        "not_print",
        P,
        "t",
        "#t { color: blue } @media not screen and (min-width: 600px) { #t { color: red } }",
        {"type": "print", "width": 800},
    ),
    (
        "and_hit",
        P,
        "t",
        "#t { color: blue } @media (min-width: 400px) and (max-width: 700px) { #t { color: red } }",
        {"width": 500},
    ),
    (
        "and_miss",
        P,
        "t",
        "#t { color: blue } @media (min-width: 400px) and (max-width: 700px) { #t { color: red } }",
        {"width": 900},
    ),
    (
        "only_screen",
        P,
        "t",
        "#t { color: blue } @media only screen and (min-width: 400px) { #t { color: red } }",
        {"type": "screen", "width": 400},
    ),
    (
        "only_print",
        P,
        "t",
        "#t { color: blue } @media only screen and (min-width: 400px) { #t { color: red } }",
        {"type": "print", "width": 800},
    ),
    (
        "unknown_feature",
        P,
        "t",
        "#t { color: blue } @media (min-width: 1px) and (hover: hover) { #t { color: red } }",
        {"width": 900},
    ),
    (
        "malformed_keeps_later",
        P,
        "t",
        "#t { color: blue } @media (min-width:) { #t { color: red } } #t { color: green }",
        {"width": 900},
    ),
    (
        "range_below",
        P,
        "t",
        "#t { color: blue } @media (400px <= width < 800px) { #t { color: red } }",
        {"width": 399},
    ),
    (
        "range_hit",
        P,
        "t",
        "#t { color: blue } @media (400px <= width < 800px) { #t { color: red } }",
        {"width": 400},
    ),
    (
        "range_above",
        P,
        "t",
        "#t { color: blue } @media (400px <= width < 800px) { #t { color: red } }",
        {"width": 800},
    ),
    (
        "dark",
        P,
        "t",
        "#t { color: blue } @media (prefers-color-scheme: dark) { #t { color: red } }",
        {"prefers-color-scheme": "dark"},
    ),
    (
        "light",
        P,
        "t",
        "#t { color: blue } @media (prefers-color-scheme: dark) { #t { color: red } }",
        {"prefers-color-scheme": "light"},
    ),
    (
        "reduced_motion",
        P,
        "t",
        "#t { color: blue } @media (prefers-reduced-motion: reduce) { #t { color: red } }",
        {"prefers-reduced-motion": "reduce"},
    ),
    (
        "no_reduced_motion",
        P,
        "t",
        "#t { color: blue } @media (prefers-reduced-motion: reduce) { #t { color: red } }",
        {"prefers-reduced-motion": "no-preference"},
    ),
    (
        "landscape",
        P,
        "t",
        "#t { color: blue } @media (orientation: landscape) { #t { color: red } }",
        {"width": 800, "height": 600},
    ),
    (
        "portrait",
        P,
        "t",
        "#t { color: blue } @media (orientation: landscape) { #t { color: red } }",
        {"width": 600, "height": 800},
    ),
    (
        "nested_condition_hit",
        P,
        "t",
        "#t { color: blue } @media (min-width: 400px) { @media (max-width: 700px) { #t { color: red } } }",
        {"width": 500},
    ),
    (
        "nested_condition_miss",
        P,
        "t",
        "#t { color: blue } @media (min-width: 400px) { @media (max-width: 700px) { #t { color: red } } }",
        {"width": 900},
    ),
    (
        "style_declaration_hit",
        CARD,
        "t",
        ".card { color: blue; @media (min-width: 500px) { color: red } }",
        {"width": 500},
    ),
    (
        "style_declaration_miss",
        CARD,
        "t",
        ".card { color: blue; @media (min-width: 500px) { color: red } }",
        {"width": 10},
    ),
    (
        "parent_specificity",
        ARTICLE,
        "t",
        "article, #shot { @media (min-width: 1px) { span { color: red } } } article span { color: blue }",
        {"width": 1},
    ),
    (
        "parent_specificity_miss",
        ARTICLE,
        "t",
        "article, #shot { @media (min-width: 1px) { span { color: red } } } article span { color: blue }",
        {"width": 0},
    ),
    (
        "layer_important_hit",
        P,
        "t",
        "@layer early { @media (min-width: 500px) { #t { color: red !important } } } "
        "@layer late { #t { color: blue !important } }",
        {"width": 500},
    ),
    (
        "layer_important_miss",
        P,
        "t",
        "@layer early { @media (min-width: 500px) { #t { color: red !important } } } "
        "@layer late { #t { color: blue !important } }",
        {"width": 100},
    ),
    (
        "scope_inside",
        SCOPE,
        "in",
        "span { color: blue } @scope (.card) { @media (min-width: 400px) { span { color: red } } }",
        {"width": 400},
    ),
    (
        "scope_outside",
        SCOPE,
        "out",
        "span { color: blue } @scope (.card) { @media (min-width: 400px) { span { color: red } } }",
        {"width": 400},
    ),
    (
        "scope_narrow",
        SCOPE,
        "in",
        "span { color: blue } @scope (.card) { @media (min-width: 400px) { span { color: red } } }",
        {"width": 100},
    ),
    ("omitted_media", P, "t", "#t { color: blue } @media (min-width: 1px) { #t { color: red } }", OMIT),
    ("empty_query", P, "t", "#t { color: blue } @media { #t { color: red } }", {"width": 0}),
    ("casefold", P, "t", "#t { color: blue } @MEDIA (MIN-WIDTH: 10px) { #t { color: red } }", {"width": 10}),
    (
        "min_height_hit",
        P,
        "t",
        "#t { color: blue } @media (min-height: 500px) { #t { color: red } }",
        {"height": 500},
    ),
    (
        "min_height_miss",
        P,
        "t",
        "#t { color: blue } @media (min-height: 500px) { #t { color: red } }",
        {"height": 499},
    ),
    (
        "all_on_print",
        P,
        "t",
        "#t { color: blue } @media all and (min-width: 1px) { #t { color: red } }",
        {"type": "print", "width": 10},
    ),
    ("bare_all", P, "t", "#t { color: blue } @media all { #t { color: red } }", {"type": "print"}),
    ("screen_on_print", P, "t", "#t { color: blue } @media screen { #t { color: red } }", {"type": "print"}),
    ("not_all", P, "t", "#t { color: blue } @media not all { #t { color: red } }", {"type": "screen", "width": 800}),
)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_selectors import cascaded_value
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    for name, markup, element_id, sheet, media in CASES:
        try:
            if media is OMIT:
                observed[name] = cascaded_value(markup, sheet, element_id, "color")
            else:
                observed[name] = cascaded_value(markup, sheet, element_id, "color", media=media)
        except Exception as exc:  # noqa: BLE001 - a rejected stylesheet is an unmet outcome
            observed[name] = f"{type(exc).__name__}: {exc}"
    return observed == EXPECTED, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
