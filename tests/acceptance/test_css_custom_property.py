"""CSS custom properties substitute at computed-value time.

An inherited variable keeps the value its parent already computed, so a child
that changes the variable it was built from does not retarget it. A cycle is
guaranteed-invalid even when that declaration has a fallback. A fallback that
is never used does not create a cycle. ``var()`` may take its custom property
name from another variable. The guaranteed-invalid value serializes as the
empty string; a valid empty value serializes as one space.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A reader without computed custom properties is an unmet
outcome, not a crash.
"""

from __future__ import annotations

import json

MARKUP = (
    "<!DOCTYPE html><html><body><div id=\"root\">"
    "<p id=\"child\"></p><p id=\"poison\"></p><p id=\"missing\"></p>"
    "<p id=\"comma\"></p><p id=\"chain\"></p><p id=\"unused\"></p>"
    "<p id=\"self\"></p><p id=\"named\"></p><p id=\"lower\"></p>"
    "<p id=\"upper\"></p><p id=\"blank\"></p><p id=\"important\"></p>"
    "</div></body></html>"
)
SHEET = """
#root { --a: var(--b); --b: red; --Brand: red; --name: --Brand; color: blue; }
#child { --b: blue; color: var(--a); }
#poison { --a: var(--b); --b: var(--a); color: var(--a); }
#missing { color: var(--missing, teal); }
#comma { color: var(--missing, rgb(1, 2, 3)); }
#chain { --a: var(--b, cycle); --b: var(--c, cycle); --c: var(--a, cycle); --y: var(--a, valid); color: var(--y); }
#unused { --y: red; --a: var(--y, var(--b, cycle)); --b: var(--y, var(--c, cycle)); --c: var(--y, var(--a, cycle)); color: var(--a); }
#self { --a: var(--a, green); color: var(--a, lime); }
#named { color: var(var(--name)); }
#lower { color: var(--brand, blue); }
#upper { color: var(--Brand); }
#blank { --a: var(--missing,); }
#important { --tone: blue !important; --tone: red; color: var(--tone); }
"""
EXPECTED = {
    "blank_a": " ",
    "chain_a": "",
    "chain_color": "valid",
    "chain_y": "valid",
    "child_a": "red",
    "child_b": "blue",
    "child_color": "red",
    "comma_color": "rgb(1, 2, 3)",
    "important_color": "blue",
    "important_tone": "blue",
    "lower_color": "blue",
    "missing_color": "teal",
    "named_color": "red",
    "poison_a": "",
    "poison_color": "blue",
    "self_a": "",
    "self_color": "lime",
    "unused_a": "red",
    "unused_color": "red",
    "upper_color": "red",
}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_selectors import computed_value
    except Exception as exc:  # noqa: BLE001 - baseline without the function still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    try:
        observed = {
            "blank_a": computed_value(MARKUP, SHEET, "blank", "--a"),
            "chain_a": computed_value(MARKUP, SHEET, "chain", "--a"),
            "chain_color": computed_value(MARKUP, SHEET, "chain", "color"),
            "chain_y": computed_value(MARKUP, SHEET, "chain", "--y"),
            "child_a": computed_value(MARKUP, SHEET, "child", "--a"),
            "child_b": computed_value(MARKUP, SHEET, "child", "--b"),
            "child_color": computed_value(MARKUP, SHEET, "child", "color"),
            "comma_color": computed_value(MARKUP, SHEET, "comma", "color"),
            "important_color": computed_value(MARKUP, SHEET, "important", "color"),
            "important_tone": computed_value(MARKUP, SHEET, "important", "--tone"),
            "lower_color": computed_value(MARKUP, SHEET, "lower", "color"),
            "missing_color": computed_value(MARKUP, SHEET, "missing", "color"),
            "named_color": computed_value(MARKUP, SHEET, "named", "color"),
            "poison_a": computed_value(MARKUP, SHEET, "poison", "--a"),
            "poison_color": computed_value(MARKUP, SHEET, "poison", "color"),
            "self_a": computed_value(MARKUP, SHEET, "self", "--a"),
            "self_color": computed_value(MARKUP, SHEET, "self", "color"),
            "unused_a": computed_value(MARKUP, SHEET, "unused", "--a"),
            "unused_color": computed_value(MARKUP, SHEET, "unused", "color"),
            "upper_color": computed_value(MARKUP, SHEET, "upper", "color"),
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
