"""The Referer value follows Referrer Policy, including a loopback downgrade.

strict-origin-when-cross-origin keeps a same-origin path and sends only the
origin across https origins. An http target omits the header. strict-origin
and no-referrer-when-downgrade also omit it when the source is loopback and
the target is an ordinary http site. origin-when-cross-origin still sends the
https origin on that insecure target. The last recognized header token wins.
A stripped referrer longer than 4096 characters is cut down to the origin,
and a referrer of exactly 4096 characters is not.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the policy step is an unmet outcome.
"""

from __future__ import annotations

import json

SOURCE = "https://shop.example/a/pay?x=1#old"
SAME = "https://shop.example/next"
CROSS = "https://other.example/b"
INSECURE = "http://other.example/b"
LOOPBACK = "http://127.0.0.1/secret"
PLAIN = "http://shop.example/"


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.referrer_policy import (
            parse_referrer_policy,
            referrer_policy_after_redirect,
            referrer_value,
        )
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    origin_base = "https://shop.example/"
    over_cap = origin_base + ("a" * (4096 - len(origin_base) + 1))
    at_cap = origin_base + ("b" * (4096 - len(origin_base)))
    at_cap_value = referrer_value("unsafe-url", at_cap, INSECURE)
    cases: dict[str, tuple[object, object]] = {
        "same_origin_keeps_path": (
            referrer_value("strict-origin-when-cross-origin", SOURCE, SAME),
            "https://shop.example/a/pay?x=1",
        ),
        "cross_origin_https_is_origin": (
            referrer_value("strict-origin-when-cross-origin", SOURCE, CROSS),
            "https://shop.example/",
        ),
        "https_to_http_omits": (
            referrer_value("strict-origin-when-cross-origin", SOURCE, INSECURE),
            "",
        ),
        "credentials_and_fragment_stripped": (
            referrer_value(
                "strict-origin-when-cross-origin",
                "https://user:pass@shop.example/a/pay?x=1#z",
                SAME,
            ),
            "https://shop.example/a/pay?x=1",
        ),
        "default_port_is_same_origin": (
            referrer_value(
                "strict-origin-when-cross-origin",
                "https://shop.example:443/a/pay?x=1#old",
                SAME,
            ),
            "https://shop.example/a/pay?x=1",
        ),
        "other_port_is_cross_origin": (
            referrer_value(
                "strict-origin-when-cross-origin",
                "https://shop.example:8443/a?q=1#f",
                "https://shop.example/b",
            ),
            "https://shop.example:8443/",
        ),
        "loopback_strict_origin_omits": (
            referrer_value("strict-origin", LOOPBACK, PLAIN),
            "",
        ),
        "loopback_octet_is_trustworthy": (
            referrer_value("strict-origin", "http://127.0.0.2/a", PLAIN),
            "",
        ),
        "ipv6_loopback_omits": (
            referrer_value("strict-origin", "http://[::1]/secret", PLAIN),
            "",
        ),
        "wss_to_ws_omits": (
            referrer_value("strict-origin", "wss://shop.example/room", "ws://shop.example/room"),
            "",
        ),
        "loopback_downgrade_policy_omits": (
            referrer_value("no-referrer-when-downgrade", "http://127.0.0.1/secret?q=1", PLAIN),
            "",
        ),
        "downgrade_policy_keeps_cross_origin_path": (
            referrer_value("no-referrer-when-downgrade", SOURCE, CROSS),
            "https://shop.example/a/pay?x=1",
        ),
        "origin_when_cross_origin_survives_http": (
            referrer_value("origin-when-cross-origin", SOURCE, INSECURE),
            "https://shop.example/",
        ),
        "same_origin_policy_omits_cross_origin": (
            referrer_value("same-origin", SOURCE, CROSS),
            "",
        ),
        "unsafe_url_keeps_path_on_http": (
            referrer_value("unsafe-url", SOURCE, INSECURE),
            "https://shop.example/a/pay?x=1",
        ),
        "no_referrer_omits_same_origin": (
            referrer_value("no-referrer", SOURCE, SAME),
            "",
        ),
        "over_cap_becomes_origin": (
            referrer_value("unsafe-url", over_cap, INSECURE),
            "https://shop.example/",
        ),
        "at_cap_keeps_path": (at_cap_value == at_cap, True),
        "last_recognized_token": (
            parse_referrer_policy("no-referrer, not-a-policy, origin"),
            "origin",
        ),
        "mixed_case_later_token": (
            parse_referrer_policy(["no-referrer", "Unsafe-URL"]),
            "unsafe-url",
        ),
        "redirect_header_replaces_policy": (
            referrer_policy_after_redirect(
                "same-origin",
                [("Referrer-Policy", "origin, unsafe-url")],
            ),
            "unsafe-url",
        ),
        "unrecognized_redirect_header_keeps_policy": (
            referrer_policy_after_redirect("same-origin", [("Referrer-Policy", "not-a-policy")]),
            "same-origin",
        ),
        "file_to_http_omits": (
            referrer_value("strict-origin", "file:///tmp/secret.html", PLAIN),
            "",
        ),
    }
    observed: dict[str, object] = {}
    mismatches: list[str] = []
    for name, (got, want) in cases.items():
        observed[name] = got
        if got != want:
            mismatches.append(name)
    observed["mismatches"] = mismatches
    observed["over_cap_length"] = len(over_cap)
    observed["at_cap_length"] = len(at_cap_value) if isinstance(at_cap_value, str) else 0
    return not mismatches, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": f"{type(exc).__name__}: {exc}"}
    if not observed:
        observed = {"empty": True}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
