"""Extract an advisory filename from a Content-Disposition field.

RFC 6266 section 4.3: when ``filename*`` is present and understood it wins
over ``filename``, whichever comes first. ``filename*`` is an RFC 8187
ext-value. Only the charsets ``UTF-8`` and ``ISO-8859-1`` are understood,
matched case-insensitively. ``ISO-8859-1`` here is IANA Latin-1, so byte
``0x80`` is U+0080. It is not the Encoding Standard label of the same
spelling, which decodes that byte as the euro sign, and aliases such as
``latin1`` are not this charset. A charset this reader does not understand,
or a UTF-8 sequence that does not decode, leaves ``filename*`` unused so
the plain ``filename`` can still apply.

``filename`` is a token or a quoted-string. It is not percent-decoded, and
``+`` is not a space. A quoted ``%2F`` stays three characters, so it cannot
become a path separator.

The chosen name then keeps only its last path segment. Separators are
``/`` and ``\\``. A final segment that is empty, ``.``, ``..``, or that
contains U+0000 is not a filename. The same parameter name twice makes the
field invalid. The argument is the field value; a leading
``Content-Disposition:`` label is accepted and ignored.
"""

from __future__ import annotations

_TCHAR = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$%&'*+-.^_`|~")
_ATTR = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$&+-.^_`|~")
_CHARSET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$%&+-^_`{}~")
_HEX = frozenset("0123456789abcdefABCDEF")
_OWS = frozenset(" \t\r\n")


class _Invalid(Exception):
    """The field value does not match the Content-Disposition grammar."""


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.n = len(text)
        self.i = 0

    def peek(self) -> str:
        if self.i >= self.n:
            return ""
        return self.text[self.i]

    def ows(self) -> None:
        while self.peek() in _OWS:
            self.i += 1

    def read_while(self, alphabet: frozenset[str]) -> str:
        start = self.i
        while self.peek() in alphabet:
            self.i += 1
        return self.text[start : self.i]

    def skip_param_tail(self) -> None:
        while self.peek() and self.peek() != ";":
            self.i += 1

    def parse_quoted(self) -> str | None:
        if self.peek() != '"':
            return None
        self.i += 1
        chars: list[str] = []
        while self.i < self.n:
            char = self.text[self.i]
            if char == '"':
                self.i += 1
                return "".join(chars)
            if char == "\\":
                if self.i + 1 >= self.n or not _escaped_ok(self.text[self.i + 1]):
                    return None
                chars.append(self.text[self.i + 1])
                self.i += 2
                continue
            if not _quoted_ok(char):
                return None
            chars.append(char)
            self.i += 1
        return None

    def parse_plain(self) -> str:
        if self.peek() == '"':
            quoted = self.parse_quoted()
            if quoted is None:
                raise _Invalid
            return quoted
        token = self.read_while(_TCHAR)
        if not token:
            raise _Invalid
        return token

    def parse_ext(self) -> str | None:
        if self.peek() == '"':
            if self.parse_quoted() is None:
                raise _Invalid
            return None
        charset = self.read_while(_CHARSET)
        if not charset or self.peek() != "'":
            self.skip_param_tail()
            return None
        self.i += 1
        language = self._language()
        if language is None:
            return None
        raw = self._value_bytes()
        if raw is None:
            return None
        return _decode_charset(charset, raw)

    def _language(self) -> str | None:
        start = self.i
        while self.peek() and self.peek() not in "'\r\n; \t":
            self.i += 1
        if self.peek() != "'":
            self.skip_param_tail()
            return None
        language = self.text[start : self.i]
        self.i += 1
        if not _language_ok(language):
            self.skip_param_tail()
            return None
        return language

    def _value_bytes(self) -> bytes | None:
        out = bytearray()
        while True:
            char = self.peek()
            if char == "" or char in "; \t\r\n":
                return bytes(out)
            if char == "%":
                digits = self.text[self.i + 1 : self.i + 3]
                if len(digits) != 2 or any(digit not in _HEX for digit in digits):
                    self.skip_param_tail()
                    return None
                out.append(int(digits, 16))
                self.i += 3
                continue
            if char in _ATTR:
                out.append(ord(char))
                self.i += 1
                continue
            self.skip_param_tail()
            return None

    def parameters(self) -> dict[str, str | None]:
        seen: dict[str, str | None] = {}
        while True:
            self.ows()
            if self.i >= self.n:
                return seen
            if self.peek() != ";":
                raise _Invalid
            self.i += 1
            self.ows()
            name = self.read_while(_TCHAR)
            if not name:
                raise _Invalid
            self.ows()
            if self.peek() != "=":
                raise _Invalid
            self.i += 1
            self.ows()
            key = name.lower()
            if key in seen:
                raise _Invalid
            seen[key] = self.parse_ext() if key.endswith("*") else self.parse_plain()


def content_disposition(header: str) -> dict[str, str]:
    """Return the disposition type and the advisory filename.

    ``type`` is the lowercased disposition type, or ``""`` when the field
    is invalid. ``filename`` is the last usable path segment, or ``""``.
    """

    if not isinstance(header, str):
        raise TypeError("Content-Disposition value must be a string")
    parser = _Parser(header)
    parser.ows()
    mark = parser.i
    leading = parser.read_while(_TCHAR)
    parser.ows()
    if leading.lower() == "content-disposition" and parser.peek() == ":":
        parser.i += 1
    else:
        parser.i = mark
    parser.ows()
    kind = parser.read_while(_TCHAR)
    if not kind:
        return _empty()
    try:
        params = parser.parameters()
    except _Invalid:
        return _empty()
    star = params.get("filename*")
    plain = params.get("filename")
    chosen = star if isinstance(star, str) else plain if isinstance(plain, str) else ""
    return {"type": kind.lower(), "filename": _last_segment(chosen)}


def _empty() -> dict[str, str]:
    return {"type": "", "filename": ""}


def _quoted_ok(char: str) -> bool:
    code = ord(char)
    if char in "\t ":
        return True
    if char in '"\\':
        return False
    return 0x21 <= code <= 0x7E or code >= 0x80


def _escaped_ok(char: str) -> bool:
    code = ord(char)
    return char in "\t " or 0x21 <= code <= 0x7E or code >= 0x80


def _language_ok(language: str) -> bool:
    if not language:
        return True
    parts = language.split("-")
    return all(part.isalnum() and len(part) <= 8 for part in parts)


def _decode_charset(charset: str, raw: bytes) -> str | None:
    name = charset.lower()
    if name == "utf-8":
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if name == "iso-8859-1":
        return raw.decode("iso-8859-1")
    return None


def _last_segment(name: str) -> str:
    if not name:
        return ""
    cut = max(name.rfind("/"), name.rfind("\\"))
    segment = name if cut < 0 else name[cut + 1 :]
    if segment in {"", ".", ".."} or "\x00" in segment:
        return ""
    return segment
