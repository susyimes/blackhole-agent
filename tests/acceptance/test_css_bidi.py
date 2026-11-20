"""Reorder a CSS bidi paragraph into visual order.

direction sets the paragraph level. unicode-bidi plaintext reads the first
strong character of each paragraph, and bidi-override forces the root inline.
An inline isolate is the RLI/PDI pair from bidi_controls. Hebrew in an LTR
paragraph reverses in place; the same letters in an RTL paragraph trade
sides with Latin.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_bidi import bidi_controls, reorder_css_bidi
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def take(name: str, text: str, **kwargs: object) -> dict[str, object]:
        try:
            result = reorder_css_bidi(text, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised reorder is an unmet outcome
            result = {"outcome": "error", "visual": None, "levels": None, "reason": f"{type(exc).__name__}: {exc}"}
        got = result if isinstance(result, dict) else {"outcome": "error", "visual": None, "levels": None}
        observed[name] = {
            "outcome": got.get("outcome"),
            "visual": got.get("visual"),
            "levels": got.get("levels"),
            "paragraph_level": got.get("paragraph_level"),
            "paragraph_levels": got.get("paragraph_levels"),
        }
        return observed[name]

    def expect(name: str, visual: str, text: str, **kwargs: object) -> dict[str, object]:
        got = take(name, text, **kwargs)
        checks.append(got.get("outcome") == "reordered" and got.get("visual") == visual)
        return got

    car = expect("ltr_embedding", "car means \u05d2\u05d1\u05d0.", "car means \u05d0\u05d1\u05d2.")
    checks.append(car.get("levels") == [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0])
    expect("rtl_paragraph", "\u05d5\u05d4\u05d3 abc \u05d2\u05d1\u05d0", "\u05d0\u05d1\u05d2 abc \u05d3\u05d4\u05d5", direction="rtl")
    expect("numbers", "abc 12 \u05d2\u05d1\u05d0", "abc \u05d0\u05d1\u05d2 12")
    expect("override_rtl", "cba", "abc", direction="rtl", unicode_bidi="bidi-override")
    expect("override_ltr", "\u05d0\u05d1\u05d2", "\u05d0\u05d1\u05d2", unicode_bidi="bidi-override")
    plain = expect("plaintext", "abc \u05d2\u05d1\u05d0", "\u05d0\u05d1\u05d2 abc", unicode_bidi="plaintext")
    checks.append(plain.get("paragraph_level") == 1)
    normal = expect("logical_ltr", "\u05d2\u05d1\u05d0 abc", "\u05d0\u05d1\u05d2 abc")
    checks.append(normal.get("paragraph_level") == 0)
    prefix, suffix = bidi_controls("rtl", "isolate")
    expect(
        "inline_isolate",
        "english17 \u2067\u05d5\u05d4\u05d3 english \u05d2\u05d1\u05d0\u2069",
        f"english17 {prefix}\u05d0\u05d1\u05d2 english \u05d3\u05d4\u05d5{suffix}",
    )
    split = expect(
        "plaintext_split",
        "ab\u2029abc \u05d2\u05d1\u05d0",
        "ab\u2029\u05d0\u05d1\u05d2 abc",
        unicode_bidi="plaintext",
    )
    checks.append(split.get("paragraph_levels") == [0, 1])
    expect("explicit_override", "azyxb", "a\u202exyz\u202cb")
    refused = take("bad_direction", "abc", direction="sideways")
    checks.append(
        refused.get("outcome") == "invalid" and refused.get("visual") is None and refused.get("levels") is None
    )
    return all(checks), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
