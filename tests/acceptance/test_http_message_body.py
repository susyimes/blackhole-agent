"""HTTP/1.1 body framing follows RFC 9112, not a CRLF line split.

A chunk extension is ignored, a trailer is kept, and bytes after the
chunked body stay unconsumed. Content-Length 4 and 04 disagree. A body
with both Content-Length and Transfer-Encoding is rejected. A transfer
coding list that ends in gzip is rejected. A quoted comma inside a
transfer parameter still selects chunked. A 204 response consumes nothing.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json


def _naive(data: bytes) -> str:
    parts = []
    for line in data.split(b"\r\n"):
        if line == b"" or all(byte in b"0123456789abcdefABCDEF" for byte in line):
            continue
        parts.append(line.decode("latin-1"))
    return "\n".join(parts)


def _text(payload: object) -> str:
    if isinstance(payload, bytes):
        return payload.decode("latin-1")
    return ""


def observe() -> tuple[bool, dict]:
    wiki = b"4;ext=1\r\nWiki\r\n5\r\npedia\r\n0\r\nX-Trace: 7\r\n\r\nZ"
    first = b"This is the data in the first chunk\r\n"
    second = b"and this is the second one\r\n"
    rfc_body = (
        b"25\r\n" + first + b"\r\n"
        + b"1C\r\n" + second + b"\r\n"
        + b"3\r\ncon\r\n"
        + b"8\r\nsequence\r\n"
        + b"0\r\n\r\nNEXT"
    )
    rfc_expected = first + second + b"consequence"
    observed: dict = {
        "naive_wiki": _naive(wiki),
        "naive_rfc": _naive(rfc_body),
        "rfc_lengths": [len(first), len(second), 3, 8],
        "rfc_expected": rfc_expected.decode("ascii"),
    }
    try:
        from blackhole_agent.http_message_body import decode_chunked, encode_chunked, read_message_body
    except Exception as exc:  # noqa: BLE001 - baseline without the decoder still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    try:
        wiki_result = read_message_body([("Transfer-Encoding", "chunked")], wiki, role="response", status=200)
        rfc_result = decode_chunked(rfc_body)
        space = read_message_body(
            [("Transfer-Encoding", "chunked")],
            b" 4\r\nWiki\r\n0\r\n\r\n",
            role="request",
            method="POST",
        )
        lengths = read_message_body(
            [("Content-Length", "4"), ("Content-Length", "04")],
            b"abcdef",
            role="request",
            method="POST",
        )
        both = read_message_body(
            [("Content-Length", "4"), ("Transfer-Encoding", "chunked")],
            wiki,
            role="request",
            method="POST",
        )
        final_gzip = read_message_body(
            [("Transfer-Encoding", "chunked, gzip")],
            b"0\r\n\r\n",
            role="request",
            method="POST",
        )
        quoted = read_message_body(
            [("Transfer-Encoding", 'gzip;note=",", chunked')],
            b"4\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\nZ",
            role="request",
            method="POST",
        )
        empty_status = read_message_body(
            [("Content-Length", "5")],
            b"helloZ",
            role="response",
            method="GET",
            status=204,
        )
        head = read_message_body(
            [("Content-Length", "5"), ("Transfer-Encoding", "chunked")],
            b"helloZ",
            role="response",
            method="HEAD",
            status=200,
        )
        no_length = read_message_body([], b"hello", role="request", method="POST")
        exact = read_message_body(
            [("Content-Length", "5"), ("Content-Length", "5")],
            b"helloZ",
            role="request",
            method="POST",
        )
        listed = read_message_body(
            [("Content-Length", "5, 5")],
            b"helloZ",
            role="request",
            method="POST",
        )
        escaped = decode_chunked(b'5;n="a\\"b"\r\nhello\r\n0\r\n\r\n')
        embedded = decode_chunked(b"2\r\n\r\n\r\n0\r\n\r\nZ")
        forbidden = decode_chunked(b"0\r\nContent-Length: 1\r\n\r\n")
        double = read_message_body(
            [("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "chunked")],
            b"0\r\n\r\n",
            role="request",
            method="POST",
        )
        until_close = read_message_body([], b"abc", role="response", status=200)
        parameter = read_message_body(
            [("Transfer-Encoding", "chunked;foo=bar")],
            b"3\r\nabc\r\n0\r\n\r\nZ",
            role="request",
            method="POST",
        )
        round_payload = b"Wiki\r\npedia"
        round_wire = encode_chunked(round_payload, [("X-Trace", "7")]) + b"Z"
        round_trip = read_message_body(
            [("Transfer-Encoding", "chunked")],
            round_wire,
            role="request",
            method="POST",
        )
    except Exception as exc:  # noqa: BLE001 - an unmet outcome still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    observed.update(
        {
            "wiki_payload": _text(wiki_result["payload"]),
            "wiki_consumed_tail": wiki[int(wiki_result["consumed"]) :].decode("ascii"),
            "wiki_trailers": list(wiki_result["trailers"]),
            "wiki_error": wiki_result["error"],
            "rfc_payload": _text(rfc_result["payload"]),
            "rfc_tail": rfc_body[int(rfc_result["consumed"]) :].decode("ascii"),
            "leading_space": space["error"],
            "conflicting_length": lengths["error"],
            "length_and_transfer": both["error"],
            "final_gzip": final_gzip["error"],
            "quoted_payload": _text(quoted["payload"]),
            "quoted_codings": list(quoted["codings"]),
            "quoted_tail": "Z" if int(quoted["consumed"]) == len(b"4\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\n") else "",
            "status_204_consumed": empty_status["consumed"],
            "status_204_payload": _text(empty_status["payload"]),
            "head_consumed": head["consumed"],
            "request_without_length": no_length["consumed"],
            "request_without_length_framing": no_length["framing"],
            "exact_payload": _text(exact["payload"]),
            "exact_tail": b"helloZ"[int(exact["consumed"]) :].decode("ascii"),
            "length_list": listed["error"],
            "escaped_payload": _text(escaped["payload"]),
            "embedded_payload": embedded["payload"].hex() if isinstance(embedded["payload"], bytes) else "",
            "embedded_tail": "Z" if int(embedded["consumed"]) == len(b"2\r\n\r\n\r\n0\r\n\r\n") else "",
            "forbidden_trailer": forbidden["error"],
            "double_chunked": double["error"],
            "until_close": _text(until_close["payload"]),
            "until_close_framing": until_close["framing"],
            "parameter_payload": _text(parameter["payload"]),
            "parameter_tail": "Z" if int(parameter["consumed"]) == len(b"3\r\nabc\r\n0\r\n\r\n") else "",
            "round_payload": _text(round_trip["payload"]),
            "round_trailers": list(round_trip["trailers"]),
            "round_tail": round_wire[int(round_trip["consumed"]) :].decode("ascii"),
        }
    )
    passed = (
        observed["rfc_lengths"] == [0x25, 0x1C, 3, 8]
        and rfc_expected == first + second + b"con" + b"sequence"
        and observed["naive_wiki"] != "Wikipedia"
        and observed["naive_rfc"] != observed["rfc_expected"]
        and wiki_result["ok"] is True
        and observed["wiki_payload"] == "Wikipedia"
        and observed["wiki_trailers"] == [("X-Trace", "7")]
        and observed["wiki_consumed_tail"] == "Z"
        and observed["rfc_payload"] == observed["rfc_expected"]
        and observed["rfc_tail"] == "NEXT"
        and space["error"] == "chunk-size"
        and space["consumed"] == 0
        and lengths["error"] == "conflicting-length"
        and both["error"] == "length-and-transfer-encoding"
        and final_gzip["error"] == "transfer-encoding"
        and quoted["ok"] is True
        and observed["quoted_payload"] == "Wikipedia"
        and observed["quoted_codings"] == ["gzip"]
        and observed["quoted_tail"] == "Z"
        and empty_status["ok"] is True
        and empty_status["consumed"] == 0
        and empty_status["payload"] == b""
        and head["consumed"] == 0
        and no_length["ok"] is True
        and no_length["consumed"] == 0
        and no_length["framing"] == "empty"
        and exact["payload"] == b"hello"
        and observed["exact_tail"] == "Z"
        and listed["error"] == "content-length"
        and escaped["payload"] == b"hello"
        and embedded["payload"] == b"\r\n"
        and observed["embedded_tail"] == "Z"
        and forbidden["error"] == "trailer"
        and double["error"] == "transfer-encoding"
        and until_close["framing"] == "until-close"
        and until_close["payload"] == b"abc"
        and parameter["payload"] == b"abc"
        and observed["parameter_tail"] == "Z"
        and round_trip["payload"] == round_payload
        and round_trip["trailers"] == (("X-Trace", "7"),)
        and observed["round_tail"] == "Z"
    )
    return passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
