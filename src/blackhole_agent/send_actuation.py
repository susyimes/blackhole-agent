"""Drive a first-class SEcure Neighbor Discovery tool through RFC 3971 CPS/CPA.

Tool routing already fails missions that require ``send``: hosted
send endpoints stay on the unsupported MCP provider, and no first-party
send provider is executable. Unbound therefore cannot speak a CPS,
lockstep a CPA sendid handshake over HTTP/1.0 SENDID,
independently poll the stored senddigest, or seal a senddigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``send`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 3971 daemon
- keep a missing-sendid client so the send-sendid hole stays falsifiable
- refuse CPA until a CPS lands with a non-empty sendid
- independently poll the stored senddigest on a later client socket
- persist a sealed senddigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 3972 Cryptographically Generated Addresses
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
    SEND_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    send_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
SEND_ACTUATION_ID = "capability.send-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SEND-OK"
POLL_TOKEN = "BH-SEND-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_SENDID = 0
EMPTY_SENDDIGEST = 0
SEND_FIRST = 0x94  # RFC 3971 CPS (ICMPv6 type 148)
SENDID_SIZE = 4
SENDDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_CPA = 0x02  # RFC 3971 cpa address
FRAME_CPS = 0x01  # RFC 3971 cps address
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
SEND_LEFTOVER = (
    "Later genesis can take RFC 3971 SEcure Neighbor Discovery CPS/CPA over an "
    "sendid-gated senddigest."
)
SEND_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SEND_ACTUATION_ID};"
    f"capability_proved:{SEND_ACTUATION_ID};"
    "no_skill_route"
)
SEND_ACTUATION_GOAL = (
    "Repair rfc3971 send cps/cpa cycle cannot land over http "
    "send sendid: hosted send endpoints remain unsupported so a CPS then "
    "CPA sendid handshake cannot land and a sealed senddigest "
    "cannot be produced. A missing send sendid stays forbidden; fail-closed "
    "routing never opts the send provider in. An independent later poll of the "
    "stored senddigest keeps the hole falsifiable."
)


class SendActuationError(RuntimeError):
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
# RFC 3971 sections 3.1 and 3.2: CPS / CPA.
RFC_CPS_FIELD = "CPS"
RFC_CPA_FIELD = "CPA"
RFC_SEND_CPA = RFC_CPA_FIELD
RFC_CPS_DIRECTIVE = "cps=message"
RFC_CPA_DIRECTIVE = "cpa=message"
DEFAULT_CPS = "CPS"
CPA_POLICY = "CPA"
CPS_HEADER = "Cps"
CPA_HEADER = "Cpa"
SEND_CPA_HEADER = CPA_HEADER
RFC_CPS_PATH = "/send/"
RFC_CPS_EMPTY = ""


def send_directive_pair(*, cpa: bool = False) -> tuple[str, str]:
    """RFC 3971 Cps / Cpa directive pair."""

    if cpa:
        return "cpa", "message"
    return "cps", "message"


def ascii_serialize_send_directive(*, cpa: bool = False) -> str:
    """RFC 3971 token "=" body-or-cpa."""

    name, value = send_directive_pair(cpa=cpa)
    if not is_token(name):
        raise SendActuationError("illegal_directive")
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
            raise SendActuationError("short_send")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 3971 body-cps token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_send(policy: str | Sequence[str]) -> str:
    """Serialize RFC 3971 CPS / CPA opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise SendActuationError("illegal_send")
    upper = text.upper().replace("_", "-")
    if upper in {"CPS", "SEND", "SEND-CPS", "SEND-CPS"}:
        return "CPS"
    if upper in {"CPA", "RESOURCE", "SEND-CPA"}:
        return "CPA"
    if upper.startswith("CPS="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SendActuationError("illegal_send")
        return "CPS"
    if upper.startswith("CPA="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SendActuationError("illegal_send")
        return "CPA"
    raise SendActuationError("illegal_send")


def parse_send(text: str) -> str:
    """Parse RFC 3971 SEND opcode header extensions into CPS or CPA."""

    raw = str(text or "").strip()
    if not raw:
        raise SendActuationError("illegal_send")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"CPS", "SEND", "SEND-CPS", "SEND-CPS"}:
        return "CPS"
    if upper in {"CPA", "RESOURCE", "SEND-CPA"}:
        return "CPA"
    if upper.startswith("CPS="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SendActuationError("illegal_send")
        return "CPS"
    if upper.startswith("CPA="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise SendActuationError("illegal_send")
        return "CPA"
    raise SendActuationError("illegal_send")


def encode_send_header(policy: str | Sequence[str]) -> bytes:
    """RFC 3971 HTTP/1.0 field as bytes."""

    return serialize_send(policy).encode("ascii")


def parse_send_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_send(field_value) if field_value else DEFAULT_CPS
    return {
        "field_value": field_value,
        "policy": policy,
        "header": CPS_HEADER,
        "directive": str(policy),
        "cps": str(policy) == "CPS",
        "cpa": str(policy) == "CPA",
    }


def canonical_temporary(identity: str, sendid: int) -> str:
    """RFC 3971 body-cps advertisement bound to identity and sendid."""

    return (
        f"{serialize_send(DEFAULT_CPS)}, "
        f"cps={ascii_serialize_send_directive()}, "
        f"identity={identity}, sendid={int(sendid) & 0xFFFFFFFF}"
    )


def canonical_public(identity: str, sendid: int, senddigest: int | None = None) -> str:
    """RFC 3971 cpa-message confirmation of the stored identifier-digest."""

    digest = ""
    if senddigest is not None:
        digest = f", senddigest={int(senddigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_send(CPA_POLICY)}, "
        f"cpa={ascii_serialize_send_directive(cpa=True)}, "
        f"identity={identity}, sendid={int(sendid) & 0xFFFFFFFF}{digest}"
    )


def representation_public(identity: str, sendid: int, senddigest: int) -> str:
    return canonical_public(identity, sendid, senddigest)


def send_matches(left: str, right: str) -> bool:
    return parse_send(left) == parse_send(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise SendActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise SendActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise SendActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise SendActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def temporary_request(identity: str, sendid: int) -> bytes:
    """HTTP CPS that elicits RFC 3971 origin HTTP/1.0."""

    keyid = f"{int(sendid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"CPS /send/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Send-Id: {int(sendid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def public_request(identity: str, sendid: int, senddigest: int | None = None) -> bytes:
    """HTTP CPA carrying RFC 3971 cpa-message confirmation of the stored identifier-digest."""

    keyid = f"{int(sendid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if senddigest is not None:
        extra = f"Send-Digest: {int(senddigest) & 0xFFFFFFFF}\r\n"
    return (
        f"CPA /send/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Send-Id: {int(sendid) & 0xFFFFFFFF}\r\n"
        "Cpa-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    send_kind = "cpa" if fields.get("cpa-confirm") == "1" else "cps"
    upgrade_field = fields.get("cps") or fields.get("send") or ""
    policy = parse_send(upgrade_field) if upgrade_field else ()
    return {
        "kind": "cps",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "send_kind": send_kind,
        "policy": policy,
        "sendid": int(fields["send-id"]) if fields.get("send-id") else EMPTY_SENDID,
        "senddigest": int(fields["send-digest"]) if fields.get("send-digest") else EMPTY_SENDDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def temporary_response(identity: str, sendid: int, senddigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 3971 origin HTTP/1.0, carrying the stored senddigest."""

    publicised = serialize_send(DEFAULT_CPS)
    payload = bytes(body or canonical_temporary(identity, sendid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Cps: {publicised}\r\n"
        f"Send-Id: {int(sendid) & 0xFFFFFFFF}\r\n"
        f"Send-Digest: {int(senddigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def public_response(identity: str, sendid: int, senddigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 3971 CPA, carrying the stored identifier-digest."""

    publicised = serialize_send(CPA_POLICY)
    payload = bytes(body or representation_public(identity, sendid, senddigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Cps: {publicised}\r\n"
        f"Send-Id: {int(sendid) & 0xFFFFFFFF}\r\n"
        f"Send-Digest: {int(senddigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/send-cpa\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise SendActuationError("illegal_content_length") from error
    field_value = fields.get("cps") or fields.get("send") or ""
    policy = parse_send(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/send-cpa" or policy == CPA_POLICY:
        status = 200
        send_kind = "cpa"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        send_kind = "cps"
    else:
        status = 0
        send_kind = "cps"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "send_kind": send_kind,
        "policy": policy,
        "sendid": int(fields["send-id"]) if fields.get("send-id") else EMPTY_SENDID,
        "senddigest": int(fields["send-digest"]) if fields.get("send-digest") else EMPTY_SENDDIGEST,
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
        raise SendActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise SendActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise SendActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise SendActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc3971_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    send: str,
) -> str:
    """RFC 3971 identifier digest over method, router-IP, identity, and sendid."""

    payload = f"{method}:{send}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def temporary_sendid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"sendid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_sendid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-sendid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def temporary_senddigest(sendid: int = EMPTY_SENDID, token: str = SENTINEL) -> int:
    nonce = f"{int(sendid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc3971_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="CPA",
        send=f"/send/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_SENDID = temporary_sendid(SENTINEL)
DEFAULT_SENDDIGEST = temporary_senddigest(DEFAULT_SENDID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    sendid: int,
    senddigest: int,
    include_sendid: bool = True,
) -> bytes:
    live_sendid = int(sendid) & 0xFFFFFFFF if include_sendid else EMPTY_SENDID
    live_digest = int(senddigest) & 0xFFFFFFFF if include_sendid and live_sendid else EMPTY_SENDDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_sendid) if live_sendid else b""
    header = bytearray()
    header.append(SEND_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_temporary(
    *,
    identity: str,
    sendid: int,
    senddigest: int | None = None,
    include_sendid: bool = True,
) -> bytes:
    live_sendid = int(sendid) & 0xFFFFFFFF if include_sendid else EMPTY_SENDID
    live_digest = int(senddigest) if senddigest is not None else temporary_senddigest(live_sendid, identity)
    return encode_packet(
        FRAME_CPS,
        identity=identity,
        sendid=live_sendid,
        senddigest=live_digest,
        include_sendid=include_sendid,
    )


def encode_public(
    *,
    identity: str,
    sendid: int,
    senddigest: int | None = None,
    include_sendid: bool = True,
) -> bytes:
    live_sendid = int(sendid) & 0xFFFFFFFF if include_sendid else EMPTY_SENDID
    live_digest = int(senddigest) if senddigest is not None else temporary_senddigest(live_sendid, identity)
    return encode_packet(
        FRAME_CPA,
        identity=identity,
        sendid=live_sendid,
        senddigest=live_digest,
        include_sendid=include_sendid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise SendActuationError("short_packet")
    first = raw[0]
    if first != SEND_FIRST:
        raise SendActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise SendActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == SENDID_SIZE:
        live_sendid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_sendid = EMPTY_SENDID
    else:
        raise SendActuationError("illegal_sendid")
    if offset >= len(raw):
        raise SendActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_CPS, FRAME_CPA}:
        raise SendActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise SendActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise SendActuationError("checksum_failed")
    if len(payload) < 5:
        raise SendActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise SendActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_sendid = int(live_sendid) != EMPTY_SENDID
    has_senddigest = has_sendid and int(live_digest) != EMPTY_SENDDIGEST
    is_temporary = frame_type == FRAME_CPS
    is_public = frame_type == FRAME_CPA
    return {
        "type": int(frame_type),
        "is_temporary": is_temporary,
        "is_public": is_public,
        "sendid": int(live_sendid),
        "has_sendid": has_sendid,
        "senddigest": int(live_digest),
        "has_senddigest": has_senddigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC3971",
        "serialize_field": canonical_temporary(identity, live_sendid) if has_sendid else "",
        "tls_field": canonical_public(identity, live_sendid, live_digest) if has_senddigest else "",
    }


class SendClient:
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
            raise SendActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_public"] or not packet["is_public"]:
            raise SendActuationError("senddigest_required")
        if not packet["has_sendid"]:
            raise SendActuationError("sendid_required")
        if not packet["has_senddigest"]:
            raise SendActuationError("senddigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_senddigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_senddigest:
            raise SendActuationError("senddigest_required")
        prefix = self._recv()
        return {
            "session": prefix,
            "sendid": int(prefix.get("sendid") or EMPTY_SENDID),
            "identity": str(prefix.get("identity") or ""),
            "senddigest": int(prefix.get("senddigest") or EMPTY_SENDDIGEST),
        }

    def cpa(
        self,
        identity: str,
        sendid: int,
        senddigest: int = EMPTY_SENDDIGEST,
        *,
        wait_senddigest: bool = True,
        include_sendid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_public(
            identity=identity,
            sendid=sendid,
            senddigest=senddigest or temporary_senddigest(sendid, identity),
            include_sendid=include_sendid,
        )
        return self.exchange(packet, wait_senddigest=wait_senddigest)


class SendSession:
    """SENDID-gated loopback RFC 3971 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        sendid_gate: int = DEFAULT_SENDID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sendid_gate = int(sendid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.sendid = EMPTY_SENDID
        self.senddigest = EMPTY_SENDDIGEST
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

    def store_sendid_once(self, identity: str, sendid: int, senddigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(sendid or EMPTY_SENDID)
            live_digest = int(senddigest or EMPTY_SENDDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.sendid = live
                self.senddigest = live_digest or temporary_senddigest(live, name)
                self.stored = True
            return str(self.identity), int(self.sendid), int(self.senddigest)

    def read_sendid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.sendid), int(self.senddigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "sendid": EMPTY_SENDID,
            "senddigest": EMPTY_SENDDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _sendid_missing(self) -> bool:
        return not int(self.sendid_gate or 0)

    def _public_tuple(self, peer: tuple[str, int], identity: str, sendid: int, senddigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_public(
            identity=identity,
            sendid=sendid,
            senddigest=senddigest,
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
            except SendActuationError:
                continue
            if not packet.get("is_temporary") and not packet.get("is_public"):
                continue
            if not packet.get("has_sendid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_sendid, stored_digest = self.store_sendid_once(
                identity,
                int(packet.get("sendid") or EMPTY_SENDID),
                int(packet.get("senddigest") or EMPTY_SENDDIGEST),
            )
            if not stored_name or not stored_sendid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_temporary"):
                    self.opened = True
                if packet.get("is_public"):
                    self.handshook = True
                self.retrieved = True
            self._public_tuple(peer, stored_name, stored_sendid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._sendid_missing():
            return self._forbidden("missing_sendid")
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
        do_temporary: bool = True,
        do_public: bool = True,
        do_senddigest: bool = True,
        replay: bool = True,
        use_sendid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._sendid_missing():
            return self._forbidden("missing_sendid")
        live_token = str(token or SENTINEL)
        origin_sendid = temporary_sendid(live_token)
        origin_digest = temporary_senddigest(origin_sendid, live_token)
        client: SendClient | None = None
        independent: SendClient | None = None
        try:
            client = SendClient(self.host, int(self.port))
            if not do_temporary:
                return self._conflict("temporary_required")
            bind_packet = encode_temporary(
                identity=live_token,
                sendid=origin_sendid,
                senddigest=origin_digest,
                include_sendid=use_sendid,
            )
            if not use_sendid:
                try:
                    client.exchange(bind_packet, wait_senddigest=True)
                except SendActuationError:
                    return self._conflict("sendid_required")
                return self._conflict("sendid_required")
            client.send(bind_packet)
            if not do_public:
                return self._conflict("public_required")
            proxy_packet = encode_public(
                identity=live_token,
                sendid=origin_sendid,
                senddigest=origin_digest,
                include_sendid=True,
            )
            if not do_senddigest:
                try:
                    client.exchange(proxy_packet, wait_senddigest=False)
                except SendActuationError as error:
                    if str(error) == "senddigest_required":
                        return self._conflict("senddigest_required")
                    return self._conflict("senddigest_required")
                return self._conflict("senddigest_required")
            try:
                prefix = client.exchange(proxy_packet, wait_senddigest=True)
            except SendActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("sendid_required")
                if reason == "senddigest_required":
                    return self._conflict("senddigest_required")
                return self._conflict("temporary_required")
            if str(prefix.get("identity") or "") != live_token:
                return self._conflict("temporary_required")
            if int(prefix.get("sendid") or EMPTY_SENDID) != origin_sendid:
                return self._conflict("senddigest_required")
            if int(prefix.get("senddigest") or EMPTY_SENDDIGEST) != origin_digest:
                return self._conflict("senddigest_required")
            self.retrieved = True
            if replay:
                independent = SendClient(self.host, int(self.port))
                try:
                    poll = independent.cpa(
                        POLL_TOKEN,
                        poll_sendid(live_token),
                        temporary_senddigest(poll_sendid(live_token), POLL_TOKEN),
                        wait_senddigest=True,
                    )
                except SendActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_sendid, stored_digest = self.read_sendid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_sendid != origin_sendid
                    or stored_digest != origin_digest
                    or int(poll.get("sendid") or EMPTY_SENDID) != origin_sendid
                    or int(poll.get("senddigest") or EMPTY_SENDDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_sendid}:{origin_digest}:{live_token}:{canonical_temporary(live_token, origin_sendid)}:{canonical_public(live_token, origin_sendid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "sendid": origin_sendid,
                "senddigest": origin_digest,
                "temporary_frame": True,
                "public_frame": True,
                "senddigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "sendid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_senddigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "sendid": origin_sendid,
                "senddigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "temporary_frame": True,
                "public_frame": True,
                "senddigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "sendid_bound": True,
            }
        except (OSError, SendActuationError) as error:
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
        live = independent_senddigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "sendid": int(live.get("sendid") or EMPTY_SENDID),
            "senddigest": int(live.get("senddigest") or EMPTY_SENDDIGEST),
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


def call_send_tool(session: SendSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one send tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_temporary = True if arguments.get("cps") is None else bool(arguments.get("cps"))
    do_public = True if arguments.get("cpa") is None else bool(arguments.get("cpa"))
    do_senddigest = True if arguments.get("senddigest") is None else bool(arguments.get("senddigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_sendid = True if arguments.get("use_sendid") is None else bool(arguments.get("use_sendid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_temporary=do_temporary,
            do_public=do_public,
            do_senddigest=do_senddigest,
            replay=replay,
            use_sendid=use_sendid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SendActuationError(f"unsupported send action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_senddigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage senddigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "sendid": EMPTY_SENDID,
        "senddigest": EMPTY_SENDDIGEST,
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
            "temporary_frame",
            "public_frame",
            "senddigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "sendid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    sendid = int(payload.get("sendid") or EMPTY_SENDID)
    senddigest = int(payload.get("senddigest") or EMPTY_SENDDIGEST)
    dual = port > 0 and bool(sendid) and bool(senddigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "sendid": sendid,
        "senddigest": senddigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "temporary_frame": payload.get("temporary_frame") is True,
        "public_frame": payload.get("public_frame") is True,
        "senddigest_locate": payload.get("senddigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "sendid_bound": payload.get("sendid_bound") is True,
    }


def run_send_workflow(
    *,
    with_sendid: bool = True,
    skip_bind: bool = False,
    do_temporary: bool = True,
    do_public: bool = True,
    do_senddigest: bool = True,
    replay: bool = True,
    use_sendid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 3971 CPS/CPA sendid cycle workflow."""

    descriptor = send_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SEND_TOOL_PROVIDER),
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
        raise SendActuationError(f"send tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="send-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SendSession(out, sendid_gate=DEFAULT_SENDID if with_sendid else EMPTY_SENDID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "cps": do_temporary,
            "cpa": do_public,
            "senddigest": do_senddigest,
            "replay": replay,
            "use_sendid": use_sendid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_send_tool(session, arguments))
            except SendActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_senddigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_sendid
        and not skip_bind
        and do_temporary
        and do_public
        and do_senddigest
        and replay
        and use_sendid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "send_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_sendid": with_sendid,
        "skip_bind": skip_bind,
        "temporary_frame": do_temporary,
        "public_frame": do_public,
        "senddigest": do_senddigest,
        "replay": replay,
        "use_sendid": use_sendid,
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
        "sendid_value": int(publish_result.get("sendid") or independent.get("sendid") or EMPTY_SENDID),
        "senddigest_value": int(publish_result.get("senddigest") or independent.get("senddigest") or EMPTY_SENDDIGEST),
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
        "sendid": int(trace_body["sendid_value"] or EMPTY_SENDID),
        "senddigest": int(trace_body["senddigest_value"] or EMPTY_SENDDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_sendid": with_sendid,
        "skip_bind": skip_bind,
        "temporary_cycle": do_temporary,
        "public_cycle": do_public,
        "senddigest_cycle": do_senddigest,
        "replay": replay,
        "use_sendid": use_sendid,
    }


def verify_send_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_senddigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    sendid = int(trace.get("sendid_value") or independent.get("sendid") or EMPTY_SENDID)
    senddigest = int(trace.get("senddigest_value") or independent.get("senddigest") or EMPTY_SENDDIGEST)
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
        "temporary_frame": independent.get("temporary_frame") is True,
        "public_frame": independent.get("public_frame") is True,
        "senddigest_locate": independent.get("senddigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "sendid_bound": independent.get("sendid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "senddigest_recorded": (
            port > 0
            and sendid == DEFAULT_SENDID
            and senddigest == DEFAULT_SENDDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def send_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.send_actuation import "
        "builtin_send_actuation_proof; r=builtin_send_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='send_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_send_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SEND_ACTUATION_ID,
        name="First-class RFC 3971 SEcure Neighbor Discovery CPS/CPA actuation",
        description=(
            "Missions that require an send tool can opt the send provider in, "
            "bind a loopback RFC 3971 SEcure Neighbor Discovery endpoint, complete a CPS "
            "with a non-empty sendid, lockstep a CPA that carries the "
            "stored senddigest, independently poll the stored senddigest "
            "on a later socket, and seal a digest-chained senddigest. Default "
            "routing stays fail-closed; a missing sendid keeps the hole "
            "falsifiable, and skip-CPS/CPA/SENDDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.send_actuation:builtin_send_actuation_proof",
        proof_command=send_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.cga-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/send_actuation.py",
            "src/blackhole_agent/cga_actuation.py",
            "src/blackhole_agent/opaqueiid_actuation.py",
            "src/blackhole_agent/tempaddr_actuation.py",
            "src/blackhole_agent/slaac_actuation.py",
            "src/blackhole_agent/ndp_actuation.py",
            "src/blackhole_agent/mld_actuation.py",
            "src/blackhole_agent/igmp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/rarp_actuation.py",
            "src/blackhole_agent/arp_actuation.py",
            "src/blackhole_agent/ip_actuation.py",
            "src/blackhole_agent/icmp_actuation.py",
            "src/blackhole_agent/ula_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required send tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 3971 daemon, speaks a "
            "CPS then CPA over SEcure Neighbor Discovery with a non-empty sendid and "
            "senddigest, independently polls the stored senddigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 3972 Cryptographically Generated Addresses lockstep is proved. "
            "Missing sendids, skip-CPS, skip-CPA, skip-senddigest, skip-REPLAY, "
            "and a CPS aimed without a sendid stay fail-closed. "
            "Later genesis can take RFC 4193 Unique Local IPv6 Unicast Addresses UNIQUE/LOCAL as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("send", "rfc3971", "http", "sendid", "senddigest", "cps", "cpa", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T210554Z-69f7a6ef",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_send_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 3971 cps/cpa lockstep actuation seals an senddigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.slaac_actuation import (
        SLAAC_ACTUATION_GOAL,
        SLAAC_ACTUATION_ID,
    )
    from blackhole_agent.ula_actuation import (
        ULA_ACTUATION_GOAL,
        ULA_ACTUATION_ID,
    )
    from blackhole_agent.ipv6addr_actuation import (
        IPV6ADDR_ACTUATION_GOAL,
        IPV6ADDR_ACTUATION_ID,
    )
    from blackhole_agent.ipv6scope_actuation import (
        IPV6SCOPE_ACTUATION_GOAL,
        IPV6SCOPE_ACTUATION_ID,
    )
    from blackhole_agent.addrselect_actuation import (
        ADDRSELECT_ACTUATION_GOAL,
        ADDRSELECT_ACTUATION_ID,
    )
    from blackhole_agent.addrpolicy_actuation import (
        ADDRPOLICY_ACTUATION_GOAL,
        ADDRPOLICY_ACTUATION_ID,
    )
    from blackhole_agent.cga_actuation import (
        CGA_ACTUATION_GOAL,
        CGA_ACTUATION_ID,
    )
    from blackhole_agent.opaqueiid_actuation import (
        OPAQUEIID_ACTUATION_GOAL,
        OPAQUEIID_ACTUATION_ID,
    )
    from blackhole_agent.tempaddr_actuation import (
        TEMPADDR_ACTUATION_GOAL,
        TEMPADDR_ACTUATION_ID,
    )
    from blackhole_agent.ndp_actuation import (
        NDP_ACTUATION_GOAL,
        NDP_ACTUATION_ID,
    )
    from blackhole_agent.mld_actuation import (
        MLD_ACTUATION_GOAL,
        MLD_ACTUATION_ID,
    )
    from blackhole_agent.igmp_actuation import (
        IGMP_ACTUATION_GOAL,
        IGMP_ACTUATION_ID,
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
    checks["denylists_self"] = SEND_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SEND_ACTUATION_GOAL) == (
        SEND_ACTUATION_ID,
    )
    checks["leftover_text_binds_send"] = leftover_marker_ids(SEND_LEFTOVER) == (
        SEND_ACTUATION_ID,
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
        (ULA_ACTUATION_GOAL, ULA_ACTUATION_ID, "ula"),
        (IPV6SCOPE_ACTUATION_GOAL, IPV6SCOPE_ACTUATION_ID, "ipv6scope"),
        (ADDRSELECT_ACTUATION_GOAL, ADDRSELECT_ACTUATION_ID, "addrselect"),
        (ADDRPOLICY_ACTUATION_GOAL, ADDRPOLICY_ACTUATION_ID, "addrpolicy"),
        (IPV6ADDR_ACTUATION_GOAL, IPV6ADDR_ACTUATION_ID, "ipv6addr"),
        (CGA_ACTUATION_GOAL, CGA_ACTUATION_ID, "cga"),
        (OPAQUEIID_ACTUATION_GOAL, OPAQUEIID_ACTUATION_ID, "opaqueiid"),
        (TEMPADDR_ACTUATION_GOAL, TEMPADDR_ACTUATION_ID, "tempaddr"),
        (SLAAC_ACTUATION_GOAL, SLAAC_ACTUATION_ID, "slaac"),
        (NDP_ACTUATION_GOAL, NDP_ACTUATION_ID, "ndp"),
        (MLD_ACTUATION_GOAL, MLD_ACTUATION_ID, "mld"),
        (IGMP_ACTUATION_GOAL, IGMP_ACTUATION_ID, "igmp"),
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
        checks[f"{name}_goal_is_not_send"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"send_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            SEND_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = SEND_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    publicised = serialize_send(DEFAULT_CPS)
    rebuilt = serialize_send(parse_send(publicised))
    preloaded = parse_send(RFC_SEND_CPA)
    header = encode_send_header(DEFAULT_CPS)
    parsed_header = parse_send_header(header)
    asked = parse_http_request(temporary_request(SENTINEL, DEFAULT_SENDID))
    preload_req = parse_http_request(public_request(SENTINEL, DEFAULT_SENDID, DEFAULT_SENDDIGEST))
    got = parse_http_response(temporary_response(SENTINEL, DEFAULT_SENDID, DEFAULT_SENDDIGEST))
    preload_public = parse_http_response(
        public_response(SENTINEL, DEFAULT_SENDID, DEFAULT_SENDDIGEST)
    )
    checks["send_roundtrip"] = (
        parse_send(publicised) == DEFAULT_CPS
        and hmac.compare_digest(rebuilt, publicised)
        and publicised == RFC_CPS_FIELD
        and is_token("CPS") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_CPS_FIELD
        and parsed_header["policy"] == DEFAULT_CPS
        and parsed_header["header"] == CPS_HEADER
        and parsed_header["cps"] is True
        and parsed_header["cpa"] is False
        and preloaded == CPA_POLICY
        and ascii_serialize_send_directive() == RFC_CPS_DIRECTIVE
        and send_directive_pair() == ("cps", "message")
        and RFC_CPS_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_send(CPA_POLICY) == RFC_SEND_CPA
        and DEFAULT_SENDDIGEST == temporary_senddigest(DEFAULT_SENDID, SENTINEL)
        and "senddigest=" in canonical_public(SENTINEL, DEFAULT_SENDID, DEFAULT_SENDDIGEST)
        and canonical_temporary(SENTINEL, DEFAULT_SENDID).startswith("CPS")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "CPS"
        and asked["send_kind"] == "cps"
        and asked["sendid"] == DEFAULT_SENDID
        and preload_req["send_kind"] == "cpa"
        and preload_req["senddigest"] == DEFAULT_SENDDIGEST
        and got["status"] == 200
        and preload_public["status"] == 200
        and got["send_kind"] == "cps"
        and preload_public["send_kind"] == "cpa"
        and got["policy"] == DEFAULT_CPS
        and preload_public["policy"] == CPA_POLICY
        and got["content_length_matches_body"] is True
        and preload_public["content_length_matches_body"] is True
        and got["senddigest"] == DEFAULT_SENDDIGEST
        and preload_public["senddigest"] == DEFAULT_SENDDIGEST
        and send_matches(serialize_send(got["policy"]), publicised)
    )

    checks["catalog_names_send"] = (
        len(catalog) > 125
        and catalog[125]["id"] == SEND_ACTUATION_ID
        and catalog[124]["id"] == CGA_ACTUATION_ID
        and catalog[123]["id"] == OPAQUEIID_ACTUATION_ID
        and catalog[125]["source"] == "genesis_bind_send"
    )
    checks["catalog_names_ula"] = (
        len(catalog) > 126
        and catalog[126]["id"] == ULA_ACTUATION_ID
        and catalog[126]["source"] == "genesis_bind_ula"
    )
    checks["catalog_names_ipv6addr"] = (
        len(catalog) > 127
        and catalog[127]["id"] == IPV6ADDR_ACTUATION_ID
        and catalog[127]["source"] == "genesis_bind_ipv6addr"
    )
    checks["catalog_names_ipv6scope"] = (
        len(catalog) > 128
        and catalog[128]["id"] == IPV6SCOPE_ACTUATION_ID
        and catalog[128]["source"] == "genesis_bind_ipv6scope"
    )
    checks["catalog_names_addrselect"] = (
        len(catalog) > 129
        and catalog[129]["id"] == ADDRSELECT_ACTUATION_ID
        and catalog[129]["source"] == "genesis_bind_addrselect"
    )
    checks["catalog_names_addrpolicy"] = (
        len(catalog) > 130
        and catalog[130]["id"] == ADDRPOLICY_ACTUATION_ID
        and catalog[130]["source"] == "genesis_bind_addrpolicy"
    )
    family = capability_family(SEND_ACTUATION_GOAL)
    checks["family_is_send"] = "send" in family.split("/")
    checks["family_is_send_surface"] = "sendid" in family
    checks["family_is_sendid"] = "sendid" in family
    checks["family_is_rfc3971"] = "rfc3971" in family
    checks["family_is_senddigest"] = "senddigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_slaac"] = (
        "slaac" not in family.split("/")
        and "rfc4862" not in family
        and "slaacid" not in family
        and "slaacdigest" not in family
    )
    checks["family_is_not_ula"] = (
        "ula" not in family.split("/")
        and "rfc4193" not in family
        and "ulaid" not in family
        and "uladigest" not in family
    )
    checks["family_is_not_ipv6addr"] = (
        "ipv6addr" not in family.split("/")
        and "rfc4291" not in family
        and "ipv6addrid" not in family
        and "ipv6addrdigest" not in family
    )
    checks["family_is_not_ipv6scope"] = (
        "ipv6scope" not in family.split("/")
        and "rfc4007" not in family
        and "scopeid" not in family
        and "scopedigest" not in family
    )
    checks["family_is_not_addrselect"] = (
        "addrselect" not in family.split("/")
        and "rfc6724" not in family
        and "selectid" not in family
        and "selectdigest" not in family
    )
    checks["family_is_not_addrpolicy"] = (
        "addrpolicy" not in family.split("/")
        and "rfc7078" not in family
        and "policyid" not in family
        and "policydigest" not in family
    )
    checks["family_is_not_cga"] = (
        "cga" not in family.split("/")
        and "rfc3972" not in family
        and "cgaid" not in family
        and "cgadigest" not in family
    )
    checks["family_is_not_opaqueiid"] = (
        "opaqueiid" not in family.split("/")
        and "rfc7217" not in family
        and "opaqueid" not in family
        and "opaquedigest" not in family
    )
    checks["family_is_not_tempaddr"] = (
        "tempaddr" not in family.split("/")
        and "rfc4941" not in family
        and "tempaddrid" not in family
        and "tempaddrdigest" not in family
    )
    checks["family_is_not_ndp"] = (
        "ndp" not in family.split("/")
        and "rfc4861" not in family
        and "ndpid" not in family
        and "ndpdigest" not in family
    )
    checks["family_is_not_mld"] = (
        "mld" not in family.split("/")
        and "rfc2710" not in family
        and "mldid" not in family
        and "mlddigest" not in family
    )
    checks["family_is_not_igmp"] = (
        "igmp" not in family.split("/")
        and "rfc1112" not in family
        and "igmpid" not in family
        and "igmpdigest" not in family
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
    packed = encode_temporary(identity=SENTINEL, sendid=DEFAULT_SENDID, senddigest=DEFAULT_SENDDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_temporary"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_sendid"] is True
        and parsed["sendid"] == DEFAULT_SENDID
        and parsed["senddigest"] == DEFAULT_SENDDIGEST
        and parsed["is_public"] is False
        and parsed["is_public"] is False
        and parsed["type"] == FRAME_CPS
        and parsed["first_byte"] == SEND_FIRST
    )
    shook = encode_public(
        identity=SENTINEL,
        sendid=DEFAULT_SENDID,
        senddigest=DEFAULT_SENDDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_public"] is True
        and answer_parsed["is_public"] is True
        and answer_parsed["is_temporary"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["sendid"] == DEFAULT_SENDID
        and answer_parsed["senddigest"] == DEFAULT_SENDDIGEST
        and answer_parsed["has_senddigest"] is True
        and answer_parsed["type"] == FRAME_CPA
        and answer_parsed["first_byte"] == SEND_FIRST
    )
    bare = encode_temporary(identity=SENTINEL, sendid=DEFAULT_SENDID, include_sendid=False)
    checks["missing_sendid_is_unauthed"] = parse_message(bare)["has_sendid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(SEND_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_send = ToolDescriptor(name="remote_send", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_send)
    checks["naive_mcp_send_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = send_tool_descriptor()
    default_send = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SEND_TOOL_PROVIDER),
    )
    checks["default_send_provider_is_unsupported"] = (
        default_send.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SEND_TOOL_PROVIDER}" in default_send.reasons
    )
    checks["opted_in_send_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_send],
        required_tool_names=("local_memory", "send"),
    )
    checks["naive_preflight_missing_send"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["send"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "send"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SEND_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "send" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="send-actuation-") as tmp:
        root = Path(tmp)
        missing = run_send_workflow(with_sendid=False, output_dir=root / "missing")
        skip_bind = run_send_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_temporary = run_send_workflow(do_temporary=False, output_dir=root / "skip-cps")
        skip_public = run_send_workflow(do_public=False, output_dir=root / "skip-cpa")
        skip_senddigest = run_send_workflow(do_senddigest=False, output_dir=root / "skip-senddigest")
        skip_replay = run_send_workflow(replay=False, output_dir=root / "skip-replay")
        skip_sendid = run_send_workflow(use_sendid=False, output_dir=root / "sksend-sendid")
        live = run_send_workflow(output_dir=root / "live")
        cpa = verify_send_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_send_trace(clone)
        checks["naive_without_sendid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_sendid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_temporary_stays_empty"] = (
            skip_temporary["ok"] is False
            and skip_temporary["error"] == "temporary_required"
            and skip_temporary["final_status"] == 409
            and skip_temporary["payload_exists"] is False
        )
        checks["skip_public_stays_empty"] = (
            skip_public["ok"] is False
            and skip_public["error"] == "public_required"
            and skip_public["final_status"] == 409
            and skip_public["payload_exists"] is False
        )
        checks["skip_senddigest_stays_empty"] = (
            skip_senddigest["ok"] is False
            and skip_senddigest["error"] == "senddigest_required"
            and skip_senddigest["final_status"] == 409
            and skip_senddigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_sendid_stays_empty"] = (
            skip_sendid["ok"] is False
            and skip_sendid["error"] == "sendid_required"
            and skip_sendid["final_status"] == 409
            and skip_sendid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_senddigest"] = (
            int(live.get("sendid") or 0) == DEFAULT_SENDID
            and int(live.get("senddigest") or 0) == DEFAULT_SENDDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_sendid_encode_public_senddigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_temporary["ok"] is False
            and skip_public["ok"] is False
            and skip_senddigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_sendid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = cpa["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="send-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SEND_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_send"] = (
        live_goal == SEND_ACTUATION_GOAL
        and SEND_ACTUATION_ID in live_done
        and live_source == "genesis_bind_send"
    )

    with tempfile.TemporaryDirectory(prefix="send-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(SEND_LEFTOVER, root)
        register_catalog_proved(root, SEND_ACTUATION_ID)
        reason = leftover_satisfied_by(SEND_LEFTOVER, root)
        after = leftover_is_open(SEND_LEFTOVER, root)
    checks["send_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_send_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{SEND_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_send_actuation_capability()
    return {
        "ok": ok,
        "action": "send_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SEND_ACTUATION_GOAL,
        "done_when": SEND_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
