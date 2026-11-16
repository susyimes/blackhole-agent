"""Cross-origin isolation, popup severance, and no-cors embed permission.

A secure document is same-origin-plus-COEP only for an enforcing same-origin
opener policy plus require-corp or credentialless. Report-only headers, a
non-secure origin, an unknown token, and same-origin-allow-popups do not
isolate. A popup severs when policies disagree and keeps an unsafe-none
popup opened by same-origin-allow-popups. A later navigation does not keep
that exception. require-corp blocks a cross-origin no-cors response with no
Cross-Origin-Resource-Policy; credentialless allows it until credentials are
included. same-site allows an https initiator to use an http response and
rejects the opposite direction.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the decision is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

APP = "https://app.example/index.html"
APP_OTHER_PATH = "https://app.example/next.html"
OTHER = "https://other.example/"
INSECURE = "http://app.example/"
LOCAL = "http://localhost/"
LOOPBACK = "http://127.0.0.1/"
WWW = "https://www.example.com/"
STATIC_HTTPS = "https://static.example.com/app.js"
STATIC_HTTP = "http://static.example.com/app.js"
WWW_HTTP = "http://www.example.com/"
CDN = "https://cdn.example/lib.js"

SAME = {"Cross-Origin-Opener-Policy": "same-origin"}
ALLOW = {"Cross-Origin-Opener-Policy": "same-origin-allow-popups"}
NOOPEN = {"Cross-Origin-Opener-Policy": "noopener-allow-popups"}
REQUIRE = {"Cross-Origin-Embedder-Policy": "require-corp"}
CREDENTIALLESS = {"Cross-Origin-Embedder-Policy": "credentialless"}
PLUS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
}
PLUS_PARAMETERS = {
    "Cross-Origin-Opener-Policy": 'same-origin; report-to="endpoint"',
    "Cross-Origin-Embedder-Policy": 'credentialless; report-to="endpoint"',
}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.cross_origin_isolation import (
            embed_allowed,
            navigation_switch,
            opener_policy,
            popup_switch,
        )
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}

    def keep(name: str, action) -> None:
        try:
            observed[name] = action()
        except Exception as exc:  # noqa: BLE001 - a rejected input is an unmet outcome
            observed[name] = f"{type(exc).__name__}: {exc}"

    keep("plus_require_corp", lambda: opener_policy(APP, PLUS))
    keep(
        "plus_credentialless",
        lambda: opener_policy(APP, {**SAME, **CREDENTIALLESS}),
    )
    keep("plus_with_parameters", lambda: opener_policy(APP, PLUS_PARAMETERS))
    keep("same_origin_without_embedder", lambda: opener_policy(APP, SAME))
    keep("allow_popups_with_embedder", lambda: opener_policy(APP, {**ALLOW, **REQUIRE}))
    keep("explicit_unsafe_none", lambda: opener_policy(APP, {"Cross-Origin-Opener-Policy": "unsafe-none", **REQUIRE}))
    keep("insecure_http", lambda: opener_policy(INSECURE, PLUS))
    keep("localhost_isolates", lambda: opener_policy(LOCAL, PLUS))
    keep("loopback_isolates", lambda: opener_policy(LOOPBACK, PLUS))
    keep(
        "report_only",
        lambda: opener_policy(
            APP,
            {
                "Cross-Origin-Opener-Policy-Report-Only": "same-origin",
                "Cross-Origin-Embedder-Policy-Report-Only": "require-corp",
            },
        ),
    )
    keep("unknown_token", lambda: opener_policy(APP, {"Cross-Origin-Opener-Policy": "mystery", **REQUIRE}))
    keep("token_case", lambda: opener_policy(APP, {"Cross-Origin-Opener-Policy": "Same-Origin", **REQUIRE}))
    keep(
        "coep_case",
        lambda: opener_policy(APP, {**SAME, "Cross-Origin-Embedder-Policy": "Require-Corp"}),
    )
    keep(
        "duplicate_embedder",
        lambda: opener_policy(APP, {**SAME, "Cross-Origin-Embedder-Policy": "require-corp, require-corp"}),
    )
    keep("popup_cross_origin", lambda: popup_switch(APP, SAME, OTHER, None))
    keep("popup_allow_popups", lambda: popup_switch(APP, ALLOW, OTHER, None))
    keep("popup_noopener", lambda: popup_switch(APP, ALLOW, OTHER, NOOPEN))
    keep("popup_same_documents", lambda: popup_switch(APP, SAME, APP_OTHER_PATH, SAME))
    keep("popup_policy_disagreement", lambda: popup_switch(APP, PLUS, APP_OTHER_PATH, SAME))
    keep("popup_both_isolated", lambda: popup_switch(APP, PLUS, APP_OTHER_PATH, PLUS))
    keep("popup_two_unsafe", lambda: popup_switch(APP, None, OTHER, None))
    keep("navigation_allow_popups_cross", lambda: navigation_switch(APP, ALLOW, OTHER, None))
    keep("navigation_same_policy", lambda: navigation_switch(APP, ALLOW, APP_OTHER_PATH, ALLOW))
    keep(
        "embed_require_missing",
        lambda: embed_allowed(APP, REQUIRE, CDN, None),
    )
    keep(
        "embed_credentialless_missing",
        lambda: embed_allowed(APP, CREDENTIALLESS, CDN, None),
    )
    keep(
        "embed_credentialless_with_credentials",
        lambda: embed_allowed(APP, CREDENTIALLESS, CDN, None, credentials=True),
    )
    keep(
        "embed_credentialless_navigation",
        lambda: embed_allowed(APP, CREDENTIALLESS, CDN, None, for_navigation=True),
    )
    keep(
        "embed_cross_origin_header",
        lambda: embed_allowed(APP, REQUIRE, CDN, {"Cross-Origin-Resource-Policy": "cross-origin"}),
    )
    keep(
        "embed_same_origin_header",
        lambda: embed_allowed(APP, REQUIRE, CDN, {"Cross-Origin-Resource-Policy": "same-origin"}),
    )
    keep(
        "embed_same_origin_resource",
        lambda: embed_allowed(APP, REQUIRE, APP_OTHER_PATH, None),
    )
    keep(
        "embed_same_site",
        lambda: embed_allowed(WWW, REQUIRE, STATIC_HTTPS, {"Cross-Origin-Resource-Policy": "same-site"}),
    )
    keep(
        "embed_https_initiator_http_resource",
        lambda: embed_allowed(WWW, REQUIRE, STATIC_HTTP, {"Cross-Origin-Resource-Policy": "same-site"}),
    )
    keep(
        "embed_http_initiator_https_resource",
        lambda: embed_allowed(WWW_HTTP, None, STATIC_HTTPS, {"Cross-Origin-Resource-Policy": "same-site"}),
    )
    expected = {
        "plus_require_corp": "same-origin-plus-COEP",
        "plus_credentialless": "same-origin-plus-COEP",
        "plus_with_parameters": "same-origin-plus-COEP",
        "same_origin_without_embedder": "same-origin",
        "allow_popups_with_embedder": "same-origin-allow-popups",
        "explicit_unsafe_none": "unsafe-none",
        "insecure_http": "unsafe-none",
        "localhost_isolates": "same-origin-plus-COEP",
        "loopback_isolates": "same-origin-plus-COEP",
        "report_only": "unsafe-none",
        "unknown_token": "unsafe-none",
        "token_case": "unsafe-none",
        "coep_case": "same-origin",
        "duplicate_embedder": "same-origin",
        "popup_cross_origin": True,
        "popup_allow_popups": False,
        "popup_noopener": True,
        "popup_same_documents": False,
        "popup_policy_disagreement": True,
        "popup_both_isolated": False,
        "popup_two_unsafe": False,
        "navigation_allow_popups_cross": True,
        "navigation_same_policy": False,
        "embed_require_missing": False,
        "embed_credentialless_missing": True,
        "embed_credentialless_with_credentials": False,
        "embed_credentialless_navigation": False,
        "embed_cross_origin_header": True,
        "embed_same_origin_header": False,
        "embed_same_origin_resource": True,
        "embed_same_site": True,
        "embed_https_initiator_http_resource": True,
        "embed_http_initiator_https_resource": False,
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
