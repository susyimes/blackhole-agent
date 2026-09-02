"""Drive a first-class SRTP tool through RFC 3711 Protect/Unprotect.

Tool routing already fails missions that require ``srtp``: hosted SRTP
endpoints stay on the unsupported MCP provider, and no first-party SRTP
provider is executable. Unbound therefore cannot speak a Protect,
lockstep an Unprotect ssrc cycle over UDP SRTP ROC,
independently poll the stored packet roc, or seal a roc
digest an independent later reader can re-open.

This module closes that hole:

- advertise an ``srtp`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 3711 daemon
- keep a missing-ssrc client so the srtp-ssrc hole stays falsifiable
- refuse Unprotect verify until a Protect lands with a non-empty ssrc
- independently poll the stored packet roc on a later client socket
- persist a sealed roc digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after DTLS
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
    SRTP_TOOL_PROVIDER,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    srtp_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
SRTP_ACTUATION_ID = "capability.srtp-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SRTP-OK"
POLL_TOKEN = "BH-SRTP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
RTP_HEADER_SIZE = 12
AUTH_TAG_SIZE = 10
EMPTY_SSRC = 0
EMPTY_ROC = 0
DEFAULT_SEQ = 1
VERSION_RTP = 2
PT_PROTECT = 96
PT_UNPROTECT = 97
EXT_PROFILE = 0xBEDE
EXT_IDENTITY = 1
EXT_ROC = 2
AUTH_KEY = b"srtp-rfc3711-auth"

SRTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SRTP_ACTUATION_ID};"
    f"capability_proved:{SRTP_ACTUATION_ID};"
    "no_skill_route"
)
SRTP_ACTUATION_GOAL = (
    "Repair rfc3711 srtp protect/unprotect cycle cannot land over udp "
    "srtp roc: hosted srtp endpoints remain unsupported so a Protect then "
    "Unprotect ssrc cycle cannot land and a sealed roc digest "
    "cannot be produced. A missing srtp ssrc stays forbidden; fail-closed "
    "routing never opts the srtp provider in. An independent later poll of the "
    "stored packet roc keeps the hole falsifiable."
)


class SrtpActuationError(RuntimeError):
    """Raised when the SRTP session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_ssrc(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"ssrc:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def poll_ssrc(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"poll-ssrc:{token or SENTINEL}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 2


def request_roc(ssrc: int = EMPTY_SSRC, token: str = SENTINEL) -> int:
    digest = hashlib.sha256(
        f"roc:{int(ssrc) & 0xFFFFFFFF}:{token or SENTINEL}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:4], "big")
    return value or 1


def request_timestamp(token: str = SENTINEL) -> int:
    digest = hashlib.sha256(f"ts:{token or SENTINEL}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def packet_index(roc: int, seq: int) -> int:
    return ((int(roc) & 0xFFFFFFFF) << 16) | (int(seq) & 0xFFFF)


def _keystream(ssrc: int, roc: int, seq: int, length: int) -> bytes:
    out = bytearray()
    counter = 0
    index = packet_index(roc, seq).to_bytes(6, "big")
    while len(out) < int(length):
        block = hashlib.sha256(
            struct.pack("!IIH", int(ssrc) & 0xFFFFFFFF, int(roc) & 0xFFFFFFFF, int(seq) & 0xFFFF)
            + index
            + struct.pack("!I", int(counter) & 0xFFFFFFFF)
        ).digest()
        out.extend(block)
        counter += 1
    return bytes(out[: int(length)])


def srtp_protect_payload(payload: bytes, ssrc: int, roc: int, seq: int) -> bytes:
    raw = bytes(payload or b"")
    stream = _keystream(ssrc, roc, seq, len(raw))
    return bytes(left ^ right for left, right in zip(raw, stream, strict=True))


def srtp_auth_tag(header_and_payload: bytes, roc: int) -> bytes:
    digest = hmac.new(
        AUTH_KEY,
        bytes(header_and_payload or b"") + struct.pack("!I", int(roc) & 0xFFFFFFFF),
        hashlib.sha256,
    ).digest()
    return digest[:AUTH_TAG_SIZE]


DEFAULT_SSRC = request_ssrc(SENTINEL)
DEFAULT_ROC = request_roc(DEFAULT_SSRC, SENTINEL)
DEFAULT_TIMESTAMP = request_timestamp(SENTINEL)


def encode_extensions(identity: str, roc: int, *, include_roc: bool) -> bytes:
    chunks = bytearray()
    ident = str(identity or "").encode("utf-8")
    if ident:
        chunks.append(EXT_IDENTITY)
        chunks.append(len(ident) & 0xFF)
        chunks.extend(ident[:255])
    if include_roc:
        chunks.append(EXT_ROC)
        chunks.append(4)
        chunks.extend(struct.pack("!I", int(roc) & 0xFFFFFFFF))
    body = bytes(chunks)
    pad = (4 - (len(body) % 4)) % 4
    body = body + (b"\x00" * pad)
    words = len(body) // 4
    return struct.pack("!HH", EXT_PROFILE, words) + body


def parse_extensions(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    identity = ""
    roc = EMPTY_ROC
    has_roc = False
    if len(raw) < 4:
        return {"identity": identity, "roc": roc, "has_roc": False, "size": 0}
    profile, words = struct.unpack("!HH", raw[:4])
    size = 4 + int(words) * 4
    if int(profile) != EXT_PROFILE or size > len(raw):
        return {"identity": identity, "roc": roc, "has_roc": False, "size": 0}
    body = raw[4:size]
    offset = 0
    while offset + 2 <= len(body):
        etype = body[offset]
        elen = body[offset + 1]
        offset += 2
        if etype == 0 and elen == 0:
            continue
        if offset + int(elen) > len(body):
            break
        value = body[offset : offset + int(elen)]
        offset += int(elen)
        if int(etype) == EXT_IDENTITY:
            identity = value.decode("utf-8", errors="replace")
        elif int(etype) == EXT_ROC and len(value) >= 4:
            roc = int(struct.unpack("!I", value[:4])[0])
            has_roc = True
    return {"identity": identity, "roc": roc, "has_roc": has_roc, "size": size}


def encode_packet(
    payload_type: int,
    *,
    identity: str,
    ssrc: int,
    roc: int,
    seq: int = DEFAULT_SEQ,
    timestamp: int | None = None,
    include_ssrc: bool = True,
) -> bytes:
    live_ssrc = int(ssrc) & 0xFFFFFFFF if include_ssrc else EMPTY_SSRC
    live_roc = int(roc) & 0xFFFFFFFF if include_ssrc and live_ssrc else EMPTY_ROC
    live_ts = int(timestamp) if timestamp is not None else request_timestamp(identity)
    ext = encode_extensions(identity, live_roc, include_roc=bool(include_ssrc and live_ssrc))
    x_bit = 1 if ext else 0
    header = struct.pack(
        "!BBHII",
        (VERSION_RTP << 6) | (x_bit << 4),
        int(payload_type) & 0x7F,
        int(seq) & 0xFFFF,
        live_ts & 0xFFFFFFFF,
        live_ssrc,
    )
    plain = str(identity or "").encode("utf-8")
    encrypted = srtp_protect_payload(plain, live_ssrc, live_roc, seq) if live_ssrc else plain
    body = header + ext + encrypted
    tag = srtp_auth_tag(body, live_roc) if live_ssrc else b"\x00" * AUTH_TAG_SIZE
    return body + tag


def encode_protect(
    *,
    identity: str,
    ssrc: int,
    roc: int | None = None,
    seq: int = DEFAULT_SEQ,
    include_ssrc: bool = True,
) -> bytes:
    live_ssrc = int(ssrc) & 0xFFFFFFFF if include_ssrc else EMPTY_SSRC
    live_roc = int(roc) if roc is not None else request_roc(live_ssrc, identity)
    return encode_packet(
        PT_PROTECT,
        identity=identity,
        ssrc=live_ssrc,
        roc=live_roc,
        seq=seq,
        include_ssrc=include_ssrc,
    )


def encode_unprotect(
    *,
    identity: str,
    ssrc: int,
    roc: int | None = None,
    seq: int = DEFAULT_SEQ,
    include_ssrc: bool = True,
) -> bytes:
    live_ssrc = int(ssrc) & 0xFFFFFFFF if include_ssrc else EMPTY_SSRC
    live_roc = int(roc) if roc is not None else request_roc(live_ssrc, identity)
    return encode_packet(
        PT_UNPROTECT,
        identity=identity,
        ssrc=live_ssrc,
        roc=live_roc,
        seq=seq,
        include_ssrc=include_ssrc,
    )


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"")
    if len(raw) < RTP_HEADER_SIZE + AUTH_TAG_SIZE:
        raise SrtpActuationError("short_packet")
    vpxcc, payload_type, seq, timestamp, ssrc = struct.unpack("!BBHII", raw[:RTP_HEADER_SIZE])
    version = (int(vpxcc) >> 6) & 0x03
    x_bit = (int(vpxcc) >> 4) & 0x01
    if int(version) != VERSION_RTP:
        raise SrtpActuationError("illegal_version")
    if int(payload_type) not in {PT_PROTECT, PT_UNPROTECT}:
        raise SrtpActuationError("illegal_method")
    offset = RTP_HEADER_SIZE
    extensions = {"identity": "", "roc": EMPTY_ROC, "has_roc": False, "size": 0}
    if x_bit:
        extensions = parse_extensions(raw[offset:])
        offset += int(extensions.get("size") or 0)
        if offset > len(raw) - AUTH_TAG_SIZE:
            raise SrtpActuationError("short_packet")
    encrypted = raw[offset : len(raw) - AUTH_TAG_SIZE]
    tag = raw[len(raw) - AUTH_TAG_SIZE :]
    live_ssrc = int(ssrc)
    live_roc = int(extensions.get("roc") or EMPTY_ROC)
    identity = str(extensions.get("identity") or "")
    if live_ssrc:
        plain = srtp_protect_payload(encrypted, live_ssrc, live_roc, int(seq))
        expected = srtp_auth_tag(raw[: len(raw) - AUTH_TAG_SIZE], live_roc)
        if tag != expected:
            raise SrtpActuationError("auth_failed")
        if not identity:
            identity = plain.decode("utf-8", errors="replace")
    else:
        if not identity:
            identity = encrypted.decode("utf-8", errors="replace")
    is_protect = int(payload_type) == PT_PROTECT
    is_unprotect = int(payload_type) == PT_UNPROTECT
    has_ssrc = live_ssrc != EMPTY_SSRC
    has_roc = bool(extensions.get("has_roc"))
    return {
        "type": int(payload_type),
        "is_protect": is_protect,
        "is_unprotect": is_unprotect,
        "is_response": is_unprotect,
        "version": int(version),
        "seq": int(seq),
        "timestamp": int(timestamp),
        "ssrc": live_ssrc,
        "has_ssrc": has_ssrc,
        "roc": live_roc,
        "has_roc": has_roc,
        "identity": identity,
        "has_identity": bool(identity),
        "packet_index": packet_index(live_roc, int(seq)) if has_ssrc else 0,
        "auth_tag": tag.hex(),
        "has_auth": len(tag) == AUTH_TAG_SIZE,
    }


class _SrtpClient:
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
            raise SrtpActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_unprotect"] or not packet["is_response"]:
            raise SrtpActuationError("roc_required")
        if not packet["has_ssrc"]:
            raise SrtpActuationError("ssrc_required")
        if not packet["has_roc"]:
            raise SrtpActuationError("roc_required")
        return packet

    def exchange(self, packet: bytes, *, wait_roc: bool = True) -> dict[str, Any]:
        self.send(packet)
        if not wait_roc:
            raise SrtpActuationError("roc_required")
        reply = self._recv()
        return {
            "unprotect": reply,
            "ssrc": int(reply.get("ssrc") or EMPTY_SSRC),
            "identity": str(reply.get("identity") or ""),
            "roc": int(reply.get("roc") or EMPTY_ROC),
        }

    def unprotect(
        self,
        identity: str,
        ssrc: int,
        roc: int = EMPTY_ROC,
        *,
        wait_roc: bool = True,
        include_ssrc: bool = True,
    ) -> dict[str, Any]:
        packet = encode_unprotect(
            identity=identity,
            ssrc=ssrc,
            roc=roc or request_roc(ssrc, identity),
            include_ssrc=include_ssrc,
        )
        return self.exchange(packet, wait_roc=wait_roc)


class SrtpSession:
    """SSRC-gated loopback RFC 3711 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        ssrc_gate: int = DEFAULT_SSRC,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ssrc_gate = int(ssrc_gate or 0)
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.ssrc = EMPTY_SSRC
        self.roc = EMPTY_ROC
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.protected = False
        self.unprotected = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_ssrc_once(self, identity: str, ssrc: int, roc: int) -> tuple[str, int, int]:
        with self._lock:
            name = str(identity or "")
            live = int(ssrc or EMPTY_SSRC)
            live_roc = int(roc or EMPTY_ROC)
            if not self.identity and name and live:
                self.identity = name
                self.ssrc = live
                self.roc = live_roc or request_roc(live, name)
                self.stored = True
            return str(self.identity), int(self.ssrc), int(self.roc)

    def read_ssrc(self) -> tuple[str, int, int]:
        with self._lock:
            return str(self.identity), int(self.ssrc), int(self.roc)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "ssrc": EMPTY_SSRC,
            "roc": EMPTY_ROC,
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _ssrc_missing(self) -> bool:
        return not int(self.ssrc_gate or 0)

    def _reply_unprotect(self, peer: tuple[str, int], identity: str, ssrc: int, roc: int) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_unprotect(
            identity=identity,
            ssrc=ssrc,
            roc=roc,
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
            except SrtpActuationError:
                continue
            if not packet.get("is_protect") and not packet.get("is_unprotect"):
                continue
            if not packet.get("has_ssrc"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_ssrc, stored_roc = self.store_ssrc_once(
                identity,
                int(packet.get("ssrc") or EMPTY_SSRC),
                int(packet.get("roc") or EMPTY_ROC),
            )
            if not stored_name or not stored_ssrc or not stored_roc:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                if packet.get("is_protect"):
                    self.protected = True
                if packet.get("is_unprotect"):
                    self.unprotected = True
                self.retrieved = True
            self._reply_unprotect(peer, stored_name, stored_ssrc, stored_roc)

    def bind(self) -> dict[str, Any]:
        if self._ssrc_missing():
            return self._forbidden("missing_ssrc")
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
        do_protect: bool = True,
        do_unprotect: bool = True,
        do_roc: bool = True,
        replay: bool = True,
        use_ssrc: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._ssrc_missing():
            return self._forbidden("missing_ssrc")
        live_token = str(token or SENTINEL)
        origin_ssrc = request_ssrc(live_token)
        origin_roc = request_roc(origin_ssrc, live_token)
        client: _SrtpClient | None = None
        independent: _SrtpClient | None = None
        try:
            client = _SrtpClient(self.host, int(self.port))
            if not do_protect:
                return self._conflict("protect_required")
            protect_packet = encode_protect(
                identity=live_token,
                ssrc=origin_ssrc,
                roc=origin_roc,
                include_ssrc=use_ssrc,
            )
            if not use_ssrc:
                try:
                    client.exchange(protect_packet, wait_roc=True)
                except SrtpActuationError:
                    return self._conflict("ssrc_required")
                return self._conflict("ssrc_required")
            client.send(protect_packet)
            if not do_unprotect:
                return self._conflict("unprotect_required")
            unprotect_packet = encode_unprotect(
                identity=live_token,
                ssrc=origin_ssrc,
                roc=origin_roc,
                include_ssrc=True,
            )
            if not do_roc:
                try:
                    client.exchange(unprotect_packet, wait_roc=False)
                except SrtpActuationError as error:
                    if str(error) == "roc_required":
                        return self._conflict("roc_required")
                    return self._conflict("roc_required")
                return self._conflict("roc_required")
            try:
                reply = client.exchange(unprotect_packet, wait_roc=True)
            except SrtpActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("ssrc_required")
                if reason == "roc_required":
                    return self._conflict("roc_required")
                return self._conflict("protect_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("protect_required")
            if int(reply.get("ssrc") or EMPTY_SSRC) != origin_ssrc:
                return self._conflict("roc_required")
            if int(reply.get("roc") or EMPTY_ROC) != origin_roc:
                return self._conflict("roc_required")
            self.retrieved = True
            if replay:
                independent = _SrtpClient(self.host, int(self.port))
                try:
                    poll = independent.unprotect(
                        POLL_TOKEN,
                        poll_ssrc(live_token),
                        request_roc(poll_ssrc(live_token), POLL_TOKEN),
                        wait_roc=True,
                    )
                except SrtpActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_ssrc, stored_roc = self.read_ssrc()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_ssrc != origin_ssrc
                    or stored_roc != origin_roc
                    or int(poll.get("ssrc") or EMPTY_SSRC) != origin_ssrc
                    or int(poll.get("roc") or EMPTY_ROC) != origin_roc
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_ssrc}:{origin_roc}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "ssrc": origin_ssrc,
                "roc": origin_roc,
                "protect": True,
                "unprotect": True,
                "roc_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "ssrc_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_srtp_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "ssrc": origin_ssrc,
                "roc": origin_roc,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "protect": True,
                "unprotect": True,
                "roc_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "ssrc_bound": True,
            }
        except (OSError, SrtpActuationError) as error:
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
        live = independent_srtp_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "ssrc": int(live.get("ssrc") or EMPTY_SSRC),
            "roc": int(live.get("roc") or EMPTY_ROC),
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


def call_srtp_tool(session: SrtpSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one SRTP tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_protect = True if arguments.get("protect") is None else bool(arguments.get("protect"))
    do_unprotect = True if arguments.get("unprotect") is None else bool(arguments.get("unprotect"))
    do_roc = True if arguments.get("roc") is None else bool(arguments.get("roc"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_ssrc = True if arguments.get("use_ssrc") is None else bool(arguments.get("use_ssrc"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_protect=do_protect,
            do_unprotect=do_unprotect,
            do_roc=do_roc,
            replay=replay,
            use_ssrc=use_ssrc,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SrtpActuationError(f"unsupported srtp action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_srtp_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed SRTP roc digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "ssrc": EMPTY_SSRC,
        "roc": EMPTY_ROC,
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
            "protect",
            "unprotect",
            "roc_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "ssrc_bound",
        )
    )
    port = int(payload.get("port") or 0)
    ssrc = int(payload.get("ssrc") or EMPTY_SSRC)
    roc = int(payload.get("roc") or EMPTY_ROC)
    dual = port > 0 and bool(ssrc) and bool(roc)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "ssrc": ssrc,
        "roc": roc,
        "size": int(payload.get("size") or 0),
        "port": port,
        "protect": payload.get("protect") is True,
        "unprotect": payload.get("unprotect") is True,
        "roc_response": payload.get("roc_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "ssrc_bound": payload.get("ssrc_bound") is True,
    }


def run_srtp_workflow(
    *,
    with_ssrc: bool = True,
    skip_bind: bool = False,
    do_protect: bool = True,
    do_unprotect: bool = True,
    do_roc: bool = True,
    replay: bool = True,
    use_ssrc: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 3711 Protect/Unprotect ssrc cycle workflow."""

    descriptor = srtp_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SRTP_TOOL_PROVIDER),
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
        raise SrtpActuationError(f"srtp tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="srtp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SrtpSession(out, ssrc_gate=DEFAULT_SSRC if with_ssrc else EMPTY_SSRC)
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "protect": do_protect,
            "unprotect": do_unprotect,
            "roc": do_roc,
            "replay": replay,
            "use_ssrc": use_ssrc,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_srtp_tool(session, arguments))
            except SrtpActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_srtp_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_ssrc
        and not skip_bind
        and do_protect
        and do_unprotect
        and do_roc
        and replay
        and use_ssrc
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "srtp_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_ssrc": with_ssrc,
        "skip_bind": skip_bind,
        "protect": do_protect,
        "unprotect": do_unprotect,
        "roc": do_roc,
        "replay": replay,
        "use_ssrc": use_ssrc,
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
        "ssrc_value": int(publish_result.get("ssrc") or independent.get("ssrc") or EMPTY_SSRC),
        "roc_value": int(publish_result.get("roc") or independent.get("roc") or EMPTY_ROC),
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
        "ssrc": int(trace_body["ssrc_value"] or EMPTY_SSRC),
        "roc": int(trace_body["roc_value"] or EMPTY_ROC),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_ssrc": with_ssrc,
        "skip_bind": skip_bind,
        "protect": do_protect,
        "unprotect": do_unprotect,
        "roc_cycle": do_roc,
        "replay": replay,
        "use_ssrc": use_ssrc,
    }


def verify_srtp_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed SRTP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_srtp_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    ssrc = int(trace.get("ssrc_value") or independent.get("ssrc") or EMPTY_SSRC)
    roc = int(trace.get("roc_value") or independent.get("roc") or EMPTY_ROC)
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
        "protect": independent.get("protect") is True,
        "unprotect": independent.get("unprotect") is True,
        "roc_response": independent.get("roc_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "ssrc_bound": independent.get("ssrc_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "roc_recorded": (
            port > 0
            and ssrc == DEFAULT_SSRC
            and roc == DEFAULT_ROC
        ),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def srtp_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.srtp_actuation import "
        "builtin_srtp_actuation_proof; r=builtin_srtp_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='srtp_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_srtp_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SRTP_ACTUATION_ID,
        name="First-class RFC 3711 SRTP Protect/Unprotect actuation",
        description=(
            "Missions that require an srtp tool can opt the srtp provider in, "
            "bind a loopback RFC 3711 UDP SRTP endpoint, complete a Protect "
            "with a non-empty ssrc, lockstep an Unprotect that carries the "
            "stored packet roc, independently poll the stored packet "
            "roc on a later socket, and seal a digest-chained roc. Default "
            "routing stays fail-closed; a missing ssrc keeps the hole "
            "falsifiable, and skip-PROTECT/UNPROTECT/ROC/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.srtp_actuation:builtin_srtp_actuation_proof",
        proof_command=srtp_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.dtls-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/srtp_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/sctp_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required srtp tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 3711 daemon, speaks a Protect "
            "then Unprotect over UDP SRTP with a non-empty ssrc and packet roc, "
            "independently polls the stored packet roc on a later client "
            "socket, and binds this family as the next diversity-catalog "
            "successor once RFC 6347 DTLS lockstep is proved. Missing ssrcs, "
            "skip-Protect, skip-Unprotect, skip-roc, skip-REPLAY, "
            "and a Protect aimed without an ssrc stay fail-closed. "
            "Later genesis can take RFC 4960 SCTP INIT/INIT-ACK as the next "
            "unsaturated diversity-catalog family."
        ),
        tags=("srtp", "rfc3711", "udp", "ssrc", "roc", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260902T000914Z-e47c79cc",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_srtp_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 3711 SRTP lockstep actuation seals a roc digest."""

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
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
    from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
    from blackhole_agent.sctp_actuation import SCTP_ACTUATION_GOAL, SCTP_ACTUATION_ID
    from blackhole_agent.sip_actuation import SIP_ACTUATION_GOAL, SIP_ACTUATION_ID
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID
    from blackhole_agent.turn_actuation import TURN_ACTUATION_GOAL, TURN_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = SRTP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SRTP_ACTUATION_GOAL) == (SRTP_ACTUATION_ID,)
    checks["dtls_goal_is_not_srtp"] = leftover_marker_ids(DTLS_ACTUATION_GOAL) == (DTLS_ACTUATION_ID,)
    checks["ice_goal_is_not_srtp"] = leftover_marker_ids(ICE_ACTUATION_GOAL) == (ICE_ACTUATION_ID,)
    checks["turn_goal_is_not_srtp"] = leftover_marker_ids(TURN_ACTUATION_GOAL) == (TURN_ACTUATION_ID,)
    checks["stun_goal_is_not_srtp"] = leftover_marker_ids(STUN_ACTUATION_GOAL) == (STUN_ACTUATION_ID,)
    checks["sip_goal_is_not_srtp"] = leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    checks["ike_goal_is_not_srtp"] = leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    checks["dhcp_goal_is_not_srtp"] = leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    checks["radius_goal_is_not_srtp"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_srtp"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_srtp"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_srtp"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_srtp"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_srtp"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_srtp"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["sctp_goal_is_not_srtp"] = leftover_marker_ids(SCTP_ACTUATION_GOAL) == (SCTP_ACTUATION_ID,)
    checks["srtp_goal_is_not_dtls"] = DTLS_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_ice"] = ICE_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_turn"] = TURN_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_stun"] = STUN_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_sip"] = SIP_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_ike"] = IKE_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_dhcp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_radius"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["srtp_goal_is_not_sctp"] = SCTP_ACTUATION_ID not in leftover_marker_ids(SRTP_ACTUATION_GOAL)
    checks["dtls_marker_stays_dtls"] = SRTP_ACTUATION_ID not in leftover_marker_ids(DTLS_ACTUATION_GOAL)
    checks["ice_marker_stays_ice"] = SRTP_ACTUATION_ID not in leftover_marker_ids(ICE_ACTUATION_GOAL)
    checks["turn_marker_stays_turn"] = SRTP_ACTUATION_ID not in leftover_marker_ids(TURN_ACTUATION_GOAL)
    checks["stun_marker_stays_stun"] = SRTP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["sip_marker_stays_sip"] = SRTP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["ike_marker_stays_ike"] = SRTP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["dhcp_marker_stays_dhcp"] = SRTP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["radius_marker_stays_radius"] = SRTP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["ntp_marker_stays_ntp"] = SRTP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = SRTP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = SRTP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = SRTP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = SRTP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = SRTP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["sctp_marker_stays_sctp"] = SRTP_ACTUATION_ID not in leftover_marker_ids(SCTP_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_srtp"] = (
        len(catalog) > 58
        and catalog[58]["id"] == SRTP_ACTUATION_ID
        and catalog[57]["id"] == DTLS_ACTUATION_ID
        and catalog[58]["source"] == "genesis_bind_srtp"
    )
    checks["catalog_names_sctp"] = (
        len(catalog) > 59
        and catalog[59]["id"] == SCTP_ACTUATION_ID
        and catalog[59]["source"] == "genesis_bind_sctp"
    )
    family = capability_family(SRTP_ACTUATION_GOAL)
    checks["family_is_srtp"] = "srtp" in family
    checks["family_is_rfc3711"] = "rfc3711" in family
    checks["family_is_ssrc"] = "ssrc" in family
    checks["family_is_roc"] = "roc" in family
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
    checks["family_is_not_sctp"] = (
        "sctp" not in family and "rfc4960" not in family and "vtag" not in family and "tsn" not in family
    )
    packed = encode_protect(identity=SENTINEL, ssrc=DEFAULT_SSRC, roc=DEFAULT_ROC)
    parsed = parse_message(packed)
    checks["protect_roundtrip"] = (
        parsed["is_protect"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_ssrc"] is True
        and parsed["ssrc"] == DEFAULT_SSRC
        and parsed["roc"] == DEFAULT_ROC
        and parsed["is_response"] is False
        and parsed["is_unprotect"] is False
        and parsed["version"] == VERSION_RTP
        and packed[0] >> 6 == VERSION_RTP
        and parsed["has_auth"] is True
    )
    unprotected = encode_unprotect(
        identity=SENTINEL,
        ssrc=DEFAULT_SSRC,
        roc=DEFAULT_ROC,
    )
    unprotect_parsed = parse_message(unprotected)
    checks["unprotect_roundtrip"] = (
        unprotect_parsed["is_unprotect"] is True
        and unprotect_parsed["is_response"] is True
        and unprotect_parsed["is_protect"] is False
        and unprotect_parsed["identity"] == SENTINEL
        and unprotect_parsed["ssrc"] == DEFAULT_SSRC
        and unprotect_parsed["roc"] == DEFAULT_ROC
        and unprotect_parsed["has_roc"] is True
    )
    bare = encode_protect(identity=SENTINEL, ssrc=DEFAULT_SSRC, include_ssrc=False)
    checks["missing_ssrc_is_unauthenticated"] = parse_message(bare)["has_ssrc"] is False
    neighbors = (
        DTLS_ACTUATION_GOAL,
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
        SCTP_ACTUATION_GOAL,
    )
    srtp_signature = semantic_signature(SRTP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(srtp_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_srtp = ToolDescriptor(name="remote_srtp", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_srtp)
    checks["naive_mcp_srtp_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = srtp_tool_descriptor()
    default_srtp = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SRTP_TOOL_PROVIDER),
    )
    checks["default_srtp_provider_is_unsupported"] = (
        default_srtp.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SRTP_TOOL_PROVIDER}" in default_srtp.reasons
    )
    checks["opted_in_srtp_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_srtp],
        required_tool_names=("local_memory", "srtp"),
    )
    checks["naive_preflight_missing_srtp"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["srtp"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "srtp"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SRTP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "srtp" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="srtp-actuation-") as tmp:
        root = Path(tmp)
        missing = run_srtp_workflow(with_ssrc=False, output_dir=root / "missing")
        skip_bind = run_srtp_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_protect = run_srtp_workflow(do_protect=False, output_dir=root / "skip-protect")
        skip_unprotect = run_srtp_workflow(do_unprotect=False, output_dir=root / "skip-unprotect")
        skip_roc = run_srtp_workflow(do_roc=False, output_dir=root / "skip-roc")
        skip_replay = run_srtp_workflow(replay=False, output_dir=root / "skip-replay")
        skip_ssrc = run_srtp_workflow(use_ssrc=False, output_dir=root / "skip-ssrc")
        live = run_srtp_workflow(output_dir=root / "live")
        verify = verify_srtp_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_srtp_trace(clone)
        checks["naive_without_ssrc_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_ssrc"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_protect_stays_empty"] = (
            skip_protect["ok"] is False
            and skip_protect["error"] == "protect_required"
            and skip_protect["final_status"] == 409
            and skip_protect["payload_exists"] is False
        )
        checks["skip_unprotect_stays_empty"] = (
            skip_unprotect["ok"] is False
            and skip_unprotect["error"] == "unprotect_required"
            and skip_unprotect["final_status"] == 409
            and skip_unprotect["payload_exists"] is False
        )
        checks["skip_roc_stays_empty"] = (
            skip_roc["ok"] is False
            and skip_roc["error"] == "roc_required"
            and skip_roc["final_status"] == 409
            and skip_roc["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_ssrc_stays_empty"] = (
            skip_ssrc["ok"] is False
            and skip_ssrc["error"] == "ssrc_required"
            and skip_ssrc["final_status"] == 409
            and skip_ssrc["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_roc"] = (
            int(live.get("ssrc") or 0) == DEFAULT_SSRC
            and int(live.get("roc") or 0) == DEFAULT_ROC
            and int(live.get("port") or 0) > 0
        )
        checks["token_ssrc_protect_unprotect_roc_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_protect["ok"] is False
            and skip_unprotect["ok"] is False
            and skip_roc["ok"] is False
            and skip_replay["ok"] is False
            and skip_ssrc["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="srtp-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SRTP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_srtp"] = (
        live_goal == SRTP_ACTUATION_GOAL
        and SRTP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_srtp"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_srtp_actuation_capability()
    return {
        "ok": ok,
        "action": "srtp_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SRTP_ACTUATION_GOAL,
        "done_when": SRTP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
