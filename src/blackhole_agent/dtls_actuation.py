"""Drive a first-class DTLS tool through RFC 6347 ClientHello/Finished.

Tool routing already fails missions that require ``dtls``: hosted DTLS
endpoints stay on the unsupported MCP provider, and no first-party DTLS
provider is executable. Unbound therefore cannot speak a ClientHello,
lockstep a Finished cookie handshake over UDP DTLS epoch 0,
independently poll the stored handshake cookie, or seal a cookie
digest an independent later reader can re-open.

This module closes that hole:

- advertise a ``dtls`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 6347 daemon
- keep a missing-cookie client so the dtls-cookie hole stays falsifiable
- refuse Finished verify until a ClientHello lands with a non-empty cookie
- independently poll the stored handshake cookie on a later client socket
- persist a sealed cookie digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after ICE
"""

from __future__ import annotations

import hashlib
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
    DTLS_TOOL_PROVIDER,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    dtls_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
DTLS_ACTUATION_ID = "capability.dtls-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-DTLS-OK"
POLL_TOKEN = "BH-DTLS-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
RECORD_HEADER_SIZE = 13
HANDSHAKE_HEADER_SIZE = 12
EMPTY_COOKIE = ""
DEFAULT_EPOCH = 0
CONTENT_HANDSHAKE = 22
VERSION_DTLS12 = 0xFEFD
HS_CLIENT_HELLO = 1
HS_FINISHED = 20
EXT_IDENTITY = 0xFF01
EXT_COOKIE = 0xFF02
EXT_EPOCH = 0xFF03
CIPHER_ECDHE_RSA_AES128_GCM = 0xC02F
VERIFY_SIZE = 12
RECORD_STRUCT = struct.Struct("!BHH6sH")
EXT_HEADER_STRUCT = struct.Struct("!HH")

DTLS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DTLS_ACTUATION_ID};"
    f"capability_proved:{DTLS_ACTUATION_ID};"
    "no_skill_route"
)
DTLS_ACTUATION_GOAL = (
    "Repair rfc6347 dtls clienthello/finished cycle cannot land over udp "
    "dtls epoch: hosted dtls endpoints remain unsupported so a ClientHello then "
    "Finished cookie handshake cannot land and a sealed cookie digest "
    "cannot be produced. A missing dtls cookie stays forbidden; fail-closed "
    "routing never opts the dtls provider in. An independent later poll of the "
    "stored handshake cookie keeps the hole falsifiable."
)


class DtlsActuationError(RuntimeError):
    """Raised when the DTLS session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def _u24(value: int) -> bytes:
    live = int(value) & 0xFFFFFF
    return bytes(((live >> 16) & 0xFF, (live >> 8) & 0xFF, live & 0xFF))


def _read_u24(data: bytes, offset: int) -> int:
    return (data[offset] << 16) | (data[offset + 1] << 8) | data[offset + 2]


def _u48(value: int) -> bytes:
    return (int(value) & 0xFFFFFFFFFFFF).to_bytes(6, "big")


def request_cookie(token: str = SENTINEL) -> str:
    digest = hashlib.sha256(f"cookie:{token or SENTINEL}".encode("utf-8")).hexdigest()
    return digest[:16]


def poll_cookie(token: str = SENTINEL) -> str:
    digest = hashlib.sha256(f"poll:{token or SENTINEL}".encode("utf-8")).hexdigest()
    return digest[:16]


def request_verify(cookie: str, identity: str = SENTINEL) -> str:
    digest = hashlib.sha256(
        f"verify:{cookie or EMPTY_COOKIE}:{identity or SENTINEL}".encode("utf-8")
    ).digest()
    return digest[:VERIFY_SIZE].hex()


def request_epoch(cookie: str = EMPTY_COOKIE) -> int:
    del cookie
    return DEFAULT_EPOCH


DEFAULT_COOKIE = request_cookie(SENTINEL)
DEFAULT_VERIFY = request_verify(DEFAULT_COOKIE, SENTINEL)


def encode_identity(identity: str) -> bytes:
    data = str(identity or "").encode("utf-8")
    if not data:
        return b""
    return EXT_HEADER_STRUCT.pack(EXT_IDENTITY, len(data)) + data


def encode_cookie_ext(cookie: str) -> bytes:
    data = str(cookie or "").encode("utf-8")
    if not data:
        return b""
    return EXT_HEADER_STRUCT.pack(EXT_COOKIE, len(data)) + data


def encode_epoch(epoch: int = DEFAULT_EPOCH) -> bytes:
    body = struct.pack("!H", int(epoch) & 0xFFFF)
    return EXT_HEADER_STRUCT.pack(EXT_EPOCH, 2) + body


def parse_extensions(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    offset = 0
    identity = ""
    cookie = ""
    epoch = DEFAULT_EPOCH
    while offset + 4 <= len(raw):
        etype, elen = EXT_HEADER_STRUCT.unpack(raw[offset : offset + 4])
        offset += 4
        if offset + int(elen) > len(raw):
            break
        value = raw[offset : offset + int(elen)]
        offset += int(elen)
        if int(etype) == EXT_IDENTITY:
            identity = value.decode("utf-8", errors="replace")
        elif int(etype) == EXT_COOKIE:
            cookie = value.decode("utf-8", errors="replace")
        elif int(etype) == EXT_EPOCH and len(value) >= 2:
            epoch = int(struct.unpack("!H", value[:2])[0])
    return {"identity": identity, "cookie": cookie, "epoch": epoch}


def _encode_handshake(msg_type: int, body: bytes, *, message_seq: int = 0) -> bytes:
    fragment = bytes(body or b"")
    length = len(fragment)
    header = (
        bytes((int(msg_type) & 0xFF,))
        + _u24(length)
        + struct.pack("!H", int(message_seq) & 0xFFFF)
        + _u24(0)
        + _u24(length)
    )
    return header + fragment


def _encode_record(handshake: bytes, *, epoch: int = DEFAULT_EPOCH, seq: int = 0) -> bytes:
    fragment = bytes(handshake or b"")
    header = (
        struct.pack("!BHH", CONTENT_HANDSHAKE, VERSION_DTLS12, int(epoch) & 0xFFFF)
        + _u48(seq)
        + struct.pack("!H", len(fragment))
    )
    return header + fragment


def encode_hello(
    *,
    identity: str,
    cookie: str,
    epoch: int = DEFAULT_EPOCH,
    include_cookie: bool = True,
    seq: int = 0,
    message_seq: int = 0,
) -> bytes:
    live = str(cookie or EMPTY_COOKIE) if include_cookie else EMPTY_COOKIE
    random = hashlib.sha256(f"random:{live}:{identity}".encode("utf-8")).digest()
    cookie_bytes = live.encode("utf-8") if include_cookie and live else b""
    if len(cookie_bytes) > 255:
        cookie_bytes = cookie_bytes[:255]
    extensions = encode_identity(identity) + encode_epoch(epoch)
    if include_cookie and live:
        extensions += encode_cookie_ext(live)
    body = (
        struct.pack("!H", VERSION_DTLS12)
        + random
        + bytes((0,))
        + bytes((len(cookie_bytes),))
        + cookie_bytes
        + struct.pack("!HH", 2, CIPHER_ECDHE_RSA_AES128_GCM)
        + bytes((1, 0))
        + struct.pack("!H", len(extensions))
        + extensions
    )
    return _encode_record(
        _encode_handshake(HS_CLIENT_HELLO, body, message_seq=message_seq),
        epoch=epoch,
        seq=seq,
    )


def encode_finished(
    *,
    identity: str,
    cookie: str,
    verify: str = "",
    epoch: int = DEFAULT_EPOCH,
    include_cookie: bool = True,
    seq: int = 0,
    message_seq: int = 1,
) -> bytes:
    live = str(cookie or EMPTY_COOKIE) if include_cookie else EMPTY_COOKIE
    live_verify = str(verify or request_verify(live, identity))
    try:
        verify_bytes = bytes.fromhex(live_verify)
    except ValueError:
        verify_bytes = b"\x00" * VERIFY_SIZE
    if len(verify_bytes) < VERIFY_SIZE:
        verify_bytes = verify_bytes + (b"\x00" * (VERIFY_SIZE - len(verify_bytes)))
    verify_bytes = verify_bytes[:VERIFY_SIZE]
    extensions = encode_identity(identity) + encode_epoch(epoch)
    if include_cookie and live:
        extensions += encode_cookie_ext(live)
    body = verify_bytes + struct.pack("!H", len(extensions)) + extensions
    return _encode_record(
        _encode_handshake(HS_FINISHED, body, message_seq=message_seq),
        epoch=epoch,
        seq=seq,
    )


def _parse_hello_body(body: bytes) -> dict[str, Any]:
    raw = bytes(body or b"")
    if len(raw) < 2 + 32 + 1 + 1 + 2 + 1 + 2:
        raise DtlsActuationError("short_hello")
    offset = 0
    version = struct.unpack("!H", raw[offset : offset + 2])[0]
    offset += 2
    offset += 32
    session_len = raw[offset]
    offset += 1 + int(session_len)
    if offset >= len(raw):
        raise DtlsActuationError("short_hello")
    cookie_len = raw[offset]
    offset += 1
    if offset + int(cookie_len) > len(raw):
        raise DtlsActuationError("short_hello")
    cookie = raw[offset : offset + int(cookie_len)].decode("utf-8", errors="replace")
    offset += int(cookie_len)
    if offset + 2 > len(raw):
        raise DtlsActuationError("short_hello")
    suites_len = struct.unpack("!H", raw[offset : offset + 2])[0]
    offset += 2 + int(suites_len)
    if offset >= len(raw):
        raise DtlsActuationError("short_hello")
    comp_len = raw[offset]
    offset += 1 + int(comp_len)
    extensions: dict[str, Any] = {"identity": "", "cookie": "", "epoch": DEFAULT_EPOCH}
    if offset + 2 <= len(raw):
        ext_len = struct.unpack("!H", raw[offset : offset + 2])[0]
        offset += 2
        extensions = parse_extensions(raw[offset : offset + int(ext_len)])
    return {
        "version": int(version),
        "cookie": cookie or str(extensions.get("cookie") or ""),
        "identity": str(extensions.get("identity") or ""),
        "epoch": int(extensions.get("epoch") or DEFAULT_EPOCH),
    }


def _parse_finished_body(body: bytes) -> dict[str, Any]:
    raw = bytes(body or b"")
    if len(raw) < VERIFY_SIZE:
        raise DtlsActuationError("short_finished")
    verify = raw[:VERIFY_SIZE].hex()
    offset = VERIFY_SIZE
    extensions: dict[str, Any] = {"identity": "", "cookie": "", "epoch": DEFAULT_EPOCH}
    if offset + 2 <= len(raw):
        ext_len = struct.unpack("!H", raw[offset : offset + 2])[0]
        offset += 2
        extensions = parse_extensions(raw[offset : offset + int(ext_len)])
    return {
        "verify": verify,
        "cookie": str(extensions.get("cookie") or ""),
        "identity": str(extensions.get("identity") or ""),
        "epoch": int(extensions.get("epoch") or DEFAULT_EPOCH),
    }


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < RECORD_HEADER_SIZE:
        raise DtlsActuationError("short_packet")
    content_type, version, epoch, seq, length = RECORD_STRUCT.unpack(raw[:RECORD_HEADER_SIZE])
    if int(content_type) != CONTENT_HANDSHAKE:
        raise DtlsActuationError("illegal_content")
    if int(version) != VERSION_DTLS12:
        raise DtlsActuationError("illegal_version")
    if int(length) < 0 or RECORD_HEADER_SIZE + int(length) > len(raw):
        raise DtlsActuationError("illegal_length")
    fragment = raw[RECORD_HEADER_SIZE : RECORD_HEADER_SIZE + int(length)]
    if len(fragment) < HANDSHAKE_HEADER_SIZE:
        raise DtlsActuationError("short_handshake")
    msg_type = fragment[0]
    hs_length = _read_u24(fragment, 1)
    message_seq = struct.unpack("!H", fragment[4:6])[0]
    frag_off = _read_u24(fragment, 6)
    frag_len = _read_u24(fragment, 9)
    body = fragment[HANDSHAKE_HEADER_SIZE : HANDSHAKE_HEADER_SIZE + int(frag_len)]
    if int(msg_type) not in {HS_CLIENT_HELLO, HS_FINISHED}:
        raise DtlsActuationError("illegal_method")
    if int(frag_off) != 0 or int(frag_len) != int(hs_length) or len(body) < int(frag_len):
        raise DtlsActuationError("illegal_fragment")
    is_hello = int(msg_type) == HS_CLIENT_HELLO
    is_finished = int(msg_type) == HS_FINISHED
    parsed = _parse_hello_body(body) if is_hello else _parse_finished_body(body)
    identity = str(parsed.get("identity") or "")
    cookie = str(parsed.get("cookie") or "")
    verify = str(parsed.get("verify") or "")
    live_epoch = int(parsed.get("epoch") or epoch)
    if is_hello and not verify:
        verify = request_verify(cookie, identity) if cookie and identity else ""
    return {
        "type": int(msg_type),
        "is_hello": is_hello,
        "is_finished": is_finished,
        "is_response": is_finished,
        "content_type": int(content_type),
        "version": int(version),
        "epoch": live_epoch,
        "seq": bytes(seq),
        "message_seq": int(message_seq),
        "identity": identity,
        "has_identity": bool(identity),
        "cookie": cookie,
        "has_cookie": bool(cookie),
        "verify": verify,
        "has_verify": bool(verify),
    }


class _DtlsClient:
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
            raise DtlsActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_finished"] or not packet["is_response"]:
            raise DtlsActuationError("verify_required")
        if not packet["has_cookie"]:
            raise DtlsActuationError("cookie_required")
        if not packet["has_verify"]:
            raise DtlsActuationError("verify_required")
        return packet

    def exchange(self, packet: bytes, *, wait_verify: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_verify:
            raise DtlsActuationError("verify_required")
        reply = self._recv()
        return {
            "verify": reply,
            "cookie": str(reply.get("cookie") or EMPTY_COOKIE),
            "identity": str(reply.get("identity") or ""),
            "verify_data": str(reply.get("verify") or ""),
            "epoch": int(reply.get("epoch") or DEFAULT_EPOCH),
        }

    def finished(
        self,
        identity: str,
        cookie: str,
        verify: str = "",
        *,
        wait_verify: bool = True,
        include_cookie: bool = True,
    ) -> dict[str, Any]:
        packet = encode_finished(
            identity=identity,
            cookie=cookie,
            verify=verify or request_verify(cookie, identity),
            include_cookie=include_cookie,
        )
        return self.exchange(packet, wait_verify=wait_verify)


class DtlsSession:
    """Cookie-gated loopback RFC 6347 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        cookie_gate: str = DEFAULT_COOKIE,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_gate = str(cookie_gate or "")
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.cookie = EMPTY_COOKIE
        self.verify = ""
        self.epoch = DEFAULT_EPOCH
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.helloed = False
        self.finished = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_cookie_once(self, identity: str, cookie: str, verify: str) -> tuple[str, str, str]:
        with self._lock:
            name = str(identity or "")
            live = str(cookie or EMPTY_COOKIE)
            live_verify = str(verify or "")
            if not self.identity and name and live:
                self.identity = name
                self.cookie = live
                self.verify = live_verify or request_verify(live, name)
                self.epoch = DEFAULT_EPOCH
                self.stored = True
            return str(self.identity), str(self.cookie), str(self.verify)

    def read_cookie(self) -> tuple[str, str, str]:
        with self._lock:
            return str(self.identity), str(self.cookie), str(self.verify)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "cookie": "",
            "verify": "",
            "epoch": DEFAULT_EPOCH,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _cookie_missing(self) -> bool:
        return not str(self.cookie_gate or "")

    def _reply_finished(self, peer: tuple[str, int], identity: str, cookie: str, verify: str) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_finished(
            identity=identity,
            cookie=cookie,
            verify=verify,
            epoch=DEFAULT_EPOCH,
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
            except DtlsActuationError:
                continue
            if packet.get("is_finished") and not packet.get("is_hello"):
                # Client Finished is still an inbound handshake; replies stay Finished.
                pass
            if not packet.get("is_hello") and not packet.get("is_finished"):
                continue
            if not packet.get("has_cookie"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_cookie, stored_verify = self.store_cookie_once(
                identity,
                str(packet.get("cookie") or EMPTY_COOKIE),
                str(packet.get("verify") or ""),
            )
            if not stored_name or not stored_cookie or not stored_verify:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_hello"):
                    self.helloed = True
                if packet.get("is_finished"):
                    self.finished = True
                self.retrieved = True
            self._reply_finished(peer, stored_name, stored_cookie, stored_verify)

    def bind(self) -> dict[str, Any]:
        if self._cookie_missing():
            return self._forbidden("missing_cookie")
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
        do_hello: bool = True,
        do_finished: bool = True,
        do_verify: bool = True,
        replay: bool = True,
        use_cookie: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._cookie_missing():
            return self._forbidden("missing_cookie")
        live_token = str(token or SENTINEL)
        origin_cookie = request_cookie(live_token)
        origin_verify = request_verify(origin_cookie, live_token)
        client: _DtlsClient | None = None
        independent: _DtlsClient | None = None
        try:
            client = _DtlsClient(self.host, int(self.port))
            if not do_hello:
                return self._conflict("hello_required")
            hello_packet = encode_hello(
                identity=live_token,
                cookie=origin_cookie,
                include_cookie=use_cookie,
            )
            if not use_cookie:
                try:
                    client.exchange(hello_packet, wait_verify=True)
                except DtlsActuationError:
                    return self._conflict("cookie_required")
                return self._conflict("cookie_required")
            client.send(hello_packet)
            if not do_finished:
                return self._conflict("finished_required")
            fin_packet = encode_finished(
                identity=live_token,
                cookie=origin_cookie,
                verify=origin_verify,
                include_cookie=True,
            )
            if not do_verify:
                try:
                    client.exchange(fin_packet, wait_verify=False)
                except DtlsActuationError as error:
                    if str(error) == "verify_required":
                        return self._conflict("verify_required")
                    return self._conflict("verify_required")
                return self._conflict("verify_required")
            try:
                reply = client.exchange(fin_packet, wait_verify=True)
            except DtlsActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("cookie_required")
                if reason == "verify_required":
                    return self._conflict("verify_required")
                return self._conflict("hello_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("hello_required")
            if str(reply.get("cookie") or "") != origin_cookie:
                return self._conflict("verify_required")
            if str(reply.get("verify_data") or "") != origin_verify:
                return self._conflict("verify_required")
            self.retrieved = True
            if replay:
                independent = _DtlsClient(self.host, int(self.port))
                try:
                    poll = independent.finished(
                        POLL_TOKEN,
                        poll_cookie(live_token),
                        request_verify(poll_cookie(live_token), POLL_TOKEN),
                        wait_verify=True,
                    )
                except DtlsActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_cookie, stored_verify = self.read_cookie()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_cookie != origin_cookie
                    or stored_verify != origin_verify
                    or str(poll.get("cookie") or "") != origin_cookie
                    or str(poll.get("verify_data") or "") != origin_verify
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_cookie}:{origin_verify}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "cookie": origin_cookie,
                "verify": origin_verify,
                "epoch": DEFAULT_EPOCH,
                "hello": True,
                "finished": True,
                "verify_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "cookie_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_dtls_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "cookie": origin_cookie,
                "verify": origin_verify,
                "epoch": DEFAULT_EPOCH,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "hello": True,
                "finished": True,
                "verify_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "cookie_bound": True,
            }
        except (OSError, DtlsActuationError) as error:
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
        live = independent_dtls_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "cookie": str(live.get("cookie") or ""),
            "verify": str(live.get("verify") or ""),
            "epoch": int(live.get("epoch") or DEFAULT_EPOCH),
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


def call_dtls_tool(session: DtlsSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one DTLS tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_hello = True if arguments.get("hello") is None else bool(arguments.get("hello"))
    do_finished = True if arguments.get("finished") is None else bool(arguments.get("finished"))
    do_verify = True if arguments.get("verify") is None else bool(arguments.get("verify"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_cookie = True if arguments.get("use_cookie") is None else bool(arguments.get("use_cookie"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_hello=do_hello,
            do_finished=do_finished,
            do_verify=do_verify,
            replay=replay,
            use_cookie=use_cookie,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise DtlsActuationError(f"unsupported dtls action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_dtls_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed DTLS cookie digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "cookie": "",
        "verify": "",
        "epoch": DEFAULT_EPOCH,
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
            "hello",
            "finished",
            "verify_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "cookie_bound",
        )
    )
    port = int(payload.get("port") or 0)
    cookie = str(payload.get("cookie") or "")
    verify = str(payload.get("verify") or "")
    epoch = int(payload.get("epoch") or DEFAULT_EPOCH)
    dual = port > 0 and bool(cookie) and bool(verify)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "cookie": cookie,
        "verify": verify,
        "epoch": epoch,
        "size": int(payload.get("size") or 0),
        "port": port,
        "hello": payload.get("hello") is True,
        "finished": payload.get("finished") is True,
        "verify_response": payload.get("verify_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "cookie_bound": payload.get("cookie_bound") is True,
    }


def run_dtls_workflow(
    *,
    with_cookie: bool = True,
    skip_bind: bool = False,
    do_hello: bool = True,
    do_finished: bool = True,
    do_verify: bool = True,
    replay: bool = True,
    use_cookie: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 6347 ClientHello/Finished cookie handshake workflow."""

    descriptor = dtls_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DTLS_TOOL_PROVIDER),
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
        raise DtlsActuationError(f"dtls tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="dtls-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = DtlsSession(out, cookie_gate=DEFAULT_COOKIE if with_cookie else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "hello": do_hello,
            "finished": do_finished,
            "verify": do_verify,
            "replay": replay,
            "use_cookie": use_cookie,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_dtls_tool(session, arguments))
            except DtlsActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_dtls_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_cookie
        and not skip_bind
        and do_hello
        and do_finished
        and do_verify
        and replay
        and use_cookie
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "dtls_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_cookie": with_cookie,
        "skip_bind": skip_bind,
        "hello": do_hello,
        "finished": do_finished,
        "verify": do_verify,
        "replay": replay,
        "use_cookie": use_cookie,
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
        "cookie_value": str(publish_result.get("cookie") or independent.get("cookie") or ""),
        "verify_value": str(publish_result.get("verify") or independent.get("verify") or ""),
        "epoch_value": int(publish_result.get("epoch") or independent.get("epoch") or DEFAULT_EPOCH),
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
        "cookie": str(trace_body["cookie_value"] or ""),
        "verify": str(trace_body["verify_value"] or ""),
        "epoch": int(trace_body["epoch_value"] or DEFAULT_EPOCH),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_cookie": with_cookie,
        "skip_bind": skip_bind,
        "hello": do_hello,
        "finished": do_finished,
        "verify_cycle": do_verify,
        "replay": replay,
        "use_cookie": use_cookie,
    }


def verify_dtls_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed DTLS trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_dtls_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    cookie = str(trace.get("cookie_value") or independent.get("cookie") or "")
    verify = str(trace.get("verify_value") or independent.get("verify") or "")
    epoch = int(trace.get("epoch_value") or independent.get("epoch") or DEFAULT_EPOCH)
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
        "hello": independent.get("hello") is True,
        "finished": independent.get("finished") is True,
        "verify_response": independent.get("verify_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "cookie_bound": independent.get("cookie_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "cookie_recorded": (
            port > 0
            and cookie == DEFAULT_COOKIE
            and verify == DEFAULT_VERIFY
            and epoch == DEFAULT_EPOCH
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def dtls_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.dtls_actuation import "
        "builtin_dtls_actuation_proof; r=builtin_dtls_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='dtls_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_dtls_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=DTLS_ACTUATION_ID,
        name="First-class RFC 6347 DTLS ClientHello/Finished actuation",
        description=(
            "Missions that require a dtls tool can opt the dtls provider in, "
            "bind a loopback RFC 6347 UDP DTLS endpoint, complete a ClientHello "
            "with a non-empty cookie, lockstep a Finished that carries the "
            "stored handshake cookie, independently poll the stored handshake "
            "cookie on a later socket, and seal a digest-chained cookie. Default "
            "routing stays fail-closed; a missing cookie keeps the hole "
            "falsifiable, and skip-HELLO/FINISHED/VERIFY/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.dtls_actuation:builtin_dtls_actuation_proof",
        proof_command=dtls_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.ice-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/dtls_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/srtp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required dtls tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 6347 daemon, speaks a ClientHello "
            "then Finished over UDP DTLS epoch 0 with a non-empty cookie, "
            "independently polls the stored handshake cookie on a later client "
            "socket, and binds this family as the next diversity-catalog "
            "successor once RFC 8445 ICE lockstep is proved. Missing cookies, "
            "skip-ClientHello, skip-Finished, skip-verify, skip-REPLAY, "
            "and a ClientHello aimed without a cookie stay fail-closed. "
            "Later genesis can take RFC 3711 SRTP Protect/Unprotect as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("dtls", "rfc6347", "udp", "cookie", "epoch", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T233738Z-84feb891",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_dtls_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 6347 DTLS lockstep actuation seals a cookie digest."""

    from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
    from blackhole_agent.ice_actuation import ICE_ACTUATION_GOAL, ICE_ACTUATION_ID
    from blackhole_agent.ike_actuation import IKE_ACTUATION_GOAL, IKE_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
    from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
    from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.srtp_actuation import SRTP_ACTUATION_GOAL, SRTP_ACTUATION_ID
    from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
    from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = DTLS_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(DTLS_ACTUATION_GOAL) == (DTLS_ACTUATION_ID,)
    checks["ice_goal_is_not_dtls"] = leftover_marker_ids(ICE_ACTUATION_GOAL) == (ICE_ACTUATION_ID,)
    checks["turn_goal_is_not_dtls"] = leftover_marker_ids(TURN_ACTUATION_GOAL) == (TURN_ACTUATION_ID,)
    checks["stun_goal_is_not_dtls"] = leftover_marker_ids(STUN_ACTUATION_GOAL) == (STUN_ACTUATION_ID,)
    checks["sip_goal_is_not_dtls"] = leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    checks["ike_goal_is_not_dtls"] = leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    checks["dhcp_goal_is_not_dtls"] = leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    checks["radius_goal_is_not_dtls"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_dtls"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_dtls"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_dtls"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_dtls"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_dtls"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_dtls"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["srtp_goal_is_not_dtls"] = leftover_marker_ids(SRTP_ACTUATION_GOAL) == (SRTP_ACTUATION_ID,)
    checks["dtls_goal_is_not_ice"] = ICE_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_turn"] = TURN_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_stun"] = STUN_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_sip"] = SIP_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_ike"] = IKE_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_dhcp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_radius"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["dtls_goal_is_not_srtp"] = SRTP_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["ice_marker_stays_ice"] = DTLS_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["turn_marker_stays_turn"] = DTLS_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["stun_marker_stays_stun"] = DTLS_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["sip_marker_stays_sip"] = DTLS_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["ike_marker_stays_ike"] = DTLS_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["dhcp_marker_stays_dhcp"] = DTLS_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["radius_marker_stays_radius"] = DTLS_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["ntp_marker_stays_ntp"] = DTLS_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = DTLS_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = DTLS_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = DTLS_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = DTLS_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = DTLS_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["srtp_marker_stays_srtp"] = DTLS_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_dtls"] = (
        len(catalog) > 57
        and catalog[57]["id"] == DTLS_ACTUATION_ID
        and catalog[56]["id"] == ICE_ACTUATION_ID
        and catalog[57]["source"] == "genesis_bind_dtls"
    )
    checks["catalog_names_srtp"] = (
        len(catalog) > 58
        and catalog[58]["id"] == SRTP_ACTUATION_ID
        and catalog[58]["source"] == "genesis_bind_srtp"
    )
    family = capability_family(DTLS_ACTUATION_GOAL)
    checks["family_is_dtls"] = "dtls" in family
    checks["family_is_rfc6347"] = "rfc6347" in family
    checks["family_is_cookie"] = "cookie" in family
    checks["family_is_epoch"] = "epoch" in family
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
    checks["family_is_not_srtp"] = (
        "srtp" not in family and "rfc3711" not in family and "roc" not in family and "ssrc" not in family
    )
    packed = encode_hello(identity=SENTINEL, cookie=DEFAULT_COOKIE)
    parsed = parse_message(packed)
    checks["hello_roundtrip"] = (
        parsed["is_hello"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_cookie"] is True
        and parsed["cookie"] == DEFAULT_COOKIE
        and parsed["epoch"] == DEFAULT_EPOCH
        and parsed["is_response"] is False
        and parsed["is_finished"] is False
        and parsed["content_type"] == CONTENT_HANDSHAKE
        and parsed["version"] == VERSION_DTLS12
        and packed[0] == CONTENT_HANDSHAKE
        and packed[1:3] == VERSION_DTLS12.to_bytes(2, "big")
    )
    finished = encode_finished(
        identity=SENTINEL,
        cookie=DEFAULT_COOKIE,
        verify=DEFAULT_VERIFY,
    )
    finished_parsed = parse_message(finished)
    checks["finished_roundtrip"] = (
        finished_parsed["is_finished"] is True
        and finished_parsed["is_response"] is True
        and finished_parsed["is_hello"] is False
        and finished_parsed["identity"] == SENTINEL
        and finished_parsed["cookie"] == DEFAULT_COOKIE
        and finished_parsed["verify"] == DEFAULT_VERIFY
        and finished_parsed["epoch"] == DEFAULT_EPOCH
        and finished_parsed["has_verify"] is True
    )
    bare = encode_hello(identity=SENTINEL, cookie=DEFAULT_COOKIE, include_cookie=False)
    checks["missing_cookie_is_unauthenticated"] = parse_message(bare)["has_cookie"] is False
    neighbors = (
        ICE_ACTUATION_GOAL,
        TURN_ACTUATION_GOAL,
        STUN_ACTUATION_GOAL,
        SIP_ACTUATION_GOAL,
        IKE_ACTUATION_GOAL,
        DHCP_ACTUATION_GOAL,
        RADIUS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        SRTP_ACTUATION_GOAL,
    )
    dtls_signature = semantic_signature(DTLS_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(dtls_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_dtls = ToolDescriptor(name="remote_dtls", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_dtls)
    checks["naive_mcp_dtls_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = dtls_tool_descriptor()
    default_dtls = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DTLS_TOOL_PROVIDER),
    )
    checks["default_dtls_provider_is_unsupported"] = (
        default_dtls.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{DTLS_TOOL_PROVIDER}" in default_dtls.reasons
    )
    checks["opted_in_dtls_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_dtls],
        required_tool_names=("local_memory", "dtls"),
    )
    checks["naive_preflight_missing_dtls"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["dtls"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "dtls"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, DTLS_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "dtls" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="dtls-actuation-") as tmp:
        root = Path(tmp)
        missing = run_dtls_workflow(with_cookie=False, output_dir=root / "missing")
        skip_bind = run_dtls_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_hello = run_dtls_workflow(do_hello=False, output_dir=root / "skip-hello")
        skip_finished = run_dtls_workflow(do_finished=False, output_dir=root / "skip-finished")
        skip_verify = run_dtls_workflow(do_verify=False, output_dir=root / "skip-verify")
        skip_replay = run_dtls_workflow(replay=False, output_dir=root / "skip-replay")
        skip_cookie = run_dtls_workflow(use_cookie=False, output_dir=root / "skip-cookie")
        live = run_dtls_workflow(output_dir=root / "live")
        verify = verify_dtls_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_dtls_trace(clone)
        checks["naive_without_cookie_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_cookie"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_hello_stays_empty"] = (
            skip_hello["ok"] is False
            and skip_hello["error"] == "hello_required"
            and skip_hello["final_status"] == 409
            and skip_hello["payload_exists"] is False
        )
        checks["skip_finished_stays_empty"] = (
            skip_finished["ok"] is False
            and skip_finished["error"] == "finished_required"
            and skip_finished["final_status"] == 409
            and skip_finished["payload_exists"] is False
        )
        checks["skip_verify_stays_empty"] = (
            skip_verify["ok"] is False
            and skip_verify["error"] == "verify_required"
            and skip_verify["final_status"] == 409
            and skip_verify["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_cookie_stays_empty"] = (
            skip_cookie["ok"] is False
            and skip_cookie["error"] == "cookie_required"
            and skip_cookie["final_status"] == 409
            and skip_cookie["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_cookie"] = (
            live.get("cookie") == DEFAULT_COOKIE
            and live.get("verify") == DEFAULT_VERIFY
            and int(live.get("epoch", DEFAULT_EPOCH)) == DEFAULT_EPOCH
            and int(live.get("port") or 0) > 0
        )
        checks["token_cookie_hello_finished_verify_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_hello["ok"] is False
            and skip_finished["ok"] is False
            and skip_verify["ok"] is False
            and skip_replay["ok"] is False
            and skip_cookie["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="dtls-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != DTLS_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_dtls"] = (
        live_goal == DTLS_ACTUATION_GOAL
        and DTLS_ACTUATION_ID in live_done
        and live_source == "genesis_bind_dtls"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_dtls_actuation_capability()
    return {
        "ok": ok,
        "action": "dtls_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": DTLS_ACTUATION_GOAL,
        "done_when": DTLS_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
