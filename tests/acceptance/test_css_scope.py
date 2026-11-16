"""CSS @scope keeps rules inside a root and ranks nearer roots after specificity.

An earlier equal-specificity color in a nearer scope beats a later color in a
farther scope. An id in the farther scope still beats a type selector in the
nearer one. The scope-root selector does not add specificity. A scope limit
and its descendants are excluded. :scope beats a later ampersand. A scoped
rule beats a later unscoped rule of equal specificity. A child combinator
does not reach a grandchild. A later layer beats an earlier, closer, more
specific scope, and an earlier important layer beats a later closer important
id. A style rule inside @layer inside @scope does not paint outside the root.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A reader that rejects @scope is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

NEAR = "<!DOCTYPE html><html><body><div class='far'><div class='near'><p id='t'></p></div></div></body></html>"
HERO = "<!DOCTYPE html><html><body><div id='hero'><p id='t' class='item'></p></div></body></html>"
LIMIT = (
    "<!DOCTYPE html><html><body><div class='root'>"
    "<p id='inside'></p><section class='limit' id='edge'><p id='below'></p></section>"
    "</div></body></html>"
)
ROOT = "<!DOCTYPE html><html><body><div class='root' id='t'><p id='child'></p></div></body></html>"
CHILD = (
    "<!DOCTYPE html><html><body><div class='root'><p id='child'></p>"
    "<div><p id='grand'></p></div></div></body></html>"
)
NEST = (
    "<!DOCTYPE html><html><body><div class='outer'><div class='inner'>"
    "<p id='t' class='content'></p><div class='limit'><p id='out' class='content'></p></div>"
    "</div></div></body></html>"
)
OUTSIDE = (
    "<!DOCTYPE html><html><body><div class='outside'><div class='root'>"
    "<p id='t'></p></div></div></body></html>"
)
OVERLAP = (
    "<!DOCTYPE html><html><body><section class='main' id='main'>"
    "<section class='sub' id='sub'><p id='para'></p></section></section></body></html>"
)
LAYER_SCOPE = (
    "<!DOCTYPE html><html><body><div class='root'><p id='t'></p></div><p id='out'></p></body></html>"
)

EXPECTED = {
    "nearer_equal_specificity": "green",
    "specificity_beats_proximity": "red",
    "prelude_not_in_specificity": "red",
    "scoped_beats_later_unscoped": "green",
    "limit_inside": "green",
    "limit_edge": "red",
    "limit_below": "red",
    "scope_beats_ampersand": "green",
    "bare_declaration_on_root": "green",
    "bare_declaration_skips_child": "red",
    "child_combinator": "green",
    "child_combinator_skips_grandchild": "red",
    "later_layer_beats_closer_scope": "green",
    "earlier_important_layer": "green",
    "nested_inner_proximity": "green",
    "nested_limit_inside": "green",
    "nested_limit_outside": "red",
    "ancestor_can_sit_outside": "green",
    "relative_selector_misses_outside_ancestor": "red",
    "overlap_keeps_inner_root": "green",
    "overlap_excludes_limit_child": "red",
    "layer_inside_scope": "green",
    "layer_inside_scope_outside_root": "red",
    "implicit_document_root": "green",
}

CASES = (
    ("nearer_equal_specificity", NEAR, "t", "@scope (.near) { p { color: green } } @scope (.far) { p { color: red } }"),
    (
        "specificity_beats_proximity",
        NEAR,
        "t",
        "@scope (.near) { p { color: green } } @scope (.far) { #t { color: red } }",
    ),
    (
        "prelude_not_in_specificity",
        HERO,
        "t",
        "@scope (#hero) { p { color: green } } .item { color: red }",
    ),
    (
        "scoped_beats_later_unscoped",
        HERO,
        "t",
        "@scope (#hero) { p { color: green } } p { color: red }",
    ),
    (
        "limit_inside",
        LIMIT,
        "inside",
        "@scope (.root) to (.limit) { p, section { color: green } } p, section { color: red }",
    ),
    (
        "limit_edge",
        LIMIT,
        "edge",
        "@scope (.root) to (.limit) { p, section { color: green } } p, section { color: red }",
    ),
    (
        "limit_below",
        LIMIT,
        "below",
        "@scope (.root) to (.limit) { p, section { color: green } } p, section { color: red }",
    ),
    (
        "scope_beats_ampersand",
        ROOT,
        "t",
        "@scope (.root) { :scope { color: green } & { color: red } }",
    ),
    (
        "bare_declaration_on_root",
        ROOT,
        "t",
        "@scope (.root) { color: green } * { color: red }",
    ),
    (
        "bare_declaration_skips_child",
        ROOT,
        "child",
        "@scope (.root) { color: green } * { color: red }",
    ),
    (
        "child_combinator",
        CHILD,
        "child",
        "@scope (.root) { > p { color: green } } p { color: red }",
    ),
    (
        "child_combinator_skips_grandchild",
        CHILD,
        "grand",
        "@scope (.root) { > p { color: green } } p { color: red }",
    ),
    (
        "later_layer_beats_closer_scope",
        NEAR,
        "t",
        """
        @layer base, theme;
        @layer base { @scope (.near) { #t { color: red } } }
        @layer theme { @scope (.far) { p { color: green } } }
        """,
    ),
    (
        "earlier_important_layer",
        NEAR,
        "t",
        """
        @layer base, theme;
        @layer base { @scope (.far) { p { color: green !important } } }
        @layer theme { @scope (.near) { #t { color: red !important } } }
        """,
    ),
    (
        "nested_inner_proximity",
        NEST,
        "t",
        "@scope (.outer) { @scope (.inner) { p { color: green } } p { color: red } }",
    ),
    (
        "nested_limit_inside",
        NEST,
        "t",
        """
        @scope (.outer) {
          @scope (:scope > .inner) to (:scope .limit) { .content { color: green } }
        }
        .content { color: red }
        """,
    ),
    (
        "nested_limit_outside",
        NEST,
        "out",
        """
        @scope (.outer) {
          @scope (:scope > .inner) to (:scope .limit) { .content { color: green } }
        }
        .content { color: red }
        """,
    ),
    (
        "ancestor_can_sit_outside",
        OUTSIDE,
        "t",
        "@scope (.root) { .outside :scope p { color: green } } p { color: red }",
    ),
    (
        "relative_selector_misses_outside_ancestor",
        OUTSIDE,
        "t",
        "@scope (.root) { .outside p { color: green } } p { color: red }",
    ),
    (
        "overlap_keeps_inner_root",
        OVERLAP,
        "sub",
        "@scope (.main) to (.sub > *) { section, p { color: green } } section, p { color: red }",
    ),
    (
        "overlap_excludes_limit_child",
        OVERLAP,
        "para",
        "@scope (.main) to (.sub > *) { section, p { color: green } } section, p { color: red }",
    ),
    (
        "layer_inside_scope",
        LAYER_SCOPE,
        "t",
        """
        @scope (.root) { @layer theme { p { color: green } } }
        @layer theme { p { color: red } }
        """,
    ),
    (
        "layer_inside_scope_outside_root",
        LAYER_SCOPE,
        "out",
        """
        @scope (.root) { @layer theme { p { color: green } } }
        @layer theme { p { color: red } }
        """,
    ),
    (
        "implicit_document_root",
        "<!DOCTYPE html><html><body><p id='t'></p></body></html>",
        "t",
        "@scope { p { color: green } } p { color: red }",
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
            return False, {"error": f"{name}: {type(exc).__name__}: {exc}", "observed": observed}
    return observed == EXPECTED, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
