"""Unit tests for live-plane RFC 9728 / OAuth 2.1 issuance."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlencode, urlsplit

from blackhole_agent.oauth_protected_resource import (
    OPERATOR_CLIENT_ID,
    OAuthIssuer,
    is_loopback_origin,
    is_loopback_redirect,
    pkce_s256,
    www_authenticate,
)


def test_pkce_s256_is_rfc7636() -> None:
    # RFC 7636 appendix B
    assert pkce_s256("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == (
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )


def test_loopback_redirect_and_origin() -> None:
    assert is_loopback_redirect("http://127.0.0.1:9/cb")
    assert is_loopback_redirect("http://localhost/cb")
    assert not is_loopback_redirect("https://evil.example/cb")
    assert not is_loopback_redirect("http://127.0.0.1:9/cb#frag")
    assert is_loopback_origin("http://127.0.0.1:6274")
    assert not is_loopback_origin("http://evil.example")


def test_www_authenticate_includes_resource_metadata() -> None:
    header = www_authenticate("http://127.0.0.1:9")
    assert 'realm="blackhole-invocation-plane"' in header
    assert 'resource_metadata="http://127.0.0.1:9/.well-known/oauth-protected-resource"' in header


def test_disabled_issuer_404s() -> None:
    issuer = OAuthIssuer("")
    assert issuer.enabled is False
    assert issuer.health()["oauth_protected_resource"] is False
    status, payload = issuer.register_client({"redirect_uris": ["http://127.0.0.1:9/cb"]})
    assert status == 404
    assert payload["error"] == "oauth_disabled"


def test_register_refuses_foreign_redirect() -> None:
    issuer = OAuthIssuer("secret")
    status, payload = issuer.register_client({"redirect_uris": ["https://evil.example/cb"]})
    assert status == 400
    assert payload["error"] == "invalid_redirect_uri"


def test_pkce_round_trip_and_replay() -> None:
    issuer = OAuthIssuer("operator-secret")
    origin = "http://127.0.0.1:9"
    redirect = "http://127.0.0.1:9/cb"
    status, registered = issuer.register_client(
        {
            "redirect_uris": [redirect],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"],
        }
    )
    assert status == 201
    client_id = registered["client_id"]
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    query = parse_qs(
        urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect,
                "code_challenge": pkce_s256(verifier),
                "code_challenge_method": "S256",
                "resource": f"{origin}/mcp",
            }
        )
    )
    denied, _, body = issuer.authorize(query, operator_ok=False, origin=origin)
    assert denied == 401
    assert body and body["error"] == "authorization_required"
    status, headers, payload = issuer.authorize(query, operator_ok=True, origin=origin)
    assert status == 302
    assert payload is None
    location = headers["Location"]
    code = parse_qs(urlsplit(location).query)["code"][0]
    token_status, token = issuer.token(
        parse_qs(
            urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect,
                    "client_id": client_id,
                    "code_verifier": verifier,
                    "resource": f"{origin}/mcp",
                }
            )
        ),
        origin=origin,
    )
    assert token_status == 200
    assert issuer.authenticate(token["access_token"]) is not None
    replay_status, replay = issuer.token(
        parse_qs(
            urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect,
                    "client_id": client_id,
                    "code_verifier": verifier,
                    "resource": f"{origin}/mcp",
                }
            )
        ),
        origin=origin,
    )
    assert replay_status == 400
    assert replay["error"] == "invalid_grant"
    wrong_status, wrong = issuer.token(
        parse_qs(
            urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": "missing",
                    "redirect_uri": redirect,
                    "client_id": client_id,
                    "code_verifier": "wrong-verifier-wrong-verifier-wrong-xx",
                    "resource": f"{origin}/mcp",
                }
            )
        ),
        origin=origin,
    )
    assert wrong_status == 400


def test_operator_client_credentials() -> None:
    issuer = OAuthIssuer("operator-secret")
    origin = "http://127.0.0.1:9"
    status, token = issuer.token(
        parse_qs(
            urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": OPERATOR_CLIENT_ID,
                    "client_secret": "operator-secret",
                    "resource": f"{origin}/mcp",
                }
            )
        ),
        origin=origin,
    )
    assert status == 200
    principal = issuer.authenticate(token["access_token"])
    assert principal is not None
    assert principal.unrestricted is True
    bad_status, bad = issuer.token(
        parse_qs(
            urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": OPERATOR_CLIENT_ID,
                    "client_secret": "wrong",
                    "resource": f"{origin}/mcp",
                }
            )
        ),
        origin=origin,
    )
    assert bad_status == 401
    assert bad["error"] == "invalid_client"


def test_goal_binds_oauth_protected_resource_leftover() -> None:
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.mcp_http_auth import MCP_HTTP_AUTH_GOAL, MCP_HTTP_AUTH_ID
    from blackhole_agent.oauth_protected_resource import (
        OAUTH_PROTECTED_RESOURCE_GOAL,
        OAUTH_PROTECTED_RESOURCE_ID,
    )

    assert leftover_marker_ids(OAUTH_PROTECTED_RESOURCE_GOAL) == (
        OAUTH_PROTECTED_RESOURCE_ID,
    )
    assert OAUTH_PROTECTED_RESOURCE_ID not in leftover_marker_ids(MCP_HTTP_AUTH_GOAL)
    assert leftover_marker_ids(MCP_HTTP_AUTH_GOAL) == (MCP_HTTP_AUTH_ID,)


def test_builtin_oauth_protected_resource_proof() -> None:
    from blackhole_agent.oauth_protected_resource import builtin_oauth_protected_resource_proof

    result = builtin_oauth_protected_resource_proof()
    assert result["ok"] is True
    assert result["action"] == "oauth_protected_resource"
    assert all(result["checks"].values())
    assert result["used_skill_route_discovery"] is False
    print(json.dumps({"proof": True, "checks": sorted(result["checks"])}))
