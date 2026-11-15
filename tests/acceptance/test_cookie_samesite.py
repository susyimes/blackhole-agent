"""SameSite cookies follow schemeful sites, not the host string alone.

A Lax cookie is withheld from a cross-site image request and sent on a
cross-site top-level GET. An explicit Lax cookie stays off a cross-site
top-level POST. A cookie with no SameSite attribute still rides that POST
for two minutes. SameSite=None without Secure is discarded. co.uk hosts
share a registrable domain, github.io neighbors do not, and http is not
the same site as https.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A jar without SameSite is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
HOME = "https://www.example.com/"
EVIL = "https://evil.test/"


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.http_cookie import CookieJar, cookie_header, same_site
    except Exception as exc:  # noqa: BLE001 - baseline without SameSite still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    def send(line: str, request: str, source: str, **kwargs: object) -> str:
        return cookie_header(
            ((line, HOME),),
            request,
            now=NOW,
            source_url=source,
            **kwargs,
        )

    try:
        sites = {
            "co_uk": same_site("https://a.example.co.uk/", "https://b.example.co.uk/"),
            "evil_co_uk": same_site("https://evil.co.uk/", "https://example.co.uk/"),
            "github_io": same_site("https://foo.github.io/", "https://bar.github.io/"),
            "museum_split": same_site(
                "https://r.wildlife.museum/", "https://other.wildlife.museum/"
            ),
            "museum_child": same_site(
                "https://r.wildlife.museum/", "https://sub.r.wildlife.museum/"
            ),
            "schemes": same_site("http://example.com/", "https://example.com/"),
            "ck_exception": same_site("https://www.ck/", "https://www.ck/path"),
            "ck_wildcard": same_site("https://bar.foo.ck/", "https://other.foo.ck/"),
        }
        headers = {
            "lax_image": send("id=1; SameSite=Lax", HOME, EVIL, top_level=False),
            "lax_get": send("id=1; SameSite=Lax", HOME, EVIL, method="GET", top_level=True),
            "lax_post": send("id=1; SameSite=Lax", HOME, EVIL, method="POST", top_level=True),
            "strict_get": send(
                "id=1; SameSite=Strict", HOME, EVIL, method="GET", top_level=True
            ),
            "same_site": send(
                "id=1; Domain=example.com; SameSite=Lax",
                "https://app.example.com/",
                "https://www.example.com/docs",
            ),
            "none_plain": send("id=1; SameSite=None", HOME, EVIL, top_level=False),
            "none_secure": send(
                "id=1; SameSite=None; Secure", HOME, EVIL, top_level=False
            ),
            "schemeful": send(
                "id=1; SameSite=Lax; Secure",
                HOME,
                "http://www.example.com/",
                top_level=False,
            ),
            "last_lax": send(
                "id=1; SameSite=None; Secure; SameSite=Lax", HOME, EVIL, top_level=False
            ),
            "last_bogus_get": send(
                "id=1; SameSite=Lax; SameSite=Bogus", HOME, EVIL, method="GET", top_level=True
            ),
            "last_bogus_same": send(
                "id=1; SameSite=Lax; SameSite=Bogus", HOME, HOME, method="GET", top_level=False
            ),
        }
        jar = CookieJar()
        jar.store("d=1", HOME, NOW)
        headers["default_post_120"] = jar.header(
            HOME,
            NOW + timedelta(seconds=120),
            source_url=EVIL,
            method="POST",
            top_level=True,
        )
        headers["default_post_121"] = jar.header(
            HOME,
            NOW + timedelta(seconds=121),
            source_url=EVIL,
            method="POST",
            top_level=True,
        )
        blocked = CookieJar()
        blocked_status = blocked.store(
            "id=1; SameSite=Lax",
            HOME,
            NOW,
            source_url=EVIL,
            top_level=False,
        )
        headers["set_cross_image"] = blocked.header(HOME, NOW, source_url=HOME)
        allowed = CookieJar()
        allowed_status = allowed.store(
            "id=1; SameSite=Lax",
            HOME,
            NOW,
            source_url=EVIL,
            top_level=True,
        )
        headers["set_cross_navigation"] = allowed.header(HOME, NOW, source_url=HOME)
        headers["co_uk"] = cookie_header(
            (("id=1; Domain=example.co.uk; SameSite=Lax", "https://a.example.co.uk/"),),
            "https://b.example.co.uk/",
            now=NOW,
            source_url="https://a.example.co.uk/",
        )
        headers["github_io"] = cookie_header(
            (("id=1; SameSite=Lax", "https://foo.github.io/"),),
            "https://foo.github.io/",
            now=NOW,
            source_url="https://bar.github.io/",
        )
    except Exception as exc:  # noqa: BLE001 - a jar that rejects the new arguments is a miss
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    expected_sites = {
        "co_uk": True,
        "evil_co_uk": False,
        "github_io": False,
        "museum_split": False,
        "museum_child": True,
        "schemes": False,
        "ck_exception": True,
        "ck_wildcard": False,
    }
    expected_headers = {
        "lax_image": "",
        "lax_get": "id=1",
        "lax_post": "",
        "strict_get": "",
        "same_site": "id=1",
        "none_plain": "",
        "none_secure": "id=1",
        "schemeful": "",
        "last_lax": "",
        "last_bogus_get": "",
        "last_bogus_same": "id=1",
        "default_post_120": "d=1",
        "default_post_121": "",
        "set_cross_image": "",
        "set_cross_navigation": "id=1",
        "co_uk": "id=1",
        "github_io": "",
    }
    observed: dict[str, object] = {
        "sites": sites,
        "headers": headers,
        "set_cross_image_status": blocked_status,
        "set_cross_navigation_status": allowed_status,
    }
    mismatches = [name for name, expected in expected_sites.items() if sites.get(name) is not expected]
    mismatches += [
        name for name, expected in expected_headers.items() if headers.get(name) != expected
    ]
    if blocked_status != "ignored":
        mismatches.append("set_cross_image_status")
    if allowed_status != "stored":
        mismatches.append("set_cross_navigation_status")
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
