"""Determine the computed media type of a resource from its bytes and label.

A Content-Type header is not the media type of the bytes. An image label is
checked against the image signatures, so PNG bytes labeled image/gif become
image/png. An HTML or XML label is kept, so those same bytes labeled
text/html or image/svg+xml stay that label. An exact Apache text/plain label
is re-read as text or binary. ``X-Content-Type-Options: nosniff`` keeps the
supplied label, and a script tag with no label is text/html only when
sniffing scriptable types is still allowed.

The pattern tables and the decision order follow the MIME Sniffing Standard.
This module does not fetch a response and does not speak a handshake.
"""

from __future__ import annotations

_HEADER_LENGTH = 1445
_WS = frozenset((0x09, 0x0A, 0x0C, 0x0D, 0x20))
_TOKEN = frozenset("!#$%&'*+-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ^_`abcdefghijklmnopqrstuvwxyz|~")
_APACHE_BUG = frozenset(
    (
        "text/plain",
        "text/plain; charset=ISO-8859-1",
        "text/plain; charset=iso-8859-1",
        "text/plain; charset=UTF-8",
    )
)
_UNKNOWN = frozenset(("unknown/unknown", "application/unknown", "*/*"))
_MP4_BRANDS = frozenset((b"mp41", b"mp42", b"isom", b"iso2", b"mmp4", b"M4V ", b"M4A ", b"M4P ", b"avc1"))
_MP3_RATES = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_MP25_RATES = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_SAMPLE_RATES = (44100, 48000, 32000, 0)

# pattern, mask, essence, ignore leading whitespace
_Signature = tuple[bytes, bytes, str, bool]


def _row(pattern: bytes, mask: bytes, essence: str, *, whitespace: bool = False) -> _Signature:
    if len(pattern) != len(mask):
        raise ValueError("pattern and mask differ in length")
    return (pattern, mask, essence, whitespace)


_SCRIPTABLE: tuple[_Signature, ...] = (
    _row(
        b"<!DOCTYPE HTML ",
        bytes((0xFF, 0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xDF, 0xDF, 0xDF, 0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xE1)),
        "text/html",
        whitespace=True,
    ),
    _row(b"<HTML ", bytes((0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<HEAD ", bytes((0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<SCRIPT ", bytes((0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<IFRAME ", bytes((0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<H1 ", bytes((0xFF, 0xDF, 0xFF, 0xE1)), "text/html", whitespace=True),
    _row(b"<DIV ", bytes((0xFF, 0xDF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<FONT ", bytes((0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<TABLE ", bytes((0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<A ", bytes((0xFF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<STYLE ", bytes((0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<TITLE ", bytes((0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<B ", bytes((0xFF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<BODY ", bytes((0xFF, 0xDF, 0xDF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<BR ", bytes((0xFF, 0xDF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<P ", bytes((0xFF, 0xDF, 0xE1)), "text/html", whitespace=True),
    _row(b"<!-- ", bytes((0xFF, 0xFF, 0xFF, 0xFF, 0xE1)), "text/html", whitespace=True),
    _row(b"<?xml", bytes((0xFF, 0xFF, 0xFF, 0xFF, 0xFF)), "text/xml", whitespace=True),
    _row(b"%PDF-", bytes((0xFF, 0xFF, 0xFF, 0xFF, 0xFF)), "application/pdf"),
)
_PLAIN: tuple[_Signature, ...] = (
    _row(b"%!PS-Adobe-", bytes((0xFF,) * 11), "application/postscript"),
    _row(b"\xfe\xff\x00\x00", bytes((0xFF, 0xFF, 0x00, 0x00)), "text/plain"),
    _row(b"\xff\xfe\x00\x00", bytes((0xFF, 0xFF, 0x00, 0x00)), "text/plain"),
    _row(b"\xef\xbb\xbf\x00", bytes((0xFF, 0xFF, 0xFF, 0x00)), "text/plain"),
)
_IMAGES: tuple[_Signature, ...] = (
    _row(b"\x00\x00\x01\x00", bytes((0xFF, 0xFF, 0xFF, 0xFF)), "image/x-icon"),
    _row(b"\x00\x00\x02\x00", bytes((0xFF, 0xFF, 0xFF, 0xFF)), "image/x-icon"),
    _row(b"BM", bytes((0xFF, 0xFF)), "image/bmp"),
    _row(b"GIF87a", bytes((0xFF,) * 6), "image/gif"),
    _row(b"GIF89a", bytes((0xFF,) * 6), "image/gif"),
    _row(
        b"RIFF\x00\x00\x00\x00WEBPVP",
        bytes((0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF)),
        "image/webp",
    ),
    _row(b"\x89PNG\r\n\x1a\n", bytes((0xFF,) * 8), "image/png"),
    _row(b"\xff\xd8\xff", bytes((0xFF, 0xFF, 0xFF)), "image/jpeg"),
)
_AUDIO_VIDEO: tuple[_Signature, ...] = (
    _row(
        b"FORM\x00\x00\x00\x00AIFF",
        bytes((0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF)),
        "audio/aiff",
    ),
    _row(b"ID3", bytes((0xFF, 0xFF, 0xFF)), "audio/mpeg"),
    _row(b"OggS\x00", bytes((0xFF, 0xFF, 0xFF, 0xFF, 0xFF)), "application/ogg"),
    _row(b"MThd\x00\x00\x00\x06", bytes((0xFF,) * 8), "audio/midi"),
    _row(
        b"RIFF\x00\x00\x00\x00AVI ",
        bytes((0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF)),
        "video/avi",
    ),
    _row(
        b"RIFF\x00\x00\x00\x00WAVE",
        bytes((0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF)),
        "audio/wave",
    ),
)
_ARCHIVES: tuple[_Signature, ...] = (
    _row(b"\x1f\x8b\x08", bytes((0xFF, 0xFF, 0xFF)), "application/x-gzip"),
    _row(b"PK\x03\x04", bytes((0xFF, 0xFF, 0xFF, 0xFF)), "application/zip"),
    _row(b"Rar!\x1a\x07\x00", bytes((0xFF,) * 7), "application/x-rar-compressed"),
)


def computed_mime_type(resource: bytes, content_type: str | None = None, *, no_sniff: bool = False) -> str:
    """Return the computed media-type essence for ``resource``.

    ``content_type`` is the raw HTTP Content-Type field value. ``None`` means
    the field is absent. ``no_sniff`` is the ``nosniff`` directive.
    """

    if not isinstance(resource, (bytes, bytearray, memoryview)):
        raise TypeError("resource must be bytes")
    if content_type is not None and not isinstance(content_type, str):
        raise TypeError("content_type must be a string or None")
    header = bytes(resource[:_HEADER_LENGTH])
    supplied, apache = _supplied(content_type)
    if supplied is not None and (_is_html(supplied) or _is_xml(supplied)):
        return _essence(supplied)
    if supplied is None or _essence(supplied) in _UNKNOWN:
        return _unknown(header, scriptable=not no_sniff)
    if no_sniff:
        return _essence(supplied)
    if apache:
        return _text_or_binary(header)
    if supplied[0] == "image":
        matched = _match_table(header, _IMAGES)
        if matched is not None:
            return matched
    if _is_audio_or_video(supplied):
        matched = _match_audio_video(header)
        if matched is not None:
            return matched
    return _essence(supplied)


def _supplied(content_type: str | None) -> tuple[tuple[str, str] | None, bool]:
    if content_type is None:
        return None, False
    parsed = _parse_mime(content_type)
    apache = content_type in _APACHE_BUG and parsed is not None
    return parsed, apache


def _parse_mime(value: str) -> tuple[str, str] | None:
    text = value.strip("\t\n\r ")
    slash = text.find("/")
    if slash <= 0:
        return None
    type_name = text[:slash]
    if not _token(type_name):
        return None
    rest = text[slash + 1 :]
    semicolon = rest.find(";")
    subtype = rest if semicolon < 0 else rest[:semicolon]
    subtype = subtype.rstrip("\t\n\r ")
    if not subtype or not _token(subtype):
        return None
    return type_name.lower(), subtype.lower()


def _token(value: str) -> bool:
    return bool(value) and all(char in _TOKEN for char in value)


def _essence(parsed: tuple[str, str]) -> str:
    return f"{parsed[0]}/{parsed[1]}"


def _is_html(parsed: tuple[str, str]) -> bool:
    return parsed == ("text", "html")


def _is_xml(parsed: tuple[str, str]) -> bool:
    type_name, subtype = parsed
    return (subtype == "xml" and type_name in {"text", "application"}) or subtype.endswith("+xml")


def _is_audio_or_video(parsed: tuple[str, str]) -> bool:
    type_name, subtype = parsed
    return type_name in {"audio", "video"} or (type_name == "application" and subtype == "ogg")


def _unknown(header: bytes, *, scriptable: bool) -> str:
    if scriptable:
        matched = _match_table(header, _SCRIPTABLE)
        if matched is not None:
            return matched
    for table in (_PLAIN, _IMAGES, _AUDIO_VIDEO):
        matched = _match_table(header, table)
        if matched is not None:
            return matched
    matched = _match_mp4(header) or _match_webm(header) or _match_mp3(header)
    if matched is not None:
        return matched
    matched = _match_table(header, _ARCHIVES)
    if matched is not None:
        return matched
    return _text_or_binary(header)


def _match_audio_video(header: bytes) -> str | None:
    matched = _match_table(header, _AUDIO_VIDEO)
    if matched is not None:
        return matched
    return _match_mp4(header) or _match_webm(header) or _match_mp3(header)


def _match_table(header: bytes, table: tuple[_Signature, ...]) -> str | None:
    for pattern, mask, essence, whitespace in table:
        if _matches(header, pattern, mask, whitespace):
            return essence
    return None


def _matches(header: bytes, pattern: bytes, mask: bytes, whitespace: bool) -> bool:
    start = 0
    if whitespace:
        while start < len(header) and header[start] in _WS:
            start += 1
    end = start + len(pattern)
    if len(header) < end:
        return False
    for index, (wanted, bits) in enumerate(zip(pattern, mask)):
        byte = header[start + index]
        if (byte & bits) != (wanted & bits):
            return False
    return True


def _binary_byte(byte: int) -> bool:
    return byte <= 0x08 or byte == 0x0B or 0x0E <= byte <= 0x1A or 0x1C <= byte <= 0x1F


def _text_or_binary(header: bytes) -> str:
    if len(header) >= 2 and header[:2] in (b"\xfe\xff", b"\xff\xfe"):
        return "text/plain"
    if len(header) >= 3 and header[:3] == b"\xef\xbb\xbf":
        return "text/plain"
    if any(_binary_byte(byte) for byte in header):
        return "application/octet-stream"
    return "text/plain"


def _match_mp4(resource: bytes) -> str | None:
    if len(resource) < 12 or resource[4:8] != b"ftyp":
        return None
    length = int.from_bytes(resource[:4], "big")
    if length < 12 or length > len(resource):
        return None
    if resource[8:12] in _MP4_BRANDS:
        return "video/mp4"
    index = 16
    while index + 4 <= length and index + 4 <= len(resource):
        if resource[index : index + 4] in _MP4_BRANDS:
            return "video/mp4"
        index += 4
    return None


def _vint_size(sequence: bytes, index: int) -> int:
    mask = 128
    number_size = 1
    while number_size < 8 and number_size < len(sequence):
        if sequence[index] & mask:
            break
        mask >>= 1
        number_size += 1
    return number_size


def _padded(sequence: bytes, offset: int, pattern: bytes) -> bool:
    while offset < len(sequence) and sequence[offset] == 0:
        offset += 1
    end = offset + len(pattern)
    return len(sequence) >= end and sequence[offset:end] == pattern


def _match_webm(resource: bytes) -> str | None:
    length = len(resource)
    if length < 4 or resource[:4] != b"\x1a\x45\xdf\xa3":
        return None
    index = 4
    while index < length and index < 38:
        if index + 1 < length and resource[index] == 0x42 and resource[index + 1] == 0x82:
            index += 2
            if index >= length:
                break
            index += _vint_size(resource, index)
            if index >= length - 4:
                break
            if _padded(resource, index, b"webm"):
                return "video/webm"
        index += 1
    return None


def _mp3_header(sequence: bytes, start: int) -> bool:
    if len(sequence) < start + 4:
        return False
    if sequence[start] != 0xFF or (sequence[start + 1] & 0xE0) != 0xE0:
        return False
    layer = (sequence[start + 1] & 0x06) >> 1
    if layer == 0:
        return False
    bit_rate = (sequence[start + 2] & 0xF0) >> 4
    sample_rate = (sequence[start + 2] & 0x0C) >> 2
    if bit_rate == 15 or sample_rate == 3:
        return False
    final_layer = (4 - layer) & 0x03
    return final_layer == 3


def _mp3_frame_size(sequence: bytes, start: int) -> int:
    version = (sequence[start + 1] & 0x18) >> 3
    bitrate_index = (sequence[start + 2] & 0xF0) >> 4
    rates = _MP3_RATES if (version & 0x01) != 0 else _MP25_RATES
    bitrate = rates[bitrate_index]
    samplerate = _SAMPLE_RATES[(sequence[start + 2] & 0x0C) >> 2]
    pad = (sequence[start + 2] & 0x02) >> 1
    if samplerate == 0 or bitrate == 0:
        return 0
    scale = 72 if version == 1 else 144
    size = (bitrate * 1000 * scale) // samplerate
    if pad:
        size += 1
    return size


def _match_mp3(resource: bytes) -> str | None:
    if not _mp3_header(resource, 0):
        return None
    skipped = _mp3_frame_size(resource, 0)
    if skipped < 4 or skipped > len(resource):
        return None
    if not _mp3_header(resource, skipped):
        return None
    return "audio/mpeg"
