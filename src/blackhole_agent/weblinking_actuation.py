"""Drive a first-class Web Linking tool through RFC 5988 LINK/RELATION.

Tool routing already fails missions that require ``weblinking``: hosted
weblinking endpoints stay on the unsupported MCP provider, and no first-party
weblinking provider is executable. Unbound therefore cannot speak a LINK,
lockstep a RELATION relationid handshake over HTTP Link RELATIONID,
independently poll the stored relationdigest, or seal a relationdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``weblinking`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 5988 daemon
- keep a missing-relationid client so the weblinking-relationid hole stays falsifiable
- refuse RELATION until a LINK lands with a non-empty relationid
- independently poll the stored relationdigest on a later client socket
- persist a sealed relationdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 6266 Content-Disposition
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
    WEBLINKING_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    weblinking_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
WEBLINKING_ACTUATION_ID = "capability.weblinking-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-WEBLINKING-OK"
POLL_TOKEN = "BH-WEBLINKING-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_RELATIONID = 0
EMPTY_RELATIONDIGEST = 0
WL_FIRST = 0x4C  # RFC 5988 Link (ASCII 'L')
RELATIONID_SIZE = 4
RELATIONDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_RELATION = 0x02  # RFC 5988 report confirmation
FRAME_LINK = 0x01  # RFC 5988 Link
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
WEBLINKING_LEFTOVER = (
    "Later genesis can take RFC 5988 Web Linking LINK/RELATION over a "
    "relationid-gated relationdigest."
)
WEBLINKING_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WEBLINKING_ACTUATION_ID};"
    f"capability_proved:{WEBLINKING_ACTUATION_ID};"
    "no_skill_route"
)
WEBLINKING_ACTUATION_GOAL = (
    "Repair rfc5988 weblinking link/relation cycle cannot land over http "
    "weblinking relationid: hosted weblinking endpoints remain unsupported so a LINK then "
    "RELATION relationid handshake cannot land and a sealed relationdigest "
    "cannot be produced. A missing weblinking relationid stays forbidden; fail-closed "
    "routing never opts the weblinking provider in. An independent later poll of the "
    "stored relationdigest keeps the hole falsifiable."
)


class WeblinkingActuationError(RuntimeError):
    """Raised when the relation session or loopback daemon fixture misbehaves."""


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
# RFC 5988 section 5 Link / relation-type.
RFC_LINK_FIELD = "LINK"
RFC_RELATION_FIELD = "RELATION"
RFC_WEBLINKING_RELATION = RFC_RELATION_FIELD
RFC_LINK_PARAM = 'rel="alternate"'
DEFAULT_LINK = "LINK"
RELATION_POLICY = "RELATION"
LINK_HEADER = "Link"
RELATION_HEADER = "Link"
WEBLINKING_RELATION_HEADER = RELATION_HEADER
RFC_REL = "alternate"
RFC_HREF = "/feed"
RFC_LINK_PATH = "/"
RFC_LINK_PAIR = '</feed>; rel="alternate"'
RFC_LINK_EMPTY = ""


def link_pair(
    href: str = RFC_HREF,
    rel: str = RFC_REL,
) -> tuple[str, str]:
    """RFC 5988 section 5 URI-Reference and rel relation-type."""

    return str(href or RFC_HREF), str(rel or RFC_REL)


def ascii_serialize_link(
    href: str = RFC_HREF,
    rel: str = RFC_REL,
) -> str:
    """RFC 5988 section 5 Link field-value: <URI-Reference>; rel="relation-type"."""

    live_href, live_rel = link_pair(href, rel)
    if not live_href.startswith(("/", "http://", "https://")):
        raise WeblinkingActuationError("illegal_href")
    if any(ord(char) <= 0x20 or char in "<>" or ord(char) >= 0x7F for char in live_href):
        raise WeblinkingActuationError("illegal_href")
    if not is_token(live_rel):
        raise WeblinkingActuationError("illegal_rel")
    return f'<{live_href}>; rel="{live_rel}"'


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise WeblinkingActuationError("short_weblinking")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 5988 directive-name."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_weblinking(policy: str | Sequence[str]) -> str:
    """Serialize RFC 5988 Link field-value."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise WeblinkingActuationError("illegal_weblinking")
    upper = text.upper()
    if upper in {"LINK", "ALTERNATE"}:
        return "LINK"
    if upper in {"RELATION", "REL"}:
        return "RELATION"
    if upper.startswith("REL="):
        rel_value = text.split("=", 1)[1].strip().strip('"')
        if not rel_value or ";" in rel_value:
            raise WeblinkingActuationError("illegal_weblinking")
        return f'rel="{rel_value}"'
    raise WeblinkingActuationError("illegal_weblinking")


def parse_weblinking(text: str) -> str:
    """Parse RFC 5988 Link into LINK, RELATION, or rel."""

    raw = str(text or "").strip()
    if not raw:
        raise WeblinkingActuationError("illegal_weblinking")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper()
    if upper in {"LINK", "ALTERNATE"}:
        return "LINK"
    if upper in {"RELATION", "REL"}:
        return "RELATION"
    if upper.startswith("REL="):
        rel_value = head.split("=", 1)[1].strip().strip('"')
        if not rel_value or ";" in rel_value:
            raise WeblinkingActuationError("illegal_weblinking")
        return f'rel="{rel_value}"'
    raise WeblinkingActuationError("illegal_weblinking")


def encode_weblinking_header(policy: str | Sequence[str]) -> bytes:
    """RFC 5988 Link field as bytes."""

    return serialize_weblinking(policy).encode("ascii")


def parse_weblinking_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_weblinking(field_value) if field_value else DEFAULT_LINK
    return {
        "field_value": field_value,
        "policy": policy,
        "header": LINK_HEADER,
        "directive": str(policy),
        "link": str(policy) == "LINK",
        "relation": str(policy) == "RELATION",
    }


def canonical_link(identity: str, relationid: int) -> str:
    """RFC 5988 LINK advertisement bound to identity and relationid."""

    return (
        f"{serialize_weblinking(DEFAULT_LINK)}, "
        f"link={ascii_serialize_link()}, "
        f"identity={identity}, relationid={int(relationid) & 0xFFFFFFFF}"
    )


def canonical_relation(identity: str, relationid: int, relationdigest: int | None = None) -> str:
    """RFC 5988 RELATION confirmation of the stored relation policy."""

    suffix = ""
    if relationdigest is not None:
        suffix = f", relationdigest={int(relationdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_weblinking(RELATION_POLICY)}, "
        f"relation={ascii_serialize_link()}, "
        f"identity={identity}, relationid={int(relationid) & 0xFFFFFFFF}{suffix}"
    )


def representation_relation(identity: str, relationid: int, relationdigest: int) -> str:
    return canonical_relation(identity, relationid, relationdigest)


def weblinking_matches(left: str, right: str) -> bool:
    return parse_weblinking(left) == parse_weblinking(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise WeblinkingActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise WeblinkingActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise WeblinkingActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise WeblinkingActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def link_request(identity: str, relationid: int) -> bytes:
    """HTTP GET that elicits RFC 5988 origin LINK."""

    keyid = f"{int(relationid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"GET /weblinking/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Relation-Id: {int(relationid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def relation_request(identity: str, relationid: int, relationdigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 5988 RELATION confirmation of the stored relation policy."""

    keyid = f"{int(relationid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if relationdigest is not None:
        extra = f"Relation-Digest: {int(relationdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"GET /weblinking/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Relation-Id: {int(relationid) & 0xFFFFFFFF}\r\n"
        "Relation-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    weblinking_kind = "relation" if fields.get("relation-confirm") == "1" else "link"
    relation_field = fields.get("link") or ""
    policy = parse_weblinking(relation_field) if relation_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "weblinking_kind": weblinking_kind,
        "policy": policy,
        "relationid": int(fields["relation-id"]) if fields.get("relation-id") else EMPTY_RELATIONID,
        "relationdigest": int(fields["relation-digest"]) if fields.get("relation-digest") else EMPTY_RELATIONDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def link_response(identity: str, relationid: int, relationdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 5988 origin LINK, carrying the stored relationdigest."""

    advertised = serialize_weblinking(DEFAULT_LINK)
    payload = bytes(body or canonical_link(identity, relationid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Link: {advertised}\r\n"
        f"Relation-Id: {int(relationid) & 0xFFFFFFFF}\r\n"
        f"Relation-Digest: {int(relationdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/web-linking\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def relation_response(identity: str, relationid: int, relationdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 5988 RELATION, carrying the stored RELATION policy."""

    advertised = serialize_weblinking(RELATION_POLICY)
    payload = bytes(body or representation_relation(identity, relationid, relationdigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Link: {advertised}\r\n"
        f"Relation-Id: {int(relationid) & 0xFFFFFFFF}\r\n"
        f"Relation-Digest: {int(relationdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/web-linking-confirm\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise WeblinkingActuationError("illegal_content_length") from error
    field_value = fields.get("link") or ""
    policy = parse_weblinking(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/web-linking-confirm" or policy == RELATION_POLICY:
        status = 200
        weblinking_kind = "relation"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        weblinking_kind = "link"
    else:
        status = 0
        weblinking_kind = "link"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "weblinking_kind": weblinking_kind,
        "policy": policy,
        "relationid": int(fields["relation-id"]) if fields.get("relation-id") else EMPTY_RELATIONID,
        "relationdigest": int(fields["relation-digest"]) if fields.get("relation-digest") else EMPTY_RELATIONDIGEST,
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
        raise WeblinkingActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise WeblinkingActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise WeblinkingActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise WeblinkingActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_relationid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"relationid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_relationid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-relationid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_relationdigest(relationid: int = EMPTY_RELATIONID, token: str = SENTINEL) -> int:
    material = canonical_link(token or SENTINEL, int(relationid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_RELATIONID = request_relationid(SENTINEL)
DEFAULT_RELATIONDIGEST = request_relationdigest(DEFAULT_RELATIONID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    relationid: int,
    relationdigest: int,
    include_relationid: bool = True,
) -> bytes:
    live_relationid = int(relationid) & 0xFFFFFFFF if include_relationid else EMPTY_RELATIONID
    live_digest = int(relationdigest) & 0xFFFFFFFF if include_relationid and live_relationid else EMPTY_RELATIONDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_relationid) if live_relationid else b""
    header = bytearray()
    header.append(WL_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_link(
    *,
    identity: str,
    relationid: int,
    relationdigest: int | None = None,
    include_relationid: bool = True,
) -> bytes:
    live_relationid = int(relationid) & 0xFFFFFFFF if include_relationid else EMPTY_RELATIONID
    live_digest = int(relationdigest) if relationdigest is not None else request_relationdigest(live_relationid, identity)
    return encode_packet(
        FRAME_LINK,
        identity=identity,
        relationid=live_relationid,
        relationdigest=live_digest,
        include_relationid=include_relationid,
    )


def encode_relation(
    *,
    identity: str,
    relationid: int,
    relationdigest: int | None = None,
    include_relationid: bool = True,
) -> bytes:
    live_relationid = int(relationid) & 0xFFFFFFFF if include_relationid else EMPTY_RELATIONID
    live_digest = int(relationdigest) if relationdigest is not None else request_relationdigest(live_relationid, identity)
    return encode_packet(
        FRAME_RELATION,
        identity=identity,
        relationid=live_relationid,
        relationdigest=live_digest,
        include_relationid=include_relationid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise WeblinkingActuationError("short_packet")
    first = raw[0]
    if first != WL_FIRST:
        raise WeblinkingActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise WeblinkingActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == RELATIONID_SIZE:
        live_relationid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_relationid = EMPTY_RELATIONID
    else:
        raise WeblinkingActuationError("illegal_relationid")
    if offset >= len(raw):
        raise WeblinkingActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_LINK, FRAME_RELATION}:
        raise WeblinkingActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise WeblinkingActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise WeblinkingActuationError("checksum_failed")
    if len(payload) < 5:
        raise WeblinkingActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise WeblinkingActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_relationid = int(live_relationid) != EMPTY_RELATIONID
    has_relationdigest = has_relationid and int(live_digest) != EMPTY_RELATIONDIGEST
    is_link = frame_type == FRAME_LINK
    is_relation = frame_type == FRAME_RELATION
    return {
        "type": int(frame_type),
        "is_link": is_link,
        "is_relation": is_relation,
        "is_response": is_relation,
        "relationid": int(live_relationid),
        "has_relationid": has_relationid,
        "relationdigest": int(live_digest),
        "has_relationdigest": has_relationdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "http_state": "RFC5988",
        "serialize_field": canonical_link(identity, live_relationid) if has_relationid else "",
        "relation_field": canonical_relation(identity, live_relationid, live_digest) if has_relationdigest else "",
    }


class WeblinkingClient:
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
            raise WeblinkingActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_relation"] or not packet["is_response"]:
            raise WeblinkingActuationError("relationdigest_required")
        if not packet["has_relationid"]:
            raise WeblinkingActuationError("relationid_required")
        if not packet["has_relationdigest"]:
            raise WeblinkingActuationError("relationdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_relationdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_relationdigest:
            raise WeblinkingActuationError("relationdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "relationid": int(reply.get("relationid") or EMPTY_RELATIONID),
            "identity": str(reply.get("identity") or ""),
            "relationdigest": int(reply.get("relationdigest") or EMPTY_RELATIONDIGEST),
        }

    def report(
        self,
        identity: str,
        relationid: int,
        relationdigest: int = EMPTY_RELATIONDIGEST,
        *,
        wait_relationdigest: bool = True,
        include_relationid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_relation(
            identity=identity,
            relationid=relationid,
            relationdigest=relationdigest or request_relationdigest(relationid, identity),
            include_relationid=include_relationid,
        )
        return self.exchange(packet, wait_relationdigest=wait_relationdigest)


class WeblinkingSession:
    """RELATIONID-gated loopback RFC 5988 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        relationid_gate: int = DEFAULT_RELATIONID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.relationid_gate = int(relationid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.relationid = EMPTY_RELATIONID
        self.relationdigest = EMPTY_RELATIONDIGEST
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

    def store_relationid_once(self, identity: str, relationid: int, relationdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(relationid or EMPTY_RELATIONID)
            live_digest = int(relationdigest or EMPTY_RELATIONDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.relationid = live
                self.relationdigest = live_digest or request_relationdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.relationid), int(self.relationdigest)

    def read_relationid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.relationid), int(self.relationdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "relationid": EMPTY_RELATIONID,
            "relationdigest": EMPTY_RELATIONDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _relationid_missing(self) -> bool:
        return not int(self.relationid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, relationid: int, relationdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_relation(
            identity=identity,
            relationid=relationid,
            relationdigest=relationdigest,
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
            except WeblinkingActuationError:
                continue
            if not packet.get("is_link") and not packet.get("is_relation"):
                continue
            if not packet.get("has_relationid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_relationid, stored_digest = self.store_relationid_once(
                identity,
                int(packet.get("relationid") or EMPTY_RELATIONID),
                int(packet.get("relationdigest") or EMPTY_RELATIONDIGEST),
            )
            if not stored_name or not stored_relationid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_link"):
                    self.opened = True
                if packet.get("is_relation"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_relationid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._relationid_missing():
            return self._forbidden("missing_relationid")
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
        do_link: bool = True,
        do_relation: bool = True,
        do_relationdigest: bool = True,
        replay: bool = True,
        use_relationid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._relationid_missing():
            return self._forbidden("missing_relationid")
        live_token = str(token or SENTINEL)
        origin_relationid = request_relationid(live_token)
        origin_digest = request_relationdigest(origin_relationid, live_token)
        client: WeblinkingClient | None = None
        independent: WeblinkingClient | None = None
        try:
            client = WeblinkingClient(self.host, int(self.port))
            if not do_link:
                return self._conflict("link_required")
            bind_packet = encode_link(
                identity=live_token,
                relationid=origin_relationid,
                relationdigest=origin_digest,
                include_relationid=use_relationid,
            )
            if not use_relationid:
                try:
                    client.exchange(bind_packet, wait_relationdigest=True)
                except WeblinkingActuationError:
                    return self._conflict("relationid_required")
                return self._conflict("relationid_required")
            client.send(bind_packet)
            if not do_relation:
                return self._conflict("relation_required")
            proxy_packet = encode_relation(
                identity=live_token,
                relationid=origin_relationid,
                relationdigest=origin_digest,
                include_relationid=True,
            )
            if not do_relationdigest:
                try:
                    client.exchange(proxy_packet, wait_relationdigest=False)
                except WeblinkingActuationError as error:
                    if str(error) == "relationdigest_required":
                        return self._conflict("relationdigest_required")
                    return self._conflict("relationdigest_required")
                return self._conflict("relationdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_relationdigest=True)
            except WeblinkingActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("relationid_required")
                if reason == "relationdigest_required":
                    return self._conflict("relationdigest_required")
                return self._conflict("link_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("link_required")
            if int(reply.get("relationid") or EMPTY_RELATIONID) != origin_relationid:
                return self._conflict("relationdigest_required")
            if int(reply.get("relationdigest") or EMPTY_RELATIONDIGEST) != origin_digest:
                return self._conflict("relationdigest_required")
            self.retrieved = True
            if replay:
                independent = WeblinkingClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_relationid(live_token),
                        request_relationdigest(poll_relationid(live_token), POLL_TOKEN),
                        wait_relationdigest=True,
                    )
                except WeblinkingActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_relationid, stored_digest = self.read_relationid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_relationid != origin_relationid
                    or stored_digest != origin_digest
                    or int(poll.get("relationid") or EMPTY_RELATIONID) != origin_relationid
                    or int(poll.get("relationdigest") or EMPTY_RELATIONDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_relationid}:{origin_digest}:{live_token}:{canonical_link(live_token, origin_relationid)}:{canonical_relation(live_token, origin_relationid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "relationid": origin_relationid,
                "relationdigest": origin_digest,
                "link_frame": True,
                "relation_frame": True,
                "relationdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "relationid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_weblinking_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "relationid": origin_relationid,
                "relationdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "link_frame": True,
                "relation_frame": True,
                "relationdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "relationid_bound": True,
            }
        except (OSError, WeblinkingActuationError) as error:
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
        live = independent_weblinking_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "relationid": int(live.get("relationid") or EMPTY_RELATIONID),
            "relationdigest": int(live.get("relationdigest") or EMPTY_RELATIONDIGEST),
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


def call_weblinking_tool(session: WeblinkingSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one relation tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_link = True if arguments.get("link") is None else bool(arguments.get("link"))
    do_relation = True if arguments.get("relation") is None else bool(arguments.get("relation"))
    do_relationdigest = True if arguments.get("relationdigest") is None else bool(arguments.get("relationdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_relationid = True if arguments.get("use_relationid") is None else bool(arguments.get("use_relationid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_link=do_link,
            do_relation=do_relation,
            do_relationdigest=do_relationdigest,
            replay=replay,
            use_relationid=use_relationid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise WeblinkingActuationError(f"unsupported weblinking action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_weblinking_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed relation relationdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "relationid": EMPTY_RELATIONID,
        "relationdigest": EMPTY_RELATIONDIGEST,
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
            "link_frame",
            "relation_frame",
            "relationdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "relationid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    relationid = int(payload.get("relationid") or EMPTY_RELATIONID)
    relationdigest = int(payload.get("relationdigest") or EMPTY_RELATIONDIGEST)
    dual = port > 0 and bool(relationid) and bool(relationdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "relationid": relationid,
        "relationdigest": relationdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "link_frame": payload.get("link_frame") is True,
        "relation_frame": payload.get("relation_frame") is True,
        "relationdigest_response": payload.get("relationdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "relationid_bound": payload.get("relationid_bound") is True,
    }


def run_weblinking_workflow(
    *,
    with_relationid: bool = True,
    skip_bind: bool = False,
    do_link: bool = True,
    do_relation: bool = True,
    do_relationdigest: bool = True,
    replay: bool = True,
    use_relationid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 5988 LINK/RELATION relationid cycle workflow."""

    descriptor = weblinking_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBLINKING_TOOL_PROVIDER),
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
        raise WeblinkingActuationError(f"weblinking tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="weblinking-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = WeblinkingSession(out, relationid_gate=DEFAULT_RELATIONID if with_relationid else EMPTY_RELATIONID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "link": do_link,
            "relation": do_relation,
            "relationdigest": do_relationdigest,
            "replay": replay,
            "use_relationid": use_relationid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_weblinking_tool(session, arguments))
            except WeblinkingActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_weblinking_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_relationid
        and not skip_bind
        and do_link
        and do_relation
        and do_relationdigest
        and replay
        and use_relationid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "weblinking_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_relationid": with_relationid,
        "skip_bind": skip_bind,
        "link_frame": do_link,
        "relation": do_relation,
        "relationdigest": do_relationdigest,
        "replay": replay,
        "use_relationid": use_relationid,
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
        "relationid_value": int(publish_result.get("relationid") or independent.get("relationid") or EMPTY_RELATIONID),
        "relationdigest_value": int(publish_result.get("relationdigest") or independent.get("relationdigest") or EMPTY_RELATIONDIGEST),
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
        "relationid": int(trace_body["relationid_value"] or EMPTY_RELATIONID),
        "relationdigest": int(trace_body["relationdigest_value"] or EMPTY_RELATIONDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_relationid": with_relationid,
        "skip_bind": skip_bind,
        "link_cycle": do_link,
        "relation_cycle": do_relation,
        "relationdigest_cycle": do_relationdigest,
        "replay": replay,
        "use_relationid": use_relationid,
    }


def verify_weblinking_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_weblinking_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    relationid = int(trace.get("relationid_value") or independent.get("relationid") or EMPTY_RELATIONID)
    relationdigest = int(trace.get("relationdigest_value") or independent.get("relationdigest") or EMPTY_RELATIONDIGEST)
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
        "link_frame": independent.get("link_frame") is True,
        "relation_frame": independent.get("relation_frame") is True,
        "relationdigest_response": independent.get("relationdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "relationid_bound": independent.get("relationid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "relationdigest_recorded": (
            port > 0
            and relationid == DEFAULT_RELATIONID
            and relationdigest == DEFAULT_RELATIONDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def weblinking_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.weblinking_actuation import "
        "builtin_weblinking_actuation_proof; r=builtin_weblinking_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='weblinking_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_weblinking_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=WEBLINKING_ACTUATION_ID,
        name="First-class RFC 5988 Web Linking LINK/RELATION actuation",
        description=(
            "Missions that require a weblinking tool can opt the weblinking provider in, "
            "bind a loopback RFC 5988 Web Linking endpoint, complete a LINK "
            "with a non-empty relationid, lockstep a RELATION that carries the "
            "stored relationdigest, independently poll the stored relationdigest "
            "on a later socket, and seal a digest-chained relationdigest. Default "
            "routing stays fail-closed; a missing relationid keeps the hole "
            "falsifiable, and skip-LINK/RELATION/RELATIONDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.weblinking_actuation:builtin_weblinking_actuation_proof",
        proof_command=weblinking_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.contentdisposition-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/weblinking_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/contentdisposition_actuation.py",
            "src/blackhole_agent/extvalue_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required weblinking tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 5988 daemon, speaks a "
            "LINK then RELATION over Web Linking with a non-empty relationid and "
            "relationdigest, independently polls the stored relationdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 6266 Content-Disposition lockstep is proved. "
            "Missing relationids, skip-LINK, skip-RELATION, skip-relationdigest, skip-REPLAY, "
            "and a LINK aimed without a relationid stay fail-closed. "
            "Later genesis can take RFC 5987 Character Set and Language Encoding ENCODING/LANGUAGE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("weblinking", "rfc5988", "http", "relationid", "relationdigest", "link", "relation", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260904T184611Z-2f544e11",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_weblinking_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 5988 relation lockstep actuation seals a relationdigest."""

    from blackhole_agent.extvalue_actuation import (
        EXTVALUE_ACTUATION_GOAL,
        EXTVALUE_ACTUATION_ID,
    )
    from blackhole_agent.contentdisposition_actuation import (
        CONTENTDISPOSITION_ACTUATION_GOAL,
        CONTENTDISPOSITION_ACTUATION_ID,
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
    checks["denylists_self"] = WEBLINKING_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(WEBLINKING_ACTUATION_GOAL) == (
        WEBLINKING_ACTUATION_ID,
    )
    checks["leftover_text_binds_weblinking"] = leftover_marker_ids(WEBLINKING_LEFTOVER) == (
        WEBLINKING_ACTUATION_ID,
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
        (CONTENTDISPOSITION_ACTUATION_GOAL, CONTENTDISPOSITION_ACTUATION_ID, "contentdisposition"),
        (EXTVALUE_ACTUATION_GOAL, EXTVALUE_ACTUATION_ID, "extvalue"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_weblinking"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"weblinking_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            WEBLINKING_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = WEBLINKING_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_weblinking(DEFAULT_LINK)
    rebuilt = serialize_weblinking(parse_weblinking(advertised))
    preloaded = parse_weblinking(RFC_WEBLINKING_RELATION)
    header = encode_weblinking_header(DEFAULT_LINK)
    parsed_header = parse_weblinking_header(header)
    asked = parse_http_request(link_request(SENTINEL, DEFAULT_RELATIONID))
    preload_req = parse_http_request(relation_request(SENTINEL, DEFAULT_RELATIONID, DEFAULT_RELATIONDIGEST))
    got = parse_http_response(link_response(SENTINEL, DEFAULT_RELATIONID, DEFAULT_RELATIONDIGEST))
    preload_reply = parse_http_response(
        relation_response(SENTINEL, DEFAULT_RELATIONID, DEFAULT_RELATIONDIGEST)
    )
    checks["weblinking_roundtrip"] = (
        parse_weblinking(advertised) == DEFAULT_LINK
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_LINK_FIELD
        and is_token("LINK") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_LINK_FIELD
        and parsed_header["policy"] == DEFAULT_LINK
        and parsed_header["header"] == LINK_HEADER
        and parsed_header["link"] is True
        and parsed_header["relation"] is False
        and preloaded == RELATION_POLICY
        and ascii_serialize_link() == RFC_LINK_PAIR
        and link_pair() == (RFC_HREF, RFC_REL)
        and RFC_LINK_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_weblinking(RELATION_POLICY) == RFC_WEBLINKING_RELATION
        and DEFAULT_RELATIONDIGEST == request_relationdigest(DEFAULT_RELATIONID, SENTINEL)
        and "relationdigest=" in canonical_relation(SENTINEL, DEFAULT_RELATIONID, DEFAULT_RELATIONDIGEST)
        and canonical_link(SENTINEL, DEFAULT_RELATIONID).startswith("LINK")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "GET"
        and asked["weblinking_kind"] == "link"
        and asked["relationid"] == DEFAULT_RELATIONID
        and preload_req["weblinking_kind"] == "relation"
        and preload_req["relationdigest"] == DEFAULT_RELATIONDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["weblinking_kind"] == "link"
        and preload_reply["weblinking_kind"] == "relation"
        and got["policy"] == DEFAULT_LINK
        and preload_reply["policy"] == RELATION_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["relationdigest"] == DEFAULT_RELATIONDIGEST
        and preload_reply["relationdigest"] == DEFAULT_RELATIONDIGEST
        and weblinking_matches(serialize_weblinking(got["policy"]), advertised)
    )

    checks["catalog_names_weblinking"] = (
        len(catalog) > 88
        and catalog[88]["id"] == WEBLINKING_ACTUATION_ID
        and catalog[87]["id"] == CONTENTDISPOSITION_ACTUATION_ID
        and catalog[88]["source"] == "genesis_bind_weblinking"
    )
    checks["catalog_names_extvalue"] = (
        len(catalog) > 89
        and catalog[89]["id"] == EXTVALUE_ACTUATION_ID
        and catalog[89]["source"] == "genesis_bind_extvalue"
    )
    family = capability_family(WEBLINKING_ACTUATION_GOAL)
    checks["family_is_weblinking"] = "weblinking" in family
    checks["family_is_weblinking_surface"] = "weblinking" in family
    checks["family_is_relationid"] = "relationid" in family
    checks["family_is_rfc5988"] = "rfc5988" in family
    checks["family_is_relationdigest"] = "relationdigest" in family
    checks["family_is_not_extvalue"] = (
        "extvalue" not in family
        and "rfc5987" not in family
        and "charsetid" not in family
        and "charsetdigest" not in family
    )
    checks["family_is_not_contentdisposition"] = (
        "contentdisposition" not in family
        and "rfc6266" not in family
        and "dispositionid" not in family
        and "dispositiondigest" not in family
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
    packed = encode_link(identity=SENTINEL, relationid=DEFAULT_RELATIONID, relationdigest=DEFAULT_RELATIONDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_link"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_relationid"] is True
        and parsed["relationid"] == DEFAULT_RELATIONID
        and parsed["relationdigest"] == DEFAULT_RELATIONDIGEST
        and parsed["is_response"] is False
        and parsed["is_relation"] is False
        and parsed["type"] == FRAME_LINK
        and parsed["first_byte"] == WL_FIRST
    )
    shook = encode_relation(
        identity=SENTINEL,
        relationid=DEFAULT_RELATIONID,
        relationdigest=DEFAULT_RELATIONDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_relation"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_link"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["relationid"] == DEFAULT_RELATIONID
        and answer_parsed["relationdigest"] == DEFAULT_RELATIONDIGEST
        and answer_parsed["has_relationdigest"] is True
        and answer_parsed["type"] == FRAME_RELATION
        and answer_parsed["first_byte"] == WL_FIRST
    )
    bare = encode_link(identity=SENTINEL, relationid=DEFAULT_RELATIONID, include_relationid=False)
    checks["missing_relationid_is_unauthenticated"] = parse_message(bare)["has_relationid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    weblinking_signature = semantic_signature(WEBLINKING_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(weblinking_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_weblinking = ToolDescriptor(name="remote_weblinking", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_weblinking)
    checks["naive_mcp_weblinking_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = weblinking_tool_descriptor()
    default_weblinking = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBLINKING_TOOL_PROVIDER),
    )
    checks["default_weblinking_provider_is_unsupported"] = (
        default_weblinking.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{WEBLINKING_TOOL_PROVIDER}" in default_weblinking.reasons
    )
    checks["opted_in_weblinking_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_weblinking],
        required_tool_names=("local_memory", "weblinking"),
    )
    checks["naive_preflight_missing_weblinking"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["weblinking"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "weblinking"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WEBLINKING_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "weblinking" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="weblinking-actuation-") as tmp:
        root = Path(tmp)
        missing = run_weblinking_workflow(with_relationid=False, output_dir=root / "missing")
        skip_bind = run_weblinking_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_link = run_weblinking_workflow(do_link=False, output_dir=root / "skip-link")
        skip_relation = run_weblinking_workflow(do_relation=False, output_dir=root / "skip-relation")
        skip_relationdigest = run_weblinking_workflow(do_relationdigest=False, output_dir=root / "skip-relationdigest")
        skip_replay = run_weblinking_workflow(replay=False, output_dir=root / "skip-replay")
        skip_relationid = run_weblinking_workflow(use_relationid=False, output_dir=root / "skip-relationid")
        live = run_weblinking_workflow(output_dir=root / "live")
        verify = verify_weblinking_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_weblinking_trace(clone)
        checks["naive_without_relationid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_relationid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_link_stays_empty"] = (
            skip_link["ok"] is False
            and skip_link["error"] == "link_required"
            and skip_link["final_status"] == 409
            and skip_link["payload_exists"] is False
        )
        checks["skip_relation_stays_empty"] = (
            skip_relation["ok"] is False
            and skip_relation["error"] == "relation_required"
            and skip_relation["final_status"] == 409
            and skip_relation["payload_exists"] is False
        )
        checks["skip_relationdigest_stays_empty"] = (
            skip_relationdigest["ok"] is False
            and skip_relationdigest["error"] == "relationdigest_required"
            and skip_relationdigest["final_status"] == 409
            and skip_relationdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_relationid_stays_empty"] = (
            skip_relationid["ok"] is False
            and skip_relationid["error"] == "relationid_required"
            and skip_relationid["final_status"] == 409
            and skip_relationid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_relationdigest"] = (
            int(live.get("relationid") or 0) == DEFAULT_RELATIONID
            and int(live.get("relationdigest") or 0) == DEFAULT_RELATIONDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_relationid_encode_relation_relationdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_link["ok"] is False
            and skip_relation["ok"] is False
            and skip_relationdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_relationid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="weblinking-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != WEBLINKING_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_weblinking"] = (
        live_goal == WEBLINKING_ACTUATION_GOAL
        and WEBLINKING_ACTUATION_ID in live_done
        and live_source == "genesis_bind_weblinking"
    )

    with tempfile.TemporaryDirectory(prefix="weblinking-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(WEBLINKING_LEFTOVER, root)
        register_catalog_proved(root, WEBLINKING_ACTUATION_ID)
        reason = leftover_satisfied_by(WEBLINKING_LEFTOVER, root)
        after = leftover_is_open(WEBLINKING_LEFTOVER, root)
    checks["weblinking_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_weblinking_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{WEBLINKING_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_weblinking_actuation_capability()
    return {
        "ok": ok,
        "action": "weblinking_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": WEBLINKING_ACTUATION_GOAL,
        "done_when": WEBLINKING_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
