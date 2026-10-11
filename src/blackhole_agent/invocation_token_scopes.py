"""Least-privilege bearer tokens for the live invocation plane.

A configured ``--token`` currently authorizes every mutating route: a CI
job that only needs one fixture tool can POST /invoke every untrusted
tool, import bundles, and drive goal sessions. This module closes that
hole with opt-in scoped bearers:

- ``--token-scope TOKEN=id[,id...]`` (repeatable) or ``BLACKHOLE_TOKEN_SCOPE``
  registers additional bearers that may invoke only the listed tool ids
- the operator ``--token`` stays unrestricted
- a disallowed POST /invoke is HTTP 403 ``tool_not_allowed`` and never
  spawns
- GET /capabilities for a scoped bearer lists only the allowed ids
- POST /solve plans only over those ids
- admin routes (bundles, contract, reproof, sessions) stay operator-only
- a plane without ``--token-scope`` keeps historical all-allow bearer
  behavior, so the hole stays falsifiable
"""

from __future__ import annotations

import contextvars
import hmac
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
TOKEN_SCOPE_ENV = "BLACKHOLE_TOKEN_SCOPE"
TOOL_NOT_ALLOWED = "tool_not_allowed"
ADMIN_REQUIRED = "admin_required"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:~-]{1,128}$")
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class TokenScopeError(ValueError):
    """Fail-closed refusal of a malformed token-scope configuration."""

    def __init__(self, detail: str) -> None:
        self.payload = {
            "ok": False,
            "error": "token_scope_invalid",
            "detail": str(detail),
        }
        super().__init__(detail)


@dataclass(frozen=True)
class TokenPrincipal:
    """Authenticated caller: unrestricted operator or a scoped allowlist."""

    unrestricted: bool
    allowed: frozenset[str] = frozenset()

    def allows(self, capability_id: str) -> bool:
        if self.unrestricted:
            return True
        return str(capability_id) in self.allowed


UNRESTRICTED = TokenPrincipal(unrestricted=True, allowed=frozenset())


@dataclass(frozen=True)
class TokenScopeTable:
    """Parsed scoped bearers. ``enabled`` is true when at least one exists."""

    entries: tuple[tuple[str, frozenset[str]], ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.entries)

    @property
    def count(self) -> int:
        return len(self.entries)

    def health(self) -> dict[str, Any]:
        return {
            "token_scopes": self.enabled,
            "token_scope_count": self.count,
        }


EMPTY_SCOPES = TokenScopeTable()

_PRINCIPAL: contextvars.ContextVar[TokenPrincipal] = contextvars.ContextVar(
    "bh_invocation_principal",
    default=UNRESTRICTED,
)


def current_principal() -> TokenPrincipal:
    return _PRINCIPAL.get()


def bind_principal(principal: TokenPrincipal) -> None:
    _PRINCIPAL.set(principal)


def reset_principal() -> None:
    _PRINCIPAL.set(UNRESTRICTED)


def _compare(offered: str, expected: str) -> bool:
    return hmac.compare_digest(offered.encode("utf-8"), expected.encode("utf-8"))


def authenticate_bearer(
    offered: str,
    operator: str,
    table: TokenScopeTable,
) -> TokenPrincipal | None:
    """Return the principal for ``offered``, or None when no secret matches.

    Every registered secret is compared so a non-match does not short-circuit
    on the first mismatch. The operator token wins when it also appears as a
    scoped secret.
    """

    offered_text = str(offered or "")
    matched_operator = bool(operator) and _compare(offered_text, str(operator))
    matched_allowed: frozenset[str] | None = None
    for secret, allowed in table.entries:
        if _compare(offered_text, secret):
            matched_allowed = allowed
    if matched_operator:
        return UNRESTRICTED
    if matched_allowed is not None:
        return TokenPrincipal(unrestricted=False, allowed=matched_allowed)
    return None


def auth_is_required(operator: str, table: TokenScopeTable) -> bool:
    return bool(str(operator or "").strip()) or table.enabled


def parse_token_scope_clause(raw: str) -> tuple[str, frozenset[str]]:
    """Parse one ``TOKEN=id[,id...]`` clause."""

    text = str(raw or "").strip()
    if not text:
        raise TokenScopeError("token-scope clause is empty")
    if "=" not in text:
        raise TokenScopeError("token-scope clause must be TOKEN=id[,id...]")
    token, _, rest = text.partition("=")
    token = token.strip()
    if not _TOKEN_RE.fullmatch(token):
        raise TokenScopeError("token-scope secret must be 1-128 letters, digits, or ._:~-")
    ids = [part.strip() for part in rest.split(",") if part.strip()]
    if not ids:
        raise TokenScopeError("token-scope clause lists no tool ids")
    allowed: set[str] = set()
    for item in ids:
        if not _ID_RE.fullmatch(item):
            raise TokenScopeError(f"token-scope tool id is invalid: {item!r}")
        allowed.add(item)
    return token, frozenset(allowed)


def _from_mapping(payload: Mapping[str, Any]) -> list[tuple[str, frozenset[str]]]:
    parsed: list[tuple[str, frozenset[str]]] = []
    for token, value in payload.items():
        secret = str(token).strip()
        if not _TOKEN_RE.fullmatch(secret):
            raise TokenScopeError("token-scope secret must be 1-128 letters, digits, or ._:~-")
        if isinstance(value, str):
            ids = [part.strip() for part in value.split(",") if part.strip()]
        elif isinstance(value, (list, tuple)):
            ids = [str(item).strip() for item in value if str(item).strip()]
        else:
            raise TokenScopeError("token-scope allow list must be a string or array")
        if not ids:
            raise TokenScopeError("token-scope clause lists no tool ids")
        allowed: set[str] = set()
        for item in ids:
            if not _ID_RE.fullmatch(item):
                raise TokenScopeError(f"token-scope tool id is invalid: {item!r}")
            allowed.add(item)
        parsed.append((secret, frozenset(allowed)))
    return parsed


def _from_env_text(text: str) -> list[tuple[str, frozenset[str]]]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise TokenScopeError(f"BLACKHOLE_TOKEN_SCOPE is not JSON: {exc}") from exc
        if isinstance(payload, dict):
            return _from_mapping(payload)
        if isinstance(payload, list):
            parsed: list[tuple[str, frozenset[str]]] = []
            for item in payload:
                if isinstance(item, str):
                    parsed.append(parse_token_scope_clause(item))
                    continue
                if not isinstance(item, dict):
                    raise TokenScopeError("BLACKHOLE_TOKEN_SCOPE list entries must be objects or clauses")
                token = str(item.get("token") or "").strip()
                allow = item.get("allow")
                if not token:
                    raise TokenScopeError("token-scope object is missing token")
                parsed.extend(_from_mapping({token: allow}))
            return parsed
        raise TokenScopeError("BLACKHOLE_TOKEN_SCOPE JSON must be an object or array")
    return [parse_token_scope_clause(stripped)]


def resolve_token_scopes(
    explicit: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> TokenScopeTable:
    """Collect scoped bearers from CLI flags, else the process environment."""

    merged: dict[str, set[str]] = {}

    def add(token: str, allowed: frozenset[str]) -> None:
        merged.setdefault(token, set()).update(allowed)

    if explicit:
        for raw in explicit:
            token, allowed = parse_token_scope_clause(str(raw))
            add(token, allowed)
    else:
        source = env if env is not None else os.environ
        for token, allowed in _from_env_text(str(source.get(TOKEN_SCOPE_ENV) or "")):
            add(token, allowed)
    entries = tuple(
        (token, frozenset(allowed))
        for token, allowed in sorted(merged.items(), key=lambda item: item[0])
    )
    return TokenScopeTable(entries=entries)


def filter_invocable(
    invocable: Mapping[str, Any],
    principal: TokenPrincipal | None = None,
) -> dict[str, Any]:
    """Return the invocable subset the principal may see or plan over."""

    actor = UNRESTRICTED if principal is None else principal
    if actor.unrestricted:
        return dict(invocable)
    return {
        capability_id: item
        for capability_id, item in invocable.items()
        if actor.allows(capability_id)
    }


def tool_is_allowed(capability_id: Any, principal: TokenPrincipal | None = None) -> bool:
    """True when the principal may invoke ``capability_id``."""

    actor = current_principal() if principal is None else principal
    return actor.allows(str(capability_id or ""))
