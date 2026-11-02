"""Out-of-range XML numeric character references parse as text.

``&#65;`` and ``&#1114111;`` still decode. ``&#9999999;``, ``&#xFFFFFF;``, and
``&#1114112;`` stay as their original reference text in tag text and in an
attribute. The previous bundle raised RangeError for those code points.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json


_LAST = chr(0x10FFFF)


def _codes(value: object) -> list[int] | str:
    if isinstance(value, str):
        return [ord(char) for char in value]
    return type(value).__name__


def observe() -> tuple[bool, dict]:
    observed: dict = {}
    try:
        from blackhole_agent.xml_numeric_entity import parse_xml
    except Exception as exc:  # noqa: BLE001 - baseline without the parser still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    documents = {
        "letter": "<root>&#65;</root>",
        "decimal_overflow": "<root>&#9999999;</root>",
        "hex_overflow": "<root>&#xFFFFFF;</root>",
        "last_code_point": "<root>&#1114111;</root>",
        "past_last": "<root>&#1114112;</root>",
        "mixed": '<root attr="&#9999999;&#x41;">&#xFFFFFF;&#65;</root>',
    }
    parsed: dict = {}
    for name, document in documents.items():
        try:
            parsed[name] = parse_xml(document)
        except Exception as exc:  # noqa: BLE001 - an unmet document stays observable
            observed[name] = {"error": type(exc).__name__, "detail": str(exc)[:240]}
            return False, observed
    letter = parsed["letter"].get("root")
    decimal = parsed["decimal_overflow"].get("root")
    hex_overflow = parsed["hex_overflow"].get("root")
    last = parsed["last_code_point"].get("root")
    past = parsed["past_last"].get("root")
    mixed = parsed["mixed"].get("root")
    mixed_text = mixed.get("#text") if isinstance(mixed, dict) else None
    mixed_attr = mixed.get("@_attr") if isinstance(mixed, dict) else None
    observed.update(
        {
            "letter": letter,
            "decimal_overflow": decimal,
            "hex_overflow": hex_overflow,
            "last_code_point": _codes(last),
            "past_last": past,
            "mixed_text": mixed_text,
            "mixed_attr": mixed_attr,
        }
    )
    passed = bool(
        letter == "A"
        and decimal == "&#9999999;"
        and hex_overflow == "&#xFFFFFF;"
        and last == _LAST
        and past == "&#1114112;"
        and mixed_text == "&#xFFFFFF;A"
        and mixed_attr == "&#9999999;A"
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
