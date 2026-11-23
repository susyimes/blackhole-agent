"""CSS @supports keeps a block only when this reader supports the condition.

A color declaration, a custom property, and selector() can keep the block.
A length assigned to color, an unknown property, :hover, a pseudo-element,
a leading combinator, a selector list, font-tech, font-format, an empty
prelude, and mixed and/or do not. The kept block stays in its layer, scope,
and nesting parent.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A reader that rejects @supports is an unmet outcome, not a crash.
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

EXPECTED = {
    "color_named": "red",
    "color_hash": "red",
    "color_function": "red",
    "color_case_important": "red",
    "color_length": "blue",
    "color_wide": "red",
    "custom_property": "red",
    "custom_words": "red",
    "custom_empty": "blue",
    "unknown_property": "blue",
    "selector_has_child": "red",
    "selector_wrapped": "red",
    "selector_hover": "blue",
    "selector_leading": "blue",
    "selector_pseudo": "red",
    "selector_list": "blue",
    "not_length": "red",
    "not_color": "blue",
    "or_length": "red",
    "and_display": "blue",
    "font_tech": "blue",
    "font_or_color": "red",
    "font_format": "blue",
    "empty_prelude": "blue",
    "malformed_keeps_later": "green",
    "whitespace": "red",
    "mystery_or": "red",
    "nested_supports": "red",
    "parent_specificity": "red",
    "parent_specificity_miss": "blue",
    "nested_declaration": "red",
    "nested_declaration_miss": "blue",
    "layer_important": "red",
    "layer_important_miss": "blue",
    "scope_inside": "red",
    "scope_outside": "blue",
}

CASES = (
    ("color_named", P, "t", "#t { color: blue } @supports (color: red) { #t { color: red } }"),
    ("color_hash", P, "t", "#t { color: blue } @supports (color: #fff) { #t { color: red } }"),
    ("color_function", P, "t", "#t { color: blue } @supports (color: rgb(1, 2, 3)) { #t { color: red } }"),
    (
        "color_case_important",
        P,
        "t",
        "#t { color: blue } @supports (COLOR: Red !important) { #t { color: red } }",
    ),
    ("color_length", P, "t", "#t { color: blue } @supports (color: 12px) { #t { color: red } }"),
    ("color_wide", P, "t", "#t { color: blue } @supports (color: inherit) { #t { color: red } }"),
    ("custom_property", P, "t", "#t { color: blue } @supports (--brand: 12px) { #t { color: red } }"),
    (
        "custom_words",
        P,
        "t",
        "#t { color: blue } @supports (--note: bread and butter) { #t { color: red } }",
    ),
    ("custom_empty", P, "t", "#t { color: blue } @supports (--brand:) { #t { color: red } }"),
    ("unknown_property", P, "t", "#t { color: blue } @supports (display: grid) { #t { color: red } }"),
    (
        "selector_has_child",
        P,
        "t",
        "#t { color: blue } @supports selector(:has(> img)) { #t { color: red } }",
    ),
    (
        "selector_wrapped",
        P,
        "t",
        "#t { color: blue } @supports (selector(:has(img))) { #t { color: red } }",
    ),
    ("selector_hover", P, "t", "#t { color: blue } @supports selector(:hover) { #t { color: red } }"),
    ("selector_leading", P, "t", "#t { color: blue } @supports selector(> img) { #t { color: red } }"),
    ("selector_pseudo", P, "t", "#t { color: blue } @supports selector(::before) { #t { color: red } }"),
    ("selector_list", P, "t", "#t { color: blue } @supports selector(a, b) { #t { color: red } }"),
    ("not_length", P, "t", "#t { color: blue } @supports not (color: 12px) { #t { color: red } }"),
    ("not_color", P, "t", "#t { color: blue } @supports not (color: red) { #t { color: red } }"),
    (
        "or_length",
        P,
        "t",
        "#t { color: blue } @supports (color: red) or (color: 12px) { #t { color: red } }",
    ),
    (
        "and_display",
        P,
        "t",
        "#t { color: blue } @supports (color: red) and (display: grid) { #t { color: red } }",
    ),
    (
        "font_tech",
        P,
        "t",
        "#t { color: blue } @supports font-tech(color-COLRv1) { #t { color: red } }",
    ),
    (
        "font_or_color",
        P,
        "t",
        "#t { color: blue } @supports font-tech(color-COLRv1) or (color: red) { #t { color: red } }",
    ),
    ("font_format", P, "t", "#t { color: blue } @supports font-format(woff2) { #t { color: red } }"),
    ("empty_prelude", P, "t", "#t { color: blue } @supports { #t { color: red } }"),
    (
        "malformed_keeps_later",
        P,
        "t",
        "#t { color: green } @supports (color: red) and (color: blue) or (color: green) { #t { color: red } }",
    ),
    ("whitespace", P, "t", "#t { color: blue } @supports ( color : red ) { #t { color: red } }"),
    (
        "mystery_or",
        P,
        "t",
        "#t { color: blue } @supports mystery(1) or (color: red) { #t { color: red } }",
    ),
    (
        "nested_supports",
        P,
        "t",
        "#t { color: blue } @supports (color: red) { @supports not (color: 12px) { #t { color: red } } }",
    ),
    (
        "parent_specificity",
        ARTICLE,
        "t",
        "article, #shot { @supports (color: red) { span { color: red } } } article span { color: blue }",
    ),
    (
        "parent_specificity_miss",
        ARTICLE,
        "t",
        "article, #shot { @supports (color: 12px) { span { color: red } } } article span { color: blue }",
    ),
    (
        "nested_declaration",
        CARD,
        "t",
        ".card { color: blue; @supports (color: red) { color: red } }",
    ),
    (
        "nested_declaration_miss",
        CARD,
        "t",
        ".card { color: blue; @supports (color: 12px) { color: red } }",
    ),
    (
        "layer_important",
        P,
        "t",
        "@layer early { @supports (color: red) { #t { color: red !important } } } "
        "@layer late { #t { color: blue !important } }",
    ),
    (
        "layer_important_miss",
        P,
        "t",
        "@layer early { @supports (color: 12px) { #t { color: red !important } } } "
        "@layer late { #t { color: blue !important } }",
    ),
    (
        "scope_inside",
        SCOPE,
        "in",
        "span { color: blue } @scope (.card) { @supports (color: red) { span { color: red } } }",
    ),
    (
        "scope_outside",
        SCOPE,
        "out",
        "span { color: blue } @scope (.card) { @supports (color: red) { span { color: red } } }",
    ),
)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_selectors import cascaded_value
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    for name, markup, element_id, sheet in CASES:
        try:
            observed[name] = cascaded_value(markup, sheet, element_id, "color")
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
