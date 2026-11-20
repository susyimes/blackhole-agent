"""Select the CSS font face used for a character.

CSS Fonts Level 4 §5.2 walks the family list and narrows each family in a
fixed order: width, then style, then weight. A requested weight from 400
through 500 is searched upward through 500 before anything lower, so the
nearest absolute weight is the wrong answer. Italic is not oblique. Faces
that share width, style, and weight are one composite face, and the later
``unicode-range`` is tried first. A character that face cannot draw moves
to the next family; another weight in the same family is not a substitute.

An ``@font-face`` family with no available face does not reveal an installed
face of the same name. A private-use character never uses a generic family.
Family names compare by Unicode default caseless matching, without
normalization, so a combining ring does not match a precomposed letter.
This matcher does not synthesize oblique faces and does not invent fonts
beyond the faces the caller supplied.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

_GENERICS = frozenset(
    {
        "serif",
        "sans-serif",
        "cursive",
        "fantasy",
        "monospace",
        "system-ui",
        "emoji",
        "math",
        "fangsong",
        "ui-serif",
        "ui-sans-serif",
        "ui-monospace",
        "ui-rounded",
    }
)
_WIDTHS = {
    "ultra-condensed": 50.0,
    "extra-condensed": 62.5,
    "condensed": 75.0,
    "semi-condensed": 87.5,
    "normal": 100.0,
    "semi-expanded": 112.5,
    "expanded": 125.0,
    "extra-expanded": 150.0,
    "ultra-expanded": 200.0,
}
_WEIGHTS = {"normal": 400.0, "bold": 700.0}
_STYLE = re.compile(
    r"^(normal|italic|oblique)"
    r"(?:\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))deg"
    r"(?:\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))deg)?)?$",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Face:
    index: int
    id: str
    family: str
    family_key: str
    source: str
    available: bool
    weight: tuple[float, float]
    width: tuple[float, float]
    italic: tuple[float, float] | None
    oblique: tuple[float, float] | None
    kind: str
    coverage: tuple[tuple[int, int], ...]
    cmap: frozenset[int] | None


@dataclass(frozen=True)
class _Logical:
    members: tuple[_Face, ...]

    @property
    def index(self) -> int:
        return self.members[0].index

    @property
    def weight(self) -> tuple[float, float]:
        return self.members[0].weight

    @property
    def width(self) -> tuple[float, float]:
        return self.members[0].width

    @property
    def italic(self) -> tuple[float, float] | None:
        return self.members[0].italic

    @property
    def oblique(self) -> tuple[float, float] | None:
        return self.members[0].oblique


@dataclass(frozen=True)
class _Request:
    families: tuple[str, ...]
    weight: float
    width: float
    style: str
    angle: float | None
    generics: dict[str, str]


@dataclass(frozen=True)
class _Choice:
    logical: _Logical
    weight: float
    width: float
    axis: str
    style_value: float


def select_font_face(
    families: object,
    faces: object,
    character: object,
    *,
    weight: object = 400,
    width: object = "normal",
    style: object = "normal",
    inherited_weight: object = None,
    generics: object = None,
) -> dict[str, object]:
    """Return the face that draws ``character``.

    ``families`` is a CSS family list. ``faces`` are ``@font-face`` rules or
    installed faces. ``weight`` accepts a number, ``normal``, ``bold``,
    ``bolder``, or ``lighter``. ``width`` accepts a percentage or a width
    keyword. ``style`` accepts ``normal``, ``italic``, or ``oblique`` with an
    angle. A string character may be a cluster: the whole sequence is tried,
    then one canonically equivalent character, then a variation selector is
    dropped, and only then is the cluster split.
    """

    try:
        request = _request(families, weight, width, style, inherited_weight, generics)
        library = _library(faces)
        text = _text(character)
        segments = _segments(library, request, text)
    except _Invalid as exc:
        return _invalid(exc.reason)
    return _pack(segments, request)


def first_available_font(
    families: object,
    faces: object,
    *,
    weight: object = 400,
    width: object = "normal",
    style: object = "normal",
    inherited_weight: object = None,
    generics: object = None,
) -> dict[str, object]:
    """Return the first face whose unicode-range does not exclude U+0020.

    The character map does not matter. Width, style, and weight still choose
    one face in the family; a different weight is not consulted when that
    face excludes space.
    """

    try:
        request = _request(families, weight, width, style, inherited_weight, generics)
        library = _library(faces)
        chosen = _walk(library, request, " ", glyphs=False)
    except _Invalid as exc:
        return _invalid(exc.reason)
    if chosen is None:
        segment = _blank(" ")
        segment["rendered"] = " "
    else:
        face, raw, choice = chosen
        segment = _segment(face, raw, choice, " ")
    return _pack([segment], request, unmatched="no face includes U+0020")


def _segments(library: tuple[_Face, ...], request: _Request, text: str) -> list[dict[str, object]]:
    chosen = _walk(library, request, text, glyphs=True)
    if chosen is not None:
        face, raw, choice = chosen
        return [_segment(face, raw, choice, text)]
    if len(text) == 1:
        return [_blank(text)]
    composed = unicodedata.normalize("NFC", text)
    if composed != text and len(composed) == 1:
        chosen = _walk(library, request, composed, glyphs=True)
        if chosen is not None:
            face, raw, choice = chosen
            segment = _segment(face, raw, choice, text)
            segment["rendered"] = composed
            return [segment]
    if len(text) == 2 and _variation(ord(text[1])):
        chosen = _walk(library, request, text[0], glyphs=True)
        if chosen is None:
            return [_blank(text)]
        face, raw, choice = chosen
        segment = _segment(face, raw, choice, text)
        segment["variation_ignored"] = True
        return [segment]
    for size in range(len(text) - 1, 0, -1):
        chosen = _walk(library, request, text[:size], glyphs=True)
        if chosen is None:
            continue
        face, raw, choice = chosen
        head = _segment(face, raw, choice, text[:size])
        return [head, *_segments(library, request, text[size:])]
    return [_blank(text[0]), *_segments(library, request, text[1:])]


def _walk(
    library: tuple[_Face, ...],
    request: _Request,
    text: str,
    *,
    glyphs: bool,
) -> tuple[_Face, str, _Choice] | None:
    private = any(_private(ord(char)) for char in text)
    for raw in request.families:
        if private and raw.casefold() in _GENERICS:
            continue
        key = _family_key(raw, request.generics)
        if key is None:
            continue
        pool = _pool(library, key)
        if not pool:
            continue
        choice = _narrow(_group(pool), request)
        if choice is None:
            continue
        for face in reversed(choice.logical.members):
            if _supports(face, text, glyphs=glyphs):
                return face, raw, choice
    return None


def _pool(library: tuple[_Face, ...], key: str) -> list[_Face]:
    declared = [face for face in library if face.family_key == key and face.source == "font-face"]
    if declared:
        return [face for face in declared if face.available]
    return [
        face
        for face in library
        if face.family_key == key and face.source == "installed" and face.available
    ]


def _group(pool: list[_Face]) -> list[_Logical]:
    grouped: dict[tuple[object, ...], list[_Face]] = {}
    logical: list[_Logical] = []
    for face in pool:
        if face.source != "font-face":
            logical.append(_Logical((face,)))
            continue
        identity = (face.weight, face.width, face.italic, face.oblique)
        grouped.setdefault(identity, []).append(face)
    for members in grouped.values():
        ordered = tuple(sorted(members, key=lambda face: face.index))
        logical.append(_Logical(ordered))
    return logical


def _narrow(logicals: list[_Logical], request: _Request) -> _Choice | None:
    if not logicals:
        return None
    width = _width_target([item.width for item in logicals], request.width)
    logicals = [item for item in logicals if _contains(item.width, width)]
    axis, style_value = _style_target(logicals, request.style, request.angle)
    if axis is None or style_value is None:
        return None
    logicals = [item for item in logicals if _contains(_axis_span(item, axis), style_value)]
    if not logicals:
        return None
    weight = _weight_target([item.weight for item in logicals], request.weight)
    logicals = [item for item in logicals if _contains(item.weight, weight)]
    if not logicals:
        return None
    chosen = min(logicals, key=lambda item: item.index)
    return _Choice(chosen, weight, width, axis, style_value)


def _axis_span(logical: _Logical, axis: str) -> tuple[float, float] | None:
    if axis == "oblique":
        return logical.oblique
    return logical.italic


def _style_target(
    logicals: list[_Logical], kind: str, angle: float | None
) -> tuple[str, float] | tuple[None, None]:
    italics = [item.italic for item in logicals if item.italic is not None]
    obliques = [item.oblique for item in logicals if item.oblique is not None]
    if kind == "normal":
        return _normal_style(italics, obliques)
    if kind == "italic":
        return _italic_style(italics, obliques)
    if angle is None:
        return None, None
    if angle < 0:
        return _reflect_oblique(italics, obliques, angle)
    if angle >= 11:
        return _steep_oblique(italics, obliques, angle)
    return _shallow_oblique(italics, obliques, angle)


def _reflect_oblique(
    italics: list[tuple[float, float]],
    obliques: list[tuple[float, float]],
    angle: float,
) -> tuple[str, float] | tuple[None, None]:
    reflected_oblique = [(-high, -low) for low, high in obliques]
    reflected_italic = [(-high, -low) for low, high in italics]
    if -angle >= 11:
        axis, value = _steep_oblique(reflected_italic, reflected_oblique, -angle)
    else:
        axis, value = _shallow_oblique(reflected_italic, reflected_oblique, -angle)
    if axis is None or value is None:
        return None, None
    return axis, -value


def _normal_style(
    italics: list[tuple[float, float]],
    obliques: list[tuple[float, float]],
) -> tuple[str, float] | tuple[None, None]:
    target = _smallest_at_least(obliques, 0)
    if target is not None:
        return "oblique", target
    target = _smallest_at_least(italics, 0)
    if target is not None:
        return "italic", target
    target = _largest_at_most(obliques, math.nextafter(0.0, -math.inf))
    if target is not None:
        return "oblique", target
    target = _largest_at_most(italics, math.nextafter(0.0, -math.inf))
    if target is not None:
        return "italic", target
    return None, None


def _italic_style(
    italics: list[tuple[float, float]],
    obliques: list[tuple[float, float]],
) -> tuple[str, float] | tuple[None, None]:
    if _interval_contains(italics, 1):
        return "italic", 1.0
    target = _smallest_above(italics, 1)
    if target is None:
        target = _largest_from(italics, math.nextafter(0.0, math.inf), 1)
    if target is not None:
        return "italic", target
    target = _smallest_at_least(obliques, 11)
    if target is None:
        target = _largest_from(obliques, math.nextafter(0.0, math.inf), 11)
    if target is not None:
        return "oblique", target
    target = _largest_at_most(italics, 0)
    if target is not None:
        return "italic", target
    target = _largest_at_most(obliques, 0)
    if target is not None:
        return "oblique", target
    return None, None


def _steep_oblique(
    italics: list[tuple[float, float]],
    obliques: list[tuple[float, float]],
    angle: float,
) -> tuple[str, float] | tuple[None, None]:
    if _interval_contains(obliques, angle):
        return "oblique", angle
    target = _smallest_above(obliques, angle)
    if target is None:
        target = _largest_from(obliques, math.nextafter(0.0, math.inf), angle)
    if target is not None:
        return "oblique", target
    target = _smallest_at_least(italics, 1)
    if target is not None:
        return "italic", target
    target = _largest_from(italics, math.nextafter(0.0, math.inf), 1)
    if target is not None:
        return "italic", target
    target = _largest_at_most(obliques, 0)
    if target is not None:
        return "oblique", target
    target = _largest_at_most(italics, 0)
    if target is not None:
        return "italic", target
    return None, None


def _shallow_oblique(
    italics: list[tuple[float, float]],
    obliques: list[tuple[float, float]],
    angle: float,
) -> tuple[str, float] | tuple[None, None]:
    if _interval_contains(obliques, angle):
        return "oblique", angle
    target = _largest_from(obliques, 0.0, angle) if angle > 0 else None
    if target is None:
        target = _smallest_above(obliques, angle)
    if target is not None:
        return "oblique", target
    target = _largest_from(italics, 0.0, 1.0)
    if target is None:
        target = _smallest_at_least(italics, 1)
    if target is not None:
        return "italic", target
    target = _largest_at_most(obliques, math.nextafter(0.0, -math.inf))
    if target is not None:
        return "oblique", target
    target = _largest_at_most(italics, math.nextafter(0.0, -math.inf))
    if target is not None:
        return "italic", target
    return None, None


def _width_target(spans: list[tuple[float, float]], desired: float) -> float:
    if _interval_contains(spans, desired):
        return desired
    if desired <= 100:
        target = _largest_at_most(spans, desired)
        if target is None:
            target = _smallest_at_least(spans, desired)
    else:
        target = _smallest_at_least(spans, desired)
        if target is None:
            target = _largest_at_most(spans, desired)
    if target is None:
        raise _Invalid("width match failed")
    return target


def _weight_target(spans: list[tuple[float, float]], desired: float) -> float:
    if _interval_contains(spans, desired):
        return desired
    if 400 <= desired <= 500:
        target = _smallest_between(spans, desired, 500)
        if target is None:
            target = _largest_at_most(spans, math.nextafter(desired, -math.inf))
        if target is None:
            target = _smallest_at_least(spans, math.nextafter(500.0, math.inf))
    elif desired < 400:
        target = _largest_at_most(spans, desired)
        if target is None:
            target = _smallest_at_least(spans, desired)
    else:
        target = _smallest_at_least(spans, desired)
        if target is None:
            target = _largest_at_most(spans, desired)
    if target is None:
        raise _Invalid("weight match failed")
    return target


def _interval_contains(spans: list[tuple[float, float]], value: float) -> bool:
    return any(low <= value <= high for low, high in spans)


def _contains(span: tuple[float, float] | None, value: float) -> bool:
    return span is not None and span[0] <= value <= span[1]


def _smallest_at_least(spans: list[tuple[float, float]], limit: float) -> float | None:
    best: float | None = None
    for low, high in spans:
        if high < limit:
            continue
        candidate = max(low, limit)
        if candidate <= high and (best is None or candidate < best):
            best = candidate
    return best


def _smallest_above(spans: list[tuple[float, float]], limit: float) -> float | None:
    return _smallest_at_least(spans, math.nextafter(limit, math.inf))


def _largest_at_most(spans: list[tuple[float, float]], limit: float) -> float | None:
    best: float | None = None
    for low, high in spans:
        if low > limit:
            continue
        candidate = min(high, limit)
        if candidate >= low and (best is None or candidate > best):
            best = candidate
    return best


def _largest_from(spans: list[tuple[float, float]], floor: float, high: float) -> float | None:
    if high <= floor:
        return None
    ceiling = math.nextafter(high, -math.inf)
    best: float | None = None
    for low, span_high in spans:
        upper = min(span_high, ceiling)
        lower = max(low, floor)
        if lower <= upper and (best is None or upper > best):
            best = upper
    return best


def _smallest_between(spans: list[tuple[float, float]], low: float, high: float) -> float | None:
    best: float | None = None
    for start, end in spans:
        candidate = max(start, low)
        if candidate <= end and candidate <= high and (best is None or candidate < best):
            best = candidate
    return best


def _supports(face: _Face, text: str, *, glyphs: bool) -> bool:
    for char in text:
        code = ord(char)
        if not any(start <= code <= end for start, end in face.coverage):
            return False
        if glyphs and face.cmap is not None and code not in face.cmap:
            return False
    return True


def _request(
    families: object,
    weight: object,
    width: object,
    style: object,
    inherited_weight: object,
    generics: object,
) -> _Request:
    names = _families(families)
    requested_weight = _requested_weight(weight, inherited_weight)
    requested_width = _requested_width(width)
    kind, angle = _requested_style(style)
    return _Request(tuple(names), requested_weight, requested_width, kind, angle, _generic_map(generics))


def _requested_weight(weight: object, inherited: object) -> float:
    if isinstance(weight, str):
        token = " ".join(weight.strip().lower().split())
        if token in {"bolder", "lighter"}:
            if inherited is None:
                raise _Invalid("inherited weight is required")
            base = _requested_weight(inherited, None)
            return _relative_weight(base, token)
        if token in _WEIGHTS:
            return _WEIGHTS[token]
    number = _unit_number(weight, "weight")
    if number < 1 or number > 1000:
        raise _Invalid("weight is outside 1 to 1000")
    return number


def _relative_weight(inherited: float, keyword: str) -> float:
    """CSS Fonts 4 relative bolder and lighter chart."""

    if keyword == "bolder":
        if inherited < 350:
            return 400
        if inherited < 550:
            return 700
        if inherited < 900:
            return 900
        return inherited
    if inherited < 100:
        return inherited
    if inherited < 550:
        return 100
    if inherited < 750:
        return 400
    return 700


def _requested_width(width: object) -> float:
    if isinstance(width, str) and " " not in width.strip():
        token = width.strip().lower()
        if token in _WIDTHS:
            return _WIDTHS[token]
        if token.endswith("%"):
            number = _unit_number(token[:-1], "width")
        else:
            number = _unit_number(width, "width")
    else:
        number = _unit_number(width, "width")
    if number <= 0:
        raise _Invalid("width must be positive")
    return number


def _requested_style(style: object) -> tuple[str, float | None]:
    if not isinstance(style, str):
        raise _Invalid("style is invalid")
    match = _STYLE.fullmatch(" ".join(style.strip().lower().split()))
    if match is None:
        raise _Invalid("style is invalid")
    kind = match.group(1)
    if kind != "oblique" and (match.group(2) or match.group(3)):
        raise _Invalid("style is invalid")
    if kind != "oblique":
        return kind, None
    if match.group(3):
        raise _Invalid("style is invalid")
    angle = 14.0 if match.group(2) is None else float(match.group(2))
    if angle < -90 or angle > 90:
        raise _Invalid("angle is outside -90 to 90")
    return "oblique", angle


def _families(value: object) -> list[str]:
    if isinstance(value, str):
        names = _split_families(value)
    elif isinstance(value, (list, tuple)) and not isinstance(value, (str, bytes)):
        names = []
        for item in value:
            if not isinstance(item, str):
                raise _Invalid("family name is invalid")
            names.append(item.strip())
    else:
        raise _Invalid("families must be a list or string")
    if not names or any(name == "" for name in names):
        raise _Invalid("family name is empty")
    return names


def _split_families(text: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    quote = ""
    for char in text:
        if quote:
            if char == quote:
                quote = ""
            else:
                buffer.append(char)
            continue
        if char in "\"'":
            quote = char
            continue
        if char == ",":
            parts.append("".join(buffer).strip())
            buffer = []
            continue
        buffer.append(char)
    if quote:
        raise _Invalid("unclosed family quote")
    parts.append("".join(buffer).strip())
    return parts


def _generic_map(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _Invalid("generics must be a mapping")
    mapped: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str) or not key.strip() or not item.strip():
            raise _Invalid("generics must map family names to family names")
        mapped[key.strip().casefold()] = item.strip()
    return mapped


def _family_key(name: str, generics: dict[str, str]) -> str | None:
    folded = name.strip().casefold()
    if folded in _GENERICS:
        mapped = generics.get(folded)
        if mapped is None:
            return None
        return mapped.strip().casefold()
    return folded


def _library(value: object) -> tuple[_Face, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("faces must be a list")
    return tuple(_face(item, index) for index, item in enumerate(value))


def _face(value: object, index: int) -> _Face:
    if not isinstance(value, dict):
        raise _Invalid(f"face {index} must be a mapping")
    family = value.get("family")
    if not isinstance(family, str) or not family.strip():
        raise _Invalid(f"face {index} family is invalid")
    source = value.get("source", "font-face")
    if source not in {"font-face", "installed"}:
        raise _Invalid(f"face {index} source is invalid")
    available = value.get("available", True)
    if not isinstance(available, bool):
        raise _Invalid(f"face {index} available is invalid")
    identity = value.get("id", f"face-{index}")
    if not isinstance(identity, str) or not identity:
        raise _Invalid(f"face {index} id is invalid")
    kind, italic, oblique = _face_style(value.get("style", "normal"), index)
    coverage, cmap = _coverage(value, index)
    return _Face(
        index,
        identity,
        family.strip(),
        family.strip().casefold(),
        str(source),
        available,
        _span(value.get("weight", 400), _WEIGHTS, "weight", index),
        _span(value.get("width", "normal"), _WIDTHS, "width", index),
        italic,
        oblique,
        kind,
        coverage,
        cmap,
    )


def _face_style(value: object, index: int) -> tuple[str, tuple[float, float] | None, tuple[float, float] | None]:
    if not isinstance(value, str):
        raise _Invalid(f"face {index} style is invalid")
    match = _STYLE.fullmatch(" ".join(value.strip().lower().split()))
    if match is None:
        raise _Invalid(f"face {index} style is invalid")
    kind = match.group(1)
    if kind == "normal":
        if match.group(2) or match.group(3):
            raise _Invalid(f"face {index} style is invalid")
        return "normal", None, (0.0, 0.0)
    if kind == "italic":
        if match.group(2) or match.group(3):
            raise _Invalid(f"face {index} style is invalid")
        return "italic", (1.0, 1.0), None
    start = 14.0 if match.group(2) is None else float(match.group(2))
    end = start if match.group(3) is None else float(match.group(3))
    if start < -90 or start > 90 or end < -90 or end > 90:
        raise _Invalid(f"face {index} angle is outside -90 to 90")
    if start > end:
        start, end = end, start
    return "oblique", None, (start, end)


def _span(value: object, keywords: dict[str, float], name: str, index: int) -> tuple[float, float]:
    try:
        points = _span_points(value, keywords, name)
    except _Invalid as exc:
        raise _Invalid(f"face {index} {exc.reason}") from exc
    if name == "weight" and any(point < 1 or point > 1000 for point in points):
        raise _Invalid(f"face {index} weight is outside 1 to 1000")
    if name == "width" and any(point <= 0 for point in points):
        raise _Invalid(f"face {index} width must be positive")
    low, high = points
    if low > high:
        low, high = high, low
    return low, high


def _span_points(value: object, keywords: dict[str, float], name: str) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and not isinstance(value, (str, bytes)):
        if len(value) != 2:
            raise _Invalid(f"{name} is invalid")
        return _keyword_number(value[0], keywords, name), _keyword_number(value[1], keywords, name)
    if isinstance(value, str):
        parts = value.replace("%", " ").replace(",", " ").split()
        if not parts or len(parts) > 2:
            raise _Invalid(f"{name} is invalid")
        numbers = [_keyword_number(part, keywords, name) for part in parts]
        if len(numbers) == 1:
            return numbers[0], numbers[0]
        return numbers[0], numbers[1]
    number = _keyword_number(value, keywords, name)
    return number, number


def _keyword_number(value: object, keywords: dict[str, float], name: str) -> float:
    if isinstance(value, str):
        token = value.strip().lower().rstrip("%")
        if token in keywords:
            return keywords[token]
        value = token
    return _unit_number(value, name)


def _coverage(
    value: dict[str, object], index: int
) -> tuple[tuple[tuple[int, int], ...], frozenset[int] | None]:
    raw_range = value.get("unicode_range", value.get("unicode-range"))
    coverage = ((0, 0x10FFFF),) if raw_range is None else _unicode_range(raw_range, index)
    raw_characters = value.get("characters")
    if raw_characters is None:
        return coverage, None
    if isinstance(raw_characters, str):
        codes = {ord(char) for char in raw_characters}
    elif isinstance(raw_characters, (list, tuple)) and not isinstance(raw_characters, (str, bytes)):
        codes = set()
        for item in raw_characters:
            if isinstance(item, bool) or not isinstance(item, int):
                raise _Invalid(f"face {index} characters are invalid")
            _scalar(item)
            codes.add(item)
    else:
        raise _Invalid(f"face {index} characters are invalid")
    return coverage, frozenset(codes)


def _unicode_range(value: object, index: int) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, str) or not value.strip():
        raise _Invalid(f"face {index} unicode-range is invalid")
    ranges: list[tuple[int, int]] = []
    for part in value.split(","):
        token = "".join(part.split()).upper()
        if not token.startswith("U+"):
            raise _Invalid(f"face {index} unicode-range is invalid")
        ranges.append(_range_token(token[2:], index))
    return tuple(ranges)


def _range_token(body: str, index: int) -> tuple[int, int]:
    reason = f"face {index} unicode-range is invalid"
    if not body or len(body) > 13:
        raise _Invalid(reason)
    if "-" in body:
        left, right = body.split("-", 1)
        if not _hex(left) or not _hex(right) or len(left) > 6 or len(right) > 6:
            raise _Invalid(reason)
        start, end = int(left, 16), int(right, 16)
    elif "?" in body:
        if body.strip("?") == "" or "?" in body.rstrip("?") or not _hex(body.rstrip("?")):
            raise _Invalid(reason)
        prefix = body.rstrip("?")
        wild = len(body) - len(prefix)
        if len(prefix) + wild > 6:
            raise _Invalid(reason)
        start = int(prefix, 16) << (4 * wild)
        end = start + (16**wild) - 1
    elif _hex(body) and len(body) <= 6:
        start = end = int(body, 16)
    else:
        raise _Invalid(reason)
    if start > end or end > 0x10FFFF:
        raise _Invalid(reason)
    return start, end


def _hex(text: str) -> bool:
    return bool(text) and all(char in "0123456789ABCDEF" for char in text)


def _text(value: object) -> str:
    if isinstance(value, str):
        if value == "":
            raise _Invalid("character is empty")
        for char in value:
            _scalar(ord(char))
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Invalid("character is not a unicode scalar")
    _scalar(value)
    return chr(value)


def _scalar(code: int) -> None:
    if code < 0 or code > 0x10FFFF or 0xD800 <= code <= 0xDFFF:
        raise _Invalid("character is not a unicode scalar")


def _private(code: int) -> bool:
    return (
        0xE000 <= code <= 0xF8FF
        or 0xF0000 <= code <= 0xFFFFD
        or 0x100000 <= code <= 0x10FFFD
    )


def _variation(code: int) -> bool:
    return 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF


def _unit_number(value: object, name: str) -> float:
    if isinstance(value, str):
        token = value.strip()
        if _NUMBER.fullmatch(token) is None:
            raise _Invalid(f"{name} is invalid")
        value = token
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if not math.isfinite(number):
        raise _Invalid(f"{name} is invalid")
    return number


def _segment(face: _Face, raw: str, choice: _Choice, text: str) -> dict[str, object]:
    return {
        "text": text,
        "rendered": text,
        "id": face.id,
        "family": face.family,
        "requested_family": raw,
        "weight": _number(choice.weight),
        "width": _number(choice.width),
        "style": face.kind,
        "angle": _number(choice.style_value) if face.kind == "oblique" else None,
        "variation_ignored": False,
    }


def _blank(text: str) -> dict[str, object]:
    return {
        "text": text,
        "rendered": None,
        "id": None,
        "family": None,
        "requested_family": None,
        "weight": None,
        "width": None,
        "style": None,
        "angle": None,
        "variation_ignored": False,
    }


def _pack(
    segments: list[dict[str, object]],
    request: _Request,
    *,
    unmatched: str = "no face supports the character",
) -> dict[str, object]:
    found = [segment for segment in segments if segment["id"] is not None]
    if found and len(found) == len(segments):
        outcome = "matched"
        reason = None
    elif found:
        outcome = "partial"
        reason = "character split across faces"
    else:
        outcome = "unmatched"
        reason = unmatched
    primary = segments[0] if len(segments) == 1 and outcome == "matched" else None
    style = request.style if request.angle is None else "oblique"
    return {
        "outcome": outcome,
        "reason": reason,
        "id": None if primary is None else primary["id"],
        "family": None if primary is None else primary["family"],
        "requested_family": None if primary is None else primary["requested_family"],
        "weight": None if primary is None else primary["weight"],
        "width": None if primary is None else primary["width"],
        "style": None if primary is None else primary["style"],
        "angle": None if primary is None else primary["angle"],
        "requested_weight": _number(request.weight),
        "requested_width": _number(request.width),
        "requested_style": style,
        "requested_angle": None if request.angle is None else _number(request.angle),
        "rendered": None if primary is None else primary["rendered"],
        "variation_ignored": False if primary is None else primary["variation_ignored"],
        "segments": segments,
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "id": None,
        "family": None,
        "requested_family": None,
        "weight": None,
        "width": None,
        "style": None,
        "angle": None,
        "requested_weight": None,
        "requested_width": None,
        "requested_style": None,
        "requested_angle": None,
        "rendered": None,
        "variation_ignored": False,
        "segments": None,
    }


def _number(value: float) -> int | float:
    if value == math.trunc(value) and abs(value) < 10**12:
        return int(value)
    return value
