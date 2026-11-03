"""Special-scheme URLs serialize the way the WHATWG URL standard does.

Python urllib keeps a default port and a backslash. An octal IPv4 address and
a same-scheme relative reference have to come out as the standard's result.
An invalid octal octet and a port above 65535 are rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit, urlunsplit


def observe() -> tuple[bool, dict]:
    observed: dict = {}
    try:
        from blackhole_agent.whatwg_url import URLParseError, parse_href
    except Exception as exc:  # noqa: BLE001 - baseline without the parser still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    samples = {
        "default_port": ("https://example.com:443/a", None, "https://example.com/a"),
        "backslash": ("https://example.com\\foo\\bar", None, "https://example.com/foo/bar"),
        "octal_ipv4": ("http://192.168.010.001/", None, "http://192.168.8.1/"),
        "same_scheme": ("https:bar", "https://example.com/a/b/c", "https://example.com/a/b/bar"),
        "tab_and_space": ("https://ex\tample.com/a b", None, "https://example.com/a%20b"),
        "userinfo_at": ("http://user:p@ss@example.com/", None, "http://user:p%40ss@example.com/"),
        "ipv6_default_port": ("http://[::1]:80/", None, "http://[::1]/"),
        "short_ipv4": ("http://127.1/", None, "http://127.0.0.1/"),
        "dot_segment": ("..", "https://example.com/a/b/c", "https://example.com/a/"),
    }
    parsed: dict = {}
    for name, (text, base, expected) in samples.items():
        try:
            href = parse_href(text, base)
        except Exception as exc:  # noqa: BLE001 - an unmet sample stays observable
            observed[name] = {"error": type(exc).__name__, "detail": str(exc)[:240]}
            return False, observed
        parsed[name] = href
        if href != expected:
            observed["parsed"] = parsed
            observed["mismatch"] = name
            return False, observed

    rejected: dict = {}
    for name, text in (
        ("bad_octal", "http://192.168.008.001/"),
        ("port_overflow", "http://example.com:65536/"),
    ):
        try:
            href = parse_href(text)
        except URLParseError as exc:
            rejected[name] = type(exc).__name__
            continue
        except Exception as exc:  # noqa: BLE001
            observed["parsed"] = parsed
            observed[name] = {"error": type(exc).__name__}
            return False, observed
        observed["parsed"] = parsed
        observed[name] = href
        return False, observed

    stdlib_port = urlunsplit(urlsplit("https://example.com:443/a"))
    stdlib_slash = urlunsplit(urlsplit("https://example.com\\foo\\bar"))
    observed = {
        "parsed": parsed,
        "rejected": rejected,
        "urllib_keeps_port": ":443" in stdlib_port,
        "urllib_keeps_backslash": "\\" in stdlib_slash,
    }
    passed = (
        rejected == {"bad_octal": "URLParseError", "port_overflow": "URLParseError"}
        and ":443" in stdlib_port
        and "\\" in stdlib_slash
    )
    return passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
