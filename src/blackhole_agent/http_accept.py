"""Choose an HTTP representation from an Accept header.

RFC 9110 section 12.5.1 assigns each variant the quality of one media range:
the most specific range that matches. A concrete ``text/html;q=0.1`` beats
``text/*;q=0.8`` for a text/html variant. Quality zero removes the variant.
A parameter on a range matches only a variant that carries that parameter.
When two acceptable variants share a quality, the earlier one in the
server's list is returned.

An empty field value has no ranges, so nothing is chosen. A missing header
is not the same event; the caller passes ``*/*`` for that default.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
_QVALUE = re.compile(r"0(?:\.[0-9]{1,3})?|1(?:\.0{1,3})?\Z")


class _Media:
    __slots__ = ("params", "quality", "subtype", "type")

    def __init__(self, type_: str, subtype: str, params: dict[str, str], quality: int) -> None:
        self.type = type_
        self.subtype = subtype
        self.params = params
        self.quality = quality


def negotiate_media_type(accept: str, available: Sequence[str]) -> dict[str, object]:
    """Return the server's chosen representation for an Accept field value.

    ``selected`` is the original available entry, or ``""`` when none is
    acceptable. ``quality_milli`` is that entry's quality in thousandths
    from 0 through 1000.
    """

    if not isinstance(accept, str):
        raise TypeError("Accept header must be a string")
    if isinstance(available, (str, bytes)) or not isinstance(available, Sequence):
        raise TypeError("available representations must be a sequence of strings")
    ranges = _accept_ranges(accept)
    chosen = ""
    best = 0
    found = False
    for item in available:
        if not isinstance(item, str):
            raise TypeError("available representations must be strings")
        media = _parse_media(item, accept_quality=False)
        if media is None:
            continue
        quality = _assigned_quality(ranges, media)
        if quality is None or quality <= 0:
            continue
        if not found or quality > best:
            found = True
            best = quality
            chosen = item
    if not found:
        return {"ok": True, "selected": "", "quality_milli": 0}
    return {"ok": True, "selected": chosen, "quality_milli": best}


def _accept_ranges(accept: str) -> list[_Media]:
    pieces = _split_top(accept, ",")
    if pieces is None:
        return []
    ranges: list[_Media] = []
    for piece in pieces:
        if not piece.strip():
            continue
        media = _parse_media(piece, accept_quality=True)
        if media is not None:
            ranges.append(media)
    return ranges


def _assigned_quality(ranges: list[_Media], media: _Media) -> int | None:
    best_spec: tuple[int, int, int] | None = None
    best_q = 0
    for item in ranges:
        if not _matches(item, media):
            continue
        spec = _specificity(item)
        if best_spec is None or spec > best_spec or (spec == best_spec and item.quality > best_q):
            best_spec = spec
            best_q = item.quality
    if best_spec is None:
        return None
    return best_q


def _specificity(media: _Media) -> tuple[int, int, int]:
    return (
        0 if media.type == "*" else 1,
        0 if media.subtype == "*" else 1,
        len(media.params),
    )


def _matches(rule: _Media, media: _Media) -> bool:
    if rule.type != "*" and rule.type != media.type:
        return False
    if rule.subtype != "*" and rule.subtype != media.subtype:
        return False
    for name, value in rule.params.items():
        if media.params.get(name) != value:
            return False
    return True


def _parse_media(value: str, *, accept_quality: bool) -> _Media | None:
    parts = _split_top(value, ";")
    if not parts:
        return None
    if not parts[-1].strip():
        parts = parts[:-1]
    if not parts or any(not part.strip() for part in parts):
        return None
    main = _parse_type(parts[0])
    if main is None:
        return None
    params: dict[str, str] = {}
    quality = 1000
    saw_quality = False
    for part in parts[1:]:
        name, raw = _parameter(part)
        if name is None or raw is None:
            return None
        if accept_quality and name == "q":
            if saw_quality:
                return None
            parsed = _quality_milli(raw)
            if parsed is None:
                return None
            saw_quality = True
            quality = parsed
            continue
        if name in params:
            return None
        params[name] = raw
    return _Media(main[0], main[1], params, quality)


def _parse_type(value: str) -> tuple[str, str] | None:
    text = value.strip().lower()
    if text.count("/") != 1:
        return None
    left, right = (part.strip() for part in text.split("/"))
    type_ = _type_token(left)
    subtype = _type_token(right)
    if type_ is None or subtype is None:
        return None
    if type_ == "*" and subtype != "*":
        return None
    return type_, subtype


def _type_token(value: str) -> str | None:
    if value == "*":
        return "*"
    if _TOKEN.fullmatch(value):
        return value
    return None


def _parameter(part: str) -> tuple[str | None, str | None]:
    text = part.strip()
    if "=" not in text:
        return None, None
    name, raw = text.split("=", 1)
    name = name.strip().lower()
    if not _TOKEN.fullmatch(name):
        return None, None
    value = _unquote(raw.strip())
    if value is None:
        return None, None
    return name, value


def _unquote(raw: str) -> str | None:
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        chars: list[str] = []
        escape = False
        for char in raw[1:-1]:
            if escape:
                chars.append(char)
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            chars.append(char)
        if escape:
            return None
        return "".join(chars).lower()
    if not _TOKEN.fullmatch(raw):
        return None
    return raw.lower()


def _quality_milli(raw: str) -> int | None:
    if not _QVALUE.fullmatch(raw):
        return None
    if "." not in raw:
        return 1000 if raw == "1" else 0
    whole, frac = raw.split(".")
    return (1000 if whole == "1" else 0) + int(frac.ljust(3, "0"))


def _split_top(value: str, separator: str) -> list[str] | None:
    parts: list[str] = []
    buf: list[str] = []
    quoted = False
    escape = False
    for char in value:
        if escape:
            buf.append(char)
            escape = False
            continue
        if quoted and char == "\\":
            buf.append(char)
            escape = True
            continue
        if char == '"':
            quoted = not quoted
            buf.append(char)
            continue
        if char == separator and not quoted:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(char)
    if quoted or escape:
        return None
    parts.append("".join(buf))
    return parts
