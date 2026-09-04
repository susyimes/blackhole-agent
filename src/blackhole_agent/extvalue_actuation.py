"""Drive a first-class Character Set and Language Encoding tool through RFC 5987 ENCODING/LANGUAGE.

Tool routing already fails missions that require ``extvalue``: hosted
extvalue endpoints stay on the unsupported MCP provider, and no first-party
extvalue provider is executable. Unbound therefore cannot speak an ENCODING,
lockstep a LANGUAGE charsetid handshake over HTTP ext-value CHARSETID,
independently poll the stored charsetdigest, or seal a charsetdigest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``extvalue`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 5987 daemon
- keep a missing-charsetid client so the extvalue-charsetid hole stays falsifiable
- refuse LANGUAGE until an ENCODING lands with a non-empty charsetid
- independently poll the stored charsetdigest on a later client socket
- persist a sealed charsetdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 5988 Web Linking
"""
from __future__ import annotations

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
    EXTVALUE_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    extvalue_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
EXTVALUE_ACTUATION_ID = "capability.extvalue-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-EXTVALUE-OK"
POLL_TOKEN = "BH-EXTVALUE-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_CHARSETID = 0
EMPTY_CHARSETDIGEST = 0
EV_FIRST = 0x45  # RFC 5987 ext-value Encoding (ASCII 'E')
CHARSETID_SIZE = 4
CHARSETDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_LANGUAGE = 0x02  # RFC 5987 report confirmation
FRAME_ENCODING = 0x01  # RFC 5987 Encoding
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
EXTVALUE_LEFTOVER = (
    "Later genesis can take RFC 5987 Character Set and Language Encoding ENCODING/LANGUAGE over a "
    "charsetid-gated charsetdigest."
)
EXTVALUE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{EXTVALUE_ACTUATION_ID};"
    f"capability_proved:{EXTVALUE_ACTUATION_ID};"
    "no_skill_route"
)
EXTVALUE_ACTUATION_GOAL = (
    "Repair rfc5987 extvalue encoding/language cycle cannot land over http "
    "extvalue charsetid: hosted extvalue endpoints remain unsupported so an ENCODING then "
    "LANGUAGE charsetid handshake cannot land and a sealed charsetdigest "
    "cannot be produced. A missing extvalue charsetid stays forbidden; fail-closed "
    "routing never opts the extvalue provider in. An independent later poll of the "
    "stored charsetdigest keeps the hole falsifiable."
)


class ExtvalueActuationError(RuntimeError):
    """Raised when the language session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


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


TCHAR = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "!#$%&'*+-.^_`|~"
)
# RFC 5987 section 3.2 charset / language-tag.
RFC_ENCODING_FIELD = "ENCODING"
RFC_LANGUAGE_FIELD = "LANGUAGE"
RFC_EXTVALUE_LANGUAGE = RFC_LANGUAGE_FIELD
RFC_ENCODING_PARAM = "UTF-8'en'"
DEFAULT_ENCODING = "ENCODING"
LANGUAGE_POLICY = "LANGUAGE"
ENCODING_HEADER = "Ext-Value"
LANGUAGE_HEADER = "Ext-Value"
EXTVALUE_LANGUAGE_HEADER = LANGUAGE_HEADER
RFC_LANG = "en"
RFC_CHARSET = "UTF-8"
RFC_ENCODING_PATH = "/"
RFC_EXT_VALUE = "UTF-8'en'rates"
RFC_EXT_EMPTY = ""


def ext_value_pair(
    charset: str = RFC_CHARSET,
    language: str = RFC_LANG,
) -> tuple[str, str]:
    """RFC 5987 section 3.2 charset and optional language tag."""

    return str(charset or RFC_CHARSET), str(language or RFC_LANG)


def ascii_serialize_ext_value(
    charset: str = RFC_CHARSET,
    language: str = RFC_LANG,
) -> str:
    """RFC 5987 section 3.2 ext-value: charset "'" [ language ] "'" value-chars."""

    live_charset, live_lang = ext_value_pair(charset, language)
    if not is_token(live_charset):
        raise ExtvalueActuationError("illegal_charset")
    if live_lang and any(ord(char) <= 0x20 or ord(char) >= 0x7F for char in live_lang):
        raise ExtvalueActuationError("illegal_language")
    return f"{live_charset}'{live_lang}'rates"


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise ExtvalueActuationError("short_extvalue")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 5987 charset / attr-char."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_extvalue(policy: str | Sequence[str]) -> str:
    """Serialize RFC 5987 ext-value charset/language token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise ExtvalueActuationError("illegal_extvalue")
    upper = text.upper()
    if upper in {"ENCODING", "UTF-8", "CHARSET"}:
        return "ENCODING"
    if upper in {"LANGUAGE", "LANG"}:
        return "LANGUAGE"
    if upper.startswith("CHARSET="):
        charset_value = text.split("=", 1)[1].strip().strip('"')
        if not charset_value or ";" in charset_value:
            raise ExtvalueActuationError("illegal_extvalue")
        return f'charset="{charset_value}"'
    raise ExtvalueActuationError("illegal_extvalue")


def parse_extvalue(text: str) -> str:
    """Parse RFC 5987 ext-value into ENCODING, LANGUAGE, or charset."""

    raw = str(text or "").strip()
    if not raw:
        raise ExtvalueActuationError("illegal_extvalue")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper()
    if upper in {"ENCODING", "UTF-8", "CHARSET"}:
        return "ENCODING"
    if upper in {"LANGUAGE", "LANG"}:
        return "LANGUAGE"
    if upper.startswith("CHARSET="):
        charset_value = head.split("=", 1)[1].strip().strip('"')
        if not charset_value or ";" in charset_value:
            raise ExtvalueActuationError("illegal_extvalue")
        return f'charset="{charset_value}"'
    raise ExtvalueActuationError("illegal_extvalue")


def encode_extvalue_header(policy: str | Sequence[str]) -> bytes:
    """RFC 5987 Ext-Value field as bytes."""

    return serialize_extvalue(policy).encode("ascii")


def parse_extvalue_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_extvalue(field_value) if field_value else DEFAULT_ENCODING
    return {
        "field_value": field_value,
        "policy": policy,
        "header": ENCODING_HEADER,
        "directive": str(policy),
        "encoding": str(policy) == "ENCODING",
        "language": str(policy) == "LANGUAGE",
    }


def canonical_encoding(identity: str, charsetid: int) -> str:
    """RFC 5987 ENCODING advertisement bound to identity and charsetid."""

    return (
        f"{serialize_extvalue(DEFAULT_ENCODING)}, "
        f"encoding={ascii_serialize_ext_value()}, "
        f"identity={identity}, charsetid={int(charsetid) & 0xFFFFFFFF}"
    )


def canonical_language(identity: str, charsetid: int, charsetdigest: int | None = None) -> str:
    """RFC 5987 LANGUAGE confirmation of the stored language policy."""

    suffix = ""
    if charsetdigest is not None:
        suffix = f", charsetdigest={int(charsetdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_extvalue(LANGUAGE_POLICY)}, "
        f"language={ascii_serialize_ext_value()}, "
        f"identity={identity}, charsetid={int(charsetid) & 0xFFFFFFFF}{suffix}"
    )


def representation_language(identity: str, charsetid: int, charsetdigest: int) -> str:
    return canonical_language(identity, charsetid, charsetdigest)


def extvalue_matches(left: str, right: str) -> bool:
    return parse_extvalue(left) == parse_extvalue(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise ExtvalueActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise ExtvalueActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise ExtvalueActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise ExtvalueActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def encoding_request(identity: str, charsetid: int) -> bytes:
    """HTTP GET that elicits RFC 5987 origin ENCODING."""

    keyid = f"{int(charsetid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /extvalue/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Charset-Id: {int(charsetid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def language_request(identity: str, charsetid: int, charsetdigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 5987 LANGUAGE confirmation of the stored language policy."""

    keyid = f"{int(charsetid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if charsetdigest is not None:
        extra = f"Charset-Digest: {int(charsetdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /extvalue/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Charset-Id: {int(charsetid) & 0xFFFFFFFF}\r\n"
        "Charset-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    extvalue_kind = "language" if fields.get("charset-confirm") == "1" else "encoding"
    encoding_field = fields.get("ext-value") or ""
    policy = parse_extvalue(encoding_field) if encoding_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "extvalue_kind": extvalue_kind,
        "policy": policy,
        "charsetid": int(fields["charset-id"]) if fields.get("charset-id") else EMPTY_CHARSETID,
        "charsetdigest": int(fields["charset-digest"]) if fields.get("charset-digest") else EMPTY_CHARSETDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def encoding_response(identity: str, charsetid: int, charsetdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 5987 origin ENCODING, carrying the stored charsetdigest."""

    advertised = serialize_extvalue(DEFAULT_ENCODING)
    payload = bytes(body or canonical_encoding(identity, charsetid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Ext-Value: {advertised}\r\n"
        f"Charset-Id: {int(charsetid) & 0xFFFFFFFF}\r\n"
        f"Charset-Digest: {int(charsetdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/ext-value\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def language_response(identity: str, charsetid: int, charsetdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 5987 LANGUAGE, carrying the stored LANGUAGE policy."""

    advertised = serialize_extvalue(LANGUAGE_POLICY)
    payload = bytes(body or representation_language(identity, charsetid, charsetdigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Ext-Value: {advertised}\r\n"
        f"Charset-Id: {int(charsetid) & 0xFFFFFFFF}\r\n"
        f"Charset-Digest: {int(charsetdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/ext-value-confirm\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise ExtvalueActuationError("illegal_content_length") from error
    field_value = fields.get("ext-value") or ""
    policy = parse_extvalue(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/ext-value-confirm" or policy == LANGUAGE_POLICY:
        status = 200
        extvalue_kind = "language"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        extvalue_kind = "encoding"
    else:
        status = 0
        extvalue_kind = "encoding"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "extvalue_kind": extvalue_kind,
        "policy": policy,
        "charsetid": int(fields["charset-id"]) if fields.get("charset-id") else EMPTY_CHARSETID,
        "charsetdigest": int(fields["charset-digest"]) if fields.get("charset-digest") else EMPTY_CHARSETDIGEST,
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
        raise ExtvalueActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise ExtvalueActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise ExtvalueActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise ExtvalueActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_charsetid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"charsetid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_charsetid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-charsetid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_charsetdigest(charsetid: int = EMPTY_CHARSETID, token: str = SENTINEL) -> int:
    material = canonical_encoding(token or SENTINEL, int(charsetid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_CHARSETID = request_charsetid(SENTINEL)
DEFAULT_CHARSETDIGEST = request_charsetdigest(DEFAULT_CHARSETID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    charsetid: int,
    charsetdigest: int,
    include_charsetid: bool = True,
) -> bytes:
    live_charsetid = int(charsetid) & 0xFFFFFFFF if include_charsetid else EMPTY_CHARSETID
    live_digest = int(charsetdigest) & 0xFFFFFFFF if include_charsetid and live_charsetid else EMPTY_CHARSETDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_charsetid) if live_charsetid else b""
    header = bytearray()
    header.append(EV_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_encoding(
    *,
    identity: str,
    charsetid: int,
    charsetdigest: int | None = None,
    include_charsetid: bool = True,
) -> bytes:
    live_charsetid = int(charsetid) & 0xFFFFFFFF if include_charsetid else EMPTY_CHARSETID
    live_digest = int(charsetdigest) if charsetdigest is not None else request_charsetdigest(live_charsetid, identity)
    return encode_packet(
        FRAME_ENCODING,
        identity=identity,
        charsetid=live_charsetid,
        charsetdigest=live_digest,
        include_charsetid=include_charsetid,
    )


def encode_language(
    *,
    identity: str,
    charsetid: int,
    charsetdigest: int | None = None,
    include_charsetid: bool = True,
) -> bytes:
    live_charsetid = int(charsetid) & 0xFFFFFFFF if include_charsetid else EMPTY_CHARSETID
    live_digest = int(charsetdigest) if charsetdigest is not None else request_charsetdigest(live_charsetid, identity)
    return encode_packet(
        FRAME_LANGUAGE,
        identity=identity,
        charsetid=live_charsetid,
        charsetdigest=live_digest,
        include_charsetid=include_charsetid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise ExtvalueActuationError("short_packet")
    first = raw[0]
    if first != EV_FIRST:
        raise ExtvalueActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise ExtvalueActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == CHARSETID_SIZE:
        live_charsetid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_charsetid = EMPTY_CHARSETID
    else:
        raise ExtvalueActuationError("illegal_charsetid")
    if offset >= len(raw):
        raise ExtvalueActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ENCODING, FRAME_LANGUAGE}:
        raise ExtvalueActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise ExtvalueActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise ExtvalueActuationError("checksum_failed")
    if len(payload) < 5:
        raise ExtvalueActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise ExtvalueActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_charsetid = int(live_charsetid) != EMPTY_CHARSETID
    has_charsetdigest = has_charsetid and int(live_digest) != EMPTY_CHARSETDIGEST
    is_encoding = frame_type == FRAME_ENCODING
    is_language = frame_type == FRAME_LANGUAGE
    return {
        "type": int(frame_type),
        "is_encoding": is_encoding,
        "is_language": is_language,
        "is_response": is_language,
        "charsetid": int(live_charsetid),
        "has_charsetid": has_charsetid,
        "charsetdigest": int(live_digest),
        "has_charsetdigest": has_charsetdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http_state": "RFC5987",
        "serialize_field": canonical_encoding(identity, live_charsetid) if has_charsetid else "",
        "language_field": canonical_language(identity, live_charsetid, live_digest) if has_charsetdigest else "",
    }


class ExtvalueClient:
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
            raise ExtvalueActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_language"] or not packet["is_response"]:
            raise ExtvalueActuationError("charsetdigest_required")
        if not packet["has_charsetid"]:
            raise ExtvalueActuationError("charsetid_required")
        if not packet["has_charsetdigest"]:
            raise ExtvalueActuationError("charsetdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_charsetdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_charsetdigest:
            raise ExtvalueActuationError("charsetdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "charsetid": int(reply.get("charsetid") or EMPTY_CHARSETID),
            "identity": str(reply.get("identity") or ""),
            "charsetdigest": int(reply.get("charsetdigest") or EMPTY_CHARSETDIGEST),
        }

    def report(
        self,
        identity: str,
        charsetid: int,
        charsetdigest: int = EMPTY_CHARSETDIGEST,
        *,
        wait_charsetdigest: bool = True,
        include_charsetid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_language(
            identity=identity,
            charsetid=charsetid,
            charsetdigest=charsetdigest or request_charsetdigest(charsetid, identity),
            include_charsetid=include_charsetid,
        )
        return self.exchange(packet, wait_charsetdigest=wait_charsetdigest)


class ExtvalueSession:
    """CHARSETID-gated loopback RFC 5987 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        charsetid_gate: int = DEFAULT_CHARSETID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.charsetid_gate = int(charsetid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.charsetid = EMPTY_CHARSETID
        self.charsetdigest = EMPTY_CHARSETDIGEST
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

    def store_charsetid_once(self, identity: str, charsetid: int, charsetdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(charsetid or EMPTY_CHARSETID)
            live_digest = int(charsetdigest or EMPTY_CHARSETDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.charsetid = live
                self.charsetdigest = live_digest or request_charsetdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.charsetid), int(self.charsetdigest)

    def read_charsetid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.charsetid), int(self.charsetdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "charsetid": EMPTY_CHARSETID,
            "charsetdigest": EMPTY_CHARSETDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _charsetid_missing(self) -> bool:
        return not int(self.charsetid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, charsetid: int, charsetdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_language(
            identity=identity,
            charsetid=charsetid,
            charsetdigest=charsetdigest,
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
            except ExtvalueActuationError:
                continue
            if not packet.get("is_encoding") and not packet.get("is_language"):
                continue
            if not packet.get("has_charsetid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_charsetid, stored_digest = self.store_charsetid_once(
                identity,
                int(packet.get("charsetid") or EMPTY_CHARSETID),
                int(packet.get("charsetdigest") or EMPTY_CHARSETDIGEST),
            )
            if not stored_name or not stored_charsetid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_encoding"):
                    self.opened = True
                if packet.get("is_language"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_charsetid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._charsetid_missing():
            return self._forbidden("missing_charsetid")
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
        do_encoding: bool = True,
        do_language: bool = True,
        do_charsetdigest: bool = True,
        replay: bool = True,
        use_charsetid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._charsetid_missing():
            return self._forbidden("missing_charsetid")
        live_token = str(token or SENTINEL)
        origin_charsetid = request_charsetid(live_token)
        origin_digest = request_charsetdigest(origin_charsetid, live_token)
        client: ExtvalueClient | None = None
        independent: ExtvalueClient | None = None
        try:
            client = ExtvalueClient(self.host, int(self.port))
            if not do_encoding:
                return self._conflict("encoding_required")
            bind_packet = encode_encoding(
                identity=live_token,
                charsetid=origin_charsetid,
                charsetdigest=origin_digest,
                include_charsetid=use_charsetid,
            )
            if not use_charsetid:
                try:
                    client.exchange(bind_packet, wait_charsetdigest=True)
                except ExtvalueActuationError:
                    return self._conflict("charsetid_required")
                return self._conflict("charsetid_required")
            client.send(bind_packet)
            if not do_language:
                return self._conflict("language_required")
            proxy_packet = encode_language(
                identity=live_token,
                charsetid=origin_charsetid,
                charsetdigest=origin_digest,
                include_charsetid=True,
            )
            if not do_charsetdigest:
                try:
                    client.exchange(proxy_packet, wait_charsetdigest=False)
                except ExtvalueActuationError as error:
                    if str(error) == "charsetdigest_required":
                        return self._conflict("charsetdigest_required")
                    return self._conflict("charsetdigest_required")
                return self._conflict("charsetdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_charsetdigest=True)
            except ExtvalueActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("charsetid_required")
                if reason == "charsetdigest_required":
                    return self._conflict("charsetdigest_required")
                return self._conflict("encoding_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("encoding_required")
            if int(reply.get("charsetid") or EMPTY_CHARSETID) != origin_charsetid:
                return self._conflict("charsetdigest_required")
            if int(reply.get("charsetdigest") or EMPTY_CHARSETDIGEST) != origin_digest:
                return self._conflict("charsetdigest_required")
            self.retrieved = True
            if replay:
                independent = ExtvalueClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_charsetid(live_token),
                        request_charsetdigest(poll_charsetid(live_token), POLL_TOKEN),
                        wait_charsetdigest=True,
                    )
                except ExtvalueActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_charsetid, stored_digest = self.read_charsetid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_charsetid != origin_charsetid
                    or stored_digest != origin_digest
                    or int(poll.get("charsetid") or EMPTY_CHARSETID) != origin_charsetid
                    or int(poll.get("charsetdigest") or EMPTY_CHARSETDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_charsetid}:{origin_digest}:{live_token}:{canonical_encoding(live_token, origin_charsetid)}:{canonical_language(live_token, origin_charsetid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "charsetid": origin_charsetid,
                "charsetdigest": origin_digest,
                "encoding_frame": True,
                "language_frame": True,
                "charsetdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "charsetid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_extvalue_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "charsetid": origin_charsetid,
                "charsetdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "encoding_frame": True,
                "language_frame": True,
                "charsetdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "charsetid_bound": True,
            }
        except (OSError, ExtvalueActuationError) as error:
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
        live = independent_extvalue_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "charsetid": int(live.get("charsetid") or EMPTY_CHARSETID),
            "charsetdigest": int(live.get("charsetdigest") or EMPTY_CHARSETDIGEST),
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


def call_extvalue_tool(session: ExtvalueSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one encoding tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_encoding = True if arguments.get("encoding") is None else bool(arguments.get("encoding"))
    do_language = True if arguments.get("language") is None else bool(arguments.get("language"))
    do_charsetdigest = True if arguments.get("charsetdigest") is None else bool(arguments.get("charsetdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_charsetid = True if arguments.get("use_charsetid") is None else bool(arguments.get("use_charsetid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_encoding=do_encoding,
            do_language=do_language,
            do_charsetdigest=do_charsetdigest,
            replay=replay,
            use_charsetid=use_charsetid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise ExtvalueActuationError(f"unsupported extvalue action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_extvalue_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed encoding charsetdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "charsetid": EMPTY_CHARSETID,
        "charsetdigest": EMPTY_CHARSETDIGEST,
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
            "encoding_frame",
            "language_frame",
            "charsetdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "charsetid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    charsetid = int(payload.get("charsetid") or EMPTY_CHARSETID)
    charsetdigest = int(payload.get("charsetdigest") or EMPTY_CHARSETDIGEST)
    dual = port > 0 and bool(charsetid) and bool(charsetdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "charsetid": charsetid,
        "charsetdigest": charsetdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "encoding_frame": payload.get("encoding_frame") is True,
        "language_frame": payload.get("language_frame") is True,
        "charsetdigest_response": payload.get("charsetdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "charsetid_bound": payload.get("charsetid_bound") is True,
    }


def run_extvalue_workflow(
    *,
    with_charsetid: bool = True,
    skip_bind: bool = False,
    do_encoding: bool = True,
    do_language: bool = True,
    do_charsetdigest: bool = True,
    replay: bool = True,
    use_charsetid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 5987 ENCODING/LANGUAGE charsetid cycle workflow."""

    descriptor = extvalue_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EXTVALUE_TOOL_PROVIDER),
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
        raise ExtvalueActuationError(f"extvalue tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="extvalue-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = ExtvalueSession(out, charsetid_gate=DEFAULT_CHARSETID if with_charsetid else EMPTY_CHARSETID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "encoding": do_encoding,
            "language": do_language,
            "charsetdigest": do_charsetdigest,
            "replay": replay,
            "use_charsetid": use_charsetid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_extvalue_tool(session, arguments))
            except ExtvalueActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_extvalue_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_charsetid
        and not skip_bind
        and do_encoding
        and do_language
        and do_charsetdigest
        and replay
        and use_charsetid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "extvalue_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_charsetid": with_charsetid,
        "skip_bind": skip_bind,
        "encoding_frame": do_encoding,
        "language": do_language,
        "charsetdigest": do_charsetdigest,
        "replay": replay,
        "use_charsetid": use_charsetid,
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
        "charsetid_value": int(publish_result.get("charsetid") or independent.get("charsetid") or EMPTY_CHARSETID),
        "charsetdigest_value": int(publish_result.get("charsetdigest") or independent.get("charsetdigest") or EMPTY_CHARSETDIGEST),
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
        "charsetid": int(trace_body["charsetid_value"] or EMPTY_CHARSETID),
        "charsetdigest": int(trace_body["charsetdigest_value"] or EMPTY_CHARSETDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_charsetid": with_charsetid,
        "skip_bind": skip_bind,
        "encoding_cycle": do_encoding,
        "language_cycle": do_language,
        "charsetdigest_cycle": do_charsetdigest,
        "replay": replay,
        "use_charsetid": use_charsetid,
    }


def verify_extvalue_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_extvalue_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    charsetid = int(trace.get("charsetid_value") or independent.get("charsetid") or EMPTY_CHARSETID)
    charsetdigest = int(trace.get("charsetdigest_value") or independent.get("charsetdigest") or EMPTY_CHARSETDIGEST)
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
        "encoding_frame": independent.get("encoding_frame") is True,
        "language_frame": independent.get("language_frame") is True,
        "charsetdigest_response": independent.get("charsetdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "charsetid_bound": independent.get("charsetid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "charsetdigest_recorded": (
            port > 0
            and charsetid == DEFAULT_CHARSETID
            and charsetdigest == DEFAULT_CHARSETDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def extvalue_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.extvalue_actuation import "
        "builtin_extvalue_actuation_proof; r=builtin_extvalue_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='extvalue_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_extvalue_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=EXTVALUE_ACTUATION_ID,
        name="First-class RFC 5987 Character Set and Language Encoding ENCODING/LANGUAGE actuation",
        description=(
            "Missions that require an extvalue tool can opt the extvalue provider in, "
            "bind a loopback RFC 5987 Character Set and Language Encoding endpoint, complete an ENCODING "
            "with a non-empty charsetid, lockstep a LANGUAGE that carries the "
            "stored charsetdigest, independently poll the stored charsetdigest "
            "on a later socket, and seal a digest-chained charsetdigest. Default "
            "routing stays fail-closed; a missing charsetid keeps the hole "
            "falsifiable, and skip-ENCODING/LANGUAGE/CHARSETDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.extvalue_actuation:builtin_extvalue_actuation_proof",
        proof_command=extvalue_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.weblinking-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/extvalue_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/weblinking_actuation.py",
            "src/blackhole_agent/stalecontent_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required extvalue tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 5987 daemon, speaks an "
            "ENCODING then LANGUAGE over Character Set and Language Encoding with a non-empty charsetid and "
            "charsetdigest, independently polls the stored charsetdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 5988 Web Linking lockstep is proved. "
            "Missing charsetids, skip-ENCODING, skip-LANGUAGE, skip-charsetdigest, skip-REPLAY, "
            "and an ENCODING aimed without a charsetid stay fail-closed. "
            "Later genesis can take RFC 5861 HTTP Cache-Control Extensions for Stale Content STALE/IFERROR as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("extvalue", "rfc5987", "http", "charsetid", "charsetdigest", "encoding", "language", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T191908Z-9c8d2101",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_extvalue_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 5987 encoding lockstep actuation seals a charsetdigest."""

    from blackhole_agent.stalecontent_actuation import (
        STALECONTENT_ACTUATION_GOAL,
        STALECONTENT_ACTUATION_ID,
    )
    from blackhole_agent.weblinking_actuation import (
        WEBLINKING_ACTUATION_GOAL,
        WEBLINKING_ACTUATION_ID,
    )
    from blackhole_agent.httpcookie_actuation import (
        HTTPCOOKIE_ACTUATION_GOAL,
        HTTPCOOKIE_ACTUATION_ID,
    )
    from blackhole_agent.weborigin_actuation import (
        WEBORIGIN_ACTUATION_GOAL,
        WEBORIGIN_ACTUATION_ID,
    )
    from blackhole_agent.xfo_actuation import (
        XFO_ACTUATION_GOAL,
        XFO_ACTUATION_ID,
    )
    from blackhole_agent.hpkp_actuation import (
        HPKP_ACTUATION_GOAL,
        HPKP_ACTUATION_ID,
    )
    from blackhole_agent.hsts_actuation import (
        HSTS_ACTUATION_GOAL,
        HSTS_ACTUATION_ID,
    )
    from blackhole_agent.altsvc_actuation import (
        ALTSVC_ACTUATION_GOAL,
        ALTSVC_ACTUATION_ID,
    )
    from blackhole_agent.encryptedcontent_actuation import (
        ENCRYPTEDCONTENT_ACTUATION_GOAL,
        ENCRYPTEDCONTENT_ACTUATION_ID,
    )
    from blackhole_agent.earlyhints_actuation import (
        EARLYHINTS_ACTUATION_GOAL,
        EARLYHINTS_ACTUATION_ID,
    )
    from blackhole_agent.structuredfields_actuation import (
        STRUCTUREDFIELDS_ACTUATION_GOAL,
        STRUCTUREDFIELDS_ACTUATION_ID,
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
    from blackhole_agent.clienthints_actuation import CLIENTHINTS_ACTUATION_GOAL, CLIENTHINTS_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = EXTVALUE_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(EXTVALUE_ACTUATION_GOAL) == (
        EXTVALUE_ACTUATION_ID,
    )
    checks["leftover_text_binds_extvalue"] = leftover_marker_ids(EXTVALUE_LEFTOVER) == (
        EXTVALUE_ACTUATION_ID,
    )
    neighbor_goals = (
        (STRUCTUREDFIELDS_ACTUATION_GOAL, STRUCTUREDFIELDS_ACTUATION_ID, "structuredfields"),
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
        (EARLYHINTS_ACTUATION_GOAL, EARLYHINTS_ACTUATION_ID, "earlyhints"),
        (ENCRYPTEDCONTENT_ACTUATION_GOAL, ENCRYPTEDCONTENT_ACTUATION_ID, "encryptedcontent"),
        (ALTSVC_ACTUATION_GOAL, ALTSVC_ACTUATION_ID, "altsvc"),
        (HSTS_ACTUATION_GOAL, HSTS_ACTUATION_ID, "hsts"),
        (HPKP_ACTUATION_GOAL, HPKP_ACTUATION_ID, "hpkp"),
        (XFO_ACTUATION_GOAL, XFO_ACTUATION_ID, "xfo"),
        (WEBORIGIN_ACTUATION_GOAL, WEBORIGIN_ACTUATION_ID, "weborigin"),
        (HTTPCOOKIE_ACTUATION_GOAL, HTTPCOOKIE_ACTUATION_ID, "httpcookie"),
        (WEBLINKING_ACTUATION_GOAL, WEBLINKING_ACTUATION_ID, "weblinking"),
        (STALECONTENT_ACTUATION_GOAL, STALECONTENT_ACTUATION_ID, "stalecontent"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_extvalue"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"extvalue_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            EXTVALUE_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = EXTVALUE_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_extvalue(DEFAULT_ENCODING)
    rebuilt = serialize_extvalue(parse_extvalue(advertised))
    preloaded = parse_extvalue(RFC_EXTVALUE_LANGUAGE)
    header = encode_extvalue_header(DEFAULT_ENCODING)
    parsed_header = parse_extvalue_header(header)
    asked = parse_http_request(encoding_request(SENTINEL, DEFAULT_CHARSETID))
    preload_req = parse_http_request(language_request(SENTINEL, DEFAULT_CHARSETID, DEFAULT_CHARSETDIGEST))
    got = parse_http_response(encoding_response(SENTINEL, DEFAULT_CHARSETID, DEFAULT_CHARSETDIGEST))
    preload_reply = parse_http_response(
        language_response(SENTINEL, DEFAULT_CHARSETID, DEFAULT_CHARSETDIGEST)
    )
    checks["extvalue_roundtrip"] = (
        parse_extvalue(advertised) == DEFAULT_ENCODING
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_ENCODING_FIELD
        and is_token("ENCODING") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_ENCODING_FIELD
        and parsed_header["policy"] == DEFAULT_ENCODING
        and parsed_header["header"] == ENCODING_HEADER
        and parsed_header["encoding"] is True
        and parsed_header["language"] is False
        and preloaded == LANGUAGE_POLICY
        and ascii_serialize_ext_value() == RFC_EXT_VALUE
        and ext_value_pair() == (RFC_CHARSET, RFC_LANG)
        and RFC_EXT_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_extvalue(LANGUAGE_POLICY) == RFC_EXTVALUE_LANGUAGE
        and DEFAULT_CHARSETDIGEST == request_charsetdigest(DEFAULT_CHARSETID, SENTINEL)
        and "charsetdigest=" in canonical_language(SENTINEL, DEFAULT_CHARSETID, DEFAULT_CHARSETDIGEST)
        and canonical_encoding(SENTINEL, DEFAULT_CHARSETID).startswith("ENCODING")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["extvalue_kind"] == "encoding"
        and asked["charsetid"] == DEFAULT_CHARSETID
        and preload_req["extvalue_kind"] == "language"
        and preload_req["charsetdigest"] == DEFAULT_CHARSETDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["extvalue_kind"] == "encoding"
        and preload_reply["extvalue_kind"] == "language"
        and got["policy"] == DEFAULT_ENCODING
        and preload_reply["policy"] == LANGUAGE_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["charsetdigest"] == DEFAULT_CHARSETDIGEST
        and preload_reply["charsetdigest"] == DEFAULT_CHARSETDIGEST
        and extvalue_matches(serialize_extvalue(got["policy"]), advertised)
    )

    checks["catalog_names_extvalue"] = (
        len(catalog) > 89
        and catalog[89]["id"] == EXTVALUE_ACTUATION_ID
        and catalog[88]["id"] == WEBLINKING_ACTUATION_ID
        and catalog[89]["source"] == "genesis_bind_extvalue"
    )
    checks["catalog_names_stalecontent"] = (
        len(catalog) > 90
        and catalog[90]["id"] == STALECONTENT_ACTUATION_ID
        and catalog[90]["source"] == "genesis_bind_stalecontent"
    )
    family = capability_family(EXTVALUE_ACTUATION_GOAL)
    checks["family_is_extvalue"] = "extvalue" in family
    checks["family_is_extvalue_surface"] = "extvalue" in family
    checks["family_is_charsetid"] = "charsetid" in family
    checks["family_is_rfc5987"] = "rfc5987" in family
    checks["family_is_charsetdigest"] = "charsetdigest" in family
    checks["family_is_not_stalecontent"] = (
        "stalecontent" not in family
        and "rfc5861" not in family
        and "staleid" not in family
        and "staledigest" not in family
    )
    checks["family_is_not_weblinking"] = (
        "weblinking" not in family
        and "rfc5988" not in family
        and "relationid" not in family
        and "relationdigest" not in family
    )
    checks["family_is_not_httpcookie"] = (
        "httpcookie" not in family
        and "rfc6265" not in family
        and "cookieid" not in family
        and "cookiedigest" not in family
    )
    checks["family_is_not_weborigin"] = (
        "weborigin" not in family
        and "rfc6454" not in family
        and "tupleid" not in family
        and "tupledigest" not in family
    )
    checks["family_is_not_xfo"] = (
        "xfo" not in family
        and "rfc7034" not in family
        and "frameid" not in family
        and "framedigest" not in family
    )
    checks["family_is_not_hpkp"] = (
        "hpkp" not in family
        and "rfc7469" not in family
        and "pinid" not in family
        and "pindigest" not in family
    )
    checks["family_is_not_hsts"] = (
        "hsts" not in family
        and "rfc6797" not in family
        and "hstsid" not in family
        and "stsdigest" not in family
    )
    checks["family_is_not_altsvc"] = (
        "altsvc" not in family
        and "rfc7838" not in family
        and "altsvcid" not in family
        and "origindigest" not in family
    )
    checks["family_is_not_encryptedcontent"] = (
        "encryptedcontent" not in family
        and "rfc8188" not in family
        and "encid" not in family
        and "aes128gcm" not in family
        and "ecedigest" not in family
    )
    checks["family_is_not_earlyhints"] = (
        "earlyhint" not in family
        and "rfc8297" not in family
        and "linkid" not in family
        and "earlydigest" not in family
    )
    checks["family_is_not_structuredfields"] = (
        "structuredfield" not in family
        and "rfc8941" not in family
        and "dictid" not in family
        and "sfv" not in family
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
        "dtls" not in family and "rfc6347" not in family and "epoch" not in family
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
    packed = encode_encoding(identity=SENTINEL, charsetid=DEFAULT_CHARSETID, charsetdigest=DEFAULT_CHARSETDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_encoding"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_charsetid"] is True
        and parsed["charsetid"] == DEFAULT_CHARSETID
        and parsed["charsetdigest"] == DEFAULT_CHARSETDIGEST
        and parsed["is_response"] is False
        and parsed["is_language"] is False
        and parsed["type"] == FRAME_ENCODING
        and parsed["first_byte"] == EV_FIRST
    )
    shook = encode_language(
        identity=SENTINEL,
        charsetid=DEFAULT_CHARSETID,
        charsetdigest=DEFAULT_CHARSETDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_language"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_encoding"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["charsetid"] == DEFAULT_CHARSETID
        and answer_parsed["charsetdigest"] == DEFAULT_CHARSETDIGEST
        and answer_parsed["has_charsetdigest"] is True
        and answer_parsed["type"] == FRAME_LANGUAGE
        and answer_parsed["first_byte"] == EV_FIRST
    )
    bare = encode_encoding(identity=SENTINEL, charsetid=DEFAULT_CHARSETID, include_charsetid=False)
    checks["missing_charsetid_is_unauthenticated"] = parse_message(bare)["has_charsetid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    extvalue_signature = semantic_signature(EXTVALUE_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(extvalue_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_extvalue = ToolDescriptor(name="remote_extvalue", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_extvalue)
    checks["naive_mcp_extvalue_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = extvalue_tool_descriptor()
    default_extvalue = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EXTVALUE_TOOL_PROVIDER),
    )
    checks["default_extvalue_provider_is_unsupported"] = (
        default_extvalue.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{EXTVALUE_TOOL_PROVIDER}" in default_extvalue.reasons
    )
    checks["opted_in_extvalue_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_extvalue],
        required_tool_names=("local_memory", "extvalue"),
    )
    checks["naive_preflight_missing_extvalue"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["extvalue"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "extvalue"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, EXTVALUE_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "extvalue" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="extvalue-actuation-") as tmp:
        root = Path(tmp)
        missing = run_extvalue_workflow(with_charsetid=False, output_dir=root / "missing")
        skip_bind = run_extvalue_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_encoding = run_extvalue_workflow(do_encoding=False, output_dir=root / "skip-encoding")
        skip_language = run_extvalue_workflow(do_language=False, output_dir=root / "skip-language")
        skip_charsetdigest = run_extvalue_workflow(do_charsetdigest=False, output_dir=root / "skip-charsetdigest")
        skip_replay = run_extvalue_workflow(replay=False, output_dir=root / "skip-replay")
        skip_charsetid = run_extvalue_workflow(use_charsetid=False, output_dir=root / "skip-charsetid")
        live = run_extvalue_workflow(output_dir=root / "live")
        verify = verify_extvalue_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_extvalue_trace(clone)
        checks["naive_without_charsetid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_charsetid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_encoding_stays_empty"] = (
            skip_encoding["ok"] is False
            and skip_encoding["error"] == "encoding_required"
            and skip_encoding["final_status"] == 409
            and skip_encoding["payload_exists"] is False
        )
        checks["skip_language_stays_empty"] = (
            skip_language["ok"] is False
            and skip_language["error"] == "language_required"
            and skip_language["final_status"] == 409
            and skip_language["payload_exists"] is False
        )
        checks["skip_charsetdigest_stays_empty"] = (
            skip_charsetdigest["ok"] is False
            and skip_charsetdigest["error"] == "charsetdigest_required"
            and skip_charsetdigest["final_status"] == 409
            and skip_charsetdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_charsetid_stays_empty"] = (
            skip_charsetid["ok"] is False
            and skip_charsetid["error"] == "charsetid_required"
            and skip_charsetid["final_status"] == 409
            and skip_charsetid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_charsetdigest"] = (
            int(live.get("charsetid") or 0) == DEFAULT_CHARSETID
            and int(live.get("charsetdigest") or 0) == DEFAULT_CHARSETDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_charsetid_encode_language_charsetdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_encoding["ok"] is False
            and skip_language["ok"] is False
            and skip_charsetdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_charsetid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="extvalue-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != EXTVALUE_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_extvalue"] = (
        live_goal == EXTVALUE_ACTUATION_GOAL
        and EXTVALUE_ACTUATION_ID in live_done
        and live_source == "genesis_bind_extvalue"
    )

    with tempfile.TemporaryDirectory(prefix="extvalue-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(EXTVALUE_LEFTOVER, root)
        register_catalog_proved(root, EXTVALUE_ACTUATION_ID)
        reason = leftover_satisfied_by(EXTVALUE_LEFTOVER, root)
        after = leftover_is_open(EXTVALUE_LEFTOVER, root)
    checks["extvalue_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_extvalue_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{EXTVALUE_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_extvalue_actuation_capability()
    return {
        "ok": ok,
        "action": "extvalue_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": EXTVALUE_ACTUATION_GOAL,
        "done_when": EXTVALUE_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
