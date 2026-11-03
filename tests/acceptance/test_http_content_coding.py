"""HTTP content-codings expand in reverse application order.

A gzip member, an x-gzip member, and a zlib deflate member become
Wikipedia. A deflate-then-gzip chain does too, from one field or two.
The same bytes fail when the coding order is reversed. Two concatenated
gzip members yield both preimages. chunked, identity, and br are
unsupported. A semicolon parameter is a content-coding error. A raw
deflate stream, a truncated gzip member, trailing junk, and an empty
gzip body are corrupt. Transfer-Encoding gzip leaves the member intact.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import gzip
import json
import zlib


def _text(result: dict) -> str:
    payload = result.get("payload")
    if result.get("ok") and isinstance(payload, bytes):
        return payload.decode("ascii")
    return str(result.get("error") or "")


def observe() -> tuple[bool, dict]:
    observed: dict = {"layer": "content-encoding"}
    try:
        from blackhole_agent.http_content_coding import decode_content_encoding
    except Exception as exc:  # noqa: BLE001 - baseline without the decoder still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    try:
        plain = b"Wikipedia"
        member = gzip.compress(plain)
        wrapped = zlib.compress(plain)
        chain = gzip.compress(wrapped)
        raw_encoder = zlib.compressobj(wbits=-15)
        raw = raw_encoder.compress(plain) + raw_encoder.flush()
        joined = gzip.compress(b"Wiki") + gzip.compress(b"pedia")
        gzip_result = decode_content_encoding(member, [("Content-Encoding", "gzip")])
        alias = decode_content_encoding(member, [("Content-Encoding", "x-gzip")])
        upper = decode_content_encoding(member, [("Content-Encoding", "GZIP")])
        deflate = decode_content_encoding(wrapped, [("Content-Encoding", "deflate")])
        ordered = decode_content_encoding(chain, [("Content-Encoding", " deflate , gzip ")])
        split = decode_content_encoding(
            chain,
            [("Content-Encoding", "deflate"), ("Transfer-Encoding", "chunked"), ("Content-Encoding", "gzip")],
        )
        reversed_order = decode_content_encoding(chain, [("Content-Encoding", "gzip, deflate")])
        concatenated = decode_content_encoding(joined, [("Content-Encoding", "gzip")])
        chunked = decode_content_encoding(member, [("Content-Encoding", "chunked")])
        identity = decode_content_encoding(plain, [("Content-Encoding", "identity")])
        brotli = decode_content_encoding(member, [("Content-Encoding", "br")])
        parameter = decode_content_encoding(member, [("Content-Encoding", "gzip;q=1")])
        raw_deflate = decode_content_encoding(raw, [("Content-Encoding", "deflate")])
        truncated = decode_content_encoding(member[:4], [("Content-Encoding", "gzip")])
        trailing = decode_content_encoding(member + b"Z", [("Content-Encoding", "gzip")])
        empty = decode_content_encoding(b"", [("Content-Encoding", "gzip")])
        absent = decode_content_encoding(plain, [])
        transfer = decode_content_encoding(member, [("Transfer-Encoding", "gzip, chunked")])
    except Exception as exc:  # noqa: BLE001 - an unmet outcome still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    observed.update(
        {
            "gzip": _text(gzip_result),
            "x_gzip": _text(alias),
            "x_gzip_coding": list(alias["codings"]),
            "upper": _text(upper),
            "deflate": _text(deflate),
            "chain": _text(ordered),
            "chain_codings": list(ordered["codings"]),
            "split": _text(split),
            "reversed": reversed_order["error"],
            "concatenated": _text(concatenated),
            "chunked": chunked["error"],
            "identity": identity["error"],
            "brotli": brotli["error"],
            "parameter": parameter["error"],
            "parameter_empty": parameter["payload"] == b"",
            "raw_deflate": raw_deflate["error"],
            "truncated": truncated["error"],
            "trailing": trailing["error"],
            "empty_gzip": empty["error"],
            "absent": _text(absent),
            "absent_codings": list(absent["codings"]),
            "transfer": "unchanged" if transfer["ok"] and transfer["payload"] == member else "changed",
            "transfer_codings": list(transfer["codings"]),
        }
    )
    passed = (
        observed["gzip"] == "Wikipedia"
        and observed["x_gzip"] == "Wikipedia"
        and observed["x_gzip_coding"] == ["x-gzip"]
        and observed["upper"] == "Wikipedia"
        and observed["deflate"] == "Wikipedia"
        and observed["chain"] == "Wikipedia"
        and observed["chain_codings"] == ["deflate", "gzip"]
        and observed["split"] == "Wikipedia"
        and observed["reversed"] == "corrupt"
        and observed["concatenated"] == "Wikipedia"
        and observed["chunked"] == "unsupported"
        and observed["identity"] == "unsupported"
        and observed["brotli"] == "unsupported"
        and observed["parameter"] == "content-coding"
        and observed["parameter_empty"] is True
        and observed["raw_deflate"] == "corrupt"
        and observed["truncated"] == "corrupt"
        and observed["trailing"] == "corrupt"
        and observed["empty_gzip"] == "corrupt"
        and observed["absent"] == "Wikipedia"
        and observed["absent_codings"] == []
        and observed["transfer"] == "unchanged"
        and observed["transfer_codings"] == []
        and gzip_result["ok"] is True
        and reversed_order["ok"] is False
        and parameter["ok"] is False
    )
    return passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
