"""Sniff the encoding of an HTML byte stream.

A scan that only looks for the bytes ``<meta charset`` gets the document
wrong. The HTML encoding sniffing algorithm (BOM, then a supported transport
label, then a 1024-byte prescan, then an XML declaration) disagrees with that
scan, and with html5lib 1.1, on several documents:

- a UTF-16 ``<?x`` prefix is UTF-16LE or UTF-16BE even though it is not a BOM
- ``<!-->`` closes a comment, so a following meta charset is visible
- a meta charset of ``x-user-defined`` is windows-1252
- ``<?xml encoding="..."?>`` supplies the encoding when the prescan finds none
- a UTF-32-looking prefix ``FF FE 00 00`` is a UTF-16LE BOM, not UTF-32

``sniff_html_encoding`` is that algorithm with no user override, no
autodetector, and no locale table. The fallback is windows-1252. Labels go
through the Encoding Standard, so ``iso-8859-1`` is windows-1252.
"""

from __future__ import annotations

from blackhole_agent.encoding_standard import encoding_name

_PRESCAN_LIMIT = 1024
_WHITESPACE = frozenset((0x09, 0x0A, 0x0C, 0x0D, 0x20))
_ASCII_SPACE = frozenset("\t\n\f\r ")
_UTF16 = frozenset({"UTF-16LE", "UTF-16BE"})
_FAIL = object()


class _End(Exception):
    """The prescan ran out of bytes or hit the 1024-byte end condition."""


def sniff_html_encoding(
    data: bytes | bytearray,
    transport: str | None = None,
    parent: str | None = None,
) -> tuple[str, str]:
    """Return ``(encoding name, confidence)`` for an HTML document.

    ``confidence`` is ``certain`` for a BOM or a supported transport label, and
    ``tentative`` for a prescan, a same-origin parent encoding, or the
    windows-1252 fallback. ``parent`` is used only when it is not UTF-16.
    """

    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("HTML input must be bytes")
    raw = bytes(data)
    bom = _bom(raw)
    if bom is not None:
        return bom, "certain"
    if transport:
        transported = _label(transport)
        if transported is not None:
            return transported, "certain"
    prescan = _prescan(raw[:_PRESCAN_LIMIT])
    if prescan is not None:
        return prescan, "tentative"
    if parent:
        inherited = _label(parent)
        if inherited is not None and inherited not in _UTF16:
            return inherited, "tentative"
    return "windows-1252", "tentative"


def _label(label: str) -> str | None:
    if not isinstance(label, str):
        raise TypeError("encoding label must be a string")
    return encoding_name(label)


def _bom(data: bytes) -> str | None:
    if data.startswith(b"\xef\xbb\xbf"):
        return "UTF-8"
    if data.startswith(b"\xfe\xff"):
        return "UTF-16BE"
    if data.startswith(b"\xff\xfe"):
        return "UTF-16LE"
    return None


def _prescan(data: bytes) -> str | None:
    if data.startswith(b"<\x00?\x00x\x00"):
        return "UTF-16LE"
    if data.startswith(b"\x00<\x00?\x00x"):
        return "UTF-16BE"
    cursor = _Cursor(data)
    try:
        while cursor.index < len(cursor.data):
            if cursor.data.startswith(b"<!--", cursor.index):
                _close_comment(cursor)
            elif _is_meta(cursor):
                found = _read_meta(cursor)
                if found:
                    return found
            elif _is_tag(cursor):
                _skip_tag(cursor)
            elif (
                cursor.data.startswith(b"<!", cursor.index)
                or cursor.data.startswith(b"</", cursor.index)
                or cursor.data.startswith(b"<?", cursor.index)
            ):
                _skip_to_gt(cursor)
            cursor.index += 1
        raise _End
    except _End:
        return _xml_encoding(data)


class _Cursor:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.index = 0

    def byte(self) -> int:
        if self.index >= len(self.data):
            raise _End
        return self.data[self.index]


def _close_comment(cursor: _Cursor) -> None:
    """Point at the ``>`` of a comment, whose dashes may be the opener's."""

    start = cursor.index
    scan = start + 1
    data = cursor.data
    while scan < len(data):
        if (
            data[scan] == 0x3E
            and scan >= 2
            and data[scan - 1] == 0x2D
            and data[scan - 2] == 0x2D
            and scan > start
        ):
            cursor.index = scan
            return
        scan += 1
    raise _End


def _is_meta(cursor: _Cursor) -> bool:
    index = cursor.index
    data = cursor.data
    if index + 6 > len(data) or data[index] != 0x3C:
        return False
    return (
        data[index + 1] in (0x4D, 0x6D)
        and data[index + 2] in (0x45, 0x65)
        and data[index + 3] in (0x54, 0x74)
        and data[index + 4] in (0x41, 0x61)
        and data[index + 5] in (0x09, 0x0A, 0x0C, 0x0D, 0x20, 0x2F)
    )


def _is_tag(cursor: _Cursor) -> bool:
    index = cursor.index
    data = cursor.data
    if index >= len(data) or data[index] != 0x3C:
        return False
    index += 1
    if index < len(data) and data[index] == 0x2F:
        index += 1
    if index >= len(data):
        return False
    letter = data[index]
    return 0x41 <= letter <= 0x5A or 0x61 <= letter <= 0x7A


def _skip_tag(cursor: _Cursor) -> None:
    _advance_to_space_or_gt(cursor)
    while _attribute(cursor) is not None:
        pass


def _advance_to_space_or_gt(cursor: _Cursor) -> None:
    while cursor.index < len(cursor.data):
        if cursor.data[cursor.index] in _WHITESPACE or cursor.data[cursor.index] == 0x3E:
            return
        cursor.index += 1
    raise _End


def _skip_to_gt(cursor: _Cursor) -> None:
    start = cursor.index
    scan = start + 1
    data = cursor.data
    while scan < len(data):
        if data[scan] == 0x3E:
            cursor.index = scan
            return
        scan += 1
    raise _End


def _read_meta(cursor: _Cursor) -> str | None:
    cursor.index += 5
    seen: list[str] = []
    got_pragma = False
    need_pragma: bool | None = None
    charset: str | object | None = None
    while True:
        attr = _attribute(cursor)
        if attr is None:
            break
        name, value = attr
        if name in seen:
            continue
        seen.append(name)
        if name == "http-equiv":
            if value == "content-type":
                got_pragma = True
        elif name == "content":
            extracted = _extract_content_encoding(value)
            if extracted is not None and charset is None:
                charset = extracted
                need_pragma = True
        elif name == "charset":
            resolved = encoding_name(value)
            charset = resolved if resolved is not None else _FAIL
            need_pragma = False
    if need_pragma is None or (need_pragma and not got_pragma) or charset in (None, _FAIL):
        return None
    assert isinstance(charset, str)
    if charset in _UTF16:
        charset = "UTF-8"
    if charset == "x-user-defined":
        charset = "windows-1252"
    return charset


def _attribute(cursor: _Cursor) -> tuple[str, str] | None:
    while True:
        byte = cursor.byte()
        if byte in _WHITESPACE or byte == 0x2F:
            cursor.index += 1
            continue
        break
    if cursor.byte() == 0x3E:
        return None
    name: list[str] = []
    while True:
        byte = cursor.byte()
        if byte == 0x3D and name:
            cursor.index += 1
            return "".join(name), _attribute_value(cursor)
        if byte in _WHITESPACE:
            cursor.index += 1
            while cursor.index < len(cursor.data) and cursor.data[cursor.index] in _WHITESPACE:
                cursor.index += 1
            if cursor.byte() != 0x3D:
                return "".join(name), ""
            cursor.index += 1
            return "".join(name), _attribute_value(cursor)
        if byte in (0x2F, 0x3E):
            return "".join(name), ""
        name.append(_fold(byte))
        cursor.index += 1


def _attribute_value(cursor: _Cursor) -> str:
    while cursor.byte() in _WHITESPACE:
        cursor.index += 1
    byte = cursor.byte()
    if byte in (0x22, 0x27):
        quote = byte
        value: list[str] = []
        while True:
            cursor.index += 1
            current = cursor.byte()
            if current == quote:
                cursor.index += 1
                return "".join(value)
            value.append(_fold(current))
    if byte == 0x3E:
        return ""
    value = [_fold(byte)]
    cursor.index += 1
    while True:
        current = cursor.byte()
        if current in _WHITESPACE or current == 0x3E:
            return "".join(value)
        value.append(_fold(current))
        cursor.index += 1


def _fold(byte: int) -> str:
    if 0x41 <= byte <= 0x5A:
        return chr(byte + 0x20)
    return chr(byte)


def _extract_content_encoding(value: str) -> str | None:
    """Extract a charset from a meta content attribute, per the HTML algorithm."""

    position = 0
    limit = len(value)
    while True:
        found = _find_charset(value, position)
        if found < 0:
            return None
        position = found + 7
        while position < limit and value[position] in _ASCII_SPACE:
            position += 1
        if position >= limit:
            return None
        if value[position] != "=":
            continue
        position += 1
        while position < limit and value[position] in _ASCII_SPACE:
            position += 1
        if position >= limit:
            return None
        quote = value[position]
        if quote in "\"'":
            end = value.find(quote, position + 1)
            if end < 0:
                return None
            return encoding_name(value[position + 1 : end])
        end = position
        while end < limit and value[end] not in _ASCII_SPACE and value[end] != ";":
            end += 1
        return encoding_name(value[position:end])


def _find_charset(value: str, start: int) -> int:
    folded: list[str] = []
    for char in value:
        if "A" <= char <= "Z":
            folded.append(chr(ord(char) + 32))
        else:
            folded.append(char)
    return "".join(folded).find("charset", start)


def _xml_encoding(data: bytes) -> str | None:
    if not data.startswith(b"<?xml"):
        return None
    declaration_end = data.find(b">")
    if declaration_end < 0:
        return None
    marker = data.find(b"encoding", 0, declaration_end)
    if marker < 0:
        return None
    index = marker + len(b"encoding")
    while index < len(data) and data[index] <= 0x20:
        index += 1
    if index >= len(data) or data[index] != 0x3D:
        return None
    index += 1
    while index < len(data) and data[index] <= 0x20:
        index += 1
    if index >= len(data) or data[index] not in (0x22, 0x27):
        return None
    quote = data[index]
    index += 1
    end = data.find(bytes((quote,)), index)
    if end < 0:
        return None
    raw = data[index:end]
    if any(byte <= 0x20 for byte in raw):
        return None
    resolved = encoding_name("".join(chr(byte) for byte in raw))
    if resolved is None:
        return None
    if resolved in _UTF16:
        return "UTF-8"
    return resolved
