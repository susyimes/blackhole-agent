"""Form bodies follow the URL Standard, not urllib.parse.

urlencode percent-encodes a star and leaves a tilde raw. parse_qsl drops an
empty field and keeps a leading BOM on the name. latin-1 cannot encode a
euro sign. The form serializer keeps the star, percent-encodes the tilde,
strips one leading BOM, keeps the empty field, and emits the windows-1252
byte for a euro sign when the label is latin1. An HTML form turns a bare
newline into CRLF before that serialization.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlencode


def _stdlib() -> dict:
    latin_error = ""
    try:
        urlencode([("q", "\u20ac")], encoding="latin-1")
    except UnicodeEncodeError as exc:
        latin_error = type(exc).__name__
    return {
        "blank": parse_qsl("a=&b"),
        "bom": parse_qsl("%EF%BB%BFa=1"),
        "star": urlencode([("q", "*")]),
        "tilde": urlencode([("q", "~")]),
        "newline": urlencode([("note", "a\nb")]),
        "latin1_euro": latin_error,
    }


def observe() -> tuple[bool, dict]:
    stdlib = _stdlib()
    observed: dict = {"stdlib": stdlib}
    try:
        from blackhole_agent.form_urlencoded import (
            parse_form_bytes,
            parse_form_urlencoded,
            serialize_form_urlencoded,
            serialize_html_form,
        )
    except Exception as exc:  # noqa: BLE001 - baseline without the codec still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    parsed = {
        "blank": parse_form_urlencoded("a=&b"),
        "bom": parse_form_urlencoded("%EF%BB%BFa=1"),
        "plus": parse_form_urlencoded("a=%2B+"),
        "replacement": parse_form_urlencoded("a=%FF"),
        "nested_equals": parse_form_urlencoded("a=b=c"),
        "skipped_empty": parse_form_urlencoded("a=1&&b=2"),
        "lone_equals": parse_form_urlencoded("="),
        "bytes": parse_form_bytes(b"q=*"),
    }
    serialized = {
        "star": serialize_form_urlencoded([("q", "*")]),
        "tilde": serialize_form_urlencoded([("q", "~")]),
        "slash": serialize_form_urlencoded([("q", "a/b")]),
        "euro_latin1": serialize_form_urlencoded([("q", "\u20ac")], encoding="latin1"),
        "euro_iso": serialize_form_urlencoded([("q", "\u20ac")], encoding="iso-8859-1"),
        "unencodable": serialize_form_urlencoded([("q", "\u0100")], encoding="latin1"),
        "newline": serialize_form_urlencoded([("note", "a\nb")]),
        "unknown_label": serialize_form_urlencoded([("q", "\u00e9")], encoding="not-a-charset"),
    }
    html = {
        "value": serialize_html_form([("note", "a\nb\rc")]),
        "name": serialize_html_form([("a\nb", "c")]),
    }
    round_trip = [("q", "*~ /\u00e9"), ("a", "1"), ("a", "2"), ("", ""), ("sp", " x "), ("plus", "+")]
    again = parse_form_urlencoded(serialize_form_urlencoded(round_trip))
    observed.update(
        {
            "parsed": {key: list(value) for key, value in parsed.items()},
            "serialized": serialized,
            "html": html,
            "round_trip": list(again),
        }
    )
    expected_parse = {
        "blank": [("a", ""), ("b", "")],
        "bom": [("a", "1")],
        "plus": [("a", "+ ")],
        "replacement": [("a", "\ufffd")],
        "nested_equals": [("a", "b=c")],
        "skipped_empty": [("a", "1"), ("b", "2")],
        "lone_equals": [("", "")],
        "bytes": [("q", "*")],
    }
    expected_serialize = {
        "star": "q=*",
        "tilde": "q=%7E",
        "slash": "q=a%2Fb",
        "euro_latin1": "q=%80",
        "euro_iso": "q=%80",
        "unencodable": "q=%26%23256%3B",
        "newline": "note=a%0Ab",
        "unknown_label": "q=%C3%A9",
    }
    passed = (
        parsed == expected_parse
        and serialized == expected_serialize
        and html == {"value": "note=a%0D%0Ab%0D%0Ac", "name": "a%0D%0Ab=c"}
        and again == round_trip
        and stdlib["blank"] == []
        and stdlib["bom"] == [("\ufeffa", "1")]
        and stdlib["star"] == "q=%2A"
        and stdlib["tilde"] == "q=~"
        and stdlib["newline"] == "note=a%0Ab"
        and stdlib["latin1_euro"] == "UnicodeEncodeError"
    )
    return passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
