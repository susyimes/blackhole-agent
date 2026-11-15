"""Parse file URLs the way the WHATWG URL standard does.

Exit 0 for both a miss and a hit. The same probe runs against the previous
milestone source and the candidate source. It prints one JSON object with
boolean passed and a nonempty observed object. A parser that still rejects
the file scheme is an unmet outcome, not a crash.

Fixtures are rows from the web-platform-tests URL suite (urltestdata):
Windows drive letters, a UNC host, localhost erasure, a parent segment that
must not delete a lone drive, and file hosts the standard rejects.
"""

from __future__ import annotations

import json

# input, base, expected href, failure
CASES = (
    ("file:///C|/Windows", None, "file:///C:/Windows", False),
    ("file://localhost/tmp", None, "file:///tmp", False),
    ("file://server/share", None, "file://server/share", False),
    ("..", "file:///C:/", "file:///C:/", False),
    ("..", "file:///ab:/", "file:///", False),
    ("C|", "file://host/dir/file", "file://host/C:", False),
    ("//C:/", "file://host/", "file:///C:/", False),
    ("file:c:\\foo\\bar.html", "file:///tmp/mock/path", "file:///c:/foo/bar.html", False),
    ("file://a\u00adb/p", None, "file://ab/p", False),
    (
        "file://loC\U0001d400\U0001d40b\U0001d407\U0001d428\U0001d42c\U0001d42d/usr/bin",
        None,
        "file:///usr/bin",
        False,
    ),
    ("file://example:1/", None, None, True),
    ("file://example%/", None, None, True),
)


def observe() -> tuple[bool, dict[str, object]]:
    observed: dict[str, object] = {}
    try:
        from blackhole_agent.whatwg_url import URLParseError, parse_href
    except Exception as exc:  # noqa: BLE001 - baseline without the parser still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    parsed: dict[str, object] = {}
    try:
        for text, base, expected, failure in CASES:
            key = text if base is None else f"{text} @ {base}"
            try:
                href = parse_href(text, base)
            except URLParseError as exc:
                if not failure:
                    parsed[key] = f"URLParseError: {exc}"
                    return False, {"parsed": parsed, "mismatch": key}
                parsed[key] = "URLParseError"
                continue
            if failure or href != expected:
                parsed[key] = href
                return False, {"parsed": parsed, "mismatch": key, "expected": expected}
            parsed[key] = href
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still print JSON
        return False, {"parsed": parsed, "error": f"{type(exc).__name__}: {exc}"}

    observed = {"parsed": parsed, "count": len(parsed)}
    return len(parsed) == len(CASES), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
