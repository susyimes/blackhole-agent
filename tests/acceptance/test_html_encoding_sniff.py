"""HTML encoding sniffing is not a search for meta charset bytes.

A little-endian <?x prefix is UTF-16LE and is not a BOM. A comment closed by
the opener's own dashes does not hide the next meta charset. x-user-defined
in that meta is windows-1252, while the same label in an XML declaration is
kept. An XML declaration supplies ISO-8859-2 when no meta does, and the
following byte 0xA1 decodes as U+0104. A UTF-8 BOM beats a transport label.
That transport label iso-8859-1, with no BOM, is windows-1252 and ignores a
meta charset. A meta that begins after the first 1024 bytes does not win.
A parent UTF-16 encoding is not inherited. FF FE 00 00 is UTF-16LE.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the sniffer is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.encoding_standard import decode_text
        from blackhole_agent.html_encoding import sniff_html_encoding
    except Exception as exc:  # noqa: BLE001 - baseline without the sniffer still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    meta = b"<meta charset=utf-8>"
    try:
        sniffed = {
            "utf16_le_prefix": sniff_html_encoding(b"<\x00?\x00x\x00"),
            "utf16_be_prefix": sniff_html_encoding(b"\x00<\x00?\x00x"),
            "utf16_upper_x": sniff_html_encoding(b"<\x00?\x00X\x00"),
            "comment_shares_dashes": sniff_html_encoding(b"<!--><meta charset=gbk>"),
            "comment_hides_meta": sniff_html_encoding(
                b"<!-- <meta charset=gbk> --><meta charset=utf-8>"
            ),
            "user_defined_meta": sniff_html_encoding(b"<meta charset=x-user-defined>"),
            "user_defined_xml": sniff_html_encoding(b'<?xml encoding="x-user-defined"?>'),
            "xml_latin2": sniff_html_encoding(b'<?xml encoding="iso-8859-2"?>\xa1'),
            "xml_utf16": sniff_html_encoding(b'<?xml encoding="utf-16"?>'),
            "bom_beats_transport": sniff_html_encoding(
                b"\xef\xbb\xbf<meta charset=gbk>",
                transport="iso-8859-1",
            ),
            "transport_latin1": sniff_html_encoding(
                b"<meta charset=gbk>",
                transport="iso-8859-1",
            ),
            "unknown_transport": sniff_html_encoding(
                b"<meta charset=utf-8>",
                transport="utf-7",
            ),
            "meta_inside_limit": sniff_html_encoding(b"x" * (1024 - len(meta)) + meta),
            "meta_past_limit": sniff_html_encoding(b"x" * 1024 + meta),
            "parent_gbk": sniff_html_encoding(b"<div></div>", parent="gbk"),
            "parent_utf16": sniff_html_encoding(b"<div></div>", parent="utf-16"),
            "utf16_bom_not_utf32": sniff_html_encoding(b"\xff\xfe\x00\x00"),
            "poison_charset": sniff_html_encoding(
                b'<meta charset=bogus http-equiv=content-type content="text/html; charset=gbk">'
            ),
            "pragma_content": sniff_html_encoding(
                b'<meta content="text/html; charset=gbk" http-equiv=content-type>'
            ),
            "first_charset": sniff_html_encoding(b"<meta charset=utf-8 charset=gbk>"),
        }
        sniffed["latin2_byte"] = decode_text(b'<?xml encoding="iso-8859-2"?>\xa1', "iso-8859-2")[-1]
    except Exception as exc:  # noqa: BLE001 - a partial sniffer is a miss
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    expected = {
        "utf16_le_prefix": ("UTF-16LE", "tentative"),
        "utf16_be_prefix": ("UTF-16BE", "tentative"),
        "utf16_upper_x": ("windows-1252", "tentative"),
        "comment_shares_dashes": ("GB18030", "tentative"),
        "comment_hides_meta": ("UTF-8", "tentative"),
        "user_defined_meta": ("windows-1252", "tentative"),
        "user_defined_xml": ("x-user-defined", "tentative"),
        "xml_latin2": ("ISO-8859-2", "tentative"),
        "xml_utf16": ("UTF-8", "tentative"),
        "bom_beats_transport": ("UTF-8", "certain"),
        "transport_latin1": ("windows-1252", "certain"),
        "unknown_transport": ("UTF-8", "tentative"),
        "meta_inside_limit": ("UTF-8", "tentative"),
        "meta_past_limit": ("windows-1252", "tentative"),
        "parent_gbk": ("GB18030", "tentative"),
        "parent_utf16": ("windows-1252", "tentative"),
        "utf16_bom_not_utf32": ("UTF-16LE", "certain"),
        "poison_charset": ("windows-1252", "tentative"),
        "pragma_content": ("GB18030", "tentative"),
        "first_charset": ("UTF-8", "tentative"),
        "latin2_byte": "\u0104",
    }
    mismatches = [name for name, want in expected.items() if sniffed.get(name) != want]
    observed: dict[str, object] = {
        "sniffed": {key: list(value) if isinstance(value, tuple) else value for key, value in sniffed.items()}
    }
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
