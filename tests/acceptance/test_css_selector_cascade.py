"""A CSS selector distinguishes a matching sibling from a child index.

:nth-child(2 of .item) is the second item, not the second child. A later
:where() rule loses to an earlier type rule. :is() and :not() keep the
specificity of their most specific argument. An important declaration beats
an identifier.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the reader is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

MARKUP = (
    "<!DOCTYPE html><html><body><div id=\"box\">"
    "<span class=\"item\" id=\"a\"></span>"
    "<div id=\"mid\"></div>"
    "<span class=\"item\" id=\"b\"></span>"
    "</div></body></html>"
)
NESTED = (
    "<!DOCTYPE html><html><body><div id=\"want\">"
    "<span id=\"ok\"><span id=\"near\"><b id=\"target\"></b></span></span>"
    "</div></body></html>"
)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_selectors import (
            cascaded_value,
            matched_ids,
            selector_specificity,
        )
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    try:
        of_item = matched_ids(MARKUP, ":nth-child(2 of .item)")
        second_child = matched_ids(MARKUP, ":nth-child(2)")
        odd_item = matched_ids(MARKUP, ":nth-child(odd of .item)")
        where_color = cascaded_value(
            MARKUP,
            "span { color: red } :where(.item) { color: green }",
            "b",
            "color",
        )
        is_color = cascaded_value(
            MARKUP,
            ":is(.item, #pin) { color: blue } .item { color: red }",
            "b",
            "color",
        )
        not_color = cascaded_value(
            MARKUP,
            ":not(div, #pin) { color: blue } .item { color: red }",
            "b",
            "color",
        )
        important_color = cascaded_value(
            MARKUP,
            "#b { color: blue } .item { color: red !important }",
            "b",
            "color",
        )
        nested = matched_ids(NESTED, "div#want > span b")
        specificity = {
            "where": selector_specificity(":where(.item)"),
            "is": selector_specificity(":is(.item, #pin)"),
            "not": selector_specificity(":not(div, #pin)"),
            "type": selector_specificity("span"),
            "nth": selector_specificity(":nth-child(2 of .item)"),
        }
    except Exception as exc:  # noqa: BLE001 - a broken reader is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed = {
        "of_item": of_item,
        "second_child": second_child,
        "odd_item": odd_item,
        "where_color": where_color,
        "is_color": is_color,
        "not_color": not_color,
        "important_color": important_color,
        "nested": nested,
        "specificity": specificity,
    }
    passed = (
        of_item == ["b"]
        and second_child == ["mid"]
        and odd_item == ["a"]
        and where_color == "red"
        and is_color == "blue"
        and not_color == "blue"
        and important_color == "red"
        and nested == ["target"]
        and specificity["where"] == [[0, 0, 0]]
        and specificity["is"] == [[1, 0, 0]]
        and specificity["not"] == [[1, 0, 0]]
        and specificity["type"] == [[0, 0, 1]]
        and specificity["nth"] == [[0, 2, 0]]
    )
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
