"""Decide whether a document may use a policy-controlled feature.

A Permissions-Policy header is not a Content Security Policy source list
and an iframe ``allow`` attribute cannot outrank its parent. This follows
the Permissions Policy algorithms for a declared header, a container
policy, and default allowlists: an empty allowlist disables the feature,
a host wildcard does not match its apex, a port wildcard matches only that
host, and a child response cannot turn a feature back on after the parent
disabled it.

The supported features are the ones whose default allowlist this module
knows. An unrecognized feature is disabled. No report is queued and no
request is fetched.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Mapping, Sequence

from blackhole_agent.structured_fields import StructuredFieldError, parse_structured_field
from blackhole_agent.whatwg_url import URLParseError, parse_href

_DEFAULTS = {
    "camera": "self",
    "fullscreen": "self",
    "geolocation": "self",
    "microphone": "self",
    "payment": "self",
    "sync-xhr": "*",
    "usb": "self",
}
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*\Z")
_HOST_LABEL = re.compile(r"[A-Za-z0-9-]+\Z")
_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}
_Header = str | Sequence[str]


class PermissionsPolicyError(ValueError):
    """A document or embedding URL cannot be given an origin."""


class _Origin:
    __slots__ = ("host", "opaque", "port", "scheme")

    def __init__(self, scheme: str, host: str, port: int | None, *, opaque: bool = False) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port
        self.opaque = opaque


class _Allow:
    __slots__ = ("expressions", "self_origin", "src_origin", "star")

    def __init__(self) -> None:
        self.star = False
        self.self_origin: _Origin | None = None
        self.src_origin: _Origin | None = None
        self.expressions: list[str] = []


class _Policy:
    __slots__ = ("declared", "document", "inherited", "reports")

    def __init__(
        self,
        inherited: dict[str, str],
        declared: dict[str, _Allow],
        reports: dict[str, str],
        document: _Origin,
    ) -> None:
        self.inherited = inherited
        self.declared = declared
        self.reports = reports
        self.document = document


def feature_enabled(
    feature: str,
    document: str,
    header: _Header = "",
    *,
    parent_document: str = "",
    parent_header: _Header = "",
    allow: str = "",
    src: str = "",
    sandbox: str | None = None,
    srcdoc: bool = False,
    allowfullscreen: bool = False,
    for_origin: str = "",
) -> dict[str, object]:
    """Return whether ``feature`` is enabled for a document or embedding.

    ``header`` is this document's ``Permissions-Policy`` value. When
    ``parent_document`` is set, the document is a child navigable: ``allow``
    and ``allowfullscreen`` are the iframe container, ``src`` is the iframe
    source, and ``sandbox`` set without ``allow-same-origin`` makes the
    origin opaque. ``for_origin`` asks about another origin under this
    document's policy; omitted, the document's own origin is used.
    """

    name = _feature_name(feature)
    if name not in _DEFAULTS:
        return _answer(False, recognized=False, inherited="", declared=False, default="", report_to="")
    parent = _document_origin(parent_document) if parent_document else None
    if parent_document and parent is None:
        raise PermissionsPolicyError("parent document must be a tuple origin")
    opaque = _sandboxed(sandbox)
    child_origin = _document_origin(document)
    if srcdoc:
        if parent is None:
            raise PermissionsPolicyError("srcdoc requires a parent document")
        child_origin = parent
    if opaque:
        child_origin = _Origin("", "", None, opaque=True)
    if parent is None:
        policy = _top_policy(child_origin, header)
    else:
        parent_policy = _top_policy(parent, parent_header)
        declared_origin = _declared_origin(parent, src=src, srcdoc=srcdoc)
        if opaque:
            declared_origin = child_origin
        container = _container_policy(
            allow,
            parent,
            declared_origin,
            allowfullscreen=allowfullscreen,
        )
        policy = _child_policy(parent_policy, parent, child_origin, container, header)
    queried = _query_origin(for_origin) if for_origin else child_origin
    state = _check(policy, name, queried)
    return _answer(
        state == "Enabled",
        recognized=True,
        inherited=policy.inherited[name],
        declared=name in policy.declared,
        default=_DEFAULTS[name],
        report_to=policy.reports.get(name, ""),
    )


def _answer(
    enabled: bool,
    *,
    recognized: bool,
    inherited: str,
    declared: bool,
    default: str,
    report_to: str,
) -> dict[str, object]:
    return {
        "enabled": enabled,
        "recognized": recognized,
        "inherited": inherited,
        "declared": declared,
        "default_allowlist": default,
        "report_to": report_to,
    }


def _feature_name(feature: str) -> str:
    if not isinstance(feature, str) or not feature.strip():
        raise PermissionsPolicyError("feature must be a non-empty string")
    return feature.strip().lower()


def _sandboxed(sandbox: str | None) -> bool:
    if sandbox is None:
        return False
    tokens = {token.lower() for token in sandbox.split()}
    return "allow-same-origin" not in tokens


def _document_origin(url: str) -> _Origin:
    if not isinstance(url, str) or not url.strip():
        raise PermissionsPolicyError("document URL must be a non-empty string")
    try:
        return _origin_from_url(url)
    except URLParseError as exc:
        raise PermissionsPolicyError(str(exc)) from exc


def _query_origin(url: str) -> _Origin:
    if url == "null":
        return _Origin("", "", None, opaque=True)
    try:
        return _origin_from_url(url)
    except URLParseError as exc:
        raise PermissionsPolicyError(str(exc)) from exc


def _declared_origin(parent: _Origin, *, src: str, srcdoc: bool) -> _Origin:
    if srcdoc or not src:
        return parent
    try:
        return _origin_from_url(src)
    except URLParseError:
        return parent


def _origin_from_url(url: str) -> _Origin:
    serialized = parse_href(url)
    scheme, separator, rest = serialized.partition(":")
    if separator != ":" or not rest.startswith("//"):
        raise URLParseError("URL has no authority")
    authority = rest[2:].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    host, port = _split_authority(authority)
    if port is not None and port == _DEFAULT_PORTS.get(scheme):
        port = None
    return _Origin(scheme, host, port)


def _split_authority(authority: str) -> tuple[str, int | None]:
    if authority.startswith("["):
        end = authority.find("]")
        if end < 0:
            raise URLParseError("IPv6 host is truncated")
        host = authority[: end + 1]
        if authority[end + 1 :] == "":
            return host, None
        if not authority[end + 1 :].startswith(":"):
            raise URLParseError("IPv6 host is truncated")
        return host, _port_number(authority[end + 2 :])
    host, separator, port_text = authority.rpartition(":")
    if not separator:
        return authority, None
    return host, _port_number(port_text)


def _port_number(text: str) -> int:
    if not text.isascii() or not text.isdigit():
        raise URLParseError("invalid port")
    value = int(text)
    if value > 65535:
        raise URLParseError("invalid port")
    return value


def _top_policy(origin: _Origin, header: _Header) -> _Policy:
    inherited = {name: "Enabled" for name in _DEFAULTS}
    declared, reports = _header_policy(header, origin)
    kept = {name: allow for name, allow in declared.items() if inherited[name] == "Enabled"}
    return _Policy(inherited, kept, reports, origin)


def _child_policy(
    parent: _Policy,
    parent_origin: _Origin,
    child: _Origin,
    container: dict[str, _Allow],
    header: _Header,
) -> _Policy:
    inherited = {
        name: _inherit(name, parent, parent_origin, child, container) for name in _DEFAULTS
    }
    declared, reports = _header_policy(header, child)
    kept = {name: allow for name, allow in declared.items() if inherited[name] == "Enabled"}
    kept_reports = {name: endpoint for name, endpoint in reports.items() if name in kept}
    return _Policy(inherited, kept, kept_reports, child)


def _inherit(
    feature: str,
    parent: _Policy,
    parent_origin: _Origin,
    child: _Origin,
    container: Mapping[str, _Allow],
) -> str:
    if _feature_value(parent, feature, parent_origin) == "Disabled":
        return "Disabled"
    if _feature_value(parent, feature, child) == "Disabled":
        return "Disabled"
    if feature in container:
        return "Enabled" if _matches(container[feature], child) else "Disabled"
    if _DEFAULTS[feature] == "*":
        return "Enabled"
    if _DEFAULTS[feature] == "self" and _same_origin(child, parent_origin):
        return "Enabled"
    return "Disabled"


def _feature_value(policy: _Policy, feature: str, origin: _Origin) -> str:
    if policy.inherited.get(feature) == "Disabled":
        return "Disabled"
    if feature in policy.declared:
        return "Enabled" if _matches(policy.declared[feature], origin) else "Disabled"
    return "Enabled"


def _check(policy: _Policy, feature: str, origin: _Origin) -> str:
    if policy.inherited.get(feature) == "Disabled":
        return "Disabled"
    if feature in policy.declared:
        return "Enabled" if _matches(policy.declared[feature], origin) else "Disabled"
    if _DEFAULTS[feature] == "*":
        return "Enabled"
    if _DEFAULTS[feature] == "self" and _same_origin(origin, policy.document):
        return "Enabled"
    return "Disabled"


def _matches(allow: _Allow, origin: _Origin) -> bool:
    if allow.star:
        return True
    if allow.self_origin is not None and _same_origin(allow.self_origin, origin):
        return True
    if allow.src_origin is not None and _same_origin(allow.src_origin, origin):
        return True
    if origin.opaque:
        return False
    return any(_expression_matches(origin, expression) for expression in allow.expressions)


def _same_origin(left: _Origin, right: _Origin) -> bool:
    if left.opaque or right.opaque:
        return left.opaque and right.opaque and left is right
    return left.scheme == right.scheme and left.host == right.host and left.port == right.port


def _header_policy(header: _Header, origin: _Origin) -> tuple[dict[str, _Allow], dict[str, str]]:
    if header == "" or header == ():
        return {}, {}
    try:
        parsed = parse_structured_field(header, "dictionary")
    except StructuredFieldError:
        return {}, {}
    if not isinstance(parsed, list):
        return {}, {}
    declared: dict[str, _Allow] = {}
    reports: dict[str, str] = {}
    for entry in parsed:
        if not isinstance(entry, list) or len(entry) != 2:
            continue
        feature, member = entry
        if not isinstance(feature, str) or feature not in _DEFAULTS or not isinstance(member, list):
            continue
        if len(member) != 2:
            continue
        allow = _allow_from_member(member[0], origin)
        if allow is None:
            continue
        declared[feature] = allow
        endpoint = _report_to(member[1])
        if endpoint:
            reports[feature] = endpoint
    return declared, reports


def _allow_from_member(value: object, origin: _Origin) -> _Allow | None:
    if isinstance(value, list):
        allow = _Allow()
        if any(_token(item[0]) == "*" for item in value if isinstance(item, list) and item):
            allow.star = True
            return allow
        for item in value:
            if not isinstance(item, list) or not item:
                continue
            _add_header_item(allow, item[0], origin)
        return allow
    token = _token(value)
    if token == "*":
        allow = _Allow()
        allow.star = True
        return allow
    if token == "self":
        allow = _Allow()
        allow.self_origin = origin
        return allow
    if isinstance(value, str) and _source_expression(value) is not None:
        allow = _Allow()
        allow.expressions.append(value)
        return allow
    return None


def _add_header_item(allow: _Allow, bare: object, origin: _Origin) -> None:
    token = _token(bare)
    if token == "self":
        allow.self_origin = origin
        return
    if isinstance(bare, str) and _source_expression(bare) is not None:
        allow.expressions.append(bare)


def _token(value: object) -> str:
    if isinstance(value, dict) and value.get("__type") == "token":
        return str(value.get("value") or "")
    return ""


def _report_to(parameters: object) -> str:
    if not isinstance(parameters, list):
        return ""
    for parameter in parameters:
        if not isinstance(parameter, list) or len(parameter) != 2 or parameter[0] != "report-to":
            continue
        return _token(parameter[1])
    return ""


def _container_policy(
    allow_text: str,
    parent: _Origin,
    target: _Origin,
    *,
    allowfullscreen: bool,
) -> dict[str, _Allow]:
    directive = _parse_allow(allow_text, parent, target)
    if allowfullscreen and "fullscreen" not in directive:
        star = _Allow()
        star.star = True
        directive["fullscreen"] = star
    return directive


def _parse_allow(value: str, container: _Origin, target: _Origin) -> dict[str, _Allow]:
    if not isinstance(value, str):
        raise PermissionsPolicyError("allow attribute must be a string")
    directive: dict[str, _Allow] = {}
    for serialized in value.split(";"):
        tokens = serialized.split()
        if not tokens:
            continue
        feature = tokens[0].lower()
        if feature not in _DEFAULTS or feature in directive:
            continue
        targetlist = tokens[1:]
        allow = _Allow()
        if any(item == "*" for item in targetlist):
            allow.star = True
        else:
            if not targetlist:
                allow.src_origin = target
            for element in targetlist:
                folded = element.lower()
                if folded == "'self'":
                    allow.self_origin = container
                    continue
                if folded == "'src'":
                    allow.src_origin = target
                    continue
                origin = _allow_origin(element)
                if origin is not None:
                    allow.expressions.append(_serialize(origin))
        directive[feature] = allow
    return directive


def _allow_origin(element: str) -> _Origin | None:
    try:
        serialized = parse_href(element)
    except URLParseError:
        return None
    if serialized.startswith("blob:") or _has_userinfo(serialized):
        return None
    try:
        return _origin_from_url(serialized)
    except URLParseError:
        return None


def _has_userinfo(serialized: str) -> bool:
    rest = serialized.split("://", 1)[-1]
    authority = rest.split("/", 1)[0]
    return "@" in authority


def _serialize(origin: _Origin) -> str:
    if origin.port is None:
        return f"{origin.scheme}://{origin.host}"
    return f"{origin.scheme}://{origin.host}:{origin.port}"


def _expression_matches(origin: _Origin, expression: str) -> bool:
    parsed = _source_expression(expression)
    if parsed is None:
        return False
    kind, scheme, host, port, path = parsed
    if kind == "scheme":
        return _scheme_matches(scheme or "", origin.scheme)
    if scheme is not None and not _scheme_matches(scheme, origin.scheme):
        return False
    if not _host_matches(host, origin.host):
        return False
    if not _port_matches(port, origin):
        return False
    return path in ("", "/")


def _source_expression(
    expression: str,
) -> tuple[str, str | None, str, str | None, str] | None:
    if not isinstance(expression, str) or not expression or any(char in expression for char in " \t\n\r"):
        return None
    if expression.endswith(":") and expression.count(":") == 1:
        scheme = expression[:-1]
        if _SCHEME.fullmatch(scheme):
            return ("scheme", scheme.lower(), "", None, "")
        return None
    scheme: str | None = None
    rest = expression
    if "://" in expression:
        scheme_text, _, rest = expression.partition("://")
        if not _SCHEME.fullmatch(scheme_text) or "@" in rest.split("/", 1)[0]:
            return None
        scheme = scheme_text.lower()
    path = ""
    if "/" in rest:
        rest, _, tail = rest.partition("/")
        path = "/" + tail
    port: str | None = None
    host = rest
    if host.startswith("["):
        end = host.find("]")
        if end < 0:
            return None
        port_text = host[end + 1 :]
        host = host[: end + 1]
        if port_text:
            if not port_text.startswith(":"):
                return None
            port = port_text[1:]
    elif ":" in host:
        host, _, port = host.rpartition(":")
    if port is not None and port != "*" and (not port.isascii() or not port.isdigit()):
        return None
    if not _valid_host(host):
        return None
    return ("host", scheme, host, port, path)


def _valid_host(host: str) -> bool:
    if host == "*":
        return True
    if host.startswith("[") and host.endswith("]"):
        try:
            ipaddress.ip_address(host[1:-1])
        except ValueError:
            return False
        return True
    body = host[2:] if host.startswith("*.") else host
    if body.endswith("."):
        body = body[:-1]
    if not body or (host.startswith("*") and not host.startswith("*.")):
        return False
    try:
        ipaddress.ip_address(body)
        return not host.startswith("*.")
    except ValueError:
        return all(_HOST_LABEL.fullmatch(label) for label in body.split("."))


def _scheme_matches(expression: str, url_scheme: str) -> bool:
    left = expression.lower()
    right = url_scheme.lower()
    if left == right:
        return True
    if left == "http" and right == "https":
        return True
    if left == "ws" and right in {"wss", "http", "https"}:
        return True
    return left == "wss" and right == "https"


def _host_matches(pattern: str, host: str) -> bool:
    folded = pattern.lower()
    actual = host.lower()
    if folded == "*":
        return True
    if folded.startswith("*."):
        if _ip(actual):
            return False
        suffix = folded[1:]
        return actual.endswith(suffix) and actual != suffix[1:]
    if _ip(folded) or _ip(actual):
        return _ip_equal(folded, actual)
    return folded == actual


def _ip(host: str) -> bool:
    text = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _ip_equal(left: str, right: str) -> bool:
    def address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        text = value[1:-1] if value.startswith("[") and value.endswith("]") else value
        return ipaddress.ip_address(text)

    try:
        return address(left) == address(right)
    except ValueError:
        return False


def _port_matches(port: str | None, origin: _Origin) -> bool:
    if port == "*":
        return True
    expected = None if port is None else int(port)
    if expected == origin.port:
        return True
    default = _DEFAULT_PORTS.get(origin.scheme)
    if origin.port is None:
        return expected == default
    return expected is None and origin.port == default
