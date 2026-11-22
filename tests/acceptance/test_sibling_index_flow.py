"""Size boxes from sibling-index() and sibling-count().

A hidden element still occupies an index. A display:contents parent does not
become the child's sibling. A commented mention is not a call. An argument
and a bare function are not lengths.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json

_PAGE = (
    '<div id="page"><div id="one"></div><div id="gone"></div>'
    '<div id="two"></div><p id="next">Z</p></div>'
)
_INDEX = (
    "#page { font-size: 10px; line-height: 10px; }"
    "#gone { display: none; }"
    "#one { height: 10px; width: calc(sibling-index() * 10%); }"
    "#two { height: 10px; width: calc(sibling-index() * 20px);"
    " margin-left: calc((sibling-index() - 1) * 5px); }"
)
_COUNT = (
    '<div id="page"><div id="one"></div><div id="gone"></div><div id="two"></div></div>',
    "#gone { display: none; }"
    "#one, #two { height: 10px; width: calc(sibling-count() * 10px); }",
)
_CONTENTS = (
    '<div id="page"><div id="before"></div><div id="wrap"><div id="inner"></div></div></div>',
    "#page { font-size: 10px; line-height: 10px; }"
    "#before { width: 10px; height: 10px; }"
    "#wrap { display: contents; }"
    "#inner { height: 10px; width: calc(sibling-index() * 20px); }",
)
_ARGUMENT = (
    '<div id="only"></div>',
    "#only { height: 10px; width: calc(sibling-index(1) * 10px); }",
)
_BARE = (
    '<div id="only"></div>',
    "#only { height: 10px; width: sibling-index(); }",
)
_PLAIN = (
    '<div id="plain"></div>',
    "#plain { height: 10px; width: calc(30px /* sibling-index() */); }",
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _placed(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
    }


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    indexed = _lay(layout_normal_flow, _PAGE, _INDEX)
    counted = _lay(layout_normal_flow, _COUNT[0], _COUNT[1])
    contents = _lay(layout_normal_flow, _CONTENTS[0], _CONTENTS[1])
    argument = _lay(layout_normal_flow, _ARGUMENT[0], _ARGUMENT[1])
    bare = _lay(layout_normal_flow, _BARE[0], _BARE[1])
    plain = _lay(layout_normal_flow, _PLAIN[0], _PLAIN[1])

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    observed: dict[str, object] = {
        "index_outcome": indexed.get("outcome"),
        "index_reason": indexed.get("reason"),
        "one": _placed(take(indexed, "one")),
        "two": _placed(take(indexed, "two")),
        "next": _placed(take(indexed, "next")),
        "count_outcome": counted.get("outcome"),
        "count_reason": counted.get("reason"),
        "count_one": _placed(take(counted, "one")),
        "count_two": _placed(take(counted, "two")),
        "contents_outcome": contents.get("outcome"),
        "contents_reason": contents.get("reason"),
        "inner": _placed(take(contents, "inner")),
        "before": _placed(take(contents, "before")),
        "argument_outcome": argument.get("outcome"),
        "argument_reason": argument.get("reason"),
        "bare_outcome": bare.get("outcome"),
        "bare_reason": bare.get("reason"),
        "plain_outcome": plain.get("outcome"),
        "plain_reason": plain.get("reason"),
        "plain": _placed(take(plain, "plain")),
    }
    checks = {
        "hidden_sibling_keeps_its_index": (
            indexed.get("outcome") == "placed"
            and _near(take(indexed, "one"), x=0, y=0, content_width=20, content_height=10)
            and _near(take(indexed, "two"), x=10, y=10, content_width=60, content_height=10)
            and _near(take(indexed, "next"), x=0, y=20, content_width=200, content_height=10)
        ),
        "hidden_sibling_keeps_the_count": (
            counted.get("outcome") == "placed"
            and _near(take(counted, "one"), x=0, y=0, content_width=30, content_height=10)
            and _near(take(counted, "two"), x=0, y=10, content_width=30, content_height=10)
        ),
        "contents_parent_does_not_reparent_the_index": (
            contents.get("outcome") == "placed"
            and _near(take(contents, "before"), x=0, y=0, content_width=10, content_height=10)
            and _near(take(contents, "inner"), x=0, y=10, content_width=20, content_height=10)
        ),
        "argument_is_invalid": argument.get("outcome") == "invalid",
        "bare_function_is_invalid": bare.get("outcome") == "invalid",
        "comment_is_not_a_call": (
            plain.get("outcome") == "placed"
            and _near(take(plain, "plain"), x=0, y=0, content_width=30, content_height=10)
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
