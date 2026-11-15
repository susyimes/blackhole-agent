"""Decode bytes with WHATWG Encoding Standard labels.

Python's codecs treat the label ``iso-8859-1`` as Latin-1, so byte ``0x80``
is U+0080 and byte ``0x81`` is U+0081. The Encoding Standard maps that label,
``latin1``, ``ascii``, and ``us-ascii`` to windows-1252: ``0x80`` is the euro
sign and ``0x81`` stays U+0081. Python's cp1252 codec rejects ``0x81``.

The same gap shows up elsewhere. Shift_JIS byte ``0x5C`` is the yen sign, not
a backslash, unless it is the second byte of a double-byte character. A
``gb2312`` or ``gbk`` label is the gb18030 encoding, and a lone ``0x80`` is
the euro sign. ``x-user-defined`` maps bytes ``0x80``–``0xFF`` into the
Private Use Area. The ``replacement`` encoding emits one U+FFFD for any
nonempty input. A leading UTF-8 or UTF-16 BOM overrides the fallback label
and is not emitted.

``encoding_name`` is the standard's "get an encoding" step. ``decode_text``
is the standard's decode hook: BOM sniff, then the decoder, error mode
replacement. ISO-2022-JP is a known label and is not decoded here.
Double-byte sequences for Shift_JIS and gb18030, and the single-byte
encodings other than windows-1252, go through Python's codec after the
label and the boundary bytes above have been corrected.
"""

from __future__ import annotations

import codecs

_ASCII_SPACE = frozenset("\t\n\f\r ")
_W1252_C1 = (
    "\u20ac\u0081\u201a\u0192\u201e\u2026\u2020\u2021"
    "\u02c6\u2030\u0160\u2039\u0152\u008d\u017d\u008f"
    "\u0090\u2018\u2019\u201c\u201d\u2022\u2013\u2014"
    "\u02dc\u2122\u0161\u203a\u0153\u009d\u017e\u0178"
)


class EncodingError(ValueError):
    """The label is unknown, or the encoding has no decoder here."""


def _labels() -> dict[str, str]:
    groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "UTF-8",
            (
                "unicode-1-1-utf-8",
                "unicode11utf8",
                "unicode20utf8",
                "utf-8",
                "utf8",
                "x-unicode20utf8",
            ),
        ),
        ("IBM866", ("866", "cp866", "csibm866", "ibm866")),
        (
            "ISO-8859-2",
            (
                "csisolatin2",
                "iso-8859-2",
                "iso-ir-101",
                "iso8859-2",
                "iso88592",
                "iso_8859-2",
                "iso_8859-2:1987",
                "l2",
                "latin2",
            ),
        ),
        (
            "ISO-8859-3",
            (
                "csisolatin3",
                "iso-8859-3",
                "iso-ir-109",
                "iso8859-3",
                "iso88593",
                "iso_8859-3",
                "iso_8859-3:1988",
                "l3",
                "latin3",
            ),
        ),
        (
            "ISO-8859-4",
            (
                "csisolatin4",
                "iso-8859-4",
                "iso-ir-110",
                "iso8859-4",
                "iso88594",
                "iso_8859-4",
                "iso_8859-4:1988",
                "l4",
                "latin4",
            ),
        ),
        (
            "ISO-8859-5",
            (
                "csisolatincyrillic",
                "cyrillic",
                "iso-8859-5",
                "iso-ir-144",
                "iso8859-5",
                "iso88595",
                "iso_8859-5",
                "iso_8859-5:1988",
            ),
        ),
        (
            "ISO-8859-6",
            (
                "arabic",
                "asmo-708",
                "csiso88596e",
                "csiso88596i",
                "csisolatinarabic",
                "ecma-114",
                "iso-8859-6",
                "iso-8859-6-e",
                "iso-8859-6-i",
                "iso-ir-127",
                "iso8859-6",
                "iso88596",
                "iso_8859-6",
                "iso_8859-6:1987",
            ),
        ),
        (
            "ISO-8859-7",
            (
                "csisolatingreek",
                "ecma-118",
                "elot_928",
                "greek",
                "greek8",
                "iso-8859-7",
                "iso-ir-126",
                "iso8859-7",
                "iso88597",
                "iso_8859-7",
                "iso_8859-7:1987",
                "sun_eu_greek",
            ),
        ),
        (
            "ISO-8859-8",
            (
                "csiso88598e",
                "csisolatinhebrew",
                "hebrew",
                "iso-8859-8",
                "iso-8859-8-e",
                "iso-ir-138",
                "iso8859-8",
                "iso88598",
                "iso_8859-8",
                "iso_8859-8:1988",
                "visual",
            ),
        ),
        ("ISO-8859-8-I", ("csiso88598i", "iso-8859-8-i", "logical")),
        (
            "ISO-8859-10",
            (
                "csisolatin6",
                "iso-8859-10",
                "iso-ir-157",
                "iso8859-10",
                "iso885910",
                "l6",
                "latin6",
            ),
        ),
        ("ISO-8859-13", ("iso-8859-13", "iso8859-13", "iso885913")),
        ("ISO-8859-14", ("iso-8859-14", "iso8859-14", "iso885914")),
        (
            "ISO-8859-15",
            (
                "csisolatin9",
                "iso-8859-15",
                "iso8859-15",
                "iso885915",
                "iso_8859-15",
                "l9",
            ),
        ),
        ("ISO-8859-16", ("iso-8859-16",)),
        ("KOI8-R", ("cskoi8r", "koi", "koi8", "koi8-r", "koi8_r")),
        ("KOI8-U", ("koi8-ru", "koi8-u")),
        ("macintosh", ("csmacintosh", "mac", "macintosh", "x-mac-roman")),
        (
            "windows-874",
            ("dos-874", "iso-8859-11", "iso8859-11", "iso885911", "tis-620", "windows-874"),
        ),
        ("windows-1250", ("cp1250", "windows-1250", "x-cp1250")),
        ("windows-1251", ("cp1251", "windows-1251", "x-cp1251")),
        (
            "windows-1252",
            (
                "ansi_x3.4-1968",
                "ascii",
                "cp1252",
                "cp819",
                "csisolatin1",
                "ibm819",
                "iso-8859-1",
                "iso-ir-100",
                "iso8859-1",
                "iso88591",
                "iso_8859-1",
                "iso_8859-1:1987",
                "l1",
                "latin1",
                "us-ascii",
                "windows-1252",
                "x-cp1252",
            ),
        ),
        ("windows-1253", ("cp1253", "windows-1253", "x-cp1253")),
        (
            "windows-1254",
            (
                "cp1254",
                "csisolatin5",
                "iso-8859-9",
                "iso-ir-148",
                "iso8859-9",
                "iso88599",
                "iso_8859-9",
                "iso_8859-9:1989",
                "l5",
                "latin5",
                "windows-1254",
                "x-cp1254",
            ),
        ),
        ("windows-1255", ("cp1255", "windows-1255", "x-cp1255")),
        ("windows-1256", ("cp1256", "windows-1256", "x-cp1256")),
        ("windows-1257", ("cp1257", "windows-1257", "x-cp1257")),
        ("windows-1258", ("cp1258", "windows-1258", "x-cp1258")),
        ("x-mac-cyrillic", ("x-mac-cyrillic", "x-mac-ukrainian")),
        ("ISO-2022-JP", ("csiso2022jp", "iso-2022-jp")),
        (
            "Shift_JIS",
            (
                "csshiftjis",
                "ms932",
                "ms_kanji",
                "shift-jis",
                "shift_jis",
                "sjis",
                "windows-31j",
                "x-sjis",
            ),
        ),
        (
            "EUC-JP",
            ("cseucpkdfmtjapanese", "euc-jp", "x-euc-jp"),
        ),
        (
            "EUC-KR",
            (
                "cseuckr",
                "csksc56011987",
                "euc-kr",
                "iso-ir-149",
                "korean",
                "ks_c_5601-1987",
                "ks_c_5601-1989",
                "ksc5601",
                "ksc_5601",
                "windows-949",
            ),
        ),
        (
            "GB18030",
            (
                "chinese",
                "csgb2312",
                "csiso58gb231280",
                "gb18030",
                "gb2312",
                "gbk",
                "gb_2312",
                "gb_2312-80",
                "iso-ir-58",
                "x-gbk",
            ),
        ),
        ("Big5", ("big5", "big5-hkscs", "cn-big5", "csbig5", "x-x-big5")),
        (
            "replacement",
            (
                "csiso2022kr",
                "hz-gb-2312",
                "iso-2022-cn",
                "iso-2022-cn-ext",
                "iso-2022-kr",
                "replacement",
            ),
        ),
        ("UTF-16BE", ("unicodefffe", "utf-16be")),
        (
            "UTF-16LE",
            (
                "csunicode",
                "iso-10646-ucs-2",
                "ucs-2",
                "unicode",
                "unicodefeff",
                "utf-16",
                "utf-16le",
            ),
        ),
        ("x-user-defined", ("x-user-defined",)),
    )
    table: dict[str, str] = {}
    for name, labels in groups:
        for label in labels:
            table[label] = name
    return table


_LABELS = _labels()

_PYTHON_CODEC = {
    "IBM866": "cp866",
    "ISO-8859-2": "iso8859-2",
    "ISO-8859-3": "iso8859-3",
    "ISO-8859-4": "iso8859-4",
    "ISO-8859-5": "iso8859-5",
    "ISO-8859-6": "iso8859-6",
    "ISO-8859-7": "iso8859-7",
    "ISO-8859-8": "iso8859-8",
    "ISO-8859-8-I": "iso8859-8",
    "ISO-8859-10": "iso8859-10",
    "ISO-8859-13": "iso8859-13",
    "ISO-8859-14": "iso8859-14",
    "ISO-8859-15": "iso8859-15",
    "ISO-8859-16": "iso8859-16",
    "KOI8-R": "koi8-r",
    "KOI8-U": "koi8-u",
    "macintosh": "mac_roman",
    "windows-874": "cp874",
    "windows-1250": "cp1250",
    "windows-1251": "cp1251",
    "windows-1253": "cp1253",
    "windows-1254": "cp1254",
    "windows-1255": "cp1255",
    "windows-1256": "cp1256",
    "windows-1257": "cp1257",
    "windows-1258": "cp1258",
    "x-mac-cyrillic": "mac_cyrillic",
    "Big5": "big5",
    "EUC-JP": "euc_jp",
    "EUC-KR": "euc_kr",
}


def encoding_name(label: str) -> str | None:
    """Return the Encoding Standard name for ``label``, or None."""

    if not isinstance(label, str):
        raise TypeError("encoding label must be a string")
    start = 0
    end = len(label)
    while start < end and label[start] in _ASCII_SPACE:
        start += 1
    while end > start and label[end - 1] in _ASCII_SPACE:
        end -= 1
    folded = []
    for char in label[start:end]:
        if "A" <= char <= "Z":
            folded.append(chr(ord(char) + 32))
        else:
            folded.append(char)
    return _LABELS.get("".join(folded))


def decode_text(data: bytes | bytearray, label: str) -> str:
    """Decode ``data`` using the Encoding Standard label ``label``.

    A UTF-8 or UTF-16 byte order mark overrides ``label`` and is consumed.
    An unknown label raises ``EncodingError``.
    """

    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("encoded input must be bytes")
    name = encoding_name(label)
    if name is None:
        raise EncodingError(f"unknown encoding label: {label!r}")
    raw = bytes(data)
    chosen, body = _bom(raw, name)
    return _decode(chosen, body)


def _bom(data: bytes, fallback: str) -> tuple[str, bytes]:
    if data.startswith(b"\xef\xbb\xbf"):
        return "UTF-8", data[3:]
    if data.startswith(b"\xfe\xff"):
        return "UTF-16BE", data[2:]
    if data.startswith(b"\xff\xfe"):
        return "UTF-16LE", data[2:]
    return fallback, data


def _decode(name: str, data: bytes) -> str:
    if name == "UTF-8":
        return data.decode("utf-8", errors="replace")
    if name == "UTF-16LE":
        return data.decode("utf-16-le", errors="replace")
    if name == "UTF-16BE":
        return data.decode("utf-16-be", errors="replace")
    if name == "windows-1252":
        return _windows_1252(data)
    if name == "x-user-defined":
        return _x_user_defined(data)
    if name == "replacement":
        return "\ufffd" if data else ""
    if name == "Shift_JIS":
        return _shift_jis(data)
    if name == "GB18030":
        return _boundary_codec("gb18030", data, {0x80: "\u20ac"})
    if name == "ISO-2022-JP":
        raise EncodingError("ISO-2022-JP is a known label and is not decoded")
    codec = _PYTHON_CODEC.get(name)
    if codec is None:
        raise EncodingError(f"no decoder for {name}")
    return data.decode(codec, errors="replace")


def _windows_1252(data: bytes) -> str:
    chars: list[str] = []
    for byte in data:
        if byte < 0x80 or byte >= 0xA0:
            chars.append(chr(byte))
        else:
            chars.append(_W1252_C1[byte - 0x80])
    return "".join(chars)


def _x_user_defined(data: bytes) -> str:
    chars: list[str] = []
    for byte in data:
        if byte < 0x80:
            chars.append(chr(byte))
        else:
            chars.append(chr(0xF780 + byte - 0x80))
    return "".join(chars)


def _shift_jis(data: bytes) -> str:
    """Shift_JIS decoder. 0x5C and 0x7E are yen and overline only as single bytes.

    A two-byte sequence whose trail is 0x5C stays a double-byte character.
    An unmapped pair is one U+FFFD. Mapped pairs use Python's shift_jis table.
    """

    chars: list[str] = []
    index = 0
    limit = len(data)
    while index < limit:
        byte = data[index]
        if byte <= 0x7F:
            if byte == 0x5C:
                chars.append("\u00a5")
            elif byte == 0x7E:
                chars.append("\u203e")
            else:
                chars.append(chr(byte))
            index += 1
            continue
        if 0xA1 <= byte <= 0xDF:
            chars.append(chr(0xFF61 + byte - 0xA1))
            index += 1
            continue
        lead = 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC
        if lead and index + 1 < limit:
            pair = data[index : index + 2]
            try:
                chars.append(pair.decode("shift_jis"))
            except UnicodeDecodeError:
                chars.append("\ufffd")
            index += 2
            continue
        chars.append("\ufffd")
        index += 1
    return "".join(chars)


def _boundary_codec(codec: str, data: bytes, singles: dict[int, str]) -> str:
    """Decode with ``codec``, except single bytes in ``singles`` at a character boundary."""

    decoder = codecs.getincrementaldecoder(codec)("replace")
    parts: list[str] = []
    for byte in data:
        buffered, _flag = decoder.getstate()
        if not buffered and byte in singles:
            parts.append(singles[byte])
            continue
        parts.append(decoder.decode(bytes((byte,))))
    parts.append(decoder.decode(b"", final=True))
    return "".join(parts)
