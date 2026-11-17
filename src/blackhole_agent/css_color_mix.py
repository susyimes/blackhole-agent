"""Mix CSS colors with color-mix().

The omitted interpolation space is Oklab. Percentages are normalized with
forced normalization: a sum below 100% becomes an alpha multiplier applied
after un-premultiplication, and two zero percentages still blend halfway
before that alpha is cleared. Channels are premultiplied, a missing
component is copied from the other color, and a powerless hue is dropped
only when a conversion produced it. Hue methods follow the shorter, longer,
increasing, and decreasing arcs.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_POLAR = frozenset({"hsl", "hwb", "lch", "oklch"})
_SPACES = frozenset(
    {
        "srgb",
        "srgb-linear",
        "hsl",
        "hwb",
        "lab",
        "lch",
        "oklab",
        "oklch",
        "xyz-d65",
        "xyz-d50",
    }
)
_HUE_INDEX = {"hsl": 0, "hwb": 0, "lch": 2, "oklch": 2}
_CATEGORIES = {
    "srgb": ("red", "green", "blue"),
    "srgb-linear": ("red", "green", "blue"),
    "xyz-d65": ("red", "green", "blue"),
    "xyz-d50": ("red", "green", "blue"),
    "hsl": ("hue", "colorfulness", "lightness"),
    "hwb": ("hue", None, None),
    "lab": ("lightness", "opponent-a", "opponent-b"),
    "lch": ("lightness", "colorfulness", "hue"),
    "oklab": ("lightness", "opponent-a", "opponent-b"),
    "oklch": ("lightness", "colorfulness", "hue"),
}
_NAMED = {
    "aqua": (0, 255, 255),
    "black": (0, 0, 0),
    "blue": (0, 0, 255),
    "cyan": (0, 255, 255),
    "fuchsia": (255, 0, 255),
    "gray": (128, 128, 128),
    "green": (0, 128, 0),
    "grey": (128, 128, 128),
    "lime": (0, 255, 0),
    "magenta": (255, 0, 255),
    "maroon": (128, 0, 0),
    "navy": (0, 0, 128),
    "olive": (128, 128, 0),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "red": (255, 0, 0),
    "silver": (192, 192, 192),
    "teal": (0, 128, 128),
    "white": (255, 255, 255),
    "yellow": (255, 255, 0),
}
_SRGB_TO_XYZ = (
    (506752 / 1228815, 87881 / 245763, 12673 / 70218),
    (87098 / 409605, 175762 / 245763, 12673 / 175545),
    (7918 / 409605, 87881 / 737289, 1001167 / 1053270),
)
_XYZ_TO_SRGB = (
    (12831 / 3959, -329 / 214, -1974 / 3959),
    (-851781 / 878810, 1648619 / 878810, 36519 / 878810),
    (705 / 12673, -2585 / 12673, 705 / 667),
)
_XYZ_TO_LMS = (
    (0.8190224379967030, 0.3619062600528904, -0.1288737815209879),
    (0.0329836539323885, 0.9292868615863434, 0.0361446663506424),
    (0.0481771893596242, 0.2642395317527308, 0.6335478284694309),
)
_LMS_TO_OKLAB = (
    (0.2104542683093140, 0.7936177747023054, -0.0040720430116193),
    (1.9779985324311684, -2.4285922420485799, 0.4505937096174110),
    (0.0259040424655478, 0.7827717124575296, -0.8086757549230774),
)
_OKLAB_TO_LMS = (
    (1.0, 0.3963377773761749, 0.2158037573099136),
    (1.0, -0.1055613458156586, -0.0638541728258133),
    (1.0, -0.0894841775298119, -1.2914855480194092),
)
_LMS_TO_XYZ = (
    (1.2268798758459243, -0.5578149944602171, 0.2813910456659647),
    (-0.0405757452148008, 1.1122868032803170, -0.0717110580655164),
    (-0.0763729366746601, -0.4214933324022432, 1.5869240198367816),
)
_D65_TO_D50 = (
    (1.0479297925449969, 0.022946870601609652, -0.05019226628920524),
    (0.02962780877005599, 0.9904344267538799, -0.017073799063418826),
    (-0.009243040646204504, 0.015055191490298152, 0.7518742814281371),
)
_D50_TO_D65 = (
    (0.955473421488075, -0.02309845494876471, 0.06325924320057072),
    (-0.0283697093338637, 1.0099953980813041, -0.021041441191917323),
    (0.012314014864481998, -0.020507649298898964, 1.330365926242124),
)
_LAB_EPSILON = 216 / 24389
_LAB_KAPPA = 24389 / 27
_CALL = re.compile(r"\A([A-Za-z][A-Za-z0-9-]*)\((.*)\)\Z", re.DOTALL)
_PERCENT = re.compile(r"\A[+-]?(?:\d+(?:\.\d*)?|\.\d+)%\Z")


class _Invalid(Exception):
    """The expression is not a color-mix this mixer accepts."""


@dataclass
class _Color:
    space: str
    channels: list[float | None]
    alpha: float | None


def _white(x_chroma: float, y_chroma: float) -> tuple[float, float, float]:
    return (x_chroma / y_chroma, 1.0, (1.0 - x_chroma - y_chroma) / y_chroma)


_D50 = _white(0.3457, 0.3585)


def mix_color(expression: str) -> dict[str, object]:
    """Return the mixed color for one color-mix() expression.

    ``outcome`` is ``mixed`` or ``invalid``. ``components`` are the three
    channels in the interpolation space, with None for a channel both
    inputs left missing. ``alpha`` is un-premultiplied and then scaled by
    the leftover percentage.
    """

    if not isinstance(expression, str):
        raise TypeError("color-mix expression must be a string")
    try:
        space, hue_method, items = _parse_mix(expression.strip())
        channels, alpha = _mix_items(items, space, hue_method)
    except (ValueError, _Invalid):
        return _invalid()
    return {
        "outcome": "mixed",
        "space": space,
        "hue_method": hue_method if space in _POLAR else "",
        "components": channels,
        "alpha": alpha,
    }


def _invalid() -> dict[str, object]:
    return {
        "outcome": "invalid",
        "space": "",
        "hue_method": "",
        "components": [],
        "alpha": None,
    }


def _parse_mix(expression: str) -> tuple[str, str, list[tuple[_Color, float | None]]]:
    if len(expression) < 11 or not expression.lower().startswith("color-mix(") or expression[-1] != ")":
        raise _Invalid
    body = expression[len("color-mix(") : -1].strip()
    if not body:
        raise _Invalid
    space = "oklab"
    hue_method = "shorter"
    if _starts_keyword(body, "in"):
        space, hue_method, body = _parse_method(body[2:].lstrip())
    parts = _split_top(body, ",")
    if not parts:
        raise _Invalid
    items: list[tuple[_Color, float | None]] = []
    for part in parts:
        color_text, percent = _split_percent(part)
        items.append((_parse_color(color_text), percent))
    return space, hue_method, items


def _starts_keyword(text: str, word: str) -> bool:
    if not text.lower().startswith(word):
        return False
    return len(text) == len(word) or not (text[len(word)].isalnum() or text[len(word)] == "-")


def _parse_method(body: str) -> tuple[str, str, str]:
    comma = _top_index(body, ",")
    if comma < 0:
        raise _Invalid
    prelude = body[:comma].strip()
    rest = body[comma + 1 :]
    tokens = prelude.split()
    if not tokens:
        raise _Invalid
    space = tokens[0].lower()
    if space == "xyz":
        space = "xyz-d65"
    if space not in _SPACES:
        raise _Invalid
    hue_method = "shorter"
    if len(tokens) == 1:
        return space, hue_method, rest
    if len(tokens) != 3 or tokens[2].lower() != "hue":
        raise _Invalid
    hue_method = tokens[1].lower()
    if hue_method not in {"shorter", "longer", "increasing", "decreasing"} or space not in _POLAR:
        raise _Invalid
    return space, hue_method, rest


def _split_percent(item: str) -> tuple[str, float | None]:
    tokens = _depth_tokens(item)
    if not tokens:
        raise _Invalid
    found = [index for index, token in enumerate(tokens) if _PERCENT.fullmatch(token)]
    if not found:
        return " ".join(tokens), None
    if len(found) != 1 or found[0] not in {0, len(tokens) - 1}:
        raise _Invalid
    index = found[0]
    percent = float(tokens[index][:-1]) / 100
    if not math.isfinite(percent) or percent < 0 or percent > 1:
        raise _Invalid
    color_tokens = tokens[:index] + tokens[index + 1 :]
    if not color_tokens:
        raise _Invalid
    return " ".join(color_tokens), percent


def _parse_color(text: str) -> _Color:
    raw = text.strip()
    lowered = raw.lower()
    if lowered == "transparent":
        return _Color("srgb", [0.0, 0.0, 0.0], 0.0)
    if lowered.startswith("color-mix("):
        mixed = mix_color(raw)
        if mixed["outcome"] != "mixed" or not isinstance(mixed["space"], str):
            raise _Invalid
        channels = mixed["components"]
        if not isinstance(channels, list) or len(channels) != 3:
            raise _Invalid
        alpha = mixed["alpha"]
        return _Color(mixed["space"], list(channels), alpha if alpha is None or isinstance(alpha, float) else None)
    if raw.startswith("#"):
        return _parse_hex(raw)
    if lowered in _NAMED:
        red, green, blue = _NAMED[lowered]
        return _Color("srgb", [red / 255, green / 255, blue / 255], 1.0)
    matched = _CALL.fullmatch(raw)
    if matched is None:
        raise _Invalid
    return _parse_call(matched.group(1).lower(), matched.group(2))


def _parse_hex(text: str) -> _Color:
    digits = text[1:]
    if len(digits) not in {3, 4, 6, 8} or any(char not in "0123456789abcdefABCDEF" for char in digits):
        raise _Invalid
    if len(digits) <= 4:
        digits = "".join(char * 2 for char in digits)
    channels = [int(digits[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
    return _Color("srgb", channels, alpha)


def _parse_call(name: str, body: str) -> _Color:
    if name == "color":
        return _parse_explicit(body)
    if name in {"rgb", "rgba"}:
        channels, alpha = _arguments(body)
        return _Color("srgb", [_rgb_channel(piece) for piece in channels], _alpha(alpha))
    if name in {"hsl", "hsla"}:
        channels, alpha = _arguments(body)
        return _Color(
            "hsl",
            [_hue(channels[0]), _scaled(channels[1], 100), _scaled(channels[2], 100)],
            _alpha(alpha),
        )
    if name == "hwb":
        channels, alpha = _arguments(body)
        return _Color(
            "hwb",
            [_hue(channels[0]), _scaled(channels[1], 100), _scaled(channels[2], 100)],
            _alpha(alpha),
        )
    if name == "lab":
        channels, alpha = _arguments(body)
        return _Color(
            "lab",
            [_scaled(channels[0], 100), _scaled(channels[1], 125), _scaled(channels[2], 125)],
            _alpha(alpha),
        )
    if name == "lch":
        channels, alpha = _arguments(body)
        return _Color(
            "lch",
            [_scaled(channels[0], 100), _scaled(channels[1], 150), _hue(channels[2])],
            _alpha(alpha),
        )
    if name == "oklab":
        channels, alpha = _arguments(body)
        return _Color(
            "oklab",
            [_scaled(channels[0], 1), _scaled(channels[1], 0.4), _scaled(channels[2], 0.4)],
            _alpha(alpha),
        )
    if name == "oklch":
        channels, alpha = _arguments(body)
        return _Color(
            "oklch",
            [_scaled(channels[0], 1), _scaled(channels[1], 0.4), _hue(channels[2])],
            _alpha(alpha),
        )
    raise _Invalid


def _parse_explicit(body: str) -> _Color:
    slash = _top_index(body, "/")
    alpha_text = None
    main = body
    if slash >= 0:
        main = body[:slash]
        alpha_text = body[slash + 1 :]
    tokens = main.split()
    if len(tokens) != 4:
        raise _Invalid
    space = tokens[0].lower()
    if space == "xyz":
        space = "xyz-d65"
    if space not in {"srgb", "srgb-linear", "xyz-d65", "xyz-d50"}:
        raise _Invalid
    scale = 1.0
    return _Color(space, [_scaled(token, scale) for token in tokens[1:]], _alpha(alpha_text))


def _arguments(body: str) -> tuple[list[str], str | None]:
    if _top_index(body, ",") >= 0:
        parts = _split_top(body, ",")
        if len(parts) == 4:
            return parts[:3], parts[3]
        if len(parts) == 3:
            return parts, None
        raise _Invalid
    slash = _top_index(body, "/")
    alpha = None
    main = body
    if slash >= 0:
        main = body[:slash]
        alpha = body[slash + 1 :]
    parts = main.split()
    if len(parts) != 3:
        raise _Invalid
    return parts, alpha


def _rgb_channel(token: str) -> float | None:
    if token.lower() == "none":
        return None
    if token.endswith("%"):
        return _number(token[:-1]) / 100
    return _number(token) / 255


def _scaled(token: str, percent_of: float) -> float | None:
    if token.lower() == "none":
        return None
    if token.endswith("%"):
        return _number(token[:-1]) / 100 * percent_of
    return _number(token)


def _hue(token: str) -> float | None:
    if token.lower() == "none":
        return None
    lower = token.lower()
    for suffix, scale in (("deg", 1.0), ("turn", 360.0), ("rad", 180 / math.pi), ("grad", 0.9)):
        if lower.endswith(suffix) and lower != suffix:
            return _number(lower[: -len(suffix)]) * scale
    return _number(lower)


def _alpha(token: str | None) -> float | None:
    if token is None:
        return 1.0
    text = token.strip()
    if not text:
        raise _Invalid
    if text.lower() == "none":
        return None
    value = _number(text[:-1]) / 100 if text.endswith("%") else _number(text)
    return value


def _number(token: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise _Invalid from exc
    if not math.isfinite(value):
        raise _Invalid
    return value


def _mix_items(
    items: list[tuple[_Color, float | None]],
    space: str,
    hue_method: str,
) -> tuple[list[float | None], float | None]:
    percents, leftover = _normalize([percent for _, percent in items])
    alpha_multiplier = 1 - leftover
    stack = [(color, percent) for (color, _), percent in zip(items, percents, strict=True)]
    stack.reverse()
    if len(stack) == 1:
        color, _percent = stack[0]
        converted = _convert(color, space)
        return converted.channels, _scale_alpha(converted.alpha, alpha_multiplier)
    while len(stack) >= 2:
        left, left_percent = stack.pop()
        right, right_percent = stack.pop()
        combined = left_percent + right_percent
        progress = 0.5 if combined == 0 else right_percent / combined
        channels, alpha = _interpolate(left, right, space, progress, hue_method)
        stack.append((_Color(space, channels, alpha), combined))
    color, _percent = stack[0]
    return color.channels, _scale_alpha(color.alpha, alpha_multiplier)


def _normalize(raw: list[float | None]) -> tuple[list[float], float]:
    specified = [percent for percent in raw if percent is not None]
    fill_sum = 0.0 if not specified else min(1.0, sum(specified))
    omitted = sum(percent is None for percent in raw)
    percents = [percent if percent is not None else (1 - fill_sum) / omitted for percent in raw]
    total = sum(percents)
    leftover = 1 - total if total < 1 else 0.0
    if total > 0:
        percents = [percent / total for percent in percents]
    return percents, leftover


def _scale_alpha(alpha: float | None, multiplier: float) -> float | None:
    if alpha is None:
        return None
    return alpha * multiplier


def _interpolate(
    left: _Color,
    right: _Color,
    space: str,
    progress: float,
    hue_method: str,
) -> tuple[list[float | None], float | None]:
    first = _convert(left, space)
    second = _convert(right, space)
    pairs = [_fill(one, other) for one, other in zip(first.channels, second.channels, strict=True)]
    alpha_pair = _fill(first.alpha, second.alpha)
    hue_index = _HUE_INDEX.get(space)
    prem_left = [
        _premultiply(value, alpha_pair[0], index == hue_index) for index, value in enumerate(one for one, _ in pairs)
    ]
    prem_right = [
        _premultiply(value, alpha_pair[1], index == hue_index)
        for index, value in enumerate(other for _, other in pairs)
    ]
    if hue_index is not None and prem_left[hue_index] is not None and prem_right[hue_index] is not None:
        prem_left[hue_index], prem_right[hue_index] = _fix_hue(
            prem_left[hue_index],
            prem_right[hue_index],
            hue_method,
        )
    mixed = [_lerp(one, other, progress) for one, other in zip(prem_left, prem_right, strict=True)]
    alpha = _lerp(alpha_pair[0], alpha_pair[1], progress)
    result = [_unpremultiply(value, alpha, index == hue_index) for index, value in enumerate(mixed)]
    if hue_index is not None and result[hue_index] is not None:
        result[hue_index] = result[hue_index] % 360
    return result, alpha


def _fill(left: float | None, right: float | None) -> tuple[float | None, float | None]:
    if left is None and right is not None:
        return right, right
    if right is None and left is not None:
        return left, left
    return left, right


def _premultiply(component: float | None, alpha: float | None, hue: bool) -> float | None:
    if alpha is None or hue or component is None:
        return component
    return component * alpha


def _unpremultiply(component: float | None, alpha: float | None, hue: bool) -> float | None:
    if alpha is None or alpha == 0 or hue or component is None:
        return component
    return component / alpha


def _lerp(left: float | None, right: float | None, progress: float) -> float | None:
    if left is None or right is None:
        return None
    return left + (right - left) * progress


def _fix_hue(first: float, second: float, method: str) -> tuple[float, float]:
    start = first % 360
    end = second % 360
    if method == "shorter":
        if end - start > 180:
            start += 360
        elif end - start < -180:
            end += 360
    elif method == "longer":
        difference = end - start
        if 0 < difference < 180:
            start += 360
        elif -180 < difference <= 0:
            end += 360
    elif method == "increasing":
        if end < start:
            end += 360
    elif method == "decreasing" and start < end:
        start += 360
    return start, end


def _convert(color: _Color, space: str) -> _Color:
    if color.space == space:
        return _Color(space, list(color.channels), color.alpha)
    carried = _carried(color.space, space, color.channels)
    numeric = tuple(0.0 if channel is None else channel for channel in color.channels)
    converted = list(_from_xyz(space, _to_xyz(color.space, numeric)))
    for index in carried:
        converted[index] = None
    _powerless(space, converted)
    return _Color(space, converted, color.alpha)


def _carried(source: str, dest: str, channels: list[float | None]) -> set[int]:
    source_cats = _CATEGORIES[source]
    dest_cats = _CATEGORIES[dest]
    dest_of = {}
    for index, category in enumerate(dest_cats):
        if category is not None:
            dest_of.setdefault(category, []).append(index)
    carried: set[int] = set()
    source_known = {category for category in source_cats if category is not None}
    dest_known = {category for category in dest_cats if category is not None}
    for index, category in enumerate(source_cats):
        if category is not None and channels[index] is None and category in dest_of:
            carried.update(dest_of[category])
    source_left = [
        index for index, category in enumerate(source_cats) if category is None or category not in dest_known
    ]
    dest_left = [index for index, category in enumerate(dest_cats) if category is None or category not in source_known]
    if source_left and all(channels[index] is None for index in source_left):
        carried.update(dest_left)
    return carried


def _powerless(space: str, channels: list[float | None]) -> None:
    if space == "hsl":
        saturation = channels[1]
        if saturation is not None and saturation <= 0.001:
            channels[0] = None
            if saturation > 0:
                channels[1] = 0.0
    elif space == "hwb":
        white, black = channels[1], channels[2]
        if white is not None and black is not None and white + black >= 99.999:
            channels[0] = None
    elif space == "lch":
        _drop_hue(channels, 0.0015)
    elif space == "oklch":
        _drop_hue(channels, 0.000004)


def _drop_hue(channels: list[float | None], epsilon: float) -> None:
    chroma = channels[1]
    if chroma is not None and chroma <= epsilon:
        channels[2] = None
        if chroma > 0:
            channels[1] = 0.0


def _to_xyz(space: str, channels: tuple[float, float, float]) -> tuple[float, float, float]:
    if space == "xyz-d65":
        return channels
    if space == "xyz-d50":
        return _multiply(_D50_TO_D65, channels)
    if space == "srgb-linear":
        return _multiply(_SRGB_TO_XYZ, channels)
    if space == "srgb":
        return _multiply(_SRGB_TO_XYZ, tuple(_linear_srgb(channel) for channel in channels))
    if space == "hsl":
        return _to_xyz("srgb", _hsl_to_srgb(channels))
    if space == "hwb":
        return _to_xyz("srgb", _hwb_to_srgb(channels))
    if space == "lab":
        return _multiply(_D50_TO_D65, _lab_to_xyz(channels))
    if space == "lch":
        return _to_xyz("lab", _lch_to_lab(channels))
    if space == "oklab":
        return _xyz_from_oklab(channels)
    if space == "oklch":
        return _to_xyz("oklab", _lch_to_lab(channels))
    raise _Invalid


def _from_xyz(space: str, xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    if space == "xyz-d65":
        return xyz
    if space == "xyz-d50":
        return _multiply(_D65_TO_D50, xyz)
    if space == "srgb-linear":
        return _multiply(_XYZ_TO_SRGB, xyz)
    if space == "srgb":
        linear = _multiply(_XYZ_TO_SRGB, xyz)
        return tuple(_gamma_srgb(channel) for channel in linear)
    if space == "hsl":
        return _srgb_to_hsl(_from_xyz("srgb", xyz))
    if space == "hwb":
        return _srgb_to_hwb(_from_xyz("srgb", xyz))
    if space == "lab":
        return _xyz_to_lab(_multiply(_D65_TO_D50, xyz))
    if space == "lch":
        return _lab_to_lch(_from_xyz("lab", xyz))
    if space == "oklab":
        return _oklab_from_xyz(xyz)
    if space == "oklch":
        return _lab_to_lch(_from_xyz("oklab", xyz))
    raise _Invalid


def _multiply(
    matrix: tuple[tuple[float, float, float], ...], vector: tuple[float, float, float]
) -> tuple[float, float, float]:
    return tuple(sum(matrix[row][column] * vector[column] for column in range(3)) for row in range(3))


def _linear_srgb(value: float) -> float:
    sign = -1.0 if value < 0 else 1.0
    magnitude = abs(value)
    if magnitude <= 0.04045:
        return sign * magnitude / 12.92
    return sign * ((magnitude + 0.055) / 1.055) ** 2.4


def _gamma_srgb(value: float) -> float:
    sign = -1.0 if value < 0 else 1.0
    magnitude = abs(value)
    if magnitude <= 0.0031308:
        return sign * 12.92 * magnitude
    return sign * (1.055 * (magnitude ** (1 / 2.4)) - 0.055)


def _cbrt(value: float) -> float:
    if value < 0:
        return -((-value) ** (1 / 3))
    return value ** (1 / 3)


def _lab_f(value: float) -> float:
    if value > _LAB_EPSILON:
        return _cbrt(value)
    return (_LAB_KAPPA * value + 16) / 116


def _lab_finv(value: float) -> float:
    cubed = value**3
    if cubed > _LAB_EPSILON:
        return cubed
    return (116 * value - 16) / _LAB_KAPPA


def _xyz_to_lab(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    scaled = [_lab_f(xyz[index] / _D50[index]) for index in range(3)]
    return (116 * scaled[1] - 16, 500 * (scaled[0] - scaled[1]), 200 * (scaled[1] - scaled[2]))


def _lab_to_xyz(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    lightness, opponent_a, opponent_b = lab
    f1 = (lightness + 16) / 116
    factors = (_lab_finv(opponent_a / 500 + f1), _lab_finv(f1), _lab_finv(f1 - opponent_b / 200))
    return tuple(factors[index] * _D50[index] for index in range(3))


def _lab_to_lch(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    lightness, opponent_a, opponent_b = lab
    chroma = math.hypot(opponent_a, opponent_b)
    hue = math.degrees(math.atan2(opponent_b, opponent_a)) % 360
    return (lightness, chroma, hue)


def _lch_to_lab(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    lightness, chroma, hue = lch
    radians = math.radians(hue)
    return (lightness, chroma * math.cos(radians), chroma * math.sin(radians))


def _oklab_from_xyz(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    rooted = tuple(_cbrt(channel) for channel in _multiply(_XYZ_TO_LMS, xyz))
    return _multiply(_LMS_TO_OKLAB, rooted)


def _xyz_from_oklab(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    lms = _multiply(_OKLAB_TO_LMS, lab)
    return _multiply(_LMS_TO_XYZ, tuple(channel**3 for channel in lms))


def _hsl_to_srgb(channels: tuple[float, float, float]) -> tuple[float, float, float]:
    hue, saturation, lightness = channels
    sat = saturation / 100
    light = lightness / 100
    if sat == 0:
        return (light, light, light)

    def channel(offset: float) -> float:
        amount = (hue / 360 + offset) % 1
        if amount < 1 / 6:
            return low + (high - low) * 6 * amount
        if amount < 1 / 2:
            return high
        if amount < 2 / 3:
            return low + (high - low) * (2 / 3 - amount) * 6
        return low

    high = light * (1 + sat) if light < 0.5 else light + sat - light * sat
    low = 2 * light - high
    return (channel(1 / 3), channel(0), channel(-1 / 3))


def _srgb_to_hsl(channels: tuple[float, float, float]) -> tuple[float, float, float]:
    red, green, blue = channels
    high = max(channels)
    low = min(channels)
    lightness = (high + low) / 2
    if high == low:
        return (0.0, 0.0, lightness * 100)
    delta = high - low
    saturation = delta / (1 - abs(2 * lightness - 1))
    if high == red:
        hue = ((green - blue) / delta) % 6
    elif high == green:
        hue = (blue - red) / delta + 2
    else:
        hue = (red - green) / delta + 4
    return (hue * 60 % 360, saturation * 100, lightness * 100)


def _hwb_to_srgb(channels: tuple[float, float, float]) -> tuple[float, float, float]:
    hue, white, black = channels
    whiteness = white / 100
    blackness = black / 100
    if whiteness + blackness >= 1:
        gray = whiteness / (whiteness + blackness) if whiteness + blackness else 0.0
        return (gray, gray, gray)
    red, green, blue = _hsl_to_srgb((hue, 100.0, 50.0))
    scale = 1 - whiteness - blackness
    return (red * scale + whiteness, green * scale + whiteness, blue * scale + whiteness)


def _srgb_to_hwb(channels: tuple[float, float, float]) -> tuple[float, float, float]:
    hue, _saturation, _lightness = _srgb_to_hsl(channels)
    return (hue, min(channels) * 100, (1 - max(channels)) * 100)


def _depth_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    buffer: list[str] = []
    depth = 0
    for char in text.strip():
        if char == "(":
            depth += 1
            buffer.append(char)
        elif char == ")":
            if depth == 0:
                raise _Invalid
            depth -= 1
            buffer.append(char)
        elif char.isspace() and depth == 0:
            if buffer:
                tokens.append("".join(buffer))
                buffer = []
        else:
            buffer.append(char)
    if depth != 0:
        raise _Invalid
    if buffer:
        tokens.append("".join(buffer))
    return tokens


def _top_index(text: str, mark: str) -> int:
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise _Invalid
        elif char == mark and depth == 0:
            return index
    if depth != 0:
        raise _Invalid
    return -1


def _split_top(text: str, mark: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
            buffer.append(char)
        elif char == ")":
            if depth == 0:
                raise _Invalid
            depth -= 1
            buffer.append(char)
        elif char == mark and depth == 0:
            parts.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
    if depth != 0:
        raise _Invalid
    tail = "".join(buffer).strip()
    if tail:
        parts.append(tail)
    if not parts or any(not part for part in parts):
        raise _Invalid
    return parts
