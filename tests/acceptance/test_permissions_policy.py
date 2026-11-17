"""Permissions Policy allowlists, iframe delegation, and default features.

An empty header list disables a feature for the document itself. A host
wildcard matches a subdomain and not the apex. A port wildcard matches
another port of that host and not a different host. A cross-origin iframe
receives geolocation only when the parent allowlist already matches it and
the allow attribute delegates it. sync-xhr is delegated without allow.
A child header cannot restore a feature the parent disabled.
allowfullscreen grants fullscreen to a child origin that an explicit allow
list does not name. An unrecognized feature stays disabled.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the decision is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

APP = "https://app.example/index.html"
GEO = "https://geo.example.com/map"
APEX = "https://example.com/"
OTHER = "https://other.example/map"
PORT = "https://example.com:444/"
OTHER_PORT = "https://other.example:444/"
EVIL = "https://evil.example/"
MAPS = "https://maps.example/"


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.permissions_policy import feature_enabled
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}

    def keep(name: str, action) -> None:
        try:
            observed[name] = action()
        except Exception as exc:  # noqa: BLE001 - a rejected input is an unmet outcome
            observed[name] = f"{type(exc).__name__}: {exc}"

    def enabled(*args, **kwargs) -> bool:
        result = feature_enabled(*args, **kwargs)
        if not isinstance(result, dict) or "enabled" not in result:
            raise TypeError("feature decision is missing")
        return bool(result["enabled"])

    keep("empty_disables_self", lambda: enabled("geolocation", APP, "geolocation=()"))
    keep("default_self_enabled", lambda: enabled("geolocation", APP))
    keep(
        "wildcard_subdomain",
        lambda: enabled(
            "geolocation",
            APP,
            'geolocation=(self "https://*.example.com")',
            for_origin=GEO,
        ),
    )
    keep(
        "wildcard_not_apex",
        lambda: enabled(
            "geolocation",
            APP,
            'geolocation=(self "https://*.example.com")',
            for_origin=APEX,
        ),
    )
    keep(
        "port_wildcard",
        lambda: enabled(
            "geolocation",
            APP,
            'geolocation=(self "https://example.com:*")',
            for_origin=PORT,
        ),
    )
    keep(
        "port_wildcard_other_host",
        lambda: enabled(
            "geolocation",
            APP,
            'geolocation=(self "https://example.com:*")',
            for_origin=OTHER_PORT,
        ),
    )
    keep(
        "https_expression_rejects_http",
        lambda: enabled("camera", APP, 'camera=("https://example.com")', for_origin="http://example.com/"),
    )
    keep(
        "http_expression_allows_https",
        lambda: enabled("camera", APP, 'camera=("http://example.com")', for_origin="https://example.com/"),
    )
    keep(
        "cross_origin_default_self",
        lambda: enabled("geolocation", OTHER, parent_document=APP),
    )
    keep(
        "same_origin_default_self",
        lambda: enabled("geolocation", "https://app.example/nested", parent_document=APP),
    )
    keep(
        "allow_without_parent_match",
        lambda: enabled(
            "geolocation",
            OTHER,
            parent_document=APP,
            parent_header="geolocation=(self)",
            allow="geolocation",
            src=OTHER,
        ),
    )
    keep(
        "allow_when_parent_lists_child",
        lambda: enabled(
            "geolocation",
            OTHER,
            parent_document=APP,
            parent_header='geolocation=(self "https://other.example")',
            allow="geolocation",
            src=OTHER,
        ),
    )
    keep(
        "star_header_still_needs_allow",
        lambda: enabled(
            "geolocation",
            OTHER,
            parent_document=APP,
            parent_header="geolocation=*",
        ),
    )
    keep(
        "sync_xhr_cross_origin",
        lambda: enabled("sync-xhr", OTHER, parent_document=APP),
    )
    keep(
        "sync_xhr_none_overrides_default",
        lambda: enabled("sync-xhr", OTHER, parent_document=APP, allow="sync-xhr 'none'", src=OTHER),
    )
    keep(
        "child_cannot_restore",
        lambda: enabled(
            "geolocation",
            APP,
            "geolocation=*",
            parent_document=APP,
            parent_header="geolocation=()",
            allow="geolocation",
            src=APP,
        ),
    )
    keep(
        "parent_without_self_blocks_delegate",
        lambda: enabled(
            "geolocation",
            OTHER,
            parent_document=APP,
            parent_header='geolocation=("https://other.example")',
            allow="geolocation",
            src=OTHER,
        ),
    )
    keep(
        "allowfullscreen_other_navigation",
        lambda: enabled(
            "fullscreen",
            EVIL,
            parent_document=APP,
            src=MAPS,
            allowfullscreen=True,
        ),
    )
    keep(
        "allow_src_rejects_other_navigation",
        lambda: enabled(
            "fullscreen",
            EVIL,
            parent_document=APP,
            src=MAPS,
            allow="fullscreen",
        ),
    )
    keep(
        "allow_port_wildcard_rejected",
        lambda: enabled(
            "geolocation",
            PORT,
            parent_document=APP,
            parent_header="geolocation=*",
            allow="geolocation https://example.com:*",
            src=PORT,
        ),
    )
    keep("unknown_feature", lambda: enabled("midi", APP))
    keep(
        "malformed_header_keeps_default",
        lambda: enabled("geolocation", APP, "Geolocation=()"),
    )
    keep(
        "report_to_still_disabled",
        lambda: (
            enabled("geolocation", APP, "geolocation=();report-to=endpoint"),
            feature_enabled("geolocation", APP, "geolocation=();report-to=endpoint").get("report_to"),
        ),
    )
    keep(
        "first_allow_entry_wins",
        lambda: enabled(
            "geolocation",
            OTHER,
            parent_document=APP,
            parent_header="geolocation=*",
            allow="geolocation 'none'; geolocation *",
            src=OTHER,
        ),
    )

    expected = {
        "empty_disables_self": False,
        "default_self_enabled": True,
        "wildcard_subdomain": True,
        "wildcard_not_apex": False,
        "port_wildcard": True,
        "port_wildcard_other_host": False,
        "https_expression_rejects_http": False,
        "http_expression_allows_https": True,
        "cross_origin_default_self": False,
        "same_origin_default_self": True,
        "allow_without_parent_match": False,
        "allow_when_parent_lists_child": True,
        "star_header_still_needs_allow": False,
        "sync_xhr_cross_origin": True,
        "sync_xhr_none_overrides_default": False,
        "child_cannot_restore": False,
        "parent_without_self_blocks_delegate": False,
        "allowfullscreen_other_navigation": True,
        "allow_src_rejects_other_navigation": False,
        "allow_port_wildcard_rejected": False,
        "unknown_feature": False,
        "malformed_header_keeps_default": True,
        "report_to_still_disabled": (False, "endpoint"),
        "first_allow_entry_wins": False,
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
