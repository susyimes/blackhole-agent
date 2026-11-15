"""RFC 7541 Appendix C header blocks, including Huffman and eviction."""

from __future__ import annotations

import pytest

from blackhole_agent.hpack import HpackDecoder, HpackError, decode_hpack_block

REQ1 = [
    (":method", "GET"),
    (":scheme", "http"),
    (":path", "/"),
    (":authority", "www.example.com"),
]
REQ2 = [*REQ1, ("cache-control", "no-cache")]
REQ3 = [
    (":method", "GET"),
    (":scheme", "https"),
    (":path", "/index.html"),
    (":authority", "www.example.com"),
    ("custom-key", "custom-value"),
]
RESP1 = [
    (":status", "302"),
    ("cache-control", "private"),
    ("date", "Mon, 21 Oct 2013 20:13:21 GMT"),
    ("location", "https://www.example.com"),
]
RESP2 = [
    (":status", "307"),
    ("cache-control", "private"),
    ("date", "Mon, 21 Oct 2013 20:13:21 GMT"),
    ("location", "https://www.example.com"),
]
COOKIE = "foo=ASDJKHQKBZXOQWEOPIUAXQWEOIU; max-age=3600; version=1"
RESP3 = [
    (":status", "200"),
    ("cache-control", "private"),
    ("date", "Mon, 21 Oct 2013 20:13:22 GMT"),
    ("location", "https://www.example.com"),
    ("content-encoding", "gzip"),
    ("set-cookie", COOKIE),
]


def _block(text: str) -> bytes:
    return bytes.fromhex(text)


def _run(blocks: list[str], expected: list[list[tuple[str, str]]], *, table_size: int = 4096) -> HpackDecoder:
    decoder = HpackDecoder(table_size)
    for text, want in zip(blocks, expected, strict=True):
        assert decoder.decode(_block(text)) == want
    return decoder


def test_literal_and_indexed_examples() -> None:
    assert decode_hpack_block(_block("400a637573746f6d2d6b65790d637573746f6d2d686561646572")) == [
        ("custom-key", "custom-header")
    ]
    fresh = HpackDecoder()
    assert fresh.decode(_block("040c2f73616d706c652f70617468")) == [(":path", "/sample/path")]
    assert fresh.table_size == 0
    assert decode_hpack_block(_block("100870617373776f726406736563726574")) == [("password", "secret")]
    secret = HpackDecoder()
    secret.decode(_block("100870617373776f726406736563726574"))
    assert secret.table_size == 0
    assert decode_hpack_block(_block("82")) == [(":method", "GET")]


def test_request_sequence_without_huffman() -> None:
    decoder = _run(
        [
            "828684410f7777772e6578616d706c652e636f6d",
            "828684be58086e6f2d6361636865",
            "828785bf400a637573746f6d2d6b65790c637573746f6d2d76616c7565",
        ],
        [REQ1, REQ2, REQ3],
    )
    assert decoder.table_size == 164


def test_request_sequence_with_huffman() -> None:
    decoder = _run(
        [
            "828684418cf1e3c2e5f23a6ba0ab90f4ff",
            "828684be5886a8eb10649cbf",
            "828785bf408825a849e95ba97d7f8925a849e95bb8e8b4bf",
        ],
        [REQ1, REQ2, REQ3],
    )
    assert decoder.table_size == 164


def test_response_sequence_evicts_at_256() -> None:
    decoder = _run(
        [
            "4803333032580770726976617465611d4d6f6e2c203231204f637420323031332032303a31333a323120474d546e1768747470733a2f2f7777772e6578616d706c652e636f6d",
            "4803333037c1c0bf",
            "88c1611d4d6f6e2c203231204f637420323031332032303a31333a323220474d54c05a04677a69707738666f6f3d4153444a4b48514b425a584f5157454f50495541585157454f49553b206d61782d6167653d333630303b2076657273696f6e3d31",
        ],
        [RESP1, RESP2, RESP3],
        table_size=256,
    )
    assert decoder.table_size == 215


def test_huffman_response_sequence_evicts_at_256() -> None:
    decoder = _run(
        [
            "488264025885aec3771a4b6196d07abe941054d444a8200595040b8166e082a62d1bff6e919d29ad171863c78f0b97c8e9ae82ae43d3",
            "4883640effc1c0bf",
            "88c16196d07abe941054d444a8200595040b8166e084a62d1bffc05a839bd9ab77ad94e7821dd7f2e6c7b335dfdfcd5b3960d5af27087f3672c1ab270fb5291f9587316065c003ed4ee5b1063d5007",
        ],
        [RESP1, RESP2, RESP3],
        table_size=256,
    )
    assert decoder.table_size == 215


def test_zero_index_and_bad_padding_and_oversize_table() -> None:
    with pytest.raises(HpackError):
        decode_hpack_block(_block("80"))
    with pytest.raises(HpackError):
        decode_hpack_block(_block("0001618100"))
    decoder = HpackDecoder(256)
    with pytest.raises(HpackError):
        decoder.decode(_block("3fe201"))


def test_size_update_drops_a_dynamic_reference() -> None:
    decoder = HpackDecoder()
    decoder.decode(_block("400a637573746f6d2d6b65790d637573746f6d2d686561646572"))
    assert decoder.table_size == 55
    assert decoder.decode(_block("20")) == []
    assert decoder.table_size == 0
    with pytest.raises(HpackError):
        decoder.decode(_block("be"))


def test_grpc_reader_resolves_indexed_and_huffman() -> None:
    from blackhole_agent.grpc_actuation import decode_hpack_headers, encode_hpack_headers

    packed = encode_hpack_headers(((":path", "/blackhole.v1.Actuator/Seal"), ("te", "trailers")))
    decoded = decode_hpack_headers(packed)
    assert decoded[":path"] == "/blackhole.v1.Actuator/Seal"
    assert decoded["te"] == "trailers"
    huffman = decode_hpack_headers(_block("828684418cf1e3c2e5f23a6ba0ab90f4ff"))
    assert huffman[":method"] == "GET"
    assert huffman[":authority"] == "www.example.com"
    assert decode_hpack_headers(_block("82")) == {":method": "GET"}
