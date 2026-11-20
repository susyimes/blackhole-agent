"""Number elements with CSS counters.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
correct numbering and a tree the baseline cannot number.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_counters import format_counter, format_counters, resolve_counters
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def run(name: str, tree: dict[str, object]) -> dict[str, object]:
        try:
            result = resolve_counters(tree)
        except Exception as exc:  # noqa: BLE001 - a raised tree is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            result = {"outcome": "error"}
        observed[name] = result
        return result

    def values(result: dict[str, object], ident: str, counter: str) -> object:
        elements = result.get("elements")
        if not isinstance(elements, dict):
            return None
        element = elements.get(ident)
        if not isinstance(element, dict):
            return None
        stored = element.get("values")
        if not isinstance(stored, dict):
            return None
        return stored.get(counter)

    def stacks(result: dict[str, object], ident: str, counter: str) -> object:
        elements = result.get("elements")
        if not isinstance(elements, dict):
            return None
        element = elements.get(ident)
        if not isinstance(element, dict):
            return None
        stored = element.get("stacks")
        if not isinstance(stored, dict):
            return None
        return stored.get(counter)

    def expect_value(name: str, tree: dict[str, object], ident: str, counter: str, expected: int) -> None:
        result = run(name, tree)
        checks.append(result.get("outcome") == "ok" and values(result, ident, counter) == expected)

    def expect_stack(
        name: str,
        tree: dict[str, object],
        ident: str,
        counter: str,
        expected: list[int],
    ) -> None:
        result = run(name, tree)
        checks.append(result.get("outcome") == "ok" and stacks(result, ident, counter) == expected)

    foo = {
        "id": "ul",
        "counter_reset": "example 0",
        "children": [
            {
                "id": "foo",
                "counter_increment": "example",
                "children": [{"id": "bar", "counter_increment": "example"}],
            },
            {"id": "baz"},
        ],
    }
    result = run("sibling_sees_descendant", foo)
    checks.append(
        result.get("outcome") == "ok"
        and values(result, "foo", "example") == 1
        and values(result, "bar", "example") == 2
        and values(result, "baz", "example") == 2
    )

    nested = {
        "id": "outer",
        "counter_reset": "item",
        "children": [
            {"id": "a", "counter_increment": "item"},
            {
                "id": "b",
                "counter_increment": "item",
                "children": [
                    {
                        "id": "inner",
                        "counter_reset": "item",
                        "children": [{"id": "c", "counter_increment": "item"}],
                    }
                ],
            },
            {"id": "d", "counter_increment": "item"},
        ],
    }
    result = run("child_reset_nests", nested)
    checks.append(
        result.get("outcome") == "ok"
        and stacks(result, "c", "item") == [2, 1]
        and stacks(result, "d", "item") == [3]
    )

    sibling_reset = {
        "id": "root",
        "children": [
            {"id": "a", "counter_increment": "item"},
            {"id": "b", "counter_reset": "item"},
            {"id": "c", "counter_increment": "item"},
        ],
    }
    result = run("sibling_reset_replaces", sibling_reset)
    checks.append(
        result.get("outcome") == "ok"
        and stacks(result, "a", "item") == [1]
        and stacks(result, "b", "item") == [0]
        and stacks(result, "c", "item") == [1]
    )

    expect_stack(
        "set_keeps_one_scope",
        {
            "id": "parent",
            "counter_reset": "n 1",
            "children": [
                {"id": "set", "counter_set": "n 5"},
                {"id": "next", "counter_increment": "n"},
            ],
        },
        "set",
        "n",
        [5],
    )
    result = observed["set_keeps_one_scope"]
    checks.append(isinstance(result, dict) and values(result, "next", "n") == 6)

    expect_value(
        "reset_then_increment",
        {"id": "one", "counter_reset": "n 10", "counter_increment": "n"},
        "one",
        "n",
        11,
    )
    expect_value(
        "set_after_increment",
        {"id": "one", "counter_reset": "n 0", "counter_increment": "n 5", "counter_set": "n 9"},
        "one",
        "n",
        9,
    )
    expect_value(
        "last_reset_wins",
        {"id": "one", "counter_reset": "n 1 n 4", "counter_increment": "n"},
        "one",
        "n",
        5,
    )
    expect_value(
        "increments_compound",
        {"id": "one", "counter_reset": "n 0", "counter_increment": "n 1 n 2"},
        "one",
        "n",
        3,
    )
    expect_value(
        "negative_reset",
        {"id": "one", "counter_reset": "section -1", "counter_increment": "section"},
        "one",
        "section",
        0,
    )

    reversed_tree = {
        "id": "list",
        "counter_reset": "reversed(item)",
        "children": [
            {"id": "r1", "counter_increment": "item -1"},
            {"id": "r2", "counter_increment": "item -1"},
            {"id": "r3", "counter_increment": "item -1"},
        ],
    }
    result = run("reversed_automatic", reversed_tree)
    checks.append(
        result.get("outcome") == "ok"
        and [values(result, ident, "item") for ident in ("r1", "r2", "r3")] == [3, 2, 1]
    )
    explicit = {
        "id": "list",
        "counter_reset": "reversed(item) 5",
        "children": [
            {"id": "e1", "counter_increment": "item -1"},
            {"id": "e2", "counter_increment": "item -1"},
        ],
    }
    result = run("reversed_explicit", explicit)
    checks.append(
        result.get("outcome") == "ok"
        and [values(result, ident, "item") for ident in ("e1", "e2")] == [4, 3]
    )

    items = {
        "id": "ol",
        "counter_reset": "list-item",
        "children": [
            {"id": "i1", "display": "list-item"},
            {"id": "i2", "display": "list-item"},
            {"id": "i3", "display": "list-item"},
        ],
    }
    result = run("list_items", items)
    checks.append(
        result.get("outcome") == "ok"
        and [values(result, ident, "list-item") for ident in ("i1", "i2", "i3")] == [1, 2, 3]
    )
    reversed_items = {
        "id": "ol",
        "counter_reset": "reversed(list-item)",
        "children": [
            {"id": "i1", "display": "list-item"},
            {"id": "i2", "display": "list-item"},
            {"id": "i3", "display": "list-item"},
        ],
    }
    result = run("reversed_list_items", reversed_items)
    checks.append(
        result.get("outcome") == "ok"
        and [values(result, ident, "list-item") for ident in ("i1", "i2", "i3")] == [3, 2, 1]
    )
    expect_value(
        "explicit_list_item_step",
        {
            "id": "ol",
            "counter_reset": "list-item",
            "children": [{"id": "i1", "display": "list-item", "counter_increment": "list-item 2"}],
        },
        "i1",
        "list-item",
        2,
    )
    stepped = {
        "id": "ol",
        "counter_reset": "list-item",
        "children": [
            {"id": "i1", "display": "list-item", "counter_increment": "list-item 0"},
            {"id": "i2", "display": "list-item"},
        ],
    }
    result = run("list_item_zero_then_automatic", stepped)
    checks.append(
        result.get("outcome") == "ok"
        and values(result, "i1", "list-item") == 0
        and values(result, "i2", "list-item") == 1
    )
    expect_value(
        "none_still_numbers_list_item",
        {
            "id": "ol",
            "counter_reset": "list-item",
            "children": [{"id": "i1", "display": "list-item", "counter_increment": "none"}],
        },
        "i1",
        "list-item",
        1,
    )

    pseudos = {
        "id": "h1",
        "counter_reset": "n 0",
        "before": {"id": "marker", "counter_increment": "n"},
        "children": [{"id": "child", "counter_increment": "n"}],
        "after": {"id": "tail", "counter_increment": "n"},
    }
    result = run("before_child_after", pseudos)
    checks.append(
        result.get("outcome") == "ok"
        and [values(result, ident, "n") for ident in ("marker", "child", "tail")] == [1, 2, 3]
    )

    hidden = {
        "id": "root",
        "counter_reset": "n 0",
        "children": [
            {"id": "a", "counter_increment": "n"},
            {
                "id": "gone",
                "display": "none",
                "counter_increment": "n",
                "children": [{"id": "secret", "counter_increment": "n"}],
            },
            {"id": "b", "counter_increment": "n"},
        ],
    }
    result = run("display_none_skips_subtree", hidden)
    elements = result.get("elements")
    checks.append(
        result.get("outcome") == "ok"
        and values(result, "a", "n") == 1
        and values(result, "b", "n") == 2
        and isinstance(elements, dict)
        and "gone" not in elements
        and "secret" not in elements
    )

    headings = {
        "id": "body",
        "counter_reset": "h1 h2 h3",
        "children": [
            {"id": "h1a", "counter_increment": "h1", "counter_reset": "h2 h3"},
            {"id": "h2a", "counter_increment": "h2", "counter_reset": "h3"},
            {"id": "h2b", "counter_increment": "h2", "counter_reset": "h3"},
            {"id": "h3a", "counter_increment": "h3"},
            {"id": "h1b", "counter_increment": "h1", "counter_reset": "h2 h3"},
            {"id": "h2c", "counter_increment": "h2", "counter_reset": "h3"},
        ],
    }
    result = run("heading_outline", headings)
    checks.append(
        result.get("outcome") == "ok"
        and values(result, "h1a", "h1") == 1
        and format_counter(values(result, "h1a", "h1"), "upper-alpha").get("text") == "A"
        and values(result, "h2a", "h2") == 1
        and values(result, "h2b", "h2") == 2
        and values(result, "h3a", "h3") == 1
        and format_counter(values(result, "h3a", "h3"), "lower-roman").get("text") == "i"
        and stacks(result, "h3a", "h3") == [0, 1]
        and values(result, "h1b", "h1") == 2
        and format_counter(values(result, "h1b", "h1"), "upper-alpha").get("text") == "B"
        and values(result, "h2c", "h2") == 1
        and stacks(result, "h2c", "h2") == [0, 1]
    )

    used = {
        "id": "first",
        "read": ["item"],
        "children": [{"id": "second", "counter_increment": "item"}],
    }
    result = run("read_instantiates_zero", used)
    checks.append(
        result.get("outcome") == "ok"
        and values(result, "first", "item") == 0
        and values(result, "second", "item") == 1
    )

    for name, tree in (
        ("bad_reset", {"id": "one", "counter_reset": "n none"}),
        ("bad_increment", {"id": "one", "counter_increment": "reversed(n)"}),
        ("duplicate_id", {"id": "one", "children": [{"id": "one"}]}),
    ):
        result = run(name, tree)
        checks.append(result.get("outcome") == "invalid" and bool(result.get("reason")))

    rendered = {
        "upper_a": format_counter(1, "upper-alpha"),
        "upper_b": format_counter(2, "upper-latin"),
        "lower_aa": format_counter(27, "lower-alpha"),
        "lower_i": format_counter(1, "lower-roman"),
        "upper_iv": format_counter(4, "upper-roman"),
        "zero_alpha": format_counter(0, "lower-alpha"),
        "negative": format_counter(-2, "decimal"),
        "none_style": format_counter(4, "none"),
        "joined": format_counters([2, 1], ".", "decimal"),
        "bad_style": format_counter(1, "disc"),
    }
    observed["formatted"] = rendered
    checks.append(
        all(isinstance(item, dict) and item.get("outcome") == "ok" for key, item in rendered.items() if key != "bad_style")
        and rendered["upper_a"].get("text") == "A"
        and rendered["upper_b"].get("text") == "B"
        and rendered["lower_aa"].get("text") == "aa"
        and rendered["lower_i"].get("text") == "i"
        and rendered["upper_iv"].get("text") == "IV"
        and rendered["zero_alpha"].get("text") == "0"
        and rendered["negative"].get("text") == "-2"
        and rendered["none_style"].get("text") == ""
        and rendered["joined"].get("text") == "2.1"
        and rendered["bad_style"].get("outcome") == "invalid"
    )
    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet behavior and baseline both exit 0
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
