"""A Content-Disposition filename comes from filename* or a quoted name.

The RFC 6266 pair keeps the euro from filename* and does not keep the
fallback words EURO rates. ISO-8859-1 byte 0x80 stays U+0080. A quoted
percent sequence is not decoded, a decoded slash keeps only the last
segment, and a repeated filename parameter yields no type and no name.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the reader is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

EXPECTED = {
    "rfc_example": {"type": "attachment", "filename": "example.html"},
    "rfc_space": {"type": "inline", "filename": "an example.html"},
    "rfc_euro": {"type": "attachment", "filename": "\u20ac rates"},
    "rfc_pair": {"type": "attachment", "filename": "\u20ac rates"},
    "latin1_byte": {"type": "inline", "filename": "\u0080"},
    "latin1_alias": {"type": "attachment", "filename": "euro.txt"},
    "broken_utf8": {"type": "attachment", "filename": "fallback.txt"},
    "quoted_percent": {"type": "attachment", "filename": "%2E%2E%2Fsecret.txt"},
    "star_path": {"type": "attachment", "filename": "secret.txt"},
    "quoted_path": {"type": "attachment", "filename": "passwd"},
    "quoted_backslash": {"type": "attachment", "filename": "evil.txt"},
    "plus_space": {"type": "attachment", "filename": "a+b c"},
    "form_name": {"type": "form-data", "filename": "up.txt"},
    "encoded_word": {"type": "attachment", "filename": "=?UTF-8?Q?caf=C3=A9?="},
    "no_type": {"type": "", "filename": ""},
    "duplicate": {"type": "", "filename": ""},
}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.content_disposition import content_disposition
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}
    headers = {
        "rfc_example": "Content-Disposition: Attachment; filename=example.html",
        "rfc_space": 'Content-Disposition: INLINE; FILENAME= "an example.html"',
        "rfc_euro": "Content-Disposition: attachment; filename*= UTF-8''%e2%82%ac%20rates",
        "rfc_pair": 'attachment; filename="EURO rates"; filename*=utf-8\'\'%e2%82%ac%20rates',
        "latin1_byte": "inline; filename=\"euro.txt\"; filename*=iso-8859-1''%80",
        "latin1_alias": "attachment; filename=\"euro.txt\"; filename*=latin1''%80",
        "broken_utf8": "attachment; filename=\"fallback.txt\"; filename*=utf-8''%FF.txt",
        "quoted_percent": 'attachment; filename="%2E%2E%2Fsecret.txt"',
        "star_path": "attachment; filename*=UTF-8''..%2Fsecret.txt",
        "quoted_path": 'attachment; filename="../../etc/passwd"',
        "quoted_backslash": 'attachment; filename="dir\\\\evil.txt"',
        "plus_space": "attachment; filename*=UTF-8''a+b%20c",
        "form_name": 'form-data; name="field"; filename="up.txt"',
        "encoded_word": 'attachment; filename="=?UTF-8?Q?caf=C3=A9?="',
        "no_type": 'filename="orphan.txt"',
        "duplicate": "attachment; filename=a.txt; filename=b.txt",
    }
    try:
        observed = {name: content_disposition(header) for name, header in headers.items()}
    except Exception as exc:  # noqa: BLE001 - a broken reader is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}
    return observed == EXPECTED, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=True))


if __name__ == "__main__":
    main()
