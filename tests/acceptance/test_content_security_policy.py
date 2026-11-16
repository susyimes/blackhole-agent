"""Content Security Policy allows a fetch or an inline script by source list.

script-src replaces default-src. A dotted wildcard does not match its apex
or a lookalike suffix. A directory path matches after percent-decoding, and
does not match a sibling segment. The first duplicate directive wins.
'none' blocks only by itself. 'strict-dynamic' blocks a parser-inserted
script whose host would otherwise match, while a nonce still allows it.
script-src-elem does not govern a worker. An inline script matches a nonce
or the sha256 of its exact bytes, and either one suppresses 'unsafe-inline'.
Two policies must both allow the request. A star does not allow a data URL,
and 'self' does not allow a blob URL.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the checker is an unmet outcome, not a crash.
"""

from __future__ import annotations

import base64
import hashlib
import json


_PAGE = "https://app.example/index.html"
_HTTP_PAGE = "http://app.example/index.html"


def _hash(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.content_security_policy import allows
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    alert = b"alert(1)"
    other = b"alert(2)"
    digest = _hash(alert)
    observed: dict[str, object] = {}
    expected: dict[str, tuple[bool, str]] = {}

    def check(
        name: str,
        policy: str | tuple[str, ...],
        *,
        destination: str,
        allowed: bool,
        directive: str,
        url: str = "",
        inline: bytes | None = None,
        nonce: str = "",
        parser_inserted: bool = False,
        document: str = _PAGE,
    ) -> None:
        result = allows(
            policy,
            document,
            destination=destination,
            url=url,
            inline=inline,
            nonce=nonce,
            parser_inserted=parser_inserted,
        )
        observed[name] = result
        expected[name] = (allowed, directive)

    check(
        "cdn_script",
        "default-src 'self'; script-src https://cdn.example",
        destination="script",
        url="https://cdn.example/app.js",
        allowed=True,
        directive="script-src",
    )
    check(
        "self_script_blocked",
        "default-src 'self'; script-src https://cdn.example",
        destination="script",
        url="https://app.example/app.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "self_image",
        "default-src 'self'; script-src https://cdn.example",
        destination="image",
        url="https://app.example/a.png",
        allowed=True,
        directive="default-src",
    )
    check(
        "cdn_image_blocked",
        "default-src 'self'; script-src https://cdn.example",
        destination="image",
        url="https://cdn.example/a.png",
        allowed=False,
        directive="default-src",
    )
    check(
        "wildcard_subdomain",
        "script-src *.example.com",
        destination="script",
        url="https://a.b.example.com/a.js",
        allowed=True,
        directive="script-src",
    )
    check(
        "wildcard_apex_blocked",
        "script-src *.example.com",
        destination="script",
        url="https://example.com/a.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "wildcard_lookalike_blocked",
        "script-src *.example.com",
        destination="script",
        url="https://notexample.com/a.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "wildcard_suffix_blocked",
        "script-src *.example.com",
        destination="script",
        url="https://example.com.evil.com/a.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "directory_child",
        "script-src https://cdn.example/js/",
        destination="script",
        url="https://cdn.example/js/app.js",
        allowed=True,
        directive="script-src",
    )
    check(
        "directory_sibling_blocked",
        "script-src https://cdn.example/js/",
        destination="script",
        url="https://cdn.example/jsapp.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "percent_decoded_segment",
        "script-src https://cdn.example/js/%61.js",
        destination="script",
        url="https://cdn.example/js/a.js",
        allowed=True,
        directive="script-src",
    )
    check(
        "percent_decoded_other_blocked",
        "script-src https://cdn.example/js/%61.js",
        destination="script",
        url="https://cdn.example/js/b.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "first_directive_wins",
        "script-src https://cdn.example; script-src 'none'",
        destination="script",
        url="https://cdn.example/app.js",
        allowed=True,
        directive="script-src",
    )
    check(
        "none_alone",
        "Script-SRC 'NONE'",
        destination="script",
        url="https://cdn.example/app.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "none_ignored_beside_host",
        "script-src 'none' https://cdn.example",
        destination="script",
        url="https://cdn.example/app.js",
        allowed=True,
        directive="script-src",
    )
    check(
        "strict_dynamic_parser_blocked",
        "script-src https://cdn.example 'strict-dynamic'",
        destination="script",
        url="https://cdn.example/app.js",
        parser_inserted=True,
        allowed=False,
        directive="script-src",
    )
    check(
        "strict_dynamic_nonce_allows",
        "script-src https://cdn.example 'nonce-YQ==' 'strict-dynamic'",
        destination="script",
        url="https://evil.example/app.js",
        nonce="YQ==",
        parser_inserted=True,
        allowed=True,
        directive="script-src",
    )
    check(
        "strict_dynamic_runtime_allows",
        "script-src https://cdn.example 'strict-dynamic'",
        destination="script",
        url="https://evil.example/app.js",
        parser_inserted=False,
        allowed=True,
        directive="script-src",
    )
    check(
        "elem_blocks_script",
        "script-src-elem https://cdn.example",
        destination="script",
        url="https://evil.example/a.js",
        allowed=False,
        directive="script-src-elem",
    )
    check(
        "elem_ignores_worker",
        "script-src-elem https://cdn.example",
        destination="worker",
        url="https://evil.example/w.js",
        allowed=True,
        directive="",
    )
    check(
        "script_src_blocks_worker",
        "script-src https://cdn.example",
        destination="worker",
        url="https://evil.example/w.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "script_src_allows_worker",
        "script-src https://cdn.example",
        destination="worker",
        url="https://cdn.example/w.js",
        allowed=True,
        directive="script-src",
    )
    check(
        "img_src_ignores_script",
        "img-src 'self'",
        destination="script",
        url="https://evil.example/a.js",
        allowed=True,
        directive="",
    )
    check(
        "self_allows",
        "Script-SRC 'Self'",
        destination="script",
        url="https://app.example/app.js",
        allowed=True,
        directive="script-src",
    )
    check(
        "self_blocks_downgrade",
        "script-src 'self'",
        destination="script",
        url="http://app.example/app.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "self_blocks_blob",
        "script-src 'self'",
        destination="script",
        url="blob:https://app.example/uuid",
        allowed=False,
        directive="script-src",
    )
    check(
        "star_allows_https",
        "script-src *",
        destination="script",
        url="https://evil.example/a.js",
        allowed=True,
        directive="script-src",
    )
    check(
        "star_blocks_data",
        "script-src *",
        destination="script",
        url="data:text/javascript,1",
        allowed=False,
        directive="script-src",
    )
    check(
        "data_scheme_allows",
        "script-src data:",
        destination="script",
        url="data:text/javascript,1",
        allowed=True,
        directive="script-src",
    )
    check(
        "https_scheme_blocks_http",
        "script-src https:",
        destination="script",
        url="http://evil.example/a.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "upgrade_from_http_source",
        "script-src http://cdn.example",
        destination="script",
        url="https://cdn.example/a.js",
        document=_HTTP_PAGE,
        allowed=True,
        directive="script-src",
    )
    check(
        "schemeless_blocks_http",
        "script-src cdn.example",
        destination="script",
        url="http://cdn.example/a.js",
        allowed=False,
        directive="script-src",
    )
    check(
        "ip_host_blocked",
        "script-src http://127.0.0.1",
        destination="script",
        url="http://127.0.0.1/a.js",
        document=_HTTP_PAGE,
        allowed=False,
        directive="script-src",
    )
    check(
        "inline_hash",
        f"script-src 'nonce-YQ==' 'sha256-{digest}'",
        destination="script",
        inline=alert,
        allowed=True,
        directive="script-src",
    )
    check(
        "inline_nonce",
        f"script-src 'nonce-YQ==' 'sha256-{digest}'",
        destination="script",
        inline=other,
        nonce="YQ==",
        allowed=True,
        directive="script-src",
    )
    check(
        "inline_wrong_nonce",
        f"script-src 'nonce-YQ==' 'sha256-{digest}'",
        destination="script",
        inline=other,
        nonce="nope",
        allowed=False,
        directive="script-src",
    )
    check(
        "unsafe_inline",
        "script-src 'unsafe-inline'",
        destination="script",
        inline=other,
        allowed=True,
        directive="script-src",
    )
    check(
        "unsafe_inline_suppressed",
        "script-src 'unsafe-inline' 'nonce-YQ=='",
        destination="script",
        inline=other,
        allowed=False,
        directive="script-src",
    )
    check(
        "two_policies_block_cdn",
        ("default-src 'self'", "script-src https://cdn.example"),
        destination="script",
        url="https://cdn.example/app.js",
        allowed=False,
        directive="default-src",
    )
    check(
        "two_policies_block_self",
        ("default-src 'self'", "script-src https://cdn.example"),
        destination="script",
        url="https://app.example/app.js",
        allowed=False,
        directive="script-src",
    )

    mismatches = {
        name: {"got": observed[name], "want_allowed": want_allowed, "want_directive": want_directive}
        for name, (want_allowed, want_directive) in expected.items()
        if not isinstance(observed[name], dict)
        or observed[name].get("allowed") is not want_allowed
        or observed[name].get("effective_directive") != want_directive
    }
    passed = not mismatches
    if mismatches:
        observed = {"mismatches": mismatches}
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=True))


if __name__ == "__main__":
    main()
