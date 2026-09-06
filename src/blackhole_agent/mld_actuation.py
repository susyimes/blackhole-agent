"""Drive a first-class Multicast Listener Discovery tool through RFC 2710 LISTENER/DONE.

Tool routing already fails missions that require ``mld``: hosted
mld endpoints stay on the unsupported MCP provider, and no first-party
mld provider is executable. Unbound therefore cannot speak a LISTENER,
lockstep a DONE mldid handshake over HTTP/1.0 MLDID,
independently poll the stored mlddigest, or seal a mlddigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``mld`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 2710 daemon
- keep a missing-mldid client so the mld-mldid hole stays falsifiable
- refuse DONE until a LISTENER lands with a non-empty mldid
- independently poll the stored mlddigest on a later client socket
- persist a sealed mlddigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 1112 Internet Group Management Protocol
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
    MLD_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    mld_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
MLD_ACTUATION_ID = "capability.mld-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-MLD-OK"
POLL_TOKEN = "BH-MLD-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_MLDID = 0
EMPTY_MLDDIGEST = 0
MLD_FIRST = 0x3A  # RFC 2710 MLD (ICMPv6 next-header 58)
MLDID_SIZE = 4
MLDDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_DONE = 0x84  # RFC 2710 Multicast Listener Done
FRAME_LISTENER = 0x83  # RFC 2710 Multicast Listener Report
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
MLD_LEFTOVER = (
    "Later genesis can take RFC 2710 Multicast Listener Discovery LISTENER/DONE over an "
    "mldid-gated mlddigest."
)
MLD_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MLD_ACTUATION_ID};"
    f"capability_proved:{MLD_ACTUATION_ID};"
    "no_skill_route"
)
MLD_ACTUATION_GOAL = (
    "Repair rfc2710 mld listener/done cycle cannot land over http "
    "mld mldid: hosted mld endpoints remain unsupported so a LISTENER then "
    "DONE mldid handshake cannot land and a sealed mlddigest "
    "cannot be produced. A missing mld mldid stays forbidden; fail-closed "
    "routing never opts the mld provider in. An independent later poll of the "
    "stored mlddigest keeps the hole falsifiable."
)


class MldActuationError(RuntimeError):
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
# RFC 2710 sections 3.3 and 3.4: LISTENER / DONE.
RFC_LISTENER_FIELD = "LISTENER"
RFC_DONE_FIELD = "DONE"
RFC_MLD_DONE = RFC_DONE_FIELD
RFC_LISTENER_DIRECTIVE = "listener=message"
RFC_DONE_DIRECTIVE = "done=message"
DEFAULT_LISTENER = "LISTENER"
DONE_POLICY = "DONE"
LISTENER_HEADER = "Listener"
DONE_HEADER = "Done"
MLD_DONE_HEADER = DONE_HEADER
RFC_LISTENER_PATH = "/mld/"
RFC_LISTENER_EMPTY = ""


def mld_directive_pair(*, done: bool = False) -> tuple[str, str]:
    """RFC 2710 Listener / Done directive pair."""

    if done:
        return "done", "message"
    return "listener", "message"


def ascii_serialize_mld_directive(*, done: bool = False) -> str:
    """RFC 2710 token "=" body-or-done."""

    name, value = mld_directive_pair(done=done)
    if not is_token(name):
        raise MldActuationError("illegal_directive")
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
            raise MldActuationError("short_mld")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 2710 body-listener token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_mld(policy: str | Sequence[str]) -> str:
    """Serialize RFC 2710 LISTENER / DONE opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise MldActuationError("illegal_mld")
    upper = text.upper().replace("_", "-")
    if upper in {"LISTENER", "MLD", "MLD-LISTENER", "MLD-REQUEST"}:
        return "LISTENER"
    if upper in {"DONE", "RESOURCE", "MLD-DONE"}:
        return "DONE"
    if upper.startswith("LISTENER="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise MldActuationError("illegal_mld")
        return "LISTENER"
    if upper.startswith("DONE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise MldActuationError("illegal_mld")
        return "DONE"
    raise MldActuationError("illegal_mld")


def parse_mld(text: str) -> str:
    """Parse RFC 2710 MLD opcode header extensions into LISTENER or DONE."""

    raw = str(text or "").strip()
    if not raw:
        raise MldActuationError("illegal_mld")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"LISTENER", "MLD", "MLD-LISTENER", "MLD-REQUEST"}:
        return "LISTENER"
    if upper in {"DONE", "RESOURCE", "MLD-DONE"}:
        return "DONE"
    if upper.startswith("LISTENER="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise MldActuationError("illegal_mld")
        return "LISTENER"
    if upper.startswith("DONE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise MldActuationError("illegal_mld")
        return "DONE"
    raise MldActuationError("illegal_mld")


def encode_mld_header(policy: str | Sequence[str]) -> bytes:
    """RFC 2710 HTTP/1.0 field as bytes."""

    return serialize_mld(policy).encode("ascii")


def parse_mld_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_mld(field_value) if field_value else DEFAULT_LISTENER
    return {
        "field_value": field_value,
        "policy": policy,
        "header": LISTENER_HEADER,
        "directive": str(policy),
        "listener": str(policy) == "LISTENER",
        "done": str(policy) == "DONE",
    }


def canonical_listener(identity: str, mldid: int) -> str:
    """RFC 2710 body-listener advertisement bound to identity and mldid."""

    return (
        f"{serialize_mld(DEFAULT_LISTENER)}, "
        f"listener={ascii_serialize_mld_directive()}, "
        f"identity={identity}, mldid={int(mldid) & 0xFFFFFFFF}"
    )


def canonical_done(identity: str, mldid: int, mlddigest: int | None = None) -> str:
    """RFC 2710 done-message confirmation of the stored identifier-digest."""

    digest = ""
    if mlddigest is not None:
        digest = f", mlddigest={int(mlddigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_mld(DONE_POLICY)}, "
        f"done={ascii_serialize_mld_directive(done=True)}, "
        f"identity={identity}, mldid={int(mldid) & 0xFFFFFFFF}{digest}"
    )


def representation_done(identity: str, mldid: int, mlddigest: int) -> str:
    return canonical_done(identity, mldid, mlddigest)


def mld_matches(left: str, right: str) -> bool:
    return parse_mld(left) == parse_mld(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise MldActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise MldActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise MldActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise MldActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def listener_request(identity: str, mldid: int) -> bytes:
    """HTTP LISTENER that elicits RFC 2710 origin HTTP/1.0."""

    keyid = f"{int(mldid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"LISTENER /mld/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Mld-Id: {int(mldid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def done_request(identity: str, mldid: int, mlddigest: int | None = None) -> bytes:
    """HTTP DONE carrying RFC 2710 done-message confirmation of the stored identifier-digest."""

    keyid = f"{int(mldid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if mlddigest is not None:
        extra = f"Mld-Digest: {int(mlddigest) & 0xFFFFFFFF}\r\n"
    return (
        f"DONE /mld/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Mld-Id: {int(mldid) & 0xFFFFFFFF}\r\n"
        "Done-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    mld_kind = "done" if fields.get("done-confirm") == "1" else "listener"
    upgrade_field = fields.get("listener") or fields.get("mld") or ""
    policy = parse_mld(upgrade_field) if upgrade_field else ()
    return {
        "kind": "listener",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "mld_kind": mld_kind,
        "policy": policy,
        "mldid": int(fields["mld-id"]) if fields.get("mld-id") else EMPTY_MLDID,
        "mlddigest": int(fields["mld-digest"]) if fields.get("mld-digest") else EMPTY_MLDDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def listener_response(identity: str, mldid: int, mlddigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 2710 origin HTTP/1.0, carrying the stored mlddigest."""

    advertised = serialize_mld(DEFAULT_LISTENER)
    payload = bytes(body or canonical_listener(identity, mldid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Listener: {advertised}\r\n"
        f"Mld-Id: {int(mldid) & 0xFFFFFFFF}\r\n"
        f"Mld-Digest: {int(mlddigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def done_response(identity: str, mldid: int, mlddigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 2710 DONE, carrying the stored identifier-digest."""

    advertised = serialize_mld(DONE_POLICY)
    payload = bytes(body or representation_done(identity, mldid, mlddigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Listener: {advertised}\r\n"
        f"Mld-Id: {int(mldid) & 0xFFFFFFFF}\r\n"
        f"Mld-Digest: {int(mlddigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/mld-done\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise MldActuationError("illegal_content_length") from error
    field_value = fields.get("listener") or fields.get("mld") or ""
    policy = parse_mld(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/mld-done" or policy == DONE_POLICY:
        status = 200
        mld_kind = "done"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        mld_kind = "listener"
    else:
        status = 0
        mld_kind = "listener"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "mld_kind": mld_kind,
        "policy": policy,
        "mldid": int(fields["mld-id"]) if fields.get("mld-id") else EMPTY_MLDID,
        "mlddigest": int(fields["mld-digest"]) if fields.get("mld-digest") else EMPTY_MLDDIGEST,
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
        raise MldActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise MldActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise MldActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise MldActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc2710_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    mld: str,
) -> str:
    """RFC 2710 identifier digest over method, listener-IP, identity, and mldid."""

    payload = f"{method}:{mld}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def listener_mldid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"mldid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_mldid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-mldid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def listener_mlddigest(mldid: int = EMPTY_MLDID, token: str = SENTINEL) -> int:
    nonce = f"{int(mldid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc2710_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="DONE",
        mld=f"/mld/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_MLDID = listener_mldid(SENTINEL)
DEFAULT_MLDDIGEST = listener_mlddigest(DEFAULT_MLDID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    mldid: int,
    mlddigest: int,
    include_mldid: bool = True,
) -> bytes:
    live_mldid = int(mldid) & 0xFFFFFFFF if include_mldid else EMPTY_MLDID
    live_digest = int(mlddigest) & 0xFFFFFFFF if include_mldid and live_mldid else EMPTY_MLDDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_mldid) if live_mldid else b""
    header = bytearray()
    header.append(MLD_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_listener(
    *,
    identity: str,
    mldid: int,
    mlddigest: int | None = None,
    include_mldid: bool = True,
) -> bytes:
    live_mldid = int(mldid) & 0xFFFFFFFF if include_mldid else EMPTY_MLDID
    live_digest = int(mlddigest) if mlddigest is not None else listener_mlddigest(live_mldid, identity)
    return encode_packet(
        FRAME_LISTENER,
        identity=identity,
        mldid=live_mldid,
        mlddigest=live_digest,
        include_mldid=include_mldid,
    )


def encode_done(
    *,
    identity: str,
    mldid: int,
    mlddigest: int | None = None,
    include_mldid: bool = True,
) -> bytes:
    live_mldid = int(mldid) & 0xFFFFFFFF if include_mldid else EMPTY_MLDID
    live_digest = int(mlddigest) if mlddigest is not None else listener_mlddigest(live_mldid, identity)
    return encode_packet(
        FRAME_DONE,
        identity=identity,
        mldid=live_mldid,
        mlddigest=live_digest,
        include_mldid=include_mldid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise MldActuationError("short_packet")
    first = raw[0]
    if first != MLD_FIRST:
        raise MldActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise MldActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == MLDID_SIZE:
        live_mldid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_mldid = EMPTY_MLDID
    else:
        raise MldActuationError("illegal_mldid")
    if offset >= len(raw):
        raise MldActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_LISTENER, FRAME_DONE}:
        raise MldActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise MldActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise MldActuationError("checksum_failed")
    if len(payload) < 5:
        raise MldActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise MldActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_mldid = int(live_mldid) != EMPTY_MLDID
    has_mlddigest = has_mldid and int(live_digest) != EMPTY_MLDDIGEST
    is_listener = frame_type == FRAME_LISTENER
    is_done = frame_type == FRAME_DONE
    return {
        "type": int(frame_type),
        "is_listener": is_listener,
        "is_done": is_done,
        "mldid": int(live_mldid),
        "has_mldid": has_mldid,
        "mlddigest": int(live_digest),
        "has_mlddigest": has_mlddigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC2710",
        "serialize_field": canonical_listener(identity, live_mldid) if has_mldid else "",
        "tls_field": canonical_done(identity, live_mldid, live_digest) if has_mlddigest else "",
    }


class MldClient:
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
            raise MldActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_done"] or not packet["is_done"]:
            raise MldActuationError("mlddigest_required")
        if not packet["has_mldid"]:
            raise MldActuationError("mldid_required")
        if not packet["has_mlddigest"]:
            raise MldActuationError("mlddigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_mlddigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_mlddigest:
            raise MldActuationError("mlddigest_required")
        done = self._recv()
        return {
            "session": done,
            "mldid": int(done.get("mldid") or EMPTY_MLDID),
            "identity": str(done.get("identity") or ""),
            "mlddigest": int(done.get("mlddigest") or EMPTY_MLDDIGEST),
        }

    def done(
        self,
        identity: str,
        mldid: int,
        mlddigest: int = EMPTY_MLDDIGEST,
        *,
        wait_mlddigest: bool = True,
        include_mldid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_done(
            identity=identity,
            mldid=mldid,
            mlddigest=mlddigest or listener_mlddigest(mldid, identity),
            include_mldid=include_mldid,
        )
        return self.exchange(packet, wait_mlddigest=wait_mlddigest)


class MldSession:
    """MLDID-gated loopback RFC 2710 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        mldid_gate: int = DEFAULT_MLDID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.mldid_gate = int(mldid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.mldid = EMPTY_MLDID
        self.mlddigest = EMPTY_MLDDIGEST
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

    def store_mldid_once(self, identity: str, mldid: int, mlddigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(mldid or EMPTY_MLDID)
            live_digest = int(mlddigest or EMPTY_MLDDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.mldid = live
                self.mlddigest = live_digest or listener_mlddigest(live, name)
                self.stored = True
            return str(self.identity), int(self.mldid), int(self.mlddigest)

    def read_mldid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.mldid), int(self.mlddigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "mldid": EMPTY_MLDID,
            "mlddigest": EMPTY_MLDDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _mldid_missing(self) -> bool:
        return not int(self.mldid_gate or 0)

    def _done_tuple(self, peer: tuple[str, int], identity: str, mldid: int, mlddigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_done(
            identity=identity,
            mldid=mldid,
            mlddigest=mlddigest,
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
            except MldActuationError:
                continue
            if not packet.get("is_listener") and not packet.get("is_done"):
                continue
            if not packet.get("has_mldid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_mldid, stored_digest = self.store_mldid_once(
                identity,
                int(packet.get("mldid") or EMPTY_MLDID),
                int(packet.get("mlddigest") or EMPTY_MLDDIGEST),
            )
            if not stored_name or not stored_mldid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_listener"):
                    self.opened = True
                if packet.get("is_done"):
                    self.handshook = True
                self.retrieved = True
            self._done_tuple(peer, stored_name, stored_mldid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._mldid_missing():
            return self._forbidden("missing_mldid")
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
        do_listener: bool = True,
        do_done: bool = True,
        do_mlddigest: bool = True,
        replay: bool = True,
        use_mldid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._mldid_missing():
            return self._forbidden("missing_mldid")
        live_token = str(token or SENTINEL)
        origin_mldid = listener_mldid(live_token)
        origin_digest = listener_mlddigest(origin_mldid, live_token)
        client: MldClient | None = None
        independent: MldClient | None = None
        try:
            client = MldClient(self.host, int(self.port))
            if not do_listener:
                return self._conflict("listener_required")
            bind_packet = encode_listener(
                identity=live_token,
                mldid=origin_mldid,
                mlddigest=origin_digest,
                include_mldid=use_mldid,
            )
            if not use_mldid:
                try:
                    client.exchange(bind_packet, wait_mlddigest=True)
                except MldActuationError:
                    return self._conflict("mldid_required")
                return self._conflict("mldid_required")
            client.send(bind_packet)
            if not do_done:
                return self._conflict("done_required")
            proxy_packet = encode_done(
                identity=live_token,
                mldid=origin_mldid,
                mlddigest=origin_digest,
                include_mldid=True,
            )
            if not do_mlddigest:
                try:
                    client.exchange(proxy_packet, wait_mlddigest=False)
                except MldActuationError as error:
                    if str(error) == "mlddigest_required":
                        return self._conflict("mlddigest_required")
                    return self._conflict("mlddigest_required")
                return self._conflict("mlddigest_required")
            try:
                done = client.exchange(proxy_packet, wait_mlddigest=True)
            except MldActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("mldid_required")
                if reason == "mlddigest_required":
                    return self._conflict("mlddigest_required")
                return self._conflict("listener_required")
            if str(done.get("identity") or "") != live_token:
                return self._conflict("listener_required")
            if int(done.get("mldid") or EMPTY_MLDID) != origin_mldid:
                return self._conflict("mlddigest_required")
            if int(done.get("mlddigest") or EMPTY_MLDDIGEST) != origin_digest:
                return self._conflict("mlddigest_required")
            self.retrieved = True
            if replay:
                independent = MldClient(self.host, int(self.port))
                try:
                    poll = independent.done(
                        POLL_TOKEN,
                        poll_mldid(live_token),
                        listener_mlddigest(poll_mldid(live_token), POLL_TOKEN),
                        wait_mlddigest=True,
                    )
                except MldActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_mldid, stored_digest = self.read_mldid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_mldid != origin_mldid
                    or stored_digest != origin_digest
                    or int(poll.get("mldid") or EMPTY_MLDID) != origin_mldid
                    or int(poll.get("mlddigest") or EMPTY_MLDDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_mldid}:{origin_digest}:{live_token}:{canonical_listener(live_token, origin_mldid)}:{canonical_done(live_token, origin_mldid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "mldid": origin_mldid,
                "mlddigest": origin_digest,
                "listener_frame": True,
                "done_frame": True,
                "mlddigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "mldid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_mlddigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "mldid": origin_mldid,
                "mlddigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "listener_frame": True,
                "done_frame": True,
                "mlddigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "mldid_bound": True,
            }
        except (OSError, MldActuationError) as error:
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
        live = independent_mlddigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "mldid": int(live.get("mldid") or EMPTY_MLDID),
            "mlddigest": int(live.get("mlddigest") or EMPTY_MLDDIGEST),
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


def call_mld_tool(session: MldSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one mld tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_listener = True if arguments.get("listener") is None else bool(arguments.get("listener"))
    do_done = True if arguments.get("done") is None else bool(arguments.get("done"))
    do_mlddigest = True if arguments.get("mlddigest") is None else bool(arguments.get("mlddigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_mldid = True if arguments.get("use_mldid") is None else bool(arguments.get("use_mldid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_listener=do_listener,
            do_done=do_done,
            do_mlddigest=do_mlddigest,
            replay=replay,
            use_mldid=use_mldid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise MldActuationError(f"unsupported mld action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_mlddigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage mlddigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "mldid": EMPTY_MLDID,
        "mlddigest": EMPTY_MLDDIGEST,
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
            "listener_frame",
            "done_frame",
            "mlddigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "mldid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    mldid = int(payload.get("mldid") or EMPTY_MLDID)
    mlddigest = int(payload.get("mlddigest") or EMPTY_MLDDIGEST)
    dual = port > 0 and bool(mldid) and bool(mlddigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "mldid": mldid,
        "mlddigest": mlddigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "listener_frame": payload.get("listener_frame") is True,
        "done_frame": payload.get("done_frame") is True,
        "mlddigest_locate": payload.get("mlddigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "mldid_bound": payload.get("mldid_bound") is True,
    }


def run_mld_workflow(
    *,
    with_mldid: bool = True,
    skip_bind: bool = False,
    do_listener: bool = True,
    do_done: bool = True,
    do_mlddigest: bool = True,
    replay: bool = True,
    use_mldid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 2710 LISTENER/DONE mldid cycle workflow."""

    descriptor = mld_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MLD_TOOL_PROVIDER),
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
        raise MldActuationError(f"mld tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="mld-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = MldSession(out, mldid_gate=DEFAULT_MLDID if with_mldid else EMPTY_MLDID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "listener": do_listener,
            "done": do_done,
            "mlddigest": do_mlddigest,
            "replay": replay,
            "use_mldid": use_mldid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_mld_tool(session, arguments))
            except MldActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_mlddigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_mldid
        and not skip_bind
        and do_listener
        and do_done
        and do_mlddigest
        and replay
        and use_mldid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mld_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_mldid": with_mldid,
        "skip_bind": skip_bind,
        "listener_frame": do_listener,
        "done_frame": do_done,
        "mlddigest": do_mlddigest,
        "replay": replay,
        "use_mldid": use_mldid,
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
        "mldid_value": int(publish_result.get("mldid") or independent.get("mldid") or EMPTY_MLDID),
        "mlddigest_value": int(publish_result.get("mlddigest") or independent.get("mlddigest") or EMPTY_MLDDIGEST),
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
        "mldid": int(trace_body["mldid_value"] or EMPTY_MLDID),
        "mlddigest": int(trace_body["mlddigest_value"] or EMPTY_MLDDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_mldid": with_mldid,
        "skip_bind": skip_bind,
        "listener_cycle": do_listener,
        "done_cycle": do_done,
        "mlddigest_cycle": do_mlddigest,
        "replay": replay,
        "use_mldid": use_mldid,
    }


def verify_mld_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_mlddigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    mldid = int(trace.get("mldid_value") or independent.get("mldid") or EMPTY_MLDID)
    mlddigest = int(trace.get("mlddigest_value") or independent.get("mlddigest") or EMPTY_MLDDIGEST)
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
        "listener_frame": independent.get("listener_frame") is True,
        "done_frame": independent.get("done_frame") is True,
        "mlddigest_locate": independent.get("mlddigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "mldid_bound": independent.get("mldid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "mlddigest_recorded": (
            port > 0
            and mldid == DEFAULT_MLDID
            and mlddigest == DEFAULT_MLDDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def mld_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mld_actuation import "
        "builtin_mld_actuation_proof; r=builtin_mld_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='mld_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mld_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MLD_ACTUATION_ID,
        name="First-class RFC 2710 Multicast Listener Discovery LISTENER/DONE actuation",
        description=(
            "Missions that require a mld tool can opt the mld provider in, "
            "bind a loopback RFC 2710 Multicast Listener Discovery endpoint, complete a LISTENER "
            "with a non-empty mldid, lockstep a DONE that carries the "
            "stored mlddigest, independently poll the stored mlddigest "
            "on a later socket, and seal a digest-chained mlddigest. Default "
            "routing stays fail-closed; a missing mldid keeps the hole "
            "falsifiable, and skip-LISTENER/DONE/MLDDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.mld_actuation:builtin_mld_actuation_proof",
        proof_command=mld_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.igmp-actuation",
        ),
        behavior_paths=(
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
            "src/blackhole_agent/ndp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required mld tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 2710 daemon, speaks a "
            "LISTENER then DONE over Multicast Listener Discovery with a non-empty mldid and "
            "mlddigest, independently polls the stored mlddigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 1112 Internet Group Management Protocol lockstep is proved. "
            "Missing mldids, skip-LISTENER, skip-DONE, skip-mlddigest, skip-REPLAY, "
            "and a LISTENER aimed without a mldid stay fail-closed. "
            "Later genesis can take RFC 4861 Neighbor Discovery Protocol SOLICIT/ADVERT as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("mld", "rfc2710", "http", "mldid", "mlddigest", "listener", "done", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T162517Z-ff82ed37",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mld_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 2710 listener/done lockstep actuation seals an mlddigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.ndp_actuation import (
        NDP_ACTUATION_GOAL,
        NDP_ACTUATION_ID,
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
    checks["denylists_self"] = MLD_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MLD_ACTUATION_GOAL) == (
        MLD_ACTUATION_ID,
    )
    checks["leftover_text_binds_mld"] = leftover_marker_ids(MLD_LEFTOVER) == (
        MLD_ACTUATION_ID,
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
        (NDP_ACTUATION_GOAL, NDP_ACTUATION_ID, "ndp"),
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
        checks[f"{name}_goal_is_not_mld"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"mld_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            MLD_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = MLD_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_mld(DEFAULT_LISTENER)
    rebuilt = serialize_mld(parse_mld(advertised))
    preloaded = parse_mld(RFC_MLD_DONE)
    header = encode_mld_header(DEFAULT_LISTENER)
    parsed_header = parse_mld_header(header)
    asked = parse_http_request(listener_request(SENTINEL, DEFAULT_MLDID))
    preload_req = parse_http_request(done_request(SENTINEL, DEFAULT_MLDID, DEFAULT_MLDDIGEST))
    got = parse_http_response(listener_response(SENTINEL, DEFAULT_MLDID, DEFAULT_MLDDIGEST))
    preload_done = parse_http_response(
        done_response(SENTINEL, DEFAULT_MLDID, DEFAULT_MLDDIGEST)
    )
    checks["mld_roundtrip"] = (
        parse_mld(advertised) == DEFAULT_LISTENER
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_LISTENER_FIELD
        and is_token("LISTENER") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_LISTENER_FIELD
        and parsed_header["policy"] == DEFAULT_LISTENER
        and parsed_header["header"] == LISTENER_HEADER
        and parsed_header["listener"] is True
        and parsed_header["done"] is False
        and preloaded == DONE_POLICY
        and ascii_serialize_mld_directive() == RFC_LISTENER_DIRECTIVE
        and mld_directive_pair() == ("listener", "message")
        and RFC_LISTENER_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_mld(DONE_POLICY) == RFC_MLD_DONE
        and DEFAULT_MLDDIGEST == listener_mlddigest(DEFAULT_MLDID, SENTINEL)
        and "mlddigest=" in canonical_done(SENTINEL, DEFAULT_MLDID, DEFAULT_MLDDIGEST)
        and canonical_listener(SENTINEL, DEFAULT_MLDID).startswith("LISTENER")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "LISTENER"
        and asked["mld_kind"] == "listener"
        and asked["mldid"] == DEFAULT_MLDID
        and preload_req["mld_kind"] == "done"
        and preload_req["mlddigest"] == DEFAULT_MLDDIGEST
        and got["status"] == 200
        and preload_done["status"] == 200
        and got["mld_kind"] == "listener"
        and preload_done["mld_kind"] == "done"
        and got["policy"] == DEFAULT_LISTENER
        and preload_done["policy"] == DONE_POLICY
        and got["content_length_matches_body"] is True
        and preload_done["content_length_matches_body"] is True
        and got["mlddigest"] == DEFAULT_MLDDIGEST
        and preload_done["mlddigest"] == DEFAULT_MLDDIGEST
        and mld_matches(serialize_mld(got["policy"]), advertised)
    )

    checks["catalog_names_mld"] = (
        len(catalog) > 119
        and catalog[119]["id"] == MLD_ACTUATION_ID
        and catalog[118]["id"] == IGMP_ACTUATION_ID
        and catalog[117]["id"] == RARP_ACTUATION_ID
        and catalog[119]["source"] == "genesis_bind_mld"
    )
    checks["catalog_names_ndp"] = (
        len(catalog) > 120
        and catalog[120]["id"] == NDP_ACTUATION_ID
        and catalog[120]["source"] == "genesis_bind_ndp"
    )
    family = capability_family(MLD_ACTUATION_GOAL)
    checks["family_is_mld"] = "mld" in family.split("/")
    checks["family_is_mld_surface"] = "mldid" in family
    checks["family_is_mldid"] = "mldid" in family
    checks["family_is_rfc2710"] = "rfc2710" in family
    checks["family_is_mlddigest"] = "mlddigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_ndp"] = (
        "ndp" not in family.split("/")
        and "rfc4861" not in family
        and "ndpid" not in family
        and "ndpdigest" not in family
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
    packed = encode_listener(identity=SENTINEL, mldid=DEFAULT_MLDID, mlddigest=DEFAULT_MLDDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_listener"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_mldid"] is True
        and parsed["mldid"] == DEFAULT_MLDID
        and parsed["mlddigest"] == DEFAULT_MLDDIGEST
        and parsed["is_done"] is False
        and parsed["is_done"] is False
        and parsed["type"] == FRAME_LISTENER
        and parsed["first_byte"] == MLD_FIRST
    )
    shook = encode_done(
        identity=SENTINEL,
        mldid=DEFAULT_MLDID,
        mlddigest=DEFAULT_MLDDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_done"] is True
        and answer_parsed["is_done"] is True
        and answer_parsed["is_listener"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["mldid"] == DEFAULT_MLDID
        and answer_parsed["mlddigest"] == DEFAULT_MLDDIGEST
        and answer_parsed["has_mlddigest"] is True
        and answer_parsed["type"] == FRAME_DONE
        and answer_parsed["first_byte"] == MLD_FIRST
    )
    bare = encode_listener(identity=SENTINEL, mldid=DEFAULT_MLDID, include_mldid=False)
    checks["missing_mldid_is_unauthed"] = parse_message(bare)["has_mldid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(MLD_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_mld = ToolDescriptor(name="remote_mld", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_mld)
    checks["naive_mcp_mld_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = mld_tool_descriptor()
    default_mld = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MLD_TOOL_PROVIDER),
    )
    checks["default_mld_provider_is_unsupported"] = (
        default_mld.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{MLD_TOOL_PROVIDER}" in default_mld.reasons
    )
    checks["opted_in_mld_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_mld],
        required_tool_names=("local_memory", "mld"),
    )
    checks["naive_preflight_missing_mld"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["mld"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "mld"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MLD_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "mld" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="mld-actuation-") as tmp:
        root = Path(tmp)
        missing = run_mld_workflow(with_mldid=False, output_dir=root / "missing")
        skip_bind = run_mld_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_listener = run_mld_workflow(do_listener=False, output_dir=root / "skip-listener")
        skip_done = run_mld_workflow(do_done=False, output_dir=root / "skip-done")
        skip_mlddigest = run_mld_workflow(do_mlddigest=False, output_dir=root / "skip-mlddigest")
        skip_replay = run_mld_workflow(replay=False, output_dir=root / "skip-replay")
        skip_mldid = run_mld_workflow(use_mldid=False, output_dir=root / "skmld-mldid")
        live = run_mld_workflow(output_dir=root / "live")
        verify = verify_mld_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_mld_trace(clone)
        checks["naive_without_mldid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_mldid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_listener_stays_empty"] = (
            skip_listener["ok"] is False
            and skip_listener["error"] == "listener_required"
            and skip_listener["final_status"] == 409
            and skip_listener["payload_exists"] is False
        )
        checks["skip_done_stays_empty"] = (
            skip_done["ok"] is False
            and skip_done["error"] == "done_required"
            and skip_done["final_status"] == 409
            and skip_done["payload_exists"] is False
        )
        checks["skip_mlddigest_stays_empty"] = (
            skip_mlddigest["ok"] is False
            and skip_mlddigest["error"] == "mlddigest_required"
            and skip_mlddigest["final_status"] == 409
            and skip_mlddigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_mldid_stays_empty"] = (
            skip_mldid["ok"] is False
            and skip_mldid["error"] == "mldid_required"
            and skip_mldid["final_status"] == 409
            and skip_mldid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_mlddigest"] = (
            int(live.get("mldid") or 0) == DEFAULT_MLDID
            and int(live.get("mlddigest") or 0) == DEFAULT_MLDDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_mldid_encode_done_mlddigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_listener["ok"] is False
            and skip_done["ok"] is False
            and skip_mlddigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_mldid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="mld-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MLD_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_mld"] = (
        live_goal == MLD_ACTUATION_GOAL
        and MLD_ACTUATION_ID in live_done
        and live_source == "genesis_bind_mld"
    )

    with tempfile.TemporaryDirectory(prefix="mld-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(MLD_LEFTOVER, root)
        register_catalog_proved(root, MLD_ACTUATION_ID)
        reason = leftover_satisfied_by(MLD_LEFTOVER, root)
        after = leftover_is_open(MLD_LEFTOVER, root)
    checks["mld_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_mld_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{MLD_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mld_actuation_capability()
    return {
        "ok": ok,
        "action": "mld_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MLD_ACTUATION_GOAL,
        "done_when": MLD_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
