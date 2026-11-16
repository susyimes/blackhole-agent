"""CSS cascade layers order author declarations, and revert-layer rolls back.

An unlayered color beats a named layer. A type selector in a later layer beats
an id in an earlier layer. An earlier layer's important color beats a later
layer's important id and an unlayered important color. A parent layer's own
rule beats a nested layer written after it. revert-layer drops the other
declarations in its layer and uses the layer below.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A reader that rejects @layer is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

MARKUP = "<!DOCTYPE html><html><body><p id=\"t\"></p></body></html>"
EXPECTED = {
    "earlier_important": "green",
    "later_normal": "green",
    "later_type_beats_earlier_id": "green",
    "layered_important": "red",
    "nested_important": "red",
    "parent_beats_nested": "green",
    "revert_same_layer": "green",
    "revert_to_theme": "blue",
    "specificity_inside_layer": "red",
    "unlayered": "purple",
}
SHEETS = {
    "earlier_important": """
        @layer theme, base;
        @layer theme { p { color: green !important } }
        @layer base { #t { color: red !important } }
    """,
    "later_normal": """
        @layer base, theme;
        @layer base { #t { color: red } }
        @layer theme { #t { color: green } }
    """,
    "later_type_beats_earlier_id": """
        @layer theme, base;
        @layer base { p { color: green } }
        @layer theme { #t { color: red } }
    """,
    "layered_important": """
        @layer base { #t { color: red !important } }
        #t { color: blue !important }
    """,
    "nested_important": """
        @layer A {
          @layer B { #t { color: red !important } }
          #t { color: green !important }
        }
    """,
    "parent_beats_nested": """
        @layer A {
          #t { color: green }
          @layer B { #t { color: red } }
        }
    """,
    "revert_same_layer": """
        @layer { #t { color: green } }
        @layer { #t { color: red; color: revert-layer } }
    """,
    "revert_to_theme": """
        @layer base, theme;
        @layer base { #t { color: red } }
        @layer theme { #t { color: blue } }
        #t { color: revert-layer }
    """,
    "specificity_inside_layer": """
        @layer base { p { color: green } #t { color: red } }
    """,
    "unlayered": """
        @layer theme { #t { color: green } }
        #t { color: purple }
    """,
}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_selectors import cascaded_value
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    try:
        observed = {
            name: cascaded_value(MARKUP, sheet, "t", "color")
            for name, sheet in SHEETS.items()
        }
    except Exception as exc:  # noqa: BLE001 - a rejected stylesheet is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}
    return observed == EXPECTED, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
