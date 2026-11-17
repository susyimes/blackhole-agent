"""Decide whether two URLs are the same cache key under No-Vary-Search.

The November 2026 draft compares scheme, host, port, and path first. A
fragment or userinfo is not part of that identity. The default configuration,
including an absent or rejected header, then compares the raw query, so
``https://example.com/a`` and ``https://example.com/a?`` stay distinct and
parameter order stays significant.

Any other configuration parses the query as application/x-www-form-urlencoded.
``+`` becomes a space, percent-encoding is decoded, and empty ``&`` pieces
are dropped. ``params`` names keys that are removed. ``except`` names the
only keys that remain. ``key-order`` sorts the remaining keys by UTF-16 code
unit and keeps the original order of equal keys, so two values of one key
do not become interchangeable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from blackhole_agent.form_urlencoded import _decode_component, parse_form_bytes
from blackhole_agent.structured_fields import StructuredFieldError, parse_structured_field
from blackhole_agent.whatwg_url import URLParseError, _parse

_WILDCARD = "*"


@dataclass(frozen=True)
class _Config:
    no_vary: tuple[str, ...] | None
    vary: tuple[str, ...] | None
    vary_on_key_order: bool
    fallback: bool

    def is_default(self) -> bool:
        return self.no_vary == () and self.vary is None and self.vary_on_key_order


def no_vary_search_equivalent(
    url_a: str,
    url_b: str,
    header: str | Sequence[str] | None = None,
) -> dict[str, object]:
    """Return whether ``url_a`` and ``url_b`` match under the header value.

    ``header`` is the ``No-Vary-Search`` field value, or several field lines.
    ``None`` means the field is absent. ``outcome`` is ``equivalent``,
    ``distinct``, or ``invalid``. ``fallback`` is true when the field is
    absent or rejected and the default configuration is used. ``left`` and
    ``right`` are the parsed parameters after the header is applied, or null
    when the raw query is compared or a URL cannot be parsed.
    """

    if not isinstance(url_a, str) or not isinstance(url_b, str):
        return _invalid()
    try:
        left = _parse(url_a, None)
        right = _parse(url_b, None)
    except URLParseError:
        return _invalid()
    config = _configuration(header)
    if (left.scheme, left.host, left.port, tuple(left.path)) != (
        right.scheme,
        right.host,
        right.port,
        tuple(right.path),
    ):
        return _decision(config, False, None, None)
    if config.is_default():
        return _decision(config, left.query == right.query, None, None)
    left_pairs = _apply(config, _query_pairs(left.query))
    right_pairs = _apply(config, _query_pairs(right.query))
    return _decision(config, left_pairs == right_pairs, left_pairs, right_pairs)


def _invalid() -> dict[str, object]:
    return {
        "outcome": "invalid",
        "equivalent": False,
        "fallback": False,
        "vary_on_key_order": None,
        "no_vary_params": None,
        "vary_params": None,
        "left": None,
        "right": None,
    }


def _decision(
    config: _Config,
    equivalent: bool,
    left: list[tuple[str, str]] | None,
    right: list[tuple[str, str]] | None,
) -> dict[str, object]:
    return {
        "outcome": "equivalent" if equivalent else "distinct",
        "equivalent": equivalent,
        "fallback": config.fallback,
        "vary_on_key_order": config.vary_on_key_order,
        "no_vary_params": _WILDCARD if config.no_vary is None else list(config.no_vary),
        "vary_params": _WILDCARD if config.vary is None else list(config.vary),
        "left": None if left is None else [list(pair) for pair in left],
        "right": None if right is None else [list(pair) for pair in right],
    }


def _default(fallback: bool) -> _Config:
    return _Config((), None, True, fallback)


def _configuration(header: str | Sequence[str] | None) -> _Config:
    if header is None:
        return _default(True)
    try:
        parsed = parse_structured_field(header, "dictionary")
    except (StructuredFieldError, TypeError):
        return _default(True)
    fields: dict[str, object] = {}
    if not isinstance(parsed, list):
        return _default(True)
    for member in parsed:
        if not isinstance(member, list) or len(member) < 2 or not isinstance(member[0], str):
            return _default(True)
        fields[member[0]] = member[1]
    vary_on_key_order = True
    if "key-order" in fields:
        key_order = _bare(fields["key-order"])
        if not isinstance(key_order, bool):
            return _default(True)
        vary_on_key_order = not key_order
    has_params = "params" in fields
    has_except = "except" in fields
    if has_params and has_except:
        return _default(True)
    if not has_params and not has_except:
        return _Config((), None, vary_on_key_order, False)
    source = fields["params"] if has_params else fields["except"]
    keys = _keys(source)
    if keys is None:
        return _default(True)
    if has_params:
        return _Config(keys, None, vary_on_key_order, False)
    return _Config(None, keys, vary_on_key_order, False)


def _bare(member: object) -> object:
    if isinstance(member, list) and member:
        return member[0]
    return None


def _keys(member: object) -> tuple[str, ...] | None:
    items = _bare(member)
    if not isinstance(items, list):
        return None
    keys: list[str] = []
    for item in items:
        if not isinstance(item, list) or not item or not isinstance(item[0], str):
            return None
        try:
            encoded = item[0].encode("ascii")
        except UnicodeEncodeError:
            return None
        keys.append(_decode_component(encoded))
    return tuple(keys)


def _query_pairs(query: str | None) -> list[tuple[str, str]]:
    if query is None:
        return []
    try:
        data = query.encode("latin-1")
    except UnicodeEncodeError:
        data = query.encode("utf-8")
    return parse_form_bytes(data)


def _apply(config: _Config, pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    if config.no_vary is not None:
        ignored = set(config.no_vary)
        selected = [pair for pair in pairs if pair[0] not in ignored]
    elif config.vary is not None:
        kept = set(config.vary)
        selected = [pair for pair in pairs if pair[0] in kept]
    else:
        selected = list(pairs)
    if config.vary_on_key_order:
        return selected
    return sorted(selected, key=lambda pair: _utf16_units(pair[0]))


def _utf16_units(text: str) -> tuple[int, ...]:
    units: list[int] = []
    for char in text:
        code = ord(char)
        if code < 0x10000:
            units.append(code)
            continue
        shifted = code - 0x10000
        units.append(0xD800 + (shifted >> 10))
        units.append(0xDC00 + (shifted & 0x3FF))
    return tuple(units)
