"""Unit tests for live-plane RFC 9728 / OAuth 2.1 issuance."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlencode, urlsplit

from blackhole_agent.oauth_protected_resource import (
    OPERATOR_CLIENT_ID,
    OAUTH_AUTHORIZE_CONSENT_ID,
    OAUTH_AUTHORIZE_CONSENT_LEFTOVER,
    OAUTH_PROTECTED_RESOURCE_GOAL,
    OAUTH_PROTECTED_RESOURCE_ID,
    OAuthIssuer,
    consent_page,
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
    assert issuer.health()["oauth_authorize_consent"] is False
    status, payload = issuer.register_client({"redirect_uris": ["http://127.0.0.1:9/cb"]})
    assert status == 404
    assert payload["error"] == "oauth_disabled"
    auth_status, _, auth_body = issuer.authorize(
        {}, operator_ok=False, origin="http://127.0.0.1:9"
    )
    assert auth_status == 404
    assert isinstance(auth_body, dict) and auth_body["error"] == "oauth_disabled"


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
    assert denied == 200
    assert isinstance(body, str)
    assert 'id="oauth-consent"' in body
    assert 'name="operator_token"' in body
    assert 'name="decision"' in body
    wrong_status, _, wrong_body = issuer.authorize(
        query,
        operator_ok=False,
        origin=origin,
        decision="allow",
        operator_secret="wrong-secret",
    )
    assert wrong_status == 200
    assert isinstance(wrong_body, str)
    assert "operator token rejected" in wrong_body
    deny_status, deny_headers, _ = issuer.authorize(
        query, operator_ok=False, origin=origin, decision="deny"
    )
    assert deny_status == 302
    deny_query = parse_qs(urlsplit(deny_headers["Location"]).query)
    assert deny_query.get("error") == ["access_denied"]
    assert "code" not in deny_query
    form_status, form_headers, _ = issuer.authorize(
        query,
        operator_ok=False,
        origin=origin,
        decision="allow",
        operator_secret="operator-secret",
    )
    assert form_status == 302
    form_code = parse_qs(urlsplit(form_headers["Location"]).query)["code"][0]
    assert form_code
    form_token_status, form_token = issuer.token(
        parse_qs(
            urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": form_code,
                    "redirect_uri": redirect,
                    "client_id": client_id,
                    "code_verifier": verifier,
                    "resource": f"{origin}/mcp",
                }
            )
        ),
        origin=origin,
    )
    assert form_token_status == 200
    assert issuer.authenticate(form_token["access_token"]) is not None
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


def test_consent_page_escapes_untrusted_fields() -> None:
    page = consent_page(
        client_id='"><script>alert(1)</script>',
        redirect_uri="http://127.0.0.1:9/cb?x=<y>",
        code_challenge="a" * 43,
        code_challenge_method="S256",
        state="<state>",
        resource="http://127.0.0.1:9/mcp",
        error='<img src=x onerror=alert(1)>',
    )
    assert "<script>" not in page
    assert "<img" not in page
    assert "&lt;script&gt;" in page
    assert "&lt;img" in page
    assert 'id="oauth-consent"' in page


def test_goal_binds_oauth_protected_resource_leftover() -> None:
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.mcp_http_auth import MCP_HTTP_AUTH_GOAL, MCP_HTTP_AUTH_ID

    assert leftover_marker_ids(OAUTH_PROTECTED_RESOURCE_GOAL) == (
        OAUTH_PROTECTED_RESOURCE_ID,
    )
    assert leftover_marker_ids(OAUTH_AUTHORIZE_CONSENT_LEFTOVER) == (
        OAUTH_AUTHORIZE_CONSENT_ID,
    )
    assert OAUTH_AUTHORIZE_CONSENT_ID not in leftover_marker_ids(
        OAUTH_PROTECTED_RESOURCE_GOAL
    )
    assert OAUTH_PROTECTED_RESOURCE_ID not in leftover_marker_ids(
        OAUTH_AUTHORIZE_CONSENT_LEFTOVER
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


def test_builtin_oauth_authorize_consent_proof() -> None:
    from blackhole_agent.oauth_protected_resource import builtin_oauth_authorize_consent_proof

    result = builtin_oauth_authorize_consent_proof()
    assert result["ok"] is True
    assert result["action"] == "oauth_authorize_consent"
    assert all(result["checks"].values())
    assert result["used_skill_route_discovery"] is False
    print(json.dumps({"proof": True, "checks": sorted(result["checks"])}))
