"""Match style() and scroll-state() container queries.

Prints JSON with boolean passed and nonempty observed. Exit 0 whether or not
the candidate answers those features. A missing matcher is an unmet outcome.
"""

from __future__ import annotations

import json


def box(identity: str, parent: str | None, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"id": identity, "parent": parent, "width": 1, "height": 1}
    row.update(extra)
    return row


REGISTERED = {
    "--count": "<number>",
    "--gap": "<length>",
    "--i": "<integer>",
    "--p": "<percentage>",
}
NEAR = [
    box(
        "page",
        None,
        container_type="size",
        container_name="page",
        width=50,
        height=40,
        custom={"--theme": "dark"},
    ),
    box(
        "card",
        "page",
        custom={
            "--theme": "light",
            "--count": "3",
            "--gap": "2em",
            "--i": "3",
            "--p": "40%",
            "--pad": "8px  4px",
        },
        registered=REGISTERED,
        font_size=16,
    ),
    box("child", "card"),
]
LABEL = [
    box("label", None, container_name="label", custom={"--theme": "dark"}),
    box("text", "label"),
]
PLAIN = [
    box("plain", None, custom={"--count": "9"}),
    box("child2", "plain"),
]
SCROLL = [
    box("host", None, container_type="size", width=500, height=100),
    box(
        "sticky",
        "host",
        container_type="scroll-state",
        stuck=["top"],
        snapped=["x"],
        scrollable=["bottom"],
        custom={"--theme": "dark"},
    ),
    box("item", "sticky"),
]
VERT = [
    box(
        "vert",
        None,
        container_type="scroll-state",
        writing_mode="vertical-rl",
        stuck=["right"],
        snapped=["y"],
    ),
    box("vchild", "vert"),
]
MIX = [
    box(
        "mix",
        None,
        container_type="size scroll-state",
        width=200,
        height=40,
        stuck=["left"],
        custom={"--theme": "ink"},
    ),
    box("mixchild", "mix"),
]
BAND = [
    box(
        "band",
        None,
        container_type="inline-size scroll-state",
        writing_mode="vertical-rl",
        width=10,
        height=80,
        stuck=["right"],
    ),
    box("bandchild", "band"),
]
SOLO = [box("solo", None, container_type="size", width=900, height=100, custom={"--theme": "dark"})]
NESTED = [
    box("outer", None, container_type="size", width=200, height=400),
    box("inner", "outer", container_type="inline-size", width=500, height=50),
    box("nested", "inner"),
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

    def expect(
        name: str,
        elements: list[dict[str, object]],
        query: str,
        element: str,
        value: str,
        container: str | None,
        *,
        matched: bool,
        index: int = 0,
    ) -> None:
        result = run(name, elements, query)
        found = row(result, element, index)
        checks.append(
            result.get("outcome") == "matched"
            and (element in result.get("matches", [])) == matched
            and found.get("value") == value
            and found.get("container") == container
        )

    expect("near_dark", NEAR, "style(--theme: dark)", "child", "false", "card", matched=False)
    expect("near_light", NEAR, "style(--theme: light)", "child", "true", "card", matched=True)
    expect("boolean_set", NEAR, "style(--theme)", "child", "true", "card", matched=True)
    expect("boolean_missing", NEAR, "style(--missing)", "child", "false", "card", matched=False)
    expect("named_page", NEAR, "@container page style(--theme: dark)", "child", "true", "page", matched=True)
    expect(
        "and_reads_size_container",
        NEAR,
        "(min-width: 100px) and style(--theme: dark)",
        "child",
        "false",
        "page",
        matched=False,
    )
    expect(
        "or_does_not_read_nearer_style",
        NEAR,
        "(min-width: 100px) or style(--theme: light)",
        "child",
        "false",
        "page",
        matched=False,
    )
    expect("whitespace", NEAR, "style(--pad: 8px 4px)", "child", "true", "card", matched=True)
    expect("case_sensitive", NEAR, "style(--theme: Light)", "child", "false", "card", matched=False)
    expect("number_range", NEAR, "style(--count > 2)", "child", "true", "card", matched=True)
    expect("inclusive_range", NEAR, "style(2 < --count <= 3)", "child", "true", "card", matched=True)
    expect("exclusive_range", NEAR, "style(2 < --count < 3)", "child", "false", "card", matched=False)
    expect("length_em", NEAR, "style(--gap > 20px)", "child", "true", "card", matched=True)
    expect("integer_range", NEAR, "style(--i > 2)", "child", "true", "card", matched=True)
    expect("integer_fraction", NEAR, "style(--i > 2.5)", "child", "false", "card", matched=False)
    expect("percentage_ge", NEAR, "style(--p >= 40%)", "child", "true", "card", matched=True)
    expect("percentage_gt", NEAR, "style(--p > 40%)", "child", "false", "card", matched=False)
    expect("unit_mismatch", NEAR, "style(--count > 10px)", "child", "false", "card", matched=False)
    expect("non_custom", NEAR, "style(color: red)", "child", "unknown", None, matched=False)
    expect("normal_name", LABEL, "@container label style(--theme: dark)", "text", "true", "label", matched=True)
    expect("unregistered_range", PLAIN, "style(--count > 2)", "child2", "false", "plain", matched=False)

    expect("stuck_top", SCROLL, "scroll-state(stuck: top)", "item", "true", "sticky", matched=True)
    expect("stuck_left_held", SCROLL, "scroll-state(stuck: left)", "item", "false", "sticky", matched=False)
    expect("stuck_none", SCROLL, "scroll-state(stuck: none)", "item", "false", "sticky", matched=False)
    expect("stuck_y", SCROLL, "scroll-state(stuck: y)", "item", "true", "sticky", matched=True)
    expect("stuck_x", SCROLL, "scroll-state(stuck: x)", "item", "false", "sticky", matched=False)
    expect("stuck_block_start", SCROLL, "scroll-state(stuck: block-start)", "item", "true", "sticky", matched=True)
    expect("snapped_x", SCROLL, "scroll-state(snapped: x)", "item", "true", "sticky", matched=True)
    expect("snapped_both", SCROLL, "scroll-state(snapped: both)", "item", "false", "sticky", matched=False)
    expect("snapped_none", SCROLL, "scroll-state(snapped: none)", "item", "false", "sticky", matched=False)
    expect("snapped_inline", SCROLL, "scroll-state(snapped: inline)", "item", "true", "sticky", matched=True)
    expect("snapped_block", SCROLL, "scroll-state(snapped: block)", "item", "false", "sticky", matched=False)
    expect("scrollable_bottom", SCROLL, "scroll-state(scrollable: bottom)", "item", "true", "sticky", matched=True)
    expect("scrollable_top", SCROLL, "scroll-state(scrollable: top)", "item", "false", "sticky", matched=False)
    expect("scrollable_y", SCROLL, "scroll-state(scrollable: y)", "item", "true", "sticky", matched=True)
    expect("scrollable_none", SCROLL, "scroll-state(scrollable: none)", "item", "false", "sticky", matched=False)
    expect("scrollable_block_end", SCROLL, "scroll-state(scrollable: block-end)", "item", "true", "sticky", matched=True)
    expect(
        "not_other_edge",
        SCROLL,
        "not scroll-state(stuck: left)",
        "item",
        "true",
        "sticky",
        matched=True,
    )
    comma = run("comma_style_or_stuck", SCROLL, "style(--theme: light), scroll-state(stuck: top)")
    checks.append(
        comma.get("outcome") == "matched"
        and "item" in comma.get("matches", [])
        and row(comma, "item", 0).get("value") == "false"
        and row(comma, "item", 0).get("container") == "sticky"
        and row(comma, "item", 1).get("value") == "true"
        and row(comma, "item", 1).get("container") == "sticky"
    )
    expect(
        "mixed_needs_both",
        SCROLL,
        "(min-width: 100px) and scroll-state(stuck: top)",
        "item",
        "unknown",
        None,
        matched=False,
    )
    expect("self_excluded", SCROLL, "scroll-state(stuck: top)", "sticky", "unknown", None, matched=False)
    expect("bad_stuck", SCROLL, "scroll-state(stuck: middle)", "item", "unknown", None, matched=False)

    expect("vertical_block_start", VERT, "scroll-state(stuck: block-start)", "vchild", "true", "vert", matched=True)
    expect("vertical_inline_start", VERT, "scroll-state(stuck: inline-start)", "vchild", "false", "vert", matched=False)
    expect("vertical_snapped_inline", VERT, "scroll-state(snapped: inline)", "vchild", "true", "vert", matched=True)
    expect("vertical_snapped_block", VERT, "scroll-state(snapped: block)", "vchild", "false", "vert", matched=False)
    expect(
        "combined_type",
        MIX,
        "(min-width: 100px) and scroll-state(stuck: left)",
        "mixchild",
        "true",
        "mix",
        matched=True,
    )
    expect(
        "inline_and_scroll",
        BAND,
        "(min-height: 40px) and scroll-state(stuck: block-start)",
        "bandchild",
        "true",
        "band",
        matched=True,
    )
    expect("solo_style", SOLO, "style(--theme: dark)", "solo", "unknown", None, matched=False)
    expect("size_still_near", NESTED, "(min-width: 400px)", "nested", "true", "inner", matched=True)

    invalid = run("bad_type", [box("bad", None, container_type="size inline-size")], "(min-width: 1px)")
    checks.append(invalid.get("outcome") == "invalid" and invalid.get("reason") == "container-type")
    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
