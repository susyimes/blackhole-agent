"""Unit tests for scoped bearer parsing and authentication."""

from __future__ import annotations

from blackhole_agent.invocation_token_scopes import (
    TOKEN_SCOPE_ENV,
    TokenPrincipal,
    TokenScopeError,
    UNRESTRICTED,
    authenticate_bearer,
    bind_optional_bearer,
    filter_invocable,
    parse_token_scope_clause,
    principal_allowlist_payload,
    reset_principal,
    resolve_token_scopes,
    tool_is_allowed,
)


def test_parse_clause_and_authenticate() -> None:
    token, allowed = parse_token_scope_clause("ci=capability.absorbed-scope-shout")
    assert token == "ci"
    assert allowed == frozenset({"capability.absorbed-scope-shout"})
    table = resolve_token_scopes(["ci=capability.absorbed-scope-shout,capability.absorbed-other"])
    operator = authenticate_bearer("admin", "admin", table)
    assert operator is UNRESTRICTED
    scoped = authenticate_bearer("ci", "admin", table)
    assert scoped is not None
    assert scoped.unrestricted is False
    assert scoped.allows("capability.absorbed-scope-shout")
    assert not scoped.allows("capability.absorbed-text-reverser")
    assert authenticate_bearer("nope", "admin", table) is None


def test_env_json_and_filter() -> None:
    table = resolve_token_scopes(
        None,
        env={TOKEN_SCOPE_ENV: '{"job": ["capability.absorbed-scope-shout"]}'},
    )
    assert table.enabled is True
    assert table.count == 1
    principal = authenticate_bearer("job", "", table)
    assert principal is not None
    visible = filter_invocable(
        {
            "capability.absorbed-scope-shout": {"id": "capability.absorbed-scope-shout"},
            "capability.absorbed-text-reverser": {"id": "capability.absorbed-text-reverser"},
        },
        principal,
    )
    assert list(visible) == ["capability.absorbed-scope-shout"]
    assert tool_is_allowed("capability.absorbed-scope-shout", principal)
    assert not tool_is_allowed("capability.absorbed-text-reverser", principal)


def test_invalid_clause_fails_closed() -> None:
    try:
        parse_token_scope_clause("noids=")
    except TokenScopeError as exc:
        assert exc.payload["error"] == "token_scope_invalid"
    else:
        raise AssertionError("expected TokenScopeError")


def test_allowlist_payload_and_optional_bearer() -> None:
    table = resolve_token_scopes(["ci=capability.absorbed-scope-shout"])
    reset_principal()
    try:
        unrestricted = bind_optional_bearer(None, "admin", table)
        assert unrestricted is UNRESTRICTED
        assert principal_allowlist_payload() == {"scoped": False, "allow": None}
        scoped = bind_optional_bearer("ci", "admin", table)
        assert scoped is not None
        assert scoped.unrestricted is False
        assert principal_allowlist_payload(scoped) == {
            "scoped": True,
            "allow": ["capability.absorbed-scope-shout"],
        }
        ignored = bind_optional_bearer("nope", "admin", table)
        assert ignored is UNRESTRICTED
    finally:
        reset_principal()
    payload = principal_allowlist_payload(
        TokenPrincipal(unrestricted=False, allowed=frozenset({"capability.absorbed-scope-shout"}))
    )
    assert payload["scoped"] is True
    assert payload["allow"] == ["capability.absorbed-scope-shout"]


def test_leftover_markers_bind_console_mcp_capability() -> None:
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.invocation_token_scopes import TOKEN_SCOPE_CONSOLE_MCP_ID

    leftover = (
        "Optional follow-on: show a scoped token's allowlist in GET /console "
        "and return JSON-RPC invalid-params for a disallowed MCP tools/call name."
    )
    assert TOKEN_SCOPE_CONSOLE_MCP_ID in leftover_marker_ids(leftover)
