"""Decide whether bytes match Subresource Integrity metadata.

W3C SRI 2 compares the base64 hash of the bytes with the strongest
recognized algorithm only. ``sha256`` is weaker than ``sha384``, which is
weaker than ``sha512``. An unknown algorithm is skipped. A question-mark
option is ignored. Metadata that recognizes nothing matches, because an
unsupported hash acts as no integrity value. A bare algorithm with no
hash value stays recognized and does not match.

This is not the Content Security Policy rule that every listed hash must
match and that one bad token voids the list.
"""

from __future__ import annotations

import base64
import hashlib

_ALGORITHMS = ("sha256", "sha384", "sha512")
_ASCII_WHITESPACE = frozenset("\t\n\x0c\r ")


def bytes_match_integrity(data: bytes, metadata: str) -> dict[str, object]:
    """Return whether ``data`` matches SRI ``metadata``.

    The result carries ``match``, the strongest recognized ``algorithm``
    (empty when none were recognized), and ``recognized``, the count of
    hash expressions whose algorithm this checker understands.
    """

    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("integrity bytes must be bytes")
    if not isinstance(metadata, str):
        raise TypeError("integrity metadata must be a string")
    parsed = _parse_metadata(metadata)
    if not parsed:
        return {"match": True, "algorithm": "", "recognized": 0}
    strongest = _strongest(parsed)
    algorithm = str(strongest[0]["alg"])
    actual = base64.b64encode(hashlib.new(algorithm, data).digest()).decode("ascii")
    matched = any(item["val"] == actual for item in strongest)
    return {"match": matched, "algorithm": algorithm, "recognized": len(parsed)}


def _parse_metadata(metadata: str) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for token in _split_ascii_whitespace(metadata):
        expression = token.split("?", 1)[0]
        pieces = expression.split("-")
        algorithm = pieces[0].lower()
        if algorithm not in _ALGORITHMS:
            continue
        value = pieces[1] if len(pieces) > 1 else ""
        parsed.append({"alg": algorithm, "val": value})
    return parsed


def _strongest(items: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    strongest_index = -1
    for item in items:
        index = _ALGORITHMS.index(item["alg"])
        if not result:
            result = [item]
            strongest_index = index
            continue
        if index < strongest_index:
            continue
        if index > strongest_index:
            result = [item]
            strongest_index = index
            continue
        result.append(item)
    return result


def _split_ascii_whitespace(text: str) -> list[str]:
    tokens: list[str] = []
    buffer: list[str] = []
    for char in text:
        if char in _ASCII_WHITESPACE:
            if buffer:
                tokens.append("".join(buffer))
                buffer = []
            continue
        buffer.append(char)
    if buffer:
        tokens.append("".join(buffer))
    return tokens
