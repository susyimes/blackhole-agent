"""Decide cache equivalence under a No-Vary-Search header.

key-order ignores parameter order and keeps duplicate keys in their original
order. params drops named keys. except keeps only named keys. An absent,
empty-params, false key-order, or rejected header compares the raw query.
A non-default header parses the query, so percent-decoding and a bare
question mark can make two URLs match. A fragment, userinfo, default port,
and host case do not split them. An unparsable URL is invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the decision is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.no_vary_search import no_vary_search_equivalent
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}

    def keep(name: str, left: str, right: str, header: str | None) -> None:
        try:
            result = no_vary_search_equivalent(left, right, header)
            observed[name] = [
                result["outcome"],
                result["equivalent"],
                result["fallback"],
                result["vary_on_key_order"],
                result["no_vary_params"],
                result["vary_params"],
                result["left"],
                result["right"],
            ]
        except Exception as exc:  # noqa: BLE001 - a raised decision is an unmet outcome
            observed[name] = f"{type(exc).__name__}: {exc}"

    order = "https://example.com/a?b=1&a=2"
    keep("key_order", order, "https://example.com/a?a=2&b=1", "key-order")
    keep("key_order_value", order, "https://example.com/a?a=2&b=3", "key-order")
    keep(
        "duplicate_keys",
        "https://example.com/a?b=1&a=2&b=3",
        "https://example.com/a?b=3&a=2&b=1",
        "key-order",
    )
    keep("params_drop", "https://example.com/a?id=2&utm=1", "https://example.com/a?id=2", 'params=("utm")')
    keep("params_value", "https://example.com/a?id=2&utm=1", "https://example.com/a?id=3", 'params=("utm")')
    keep(
        "params_order",
        "https://example.com/a?id=2&x=1",
        "https://example.com/a?x=1&id=2",
        'params=("utm")',
    )
    keep(
        "except_keep",
        "https://example.com/a?id=2&utm=1",
        "https://example.com/a?utm=9&id=2",
        'except=("id")',
    )
    keep("except_all", "https://example.com/a?x=1", "https://example.com/a?y=2", "except=()")
    keep("except_absent_query", "https://example.com/a?x=1", "https://example.com/a", "except=()")
    keep("empty_query", "https://example.com/a", "https://example.com/a?", "key-order")
    keep("raw_absent", order, "https://example.com/a?a=2&b=1", None)
    keep("raw_empty_params", order, "https://example.com/a?a=2&b=1", "params=()")
    keep("raw_key_order_false", order, "https://example.com/a?a=2&b=1", "key-order=?0")
    keep("rejected_boolean", order, "https://example.com/a?a=2&b=1", "params=?1")
    keep("rejected_both", order, "https://example.com/a?a=2&b=1", 'key-order, params=("a"), except=("b")')
    keep("unknown_key", order, "https://example.com/a?a=2&b=1", 'future=("a")')
    keep("percent", "https://example.com/q?a=x", "https://example.com/q?%61=%78", "key-order")
    keep("unicode", "https://example.com/q?a=é", "https://example.com/q?a=%C3%A9", "key-order")
    keep("replacement", "https://example.com/q?a=%f6", "https://example.com/q?a=%EF%BF%BD", "key-order")
    keep("no_unicode_norm", "https://example.com/q?a=%C3%A9", "https://example.com/q?a=e%CC%81", "key-order")
    keep("empty_ampersand", "https://example.com/foo?a=x&&&&", "https://example.com/foo?a=x", "key-order")
    keep("plus_space", "https://example.com/q?a=+", "https://example.com/q?a=%20", "key-order")
    keep("bare_name", "https://example.com/q?a=", "https://example.com/q?a", "key-order")
    keep("path", "https://example.com/a?x=1", "https://example.com/b?x=1", "key-order")
    keep("host_case", "https://EXAMPLE.com/a?x=1", "https://example.com/a?x=1", "key-order")
    keep("default_port", "https://example.com:443/a?x=1", "https://example.com/a?x=1", "key-order")
    keep("fragment", "https://example.com/a?x=1#one", "https://example.com/a?x=1#two", "key-order")
    keep(
        "userinfo",
        "https://user:secret@example.com/a?x=1",
        "https://example.com/a?x=1",
        "key-order",
    )
    keep("dot_segment", "https://example.com/a/../b?x=1", "https://example.com/b?x=1", "key-order")
    keep("scheme", "http://example.com/a?x=1", "https://example.com/a?x=1", "key-order")
    keep(
        "encoded_key",
        "https://example.com/?%C3%A9+%E6%B0%97=1",
        "https://example.com/?%C3%A9%20%E6%B0%97=2",
        'params=("%C3%A9+%E6%B0%97")',
    )
    keep("token_param", order, "https://example.com/a?a=2&b=1", "params=(utm)")
    keep("invalid_url", "not a url", "https://example.com/", "key-order")
    keep(
        "utf16_order",
        "https://example.com/q?\U00010000=1&\uE000=2",
        "https://example.com/q?\uE000=2&\U00010000=1",
        "key-order",
    )

    expected = {
        "key_order": ["equivalent", True, False, False, [], "*", [["a", "2"], ["b", "1"]], [["a", "2"], ["b", "1"]]],
        "key_order_value": ["distinct", False, False, False, [], "*", [["a", "2"], ["b", "1"]], [["a", "2"], ["b", "3"]]],
        "duplicate_keys": [
            "distinct",
            False,
            False,
            False,
            [],
            "*",
            [["a", "2"], ["b", "1"], ["b", "3"]],
            [["a", "2"], ["b", "3"], ["b", "1"]],
        ],
        "params_drop": ["equivalent", True, False, True, ["utm"], "*", [["id", "2"]], [["id", "2"]]],
        "params_value": ["distinct", False, False, True, ["utm"], "*", [["id", "2"]], [["id", "3"]]],
        "params_order": [
            "distinct",
            False,
            False,
            True,
            ["utm"],
            "*",
            [["id", "2"], ["x", "1"]],
            [["x", "1"], ["id", "2"]],
        ],
        "except_keep": ["equivalent", True, False, True, "*", ["id"], [["id", "2"]], [["id", "2"]]],
        "except_all": ["equivalent", True, False, True, "*", [], [], []],
        "except_absent_query": ["equivalent", True, False, True, "*", [], [], []],
        "empty_query": ["equivalent", True, False, False, [], "*", [], []],
        "raw_absent": ["distinct", False, True, True, [], "*", None, None],
        "raw_empty_params": ["distinct", False, False, True, [], "*", None, None],
        "raw_key_order_false": ["distinct", False, False, True, [], "*", None, None],
        "rejected_boolean": ["distinct", False, True, True, [], "*", None, None],
        "rejected_both": ["distinct", False, True, True, [], "*", None, None],
        "unknown_key": ["distinct", False, False, True, [], "*", None, None],
        "percent": ["equivalent", True, False, False, [], "*", [["a", "x"]], [["a", "x"]]],
        "unicode": ["equivalent", True, False, False, [], "*", [["a", "é"]], [["a", "é"]]],
        "replacement": ["equivalent", True, False, False, [], "*", [["a", "\ufffd"]], [["a", "\ufffd"]]],
        "no_unicode_norm": ["distinct", False, False, False, [], "*", [["a", "é"]], [["a", "e\u0301"]]],
        "empty_ampersand": ["equivalent", True, False, False, [], "*", [["a", "x"]], [["a", "x"]]],
        "plus_space": ["equivalent", True, False, False, [], "*", [["a", " "]], [["a", " "]]],
        "bare_name": ["equivalent", True, False, False, [], "*", [["a", ""]], [["a", ""]]],
        "path": ["distinct", False, False, False, [], "*", None, None],
        "host_case": ["equivalent", True, False, False, [], "*", [["x", "1"]], [["x", "1"]]],
        "default_port": ["equivalent", True, False, False, [], "*", [["x", "1"]], [["x", "1"]]],
        "fragment": ["equivalent", True, False, False, [], "*", [["x", "1"]], [["x", "1"]]],
        "userinfo": ["equivalent", True, False, False, [], "*", [["x", "1"]], [["x", "1"]]],
        "dot_segment": ["equivalent", True, False, False, [], "*", [["x", "1"]], [["x", "1"]]],
        "scheme": ["distinct", False, False, False, [], "*", None, None],
        "encoded_key": ["equivalent", True, False, True, ["é 気"], "*", [], []],
        "token_param": ["distinct", False, True, True, [], "*", None, None],
        "invalid_url": ["invalid", False, False, None, None, None, None, None],
        "utf16_order": [
            "equivalent",
            True,
            False,
            False,
            [],
            "*",
            [["\U00010000", "1"], ["\uE000", "2"]],
            [["\U00010000", "1"], ["\uE000", "2"]],
        ],
    }
    return observed == expected, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
