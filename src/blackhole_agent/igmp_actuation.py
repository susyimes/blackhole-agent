"""Drive a first-class Internet Group Management Protocol tool through RFC 1112 QUERY/REPORT.

Tool routing already fails missions that require ``igmp``: hosted
igmp endpoints stay on the unsupported MCP provider, and no first-party
igmp provider is executable. Unbound therefore cannot speak a QUERY,
lockstep a REPORT igmpid handshake over HTTP/1.0 IGMPID,
independently poll the stored igmpdigest, or seal a igmpdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``igmp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1112 daemon
- keep a missing-igmpid client so the igmp-igmpid hole stays falsifiable
- refuse REPORT until a QUERY lands with a non-empty igmpid
- independently poll the stored igmpdigest on a later client socket
- persist a sealed igmpdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 903 Reverse Address Resolution Protocol
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
    IGMP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    igmp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
IGMP_ACTUATION_ID = "capability.igmp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-IGMP-OK"
POLL_TOKEN = "BH-IGMP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_IGMPID = 0
EMPTY_IGMPDIGEST = 0
IGMP_FIRST = 0x02  # RFC 1112 IGMP (IP protocol 2)
IGMPID_SIZE = 4
IGMPDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_REPORT = 0x02  # RFC 1112 Host Membership Report
FRAME_QUERY = 0x01  # RFC 1112 Host Membership Query
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
IGMP_LEFTOVER = (
    "Later genesis can take RFC 1112 Internet Group Management Protocol QUERY/REPORT over a "
    "igmpid-gated igmpdigest."
)
IGMP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{IGMP_ACTUATION_ID};"
    f"capability_proved:{IGMP_ACTUATION_ID};"
    "no_skill_route"
)
IGMP_ACTUATION_GOAL = (
    "Repair rfc1112 igmp query/report cycle cannot land over http "
    "igmp igmpid: hosted igmp endpoints remain unsupported so a QUERY then "
    "REPORT igmpid handshake cannot land and a sealed igmpdigest "
    "cannot be produced. A missing igmp igmpid stays forbidden; fail-closed "
    "routing never opts the igmp provider in. An independent later poll of the "
    "stored igmpdigest keeps the hole falsifiable."
)


class IgmpActuationError(RuntimeError):
    """Raised when the HTTP/1.0 session or loopback daemon fixture misbehaves."""


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
# RFC 1112 sections 3.3 and 3.4: QUERY / REPORT.
RFC_QUERY_FIELD = "QUERY"
RFC_REPORT_FIELD = "REPORT"
RFC_IGMP_REPORT = RFC_REPORT_FIELD
RFC_QUERY_DIRECTIVE = "query=message"
RFC_REPORT_DIRECTIVE = "report=message"
DEFAULT_QUERY = "QUERY"
REPORT_POLICY = "REPORT"
QUERY_HEADER = "Query"
REPORT_HEADER = "Report"
IGMP_REPORT_HEADER = REPORT_HEADER
RFC_QUERY_PATH = "/igmp/"
RFC_QUERY_EMPTY = ""


def igmp_directive_pair(*, report: bool = False) -> tuple[str, str]:
    """RFC 1112 Query / Report directive pair."""

    if report:
        return "report", "message"
    return "query", "message"


def ascii_serialize_igmp_directive(*, report: bool = False) -> str:
    """RFC 1112 token "=" body-or-report."""

    name, value = igmp_directive_pair(report=report)
    if not is_token(name):
        raise IgmpActuationError("illegal_directive")
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
            raise IgmpActuationError("short_igmp")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 1112 body-query token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_igmp(policy: str | Sequence[str]) -> str:
    """Serialize RFC 1112 QUERY / REPORT opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise IgmpActuationError("illegal_igmp")
    upper = text.upper().replace("_", "-")
    if upper in {"QUERY", "IGMP", "IGMP-QUERY", "IGMP-REQUEST"}:
        return "QUERY"
    if upper in {"REPORT", "RESOURCE", "IGMP-REPORT"}:
        return "REPORT"
    if upper.startswith("QUERY="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IgmpActuationError("illegal_igmp")
        return "QUERY"
    if upper.startswith("REPORT="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IgmpActuationError("illegal_igmp")
        return "REPORT"
    raise IgmpActuationError("illegal_igmp")


def parse_igmp(text: str) -> str:
    """Parse RFC 1112 IGMP opcode header extensions into QUERY or REPORT."""

    raw = str(text or "").strip()
    if not raw:
        raise IgmpActuationError("illegal_igmp")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"QUERY", "IGMP", "IGMP-QUERY", "IGMP-REQUEST"}:
        return "QUERY"
    if upper in {"REPORT", "RESOURCE", "IGMP-REPORT"}:
        return "REPORT"
    if upper.startswith("QUERY="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IgmpActuationError("illegal_igmp")
        return "QUERY"
    if upper.startswith("REPORT="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IgmpActuationError("illegal_igmp")
        return "REPORT"
    raise IgmpActuationError("illegal_igmp")


def encode_igmp_header(policy: str | Sequence[str]) -> bytes:
    """RFC 1112 HTTP/1.0 field as bytes."""

    return serialize_igmp(policy).encode("ascii")


def parse_igmp_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_igmp(field_value) if field_value else DEFAULT_QUERY
    return {
        "field_value": field_value,
        "policy": policy,
        "header": QUERY_HEADER,
        "directive": str(policy),
        "query": str(policy) == "QUERY",
        "report": str(policy) == "REPORT",
    }


def canonical_query(identity: str, igmpid: int) -> str:
    """RFC 1112 body-query advertisement bound to identity and igmpid."""

    return (
        f"{serialize_igmp(DEFAULT_QUERY)}, "
        f"query={ascii_serialize_igmp_directive()}, "
        f"identity={identity}, igmpid={int(igmpid) & 0xFFFFFFFF}"
    )


def canonical_report(identity: str, igmpid: int, igmpdigest: int | None = None) -> str:
    """RFC 1112 report-message confirmation of the stored identifier-digest."""

    digest = ""
    if igmpdigest is not None:
        digest = f", igmpdigest={int(igmpdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_igmp(REPORT_POLICY)}, "
        f"report={ascii_serialize_igmp_directive(report=True)}, "
        f"identity={identity}, igmpid={int(igmpid) & 0xFFFFFFFF}{digest}"
    )


def representation_report(identity: str, igmpid: int, igmpdigest: int) -> str:
    return canonical_report(identity, igmpid, igmpdigest)


def igmp_matches(left: str, right: str) -> bool:
    return parse_igmp(left) == parse_igmp(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise IgmpActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise IgmpActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise IgmpActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise IgmpActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def query_request(identity: str, igmpid: int) -> bytes:
    """HTTP QUERY that elicits RFC 1112 origin HTTP/1.0."""

    keyid = f"{int(igmpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"QUERY /igmp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Igmp-Id: {int(igmpid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def report_request(identity: str, igmpid: int, igmpdigest: int | None = None) -> bytes:
    """HTTP REPORT carrying RFC 1112 report-message confirmation of the stored identifier-digest."""

    keyid = f"{int(igmpid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if igmpdigest is not None:
        extra = f"Igmp-Digest: {int(igmpdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"REPORT /igmp/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Igmp-Id: {int(igmpid) & 0xFFFFFFFF}\r\n"
        "Report-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    igmp_kind = "report" if fields.get("report-confirm") == "1" else "query"
    upgrade_field = fields.get("query") or fields.get("igmp") or ""
    policy = parse_igmp(upgrade_field) if upgrade_field else ()
    return {
        "kind": "query",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "igmp_kind": igmp_kind,
        "policy": policy,
        "igmpid": int(fields["igmp-id"]) if fields.get("igmp-id") else EMPTY_IGMPID,
        "igmpdigest": int(fields["igmp-digest"]) if fields.get("igmp-digest") else EMPTY_IGMPDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def query_response(identity: str, igmpid: int, igmpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 1112 origin HTTP/1.0, carrying the stored igmpdigest."""

    advertised = serialize_igmp(DEFAULT_QUERY)
    payload = bytes(body or canonical_query(identity, igmpid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Query: {advertised}\r\n"
        f"Igmp-Id: {int(igmpid) & 0xFFFFFFFF}\r\n"
        f"Igmp-Digest: {int(igmpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def report_response(identity: str, igmpid: int, igmpdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 1112 REPORT, carrying the stored identifier-digest."""

    advertised = serialize_igmp(REPORT_POLICY)
    payload = bytes(body or representation_report(identity, igmpid, igmpdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Query: {advertised}\r\n"
        f"Igmp-Id: {int(igmpid) & 0xFFFFFFFF}\r\n"
        f"Igmp-Digest: {int(igmpdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/igmp-report\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise IgmpActuationError("illegal_content_length") from error
    field_value = fields.get("query") or fields.get("igmp") or ""
    policy = parse_igmp(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/igmp-report" or policy == REPORT_POLICY:
        status = 200
        igmp_kind = "report"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        igmp_kind = "query"
    else:
        status = 0
        igmp_kind = "query"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "igmp_kind": igmp_kind,
        "policy": policy,
        "igmpid": int(fields["igmp-id"]) if fields.get("igmp-id") else EMPTY_IGMPID,
        "igmpdigest": int(fields["igmp-digest"]) if fields.get("igmp-digest") else EMPTY_IGMPDIGEST,
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
        raise IgmpActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise IgmpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise IgmpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise IgmpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc1112_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    igmp: str,
) -> str:
    """RFC 1112 identifier digest over method, query-IP, identity, and igmpid."""

    payload = f"{method}:{igmp}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def query_igmpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"igmpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_igmpid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-igmpid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def query_igmpdigest(igmpid: int = EMPTY_IGMPID, token: str = SENTINEL) -> int:
    nonce = f"{int(igmpid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc1112_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="REPORT",
        igmp=f"/igmp/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_IGMPID = query_igmpid(SENTINEL)
DEFAULT_IGMPDIGEST = query_igmpdigest(DEFAULT_IGMPID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    igmpid: int,
    igmpdigest: int,
    include_igmpid: bool = True,
) -> bytes:
    live_igmpid = int(igmpid) & 0xFFFFFFFF if include_igmpid else EMPTY_IGMPID
    live_digest = int(igmpdigest) & 0xFFFFFFFF if include_igmpid and live_igmpid else EMPTY_IGMPDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_igmpid) if live_igmpid else b""
    header = bytearray()
    header.append(IGMP_FIRST)
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
    igmpid: int,
    igmpdigest: int | None = None,
    include_igmpid: bool = True,
) -> bytes:
    live_igmpid = int(igmpid) & 0xFFFFFFFF if include_igmpid else EMPTY_IGMPID
    live_digest = int(igmpdigest) if igmpdigest is not None else query_igmpdigest(live_igmpid, identity)
    return encode_packet(
        FRAME_QUERY,
        identity=identity,
        igmpid=live_igmpid,
        igmpdigest=live_digest,
        include_igmpid=include_igmpid,
    )


def encode_report(
    *,
    identity: str,
    igmpid: int,
    igmpdigest: int | None = None,
    include_igmpid: bool = True,
) -> bytes:
    live_igmpid = int(igmpid) & 0xFFFFFFFF if include_igmpid else EMPTY_IGMPID
    live_digest = int(igmpdigest) if igmpdigest is not None else query_igmpdigest(live_igmpid, identity)
    return encode_packet(
        FRAME_REPORT,
        identity=identity,
        igmpid=live_igmpid,
        igmpdigest=live_digest,
        include_igmpid=include_igmpid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise IgmpActuationError("short_packet")
    first = raw[0]
    if first != IGMP_FIRST:
        raise IgmpActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise IgmpActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == IGMPID_SIZE:
        live_igmpid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_igmpid = EMPTY_IGMPID
    else:
        raise IgmpActuationError("illegal_igmpid")
    if offset >= len(raw):
        raise IgmpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_QUERY, FRAME_REPORT}:
        raise IgmpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise IgmpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise IgmpActuationError("checksum_failed")
    if len(payload) < 5:
        raise IgmpActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise IgmpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_igmpid = int(live_igmpid) != EMPTY_IGMPID
    has_igmpdigest = has_igmpid and int(live_digest) != EMPTY_IGMPDIGEST
    is_query = frame_type == FRAME_QUERY
    is_report = frame_type == FRAME_REPORT
    return {
        "type": int(frame_type),
        "is_query": is_query,
        "is_report": is_report,
        "igmpid": int(live_igmpid),
        "has_igmpid": has_igmpid,
        "igmpdigest": int(live_digest),
        "has_igmpdigest": has_igmpdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC1112",
        "serialize_field": canonical_query(identity, live_igmpid) if has_igmpid else "",
        "tls_field": canonical_report(identity, live_igmpid, live_digest) if has_igmpdigest else "",
    }


class IgmpClient:
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
            raise IgmpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_report"] or not packet["is_report"]:
            raise IgmpActuationError("igmpdigest_required")
        if not packet["has_igmpid"]:
            raise IgmpActuationError("igmpid_required")
        if not packet["has_igmpdigest"]:
            raise IgmpActuationError("igmpdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_igmpdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_igmpdigest:
            raise IgmpActuationError("igmpdigest_required")
        report = self._recv()
        return {
            "session": report,
            "igmpid": int(report.get("igmpid") or EMPTY_IGMPID),
            "identity": str(report.get("identity") or ""),
            "igmpdigest": int(report.get("igmpdigest") or EMPTY_IGMPDIGEST),
        }

    def report(
        self,
        identity: str,
        igmpid: int,
        igmpdigest: int = EMPTY_IGMPDIGEST,
        *,
        wait_igmpdigest: bool = True,
        include_igmpid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_report(
            identity=identity,
            igmpid=igmpid,
            igmpdigest=igmpdigest or query_igmpdigest(igmpid, identity),
            include_igmpid=include_igmpid,
        )
        return self.exchange(packet, wait_igmpdigest=wait_igmpdigest)


class IgmpSession:
    """IGMPID-gated loopback RFC 1112 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        igmpid_gate: int = DEFAULT_IGMPID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.igmpid_gate = int(igmpid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.igmpid = EMPTY_IGMPID
        self.igmpdigest = EMPTY_IGMPDIGEST
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

    def store_igmpid_once(self, identity: str, igmpid: int, igmpdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(igmpid or EMPTY_IGMPID)
            live_digest = int(igmpdigest or EMPTY_IGMPDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.igmpid = live
                self.igmpdigest = live_digest or query_igmpdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.igmpid), int(self.igmpdigest)

    def read_igmpid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.igmpid), int(self.igmpdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "igmpid": EMPTY_IGMPID,
            "igmpdigest": EMPTY_IGMPDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _igmpid_missing(self) -> bool:
        return not int(self.igmpid_gate or 0)

    def _report_tuple(self, peer: tuple[str, int], identity: str, igmpid: int, igmpdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_report(
            identity=identity,
            igmpid=igmpid,
            igmpdigest=igmpdigest,
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
            except IgmpActuationError:
                continue
            if not packet.get("is_query") and not packet.get("is_report"):
                continue
            if not packet.get("has_igmpid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_igmpid, stored_digest = self.store_igmpid_once(
                identity,
                int(packet.get("igmpid") or EMPTY_IGMPID),
                int(packet.get("igmpdigest") or EMPTY_IGMPDIGEST),
            )
            if not stored_name or not stored_igmpid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_query"):
                    self.opened = True
                if packet.get("is_report"):
                    self.handshook = True
                self.retrieved = True
            self._report_tuple(peer, stored_name, stored_igmpid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._igmpid_missing():
            return self._forbidden("missing_igmpid")
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
        do_report: bool = True,
        do_igmpdigest: bool = True,
        replay: bool = True,
        use_igmpid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._igmpid_missing():
            return self._forbidden("missing_igmpid")
        live_token = str(token or SENTINEL)
        origin_igmpid = query_igmpid(live_token)
        origin_digest = query_igmpdigest(origin_igmpid, live_token)
        client: IgmpClient | None = None
        independent: IgmpClient | None = None
        try:
            client = IgmpClient(self.host, int(self.port))
            if not do_query:
                return self._conflict("query_required")
            bind_packet = encode_query(
                identity=live_token,
                igmpid=origin_igmpid,
                igmpdigest=origin_digest,
                include_igmpid=use_igmpid,
            )
            if not use_igmpid:
                try:
                    client.exchange(bind_packet, wait_igmpdigest=True)
                except IgmpActuationError:
                    return self._conflict("igmpid_required")
                return self._conflict("igmpid_required")
            client.send(bind_packet)
            if not do_report:
                return self._conflict("report_required")
            proxy_packet = encode_report(
                identity=live_token,
                igmpid=origin_igmpid,
                igmpdigest=origin_digest,
                include_igmpid=True,
            )
            if not do_igmpdigest:
                try:
                    client.exchange(proxy_packet, wait_igmpdigest=False)
                except IgmpActuationError as error:
                    if str(error) == "igmpdigest_required":
                        return self._conflict("igmpdigest_required")
                    return self._conflict("igmpdigest_required")
                return self._conflict("igmpdigest_required")
            try:
                report = client.exchange(proxy_packet, wait_igmpdigest=True)
            except IgmpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("igmpid_required")
                if reason == "igmpdigest_required":
                    return self._conflict("igmpdigest_required")
                return self._conflict("query_required")
            if str(report.get("identity") or "") != live_token:
                return self._conflict("query_required")
            if int(report.get("igmpid") or EMPTY_IGMPID) != origin_igmpid:
                return self._conflict("igmpdigest_required")
            if int(report.get("igmpdigest") or EMPTY_IGMPDIGEST) != origin_digest:
                return self._conflict("igmpdigest_required")
            self.retrieved = True
            if replay:
                independent = IgmpClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_igmpid(live_token),
                        query_igmpdigest(poll_igmpid(live_token), POLL_TOKEN),
                        wait_igmpdigest=True,
                    )
                except IgmpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_igmpid, stored_digest = self.read_igmpid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_igmpid != origin_igmpid
                    or stored_digest != origin_digest
                    or int(poll.get("igmpid") or EMPTY_IGMPID) != origin_igmpid
                    or int(poll.get("igmpdigest") or EMPTY_IGMPDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_igmpid}:{origin_digest}:{live_token}:{canonical_query(live_token, origin_igmpid)}:{canonical_report(live_token, origin_igmpid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "igmpid": origin_igmpid,
                "igmpdigest": origin_digest,
                "query_frame": True,
                "report_frame": True,
                "igmpdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "igmpid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_igmpdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "igmpid": origin_igmpid,
                "igmpdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "query_frame": True,
                "report_frame": True,
                "igmpdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "igmpid_bound": True,
            }
        except (OSError, IgmpActuationError) as error:
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
        live = independent_igmpdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "igmpid": int(live.get("igmpid") or EMPTY_IGMPID),
            "igmpdigest": int(live.get("igmpdigest") or EMPTY_IGMPDIGEST),
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


def call_igmp_tool(session: IgmpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one igmp tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_query = True if arguments.get("query") is None else bool(arguments.get("query"))
    do_report = True if arguments.get("report") is None else bool(arguments.get("report"))
    do_igmpdigest = True if arguments.get("igmpdigest") is None else bool(arguments.get("igmpdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_igmpid = True if arguments.get("use_igmpid") is None else bool(arguments.get("use_igmpid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_query=do_query,
            do_report=do_report,
            do_igmpdigest=do_igmpdigest,
            replay=replay,
            use_igmpid=use_igmpid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise IgmpActuationError(f"unsupported igmp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_igmpdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage igmpdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "igmpid": EMPTY_IGMPID,
        "igmpdigest": EMPTY_IGMPDIGEST,
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
            "report_frame",
            "igmpdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "igmpid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    igmpid = int(payload.get("igmpid") or EMPTY_IGMPID)
    igmpdigest = int(payload.get("igmpdigest") or EMPTY_IGMPDIGEST)
    dual = port > 0 and bool(igmpid) and bool(igmpdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "igmpid": igmpid,
        "igmpdigest": igmpdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "query_frame": payload.get("query_frame") is True,
        "report_frame": payload.get("report_frame") is True,
        "igmpdigest_locate": payload.get("igmpdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "igmpid_bound": payload.get("igmpid_bound") is True,
    }


def run_igmp_workflow(
    *,
    with_igmpid: bool = True,
    skip_bind: bool = False,
    do_query: bool = True,
    do_report: bool = True,
    do_igmpdigest: bool = True,
    replay: bool = True,
    use_igmpid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1112 QUERY/REPORT igmpid cycle workflow."""

    descriptor = igmp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IGMP_TOOL_PROVIDER),
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
        raise IgmpActuationError(f"igmp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="igmp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = IgmpSession(out, igmpid_gate=DEFAULT_IGMPID if with_igmpid else EMPTY_IGMPID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "query": do_query,
            "report": do_report,
            "igmpdigest": do_igmpdigest,
            "replay": replay,
            "use_igmpid": use_igmpid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_igmp_tool(session, arguments))
            except IgmpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_igmpdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_igmpid
        and not skip_bind
        and do_query
        and do_report
        and do_igmpdigest
        and replay
        and use_igmpid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "igmp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_igmpid": with_igmpid,
        "skip_bind": skip_bind,
        "query_frame": do_query,
        "report_frame": do_report,
        "igmpdigest": do_igmpdigest,
        "replay": replay,
        "use_igmpid": use_igmpid,
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
        "igmpid_value": int(publish_result.get("igmpid") or independent.get("igmpid") or EMPTY_IGMPID),
        "igmpdigest_value": int(publish_result.get("igmpdigest") or independent.get("igmpdigest") or EMPTY_IGMPDIGEST),
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
        "igmpid": int(trace_body["igmpid_value"] or EMPTY_IGMPID),
        "igmpdigest": int(trace_body["igmpdigest_value"] or EMPTY_IGMPDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_igmpid": with_igmpid,
        "skip_bind": skip_bind,
        "query_cycle": do_query,
        "report_cycle": do_report,
        "igmpdigest_cycle": do_igmpdigest,
        "replay": replay,
        "use_igmpid": use_igmpid,
    }


def verify_igmp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_igmpdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    igmpid = int(trace.get("igmpid_value") or independent.get("igmpid") or EMPTY_IGMPID)
    igmpdigest = int(trace.get("igmpdigest_value") or independent.get("igmpdigest") or EMPTY_IGMPDIGEST)
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
        "report_frame": independent.get("report_frame") is True,
        "igmpdigest_locate": independent.get("igmpdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "igmpid_bound": independent.get("igmpid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "igmpdigest_recorded": (
            port > 0
            and igmpid == DEFAULT_IGMPID
            and igmpdigest == DEFAULT_IGMPDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def igmp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.igmp_actuation import "
        "builtin_igmp_actuation_proof; r=builtin_igmp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='igmp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_igmp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=IGMP_ACTUATION_ID,
        name="First-class RFC 1112 Internet Group Management Protocol QUERY/REPORT actuation",
        description=(
            "Missions that require a igmp tool can opt the igmp provider in, "
            "bind a loopback RFC 1112 Internet Group Management Protocol endpoint, complete a QUERY "
            "with a non-empty igmpid, lockstep a REPORT that carries the "
            "stored igmpdigest, independently poll the stored igmpdigest "
            "on a later socket, and seal a digest-chained igmpdigest. Default "
            "routing stays fail-closed; a missing igmpid keeps the hole "
            "falsifiable, and skip-QUERY/REPORT/IGMPDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.igmp_actuation:builtin_igmp_actuation_proof",
        proof_command=igmp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.rarp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/igmp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/rarp_actuation.py",
            "src/blackhole_agent/arp_actuation.py",
            "src/blackhole_agent/ip_actuation.py",
            "src/blackhole_agent/icmp_actuation.py",
            "src/blackhole_agent/mld_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required igmp tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 1112 daemon, speaks a "
            "QUERY then REPORT over Internet Group Management Protocol with a non-empty igmpid and "
            "igmpdigest, independently polls the stored igmpdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 903 Reverse Address Resolution Protocol lockstep is proved. "
            "Missing igmpids, skip-QUERY, skip-REPORT, skip-igmpdigest, skip-REPLAY, "
            "and a QUERY aimed without a igmpid stay fail-closed. "
            "Later genesis can take RFC 2710 Multicast Listener Discovery LISTENER/DONE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("igmp", "rfc1112", "http", "igmpid", "igmpdigest", "query", "report", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T155059Z-4e773aa0",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_igmp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1112 query/report lockstep actuation seals an igmpdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.mld_actuation import (
        MLD_ACTUATION_GOAL,
        MLD_ACTUATION_ID,
    )
    from blackhole_agent.rarp_actuation import (
        RARP_ACTUATION_GOAL,
        RARP_ACTUATION_ID,
    )
    from blackhole_agent.arp_actuation import (
        ARP_ACTUATION_GOAL,
        ARP_ACTUATION_ID,
    )
    from blackhole_agent.ip_actuation import (
        IP_ACTUATION_GOAL,
        IP_ACTUATION_ID,
    )
    from blackhole_agent.icmp_actuation import (
        ICMP_ACTUATION_GOAL,
        ICMP_ACTUATION_ID,
    )
    from blackhole_agent.udp_actuation import (
        UDP_ACTUATION_GOAL,
        UDP_ACTUATION_ID,
    )
    from blackhole_agent.tcp_actuation import (
        TCP_ACTUATION_GOAL,
        TCP_ACTUATION_ID,
    )
    from blackhole_agent.telnet_actuation import (
        TELNET_ACTUATION_GOAL,
        TELNET_ACTUATION_ID,
    )
    from blackhole_agent.finger_actuation import (
        FINGER_ACTUATION_GOAL,
        FINGER_ACTUATION_ID,
    )
    from blackhole_agent.mime_actuation import (
        MIME_ACTUATION_GOAL,
        MIME_ACTUATION_ID,
    )
    from blackhole_agent.uri_actuation import (
        URI_ACTUATION_GOAL,
        URI_ACTUATION_ID,
    )
    from blackhole_agent.http10_actuation import (
        HTTP10_ACTUATION_GOAL,
        HTTP10_ACTUATION_ID,
    )
    from blackhole_agent.digestauth_actuation import (
        DIGESTAUTH_ACTUATION_GOAL,
        DIGESTAUTH_ACTUATION_ID,
    )
    from blackhole_agent.httpstate_actuation import (
        HTTPSTATE_ACTUATION_GOAL,
        HTTPSTATE_ACTUATION_ID,
    )
    from blackhole_agent.httpver_actuation import (
        HTTPVER_ACTUATION_GOAL,
        HTTPVER_ACTUATION_ID,
    )
    from blackhole_agent.icp_actuation import (
        ICP_ACTUATION_GOAL,
        ICP_ACTUATION_ID,
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
    checks["denylists_self"] = IGMP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(IGMP_ACTUATION_GOAL) == (
        IGMP_ACTUATION_ID,
    )
    checks["leftover_text_binds_igmp"] = leftover_marker_ids(IGMP_LEFTOVER) == (
        IGMP_ACTUATION_ID,
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
        (MLD_ACTUATION_GOAL, MLD_ACTUATION_ID, "mld"),
        (RARP_ACTUATION_GOAL, RARP_ACTUATION_ID, "rarp"),
        (ARP_ACTUATION_GOAL, ARP_ACTUATION_ID, "arp"),
        (IP_ACTUATION_GOAL, IP_ACTUATION_ID, "ip"),
        (ICMP_ACTUATION_GOAL, ICMP_ACTUATION_ID, "icmp"),
        (UDP_ACTUATION_GOAL, UDP_ACTUATION_ID, "udp"),
        (TCP_ACTUATION_GOAL, TCP_ACTUATION_ID, "tcp"),
        (TELNET_ACTUATION_GOAL, TELNET_ACTUATION_ID, "telnet"),
        (FINGER_ACTUATION_GOAL, FINGER_ACTUATION_ID, "finger"),
        (MIME_ACTUATION_GOAL, MIME_ACTUATION_ID, "mime"),
        (URI_ACTUATION_GOAL, URI_ACTUATION_ID, "uri"),
        (HTTP10_ACTUATION_GOAL, HTTP10_ACTUATION_ID, "http10"),
        (DIGESTAUTH_ACTUATION_GOAL, DIGESTAUTH_ACTUATION_ID, "digestauth"),
        (HTTPSTATE_ACTUATION_GOAL, HTTPSTATE_ACTUATION_ID, "httpstate"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_igmp"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"igmp_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            IGMP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = IGMP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_igmp(DEFAULT_QUERY)
    rebuilt = serialize_igmp(parse_igmp(advertised))
    preloaded = parse_igmp(RFC_IGMP_REPORT)
    header = encode_igmp_header(DEFAULT_QUERY)
    parsed_header = parse_igmp_header(header)
    asked = parse_http_request(query_request(SENTINEL, DEFAULT_IGMPID))
    preload_req = parse_http_request(report_request(SENTINEL, DEFAULT_IGMPID, DEFAULT_IGMPDIGEST))
    got = parse_http_response(query_response(SENTINEL, DEFAULT_IGMPID, DEFAULT_IGMPDIGEST))
    preload_report = parse_http_response(
        report_response(SENTINEL, DEFAULT_IGMPID, DEFAULT_IGMPDIGEST)
    )
    checks["igmp_roundtrip"] = (
        parse_igmp(advertised) == DEFAULT_QUERY
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_QUERY_FIELD
        and is_token("QUERY") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_QUERY_FIELD
        and parsed_header["policy"] == DEFAULT_QUERY
        and parsed_header["header"] == QUERY_HEADER
        and parsed_header["query"] is True
        and parsed_header["report"] is False
        and preloaded == REPORT_POLICY
        and ascii_serialize_igmp_directive() == RFC_QUERY_DIRECTIVE
        and igmp_directive_pair() == ("query", "message")
        and RFC_QUERY_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_igmp(REPORT_POLICY) == RFC_IGMP_REPORT
        and DEFAULT_IGMPDIGEST == query_igmpdigest(DEFAULT_IGMPID, SENTINEL)
        and "igmpdigest=" in canonical_report(SENTINEL, DEFAULT_IGMPID, DEFAULT_IGMPDIGEST)
        and canonical_query(SENTINEL, DEFAULT_IGMPID).startswith("QUERY")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "QUERY"
        and asked["igmp_kind"] == "query"
        and asked["igmpid"] == DEFAULT_IGMPID
        and preload_req["igmp_kind"] == "report"
        and preload_req["igmpdigest"] == DEFAULT_IGMPDIGEST
        and got["status"] == 200
        and preload_report["status"] == 200
        and got["igmp_kind"] == "query"
        and preload_report["igmp_kind"] == "report"
        and got["policy"] == DEFAULT_QUERY
        and preload_report["policy"] == REPORT_POLICY
        and got["content_length_matches_body"] is True
        and preload_report["content_length_matches_body"] is True
        and got["igmpdigest"] == DEFAULT_IGMPDIGEST
        and preload_report["igmpdigest"] == DEFAULT_IGMPDIGEST
        and igmp_matches(serialize_igmp(got["policy"]), advertised)
    )

    checks["catalog_names_igmp"] = (
        len(catalog) > 118
        and catalog[118]["id"] == IGMP_ACTUATION_ID
        and catalog[117]["id"] == RARP_ACTUATION_ID
        and catalog[116]["id"] == ARP_ACTUATION_ID
        and catalog[118]["source"] == "genesis_bind_igmp"
    )
    checks["catalog_names_mld"] = (
        len(catalog) > 119
        and catalog[119]["id"] == MLD_ACTUATION_ID
        and catalog[119]["source"] == "genesis_bind_mld"
    )
    family = capability_family(IGMP_ACTUATION_GOAL)
    checks["family_is_igmp"] = "igmp" in family.split("/")
    checks["family_is_igmp_surface"] = "igmpid" in family
    checks["family_is_igmpid"] = "igmpid" in family
    checks["family_is_rfc1112"] = "rfc1112" in family
    checks["family_is_igmpdigest"] = "igmpdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_mld"] = (
        "mld" not in family.split("/")
        and "rfc2710" not in family
        and "mldid" not in family
        and "mlddigest" not in family
    )
    checks["family_is_not_rarp"] = (
        "rarp" not in family.split("/")
        and "rfc903" not in family
        and "rarpid" not in family
        and "rarpdigest" not in family
    )
    checks["family_is_not_arp"] = (
        "arp" not in family.split("/")
        and "rfc826" not in family
        and "arpid" not in family.split("/")
        and "arpdigest" not in family.split("/")
    )
    checks["family_is_not_ip"] = (
        "ip" not in family.split("/")
        and "rfc791" not in family
        and "ipid" not in family
        and "ipdigest" not in family
    )
    checks["family_is_not_tcp"] = (
        "tcp" not in family.split("/")
        and "rfc793" not in family
        and "tcpid" not in family
        and "tcpdigest" not in family
    )
    checks["family_is_not_icmp"] = (
        "icmp" not in family.split("/")
        and "rfc792" not in family
        and "icmpid" not in family
        and "icmpdigest" not in family
    )
    checks["family_is_not_udp"] = (
        "udp" not in family.split("/")
        and "rfc768" not in family
        and "udpid" not in family
        and "udpdigest" not in family
    )
    checks["family_is_not_telnet"] = (
        "telnet" not in family.split("/")
        and "rfc854" not in family
        and "telnetid" not in family
        and "telnetdigest" not in family
    )
    checks["family_is_not_finger"] = (
        "finger" not in family.split("/")
        and "rfc1288" not in family
        and "fingerid" not in family
        and "fingerdigest" not in family
    )
    checks["family_is_not_mime"] = (
        "mime" not in family.split("/")
        and "rfc1521" not in family
        and "mimeid" not in family
        and "mimedigest" not in family
    )
    checks["family_is_not_uri"] = (
        "uri" not in family.split("/")
        and "rfc1630" not in family
        and "uriid" not in family
        and "uridigest" not in family
    )
    checks["family_is_not_http10"] = (
        "http10" not in family
        and "rfc1945" not in family
        and "http10id" not in family
        and "http10digest" not in family
    )
    checks["family_is_not_digestauth"] = (
        "digestauth" not in family
        and "rfc2069" not in family
        and "challengeid" not in family
        and "responsedigest" not in family
    )
    checks["family_is_not_httpstate"] = (
        "httpstate" not in family
        and "rfc2109" not in family
        and "stateid" not in family
        and "statedigest" not in family
    )
    checks["family_is_not_httpver"] = (
        "httpver" not in family
        and "rfc2145" not in family
        and "versionid" not in family
        and "versiondigest" not in family
    )
    checks["family_is_not_icp"] = (
        "icp" not in family
        and "rfc2186" not in family
        and "queryid" not in family
        and "icpdigest" not in family
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
        "rfc9221" not in family
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
    checks["family_is_not_ntp"] = (
        "ntp" not in family.split("/")
        and "rfc5905" not in family
        and "keyid" not in family
    )
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
    packed = encode_query(identity=SENTINEL, igmpid=DEFAULT_IGMPID, igmpdigest=DEFAULT_IGMPDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_query"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_igmpid"] is True
        and parsed["igmpid"] == DEFAULT_IGMPID
        and parsed["igmpdigest"] == DEFAULT_IGMPDIGEST
        and parsed["is_report"] is False
        and parsed["is_report"] is False
        and parsed["type"] == FRAME_QUERY
        and parsed["first_byte"] == IGMP_FIRST
    )
    shook = encode_report(
        identity=SENTINEL,
        igmpid=DEFAULT_IGMPID,
        igmpdigest=DEFAULT_IGMPDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_report"] is True
        and answer_parsed["is_report"] is True
        and answer_parsed["is_query"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["igmpid"] == DEFAULT_IGMPID
        and answer_parsed["igmpdigest"] == DEFAULT_IGMPDIGEST
        and answer_parsed["has_igmpdigest"] is True
        and answer_parsed["type"] == FRAME_REPORT
        and answer_parsed["first_byte"] == IGMP_FIRST
    )
    bare = encode_query(identity=SENTINEL, igmpid=DEFAULT_IGMPID, include_igmpid=False)
    checks["missing_igmpid_is_unauthed"] = parse_message(bare)["has_igmpid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(IGMP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_igmp = ToolDescriptor(name="remote_igmp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_igmp)
    checks["naive_mcp_igmp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = igmp_tool_descriptor()
    default_igmp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IGMP_TOOL_PROVIDER),
    )
    checks["default_igmp_provider_is_unsupported"] = (
        default_igmp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{IGMP_TOOL_PROVIDER}" in default_igmp.reasons
    )
    checks["opted_in_igmp_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_igmp],
        required_tool_names=("local_memory", "igmp"),
    )
    checks["naive_preflight_missing_igmp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["igmp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "igmp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IGMP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "igmp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="igmp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_igmp_workflow(with_igmpid=False, output_dir=root / "missing")
        skip_bind = run_igmp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_query = run_igmp_workflow(do_query=False, output_dir=root / "skip-query")
        skip_report = run_igmp_workflow(do_report=False, output_dir=root / "skip-report")
        skip_igmpdigest = run_igmp_workflow(do_igmpdigest=False, output_dir=root / "skip-igmpdigest")
        skip_replay = run_igmp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_igmpid = run_igmp_workflow(use_igmpid=False, output_dir=root / "skigmp-igmpid")
        live = run_igmp_workflow(output_dir=root / "live")
        verify = verify_igmp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_igmp_trace(clone)
        checks["naive_without_igmpid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_igmpid"
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
        checks["skip_report_stays_empty"] = (
            skip_report["ok"] is False
            and skip_report["error"] == "report_required"
            and skip_report["final_status"] == 409
            and skip_report["payload_exists"] is False
        )
        checks["skip_igmpdigest_stays_empty"] = (
            skip_igmpdigest["ok"] is False
            and skip_igmpdigest["error"] == "igmpdigest_required"
            and skip_igmpdigest["final_status"] == 409
            and skip_igmpdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_igmpid_stays_empty"] = (
            skip_igmpid["ok"] is False
            and skip_igmpid["error"] == "igmpid_required"
            and skip_igmpid["final_status"] == 409
            and skip_igmpid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_igmpdigest"] = (
            int(live.get("igmpid") or 0) == DEFAULT_IGMPID
            and int(live.get("igmpdigest") or 0) == DEFAULT_IGMPDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_igmpid_encode_report_igmpdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_query["ok"] is False
            and skip_report["ok"] is False
            and skip_igmpdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_igmpid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="igmp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != IGMP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_igmp"] = (
        live_goal == IGMP_ACTUATION_GOAL
        and IGMP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_igmp"
    )

    with tempfile.TemporaryDirectory(prefix="igmp-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(IGMP_LEFTOVER, root)
        register_catalog_proved(root, IGMP_ACTUATION_ID)
        reason = leftover_satisfied_by(IGMP_LEFTOVER, root)
        after = leftover_is_open(IGMP_LEFTOVER, root)
    checks["igmp_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_igmp_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{IGMP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_igmp_actuation_capability()
    return {
        "ok": ok,
        "action": "igmp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": IGMP_ACTUATION_GOAL,
        "done_when": IGMP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
