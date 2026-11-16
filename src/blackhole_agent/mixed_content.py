"""Upgrade or block a subresource as mixed content.

Content Security Policy can allow an ``http:`` image that this check still
rewrites, and it does not treat a loopback embedder as a secure context.
The decision follows Mixed Content (editor's draft algorithms 4.1, 4.3,
4.4, and 4.5) and Secure Contexts for potentially trustworthy URLs:

- an ``http`` image, audio, or video on a restricting page is rewritten to
  ``https`` and the explicit port is kept
- an IP-address host is not rewritten, then the insecure URL is blocked
- an ``imageset`` image is not rewritten
- ``https``, ``wss``, ``file``, ``data:``, ``about:blank``, ``about:srcdoc``,
  ``127.0.0.0/8``, ``::1``, and ``localhost`` names are potentially
  trustworthy
- a framed document restricts mixed content when any ancestor origin is
  trustworthy; a worker does not walk ancestors
- a top-level document navigation is allowed; the response URL is judged
  separately, so an ``https`` request that comes back as ``http`` is blocked

User opt-out of blocking is ``allow_mixed``. It does not disable upgrades.
"""

from __future__ import annotations

import ipaddress
from typing import Mapping, Sequence

from blackhole_agent.whatwg_url import URLParseError, parse_href

_UPGRADEABLE = frozenset({"image", "audio", "video"})
_LOOPBACK_V4 = ipaddress.ip_network("127.0.0.0/8")
_LOOPBACK_V6 = ipaddress.ip_network("::1/128")


def load_mixed_content(
    document_url: str,
    request_url: str,
    *,
    destination: str = "script",
    initiator: str = "",
    ancestors: Sequence[str] = (),
    kind: str = "window",
    parent: bool = True,
    response_url: str | None = None,
    allow_mixed: bool = False,
) -> dict[str, object]:
    """Return the upgrade and block decision for one subresource load.

    ``request`` and ``response`` are ``allowed`` or ``blocked``. ``response``
    is empty when ``response_url`` is omitted. ``url`` is the request URL
    after a possible upgrade. ``prohibits`` is true when the document's
    settings restrict mixed content.
    """

    if not isinstance(document_url, str) or not isinstance(request_url, str):
        raise TypeError("mixed content URLs must be strings")
    if kind not in {"window", "worker"}:
        raise ValueError("mixed content kind must be window or worker")
    if response_url is not None and not isinstance(response_url, str):
        raise TypeError("mixed content response URL must be a string")
    place = destination.strip().lower()
    who = initiator.strip().lower()
    document = _parse_url(document_url, base=None)
    prohibits = _origin_trustworthy(document)
    if kind == "window":
        prohibits = prohibits or any(
            _origin_trustworthy(_parse_url(item, base=None)) for item in ancestors
        )
    request = _maybe_upgrade(
        _parse_url(request_url, base=document_url),
        destination=place,
        initiator=who,
        prohibits=prohibits,
    )
    response = ""
    if response_url is not None:
        arrived = _parse_url(response_url, base=document_url)
        response = _block_state(
            arrived,
            destination=place,
            prohibits=prohibits,
            parent=parent,
            allow_mixed=allow_mixed,
        )
    return {
        "request": _block_state(
            request,
            destination=place,
            prohibits=prohibits,
            parent=parent,
            allow_mixed=allow_mixed,
        ),
        "response": response,
        "url": request["serialized"],
        "upgraded": request["upgraded"],
        "prohibits": prohibits,
    }


def _maybe_upgrade(
    record: dict[str, object],
    *,
    destination: str,
    initiator: str,
    prohibits: bool,
) -> dict[str, object]:
    if (
        _url_trustworthy(record)
        or record["ip"] is not None
        or not prohibits
        or destination not in _UPGRADEABLE
        or (destination == "image" and initiator == "imageset")
        or record["scheme"] != "http"
    ):
        return record
    upgraded = "https:" + str(record["serialized"])[len("http:") :]
    rewritten = _describe(upgraded, scheme="https", host=record["host"], ip_text=record["ip_text"])
    rewritten["upgraded"] = True
    rewritten["serialized"] = upgraded
    return rewritten


def _block_state(
    record: Mapping[str, object],
    *,
    destination: str,
    prohibits: bool,
    parent: bool,
    allow_mixed: bool,
) -> str:
    if (
        not prohibits
        or _url_trustworthy(record)
        or allow_mixed
        or (destination == "document" and not parent)
    ):
        return "allowed"
    return "blocked"


def _parse_url(text: str, *, base: str | None) -> dict[str, object]:
    stripped = "".join(char for char in text if char not in "\t\n\r").strip()
    lowered = stripped.lower()
    if lowered == "about:blank" or lowered.startswith("about:blank#"):
        return _special_record("about", "blank")
    if lowered == "about:srcdoc" or lowered.startswith("about:srcdoc#"):
        return _special_record("about", "srcdoc")
    if lowered.startswith("data:"):
        return _special_record("data", "")
    if lowered.startswith("blob:"):
        inner = stripped[5:]
        try:
            parsed = _parse_url(inner, base=None)
        except (URLParseError, ValueError):
            return _special_record("blob", "")
        parsed["serialized"] = stripped
        parsed["upgraded"] = False
        return parsed
    try:
        serialized = parse_href(stripped, _usable_base(base))
    except URLParseError as exc:
        raise ValueError(f"mixed content URL is not usable: {text}") from exc
    scheme, host, ip_text = _host_of(serialized)
    return _describe(serialized, scheme=scheme, host=host, ip_text=ip_text)


def _usable_base(base: str | None) -> str | None:
    if not base:
        return None
    scheme = base.split(":", 1)[0].strip().lower()
    if scheme in {"http", "https", "ws", "wss", "ftp", "file"}:
        return base
    return None


def _special_record(scheme: str, about: str) -> dict[str, object]:
    record = _describe("", scheme=scheme, host="", ip_text="")
    record["about"] = about
    record["opaque"] = True
    record["serialized"] = f"{scheme}:{about}" if about else f"{scheme}:"
    return record


def _describe(serialized: str, *, scheme: str, host: object, ip_text: object) -> dict[str, object]:
    host_text = str(host or "")
    ip_value = _ip_address(str(ip_text or ""))
    return {
        "serialized": serialized,
        "scheme": scheme,
        "host": host_text,
        "ip": ip_value,
        "ip_text": str(ip_text or ""),
        "about": "",
        "opaque": False,
        "upgraded": False,
    }


def _host_of(serialized: str) -> tuple[str, str, str]:
    scheme, _, rest = serialized.partition(":")
    if rest.startswith("//"):
        rest = rest[2:]
    if "@" in rest:
        _, _, rest = rest.rpartition("@")
    end = len(rest)
    for index, char in enumerate(rest):
        if char in "/?#":
            end = index
            break
    hostport = rest[:end]
    if hostport.startswith("["):
        close = hostport.find("]")
        host = hostport[: close + 1] if close >= 0 else hostport
        ip_text = host[1:-1] if close >= 0 else ""
        return scheme, host, ip_text
    host = hostport.rsplit(":", 1)[0] if hostport.count(":") == 1 else hostport
    return scheme, host, host


def _origin_trustworthy(record: Mapping[str, object]) -> bool:
    if record.get("opaque"):
        return False
    scheme = str(record.get("scheme") or "")
    if scheme in {"https", "wss", "file"}:
        return True
    host = str(record.get("host") or "")
    ip_value = record.get("ip")
    if isinstance(ip_value, ipaddress.IPv4Address) and ip_value in _LOOPBACK_V4:
        return True
    if isinstance(ip_value, ipaddress.IPv6Address) and ip_value in _LOOPBACK_V6:
        return True
    folded = host.lower()
    return folded in {"localhost", "localhost."} or folded.endswith((".localhost", ".localhost."))


def _url_trustworthy(record: Mapping[str, object]) -> bool:
    if record.get("about") in {"blank", "srcdoc"} or record.get("scheme") == "data":
        return True
    if record.get("opaque"):
        return False
    return _origin_trustworthy(record)


def _ip_address(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not text:
        return None
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None
