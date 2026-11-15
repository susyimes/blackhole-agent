"""WHATWG domain parser, not IDNA 2003 nameprep.

A sharp s must stay a punycode label. A final sigma must not fold into sigma.
An underscore inside that label and a leading hyphen stay. An A-label that
decodes to a mapped character fails when the domain is not ASCII. An ASCII
underscore host and a Windows file URL stay as they are.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a miss
and a hit. The previous parser returns passed false because it rewrites the
sharp s to ss.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    observed: dict[str, object] = {}
    try:
        from blackhole_agent.whatwg_url import URLParseError, parse_href
    except Exception as exc:  # noqa: BLE001 - a missing parser is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    expected = {
        "sharp_s": ("https://faß.de/", "https://xn--fa-hia.de/"),
        "final_sigma": ("https://ς.example/", "https://xn--3xa.example/"),
        "sigma": ("https://σ.example/", "https://xn--4xa.example/"),
        "underscore_deviation": ("https://faß_bar.example/", "https://xn--fa_bar-cta.example/"),
        "leading_hyphen": ("https://-ß.example/", "https://xn----qfa.example/"),
        "emoji": ("https://☕.example/", "https://xn--53h.example/"),
        "ascii_underscore": ("https://foo_bar.example/", "https://foo_bar.example/"),
        "file_drive": ("file:///C|/Windows", "file:///C:/Windows"),
    }
    parsed: dict[str, object] = {}
    for name, (text, href) in expected.items():
        try:
            got = parse_href(text)
        except Exception as exc:  # noqa: BLE001 - record the miss and keep going
            parsed[name] = f"{type(exc).__name__}: {exc}"
            continue
        parsed[name] = got
        if got != href:
            observed = {"parsed": parsed, "mismatch": name, "expected": href}
            return False, observed

    mapped = "https://faß.xn--8i7caa/"
    try:
        parsed["mapped_alabel"] = parse_href(mapped)
    except URLParseError as exc:
        parsed["mapped_alabel"] = type(exc).__name__
    except Exception as exc:  # noqa: BLE001
        parsed["mapped_alabel"] = f"{type(exc).__name__}: {exc}"

    bidi = "https://1א.example/"
    try:
        parsed["bidi"] = parse_href(bidi)
    except URLParseError as exc:
        parsed["bidi"] = type(exc).__name__
    except Exception as exc:  # noqa: BLE001
        parsed["bidi"] = f"{type(exc).__name__}: {exc}"

    joiner = "https://a\u200dß.example/"
    try:
        parsed["joiner"] = parse_href(joiner)
    except URLParseError as exc:
        parsed["joiner"] = type(exc).__name__
    except Exception as exc:  # noqa: BLE001
        parsed["joiner"] = f"{type(exc).__name__}: {exc}"

    observed = {"parsed": parsed}
    passed = parsed == {
        "sharp_s": "https://xn--fa-hia.de/",
        "final_sigma": "https://xn--3xa.example/",
        "sigma": "https://xn--4xa.example/",
        "underscore_deviation": "https://xn--fa_bar-cta.example/",
        "leading_hyphen": "https://xn----qfa.example/",
        "emoji": "https://xn--53h.example/",
        "ascii_underscore": "https://foo_bar.example/",
        "file_drive": "file:///C:/Windows",
        "mapped_alabel": "URLParseError",
        "bidi": "URLParseError",
        "joiner": "URLParseError",
    }
    return passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
