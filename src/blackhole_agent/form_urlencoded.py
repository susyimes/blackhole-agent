"""Parse and serialize application/x-www-form-urlencoded bodies.

``urllib.parse.urlencode`` percent-encodes ``*`` and leaves ``~`` raw.
``urllib.parse.parse_qsl`` drops an empty field and keeps a leading BOM
glued to the name. An ``iso-8859-1`` or ``latin1`` label is windows-1252,
so ``€`` is the byte ``0x80`` rather than a ``UnicodeEncodeError``.

This module is the URL Standard parser and serializer (15 August 2022
review draft, sections 5.1 and 5.2), plus the HTML form step that
CRLF-normalizes names and values before that serializer. It does not
parse URLs.
"""

from __future__ import annotations

from typing import Sequence

# Encoding Standard output labels. iso-8859-1 and ascii are windows-1252.
_OUTPUT_CODECS = {
    "unicode-1-1-utf-8": "utf-8",
    "unicode11utf8": "utf-8",
    "unicode20utf8": "utf-8",
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "x-unicode20utf8": "utf-8",
    "ansi_x3.4-1968": "cp1252",
    "ascii": "cp1252",
    "cp1252": "cp1252",
    "cp819": "cp1252",
    "csisolatin1": "cp1252",
    "ibm819": "cp1252",
    "iso-8859-1": "cp1252",
    "iso-ir-100": "cp1252",
    "iso8859-1": "cp1252",
    "iso88591": "cp1252",
    "iso_8859-1": "cp1252",
    "iso_8859-1:1987": "cp1252",
    "l1": "cp1252",
    "latin1": "cp1252",
    "us-ascii": "cp1252",
    "windows-1252": "cp1252",
    "x-cp1252": "cp1252",
}
_PASS_THROUGH = frozenset(b"*-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz")


def parse_form_urlencoded(text: str) -> list[tuple[str, str]]:
    """Parse one application/x-www-form-urlencoded string.

    The string is UTF-8 encoded, then parsed as bytes. A leading UTF-8 BOM
    on a percent-decoded name or value is removed. Empty ``&`` pieces are
    skipped. An empty value, including a name with no ``=``, is kept.
    """

    scalar = _scalar_value(text)
    return parse_form_bytes(scalar.encode("utf-8"))


def parse_form_bytes(data: bytes) -> list[tuple[str, str]]:
    """Parse one application/x-www-form-urlencoded byte sequence."""

    pairs: list[tuple[str, str]] = []
    for piece in data.split(b"&"):
        if piece == b"":
            continue
        if b"=" in piece:
            name, value = piece.split(b"=", 1)
        else:
            name, value = piece, b""
        pairs.append((_decode_component(name), _decode_component(value)))
    return pairs


def serialize_form_urlencoded(
    pairs: Sequence[tuple[str, str]],
    *,
    encoding: str = "utf-8",
) -> str:
    """Serialize name-value pairs.

    ``encoding`` is an Encoding Standard label. An unknown label uses UTF-8.
    Space is ``+``. ``*`` ``-`` ``.`` ``_`` and ASCII alphanumerics stay raw.
    Every other byte is uppercase percent-encoding. A code point the output
    encoding cannot store is a percent-encoded ``&#code point;``.
    """

    codec = _output_codec(encoding)
    parts: list[str] = []
    for name, value in pairs:
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("form pairs must be strings")
        parts.append(f"{_encode_component(name, codec)}={_encode_component(value, codec)}")
    return "&".join(parts)


def serialize_html_form(
    pairs: Sequence[tuple[str, str]],
    *,
    encoding: str = "utf-8",
) -> str:
    """Serialize an HTML form body.

    Names and values are CRLF-normalized, then passed to
    ``serialize_form_urlencoded``. A bare LF or CR becomes ``%0D%0A``.
    """

    normalized = [(_crlf(name), _crlf(value)) for name, value in pairs]
    return serialize_form_urlencoded(normalized, encoding=encoding)


def _output_codec(label: str) -> str:
    key = str(label or "").strip().lower()
    return _OUTPUT_CODECS.get(key, "utf-8")


def _scalar_value(text: str) -> str:
    return "".join("\ufffd" if 0xD800 <= ord(char) <= 0xDFFF else char for char in text)


def _decode_component(data: bytes) -> str:
    decoded = data.replace(b"+", b" ")
    return _percent_decode(decoded).decode("utf-8-sig", errors="replace")


def _percent_decode(data: bytes) -> bytes:
    output = bytearray()
    index = 0
    limit = len(data)
    while index < limit:
        byte = data[index]
        if (
            byte == 0x25
            and index + 2 < limit
            and data[index + 1] in _HEX
            and data[index + 2] in _HEX
        ):
            output.append(int(data[index + 1 : index + 3], 16))
            index += 3
            continue
        output.append(byte)
        index += 1
    return bytes(output)


_HEX = frozenset(b"0123456789ABCDEFabcdef")


def _encode_component(text: str, codec: str) -> str:
    encoded = bytearray()
    for char in text:
        try:
            encoded.extend(char.encode(codec))
        except UnicodeEncodeError:
            encoded.extend(f"&#{ord(char)};".encode("ascii"))
    return _byte_serialize(bytes(encoded))


def _byte_serialize(data: bytes) -> str:
    parts: list[str] = []
    for byte in data:
        if byte == 0x20:
            parts.append("+")
        elif byte in _PASS_THROUGH:
            parts.append(chr(byte))
        else:
            parts.append(f"%{byte:02X}")
    return "".join(parts)


def _crlf(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("form pairs must be strings")
    parts: list[str] = []
    index = 0
    limit = len(text)
    while index < limit:
        char = text[index]
        if char == "\r":
            parts.append("\r\n")
            index += 2 if index + 1 < limit and text[index + 1] == "\n" else 1
            continue
        if char == "\n":
            parts.append("\r\n")
            index += 1
            continue
        parts.append(char)
        index += 1
    return "".join(parts)
