"""Drive a first-class HTTP Message Signatures tool through RFC 9421 SIGN/VERIFY.

Tool routing already fails missions that require ``httpsig``: hosted httpsig
endpoints stay on the unsupported MCP provider, and no first-party httpsig
provider is executable. Unbound therefore cannot speak a SIGN,
lockstep a VERIFY sigid handshake over HTTP Message Signatures SIGID,
independently poll the stored sigbase, or seal a sigbase digest
an independent later reader can re-open.

This module closes that hole:

- advertise an ``httpsig`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 9421 daemon
- keep a missing-sigid client so the httpsig-sigid hole stays falsifiable
- refuse VERIFY until a SIGN lands with a non-empty sigid
- independently poll the stored sigbase on a later client socket
- persist a sealed sigbase digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after RFC 9540 Oblivious Service Binding
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
    HTTPSIG_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    httpsig_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
HTTPSIG_ACTUATION_ID = "capability.httpsig-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-HS-OK"
POLL_TOKEN = "BH-HS-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
EMPTY_SIGID = 0
EMPTY_SIGBASE = 0
HS_FIRST = 0x48  # RFC 9421 HTTP Message Signatures
SIGID_SIZE = 4
SIGBASE_SIZE = 4
CHECKSUM_SIZE = 4
FRAME_VERIFY = 0x02  # RFC 9421 HTTP Message Signature verification
FRAME_SIGN = 0x01  # RFC 9421 HTTP Message Signature generation
HTTPSIG_ALG_ID = 0x04  # RFC 9421 section 3.3.3 hmac-sha256
CRC32C_POLY = 0x82F63B78
CRC32C_CHECK = 0xE3069283
HTTPSIG_LEFTOVER = (
    "Later genesis can take RFC 9421 HTTP Message Signatures SIGN/VERIFY over a "
    "sigid-gated sigbase digest."
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


def signature_base(identity: str, sigid: int) -> bytes:
    """RFC 9421 section 2.5 signature base over method, authority, path, and params."""

    keyid = f"{int(sigid) & 0xFFFFFFFF:08x}"
    params = f'("@method" "@authority" "@path");alg="hmac-sha256";keyid="{keyid}"'
    return (
        f'"@method": POST\n'
        f'"@authority": {identity}\n'
        f'"@path": /httpsig/{keyid}\n'
        f'"@signature-params": {params}'
    ).encode("utf-8")


def httpsig_hmac(identity: str, sigid: int, *, key: bytes | None = None) -> bytes:
    """RFC 9421 section 3.3.3 HMAC-SHA256 over the signature base."""

    material = (
        key
        if key is not None
        else hashlib.sha256(f"httpsig-key:{identity}:{int(sigid) & 0xFFFFFFFF}".encode("utf-8")).digest()
    )
    return hmac.new(material, signature_base(identity, sigid), hashlib.sha256).digest()


HTTPSIG_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPSIG_ACTUATION_ID};"
    f"capability_proved:{HTTPSIG_ACTUATION_ID};"
    "no_skill_route"
)
HTTPSIG_ACTUATION_GOAL = (
    "Repair rfc9421 httpsig sign/verify cycle cannot land over http "
    "httpsig sigid: hosted httpsig endpoints remain unsupported so a SIGN then "
    "VERIFY sigid handshake cannot land and a sealed sigbase digest "
    "cannot be produced. A missing httpsig sigid stays forbidden; fail-closed "
    "routing never opts the httpsig provider in. An independent later poll of the "
    "stored message sigbase keeps the hole falsifiable."
)


class HttpsigActuationError(RuntimeError):
    """Raised when the HTTP Message Signatures session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_sigid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"sigid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_sigid(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-sigid:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_sigbase(sigid: int = EMPTY_SIGID, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(signature_base(token or SENTINEL, int(sigid) & 0xFFFFFFFF)).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


DEFAULT_SIGID = request_sigid(SENTINEL)
DEFAULT_SIGBASE = request_sigbase(DEFAULT_SIGID, SENTINEL)


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
        raise HttpsigActuationError("short_packet")
    prefix = raw[offset] >> 6
    if prefix == 0:
        return raw[offset] & 0x3F, offset + 1
    if prefix == 1:
        if offset + 2 > len(raw):
            raise HttpsigActuationError("short_packet")
        return struct.unpack("!H", raw[offset : offset + 2])[0] & 0x3FFF, offset + 2
    if prefix == 2:
        if offset + 4 > len(raw):
            raise HttpsigActuationError("short_packet")
        return struct.unpack("!I", raw[offset : offset + 4])[0] & 0x3FFFFFFF, offset + 4
    if offset + 8 > len(raw):
        raise HttpsigActuationError("short_packet")
    return (
        struct.unpack("!Q", raw[offset : offset + 8])[0] & 0x3FFFFFFFFFFFFFFF,
        offset + 8,
    )


def encode_packet(
    frame_type: int,
    *,
    identity: str,
    sigid: int,
    sigbase: int,
    include_sigid: bool = True,
) -> bytes:
    live_sigid = int(sigid) & 0xFFFFFFFF if include_sigid else EMPTY_SIGID
    live_sigbase = int(sigbase) & 0xFFFFFFFF if include_sigid and live_sigid else EMPTY_SIGBASE
    ident = str(identity or "").encode("utf-8")[:255]
    payload = struct.pack("!IB", live_sigbase, len(ident)) + ident
    prefix_bytes = struct.pack("!I", live_sigid) if live_sigid else b""
    header = bytearray()
    header.append(HS_FIRST)
    header.append(len(prefix_bytes))
    header.extend(prefix_bytes)
    header.append(int(frame_type) & 0xFF)
    remainder = payload + (b"\x00" * CHECKSUM_SIZE)
    header.extend(encode_varint(len(remainder)))
    packet = bytes(header) + remainder
    checksum = crc32c(packet)
    return packet[:-CHECKSUM_SIZE] + struct.pack("!I", checksum)


def encode_sign(
    *,
    identity: str,
    sigid: int,
    sigbase: int | None = None,
    include_sigid: bool = True,
) -> bytes:
    live_sigid = int(sigid) & 0xFFFFFFFF if include_sigid else EMPTY_SIGID
    live_sigbase = int(sigbase) if sigbase is not None else request_sigbase(live_sigid, identity)
    return encode_packet(
        FRAME_SIGN,
        identity=identity,
        sigid=live_sigid,
        sigbase=live_sigbase,
        include_sigid=include_sigid,
    )


def encode_verify(
    *,
    identity: str,
    sigid: int,
    sigbase: int | None = None,
    include_sigid: bool = True,
) -> bytes:
    live_sigid = int(sigid) & 0xFFFFFFFF if include_sigid else EMPTY_SIGID
    live_sigbase = int(sigbase) if sigbase is not None else request_sigbase(live_sigid, identity)
    return encode_packet(
        FRAME_VERIFY,
        identity=identity,
        sigid=live_sigid,
        sigbase=live_sigbase,
        include_sigid=include_sigid,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < 4:
        raise HttpsigActuationError("short_packet")
    first = raw[0]
    if first != HS_FIRST:
        raise HttpsigActuationError("illegal_header")
    offset = 1
    prefix_len = raw[offset]
    offset += 1
    if offset + prefix_len > len(raw):
        raise HttpsigActuationError("short_packet")
    prefix_bytes = raw[offset : offset + prefix_len]
    offset += prefix_len
    if prefix_len == SIGID_SIZE:
        live_sigid = struct.unpack("!I", prefix_bytes)[0]
    elif prefix_len == 0:
        live_sigid = EMPTY_SIGID
    else:
        raise HttpsigActuationError("illegal_sigid")
    if offset >= len(raw):
        raise HttpsigActuationError("short_packet")
    frame_type = raw[offset]
    offset += 1
    if frame_type not in {FRAME_SIGN, FRAME_VERIFY}:
        raise HttpsigActuationError("illegal_frame")
    length, offset = decode_varint(raw, offset)
    end = offset + int(length)
    if end > len(raw) or int(length) < 5 + CHECKSUM_SIZE:
        raise HttpsigActuationError("short_packet")
    payload = raw[offset : end - CHECKSUM_SIZE]
    checksum = struct.unpack("!I", raw[end - CHECKSUM_SIZE : end])[0]
    zeroed = raw[: end - CHECKSUM_SIZE] + (b"\x00" * CHECKSUM_SIZE)
    if int(checksum) != crc32c(zeroed):
        raise HttpsigActuationError("checksum_failed")
    if len(payload) < 5:
        raise HttpsigActuationError("short_packet")
    live_sigbase, ident_len = struct.unpack("!IB", payload[:5])
    if 5 + int(ident_len) > len(payload):
        raise HttpsigActuationError("short_packet")
    identity = payload[5 : 5 + int(ident_len)].decode("utf-8", errors="replace")
    has_sigid = int(live_sigid) != EMPTY_SIGID
    has_sigbase = has_sigid and int(live_sigbase) != EMPTY_SIGBASE
    is_sign = frame_type == FRAME_SIGN
    is_verify = frame_type == FRAME_VERIFY
    return {
        "type": int(frame_type),
        "is_sign": is_sign,
        "is_verify": is_verify,
        "is_response": is_verify,
        "sigid": int(live_sigid),
        "has_sigid": has_sigid,
        "sigbase": int(live_sigbase),
        "has_sigbase": has_sigbase,
        "frame_length": int(length),
        "identity": identity,
        "has_identity": bool(identity),
        "checksum": int(checksum),
        "first_byte": int(first),
        "prefix_len": int(prefix_len),
        "httpsig_alg_id": HTTPSIG_ALG_ID,
    }


class HttpsigClient:
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
            raise HttpsigActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_verify"] or not packet["is_response"]:
            raise HttpsigActuationError("sigbase_required")
        if not packet["has_sigid"]:
            raise HttpsigActuationError("sigid_required")
        if not packet["has_sigbase"]:
            raise HttpsigActuationError("sigbase_required")
        return packet

    def exchange(self, packet: bytes, *, wait_sigbase: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_sigbase:
            raise HttpsigActuationError("sigbase_required")
        reply = self._recv()
        return {
            "session": reply,
            "sigid": int(reply.get("sigid") or EMPTY_SIGID),
            "identity": str(reply.get("identity") or ""),
            "sigbase": int(reply.get("sigbase") or EMPTY_SIGBASE),
        }

    def verify(
        self,
        identity: str,
        sigid: int,
        sigbase: int = EMPTY_SIGBASE,
        *,
        wait_sigbase: bool = True,
        include_sigid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_verify(
            identity=identity,
            sigid=sigid,
            sigbase=sigbase or request_sigbase(sigid, identity),
            include_sigid=include_sigid,
        )
        return self.exchange(packet, wait_sigbase=wait_sigbase)


class HttpsigSession:
    """SIGID-gated loopback RFC 9421 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        sigid_gate: int = DEFAULT_SIGID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sigid_gate = int(sigid_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.sigid = EMPTY_SIGID
        self.sigbase = EMPTY_SIGBASE
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

    def store_sigid_once(self, identity: str, sigid: int, sigbase: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(sigid or EMPTY_SIGID)
            live_sigbase = int(sigbase or EMPTY_SIGBASE)
            if not self.identity and name and live:
                self.identity = name
                self.sigid = live
                self.sigbase = live_sigbase or request_sigbase(live, name)
                self.stored = True
            return str(self.identity), int(self.sigid), int(self.sigbase)

    def read_sigid(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.sigid), int(self.sigbase)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "sigid": EMPTY_SIGID,
            "sigbase": EMPTY_SIGBASE,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _sigid_missing(self) -> bool:
        return not int(self.sigid_gate or 0)

    def _reply_verify(self, peer: tuple[str, int], identity: str, sigid: int, sigbase: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_verify(
            identity=identity,
            sigid=sigid,
            sigbase=sigbase,
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
            except HttpsigActuationError:
                continue
            if not packet.get("is_sign") and not packet.get("is_verify"):
                continue
            if not packet.get("has_sigid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_sigid, stored_sigbase = self.store_sigid_once(
                identity,
                int(packet.get("sigid") or EMPTY_SIGID),
                int(packet.get("sigbase") or EMPTY_SIGBASE),
            )
            if not stored_name or not stored_sigid or not stored_sigbase:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_sign"):
                    self.opened = True
                if packet.get("is_verify"):
                    self.handshook = True
                self.retrieved = True
            self._reply_verify(peer, stored_name, stored_sigid, stored_sigbase)

    def bind(self) -> dict[str, Any]:
        if self._sigid_missing():
            return self._forbidden("missing_sigid")
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
        do_sign_cycle: bool = True,
        do_verify: bool = True,
        do_sigbase: bool = True,
        replay: bool = True,
        use_sigid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._sigid_missing():
            return self._forbidden("missing_sigid")
        live_token = str(token or SENTINEL)
        origin_sigid = request_sigid(live_token)
        origin_sigbase = request_sigbase(origin_sigid, live_token)
        client: HttpsigClient | None = None
        independent: HttpsigClient | None = None
        try:
            client = HttpsigClient(self.host, int(self.port))
            if not do_sign_cycle:
                return self._conflict("sign_required")
            bind_packet = encode_sign(
                identity=live_token,
                sigid=origin_sigid,
                sigbase=origin_sigbase,
                include_sigid=use_sigid,
            )
            if not use_sigid:
                try:
                    client.exchange(bind_packet, wait_sigbase=True)
                except HttpsigActuationError:
                    return self._conflict("sigid_required")
                return self._conflict("sigid_required")
            client.send(bind_packet)
            if not do_verify:
                return self._conflict("verify_required")
            proxy_packet = encode_verify(
                identity=live_token,
                sigid=origin_sigid,
                sigbase=origin_sigbase,
                include_sigid=True,
            )
            if not do_sigbase:
                try:
                    client.exchange(proxy_packet, wait_sigbase=False)
                except HttpsigActuationError as error:
                    if str(error) == "sigbase_required":
                        return self._conflict("sigbase_required")
                    return self._conflict("sigbase_required")
                return self._conflict("sigbase_required")
            try:
                reply = client.exchange(proxy_packet, wait_sigbase=True)
            except HttpsigActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("sigid_required")
                if reason == "sigbase_required":
                    return self._conflict("sigbase_required")
                return self._conflict("sign_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("sign_required")
            if int(reply.get("sigid") or EMPTY_SIGID) != origin_sigid:
                return self._conflict("sigbase_required")
            if int(reply.get("sigbase") or EMPTY_SIGBASE) != origin_sigbase:
                return self._conflict("sigbase_required")
            self.retrieved = True
            if replay:
                independent = HttpsigClient(self.host, int(self.port))
                try:
                    poll = independent.verify(
                        POLL_TOKEN,
                        poll_sigid(live_token),
                        request_sigbase(poll_sigid(live_token), POLL_TOKEN),
                        wait_sigbase=True,
                    )
                except HttpsigActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_sigid, stored_sigbase = self.read_sigid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_sigid != origin_sigid
                    or stored_sigbase != origin_sigbase
                    or int(poll.get("sigid") or EMPTY_SIGID) != origin_sigid
                    or int(poll.get("sigbase") or EMPTY_SIGBASE) != origin_sigbase
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_sigid}:{origin_sigbase}:{live_token}:{httpsig_hmac(live_token, origin_sigid).hex()}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "sigid": origin_sigid,
                "sigbase": origin_sigbase,
                "sign": True,
                "verify": True,
                "sigbase_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "sigid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_httpsig_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "sigid": origin_sigid,
                "sigbase": origin_sigbase,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "sign": True,
                "verify": True,
                "sigbase_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "sigid_bound": True,
            }
        except (OSError, HttpsigActuationError) as error:
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
        live = independent_httpsig_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "sigid": int(live.get("sigid") or EMPTY_SIGID),
            "sigbase": int(live.get("sigbase") or EMPTY_SIGBASE),
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


def call_httpsig_tool(session: HttpsigSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one HTTPSIG tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_sign_cycle = True if arguments.get("sign_cycle") is None else bool(arguments.get("sign_cycle"))
    do_verify = True if arguments.get("verify") is None else bool(arguments.get("verify"))
    do_sigbase = True if arguments.get("sigbase") is None else bool(arguments.get("sigbase"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_sigid = True if arguments.get("use_sigid") is None else bool(arguments.get("use_sigid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_sign_cycle=do_sign_cycle,
            do_verify=do_verify,
            do_sigbase=do_sigbase,
            replay=replay,
            use_sigid=use_sigid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise HttpsigActuationError(f"unsupported httpsig action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_httpsig_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed HTTPSIG sigbase digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "sigid": EMPTY_SIGID,
        "sigbase": EMPTY_SIGBASE,
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
            "sign",
            "verify",
            "sigbase_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "sigid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    sigid = int(payload.get("sigid") or EMPTY_SIGID)
    sigbase = int(payload.get("sigbase") or EMPTY_SIGBASE)
    dual = port > 0 and bool(sigid) and bool(sigbase)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "sigid": sigid,
        "sigbase": sigbase,
        "size": int(payload.get("size") or 0),
        "port": port,
        "sign": payload.get("sign") is True,
        "verify": payload.get("verify") is True,
        "sigbase_response": payload.get("sigbase_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "sigid_bound": payload.get("sigid_bound") is True,
    }


def run_httpsig_workflow(
    *,
    with_sigid: bool = True,
    skip_bind: bool = False,
    do_sign_cycle: bool = True,
    do_verify: bool = True,
    do_sigbase: bool = True,
    replay: bool = True,
    use_sigid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 9421 SIGN/VERIFY sigid cycle workflow."""

    descriptor = httpsig_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPSIG_TOOL_PROVIDER),
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
        raise HttpsigActuationError(f"httpsig tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="httpsig-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = HttpsigSession(out, sigid_gate=DEFAULT_SIGID if with_sigid else EMPTY_SIGID)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "sign_cycle": do_sign_cycle,
            "verify": do_verify,
            "sigbase": do_sigbase,
            "replay": replay,
            "use_sigid": use_sigid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_httpsig_tool(session, arguments))
            except HttpsigActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_httpsig_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_sigid
        and not skip_bind
        and do_sign_cycle
        and do_verify
        and do_sigbase
        and replay
        and use_sigid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "httpsig_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_sigid": with_sigid,
        "skip_bind": skip_bind,
        "sign": do_sign_cycle,
        "verify": do_verify,
        "sigbase": do_sigbase,
        "replay": replay,
        "use_sigid": use_sigid,
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
        "sigid_value": int(publish_result.get("sigid") or independent.get("sigid") or EMPTY_SIGID),
        "sigbase_value": int(publish_result.get("sigbase") or independent.get("sigbase") or EMPTY_SIGBASE),
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
        "sigid": int(trace_body["sigid_value"] or EMPTY_SIGID),
        "sigbase": int(trace_body["sigbase_value"] or EMPTY_SIGBASE),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_sigid": with_sigid,
        "skip_bind": skip_bind,
        "sign_cycle": do_sign_cycle,
        "verify_cycle": do_verify,
        "sigbase_cycle": do_sigbase,
        "replay": replay,
        "use_sigid": use_sigid,
    }


def verify_httpsig_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed HTTPSIG trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_httpsig_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    port = int(trace.get("port") or independent.get("port") or 0)
    sigid = int(trace.get("sigid_value") or independent.get("sigid") or EMPTY_SIGID)
    sigbase = int(trace.get("sigbase_value") or independent.get("sigbase") or EMPTY_SIGBASE)
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
        "sign": independent.get("sign") is True,
        "verify": independent.get("verify") is True,
        "sigbase_response": independent.get("sigbase_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "sigid_bound": independent.get("sigid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "sigbase_recorded": (
            port > 0
            and sigid == DEFAULT_SIGID
            and sigbase == DEFAULT_SIGBASE
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def httpsig_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.httpsig_actuation import "
        "builtin_httpsig_actuation_proof; r=builtin_httpsig_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='httpsig_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_httpsig_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HTTPSIG_ACTUATION_ID,
        name="First-class RFC 9421 HTTP Message Signatures SIGN/VERIFY actuation",
        description=(
            "Missions that require an httpsig tool can opt the httpsig provider in, "
            "bind a loopback RFC 9421 HTTP Message Signatures origin, complete a SIGN "
            "with a non-empty sigid, lockstep a VERIFY that carries the "
            "stored sigbase, independently poll the stored "
            "sigbase on a later socket, and seal a digest-chained sigbase. Default "
            "routing stays fail-closed; a missing sigid keeps the hole "
            "falsifiable, and skip-SIGN/VERIFY/SIGBASE/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.httpsig_actuation:builtin_httpsig_actuation_proof",
        proof_command=httpsig_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.ohsvcb-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/httpsig_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/digestfields_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required httpsig tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback RFC 9421 daemon, speaks a "
            "SIGN then VERIFY over HTTP Message Signatures with a non-empty sigid and "
            "sigbase, independently polls the stored sigbase on a "
            "later client socket, and binds this family as the next "
            "diversity-catalog successor once RFC 9540 Oblivious Service Binding lockstep is proved. "
            "Missing sigids, skip-SIGN, skip-VERIFY, skip-sigbase, skip-REPLAY, "
            "and a SIGN aimed without a sigid stay fail-closed. "
            "Later genesis can take RFC 9530 Digest Fields DIGEST/VERIFY as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("httpsig", "rfc9421", "http", "sigid", "sigbase", "hmac-sha256", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260903T072320Z-e5898343",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_httpsig_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 9421 HTTP Message Signatures lockstep actuation seals a sigbase digest."""

    from blackhole_agent.digestfields_actuation import DIGESTFIELDS_ACTUATION_GOAL, DIGESTFIELDS_ACTUATION_ID
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
    checks["denylists_self"] = HTTPSIG_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HTTPSIG_ACTUATION_GOAL) == (
        HTTPSIG_ACTUATION_ID,
    )
    checks["leftover_text_binds_httpsig"] = leftover_marker_ids(HTTPSIG_LEFTOVER) == (
        HTTPSIG_ACTUATION_ID,
    )
    neighbor_goals = (
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
        (DIGESTFIELDS_ACTUATION_GOAL, DIGESTFIELDS_ACTUATION_ID, "digestfields"),
    )
    for goal, capability_id, name in neighbor_goals:
        checks[f"{name}_goal_is_not_httpsig"] = leftover_marker_ids(goal) == (capability_id,)
        checks[f"httpsig_goal_is_not_{name}"] = capability_id not in leftover_marker_ids(
            HTTPSIG_ACTUATION_GOAL
        )
        checks[f"{name}_marker_stays_{name}"] = HTTPSIG_ACTUATION_ID not in leftover_marker_ids(
            goal
        )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["crc32c_vector"] = crc32c(b"123456789") == CRC32C_CHECK
    mac = httpsig_hmac(SENTINEL, DEFAULT_SIGID)
    base = signature_base(SENTINEL, DEFAULT_SIGID)
    key = hashlib.sha256(f"httpsig-key:{SENTINEL}:{DEFAULT_SIGID}".encode("utf-8")).digest()
    checks["hmac_sha256_roundtrip"] = (
        hmac.compare_digest(mac, hmac.new(key, base, hashlib.sha256).digest())
        and len(mac) == 32
        and DEFAULT_SIGBASE == request_sigbase(DEFAULT_SIGID, SENTINEL)
    )
    checks["catalog_names_httpsig"] = (
        len(catalog) > 69
        and catalog[69]["id"] == HTTPSIG_ACTUATION_ID
        and catalog[68]["id"] == OHSVCB_ACTUATION_ID
        and catalog[69]["source"] == "genesis_bind_httpsig"
    )
    checks["catalog_names_digestfields"] = (
        len(catalog) > 70
        and catalog[70]["id"] == DIGESTFIELDS_ACTUATION_ID
        and catalog[70]["source"] == "genesis_bind_digestfields"
    )
    family = capability_family(HTTPSIG_ACTUATION_GOAL)
    checks["family_is_httpsig"] = "httpsig" in family
    checks["family_is_rfc9421"] = "rfc9421" in family
    checks["family_is_sigid"] = "sigid" in family
    checks["family_is_sigbase"] = "sigbase" in family
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
    checks["family_is_not_digestfields"] = (
        "digestfields" not in family
        and "digestfield" not in family
        and "rfc9530" not in family
        and "digestid" not in family
        and "contentdigest" not in family
    )
    packed = encode_sign(identity=SENTINEL, sigid=DEFAULT_SIGID, sigbase=DEFAULT_SIGBASE)
    parsed = parse_message(packed)
    checks["sign_roundtrip"] = (
        parsed["is_sign"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_sigid"] is True
        and parsed["sigid"] == DEFAULT_SIGID
        and parsed["sigbase"] == DEFAULT_SIGBASE
        and parsed["is_response"] is False
        and parsed["is_verify"] is False
        and parsed["type"] == FRAME_SIGN
        and parsed["first_byte"] == HS_FIRST
    )
    shook = encode_verify(
        identity=SENTINEL,
        sigid=DEFAULT_SIGID,
        sigbase=DEFAULT_SIGBASE,
    )
    answer_parsed = parse_message(shook)
    checks["verify_roundtrip"] = (
        answer_parsed["is_verify"] is True
        and answer_parsed["is_response"] is True
        and answer_parsed["is_sign"] is False
        and answer_parsed["identity"] == SENTINEL
        and answer_parsed["sigid"] == DEFAULT_SIGID
        and answer_parsed["sigbase"] == DEFAULT_SIGBASE
        and answer_parsed["has_sigbase"] is True
        and answer_parsed["type"] == FRAME_VERIFY
        and answer_parsed["first_byte"] == HS_FIRST
    )
    bare = encode_sign(identity=SENTINEL, sigid=DEFAULT_SIGID, include_sigid=False)
    checks["missing_sigid_is_unauthenticated"] = parse_message(bare)["has_sigid"] is False
    neighbors = tuple(goal for goal, _capability_id, _name in neighbor_goals)
    httpsig_signature = semantic_signature(HTTPSIG_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(httpsig_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_httpsig = ToolDescriptor(name="remote_httpsig", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_httpsig)
    checks["naive_mcp_httpsig_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = httpsig_tool_descriptor()
    default_httpsig = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPSIG_TOOL_PROVIDER),
    )
    checks["default_httpsig_provider_is_unsupported"] = (
        default_httpsig.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{HTTPSIG_TOOL_PROVIDER}" in default_httpsig.reasons
    )
    checks["opted_in_httpsig_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_httpsig],
        required_tool_names=("local_memory", "httpsig"),
    )
    checks["naive_preflight_missing_httpsig"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["httpsig"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "httpsig"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, HTTPSIG_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "httpsig" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="httpsig-actuation-") as tmp:
        root = Path(tmp)
        missing = run_httpsig_workflow(with_sigid=False, output_dir=root / "missing")
        skip_bind = run_httpsig_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_sign_cycle = run_httpsig_workflow(do_sign_cycle=False, output_dir=root / "skip-sign-cycle")
        skip_verify = run_httpsig_workflow(do_verify=False, output_dir=root / "skip-verify")
        skip_sigbase = run_httpsig_workflow(do_sigbase=False, output_dir=root / "skip-sigbase")
        skip_replay = run_httpsig_workflow(replay=False, output_dir=root / "skip-replay")
        skip_sigid = run_httpsig_workflow(use_sigid=False, output_dir=root / "skip-sigid")
        live = run_httpsig_workflow(output_dir=root / "live")
        verify = verify_httpsig_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_httpsig_trace(clone)
        checks["naive_without_sigid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_sigid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_sign_cycle_stays_empty"] = (
            skip_sign_cycle["ok"] is False
            and skip_sign_cycle["error"] == "sign_required"
            and skip_sign_cycle["final_status"] == 409
            and skip_sign_cycle["payload_exists"] is False
        )
        checks["skip_verify_stays_empty"] = (
            skip_verify["ok"] is False
            and skip_verify["error"] == "verify_required"
            and skip_verify["final_status"] == 409
            and skip_verify["payload_exists"] is False
        )
        checks["skip_sigbase_stays_empty"] = (
            skip_sigbase["ok"] is False
            and skip_sigbase["error"] == "sigbase_required"
            and skip_sigbase["final_status"] == 409
            and skip_sigbase["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_sigid_stays_empty"] = (
            skip_sigid["ok"] is False
            and skip_sigid["error"] == "sigid_required"
            and skip_sigid["final_status"] == 409
            and skip_sigid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_sigbase"] = (
            int(live.get("sigid") or 0) == DEFAULT_SIGID
            and int(live.get("sigbase") or 0) == DEFAULT_SIGBASE
            and int(live.get("port") or 0) > 0
        )
        checks["token_sigid_sign_verify_sigbase_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_sign_cycle["ok"] is False
            and skip_verify["ok"] is False
            and skip_sigbase["ok"] is False
            and skip_replay["ok"] is False
            and skip_sigid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="httpsig-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HTTPSIG_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_httpsig"] = (
        live_goal == HTTPSIG_ACTUATION_GOAL
        and HTTPSIG_ACTUATION_ID in live_done
        and live_source == "genesis_bind_httpsig"
    )

    with tempfile.TemporaryDirectory(prefix="httpsig-leftover-") as tmp:
        root = Path(tmp)
        open_before = leftover_is_open(HTTPSIG_LEFTOVER, root)
        register_catalog_proved(root, HTTPSIG_ACTUATION_ID)
        reason = leftover_satisfied_by(HTTPSIG_LEFTOVER, root)
        after = leftover_is_open(HTTPSIG_LEFTOVER, root)
    checks["httpsig_leftover_stays_open_without_closer"] = open_before is True
    checks["proved_httpsig_consumes_leftover"] = (
        after is False and reason.startswith(f"ledger:{HTTPSIG_ACTUATION_ID}")
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_httpsig_actuation_capability()
    return {
        "ok": ok,
        "action": "httpsig_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HTTPSIG_ACTUATION_GOAL,
        "done_when": HTTPSIG_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
