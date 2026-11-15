"""Parse and serialize HTTP structured field values (RFC 9651).

A field is an item, a list, or a dictionary of typed bare values with
ordered parameters. A dictionary member or parameter with no value is
boolean true. Integers and dates accept at most 15 digits, including
leading zeros. Display strings percent-decode lowercase UTF-8. The
serializer writes the canonical text for a value this parser produced.
"""

from __future__ import annotations

import base64
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Sequence

_KINDS = frozenset({"item", "list", "dictionary"})
_KEY_EXTRA = frozenset("0123456789_-.*")
_TOKEN_EXTRA = frozenset("!#$%&'*+-.^_`|~0123456789:/")
_STRING_BYTES = frozenset(bytes((*range(0x20, 0x22), *range(0x23, 0x5C), *range(0x5D, 0x7F))))
_DISPLAY_RAW = frozenset(bytes((*range(0x20, 0x22), *range(0x23, 0x25), *range(0x26, 0x7F))))
_HEX = frozenset("0123456789abcdef")
_B64 = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


class StructuredFieldError(ValueError):
    """The field is not a valid structured field value of the requested kind."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_structured_field(value: str | Sequence[str], kind: str) -> object:
    """Parse one field into the structured-field data model.

    ``kind`` is ``item``, ``list``, or ``dictionary``. Several field lines
    combine with a comma for lists and dictionaries. An item that arrives
    on more than one line fails. Decimals are ``Decimal`` values. Tokens,
    byte sequences, dates, and display strings keep a ``__type`` tag.
    """

    field_kind = _kind(kind)
    lines = _lines(value)
    if field_kind == "item":
        if len(lines) != 1:
            _fail("item-lines")
        text = lines[0]
    else:
        text = ",".join(lines)
    if any(ord(char) > 127 for char in text):
        _fail("ascii")
    index = _skip(text, 0, " ")
    if field_kind == "list":
        parsed, index = ([], index) if index >= len(text) else _list(text, index)
    elif field_kind == "dictionary":
        parsed, index = ([], index) if index >= len(text) else _dictionary(text, index)
    else:
        if index >= len(text):
            _fail("empty-item")
        parsed, index = _item(text, index)
    index = _skip(text, index, " ")
    if index != len(text):
        _fail("trailing")
    return parsed


def serialize_structured_field(value: object, kind: str) -> str:
    """Serialize a parsed structured field to its canonical text."""

    field_kind = _kind(kind)
    if field_kind == "list":
        if not isinstance(value, list):
            _fail("serialize-list")
        return ", ".join(_member_text(member) for member in value)
    if field_kind == "dictionary":
        if not isinstance(value, list):
            _fail("serialize-dictionary")
        return ", ".join(_dict_member_text(member) for member in value)
    return _item_text(value)


def _kind(kind: str) -> str:
    if kind not in _KINDS:
        _fail("kind")
    return kind


def _lines(value: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    lines = tuple(value)
    if not lines or any(not isinstance(line, str) for line in lines):
        _fail("lines")
    return lines


def _fail(reason: str) -> None:
    raise StructuredFieldError(reason)


def _skip(text: str, index: int, allowed: str) -> int:
    size = len(text)
    while index < size and text[index] in allowed:
        index += 1
    return index


def _list(text: str, index: int) -> tuple[list[object], int]:
    members: list[object] = []
    while True:
        member, index = _member(text, index)
        members.append(member)
        index = _skip(text, index, " \t")
        if index >= len(text):
            return members, index
        if text[index] != ",":
            _fail("list-separator")
        index = _skip(text, index + 1, " \t")
        if index >= len(text):
            _fail("trailing-comma")


def _dictionary(text: str, index: int) -> tuple[list[object], int]:
    members: list[list[object]] = []
    positions: dict[str, int] = {}
    while True:
        key, index = _key(text, index)
        if index < len(text) and text[index] == "=":
            member, index = _member(text, index + 1)
        else:
            parameters, index = _parameters(text, index)
            member = [True, parameters]
        if key in positions:
            members[positions[key]][1] = member
        else:
            positions[key] = len(members)
            members.append([key, member])
        index = _skip(text, index, " \t")
        if index >= len(text):
            return members, index
        if text[index] != ",":
            _fail("dictionary-separator")
        index = _skip(text, index + 1, " \t")
        if index >= len(text):
            _fail("trailing-comma")


def _member(text: str, index: int) -> tuple[object, int]:
    if index < len(text) and text[index] == "(":
        return _inner(text, index)
    return _item(text, index)


def _inner(text: str, index: int) -> tuple[list[object], int]:
    if index >= len(text) or text[index] != "(":
        _fail("inner-list")
    index += 1
    items: list[object] = []
    while True:
        index = _skip(text, index, " ")
        if index >= len(text):
            _fail("inner-list")
        if text[index] == ")":
            index += 1
            break
        item, index = _item(text, index)
        items.append(item)
        if index >= len(text) or text[index] not in " )":
            _fail("inner-list")
    parameters, index = _parameters(text, index)
    return [items, parameters], index


def _item(text: str, index: int) -> tuple[list[object], int]:
    bare, index = _bare(text, index)
    parameters, index = _parameters(text, index)
    return [bare, parameters], index


def _parameters(text: str, index: int) -> tuple[list[list[object]], int]:
    parameters: list[list[object]] = []
    positions: dict[str, int] = {}
    while index < len(text) and text[index] == ";":
        index = _skip(text, index + 1, " ")
        key, index = _key(text, index)
        if index < len(text) and text[index] == "=":
            bare, index = _bare(text, index + 1)
        else:
            bare = True
        if key in positions:
            parameters[positions[key]][1] = bare
        else:
            positions[key] = len(parameters)
            parameters.append([key, bare])
    return parameters, index


def _key(text: str, index: int) -> tuple[str, int]:
    if index >= len(text) or not (text[index].islower() or text[index] == "*"):
        _fail("key")
    start = index
    index += 1
    size = len(text)
    while index < size and (text[index].islower() or text[index] in _KEY_EXTRA):
        index += 1
    return text[start:index], index


def _bare(text: str, index: int) -> tuple[object, int]:
    if index >= len(text):
        _fail("bare")
    char = text[index]
    if char == "-" or char.isdigit():
        return _number(text, index, date=False)
    if char == '"':
        return _string(text, index)
    if char.isalpha() or char == "*":
        return _token(text, index)
    if char == ":":
        return _binary(text, index)
    if char == "?":
        return _boolean(text, index)
    if char == "@":
        number, index = _number(text, index + 1, date=True)
        return {"__type": "date", "value": number}, index
    if char == "%":
        return _display(text, index)
    _fail("bare")
    raise AssertionError


def _number(text: str, index: int, *, date: bool) -> tuple[object, int]:
    size = len(text)
    sign = 1
    if index < size and text[index] == "-":
        sign = -1
        index += 1
    if index >= size or not text[index].isdigit():
        _fail("date" if date else "number")
    integer_digits = 0
    fraction_digits = 0
    decimal = False
    start = index
    while index < size and (text[index].isdigit() or text[index] == "."):
        if text[index] == ".":
            if date or decimal or integer_digits > 12:
                _fail("date" if date else "decimal")
            decimal = True
        elif decimal:
            if fraction_digits >= 3:
                _fail("decimal")
            fraction_digits += 1
        else:
            if integer_digits >= 15:
                _fail("date" if date else "integer")
            integer_digits += 1
        index += 1
    if decimal and fraction_digits == 0:
        _fail("decimal")
    raw = text[start:index]
    if decimal:
        whole, fraction = raw.split(".", 1)
        whole = whole.lstrip("0") or "0"
        fraction = fraction.rstrip("0") or "0"
        value: object = Decimal(("-" if sign < 0 else "") + whole + "." + fraction)
        if value == 0:
            value = Decimal("0.0")
        return value, index
    number = int(raw) * sign
    return number, index


def _string(text: str, index: int) -> tuple[str, int]:
    if text[index] != '"':
        _fail("string")
    index += 1
    chars: list[str] = []
    size = len(text)
    while index < size:
        char = text[index]
        if char == "\\":
            if index + 1 >= size or text[index + 1] not in '\\"':
                _fail("string")
            chars.append(text[index + 1])
            index += 2
            continue
        if char == '"':
            return "".join(chars), index + 1
        if ord(char) not in _STRING_BYTES:
            _fail("string")
        chars.append(char)
        index += 1
    _fail("string")
    raise AssertionError


def _token(text: str, index: int) -> tuple[dict[str, str], int]:
    if not (text[index].isalpha() or text[index] == "*"):
        _fail("token")
    start = index
    index += 1
    size = len(text)
    while index < size and (text[index].isalnum() or text[index] in _TOKEN_EXTRA):
        index += 1
    return {"__type": "token", "value": text[start:index]}, index


def _binary(text: str, index: int) -> tuple[dict[str, object], int]:
    if text[index] != ":":
        _fail("binary")
    index += 1
    start = index
    size = len(text)
    while index < size and text[index] != ":":
        if text[index] not in _B64:
            _fail("binary")
        index += 1
    if index >= size:
        _fail("binary")
    encoded = text[start:index]
    if len(encoded) % 4 != 0 or encoded.find("=") not in {-1, len(encoded.rstrip("="))}:
        _fail("binary")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise StructuredFieldError("binary") from exc
    if base64.b64encode(decoded).decode("ascii") != encoded:
        _fail("binary")
    return {"__type": "binary", "value": decoded}, index + 1


def _boolean(text: str, index: int) -> tuple[bool, int]:
    if index + 1 >= len(text) or text[index] != "?" or text[index + 1] not in "01":
        _fail("boolean")
    return text[index + 1] == "1", index + 2


def _display(text: str, index: int) -> tuple[dict[str, str], int]:
    if index + 1 >= len(text) or text[index] != "%" or text[index + 1] != '"':
        _fail("display-string")
    index += 2
    encoded = bytearray()
    size = len(text)
    while index < size:
        char = text[index]
        if char == '"':
            try:
                decoded = encoded.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise StructuredFieldError("display-string") from exc
            return {"__type": "displaystring", "value": decoded}, index + 1
        if char == "%":
            if index + 3 > size or any(digit not in _HEX for digit in text[index + 1 : index + 3]):
                _fail("display-string")
            encoded.append(int(text[index + 1 : index + 3], 16))
            index += 3
            continue
        if ord(char) not in _DISPLAY_RAW:
            _fail("display-string")
        encoded.append(ord(char))
        index += 1
    _fail("display-string")
    raise AssertionError


def _member_text(member: object) -> str:
    if _is_inner(member):
        return _inner_text(member)
    return _item_text(member)


def _dict_member_text(member: object) -> str:
    if not isinstance(member, list) or len(member) != 2 or not isinstance(member[0], str):
        _fail("serialize-dictionary")
    key, value = member
    _key_text(key)
    if _is_inner(value):
        return key + "=" + _inner_text(value)
    if isinstance(value, list) and len(value) == 2 and value[0] is True:
        return key + _params_text(value[1])
    return key + "=" + _item_text(value)


def _inner_text(member: object) -> str:
    if not _is_inner(member):
        _fail("serialize-inner")
    items, parameters = member  # type: ignore[misc]
    return "(" + " ".join(_item_text(item) for item in items) + ")" + _params_text(parameters)


def _item_text(member: object) -> str:
    if not isinstance(member, list) or len(member) != 2:
        _fail("serialize-item")
    bare, parameters = member
    return _bare_text(bare) + _params_text(parameters)


def _is_inner(member: object) -> bool:
    if not isinstance(member, list) or len(member) != 2:
        return False
    items, parameters = member
    if not isinstance(items, list) or not isinstance(parameters, list):
        return False
    return all(isinstance(item, list) and len(item) == 2 and isinstance(item[1], list) for item in items)


def _params_text(parameters: object) -> str:
    if not isinstance(parameters, list):
        _fail("serialize-parameters")
    parts: list[str] = []
    for parameter in parameters:
        if not isinstance(parameter, list) or len(parameter) != 2 or not isinstance(parameter[0], str):
            _fail("serialize-parameters")
        key, bare = parameter
        _key_text(key)
        parts.append(key if bare is True else key + "=" + _bare_text(bare))
    return "".join(";" + part for part in parts)


def _key_text(key: str) -> None:
    if not key or not (key[0].islower() or key[0] == "*"):
        _fail("serialize-key")
    if any(not (char.islower() or char in _KEY_EXTRA) for char in key[1:]):
        _fail("serialize-key")


def _bare_text(bare: object) -> str:
    if isinstance(bare, bool):
        return "?1" if bare else "?0"
    if isinstance(bare, int):
        if abs(bare) >= 10**15:
            _fail("serialize-integer")
        return str(bare)
    if isinstance(bare, Decimal):
        return _decimal_text(bare)
    if isinstance(bare, str):
        if any(ord(char) < 0x20 or ord(char) > 0x7E for char in bare):
            _fail("serialize-string")
        return '"' + bare.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(bare, dict):
        kind = bare.get("__type")
        if kind == "token" and isinstance(bare.get("value"), str):
            token = bare["value"]
            if token and (token[0].isalpha() or token[0] == "*") and all(char.isalnum() or char in _TOKEN_EXTRA for char in token[1:]):
                return token
        if kind == "binary" and isinstance(bare.get("value"), (bytes, bytearray)):
            return ":" + base64.b64encode(bytes(bare["value"])).decode("ascii") + ":"
        if kind == "date" and type(bare.get("value")) is int:
            number = bare["value"]
            if abs(number) >= 10**15:
                _fail("serialize-date")
            return "@" + str(number)
        if kind == "displaystring" and isinstance(bare.get("value"), str):
            return _display_text(bare["value"])
    _fail("serialize-bare")
    raise AssertionError


def _decimal_text(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.001"), rounding=ROUND_HALF_EVEN)
    if rounded == 0:
        return "0.0"
    sign = "-" if rounded < 0 else ""
    text = format(abs(rounded), "f")
    whole, _, fraction = text.partition(".")
    if len(whole.lstrip("0") or "0") > 12:
        _fail("serialize-decimal")
    fraction = fraction.rstrip("0") or "0"
    whole = whole.lstrip("0") or "0"
    return sign + whole + "." + fraction


def _display_text(value: str) -> str:
    encoded: list[str] = ['%"']
    for byte in value.encode("utf-8"):
        if byte in _DISPLAY_RAW:
            encoded.append(chr(byte))
        else:
            encoded.append(f"%{byte:02x}")
    encoded.append('"')
    return "".join(encoded)
