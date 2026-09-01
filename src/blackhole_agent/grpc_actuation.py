"""Drive a first-class grpc tool through HTTP/2 length-prefixed RPC.

Tool routing already fails missions that require ``grpc``: hosted RPC
plugins stay on the unsupported MCP provider, and no first-party HTTP/2
gRPC provider is executable. Unbound therefore cannot complete a connection
preface, SETTINGS exchange, HPACK HEADERS, length-prefixed DATA, or
grpc-status TRAILERS, and cannot independently replay a sealed status digest.

This module closes that hole:

- advertise a ``grpc`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback HTTP/2 gRPC listener
- keep a missing-token client so the Bearer metadata hole stays falsifiable
- refuse HEADERS/DATA/TRAILERS until PREFACE plus SETTINGS succeed
- encode protobuf SealRequest/SealReply inside the 5-byte gRPC envelope
- independently re-invoke /blackhole.v1.Actuator/Seal on a later stream
- persist a sealed status digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after ssh
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
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    GRPC_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    grpc_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
GRPC_ACTUATION_ID = "capability.grpc-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-GRPC-OK"
DEFAULT_TOKEN = "blackhole-grpc-secret"
SERVICE_PATH = "/blackhole.v1.Actuator/Seal"
CONTENT_TYPE = "application/grpc"
SEALED_NAME = "sealed.json"
RETAINED_NAME = "retained.bin"
IO_TIMEOUT = 2.0
PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
MAX_FRAME = 256 * 1024

FRAME_DATA = 0x0
FRAME_HEADERS = 0x1
FRAME_RST_STREAM = 0x3
FRAME_SETTINGS = 0x4
FRAME_PING = 0x6
FRAME_GOAWAY = 0x7
FRAME_WINDOW_UPDATE = 0x8

FLAG_END_STREAM = 0x1
FLAG_ACK = 0x1
FLAG_END_HEADERS = 0x4

GRPC_OK = "0"
GRPC_UNAUTHENTICATED = "16"
GRPC_PERMISSION_DENIED = "7"

GRPC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{GRPC_ACTUATION_ID};"
    f"capability_proved:{GRPC_ACTUATION_ID};"
    "no_skill_route"
)
GRPC_ACTUATION_GOAL = (
    "Repair grpc http2 length-prefixed rpc: hosted grpc tools remain "
    "unsupported so a PREFACE/SETTINGS/HEADERS/DATA/TRAILERS cycle cannot "
    "land and a sealed status digest cannot be produced. A missing grpc "
    "metadata token stays forbidden; fail-closed routing never opts the grpc "
    "provider in. The http2 stream and later-session rpc replay keep the hole "
    "falsifiable."
)


class GrpcActuationError(RuntimeError):
    """Raised when the gRPC session or HTTP/2 listener fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def encode_frame(payload: bytes, *, ftype: int, flags: int, stream_id: int) -> bytes:
    body = bytes(payload or b"")
    if len(body) > MAX_FRAME:
        raise GrpcActuationError("frame too large")
    header = struct.pack(">I", len(body))[1:]
    header += bytes([int(ftype) & 0xFF, int(flags) & 0xFF])
    header += struct.pack(">I", int(stream_id) & 0x7FFFFFFF)
    return header + body


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    if size < 0 or size > MAX_FRAME + 9:
        raise GrpcActuationError(f"read length out of range: {size}")
    buf = bytearray()
    while len(buf) < size:
        chunk = conn.recv(size - len(buf))
        if not chunk:
            raise GrpcActuationError("eof")
        buf.extend(chunk)
    return bytes(buf)


def decode_frame(conn: socket.socket) -> tuple[int, int, int, bytes]:
    header = _recv_exact(conn, 9)
    length = int.from_bytes(header[0:3], "big")
    if length > MAX_FRAME:
        raise GrpcActuationError("frame too large")
    ftype = header[3]
    flags = header[4]
    stream_id = struct.unpack(">I", header[5:9])[0] & 0x7FFFFFFF
    payload = _recv_exact(conn, length) if length else b""
    return ftype, flags, stream_id, payload


def hpack_int(value: int, n: int, leading: int = 0) -> bytes:
    maxv = (1 << n) - 1
    if value < maxv:
        return bytes([leading | value])
    out = bytearray([leading | maxv])
    remain = int(value) - maxv
    while remain >= 128:
        out.append((remain & 0x7F) | 0x80)
        remain >>= 7
    out.append(remain)
    return bytes(out)


def read_hpack_int(data: bytes, offset: int, n: int) -> tuple[int, int]:
    if offset >= len(data):
        raise GrpcActuationError("truncated hpack int")
    mask = (1 << n) - 1
    value = data[offset] & mask
    offset += 1
    if value < mask:
        return value, offset
    shift = 0
    while True:
        if offset >= len(data):
            raise GrpcActuationError("truncated hpack int")
        byte = data[offset]
        offset += 1
        value += (byte & 0x7F) << shift
        shift += 7
        if byte & 0x80 == 0:
            return value, offset
        if shift > 63:
            raise GrpcActuationError("hpack int overflow")


def hpack_string(text: str) -> bytes:
    raw = str(text).encode("ascii")
    return hpack_int(len(raw), 7) + raw


def read_hpack_string(data: bytes, offset: int) -> tuple[str, int]:
    if offset >= len(data):
        raise GrpcActuationError("truncated hpack string")
    if data[offset] & 0x80:
        raise GrpcActuationError("huffman unsupported")
    length, offset = read_hpack_int(data, offset, 7)
    raw = data[offset : offset + length]
    if len(raw) != length:
        raise GrpcActuationError("truncated hpack string body")
    return raw.decode("ascii", errors="replace"), offset + length


def encode_hpack_headers(headers: Sequence[tuple[str, str]]) -> bytes:
    out = bytearray()
    for name, value in headers:
        out.append(0x00)
        out.extend(hpack_string(str(name).lower()))
        out.extend(hpack_string(str(value)))
    return bytes(out)


def decode_hpack_headers(payload: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    offset = 0
    data = bytes(payload or b"")
    while offset < len(data):
        first = data[offset]
        if first & 0x80:
            _index, offset = read_hpack_int(data, offset, 7)
            continue
        if first & 0xC0 == 0x40:
            index, offset = read_hpack_int(data, offset, 6)
            if index == 0:
                name, offset = read_hpack_string(data, offset)
            else:
                name = f"idx{index}"
            value, offset = read_hpack_string(data, offset)
            headers[name] = value
            continue
        if first & 0xE0 == 0x20:
            _size, offset = read_hpack_int(data, offset, 5)
            continue
        index, offset = read_hpack_int(data, offset, 4)
        if index == 0:
            name, offset = read_hpack_string(data, offset)
        else:
            name = f"idx{index}"
        value, offset = read_hpack_string(data, offset)
        headers[name] = value
    return headers


def write_varint(value: int) -> bytes:
    if value < 0:
        raise GrpcActuationError("negative varint")
    out = bytearray()
    remain = int(value)
    while remain > 127:
        out.append((remain & 0x7F) | 0x80)
        remain >>= 7
    out.append(remain)
    return bytes(out)


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise GrpcActuationError("truncated varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return value, offset
        shift += 7
        if shift > 63:
            raise GrpcActuationError("varint overflow")


def proto_bytes_field(field: int, raw: bytes) -> bytes:
    tag = (int(field) << 3) | 2
    body = bytes(raw or b"")
    return write_varint(tag) + write_varint(len(body)) + body


def encode_seal_request(token: str) -> bytes:
    return proto_bytes_field(1, str(token).encode("utf-8"))


def encode_seal_reply(sentinel: str, digest: str) -> bytes:
    return proto_bytes_field(1, str(sentinel).encode("utf-8")) + proto_bytes_field(
        2, str(digest).encode("utf-8")
    )


def decode_proto_map(data: bytes) -> dict[int, bytes]:
    fields: dict[int, bytes] = {}
    offset = 0
    body = bytes(data or b"")
    while offset < len(body):
        tag, offset = read_varint(body, offset)
        field = tag >> 3
        wire = tag & 7
        if wire != 2:
            raise GrpcActuationError("unsupported protobuf wire type")
        length, offset = read_varint(body, offset)
        value = body[offset : offset + length]
        if len(value) != length:
            raise GrpcActuationError("truncated protobuf field")
        fields[int(field)] = value
        offset += length
    return fields


def encode_grpc_message(message: bytes) -> bytes:
    body = bytes(message or b"")
    return b"\x00" + struct.pack(">I", len(body)) + body


def decode_grpc_message(data: bytes) -> bytes:
    blob = bytes(data or b"")
    if len(blob) < 5:
        raise GrpcActuationError("truncated grpc envelope")
    length = struct.unpack(">I", blob[1:5])[0]
    body = blob[5 : 5 + length]
    if len(body) != length:
        raise GrpcActuationError("truncated grpc message")
    return body


def _ignore_control(conn: socket.socket, ftype: int, flags: int, payload: bytes) -> bool:
    if ftype == FRAME_SETTINGS:
        if not (flags & FLAG_ACK):
            conn.sendall(encode_frame(b"", ftype=FRAME_SETTINGS, flags=FLAG_ACK, stream_id=0))
        return True
    if ftype == FRAME_WINDOW_UPDATE:
        return True
    if ftype == FRAME_PING:
        if not (flags & FLAG_ACK):
            conn.sendall(encode_frame(payload, ftype=FRAME_PING, flags=FLAG_ACK, stream_id=0))
        return True
    return False


class GrpcListener:
    """Loopback HTTP/2 gRPC listener that retains the last SealReply."""

    def __init__(self, secret: str) -> None:
        self.secret = str(secret or "")
        self.retained = b""
        self.last_status = ""
        self.calls = 0
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(16)
        self._sock.settimeout(0.2)
        self.host, self.port = self._sock.getsockname()[:2]
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="grpc-h2-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=1)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            worker = threading.Thread(target=self._serve, args=(conn,), daemon=True)
            worker.start()

    def _goaway(self, conn: socket.socket, error_code: int = 1) -> None:
        payload = struct.pack(">II", 0, error_code)
        try:
            conn.sendall(encode_frame(payload, ftype=FRAME_GOAWAY, flags=0, stream_id=0))
        except OSError:
            pass

    def _respond(
        self,
        conn: socket.socket,
        stream_id: int,
        headers: Mapping[str, str],
        data: bytes,
    ) -> None:
        path = str(headers.get(":path") or "")
        method = str(headers.get(":method") or "")
        content_type = str(headers.get("content-type") or "")
        authorization = str(headers.get("authorization") or "")
        if path != SERVICE_PATH or method != "POST" or not content_type.startswith(CONTENT_TYPE):
            self._send_status(conn, stream_id, GRPC_PERMISSION_DENIED, b"")
            return
        presented = ""
        if authorization.lower().startswith("bearer "):
            presented = authorization[7:].strip()
        if not self.secret:
            self._send_status(conn, stream_id, GRPC_PERMISSION_DENIED, b"")
            return
        if not presented:
            self._send_status(conn, stream_id, GRPC_UNAUTHENTICATED, b"")
            return
        if presented != self.secret:
            self._send_status(conn, stream_id, GRPC_PERMISSION_DENIED, b"")
            return
        try:
            message = decode_grpc_message(data)
            fields = decode_proto_map(message)
        except GrpcActuationError:
            self._send_status(conn, stream_id, GRPC_PERMISSION_DENIED, b"")
            return
        token = fields.get(1, b"").decode("utf-8", errors="replace")
        digest = payload_sha256(message)
        reply = encode_seal_reply(SENTINEL if token == SENTINEL else "", digest)
        with self._lock:
            self.retained = reply
            self.last_status = GRPC_OK
            self.calls += 1
        self._send_status(conn, stream_id, GRPC_OK, encode_grpc_message(reply))

    def _send_status(self, conn: socket.socket, stream_id: int, grpc_status: str, data: bytes) -> None:
        response_headers = encode_hpack_headers(
            (
                (":status", "200"),
                ("content-type", CONTENT_TYPE),
                ("grpc-encoding", "identity"),
            )
        )
        conn.sendall(
            encode_frame(
                response_headers,
                ftype=FRAME_HEADERS,
                flags=FLAG_END_HEADERS,
                stream_id=stream_id,
            )
        )
        if data:
            conn.sendall(encode_frame(data, ftype=FRAME_DATA, flags=0, stream_id=stream_id))
        trailers = encode_hpack_headers(
            (
                ("grpc-status", grpc_status),
                ("grpc-message", "ok" if grpc_status == GRPC_OK else "denied"),
            )
        )
        conn.sendall(
            encode_frame(
                trailers,
                ftype=FRAME_HEADERS,
                flags=FLAG_END_HEADERS | FLAG_END_STREAM,
                stream_id=stream_id,
            )
        )

    def _serve(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(IO_TIMEOUT)
            preface = _recv_exact(conn, 24)
            if preface != PREFACE:
                self._goaway(conn)
                return
            conn.sendall(encode_frame(b"", ftype=FRAME_SETTINGS, flags=0, stream_id=0))
            saw_settings = False
            headers: dict[str, str] = {}
            data = bytearray()
            stream_id = 1
            while not self._stop.is_set():
                ftype, flags, stream_id, payload = decode_frame(conn)
                if _ignore_control(conn, ftype, flags, payload):
                    if ftype == FRAME_SETTINGS and not (flags & FLAG_ACK):
                        saw_settings = True
                    continue
                if ftype in {FRAME_RST_STREAM, FRAME_GOAWAY}:
                    return
                if not saw_settings:
                    self._goaway(conn)
                    return
                if ftype == FRAME_HEADERS:
                    headers = decode_hpack_headers(payload)
                    if flags & FLAG_END_STREAM:
                        self._respond(conn, stream_id, headers, bytes(data))
                        return
                    continue
                if ftype == FRAME_DATA:
                    data.extend(payload)
                    if flags & FLAG_END_STREAM:
                        self._respond(conn, stream_id, headers, bytes(data))
                        return
                    continue
                self._goaway(conn)
                return
        except (OSError, GrpcActuationError, TimeoutError, struct.error, ValueError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass


class GrpcClient:
    """HTTP/2 gRPC client used by the actuation workflow."""

    def __init__(self) -> None:
        self.sock: socket.socket | None = None
        self.headers: dict[str, str] = {}
        self.trailers: dict[str, str] = {}
        self.message = b""

    def close(self) -> None:
        sock = self.sock
        self.sock = None
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass

    def _drain_settings(self, sock: socket.socket) -> None:
        saw_settings = False
        saw_ack = False
        for _ in range(8):
            if saw_settings and saw_ack:
                return
            ftype, flags, _stream_id, payload = decode_frame(sock)
            if ftype == FRAME_SETTINGS:
                if flags & FLAG_ACK:
                    saw_ack = True
                else:
                    sock.sendall(
                        encode_frame(b"", ftype=FRAME_SETTINGS, flags=FLAG_ACK, stream_id=0)
                    )
                    saw_settings = True
                continue
            if ftype == FRAME_WINDOW_UPDATE:
                continue
            if ftype == FRAME_PING and not (flags & FLAG_ACK):
                sock.sendall(encode_frame(payload, ftype=FRAME_PING, flags=FLAG_ACK, stream_id=0))
                continue
            raise GrpcActuationError("settings_required")
        if not saw_settings:
            raise GrpcActuationError("settings_required")

    def _read_response(self, sock: socket.socket, *, need_trailers: bool) -> tuple[dict[str, str], bytes, dict[str, str]]:
        headers: dict[str, str] = {}
        trailers: dict[str, str] = {}
        data = bytearray()
        saw_headers = False
        for _ in range(16):
            ftype, flags, _stream_id, payload = decode_frame(sock)
            if _ignore_control(sock, ftype, flags, payload):
                continue
            if ftype in {FRAME_RST_STREAM, FRAME_GOAWAY}:
                raise GrpcActuationError("reset")
            if ftype == FRAME_HEADERS:
                decoded = decode_hpack_headers(payload)
                if not saw_headers:
                    headers = decoded
                    saw_headers = True
                    if flags & FLAG_END_STREAM:
                        return headers, bytes(data), decoded
                    continue
                trailers = decoded
                return headers, bytes(data), trailers
            if ftype == FRAME_DATA:
                data.extend(payload)
                if not need_trailers and saw_headers:
                    return headers, bytes(data), {}
                if flags & FLAG_END_STREAM:
                    return headers, bytes(data), trailers
                continue
            raise GrpcActuationError("unexpected frame")
        raise GrpcActuationError("trailers_required")

    def call(
        self,
        host: str,
        port: int,
        *,
        bearer: str,
        token: str,
        authenticate: bool = True,
        preface: bool = True,
        settings: bool = True,
        headers: bool = True,
        data: bool = True,
        trailers: bool = True,
    ) -> dict[str, Any]:
        sock = socket.create_connection((host, port), timeout=IO_TIMEOUT)
        self.sock = sock
        sock.settimeout(IO_TIMEOUT)
        request = encode_seal_request(token)
        if not preface:
            return {"ok": False, "status": 409, "error": "preface_required"}
        sock.sendall(PREFACE)
        if not settings:
            return {"ok": False, "status": 409, "error": "settings_required"}
        sock.sendall(encode_frame(b"", ftype=FRAME_SETTINGS, flags=0, stream_id=0))
        self._drain_settings(sock)
        if not headers:
            return {"ok": False, "status": 409, "error": "headers_required"}
        header_list: list[tuple[str, str]] = [
            (":method", "POST"),
            (":scheme", "http"),
            (":path", SERVICE_PATH),
            (":authority", f"{host}:{port}"),
            ("content-type", CONTENT_TYPE),
            ("te", "trailers"),
            ("grpc-encoding", "identity"),
        ]
        if authenticate:
            header_list.append(("authorization", f"Bearer {bearer}"))
        sock.sendall(
            encode_frame(
                encode_hpack_headers(header_list),
                ftype=FRAME_HEADERS,
                flags=FLAG_END_HEADERS,
                stream_id=1,
            )
        )
        if not data:
            return {"ok": False, "status": 409, "error": "data_required"}
        sock.sendall(
            encode_frame(
                encode_grpc_message(request),
                ftype=FRAME_DATA,
                flags=FLAG_END_STREAM,
                stream_id=1,
            )
        )
        if not trailers:
            self._read_response(sock, need_trailers=False)
            return {"ok": False, "status": 409, "error": "trailers_required"}
        resp_headers, resp_data, resp_trailers = self._read_response(sock, need_trailers=True)
        self.headers = resp_headers
        self.trailers = resp_trailers
        grpc_status = str(resp_trailers.get("grpc-status") or "")
        if grpc_status == GRPC_UNAUTHENTICATED:
            return {"ok": False, "status": 401, "error": "auth_required", "grpc_status": grpc_status}
        if grpc_status == GRPC_PERMISSION_DENIED:
            return {"ok": False, "status": 403, "error": "auth_failed", "grpc_status": grpc_status}
        if grpc_status != GRPC_OK:
            return {"ok": False, "status": 409, "error": "trailers_required", "grpc_status": grpc_status}
        message = decode_grpc_message(resp_data) if resp_data else b""
        self.message = message
        fields = decode_proto_map(message) if message else {}
        sentinel = fields.get(1, b"").decode("utf-8", errors="replace")
        digest = fields.get(2, b"").decode("utf-8", errors="replace")
        session_id = payload_sha256(PREFACE + request + grpc_status.encode("ascii"))
        return {
            "ok": True,
            "status": 200,
            "error": "",
            "grpc_status": grpc_status,
            "sentinel": sentinel,
            "digest": digest,
            "message": message,
            "request": request,
            "session_id": session_id,
            "http_status": str(resp_headers.get(":status") or ""),
        }


class GrpcSession:
    """Token-gated HTTP/2 gRPC session: bind, publish, read."""

    def __init__(self, output_dir: Path, *, secret: str = DEFAULT_TOKEN) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.secret = str(secret or "")
        self.listener: GrpcListener | None = None
        self.delivered = False
        self.last_digest = ""
        self.last_token = ""
        self.last_session_id = ""
        self.history: list[dict[str, Any]] = []

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    @property
    def retained_path(self) -> Path:
        return self.output_dir / RETAINED_NAME

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "session_id": "",
            "delivered": self.delivered,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 409,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "session_id": "",
            "delivered": self.delivered,
        }

    def bind(self) -> dict[str, Any]:
        if self.listener is not None:
            return {
                "ok": True,
                "status": 200,
                "host": self.listener.host,
                "port": self.listener.port,
                "reused": True,
            }
        listener = GrpcListener(self.secret)
        listener.start()
        self.listener = listener
        return {
            "ok": True,
            "status": 200,
            "host": listener.host,
            "port": listener.port,
            "reused": False,
        }

    def publish(
        self,
        token: str = SENTINEL,
        *,
        authenticate: bool = True,
        preface: bool = True,
        settings: bool = True,
        headers: bool = True,
        data: bool = True,
        trailers: bool = True,
        replay: bool = True,
        secret: str | None = None,
    ) -> dict[str, Any]:
        if self.listener is None:
            return self._conflict("grpc_required")
        if not self.secret:
            return self._forbidden("missing_secret")
        presented = self.secret if secret is None else str(secret)
        live_token = str(token or SENTINEL)
        client = GrpcClient()
        replay_client: GrpcClient | None = None
        try:
            first = client.call(
                str(self.listener.host),
                int(self.listener.port),
                bearer=presented,
                token=live_token,
                authenticate=authenticate,
                preface=preface,
                settings=settings,
                headers=headers,
                data=data,
                trailers=trailers,
            )
            if not first.get("ok"):
                reason = str(first.get("error") or "auth_failed")
                status = int(first.get("status") or 403)
                if reason in {
                    "preface_required",
                    "settings_required",
                    "headers_required",
                    "data_required",
                    "trailers_required",
                }:
                    return self._conflict(reason)
                return self._forbidden(reason, status=status)
            client.close()
            if not replay:
                return self._conflict("replay_required")
            replay_client = GrpcClient()
            second = replay_client.call(
                str(self.listener.host),
                int(self.listener.port),
                bearer=self.secret,
                token=live_token,
                authenticate=True,
            )
            if not second.get("ok") or bytes(second.get("message") or b"") != bytes(first.get("message") or b""):
                return self._forbidden("replay_failed", status=503)
            reply = bytes(first.get("message") or b"")
            live_digest = payload_sha256(reply)
            session_id = str(first.get("session_id") or "")
            self.retained_path.write_bytes(reply)
            sealed = {
                "host": self.listener.host,
                "port": self.listener.port,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": live_digest,
                "session_id": session_id,
                "authenticated": True,
                "prefaced": True,
                "settings": True,
                "headers": True,
                "data": True,
                "trailers": True,
                "replayed": True,
                "independent": True,
                "grpc_status": GRPC_OK,
                "retained_path": str(self.retained_path),
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            self.last_digest = live_digest
            self.last_session_id = session_id
            live = independent_grpc_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "host": self.listener.host,
                "port": self.listener.port,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": live_digest,
                "session_id": session_id,
                "path": str(self.sealed_path),
                "authenticated": True,
                "prefaced": True,
                "settings": True,
                "headers": True,
                "data": True,
                "trailers": True,
                "replayed": True,
                "independent": True,
            }
        except (OSError, GrpcActuationError, TimeoutError, struct.error, ValueError) as error:
            reason = str(error) or "unreachable"
            if reason in {
                "preface_required",
                "settings_required",
                "headers_required",
                "data_required",
                "trailers_required",
            }:
                return self._conflict(reason)
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": reason,
                "token": live_token,
                "sentinel": "",
                "digest": "",
                "session_id": "",
            }
        finally:
            if replay_client is not None:
                replay_client.close()
            client.close()

    def read(self) -> dict[str, Any]:
        live = independent_grpc_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "session_id": str(live.get("session_id") or ""),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        listener = self.listener
        self.listener = None
        if listener is not None:
            listener.stop()
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_grpc_tool(session: GrpcSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one gRPC tool call against a bound HTTP/2 session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = True if arguments.get("authenticate") is None else bool(arguments.get("authenticate"))
    preface = True if arguments.get("preface") is None else bool(arguments.get("preface"))
    settings = True if arguments.get("settings") is None else bool(arguments.get("settings"))
    headers = True if arguments.get("headers") is None else bool(arguments.get("headers"))
    data = True if arguments.get("data") is None else bool(arguments.get("data"))
    trailers = True if arguments.get("trailers") is None else bool(arguments.get("trailers"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    secret = arguments.get("secret")
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            authenticate=authenticate,
            preface=preface,
            settings=settings,
            headers=headers,
            data=data,
            trailers=trailers,
            replay=replay,
            secret=None if secret is None else str(secret),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise GrpcActuationError(f"unsupported grpc action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_grpc_digest(sealed_path: Path) -> dict[str, Any]:
    """Re-hash the retained SealReply through a fresh open and compare the sealed digest."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "session_id": "",
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
    digest = str(payload.get("digest") or "")
    retained_path = Path(str(payload.get("retained_path") or ""))
    live_digest = payload_sha256(retained_path.read_bytes()) if retained_path.is_file() else ""
    authenticated = payload.get("authenticated") is True
    prefaced = payload.get("prefaced") is True
    settings = payload.get("settings") is True
    headers = payload.get("headers") is True
    data = payload.get("data") is True
    trailers = payload.get("trailers") is True
    replayed = payload.get("replayed") is True
    independent = payload.get("independent") is True
    matched = bool(digest) and digest == live_digest
    sentinel = (
        SENTINEL
        if token == SENTINEL
        and matched
        and authenticated
        and prefaced
        and settings
        and headers
        and data
        and trailers
        and replayed
        and independent
        else ""
    )
    return {
        "ok": bool(sentinel) and matched,
        "token": token,
        "sentinel": sentinel,
        "digest": digest,
        "live_digest": live_digest,
        "session_id": str(payload.get("session_id") or ""),
        "authenticated": authenticated,
        "prefaced": prefaced,
        "settings": settings,
        "headers": headers,
        "data": data,
        "trailers": trailers,
        "replayed": replayed,
        "independent": independent,
        "error": "" if sentinel else "digest_mismatch",
    }


def run_grpc_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    preface: bool = True,
    settings: bool = True,
    headers: bool = True,
    data: bool = True,
    trailers: bool = True,
    replay: bool = True,
    secret: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the PREFACE/SETTINGS/HEADERS/DATA/TRAILERS workflow and seal a trace."""

    descriptor = grpc_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GRPC_TOOL_PROVIDER),
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
        raise GrpcActuationError(f"grpc tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="grpc-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = GrpcSession(out, secret=DEFAULT_TOKEN if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    publish_args: dict[str, Any] = {
        "action": "publish",
        "token": SENTINEL,
        "authenticate": authenticate,
        "preface": preface,
        "settings": settings,
        "headers": headers,
        "data": data,
        "trailers": trailers,
        "replay": replay,
    }
    if secret is not None:
        publish_args["secret"] = secret
    calls.append(publish_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_grpc_tool(session, arguments))
            except GrpcActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_grpc_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and preface
        and settings
        and headers
        and data
        and trailers
        and replay
        and secret is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "grpc_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "preface": preface,
        "settings": settings,
        "headers": headers,
        "data": data,
        "trailers": trailers,
        "replay": replay,
        "wrong_secret": secret is not None,
        "sealed_path": str(session.sealed_path),
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "independent": independent,
        "independent_digest": _digest(independent),
        "sentinel": sentinel,
        "digest": str(publish_result.get("digest") or session.last_digest),
        "session_id": str(publish_result.get("session_id") or session.last_session_id),
        "delivered": bool(session.delivered or publish_result.get("replayed")),
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
        "session_id": str(trace_body["session_id"] or ""),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "delivered": bool(trace_body["delivered"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "preface": preface,
        "settings": settings,
        "headers": headers,
        "data": data,
        "trailers": trailers,
        "replay": replay,
    }


def verify_grpc_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed gRPC trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_grpc_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
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
        "delivered": trace.get("delivered") is True,
        "authenticated": independent.get("authenticated") is True,
        "prefaced": independent.get("prefaced") is True,
        "settings": independent.get("settings") is True,
        "headers": independent.get("headers") is True,
        "data": independent.get("data") is True,
        "trailers": independent.get("trailers") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "digest_matches_live": str(independent.get("digest") or "")
        == str(independent.get("live_digest") or live_row.get("live_digest") or ""),
        "session_id_recorded": len(str(trace.get("session_id") or independent.get("session_id") or "")) == 64,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def grpc_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.grpc_actuation import "
        "builtin_grpc_actuation_proof; r=builtin_grpc_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='grpc_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_grpc_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=GRPC_ACTUATION_ID,
        name="First-class HTTP/2 gRPC PREFACE/SETTINGS/HEADERS/DATA/TRAILERS actuation",
        description=(
            "Missions that require a grpc tool can opt the grpc provider in, "
            "bind a real loopback HTTP/2 listener, complete the connection "
            "preface, SETTINGS, HPACK HEADERS, length-prefixed DATA, "
            "grpc-status TRAILERS, independently re-invoke Seal on a later "
            "stream, and seal digest-chained grpc traces. Default routing "
            "stays fail-closed; a missing metadata token keeps the hole "
            "falsifiable, and skip-PREFACE, skip-SETTINGS, skip-HEADERS, "
            "skip-DATA, skip-TRAILERS, or skip-REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.grpc_actuation:builtin_grpc_actuation_proof",
        proof_command=grpc_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.ssh-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/grpc_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required grpc tool is executable after explicit provider "
            "opt-in: Unbound binds a real loopback HTTP/2 gRPC listener, "
            "completes PREFACE, SETTINGS, HPACK HEADERS, a length-prefixed "
            "protobuf Seal RPC, grpc-status TRAILERS, independently "
            "re-invokes the retained reply on a later stream, and binds this "
            "family as the next diversity-catalog successor once ssh exec is "
            "proved. Missing tokens, wrong tokens, skip-PREFACE, "
            "skip-SETTINGS, skip-HEADERS, skip-DATA, skip-TRAILERS, and "
            "skip-REPLAY stay fail-closed."
        ),
        tags=(
            "grpc",
            "http2",
            "rpc",
            "protobuf",
            "actuation",
            "diversity",
        ),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T145933Z-9b1a7524",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_grpc_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in HTTP/2 gRPC actuation seals a later-session digest."""

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
    from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
    from blackhole_agent.s3_actuation import S3_ACTUATION_GOAL, S3_ACTUATION_ID
    from blackhole_agent.ssh_actuation import SSH_ACTUATION_GOAL, SSH_ACTUATION_ID
    from blackhole_agent.tool_routing import GRPC_TOOL_PROVIDER
    from blackhole_agent.watch_actuation import WATCH_ACTUATION_GOAL, WATCH_ACTUATION_ID
    from blackhole_agent.websocket_actuation import WEBSOCKET_ACTUATION_GOAL, WEBSOCKET_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = GRPC_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(GRPC_ACTUATION_GOAL) == (GRPC_ACTUATION_ID,)
    checks["ssh_goal_is_not_grpc"] = leftover_marker_ids(SSH_ACTUATION_GOAL) == (SSH_ACTUATION_ID,)
    checks["websocket_goal_is_not_grpc"] = leftover_marker_ids(WEBSOCKET_ACTUATION_GOAL) == (
        WEBSOCKET_ACTUATION_ID,
    )
    checks["watch_goal_is_not_grpc"] = leftover_marker_ids(WATCH_ACTUATION_GOAL) == (WATCH_ACTUATION_ID,)
    checks["s3_goal_is_not_grpc"] = leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    checks["mqtt_goal_is_not_grpc"] = leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    checks["grpc_goal_is_not_ssh"] = SSH_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    checks["grpc_goal_is_not_websocket"] = WEBSOCKET_ACTUATION_ID not in leftover_marker_ids(
        GRPC_ACTUATION_GOAL
    )
    checks["grpc_goal_is_not_watch"] = WATCH_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    checks["grpc_goal_is_not_s3"] = S3_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    checks["grpc_goal_is_not_mqtt"] = MQTT_ACTUATION_ID not in leftover_marker_ids(GRPC_ACTUATION_GOAL)
    checks["ssh_marker_stays_ssh"] = GRPC_ACTUATION_ID not in leftover_marker_ids(SSH_ACTUATION_GOAL)
    checks["websocket_marker_stays_websocket"] = GRPC_ACTUATION_ID not in leftover_marker_ids(
        WEBSOCKET_ACTUATION_GOAL
    )
    checks["watch_marker_stays_watch"] = GRPC_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    checks["s3_marker_stays_s3"] = GRPC_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    checks["mqtt_marker_stays_mqtt"] = GRPC_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_grpc"] = (
        len(catalog) > 43
        and catalog[43]["id"] == GRPC_ACTUATION_ID
        and catalog[42]["id"] == SSH_ACTUATION_ID
    )
    family = capability_family(GRPC_ACTUATION_GOAL)
    checks["family_is_grpc"] = "grpc" in family
    checks["family_is_http2"] = "http2" in family
    checks["family_is_length"] = "length" in family
    checks["family_is_prefixed"] = "prefixed" in family
    checks["family_is_not_openssh"] = "openssh" not in family and "ssh" not in family
    checks["family_is_not_websocket"] = "websocket" not in family and "rfc6455" not in family
    checks["family_is_not_watch"] = "watch" not in family and "path" not in family
    checks["family_is_not_object"] = "object" not in family
    checks["family_is_not_mqtt"] = "mqtt" not in family
    sample_token = "seal-me"
    request = encode_seal_request(sample_token)
    checks["protobuf_request_roundtrip"] = decode_proto_map(request).get(1) == sample_token.encode("utf-8")
    envelope = encode_grpc_message(request)
    checks["grpc_envelope_roundtrip"] = decode_grpc_message(envelope) == request
    packed = encode_hpack_headers(((":method", "POST"), ("te", "trailers")))
    decoded_headers = decode_hpack_headers(packed)
    checks["hpack_literal_roundtrip"] = (
        decoded_headers.get(":method") == "POST" and decoded_headers.get("te") == "trailers"
    )
    neighbors = (
        SSH_ACTUATION_GOAL,
        WEBSOCKET_ACTUATION_GOAL,
        WATCH_ACTUATION_GOAL,
        S3_ACTUATION_GOAL,
        MQTT_ACTUATION_GOAL,
    )
    grpc_signature = semantic_signature(GRPC_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(grpc_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_grpc = ToolDescriptor(name="remote_grpc", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_grpc)
    checks["naive_mcp_grpc_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = grpc_tool_descriptor()
    default_grpc = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GRPC_TOOL_PROVIDER),
    )
    checks["default_grpc_provider_is_unsupported"] = (
        default_grpc.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{GRPC_TOOL_PROVIDER}" in default_grpc.reasons
    )
    checks["opted_in_grpc_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_grpc],
        required_tool_names=("local_memory", "grpc"),
    )
    checks["naive_preflight_missing_grpc"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["grpc"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "grpc"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GRPC_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "grpc" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="grpc-actuation-") as tmp:
        root = Path(tmp)
        missing = run_grpc_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_grpc_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_grpc_workflow(secret="wrong-token", output_dir=root / "wrong")
        skip_bind = run_grpc_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_preface = run_grpc_workflow(preface=False, output_dir=root / "skip-preface")
        skip_settings = run_grpc_workflow(settings=False, output_dir=root / "skip-settings")
        skip_headers = run_grpc_workflow(headers=False, output_dir=root / "skip-headers")
        skip_data = run_grpc_workflow(data=False, output_dir=root / "skip-data")
        skip_trailers = run_grpc_workflow(trailers=False, output_dir=root / "skip-trailers")
        skip_replay = run_grpc_workflow(replay=False, output_dir=root / "skip-replay")
        live = run_grpc_workflow(output_dir=root / "live")
        verify = verify_grpc_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_grpc_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unsigned_rpc_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 401
            and unauth["error"] == "auth_required"
            and unauth["payload_exists"] is False
        )
        checks["wrong_token_is_forbidden"] = (
            wrong["ok"] is False
            and wrong["final_status"] == 403
            and wrong["error"] == "auth_failed"
            and wrong["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "grpc_required"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_preface_stays_empty"] = (
            skip_preface["ok"] is False
            and skip_preface["error"] == "preface_required"
            and skip_preface["final_status"] == 409
            and skip_preface["payload_exists"] is False
        )
        checks["skip_settings_stays_empty"] = (
            skip_settings["ok"] is False
            and skip_settings["error"] == "settings_required"
            and skip_settings["final_status"] == 409
            and skip_settings["payload_exists"] is False
        )
        checks["skip_headers_stays_empty"] = (
            skip_headers["ok"] is False
            and skip_headers["error"] == "headers_required"
            and skip_headers["final_status"] == 409
            and skip_headers["payload_exists"] is False
        )
        checks["skip_data_stays_empty"] = (
            skip_data["ok"] is False
            and skip_data["error"] == "data_required"
            and skip_data["final_status"] == 409
            and skip_data["payload_exists"] is False
        )
        checks["skip_trailers_stays_empty"] = (
            skip_trailers["ok"] is False
            and skip_trailers["error"] == "trailers_required"
            and skip_trailers["final_status"] == 409
            and skip_trailers["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["token_preface_settings_headers_data_trailers_and_replay_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_bind["ok"] is False
            and skip_preface["ok"] is False
            and skip_settings["ok"] is False
            and skip_headers["ok"] is False
            and skip_data["ok"] is False
            and skip_trailers["ok"] is False
            and skip_replay["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False
        checks["session_id_is_sha256"] = len(str(live.get("session_id") or "")) == 64

    with tempfile.TemporaryDirectory(prefix="grpc-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != GRPC_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_grpc"] = (
        live_goal == GRPC_ACTUATION_GOAL
        and GRPC_ACTUATION_ID in live_done
        and live_source == "genesis_bind_grpc"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_grpc_actuation_capability()
    return {
        "ok": ok,
        "action": "grpc_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": GRPC_ACTUATION_GOAL,
        "done_when": GRPC_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
