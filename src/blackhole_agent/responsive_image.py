"""Choose the image URL and pixel density for an img or picture.

This follows the HTML source-selection steps that a comma-split gets wrong.
A comma inside a URL stays in that URL. A comma after a URL ends that
candidate, so ``hero.jpg, 2x`` is the URL ``hero.jpg`` plus a second URL
``2x``, not a 2x descriptor. A width descriptor becomes a density by dividing
by the sizes length. The earliest density greater than or equal to the
device pixel ratio wins; otherwise the largest density wins. A repeated
density keeps the earlier URL. The img ``src`` is appended only when the
srcset has no width descriptor and no explicit 1x descriptor. A picture
``source`` is used only when it has at least one candidate, its media
matches, and its type is supported. It does not inherit the img ``src``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_WS = frozenset(" \t\n\x0c\r")
_DEFAULT_TYPES = (
    "image/avif",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/svg+xml",
    "image/webp",
)
_MEDIA_TYPES = frozenset(
    {
        "all",
        "aural",
        "braille",
        "embossed",
        "handheld",
        "print",
        "projection",
        "screen",
        "speech",
        "tty",
        "tv",
    }
)
_ABS_UNITS = {
    "px": 1.0,
    "in": 96.0,
    "cm": 96.0 / 2.54,
    "mm": 96.0 / 25.4,
    "q": 96.0 / 101.6,
    "pt": 96.0 / 72.0,
    "pc": 16.0,
}
_FLOAT = re.compile(r"^-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_CSS_NUMBER = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_MIME_TOKEN = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]*\Z")
_RANGE_OP = re.compile(r"\s*(<=|>=|<|>|=)\s*")
_IDENT = re.compile(r"[A-Za-z0-9-]+")


@dataclass(frozen=True)
class _Candidate:
    url: str
    width: int | None
    density: float | None


@dataclass(frozen=True)
class _Env:
    viewport_width: float
    viewport_height: float
    device_pixel_ratio: float
    media_type: str
    root_font_px: float


def select_image(
    src: str = "",
    srcset: str = "",
    sizes: str = "",
    *,
    viewport_width: float = 1000,
    viewport_height: float = 1000,
    device_pixel_ratio: float = 1,
    media_type: str = "screen",
    root_font_px: float = 16,
    sources: Sequence[Mapping[str, object]] | None = None,
    supported_types: Sequence[str] = _DEFAULT_TYPES,
    auto_sizes: bool = False,
    layout_width: float | None = None,
    last_auto_width: float | None = None,
) -> dict[str, object]:
    """Return the selected candidate URL, density, and sizes length.

    ``density`` is ``"inf"`` when a width is divided by a zero source size.
    ``slot`` is ``"source"`` or ``"img"``. ``source_index`` counts only the
    supplied picture sources. An empty result has ``url`` ``""`` and
    ``density`` ``None``.
    """

    if not isinstance(src, str) or not isinstance(srcset, str) or not isinstance(sizes, str):
        raise TypeError("src, srcset, and sizes must be strings")
    if not isinstance(media_type, str) or not isinstance(auto_sizes, bool):
        raise TypeError("media_type must be a string and auto_sizes a bool")
    env = _Env(
        viewport_width=_real("viewport_width", viewport_width),
        viewport_height=_real("viewport_height", viewport_height),
        device_pixel_ratio=_real("device_pixel_ratio", device_pixel_ratio),
        media_type=media_type.strip().lower() or "screen",
        root_font_px=_real("root_font_px", root_font_px, positive=True),
    )
    layout = None if layout_width is None else _real("layout_width", layout_width)
    previous_auto = None if last_auto_width is None else _real("last_auto_width", last_auto_width)
    allowed = _supported(supported_types)
    if sources is not None:
        if isinstance(sources, (str, bytes)) or not isinstance(sources, Sequence):
            raise TypeError("sources must be a sequence of mappings")
        for index, attrs in enumerate(sources):
            if not isinstance(attrs, Mapping):
                raise TypeError("each picture source must be a mapping")
            built = _source_set(
                attrs,
                env,
                allowed,
                auto_sizes=auto_sizes,
                layout_width=layout,
                last_auto_width=previous_auto,
            )
            if built is None:
                continue
            normalized, source_size = built
            chosen = _choose(normalized, env.device_pixel_ratio)
            if chosen is None:
                continue
            return _payload(chosen, source_size, "source", index)
    normalized, source_size = _create_source_set(
        src,
        srcset,
        sizes,
        env,
        auto_sizes=auto_sizes,
        layout_width=layout,
        last_auto_width=previous_auto,
    )
    return _payload(_choose(normalized, env.device_pixel_ratio), source_size, "img", None)


def _real(name: str, value: object, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    number = float(value)
    if not math.isfinite(number) or number < 0 or (positive and number <= 0):
        raise ValueError(f"{name} is out of range")
    return number


def _supported(types: Sequence[str]) -> set[str]:
    if isinstance(types, (str, bytes)) or not isinstance(types, Sequence):
        raise TypeError("supported_types must be a sequence of strings")
    allowed: set[str] = set()
    for item in types:
        if not isinstance(item, str):
            raise TypeError("supported_types must be a sequence of strings")
        allowed.add(item.strip().lower())
    return allowed


def _payload(
    chosen: tuple[str, float] | None,
    source_size: float,
    slot: str,
    index: int | None,
) -> dict[str, object]:
    if chosen is None:
        return {
            "url": "",
            "density": None,
            "source_size": _public_num(source_size),
            "slot": "",
            "source_index": None,
        }
    url, density = chosen
    return {
        "url": url,
        "density": _public_num(density),
        "source_size": _public_num(source_size),
        "slot": slot,
        "source_index": index,
    }


def _public_num(value: float) -> int | float | str:
    if math.isinf(value):
        return "inf"
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value


def _parse_srcset(value: str) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    index = 0
    length = len(value)
    while True:
        while index < length and (value[index] in _WS or value[index] == ","):
            index += 1
        if index >= length:
            return candidates
        start = index
        while index < length and value[index] not in _WS:
            index += 1
        url = value[start:index]
        descriptors: list[str] = []
        if url.endswith(","):
            url = url.rstrip(",")
        else:
            descriptors, index = _descriptors(value, index)
        if url and not _descriptor_error(descriptors):
            width, density = _descriptor_values(descriptors)
            candidates.append(_Candidate(url, width, density))


def _descriptors(value: str, index: int) -> tuple[list[str], int]:
    descriptors: list[str] = []
    current: list[str] = []
    state = "in"
    length = len(value)
    while True:
        if index >= length:
            if current:
                descriptors.append("".join(current))
            return descriptors, index
        char = value[index]
        if state == "in":
            if char in _WS:
                if current:
                    descriptors.append("".join(current))
                    current = []
                state = "after"
                index += 1
                continue
            if char == ",":
                index += 1
                if current:
                    descriptors.append("".join(current))
                return descriptors, index
            if char == "(":
                current.append(char)
                state = "paren"
                index += 1
                continue
            current.append(char)
            index += 1
            continue
        if state == "paren":
            current.append(char)
            index += 1
            if char == ")":
                state = "in"
            continue
        if char in _WS:
            index += 1
            continue
        state = "in"


def _descriptor_error(descriptors: list[str]) -> bool:
    width = False
    density = False
    future_h = False
    error = False
    for descriptor in descriptors:
        kind, number = _classify_descriptor(descriptor)
        if kind == "w":
            if width or density or number == 0:
                error = True
            else:
                width = True
        elif kind == "x":
            if width or density or future_h or number < 0:
                error = True
            else:
                density = True
        elif kind == "h":
            if future_h or density or number == 0:
                error = True
            else:
                future_h = True
        else:
            error = True
    if future_h and not width:
        error = True
    return error


def _descriptor_values(descriptors: list[str]) -> tuple[int | None, float | None]:
    width: int | None = None
    density: float | None = None
    for descriptor in descriptors:
        kind, number = _classify_descriptor(descriptor)
        if kind == "w":
            width = int(number)
        elif kind == "x":
            density = float(number)
    return width, density


def _classify_descriptor(descriptor: str) -> tuple[str, float]:
    if len(descriptor) < 2:
        return "", 0
    suffix = descriptor[-1]
    body = descriptor[:-1]
    if suffix == "w" and re.fullmatch(r"[0-9]+", body):
        return "w", int(body, 10)
    if suffix == "x" and _FLOAT.fullmatch(body):
        return "x", float(body)
    if suffix == "h" and re.fullmatch(r"[0-9]+", body):
        return "h", int(body, 10)
    return "", 0


def _create_source_set(
    src: str,
    srcset: str,
    sizes: str,
    env: _Env,
    *,
    auto_sizes: bool,
    layout_width: float | None,
    last_auto_width: float | None,
) -> tuple[list[tuple[str, float]], float]:
    candidates = _parse_srcset(srcset) if srcset else []
    source_size = _parse_sizes(
        sizes,
        env,
        auto_sizes=auto_sizes,
        layout_width=layout_width,
        last_auto_width=last_auto_width,
    )
    has_width = any(item.width is not None for item in candidates)
    has_one = any(item.density == 1 for item in candidates)
    if src and not has_width and not has_one:
        candidates.append(_Candidate(src, None, None))
    return _normalize(candidates, source_size), source_size


def _source_set(
    attrs: Mapping[str, object],
    env: _Env,
    supported: set[str],
    *,
    auto_sizes: bool,
    layout_width: float | None,
    last_auto_width: float | None,
) -> tuple[list[tuple[str, float]], float] | None:
    if "srcset" not in attrs:
        return None
    raw = attrs.get("srcset")
    if not isinstance(raw, str):
        raise TypeError("source srcset must be a string")
    parsed = _parse_srcset(raw)
    if not parsed:
        return None
    if "media" in attrs:
        media = attrs.get("media")
        if not isinstance(media, str) or not _query_list(media, env):
            return None
    if "type" in attrs:
        mime = attrs.get("type")
        if not isinstance(mime, str) or not _mime_supported(mime, supported):
            return None
    sizes = attrs.get("sizes", "")
    if sizes is None:
        sizes = ""
    if not isinstance(sizes, str):
        raise TypeError("source sizes must be a string")
    source_size = _parse_sizes(
        sizes,
        env,
        auto_sizes=auto_sizes,
        layout_width=layout_width,
        last_auto_width=last_auto_width,
    )
    return _normalize(parsed, source_size), source_size


def _normalize(candidates: list[_Candidate], source_size: float) -> list[tuple[str, float]]:
    normalized: list[tuple[str, float]] = []
    for item in candidates:
        if item.density is not None:
            density = item.density
        elif item.width is not None:
            density = math.inf if source_size == 0 else item.width / source_size
        else:
            density = 1.0
        normalized.append((item.url, density))
    return normalized


def _choose(candidates: list[tuple[str, float]], device_pixel_ratio: float) -> tuple[str, float] | None:
    if not candidates:
        return None
    kept: list[tuple[str, float]] = []
    seen: list[float] = []
    for url, density in candidates:
        if any(_same_density(density, previous) for previous in seen):
            continue
        seen.append(density)
        kept.append((url, density))
    kept.sort(key=lambda item: item[1])
    for item in kept:
        if item[1] >= device_pixel_ratio:
            return item
    return kept[-1]


def _same_density(left: float, right: float) -> bool:
    if math.isinf(left) or math.isinf(right):
        return math.isinf(left) and math.isinf(right)
    return left == right


def _parse_sizes(
    sizes: str,
    env: _Env,
    *,
    auto_sizes: bool,
    layout_width: float | None,
    last_auto_width: float | None,
) -> float:
    if sizes.strip() == "":
        return env.viewport_width
    for entry in _split_commas(sizes):
        components = _components(entry)
        if not components:
            continue
        size = _size_value(components[-1], env)
        if size is None:
            continue
        if size == "auto":
            if auto_sizes and layout_width is not None:
                resolved = layout_width
            elif auto_sizes and last_auto_width is not None:
                resolved = last_auto_width
            else:
                continue
        else:
            resolved = size
        rest = " ".join(components[:-1]).strip()
        if not rest:
            return resolved
        if _condition(rest, env) is True:
            return resolved
    return env.viewport_width


def _size_value(token: str, env: _Env) -> float | str | None:
    if token.lower() == "auto":
        return "auto"
    if token.lower().startswith("calc(") and token.endswith(")") and _wrapped(token[4:]):
        value = _parse_calc(token, env)
    else:
        value = _css_length(token, env, allow_negative=True)
    if value is None or value < 0:
        return None
    return value


def _css_length(token: str, env: _Env, *, allow_negative: bool) -> float | None:
    match = _CSS_NUMBER.match(token.strip())
    if match is None:
        return None
    number = float(match.group(0))
    unit = token.strip()[match.end() :].lower()
    if unit == "":
        value = 0.0 if number == 0 else None
    elif unit == "vw":
        value = env.viewport_width * number / 100.0
    elif unit == "vh":
        value = env.viewport_height * number / 100.0
    elif unit in {"em", "rem"}:
        value = env.root_font_px * number
    elif unit in _ABS_UNITS:
        value = number * _ABS_UNITS[unit]
    else:
        value = None
    if value is None:
        return None
    if not allow_negative and value < 0:
        return None
    return value


def _parse_calc(token: str, env: _Env) -> float | None:
    inner = token.strip()[5:-1].strip()
    parsed = _parse_sum(inner, env)
    if parsed is None or parsed[1] != "length":
        return None
    return parsed[0]


def _parse_sum(text: str, env: _Env) -> tuple[float, str] | None:
    parts = _split_operators(text, {("+",), ("-",)})
    if parts is None:
        return _parse_product(text, env)
    value: float | None = None
    kind = ""
    for operator, piece in parts:
        parsed = _parse_product(piece, env)
        if parsed is None:
            return None
        number, part_kind = parsed
        if value is None:
            if operator == "-":
                number = -number
            value = number
            kind = part_kind
            continue
        if kind != "length" or part_kind != "length":
            return None
        value = value + number if operator == "+" else value - number
    if value is None:
        return None
    return value, kind


def _parse_product(text: str, env: _Env) -> tuple[float, str] | None:
    parts = _split_operators(text, {("*",), ("/",)})
    if parts is None:
        return _parse_atomic(text, env)
    current: tuple[float, str] | None = None
    for operator, piece in parts:
        parsed = _parse_atomic(piece, env)
        if parsed is None:
            return None
        if current is None:
            if operator != "+":
                return None
            current = parsed
            continue
        left, left_kind = current
        right, right_kind = parsed
        if operator == "*":
            if left_kind == "number" and right_kind == "length":
                current = (left * right, "length")
            elif left_kind == "length" and right_kind == "number":
                current = (left * right, "length")
            elif left_kind == "number" and right_kind == "number":
                current = (left * right, "number")
            else:
                return None
        elif right_kind != "number" or right == 0:
            return None
        else:
            current = (left / right, left_kind)
    return current


def _parse_atomic(text: str, env: _Env) -> tuple[float, str] | None:
    token = text.strip()
    if not token:
        return None
    if token.lower().startswith("calc(") and token.endswith(")") and _wrapped(token[4:]):
        value = _parse_calc(token, env)
        if value is None:
            return None
        return value, "length"
    if _wrapped(token):
        return _parse_sum(token[1:-1], env)
    length = _css_length(token, env, allow_negative=True)
    if length is not None:
        return length, "length"
    match = _CSS_NUMBER.fullmatch(token)
    if match is None:
        return None
    return float(match.group(0)), "number"


def _split_operators(text: str, operators: set[tuple[str, ...]]) -> list[tuple[str, str]] | None:
    """Split on top-level calc operators that are surrounded by whitespace.

    The first piece is returned with operator ``+``. ``None`` means the
    operator does not occur, so the caller parses the text as one piece.
    """

    found: list[tuple[int, str]] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and char in {"+", "-", "*", "/"} and (char,) in operators:
            if index > 0 and text[index - 1] in _WS and index + 1 < len(text) and text[index + 1] in _WS:
                found.append((index, char))
        index += 1
    if not found:
        return None
    pieces: list[tuple[str, str]] = []
    start = 0
    previous = "+"
    for position, operator in found:
        pieces.append((previous, text[start:position]))
        previous = operator
        start = position + 1
    pieces.append((previous, text[start:]))
    if any(not piece.strip() for _, piece in pieces):
        return None
    return pieces


def _split_commas(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
            buf.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            buf.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    parts.append("".join(buf))
    return parts


def _components(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
            buf.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            buf.append(char)
        elif char in _WS and depth == 0:
            if buf:
                parts.append("".join(buf))
                buf = []
        else:
            buf.append(char)
    if buf:
        parts.append("".join(buf))
    return parts


def _wrapped(text: str) -> bool:
    if len(text) < 2 or text[0] != "(" or text[-1] != ")":
        return False
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return False
            if depth < 0:
                return False
    return depth == 0


def _query_list(text: str, env: _Env) -> bool:
    if text.strip() == "":
        return True
    saw = False
    for part in _split_commas(text):
        piece = part.strip()
        if not piece:
            continue
        saw = True
        if _query(piece, env):
            return True
    return not saw


def _query(text: str, env: _Env) -> bool:
    body = text.strip()
    negated = False
    if _starts_keyword(body, "not"):
        negated = True
        body = body[3:].strip()
    elif _starts_keyword(body, "only"):
        body = body[4:].strip()
    if not body:
        return False
    if body.startswith("("):
        value = _condition(body, env)
        if value is None:
            return False
        return (not value) if negated else value
    matched = _IDENT.match(body)
    if matched is None:
        return False
    type_name = matched.group(0).lower()
    rest = body[matched.end() :].strip()
    if type_name not in _MEDIA_TYPES:
        type_matches = False
    else:
        type_matches = type_name == "all" or type_name == env.media_type
    if not rest:
        return (not type_matches) if negated else type_matches
    if not _starts_keyword(rest, "and"):
        return False
    condition = _condition(rest[3:].strip(), env)
    if condition is None:
        return False
    value = type_matches and condition
    return (not value) if negated else value


def _condition(text: str, env: _Env) -> bool | None:
    body = text.strip()
    if not body:
        return None
    if _starts_keyword(body, "not"):
        inner = _condition(body[3:].strip(), env)
        if inner is None:
            return None
        return not inner
    and_parts = _split_keyword(body, "and")
    or_parts = _split_keyword(body, "or")
    if and_parts is not None and or_parts is not None:
        return None
    if and_parts is not None:
        values = [_parens(part, env) for part in and_parts]
        if any(item is None for item in values):
            return None
        return all(values)
    if or_parts is not None:
        values = [_parens(part, env) for part in or_parts]
        if any(item is None for item in values):
            return None
        return any(values)
    return _parens(body, env)


def _parens(text: str, env: _Env) -> bool | None:
    body = text.strip()
    if not _wrapped(body):
        return None
    inner = body[1:-1].strip()
    if not inner:
        return None
    if inner.startswith("(") or _starts_keyword(inner, "not") or _split_keyword(inner, "and") or _split_keyword(inner, "or"):
        return _condition(inner, env)
    return _feature(inner, env)


def _feature(body: str, env: _Env) -> bool | None:
    if any(operator in body for operator in ("<=", ">=", "<", ">", "=")):
        return _range(body, env)
    if ":" not in body:
        name = body.strip().lower()
        if name == "width":
            return env.viewport_width > 0
        if name == "height":
            return env.viewport_height > 0
        if name == "orientation":
            return True
        return False
    name, raw_value = body.split(":", 1)
    name = name.strip().lower()
    raw_value = raw_value.strip()
    if name in {"width", "height", "min-width", "max-width", "min-height", "max-height"}:
        length = _css_length(raw_value, env, allow_negative=False)
        if length is None:
            return None
        dimension = env.viewport_width if "width" in name else env.viewport_height
        if name.startswith("min-"):
            return dimension >= length
        if name.startswith("max-"):
            return dimension <= length
        return dimension == length
    if name == "orientation":
        wanted = raw_value.lower()
        portrait = env.viewport_height >= env.viewport_width
        if wanted == "portrait":
            return portrait
        if wanted == "landscape":
            return not portrait
        return False
    return False


def _range(body: str, env: _Env) -> bool | None:
    parts = _RANGE_OP.split(body.strip())
    if len(parts) == 3:
        return _compare_ends(parts[0], parts[1], parts[2], env)
    if len(parts) == 5:
        left = _compare_ends(parts[0], parts[1], parts[2], env)
        right = _compare_ends(parts[2], parts[3], parts[4], env)
        if left is None or right is None:
            return None
        return left and right
    return None


def _compare_ends(left: str, operator: str, right: str, env: _Env) -> bool | None:
    left_name = left.strip().lower()
    right_name = right.strip().lower()
    if left_name in {"width", "height"} and right_name not in {"width", "height"}:
        length = _css_length(right.strip(), env, allow_negative=False)
        dimension = env.viewport_width if left_name == "width" else env.viewport_height
        if length is None:
            return None
        return _apply_op(dimension, operator, length)
    if right_name in {"width", "height"} and left_name not in {"width", "height"}:
        length = _css_length(left.strip(), env, allow_negative=False)
        dimension = env.viewport_width if right_name == "width" else env.viewport_height
        if length is None:
            return None
        return _apply_op(length, operator, dimension)
    return None


def _apply_op(left: float, operator: str, right: float) -> bool:
    if operator == "<":
        return left < right
    if operator == ">":
        return left > right
    if operator == "<=":
        return left <= right
    if operator == ">=":
        return left >= right
    return left == right


def _starts_keyword(text: str, keyword: str) -> bool:
    if not text.lower().startswith(keyword):
        return False
    if len(text) == len(keyword):
        return True
    return text[len(keyword)] in _WS or text[len(keyword)] == "("


def _split_keyword(text: str, keyword: str) -> list[str] | None:
    lower = text.lower()
    depth = 0
    start = 0
    parts: list[str] = []
    index = 0
    found = False
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif (
            depth == 0
            and index > 0
            and text[index - 1] in _WS
            and lower.startswith(keyword, index)
            and _keyword_ends(text, index + len(keyword))
        ):
            parts.append(text[start:index].strip())
            found = True
            index += len(keyword)
            while index < len(text) and text[index] in _WS:
                index += 1
            start = index
            continue
        index += 1
    if not found:
        return None
    parts.append(text[start:].strip())
    if any(not part for part in parts):
        return None
    return parts


def _keyword_ends(text: str, index: int) -> bool:
    return index >= len(text) or text[index] in _WS or text[index] == "("


def _mime_supported(value: str, supported: set[str]) -> bool:
    essence = value.split(";", 1)[0].strip().lower()
    if "/" not in essence or any(char in essence for char in _WS):
        return False
    type_name, subtype = essence.split("/", 1)
    if not _MIME_TOKEN.fullmatch(type_name) or not _MIME_TOKEN.fullmatch(subtype):
        return False
    return essence in supported
