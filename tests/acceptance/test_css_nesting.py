"""A nested style rule substitutes the parent selector list.

The most specific parent supplies specificity for every parent, including the
parent that did not match. A selector with no nesting selector is a
descendant, a leading child combinator stays direct, and an ampersand
compounds with or follows the parent. A later declaration in the same rule
still wins. An invalid nested selector is ignored. A nested rule inside a
layer stays in that layer, so an earlier unlayered rule beats it.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A reader that rejects the inner rule is an unmet outcome,
not a crash.
"""

from __future__ import annotations

import json

PLAIN = "<!DOCTYPE html><html><body><article id='plain'><span id='t'></span></article></body></html>"
CHILD = (
    "<!DOCTYPE html><html><body><div class='card'><span id='child'></span>"
    "<div><span id='grand'></span></div></div></body></html>"
)
HOT = "<!DOCTYPE html><html><body><p id='hot' class='card hot'></p><p id='plain' class='card'></p></body></html>"
WRAP = (
    "<!DOCTYPE html><html><body><div class='wrap'><p id='inside' class='card'></p></div>"
    "<p id='outside' class='card'></p></body></html>"
)
CARD = "<!DOCTYPE html><html><body><p id='t' class='card'></p></body></html>"
EM = "<!DOCTYPE html><html><body><div class='card'><span><em id='t'></em></span></div></body></html>"
LATE = "<!DOCTYPE html><html><body><div class='card'><span id='t'></span></div></body></html>"

EXPECTED = {
    "parent_id_specificity": "red",
    "direct_child": "red",
    "grandchild": "blue",
    "ampersand_compound": "red",
    "plain_card": "blue",
    "ancestor_ampersand": "red",
    "outside_ancestor": "blue",
    "later_declaration": "green",
    "invalid_nested_keeps_parent": "blue",
    "two_levels": "red",
    "nested_rule_stays_in_layer": "blue",
}

CASES = (
    (
        "parent_id_specificity",
        PLAIN,
        "t",
        "article, #shot { span { color: red } } article span { color: blue }",
    ),
    (
        "direct_child",
        CHILD,
        "child",
        ".card { > span { color: red } } span { color: blue }",
    ),
    (
        "grandchild",
        CHILD,
        "grand",
        ".card { > span { color: red } } span { color: blue }",
    ),
    (
        "ampersand_compound",
        HOT,
        "hot",
        ".card { color: blue; &.hot { color: red } }",
    ),
    (
        "plain_card",
        HOT,
        "plain",
        ".card { color: blue; &.hot { color: red } }",
    ),
    (
        "ancestor_ampersand",
        WRAP,
        "inside",
        ".card { color: blue; .wrap & { color: red } }",
    ),
    (
        "outside_ancestor",
        WRAP,
        "outside",
        ".card { color: blue; .wrap & { color: red } }",
    ),
    (
        "later_declaration",
        CARD,
        "t",
        ".card { color: blue; & { color: red } color: green; }",
    ),
    (
        "invalid_nested_keeps_parent",
        CARD,
        "t",
        ".card { color: blue; :hover { color: red } }",
    ),
    (
        "two_levels",
        EM,
        "t",
        ".card { span { em { color: red } } } span em { color: blue }",
    ),
    (
        "nested_rule_stays_in_layer",
        LATE,
        "t",
        "span { color: blue } @layer late { .card { span { color: red } } }",
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
