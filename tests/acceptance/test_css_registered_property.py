"""A CSS @property rule registers a custom property at computed-value time.

The last valid rule wins. An earlier green initial value loses to a later
black one, and a still later initial value that is not a color is ignored.
A non-inheriting property does not pass its parent value to a child. A value
that fails the syntax computes to the initial value, and var() substitutes
that computed value. An explicit inherit still takes the parent. An
unregistered property still inherits an arbitrary token stream, and an
unregistered cycle stays guaranteed-invalid. A universal syntax cycle stays
guaranteed-invalid even when an initial value exists, while a missing
declaration uses that initial value. A typed cycle computes to the initial
value. A rule whose only initial value fails the syntax does not register.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A reader that rejects @property is an unmet outcome, not a
crash.
"""

from __future__ import annotations

import json

MARKUP = (
    "<!DOCTYPE html><html><body><div id='parent'>"
    "<p id='child'></p><p id='set'></p><p id='bad'></p><p id='note'></p>"
    "<p id='loop'></p><p id='paint'></p><p id='free'></p><p id='plain'></p>"
    "<p id='adopt'></p><p id='open'></p>"
    "</div></body></html>"
)
SHEET = """
@property --tone {
  syntax: "<color>";
  inherits: false;
  initial-value: green;
}
@property --wide, --tall {
  syntax: "<length>";
  inherits: false;
  initial-value: 0px;
}
@property --paint {
  syntax: "<color>";
  inherits: true;
  initial-value: black;
}
@property --free {
  syntax: "*";
  inherits: false;
  initial-value: none;
}
@property --open {
  syntax: "<color>";
  inherits: false;
  initial-value: 12px;
}
@property --tone {
  syntax: "<color>";
  inherits: false;
  initial-value: black;
}
@property --tone {
  syntax: "<color>";
  inherits: false;
  initial-value: 12px;
}
#parent { --tone: red; --note: blue; --tall: 4px; --open: red; }
#child { --wide: 10px; }
#set { --tone: green; }
#bad { --tone: 12px; color: var(--tone); }
#loop { --loop: var(--loop); }
#paint { --paint: var(--paint); }
#free { --free: var(--free); }
#adopt { --tone: inherit; }
"""
EXPECTED = {
    "adopt_tone": "red",
    "bad_color": "black",
    "bad_tone": "black",
    "child_tall": "0px",
    "child_tone": "black",
    "child_wide": "10px",
    "free": "",
    "loop": "",
    "note": "blue",
    "open": "red",
    "paint": "black",
    "plain": "none",
    "set_tone": "green",
}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_selectors import computed_value
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    queries = {
        "adopt_tone": ("adopt", "--tone"),
        "bad_color": ("bad", "color"),
        "bad_tone": ("bad", "--tone"),
        "child_tall": ("child", "--tall"),
        "child_tone": ("child", "--tone"),
        "child_wide": ("child", "--wide"),
        "free": ("free", "--free"),
        "loop": ("loop", "--loop"),
        "note": ("note", "--note"),
        "open": ("open", "--open"),
        "paint": ("paint", "--paint"),
        "plain": ("plain", "--free"),
        "set_tone": ("set", "--tone"),
    }
    observed: dict[str, object] = {}
    try:
        for key, (element_id, prop) in queries.items():
            observed[key] = computed_value(MARKUP, SHEET, element_id, prop)
    except Exception as exc:  # noqa: BLE001 - a rejected @property rule is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}", "observed": observed}

    return observed == EXPECTED, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
