"""Encoding Standard labels are not Python codec names.

iso-8859-1 byte 0x80 is the euro sign and byte 0x81 stays U+0081.
Shift_JIS byte 0x5C is the yen sign, while the same byte as a trail stays
a double-byte character. gb2312 byte 0x80 is the euro sign, and gb18030
bytes 0x81 0x80 stay one character. x-user-defined maps 0x80 to U+F780.
A leading BOM overrides the fallback label. The replacement encoding emits
one U+FFFD. An unknown label is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without decode_text is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.encoding_standard import EncodingError, decode_text, encoding_name
    except Exception as exc:  # noqa: BLE001 - baseline without the decoder still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    try:
        decoded = {
            "latin1_euro": decode_text(b"\x80", "iso-8859-1"),
            "latin1_c1": decode_text(b"\x81", " latin1 "),
            "ascii_euro": decode_text(b"\x80", "us-ascii"),
            "yen": decode_text(b"\x5c", "shift_jis"),
            "overline": decode_text(b"\x7e", "shift_jis"),
            "hiragana": decode_text(b"\x82\xa0", "shift-jis"),
            "yen_trail": decode_text(b"\x81\x5c", "sjis"),
            "gb_euro": decode_text(b"\x80", "gb2312"),
            "gb_pair": decode_text(b"\x81\x80", "gbk"),
            "user_defined": decode_text(b"\x80\xff", "x-user-defined"),
            "user_ascii": decode_text(b"A", "x-user-defined"),
            "replacement": decode_text(b"\xff\x00", "replacement"),
            "replacement_empty": decode_text(b"", "replacement"),
            "replacement_bom": decode_text(b"\xef\xbb\xbfA", "replacement"),
            "utf8_bom": decode_text(b"\xef\xbb\xbfA", "utf-8"),
            "utf8_overridden": decode_text(b"\xff\xfe\x61\x00", "utf-8"),
            "lone_surrogate": decode_text(b"\x00\xd8", "utf-16le"),
            "name_cyrillic": encoding_name("  Cyrillic "),
            "name_unknown": encoding_name("utf-7"),
        }
        try:
            decode_text(b"A", "utf-7")
            decoded["unknown_label"] = "accepted"
        except EncodingError:
            decoded["unknown_label"] = "rejected"
        except Exception as exc:  # noqa: BLE001 - a different failure is a miss
            decoded["unknown_label"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001 - a partial decoder is a miss
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    expected = {
        "latin1_euro": "\u20ac",
        "latin1_c1": "\u0081",
        "ascii_euro": "\u20ac",
        "yen": "\u00a5",
        "overline": "\u203e",
        "hiragana": "\u3042",
        "yen_trail": "\u2015",
        "gb_euro": "\u20ac",
        "gb_pair": "\u4e90",
        "user_defined": "\uf780\uf7ff",
        "user_ascii": "A",
        "replacement": "\ufffd",
        "replacement_empty": "",
        "replacement_bom": "A",
        "utf8_bom": "A",
        "utf8_overridden": "a",
        "lone_surrogate": "\ufffd",
        "name_cyrillic": "ISO-8859-5",
        "name_unknown": None,
        "unknown_label": "rejected",
    }
    mismatches = [name for name, want in expected.items() if decoded.get(name) != want]
    observed: dict[str, object] = {"decoded": decoded}
    if mismatches:
        observed["mismatches"] = mismatches
        return False, observed
    return True, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
