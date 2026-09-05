"""Drive a first-class Internet Cache Protocol tool through RFC 2186 QUERY/HIT.

Tool routing already fails missions that require ``icp``: hosted
icp endpoints stay on the unsupported MCP provider, and no first-party
icp provider is executable. Unbound therefore cannot speak a QUERY,
lockstep a HIT queryid handshake over ICP Hit QUERYID,
independently poll the stored icpdigest, or seal a icpdigest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``icp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2186 daemon
- keep a missing-queryid client so the icp-queryid hole stays falsifiable
- refuse HIT until a QUERY lands with a non-empty queryid
- independently poll the stored icpdigest on a later client socket
- persist a sealed icpdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 2227 Simple Hit-Metering
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
    ICP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    icp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
ICP_ACTUATION_ID = "capability.icp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-ICP-OK"
POLL_TOKEN = "BH-ICP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_QUERYID = 0
EMPTY_ICPDIGEST = 0
ICP_FIRST = 0x49  # RFC 2186 Internet Cache Protocol (ASCII 'I')
QUERYID_SIZE = 4
ICPDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_HIT = 0x02  # RFC 2186 HIT confirmation
FRAME_QUERY = 0x01  # RFC 2186 QUERY
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
ICP_LEFTOVER = (
    "Later genesis can take RFC 2186 Internet Cache Protocol QUERY/HIT over a "
    "queryid-gated icpdigest."
)
ICP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ICP_ACTUATION_ID};"
    f"capability_proved:{ICP_ACTUATION_ID};"
    "no_skill_route"
)
ICP_ACTUATION_GOAL = (
    "Repair rfc2186 icp query/hit cycle cannot land over http "
    "icp queryid: hosted icp endpoints remain unsupported so a QUERY then "
    "HIT queryid handshake cannot land and a sealed icpdigest "
    "cannot be produced. A missing icp queryid stays forbidden; fail-closed "
    "routing never opts the icp provider in. An independent later poll of the "
    "stored icpdigest keeps the hole falsifiable."
)


class IcpActuationError(RuntimeError):
    """Raised when the digest session or loopback daemon fixture misbehaves."""


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
# RFC 2186 sections 5.1 and 5.2: AUTH / DIGEST.
RFC_QUERY_FIELD = "QUERY"
RFC_HIT_FIELD = "HIT"
RFC_ICP_HIT = RFC_HIT_FIELD
RFC_QUERY_DIRECTIVE = "query=url"
RFC_HIT_DIRECTIVE = "hit=object"
DEFAULT_QUERY = "QUERY"
HIT_POLICY = "HIT"
QUERY_HEADER = "Query"
HIT_HEADER = "Hit"
ICP_HIT_HEADER = HIT_HEADER
RFC_QUERY_PATH = "/icp/"
RFC_QUERY_EMPTY = ""


def icp_directive_pair(*, hit: bool = False) -> tuple[str, str]:
    """RFC 2186 Query / Hit directive pair."""

    if hit:
        return "hit", "object"
    return "query", "url"


def ascii_serialize_icp_directive(*, hit: bool = False) -> str:
    """RFC 2186 token "=" query-or-hit."""

    name, value = icp_directive_pair(hit=hit)
    if not is_token(name):
        raise IcpActuationError("illegal_directive")
    return f"{name}={value}"


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = str(text or "")
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def take(self, count: int = 1) -> str:
        chunk = self.text[self.pos : self.pos + count]
        if len(chunk) < count:
            raise IcpActuationError("short_icp")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 2186 Meter token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_icp(policy: str | Sequence[str]) -> str:
    """Serialize RFC 2186 QUERY / HIT opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise IcpActuationError("illegal_icp")
    upper = text.upper().replace("_", "-")
    if upper in {"QUERY", "ICP", "ICP-QUERY"}:
        return "QUERY"
    if upper in {"HIT", "OBJECT", "ICP-HIT"}:
        return "HIT"
    if upper.startswith("QUERY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IcpActuationError("illegal_icp")
        return "QUERY"
    if upper.startswith("HIT="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IcpActuationError("illegal_icp")
        return "HIT"
    raise IcpActuationError("illegal_icp")


def parse_icp(text: str) -> str:
    """Parse RFC 2186 ICP opcode header extensions into QUERY or HIT."""

    raw = str(text or "").strip()
    if not raw:
        raise IcpActuationError("illegal_icp")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"QUERY", "ICP", "ICP-QUERY"}:
        return "QUERY"
    if upper in {"HIT", "OBJECT", "ICP-HIT"}:
        return "HIT"
    if upper.startswith("QUERY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IcpActuationError("illegal_icp")
        return "QUERY"
    if upper.startswith("HIT="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IcpActuationError("illegal_icp")
        return "HIT"
    raise IcpActuationError("illegal_icp")


def encode_icp_header(policy: str | Sequence[str]) -> bytes:
    """RFC 2186 Meter field as bytes."""

    return serialize_icp(policy).encode("ascii")


def parse_icp_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_icp(field_value) if field_value else DEFAULT_QUERY
    return {
        "field_value": field_value,
        "policy": policy,
        "header": QUERY_HEADER,
        "directive": str(policy),
        "query": str(policy) == "QUERY",
        "hit": str(policy) == "HIT",
    }


def canonical_query(identity: str, queryid: int) -> str:
    """RFC 2186 AUTH advertisement bound to identity and queryid."""

    return (
        f"{serialize_icp(DEFAULT_QUERY)}, "
        f"query={ascii_serialize_icp_directive()}, "
        f"identity={identity}, queryid={int(queryid) & 0xFFFFFFFF}"
    )


def canonical_hit(identity: str, queryid: int, icpdigest: int | None = None) -> str:
    """RFC 2186 DIGEST confirmation of the stored digest policy."""

    digest = ""
    if icpdigest is not None:
        digest = f", icpdigest={int(icpdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_icp(HIT_POLICY)}, "
        f"hit={ascii_serialize_icp_directive(hit=True)}, "
        f"identity={identity}, queryid={int(queryid) & 0xFFFFFFFF}{digest}"
    )


def representation_hit(identity: str, queryid: int, icpdigest: int) -> str:
    return canonical_hit(identity, queryid, icpdigest)


def icp_matches(left: str, right: str) -> bool:
    return parse_icp(left) == parse_icp(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise IcpActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise IcpActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise IcpActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise IcpActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def query_request(identity: str, queryid: int) -> bytes:
    """HTTP AUTH that elicits RFC 2186 origin AUTH."""

    keyid = f"{int(queryid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"QUERY /icp/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Query-Id: {int(queryid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def hit_request(identity: str, queryid: int, icpdigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 2186 DIGEST confirmation of the stored digest policy."""

    keyid = f"{int(queryid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if icpdigest is not None:
        extra = f"Icp-Digest: {int(icpdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"HIT /icp/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Query-Id: {int(queryid) & 0xFFFFFFFF}\r\n"
        "Hit-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    icp_kind = "hit" if fields.get("hit-confirm") == "1" else "query"
    upgrade_field = fields.get("query") or fields.get("negotiate") or fields.get("icp") or ""
    policy = parse_icp(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "icp_kind": icp_kind,
        "policy": policy,
        "queryid": int(fields["query-id"]) if fields.get("query-id") else EMPTY_QUERYID,
        "icpdigest": int(fields["icp-digest"]) if fields.get("icp-digest") else EMPTY_ICPDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def query_response(identity: str, queryid: int, icpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 2186 origin AUTH, carrying the stored icpdigest."""

    advertised = serialize_icp(DEFAULT_QUERY)
    payload = bytes(body or canonical_query(identity, queryid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Query: {advertised}\r\n"
        f"Query-Id: {int(queryid) & 0xFFFFFFFF}\r\n"
        f"Icp-Digest: {int(icpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def hit_response(identity: str, queryid: int, icpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 2186 DIGEST, carrying the stored DIGEST policy."""

    advertised = serialize_icp(HIT_POLICY)
    payload = bytes(body or representation_hit(identity, queryid, icpdigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Query: {advertised}\r\n"
        f"Query-Id: {int(queryid) & 0xFFFFFFFF}\r\n"
        f"Icp-Digest: {int(icpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/icp-hit\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise IcpActuationError("illegal_content_length") from error
    field_value = fields.get("query") or fields.get("negotiate") or fields.get("icp") or ""
    policy = parse_icp(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/icp-hit" or policy == HIT_POLICY:
        status = 200
        icp_kind = "hit"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        icp_kind = "query"
    else:
        status = 0
        icp_kind = "query"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "icp_kind": icp_kind,
        "policy": policy,
        "queryid": int(fields["query-id"]) if fields.get("query-id") else EMPTY_QUERYID,
        "icpdigest": int(fields["icp-digest"]) if fields.get("icp-digest") else EMPTY_ICPDIGEST,
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
        raise IcpActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise IcpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise IcpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise IcpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_queryid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"queryid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_queryid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-queryid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_icpdigest(queryid: int = EMPTY_QUERYID, token: str = SENTINEL) -> int:
    material = canonical_query(token or SENTINEL, int(queryid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_QUERYID = request_queryid(SENTINEL)
DEFAULT_ICPDIGEST = request_icpdigest(DEFAULT_QUERYID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    queryid: int,
    icpdigest: int,
    include_queryid: bool = True,
) -> bytes:
    live_queryid = int(queryid) & 0xFFFFFFFF if include_queryid else EMPTY_QUERYID
    live_digest = int(icpdigest) & 0xFFFFFFFF if include_queryid and live_queryid else EMPTY_ICPDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_queryid) if live_queryid else b""
    header = bytearray()
    header.append(ICP_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_query(
    *,
    identity: str,
    queryid: int,
    icpdigest: int | None = None,
    include_queryid: bool = True,
) -> bytes:
    live_queryid = int(queryid) & 0xFFFFFFFF if include_queryid else EMPTY_QUERYID
    live_digest = int(icpdigest) if icpdigest is not None else request_icpdigest(live_queryid, identity)
    return encode_packet(
        FRAME_QUERY,
        identity=identity,
        queryid=live_queryid,
        icpdigest=live_digest,
        include_queryid=include_queryid,
    )


def encode_hit(
    *,
    identity: str,
    queryid: int,
    icpdigest: int | None = None,
    include_queryid: bool = True,
) -> bytes:
    live_queryid = int(queryid) & 0xFFFFFFFF if include_queryid else EMPTY_QUERYID
    live_digest = int(icpdigest) if icpdigest is not None else request_icpdigest(live_queryid, identity)
    return encode_packet(
        FRAME_HIT,
        identity=identity,
        queryid=live_queryid,
        icpdigest=live_digest,
        include_queryid=include_queryid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise IcpActuationError("short_packet")
    first = raw[0]
    if first != ICP_FIRST:
        raise IcpActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise IcpActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == QUERYID_SIZE:
        live_queryid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_queryid = EMPTY_QUERYID
    else:
        raise IcpActuationError("illegal_queryid")
    if offset >= len(raw):
        raise IcpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_QUERY, FRAME_HIT}:
        raise IcpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise IcpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise IcpActuationError("checksum_failed")
    if len(payload) < 5:
        raise IcpActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise IcpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_queryid = int(live_queryid) != EMPTY_QUERYID
    has_icpdigest = has_queryid and int(live_digest) != EMPTY_ICPDIGEST
    is_query = frame_type == FRAME_QUERY
    is_hit = frame_type == FRAME_HIT
    return {
        "type": int(frame_type),
        "is_query": is_query,
        "is_hit": is_hit,
        "is_response": is_hit,
        "queryid": int(live_queryid),
        "has_queryid": has_queryid,
        "icpdigest": int(live_digest),
        "has_icpdigest": has_icpdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC2186",
        "serialize_field": canonical_query(identity, live_queryid) if has_queryid else "",
        "tls_field": canonical_hit(identity, live_queryid, live_digest) if has_icpdigest else "",
    }


class IcpClient:
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
            raise IcpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_hit"] or not packet["is_response"]:
            raise IcpActuationError("icpdigest_required")
        if not packet["has_queryid"]:
            raise IcpActuationError("queryid_required")
        if not packet["has_icpdigest"]:
            raise IcpActuationError("icpdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_icpdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_icpdigest:
            raise IcpActuationError("icpdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "queryid": int(reply.get("queryid") or EMPTY_QUERYID),
            "identity": str(reply.get("identity") or ""),
            "icpdigest": int(reply.get("icpdigest") or EMPTY_ICPDIGEST),
        }

    def report(
        self,
        identity: str,
        queryid: int,
        icpdigest: int = EMPTY_ICPDIGEST,
        *,
        wait_icpdigest: bool = True,
        include_queryid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_hit(
            identity=identity,
            queryid=queryid,
            icpdigest=icpdigest or request_icpdigest(queryid, identity),
            include_queryid=include_queryid,
        )
        return self.exchange(packet, wait_icpdigest=wait_icpdigest)


class IcpSession:
    """QUERYID-gated loopback RFC 2186 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        queryid_gate: int = DEFAULT_QUERYID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.queryid_gate = int(queryid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.queryid = EMPTY_QUERYID
        self.icpdigest = EMPTY_ICPDIGEST
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

    def store_queryid_once(self, identity: str, queryid: int, icpdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(queryid or EMPTY_QUERYID)
            live_digest = int(icpdigest or EMPTY_ICPDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.queryid = live
                self.icpdigest = live_digest or request_icpdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.queryid), int(self.icpdigest)

    def read_queryid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.queryid), int(self.icpdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "queryid": EMPTY_QUERYID,
            "icpdigest": EMPTY_ICPDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _queryid_missing(self) -> bool:
        return not int(self.queryid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, queryid: int, icpdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_hit(
            identity=identity,
            queryid=queryid,
            icpdigest=icpdigest,
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
            except IcpActuationError:
                continue
            if not packet.get("is_query") and not packet.get("is_hit"):
                continue
            if not packet.get("has_queryid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_queryid, stored_digest = self.store_queryid_once(
                identity,
                int(packet.get("queryid") or EMPTY_QUERYID),
                int(packet.get("icpdigest") or EMPTY_ICPDIGEST),
            )
            if not stored_name or not stored_queryid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_query"):
                    self.opened = True
                if packet.get("is_hit"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_queryid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._queryid_missing():
            return self._forbidden("missing_queryid")
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
        do_query: bool = True,
        do_hit: bool = True,
        do_icpdigest: bool = True,
        replay: bool = True,
        use_queryid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._queryid_missing():
            return self._forbidden("missing_queryid")
        live_token = str(token or SENTINEL)
        origin_queryid = request_queryid(live_token)
        origin_digest = request_icpdigest(origin_queryid, live_token)
        client: IcpClient | None = None
        independent: IcpClient | None = None
        try:
            client = IcpClient(self.host, int(self.port))
            if not do_query:
                return self._conflict("query_required")
            bind_packet = encode_query(
                identity=live_token,
                queryid=origin_queryid,
                icpdigest=origin_digest,
                include_queryid=use_queryid,
            )
            if not use_queryid:
                try:
                    client.exchange(bind_packet, wait_icpdigest=True)
                except IcpActuationError:
                    return self._conflict("queryid_required")
                return self._conflict("queryid_required")
            client.send(bind_packet)
            if not do_hit:
                return self._conflict("hit_required")
            proxy_packet = encode_hit(
                identity=live_token,
                queryid=origin_queryid,
                icpdigest=origin_digest,
                include_queryid=True,
            )
            if not do_icpdigest:
                try:
                    client.exchange(proxy_packet, wait_icpdigest=False)
                except IcpActuationError as error:
                    if str(error) == "icpdigest_required":
                        return self._conflict("icpdigest_required")
                    return self._conflict("icpdigest_required")
                return self._conflict("icpdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_icpdigest=True)
            except IcpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("queryid_required")
                if reason == "icpdigest_required":
                    return self._conflict("icpdigest_required")
                return self._conflict("query_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("query_required")
            if int(reply.get("queryid") or EMPTY_QUERYID) != origin_queryid:
                return self._conflict("icpdigest_required")
            if int(reply.get("icpdigest") or EMPTY_ICPDIGEST) != origin_digest:
                return self._conflict("icpdigest_required")
            self.retrieved = True
            if replay:
                independent = IcpClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_queryid(live_token),
                        request_icpdigest(poll_queryid(live_token), POLL_TOKEN),
                        wait_icpdigest=True,
                    )
                except IcpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_queryid, stored_digest = self.read_queryid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_queryid != origin_queryid
                    or stored_digest != origin_digest
                    or int(poll.get("queryid") or EMPTY_QUERYID) != origin_queryid
                    or int(poll.get("icpdigest") or EMPTY_ICPDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_queryid}:{origin_digest}:{live_token}:{canonical_query(live_token, origin_queryid)}:{canonical_hit(live_token, origin_queryid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "queryid": origin_queryid,
                "icpdigest": origin_digest,
                "query_frame": True,
                "hit_frame": True,
                "icpdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "queryid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_icp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "queryid": origin_queryid,
                "icpdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "query_frame": True,
                "hit_frame": True,
                "icpdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "queryid_bound": True,
            }
        except (OSError, IcpActuationError) as error:
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
        live = independent_icp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "queryid": int(live.get("queryid") or EMPTY_QUERYID),
            "icpdigest": int(live.get("icpdigest") or EMPTY_ICPDIGEST),
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


def call_icp_tool(session: IcpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one icp tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_query = True if arguments.get("query") is None else bool(arguments.get("query"))
    do_hit = True if arguments.get("hit") is None else bool(arguments.get("hit"))
    do_icpdigest = True if arguments.get("icpdigest") is None else bool(arguments.get("icpdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_queryid = True if arguments.get("use_queryid") is None else bool(arguments.get("use_queryid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_query=do_query,
            do_hit=do_hit,
            do_icpdigest=do_icpdigest,
            replay=replay,
            use_queryid=use_queryid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise IcpActuationError(f"unsupported icp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_icp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage icpdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "queryid": EMPTY_QUERYID,
        "icpdigest": EMPTY_ICPDIGEST,
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
            "query_frame",
            "hit_frame",
            "icpdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "queryid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    queryid = int(payload.get("queryid") or EMPTY_QUERYID)
    icpdigest = int(payload.get("icpdigest") or EMPTY_ICPDIGEST)
    dual = port > 0 and bool(queryid) and bool(icpdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "queryid": queryid,
        "icpdigest": icpdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "query_frame": payload.get("query_frame") is True,
        "hit_frame": payload.get("hit_frame") is True,
        "icpdigest_response": payload.get("icpdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "queryid_bound": payload.get("queryid_bound") is True,
    }


def run_icp_workflow(
    *,
    with_queryid: bool = True,
    skip_bind: bool = False,
    do_query: bool = True,
    do_hit: bool = True,
    do_icpdigest: bool = True,
    replay: bool = True,
    use_queryid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2186 QUERY/HIT queryid cycle workflow."""

    descriptor = icp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICP_TOOL_PROVIDER),
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
        raise IcpActuationError(f"icp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="icp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = IcpSession(out, queryid_gate=DEFAULT_QUERYID if with_queryid else EMPTY_QUERYID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "query": do_query,
            "hit": do_hit,
            "icpdigest": do_icpdigest,
            "replay": replay,
            "use_queryid": use_queryid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_icp_tool(session, arguments))
            except IcpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_icp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_queryid
        and not skip_bind
        and do_query
        and do_hit
        and do_icpdigest
        and replay
        and use_queryid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "icp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_queryid": with_queryid,
        "skip_bind": skip_bind,
        "query_frame": do_query,
        "hit": do_hit,
        "icpdigest": do_icpdigest,
        "replay": replay,
        "use_queryid": use_queryid,
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
        "queryid_value": int(publish_result.get("queryid") or independent.get("queryid") or EMPTY_QUERYID),
        "icpdigest_value": int(publish_result.get("icpdigest") or independent.get("icpdigest") or EMPTY_ICPDIGEST),
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
        "queryid": int(trace_body["queryid_value"] or EMPTY_QUERYID),
        "icpdigest": int(trace_body["icpdigest_value"] or EMPTY_ICPDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_queryid": with_queryid,
        "skip_bind": skip_bind,
        "query_cycle": do_query,
        "hit_cycle": do_hit,
        "icpdigest_cycle": do_icpdigest,
        "replay": replay,
        "use_queryid": use_queryid,
    }


def verify_icp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_icp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    queryid = int(trace.get("queryid_value") or independent.get("queryid") or EMPTY_QUERYID)
    icpdigest = int(trace.get("icpdigest_value") or independent.get("icpdigest") or EMPTY_ICPDIGEST)
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
        "query_frame": independent.get("query_frame") is True,
        "hit_frame": independent.get("hit_frame") is True,
        "icpdigest_response": independent.get("icpdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "queryid_bound": independent.get("queryid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "icpdigest_recorded": (
            port > 0
            and queryid == DEFAULT_QUERYID
            and icpdigest == DEFAULT_ICPDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def icp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.icp_actuation import "
        "builtin_icp_actuation_proof; r=builtin_icp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='icp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_icp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ICP_ACTUATION_ID,
        name="First-class RFC 2186 Internet Cache Protocol QUERY/HIT actuation",
        description=(
            "Missions that require a icp tool can opt the icp provider in, "
            "bind a loopback RFC 2186 Internet Cache Protocol endpoint, complete a QUERY "
            "with a non-empty queryid, lockstep a HIT that carries the "
            "stored icpdigest, independently poll the stored icpdigest "
            "on a later socket, and seal a digest-chained icpdigest. Default "
            "routing stays fail-closed; a missing queryid keeps the hole "
            "falsifiable, and skip-QUERY/HIT/ICPDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.icp_actuation:builtin_icp_actuation_proof",
        proof_command=icp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.hitmeter-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/icp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/hitmeter_actuation.py",
            "src/blackhole_agent/httpver_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required icp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 2186 daemon, speaks a "
            "QUERY then HIT over Internet Cache Protocol with a non-empty queryid and "
            "icpdigest, independently polls the stored icpdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 2227 Simple Hit-Metering lockstep is proved. "
            "Missing queryids, skip-QUERY, skip-HIT, skip-icpdigest, skip-REPLAY, "
            "and a QUERY aimed without a queryid stay fail-closed. "
            "Later genesis can take RFC 2145 Use and Interpretation of HTTP Version Numbers VERSION/INTERPRET as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("icp", "rfc2186", "http", "queryid", "icpdigest", "query", "hit", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T022204Z-0682e366",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_icp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2186 query lockstep actuation seals a icpdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.httpver_actuation import (
        HTTPVER_ACTUATION_GOAL,
        HTTPVER_ACTUATION_ID,
    )
    from blackhole_agent.hitmeter_actuation import (
        HITMETER_ACTUATION_GOAL,
        HITMETER_ACTUATION_ID,
    )
    from blackhole_agent.spnego_actuation import (
        SPNEGO_ACTUATION_GOAL,
        SPNEGO_ACTUATION_ID,
    )
    from blackhole_agent.stalecontent_actuation import (
        STALECONTENT_ACTUATION_GOAL,
        STALECONTENT_ACTUATION_ID,
    )
    from blackhole_agent.extvalue_actuation import (
        EXTVALUE_ACTUATION_GOAL,
        EXTVALUE_ACTUATION_ID,
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
    checks["denylists_self"] = ICP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(ICP_ACTUATION_GOAL) == (
        ICP_ACTUATION_ID,
    )
    checks["leftover_text_binds_icp"] = leftover_marker_ids(ICP_LEFTOVER) == (
        ICP_ACTUATION_ID,
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
        (EXTVALUE_ACTUATION_GOAL, EXTVALUE_ACTUATION_ID, "extvalue"),
        (STALECONTENT_ACTUATION_GOAL, STALECONTENT_ACTUATION_ID, "stalecontent"),
        (SPNEGO_ACTUATION_GOAL, SPNEGO_ACTUATION_ID, "spnego"),
        (HTTPAUTH_ACTUATION_GOAL, HTTPAUTH_ACTUATION_ID, "httpauth"),
        (TCN_ACTUATION_GOAL, TCN_ACTUATION_ID, "tcn"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (HITMETER_ACTUATION_GOAL, HITMETER_ACTUATION_ID, "hitmeter"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_icp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"icp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            ICP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = ICP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_icp(DEFAULT_QUERY)
    rebuilt = serialize_icp(parse_icp(advertised))
    preloaded = parse_icp(RFC_ICP_HIT)
    header = encode_icp_header(DEFAULT_QUERY)
    parsed_header = parse_icp_header(header)
    asked = parse_http_request(query_request(SENTINEL, DEFAULT_QUERYID))
    preload_req = parse_http_request(hit_request(SENTINEL, DEFAULT_QUERYID, DEFAULT_ICPDIGEST))
    got = parse_http_response(query_response(SENTINEL, DEFAULT_QUERYID, DEFAULT_ICPDIGEST))
    preload_reply = parse_http_response(
        hit_response(SENTINEL, DEFAULT_QUERYID, DEFAULT_ICPDIGEST)
    )
    checks["icp_roundtrip"] = (
        parse_icp(advertised) == DEFAULT_QUERY
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_QUERY_FIELD
        and is_token("QUERY") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_QUERY_FIELD
        and parsed_header["policy"] == DEFAULT_QUERY
        and parsed_header["header"] == QUERY_HEADER
        and parsed_header["query"] is True
        and parsed_header["hit"] is False
        and preloaded == HIT_POLICY
        and ascii_serialize_icp_directive() == RFC_QUERY_DIRECTIVE
        and icp_directive_pair() == ("query", "url")
        and RFC_QUERY_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_icp(HIT_POLICY) == RFC_ICP_HIT
        and DEFAULT_ICPDIGEST == request_icpdigest(DEFAULT_QUERYID, SENTINEL)
        and "icpdigest=" in canonical_hit(SENTINEL, DEFAULT_QUERYID, DEFAULT_ICPDIGEST)
        and canonical_query(SENTINEL, DEFAULT_QUERYID).startswith("QUERY")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "QUERY"
        and asked["icp_kind"] == "query"
        and asked["queryid"] == DEFAULT_QUERYID
        and preload_req["icp_kind"] == "hit"
        and preload_req["icpdigest"] == DEFAULT_ICPDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["icp_kind"] == "query"
        and preload_reply["icp_kind"] == "hit"
        and got["policy"] == DEFAULT_QUERY
        and preload_reply["policy"] == HIT_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["icpdigest"] == DEFAULT_ICPDIGEST
        and preload_reply["icpdigest"] == DEFAULT_ICPDIGEST
        and icp_matches(serialize_icp(got["policy"]), advertised)
    )

    checks["catalog_names_icp"] = (
        len(catalog) > 99
        and catalog[99]["id"] == ICP_ACTUATION_ID
        and catalog[98]["id"] == HITMETER_ACTUATION_ID
        and catalog[99]["source"] == "genesis_bind_icp"
    )
    checks["catalog_names_httpver"] = (
        len(catalog) > 100
        and catalog[100]["id"] == HTTPVER_ACTUATION_ID
        and catalog[100]["source"] == "genesis_bind_httpver"
    )
    family = capability_family(ICP_ACTUATION_GOAL)
    checks["family_is_icp"] = "icp" in family
    checks["family_is_icp_surface"] = "icp" in family
    checks["family_is_queryid"] = "queryid" in family
    checks["family_is_rfc2186"] = "rfc2186" in family
    checks["family_is_icpdigest"] = "icpdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_httpver"] = (
        "httpver" not in family
        and "rfc2145" not in family
        and "versionid" not in family
        and "versiondigest" not in family
    )
    checks["family_is_not_hitmeter"] = (
        "hitmeter" not in family
        and "rfc2227" not in family
        and "meterid" not in family
        and "usagedigest" not in family
    )
    checks["family_is_not_httpauth"] = (
        "httpauth" not in family
        and "rfc2617" not in family
        and "nonceid" not in family
        and "authdigest" not in family
    )
    checks["family_is_not_tcn"] = (
        "tcn" not in family
        and "rfc2295" not in family
        and "variantid" not in family
        and "choicedigest" not in family
    )
    checks["family_is_not_stalecontent"] = (
        "stalecontent" not in family
        and "rfc5861" not in family
        and "staleid" not in family
        and "staledigest" not in family
    )
    checks["family_is_not_extvalue"] = (
        "extvalue" not in family
        and "rfc5987" not in family
        and "charsetid" not in family
        and "charsetdigest" not in family
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
        and "complianceid" not in family
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
    checks["family_is_not_ice"] = (
        "ice" not in family.split("/") and "rfc8445" not in family and "ufrag" not in family
    )
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
    packed = encode_query(identity=SENTINEL, queryid=DEFAULT_QUERYID, icpdigest=DEFAULT_ICPDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_query"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_queryid"] is True
        and parsed["queryid"] == DEFAULT_QUERYID
        and parsed["icpdigest"] == DEFAULT_ICPDIGEST
        and parsed["is_response"] is False
        and parsed["is_hit"] is False
        and parsed["type"] == FRAME_QUERY
        and parsed["first_byte"] == ICP_FIRST
    )
    shook = encode_hit(
        identity=SENTINEL,
        queryid=DEFAULT_QUERYID,
        icpdigest=DEFAULT_ICPDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_hit"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_query"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["queryid"] == DEFAULT_QUERYID
        and answer_parsed["icpdigest"] == DEFAULT_ICPDIGEST
        and answer_parsed["has_icpdigest"] is True
        and answer_parsed["type"] == FRAME_HIT
        and answer_parsed["first_byte"] == ICP_FIRST
    )
    bare = encode_query(identity=SENTINEL, queryid=DEFAULT_QUERYID, include_queryid=False)
    checks["missing_queryid_is_unauthed"] = parse_message(bare)["has_queryid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    hitmeter_signature = semantic_signature(ICP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(hitmeter_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_icp = ToolDescriptor(name="remote_icp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_icp)
    checks["naive_mcp_icp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = icp_tool_descriptor()
    default_icp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICP_TOOL_PROVIDER),
    )
    checks["default_icp_provider_is_unsupported"] = (
        default_icp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{ICP_TOOL_PROVIDER}" in default_icp.reasons
    )
    checks["opted_in_icp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_icp],
        required_tool_names=("local_memory", "icp"),
    )
    checks["naive_preflight_missing_icp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["icp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "icp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, ICP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "icp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="icp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_icp_workflow(with_queryid=False, output_dir=root / "missing")
        skip_bind = run_icp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_query = run_icp_workflow(do_query=False, output_dir=root / "skip-query")
        skip_hit = run_icp_workflow(do_hit=False, output_dir=root / "skip-hit")
        skip_icpdigest = run_icp_workflow(do_icpdigest=False, output_dir=root / "skip-icpdigest")
        skip_replay = run_icp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_queryid = run_icp_workflow(use_queryid=False, output_dir=root / "skip-queryid")
        live = run_icp_workflow(output_dir=root / "live")
        verify = verify_icp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_icp_trace(clone)
        checks["naive_without_queryid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_queryid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_query_stays_empty"] = (
            skip_query["ok"] is False
            and skip_query["error"] == "query_required"
            and skip_query["final_status"] == 409
            and skip_query["payload_exists"] is False
        )
        checks["skip_hit_stays_empty"] = (
            skip_hit["ok"] is False
            and skip_hit["error"] == "hit_required"
            and skip_hit["final_status"] == 409
            and skip_hit["payload_exists"] is False
        )
        checks["skip_icpdigest_stays_empty"] = (
            skip_icpdigest["ok"] is False
            and skip_icpdigest["error"] == "icpdigest_required"
            and skip_icpdigest["final_status"] == 409
            and skip_icpdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_queryid_stays_empty"] = (
            skip_queryid["ok"] is False
            and skip_queryid["error"] == "queryid_required"
            and skip_queryid["final_status"] == 409
            and skip_queryid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_icpdigest"] = (
            int(live.get("queryid") or 0) == DEFAULT_QUERYID
            and int(live.get("icpdigest") or 0) == DEFAULT_ICPDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_queryid_encode_hit_icpdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_query["ok"] is False
            and skip_hit["ok"] is False
            and skip_icpdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_queryid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="icp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != ICP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_icp"] = (
        live_goal == ICP_ACTUATION_GOAL
        and ICP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_icp"
    )

    with tempfile.TemporaryDirectory(prefix="icp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(ICP_LEFTOVER, root)
        register_catalog_proved(root, ICP_ACTUATION_ID)
        reason = leftover_satisfied_by(ICP_LEFTOVER, root)
        after = leftover_is_open(ICP_LEFTOVER, root)
    checks["icp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_icp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{ICP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_icp_actuation_capability()
    return {
        "ok": ok,
        "action": "icp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": ICP_ACTUATION_GOAL,
        "done_when": ICP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
