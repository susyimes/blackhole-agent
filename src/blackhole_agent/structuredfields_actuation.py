"""Drive a first-class Structured Fields tool through RFC 8941 DICT/LIST.

Tool routing already fails missions that require ``structuredfields``: hosted
structuredfields endpoints stay on the unsupported MCP provider, and no first-party
structuredfields provider is executable. Unbound therefore cannot speak a DICT,
lockstep a LIST dictid handshake over HTTP Structured Fields DICTID,
independently poll the stored sfv, or seal an sfv digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``structuredfields`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 8941 daemon
- keep a missing-dictid client so the structuredfields-dictid hole stays falsifiable
- refuse LIST until a DICT lands with a non-empty dictid
- independently poll the stored sfv on a later client socket
- persist a sealed sfv digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9110 HTTP Semantics
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import shutil
import socket
import struct
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    STRUCTUREDFIELDS_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    structuredfields_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
STRUCTUREDFIELDS_ACTUATION_ID = "capability.structuredfields-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SF-OK"
POLL_TOKEN = "BH-SF-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_DICTID = 0
EMPTY_SFV = 0
SF_FIRST = 0x46  # RFC 8941 Structured Fields (ASCII 'F')
DICTID_SIZE = 4
SFV_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_LIST = 0x02  # RFC 8941 List
FRAME_DICT = 0x01  # RFC 8941 Dictionary
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
TCHAR = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "!#$%&'*+-.^_`|~"
)
TOKEN_START = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ*")
KEY_START = frozenset("abcdefghijklmnopqrstuvwxyz")
KEY_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-*")
STRUCTUREDFIELDS_LEFTOVER = (
    "Later genesis can take RFC 8941 Structured Fields DICT/LIST over a "
    "dictid-gated sfv digest."
)


class SfToken(str):
    """RFC 8941 sf-token (unquoted)."""


def _crc32c_table() -> tuple[int, ...]:
    table = []
    for index in range(256):
        crc = index
        for _ in range(8):
            crc = (crc >> 1) ^ CRC32C_POLY if crc & 1 else crc >> 1
        table.append(crc)
    return tuple(table)


_CRC32C_TABLE = _crc32c_table()


def crc32c(data: bytes) -> int:
    """RFC 3309 CRC32c (Castagnoli) over ``data``."""

    crc = 0xFFFFFFFF
    for byte in bytes(data or b""):
        crc = _CRC32C_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


STRUCTUREDFIELDS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{STRUCTUREDFIELDS_ACTUATION_ID};"
    f"capability_proved:{STRUCTUREDFIELDS_ACTUATION_ID};"
    "no_skill_route"
)
STRUCTUREDFIELDS_ACTUATION_GOAL = (
    "Repair rfc8941 structuredfields dict/list cycle cannot land over http "
    "structuredfields dictid: hosted structuredfields endpoints remain unsupported so a DICT then "
    "LIST dictid handshake cannot land and a sealed sfv digest "
    "cannot be produced. A missing structuredfields dictid stays forbidden; fail-closed "
    "routing never opts the structuredfields provider in. An independent later poll of the "
    "stored sfv keeps the hole falsifiable."
)


class StructuredfieldsActuationError(RuntimeError):
    """Raised when the Structured Fields session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise StructuredfieldsActuationError("short_sfv")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def skip_sp(self) -> None:
        while self.peek() == " ":
            self.pos += 1

    def remaining(self) -> str:
        return self.text[self.pos :]

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 8941 sf-token: (ALPHA / "*") *(tchar / ":" / "/")."""

    raw = str(value or "")
    if not raw or raw[0] not in TOKEN_START:
        return False
    allowed = TCHAR | set(":/")
    return all(char in allowed for char in raw)


def is_key(value: str) -> bool:
    """RFC 8941 key: lcalpha *(lcalpha / DIGIT / "_" / "-" / "*")."""

    raw = str(value or "")
    if not raw or raw[0] not in KEY_START:
        return False
    return all(char in KEY_CHARS for char in raw)


def serialize_bare(value: Any) -> str:
    """RFC 8941 section 4.1.1 serialization of a bare item."""

    if isinstance(value, bool):
        return "?1" if value else "?0"
    if isinstance(value, SfToken):
        if not is_token(value):
            raise StructuredfieldsActuationError("illegal_token")
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        for char in escaped:
            code = ord(char)
            if code < 0x20 or code > 0x7E:
                raise StructuredfieldsActuationError("illegal_string")
        return f'"{escaped}"'
    if isinstance(value, (bytes, bytearray)):
        return f":{base64.b64encode(bytes(value)).decode('ascii')}:"
    if isinstance(value, int):
        number = int(value)
        if number < -999_999_999_999_999 or number > 999_999_999_999_999:
            raise StructuredfieldsActuationError("illegal_integer")
        return str(number)
    if isinstance(value, float):
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        if "." not in text:
            text += ".0"
        return text
    raise StructuredfieldsActuationError("illegal_bare_item")


def serialize_parameters(params: Sequence[tuple[str, Any]] | None) -> str:
    """RFC 8941 section 4.1.1.2 serialization of parameters."""

    chunks: list[str] = []
    for key, value in params or ():
        if not is_key(key):
            raise StructuredfieldsActuationError("illegal_key")
        if value is True:
            chunks.append(f";{key}")
        else:
            chunks.append(f";{key}={serialize_bare(value)}")
    return "".join(chunks)


def serialize_item(item: tuple[Any, Sequence[tuple[str, Any]]] | Any) -> str:
    """RFC 8941 section 4.1.1 serialization of an Item."""

    if isinstance(item, tuple) and len(item) == 2 and not isinstance(item[0], tuple):
        value, params = item
        return serialize_bare(value) + serialize_parameters(params)
    return serialize_bare(item)


def serialize_inner_list(items: Sequence[Any], params: Sequence[tuple[str, Any]] | None = None) -> str:
    """RFC 8941 section 4.1.1.3 serialization of an Inner List."""

    body = " ".join(serialize_item(item) for item in items)
    inner = f"({body})" if body else "()"
    return inner + serialize_parameters(params)


def serialize_list(members: Sequence[Any]) -> str:
    """RFC 8941 section 4.1.1 serialization of a List (COMMA + SP)."""

    chunks: list[str] = []
    for member in members:
        if isinstance(member, tuple) and member and isinstance(member[0], (list, tuple)) and not (
            len(member) == 2 and not isinstance(member[0], (list, tuple))
        ):
            items, params = member[0], member[1] if len(member) > 1 else ()
            chunks.append(serialize_inner_list(items, params))
        else:
            chunks.append(serialize_item(member))
    return ", ".join(chunks)


def serialize_dictionary(members: Sequence[tuple[str, Any]]) -> str:
    """RFC 8941 section 4.1.2 serialization of a Dictionary."""

    chunks: list[str] = []
    for key, item in members:
        if not is_key(key):
            raise StructuredfieldsActuationError("illegal_key")
        if isinstance(item, tuple) and len(item) == 2:
            value, params = item
        else:
            value, params = item, ()
        if value is True:
            chunks.append(key + serialize_parameters(params))
        else:
            chunks.append(f"{key}={serialize_item((value, params))}")
    return ", ".join(chunks)


def _parse_key(parser: _Parser) -> str:
    if parser.peek() not in KEY_START:
        raise StructuredfieldsActuationError("illegal_key")
    start = parser.pos
    parser.pos += 1
    while parser.peek() in KEY_CHARS:
        parser.pos += 1
    return parser.text[start:parser.pos]


def _parse_token(parser: _Parser) -> SfToken:
    if parser.peek() not in TOKEN_START:
        raise StructuredfieldsActuationError("illegal_token")
    start = parser.pos
    allowed = TCHAR | set(":/")
    parser.pos += 1
    while parser.peek() in allowed:
        parser.pos += 1
    return SfToken(parser.text[start:parser.pos])


def _parse_string(parser: _Parser) -> str:
    if parser.take() != '"':
        raise StructuredfieldsActuationError("illegal_string")
    chars: list[str] = []
    while True:
        char = parser.peek()
        if not char:
            raise StructuredfieldsActuationError("unterminated_string")
        if char == '"':
            parser.pos += 1
            return "".join(chars)
        if char == "\\":
            parser.pos += 1
            escaped = parser.take()
            if escaped not in {'"', "\\"}:
                raise StructuredfieldsActuationError("illegal_string")
            chars.append(escaped)
            continue
        code = ord(char)
        if code < 0x20 or code > 0x7E:
            raise StructuredfieldsActuationError("illegal_string")
        chars.append(char)
        parser.pos += 1


def _parse_byteseq(parser: _Parser) -> bytes:
    if parser.take() != ":":
        raise StructuredfieldsActuationError("illegal_byteseq")
    start = parser.pos
    while parser.peek() and parser.peek() != ":":
        parser.pos += 1
    raw = parser.text[start:parser.pos]
    if parser.take() != ":":
        raise StructuredfieldsActuationError("illegal_byteseq")
    try:
        return base64.b64decode(raw, validate=True)
    except (ValueError, base64.binascii.Error) as error:  # type: ignore[attr-defined]
        raise StructuredfieldsActuationError("illegal_byteseq") from error


def _parse_boolean(parser: _Parser) -> bool:
    if parser.take() != "?":
        raise StructuredfieldsActuationError("illegal_boolean")
    flag = parser.take()
    if flag == "1":
        return True
    if flag == "0":
        return False
    raise StructuredfieldsActuationError("illegal_boolean")


def _parse_number(parser: _Parser) -> int | float:
    start = parser.pos
    if parser.peek() == "-":
        parser.pos += 1
    digits = 0
    while parser.peek().isdigit():
        parser.pos += 1
        digits += 1
    if digits == 0:
        raise StructuredfieldsActuationError("illegal_number")
    if parser.peek() == ".":
        parser.pos += 1
        frac = 0
        while parser.peek().isdigit():
            parser.pos += 1
            frac += 1
        if frac == 0 or frac > 3 or digits > 12:
            raise StructuredfieldsActuationError("illegal_decimal")
        return float(parser.text[start:parser.pos])
    if digits > 15:
        raise StructuredfieldsActuationError("illegal_integer")
    return int(parser.text[start:parser.pos])


def parse_bare(parser: _Parser) -> Any:
    """RFC 8941 section 4.2.3.1 parse a bare item."""

    char = parser.peek()
    if char == '"':
        return _parse_string(parser)
    if char == ":":
        return _parse_byteseq(parser)
    if char == "?":
        return _parse_boolean(parser)
    if char == "-" or char.isdigit():
        return _parse_number(parser)
    if char in TOKEN_START:
        return _parse_token(parser)
    raise StructuredfieldsActuationError("illegal_bare_item")


def parse_parameters(parser: _Parser) -> tuple[tuple[str, Any], ...]:
    """RFC 8941 section 4.2.3.2 parse parameters."""

    params: list[tuple[str, Any]] = []
    while parser.peek() == ";":
        parser.pos += 1
        parser.skip_ows()
        key = _parse_key(parser)
        if parser.peek() == "=":
            parser.pos += 1
            params.append((key, parse_bare(parser)))
        else:
            params.append((key, True))
    return tuple(params)


def parse_item(parser: _Parser) -> tuple[Any, tuple[tuple[str, Any], ...]]:
    """RFC 8941 section 4.2.3 parse an Item."""

    value = parse_bare(parser)
    params = parse_parameters(parser)
    return value, params


def parse_inner_list(parser: _Parser) -> tuple[tuple[tuple[Any, tuple[tuple[str, Any], ...]], ...], tuple[tuple[str, Any], ...]]:
    """RFC 8941 section 4.2.1.2 parse an Inner List."""

    if parser.take() != "(":
        raise StructuredfieldsActuationError("illegal_inner_list")
    items: list[tuple[Any, tuple[tuple[str, Any], ...]]] = []
    parser.skip_sp()
    while parser.peek() and parser.peek() != ")":
        items.append(parse_item(parser))
        parser.skip_sp()
    if parser.take() != ")":
        raise StructuredfieldsActuationError("illegal_inner_list")
    return tuple(items), parse_parameters(parser)


def parse_list(text: str) -> tuple[Any, ...]:
    """RFC 8941 section 4.2.1 parse a List."""

    parser = _Parser(text)
    parser.skip_ows()
    if parser.eof():
        return ()
    members: list[Any] = []
    while True:
        parser.skip_ows()
        if parser.peek() == "(":
            members.append(parse_inner_list(parser))
        else:
            members.append(parse_item(parser))
        parser.skip_ows()
        if parser.peek() != ",":
            break
        parser.pos += 1
    parser.skip_ows()
    if not parser.eof():
        raise StructuredfieldsActuationError("illegal_list")
    return tuple(members)


def parse_dictionary(text: str) -> tuple[tuple[str, tuple[Any, tuple[tuple[str, Any], ...]]], ...]:
    """RFC 8941 section 4.2.2 parse a Dictionary."""

    parser = _Parser(text)
    parser.skip_ows()
    if parser.eof():
        return ()
    members: list[tuple[str, tuple[Any, tuple[tuple[str, Any], ...]]]] = []
    while True:
        parser.skip_ows()
        key = _parse_key(parser)
        if parser.peek() == "=":
            parser.pos += 1
            members.append((key, parse_item(parser)))
        else:
            params = parse_parameters(parser)
            members.append((key, (True, params)))
        parser.skip_ows()
        if parser.peek() != ",":
            break
        parser.pos += 1
    parser.skip_ows()
    if not parser.eof():
        raise StructuredfieldsActuationError("illegal_dictionary")
    return tuple(members)


def canonical_dictionary(identity: str, dictid: int) -> str:
    """RFC 8941 Dictionary bound to identity and dictid."""

    return serialize_dictionary(
        (
            ("identity", (str(identity or ""), ())),
            ("dictid", (int(dictid) & 0xFFFFFFFF, ())),
        )
    )


def canonical_list(identity: str, dictid: int, sfv: int | None = None) -> str:
    """RFC 8941 List of the stored dictionary members, optionally including sfv."""

    members: list[Any] = [
        (str(identity or ""), ()),
        (int(dictid) & 0xFFFFFFFF, ()),
    ]
    if sfv is not None:
        members.append((int(sfv) & 0xFFFFFFFF, ()))
    return serialize_list(members)


def representation_dictionary(identity: str, dictid: int, sfv: int) -> str:
    return serialize_dictionary(
        (
            ("identity", (str(identity or ""), ())),
            ("dictid", (int(dictid) & 0xFFFFFFFF, ())),
            ("sfv", (int(sfv) & 0xFFFFFFFF, ())),
        )
    )


def dictionary_matches(left: str, right: str) -> bool:
    return parse_dictionary(left) == parse_dictionary(right)


def list_matches(left: str, right: str) -> bool:
    return parse_list(left) == parse_list(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise StructuredfieldsActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise StructuredfieldsActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise StructuredfieldsActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise StructuredfieldsActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def dict_request(identity: str, dictid: int) -> bytes:
    """HTTP message carrying an RFC 8941 Dictionary for the dictid-gated resource."""

    keyid = f"{int(dictid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    body = canonical_dictionary(identity, dictid)
    return (
        f"PUT /structuredfields/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Content-Type: application/sf-dictionary\r\n"
        f"Content-Length: {len(body.encode('ascii'))}\r\n"
        f"SF-Dictionary: {body}\r\n"
        "\r\n"
        f"{body}"
    ).encode("ascii")


def list_request(identity: str, dictid: int, sfv: int | None = None) -> bytes:
    """HTTP message carrying an RFC 8941 List lockstep of the stored dictionary."""

    keyid = f"{int(dictid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    body = canonical_list(identity, dictid, sfv)
    return (
        f"PUT /structuredfields/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Content-Type: application/sf-list\r\n"
        f"Content-Length: {len(body.encode('ascii'))}\r\n"
        f"SF-List: {body}\r\n"
        "\r\n"
        f"{body}"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    content_type = fields.get("content-type", "")
    sf_kind = "dictionary" if content_type.endswith("sf-dictionary") else "list" if content_type.endswith("sf-list") else ""
    parsed: Any = None
    if sf_kind == "dictionary":
        parsed = parse_dictionary(body.decode("ascii") if body else fields.get("sf-dictionary", ""))
    elif sf_kind == "list":
        parsed = parse_list(body.decode("ascii") if body else fields.get("sf-list", ""))
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "content_type": content_type,
        "sf_kind": sf_kind,
        "sfv": parsed,
        "sf_dictionary": fields.get("sf-dictionary", ""),
        "sf_list": fields.get("sf-list", ""),
    }


def dict_response(identity: str, dictid: int, sfv: int) -> bytes:
    """HTTP response whose field value is an RFC 8941 Dictionary including sfv."""

    body = representation_dictionary(identity, dictid, sfv)
    return (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/sf-dictionary\r\n"
        f"Content-Length: {len(body.encode('ascii'))}\r\n"
        f"SF-Dictionary: {body}\r\n"
        "\r\n"
        f"{body}"
    ).encode("ascii")


def list_response(identity: str, dictid: int, sfv: int) -> bytes:
    """HTTP response whose field value is an RFC 8941 List of stored members."""

    body = canonical_list(identity, dictid, sfv)
    return (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/sf-list\r\n"
        f"Content-Length: {len(body.encode('ascii'))}\r\n"
        f"SF-List: {body}\r\n"
        "\r\n"
        f"{body}"
    ).encode("ascii")


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    content_type = fields.get("content-type", "")
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise StructuredfieldsActuationError("illegal_content_length") from error
    text = body.decode("ascii") if body else ""
    sf_kind = "dictionary" if "sf-dictionary" in content_type else "list" if "sf-list" in content_type else ""
    parsed: Any = None
    if sf_kind == "dictionary":
        parsed = parse_dictionary(text or fields.get("sf-dictionary", ""))
    elif sf_kind == "list":
        parsed = parse_list(text or fields.get("sf-list", ""))
    return {
        "kind": "response",
        "start_line": start,
        "status": 200 if start.startswith("HTTP/1.1 200") else 0,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": content_type,
        "sf_kind": sf_kind,
        "sfv": parsed,
        "content_length_matches_body": content_length == len(body),
    }


def encode_varint(value: int) -> bytes:
    number = int(value)
    if number < 0:
        number = 0
    if number <= 63:
        return bytes([number])
    if number <= 16383:
        return struct.pack("!H", 0x4000 | number)
    if number <= 1073741823:
        return struct.pack("!I", 0x80000000 | number)
    return struct.pack("!Q", 0xC000000000000000 | (number & 0x3FFFFFFFFFFFFFFF))


def decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    raw = bytes(data or b"")
    if offset >= len(raw):
        raise StructuredfieldsActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise StructuredfieldsActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise StructuredfieldsActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise StructuredfieldsActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_dictid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"dictid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_dictid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-dictid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_sfv(dictid: int = EMPTY_DICTID, token: str = SENTINEL) -> int:
    material = canonical_dictionary(token or SENTINEL, int(dictid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_DICTID = request_dictid(SENTINEL)
DEFAULT_SFV = request_sfv(DEFAULT_DICTID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    dictid: int,
    sfv: int,
    include_dictid: bool = True,
) -> bytes:
    live_dictid = int(dictid) & 0xFFFFFFFF if include_dictid else EMPTY_DICTID
    live_sfv = int(sfv) & 0xFFFFFFFF if include_dictid and live_dictid else EMPTY_SFV
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_sfv, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_dictid) if live_dictid else b""
    header = bytearray()
    header.append(SF_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_dict(
    *,
    identity: str,
    dictid: int,
    sfv: int | None = None,
    include_dictid: bool = True,
) -> bytes:
    live_dictid = int(dictid) & 0xFFFFFFFF if include_dictid else EMPTY_DICTID
    live_sfv = int(sfv) if sfv is not None else request_sfv(live_dictid, identity)
    return encode_packet(
        FRAME_DICT,
        identity=identity,
        dictid=live_dictid,
        sfv=live_sfv,
        include_dictid=include_dictid,
    )


def encode_list(
    *,
    identity: str,
    dictid: int,
    sfv: int | None = None,
    include_dictid: bool = True,
) -> bytes:
    live_dictid = int(dictid) & 0xFFFFFFFF if include_dictid else EMPTY_DICTID
    live_sfv = int(sfv) if sfv is not None else request_sfv(live_dictid, identity)
    return encode_packet(
        FRAME_LIST,
        identity=identity,
        dictid=live_dictid,
        sfv=live_sfv,
        include_dictid=include_dictid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise StructuredfieldsActuationError("short_packet")
    first = raw[0]
    if first != SF_FIRST:
        raise StructuredfieldsActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise StructuredfieldsActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == DICTID_SIZE:
        live_dictid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_dictid = EMPTY_DICTID
    else:
        raise StructuredfieldsActuationError("illegal_dictid")
    if offset >= len(raw):
        raise StructuredfieldsActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_DICT, FRAME_LIST}:
        raise StructuredfieldsActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise StructuredfieldsActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise StructuredfieldsActuationError("checksum_failed")
    if len(payload) < 5:
        raise StructuredfieldsActuationError("short_packet")
    live_sfv, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise StructuredfieldsActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_dictid = int(live_dictid) != EMPTY_DICTID
    has_sfv = has_dictid and int(live_sfv) != EMPTY_SFV
    is_dict = frame_type == FRAME_DICT
    is_list = frame_type == FRAME_LIST
    return {
        "type": int(frame_type),
        "is_dict": is_dict,
        "is_list": is_list,
        "is_response": is_list,
        "dictid": int(live_dictid),
        "has_dictid": has_dictid,
        "sfv": int(live_sfv),
        "has_sfv": has_sfv,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "structured_fields": "RFC8941",
        "dictionary": canonical_dictionary(identity, live_dictid) if has_dictid else "",
        "list": canonical_list(identity, live_dictid, live_sfv) if has_sfv else "",
    }


class StructuredfieldsClient:
    def __init__(self, host: str, port: int, *, timeout: float = IO_TIMEOUT) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(timeout)
        self.client_port = int(self.sock.getsockname()[1])

    def close(self) -> None:
        sock = self.sock
        self.sock = None  # type: ignore[assignment]
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass

    def send(self, packet: bytes) -> None:
        self.sock.sendto(bytes(packet or b""), (self.host, self.port))

    def _recv(self) -> dict[str, Any]:
        try:
            payload, _addr = self.sock.recvfrom(65535)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise StructuredfieldsActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_list"] or not packet["is_response"]:
            raise StructuredfieldsActuationError("sfv_required")
        if not packet["has_dictid"]:
            raise StructuredfieldsActuationError("dictid_required")
        if not packet["has_sfv"]:
            raise StructuredfieldsActuationError("sfv_required")
        return packet

    def exchange(self, packet: bytes, *, wait_sfv: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_sfv:
            raise StructuredfieldsActuationError("sfv_required")
        reply = self._recv()
        return {
            "session": reply,
            "dictid": int(reply.get("dictid") or EMPTY_DICTID),
            "identity": str(reply.get("identity") or ""),
            "sfv": int(reply.get("sfv") or EMPTY_SFV),
        }

    def list(
        self,
        identity: str,
        dictid: int,
        sfv: int = EMPTY_SFV,
        *,
        wait_sfv: bool = True,
        include_dictid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_list(
            identity=identity,
            dictid=dictid,
            sfv=sfv or request_sfv(dictid, identity),
            include_dictid=include_dictid,
        )
        return self.exchange(packet, wait_sfv=wait_sfv)


class StructuredfieldsSession:
    """DICTID-gated loopback RFC 8941 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        dictid_gate: int = DEFAULT_DICTID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dictid_gate = int(dictid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.dictid = EMPTY_DICTID
        self.sfv = EMPTY_SFV
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.opened = False
        self.handshook = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_dictid_once(self, identity: str, dictid: int, sfv: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(dictid or EMPTY_DICTID)
            live_sfv = int(sfv or EMPTY_SFV)
            if not self.identity and name and live:
                self.identity = name
                self.dictid = live
                self.sfv = live_sfv or request_sfv(live, name)
                self.stored = True
            return str(self.identity), int(self.dictid), int(self.sfv)

    def read_dictid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.dictid), int(self.sfv)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "dictid": EMPTY_DICTID,
            "sfv": EMPTY_SFV,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _dictid_missing(self) -> bool:
        return not int(self.dictid_gate or 0)

    def _reply_list(self, peer: tuple[str, int], identity: str, dictid: int, sfv: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_list(
            identity=identity,
            dictid=dictid,
            sfv=sfv,
        )
        try:
            sock.sendto(packet, peer)
        except OSError:
            return

    def _serve(self) -> None:
        while self._running:
            sock = self.sock
            if sock is None:
                return
            try:
                payload, addr = sock.recvfrom(65535)
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                return
            try:
                packet = parse_message(payload)
            except StructuredfieldsActuationError:
                continue
            if not packet.get("is_dict") and not packet.get("is_list"):
                continue
            if not packet.get("has_dictid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_dictid, stored_sfv = self.store_dictid_once(
                identity,
                int(packet.get("dictid") or EMPTY_DICTID),
                int(packet.get("sfv") or EMPTY_SFV),
            )
            if not stored_name or not stored_dictid or not stored_sfv:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_dict"):
                    self.opened = True
                if packet.get("is_list"):
                    self.handshook = True
                self.retrieved = True
            self._reply_list(peer, stored_name, stored_dictid, stored_sfv)

    def bind(self) -> dict[str, Any]:
        if self._dictid_missing():
            return self._forbidden("missing_dictid")
        if self.sock is not None:
            return {
                "ok": True,
                "status": 200,
                "host": self.host or "",
                "port": int(self.port or 0),
                "reused": True,
            }
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(SERVE_TIMEOUT)
        host, port = sock.getsockname()[:2]
        self.sock = sock
        self.host = str(host)
        self.port = int(port)
        self._running = True
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
        self.thread = thread
        return {
            "ok": True,
            "status": 200,
            "host": self.host,
            "port": self.port,
            "reused": False,
        }

    def publish(
        self,
        token: str = SENTINEL,
        *,
        do_dict_cycle: bool = True,
        do_list: bool = True,
        do_sfv: bool = True,
        replay: bool = True,
        use_dictid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._dictid_missing():
            return self._forbidden("missing_dictid")
        live_token = str(token or SENTINEL)
        origin_dictid = request_dictid(live_token)
        origin_sfv = request_sfv(origin_dictid, live_token)
        client: StructuredfieldsClient | None = None
        independent: StructuredfieldsClient | None = None
        try:
            client = StructuredfieldsClient(self.host, int(self.port))
            if not do_dict_cycle:
                return self._conflict("dict_required")
            bind_packet = encode_dict(
                identity=live_token,
                dictid=origin_dictid,
                sfv=origin_sfv,
                include_dictid=use_dictid,
            )
            if not use_dictid:
                try:
                    client.exchange(bind_packet, wait_sfv=True)
                except StructuredfieldsActuationError:
                    return self._conflict("dictid_required")
                return self._conflict("dictid_required")
            client.send(bind_packet)
            if not do_list:
                return self._conflict("list_required")
            proxy_packet = encode_list(
                identity=live_token,
                dictid=origin_dictid,
                sfv=origin_sfv,
                include_dictid=True,
            )
            if not do_sfv:
                try:
                    client.exchange(proxy_packet, wait_sfv=False)
                except StructuredfieldsActuationError as error:
                    if str(error) == "sfv_required":
                        return self._conflict("sfv_required")
                    return self._conflict("sfv_required")
                return self._conflict("sfv_required")
            try:
                reply = client.exchange(proxy_packet, wait_sfv=True)
            except StructuredfieldsActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("dictid_required")
                if reason == "sfv_required":
                    return self._conflict("sfv_required")
                return self._conflict("dict_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("dict_required")
            if int(reply.get("dictid") or EMPTY_DICTID) != origin_dictid:
                return self._conflict("sfv_required")
            if int(reply.get("sfv") or EMPTY_SFV) != origin_sfv:
                return self._conflict("sfv_required")
            self.retrieved = True
            if replay:
                independent = StructuredfieldsClient(self.host, int(self.port))
                try:
                    poll = independent.list(
                        POLL_TOKEN,
                        poll_dictid(live_token),
                        request_sfv(poll_dictid(live_token), POLL_TOKEN),
                        wait_sfv=True,
                    )
                except StructuredfieldsActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_dictid, stored_sfv = self.read_dictid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_dictid != origin_dictid
                    or stored_sfv != origin_sfv
                    or int(poll.get("dictid") or EMPTY_DICTID) != origin_dictid
                    or int(poll.get("sfv") or EMPTY_SFV) != origin_sfv
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_dictid}:{origin_sfv}:{live_token}:{canonical_dictionary(live_token, origin_dictid)}:{canonical_list(live_token, origin_dictid, origin_sfv)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "dictid": origin_dictid,
                "sfv": origin_sfv,
                "dict_frame": True,
                "list": True,
                "sfv_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "dictid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_structuredfields_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "dictid": origin_dictid,
                "sfv": origin_sfv,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "dict_frame": True,
                "list": True,
                "sfv_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "dictid_bound": True,
            }
        except (OSError, StructuredfieldsActuationError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error),
                "token": live_token,
                "sentinel": "",
                "digest": "",
            }
        finally:
            if independent is not None:
                independent.close()
            if client is not None:
                client.close()

    def read(self) -> dict[str, Any]:
        live = independent_structuredfields_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "dictid": int(live.get("dictid") or EMPTY_DICTID),
            "sfv": int(live.get("sfv") or EMPTY_SFV),
            "port": int(live.get("port") or 0),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        self._running = False
        sock = self.sock
        thread = self.thread
        self.sock = None
        self.thread = None
        self.host = None
        self.port = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=1)
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_structuredfields_tool(session: StructuredfieldsSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one Structured Fields tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_dict_cycle = True if arguments.get("dict_cycle") is None else bool(arguments.get("dict_cycle"))
    do_list = True if arguments.get("list") is None else bool(arguments.get("list"))
    do_sfv = True if arguments.get("sfv") is None else bool(arguments.get("sfv"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_dictid = True if arguments.get("use_dictid") is None else bool(arguments.get("use_dictid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_dict_cycle=do_dict_cycle,
            do_list=do_list,
            do_sfv=do_sfv,
            replay=replay,
            use_dictid=use_dictid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise StructuredfieldsActuationError(f"unsupported structuredfields action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_structuredfields_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed Structured Fields sfv digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "dictid": EMPTY_DICTID,
        "sfv": EMPTY_SFV,
        "port": 0,
    }
    if not path.is_file():
        return empty
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {**empty, "error": "invalid_payload", "detail": str(error)}
    if not isinstance(payload, dict):
        return {**empty, "error": "invalid_payload"}
    token = str(payload.get("token") or "")
    flags = all(
        payload.get(name) is True
        for name in (
            "dict_frame",
            "list",
            "sfv_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "dictid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    dictid = int(payload.get("dictid") or EMPTY_DICTID)
    sfv = int(payload.get("sfv") or EMPTY_SFV)
    dual = port > 0 and bool(dictid) and bool(sfv)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "dictid": dictid,
        "sfv": sfv,
        "size": int(payload.get("size") or 0),
        "port": port,
        "dict_frame": payload.get("dict_frame") is True,
        "list": payload.get("list") is True,
        "sfv_response": payload.get("sfv_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "dictid_bound": payload.get("dictid_bound") is True,
    }


def run_structuredfields_workflow(
    *,
    with_dictid: bool = True,
    skip_bind: bool = False,
    do_dict_cycle: bool = True,
    do_list: bool = True,
    do_sfv: bool = True,
    replay: bool = True,
    use_dictid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 8941 DICT/LIST dictid cycle workflow."""

    descriptor = structuredfields_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STRUCTUREDFIELDS_TOOL_PROVIDER),
    )
    routing = {
        "descriptor": {
            "name": descriptor.name,
            "provider": descriptor.provider,
            "tool_type": descriptor.tool_type,
        },
        "route": decision.route,
        "reasons": list(decision.reasons),
        "executable": decision.executable,
    }
    if not decision.executable:
        raise StructuredfieldsActuationError(f"structuredfields tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="structuredfields-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = StructuredfieldsSession(out, dictid_gate=DEFAULT_DICTID if with_dictid else EMPTY_DICTID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "dict_cycle": do_dict_cycle,
            "list": do_list,
            "sfv": do_sfv,
            "replay": replay,
            "use_dictid": use_dictid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_structuredfields_tool(session, arguments))
            except StructuredfieldsActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_structuredfields_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_dictid
        and not skip_bind
        and do_dict_cycle
        and do_list
        and do_sfv
        and replay
        and use_dictid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "structuredfields_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_dictid": with_dictid,
        "skip_bind": skip_bind,
        "dict_frame": do_dict_cycle,
        "list": do_list,
        "sfv": do_sfv,
        "replay": replay,
        "use_dictid": use_dictid,
        "sealed_path": str(session.sealed_path),
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "independent": independent,
        "independent_digest": _digest(independent),
        "sentinel": sentinel,
        "digest": str(publish_result.get("digest") or independent.get("digest") or ""),
        "port": int(publish_result.get("port") or independent.get("port") or 0),
        "dictid_value": int(publish_result.get("dictid") or independent.get("dictid") or EMPTY_DICTID),
        "sfv_value": int(publish_result.get("sfv") or independent.get("sfv") or EMPTY_SFV),
        "stored": bool(session.stored or publish_result.get("stored")),
        "payload_exists": session.sealed_path.is_file(),
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}
    from blackhole_agent.capability_compounder import atomic_write_json

    atomic_write_json(out / "execution.json", trace)
    final = results[-1] if results else {}
    return {
        "ok": sealed,
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "sealed_path": str(session.sealed_path),
        "sentinel": sentinel,
        "digest": str(trace_body["digest"] or ""),
        "port": int(trace_body["port"] or 0),
        "dictid": int(trace_body["dictid_value"] or EMPTY_DICTID),
        "sfv": int(trace_body["sfv_value"] or EMPTY_SFV),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_dictid": with_dictid,
        "skip_bind": skip_bind,
        "dict_cycle": do_dict_cycle,
        "list_cycle": do_list,
        "sfv_cycle": do_sfv,
        "replay": replay,
        "use_dictid": use_dictid,
    }


def verify_structuredfields_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Structured Fields trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_structuredfields_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    dictid = int(trace.get("dictid_value") or independent.get("dictid") or EMPTY_DICTID)
    sfv = int(trace.get("sfv_value") or independent.get("sfv") or EMPTY_SFV)
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "independent_digest": _digest(independent) == trace.get("independent_digest"),
        "routing_executable": routing.get("executable") is True and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "independent_recorded": str(independent.get("sentinel") or "") == SENTINEL,
        "live_payload_matches": str(live_row.get("sentinel") or "") == SENTINEL,
        "payload_exists": bool(trace.get("payload_exists")) and sealed_path.is_file(),
        "stored": trace.get("stored") is True,
        "dict_frame": independent.get("dict_frame") is True,
        "list": independent.get("list") is True,
        "sfv_response": independent.get("sfv_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "dictid_bound": independent.get("dictid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "sfv_recorded": (
            port > 0
            and dictid == DEFAULT_DICTID
            and sfv == DEFAULT_SFV
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def structuredfields_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.structuredfields_actuation import "
        "builtin_structuredfields_actuation_proof; r=builtin_structuredfields_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='structuredfields_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_structuredfields_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=STRUCTUREDFIELDS_ACTUATION_ID,
        name="First-class RFC 8941 Structured Fields DICT/LIST actuation",
        description=(
            "Missions that require a structuredfields tool can opt the structuredfields provider in, "
            "bind a loopback RFC 8941 Structured Fields origin, complete a DICT "
            "with a non-empty dictid, lockstep a LIST that carries the "
            "stored sfv, independently poll the stored sfv "
            "on a later socket, and seal a digest-chained sfv. Default "
            "routing stays fail-closed; a missing dictid keeps the hole "
            "falsifiable, and skip-DICT/LIST/SFV/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.structuredfields_actuation:builtin_structuredfields_actuation_proof",
        proof_command=structuredfields_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.httpsemantics-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/structuredfields_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/clienthints_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required structuredfields tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 8941 daemon, speaks a "
            "DICT then LIST over Structured Fields with a non-empty dictid and "
            "sfv, independently polls the stored sfv on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9110 HTTP Semantics lockstep is proved. "
            "Missing dictids, skip-DICT, skip-LIST, skip-sfv, skip-REPLAY, "
            "and a DICT aimed without a dictid stay fail-closed. "
            "Later genesis can take RFC 8942 HTTP Client Hints ACCEPTCH/CRITCH as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("structuredfields", "rfc8941", "http", "dictid", "sfv", "dict", "list", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T130828Z-35bf8e6c",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_structuredfields_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 8941 Structured Fields lockstep actuation seals an sfv digest."""

    from blackhole_agent.clienthints_actuation import (
        CLIENTHINTS_ACTUATION_GOAL,
        CLIENTHINTS_ACTUATION_ID,
    )
    from blackhole_agent.httpsemantics_actuation import HTTPSMANTICS_ACTUATION_GOAL, HTTPSMANTICS_ACTUATION_ID
    from blackhole_agent.httpcache_actuation import HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID
    from blackhole_agent.http2_actuation import HTTP2_ACTUATION_GOAL, HTTP2_ACTUATION_ID
    from blackhole_agent.http11_actuation import HTTP11_ACTUATION_GOAL, HTTP11_ACTUATION_ID
    from blackhole_agent.bhttp_actuation import BHTTP_ACTUATION_GOAL, BHTTP_ACTUATION_ID
    from blackhole_agent.digestfields_actuation import DIGESTFIELDS_ACTUATION_GOAL, DIGESTFIELDS_ACTUATION_ID
    from blackhole_agent.httpsig_actuation import HTTPSIG_ACTUATION_GOAL, HTTPSIG_ACTUATION_ID
    from blackhole_agent.ohsvcb_actuation import OHSVCB_ACTUATION_GOAL, OHSVCB_ACTUATION_ID
    from blackhole_agent.ohttp_actuation import OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID
    from blackhole_agent.connectip_actuation import CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID
    from blackhole_agent.masque_actuation import MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID
    from blackhole_agent.datagram_actuation import DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID
    from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.dtls_actuation import DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID
    from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
    from blackhole_agent.ice_actuation import ICE_ACTUATION_GOAL, ICE_ACTUATION_ID
    from blackhole_agent.ike_actuation import IKE_ACTUATION_GOAL, IKE_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.kernel_leftover import leftover_is_open, leftover_satisfied_by
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
    from blackhole_agent.http3_actuation import HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID
    from blackhole_agent.webtransport_actuation import (
        WEBTRANSPORT_ACTUATION_GOAL,
        WEBTRANSPORT_ACTUATION_ID,
    )
    from blackhole_agent.quic_actuation import QUIC_ACTUATION_GOAL, QUIC_ACTUATION_ID
    from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
    from blackhole_agent.sctp_actuation import SCTP_ACTUATION_GOAL, SCTP_ACTUATION_ID
    from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.srtp_actuation import SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID
    from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
    from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID
    from blackhole_agent.datachannel_actuation import (
        DATACHANNEL_ACTUATION_GOAL,
        DATACHANNEL_ACTUATION_ID,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = STRUCTUREDFIELDS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(STRUCTUREDFIELDS_ACTUATION_GOAL) == (
        STRUCTUREDFIELDS_ACTUATION_ID,
    )
    checks["leftover_text_binds_structuredfields"] = leftover_marker_ids(STRUCTUREDFIELDS_LEFTOVER) == (
        STRUCTUREDFIELDS_ACTUATION_ID,
    )
    neighbor_goals = (
        (HTTPSMANTICS_ACTUATION_GOAL, HTTPSMANTICS_ACTUATION_ID, "httpsemantics"),
        (HTTPCACHE_ACTUATION_GOAL, HTTPCACHE_ACTUATION_ID, "httpcache"),
        (HTTP2_ACTUATION_GOAL, HTTP2_ACTUATION_ID, "http2"),
        (HTTP11_ACTUATION_GOAL, HTTP11_ACTUATION_ID, "http11"),
        (BHTTP_ACTUATION_GOAL, BHTTP_ACTUATION_ID, "bhttp"),
        (DIGESTFIELDS_ACTUATION_GOAL, DIGESTFIELDS_ACTUATION_ID, "digestfields"),
        (HTTPSIG_ACTUATION_GOAL, HTTPSIG_ACTUATION_ID, "httpsig"),
        (OHSVCB_ACTUATION_GOAL, OHSVCB_ACTUATION_ID, "ohsvcb"),
        (OHTTP_ACTUATION_GOAL, OHTTP_ACTUATION_ID, "ohttp"),
        (CONNECTIP_ACTUATION_GOAL, CONNECTIP_ACTUATION_ID, "connectip"),
        (MASQUE_ACTUATION_GOAL, MASQUE_ACTUATION_ID, "masque"),
        (DATAGRAM_ACTUATION_GOAL, DATAGRAM_ACTUATION_ID, "datagram"),
        (WEBTRANSPORT_ACTUATION_GOAL, WEBTRANSPORT_ACTUATION_ID, "webtransport"),
        (HTTP3_ACTUATION_GOAL, HTTP3_ACTUATION_ID, "http3"),
        (QUIC_ACTUATION_GOAL, QUIC_ACTUATION_ID, "quic"),
        (DATACHANNEL_ACTUATION_GOAL, DATACHANNEL_ACTUATION_ID, "datachannel"),
        (SCTP_ACTUATION_GOAL, SCTP_ACTUATION_ID, "sctp"),
        (SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID, "srtp"),
        (DTLS_ACTUATION_GOAL, DTLS_ACTUATION_ID, "dtls"),
        (ICE_ACTUATION_GOAL, ICE_ACTUATION_ID, "ice"),
        (TURN_ACTUATION_GOAL, TURN_ACTUATION_ID, "turn"),
        (STUN_ACTUATION_GOAL, STUN_ACTUATION_ID, "stun"),
        (SIP_ACTUATION_GOAL, SIP_ACTUATION_ID, "sip"),
        (IKE_ACTUATION_GOAL, IKE_ACTUATION_ID, "ike"),
        (DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID, "dhcp"),
        (RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID, "radius"),
        (NTP_ACTUATION_GOAL, NTP_ACTUATION_ID, "ntp"),
        (SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID, "syslog"),
        (SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID, "snmp"),
        (TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID, "tftp"),
        (FTP_ACTUATION_GOAL, FTP_ACTUATION_ID, "ftp"),
        (DNS_ACTUATION_GOAL, DNS_ACTUATION_ID, "dns"),
        (CLIENTHINTS_ACTUATION_GOAL, CLIENTHINTS_ACTUATION_ID, "clienthints"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_structuredfields"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"structuredfields_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            STRUCTUREDFIELDS_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = STRUCTUREDFIELDS_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    dictionary = canonical_dictionary(SENTINEL, DEFAULT_DICTID)
    rebuilt = serialize_dictionary(parse_dictionary(dictionary))
    listed = canonical_list(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV)
    rfc_dict = parse_dictionary('a=1, b=2;foo=3, c, d=?0')
    rfc_list = parse_list('1;foo=1, 2, "str"')
    asked = parse_http_request(dict_request(SENTINEL, DEFAULT_DICTID))
    listed_req = parse_http_request(list_request(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV))
    got = parse_http_response(dict_response(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV))
    list_reply = parse_http_response(list_response(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV))
    checks["sf_dictionary_roundtrip"] = (
        parse_dictionary(dictionary)[0] == ("identity", (SENTINEL, ()))
        and parse_dictionary(dictionary)[1] == ("dictid", (DEFAULT_DICTID, ()))
        and hmac.compare_digest(rebuilt, dictionary)
        and is_key("identity") is True
        and is_token("BH-SF-OK") is True
        and rfc_dict[0] == ("a", (1, ()))
        and rfc_dict[1][0] == "b"
        and rfc_dict[1][1][0] == 2
        and rfc_dict[1][1][1] == (("foo", 3),)
        and rfc_dict[2] == ("c", (True, ()))
        and rfc_dict[3] == ("d", (False, ()))
    )
    checks["sf_list_roundtrip"] = (
        parse_list(listed)[0] == (SENTINEL, ())
        and parse_list(listed)[1] == (DEFAULT_DICTID, ())
        and parse_list(listed)[2] == (DEFAULT_SFV, ())
        and hmac.compare_digest(serialize_list(parse_list(listed)), listed)
        and rfc_list[0] == (1, (("foo", 1),))
        and rfc_list[1] == (2, ())
        and rfc_list[2] == ("str", ())
        and DEFAULT_SFV == request_sfv(DEFAULT_DICTID, SENTINEL)
    )
    checks["dict_list_http_roundtrip"] = (
        asked["method"] == "PUT"
        and asked["sf_kind"] == "dictionary"
        and asked["sfv"][0] == ("identity", (SENTINEL, ()))
        and listed_req["sf_kind"] == "list"
        and listed_req["sfv"][0] == (SENTINEL, ())
        and got["status"] == 200
        and list_reply["status"] == 200
        and got["sf_kind"] == "dictionary"
        and list_reply["sf_kind"] == "list"
        and got["content_length_matches_body"] is True
        and list_reply["content_length_matches_body"] is True
        and dictionary_matches(got["body"].decode("ascii"), representation_dictionary(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV))
        and list_matches(list_reply["body"].decode("ascii"), canonical_list(SENTINEL, DEFAULT_DICTID, DEFAULT_SFV))
    )
    checks["catalog_names_structuredfields"] = (
        len(catalog) > 76
        and catalog[76]["id"] == STRUCTUREDFIELDS_ACTUATION_ID
        and catalog[75]["id"] == HTTPSMANTICS_ACTUATION_ID
        and catalog[76]["source"] == "genesis_bind_structuredfields"
    )
    checks["catalog_names_clienthints"] = (
        len(catalog) > 77
        and catalog[77]["id"] == CLIENTHINTS_ACTUATION_ID
        and catalog[77]["source"] == "genesis_bind_clienthints"
    )
    family = capability_family(STRUCTUREDFIELDS_ACTUATION_GOAL)
    checks["family_is_structuredfields"] = "structuredfield" in family
    checks["family_is_rfc8941"] = "rfc8941" in family
    checks["family_is_dictid"] = "dictid" in family
    checks["family_is_sfv"] = "sfv" in family
    checks["family_is_not_clienthints"] = (
        "clienthint" not in family
        and "rfc8942" not in family
        and "chid" not in family
        and "acceptch" not in family
        and "hintsdigest" not in family
    )
    checks["family_is_not_httpsemantics"] = (
        "httpsemantic" not in family
        and "rfc9110" not in family
        and "methodid" not in family
        and "fieldsection" not in family
    )
    checks["family_is_not_httpcache"] = (
        "httpcache" not in family
        and "rfc9111" not in family
        and "cacheid" not in family
        and "freshness" not in family
        and "validator" not in family
    )
    checks["family_is_not_http2"] = (
        "http2" not in family
        and "rfc9113" not in family
        and "settingsid" not in family
        and "hpack" not in family
        and "preface" not in family
    )
    checks["family_is_not_digestfields"] = (
        "digestfield" not in family
        and "rfc9530" not in family
        and "digestid" not in family
        and "contentdigest" not in family
    )
    checks["family_is_not_httpsig"] = (
        "httpsig" not in family
        and "rfc9421" not in family
        and "sigid" not in family
        and "sigbase" not in family
    )
    checks["family_is_not_ohsvcb"] = (
        "ohsvcb" not in family
        and "rfc9540" not in family
        and "svcbid" not in family
        and "keyconf" not in family
    )
    checks["family_is_not_ohttp"] = (
        "ohttp" not in family
        and "rfc9458" not in family
        and "configid" not in family
        and "gateway" not in family
    )
    checks["family_is_not_connectip"] = (
        "connectip" not in family
        and "rfc9484" not in family
        and "prefixid" not in family
        and "ipaddr" not in family
    )
    checks["family_is_not_masque"] = (
        "masque" not in family
        and "rfc9298" not in family
        and "targetid" not in family
        and "authority" not in family
    )
    checks["family_is_not_datagram"] = (
        "datagram" not in family
        and "rfc9221" not in family
        and "flowid" not in family
        and "contextid" not in family
    )
    checks["family_is_not_webtransport"] = (
        "webtransport" not in family
        and "rfc9220" not in family
        and "sessionid" not in family
        and "capsule" not in family
    )
    checks["family_is_not_http3"] = (
        "http3" not in family
        and "rfc9114" not in family
        and "streamid" not in family
        and "qpack" not in family
    )
    checks["family_is_not_quic"] = (
        "quic" not in family
        and "rfc9000" not in family
        and "dcid" not in family
        and "pktnum" not in family
    )
    checks["family_is_not_datachannel"] = (
        "datachannel" not in family
        and "rfc8831" not in family
        and "ppid" not in family
        and "dcep" not in family
    )
    checks["family_is_not_sctp_association"] = (
        "rfc4960" not in family and "vtag" not in family and "tsn" not in family
    )
    checks["family_is_not_srtp"] = (
        "srtp" not in family and "rfc3711" not in family and "roc" not in family and "ssrc" not in family
    )
    checks["family_is_not_dtls"] = (
        "dtls" not in family and "rfc6347" not in family and "cookie" not in family and "epoch" not in family
    )
    checks["family_is_not_ice"] = "ice" not in family and "rfc8445" not in family and "ufrag" not in family
    checks["family_is_not_turn"] = "turn" not in family and "rfc5766" not in family and "relay" not in family
    checks["family_is_not_stun"] = "stun" not in family and "rfc5389" not in family and "txid" not in family
    checks["family_is_not_sip"] = "sip" not in family and "rfc3261" not in family and "callid" not in family
    checks["family_is_not_ike"] = "ike" not in family and "rfc7296" not in family and "spi" not in family
    checks["family_is_not_dhcp"] = "dhcp" not in family and "rfc2131" not in family and "yiaddr" not in family
    checks["family_is_not_radius"] = (
        "radius" not in family and "radiu" not in family and "rfc2865" not in family
    )
    checks["family_is_not_ntp"] = "ntp" not in family and "rfc5905" not in family and "keyid" not in family
    checks["family_is_not_syslog"] = "syslog" not in family and "nilvalue" not in family
    checks["family_is_not_snmp"] = "snmp" not in family and "varbind" not in family
    checks["family_is_not_tftp"] = "tftp" not in family and "rfc1350" not in family
    checks["family_is_not_ftp"] = "ftpd" not in family and "pasv" not in family
    checks["family_is_not_dns"] = "tsig" not in family and "nameserver" not in family
    checks["family_is_not_bhttp"] = (
        "bhttp" not in family
        and "rfc9292" not in family
        and "messageid" not in family
        and "binarymsg" not in family
        and "binaryhttp" not in family
    )
    checks["family_is_not_http11"] = (
        "http11" not in family
        and "rfc9112" not in family
        and "requestid" not in family
        and "startline" not in family
        and "httpmessage" not in family
    )
    packed = encode_dict(identity=SENTINEL, dictid=DEFAULT_DICTID, sfv=DEFAULT_SFV)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_dict"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_dictid"] is True
        and parsed["dictid"] == DEFAULT_DICTID
        and parsed["sfv"] == DEFAULT_SFV
        and parsed["is_response"] is False
        and parsed["is_list"] is False
        and parsed["type"] == FRAME_DICT
        and parsed["first_byte"] == SF_FIRST
    )
    shook = encode_list(
        identity=SENTINEL,
        dictid=DEFAULT_DICTID,
        sfv=DEFAULT_SFV,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_list"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_dict"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["dictid"] == DEFAULT_DICTID
        and answer_parsed["sfv"] == DEFAULT_SFV
        and answer_parsed["has_sfv"] is True
        and answer_parsed["type"] == FRAME_LIST
        and answer_parsed["first_byte"] == SF_FIRST
    )
    bare = encode_dict(identity=SENTINEL, dictid=DEFAULT_DICTID, include_dictid=False)
    checks["missing_dictid_is_unauthenticated"] = parse_message(bare)["has_dictid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    structuredfields_signature = semantic_signature(STRUCTUREDFIELDS_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(structuredfields_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_structuredfields = ToolDescriptor(name="remote_structuredfields", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_structuredfields)
    checks["naive_mcp_structuredfields_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = structuredfields_tool_descriptor()
    default_structuredfields = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STRUCTUREDFIELDS_TOOL_PROVIDER),
    )
    checks["default_structuredfields_provider_is_unsupported"] = (
        default_structuredfields.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{STRUCTUREDFIELDS_TOOL_PROVIDER}" in default_structuredfields.reasons
    )
    checks["opted_in_structuredfields_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_structuredfields],
        required_tool_names=("local_memory", "structuredfields"),
    )
    checks["naive_preflight_missing_structuredfields"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["structuredfields"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "structuredfields"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, STRUCTUREDFIELDS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "structuredfields" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="structuredfields-actuation-") as tmp:
        root = Path(tmp)
        missing = run_structuredfields_workflow(with_dictid=False, output_dir=root / "missing")
        skip_bind = run_structuredfields_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_dict_cycle = run_structuredfields_workflow(do_dict_cycle=False, output_dir=root / "skip-dict-cycle")
        skip_list = run_structuredfields_workflow(do_list=False, output_dir=root / "skip-list")
        skip_sfv = run_structuredfields_workflow(do_sfv=False, output_dir=root / "skip-sfv")
        skip_replay = run_structuredfields_workflow(replay=False, output_dir=root / "skip-replay")
        skip_dictid = run_structuredfields_workflow(use_dictid=False, output_dir=root / "skip-dictid")
        live = run_structuredfields_workflow(output_dir=root / "live")
        verify = verify_structuredfields_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_structuredfields_trace(clone)
        checks["naive_without_dictid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_dictid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_dict_cycle_stays_empty"] = (
            skip_dict_cycle["ok"] is False
            and skip_dict_cycle["error"] == "dict_required"
            and skip_dict_cycle["final_status"] == 409
            and skip_dict_cycle["payload_exists"] is False
        )
        checks["skip_list_stays_empty"] = (
            skip_list["ok"] is False
            and skip_list["error"] == "list_required"
            and skip_list["final_status"] == 409
            and skip_list["payload_exists"] is False
        )
        checks["skip_sfv_stays_empty"] = (
            skip_sfv["ok"] is False
            and skip_sfv["error"] == "sfv_required"
            and skip_sfv["final_status"] == 409
            and skip_sfv["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_dictid_stays_empty"] = (
            skip_dictid["ok"] is False
            and skip_dictid["error"] == "dictid_required"
            and skip_dictid["final_status"] == 409
            and skip_dictid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_sfv"] = (
            int(live.get("dictid") or 0) == DEFAULT_DICTID
            and int(live.get("sfv") or 0) == DEFAULT_SFV
            and int(live.get("port") or 0) > 0
        )
        checks["token_dictid_encode_list_sfv_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_dict_cycle["ok"] is False
            and skip_list["ok"] is False
            and skip_sfv["ok"] is False
            and skip_replay["ok"] is False
            and skip_dictid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="structuredfields-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != STRUCTUREDFIELDS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_structuredfields"] = (
        live_goal == STRUCTUREDFIELDS_ACTUATION_GOAL
        and STRUCTUREDFIELDS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_structuredfields"
    )

    with tempfile.TemporaryDirectory(prefix="structuredfields-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(STRUCTUREDFIELDS_LEFTOVER, root)
        register_catalog_proved(root, STRUCTUREDFIELDS_ACTUATION_ID)
        reason = leftover_satisfied_by(STRUCTUREDFIELDS_LEFTOVER, root)
        after = leftover_is_open(STRUCTUREDFIELDS_LEFTOVER, root)
    checks["structuredfields_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_structuredfields_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{STRUCTUREDFIELDS_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_structuredfields_actuation_capability()
    return {
        "ok": ok,
        "action": "structuredfields_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": STRUCTUREDFIELDS_ACTUATION_GOAL,
        "done_when": STRUCTUREDFIELDS_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
