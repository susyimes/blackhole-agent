"""An HPACK block yields header fields the old reader dropped or rejected.

An indexed static field is the field itself. A Huffman literal is text.
A dynamic-table entry from one block is readable from the next block, and a
table-size update of zero makes that reference invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the reader is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

HUFFMAN_REQUEST = bytes.fromhex("828684418cf1e3c2e5f23a6ba0ab90f4ff")
FIRST_RESPONSE = bytes.fromhex(
    "4803333032580770726976617465611d4d6f6e2c203231204f63742032303133"
    "2032303a31333a323120474d546e1768747470733a2f2f7777772e6578616d706c652e636f6d"
)
SECOND_RESPONSE = bytes.fromhex("4803333037c1c0bf")
REQUEST = [
    [":method", "GET"],
    [":scheme", "http"],
    [":path", "/"],
    [":authority", "www.example.com"],
]
RESPONSE_302 = [
    [":status", "302"],
    ["cache-control", "private"],
    ["date", "Mon, 21 Oct 2013 20:13:21 GMT"],
    ["location", "https://www.example.com"],
]
RESPONSE_307 = [
    [":status", "307"],
    ["cache-control", "private"],
    ["date", "Mon, 21 Oct 2013 20:13:21 GMT"],
    ["location", "https://www.example.com"],
]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.hpack import HpackDecoder, HpackError
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    try:
        indexed = HpackDecoder().decode(b"\x82")
        huffman = HpackDecoder().decode(HUFFMAN_REQUEST)
        responses = HpackDecoder(256)
        first = responses.decode(FIRST_RESPONSE)
        second = responses.decode(SECOND_RESPONSE)
        kept = responses.table_size
        responses.decode(b"\x20")
        evicted = responses.table_size
        try:
            responses.decode(b"\xbe")
            reference = "resolved"
        except HpackError:
            reference = "rejected"
    except Exception as exc:  # noqa: BLE001 - a broken reader is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed = {
        "indexed": [list(pair) for pair in indexed],
        "huffman_request": [list(pair) for pair in huffman],
        "first_response": [list(pair) for pair in first],
        "second_response": [list(pair) for pair in second],
        "table_before_clear": kept,
        "table_after_clear": evicted,
        "dynamic_reference": reference,
    }
    passed = (
        observed["indexed"] == [[":method", "GET"]]
        and observed["huffman_request"] == REQUEST
        and observed["first_response"] == RESPONSE_302
        and observed["second_response"] == RESPONSE_307
        and kept == 222
        and evicted == 0
        and reference == "rejected"
    )
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
