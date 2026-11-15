"""Decode HPACK header blocks from RFC 7541.

The gRPC helper used to skip an indexed field and refuse a Huffman string.
This reader resolves both, keeps one dynamic table across header blocks, and
rejects a zero index, a Huffman pad that is not an EOS prefix, and a table
size above the limit the decoder was given.

Header names and values are opaque octets, returned as Latin-1 text so every
byte survives. The dynamic table size of an entry is the raw name length plus
the raw value length plus 32, which is the size before Huffman coding.
"""

from __future__ import annotations

import base64
import struct

_STATIC: tuple[tuple[str, str], ...] = (
    (":authority", ""),
    (":method", "GET"),
    (":method", "POST"),
    (":path", "/"),
    (":path", "/index.html"),
    (":scheme", "http"),
    (":scheme", "https"),
    (":status", "200"),
    (":status", "204"),
    (":status", "206"),
    (":status", "304"),
    (":status", "400"),
    (":status", "404"),
    (":status", "500"),
    ("accept-charset", ""),
    ("accept-encoding", "gzip, deflate"),
    ("accept-language", ""),
    ("accept-ranges", ""),
    ("accept", ""),
    ("access-control-allow-origin", ""),
    ("age", ""),
    ("allow", ""),
    ("authorization", ""),
    ("cache-control", ""),
    ("content-disposition", ""),
    ("content-encoding", ""),
    ("content-language", ""),
    ("content-length", ""),
    ("content-location", ""),
    ("content-range", ""),
    ("content-type", ""),
    ("cookie", ""),
    ("date", ""),
    ("etag", ""),
    ("expect", ""),
    ("expires", ""),
    ("from", ""),
    ("host", ""),
    ("if-match", ""),
    ("if-modified-since", ""),
    ("if-none-match", ""),
    ("if-range", ""),
    ("if-unmodified-since", ""),
    ("last-modified", ""),
    ("link", ""),
    ("location", ""),
    ("max-forwards", ""),
    ("proxy-authenticate", ""),
    ("proxy-authorization", ""),
    ("range", ""),
    ("referer", ""),
    ("refresh", ""),
    ("retry-after", ""),
    ("server", ""),
    ("set-cookie", ""),
    ("strict-transport-security", ""),
    ("transfer-encoding", ""),
    ("user-agent", ""),
    ("vary", ""),
    ("via", ""),
    ("www-authenticate", ""),
)
_EOS = 256
_HUFFMAN_B64 = (
    "AAAf+A0Af//YFw///+IcD///4xwP///kHA///+UcD///5hwP///nHA///+gcAP//6hg////8Hg//"
    "/+kcD///6hw////9Hg///+scD///7BwP///tHA///+4cD///7xwP///wHA////EcD///8hw////+"
    "Hg////McD///9BwP///1HA////YcD///9xwP///4HA////kcD///+hwP///7HAAAABQGAAAD+AoA"
    "AAP5CgAAD/oMAAAf+Q0AAAAVBgAAAPgIAAAH+gsAAAP6CgAAA/sKAAAA+QgAAAf7CwAAAPoIAAAA"
    "FgYAAAAXBgAAABgGAAAAAAUAAAABBQAAAAIFAAAAGQYAAAAaBgAAABsGAAAAHAYAAAAdBgAAAB4G"
    "AAAAHwYAAABcBwAAAPsIAAB//A8AAAAgBgAAD/sMAAAD/AoAAB/6DQAAACEGAAAAXQcAAABeBwAA"
    "AF8HAAAAYAcAAABhBwAAAGIHAAAAYwcAAABkBwAAAGUHAAAAZgcAAABnBwAAAGgHAAAAaQcAAABq"
    "BwAAAGsHAAAAbAcAAABtBwAAAG4HAAAAbwcAAABwBwAAAHEHAAAAcgcAAAD8CAAAAHMHAAAA/QgA"
    "AB/7DQAH//ATAAAf/A0AAD/8DgAAACIGAAB//Q8AAAADBQAAACMGAAAABAUAAAAkBgAAAAUFAAAA"
    "JQYAAAAmBgAAACcGAAAABgUAAAB0BwAAAHUHAAAAKAYAAAApBgAAACoGAAAABwUAAAArBgAAAHYH"
    "AAAALAYAAAAIBQAAAAkFAAAALQYAAAB3BwAAAHgHAAAAeQcAAAB6BwAAAHsHAAB//g8AAAf8CwAA"
    "P/0OAAAf/Q0P///8HAAP/+YUAD//0hYAD//nFAAP/+gUAD//0xYAP//UFgA//9UWAH//2RcAP//W"
    "FgB//9oXAH//2xcAf//cFwB//90XAH//3hcA///rGAB//98XAP//7BgA///tGAA//9cWAH//4BcA"
    "///uGAB//+EXAH//4hcAf//jFwB//+QXAB//3BUAP//YFgB//+UXAD//2RYAf//mFwB//+cXAP//"
    "7xgAP//aFgAf/90VAA//6RQAP//bFgA//9wWAH//6BcAf//pFwAf/94VAH//6hcAP//dFgA//94W"
    "AP//8BgAH//fFQA//98WAH//6xcAf//sFwAf/+AVAB//4RUAP//gFgAf/+IVAH//7RcAP//hFgB/"
    "/+4XAH//7xcAD//qFAA//+IWAD//4xYAP//kFgB///AXAD//5RYAP//mFgB///EXA///4BoD///h"
    "GgAP/+sUAAf/8RMAP//nFgB///IXAD//6BYB///sGQP//+IaA///4xoD///kGgf//94bB///3xsD"
    "///lGgD///EYAf//7RkAB//yEwAf/+MVA///5hoH///gGwf//+EbA///5xoH///iGwD///IYAB//"
    "5BUAH//lFQP//+gaA///6RoP///9HAf//+MbB///5BsH///lGwAP/+wUAP//8xgAD//tFAAf/+YV"
    "AD//6RYAH//nFQAf/+gVAH//8xcAP//qFgA//+sWAf//7hkB///vGQD///QYAP//9RgD///qGgB/"
    "//QXA///6xoH///mGwP//+waA///7RoH///nGwf//+gbB///6RsH///qGwf//+sbD////hwH///s"
    "Gwf//+0bB///7hsH///vGwf///AbA///7ho/////Hg=="
)


class HpackError(ValueError):
    """A header block is not a valid HPACK encoding."""


class _Node:
    __slots__ = ("child", "symbol")

    def __init__(self) -> None:
        self.child: list[_Node | None] = [None, None]
        self.symbol: int | None = None


def _huffman_root() -> _Node:
    raw = base64.b64decode(_HUFFMAN_B64)
    root = _Node()
    for symbol in range(257):
        code, length = struct.unpack_from(">IB", raw, symbol * 5)
        node = root
        for shift in range(length - 1, -1, -1):
            bit = (code >> shift) & 1
            nxt = node.child[bit]
            if nxt is None:
                nxt = _Node()
                node.child[bit] = nxt
            node = nxt
        node.symbol = symbol
    return root


_ROOT = _huffman_root()


def _read_int(data: bytes, offset: int, prefix: int) -> tuple[int, int]:
    if offset >= len(data):
        raise HpackError("truncated")
    mask = (1 << prefix) - 1
    value = data[offset] & mask
    offset += 1
    if value < mask:
        return value, offset
    shift = 0
    while True:
        if offset >= len(data):
            raise HpackError("truncated")
        if shift > 28:
            raise HpackError("overflow")
        byte = data[offset]
        offset += 1
        value += (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return value, offset
        shift += 7


def _huffman_decode(data: bytes) -> bytes:
    node = _ROOT
    out = bytearray()
    pending = 0
    ones = True
    for byte in data:
        for shift in range(7, -1, -1):
            bit = (byte >> shift) & 1
            nxt = node.child[bit]
            if nxt is None:
                raise HpackError("huffman")
            node = nxt
            pending += 1
            if bit == 0:
                ones = False
            if node.symbol is not None:
                if node.symbol == _EOS:
                    raise HpackError("huffman")
                out.append(node.symbol)
                node = _ROOT
                pending = 0
                ones = True
    if node is not _ROOT and (pending > 7 or not ones):
        raise HpackError("huffman")
    return bytes(out)


def read_string(data: bytes, offset: int) -> tuple[str, int]:
    """Read one HPACK string literal starting at ``offset``."""

    if offset >= len(data) or offset < 0:
        raise HpackError("truncated")
    huffman = bool(data[offset] & 0x80)
    length, offset = _read_int(data, offset, 7)
    if length > len(data) - offset:
        raise HpackError("truncated")
    raw = data[offset : offset + length]
    offset += length
    if huffman:
        raw = _huffman_decode(raw)
    return raw.decode("latin-1"), offset


class HpackDecoder:
    """One decoding context. Request and response contexts stay separate."""

    def __init__(self, table_size: int = 4096) -> None:
        if isinstance(table_size, bool) or not isinstance(table_size, int):
            raise TypeError("table size must be an int")
        if table_size < 0:
            raise ValueError("table size must be non-negative")
        self._protocol_max = table_size
        self._max = table_size
        self._entries: list[tuple[str, str, int]] = []
        self._size = 0

    @property
    def table_size(self) -> int:
        """Current dynamic-table size in octets, including the 32-octet overhead."""

        return self._size

    def decode(self, block: bytes) -> list[tuple[str, str]]:
        """Decode one header block and apply its table updates."""

        if isinstance(block, bytearray):
            data = bytes(block)
        elif isinstance(block, bytes):
            data = block
        else:
            raise TypeError("header block must be bytes")
        headers: list[tuple[str, str]] = []
        offset = 0
        seen = False
        while offset < len(data):
            first = data[offset]
            if first & 0x80:
                index, offset = _read_int(data, offset, 7)
                if index == 0:
                    raise HpackError("index")
                headers.append(self._get(index))
                seen = True
                continue
            if first & 0xC0 == 0x40:
                index, offset = _read_int(data, offset, 6)
                name, offset = self._literal_name(data, offset, index)
                value, offset = read_string(data, offset)
                headers.append((name, value))
                self._add(name, value)
                seen = True
                continue
            if first & 0xE0 == 0x20:
                if seen:
                    raise HpackError("table-size")
                size, offset = _read_int(data, offset, 5)
                self._set_max(size)
                continue
            if first & 0xF0 == 0x10:
                index, offset = _read_int(data, offset, 4)
                name, offset = self._literal_name(data, offset, index)
                value, offset = read_string(data, offset)
                headers.append((name, value))
                seen = True
                continue
            if first & 0xF0 == 0x00:
                index, offset = _read_int(data, offset, 4)
                name, offset = self._literal_name(data, offset, index)
                value, offset = read_string(data, offset)
                headers.append((name, value))
                seen = True
                continue
            raise HpackError("representation")
        return headers

    def _literal_name(self, data: bytes, offset: int, index: int) -> tuple[str, int]:
        if index == 0:
            return read_string(data, offset)
        name, _value = self._get(index)
        return name, offset

    def _get(self, index: int) -> tuple[str, str]:
        if index <= len(_STATIC):
            return _STATIC[index - 1]
        slot = index - len(_STATIC) - 1
        if slot < 0 or slot >= len(self._entries):
            raise HpackError("index")
        name, value, _size = self._entries[slot]
        return name, value

    def _set_max(self, size: int) -> None:
        if size > self._protocol_max:
            raise HpackError("table-size")
        self._max = size
        self._evict_to(size)

    def _add(self, name: str, value: str) -> None:
        size = len(name) + len(value) + 32
        if size > self._max:
            self._entries.clear()
            self._size = 0
            return
        self._evict_to(self._max - size)
        self._entries.insert(0, (name, value, size))
        self._size += size

    def _evict_to(self, limit: int) -> None:
        while self._entries and self._size > limit:
            _name, _value, size = self._entries.pop()
            self._size -= size


def decode_hpack_block(block: bytes, *, table_size: int = 4096) -> list[tuple[str, str]]:
    """Decode one block with a fresh dynamic table."""

    return HpackDecoder(table_size).decode(block)
