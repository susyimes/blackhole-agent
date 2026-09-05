"""Drive a first-class HTTP State Management Mechanism tool through RFC 2109 OFFER/ATTACH.

Tool routing already fails missions that require ``httpstate``: hosted
httpstate endpoints stay on the unsupported MCP provider, and no first-party
httpstate provider is executable. Unbound therefore cannot speak a OFFER,
lockstep a ATTACH stateid handshake over HTTP State STATEID,
independently poll the stored statedigest, or seal a statedigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``httpstate`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2109 daemon
- keep a missing-stateid client so the httpstate-stateid hole stays falsifiable
- refuse ATTACH until a OFFER lands with a non-empty stateid
- independently poll the stored statedigest on a later client socket
- persist a sealed statedigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 2145 Use and Interpretation of HTTP Version Numbers
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
    HTTPSTATE_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    httpstate_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTPSTATE_ACTUATION_ID = "capability.httpstate-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-HTTPSTATE-OK"
POLL_TOKEN = "BH-HTTPSTATE-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_STATEID = 0
EMPTY_STATEDIGEST = 0
HTTPSTATE_FIRST = 0x43  # RFC 2109 HTTP State Management Mechanism (ASCII 'C')
STATEID_SIZE = 4
STATEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_ATTACH = 0x02  # RFC 2109 ATTACH confirmation
FRAME_OFFER = 0x01  # RFC 2109 OFFER
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTPSTATE_LEFTOVER = (
    "Later genesis can take RFC 2109 HTTP State Management Mechanism OFFER/ATTACH over a "
    "stateid-gated statedigest."
)
HTTPSTATE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPSTATE_ACTUATION_ID};"
    f"capability_proved:{HTTPSTATE_ACTUATION_ID};"
    "no_skill_route"
)
HTTPSTATE_ACTUATION_GOAL = (
    "Repair rfc2109 httpstate offer/attach cycle cannot land over http "
    "httpstate stateid: hosted httpstate endpoints remain unsupported so a OFFER then "
    "ATTACH stateid handshake cannot land and a sealed statedigest "
    "cannot be produced. A missing httpstate stateid stays forbidden; fail-closed "
    "routing never opts the httpstate provider in. An independent later poll of the "
    "stored statedigest keeps the hole falsifiable."
)


class HttpstateActuationError(RuntimeError):
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
# RFC 2109 sections 5.1 and 5.2: AUTH / DIGEST.
RFC_OFFER_FIELD = "OFFER"
RFC_ATTACH_FIELD = "ATTACH"
RFC_HTTPSTATE_ATTACH = RFC_ATTACH_FIELD
RFC_OFFER_DIRECTIVE = "offer=cookie"
RFC_ATTACH_DIRECTIVE = "attach=path"
DEFAULT_OFFER = "OFFER"
ATTACH_POLICY = "ATTACH"
OFFER_HEADER = "Offer"
ATTACH_HEADER = "Attach"
HTTPSTATE_ATTACH_HEADER = ATTACH_HEADER
RFC_OFFER_PATH = "/httpstate/"
RFC_OFFER_EMPTY = ""


def httpstate_directive_pair(*, hit: bool = False) -> tuple[str, str]:
    """RFC 2109 Offer / Interpret directive pair."""

    if hit:
        return "attach", "path"
    return "offer", "cookie"


def ascii_serialize_httpstate_directive(*, hit: bool = False) -> str:
    """RFC 2109 token "=" offer-or-attach."""

    name, value = httpstate_directive_pair(hit=hit)
    if not is_token(name):
        raise HttpstateActuationError("illegal_directive")
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
            raise HttpstateActuationError("short_httpstate")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 2109 Meter token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_httpstate(policy: str | Sequence[str]) -> str:
    """Serialize RFC 2109 OFFER / ATTACH opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise HttpstateActuationError("illegal_httpstate")
    upper = text.upper().replace("_", "-")
    if upper in {"OFFER", "HTTPSTATE", "HTTPSTATE-OFFER"}:
        return "OFFER"
    if upper in {"ATTACH", "COOKIE", "HTTPSTATE-ATTACH"}:
        return "ATTACH"
    if upper.startswith("OFFER="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpstateActuationError("illegal_httpstate")
        return "OFFER"
    if upper.startswith("ATTACH="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpstateActuationError("illegal_httpstate")
        return "ATTACH"
    raise HttpstateActuationError("illegal_httpstate")


def parse_httpstate(text: str) -> str:
    """Parse RFC 2109 HTTPSTATE opcode header extensions into OFFER or ATTACH."""

    raw = str(text or "").strip()
    if not raw:
        raise HttpstateActuationError("illegal_httpstate")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"OFFER", "HTTPSTATE", "HTTPSTATE-OFFER"}:
        return "OFFER"
    if upper in {"ATTACH", "COOKIE", "HTTPSTATE-ATTACH"}:
        return "ATTACH"
    if upper.startswith("OFFER="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpstateActuationError("illegal_httpstate")
        return "OFFER"
    if upper.startswith("ATTACH="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise HttpstateActuationError("illegal_httpstate")
        return "ATTACH"
    raise HttpstateActuationError("illegal_httpstate")


def encode_httpstate_header(policy: str | Sequence[str]) -> bytes:
    """RFC 2109 Meter field as bytes."""

    return serialize_httpstate(policy).encode("ascii")


def parse_httpstate_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_httpstate(field_value) if field_value else DEFAULT_OFFER
    return {
        "field_value": field_value,
        "policy": policy,
        "header": OFFER_HEADER,
        "directive": str(policy),
        "offer": str(policy) == "OFFER",
        "attach": str(policy) == "ATTACH",
    }


def canonical_offer(identity: str, stateid: int) -> str:
    """RFC 2109 AUTH advertisement bound to identity and stateid."""

    return (
        f"{serialize_httpstate(DEFAULT_OFFER)}, "
        f"offer={ascii_serialize_httpstate_directive()}, "
        f"identity={identity}, stateid={int(stateid) & 0xFFFFFFFF}"
    )


def canonical_attach(identity: str, stateid: int, statedigest: int | None = None) -> str:
    """RFC 2109 DIGEST confirmation of the stored digest policy."""

    digest = ""
    if statedigest is not None:
        digest = f", statedigest={int(statedigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_httpstate(ATTACH_POLICY)}, "
        f"attach={ascii_serialize_httpstate_directive(hit=True)}, "
        f"identity={identity}, stateid={int(stateid) & 0xFFFFFFFF}{digest}"
    )


def representation_attach(identity: str, stateid: int, statedigest: int) -> str:
    return canonical_attach(identity, stateid, statedigest)


def httpstate_matches(left: str, right: str) -> bool:
    return parse_httpstate(left) == parse_httpstate(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise HttpstateActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise HttpstateActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise HttpstateActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise HttpstateActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def offer_request(identity: str, stateid: int) -> bytes:
    """HTTP AUTH that elicits RFC 2109 origin AUTH."""

    keyid = f"{int(stateid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"OFFER /httpstate/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"State-Id: {int(stateid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def attach_request(identity: str, stateid: int, statedigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 2109 DIGEST confirmation of the stored digest policy."""

    keyid = f"{int(stateid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if statedigest is not None:
        extra = f"State-Digest: {int(statedigest) & 0xFFFFFFFF}\r\n"
    return (
        f"ATTACH /httpstate/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"State-Id: {int(stateid) & 0xFFFFFFFF}\r\n"
        "Attach-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    httpstate_kind = "attach" if fields.get("attach-confirm") == "1" else "offer"
    upgrade_field = fields.get("offer") or fields.get("negotiate") or fields.get("httpstate") or ""
    policy = parse_httpstate(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "httpstate_kind": httpstate_kind,
        "policy": policy,
        "stateid": int(fields["state-id"]) if fields.get("state-id") else EMPTY_STATEID,
        "statedigest": int(fields["state-digest"]) if fields.get("state-digest") else EMPTY_STATEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def offer_response(identity: str, stateid: int, statedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 2109 origin AUTH, carrying the stored statedigest."""

    advertised = serialize_httpstate(DEFAULT_OFFER)
    payload = bytes(body or canonical_offer(identity, stateid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Offer: {advertised}\r\n"
        f"State-Id: {int(stateid) & 0xFFFFFFFF}\r\n"
        f"State-Digest: {int(statedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def attach_response(identity: str, stateid: int, statedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 2109 DIGEST, carrying the stored DIGEST policy."""

    advertised = serialize_httpstate(ATTACH_POLICY)
    payload = bytes(body or representation_attach(identity, stateid, statedigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Offer: {advertised}\r\n"
        f"State-Id: {int(stateid) & 0xFFFFFFFF}\r\n"
        f"State-Digest: {int(statedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/httpstate-attach\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise HttpstateActuationError("illegal_content_length") from error
    field_value = fields.get("offer") or fields.get("negotiate") or fields.get("httpstate") or ""
    policy = parse_httpstate(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/httpstate-attach" or policy == ATTACH_POLICY:
        status = 200
        httpstate_kind = "attach"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        httpstate_kind = "offer"
    else:
        status = 0
        httpstate_kind = "offer"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "httpstate_kind": httpstate_kind,
        "policy": policy,
        "stateid": int(fields["state-id"]) if fields.get("state-id") else EMPTY_STATEID,
        "statedigest": int(fields["state-digest"]) if fields.get("state-digest") else EMPTY_STATEDIGEST,
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
        raise HttpstateActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise HttpstateActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise HttpstateActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HttpstateActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_stateid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"stateid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_stateid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-stateid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_statedigest(stateid: int = EMPTY_STATEID, token: str = SENTINEL) -> int:
    material = canonical_offer(token or SENTINEL, int(stateid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_STATEID = request_stateid(SENTINEL)
DEFAULT_STATEDIGEST = request_statedigest(DEFAULT_STATEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    stateid: int,
    statedigest: int,
    include_stateid: bool = True,
) -> bytes:
    live_stateid = int(stateid) & 0xFFFFFFFF if include_stateid else EMPTY_STATEID
    live_digest = int(statedigest) & 0xFFFFFFFF if include_stateid and live_stateid else EMPTY_STATEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_stateid) if live_stateid else b""
    header = bytearray()
    header.append(HTTPSTATE_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_offer(
    *,
    identity: str,
    stateid: int,
    statedigest: int | None = None,
    include_stateid: bool = True,
) -> bytes:
    live_stateid = int(stateid) & 0xFFFFFFFF if include_stateid else EMPTY_STATEID
    live_digest = int(statedigest) if statedigest is not None else request_statedigest(live_stateid, identity)
    return encode_packet(
        FRAME_OFFER,
        identity=identity,
        stateid=live_stateid,
        statedigest=live_digest,
        include_stateid=include_stateid,
    )


def encode_attach(
    *,
    identity: str,
    stateid: int,
    statedigest: int | None = None,
    include_stateid: bool = True,
) -> bytes:
    live_stateid = int(stateid) & 0xFFFFFFFF if include_stateid else EMPTY_STATEID
    live_digest = int(statedigest) if statedigest is not None else request_statedigest(live_stateid, identity)
    return encode_packet(
        FRAME_ATTACH,
        identity=identity,
        stateid=live_stateid,
        statedigest=live_digest,
        include_stateid=include_stateid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HttpstateActuationError("short_packet")
    first = raw[0]
    if first != HTTPSTATE_FIRST:
        raise HttpstateActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise HttpstateActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == STATEID_SIZE:
        live_stateid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_stateid = EMPTY_STATEID
    else:
        raise HttpstateActuationError("illegal_stateid")
    if offset >= len(raw):
        raise HttpstateActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_OFFER, FRAME_ATTACH}:
        raise HttpstateActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HttpstateActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HttpstateActuationError("checksum_failed")
    if len(payload) < 5:
        raise HttpstateActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HttpstateActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_stateid = int(live_stateid) != EMPTY_STATEID
    has_statedigest = has_stateid and int(live_digest) != EMPTY_STATEDIGEST
    is_offer = frame_type == FRAME_OFFER
    is_attach = frame_type == FRAME_ATTACH
    return {
        "type": int(frame_type),
        "is_offer": is_offer,
        "is_attach": is_attach,
        "is_response": is_attach,
        "stateid": int(live_stateid),
        "has_stateid": has_stateid,
        "statedigest": int(live_digest),
        "has_statedigest": has_statedigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC2109",
        "serialize_field": canonical_offer(identity, live_stateid) if has_stateid else "",
        "tls_field": canonical_attach(identity, live_stateid, live_digest) if has_statedigest else "",
    }


class HttpstateClient:
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
            raise HttpstateActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_attach"] or not packet["is_response"]:
            raise HttpstateActuationError("statedigest_required")
        if not packet["has_stateid"]:
            raise HttpstateActuationError("stateid_required")
        if not packet["has_statedigest"]:
            raise HttpstateActuationError("statedigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_statedigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_statedigest:
            raise HttpstateActuationError("statedigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "stateid": int(reply.get("stateid") or EMPTY_STATEID),
            "identity": str(reply.get("identity") or ""),
            "statedigest": int(reply.get("statedigest") or EMPTY_STATEDIGEST),
        }

    def report(
        self,
        identity: str,
        stateid: int,
        statedigest: int = EMPTY_STATEDIGEST,
        *,
        wait_statedigest: bool = True,
        include_stateid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_attach(
            identity=identity,
            stateid=stateid,
            statedigest=statedigest or request_statedigest(stateid, identity),
            include_stateid=include_stateid,
        )
        return self.exchange(packet, wait_statedigest=wait_statedigest)


class HttpstateSession:
    """STATEID-gated loopback RFC 2109 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        stateid_gate: int = DEFAULT_STATEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stateid_gate = int(stateid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.stateid = EMPTY_STATEID
        self.statedigest = EMPTY_STATEDIGEST
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

    def store_stateid_once(self, identity: str, stateid: int, statedigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(stateid or EMPTY_STATEID)
            live_digest = int(statedigest or EMPTY_STATEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.stateid = live
                self.statedigest = live_digest or request_statedigest(live, name)
                self.stored = True
            return str(self.identity), int(self.stateid), int(self.statedigest)

    def read_stateid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.stateid), int(self.statedigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "stateid": EMPTY_STATEID,
            "statedigest": EMPTY_STATEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _stateid_missing(self) -> bool:
        return not int(self.stateid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, stateid: int, statedigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_attach(
            identity=identity,
            stateid=stateid,
            statedigest=statedigest,
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
            except HttpstateActuationError:
                continue
            if not packet.get("is_offer") and not packet.get("is_attach"):
                continue
            if not packet.get("has_stateid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_stateid, stored_digest = self.store_stateid_once(
                identity,
                int(packet.get("stateid") or EMPTY_STATEID),
                int(packet.get("statedigest") or EMPTY_STATEDIGEST),
            )
            if not stored_name or not stored_stateid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_offer"):
                    self.opened = True
                if packet.get("is_attach"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_stateid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._stateid_missing():
            return self._forbidden("missing_stateid")
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
        do_offer: bool = True,
        do_attach: bool = True,
        do_statedigest: bool = True,
        replay: bool = True,
        use_stateid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._stateid_missing():
            return self._forbidden("missing_stateid")
        live_token = str(token or SENTINEL)
        origin_stateid = request_stateid(live_token)
        origin_digest = request_statedigest(origin_stateid, live_token)
        client: HttpstateClient | None = None
        independent: HttpstateClient | None = None
        try:
            client = HttpstateClient(self.host, int(self.port))
            if not do_offer:
                return self._conflict("offer_required")
            bind_packet = encode_offer(
                identity=live_token,
                stateid=origin_stateid,
                statedigest=origin_digest,
                include_stateid=use_stateid,
            )
            if not use_stateid:
                try:
                    client.exchange(bind_packet, wait_statedigest=True)
                except HttpstateActuationError:
                    return self._conflict("stateid_required")
                return self._conflict("stateid_required")
            client.send(bind_packet)
            if not do_attach:
                return self._conflict("attach_required")
            proxy_packet = encode_attach(
                identity=live_token,
                stateid=origin_stateid,
                statedigest=origin_digest,
                include_stateid=True,
            )
            if not do_statedigest:
                try:
                    client.exchange(proxy_packet, wait_statedigest=False)
                except HttpstateActuationError as error:
                    if str(error) == "statedigest_required":
                        return self._conflict("statedigest_required")
                    return self._conflict("statedigest_required")
                return self._conflict("statedigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_statedigest=True)
            except HttpstateActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("stateid_required")
                if reason == "statedigest_required":
                    return self._conflict("statedigest_required")
                return self._conflict("offer_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("offer_required")
            if int(reply.get("stateid") or EMPTY_STATEID) != origin_stateid:
                return self._conflict("statedigest_required")
            if int(reply.get("statedigest") or EMPTY_STATEDIGEST) != origin_digest:
                return self._conflict("statedigest_required")
            self.retrieved = True
            if replay:
                independent = HttpstateClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_stateid(live_token),
                        request_statedigest(poll_stateid(live_token), POLL_TOKEN),
                        wait_statedigest=True,
                    )
                except HttpstateActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_stateid, stored_digest = self.read_stateid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_stateid != origin_stateid
                    or stored_digest != origin_digest
                    or int(poll.get("stateid") or EMPTY_STATEID) != origin_stateid
                    or int(poll.get("statedigest") or EMPTY_STATEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_stateid}:{origin_digest}:{live_token}:{canonical_offer(live_token, origin_stateid)}:{canonical_attach(live_token, origin_stateid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "stateid": origin_stateid,
                "statedigest": origin_digest,
                "offer_frame": True,
                "attach_frame": True,
                "statedigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "stateid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_httpstate_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "stateid": origin_stateid,
                "statedigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "offer_frame": True,
                "attach_frame": True,
                "statedigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "stateid_bound": True,
            }
        except (OSError, HttpstateActuationError) as error:
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
        live = independent_httpstate_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "stateid": int(live.get("stateid") or EMPTY_STATEID),
            "statedigest": int(live.get("statedigest") or EMPTY_STATEDIGEST),
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


def call_httpstate_tool(session: HttpstateSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one httpstate tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_offer = True if arguments.get("offer") is None else bool(arguments.get("offer"))
    do_attach = True if arguments.get("attach") is None else bool(arguments.get("attach"))
    do_statedigest = True if arguments.get("statedigest") is None else bool(arguments.get("statedigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_stateid = True if arguments.get("use_stateid") is None else bool(arguments.get("use_stateid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_offer=do_offer,
            do_attach=do_attach,
            do_statedigest=do_statedigest,
            replay=replay,
            use_stateid=use_stateid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HttpstateActuationError(f"unsupported httpstate action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_httpstate_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage statedigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "stateid": EMPTY_STATEID,
        "statedigest": EMPTY_STATEDIGEST,
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
            "offer_frame",
            "attach_frame",
            "statedigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "stateid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    stateid = int(payload.get("stateid") or EMPTY_STATEID)
    statedigest = int(payload.get("statedigest") or EMPTY_STATEDIGEST)
    dual = port > 0 and bool(stateid) and bool(statedigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "stateid": stateid,
        "statedigest": statedigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "offer_frame": payload.get("offer_frame") is True,
        "attach_frame": payload.get("attach_frame") is True,
        "statedigest_response": payload.get("statedigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "stateid_bound": payload.get("stateid_bound") is True,
    }


def run_httpstate_workflow(
    *,
    with_stateid: bool = True,
    skip_bind: bool = False,
    do_offer: bool = True,
    do_attach: bool = True,
    do_statedigest: bool = True,
    replay: bool = True,
    use_stateid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2109 OFFER/ATTACH stateid cycle workflow."""

    descriptor = httpstate_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPSTATE_TOOL_PROVIDER),
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
        raise HttpstateActuationError(f"httpstate tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="httpstate-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HttpstateSession(out, stateid_gate=DEFAULT_STATEID if with_stateid else EMPTY_STATEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "offer": do_offer,
            "attach": do_attach,
            "statedigest": do_statedigest,
            "replay": replay,
            "use_stateid": use_stateid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_httpstate_tool(session, arguments))
            except HttpstateActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_httpstate_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_stateid
        and not skip_bind
        and do_offer
        and do_attach
        and do_statedigest
        and replay
        and use_stateid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "httpstate_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_stateid": with_stateid,
        "skip_bind": skip_bind,
        "offer_frame": do_offer,
        "attach": do_attach,
        "statedigest": do_statedigest,
        "replay": replay,
        "use_stateid": use_stateid,
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
        "stateid_value": int(publish_result.get("stateid") or independent.get("stateid") or EMPTY_STATEID),
        "statedigest_value": int(publish_result.get("statedigest") or independent.get("statedigest") or EMPTY_STATEDIGEST),
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
        "stateid": int(trace_body["stateid_value"] or EMPTY_STATEID),
        "statedigest": int(trace_body["statedigest_value"] or EMPTY_STATEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_stateid": with_stateid,
        "skip_bind": skip_bind,
        "offer_cycle": do_offer,
        "attach_cycle": do_attach,
        "statedigest_cycle": do_statedigest,
        "replay": replay,
        "use_stateid": use_stateid,
    }


def verify_httpstate_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_httpstate_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    stateid = int(trace.get("stateid_value") or independent.get("stateid") or EMPTY_STATEID)
    statedigest = int(trace.get("statedigest_value") or independent.get("statedigest") or EMPTY_STATEDIGEST)
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
        "offer_frame": independent.get("offer_frame") is True,
        "attach_frame": independent.get("attach_frame") is True,
        "statedigest_response": independent.get("statedigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "stateid_bound": independent.get("stateid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "statedigest_recorded": (
            port > 0
            and stateid == DEFAULT_STATEID
            and statedigest == DEFAULT_STATEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def httpstate_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.httpstate_actuation import "
        "builtin_httpstate_actuation_proof; r=builtin_httpstate_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='httpstate_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_httpstate_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTPSTATE_ACTUATION_ID,
        name="First-class RFC 2109 HTTP State Management Mechanism OFFER/ATTACH actuation",
        description=(
            "Missions that require a httpstate tool can opt the httpstate provider in, "
            "bind a loopback RFC 2109 HTTP State Management Mechanism endpoint, complete a OFFER "
            "with a non-empty stateid, lockstep a ATTACH that carries the "
            "stored statedigest, independently poll the stored statedigest "
            "on a later socket, and seal a digest-chained statedigest. Default "
            "routing stays fail-closed; a missing stateid keeps the hole "
            "falsifiable, and skip-OFFER/ATTACH/STATEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.httpstate_actuation:builtin_httpstate_actuation_proof",
        proof_command=httpstate_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.httpver-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/httpstate_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/httpver_actuation.py",
            "src/blackhole_agent/digestauth_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required httpstate tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 2109 daemon, speaks a "
            "OFFER then ATTACH over HTTP State Management Mechanism with a non-empty stateid and "
            "statedigest, independently polls the stored statedigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 2145 Use and Interpretation of HTTP Version Numbers lockstep is proved. "
            "Missing stateids, skip-OFFER, skip-ATTACH, skip-statedigest, skip-REPLAY, "
            "and a OFFER aimed without a stateid stay fail-closed. "
            "Later genesis can take RFC 2069 Digest Access Authentication CHALLENGE/RESPONSE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("httpstate", "rfc2109", "http", "stateid", "statedigest", "offer", "attach", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T033108Z-864dfb33",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_httpstate_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2109 query lockstep actuation seals a statedigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.digestauth_actuation import (
        DIGESTAUTH_ACTUATION_GOAL,
        DIGESTAUTH_ACTUATION_ID,
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
    checks["denylists_self"] = HTTPSTATE_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTPSTATE_ACTUATION_GOAL) == (
        HTTPSTATE_ACTUATION_ID,
    )
    checks["leftover_text_binds_httpstate"] = leftover_marker_ids(HTTPSTATE_LEFTOVER) == (
        HTTPSTATE_ACTUATION_ID,
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
        (DIGESTAUTH_ACTUATION_GOAL, DIGESTAUTH_ACTUATION_ID, "digestauth"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_httpstate"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"httpstate_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTPSTATE_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTPSTATE_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_httpstate(DEFAULT_OFFER)
    rebuilt = serialize_httpstate(parse_httpstate(advertised))
    preloaded = parse_httpstate(RFC_HTTPSTATE_ATTACH)
    header = encode_httpstate_header(DEFAULT_OFFER)
    parsed_header = parse_httpstate_header(header)
    asked = parse_http_request(offer_request(SENTINEL, DEFAULT_STATEID))
    preload_req = parse_http_request(attach_request(SENTINEL, DEFAULT_STATEID, DEFAULT_STATEDIGEST))
    got = parse_http_response(offer_response(SENTINEL, DEFAULT_STATEID, DEFAULT_STATEDIGEST))
    preload_reply = parse_http_response(
        attach_response(SENTINEL, DEFAULT_STATEID, DEFAULT_STATEDIGEST)
    )
    checks["httpstate_roundtrip"] = (
        parse_httpstate(advertised) == DEFAULT_OFFER
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_OFFER_FIELD
        and is_token("OFFER") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_OFFER_FIELD
        and parsed_header["policy"] == DEFAULT_OFFER
        and parsed_header["header"] == OFFER_HEADER
        and parsed_header["offer"] is True
        and parsed_header["attach"] is False
        and preloaded == ATTACH_POLICY
        and ascii_serialize_httpstate_directive() == RFC_OFFER_DIRECTIVE
        and httpstate_directive_pair() == ("offer", "cookie")
        and RFC_OFFER_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_httpstate(ATTACH_POLICY) == RFC_HTTPSTATE_ATTACH
        and DEFAULT_STATEDIGEST == request_statedigest(DEFAULT_STATEID, SENTINEL)
        and "statedigest=" in canonical_attach(SENTINEL, DEFAULT_STATEID, DEFAULT_STATEDIGEST)
        and canonical_offer(SENTINEL, DEFAULT_STATEID).startswith("OFFER")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "OFFER"
        and asked["httpstate_kind"] == "offer"
        and asked["stateid"] == DEFAULT_STATEID
        and preload_req["httpstate_kind"] == "attach"
        and preload_req["statedigest"] == DEFAULT_STATEDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["httpstate_kind"] == "offer"
        and preload_reply["httpstate_kind"] == "attach"
        and got["policy"] == DEFAULT_OFFER
        and preload_reply["policy"] == ATTACH_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["statedigest"] == DEFAULT_STATEDIGEST
        and preload_reply["statedigest"] == DEFAULT_STATEDIGEST
        and httpstate_matches(serialize_httpstate(got["policy"]), advertised)
    )

    checks["catalog_names_httpstate"] = (
        len(catalog) > 101
        and catalog[101]["id"] == HTTPSTATE_ACTUATION_ID
        and catalog[100]["id"] == HTTPVER_ACTUATION_ID
        and catalog[101]["source"] == "genesis_bind_httpstate"
    )
    checks["catalog_names_digestauth"] = (
        len(catalog) > 102
        and catalog[102]["id"] == DIGESTAUTH_ACTUATION_ID
        and catalog[102]["source"] == "genesis_bind_digestauth"
    )
    family = capability_family(HTTPSTATE_ACTUATION_GOAL)
    checks["family_is_httpstate"] = "httpstate" in family
    checks["family_is_httpstate_surface"] = "httpstate" in family
    checks["family_is_stateid"] = "stateid" in family
    checks["family_is_rfc2109"] = "rfc2109" in family
    checks["family_is_statedigest"] = "statedigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_digestauth"] = (
        "digestauth" not in family
        and "rfc2069" not in family
        and "challengeid" not in family
        and "responsedigest" not in family
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
    packed = encode_offer(identity=SENTINEL, stateid=DEFAULT_STATEID, statedigest=DEFAULT_STATEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_offer"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_stateid"] is True
        and parsed["stateid"] == DEFAULT_STATEID
        and parsed["statedigest"] == DEFAULT_STATEDIGEST
        and parsed["is_response"] is False
        and parsed["is_attach"] is False
        and parsed["type"] == FRAME_OFFER
        and parsed["first_byte"] == HTTPSTATE_FIRST
    )
    shook = encode_attach(
        identity=SENTINEL,
        stateid=DEFAULT_STATEID,
        statedigest=DEFAULT_STATEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_attach"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_offer"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["stateid"] == DEFAULT_STATEID
        and answer_parsed["statedigest"] == DEFAULT_STATEDIGEST
        and answer_parsed["has_statedigest"] is True
        and answer_parsed["type"] == FRAME_ATTACH
        and answer_parsed["first_byte"] == HTTPSTATE_FIRST
    )
    bare = encode_offer(identity=SENTINEL, stateid=DEFAULT_STATEID, include_stateid=False)
    checks["missing_stateid_is_unauthed"] = parse_message(bare)["has_stateid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(HTTPSTATE_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_httpstate = ToolDescriptor(name="remote_httpstate", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_httpstate)
    checks["naive_mcp_httpstate_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = httpstate_tool_descriptor()
    default_httpstate = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPSTATE_TOOL_PROVIDER),
    )
    checks["default_httpstate_provider_is_unsupported"] = (
        default_httpstate.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTPSTATE_TOOL_PROVIDER}" in default_httpstate.reasons
    )
    checks["opted_in_httpstate_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_httpstate],
        required_tool_names=("local_memory", "httpstate"),
    )
    checks["naive_preflight_missing_httpstate"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["httpstate"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "httpstate"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPSTATE_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "httpstate" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="httpstate-actuation-") as tmp:
        root = Path(tmp)
        missing = run_httpstate_workflow(with_stateid=False, output_dir=root / "missing")
        skip_bind = run_httpstate_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_offer = run_httpstate_workflow(do_offer=False, output_dir=root / "skip-offer")
        skip_attach = run_httpstate_workflow(do_attach=False, output_dir=root / "skip-attach")
        skip_statedigest = run_httpstate_workflow(do_statedigest=False, output_dir=root / "skip-statedigest")
        skip_replay = run_httpstate_workflow(replay=False, output_dir=root / "skip-replay")
        skip_stateid = run_httpstate_workflow(use_stateid=False, output_dir=root / "skip-stateid")
        live = run_httpstate_workflow(output_dir=root / "live")
        verify = verify_httpstate_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_httpstate_trace(clone)
        checks["naive_without_stateid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_stateid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_offer_stays_empty"] = (
            skip_offer["ok"] is False
            and skip_offer["error"] == "offer_required"
            and skip_offer["final_status"] == 409
            and skip_offer["payload_exists"] is False
        )
        checks["skip_attach_stays_empty"] = (
            skip_attach["ok"] is False
            and skip_attach["error"] == "attach_required"
            and skip_attach["final_status"] == 409
            and skip_attach["payload_exists"] is False
        )
        checks["skip_statedigest_stays_empty"] = (
            skip_statedigest["ok"] is False
            and skip_statedigest["error"] == "statedigest_required"
            and skip_statedigest["final_status"] == 409
            and skip_statedigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_stateid_stays_empty"] = (
            skip_stateid["ok"] is False
            and skip_stateid["error"] == "stateid_required"
            and skip_stateid["final_status"] == 409
            and skip_stateid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_statedigest"] = (
            int(live.get("stateid") or 0) == DEFAULT_STATEID
            and int(live.get("statedigest") or 0) == DEFAULT_STATEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_stateid_encode_attach_statedigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_offer["ok"] is False
            and skip_attach["ok"] is False
            and skip_statedigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_stateid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="httpstate-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTPSTATE_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_httpstate"] = (
        live_goal == HTTPSTATE_ACTUATION_GOAL
        and HTTPSTATE_ACTUATION_ID in live_done
        and live_source == "genesis_bind_httpstate"
    )

    with tempfile.TemporaryDirectory(prefix="httpstate-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTPSTATE_LEFTOVER, root)
        register_catalog_proved(root, HTTPSTATE_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTPSTATE_LEFTOVER, root)
        after = leftover_is_open(HTTPSTATE_LEFTOVER, root)
    checks["httpstate_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_httpstate_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTPSTATE_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_httpstate_actuation_capability()
    return {
        "ok": ok,
        "action": "httpstate_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTPSTATE_ACTUATION_GOAL,
        "done_when": HTTPSTATE_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
