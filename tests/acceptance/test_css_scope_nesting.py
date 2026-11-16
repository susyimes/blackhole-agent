"""Nested style rules inside @scope keep the scope and the parent selector.

A descendant, a direct child, a scope-relative parent, a scope limit, the
most specific parent, an invalid inner selector, nearer-scope proximity,
an ampersand, two levels, and an important layer all stay observable through
cascaded color. A reader that rejects the nest is an unmet outcome, not a crash.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

CARD = (
    "<!DOCTYPE html><html><body>"
    "<div class='card'><span id='span'><em id='in'></em><i><em id='grand'></em></i></span>"
    "<div class='limit'><span><em id='lim'></em></span></div></div>"
    "<span><em id='out'></em></span>"
    "</body></html>"
)
OUTSIDE_SPAN = (
    "<!DOCTYPE html><html><body>"
    "<span><div class='card'><em id='t'></em></div></span>"
    "</body></html>"
)
DIRECT_SPAN = (
    "<!DOCTYPE html><html><body><div class='card'>"
    "<span><em id='direct'></em></span>"
    "<div><span><em id='deep'></em></span></div>"
    "</div></body></html>"
)
SPEC = (
    "<!DOCTYPE html><html><body>"
    "<div class='card'><article><span id='in'></span></article>"
    "<div id='shot'><span></span></div></div>"
    "<article><span id='out'></span></article>"
    "</body></html>"
)
NEAR = (
    "<!DOCTYPE html><html><body><div class='outer'><div class='inner'>"
    "<span><em id='t'></em></span>"
    "</div></div></body></html>"
)
AMP = (
    "<!DOCTYPE html><html><body><div class='card'>"
    "<em id='loose'></em><span><em id='in'></em></span>"
    "</div></body></html>"
)
TWO = (
    "<!DOCTYPE html><html><body>"
    "<div class='card'><span><em><b id='in'></b></em></span></div>"
    "<span><em><b id='out'></b></em></span>"
    "</body></html>"
)
LAYER = (
    "<!DOCTYPE html><html><body><div class='card'><span><em id='t'></em></span></div>"
    "</body></html>"
)
INVALID = (
    "<!DOCTYPE html><html><body>"
    "<div class='card'><span id='in'></span></div>"
    "<span id='out'></span><em id='later'></em>"
    "</body></html>"
)

EXPECTED = {
    "descendant_in": "red",
    "descendant_grand": "red",
    "descendant_out": "blue",
    "child_direct": "red",
    "child_grand": "blue",
    "scope_child_direct": "red",
    "scope_child_deep": "blue",
    "parent_outside_scope": "blue",
    "limit_in": "red",
    "limit_excluded": "blue",
    "specific_parent": "red",
    "specific_parent_out": "blue",
    "invalid_keeps_parent": "green",
    "invalid_keeps_outside": "blue",
    "invalid_keeps_later": "teal",
    "nearer_scope": "red",
    "ampersand_in": "red",
    "ampersand_loose": "blue",
    "two_levels_in": "red",
    "two_levels_out": "blue",
    "parent_color": "green",
    "nested_color": "red",
    "layer_important": "red",
}

CASES = (
    (
        "descendant_in",
        CARD,
        "in",
        "em { color: blue } @scope (.card) { span { em { color: red } } }",
    ),
    (
        "descendant_grand",
        CARD,
        "grand",
        "em { color: blue } @scope (.card) { span { em { color: red } } }",
    ),
    (
        "descendant_out",
        CARD,
        "out",
        "em { color: blue } @scope (.card) { span { em { color: red } } }",
    ),
    (
        "child_direct",
        CARD,
        "in",
        "em { color: blue } @scope (.card) { span { > em { color: red } } }",
    ),
    (
        "child_grand",
        CARD,
        "grand",
        "em { color: blue } @scope (.card) { span { > em { color: red } } }",
    ),
    (
        "scope_child_direct",
        DIRECT_SPAN,
        "direct",
        "em { color: blue } @scope (.card) { > span { em { color: red } } }",
    ),
    (
        "scope_child_deep",
        DIRECT_SPAN,
        "deep",
        "em { color: blue } @scope (.card) { > span { em { color: red } } }",
    ),
    (
        "parent_outside_scope",
        OUTSIDE_SPAN,
        "t",
        "em { color: blue } @scope (.card) { span { em { color: red } } }",
    ),
    (
        "limit_in",
        CARD,
        "in",
        "em { color: blue } @scope (.card) to (.limit) { span { em { color: red } } }",
    ),
    (
        "limit_excluded",
        CARD,
        "lim",
        "em { color: blue } @scope (.card) to (.limit) { span { em { color: red } } }",
    ),
    (
        "specific_parent",
        SPEC,
        "in",
        "@scope (.card) { article, #shot { span { color: red } } } article span { color: blue }",
    ),
    (
        "specific_parent_out",
        SPEC,
        "out",
        "@scope (.card) { article, #shot { span { color: red } } } article span { color: blue }",
    ),
    (
        "invalid_keeps_parent",
        INVALID,
        "in",
        "span { color: blue } @scope (.card) { span { color: green; :hover { color: red } } } em { color: teal }",
    ),
    (
        "invalid_keeps_outside",
        INVALID,
        "out",
        "span { color: blue } @scope (.card) { span { color: green; :hover { color: red } } } em { color: teal }",
    ),
    (
        "invalid_keeps_later",
        INVALID,
        "later",
        "span { color: blue } @scope (.card) { span { color: green; :hover { color: red } } } em { color: teal }",
    ),
    (
        "nearer_scope",
        NEAR,
        "t",
        "@scope (.outer) { span { em { color: blue } } } @scope (.inner) { span { em { color: red } } }",
    ),
    (
        "ampersand_in",
        AMP,
        "in",
        "em { color: blue } @scope (.card) { span { & em { color: red } } }",
    ),
    (
        "ampersand_loose",
        AMP,
        "loose",
        "em { color: blue } @scope (.card) { span { & em { color: red } } }",
    ),
    (
        "two_levels_in",
        TWO,
        "in",
        "b { color: blue } @scope (.card) { span { em { b { color: red } } } }",
    ),
    (
        "two_levels_out",
        TWO,
        "out",
        "b { color: blue } @scope (.card) { span { em { b { color: red } } } }",
    ),
    (
        "parent_color",
        CARD,
        "span",
        "@scope (.card) { span { color: green; em { color: red } } }",
    ),
    (
        "nested_color",
        CARD,
        "in",
        "@scope (.card) { span { color: green; em { color: red } } }",
    ),
    (
        "layer_important",
        LAYER,
        "t",
        "@layer early, late; @layer early { @scope (.card) { span { em { color: red !important } } } } "
        "@layer late { em { color: blue !important } }",
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
        except Exception as exc:  # noqa: BLE001 - a rejected nest is an unmet outcome
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
