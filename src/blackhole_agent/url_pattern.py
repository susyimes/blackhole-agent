"""Match URLs with the URL Pattern Standard.

A star is not a single path segment, and an omitted constructor field is not
always a wildcard. A named pathname group stops at the next slash, and an
optional group takes the slash in front of it: ``/products/:id?`` matches
``/products`` and ``/products/2`` and rejects ``/products/``. A named hostname
group stops at the next dot, so ``:name.example.com`` matches one label and
rejects ``a.b.example.com``. A full ``*`` crosses slashes. A relative pattern
resolves ``..`` against its base URL before it matches. When a constructor
string names a host and omits the port, only the default port matches; when
it names a hash and omits the search, the search must be empty. A
parenthesized group is a regular expression, not a capture of the parentheses.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Mapping

from blackhole_agent.whatwg_url import URLParseError, parse_href

_COMPONENTS = (
    "protocol",
    "username",
    "password",
    "hostname",
    "port",
    "pathname",
    "search",
    "hash",
)
_SPECIAL_SCHEMES = ("http", "https", "ws", "wss", "ftp", "file")
_DEFAULT_PORTS = {"http": "80", "https": "443", "ws": "80", "wss": "443", "ftp": "21"}
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+\-.]*\Z")
_QUERY_EXTRA = frozenset(' "<>#')
_FRAGMENT_EXTRA = frozenset(' "<>`')
_USERINFO_EXTRA = frozenset(' "<>#?`{}/:;=@[\\]^|')
_OPAQUE_EXTRA = frozenset(' "<>#?`{}')
_REGEXP_ESCAPES = frozenset(".+*?^${}()[]|/\\")
_PATTERN_ESCAPES = frozenset("+*?:{}()\\")
_FULL_WILDCARD = ".*"


class URLPatternError(ValueError):
    """The pattern is not a valid URL pattern."""


@dataclass(frozen=True)
class _Token:
    type: str
    index: int
    value: str


@dataclass
class _Part:
    type: str
    value: str
    modifier: str
    name: str = ""
    prefix: str = ""
    suffix: str = ""


@dataclass(frozen=True)
class _Options:
    delimiter: str
    prefix: str
    ignore_case: bool = False

    def with_ignore_case(self, ignore_case: bool) -> _Options:
        return _Options(self.delimiter, self.prefix, ignore_case)


_DEFAULT = _Options("", "")
_HOSTNAME = _Options(".", "")
_PATHNAME = _Options("/", "/")


@dataclass
class _Component:
    pattern: str
    expression: re.Pattern[str]
    names: tuple[str, ...]
    has_regexp: bool


def _percent_encode(char: str, extra: frozenset[str]) -> str:
    code = ord(char)
    if code < 0x20 or code > 0x7E or char in extra:
        return "".join(f"%{byte:02X}" for byte in char.encode("utf-8"))
    return char


def _encode(value: str, extra: frozenset[str]) -> str:
    return "".join(_percent_encode(char, extra) for char in value)


def _name_char(char: str, first: bool) -> bool:
    if char in {"$", "_"} or ("A" <= char <= "Z") or ("a" <= char <= "z"):
        return True
    if not first and "0" <= char <= "9":
        return True
    category = unicodedata.category(char)
    if first:
        return category in {"Lu", "Ll", "Lt", "Lm", "Lo", "Nl"}
    return category in {"Lu", "Ll", "Lt", "Lm", "Lo", "Nl", "Mn", "Mc", "Nd", "Pc"}


def _escape_regexp(value: str) -> str:
    if not value.isascii():
        raise URLPatternError("canonical pattern text is not ASCII")
    return "".join(("\\" + char if char in _REGEXP_ESCAPES else char) for char in value)


def _escape_pattern(value: str) -> str:
    if not value.isascii():
        raise URLPatternError("canonical pattern text is not ASCII")
    return "".join(("\\" + char if char in _PATTERN_ESCAPES else char) for char in value)


def _segment_wildcard(options: _Options) -> str:
    return "[^" + _escape_regexp(options.delimiter) + "]+?"


def _python_regexp(expression: str) -> str:
    # JavaScript accepts [^]+? for an empty delimiter and matches every
    # character. Python rejects that class, so compile the same meaning.
    return expression.replace("[^]+?", r"[\s\S]+?")


def _modifier_name(token: _Token | None) -> str:
    if token is None:
        return "none"
    if token.value == "?":
        return "optional"
    if token.value == "*":
        return "zero-or-more"
    if token.value == "+":
        return "one-or-more"
    raise URLPatternError("invalid modifier")


def _modifier_text(modifier: str) -> str:
    if modifier == "zero-or-more":
        return "*"
    if modifier == "optional":
        return "?"
    if modifier == "one-or-more":
        return "+"
    return ""


class _Tokenizer:
    def __init__(self, text: str, policy: str) -> None:
        self.text = text
        self.policy = policy
        self.index = 0
        self.next_index = 0
        self.code = ""
        self.tokens: list[_Token] = []

    def _read(self, index: int) -> None:
        self.next_index = index
        if self.next_index >= len(self.text):
            raise URLPatternError("read past the end of the pattern")
        self.code = self.text[self.next_index]
        self.next_index += 1

    def _add(self, kind: str, next_position: int, value_position: int, value_length: int) -> None:
        self.tokens.append(
            _Token(kind, self.index, self.text[value_position : value_position + value_length])
        )
        self.index = next_position

    def _add_span(self, kind: str, next_position: int, value_position: int) -> None:
        self._add(kind, next_position, value_position, next_position - value_position)

    def _error(self, next_position: int, value_position: int) -> None:
        if self.policy == "strict":
            raise URLPatternError("invalid pattern syntax")
        self._add_span("invalid-char", next_position, value_position)

    def run(self) -> list[_Token]:
        while self.index < len(self.text):
            self._read(self.index)
            code = self.code
            if code == "*":
                self._add_span("asterisk", self.next_index, self.index)
                continue
            if code in {"+", "?"}:
                self._add_span("other-modifier", self.next_index, self.index)
                continue
            if code == "\\":
                if self.index == len(self.text) - 1:
                    self._error(self.next_index, self.index)
                    continue
                escaped_at = self.next_index
                self._read(self.next_index)
                self._add_span("escaped-char", self.next_index, escaped_at)
                continue
            if code == "{":
                self._add_span("open", self.next_index, self.index)
                continue
            if code == "}":
                self._add_span("close", self.next_index, self.index)
                continue
            if code == ":":
                name_at = self.next_index
                name_start = name_at
                while name_at < len(self.text):
                    self._read(name_at)
                    if not _name_char(self.code, name_at == name_start):
                        break
                    name_at = self.next_index
                if name_at <= name_start:
                    self._error(name_start, self.index)
                    continue
                self._add_span("name", name_at, name_start)
                continue
            if code == "(":
                if not self._regexp():
                    continue
                continue
            self._add_span("char", self.next_index, self.index)
        self._add_span("end", self.index, self.index)
        return self.tokens

    def _regexp(self) -> bool:
        depth = 1
        position = self.next_index
        start = position
        while position < len(self.text):
            self._read(position)
            if not self.code.isascii():
                self._error(start, self.index)
                return False
            if position == start and self.code == "?":
                self._error(start, self.index)
                return False
            if self.code == "\\":
                if position == len(self.text) - 1:
                    self._error(start, self.index)
                    return False
                self._read(self.next_index)
                if not self.code.isascii():
                    self._error(start, self.index)
                    return False
                position = self.next_index
                continue
            if self.code == ")":
                depth -= 1
                if depth == 0:
                    position = self.next_index
                    break
            elif self.code == "(":
                depth += 1
                if position == len(self.text) - 1:
                    self._error(start, self.index)
                    return False
                temporary = self.next_index
                self._read(self.next_index)
                if self.code != "?":
                    self._error(start, self.index)
                    return False
                self.next_index = temporary
                position = self.next_index
                continue
            position = self.next_index
        if depth != 0:
            self._error(start, self.index)
            return False
        length = position - start - 1
        if length <= 0:
            self._error(start, self.index)
            return False
        self._add("regexp", position, start, length)
        return True


class _PatternParser:
    def __init__(self, tokens: list[_Token], options: _Options, encode: Callable[[str], str]) -> None:
        self.tokens = tokens
        self.options = options
        self.encode = encode
        self.segment = _segment_wildcard(options)
        self.parts: list[_Part] = []
        self.pending = ""
        self.index = 0
        self.numeric = 0

    def _peek(self, kind: str) -> _Token | None:
        token = self.tokens[self.index]
        if token.type != kind:
            return None
        self.index += 1
        return token

    def _regexp_or_wildcard(self, name: _Token | None) -> _Token | None:
        token = self._peek("regexp")
        if name is None and token is None:
            token = self._peek("asterisk")
        return token

    def _modifier(self) -> _Token | None:
        token = self._peek("other-modifier")
        if token is not None:
            return token
        return self._peek("asterisk")

    def _text(self) -> str:
        collected = ""
        while True:
            token = self._peek("char")
            if token is None:
                token = self._peek("escaped-char")
            if token is None:
                return collected
            collected += token.value

    def _flush(self) -> None:
        if not self.pending:
            return
        encoded = self.encode(self.pending)
        self.pending = ""
        self.parts.append(_Part("fixed-text", encoded, "none"))

    def _duplicate(self, name: str) -> bool:
        return any(part.name == name for part in self.parts)

    def _add_group(
        self,
        prefix: str,
        name: _Token | None,
        wildcard: _Token | None,
        suffix: str,
        modifier_token: _Token | None,
    ) -> None:
        modifier = _modifier_name(modifier_token)
        if name is None and wildcard is None and modifier == "none":
            self.pending += prefix
            return
        self._flush()
        if name is None and wildcard is None:
            if not prefix:
                return
            self.parts.append(_Part("fixed-text", self.encode(prefix), modifier))
            return
        if wildcard is None:
            regexp_value = self.segment
        elif wildcard.type == "asterisk":
            regexp_value = _FULL_WILDCARD
        else:
            regexp_value = wildcard.value
        kind = "regexp"
        if regexp_value == self.segment:
            kind = "segment-wildcard"
            regexp_value = ""
        elif regexp_value == _FULL_WILDCARD:
            kind = "full-wildcard"
            regexp_value = ""
        if name is not None:
            group_name = name.value
        else:
            group_name = str(self.numeric)
            self.numeric += 1
        if self._duplicate(group_name):
            raise URLPatternError("duplicate group name")
        self.parts.append(
            _Part(kind, regexp_value, modifier, group_name, self.encode(prefix), self.encode(suffix))
        )

    def parse(self) -> list[_Part]:
        while self.index < len(self.tokens):
            char = self._peek("char")
            name = self._peek("name")
            wildcard = self._regexp_or_wildcard(name)
            if name is not None or wildcard is not None:
                prefix = "" if char is None else char.value
                if prefix and prefix != self.options.prefix:
                    self.pending += prefix
                    prefix = ""
                self._flush()
                self._add_group(prefix, name, wildcard, "", self._modifier())
                continue
            fixed = char if char is not None else self._peek("escaped-char")
            if fixed is not None:
                self.pending += fixed.value
                continue
            if self._peek("open") is not None:
                prefix = self._text()
                name = self._peek("name")
                wildcard = self._regexp_or_wildcard(name)
                suffix = self._text()
                if self._peek("close") is None:
                    raise URLPatternError("unclosed pattern group")
                self._add_group(prefix, name, wildcard, suffix, self._modifier())
                continue
            self._flush()
            if self._peek("end") is None:
                raise URLPatternError("invalid pattern syntax")
        return self.parts


def _generate_regexp(parts: list[_Part], options: _Options) -> tuple[str, list[str]]:
    result = "^"
    names: list[str] = []
    for part in parts:
        if part.type == "fixed-text":
            escaped = _escape_regexp(part.value)
            if part.modifier == "none":
                result += escaped
            else:
                result += "(?:" + escaped + ")" + _modifier_text(part.modifier)
            continue
        names.append(part.name)
        if part.type == "segment-wildcard":
            regexp_value = _segment_wildcard(options)
        elif part.type == "full-wildcard":
            regexp_value = _FULL_WILDCARD
        else:
            regexp_value = part.value
        if not part.prefix and not part.suffix:
            if part.modifier in {"none", "optional"}:
                result += "(" + regexp_value + ")" + _modifier_text(part.modifier)
            else:
                result += "((?:" + regexp_value + ")" + _modifier_text(part.modifier) + ")"
            continue
        if part.modifier in {"none", "optional"}:
            result += (
                "(?:"
                + _escape_regexp(part.prefix)
                + "("
                + regexp_value
                + ")"
                + _escape_regexp(part.suffix)
                + ")"
                + _modifier_text(part.modifier)
            )
            continue
        result += (
            "(?:"
            + _escape_regexp(part.prefix)
            + "((?:"
            + regexp_value
            + ")(?:"
            + _escape_regexp(part.suffix)
            + _escape_regexp(part.prefix)
            + "(?:"
            + regexp_value
            + "))*)"
            + _escape_regexp(part.suffix)
            + ")"
        )
        if part.modifier == "zero-or-more":
            result += "?"
    return result + "$", names


def _needs_grouping(part: _Part, previous: _Part | None, nxt: _Part | None, options: _Options) -> bool:
    needs = bool(part.suffix) or bool(part.prefix and part.prefix != options.prefix)
    custom = not part.name[:1].isdigit()
    if (
        not needs
        and custom
        and part.type == "segment-wildcard"
        and part.modifier == "none"
        and nxt is not None
        and not nxt.prefix
        and not nxt.suffix
    ):
        if nxt.type == "fixed-text":
            needs = _name_char(nxt.value[0], False)
        else:
            needs = nxt.name[:1].isdigit()
    if (
        not needs
        and not part.prefix
        and previous is not None
        and previous.type == "fixed-text"
        and previous.value[-1:] == options.prefix
    ):
        needs = True
    return needs


def _generate_pattern(parts: list[_Part], options: _Options) -> str:
    result = ""
    for index, part in enumerate(parts):
        previous = parts[index - 1] if index else None
        nxt = parts[index + 1] if index + 1 < len(parts) else None
        if part.type == "fixed-text":
            if part.modifier == "none":
                result += _escape_pattern(part.value)
                continue
            result += "{" + _escape_pattern(part.value) + "}" + _modifier_text(part.modifier)
            continue
        custom = not part.name[:1].isdigit()
        grouped = _needs_grouping(part, previous, nxt, options)
        if grouped:
            result += "{"
        result += _escape_pattern(part.prefix)
        if custom:
            result += ":" + part.name
        if part.type == "regexp":
            result += "(" + part.value + ")"
        elif part.type == "segment-wildcard" and not custom:
            result += "(" + _segment_wildcard(options) + ")"
        elif part.type == "full-wildcard":
            bare = (
                not custom
                and (
                    previous is None
                    or previous.type == "fixed-text"
                    or previous.modifier != "none"
                    or grouped
                    or bool(part.prefix)
                )
            )
            if bare:
                result += "*"
            else:
                result += "(" + _FULL_WILDCARD + ")"
        if (
            part.type == "segment-wildcard"
            and custom
            and part.suffix
            and _name_char(part.suffix[0], False)
        ):
            result += "\\"
        result += _escape_pattern(part.suffix)
        if grouped:
            result += "}"
        result += _modifier_text(part.modifier)
    return result


def _compile_component(text: str, encode: Callable[[str], str], options: _Options) -> _Component:
    tokens = _Tokenizer(text, "strict").run()
    parts = _PatternParser(tokens, options, encode).parse()
    expression, names = _generate_regexp(parts, options)
    flags = re.IGNORECASE if options.ignore_case else 0
    try:
        compiled = re.compile(_python_regexp(expression), flags)
    except re.error as exc:
        raise URLPatternError("invalid pattern regular expression") from exc
    return _Component(
        _generate_pattern(parts, options),
        compiled,
        tuple(names),
        any(part.type == "regexp" for part in parts),
    )


def _canonicalize_protocol(value: str) -> str:
    if not value:
        return ""
    if _SCHEME.fullmatch(value) is None:
        raise URLPatternError("invalid protocol")
    return value.lower()


def _canonicalize_hostname(value: str) -> str:
    if not value:
        return ""
    try:
        serialized = parse_href("https://" + value + "/")
    except URLParseError as exc:
        raise URLPatternError("invalid hostname") from exc
    return _components(serialized)["hostname"]


def _canonicalize_ipv6(value: str) -> str:
    for char in value:
        if char not in "0123456789abcdefABCDEF[]:":
            raise URLPatternError("invalid IPv6 hostname")
    return value.lower()


def _canonicalize_port(value: str) -> str:
    if not value:
        return ""
    if not value.isascii() or not value.isdigit():
        raise URLPatternError("invalid port")
    number = int(value)
    if number > 65535:
        raise URLPatternError("invalid port")
    return str(number)


def _canonicalize_pathname(value: str) -> str:
    if not value:
        return ""
    leading = value.startswith("/")
    modified = value if leading else "/-" + value
    try:
        serialized = parse_href("https://dummy.invalid" + modified)
    except URLParseError as exc:
        raise URLPatternError("invalid pathname") from exc
    path = _components(serialized)["pathname"]
    if not leading:
        if len(path) < 2:
            raise URLPatternError("invalid pathname")
        path = path[2:]
    return path


def _canonicalize_opaque(value: str) -> str:
    return _encode(value, _OPAQUE_EXTRA)


def _canonicalize_search(value: str) -> str:
    return _encode(value, _QUERY_EXTRA)


def _canonicalize_hash(value: str) -> str:
    return _encode(value, _FRAGMENT_EXTRA)


def _canonicalize_userinfo(value: str) -> str:
    return _encode(value, _USERINFO_EXTRA)


def _is_ipv6_pattern(value: str) -> bool:
    if len(value) < 2:
        return False
    if value[0] == "[":
        return True
    if value[0] == "{" and value[1] == "[":
        return True
    return value[0] == "\\" and value[1] == "["


def _matches_special(component: _Component) -> bool:
    return any(component.expression.search(scheme) is not None for scheme in _SPECIAL_SCHEMES)


def _components(serialized: str) -> dict[str, str]:
    scheme, separator, rest = serialized.partition(":")
    if not separator:
        raise URLPatternError("invalid URL")
    username = password = hostname = port = ""
    if rest.startswith("//"):
        rest = rest[2:]
        cut = len(rest)
        for index, char in enumerate(rest):
            if char in "/?#":
                cut = index
                break
        authority = rest[:cut]
        rest = rest[cut:]
        if "@" in authority:
            userinfo, authority = authority.rsplit("@", 1)
            if ":" in userinfo:
                username, password = userinfo.split(":", 1)
            else:
                username = userinfo
        if authority.startswith("[") and "]" in authority:
            bracket = authority.find("]")
            hostname = authority[: bracket + 1]
            if bracket + 1 < len(authority) and authority[bracket + 1] == ":":
                port = authority[bracket + 2 :]
        elif ":" in authority:
            hostname, port = authority.rsplit(":", 1)
        else:
            hostname = authority
    fragment = ""
    query = ""
    if "#" in rest:
        rest, fragment = rest.split("#", 1)
    if "?" in rest:
        rest, query = rest.split("?", 1)
    return {
        "protocol": scheme,
        "username": username,
        "password": password,
        "hostname": hostname,
        "port": port,
        "pathname": rest,
        "search": query,
        "hash": fragment,
    }


def _strip_one_trailing(value: str, char: str) -> str:
    if value.endswith(char):
        return value[:-1]
    return value


def _strip_one_leading(value: str, char: str) -> str:
    if value.startswith(char):
        return value[1:]
    return value


def _absolute_pathname(value: str, kind: str) -> bool:
    if not value:
        return False
    if value[0] == "/":
        return True
    if kind == "url" or len(value) < 2:
        return False
    if value[0] == "\\" and value[1] == "/":
        return True
    return value[0] == "{" and value[1] == "/"


def _process_init(init: Mapping[str, str], kind: str) -> dict[str, str]:
    result: dict[str, str] = {}
    base: dict[str, str] | None = None
    if "baseURL" in init:
        try:
            base = _components(parse_href(init["baseURL"]))
        except URLParseError as exc:
            raise URLPatternError("invalid base URL") from exc
        if "protocol" not in init:
            result["protocol"] = base["protocol"] if kind != "pattern" else _escape_pattern(base["protocol"])
        if kind != "pattern" and not any(key in init for key in ("protocol", "hostname", "port", "username")):
            result["username"] = base["username"]
        if kind != "pattern" and not any(
            key in init for key in ("protocol", "hostname", "port", "username", "password")
        ):
            result["password"] = base["password"]
        if "protocol" not in init and "hostname" not in init:
            host = base["hostname"]
            result["hostname"] = host if kind != "pattern" else _escape_pattern(host)
        if not any(key in init for key in ("protocol", "hostname", "port")):
            result["port"] = base["port"]
        if not any(key in init for key in ("protocol", "hostname", "port", "pathname")):
            path = base["pathname"]
            result["pathname"] = path if kind != "pattern" else _escape_pattern(path)
        if not any(key in init for key in ("protocol", "hostname", "port", "pathname", "search")):
            search = base["search"]
            result["search"] = search if kind != "pattern" else _escape_pattern(search)
        if not any(key in init for key in ("protocol", "hostname", "port", "pathname", "search", "hash")):
            fragment = base["hash"]
            result["hash"] = fragment if kind != "pattern" else _escape_pattern(fragment)
    if "protocol" in init:
        result["protocol"] = _strip_one_trailing(init["protocol"], ":")
        if kind != "pattern":
            result["protocol"] = _canonicalize_protocol(result["protocol"])
    if "username" in init:
        result["username"] = init["username"] if kind == "pattern" else _canonicalize_userinfo(init["username"])
    if "password" in init:
        result["password"] = init["password"] if kind == "pattern" else _canonicalize_userinfo(init["password"])
    if "hostname" in init:
        result["hostname"] = init["hostname"] if kind == "pattern" else _canonicalize_hostname(init["hostname"])
    protocol = result.get("protocol", "")
    if "port" in init:
        result["port"] = init["port"] if kind == "pattern" else _canonicalize_port(init["port"])
    if "pathname" in init:
        pathname = init["pathname"]
        if base is not None and not _absolute_pathname(pathname, kind):
            base_path = base["pathname"] if kind != "pattern" else _escape_pattern(base["pathname"])
            slash = base_path.rfind("/")
            if slash != -1:
                pathname = base_path[: slash + 1] + pathname
        if kind == "pattern":
            result["pathname"] = pathname
        elif protocol in _SPECIAL_SCHEMES or protocol == "":
            result["pathname"] = _canonicalize_pathname(pathname)
        else:
            result["pathname"] = _canonicalize_opaque(pathname)
    if "search" in init:
        search = _strip_one_leading(init["search"], "?")
        result["search"] = search if kind == "pattern" else _canonicalize_search(search)
    if "hash" in init:
        fragment = _strip_one_leading(init["hash"], "#")
        result["hash"] = fragment if kind == "pattern" else _canonicalize_hash(fragment)
    return result


class _ConstructorParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = _Tokenizer(text, "lenient").run()
        self.result: dict[str, str] = {}
        self.token_index = 0
        self.token_increment = 1
        self.component_start = 0
        self.group_depth = 0
        self.ipv6_depth = 0
        self.special = False
        self.state = "init"

    def _token(self, index: int) -> _Token:
        if index < len(self.tokens):
            return self.tokens[index]
        return self.tokens[-1]

    def _current(self) -> _Token:
        return self.tokens[self.token_index]

    def _is_literal(self, index: int, value: str) -> bool:
        token = self._token(index)
        return token.value == value and token.type in {"char", "escaped-char", "invalid-char"}

    def _component_string(self) -> str:
        start = self._token(self.component_start).index
        end = self._current().index
        return self.text[start:end]

    def _rewind(self) -> None:
        self.token_index = self.component_start
        self.token_increment = 0

    def _change_state(self, new_state: str, skip: int) -> None:
        if self.state not in {"init", "authority", "done"}:
            self.result[self.state] = self._component_string()
        if self.state != "init" and new_state != "done":
            early = {"protocol", "authority", "username", "password"}
            if self.state in early and new_state in {"port", "pathname", "search", "hash"} and "hostname" not in self.result:
                self.result["hostname"] = ""
            if (
                self.state in early | {"hostname", "port"}
                and new_state in {"search", "hash"}
                and "pathname" not in self.result
            ):
                self.result["pathname"] = "/" if self.special else ""
            if (
                self.state in early | {"hostname", "port", "pathname"}
                and new_state == "hash"
                and "search" not in self.result
            ):
                self.result["search"] = ""
        self.state = new_state
        self.token_index += skip
        self.component_start = self.token_index
        self.token_increment = 0

    def _mark_special(self) -> None:
        protocol = self._component_string()
        compiled = _compile_component(protocol, _canonicalize_protocol, _DEFAULT)
        self.special = _matches_special(compiled)

    def _search_prefix(self) -> bool:
        if self._is_literal(self.token_index, "?"):
            return True
        if self._current().value != "?":
            return False
        previous = self.token_index - 1
        if previous < 0:
            return True
        return self._token(previous).type not in {"name", "regexp", "close", "asterisk"}

    def parse(self) -> dict[str, str]:
        while self.token_index < len(self.tokens):
            self.token_increment = 1
            token = self._current()
            if token.type == "end":
                if self.state == "init":
                    self._rewind()
                    if self._is_literal(self.token_index, "#"):
                        self._change_state("hash", 1)
                    elif self._search_prefix():
                        self._change_state("search", 1)
                    else:
                        self._change_state("pathname", 0)
                    self.token_index += self.token_increment
                    continue
                if self.state == "authority":
                    self._rewind()
                    self.state = "hostname"
                    self.token_index += self.token_increment
                    continue
                self._change_state("done", 0)
                break
            if token.type == "open":
                self.group_depth += 1
                self.token_index += self.token_increment
                continue
            if self.group_depth > 0:
                if token.type == "close":
                    self.group_depth -= 1
                else:
                    self.token_index += self.token_increment
                    continue
            self._state()
            self.token_index += self.token_increment
        if "hostname" in self.result and "port" not in self.result:
            self.result["port"] = ""
        return self.result

    def _state(self) -> None:
        state = self.state
        if state == "init":
            if self._is_literal(self.token_index, ":"):
                self._rewind()
                self.state = "protocol"
            return
        if state == "protocol":
            if not self._is_literal(self.token_index, ":"):
                return
            self._mark_special()
            next_state = "pathname"
            skip = 1
            if self._is_literal(self.token_index + 1, "/") and self._is_literal(self.token_index + 2, "/"):
                next_state = "authority"
                skip = 3
            elif self.special:
                next_state = "authority"
            self._change_state(next_state, skip)
            return
        if state == "authority":
            if self._is_literal(self.token_index, "@"):
                self._rewind()
                self.state = "username"
            elif (
                self._is_literal(self.token_index, "/")
                or self._search_prefix()
                or self._is_literal(self.token_index, "#")
            ):
                self._rewind()
                self.state = "hostname"
            return
        if state == "username":
            if self._is_literal(self.token_index, ":"):
                self._change_state("password", 1)
            elif self._is_literal(self.token_index, "@"):
                self._change_state("hostname", 1)
            return
        if state == "password":
            if self._is_literal(self.token_index, "@"):
                self._change_state("hostname", 1)
            return
        if state == "hostname":
            if self._is_literal(self.token_index, "["):
                self.ipv6_depth += 1
            elif self._is_literal(self.token_index, "]"):
                self.ipv6_depth -= 1
            elif self._is_literal(self.token_index, ":") and self.ipv6_depth == 0:
                self._change_state("port", 1)
            elif self._is_literal(self.token_index, "/"):
                self._change_state("pathname", 0)
            elif self._search_prefix():
                self._change_state("search", 1)
            elif self._is_literal(self.token_index, "#"):
                self._change_state("hash", 1)
            return
        if state == "port":
            if self._is_literal(self.token_index, "/"):
                self._change_state("pathname", 0)
            elif self._search_prefix():
                self._change_state("search", 1)
            elif self._is_literal(self.token_index, "#"):
                self._change_state("hash", 1)
            return
        if state == "pathname":
            if self._search_prefix():
                self._change_state("search", 1)
            elif self._is_literal(self.token_index, "#"):
                self._change_state("hash", 1)
            return
        if state == "search" and self._is_literal(self.token_index, "#"):
            self._change_state("hash", 1)


def _init_from(pattern: str | Mapping[str, str], base_url: str | None) -> dict[str, str]:
    if isinstance(pattern, str):
        init = _ConstructorParser(pattern).parse()
        if base_url is None and "protocol" not in init:
            raise URLPatternError("relative pattern needs a base URL")
        if base_url is not None:
            init["baseURL"] = base_url
        return init
    if not isinstance(pattern, Mapping):
        raise URLPatternError("pattern must be a string or component dictionary")
    if base_url is not None:
        raise URLPatternError("pass the base URL inside the component dictionary")
    init: dict[str, str] = {}
    for key, value in pattern.items():
        if key not in {* _COMPONENTS, "baseURL"}:
            continue
        if not isinstance(value, str):
            raise URLPatternError("pattern components must be strings")
        init[key] = value
    return init


def _build(pattern: str | Mapping[str, str], base_url: str | None, ignore_case: bool) -> dict[str, _Component]:
    if not isinstance(ignore_case, bool):
        raise URLPatternError("ignore_case must be a boolean")
    processed = _process_init(_init_from(pattern, base_url), "pattern")
    for name in _COMPONENTS:
        processed.setdefault(name, "*")
    if processed["port"] == _DEFAULT_PORTS.get(processed["protocol"], "\0"):
        processed["port"] = ""
    protocol = _compile_component(processed["protocol"], _canonicalize_protocol, _DEFAULT)
    username = _compile_component(processed["username"], _canonicalize_userinfo, _DEFAULT)
    password = _compile_component(processed["password"], _canonicalize_userinfo, _DEFAULT)
    if _is_ipv6_pattern(processed["hostname"]):
        hostname = _compile_component(processed["hostname"], _canonicalize_ipv6, _HOSTNAME)
    else:
        hostname = _compile_component(processed["hostname"], _canonicalize_hostname, _HOSTNAME)
    port = _compile_component(processed["port"], _canonicalize_port, _DEFAULT)
    cased = _DEFAULT.with_ignore_case(ignore_case)
    if _matches_special(protocol):
        pathname = _compile_component(
            processed["pathname"],
            _canonicalize_pathname,
            _PATHNAME.with_ignore_case(ignore_case),
        )
    else:
        pathname = _compile_component(processed["pathname"], _canonicalize_opaque, cased)
    search = _compile_component(processed["search"], _canonicalize_search, cased)
    fragment = _compile_component(processed["hash"], _canonicalize_hash, cased)
    return {
        "protocol": protocol,
        "username": username,
        "password": password,
        "hostname": hostname,
        "port": port,
        "pathname": pathname,
        "search": search,
        "hash": fragment,
    }


def _groups(component: _Component, matched: re.Match[str]) -> dict[str, str]:
    groups: dict[str, str] = {}
    for index, name in enumerate(component.names, start=1):
        value = matched.group(index)
        if value is not None:
            groups[name] = value
    return groups


class URLPattern:
    """One compiled URL pattern and the matches it accepts."""

    def __init__(
        self,
        pattern: str | Mapping[str, str],
        base_url: str | None = None,
        *,
        ignore_case: bool = False,
    ) -> None:
        components = _build(pattern, base_url, ignore_case)
        self._components = components
        self.protocol = components["protocol"].pattern
        self.username = components["username"].pattern
        self.password = components["password"].pattern
        self.hostname = components["hostname"].pattern
        self.port = components["port"].pattern
        self.pathname = components["pathname"].pattern
        self.search = components["search"].pattern
        self.hash = components["hash"].pattern
        self.has_regexp_groups = any(item.has_regexp for item in components.values())

    def exec(self, url: str, base_url: str | None = None) -> dict[str, object] | None:
        """Return the component captures, or None when the URL does not match."""

        if not isinstance(url, str):
            raise URLPatternError("URL must be a string")
        inputs: list[str] = [url]
        parsed_base: str | None = None
        if base_url is not None:
            if not isinstance(base_url, str):
                raise URLPatternError("base URL must be a string")
            try:
                parse_href(base_url)
            except URLParseError:
                return None
            parsed_base = base_url
            inputs.append(base_url)
        try:
            record = _components(parse_href(url, parsed_base))
        except URLParseError:
            return None
        result: dict[str, object] = {"inputs": inputs}
        for name in _COMPONENTS:
            component = self._components[name]
            matched = component.expression.search(record[name])
            if matched is None:
                return None
            result[name] = {"input": record[name], "groups": _groups(component, matched)}
        return result

    def test(self, url: str, base_url: str | None = None) -> bool:
        """Return whether every component of the URL matches."""

        return self.exec(url, base_url) is not None
