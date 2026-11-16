"""A :has() relative selector looks forward from the element being matched.

A descendant image matches, a child combinator does not accept a grandchild,
and a next-sibling combinator does not look backward. :has() takes the
specificity of its most specific argument, so the pictured article becomes
red and the plain article stays blue.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A reader that rejects :has() is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

MARKUP = (
    "<!DOCTYPE html><html><body><section id=\"gallery\">"
    "<article id=\"nest\"><p><img id=\"shot\"></p></article>"
    "<article id=\"direct\"><img id=\"child\"></article>"
    "<article id=\"plain\"><span>text</span></article>"
    "<article id=\"before\"></article><img id=\"between\">"
    "<article id=\"after\"></article></section><img id=\"solo\"></body></html>"
)
SHEET = "article { color: blue } article:has(img) { color: red }"


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_selectors import cascaded_value, matched_ids, selector_specificity
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    try:
        descendant = matched_ids(MARKUP, "article:has(img)")
        child = matched_ids(MARKUP, "article:has(> img)")
        grandchild = matched_ids(MARKUP, "article:has(> p > img)")
        nxt = matched_ids(MARKUP, "article:has(+ img)")
        later = matched_ids(MARKUP, "article:has(~ img)")
        forward = matched_ids(MARKUP, "img:has(+ article)")
        self_image = matched_ids(MARKUP, "img:has(img)")
        nested = matched_ids(MARKUP, "section:has(article:has(> img))")
        strong = selector_specificity("article:has(#shot, span)")
        forgiven = selector_specificity("article:has(:where(#shot))")
        pictured = cascaded_value(MARKUP, SHEET, "nest", "color")
        plain = cascaded_value(MARKUP, SHEET, "plain", "color")
    except Exception as exc:  # noqa: BLE001 - rejection of :has() is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed = {
        "child": child,
        "descendant": descendant,
        "forward": forward,
        "grandchild": grandchild,
        "later": later,
        "nested": nested,
        "next": nxt,
        "pictured": pictured,
        "plain": plain,
        "self_image": self_image,
        "specificity": strong,
        "where_specificity": forgiven,
    }
    passed = (
        descendant == ["nest", "direct"]
        and child == ["direct"]
        and grandchild == ["nest"]
        and nxt == ["before"]
        and later == ["nest", "direct", "plain", "before"]
        and forward == ["between"]
        and self_image == []
        and nested == ["gallery"]
        and strong == [[1, 0, 1]]
        and forgiven == [[0, 0, 1]]
        and pictured == "red"
        and plain == "blue"
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
