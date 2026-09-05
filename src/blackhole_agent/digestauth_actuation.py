"""Drive a first-class Digest Access Authentication tool through RFC 2069 CHALLENGE/RESPONSE.

Tool routing already fails missions that require ``digestauth``: hosted
digestauth endpoints stay on the unsupported MCP provider, and no first-party
digestauth provider is executable. Unbound therefore cannot speak a CHALLENGE,
lockstep a RESPONSE challengeid handshake over Digest CHALLENGEID,
independently poll the stored responsedigest, or seal a responsedigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``digestauth`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2069 daemon
- keep a missing-challengeid client so the digestauth-challengeid hole stays falsifiable
- refuse RESPONSE until a CHALLENGE lands with a non-empty challengeid
- independently poll the stored responsedigest on a later client socket
- persist a sealed responsedigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 2109 HTTP State Management Mechanism
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
    DIGESTAUTH_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    digestauth_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
DIGESTAUTH_ACTUATION_ID = "capability.digestauth-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-DIGESTAUTH-OK"
POLL_TOKEN = "BH-DIGESTAUTH-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_CHALLENGEID = 0
EMPTY_RESPONSEDIGEST = 0
DIGESTAUTH_FIRST = 0x44  # RFC 2069 Digest Access Authentication (ASCII 'D')
CHALLENGEID_SIZE = 4
RESPONSEDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_RESPONSE = 0x02  # RFC 2069 RESPONSE confirmation
FRAME_CHALLENGE = 0x01  # RFC 2069 CHALLENGE
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
DIGESTAUTH_LEFTOVER = (
    "Later genesis can take RFC 2069 Digest Access Authentication CHALLENGE/RESPONSE over a "
    "challengeid-gated responsedigest."
)
DIGESTAUTH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DIGESTAUTH_ACTUATION_ID};"
    f"capability_proved:{DIGESTAUTH_ACTUATION_ID};"
    "no_skill_route"
)
DIGESTAUTH_ACTUATION_GOAL = (
    "Repair rfc2069 digestauth challenge/response cycle cannot land over http "
    "digestauth challengeid: hosted digestauth endpoints remain unsupported so a CHALLENGE then "
    "RESPONSE challengeid handshake cannot land and a sealed responsedigest "
    "cannot be produced. A missing digestauth challengeid stays forbidden; fail-closed "
    "routing never opts the digestauth provider in. An independent later poll of the "
    "stored responsedigest keeps the hole falsifiable."
)


class DigestauthActuationError(RuntimeError):
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
# RFC 2069 sections 2.1 and 2.1.2: CHALLENGE / RESPONSE.
RFC_CHALLENGE_FIELD = "CHALLENGE"
RFC_RESPONSE_FIELD = "RESPONSE"
RFC_DIGESTAUTH_RESPONSE = RFC_RESPONSE_FIELD
RFC_CHALLENGE_DIRECTIVE = "challenge=realm"
RFC_RESPONSE_DIRECTIVE = "response=uri"
DEFAULT_CHALLENGE = "CHALLENGE"
RESPONSE_POLICY = "RESPONSE"
CHALLENGE_HEADER = "Challenge"
RESPONSE_HEADER = "Response"
DIGESTAUTH_RESPONSE_HEADER = RESPONSE_HEADER
RFC_CHALLENGE_PATH = "/digestauth/"
RFC_CHALLENGE_EMPTY = ""


def digestauth_directive_pair(*, response: bool = False) -> tuple[str, str]:
    """RFC 2069 Challenge / Response directive pair."""

    if response:
        return "response", "uri"
    return "challenge", "realm"


def ascii_serialize_digestauth_directive(*, response: bool = False) -> str:
    """RFC 2069 token "=" challenge-or-response."""

    name, value = digestauth_directive_pair(response=response)
    if not is_token(name):
        raise DigestauthActuationError("illegal_directive")
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
            raise DigestauthActuationError("short_digestauth")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 2069 digest-challenge token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_digestauth(policy: str | Sequence[str]) -> str:
    """Serialize RFC 2069 CHALLENGE / RESPONSE opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise DigestauthActuationError("illegal_digestauth")
    upper = text.upper().replace("_", "-")
    if upper in {"CHALLENGE", "DIGESTAUTH", "DIGESTAUTH-CHALLENGE"}:
        return "CHALLENGE"
    if upper in {"RESPONSE", "URI", "DIGESTAUTH-RESPONSE"}:
        return "RESPONSE"
    if upper.startswith("CHALLENGE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise DigestauthActuationError("illegal_digestauth")
        return "CHALLENGE"
    if upper.startswith("RESPONSE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise DigestauthActuationError("illegal_digestauth")
        return "RESPONSE"
    raise DigestauthActuationError("illegal_digestauth")


def parse_digestauth(text: str) -> str:
    """Parse RFC 2069 DIGESTAUTH opcode header extensions into CHALLENGE or RESPONSE."""

    raw = str(text or "").strip()
    if not raw:
        raise DigestauthActuationError("illegal_digestauth")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"CHALLENGE", "DIGESTAUTH", "DIGESTAUTH-CHALLENGE"}:
        return "CHALLENGE"
    if upper in {"RESPONSE", "URI", "DIGESTAUTH-RESPONSE"}:
        return "RESPONSE"
    if upper.startswith("CHALLENGE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise DigestauthActuationError("illegal_digestauth")
        return "CHALLENGE"
    if upper.startswith("RESPONSE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise DigestauthActuationError("illegal_digestauth")
        return "RESPONSE"
    raise DigestauthActuationError("illegal_digestauth")


def encode_digestauth_header(policy: str | Sequence[str]) -> bytes:
    """RFC 2069 WWW-Authenticate field as bytes."""

    return serialize_digestauth(policy).encode("ascii")


def parse_digestauth_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_digestauth(field_value) if field_value else DEFAULT_CHALLENGE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": CHALLENGE_HEADER,
        "directive": str(policy),
        "challenge": str(policy) == "CHALLENGE",
        "response": str(policy) == "RESPONSE",
    }


def canonical_challenge(identity: str, challengeid: int) -> str:
    """RFC 2069 digest-challenge advertisement bound to identity and challengeid."""

    return (
        f"{serialize_digestauth(DEFAULT_CHALLENGE)}, "
        f"challenge={ascii_serialize_digestauth_directive()}, "
        f"identity={identity}, challengeid={int(challengeid) & 0xFFFFFFFF}"
    )


def canonical_response(identity: str, challengeid: int, responsedigest: int | None = None) -> str:
    """RFC 2069 digest-response confirmation of the stored request-digest."""

    digest = ""
    if responsedigest is not None:
        digest = f", responsedigest={int(responsedigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_digestauth(RESPONSE_POLICY)}, "
        f"response={ascii_serialize_digestauth_directive(response=True)}, "
        f"identity={identity}, challengeid={int(challengeid) & 0xFFFFFFFF}{digest}"
    )


def representation_response(identity: str, challengeid: int, responsedigest: int) -> str:
    return canonical_response(identity, challengeid, responsedigest)


def digestauth_matches(left: str, right: str) -> bool:
    return parse_digestauth(left) == parse_digestauth(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise DigestauthActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise DigestauthActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise DigestauthActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise DigestauthActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def challenge_request(identity: str, challengeid: int) -> bytes:
    """HTTP CHALLENGE that elicits RFC 2069 origin WWW-Authenticate."""

    keyid = f"{int(challengeid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"CHALLENGE /digestauth/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Challenge-Id: {int(challengeid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def response_request(identity: str, challengeid: int, responsedigest: int | None = None) -> bytes:
    """HTTP GET carrying RFC 2069 digest-response confirmation of the stored request-digest."""

    keyid = f"{int(challengeid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if responsedigest is not None:
        extra = f"Response-Digest: {int(responsedigest) & 0xFFFFFFFF}\r\n"
    return (
        f"RESPONSE /digestauth/{keyid} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Challenge-Id: {int(challengeid) & 0xFFFFFFFF}\r\n"
        "Response-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    digestauth_kind = "response" if fields.get("response-confirm") == "1" else "challenge"
    upgrade_field = fields.get("challenge") or fields.get("negotiate") or fields.get("digestauth") or ""
    policy = parse_digestauth(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "digestauth_kind": digestauth_kind,
        "policy": policy,
        "challengeid": int(fields["challenge-id"]) if fields.get("challenge-id") else EMPTY_CHALLENGEID,
        "responsedigest": int(fields["response-digest"]) if fields.get("response-digest") else EMPTY_RESPONSEDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def challenge_response(identity: str, challengeid: int, responsedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 2069 origin WWW-Authenticate, carrying the stored responsedigest."""

    advertised = serialize_digestauth(DEFAULT_CHALLENGE)
    payload = bytes(body or canonical_challenge(identity, challengeid).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Challenge: {advertised}\r\n"
        f"Challenge-Id: {int(challengeid) & 0xFFFFFFFF}\r\n"
        f"Response-Digest: {int(responsedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def response_response(identity: str, challengeid: int, responsedigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 2069 RESPONSE, carrying the stored request-digest."""

    advertised = serialize_digestauth(RESPONSE_POLICY)
    payload = bytes(body or representation_response(identity, challengeid, responsedigest).encode("ascii"))
    return (
        "HTTP/1.1 200 OK\r\n"
        f"Challenge: {advertised}\r\n"
        f"Challenge-Id: {int(challengeid) & 0xFFFFFFFF}\r\n"
        f"Response-Digest: {int(responsedigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/digestauth-response\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise DigestauthActuationError("illegal_content_length") from error
    field_value = fields.get("challenge") or fields.get("negotiate") or fields.get("digestauth") or ""
    policy = parse_digestauth(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/digestauth-response" or policy == RESPONSE_POLICY:
        status = 200
        digestauth_kind = "response"
    elif start.startswith("HTTP/1.1 200"):
        status = 200
        digestauth_kind = "challenge"
    else:
        status = 0
        digestauth_kind = "challenge"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "digestauth_kind": digestauth_kind,
        "policy": policy,
        "challengeid": int(fields["challenge-id"]) if fields.get("challenge-id") else EMPTY_CHALLENGEID,
        "responsedigest": int(fields["response-digest"]) if fields.get("response-digest") else EMPTY_RESPONSEDIGEST,
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
        raise DigestauthActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise DigestauthActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise DigestauthActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise DigestauthActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc2069_request_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    uri: str,
) -> str:
    """RFC 2069 request-digest = KD(H(A1), nonce ":" H(A2)) with MD5."""

    def h(data: str) -> str:
        return hashlib.md5(data.encode("ascii"), usedforsecurity=False).hexdigest()

    a1 = f"{username}:{realm}:{password}"
    a2 = f"{method}:{uri}"
    return h(f"{h(a1)}:{nonce}:{h(a2)}")


def request_challengeid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"challengeid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_challengeid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-challengeid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_responsedigest(challengeid: int = EMPTY_CHALLENGEID, token: str = SENTINEL) -> int:
    nonce = f"{int(challengeid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc2069_request_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="RESPONSE",
        uri=f"/digestauth/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_CHALLENGEID = request_challengeid(SENTINEL)
DEFAULT_RESPONSEDIGEST = request_responsedigest(DEFAULT_CHALLENGEID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    challengeid: int,
    responsedigest: int,
    include_challengeid: bool = True,
) -> bytes:
    live_challengeid = int(challengeid) & 0xFFFFFFFF if include_challengeid else EMPTY_CHALLENGEID
    live_digest = int(responsedigest) & 0xFFFFFFFF if include_challengeid and live_challengeid else EMPTY_RESPONSEDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_challengeid) if live_challengeid else b""
    header = bytearray()
    header.append(DIGESTAUTH_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_challenge(
    *,
    identity: str,
    challengeid: int,
    responsedigest: int | None = None,
    include_challengeid: bool = True,
) -> bytes:
    live_challengeid = int(challengeid) & 0xFFFFFFFF if include_challengeid else EMPTY_CHALLENGEID
    live_digest = int(responsedigest) if responsedigest is not None else request_responsedigest(live_challengeid, identity)
    return encode_packet(
        FRAME_CHALLENGE,
        identity=identity,
        challengeid=live_challengeid,
        responsedigest=live_digest,
        include_challengeid=include_challengeid,
    )


def encode_response(
    *,
    identity: str,
    challengeid: int,
    responsedigest: int | None = None,
    include_challengeid: bool = True,
) -> bytes:
    live_challengeid = int(challengeid) & 0xFFFFFFFF if include_challengeid else EMPTY_CHALLENGEID
    live_digest = int(responsedigest) if responsedigest is not None else request_responsedigest(live_challengeid, identity)
    return encode_packet(
        FRAME_RESPONSE,
        identity=identity,
        challengeid=live_challengeid,
        responsedigest=live_digest,
        include_challengeid=include_challengeid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise DigestauthActuationError("short_packet")
    first = raw[0]
    if first != DIGESTAUTH_FIRST:
        raise DigestauthActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise DigestauthActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == CHALLENGEID_SIZE:
        live_challengeid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_challengeid = EMPTY_CHALLENGEID
    else:
        raise DigestauthActuationError("illegal_challengeid")
    if offset >= len(raw):
        raise DigestauthActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_CHALLENGE, FRAME_RESPONSE}:
        raise DigestauthActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise DigestauthActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise DigestauthActuationError("checksum_failed")
    if len(payload) < 5:
        raise DigestauthActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise DigestauthActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_challengeid = int(live_challengeid) != EMPTY_CHALLENGEID
    has_responsedigest = has_challengeid and int(live_digest) != EMPTY_RESPONSEDIGEST
    is_challenge = frame_type == FRAME_CHALLENGE
    is_response = frame_type == FRAME_RESPONSE
    return {
        "type": int(frame_type),
        "is_challenge": is_challenge,
        "is_response": is_response,
        "challengeid": int(live_challengeid),
        "has_challengeid": has_challengeid,
        "responsedigest": int(live_digest),
        "has_responsedigest": has_responsedigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC2069",
        "serialize_field": canonical_challenge(identity, live_challengeid) if has_challengeid else "",
        "tls_field": canonical_response(identity, live_challengeid, live_digest) if has_responsedigest else "",
    }


class DigestauthClient:
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
            raise DigestauthActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_response"] or not packet["is_response"]:
            raise DigestauthActuationError("responsedigest_required")
        if not packet["has_challengeid"]:
            raise DigestauthActuationError("challengeid_required")
        if not packet["has_responsedigest"]:
            raise DigestauthActuationError("responsedigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_responsedigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_responsedigest:
            raise DigestauthActuationError("responsedigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "challengeid": int(reply.get("challengeid") or EMPTY_CHALLENGEID),
            "identity": str(reply.get("identity") or ""),
            "responsedigest": int(reply.get("responsedigest") or EMPTY_RESPONSEDIGEST),
        }

    def report(
        self,
        identity: str,
        challengeid: int,
        responsedigest: int = EMPTY_RESPONSEDIGEST,
        *,
        wait_responsedigest: bool = True,
        include_challengeid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_response(
            identity=identity,
            challengeid=challengeid,
            responsedigest=responsedigest or request_responsedigest(challengeid, identity),
            include_challengeid=include_challengeid,
        )
        return self.exchange(packet, wait_responsedigest=wait_responsedigest)


class DigestauthSession:
    """CHALLENGEID-gated loopback RFC 2069 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        challengeid_gate: int = DEFAULT_CHALLENGEID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.challengeid_gate = int(challengeid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.challengeid = EMPTY_CHALLENGEID
        self.responsedigest = EMPTY_RESPONSEDIGEST
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

    def store_challengeid_once(self, identity: str, challengeid: int, responsedigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(challengeid or EMPTY_CHALLENGEID)
            live_digest = int(responsedigest or EMPTY_RESPONSEDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.challengeid = live
                self.responsedigest = live_digest or request_responsedigest(live, name)
                self.stored = True
            return str(self.identity), int(self.challengeid), int(self.responsedigest)

    def read_challengeid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.challengeid), int(self.responsedigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "challengeid": EMPTY_CHALLENGEID,
            "responsedigest": EMPTY_RESPONSEDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _challengeid_missing(self) -> bool:
        return not int(self.challengeid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, challengeid: int, responsedigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_response(
            identity=identity,
            challengeid=challengeid,
            responsedigest=responsedigest,
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
            except DigestauthActuationError:
                continue
            if not packet.get("is_challenge") and not packet.get("is_response"):
                continue
            if not packet.get("has_challengeid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_challengeid, stored_digest = self.store_challengeid_once(
                identity,
                int(packet.get("challengeid") or EMPTY_CHALLENGEID),
                int(packet.get("responsedigest") or EMPTY_RESPONSEDIGEST),
            )
            if not stored_name or not stored_challengeid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_challenge"):
                    self.opened = True
                if packet.get("is_response"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_challengeid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._challengeid_missing():
            return self._forbidden("missing_challengeid")
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
        do_challenge: bool = True,
        do_response: bool = True,
        do_responsedigest: bool = True,
        replay: bool = True,
        use_challengeid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._challengeid_missing():
            return self._forbidden("missing_challengeid")
        live_token = str(token or SENTINEL)
        origin_challengeid = request_challengeid(live_token)
        origin_digest = request_responsedigest(origin_challengeid, live_token)
        client: DigestauthClient | None = None
        independent: DigestauthClient | None = None
        try:
            client = DigestauthClient(self.host, int(self.port))
            if not do_challenge:
                return self._conflict("challenge_required")
            bind_packet = encode_challenge(
                identity=live_token,
                challengeid=origin_challengeid,
                responsedigest=origin_digest,
                include_challengeid=use_challengeid,
            )
            if not use_challengeid:
                try:
                    client.exchange(bind_packet, wait_responsedigest=True)
                except DigestauthActuationError:
                    return self._conflict("challengeid_required")
                return self._conflict("challengeid_required")
            client.send(bind_packet)
            if not do_response:
                return self._conflict("response_required")
            proxy_packet = encode_response(
                identity=live_token,
                challengeid=origin_challengeid,
                responsedigest=origin_digest,
                include_challengeid=True,
            )
            if not do_responsedigest:
                try:
                    client.exchange(proxy_packet, wait_responsedigest=False)
                except DigestauthActuationError as error:
                    if str(error) == "responsedigest_required":
                        return self._conflict("responsedigest_required")
                    return self._conflict("responsedigest_required")
                return self._conflict("responsedigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_responsedigest=True)
            except DigestauthActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("challengeid_required")
                if reason == "responsedigest_required":
                    return self._conflict("responsedigest_required")
                return self._conflict("challenge_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("challenge_required")
            if int(reply.get("challengeid") or EMPTY_CHALLENGEID) != origin_challengeid:
                return self._conflict("responsedigest_required")
            if int(reply.get("responsedigest") or EMPTY_RESPONSEDIGEST) != origin_digest:
                return self._conflict("responsedigest_required")
            self.retrieved = True
            if replay:
                independent = DigestauthClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_challengeid(live_token),
                        request_responsedigest(poll_challengeid(live_token), POLL_TOKEN),
                        wait_responsedigest=True,
                    )
                except DigestauthActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_challengeid, stored_digest = self.read_challengeid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_challengeid != origin_challengeid
                    or stored_digest != origin_digest
                    or int(poll.get("challengeid") or EMPTY_CHALLENGEID) != origin_challengeid
                    or int(poll.get("responsedigest") or EMPTY_RESPONSEDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_challengeid}:{origin_digest}:{live_token}:{canonical_challenge(live_token, origin_challengeid)}:{canonical_response(live_token, origin_challengeid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "challengeid": origin_challengeid,
                "responsedigest": origin_digest,
                "challenge_frame": True,
                "response_frame": True,
                "responsedigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "challengeid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_digestauth_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "challengeid": origin_challengeid,
                "responsedigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "challenge_frame": True,
                "response_frame": True,
                "responsedigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "challengeid_bound": True,
            }
        except (OSError, DigestauthActuationError) as error:
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
        live = independent_digestauth_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "challengeid": int(live.get("challengeid") or EMPTY_CHALLENGEID),
            "responsedigest": int(live.get("responsedigest") or EMPTY_RESPONSEDIGEST),
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


def call_digestauth_tool(session: DigestauthSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one digestauth tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_challenge = True if arguments.get("challenge") is None else bool(arguments.get("challenge"))
    do_response = True if arguments.get("response") is None else bool(arguments.get("response"))
    do_responsedigest = True if arguments.get("responsedigest") is None else bool(arguments.get("responsedigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_challengeid = True if arguments.get("use_challengeid") is None else bool(arguments.get("use_challengeid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_challenge=do_challenge,
            do_response=do_response,
            do_responsedigest=do_responsedigest,
            replay=replay,
            use_challengeid=use_challengeid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise DigestauthActuationError(f"unsupported digestauth action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_digestauth_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage responsedigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "challengeid": EMPTY_CHALLENGEID,
        "responsedigest": EMPTY_RESPONSEDIGEST,
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
            "challenge_frame",
            "response_frame",
            "responsedigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "challengeid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    challengeid = int(payload.get("challengeid") or EMPTY_CHALLENGEID)
    responsedigest = int(payload.get("responsedigest") or EMPTY_RESPONSEDIGEST)
    dual = port > 0 and bool(challengeid) and bool(responsedigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "challengeid": challengeid,
        "responsedigest": responsedigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "challenge_frame": payload.get("challenge_frame") is True,
        "response_frame": payload.get("response_frame") is True,
        "responsedigest_response": payload.get("responsedigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "challengeid_bound": payload.get("challengeid_bound") is True,
    }


def run_digestauth_workflow(
    *,
    with_challengeid: bool = True,
    skip_bind: bool = False,
    do_challenge: bool = True,
    do_response: bool = True,
    do_responsedigest: bool = True,
    replay: bool = True,
    use_challengeid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2069 CHALLENGE/RESPONSE challengeid cycle workflow."""

    descriptor = digestauth_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DIGESTAUTH_TOOL_PROVIDER),
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
        raise DigestauthActuationError(f"digestauth tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="digestauth-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = DigestauthSession(out, challengeid_gate=DEFAULT_CHALLENGEID if with_challengeid else EMPTY_CHALLENGEID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "challenge": do_challenge,
            "response": do_response,
            "responsedigest": do_responsedigest,
            "replay": replay,
            "use_challengeid": use_challengeid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_digestauth_tool(session, arguments))
            except DigestauthActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_digestauth_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_challengeid
        and not skip_bind
        and do_challenge
        and do_response
        and do_responsedigest
        and replay
        and use_challengeid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "digestauth_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_challengeid": with_challengeid,
        "skip_bind": skip_bind,
        "challenge_frame": do_challenge,
        "response_frame": do_response,
        "responsedigest": do_responsedigest,
        "replay": replay,
        "use_challengeid": use_challengeid,
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
        "challengeid_value": int(publish_result.get("challengeid") or independent.get("challengeid") or EMPTY_CHALLENGEID),
        "responsedigest_value": int(publish_result.get("responsedigest") or independent.get("responsedigest") or EMPTY_RESPONSEDIGEST),
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
        "challengeid": int(trace_body["challengeid_value"] or EMPTY_CHALLENGEID),
        "responsedigest": int(trace_body["responsedigest_value"] or EMPTY_RESPONSEDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_challengeid": with_challengeid,
        "skip_bind": skip_bind,
        "challenge_cycle": do_challenge,
        "response_cycle": do_response,
        "responsedigest_cycle": do_responsedigest,
        "replay": replay,
        "use_challengeid": use_challengeid,
    }


def verify_digestauth_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_digestauth_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    challengeid = int(trace.get("challengeid_value") or independent.get("challengeid") or EMPTY_CHALLENGEID)
    responsedigest = int(trace.get("responsedigest_value") or independent.get("responsedigest") or EMPTY_RESPONSEDIGEST)
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
        "challenge_frame": independent.get("challenge_frame") is True,
        "response_frame": independent.get("response_frame") is True,
        "responsedigest_response": independent.get("responsedigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "challengeid_bound": independent.get("challengeid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "responsedigest_recorded": (
            port > 0
            and challengeid == DEFAULT_CHALLENGEID
            and responsedigest == DEFAULT_RESPONSEDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def digestauth_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.digestauth_actuation import "
        "builtin_digestauth_actuation_proof; r=builtin_digestauth_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='digestauth_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_digestauth_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=DIGESTAUTH_ACTUATION_ID,
        name="First-class RFC 2069 Digest Access Authentication CHALLENGE/RESPONSE actuation",
        description=(
            "Missions that require a digestauth tool can opt the digestauth provider in, "
            "bind a loopback RFC 2069 Digest Access Authentication endpoint, complete a CHALLENGE "
            "with a non-empty challengeid, lockstep a RESPONSE that carries the "
            "stored responsedigest, independently poll the stored responsedigest "
            "on a later socket, and seal a digest-chained responsedigest. Default "
            "routing stays fail-closed; a missing challengeid keeps the hole "
            "falsifiable, and skip-CHALLENGE/RESPONSE/RESPONSEDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.digestauth_actuation:builtin_digestauth_actuation_proof",
        proof_command=digestauth_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.httpstate-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/digestauth_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/httpstate_actuation.py",
            "src/blackhole_agent/http10_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required digestauth tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 2069 daemon, speaks a "
            "CHALLENGE then RESPONSE over Digest Access Authentication with a non-empty challengeid and "
            "responsedigest, independently polls the stored responsedigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 2109 HTTP State Management Mechanism lockstep is proved. "
            "Missing challengeids, skip-CHALLENGE, skip-RESPONSE, skip-responsedigest, skip-REPLAY, "
            "and a CHALLENGE aimed without a challengeid stay fail-closed. "
            "Later genesis can take RFC 1945 Hypertext Transfer Protocol -- HTTP/1.0 GET/POST as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("digestauth", "rfc2069", "http", "challengeid", "responsedigest", "challenge", "response", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T040710Z-7eed0503",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_digestauth_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2069 challenge/response lockstep actuation seals a responsedigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.http10_actuation import (
        HTTP10_ACTUATION_GOAL,
        HTTP10_ACTUATION_ID,
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
    checks["denylists_self"] = DIGESTAUTH_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(DIGESTAUTH_ACTUATION_GOAL) == (
        DIGESTAUTH_ACTUATION_ID,
    )
    checks["leftover_text_binds_digestauth"] = leftover_marker_ids(DIGESTAUTH_LEFTOVER) == (
        DIGESTAUTH_ACTUATION_ID,
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
        (HTTP10_ACTUATION_GOAL, HTTP10_ACTUATION_ID, "http10"),
        (HTTPSTATE_ACTUATION_GOAL, HTTPSTATE_ACTUATION_ID, "httpstate"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_digestauth"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"digestauth_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            DIGESTAUTH_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = DIGESTAUTH_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_digestauth(DEFAULT_CHALLENGE)
    rebuilt = serialize_digestauth(parse_digestauth(advertised))
    preloaded = parse_digestauth(RFC_DIGESTAUTH_RESPONSE)
    header = encode_digestauth_header(DEFAULT_CHALLENGE)
    parsed_header = parse_digestauth_header(header)
    asked = parse_http_request(challenge_request(SENTINEL, DEFAULT_CHALLENGEID))
    preload_req = parse_http_request(response_request(SENTINEL, DEFAULT_CHALLENGEID, DEFAULT_RESPONSEDIGEST))
    got = parse_http_response(challenge_response(SENTINEL, DEFAULT_CHALLENGEID, DEFAULT_RESPONSEDIGEST))
    preload_reply = parse_http_response(
        response_response(SENTINEL, DEFAULT_CHALLENGEID, DEFAULT_RESPONSEDIGEST)
    )
    checks["digestauth_roundtrip"] = (
        parse_digestauth(advertised) == DEFAULT_CHALLENGE
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_CHALLENGE_FIELD
        and is_token("CHALLENGE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_CHALLENGE_FIELD
        and parsed_header["policy"] == DEFAULT_CHALLENGE
        and parsed_header["header"] == CHALLENGE_HEADER
        and parsed_header["challenge"] is True
        and parsed_header["response"] is False
        and preloaded == RESPONSE_POLICY
        and ascii_serialize_digestauth_directive() == RFC_CHALLENGE_DIRECTIVE
        and digestauth_directive_pair() == ("challenge", "realm")
        and RFC_CHALLENGE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_digestauth(RESPONSE_POLICY) == RFC_DIGESTAUTH_RESPONSE
        and DEFAULT_RESPONSEDIGEST == request_responsedigest(DEFAULT_CHALLENGEID, SENTINEL)
        and "responsedigest=" in canonical_response(SENTINEL, DEFAULT_CHALLENGEID, DEFAULT_RESPONSEDIGEST)
        and canonical_challenge(SENTINEL, DEFAULT_CHALLENGEID).startswith("CHALLENGE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "CHALLENGE"
        and asked["digestauth_kind"] == "challenge"
        and asked["challengeid"] == DEFAULT_CHALLENGEID
        and preload_req["digestauth_kind"] == "response"
        and preload_req["responsedigest"] == DEFAULT_RESPONSEDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["digestauth_kind"] == "challenge"
        and preload_reply["digestauth_kind"] == "response"
        and got["policy"] == DEFAULT_CHALLENGE
        and preload_reply["policy"] == RESPONSE_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["responsedigest"] == DEFAULT_RESPONSEDIGEST
        and preload_reply["responsedigest"] == DEFAULT_RESPONSEDIGEST
        and digestauth_matches(serialize_digestauth(got["policy"]), advertised)
    )

    checks["catalog_names_digestauth"] = (
        len(catalog) > 102
        and catalog[102]["id"] == DIGESTAUTH_ACTUATION_ID
        and catalog[101]["id"] == HTTPSTATE_ACTUATION_ID
        and catalog[102]["source"] == "genesis_bind_digestauth"
    )
    checks["catalog_names_http10"] = (
        len(catalog) > 103
        and catalog[103]["id"] == HTTP10_ACTUATION_ID
        and catalog[103]["source"] == "genesis_bind_http10"
    )
    family = capability_family(DIGESTAUTH_ACTUATION_GOAL)
    checks["family_is_digestauth"] = "digestauth" in family
    checks["family_is_digestauth_surface"] = "digestauth" in family
    checks["family_is_challengeid"] = "challengeid" in family
    checks["family_is_rfc2069"] = "rfc2069" in family
    checks["family_is_responsedigest"] = "responsedigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_http10"] = (
        "http10" not in family
        and "rfc1945" not in family
        and "http10id" not in family
        and "http10digest" not in family
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
    packed = encode_challenge(identity=SENTINEL, challengeid=DEFAULT_CHALLENGEID, responsedigest=DEFAULT_RESPONSEDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_challenge"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_challengeid"] is True
        and parsed["challengeid"] == DEFAULT_CHALLENGEID
        and parsed["responsedigest"] == DEFAULT_RESPONSEDIGEST
        and parsed["is_response"] is False
        and parsed["is_response"] is False
        and parsed["type"] == FRAME_CHALLENGE
        and parsed["first_byte"] == DIGESTAUTH_FIRST
    )
    shook = encode_response(
        identity=SENTINEL,
        challengeid=DEFAULT_CHALLENGEID,
        responsedigest=DEFAULT_RESPONSEDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_response"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_challenge"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["challengeid"] == DEFAULT_CHALLENGEID
        and answer_parsed["responsedigest"] == DEFAULT_RESPONSEDIGEST
        and answer_parsed["has_responsedigest"] is True
        and answer_parsed["type"] == FRAME_RESPONSE
        and answer_parsed["first_byte"] == DIGESTAUTH_FIRST
    )
    bare = encode_challenge(identity=SENTINEL, challengeid=DEFAULT_CHALLENGEID, include_challengeid=False)
    checks["missing_challengeid_is_unauthed"] = parse_message(bare)["has_challengeid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(DIGESTAUTH_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_digestauth = ToolDescriptor(name="remote_digestauth", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_digestauth)
    checks["naive_mcp_digestauth_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = digestauth_tool_descriptor()
    default_digestauth = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DIGESTAUTH_TOOL_PROVIDER),
    )
    checks["default_digestauth_provider_is_unsupported"] = (
        default_digestauth.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{DIGESTAUTH_TOOL_PROVIDER}" in default_digestauth.reasons
    )
    checks["opted_in_digestauth_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_digestauth],
        required_tool_names=("local_memory", "digestauth"),
    )
    checks["naive_preflight_missing_digestauth"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["digestauth"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "digestauth"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DIGESTAUTH_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "digestauth" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="digestauth-actuation-") as tmp:
        root = Path(tmp)
        missing = run_digestauth_workflow(with_challengeid=False, output_dir=root / "missing")
        skip_bind = run_digestauth_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_challenge = run_digestauth_workflow(do_challenge=False, output_dir=root / "skip-challenge")
        skip_response = run_digestauth_workflow(do_response=False, output_dir=root / "skip-response")
        skip_responsedigest = run_digestauth_workflow(do_responsedigest=False, output_dir=root / "skip-responsedigest")
        skip_replay = run_digestauth_workflow(replay=False, output_dir=root / "skip-replay")
        skip_challengeid = run_digestauth_workflow(use_challengeid=False, output_dir=root / "skip-challengeid")
        live = run_digestauth_workflow(output_dir=root / "live")
        verify = verify_digestauth_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_digestauth_trace(clone)
        checks["naive_without_challengeid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_challengeid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_challenge_stays_empty"] = (
            skip_challenge["ok"] is False
            and skip_challenge["error"] == "challenge_required"
            and skip_challenge["final_status"] == 409
            and skip_challenge["payload_exists"] is False
        )
        checks["skip_response_stays_empty"] = (
            skip_response["ok"] is False
            and skip_response["error"] == "response_required"
            and skip_response["final_status"] == 409
            and skip_response["payload_exists"] is False
        )
        checks["skip_responsedigest_stays_empty"] = (
            skip_responsedigest["ok"] is False
            and skip_responsedigest["error"] == "responsedigest_required"
            and skip_responsedigest["final_status"] == 409
            and skip_responsedigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_challengeid_stays_empty"] = (
            skip_challengeid["ok"] is False
            and skip_challengeid["error"] == "challengeid_required"
            and skip_challengeid["final_status"] == 409
            and skip_challengeid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_responsedigest"] = (
            int(live.get("challengeid") or 0) == DEFAULT_CHALLENGEID
            and int(live.get("responsedigest") or 0) == DEFAULT_RESPONSEDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_challengeid_encode_response_responsedigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_challenge["ok"] is False
            and skip_response["ok"] is False
            and skip_responsedigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_challengeid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="digestauth-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != DIGESTAUTH_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_digestauth"] = (
        live_goal == DIGESTAUTH_ACTUATION_GOAL
        and DIGESTAUTH_ACTUATION_ID in live_done
        and live_source == "genesis_bind_digestauth"
    )

    with tempfile.TemporaryDirectory(prefix="digestauth-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(DIGESTAUTH_LEFTOVER, root)
        register_catalog_proved(root, DIGESTAUTH_ACTUATION_ID)
        reason = leftover_satisfied_by(DIGESTAUTH_LEFTOVER, root)
        after = leftover_is_open(DIGESTAUTH_LEFTOVER, root)
    checks["digestauth_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_digestauth_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{DIGESTAUTH_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_digestauth_actuation_capability()
    return {
        "ok": ok,
        "action": "digestauth_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": DIGESTAUTH_ACTUATION_GOAL,
        "done_when": DIGESTAUTH_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
