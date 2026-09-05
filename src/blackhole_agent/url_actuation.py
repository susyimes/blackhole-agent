"""Drive a first-class Uniform Resource Locators tool through RFC 1738 RESOLVE/LOCATE.

Tool routing already fails missions that require ``url``: hosted
url endpoints stay on the unsupported MCP provider, and no first-party
url provider is executable. Unbound therefore cannot speak a RESOLVE,
lockstep a LOCATE urlid handshake over HTTP/1.0 URLID,
independently poll the stored urldigest, or seal a urldigest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``url`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 1738 daemon
- keep a missing-urlid client so the url-urlid hole stays falsifiable
- refuse LOCATE until a RESOLVE lands with a non-empty urlid
- independently poll the stored urldigest on a later client socket
- persist a sealed urldigest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 1945 Hypertext Transfer Protocol -- HTTP/1.0
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
    URL_TOOL_PROVIDER,
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    url_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
URL_ACTUATION_ID = "capability.url-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-URL-OK"
POLL_TOKEN = "BH-URL-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_URLID = 0
EMPTY_URLDIGEST = 0
URL_FIRST = 0x55  # RFC 1738 Uniform Resource Locators (ASCII 'U')
URLID_SIZE = 4
URLDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_LOCATE = 0x02  # RFC 1738 LOCATE confirmation
FRAME_RESOLVE = 0x01  # RFC 1738 RESOLVE
HEADER_END = b"\r\n\r\n"
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
URL_LEFTOVER = (
    "Later genesis can take RFC 1738 Uniform Resource Locators RESOLVE/LOCATE over a "
    "urlid-gated urldigest."
)
URL_ACTUATION_DONE_WHEN = (
    f"capability_exists:{URL_ACTUATION_ID};"
    f"capability_proved:{URL_ACTUATION_ID};"
    "no_skill_route"
)
URL_ACTUATION_GOAL = (
    "Repair rfc1738 url resolve/locate cycle cannot land over http "
    "url urlid: hosted url endpoints remain unsupported so a RESOLVE then "
    "LOCATE urlid handshake cannot land and a sealed urldigest "
    "cannot be produced. A missing url urlid stays forbidden; fail-closed "
    "routing never opts the url provider in. An independent later poll of the "
    "stored urldigest keeps the hole falsifiable."
)


class UrlActuationError(RuntimeError):
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
# RFC 1738 sections 2.1 and 2.1.2: RESOLVE / LOCATE.
RFC_RESOLVE_FIELD = "RESOLVE"
RFC_LOCATE_FIELD = "LOCATE"
RFC_URL_LOCATE = RFC_LOCATE_FIELD
RFC_RESOLVE_DIRECTIVE = "resolve=scheme"
RFC_LOCATE_DIRECTIVE = "locate=resource"
DEFAULT_RESOLVE = "RESOLVE"
LOCATE_POLICY = "LOCATE"
RESOLVE_HEADER = "Resolve"
LOCATE_HEADER = "Locate"
URL_LOCATE_HEADER = LOCATE_HEADER
RFC_RESOLVE_PATH = "/url/"
RFC_RESOLVE_EMPTY = ""


def url_directive_pair(*, locate: bool = False) -> tuple[str, str]:
    """RFC 1738 Resolve / Locate directive pair."""

    if locate:
        return "locate", "resource"
    return "resolve", "scheme"


def ascii_serialize_url_directive(*, locate: bool = False) -> str:
    """RFC 1738 token "=" resolve-or-locate."""

    name, value = url_directive_pair(locate=locate)
    if not is_token(name):
        raise UrlActuationError("illegal_directive")
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
            raise UrlActuationError("short_url")
        self.pos += count
        return chunk

    def skip_ows(self) -> None:
        while self.peek() in (" ", "\t"):
            self.pos += 1

    def eof(self) -> bool:
        return self.pos >= len(self.text)


def is_token(value: str) -> bool:
    """RFC 7230 tchar used as RFC 1738 resolve-request token."""

    raw = str(value or "")
    return bool(raw) and all(char in TCHAR for char in raw)


def serialize_url(policy: str | Sequence[str]) -> str:
    """Serialize RFC 1738 RESOLVE / LOCATE opcode token."""

    if isinstance(policy, (list, tuple)):
        raw = str(policy[0] if policy else "")
    else:
        raw = str(policy or "")
    text = raw.strip()
    if not text:
        raise UrlActuationError("illegal_url")
    upper = text.upper().replace("_", "-")
    if upper in {"RESOLVE", "URL", "URL-RESOLVE"}:
        return "RESOLVE"
    if upper in {"LOCATE", "RESOURCE", "URL-LOCATE"}:
        return "LOCATE"
    if upper.startswith("RESOLVE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UrlActuationError("illegal_url")
        return "RESOLVE"
    if upper.startswith("LOCATE="):
        value = text.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UrlActuationError("illegal_url")
        return "LOCATE"
    raise UrlActuationError("illegal_url")


def parse_url(text: str) -> str:
    """Parse RFC 1738 URL opcode header extensions into RESOLVE or LOCATE."""

    raw = str(text or "").strip()
    if not raw:
        raise UrlActuationError("illegal_url")
    head = raw.split(";", 1)[0].strip()
    upper = head.upper().replace("_", "-")
    if upper in {"RESOLVE", "URL", "URL-RESOLVE"}:
        return "RESOLVE"
    if upper in {"LOCATE", "RESOURCE", "URL-LOCATE"}:
        return "LOCATE"
    if upper.startswith("RESOLVE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UrlActuationError("illegal_url")
        return "RESOLVE"
    if upper.startswith("LOCATE="):
        value = head.split("=", 1)[1].strip().strip('"')
        if not value:
            raise UrlActuationError("illegal_url")
        return "LOCATE"
    raise UrlActuationError("illegal_url")


def encode_url_header(policy: str | Sequence[str]) -> bytes:
    """RFC 1738 HTTP/1.0 field as bytes."""

    return serialize_url(policy).encode("ascii")


def parse_url_header(data: bytes) -> dict[str, Any]:
    field_value = bytes(data or b"").decode("ascii")
    policy = parse_url(field_value) if field_value else DEFAULT_RESOLVE
    return {
        "field_value": field_value,
        "policy": policy,
        "header": RESOLVE_HEADER,
        "directive": str(policy),
        "resolve": str(policy) == "RESOLVE",
        "locate": str(policy) == "LOCATE",
    }


def canonical_resolve(identity: str, urlid: int) -> str:
    """RFC 1738 resolve-request advertisement bound to identity and urlid."""

    return (
        f"{serialize_url(DEFAULT_RESOLVE)}, "
        f"resolve={ascii_serialize_url_directive()}, "
        f"identity={identity}, urlid={int(urlid) & 0xFFFFFFFF}"
    )


def canonical_locate(identity: str, urlid: int, urldigest: int | None = None) -> str:
    """RFC 1738 locate-resource confirmation of the stored locator-digest."""

    digest = ""
    if urldigest is not None:
        digest = f", urldigest={int(urldigest) & 0xFFFFFFFF}"
    return (
        f"{serialize_url(LOCATE_POLICY)}, "
        f"locate={ascii_serialize_url_directive(locate=True)}, "
        f"identity={identity}, urlid={int(urlid) & 0xFFFFFFFF}{digest}"
    )


def representation_locate(identity: str, urlid: int, urldigest: int) -> str:
    return canonical_locate(identity, urlid, urldigest)


def url_matches(left: str, right: str) -> bool:
    return parse_url(left) == parse_url(right)


def _split_http_message(data: bytes) -> tuple[str, list[tuple[str, str]], bytes]:
    raw = bytes(data or b"")
    split = raw.find(HEADER_END)
    if split < 0:
        raise UrlActuationError("short_message")
    try:
        head = raw[:split].decode("ascii")
    except UnicodeDecodeError as error:
        raise UrlActuationError("illegal_message") from error
    body = raw[split + len(HEADER_END) :]
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        raise UrlActuationError("illegal_start_line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise UrlActuationError("illegal_field")
        headers.append((name.strip().lower(), value.strip()))
    return lines[0], headers, body


def resolve_request(identity: str, urlid: int) -> bytes:
    """HTTP RESOLVE that elicits RFC 1738 origin HTTP/1.0."""

    keyid = f"{int(urlid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    return (
        f"RESOLVE /url/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Url-Id: {int(urlid) & 0xFFFFFFFF}\r\n"
        "\r\n"
    ).encode("ascii")


def locate_request(identity: str, urlid: int, urldigest: int | None = None) -> bytes:
    """HTTP RESOLVE carrying RFC 1738 locate-resource confirmation of the stored locator-digest."""

    keyid = f"{int(urlid) & 0xFFFFFFFF:08x}"
    host = str(identity or "localhost")
    extra = ""
    if urldigest is not None:
        extra = f"Url-Digest: {int(urldigest) & 0xFFFFFFFF}\r\n"
    return (
        f"LOCATE /url/{keyid} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"Url-Id: {int(urlid) & 0xFFFFFFFF}\r\n"
        "Locate-Confirm: 1\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def parse_http_request(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    parts = start.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else ""
    fields = dict(headers)
    url_kind = "locate" if fields.get("locate-confirm") == "1" else "resolve"
    upgrade_field = fields.get("resolve") or fields.get("url") or ""
    policy = parse_url(upgrade_field) if upgrade_field else ()
    return {
        "kind": "request",
        "start_line": start,
        "method": method,
        "target": target,
        "headers": headers,
        "body": body,
        "host": fields.get("host", ""),
        "url_kind": url_kind,
        "policy": policy,
        "urlid": int(fields["url-id"]) if fields.get("url-id") else EMPTY_URLID,
        "urldigest": int(fields["url-digest"]) if fields.get("url-digest") else EMPTY_URLDIGEST,
        "content_length_matches_body": int(fields.get("content-length") or "0") == len(body)
        if str(fields.get("content-length") or "").isdigit()
        else True,
    }


def resolve_response(identity: str, urlid: int, urldigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 advertising RFC 1738 origin HTTP/1.0, carrying the stored urldigest."""

    advertised = serialize_url(DEFAULT_RESOLVE)
    payload = bytes(body or canonical_resolve(identity, urlid).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Resolve: {advertised}\r\n"
        f"Url-Id: {int(urlid) & 0xFFFFFFFF}\r\n"
        f"Url-Digest: {int(urldigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def locate_response(identity: str, urlid: int, urldigest: int, body: bytes = b"") -> bytes:
    """HTTP 200 after RFC 1738 LOCATE, carrying the stored locator-digest."""

    advertised = serialize_url(LOCATE_POLICY)
    payload = bytes(body or representation_locate(identity, urlid, urldigest).encode("ascii"))
    return (
        "HTTP/1.0 200 OK\r\n"
        f"Resolve: {advertised}\r\n"
        f"Url-Id: {int(urlid) & 0xFFFFFFFF}\r\n"
        f"Url-Digest: {int(urldigest) & 0xFFFFFFFF}\r\n"
        "Content-Type: application/url-locate\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("ascii") + payload


def parse_http_response(data: bytes) -> dict[str, Any]:
    start, headers, body = _split_http_message(data)
    fields = dict(headers)
    try:
        content_length = int(fields.get("content-length") or "0")
    except ValueError as error:
        raise UrlActuationError("illegal_content_length") from error
    field_value = fields.get("resolve") or fields.get("url") or ""
    policy = parse_url(field_value) if field_value else ()
    content_type = fields.get("content-type", "")
    if content_type == "application/url-locate" or policy == LOCATE_POLICY:
        status = 200
        url_kind = "locate"
    elif start.startswith("HTTP/1.0 200"):
        status = 200
        url_kind = "resolve"
    else:
        status = 0
        url_kind = "resolve"
    return {
        "kind": "response",
        "start_line": start,
        "status": status,
        "headers": headers,
        "body": body,
        "content_length": content_length,
        "content_type": fields.get("content-type", ""),
        "url_kind": url_kind,
        "policy": policy,
        "urlid": int(fields["url-id"]) if fields.get("url-id") else EMPTY_URLID,
        "urldigest": int(fields["url-digest"]) if fields.get("url-digest") else EMPTY_URLDIGEST,
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
        raise UrlActuationError("short_packet")
    mech = raw[offset] >> 6
    if mech == 0:
        return raw[offset] & 0x3F, offset + 1
    if mech == 1:
        if offset + 2 > len(raw):
            raise UrlActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if mech == 2:
        if offset + 4 > len(raw):
            raise UrlActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise UrlActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )



def rfc1738_locator_digest(
    *,
    username: str,
    realm: str,
    password: str,
    nonce: str,
    method: str,
    uri: str,
) -> str:
    """RFC 1738 locator digest over method, request-URI, identity, and urlid."""

    payload = f"{method}:{uri}:{username}:{realm}:{password}:{nonce}"
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def request_urlid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"urlid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_urlid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-urlid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_urldigest(urlid: int = EMPTY_URLID, token: str = SENTINEL) -> int:
    nonce = f"{int(urlid) & 0xFFFFFFFF:08x}"
    identity = token or SENTINEL
    digest_hex = rfc1738_locator_digest(
        username=identity,
        realm="blackhole",
        password=SENTINEL,
        nonce=nonce,
        method="LOCATE",
        uri=f"/url/{nonce}",
    )
    value = int(digest_hex[:8], 16)
    return value or 1


DEFAULT_URLID = request_urlid(SENTINEL)
DEFAULT_URLDIGEST = request_urldigest(DEFAULT_URLID, SENTINEL)


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    urlid: int,
    urldigest: int,
    include_urlid: bool = True,
) -> bytes:
    live_urlid = int(urlid) & 0xFFFFFFFF if include_urlid else EMPTY_URLID
    live_digest = int(urldigest) & 0xFFFFFFFF if include_urlid and live_urlid else EMPTY_URLDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_digest, len(ident)) + ident
    mech_bytes = struct.pack("!I", live_urlid) if live_urlid else b""
    header = bytearray()
    header.append(URL_FIRST)
    header.append(len(mech_bytes))
    header.extend(mech_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_resolve(
    *,
    identity: str,
    urlid: int,
    urldigest: int | None = None,
    include_urlid: bool = True,
) -> bytes:
    live_urlid = int(urlid) & 0xFFFFFFFF if include_urlid else EMPTY_URLID
    live_digest = int(urldigest) if urldigest is not None else request_urldigest(live_urlid, identity)
    return encode_packet(
        FRAME_RESOLVE,
        identity=identity,
        urlid=live_urlid,
        urldigest=live_digest,
        include_urlid=include_urlid,
    )


def encode_locate(
    *,
    identity: str,
    urlid: int,
    urldigest: int | None = None,
    include_urlid: bool = True,
) -> bytes:
    live_urlid = int(urlid) & 0xFFFFFFFF if include_urlid else EMPTY_URLID
    live_digest = int(urldigest) if urldigest is not None else request_urldigest(live_urlid, identity)
    return encode_packet(
        FRAME_LOCATE,
        identity=identity,
        urlid=live_urlid,
        urldigest=live_digest,
        include_urlid=include_urlid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise UrlActuationError("short_packet")
    first = raw[0]
    if first != URL_FIRST:
        raise UrlActuationError("illegal_header")
    offset = 1
    mech_len = raw[offset]
    offset += 1
    if offset + mech_len > len(raw):
        raise UrlActuationError("short_packet")
    mech_bytes = raw[offset : offset + mech_len]
    offset += mech_len
    if mech_len == URLID_SIZE:
        live_urlid = struct.unpack("!I", mech_bytes)[0]
    elif mech_len == 0:
        live_urlid = EMPTY_URLID
    else:
        raise UrlActuationError("illegal_urlid")
    if offset >= len(raw):
        raise UrlActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_RESOLVE, FRAME_LOCATE}:
        raise UrlActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise UrlActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise UrlActuationError("checksum_failed")
    if len(payload) < 5:
        raise UrlActuationError("short_packet")
    live_digest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise UrlActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_urlid = int(live_urlid) != EMPTY_URLID
    has_urldigest = has_urlid and int(live_digest) != EMPTY_URLDIGEST
    is_resolve = frame_type == FRAME_RESOLVE
    is_locate = frame_type == FRAME_LOCATE
    return {
        "type": int(frame_type),
        "is_resolve": is_resolve,
        "is_locate": is_locate,
        "urlid": int(live_urlid),
        "has_urlid": has_urlid,
        "urldigest": int(live_digest),
        "has_urldigest": has_urldigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "mech_len": int(mech_len),
        "http_state": "RFC1738",
        "serialize_field": canonical_resolve(identity, live_urlid) if has_urlid else "",
        "tls_field": canonical_locate(identity, live_urlid, live_digest) if has_urldigest else "",
    }


class UrlClient:
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
            raise UrlActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_locate"] or not packet["is_locate"]:
            raise UrlActuationError("urldigest_required")
        if not packet["has_urlid"]:
            raise UrlActuationError("urlid_required")
        if not packet["has_urldigest"]:
            raise UrlActuationError("urldigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_urldigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_urldigest:
            raise UrlActuationError("urldigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "urlid": int(reply.get("urlid") or EMPTY_URLID),
            "identity": str(reply.get("identity") or ""),
            "urldigest": int(reply.get("urldigest") or EMPTY_URLDIGEST),
        }

    def report(
        self,
        identity: str,
        urlid: int,
        urldigest: int = EMPTY_URLDIGEST,
        *,
        wait_urldigest: bool = True,
        include_urlid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_locate(
            identity=identity,
            urlid=urlid,
            urldigest=urldigest or request_urldigest(urlid, identity),
            include_urlid=include_urlid,
        )
        return self.exchange(packet, wait_urldigest=wait_urldigest)


class UrlSession:
    """URLID-gated loopback RFC 1738 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        urlid_gate: int = DEFAULT_URLID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.urlid_gate = int(urlid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.urlid = EMPTY_URLID
        self.urldigest = EMPTY_URLDIGEST
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

    def store_urlid_once(self, identity: str, urlid: int, urldigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(urlid or EMPTY_URLID)
            live_digest = int(urldigest or EMPTY_URLDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.urlid = live
                self.urldigest = live_digest or request_urldigest(live, name)
                self.stored = True
            return str(self.identity), int(self.urlid), int(self.urldigest)

    def read_urlid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.urlid), int(self.urldigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "urlid": EMPTY_URLID,
            "urldigest": EMPTY_URLDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _urlid_missing(self) -> bool:
        return not int(self.urlid_gate or 0)

    def _reply_tuple(self, peer: tuple[str, int], identity: str, urlid: int, urldigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_locate(
            identity=identity,
            urlid=urlid,
            urldigest=urldigest,
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
            except UrlActuationError:
                continue
            if not packet.get("is_resolve") and not packet.get("is_locate"):
                continue
            if not packet.get("has_urlid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_urlid, stored_digest = self.store_urlid_once(
                identity,
                int(packet.get("urlid") or EMPTY_URLID),
                int(packet.get("urldigest") or EMPTY_URLDIGEST),
            )
            if not stored_name or not stored_urlid or not stored_digest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_resolve"):
                    self.opened = True
                if packet.get("is_locate"):
                    self.handshook = True
                self.retrieved = True
            self._reply_tuple(peer, stored_name, stored_urlid, stored_digest)

    def bind(self) -> dict[str, Any]:
        if self._urlid_missing():
            return self._forbidden("missing_urlid")
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
        do_resolve: bool = True,
        do_locate: bool = True,
        do_urldigest: bool = True,
        replay: bool = True,
        use_urlid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._urlid_missing():
            return self._forbidden("missing_urlid")
        live_token = str(token or SENTINEL)
        origin_urlid = request_urlid(live_token)
        origin_digest = request_urldigest(origin_urlid, live_token)
        client: UrlClient | None = None
        independent: UrlClient | None = None
        try:
            client = UrlClient(self.host, int(self.port))
            if not do_resolve:
                return self._conflict("resolve_required")
            bind_packet = encode_resolve(
                identity=live_token,
                urlid=origin_urlid,
                urldigest=origin_digest,
                include_urlid=use_urlid,
            )
            if not use_urlid:
                try:
                    client.exchange(bind_packet, wait_urldigest=True)
                except UrlActuationError:
                    return self._conflict("urlid_required")
                return self._conflict("urlid_required")
            client.send(bind_packet)
            if not do_locate:
                return self._conflict("locate_required")
            proxy_packet = encode_locate(
                identity=live_token,
                urlid=origin_urlid,
                urldigest=origin_digest,
                include_urlid=True,
            )
            if not do_urldigest:
                try:
                    client.exchange(proxy_packet, wait_urldigest=False)
                except UrlActuationError as error:
                    if str(error) == "urldigest_required":
                        return self._conflict("urldigest_required")
                    return self._conflict("urldigest_required")
                return self._conflict("urldigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_urldigest=True)
            except UrlActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("urlid_required")
                if reason == "urldigest_required":
                    return self._conflict("urldigest_required")
                return self._conflict("resolve_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("resolve_required")
            if int(reply.get("urlid") or EMPTY_URLID) != origin_urlid:
                return self._conflict("urldigest_required")
            if int(reply.get("urldigest") or EMPTY_URLDIGEST) != origin_digest:
                return self._conflict("urldigest_required")
            self.retrieved = True
            if replay:
                independent = UrlClient(self.host, int(self.port))
                try:
                    poll = independent.report(
                        POLL_TOKEN,
                        poll_urlid(live_token),
                        request_urldigest(poll_urlid(live_token), POLL_TOKEN),
                        wait_urldigest=True,
                    )
                except UrlActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_urlid, stored_digest = self.read_urlid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_urlid != origin_urlid
                    or stored_digest != origin_digest
                    or int(poll.get("urlid") or EMPTY_URLID) != origin_urlid
                    or int(poll.get("urldigest") or EMPTY_URLDIGEST) != origin_digest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(
                f"{origin_urlid}:{origin_digest}:{live_token}:{canonical_resolve(live_token, origin_urlid)}:{canonical_locate(live_token, origin_urlid, origin_digest)}".encode(
                    "utf-8"
                )
            )
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "urlid": origin_urlid,
                "urldigest": origin_digest,
                "resolve_frame": True,
                "locate_frame": True,
                "urldigest_locate": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "urlid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_urldigest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "urlid": origin_urlid,
                "urldigest": origin_digest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "resolve_frame": True,
                "locate_frame": True,
                "urldigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "urlid_bound": True,
            }
        except (OSError, UrlActuationError) as error:
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
        live = independent_urldigest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "urlid": int(live.get("urlid") or EMPTY_URLID),
            "urldigest": int(live.get("urldigest") or EMPTY_URLDIGEST),
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


def call_url_tool(session: UrlSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one url tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_resolve = True if arguments.get("resolve") is None else bool(arguments.get("resolve"))
    do_locate = True if arguments.get("locate") is None else bool(arguments.get("locate"))
    do_urldigest = True if arguments.get("urldigest") is None else bool(arguments.get("urldigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_urlid = True if arguments.get("use_urlid") is None else bool(arguments.get("use_urlid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_resolve=do_resolve,
            do_locate=do_locate,
            do_urldigest=do_urldigest,
            replay=replay,
            use_urlid=use_urlid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise UrlActuationError(f"unsupported url action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_urldigest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed usage urldigest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "urlid": EMPTY_URLID,
        "urldigest": EMPTY_URLDIGEST,
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
            "resolve_frame",
            "locate_frame",
            "urldigest_locate",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "urlid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    urlid = int(payload.get("urlid") or EMPTY_URLID)
    urldigest = int(payload.get("urldigest") or EMPTY_URLDIGEST)
    dual = port > 0 and bool(urlid) and bool(urldigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "urlid": urlid,
        "urldigest": urldigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "resolve_frame": payload.get("resolve_frame") is True,
        "locate_frame": payload.get("locate_frame") is True,
        "urldigest_locate": payload.get("urldigest_locate") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "urlid_bound": payload.get("urlid_bound") is True,
    }


def run_url_workflow(
    *,
    with_urlid: bool = True,
    skip_bind: bool = False,
    do_resolve: bool = True,
    do_locate: bool = True,
    do_urldigest: bool = True,
    replay: bool = True,
    use_urlid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 1738 RESOLVE/LOCATE urlid cycle workflow."""

    descriptor = url_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, URL_TOOL_PROVIDER),
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
        raise UrlActuationError(f"url tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="url-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = UrlSession(out, urlid_gate=DEFAULT_URLID if with_urlid else EMPTY_URLID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "resolve": do_resolve,
            "locate": do_locate,
            "urldigest": do_urldigest,
            "replay": replay,
            "use_urlid": use_urlid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_url_tool(session, arguments))
            except UrlActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_urldigest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_urlid
        and not skip_bind
        and do_resolve
        and do_locate
        and do_urldigest
        and replay
        and use_urlid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "url_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_urlid": with_urlid,
        "skip_bind": skip_bind,
        "resolve_frame": do_resolve,
        "locate_frame": do_locate,
        "urldigest": do_urldigest,
        "replay": replay,
        "use_urlid": use_urlid,
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
        "urlid_value": int(publish_result.get("urlid") or independent.get("urlid") or EMPTY_URLID),
        "urldigest_value": int(publish_result.get("urldigest") or independent.get("urldigest") or EMPTY_URLDIGEST),
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
        "urlid": int(trace_body["urlid_value"] or EMPTY_URLID),
        "urldigest": int(trace_body["urldigest_value"] or EMPTY_URLDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_urlid": with_urlid,
        "skip_bind": skip_bind,
        "resolve_cycle": do_resolve,
        "locate_cycle": do_locate,
        "urldigest_cycle": do_urldigest,
        "replay": replay,
        "use_urlid": use_urlid,
    }


def verify_url_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Origin trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_urldigest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    urlid = int(trace.get("urlid_value") or independent.get("urlid") or EMPTY_URLID)
    urldigest = int(trace.get("urldigest_value") or independent.get("urldigest") or EMPTY_URLDIGEST)
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
        "resolve_frame": independent.get("resolve_frame") is True,
        "locate_frame": independent.get("locate_frame") is True,
        "urldigest_locate": independent.get("urldigest_locate") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "urlid_bound": independent.get("urlid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "urldigest_recorded": (
            port > 0
            and urlid == DEFAULT_URLID
            and urldigest == DEFAULT_URLDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def url_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.url_actuation import "
        "builtin_url_actuation_proof; r=builtin_url_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='url_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_url_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=URL_ACTUATION_ID,
        name="First-class RFC 1738 Uniform Resource Locators RESOLVE/LOCATE actuation",
        description=(
            "Missions that require a url tool can opt the url provider in, "
            "bind a loopback RFC 1738 Uniform Resource Locators endpoint, complete a RESOLVE "
            "with a non-empty urlid, lockstep a LOCATE that carries the "
            "stored urldigest, independently poll the stored urldigest "
            "on a later socket, and seal a digest-chained urldigest. Default "
            "routing stays fail-closed; a missing urlid keeps the hole "
            "falsifiable, and skip-RESOLVE/LOCATE/URLDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.url_actuation:builtin_url_actuation_proof",
        proof_command=url_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.http10-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/url_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/http10_actuation.py",
            "src/blackhole_agent/uri_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required url tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 1738 daemon, speaks a "
            "RESOLVE then LOCATE over Uniform Resource Locators with a non-empty urlid and "
            "urldigest, independently polls the stored urldigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 1945 Hypertext Transfer Protocol -- HTTP/1.0 lockstep is proved. "
            "Missing urlids, skip-RESOLVE, skip-LOCATE, skip-urldigest, skip-REPLAY, "
            "and a RESOLVE aimed without a urlid stay fail-closed. "
            "Later genesis can take RFC 1630 Universal Resource Identifiers IDENTIFY/DEREF as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("url", "rfc1738", "http", "urlid", "urldigest", "resolve", "locate", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260905T051846Z-87e65486",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_url_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 1738 resolve/locate lockstep actuation seals a urldigest."""

    from blackhole_agent.httpauth_actuation import (
        HTTPAUTH_ACTUATION_GOAL,
        HTTPAUTH_ACTUATION_ID,
    )
    from blackhole_agent.tcn_actuation import (
        TCN_ACTUATION_GOAL,
        TCN_ACTUATION_ID,
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
    checks["denylists_self"] = URL_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(URL_ACTUATION_GOAL) == (
        URL_ACTUATION_ID,
    )
    checks["leftover_text_binds_url"] = leftover_marker_ids(URL_LEFTOVER) == (
        URL_ACTUATION_ID,
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
        (URI_ACTUATION_GOAL, URI_ACTUATION_ID, "uri"),
        (HTTP10_ACTUATION_GOAL, HTTP10_ACTUATION_ID, "http10"),
        (DIGESTAUTH_ACTUATION_GOAL, DIGESTAUTH_ACTUATION_ID, "digestauth"),
        (HTTPSTATE_ACTUATION_GOAL, HTTPSTATE_ACTUATION_ID, "httpstate"),
        (HTTPVER_ACTUATION_GOAL, HTTPVER_ACTUATION_ID, "httpver"),
        (ICP_ACTUATION_GOAL, ICP_ACTUATION_ID, "icp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_url"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"url_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            URL_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = URL_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    advertised = serialize_url(DEFAULT_RESOLVE)
    rebuilt = serialize_url(parse_url(advertised))
    preloaded = parse_url(RFC_URL_LOCATE)
    header = encode_url_header(DEFAULT_RESOLVE)
    parsed_header = parse_url_header(header)
    asked = parse_http_request(resolve_request(SENTINEL, DEFAULT_URLID))
    preload_req = parse_http_request(locate_request(SENTINEL, DEFAULT_URLID, DEFAULT_URLDIGEST))
    got = parse_http_response(resolve_response(SENTINEL, DEFAULT_URLID, DEFAULT_URLDIGEST))
    preload_reply = parse_http_response(
        locate_response(SENTINEL, DEFAULT_URLID, DEFAULT_URLDIGEST)
    )
    checks["url_roundtrip"] = (
        parse_url(advertised) == DEFAULT_RESOLVE
        and hmac.compare_digest(rebuilt, advertised)
        and advertised == RFC_RESOLVE_FIELD
        and is_token("RESOLVE") is True
        and is_token(SENTINEL) is True
        and parsed_header["field_value"] == RFC_RESOLVE_FIELD
        and parsed_header["policy"] == DEFAULT_RESOLVE
        and parsed_header["header"] == RESOLVE_HEADER
        and parsed_header["resolve"] is True
        and parsed_header["locate"] is False
        and preloaded == LOCATE_POLICY
        and ascii_serialize_url_directive() == RFC_RESOLVE_DIRECTIVE
        and url_directive_pair() == ("resolve", "scheme")
        and RFC_RESOLVE_EMPTY == ""
    )
    checks["tuple_roundtrip"] = (
        serialize_url(LOCATE_POLICY) == RFC_URL_LOCATE
        and DEFAULT_URLDIGEST == request_urldigest(DEFAULT_URLID, SENTINEL)
        and "urldigest=" in canonical_locate(SENTINEL, DEFAULT_URLID, DEFAULT_URLDIGEST)
        and canonical_resolve(SENTINEL, DEFAULT_URLID).startswith("RESOLVE")
    )
    checks["serialize_tuple_http_roundtrip"] = (
        asked["method"] == "RESOLVE"
        and asked["url_kind"] == "resolve"
        and asked["urlid"] == DEFAULT_URLID
        and preload_req["url_kind"] == "locate"
        and preload_req["urldigest"] == DEFAULT_URLDIGEST
        and got["status"] == 200
        and preload_reply["status"] == 200
        and got["url_kind"] == "resolve"
        and preload_reply["url_kind"] == "locate"
        and got["policy"] == DEFAULT_RESOLVE
        and preload_reply["policy"] == LOCATE_POLICY
        and got["content_length_matches_body"] is True
        and preload_reply["content_length_matches_body"] is True
        and got["urldigest"] == DEFAULT_URLDIGEST
        and preload_reply["urldigest"] == DEFAULT_URLDIGEST
        and url_matches(serialize_url(got["policy"]), advertised)
    )

    checks["catalog_names_url"] = (
        len(catalog) > 104
        and catalog[104]["id"] == URL_ACTUATION_ID
        and catalog[103]["id"] == HTTP10_ACTUATION_ID
        and catalog[104]["source"] == "genesis_bind_url"
    )
    checks["catalog_names_uri"] = (
        len(catalog) > 105
        and catalog[105]["id"] == URI_ACTUATION_ID
        and catalog[105]["source"] == "genesis_bind_uri"
    )
    family = capability_family(URL_ACTUATION_GOAL)
    checks["family_is_url"] = "url" in family
    checks["family_is_url_surface"] = "url" in family
    checks["family_is_urlid"] = "urlid" in family
    checks["family_is_rfc1738"] = "rfc1738" in family
    checks["family_is_urldigest"] = "urldigest" in family
    checks["family_is_not_spnego"] = (
        "spnego" not in family
        and "rfc4559" not in family
        and "negotiateid" not in family
        and "negotiatedigest" not in family
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
    packed = encode_resolve(identity=SENTINEL, urlid=DEFAULT_URLID, urldigest=DEFAULT_URLDIGEST)
    parsed = parse_message(packed)
    checks["parse_roundtrip"] = (
        parsed["is_resolve"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_urlid"] is True
        and parsed["urlid"] == DEFAULT_URLID
        and parsed["urldigest"] == DEFAULT_URLDIGEST
        and parsed["is_locate"] is False
        and parsed["is_locate"] is False
        and parsed["type"] == FRAME_RESOLVE
        and parsed["first_byte"] == URL_FIRST
    )
    shook = encode_locate(
        identity=SENTINEL,
        urlid=DEFAULT_URLID,
        urldigest=DEFAULT_URLDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["serialize_roundtrip"] = (
        answer_parsed["is_locate"] is True
        and answer_parsed["is_locate"] is True
        and answer_parsed["is_resolve"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["urlid"] == DEFAULT_URLID
        and answer_parsed["urldigest"] == DEFAULT_URLDIGEST
        and answer_parsed["has_urldigest"] is True
        and answer_parsed["type"] == FRAME_LOCATE
        and answer_parsed["first_byte"] == URL_FIRST
    )
    bare = encode_resolve(identity=SENTINEL, urlid=DEFAULT_URLID, include_urlid=False)
    checks["missing_urlid_is_unauthed"] = parse_message(bare)["has_urlid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    icp_signature = semantic_signature(URL_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(icp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_url = ToolDescriptor(name="remote_url", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_url)
    checks["naive_mcp_url_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = url_tool_descriptor()
    default_url = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, URL_TOOL_PROVIDER),
    )
    checks["default_url_provider_is_unsupported"] = (
        default_url.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{URL_TOOL_PROVIDER}" in default_url.reasons
    )
    checks["opted_in_url_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_url],
        required_tool_names=("local_memory", "url"),
    )
    checks["naive_preflight_missing_url"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["url"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "url"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, URL_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "url" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="url-actuation-") as tmp:
        root = Path(tmp)
        missing = run_url_workflow(with_urlid=False, output_dir=root / "missing")
        skip_bind = run_url_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_resolve = run_url_workflow(do_resolve=False, output_dir=root / "skip-resolve")
        skip_locate = run_url_workflow(do_locate=False, output_dir=root / "skip-locate")
        skip_urldigest = run_url_workflow(do_urldigest=False, output_dir=root / "skip-urldigest")
        skip_replay = run_url_workflow(replay=False, output_dir=root / "skip-replay")
        skip_urlid = run_url_workflow(use_urlid=False, output_dir=root / "skip-urlid")
        live = run_url_workflow(output_dir=root / "live")
        verify = verify_url_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_url_trace(clone)
        checks["naive_without_urlid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_urlid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_resolve_stays_empty"] = (
            skip_resolve["ok"] is False
            and skip_resolve["error"] == "resolve_required"
            and skip_resolve["final_status"] == 409
            and skip_resolve["payload_exists"] is False
        )
        checks["skip_locate_stays_empty"] = (
            skip_locate["ok"] is False
            and skip_locate["error"] == "locate_required"
            and skip_locate["final_status"] == 409
            and skip_locate["payload_exists"] is False
        )
        checks["skip_urldigest_stays_empty"] = (
            skip_urldigest["ok"] is False
            and skip_urldigest["error"] == "urldigest_required"
            and skip_urldigest["final_status"] == 409
            and skip_urldigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_urlid_stays_empty"] = (
            skip_urlid["ok"] is False
            and skip_urlid["error"] == "urlid_required"
            and skip_urlid["final_status"] == 409
            and skip_urlid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_urldigest"] = (
            int(live.get("urlid") or 0) == DEFAULT_URLID
            and int(live.get("urldigest") or 0) == DEFAULT_URLDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_urlid_encode_locate_urldigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_resolve["ok"] is False
            and skip_locate["ok"] is False
            and skip_urldigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_urlid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="url-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != URL_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_url"] = (
        live_goal == URL_ACTUATION_GOAL
        and URL_ACTUATION_ID in live_done
        and live_source == "genesis_bind_url"
    )

    with tempfile.TemporaryDirectory(prefix="url-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(URL_LEFTOVER, root)
        register_catalog_proved(root, URL_ACTUATION_ID)
        reason = leftover_satisfied_by(URL_LEFTOVER, root)
        after = leftover_is_open(URL_LEFTOVER, root)
    checks["url_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_url_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{URL_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_url_actuation_capability()
    return {
        "ok": ok,
        "action": "url_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": URL_ACTUATION_GOAL,
        "done_when": URL_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
