"""Resolve CSS sibling-index() and sibling-count() on the DOM tree.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without these functions still exits 0.
"""

from __future__ import annotations

import json


def _near(found: object, expected: float, tol: float = 1e-6) -> bool:
    return isinstance(found, (int, float)) and not isinstance(found, bool) and abs(float(found) - expected) <= tol


def _tree() -> dict:
    return {
        "tag": "ul",
        "id": "list",
        "children": [
            {"text": "lead"},
            {"tag": "li", "id": "one", "children": [{"tag": "em", "id": "inner"}]},
            {"comment": "mid"},
            {"tag": "li", "id": "two"},
            {"tag": "li", "id": "three"},
        ],
    }


def _shadow_tree() -> dict:
    return {
        "tag": "div",
        "id": "wrap",
        "children": [
            {"tag": "i", "id": "before"},
            {
                "tag": "div",
                "id": "host",
                "children": [
                    {"text": "nope"},
                    {"tag": "span", "id": "s1"},
                    {"comment": "c"},
                    {"tag": "span", "id": "s2"},
                ],
                "shadow": [
                    {"tag": "b", "id": "part", "part": "my-part"},
                    {"comment": "hidden"},
                    {"tag": "b", "id": "other"},
                    {
                        "tag": "span",
                        "id": "inner-host",
                        "shadow": [{"tag": "em", "id": "deep"}],
                    },
                ],
            },
            {"tag": "i", "id": "after"},
        ],
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_tree_counting import resolve_tree_counting
    except Exception as exc:  # noqa: BLE001 - baseline without the resolver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []
    tree = _tree()
    shadow = _shadow_tree()

    def keep(name: str, row: dict[str, object], ok: bool) -> None:
        observed[name] = row
        checks.append(ok)

    def counted(name: str, expression: str, element: str, index: int, count: int, **kwargs: object) -> None:
        chosen = shadow if kwargs.pop("shadow", False) else tree
        row = resolve_tree_counting(expression, chosen, element, **kwargs)
        keep(
            name,
            row,
            row.get("outcome") == "resolved"
            and row.get("scoped") is True
            and row.get("index") == index
            and row.get("count") == count
            and row.get("reason") == "",
        )

    counted("middle_index", "sibling-index()", "two", 2, 3)
    counted("middle_count", "sibling-count()", "two", 2, 3)
    counted("spaced", "sibling-index( )", "two", 2, 3)
    counted("comment_args", "sibling-index(/*n*/)", "two", 2, 3)
    counted("case", "SIBLING-COUNT()", "two", 2, 3)
    counted("before", "sibling-index()", "two", 2, 3, pseudo="::before")
    counted("before_marker", "sibling-index()", "two", 2, 3, pseudo="::before::marker")
    counted("nested_child", "sibling-index()", "inner", 1, 1)
    counted("root", "sibling-count()", "list", 1, 1)

    length = resolve_tree_counting("calc(sibling-index() * 10px)", tree, "two")
    observed["middle_length"] = length
    checks.append(
        length.get("outcome") == "resolved"
        and length.get("px") == 20
        and length.get("index") == 2
        and length.get("count") == 3
    )

    ratio = resolve_tree_counting("calc(sibling-index() / sibling-count() * 100px)", tree, "two")
    observed["middle_ratio"] = ratio
    checks.append(ratio.get("outcome") == "resolved" and _near(ratio.get("px"), 200 / 3))

    kept = resolve_tree_counting("calc(sibling-index() * 1px /* sibling-count() */)", tree, "two")
    observed["comment_kept"] = kept
    checks.append(
        kept.get("outcome") == "resolved"
        and kept.get("px") == 2
        and isinstance(kept.get("value"), str)
        and "sibling-count()" in str(kept.get("value"))
    )

    argument = resolve_tree_counting("sibling-index(1)", tree, "two")
    observed["argument"] = argument
    checks.append(
        argument.get("outcome") == "invalid"
        and argument.get("reason") == "argument"
        and argument.get("px") is None
        and argument.get("value") == ""
    )

    unitless = resolve_tree_counting("calc(sibling-index())", tree, "two")
    observed["unitless"] = unitless
    checks.append(unitless.get("outcome") == "invalid" and unitless.get("reason") == "type" and unitless.get("px") is None)

    quoted = resolve_tree_counting('"sibling-index()"', tree, "two")
    observed["quoted"] = quoted
    checks.append(quoted.get("outcome") == "invalid" and quoted.get("reason") == "function")

    part = resolve_tree_counting(
        "calc(sibling-index() * 10px)",
        shadow,
        "part",
        pseudo="::part(my-part)",
        style_scope="document",
    )
    observed["outer_part"] = part
    checks.append(
        part.get("outcome") == "resolved"
        and part.get("scoped") is False
        and part.get("index") == 0
        and part.get("count") == 0
        and part.get("px") == 0
    )

    counted(
        "inner_part",
        "sibling-index()",
        "part",
        1,
        3,
        shadow=True,
        pseudo="::part(my-part)",
        style_scope="host",
    )
    counted("host", "sibling-index()", "host", 2, 3, shadow=True, pseudo=":host", style_scope="host")
    counted(
        "host_before",
        "sibling-count()",
        "host",
        2,
        3,
        shadow=True,
        pseudo=":host::before",
        style_scope="host",
    )
    counted("slotted", "sibling-index()", "s2", 2, 2, shadow=True, pseudo="::slotted(*)", style_scope="host")
    deep = resolve_tree_counting("sibling-index()", shadow, "deep", style_scope="host")
    observed["deep_from_outer_shadow"] = deep
    checks.append(
        deep.get("outcome") == "resolved" and deep.get("scoped") is False and deep.get("index") == 0 and deep.get("value") == "0"
    )
    deep_own = resolve_tree_counting("sibling-count()", shadow, "deep", style_scope="inner-host")
    observed["deep_own_shadow"] = deep_own
    checks.append(
        deep_own.get("outcome") == "resolved"
        and deep_own.get("scoped") is True
        and deep_own.get("index") == 1
        and deep_own.get("count") == 1
    )
    outside = resolve_tree_counting("sibling-index()", shadow, "before", style_scope="host")
    observed["outer_sibling_from_shadow"] = outside
    checks.append(outside.get("outcome") == "resolved" and outside.get("scoped") is False and outside.get("index") == 0)

    passed = all(checks) and bool(checks)
    if not passed:
        observed["failed"] = [name for name, ok in zip(observed, checks, strict=False) if not ok]
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
