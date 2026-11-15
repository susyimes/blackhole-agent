"""Rewrite one HTTP redirect the way the Fetch standard does.

``urllib`` treats a redirect as the same request pointed at a new URL, and it
stops following once the method is not GET or HEAD. Fetch does not. A 301 or
302 rewrites only ``POST`` into ``GET``. A 303 rewrites every method except
``GET`` and ``HEAD``. A 307 or 308 keeps the method and the body. Rewriting
to ``GET`` removes the request-body headers and leaves ``Content-Length``.
The first cross-origin hop removes ``Authorization``. A ``wss`` location is
not an HTTP(S) scheme, so it is a network error. The twentieth redirect is
rejected before the count increments; a body that cannot be replayed is
rejected after it increments, except for 303, which drops the body first.

This is one redirect step. It does not perform the next network fetch and it
does not change the request's referrer policy.
"""

from __future__ import annotations

from typing import Sequence

from blackhole_agent.whatwg_url import URLParseError, parse_href

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_HTTP_SCHEMES = frozenset({"http", "https"})
_BODY_HEADERS = frozenset(
    {"content-encoding", "content-language", "content-location", "content-type"}
)
_AUTHORIZATION = "authorization"
_MAX_REDIRECTS = 20


def follow_redirect(
    method: str,
    url: str,
    status: int,
    response_headers: Sequence[tuple[str, str]],
    request_headers: Sequence[tuple[str, str]] = (),
    body: bytes | None = None,
    *,
    replayable: bool = True,
    redirect_count: int = 0,
    redirect_mode: str = "follow",
    mode: str = "cors",
    origin: str | None = None,
    tainting: str = "basic",
) -> dict[str, object]:
    """Return the next request, the original response, or a network error.

    ``origin`` is the request's origin. ``None`` uses the current URL's
    origin. ``"null"`` is an opaque origin. ``replayable`` is false when the
    body has no source that can be sent again. ``redirect_count`` is the
    number of redirects already followed.
    """

    checked = _inputs(
        method,
        url,
        status,
        response_headers,
        request_headers,
        body,
        redirect_count,
        redirect_mode,
        mode,
        tainting,
    )
    if checked is not None:
        return checked
    assert body is None or isinstance(body, bytes)
    headers = [(str(name), str(value)) for name, value in request_headers]
    if status not in _REDIRECT_STATUSES:
        return _view(
            "response",
            "not-redirect",
            method,
            url,
            body,
            headers,
            redirect_count,
            status,
        )
    if redirect_mode == "error":
        return _view("network-error", "redirect-mode", method, url, body, headers, redirect_count, None)
    if redirect_mode == "manual" and mode != "navigate":
        return _view("opaque-redirect", "opaque-redirect", method, url, None, [], redirect_count, 0)
    if redirect_mode == "manual":
        return _view(
            "manual-redirect",
            "deferred",
            method,
            url,
            body,
            headers,
            redirect_count,
            status,
        )
    if redirect_mode != "follow":
        return _view("network-error", "redirect-mode", method, url, body, headers, redirect_count, None)

    location, location_error = _location_url(status, response_headers, url)
    if location_error == "null":
        return _view("response", "no-location", method, url, body, headers, redirect_count, status)
    if location_error == "failure":
        return _view(
            "network-error",
            "invalid-location",
            method,
            url,
            body,
            headers,
            redirect_count,
            None,
        )
    assert location is not None
    if _scheme(location) not in _HTTP_SCHEMES:
        return _view(
            "network-error",
            "non-http-scheme",
            method,
            url,
            body,
            headers,
            redirect_count,
            None,
        )
    if redirect_count == _MAX_REDIRECTS:
        return _view(
            "network-error",
            "redirect-count",
            method,
            url,
            body,
            headers,
            redirect_count,
            None,
        )

    redirect_count += 1
    request_origin = _origin(origin) if origin is not None else _origin(url)
    location_origin = _origin(location)
    if (
        mode == "cors"
        and _has_credentials(location)
        and not _same_origin(request_origin, location_origin)
    ):
        return _view(
            "network-error",
            "cors-credentials",
            method,
            url,
            body,
            headers,
            redirect_count,
            None,
        )
    if tainting == "cors" and _has_credentials(location):
        return _view(
            "network-error",
            "cors-tainted-credentials",
            method,
            url,
            body,
            headers,
            redirect_count,
            None,
        )
    if status != 303 and body is not None and not replayable:
        return _view(
            "network-error",
            "unreplayable-body",
            method,
            url,
            body,
            headers,
            redirect_count,
            None,
        )

    if (status in {301, 302} and method == "POST") or (
        status == 303 and method not in {"GET", "HEAD"}
    ):
        method = "GET"
        body = None
        headers = _delete(headers, _BODY_HEADERS)
    if not _same_origin(_origin(url), location_origin):
        headers = _delete(headers, frozenset({_AUTHORIZATION}))
    return _view(
        "next-request",
        "followed",
        method,
        location,
        body,
        headers,
        redirect_count,
        None,
    )


def _inputs(
    method: object,
    url: object,
    status: object,
    response_headers: object,
    request_headers: object,
    body: object,
    redirect_count: object,
    redirect_mode: object,
    mode: object,
    tainting: object,
) -> dict[str, object] | None:
    if (
        not isinstance(method, str)
        or not isinstance(url, str)
        or type(status) is not int
        or not isinstance(redirect_mode, str)
        or not isinstance(mode, str)
        or not isinstance(tainting, str)
        or type(redirect_count) is not int
        or redirect_count < 0
        or not isinstance(body, (bytes, type(None)))
        or not _header_pairs(response_headers)
        or not _header_pairs(request_headers)
    ):
        return _view("network-error", "invalid-input", "", "", None, [], 0, None)
    return None


def _header_pairs(headers: object) -> bool:
    if not isinstance(headers, Sequence) or isinstance(headers, (str, bytes)):
        return False
    return all(
        isinstance(item, tuple)
        and len(item) == 2
        and isinstance(item[0], str)
        and isinstance(item[1], str)
        for item in headers
    )


def _location_url(
    status: int,
    response_headers: Sequence[tuple[str, str]],
    response_url: str,
) -> tuple[str | None, str | None]:
    if status not in _REDIRECT_STATUSES:
        return None, "null"
    values = [
        value
        for name, value in response_headers
        if name.lower() == "location"
    ]
    if not values:
        return None, "null"
    if len(values) != 1 or any(char in values[0] for char in "\x00\r\n"):
        return None, "failure"
    try:
        parsed = parse_href(values[0], response_url)
        current = parse_href(response_url)
    except URLParseError:
        return None, "failure"
    if _fragment(parsed) is None:
        request_fragment = _fragment(current)
        if request_fragment is not None:
            parsed += "#" + request_fragment
    return parsed, None


def _fragment(serialized: str) -> str | None:
    if "#" not in serialized:
        return None
    return serialized.split("#", 1)[1]


def _scheme(serialized: str) -> str:
    return serialized.split(":", 1)[0]


def _origin(value: str | None) -> str | None:
    if value is None or value == "" or value == "null":
        return None
    try:
        serialized = parse_href(value)
    except URLParseError:
        return None
    bare = serialized.split("#", 1)[0].split("?", 1)[0]
    if "://" not in bare:
        return None
    scheme, rest = bare.split("://", 1)
    if scheme not in _HTTP_SCHEMES:
        return None
    authority = rest.split("/", 1)[0]
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    if authority == "":
        return None
    return f"{scheme}://{authority}"


def _same_origin(left: str | None, right: str | None) -> bool:
    return left is not None and left == right


def _has_credentials(serialized: str) -> bool:
    bare = serialized.split("#", 1)[0].split("?", 1)[0]
    if "://" not in bare:
        return False
    authority = bare.split("://", 1)[1].split("/", 1)[0]
    if "@" not in authority:
        return False
    userinfo = authority.rsplit("@", 1)[0]
    if ":" not in userinfo:
        return userinfo != ""
    username, password = userinfo.split(":", 1)
    return username != "" or password != ""


def _delete(
    headers: list[tuple[str, str]],
    names: frozenset[str],
) -> list[tuple[str, str]]:
    return [pair for pair in headers if pair[0].lower() not in names]


def _view(
    kind: str,
    reason: str,
    method: str,
    url: str,
    body: bytes | None,
    headers: list[tuple[str, str]],
    redirect_count: int,
    status: int | None,
) -> dict[str, object]:
    return {
        "type": kind,
        "reason": reason,
        "method": method,
        "url": url,
        "body": None if body is None else body.decode("latin-1"),
        "headers": [[name, value] for name, value in headers],
        "redirect_count": redirect_count,
        "status": status,
    }
