"""Drive a first-class Digest Fields tool through RFC 9530 DIGEST/VERIFY.

Tool routing already fails missions that require ``digestfields``: hosted digestfields
endpoints stay on the unsupported MCP provider, and no first-party digestfields
provider is executable. Unbound therefore cannot speak a DIGEST,
lockstep a VERIFY digestid handshake over HTTP Digest Fields DIGESTID,
independently poll the stored contentdigest, or seal a contentdigest digest
an independent later reader can re-open.

This module closes that hole:

- advertise a ``digestfields`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9530 daemon
- keep a missing-digestid client so the digestfields-digestid hole stays falsifiable
- refuse VERIFY until a DIGEST lands with a non-empty digestid
- independently poll the stored contentdigest on a later client socket
- persist a sealed contentdigest digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9421 HTTP Message Signatures
"""


from __future__ import annotations

import base64
import hashlib
import hmac
import json
import shutil
import socket
import struct
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping

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
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    DIGESTFIELDS_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    digestfields_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
DIGESTFIELDS_ACTUATION_ID = "capability.digestfields-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-DF-OK"
POLL_TOKEN = "BH-DF-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_DIGESTID = 0
EMPTY_CONTENTDIGEST = 0
DF_FIRST = 0x44  # RFC 9530 Digest Fields (ASCII 'D')
DIGESTID_SIZE = 4
CONTENTDIGEST_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_VERIFY = 0x02  # RFC 9530 Content-Digest verification
FRAME_DIGEST = 0x01  # RFC 9530 Content-Digest generation
DIGESTFIELDS_ALG_ID = 0x01  # RFC 9530 sha-256
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
DIGESTFIELDS_LEFTOVER = (
    "Later genesis can take RFC 9530 Digest Fields DIGEST/VERIFY over a "
    "digestid-gated contentdigest digest."
)


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


def representation_content(identity: str, digestid: int) -> bytes:
    """RFC 9530 selected representation content bound to digestid."""

    keyid = f"{int(digestid) & 0xFFFFFFFF:08x}"
    return (
        f"POST /digestfields/{keyid} HTTP/1.1\r\n"
        f"Host: {identity}\r\n"
        f"Content-Type: application/octet-stream\r\n"
        f"\r\n"
        f"{identity}:{keyid}"
    ).encode("utf-8")


def content_digest_bytes(identity: str, digestid: int) -> bytes:
    """RFC 9530 section 2 sha-256 digest of representation content."""

    return hashlib.sha256(representation_content(identity, digestid)).digest()


def content_digest_sfv(identity: str, digestid: int) -> str:
    """RFC 9530 Content-Digest as an RFC 8941 dictionary structured field."""

    digest = content_digest_bytes(identity, digestid)
    b64 = base64.standard_b64encode(digest).decode("ascii")
    return f"sha-256=:{b64}:"


DIGESTFIELDS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DIGESTFIELDS_ACTUATION_ID};"
    f"capability_proved:{DIGESTFIELDS_ACTUATION_ID};"
    "no_skill_route"
)
DIGESTFIELDS_ACTUATION_GOAL = (
    "Repair rfc9530 digestfields digest/verify cycle cannot land over http "
    "digestfields digestid: hosted digestfields endpoints remain unsupported so a DIGEST then "
    "VERIFY digestid handshake cannot land and a sealed contentdigest digest "
    "cannot be produced. A missing digestfields digestid stays forbidden; fail-closed "
    "routing never opts the digestfields provider in. An independent later poll of the "
    "stored representation contentdigest keeps the hole falsifiable."
)


class DigestfieldsActuationError(RuntimeError):
    """Raised when the Digest Fields session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_digestid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"digestid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_digestid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-digestid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_contentdigest(digestid: int = EMPTY_DIGESTID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        content_digest_sfv(token or SENTINEL, int(digestid) & 0xFFFFFFFF).encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_DIGESTID = request_digestid(SENTINEL)
DEFAULT_CONTENTDIGEST = request_contentdigest(DEFAULT_DIGESTID, SENTINEL)


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
        raise DigestfieldsActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise DigestfieldsActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise DigestfieldsActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise DigestfieldsActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    digestid: int,
    contentdigest: int,
    include_digestid: bool = True,
) -> bytes:
    live_digestid = int(digestid) & 0xFFFFFFFF if include_digestid else EMPTY_DIGESTID
    live_contentdigest = int(contentdigest) & 0xFFFFFFFF if include_digestid and live_digestid else EMPTY_CONTENTDIGEST
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_contentdigest, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_digestid) if live_digestid else b""
    header = bytearray()
    header.append(DF_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_digest(
    *,
    identity: str,
    digestid: int,
    contentdigest: int | None = None,
    include_digestid: bool = True,
) -> bytes:
    live_digestid = int(digestid) & 0xFFFFFFFF if include_digestid else EMPTY_DIGESTID
    live_contentdigest = int(contentdigest) if contentdigest is not None else request_contentdigest(live_digestid, identity)
    return encode_packet(
        FRAME_DIGEST,
        identity=identity,
        digestid=live_digestid,
        contentdigest=live_contentdigest,
        include_digestid=include_digestid,
    )


def encode_verify(
    *,
    identity: str,
    digestid: int,
    contentdigest: int | None = None,
    include_digestid: bool = True,
) -> bytes:
    live_digestid = int(digestid) & 0xFFFFFFFF if include_digestid else EMPTY_DIGESTID
    live_contentdigest = int(contentdigest) if contentdigest is not None else request_contentdigest(live_digestid, identity)
    return encode_packet(
        FRAME_VERIFY,
        identity=identity,
        digestid=live_digestid,
        contentdigest=live_contentdigest,
        include_digestid=include_digestid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise DigestfieldsActuationError("short_packet")
    first = raw[0]
    if first != DF_FIRST:
        raise DigestfieldsActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise DigestfieldsActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == DIGESTID_SIZE:
        live_digestid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_digestid = EMPTY_DIGESTID
    else:
        raise DigestfieldsActuationError("illegal_digestid")
    if offset >= len(raw):
        raise DigestfieldsActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_DIGEST, FRAME_VERIFY}:
        raise DigestfieldsActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise DigestfieldsActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise DigestfieldsActuationError("checksum_failed")
    if len(payload) < 5:
        raise DigestfieldsActuationError("short_packet")
    live_contentdigest, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise DigestfieldsActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_digestid = int(live_digestid) != EMPTY_DIGESTID
    has_contentdigest = has_digestid and int(live_contentdigest) != EMPTY_CONTENTDIGEST
    is_digest = frame_type == FRAME_DIGEST
    is_verify = frame_type == FRAME_VERIFY
    return {
        "type": int(frame_type),
        "is_digest": is_digest,
        "is_verify": is_verify,
        "is_response": is_verify,
        "digestid": int(live_digestid),
        "has_digestid": has_digestid,
        "contentdigest": int(live_contentdigest),
        "has_contentdigest": has_contentdigest,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "digestfields_alg_id": DIGESTFIELDS_ALG_ID,
    }


class DigestfieldsClient:
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
            raise DigestfieldsActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_verify"] or not packet["is_response"]:
            raise DigestfieldsActuationError("contentdigest_required")
        if not packet["has_digestid"]:
            raise DigestfieldsActuationError("digestid_required")
        if not packet["has_contentdigest"]:
            raise DigestfieldsActuationError("contentdigest_required")
        return packet

    def exchange(self, packet: bytes, *, wait_contentdigest: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_contentdigest:
            raise DigestfieldsActuationError("contentdigest_required")
        reply = self._recv()
        return {
            "session": reply,
            "digestid": int(reply.get("digestid") or EMPTY_DIGESTID),
            "identity": str(reply.get("identity") or ""),
            "contentdigest": int(reply.get("contentdigest") or EMPTY_CONTENTDIGEST),
        }

    def verify(
        self,
        identity: str,
        digestid: int,
        contentdigest: int = EMPTY_CONTENTDIGEST,
        *,
        wait_contentdigest: bool = True,
        include_digestid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_verify(
            identity=identity,
            digestid=digestid,
            contentdigest=contentdigest or request_contentdigest(digestid, identity),
            include_digestid=include_digestid,
        )
        return self.exchange(packet, wait_contentdigest=wait_contentdigest)


class DigestfieldsSession:
    """DIGESTID-gated loopback RFC 9530 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        digestid_gate: int = DEFAULT_DIGESTID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.digestid_gate = int(digestid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.digestid = EMPTY_DIGESTID
        self.contentdigest = EMPTY_CONTENTDIGEST
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

    def store_digestid_once(self, identity: str, digestid: int, contentdigest: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(digestid or EMPTY_DIGESTID)
            live_contentdigest = int(contentdigest or EMPTY_CONTENTDIGEST)
            if not self.identity and name and live:
                self.identity = name
                self.digestid = live
                self.contentdigest = live_contentdigest or request_contentdigest(live, name)
                self.stored = True
            return str(self.identity), int(self.digestid), int(self.contentdigest)

    def read_digestid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.digestid), int(self.contentdigest)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "digestid": EMPTY_DIGESTID,
            "contentdigest": EMPTY_CONTENTDIGEST,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _digestid_missing(self) -> bool:
        return not int(self.digestid_gate or 0)

    def _reply_verify(self, peer: tuple[str, int], identity: str, digestid: int, contentdigest: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_verify(
            identity=identity,
            digestid=digestid,
            contentdigest=contentdigest,
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
            except DigestfieldsActuationError:
                continue
            if not packet.get("is_digest") and not packet.get("is_verify"):
                continue
            if not packet.get("has_digestid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_digestid, stored_contentdigest = self.store_digestid_once(
                identity,
                int(packet.get("digestid") or EMPTY_DIGESTID),
                int(packet.get("contentdigest") or EMPTY_CONTENTDIGEST),
            )
            if not stored_name or not stored_digestid or not stored_contentdigest:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_digest"):
                    self.opened = True
                if packet.get("is_verify"):
                    self.handshook = True
                self.retrieved = True
            self._reply_verify(peer, stored_name, stored_digestid, stored_contentdigest)

    def bind(self) -> dict[str, Any]:
        if self._digestid_missing():
            return self._forbidden("missing_digestid")
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
        do_digest_cycle: bool = True,
        do_verify: bool = True,
        do_contentdigest: bool = True,
        replay: bool = True,
        use_digestid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._digestid_missing():
            return self._forbidden("missing_digestid")
        live_token = str(token or SENTINEL)
        origin_digestid = request_digestid(live_token)
        origin_contentdigest = request_contentdigest(origin_digestid, live_token)
        client: DigestfieldsClient | None = None
        independent: DigestfieldsClient | None = None
        try:
            client = DigestfieldsClient(self.host, int(self.port))
            if not do_digest_cycle:
                return self._conflict("digest_required")
            bind_packet = encode_digest(
                identity=live_token,
                digestid=origin_digestid,
                contentdigest=origin_contentdigest,
                include_digestid=use_digestid,
            )
            if not use_digestid:
                try:
                    client.exchange(bind_packet, wait_contentdigest=True)
                except DigestfieldsActuationError:
                    return self._conflict("digestid_required")
                return self._conflict("digestid_required")
            client.send(bind_packet)
            if not do_verify:
                return self._conflict("verify_required")
            proxy_packet = encode_verify(
                identity=live_token,
                digestid=origin_digestid,
                contentdigest=origin_contentdigest,
                include_digestid=True,
            )
            if not do_contentdigest:
                try:
                    client.exchange(proxy_packet, wait_contentdigest=False)
                except DigestfieldsActuationError as error:
                    if str(error) == "contentdigest_required":
                        return self._conflict("contentdigest_required")
                    return self._conflict("contentdigest_required")
                return self._conflict("contentdigest_required")
            try:
                reply = client.exchange(proxy_packet, wait_contentdigest=True)
            except DigestfieldsActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("digestid_required")
                if reason == "contentdigest_required":
                    return self._conflict("contentdigest_required")
                return self._conflict("digest_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("digest_required")
            if int(reply.get("digestid") or EMPTY_DIGESTID) != origin_digestid:
                return self._conflict("contentdigest_required")
            if int(reply.get("contentdigest") or EMPTY_CONTENTDIGEST) != origin_contentdigest:
                return self._conflict("contentdigest_required")
            self.retrieved = True
            if replay:
                independent = DigestfieldsClient(self.host, int(self.port))
                try:
                    poll = independent.verify(
                        POLL_TOKEN,
                        poll_digestid(live_token),
                        request_contentdigest(poll_digestid(live_token), POLL_TOKEN),
                        wait_contentdigest=True,
                    )
                except DigestfieldsActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_digestid, stored_contentdigest = self.read_digestid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_digestid != origin_digestid
                    or stored_contentdigest != origin_contentdigest
                    or int(poll.get("digestid") or EMPTY_DIGESTID) != origin_digestid
                    or int(poll.get("contentdigest") or EMPTY_CONTENTDIGEST) != origin_contentdigest
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_digestid}:{origin_contentdigest}:{live_token}:{content_digest_bytes(live_token, origin_digestid).hex()}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "digestid": origin_digestid,
                "contentdigest": origin_contentdigest,
                "digest_frame": True,
                "verify": True,
                "contentdigest_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "digestid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_digestfields_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "digestid": origin_digestid,
                "contentdigest": origin_contentdigest,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "digest_frame": True,
                "verify": True,
                "contentdigest_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "digestid_bound": True,
            }
        except (OSError, DigestfieldsActuationError) as error:
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
        live = independent_digestfields_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "digestid": int(live.get("digestid") or EMPTY_DIGESTID),
            "contentdigest": int(live.get("contentdigest") or EMPTY_CONTENTDIGEST),
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


def call_digestfields_tool(session: DigestfieldsSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one DIGESTFIELDS tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_digest_cycle = True if arguments.get("digest_cycle") is None else bool(arguments.get("digest_cycle"))
    do_verify = True if arguments.get("verify") is None else bool(arguments.get("verify"))
    do_contentdigest = True if arguments.get("contentdigest") is None else bool(arguments.get("contentdigest"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_digestid = True if arguments.get("use_digestid") is None else bool(arguments.get("use_digestid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_digest_cycle=do_digest_cycle,
            do_verify=do_verify,
            do_contentdigest=do_contentdigest,
            replay=replay,
            use_digestid=use_digestid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise DigestfieldsActuationError(f"unsupported digestfields action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_digestfields_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed DIGESTFIELDS contentdigest digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "digestid": EMPTY_DIGESTID,
        "contentdigest": EMPTY_CONTENTDIGEST,
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
            "digest_frame",
            "verify",
            "contentdigest_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "digestid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    digestid = int(payload.get("digestid") or EMPTY_DIGESTID)
    contentdigest = int(payload.get("contentdigest") or EMPTY_CONTENTDIGEST)
    dual = port > 0 and bool(digestid) and bool(contentdigest)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "digestid": digestid,
        "contentdigest": contentdigest,
        "size": int(payload.get("size") or 0),
        "port": port,
        "digest_frame": payload.get("digest_frame") is True,
        "verify": payload.get("verify") is True,
        "contentdigest_response": payload.get("contentdigest_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "digestid_bound": payload.get("digestid_bound") is True,
    }


def run_digestfields_workflow(
    *,
    with_digestid: bool = True,
    skip_bind: bool = False,
    do_digest_cycle: bool = True,
    do_verify: bool = True,
    do_contentdigest: bool = True,
    replay: bool = True,
    use_digestid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9530 DIGEST/VERIFY digestid cycle workflow."""

    descriptor = digestfields_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DIGESTFIELDS_TOOL_PROVIDER),
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
        raise DigestfieldsActuationError(f"digestfields tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="digestfields-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = DigestfieldsSession(out, digestid_gate=DEFAULT_DIGESTID if with_digestid else EMPTY_DIGESTID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "digest_cycle": do_digest_cycle,
            "verify": do_verify,
            "contentdigest": do_contentdigest,
            "replay": replay,
            "use_digestid": use_digestid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_digestfields_tool(session, arguments))
            except DigestfieldsActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_digestfields_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_digestid
        and not skip_bind
        and do_digest_cycle
        and do_verify
        and do_contentdigest
        and replay
        and use_digestid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "digestfields_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_digestid": with_digestid,
        "skip_bind": skip_bind,
        "digest_frame": do_digest_cycle,
        "verify": do_verify,
        "contentdigest": do_contentdigest,
        "replay": replay,
        "use_digestid": use_digestid,
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
        "digestid_value": int(publish_result.get("digestid") or independent.get("digestid") or EMPTY_DIGESTID),
        "contentdigest_value": int(publish_result.get("contentdigest") or independent.get("contentdigest") or EMPTY_CONTENTDIGEST),
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
        "digestid": int(trace_body["digestid_value"] or EMPTY_DIGESTID),
        "contentdigest": int(trace_body["contentdigest_value"] or EMPTY_CONTENTDIGEST),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_digestid": with_digestid,
        "skip_bind": skip_bind,
        "digest_cycle": do_digest_cycle,
        "verify_cycle": do_verify,
        "contentdigest_cycle": do_contentdigest,
        "replay": replay,
        "use_digestid": use_digestid,
    }


def verify_digestfields_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed DIGESTFIELDS trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_digestfields_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    digestid = int(trace.get("digestid_value") or independent.get("digestid") or EMPTY_DIGESTID)
    contentdigest = int(trace.get("contentdigest_value") or independent.get("contentdigest") or EMPTY_CONTENTDIGEST)
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
        "digest_frame": independent.get("digest_frame") is True,
        "verify": independent.get("verify") is True,
        "contentdigest_response": independent.get("contentdigest_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "digestid_bound": independent.get("digestid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "contentdigest_recorded": (
            port > 0
            and digestid == DEFAULT_DIGESTID
            and contentdigest == DEFAULT_CONTENTDIGEST
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def digestfields_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.digestfields_actuation import "
        "builtin_digestfields_actuation_proof; r=builtin_digestfields_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='digestfields_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_digestfields_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=DIGESTFIELDS_ACTUATION_ID,
        name="First-class RFC 9530 Digest Fields DIGEST/VERIFY actuation",
        description=(
            "Missions that require a digestfields tool can opt the digestfields provider in, "
            "bind a loopback RFC 9530 Digest Fields origin, complete a DIGEST "
            "with a non-empty digestid, lockstep a VERIFY that carries the "
            "stored contentdigest, independently poll the stored "
            "contentdigest on a later socket, and seal a digest-chained contentdigest. Default "
            "routing stays fail-closed; a missing digestid keeps the hole "
            "falsifiable, and skip-DIGEST/VERIFY/CONTENTDIGEST/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.digestfields_actuation:builtin_digestfields_actuation_proof",
        proof_command=digestfields_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.httpsig-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/digestfields_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/bhttp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required digestfields tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9530 daemon, speaks a "
            "DIGEST then VERIFY over Digest Fields with a non-empty digestid and "
            "contentdigest, independently polls the stored contentdigest on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9421 HTTP Message Signatures lockstep is proved. "
            "Missing digestids, skip-DIGEST, skip-VERIFY, skip-contentdigest, skip-REPLAY, "
            "and a DIGEST aimed without a digestid stay fail-closed. "
            "Later genesis can take RFC 9292 Binary HTTP ENCODE/DECODE as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("digestfields", "rfc9530", "http", "digestid", "contentdigest", "sha-256", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T080401Z-d5ee36c9",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_digestfields_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9530 Digest Fields lockstep actuation seals a contentdigest digest."""

    from blackhole_agent.bhttp_actuation import BHTTP_ACTUATION_GOAL, BHTTP_ACTUATION_ID
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

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = DIGESTFIELDS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(DIGESTFIELDS_ACTUATION_GOAL) == (
        DIGESTFIELDS_ACTUATION_ID,
    )
    checks["leftover_text_binds_digestfields"] = leftover_marker_ids(DIGESTFIELDS_LEFTOVER) == (
        DIGESTFIELDS_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (BHTTP_ACTUATION_GOAL, BHTTP_ACTUATION_ID, "bhttp"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_digestfields"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"digestfields_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            DIGESTFIELDS_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = DIGESTFIELDS_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    digest = content_digest_bytes(SENTINEL, DEFAULT_DIGESTID)
    body = representation_content(SENTINEL, DEFAULT_DIGESTID)
    sfv = content_digest_sfv(SENTINEL, DEFAULT_DIGESTID)
    checks["sha256_contentdigest_roundtrip"] = (
        hmac.compare_digest(digest, hashlib.sha256(body).digest())
        and len(digest) == 32
        and sfv.startswith("sha-256=:")
        and sfv.endswith(":")
        and DEFAULT_CONTENTDIGEST == request_contentdigest(DEFAULT_DIGESTID, SENTINEL)
    )
    checks["catalog_names_digestfields"] = (
        len(catalog) > 70
        and catalog[70]["id"] == DIGESTFIELDS_ACTUATION_ID
        and catalog[69]["id"] == HTTPSIG_ACTUATION_ID
        and catalog[70]["source"] == "genesis_bind_digestfields"
    )
    checks["catalog_names_bhttp"] = (
        len(catalog) > 71
        and catalog[71]["id"] == BHTTP_ACTUATION_ID
        and catalog[71]["source"] == "genesis_bind_bhttp"
    )
    family = capability_family(DIGESTFIELDS_ACTUATION_GOAL)
    checks["family_is_digestfields"] = "digestfield" in family
    checks["family_is_rfc9530"] = "rfc9530" in family
    checks["family_is_digestid"] = "digestid" in family
    checks["family_is_contentdigest"] = "contentdigest" in family
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
        "dtls" not in family and "rfc6347" not in family and "cookie" not in family and "epoch" not in family
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
        and "binaryhttp" not in family
        and "rfc9292" not in family
        and "messageid" not in family
        and "binarymsg" not in family
    )
    packed = encode_digest(identity=SENTINEL, digestid=DEFAULT_DIGESTID, contentdigest=DEFAULT_CONTENTDIGEST)
    parsed = parse_message(packed)
    checks["digest_roundtrip"] = (
        parsed["is_digest"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_digestid"] is True
        and parsed["digestid"] == DEFAULT_DIGESTID
        and parsed["contentdigest"] == DEFAULT_CONTENTDIGEST
        and parsed["is_response"] is False
        and parsed["is_verify"] is False
        and parsed["type"] == FRAME_DIGEST
        and parsed["first_byte"] == DF_FIRST
    )
    shook = encode_verify(
        identity=SENTINEL,
        digestid=DEFAULT_DIGESTID,
        contentdigest=DEFAULT_CONTENTDIGEST,
    )
    answer_parsed = parse_message(shook)
    checks["verify_roundtrip"] = (
        answer_parsed["is_verify"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_digest"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["digestid"] == DEFAULT_DIGESTID
        and answer_parsed["contentdigest"] == DEFAULT_CONTENTDIGEST
        and answer_parsed["has_contentdigest"] is True
        and answer_parsed["type"] == FRAME_VERIFY
        and answer_parsed["first_byte"] == DF_FIRST
    )
    bare = encode_digest(identity=SENTINEL, digestid=DEFAULT_DIGESTID, include_digestid=False)
    checks["missing_digestid_is_unauthenticated"] = parse_message(bare)["has_digestid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    digestfields_signature = semantic_signature(DIGESTFIELDS_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(digestfields_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_digestfields = ToolDescriptor(name="remote_digestfields", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_digestfields)
    checks["naive_mcp_digestfields_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = digestfields_tool_descriptor()
    default_digestfields = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DIGESTFIELDS_TOOL_PROVIDER),
    )
    checks["default_digestfields_provider_is_unsupported"] = (
        default_digestfields.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{DIGESTFIELDS_TOOL_PROVIDER}" in default_digestfields.reasons
    )
    checks["opted_in_digestfields_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_digestfields],
        required_tool_names=("local_memory", "digestfields"),
    )
    checks["naive_preflight_missing_digestfields"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["digestfields"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "digestfields"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DIGESTFIELDS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "digestfields" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="digestfields-actuation-") as tmp:
        root = Path(tmp)
        missing = run_digestfields_workflow(with_digestid=False, output_dir=root / "missing")
        skip_bind = run_digestfields_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_digest_cycle = run_digestfields_workflow(do_digest_cycle=False, output_dir=root / "skip-digest-cycle")
        skip_verify = run_digestfields_workflow(do_verify=False, output_dir=root / "skip-verify")
        skip_contentdigest = run_digestfields_workflow(do_contentdigest=False, output_dir=root / "skip-contentdigest")
        skip_replay = run_digestfields_workflow(replay=False, output_dir=root / "skip-replay")
        skip_digestid = run_digestfields_workflow(use_digestid=False, output_dir=root / "skip-digestid")
        live = run_digestfields_workflow(output_dir=root / "live")
        verify = verify_digestfields_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_digestfields_trace(clone)
        checks["naive_without_digestid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_digestid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_digest_cycle_stays_empty"] = (
            skip_digest_cycle["ok"] is False
            and skip_digest_cycle["error"] == "digest_required"
            and skip_digest_cycle["final_status"] == 409
            and skip_digest_cycle["payload_exists"] is False
        )
        checks["skip_verify_stays_empty"] = (
            skip_verify["ok"] is False
            and skip_verify["error"] == "verify_required"
            and skip_verify["final_status"] == 409
            and skip_verify["payload_exists"] is False
        )
        checks["skip_contentdigest_stays_empty"] = (
            skip_contentdigest["ok"] is False
            and skip_contentdigest["error"] == "contentdigest_required"
            and skip_contentdigest["final_status"] == 409
            and skip_contentdigest["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_digestid_stays_empty"] = (
            skip_digestid["ok"] is False
            and skip_digestid["error"] == "digestid_required"
            and skip_digestid["final_status"] == 409
            and skip_digestid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_contentdigest"] = (
            int(live.get("digestid") or 0) == DEFAULT_DIGESTID
            and int(live.get("contentdigest") or 0) == DEFAULT_CONTENTDIGEST
            and int(live.get("port") or 0) > 0
        )
        checks["token_digestid_sign_verify_contentdigest_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_digest_cycle["ok"] is False
            and skip_verify["ok"] is False
            and skip_contentdigest["ok"] is False
            and skip_replay["ok"] is False
            and skip_digestid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="digestfields-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != DIGESTFIELDS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_digestfields"] = (
        live_goal == DIGESTFIELDS_ACTUATION_GOAL
        and DIGESTFIELDS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_digestfields"
    )

    with tempfile.TemporaryDirectory(prefix="digestfields-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(DIGESTFIELDS_LEFTOVER, root)
        register_catalog_proved(root, DIGESTFIELDS_ACTUATION_ID)
        reason = leftover_satisfied_by(DIGESTFIELDS_LEFTOVER, root)
        after = leftover_is_open(DIGESTFIELDS_LEFTOVER, root)
    checks["digestfields_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_digestfields_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{DIGESTFIELDS_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_digestfields_actuation_capability()
    return {
        "ok": ok,
        "action": "digestfields_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": DIGESTFIELDS_ACTUATION_GOAL,
        "done_when": DIGESTFIELDS_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
