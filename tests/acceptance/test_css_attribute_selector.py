"""Attribute selectors match HTML values inside the cascade.

Presence, exact, word, dash, prefix, suffix, and substring comparisons are
covered, including HTML ASCII case folding and the i/s flags. A reader that
rejects a bracket is an unmet outcome, not a crash.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

MARKUP = (
    "<!DOCTYPE html><html><body>"
    '<a id="link" href="https://ex.example/a.PDF" rel="next external" lang="en-GB" title=""></a>'
    '<a id="plain" href="http://ex.example/a.pdf" rel="external" lang="english"></a>'
    '<a id="rootlang" href="https://ex.example/home" lang="en"></a>'
    '<input id="text" type="text">'
    '<input id="file" type="file">'
    '<span id="note" data-kind="Note" class="Item"></span>'
    '<span id="empty" data-kind=""></span>'
    '<span id="bare"></span>'
    '<div id="wrap"><a id="nested" href="https://ex.example/nested" rel="next"></a></div>'
    "</body></html>"
)

CASES = (
    ("title_present", "link", "* { color: blue } [title] { color: red }", "red"),
    ("title_missing", "plain", "* { color: blue } [title] { color: red }", "blue"),
    ("exact_empty", "empty", 'span { color: blue } [data-kind=""] { color: red }', "red"),
    ("exact_empty_miss", "note", 'span { color: blue } [data-kind=""] { color: red }', "blue"),
    ("word_next", "link", "a { color: blue } a[rel~=next] { color: red }", "red"),
    ("word_next_miss", "plain", "a { color: blue } a[rel~=next] { color: red }", "blue"),
    ("word_substring", "link", "a { color: blue } a[rel~=ext] { color: red }", "blue"),
    ("substring_hit", "link", 'a { color: blue } a[href*="ex.example"] { color: red }', "red"),
    ("substring_miss", "note", '* { color: blue } [href*="ex.example"] { color: red }', "blue"),
    ("dash_prefix", "link", "a { color: blue } a[lang|=en] { color: red }", "red"),
    ("dash_exact", "rootlang", "a { color: blue } a[lang|=en] { color: red }", "red"),
    ("dash_miss", "plain", "a { color: blue } a[lang|=en] { color: red }", "blue"),
    ("dash_folded", "link", "a { color: blue } a[lang|=EN] { color: red }", "red"),
    ("prefix_https", "link", 'a { color: blue } a[href^="https"] { color: red }', "red"),
    ("prefix_https_miss", "plain", 'a { color: blue } a[href^="https"] { color: red }', "blue"),
    ("suffix_sensitive", "link", 'a { color: blue } a[href$=".pdf"] { color: red }', "blue"),
    ("suffix_sensitive_hit", "plain", 'a { color: blue } a[href$=".pdf"] { color: red }', "red"),
    ("suffix_folded", "link", 'a { color: blue } a[href$=".pdf" i] { color: red }', "red"),
    ("type_folded", "text", "input { color: blue } input[type=TEXT] { color: red }", "red"),
    ("type_folded_miss", "file", "input { color: blue } input[type=TEXT] { color: red }", "blue"),
    ("type_sensitive_flag", "text", "input { color: blue } input[type=TEXT s] { color: red }", "blue"),
    ("data_sensitive", "note", "span { color: blue } span[data-kind=note] { color: red }", "blue"),
    ("data_folded_flag", "note", "span { color: blue } span[data-kind=note i] { color: red }", "red"),
    ("rel_folded", "link", "a { color: blue } a[rel~=NEXT] { color: red }", "red"),
    ("rel_sensitive_flag", "link", "a { color: blue } a[rel~=NEXT s] { color: red }", "blue"),
    ("name_folded", "link", 'a { color: blue } a[HREF^="https"] { color: red }', "red"),
    ("quoted_exact", "link", 'a { color: blue } a[rel="next external"] { color: red }', "red"),
    ("quoted_exact_miss", "plain", 'a { color: blue } a[rel="next external"] { color: red }', "blue"),
    ("child_combinator", "link", "a { color: blue } body > a[rel~=next] { color: red }", "red"),
    ("child_combinator_miss", "nested", "a { color: blue } body > a[rel~=next] { color: red }", "blue"),
    ("negated_type", "text", "input { color: blue } input:not([type=file]) { color: red }", "red"),
    ("negated_type_miss", "file", "input { color: blue } input:not([type=file]) { color: red }", "blue"),
    (
        "is_beats_type",
        "note",
        ':is([data-kind="Note"]) { color: red } span { color: blue }',
        "red",
    ),
    (
        "where_loses_to_type",
        "note",
        ':where([data-kind="Note"]) { color: red } span { color: blue }',
        "blue",
    ),
    (
        "nested_ampersand",
        "link",
        "a { color: blue; &[rel~=next] { color: red } }",
        "red",
    ),
    (
        "nested_ampersand_miss",
        "plain",
        "a { color: blue; &[rel~=next] { color: red } }",
        "blue",
    ),
    (
        "supports_keeps",
        "link",
        'a { color: blue } @supports selector(a[href]) { a[href^="https"] { color: red } }',
        "red",
    ),
    (
        "supports_drops",
        "link",
        "a { color: blue } @supports selector(a[href~=]) { a { color: red } }",
        "blue",
    ),
    ("class_sensitive", "note", "span { color: blue } span[class~=Item] { color: red }", "red"),
    ("class_sensitive_miss", "note", "span { color: blue } span[class~=item] { color: red }", "blue"),
    ("spaced_operator", "link", 'a { color: blue } a[ href ^= "https" ] { color: red }', "red"),
)

ERRORS = (
    "a[rel~=''] { color: red }",
    'a[href^=""] { color: red }',
    'a[href*=""] { color: red }',
    'a[rel~="next external"] { color: red }',
    "a[type=text i s] { color: red }",
    "a[*|href] { color: red }",
)

SPECIFICITY = (
    ("spec_href", "[href]", "0,1,0"),
    ("spec_compound", "a[href].x", "0,2,1"),
    ("spec_where", ":where([href])", "0,0,0"),
    ("spec_is", ":is([href], a)", "0,1,0"),
)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_selectors import (
            CssSelectorError,
            cascaded_value,
            selector_specificity,
        )
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    for name, element_id, sheet, _expected in CASES:
        try:
            observed[name] = cascaded_value(MARKUP, sheet, element_id, "color")
        except Exception as exc:  # noqa: BLE001 - a rejected selector is an unmet outcome
            observed[name] = type(exc).__name__
    for index, sheet in enumerate(ERRORS, start=1):
        try:
            cascaded_value(MARKUP, sheet, "link", "color")
        except CssSelectorError:
            observed[f"error_{index}"] = "CssSelectorError"
        except Exception as exc:  # noqa: BLE001
            observed[f"error_{index}"] = type(exc).__name__
        else:
            observed[f"error_{index}"] = "accepted"
    for name, selector, _expected in SPECIFICITY:
        try:
            rows = selector_specificity(selector)
        except Exception as exc:  # noqa: BLE001
            observed[name] = type(exc).__name__
        else:
            observed[name] = "|".join(",".join(str(part) for part in row) for row in rows)
    expected = {name: value for name, _element, _sheet, value in CASES}
    expected.update({f"error_{index}": "CssSelectorError" for index in range(1, len(ERRORS) + 1)})
    expected.update({name: value for name, _selector, value in SPECIFICITY})
    return observed == expected, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
