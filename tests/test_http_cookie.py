from datetime import datetime, timezone

from blackhole_agent.http_cookie import CookieJar, cookie_header

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
PAGE = "https://www.example.com/docs/secret/page"


def test_max_age_zero_evicts_and_prefixes_are_refused():
    header = cookie_header(
        (
            ("gone=old; Path=/", PAGE),
            ("gone=new; Path=/; Max-Age=0", PAGE),
            ("__Host-bad=1; Domain=example.com; Path=/; Secure", PAGE),
            ("__Secure-tok=s; Path=/", PAGE),
            ("stay=1; Max-Age=60; Expires=Tue, 01 Jan 1980 00:00:00 GMT; Path=/", PAGE),
        ),
        PAGE,
        now=NOW,
    )
    assert header == "stay=1"


def test_host_only_cookie_is_not_sent_to_a_sibling():
    header = cookie_header((("id=1", "https://www.example.com/"),), "https://api.example.com/", now=NOW)
    assert header == ""
    same = cookie_header((("id=1", "https://www.example.com/"),), "https://www.example.com/app", now=NOW)
    assert same == "id=1"


def test_replacement_keeps_creation_order():
    jar = CookieJar()
    jar.store("a=1; Path=/", "https://example.com/", NOW)
    jar.store("b=1; Path=/", "https://example.com/", NOW)
    jar.store("a=2; Path=/", "https://example.com/", NOW)
    assert jar.header("https://example.com/", NOW) == "a=2; b=1"
