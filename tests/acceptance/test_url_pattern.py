"""Match URLs with the URL Pattern syntax.

A named pathname group stops at a slash and an optional group keeps that
slash. A named hostname group stops at a dot. A star crosses slashes. A
relative pattern resolves dot segments against its base. An omitted port is
the default port, and a hash with no search requires an empty search.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the matcher still exits 0.
"""

from __future__ import annotations

import json


def _groups(result: object, component: str) -> dict[str, str] | None:
    if not isinstance(result, dict):
        return None
    record = result.get(component)
    if not isinstance(record, dict):
        return None
    groups = record.get("groups")
    if not isinstance(groups, dict):
        return None
    return {str(key): value for key, value in groups.items() if isinstance(value, str)}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.url_pattern import URLPattern, URLPatternError
    except Exception as exc:  # noqa: BLE001 - baseline without the matcher still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, pattern: object, url: str, base: str | None = None) -> object:
        try:
            if not hasattr(pattern, "exec"):
                result: object = {"error": "not a pattern"}
            else:
                result = pattern.exec(url, base)
        except Exception as exc:  # noqa: BLE001 - a raised match is an unmet outcome
            result = {"error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result

    category = URLPattern("https://example.com/:category/*")
    observed["category_pattern"] = {
        "protocol": category.protocol,
        "username": category.username,
        "port": category.port,
        "pathname": category.pathname,
        "search": category.search,
        "hash": category.hash,
        "has_regexp_groups": category.has_regexp_groups,
    }
    checks.append(
        category.protocol == "https"
        and category.username == "*"
        and category.port == ""
        and category.pathname == "/:category/*"
        and category.search == "*"
        and category.hash == "*"
        and category.has_regexp_groups is False
    )
    blog = keep("blog", category, "https://example.com/blog/our-greatest-product-ever")
    checks.append(_groups(blog, "pathname") == {"category": "blog", "0": "our-greatest-product-ever"})
    products = keep("products", category, "https://example.com/products/")
    checks.append(_groups(products, "pathname") == {"category": "products", "0": ""})
    checks.append(keep("origin_root", category, "https://example.com/") is None)
    checks.append(keep("http_scheme", category, "http://example.com/products/") is None)
    checks.append(
        keep("explicit_port", category, "https://example.com:8443/blog/our-greatest-product-ever") is None
    )

    shop = URLPattern("http{s}?://{:subdomain.}?shop.example/products/:id([0-9]+)#reviews")
    observed["shop_pattern"] = {
        "protocol": shop.protocol,
        "hostname": shop.hostname,
        "port": shop.port,
        "pathname": shop.pathname,
        "search": shop.search,
        "hash": shop.hash,
        "has_regexp_groups": shop.has_regexp_groups,
    }
    checks.append(
        shop.protocol == "http{s}?"
        and shop.hostname == "{:subdomain.}?shop.example"
        and shop.port == ""
        and shop.pathname == "/products/:id([0-9]+)"
        and shop.search == ""
        and shop.hash == "reviews"
        and shop.has_regexp_groups is True
    )
    plain = keep("shop_plain", shop, "https://shop.example/products/74205#reviews")
    checks.append(_groups(plain, "pathname") == {"id": "74205"} and _groups(plain, "hostname") == {})
    voyager = keep("shop_user", shop, "https://kathryn@voyager.shop.example/products/74656#reviews")
    checks.append(
        _groups(voyager, "hostname") == {"subdomain": "voyager"} and _groups(voyager, "pathname") == {"id": "74656"}
    )
    insecure = keep("shop_http", shop, "http://insecure.shop.example/products/1701#reviews")
    checks.append(
        _groups(insecure, "hostname") == {"subdomain": "insecure"}
        and _groups(insecure, "pathname") == {"id": "1701"}
    )
    checks.append(keep("shop_no_hash", shop, "https://shop.example/products/2000") is None)
    checks.append(keep("shop_port", shop, "http://shop.example:8080/products/0#reviews") is None)
    checks.append(keep("shop_search", shop, "https://nx.shop.example/products/01?speed=5#reviews") is None)
    checks.append(keep("shop_text", shop, "https://shop.example/products/chair#reviews") is None)

    admin = URLPattern("../admin/*", "https://discussion.example/forum/?page=2")
    observed["admin_pattern"] = {
        "protocol": admin.protocol,
        "hostname": admin.hostname,
        "port": admin.port,
        "pathname": admin.pathname,
        "search": admin.search,
        "hash": admin.hash,
    }
    checks.append(
        admin.protocol == "https"
        and admin.hostname == "discussion.example"
        and admin.port == ""
        and admin.pathname == "/admin/*"
        and admin.search == "*"
        and admin.hash == "*"
    )
    updated = keep("admin_update", admin, "https://edd:librarian@discussion.example/admin/update?id=1")
    checks.append(_groups(updated, "pathname") == {"0": "update"})
    checks.append(keep("admin_root", admin, "https://discussion.example/admin/") is not None)
    checks.append(keep("admin_forum", admin, "https://discussion.example/forum/admin/") is None)
    checks.append(keep("admin_other_port", admin, "http://discussion.example:8080/admin/update?id=1") is None)

    optional = URLPattern({"pathname": "/products/:id?"})
    checks.append(optional.pathname == "/products/:id?" and optional.port == "*")
    bare = keep("optional_bare", optional, "https://example.com/products")
    checks.append(bare is not None and _groups(bare, "pathname") == {})
    numbered = keep("optional_id", optional, "https://example.com/products/2")
    checks.append(_groups(numbered, "pathname") == {"id": "2"})
    checks.append(keep("optional_slash", optional, "https://example.com/products/") is None)
    checks.append(keep("optional_extra", optional, "https://example.com/products/2/extra") is None)

    host = URLPattern({"hostname": ":name.example.com"})
    one = keep("host_one", host, "https://a.example.com/")
    checks.append(host.hostname == ":name.example.com" and _groups(one, "hostname") == {"name": "a"})
    checks.append(keep("host_two", host, "https://a.b.example.com/") is None)
    checks.append(keep("host_apex", host, "https://example.com/") is None)

    folded = URLPattern("https://example.com/Foo", ignore_case=True)
    sensitive = URLPattern("https://example.com/Foo")
    observed["case_pathname"] = folded.pathname
    checks.append(folded.pathname == "/Foo" and folded.test("https://example.com/foo") is True)
    checks.append(sensitive.test("https://example.com/foo") is False)
    checks.append(sensitive.test("https://example.com/Foo") is True)

    try:
        URLPattern({"pathname": "/:id/:id"})
        observed["duplicate"] = "accepted"
        checks.append(False)
    except URLPatternError:
        observed["duplicate"] = "rejected"
        checks.append(True)

    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
