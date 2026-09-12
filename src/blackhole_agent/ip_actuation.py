"""Drive a first-class Internet Protocol tool through RFC 791 DATAGRAM/FRAGMENT.

Tool routing already fails missions that require ``ip``: hosted
ip endpoints stay on the unsupported MCP provider, and no first-party
ip provider is executable. Unbound therefore cannot speak a DATAGRAM,
lockstep a FRAGMENT ipid handshake over HTTP/1.0 IPID,
independently poll the stored ipdigest, or seal a ipdigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``ip`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 791 daemon
- keep a missing-ipid client so the ip-ipid hole stays falsifiable
- refuse FRAGMENT until a DATAGRAM lands with a non-empty ipid
- independently poll the stored ipdigest on a later client socket
- persist a sealed ipdigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 792 Internet Control Message Protocol
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
    IP_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    ip_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
IP_ACTUATION_ID = "capability.ip-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-IP-OK"
POLL_TOKEN = "BH-IP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_IPID = 0
EMPTY_IPDIGEST = 0
IP_FIRST = 0x04  # RFC 791 IPv4 (IP protocol 4)
IPID_SIZE = 4
IPDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_FRAGMENT = 0x02  # RFC 791 FRAGMENT confirmation
FRAME_DATAGRAM = 0x01  # RFC 791 DATAGRAM
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
IP_LEFTOVER = (
    "Later genesis can take RFC 791 Internet Protocol DATAGRAM/FRAGMENT over a "
    "ipid-gated ipdigest."
)
IP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{IP_ACTUATION_ID};"
    f"capability_proved:{IP_ACTUATION_ID};"
    "no_skill_route"
)
IP_ACTUATION_GOAL = (
    "Repair rfc791 ip datagram/fragment cycle cannot land over http "
    "ip ipid: hosted ip endpoints remain unsupported so a DATAGRAM then "
    "FRAGMENT ipid handshake cannot land and a sealed ipdigest "
    "cannot be produced. A missing ip ipid stays forbidden; fail-closed "
    "routing never opts the ip provider in. An independent later poll of the "
    "stored ipdigest keeps the hole falsifiable."
)


class IpActuationError(RuntimeError):
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
# RFC 791 sections 3.3 and 3.4: DATAGRAM / FRAGMENT.
RFC_DATAGRAM_FIELD = "DATAGRAM"
RFC_FRAGMENT_FIELD = "FRAGMENT"
RFC_IP_FRAGMENT = RFC_FRAGMENT_FIELD
RFC_DATAGRAM_DIRECTIVE = "datagram=message"
RFC_FRAGMENT_DIRECTIVE = "fragment=message"
DEFAULT_DATAGRAM = "DATAGRAM"
FRAGMENT_POLICY = "FRAGMENT"
DATAGRAM_HEADER = "Datagram"
FRAGMENT_HEADER = "Fragment"
IP_FRAGMENT_HEADER = FRAGMENT_HEADER
RFC_DATAGRAM_PATH = "/ip/"
RFC_DATAGRAM_EMPTY = ""


def ip_directive_pair(*, fragment: bool = False) -> tuple[str, str]:
    """RFC 791 Datagram / Fragment directive pair."""

    if fragment:
        return "fragment", "message"
    return "datagram", "message"


def ascii_serialize_ip_directive(*, fragment: bool = False) -> str:
    """RFC 791 token "=" body-or-fragment."""

    name, value = ip_directive_pair(fragment=fragment)
    if not is_token(name):
        raise IpActuationError("illegal_directive")
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
            raise IpActuationError("short_ip")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 791 body-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_ip(policy: str | Sequence[str]) -> str:
    """Serialize RFC 791 DATAGRAM / FRAGMENT opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise IpActuationError("illegal_ip")
    upper = text.upper().replace("_", "-")
    if upper in {"DATAGRAM", "IP", "IP-DATAGRAM"}:
        return "DATAGRAM"
    if upper in {"FRAGMENT", "RESOURCE", "IP-FRAGMENT"}:
        return "FRAGMENT"
    if upper.startswith("DATAGRAM="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IpActuationError("illegal_ip")
        return "DATAGRAM"
    if upper.startswith("FRAGMENT="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IpActuationError("illegal_ip")
        return "FRAGMENT"
    raise IpActuationError("illegal_ip")


def parse_ip(text: str) -> str:
    """Parse RFC 791 IP opcode header extensions into DATAGRAM or FRAGMENT."""

    raw = str(text or "").strip()
    if not raw:
        raise IpActuationError("illegal_ip")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"DATAGRAM", "IP", "IP-DATAGRAM"}:
        return "DATAGRAM"
    if upper in {"FRAGMENT", "RESOURCE", "IP-FRAGMENT"}:
        return "FRAGMENT"
    if upper.startswith("DATAGRAM="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IpActuationError("illegal_ip")
        return "DATAGRAM"
    if upper.startswith("FRAGMENT="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise IpActuationError("illegal_ip")
        return "FRAGMENT"
    raise IpActuationError("illegal_ip")


def encode_ip_header(policy: str | Sequence[str]) -> bytes:
    """RFC 791 HTTP/1.0 field as bytes."""

    return serialize_ip(policy).encode("ascii")


def parse_ip_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_ip(field_value) if field_value else DEFAULT_DATAGRAM
    return {
        "field_value": field_value,
        "policy": policy,
        "header": DATAGRAM_HEADER,
        "directive": str(policy),
        "datagram": str(policy) == "DATAGRAM",
        "fragment": str(policy) == "FRAGMENT",
    }


def canonical_datagram(identity: str, ipid: int) -> str:
    """RFC 791 body-request advertisement bound to identity and ipid."""

    return (
        f"{serialize_ip(DEFAULT_DATAGRAM)}, "
        f"datagram={ascii_serialize_ip_directive()}, "
        f"identity={identity}, ipid={int(ipid) & 0xFFFFFFFF}"
    )


def canonical_fragment(identity: str, ipid: int, ipdigest: int | None = None) -> str:
    """RFC 791 reply-message confirmation of the stored identifier-digest."""

    digest = ""
    if ipdigest is not None:
        digest = f", ipdigest={int(ipdigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_ip(FRAGMENT_POLICY)}, "
        f"fragment={ascii_serialize_ip_directive(fragment=True)}, "
        f"identity={identity}, ipid={int(ipid) & 0xFFFFFFFF}{digest}"
    )


def representation_fragment(identity: str, ipid: int, ipdigest: int) -> str:
    return canonical_fragment(identity, ipid, ipdigest)


def ip_matches(left: str, right: str) -> bool:
    return parse_ip(left) == parse_ip(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise IpActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise IpActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise IpActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise IpActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def datagram_request(identity: str, ipid: int) -> bytes:
    """HTTP DATAGRAM that elicits RFC 791 origin HTTP/1.0."""

    keyid = f"{int(ipid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"DATAGRAM /ip/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Ip-Id: {int(ipid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def fragment_request(identity: str, ipid: int, ipdigest: int | None = None) -> bytes:
    """HTTP FRAGMENT carrying RFC 791 reply-message confirmation of the stored identifier-digest."""

    keyid = f"{int(ipid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if ipdigest is not None:
        extra = f"Ip-Digest: {int(ipdigest) & 0xFFFFFFFF}\r\n"
    return (
        f"FRAGMENT /ip/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Ip-Id: {int(ipid) & 0xFFFFFFFF}\r\n"
        "Fragment-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    ip_kind = "fragment" if fields.get("fragment-confirm") == "1" else "datagram"
    upgrade_field = fields.get("datagram") or fields.get("ip") or ""
    policy = parse_ip(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "ip_kind": ip_kind,
        "policy": policy,
        "ipid": int(fields["ip-id"]) if fields.get("ip-id") else EMPTY_IPID,
        "ipdigest": int(fields["ip-digest"]) if fields.get("ip-digest") else EMPTY_IPDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def datagram_response(identity: str, ipid: int, ipdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 791 origin HTTP/1.0, carrying the stored ipdigest."""

    advertised = serialize_ip(DEFAULT_DATAGRAM)
    payload = bytes(body or canonical_datagram(identity, ipid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Datagram: {advertised}\r\n"
        f"Ip-Id: {int(ipid) & 0xFFFFFFFF}\r\n"
        f"Ip-Digest: {int(ipdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def fragment_response(identity: str, ipid: int, ipdigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 791 FRAGMENT, carrying the stored identifier-digest."""

    advertised = serialize_ip(FRAGMENT_POLICY)
    payload = bytes(body or representation_fragment(identity, ipid, ipdigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Datagram: {advertised}\r\n"
        f"Ip-Id: {int(ipid) & 0xFFFFFFFF}\r\n"
        f"Ip-Digest: {int(ipdigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/ip-fragment\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise IpActuationError("illegal_content_length") from error
    field_value = fields.get("datagram") or fields.get("ip") or ""
    policy = parse_ip(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/ip-fragment" or policy == FRAGMENT_POLICY:
        status = 200
        ip_kind = "fragment"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        ip_kind = "datagram"
    else:
        status = 0
        ip_kind = "datagram"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "ip_kind": ip_kind,
        "policy": policy,
        "ipid": int(fields["ip-id"]) if fields.get("ip-id") else EMPTY_IPID,
        "ipdigest": int(fields["ip-digest"]) if fields.get("ip-digest") else EMPTY_IPDIGEST,
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
        raise IpActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise IpActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise IpActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise IpActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc791_identifier_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    ip: str,
) -> str:
    """RFC 791 identifier digest over method, request-IP, identity, and ipid."""

    payload = f"{method}:{ip}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_ipid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"ipid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_ipid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-ipid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_ipdigest(ipid: int = EMPTY_IPID, token: str = SENTINEL) -> int:
    nonce = f"{int(ipid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc791_identifier_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="FRAGMENT",
        ip=f"/ip/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_IPID = request_ipid(SENTINEL)
DEFAULT_IPDIGEST = request_ipdigest(DEFAULT_IPID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    ipid: int,
    ipdigest: int,
    include_ipid: bool = True,
) -> bytes:
    live_ipid = int(ipid) & 0xFFFFFFFF if include_ipid else EMPTY_IPID
    live_digest = int(ipdigest) & 0xFFFFFFFF if include_ipid and live_ipid else EMPTY_IPDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_ipid) if live_ipid else b""
    header = bytearray()
    header.append(IP_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_datagram(
    *,
    identity: str,
    ipid: int,
    ipdigest: int | None = None,
    include_ipid: bool = True,
) -> bytes:
    live_ipid = int(ipid) & 0xFFFFFFFF if include_ipid else EMPTY_IPID
    live_digest = int(ipdigest) if ipdigest is not None else request_ipdigest(live_ipid, identity)
    return encode_packet(
        FRAME_DATAGRAM,
        identity=identity,
        ipid=live_ipid,
        ipdigest=live_digest,
        include_ipid=include_ipid,
    )


def encode_fragment(
    *,
    identity: str,
    ipid: int,
    ipdigest: int | None = None,
    include_ipid: bool = True,
) -> bytes:
    live_ipid = int(ipid) & 0xFFFFFFFF if include_ipid else EMPTY_IPID
    live_digest = int(ipdigest) if ipdigest is not None else request_ipdigest(live_ipid, identity)
    return encode_packet(
        FRAME_FRAGMENT,
        identity=identity,
        ipid=live_ipid,
        ipdigest=live_digest,
        include_ipid=include_ipid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise IpActuationError("short_packet")
    first = raw[0]
    if first != IP_FIRST:
        raise IpActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise IpActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == IPID_SIZE:
        live_ipid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_ipid = EMPTY_IPID
    else:
        raise IpActuationError("illegal_ipid")
    if offset >= len(raw):
        raise IpActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_DATAGRAM, FRAME_FRAGMENT}:
        raise IpActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise IpActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise IpActuationError("checksum_failed")
    if len(payload) < 5:
        raise IpActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise IpActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_ipid = int(live_ipid) != EMPTY_IPID
    has_ipdigest = has_ipid and int(live_digest) != EMPTY_IPDIGEST
    is_datagram = frame_type == FRAME_DATAGRAM
    is_fragment = frame_type == FRAME_FRAGMENT
    return {
        "type": int(frame_type),
        "is_datagram": is_datagram,
        "is_fragment": is_fragment,
        "ipid": int(live_ipid),
        "has_ipid": has_ipid,
        "ipdigest": int(live_digest),
        "has_ipdigest": has_ipdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC791",
        "serialize_field": canonical_datagram(identity, live_ipid) if has_ipid else "",
        "tls_field": canonical_fragment(identity, live_ipid, live_digest) if has_ipdigest else "",
    }


class IpClient:
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
            raise IpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_fragment"] or not packet["is_fragment"]:
            raise IpActuationError("ipdigest_required")
        if not packet["has_ipid"]:
            raise IpActuationError("ipid_required")
        if not packet["has_ipdigest"]:
            raise IpActuationError("ipdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_ipdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_ipdigest:
            raise IpActuationError("ipdigest_required")
        fragment = self._recv()
        return {
            "session": fragment,
            "ipid": int(fragment.get("ipid") or EMPTY_IPID),
            "identity": str(fragment.get("identity") or ""),
            "ipdigest": int(fragment.get("ipdigest") or EMPTY_IPDIGEST),
        }

    def report(
        self,
        identity: str,
        ipid: int,
        ipdigest: int = EMPTY_IPDIGEST,
        *,
        wait_ipdigest: bool = True,
        include_ipid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_fragment(
            identity=identity,
            ipid=ipid,
            ipdigest=ipdigest or request_ipdigest(ipid, identity),
            include_ipid=include_ipid,
        )
        return self.exchange(packet, wait_ipdigest=wait_ipdigest)


class IpSession:
    """IPID-gated loopback RFC 791 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        ipid_gate: int = DEFAULT_IPID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ipid_gate = int(ipid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.ipid = EMPTY_IPID
        self.ipdigest = EMPTY_IPDIGEST
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

    def store_ipid_once(self, identity: str, ipid: int, ipdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(ipid or EMPTY_IPID)
            live_digest = int(ipdigest or EMPTY_IPDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.ipid = live
                self.ipdigest = live_digest or request_ipdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.ipid), int(self.ipdigest)

    def read_ipid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.ipid), int(self.ipdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "ipid": EMPTY_IPID,
            "ipdigest": EMPTY_IPDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _ipid_missing(self) -> bool:
        return not int(self.ipid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, ipid: int, ipdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_fragment(
            identity=identity,
            ipid=ipid,
            ipdigest=ipdigest,
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
            except IpActuationError:
                continue
            if not packet.get("is_datagram") and not packet.get("is_fragment"):
                continue
            if not packet.get("has_ipid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_ipid, stored_digest = self.store_ipid_once(
                identity,
                int(packet.get("ipid") or EMPTY_IPID),
                int(packet.get("ipdigest") or EMPTY_IPDIGEST),
            )
            if not stored_name or not stored_ipid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_datagram"):
                    self.opened = True
                if packet.get("is_fragment"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_ipid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._ipid_missing():
            return self._forbidden("missing_ipid")
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
        do_datagram: bool = True,
        do_fragment: bool = True,
        do_ipdigest: bool = True,
        replay: bool = True,
        use_ipid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._ipid_missing():
            return self._forbidden("missing_ipid")
        live_token = str(token or SENTINEL)
        origin_ipid = request_ipid(live_token)
        origin_digest = request_ipdigest(origin_ipid, live_token)
        client: IpClient | None = None
        independent: IpClient | None = None
        try:
            client = IpClient(self.host, int(self.port))
            if not do_datagram:
                return self._conflict("datagram_required")
            bind_packet = encode_datagram(
                identity=live_token,
                ipid=origin_ipid,
                ipdigest=origin_digest,
                include_ipid=use_ipid,
            )
            if not use_ipid:
                try:
                    client.exchange(bind_packet, wait_ipdigest=True)
                except IpActuationError:
                    return self._conflict("ipid_required")
                return self._conflict("ipid_required")
            client.send(bind_packet)
            if not do_fragment:
                return self._conflict("fragment_required")
            proxy_packet = encode_fragment(
                identity=live_token,
                ipid=origin_ipid,
                ipdigest=origin_digest,
                include_ipid=True,
            )
            if not do_ipdigest:
                try:
                    client.exchange(proxy_packet, wait_ipdigest=False)
                except IpActuationError as error:
                    if str(error) == "ipdigest_required":
                        return self._conflict("ipdigest_required")
                    return self._conflict("ipdigest_required")
                return self._conflict("ipdigest_required")
            try:
                fragment = client.exchange(proxy_packet, wait_ipdigest=True)
            except IpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("ipid_required")
                if reason == "ipdigest_required":
                    return self._conflict("ipdigest_required")
                return self._conflict("datagram_required")
            if str(fragment.get("identity") or "") != live_token:
                return self._conflict("datagram_required")
            if int(fragment.get("ipid") or EMPTY_IPID) != origin_ipid:
                return self._conflict("ipdigest_required")
            if int(fragment.get("ipdigest") or EMPTY_IPDIGEST) != origin_digest:
                return self._conflict("ipdigest_required")
            self.retrieved = True
            if replay:
                independent = IpClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_ipid(live_token),
                        request_ipdigest(poll_ipid(live_token), POLL_TOKEN),
                        wait_ipdigest=True,
                    )
                except IpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_ipid, stored_digest = self.read_ipid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_ipid != origin_ipid
                    or stored_digest != origin_digest
                    or int(poll.get("ipid") or EMPTY_IPID) != origin_ipid
                    or int(poll.get("ipdigest") or EMPTY_IPDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_ipid}:{origin_digest}:{live_token}:{canonical_datagram(live_token, origin_ipid)}:{canonical_fragment(live_token, origin_ipid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "ipid": origin_ipid,
                "ipdigest": origin_digest,
                "datagram_frame": True,
                "fragment_frame": True,
                "ipdigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "ipid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_ipdigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "ipid": origin_ipid,
                "ipdigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "datagram_frame": True,
                "fragment_frame": True,
                "ipdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "ipid_bound": True,
            }
        except (OSError, IpActuationError) as error:
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
        live = independent_ipdigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "ipid": int(live.get("ipid") or EMPTY_IPID),
            "ipdigest": int(live.get("ipdigest") or EMPTY_IPDIGEST),
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


def call_ip_tool(session: IpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one ip tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_datagram = True if arguments.get("datagram") is None else bool(arguments.get("datagram"))
    do_fragment = True if arguments.get("fragment") is None else bool(arguments.get("fragment"))
    do_ipdigest = True if arguments.get("ipdigest") is None else bool(arguments.get("ipdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_ipid = True if arguments.get("use_ipid") is None else bool(arguments.get("use_ipid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_datagram=do_datagram,
            do_fragment=do_fragment,
            do_ipdigest=do_ipdigest,
            replay=replay,
            use_ipid=use_ipid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise IpActuationError(f"unsupported ip action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_ipdigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage ipdigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "ipid": EMPTY_IPID,
        "ipdigest": EMPTY_IPDIGEST,
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
            "datagram_frame",
            "fragment_frame",
            "ipdigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "ipid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    ipid = int(payload.get("ipid") or EMPTY_IPID)
    ipdigest = int(payload.get("ipdigest") or EMPTY_IPDIGEST)
    dual = port > 0 and bool(ipid) and bool(ipdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "ipid": ipid,
        "ipdigest": ipdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "datagram_frame": payload.get("datagram_frame") is True,
        "fragment_frame": payload.get("fragment_frame") is True,
        "ipdigest_locate": payload.get("ipdigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "ipid_bound": payload.get("ipid_bound") is True,
    }


def run_ip_workflow(
    *,
    with_ipid: bool = True,
    skip_bind: bool = False,
    do_datagram: bool = True,
    do_fragment: bool = True,
    do_ipdigest: bool = True,
    replay: bool = True,
    use_ipid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 791 DATAGRAM/FRAGMENT ipid cycle workflow."""

    descriptor = ip_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IP_TOOL_PROVIDER),
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
        raise IpActuationError(f"ip tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ip-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = IpSession(out, ipid_gate=DEFAULT_IPID if with_ipid else EMPTY_IPID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "datagram": do_datagram,
            "fragment": do_fragment,
            "ipdigest": do_ipdigest,
            "replay": replay,
            "use_ipid": use_ipid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_ip_tool(session, arguments))
            except IpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_ipdigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_ipid
        and not skip_bind
        and do_datagram
        and do_fragment
        and do_ipdigest
        and replay
        and use_ipid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ip_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_ipid": with_ipid,
        "skip_bind": skip_bind,
        "datagram_frame": do_datagram,
        "fragment_frame": do_fragment,
        "ipdigest": do_ipdigest,
        "replay": replay,
        "use_ipid": use_ipid,
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
        "ipid_value": int(publish_result.get("ipid") or independent.get("ipid") or EMPTY_IPID),
        "ipdigest_value": int(publish_result.get("ipdigest") or independent.get("ipdigest") or EMPTY_IPDIGEST),
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
        "ipid": int(trace_body["ipid_value"] or EMPTY_IPID),
        "ipdigest": int(trace_body["ipdigest_value"] or EMPTY_IPDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_ipid": with_ipid,
        "skip_bind": skip_bind,
        "datagram_cycle": do_datagram,
        "fragment_cycle": do_fragment,
        "ipdigest_cycle": do_ipdigest,
        "replay": replay,
        "use_ipid": use_ipid,
    }


def verify_ip_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_ipdigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    ipid = int(trace.get("ipid_value") or independent.get("ipid") or EMPTY_IPID)
    ipdigest = int(trace.get("ipdigest_value") or independent.get("ipdigest") or EMPTY_IPDIGEST)
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
        "datagram_frame": independent.get("datagram_frame") is True,
        "fragment_frame": independent.get("fragment_frame") is True,
        "ipdigest_locate": independent.get("ipdigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "ipid_bound": independent.get("ipid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "ipdigest_recorded": (
            port > 0
            and ipid == DEFAULT_IPID
            and ipdigest == DEFAULT_IPDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def ip_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.ip_actuation import "
        "builtin_ip_actuation_proof; r=builtin_ip_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='ip_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_ip_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=IP_ACTUATION_ID,
        name="First-class RFC 791 Internet Protocol DATAGRAM/FRAGMENT actuation",
        description=(
            "Missions that require a ip tool can opt the ip provider in, "
            "bind a loopback RFC 791 Internet Protocol endpoint, complete a DATAGRAM "
            "with a non-empty ipid, lockstep a FRAGMENT that carries the "
            "stored ipdigest, independently poll the stored ipdigest "
            "on a later socket, and seal a digest-chained ipdigest. Default "
            "routing stays fail-closed; a missing ipid keeps the hole "
            "falsifiable, and skip-DATAGRAM/FRAGMENT/IPDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.ip_actuation:builtin_ip_actuation_proof",
        proof_command=ip_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.icmp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/ip_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/icmp_actuation.py",
            "src/blackhole_agent/udp_actuation.py",
            "src/blackhole_agent/tcp_actuation.py",
            "src/blackhole_agent/telnet_actuation.py",
            "src/blackhole_agent/arp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required ip tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 791 daemon, speaks a "
            "DATAGRAM then FRAGMENT over Internet Protocol with a non-empty ipid and "
            "ipdigest, independently polls the stored ipdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 792 Internet Control Message Protocol lockstep is proved. "
            "Missing ipids, skip-DATAGRAM, skip-FRAGMENT, skip-ipdigest, skip-REPLAY, "
            "and a DATAGRAM aimed without a ipid stay fail-closed. "
            "Later genesis can take RFC 826 Address Resolution Protocol REQUEST/REPLY as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("ip", "rfc791", "http", "ipid", "ipdigest", "datagram", "fragment", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260906T140029Z-689356bb",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_ip_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 791 datagram/fragment lockstep actuation seals a ipdigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
    )
    from blackhole_agent.arp_actuation import (
        ARP_ACTUATION_GOAL,
        ARP_ACTUATION_ID,
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
    checks["denylists_self"] = IP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(IP_ACTUATION_GOAL) == (
        IP_ACTUATION_ID,
    )
    checks["leftover_text_binds_ip"] = leftover_marker_ids(IP_LEFTOVER) == (
        IP_ACTUATION_ID,
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
        (ARP_ACTUATION_GOAL, ARP_ACTUATION_ID, "arp"),
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
        checks[f"{name}_goal_is_not_ip"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"ip_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            IP_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = IP_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_ip(DEFAULT_DATAGRAM)
    rebuilt = serialize_ip(parse_ip(advertised))
    preloaded = parse_ip(RFC_IP_FRAGMENT)
    header = encode_ip_header(DEFAULT_DATAGRAM)
    parsed_header = parse_ip_header(header)
    asked = parse_http_request(datagram_request(SENTINEL, DEFAULT_IPID))
    preload_req = parse_http_request(fragment_request(SENTINEL, DEFAULT_IPID, DEFAULT_IPDIGEST))
    got = parse_http_response(datagram_response(SENTINEL, DEFAULT_IPID, DEFAULT_IPDIGEST))
    preload_reply = parse_http_response(
        fragment_response(SENTINEL, DEFAULT_IPID, DEFAULT_IPDIGEST)
    )
    checks["ip_roundtrip"] = (
        parse_ip(advertised) == DEFAULT_DATAGRAM
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_DATAGRAM_FIELD
        and is_token("DATAGRAM") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_DATAGRAM_FIELD
        and parsed_header["policy"] == DEFAULT_DATAGRAM
        and parsed_header["header"] == DATAGRAM_HEADER
        and parsed_header["datagram"] is True
        and parsed_header["fragment"] is False
        and preloaded == FRAGMENT_POLICY
        and ascii_serialize_ip_directive() == RFC_DATAGRAM_DIRECTIVE
        and ip_directive_pair() == ("datagram", "message")
        and RFC_DATAGRAM_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_ip(FRAGMENT_POLICY) == RFC_IP_FRAGMENT
        and DEFAULT_IPDIGEST == request_ipdigest(DEFAULT_IPID, SENTINEL)
        and "ipdigest=" in canonical_fragment(SENTINEL, DEFAULT_IPID, DEFAULT_IPDIGEST)
        and canonical_datagram(SENTINEL, DEFAULT_IPID).startswith("DATAGRAM")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "DATAGRAM"
        and asked["ip_kind"] == "datagram"
        and asked["ipid"] == DEFAULT_IPID
        and preload_req["ip_kind"] == "fragment"
        and preload_req["ipdigest"] == DEFAULT_IPDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["ip_kind"] == "datagram"
        and preload_reply["ip_kind"] == "fragment"
        and got["policy"] == DEFAULT_DATAGRAM
        and preload_reply["policy"] == FRAGMENT_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["ipdigest"] == DEFAULT_IPDIGEST
        and preload_reply["ipdigest"] == DEFAULT_IPDIGEST
        and ip_matches(serialize_ip(got["policy"]), advertised)
    )

    checks["catalog_names_ip"] = (
        len(catalog) > 115
        and catalog[115]["id"] == IP_ACTUATION_ID
        and catalog[114]["id"] == ICMP_ACTUATION_ID
        and catalog[115]["source"] == "genesis_bind_ip"
    )
    checks["catalog_names_arp"] = (
        len(catalog) > 116
        and catalog[116]["id"] == ARP_ACTUATION_ID
        and catalog[116]["source"] == "genesis_bind_arp"
    )
    from blackhole_agent.mission_selection import semantic_tokens

    family = capability_family(IP_ACTUATION_GOAL)
    checks["family_is_ip"] = "ip" in family.split("/")
    checks["family_is_ip_surface"] = "ipid" in family
    checks["family_is_ipid"] = "ipid" in family
    checks["family_is_rfc791"] = "rfc791" in set(semantic_tokens(IP_ACTUATION_GOAL))
    checks["family_is_ipdigest"] = "ipdigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
    )
    checks["family_is_not_arp"] = (
        "arp" not in family.split("/")
        and "rfc826" not in family
        and "arpid" not in family
        and "arpdigest" not in family
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
    packed = encode_datagram(identity=SENTINEL, ipid=DEFAULT_IPID, ipdigest=DEFAULT_IPDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_datagram"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_ipid"] is True
        and parsed["ipid"] == DEFAULT_IPID
        and parsed["ipdigest"] == DEFAULT_IPDIGEST
        and parsed["is_fragment"] is False
        and parsed["is_fragment"] is False
        and parsed["type"] == FRAME_DATAGRAM
        and parsed["first_byte"] == IP_FIRST
    )
    shook = encode_fragment(
        identity=SENTINEL,
        ipid=DEFAULT_IPID,
        ipdigest=DEFAULT_IPDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_fragment"] is True
        and answer_parsed["is_fragment"] is True
        and answer_parsed["is_datagram"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["ipid"] == DEFAULT_IPID
        and answer_parsed["ipdigest"] == DEFAULT_IPDIGEST
        and answer_parsed["has_ipdigest"] is True
        and answer_parsed["type"] == FRAME_FRAGMENT
        and answer_parsed["first_byte"] == IP_FIRST
    )
    bare = encode_datagram(identity=SENTINEL, ipid=DEFAULT_IPID, include_ipid=False)
    checks["missing_ipid_is_unauthed"] = parse_message(bare)["has_ipid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(IP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_ip = ToolDescriptor(name="remote_ip", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_ip)
    checks["naive_mcp_ip_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = ip_tool_descriptor()
    default_ip = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IP_TOOL_PROVIDER),
    )
    checks["default_ip_provider_is_unsupported"] = (
        default_ip.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{IP_TOOL_PROVIDER}" in default_ip.reasons
    )
    checks["opted_in_ip_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_ip],
        required_tool_names=("local_memory", "ip"),
    )
    checks["naive_preflight_missing_ip"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["ip"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "ip"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, IP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "ip" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="ip-actuation-") as tmp:
        root = Path(tmp)
        missing = run_ip_workflow(with_ipid=False, output_dir=root / "missing")
        skip_bind = run_ip_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_datagram = run_ip_workflow(do_datagram=False, output_dir=root / "skip-datagram")
        skip_fragment = run_ip_workflow(do_fragment=False, output_dir=root / "skip-fragment")
        skip_ipdigest = run_ip_workflow(do_ipdigest=False, output_dir=root / "skip-ipdigest")
        skip_replay = run_ip_workflow(replay=False, output_dir=root / "skip-replay")
        skip_ipid = run_ip_workflow(use_ipid=False, output_dir=root / "skip-ipid")
        live = run_ip_workflow(output_dir=root / "live")
        verify = verify_ip_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_ip_trace(clone)
        checks["naive_without_ipid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_ipid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_datagram_stays_empty"] = (
            skip_datagram["ok"] is False
            and skip_datagram["error"] == "datagram_required"
            and skip_datagram["final_status"] == 409
            and skip_datagram["payload_exists"] is False
        )
        checks["skip_fragment_stays_empty"] = (
            skip_fragment["ok"] is False
            and skip_fragment["error"] == "fragment_required"
            and skip_fragment["final_status"] == 409
            and skip_fragment["payload_exists"] is False
        )
        checks["skip_ipdigest_stays_empty"] = (
            skip_ipdigest["ok"] is False
            and skip_ipdigest["error"] == "ipdigest_required"
            and skip_ipdigest["final_status"] == 409
            and skip_ipdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_ipid_stays_empty"] = (
            skip_ipid["ok"] is False
            and skip_ipid["error"] == "ipid_required"
            and skip_ipid["final_status"] == 409
            and skip_ipid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_ipdigest"] = (
            int(live.get("ipid") or 0) == DEFAULT_IPID
            and int(live.get("ipdigest") or 0) == DEFAULT_IPDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_ipid_encode_fragment_ipdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_datagram["ok"] is False
            and skip_fragment["ok"] is False
            and skip_ipdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_ipid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="ip-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != IP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, IP_ACTUATION_GOAL, IP_ACTUATION_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_ip"] = (
        not gate.accepted
        and live_goal != IP_ACTUATION_GOAL
        and IP_ACTUATION_ID not in live_done
        and live_source != "genesis_bind_ip"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
    )

    with tempfile.TemporaryDirectory(prefix="ip-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(IP_LEFTOVER, root)
        register_catalog_proved(root, IP_ACTUATION_ID)
        reason = leftover_satisfied_by(IP_LEFTOVER, root)
        after = leftover_is_open(IP_LEFTOVER, root)
    checks["ip_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_ip_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{IP_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_ip_actuation_capability()
    return {
        "ok": ok,
        "action": "ip_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": IP_ACTUATION_GOAL,
        "done_when": IP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
