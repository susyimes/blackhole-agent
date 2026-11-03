"""An HTTP request is the bytes on a connection, not a pre-split field list.

A chunked POST returns its payload and leaves the next request unconsumed.
A space before a field colon, an obsolete line fold, and a bare line feed
are rejected. HTTP/1.1 without Host is rejected. HTTP/1.0 without Host
still returns the target. The stdlib request handler accepts the space
and the fold.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import json
from io import BytesIO


def _text(payload: object) -> str:
    if isinstance(payload, bytes):
        return payload.decode("ascii")
    return ""


def _peer(raw: bytes) -> dict[str, object]:
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def __init__(self) -> None:
            self.rfile = BytesIO(raw)
            self.wfile = BytesIO()
            self.client_address = ("127.0.0.1", 0)
            self.raw_requestline = self.rfile.readline(65537)
            self.close_connection = True
            self.ok = self.parse_request()

        def log_error(self, format: str, *args: object) -> None:
            return None

    handler = Handler()
    headers = [] if handler.headers is None else list(handler.headers.items())
    return {"ok": bool(handler.ok), "headers": headers}


def observe() -> tuple[bool, dict[str, object]]:
    observed: dict[str, object] = {"layer": "http-request"}
    try:
        from blackhole_agent.http_request import read_http_request
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    chunked = (
        b"POST /wiki HTTP/1.1\r\n"
        b"Host: a\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"\r\n"
        b"4;ext=1\r\nWiki\r\n5\r\npedia\r\n0\r\n"
        b"X-Trace: 7\r\n"
        b"\r\n"
        b"GET /next HTTP/1.1\r\n"
        b"Host: a\r\n"
        b"\r\n"
    )
    quoted = (
        b"POST /wiki HTTP/1.1\r\n"
        b"Host: a\r\n"
        b'Transfer-Encoding: gzip;note=",", chunked\r\n'
        b"\r\n"
        b"4\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\nZ"
    )
    posted = b"POST /wiki HTTP/1.1\r\nHost: a\r\nContent-Length: 4\r\n\r\nabcdZ"
    spaced = b"POST /wiki HTTP/1.1\r\nHost: a\r\nContent-Length : 4\r\n\r\nabcd"
    tabbed = b"POST /wiki HTTP/1.1\r\nHost: a\r\nContent-Length\t: 4\r\n\r\nabcd"
    folded = b"POST /wiki HTTP/1.1\r\nHost: a\r\nContent-Length:\r\n 4\r\n\r\nabcd"
    tab_folded = b"POST /wiki HTTP/1.1\r\nHost: a\r\nContent-Length:\r\n\t4\r\n\r\nabcd"
    bare = b"GET /wiki HTTP/1.1\nHost: a\n\n"
    mixed = b"POST /wiki HTTP/1.1\r\nHost: a\r\nContent-Length: 4\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
    conflict = b"POST /wiki HTTP/1.1\r\nHost: a\r\nContent-Length: 4\r\nContent-Length: 5\r\n\r\n"
    missing_host = b"GET /wiki HTTP/1.1\r\n\r\n"
    two_hosts = b"GET /wiki HTTP/1.1\r\nHost: a\r\nHost: b\r\n\r\n"
    http10 = b"GET /wiki HTTP/1.0\r\n\r\n"
    lower_host = b"GET /wiki HTTP/1.1\r\nhost: a\r\n\r\n"
    absolute = b"GET http://ex.test/wiki HTTP/1.1\r\nHost: ex.test\r\n\r\n"
    asterisk = b"OPTIONS * HTTP/1.1\r\nHost: a\r\n\r\n"
    connect = b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n"
    authority = b"GET example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n"
    partial = b"GET /wiki HTTP/1.1\r\nHost: a\r\n"
    too_long = b"A" * 8001 + b" / HTTP/1.1\r\nHost: a\r\n\r\n"
    lowered = b"GET /wiki http/1.1\r\nHost: a\r\n\r\n"
    leading = b"\r\n" + b"GET /wiki HTTP/1.1\r\nHost: a\r\n\r\n"

    try:
        chunked_result = read_http_request(chunked)
        quoted_result = read_http_request(quoted)
        posted_result = read_http_request(posted)
        spaced_result = read_http_request(spaced)
        tabbed_result = read_http_request(tabbed)
        folded_result = read_http_request(folded)
        tab_folded_result = read_http_request(tab_folded)
        bare_result = read_http_request(bare)
        mixed_result = read_http_request(mixed)
        conflict_result = read_http_request(conflict)
        missing_result = read_http_request(missing_host)
        two_host_result = read_http_request(two_hosts)
        http10_result = read_http_request(http10)
        lower_host_result = read_http_request(lower_host)
        absolute_result = read_http_request(absolute)
        asterisk_result = read_http_request(asterisk)
        connect_result = read_http_request(connect)
        authority_result = read_http_request(authority)
        partial_result = read_http_request(partial)
        long_result = read_http_request(too_long)
        lowered_result = read_http_request(lowered)
        leading_result = read_http_request(leading)
        peer_space = _peer(spaced)
        peer_fold = _peer(folded)
    except Exception as exc:  # noqa: BLE001 - an unmet outcome still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    tail = chunked[int(chunked_result["consumed"]) :]
    peer_space_headers = list(peer_space["headers"])
    peer_fold_headers = dict(peer_fold["headers"])
    observed.update(
        {
            "chunked_method": chunked_result["method"],
            "chunked_target": chunked_result["target"],
            "chunked_version": chunked_result["version"],
            "chunked_payload": _text(chunked_result["payload"]),
            "chunked_trailers": list(chunked_result["trailers"]),
            "chunked_tail": tail.decode("ascii", "replace")[:12],
            "quoted_payload": _text(quoted_result["payload"]),
            "quoted_codings": list(quoted_result["codings"]),
            "quoted_tail": quoted[int(quoted_result["consumed"]) :].decode("ascii", "replace"),
            "posted_payload": _text(posted_result["payload"]),
            "posted_tail": posted[int(posted_result["consumed"]) :].decode("ascii", "replace"),
            "spaced": spaced_result["error"],
            "tabbed": tabbed_result["error"],
            "folded": folded_result["error"],
            "tab_folded": tab_folded_result["error"],
            "bare": bare_result["error"],
            "mixed": mixed_result["error"],
            "conflict": conflict_result["error"],
            "missing_host": missing_result["error"],
            "two_hosts": two_host_result["error"],
            "http10_target": http10_result["target"],
            "http10_version": http10_result["version"],
            "http10_payload": _text(http10_result["payload"]),
            "lower_host": lower_host_result["method"],
            "absolute_target": absolute_result["target"],
            "asterisk_target": asterisk_result["target"],
            "connect_target": connect_result["target"],
            "authority": authority_result["error"],
            "partial": partial_result["error"],
            "too_long": long_result["error"],
            "lowered_version": lowered_result["error"],
            "leading_method": leading_result["method"],
            "peer_space_accepted": peer_space["ok"] is True,
            "peer_fold_accepted": peer_fold["ok"] is True,
            "peer_fold_length": peer_fold_headers.get("Content-Length", ""),
            "peer_space_kept_length": any(name.lower() == "content-length" for name, _value in peer_space_headers),
        }
    )
    passed = (
        chunked_result["ok"] is True
        and observed["chunked_method"] == "POST"
        and observed["chunked_target"] == "/wiki"
        and observed["chunked_version"] == "1.1"
        and observed["chunked_payload"] == "Wikipedia"
        and observed["chunked_trailers"] == [("X-Trace", "7")]
        and str(observed["chunked_tail"]).startswith("GET /next")
        and quoted_result["ok"] is True
        and observed["quoted_payload"] == "Wikipedia"
        and observed["quoted_codings"] == ["gzip"]
        and observed["quoted_tail"] == "Z"
        and posted_result["ok"] is True
        and observed["posted_payload"] == "abcd"
        and observed["posted_tail"] == "Z"
        and spaced_result["ok"] is False
        and spaced_result["consumed"] == 0
        and observed["spaced"] == "field-whitespace"
        and observed["tabbed"] == "field-whitespace"
        and folded_result["ok"] is False
        and observed["folded"] == "obsolete-fold"
        and observed["tab_folded"] == "obsolete-fold"
        and observed["bare"] == "line-ending"
        and observed["mixed"] == "length-and-transfer-encoding"
        and observed["conflict"] == "conflicting-length"
        and observed["missing_host"] == "host"
        and observed["two_hosts"] == "host"
        and http10_result["ok"] is True
        and observed["http10_target"] == "/wiki"
        and observed["http10_version"] == "1.0"
        and observed["http10_payload"] == ""
        and lower_host_result["ok"] is True
        and observed["lower_host"] == "GET"
        and absolute_result["ok"] is True
        and observed["absolute_target"] == "http://ex.test/wiki"
        and asterisk_result["ok"] is True
        and observed["asterisk_target"] == "*"
        and connect_result["ok"] is True
        and observed["connect_target"] == "example.com:443"
        and observed["authority"] == "target"
        and observed["partial"] == "truncated"
        and observed["too_long"] == "request-line"
        and observed["lowered_version"] == "version"
        and leading_result["ok"] is True
        and observed["leading_method"] == "GET"
        and observed["peer_space_accepted"] is True
        and observed["peer_space_kept_length"] is False
        and observed["peer_fold_accepted"] is True
        and observed["peer_fold_length"] == "4"
    )
    return passed, observed


def test_http_request_intake() -> None:
    passed, observed = observe()
    assert passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
