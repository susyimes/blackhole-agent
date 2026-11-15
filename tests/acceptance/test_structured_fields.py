"""Parse and serialize an HTTP structured field.

A dictionary member with no equals sign is true. A parameter with no value
is true. Sixteen digits is not an integer. A display string percent-decodes
lowercase UTF-8. A date keeps the signed integer after @. Decimals round
half-even to three places. Prints JSON with boolean passed and nonempty
observed. Exit 0 for both a miss and a hit. A tree without this parser is
an unmet outcome.
"""

from __future__ import annotations

import json
from decimal import Decimal


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.structured_fields import (
            StructuredFieldError,
            parse_structured_field,
            serialize_structured_field,
        )
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    def rejected(raw: str, kind: str) -> str:
        try:
            parse_structured_field([raw], kind)
        except StructuredFieldError as exc:
            return exc.reason
        return "accepted"

    def serialized(value: object, kind: str) -> str:
        try:
            return serialize_structured_field(value, kind)
        except StructuredFieldError as exc:
            return exc.reason

    dictionary = parse_structured_field(["a=?0, b, c; foo=bar"], "dictionary")
    flagged = parse_structured_field(["1; a; b=?0"], "item")
    inner = parse_structured_field(['("foo"; a=1;b=2);lvl=5'], "list")
    decimal = parse_structured_field(["1.230"], "item")
    duplicate = parse_structured_field(["a=1, b=2, a=3"], "dictionary")
    parameters = parse_structured_field(["a;b=1;c=2;b=3"], "list")
    binary = parse_structured_field([":aGVsbG8=:"], "item")
    observed: dict[str, object] = {
        "dictionary": serialize_structured_field(dictionary, "dictionary"),
        "bare_member_is_true": dictionary[1][1][0] is True,
        "bare_parameter_is_true": flagged[1][0][1] is True,
        "false_parameter": flagged[1][1][1] is False,
        "parameter_token": dictionary[2][1][1][0][1]["value"],
        "sixteen_digit": rejected("1234567890123456", "item"),
        "sixteen_leading_zeros": rejected("0000000000000001", "item"),
        "display": parse_structured_field(['%"f%c3%bc"'], "item")[0]["value"],
        "uppercase_percent": rejected('%"%C3%bc"', "item"),
        "bad_utf8": rejected('%"%c3%28"', "item"),
        "date": parse_structured_field(["@-1659578233"], "item")[0]["value"],
        "negative_zero_date": serialize_structured_field(
            parse_structured_field(["@-0"], "item"), "item"
        ),
        "inner": serialize_structured_field(inner, "list"),
        "inner_member_parameters": inner[0][0][0][1],
        "inner_list_parameters": inner[0][1],
        "decimal": str(decimal[0]),
        "decimal_canonical": serialize_structured_field(decimal, "item"),
        "half_even_odd": serialized([Decimal("0.0015"), []], "item"),
        "half_even_even": serialized([Decimal("0.0025"), []], "item"),
        "round_into_integer": serialized([Decimal("9.9995"), []], "item"),
        "round_past_integer_limit": serialized([Decimal("999999999999.9996"), []], "item"),
        "integer_limit": serialized([10**15, []], "item"),
        "duplicate_key": serialize_structured_field(duplicate, "dictionary"),
        "duplicate_parameter": serialize_structured_field(parameters, "list"),
        "leading_zero": parse_structured_field(["042"], "item")[0],
        "binary": binary[0]["value"].decode("ascii"),
    }
    passed = observed == {
        "dictionary": "a=?0, b, c;foo=bar",
        "bare_member_is_true": True,
        "bare_parameter_is_true": True,
        "false_parameter": True,
        "parameter_token": "bar",
        "sixteen_digit": "integer",
        "sixteen_leading_zeros": "integer",
        "display": "fü",
        "uppercase_percent": "display-string",
        "bad_utf8": "display-string",
        "date": -1659578233,
        "negative_zero_date": "@0",
        "inner": '("foo";a=1;b=2);lvl=5',
        "inner_member_parameters": [["a", 1], ["b", 2]],
        "inner_list_parameters": [["lvl", 5]],
        "decimal": "1.23",
        "decimal_canonical": "1.23",
        "half_even_odd": "0.002",
        "half_even_even": "0.002",
        "round_into_integer": "10.0",
        "round_past_integer_limit": "serialize-decimal",
        "integer_limit": "serialize-integer",
        "duplicate_key": "a=3, b=2",
        "duplicate_parameter": "a;b=3;c=2",
        "leading_zero": 42,
        "binary": "hello",
    }
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
