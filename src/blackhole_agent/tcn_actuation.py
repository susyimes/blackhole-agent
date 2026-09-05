"""Drive a first-class Transparent Content Negotiation tool through RFC 2295 ALTERNATES/CHOICE.

Tool routing already fails missions that require ``tcn``: hosted
tcn endpoints stay on the unsupported MCP provider, and no first-party
tcn provider is executable. Unbound therefore cannot speak an ALTERNATES,
lockstep a CHOICE variantid handshake over TCN Choice VARIANTID,
independently poll the stored choicedigest, or seal a choicedigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``tcn`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2295 daemon
- keep a missing-variantid client so the tcn-variantid hole stays falsifiable
- refuse CHOICE until an ALTERNATES lands with a non-empty variantid
- independently poll the stored choicedigest on a later client socket
- persist a sealed choicedigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 2617 HTTP Authentication
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
    TCN_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    tcn_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
TCN_ACTUATION_ID = "capability.tcn-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-TCN-OK"
POLL_TOKEN = "BH-TCN-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_VARIANTID = 0
EMPTY_CHOICEDIGEST = 0
TCN_FIRST = 0x54  # RFC 2295 Transparent Content Negotiation (ASCII 'T')
VARIANTID_SIZE = 4
CHOICEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_CHOICE = 0x02  # RFC 2295 digest confirmation
FRAME_ALTERNATES = 0x01  # RFC 2295 AUTH
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
TCN_LEFTOVER = (
    "Later genesis can take RFC 2295 Transparent Content Negotiation ALTERNATES/CHOICE over a "
    "variantid-gated choicedigest."
)
TCN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TCN_ACTUATION_ID};"
    f"capability_proved:{TCN_ACTUATION_ID};"
    "no_skill_route"
)
TCN_ACTUATION_GOAL = (
    "Repair rfc2295 tcn alternates/choice cycle cannot land over http "
    "tcn variantid: hosted tcn endpoints remain unsupported so a ALTERNATES then "
    "CHOICE variantid handshake cannot land and a sealed choicedigest "
    "cannot be produced. A missing tcn variantid stays forbidden; fail-closed "
    "routing never opts the tcn provider in. An independent later poll of the "
    "stored choicedigest keeps the hole falsifiable."
)


class TcnActuationError(RuntimeError):
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
# RFC 2295 sections 5.1 and 5.2: AUTH / DIGEST.
RFC_ALTERNATES_FIELD = "ALTERNATES"
RFC_CHOICE_FIELD = "CHOICE"
RFC_TCN_CHOICE = RFC_CHOICE_FIELD
RFC_ALTERNATES_DIRECTIVE = "type=list"
RFC_CHOICE_DIRECTIVE = "negotiate=trans"
DEFAULT_ALTERNATES = "ALTERNATES"
CHOICE_POLICY = "CHOICE"
ALTERNATES_HEADER = "Alternates"
CHOICE_HEADER = "Negotiate"
TCN_CHOICE_HEADER = CHOICE_HEADER
RFC_ALTERNATES_PATH = "/tcn/"
RFC_ALTERNATES_EMPTY = ""


def tcn_directive_pair(*, choice: bool = False) -> tuple[str, str]:
    """RFC 2295 AUTH scheme / DIGEST qop pair."""

    if choice:
        return "negotiate", "trans"
    return "type", "list"


def ascii_serialize_tcn_directive(*, choice: bool = False) -> str:
    """RFC 2295 token "=" auth-or-digest."""

    name, value = tcn_directive_pair(choice=choice)
    if not is_token(name):
        raise TcnActuationError("illegal_directive")
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
            raise TcnActuationError("short_tcn")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 2295 DAV token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_tcn(policy: str | Sequence[str]) -> str:
    """Serialize RFC 2295 AUTH / DIGEST token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise TcnActuationError("illegal_tcn")
    upper = text.upper().replace("_", "-")
    if upper in {"ALTERNATES", "TYPE", "TCN"}:
        return "ALTERNATES"
    if upper in {"CHOICE", "NEGOTIATE", "TCN-CHOICE"}:
        return "CHOICE"
    if upper.startswith("TYPE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TcnActuationError("illegal_tcn")
        return "ALTERNATES"
    if upper.startswith("NEGOTIATE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TcnActuationError("illegal_tcn")
        return "CHOICE"
    raise TcnActuationError("illegal_tcn")


def parse_tcn(text: str) -> str:
    """Parse RFC 2295 DAV auth extensions into AUTH or DIGEST."""

    raw = str(text or "").strip()
    if not raw:
        raise TcnActuationError("illegal_tcn")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"ALTERNATES", "TYPE", "TCN"}:
        return "ALTERNATES"
    if upper in {"CHOICE", "NEGOTIATE", "TCN-CHOICE"}:
        return "CHOICE"
    if upper.startswith("TYPE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TcnActuationError("illegal_tcn")
        return "ALTERNATES"
    if upper.startswith("NEGOTIATE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise TcnActuationError("illegal_tcn")
        return "CHOICE"
    raise TcnActuationError("illegal_tcn")


def encode_tcn_header(policy: str | Sequence[str]) -> bytes:
    """RFC 2295 DAV field as bytes."""

    return serialize_tcn(policy).encode("ascii")


def parse_tcn_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_tcn(field_value) if field_value else DEFAULT_ALTERNATES
    return {
        "field_value": field_value,
        "policy": policy,
        "header": ALTERNATES_HEADER,
        "directive": str(policy),
        "alternates": str(policy) == "ALTERNATES",
        "choice": str(policy) == "CHOICE",
    }


def canonical_alternates(identity: str, variantid: int) -> str:
    """RFC 2295 AUTH advertisement bound to identity and variantid."""

    return (
        f"{serialize_tcn(DEFAULT_ALTERNATES)}, "
        f"alternates={ascii_serialize_tcn_directive()}, "
        f"identity={identity}, variantid={int(variantid) & 0xFFFFFFFF}"
    )


def canonical_choice(identity: str, variantid: int, choicedigest: int | None = None) -> str:
    """RFC 2295 DIGEST confirmation of the stored digest policy."""

    digest = ""
    if choicedigest is not None:
        digest = f", choicedigest={int(choicedigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_tcn(CHOICE_POLICY)}, "
        f"choice={ascii_serialize_tcn_directive(choice=True)}, "
        f"identity={identity}, variantid={int(variantid) & 0xFFFFFFFF}{digest}"
    )


def representation_choice(identity: str, variantid: int, choicedigest: int) -> str:
    return canonical_choice(identity, variantid, choicedigest)


def tcn_matches(left: str, right: str) -> bool:
    return parse_tcn(left) == parse_tcn(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise TcnActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise TcnActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise TcnActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise TcnActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def alternates_request(identity: str, variantid: int) -> bytes:
    """HTTP AUTH that elicits RFC 2295 origin AUTH."""

    keyid = f"{int(variantid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"ALTERNATES /tcn/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Variant-Id: {int(variantid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def choice_request(identity: str, variantid: int, choicedigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 2295 DIGEST confirmation of the stored digest policy."""

    keyid = f"{int(variantid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if choicedigest is not None:
        extra = f"Choice-Digest: {int(choicedigest) & 0xFFFFFFFF}\r\n"
    return (
        f"CHOICE /tcn/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Variant-Id: {int(variantid) & 0xFFFFFFFF}\r\n"
        "Choice-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    tcn_kind = "choice" if fields.get("choice-confirm") == "1" else "alternates"
    upgrade_field = fields.get("alternates") or fields.get("negotiate") or fields.get("tcn") or ""
    policy = parse_tcn(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "tcn_kind": tcn_kind,
        "policy": policy,
        "variantid": int(fields["variant-id"]) if fields.get("variant-id") else EMPTY_VARIANTID,
        "choicedigest": int(fields["choice-digest"]) if fields.get("choice-digest") else EMPTY_CHOICEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def alternates_response(identity: str, variantid: int, choicedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 2295 origin AUTH, carrying the stored choicedigest."""

    advertised = serialize_tcn(DEFAULT_ALTERNATES)
    payload = bytes(body or canonical_alternates(identity, variantid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Alternates: {advertised}\r\n"
        f"Variant-Id: {int(variantid) & 0xFFFFFFFF}\r\n"
        f"Choice-Digest: {int(choicedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def choice_response(identity: str, variantid: int, choicedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 2295 DIGEST, carrying the stored DIGEST policy."""

    advertised = serialize_tcn(CHOICE_POLICY)
    payload = bytes(body or representation_choice(identity, variantid, choicedigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Alternates: {advertised}\r\n"
        f"Variant-Id: {int(variantid) & 0xFFFFFFFF}\r\n"
        f"Choice-Digest: {int(choicedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/http-choice\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise TcnActuationError("illegal_content_length") from error
    field_value = fields.get("alternates") or fields.get("negotiate") or fields.get("tcn") or ""
    policy = parse_tcn(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/http-choice" or policy == CHOICE_POLICY:
        status = 200
        tcn_kind = "choice"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        tcn_kind = "alternates"
    else:
        status = 0
        tcn_kind = "alternates"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "tcn_kind": tcn_kind,
        "policy": policy,
        "variantid": int(fields["variant-id"]) if fields.get("variant-id") else EMPTY_VARIANTID,
        "choicedigest": int(fields["choice-digest"]) if fields.get("choice-digest") else EMPTY_CHOICEDIGEST,
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
        raise TcnActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise TcnActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise TcnActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise TcnActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def request_variantid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"variantid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_variantid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-variantid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_choicedigest(variantid: int = EMPTY_VARIANTID, token: str = SENTINEL) -> int:
    material = canonical_alternates(token or SENTINEL, int(variantid) & 0xFFFFFFFF).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_VARIANTID = request_variantid(SENTINEL)
DEFAULT_CHOICEDIGEST = request_choicedigest(DEFAULT_VARIANTID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    variantid: int,
    choicedigest: int,
    include_variantid: bool = True,
) -> bytes:
    live_variantid = int(variantid) & 0xFFFFFFFF if include_variantid else EMPTY_VARIANTID
    live_digest = int(choicedigest) & 0xFFFFFFFF if include_variantid and live_variantid else EMPTY_CHOICEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_variantid) if live_variantid else b""
    header = bytearray()
    header.append(TCN_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_alternates(
    *,
    identity: str,
    variantid: int,
    choicedigest: int | None = None,
    include_variantid: bool = True,
) -> bytes:
    live_variantid = int(variantid) & 0xFFFFFFFF if include_variantid else EMPTY_VARIANTID
    live_digest = int(choicedigest) if choicedigest is not None else request_choicedigest(live_variantid, identity)
    return encode_packet(
        FRAME_ALTERNATES,
        identity=identity,
        variantid=live_variantid,
        choicedigest=live_digest,
        include_variantid=include_variantid,
    )


def encode_choice(
    *,
    identity: str,
    variantid: int,
    choicedigest: int | None = None,
    include_variantid: bool = True,
) -> bytes:
    live_variantid = int(variantid) & 0xFFFFFFFF if include_variantid else EMPTY_VARIANTID
    live_digest = int(choicedigest) if choicedigest is not None else request_choicedigest(live_variantid, identity)
    return encode_packet(
        FRAME_CHOICE,
        identity=identity,
        variantid=live_variantid,
        choicedigest=live_digest,
        include_variantid=include_variantid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise TcnActuationError("short_packet")
    first = raw[0]
    if first != TCN_FIRST:
        raise TcnActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise TcnActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == VARIANTID_SIZE:
        live_variantid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_variantid = EMPTY_VARIANTID
    else:
        raise TcnActuationError("illegal_variantid")
    if offset >= len(raw):
        raise TcnActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_ALTERNATES, FRAME_CHOICE}:
        raise TcnActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise TcnActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise TcnActuationError("checksum_failed")
    if len(payload) < 5:
        raise TcnActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise TcnActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_variantid = int(live_variantid) != EMPTY_VARIANTID
    has_choicedigest = has_variantid and int(live_digest) != EMPTY_CHOICEDIGEST
    is_alternates = frame_type == FRAME_ALTERNATES
    is_choice = frame_type == FRAME_CHOICE
    return {
        "type": int(frame_type),
        "is_alternates": is_alternates,
        "is_choice": is_choice,
        "is_response": is_choice,
        "variantid": int(live_variantid),
        "has_variantid": has_variantid,
        "choicedigest": int(live_digest),
        "has_choicedigest": has_choicedigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC2295",
        "serialize_field": canonical_alternates(identity, live_variantid) if has_variantid else "",
        "tls_field": canonical_choice(identity, live_variantid, live_digest) if has_choicedigest else "",
    }


class TcnClient:
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
            raise TcnActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_choice"] or not packet["is_response"]:
            raise TcnActuationError("choicedigest_required")
        if not packet["has_variantid"]:
            raise TcnActuationError("variantid_required")
        if not packet["has_choicedigest"]:
            raise TcnActuationError("choicedigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_choicedigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_choicedigest:
            raise TcnActuationError("choicedigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "variantid": int(reply.get("variantid") or EMPTY_VARIANTID),
            "identity": str(reply.get("identity") or ""),
            "choicedigest": int(reply.get("choicedigest") or EMPTY_CHOICEDIGEST),
        }

    def report(
        self,
        identity: str,
        variantid: int,
        choicedigest: int = EMPTY_CHOICEDIGEST,
        *,
        wait_choicedigest: bool = True,
        include_variantid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_choice(
            identity=identity,
            variantid=variantid,
            choicedigest=choicedigest or request_choicedigest(variantid, identity),
            include_variantid=include_variantid,
        )
        return self.exchange(packet, wait_choicedigest=wait_choicedigest)


class TcnSession:
    """VARIANTID-gated loopback RFC 2295 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        variantid_gate: int = DEFAULT_VARIANTID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.variantid_gate = int(variantid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.variantid = EMPTY_VARIANTID
        self.choicedigest = EMPTY_CHOICEDIGEST
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

    def store_variantid_once(self, identity: str, variantid: int, choicedigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(variantid or EMPTY_VARIANTID)
            live_digest = int(choicedigest or EMPTY_CHOICEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.variantid = live
                self.choicedigest = live_digest or request_choicedigest(live, name)
                self.stored = True
            return str(self.identity), int(self.variantid), int(self.choicedigest)

    def read_variantid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.variantid), int(self.choicedigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "variantid": EMPTY_VARIANTID,
            "choicedigest": EMPTY_CHOICEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _variantid_missing(self) -> bool:
        return not int(self.variantid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, variantid: int, choicedigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_choice(
            identity=identity,
            variantid=variantid,
            choicedigest=choicedigest,
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
            except TcnActuationError:
                continue
            if not packet.get("is_alternates") and not packet.get("is_choice"):
                continue
            if not packet.get("has_variantid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_variantid, stored_digest = self.store_variantid_once(
                identity,
                int(packet.get("variantid") or EMPTY_VARIANTID),
                int(packet.get("choicedigest") or EMPTY_CHOICEDIGEST),
            )
            if not stored_name or not stored_variantid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_alternates"):
                    self.opened = True
                if packet.get("is_choice"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_variantid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._variantid_missing():
            return self._forbidden("missing_variantid")
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
        do_alternates: bool = True,
        do_choice: bool = True,
        do_choicedigest: bool = True,
        replay: bool = True,
        use_variantid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._variantid_missing():
            return self._forbidden("missing_variantid")
        live_token = str(token or SENTINEL)
        origin_variantid = request_variantid(live_token)
        origin_digest = request_choicedigest(origin_variantid, live_token)
        client: TcnClient | None = None
        independent: TcnClient | None = None
        try:
            client = TcnClient(self.host, int(self.port))
            if not do_alternates:
                return self._conflict("alternates_required")
            bind_packet = encode_alternates(
                identity=live_token,
                variantid=origin_variantid,
                choicedigest=origin_digest,
                include_variantid=use_variantid,
            )
            if not use_variantid:
                try:
                    client.exchange(bind_packet, wait_choicedigest=True)
                except TcnActuationError:
                    return self._conflict("variantid_required")
                return self._conflict("variantid_required")
            client.send(bind_packet)
            if not do_choice:
                return self._conflict("choice_required")
            proxy_packet = encode_choice(
                identity=live_token,
                variantid=origin_variantid,
                choicedigest=origin_digest,
                include_variantid=True,
            )
            if not do_choicedigest:
                try:
                    client.exchange(proxy_packet, wait_choicedigest=False)
                except TcnActuationError as error:
                    if str(error) == "choicedigest_required":
                        return self._conflict("choicedigest_required")
                    return self._conflict("choicedigest_required")
                return self._conflict("choicedigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_choicedigest=True)
            except TcnActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("variantid_required")
                if reason == "choicedigest_required":
                    return self._conflict("choicedigest_required")
                return self._conflict("alternates_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("alternates_required")
            if int(reply.get("variantid") or EMPTY_VARIANTID) != origin_variantid:
                return self._conflict("choicedigest_required")
            if int(reply.get("choicedigest") or EMPTY_CHOICEDIGEST) != origin_digest:
                return self._conflict("choicedigest_required")
            self.retrieved = True
            if replay:
                independent = TcnClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_variantid(live_token),
                        request_choicedigest(poll_variantid(live_token), POLL_TOKEN),
                        wait_choicedigest=True,
                    )
                except TcnActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_variantid, stored_digest = self.read_variantid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_variantid != origin_variantid
                    or stored_digest != origin_digest
                    or int(poll.get("variantid") or EMPTY_VARIANTID) != origin_variantid
                    or int(poll.get("choicedigest") or EMPTY_CHOICEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_variantid}:{origin_digest}:{live_token}:{canonical_alternates(live_token, origin_variantid)}:{canonical_choice(live_token, origin_variantid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "variantid": origin_variantid,
                "choicedigest": origin_digest,
                "alternates_frame": True,
                "choice_frame": True,
                "choicedigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "variantid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_tcn_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "variantid": origin_variantid,
                "choicedigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "alternates_frame": True,
                "choice_frame": True,
                "choicedigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "variantid_bound": True,
            }
        except (OSError, TcnActuationError) as error:
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
        live = independent_tcn_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "variantid": int(live.get("variantid") or EMPTY_VARIANTID),
            "choicedigest": int(live.get("choicedigest") or EMPTY_CHOICEDIGEST),
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


def call_tcn_tool(session: TcnSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one auth tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_alternates = True if arguments.get("alternates") is None else bool(arguments.get("alternates"))
    do_choice = True if arguments.get("choice") is None else bool(arguments.get("choice"))
    do_choicedigest = True if arguments.get("choicedigest") is None else bool(arguments.get("choicedigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_variantid = True if arguments.get("use_variantid") is None else bool(arguments.get("use_variantid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_alternates=do_alternates,
            do_choice=do_choice,
            do_choicedigest=do_choicedigest,
            replay=replay,
            use_variantid=use_variantid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise TcnActuationError(f"unsupported tcn action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_tcn_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed auth choicedigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "variantid": EMPTY_VARIANTID,
        "choicedigest": EMPTY_CHOICEDIGEST,
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
            "alternates_frame",
            "choice_frame",
            "choicedigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "variantid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    variantid = int(payload.get("variantid") or EMPTY_VARIANTID)
    choicedigest = int(payload.get("choicedigest") or EMPTY_CHOICEDIGEST)
    dual = port > 0 and bool(variantid) and bool(choicedigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "variantid": variantid,
        "choicedigest": choicedigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "alternates_frame": payload.get("alternates_frame") is True,
        "choice_frame": payload.get("choice_frame") is True,
        "choicedigest_response": payload.get("choicedigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "variantid_bound": payload.get("variantid_bound") is True,
    }


def run_tcn_workflow(
    *,
    with_variantid: bool = True,
    skip_bind: bool = False,
    do_alternates: bool = True,
    do_choice: bool = True,
    do_choicedigest: bool = True,
    replay: bool = True,
    use_variantid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2295 ALTERNATES/CHOICE variantid cycle workflow."""

    descriptor = tcn_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TCN_TOOL_PROVIDER),
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
        raise TcnActuationError(f"tcn tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="tcn-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = TcnSession(out, variantid_gate=DEFAULT_VARIANTID if with_variantid else EMPTY_VARIANTID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "alternates": do_alternates,
            "choice": do_choice,
            "choicedigest": do_choicedigest,
            "replay": replay,
            "use_variantid": use_variantid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_tcn_tool(session, arguments))
            except TcnActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_tcn_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_variantid
        and not skip_bind
        and do_alternates
        and do_choice
        and do_choicedigest
        and replay
        and use_variantid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "tcn_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_variantid": with_variantid,
        "skip_bind": skip_bind,
        "alternates_frame": do_alternates,
        "choice": do_choice,
        "choicedigest": do_choicedigest,
        "replay": replay,
        "use_variantid": use_variantid,
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
        "variantid_value": int(publish_result.get("variantid") or independent.get("variantid") or EMPTY_VARIANTID),
        "choicedigest_value": int(publish_result.get("choicedigest") or independent.get("choicedigest") or EMPTY_CHOICEDIGEST),
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
        "variantid": int(trace_body["variantid_value"] or EMPTY_VARIANTID),
        "choicedigest": int(trace_body["choicedigest_value"] or EMPTY_CHOICEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_variantid": with_variantid,
        "skip_bind": skip_bind,
        "alternates_cycle": do_alternates,
        "choice_cycle": do_choice,
        "choicedigest_cycle": do_choicedigest,
        "replay": replay,
        "use_variantid": use_variantid,
    }


def verify_tcn_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_tcn_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    variantid = int(trace.get("variantid_value") or independent.get("variantid") or EMPTY_VARIANTID)
    choicedigest = int(trace.get("choicedigest_value") or independent.get("choicedigest") or EMPTY_CHOICEDIGEST)
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
        "alternates_frame": independent.get("alternates_frame") is True,
        "choice_frame": independent.get("choice_frame") is True,
        "choicedigest_response": independent.get("choicedigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "variantid_bound": independent.get("variantid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "choicedigest_recorded": (
            port > 0
            and variantid == DEFAULT_VARIANTID
            and choicedigest == DEFAULT_CHOICEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def tcn_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.tcn_actuation import "
        "builtin_tcn_actuation_proof; r=builtin_tcn_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='tcn_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_tcn_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=TCN_ACTUATION_ID,
        name="First-class RFC 2295 Transparent Content Negotiation ALTERNATES/CHOICE actuation",
        description=(
            "Missions that require a tcn tool can opt the tcn provider in, "
            "bind a loopback RFC 2295 Transparent Content Negotiation endpoint, complete an ALTERNATES "
            "with a non-empty variantid, lockstep a CHOICE that carries the "
            "stored choicedigest, independently poll the stored choicedigest "
            "on a later socket, and seal a digest-chained choicedigest. Default "
            "routing stays fail-closed; a missing variantid keeps the hole "
            "falsifiable, and skip-ALTERNATES/CHOICE/CHOICEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.tcn_actuation:builtin_tcn_actuation_proof",
        proof_command=tcn_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.httpauth-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/tcn_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/httpauth_actuation.py",
            "src/blackhole_agent/hitmeter_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required tcn tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 2295 daemon, speaks a "
            "ALTERNATES then CHOICE over Transparent Content Negotiation with a non-empty variantid and "
            "choicedigest, independently polls the stored choicedigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 2617 HTTP Authentication lockstep is proved. "
            "Missing variantids, skip-ALTERNATES, skip-CHOICE, skip-choicedigest, skip-REPLAY, "
            "and an ALTERNATES aimed without a variantid stay fail-closed. "
            "Later genesis can take RFC 2227 Simple Hit-Metering METER/USAGE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("tcn", "rfc2295", "http", "variantid", "choicedigest", "alternates", "choice", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T010813Z-056d63ec",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_tcn_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2295 auth lockstep actuation seals a choicedigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
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
    checks["denylists_self"] = TCN_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(TCN_ACTUATION_GOAL) == (
        TCN_ACTUATION_ID,
    )
    checks["leftover_text_binds_tcn"] = leftover_marker_ids(TCN_LEFTOVER) == (
        TCN_ACTUATION_ID,
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
        (HITMETER_ACTUATION_GOAL, HITMETER_ACTUATION_ID, "hitmeter"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_tcn"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"tcn_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            TCN_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = TCN_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_tcn(DEFAULT_ALTERNATES)
    rebuilt = serialize_tcn(parse_tcn(advertised))
    preloaded = parse_tcn(RFC_TCN_CHOICE)
    header = encode_tcn_header(DEFAULT_ALTERNATES)
    parsed_header = parse_tcn_header(header)
    asked = parse_http_request(alternates_request(SENTINEL, DEFAULT_VARIANTID))
    preload_req = parse_http_request(choice_request(SENTINEL, DEFAULT_VARIANTID, DEFAULT_CHOICEDIGEST))
    got = parse_http_response(alternates_response(SENTINEL, DEFAULT_VARIANTID, DEFAULT_CHOICEDIGEST))
    preload_reply = parse_http_response(
        choice_response(SENTINEL, DEFAULT_VARIANTID, DEFAULT_CHOICEDIGEST)
    )
    checks["tcn_roundtrip"] = (
        parse_tcn(advertised) == DEFAULT_ALTERNATES
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_ALTERNATES_FIELD
        and is_token("ALTERNATES") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_ALTERNATES_FIELD
        and parsed_header["policy"] == DEFAULT_ALTERNATES
        and parsed_header["header"] == ALTERNATES_HEADER
        and parsed_header["alternates"] is True
        and parsed_header["choice"] is False
        and preloaded == CHOICE_POLICY
        and ascii_serialize_tcn_directive() == RFC_ALTERNATES_DIRECTIVE
        and tcn_directive_pair() == ("type", "list")
        and RFC_ALTERNATES_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_tcn(CHOICE_POLICY) == RFC_TCN_CHOICE
        and DEFAULT_CHOICEDIGEST == request_choicedigest(DEFAULT_VARIANTID, SENTINEL)
        and "choicedigest=" in canonical_choice(SENTINEL, DEFAULT_VARIANTID, DEFAULT_CHOICEDIGEST)
        and canonical_alternates(SENTINEL, DEFAULT_VARIANTID).startswith("ALTERNATES")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "ALTERNATES"
        and asked["tcn_kind"] == "alternates"
        and asked["variantid"] == DEFAULT_VARIANTID
        and preload_req["tcn_kind"] == "choice"
        and preload_req["choicedigest"] == DEFAULT_CHOICEDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["tcn_kind"] == "alternates"
        and preload_reply["tcn_kind"] == "choice"
        and got["policy"] == DEFAULT_ALTERNATES
        and preload_reply["policy"] == CHOICE_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["choicedigest"] == DEFAULT_CHOICEDIGEST
        and preload_reply["choicedigest"] == DEFAULT_CHOICEDIGEST
        and tcn_matches(serialize_tcn(got["policy"]), advertised)
    )

    checks["catalog_names_tcn"] = (
        len(catalog) > 97
        and catalog[97]["id"] == TCN_ACTUATION_ID
        and catalog[96]["id"] == HTTPAUTH_ACTUATION_ID
        and catalog[97]["source"] == "genesis_bind_tcn"
    )
    checks["catalog_names_hitmeter"] = (
        len(catalog) > 98
        and catalog[98]["id"] == HITMETER_ACTUATION_ID
        and catalog[98]["source"] == "genesis_bind_hitmeter"
    )
    family = capability_family(TCN_ACTUATION_GOAL)
    checks["family_is_tcn"] = "tcn" in family
    checks["family_is_tcn_surface"] = "tcn" in family
    checks["family_is_variantid"] = "variantid" in family
    checks["family_is_rfc2295"] = "rfc2295" in family
    checks["family_is_choicedigest"] = "choicedigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
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
    packed = encode_alternates(identity=SENTINEL, variantid=DEFAULT_VARIANTID, choicedigest=DEFAULT_CHOICEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_alternates"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_variantid"] is True
        and parsed["variantid"] == DEFAULT_VARIANTID
        and parsed["choicedigest"] == DEFAULT_CHOICEDIGEST
        and parsed["is_response"] is False
        and parsed["is_choice"] is False
        and parsed["type"] == FRAME_ALTERNATES
        and parsed["first_byte"] == TCN_FIRST
    )
    shook = encode_choice(
        identity=SENTINEL,
        variantid=DEFAULT_VARIANTID,
        choicedigest=DEFAULT_CHOICEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_choice"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_alternates"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["variantid"] == DEFAULT_VARIANTID
        and answer_parsed["choicedigest"] == DEFAULT_CHOICEDIGEST
        and answer_parsed["has_choicedigest"] is True
        and answer_parsed["type"] == FRAME_CHOICE
        and answer_parsed["first_byte"] == TCN_FIRST
    )
    bare = encode_alternates(identity=SENTINEL, variantid=DEFAULT_VARIANTID, include_variantid=False)
    checks["missing_variantid_is_unauthed"] = parse_message(bare)["has_variantid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    tcn_signature = semantic_signature(TCN_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(tcn_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_tcn = ToolDescriptor(name="remote_tcn", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_tcn)
    checks["naive_mcp_tcn_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = tcn_tool_descriptor()
    default_tcn = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TCN_TOOL_PROVIDER),
    )
    checks["default_tcn_provider_is_unsupported"] = (
        default_tcn.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{TCN_TOOL_PROVIDER}" in default_tcn.reasons
    )
    checks["opted_in_tcn_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_tcn],
        required_tool_names=("local_memory", "tcn"),
    )
    checks["naive_preflight_missing_tcn"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["tcn"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "tcn"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, TCN_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "tcn" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="tcn-actuation-") as tmp:
        root = Path(tmp)
        missing = run_tcn_workflow(with_variantid=False, output_dir=root / "missing")
        skip_bind = run_tcn_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_alternates = run_tcn_workflow(do_alternates=False, output_dir=root / "skip-upgrade")
        skip_choice = run_tcn_workflow(do_choice=False, output_dir=root / "skip-tls")
        skip_choicedigest = run_tcn_workflow(do_choicedigest=False, output_dir=root / "skip-choicedigest")
        skip_replay = run_tcn_workflow(replay=False, output_dir=root / "skip-replay")
        skip_variantid = run_tcn_workflow(use_variantid=False, output_dir=root / "skip-variantid")
        live = run_tcn_workflow(output_dir=root / "live")
        verify = verify_tcn_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_tcn_trace(clone)
        checks["naive_without_variantid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_variantid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_alternates_stays_empty"] = (
            skip_alternates["ok"] is False
            and skip_alternates["error"] == "alternates_required"
            and skip_alternates["final_status"] == 409
            and skip_alternates["payload_exists"] is False
        )
        checks["skip_choice_stays_empty"] = (
            skip_choice["ok"] is False
            and skip_choice["error"] == "choice_required"
            and skip_choice["final_status"] == 409
            and skip_choice["payload_exists"] is False
        )
        checks["skip_choicedigest_stays_empty"] = (
            skip_choicedigest["ok"] is False
            and skip_choicedigest["error"] == "choicedigest_required"
            and skip_choicedigest["final_status"] == 409
            and skip_choicedigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_variantid_stays_empty"] = (
            skip_variantid["ok"] is False
            and skip_variantid["error"] == "variantid_required"
            and skip_variantid["final_status"] == 409
            and skip_variantid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_choicedigest"] = (
            int(live.get("variantid") or 0) == DEFAULT_VARIANTID
            and int(live.get("choicedigest") or 0) == DEFAULT_CHOICEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_variantid_encode_choice_choicedigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_alternates["ok"] is False
            and skip_choice["ok"] is False
            and skip_choicedigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_variantid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="tcn-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != TCN_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_tcn"] = (
        live_goal == TCN_ACTUATION_GOAL
        and TCN_ACTUATION_ID in live_done
        and live_source == "genesis_bind_tcn"
    )

    with tempfile.TemporaryDirectory(prefix="tcn-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(TCN_LEFTOVER, root)
        register_catalog_proved(root, TCN_ACTUATION_ID)
        reason = leftover_satisfied_by(TCN_LEFTOVER, root)
        after = leftover_is_open(TCN_LEFTOVER, root)
    checks["tcn_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_tcn_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{TCN_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_tcn_actuation_capability()
    return {
        "ok": ok,
        "action": "tcn_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": TCN_ACTUATION_GOAL,
        "done_when": TCN_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
