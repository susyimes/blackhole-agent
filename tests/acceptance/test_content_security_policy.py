"""A Content-Security-Policy allows or blocks a request by its operative directive.

script-src replaces default-src for scripts and does not police images.
A host source does not match a longer suffix. strict-dynamic blocks a
parser-inserted script that only matches a host. An http host source allows
the https upgrade on the default port and an explicit port 80 does not match
https. self on an http origin allows the https same-host upgrade and does
not allow a blob URL.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the policy check is an unmet outcome, not
a crash.
"""

from __future__ import annotations

import json

PAGE = "https://page.example"
HTTP_PAGE = "http://page.example"


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.content_security import request_allowed
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "suffix_host": (
            {
                "policies": "script-src https://example.com",
                "destination": "script",
                "url": "https://example.com.evil/a.js",
                "origin": PAGE,
            },
            False,
            "script-src",
        ),
        "apex_not_wildcard": (
            {
                "policies": "script-src *.example.com",
                "destination": "script",
                "url": "https://example.com/a.js",
                "origin": PAGE,
            },
            False,
            "script-src",
        ),
        "nested_wildcard": (
            {
                "policies": "script-src *.example.com",
                "destination": "script",
                "url": "https://a.b.example.com/a.js",
                "origin": PAGE,
            },
            True,
            "script-src",
        ),
        "script_replaces_default": (
            {
                "policies": "default-src 'self'; script-src https://cdn.example",
                "destination": "script",
                "url": "https://page.example/a.js",
                "origin": PAGE,
            },
            False,
            "script-src",
        ),
        "script_uses_script_src": (
            {
                "policies": "default-src 'self'; script-src https://cdn.example",
                "destination": "script",
                "url": "https://cdn.example/a.js",
                "origin": PAGE,
            },
            True,
            "script-src",
        ),
        "image_uses_default": (
            {
                "policies": "default-src 'self'; script-src https://cdn.example",
                "destination": "image",
                "url": "https://cdn.example/a.png",
                "origin": PAGE,
            },
            False,
            "default-src",
        ),
        "image_self": (
            {
                "policies": "default-src 'self'; script-src https://cdn.example",
                "destination": "image",
                "url": "https://page.example/a.png",
                "origin": PAGE,
            },
            True,
            "default-src",
        ),
        "script_ignores_images": (
            {
                "policies": "script-src 'none'",
                "destination": "image",
                "url": "https://evil.example/a.png",
                "origin": PAGE,
            },
            True,
            "",
        ),
        "exact_path": (
            {
                "policies": "script-src https://cdn.example/app.js",
                "destination": "script",
                "url": "https://cdn.example/app.js",
                "origin": PAGE,
            },
            True,
            "script-src",
        ),
        "path_prefix_miss": (
            {
                "policies": "script-src https://cdn.example/js/",
                "destination": "script",
                "url": "https://cdn.example/js-evil/app.js",
                "origin": PAGE,
            },
            False,
            "script-src",
        ),
        "path_prefix_hit": (
            {
                "policies": "script-src https://cdn.example/js/",
                "destination": "script",
                "url": "https://cdn.example/js/app.js",
                "origin": PAGE,
            },
            True,
            "script-src",
        ),
        "redirect_drops_path": (
            {
                "policies": "script-src https://cdn.example/app.js",
                "destination": "script",
                "url": "https://cdn.example/other.js",
                "origin": PAGE,
                "redirect_count": 1,
            },
            True,
            "script-src",
        ),
        "http_upgrades_https": (
            {
                "policies": "script-src http://cdn.example",
                "destination": "script",
                "url": "https://cdn.example/a.js",
                "origin": PAGE,
            },
            True,
            "script-src",
        ),
        "https_blocks_http": (
            {
                "policies": "script-src https://cdn.example",
                "destination": "script",
                "url": "http://cdn.example/a.js",
                "origin": PAGE,
            },
            False,
            "script-src",
        ),
        "explicit_80_blocks_https": (
            {
                "policies": "script-src http://cdn.example:80",
                "destination": "script",
                "url": "https://cdn.example/a.js",
                "origin": PAGE,
            },
            False,
            "script-src",
        ),
        "explicit_80_allows_http": (
            {
                "policies": "script-src http://cdn.example:80",
                "destination": "script",
                "url": "http://cdn.example/a.js",
                "origin": PAGE,
            },
            True,
            "script-src",
        ),
        "self_https_upgrade": (
            {
                "policies": "script-src 'self'",
                "destination": "script",
                "url": "https://page.example/a.js",
                "origin": HTTP_PAGE,
            },
            True,
            "script-src",
        ),
        "self_blocks_blob": (
            {
                "policies": "script-src 'self'",
                "destination": "script",
                "url": "blob:http://page.example/uuid",
                "origin": HTTP_PAGE,
            },
            False,
            "script-src",
        ),
        "self_blocks_other_port": (
            {
                "policies": "script-src 'self'",
                "destination": "script",
                "url": "https://page.example:8443/a.js",
                "origin": HTTP_PAGE,
            },
            False,
            "script-src",
        ),
        "star_allows_https": (
            {"policies": "script-src *", "destination": "script", "url": "https://evil.example/a.js", "origin": PAGE},
            True,
            "script-src",
        ),
        "star_blocks_data": (
            {"policies": "script-src *", "destination": "script", "url": "data:text/plain,hi", "origin": PAGE},
            False,
            "script-src",
        ),
        "star_allows_ip": (
            {"policies": "script-src *", "destination": "script", "url": "https://127.0.0.1/a.js", "origin": PAGE},
            True,
            "script-src",
        ),
        "host_star_blocks_ip": (
            {
                "policies": "script-src https://*",
                "destination": "script",
                "url": "https://127.0.0.1/a.js",
                "origin": PAGE,
            },
            False,
            "script-src",
        ),
        "ip_host_blocks_itself": (
            {
                "policies": "script-src 127.0.0.1",
                "destination": "script",
                "url": "https://127.0.0.1/a.js",
                "origin": "https://127.0.0.1",
            },
            False,
            "script-src",
        ),
        "self_allows_ip": (
            {
                "policies": "script-src 'self'",
                "destination": "script",
                "url": "https://127.0.0.1/a.js",
                "origin": "https://127.0.0.1",
            },
            True,
            "script-src",
        ),
        "strict_dynamic_blocks_parser": (
            {
                "policies": "script-src 'strict-dynamic' https://cdn.example",
                "destination": "script",
                "url": "https://cdn.example/a.js",
                "origin": PAGE,
                "parser_metadata": "parser-inserted",
            },
            False,
            "script-src",
        ),
        "strict_dynamic_allows_inserted": (
            {
                "policies": "script-src 'strict-dynamic' https://cdn.example",
                "destination": "script",
                "url": "https://evil.example/a.js",
                "origin": PAGE,
                "parser_metadata": "not-parser-inserted",
            },
            True,
            "script-src",
        ),
        "nonce_beats_strict_dynamic": (
            {
                "policies": "script-src 'strict-dynamic' 'nonce-Abc'",
                "destination": "script",
                "url": "https://evil.example/a.js",
                "origin": PAGE,
                "nonce": "Abc",
                "parser_metadata": "parser-inserted",
            },
            True,
            "script-src",
        ),
        "nonce_is_case_sensitive": (
            {
                "policies": "script-src 'nonce-Abc'",
                "destination": "script",
                "url": "https://cdn.example/a.js",
                "origin": PAGE,
                "nonce": "abc",
                "parser_metadata": "parser-inserted",
            },
            False,
            "script-src",
        ),
        "none_with_host": (
            {
                "policies": "script-src 'none' https://cdn.example",
                "destination": "script",
                "url": "https://cdn.example/a.js",
                "origin": PAGE,
            },
            True,
            "script-src",
        ),
        "none_alone": (
            {
                "policies": "script-src 'none'",
                "destination": "script",
                "url": "https://page.example/a.js",
                "origin": PAGE,
            },
            False,
            "script-src",
        ),
        "comma_is_second_policy": (
            {
                "policies": "script-src 'self', default-src 'none'",
                "destination": "script",
                "url": "https://page.example/a.js",
                "origin": PAGE,
            },
            False,
            "default-src",
        ),
        "semicolon_keeps_script": (
            {
                "policies": "script-src 'self'; default-src 'none'",
                "destination": "script",
                "url": "https://page.example/a.js",
                "origin": PAGE,
            },
            True,
            "script-src",
        ),
        "first_directive_wins": (
            {
                "policies": "script-src https://cdn.example/app.js; script-src 'none'",
                "destination": "script",
                "url": "https://cdn.example/app.js",
                "origin": PAGE,
            },
            True,
            "script-src",
        ),
        "worker_script_src_none": (
            {
                "policies": "script-src 'none'",
                "destination": "worker",
                "url": "https://cdn.example/sw.js",
                "origin": PAGE,
            },
            False,
            "script-src",
        ),
        "child_src_before_script": (
            {
                "policies": "child-src https://cdn.example; script-src 'none'",
                "destination": "worker",
                "url": "https://cdn.example/sw.js",
                "origin": PAGE,
            },
            True,
            "child-src",
        ),
        "ws_allows_https": (
            {"policies": "connect-src ws:", "destination": "json", "url": "https://example.com/socket", "origin": PAGE},
            True,
            "connect-src",
        ),
        "ws_blocks_ftp": (
            {"policies": "connect-src ws:", "destination": "json", "url": "ftp://example.com/file", "origin": PAGE},
            False,
            "connect-src",
        ),
        "prefetch_default_blocks": (
            {
                "policies": "default-src *",
                "destination": "image",
                "url": "https://cdn.example/a.png",
                "origin": PAGE,
                "initiator": "prefetch",
            },
            False,
            "default-src",
        ),
        "prefetch_img_allows": (
            {
                "policies": "img-src https://cdn.example",
                "destination": "image",
                "url": "https://cdn.example/a.png",
                "origin": PAGE,
                "initiator": "prefetch",
            },
            True,
            "",
        ),
        "prefetch_without_default_allows": (
            {
                "policies": "img-src https://cdn.example",
                "destination": "image",
                "url": "https://evil.example/a.png",
                "origin": PAGE,
                "initiator": "prefetch",
            },
            True,
            "",
        ),
        "opaque_schemeless_blocks": (
            {
                "policies": "script-src example.com",
                "destination": "script",
                "url": "https://example.com/a.js",
                "origin": "null",
            },
            False,
            "script-src",
        ),
        "opaque_explicit_scheme_allows": (
            {
                "policies": "script-src https://example.com",
                "destination": "script",
                "url": "https://example.com/a.js",
                "origin": "null",
            },
            True,
            "script-src",
        ),
    }
    observed: dict[str, object] = {}
    mismatches: list[str] = []
    for name, (kwargs, allowed, checked) in cases.items():
        try:
            seen = request_allowed(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised check is an unmet outcome
            observed[name] = {"error": f"{type(exc).__name__}: {exc}"}
            mismatches.append(name)
            continue
        observed[name] = {"allowed": seen["allowed"], "checked": seen["checked"], "reason": seen["reason"]}
        if seen["allowed"] is not allowed or seen["checked"] != checked:
            mismatches.append(name)
    return not mismatches, {"cases": observed, "mismatches": mismatches}


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
