"""Match CSS container queries against ancestor query containers.

Prints JSON with boolean passed and nonempty observed. Exit 0 whether or not
the candidate implements container queries. A missing matcher is an unmet
outcome.
"""

from __future__ import annotations

import json


def box(identity: str, parent: str | None, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": identity,
        "parent": parent,
        "container_type": "normal",
        "width": 0,
        "height": 0,
    }
    row.update(extra)
    return row


NESTED = [
    box("outer", None, container_type="size", width=200, height=400),
    box("inner", "outer", container_type="inline-size", width=500, height=50),
    box("child", "inner", width=1, height=1),
]
NARROW = [
    box("outer", None, container_type="size", width=500, height=100),
    box("inner", "outer", container_type="inline-size", width=100, height=20),
    box("child", "inner", width=1, height=1),
]
NAMED = [
    box("page", None, container_type="size", container_name="page", width=800, height=800),
    box("card", "page", container_type="inline-size", container_name="card", width=500, height=20),
    box("child", "card", width=1, height=1),
]
FONTS = [
    box("small", None, container_type="inline-size", width=641, height=10, font_size=16),
    box("h2s", "small", width=1, height=1),
    box("big", None, container_type="inline-size", width=641, height=10, font_size=24),
    box("h2b", "big", width=1, height=1),
    box("wide", None, container_type="inline-size", width=961, height=10, font_size=24),
    box("h2w", "wide", width=1, height=1),
]
VERTICAL = [
    box("outer", None, container_type="size", width=50, height=50),
    box("vert", "outer", container_type="inline-size", writing_mode="vertical-rl", width=500, height=100),
    box("child", "vert", width=1, height=1),
]
NAMED_NORMAL = [
    box("page", None, container_type="normal", container_name="page", width=900, height=100),
    box("child", "page", width=1, height=1),
]
VARS = [
    box("aside", None, container_type="inline-size", width=301, height=10, custom={"--query": "300px"}),
    box("a", "aside", width=1, height=1),
    box("main", None, container_type="inline-size", width=301, height=10, custom={"--query": "500px"}),
    box("m", "main", width=1, height=1),
]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_container_query import match_container_query
    except Exception as exc:  # noqa: BLE001 - baseline without the matcher still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def run(name: str, elements: list[dict[str, object]], query: str) -> dict[str, object]:
        try:
            result = match_container_query(elements, query)
        except Exception as exc:  # noqa: BLE001 - a raised match is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        observed[name] = result if isinstance(result, dict) else {"outcome": "error"}
        return observed[name]

    def row(result: dict[str, object], element: str, index: int = 0) -> dict[str, object]:
        conditions = result.get("conditions")
        if not isinstance(conditions, dict):
            return {}
        found = conditions.get(element)
        if not isinstance(found, list) or len(found) <= index or not isinstance(found[index], dict):
            return {}
        return found[index]

    width = run("inner_width", NESTED, "(min-width: 400px)")
    width_row = row(width, "child")
    checks.append(
        width.get("outcome") == "matched"
        and width.get("matches") == ["child"]
        and width_row.get("value") == "true"
        and width_row.get("container") == "inner"
    )

    height = run("outer_height", NESTED, "(min-height: 100px)")
    height_row = row(height, "child")
    checks.append(
        "child" in height.get("matches", [])
        and height_row.get("value") == "true"
        and height_row.get("container") == "outer"
    )

    both = run("both_axes", NESTED, "(min-width: 400px) and (min-height: 100px)")
    both_row = row(both, "child")
    checks.append(
        both.get("matches") == []
        and both_row.get("value") == "false"
        and both_row.get("container") == "outer"
    )

    mixed = run("or_one_container", NESTED, "(min-width: 400px) or (min-height: 1000px)")
    mixed_row = row(mixed, "child")
    checks.append(
        mixed.get("matches") == []
        and mixed_row.get("value") == "false"
        and mixed_row.get("container") == "outer"
    )

    held = run("no_fallthrough", NARROW, "(min-width: 400px)")
    held_row = row(held, "child")
    checks.append(
        "child" not in held.get("matches", [])
        and held_row.get("value") == "false"
        and held_row.get("container") == "inner"
    )

    negated = run("not_on_nearer", NARROW, "not (min-width: 400px)")
    negated_row = row(negated, "child")
    checks.append(
        negated.get("matches") == ["child"]
        and negated_row.get("value") == "true"
        and negated_row.get("container") == "inner"
    )

    card = run("named_card_height", NAMED, "@container card (min-height: 10px)")
    card_row = row(card, "child")
    checks.append(card.get("matches") == [] and card_row.get("value") == "unknown" and card_row.get("container") is None)

    page = run("named_page_width", NAMED, "@container page (min-width: 500px)")
    page_row = row(page, "child")
    checks.append(
        "child" in page.get("matches", [])
        and page_row.get("value") == "true"
        and page_row.get("container") == "page"
    )

    comma = run("comma_list", NARROW, "(min-width: 400px), (min-height: 100px)")
    comma_width = row(comma, "child", 0)
    comma_height = row(comma, "child", 1)
    checks.append(
        "child" in comma.get("matches", [])
        and comma_width.get("value") == "false"
        and comma_width.get("container") == "inner"
        and comma_height.get("value") == "true"
        and comma_height.get("container") == "outer"
    )

    solo = run("self_excluded", [box("solo", None, container_type="size", width=900, height=100)], "(min-width: 100px)")
    solo_row = row(solo, "solo")
    checks.append(solo.get("matches") == [] and solo_row.get("value") == "unknown" and solo_row.get("container") is None)

    em = run("em_font", FONTS, "(width > 40em)")
    small = row(em, "h2s")
    big = row(em, "h2b")
    wide = row(em, "h2w")
    checks.append(
        em.get("matches") == ["h2s", "h2w"]
        and small.get("value") == "true"
        and small.get("container") == "small"
        and big.get("value") == "false"
        and big.get("container") == "big"
        and wide.get("value") == "true"
        and wide.get("container") == "wide"
        and "small" not in em.get("matches", [])
    )

    vertical_height = run("vertical_inline", VERTICAL, "(min-height: 80px)")
    vertical_height_row = row(vertical_height, "child")
    checks.append(
        vertical_height.get("matches") == ["child"]
        and vertical_height_row.get("value") == "true"
        and vertical_height_row.get("container") == "vert"
    )
    vertical_width = run("vertical_block", VERTICAL, "(min-width: 80px)")
    vertical_width_row = row(vertical_width, "child")
    checks.append(
        vertical_width.get("matches") == []
        and vertical_width_row.get("value") == "false"
        and vertical_width_row.get("container") == "outer"
    )

    name_only = run("name_only", NAMED_NORMAL, "@container page")
    name_only_row = row(name_only, "child")
    checks.append(
        name_only.get("matches") == ["child"]
        and name_only_row.get("value") == "true"
        and name_only_row.get("container") == "page"
    )
    normal_size = run("normal_not_size", NAMED_NORMAL, "@container page (min-width: 1px)")
    normal_row = row(normal_size, "child")
    checks.append(
        normal_size.get("matches") == []
        and normal_row.get("value") == "unknown"
        and normal_row.get("container") is None
    )

    closed = run("inclusive_range", NESTED, "(100px < width <= 500px)")
    open_range = run("exclusive_range", NESTED, "(100px < width < 500px)")
    checks.append(
        row(closed, "child").get("value") == "true"
        and row(closed, "child").get("container") == "inner"
        and row(open_range, "child").get("value") == "false"
        and row(open_range, "child").get("container") == "inner"
    )

    custom = run("var_query", VARS, "(width > var(--query))")
    checks.append(
        custom.get("matches") == ["a"]
        and row(custom, "a").get("value") == "true"
        and row(custom, "a").get("container") == "aside"
        and row(custom, "m").get("value") == "false"
        and row(custom, "m").get("container") == "main"
    )

    unknown = run("unknown_inside_or", NESTED, "(min-width: 400px) or (not-a-size: 1px)")
    unknown_row = row(unknown, "child")
    checks.append(
        unknown.get("matches") == []
        and unknown_row.get("value") == "unknown"
        and unknown_row.get("container") is None
    )
    comma_unknown = run("unknown_in_list", NESTED, "(min-width: 400px), (not-a-size: 1px)")
    checks.append(
        comma_unknown.get("matches") == ["child"]
        and row(comma_unknown, "child", 0).get("container") == "inner"
        and row(comma_unknown, "child", 1).get("value") == "unknown"
    )

    invalid = run("mixed_and_or", NESTED, "(min-width: 1px) and (min-height: 1px) or (min-width: 1px)")
    checks.append(invalid.get("outcome") == "invalid" and invalid.get("reason") == "mixed and or")
    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
