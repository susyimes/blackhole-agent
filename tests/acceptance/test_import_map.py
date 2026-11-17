"""Resolve module specifiers through an import map.

An exact key beats a trailing-slash prefix, and the longer prefix is tried
first. A null address stops the search. A scope without a trailing slash does
not cover its children. A data URL is not rewritten by a prefix. A bare
remainder that climbs out of the mapped address is blocked. A special URL is
normalized before that prefix test, so its own dot segments are not a climb
through the map.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the resolver is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

MAP_BASE = "https://example.com/app/index.html"
SCRIPT = MAP_BASE
VENDOR = "https://example.com/vendor/app.js"
EXACT = "https://example.com/exact"
EXACT_CHILD = "https://example.com/exact/child.js"

IMPORT_MAP = """
{
  "imports": {
    "moment": "/node_modules/moment/src/moment.js",
    "moment/": "/node_modules/moment/src/",
    "foo/": "/lib/foo/",
    "foo/bar/": "/lib/bar/",
    "blocked": null,
    "bare-address": "not-a-url",
    "slash-mismatch/": "/lib",
    "data:text/": "/should-not-apply/",
    "exact-data": "data:text/javascript,1",
    "pkg/file.js": null,
    "pkg/": "/pkg/",
    "https://cdn.example/lib/": "https://example.com/mirror/",
    "git://example.com/lib/": "https://example.com/mirror/",
    "git://user@example.com/lib/": "https://example.com/mirror/"
  },
  "scopes": {
    "/vendor/": {
      "helper": "./vendor-helper.mjs",
      "only-vendor": null,
      "shared": "/from-vendor.js"
    },
    "/": {
      "helper": "/root-helper.mjs",
      "helper2": "/root-helper2.mjs",
      "shared": "/from-root.js",
      "only-vendor": "/from-root.js"
    },
    "https://example.com/exact": {
      "helper": "/exact-helper.mjs"
    }
  },
  "integrity": {
    "/node_modules/moment/src/moment.js": "sha256-abc",
    "./vendor-helper.mjs": "sha256-vendor"
  },
  "ignored": true
}
"""


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.import_map import resolve_module_specifier
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}

    def keep(name: str, specifier: str, base: str = SCRIPT) -> None:
        try:
            result = resolve_module_specifier(
                specifier,
                IMPORT_MAP,
                base,
                map_base_url=MAP_BASE,
            )
            observed[name] = [result["outcome"], result["url"], result["integrity"]]
        except Exception as exc:  # noqa: BLE001 - a raised resolver is an unmet outcome
            observed[name] = f"{type(exc).__name__}: {exc}"

    keep("exact_bare", "moment")
    keep("trailing_prefix", "moment/locale/zh-cn.js")
    keep("longer_prefix", "foo/bar/baz.js")
    keep("shorter_prefix", "foo/baz.js")
    keep("null_address", "blocked")
    keep("bare_address_blocked", "bare-address")
    keep("slash_mismatch_blocked", "slash-mismatch/x.js")
    keep("data_url_not_rewritten", "data:text/javascript,1")
    keep("exact_data_address", "exact-data")
    keep("prefix_climb_blocked", "moment/../secret.js")
    keep("absolute_remainder_blocked", "moment/https://evil.example/x")
    keep("relative_passthrough", "./local.js")
    keep("unmatched_bare", "lodash")
    keep("vendor_scope", "helper", VENDOR)
    keep("scope_falls_through", "helper2", VENDOR)
    keep("root_scope", "helper")
    keep("exact_scope", "helper", EXACT)
    keep("exact_scope_child", "helper", EXACT_CHILD)
    keep("scope_null_blocks", "only-vendor", VENDOR)
    keep("scope_override", "shared", VENDOR)
    keep("scope_root_shared", "shared")
    keep("exact_null_beats_prefix", "pkg/file.js")
    keep("special_url_prefix", "https://cdn.example/lib/a.js")
    keep("normalized_dots_skip_prefix", "https://cdn.example/lib/../secret.js")
    keep("scheme_relative", "//cdn.example/a.js")
    keep("non_special_authority", "git://example.com/lib/a")
    keep("non_special_userinfo", "git://user@example.com/lib/a")
    try:
        invalid = resolve_module_specifier("moment", '{"imports": []}', SCRIPT)
        observed["invalid_imports"] = [invalid["outcome"], invalid["url"], invalid["integrity"]]
    except Exception as exc:  # noqa: BLE001 - a raised parser is an unmet outcome
        observed["invalid_imports"] = f"{type(exc).__name__}: {exc}"

    expected = {
        "exact_bare": ["resolved", "https://example.com/node_modules/moment/src/moment.js", "sha256-abc"],
        "trailing_prefix": ["resolved", "https://example.com/node_modules/moment/src/locale/zh-cn.js", ""],
        "longer_prefix": ["resolved", "https://example.com/lib/bar/baz.js", ""],
        "shorter_prefix": ["resolved", "https://example.com/lib/foo/baz.js", ""],
        "null_address": ["blocked", None, ""],
        "bare_address_blocked": ["blocked", None, ""],
        "slash_mismatch_blocked": ["blocked", None, ""],
        "data_url_not_rewritten": ["resolved", "data:text/javascript,1", ""],
        "exact_data_address": ["resolved", "data:text/javascript,1", ""],
        "prefix_climb_blocked": ["blocked", None, ""],
        "absolute_remainder_blocked": ["blocked", None, ""],
        "relative_passthrough": ["resolved", "https://example.com/app/local.js", ""],
        "unmatched_bare": ["bare", None, ""],
        "vendor_scope": ["resolved", "https://example.com/app/vendor-helper.mjs", "sha256-vendor"],
        "scope_falls_through": ["resolved", "https://example.com/root-helper2.mjs", ""],
        "root_scope": ["resolved", "https://example.com/root-helper.mjs", ""],
        "exact_scope": ["resolved", "https://example.com/exact-helper.mjs", ""],
        "exact_scope_child": ["resolved", "https://example.com/root-helper.mjs", ""],
        "scope_null_blocks": ["blocked", None, ""],
        "scope_override": ["resolved", "https://example.com/from-vendor.js", ""],
        "scope_root_shared": ["resolved", "https://example.com/from-root.js", ""],
        "exact_null_beats_prefix": ["blocked", None, ""],
        "special_url_prefix": ["resolved", "https://example.com/mirror/a.js", ""],
        "normalized_dots_skip_prefix": ["resolved", "https://cdn.example/secret.js", ""],
        "scheme_relative": ["resolved", "https://cdn.example/a.js", ""],
        "non_special_authority": ["resolved", "git://example.com/lib/a", ""],
        "non_special_userinfo": ["resolved", "git://user@example.com/lib/a", ""],
        "invalid_imports": ["invalid", None, ""],
    }
    return observed == expected, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
