"""Parse and serialize special-scheme URLs the way the WHATWG URL standard does.

Python's ``urllib.parse`` keeps a default port, leaves a backslash in an http(s)
URL, and does not rewrite an octal IPv4 octet. ``parse_href`` follows the URL
standard for the special schemes ``http``, ``https``, ``ws``, ``wss``, ``ftp``,
and ``file``: tab and newline stripping, default-port omission, backslash as
slash, octal and hexadecimal IPv4, dot-segment resolution, same-scheme
relatives, and file URLs whose Windows drive letter, UNC host, and localhost
host are not what ``urllib`` emits.

This is the standard's special-URL parser, not a wrapper around ``urllib``.
"""

from __future__ import annotations

import ipaddress

_SPECIAL_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}
_SPECIAL_SCHEMES = frozenset({*_SPECIAL_PORTS, "file"})
_FORBIDDEN_HOST = frozenset("\x00\t\n\r #/:<>?@[\\]^|")
_QUERY_EXTRA = frozenset(' "<>#')
_PATH_EXTRA = _QUERY_EXTRA | frozenset("?`{}")
_USERINFO_EXTRA = _PATH_EXTRA | frozenset("/:;=@[\\]^|")
_FRAGMENT_EXTRA = frozenset(' "<>`')
_SINGLE_DOT = frozenset({".", "%2e"})
_DOUBLE_DOT = frozenset({"..", ".%2e", "%2e.", "%2e%2e"})


class URLParseError(ValueError):
    """The input is not a URL the WHATWG standard accepts."""


class _URL:
    def __init__(self) -> None:
        self.scheme = ""
        self.username = ""
        self.password = ""
        self.host: str | None = None
        self.port: int | None = None
        self.path: list[str] = []
        self.query: str | None = None
        self.fragment: str | None = None

    def copy_authority_from(self, base: _URL) -> None:
        self.username = base.username
        self.password = base.password
        self.host = base.host
        self.port = base.port


def parse_href(text: str, base: str | None = None) -> str:
    """Return the serialized URL for ``text``.

    ``base`` is the base URL for a relative reference. A URL the standard
    rejects raises ``URLParseError``.
    """

    if not isinstance(text, str):
        raise URLParseError("URL input must be a string")
    base_url = None
    if base is not None:
        if not isinstance(base, str):
            raise URLParseError("URL base must be a string")
        base_url = _parse(base, None)
    return _serialize(_parse(text, base_url))


def _parse(text: str, base: _URL | None) -> _URL:
    raw = "".join(char for char in text if char not in "\t\n\r")
    start = 0
    end = len(raw)
    while start < end and (_is_c0(raw[start]) or raw[start] == " "):
        start += 1
    while end > start and (_is_c0(raw[end - 1]) or raw[end - 1] == " "):
        end -= 1
    chars = raw[start:end]
    url = _URL()
    state = "scheme start"
    buffer = ""
    at_sign = False
    password_token = False
    inside_brackets = False
    index = 0
    limit = len(chars) * 8 + 48
    steps = 0
    while steps <= limit:
        steps += 1
        char = chars[index] if index < len(chars) else None
        hold = False

        if state == "scheme start":
            if char is not None and char.isascii() and char.isalpha():
                buffer += char.lower()
                state = "scheme"
            else:
                state = "no scheme"
                hold = True
        elif state == "scheme":
            if char is not None and char.isascii() and (char.isalnum() or char in "+-."):
                buffer += char.lower()
            elif char == ":":
                url.scheme = buffer
                buffer = ""
                if url.scheme == "file":
                    state = "file"
                elif url.scheme not in _SPECIAL_SCHEMES:
                    raise URLParseError(f"scheme {url.scheme!r} is not a special scheme")
                elif base is not None and base.scheme == url.scheme:
                    state = "special relative or authority"
                else:
                    state = "special authority slashes"
            else:
                buffer = ""
                index = 0
                state = "no scheme"
                continue
        elif state == "no scheme":
            if base is None:
                raise URLParseError("relative URL without a base")
            # A file base never enters the generic relative state. The file
            # state is what keeps a Windows drive letter on the path.
            state = "file" if base.scheme == "file" else "relative"
            hold = True
        elif state == "file":
            url.scheme = "file"
            url.host = ""
            if char in {"/", "\\"}:
                state = "file slash"
            elif base is not None and base.scheme == "file":
                url.host = base.host
                url.path = list(base.path)
                url.query = base.query
                if char == "?":
                    url.query = ""
                    state = "query"
                elif char == "#":
                    url.fragment = ""
                    state = "fragment"
                elif char is not None:
                    url.query = None
                    if not _starts_with_windows_drive(chars[index:]):
                        _shorten(url)
                    else:
                        url.path = []
                    state = "path"
                    hold = True
                else:
                    return url
            else:
                state = "path"
                hold = True
        elif state == "file slash":
            if char in {"/", "\\"}:
                state = "file host"
            else:
                if base is not None and base.scheme == "file":
                    url.host = base.host
                    if (
                        not _starts_with_windows_drive(chars[index:])
                        and base.path
                        and _is_normalized_windows_drive(base.path[0])
                    ):
                        url.path.append(base.path[0])
                state = "path"
                hold = True
        elif state == "file host":
            if char is None or char in "/\\?#":
                if _is_windows_drive(buffer):
                    # The drive letter is a path segment, not a host. The
                    # buffer stays so path state can normalize "|" to ":".
                    state = "path"
                    hold = True
                elif buffer == "":
                    url.host = ""
                    state = "path start"
                    hold = True
                else:
                    url.host = _parse_file_host(buffer)
                    buffer = ""
                    state = "path start"
                    hold = True
            else:
                buffer += char
        elif state == "special relative or authority":
            if char == "/" and _peek(chars, index) == "/":
                state = "special authority ignore slashes"
                index += 1
            else:
                state = "relative"
                hold = True
        elif state == "special authority slashes":
            if char == "/" and _peek(chars, index) == "/":
                state = "special authority ignore slashes"
                index += 1
            else:
                state = "special authority ignore slashes"
                hold = True
        elif state == "special authority ignore slashes":
            if char not in {"/", "\\"}:
                state = "authority"
                hold = True
        elif state == "relative":
            url.scheme = base.scheme if base is not None else ""
            if char == "/" or (char == "\\" and _is_special(url.scheme)):
                state = "relative slash"
            else:
                if base is None:
                    raise URLParseError("relative URL without a base")
                url.copy_authority_from(base)
                url.path = list(base.path)
                url.query = base.query
                if char == "?":
                    url.query = ""
                    state = "query"
                elif char == "#":
                    url.fragment = ""
                    state = "fragment"
                elif char is not None:
                    url.query = None
                    _shorten(url)
                    state = "path"
                    hold = True
                else:
                    return url
        elif state == "relative slash":
            if base is None:
                raise URLParseError("relative URL without a base")
            if char in {"/", "\\"} and _is_special(url.scheme):
                state = "special authority ignore slashes"
            elif char == "/":
                state = "authority"
            else:
                url.copy_authority_from(base)
                state = "path"
                hold = True
        elif state == "authority":
            if char == "@":
                if at_sign:
                    buffer = "%40" + buffer
                at_sign = True
                url.username, url.password, password_token = _consume_userinfo(
                    buffer, url.username, url.password, password_token
                )
                buffer = ""
            elif char is None or char in "/?#" or (char == "\\" and _is_special(url.scheme)):
                if at_sign and buffer == "":
                    raise URLParseError("empty host")
                index -= len(buffer)
                buffer = ""
                inside_brackets = False
                state = "host"
                continue
            else:
                buffer += char
        elif state == "host":
            if char == ":" and not inside_brackets:
                url.host = _parse_host(buffer, special=_is_special(url.scheme))
                buffer = ""
                state = "port"
            elif char is None or char in "/?#" or (char == "\\" and _is_special(url.scheme)):
                if _is_special(url.scheme) and buffer == "":
                    raise URLParseError("empty host")
                url.host = _parse_host(buffer, special=_is_special(url.scheme))
                buffer = ""
                state = "path start"
                hold = True
            else:
                if char == "[":
                    inside_brackets = True
                elif char == "]":
                    inside_brackets = False
                buffer += char
        elif state == "port":
            if char is not None and char.isascii() and char.isdigit():
                buffer += char
            elif char is None or char in "/?#" or (char == "\\" and _is_special(url.scheme)):
                if buffer != "":
                    port = int(buffer, 10)
                    if port > 65535:
                        raise URLParseError("port out of range")
                    url.port = None if port == _SPECIAL_PORTS.get(url.scheme) else port
                    buffer = ""
                state = "path start"
                hold = True
            else:
                raise URLParseError("invalid port")
        elif state == "path start":
            if char in {"/", "\\"} and _is_special(url.scheme):
                state = "path"
            elif char == "?":
                url.query = ""
                state = "query"
            elif char == "#":
                url.fragment = ""
                state = "fragment"
            elif char is not None:
                state = "path"
                hold = True
            else:
                return url
        elif state == "path":
            if char is None or char in "/?#" or (char == "\\" and _is_special(url.scheme)):
                _commit_path(url, buffer, char)
                buffer = ""
                if char == "?":
                    url.query = ""
                    state = "query"
                elif char == "#":
                    url.fragment = ""
                    state = "fragment"
                elif char is None:
                    return url
            else:
                buffer += _percent_encode(char, _PATH_EXTRA)
        elif state == "query":
            if char is None or char == "#":
                url.query = buffer
                buffer = ""
                if char == "#":
                    url.fragment = ""
                    state = "fragment"
                else:
                    return url
            else:
                buffer += _percent_encode(char, _QUERY_EXTRA)
        elif state == "fragment":
            if char is None:
                url.fragment = buffer
                return url
            buffer += _percent_encode(char, _FRAGMENT_EXTRA)
        else:
            raise URLParseError(f"unknown parser state {state}")

        if not hold:
            index += 1
    raise URLParseError("parser exceeded its step budget")


def _peek(chars: str, index: int) -> str | None:
    nxt = index + 1
    if nxt < len(chars):
        return chars[nxt]
    return None


def _is_c0(char: str) -> bool:
    return ord(char) <= 0x1F


def _percent_encode(char: str, extra: frozenset[str]) -> str:
    code = ord(char)
    if code < 0x20 or code > 0x7E or char in extra:
        return "".join(f"%{byte:02X}" for byte in char.encode("utf-8"))
    return char


def _consume_userinfo(
    buffer: str, username: str, password: str, password_token: bool
) -> tuple[str, str, bool]:
    for char in buffer:
        if char == ":" and not password_token:
            password_token = True
            continue
        encoded = _percent_encode(char, _USERINFO_EXTRA)
        if password_token:
            password += encoded
        else:
            username += encoded
    return username, password, password_token


def _commit_path(url: _URL, buffer: str, char: str | None) -> None:
    kind = buffer.lower()
    directory = char is None or char in "?#"
    if kind in _DOUBLE_DOT:
        _shorten(url)
        if directory:
            url.path.append("")
        return
    if kind in _SINGLE_DOT:
        if directory:
            url.path.append("")
        return
    if url.scheme == "file" and not url.path and _is_windows_drive(buffer):
        buffer = buffer[0] + ":"
    url.path.append(buffer)


def _is_special(scheme: str) -> bool:
    return scheme in _SPECIAL_SCHEMES


def _is_windows_drive(text: str) -> bool:
    return (
        len(text) == 2
        and text[0].isascii()
        and text[0].isalpha()
        and text[1] in ":|"
    )


def _is_normalized_windows_drive(text: str) -> bool:
    return len(text) == 2 and text[0].isascii() and text[0].isalpha() and text[1] == ":"


def _starts_with_windows_drive(text: str) -> bool:
    if not _is_windows_drive(text[:2]):
        return False
    return len(text) == 2 or text[2] in "/\\?#"


def _shorten(url: _URL) -> None:
    """Pop one path segment, except a file URL's lone Windows drive letter."""

    if (
        url.scheme == "file"
        and len(url.path) == 1
        and _is_normalized_windows_drive(url.path[0])
    ):
        return
    if url.path:
        url.path.pop()


def _parse_file_host(text: str) -> str:
    host = _parse_host(text, special=True)
    if host == "localhost":
        return ""
    return host


def _parse_host(text: str, *, special: bool) -> str:
    if text.startswith("["):
        if not text.endswith("]") or len(text) < 2:
            raise URLParseError("invalid IPv6 host")
        try:
            address = ipaddress.IPv6Address(text[1:-1])
        except ipaddress.AddressValueError as exc:
            raise URLParseError("invalid IPv6 host") from exc
        packed = int(address)
        pieces = [(packed >> shift) & 0xFFFF for shift in (112, 96, 80, 64, 48, 32, 16, 0)]
        return "[" + _compress_ipv6(pieces) + "]"
    if special and text == "":
        raise URLParseError("empty host")
    ascii_domain = _domain_to_ascii(text)
    if _ends_in_a_number(ascii_domain):
        return _parse_ipv4(ascii_domain)
    return ascii_domain


def _ends_in_a_number(text: str) -> bool:
    if text == "":
        return False
    parts = text.split(".")
    if parts[-1] == "":
        if len(parts) == 1:
            return False
        parts.pop()
    return _ipv4_number(parts[-1]) is not None


def _ipv4_number(text: str) -> int | None:
    if text == "":
        return None
    if len(text) >= 2 and text[0] == "0" and text[1] in "xX":
        rest = text[2:]
        if rest == "" or any(char not in "0123456789abcdefABCDEF" for char in rest):
            return None
        return int(rest, 16)
    if len(text) >= 2 and text[0] == "0":
        if any(char not in "01234567" for char in text):
            return None
        return int(text, 8)
    if any(char not in "0123456789" for char in text):
        return None
    return int(text, 10)


def _parse_ipv4(text: str) -> str:
    parts = text.split(".")
    if parts and parts[-1] == "":
        if len(parts) == 1:
            raise URLParseError("invalid IPv4 host")
        parts.pop()
    if not parts or len(parts) > 4:
        raise URLParseError("invalid IPv4 host")
    numbers: list[int] = []
    for part in parts:
        number = _ipv4_number(part)
        if number is None:
            raise URLParseError("invalid IPv4 host")
        numbers.append(number)
    for number in numbers[:-1]:
        if number > 255:
            raise URLParseError("invalid IPv4 host")
    if numbers[-1] >= 256 ** (5 - len(numbers)):
        raise URLParseError("invalid IPv4 host")
    value = numbers[-1]
    for counter, number in enumerate(numbers[:-1]):
        value += number * 256 ** (3 - counter)
    octets = [(value >> shift) & 255 for shift in (24, 16, 8, 0)]
    return ".".join(str(octet) for octet in octets)


def _domain_to_ascii(text: str) -> str:
    """Domain to ASCII after UTF-8 percent-decoding.

    An ASCII domain is lowercased and then rejected when it still contains a
    forbidden domain code point such as ``%``. A non-ASCII domain goes through
    IDNA, which maps a soft hyphen away and rejects a label that becomes empty.
    """

    decoded = _percent_decode_utf8(text)
    if "\ufffd" in decoded:
        raise URLParseError("invalid domain")
    trailing = decoded.endswith(".")
    body = decoded[:-1] if trailing else decoded
    if body == "":
        result = "." if trailing else ""
    elif all(ord(char) < 128 for char in body):
        result = body.lower() + ("." if trailing else "")
    else:
        labels: list[str] = []
        try:
            for label in body.split("."):
                labels.append(label.encode("idna").decode("ascii") if label else "")
        except UnicodeError as exc:
            raise URLParseError("invalid domain") from exc
        result = ".".join(labels)
        if trailing:
            result += "."
    if result == "" or _has_forbidden_domain(result):
        raise URLParseError("forbidden host code point")
    return result


def _percent_decode_utf8(text: str) -> str:
    raw = text.encode("utf-8")
    output = bytearray()
    index = 0
    hex_digits = b"0123456789abcdefABCDEF"
    while index < len(raw):
        byte = raw[index]
        if (
            byte == 0x25
            and index + 2 < len(raw)
            and raw[index + 1] in hex_digits
            and raw[index + 2] in hex_digits
        ):
            output.append(int(raw[index + 1 : index + 3], 16))
            index += 3
            continue
        output.append(byte)
        index += 1
    return output.decode("utf-8", errors="replace")


def _has_forbidden_domain(text: str) -> bool:
    for char in text:
        code = ord(char)
        if code <= 0x1F or code == 0x7F or char in _FORBIDDEN_HOST or char == "%":
            return True
    return False


def _compress_ipv6(pieces: list[int]) -> str:
    best_at = -1
    best_length = 1
    index = 0
    while index < 8:
        if pieces[index] != 0:
            index += 1
            continue
        end = index
        while end < 8 and pieces[end] == 0:
            end += 1
        if end - index > best_length:
            best_at = index
            best_length = end - index
        index = end
    if best_at < 0:
        return ":".join(f"{piece:x}" for piece in pieces)
    left = ":".join(f"{piece:x}" for piece in pieces[:best_at])
    right = ":".join(f"{piece:x}" for piece in pieces[best_at + best_length :])
    return f"{left}::{right}"


def _serialize(url: _URL) -> str:
    output = url.scheme + ":"
    if url.host is not None:
        output += "//"
        if url.username or url.password:
            output += url.username
            if url.password:
                output += ":" + url.password
            output += "@"
        output += url.host
        if url.port is not None:
            output += ":" + str(url.port)
    if url.path:
        output += "".join("/" + segment for segment in url.path)
    elif url.host is not None:
        output += "/"
    if url.query is not None:
        output += "?" + url.query
    if url.fragment is not None:
        output += "#" + url.fragment
    return output
