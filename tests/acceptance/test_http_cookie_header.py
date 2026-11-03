"""Cookie storage evicts Max-Age=0 and enforces __Host- and __Secure- prefixes.

Python's cookie jar keeps the previous cookie when Max-Age is zero, stores a
__Host- cookie that carries a Domain, and stores a Secure cookie set over
plain HTTP. The header from cookie_header follows the cookie draft instead.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from email.message import Message
from http.cookiejar import CookieJar
from urllib.request import Request

PAGE = "https://www.example.com/docs/secret/page"
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
RECEIPTS = (
    ("id=docs; Path=/docs", PAGE),
    ("id=deep; Path=/docs/secret", PAGE),
    ("session=abc", PAGE),
    ("shared=1; Domain=example.com; Path=/", PAGE),
    ("gone=old; Path=/", PAGE),
    ("gone=new; Path=/; Max-Age=0", PAGE),
    ("stay=1; Max-Age=3600; Expires=Tue, 01 Jan 1980 00:00:00 GMT; Path=/", PAGE),
    ("__Secure-tok=s; Domain=example.com; Path=/", PAGE),
    ("__Secure-ok=1; Domain=example.com; Path=/; Secure", PAGE),
    ("__Host-bad=1; Domain=example.com; Path=/; Secure", PAGE),
    ("__Host-nop=1; Secure", PAGE),
    ("__Host-ok=1; Secure; Path=/", PAGE),
)
EXPECTED = {
    "page": "id=deep; session=abc; id=docs; shared=1; stay=1; __Secure-ok=1; __Host-ok=1",
    "subdomain": "shared=1; __Secure-ok=1",
    "plain_http": "id=deep; session=abc; id=docs; shared=1; stay=1",
    "other_site": "",
    "path_boundary": "shared=1; stay=1; __Secure-ok=1; __Host-ok=1",
    "http_cannot_set_secure": "",
    "localhost_secure": "__Host-local=1",
    "single_label_domain": "",
}


def _stdlib_header() -> str:
    jar = CookieJar()
    request = Request(PAGE)

    class Response:
        def info(self) -> Message:
            message = Message()
            for line, _url in RECEIPTS:
                message["Set-Cookie"] = line
            return message

    jar.extract_cookies(Response(), request)
    outgoing = Request(PAGE)
    jar.add_cookie_header(outgoing)
    return outgoing.get_header("Cookie") or ""


def observe() -> tuple[bool, dict]:
    observed: dict = {"stdlib": _stdlib_header()}
    try:
        from blackhole_agent.http_cookie import cookie_header
    except Exception as exc:  # noqa: BLE001 - baseline without the jar still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    headers = {
        "page": cookie_header(RECEIPTS, PAGE, now=NOW),
        "subdomain": cookie_header(RECEIPTS, "https://api.example.com/docs/secret/page", now=NOW),
        "plain_http": cookie_header(RECEIPTS, "http://www.example.com/docs/secret/page", now=NOW),
        "other_site": cookie_header(RECEIPTS, "https://notexample.com/", now=NOW),
        "path_boundary": cookie_header(RECEIPTS, "https://www.example.com/doc", now=NOW),
        "http_cannot_set_secure": cookie_header(
            (("__Host-ok=1; Secure; Path=/", "http://www.example.com/"),),
            "https://www.example.com/",
            now=NOW,
        ),
        "localhost_secure": cookie_header(
            (("__Host-local=1; Secure; Path=/", "http://localhost/"),),
            "http://localhost/",
            now=NOW,
        ),
        "single_label_domain": cookie_header(
            (("x=1; Domain=com", "https://example.com/"),),
            "https://example.com/",
            now=NOW,
        ),
    }
    observed["headers"] = headers
    mismatches = [name for name, expected in EXPECTED.items() if headers.get(name) != expected]
    observed["mismatches"] = mismatches
    stdlib = observed["stdlib"]
    observed["stdlib_keeps_evicted"] = "gone=old" in stdlib
    observed["stdlib_keeps_bad_host_prefix"] = "__Host-bad=" in stdlib
    observed["stdlib_keeps_insecure_prefix"] = "__Secure-tok=" in stdlib
    passed = not mismatches
    return passed, observed


def test_cookie_header_matches_the_draft() -> None:
    passed, observed = observe()
    assert passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
